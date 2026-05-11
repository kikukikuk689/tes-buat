# MusicViz Studio

Aplikasi Python untuk membuat **video musik dengan spectrum visualizer, lirik tersinkronisasi, dan efek modern**. Dirancang ringan supaya tetap nyaman di PC/laptop kentang.

![spectrum demo](docs/preview.png)

## Fitur

- **15+ gaya spectrum** smooth & berwarna (bars, mirror, circular, particle, neon, galaxy, wave, dll). Pengaturan kepadatan/visibility supaya tidak terlalu penuh.
- **15 efek video** musical (kunang-kunang, kelap-kelip, bokeh, snow, stars, light rays, confetti, dust, glow pulse, rain, petals, hearts, notes, dll).
- **Lirik LRC** tersinkronisasi dengan timestamp — tidak muncul sebelum waktunya. Banyak pilihan font, warna, ukuran, stroke, shadow.
- **Background** image/video, single atau multi (slideshow + crossfade) dengan toggle on/off.
- **Logo** dengan opsi bulat (circular mask), pilihan posisi (9 anchor + offset) dan ukuran.
- **Batch mode**: pilih folder musik + folder lirik + folder background. 3 strategi pencocokan: urutan file, nama musik, random. Untuk strategi 1 & 3 ada opsi single/multi background.
- **Preview** frame realtime di UI + tombol play hasil render.
- **Pilih resolusi** render: 480p, 720p, 1080p, 1440p, 2160p, atau custom.
- **Render cepat** via FFmpeg pipe + multithreaded frame generation.
- **Status FFmpeg** terdeteksi otomatis + tombol install online jika belum tersedia.
- **Log panel** realtime untuk monitoring proses & error.
- **Tema light/auto** mengikuti sistem operasi.

## Instalasi (Windows)

1. Double-click `setup.bat` — script akan:
   - Cek instalasi Python (>=3.10)
   - Install dependency Python (`customtkinter`, `numpy`, `Pillow`)
   - Cek instalasi FFmpeg, kasih tahu kalau belum ada
2. Double-click `run.bat` untuk menjalankan aplikasi.

> Kalau FFmpeg belum terinstall, ada **tombol "Install FFmpeg Online"** di dalam aplikasi yang akan otomatis download & extract ke folder `tools/ffmpeg/`.

## Instalasi (Linux/Mac)

```bash
chmod +x setup.sh run.sh
./setup.sh
./run.sh
```

## Penggunaan

### Mode Single
1. Pilih file musik (mp3/wav/flac/m4a/ogg).
2. (Opsional) Pilih file LRC untuk lirik.
3. (Opsional) Pilih background — bisa 1 gambar, 1 video, atau multi (slideshow).
4. (Opsional) Pilih logo + posisi + ukuran + toggle bulat.
5. Pilih gaya spectrum + efek video + font lirik.
6. Pilih resolusi + framerate.
7. Klik **Render** — progress bar + log realtime.

### Mode Batch
1. Tab **Batch**.
2. Pilih folder musik.
3. Pilih folder lirik (opsional).
4. Pilih folder background (opsional) — set strategi:
   - **By file order**: dipasangkan sesuai urutan sort filename.
   - **By music name**: cari background dengan nama mirip nama musik.
   - **Random**: acak.
5. Untuk strategi *by order* dan *random*, pilih **Single** (1 background per video) atau **Multi** (slideshow multi-background per video).
6. Klik **Start Batch**.

## Struktur Project

```
.
├── main.py                  # Entry point
├── setup.bat / setup.sh
├── run.bat / run.sh
├── requirements.txt
├── src/
│   ├── app.py               # Main application controller
│   ├── ui/                  # CustomTkinter UI
│   ├── core/                # Renderer, audio, LRC, ffmpeg utils
│   ├── spectrum/            # 15+ spectrum styles
│   ├── effects/             # 15 video effects
│   ├── overlays/            # Logo & lyrics overlay
│   ├── batch/               # Batch processing
│   └── utils/               # Logger, fonts
└── assets/                  # Fonts, icons
```

## Tips Performa (PC kentang)

- Pilih resolusi **720p** atau lebih rendah.
- Set framerate **24 fps**.
- Kurangi `density` spectrum di panel Spectrum.
- Pilih efek "Soft Glow Pulse" atau "Bokeh" yang ringan; hindari "Fireflies" dengan particle count besar.
- Aktifkan **Hardware encoder** (NVENC/QSV/AMF) di pengaturan output kalau punya GPU.

## Lisensi

MIT.
