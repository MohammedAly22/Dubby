"""Automatic YouTube PO-token helper — no cookies, no sign-in.

YouTube scores download requests partly on a Proof-of-Origin (PO) token. The
``bgutil-ytdlp-pot-provider`` yt-dlp plugin mints these tokens through a small
Node.js server. Dubby builds that server once (into the cache dir) and keeps it
running next to the studio, so yt-dlp picks the tokens up automatically.
"""

from __future__ import annotations

import atexit
import shutil
import socket
import subprocess
import threading
import time
from importlib import metadata
from pathlib import Path
from typing import Callable, Optional

from dubby.config import Settings

PORT = 4416
BASE_URL = f"http://127.0.0.1:{PORT}"
REPO = "https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git"
PLUGIN = "bgutil-ytdlp-pot-provider"

LogFn = Callable[[str, str], None]

_lock = threading.Lock()
_proc: Optional[subprocess.Popen] = None


def _noop(msg: str, level: str = "info") -> None:
    pass


def plugin_version() -> Optional[str]:
    try:
        return metadata.version(PLUGIN)
    except metadata.PackageNotFoundError:
        return None


def is_running() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=0.3):
            return True
    except OSError:
        return False


def server_dir(settings: Settings) -> Optional[Path]:
    version = plugin_version()
    return settings.cache_dir / f"bgutil-{version}" / "server" if version else None


def _run(cmd: list, cwd: Path) -> None:
    res = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, errors="replace")
    if res.returncode != 0:
        tail = (res.stderr or res.stdout or "").strip().splitlines()[-5:]
        raise RuntimeError(f"{' '.join(map(str, cmd[:3]))} failed: {' | '.join(tail)}")


def ensure_built(settings: Settings, log: LogFn = _noop) -> Path:
    """Clone and compile the token server matching the installed plugin version (once)."""
    version = plugin_version()
    if not version:
        raise RuntimeError(f"{PLUGIN} is not installed (pip install {PLUGIN})")
    target = server_dir(settings)
    assert target is not None
    if (target / "build" / "main.js").is_file():
        return target
    node = settings.resolved_node()
    npm = shutil.which("npm", path=str(Path(node).parent)) if node else None
    npm = npm or shutil.which("npm")
    git = shutil.which("git")
    if not (node and npm and git):
        raise RuntimeError("building the YouTube token helper needs node, npm and git on the PATH")

    root = target.parent
    staging = root.with_name(root.name + ".partial")
    shutil.rmtree(staging, ignore_errors=True)
    log(f"Building the YouTube token helper (bgutil {version}, one-time, ~1 min)…", "info")
    _run([git, "clone", "--quiet", "--depth", "1", "--single-branch", "--branch", version, REPO, str(staging)], settings.cache_dir)
    server = staging / "server"
    _run([npm, "ci", "--no-audit", "--no-fund", "--loglevel=error"], server)
    _run([node, str(server / "node_modules" / "typescript" / "bin" / "tsc")], server)
    if not (server / "build" / "main.js").is_file():
        raise RuntimeError("token helper build produced no build/main.js")
    shutil.rmtree(root, ignore_errors=True)
    staging.rename(root)
    log("YouTube token helper built", "info")
    return target


def ensure_running(settings: Settings, log: LogFn = _noop, timeout: float = 60.0) -> bool:
    """Make sure the token server answers on 127.0.0.1:4416. Never raises."""
    global _proc
    with _lock:
        if is_running():
            return True
        if not plugin_version():
            log(f"YouTube token helper unavailable: {PLUGIN} is not installed", "warning")
            return False
        try:
            server = ensure_built(settings, log)
            node = settings.resolved_node()
            log_path = settings.cache_dir / "bgutil-server.log"
            _proc = subprocess.Popen(
                [node, str(server / "build" / "main.js"), "--port", str(PORT)],
                cwd=str(server),
                stdin=subprocess.DEVNULL,
                stdout=open(log_path, "ab"),
                stderr=subprocess.STDOUT,
            )
            deadline = time.time() + timeout
            while time.time() < deadline:
                if is_running():
                    log(f"YouTube token helper running on {BASE_URL}", "info")
                    return True
                if _proc.poll() is not None:
                    raise RuntimeError(f"token server exited with code {_proc.returncode} (see {log_path})")
                time.sleep(0.25)
            raise RuntimeError(f"token server did not start within {timeout:.0f}s (see {log_path})")
        except Exception as exc:  # the downloader still tries other strategies
            if _proc and _proc.poll() is None:
                _proc.kill()
            _proc = None
            log(f"YouTube token helper unavailable: {exc}", "warning")
            return False


def warm_up(settings: Settings, log: LogFn = _noop) -> None:
    """Build/start the helper in the background so the first download is fast."""
    threading.Thread(target=ensure_running, args=(settings, log), name="dubby-pot", daemon=True).start()


def stop() -> None:
    global _proc
    proc, _proc = _proc, None
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


atexit.register(stop)
