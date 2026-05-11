"""Penemuan & manajemen font lirik."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, List

from PIL import ImageFont

# Bundled font directory
_BUNDLED_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"

# Some common system font directories
_SYSTEM_DIRS = [
    Path("C:/Windows/Fonts"),
    Path("/Library/Fonts"),
    Path("/System/Library/Fonts"),
    Path("/usr/share/fonts"),
    Path("/usr/local/share/fonts"),
    Path.home() / ".local/share/fonts",
    Path.home() / ".fonts",
]

# Preferred fallback names if bundled fonts missing
_PREFERRED = [
    "DejaVuSans-Bold.ttf",
    "DejaVuSans.ttf",
    "LiberationSans-Bold.ttf",
    "LiberationSans-Regular.ttf",
    "NotoSans-Bold.ttf",
    "NotoSans-Regular.ttf",
    "FreeSans.ttf",
    "FreeSansBold.ttf",
    "Arial.ttf",
    "arialbd.ttf",
    "ARIAL.TTF",
    "Verdana.ttf",
    "verdanab.ttf",
    "Tahoma.ttf",
    "tahomabd.ttf",
    "Calibri.ttf",
    "calibrib.ttf",
    "TimesNewRoman.ttf",
    "Georgia.ttf",
    "georgiab.ttf",
    "Comic.ttf",
    "ImpactRegular.ttf",
    "impact.ttf",
    "Roboto-Regular.ttf",
    "Roboto-Bold.ttf",
    "OpenSans-Bold.ttf",
    "OpenSans-Regular.ttf",
    "Montserrat-Bold.ttf",
    "Lato-Bold.ttf",
    "Poppins-Bold.ttf",
    "Inter-Bold.ttf",
    "Oswald-Bold.ttf",
    "Raleway-Bold.ttf",
    "Quicksand-Bold.ttf",
    "PlayfairDisplay-Bold.ttf",
    "Anton-Regular.ttf",
    "BebasNeue-Regular.ttf",
    "PT_Sans-Bold.ttf",
    "Ubuntu-B.ttf",
    "Ubuntu-R.ttf",
]


def _index_dir(d: Path, out: Dict[str, Path]) -> None:
    if not d.exists():
        return
    for p in d.rglob("*"):
        if p.suffix.lower() in {".ttf", ".otf"} and p.is_file():
            name = p.stem
            # Prefer first occurrence
            if name not in out:
                out[name] = p


def list_available_fonts() -> Dict[str, Path]:
    """Return mapping {font_display_name: path}."""
    fonts: Dict[str, Path] = {}
    _index_dir(_BUNDLED_DIR, fonts)
    for d in _SYSTEM_DIRS:
        _index_dir(d, fonts)
    return dict(sorted(fonts.items(), key=lambda kv: kv[0].lower()))


def load_font(name_or_path: str | None, size: int) -> ImageFont.FreeTypeFont:
    """Load a TrueType font. Falls back to PIL default if unavailable."""
    if name_or_path:
        path = Path(name_or_path)
        if path.is_file():
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                pass
        # Try lookup by name
        all_fonts = list_available_fonts()
        if name_or_path in all_fonts:
            try:
                return ImageFont.truetype(str(all_fonts[name_or_path]), size)
            except OSError:
                pass
        # Search by stem
        for n, p in all_fonts.items():
            if n.lower() == name_or_path.lower():
                try:
                    return ImageFont.truetype(str(p), size)
                except OSError:
                    pass

    # Try preferred list across system dirs
    for d in _SYSTEM_DIRS + [_BUNDLED_DIR]:
        for fn in _PREFERRED:
            cand = d / fn
            if cand.is_file():
                try:
                    return ImageFont.truetype(str(cand), size)
                except OSError:
                    continue
            # try recursive single search
            try:
                for p in d.rglob(fn):
                    try:
                        return ImageFont.truetype(str(p), size)
                    except OSError:
                        pass
            except (OSError, ValueError):
                pass

    return ImageFont.load_default()


def default_font_name() -> str | None:
    """Pick a sensible default display name."""
    fonts = list_available_fonts()
    for pref in ("DejaVuSans-Bold", "LiberationSans-Bold", "NotoSans-Bold",
                 "Arial Bold", "arialbd", "Roboto-Bold", "Inter-Bold"):
        if pref in fonts:
            return pref
    return next(iter(fonts), None)
