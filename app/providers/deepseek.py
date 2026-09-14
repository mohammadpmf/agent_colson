"""DeepSeek provider implementing OpenAI-compatible chat + tool calling."""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Callable

import requests

from .base import ChatMessage, LLMProvider, LLMResponse, ToolCall

log = logging.getLogger(__name__)


class DeepSeekError(Exception):
    """Raised for any DeepSeek API error."""


class DeepSeekProvider(LLMProvider):
    """Concrete provider for the DeepSeek API."""

    name = "deepseek"

    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-chat",
        base_url: str = "https://api.deepseek.com",
        temperature: float = 0.2,
        max_tokens: int = 4096,
        timeout: int = 120,
    ) -> None:
        self.api_key = api_key.strip()
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    # ------------------------------------------------------------------ #
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
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
            return False, f"HTTP {r.status_code}: {r.text[:200]}"
        except requests.RequestException as exc:
            return False, f"Network error: {exc}"

    # ------------------------------------------------------------------ #
    def chat(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None = None,
        stream: bool = True,
        on_token: Callable[[str], None] | None = None,
        cancel_flag: Callable[[], bool] | None = None,
    ) -> LLMResponse:
        if not self.api_key:
            raise DeepSeekError("DeepSeek API key is not configured.")

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

        if stream:
            return self._stream_chat(url, payload, on_token, cancel_flag)
        return self._blocking_chat(url, payload)

    # ------------------------------------------------------------------ #
    def _blocking_chat(self, url: str, payload: dict[str, Any]) -> LLMResponse:
        try:
            r = requests.post(
                url, headers=self._headers(), json=payload, timeout=self.timeout
            )
        except requests.Timeout as exc:
            raise DeepSeekError(f"Request timed out after {self.timeout}s.") from exc
        except requests.RequestException as exc:
            raise DeepSeekError(f"Network error: {exc}") from exc

        self._raise_for_status(r)
        data = r.json()
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message", {}) or {}
        usage = data.get("usage", {}) or {}

        return LLMResponse(
            content=message.get("content") or "",
            tool_calls=_parse_tool_calls(message.get("tool_calls")),
            finish_reason=choice.get("finish_reason", "stop"),
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
        )

    def _stream_chat(
        self,
        url: str,
        payload: dict[str, Any],
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
                json=payload,
                timeout=self.timeout,
                stream=True,
            ) as r:
                self._raise_for_status(r)
                for raw_line in r.iter_lines(decode_unicode=True):
                    if cancel_flag and cancel_flag():
                        log.info("Streaming cancelled by user.")
                        break
                    if not raw_line:
                        continue
                    line = raw_line.strip()
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
                            idx,
                            {"id": "", "name": "", "arguments": ""},
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
            raise DeepSeekError(f"Request timed out after {self.timeout}s.") from exc
        except requests.RequestException as exc:
            raise DeepSeekError(f"Network error: {exc}") from exc

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

    # ------------------------------------------------------------------ #
    @staticmethod
    def _raise_for_status(r: requests.Response) -> None:
        if r.status_code < 400:
            return
        try:
            body = r.json()
            detail = (
                body.get("error", {}).get("message") or body.get("message") or r.text
            )
        except Exception:  # noqa: BLE001
            detail = r.text
        if r.status_code == 401:
            raise DeepSeekError(f"Authentication failed (401): {detail}")
        if r.status_code == 429:
            raise DeepSeekError(f"Rate limit exceeded (429): {detail}")
        if 500 <= r.status_code < 600:
            raise DeepSeekError(f"Server error ({r.status_code}): {detail}")
        raise DeepSeekError(f"HTTP {r.status_code}: {detail}")


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
