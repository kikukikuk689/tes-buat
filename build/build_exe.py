#!/usr/bin/env python3
"""One-click Nuitka build script.

Usage::

    python build/build_exe.py            # standard release build
    python build/build_exe.py --debug    # keep console window + debug info

Produces a single-folder distribution under ``dist/`` and (on Windows) a
single-file EXE under ``dist/ASMRBroadcastStudio.exe``.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true", help="Keep console + debug symbols")
    parser.add_argument("--no-onefile", action="store_true", help="Don't bundle into a single file")
    args = parser.parse_args()

    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)

    cmd = [
        sys.executable,
        "-m",
        "nuitka",
        "--standalone",
        "--enable-plugin=pyside6",
        "--plugin-enable=anti-bloat",
        "--include-package=app",
        "--include-package-data=app",
        "--include-package-data=assets",
        "--include-package-data=web",
        "--include-package-data=config",
        f"--output-dir={dist}",
        "--remove-output",
        "--assume-yes-for-downloads",
        "--lto=yes",
        "--company-name=ASMR Broadcast Studio",
        "--product-name=ASMR Broadcast Studio",
        "--product-version=1.0.0",
        "--file-description=Premium 24/7 ASMR broadcasting engine",
        "--copyright=© 2024 ASMR Broadcast Studio",
    ]
    if not args.debug:
        cmd.append("--windows-console-mode=disable")
        cmd.append("--no-progressbar")
    if not args.no_onefile:
        cmd.append("--onefile")
    icon = ROOT / "assets" / "icons" / "studio.ico"
    if icon.exists():
        cmd.append(f"--windows-icon-from-ico={icon}")
    cmd.append("main.py")

    env = os.environ.copy()
    env.setdefault("PYTHONOPTIMIZE", "1" if not args.debug else "0")

    print("→", " ".join(cmd))
    result = subprocess.run(cmd, cwd=str(ROOT), env=env)
    if result.returncode != 0:
        return result.returncode

    # Copy runtime resources next to the build for ease of zipping.
    runtime_dir = dist / "main.dist"
    if runtime_dir.exists():
        for resource in ("assets", "web", "config"):
            src = ROOT / resource
            dst = runtime_dir / resource
            if src.exists():
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
    print("Build complete:", dist)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
