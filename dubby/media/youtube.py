"""YouTube download via yt-dlp — no sign-in needed.

Cloud machines (Colab, VMs) are often answered with "Sign in to confirm you're not
a bot". Instead of asking for cookies, the downloader works through strategies
automatically:

1. PO tokens from the bundled token helper (see :mod:`dubby.media.pot`), IPv4;
2. the same video through other YouTube player clients (TV, embedded, Safari…),
   which YouTube scrutinises differently.

A proxy or cookies file from Settings is used when present, but neither is required.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from dubby.config import Settings
from dubby.media import pot

ProgressFn = Callable[[float, str], None]
LogFn = Callable[[str, str], None]

FORMAT = (
    "bv*[vcodec^=avc1][height<=1080]+ba[ext=m4a]/"
    "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/"
    "bv*[height<=1080]+ba/b[ext=mp4]/b"
)

# (label, player clients) — None keeps yt-dlp's own defaults
STRATEGIES: List[Tuple[str, Optional[List[str]]]] = [
    ("default clients", None),
    ("TV client", ["tv_simply", "tv"]),
    ("embedded player", ["web_embedded", "mweb"]),
    ("Safari web client", ["web_safari", "web"]),
]

BLOCK_MARKERS = (
    "confirm you’re not a bot",
    "confirm you're not a bot",
    "sign in to confirm",
    "http error 403",
    "requested format is not available",
    "po token",
    "only images are available",
)
FINAL_MARKERS = ("video unavailable", "private video", "members-only", "join this channel", "has been removed", "is not a valid url", "unsupported url")


class YouTubeAccessError(RuntimeError):
    """A download failure with a human-readable explanation and next steps."""

    def __init__(self, message: str, blocked: bool = False):
        super().__init__(message)
        self.blocked = blocked


def is_blocked(raw: str) -> bool:
    low = raw.lower()
    return any(m in low for m in BLOCK_MARKERS) and not any(m in low for m in FINAL_MARKERS)


def friendly_error(raw: str, attempts: int = 1, token_helper: bool = False) -> YouTubeAccessError:
    text = raw.replace("ERROR: ", "").strip()
    low = text.lower()
    if is_blocked(text):
        tried = f"after {attempts} automatic strategies" + (" with PO tokens" if token_helper else "")
        return YouTubeAccessError(
            f"YouTube is blocking downloads from this server's IP address ({tried}). This happens on Colab and cloud "
            "machines. Fastest fix: upload the video file below — the project keeps all its settings. You can also "
            "retry later or on a new Colab runtime (new IP).",
            blocked=True,
        )
    if "private video" in low or "members-only" in low or "join this channel" in low:
        return YouTubeAccessError("This video is private or members-only — upload the video file instead.", blocked=True)
    if "confirm your age" in low or "age-restricted" in low:
        return YouTubeAccessError("This video is age-restricted — upload the video file instead.", blocked=True)
    if "video unavailable" in low:
        return YouTubeAccessError("YouTube says the video is unavailable (removed, region-locked or a wrong link).")
    return YouTubeAccessError(text)


def _human(num: Optional[float]) -> str:
    if not num:
        return "?"
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024:
            return f"{num:.1f}{unit}"
        num /= 1024
    return f"{num:.1f}TB"


def _noop(msg: str, level: str = "info") -> None:
    pass


def download(url: str, out_dir: Path, settings: Settings, progress: ProgressFn, log: LogFn = _noop) -> Dict:
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

    base: Dict = {
        "format": FORMAT,
        "merge_output_format": "mp4",
        "outtmpl": str(out_dir / "video.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "retries": 3,
        "fragment_retries": 5,
        "source_address": "0.0.0.0",  # IPv4: datacenter IPv6 ranges are flagged more often
        "progress_hooks": [hook],
        "postprocessor_hooks": [pp_hook],
    }
    node = settings.resolved_node()
    if node:
        base["js_runtimes"] = {"node": {"path": node}}
        base["remote_components"] = ["ejs:github"]
    if settings.proxy:
        base["proxy"] = settings.proxy
    cookies = Path(settings.cookies_file).expanduser() if settings.cookies_file else None
    if cookies and cookies.is_file():
        base["cookiefile"] = str(cookies)

    progress(0.005, "Starting the YouTube token helper…")
    token_helper = pot.ensure_running(settings, log)

    last_error = ""
    for attempt, (label, clients) in enumerate(STRATEGIES, start=1):
        opts = dict(base)
        extractor_args: Dict[str, Dict[str, List[str]]] = {}
        if clients:
            extractor_args["youtube"] = {"player_client": clients}
        if token_helper:
            extractor_args["youtubepot-bgutilhttp"] = {"base_url": [pot.BASE_URL]}
        if extractor_args:
            opts["extractor_args"] = extractor_args
        state["stream"] = 0
        for leftover in out_dir.glob("video.*"):
            leftover.unlink(missing_ok=True)
        progress(0.01, f"Resolving video ({label}{', PO tokens' if token_helper else ''})…")
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
        except yt_dlp.utils.DownloadError as exc:
            last_error = str(exc)
            if not is_blocked(last_error) or attempt == len(STRATEGIES):
                raise friendly_error(last_error, attempt, token_helper) from None
            log(f"YouTube blocked the {label} ({last_error.splitlines()[0][:160]}) — trying the next strategy", "warning")
            continue
        if attempt > 1:
            log(f"Downloaded using the {label}", "info")
        break
    else:  # pragma: no cover - loop always breaks or raises
        raise friendly_error(last_error, len(STRATEGIES), token_helper)

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
