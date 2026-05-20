"""AI assistance service.

Wraps an OpenAI-compatible chat completions endpoint to produce:

* stream titles
* descriptions
* hashtags
* thumbnail prompts
* bitrate / encoder optimisation suggestions

When no API key has been configured the service falls back to
high-quality deterministic templates so the UI buttons always do
*something useful* rather than being dummies.  When an API key *is*
configured we use it for real and surface the response verbatim.
"""
from __future__ import annotations

import json
import random
from collections.abc import Iterable
from dataclasses import dataclass

import httpx

from ..core.config import get_config
from ..core.logger import get_logger
from ..security.credentials import get_credentials
from ..utils.platform_utils import detect_gpu


@dataclass
class AISuggestion:
    title: str
    description: str
    hashtags: list[str]
    thumbnail_prompt: str
    source: str  # "ai" or "template"


SAMPLE_VIBES = [
    "Cozy thunderstorm",
    "Soft brushing whispers",
    "Crackling fireplace",
    "Ocean waves at midnight",
    "Tapping & scratching",
    "Layered tingles",
    "Page turning",
    "Slow ear cleaning",
]

HOOKS = [
    "Drift into deep sleep",
    "Unwind and relax",
    "Total tingles guaranteed",
    "Stress melts away",
    "Slow, gentle, immersive",
]


class AIService:
    def __init__(self) -> None:
        self._log = get_logger("ai")

    # ------------------------------------------------------------------
    @property
    def enabled(self) -> bool:
        cfg = get_config().config.ai
        if not cfg.enabled:
            return False
        return bool(self._api_key())

    def _api_key(self) -> str:
        return get_credentials().get("openai_api_key", "")

    # ------------------------------------------------------------------
    def suggest_stream_metadata(self, *, theme: str = "ASMR", channel_name: str = "") -> AISuggestion:
        if self.enabled:
            try:
                return self._ai_metadata(theme=theme, channel_name=channel_name)
            except Exception as exc:  # noqa: BLE001
                self._log.warning("AI metadata failed, falling back to template: %s", exc)
        return self._template_metadata(theme=theme, channel_name=channel_name)

    def optimize_encoder(self, *, target_bitrate_kbps: int, available_encoders: Iterable[str]) -> dict:
        gpu = detect_gpu()
        encoder = gpu.best_encoder
        preset = "p4" if encoder == "nvenc" else "veryfast"
        # bitrate clamp: keep within sane RTMP territory
        bitrate = max(2000, min(target_bitrate_kbps, 12_000))
        return {
            "video_encoder": {
                "nvenc": "h264_nvenc",
                "qsv": "h264_qsv",
                "amf": "h264_amf",
                "videotoolbox": "h264_videotoolbox",
            }.get(encoder, "libx264"),
            "preset": preset,
            "tuned_bitrate_kbps": bitrate,
            "rationale": (
                f"Detected GPU vendor preference: {encoder}. "
                f"Clamped bitrate to {bitrate} kbps for stable RTMP delivery."
            ),
        }

    def suggest_thumbnail_text(self, *, theme: str = "ASMR") -> str:
        if self.enabled:
            try:
                return self._ai_call(
                    "You are a concise YouTube thumbnail copywriter. "
                    "Reply with one short, hooky 2-5 word thumbnail phrase.",
                    f"Theme: {theme}",
                ).strip().strip('"')
            except Exception as exc:  # noqa: BLE001
                self._log.warning("Thumbnail AI call failed: %s", exc)
        return f"{random.choice(HOOKS)} • {random.choice(SAMPLE_VIBES)}"

    # ------------------------------------------------------------------
    # AI backed implementations
    # ------------------------------------------------------------------
    def _ai_metadata(self, theme: str, channel_name: str) -> AISuggestion:
        system = (
            "You are an expert YouTube/Twitch broadcasting copywriter for ASMR streams. "
            "Return JSON with keys: title, description, hashtags (list), thumbnail_prompt. "
            "Keep title under 90 chars. Description should be 3-5 sentences."
        )
        user = json.dumps(
            {
                "channel_name": channel_name or "ASMR Studio",
                "theme": theme,
                "language": get_config().config.ai.default_language,
            }
        )
        raw = self._ai_call(system, user)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {}
        return AISuggestion(
            title=payload.get("title", "")[:100] or f"24/7 {theme} Live Stream",
            description=payload.get("description", "") or "",
            hashtags=[h.lstrip("#") for h in payload.get("hashtags", []) if isinstance(h, str)],
            thumbnail_prompt=payload.get("thumbnail_prompt", ""),
            source="ai",
        )

    def _ai_call(self, system: str, user: str) -> str:
        cfg = get_config().config.ai
        api_key = self._api_key()
        url = f"{cfg.api_base.rstrip('/')}/chat/completions"
        body = {
            "model": cfg.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.7,
            "response_format": {"type": "json_object"} if "json" in system.lower() else None,
        }
        # Strip None entries for providers that don't accept response_format
        body = {k: v for k, v in body.items() if v is not None}
        with httpx.Client(timeout=30) as client:
            r = client.post(
                url, json=body, headers={"Authorization": f"Bearer {api_key}"}
            )
            r.raise_for_status()
            data = r.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"Unexpected AI response: {data}") from exc

    # ------------------------------------------------------------------
    def _template_metadata(self, theme: str, channel_name: str) -> AISuggestion:
        vibe = random.choice(SAMPLE_VIBES)
        hook = random.choice(HOOKS)
        title = f"24/7 {theme} • {vibe} • {hook}"
        description = (
            f"Welcome to {channel_name or 'our ASMR studio'} — a continuous, "
            f"cinematic {theme.lower()} broadcast designed to help you relax, "
            f"focus, or sleep. Tonight's vibe: {vibe.lower()}. New triggers added daily.\n\n"
            "Tip: use headphones for the best immersive experience."
        )
        hashtags = [
            "asmr",
            "asmrlive",
            theme.lower().replace(" ", ""),
            vibe.split()[0].lower(),
            "sleep",
            "relax",
            "ambient",
        ]
        thumbnail_prompt = f"Soft cinematic close-up of {vibe.lower()}, dramatic purple neon lighting, 4k."
        return AISuggestion(
            title=title,
            description=description,
            hashtags=hashtags,
            thumbnail_prompt=thumbnail_prompt,
            source="template",
        )


_GLOBAL: AIService | None = None


def get_ai() -> AIService:
    global _GLOBAL
    if _GLOBAL is None:
        _GLOBAL = AIService()
    return _GLOBAL
