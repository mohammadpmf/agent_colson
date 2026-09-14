"""GapGPT provider — OpenAI-compatible chat + tool calling."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Callable

import requests

from .base import ChatMessage, LLMProvider, LLMResponse, ToolCall

log = logging.getLogger(__name__)


class GapGPTError(Exception):
    """Raised for any GapGPT API error."""


def _decode_response(response: requests.Response) -> str:
    """Force UTF-8 decoding and strip a possible BOM."""
    response.encoding = "utf-8"
    text = response.text
    if text and text[0] == "\ufeff":
        text = text[1:]
    return text


class GapGPTProvider(LLMProvider):
    """Concrete provider for the GapGPT API (OpenAI-compatible)."""

    name = "gapgpt"

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        base_url: str = "https://api.gapgpt.app/v1",
        temperature: float = 0.2,
        max_tokens: int = 4096,
        timeout: int = 60,
    ) -> None:
        self.api_key = api_key.strip()
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json, text/event-stream",
            "Accept-Charset": "utf-8",
        }

    def test_connection(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "API key is empty."
        try:
            r = requests.get(
                f"{self.base_url}/models",
                headers=self._headers(),
                timeout=15,
            )
            if r.status_code == 200:
                return True, "Connected"
            if r.status_code == 401:
                return False, "Authentication failed (401). Check your API key."
            if r.status_code == 404:
                return self._probe_chat()
            return False, f"HTTP {r.status_code}: {_decode_response(r)[:200]}"
        except requests.RequestException as exc:
            return False, f"Network error: {exc}"

    def _probe_chat(self) -> tuple[bool, str]:
        try:
            r = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                    "stream": False,
                },
                timeout=20,
            )
            if r.status_code < 400:
                return True, "Connected (via chat probe)"
            if r.status_code == 401:
                return False, "Authentication failed (401). Check your API key."
            return False, f"HTTP {r.status_code}: {_decode_response(r)[:200]}"
        except requests.RequestException as exc:
            return False, f"Network error: {exc}"

    def chat(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None = None,
        stream: bool = True,
        on_token: Callable[[str], None] | None = None,
        cancel_flag: Callable[[], bool] | None = None,
    ) -> LLMResponse:
        if not self.api_key:
            raise GapGPTError("GapGPT API key is not configured.")

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [m.to_api() for m in messages],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": bool(stream),
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        url = f"{self.base_url}/chat/completions"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        log.info(
            "[gapgpt] POST %s model=%s stream=%s tools=%d messages=%d",
            url,
            self.model,
            stream,
            len(tools or []),
            len(messages),
        )

        if stream:
            try:
                return self._stream_chat(url, body, on_token, cancel_flag)
            except GapGPTError as exc:
                log.warning("[gapgpt] streaming failed (%s); falling back", exc)
                return self._blocking_chat(url, body, on_token)

        return self._blocking_chat(url, body, on_token)

    def _blocking_chat(
        self,
        url: str,
        body: bytes,
        on_token: Callable[[str], None] | None = None,
    ) -> LLMResponse:
        payload = json.loads(body.decode("utf-8"))
        payload["stream"] = False
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        try:
            r = requests.post(
                url, headers=self._headers(), data=body, timeout=self.timeout
            )
        except requests.Timeout as exc:
            raise GapGPTError(f"Request timed out after {self.timeout}s.") from exc
        except requests.RequestException as exc:
            raise GapGPTError(f"Network error: {exc}") from exc

        self._raise_for_status(r)
        text = _decode_response(r)
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise GapGPTError(
                f"Upstream returned non-JSON response: {text[:200]!r}"
            ) from exc

        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message", {}) or {}
        usage = data.get("usage", {}) or {}

        content = message.get("content") or ""
        if content and on_token:
            on_token(content)

        return LLMResponse(
            content=content,
            tool_calls=_parse_tool_calls(message.get("tool_calls")),
            finish_reason=choice.get("finish_reason", "stop"),
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
        )

    def _stream_chat(
        self,
        url: str,
        body: bytes,
        on_token: Callable[[str], None] | None,
        cancel_flag: Callable[[], bool] | None,
    ) -> LLMResponse:
        content_parts: list[str] = []
        tool_acc: dict[int, dict[str, Any]] = {}
        finish_reason = "stop"
        input_tokens = 0
        output_tokens = 0

        try:
            with requests.post(
                url,
                headers=self._headers(),
                data=body,
                timeout=self.timeout,
                stream=True,
            ) as r:
                r.encoding = "utf-8"
                self._raise_for_status(r)

                content_type = r.headers.get("Content-Type", "").lower()
                if "text/event-stream" not in content_type:
                    raw = r.content
                    if raw.startswith(b"\xef\xbb\xbf"):
                        raw = raw[3:]
                    text = raw.decode("utf-8", errors="replace")
                    try:
                        data = json.loads(text)
                    except json.JSONDecodeError as exc:
                        raise GapGPTError(
                            f"Upstream did not return SSE and body wasn't JSON "
                            f"(Content-Type={content_type!r})."
                        ) from exc
                    choice = (data.get("choices") or [{}])[0]
                    message = choice.get("message", {}) or {}
                    usage = data.get("usage", {}) or {}
                    text_content = message.get("content") or ""
                    if text_content and on_token:
                        on_token(text_content)
                    return LLMResponse(
                        content=text_content,
                        tool_calls=_parse_tool_calls(message.get("tool_calls")),
                        finish_reason=choice.get("finish_reason", "stop"),
                        input_tokens=int(usage.get("prompt_tokens", 0)),
                        output_tokens=int(usage.get("completion_tokens", 0)),
                    )

                for raw_line in r.iter_lines(decode_unicode=True):
                    if cancel_flag and cancel_flag():
                        break
                    if not raw_line:
                        continue
                    line = raw_line.strip()
                    if line.startswith("\ufeff"):
                        line = line.lstrip("\ufeff")
                    if not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    usage = chunk.get("usage")
                    if usage:
                        input_tokens = int(usage.get("prompt_tokens", input_tokens))
                        output_tokens = int(
                            usage.get("completion_tokens", output_tokens)
                        )

                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    choice = choices[0]
                    delta = choice.get("delta") or {}

                    piece = delta.get("content")
                    if piece:
                        content_parts.append(piece)
                        if on_token:
                            on_token(piece)

                    for tc_delta in delta.get("tool_calls") or []:
                        idx = tc_delta.get("index", 0)
                        slot = tool_acc.setdefault(
                            idx, {"id": "", "name": "", "arguments": ""}
                        )
                        if tc_delta.get("id"):
                            slot["id"] = tc_delta["id"]
                        fn = tc_delta.get("function") or {}
                        if fn.get("name"):
                            slot["name"] = fn["name"]
                        if fn.get("arguments"):
                            slot["arguments"] += fn["arguments"]

                    if choice.get("finish_reason"):
                        finish_reason = choice["finish_reason"]
        except requests.Timeout as exc:
            raise GapGPTError(
                f"Streaming request timed out after {self.timeout}s."
            ) from exc
        except requests.RequestException as exc:
            raise GapGPTError(f"Network error: {exc}") from exc

        tool_calls: list[ToolCall] = []
        for slot in tool_acc.values():
            if not slot["name"]:
                continue
            try:
                args = json.loads(slot["arguments"]) if slot["arguments"] else {}
            except json.JSONDecodeError:
                args = {"_raw": slot["arguments"]}
            tool_calls.append(
                ToolCall(
                    id=slot["id"] or f"call_{uuid.uuid4().hex[:8]}",
                    name=slot["name"],
                    arguments=args,
                )
            )

        return LLMResponse(
            content="".join(content_parts),
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    @staticmethod
    def _raise_for_status(r: requests.Response) -> None:
        if r.status_code < 400:
            return
        detail = _decode_response(r)
        try:
            body = json.loads(detail)
            detail = (
                body.get("error", {}).get("message") or body.get("message") or detail
            )
        except Exception:  # noqa: BLE001
            pass
        if r.status_code == 401:
            raise GapGPTError(f"Authentication failed (401): {detail}")
        if r.status_code == 402:
            raise GapGPTError(f"Payment required (402): {detail}")
        if r.status_code == 429:
            raise GapGPTError(f"Rate limit exceeded (429): {detail}")
        if 500 <= r.status_code < 600:
            raise GapGPTError(f"Server error ({r.status_code}): {detail}")
        raise GapGPTError(f"HTTP {r.status_code}: {detail}")


def _parse_tool_calls(raw: Any) -> list[ToolCall]:
    if not raw:
        return []
    calls: list[ToolCall] = []
    for item in raw:
        fn = item.get("function") or {}
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {"_raw": fn.get("arguments", "")}
        calls.append(
            ToolCall(
                id=item.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                name=fn.get("name", ""),
                arguments=args,
            )
        )
    return calls
