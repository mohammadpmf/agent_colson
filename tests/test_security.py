from __future__ import annotations

from pathlib import Path

import pytest

from app.security import SecurityGuard, SecurityViolation


@pytest.fixture()
def guard(tmp_path: Path) -> SecurityGuard:
    return SecurityGuard(tmp_path)


def test_path_inside_ok(guard: SecurityGuard, tmp_path: Path):
    (tmp_path / "a.py").write_text("x")
    p = guard.check_path("a.py")
    assert p.name == "a.py"


def test_path_outside_raises(guard: SecurityGuard):
    with pytest.raises(SecurityViolation):
        guard.check_path("../escape.txt")


def test_sensitive_detection(guard: SecurityGuard, tmp_path: Path):
    assert guard.is_sensitive(tmp_path / ".env") is True
    assert guard.is_sensitive(tmp_path / "id_rsa") is True
    assert guard.is_sensitive(tmp_path / "server.pem") is True
    assert guard.is_sensitive(tmp_path / "main.py") is False


def test_secret_detection(guard: SecurityGuard):
    text = 'api_key = "sk-abcdefghijklmnop1234"'
    found = guard.contains_secret(text)
    assert found


def test_dangerous_command_detection(guard: SecurityGuard):
    assert guard.is_dangerous_command("rm -rf /") is True
    assert guard.is_dangerous_command("echo hello") is False
    assert guard.is_dangerous_command("DROP DATABASE prod") is True
