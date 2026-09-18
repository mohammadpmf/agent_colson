"""JSON-file-based conversation store."""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
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
        if not re.fullmatch(r"[A-Za-z0-9_-]+", conv_id):
            raise ValueError("Invalid conversation ID")
        return self.base_dir / f"{conv_id}.json"

    def save(self, conversation: Conversation) -> bool:
        temporary = None
        try:
            destination = self._path(conversation.id)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.base_dir, delete=False) as handle:
                temporary = Path(handle.name)
                json.dump(conversation.to_dict(), handle, indent=2, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(destination)
            return True
        except OSError as exc:
            log.error("Failed to save conversation %s: %s", conversation.id, exc)
            return False
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def load(self, conv_id: str) -> Conversation | None:
        path = self._path(conv_id)
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            conversation = Conversation.from_dict(raw)
            conversation.id = conv_id
            return conversation
        except (ValueError, TypeError, AttributeError, OSError) as exc:
            log.error("Failed to load conversation %s: %s", conv_id, exc)
            return None

    def list_all(self) -> list[Conversation]:
        items: list[Conversation] = []
        for p in self.base_dir.glob("*.json"):
            if not re.fullmatch(r"[A-Za-z0-9_-]+", p.stem):
                continue
            conversation = self.load(p.stem)
            if conversation is not None:
                items.append(conversation)
        return sorted(items, key=lambda c: c.updated_at, reverse=True)

    def delete(self, conv_id: str) -> None:
        path = self._path(conv_id)
        try:
            if path.exists():
                path.unlink()
        except OSError as exc:
            log.error("Failed to delete conversation %s: %s", conv_id, exc)
