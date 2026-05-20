"""Analytics page — aggregated statistics."""
from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ...db.base import get_db
from ...db.repository import AnalyticsRepository, ChannelRepository, SessionRepository
from ...utils.time_utils import fmt_bitrate, fmt_duration
from ..widgets import Card, MetricCard, SparklineChart
from .base_page import BasePage


class AnalyticsPage(BasePage):
    title = "Analytics"
    subtitle = "Cross-channel performance & history"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        cards_row = QHBoxLayout()
        self.total_hours = MetricCard("Total streaming", "0h", "lifetime", glow=True)
        self.avg_bitrate = MetricCard("Average bitrate", "0 kbps", "across sessions")
        self.avg_fps = MetricCard("Average FPS", "0", "across sessions")
        self.errors = MetricCard("Sessions with errors", "0", "lifetime")
        for c in (self.total_hours, self.avg_bitrate, self.avg_fps, self.errors):
            cards_row.addWidget(c)
        self.content_layout.addLayout(cards_row)

        body_row = QHBoxLayout()

        history_card = Card("Recent sessions")
        self.sessions_table = QTableWidget(0, 6)
        self.sessions_table.setHorizontalHeaderLabels(
            ["Channel", "Started", "Duration", "Avg bitrate", "Avg fps", "OK"]
        )
        self.sessions_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.sessions_table.verticalHeader().setVisible(False)
        self.sessions_table.setEditTriggers(QTableWidget.NoEditTriggers)
        history_card.content_layout.addWidget(self.sessions_table)
        body_row.addWidget(history_card, 3)

        side = QVBoxLayout()
        chart_card = Card("Bitrate (last 60 samples)")
        self.chart = SparklineChart(capacity=60, color="#5E9DFF", title="Bitrate kbps")
        chart_card.content_layout.addWidget(self.chart)
        side.addWidget(chart_card)
        recent_card = Card("Recent events")
        self.events_table = QTableWidget(0, 3)
        self.events_table.setHorizontalHeaderLabels(["When", "Event", "Channel"])
        self.events_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.events_table.verticalHeader().setVisible(False)
        self.events_table.setEditTriggers(QTableWidget.NoEditTriggers)
        recent_card.content_layout.addWidget(self.events_table)
        side.addWidget(recent_card)
        body_row.addLayout(side, 2)
        self.content_layout.addLayout(body_row)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._reload)
        self._timer.setInterval(5000)
        self._reload()

    def on_show(self) -> None:
        super().on_show()
        self._timer.start()
        self._reload()

    def on_hide(self) -> None:
        super().on_hide()
        self._timer.stop()

    def _reload(self) -> None:
        sessions_repo = SessionRepository(get_db())
        analytics_repo = AnalyticsRepository(get_db())
        agg = sessions_repo.aggregate()
        self.total_hours.set_value(f"{agg['total_seconds'] / 3600:.1f}h", "lifetime")
        self.avg_bitrate.set_value(fmt_bitrate(agg["average_bitrate"]), "across sessions")
        self.avg_fps.set_value(f"{agg['average_fps']:.1f}", "across sessions")
        self.errors.set_value(str(agg["errors"]), "lifetime")

        channels = {c.id: c.name for c in ChannelRepository(get_db()).list()}
        sessions = sessions_repo.recent(80)
        self.sessions_table.setRowCount(len(sessions))
        bitrates: list[float] = []
        for row, s in enumerate(sessions):
            self.sessions_table.setItem(row, 0, QTableWidgetItem(channels.get(s.channel_id, f"#{s.channel_id}")))
            self.sessions_table.setItem(row, 1, QTableWidgetItem(s.started_at.isoformat()))
            self.sessions_table.setItem(row, 2, QTableWidgetItem(fmt_duration(s.duration_sec)))
            self.sessions_table.setItem(row, 3, QTableWidgetItem(fmt_bitrate(s.average_bitrate_kbps)))
            self.sessions_table.setItem(row, 4, QTableWidgetItem(f"{s.average_fps:.1f}"))
            self.sessions_table.setItem(row, 5, QTableWidgetItem("Yes" if s.finished_ok else "No"))
            bitrates.append(s.average_bitrate_kbps)
        if bitrates:
            self.chart.set_values(reversed(bitrates))

        events = analytics_repo.recent(50)
        self.events_table.setRowCount(len(events))
        for row, e in enumerate(events):
            self.events_table.setItem(row, 0, QTableWidgetItem(e.ts.isoformat()))
            self.events_table.setItem(row, 1, QTableWidgetItem(e.event))
            self.events_table.setItem(row, 2, QTableWidgetItem(channels.get(e.channel_id, "—")))
