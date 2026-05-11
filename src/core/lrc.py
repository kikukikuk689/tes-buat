"""LRC parser dengan dukungan multi-timestamp per baris."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

# [00:19.20] or [00:19.200] or [00:19] or [1:23:45.67]
_TS_RE = re.compile(r"\[(\d{1,2}):(\d{2})(?:\.(\d{1,3}))?]")
_META_RE = re.compile(r"\[(ti|ar|al|au|by|offset|length|re|ve):([^\]]*)]", re.IGNORECASE)


@dataclass(frozen=True)
class LyricLine:
    start: float           # detik
    end: float             # detik (start baris berikutnya)
    text: str


@dataclass
class LRC:
    lines: List[LyricLine] = field(default_factory=list)
    offset: float = 0.0
    title: str = ""
    artist: str = ""

    @property
    def first_start(self) -> float:
        return self.lines[0].start if self.lines else float("inf")

    def line_at(self, t: float) -> Optional[LyricLine]:
        # Linear scan adequate for typical lyric counts (<= a few hundred).
        for ln in self.lines:
            if ln.start <= t < ln.end:
                return ln
        return None

    def upcoming(self, t: float) -> Optional[LyricLine]:
        """Baris berikutnya setelah t (untuk preview baris berikutnya)."""
        for ln in self.lines:
            if ln.start > t:
                return ln
        return None


def _to_seconds(m: int, s: int, ms: Optional[str]) -> float:
    frac = 0.0
    if ms:
        # zero-pad to 3 digits then divide
        ms_padded = (ms + "000")[:3]
        frac = int(ms_padded) / 1000.0
    return m * 60 + s + frac


def parse_lrc(path: str | Path | None = None, text: str | None = None) -> LRC:
    """Parse file LRC atau string mentah."""
    if path is not None:
        path = Path(path)
        try:
            raw = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raw = path.read_text(encoding="latin-1")
    elif text is not None:
        raw = text
    else:
        return LRC()

    offset = 0.0
    title = ""
    artist = ""

    entries: list[tuple[float, str]] = []

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue

        meta = _META_RE.match(line)
        if meta:
            tag, val = meta.group(1).lower(), meta.group(2).strip()
            if tag == "ti":
                title = val
            elif tag == "ar":
                artist = val
            elif tag == "offset":
                try:
                    offset = -int(val) / 1000.0
                except ValueError:
                    offset = 0.0
            continue

        timestamps = [_to_seconds(int(g[0]), int(g[1]), g[2]) for g in _TS_RE.findall(line)]
        if not timestamps:
            continue
        content = _TS_RE.sub("", line).strip()
        for t in timestamps:
            entries.append((t + offset, content))

    entries.sort(key=lambda e: e[0])
    lines: list[LyricLine] = []
    for i, (t, txt) in enumerate(entries):
        end = entries[i + 1][0] if i + 1 < len(entries) else t + 6.0
        # Buang baris kosong (instrumental marker) tapi tetap akhir baris sebelumnya
        if not txt:
            continue
        lines.append(LyricLine(start=t, end=end, text=txt))

    # Buang celah panjang antar lirik: clamp end di end + 2x rata-rata kalau gap besar
    return LRC(lines=lines, offset=offset, title=title, artist=artist)


def parse_lrc_text(text: str) -> LRC:
    return parse_lrc(text=text)


def split_long_line(line: LyricLine, max_chars: int = 38) -> Sequence[str]:
    """Wrap teks lirik supaya tidak terlalu lebar."""
    if len(line.text) <= max_chars:
        return [line.text]
    words = line.text.split()
    out: list[str] = []
    cur = ""
    for w in words:
        if not cur:
            cur = w
        elif len(cur) + 1 + len(w) <= max_chars:
            cur = cur + " " + w
        else:
            out.append(cur)
            cur = w
    if cur:
        out.append(cur)
    return out


def all_text(lyrics: Iterable[LyricLine]) -> str:
    return "\n".join(ln.text for ln in lyrics)
