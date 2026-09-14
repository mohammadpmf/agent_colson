"""Settings dialog with AI / API / Permissions / Appearance tabs."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.config import AppConfig
from app.permissions import PermissionManager


class SettingsDialog(QDialog):
    """Edits a copy of AppConfig and exposes permission reset."""

    config_saved = Signal(AppConfig)

    def __init__(
        self,
        config: AppConfig,
        permissions: PermissionManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setMinimumSize(640, 520)

        self.config = config
        self.permissions = permissions

        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self._build_ai_tab(), "AI")
        tabs.addTab(self._build_api_tab(), "API")
        tabs.addTab(self._build_permissions_tab(), "Permissions")
        tabs.addTab(self._build_appearance_tab(), "Appearance")
        layout.addWidget(tabs)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------ #
    def _build_ai_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)

        self.model_edit = QLineEdit(self.config.model)
        form.addRow("Model:", self.model_edit)

        self.temp = QDoubleSpinBox()
        self.temp.setRange(0.0, 2.0)
        self.temp.setSingleStep(0.1)
        self.temp.setValue(self.config.temperature)
        form.addRow("Temperature:", self.temp)

        self.max_tokens = QSpinBox()
        self.max_tokens.setRange(256, 128_000)
        self.max_tokens.setValue(self.config.max_tokens)
        form.addRow("Max tokens:", self.max_tokens)

        self.streaming_cb = QCheckBox("Stream responses")
        self.streaming_cb.setChecked(self.config.streaming)
        form.addRow("", self.streaming_cb)

        self.edit_mode = QComboBox()
        self.edit_mode.addItems(["ask", "ask_first", "auto"])
        self.edit_mode.setCurrentText(self.config.edit_mode)
        form.addRow("File edit mode:", self.edit_mode)

        return w

    def _build_api_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)

        self.api_key_edit = QLineEdit(self.config.api_key)
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.api_key_edit.setPlaceholderText("sk-...")
        form.addRow("DeepSeek API Key:", self.api_key_edit)

        self.base_url_edit = QLineEdit(self.config.base_url)
        form.addRow("Base URL:", self.base_url_edit)

        self.conn_label = QLabel("Connection: not tested")
        self.conn_label.setObjectName("Sub")
        form.addRow("", self.conn_label)

        test_btn = QPushButton("Test Connection")
        test_btn.clicked.connect(self._test_connection)
        form.addRow("", test_btn)

        return w

    def _build_permissions_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        info = QLabel(
            "Active `always allow` rules. Click 'Reset' to forget all of them."
        )
        info.setObjectName("Sub")
        info.setWordWrap(True)
        layout.addWidget(info)

        self.rules_list = QListWidget()
        self._reload_rules()
        layout.addWidget(self.rules_list, stretch=1)

        row = QHBoxLayout()
        row.addStretch(1)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self._reload_rules)
        reset = QPushButton("Reset All")
        reset.setObjectName("Danger")
        reset.clicked.connect(self._reset_rules)
        row.addWidget(refresh)
        row.addWidget(reset)
        layout.addLayout(row)

        return w

    def _build_appearance_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["dark", "light"])
        self.theme_combo.setCurrentText(self.config.theme)
        form.addRow("Theme:", self.theme_combo)

        return w

    # ------------------------------------------------------------------ #
    def _reload_rules(self) -> None:
        self.rules_list.clear()
        rules = self.permissions.list_rules()
        if not rules:
            item = QListWidgetItem("(no rules — you'll always be asked)")
            item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
            self.rules_list.addItem(item)
            return
        for r in rules:
            text = f"{r.action.value}  ·  {r.scope.value}  ·  {r.target}"
            self.rules_list.addItem(QListWidgetItem(text))

    def _reset_rules(self) -> None:
        self.permissions.reset_rules()
        self._reload_rules()

    def _test_connection(self) -> None:
        from app.providers import DeepSeekProvider

        provider = DeepSeekProvider(
            api_key=self.api_key_edit.text().strip(),
            model=self.model_edit.text().strip() or "deepseek-chat",
            base_url=self.base_url_edit.text().strip() or "https://api.deepseek.com",
        )
        ok, msg = provider.test_connection()
        if ok:
            self.conn_label.setText(f"Connection: ● {msg}")
            self.conn_label.setStyleSheet("color:#4ade80;font-weight:600;")
        else:
            self.conn_label.setText(f"Connection: ● {msg}")
            self.conn_label.setStyleSheet("color:#f87171;font-weight:600;")

    # ------------------------------------------------------------------ #
    def _save(self) -> None:
        self.config.api_key = self.api_key_edit.text().strip()
        self.config.model = self.model_edit.text().strip() or "deepseek-chat"
        self.config.base_url = (
            self.base_url_edit.text().strip() or "https://api.deepseek.com"
        )
        self.config.temperature = float(self.temp.value())
        self.config.max_tokens = int(self.max_tokens.value())
        self.config.streaming = self.streaming_cb.isChecked()
        self.config.edit_mode = self.edit_mode.currentText()
        self.config.theme = self.theme_combo.currentText()
        self.config.save()

        self.config_saved.emit(self.config)
        self.accept()
