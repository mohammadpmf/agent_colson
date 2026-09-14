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
CREDENTIALS_FILE = DATA_DIR / "credentials.json"


@dataclass
class AppConfig:
    """Runtime configuration for the whole application."""

    # Active provider: "gapgpt" or "deepseek"
    provider: str = "gapgpt"

    # GapGPT
    gapgpt_api_key: str = ""
    gapgpt_base_url: str = "https://api.gapgpt.app/v1"
    gapgpt_model: str = "gpt-4o"

    # DeepSeek (kept for optional use)
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # Shared generation settings
    temperature: float = 0.2
    max_tokens: int = 4096
    streaming: bool = True

    # UI
    theme: str = "dark"
    edit_mode: str = "ask"

    # Workspace
    workspace: str = ""
    recent_workspaces: list[str] = field(default_factory=list)

    data_dir: Path = DATA_DIR
    log_dir: Path = LOGS_DIR

    # ------------------------------------------------------------------ #
    # Convenience: active credentials based on provider
    # ------------------------------------------------------------------ #
    @property
    def api_key(self) -> str:
        return (
            self.gapgpt_api_key if self.provider == "gapgpt" else self.deepseek_api_key
        )

    @property
    def base_url(self) -> str:
        return (
            self.gapgpt_base_url
            if self.provider == "gapgpt"
            else self.deepseek_base_url
        )

    @property
    def model(self) -> str:
        return self.gapgpt_model if self.provider == "gapgpt" else self.deepseek_model

    @model.setter
    def model(self, value: str) -> None:
        if self.provider == "gapgpt":
            self.gapgpt_model = value
        else:
            self.deepseek_model = value

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #
    def to_public_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Never persist raw keys here; they go to credentials.json
        d.pop("gapgpt_api_key", None)
        d.pop("deepseek_api_key", None)
        d["data_dir"] = str(self.data_dir)
        d["log_dir"] = str(self.log_dir)
        return d

    def save(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(
            json.dumps(self.to_public_dict(), indent=2), encoding="utf-8"
        )
        _save_credentials(self)

    def add_recent_workspace(self, path: str) -> None:
        if not path:
            return
        path = str(Path(path).resolve())
        self.recent_workspaces = [p for p in self.recent_workspaces if p != path]
        self.recent_workspaces.insert(0, path)
        self.recent_workspaces = self.recent_workspaces[:10]


# ---------------------------------------------------------------------- #
def _save_credentials(cfg: AppConfig) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "gapgpt_api_key": cfg.gapgpt_api_key,
        "deepseek_api_key": cfg.deepseek_api_key,
    }
    CREDENTIALS_FILE.write_text(json.dumps(payload), encoding="utf-8")
    try:
        os.chmod(CREDENTIALS_FILE, 0o600)
    except OSError:
        pass


def _load_credentials() -> dict[str, str]:
    if not CREDENTIALS_FILE.exists():
        return {}
    try:
        data = json.loads(CREDENTIALS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def load_config() -> AppConfig:
    """Build an AppConfig from .env, credentials file, and settings.json."""
    load_dotenv(ROOT_DIR / ".env")

    cfg = AppConfig()

    # 1) credentials file
    creds = _load_credentials()
    cfg.gapgpt_api_key = creds.get("gapgpt_api_key", "")
    cfg.deepseek_api_key = creds.get("deepseek_api_key", "")

    # 2) environment overrides
    if os.getenv("GAPGPT_API_KEY"):
        cfg.gapgpt_api_key = os.environ["GAPGPT_API_KEY"].strip()
    if os.getenv("GAPGPT_MODEL"):
        cfg.gapgpt_model = os.environ["GAPGPT_MODEL"].strip()
    if os.getenv("GAPGPT_BASE_URL"):
        cfg.gapgpt_base_url = os.environ["GAPGPT_BASE_URL"].strip()
    if os.getenv("DEEPSEEK_API_KEY"):
        cfg.deepseek_api_key = os.environ["DEEPSEEK_API_KEY"].strip()
    if os.getenv("DEEPSEEK_MODEL"):
        cfg.deepseek_model = os.environ["DEEPSEEK_MODEL"].strip()
    if os.getenv("DEEPSEEK_BASE_URL"):
        cfg.deepseek_base_url = os.environ["DEEPSEEK_BASE_URL"].strip()
    if os.getenv("AGENT_PROVIDER"):
        cfg.provider = os.environ["AGENT_PROVIDER"].strip().lower()

    # 3) settings.json
    if SETTINGS_FILE.exists():
        try:
            raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            raw = {}
        for field_name in (
            "provider",
            "gapgpt_base_url",
            "gapgpt_model",
            "deepseek_base_url",
            "deepseek_model",
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
