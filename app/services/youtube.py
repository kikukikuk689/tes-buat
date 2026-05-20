"""YouTube Live API integration.

Provides a real OAuth flow (``google-auth-oauthlib``) and Live Broadcast
CRUD over the YouTube Data API v3.  The user must supply a
``client_secret.json`` downloaded from their Google Cloud Console; the
path is stored in the application config (``youtube.client_secret_path``).

Operations exposed
------------------

* ``authorize(force=False)`` - browser-based OAuth dance.
* ``create_live_broadcast(...)``
* ``bind_stream(broadcast_id, stream_id)``
* ``update_broadcast(broadcast_id, ...)``
* ``set_thumbnail(broadcast_id, path)``
* ``list_active_broadcasts()``
* ``get_live_analytics(video_id)``
"""
from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..core.config import get_config
from ..core.exceptions import StudioError
from ..core.logger import get_logger
from ..core.paths import paths

# All Google libraries are imported lazily so the rest of the app starts
# even if they fail to import (e.g. on stripped-down CI environments).
SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


class YouTubeError(StudioError):
    pass


class YouTubeService:
    def __init__(self) -> None:
        self._log = get_logger("youtube")
        self._lock = threading.RLock()
        self._service = None  # googleapiclient.discovery.Resource | None

    # ------------------------------------------------------------------
    @property
    def is_authorized(self) -> bool:
        return paths.youtube_token_file.exists()

    def authorize(self, force: bool = False) -> dict[str, Any]:
        cfg = get_config().config.youtube
        secret_path = Path(cfg.client_secret_path).expanduser()
        if not secret_path.exists():
            raise YouTubeError(
                "client_secret.json not configured. Set youtube.client_secret_path in settings."
            )
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
        except ImportError as exc:
            raise YouTubeError("google-auth-oauthlib is required for YouTube OAuth.") from exc
        if force and paths.youtube_token_file.exists():
            paths.youtube_token_file.unlink()
        flow = InstalledAppFlow.from_client_secrets_file(str(secret_path), SCOPES)
        creds = flow.run_local_server(port=0, open_browser=True)
        paths.youtube_token_file.write_text(creds.to_json(), encoding="utf-8")
        with self._lock:
            self._service = None  # force re-build with the new creds
        return {"authorized": True, "scopes": creds.scopes}

    def revoke(self) -> None:
        if paths.youtube_token_file.exists():
            paths.youtube_token_file.unlink()
        with self._lock:
            self._service = None

    # ------------------------------------------------------------------
    def _client(self):
        with self._lock:
            if self._service is not None:
                return self._service
            try:
                from google.auth.transport.requests import Request as GRequest
                from google.oauth2.credentials import Credentials
                from googleapiclient.discovery import build
            except ImportError as exc:
                raise YouTubeError("google-api-python-client is required") from exc
            if not paths.youtube_token_file.exists():
                raise YouTubeError("YouTube is not authorized yet — call authorize() first.")
            data = json.loads(paths.youtube_token_file.read_text(encoding="utf-8"))
            creds = Credentials.from_authorized_user_info(data, SCOPES)
            if not creds.valid and creds.expired and creds.refresh_token:
                creds.refresh(GRequest())
                paths.youtube_token_file.write_text(creds.to_json(), encoding="utf-8")
            self._service = build("youtube", "v3", credentials=creds, cache_discovery=False)
            return self._service

    # ------------------------------------------------------------------
    # High-level helpers
    # ------------------------------------------------------------------
    def create_live_broadcast(
        self,
        title: str,
        description: str = "",
        scheduled_start: datetime | None = None,
        privacy: str | None = None,
        category_id: str | None = None,
        tags: list[str] | None = None,
        latency: str | None = None,
        enable_dvr: bool | None = None,
    ) -> dict[str, Any]:
        cfg = get_config().config.youtube
        svc = self._client()
        when = scheduled_start or datetime.now(UTC)
        body = {
            "snippet": {
                "title": title,
                "description": description,
                "scheduledStartTime": when.isoformat().replace("+00:00", "Z"),
                "categoryId": category_id or cfg.default_category_id,
            },
            "status": {
                "privacyStatus": privacy or cfg.default_privacy,
                "selfDeclaredMadeForKids": False,
            },
            "contentDetails": {
                "enableAutoStart": True,
                "enableAutoStop": True,
                "enableDvr": cfg.enable_dvr if enable_dvr is None else enable_dvr,
                "enableContentEncryption": True,
                "latencyPreference": latency or cfg.latency_preference,
            },
        }
        broadcast = svc.liveBroadcasts().insert(
            part="snippet,status,contentDetails", body=body
        ).execute()
        if tags:
            self.update_broadcast(broadcast["id"], tags=tags)
        return broadcast

    def list_active_broadcasts(self) -> list[dict[str, Any]]:
        svc = self._client()
        response = svc.liveBroadcasts().list(
            part="id,snippet,status",
            broadcastStatus="active",
            maxResults=50,
        ).execute()
        return response.get("items", [])

    def update_broadcast(
        self,
        broadcast_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
        category_id: str | None = None,
    ) -> dict[str, Any]:
        svc = self._client()
        current = svc.videos().list(part="snippet,status", id=broadcast_id).execute()
        items = current.get("items", [])
        if not items:
            raise YouTubeError(f"Broadcast {broadcast_id} not found")
        snippet = items[0]["snippet"]
        if title is not None:
            snippet["title"] = title
        if description is not None:
            snippet["description"] = description
        if tags is not None:
            snippet["tags"] = tags
        if category_id is not None:
            snippet["categoryId"] = category_id
        body = {"id": broadcast_id, "snippet": snippet}
        return svc.videos().update(part="snippet", body=body).execute()

    def set_thumbnail(self, broadcast_id: str, image_path: str | Path) -> dict[str, Any]:
        svc = self._client()
        return svc.thumbnails().set(videoId=broadcast_id, media_body=str(image_path)).execute()

    def bind_stream(self, broadcast_id: str, stream_id: str) -> dict[str, Any]:
        svc = self._client()
        return svc.liveBroadcasts().bind(
            part="id,snippet,contentDetails,status",
            id=broadcast_id,
            streamId=stream_id,
        ).execute()

    def create_stream(
        self,
        title: str,
        *,
        resolution: str = "1080p",
        fps: int = 30,
        ingestion_type: str = "rtmp",
    ) -> dict[str, Any]:
        svc = self._client()
        body = {
            "snippet": {"title": title},
            "cdn": {
                "frameRate": "30fps" if fps <= 30 else "60fps",
                "ingestionType": ingestion_type,
                "resolution": resolution,
            },
        }
        return svc.liveStreams().insert(part="snippet,cdn,status", body=body).execute()

    def get_live_analytics(self, video_id: str) -> dict[str, Any]:
        svc = self._client()
        response = svc.videos().list(
            part="liveStreamingDetails,statistics,status", id=video_id
        ).execute()
        items = response.get("items", [])
        if not items:
            return {}
        v = items[0]
        details = v.get("liveStreamingDetails", {})
        stats = v.get("statistics", {})
        return {
            "concurrent_viewers": int(details.get("concurrentViewers", 0)),
            "scheduled_start": details.get("scheduledStartTime"),
            "actual_start": details.get("actualStartTime"),
            "actual_end": details.get("actualEndTime"),
            "active_live_chat_id": details.get("activeLiveChatId"),
            "view_count": int(stats.get("viewCount", 0)),
            "like_count": int(stats.get("likeCount", 0)),
        }


_GLOBAL: YouTubeService | None = None


def get_youtube() -> YouTubeService:
    global _GLOBAL
    if _GLOBAL is None:
        _GLOBAL = YouTubeService()
    return _GLOBAL
