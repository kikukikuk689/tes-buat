"""Global encoder defaults + GPU optimisation suggestions."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
)

from ...core.config import get_config
from ...services import get_ai, get_ffmpeg_manager, get_notifier
from ...utils.platform_utils import detect_gpu, system_summary
from ..widgets import Card, MetricCard
from .base_page import BasePage


class EncoderPage(BasePage):
    title = "Encoder Settings"
    subtitle = "Global encoder defaults + GPU acceleration"

    PRESETS = ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow"]
    HW = ["auto", "none", "nvenc", "qsv", "amf", "videotoolbox", "vaapi"]
    CODECS = ["libx264", "libx265", "h264_nvenc", "h264_qsv", "h264_amf", "h264_videotoolbox"]

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        cfg = get_config().config.streaming
        gpu = detect_gpu()
        sys_info = system_summary()

        # Hardware info
        info_row = QHBoxLayout()
        self.gpu_card = MetricCard("GPU", ", ".join(gpu.names) or "Not detected", "primary GPU(s)")
        self.os_card = MetricCard("Operating system", f"{sys_info['system']} {sys_info['release']}", sys_info['machine'])
        self.encoder_card = MetricCard(
            "Recommended encoder", gpu.best_encoder.upper(), "auto-selected if hw_accel = auto"
        )
        for c in (self.gpu_card, self.os_card, self.encoder_card):
            info_row.addWidget(c)
        self.content_layout.addLayout(info_row)

        form_card = Card("Default encoder settings", glow=True)
        form = QFormLayout()
        form.setContentsMargins(0, 10, 0, 0)
        self.resolution = QComboBox()
        self.resolution.addItems(["1280x720", "1920x1080", "2560x1440", "3840x2160"])
        self.resolution.setCurrentText(cfg.resolution)
        self.fps = QSpinBox()
        self.fps.setRange(15, 60)
        self.fps.setValue(cfg.fps)
        self.v_bitrate = QSpinBox()
        self.v_bitrate.setRange(500, 50000)
        self.v_bitrate.setValue(cfg.video_bitrate_kbps)
        self.v_bitrate.setSuffix(" kbps")
        self.a_bitrate = QSpinBox()
        self.a_bitrate.setRange(64, 512)
        self.a_bitrate.setValue(cfg.audio_bitrate_kbps)
        self.a_bitrate.setSuffix(" kbps")
        self.preset = QComboBox()
        self.preset.addItems(self.PRESETS)
        self.preset.setCurrentText(cfg.preset)
        self.codec = QComboBox()
        self.codec.addItems(self.CODECS)
        self.codec.setCurrentText(cfg.video_codec)
        self.hw = QComboBox()
        self.hw.addItems(self.HW)
        self.hw.setCurrentText(cfg.hw_accel)
        self.gop = QSpinBox()
        self.gop.setRange(1, 10)
        self.gop.setValue(cfg.keyframe_interval_sec)
        self.gop.setSuffix(" s keyframe")
        self.normalize = QCheckBox("Apply loudnorm")
        self.normalize.setChecked(cfg.normalize_audio)

        form.addRow("Resolution", self.resolution)
        form.addRow("FPS", self.fps)
        form.addRow("Video bitrate", self.v_bitrate)
        form.addRow("Audio bitrate", self.a_bitrate)
        form.addRow("Preset", self.preset)
        form.addRow("Codec", self.codec)
        form.addRow("HW acceleration", self.hw)
        form.addRow("Keyframe interval", self.gop)
        form.addRow(self.normalize)
        form_card.content_layout.addLayout(form)

        save_row = QHBoxLayout()
        self.save_btn = QPushButton("Save defaults")
        self.save_btn.setObjectName("primary")
        self.optimize_btn = QPushButton("✨ Optimize for this PC")
        self.optimize_btn.setObjectName("ghost")
        save_row.addWidget(self.save_btn)
        save_row.addWidget(self.optimize_btn)
        save_row.addStretch()
        form_card.content_layout.addLayout(save_row)
        self.content_layout.addWidget(form_card)

        self.suggestion = QLabel("Click 'Optimize for this PC' to receive AI-tuned settings.")
        self.suggestion.setStyleSheet("color: #8A8AAE;")
        self.suggestion.setWordWrap(True)
        self.content_layout.addWidget(self.suggestion)

        self.save_btn.clicked.connect(self._save)
        self.optimize_btn.clicked.connect(self._optimize)

    def _save(self) -> None:
        get_config().update(
            streaming={
                "resolution": self.resolution.currentText(),
                "fps": int(self.fps.value()),
                "video_bitrate_kbps": int(self.v_bitrate.value()),
                "audio_bitrate_kbps": int(self.a_bitrate.value()),
                "preset": self.preset.currentText(),
                "video_codec": self.codec.currentText(),
                "hw_accel": self.hw.currentText(),
                "keyframe_interval_sec": int(self.gop.value()),
                "normalize_audio": self.normalize.isChecked(),
            }
        )
        get_notifier().notify("Encoder", "Defaults saved", "success")

    def _optimize(self) -> None:
        encoders = get_ffmpeg_manager().info.encoders
        suggestion = get_ai().optimize_encoder(
            target_bitrate_kbps=int(self.v_bitrate.value()),
            available_encoders=encoders,
        )
        self.codec.setCurrentText(suggestion["video_encoder"])
        self.preset.setCurrentText(suggestion["preset"])
        self.v_bitrate.setValue(int(suggestion["tuned_bitrate_kbps"]))
        self.suggestion.setText("AI suggestion: " + suggestion["rationale"])
