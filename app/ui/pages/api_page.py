"""API Manager — YouTube OAuth + AI provider config."""
from __future__ import annotations

import threading

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
)

from ...core.config import get_config
from ...core.paths import paths
from ...security.credentials import get_credentials
from ...services import get_ai, get_notifier, get_youtube
from ..widgets import Card, MetricCard
from .base_page import BasePage


class ApiManagerPage(BasePage):
    title = "API Manager"
    subtitle = "YouTube OAuth, AI provider, third-party endpoints"

    authResult = Signal(bool, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        cfg = get_config().config

        status_row = QHBoxLayout()
        self.youtube_card = MetricCard(
            "YouTube",
            "Authorized" if get_youtube().is_authorized else "Not authorized",
            "OAuth status",
            glow=True,
        )
        self.ai_card = MetricCard(
            "AI provider", "Enabled" if get_ai().enabled else "Disabled", cfg.ai.model
        )
        status_row.addWidget(self.youtube_card)
        status_row.addWidget(self.ai_card)
        self.content_layout.addLayout(status_row)

        yt_card = Card("YouTube Live", subtitle="OAuth + default live event behaviour")
        yt_form = QFormLayout()
        self.enable_yt = QCheckBox("Enable YouTube integration")
        self.enable_yt.setChecked(cfg.youtube.enabled)
        self.client_secret_path = QLineEdit(cfg.youtube.client_secret_path)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._pick_client_secret)
        row = QHBoxLayout()
        row.addWidget(self.client_secret_path, 1)
        row.addWidget(browse)
        path_wrap = QPushButton()  # placeholder
        path_wrap.setVisible(False)
        self.privacy = QComboBox()
        self.privacy.addItems(["public", "unlisted", "private"])
        self.privacy.setCurrentText(cfg.youtube.default_privacy)
        self.latency = QComboBox()
        self.latency.addItems(["normal", "low", "ultraLow"])
        self.latency.setCurrentText(cfg.youtube.latency_preference)
        self.enable_dvr = QCheckBox("Enable DVR")
        self.enable_dvr.setChecked(cfg.youtube.enable_dvr)
        yt_form.addRow(self.enable_yt)
        yt_form.addRow("client_secret.json", row)
        yt_form.addRow("Default privacy", self.privacy)
        yt_form.addRow("Latency", self.latency)
        yt_form.addRow(self.enable_dvr)
        yt_card.content_layout.addLayout(yt_form)
        yt_buttons = QHBoxLayout()
        self.auth_btn = QPushButton("Authorize via browser")
        self.auth_btn.setObjectName("primary")
        self.revoke_btn = QPushButton("Revoke")
        self.revoke_btn.setObjectName("danger")
        self.test_btn = QPushButton("Test connection")
        for b in (self.auth_btn, self.revoke_btn, self.test_btn):
            yt_buttons.addWidget(b)
        yt_buttons.addStretch()
        yt_card.content_layout.addLayout(yt_buttons)
        self.content_layout.addWidget(yt_card)

        ai_card = Card("AI service", subtitle="Used by title / description / thumbnail generators")
        ai_form = QFormLayout()
        self.enable_ai = QCheckBox("Enable AI features")
        self.enable_ai.setChecked(cfg.ai.enabled)
        self.api_base = QLineEdit(cfg.ai.api_base)
        self.model = QLineEdit(cfg.ai.model)
        self.api_key = QLineEdit("")
        self.api_key.setEchoMode(QLineEdit.Password)
        self.api_key.setPlaceholderText("API key (stored encrypted — leave blank to keep)")
        self.lang = QComboBox()
        self.lang.addItems(["en", "id", "ja", "ko", "es", "fr", "de"])
        self.lang.setCurrentText(cfg.ai.default_language)
        ai_form.addRow(self.enable_ai)
        ai_form.addRow("API base", self.api_base)
        ai_form.addRow("Model", self.model)
        ai_form.addRow("API key", self.api_key)
        ai_form.addRow("Default language", self.lang)
        ai_card.content_layout.addLayout(ai_form)
        self.save_btn = QPushButton("Save API settings")
        self.save_btn.setObjectName("primary")
        self.save_btn.clicked.connect(self._save)
        ai_card.content_layout.addWidget(self.save_btn)
        self.content_layout.addWidget(ai_card)

        self.auth_btn.clicked.connect(self._authorize)
        self.revoke_btn.clicked.connect(self._revoke)
        self.test_btn.clicked.connect(self._test)
        self.authResult.connect(self._on_auth_done)

    def _pick_client_secret(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select client_secret.json", str(paths.data_root), "JSON (*.json)")
        if path:
            self.client_secret_path.setText(path)

    def _save(self) -> None:
        get_config().update(
            youtube={
                "enabled": self.enable_yt.isChecked(),
                "client_secret_path": self.client_secret_path.text().strip(),
                "default_privacy": self.privacy.currentText(),
                "latency_preference": self.latency.currentText(),
                "enable_dvr": self.enable_dvr.isChecked(),
            },
            ai={
                "enabled": self.enable_ai.isChecked(),
                "api_base": self.api_base.text().strip(),
                "model": self.model.text().strip(),
                "default_language": self.lang.currentText(),
            },
        )
        key = self.api_key.text().strip()
        if key:
            get_credentials().set("openai_api_key", key)
            self.api_key.clear()
        get_notifier().notify("API Manager", "Settings saved", "success")
        self.youtube_card.set_value("Authorized" if get_youtube().is_authorized else "Not authorized", "")
        self.ai_card.set_value("Enabled" if get_ai().enabled else "Disabled", get_config().config.ai.model)

    def _authorize(self) -> None:
        path = self.client_secret_path.text().strip()
        if not path:
            QMessageBox.warning(self, "Missing client_secret", "Set the path to client_secret.json first.")
            return
        # Persist so authorize() picks it up
        self._save()
        self.auth_btn.setEnabled(False)
        self.auth_btn.setText("Opening browser…")

        def worker():
            try:
                get_youtube().authorize(force=True)
                self.authResult.emit(True, "YouTube authorized")
            except Exception as exc:  # noqa: BLE001
                self.authResult.emit(False, str(exc))

        threading.Thread(target=worker, name="yt-oauth", daemon=True).start()

    def _on_auth_done(self, ok: bool, message: str) -> None:
        self.auth_btn.setEnabled(True)
        self.auth_btn.setText("Authorize via browser")
        notifier = get_notifier()
        if ok:
            self.youtube_card.set_value("Authorized", "")
            notifier.notify("YouTube", message, "success")
        else:
            notifier.notify("YouTube", message, "error")

    def _revoke(self) -> None:
        get_youtube().revoke()
        self.youtube_card.set_value("Not authorized", "")
        get_notifier().notify("YouTube", "Credentials revoked", "info")

    def _test(self) -> None:
        try:
            broadcasts = get_youtube().list_active_broadcasts()
            QMessageBox.information(
                self,
                "YouTube",
                f"Connection ok — {len(broadcasts)} active broadcast(s) found.",
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "YouTube", str(exc))
