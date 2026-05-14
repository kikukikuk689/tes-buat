# VertiClip Studio

**Composer profesional untuk membuat video clip vertikal 9:16 (ukuran HP).**

Aplikasi desktop Python (PySide6 + FFmpeg) untuk membuat clip TikTok/Reels/Shorts
dengan: 4 mode background, multi-text drag presisi, auto-split per detik,
auto-numbering "Part/Clip", logo bergerak, dan overlay greenscreen/blackscreen/whitescreen.

---

## Fitur Utama

### 1. Mode Background (9:16)
- **Fit + Blur BG** – Video proporsional di tengah, sisi diisi versi blur dari video itu sendiri.
- **Fit + Black BG** – Video proporsional, sisi hitam.
- **Fill + Crop** – Video diperbesar memenuhi seluruh frame, tepi dipotong.
- **Fit + Custom** – Background diisi gambar atau video pilihan Anda. Background otomatis
  di-resize/crop menjadi 9:16 supaya menutup seluruh area.

### 2. Multi-Text dengan Drag Presisi
- Tombol **+ Tambah Teks** untuk menambah teks sebanyak yang dibutuhkan.
- Bisa drag langsung di preview, atau set posisi via input X/Y (normalized 0.0 – 1.0).
- **Drag → posisi presisi**: koordinat yang disimpan adalah koordinat normalisasi terhadap
  canvas output, sehingga apa yang Anda lihat di preview = posisi pasti di render akhir,
  bahkan saat resolusi output diganti.
- Banyak pilihan font (membaca font yang terinstall di OS), font dapat diganti dan **preview
  langsung berubah** real-time. Pilihan warna teks, outline, dan ketebalan outline.

### 3. Auto-Split per N Detik + Part/Clip Otomatis
- Checkbox **Aktifkan auto-split** + input *durasi per clip (detik)*.
- Setelah aktif, ada toggle optional **on/off** untuk teks "Part/Clip" otomatis.
- Saat aktif: video 1 dapat teks "Part 1", video 2 dapat "Part 2", dst. tanpa perlu edit lagi.
  Kata bisa diubah jadi "Clip", "Episode", dll.
- Posisi teks Part/Clip juga **drag-presisi** dengan koordinat normalisasi.

### 4. Logo + Animasi Gerakan
- Upload PNG/JPG untuk logo.
- Pilih posisi (drag presisi atau input X/Y) dan ukuran (relatif lebar).
- Gerakan opsional:
  - **Lingkaran** (seperti angka 0)
  - **Figure-8** (seperti angka 8)
  - **Memantul** (bouncing)
- Amplitudo & periode (detik per siklus) dapat diatur.

### 5. Overlay Greenscreen/Blackscreen/Whitescreen
- Tambahkan video efek di atas video utama tanpa menutupinya.
- Tipe keying: **Auto** (deteksi warna otomatis), Green, Black, White.
- Atur opacity, similarity, blend untuk hasil terbaik.

### 6. Layout Profesional
- Kanan: **Preview 9:16** real-time dengan drag interaktif.
- Kiri: tab kontrol (Background, Teks, Split/Part, Logo, Overlay).
- Bawah: **Render Settings** (resolusi, FPS, kualitas, folder output, prefix nama file).

### 7. Resolusi Output
- 720x1280 (HD), 1080x1920 (Full HD), **1440x2560 (2K)**.
- Custom folder output.
- Custom nama file (prefix). Saat split, file diberi suffix `_partXX`.

### 8. Status FFmpeg + Auto-Install
- Status bar atas menampilkan apakah FFmpeg terdeteksi.
- Jika belum: tombol **Install FFmpeg** untuk download otomatis (Windows). Linux/macOS
  diarahkan ke package manager.

---

## Cara Menggunakan (Windows)

1. **Install Python 3.10+** dari https://www.python.org/downloads/ (centang "Add Python to PATH").
2. Double-click **`setup.bat`** – ini akan:
   - Membuat virtual environment di folder `venv\`.
   - Install dependencies (PySide6, OpenCV, Pillow, NumPy, requests).
3. Double-click **`run.bat`** untuk membuka aplikasi.
4. Di aplikasi:
   - Klik tab **Background** → pilih video sumber.
   - Pilih mode background (Blur/Black/Crop/Custom).
   - (Opsional) Tambah teks di tab **Teks**, atur posisi via drag di preview.
   - (Opsional) Aktifkan **Split/Part** untuk membagi video per N detik dengan auto-numbering.
   - (Opsional) Upload logo dan pilih gerakan di tab **Logo**.
   - (Opsional) Upload overlay greenscreen/blackscreen/whitescreen di tab **Overlay**.
   - Atur **Render Settings** di bawah (resolusi, folder output).
   - Klik **RENDER VIDEO**.

## Linux / macOS

```bash
chmod +x setup.sh run.sh
./setup.sh   # buat venv & install deps
./run.sh     # jalankan aplikasi
```

Install FFmpeg via package manager:
- Linux: `sudo apt install ffmpeg` atau setara
- macOS: `brew install ffmpeg`

---

## Arsitektur Singkat

```
verticlip/
├── __main__.py                    # entry point: python -m verticlip
├── core/
│   ├── project.py                 # state model (normalized coords)
│   ├── ffmpeg_utils.py            # detect + online install + probe
│   ├── fonts.py                   # discover OS fonts
│   ├── chroma_key.py              # auto-detect green/black/white
│   ├── animation.py               # circle / figure-8 / bounce math
│   ├── preview_render.py          # OpenCV+Pillow preview compositor
│   └── render.py                  # FFmpeg filter graph builder
└── ui/
    ├── main_window.py
    ├── styles.py                  # dark theme
    ├── preview_canvas.py          # 9:16 drag-precise canvas
    ├── controls_panel.py          # tabbed editor
    ├── render_panel.py            # bottom render bar
    └── ffmpeg_status.py           # status pill + install button
```

**Drag presisi**: semua posisi (teks, Part text, logo) disimpan sebagai koordinat
ternormalisasi [0.0–1.0] terhadap output canvas. Preview maupun final render
menggunakan koordinat yang sama → tidak ada drift antara apa yang dilihat dan
apa yang dihasilkan.

---

## Lisensi

MIT.
