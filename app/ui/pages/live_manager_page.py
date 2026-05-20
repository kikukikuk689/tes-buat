"""Live Manager — control individual channels in real time."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...core.events import Topics, event_bus
from ...db.base import get_db
from ...db.repository import ChannelRepository
from ...services import get_notifier, get_stream_engine
from ...utils.time_utils import fmt_bitrate, fmt_duration
from ..widgets import StatusBadge
from .base_page import BasePage


class _ChannelCard(QFrame):
    def __init__(self, channel, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.channel_id = channel.id
        self.channel_name = channel.name

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 14, 18, 14)
        outer.setSpacing(8)

        head = QHBoxLayout()
        title = QLabel(channel.name)
        title.setStyleSheet("color: #FFFFFF; font-weight: 700; font-size: 16px;")
        self.badge = StatusBadge(channel.last_state.value if channel.last_state else "idle")
        platform = QLabel(channel.platform.upper())
        platform.setStyleSheet("color: #9D4DFF; font-weight: 700;")
        head.addWidget(title)
        head.addStretch()
        head.addWidget(platform)
        head.addWidget(self.badge)
        outer.addLayout(head)

        rtmp = QLabel(channel.rtmp_url)
        rtmp.setStyleSheet("color: #8A8AAE; font-size: 11px;")
        outer.addWidget(rtmp)

        stats_row = QHBoxLayout()
        self.fps_lbl = QLabel("FPS: 0")
        self.bitrate_lbl = QLabel("Bitrate: 0 kbps")
        self.uptime_lbl = QLabel("Uptime: 00:00")
        self.reconn_lbl = QLabel("↻ 0")
        for lbl in (self.fps_lbl, self.bitrate_lbl, self.uptime_lbl, self.reconn_lbl):
            lbl.setStyleSheet("color: #C5C5DC;")
            stats_row.addWidget(lbl)
        stats_row.addStretch()
        outer.addLayout(stats_row)

        btn_row = QHBoxLayout()
        self.start_btn = QPushButton("▶ Start")
        self.start_btn.setObjectName("primary")
        self.stop_btn = QPushButton("■ Stop")
        self.stop_btn.setObjectName("danger")
        self.restart_btn = QPushButton("↻ Restart")
        self.pause_btn = QPushButton("⏸ Pause")
        for b in (self.start_btn, self.stop_btn, self.restart_btn, self.pause_btn):
            btn_row.addWidget(b)
        btn_row.addStretch()
        outer.addLayout(btn_row)

        engine = get_stream_engine()
        self.start_btn.clicked.connect(lambda _: engine.start(self.channel_id))
        self.stop_btn.clicked.connect(lambda _: engine.stop(self.channel_id))
        self.restart_btn.clicked.connect(lambda _: engine.restart(self.channel_id))
        self.pause_btn.clicked.connect(lambda _: engine.pause(self.channel_id))

    def update_stats(self, stats) -> None:
        self.badge.set_state(stats.state.value)
        self.fps_lbl.setText(f"FPS: {stats.fps:.0f}")
        self.bitrate_lbl.setText(f"Bitrate: {fmt_bitrate(stats.bitrate_kbps)}")
        self.uptime_lbl.setText(f"Uptime: {fmt_duration(stats.uptime_sec)}")
        self.reconn_lbl.setText(f"↻ {stats.reconnects}")


class LiveManagerPage(BasePage):
    title = "Live Manager"
    subtitle = "Start, stop, and supervise every channel"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        toolbar = QHBoxLayout()
        self.start_all = QPushButton("▶  Start all enabled")
        self.start_all.setObjectName("success")
        self.start_all.clicked.connect(self._start_all)
        self.stop_all = QPushButton("■  Stop all")
        self.stop_all.setObjectName("danger")
        self.stop_all.clicked.connect(self._stop_all)
        toolbar.addWidget(self.start_all)
        toolbar.addWidget(self.stop_all)
        toolbar.addStretch()
        self.content_layout.addLayout(toolbar)

        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setHorizontalSpacing(16)
        self.grid.setVerticalSpacing(16)
        self.content_layout.addWidget(self.grid_host)

        self._cards: dict[int, _ChannelCard] = {}
        self._unsubs = [
            event_bus.subscribe(Topics.STREAM_STATS, lambda p: QTimer.singleShot(0, lambda: self._on_stats(p))),
            event_bus.subscribe(Topics.STREAM_STATE, lambda p: QTimer.singleShot(0, lambda: self._on_state(p))),
            event_bus.subscribe(Topics.CHANNEL_CHANGED, lambda p: QTimer.singleShot(0, lambda: self._rebuild())),
        ]
        self._rebuild()

    def on_show(self) -> None:
        super().on_show()
        self._rebuild()

    def _rebuild(self) -> None:
        # Clear grid
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._cards.clear()
        channels = ChannelRepository(get_db()).list()
        if not channels:
            empty = QLabel("Add a channel via the Multi Channel Manager to begin streaming.")
            empty.setStyleSheet("color: #6A6A8A;")
            self.grid.addWidget(empty, 0, 0)
            return
        for i, ch in enumerate(channels):
            card = _ChannelCard(ch)
            card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.grid.addWidget(card, i // 2, i % 2)
            self._cards[ch.id] = card

    def _on_stats(self, payload: dict) -> None:
        cid = payload.get("channel_id")
        card = self._cards.get(cid)
        if card and get_stream_engine().is_running(cid):
            card.update_stats(get_stream_engine().runtime(cid).stats)

    def _on_state(self, payload: dict) -> None:
        cid = payload.get("channel_id")
        card = self._cards.get(cid)
        if card:
            card.badge.set_state(payload.get("state", "idle"))

    def _start_all(self) -> None:
        count = get_stream_engine().start_all_enabled()
        get_notifier().notify("Streaming", f"Started {count} channel(s)", "success")

    def _stop_all(self) -> None:
        get_stream_engine().stop_all()
        get_notifier().notify("Streaming", "All streams stopped", "info")
