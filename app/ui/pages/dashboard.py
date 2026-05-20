"""Dashboard – real-time overview of the broadcasting engine."""
from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
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
from ...db.repository import ChannelRepository, SessionRepository
from ...services import get_notifier, get_stream_engine
from ...utils.time_utils import fmt_bitrate, fmt_duration
from ..widgets import MetricCard, SparklineChart, StatusBadge
from .base_page import BasePage


class DashboardPage(BasePage):
    title = "Dashboard"
    subtitle = "Live broadcasting overview"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.cpu_card = MetricCard("CPU", "0%", "load (1.5s sample)", glow=True)
        self.ram_card = MetricCard("RAM", "0 MB", "used")
        self.gpu_card = MetricCard("GPU", "n/a", "utilisation")
        self.net_card = MetricCard("Network", "0 kbps", "upload")
        self.live_card = MetricCard("Live", "0", "active channels", glow=True)
        self.uptime_card = MetricCard("Uptime", "00:00", "since boot")

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(16)
        for i, w in enumerate(
            (self.cpu_card, self.ram_card, self.gpu_card, self.net_card, self.live_card, self.uptime_card)
        ):
            grid.addWidget(w, i // 3, i % 3)
            w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.content_layout.addLayout(grid)

        # Charts row
        chart_row = QHBoxLayout()
        chart_row.setSpacing(16)
        self.cpu_chart = SparklineChart(capacity=60, color="#9D4DFF", title="CPU usage")
        self.net_chart = SparklineChart(capacity=60, color="#5E9DFF", title="Upload kbps", min_y=None)
        self.bitrate_chart = SparklineChart(capacity=60, color="#2AD27D", title="Streaming bitrate kbps")
        for ch in (self.cpu_chart, self.net_chart, self.bitrate_chart):
            ch.setMinimumHeight(120)
            chart_row.addWidget(ch, 1)
        self.content_layout.addLayout(chart_row)

        # Channel summary list
        summary = QWidget()
        s_layout = QVBoxLayout(summary)
        s_layout.setContentsMargins(0, 0, 0, 0)
        s_layout.setSpacing(6)
        header = QLabel("Active channels")
        header.setStyleSheet("color: #FFFFFF; font-weight: 700; font-size: 14px;")
        s_layout.addWidget(header)
        self.channels_panel = QVBoxLayout()
        s_layout.addLayout(self.channels_panel)
        self.content_layout.addWidget(summary)

        # Quick actions
        actions = QHBoxLayout()
        self.start_all_btn = QPushButton("▶  Start all enabled channels")
        self.start_all_btn.setObjectName("primary")
        self.start_all_btn.clicked.connect(self._start_all)
        self.stop_all_btn = QPushButton("■  Stop all streams")
        self.stop_all_btn.setObjectName("danger")
        self.stop_all_btn.clicked.connect(self._stop_all)
        actions.addWidget(self.start_all_btn)
        actions.addWidget(self.stop_all_btn)
        actions.addStretch()
        self.content_layout.addLayout(actions)

        # Subscriptions
        self._unsubs = [
            event_bus.subscribe(Topics.SYSTEM_STATS, lambda p: QTimer.singleShot(0, lambda: self._on_system_stats(p))),
            event_bus.subscribe(Topics.STREAM_STATS, lambda p: QTimer.singleShot(0, lambda: self._on_stream_stats(p))),
            event_bus.subscribe(Topics.STREAM_STATE, lambda p: QTimer.singleShot(0, lambda: self._refresh_channels())),
            event_bus.subscribe(Topics.NETWORK_STATE, lambda p: QTimer.singleShot(0, lambda: self._on_network(p))),
        ]
        self._latest_stream_bitrate = 0.0
        self._refresh_channels()

    # ------------------------------------------------------------------
    def on_refresh_tick(self) -> None:
        engine = get_stream_engine()
        snap = engine.snapshot()
        active = sum(1 for s in snap.values() if s.is_active)
        self.live_card.set_value(str(active), f"of {len(ChannelRepository(get_db()).list())} channels")
        total_uptime = SessionRepository(get_db()).aggregate().get("total_seconds", 0)
        self.uptime_card.set_value(fmt_duration(total_uptime), "lifetime")
        self._refresh_channels()

    def _on_system_stats(self, payload: dict) -> None:
        cpu = payload.get("cpu_percent", 0.0)
        self.cpu_card.set_value(f"{cpu:.1f}%", "1.5s sample")
        self.cpu_chart.set_values(payload.get("history_cpu", []))
        self.net_chart.set_values(payload.get("history_net_up", []))
        ram_used = payload.get("ram_used_mb", 0)
        ram_total = payload.get("ram_total_mb", 1)
        self.ram_card.set_value(f"{ram_used:.0f} MB", f"of {ram_total:.0f} MB ({payload.get('ram_percent', 0):.0f}%)")
        gpu = payload.get("gpu_percent")
        if gpu is None:
            self.gpu_card.set_value("n/a", "no NVIDIA driver detected")
        else:
            self.gpu_card.set_value(f"{gpu:.0f}%", "GPU utilisation")
        self.net_card.set_value(
            f"↑ {payload.get('net_up_kbps', 0):.0f} kbps",
            f"↓ {payload.get('net_down_kbps', 0):.0f} kbps",
        )

    def _on_stream_stats(self, payload: dict) -> None:
        bitrate = float(payload.get("bitrate_kbps") or 0)
        self._latest_stream_bitrate = bitrate
        self.bitrate_chart.push(bitrate)

    def _on_network(self, payload: dict) -> None:
        if payload.get("silent"):
            return
        if not payload.get("online"):
            self.net_card.set_value("OFFLINE", "internet check failed")

    # ------------------------------------------------------------------
    def _refresh_channels(self) -> None:
        while self.channels_panel.count():
            item = self.channels_panel.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        engine = get_stream_engine()
        repo = ChannelRepository(get_db())
        channels = repo.list()
        if not channels:
            empty = QLabel("No channels configured yet. Go to Multi Channel Manager to add one.")
            empty.setStyleSheet("color: #6A6A8A; padding: 8px;")
            self.channels_panel.addWidget(empty)
            return
        for ch in channels:
            row = QHBoxLayout()
            badge = StatusBadge(ch.last_state.value if not engine.is_running(ch.id) else engine.runtime(ch.id).stats.state.value)
            name = QLabel(ch.name)
            name.setStyleSheet("color: #FFFFFF; font-weight: 600;")
            platform = QLabel(ch.platform.upper())
            platform.setStyleSheet("color: #8A8AAE; font-size: 11px;")
            stats_label = QLabel("")
            stats_label.setStyleSheet("color: #C8C8E4;")
            if engine.is_running(ch.id):
                s = engine.runtime(ch.id).stats
                stats_label.setText(
                    f"{fmt_bitrate(s.bitrate_kbps)}   |   {s.fps:.0f} fps   |   ↻ {s.reconnects}   |   ⏱ {fmt_duration(s.uptime_sec)}"
                )
            row.addWidget(badge)
            row.addWidget(name)
            row.addWidget(platform)
            row.addStretch()
            row.addWidget(stats_label)
            wrap = QWidget()
            wrap.setLayout(row)
            wrap.setStyleSheet(
                "background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.05); "
                "border-radius: 10px; padding: 8px 14px;"
            )
            self.channels_panel.addWidget(wrap)

    # ------------------------------------------------------------------
    def _start_all(self) -> None:
        count = get_stream_engine().start_all_enabled()
        get_notifier().notify("Streaming", f"Started {count} channel(s)", "success")

    def _stop_all(self) -> None:
        get_stream_engine().stop_all()
        get_notifier().notify("Streaming", "All streams stopped", "info")
