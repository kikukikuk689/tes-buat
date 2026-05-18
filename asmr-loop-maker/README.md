# ASMR Seamless Loop Maker

Aplikasi Python untuk mengubah video pendek (misalnya 8 detik) menjadi video ASMR
berdurasi panjang (1 jam, 3 jam, atau lebih). Aplikasi otomatis menganalisis frame
video dengan OpenCV untuk mencari titik potong terbaik agar loop terasa halus,
lalu menggabungkan loop tersebut dengan crossfade visual dan audio.

## Fitur

- Input satu video atau folder berisi banyak video (batch mode).
- Mendukung format `.mp4`, `.mov`, `.mkv`, `.avi`.
- Analisis frame dengan **OpenCV**:
  - Bandingkan frame dengan **grayscale difference** + **histogram color similarity**.
  - Cari pasangan `start_frame`/`end_frame` paling mirip dengan skor kemulusan.
- Render loop panjang dengan **crossfade alpha-blend** antar-loop.
- Audio diekstrak via **FFmpeg**, di-loop dengan **constant-power crossfade**
  menggunakan `soundfile` + `numpy`, lalu di-mux kembali ke video.
- Output akhir: **MP4 H.264 + AAC**, `+faststart`.
- Batch CSV report (`reports/batch_report_*.csv`).
- CLI lewat `argparse` dan UI sederhana lewat **Streamlit**.

## Struktur Folder

```text
asmr-loop-maker/
├── app/
│   ├── __init__.py
│   ├── analyzer.py      # OpenCV frame analysis & loop point search
│   ├── audio.py         # FFmpeg extract/mux + soundfile crossfade
│   ├── batch.py         # single + batch pipeline, CSV report
│   ├── cli.py           # argparse CLI
│   ├── config.py        # default values, supported extensions, folders
│   ├── renderer.py      # OpenCV VideoWriter + visual crossfade
│   ├── ui.py            # Streamlit UI
│   └── utils.py         # helpers (ensure_dir, run_command, ffmpeg check, …)
├── input/               # taruh video sumber di sini (batch mode)
├── output/              # hasil render disimpan di sini
├── reports/             # CSV report batch
├── scripts/
│   ├── setup.sh         # buat venv & install deps (macOS/Linux)
│   ├── setup.bat        # buat venv & install deps (Windows)
│   ├── run_cli.sh       # contoh batch dari input/ ke output/ (macOS/Linux)
│   ├── run_cli.bat      # versi Windows
│   ├── run_ui.sh        # jalankan Streamlit UI (macOS/Linux)
│   └── run_ui.bat       # versi Windows
├── main.py              # entry point untuk CLI
├── requirements.txt
└── README.md
```

## Instalasi

### Persyaratan Umum

- Python **3.10+**
- **FFmpeg** yang bisa dipanggil dari terminal (`ffmpeg -version` harus jalan).

### Windows

```bat
:: 1) Install Python 3.10+ dari https://www.python.org/downloads/ (centang "Add to PATH").
:: 2) Install FFmpeg, contoh via winget:
winget install --id=Gyan.FFmpeg -e
:: atau download dari https://www.gyan.dev/ffmpeg/builds/ dan tambahkan folder bin ke PATH.

:: 3) Setup project:
cd asmr-loop-maker
scripts\setup.bat
```

### macOS

```bash
# 1) Install FFmpeg via Homebrew
brew install ffmpeg

# 2) Setup project
cd asmr-loop-maker
bash scripts/setup.sh
```

### Linux (Debian/Ubuntu)

```bash
# 1) Install FFmpeg
sudo apt-get update && sudo apt-get install -y ffmpeg python3-venv

# 2) Setup project
cd asmr-loop-maker
bash scripts/setup.sh
```

Aktifkan virtualenv setelah setup:

```bash
# macOS/Linux
source .venv/bin/activate
```

```bat
:: Windows
call .venv\Scripts\activate.bat
```

## Menjalankan

### CLI — single video

```bash
python main.py --input input/video.mp4 --output output --hours 1 --crossfade 0.8
```

### CLI — batch folder

```bash
python main.py --input input/ --output output --hours 3 --crossfade 1.0 --batch
```

Argumen tambahan:

| Argumen          | Default      | Keterangan                                          |
|------------------|--------------|-----------------------------------------------------|
| `--min-loop`     | `2.0`        | Durasi minimum satu loop dalam detik.               |
| `--reports`      | `reports/`   | Folder tempat menyimpan CSV report batch.           |
| `--batch`        | otomatis     | Paksa mode batch (otomatis aktif jika input folder).|

Helper script siap pakai:

```bash
# macOS/Linux
bash scripts/run_cli.sh              # batch input/ -> output/, 1 jam, 0.8s
INPUT=input/clip.mp4 HOURS=3 bash scripts/run_cli.sh   # custom

# Windows
scripts\run_cli.bat
```

### UI Streamlit

```bash
bash scripts/run_ui.sh            # macOS/Linux
scripts\run_ui.bat                 # Windows
# atau langsung:
streamlit run app/ui.py
```

Browser akan otomatis terbuka di `http://localhost:8501`. Di UI kamu bisa:

- pilih mode **Single video** (upload) atau **Batch folder** (path),
- atur durasi output (jam), crossfade (detik), minimum loop (detik),
- lihat hasil analisis loop (`start_sec`, `end_sec`, `score`, dll.),
- preview hasil video jika ukuran file masih wajar.

### Contoh command lengkap

```bash
# Single video, 1 jam, crossfade 0.8 detik
python main.py -i input/rain_8s.mp4 -o output --hours 1 --crossfade 0.8

# Batch folder, 6 jam, crossfade 1.2 detik, minimum loop 3 detik
python main.py -i input/ -o output --hours 6 --crossfade 1.2 --min-loop 3 --batch
```

## Troubleshooting FFmpeg

Jika kamu melihat pesan:

> `FFmpeg belum terinstall. Install FFmpeg dan pastikan bisa dipanggil dari terminal.`

artinya `ffmpeg` belum ada di `PATH`. Solusi:

- **Windows:** `winget install Gyan.FFmpeg` lalu **buka ulang Command Prompt**.
  Verifikasi dengan `ffmpeg -version`.
- **macOS:** `brew install ffmpeg`.
- **Ubuntu/Debian:** `sudo apt-get install -y ffmpeg`.
- **Linux lain:** install via package manager distro (`dnf`, `pacman`, …) atau
  build statis dari https://johnvansickle.com/ffmpeg/.

Jalankan ulang aplikasi setelah `ffmpeg -version` dan `ffprobe -version` berjalan.

## Tips agar Loop ASMR Lebih Halus

1. **Pilih sumber yang sudah stabil.** Hindari clip dengan zoom, pan, atau
   perubahan pencahayaan tajam — analyzer mencocokkan kemiripan visual,
   jadi semakin stabil framing-nya, semakin halus loop-nya.
2. **Sediakan minimal 5–10 detik footage.** Window pencarian start/end butuh
   ruang gerak; clip yang terlalu pendek membatasi pilihan kandidat.
3. **Perbesar `--crossfade`** untuk sumber dengan tekstur tinggi (hujan, api).
   Coba `1.0–1.5` detik. Untuk objek diam dengan suara halus, `0.5–0.8` detik
   biasanya cukup.
4. **Naikkan `--min-loop`** kalau loop terasa terlalu cepat berulang. Nilai
   `4–8` detik membuat hasil lebih natural.
5. **Pastikan audio sudah bersih.** Crossfade audio menyamarkan klik di titik
   sambung, tapi noise/clipping di sumber tetap terdengar berulang. Bersihkan
   audio sumber jika perlu.
6. **Cek `score`** di output CLI/UI. Nilai mendekati `0.0` artinya frame
   start/end sangat mirip → loop sangat halus. Score `> 0.1` biasanya masih
   terlihat sambungannya; pertimbangkan crossfade yang lebih panjang.

## Lisensi

Kode di repository ini didistribusikan apa adanya untuk keperluan internal
kikukikuk689. Sesuaikan jika kamu ingin menggunakan ulang.
