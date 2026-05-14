"""
Left-side control panel.

Hosts the tabbed editor: Background, Texts, Logo, Overlay, Split.
Each tab edits the project state and triggers preview refresh.
"""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from verticlip.core.fonts import list_families
from verticlip.core.project import (
    BackgroundMode,
    LogoMotion,
    OverlayKey,
    Project,
    TextItem,
)


# Cache so we don't rescan fonts every keystroke.
_FAMILY_CACHE: Optional[list[str]] = None


def _families() -> list[str]:
    global _FAMILY_CACHE
    if _FAMILY_CACHE is None:
        _FAMILY_CACHE = list_families()
    return _FAMILY_CACHE


def _color_button(initial: str, on_change: Callable[[str], None]) -> QPushButton:
    btn = QPushButton()
    btn.setFixedWidth(36)
    btn.setFixedHeight(24)

    def _apply(color: str) -> None:
        btn.setStyleSheet(
            f"QPushButton {{ background: {color}; border: 1px solid #555; border-radius: 4px; }}"
        )

    def _clicked() -> None:
        dlg = QColorDialog(QColor(btn._color), btn)
        dlg.setOption(QColorDialog.DontUseNativeDialog, False)
        if dlg.exec() == QColorDialog.Accepted:
            c = dlg.selectedColor()
            if c.isValid():
                hexc = c.name()
                btn._color = hexc
                _apply(hexc)
                on_change(hexc)

    btn._color = initial
    _apply(initial)
    btn.clicked.connect(_clicked)
    return btn


class _BackgroundTab(QWidget):
    def __init__(self, project: Project, refresh_cb: Callable[[], None]) -> None:
        super().__init__()
        self.project = project
        self.refresh = refresh_cb

        layout = QVBoxLayout(self)

        src_group = QGroupBox("Video Sumber")
        src_layout = QHBoxLayout(src_group)
        self.src_edit = QLineEdit(project.source_video or "")
        self.src_edit.setReadOnly(True)
        src_browse = QPushButton("Pilih video ...")
        src_browse.clicked.connect(self._pick_source)
        src_layout.addWidget(self.src_edit, 1)
        src_layout.addWidget(src_browse)
        layout.addWidget(src_group)

        bg_group = QGroupBox("Mode Background (9:16)")
        bg_layout = QFormLayout(bg_group)
        self.bg_combo = QComboBox()
        self.bg_combo.addItem("Fit + Blur BG (proporsional, background blur)", BackgroundMode.FIT_BLUR)
        self.bg_combo.addItem("Fit + Black BG (proporsional, background hitam)", BackgroundMode.FIT_BLACK)
        self.bg_combo.addItem("Fill + Crop (video memenuhi, tepi terpotong)", BackgroundMode.FILL_CROP)
        self.bg_combo.addItem("Fit + Custom (background dari gambar/video)", BackgroundMode.FIT_CUSTOM)
        idx = self.bg_combo.findData(project.background_mode)
        if idx >= 0:
            self.bg_combo.setCurrentIndex(idx)
        self.bg_combo.currentIndexChanged.connect(self._mode_changed)
        bg_layout.addRow("Mode:", self.bg_combo)

        self.custom_row = QWidget()
        cr = QHBoxLayout(self.custom_row)
        cr.setContentsMargins(0, 0, 0, 0)
        self.custom_edit = QLineEdit(project.custom_bg_path or "")
        self.custom_edit.setReadOnly(True)
        custom_btn = QPushButton("Pilih background ...")
        custom_btn.clicked.connect(self._pick_custom)
        cr.addWidget(self.custom_edit, 1)
        cr.addWidget(custom_btn)
        bg_layout.addRow("Custom file:", self.custom_row)
        self._update_custom_visibility()

        layout.addWidget(bg_group)
        layout.addStretch(1)

    def _mode_changed(self) -> None:
        self.project.background_mode = self.bg_combo.currentData()
        self._update_custom_visibility()
        self.refresh()

    def _update_custom_visibility(self) -> None:
        self.custom_row.setEnabled(self.project.background_mode == BackgroundMode.FIT_CUSTOM)

    def _pick_source(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Pilih video sumber", "",
            "Video (*.mp4 *.mov *.mkv *.webm *.avi);;Semua file (*)",
        )
        if path:
            self.project.source_video = path
            self.src_edit.setText(path)
            self.refresh()

    def _pick_custom(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Pilih background custom", "",
            "Gambar/Video (*.jpg *.jpeg *.png *.bmp *.webp *.mp4 *.mov *.mkv *.webm)",
        )
        if path:
            self.project.custom_bg_path = path
            self.custom_edit.setText(path)
            self.refresh()


class _TextItemEditor(QWidget):
    """Editor for a single TextItem; emits a change callback to refresh preview."""

    changed = Signal()

    def __init__(self, item: TextItem) -> None:
        super().__init__()
        self.item = item
        layout = QFormLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self.text_edit = QLineEdit(item.text)
        self.text_edit.textChanged.connect(self._text_changed)
        layout.addRow("Teks:", self.text_edit)

        self.font_combo = QComboBox()
        self.font_combo.setEditable(True)
        families = _families()
        if families:
            self.font_combo.addItems(families)
        if item.font_family:
            self.font_combo.setCurrentText(item.font_family)
        self.font_combo.currentTextChanged.connect(self._font_changed)
        layout.addRow("Font:", self.font_combo)

        self.size_spin = QSpinBox()
        self.size_spin.setRange(10, 400)
        self.size_spin.setValue(item.font_size)
        self.size_spin.valueChanged.connect(self._size_changed)
        layout.addRow("Ukuran:", self.size_spin)

        color_row = QWidget()
        cr = QHBoxLayout(color_row)
        cr.setContentsMargins(0, 0, 0, 0)
        cr.addWidget(QLabel("Warna:"))
        self.color_btn = _color_button(item.color, self._color_changed)
        cr.addWidget(self.color_btn)
        cr.addWidget(QLabel("Outline:"))
        self.stroke_color_btn = _color_button(item.stroke_color, self._stroke_color_changed)
        cr.addWidget(self.stroke_color_btn)
        cr.addStretch(1)
        layout.addRow(color_row)

        self.stroke_spin = QSpinBox()
        self.stroke_spin.setRange(0, 30)
        self.stroke_spin.setValue(item.stroke_width)
        self.stroke_spin.valueChanged.connect(self._stroke_changed)
        layout.addRow("Tebal outline:", self.stroke_spin)

        pos_row = QWidget()
        pr = QHBoxLayout(pos_row)
        pr.setContentsMargins(0, 0, 0, 0)
        pr.addWidget(QLabel("X:"))
        self.x_spin = QDoubleSpinBox()
        self.x_spin.setRange(0.0, 1.0)
        self.x_spin.setSingleStep(0.01)
        self.x_spin.setDecimals(4)
        self.x_spin.setValue(item.x)
        self.x_spin.valueChanged.connect(self._x_changed)
        pr.addWidget(self.x_spin)
        pr.addWidget(QLabel("Y:"))
        self.y_spin = QDoubleSpinBox()
        self.y_spin.setRange(0.0, 1.0)
        self.y_spin.setSingleStep(0.01)
        self.y_spin.setDecimals(4)
        self.y_spin.setValue(item.y)
        self.y_spin.valueChanged.connect(self._y_changed)
        pr.addWidget(self.y_spin)
        pr.addStretch(1)
        layout.addRow("Posisi (norm):", pos_row)

        anchor_row = QWidget()
        ar = QHBoxLayout(anchor_row)
        ar.setContentsMargins(0, 0, 0, 0)
        for label, x, y in (
            ("Atas", 0.5, 0.1), ("Tengah", 0.5, 0.5), ("Bawah", 0.5, 0.9),
            ("Kiri", 0.12, 0.5), ("Kanan", 0.88, 0.5),
        ):
            btn = QPushButton(label)
            btn.clicked.connect(lambda _=False, x=x, y=y: self._set_anchor(x, y))
            ar.addWidget(btn)
        layout.addRow("Cepat:", anchor_row)

    def _text_changed(self, s: str) -> None:
        self.item.text = s
        self.changed.emit()

    def _font_changed(self, fam: str) -> None:
        self.item.font_family = fam
        self.changed.emit()

    def _size_changed(self, v: int) -> None:
        self.item.font_size = v
        self.changed.emit()

    def _color_changed(self, c: str) -> None:
        self.item.color = c
        self.changed.emit()

    def _stroke_color_changed(self, c: str) -> None:
        self.item.stroke_color = c
        self.changed.emit()

    def _stroke_changed(self, v: int) -> None:
        self.item.stroke_width = v
        self.changed.emit()

    def _x_changed(self, v: float) -> None:
        self.item.x = v
        self.changed.emit()

    def _y_changed(self, v: float) -> None:
        self.item.y = v
        self.changed.emit()

    def _set_anchor(self, x: float, y: float) -> None:
        self.item.x, self.item.y = x, y
        self.x_spin.setValue(x)
        self.y_spin.setValue(y)
        self.changed.emit()

    def sync_from_model(self) -> None:
        # called after drag
        self.x_spin.blockSignals(True)
        self.y_spin.blockSignals(True)
        self.x_spin.setValue(self.item.x)
        self.y_spin.setValue(self.item.y)
        self.x_spin.blockSignals(False)
        self.y_spin.blockSignals(False)


class _TextsTab(QWidget):
    selectionChanged = Signal(str, int)
    refreshRequested = Signal()

    def __init__(self, project: Project) -> None:
        super().__init__()
        self.project = project
        self._editors: dict[int, _TextItemEditor] = {}
        layout = QHBoxLayout(self)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._row_changed)
        left_layout.addWidget(self.list, 1)
        btn_row = QHBoxLayout()
        add_btn = QPushButton("+ Tambah Teks")
        add_btn.clicked.connect(self._add)
        del_btn = QPushButton("Hapus")
        del_btn.clicked.connect(self._remove)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(del_btn)
        left_layout.addLayout(btn_row)
        layout.addWidget(left, 1)

        self.editor_holder = QWidget()
        self.editor_layout = QVBoxLayout(self.editor_holder)
        self.editor_layout.setContentsMargins(0, 0, 0, 0)
        self.editor_layout.addStretch(1)
        layout.addWidget(self.editor_holder, 2)

        # Initial render
        for _ in project.texts:
            self._append_list_item()

    def _refresh_list_labels(self) -> None:
        self.list.clear()
        for i, t in enumerate(self.project.texts):
            self.list.addItem(QListWidgetItem(f"{i + 1}. {t.text or '(kosong)'}"))

    def _append_list_item(self) -> None:
        i = len(self.project.texts) - 1
        item = self.project.texts[i]
        self.list.addItem(QListWidgetItem(f"{i + 1}. {item.text or '(kosong)'}"))

    def _add(self) -> None:
        item = TextItem()
        self.project.texts.append(item)
        self._refresh_list_labels()
        self.list.setCurrentRow(len(self.project.texts) - 1)
        self.refreshRequested.emit()

    def _remove(self) -> None:
        row = self.list.currentRow()
        if row < 0 or row >= len(self.project.texts):
            return
        self.project.texts.pop(row)
        self._editors.pop(row, None)
        # rebuild editors mapping (indices shift)
        self._editors = {}
        self._refresh_list_labels()
        if self.project.texts:
            self.list.setCurrentRow(min(row, len(self.project.texts) - 1))
        else:
            self._clear_editor()
        self.refreshRequested.emit()

    def _row_changed(self, row: int) -> None:
        self._clear_editor()
        if row < 0 or row >= len(self.project.texts):
            self.selectionChanged.emit("", -1)
            return
        item = self.project.texts[row]
        editor = self._editors.get(row)
        if editor is None:
            editor = _TextItemEditor(item)
            editor.changed.connect(self._editor_changed)
            self._editors[row] = editor
        self.editor_layout.insertWidget(0, editor)
        self.selectionChanged.emit("text", row)

    def _clear_editor(self) -> None:
        while self.editor_layout.count() > 1:
            w = self.editor_layout.takeAt(0).widget()
            if w is not None:
                w.setParent(None)

    def _editor_changed(self) -> None:
        row = self.list.currentRow()
        if row >= 0:
            it = self.project.texts[row]
            self.list.item(row).setText(f"{row + 1}. {it.text or '(kosong)'}")
        self.refreshRequested.emit()

    def sync_current_position(self) -> None:
        row = self.list.currentRow()
        editor = self._editors.get(row)
        if editor:
            editor.sync_from_model()


class _PartTab(QWidget):
    selectionChanged = Signal(str, int)
    refreshRequested = Signal()

    def __init__(self, project: Project) -> None:
        super().__init__()
        self.project = project
        layout = QFormLayout(self)

        self.split_check = QCheckBox("Aktifkan auto-split (potong per detik)")
        self.split_check.setChecked(project.split.enabled)
        self.split_check.toggled.connect(self._split_toggled)
        layout.addRow(self.split_check)

        self.seconds_spin = QSpinBox()
        self.seconds_spin.setRange(5, 3600)
        self.seconds_spin.setValue(project.split.seconds_per_clip)
        self.seconds_spin.valueChanged.connect(self._seconds_changed)
        layout.addRow("Durasi per clip (detik):", self.seconds_spin)

        layout.addRow(QLabel(""))

        self.part_check = QCheckBox("Tambahkan teks Part/Clip otomatis di tiap potongan")
        self.part_check.setChecked(project.part_text.enabled)
        self.part_check.toggled.connect(self._part_toggled)
        layout.addRow(self.part_check)

        self.part_label = QLineEdit(project.part_text.label)
        self.part_label.textChanged.connect(self._label_changed)
        layout.addRow("Kata (Part/Clip):", self.part_label)

        self.part_start = QSpinBox()
        self.part_start.setRange(0, 9999)
        self.part_start.setValue(project.part_text.start_index)
        self.part_start.valueChanged.connect(self._start_changed)
        layout.addRow("Mulai dari angka:", self.part_start)

        self.part_font = QComboBox()
        self.part_font.setEditable(True)
        families = _families()
        if families:
            self.part_font.addItems(families)
        self.part_font.setCurrentText(project.part_text.font_family)
        self.part_font.currentTextChanged.connect(self._font_changed)
        layout.addRow("Font:", self.part_font)

        self.part_size = QSpinBox()
        self.part_size.setRange(10, 400)
        self.part_size.setValue(project.part_text.font_size)
        self.part_size.valueChanged.connect(self._size_changed)
        layout.addRow("Ukuran:", self.part_size)

        cr = QWidget()
        crl = QHBoxLayout(cr)
        crl.setContentsMargins(0, 0, 0, 0)
        crl.addWidget(QLabel("Warna:"))
        self.color_btn = _color_button(project.part_text.color, self._color_changed)
        crl.addWidget(self.color_btn)
        crl.addWidget(QLabel("Outline:"))
        self.stroke_btn = _color_button(project.part_text.stroke_color, self._stroke_color_changed)
        crl.addWidget(self.stroke_btn)
        self.stroke_spin = QSpinBox()
        self.stroke_spin.setRange(0, 30)
        self.stroke_spin.setValue(project.part_text.stroke_width)
        self.stroke_spin.valueChanged.connect(self._stroke_changed)
        crl.addWidget(QLabel("Tebal:"))
        crl.addWidget(self.stroke_spin)
        crl.addStretch(1)
        layout.addRow(cr)

        pos_row = QWidget()
        pr = QHBoxLayout(pos_row)
        pr.setContentsMargins(0, 0, 0, 0)
        pr.addWidget(QLabel("X:"))
        self.x_spin = QDoubleSpinBox()
        self.x_spin.setRange(0.0, 1.0)
        self.x_spin.setSingleStep(0.01)
        self.x_spin.setDecimals(4)
        self.x_spin.setValue(project.part_text.x)
        self.x_spin.valueChanged.connect(self._x_changed)
        pr.addWidget(self.x_spin)
        pr.addWidget(QLabel("Y:"))
        self.y_spin = QDoubleSpinBox()
        self.y_spin.setRange(0.0, 1.0)
        self.y_spin.setSingleStep(0.01)
        self.y_spin.setDecimals(4)
        self.y_spin.setValue(project.part_text.y)
        self.y_spin.valueChanged.connect(self._y_changed)
        pr.addWidget(self.y_spin)
        pr.addStretch(1)
        layout.addRow("Posisi (norm):", pos_row)

        self.preview_index = QSpinBox()
        self.preview_index.setRange(1, 9999)
        self.preview_index.setValue(project.part_text.start_index)
        self.preview_index.setToolTip("Hanya untuk preview - tidak mempengaruhi hasil render.")
        layout.addRow("Preview Part #:", self.preview_index)
        self.preview_index.valueChanged.connect(self._preview_part_changed)

    # callbacks
    def _split_toggled(self, on: bool) -> None:
        self.project.split.enabled = on
        self.refreshRequested.emit()

    def _seconds_changed(self, v: int) -> None:
        self.project.split.seconds_per_clip = v
        self.refreshRequested.emit()

    def _part_toggled(self, on: bool) -> None:
        self.project.part_text.enabled = on
        self.refreshRequested.emit()
        if on:
            self.selectionChanged.emit("part", -1)

    def _label_changed(self, s: str) -> None:
        self.project.part_text.label = s
        self.refreshRequested.emit()

    def _start_changed(self, v: int) -> None:
        self.project.part_text.start_index = v
        self.preview_index.setValue(v)
        self.refreshRequested.emit()

    def _font_changed(self, fam: str) -> None:
        self.project.part_text.font_family = fam
        self.refreshRequested.emit()

    def _size_changed(self, v: int) -> None:
        self.project.part_text.font_size = v
        self.refreshRequested.emit()

    def _color_changed(self, c: str) -> None:
        self.project.part_text.color = c
        self.refreshRequested.emit()

    def _stroke_color_changed(self, c: str) -> None:
        self.project.part_text.stroke_color = c
        self.refreshRequested.emit()

    def _stroke_changed(self, v: int) -> None:
        self.project.part_text.stroke_width = v
        self.refreshRequested.emit()

    def _x_changed(self, v: float) -> None:
        self.project.part_text.x = v
        self.refreshRequested.emit()

    def _y_changed(self, v: float) -> None:
        self.project.part_text.y = v
        self.refreshRequested.emit()

    def _preview_part_changed(self, v: int) -> None:
        # exposed via property; main window will pick it up
        self._preview_idx = v
        self.refreshRequested.emit()

    @property
    def preview_part_index(self) -> int:
        return self.preview_index.value()

    def sync_from_model(self) -> None:
        self.x_spin.blockSignals(True)
        self.y_spin.blockSignals(True)
        self.x_spin.setValue(self.project.part_text.x)
        self.y_spin.setValue(self.project.part_text.y)
        self.x_spin.blockSignals(False)
        self.y_spin.blockSignals(False)


class _LogoTab(QWidget):
    selectionChanged = Signal(str, int)
    refreshRequested = Signal()

    def __init__(self, project: Project) -> None:
        super().__init__()
        self.project = project
        layout = QFormLayout(self)

        pr = QHBoxLayout()
        self.path_edit = QLineEdit(project.logo.path or "")
        self.path_edit.setReadOnly(True)
        btn = QPushButton("Pilih logo ...")
        btn.clicked.connect(self._pick)
        clr = QPushButton("X")
        clr.setFixedWidth(28)
        clr.clicked.connect(self._clear)
        pr.addWidget(self.path_edit, 1)
        pr.addWidget(btn)
        pr.addWidget(clr)
        wrap = QWidget()
        wrap.setLayout(pr)
        layout.addRow("File logo (PNG transparan disarankan):", wrap)

        self.size_spin = QDoubleSpinBox()
        self.size_spin.setRange(0.02, 0.8)
        self.size_spin.setSingleStep(0.01)
        self.size_spin.setDecimals(3)
        self.size_spin.setValue(project.logo.size)
        self.size_spin.valueChanged.connect(self._size_changed)
        layout.addRow("Ukuran (lebar relatif):", self.size_spin)

        self.opacity_spin = QDoubleSpinBox()
        self.opacity_spin.setRange(0.0, 1.0)
        self.opacity_spin.setSingleStep(0.05)
        self.opacity_spin.setDecimals(2)
        self.opacity_spin.setValue(project.logo.opacity)
        self.opacity_spin.valueChanged.connect(self._opacity_changed)
        layout.addRow("Opacity:", self.opacity_spin)

        pos = QWidget()
        prl = QHBoxLayout(pos)
        prl.setContentsMargins(0, 0, 0, 0)
        prl.addWidget(QLabel("X:"))
        self.x_spin = QDoubleSpinBox()
        self.x_spin.setRange(0.0, 1.0)
        self.x_spin.setSingleStep(0.01)
        self.x_spin.setDecimals(4)
        self.x_spin.setValue(project.logo.x)
        self.x_spin.valueChanged.connect(self._x_changed)
        prl.addWidget(self.x_spin)
        prl.addWidget(QLabel("Y:"))
        self.y_spin = QDoubleSpinBox()
        self.y_spin.setRange(0.0, 1.0)
        self.y_spin.setSingleStep(0.01)
        self.y_spin.setDecimals(4)
        self.y_spin.setValue(project.logo.y)
        self.y_spin.valueChanged.connect(self._y_changed)
        prl.addWidget(self.y_spin)
        prl.addStretch(1)
        layout.addRow("Posisi (norm):", pos)

        self.motion_combo = QComboBox()
        self.motion_combo.addItem("Diam (tidak bergerak)", LogoMotion.NONE)
        self.motion_combo.addItem("Bergerak seperti angka 0 (lingkaran)", LogoMotion.CIRCLE)
        self.motion_combo.addItem("Bergerak seperti angka 8 (figure-8)", LogoMotion.FIGURE8)
        self.motion_combo.addItem("Memantul (bouncing)", LogoMotion.BOUNCE)
        idx = self.motion_combo.findData(project.logo.motion)
        if idx >= 0:
            self.motion_combo.setCurrentIndex(idx)
        self.motion_combo.currentIndexChanged.connect(self._motion_changed)
        layout.addRow("Gerakan:", self.motion_combo)

        self.amp_spin = QDoubleSpinBox()
        self.amp_spin.setRange(0.0, 0.5)
        self.amp_spin.setDecimals(3)
        self.amp_spin.setSingleStep(0.005)
        self.amp_spin.setValue(project.logo.motion_amplitude)
        self.amp_spin.valueChanged.connect(self._amp_changed)
        layout.addRow("Amplitudo:", self.amp_spin)

        self.period_spin = QDoubleSpinBox()
        self.period_spin.setRange(0.2, 60.0)
        self.period_spin.setDecimals(2)
        self.period_spin.setSingleStep(0.1)
        self.period_spin.setValue(project.logo.motion_period_s)
        self.period_spin.valueChanged.connect(self._period_changed)
        layout.addRow("Periode (detik / siklus):", self.period_spin)

    def _pick(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Pilih file logo", "",
            "Gambar (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if path:
            self.project.logo.path = path
            self.path_edit.setText(path)
            self.refreshRequested.emit()
            self.selectionChanged.emit("logo", -1)

    def _clear(self) -> None:
        self.project.logo.path = None
        self.path_edit.setText("")
        self.refreshRequested.emit()

    def _size_changed(self, v: float) -> None:
        self.project.logo.size = v
        self.refreshRequested.emit()

    def _opacity_changed(self, v: float) -> None:
        self.project.logo.opacity = v
        self.refreshRequested.emit()

    def _x_changed(self, v: float) -> None:
        self.project.logo.x = v
        self.refreshRequested.emit()

    def _y_changed(self, v: float) -> None:
        self.project.logo.y = v
        self.refreshRequested.emit()

    def _motion_changed(self) -> None:
        self.project.logo.motion = self.motion_combo.currentData()
        self.refreshRequested.emit()

    def _amp_changed(self, v: float) -> None:
        self.project.logo.motion_amplitude = v
        self.refreshRequested.emit()

    def _period_changed(self, v: float) -> None:
        self.project.logo.motion_period_s = v
        self.refreshRequested.emit()

    def sync_from_model(self) -> None:
        self.x_spin.blockSignals(True)
        self.y_spin.blockSignals(True)
        self.x_spin.setValue(self.project.logo.x)
        self.y_spin.setValue(self.project.logo.y)
        self.x_spin.blockSignals(False)
        self.y_spin.blockSignals(False)


class _OverlayTab(QWidget):
    refreshRequested = Signal()

    def __init__(self, project: Project) -> None:
        super().__init__()
        self.project = project
        layout = QFormLayout(self)

        pr = QHBoxLayout()
        self.path_edit = QLineEdit(project.overlay.path or "")
        self.path_edit.setReadOnly(True)
        btn = QPushButton("Pilih overlay ...")
        btn.clicked.connect(self._pick)
        clr = QPushButton("X")
        clr.setFixedWidth(28)
        clr.clicked.connect(self._clear)
        pr.addWidget(self.path_edit, 1)
        pr.addWidget(btn)
        pr.addWidget(clr)
        wrap = QWidget()
        wrap.setLayout(pr)
        layout.addRow("File overlay (greenscreen/blackscreen/whitescreen):", wrap)

        self.key_combo = QComboBox()
        self.key_combo.addItem("Auto (deteksi otomatis)", OverlayKey.AUTO)
        self.key_combo.addItem("Greenscreen", OverlayKey.GREEN)
        self.key_combo.addItem("Blackscreen", OverlayKey.BLACK)
        self.key_combo.addItem("Whitescreen", OverlayKey.WHITE)
        idx = self.key_combo.findData(project.overlay.key)
        if idx >= 0:
            self.key_combo.setCurrentIndex(idx)
        self.key_combo.currentIndexChanged.connect(self._key_changed)
        layout.addRow("Tipe keying:", self.key_combo)

        self.opacity_spin = QDoubleSpinBox()
        self.opacity_spin.setRange(0.0, 1.0)
        self.opacity_spin.setSingleStep(0.05)
        self.opacity_spin.setValue(project.overlay.opacity)
        self.opacity_spin.valueChanged.connect(self._opacity_changed)
        layout.addRow("Opacity:", self.opacity_spin)

        self.similarity_spin = QDoubleSpinBox()
        self.similarity_spin.setRange(0.01, 1.0)
        self.similarity_spin.setSingleStep(0.01)
        self.similarity_spin.setValue(project.overlay.similarity)
        self.similarity_spin.valueChanged.connect(self._sim_changed)
        layout.addRow("Similarity:", self.similarity_spin)

        self.blend_spin = QDoubleSpinBox()
        self.blend_spin.setRange(0.0, 1.0)
        self.blend_spin.setSingleStep(0.01)
        self.blend_spin.setValue(project.overlay.blend)
        self.blend_spin.valueChanged.connect(self._blend_changed)
        layout.addRow("Blend:", self.blend_spin)

    def _pick(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Pilih overlay", "",
            "Video/Gambar (*.mp4 *.mov *.mkv *.webm *.gif *.png *.jpg *.jpeg)",
        )
        if path:
            self.project.overlay.path = path
            self.path_edit.setText(path)
            self.refreshRequested.emit()

    def _clear(self) -> None:
        self.project.overlay.path = None
        self.path_edit.setText("")
        self.refreshRequested.emit()

    def _key_changed(self) -> None:
        self.project.overlay.key = self.key_combo.currentData()
        self.refreshRequested.emit()

    def _opacity_changed(self, v: float) -> None:
        self.project.overlay.opacity = v
        self.refreshRequested.emit()

    def _sim_changed(self, v: float) -> None:
        self.project.overlay.similarity = v
        self.refreshRequested.emit()

    def _blend_changed(self, v: float) -> None:
        self.project.overlay.blend = v
        self.refreshRequested.emit()


class ControlsPanel(QWidget):
    """Tabbed left panel."""

    refreshRequested = Signal()
    selectionChanged = Signal(str, int)

    def __init__(self, project: Project) -> None:
        super().__init__()
        self.project = project
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self.tabs = QTabWidget()
        self.bg_tab = _BackgroundTab(project, self.refreshRequested.emit)
        self.texts_tab = _TextsTab(project)
        self.part_tab = _PartTab(project)
        self.logo_tab = _LogoTab(project)
        self.overlay_tab = _OverlayTab(project)

        self.tabs.addTab(self.bg_tab, "Background")
        self.tabs.addTab(self.texts_tab, "Teks")
        self.tabs.addTab(self.part_tab, "Split / Part")
        self.tabs.addTab(self.logo_tab, "Logo")
        self.tabs.addTab(self.overlay_tab, "Overlay")

        layout.addWidget(self.tabs)

        # Wire child signals up to panel signals
        self.texts_tab.refreshRequested.connect(self.refreshRequested.emit)
        self.texts_tab.selectionChanged.connect(self.selectionChanged.emit)
        self.part_tab.refreshRequested.connect(self.refreshRequested.emit)
        self.part_tab.selectionChanged.connect(self.selectionChanged.emit)
        self.logo_tab.refreshRequested.connect(self.refreshRequested.emit)
        self.logo_tab.selectionChanged.connect(self.selectionChanged.emit)
        self.overlay_tab.refreshRequested.connect(self.refreshRequested.emit)

    def show_for_selection(self, kind: str, index: int) -> None:
        if kind == "text":
            self.tabs.setCurrentWidget(self.texts_tab)
            self.texts_tab.list.setCurrentRow(index)
        elif kind == "part":
            self.tabs.setCurrentWidget(self.part_tab)
        elif kind == "logo":
            self.tabs.setCurrentWidget(self.logo_tab)

    def sync_after_drag(self, kind: str, index: int) -> None:
        if kind == "text":
            self.texts_tab.sync_current_position()
        elif kind == "part":
            self.part_tab.sync_from_model()
        elif kind == "logo":
            self.logo_tab.sync_from_model()

    @property
    def preview_part_index(self) -> int:
        return self.part_tab.preview_part_index
