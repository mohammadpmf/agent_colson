"""Application configuration loaded from environment + local settings."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
LOGS_DIR = ROOT_DIR / "logs"
SETTINGS_FILE = DATA_DIR / "settings.json"


@dataclass
class AppConfig:
    """Runtime configuration for the whole application."""

    api_key: str = ""
    model: str = "deepseek-chat"
    base_url: str = "https://api.deepseek.com"
    temperature: float = 0.2
    max_tokens: int = 4096
    streaming: bool = True
    theme: str = "dark"
    edit_mode: str = "ask"  # ask | ask_first | auto
    workspace: str = ""
    recent_workspaces: list[str] = field(default_factory=list)

    data_dir: Path = DATA_DIR
    log_dir: Path = LOGS_DIR

    # ---------- persistence ----------
    def to_public_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("api_key", None)
        d["data_dir"] = str(self.data_dir)
        d["log_dir"] = str(self.log_dir)
        return d

    def save(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        payload = self.to_public_dict()
        # API key is stored separately in a restricted file
        SETTINGS_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        if self.api_key:
            _save_api_key(self.api_key)

    def add_recent_workspace(self, path: str) -> None:
        if not path:
            return
        path = str(Path(path).resolve())
        self.recent_workspaces = [p for p in self.recent_workspaces if p != path]
        self.recent_workspaces.insert(0, path)
        self.recent_workspaces = self.recent_workspaces[:10]


def _save_api_key(key: str) -> None:
    """Store the API key in a separate, restricted file (best-effort)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    key_file = DATA_DIR / "credentials.json"
    key_file.write_text(json.dumps({"DEEPSEEK_API_KEY": key}), encoding="utf-8")
    try:
        os.chmod(key_file, 0o600)
    except OSError:
        pass


def _load_api_key() -> str:
    env_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if env_key:
        return env_key
    key_file = DATA_DIR / "credentials.json"
    if key_file.exists():
        try:
            return json.loads(key_file.read_text(encoding="utf-8")).get(
                "DEEPSEEK_API_KEY", ""
            )
        except (json.JSONDecodeError, OSError):
            return ""
    return ""


def load_config() -> AppConfig:
    """Build an AppConfig from .env, credentials file, and settings.json."""
    load_dotenv(ROOT_DIR / ".env")

    cfg = AppConfig()
    cfg.api_key = _load_api_key()
    cfg.model = os.getenv("DEEPSEEK_MODEL", cfg.model)
    cfg.base_url = os.getenv("DEEPSEEK_BASE_URL", cfg.base_url)

    if SETTINGS_FILE.exists():
        try:
            raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            raw = {}
        for field_name in (
            "model",
            "base_url",
            "temperature",
            "max_tokens",
            "streaming",
            "theme",
            "edit_mode",
            "workspace",
        ):
            if field_name in raw:
                setattr(cfg, field_name, raw[field_name])
        cfg.recent_workspaces = list(raw.get("recent_workspaces", []))

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    return cfg
