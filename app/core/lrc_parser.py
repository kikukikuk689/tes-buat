"""Parser for `.lrc` lyric files with timestamps.

Supports standard tags like:
    [mm:ss.xx]LYRIC TEXT
    [mm:ss]LYRIC TEXT
    [mm:ss.xxx]LYRIC TEXT
    [offset:+/-ms]  (applied as a global shift to all timestamps)

Also tolerates ID tags ([ti:], [ar:], etc.) by ignoring them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


TIME_RE = re.compile(r"\[(\d{1,2}):(\d{1,2})(?:\.(\d{1,3}))?\]")
META_RE = re.compile(r"\[(\w{2,}):([^\]]*)\]")


@dataclass
class LyricLine:
    start: float          # seconds
    end: float            # seconds (set during finalization)
    text: str


def _parse_seconds(m, h, *_) -> float:  # pragma: no cover
    return 0


def parse_lrc(path: str, offset_ms: int = 0) -> List[LyricLine]:
    """Parse an .lrc file and return time-sorted lyric events.

    ``offset_ms`` is added to every timestamp (negative = lyrics earlier).
    """
    p = Path(path)
    if not p.exists():
        return []
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    lines: List[LyricLine] = []
    file_offset = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        # Look for [offset: +-ms] meta tag
        if line.lower().startswith("[offset:"):
            try:
                file_offset = int(line.split(":", 1)[1].rstrip("]").strip())
            except ValueError:
                pass
            continue
        # Skip ID3-style meta tags (ti, ar, al, by, length, etc.)
        if META_RE.match(line) and not TIME_RE.match(line):
            continue

        # Find all timestamps at beginning of the line
        matches = list(TIME_RE.finditer(line))
        if not matches:
            continue
        # Text starts after last timestamp
        last_match = matches[-1]
        text_part = line[last_match.end():].strip()
        for m in matches:
            mm = int(m.group(1))
            ss = int(m.group(2))
            frac = m.group(3) or "0"
            # Normalize to seconds; LRC fractional part is hundredths if 2
            # digits and milliseconds if 3 digits.
            if len(frac) == 1:
                frac_val = int(frac) / 10
            elif len(frac) == 2:
                frac_val = int(frac) / 100
            else:
                frac_val = int(frac) / 1000
            t = mm * 60 + ss + frac_val
            t += (offset_ms + file_offset) / 1000.0
            t = max(0.0, t)
            if text_part:
                lines.append(LyricLine(start=t, end=t, text=text_part))

    # Sort and assign end times so each line lives until the next one starts.
    lines.sort(key=lambda l: l.start)
    for i in range(len(lines)):
        if i + 1 < len(lines):
            lines[i].end = max(lines[i].start + 0.5, lines[i + 1].start)
        else:
            lines[i].end = lines[i].start + 6.0
    return lines


def lyric_at(lines: List[LyricLine], t: float, lead_in: float = 0.0,
             linger: float = 0.0) -> Optional[LyricLine]:
    """Find the lyric line active at time ``t`` (in seconds).

    ``lead_in`` lets you reveal the next line slightly before its timestamp.
    ``linger`` keeps the previous line visible for that many extra seconds.
    Returns ``None`` if no line should be visible at ``t`` -- importantly,
    this means before the first timestamp, no lyric appears (as the user
    requested).
    """
    if not lines:
        return None
    for line in lines:
        start = line.start - lead_in
        end = line.end + linger
        if start <= t < end:
            return line
    return None
