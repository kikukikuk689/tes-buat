"""Main UI window (CustomTkinter).

Tabbed layout:
- Single (default)
- Batch
- Settings

Right pane: preview + log.
"""
from __future__ import annotations

import os
import platform
import queue
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from tkinter import filedialog
from typing import Callable, List, Optional, Tuple

import customtkinter as ctk
from PIL import Image, ImageTk

from ..batch.batch import BatchConfig, BatchStrategy, plan_batch, run_batch
from ..core.background import BackgroundConfig, IMAGE_EXT, VIDEO_EXT
from ..core.ffmpeg_utils import (
    ffmpeg_version,
    find_ffmpeg,
    install_online_async,
    probe_duration,
    status as ffmpeg_status,
)
from ..core.renderer import (
    RESOLUTION_PRESETS,
    RenderJob,
    render,
    render_preview_frame,
)
from ..effects.effects import EffectConfig, list_effects
from ..overlays.logo import ANCHORS, LogoConfig
from ..overlays.lyrics import LyricsConfig
from ..spectrum.styles import (
    SpectrumConfig,
    list_palettes,
    list_styles,
)
from ..utils.fonts import default_font_name, list_available_fonts
from ..utils.logger import get_logger, subscribe

_log = get_logger("ui")


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

AUDIO_FILETYPES = [("Audio files", "*.mp3 *.wav *.flac *.m4a *.ogg *.aac *.opus"),
                   ("All files", "*.*")]
LRC_FILETYPES = [("Lyric files", "*.lrc *.txt"), ("All files", "*.*")]
BG_FILETYPES = [
    ("Media files",
     " ".join([f"*{e}" for e in (*IMAGE_EXT, *VIDEO_EXT)])),
    ("All files", "*.*"),
]
LOGO_FILETYPES = [("Image", "*.png *.jpg *.jpeg *.webp"), ("All files", "*.*")]


def _hex_to_rgb(s: str) -> Tuple[int, int, int]:
    s = s.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    try:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except (ValueError, IndexError):
        return (255, 255, 255)


def _rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


# ------------------------------------------------------------
# Main app
# ------------------------------------------------------------

class MusicVizApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("MusicViz Studio")
        self.geometry("1400x860")
        try:
            self.minsize(1200, 760)
        except Exception:  # noqa: BLE001
            pass

        ctk.set_appearance_mode("light")  # default tema putih, bisa diubah ke "system"
        try:
            ctk.set_default_color_theme("blue")
        except Exception:  # noqa: BLE001
            pass

        # State
        self._audio_path: Optional[str] = None
        self._lrc_path: Optional[str] = None
        self._bg_paths: List[str] = []
        self._logo_path: Optional[str] = None
        self._current_job: Optional[RenderJob] = None
        self._cancel_flag = False
        self._render_thread: Optional[threading.Thread] = None
        self._batch_thread: Optional[threading.Thread] = None
        self._preview_image: Optional[ImageTk.PhotoImage] = None
        self._available_fonts = list_available_fonts()

        # UI variables
        self.var_appearance = ctk.StringVar(value="light")
        self.var_audio = ctk.StringVar(value="")
        self.var_lrc = ctk.StringVar(value="")
        self.var_bg = ctk.StringVar(value="(belum dipilih)")
        self.var_bg_enabled = ctk.BooleanVar(value=True)
        self.var_resolution = ctk.StringVar(value="720p")
        self.var_fps = ctk.IntVar(value=30)
        self.var_encoder = ctk.StringVar(value="libx264")
        self.var_preset = ctk.StringVar(value="veryfast")
        self.var_crf = ctk.IntVar(value=21)
        self.var_bitrate = ctk.IntVar(value=4500)
        self.var_threads = ctk.IntVar(value=0)
        self.var_output = ctk.StringVar(value=str(Path("output").resolve() / "render.mp4"))

        self.var_style = ctk.StringVar(value="Bars")
        self.var_palette = ctk.StringVar(value="Aurora")
        self.var_n_bands = ctk.IntVar(value=64)
        self.var_height = ctk.DoubleVar(value=0.28)
        self.var_density = ctk.DoubleVar(value=1.0)
        self.var_glow = ctk.DoubleVar(value=1.0)
        self.var_padding = ctk.IntVar(value=18)
        self.var_smooth = ctk.DoubleVar(value=0.55)

        self.var_effect = ctk.StringVar(value="Fireflies")
        self.var_effect_intensity = ctk.DoubleVar(value=0.6)
        self.var_effect_color = ctk.StringVar(value="#FFD9A8")

        self.var_logo_enabled = ctk.BooleanVar(value=False)
        self.var_logo_circular = ctk.BooleanVar(value=True)
        self.var_logo_anchor = ctk.StringVar(value="top-right")
        self.var_logo_size = ctk.DoubleVar(value=0.12)
        self.var_logo_margin = ctk.IntVar(value=24)

        self.var_lyrics_font = ctk.StringVar(value=default_font_name() or "")
        self.var_lyrics_size = ctk.DoubleVar(value=0.045)
        self.var_lyrics_color = ctk.StringVar(value="#FFFFFF")
        self.var_lyrics_stroke_color = ctk.StringVar(value="#000000")
        self.var_lyrics_stroke = ctk.IntVar(value=3)
        self.var_lyrics_show_upcoming = ctk.BooleanVar(value=True)
        self.var_lyrics_bottom = ctk.DoubleVar(value=0.78)
        self.var_lyrics_pre_roll = ctk.DoubleVar(value=0.0)

        # Batch tab
        self.var_b_music = ctk.StringVar(value="")
        self.var_b_lyrics = ctk.StringVar(value="")
        self.var_b_bg = ctk.StringVar(value="")
        self.var_b_strategy = ctk.StringVar(value="order")
        self.var_b_multi = ctk.BooleanVar(value=False)
        self.var_b_per_clip = ctk.DoubleVar(value=6.0)
        self.var_b_output = ctk.StringVar(value=str(Path("output").resolve()))

        # Build UI
        self._build_layout()
        self._build_status_bar()
        # Log subscription
        subscribe(self._on_log)
        self._update_ffmpeg_status()
        get_logger().info("MusicViz Studio siap.")

    # ------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------
    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=2, uniform="cols")
        self.grid_columnconfigure(1, weight=3, uniform="cols")
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)

        # Left: tabbed config
        left = ctk.CTkFrame(self)
        left.grid(row=0, column=0, sticky="nsew", padx=(10, 6), pady=(10, 6))
        left.grid_rowconfigure(0, weight=1)
        left.grid_columnconfigure(0, weight=1)

        self.tabs = ctk.CTkTabview(left, segmented_button_selected_color="#3b82f6")
        self.tabs.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        self.tabs.add("Single")
        self.tabs.add("Spectrum")
        self.tabs.add("Effects")
        self.tabs.add("Logo")
        self.tabs.add("Lyrics")
        self.tabs.add("Output")
        self.tabs.add("Batch")
        self.tabs.add("Settings")

        self._build_single_tab(self.tabs.tab("Single"))
        self._build_spectrum_tab(self.tabs.tab("Spectrum"))
        self._build_effects_tab(self.tabs.tab("Effects"))
        self._build_logo_tab(self.tabs.tab("Logo"))
        self._build_lyrics_tab(self.tabs.tab("Lyrics"))
        self._build_output_tab(self.tabs.tab("Output"))
        self._build_batch_tab(self.tabs.tab("Batch"))
        self._build_settings_tab(self.tabs.tab("Settings"))

        # Right: preview + log
        right = ctk.CTkFrame(self)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 10), pady=(10, 6))
        right.grid_rowconfigure(0, weight=3)
        right.grid_rowconfigure(1, weight=0)
        right.grid_rowconfigure(2, weight=2)
        right.grid_columnconfigure(0, weight=1)

        preview_frame = ctk.CTkFrame(right, fg_color=("#f3f4f6", "#1f2937"))
        preview_frame.grid(row=0, column=0, sticky="nsew", padx=8, pady=(8, 4))
        preview_frame.grid_rowconfigure(0, weight=1)
        preview_frame.grid_columnconfigure(0, weight=1)

        self.preview_label = ctk.CTkLabel(preview_frame, text="Preview muncul di sini",
                                          text_color=("#374151", "#9ca3af"))
        self.preview_label.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        preview_ctrl = ctk.CTkFrame(right)
        preview_ctrl.grid(row=1, column=0, sticky="ew", padx=8, pady=2)
        preview_ctrl.grid_columnconfigure(0, weight=0)
        preview_ctrl.grid_columnconfigure(1, weight=1)
        preview_ctrl.grid_columnconfigure(2, weight=0)
        ctk.CTkLabel(preview_ctrl, text="Preview pada (detik):").grid(row=0, column=0, padx=6)
        self.var_preview_t = ctk.DoubleVar(value=20.0)
        ctk.CTkSlider(preview_ctrl, from_=0, to=300,
                      variable=self.var_preview_t,
                      width=300).grid(row=0, column=1, sticky="ew", padx=4)
        ctk.CTkButton(preview_ctrl, text="Refresh Preview",
                      command=self._refresh_preview).grid(row=0, column=2, padx=6)

        log_frame = ctk.CTkFrame(right)
        log_frame.grid(row=2, column=0, sticky="nsew", padx=8, pady=(4, 8))
        log_frame.grid_rowconfigure(1, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(log_frame, text="Log", anchor="w",
                     font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w", padx=8, pady=(6, 0))
        self.log_box = ctk.CTkTextbox(log_frame, font=ctk.CTkFont(family="Courier", size=12))
        self.log_box.grid(row=1, column=0, sticky="nsew", padx=8, pady=6)
        self.log_box.configure(state="disabled")

    def _build_status_bar(self) -> None:
        bar = ctk.CTkFrame(self, height=44, fg_color=("#e5e7eb", "#0f172a"))
        bar.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))
        bar.grid_columnconfigure(0, weight=1)

        left = ctk.CTkFrame(bar, fg_color="transparent")
        left.grid(row=0, column=0, sticky="w", padx=10, pady=4)
        self.lbl_ffmpeg = ctk.CTkLabel(left, text="FFmpeg: ?",
                                        font=ctk.CTkFont(weight="bold"))
        self.lbl_ffmpeg.pack(side="left")
        self.btn_install_ffmpeg = ctk.CTkButton(left, text="Install FFmpeg Online",
                                                command=self._install_ffmpeg,
                                                width=180)
        self.btn_install_ffmpeg.pack(side="left", padx=10)

        right = ctk.CTkFrame(bar, fg_color="transparent")
        right.grid(row=0, column=1, sticky="e", padx=10, pady=4)
        self.progress = ctk.CTkProgressBar(right, width=240)
        self.progress.set(0)
        self.progress.pack(side="left", padx=6)
        self.lbl_progress = ctk.CTkLabel(right, text="Siap.")
        self.lbl_progress.pack(side="left", padx=6)

        self.btn_render = ctk.CTkButton(right, text="Render",
                                        command=self._start_render,
                                        fg_color="#2563eb", hover_color="#1d4ed8")
        self.btn_render.pack(side="left", padx=6)
        self.btn_cancel = ctk.CTkButton(right, text="Cancel",
                                        command=self._cancel_render,
                                        fg_color="#ef4444", hover_color="#dc2626")
        self.btn_cancel.pack(side="left", padx=4)
        self.btn_cancel.configure(state="disabled")

    # ------------------------------------------------------------
    # Tab builders
    # ------------------------------------------------------------
    def _build_single_tab(self, parent) -> None:
        parent.grid_columnconfigure(1, weight=1)
        row = 0
        ctk.CTkLabel(parent, text="File Musik",
                     font=ctk.CTkFont(weight="bold")).grid(row=row, column=0, sticky="w", padx=8, pady=(8, 0))
        row += 1
        ctk.CTkEntry(parent, textvariable=self.var_audio).grid(row=row, column=0, columnspan=2, sticky="ew", padx=8, pady=2)
        row += 1
        ctk.CTkButton(parent, text="Pilih file audio...",
                      command=self._pick_audio).grid(row=row, column=0, sticky="w", padx=8, pady=2)
        self.lbl_audio_info = ctk.CTkLabel(parent, text="", text_color="#6b7280")
        self.lbl_audio_info.grid(row=row, column=1, sticky="w", padx=8)
        row += 1

        ctk.CTkLabel(parent, text="File Lirik (LRC)",
                     font=ctk.CTkFont(weight="bold")).grid(row=row, column=0, sticky="w", padx=8, pady=(12, 0))
        row += 1
        ctk.CTkEntry(parent, textvariable=self.var_lrc).grid(row=row, column=0, columnspan=2, sticky="ew", padx=8, pady=2)
        row += 1
        ctk.CTkButton(parent, text="Pilih file LRC...",
                      command=self._pick_lrc).grid(row=row, column=0, sticky="w", padx=8, pady=2)
        ctk.CTkButton(parent, text="(kosongkan)",
                      command=lambda: (self.var_lrc.set(""), setattr(self, "_lrc_path", None))).grid(row=row, column=1, sticky="w", padx=8)
        row += 1

        ctk.CTkLabel(parent, text="Background (1 atau lebih)",
                     font=ctk.CTkFont(weight="bold")).grid(row=row, column=0, sticky="w", padx=8, pady=(12, 0))
        row += 1
        ctk.CTkCheckBox(parent, text="Aktifkan background",
                        variable=self.var_bg_enabled).grid(row=row, column=0, sticky="w", padx=8, pady=2)
        row += 1
        self.lbl_bg_count = ctk.CTkLabel(parent, textvariable=self.var_bg, text_color="#6b7280")
        self.lbl_bg_count.grid(row=row, column=0, columnspan=2, sticky="w", padx=8)
        row += 1
        bg_btns = ctk.CTkFrame(parent, fg_color="transparent")
        bg_btns.grid(row=row, column=0, columnspan=2, sticky="w", padx=8, pady=2)
        ctk.CTkButton(bg_btns, text="Pilih 1 file...",
                      command=self._pick_bg_single).pack(side="left", padx=2)
        ctk.CTkButton(bg_btns, text="Pilih banyak file...",
                      command=self._pick_bg_multi).pack(side="left", padx=2)
        ctk.CTkButton(bg_btns, text="Bersihkan",
                      command=self._clear_bg).pack(side="left", padx=2)

    def _build_spectrum_tab(self, parent) -> None:
        parent.grid_columnconfigure(1, weight=1)
        row = 0
        ctk.CTkLabel(parent, text="Gaya Spectrum",
                     font=ctk.CTkFont(weight="bold")).grid(row=row, column=0, sticky="w", padx=8, pady=(8, 0))
        row += 1
        ctk.CTkOptionMenu(parent, variable=self.var_style,
                          values=list_styles()).grid(row=row, column=0, sticky="w", padx=8, pady=2)
        ctk.CTkLabel(parent, text="Palette warna:").grid(row=row, column=1, sticky="w", padx=8)
        row += 1
        ctk.CTkOptionMenu(parent, variable=self.var_palette,
                          values=list_palettes()).grid(row=row, column=0, sticky="w", padx=8, pady=2)
        row += 2

        for label, var, lo, hi, fmt in [
            ("Jumlah band", self.var_n_bands, 16, 192, "%d"),
            ("Tinggi spectrum (rasio)", self.var_height, 0.05, 0.6, "%.2f"),
            ("Kepadatan (density)", self.var_density, 0.2, 1.5, "%.2f"),
            ("Glow", self.var_glow, 0, 2, "%.2f"),
            ("Padding bawah (px)", self.var_padding, 0, 200, "%d"),
            ("Smoothness", self.var_smooth, 0, 0.95, "%.2f"),
        ]:
            ctk.CTkLabel(parent, text=label).grid(row=row, column=0, sticky="w", padx=8)
            slider = ctk.CTkSlider(parent, from_=lo, to=hi, variable=var)
            slider.grid(row=row, column=1, sticky="ew", padx=8, pady=2)
            row += 1

    def _build_effects_tab(self, parent) -> None:
        parent.grid_columnconfigure(1, weight=1)
        row = 0
        ctk.CTkLabel(parent, text="Efek Video",
                     font=ctk.CTkFont(weight="bold")).grid(row=row, column=0, sticky="w", padx=8, pady=(8, 0))
        row += 1
        ctk.CTkOptionMenu(parent, variable=self.var_effect,
                          values=list_effects()).grid(row=row, column=0, sticky="w", padx=8, pady=2)
        row += 1
        ctk.CTkLabel(parent, text="Intensitas").grid(row=row, column=0, sticky="w", padx=8)
        ctk.CTkSlider(parent, from_=0, to=1, variable=self.var_effect_intensity).grid(row=row, column=1, sticky="ew", padx=8)
        row += 1
        ctk.CTkLabel(parent, text="Warna efek (hex):").grid(row=row, column=0, sticky="w", padx=8)
        ctk.CTkEntry(parent, textvariable=self.var_effect_color, width=120).grid(row=row, column=1, sticky="w", padx=8)
        row += 1
        ctk.CTkLabel(parent, text="(Pilih 'None' untuk menonaktifkan efek.)",
                     text_color="#9ca3af").grid(row=row, column=0, columnspan=2, sticky="w", padx=8, pady=(8, 0))

    def _build_logo_tab(self, parent) -> None:
        parent.grid_columnconfigure(1, weight=1)
        row = 0
        ctk.CTkLabel(parent, text="Logo",
                     font=ctk.CTkFont(weight="bold")).grid(row=row, column=0, sticky="w", padx=8, pady=(8, 0))
        row += 1
        ctk.CTkCheckBox(parent, text="Aktifkan logo",
                        variable=self.var_logo_enabled).grid(row=row, column=0, sticky="w", padx=8, pady=2)
        ctk.CTkCheckBox(parent, text="Bulat",
                        variable=self.var_logo_circular).grid(row=row, column=1, sticky="w", padx=8)
        row += 1
        self.lbl_logo_path = ctk.CTkLabel(parent, text="(belum dipilih)", text_color="#6b7280")
        self.lbl_logo_path.grid(row=row, column=0, columnspan=2, sticky="w", padx=8)
        row += 1
        ctk.CTkButton(parent, text="Pilih file logo...",
                      command=self._pick_logo).grid(row=row, column=0, sticky="w", padx=8, pady=2)
        row += 1
        ctk.CTkLabel(parent, text="Posisi").grid(row=row, column=0, sticky="w", padx=8)
        ctk.CTkOptionMenu(parent, variable=self.var_logo_anchor,
                          values=list(ANCHORS)).grid(row=row, column=1, sticky="w", padx=8)
        row += 1
        ctk.CTkLabel(parent, text="Ukuran (rasio)").grid(row=row, column=0, sticky="w", padx=8)
        ctk.CTkSlider(parent, from_=0.04, to=0.4,
                      variable=self.var_logo_size).grid(row=row, column=1, sticky="ew", padx=8)
        row += 1
        ctk.CTkLabel(parent, text="Margin (px)").grid(row=row, column=0, sticky="w", padx=8)
        ctk.CTkSlider(parent, from_=0, to=200,
                      variable=self.var_logo_margin).grid(row=row, column=1, sticky="ew", padx=8)

    def _build_lyrics_tab(self, parent) -> None:
        parent.grid_columnconfigure(1, weight=1)
        row = 0
        ctk.CTkLabel(parent, text="Pengaturan Lirik",
                     font=ctk.CTkFont(weight="bold")).grid(row=row, column=0, sticky="w", padx=8, pady=(8, 0))
        row += 1
        fonts = sorted(self._available_fonts.keys()) or ["Default"]
        ctk.CTkLabel(parent, text="Font").grid(row=row, column=0, sticky="w", padx=8)
        ctk.CTkOptionMenu(parent, variable=self.var_lyrics_font,
                          values=fonts, width=260).grid(row=row, column=1, sticky="w", padx=8)
        row += 1
        ctk.CTkLabel(parent, text="Ukuran (rasio H)").grid(row=row, column=0, sticky="w", padx=8)
        ctk.CTkSlider(parent, from_=0.02, to=0.10,
                      variable=self.var_lyrics_size).grid(row=row, column=1, sticky="ew", padx=8)
        row += 1
        ctk.CTkLabel(parent, text="Warna").grid(row=row, column=0, sticky="w", padx=8)
        ctk.CTkEntry(parent, textvariable=self.var_lyrics_color,
                     width=120).grid(row=row, column=1, sticky="w", padx=8)
        row += 1
        ctk.CTkLabel(parent, text="Warna stroke").grid(row=row, column=0, sticky="w", padx=8)
        ctk.CTkEntry(parent, textvariable=self.var_lyrics_stroke_color,
                     width=120).grid(row=row, column=1, sticky="w", padx=8)
        row += 1
        ctk.CTkLabel(parent, text="Stroke (px)").grid(row=row, column=0, sticky="w", padx=8)
        ctk.CTkSlider(parent, from_=0, to=10,
                      variable=self.var_lyrics_stroke).grid(row=row, column=1, sticky="ew", padx=8)
        row += 1
        ctk.CTkLabel(parent, text="Posisi (rasio Y)").grid(row=row, column=0, sticky="w", padx=8)
        ctk.CTkSlider(parent, from_=0.3, to=0.92,
                      variable=self.var_lyrics_bottom).grid(row=row, column=1, sticky="ew", padx=8)
        row += 1
        ctk.CTkCheckBox(parent, text="Tampilkan baris berikutnya (preview)",
                        variable=self.var_lyrics_show_upcoming).grid(row=row, column=0,
                                                                      columnspan=2, sticky="w", padx=8)
        row += 1
        ctk.CTkLabel(parent, text="Pre-roll (detik)").grid(row=row, column=0, sticky="w", padx=8)
        ctk.CTkSlider(parent, from_=0, to=1.5,
                      variable=self.var_lyrics_pre_roll).grid(row=row, column=1, sticky="ew", padx=8)
        row += 1
        ctk.CTkLabel(parent, text="Catatan: Lirik tidak akan muncul sebelum timestamp pertama.",
                     text_color="#9ca3af",
                     wraplength=400).grid(row=row, column=0, columnspan=2, sticky="w", padx=8, pady=(10, 0))

    def _build_output_tab(self, parent) -> None:
        parent.grid_columnconfigure(1, weight=1)
        row = 0
        ctk.CTkLabel(parent, text="Output",
                     font=ctk.CTkFont(weight="bold")).grid(row=row, column=0, sticky="w", padx=8, pady=(8, 0))
        row += 1
        ctk.CTkEntry(parent, textvariable=self.var_output).grid(row=row, column=0, columnspan=2,
                                                                 sticky="ew", padx=8, pady=2)
        row += 1
        ctk.CTkButton(parent, text="Pilih file output...",
                      command=self._pick_output).grid(row=row, column=0, sticky="w", padx=8)
        row += 1

        ctk.CTkLabel(parent, text="Resolusi").grid(row=row, column=0, sticky="w", padx=8, pady=(12, 0))
        ctk.CTkOptionMenu(parent, variable=self.var_resolution,
                          values=list(RESOLUTION_PRESETS.keys()) + ["custom"]).grid(row=row, column=1, sticky="w", padx=8)
        row += 1
        ctk.CTkLabel(parent, text="FPS").grid(row=row, column=0, sticky="w", padx=8)
        ctk.CTkOptionMenu(parent, variable=self.var_fps,
                          values=["24", "30", "60"],
                          command=lambda v: self.var_fps.set(int(v))).grid(row=row, column=1, sticky="w", padx=8)
        row += 1
        ctk.CTkLabel(parent, text="Encoder").grid(row=row, column=0, sticky="w", padx=8)
        ctk.CTkOptionMenu(parent, variable=self.var_encoder,
                          values=["libx264", "h264_nvenc", "h264_qsv", "h264_amf", "libx265"]).grid(row=row, column=1, sticky="w", padx=8)
        row += 1
        ctk.CTkLabel(parent, text="Preset").grid(row=row, column=0, sticky="w", padx=8)
        ctk.CTkOptionMenu(parent, variable=self.var_preset,
                          values=["ultrafast", "superfast", "veryfast",
                                  "faster", "fast", "medium", "slow"]).grid(row=row, column=1, sticky="w", padx=8)
        row += 1
        ctk.CTkLabel(parent, text="CRF (lebih kecil = lebih bagus)").grid(row=row, column=0, sticky="w", padx=8)
        ctk.CTkSlider(parent, from_=14, to=32,
                      variable=self.var_crf).grid(row=row, column=1, sticky="ew", padx=8)
        row += 1
        ctk.CTkLabel(parent, text="Bitrate (Kbps)").grid(row=row, column=0, sticky="w", padx=8)
        ctk.CTkEntry(parent, textvariable=self.var_bitrate, width=120).grid(row=row, column=1, sticky="w", padx=8)
        row += 1
        ctk.CTkLabel(parent, text="FFmpeg threads (0 = auto)").grid(row=row, column=0, sticky="w", padx=8)
        ctk.CTkEntry(parent, textvariable=self.var_threads, width=120).grid(row=row, column=1, sticky="w", padx=8)
        row += 1
        ctk.CTkButton(parent, text="Buka folder output",
                      command=self._open_output_folder).grid(row=row, column=0, sticky="w", padx=8, pady=(12, 0))
        ctk.CTkButton(parent, text="Play video output",
                      command=self._play_output).grid(row=row, column=1, sticky="w", padx=8, pady=(12, 0))

    def _build_batch_tab(self, parent) -> None:
        parent.grid_columnconfigure(1, weight=1)
        row = 0
        ctk.CTkLabel(parent, text="Batch",
                     font=ctk.CTkFont(weight="bold")).grid(row=row, column=0, sticky="w", padx=8, pady=(8, 0))
        row += 1
        for label, var, picker in [
            ("Folder musik", self.var_b_music, lambda: self._pick_folder(self.var_b_music)),
            ("Folder lirik", self.var_b_lyrics, lambda: self._pick_folder(self.var_b_lyrics)),
            ("Folder background", self.var_b_bg, lambda: self._pick_folder(self.var_b_bg)),
            ("Folder output", self.var_b_output, lambda: self._pick_folder(self.var_b_output)),
        ]:
            ctk.CTkLabel(parent, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=2)
            ctk.CTkEntry(parent, textvariable=var).grid(row=row, column=1, sticky="ew", padx=8)
            row += 1
            ctk.CTkButton(parent, text="Pilih folder...",
                          command=picker).grid(row=row, column=1, sticky="w", padx=8)
            row += 1

        ctk.CTkLabel(parent, text="Strategi pencocokan background").grid(row=row, column=0, sticky="w", padx=8, pady=(12, 0))
        ctk.CTkOptionMenu(parent, variable=self.var_b_strategy,
                          values=["order", "name", "random"]).grid(row=row, column=1, sticky="w", padx=8)
        row += 1
        ctk.CTkCheckBox(parent, text="Multi-background per video (untuk order/random)",
                        variable=self.var_b_multi).grid(row=row, column=0, columnspan=2, sticky="w", padx=8)
        row += 1
        ctk.CTkLabel(parent, text="Durasi tiap background (detik)").grid(row=row, column=0, sticky="w", padx=8)
        ctk.CTkSlider(parent, from_=2, to=30, variable=self.var_b_per_clip).grid(row=row, column=1, sticky="ew", padx=8)
        row += 1
        btns = ctk.CTkFrame(parent, fg_color="transparent")
        btns.grid(row=row, column=0, columnspan=2, sticky="w", padx=8, pady=12)
        ctk.CTkButton(btns, text="Preview rencana batch",
                      command=self._preview_batch_plan).pack(side="left", padx=4)
        ctk.CTkButton(btns, text="Mulai Batch",
                      command=self._start_batch,
                      fg_color="#10b981", hover_color="#059669").pack(side="left", padx=4)

    def _build_settings_tab(self, parent) -> None:
        row = 0
        ctk.CTkLabel(parent, text="Tampilan",
                     font=ctk.CTkFont(weight="bold")).grid(row=row, column=0, sticky="w", padx=8, pady=(8, 0))
        row += 1
        ctk.CTkLabel(parent, text="Tema").grid(row=row, column=0, sticky="w", padx=8)
        ctk.CTkOptionMenu(parent, variable=self.var_appearance,
                          values=["light", "dark", "system"],
                          command=self._set_appearance).grid(row=row, column=1, sticky="w", padx=8)
        row += 1
        ctk.CTkLabel(parent, text="Versi: 1.0.0",
                     text_color="#9ca3af").grid(row=row, column=0, columnspan=2, padx=8, pady=20)

    # ------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------
    def _set_appearance(self, val: str) -> None:
        ctk.set_appearance_mode(val)

    def _pick_audio(self) -> None:
        path = filedialog.askopenfilename(title="Pilih file audio", filetypes=AUDIO_FILETYPES)
        if not path:
            return
        self._audio_path = path
        self.var_audio.set(path)
        dur = probe_duration(path) or 0.0
        self.lbl_audio_info.configure(text=f"Durasi: {dur:.1f}s ({Path(path).name})")
        get_logger().info("Audio dipilih: %s (%.1fs)", path, dur)
        # Auto-set output filename
        if not self.var_output.get() or "render.mp4" in self.var_output.get():
            out = Path("output") / (Path(path).stem + ".mp4")
            self.var_output.set(str(out.resolve()))

    def _pick_lrc(self) -> None:
        path = filedialog.askopenfilename(title="Pilih file LRC", filetypes=LRC_FILETYPES)
        if not path:
            return
        self._lrc_path = path
        self.var_lrc.set(path)
        get_logger().info("Lirik dipilih: %s", path)

    def _pick_bg_single(self) -> None:
        path = filedialog.askopenfilename(title="Pilih background", filetypes=BG_FILETYPES)
        if not path:
            return
        self._bg_paths = [path]
        self.var_bg.set(f"1 file: {Path(path).name}")
        get_logger().info("Background dipilih: %s", path)

    def _pick_bg_multi(self) -> None:
        paths = filedialog.askopenfilenames(title="Pilih banyak background", filetypes=BG_FILETYPES)
        if not paths:
            return
        self._bg_paths = list(paths)
        names = ", ".join(Path(p).name for p in paths[:3])
        more = "" if len(paths) <= 3 else f" (+{len(paths) - 3} lagi)"
        self.var_bg.set(f"{len(paths)} file: {names}{more}")
        get_logger().info("%d background dipilih", len(paths))

    def _clear_bg(self) -> None:
        self._bg_paths = []
        self.var_bg.set("(belum dipilih)")

    def _pick_logo(self) -> None:
        path = filedialog.askopenfilename(title="Pilih logo", filetypes=LOGO_FILETYPES)
        if not path:
            return
        self._logo_path = path
        self.lbl_logo_path.configure(text=Path(path).name)
        self.var_logo_enabled.set(True)

    def _pick_output(self) -> None:
        path = filedialog.asksaveasfilename(title="Simpan output sebagai...",
                                            defaultextension=".mp4",
                                            filetypes=[("MP4", "*.mp4")])
        if path:
            self.var_output.set(path)

    def _pick_folder(self, var: ctk.StringVar) -> None:
        path = filedialog.askdirectory()
        if path:
            var.set(path)

    def _open_output_folder(self) -> None:
        out = Path(self.var_output.get()).parent
        out.mkdir(parents=True, exist_ok=True)
        _open_path(out)

    def _play_output(self) -> None:
        out = Path(self.var_output.get())
        if not out.exists():
            get_logger().warning("File output belum ada: %s", out)
            return
        _open_path(out)

    # ------------------------------------------------------------
    # FFmpeg
    # ------------------------------------------------------------
    def _update_ffmpeg_status(self) -> None:
        st = ffmpeg_status()
        if st.available:
            self.lbl_ffmpeg.configure(text=f"FFmpeg: ✓ ({Path(st.path).name})",
                                      text_color="#16a34a")
            self.btn_install_ffmpeg.configure(state="disabled",
                                              text="FFmpeg tersedia")
        else:
            self.lbl_ffmpeg.configure(text="FFmpeg: ✗ belum terinstall",
                                      text_color="#ef4444")
            self.btn_install_ffmpeg.configure(state="normal",
                                              text="Install FFmpeg Online")

    def _install_ffmpeg(self) -> None:
        self.btn_install_ffmpeg.configure(state="disabled", text="Mengunduh...")
        self.lbl_progress.configure(text="Mengunduh FFmpeg...")

        def _progress(read: int, total: int) -> None:
            if total > 0:
                pct = read / total
                self.progress.set(pct)
                self.lbl_progress.configure(text=f"Download {pct*100:.0f}%")

        def _status(msg: str) -> None:
            self.lbl_progress.configure(text=msg)

        def _done(ok: bool) -> None:
            self.progress.set(0)
            if ok:
                self.lbl_progress.configure(text="FFmpeg siap.")
            else:
                self.lbl_progress.configure(text="Gagal install FFmpeg.")
                self.btn_install_ffmpeg.configure(state="normal", text="Install FFmpeg Online")
            self._update_ffmpeg_status()

        install_online_async(on_done=_done, progress=_progress, status_cb=_status)

    # ------------------------------------------------------------
    # Job construction
    # ------------------------------------------------------------
    def _current_render_job(self) -> RenderJob:
        if not self._audio_path:
            raise ValueError("Silakan pilih file audio dulu.")
        bg_cfg = BackgroundConfig(
            paths=self._bg_paths,
            enabled=self.var_bg_enabled.get() and bool(self._bg_paths),
        )
        eff_cfgs: List[EffectConfig] = []
        if self.var_effect.get() and self.var_effect.get() != "None":
            eff_cfgs.append(EffectConfig(
                name=self.var_effect.get(),
                intensity=self.var_effect_intensity.get(),
                color=_hex_to_rgb(self.var_effect_color.get()),
            ))
        spec_cfg = SpectrumConfig(
            style=self.var_style.get(),
            palette=self.var_palette.get(),
            n_bands=int(self.var_n_bands.get()),
            height_ratio=float(self.var_height.get()),
            density=float(self.var_density.get()),
            glow=float(self.var_glow.get()),
            bottom_padding=int(self.var_padding.get()),
            smoothness=float(self.var_smooth.get()),
        )
        logo_cfg = LogoConfig(
            path=self._logo_path,
            enabled=self.var_logo_enabled.get() and bool(self._logo_path),
            circular=self.var_logo_circular.get(),
            anchor=self.var_logo_anchor.get(),
            size_ratio=float(self.var_logo_size.get()),
            margin=int(self.var_logo_margin.get()),
        )
        lyrics_cfg = LyricsConfig(
            font_name=self.var_lyrics_font.get() or None,
            font_size_ratio=float(self.var_lyrics_size.get()),
            color=_hex_to_rgb(self.var_lyrics_color.get()),
            stroke_color=_hex_to_rgb(self.var_lyrics_stroke_color.get()),
            stroke_width=int(self.var_lyrics_stroke.get()),
            show_upcoming=self.var_lyrics_show_upcoming.get(),
            bottom_ratio=float(self.var_lyrics_bottom.get()),
            pre_roll=float(self.var_lyrics_pre_roll.get()),
        )
        return RenderJob(
            audio_path=self._audio_path,
            output_path=self.var_output.get(),
            lrc_path=self._lrc_path or (self.var_lrc.get() or None),
            background=bg_cfg,
            spectrum=spec_cfg,
            effects=eff_cfgs,
            logo=logo_cfg,
            lyrics=lyrics_cfg,
            resolution=self.var_resolution.get(),
            fps=int(self.var_fps.get()),
            encoder=self.var_encoder.get(),
            preset=self.var_preset.get(),
            crf=int(self.var_crf.get()),
            bitrate_kbps=int(self.var_bitrate.get()),
            threads=int(self.var_threads.get()),
        )

    # ------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------
    def _refresh_preview(self) -> None:
        try:
            job = self._current_render_job()
        except ValueError as e:
            get_logger().warning(str(e))
            return
        t = float(self.var_preview_t.get())

        def _work() -> None:
            try:
                im = render_preview_frame(job, t)
                self.after(0, lambda: self._set_preview(im))
            except Exception as e:  # noqa: BLE001
                get_logger().exception("Preview gagal: %s", e)

        threading.Thread(target=_work, daemon=True).start()

    def _set_preview(self, im: Image.Image) -> None:
        # Resize agar muat
        w = max(self.preview_label.winfo_width(), 600)
        h = max(self.preview_label.winfo_height(), 360)
        ratio = min(w / im.width, h / im.height)
        new = (max(1, int(im.width * ratio)), max(1, int(im.height * ratio)))
        im2 = im.resize(new, Image.LANCZOS)
        self._preview_image = ImageTk.PhotoImage(im2)
        self.preview_label.configure(image=self._preview_image, text="")

    # ------------------------------------------------------------
    # Render
    # ------------------------------------------------------------
    def _start_render(self) -> None:
        try:
            job = self._current_render_job()
        except ValueError as e:
            get_logger().error(str(e))
            return
        if self._render_thread and self._render_thread.is_alive():
            get_logger().warning("Render sedang berjalan.")
            return
        self._cancel_flag = False
        self.btn_render.configure(state="disabled")
        self.btn_cancel.configure(state="normal")
        self.progress.set(0)
        self.lbl_progress.configure(text="Memulai render...")

        def _progress(frac: float, msg: str) -> None:
            self.after(0, lambda: (self.progress.set(frac),
                                   self.lbl_progress.configure(text=msg)))

        def _work() -> None:
            try:
                token = _TokenWrap(self)
                from ..core.renderer import _CancelToken
                ct = _CancelToken()
                token.token = ct

                def _check_cancel():
                    if self._cancel_flag:
                        ct.cancel()

                # Periodically poll cancel flag
                def _poller():
                    while self._render_thread and self._render_thread.is_alive():
                        _check_cancel()
                        time.sleep(0.3)
                threading.Thread(target=_poller, daemon=True).start()

                out = render(job, progress_cb=_progress, cancel=ct)
                get_logger().info("Output: %s", out)
                self.after(0, lambda: self.lbl_progress.configure(text=f"Selesai: {Path(out).name}"))
            except Exception as e:  # noqa: BLE001
                get_logger().exception("Render gagal: %s", e)
                self.after(0, lambda: self.lbl_progress.configure(text=f"Gagal: {e}"))
            finally:
                self.after(0, lambda: (self.btn_render.configure(state="normal"),
                                       self.btn_cancel.configure(state="disabled"),
                                       self.progress.set(1.0)))

        self._render_thread = threading.Thread(target=_work, daemon=True)
        self._render_thread.start()

    def _cancel_render(self) -> None:
        self._cancel_flag = True
        get_logger().info("Mengirim sinyal cancel...")

    # ------------------------------------------------------------
    # Batch
    # ------------------------------------------------------------
    def _build_batch_config(self) -> BatchConfig:
        if not self.var_b_music.get():
            raise ValueError("Folder musik wajib diisi.")
        tpl = self._current_render_job() if self._audio_path else RenderJob(audio_path="", output_path="")
        # Reset paths to placeholder
        tpl.audio_path = ""
        tpl.output_path = ""
        return BatchConfig(
            music_folder=self.var_b_music.get(),
            lyrics_folder=self.var_b_lyrics.get() or None,
            background_folder=self.var_b_bg.get() or None,
            output_folder=self.var_b_output.get() or "output",
            strategy=BatchStrategy(self.var_b_strategy.get()),
            multi_background=self.var_b_multi.get(),
            per_clip_seconds=float(self.var_b_per_clip.get()),
            template=tpl,
        )

    def _preview_batch_plan(self) -> None:
        try:
            cfg = self._build_batch_config()
            jobs = plan_batch(cfg)
        except Exception as e:  # noqa: BLE001
            get_logger().error("Plan gagal: %s", e)
            return
        get_logger().info("Rencana batch (%d job):", len(jobs))
        for j in jobs:
            get_logger().info(" - %s | lrc=%s | bg=%d", j.audio.name,
                              j.lrc.name if j.lrc else "-", len(j.backgrounds))

    def _start_batch(self) -> None:
        try:
            cfg = self._build_batch_config()
        except Exception as e:  # noqa: BLE001
            get_logger().error("Batch gagal: %s", e)
            return
        if self._batch_thread and self._batch_thread.is_alive():
            get_logger().warning("Batch sedang berjalan.")
            return

        def _progress(idx: int, total: int, name: str, frac: float) -> None:
            self.after(0, lambda: (
                self.progress.set(((idx - 1) + frac) / total),
                self.lbl_progress.configure(text=f"[{idx}/{total}] {name} - {frac*100:.0f}%"),
            ))

        def _work() -> None:
            try:
                outs = run_batch(cfg, progress_cb=_progress,
                                 cancel_check=lambda: self._cancel_flag)
                get_logger().info("Batch selesai: %d file", len(outs))
                self.after(0, lambda: self.lbl_progress.configure(text=f"Batch selesai ({len(outs)} file)"))
            except Exception as e:  # noqa: BLE001
                get_logger().exception("Batch error: %s", e)

        self._cancel_flag = False
        self._batch_thread = threading.Thread(target=_work, daemon=True)
        self._batch_thread.start()

    # ------------------------------------------------------------
    # Log
    # ------------------------------------------------------------
    def _on_log(self, level: str, msg: str) -> None:
        # Marshal to main thread
        try:
            self.after(0, lambda: self._append_log(level, msg))
        except RuntimeError:
            pass

    def _append_log(self, level: str, msg: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")


# --- helpers ---

class _TokenWrap:
    def __init__(self, app: MusicVizApp):
        self.app = app
        self.token = None


def _open_path(p: Path) -> None:
    p = Path(p)
    try:
        if platform.system() == "Windows":
            os.startfile(p)  # type: ignore[attr-defined]
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", str(p)])
        else:
            subprocess.Popen(["xdg-open", str(p)])
    except OSError as e:
        get_logger().warning("Tidak bisa membuka %s: %s", p, e)


def run_app() -> None:
    app = MusicVizApp()
    app.mainloop()
