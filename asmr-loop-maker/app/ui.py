"""Streamlit user interface for ASMR Seamless Loop Maker."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import streamlit as st

from .batch import process_batch, process_single_video
from .config import (
    DEFAULT_CROSSFADE_SEC,
    DEFAULT_INPUT_DIR,
    DEFAULT_MIN_LOOP_SEC,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_REPORTS_DIR,
    DEFAULT_TARGET_HOURS,
)
from .utils import FFmpegNotFoundError, ensure_dir, ensure_ffmpeg_available, is_video_file


def _make_progress_callback(progress_bar, status_placeholder):
    """Return a callback that updates a Streamlit progress bar."""

    stage_weights = {
        "analyzing": 0.25,
        "rendering_video": 0.45,
        "extracting_audio": 0.05,
        "rendering_audio": 0.15,
        "muxing": 0.10,
    }
    cumulative = {}
    running = {"value": 0.0}

    order = list(stage_weights.keys())
    for i, name in enumerate(order):
        cumulative[name] = sum(stage_weights[n] for n in order[:i])

    def cb(stage: str, frac: float) -> None:
        base = cumulative.get(stage, running["value"])
        weight = stage_weights.get(stage, 0.0)
        total = min(1.0, base + frac * weight)
        running["value"] = total
        progress_bar.progress(total)
        status_placeholder.text(f"{stage} … {int(total * 100)}%")

    return cb


def _render_single(
    input_video: Path,
    output_dir: Path,
    target_hours: float,
    crossfade_sec: float,
    min_loop_sec: float,
) -> None:
    progress_bar = st.progress(0.0)
    status = st.empty()
    cb = _make_progress_callback(progress_bar, status)

    with st.spinner(f"Memproses {input_video.name} …"):
        result = process_single_video(
            input_path=input_video,
            output_dir=output_dir,
            target_hours=target_hours,
            crossfade_sec=crossfade_sec,
            min_loop_sec=min_loop_sec,
            progress=cb,
        )

    progress_bar.progress(1.0)
    if result.status == "success":
        status.success("Selesai!")
        st.subheader("Hasil Analisis Loop")
        if result.loop_info is not None:
            st.json(dict(result.loop_info))
        st.write(f"**Output:** `{result.output_path}`")
        out_path = Path(result.output_path)
        if out_path.exists() and out_path.stat().st_size < 200 * 1024 * 1024:
            try:
                st.video(str(out_path))
            except Exception as exc:  # pragma: no cover - best-effort preview
                st.info(f"Preview tidak tersedia: {exc}")
        else:
            st.info(
                "Preview dilewati karena file output terlalu besar untuk ditampilkan inline. "
                "Buka file langsung dari folder output."
            )
    else:
        status.error("Gagal memproses video.")
        st.error(result.error)


def _render_batch(
    input_dir: Path,
    output_dir: Path,
    target_hours: float,
    crossfade_sec: float,
    min_loop_sec: float,
    reports_dir: Path,
) -> None:
    with st.spinner(f"Memproses folder {input_dir} …"):
        try:
            results, report_path = process_batch(
                input_dir=input_dir,
                output_dir=output_dir,
                target_hours=target_hours,
                crossfade_sec=crossfade_sec,
                min_loop_sec=min_loop_sec,
                reports_dir=reports_dir,
            )
        except (FileNotFoundError, ValueError) as exc:
            st.error(str(exc))
            return

    st.subheader("Ringkasan Batch")
    rows = [r.to_row() for r in results]
    st.dataframe(rows, use_container_width=True)
    st.write(f"**Report CSV:** `{report_path}`")


def render_app() -> None:
    """Render the Streamlit application."""

    st.set_page_config(page_title="ASMR Seamless Loop Maker", page_icon="🎧", layout="centered")
    st.title("ASMR Seamless Loop Maker")
    st.caption(
        "Ubah video pendek menjadi video ASMR berdurasi panjang dengan loop visual & audio yang mulus."
    )

    try:
        ensure_ffmpeg_available()
    except FFmpegNotFoundError as exc:
        st.error(str(exc))
        st.stop()

    mode = st.radio("Mode", options=["Single video", "Batch folder"], horizontal=True)

    target_hours = st.number_input(
        "Durasi output (jam)",
        min_value=0.05,
        max_value=24.0,
        value=float(DEFAULT_TARGET_HOURS),
        step=0.5,
    )
    crossfade_sec = st.number_input(
        "Crossfade (detik)",
        min_value=0.0,
        max_value=10.0,
        value=float(DEFAULT_CROSSFADE_SEC),
        step=0.1,
    )
    min_loop_sec = st.number_input(
        "Durasi minimum loop (detik)",
        min_value=0.5,
        max_value=60.0,
        value=float(DEFAULT_MIN_LOOP_SEC),
        step=0.5,
    )

    output_dir_str = st.text_input("Folder output", value=str(DEFAULT_OUTPUT_DIR))
    output_dir = ensure_dir(Path(output_dir_str).expanduser())

    if mode == "Single video":
        st.subheader("Input video")
        uploaded = st.file_uploader(
            "Upload satu video",
            type=["mp4", "mov", "mkv", "avi"],
            accept_multiple_files=False,
        )
        input_path_str = st.text_input(
            "…atau isi path file video di server",
            value="",
            help="Berguna ketika file sudah berada di mesin yang sama.",
        )
        if st.button("Process", type="primary", disabled=(uploaded is None and not input_path_str)):
            if uploaded is not None:
                tmp_dir = Path(tempfile.mkdtemp(prefix="asmr_upload_"))
                tmp_video = tmp_dir / uploaded.name
                with tmp_video.open("wb") as fh:
                    shutil.copyfileobj(uploaded, fh)
                input_video = tmp_video
            else:
                input_video = Path(input_path_str).expanduser()
                if not is_video_file(input_video):
                    st.error(f"File bukan video yang didukung: {input_video}")
                    return
            _render_single(input_video, output_dir, target_hours, crossfade_sec, min_loop_sec)
    else:
        st.subheader("Folder input")
        input_dir_str = st.text_input("Folder input", value=str(DEFAULT_INPUT_DIR))
        reports_dir_str = st.text_input("Folder reports", value=str(DEFAULT_REPORTS_DIR))
        if st.button("Process batch", type="primary"):
            input_dir = Path(input_dir_str).expanduser()
            reports_dir = ensure_dir(Path(reports_dir_str).expanduser())
            _render_batch(input_dir, output_dir, target_hours, crossfade_sec, min_loop_sec, reports_dir)


if __name__ == "__main__":
    render_app()
