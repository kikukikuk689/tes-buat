"""Repository facades over the ORM models.

The repository layer keeps SQLAlchemy out of the service / UI code so
the rest of the app deals in plain domain objects.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta

from sqlalchemy import desc, select

from .base import Database
from .models import (
    AnalyticsEvent,
    Channel,
    ChannelState,
    LogEntry,
    Playlist,
    PlaylistItem,
    Schedule,
    Setting,
    StreamSession,
)


class _BaseRepo:
    def __init__(self, db: Database) -> None:
        self.db = db


class ChannelRepository(_BaseRepo):
    def list(self) -> list[Channel]:
        with self.db.session() as s:
            return list(s.scalars(select(Channel).order_by(Channel.name)).all())

    def get(self, channel_id: int) -> Channel | None:
        with self.db.session() as s:
            return s.get(Channel, channel_id)

    def get_by_name(self, name: str) -> Channel | None:
        with self.db.session() as s:
            return s.scalar(select(Channel).where(Channel.name == name))

    def create(self, **fields) -> Channel:
        with self.db.session() as s:
            ch = Channel(**fields)
            s.add(ch)
            s.flush()
            s.refresh(ch)
            return ch

    def update(self, channel_id: int, **fields) -> Channel:
        with self.db.session() as s:
            ch = s.get(Channel, channel_id)
            if ch is None:
                raise KeyError(channel_id)
            for k, v in fields.items():
                setattr(ch, k, v)
            s.flush()
            s.refresh(ch)
            return ch

    def delete(self, channel_id: int) -> None:
        with self.db.session() as s:
            ch = s.get(Channel, channel_id)
            if ch is not None:
                s.delete(ch)

    def set_state(self, channel_id: int, state: ChannelState, error: str = "") -> None:
        with self.db.session() as s:
            ch = s.get(Channel, channel_id)
            if ch is None:
                return
            ch.last_state = state
            if error:
                ch.last_error = error


class PlaylistRepository(_BaseRepo):
    def list(self) -> list[Playlist]:
        with self.db.session() as s:
            return list(s.scalars(select(Playlist).order_by(Playlist.name)).all())

    def get(self, pid: int) -> Playlist | None:
        with self.db.session() as s:
            return s.get(Playlist, pid)

    def create(self, name: str, **fields) -> Playlist:
        with self.db.session() as s:
            pl = Playlist(name=name, **fields)
            s.add(pl)
            s.flush()
            s.refresh(pl)
            return pl

    def update(self, pid: int, **fields) -> Playlist:
        with self.db.session() as s:
            pl = s.get(Playlist, pid)
            if pl is None:
                raise KeyError(pid)
            for k, v in fields.items():
                setattr(pl, k, v)
            s.flush()
            s.refresh(pl)
            return pl

    def delete(self, pid: int) -> None:
        with self.db.session() as s:
            pl = s.get(Playlist, pid)
            if pl is not None:
                s.delete(pl)

    def add_items(self, pid: int, items: Iterable[dict]) -> None:
        with self.db.session() as s:
            pl = s.get(Playlist, pid)
            if pl is None:
                raise KeyError(pid)
            existing = {it.path for it in pl.items}
            position = max((it.position for it in pl.items), default=-1) + 1
            for it in items:
                if it["path"] in existing:
                    continue
                pl.items.append(
                    PlaylistItem(
                        path=it["path"],
                        title=it.get("title", ""),
                        duration_sec=float(it.get("duration_sec", 0.0)),
                        position=position,
                    )
                )
                position += 1

    def replace_items(self, pid: int, items: list[dict]) -> None:
        with self.db.session() as s:
            pl = s.get(Playlist, pid)
            if pl is None:
                raise KeyError(pid)
            pl.items.clear()
            s.flush()
            for index, it in enumerate(items):
                pl.items.append(
                    PlaylistItem(
                        path=it["path"],
                        title=it.get("title", ""),
                        duration_sec=float(it.get("duration_sec", 0.0)),
                        position=index,
                        enabled=bool(it.get("enabled", True)),
                    )
                )

    def remove_item(self, pid: int, item_id: int) -> None:
        with self.db.session() as s:
            it = s.get(PlaylistItem, item_id)
            if it is not None and it.playlist_id == pid:
                s.delete(it)


class ScheduleRepository(_BaseRepo):
    def list(self, channel_id: int | None = None) -> list[Schedule]:
        with self.db.session() as s:
            q = select(Schedule).order_by(Schedule.start_at.is_(None), Schedule.start_at)
            if channel_id is not None:
                q = q.where(Schedule.channel_id == channel_id)
            return list(s.scalars(q).all())

    def add(self, channel_id: int, **fields) -> Schedule:
        with self.db.session() as s:
            sc = Schedule(channel_id=channel_id, **fields)
            s.add(sc)
            s.flush()
            s.refresh(sc)
            return sc

    def update(self, schedule_id: int, **fields) -> Schedule:
        with self.db.session() as s:
            sc = s.get(Schedule, schedule_id)
            if sc is None:
                raise KeyError(schedule_id)
            for k, v in fields.items():
                setattr(sc, k, v)
            s.flush()
            s.refresh(sc)
            return sc

    def delete(self, schedule_id: int) -> None:
        with self.db.session() as s:
            sc = s.get(Schedule, schedule_id)
            if sc is not None:
                s.delete(sc)


class SessionRepository(_BaseRepo):
    def open(self, channel_id: int) -> int:
        with self.db.session() as s:
            ss = StreamSession(channel_id=channel_id, started_at=datetime.utcnow())
            s.add(ss)
            s.flush()
            return ss.id

    def close(
        self,
        session_id: int,
        *,
        avg_bitrate: float,
        avg_fps: float,
        dropped: int,
        reconnects: int,
        ok: bool,
        error: str = "",
    ) -> None:
        with self.db.session() as s:
            ss = s.get(StreamSession, session_id)
            if ss is None:
                return
            ss.ended_at = datetime.utcnow()
            ss.duration_sec = (ss.ended_at - ss.started_at).total_seconds()
            ss.average_bitrate_kbps = float(avg_bitrate)
            ss.average_fps = float(avg_fps)
            ss.dropped_frames = int(dropped)
            ss.reconnects = int(reconnects)
            ss.finished_ok = bool(ok)
            ss.error_message = error

    def recent(self, limit: int = 50) -> list[StreamSession]:
        with self.db.session() as s:
            return list(
                s.scalars(
                    select(StreamSession).order_by(desc(StreamSession.started_at)).limit(limit)
                ).all()
            )

    def aggregate(self, since: datetime | None = None) -> dict:
        with self.db.session() as s:
            q = select(StreamSession)
            if since is not None:
                q = q.where(StreamSession.started_at >= since)
            sessions = list(s.scalars(q).all())
        total_seconds = sum(ss.duration_sec for ss in sessions)
        avg_bitrate = (
            sum(ss.average_bitrate_kbps for ss in sessions) / len(sessions) if sessions else 0.0
        )
        avg_fps = (
            sum(ss.average_fps for ss in sessions) / len(sessions) if sessions else 0.0
        )
        return {
            "total_sessions": len(sessions),
            "total_seconds": total_seconds,
            "average_bitrate": avg_bitrate,
            "average_fps": avg_fps,
            "dropped_frames": sum(ss.dropped_frames for ss in sessions),
            "reconnects": sum(ss.reconnects for ss in sessions),
            "errors": sum(0 if ss.finished_ok else 1 for ss in sessions),
        }


class LogRepository(_BaseRepo):
    def add(
        self,
        message: str,
        level: str = "INFO",
        source: str = "app",
        channel_id: int | None = None,
    ) -> None:
        with self.db.session() as s:
            s.add(LogEntry(level=level, source=source, channel_id=channel_id, message=message))

    def query(
        self,
        *,
        level: str | None = None,
        source: str | None = None,
        channel_id: int | None = None,
        search: str | None = None,
        limit: int = 500,
    ) -> list[LogEntry]:
        with self.db.session() as s:
            q = select(LogEntry).order_by(desc(LogEntry.ts)).limit(limit)
            if level:
                q = q.where(LogEntry.level == level)
            if source:
                q = q.where(LogEntry.source == source)
            if channel_id is not None:
                q = q.where(LogEntry.channel_id == channel_id)
            if search:
                q = q.where(LogEntry.message.contains(search))
            return list(s.scalars(q).all())

    def prune(self, older_than_days: int) -> int:
        cutoff = datetime.utcnow() - timedelta(days=older_than_days)
        with self.db.session() as s:
            rows = s.scalars(select(LogEntry).where(LogEntry.ts < cutoff)).all()
            count = len(rows)
            for r in rows:
                s.delete(r)
            return count


class AnalyticsRepository(_BaseRepo):
    def add(self, event: str, channel_id: int | None = None, payload: dict | None = None) -> None:
        with self.db.session() as s:
            s.add(AnalyticsEvent(event=event, channel_id=channel_id, payload=payload or {}))

    def recent(self, limit: int = 200) -> list[AnalyticsEvent]:
        with self.db.session() as s:
            return list(
                s.scalars(
                    select(AnalyticsEvent).order_by(desc(AnalyticsEvent.ts)).limit(limit)
                ).all()
            )


class SettingsRepository(_BaseRepo):
    def get(self, key: str, default: str = "") -> str:
        with self.db.session() as s:
            row = s.get(Setting, key)
            return row.value if row else default

    def set(self, key: str, value: str) -> None:
        with self.db.session() as s:
            row = s.get(Setting, key)
            if row is None:
                s.add(Setting(key=key, value=value))
            else:
                row.value = value

    def all(self) -> dict[str, str]:
        with self.db.session() as s:
            return {row.key: row.value for row in s.scalars(select(Setting)).all()}
