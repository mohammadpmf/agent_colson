"""SQLite-backed persistence for permission rules and audit log."""

from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from .models import (
    PermissionAction,
    PermissionRule,
    PermissionScope,
)


class PermissionStorage:
    """Thread-safe SQLite storage for permission rules."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_schema()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._lock, self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS permission_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    target TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    UNIQUE(action, scope, target)
                )
                """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    action TEXT NOT NULL,
                    target TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    note TEXT
                )
                """)
            conn.commit()

    # ------------------------------------------------------------------ #
    def add_rule(self, rule: PermissionRule) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO permission_rules (action, scope, target, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    rule.action.value,
                    rule.scope.value,
                    rule.target,
                    rule.created_at or time.time(),
                ),
            )
            conn.commit()

    def list_rules(self) -> list[PermissionRule]:
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT action, scope, target, created_at FROM permission_rules ORDER BY id"
            ).fetchall()
        return [
            PermissionRule(
                action=PermissionAction(r["action"]),
                scope=PermissionScope(r["scope"]),
                target=r["target"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def clear_rules(self) -> None:
        with self._lock, self._conn() as conn:
            conn.execute("DELETE FROM permission_rules")
            conn.commit()

    def log(self, action: str, target: str, decision: str, note: str = "") -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                "INSERT INTO audit_log (ts, action, target, decision, note) VALUES (?, ?, ?, ?, ?)",
                (time.time(), action, target, decision, note),
            )
            conn.commit()

    def audit_entries(self, limit: int = 200) -> list[dict]:
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT ts, action, target, decision, note FROM audit_log ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
