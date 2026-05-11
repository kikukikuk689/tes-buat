"""15 efek video musical.

Tiap efek mengimplementasikan draw(im, t, frame_idx, env, beat). Stateful
particle effects menyimpan state internal di self._state.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


@dataclass
class EffectConfig:
    name: str = "None"
    intensity: float = 0.6     # 0..1 (particle count multiplier)
    color: Tuple[int, int, int] = (255, 255, 255)
    react_to_music: bool = True


# ============================================================
# Base
# ============================================================

class _EffectBase:
    name = "None"

    def __init__(self, cfg: EffectConfig, size: Tuple[int, int], fps: int):
        self.cfg = cfg
        self.W, self.H = size
        self.fps = fps
        self._rng = random.Random(1337)
        self._state: Dict[str, np.ndarray] = {}
        self._setup()

    def _setup(self) -> None:
        return

    def reset(self) -> None:
        self._rng = random.Random(1337)
        self._state.clear()
        self._setup()

    def draw(self, im: Image.Image, t: float, frame_idx: int,
             env: float, beat: bool) -> None:  # pragma: no cover - abstract
        raise NotImplementedError


# ============================================================
# Particle helpers
# ============================================================

def _scale_intensity(cfg: EffectConfig, base: int) -> int:
    return max(4, int(base * (0.3 + cfg.intensity * 1.4)))


def _draw_soft_dot(layer: Image.Image, x: float, y: float, r: float,
                   color: Tuple[int, int, int], alpha: int) -> None:
    if r < 1:
        r = 1.0
    d = ImageDraw.Draw(layer)
    # outer glow
    d.ellipse([x - r * 1.6, y - r * 1.6, x + r * 1.6, y + r * 1.6],
              fill=(*color, max(0, int(alpha * 0.25))))
    d.ellipse([x - r, y - r, x + r, y + r], fill=(*color, alpha))
    # inner
    rr = max(0.5, r * 0.45)
    d.ellipse([x - rr, y - rr, x + rr, y + rr],
              fill=(255, 255, 255, min(255, alpha + 40)))


# ============================================================
# Effect implementations
# ============================================================

class _NullEffect(_EffectBase):
    name = "None"

    def draw(self, im, t, frame_idx, env, beat):
        return


class FirefliesEffect(_EffectBase):
    name = "Fireflies"

    def _setup(self) -> None:
        n = _scale_intensity(self.cfg, 60)
        rng = np.random.default_rng(42)
        self._state["x"] = rng.uniform(0, self.W, n).astype(np.float32)
        self._state["y"] = rng.uniform(0, self.H, n).astype(np.float32)
        self._state["vx"] = rng.uniform(-0.3, 0.3, n).astype(np.float32)
        self._state["vy"] = rng.uniform(-0.4, 0.0, n).astype(np.float32)
        self._state["phase"] = rng.uniform(0, math.tau, n).astype(np.float32)
        self._state["size"] = rng.uniform(1.5, 3.5, n).astype(np.float32)

    def draw(self, im, t, frame_idx, env, beat):
        x = self._state["x"]; y = self._state["y"]
        vx = self._state["vx"]; vy = self._state["vy"]
        ph = self._state["phase"]; sz = self._state["size"]
        # drift
        x += vx * (1.0 + env * 0.5)
        y += vy * (1.0 + env * 0.5)
        # gentle random walk
        vx += np.random.default_rng(frame_idx).uniform(-0.05, 0.05, vx.shape).astype(np.float32)
        vy += np.random.default_rng(frame_idx + 1).uniform(-0.05, 0.05, vy.shape).astype(np.float32)
        vx = np.clip(vx, -0.8, 0.8); vy = np.clip(vy, -0.8, 0.4)
        # wrap
        x %= self.W; y %= self.H
        self._state["x"] = x; self._state["y"] = y
        self._state["vx"] = vx; self._state["vy"] = vy

        layer = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        color = self.cfg.color
        for i in range(x.size):
            blink = 0.5 + 0.5 * math.sin(t * 2.0 + ph[i])
            r = sz[i] * (0.9 + 0.4 * blink + 0.3 * env)
            a = int(120 + 110 * blink * (0.6 + 0.4 * env))
            d.ellipse([x[i] - r * 1.7, y[i] - r * 1.7, x[i] + r * 1.7, y[i] + r * 1.7],
                      fill=(*color, int(a * 0.3)))
            d.ellipse([x[i] - r, y[i] - r, x[i] + r, y[i] + r],
                      fill=(*color, a))
        im.alpha_composite(layer)


class SparkleEffect(_EffectBase):
    name = "Sparkles"

    def _setup(self) -> None:
        n = _scale_intensity(self.cfg, 40)
        rng = np.random.default_rng(7)
        self._state["x"] = rng.uniform(0, self.W, n).astype(np.float32)
        self._state["y"] = rng.uniform(0, self.H, n).astype(np.float32)
        self._state["phase"] = rng.uniform(0, math.tau, n).astype(np.float32)

    def draw(self, im, t, frame_idx, env, beat):
        layer = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        color = self.cfg.color
        for i in range(self._state["x"].size):
            blink = math.sin(t * 4.0 + self._state["phase"][i]) ** 4
            if blink < 0.05:
                continue
            x = self._state["x"][i]; y = self._state["y"][i]
            r = 3 + 6 * blink * (0.6 + 0.6 * env)
            a = int(255 * blink)
            # cross
            d.line([(x - r, y), (x + r, y)], fill=(*color, a), width=1)
            d.line([(x, y - r), (x, y + r)], fill=(*color, a), width=1)
            # diag
            r2 = r * 0.55
            d.line([(x - r2, y - r2), (x + r2, y + r2)], fill=(*color, int(a * 0.7)), width=1)
            d.line([(x - r2, y + r2), (x + r2, y - r2)], fill=(*color, int(a * 0.7)), width=1)
            d.ellipse([x - 1.6, y - 1.6, x + 1.6, y + 1.6], fill=(255, 255, 255, a))
        im.alpha_composite(layer)


class SnowEffect(_EffectBase):
    name = "Snow"

    def _setup(self) -> None:
        n = _scale_intensity(self.cfg, 90)
        rng = np.random.default_rng(11)
        self._state["x"] = rng.uniform(0, self.W, n).astype(np.float32)
        self._state["y"] = rng.uniform(-self.H, self.H, n).astype(np.float32)
        self._state["sz"] = rng.uniform(1.5, 4.0, n).astype(np.float32)
        self._state["spd"] = rng.uniform(0.6, 1.8, n).astype(np.float32)
        self._state["sw"] = rng.uniform(0, math.tau, n).astype(np.float32)

    def draw(self, im, t, frame_idx, env, beat):
        x = self._state["x"]; y = self._state["y"]
        sz = self._state["sz"]; spd = self._state["spd"]; sw = self._state["sw"]
        y += spd * (1.2 + 0.6 * env)
        x += np.sin(sw + t * 1.2) * 0.5
        y[y > self.H + 5] -= (self.H + 10)
        x %= self.W
        self._state["x"] = x; self._state["y"] = y

        layer = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        c = self.cfg.color
        for i in range(x.size):
            r = sz[i]
            d.ellipse([x[i] - r, y[i] - r, x[i] + r, y[i] + r], fill=(*c, 200))
        im.alpha_composite(layer)


class BokehEffect(_EffectBase):
    name = "Bokeh"

    def _setup(self) -> None:
        n = _scale_intensity(self.cfg, 24)
        rng = np.random.default_rng(99)
        self._state["x"] = rng.uniform(0, self.W, n).astype(np.float32)
        self._state["y"] = rng.uniform(0, self.H, n).astype(np.float32)
        self._state["vx"] = rng.uniform(-0.15, 0.15, n).astype(np.float32)
        self._state["vy"] = rng.uniform(-0.2, -0.05, n).astype(np.float32)
        self._state["sz"] = rng.uniform(20, 60, n).astype(np.float32)
        self._state["hue"] = rng.uniform(0, 1, n).astype(np.float32)

    def draw(self, im, t, frame_idx, env, beat):
        x = self._state["x"]; y = self._state["y"]
        vx = self._state["vx"]; vy = self._state["vy"]
        sz = self._state["sz"]; hue = self._state["hue"]
        x += vx; y += vy
        x %= self.W; y %= self.H
        self._state["x"] = x; self._state["y"] = y

        # Build layer at smaller size for speed, then resize
        scale = 4
        small = Image.new("RGBA", (self.W // scale, self.H // scale), (0, 0, 0, 0))
        ds = ImageDraw.Draw(small)
        c = self.cfg.color
        for i in range(x.size):
            xi = x[i] / scale; yi = y[i] / scale
            r = sz[i] * (0.9 + 0.3 * env) / scale
            # slight per-particle hue shift
            shift = hue[i]
            col = (int(c[0] * (0.6 + 0.4 * shift)),
                   int(c[1] * (0.5 + 0.5 * (1 - shift))),
                   int(c[2] * (0.6 + 0.4 * (1 - shift))))
            ds.ellipse([xi - r, yi - r, xi + r, yi + r], fill=(*col, 120))
        small = small.filter(ImageFilter.GaussianBlur(8))
        big = small.resize((self.W, self.H), Image.BILINEAR)
        im.alpha_composite(big)


class StarsEffect(_EffectBase):
    name = "Stars"

    def _setup(self) -> None:
        n = _scale_intensity(self.cfg, 80)
        rng = np.random.default_rng(3)
        self._state["x"] = rng.uniform(0, self.W, n).astype(np.float32)
        self._state["y"] = rng.uniform(0, self.H, n).astype(np.float32)
        self._state["br"] = rng.uniform(0.4, 1.0, n).astype(np.float32)
        self._state["ph"] = rng.uniform(0, math.tau, n).astype(np.float32)

    def draw(self, im, t, frame_idx, env, beat):
        layer = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        c = self.cfg.color
        for i in range(self._state["x"].size):
            br = self._state["br"][i]
            blink = 0.6 + 0.4 * math.sin(t * (1 + br) + self._state["ph"][i])
            a = int(255 * br * blink)
            x = self._state["x"][i]; y = self._state["y"][i]
            d.point((x, y), fill=(*c, a))
            d.ellipse([x - 1, y - 1, x + 1, y + 1], fill=(*c, a))
        im.alpha_composite(layer)


class LightRaysEffect(_EffectBase):
    name = "Light Rays"

    def draw(self, im, t, frame_idx, env, beat):
        cx, cy = self.W // 2, -self.H // 6
        layer = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        c = self.cfg.color
        n = 9
        rot = t * 0.08
        for i in range(n):
            theta = -math.pi / 2 + (i - n / 2) * 0.18 + math.sin(t * 0.3 + i) * 0.05 + rot * 0
            x2 = cx + math.cos(theta) * (self.H * 2)
            y2 = cy + math.sin(theta) * (self.H * 2)
            for k in range(6):
                w = max(2, int(30 - k * 4))
                a = int(35 - k * 4) + int(20 * env)
                if a <= 2:
                    continue
                d.line([(cx, cy), (x2, y2)], fill=(*c, a), width=w)
        layer = layer.filter(ImageFilter.GaussianBlur(6))
        im.alpha_composite(layer)


class ConfettiEffect(_EffectBase):
    name = "Confetti"

    def _setup(self) -> None:
        n = _scale_intensity(self.cfg, 60)
        rng = np.random.default_rng(21)
        self._state["x"] = rng.uniform(0, self.W, n).astype(np.float32)
        self._state["y"] = rng.uniform(-self.H, 0, n).astype(np.float32)
        self._state["vy"] = rng.uniform(2.0, 5.0, n).astype(np.float32)
        self._state["vx"] = rng.uniform(-1.2, 1.2, n).astype(np.float32)
        self._state["rot"] = rng.uniform(0, math.tau, n).astype(np.float32)
        self._state["spin"] = rng.uniform(-0.2, 0.2, n).astype(np.float32)
        self._state["hue"] = rng.uniform(0, 1, n).astype(np.float32)

    def draw(self, im, t, frame_idx, env, beat):
        x = self._state["x"]; y = self._state["y"]
        vy = self._state["vy"]; vx = self._state["vx"]
        rot = self._state["rot"]; spin = self._state["spin"]
        hue = self._state["hue"]
        y += vy * (0.8 + 0.6 * env)
        x += vx
        rot += spin
        y[y > self.H + 10] -= (self.H + 30)
        x %= self.W
        self._state["y"] = y; self._state["x"] = x; self._state["rot"] = rot

        layer = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        for i in range(x.size):
            c = (int(255 * hue[i]),
                 int(255 * (1 - hue[i])),
                 int(255 * (0.5 + 0.5 * math.sin(hue[i] * 6.28))))
            ca = math.cos(rot[i]); sa = math.sin(rot[i])
            w, h = 8, 4
            pts = [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
            poly = [(x[i] + p[0] * ca - p[1] * sa, y[i] + p[0] * sa + p[1] * ca) for p in pts]
            d.polygon(poly, fill=(*c, 220))
        im.alpha_composite(layer)


class DustEffect(_EffectBase):
    name = "Dust"

    def _setup(self) -> None:
        n = _scale_intensity(self.cfg, 120)
        rng = np.random.default_rng(31)
        self._state["x"] = rng.uniform(0, self.W, n).astype(np.float32)
        self._state["y"] = rng.uniform(0, self.H, n).astype(np.float32)
        self._state["vx"] = rng.uniform(-0.4, 0.4, n).astype(np.float32)
        self._state["vy"] = rng.uniform(-0.3, -0.05, n).astype(np.float32)
        self._state["ph"] = rng.uniform(0, math.tau, n).astype(np.float32)

    def draw(self, im, t, frame_idx, env, beat):
        x = self._state["x"]; y = self._state["y"]
        vx = self._state["vx"]; vy = self._state["vy"]; ph = self._state["ph"]
        x += vx; y += vy
        x %= self.W; y %= self.H
        self._state["x"] = x; self._state["y"] = y

        layer = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        c = self.cfg.color
        for i in range(x.size):
            a = int(60 + 60 * math.sin(t * 0.8 + ph[i])) + int(40 * env)
            a = max(20, min(220, a))
            d.point((x[i], y[i]), fill=(*c, a))
        im.alpha_composite(layer)


class GlowPulseEffect(_EffectBase):
    name = "Glow Pulse"

    def draw(self, im, t, frame_idx, env, beat):
        # Soft vignette-like radial pulse
        layer = Image.new("RGBA", (self.W // 4, self.H // 4), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        cx, cy = layer.size[0] // 2, layer.size[1] // 2
        r = int(min(layer.size) * (0.3 + 0.55 * env))
        c = self.cfg.color
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*c, int(120 * env + 60)))
        layer = layer.filter(ImageFilter.GaussianBlur(40))
        big = layer.resize((self.W, self.H), Image.BILINEAR)
        im.alpha_composite(big)


class ColorWashEffect(_EffectBase):
    name = "Color Wash"

    def draw(self, im, t, frame_idx, env, beat):
        # Translucent full-frame color tint pulsing
        layer = Image.new("RGBA", (self.W, self.H),
                          (*self.cfg.color, int(40 + 80 * env)))
        im.alpha_composite(layer)


class VignettePulseEffect(_EffectBase):
    name = "Vignette Pulse"

    def __init__(self, cfg: EffectConfig, size: Tuple[int, int], fps: int):
        super().__init__(cfg, size, fps)
        # Pre-build vignette
        small = Image.new("L", (self.W // 4, self.H // 4), 0)
        d = ImageDraw.Draw(small)
        cx, cy = small.size[0] // 2, small.size[1] // 2
        r = int(min(small.size) * 0.45)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
        small = small.filter(ImageFilter.GaussianBlur(20))
        # Invert: dark edges
        mask = Image.eval(small, lambda v: 255 - v)
        mask = mask.resize((self.W, self.H), Image.BILINEAR)
        self._vignette = Image.merge("RGBA", [
            Image.new("L", (self.W, self.H), 0),
            Image.new("L", (self.W, self.H), 0),
            Image.new("L", (self.W, self.H), 0),
            mask,
        ])

    def draw(self, im, t, frame_idx, env, beat):
        # Reduce vignette strength when audio peaks for "breathing" effect
        a = int(200 - 160 * env)
        v = self._vignette.copy()
        # adjust alpha
        np_arr = np.asarray(v, dtype=np.uint8).copy()
        np_arr[..., 3] = (np_arr[..., 3].astype(np.int32) * a // 255).astype(np.uint8)
        im.alpha_composite(Image.fromarray(np_arr, "RGBA"))


class RainEffect(_EffectBase):
    name = "Rain"

    def _setup(self) -> None:
        n = _scale_intensity(self.cfg, 90)
        rng = np.random.default_rng(73)
        self._state["x"] = rng.uniform(0, self.W, n).astype(np.float32)
        self._state["y"] = rng.uniform(-self.H, 0, n).astype(np.float32)
        self._state["spd"] = rng.uniform(8, 16, n).astype(np.float32)
        self._state["len"] = rng.uniform(8, 18, n).astype(np.float32)

    def draw(self, im, t, frame_idx, env, beat):
        x = self._state["x"]; y = self._state["y"]
        spd = self._state["spd"]; ln = self._state["len"]
        y += spd
        y[y > self.H + 20] = -ln[y > self.H + 20]
        x = (x + 1.5) % self.W
        self._state["x"] = x; self._state["y"] = y

        layer = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        c = self.cfg.color
        for i in range(x.size):
            d.line([(x[i], y[i]), (x[i] - 2, y[i] + ln[i])],
                   fill=(*c, 170), width=1)
        im.alpha_composite(layer)


class PetalsEffect(_EffectBase):
    name = "Petals"

    def _setup(self) -> None:
        n = _scale_intensity(self.cfg, 40)
        rng = np.random.default_rng(13)
        self._state["x"] = rng.uniform(0, self.W, n).astype(np.float32)
        self._state["y"] = rng.uniform(-self.H, 0, n).astype(np.float32)
        self._state["spd"] = rng.uniform(0.8, 2.0, n).astype(np.float32)
        self._state["swp"] = rng.uniform(0, math.tau, n).astype(np.float32)
        self._state["rot"] = rng.uniform(0, math.tau, n).astype(np.float32)

    def draw(self, im, t, frame_idx, env, beat):
        x = self._state["x"]; y = self._state["y"]
        spd = self._state["spd"]; swp = self._state["swp"]; rot = self._state["rot"]
        y += spd * (0.8 + 0.4 * env)
        x += np.sin(swp + t * 0.7) * 1.2
        y[y > self.H + 12] -= (self.H + 30)
        x %= self.W
        rot += 0.02
        self._state["x"] = x; self._state["y"] = y; self._state["rot"] = rot

        layer = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        c = self.cfg.color
        for i in range(x.size):
            r = 4
            ca = math.cos(rot[i]); sa = math.sin(rot[i])
            pts = [(0, -r), (r * 0.7, 0), (0, r), (-r * 0.7, 0)]
            poly = [(x[i] + p[0] * ca - p[1] * sa, y[i] + p[0] * sa + p[1] * ca) for p in pts]
            d.polygon(poly, fill=(*c, 200))
        im.alpha_composite(layer)


class HeartsEffect(_EffectBase):
    name = "Hearts"

    def _setup(self) -> None:
        n = _scale_intensity(self.cfg, 30)
        rng = np.random.default_rng(99)
        self._state["x"] = rng.uniform(0, self.W, n).astype(np.float32)
        self._state["y"] = rng.uniform(0, self.H, n).astype(np.float32)
        self._state["spd"] = rng.uniform(0.5, 1.5, n).astype(np.float32)
        self._state["sz"] = rng.uniform(6, 14, n).astype(np.float32)

    def draw(self, im, t, frame_idx, env, beat):
        x = self._state["x"]; y = self._state["y"]
        spd = self._state["spd"]; sz = self._state["sz"]
        y -= spd * (0.8 + 0.6 * env)
        x += np.sin(t * 0.9 + y * 0.02) * 0.5
        y[y < -16] += self.H + 16
        x %= self.W
        self._state["x"] = x; self._state["y"] = y

        layer = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        c = self.cfg.color
        for i in range(x.size):
            s = sz[i]
            cx, cy = x[i], y[i]
            # heart from 2 circles + triangle
            d.ellipse([cx - s, cy - s, cx, cy], fill=(*c, 220))
            d.ellipse([cx, cy - s, cx + s, cy], fill=(*c, 220))
            d.polygon([(cx - s, cy - s / 2),
                       (cx + s, cy - s / 2),
                       (cx, cy + s)], fill=(*c, 220))
        im.alpha_composite(layer)


class MusicNotesEffect(_EffectBase):
    name = "Music Notes"

    def _setup(self) -> None:
        n = _scale_intensity(self.cfg, 18)
        rng = np.random.default_rng(55)
        self._state["x"] = rng.uniform(0, self.W, n).astype(np.float32)
        self._state["y"] = rng.uniform(0, self.H, n).astype(np.float32)
        self._state["spd"] = rng.uniform(0.6, 1.4, n).astype(np.float32)
        self._state["sw"] = rng.uniform(0, math.tau, n).astype(np.float32)
        self._state["which"] = rng.integers(0, 2, n)

    def draw(self, im, t, frame_idx, env, beat):
        x = self._state["x"]; y = self._state["y"]
        spd = self._state["spd"]; sw = self._state["sw"]; which = self._state["which"]
        y -= spd * (0.8 + 0.6 * env)
        x += np.sin(sw + t) * 0.8
        y[y < -20] += self.H + 20
        x %= self.W
        self._state["x"] = x; self._state["y"] = y

        layer = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        c = self.cfg.color
        for i in range(x.size):
            cx, cy = x[i], y[i]
            if which[i] == 0:
                # quarter note
                d.ellipse([cx - 6, cy - 4, cx + 4, cy + 4], fill=(*c, 220))
                d.line([(cx + 4, cy), (cx + 4, cy - 22)], fill=(*c, 220), width=2)
            else:
                # eighth note pair
                d.ellipse([cx - 6, cy - 4, cx + 4, cy + 4], fill=(*c, 220))
                d.ellipse([cx + 8, cy - 4, cx + 18, cy + 4], fill=(*c, 220))
                d.line([(cx + 4, cy), (cx + 4, cy - 22)], fill=(*c, 220), width=2)
                d.line([(cx + 18, cy), (cx + 18, cy - 22)], fill=(*c, 220), width=2)
                d.line([(cx + 4, cy - 22), (cx + 18, cy - 22)], fill=(*c, 220), width=2)
        im.alpha_composite(layer)


# Registry
_EFFECTS: Dict[str, type[_EffectBase]] = {
    cls.name: cls for cls in [
        _NullEffect, FirefliesEffect, SparkleEffect, SnowEffect, BokehEffect,
        StarsEffect, LightRaysEffect, ConfettiEffect, DustEffect,
        GlowPulseEffect, ColorWashEffect, VignettePulseEffect, RainEffect,
        PetalsEffect, HeartsEffect, MusicNotesEffect,
    ]
}


def list_effects() -> List[str]:
    return list(_EFFECTS.keys())


class EffectRenderer:
    """Manage multiple stacked effects."""

    def __init__(self, cfgs: List[EffectConfig], size: Tuple[int, int], fps: int):
        self.size = size
        self.fps = fps
        self._effects = [_EFFECTS.get(c.name, _NullEffect)(c, size, fps) for c in cfgs]

    def reload(self, cfgs: List[EffectConfig]) -> None:
        self._effects = [_EFFECTS.get(c.name, _NullEffect)(c, self.size, self.fps) for c in cfgs]

    def draw(self, im: Image.Image, t: float, frame_idx: int,
             env: float, beat: bool) -> None:
        for e in self._effects:
            e.draw(im, t, frame_idx, env, beat)
