"""
Project state model.

All positional values are stored as **normalized coordinates** in [0.0, 1.0]
relative to the OUTPUT canvas (9:16). This guarantees drag positions in
the preview map *exactly* to the rendered output regardless of preview
size or final resolution.

(x, y) refers to the CENTER of the element. The anchor is the center so
that horizontal/vertical centering math is simple and the rendered
result matches what the user sees in preview.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


# Output canvas aspect = 9:16. Reference height for font-size math = 1920.
OUTPUT_ASPECT_W = 9
OUTPUT_ASPECT_H = 16
REFERENCE_HEIGHT = 1920


class BackgroundMode(str, Enum):
    FIT_BLUR = "fit_blur"
    FIT_BLACK = "fit_black"
    FILL_CROP = "fill_crop"
    FIT_CUSTOM = "fit_custom"


class LogoMotion(str, Enum):
    NONE = "none"
    CIRCLE = "circle"        # like the digit "0"
    FIGURE8 = "figure8"      # like the digit "8"
    BOUNCE = "bounce"        # vertical bounce


class OverlayKey(str, Enum):
    AUTO = "auto"
    GREEN = "green"
    BLACK = "black"
    WHITE = "white"


@dataclass
class TextItem:
    """A draggable text overlay."""
    text: str = "Sample Text"
    # Normalized center position. Default = visually centered, slightly above bottom.
    x: float = 0.5
    y: float = 0.85
    font_family: str = "Arial"
    font_size: int = 64           # in REFERENCE_HEIGHT pixels (scaled to output)
    color: str = "#FFFFFF"
    bold: bool = True
    italic: bool = False
    stroke_color: str = "#000000"
    stroke_width: int = 4         # in REFERENCE_HEIGHT pixels
    bg_box: bool = False
    bg_color: str = "#000000"
    bg_opacity: float = 0.5


@dataclass
class PartTextSettings:
    """
    Auto Part/Clip text. Inserted on every split clip with auto-incrementing
    number. Position is normalized & drag-precise like any other text.
    """
    enabled: bool = False
    label: str = "Part"           # e.g. "Part" or "Clip"
    start_index: int = 1
    x: float = 0.5
    y: float = 0.12
    font_family: str = "Arial"
    font_size: int = 80
    color: str = "#FFFFFF"
    bold: bool = True
    italic: bool = False
    stroke_color: str = "#000000"
    stroke_width: int = 5


@dataclass
class LogoItem:
    path: Optional[str] = None
    # Normalized center position
    x: float = 0.5
    y: float = 0.1
    # Normalized size: width as fraction of output width
    size: float = 0.18
    opacity: float = 1.0
    motion: LogoMotion = LogoMotion.NONE
    motion_amplitude: float = 0.05   # normalized radius (relative to output width/height)
    motion_period_s: float = 4.0      # seconds per cycle


@dataclass
class OverlayItem:
    path: Optional[str] = None
    key: OverlayKey = OverlayKey.AUTO
    opacity: float = 1.0
    similarity: float = 0.30
    blend: float = 0.10


@dataclass
class SplitSettings:
    enabled: bool = False
    seconds_per_clip: int = 50


@dataclass
class RenderSettings:
    # 9:16 presets. height drives the math; width = height * 9/16.
    output_height: int = 1920       # 1920 = 1080x1920, 2560 = 1440x2560 (2K)
    fps: int = 30
    crf: int = 20                    # x264 quality (lower = better)
    preset: str = "medium"
    output_dir: str = ""             # user-selected
    file_prefix: str = "verticlip"

    @property
    def output_width(self) -> int:
        # Snap to even number (ffmpeg requirement)
        w = int(round(self.output_height * OUTPUT_ASPECT_W / OUTPUT_ASPECT_H))
        return w - (w % 2)


@dataclass
class Project:
    source_video: Optional[str] = None
    background_mode: BackgroundMode = BackgroundMode.FIT_BLUR
    custom_bg_path: Optional[str] = None     # used when background_mode == FIT_CUSTOM
    texts: List[TextItem] = field(default_factory=list)
    part_text: PartTextSettings = field(default_factory=PartTextSettings)
    logo: LogoItem = field(default_factory=LogoItem)
    overlay: OverlayItem = field(default_factory=OverlayItem)
    split: SplitSettings = field(default_factory=SplitSettings)
    render: RenderSettings = field(default_factory=RenderSettings)
