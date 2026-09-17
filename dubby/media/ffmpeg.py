"""Thin, explicit ffmpeg wrappers."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple


class FFmpegError(RuntimeError):
    pass


def binary(name: str = "ffmpeg") -> str:
    path = shutil.which(name)
    if not path:
        raise FFmpegError(f"{name} not found on PATH. Install ffmpeg (conda install -c conda-forge ffmpeg).")
    return path


_filter_binaries: Dict[str, Optional[str]] = {}


def _candidates() -> List[str]:
    """Every ffmpeg we could use: the one first on PATH, others further down PATH, then the imageio-ffmpeg build."""
    found: List[str] = []
    first = shutil.which("ffmpeg")
    if first:
        found.append(first)
    exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    for folder in os.environ.get("PATH", "").split(os.pathsep):
        path = Path(folder.strip('"')) / exe
        if folder and path.is_file():
            found.append(str(path))
    try:
        import imageio_ffmpeg

        found.append(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        pass
    unique: List[str] = []
    for path in found:
        key = os.path.normcase(os.path.realpath(path))
        if key not in {os.path.normcase(os.path.realpath(u)) for u in unique}:
            unique.append(path)
    return unique


def _has_filter(path: str, name: str) -> bool:
    try:
        proc = subprocess.run([path, "-hide_banner", "-filters"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
    except (OSError, subprocess.SubprocessError):
        return False
    return any(len(parts) > 1 and parts[1] == name for parts in (line.split() for line in proc.stdout.splitlines()))


def binary_with_filter(name: str) -> Optional[str]:
    """An ffmpeg that has filter ``name`` (e.g. ``ass``: conda-forge's Windows build ships without libass)."""
    if name not in _filter_binaries:
        _filter_binaries[name] = next((path for path in _candidates() if _has_filter(path, name)), None)
    return _filter_binaries[name]


_encoder_binaries: Optional[Dict[str, str]] = None


def video_encoders(names: Sequence[str] = ("h264_nvenc", "libx264")) -> Dict[str, str]:
    """For each encoder name, the first ffmpeg here that has it (PATH first, then imageio-ffmpeg)."""
    global _encoder_binaries
    if _encoder_binaries is None:
        found: Dict[str, str] = {}
        for path in _candidates():
            try:
                listing = subprocess.run([path, "-hide_banner", "-encoders"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20).stdout
            except (OSError, subprocess.SubprocessError):
                continue
            available = {parts[1] for parts in (line.split() for line in listing.splitlines()) if len(parts) > 1}
            for name in names:
                if name in available:
                    found.setdefault(name, path)
        _encoder_binaries = found
    return _encoder_binaries


def run(args: Sequence[str], cwd: Optional[Path | str] = None) -> str:
    proc = subprocess.run(
        [binary(), "-hide_banner", "-loglevel", "error", "-y", *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(cwd) if cwd else None,
    )
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


def video_size(path: Path | str) -> Tuple[int, int]:
    for s in probe(path).get("streams", []):
        if s.get("codec_type") == "video":
            return int(s.get("width") or 1280), int(s.get("height") or 720)
    return 1280, 720


def run_with_progress(args: Sequence[str], total_seconds: float, progress: Callable[[float], None], cwd: Optional[Path | str] = None,
                      executable: Optional[str] = None) -> None:
    """Run ffmpeg, reporting 0..1 progress from its ``-progress`` stream."""
    cmd = [executable or binary(), "-hide_banner", "-loglevel", "error", "-y", "-progress", "pipe:1", "-nostats", *args]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", cwd=str(cwd) if cwd else None)
    assert proc.stdout is not None
    for line in proc.stdout:
        if line.startswith("out_time_us=") or line.startswith("out_time_ms="):
            try:
                seconds = int(line.split("=", 1)[1]) / 1_000_000
            except ValueError:
                continue
            if total_seconds > 0:
                progress(max(0.0, min(1.0, seconds / total_seconds)))
    stderr = proc.stderr.read() if proc.stderr else ""
    if proc.wait() != 0:
        raise FFmpegError(stderr.strip()[-1500:] or f"ffmpeg failed with code {proc.returncode}")


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
