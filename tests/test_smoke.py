"""Smoke tests for the ASMR loop maker.

These tests synthesise tiny videos with ``ffmpeg`` and exercise the
analysis, audio, video and batch pipelines end-to-end on short outputs.
They are designed to run in well under a minute on a typical CI worker.
"""

from __future__ import annotations

import csv
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np

from asmr_loop_maker.analyzer import analyze_video
from asmr_loop_maker.audio import (
    AudioSegment,
    build_loop_unit as build_audio_unit,
)
from asmr_loop_maker.batch import process_batch
from asmr_loop_maker.processor import process_video
from asmr_loop_maker.utils import iter_video_files
from asmr_loop_maker.video import build_loop_unit as build_video_unit


def _ffmpeg() -> str:
    binary = shutil.which("ffmpeg")
    if binary is None:
        raise unittest.SkipTest("ffmpeg is required for smoke tests")
    return binary


def _make_sample_video(path: Path, duration: float = 2.5) -> None:
    """Render a small video with synthetic content and a sine-wave tone."""

    ffmpeg = _ffmpeg()
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=size=64x64:rate=10:duration={duration}",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=440:sample_rate=22050:duration={duration}",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "64k",
        "-shortest",
        str(path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


class AudioLoopUnitTests(unittest.TestCase):
    def test_loop_unit_length_matches_segment_minus_crossfade(self) -> None:
        sample_rate = 1000
        samples = np.linspace(-1.0, 1.0, sample_rate, dtype=np.float32).reshape(-1, 1)
        segment = AudioSegment(sample_rate=sample_rate, channels=1, samples=samples)
        unit, cf = build_audio_unit(segment, crossfade_seconds=0.1)
        self.assertEqual(cf, 100)
        # length = total - crossfade_samples (head and tail merged into the
        # leading crossfade region)
        self.assertEqual(unit.shape[0], sample_rate - 100)

    def test_loop_unit_with_zero_crossfade_returns_copy(self) -> None:
        sample_rate = 1000
        samples = np.ones((sample_rate, 2), dtype=np.float32) * 0.5
        segment = AudioSegment(sample_rate=sample_rate, channels=2, samples=samples)
        unit, cf = build_audio_unit(segment, crossfade_seconds=0.0)
        self.assertEqual(cf, 0)
        self.assertEqual(unit.shape, samples.shape)
        # Must be an independent buffer (mutating one shouldn't affect the other).
        unit[0, 0] = 99.0
        self.assertNotEqual(samples[0, 0], unit[0, 0])


class VideoLoopUnitTests(unittest.TestCase):
    def test_loop_unit_blends_head_and_tail(self) -> None:
        frames = [
            (np.ones((4, 4, 3), dtype=np.uint8) * (i * 25)).astype(np.uint8)
            for i in range(8)
        ]
        unit = build_video_unit(frames, crossfade_frames=2)
        # Length = total - crossfade_frames (the trailing crossfade region is
        # absorbed into the leading blend of the next loop).
        self.assertEqual(len(unit), 8 - 2)
        # First blended frame is dominated by the tail (alpha=0).
        self.assertTrue(np.all(unit[0] == frames[-2]))
        # Internal frames are unmodified.
        self.assertTrue(np.array_equal(unit[2], frames[2]))


class EndToEndTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="asmr_test_")
        self.tmp_root = Path(self.tmp.name)
        self.sample = self.tmp_root / "sample.mp4"
        _make_sample_video(self.sample, duration=2.5)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_analyze_returns_valid_window(self) -> None:
        analysis = analyze_video(self.sample, min_loop_seconds=0.5)
        self.assertGreater(analysis.total_frames, 0)
        self.assertGreaterEqual(analysis.start_frame, 0)
        self.assertGreater(analysis.end_frame, analysis.start_frame)
        self.assertGreaterEqual(analysis.score, 0.0)
        self.assertLessEqual(analysis.score, 1.0)

    def test_process_video_writes_output(self) -> None:
        output = self.tmp_root / "loop.mp4"
        # ~6 second output keeps the test fast while exercising multiple loops.
        target_hours = 6.0 / 3600.0
        result = process_video(
            self.sample,
            output,
            target_hours=target_hours,
            crossfade_seconds=0.2,
            min_loop_seconds=0.5,
            crf=28,
            preset="ultrafast",
        )
        self.assertTrue(output.exists())
        self.assertGreater(output.stat().st_size, 1024)
        self.assertEqual(result.output_path, str(output))
        self.assertTrue(result.has_audio)

    def test_batch_creates_csv_report(self) -> None:
        in_dir = self.tmp_root / "in"
        out_dir = self.tmp_root / "out"
        in_dir.mkdir()
        for i in range(2):
            _make_sample_video(in_dir / f"clip_{i}.mp4", duration=2.0)
        videos = iter_video_files(in_dir)
        self.assertEqual(len(videos), 2)

        target_hours = 4.0 / 3600.0
        result = process_batch(
            in_dir,
            out_dir,
            target_hours=target_hours,
            crossfade_seconds=0.15,
            min_loop_seconds=0.5,
            crf=28,
            preset="ultrafast",
        )
        self.assertEqual(len(result.items), 2)
        self.assertEqual(len(result.failed), 0)
        report = Path(result.report_path)
        self.assertTrue(report.exists())
        with report.open() as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(row["status"], "ok")
            self.assertTrue(row["output_path"].endswith("_asmr_loop.mp4"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
