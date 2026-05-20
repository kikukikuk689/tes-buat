"""Remote Control page — toggle the embedded FastAPI server."""
from __future__ import annotations

import secrets
import socket

from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
)

from ...core.config import get_config
from ...services import get_notifier, get_remote_server
from ..widgets import Card, MetricCard
from .base_page import BasePage


def _local_ip() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(1)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except OSError:
        return "127.0.0.1"


class RemotePage(BasePage):
    title = "Remote Control"
    subtitle = "Web dashboard + WebSocket realtime API"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        cfg = get_config().config.remote

        ip = _local_ip()
        status_row = QHBoxLayout()
        self.state_card = MetricCard(
            "Server",
            "Running" if get_remote_server().running else "Stopped",
            "FastAPI + WebSocket",
            glow=True,
        )
        self.url_card = MetricCard("URL", f"http://{ip}:{cfg.port}", "open in your browser")
        self.token_card = MetricCard("Auth token", "Set" if cfg.auth_token else "Open", "X-Auth-Token header")
        for c in (self.state_card, self.url_card, self.token_card):
            status_row.addWidget(c)
        self.content_layout.addLayout(status_row)

        card = Card("Configuration", glow=True)
        form = QFormLayout()
        self.enabled = QCheckBox("Enable remote control")
        self.enabled.setChecked(cfg.enabled)
        self.host = QLineEdit(cfg.host)
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(cfg.port)
        self.token = QLineEdit(cfg.auth_token)
        self.token.setEchoMode(QLineEdit.Password)
        self.regen_btn = QPushButton("Generate token")
        self.regen_btn.clicked.connect(self._regen)
        token_row = QHBoxLayout()
        token_row.addWidget(self.token, 1)
        token_row.addWidget(self.regen_btn)
        form.addRow(self.enabled)
        form.addRow("Bind host", self.host)
        form.addRow("Port", self.port)
        form.addRow("Auth token", token_row)
        card.content_layout.addLayout(form)

        button_row = QHBoxLayout()
        self.save_btn = QPushButton("Save")
        self.save_btn.setObjectName("primary")
        self.save_btn.clicked.connect(self._save)
        self.start_btn = QPushButton("Start server")
        self.stop_btn = QPushButton("Stop server")
        self.stop_btn.setObjectName("danger")
        self.start_btn.clicked.connect(self._start)
        self.stop_btn.clicked.connect(self._stop)
        button_row.addWidget(self.save_btn)
        button_row.addWidget(self.start_btn)
        button_row.addWidget(self.stop_btn)
        button_row.addStretch()
        card.content_layout.addLayout(button_row)
        self.content_layout.addWidget(card)

        info = QLabel(
            "Endpoints:  GET /api/status   POST /api/channels/{id}/start|stop|restart   "
            "WS /ws (push)\nHeader:  X-Auth-Token: <token>"
        )
        info.setStyleSheet("color: #8A8AAE;")
        info.setWordWrap(True)
        self.content_layout.addWidget(info)

    def _save(self) -> None:
        get_config().update(
            remote={
                "enabled": self.enabled.isChecked(),
                "host": self.host.text().strip(),
                "port": int(self.port.value()),
                "auth_token": self.token.text().strip(),
            }
        )
        ip = _local_ip()
        self.url_card.set_value(f"http://{ip}:{self.port.value()}", "open in your browser")
        self.token_card.set_value("Set" if self.token.text().strip() else "Open", "")
        get_notifier().notify("Remote", "Settings saved", "success")

    def _start(self) -> None:
        self._save()
        try:
            get_remote_server().start()
            self.state_card.set_value("Running", "FastAPI + WebSocket")
            get_notifier().notify("Remote", "Server started", "success")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Remote", str(exc))

    def _stop(self) -> None:
        get_remote_server().stop()
        self.state_card.set_value("Stopped", "FastAPI + WebSocket")
        get_notifier().notify("Remote", "Server stopped", "info")

    def _regen(self) -> None:
        self.token.setText(secrets.token_urlsafe(24))
