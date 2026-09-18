"""Offline visual smoke test: python tests/render_preview.py."""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from app.config import AppConfig
from app.conversations import Conversation, StoredMessage
from app.ui.main_window import MainWindow

app = QApplication([])
for font in ("segoeui.ttf", "seguisb.ttf", "tahoma.ttf", "consola.ttf"):
    font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / font
    if font_path.exists():
        QFontDatabase.addApplicationFont(str(font_path))
output = ROOT / "artifacts"
output.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    (root / "example.py").write_text('print("Hello")')
    config = AppConfig(data_dir=root / "data", workspace=str(root))
    with patch.object(MainWindow, "_refresh_connection_status"), patch.object(MainWindow, "_prompt_first_run"):
        window = MainWindow(config)
        chat = Conversation(title="بررسی پروژه و ادامهٔ گفتگو", workspace=str(root), messages=[
            StoredMessage(role="user", content="سلام، لطفاً این پروژهٔ Python را بررسی کن."),
            StoredMessage(role="assistant", content='## نتیجهٔ بررسی\n\nمتن **فارسی** همراه با `Python` درست نمایش داده می‌شود.\n\nEnglish paragraph with Persian: سلام\n\n```python\ndef greet(name):\n    return f"سلام {name}"\n```\n\n- گفتگو ذخیره می‌شود.\n- برای ادامه، عنوان آن را انتخاب کنید.'),
        ])
        window.conversation_store.save(chat)
        window._load_chat(chat.id)
        window.input.setPlainText("لطفاً بررسی را ادامه بده.\nPlease continue the review.")
        window.show()
        for theme in ("dark", "light"):
            window._apply_theme(theme)
            for _ in range(20):
                app.processEvents()
            window.grab().save(str(output / f"chat-{theme}.png"))
        window.close()
        app.processEvents()
print(output)
