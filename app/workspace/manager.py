"""Workspace root management + safe path resolution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.security.guard import SecurityGuard, SecurityViolation

IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    ".env",
    "dist",
    "build",
    ".idea",
    ".vscode",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}

TEXT_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".html",
    ".htm",
    ".css",
    ".scss",
    ".sass",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".md",
    ".rst",
    ".txt",
    ".sh",
    ".bash",
    ".zsh",
    ".ps1",
    ".bat",
    ".sql",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".rb",
    ".php",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".cs",
    ".swift",
    ".lua",
    ".dockerfile",
    ".gitignore",
    ".editorconfig",
    ".env.example",
}


@dataclass
class FileEntry:
    name: str
    path: str
    is_dir: bool
    size: int = 0


class WorkspaceManager:
    """Owns the currently-opened workspace root."""

    def __init__(self, root: Path | None = None) -> None:
        self._root: Path | None = None
        if root is not None:
            self.set_root(root)

    # ------------------------------------------------------------------ #
    @property
    def root(self) -> Path | None:
        return self._root

    def set_root(self, root: Path | str) -> Path:
        r = Path(root).expanduser().resolve()
        if not r.exists():
            raise FileNotFoundError(f"Workspace does not exist: {r}")
        if not r.is_dir():
            raise NotADirectoryError(f"Workspace is not a directory: {r}")
        self._root = r
        return r

    def guard(self, allow_outside: bool = False) -> SecurityGuard:
        if self._root is None:
            raise RuntimeError("No workspace is open.")
        return SecurityGuard(self._root, allow_outside=allow_outside)

    # ------------------------------------------------------------------ #
    def list_entries(self, relative: str = ".", depth: int = 1) -> list[FileEntry]:
        if self._root is None:
            raise RuntimeError("No workspace is open.")
        base = self.resolve(relative)
        if not base.is_dir():
            return []

        entries: list[FileEntry] = []
        self._walk(base, entries, depth)
        return entries

    def _walk(self, current: Path, entries: list[FileEntry], depth: int) -> None:
        try:
            children = sorted(
                current.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())
            )
        except (OSError, PermissionError):
            return
        for child in children:
            if child.name in IGNORED_DIRS or child.is_symlink():
                continue
            try:
                is_dir = child.is_dir()
                size = 0 if is_dir else child.stat().st_size
            except OSError:
                continue
            entries.append(FileEntry(child.name, str(child), is_dir, size))
            if is_dir and depth > 1:
                self._walk(child, entries, depth - 1)

    # ------------------------------------------------------------------ #
    def resolve(self, relative: str | Path) -> Path:
        if self._root is None:
            raise RuntimeError("No workspace is open.")
        return self.guard().check_path(relative)

    def is_text_file(self, path: Path) -> bool:
        if path.suffix.lower() in TEXT_EXTENSIONS:
            return True
        if path.name.lower() in {
            "dockerfile",
            "makefile",
            ".gitignore",
            ".env.example",
        }:
            return True
        # Fallback: sniff for NUL bytes
        try:
            with path.open("rb") as handle:
                chunk = handle.read(2048)
        except OSError:
            return False
        return b"\x00" not in chunk
