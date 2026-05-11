"""Special video effects (fireflies, sparkles, light leaks, etc).

Each effect is a stateful generator that maintains its own particle / state
across frames so motion is continuous.  ``EffectEngine`` is created with a
target size + selected effect + audio analysis, and ``render_frame(i)`` is
called once per output frame.

Effects are intentionally lightweight: most use small particle counts and
numpy/PIL draws so they run on low-end hardware.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


# --------------------------------------------------------------------------
# Particle helpers
# --------------------------------------------------------------------------

@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    size: float
    color: Tuple[int, int, int]
    life: float
    max_life: float
    rot: float = 0.0
    rot_v: float = 0.0


def _add_glow(img: Image.Image, strength: float) -> Image.Image:
    if strength <= 0:
        return img
    blur = img.filter(ImageFilter.GaussianBlur(radius=4 + strength * 8))
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.alpha_composite(blur)
    out.alpha_composite(img)
    return out


# --------------------------------------------------------------------------
# Effect engine base
# --------------------------------------------------------------------------

class Effect:
    name = "Base"
    requires_audio = False

    def __init__(self, size, fps: int, intensity: float = 1.0, color: Tuple[int, int, int] = (255, 230, 160), seed: int = 1234):
        self.w, self.h = size
        self.fps = fps
        self.intensity = max(0.0, min(2.0, intensity))
        self.color = color
        self.rng = random.Random(seed)
        self.np_rng = np.random.default_rng(seed)
        self.particles: List[Particle] = []
        self.state = {}

    def reset(self):
        self.particles.clear()
        self.state.clear()

    def step(self, beat: float, loudness: float, t_sec: float) -> Image.Image:
        raise NotImplementedError


# --------------------------------------------------------------------------
# Individual effects
# --------------------------------------------------------------------------

class FirefliesEffect(Effect):
    """Slowly moving glowing dots that fade in/out like fireflies."""
    name = "Fireflies"

    def __init__(self, size, fps, intensity=1.0, color=(255, 240, 170), **kw):
        super().__init__(size, fps, intensity, color, **kw)
        n = int(60 * intensity)
        for _ in range(n):
            self._spawn()

    def _spawn(self):
        self.particles.append(Particle(
            x=self.rng.uniform(0, self.w),
            y=self.rng.uniform(0, self.h),
            vx=self.rng.uniform(-0.4, 0.4),
            vy=self.rng.uniform(-0.3, 0.3),
            size=self.rng.uniform(2, 5),
            color=self.color,
            life=self.rng.uniform(0.4, 1.0),
            max_life=self.rng.uniform(2.0, 5.0),
        ))

    def step(self, beat, loudness, t_sec):
        img = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img, "RGBA")
        dt = 1.0 / self.fps
        for p in self.particles:
            p.x += p.vx
            p.y += p.vy
            p.life -= dt
            if p.life <= 0:
                p.x = self.rng.uniform(0, self.w)
                p.y = self.rng.uniform(0, self.h)
                p.life = p.max_life
                p.vx = self.rng.uniform(-0.4, 0.4)
                p.vy = self.rng.uniform(-0.3, 0.3)
            # alpha pulsates
            t = p.life / p.max_life
            alpha = int(255 * math.sin(t * math.pi) ** 2 * 0.8 + 40 * loudness)
            alpha = max(0, min(255, alpha))
            col = p.color + (alpha,)
            r = p.size
            draw.ellipse([p.x - r, p.y - r, p.x + r, p.y + r], fill=col)
        return _add_glow(img, 1.0)


class SparkleEffect(Effect):
    """Bright sparkles that burst on loudness peaks."""
    name = "Sparkles"

    def step(self, beat, loudness, t_sec):
        img = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img, "RGBA")
        spawn = int(self.intensity * (3 + 25 * beat))
        for _ in range(spawn):
            self.particles.append(Particle(
                x=self.rng.uniform(0, self.w),
                y=self.rng.uniform(0, self.h),
                vx=0, vy=0,
                size=self.rng.uniform(2, 6 + 4 * loudness),
                color=self.color,
                life=self.rng.uniform(0.2, 0.6),
                max_life=0.6,
            ))
        dt = 1.0 / self.fps
        new_particles = []
        for p in self.particles:
            p.life -= dt
            if p.life <= 0:
                continue
            t = p.life / p.max_life
            alpha = int(255 * t)
            col = p.color + (alpha,)
            r = p.size
            draw.ellipse([p.x - r, p.y - r, p.x + r, p.y + r], fill=col)
            # cross / plus shape for that "twinkle" look
            draw.line([p.x - r * 2.5, p.y, p.x + r * 2.5, p.y], fill=col, width=1)
            draw.line([p.x, p.y - r * 2.5, p.x, p.y + r * 2.5], fill=col, width=1)
            new_particles.append(p)
        self.particles = new_particles[-400:]
        return _add_glow(img, 1.2)


class SnowEffect(Effect):
    """Snow / dust falling slowly with drift."""
    name = "Snow"

    def __init__(self, size, fps, intensity=1.0, color=(255, 255, 255), **kw):
        super().__init__(size, fps, intensity, color, **kw)
        n = int(120 * intensity)
        for _ in range(n):
            self.particles.append(Particle(
                x=self.rng.uniform(0, self.w),
                y=self.rng.uniform(-self.h, self.h),
                vx=self.rng.uniform(-0.4, 0.4),
                vy=self.rng.uniform(0.8, 2.4),
                size=self.rng.uniform(1.2, 3.0),
                color=self.color,
                life=1.0, max_life=1.0,
            ))

    def step(self, beat, loudness, t_sec):
        img = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img, "RGBA")
        for p in self.particles:
            p.x += p.vx + math.sin(t_sec * 0.5 + p.y * 0.01) * 0.5
            p.y += p.vy + loudness * 1.0
            if p.y > self.h + 5:
                p.y = -self.rng.uniform(0, 50)
                p.x = self.rng.uniform(0, self.w)
            alpha = 200
            col = p.color + (alpha,)
            r = p.size
            draw.ellipse([p.x - r, p.y - r, p.x + r, p.y + r], fill=col)
        return _add_glow(img, 0.4)


class RainEffect(Effect):
    """Diagonal rain streaks."""
    name = "Rain"

    def __init__(self, size, fps, intensity=1.0, color=(190, 220, 255), **kw):
        super().__init__(size, fps, intensity, color, **kw)
        n = int(180 * intensity)
        for _ in range(n):
            self.particles.append(Particle(
                x=self.rng.uniform(-self.w * 0.2, self.w),
                y=self.rng.uniform(0, self.h),
                vx=self.rng.uniform(2.0, 4.0),
                vy=self.rng.uniform(10, 18),
                size=self.rng.uniform(6, 14),
                color=self.color, life=1.0, max_life=1.0,
            ))

    def step(self, beat, loudness, t_sec):
        img = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img, "RGBA")
        for p in self.particles:
            p.x += p.vx
            p.y += p.vy
            if p.y > self.h:
                p.y = -self.rng.uniform(0, 50)
                p.x = self.rng.uniform(0, self.w)
            col = p.color + (140,)
            draw.line([p.x, p.y, p.x - p.vx * 1.2, p.y - p.vy * 1.2], fill=col, width=1)
        return _add_glow(img, 0.2)


class BokehEffect(Effect):
    """Large soft blurred orbs floating slowly."""
    name = "Bokeh"

    def __init__(self, size, fps, intensity=1.0, color=(255, 200, 240), **kw):
        super().__init__(size, fps, intensity, color, **kw)
        n = int(25 * intensity)
        for _ in range(n):
            self.particles.append(Particle(
                x=self.rng.uniform(0, self.w),
                y=self.rng.uniform(0, self.h),
                vx=self.rng.uniform(-0.3, 0.3),
                vy=self.rng.uniform(-0.4, -0.05),
                size=self.rng.uniform(self.w * 0.02, self.w * 0.06),
                color=(self.rng.randint(180, 255), self.rng.randint(150, 255),
                       self.rng.randint(200, 255)),
                life=1.0, max_life=1.0,
            ))

    def step(self, beat, loudness, t_sec):
        img = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img, "RGBA")
        for p in self.particles:
            p.x += p.vx
            p.y += p.vy
            if p.y < -p.size or p.x < -p.size or p.x > self.w + p.size:
                p.y = self.h + p.size
                p.x = self.rng.uniform(0, self.w)
            col = p.color + (90,)
            draw.ellipse([p.x - p.size, p.y - p.size, p.x + p.size, p.y + p.size], fill=col)
        return img.filter(ImageFilter.GaussianBlur(radius=18))


class LightLeakEffect(Effect):
    """Drifting blurred color streaks across the frame."""
    name = "Light Leak"

    def __init__(self, size, fps, intensity=1.0, color=(255, 180, 120), **kw):
        super().__init__(size, fps, intensity, color, **kw)
        self.streaks = []
        for _ in range(int(4 * intensity)):
            self.streaks.append({
                "x": self.rng.uniform(-self.w * 0.3, self.w),
                "y": self.rng.uniform(0, self.h),
                "len": self.rng.uniform(self.w * 0.4, self.w * 0.8),
                "th": self.rng.uniform(self.h * 0.08, self.h * 0.2),
                "vx": self.rng.uniform(0.3, 1.0),
                "color": (self.rng.randint(200, 255), self.rng.randint(100, 220),
                          self.rng.randint(80, 200)),
            })

    def step(self, beat, loudness, t_sec):
        img = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img, "RGBA")
        for s in self.streaks:
            s["x"] += s["vx"]
            if s["x"] > self.w + s["len"]:
                s["x"] = -s["len"]
                s["y"] = self.rng.uniform(0, self.h)
            col = s["color"] + (80,)
            draw.ellipse([s["x"], s["y"] - s["th"] / 2,
                          s["x"] + s["len"], s["y"] + s["th"] / 2], fill=col)
        return img.filter(ImageFilter.GaussianBlur(radius=40))


class StarsEffect(Effect):
    """Twinkling distant stars."""
    name = "Stars"

    def __init__(self, size, fps, intensity=1.0, color=(255, 255, 230), **kw):
        super().__init__(size, fps, intensity, color, **kw)
        n = int(200 * intensity)
        for _ in range(n):
            self.particles.append(Particle(
                x=self.rng.uniform(0, self.w),
                y=self.rng.uniform(0, self.h),
                vx=0, vy=0,
                size=self.rng.uniform(0.8, 2.4),
                color=self.color,
                life=self.rng.uniform(0, 1.0),
                max_life=self.rng.uniform(1.0, 3.0),
            ))

    def step(self, beat, loudness, t_sec):
        img = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img, "RGBA")
        dt = 1.0 / self.fps
        for p in self.particles:
            p.life += dt
            twinkle = (math.sin(p.life * 6.28 / p.max_life) + 1) / 2
            alpha = int(220 * twinkle + 30 * loudness)
            col = p.color + (alpha,)
            r = p.size
            draw.ellipse([p.x - r, p.y - r, p.x + r, p.y + r], fill=col)
        return _add_glow(img, 0.5)


class HeartsEffect(Effect):
    """Rising heart-shaped particles - nice for love songs."""
    name = "Hearts"

    def __init__(self, size, fps, intensity=1.0, color=(255, 95, 130), **kw):
        super().__init__(size, fps, intensity, color, **kw)
        self._spawn_pool = int(2 * intensity)

    def step(self, beat, loudness, t_sec):
        img = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img, "RGBA")
        for _ in range(self._spawn_pool + int(beat * 3)):
            self.particles.append(Particle(
                x=self.rng.uniform(0, self.w),
                y=self.h + 10,
                vx=self.rng.uniform(-0.4, 0.4),
                vy=-self.rng.uniform(1.0, 2.4),
                size=self.rng.uniform(6, 14),
                color=self.color,
                life=self.rng.uniform(2.0, 5.0),
                max_life=5.0,
            ))
        dt = 1.0 / self.fps
        kept = []
        for p in self.particles:
            p.x += p.vx + math.sin(t_sec * 1.5 + p.y * 0.01) * 0.5
            p.y += p.vy
            p.life -= dt
            if p.life <= 0 or p.y < -20:
                continue
            t = max(0, p.life / p.max_life)
            alpha = int(255 * t)
            col = p.color + (alpha,)
            self._draw_heart(draw, p.x, p.y, p.size, col)
            kept.append(p)
        self.particles = kept[-300:]
        return _add_glow(img, 0.4)

    @staticmethod
    def _draw_heart(draw, x, y, s, col):
        draw.ellipse([x - s, y - s, x, y], fill=col)
        draw.ellipse([x, y - s, x + s, y], fill=col)
        draw.polygon([(x - s, y - s * 0.2), (x + s, y - s * 0.2), (x, y + s)], fill=col)


class BubblesEffect(Effect):
    """Rising bubble outlines."""
    name = "Bubbles"

    def __init__(self, size, fps, intensity=1.0, color=(200, 240, 255), **kw):
        super().__init__(size, fps, intensity, color, **kw)

    def step(self, beat, loudness, t_sec):
        img = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img, "RGBA")
        spawn = int(self.intensity * 2 + beat * 3)
        for _ in range(spawn):
            self.particles.append(Particle(
                x=self.rng.uniform(0, self.w),
                y=self.h + 10,
                vx=self.rng.uniform(-0.4, 0.4),
                vy=-self.rng.uniform(1.0, 2.0),
                size=self.rng.uniform(4, 14),
                color=self.color,
                life=self.rng.uniform(2.0, 5.0), max_life=5.0,
            ))
        dt = 1.0 / self.fps
        kept = []
        for p in self.particles:
            p.x += p.vx + math.sin(t_sec * 1.5 + p.y * 0.01) * 0.4
            p.y += p.vy
            p.life -= dt
            if p.life <= 0 or p.y < -p.size:
                continue
            t = max(0, p.life / p.max_life)
            alpha = int(180 * t)
            col = p.color + (alpha,)
            draw.ellipse([p.x - p.size, p.y - p.size, p.x + p.size, p.y + p.size],
                         outline=col, width=2)
            draw.ellipse([p.x - p.size * 0.45, p.y - p.size * 0.55,
                          p.x - p.size * 0.2, p.y - p.size * 0.3],
                         fill=col)
            kept.append(p)
        self.particles = kept[-300:]
        return _add_glow(img, 0.5)


class ConfettiEffect(Effect):
    """Spinning rectangular confetti."""
    name = "Confetti"

    def __init__(self, size, fps, intensity=1.0, color=(255, 100, 100), **kw):
        super().__init__(size, fps, intensity, color, **kw)
        n = int(80 * intensity)
        for _ in range(n):
            self.particles.append(Particle(
                x=self.rng.uniform(0, self.w),
                y=self.rng.uniform(-self.h, 0),
                vx=self.rng.uniform(-1, 1),
                vy=self.rng.uniform(2, 5),
                size=self.rng.uniform(6, 12),
                color=(self.rng.randint(80, 255), self.rng.randint(80, 255),
                       self.rng.randint(80, 255)),
                life=1.0, max_life=1.0,
                rot=self.rng.uniform(0, 360),
                rot_v=self.rng.uniform(-6, 6),
            ))

    def step(self, beat, loudness, t_sec):
        img = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        for p in self.particles:
            p.x += p.vx + math.sin(t_sec + p.y * 0.01) * 0.3
            p.y += p.vy
            p.rot += p.rot_v
            if p.y > self.h + 10:
                p.y = -self.rng.uniform(0, 80)
                p.x = self.rng.uniform(0, self.w)
            shape = Image.new("RGBA", (int(p.size * 2), int(p.size * 2)), (0, 0, 0, 0))
            ImageDraw.Draw(shape).rectangle(
                [0, p.size * 0.7, p.size * 2, p.size * 1.3],
                fill=p.color + (220,),
            )
            shape = shape.rotate(p.rot, resample=Image.BILINEAR)
            img.alpha_composite(shape, (int(p.x - p.size), int(p.y - p.size)))
        return img


class SmokeEffect(Effect):
    """Soft drifting smoke clouds."""
    name = "Smoke"

    def __init__(self, size, fps, intensity=1.0, color=(220, 220, 230), **kw):
        super().__init__(size, fps, intensity, color, **kw)

    def step(self, beat, loudness, t_sec):
        img = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        for _ in range(int(self.intensity * 2 + beat * 2)):
            self.particles.append(Particle(
                x=self.rng.uniform(0, self.w),
                y=self.h + 20,
                vx=self.rng.uniform(-0.2, 0.2),
                vy=-self.rng.uniform(0.4, 1.0),
                size=self.rng.uniform(self.w * 0.04, self.w * 0.1),
                color=self.color, life=self.rng.uniform(2, 4), max_life=4,
            ))
        dt = 1.0 / self.fps
        kept = []
        for p in self.particles:
            p.x += p.vx
            p.y += p.vy
            p.size += 0.2
            p.life -= dt
            if p.life <= 0 or p.y < -p.size:
                continue
            t = max(0, p.life / p.max_life)
            col = p.color + (int(60 * t),)
            ImageDraw.Draw(img).ellipse(
                [p.x - p.size, p.y - p.size, p.x + p.size, p.y + p.size],
                fill=col,
            )
            kept.append(p)
        self.particles = kept[-150:]
        return img.filter(ImageFilter.GaussianBlur(radius=18))


class NeonGridEffect(Effect):
    """Retro neon grid that pulses with the music."""
    name = "Neon Grid"

    def step(self, beat, loudness, t_sec):
        img = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img, "RGBA")
        horizon_y = int(self.h * 0.55)
        spacing = 30
        for i in range(0, self.w, spacing):
            col = self.color + (int(120 + 80 * loudness),)
            draw.line([(i, horizon_y), (self.w / 2, self.h)], fill=col, width=1)
            draw.line([(i, horizon_y), (i - (i - self.w / 2) * 1.6, self.h)],
                       fill=col, width=1)
        for j in range(0, 8):
            yy = horizon_y + (self.h - horizon_y) * ((j + (t_sec * 0.3 % 1)) / 8) ** 2
            col = self.color + (int(80 + 100 * (j / 8)),)
            draw.line([(0, yy), (self.w, yy)], fill=col, width=1)
        return _add_glow(img, 0.8)


class PulseRingEffect(Effect):
    """Concentric rings that pulse out from center on beats."""
    name = "Pulse Rings"

    def __init__(self, size, fps, intensity=1.0, color=(255, 255, 255), **kw):
        super().__init__(size, fps, intensity, color, **kw)
        self.rings = []

    def step(self, beat, loudness, t_sec):
        img = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img, "RGBA")
        if beat > 0.4:
            self.rings.append({"r": 20.0, "alpha": 200.0})
        cx, cy = self.w / 2, self.h / 2
        kept = []
        for r in self.rings:
            r["r"] += 6 + 4 * self.intensity
            r["alpha"] *= 0.95
            if r["alpha"] < 5:
                continue
            col = self.color + (int(r["alpha"]),)
            draw.ellipse([cx - r["r"], cy - r["r"], cx + r["r"], cy + r["r"]],
                         outline=col, width=3)
            kept.append(r)
        self.rings = kept
        return _add_glow(img, 0.7)


class VinylScratchEffect(Effect):
    """Film grain / vinyl noise overlay."""
    name = "Film Grain"

    def step(self, beat, loudness, t_sec):
        noise = (self.np_rng.random((self.h // 4, self.w // 4)) * 60 + 20).astype(np.uint8)
        arr = np.stack([noise] * 3 + [np.full_like(noise, int(30 * self.intensity))], axis=-1)
        img = Image.fromarray(arr, "RGBA").resize((self.w, self.h), Image.NEAREST)
        return img


class AuroraEffect(Effect):
    """Colorful aurora-like vertical waves at top of screen."""
    name = "Aurora"

    def step(self, beat, loudness, t_sec):
        img = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img, "RGBA")
        bands = 4
        for b in range(bands):
            pts_top = []
            pts_bot = []
            phase = t_sec * 0.3 + b * 0.7
            for x in range(0, self.w + 10, 20):
                yy = self.h * 0.15 + math.sin(x * 0.005 + phase) * 30 + b * 25
                pts_top.append((x, yy))
                pts_bot.append((x, yy + 80 + 40 * loudness))
            poly = pts_top + pts_bot[::-1]
            r = int(80 + 60 * b)
            g = int(220 - 30 * b)
            bl = int(180 + 20 * b)
            col = (max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, bl)), 80)
            draw.polygon(poly, fill=col)
        return img.filter(ImageFilter.GaussianBlur(radius=20))


EFFECTS: Dict[str, type] = {
    "None": None,  # type: ignore
    "Fireflies": FirefliesEffect,
    "Sparkles": SparkleEffect,
    "Snow": SnowEffect,
    "Rain": RainEffect,
    "Bokeh": BokehEffect,
    "Light Leak": LightLeakEffect,
    "Stars": StarsEffect,
    "Hearts": HeartsEffect,
    "Bubbles": BubblesEffect,
    "Confetti": ConfettiEffect,
    "Smoke": SmokeEffect,
    "Neon Grid": NeonGridEffect,
    "Pulse Rings": PulseRingEffect,
    "Film Grain": VinylScratchEffect,
    "Aurora": AuroraEffect,
}


def list_effects() -> List[str]:
    return list(EFFECTS.keys())


def create_effect(name: str, size, fps: int, intensity: float = 1.0,
                  color: Tuple[int, int, int] = (255, 230, 160)) -> Optional[Effect]:
    cls = EFFECTS.get(name)
    if cls is None:
        return None
    return cls(size, fps=fps, intensity=intensity, color=color)
