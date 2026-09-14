"""Path / command / secret safety checks."""

from __future__ import annotations

import re
from pathlib import Path


class SecurityViolation(Exception):
    """Raised when the agent attempts an unsafe operation."""


_SENSITIVE_FILENAMES = {
    ".env",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "credentials.json",
    "secrets.json",
}
_SENSITIVE_SUFFIXES = (".pem", ".key", ".p12", ".pfx")

_SECRET_REGEXES = [
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"AIza[0-9A-Za-z\-_]{20,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(
        r"(?i)(api[_-]?key|password|secret|token)\s*[:=]\s*['\"]?([^\s'\"]{6,})"
    ),
]

_DANGEROUS_COMMAND_PATTERNS = [
    re.compile(r"\brm\s+-rf\b", re.IGNORECASE),
    re.compile(r"\brm\s+-fr\b", re.IGNORECASE),
    re.compile(r"\bdel\s+/[sqf]\b", re.IGNORECASE),
    re.compile(r"\bformat\b", re.IGNORECASE),
    re.compile(r"\bshutdown\b", re.IGNORECASE),
    re.compile(r"\breboot\b", re.IGNORECASE),
    re.compile(r"\bdiskpart\b", re.IGNORECASE),
    re.compile(r"\bmkfs\b", re.IGNORECASE),
    re.compile(r"\bdd\s+if=", re.IGNORECASE),
    re.compile(r"DROP\s+(DATABASE|TABLE)", re.IGNORECASE),
    re.compile(r"TRUNCATE\s+TABLE", re.IGNORECASE),
    re.compile(r":\(\)\s*\{\s*:\|\s*:\s*&\s*\};:", re.IGNORECASE),  # fork bomb
]


class SecurityGuard:
    """Stateless helper providing safety checks."""

    def __init__(self, workspace_root: Path, allow_outside: bool = False) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.allow_outside = allow_outside

    # ---------- path checks ----------
    def check_path(self, raw_path: str | Path) -> Path:
        """Normalize, resolve symlinks, and ensure within workspace."""
        p = Path(raw_path).expanduser()
        if not p.is_absolute():
            p = self.workspace_root / p
        try:
            resolved = p.resolve(strict=False)
        except OSError as exc:
            raise SecurityViolation(f"Cannot resolve path: {raw_path}") from exc

        if not self.allow_outside and not self._is_inside(resolved):
            raise SecurityViolation(
                f"Path '{resolved}' is outside workspace '{self.workspace_root}'."
            )
        return resolved

    def is_sensitive(self, path: Path) -> bool:
        name = path.name.lower()
        if name in _SENSITIVE_FILENAMES:
            return True
        if name.startswith(".env") and not name.endswith(".example"):
            return True
        if name.endswith(_SENSITIVE_SUFFIXES):
            return True
        return False

    def contains_secret(self, text: str) -> list[str]:
        """Return a list of matched secret patterns (labels, not values)."""
        found: list[str] = []
        for rx in _SECRET_REGEXES:
            if rx.search(text):
                found.append(rx.pattern[:40])
        return found

    # ---------- command checks ----------
    def is_dangerous_command(self, command: str) -> bool:
        return any(rx.search(command) for rx in _DANGEROUS_COMMAND_PATTERNS)

    def check_command(self, command: str) -> None:
        if not command.strip():
            raise SecurityViolation("Empty command.")

    # ------------------------------------------------------------------ #
    def _is_inside(self, candidate: Path) -> bool:
        try:
            candidate.relative_to(self.workspace_root)
            return True
        except ValueError:
            return False
