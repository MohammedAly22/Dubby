from __future__ import annotations

import asyncio
import mimetypes
import re
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

    @app.get("/api/engines")
    async def engines(refresh: bool = False):
        return await run_in_threadpool(studio.engines, refresh)

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

    @app.get("/api/logs")
    async def logs(limit: int = 300, project_id: Optional[str] = None):
        items = [e for e in studio.bus.logs if project_id is None or e.get("project_id") in (None, project_id)]
        return items[-limit:]

    # ------------------------------------------------------------ voices
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
        items = await run_in_threadpool(studio.export, pid, body.directory)
        return [i.model_dump() for i in items]

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
            await ws.send_json({"type": "hello", "jobs": studio.jobs.snapshot()})
            while not recv_task.done():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    event = {"type": "ping"}
                await ws.send_json(event)
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
