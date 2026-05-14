"""Font discovery + resolution to a usable font file for FFmpeg."""
from __future__ import annotations

import platform
from pathlib import Path
from typing import Dict, List, Optional


_SYSTEM_FONT_DIRS_LINUX = [
    "/usr/share/fonts",
    "/usr/local/share/fonts",
    str(Path.home() / ".fonts"),
    str(Path.home() / ".local/share/fonts"),
]
_SYSTEM_FONT_DIRS_MAC = [
    "/System/Library/Fonts",
    "/Library/Fonts",
    str(Path.home() / "Library/Fonts"),
]
_SYSTEM_FONT_DIRS_WIN = [
    r"C:\Windows\Fonts",
    str(Path.home() / "AppData/Local/Microsoft/Windows/Fonts"),
]


def _font_dirs() -> List[str]:
    system = platform.system()
    if system == "Windows":
        return _SYSTEM_FONT_DIRS_WIN
    if system == "Darwin":
        return _SYSTEM_FONT_DIRS_MAC
    return _SYSTEM_FONT_DIRS_LINUX


# Build a {family_lower: full_path} map of TTF/OTF font files. Family is
# inferred from the file stem (good enough for FFmpeg drawtext fontfile).
_cache: Optional[Dict[str, str]] = None


def font_map() -> Dict[str, str]:
    global _cache
    if _cache is not None:
        return _cache

    mapping: Dict[str, str] = {}
    for d in _font_dirs():
        p = Path(d)
        if not p.exists():
            continue
        for ext in (".ttf", ".otf", ".ttc"):
            for fp in p.rglob(f"*{ext}"):
                key = fp.stem.lower()
                mapping.setdefault(key, str(fp))
    _cache = mapping
    return mapping


def list_families() -> List[str]:
    """Return a sorted, de-duplicated list of font *family* names.

    We derive families from filenames so the list is portable across
    platforms; users can also see the raw filename in case of doubt.
    """
    fonts = font_map()
    families = set()
    for stem in fonts.keys():
        # Trim common weight/style suffixes for a friendlier family name.
        family = stem
        for suffix in (
            "-regular", "-bold", "-italic", "-bolditalic", "-light",
            "-medium", "-thin", "-black", "-semibold", "-extrabold",
            " regular", " bold", " italic", " bolditalic",
        ):
            if family.endswith(suffix):
                family = family[: -len(suffix)]
                break
        families.add(family.title())
    out = sorted(families)
    return out


def resolve_font_file(family: str) -> Optional[str]:
    """Find a font file matching a family name (best-effort)."""
    fonts = font_map()
    if not fonts:
        return None
    fam = family.lower()
    # Prefer regular weight
    candidates_order = [
        f"{fam}-regular",
        fam,
        f"{fam}-medium",
        f"{fam}-bold",
        f"{fam} regular",
        f"{fam} medium",
        f"{fam} bold",
    ]
    for key in candidates_order:
        if key in fonts:
            return fonts[key]
    # Fallback: any file whose stem starts with the family
    for stem, path in fonts.items():
        if stem.startswith(fam):
            return path
    # Last-resort fallback to *something* readable.
    fallbacks = (
        "dejavusans", "dejavusans-bold", "liberationsans-regular",
        "arial", "verdana", "sans-serif",
    )
    for fb in fallbacks:
        if fb in fonts:
            return fonts[fb]
    # Return any
    return next(iter(fonts.values()), None)
