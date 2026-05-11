"""Spectrum visualization styles.

Each style is a small, fast renderer that takes a ``(n_bars,)`` array of
normalized magnitudes (and a few global scalars) and draws into an RGBA
PIL image overlay. The overlay is then composited onto the background by
the renderer.

All styles share the same ``SpectrumConfig`` so the GUI can swap styles
seamlessly. Rendering is intentionally numpy / PIL based (no shaders) so
the app stays light enough for low-end PCs.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


# ---------------------------------------------------------------------------
# Color helpers
# ---------------------------------------------------------------------------

def hex_to_rgb(s: str) -> Tuple[int, int, int]:
    s = s.lstrip("#")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def lerp_color(c1, c2, t: float):
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


def hsv_to_rgb(h: float, s: float, v: float) -> Tuple[int, int, int]:
    h = h % 1.0
    i = int(h * 6)
    f = h * 6 - i
    p = v * (1 - s)
    q = v * (1 - f * s)
    t = v * (1 - (1 - f) * s)
    if i % 6 == 0: r, g, b = v, t, p
    elif i % 6 == 1: r, g, b = q, v, p
    elif i % 6 == 2: r, g, b = p, v, t
    elif i % 6 == 3: r, g, b = p, q, v
    elif i % 6 == 4: r, g, b = t, p, v
    else: r, g, b = v, p, q
    return int(r * 255), int(g * 255), int(b * 255)


# Color palettes the user can pick from in the GUI. Each is a list of
# RGB stops used either as a gradient across bars or across height.
PALETTES: Dict[str, List[Tuple[int, int, int]]] = {
    "Sunset":      [(255, 81, 47), (240, 152, 25), (255, 213, 79)],
    "Aurora":      [(0, 210, 255), (123, 97, 255), (255, 87, 184)],
    "Ocean":       [(0, 122, 204), (0, 200, 220), (140, 240, 200)],
    "Neon":        [(57, 255, 20), (0, 255, 255), (255, 0, 200)],
    "Fire":        [(255, 0, 0), (255, 140, 0), (255, 230, 90)],
    "Ice":         [(140, 240, 255), (190, 220, 255), (255, 255, 255)],
    "Candy":       [(255, 110, 196), (255, 195, 113), (140, 235, 255)],
    "Forest":      [(46, 125, 50), (139, 195, 74), (220, 237, 200)],
    "Gold":        [(255, 215, 0), (255, 165, 0), (255, 245, 200)],
    "Monochrome":  [(255, 255, 255), (220, 220, 220), (180, 180, 180)],
    "Rainbow":     [hsv_to_rgb(h / 8.0, 0.9, 1.0) for h in range(9)],
    "Galaxy":      [(83, 0, 153), (211, 0, 153), (66, 230, 255)],
    "Magma":       [(0, 0, 60), (160, 30, 90), (255, 200, 80)],
    "Mint":        [(0, 196, 154), (167, 233, 175), (240, 255, 220)],
    "Cherry":      [(245, 0, 87), (255, 110, 64), (255, 213, 213)],
}


def palette_color(palette: str, t: float) -> Tuple[int, int, int]:
    """Sample a palette gradient at ``t`` in [0,1]."""
    stops = PALETTES.get(palette, PALETTES["Aurora"])
    if t <= 0:
        return stops[0]
    if t >= 1:
        return stops[-1]
    pos = t * (len(stops) - 1)
    i = int(pos)
    f = pos - i
    return lerp_color(stops[i], stops[i + 1], f)


# ---------------------------------------------------------------------------
# Config + base helpers
# ---------------------------------------------------------------------------


@dataclass
class SpectrumConfig:
    style: str = "Bars"
    palette: str = "Aurora"
    # Vertical region the spectrum may occupy as a fraction of the canvas
    # height. ``height_ratio=0.25`` keeps it nicely along the bottom and
    # prevents the spectrum from filling the whole frame.
    height_ratio: float = 0.25
    # Horizontal margin as fraction of width.
    side_margin: float = 0.04
    # Bar density factor (0.4..1.0). Lower = wider gaps, less crowded.
    density: float = 0.85
    # Opacity 0..1 of the spectrum overlay.
    opacity: float = 1.0
    # Glow strength 0..1.
    glow: float = 0.6
    # Mirror across horizontal center line.
    mirror: bool = False
    # Move spectrum away from absolute bottom (0..1 of height).
    bottom_offset: float = 0.06
    # Smooth between bars for wave styles.
    smoothness: float = 0.5
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

def _new_canvas(size) -> Image.Image:
    return Image.new("RGBA", size, (0, 0, 0, 0))


def _apply_glow(img: Image.Image, strength: float) -> Image.Image:
    """Add a soft additive glow to ``img``."""
    if strength <= 0.0:
        return img
    radius = 4 + int(20 * strength)
    blurred = img.filter(ImageFilter.GaussianBlur(radius=radius))
    # Multiply alpha down for the glow layer so it adds light, not noise.
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    glow.alpha_composite(blurred)
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.alpha_composite(glow)
    out.alpha_composite(img)
    return out


def _spectrum_region(size, cfg: SpectrumConfig):
    """Return (x0, y0, x1, y1) where the spectrum drawing lives.

    The bottom of the region is always anchored to the bottom of the frame
    (with optional ``bottom_offset``) so bar-style spectrums sit flush at
    the bottom of the video like the user asked.
    """
    w, h = size
    region_h = max(40, int(h * cfg.height_ratio))
    bottom = h - int(h * cfg.bottom_offset)
    top = bottom - region_h
    x_margin = int(w * cfg.side_margin)
    return x_margin, top, w - x_margin, bottom


def _palette_array(palette: str, n: int) -> np.ndarray:
    """Vectorized palette samples for n positions."""
    out = np.zeros((n, 3), dtype=np.uint8)
    if n == 1:
        out[0] = palette_color(palette, 0.5)
    else:
        for i in range(n):
            out[i] = palette_color(palette, i / (n - 1))
    return out


# ---------------------------------------------------------------------------
# Individual styles
# ---------------------------------------------------------------------------

def _style_bars(size, bars, cfg, loudness, beat, t_sec) -> Image.Image:
    """Classic vertical bars anchored to bottom of frame."""
    img = _new_canvas(size)
    draw = ImageDraw.Draw(img, "RGBA")
    x0, y0, x1, y1 = _spectrum_region(size, cfg)
    region_w = x1 - x0
    region_h = y1 - y0
    n = bars.size

    gap_ratio = 0.35 * (1.2 - cfg.density)
    bar_w = region_w / n
    pad = bar_w * gap_ratio
    inner_w = max(1.0, bar_w - pad)
    colors = _palette_array(cfg.palette, n)

    for i in range(n):
        v = float(bars[i])
        if v <= 0.01:
            continue
        bh = max(2.0, v * region_h)
        cx = x0 + i * bar_w + bar_w / 2
        left = cx - inner_w / 2
        right = cx + inner_w / 2
        top = y1 - bh
        col = tuple(colors[i].tolist()) + (int(255 * cfg.opacity),)
        draw.rounded_rectangle([left, top, right, y1], radius=min(8, inner_w / 2),
                               fill=col)
        # bright highlight tip
        tip_col = (255, 255, 255, int(220 * cfg.opacity))
        draw.rounded_rectangle([left, top, right, top + min(4, bh / 4)],
                               radius=min(4, inner_w / 2), fill=tip_col)

    return _apply_glow(img, cfg.glow * 0.7)


def _style_mirror_bars(size, bars, cfg, loudness, beat, t_sec) -> Image.Image:
    img = _new_canvas(size)
    draw = ImageDraw.Draw(img, "RGBA")
    x0, y0, x1, y1 = _spectrum_region(size, cfg)
    region_w = x1 - x0
    region_h = (y1 - y0)
    center_y = (y0 + y1) / 2
    n = bars.size
    gap_ratio = 0.35 * (1.2 - cfg.density)
    bar_w = region_w / n
    pad = bar_w * gap_ratio
    inner_w = max(1.0, bar_w - pad)
    colors = _palette_array(cfg.palette, n)

    for i in range(n):
        v = float(bars[i])
        if v <= 0.01:
            continue
        bh = v * region_h / 2
        cx = x0 + i * bar_w + bar_w / 2
        left = cx - inner_w / 2
        right = cx + inner_w / 2
        col = tuple(colors[i].tolist()) + (int(255 * cfg.opacity),)
        draw.rounded_rectangle([left, center_y - bh, right, center_y + bh],
                               radius=min(8, inner_w / 2), fill=col)
    return _apply_glow(img, cfg.glow * 0.7)


def _style_rounded_bars(size, bars, cfg, loudness, beat, t_sec) -> Image.Image:
    img = _new_canvas(size)
    draw = ImageDraw.Draw(img, "RGBA")
    x0, y0, x1, y1 = _spectrum_region(size, cfg)
    region_w = x1 - x0
    region_h = y1 - y0
    n = bars.size
    bar_w = region_w / n
    inner_w = max(2.0, bar_w * (0.55 + 0.4 * cfg.density))
    colors = _palette_array(cfg.palette, n)
    for i in range(n):
        v = float(bars[i])
        if v <= 0.01:
            continue
        bh = max(inner_w, v * region_h)
        cx = x0 + i * bar_w + bar_w / 2
        col = tuple(colors[i].tolist()) + (int(255 * cfg.opacity),)
        draw.rounded_rectangle([cx - inner_w / 2, y1 - bh,
                                cx + inner_w / 2, y1],
                               radius=inner_w / 2, fill=col)
    return _apply_glow(img, cfg.glow * 0.9)


def _style_wave(size, bars, cfg, loudness, beat, t_sec) -> Image.Image:
    img = _new_canvas(size)
    draw = ImageDraw.Draw(img, "RGBA")
    x0, y0, x1, y1 = _spectrum_region(size, cfg)
    region_w = x1 - x0
    region_h = y1 - y0
    n = bars.size
    pts = []
    for i in range(n):
        v = float(bars[i])
        x = x0 + i * region_w / max(1, n - 1)
        y = y1 - v * region_h
        pts.append((x, y))
    # Bottom polygon for filled wave.
    fill_pts = pts + [(x1, y1), (x0, y1)]
    fill_col = palette_color(cfg.palette, 0.5) + (int(140 * cfg.opacity),)
    draw.polygon(fill_pts, fill=fill_col)
    # Stroke top
    stroke_col = palette_color(cfg.palette, 1.0) + (int(255 * cfg.opacity),)
    draw.line(pts, fill=stroke_col, width=max(2, int(size[1] * 0.004)))
    return _apply_glow(img, cfg.glow)


def _style_mirror_wave(size, bars, cfg, loudness, beat, t_sec) -> Image.Image:
    img = _new_canvas(size)
    draw = ImageDraw.Draw(img, "RGBA")
    x0, y0, x1, y1 = _spectrum_region(size, cfg)
    region_w = x1 - x0
    region_h = (y1 - y0)
    cy = (y0 + y1) / 2
    n = bars.size
    pts_top, pts_bot = [], []
    for i in range(n):
        v = float(bars[i]) * region_h / 2
        x = x0 + i * region_w / max(1, n - 1)
        pts_top.append((x, cy - v))
        pts_bot.append((x, cy + v))
    poly = pts_top + pts_bot[::-1]
    fill_col = palette_color(cfg.palette, 0.5) + (int(160 * cfg.opacity),)
    draw.polygon(poly, fill=fill_col)
    stroke_col = palette_color(cfg.palette, 1.0) + (int(255 * cfg.opacity),)
    draw.line(pts_top, fill=stroke_col, width=2)
    draw.line(pts_bot, fill=stroke_col, width=2)
    return _apply_glow(img, cfg.glow)


def _style_circle_bars(size, bars, cfg, loudness, beat, t_sec) -> Image.Image:
    img = _new_canvas(size)
    draw = ImageDraw.Draw(img, "RGBA")
    w, h = size
    n = bars.size
    cx, cy = w / 2, h / 2
    inner_r = min(w, h) * (0.16 + 0.05 * cfg.density)
    bar_max = min(w, h) * 0.22 * (0.7 + 0.6 * cfg.height_ratio)
    colors = _palette_array(cfg.palette, n)
    # Outer ring
    ring_col = (255, 255, 255, int(120 * cfg.opacity))
    draw.ellipse([cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r],
                 outline=ring_col, width=2)
    for i in range(n):
        v = float(bars[i])
        if v <= 0.01:
            continue
        a = (i / n) * 2 * math.pi - math.pi / 2
        r1 = inner_r
        r2 = inner_r + v * bar_max
        x1, y1 = cx + math.cos(a) * r1, cy + math.sin(a) * r1
        x2, y2 = cx + math.cos(a) * r2, cy + math.sin(a) * r2
        col = tuple(colors[i].tolist()) + (int(255 * cfg.opacity),)
        bar_thick = max(2, int(2 * math.pi * inner_r / n * 0.7))
        draw.line([(x1, y1), (x2, y2)], fill=col, width=bar_thick)
    return _apply_glow(img, cfg.glow)


def _style_dots(size, bars, cfg, loudness, beat, t_sec) -> Image.Image:
    img = _new_canvas(size)
    draw = ImageDraw.Draw(img, "RGBA")
    x0, y0, x1, y1 = _spectrum_region(size, cfg)
    region_w = x1 - x0
    region_h = y1 - y0
    n = bars.size
    bar_w = region_w / n
    dot_r = max(2.0, bar_w * 0.35)
    colors = _palette_array(cfg.palette, n)
    for i in range(n):
        v = float(bars[i])
        if v <= 0.005:
            continue
        cx = x0 + i * bar_w + bar_w / 2
        steps = max(2, int(v * region_h / (dot_r * 2.5)))
        for s in range(steps):
            yy = y1 - s * (dot_r * 2.5)
            alpha = int(255 * (1.0 - s / max(1, steps)) * cfg.opacity)
            col = tuple(colors[i].tolist()) + (alpha,)
            draw.ellipse([cx - dot_r, yy - dot_r, cx + dot_r, yy + dot_r], fill=col)
    return _apply_glow(img, cfg.glow)


def _style_glow_bars(size, bars, cfg, loudness, beat, t_sec) -> Image.Image:
    cfg2 = SpectrumConfig(**{**cfg.__dict__, "glow": min(1.0, cfg.glow + 0.4)})
    return _style_bars(size, bars, cfg2, loudness, beat, t_sec)


def _style_neon_wave(size, bars, cfg, loudness, beat, t_sec) -> Image.Image:
    img = _new_canvas(size)
    draw = ImageDraw.Draw(img, "RGBA")
    x0, y0, x1, y1 = _spectrum_region(size, cfg)
    region_w = x1 - x0
    region_h = y1 - y0
    n = bars.size
    pts = []
    for i in range(n):
        v = float(bars[i])
        x = x0 + i * region_w / max(1, n - 1)
        y = y1 - v * region_h
        pts.append((x, y))
    stroke_col = palette_color(cfg.palette, 1.0) + (int(255 * cfg.opacity),)
    draw.line(pts, fill=stroke_col, width=max(3, int(size[1] * 0.006)))
    return _apply_glow(img, max(0.7, cfg.glow))


def _style_pulse_ring(size, bars, cfg, loudness, beat, t_sec) -> Image.Image:
    img = _new_canvas(size)
    draw = ImageDraw.Draw(img, "RGBA")
    w, h = size
    cx, cy = w / 2, h / 2
    base_r = min(w, h) * 0.18
    n = bars.size
    rings = 5
    for r_idx in range(rings):
        idx = int((r_idx + 1) / (rings + 1) * n)
        v = float(bars[idx])
        radius = base_r + r_idx * 30 + v * 120 + loudness * 60
        col = palette_color(cfg.palette, r_idx / max(1, rings - 1)) + (
            int(180 * cfg.opacity * (1 - r_idx / rings)),
        )
        draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius],
                     outline=col, width=max(2, int(min(w, h) * 0.004)))
    return _apply_glow(img, cfg.glow)


def _style_hexagon(size, bars, cfg, loudness, beat, t_sec) -> Image.Image:
    img = _new_canvas(size)
    draw = ImageDraw.Draw(img, "RGBA")
    x0, y0, x1, y1 = _spectrum_region(size, cfg)
    region_w = x1 - x0
    region_h = y1 - y0
    n = bars.size
    bar_w = region_w / n
    colors = _palette_array(cfg.palette, n)
    for i in range(n):
        v = float(bars[i])
        if v <= 0.01:
            continue
        cx = x0 + i * bar_w + bar_w / 2
        size_hex = bar_w * 0.45
        rows = max(1, int(v * region_h / (size_hex * 1.7)))
        for r in range(rows):
            yy = y1 - r * size_hex * 1.7 - size_hex
            angle_off = (math.pi / 6) if (r % 2) else 0
            pts = []
            for k in range(6):
                a = angle_off + k * math.pi / 3
                pts.append((cx + math.cos(a) * size_hex,
                            yy + math.sin(a) * size_hex))
            alpha = int(255 * (1 - r / max(1, rows)) * cfg.opacity)
            col = tuple(colors[i].tolist()) + (alpha,)
            draw.polygon(pts, fill=col)
    return _apply_glow(img, cfg.glow * 0.8)


def _style_3d_bars(size, bars, cfg, loudness, beat, t_sec) -> Image.Image:
    img = _new_canvas(size)
    draw = ImageDraw.Draw(img, "RGBA")
    x0, y0, x1, y1 = _spectrum_region(size, cfg)
    region_w = x1 - x0
    region_h = y1 - y0
    n = bars.size
    bar_w = region_w / n
    inner_w = max(2.0, bar_w * (0.6 + 0.3 * cfg.density))
    depth = max(4.0, bar_w * 0.5)
    colors = _palette_array(cfg.palette, n)
    for i in range(n):
        v = float(bars[i])
        if v <= 0.01:
            continue
        bh = max(2.0, v * region_h)
        cx = x0 + i * bar_w + bar_w / 2
        l = cx - inner_w / 2
        r = cx + inner_w / 2
        t = y1 - bh
        # side face
        side_col = tuple(int(c * 0.5) for c in colors[i].tolist()) + (int(220 * cfg.opacity),)
        draw.polygon([(r, t), (r + depth, t - depth * 0.5),
                      (r + depth, y1 - depth * 0.5), (r, y1)], fill=side_col)
        # top face
        top_col = tuple(int(min(255, c * 1.2)) for c in colors[i].tolist()) + (int(255 * cfg.opacity),)
        draw.polygon([(l, t), (r, t), (r + depth, t - depth * 0.5),
                      (l + depth, t - depth * 0.5)], fill=top_col)
        # front face
        front_col = tuple(colors[i].tolist()) + (int(255 * cfg.opacity),)
        draw.rectangle([l, t, r, y1], fill=front_col)
    return _apply_glow(img, cfg.glow * 0.5)


def _style_particles(size, bars, cfg, loudness, beat, t_sec) -> Image.Image:
    img = _new_canvas(size)
    draw = ImageDraw.Draw(img, "RGBA")
    x0, y0, x1, y1 = _spectrum_region(size, cfg)
    region_w = x1 - x0
    region_h = y1 - y0
    n = bars.size
    rng = np.random.default_rng(int(t_sec * 30) & 0xFFFFFFFF)
    colors = _palette_array(cfg.palette, n)
    for i in range(n):
        v = float(bars[i])
        if v <= 0.01:
            continue
        cx = x0 + i * region_w / n + region_w / n / 2
        count = int(v * 6)
        for _ in range(count):
            yy = y1 - rng.uniform(0, v * region_h)
            jitter_x = rng.uniform(-region_w / n * 0.35, region_w / n * 0.35)
            r_dot = rng.uniform(1.4, 3.6)
            alpha = int(255 * (yy_norm := (y1 - yy) / max(1, region_h)) * cfg.opacity)
            col = tuple(colors[i].tolist()) + (max(40, alpha),)
            draw.ellipse([cx + jitter_x - r_dot, yy - r_dot,
                          cx + jitter_x + r_dot, yy + r_dot], fill=col)
    return _apply_glow(img, cfg.glow + 0.1)


def _style_ribbon(size, bars, cfg, loudness, beat, t_sec) -> Image.Image:
    """Ribbon/flowing band whose thickness modulates with audio."""
    img = _new_canvas(size)
    draw = ImageDraw.Draw(img, "RGBA")
    x0, y0, x1, y1 = _spectrum_region(size, cfg)
    region_w = x1 - x0
    region_h = y1 - y0
    n = bars.size
    cy = (y0 + y1) / 2
    pts_top, pts_bot = [], []
    for i in range(n):
        v = float(bars[i])
        x = x0 + i * region_w / max(1, n - 1)
        thick = (0.15 + v * 0.9) * region_h / 2
        wave_off = math.sin(t_sec * 1.5 + i * 0.18) * region_h * 0.08
        pts_top.append((x, cy - thick + wave_off))
        pts_bot.append((x, cy + thick + wave_off))
    poly = pts_top + pts_bot[::-1]
    fill = palette_color(cfg.palette, 0.4) + (int(180 * cfg.opacity),)
    draw.polygon(poly, fill=fill)
    edge = palette_color(cfg.palette, 1.0) + (int(220 * cfg.opacity),)
    draw.line(pts_top, fill=edge, width=2)
    draw.line(pts_bot, fill=edge, width=2)
    return _apply_glow(img, cfg.glow)


def _style_fire(size, bars, cfg, loudness, beat, t_sec) -> Image.Image:
    """Vertical flame style: bars with strong glow and warm palette feel."""
    img = _new_canvas(size)
    draw = ImageDraw.Draw(img, "RGBA")
    x0, y0, x1, y1 = _spectrum_region(size, cfg)
    region_w = x1 - x0
    region_h = y1 - y0
    n = bars.size
    bar_w = region_w / n
    colors = _palette_array(cfg.palette, n)
    for i in range(n):
        v = float(bars[i])
        if v <= 0.01:
            continue
        cx = x0 + i * bar_w + bar_w / 2
        bh = v * region_h
        # Draw a few stacked ellipses to simulate flame shape.
        steps = 6
        for s in range(steps):
            f = s / (steps - 1)
            yy = y1 - f * bh
            ww = bar_w * (0.85 - 0.55 * f) * (0.6 + 0.6 * v)
            hh = bh * 0.18 + 2
            alpha = int(255 * (1 - f) * cfg.opacity)
            col = palette_color(cfg.palette, f) + (alpha,)
            draw.ellipse([cx - ww / 2, yy - hh / 2, cx + ww / 2, yy + hh / 2], fill=col)
    return _apply_glow(img, max(0.7, cfg.glow))


def _style_polygon(size, bars, cfg, loudness, beat, t_sec) -> Image.Image:
    """Star/polygon morphing with audio energy."""
    img = _new_canvas(size)
    draw = ImageDraw.Draw(img, "RGBA")
    w, h = size
    cx, cy = w / 2, h / 2
    base_r = min(w, h) * 0.16
    n = bars.size
    pts = []
    for i in range(n):
        a = (i / n) * 2 * math.pi - math.pi / 2 + t_sec * 0.4
        v = float(bars[i])
        r = base_r + v * min(w, h) * 0.18 + loudness * 30
        pts.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
    col = palette_color(cfg.palette, 0.6) + (int(150 * cfg.opacity),)
    draw.polygon(pts, fill=col)
    edge = palette_color(cfg.palette, 1.0) + (int(220 * cfg.opacity),)
    for i in range(len(pts)):
        draw.line([pts[i], pts[(i + 1) % len(pts)]], fill=edge, width=2)
    return _apply_glow(img, cfg.glow + 0.1)


def _style_liquid(size, bars, cfg, loudness, beat, t_sec) -> Image.Image:
    """Liquid mercury-like wavy blob along bottom of frame."""
    img = _new_canvas(size)
    draw = ImageDraw.Draw(img, "RGBA")
    x0, y0, x1, y1 = _spectrum_region(size, cfg)
    region_w = x1 - x0
    region_h = y1 - y0
    n = bars.size
    pts = []
    for i in range(n):
        x = x0 + i * region_w / max(1, n - 1)
        v = float(bars[i])
        y = y1 - (0.25 + 0.7 * v) * region_h
        y += math.sin(t_sec * 2 + i * 0.4) * region_h * 0.05
        pts.append((x, y))
    fill_pts = pts + [(x1, y1), (x0, y1)]
    col = palette_color(cfg.palette, 0.7) + (int(200 * cfg.opacity),)
    draw.polygon(fill_pts, fill=col)
    return _apply_glow(img, max(0.5, cfg.glow))


def _style_galaxy(size, bars, cfg, loudness, beat, t_sec) -> Image.Image:
    """Rotating spiral arms reactive to the spectrum."""
    img = _new_canvas(size)
    draw = ImageDraw.Draw(img, "RGBA")
    w, h = size
    cx, cy = w / 2, h / 2
    arms = 4
    n = bars.size
    for arm in range(arms):
        for i in range(n):
            v = float(bars[i])
            r = (i / n) * min(w, h) * 0.4 + 30 + v * 60
            a = (i / n) * math.pi * 2 + arm * (2 * math.pi / arms) + t_sec * 0.5
            x = cx + math.cos(a) * r
            y = cy + math.sin(a) * r
            rad = 2 + v * 5
            col = palette_color(cfg.palette, i / max(1, n - 1)) + (int(220 * cfg.opacity),)
            draw.ellipse([x - rad, y - rad, x + rad, y + rad], fill=col)
    return _apply_glow(img, max(0.6, cfg.glow))


STYLES: Dict[str, Callable] = {
    "Bars":          _style_bars,
    "Mirror Bars":   _style_mirror_bars,
    "Rounded Bars":  _style_rounded_bars,
    "Glow Bars":     _style_glow_bars,
    "3D Bars":       _style_3d_bars,
    "Wave":          _style_wave,
    "Mirror Wave":   _style_mirror_wave,
    "Neon Wave":     _style_neon_wave,
    "Ribbon":        _style_ribbon,
    "Liquid":        _style_liquid,
    "Dots":          _style_dots,
    "Particles":     _style_particles,
    "Fire":          _style_fire,
    "Circle Bars":   _style_circle_bars,
    "Pulse Ring":    _style_pulse_ring,
    "Hexagon":       _style_hexagon,
    "Polygon":       _style_polygon,
    "Galaxy":        _style_galaxy,
}


def list_styles() -> List[str]:
    return list(STYLES.keys())


def render_frame(size, bars, cfg: SpectrumConfig, loudness: float,
                 beat: float, t_sec: float) -> Image.Image:
    """Render a single spectrum overlay frame as an RGBA PIL image."""
    fn = STYLES.get(cfg.style, _style_bars)
    return fn(size, bars, cfg, loudness, beat, t_sec)
