from __future__ import annotations

from pathlib import Path
from typing import Iterable

from dubby.schemas import Segment


def _ts(seconds: float, sep: str) -> str:
    ms = int(round(max(0.0, seconds) * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def write_srt(segments: Iterable[Segment], path: Path, field: str = "translation") -> Path:
    lines = []
    idx = 1
    for seg in segments:
        text = (getattr(seg, field) or "").strip()
        if not text:
            continue
        lines += [str(idx), f"{_ts(seg.start, ',')} --> {_ts(seg.end, ',')}", text, ""]
        idx += 1
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_vtt(segments: Iterable[Segment], path: Path, field: str = "translation") -> Path:
    lines = ["WEBVTT", ""]
    for seg in segments:
        text = (getattr(seg, field) or "").strip()
        if not text:
            continue
        lines += [f"{_ts(seg.start, '.')} --> {_ts(seg.end, '.')}", text, ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
