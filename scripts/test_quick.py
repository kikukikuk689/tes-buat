"""Quick test: render the first ~30 seconds of the supplied sample.

Useful to confirm the pipeline before doing the full GUI test.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import subprocess

from app.core.renderer import Renderer, RenderConfig, RESOLUTIONS
from app.core.spectrum_styles import SpectrumConfig
from app.core.background_handler import BackgroundConfig
from app.core.logo_handler import LogoConfig
from app.utils.logger import AppLogger


SAMPLES_DIR = ROOT / "samples"
SAMPLES_DIR.mkdir(exist_ok=True)
OUT_DIR = ROOT / "output" / "render"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def trim_audio(src: str, dst: str, seconds: float) -> None:
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", src, "-t", str(seconds),
        "-c:v", "copy", "-c:a", "copy",
        dst,
    ], check=True)


def main():
    audio = "/home/ubuntu/attachments/6d3059a4-6cc1-4af3-b9ca-7180337a6a8c/Rindu+di+Malam+Ini.mp4"
    lyrics = "/home/ubuntu/attachments/f1f493fe-e271-4617-a243-49551c1a992b/lirik_Rindu+di+Malam+Ini.lrc"
    background = "/home/ubuntu/attachments/43ff1645-6c2c-4ba4-8c75-e24624b4619f/background.jpg"

    short = str(SAMPLES_DIR / "rindu_30s.mp4")
    trim_audio(audio, short, 35.0)

    cfg = RenderConfig(
        audio_input=short,
        lyrics_input=lyrics,
        output_path=str(OUT_DIR / "test_quick.mp4"),
        resolution="720p (1280x720)",
        fps=24,
        encoder_preset="veryfast",
        crf=22,
    )
    cfg.spectrum = SpectrumConfig(style="Bars", palette="Aurora",
                                  height_ratio=0.22, density=0.85,
                                  glow=0.6)
    cfg.background = BackgroundConfig(files=[background], blur=0.25, darken=0.30,
                                       zoom_pulse=True)
    cfg.effect_name = "Fireflies"
    cfg.effect_intensity = 1.0
    cfg.lyric.font_family = "DejaVu Sans"
    cfg.lyric.font_size_pct = 0.06
    cfg.lyric.position_pct = 0.78

    AppLogger.get().info("Quick test render starting")
    r = Renderer(cfg)
    ok = r.render(progress=lambda ratio, msg: print(f"  {ratio*100:5.1f}%  {msg}"))
    print("OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
