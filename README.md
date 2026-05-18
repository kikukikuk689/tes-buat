# ASMR Seamless Loop Maker

Turn a short clip into a long (1 hour, 3 hours, or more) seamlessly looping
ASMR video. The tool finds the smoothest possible loop point in the source
clip using OpenCV, crossfades both the video and the audio at every loop
boundary, and renders the result with `ffmpeg`. It works on a single file
or on a whole folder in batch mode, and ships with both a CLI and a
Streamlit UI.

## Features

- Input one video or a folder of videos.
- Supports `.mp4`, `.mov`, `.mkv`, `.avi`.
- Analyses every frame with OpenCV:
  - mean absolute grayscale difference between candidate start/end frames
  - HSV color histogram correlation
  - a small bonus that favours longer (more meaningful) loops
- Picks the best `(start_frame, end_frame)` pair and reports a smoothness
  score.
- Renders a long output by streaming a pre-crossfaded "loop unit" into
  `ffmpeg`, so memory stays bounded regardless of output duration.
- Adds a visual crossfade between every loop iteration.
- Extracts audio with `ffmpeg`, builds a click-free audio loop unit in
  Python (linear crossfade between tail and head), repeats to target
  duration, then muxes everything back together.
- Batch mode writes outputs as `{input_stem}_asmr_loop.mp4` next to a
  CSV report with the loop score and timings for every file.
- CLI for terminal use.
- Streamlit UI with single-file upload, folder batch, target duration in
  hours, crossfade duration, analysis preview, and an inline video
  preview when the output is small enough to stream.

## Requirements

- Python 3.10+ (developed against 3.12)
- `ffmpeg` and `ffprobe` available on `PATH`
- The Python dependencies in [`requirements.txt`](./requirements.txt):
  `numpy`, `opencv-python-headless`, `streamlit`, `tqdm`.

Install everything with:

```bash
pip install -r requirements.txt
```

On Debian/Ubuntu you can install `ffmpeg` with:

```bash
sudo apt-get install -y ffmpeg
```

## Usage

### CLI

Single file:

```bash
python -m asmr_loop_maker input.mp4 -o output.mp4 \
    --hours 1.0 \
    --crossfade 0.5
```

Folder (batch mode):

```bash
python -m asmr_loop_maker ./inputs -o ./outputs \
    --hours 3.0 \
    --crossfade 0.75 \
    --report batch_report.csv
```

Useful flags:

| Flag | Default | Description |
| ---- | ------- | ----------- |
| `--hours` | `1.0` | Target output duration in hours. |
| `--crossfade` | `0.5` | Crossfade duration in seconds applied at every loop boundary. |
| `--min-loop` | `1.5` | Minimum allowed loop length, in seconds. |
| `--max-loop` | _none_ | Optional cap on the loop length. |
| `--crf` | `20` | x264 CRF (lower = better, larger files). |
| `--preset` | `medium` | x264 preset (`ultrafast` … `veryslow`). |
| `--report` | `batch_report.csv` | Filename for the batch CSV report. |
| `--no-overwrite` | _off_ | Don't overwrite existing outputs; append `_N`. |
| `--json` | _off_ | Print machine-readable JSON summary after processing. |
| `-v, --verbose` | _off_ | Enable debug logging. |

The CLI exit code is `0` when everything succeeded, `1` if any files in a
batch failed.

### Streamlit UI

```bash
streamlit run asmr_loop_maker/streamlit_app.py
```

The UI exposes:

- **Single video** tab: upload a clip, choose where to save the long
  output, run analysis only or full render, see the smoothness score, and
  preview small outputs inline.
- **Batch (folder)** tab: point at an input folder, set an output folder
  and report filename, see the table of results, and download the CSV.

All shared knobs (target hours, crossfade, min/max loop, encoder CRF and
preset) live in the sidebar.

### As a library

```python
from pathlib import Path
from asmr_loop_maker import analyze_video, process_video, process_batch

analysis = analyze_video("clip.mp4")
print(analysis.start_time, analysis.end_time, analysis.score)

process_video(
    "clip.mp4",
    "clip_asmr_loop.mp4",
    target_hours=1.0,
    crossfade_seconds=0.5,
)

result = process_batch(
    "./inputs",
    "./outputs",
    target_hours=3.0,
    crossfade_seconds=0.75,
)
print(result.report_path, len(result.succeeded), len(result.failed))
```

## How the loop is built

1. **Analyse** – Every frame is downscaled to 160×90 once. Candidate
   start frames are sampled from the first ~40 % of the clip, candidate
   end frames from the last ~40 %. For each pair we compute:
   - grayscale similarity = `1 - mean_abs_diff / 64`,
   - histogram similarity = clamped HSV histogram correlation,
   - a small duration bonus.
   The best-scoring pair becomes the loop window.
2. **Build a loop unit** – The chosen segment is read into memory. Its
   first `crossfade_seconds` are replaced with a linear blend of the
   segment's tail and head, so concatenating copies of the unit produces
   a smooth video that returns to its starting frame seamlessly.
3. **Stream-encode** – Frames of the loop unit are written into an
   `ffmpeg` stdin pipe as raw BGR, encoded with `libx264` (CRF/preset
   configurable) to `yuv420p` MP4. The unit is replayed as many times as
   needed for the target duration. Memory stays bounded to one segment.
4. **Audio** – The same window is extracted with `ffmpeg` as a 16-bit
   PCM WAV, loaded with `numpy`, crossfaded the same way, then written
   to disk in chunks until the target duration is reached.
5. **Mux** – The video and audio are combined with `ffmpeg -c:v copy
   -c:a aac` to produce the final `*_asmr_loop.mp4`. Videos without an
   audio stream are passed through silently.

## Project layout

```
asmr_loop_maker/
├── __init__.py        # public API re-exports
├── __main__.py        # `python -m asmr_loop_maker` shim
├── analyzer.py        # OpenCV loop point search
├── audio.py           # WAV extraction + loop with crossfade
├── batch.py           # batch processor + CSV report
├── cli.py             # argparse CLI
├── processor.py       # analyse -> video -> audio -> mux orchestrator
├── streamlit_app.py   # Streamlit UI
├── utils.py           # ffmpeg helpers, supported extensions, etc.
└── video.py           # frame-level crossfade + ffmpeg-piped encoder
```

## Tests

Lightweight smoke tests live under `tests/`. They synthesise a tiny
video with `ffmpeg`, run analysis + a short render, and verify the
result. Run them with:

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -v
```
