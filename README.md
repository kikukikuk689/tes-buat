# ASMR Broadcast Studio

A **production-ready** desktop application for 24/7 ASMR multi-channel live
streaming.  Built on PySide6, FFmpeg, SQLAlchemy and FastAPI — designed to be
enterprise-grade, modular, scalable and immediately usable for nonstop
broadcasting.

![themes](docs/banner.svg)

## Highlights

- **Unlimited channels** — each with its own playlist, encoder profile, RTMP
  destination and schedule.  Stream simultaneously to YouTube, Twitch,
  Facebook Live, TikTok RTMP or any custom endpoint.
- **Full FFmpeg pipeline** — per-channel subprocess supervised by a
  watchdog with auto-reconnect, exponential backoff and dropped-frame
  detection.
- **Hardware acceleration auto-detect** — NVENC, QSV, AMF, VideoToolbox
  and VAAPI are surfaced automatically; fall back to `libx264` if none.
- **Modern PySide6 UI** — 15 dedicated pages, frameless window,
  cyberpunk / midnight / purple-neon themes, sparkline charts, toast
  notifications.
- **Realtime monitoring** — psutil-based CPU/RAM/GPU/network sampling at
  configurable intervals; published over an event bus to UI, web
  dashboard and watchdog.
- **Watchdog + scheduler** — APScheduler-driven start/stop schedules
  (cron or one-shot) plus an in-process watchdog that restarts stale
  streams.
- **YouTube API integration** — real OAuth (`google-auth-oauthlib`),
  live broadcast / stream creation, title/description/thumbnail
  management, viewer statistics polling.
- **AI assistance** — title / description / hashtag generation, thumbnail
  prompt suggestion, encoder optimisation.  Drop in an OpenAI-compatible
  API key to power it; otherwise the app uses deterministic templates so
  every button stays functional.
- **Remote web dashboard** — FastAPI + WebSocket API for LAN / mobile
  control.  Optional bearer token authentication.
- **Encrypted credentials** — Fernet-based vault for stream keys,
  API tokens and YouTube OAuth state.
- **License system** — HMAC-signed offline license files, device
  binding, configurable trial, optional online activation endpoint.
- **Auto-backup + restore** — scheduled snapshots of the database,
  config and license file; import / export of YAML config.
- **System tray** — start/stop everything from the tray, persistent
  background operation, native OS notifications.
- **Build pipeline** — one-click Nuitka build producing an optimised
  EXE with embedded resources.

## Project layout

```
.
├── app/
│   ├── core/         # config, logging, paths, events, exceptions
│   ├── db/           # SQLAlchemy models + repositories
│   ├── security/     # Fernet crypto, credentials vault, license manager
│   ├── services/     # FFmpeg manager, stream engine, watchdog, scheduler,
│   │                  # monitor, network probe, remote control, YouTube,
│   │                  # AI, backup, notifications, tray
│   ├── ui/           # PySide6 widgets and the 15 pages
│   └── utils/        # ffprobe, platform detection, time helpers
├── assets/           # icons, QSS themes, sounds
├── config/           # default.yaml template
├── web/              # static + templates for the remote dashboard
├── build/            # Nuitka build script
├── main.py           # entry point
├── requirements.txt
└── pyproject.toml
```

## Getting started

### 1. Install Python 3.12+

The project targets the Python 3.12 syntax level.  Earlier 3.10/3.11 versions
should work as long as PySide6 wheels are available for them, but 3.12+ is
recommended.

### 2. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate          # PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Linux desktops need a working Qt platform plugin (`libxcb`, `libegl`,
`libxkbcommon`, etc.).  On Ubuntu:

```bash
sudo apt install libxcb-cursor0 libxcb-xinerama0 libxkbcommon-x11-0 \
                 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 \
                 libxcb-render-util0 libxcb-shape0 libxcb-sync1 libxcb-xfixes0
```

### 3. Launch

```bash
python main.py
```

On first run the app creates its data directory:

* Linux: `~/.local/share/ASMRBroadcastStudio/`
* macOS: `~/Library/Application Support/ASMRBroadcastStudio/`
* Windows: `%APPDATA%\ASMRBroadcastStudio\`

If FFmpeg is not on `PATH`, open **FFmpeg Manager** and click *Install
FFmpeg* — the app downloads the official static build from
[gyan.dev](https://www.gyan.dev/ffmpeg/builds/) /
[johnvansickle.com](https://johnvansickle.com/ffmpeg/) /
[evermeet.cx](https://evermeet.cx/ffmpeg/), extracts it into the data
directory and verifies the binary automatically.

### 4. Configure a channel

1. Navigate to **Multi Channel Manager** and add a channel.
2. Paste the RTMP URL + stream key (the key is stored encrypted).
3. Pick or create a playlist in **Playlist Manager** and assign it to
   the channel.
4. Optionally configure a schedule in **Scheduler**.
5. Go to **Live Manager** and press **Start**.

### 5. Remote dashboard (optional)

Enable the embedded web dashboard in **Remote Control**:

* Tick *Enable remote control* and click *Start server*.
* Open `http://<your-LAN-IP>:<port>` from a phone or other PC.
* If you set a token, append `?token=<token>` to the URL.

### 6. YouTube integration (optional)

Provide your `client_secret.json` in **API Manager** and click
*Authorize via browser*.  The OAuth callback is handled by Google's
local-loopback flow — credentials are stored in
`youtube_token.json` inside the data directory.

### 7. AI features (optional)

Tick *Enable AI features* and supply an OpenAI-compatible API key
(stored encrypted via the credential vault).  Buttons on the encoder
and (in the channel dialog) channel pages use the AI service when
available, and gracefully fall back to high-quality templates when
not.

## Build a redistributable EXE

```bash
pip install nuitka
python build/build_exe.py            # release build
python build/build_exe.py --debug    # keep console + symbols
```

The resulting `dist/main.dist/` directory contains the app and bundled
resources; on Windows a single-file `dist/ASMRBroadcastStudio.exe` is
produced.

## Architecture notes

The application is deliberately layered:

* **core** — pure-Python infrastructure (config, logging, events).
* **db** — SQLAlchemy ORM behind a repository facade so the rest of the
  app never sees ORM sessions.
* **services** — long-lived background components that publish on the
  event bus (`app.core.events`).  Each is a small singleton accessible
  via `get_*()` helpers.
* **ui** — pure Qt code; subscribes to the event bus and uses
  `QTimer.singleShot(0, …)` to marshal handlers back to the GUI thread.
* **security** — crypto + credentials + licensing kept separate so they
  can evolve independently of the rest of the app.

## License

This source ships under the MIT license.  See `LICENSE` if present, or
treat the `LICENSE` header in the build script as the authoritative
notice.  The license manager included in the app is an *application-level*
license system intended to gate paid distributions — it has nothing to
do with the OSS license of this code.
