"""The Studio: orchestrates projects, stages, workers and events.

Both the web server and the CLI drive the pipeline exclusively through this class.
"""

from __future__ import annotations

import os
import re
import shutil
import threading
import time
import traceback
import uuid
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple  # noqa: F401

from pydantic import ValidationError

from dubby import hardware, languages, recommend
from dubby.errors import explain
from dubby.config import ENGINE_FAMILIES, Settings, load_settings, save_settings
from dubby.core import voices
from dubby.core.events import EventBus
from dubby.core.reporter import TerminalReporter
from dubby.core.jobs import Job, JobHandlers, JobManager, run_doctor
from dubby.core.storage import ProjectStore
from dubby.engines.registry import all_infos, get_info
from dubby.media import ffmpeg, pot, youtube
from dubby.pipeline.chunking import fill_word_times, split_segment_words
from dubby.text import SUPPORTED as TEXT_LANGUAGES
from dubby.text import normalize_safe
from dubby.pipeline import captions as caption_burn
from dubby.pipeline.render import render_project
from dubby.schemas import (
    EngineChoice,
    ExportItem,
    MixConfig,
    Project,
    ProjectSettings,
    RenderInfo,
    Segment,
    StageState,
    TTSState,
    VoiceConfig,
    Word,
)

YOUTUBE_RE = re.compile(r"^(https?://)?(www\.|m\.|music\.)?(youtube\.com|youtu\.be)/", re.I)

# Minimum gap between progress-only stage events (status changes are never throttled).
PROGRESS_PUBLISH_INTERVAL = 0.2


class StudioError(Exception):
    """A user-facing error (bad request, missing prerequisite…)."""


class Cancelled(Exception):
    pass


def _deep_merge(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict) and k != "params":
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


class Studio:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or load_settings()
        self.store = ProjectStore(self.settings.projects_dir)
        self.bus = EventBus()
        # the terminal log, mirrored line by line into the UI's Logs drawer
        self.bus.subscribe(TerminalReporter(echo=False, feed=self.bus.console))
        self.jobs = JobManager(self.settings, self.bus)
        self.pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="dubby-cpu")
        self._engine_status: Dict[str, Any] = {}
        self._status_lock = threading.Lock()
        self._cancel_flags: Set[Tuple[str, str]] = set()
        self._last_progress_pub: Dict[Tuple[str, str], float] = {}
        self._recover()
        recommend.set_gemini(bool(self.settings.gemini_api_key))
        threading.Thread(target=self._saver, daemon=True, name="dubby-saver").start()
        # build/start the YouTube token helper now so the first download doesn't wait for it
        pot.warm_up(self.settings, lambda msg, level="info": self.bus.log(msg, level, source="youtube"))

    # ================================================================ plumbing
    def _saver(self) -> None:
        while True:
            time.sleep(1.0)
            try:
                self.store.flush_dirty()
            except Exception as exc:
                self.bus.log(f"Autosave failed: {exc}", "error")

    def _recover(self) -> None:
        for p in self.store.list():
            changed = False
            for name, st in p.stages.items():
                if st.status in ("running", "queued"):
                    st.status, st.error, st.message = "error", "Interrupted — the studio was restarted.", "Interrupted"
                    changed = True
            for s in p.segments:
                if s.translation_status in ("queued", "running"):
                    s.translation_status = "done" if s.translation else "pending"
                    changed = True
                if s.tts.status in ("queued", "running"):
                    s.tts.status = "done" if s.tts.audio else "pending"
                    changed = True
            if changed:
                self.store.save(p)

    def publish_project(self, project_id: str) -> None:
        self.bus.publish({"type": "project", "project": self.store.get(project_id).model_dump()})

    def set_stage(self, project_id: str, stage: str, persist: bool = True, **changes: Any) -> None:
        # Progress ticks arrive many times a second; publishing each one floods the websocket
        # (very noticeable through the Colab proxy). Status changes always go out immediately.
        if "status" not in changes:
            now = time.time()
            key = (project_id, stage)
            if now - self._last_progress_pub.get(key, 0.0) < PROGRESS_PUBLISH_INTERVAL:
                with self.store.mutate(project_id, persist=persist) as p:
                    st = p.stages.setdefault(stage, StageState())
                    for k, v in changes.items():
                        setattr(st, k, v)
                return
            self._last_progress_pub[key] = now
        with self.store.mutate(project_id, persist=persist) as p:
            st = p.stages.setdefault(stage, StageState())
            status = changes.get("status")
            if status == "running" and st.status != "running":
                st.started_at, st.finished_at, st.error = time.time(), None, None
            if status in ("done", "error", "cancelled", "paused"):
                st.finished_at = time.time()
            for key, value in changes.items():
                setattr(st, key, value)
            state = st.model_dump()
        self.bus.publish({"type": "stage", "project_id": project_id, "stage": stage, "state": state})

    def _publish_segment(self, project_id: str, seg: Segment, index: int, change: str) -> None:
        self.bus.publish({"type": "segment", "project_id": project_id, "segment": seg.model_dump(), "index": index, "change": change})

    def _check_cancel(self, project_id: str, stage: str) -> None:
        if (project_id, stage) in self._cancel_flags:
            self._cancel_flags.discard((project_id, stage))
            raise Cancelled()

    @contextmanager
    def track(self, project_id: Optional[str], kind: str, label: str, stage: Optional[str] = None, engine: Optional[str] = None, **detail: Any):
        """Report studio-side work (downloads, renders, exports...) to the Requests tab."""
        rid = f"studio:{uuid.uuid4().hex[:12]}"
        self.bus.request({"id": rid, "kind": kind, "label": label, "level": "job", "status": "running", "started": time.time(),
                          "project_id": project_id, "stage": stage, "engine": engine, "family": "studio", "detail": detail})
        try:
            yield
        except Cancelled:
            self.bus.request({"id": rid, "status": "cancelled", "ended": time.time()})
            raise
        except BaseException as exc:
            self.bus.request({"id": rid, "status": "error", "ended": time.time(), "error": str(exc)[:400]})
            raise
        self.bus.request({"id": rid, "status": "done", "ended": time.time()})

    def _choice(self, project_id: str, stage: str, engine: Optional[str], params: Optional[Dict[str, Any]]) -> EngineChoice:
        with self.store.mutate(project_id) as p:
            current: EngineChoice = getattr(p.settings, stage)
            if engine and engine != current.engine:
                current = EngineChoice(engine=engine, params={})
            if params is not None:
                current.params = {**current.params, **params}
            if not current.engine:
                raise StudioError(f"Choose a {stage} engine first")
            info = get_info(current.engine)
            current.params = {**info.defaults(), **current.params}
            setattr(p.settings, stage, current)
            choice = current.model_copy(deep=True)
        self._ensure_fits(choice.engine, choice.params)
        return choice

    def _gpu(self) -> Optional[hardware.GPU]:
        with self._status_lock:
            status = self._engine_status
        return hardware.from_status(status)

    def _ensure_fits(self, engine_id: str, params: Dict[str, Any]) -> None:
        """Refuse to queue a model that cannot fit the GPU (the worker double-checks)."""
        verdict = hardware.check(engine_id, params, self._gpu())
        if not verdict["fits"]:
            raise StudioError(" ".join(filter(None, [verdict["message"], verdict["suggestion"]])))

    def check_engine(self, engine_id: str, params: Optional[Dict[str, Any]], source: Optional[str] = None, target: Optional[str] = None) -> Dict[str, Any]:
        try:
            get_info(engine_id)
        except KeyError as exc:
            raise StudioError(str(exc).strip("'\"")) from None
        return hardware.check(engine_id, params, self._gpu(), source, target)

    def _require_available(self, engine_id: str) -> None:
        status = self.engine_status()
        info = get_info(engine_id)
        if info.family == "cloud" and not self.settings.gemini_api_key:
            raise StudioError(f"{info.name} needs a Gemini API key. Add it in ⚙️ Settings → Gemini API key.")
        fam = status.get(info.family, {})
        entry = fam.get("engines", {}).get(engine_id)
        if fam and entry and not entry.get("available"):
            raise StudioError(f"{info.name} is not installed in the '{info.family}' interpreter (missing: {', '.join(entry.get('missing', []))}). Install: {info.install}")

    # ================================================================ engines
    def engine_status(self, refresh: bool = False) -> Dict[str, Any]:
        with self._status_lock:
            if self._engine_status and not refresh:
                return self._engine_status
        families = sorted({i.family for i in all_infos()} | set(ENGINE_FAMILIES))
        with ThreadPoolExecutor(max_workers=len(families)) as ex:
            results = dict(zip(families, ex.map(lambda f: run_doctor(self.settings, f), families)))
        with self._status_lock:
            self._engine_status = results
        self.bus.publish({"type": "engines"})
        return results

    def engines(self, refresh: bool = False) -> Dict[str, Any]:
        status = self.engine_status(refresh)
        gpu = hardware.from_status(status)
        infos = []
        for info in all_infos():
            d = info.to_dict()
            fam = status.get(info.family, {})
            entry = fam.get("engines", {}).get(info.id)
            d["available"] = bool(entry and entry.get("available"))
            d["missing"] = entry.get("missing", []) if entry else info.requires
            d["family_error"] = fam.get("error")
            if info.family == "cloud" and not self.settings.gemini_api_key:
                d["available"] = False
                d["missing"] = ["Gemini API key (⚙️ Settings)"]
            try:
                d.update(hardware.minimum_vram(info.id, gpu))
            except Exception:  # a buggy estimate must never hide the engine list
                d.update(vram_min_gb=None, vram_default_gb=None, fits_any=True)
            infos.append(d)
        return {"engines": infos, "families": status, "gpu": gpu.to_dict() if gpu else None}

    def system(self) -> Dict[str, Any]:
        status = self.engine_status()
        return {
            "settings": self.settings.public(),
            "families": {f: {k: v.get(k) for k in ("python", "python_version", "torch", "error")} for f, v in status.items()},
            "jobs": self.jobs.snapshot(),
            "ffmpeg": shutil.which("ffmpeg"),
            "node": self.settings.resolved_node(),
        }

    def apply_settings(self, settings: Settings) -> None:
        key_changed = settings.gemini_api_key != self.settings.gemini_api_key
        self.settings = settings
        self.jobs.settings = settings
        for w in self.jobs.workers.values():
            w.settings = settings
        recommend.set_gemini(bool(settings.gemini_api_key))
        if key_changed and "cloud" in self.jobs.workers:
            self.jobs.workers["cloud"].stop()  # the API key is passed to the worker at start-up
        self.pool.submit(self.engine_status, True)

    # ------------------------------------------------------------ Gemini
    def save_gemini_key(self, key: str) -> Dict[str, Any]:
        """Validate a Gemini API key with one tiny request, then save it."""
        from dubby.engines.gemini_common import validate_key

        result = validate_key(key)
        if not result.get("ok"):
            return {**result, "settings": self.settings.public()}
        settings = save_settings({"gemini_api_key": key.strip()})
        self.apply_settings(settings)
        self.bus.log(f"Gemini API key saved and verified ({result['model']}, {result['latency_ms']} ms)", source="settings")
        self.bus.publish({"type": "engines"})
        return {**result, "settings": settings.public()}

    def remove_gemini_key(self) -> Settings:
        settings = save_settings({"gemini_api_key": None})
        self.apply_settings(settings)
        self.bus.log("Gemini API key removed", source="settings")
        self.bus.publish({"type": "engines"})
        return settings

    def gemini_voice_preview(self, voice: str, language: str) -> Path:
        from dubby.engines.tts import gemini_tts

        if not self.settings.gemini_api_key:
            raise StudioError("Add a Gemini API key in ⚙️ Settings to preview Gemini voices.")
        if voice not in gemini_tts.VOICE_NAMES:
            raise StudioError(f"Unknown Gemini voice '{voice}'.")
        language = language if language in gemini_tts.SAMPLE_TEXT else "en"
        out = self.settings.cache_dir / "gemini_voices" / f"{voice}_{language}.wav"
        try:
            gemini_tts.preview_voice(voice, language, str(out), self.settings.gemini_api_key)
        except Exception as exc:
            out.unlink(missing_ok=True)
            raise StudioError(explain(exc).text()) from None
        return out

    # ================================================================ projects
    def _available_engines(self) -> Optional[Set[str]]:
        with self._status_lock:
            status = self._engine_status
        if not status:
            return None
        ready = {eid for fam in status.values() for eid, entry in fam.get("engines", {}).items() if entry.get("available")}
        if not self.settings.gemini_api_key:  # API engines need a key as well as the package
            ready = {eid for eid in ready if get_info(eid).family != "cloud"}
        return ready

    def _new_settings(self, source_language: str, target: str) -> Tuple[ProjectSettings, bool]:
        auto = source_language in ("auto", "", None)
        source = "en" if auto else source_language
        if source not in languages.SOURCE_CODES:
            raise StudioError(f"Unsupported spoken language '{source_language}'. Choose one of: auto, {', '.join(languages.SOURCE_CODES)}.")
        if target not in languages.TARGET_CODES:
            raise StudioError(f"Unsupported dub language '{target}'. Choose one of: {', '.join(languages.TARGET_CODES)}.")
        settings = ProjectSettings(source_language=source, target=target)
        available = self._available_engines()
        for stage in ("asr", "translation", "tts"):
            rec = recommend.best(stage, source, target, available)
            if rec:
                setattr(settings, stage, EngineChoice(engine=rec.engine, params=dict(rec.params)))
        return settings, auto

    def create_project(self, url: str, source_language: str = "auto", target: str = "arz") -> Project:
        url = (url or "").strip()
        if not YOUTUBE_RE.match(url):
            raise StudioError("Please paste a valid YouTube link (youtube.com or youtu.be).")
        settings, auto = self._new_settings(source_language, target)
        p = self.store.create(title="YouTube video")
        with self.store.mutate(p.id) as proj:
            proj.source.kind, proj.source.url, proj.source.auto_detect = "youtube", url, auto
            proj.settings = settings
        self.publish_project(p.id)
        self.bus.log(f"New project {p.id} ← {url}", project_id=p.id)
        self.pool.submit(self._prepare_source, p.id)
        return self.store.get(p.id)

    def create_project_from_file(self, filename: str, data: bytes, source_language: str = "auto", target: str = "arz") -> Project:
        settings, auto = self._new_settings(source_language, target)
        p = self.store.create(title=Path(filename).stem)
        ext = Path(filename).suffix.lower() or ".mp4"
        dest = self.store.dir(p.id) / "source" / f"upload{ext}"
        with self.track(p.id, "upload", f"Save upload · {filename}", stage="download", bytes=len(data)):
            dest.write_bytes(data)
        with self.store.mutate(p.id) as proj:
            proj.source.kind, proj.source.video, proj.title = "upload", f"source/{dest.name}", Path(filename).stem
            proj.source.auto_detect = auto
            proj.settings = settings
        self.publish_project(p.id)
        self.pool.submit(self._prepare_source, p.id)
        return self.store.get(p.id)

    def replace_source_with_file(self, project_id: str, filename: str, data: bytes) -> Project:
        """Use an uploaded video for an existing project (e.g. when YouTube blocks the download)."""
        p = self.store.get(project_id)
        if p.stages.get("download", StageState()).status in ("running", "queued"):
            raise StudioError("The download is still running — cancel it first.")
        ext = Path(filename).suffix.lower() or ".mp4"
        dest = self.store.dir(project_id) / "source" / f"upload{ext}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        with self.store.mutate(project_id) as proj:
            proj.source.kind, proj.source.video = "upload", f"source/{dest.name}"
            proj.source.audio16k = proj.source.audio_hq = proj.source.vocals = proj.source.background = None
            if proj.title in ("YouTube video", "Untitled"):
                proj.title = Path(filename).stem
        self.bus.log(f"Using uploaded file {filename} as the source", project_id=project_id)
        self.publish_project(project_id)
        self.pool.submit(self._prepare_source, project_id)
        return self.store.get(project_id)

    # ---------------------------------------------------------- YouTube cookies
    def save_cookies(self, data: bytes) -> Settings:
        """Validate and store a Netscape cookies.txt used by yt-dlp. Contents are never logged."""
        text = data.decode("utf-8", errors="replace")
        entries = []
        for line in text.splitlines():
            if line.startswith("#HttpOnly_"):
                line = line[len("#HttpOnly_"):]
            elif not line.strip() or line.startswith("#"):
                continue
            fields = line.split("\t")
            if len(fields) >= 7:
                entries.append(fields)
        if not entries:
            raise StudioError("That is not a Netscape cookies.txt file (tab-separated lines with 7 fields). Export it with a “Get cookies.txt LOCALLY” browser extension.")
        if not any("youtube.com" in f[0] for f in entries):
            raise StudioError("The file has no youtube.com cookies — export them from a browser tab where you are signed in to YouTube.")
        path = self.settings.home_path / "cookies.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        settings = save_settings({"cookies_file": str(path)})
        self.apply_settings(settings)
        self.bus.log(f"YouTube cookies saved ({sum(1 for f in entries if 'youtube.com' in f[0])} youtube.com cookies)", source="settings")
        return settings

    def remove_cookies(self) -> Settings:
        current = self.settings.cookies_file
        if current:
            path = Path(current)
            if path.is_file() and path.parent.resolve() == self.settings.home_path.resolve():
                path.unlink(missing_ok=True)
        settings = save_settings({"cookies_file": None})
        self.apply_settings(settings)
        self.bus.log("YouTube cookies removed", source="settings")
        return settings

    def delete_project(self, project_id: str) -> None:
        self.jobs.cancel(project_id)
        self.store.delete(project_id)
        self.bus.publish({"type": "project_deleted", "project_id": project_id})

    def _prepare_source(self, project_id: str) -> None:
        stage = "download"
        try:
            self.set_stage(project_id, stage, status="running", progress=0.0, message="Starting…", engine="yt-dlp", error=None)
            p = self.store.get(project_id)
            src_dir = self.store.dir(project_id) / "source"

            def progress(v: float, msg: str) -> None:
                self._check_cancel(project_id, stage)
                self.set_stage(project_id, stage, persist=False, progress=round(v * 0.85, 4), message=msg)

            meta: Dict[str, Any] = {}
            if p.source.kind == "youtube":
                with self.track(project_id, "download", "YouTube download", stage=stage, engine="yt-dlp", url=p.source.url):
                    meta = youtube.download(
                        p.source.url or "", src_dir, self.settings, progress,
                        log=lambda msg, level="info": self.bus.log(msg, level, project_id, source="download"),
                    )
                video = Path(meta["video"])
            else:
                video = self.store.path(project_id, p.source.video or "")
            self.set_stage(project_id, stage, persist=False, progress=0.87, message="Checking video codec…")
            with self.track(project_id, "ffmpeg", "Check / convert video codec", stage=stage, engine="ffmpeg"):
                video = ffmpeg.ensure_browser_video(video)
            self._check_cancel(project_id, stage)
            self.set_stage(project_id, stage, persist=False, progress=0.92, message="Extracting 16 kHz speech track…")
            with self.track(project_id, "ffmpeg", "Extract 16 kHz speech track", stage=stage, engine="ffmpeg"):
                a16 = ffmpeg.extract_audio(video, src_dir / "audio_16k.wav", 16000, 1)
            self.set_stage(project_id, stage, persist=False, progress=0.96, message="Extracting 44.1 kHz mix track…")
            with self.track(project_id, "ffmpeg", "Extract 44.1 kHz mix track", stage=stage, engine="ffmpeg"):
                hq = ffmpeg.extract_audio(video, src_dir / "audio_hq.wav", 44100, 2)
            duration = ffmpeg.duration(video)
            with self.store.mutate(project_id) as proj:
                proj.source.video = self.store.rel(project_id, video)
                proj.source.audio16k = self.store.rel(project_id, a16)
                proj.source.audio_hq = self.store.rel(project_id, hq)
                proj.source.duration = duration
                for key in ("title", "uploader", "thumbnail"):
                    if meta.get(key):
                        setattr(proj.source, key, meta[key])
                if meta.get("title"):
                    proj.title = meta["title"]
                title = proj.title
                auto_detect = proj.source.auto_detect
            if auto_detect:
                # queue detection before marking the download done so waiters never see a gap
                try:
                    self.run_langid(project_id)
                except StudioError as exc:
                    self.bus.log(f"Language detection skipped: {exc}", "warning", project_id)
            self.set_stage(project_id, stage, status="done", progress=1.0, message=f"{title} · {int(duration // 60)}m{int(duration % 60):02d}s")
            self.publish_project(project_id)
        except Cancelled:
            self.set_stage(project_id, stage, status="cancelled", message="Cancelled")
        except youtube.YouTubeAccessError as exc:
            # expected, actionable failure: no traceback, just the explanation
            self.bus.log(str(exc), "warning", project_id, source="download")
            self.set_stage(project_id, stage, status="error", error=str(exc), message="Blocked by YouTube — upload the file" if exc.blocked else "Failed")
        except Exception as exc:
            self.bus.log(traceback.format_exc(), "error", project_id, source="download")
            self.set_stage(project_id, stage, status="error", error=str(exc), message="Failed")

    def update_settings(self, project_id: str, patch: Dict[str, Any]) -> Project:
        try:
            with self.store.mutate(project_id) as p:
                merged = _deep_merge(p.settings.model_dump(), patch)
                p.settings = ProjectSettings.model_validate(merged)
        except ValidationError as exc:
            raise StudioError("; ".join(err["msg"] for err in exc.errors())) from exc
        # A language change re-picks the stages that depend on it (the previous engines were chosen
        # for another language); engines explicitly sent in the same patch are kept.
        affected: List[str] = []
        if "source_language" in patch:
            affected += ["asr", "translation"]
        if "target" in patch:
            affected += ["translation", "tts"]
        stages = [s for s in dict.fromkeys(affected) if s not in patch]
        if stages:
            self.apply_recommendations(project_id, stages=stages, publish=False)
        self.publish_project(project_id)
        return self.store.get(project_id)

    def apply_recommendations(
        self,
        project_id: str,
        stages: Iterable[str] = ("asr", "translation", "tts"),
        only_incompatible: bool = False,
        publish: bool = True,
    ) -> Project:
        available = self._available_engines()
        changed: List[str] = []
        with self.store.mutate(project_id) as p:
            source, target = p.settings.source_language, p.settings.target
            for stage in stages:
                current: EngineChoice = getattr(p.settings, stage)
                if only_incompatible and current.engine and recommend.supports(current.engine, stage, source, target):
                    continue
                rec = recommend.best(stage, source, target, available)
                if rec and (rec.engine != current.engine or not only_incompatible):
                    setattr(p.settings, stage, EngineChoice(engine=rec.engine, params=dict(rec.params)))
                    changed.append(f"{stage}={rec.engine}")
        if changed:
            self.bus.log(f"Recommended engines applied: {', '.join(changed)}", project_id=project_id)
        if publish:
            self.publish_project(project_id)
        return self.store.get(project_id)

    # ----------------------------------------------------------- language ID
    def run_langid(self, project_id: str, engine: str = "whisper-langid", params: Optional[Dict[str, Any]] = None) -> Job:
        p = self.store.get(project_id)
        if not p.source.audio16k:
            raise StudioError("The source audio is not ready yet.")
        self._require_available(engine)
        info = get_info(engine)

        def on_done(data: Dict[str, Any]) -> None:
            raw = data.get("language") or ""
            probability = float(data.get("probability") or 0.0)
            detected = languages.from_iso(raw)
            with self.store.mutate(project_id) as proj:
                proj.source.detected_language = raw
                proj.source.detected_probability = probability
                proj.source.detected_candidates = data.get("candidates", [])
                proj.source.auto_detect = False
                previous = proj.settings.source_language
                if detected:
                    proj.settings.source_language = detected
            if detected:
                self.apply_recommendations(project_id, stages=("asr", "translation"), publish=False)
                msg = f"{languages.get(detected).name} · {probability:.0%} confidence"
            else:
                msg = f"Detected '{raw}' ({probability:.0%}) — not a supported spoken language, kept {languages.get(previous).name}"
            self.set_stage(project_id, "langid", status="done", progress=1.0, message=msg)
            self.publish_project(project_id)

        handlers = JobHandlers(
            on_start=lambda: self.set_stage(project_id, "langid", status="running", progress=0.0, message="Detecting the spoken language…", engine=engine),
            on_progress=lambda v, m: self.set_stage(project_id, "langid", persist=False, progress=v, message=m),
            on_done=on_done,
            on_error=lambda e: self.set_stage(project_id, "langid", status="error", error=e, message="Failed"),
            on_cancel=lambda: self.set_stage(project_id, "langid", status="cancelled", message="Cancelled"),
        )
        self.set_stage(project_id, "langid", status="queued", progress=0.0, message="Waiting for a worker…", engine=engine, error=None)
        payload = {"audio": str(self.store.path(project_id, p.source.audio16k))}
        return self.jobs.submit(Job(project_id, "langid", "langid", engine, {**info.defaults(), **(params or {})}, payload, handlers))

    # --------------------------------------------------- reference transcript
    def transcribe_voice_reference(self, project_id: str, engine: Optional[str] = None, language: Optional[str] = None, params: Optional[Dict[str, Any]] = None) -> Job:
        """Transcribe the prepared reference clip with an ASR engine to use as the TTS reference text."""
        p = self.store.get(project_id)
        if not p.voice.ref_audio:
            raise StudioError("Prepare a clip or upload a reference voice first.")
        lang = language or p.voice.ref_language or p.settings.source_language
        if lang not in languages.SOURCE_CODES:
            raise StudioError(f"Unsupported reference language '{lang}'.")
        if not engine:
            current = p.settings.asr.engine
            if current and recommend.supports(current, "asr", lang, p.settings.target):
                engine = current
            else:
                rec = recommend.best("asr", lang, p.settings.target, self._available_engines())
                engine = rec.engine if rec else None
        if not engine:
            raise StudioError("No ASR engine supports the reference language.")
        info = get_info(engine)
        if lang not in info.source_languages:
            raise StudioError(f"{info.name} does not support {languages.get(lang).name}.")
        self._require_available(engine)
        run_params = {**info.defaults(), **(p.settings.asr.params if engine == p.settings.asr.engine else {}), **(params or {})}
        payload = {"audio": str(self.store.path(project_id, p.voice.ref_audio)), "language": lang}

        def set_status(status: str, **extra: Any) -> None:
            with self.store.mutate(project_id) as proj:
                proj.voice.ref_text_status = status  # type: ignore[assignment]
                for key, value in extra.items():
                    setattr(proj.voice, key, value)
            self.publish_project(project_id)

        def on_done(data: Dict[str, Any]) -> None:
            text = str(data.get("text", "")).strip()
            set_status("done", ref_text=text, ref_language=lang)
            self.bus.log(f"Reference transcribed with {info.name}: {text[:160]}", project_id=project_id, source="voice")

        handlers = JobHandlers(
            on_start=lambda: set_status("running"),
            on_done=on_done,
            on_error=lambda e: (set_status("error"), self.bus.log(f"Reference transcription failed: {e}", "error", project_id, source="voice")),
            on_cancel=lambda: set_status("idle"),
        )
        set_status("queued")
        return self.jobs.submit(Job(project_id, "voice", "asr_ref", engine, run_params, payload, handlers))

    # ================================================================ segments
    def update_segment(self, project_id: str, seg_id: str, patch: Dict[str, Any]) -> Segment:
        with self.store.mutate(project_id) as p:
            seg = p.segment(seg_id)
            index = p.segments.index(seg)
            duration = p.source.duration or 1e9
            if "start" in patch or "end" in patch:
                start = float(patch.get("start", seg.start))
                end = float(patch.get("end", seg.end))
                if not 0 <= start < end <= duration + 0.5:
                    raise StudioError("Invalid segment times")
                seg.start, seg.end = round(start, 3), round(end, 3)
                seg.words = [w for w in seg.words if w.end > seg.start and w.start < seg.end]
            if "text" in patch and patch["text"].strip() != seg.text:
                lang = p.settings.source_language
                raw_text = str(patch["text"]).strip()
                text = " ".join(raw_text.split()) if languages.get(lang).spaced else raw_text
                tokens = languages.tokenize(text, lang)
                if len(tokens) == len(seg.words):
                    for w, t in zip(seg.words, tokens):
                        w.text = t
                else:
                    seg.words = [Word(**w) for w in fill_word_times([{"text": t} for t in tokens], seg.start, seg.end)]
                seg.text = text
            if "translation" in patch:
                seg.translation = str(patch["translation"]).strip()
                seg.translation_status = "done" if seg.translation else "pending"
                seg.translation_source = seg.text
                seg.translation_error = None
        self._publish_segment(project_id, seg, index, "edit")
        return seg

    def merge_segment(self, project_id: str, seg_id: str) -> Project:
        with self.store.mutate(project_id) as p:
            seg = p.segment(seg_id)
            i = p.segments.index(seg)
            if i + 1 >= len(p.segments):
                raise StudioError("This is the last segment — nothing to merge with.")
            nxt = p.segments[i + 1]
            both_translated = seg.translation_status == "done" and nxt.translation_status == "done"
            merged_text = languages.join_tokens([seg.text, nxt.text], p.settings.source_language)
            merged = Segment(
                id=seg.id,
                start=seg.start,
                end=nxt.end,
                text=merged_text,
                words=seg.words + nxt.words,
                translation=languages.join_tokens([seg.translation, nxt.translation], p.settings.target) if both_translated else "",
                translation_status="done" if both_translated else "pending",
                translation_source=merged_text if both_translated else None,
            )
            p.segments[i:i + 2] = [merged]
        self.publish_project(project_id)
        return self.store.get(project_id)

    def split_segment(self, project_id: str, seg_id: str, word_index: int) -> Project:
        with self.store.mutate(project_id) as p:
            seg = p.segment(seg_id)
            i = p.segments.index(seg)
            try:
                parts = split_segment_words(seg.model_dump(), int(word_index), languages.get(p.settings.source_language).spaced)
            except ValueError as exc:
                raise StudioError(str(exc)) from exc
            p.segments[i:i + 1] = [Segment(**part) for part in parts]
        self.publish_project(project_id)
        return self.store.get(project_id)

    def delete_segment(self, project_id: str, seg_id: str) -> Project:
        with self.store.mutate(project_id) as p:
            p.segments = [s for s in p.segments if s.id != seg_id]
        self.publish_project(project_id)
        return self.store.get(project_id)

    # ================================================================ stages
    def run_stage(self, project_id: str, stage: str, engine: Optional[str] = None, params: Optional[Dict[str, Any]] = None, segment_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        runners: Dict[str, Callable[..., Any]] = {
            "download": lambda: self.pool.submit(self._prepare_source, project_id),
            "langid": lambda: self.run_langid(project_id, engine or "whisper-langid", params),
            "asr": lambda: self.run_asr(project_id, engine, params),
            "translation": lambda: self.run_translation(project_id, engine, params, segment_ids),
            "tts": lambda: self.run_tts(project_id, engine, params, segment_ids),
            "separation": lambda: self.run_separation(project_id, engine or "demucs", params),
            "render": lambda: self.render(project_id),
        }
        if stage not in runners:
            raise StudioError(f"Unknown stage '{stage}'")
        self.store.get(project_id)
        runners[stage]()
        return {"ok": True}

    def cancel(self, project_id: str, stage: str) -> Dict[str, Any]:
        if stage in ("download", "render", "export"):
            st = self.store.get(project_id).stages.get(stage)
            if st and st.status == "running":
                self._cancel_flags.add((project_id, stage))
            return {"cancelled": 1}
        return {"cancelled": self.jobs.cancel(project_id, stage)}

    # ----------------------------------------------------------------- ASR
    def run_asr(self, project_id: str, engine: Optional[str] = None, params: Optional[Dict[str, Any]] = None) -> Job:
        p = self.store.get(project_id)
        if not p.source.audio16k:
            raise StudioError("The source video is not ready yet.")
        choice = self._choice(project_id, "asr", engine, params)
        info = get_info(choice.engine or "")
        self._require_available(info.id)
        lang = p.settings.source_language
        if lang not in info.source_languages:
            raise StudioError(f"{info.name} does not support the source language '{lang}'.")
        payload = {
            "audio": str(self.store.path(project_id, p.source.audio16k)),
            "language": lang,
            "chunking": {
                "max_seconds": p.settings.max_chunk_seconds,
                "min_seconds": p.settings.min_chunk_seconds,
                "max_gap": p.settings.max_word_gap,
                "spaced": languages.get(lang).spaced,
            },
        }
        preview: List[Dict[str, Any]] = []

        def on_result(kind: str, data: Dict[str, Any]) -> None:
            if kind != "asr_partial":
                return
            if data.get("replace"):
                preview.clear()
            preview.extend(data.get("segments", []))
            self.bus.publish({"type": "segments", "project_id": project_id, "segments": preview, "partial": True, "replace": bool(data.get("replace"))})

        def on_done(data: Dict[str, Any]) -> None:
            segments = [Segment(**s) for s in data.get("segments", [])]
            with self.store.mutate(project_id) as proj:
                proj.segments = segments
                for name in ("translation", "tts", "render"):
                    proj.stages[name] = StageState()
                proj.render = RenderInfo()
            self.bus.publish({"type": "segments", "project_id": project_id, "segments": [s.model_dump() for s in segments], "final": True})
            words = sum(len(s.words) for s in segments)
            self.set_stage(project_id, "asr", status="done", progress=1.0, message=f"{len(segments)} chunks · {words} words")
            self.publish_project(project_id)

        handlers = JobHandlers(
            on_start=lambda: self.set_stage(project_id, "asr", status="running", progress=0.0, message=f"Starting {info.name}…", engine=info.id),
            on_progress=lambda v, m: self.set_stage(project_id, "asr", persist=False, progress=v, message=m),
            on_result=on_result,
            on_done=on_done,
            on_error=lambda e: self.set_stage(project_id, "asr", status="error", error=e, message="Failed"),
            on_cancel=lambda: self.set_stage(project_id, "asr", status="cancelled", message="Cancelled"),
        )
        self.set_stage(project_id, "asr", status="queued", progress=0.0, message="Waiting for a worker…", engine=info.id, error=None)
        return self.jobs.submit(Job(project_id, "asr", "asr", info.id, choice.params, payload, handlers))

    # ---------------------------------------------------------- translation
    def run_translation(self, project_id: str, engine: Optional[str] = None, params: Optional[Dict[str, Any]] = None, segment_ids: Optional[List[str]] = None) -> Job:
        p = self.store.get(project_id)
        if not p.segments:
            raise StudioError("Transcribe the video first.")
        choice = self._choice(project_id, "translation", engine, params)
        info = get_info(choice.engine or "")
        self._require_available(info.id)
        source, target = p.settings.source_language, p.settings.target
        if not recommend.supports(info.id, "translation", source, target):
            raise StudioError(f"{info.name} cannot translate {languages.get(source).name} → {languages.get(target).name}.")
        wanted = set(segment_ids) if segment_ids else None
        items = [
            {"id": s.id, "text": s.text, "duration": round(s.duration, 2)}
            for s in p.segments
            if (wanted is None or s.id in wanted) and s.text.strip()
        ]
        if not items:
            raise StudioError("No segments to translate.")
        sources = {it["id"]: it["text"] for it in items}
        previous: Dict[str, str] = {}
        with self.store.mutate(project_id) as proj:
            for s in proj.segments:
                if s.id in sources:
                    previous[s.id] = s.translation_status
                    s.translation_status, s.translation_error = "queued", None
        self.publish_project(project_id)
        done_count = {"n": 0}

        def on_start() -> None:
            with self.store.mutate(project_id, persist=False) as proj:
                for s in proj.segments:
                    if s.id in sources and s.translation_status == "queued":
                        s.translation_status = "running"
            self.set_stage(project_id, "translation", status="running", progress=0.0, message=f"Starting {info.name}…", engine=info.id)
            self.publish_project(project_id)

        def on_result(kind: str, data: Dict[str, Any]) -> None:
            if kind != "segment_translation":
                return
            with self.store.mutate(project_id, persist=False) as proj:
                try:
                    seg = proj.segment(data["id"])
                except KeyError:
                    return
                seg.translation = data["text"]
                seg.translation_status = "done"
                seg.translation_source = sources.get(seg.id, seg.text)
                index = proj.segments.index(seg)
            done_count["n"] += 1
            self._publish_segment(project_id, seg, index, "translation")

        def revert(status: str, error: Optional[str] = None) -> None:
            with self.store.mutate(project_id) as proj:
                for s in proj.segments:
                    if s.id in sources and s.translation_status in ("queued", "running"):
                        s.translation_status = "done" if previous.get(s.id) == "done" and s.translation else "pending"
            if status == "error":
                self.set_stage(project_id, "translation", status="error", error=error, message="Failed")
            else:
                self.set_stage(project_id, "translation", status="cancelled", message="Cancelled")
            self.publish_project(project_id)

        handlers = JobHandlers(
            on_start=on_start,
            on_progress=lambda v, m: self.set_stage(project_id, "translation", persist=False, progress=v, message=m),
            on_result=on_result,
            on_done=lambda d: (self.store.flush_dirty(), self.set_stage(project_id, "translation", status="done", progress=1.0, message=f"{done_count['n']} segments translated")),
            on_error=lambda e: revert("error", e),
            on_cancel=lambda: revert("cancelled"),
        )
        self.set_stage(project_id, "translation", status="queued", progress=0.0, message="Waiting for a worker…", engine=info.id, error=None)
        payload = {"items": items, "source": source, "target": target}
        return self.jobs.submit(Job(project_id, "translation", "translation", info.id, choice.params, payload, handlers))

    # ----------------------------------------------------------------- voice
    def _text_in_range(self, p: Project, start: float, end: float) -> str:
        lang = p.settings.source_language
        words = [w.text for s in p.segments for w in s.words if w.start >= start - 0.05 and w.end <= end + 0.05]
        if words:
            return languages.join_tokens(words, lang)
        return languages.join_tokens([s.text for s in p.segments if s.start < end and s.end > start], lang)

    def _voice_source(self, p: Project) -> Path:
        rel = p.source.vocals or p.source.audio_hq
        if not rel:
            raise StudioError("The source audio is not ready yet.")
        return self.store.path(p.id, rel)

    def set_voice(self, project_id: str, config: Dict[str, Any]) -> Project:
        with self.store.mutate(project_id) as p:
            v = VoiceConfig(**{**p.voice.model_dump(), **config})
            if v.mode == "preset":
                try:
                    preset = voices.get_preset(v.preset or "")
                except KeyError as exc:
                    raise StudioError(str(exc)) from exc
                message = f"Preset voice · {preset['name']}"
            elif v.mode == "clip":
                if v.clip_start is None or v.clip_end is None or v.clip_end <= v.clip_start:
                    raise StudioError("Select a start and end time for the reference clip.")
                if v.clip_end - v.clip_start > 30:
                    raise StudioError("Keep the reference clip under 30 seconds (3–12 s works best).")
                try:
                    voices.cut_reference(self._voice_source(p), v.clip_start, v.clip_end, self.store.dir(project_id) / "refs" / "clip.wav")
                except ValueError as exc:
                    raise StudioError(str(exc)) from exc
                v.ref_audio = "refs/clip.wav"
                if not config.get("ref_text"):
                    v.ref_text = self._text_in_range(p, v.clip_start, v.clip_end)
                message = f"Clip {v.clip_start:.1f}s → {v.clip_end:.1f}s from the video"
            elif v.mode == "upload":
                if not v.ref_audio:
                    raise StudioError("Upload a reference audio file first.")
                message = f"Uploaded voice · {v.upload_name or 'reference'}"
            else:
                message = "Automatic: each segment clones the original speaker"
            p.voice = v
        self.set_stage(project_id, "voice", status="done", progress=1.0, message=message)
        self.publish_project(project_id)
        return self.store.get(project_id)

    def upload_voice(
        self,
        project_id: str,
        filename: str,
        data: bytes,
        ref_text: str,
        auto_transcribe: bool = True,
        asr_engine: Optional[str] = None,
        language: Optional[str] = None,
    ) -> Project:
        project = self._store_uploaded_voice(project_id, filename, data, ref_text, language)
        if auto_transcribe and not ref_text.strip():
            self.transcribe_voice_reference(project_id, asr_engine or None, language or None)
        return project

    def _store_uploaded_voice(self, project_id: str, filename: str, data: bytes, ref_text: str, language: Optional[str]) -> Project:
        refs = self.store.dir(project_id) / "refs"
        refs.mkdir(parents=True, exist_ok=True)
        raw = refs / f"upload_raw{Path(filename).suffix.lower() or '.wav'}"
        raw.write_bytes(data)
        try:
            voices.convert_upload(raw, refs / "upload.wav")
        except Exception as exc:
            raise StudioError(f"Could not read the audio file: {exc}") from exc
        return self.set_voice(
            project_id,
            {"mode": "upload", "ref_audio": "refs/upload.wav", "ref_text": ref_text, "upload_name": filename, "ref_language": language or None, "ref_text_status": "idle"},
        )

    def _voice_resolver(self, p: Project) -> Callable[[Segment], Tuple[Optional[str], Optional[str]]]:
        v = p.voice
        if v.mode == "preset":
            preset = voices.get_preset(v.preset or "Mohamed")
            return lambda s: (preset["audio"], preset["text"])
        if v.mode in ("clip", "upload"):
            if not v.ref_audio:
                raise StudioError("Prepare the reference voice first (Voice step).")
            path = str(self.store.path(p.id, v.ref_audio))
            return lambda s: (path, v.ref_text or None)
        source = self._voice_source(p)
        total = p.source.duration or 0.0

        def auto(seg: Segment) -> Tuple[Optional[str], Optional[str]]:
            start, end = seg.start, min(seg.end, seg.start + 15.0)
            if end - start < 3.0:
                pad = (3.0 - (end - start)) / 2
                start, end = max(0.0, start - pad), min(total or end + pad, end + pad)
            out = self.store.dir(p.id) / "refs" / f"auto_{seg.id}.wav"
            voices.cut_reference(source, start, end, out)
            return str(out), self._text_in_range(p, start, end)

        return auto

    # ------------------------------------------------------------------ TTS
    @staticmethod
    def _normalize_on(info: Any, params: Dict[str, Any]) -> bool:
        if not any(spec.key == "normalize" for spec in info.params):
            return False
        return bool(params.get("normalize", True))

    def normalize_preview(self, text: str, language: str) -> Dict[str, Any]:
        """Processed text for a language, as the TTS would receive it (studio preview)."""
        normalized, error = normalize_safe(text or "", language)
        return {"language": language, "supported": language in TEXT_LANGUAGES, "text": text, "normalized": normalized, "error": error}

    def run_tts(self, project_id: str, engine: Optional[str] = None, params: Optional[Dict[str, Any]] = None, segment_ids: Optional[List[str]] = None) -> Job:
        p = self.store.get(project_id)
        choice = self._choice(project_id, "tts", engine, params)
        info = get_info(choice.engine or "")
        self._require_available(info.id)
        target = p.settings.target
        if target not in info.targets:
            raise StudioError(f"{info.name} does not support {target}.")
        wanted = set(segment_ids) if segment_ids else None
        selected = [s for s in p.segments if (wanted is None or s.id in wanted) and s.translation.strip()]
        if not selected:
            raise StudioError("Nothing to voice — translate the segments first.")
        # Gemini TTS speaks with a preset voice: no reference clip to resolve
        resolve = (lambda s: (None, None)) if info.id == "gemini-tts" else self._voice_resolver(p)
        items, texts, spoken, previous = [], {}, {}, {}
        tts_dir = self.store.dir(project_id) / "tts"
        # Normalization happens here, once, for every TTS engine (engines receive the processed text
        # and never normalize again). The processed text is stored on the clip so the UI can show it.
        normalize_on = self._normalize_on(info, choice.params)
        failures = []
        for s in selected:
            ref_audio, ref_text = resolve(s)
            if normalize_on:
                spoken[s.id], error = normalize_safe(s.translation, target)
                if error:
                    failures.append(error)
            else:
                spoken[s.id] = " ".join(s.translation.split())
            items.append({
                "id": s.id,
                "text": spoken[s.id],
                "out_path": str(tts_dir / f"{s.id}_v{s.tts.version + 1}.wav"),
                "ref_audio": ref_audio,
                "ref_text": ref_text,
                "duration": round(s.duration, 3),
            })
            texts[s.id] = s.translation
        if failures:
            self.bus.log(f"Text normalization failed for {len(failures)} segment(s), using the raw text: {failures[0]}", "warning", project_id, source="tts")
        with self.store.mutate(project_id) as proj:
            for s in proj.segments:
                if s.id in texts:
                    previous[s.id] = s.tts.status
                    s.tts.status, s.tts.error = "queued", None
        self.publish_project(project_id)
        done_count = {"n": 0, "failed": 0}
        quota: Dict[str, Any] = {}

        def on_result(kind: str, data: Dict[str, Any]) -> None:
            with self.store.mutate(project_id, persist=False) as proj:
                if kind == "tts_running":
                    changed = []
                    for sid in data.get("ids", []):
                        try:
                            seg = proj.segment(sid)
                        except KeyError:
                            continue
                        seg.tts.status = "running"
                        changed.append((seg, proj.segments.index(seg)))
                elif kind == "tts_quota":
                    # the engine hit its daily quota: keep what was generated, park the rest as pending
                    quota.update(data)
                    changed = []
                    for sid in data.get("paused", []):
                        try:
                            seg = proj.segment(sid)
                        except KeyError:
                            continue
                        if seg.tts.status in ("queued", "running"):
                            seg.tts.status = "done" if seg.tts.audio else "pending"
                            changed.append((seg, proj.segments.index(seg)))
                elif kind in ("segment_audio", "tts_error"):
                    try:
                        seg = proj.segment(data["id"])
                    except KeyError:
                        return
                    if kind == "segment_audio":
                        old = seg.tts.audio
                        new_rel = self.store.rel(project_id, data["path"])
                        if old and old != new_rel:
                            (self.store.dir(project_id) / old).unlink(missing_ok=True)
                        seg.tts = TTSState(
                            status="done",
                            audio=new_rel,
                            duration=round(float(data["duration"]), 3),
                            text=texts.get(seg.id, data.get("text")),
                            normalized=spoken.get(seg.id) if normalize_on else None,
                            engine=info.id,
                            version=seg.tts.version + 1,
                        )
                        done_count["n"] += 1
                    else:
                        seg.tts.status, seg.tts.error = "error", data.get("error")
                        done_count["failed"] += 1
                    changed = [(seg, proj.segments.index(seg))]
                else:
                    return
            for seg, index in changed:
                self._publish_segment(project_id, seg, index, "tts")

        def revert(status: str, error: Optional[str] = None) -> None:
            with self.store.mutate(project_id) as proj:
                for s in proj.segments:
                    if s.id in texts and s.tts.status in ("queued", "running"):
                        s.tts.status = "done" if s.tts.audio else "pending"
            if status == "error":
                self.set_stage(project_id, "tts", status="error", error=error, message="Failed")
            else:
                self.set_stage(project_id, "tts", status="cancelled", message="Cancelled")
            self.publish_project(project_id)

        def on_done(_: Dict[str, Any]) -> None:
            self.store.flush_dirty()
            if quota:
                p_now = self.store.get(project_id)
                voiced_total = sum(1 for s in p_now.segments if s.tts.status == "done")
                remaining = len(quota.get("paused", []))
                message = (f"{quota['message']} {done_count['n']} of {quota.get('total', len(items))} clips were generated in this run; "
                           f"the other {remaining} are paused.")
                self.set_stage(project_id, "tts", status="paused", progress=done_count["n"] / max(1, len(items)),
                               message=f"Paused · daily Gemini quota · {done_count['n']}/{len(items)} clips", error=message)
                self.bus.publish({"type": "quota", "project_id": project_id, "stage": "tts", "model": quota.get("model"),
                                  "limit": quota.get("limit"), "generated": done_count["n"], "remaining": remaining,
                                  "voiced_total": voiced_total, "message": message})
                self.publish_project(project_id)
                return
            msg = f"{done_count['n']} clips generated" + (f" · {done_count['failed']} failed" if done_count["failed"] else "")
            self.set_stage(project_id, "tts", status="done", progress=1.0, message=msg)

        handlers = JobHandlers(
            on_start=lambda: self.set_stage(project_id, "tts", status="running", progress=0.0, message=f"Starting {info.name}…", engine=info.id),
            on_progress=lambda v, m: self.set_stage(project_id, "tts", persist=False, progress=v, message=m),
            on_result=on_result,
            on_done=on_done,
            on_error=lambda e: revert("error", e),
            on_cancel=lambda: revert("cancelled"),
        )
        self.set_stage(project_id, "tts", status="queued", progress=0.0, message="Waiting for a worker…", engine=info.id, error=None)
        return self.jobs.submit(Job(project_id, "tts", "tts", info.id, choice.params, {"items": items, "target": target}, handlers))

    # ----------------------------------------------------------- separation
    def run_separation(self, project_id: str, engine: str = "demucs", params: Optional[Dict[str, Any]] = None) -> Job:
        p = self.store.get(project_id)
        if not p.source.audio_hq:
            raise StudioError("The source audio is not ready yet.")
        self._require_available(engine)
        src = self.store.dir(project_id) / "source"
        payload = {"audio": str(self.store.path(project_id, p.source.audio_hq)), "vocals_out": str(src / "vocals.wav"), "background_out": str(src / "background.wav")}

        def on_done(data: Dict[str, Any]) -> None:
            with self.store.mutate(project_id) as proj:
                proj.source.vocals, proj.source.background = "source/vocals.wav", "source/background.wav"
            self.set_stage(project_id, "separation", status="done", progress=1.0, message="Vocals and background separated")
            self.publish_project(project_id)

        handlers = JobHandlers(
            on_start=lambda: self.set_stage(project_id, "separation", status="running", progress=0.0, message="Starting Demucs…", engine=engine),
            on_progress=lambda v, m: self.set_stage(project_id, "separation", persist=False, progress=v, message=m),
            on_done=on_done,
            on_error=lambda e: self.set_stage(project_id, "separation", status="error", error=e, message="Failed"),
            on_cancel=lambda: self.set_stage(project_id, "separation", status="cancelled", message="Cancelled"),
        )
        self.set_stage(project_id, "separation", status="queued", progress=0.0, message="Waiting for a worker…", engine=engine, error=None)
        info = get_info(engine)
        return self.jobs.submit(Job(project_id, "separation", "separation", engine, {**info.defaults(), **(params or {})}, payload, handlers))

    # ---------------------------------------------------------------- render
    def render(self, project_id: str, mix: Optional[Dict[str, Any]] = None) -> None:
        if mix:
            with self.store.mutate(project_id) as p:
                p.settings.mix = MixConfig(**{**p.settings.mix.model_dump(), **mix})
        p = self.store.get(project_id)
        if p.stages.get("render", StageState()).status == "running":
            raise StudioError("A render is already running.")
        if not any(s.tts.status == "done" for s in p.segments):
            raise StudioError("Generate the dubbed audio first.")
        self.set_stage(project_id, "render", status="queued", progress=0.0, message="Queued", engine="ffmpeg", error=None)
        self.pool.submit(self._render, project_id)

    def _render(self, project_id: str) -> None:
        try:
            self.set_stage(project_id, "render", status="running", progress=0.0, message="Preparing…")
            snapshot = self.store.get(project_id).model_copy(deep=True)

            def progress(v: float, m: str) -> None:
                self._check_cancel(project_id, "render")
                self.set_stage(project_id, "render", persist=False, progress=v, message=m)

            with self.track(project_id, "render", "Mix dub + mux video", stage="render", engine="ffmpeg", clips=sum(1 for s in snapshot.segments if s.tts.status == "done")):
                result = render_project(snapshot, self.store.dir(project_id), progress)
            stats = result.pop("stats")
            with self.store.mutate(project_id) as p:
                p.render = RenderInfo(**result)
            msg = f"v{result['version']} · {stats['placed']} clips" + (f" · {stats['stretched']} sped up (max ×{stats['max_rate']})" if stats["stretched"] else "") + (f" · {stats['trimmed']} trimmed" if stats["trimmed"] else "")
            self.set_stage(project_id, "render", status="done", progress=1.0, message=msg)
            self.publish_project(project_id)
            self.align_captions(project_id)
        except Cancelled:
            self.set_stage(project_id, "render", status="cancelled", message="Cancelled")
        except Exception as exc:
            self.bus.log(traceback.format_exc(), "error", project_id, source="render")
            self.set_stage(project_id, "render", status="error", error=str(exc), message="Failed")

    # ---------------------------------------------------------------- export
    # --------------------------------------------------------------- captions
    def _estimate_dub_words(self, project_id: str) -> None:
        """Immediate dub caption timing from clip placement (refined by alignment when available)."""
        with self.store.mutate(project_id) as p:
            clips = {c["id"]: c for c in p.render.clips}
            for seg in p.segments:
                clip = clips.get(seg.id)
                if clip and seg.translation.strip():
                    words = caption_burn.estimate_words(seg.translation, clip["start"], clip["end"], p.settings.target)
                    seg.dub_words = [Word(**w) for w in words]
                else:
                    seg.dub_words = []
            p.render.captions = {"method": "estimated", "aligned": 0, "total": len(clips), "version": p.render.version}

    def align_captions(self, project_id: str) -> Optional[Job]:
        """Word-align the rendered dub voice track so dub captions highlight words as they are spoken."""
        p = self.store.get(project_id)
        if not p.render.clips or not p.render.voice:
            return None
        self._estimate_dub_words(project_id)
        self.publish_project(project_id)
        engine = "caption-align"
        available = self._available_engines()
        if available is not None and engine not in available:
            self.bus.log("wav2vec2 aligner not installed: dub captions use estimated word timing", "info", project_id, source="captions")
            self.set_stage(project_id, "captions", status="done", progress=1.0, message="Estimated word timing (aligner not installed)", engine=engine)
            return None
        texts = {s.id: s.translation for s in p.segments}
        segments = [{"id": c["id"], "start": c["start"], "end": c["end"], "text": texts.get(c["id"], "")} for c in p.render.clips if texts.get(c["id"], "").strip()]
        payload = {"audio": str(self.store.dir(project_id) / p.render.voice), "language": p.settings.target, "segments": segments}
        version = p.render.version

        def on_result(kind: str, data: Dict[str, Any]) -> None:
            if kind != "caption_words":
                return
            with self.store.mutate(project_id, persist=False) as proj:
                if proj.render.version != version:
                    return  # a newer render replaced this one
                try:
                    seg = proj.segment(data["id"])
                except KeyError:
                    return
                seg.dub_words = [Word(**w) for w in data.get("words", []) if w.get("start") is not None and w.get("end") is not None]

        def on_done(data: Dict[str, Any]) -> None:
            with self.store.mutate(project_id) as proj:
                if proj.render.version == version:
                    proj.render.captions = {"method": "aligned", "aligned": data.get("aligned", 0), "total": data.get("total", 0), "version": version}
            self.set_stage(project_id, "captions", status="done", progress=1.0, message=f"Aligned {data.get('aligned', 0)}/{data.get('total', 0)} dub clips")
            self.publish_project(project_id)

        def on_error(error: str) -> None:
            self.set_stage(project_id, "captions", status="error", error=error, message="Using estimated word timing")
            self.publish_project(project_id)

        handlers = JobHandlers(
            on_start=lambda: self.set_stage(project_id, "captions", status="running", progress=0.0, message="Aligning dub captions…", engine=engine, error=None),
            on_progress=lambda v, m: self.set_stage(project_id, "captions", persist=False, progress=v, message=m),
            on_result=on_result,
            on_done=on_done,
            on_error=on_error,
            on_cancel=lambda: self.set_stage(project_id, "captions", status="cancelled", message="Cancelled"),
        )
        self.set_stage(project_id, "captions", status="queued", progress=0.0, message="Queued", engine=engine, error=None)
        return self.jobs.submit(Job(project_id, "captions", "align", engine, {}, payload, handlers))

    # ---------------------------------------------------------------- export
    def export(self, project_id: str, directory: Optional[str] = None, captions: str = "none") -> Dict[str, Any]:
        p = self.store.get(project_id)
        if not p.render.video:
            raise StudioError("Render the dubbed video first.")
        if captions not in ("none", *caption_burn.MODES):
            raise StudioError("Captions must be none, original, dub or both.")
        dest = Path(directory).expanduser() if directory else self.settings.export_path
        try:
            dest.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StudioError(f"Cannot write to {dest}: {exc}") from exc
        with self.store.mutate(project_id) as proj:
            proj.settings.mix.burn_captions = captions  # remember the choice
        if captions == "none":
            items = self._copy_exports(project_id, dest, None, captions)
            return {"queued": False, "items": [i.model_dump() for i in items]}
        if p.stages.get("export", StageState()).status in ("running", "queued"):
            raise StudioError("An export is already running.")
        self.set_stage(project_id, "export", status="queued", progress=0.0, message="Queued", engine="ffmpeg", error=None)
        self.pool.submit(self._export_with_captions, project_id, dest, captions)
        return {"queued": True, "items": []}

    def _export_with_captions(self, project_id: str, dest: Path, captions: str) -> None:
        stage = "export"
        try:
            self.set_stage(project_id, stage, status="running", progress=0.0, message=f"Burning {captions} captions…")
            if captions in ("dub", "both"):
                # burn the word-aligned timings, not the estimates, when alignment is still running
                while self.store.get(project_id).stages.get("captions", StageState()).status in ("running", "queued"):
                    self._check_cancel(project_id, stage)
                    self.set_stage(project_id, stage, persist=False, progress=0.0, message="Waiting for dub caption alignment to finish…")
                    time.sleep(0.5)
            snapshot = self.store.get(project_id).model_copy(deep=True)

            def progress(v: float, message: str) -> None:
                self._check_cancel(project_id, stage)
                self.set_stage(project_id, stage, persist=False, progress=round(v * 0.95, 4), message=message)

            with self.track(project_id, "export", f"Burn {captions} captions into the video", stage=stage, engine="Pillow + ffmpeg"):
                burned = caption_burn.burn(snapshot, self.store.dir(project_id), captions, progress, fonts_dir=self.settings.cache_dir / "fonts",
                                           log=lambda message: self.bus.log(message, "info", project_id, source="export"))
            rel = self.store.rel(project_id, burned)
            with self.store.mutate(project_id) as proj:
                proj.render.burned = {**proj.render.burned, captions: rel}
            self.set_stage(project_id, stage, persist=False, progress=0.97, message="Copying files…")
            items = self._copy_exports(project_id, dest, rel, captions)
            self.set_stage(project_id, stage, status="done", progress=1.0, message=f"Exported {len(items)} files with {captions} captions")
        except Cancelled:
            self.set_stage(project_id, stage, status="cancelled", message="Cancelled")
        except Exception as exc:
            self.bus.log(traceback.format_exc(), "error", project_id, source="export")
            self.set_stage(project_id, stage, status="error", error=explain(exc).text(), message="Failed")

    def _copy_exports(self, project_id: str, dest: Path, video_rel: Optional[str], captions: str) -> List[ExportItem]:
        p = self.store.get(project_id)
        slug = re.sub(r"[^\w\-]+", "_", p.title, flags=re.UNICODE).strip("_")[:60] or p.id
        base = f"{slug}_dubby_{p.settings.target}_v{p.render.version}"
        pdir = self.store.dir(project_id)
        suffix = "" if captions == "none" else f"_captions-{captions}"
        plan: List[Tuple[str, Optional[str], str]] = [
            ("video" + ("" if captions == "none" else f" ({captions} captions)"), video_rel or p.render.video, f"{base}{suffix}.mp4"),
            ("audio", p.render.mix, f"{base}.wav"),
            (f"subtitles ({p.settings.target})", p.render.subtitles.get("ar_srt"), f"{base}.{p.settings.target}.srt"),
            (f"subtitles ({p.settings.source_language})", p.render.subtitles.get("src_srt"), f"{base}.{p.settings.source_language}.srt"),
        ]
        items: List[ExportItem] = []
        with self.track(project_id, "export", "Copy files to disk", stage="export", destination=str(dest)):
            for kind, rel, name in plan:
                if not rel or not (pdir / rel).exists():
                    continue
                target = dest / name
                shutil.copy2(pdir / rel, target)
                items.append(ExportItem(kind=kind, path=str(target.resolve()), rel=rel, size=target.stat().st_size))
        with self.store.mutate(project_id) as proj:
            proj.exports = items + proj.exports[:30]
        self.bus.publish({"type": "export", "project_id": project_id, "items": [i.model_dump() for i in items]})
        self.publish_project(project_id)
        return items

    # ------------------------------------------------------------------ misc
    def wait(self, project_id: str, stage: str, timeout: Optional[float] = None, poll: float = 0.5) -> StageState:
        started = time.time()
        time.sleep(poll)
        while True:
            st = self.store.get(project_id).stages.get(stage, StageState())
            if st.status in ("done", "error", "cancelled", "paused", "idle"):
                return st
            if timeout and time.time() - started > timeout:
                raise TimeoutError(f"{stage} did not finish in {timeout}s")
            time.sleep(poll)

    def shutdown(self) -> None:
        self.store.flush_dirty()
        self.jobs.shutdown()
        pot.stop()
        self.pool.shutdown(wait=False, cancel_futures=True)
