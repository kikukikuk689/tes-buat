"""Logo loading and compositing (circular crop, position, size)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter


# Friendly position labels mapped to a fractional (x, y) anchor of the logo
# center, expressed as a fraction of the canvas.
POSITIONS = {
    "Top Left":      (0.06, 0.10),
    "Top Center":    (0.50, 0.10),
    "Top Right":     (0.94, 0.10),
    "Middle Left":   (0.06, 0.50),
    "Center":        (0.50, 0.50),
    "Middle Right":  (0.94, 0.50),
    "Bottom Left":   (0.06, 0.88),
    "Bottom Center": (0.50, 0.88),
    "Bottom Right":  (0.94, 0.88),
}


@dataclass
class LogoConfig:
    path: Optional[str] = None
    enabled: bool = False
    circular: bool = True
    position: str = "Top Right"
    size_pct: float = 0.10        # diameter as fraction of min(w, h)
    opacity: float = 1.0
    border: bool = True
    border_width_pct: float = 0.012
    border_color: Tuple[int, int, int] = (255, 255, 255)
    shadow: bool = True


class LogoOverlay:
    """Precomputes the logo overlay once, then ``composite()``s per frame."""

    def __init__(self, canvas_size: Tuple[int, int], cfg: LogoConfig):
        self.size = canvas_size
        self.cfg = cfg
        self._overlay: Optional[Image.Image] = None
        self._pos: Tuple[int, int] = (0, 0)
        self._build()

    def _build(self):
        cfg = self.cfg
        if not (cfg.enabled and cfg.path and Path(cfg.path).exists()):
            self._overlay = None
            return
        try:
            src = Image.open(cfg.path).convert("RGBA")
        except OSError:
            self._overlay = None
            return

        w, h = self.size
        diameter = max(24, int(min(w, h) * cfg.size_pct))
        # Aspect-preserving fit into a diameter x diameter box
        ratio = min(diameter / src.width, diameter / src.height)
        new_w = max(1, int(src.width * ratio))
        new_h = max(1, int(src.height * ratio))
        src = src.resize((new_w, new_h), Image.LANCZOS)
        # Pad into square so circular crop is centered
        canvas = Image.new("RGBA", (diameter, diameter), (0, 0, 0, 0))
        canvas.paste(src, ((diameter - new_w) // 2, (diameter - new_h) // 2), src)

        if cfg.circular:
            mask = Image.new("L", (diameter, diameter), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, diameter, diameter), fill=255)
            result = Image.new("RGBA", (diameter, diameter), (0, 0, 0, 0))
            result.paste(canvas, (0, 0), mask)
            canvas = result

        if cfg.border:
            border_px = max(1, int(min(w, h) * cfg.border_width_pct))
            outline = Image.new("RGBA", (diameter, diameter), (0, 0, 0, 0))
            d = ImageDraw.Draw(outline)
            if cfg.circular:
                d.ellipse([border_px // 2, border_px // 2,
                           diameter - border_px // 2, diameter - border_px // 2],
                          outline=cfg.border_color + (255,), width=border_px)
            else:
                d.rectangle([0, 0, diameter - 1, diameter - 1],
                            outline=cfg.border_color + (255,), width=border_px)
            canvas.alpha_composite(outline)

        if cfg.shadow:
            shadow_size = diameter + 24
            shadow = Image.new("RGBA", (shadow_size, shadow_size), (0, 0, 0, 0))
            ImageDraw.Draw(shadow).ellipse((12, 12, shadow_size - 12, shadow_size - 12),
                                            fill=(0, 0, 0, 130))
            shadow = shadow.filter(ImageFilter.GaussianBlur(radius=10))
            wrap = Image.new("RGBA", (shadow_size, shadow_size), (0, 0, 0, 0))
            wrap.alpha_composite(shadow)
            wrap.alpha_composite(canvas, (12, 12))
            canvas = wrap
            diameter = shadow_size

        if cfg.opacity < 1.0:
            r, g, b, a = canvas.split()
            a = a.point(lambda v: int(v * cfg.opacity))
            canvas = Image.merge("RGBA", (r, g, b, a))

        self._overlay = canvas

        fx, fy = POSITIONS.get(cfg.position, POSITIONS["Top Right"])
        cx = int(w * fx)
        cy = int(h * fy)
        self._pos = (cx - diameter // 2, cy - diameter // 2)

    def composite(self, frame: Image.Image) -> Image.Image:
        if self._overlay is None:
            return frame
        frame.alpha_composite(self._overlay, self._pos)
        return frame
