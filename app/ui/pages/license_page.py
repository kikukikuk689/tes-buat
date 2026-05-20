"""License Manager — install + activate licenses."""
from __future__ import annotations

import threading

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
)

from ...core.config import get_config
from ...security import get_license_manager
from ..widgets import Card, MetricCard
from .base_page import BasePage


class LicensePage(BasePage):
    title = "License Manager"
    subtitle = "Trial, activation, device binding"

    licenseResult = Signal(bool, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        mgr = get_license_manager()
        status = mgr.status()

        cards = QHBoxLayout()
        self.status_card = MetricCard("Status", status.status.value.upper(), status.message or "", glow=True)
        self.expires_card = MetricCard("Expires", status.expires_at or "—", f"{status.days_remaining} day(s) left")
        self.device_card = MetricCard("Device id", mgr.device_id, "stored locally")
        for c in (self.status_card, self.expires_card, self.device_card):
            cards.addWidget(c)
        self.content_layout.addLayout(cards)

        install_card = Card("Install license", subtitle="Paste a signed license blob")
        form = QFormLayout()
        self.license_blob = QTextEdit()
        self.license_blob.setPlaceholderText("Base64-encoded license blob…")
        self.license_blob.setFixedHeight(120)
        form.addRow(self.license_blob)
        install_card.content_layout.addLayout(form)
        install_row = QHBoxLayout()
        self.install_btn = QPushButton("Install license")
        self.install_btn.setObjectName("primary")
        self.install_btn.clicked.connect(self._install)
        self.remove_btn = QPushButton("Remove license")
        self.remove_btn.setObjectName("danger")
        self.remove_btn.clicked.connect(self._remove)
        install_row.addWidget(self.install_btn)
        install_row.addWidget(self.remove_btn)
        install_row.addStretch()
        install_card.content_layout.addLayout(install_row)
        self.content_layout.addWidget(install_card)

        cfg = get_config().config.licensing
        online_card = Card("Online activation", subtitle="POSTs {key,email,device_id} to your activation endpoint")
        online_form = QFormLayout()
        self.activation_url = QLineEdit(cfg.activation_url)
        self.key = QLineEdit()
        self.key.setPlaceholderText("License key")
        self.email = QLineEdit()
        self.email.setPlaceholderText("E-mail (optional)")
        self.trial_days = QSpinBox()
        self.trial_days.setRange(1, 365)
        self.trial_days.setValue(cfg.trial_days)
        self.trial_days.setSuffix(" days trial")
        online_form.addRow("Activation URL", self.activation_url)
        online_form.addRow("Key", self.key)
        online_form.addRow("Email", self.email)
        online_form.addRow("Trial length", self.trial_days)
        online_card.content_layout.addLayout(online_form)
        row = QHBoxLayout()
        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self._save_url)
        self.activate_btn = QPushButton("Activate online")
        self.activate_btn.setObjectName("primary")
        self.activate_btn.clicked.connect(self._activate)
        row.addWidget(self.save_btn)
        row.addWidget(self.activate_btn)
        row.addStretch()
        online_card.content_layout.addLayout(row)
        self.content_layout.addWidget(online_card)

        self.licenseResult.connect(self._on_result)

    def _refresh(self) -> None:
        mgr = get_license_manager()
        status = mgr.status()
        self.status_card.set_value(status.status.value.upper(), status.message or "")
        self.expires_card.set_value(status.expires_at or "—", f"{status.days_remaining} day(s) left")

    def _save_url(self) -> None:
        get_config().update(
            licensing={
                "activation_url": self.activation_url.text().strip(),
                "trial_days": int(self.trial_days.value()),
            }
        )
        QMessageBox.information(self, "Saved", "License preferences saved.")

    def _install(self) -> None:
        blob = self.license_blob.toPlainText().strip()
        if not blob:
            return
        try:
            get_license_manager().install_license_text(blob)
            self._refresh()
            QMessageBox.information(self, "License", "License installed.")
            self.license_blob.clear()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "License", str(exc))

    def _remove(self) -> None:
        get_license_manager().deactivate()
        self._refresh()

    def _activate(self) -> None:
        self._save_url()
        key = self.key.text().strip()
        email = self.email.text().strip()
        if not key:
            QMessageBox.warning(self, "License", "Enter a license key first.")
            return
        self.activate_btn.setEnabled(False)

        def worker():
            try:
                get_license_manager().activate_online(key=key, email=email)
                self.licenseResult.emit(True, "License activated.")
            except Exception as exc:  # noqa: BLE001
                self.licenseResult.emit(False, str(exc))

        threading.Thread(target=worker, name="license-activate", daemon=True).start()

    def _on_result(self, ok: bool, message: str) -> None:
        self.activate_btn.setEnabled(True)
        if ok:
            QMessageBox.information(self, "License", message)
        else:
            QMessageBox.critical(self, "License", message)
        self._refresh()
