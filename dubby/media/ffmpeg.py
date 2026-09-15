"""Thin, explicit ffmpeg wrappers."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Sequence, Tuple


class FFmpegError(RuntimeError):
    pass


def binary(name: str = "ffmpeg") -> str:
    path = shutil.which(name)
    if not path:
        raise FFmpegError(f"{name} not found on PATH. Install ffmpeg (conda install -c conda-forge ffmpeg).")
    return path


def run(args: Sequence[str]) -> str:
    proc = subprocess.run([binary(), "-hide_banner", "-loglevel", "error", "-y", *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise FFmpegError(proc.stderr.strip()[-1500:] or f"ffmpeg failed with code {proc.returncode}")
    return proc.stdout


def probe(path: Path | str) -> dict:
    proc = subprocess.run(
        [binary("ffprobe"), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        raise FFmpegError(proc.stderr.strip()[-800:])
    return json.loads(proc.stdout)


def duration(path: Path | str) -> float:
    return float(probe(path)["format"].get("duration", 0.0))


def video_codec(path: Path | str) -> Optional[str]:
    for s in probe(path).get("streams", []):
        if s.get("codec_type") == "video":
            return s.get("codec_name")
    return None


def extract_audio(video: Path | str, out: Path | str, sample_rate: int, channels: int) -> Path:
    run(["-i", str(video), "-vn", "-ac", str(channels), "-ar", str(sample_rate), "-c:a", "pcm_s16le", str(out)])
    return Path(out)


def ensure_browser_video(path: Path) -> Path:
    """Re-encode to H.264/AAC MP4 when the downloaded codec is not browser friendly."""
    codec = video_codec(path)
    if path.suffix.lower() == ".mp4" and codec in ("h264", "vp9", "av1"):
        return path
    out = path.with_name("video_h264.mp4")
    run(["-i", str(path), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)])
    return out


def atempo(src: Path | str, dst: Path | str, rate: float) -> None:
    filters: List[str] = []
    remaining = rate
    while remaining > 2.0:
        filters.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        filters.append("atempo=0.5")
        remaining /= 0.5
    filters.append(f"atempo={remaining:.5f}")
    run(["-i", str(src), "-filter:a", ",".join(filters), str(dst)])


def mux(video: Path | str, audio: Path | str, out: Path | str, subtitles: Sequence[Tuple[Path, str]] = ()) -> Path:
    args: List[str] = ["-i", str(video), "-i", str(audio)]
    for sub, _ in subtitles:
        args += ["-i", str(sub)]
    args += ["-map", "0:v:0", "-map", "1:a:0"]
    for i, _ in enumerate(subtitles):
        args += ["-map", f"{i + 2}:s:0"]
    args += ["-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-metadata:s:a:0", "language=ara"]
    if subtitles:
        args += ["-c:s", "mov_text"]
        for i, (_, lang) in enumerate(subtitles):
            args += [f"-metadata:s:s:{i}", f"language={lang}"]
    args += ["-movflags", "+faststart", str(out)]
    run(args)
    return Path(out)
