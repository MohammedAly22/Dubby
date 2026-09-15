"""Runtime settings.

Settings are resolved from (lowest → highest priority):
  1. built-in defaults
  2. ``<DUBBY_HOME>/settings.json`` (editable from the UI)
  3. environment variables (``DUBBY_*``, ``HF_TOKEN``)
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import threading
from pathlib import Path
from typing import Dict, Optional

from pydantic import BaseModel, Field

ENGINE_FAMILIES = ("core", "qwen", "nemo", "indic")


def default_home() -> Path:
    env = os.environ.get("DUBBY_HOME")
    if env:
        return Path(env).expanduser().resolve()
    return (Path.home() / "Dubby").resolve()


def _conda_env_python(env_name: str) -> Optional[str]:
    """Locate ``python`` inside a sibling conda env (e.g. ``dubby-qwen``)."""
    candidates = []
    prefix = os.environ.get("CONDA_PREFIX") or sys.prefix
    prefix_path = Path(prefix)
    # sys.prefix is either <root> or <root>/envs/<name>
    roots = {prefix_path, prefix_path.parent.parent}
    for root in roots:
        env_dir = root / "envs" / env_name
        candidates += [env_dir / "python.exe", env_dir / "bin" / "python"]
    # Colab / venv layout used by the notebook
    candidates += [Path("/content/envs") / env_name / "bin" / "python"]
    for c in candidates:
        if c.exists():
            return str(c)
    return None


class Settings(BaseModel):
    home: str = Field(default_factory=lambda: str(default_home()))
    host: str = "127.0.0.1"
    port: int = 8765
    device: str = "auto"  # auto | cuda | cpu
    hf_token: Optional[str] = None
    # Interpreter used for each engine family's worker process.
    worker_python: Dict[str, Optional[str]] = Field(default_factory=dict)
    # Stop workers of other families before starting one (frees GPU memory).
    exclusive_gpu: bool = True
    # yt-dlp
    cookies_file: Optional[str] = None
    node_path: Optional[str] = None
    export_dir: Optional[str] = None

    # ------------------------------------------------------------------ paths
    @property
    def home_path(self) -> Path:
        return Path(self.home)

    @property
    def projects_dir(self) -> Path:
        return self.home_path / "projects"

    @property
    def cache_dir(self) -> Path:
        return self.home_path / "cache"

    @property
    def export_path(self) -> Path:
        return Path(self.export_dir).expanduser() if self.export_dir else self.home_path / "exports"

    def python_for(self, family: str) -> str:
        explicit = self.worker_python.get(family)
        if explicit:
            return explicit
        env_var = os.environ.get(f"DUBBY_PYTHON_{family.upper()}")
        if env_var:
            return env_var
        if family != "core":
            found = _conda_env_python(f"dubby-{family}")
            if found:
                return found
        return sys.executable

    def resolved_node(self) -> Optional[str]:
        if self.node_path:
            return self.node_path
        return shutil.which("node")

    def resolved_device(self) -> str:
        if self.device != "auto":
            return self.device
        try:
            import torch  # noqa: WPS433 (optional heavy import)

            return "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            return "cuda" if shutil.which("nvidia-smi") else "cpu"

    def public(self) -> dict:
        data = self.model_dump()
        data["hf_token"] = bool(self.hf_token)
        data["worker_python_resolved"] = {f: self.python_for(f) for f in ENGINE_FAMILIES}
        data["node_resolved"] = self.resolved_node()
        data["device_resolved"] = self.resolved_device()
        return data


_lock = threading.Lock()
_settings: Optional[Settings] = None


def settings_file(home: Optional[Path] = None) -> Path:
    return (home or default_home()) / "settings.json"


def load_settings(reload: bool = False) -> Settings:
    global _settings
    with _lock:
        if _settings is not None and not reload:
            return _settings
        data: dict = {}
        path = settings_file()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                data = {}
        s = Settings(**data)
        if os.environ.get("DUBBY_HOST"):
            s.host = os.environ["DUBBY_HOST"]
        if os.environ.get("DUBBY_PORT"):
            s.port = int(os.environ["DUBBY_PORT"])
        if os.environ.get("DUBBY_DEVICE"):
            s.device = os.environ["DUBBY_DEVICE"]
        token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
        if token and not s.hf_token:
            s.hf_token = token
        for d in (s.projects_dir, s.cache_dir):
            d.mkdir(parents=True, exist_ok=True)
        _settings = s
        return s


def save_settings(update: dict) -> Settings:
    current = load_settings()
    merged = current.model_dump()
    for key, value in update.items():
        if key not in merged:
            continue
        if key == "hf_token" and value in (True, False):
            continue  # masked value coming back from the UI
        if key == "worker_python" and isinstance(value, dict):
            merged[key] = {k: (v or None) for k, v in value.items()}
            continue
        merged[key] = value
    s = Settings(**merged)
    path = settings_file(Path(s.home)) if s.home else settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(s.model_dump(), indent=2, ensure_ascii=False), encoding="utf-8")
    global _settings
    with _lock:
        _settings = s
    return s
