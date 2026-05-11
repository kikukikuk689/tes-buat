"""Lyric font discovery and loading.

Provides a clean list of font families the user can pick from.  The set
combines:
    1) Common system fonts that look great for music videos (Montserrat,
       Roboto, Poppins, etc) when installed.
    2) Bundled fallback fonts shipped under ``app/assets/fonts``.
    3) DejaVu / Liberation that exist on most Linux installs and serve as a
       last resort so the app never fails to render text.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from PIL import ImageFont


SEARCH_PATHS = []
if sys.platform.startswith("win"):
    SEARCH_PATHS = [Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"]
elif sys.platform == "darwin":
    SEARCH_PATHS = [Path("/Library/Fonts"), Path("/System/Library/Fonts"),
                    Path.home() / "Library/Fonts"]
else:
    SEARCH_PATHS = [
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
        Path.home() / ".fonts",
        Path.home() / ".local/share/fonts",
    ]

BUNDLED_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"

PREFERRED_FAMILIES = [
    "Montserrat",
    "Poppins",
    "Roboto",
    "Roboto Condensed",
    "Inter",
    "Lato",
    "Oswald",
    "Bebas Neue",
    "Raleway",
    "Open Sans",
    "Quicksand",
    "Nunito",
    "Source Sans Pro",
    "Playfair Display",
    "Merriweather",
    "Pacifico",
    "Dancing Script",
    "Great Vibes",
    "Lobster",
    "Caveat",
    "Comfortaa",
    "Anton",
    "Righteous",
    "Bungee",
    "Permanent Marker",
    "DejaVu Sans",
    "Liberation Sans",
    "Noto Sans",
    "Arial",
    "Verdana",
    "Tahoma",
]


@dataclass
class FontInfo:
    family: str
    path: str

    def __str__(self) -> str:
        return self.family


def _scan_fonts(roots: List[Path]) -> Dict[str, str]:
    """Return mapping {display_family_name: path_to_ttf}."""
    found: Dict[str, str] = {}
    for root in roots:
        if not root.exists():
            continue
        try:
            for p in root.rglob("*"):
                if p.is_file() and p.suffix.lower() in {".ttf", ".otf"}:
                    name = _family_from_filename(p.stem)
                    if name and name not in found:
                        found[name] = str(p)
        except (PermissionError, OSError):
            continue
    return found


def _family_from_filename(stem: str) -> str:
    parts = stem.replace("_", " ").replace("-", " ").split()
    keep = []
    drop = {"regular", "bold", "italic", "medium", "light", "semibold", "thin",
            "extrabold", "extralight", "black", "oblique", "condensed", "narrow"}
    for part in parts:
        if part.lower() in drop:
            continue
        keep.append(part)
    return " ".join(keep).strip() or stem


def discover_fonts() -> List[FontInfo]:
    """Return ordered list of available fonts: preferred families first."""
    available = _scan_fonts([BUNDLED_DIR, *SEARCH_PATHS])

    result: List[FontInfo] = []
    used = set()

    # 1. Preferred families that exist.
    for fam in PREFERRED_FAMILIES:
        if fam in available and fam not in used:
            result.append(FontInfo(family=fam, path=available[fam]))
            used.add(fam)

    # 2. Anything else discovered, alphabetical.
    for fam in sorted(available):
        if fam in used:
            continue
        # Skip ugly system-only font families.
        if fam.lower().startswith(("noto color", "symbola", "wingdings")):
            continue
        result.append(FontInfo(family=fam, path=available[fam]))
        used.add(fam)

    # Always include a fallback so the GUI is never empty.
    if not result:
        result.append(FontInfo(family="Default", path=""))
    return result


_FONT_CACHE: Dict[tuple, ImageFont.FreeTypeFont] = {}


def load_font(family_or_path: str, size: int) -> ImageFont.FreeTypeFont:
    """Load a font, caching by (path, size)."""
    key = (family_or_path, size)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]

    # Direct path?
    if family_or_path and os.path.exists(family_or_path):
        try:
            font = ImageFont.truetype(family_or_path, size=size)
            _FONT_CACHE[key] = font
            return font
        except OSError:
            pass

    # Family name -> path
    families = {f.family: f.path for f in discover_fonts()}
    path = families.get(family_or_path)
    if path:
        try:
            font = ImageFont.truetype(path, size=size)
            _FONT_CACHE[key] = font
            return font
        except OSError:
            pass

    # Final fallback
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", size=size)
    except OSError:
        font = ImageFont.load_default()
    _FONT_CACHE[key] = font
    return font
