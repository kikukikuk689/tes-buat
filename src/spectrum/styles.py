"""15+ gaya spectrum visualizer.

Setiap style mengimplementasikan :meth:`draw(im, t, frame_idx, bands, env)` di mana:
- ``im`` adalah ``PIL.Image`` RGBA target (in-place modify).
- ``t`` waktu dalam detik.
- ``frame_idx`` indeks frame video.
- ``bands`` numpy array shape (n_bands,) float32 0..~1.
- ``env`` skalar 0..1 (loudness envelope keseluruhan).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

# ============================================================
# Palettes (gradient warna)
# ============================================================

Palette = List[Tuple[int, int, int]]

_PALETTES: Dict[str, Palette] = {
    "Aurora":        [(72, 219, 251), (95, 39, 205), (255, 121, 198)],
    "Sunset":        [(255, 154, 0), (255, 87, 87), (155, 89, 182)],
    "Ocean":         [(0, 180, 219), (0, 131, 176), (51, 80, 158)],
    "Mint":          [(0, 245, 212), (28, 224, 192), (52, 235, 152)],
    "Lava":          [(255, 195, 0), (255, 87, 34), (231, 76, 60)],
    "Galaxy":        [(99, 102, 241), (192, 38, 211), (236, 72, 153)],
    "Neon Pink":     [(255, 0, 128), (236, 72, 153), (244, 114, 182)],
    "Neon Blue":     [(0, 240, 255), (59, 130, 246), (37, 99, 235)],
    "Gold":          [(255, 215, 0), (255, 165, 0), (244, 154, 4)],
    "Forest":        [(168, 230, 207), (60, 179, 113), (34, 139, 34)],
    "Cherry":        [(255, 182, 193), (255, 105, 180), (220, 20, 60)],
    "Ice":           [(240, 248, 255), (135, 206, 235), (70, 130, 180)],
    "Rainbow":       [(255, 0, 0), (255, 165, 0), (255, 255, 0),
                      (0, 255, 0), (0, 191, 255), (138, 43, 226)],
    "White":         [(255, 255, 255), (220, 220, 220), (255, 255, 255)],
    "Soft Pastel":   [(255, 209, 220), (255, 234, 167), (162, 217, 245)],
}


def list_palettes() -> List[str]:
    return list(_PALETTES.keys())


def get_palette(name: str) -> Palette:
    return _PALETTES.get(name, _PALETTES["Aurora"])


def _lerp(a: Tuple[int, int, int], b: Tuple[int, int, int], t: float) -> Tuple[int, int, int]:
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def _palette_at(palette: Palette, t: float) -> Tuple[int, int, int]:
    """t in [0,1] -> color along palette."""
    if not palette:
        return (255, 255, 255)
    if len(palette) == 1:
        return palette[0]
    t = max(0.0, min(1.0, t))
    seg = t * (len(palette) - 1)
    i = int(seg)
    if i >= len(palette) - 1:
        return palette[-1]
    return _lerp(palette[i], palette[i + 1], seg - i)


# ============================================================
# Config
# ============================================================

@dataclass
class SpectrumConfig:
    style: str = "Bars"
    palette: str = "Aurora"
    n_bands: int = 64
    height_ratio: float = 0.28      # tinggi spectrum relatif tinggi video
    density: float = 1.0            # kepadatan bar; <1 = lebih jarang
    glow: float = 1.0               # intensitas glow 0..2
    bottom_padding: int = 18        # jarak bar bottom dari bottom video
    line_width: int = 4
    smoothness: float = 0.55
    rotation_speed: float = 0.0     # untuk style circular (rev/sec)
    base_alpha: int = 235

    def effective_bands(self) -> int:
        """Jumlah band yang ditampilkan setelah density factor."""
        eff = max(8, int(self.n_bands * max(0.2, min(1.5, self.density))))
        return eff


# ============================================================
# Helper drawing primitives
# ============================================================

def _gradient_rect(draw: ImageDraw.ImageDraw,
                   x0: int, y0: int, x1: int, y1: int,
                   palette: Palette,
                   alpha: int = 235,
                   vertical: bool = True) -> None:
    """Draw a smooth vertical gradient bar (Pillow lacks native gradient)."""
    if x1 <= x0 or y1 <= y0:
        return
    if vertical:
        h = y1 - y0
        steps = max(1, h)
        for i in range(steps):
            t = i / max(1, steps - 1)
            c = _palette_at(palette, t)
            draw.line([(x0, y0 + i), (x1, y0 + i)], fill=(*c, alpha))
    else:
        w = x1 - x0
        steps = max(1, w)
        for i in range(steps):
            t = i / max(1, steps - 1)
            c = _palette_at(palette, t)
            draw.line([(x0 + i, y0), (x0 + i, y1)], fill=(*c, alpha))


def _resample_bands(bands: np.ndarray, target: int) -> np.ndarray:
    n = bands.shape[0]
    if n == target:
        return bands
    xs = np.linspace(0, n - 1, target)
    return np.interp(xs, np.arange(n), bands).astype(np.float32)


def _composite_glow(im: Image.Image, layer: Image.Image, glow: float) -> None:
    """Add glow by alpha-compositing a blurred copy of `layer` onto `im`."""
    if glow <= 0.01:
        im.alpha_composite(layer)
        return
    radius = int(2 + 6 * glow)
    blurred = layer.filter(ImageFilter.GaussianBlur(radius))
    # boost alpha
    a = np.asarray(blurred, dtype=np.uint8).copy()
    a[..., 3] = np.clip(a[..., 3].astype(np.int32) * (0.7 + 0.6 * glow), 0, 255).astype(np.uint8)
    blurred = Image.fromarray(a, "RGBA")
    im.alpha_composite(blurred)
    im.alpha_composite(layer)


# ============================================================
# Style implementations
# ============================================================

class _StyleBase:
    name = "Base"
    description = ""

    def __init__(self, cfg: SpectrumConfig):
        self.cfg = cfg
        self.palette = get_palette(cfg.palette)

    def draw(self, im: Image.Image, t: float, frame_idx: int,
             bands: np.ndarray, env: float) -> None:  # pragma: no cover - abstract
        raise NotImplementedError


# --- 1. Classic Bars (bottom-aligned) ---
class BarsStyle(_StyleBase):
    name = "Bars"

    def draw(self, im, t, frame_idx, bands, env):
        W, H = im.size
        cfg = self.cfg
        n = cfg.effective_bands()
        b = _resample_bands(bands, n)

        max_h = int(H * cfg.height_ratio)
        gap = max(1, int(W / (n * 6)))
        total_gap = gap * (n + 1)
        bw = max(1, (W - total_gap) // n)
        base_y = H - cfg.bottom_padding
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)

        x = gap
        for i in range(n):
            bh = int(b[i] * max_h)
            if bh < 2:
                bh = 2
            y0 = base_y - bh
            y1 = base_y
            # rounded top
            radius = min(bw // 2, 8)
            try:
                d.rounded_rectangle([x, y0, x + bw, y1], radius=radius,
                                    fill=(*_palette_at(self.palette, i / max(1, n - 1)),
                                          cfg.base_alpha))
            except AttributeError:
                d.rectangle([x, y0, x + bw, y1],
                            fill=(*_palette_at(self.palette, i / max(1, n - 1)),
                                  cfg.base_alpha))
            x += bw + gap

        _composite_glow(im, layer, cfg.glow * 0.8)


# --- 2. Gradient Bars (vertical color top->bottom) ---
class GradientBarsStyle(_StyleBase):
    name = "Gradient Bars"

    def draw(self, im, t, frame_idx, bands, env):
        W, H = im.size
        cfg = self.cfg
        n = cfg.effective_bands()
        b = _resample_bands(bands, n)
        max_h = int(H * cfg.height_ratio)
        gap = max(1, int(W / (n * 8)))
        total_gap = gap * (n + 1)
        bw = max(1, (W - total_gap) // n)
        base_y = H - cfg.bottom_padding
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)

        x = gap
        for i in range(n):
            bh = int(b[i] * max_h)
            if bh < 2:
                bh = 2
            y0 = base_y - bh
            _gradient_rect(d, x, y0, x + bw, base_y, self.palette,
                           alpha=cfg.base_alpha)
            x += bw + gap

        _composite_glow(im, layer, cfg.glow)


# --- 3. Mirror Bars (mirrored top + bottom) ---
class MirrorBarsStyle(_StyleBase):
    name = "Mirror Bars"

    def draw(self, im, t, frame_idx, bands, env):
        W, H = im.size
        cfg = self.cfg
        n = cfg.effective_bands()
        b = _resample_bands(bands, n)
        max_h = int(H * cfg.height_ratio * 0.55)
        gap = max(1, int(W / (n * 6)))
        total_gap = gap * (n + 1)
        bw = max(1, (W - total_gap) // n)
        cy = H - cfg.bottom_padding - max_h
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)

        x = gap
        for i in range(n):
            bh = int(b[i] * max_h)
            if bh < 2:
                bh = 2
            color = _palette_at(self.palette, i / max(1, n - 1))
            radius = min(bw // 2, 8)
            try:
                d.rounded_rectangle([x, cy - bh, x + bw, cy], radius=radius,
                                    fill=(*color, cfg.base_alpha))
                d.rounded_rectangle([x, cy, x + bw, cy + bh], radius=radius,
                                    fill=(*color, int(cfg.base_alpha * 0.65)))
            except AttributeError:
                d.rectangle([x, cy - bh, x + bw, cy], fill=(*color, cfg.base_alpha))
                d.rectangle([x, cy, x + bw, cy + bh],
                            fill=(*color, int(cfg.base_alpha * 0.65)))
            x += bw + gap
        _composite_glow(im, layer, cfg.glow)


# --- 4. Smooth Wave (filled area, bottom-aligned) ---
class WaveAreaStyle(_StyleBase):
    name = "Smooth Wave"

    def draw(self, im, t, frame_idx, bands, env):
        W, H = im.size
        cfg = self.cfg
        n = max(40, cfg.effective_bands())
        b = _resample_bands(bands, n)
        max_h = int(H * cfg.height_ratio)
        base_y = H - cfg.bottom_padding

        # Build polyline points
        pts: List[Tuple[float, float]] = []
        # Catmull-Rom-ish smoothing via interpolation
        xs = np.linspace(0, W, n)
        ys = base_y - b * max_h
        # Cubic-ish smoothing
        for i in range(n):
            pts.append((xs[i], ys[i]))
        # Build polygon area
        polygon = [(0, base_y)] + pts + [(W, base_y)]

        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)

        # Build full-frame gradient layer
        grad = Image.new("RGBA", im.size, (0, 0, 0, 0))
        gd = ImageDraw.Draw(grad)
        top_y = max(0, base_y - max_h - 4)
        for yy in range(top_y, base_y + 1):
            tt = 1.0 - (yy - top_y) / max(1, base_y - top_y)
            c = _palette_at(self.palette, tt)
            gd.line([(0, yy), (W, yy)], fill=(*c, int(180 * (0.4 + 0.6 * tt))))
        # Mask via polygon
        mask = Image.new("L", im.size, 0)
        md = ImageDraw.Draw(mask)
        md.polygon(polygon, fill=255)
        # Multiply existing alpha with polygon mask so the inner alpha gradient is preserved.
        from PIL import ImageChops
        cur_alpha = grad.split()[-1]
        new_alpha = ImageChops.multiply(cur_alpha, mask)
        grad.putalpha(new_alpha)
        layer.alpha_composite(grad)
        # outline
        d.line(pts, fill=(*_palette_at(self.palette, 0.5), cfg.base_alpha),
               width=cfg.line_width, joint="curve")

        _composite_glow(im, layer, cfg.glow)


# --- 5. Oscilloscope Line ---
class OscilloscopeStyle(_StyleBase):
    name = "Oscilloscope"

    def draw(self, im, t, frame_idx, bands, env):
        W, H = im.size
        cfg = self.cfg
        n = max(80, cfg.effective_bands())
        b = _resample_bands(bands, n)
        amp = int(H * cfg.height_ratio * 0.5)
        cy = H - cfg.bottom_padding - amp
        # symmetric line via sign per index
        phase = t * 2.0
        xs = np.linspace(0, W, n)
        sine = np.sin(np.linspace(0, math.pi * 6, n) + phase)
        ys = cy - sine * b * amp
        pts = list(zip(xs.tolist(), ys.tolist()))
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        c = _palette_at(self.palette, 0.5)
        d.line(pts, fill=(*c, cfg.base_alpha), width=cfg.line_width, joint="curve")
        _composite_glow(im, layer, cfg.glow)


# --- 6. Circular Spectrum ---
class CircularStyle(_StyleBase):
    name = "Circular"

    def draw(self, im, t, frame_idx, bands, env):
        W, H = im.size
        cfg = self.cfg
        n = cfg.effective_bands()
        b = _resample_bands(bands, n)
        cx, cy = W // 2, int(H * 0.5)
        r0 = int(min(W, H) * 0.18)
        max_h = int(min(W, H) * cfg.height_ratio * 0.7)
        rot = t * cfg.rotation_speed * 2 * math.pi
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)

        for i in range(n):
            theta = rot + (2 * math.pi * i / n) - math.pi / 2
            length = r0 + int(b[i] * max_h)
            x0 = cx + math.cos(theta) * r0
            y0 = cy + math.sin(theta) * r0
            x1 = cx + math.cos(theta) * length
            y1 = cy + math.sin(theta) * length
            c = _palette_at(self.palette, i / max(1, n - 1))
            d.line([(x0, y0), (x1, y1)], fill=(*c, cfg.base_alpha),
                   width=max(2, cfg.line_width - 1))

        # inner ring
        d.ellipse([cx - r0, cy - r0, cx + r0, cy + r0],
                  outline=(*_palette_at(self.palette, env), 200),
                  width=2)
        _composite_glow(im, layer, cfg.glow)


# --- 7. Pulse Rings (concentric expanding) ---
class PulseRingsStyle(_StyleBase):
    name = "Pulse Rings"

    def draw(self, im, t, frame_idx, bands, env):
        W, H = im.size
        cfg = self.cfg
        n = 6
        b = _resample_bands(bands, n)
        cx, cy = W // 2, int(H * 0.55)
        max_r = int(min(W, H) * 0.45)
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        for i in range(n):
            phase = ((t * (0.4 + 0.15 * i)) % 1.0)
            r = int(max_r * phase * (0.6 + b[i] * 0.8))
            alpha = int(180 * (1.0 - phase))
            c = _palette_at(self.palette, i / max(1, n - 1))
            d.ellipse([cx - r, cy - r, cx + r, cy + r],
                      outline=(*c, alpha), width=max(2, cfg.line_width))
        _composite_glow(im, layer, cfg.glow)


# --- 8. Particle Bars (dots stacked) ---
class ParticleBarsStyle(_StyleBase):
    name = "Particle Bars"

    def draw(self, im, t, frame_idx, bands, env):
        W, H = im.size
        cfg = self.cfg
        n = max(32, cfg.effective_bands())
        b = _resample_bands(bands, n)
        max_h = int(H * cfg.height_ratio)
        base_y = H - cfg.bottom_padding
        gap = max(2, int(W / (n * 6)))
        bw = max(2, (W - gap * (n + 1)) // n)
        step = max(4, bw)
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        x = gap
        for i in range(n):
            bh = int(b[i] * max_h)
            dots = max(1, bh // step)
            for k in range(dots):
                y = base_y - k * step - step // 2
                tcol = (i / max(1, n - 1) * 0.5) + (k / max(1, dots - 1)) * 0.5
                c = _palette_at(self.palette, tcol)
                r = bw // 2
                d.ellipse([x, y - r, x + bw, y + r], fill=(*c, cfg.base_alpha))
            x += bw + gap
        _composite_glow(im, layer, cfg.glow)


# --- 9. Neon Strip (glowing line w/ vertical ticks) ---
class NeonStripStyle(_StyleBase):
    name = "Neon Strip"

    def draw(self, im, t, frame_idx, bands, env):
        W, H = im.size
        cfg = self.cfg
        n = max(80, cfg.effective_bands())
        b = _resample_bands(bands, n)
        max_h = int(H * cfg.height_ratio * 0.7)
        base_y = H - cfg.bottom_padding
        xs = np.linspace(0, W, n)
        ys = base_y - b * max_h
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        # baseline
        d.line([(0, base_y), (W, base_y)],
               fill=(*_palette_at(self.palette, 0.5), 80), width=2)
        # main spectral line
        c0 = _palette_at(self.palette, 0.3)
        c1 = _palette_at(self.palette, 0.9)
        d.line(list(zip(xs.tolist(), ys.tolist())),
               fill=(*c1, cfg.base_alpha),
               width=max(2, cfg.line_width), joint="curve")
        # vertical ticks
        for i in range(0, n, max(1, n // 32)):
            d.line([(xs[i], base_y), (xs[i], ys[i])],
                   fill=(*c0, 160), width=1)
        _composite_glow(im, layer, max(0.8, cfg.glow))


# --- 10. Liquid Wave (multi-layered translucent sine) ---
class LiquidWaveStyle(_StyleBase):
    name = "Liquid Wave"

    def draw(self, im, t, frame_idx, bands, env):
        W, H = im.size
        cfg = self.cfg
        max_h = int(H * cfg.height_ratio)
        base_y = H - cfg.bottom_padding
        n = 240
        xs = np.linspace(0, W, n)
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)

        # Use env to modulate amplitude
        amp = max_h * (0.4 + 0.6 * env)
        for layer_i, (freq, phase, alpha, c_t) in enumerate(
            [(1.5, 0.0, 100, 0.2),
             (2.3, 1.0, 130, 0.55),
             (3.1, 2.0, 160, 0.85)]
        ):
            ys = base_y - amp * np.sin(np.linspace(0, math.pi * freq, n) + t * 1.5 + phase)
            pts = [(0, H)] + list(zip(xs.tolist(), ys.tolist())) + [(W, H)]
            c = _palette_at(self.palette, c_t)
            d.polygon(pts, fill=(*c, alpha))
        _composite_glow(im, layer, cfg.glow * 0.6)


# --- 11. Wireframe Mountains (filled + outline) ---
class MountainStyle(_StyleBase):
    name = "Mountain"

    def draw(self, im, t, frame_idx, bands, env):
        W, H = im.size
        cfg = self.cfg
        n = max(40, cfg.effective_bands())
        b = _resample_bands(bands, n)
        max_h = int(H * cfg.height_ratio)
        base_y = H - cfg.bottom_padding
        xs = np.linspace(0, W, n)
        ys = base_y - b * max_h
        pts = list(zip(xs.tolist(), ys.tolist()))
        poly = [(0, base_y)] + pts + [(W, base_y)]

        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        # filled translucent
        c = _palette_at(self.palette, 0.5)
        d.polygon(poly, fill=(*c, 90))
        # outline gradient: draw segments with palette
        for i in range(len(pts) - 1):
            tc = i / max(1, len(pts) - 2)
            col = _palette_at(self.palette, tc)
            d.line([pts[i], pts[i + 1]], fill=(*col, cfg.base_alpha),
                   width=cfg.line_width)
        _composite_glow(im, layer, cfg.glow)


# --- 12. Block Grid (LED matrix) ---
class BlockGridStyle(_StyleBase):
    name = "Block Grid"

    def draw(self, im, t, frame_idx, bands, env):
        W, H = im.size
        cfg = self.cfg
        n = max(24, cfg.effective_bands() // 2)
        b = _resample_bands(bands, n)
        max_h = int(H * cfg.height_ratio)
        base_y = H - cfg.bottom_padding
        gap = max(2, int(W / (n * 7)))
        bw = max(3, (W - gap * (n + 1)) // n)
        cell_h = bw  # square cells
        rows = max(4, max_h // cell_h)
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        x = gap
        for i in range(n):
            level = int(b[i] * rows)
            for r in range(level):
                y = base_y - (r + 1) * cell_h - r * 1
                c = _palette_at(self.palette, r / max(1, rows - 1))
                d.rectangle([x, y, x + bw, y + cell_h - 1], fill=(*c, cfg.base_alpha))
            x += bw + gap
        _composite_glow(im, layer, cfg.glow * 0.7)


# --- 13. Radial Bars (centered, fan up) ---
class RadialBarsStyle(_StyleBase):
    name = "Radial Bars"

    def draw(self, im, t, frame_idx, bands, env):
        W, H = im.size
        cfg = self.cfg
        n = max(36, cfg.effective_bands())
        b = _resample_bands(bands, n)
        cx = W // 2
        cy = H - cfg.bottom_padding
        max_h = int(H * cfg.height_ratio * 1.25)
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        spread = math.radians(140)
        for i in range(n):
            tt = i / max(1, n - 1)
            theta = -math.pi / 2 - spread / 2 + tt * spread
            length = int(b[i] * max_h)
            x1 = cx + math.cos(theta) * length
            y1 = cy + math.sin(theta) * length
            c = _palette_at(self.palette, tt)
            d.line([(cx, cy), (x1, y1)], fill=(*c, cfg.base_alpha),
                   width=max(2, cfg.line_width))
        _composite_glow(im, layer, cfg.glow)


# --- 14. Galaxy Spiral ---
class GalaxySpiralStyle(_StyleBase):
    name = "Galaxy Spiral"

    def draw(self, im, t, frame_idx, bands, env):
        W, H = im.size
        cfg = self.cfg
        n = max(80, cfg.effective_bands() * 2)
        b = _resample_bands(bands, n)
        cx, cy = W // 2, int(H * 0.55)
        max_r = int(min(W, H) * (0.32 + 0.1 * env))
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        rot = t * 0.4 + cfg.rotation_speed * t
        for arm in range(3):
            for i in range(n):
                tt = i / n
                ang = rot + arm * 2 * math.pi / 3 + tt * math.pi * 3.0
                r = tt * max_r
                x = cx + math.cos(ang) * r
                y = cy + math.sin(ang) * r
                col = _palette_at(self.palette, tt)
                sz = 1 + b[i] * 4
                d.ellipse([x - sz, y - sz, x + sz, y + sz],
                          fill=(*col, int(180 * (0.6 + 0.4 * b[i]))))
        _composite_glow(im, layer, max(1.0, cfg.glow))


# --- 15. Floating Curve (3 curves stacked) ---
class FloatingCurveStyle(_StyleBase):
    name = "Floating Curve"

    def draw(self, im, t, frame_idx, bands, env):
        W, H = im.size
        cfg = self.cfg
        n = max(60, cfg.effective_bands())
        b = _resample_bands(bands, n)
        max_h = int(H * cfg.height_ratio * 0.45)
        base_y = H - cfg.bottom_padding
        xs = np.linspace(0, W, n)
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        for k in range(3):
            offset = k * (max_h // 3 + 4)
            ys = base_y - offset - (b * max_h * (0.4 + 0.3 * k))
            c = _palette_at(self.palette, k / 2.0)
            d.line(list(zip(xs.tolist(), ys.tolist())),
                   fill=(*c, max(120, cfg.base_alpha - k * 30)),
                   width=cfg.line_width, joint="curve")
        _composite_glow(im, layer, cfg.glow)


# --- 16. Ring Spectrum (closed ring) ---
class RingStyle(_StyleBase):
    name = "Ring"

    def draw(self, im, t, frame_idx, bands, env):
        W, H = im.size
        cfg = self.cfg
        n = max(60, cfg.effective_bands())
        b = _resample_bands(bands, n)
        cx, cy = W // 2, int(H * 0.5)
        r0 = int(min(W, H) * 0.22)
        max_h = int(min(W, H) * cfg.height_ratio * 0.5)
        rot = t * (cfg.rotation_speed or 0.1) * 2 * math.pi
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)

        pts_outer: List[Tuple[float, float]] = []
        for i in range(n + 1):
            theta = rot + 2 * math.pi * i / n
            r = r0 + b[i % n] * max_h
            x = cx + math.cos(theta) * r
            y = cy + math.sin(theta) * r
            pts_outer.append((x, y))
        c = _palette_at(self.palette, 0.6)
        d.line(pts_outer, fill=(*c, cfg.base_alpha), width=cfg.line_width, joint="curve")
        d.ellipse([cx - r0, cy - r0, cx + r0, cy + r0],
                  outline=(*_palette_at(self.palette, 0.2), 160), width=2)
        _composite_glow(im, layer, cfg.glow)


# --- 17. Stacked Dots (skyline) ---
class StackedDotsStyle(_StyleBase):
    name = "Stacked Dots"

    def draw(self, im, t, frame_idx, bands, env):
        W, H = im.size
        cfg = self.cfg
        n = max(40, cfg.effective_bands())
        b = _resample_bands(bands, n)
        max_h = int(H * cfg.height_ratio)
        base_y = H - cfg.bottom_padding
        gap = max(2, int(W / (n * 8)))
        bw = max(3, (W - gap * (n + 1)) // n)
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        x = gap
        for i in range(n):
            bh = int(b[i] * max_h)
            d.ellipse([x, base_y - bh, x + bw, base_y - bh + bw],
                      fill=(*_palette_at(self.palette, i / max(1, n - 1)), cfg.base_alpha))
            # cap dot
            d.ellipse([x - 1, base_y - bh - bw // 2, x + bw + 1, base_y - bh + bw // 2],
                      outline=(*_palette_at(self.palette, 1.0), 230), width=1)
            x += bw + gap
        _composite_glow(im, layer, cfg.glow)


# Registry
_STYLES: Dict[str, type[_StyleBase]] = {
    cls.name: cls for cls in [
        BarsStyle, GradientBarsStyle, MirrorBarsStyle, WaveAreaStyle,
        OscilloscopeStyle, CircularStyle, PulseRingsStyle, ParticleBarsStyle,
        NeonStripStyle, LiquidWaveStyle, MountainStyle, BlockGridStyle,
        RadialBarsStyle, GalaxySpiralStyle, FloatingCurveStyle, RingStyle,
        StackedDotsStyle,
    ]
}


def list_styles() -> List[str]:
    return list(_STYLES.keys())


class SpectrumRenderer:
    """Composer kecil: ambil cfg + bands -> draw ke image."""

    def __init__(self, cfg: SpectrumConfig):
        self.cfg = cfg
        self._style = _STYLES.get(cfg.style, BarsStyle)(cfg)

    def reload(self, cfg: SpectrumConfig) -> None:
        self.cfg = cfg
        self._style = _STYLES.get(cfg.style, BarsStyle)(cfg)

    def draw(self, im: Image.Image, t: float, frame_idx: int,
             bands: np.ndarray, env: float) -> None:
        self._style.draw(im, t, frame_idx, bands, env)
