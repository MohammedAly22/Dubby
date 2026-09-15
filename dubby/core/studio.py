"""The Studio: orchestrates projects, stages, workers and events.

Both the web server and the CLI drive the pipeline exclusively through this class.
"""

from __future__ import annotations

import re
import shutil
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

from dubby.config import ENGINE_FAMILIES, Settings, load_settings
from dubby.core import voices
from dubby.core.events import EventBus
from dubby.core.jobs import Job, JobHandlers, JobManager, run_doctor
from dubby.core.storage import ProjectStore
from dubby.engines.registry import all_infos, get_info
from dubby.media import ffmpeg, youtube
from dubby.pipeline.chunking import fill_word_times, split_segment_words
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
        self.jobs = JobManager(self.settings, self.bus)
        self.pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="dubby-cpu")
        self._engine_status: Dict[str, Any] = {}
        self._status_lock = threading.Lock()
        self._cancel_flags: Set[Tuple[str, str]] = set()
        self._recover()
        threading.Thread(target=self._saver, daemon=True, name="dubby-saver").start()

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
        with self.store.mutate(project_id, persist=persist) as p:
            st = p.stages.setdefault(stage, StageState())
            status = changes.get("status")
            if status == "running" and st.status != "running":
                st.started_at, st.finished_at, st.error = time.time(), None, None
            if status in ("done", "error", "cancelled"):
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
            return current.model_copy(deep=True)

    def _require_available(self, engine_id: str) -> None:
        status = self.engine_status()
        info = get_info(engine_id)
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
        infos = []
        for info in all_infos():
            d = info.to_dict()
            fam = status.get(info.family, {})
            entry = fam.get("engines", {}).get(info.id)
            d["available"] = bool(entry and entry.get("available"))
            d["missing"] = entry.get("missing", []) if entry else info.requires
            d["family_error"] = fam.get("error")
            infos.append(d)
        return {"engines": infos, "families": status}

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
        self.settings = settings
        self.jobs.settings = settings
        for w in self.jobs.workers.values():
            w.settings = settings
        self.pool.submit(self.engine_status, True)

    # ================================================================ projects
    def create_project(self, url: str, source_language: str = "en", target: str = "arz") -> Project:
        url = (url or "").strip()
        if not YOUTUBE_RE.match(url):
            raise StudioError("Please paste a valid YouTube link (youtube.com or youtu.be).")
        p = self.store.create(title="YouTube video")
        with self.store.mutate(p.id) as proj:
            proj.source.kind, proj.source.url = "youtube", url
            proj.settings = ProjectSettings(source_language=source_language, target=target)
            if source_language == "ar":
                proj.settings.asr = EngineChoice(engine="cohere-transcribe-arabic")
        self.publish_project(p.id)
        self.bus.log(f"New project {p.id} ← {url}", project_id=p.id)
        self.pool.submit(self._prepare_source, p.id)
        return self.store.get(p.id)

    def create_project_from_file(self, filename: str, data: bytes, source_language: str = "en", target: str = "arz") -> Project:
        p = self.store.create(title=Path(filename).stem)
        ext = Path(filename).suffix.lower() or ".mp4"
        dest = self.store.dir(p.id) / "source" / f"upload{ext}"
        dest.write_bytes(data)
        with self.store.mutate(p.id) as proj:
            proj.source.kind, proj.source.video, proj.title = "upload", f"source/{dest.name}", Path(filename).stem
            proj.settings = ProjectSettings(source_language=source_language, target=target)
        self.publish_project(p.id)
        self.pool.submit(self._prepare_source, p.id)
        return self.store.get(p.id)

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
                meta = youtube.download(p.source.url or "", src_dir, self.settings, progress)
                video = Path(meta["video"])
            else:
                video = self.store.path(project_id, p.source.video or "")
            self.set_stage(project_id, stage, persist=False, progress=0.87, message="Checking video codec…")
            video = ffmpeg.ensure_browser_video(video)
            self._check_cancel(project_id, stage)
            self.set_stage(project_id, stage, persist=False, progress=0.92, message="Extracting 16 kHz speech track…")
            a16 = ffmpeg.extract_audio(video, src_dir / "audio_16k.wav", 16000, 1)
            self.set_stage(project_id, stage, persist=False, progress=0.96, message="Extracting 44.1 kHz mix track…")
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
            self.set_stage(project_id, stage, status="done", progress=1.0, message=f"{title} · {int(duration // 60)}m{int(duration % 60):02d}s")
            self.publish_project(project_id)
        except Cancelled:
            self.set_stage(project_id, stage, status="cancelled", message="Cancelled")
        except Exception as exc:
            self.bus.log(traceback.format_exc(), "error", project_id, source="download")
            self.set_stage(project_id, stage, status="error", error=str(exc), message="Failed")

    def update_settings(self, project_id: str, patch: Dict[str, Any]) -> Project:
        with self.store.mutate(project_id) as p:
            merged = _deep_merge(p.settings.model_dump(), patch)
            p.settings = ProjectSettings.model_validate(merged)
        self.publish_project(project_id)
        return self.store.get(project_id)

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
                text = " ".join(str(patch["text"]).split())
                tokens = text.split(" ")
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
            merged = Segment(
                id=seg.id,
                start=seg.start,
                end=nxt.end,
                text=f"{seg.text} {nxt.text}".strip(),
                words=seg.words + nxt.words,
                translation=f"{seg.translation} {nxt.translation}".strip() if both_translated else "",
                translation_status="done" if both_translated else "pending",
                translation_source=f"{seg.text} {nxt.text}".strip() if both_translated else None,
            )
            p.segments[i:i + 2] = [merged]
        self.publish_project(project_id)
        return self.store.get(project_id)

    def split_segment(self, project_id: str, seg_id: str, word_index: int) -> Project:
        with self.store.mutate(project_id) as p:
            seg = p.segment(seg_id)
            i = p.segments.index(seg)
            try:
                parts = split_segment_words(seg.model_dump(), int(word_index))
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
        if stage in ("download", "render"):
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
            "chunking": {"max_seconds": p.settings.max_chunk_seconds, "min_seconds": p.settings.min_chunk_seconds, "max_gap": p.settings.max_word_gap},
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
        if source not in info.source_languages or target not in info.targets:
            raise StudioError(f"{info.name} cannot translate {source} → {target}.")
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
        words = [w.text for s in p.segments for w in s.words if w.start >= start - 0.05 and w.end <= end + 0.05]
        if words:
            return " ".join(words)
        return " ".join(s.text for s in p.segments if s.start < end and s.end > start)

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

    def upload_voice(self, project_id: str, filename: str, data: bytes, ref_text: str) -> Project:
        refs = self.store.dir(project_id) / "refs"
        refs.mkdir(parents=True, exist_ok=True)
        raw = refs / f"upload_raw{Path(filename).suffix.lower() or '.wav'}"
        raw.write_bytes(data)
        try:
            voices.convert_upload(raw, refs / "upload.wav")
        except Exception as exc:
            raise StudioError(f"Could not read the audio file: {exc}") from exc
        return self.set_voice(project_id, {"mode": "upload", "ref_audio": "refs/upload.wav", "ref_text": ref_text, "upload_name": filename})

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
        resolve = self._voice_resolver(p)
        items, texts, previous = [], {}, {}
        tts_dir = self.store.dir(project_id) / "tts"
        for s in selected:
            ref_audio, ref_text = resolve(s)
            items.append({
                "id": s.id,
                "text": s.translation,
                "out_path": str(tts_dir / f"{s.id}_v{s.tts.version + 1}.wav"),
                "ref_audio": ref_audio,
                "ref_text": ref_text,
                "duration": round(s.duration, 3),
            })
            texts[s.id] = s.translation
        with self.store.mutate(project_id) as proj:
            for s in proj.segments:
                if s.id in texts:
                    previous[s.id] = s.tts.status
                    s.tts.status, s.tts.error = "queued", None
        self.publish_project(project_id)
        done_count = {"n": 0, "failed": 0}

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
                        seg.tts = TTSState(status="done", audio=new_rel, duration=round(float(data["duration"]), 3), text=data.get("text", texts.get(seg.id)), engine=info.id, version=seg.tts.version + 1)
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

            result = render_project(snapshot, self.store.dir(project_id), progress)
            stats = result.pop("stats")
            with self.store.mutate(project_id) as p:
                p.render = RenderInfo(**result)
            msg = f"v{result['version']} · {stats['placed']} clips" + (f" · {stats['stretched']} sped up (max ×{stats['max_rate']})" if stats["stretched"] else "") + (f" · {stats['trimmed']} trimmed" if stats["trimmed"] else "")
            self.set_stage(project_id, "render", status="done", progress=1.0, message=msg)
            self.publish_project(project_id)
        except Cancelled:
            self.set_stage(project_id, "render", status="cancelled", message="Cancelled")
        except Exception as exc:
            self.bus.log(traceback.format_exc(), "error", project_id, source="render")
            self.set_stage(project_id, "render", status="error", error=str(exc), message="Failed")

    # ---------------------------------------------------------------- export
    def export(self, project_id: str, directory: Optional[str] = None) -> List[ExportItem]:
        p = self.store.get(project_id)
        if not p.render.video:
            raise StudioError("Render the dubbed video first.")
        dest = Path(directory).expanduser() if directory else self.settings.export_path
        try:
            dest.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StudioError(f"Cannot write to {dest}: {exc}") from exc
        slug = re.sub(r"[^\w\-]+", "_", p.title, flags=re.UNICODE).strip("_")[:60] or p.id
        base = f"{slug}_dubby_{p.settings.target}_v{p.render.version}"
        pdir = self.store.dir(project_id)
        plan: Iterable[Tuple[str, Optional[str], str]] = [
            ("video", p.render.video, f"{base}.mp4"),
            ("audio", p.render.mix, f"{base}.wav"),
            ("subtitles (ar)", p.render.subtitles.get("ar_srt"), f"{base}.ar.srt"),
            (f"subtitles ({p.settings.source_language})", p.render.subtitles.get("src_srt"), f"{base}.{p.settings.source_language}.srt"),
        ]
        items: List[ExportItem] = []
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
            if st.status in ("done", "error", "cancelled", "idle"):
                return st
            if timeout and time.time() - started > timeout:
                raise TimeoutError(f"{stage} did not finish in {timeout}s")
            time.sleep(poll)

    def shutdown(self) -> None:
        self.store.flush_dirty()
        self.jobs.shutdown()
        self.pool.shutdown(wait=False, cancel_futures=True)
