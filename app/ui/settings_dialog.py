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
        self.setMinimumSize(680, 560)

        self.config = config
        self.permissions = permissions

        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self._build_provider_tab(), "Provider")
        tabs.addTab(self._build_gapgpt_tab(), "GapGPT")
        tabs.addTab(self._build_deepseek_tab(), "DeepSeek")
        tabs.addTab(self._build_ai_tab(), "AI")
        tabs.addTab(self._build_permissions_tab(), "Permissions")
        tabs.addTab(self._build_appearance_tab(), "Appearance")
        layout.addWidget(tabs)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------ #
    def _build_provider_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)

        self.provider_combo = QComboBox()
        self.provider_combo.addItems(["gapgpt", "deepseek"])
        self.provider_combo.setCurrentText(self.config.provider)
        form.addRow("Active provider:", self.provider_combo)

        hint = QLabel(
            "GapGPT is an OpenAI-compatible proxy. It speaks the same protocol "
            "as the OpenAI SDK, so the agent works with it unchanged."
        )
        hint.setWordWrap(True)
        hint.setObjectName("Sub")
        form.addRow(hint)

        return w

    def _build_gapgpt_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)

        self.gap_key_edit = QLineEdit(self.config.gapgpt_api_key)
        self.gap_key_edit.setEchoMode(QLineEdit.Password)
        self.gap_key_edit.setPlaceholderText("your GapGPT key")
        form.addRow("GapGPT API Key:", self.gap_key_edit)

        self.gap_url_edit = QLineEdit(self.config.gapgpt_base_url)
        form.addRow("Base URL:", self.gap_url_edit)

        self.gap_model_edit = QLineEdit(self.config.gapgpt_model)
        self.gap_model_edit.setPlaceholderText("gpt-4o, gpt-4o-mini, ...")
        form.addRow("Model:", self.gap_model_edit)

        self.gap_conn_label = QLabel("Connection: not tested")
        self.gap_conn_label.setObjectName("Sub")
        form.addRow("", self.gap_conn_label)

        test_btn = QPushButton("Test GapGPT Connection")
        test_btn.clicked.connect(self._test_gapgpt)
        form.addRow("", test_btn)

        return w

    def _build_deepseek_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)

        self.ds_key_edit = QLineEdit(self.config.deepseek_api_key)
        self.ds_key_edit.setEchoMode(QLineEdit.Password)
        self.ds_key_edit.setPlaceholderText("sk-...")
        form.addRow("DeepSeek API Key:", self.ds_key_edit)

        self.ds_url_edit = QLineEdit(self.config.deepseek_base_url)
        form.addRow("Base URL:", self.ds_url_edit)

        self.ds_model_edit = QLineEdit(self.config.deepseek_model)
        form.addRow("Model:", self.ds_model_edit)

        self.ds_conn_label = QLabel("Connection: not tested")
        self.ds_conn_label.setObjectName("Sub")
        form.addRow("", self.ds_conn_label)

        test_btn = QPushButton("Test DeepSeek Connection")
        test_btn.clicked.connect(self._test_deepseek)
        form.addRow("", test_btn)

        return w

    def _build_ai_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)

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

    def _test_gapgpt(self) -> None:
        from app.providers import GapGPTProvider

        provider = GapGPTProvider(
            api_key=self.gap_key_edit.text().strip(),
            model=self.gap_model_edit.text().strip() or "gpt-4o",
            base_url=self.gap_url_edit.text().strip() or "https://api.gapgpt.app/v1",
        )
        ok, msg = provider.test_connection()
        self._set_conn_label(self.gap_conn_label, ok, msg)

    def _test_deepseek(self) -> None:
        from app.providers import DeepSeekProvider

        provider = DeepSeekProvider(
            api_key=self.ds_key_edit.text().strip(),
            model=self.ds_model_edit.text().strip() or "deepseek-chat",
            base_url=self.ds_url_edit.text().strip() or "https://api.deepseek.com",
        )
        ok, msg = provider.test_connection()
        self._set_conn_label(self.ds_conn_label, ok, msg)

    @staticmethod
    def _set_conn_label(label: QLabel, ok: bool, msg: str) -> None:
        if ok:
            label.setText(f"Connection: ● {msg}")
            label.setStyleSheet("color:#4ade80;font-weight:600;")
        else:
            label.setText(f"Connection: ● {msg}")
            label.setStyleSheet("color:#f87171;font-weight:600;")

    # ------------------------------------------------------------------ #
    def _save(self) -> None:
        self.config.provider = self.provider_combo.currentText()

        self.config.gapgpt_api_key = self.gap_key_edit.text().strip()
        self.config.gapgpt_base_url = (
            self.gap_url_edit.text().strip() or "https://api.gapgpt.app/v1"
        )
        self.config.gapgpt_model = self.gap_model_edit.text().strip() or "gpt-4o"

        self.config.deepseek_api_key = self.ds_key_edit.text().strip()
        self.config.deepseek_base_url = (
            self.ds_url_edit.text().strip() or "https://api.deepseek.com"
        )
        self.config.deepseek_model = (
            self.ds_model_edit.text().strip() or "deepseek-chat"
        )

        self.config.temperature = float(self.temp.value())
        self.config.max_tokens = int(self.max_tokens.value())
        self.config.streaming = self.streaming_cb.isChecked()
        self.config.edit_mode = self.edit_mode.currentText()
        self.config.theme = self.theme_combo.currentText()
        self.config.save()

        self.config_saved.emit(self.config)
        self.accept()
