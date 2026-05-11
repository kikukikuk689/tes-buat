"""Logo overlay (circular optional, custom position/size)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter

ANCHORS = (
    "top-left", "top-center", "top-right",
    "middle-left", "center", "middle-right",
    "bottom-left", "bottom-center", "bottom-right",
)


@dataclass
class LogoConfig:
    path: Optional[str] = None
    enabled: bool = True
    circular: bool = True
    anchor: str = "top-right"
    size_ratio: float = 0.12       # fraksi panjang sisi terpendek video
    margin: int = 24
    offset_x: int = 0
    offset_y: int = 0
    alpha: float = 1.0
    border_color: Tuple[int, int, int] = (255, 255, 255)
    border_width: int = 0


class LogoOverlay:
    """Prepare & cache logo image, then paste tiap frame."""

    def __init__(self, cfg: LogoConfig, frame_size: Tuple[int, int]):
        self.cfg = cfg
        self.frame_size = frame_size
        self._cached: Optional[Image.Image] = None
        self._cached_pos: Optional[Tuple[int, int]] = None
        self._rebuild()

    def update(self, cfg: LogoConfig) -> None:
        self.cfg = cfg
        self._rebuild()

    def _rebuild(self) -> None:
        cfg = self.cfg
        self._cached = None
        if not cfg.enabled or not cfg.path:
            return
        p = Path(cfg.path)
        if not p.exists():
            return
        try:
            im = Image.open(p).convert("RGBA")
        except OSError:
            return

        w_video, h_video = self.frame_size
        target = max(16, int(min(w_video, h_video) * cfg.size_ratio))
        # square crop to target
        ratio = target / max(im.width, im.height)
        new_w = max(1, int(im.width * ratio))
        new_h = max(1, int(im.height * ratio))
        im = im.resize((new_w, new_h), Image.LANCZOS)

        if cfg.circular:
            side = min(new_w, new_h)
            # center crop
            cx, cy = new_w // 2, new_h // 2
            crop = im.crop((cx - side // 2, cy - side // 2,
                            cx - side // 2 + side, cy - side // 2 + side))
            mask = Image.new("L", crop.size, 0)
            d = ImageDraw.Draw(mask)
            d.ellipse([0, 0, side - 1, side - 1], fill=255)
            mask = mask.filter(ImageFilter.GaussianBlur(0.6))
            crop.putalpha(mask)
            im = crop

        if cfg.border_width > 0:
            bw = cfg.border_width
            new = Image.new("RGBA", (im.width + bw * 2, im.height + bw * 2), (0, 0, 0, 0))
            d = ImageDraw.Draw(new)
            if cfg.circular:
                d.ellipse([0, 0, new.width - 1, new.height - 1],
                          outline=(*cfg.border_color, 255), width=bw)
            else:
                d.rectangle([0, 0, new.width - 1, new.height - 1],
                            outline=(*cfg.border_color, 255), width=bw)
            new.alpha_composite(im, (bw, bw))
            im = new

        # apply alpha
        if cfg.alpha < 0.999:
            a = im.split()[-1].point(lambda v: int(v * max(0.0, min(1.0, cfg.alpha))))
            im.putalpha(a)

        # Calculate position
        pos = self._anchor_pos(im.size)
        self._cached = im
        self._cached_pos = pos

    def _anchor_pos(self, size: Tuple[int, int]) -> Tuple[int, int]:
        W, H = self.frame_size
        w, h = size
        m = self.cfg.margin
        ax = self.cfg.anchor
        if ax.endswith("left"):
            x = m
        elif ax.endswith("center"):
            x = (W - w) // 2
        else:
            x = W - w - m
        if ax.startswith("top"):
            y = m
        elif ax.startswith("middle"):
            y = (H - h) // 2
        else:
            y = H - h - m
        x += self.cfg.offset_x
        y += self.cfg.offset_y
        return x, y

    def draw(self, im: Image.Image) -> None:
        if self._cached is None or self._cached_pos is None:
            return
        im.alpha_composite(self._cached, self._cached_pos)
