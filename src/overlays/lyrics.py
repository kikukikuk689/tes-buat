"""Lyrics overlay dengan sinkronisasi LRC timestamp."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter

from ..core.lrc import LRC, LyricLine, split_long_line
from ..utils.fonts import default_font_name, load_font


@dataclass
class LyricsConfig:
    font_name: Optional[str] = None
    font_size_ratio: float = 0.045       # relatif tinggi video
    color: Tuple[int, int, int] = (255, 255, 255)
    stroke_color: Tuple[int, int, int] = (0, 0, 0)
    stroke_width: int = 3
    shadow: bool = True
    shadow_offset: Tuple[int, int] = (2, 3)
    shadow_blur: int = 4
    bottom_ratio: float = 0.78          # posisi vertikal pusat lirik (frac H)
    max_chars: int = 38
    show_upcoming: bool = True
    fade_seconds: float = 0.35
    highlight_color: Optional[Tuple[int, int, int]] = None  # kalau ada, baris aktif pakai warna ini
    spacing: int = 6
    pre_roll: float = 0.0               # offset (detik) untuk muncul lebih awal kalau diinginkan


class LyricsOverlay:
    def __init__(self, cfg: LyricsConfig, lrc: Optional[LRC], frame_size: Tuple[int, int]):
        self.cfg = cfg
        self.lrc = lrc or LRC()
        self.frame_size = frame_size
        self._font_cache = None
        self._font_size = max(16, int(frame_size[1] * cfg.font_size_ratio))
        self._reload_font()

    def update(self, cfg: Optional[LyricsConfig] = None, lrc: Optional[LRC] = None) -> None:
        if cfg is not None:
            self.cfg = cfg
            self._font_size = max(16, int(self.frame_size[1] * cfg.font_size_ratio))
            self._reload_font()
        if lrc is not None:
            self.lrc = lrc

    def _reload_font(self) -> None:
        name = self.cfg.font_name or default_font_name()
        self._font_cache = load_font(name, self._font_size)

    def _alpha_for(self, line: LyricLine, t: float) -> float:
        fade = max(0.01, self.cfg.fade_seconds)
        if t < line.start - self.cfg.pre_roll:
            return 0.0
        if t < line.start:
            return (t - (line.start - self.cfg.pre_roll)) / max(0.01, self.cfg.pre_roll)
        # fade in
        if t < line.start + fade:
            return (t - line.start) / fade
        # fade out
        if t > line.end - fade:
            return max(0.0, (line.end - t) / fade)
        return 1.0

    def _draw_text(self, draw: ImageDraw.ImageDraw, layer: Image.Image,
                   text: str, cy: int, color: Tuple[int, int, int], alpha: float) -> None:
        if alpha <= 0.0 or not text:
            return
        font = self._font_cache
        W, _ = self.frame_size
        # Wrap
        wraps = split_long_line(LyricLine(0, 0, text), self.cfg.max_chars)
        # Measure total height
        line_h = self._font_size + self.cfg.spacing
        total_h = line_h * len(wraps)
        y0 = cy - total_h // 2

        a = int(255 * max(0.0, min(1.0, alpha)))

        if self.cfg.shadow:
            shadow_layer = Image.new("RGBA", layer.size, (0, 0, 0, 0))
            sd = ImageDraw.Draw(shadow_layer)
            ox, oy = self.cfg.shadow_offset
            for i, ln in enumerate(wraps):
                bbox = sd.textbbox((0, 0), ln, font=font)
                tw = bbox[2] - bbox[0]
                tx = (W - tw) // 2 + ox
                ty = y0 + i * line_h + oy
                sd.text((tx, ty), ln, font=font, fill=(0, 0, 0, int(a * 0.65)))
            shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(self.cfg.shadow_blur))
            layer.alpha_composite(shadow_layer)

        for i, ln in enumerate(wraps):
            bbox = draw.textbbox((0, 0), ln, font=font)
            tw = bbox[2] - bbox[0]
            tx = (W - tw) // 2
            ty = y0 + i * line_h
            if self.cfg.stroke_width > 0:
                draw.text((tx, ty), ln, font=font,
                          fill=(*color, a),
                          stroke_width=self.cfg.stroke_width,
                          stroke_fill=(*self.cfg.stroke_color, a))
            else:
                draw.text((tx, ty), ln, font=font, fill=(*color, a))

    def draw(self, im: Image.Image, t: float) -> None:
        if not self.lrc.lines:
            return
        if t < self.lrc.first_start - self.cfg.pre_roll:
            return  # benar-benar belum ada lirik

        W, H = self.frame_size
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        y = int(H * self.cfg.bottom_ratio)

        cur = self.lrc.line_at(t)
        upcoming = self.lrc.upcoming(t)

        # Active line
        if cur is not None:
            alpha = self._alpha_for(cur, t)
            color = self.cfg.highlight_color or self.cfg.color
            self._draw_text(d, layer, cur.text, y, color, alpha)
        # Upcoming preview (slightly smaller / dimmer)
        if self.cfg.show_upcoming and upcoming is not None and (
            cur is None or upcoming is not cur
        ):
            preview_alpha = 0.0
            # within 1.5s before start
            if upcoming.start - t < 1.5:
                preview_alpha = max(0.0, 1.0 - (upcoming.start - t) / 1.5) * 0.55
            if preview_alpha > 0.01:
                self._draw_text(d, layer, upcoming.text,
                                y + int(self._font_size * 1.3),
                                self.cfg.color, preview_alpha * 0.6)

        im.alpha_composite(layer)
