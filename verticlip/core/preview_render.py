"""
Single-frame preview compositor.

The preview rasterizes the output canvas at REDUCED resolution (to keep
it real-time), then the preview widget displays it. Drag positions are
stored as normalized coordinates so they map 1:1 to the final render.
"""
from __future__ import annotations

import os
from typing import Optional

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .animation import offset_at
from .fonts import resolve_font_file
from .project import (
    BackgroundMode,
    LogoItem,
    OverlayKey,
    PartTextSettings,
    Project,
    REFERENCE_HEIGHT,
    TextItem,
)


# Preview canvas size: 405x720 keeps 9:16 with smooth performance.
PREVIEW_W = 405
PREVIEW_H = 720


def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    s = hex_str.lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


def _ensure_video_frame(path: str, timestamp_s: float = 1.0) -> Optional[np.ndarray]:
    """Return a representative BGR frame from the video, or None."""
    if not path or not os.path.exists(path):
        return None
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return None
    duration_ms = 0
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    if fps > 0 and frame_count > 0:
        duration_ms = (frame_count / fps) * 1000.0
    target_ms = min(timestamp_s * 1000.0, max(0.0, duration_ms - 100.0))
    cap.set(cv2.CAP_PROP_POS_MSEC, target_ms)
    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        return None
    return frame


def _load_image_bgr(path: str) -> Optional[np.ndarray]:
    if not path or not os.path.exists(path):
        return None
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    return img


def _load_image_bgra(path: str) -> Optional[np.ndarray]:
    if not path or not os.path.exists(path):
        return None
    return cv2.imread(path, cv2.IMREAD_UNCHANGED)


def _fit_into(frame: np.ndarray, target_w: int, target_h: int) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """Resize ``frame`` to fit inside (target_w, target_h) preserving aspect.

    Returns (resized_frame, (offset_x, offset_y, fitted_w, fitted_h))
    """
    h, w = frame.shape[:2]
    if w <= 0 or h <= 0:
        return frame, (0, 0, target_w, target_h)
    scale = min(target_w / w, target_h / h)
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))
    resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
    ox = (target_w - new_w) // 2
    oy = (target_h - new_h) // 2
    return resized, (ox, oy, new_w, new_h)


def _fill_crop(frame: np.ndarray, target_w: int, target_h: int) -> np.ndarray:
    h, w = frame.shape[:2]
    if w <= 0 or h <= 0:
        return np.zeros((target_h, target_w, 3), dtype=np.uint8)
    scale = max(target_w / w, target_h / h)
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))
    resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
    cx = (new_w - target_w) // 2
    cy = (new_h - target_h) // 2
    return resized[cy:cy + target_h, cx:cx + target_w]


def _compose_background(project: Project, target_w: int, target_h: int) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """Return (background_canvas, foreground_rect)."""
    canvas = np.zeros((target_h, target_w, 3), dtype=np.uint8)
    fg_rect = (0, 0, target_w, target_h)
    src = project.source_video
    if not src:
        return canvas, fg_rect

    fg = _ensure_video_frame(src)
    if fg is None:
        return canvas, fg_rect

    mode = project.background_mode
    if mode == BackgroundMode.FILL_CROP:
        canvas = _fill_crop(fg, target_w, target_h)
        fg_rect = (0, 0, target_w, target_h)
        return canvas, fg_rect

    if mode == BackgroundMode.FIT_BLUR:
        bg = _fill_crop(fg, target_w, target_h)
        # heavy blur for backdrop
        k = max(15, target_w // 12)
        if k % 2 == 0:
            k += 1
        canvas = cv2.GaussianBlur(bg, (k, k), 0)
    elif mode == BackgroundMode.FIT_BLACK:
        canvas[:] = 0
    elif mode == BackgroundMode.FIT_CUSTOM:
        custom_path = project.custom_bg_path
        bg_img = None
        if custom_path and os.path.exists(custom_path):
            if custom_path.lower().endswith((".mp4", ".mov", ".webm", ".mkv", ".avi")):
                bg_img = _ensure_video_frame(custom_path)
            else:
                bg_img = _load_image_bgr(custom_path)
        if bg_img is not None:
            canvas = _fill_crop(bg_img, target_w, target_h)
        else:
            canvas[:] = 0

    # Place fitted foreground over the chosen background.
    fitted, fg_rect = _fit_into(fg, target_w, target_h)
    ox, oy, fw, fh = fg_rect
    canvas[oy:oy + fh, ox:ox + fw] = fitted
    return canvas, fg_rect


def _alpha_blend(base: np.ndarray, overlay_bgra: np.ndarray, x: int, y: int) -> None:
    """In-place alpha-blend ``overlay_bgra`` onto ``base`` (BGR) at (x, y)."""
    if overlay_bgra is None or overlay_bgra.size == 0:
        return
    bh, bw = base.shape[:2]
    oh, ow = overlay_bgra.shape[:2]
    if x >= bw or y >= bh:
        return
    x1 = max(0, x)
    y1 = max(0, y)
    x2 = min(bw, x + ow)
    y2 = min(bh, y + oh)
    if x2 <= x1 or y2 <= y1:
        return
    ox1 = x1 - x
    oy1 = y1 - y
    ox2 = ox1 + (x2 - x1)
    oy2 = oy1 + (y2 - y1)

    patch = overlay_bgra[oy1:oy2, ox1:ox2]
    if patch.shape[2] == 4:
        bgr = patch[:, :, :3].astype(np.float32)
        alpha = (patch[:, :, 3:4].astype(np.float32)) / 255.0
    else:
        bgr = patch.astype(np.float32)
        alpha = np.ones((patch.shape[0], patch.shape[1], 1), dtype=np.float32)
    dest = base[y1:y2, x1:x2].astype(np.float32)
    blended = dest * (1.0 - alpha) + bgr * alpha
    base[y1:y2, x1:x2] = np.clip(blended, 0, 255).astype(np.uint8)


def _draw_text_pil(
    canvas: np.ndarray,
    text: str,
    cx: int,
    cy: int,
    font_path: Optional[str],
    font_size_px: int,
    color: tuple[int, int, int],
    stroke_color: tuple[int, int, int],
    stroke_w: int,
    bg_box: bool = False,
    bg_color: tuple[int, int, int] = (0, 0, 0),
    bg_opacity: float = 0.5,
) -> tuple[int, int, int, int]:
    """Draw text centered at (cx, cy) on a BGR numpy canvas in-place.

    Returns the rendered bounding box (x1, y1, x2, y2) in canvas pixels.
    """
    if not text:
        return (cx, cy, cx, cy)
    if font_path and os.path.exists(font_path):
        try:
            font = ImageFont.truetype(font_path, max(8, int(font_size_px)))
        except Exception:
            font = ImageFont.load_default()
    else:
        font = ImageFont.load_default()

    pil_img = Image.fromarray(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGBA))
    draw = ImageDraw.Draw(pil_img, "RGBA")
    # Measure
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_w)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = cx - tw // 2 - bbox[0]
    y = cy - th // 2 - bbox[1]

    if bg_box:
        pad = max(4, stroke_w * 2)
        box_color = (*bg_color, int(255 * max(0.0, min(1.0, bg_opacity))))
        draw.rectangle(
            (x + bbox[0] - pad, y + bbox[1] - pad, x + bbox[2] + pad, y + bbox[3] + pad),
            fill=box_color,
        )
    draw.text(
        (x, y),
        text,
        font=font,
        fill=(color[0], color[1], color[2], 255),
        stroke_width=stroke_w,
        stroke_fill=(stroke_color[0], stroke_color[1], stroke_color[2], 255),
    )
    composed = np.array(pil_img)
    canvas[:] = cv2.cvtColor(composed, cv2.COLOR_RGBA2BGR)

    out_box = (x + bbox[0], y + bbox[1], x + bbox[2], y + bbox[3])
    return out_box


def render_preview_frame(
    project: Project,
    t_seconds: float = 0.0,
    target_size: tuple[int, int] = (PREVIEW_W, PREVIEW_H),
    part_index: Optional[int] = None,
    show_part_text: bool = True,
) -> np.ndarray:
    """Render a BGR preview frame at ``target_size``."""
    target_w, target_h = target_size
    canvas, _fg_rect = _compose_background(project, target_w, target_h)

    # Scale factor relative to REFERENCE_HEIGHT (output reference).
    # This makes font sizes/stroke/logo sizes equivalent to the rendered output.
    scale = target_h / REFERENCE_HEIGHT

    # Overlay (chroma keyed) - in preview we just dim/show first frame of overlay.
    if project.overlay.path and os.path.exists(project.overlay.path):
        overlay = _ensure_video_frame(project.overlay.path)
        if overlay is None:
            overlay = _load_image_bgr(project.overlay.path)
        if overlay is not None:
            overlay = _fill_crop(overlay, target_w, target_h)
            # cheap keying for preview: use mask based on chosen key
            key = project.overlay.key
            if key == OverlayKey.AUTO:
                from .chroma_key import detect_key
                key = detect_key(project.overlay.path)
            mask = _preview_chroma_mask(overlay, key)
            alpha = (mask.astype(np.float32) / 255.0) * project.overlay.opacity
            canvas = (canvas.astype(np.float32) * (1.0 - alpha[..., None])
                      + overlay.astype(np.float32) * alpha[..., None])
            canvas = np.clip(canvas, 0, 255).astype(np.uint8)

    # Logo
    if project.logo.path and os.path.exists(project.logo.path):
        _draw_logo(canvas, project.logo, t_seconds, target_w, target_h)

    # Text items
    for item in project.texts:
        _draw_text_item(canvas, item, target_w, target_h, scale)

    # Part text
    if show_part_text and project.part_text.enabled:
        idx = part_index if part_index is not None else project.part_text.start_index
        _draw_part_text(canvas, project.part_text, idx, target_w, target_h, scale)

    return canvas


def _preview_chroma_mask(overlay_bgr: np.ndarray, key: OverlayKey) -> np.ndarray:
    """Return an 8-bit alpha mask (255 = keep) for the overlay."""
    if key == OverlayKey.GREEN:
        hsv = cv2.cvtColor(overlay_bgr, cv2.COLOR_BGR2HSV)
        lower = np.array([35, 50, 50])
        upper = np.array([85, 255, 255])
        green = cv2.inRange(hsv, lower, upper)
        return cv2.bitwise_not(green)
    gray = cv2.cvtColor(overlay_bgr, cv2.COLOR_BGR2GRAY)
    if key == OverlayKey.WHITE:
        # Keep darker pixels
        _, mask = cv2.threshold(gray, 220, 255, cv2.THRESH_BINARY_INV)
        return mask
    if key == OverlayKey.BLACK:
        _, mask = cv2.threshold(gray, 25, 255, cv2.THRESH_BINARY)
        return mask
    return np.full(overlay_bgr.shape[:2], 255, dtype=np.uint8)


def _draw_logo(
    canvas: np.ndarray,
    logo: LogoItem,
    t_seconds: float,
    target_w: int,
    target_h: int,
) -> None:
    img = _load_image_bgra(logo.path or "")
    if img is None:
        return
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGRA)
    if img.shape[2] == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
    logo_w = max(2, int(round(logo.size * target_w)))
    aspect = img.shape[0] / img.shape[1] if img.shape[1] > 0 else 1.0
    logo_h = max(2, int(round(logo_w * aspect)))
    img = cv2.resize(img, (logo_w, logo_h), interpolation=cv2.INTER_AREA)

    if 0.0 <= logo.opacity < 1.0:
        img = img.copy()
        img[:, :, 3] = (img[:, :, 3].astype(np.float32) * logo.opacity).astype(np.uint8)

    dx_norm, dy_norm = offset_at(logo.motion, t_seconds, logo.motion_amplitude, logo.motion_period_s)
    cx_norm = logo.x + dx_norm
    cy_norm = logo.y + dy_norm
    cx = int(round(cx_norm * target_w))
    cy = int(round(cy_norm * target_h))
    x = cx - logo_w // 2
    y = cy - logo_h // 2
    _alpha_blend(canvas, img, x, y)


def _draw_text_item(
    canvas: np.ndarray,
    item: TextItem,
    target_w: int,
    target_h: int,
    scale: float,
) -> None:
    font_path = resolve_font_file(item.font_family)
    cx = int(round(item.x * target_w))
    cy = int(round(item.y * target_h))
    _draw_text_pil(
        canvas,
        item.text,
        cx, cy,
        font_path,
        int(round(item.font_size * scale)),
        _hex_to_rgb(item.color),
        _hex_to_rgb(item.stroke_color),
        max(0, int(round(item.stroke_width * scale))),
        bg_box=item.bg_box,
        bg_color=_hex_to_rgb(item.bg_color),
        bg_opacity=item.bg_opacity,
    )


def _draw_part_text(
    canvas: np.ndarray,
    p: PartTextSettings,
    index: int,
    target_w: int,
    target_h: int,
    scale: float,
) -> None:
    text = f"{p.label} {index}"
    font_path = resolve_font_file(p.font_family)
    cx = int(round(p.x * target_w))
    cy = int(round(p.y * target_h))
    _draw_text_pil(
        canvas,
        text,
        cx, cy,
        font_path,
        int(round(p.font_size * scale)),
        _hex_to_rgb(p.color),
        _hex_to_rgb(p.stroke_color),
        max(0, int(round(p.stroke_width * scale))),
    )
