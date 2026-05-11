"""CLI tool untuk render headless (testing/automation)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

from .core.background import BackgroundConfig
from .core.renderer import RenderJob, render
from .effects.effects import EffectConfig
from .overlays.logo import LogoConfig
from .overlays.lyrics import LyricsConfig
from .spectrum.styles import SpectrumConfig, list_palettes, list_styles
from .effects.effects import list_effects
from .utils.logger import get_logger, log_session_header


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="musicviz", description="Render music spectrum video.")
    p.add_argument("--audio", required=True, help="Path audio file (mp3/wav/...).")
    p.add_argument("--output", required=True, help="Path output mp4.")
    p.add_argument("--lrc", default=None, help="Path file LRC (optional).")
    p.add_argument("--background", nargs="*", default=[], help="Background image/video paths.")
    p.add_argument("--resolution", default="720p",
                   help="360p|480p|720p|1080p|1440p|2160p|custom")
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--style", default="Bars", choices=list_styles())
    p.add_argument("--palette", default="Aurora", choices=list_palettes())
    p.add_argument("--effect", default="None", choices=list_effects())
    p.add_argument("--effect-intensity", type=float, default=0.6)
    p.add_argument("--logo", default=None)
    p.add_argument("--logo-anchor", default="top-right")
    p.add_argument("--logo-circular", action="store_true", default=True)
    p.add_argument("--logo-size", type=float, default=0.12)
    p.add_argument("--encoder", default="libx264")
    p.add_argument("--preset", default="veryfast")
    p.add_argument("--crf", type=int, default=21)
    p.add_argument("--bitrate", type=int, default=4500)
    p.add_argument("--n-bands", type=int, default=64)
    p.add_argument("--height-ratio", type=float, default=0.28)
    p.add_argument("--density", type=float, default=1.0)
    p.add_argument("--padding", type=int, default=18)
    p.add_argument("--glow", type=float, default=1.0)
    p.add_argument("--font", default=None)
    p.add_argument("--limit-seconds", type=float, default=0.0,
                   help="(testing) Hard cap duration via ffmpeg -t after render.")
    return p


def main(argv: List[str] | None = None) -> int:
    log_session_header()
    args = build_parser().parse_args(argv)
    job = RenderJob(
        audio_path=args.audio,
        output_path=args.output,
        lrc_path=args.lrc,
        background=BackgroundConfig(paths=list(args.background), enabled=bool(args.background)),
        spectrum=SpectrumConfig(
            style=args.style,
            palette=args.palette,
            n_bands=args.n_bands,
            height_ratio=args.height_ratio,
            density=args.density,
            glow=args.glow,
            bottom_padding=args.padding,
        ),
        effects=([] if args.effect == "None"
                 else [EffectConfig(name=args.effect, intensity=args.effect_intensity)]),
        logo=LogoConfig(path=args.logo, enabled=bool(args.logo),
                        circular=args.logo_circular, anchor=args.logo_anchor,
                        size_ratio=args.logo_size),
        lyrics=LyricsConfig(font_name=args.font),
        resolution=args.resolution,
        fps=args.fps,
        encoder=args.encoder,
        preset=args.preset,
        crf=args.crf,
        bitrate_kbps=args.bitrate,
    )
    out = render(job, progress_cb=lambda f, m: get_logger().info("%.0f%% %s", f * 100, m))
    print("OK:", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
