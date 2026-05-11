"""Batch rendering across folders of music + lyrics + backgrounds."""
from __future__ import annotations

import dataclasses
import os
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from .renderer import RenderConfig, Renderer
from .background_handler import BackgroundConfig, is_image, is_video, IMG_EXT, VID_EXT
from ..utils.logger import AppLogger


AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".mp4"}
LRC_EXT = {".lrc"}


def _normalize_name(s: str) -> str:
    s = re.sub(r"[\W_]+", "", s).lower()
    return s


def _list_files(folder: str, ext_set: set) -> List[str]:
    p = Path(folder)
    if not p.is_dir():
        return []
    return sorted(str(f) for f in p.iterdir()
                  if f.is_file() and f.suffix.lower() in ext_set)


@dataclass
class BatchConfig:
    music_folder: str
    lyrics_folder: Optional[str] = None
    bg_folder: Optional[str] = None
    bg_strategy: str = "Order"      # "Order" / "Match by Name" / "Random"
    bg_multi_mode: str = "Single"   # for Order/Random: "Single" / "Multi"
    output_folder: str = "output/render"
    base_render: Optional[RenderConfig] = None


def _find_lyric_for(audio_path: str, lyrics_dir: Optional[str]) -> Optional[str]:
    if not lyrics_dir:
        return None
    stem = Path(audio_path).stem
    norm = _normalize_name(stem)
    candidates = _list_files(lyrics_dir, LRC_EXT)
    for c in candidates:
        cstem = Path(c).stem
        cn = _normalize_name(cstem)
        if cn == norm or norm in cn or cn in norm:
            return c
    return None


def _bg_files_for(audio_path: str, idx: int, audio_count: int,
                  bg_files: List[str], cfg: BatchConfig) -> List[str]:
    if not bg_files:
        return []
    strat = cfg.bg_strategy
    multi = cfg.bg_multi_mode == "Multi"
    if strat == "Match by Name":
        norm = _normalize_name(Path(audio_path).stem)
        match = None
        for b in bg_files:
            if _normalize_name(Path(b).stem) == norm:
                match = b
                break
        if match:
            return [match]
        # fall back to order
        return [bg_files[idx % len(bg_files)]]
    if strat == "Random":
        if multi:
            n = min(len(bg_files), max(2, len(bg_files) // 2))
            return random.sample(bg_files, n)
        return [random.choice(bg_files)]
    # Order
    if multi:
        return list(bg_files)
    return [bg_files[idx % len(bg_files)]]


def list_batch_pairs(cfg: BatchConfig) -> List[dict]:
    """Resolve the file pairings before actually rendering, for preview."""
    audio = _list_files(cfg.music_folder, AUDIO_EXT)
    bg_files = _list_files(cfg.bg_folder, IMG_EXT | VID_EXT) if cfg.bg_folder else []
    result = []
    for i, a in enumerate(audio):
        lyric = _find_lyric_for(a, cfg.lyrics_folder)
        bgs = _bg_files_for(a, i, len(audio), bg_files, cfg)
        result.append({"audio": a, "lyric": lyric, "background": bgs})
    return result


def run_batch(cfg: BatchConfig,
              progress: Optional[Callable[[int, int, float, str], None]] = None,
              cancel_flag: Optional[Callable[[], bool]] = None) -> List[dict]:
    """Render every track in the music folder.

    ``progress(i, total, ratio, message)`` is called for each track and during
    rendering.  ``cancel_flag`` is an optional callable returning True to
    stop early.  Returns a list of result dicts {audio, output, ok}.
    """
    log = AppLogger.get()
    pairs = list_batch_pairs(cfg)
    total = len(pairs)
    Path(cfg.output_folder).mkdir(parents=True, exist_ok=True)

    results = []
    for i, pair in enumerate(pairs):
        if cancel_flag and cancel_flag():
            break
        a = pair["audio"]
        log.info(f"[Batch {i+1}/{total}] Render {Path(a).name}")
        base = cfg.base_render
        if base is None:
            from .renderer import RenderConfig as RC  # avoid circular
            base = RC(audio_input=a)
        rc = dataclasses.replace(base, audio_input=a)
        # Per-track output path inside batch output folder
        out_name = Path(a).stem + ".mp4"
        rc.output_path = str(Path(cfg.output_folder) / out_name)
        rc.lyrics_input = pair["lyric"]
        rc.background = dataclasses.replace(
            rc.background,
            files=pair["background"],
            multi_mode=("Multi" if len(pair["background"]) > 1 else "Single"),
            multi_strategy=(cfg.bg_strategy if cfg.bg_strategy in ("Order", "Random") else "Order"),
        )
        renderer = Renderer(rc)

        def _p(ratio: float, msg: str, idx=i):
            if progress:
                progress(idx, total, ratio, msg)

        ok = False
        try:
            ok = renderer.render(progress=_p)
        except Exception as exc:  # pragma: no cover
            log.error(f"Render gagal: {exc}")
        results.append({"audio": a, "output": rc.output_path, "ok": ok})
    return results
