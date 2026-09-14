"""Central logging configuration with secret redaction."""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

_SECRET_PATTERNS = [
    re.compile(r"(sk-[A-Za-z0-9]{10,})"),
    re.compile(r"(\"DEEPSEEK_API_KEY\"\s*:\s*\")[^\"]+(\")"),
    re.compile(r"(api[_-]?key\s*[=:]\s*)([^\s,;\"']+)", re.IGNORECASE),
    re.compile(r"(password\s*[=:]\s*)([^\s,;\"']+)", re.IGNORECASE),
    re.compile(r"(token\s*[=:]\s*)([^\s,;\"']+)", re.IGNORECASE),
]


class _RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for pat in _SECRET_PATTERNS:
            if pat.groups >= 2:
                msg = pat.sub(
                    lambda m: m.group(1) + "***REDACTED***" + m.group(m.lastindex or 1),
                    msg,
                )
            else:
                msg = pat.sub("***REDACTED***", msg)
        record.msg = msg
        record.args = ()
        return True


def setup_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in list(root.handlers):
        root.removeHandler(h)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    redactor = _RedactingFilter()

    agent_handler = RotatingFileHandler(
        log_dir / "agent.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8"
    )
    agent_handler.setFormatter(fmt)
    agent_handler.addFilter(redactor)
    root.addHandler(agent_handler)

    err_handler = RotatingFileHandler(
        log_dir / "errors.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8"
    )
    err_handler.setLevel(logging.ERROR)
    err_handler.setFormatter(fmt)
    err_handler.addFilter(redactor)
    root.addHandler(err_handler)

    console = logging.StreamHandler()
    console.setLevel(logging.WARNING)
    console.setFormatter(fmt)
    console.addFilter(redactor)
    root.addHandler(console)
