# Music Spectrum Studio

Aplikasi Python modern untuk membuat video musik dengan spectrum
visualizer + lirik time-synced. Dirancang ringan untuk laptop/PC
spek minimal, dengan tampilan profesional dan banyak fitur.

## Fitur

- **18 gaya spectrum** (Bars, Mirror Bars, Rounded Bars, Glow Bars, 3D Bars,
  Wave, Mirror Wave, Neon Wave, Ribbon, Liquid, Dots, Particles, Fire,
  Circle Bars, Pulse Ring, Hexagon, Polygon, Galaxy) — smooth, berwarna,
  berkarakter, dan sejajar bagian bawah video.
- **15 efek video** spesial musik: Fireflies (kunang-kunang), Sparkles,
  Snow, Rain, Bokeh, Light Leak, Stars, Hearts, Bubbles, Confetti, Smoke,
  Neon Grid, Pulse Rings, Film Grain, Aurora.
- **Lirik time-synced** dari file `.lrc` — sebelum timestamp pertama, tidak
  ada lirik yang muncul. Banyak pilihan font yang otomatis terdeteksi dari
  sistem Anda + offset timestamp manual.
- **Logo overlay** dengan crop bulat opsional, pilih posisi (9 anchor),
  ukuran, opasitas, border & shadow.
- **Background fleksibel**: gambar atau video, single atau multi (Order /
  Random), dengan blur, dim, dan ken-burns zoom.
- **Batch render**: 1 folder musik + 1 folder lirik + 1 folder background.
  Strategi background: **Order** (sesuai urutan file), **Match by Name**
  (sesuai nama musik), atau **Random**. Untuk Order/Random, sub-opsi
  Single atau Multi.
- **Status FFmpeg** otomatis + tombol install online (static build).
- **Preview frame** + pemutar hasil render bawaan + **log live**
  (error & progress).
- **Pilih resolusi** 480p..2160p, vertikal 9:16, square 1:1, dst.
- **Encoder cepat** (libx264 dengan preset configurable).
- **Tema modern terang** atau mengikuti tema sistem.

## Struktur Project

```
music-spectrum-studio/
├── app/
│   ├── main.py                # entry point GUI
│   ├── core/                  # pipeline render
│   │   ├── audio_analyzer.py
│   │   ├── spectrum_styles.py
│   │   ├── effects.py
│   │   ├── lrc_parser.py
│   │   ├── logo_handler.py
│   │   ├── background_handler.py
│   │   ├── ffmpeg_utils.py
│   │   ├── renderer.py
│   │   └── batch_renderer.py
│   ├── gui/                   # PySide6 GUI
│   │   ├── main_window.py
│   │   ├── preview_widget.py
│   │   └── styles.py
│   └── utils/
│       ├── fonts.py
│       └── logger.py
├── assets/                    # ikon / template (kosong by default)
├── output/
│   ├── render/                # hasil render
│   └── logs/                  # log aplikasi
├── samples/                   # contoh untuk tes
├── scripts/
│   └── test_quick.py          # tes render cepat dari CLI
├── requirements.txt
├── setup.bat / setup.sh
└── run.bat   / run.sh
```

## Instalasi (Windows)

1. Jalankan `setup.bat` (dobel-klik atau dari Command Prompt).
   Script ini akan:
   - membuat virtual environment `.venv`,
   - menginstall semua dependensi Python,
   - memeriksa apakah `ffmpeg.exe` tersedia di PATH atau folder `bin\`.
2. Jalankan `run.bat` untuk membuka aplikasi.
3. Jika status FFmpeg di pojok kanan atas menyatakan "Belum terpasang",
   klik tombol **Install FFmpeg**: aplikasi akan mengunduh build statis
   dari gyan.dev langsung ke folder `bin/`.

## Instalasi (Linux / macOS)

```bash
./setup.sh
./run.sh
```

## Penggunaan Cepat

1. **Project** tab → pilih file musik (.mp3/.wav/.mp4/.flac/...),
   file lirik `.lrc`, dan satu atau lebih background (gambar/video).
2. **Spectrum** tab → pilih gaya & palet, atur tinggi area, kepadatan,
   opasitas, glow. Spectrum default selalu sejajar bagian bawah video.
3. **Efek** tab → pilih efek video & intensitas.
4. **Lirik** tab → pilih font, ukuran, warna, outline, posisi, offset ms.
5. **Logo** tab → pilih file, mode bulat, posisi & ukuran.
6. **Output** tab → resolusi, fps, preset encoder, CRF, path output.
7. Klik **Preview Frame** untuk lihat hasil pada waktu tertentu.
8. Klik **Render Sekarang** untuk render full video.
9. Pemutar bawaan akan otomatis memutar hasil rendernya.

## Batch

Tab **Batch**:
- Pilih *Folder Musik*, *Folder Lirik*, *Folder Background*.
- Pilih strategi background:
  - **Order** — pakai background sesuai urutan file (lagu 1 -> bg 1, dst).
    Sub-mode Single / Multi.
  - **Match by Name** — pasangkan background dengan musik yang punya nama
    serupa.
  - **Random** — pilih background acak per lagu. Sub-mode Single / Multi.
- Klik **Pratinjau Pasangan File** untuk lihat pasangan musik–lirik–bg
  sebelum render.
- Klik **Mulai Batch Render**.

## Tips Performa (PC Spek Minim)

- Pakai resolusi **720p** dan **fps 24**.
- Preset encoder **ultrafast / superfast** + **CRF 24-26**.
- Pakai background gambar diam (lebih cepat dari video).
- Matikan zoom pulse / efek berat (Confetti, Aurora) jika lemot.
- Tutup aplikasi lain saat render.

## Format Lirik

LRC standar:

```
[00:19.20]MALAM INI SUNYI LAGI
[00:24.50]ANGIN BERBISIK PELAN SEKALI
```

Sebelum timestamp pertama (`00:19.20`) tidak ada teks yang muncul.

## License

MIT.
