"""Streamlit UI for ASMR Seamless Loop Maker.

Run with::

    streamlit run asmr_loop_maker/streamlit_app.py

The UI lets you either upload a single video or point at a folder on disk
for batch processing.  Configurable target duration (hours), crossfade,
loop analysis bounds, and encoder quality are exposed.
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Optional

import streamlit as st

from asmr_loop_maker.analyzer import analyze_video
from asmr_loop_maker.batch import process_batch
from asmr_loop_maker.processor import process_video
from asmr_loop_maker.utils import (
    SUPPORTED_EXTENSIONS,
    ensure_ffmpeg,
    humanise_seconds,
    iter_video_files,
)


def _ensure_outdir(value: str) -> Path:
    path = Path(value).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _format_score_table(analysis) -> dict:
    return {
        "Total Score": f"{analysis.score:.3f}",
        "Grayscale Similarity": f"{analysis.grayscale_score:.3f}",
        "Histogram Similarity": f"{analysis.histogram_score:.3f}",
        "Duration Bonus": f"{analysis.duration_score:.3f}",
        "Loop Duration (s)": f"{analysis.loop_duration:.3f}",
        "Start Frame": analysis.start_frame,
        "End Frame": analysis.end_frame,
        "Start Time (s)": f"{analysis.start_time:.3f}",
        "End Time (s)": f"{analysis.end_time:.3f}",
        "Source FPS": f"{analysis.fps:.3f}",
        "Source Total Frames": analysis.total_frames,
    }


def _sidebar_controls() -> dict:
    st.sidebar.header("Output settings")
    hours = st.sidebar.number_input(
        "Target duration (hours)",
        min_value=0.05,
        max_value=24.0,
        value=1.0,
        step=0.25,
        help="Final output length in hours.",
    )
    crossfade = st.sidebar.number_input(
        "Crossfade duration (seconds)",
        min_value=0.0,
        max_value=10.0,
        value=0.5,
        step=0.1,
        help="Audio + visual crossfade applied at every loop boundary.",
    )
    min_loop = st.sidebar.number_input(
        "Minimum loop length (seconds)",
        min_value=0.5,
        max_value=120.0,
        value=1.5,
        step=0.5,
    )
    use_max_loop = st.sidebar.checkbox("Limit maximum loop length", value=False)
    max_loop: Optional[float] = None
    if use_max_loop:
        max_loop = st.sidebar.number_input(
            "Maximum loop length (seconds)",
            min_value=min_loop,
            max_value=600.0,
            value=max(min_loop + 1.0, 6.0),
            step=0.5,
        )

    with st.sidebar.expander("Encoder settings", expanded=False):
        crf = st.slider("x264 CRF (lower = better)", min_value=14, max_value=32, value=20)
        preset = st.selectbox(
            "x264 preset",
            options=[
                "ultrafast",
                "superfast",
                "veryfast",
                "faster",
                "fast",
                "medium",
                "slow",
                "slower",
                "veryslow",
            ],
            index=5,
        )

    return {
        "hours": float(hours),
        "crossfade": float(crossfade),
        "min_loop": float(min_loop),
        "max_loop": float(max_loop) if max_loop is not None else None,
        "crf": int(crf),
        "preset": preset,
    }


def _render_progress_widgets():
    overall = st.progress(0.0, text="Idle")
    sub = st.progress(0.0, text="")

    def update(stage: str, fraction: float) -> None:
        weights = {"analyze": 0.05, "video": 0.7, "audio": 0.15, "mux": 0.10}
        offsets = {"analyze": 0.0, "video": 0.05, "audio": 0.75, "mux": 0.9}
        weight = weights.get(stage, 0.25)
        offset = offsets.get(stage, 0.0)
        global_fraction = min(1.0, offset + weight * max(0.0, min(1.0, fraction)))
        overall.progress(global_fraction, text=f"{stage.title()} ({fraction * 100:.0f}%)")
        sub.progress(min(1.0, max(0.0, fraction)), text=stage.title())

    return overall, sub, update


def _single_video_flow(settings: dict) -> None:
    st.subheader("Single video")
    uploaded = st.file_uploader(
        "Upload a video",
        type=[ext.lstrip(".") for ext in SUPPORTED_EXTENSIONS],
        help="Drag a short clip here — MP4, MOV, MKV, or AVI.",
    )
    default_output = str(Path.cwd() / "asmr_loop_output.mp4")
    output_path_str = st.text_input(
        "Output file path",
        value=default_output,
        help="Where to write the final long ASMR loop.",
    )

    analyse_only = st.button("Analyse only (no rendering)", key="single_analyze")
    render = st.button("Generate loop", type="primary", key="single_render")

    if not uploaded:
        st.info("Upload a video to start.")
        return

    with tempfile.TemporaryDirectory(prefix="asmr_st_") as tmpdir:
        tmp_input = Path(tmpdir) / uploaded.name
        tmp_input.write_bytes(uploaded.getbuffer())

        if analyse_only:
            with st.spinner("Analysing video..."):
                analysis = analyze_video(
                    tmp_input,
                    min_loop_seconds=settings["min_loop"],
                    max_loop_seconds=settings["max_loop"],
                )
            st.success("Analysis complete")
            st.table(_format_score_table(analysis))
            return

        if not render:
            return

        out_path = Path(output_path_str).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)

        _, _, progress_cb = _render_progress_widgets()
        start = time.monotonic()
        try:
            result = process_video(
                tmp_input,
                out_path,
                target_hours=settings["hours"],
                crossfade_seconds=settings["crossfade"],
                min_loop_seconds=settings["min_loop"],
                max_loop_seconds=settings["max_loop"],
                crf=settings["crf"],
                preset=settings["preset"],
                progress=progress_cb,
            )
        except Exception as exc:  # pragma: no cover - surfaced to UI
            st.error(f"Processing failed: {exc}")
            return
        elapsed = time.monotonic() - start

        st.success(
            f"Done in {humanise_seconds(elapsed)} — wrote {result.output_path}"
        )
        st.table(_format_score_table(result.analysis))
        st.write(
            f"**Target duration:** {humanise_seconds(result.target_duration)}  ·  "
            f"**Crossfade:** {result.crossfade_seconds:.2f} s  ·  "
            f"**Audio:** {'yes' if result.has_audio else 'no'}"
        )

        try:
            out_size_mb = out_path.stat().st_size / (1024 * 1024)
            st.caption(f"Output size: {out_size_mb:.1f} MB")
            # Streamlit can only stream files smaller than ~200 MB reliably.
            if out_size_mb < 200:
                st.video(str(out_path))
            else:
                st.info(
                    "Preview skipped because the file is large. "
                    f"Open it from disk: {out_path}"
                )
        except OSError:
            st.warning("Could not stat output file for preview.")


def _batch_flow(settings: dict) -> None:
    st.subheader("Batch (folder)")
    folder_str = st.text_input(
        "Input folder",
        value=str(Path.cwd()),
        help="Folder containing one or more videos.",
    )
    output_str = st.text_input(
        "Output folder",
        value=str(Path.cwd() / "asmr_loop_output"),
        help="Outputs will be saved as {name}_asmr_loop.mp4 here.",
    )
    report_name = st.text_input("Batch report filename", value="batch_report.csv")

    folder = Path(folder_str).expanduser()
    if folder.exists() and folder.is_dir():
        try:
            videos = iter_video_files(folder)
            st.caption(f"Detected {len(videos)} supported video(s) in {folder}")
            with st.expander("Files to process", expanded=False):
                for v in videos[:50]:
                    st.write(f"- {v.name}")
                if len(videos) > 50:
                    st.write(f"… and {len(videos) - 50} more")
        except Exception as exc:
            st.warning(str(exc))

    run = st.button("Run batch", type="primary", key="batch_run")
    if not run:
        return

    if not folder.exists() or not folder.is_dir():
        st.error("Input folder does not exist or is not a directory.")
        return

    output_dir = _ensure_outdir(output_str)
    progress_bar = st.progress(0.0, text="Starting...")

    def progress(idx: int, total: int, path: str) -> None:
        progress_bar.progress(
            (idx - 1) / max(1, total),
            text=f"Processing {idx}/{total}: {Path(path).name}",
        )

    start = time.monotonic()
    try:
        result = process_batch(
            folder,
            output_dir,
            target_hours=settings["hours"],
            crossfade_seconds=settings["crossfade"],
            min_loop_seconds=settings["min_loop"],
            max_loop_seconds=settings["max_loop"],
            crf=settings["crf"],
            preset=settings["preset"],
            report_name=report_name,
            progress=progress,
        )
    except Exception as exc:  # pragma: no cover
        st.error(f"Batch failed: {exc}")
        return
    progress_bar.progress(1.0, text="Done")
    elapsed = time.monotonic() - start

    ok = len(result.succeeded)
    failed = len(result.failed)
    st.success(
        f"Batch finished in {humanise_seconds(elapsed)} — {ok} ok, {failed} failed."
    )
    if result.report_path:
        try:
            with open(result.report_path, "rb") as f:
                st.download_button(
                    "Download CSV report",
                    data=f.read(),
                    file_name=Path(result.report_path).name,
                    mime="text/csv",
                )
        except OSError:
            pass

    rows = []
    for item in result.items:
        rows.append(
            {
                "Input": Path(item.input_path).name,
                "Output": Path(item.output_path).name,
                "Status": item.status,
                "Elapsed (s)": f"{item.elapsed_seconds:.1f}",
                "Score": (
                    f"{item.result.analysis.score:.3f}" if item.result else "—"
                ),
                "Message": item.message,
            }
        )
    if rows:
        st.dataframe(rows, use_container_width=True)


def main() -> None:
    st.set_page_config(
        page_title="ASMR Seamless Loop Maker",
        page_icon=":sleeping:",
        layout="wide",
    )
    st.title("ASMR Seamless Loop Maker")
    st.write(
        "Turn a short clip into a long, seamlessly looping ASMR video. "
        "Pick a single file or a folder for batch processing."
    )

    try:
        ensure_ffmpeg()
    except RuntimeError as exc:
        st.error(str(exc))
        st.stop()

    settings = _sidebar_controls()

    tab_single, tab_batch = st.tabs(["Single video", "Batch (folder)"])
    with tab_single:
        _single_video_flow(settings)
    with tab_batch:
        _batch_flow(settings)


main()
