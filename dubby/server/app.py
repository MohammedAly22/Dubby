from __future__ import annotations

import asyncio
import mimetypes
import re
import traceback
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from dubby import languages, recommend
from dubby.config import save_settings
from dubby.core import voices
from dubby.core.studio import Studio, StudioError
from dubby.errors import explain

WEB_DIST = Path(__file__).resolve().parents[1] / "web" / "dist"
mimetypes.add_type("text/vtt", ".vtt")
mimetypes.add_type("application/x-subrip", ".srt")


class CreateProject(BaseModel):
    url: str
    source_language: str = "auto"
    target: str = "arz"


class RunStage(BaseModel):
    engine: Optional[str] = None
    params: Optional[Dict[str, Any]] = None
    segment_ids: Optional[List[str]] = None


class SplitBody(BaseModel):
    word_index: int


class ExportBody(BaseModel):
    directory: Optional[str] = None
    captions: str = "none"  # none | original | dub | both — burned into the video frames


class RenderBody(BaseModel):
    mix: Optional[Dict[str, Any]] = None


def _range_response(path: Path, request: Request, download: bool) -> Any:
    size = path.stat().st_size
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    headers = {"Accept-Ranges": "bytes", "Cache-Control": "no-cache"}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="{path.name}"'
    match = re.match(r"bytes=(\d*)-(\d*)", request.headers.get("range", ""))
    if not match or (not match.group(1) and not match.group(2)):
        return FileResponse(path, media_type=media_type, headers=headers)
    if match.group(1):
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else size - 1
    else:
        start, end = max(0, size - int(match.group(2))), size - 1
    end = min(end, size - 1)
    if start > end:
        return JSONResponse({"detail": "invalid range"}, status_code=416, headers={"Content-Range": f"bytes */{size}"})

    def stream():
        with open(path, "rb") as f:
            f.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                chunk = f.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    headers.update({"Content-Range": f"bytes {start}-{end}/{size}", "Content-Length": str(end - start + 1)})
    return StreamingResponse(stream(), status_code=206, media_type=media_type, headers=headers)


class GeminiKeyBody(BaseModel):
    api_key: str


class NormalizeBody(BaseModel):
    text: str
    language: str


class EngineCheck(BaseModel):
    params: Dict[str, Any] = {}
    source: Optional[str] = None
    target: Optional[str] = None


BATCH_WINDOW = 0.08  # seconds to gather events before sending one websocket frame
BATCH_MAX = 250


def collapse_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Drop superseded events. Each carries full state, so only the newest per target matters."""

    def key(e: Dict[str, Any]) -> Optional[tuple]:
        kind = e.get("type")
        if kind == "project":
            return ("project", (e.get("project") or {}).get("id"))
        if kind == "stage":
            return ("stage", e.get("project_id"), e.get("stage"))
        if kind == "segment":
            return ("segment", e.get("project_id"), (e.get("segment") or {}).get("id"))
        if kind == "download":
            return ("download", e.get("id"))
        if kind == "request":
            return ("request", e.get("id"))
        if kind in ("jobs", "engines"):
            return (kind,)
        return None  # logs, exports, … are all kept

    seen: Set[tuple] = set()
    keep: List[Dict[str, Any]] = []
    for e in reversed(events):
        k = key(e)
        if k is not None:
            if k in seen:
                continue
            seen.add(k)
        keep.append(e)
    keep.reverse()
    return keep


def create_app(studio: Studio) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        studio.bus.bind_loop(asyncio.get_running_loop())
        studio.pool.submit(studio.engine_status, True)
        yield
        studio.shutdown()

    app = FastAPI(title="Dubby 🐨", version="0.1.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(StudioError)
    async def studio_error(_: Request, exc: StudioError):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(KeyError)
    async def not_found(_: Request, exc: KeyError):
        return JSONResponse({"detail": f"Not found: {exc}"}, status_code=404)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception):
        # Never hand the browser a bare "Internal Server Error": log the traceback, explain the cause.
        studio.bus.log(f"{request.method} {request.url.path} failed:\n{traceback.format_exc()}", "error", source="api")
        return JSONResponse({"detail": explain(exc).text()}, status_code=500)

    # ------------------------------------------------------------ system
    @app.get("/api/system")
    async def system():
        return await run_in_threadpool(studio.system)

    @app.get("/api/settings")
    async def get_settings():
        return studio.settings.public()

    @app.put("/api/settings")
    async def put_settings(body: Dict[str, Any]):
        settings = save_settings(body)
        studio.apply_settings(settings)
        return settings.public()

    @app.post("/api/settings/cookies")
    async def upload_cookies(file: UploadFile = File(...)):
        data = await file.read()
        return (await run_in_threadpool(studio.save_cookies, data)).public()

    @app.delete("/api/settings/cookies")
    async def delete_cookies():
        return (await run_in_threadpool(studio.remove_cookies)).public()

    @app.get("/api/engines")
    async def engines(refresh: bool = False):
        return await run_in_threadpool(studio.engines, refresh)

    @app.post("/api/engines/{engine_id}/check")
    async def check_engine(engine_id: str, body: EngineCheck):
        return await run_in_threadpool(studio.check_engine, engine_id, body.params, body.source, body.target)

    @app.post("/api/normalize")
    async def normalize_text(body: NormalizeBody):
        """Preview the processed text the TTS would receive for a dub language."""
        return studio.normalize_preview(body.text, body.language)

    @app.get("/api/languages")
    async def get_languages():
        return {**languages.public(), "recommendations": recommend.matrix()}

    @app.get("/api/jobs")
    async def jobs():
        return studio.jobs.snapshot()

    @app.post("/api/workers/stop")
    async def stop_workers():
        await run_in_threadpool(studio.jobs.stop_workers)
        return studio.jobs.snapshot()

    @app.get("/api/requests")
    async def list_requests(limit: int = 1000):
        return list(studio.bus.requests.values())[-limit:]

    @app.delete("/api/requests")
    async def clear_requests():
        studio.bus.clear_requests()
        return {"ok": True}

    @app.get("/api/logs")
    async def logs(limit: int = 300, project_id: Optional[str] = None):
        items = [e for e in studio.bus.logs if project_id is None or e.get("project_id") in (None, project_id)]
        return items[-limit:]

    @app.get("/api/console")
    async def console_lines(limit: int = 1000):
        return list(studio.bus.console_lines)[-limit:]

    @app.delete("/api/console")
    async def clear_console():
        studio.bus.console_lines.clear()
        return {"ok": True}

    # ------------------------------------------------------------ voices
    @app.post("/api/settings/gemini")
    async def save_gemini_key(body: GeminiKeyBody):
        """Validate the key with one tiny request and save it only when it works."""
        return await run_in_threadpool(studio.save_gemini_key, body.api_key)

    @app.delete("/api/settings/gemini")
    async def remove_gemini_key():
        return (await run_in_threadpool(studio.remove_gemini_key)).public()

    @app.get("/api/gemini/voices")
    async def gemini_voices():
        from dubby.engines.tts.gemini_tts import VOICES

        return [{"name": name, "style": style, "gender": gender} for name, style, gender in VOICES]

    @app.get("/api/gemini/voices/{voice}/preview")
    async def gemini_voice_preview(voice: str, request: Request, language: str = "en"):
        path = await run_in_threadpool(studio.gemini_voice_preview, voice, language)
        return _range_response(path, request, False)

    @app.get("/api/voices/presets")
    async def presets():
        try:
            items = await run_in_threadpool(voices.list_presets)
        except Exception as exc:
            raise HTTPException(503, f"Could not fetch preset voices: {exc}")
        return [{k: v for k, v in p.items() if k != "audio"} for p in items]

    @app.get("/api/voices/presets/{name}/audio")
    async def preset_audio(name: str, request: Request):
        preset = await run_in_threadpool(voices.get_preset, name)
        return _range_response(Path(preset["audio"]), request, False)

    # ------------------------------------------------------------ projects
    @app.get("/api/projects")
    async def list_projects():
        return [p.summary() for p in studio.store.list()]

    @app.post("/api/projects")
    async def create_project(body: CreateProject):
        p = await run_in_threadpool(studio.create_project, body.url, body.source_language, body.target)
        return p.model_dump()

    @app.post("/api/projects/upload")
    async def upload_project(file: UploadFile = File(...), source_language: str = Form("auto"), target: str = Form("arz")):
        data = await file.read()
        p = await run_in_threadpool(studio.create_project_from_file, file.filename or "video.mp4", data, source_language, target)
        return p.model_dump()

    @app.post("/api/projects/{pid}/source/upload")
    async def replace_source(pid: str, file: UploadFile = File(...)):
        data = await file.read()
        return (await run_in_threadpool(studio.replace_source_with_file, pid, file.filename or "video.mp4", data)).model_dump()

    @app.get("/api/projects/{pid}")
    async def get_project(pid: str):
        return studio.store.get(pid).model_dump()

    @app.delete("/api/projects/{pid}")
    async def delete_project(pid: str):
        await run_in_threadpool(studio.delete_project, pid)
        return {"ok": True}

    @app.patch("/api/projects/{pid}/settings")
    async def patch_settings(pid: str, body: Dict[str, Any]):
        return (await run_in_threadpool(studio.update_settings, pid, body)).model_dump()

    @app.patch("/api/projects/{pid}/segments/{sid}")
    async def patch_segment(pid: str, sid: str, body: Dict[str, Any]):
        return (await run_in_threadpool(studio.update_segment, pid, sid, body)).model_dump()

    @app.post("/api/projects/{pid}/segments/{sid}/merge")
    async def merge_segment(pid: str, sid: str):
        return (await run_in_threadpool(studio.merge_segment, pid, sid)).model_dump()

    @app.post("/api/projects/{pid}/segments/{sid}/split")
    async def split_segment(pid: str, sid: str, body: SplitBody):
        return (await run_in_threadpool(studio.split_segment, pid, sid, body.word_index)).model_dump()

    @app.delete("/api/projects/{pid}/segments/{sid}")
    async def delete_segment(pid: str, sid: str):
        return (await run_in_threadpool(studio.delete_segment, pid, sid)).model_dump()

    @app.post("/api/projects/{pid}/stages/{stage}/run")
    async def run_stage(pid: str, stage: str, body: RunStage):
        return await run_in_threadpool(studio.run_stage, pid, stage, body.engine, body.params, body.segment_ids)

    @app.post("/api/projects/{pid}/stages/{stage}/cancel")
    async def cancel_stage(pid: str, stage: str):
        return await run_in_threadpool(studio.cancel, pid, stage)

    @app.put("/api/projects/{pid}/voice")
    async def put_voice(pid: str, body: Dict[str, Any]):
        return (await run_in_threadpool(studio.set_voice, pid, body)).model_dump()

    @app.post("/api/projects/{pid}/voice/upload")
    async def upload_voice(
        pid: str,
        file: UploadFile = File(...),
        ref_text: str = Form(""),
        auto_transcribe: bool = Form(True),
        asr_engine: str = Form(""),
        language: str = Form(""),
    ):
        data = await file.read()
        project = await run_in_threadpool(studio.upload_voice, pid, file.filename or "voice.wav", data, ref_text, auto_transcribe, asr_engine or None, language or None)
        return project.model_dump()

    @app.post("/api/projects/{pid}/voice/transcribe")
    async def transcribe_voice(pid: str, body: Dict[str, Any]):
        await run_in_threadpool(studio.transcribe_voice_reference, pid, body.get("engine") or None, body.get("language") or None, body.get("params"))
        return {"ok": True}

    @app.post("/api/projects/{pid}/detect-language")
    async def detect_language(pid: str, body: RunStage):
        await run_in_threadpool(studio.run_langid, pid, body.engine or "whisper-langid", body.params)
        return {"ok": True}

    @app.post("/api/projects/{pid}/recommendations/apply")
    async def apply_recommendations(pid: str, body: Dict[str, Any]):
        stages = tuple(body.get("stages") or ("asr", "translation", "tts"))
        return (await run_in_threadpool(studio.apply_recommendations, pid, stages)).model_dump()

    @app.post("/api/projects/{pid}/render")
    async def render(pid: str, body: RenderBody):
        await run_in_threadpool(studio.render, pid, body.mix)
        return {"ok": True}

    @app.post("/api/projects/{pid}/export")
    async def export(pid: str, body: ExportBody):
        """Copies the render to disk; with captions the burn runs in the background (stage "export")."""
        return await run_in_threadpool(studio.export, pid, body.directory, body.captions)

    @app.post("/api/projects/{pid}/captions/align")
    async def align_captions(pid: str):
        job = await run_in_threadpool(studio.align_captions, pid)
        return {"queued": job is not None}

    @app.get("/api/projects/{pid}/files/{rel:path}")
    async def project_file(pid: str, rel: str, request: Request, download: bool = False):
        try:
            path = studio.store.path(pid, rel)
        except ValueError:
            raise HTTPException(403, "forbidden")
        if not path.is_file():
            raise HTTPException(404, "file not found")
        return _range_response(path, request, download)

    # ------------------------------------------------------------ realtime
    @app.websocket("/api/ws")
    async def websocket(ws: WebSocket):
        await ws.accept()
        queue = studio.bus.open_queue()

        async def receiver():
            try:
                while True:
                    await ws.receive_text()
            except Exception:
                return

        recv_task = asyncio.create_task(receiver())
        try:
            await ws.send_json({
                "type": "hello",
                "jobs": studio.jobs.snapshot(),
                "downloads": list(studio.bus.downloads.values()),
                "requests": list(studio.bus.requests.values())[-500:],
                "console": list(studio.bus.console_lines)[-1000:],
            })
            while not recv_task.done():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    await ws.send_json({"type": "ping"})
                    continue
                # Coalesce the burst that follows into one frame: far fewer round trips over the
                # Colab proxy, and one React render instead of dozens.
                batch = [event]
                await asyncio.sleep(BATCH_WINDOW)
                while len(batch) < BATCH_MAX:
                    try:
                        batch.append(queue.get_nowait())
                    except asyncio.QueueEmpty:
                        break
                batch = collapse_events(batch)
                await ws.send_json(batch[0] if len(batch) == 1 else {"type": "batch", "events": batch})
        except Exception:
            pass
        finally:
            studio.bus.close_queue(queue)
            recv_task.cancel()

    # ------------------------------------------------------------ web UI
    if (WEB_DIST / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        candidate = WEB_DIST / full_path
        if full_path and candidate.is_file() and WEB_DIST in candidate.resolve().parents:
            return FileResponse(candidate)
        index = WEB_DIST / "index.html"
        if index.exists():
            return FileResponse(index)
        return HTMLResponse(
            "<body style='background:#000;color:#fff;font-family:system-ui;padding:40px'>"
            "<h1>Dubby 🐨</h1><p>The web UI is not built yet. Run <code>dubby build-ui</code> and reload.</p></body>"
        )

    return app
