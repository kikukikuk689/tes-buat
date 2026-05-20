"""APScheduler-backed channel scheduler."""
from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from ..core.events import Topics, event_bus
from ..core.logger import get_logger
from ..db.base import get_db
from ..db.repository import ChannelRepository, ScheduleRepository
from .stream_engine import get_stream_engine


class SchedulerService:
    def __init__(self) -> None:
        self._log = get_logger("scheduler")
        self._scheduler: BackgroundScheduler | None = None
        self._lock = threading.RLock()
        self._jobs: dict[str, str] = {}

    def start(self) -> None:
        with self._lock:
            if self._scheduler is None:
                self._scheduler = BackgroundScheduler()
                self._scheduler.start()
                self.reload()

    def stop(self) -> None:
        with self._lock:
            if self._scheduler is not None:
                self._scheduler.shutdown(wait=False)
                self._scheduler = None
                self._jobs.clear()

    def reload(self) -> None:
        """Re-read all schedules from the DB and re-register them."""
        with self._lock:
            sched = self._scheduler
            if sched is None:
                return
            for job_id in list(self._jobs.values()):
                try:
                    sched.remove_job(job_id)
                except Exception:  # noqa: BLE001
                    pass
            self._jobs.clear()
            schedules = ScheduleRepository(get_db()).list()
            channels = {c.id: c for c in ChannelRepository(get_db()).list()}
            for s in schedules:
                if not s.enabled or s.channel_id not in channels:
                    continue
                self._register(s, sched)
            self._log.info("Loaded %d schedules", len(self._jobs) // 2)

    # ------------------------------------------------------------------
    def _register(self, s, sched: BackgroundScheduler) -> None:
        engine = get_stream_engine()

        def _start(channel_id=s.channel_id) -> None:
            self._log.info("Scheduler firing start for channel %s", channel_id)
            engine.start(channel_id)
            event_bus.publish(
                Topics.SCHEDULER_TICK,
                {"channel_id": channel_id, "action": "start", "at": datetime.utcnow().isoformat()},
            )

        def _stop(channel_id=s.channel_id) -> None:
            self._log.info("Scheduler firing stop for channel %s", channel_id)
            engine.stop(channel_id)
            event_bus.publish(
                Topics.SCHEDULER_TICK,
                {"channel_id": channel_id, "action": "stop", "at": datetime.utcnow().isoformat()},
            )

        start_id = f"sched-{s.id}-start"
        stop_id = f"sched-{s.id}-stop"
        try:
            if s.start_at:
                sched.add_job(_start, DateTrigger(run_date=s.start_at), id=start_id, replace_existing=True)
                self._jobs[f"start:{s.id}"] = start_id
            if s.stop_at:
                sched.add_job(_stop, DateTrigger(run_date=s.stop_at), id=stop_id, replace_existing=True)
                self._jobs[f"stop:{s.id}"] = stop_id
            if s.cron_start:
                sched.add_job(
                    _start,
                    CronTrigger.from_crontab(s.cron_start),
                    id=start_id,
                    replace_existing=True,
                )
                self._jobs[f"start:{s.id}"] = start_id
            if s.cron_stop:
                sched.add_job(
                    _stop,
                    CronTrigger.from_crontab(s.cron_stop),
                    id=stop_id,
                    replace_existing=True,
                )
                self._jobs[f"stop:{s.id}"] = stop_id
        except Exception:  # noqa: BLE001
            self._log.exception("Failed to register schedule %s", s.id)

    def add_one_shot(self, channel_id: int, when: datetime, action: str, callback: Callable | None = None) -> None:
        with self._lock:
            if self._scheduler is None:
                return
            engine = get_stream_engine()
            target = engine.start if action == "start" else engine.stop
            job_id = f"oneshot-{channel_id}-{when.timestamp()}-{action}"
            self._scheduler.add_job(target, DateTrigger(run_date=when), args=(channel_id,), id=job_id)
            if callback:
                callback()


_GLOBAL: SchedulerService | None = None


def get_scheduler() -> SchedulerService:
    global _GLOBAL
    if _GLOBAL is None:
        _GLOBAL = SchedulerService()
    return _GLOBAL
