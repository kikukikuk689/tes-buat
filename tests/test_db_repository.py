from __future__ import annotations

from pathlib import Path

from app.db.base import Database
from app.db.repository import (
    ChannelRepository,
    PlaylistRepository,
    ScheduleRepository,
    SessionRepository,
)


def _db(tmp_path: Path) -> Database:
    db = Database(tmp_path / "studio.db")
    db.init()
    return db


def test_channel_crud(tmp_path: Path) -> None:
    db = _db(tmp_path)
    repo = ChannelRepository(db)
    ch = repo.create(name="Test", platform="youtube", rtmp_url="rtmp://example/live")
    assert ch.id is not None

    repo.update(ch.id, video_bitrate_kbps=5000)
    fetched = repo.get(ch.id)
    assert fetched is not None
    assert fetched.video_bitrate_kbps == 5000

    repo.delete(ch.id)
    assert repo.get(ch.id) is None


def test_playlist_items_replace(tmp_path: Path) -> None:
    from sqlalchemy import select

    from app.db.models import PlaylistItem

    db = _db(tmp_path)
    repo = PlaylistRepository(db)
    pl = repo.create(name="ambient")
    repo.add_items(pl.id, [{"path": "/a.mp4"}, {"path": "/b.mp4"}])

    with db.session() as s:
        items = list(s.scalars(select(PlaylistItem).where(PlaylistItem.playlist_id == pl.id)))
        assert {i.path for i in items} == {"/a.mp4", "/b.mp4"}

    repo.replace_items(pl.id, [{"path": "/c.mp4"}])
    with db.session() as s:
        items = list(s.scalars(select(PlaylistItem).where(PlaylistItem.playlist_id == pl.id)))
        assert [i.path for i in items] == ["/c.mp4"]


def test_schedule_lifecycle(tmp_path: Path) -> None:
    db = _db(tmp_path)
    ch = ChannelRepository(db).create(name="C", platform="youtube", rtmp_url="rtmp://x/y")
    sched_repo = ScheduleRepository(db)
    sc = sched_repo.add(ch.id, label="nightly", cron_start="0 22 * * *")
    assert sched_repo.list(ch.id)
    sched_repo.delete(sc.id)
    assert not sched_repo.list(ch.id)


def test_session_aggregate(tmp_path: Path) -> None:
    db = _db(tmp_path)
    ch = ChannelRepository(db).create(name="C2", platform="youtube", rtmp_url="rtmp://x/y")
    sr = SessionRepository(db)
    sid = sr.open(ch.id)
    sr.close(sid, avg_bitrate=3000, avg_fps=29.97, dropped=2, reconnects=1, ok=True)
    agg = sr.aggregate()
    assert agg["total_sessions"] == 1
    assert agg["average_bitrate"] == 3000
    assert agg["reconnects"] == 1
