"""Batch processing pipeline.

User selects:
- folder musik (wajib)
- folder lirik (opsional)
- folder background (opsional)
- strategi pencocokan: order | name | random
- untuk order/random: single (1 bg) atau multi (banyak bg per video)
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Callable, List, Optional, Sequence

from ..core.background import (
    BackgroundConfig,
    IMAGE_EXT,
    VIDEO_EXT,
    gather_media,
    is_image,
    is_video,
)
from ..core.renderer import RenderJob, render
from ..utils.logger import get_logger

_log = get_logger("batch")

AUDIO_EXT = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac", ".opus"}
LRC_EXT = {".lrc", ".txt"}


class BatchStrategy(str, Enum):
    ORDER = "order"      # by sorted file order
    NAME = "name"        # by filename match
    RANDOM = "random"


@dataclass
class BatchConfig:
    music_folder: str
    lyrics_folder: Optional[str] = None
    background_folder: Optional[str] = None
    output_folder: str = "output"
    strategy: BatchStrategy = BatchStrategy.ORDER
    multi_background: bool = False    # untuk order/random: multi=banyak bg per video
    per_clip_seconds: float = 6.0
    template: RenderJob = field(default_factory=lambda: RenderJob(audio_path="", output_path=""))


@dataclass
class BatchJob:
    audio: Path
    lrc: Optional[Path]
    backgrounds: List[Path]
    output: Path


# ============================================================
# File matching helpers
# ============================================================

_SAFE = re.compile(r"[^a-z0-9]+")


def _normalize(name: str) -> str:
    return _SAFE.sub("", name.lower())


def _gather_audio(folder: Path) -> List[Path]:
    return sorted(p for p in folder.iterdir()
                  if p.is_file() and p.suffix.lower() in AUDIO_EXT)


def _gather_lrc(folder: Path) -> List[Path]:
    return sorted(p for p in folder.iterdir()
                  if p.is_file() and p.suffix.lower() in LRC_EXT)


def _match_by_name(audio: Path, candidates: Sequence[Path]) -> Optional[Path]:
    """Cari kandidat dengan nama (tanpa ekstensi) paling mirip."""
    target = _normalize(audio.stem)
    if not target:
        return None
    # Exact normalized
    for c in candidates:
        if _normalize(c.stem) == target:
            return c
    # Contains
    for c in candidates:
        nc = _normalize(c.stem)
        if target in nc or nc in target:
            return c
    return None


# ============================================================
# Batch planning
# ============================================================

def plan_batch(cfg: BatchConfig) -> List[BatchJob]:
    music_dir = Path(cfg.music_folder)
    if not music_dir.exists():
        raise FileNotFoundError(f"Folder musik tidak ada: {music_dir}")

    audios = _gather_audio(music_dir)
    if not audios:
        raise RuntimeError(f"Tidak ada file audio di {music_dir}")

    lyrics_dir = Path(cfg.lyrics_folder) if cfg.lyrics_folder else None
    bg_dir = Path(cfg.background_folder) if cfg.background_folder else None
    out_dir = Path(cfg.output_folder)
    out_dir.mkdir(parents=True, exist_ok=True)

    lrcs = _gather_lrc(lyrics_dir) if lyrics_dir and lyrics_dir.exists() else []
    bgs = gather_media(bg_dir) if bg_dir and bg_dir.exists() else []

    rng = random.Random(0xC0FFEE)
    jobs: List[BatchJob] = []

    for i, audio in enumerate(audios):
        # Lyrics matching: always by name when present
        lrc: Optional[Path] = None
        if lrcs:
            lrc = _match_by_name(audio, lrcs)
            if lrc is None:
                # fallback: by order
                lrc = lrcs[i % len(lrcs)] if cfg.strategy != BatchStrategy.RANDOM else rng.choice(lrcs)

        # Background matching
        backgrounds: List[Path] = []
        if bgs:
            if cfg.strategy == BatchStrategy.NAME:
                m = _match_by_name(audio, bgs)
                if m:
                    backgrounds = [m]
                else:
                    backgrounds = [bgs[i % len(bgs)]]
            elif cfg.strategy == BatchStrategy.ORDER:
                if cfg.multi_background:
                    backgrounds = list(bgs)
                else:
                    backgrounds = [bgs[i % len(bgs)]]
            elif cfg.strategy == BatchStrategy.RANDOM:
                if cfg.multi_background:
                    shuffled = list(bgs)
                    rng.shuffle(shuffled)
                    backgrounds = shuffled
                else:
                    backgrounds = [rng.choice(bgs)]

        out_path = out_dir / f"{audio.stem}.mp4"
        jobs.append(BatchJob(audio=audio, lrc=lrc, backgrounds=backgrounds, output=out_path))
    return jobs


# ============================================================
# Execution
# ============================================================

def _build_render_job(template: RenderJob, bjob: BatchJob,
                      per_clip_seconds: float) -> RenderJob:
    bg_paths = [str(p) for p in bjob.backgrounds]
    new_bg = replace(template.background, paths=bg_paths,
                     per_clip_seconds=per_clip_seconds,
                     enabled=bool(bg_paths) and template.background.enabled)
    job = replace(
        template,
        audio_path=str(bjob.audio),
        output_path=str(bjob.output),
        lrc_path=str(bjob.lrc) if bjob.lrc else None,
        background=new_bg,
    )
    return job


def run_batch(cfg: BatchConfig,
              progress_cb: Optional[Callable[[int, int, str, float], None]] = None,
              cancel_check: Optional[Callable[[], bool]] = None) -> List[Path]:
    """Jalankan batch. ``progress_cb(idx, total, name, frac)``."""
    jobs = plan_batch(cfg)
    total = len(jobs)
    _log.info("Batch plan: %d job", total)
    done: List[Path] = []
    for i, bjob in enumerate(jobs):
        if cancel_check and cancel_check():
            _log.warning("Batch dibatalkan setelah %d/%d", i, total)
            break
        _log.info("[%d/%d] %s", i + 1, total, bjob.audio.name)
        rjob = _build_render_job(cfg.template, bjob, cfg.per_clip_seconds)

        def _job_progress(frac: float, msg: str, _i=i, _name=bjob.audio.name) -> None:
            if progress_cb:
                try:
                    progress_cb(_i + 1, total, _name, frac)
                except Exception:  # noqa: BLE001
                    pass

        try:
            out = render(rjob, progress_cb=_job_progress)
            done.append(Path(out))
        except Exception as e:  # noqa: BLE001
            _log.exception("Gagal render %s: %s", bjob.audio.name, e)
    return done
