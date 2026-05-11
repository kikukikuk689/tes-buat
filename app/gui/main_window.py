"""Main GUI window for Music Spectrum Studio."""
from __future__ import annotations

import dataclasses
import os
import sys
import threading
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, QObject, QThread, Signal, Slot, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QIcon
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
    QSizePolicy, QSlider, QSpinBox, QSplitter, QStatusBar, QTabWidget, QVBoxLayout,
    QWidget,
)

from ..core import ffmpeg_utils
from ..core.background_handler import BackgroundConfig
from ..core.batch_renderer import BatchConfig, list_batch_pairs, run_batch
from ..core.effects import EFFECTS, list_effects
from ..core.logo_handler import LogoConfig, POSITIONS as LOGO_POSITIONS
from ..core.renderer import (
    RESOLUTIONS, RenderConfig, Renderer, LyricStyle,
)
from ..core.spectrum_styles import PALETTES, SpectrumConfig, list_styles
from ..utils.fonts import discover_fonts
from ..utils.logger import AppLogger


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hex(c):
    return "#{:02x}{:02x}{:02x}".format(*c)


def _pick_color(initial):
    from PySide6.QtGui import QColor
    dlg = QColorDialog(QColor(*initial))
    if dlg.exec():
        c = dlg.selectedColor()
        return c.red(), c.green(), c.blue()
    return initial


def _color_button(initial):
    btn = QPushButton(_hex(initial))
    btn.setStyleSheet(f"background:{_hex(initial)}; color: white; padding:4px 12px;")
    btn._color = tuple(initial)

    def _click():
        c = _pick_color(btn._color)
        btn._color = c
        btn.setText(_hex(c))
        btn.setStyleSheet(f"background:{_hex(c)}; color: white; padding:4px 12px;")
    btn.clicked.connect(_click)
    return btn


# ---------------------------------------------------------------------------
# Worker threads
# ---------------------------------------------------------------------------

class RenderWorker(QObject):
    progress = Signal(float, str)
    finished = Signal(bool, str)

    def __init__(self, cfg: RenderConfig):
        super().__init__()
        self.cfg = cfg
        self._renderer: Optional[Renderer] = None

    def cancel(self):
        if self._renderer:
            self._renderer.cancel()

    @Slot()
    def run(self):
        try:
            self._renderer = Renderer(self.cfg)
            ok = self._renderer.render(progress=lambda r, m: self.progress.emit(r, m))
            self.finished.emit(ok, self.cfg.output_path)
        except Exception as exc:  # pragma: no cover
            AppLogger.get().error(f"Render error: {exc}")
            self.finished.emit(False, str(exc))


class BatchWorker(QObject):
    progress = Signal(int, int, float, str)
    finished = Signal(list)

    def __init__(self, cfg: BatchConfig):
        super().__init__()
        self.cfg = cfg
        self._cancel = threading.Event()

    def cancel(self):
        self._cancel.set()

    @Slot()
    def run(self):
        results = run_batch(self.cfg,
                            progress=lambda i, t, r, m: self.progress.emit(i, t, r, m),
                            cancel_flag=self._cancel.is_set)
        self.finished.emit(results)


class InstallWorker(QObject):
    progress = Signal(str, float)
    finished = Signal(bool, str)

    @Slot()
    def run(self):
        ok, msg = ffmpeg_utils.install_ffmpeg(
            progress=lambda t, r: self.progress.emit(t, r))
        self.finished.emit(ok, msg)


# ---------------------------------------------------------------------------
# Main Window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Music Spectrum Studio")
        self.resize(1400, 900)
        self.log = AppLogger.get()

        # State
        self.bg_files: List[str] = []
        self.fonts = discover_fonts()
        self.render_thread: Optional[QThread] = None
        self.render_worker: Optional[RenderWorker] = None
        self.batch_thread: Optional[QThread] = None
        self.batch_worker: Optional[BatchWorker] = None
        self.install_thread: Optional[QThread] = None
        self.install_worker: Optional[InstallWorker] = None

        # Layout
        self._build_ui()
        self._refresh_ffmpeg_status()

        # Logger -> log widget
        self.log.add_listener(self._on_log)

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # Top bar with FFmpeg status
        bar = QHBoxLayout()
        self.title_label = QLabel("<b>Music Spectrum Studio</b> &mdash; pro music visualizer")
        bar.addWidget(self.title_label)
        bar.addStretch(1)
        self.ff_status = QLabel("FFmpeg: ...")
        bar.addWidget(self.ff_status)
        self.ff_install_btn = QPushButton("Install FFmpeg")
        self.ff_install_btn.clicked.connect(self._install_ffmpeg)
        bar.addWidget(self.ff_install_btn)
        self.ff_refresh_btn = QPushButton("Cek Ulang")
        self.ff_refresh_btn.clicked.connect(self._refresh_ffmpeg_status)
        bar.addWidget(self.ff_refresh_btn)
        root.addLayout(bar)

        # Main splitter: left config tabs, right preview/log
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        root.addWidget(splitter, 1)

        # Left side: tab widget
        self.tabs = QTabWidget()
        self.tabs.setUsesScrollButtons(False)
        splitter.addWidget(self.tabs)
        self._build_tab_project()
        self._build_tab_spectrum()
        self._build_tab_effects()
        self._build_tab_lyrics()
        self._build_tab_logo()
        self._build_tab_output()
        self._build_tab_batch()

        # Right side: preview + log
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(6)

        prev_group = QGroupBox("Preview")
        prev_layout = QVBoxLayout(prev_group)
        from .preview_widget import PreviewWidget
        self.preview = PreviewWidget()
        prev_layout.addWidget(self.preview, 1)

        # Preview controls
        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel("Waktu (detik):"))
        self.preview_time = QDoubleSpinBox()
        self.preview_time.setRange(0, 7200)
        self.preview_time.setValue(20.0)
        ctrl.addWidget(self.preview_time)
        btn_preview = QPushButton("Preview Frame")
        btn_preview.clicked.connect(self._preview_frame)
        ctrl.addWidget(btn_preview)
        btn_play = QPushButton("Putar Hasil")
        btn_play.clicked.connect(self._play_last_output)
        ctrl.addWidget(btn_play)
        ctrl.addStretch(1)
        prev_layout.addLayout(ctrl)

        # Video player
        self.player_widget = QVideoWidget()
        self.player_widget.setMinimumHeight(200)
        self.player = QMediaPlayer()
        self.audio_out = QAudioOutput()
        self.player.setAudioOutput(self.audio_out)
        self.player.setVideoOutput(self.player_widget)
        prev_layout.addWidget(self.player_widget, 1)
        rl.addWidget(prev_group, 3)

        log_group = QGroupBox("Log")
        log_layout = QVBoxLayout(log_group)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        log_layout.addWidget(self.log_view, 1)
        rl.addWidget(log_group, 2)
        splitter.addWidget(right)
        splitter.setSizes([600, 800])

        # Bottom action bar
        actions = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        actions.addWidget(self.progress_bar, 3)
        self.btn_render = QPushButton("Render Sekarang")
        self.btn_render.setObjectName("primary")
        self.btn_render.clicked.connect(self._start_render)
        actions.addWidget(self.btn_render)
        self.btn_cancel = QPushButton("Batalkan")
        self.btn_cancel.setObjectName("danger")
        self.btn_cancel.clicked.connect(self._cancel_render)
        self.btn_cancel.setEnabled(False)
        actions.addWidget(self.btn_cancel)
        self.btn_open_out = QPushButton("Buka Folder Output")
        self.btn_open_out.clicked.connect(self._open_output_folder)
        actions.addWidget(self.btn_open_out)
        root.addLayout(actions)

        # Status bar
        self.setStatusBar(QStatusBar(self))
        self.statusBar().showMessage("Siap.")

    # ------------------------------------------------------------ Project tab
    def _build_tab_project(self):
        w = QWidget()
        f = QFormLayout(w)

        self.audio_input = QLineEdit()
        b1 = QPushButton("Pilih File...")
        b1.clicked.connect(lambda: self._pick_file(self.audio_input,
                                                    "Audio/Video Files (*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.mp4 *.mkv)"))
        f.addRow("File Musik:", _row(self.audio_input, b1))

        self.lyric_input = QLineEdit()
        b2 = QPushButton("Pilih File...")
        b2.clicked.connect(lambda: self._pick_file(self.lyric_input, "Lirik (*.lrc)"))
        f.addRow("File Lirik (.lrc):", _row(self.lyric_input, b2))

        # Background list + controls
        self.bg_list = QListWidget()
        self.bg_list.setMaximumHeight(110)
        bg_add = QPushButton("Tambah Gambar/Video")
        bg_add.clicked.connect(self._add_backgrounds)
        bg_clear = QPushButton("Hapus Semua")
        bg_clear.clicked.connect(self._clear_backgrounds)
        bg_row = QVBoxLayout()
        bg_row.addWidget(self.bg_list)
        h = QHBoxLayout()
        h.addWidget(bg_add)
        h.addWidget(bg_clear)
        bg_row.addLayout(h)
        bg_box = QGroupBox("Background (gambar/video)")
        bg_box.setLayout(bg_row)
        f.addRow(bg_box)

        bg_opts = QFormLayout()
        self.bg_multi_enabled = QCheckBox("Pakai beberapa gambar/video sekaligus")
        bg_opts.addRow(self.bg_multi_enabled)
        self.bg_multi_strategy = QComboBox()
        self.bg_multi_strategy.addItems(["Order", "Random"])
        bg_opts.addRow("Mode multi (urutan / acak):", self.bg_multi_strategy)
        self.bg_blur = _slider(0, 100, 25)
        bg_opts.addRow("Blur:", self.bg_blur)
        self.bg_darken = _slider(0, 100, 30)
        bg_opts.addRow("Gelap (overlay hitam):", self.bg_darken)
        self.bg_zoom = QCheckBox("Aktifkan zoom pulse (Ken Burns)")
        self.bg_zoom.setChecked(True)
        bg_opts.addRow(self.bg_zoom)
        bg_opt_box = QGroupBox("Pengaturan Background")
        bg_opt_box.setLayout(bg_opts)
        f.addRow(bg_opt_box)

        self.tabs.addTab(w, "Project")

    # ------------------------------------------------------------ Spectrum tab
    def _build_tab_spectrum(self):
        w = QWidget()
        f = QFormLayout(w)

        self.spec_style = QComboBox()
        self.spec_style.addItems(list_styles())
        f.addRow("Gaya Spectrum:", self.spec_style)

        self.spec_palette = QComboBox()
        self.spec_palette.addItems(list(PALETTES.keys()))
        self.spec_palette.setCurrentText("Aurora")
        f.addRow("Palet Warna:", self.spec_palette)

        self.spec_height = _slider(10, 60, 25)  # height_ratio % of canvas
        f.addRow("Tinggi Area Spectrum (%):", self.spec_height)

        self.spec_bottom = _slider(0, 30, 6)
        f.addRow("Jarak dari bawah (%):", self.spec_bottom)

        self.spec_density = _slider(40, 100, 85)
        f.addRow("Kepadatan Bar (%):", self.spec_density)

        self.spec_opacity = _slider(20, 100, 100)
        f.addRow("Opasitas (%):", self.spec_opacity)

        self.spec_glow = _slider(0, 100, 60)
        f.addRow("Glow (%):", self.spec_glow)

        self.spec_mirror = QCheckBox("Mirror")
        f.addRow("", self.spec_mirror)

        self.tabs.addTab(w, "Spectrum")

    # ------------------------------------------------------------ Effects tab
    def _build_tab_effects(self):
        w = QWidget()
        f = QFormLayout(w)
        self.fx_name = QComboBox()
        self.fx_name.addItems(list_effects())
        self.fx_name.setCurrentText("Fireflies")
        f.addRow("Efek:", self.fx_name)
        self.fx_intensity = _slider(0, 200, 100)
        f.addRow("Intensitas (%):", self.fx_intensity)
        self.fx_color = _color_button((255, 230, 160))
        f.addRow("Warna efek:", self.fx_color)
        f.addRow(QLabel("<i class='muted'>Tip: pilih Sparkles/Pulse Rings untuk lagu beat kuat, "
                        "Fireflies/Stars untuk lagu lambat.</i>"))
        self.tabs.addTab(w, "Efek")

    # ------------------------------------------------------------ Lyrics tab
    def _build_tab_lyrics(self):
        w = QWidget()
        f = QFormLayout(w)
        self.lyric_font = QComboBox()
        for fi in self.fonts:
            self.lyric_font.addItem(fi.family)
        # default to first preferred match
        for pref in ["Montserrat", "Poppins", "Roboto", "Inter", "DejaVu Sans"]:
            idx = self.lyric_font.findText(pref)
            if idx >= 0:
                self.lyric_font.setCurrentIndex(idx)
                break
        f.addRow("Font:", self.lyric_font)

        self.lyric_size = _slider(20, 120, 55)  # x0.001 of height
        f.addRow("Ukuran (%H × 1/1000):", self.lyric_size)

        self.lyric_color = _color_button((255, 255, 255))
        f.addRow("Warna Teks:", self.lyric_color)
        self.lyric_outline_color = _color_button((0, 0, 0))
        f.addRow("Warna Outline:", self.lyric_outline_color)
        self.lyric_outline_width = _slider(0, 10, 3)
        f.addRow("Lebar Outline:", self.lyric_outline_width)

        self.lyric_box = QCheckBox("Tampilkan kotak gelap di belakang teks")
        f.addRow(self.lyric_box)
        self.lyric_uppercase = QCheckBox("Huruf besar (UPPERCASE)")
        f.addRow(self.lyric_uppercase)
        self.lyric_position = _slider(20, 90, 68)
        f.addRow("Posisi Vertikal (%):", self.lyric_position)
        self.lyric_offset = QSpinBox()
        self.lyric_offset.setRange(-5000, 5000)
        self.lyric_offset.setValue(0)
        self.lyric_offset.setSuffix(" ms")
        f.addRow("Offset Timestamp Lirik:", self.lyric_offset)

        self.tabs.addTab(w, "Lirik")

    # ------------------------------------------------------------ Logo tab
    def _build_tab_logo(self):
        w = QWidget()
        f = QFormLayout(w)
        self.logo_enabled = QCheckBox("Aktifkan logo")
        f.addRow(self.logo_enabled)
        self.logo_path = QLineEdit()
        b = QPushButton("Pilih...")
        b.clicked.connect(lambda: self._pick_file(self.logo_path,
                                                   "Gambar (*.png *.jpg *.jpeg *.webp)"))
        f.addRow("File Logo:", _row(self.logo_path, b))
        self.logo_circular = QCheckBox("Bentuk bulat (lingkaran)")
        self.logo_circular.setChecked(True)
        f.addRow(self.logo_circular)
        self.logo_position = QComboBox()
        self.logo_position.addItems(LOGO_POSITIONS.keys())
        self.logo_position.setCurrentText("Top Right")
        f.addRow("Posisi:", self.logo_position)
        self.logo_size = _slider(4, 40, 12)
        f.addRow("Ukuran (%):", self.logo_size)
        self.logo_opacity = _slider(20, 100, 100)
        f.addRow("Opasitas (%):", self.logo_opacity)
        self.logo_border = QCheckBox("Pakai border")
        self.logo_border.setChecked(True)
        f.addRow(self.logo_border)
        self.logo_shadow = QCheckBox("Pakai bayangan")
        self.logo_shadow.setChecked(True)
        f.addRow(self.logo_shadow)
        self.tabs.addTab(w, "Logo")

    # ------------------------------------------------------------ Output tab
    def _build_tab_output(self):
        w = QWidget()
        f = QFormLayout(w)
        self.out_resolution = QComboBox()
        self.out_resolution.addItems(list(RESOLUTIONS.keys()))
        self.out_resolution.setCurrentText("720p (1280x720)")
        f.addRow("Resolusi:", self.out_resolution)
        self.out_fps = QSpinBox()
        self.out_fps.setRange(15, 60)
        self.out_fps.setValue(24)
        f.addRow("FPS:", self.out_fps)
        self.out_preset = QComboBox()
        self.out_preset.addItems([
            "ultrafast", "superfast", "veryfast", "faster", "fast",
            "medium", "slow", "slower",
        ])
        self.out_preset.setCurrentText("veryfast")
        f.addRow("Preset Encoder (cepat .. detail):", self.out_preset)
        self.out_crf = QSpinBox()
        self.out_crf.setRange(15, 32)
        self.out_crf.setValue(22)
        f.addRow("CRF (15 = sangat bagus, 28 = file kecil):", self.out_crf)
        self.out_path = QLineEdit("output/render/output.mp4")
        b = QPushButton("Pilih...")
        b.clicked.connect(self._pick_output_path)
        f.addRow("File Output:", _row(self.out_path, b))
        self.tabs.addTab(w, "Output")

    # ------------------------------------------------------------ Batch tab
    def _build_tab_batch(self):
        w = QWidget()
        f = QFormLayout(w)
        self.batch_music = QLineEdit()
        b1 = QPushButton("Pilih...")
        b1.clicked.connect(lambda: self._pick_dir(self.batch_music))
        f.addRow("Folder Musik:", _row(self.batch_music, b1))
        self.batch_lyric = QLineEdit()
        b2 = QPushButton("Pilih...")
        b2.clicked.connect(lambda: self._pick_dir(self.batch_lyric))
        f.addRow("Folder Lirik (.lrc):", _row(self.batch_lyric, b2))
        self.batch_bg = QLineEdit()
        b3 = QPushButton("Pilih...")
        b3.clicked.connect(lambda: self._pick_dir(self.batch_bg))
        f.addRow("Folder Background:", _row(self.batch_bg, b3))

        self.batch_strategy = QComboBox()
        self.batch_strategy.addItems(["Order", "Match by Name", "Random"])
        f.addRow("Strategi Background:", self.batch_strategy)
        self.batch_multi = QComboBox()
        self.batch_multi.addItems(["Single", "Multi"])
        f.addRow("Mode (Order / Random):", self.batch_multi)
        self.batch_outdir = QLineEdit("output/render/batch")
        b4 = QPushButton("Pilih...")
        b4.clicked.connect(lambda: self._pick_dir(self.batch_outdir))
        f.addRow("Folder Output:", _row(self.batch_outdir, b4))

        self.batch_preview = QPushButton("Pratinjau Pasangan File")
        self.batch_preview.clicked.connect(self._preview_batch)
        self.batch_start = QPushButton("Mulai Batch Render")
        self.batch_start.setObjectName("primary")
        self.batch_start.clicked.connect(self._start_batch)
        h = QHBoxLayout()
        h.addWidget(self.batch_preview)
        h.addWidget(self.batch_start)
        f.addRow(h)
        self.batch_log = QPlainTextEdit()
        self.batch_log.setReadOnly(True)
        self.batch_log.setMaximumHeight(220)
        f.addRow(self.batch_log)
        self.tabs.addTab(w, "Batch")

    # ------------------------------------------------------------------ Pickers
    def _pick_file(self, line: QLineEdit, filt: str):
        p, _ = QFileDialog.getOpenFileName(self, "Pilih file", "", filt)
        if p:
            line.setText(p)

    def _pick_dir(self, line: QLineEdit):
        p = QFileDialog.getExistingDirectory(self, "Pilih folder")
        if p:
            line.setText(p)

    def _add_backgrounds(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Pilih gambar / video",
            "", "Media (*.png *.jpg *.jpeg *.bmp *.webp *.mp4 *.mov *.mkv *.webm)")
        for p in paths:
            if p not in self.bg_files:
                self.bg_files.append(p)
                self.bg_list.addItem(p)

    def _clear_backgrounds(self):
        self.bg_files.clear()
        self.bg_list.clear()

    def _pick_output_path(self):
        p, _ = QFileDialog.getSaveFileName(self, "Simpan output sebagai",
                                            self.out_path.text(), "MP4 (*.mp4)")
        if p:
            if not p.lower().endswith(".mp4"):
                p += ".mp4"
            self.out_path.setText(p)

    # ----------------------------------------------------------- FFmpeg status
    def _refresh_ffmpeg_status(self):
        ok, msg = ffmpeg_utils.status()
        if ok:
            self.ff_status.setText("FFmpeg: <b style='color:#1f8c5e'>Terpasang</b>")
            self.ff_install_btn.setEnabled(False)
        else:
            self.ff_status.setText("FFmpeg: <b style='color:#c0322a'>Belum terpasang</b>")
            self.ff_install_btn.setEnabled(True)
        self.statusBar().showMessage(msg.splitlines()[0])

    def _install_ffmpeg(self):
        self.ff_install_btn.setEnabled(False)
        self.statusBar().showMessage("Mengunduh FFmpeg...")
        self.install_thread = QThread()
        self.install_worker = InstallWorker()
        self.install_worker.moveToThread(self.install_thread)
        self.install_worker.progress.connect(self._on_install_progress)
        self.install_worker.finished.connect(self._on_install_done)
        self.install_thread.started.connect(self.install_worker.run)
        self.install_thread.start()

    @Slot(str, float)
    def _on_install_progress(self, msg: str, ratio: float):
        self.statusBar().showMessage(msg)
        if ratio >= 0:
            self.progress_bar.setValue(int(ratio * 100))

    @Slot(bool, str)
    def _on_install_done(self, ok: bool, msg: str):
        self.install_thread.quit()
        self.install_thread.wait(2000)
        if ok:
            QMessageBox.information(self, "FFmpeg",
                                     f"FFmpeg terpasang.\n{msg}")
        else:
            QMessageBox.critical(self, "FFmpeg", f"Gagal: {msg}")
        self._refresh_ffmpeg_status()
        self.progress_bar.setValue(0)

    # --------------------------------------------------------------- Config build
    def _build_render_config(self) -> Optional[RenderConfig]:
        audio = self.audio_input.text().strip()
        if not audio or not Path(audio).exists():
            QMessageBox.warning(self, "Audio", "Pilih file musik dulu.")
            return None
        cfg = RenderConfig(audio_input=audio)
        cfg.lyrics_input = self.lyric_input.text().strip() or None
        cfg.output_path = self.out_path.text().strip() or "output/render/output.mp4"
        cfg.resolution = self.out_resolution.currentText()
        cfg.fps = self.out_fps.value()
        cfg.encoder_preset = self.out_preset.currentText()
        cfg.crf = self.out_crf.value()

        cfg.spectrum = SpectrumConfig(
            style=self.spec_style.currentText(),
            palette=self.spec_palette.currentText(),
            height_ratio=self.spec_height.value() / 100.0,
            bottom_offset=self.spec_bottom.value() / 100.0,
            density=self.spec_density.value() / 100.0,
            opacity=self.spec_opacity.value() / 100.0,
            glow=self.spec_glow.value() / 100.0,
            mirror=self.spec_mirror.isChecked(),
        )
        cfg.background = BackgroundConfig(
            files=list(self.bg_files),
            multi_mode=("Multi" if self.bg_multi_enabled.isChecked() and len(self.bg_files) > 1 else "Single"),
            multi_strategy=self.bg_multi_strategy.currentText(),
            blur=self.bg_blur.value() / 100.0,
            darken=self.bg_darken.value() / 100.0,
            zoom_pulse=self.bg_zoom.isChecked(),
        )
        cfg.logo = LogoConfig(
            path=self.logo_path.text().strip() or None,
            enabled=self.logo_enabled.isChecked(),
            circular=self.logo_circular.isChecked(),
            position=self.logo_position.currentText(),
            size_pct=self.logo_size.value() / 100.0,
            opacity=self.logo_opacity.value() / 100.0,
            border=self.logo_border.isChecked(),
            shadow=self.logo_shadow.isChecked(),
        )
        cfg.effect_name = self.fx_name.currentText()
        cfg.effect_intensity = self.fx_intensity.value() / 100.0
        cfg.effect_color = self.fx_color._color
        cfg.lyric = LyricStyle(
            font_family=self.lyric_font.currentText(),
            font_size_pct=self.lyric_size.value() / 1000.0,
            color=self.lyric_color._color,
            outline_color=self.lyric_outline_color._color,
            outline_width=self.lyric_outline_width.value(),
            bold_box=self.lyric_box.isChecked(),
            position_pct=self.lyric_position.value() / 100.0,
            uppercase=self.lyric_uppercase.isChecked(),
        )
        cfg.lyric_offset_ms = self.lyric_offset.value()
        return cfg

    # --------------------------------------------------------------- Render
    def _start_render(self):
        cfg = self._build_render_config()
        if cfg is None:
            return
        if not ffmpeg_utils.ffmpeg_path():
            QMessageBox.warning(self, "FFmpeg", "FFmpeg belum terpasang. Klik 'Install FFmpeg'.")
            return
        self.btn_render.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress_bar.setValue(0)
        self.render_thread = QThread()
        self.render_worker = RenderWorker(cfg)
        self.render_worker.moveToThread(self.render_thread)
        self.render_worker.progress.connect(self._on_render_progress)
        self.render_worker.finished.connect(self._on_render_done)
        self.render_thread.started.connect(self.render_worker.run)
        self.render_thread.start()

    def _cancel_render(self):
        if self.render_worker:
            self.render_worker.cancel()
        if self.batch_worker:
            self.batch_worker.cancel()

    @Slot(float, str)
    def _on_render_progress(self, ratio: float, msg: str):
        self.progress_bar.setValue(int(ratio * 100))
        self.statusBar().showMessage(msg)

    @Slot(bool, str)
    def _on_render_done(self, ok: bool, path: str):
        self.render_thread.quit()
        self.render_thread.wait(2000)
        self.btn_render.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        if ok:
            self.progress_bar.setValue(100)
            self.statusBar().showMessage(f"Selesai: {path}")
            self._play_file(path)
        else:
            QMessageBox.warning(self, "Render", f"Render gagal: {path}")

    # ---------------------------------------------------------------- Preview
    def _preview_frame(self):
        cfg = self._build_render_config()
        if cfg is None:
            return
        t = self.preview_time.value()
        self.statusBar().showMessage("Membuat preview...")
        QApplication.processEvents()
        try:
            from .preview_widget import render_preview_frame
            img = render_preview_frame(cfg, t)
            self.preview.set_image(img)
            self.statusBar().showMessage(f"Preview frame @ {t:.1f}s siap.")
        except Exception as exc:
            self.statusBar().showMessage(f"Gagal preview: {exc}")
            QMessageBox.warning(self, "Preview", str(exc))

    def _play_last_output(self):
        out = self.out_path.text().strip()
        if out and Path(out).exists():
            self._play_file(out)
        else:
            QMessageBox.information(self, "Preview", "File output belum ada.")

    def _play_file(self, path: str):
        self.player.setSource(QUrl.fromLocalFile(path))
        self.player.play()

    def _open_output_folder(self):
        out = Path(self.out_path.text().strip()).parent
        out.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(out)))

    # ---------------------------------------------------------------- Batch
    def _make_batch_cfg(self) -> Optional[BatchConfig]:
        m = self.batch_music.text().strip()
        if not m or not Path(m).is_dir():
            QMessageBox.warning(self, "Batch", "Pilih folder musik dulu.")
            return None
        base = self._build_render_config()
        if base is None:
            return None
        return BatchConfig(
            music_folder=m,
            lyrics_folder=self.batch_lyric.text().strip() or None,
            bg_folder=self.batch_bg.text().strip() or None,
            bg_strategy=self.batch_strategy.currentText(),
            bg_multi_mode=self.batch_multi.currentText(),
            output_folder=self.batch_outdir.text().strip() or "output/render/batch",
            base_render=base,
        )

    def _preview_batch(self):
        cfg = self._make_batch_cfg()
        if cfg is None:
            return
        pairs = list_batch_pairs(cfg)
        self.batch_log.clear()
        for i, p in enumerate(pairs):
            self.batch_log.appendPlainText(
                f"{i+1:02d}. {Path(p['audio']).name}\n"
                f"      Lirik   : {Path(p['lyric']).name if p['lyric'] else '(tidak ada)'}\n"
                f"      BG ({len(p['background'])}): "
                + (", ".join(Path(b).name for b in p['background']) or '(default)')
            )

    def _start_batch(self):
        cfg = self._make_batch_cfg()
        if cfg is None:
            return
        if not ffmpeg_utils.ffmpeg_path():
            QMessageBox.warning(self, "FFmpeg", "FFmpeg belum terpasang.")
            return
        self.btn_render.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.batch_log.clear()
        self.batch_thread = QThread()
        self.batch_worker = BatchWorker(cfg)
        self.batch_worker.moveToThread(self.batch_thread)
        self.batch_worker.progress.connect(self._on_batch_progress)
        self.batch_worker.finished.connect(self._on_batch_done)
        self.batch_thread.started.connect(self.batch_worker.run)
        self.batch_thread.start()

    @Slot(int, int, float, str)
    def _on_batch_progress(self, i: int, total: int, ratio: float, msg: str):
        overall = (i + ratio) / max(1, total)
        self.progress_bar.setValue(int(overall * 100))
        self.statusBar().showMessage(f"[{i+1}/{total}] {msg}")

    @Slot(list)
    def _on_batch_done(self, results: list):
        self.batch_thread.quit()
        self.batch_thread.wait(2000)
        self.btn_render.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        ok = sum(1 for r in results if r["ok"])
        fail = len(results) - ok
        self.batch_log.appendPlainText(
            f"\nSelesai. Berhasil {ok}, gagal {fail}, total {len(results)}.")
        for r in results:
            mark = "OK " if r["ok"] else "FAIL"
            self.batch_log.appendPlainText(f"  [{mark}] {Path(r['audio']).name} -> {r['output']}")

    # ---------------------------------------------------------------- Log
    @Slot(str, str)
    def _on_log(self, level: str, msg: str):
        # Logger is called from worker threads; route through invoker.
        QTimer.singleShot(0, lambda: self._append_log(level, msg))

    def _append_log(self, level: str, msg: str):
        self.log_view.appendPlainText(f"[{level}] {msg}")


# ---------------------------------------------------------------------------
# Layout helpers
# ---------------------------------------------------------------------------

def _row(*widgets) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    for wd in widgets:
        lay.addWidget(wd)
    return w


def _slider(low: int, high: int, val: int) -> QSlider:
    s = QSlider(Qt.Orientation.Horizontal)
    s.setRange(low, high)
    s.setValue(val)
    s.setTickPosition(QSlider.TickPosition.TicksBelow)
    s.setTickInterval(max(1, (high - low) // 10))
    s.setMinimumWidth(180)
    return s
