"""YouTube download via yt-dlp (uses Node.js from the conda env for YouTube's JS challenges)."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, Optional

from dubby.config import Settings

ProgressFn = Callable[[float, str], None]

BOT_CHECK_MARKERS = ("confirm you’re not a bot", "confirm you're not a bot", "sign in to confirm")


class YouTubeAccessError(RuntimeError):
    """A download failure with a human-readable explanation and next steps."""

    def __init__(self, message: str, needs_cookies: bool = False):
        super().__init__(message)
        self.needs_cookies = needs_cookies


def friendly_error(raw: str, used_cookies: bool) -> YouTubeAccessError:
    text = raw.replace("ERROR: ", "").strip()
    low = text.lower()
    if any(marker in low for marker in BOT_CHECK_MARKERS):
        if used_cookies:
            return YouTubeAccessError(
                "YouTube still asks to confirm you're not a bot, even with your cookies. They are probably expired or were "
                "rotated by YouTube. Export fresh cookies from a private/incognito window (Settings → YouTube cookies) and "
                "press Retry, or upload the video file instead.",
                needs_cookies=True,
            )
        return YouTubeAccessError(
            "YouTube asks to confirm you're not a bot — this happens on Colab and other cloud servers. Add your browser's "
            "YouTube cookies (a cookies.txt file) in Settings → YouTube cookies and press Retry, or upload the video file instead.",
            needs_cookies=True,
        )
    if "private video" in low or "members-only" in low or "join this channel" in low:
        return YouTubeAccessError("This video is private or members-only. Add cookies from an account that can watch it, or upload the file.", needs_cookies=True)
    if "age" in low and ("confirm your age" in low or "age-restricted" in low):
        return YouTubeAccessError("This video is age-restricted. Add cookies from a signed-in adult account, or upload the file.", needs_cookies=True)
    if "video unavailable" in low:
        return YouTubeAccessError("YouTube says the video is unavailable (removed, region-locked or a wrong link).")
    return YouTubeAccessError(text)

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
    cookies = Path(settings.cookies_file).expanduser() if settings.cookies_file else None
    if cookies and cookies.is_file():
        opts["cookiefile"] = str(cookies)

    progress(0.01, "Resolving video…" + (" (with your YouTube cookies)" if "cookiefile" in opts else ""))
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except yt_dlp.utils.DownloadError as exc:
        raise friendly_error(str(exc), used_cookies="cookiefile" in opts) from None
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
