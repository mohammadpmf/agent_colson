"""JSON-file-based conversation store."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .models import Conversation

log = logging.getLogger(__name__)


class ConversationStore:
    """Persists conversations under `<data_dir>/conversations/*.json`."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    def _path(self, conv_id: str) -> Path:
        return self.base_dir / f"{conv_id}.json"

    def save(self, conversation: Conversation) -> None:
        try:
            self._path(conversation.id).write_text(
                json.dumps(conversation.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:
            log.error("Failed to save conversation %s: %s", conversation.id, exc)

    def load(self, conv_id: str) -> Conversation | None:
        path = self._path(conv_id)
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            log.error("Failed to load conversation %s: %s", conv_id, exc)
            return None
        return Conversation.from_dict(raw)

    def list_all(self) -> list[Conversation]:
        items: list[Conversation] = []
        for p in sorted(
            self.base_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True
        ):
            try:
                raw = json.loads(p.read_text(encoding="utf-8"))
                items.append(Conversation.from_dict(raw))
            except (json.JSONDecodeError, OSError):
                continue
        return items

    def delete(self, conv_id: str) -> None:
        path = self._path(conv_id)
        try:
            if path.exists():
                path.unlink()
        except OSError as exc:
            log.error("Failed to delete conversation %s: %s", conv_id, exc)
