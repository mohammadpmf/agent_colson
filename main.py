"""Entry point for the DeepSeek Local Agent desktop application."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

# Ensure the project root is on sys.path when running `python main.py`
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import load_config
from app.logging_setup import setup_logging
from app.ui.main_window import MainWindow


def main() -> int:
    config = load_config()
    setup_logging(config.log_dir)

    app = QApplication(sys.argv)
    app.setApplicationName("DeepSeek Local Agent")
    app.setOrganizationName("DeepSeekAgent")

    window = MainWindow(config)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
