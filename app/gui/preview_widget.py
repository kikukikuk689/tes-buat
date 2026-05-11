"""Live composite preview widget.

Renders ONE frame at the current preview time, with the same code paths as
the full renderer.  Useful for checking the spectrum / lyric placement /
logo before kicking off a full render.
"""
from __future__ import annotations

from io import BytesIO

import numpy as np
from PIL import Image
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QLabel, QSizePolicy, QVBoxLayout, QWidget,
)

from ..core.renderer import RenderConfig, _draw_lyric
from ..core.audio_analyzer import analyze_audio, cleanup_audio
from ..core.background_handler import BackgroundEngine
from ..core.effects import create_effect
from ..core.logo_handler import LogoOverlay
from ..core.lrc_parser import parse_lrc, lyric_at
from ..core.spectrum_styles import render_frame as render_spectrum


def _pil_to_qpixmap(img: Image.Image) -> QPixmap:
    rgb = img.convert("RGB")
    data = np.array(rgb)
    h, w, _ = data.shape
    qimg = QImage(data.tobytes(), w, h, w * 3, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qimg.copy())


class PreviewWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.label = QLabel("Preview belum tersedia. Pilih audio + klik 'Preview'.", self)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.label.setMinimumSize(480, 270)
        self.label.setStyleSheet(
            "border:1px solid #d0d0d0; border-radius: 10px; background:#111; color:#aaa;"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.label)
        self._pix = None

    def set_image(self, img: Image.Image):
        pix = _pil_to_qpixmap(img)
        self._pix = pix
        self._refit()

    def resizeEvent(self, e):  # type: ignore
        self._refit()
        return super().resizeEvent(e)

    def _refit(self):
        if self._pix is None:
            return
        scaled = self._pix.scaled(self.label.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation)
        self.label.setPixmap(scaled)


def render_preview_frame(cfg: RenderConfig, t_sec: float) -> Image.Image:
    """Render a single composite preview frame at time ``t_sec``.

    NOTE: this re-analyzes audio each time which is expensive; the GUI
    should call this on demand only.  For real previews users can render
    a short clip.
    """
    size = cfg.size
    analysis = analyze_audio(cfg.audio_input, fps=cfg.fps, n_bars=64)
    try:
        i = min(int(t_sec * cfg.fps), analysis.bars.shape[0] - 1)
        bars = analysis.bars[i]
        loud = float(analysis.loudness[i])
        beat = float(analysis.beat[i])

        bg = BackgroundEngine(size, analysis.duration_sec, cfg.background)
        canvas = bg.frame(t_sec).convert("RGBA")
        bg.cleanup()

        canvas.alpha_composite(render_spectrum(size, bars, cfg.spectrum, loud, beat, t_sec))
        eff = create_effect(cfg.effect_name, size, cfg.fps,
                             intensity=cfg.effect_intensity,
                             color=cfg.effect_color)
        if eff is not None:
            canvas.alpha_composite(eff.step(beat, loud, t_sec))
        LogoOverlay(size, cfg.logo).composite(canvas)
        if cfg.lyrics_input:
            lyrics = parse_lrc(cfg.lyrics_input, offset_ms=cfg.lyric_offset_ms)
            active = lyric_at(lyrics, t_sec, cfg.lyric_lead_in, cfg.lyric_linger)
            if active is not None:
                _draw_lyric(canvas, active.text, cfg)
        return canvas
    finally:
        cleanup_audio(analysis)
