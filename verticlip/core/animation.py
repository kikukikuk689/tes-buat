"""
Logo motion math used both by preview and the FFmpeg render.

All motions are expressed as a smooth, periodic offset (dx, dy) in
**normalized output coordinates** so they look identical in preview and
in the final video.

We expose two interfaces:
    * ``offset_at(motion, t, amplitude, period)``  -> (dx, dy) for preview
    * ``ffmpeg_expr(motion, amplitude, period, output_w, output_h)``
      returns a pair of FFmpeg expressions (x_expr, y_expr) suitable for
      the ``overlay`` filter's ``x=`` and ``y=`` arguments.
"""
from __future__ import annotations

import math
from typing import Tuple

from .project import LogoMotion


def offset_at(
    motion: LogoMotion,
    t_seconds: float,
    amplitude: float,
    period_s: float,
) -> Tuple[float, float]:
    """Return normalized (dx, dy) offset for the given time."""
    if motion == LogoMotion.NONE or period_s <= 0.0:
        return (0.0, 0.0)
    phase = 2.0 * math.pi * (t_seconds / period_s)
    if motion == LogoMotion.CIRCLE:
        # Move on a circle of radius=amplitude (looks like the digit 0).
        return (amplitude * math.cos(phase), amplitude * math.sin(phase))
    if motion == LogoMotion.FIGURE8:
        # Lissajous figure 8: x = A*sin(t), y = A*sin(2t)/2
        return (
            amplitude * math.sin(phase),
            (amplitude / 2.0) * math.sin(2.0 * phase),
        )
    if motion == LogoMotion.BOUNCE:
        # Vertical bounce (downward then back): abs(sin) gives bouncing feel
        return (0.0, -amplitude * abs(math.sin(phase)))
    return (0.0, 0.0)


def ffmpeg_expr(
    motion: LogoMotion,
    base_x: float,
    base_y: float,
    amp_px_x: float,
    amp_px_y: float,
    period_s: float,
) -> Tuple[str, str]:
    """
    Build the FFmpeg ``overlay`` x/y expressions in PIXELS.

    ``base_x``/``base_y`` are the un-animated top-left position in pixels.
    ``amp_px_*`` is the motion amplitude in pixels for each axis.
    """
    if motion == LogoMotion.NONE or period_s <= 0.0:
        return (f"{base_x}", f"{base_y}")

    # FFmpeg expression evaluator supports ``t`` (seconds), sin/cos/abs.
    omega = f"(2*PI*t/{period_s})"
    if motion == LogoMotion.CIRCLE:
        x = f"{base_x}+({amp_px_x})*cos({omega})"
        y = f"{base_y}+({amp_px_y})*sin({omega})"
        return (x, y)
    if motion == LogoMotion.FIGURE8:
        x = f"{base_x}+({amp_px_x})*sin({omega})"
        y = f"{base_y}+({amp_px_y}/2)*sin(2*{omega})"
        return (x, y)
    if motion == LogoMotion.BOUNCE:
        x = f"{base_x}"
        y = f"{base_y}-({amp_px_y})*abs(sin({omega}))"
        return (x, y)
    return (f"{base_x}", f"{base_y}")
