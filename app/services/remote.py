"""Remote control web dashboard (FastAPI + Socket.IO).

Provides a small REST + WebSocket API that mirrors the in-app stream
engine.  All routes require the optional auth token configured in
``remote.auth_token``.

Routes
------

* ``GET  /``                   – web dashboard (HTML)
* ``GET  /api/status``         – overall status (channels + stats)
* ``GET  /api/channels``       – channel list
* ``POST /api/channels/{id}/start``
* ``POST /api/channels/{id}/stop``
* ``POST /api/channels/{id}/restart``
* ``GET  /api/system``         – system metrics snapshot
* ``GET  /api/logs``           – recent log entries
* ``WS   /ws``                 – realtime push of stream + system events
"""
from __future__ import annotations

import asyncio
import json
import threading
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from ..core.config import get_config
from ..core.events import Topics, event_bus
from ..core.logger import get_logger
from ..core.paths import paths
from ..db.base import get_db
from ..db.repository import ChannelRepository, LogRepository
from .ffmpeg_manager import get_ffmpeg_manager
from .monitor import get_monitor
from .stream_engine import get_stream_engine


class _Hub:
    """Tiny WebSocket fan-out hub."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def add(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.add(ws)

    async def remove(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    def publish_threadsafe(self, payload: dict[str, Any]) -> None:
        if self._loop is None:
            return
        try:
            asyncio.run_coroutine_threadsafe(self._broadcast(payload), self._loop)
        except RuntimeError:
            pass

    async def _broadcast(self, payload: dict[str, Any]) -> None:
        text = json.dumps(payload, default=str)
        async with self._lock:
            dead: list[WebSocket] = []
            for ws in list(self._clients):
                try:
                    await ws.send_text(text)
                except Exception:  # noqa: BLE001
                    dead.append(ws)
            for ws in dead:
                self._clients.discard(ws)


def _require_token(request: Request | None) -> None:
    cfg = get_config().config.remote
    if not cfg.auth_token:
        return
    token = None
    if request is not None:
        token = request.headers.get("X-Auth-Token") or request.query_params.get("token")
    if token != cfg.auth_token:
        raise HTTPException(status_code=401, detail="Invalid auth token")


class RemoteControlServer:
    """Wraps uvicorn so the desktop app can start/stop the server in-process."""

    def __init__(self) -> None:
        self._log = get_logger("remote")
        self._thread: threading.Thread | None = None
        self._server: uvicorn.Server | None = None
        self._hub = _Hub()
        self._unsubs: list = []
        self._app = self._build_app()

    @property
    def running(self) -> bool:
        return self._server is not None and not self._server.should_exit

    def start(self) -> None:
        cfg = get_config().config.remote
        if not cfg.enabled or self.running:
            return
        config = uvicorn.Config(
            self._app,
            host=cfg.host,
            port=cfg.port,
            log_level="warning",
            loop="asyncio",
            access_log=False,
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(
            target=self._server.run, name="remote-control", daemon=True
        )
        self._thread.start()
        self._log.info("Remote control listening on http://%s:%d", cfg.host, cfg.port)

    def stop(self) -> None:
        for un in self._unsubs:
            try:
                un()
            except Exception:  # noqa: BLE001
                pass
        self._unsubs.clear()
        if self._server is not None:
            self._server.should_exit = True
        if self._thread:
            self._thread.join(timeout=4)
        self._server = None
        self._thread = None

    # ------------------------------------------------------------------
    def _build_app(self) -> FastAPI:
        app = FastAPI(title="ASMR Broadcast Studio")
        hub = self._hub
        log = self._log

        # Static + templates
        if paths.web_static.exists():
            app.mount("/static", StaticFiles(directory=str(paths.web_static)), name="static")

        @app.on_event("startup")
        async def _on_start() -> None:
            hub.set_loop(asyncio.get_running_loop())
            # subscribe to event bus and forward to ws clients
            self._unsubs.append(
                event_bus.subscribe(
                    Topics.STREAM_STATS, lambda p: hub.publish_threadsafe({"type": "stream.stats", "data": p})
                )
            )
            self._unsubs.append(
                event_bus.subscribe(
                    Topics.STREAM_STATE, lambda p: hub.publish_threadsafe({"type": "stream.state", "data": p})
                )
            )
            self._unsubs.append(
                event_bus.subscribe(
                    Topics.SYSTEM_STATS, lambda p: hub.publish_threadsafe({"type": "system.stats", "data": p})
                )
            )
            self._unsubs.append(
                event_bus.subscribe(
                    Topics.NOTIFICATION, lambda p: hub.publish_threadsafe({"type": "notification", "data": p})
                )
            )

        @app.get("/", response_class=HTMLResponse)
        async def index() -> str:
            index_file = paths.web_templates / "index.html"
            if index_file.exists():
                return index_file.read_text(encoding="utf-8")
            return "<h1>ASMR Broadcast Studio</h1><p>Web template missing.</p>"

        @app.get("/api/status")
        async def status(request: Request) -> dict[str, Any]:
            _require_token(request)
            engine = get_stream_engine()
            return {
                "channels": _serialise_channels(engine),
                "ffmpeg": {
                    "state": get_ffmpeg_manager().info.state.value,
                    "version": get_ffmpeg_manager().info.version,
                },
                "system": _stats_dict(),
            }

        @app.get("/api/channels")
        async def list_channels(request: Request) -> list[dict[str, Any]]:
            _require_token(request)
            return _serialise_channels(get_stream_engine())

        @app.post("/api/channels/{cid}/start")
        async def start_channel(cid: int, request: Request) -> dict[str, Any]:
            _require_token(request)
            get_stream_engine().start(cid)
            return {"ok": True, "channel_id": cid, "action": "start"}

        @app.post("/api/channels/{cid}/stop")
        async def stop_channel(cid: int, request: Request) -> dict[str, Any]:
            _require_token(request)
            get_stream_engine().stop(cid)
            return {"ok": True, "channel_id": cid, "action": "stop"}

        @app.post("/api/channels/{cid}/restart")
        async def restart_channel(cid: int, request: Request) -> dict[str, Any]:
            _require_token(request)
            get_stream_engine().restart(cid)
            return {"ok": True, "channel_id": cid, "action": "restart"}

        @app.get("/api/system")
        async def system(request: Request) -> dict[str, Any]:
            _require_token(request)
            return _stats_dict()

        @app.get("/api/logs")
        async def logs(request: Request, limit: int = 200) -> list[dict[str, Any]]:
            _require_token(request)
            entries = LogRepository(get_db()).query(limit=limit)
            return [
                {
                    "ts": e.ts.isoformat() + "Z",
                    "level": e.level,
                    "source": e.source,
                    "channel_id": e.channel_id,
                    "message": e.message,
                }
                for e in entries
            ]

        @app.websocket("/ws")
        async def ws_endpoint(ws: WebSocket) -> None:
            token = ws.query_params.get("token", "")
            cfg = get_config().config.remote
            if cfg.auth_token and token != cfg.auth_token:
                await ws.close(code=4401)
                return
            await ws.accept()
            await hub.add(ws)
            try:
                # initial snapshot
                await ws.send_text(
                    json.dumps(
                        {
                            "type": "snapshot",
                            "data": {
                                "channels": _serialise_channels(get_stream_engine()),
                                "system": _stats_dict(),
                            },
                        },
                        default=str,
                    )
                )
                while True:
                    msg = await ws.receive_text()
                    try:
                        data = json.loads(msg)
                    except json.JSONDecodeError:
                        continue
                    action = data.get("action")
                    cid = int(data.get("channel_id", -1))
                    if cid < 0:
                        continue
                    engine = get_stream_engine()
                    if action == "start":
                        engine.start(cid)
                    elif action == "stop":
                        engine.stop(cid)
                    elif action == "restart":
                        engine.restart(cid)
            except WebSocketDisconnect:
                pass
            except Exception:  # noqa: BLE001
                log.exception("WebSocket failed")
            finally:
                await hub.remove(ws)

        return app


def _serialise_channels(engine) -> list[dict[str, Any]]:
    repo = ChannelRepository(get_db())
    out = []
    for ch in repo.list():
        stats = engine.runtime(ch.id).stats if engine.is_running(ch.id) else None
        out.append(
            {
                "id": ch.id,
                "name": ch.name,
                "platform": ch.platform,
                "rtmp_url": ch.rtmp_url,
                "enabled": ch.enabled,
                "state": (stats.state.value if stats else ch.last_state.value),
                "fps": getattr(stats, "fps", 0.0),
                "bitrate_kbps": getattr(stats, "bitrate_kbps", 0.0),
                "uptime_sec": getattr(stats, "uptime_sec", 0.0),
                "reconnects": getattr(stats, "reconnects", 0),
                "dropped": getattr(stats, "dropped", 0),
            }
        )
    return out


def _stats_dict() -> dict[str, Any]:
    from dataclasses import asdict

    return asdict(get_monitor().stats())


_GLOBAL: RemoteControlServer | None = None


def get_remote_server() -> RemoteControlServer:
    global _GLOBAL
    if _GLOBAL is None:
        _GLOBAL = RemoteControlServer()
    return _GLOBAL
