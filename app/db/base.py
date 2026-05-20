"""SQLAlchemy engine / session management."""
from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from ..core.logger import get_logger
from ..core.paths import paths


class Base(DeclarativeBase):
    pass


class Database:
    """Wraps the engine/session factory with thread-safe accessors."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._log = get_logger("db")
        self._lock = threading.RLock()
        self._path = db_path or paths.db_path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{self._path}"
        self._engine: Engine = create_engine(
            url,
            future=True,
            echo=False,
            connect_args={"check_same_thread": False, "timeout": 30},
        )

        @event.listens_for(self._engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:  # noqa: ANN001
            cur = dbapi_connection.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.close()

        self._SessionLocal = sessionmaker(
            bind=self._engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
            future=True,
        )
        self._initialised = False

    @property
    def engine(self) -> Engine:
        return self._engine

    @property
    def path(self) -> Path:
        return self._path

    def init(self) -> None:
        if self._initialised:
            return
        with self._lock:
            from . import models  # noqa: F401 - ensure tables are registered

            Base.metadata.create_all(self._engine)
            self._initialised = True
            self._log.info("Database initialised at %s", self._path)

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Context-managed session with auto-commit on success."""
        self.init()
        session = self._SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def vacuum(self) -> None:
        with self._engine.begin() as conn:
            conn.exec_driver_sql("VACUUM")


_GLOBAL: Database | None = None


def get_db() -> Database:
    global _GLOBAL
    if _GLOBAL is None:
        _GLOBAL = Database()
        _GLOBAL.init()
    return _GLOBAL
