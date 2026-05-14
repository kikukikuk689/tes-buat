"""FFmpeg status indicator + Install button."""
from __future__ import annotations

import platform
from typing import Optional

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QWidget,
)

from verticlip.core.ffmpeg_utils import (
    FFmpegStatus,
    install_ffmpeg_online,
    probe_ffmpeg,
)


class _Installer(QObject):
    progress = Signal(int, int, str)
    finished = Signal(bool, str)

    def run(self) -> None:
        try:
            install_ffmpeg_online(progress=lambda d, t, m: self.progress.emit(d, t, m))
            self.finished.emit(True, "FFmpeg berhasil diinstall.")
        except Exception as exc:  # pragma: no cover - depends on network
            self.finished.emit(False, str(exc))


class FFmpegStatusWidget(QWidget):
    """Inline status: green if installed, red w/ install button if missing."""

    statusChanged = Signal(object)  # FFmpegStatus

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.icon = QLabel()
        self.label = QLabel()
        self.label.setObjectName("statusBad")
        self.install_btn = QPushButton("Install FFmpeg")
        self.install_btn.clicked.connect(self._install_clicked)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh)
        layout.addWidget(self.icon)
        layout.addWidget(self.label, 1)
        layout.addWidget(self.refresh_btn)
        layout.addWidget(self.install_btn)
        self._status: FFmpegStatus = FFmpegStatus(False, None, None, "missing")
        self._thread: Optional[QThread] = None
        self._installer: Optional[_Installer] = None
        self.refresh()

    def status(self) -> FFmpegStatus:
        return self._status

    def refresh(self) -> None:
        st = probe_ffmpeg()
        self._status = st
        if st.available:
            label = "FFmpeg terdeteksi"
            if st.version:
                label += f"  ({st.version})"
            if st.source == "bundled":
                label += "  [bundled]"
            self.label.setText(label)
            self.label.setObjectName("statusOk")
            self.install_btn.setEnabled(False)
            self.install_btn.setText("Sudah terinstall")
        else:
            self.label.setText("FFmpeg belum terinstall - render dinonaktifkan")
            self.label.setObjectName("statusBad")
            self.install_btn.setEnabled(True)
            self.install_btn.setText("Install FFmpeg")
        # force style recompute
        self.label.style().unpolish(self.label)
        self.label.style().polish(self.label)
        self.statusChanged.emit(st)

    def _install_clicked(self) -> None:
        system = platform.system()
        if system != "Windows":
            QMessageBox.information(
                self,
                "Install FFmpeg",
                "Auto-install hanya untuk Windows.\n\n"
                "Linux : sudo apt install ffmpeg\n"
                "macOS : brew install ffmpeg",
            )
            return

        dlg = QProgressDialog("Mengunduh FFmpeg ...", "Batal", 0, 100, self)
        dlg.setWindowTitle("Install FFmpeg")
        dlg.setMinimumDuration(0)
        dlg.setAutoClose(False)
        dlg.setValue(0)

        self._thread = QThread(self)
        self._installer = _Installer()
        self._installer.moveToThread(self._thread)
        self._thread.started.connect(self._installer.run)

        def on_progress(done: int, total: int, msg: str) -> None:
            if total > 0:
                dlg.setMaximum(100)
                dlg.setValue(int(done * 100 / total))
            else:
                dlg.setMaximum(0)  # busy indicator
            dlg.setLabelText(msg)

        def on_finished(ok: bool, msg: str) -> None:
            dlg.close()
            if self._thread:
                self._thread.quit()
                self._thread.wait()
            if ok:
                QMessageBox.information(self, "FFmpeg", "Install selesai.\n" + msg)
            else:
                QMessageBox.critical(self, "Gagal install FFmpeg", msg)
            self.refresh()

        self._installer.progress.connect(on_progress)
        self._installer.finished.connect(on_finished)
        self._thread.start()
