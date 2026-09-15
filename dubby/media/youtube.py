"""YouTube download via yt-dlp (uses Node.js from the conda env for YouTube's JS challenges)."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, Optional

from dubby.config import Settings

ProgressFn = Callable[[float, str], None]

FORMAT = (
    "bv*[vcodec^=avc1][height<=1080]+ba[ext=m4a]/"
    "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/"
    "bv*[height<=1080]+ba/b[ext=mp4]/b"
)


def _human(num: Optional[float]) -> str:
    if not num:
        return "?"
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024:
            return f"{num:.1f}{unit}"
        num /= 1024
    return f"{num:.1f}TB"


def download(url: str, out_dir: Path, settings: Settings, progress: ProgressFn) -> Dict:
    import yt_dlp

    out_dir.mkdir(parents=True, exist_ok=True)
    state = {"stream": 0}

    def hook(d: Dict) -> None:
        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            frac = (done / total) if total else 0.0
            base, span = (0.0, 0.75) if state["stream"] == 0 else (0.75, 0.15)
            speed = d.get("speed")
            eta = d.get("eta")
            msg = f"Downloading {'video' if state['stream'] == 0 else 'audio'} · {_human(done)}/{_human(total)} · {_human(speed)}/s" + (f" · ETA {eta}s" if eta else "")
            progress(base + span * frac, msg)
        elif status == "finished":
            state["stream"] += 1

    def pp_hook(d: Dict) -> None:
        if d.get("status") == "started":
            progress(0.92, f"Post-processing ({d.get('postprocessor')})…")

    opts: Dict = {
        "format": FORMAT,
        "merge_output_format": "mp4",
        "outtmpl": str(out_dir / "video.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "retries": 5,
        "fragment_retries": 5,
        "progress_hooks": [hook],
        "postprocessor_hooks": [pp_hook],
    }
    node = settings.resolved_node()
    if node:
        opts["js_runtimes"] = {"node": {"path": node}}
        opts["remote_components"] = ["ejs:github"]
    if settings.cookies_file:
        opts["cookiefile"] = settings.cookies_file

    progress(0.01, "Resolving video…")
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
    candidates = sorted(out_dir.glob("video.*"), key=lambda p: p.stat().st_size, reverse=True)
    candidates = [c for c in candidates if c.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov")]
    if not candidates:
        raise RuntimeError("yt-dlp finished but no video file was produced")
    return {
        "title": info.get("title"),
        "uploader": info.get("uploader") or info.get("channel"),
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "video": candidates[0],
    }
