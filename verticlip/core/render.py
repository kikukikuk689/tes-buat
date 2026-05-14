"""
Final-output renderer using FFmpeg.

Builds one filter graph per output clip and runs ffmpeg with progress
reporting. Positions are taken from the project model and converted from
normalized coordinates into pixel coordinates at the chosen output
resolution -- the same coordinates the preview uses, so the final result
matches the preview drag positions exactly.
"""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from .chroma_key import detect_key, ffmpeg_key_filter
from .fonts import resolve_font_file
from .ffmpeg_utils import find_ffmpeg, probe_video
from .project import (
    BackgroundMode,
    LogoMotion,
    OverlayKey,
    Project,
    REFERENCE_HEIGHT,
)


ProgressCb = Callable[[float, str], None]  # 0..1 progress, status message


@dataclass
class RenderError(Exception):
    message: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.message


def _hex_to_rgba(hex_str: str, opacity: float = 1.0) -> str:
    s = hex_str.lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    r, g, b = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    a = max(0.0, min(1.0, opacity))
    # FFmpeg drawtext accepts named or 0xRRGGBB. We use 0xRRGGBB and alpha separately when needed.
    return f"0x{r:02X}{g:02X}{b:02X}@{a:.3f}"


def _escape_drawtext(text: str) -> str:
    """Escape ``text`` for use in FFmpeg drawtext text= argument."""
    # Order matters: backslash first.
    s = text.replace("\\", "\\\\")
    s = s.replace(":", r"\:")
    s = s.replace("'", r"\'")
    s = s.replace("%", r"\%")
    return s


def _drawtext_filter(
    text: str,
    cx_norm: float,
    cy_norm: float,
    font_family: str,
    font_size: int,
    color: str,
    stroke_color: str,
    stroke_w: int,
    out_w: int,
    out_h: int,
    bg_box: bool = False,
    bg_color: str = "#000000",
    bg_opacity: float = 0.5,
) -> str:
    """Build a single drawtext filter string."""
    font_path = resolve_font_file(font_family) or ""
    scale = out_h / REFERENCE_HEIGHT
    px_size = max(8, int(round(font_size * scale)))
    border = max(0, int(round(stroke_w * scale)))

    # Center anchor: drawtext positions top-left, so subtract text width/height.
    # text_w / text_h are evaluated at drawtext time.
    x_expr = f"{int(round(cx_norm * out_w))}-text_w/2"
    y_expr = f"{int(round(cy_norm * out_h))}-text_h/2"

    parts = [
        f"text='{_escape_drawtext(text)}'",
        f"fontsize={px_size}",
        f"fontcolor={_hex_to_rgba(color, 1.0)}",
        f"x={x_expr}",
        f"y={y_expr}",
    ]
    if font_path:
        # Escape backslashes/colons in path (Windows paths are common).
        escaped = font_path.replace("\\", "/").replace(":", r"\:")
        parts.append(f"fontfile='{escaped}'")
    if border > 0:
        parts.append(f"bordercolor={_hex_to_rgba(stroke_color, 1.0)}")
        parts.append(f"borderw={border}")
    if bg_box:
        parts.append("box=1")
        parts.append(f"boxcolor={_hex_to_rgba(bg_color, bg_opacity)}")
        parts.append("boxborderw=10")
    return "drawtext=" + ":".join(parts)


def _build_filter_complex(
    project: Project,
    part_index: Optional[int],
) -> Tuple[List[str], List[str], str]:
    """
    Build the complete filter_complex.

    Returns (extra_inputs, segments, final_video_label).
    Input ordering:
        [0:v] main source (always)
        [1:v] custom bg if FIT_CUSTOM
        [N:v] overlay if present
        [M:v] logo if present
    """
    out_w = project.render.output_width
    out_h = project.render.output_height
    segments: List[str] = []
    extra_inputs: List[str] = []
    next_input_index = 1  # 0 is main video

    # ---- background ----------------------------------------------------
    if project.background_mode == BackgroundMode.FIT_CUSTOM and project.custom_bg_path:
        is_image = project.custom_bg_path.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".webp"))
        if is_image:
            extra_inputs.extend(["-loop", "1", "-i", project.custom_bg_path])
        else:
            extra_inputs.extend(["-stream_loop", "-1", "-i", project.custom_bg_path])
        custom_idx = next_input_index
        next_input_index += 1

        segments.append("[0:v]split=1[main0]")  # keep numbering simple
        segments.append(
            f"[{custom_idx}:v]scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
            f"crop={out_w}:{out_h}[bgc]"
        )
        segments.append(
            f"[main0]scale={out_w}:{out_h}:force_original_aspect_ratio=decrease[fg0]"
        )
        segments.append("[bgc][fg0]overlay=(W-w)/2:(H-h)/2:shortest=1[bg]")
        last_label = "[bg]"
        next_input_index += 0  # no-op, kept for readability
    elif project.background_mode == BackgroundMode.FILL_CROP:
        segments.append(
            f"[0:v]scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
            f"crop={out_w}:{out_h}[bg]"
        )
        last_label = "[bg]"
    elif project.background_mode == BackgroundMode.FIT_BLACK:
        segments.append(
            f"color=size={out_w}x{out_h}:color=black:duration=1:rate=30[blk]"
        )
        segments.append(
            f"[0:v]scale={out_w}:{out_h}:force_original_aspect_ratio=decrease[fg0]"
        )
        segments.append("[blk][fg0]overlay=(W-w)/2:(H-h)/2:shortest=1[bg]")
        last_label = "[bg]"
    else:  # FIT_BLUR (default)
        segments.append("[0:v]split=2[s0][s1]")
        segments.append(
            f"[s0]scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
            f"crop={out_w}:{out_h},gblur=sigma=30[bgblur]"
        )
        segments.append(
            f"[s1]scale={out_w}:{out_h}:force_original_aspect_ratio=decrease[fg0]"
        )
        segments.append("[bgblur][fg0]overlay=(W-w)/2:(H-h)/2:shortest=1[bg]")
        last_label = "[bg]"

    # ---- overlay (chroma keyed) ---------------------------------------
    if project.overlay.path and os.path.exists(project.overlay.path):
        overlay_idx = next_input_index
        next_input_index += 1
        is_image = project.overlay.path.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".webp"))
        if is_image:
            extra_inputs.extend(["-loop", "1", "-i", project.overlay.path])
        else:
            extra_inputs.extend(["-stream_loop", "-1", "-i", project.overlay.path])
        key = project.overlay.key
        if key == OverlayKey.AUTO:
            key = detect_key(project.overlay.path)
        key_filter = ffmpeg_key_filter(key, project.overlay.similarity, project.overlay.blend)
        segments.append(
            f"[{overlay_idx}:v]scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
            f"crop={out_w}:{out_h},{key_filter},format=yuva420p,"
            f"colorchannelmixer=aa={project.overlay.opacity:.3f}[ovkey]"
        )
        segments.append(f"{last_label}[ovkey]overlay=0:0:shortest=1[ovstage]")
        last_label = "[ovstage]"

    # ---- text items ----------------------------------------------------
    for i, item in enumerate(project.texts):
        flt = _drawtext_filter(
            text=item.text,
            cx_norm=item.x,
            cy_norm=item.y,
            font_family=item.font_family,
            font_size=item.font_size,
            color=item.color,
            stroke_color=item.stroke_color,
            stroke_w=item.stroke_width,
            out_w=out_w,
            out_h=out_h,
            bg_box=item.bg_box,
            bg_color=item.bg_color,
            bg_opacity=item.bg_opacity,
        )
        new_label = f"[txt{i}]"
        segments.append(f"{last_label}{flt}{new_label}")
        last_label = new_label

    # ---- auto part text -------------------------------------------------
    if project.part_text.enabled and part_index is not None:
        p = project.part_text
        part_text = f"{p.label} {part_index}"
        flt = _drawtext_filter(
            text=part_text,
            cx_norm=p.x,
            cy_norm=p.y,
            font_family=p.font_family,
            font_size=p.font_size,
            color=p.color,
            stroke_color=p.stroke_color,
            stroke_w=p.stroke_width,
            out_w=out_w,
            out_h=out_h,
        )
        new_label = "[parttxt]"
        segments.append(f"{last_label}{flt}{new_label}")
        last_label = new_label

    # ---- logo with optional motion ------------------------------------
    if project.logo.path and os.path.exists(project.logo.path):
        logo_idx = next_input_index
        next_input_index += 1
        extra_inputs.extend(["-loop", "1", "-i", project.logo.path])

        logo_w = max(2, int(round(project.logo.size * out_w)))
        segments.append(
            f"[{logo_idx}:v]scale={logo_w}:-1,format=rgba,"
            f"colorchannelmixer=aa={project.logo.opacity:.3f}[lg]"
        )
        # Base top-left in pixels (logo height unknown -> use 'h' expression)
        base_cx = project.logo.x * out_w
        base_cy = project.logo.y * out_h
        # In FFmpeg overlay expr: 'W' is main width, 'w' is overlay width, 'h' overlay height.
        # base top-left = base_cx - w/2, base_cy - h/2
        base_x_expr = f"({base_cx}-w/2)"
        base_y_expr = f"({base_cy}-h/2)"
        amp_px_x = project.logo.motion_amplitude * out_w
        amp_px_y = project.logo.motion_amplitude * out_h
        if project.logo.motion == LogoMotion.NONE:
            x_expr = base_x_expr
            y_expr = base_y_expr
        elif project.logo.motion == LogoMotion.CIRCLE:
            omega = f"(2*PI*t/{project.logo.motion_period_s})"
            x_expr = f"{base_x_expr}+({amp_px_x})*cos({omega})"
            y_expr = f"{base_y_expr}+({amp_px_y})*sin({omega})"
        elif project.logo.motion == LogoMotion.FIGURE8:
            omega = f"(2*PI*t/{project.logo.motion_period_s})"
            x_expr = f"{base_x_expr}+({amp_px_x})*sin({omega})"
            y_expr = f"{base_y_expr}+({amp_px_y}/2)*sin(2*{omega})"
        elif project.logo.motion == LogoMotion.BOUNCE:
            omega = f"(2*PI*t/{project.logo.motion_period_s})"
            x_expr = base_x_expr
            y_expr = f"{base_y_expr}-({amp_px_y})*abs(sin({omega}))"
        else:
            x_expr = base_x_expr
            y_expr = base_y_expr

        new_label = "[lgstage]"
        segments.append(
            f"{last_label}[lg]overlay=x='{x_expr}':y='{y_expr}':shortest=1{new_label}"
        )
        last_label = new_label

    return extra_inputs, segments, last_label


def _format_offset(seconds: float) -> str:
    return f"{seconds:.3f}"


def _compute_clip_ranges(duration: float, settings) -> List[Tuple[float, float]]:
    """Return list of (start, dur) split ranges."""
    if not settings.enabled or settings.seconds_per_clip <= 0 or duration <= 0:
        return [(0.0, duration if duration > 0 else 0.0)]
    spc = float(settings.seconds_per_clip)
    ranges: List[Tuple[float, float]] = []
    t = 0.0
    while t < duration:
        d = min(spc, duration - t)
        if d <= 0.1:
            break
        ranges.append((t, d))
        t += d
    if not ranges:
        ranges.append((0.0, duration))
    return ranges


def _run_ffmpeg(cmd: List[str], total_duration: float, progress: Optional[ProgressCb], status_prefix: str) -> None:
    """Run an ffmpeg command and parse progress from stderr."""
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        universal_newlines=True,
    )
    time_re = re.compile(r"time=(\d+):(\d+):(\d+\.?\d*)")
    assert proc.stderr is not None
    for line in proc.stderr:
        m = time_re.search(line)
        if m and progress and total_duration > 0:
            h, mi, s = m.groups()
            t = int(h) * 3600 + int(mi) * 60 + float(s)
            progress(min(1.0, t / total_duration), f"{status_prefix} {t:.1f}s/{total_duration:.1f}s")
    proc.wait()
    if proc.returncode != 0:
        raise RenderError(f"FFmpeg exited with code {proc.returncode}")
    if progress:
        progress(1.0, f"{status_prefix} done")


def render_project(project: Project, progress: Optional[ProgressCb] = None) -> List[str]:
    """Render the project. Returns list of output paths."""
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RenderError("FFmpeg tidak ditemukan. Install dulu lewat tombol Install FFmpeg.")
    if not project.source_video or not os.path.exists(project.source_video):
        raise RenderError("Video sumber belum dipilih.")
    if not project.render.output_dir:
        raise RenderError("Folder output belum dipilih.")
    out_dir = Path(project.render.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    info = probe_video(project.source_video)
    duration = info.duration if info else 0.0
    if duration <= 0:
        raise RenderError("Gagal membaca durasi video sumber.")

    clip_ranges = _compute_clip_ranges(duration, project.split)
    outputs: List[str] = []

    total_render_seconds = sum(d for _, d in clip_ranges) or duration
    rendered_so_far = 0.0

    for i, (start, dur) in enumerate(clip_ranges):
        part_index = (project.part_text.start_index + i) if project.part_text.enabled else None
        extra_inputs, segments, last_label = _build_filter_complex(project, part_index)
        filter_complex = ";".join(segments)

        prefix = project.render.file_prefix or "verticlip"
        if project.split.enabled and len(clip_ranges) > 1:
            out_file = out_dir / f"{prefix}_part{project.part_text.start_index + i:02d}.mp4"
        else:
            out_file = out_dir / f"{prefix}.mp4"

        cmd: List[str] = [
            ffmpeg, "-y",
            "-ss", _format_offset(start),
            "-t", _format_offset(dur),
            "-i", project.source_video,
        ]
        cmd.extend(extra_inputs)
        cmd.extend([
            "-filter_complex", filter_complex,
            "-map", last_label,
        ])
        if info and info.has_audio:
            cmd.extend(["-map", "0:a?"])

        cmd.extend([
            "-c:v", "libx264",
            "-preset", project.render.preset,
            "-crf", str(project.render.crf),
            "-pix_fmt", "yuv420p",
            "-r", str(project.render.fps),
        ])
        if info and info.has_audio:
            cmd.extend(["-c:a", "aac", "-b:a", "192k"])
        cmd.extend([
            "-movflags", "+faststart",
            "-shortest",
            str(out_file),
        ])

        def clip_progress(p: float, msg: str, *, _i: int = i, _dur: float = dur) -> None:
            if progress is None:
                return
            local = max(0.0, min(1.0, p))
            done = rendered_so_far + local * _dur
            overall = done / total_render_seconds if total_render_seconds > 0 else 0.0
            progress(min(1.0, overall), f"Render clip {_i + 1}/{len(clip_ranges)}: {msg}")

        _run_ffmpeg(cmd, dur, clip_progress, f"Clip {i + 1}/{len(clip_ranges)}")
        rendered_so_far += dur
        outputs.append(str(out_file))

    return outputs
