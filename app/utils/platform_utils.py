"""Platform / GPU detection helpers."""
from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass


@dataclass
class GPUInfo:
    nvidia: bool
    amd: bool
    intel: bool
    apple_silicon: bool
    names: list[str]

    @property
    def best_encoder(self) -> str:
        """Pick the best hardware encoder for libx264-equivalent output."""
        if self.nvidia:
            return "nvenc"
        if self.apple_silicon:
            return "videotoolbox"
        if self.amd:
            return "amf"
        if self.intel:
            return "qsv"
        return "cpu"


def _safe_run(args: list[str]) -> str:
    try:
        return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL, timeout=10)
    except Exception:  # noqa: BLE001
        return ""


def detect_gpu() -> GPUInfo:
    """Detect the available GPU vendors on the current machine."""
    names: list[str] = []
    nvidia = bool(shutil.which("nvidia-smi"))
    if nvidia:
        out = _safe_run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"])
        names.extend(filter(None, (l.strip() for l in out.splitlines())))

    amd = False
    intel = False

    if sys.platform.startswith("linux"):
        lspci = _safe_run(["lspci"])
        for line in lspci.splitlines():
            line_low = line.lower()
            if "vga compatible controller" in line_low or "3d controller" in line_low:
                names.append(line.split(":", 2)[-1].strip())
                if "amd" in line_low or "advanced micro devices" in line_low:
                    amd = True
                if "intel" in line_low:
                    intel = True
                if "nvidia" in line_low:
                    nvidia = True

    elif sys.platform == "win32":
        out = _safe_run(["wmic", "path", "win32_VideoController", "get", "name"])
        for line in out.splitlines()[1:]:
            line = line.strip()
            if not line:
                continue
            names.append(line)
            low = line.lower()
            if "nvidia" in low:
                nvidia = True
            if "amd" in low or "radeon" in low:
                amd = True
            if "intel" in low:
                intel = True

    apple_silicon = sys.platform == "darwin" and platform.machine().lower() in {"arm64", "aarch64"}

    return GPUInfo(nvidia=nvidia, amd=amd, intel=intel, apple_silicon=apple_silicon, names=names)


def system_summary() -> dict:
    """Return a compact dictionary describing the current host."""
    return {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "processor": platform.processor() or "",
    }
