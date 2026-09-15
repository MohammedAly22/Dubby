"""``dubby`` command line: serve the studio, build the UI, check engines, dub headlessly."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Any, Dict, List

from rich.table import Table
from rich.text import Text

from dubby import __version__
from dubby.config import ENGINE_FAMILIES, load_settings
from dubby.core.reporter import TerminalReporter, banner, console
from dubby.languages import SOURCE_CODES, TARGET_CODES

ROOT = Path(__file__).resolve().parents[1]
UI_DIR = ROOT / "ui"
WEB_DIST = Path(__file__).resolve().parent / "web" / "dist"


def _coerce(value: str) -> Any:
    low = value.lower()
    if low in ("true", "false"):
        return low == "true"
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _params(pairs: List[str] | None) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for pair in pairs or []:
        key, _, value = pair.partition("=")
        out[key.strip()] = _coerce(value.strip())
    return out


# ----------------------------------------------------------------------- serve
def cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn

    from dubby.core.studio import Studio
    from dubby.server.app import create_app

    settings = load_settings()
    host, port = args.host or settings.host, args.port or settings.port
    studio = Studio(settings)
    studio.bus.subscribe(TerminalReporter(verbose=args.verbose))
    banner(host, port, {"Home": settings.home, "Device": settings.resolved_device(), "Node": settings.resolved_node() or "not found"})
    if not (WEB_DIST / "index.html").exists():
        console.print(Text("  ⚠️  Web UI not built — run `dubby build-ui` (needs Node.js).", style="yellow"))
    if args.open:
        threading.Timer(1.5, lambda: webbrowser.open(f"http://{'127.0.0.1' if host in ('0.0.0.0', '::') else host}:{port}")).start()
    uvicorn.run(create_app(studio), host=host, port=port, log_level="warning")


# ------------------------------------------------------------------------- dev
def cmd_dev(args: argparse.Namespace) -> None:
    """Backend + Vite dev server (hot reload) in one terminal."""
    import uvicorn

    from dubby.core.studio import Studio
    from dubby.server.app import create_app

    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if not npm:
        console.print("[red]npm not found. Install Node.js ≥ 22 (conda install -c conda-forge nodejs).[/red]")
        sys.exit(1)
    settings = load_settings()
    port = args.port or settings.port
    if not (UI_DIR / "node_modules").exists():
        console.print(Text("  $ npm install", style="grey62"))
        subprocess.call([npm, "install", "--no-fund", "--no-audit"], cwd=UI_DIR, shell=os.name == "nt")

    studio = Studio(settings)
    studio.bus.subscribe(TerminalReporter(verbose=args.verbose))
    banner("127.0.0.1", port, {"Dev UI": "http://localhost:5173  (hot reload)", "Home": settings.home, "Device": settings.resolved_device()})
    env = {**os.environ, "DUBBY_PORT": str(port)}
    vite = subprocess.Popen([npm, "run", "dev"], cwd=UI_DIR, env=env, shell=os.name == "nt")
    if args.open:
        threading.Timer(3.0, lambda: webbrowser.open("http://localhost:5173")).start()
    try:
        uvicorn.run(create_app(studio), host="127.0.0.1", port=port, log_level="warning")
    finally:
        if vite.poll() is None:
            if os.name == "nt":
                subprocess.call(["taskkill", "/F", "/T", "/PID", str(vite.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                vite.terminate()


# -------------------------------------------------------------------- build-ui
def cmd_build_ui(args: argparse.Namespace) -> None:
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if not npm:
        console.print("[red]npm not found. Install Node.js ≥ 22 (conda install -c conda-forge nodejs).[/red]")
        sys.exit(1)
    if not UI_DIR.exists():
        console.print(f"[red]UI sources not found at {UI_DIR}[/red]")
        sys.exit(1)
    console.rule(Text(" 🧱 Building the Dubby web UI ", style="bold white"), style="grey35")
    install = ["ci"] if (UI_DIR / "package-lock.json").exists() and not args.fresh else ["install"]
    for step in (install, ["run", "build"]):
        console.print(Text(f"  $ npm {' '.join(step)}", style="grey62"))
        code = subprocess.call([npm, *step, "--no-fund", "--no-audit"] if step[0] in ("ci", "install") else [npm, *step], cwd=UI_DIR, shell=os.name == "nt")
        if code != 0:
            console.print(f"[red]npm {' '.join(step)} failed with code {code}[/red]")
            sys.exit(code)
    console.print(Text(f"  ✅ UI built → {WEB_DIST}", style="bold green"))


# ---------------------------------------------------------------------- doctor
def cmd_doctor(args: argparse.Namespace) -> None:
    from dubby.core.jobs import run_doctor
    from dubby.engines.registry import all_infos

    settings = load_settings()
    banner(extra={"Home": settings.home})
    tools = Table(title="🧰 Tools", border_style="grey35", header_style="bold white", title_style="bold white")
    tools.add_column("tool")
    tools.add_column("path")
    for name, path in (("ffmpeg", shutil.which("ffmpeg")), ("ffprobe", shutil.which("ffprobe")), ("node", settings.resolved_node()), ("npm", shutil.which("npm"))):
        tools.add_row(name, Text(path or "missing", style="green" if path else "red"))
    console.print(tools)

    families = {f: run_doctor(settings, f) for f in ENGINE_FAMILIES}
    fam_table = Table(title="🐍 Engine families", border_style="grey35", header_style="bold white", title_style="bold white")
    for col in ("family", "python", "torch", "device"):
        fam_table.add_column(col)
    for f, rep in families.items():
        torch = rep.get("torch") or {}
        fam_table.add_row(f, rep.get("python", "?"), str(torch.get("version", rep.get("error", "—"))), str(torch.get("device", "—")))
    console.print(fam_table)

    table = Table(title="🧩 Engines", border_style="grey35", header_style="bold white", title_style="bold white")
    for col in ("kind", "engine", "family", "status", "install"):
        table.add_column(col)
    for info in all_infos():
        entry = families.get(info.family, {}).get("engines", {}).get(info.id)
        ok = bool(entry and entry.get("available"))
        status = Text("ready", style="bold green") if ok else Text("missing: " + ", ".join((entry or {}).get("missing", info.requires)), style="yellow")
        table.add_row(info.kind, f"{info.name} ({info.id})", info.family, status, "" if ok else info.install)
    console.print(table)
    if args.json:
        console.print_json(json.dumps(families))


# --------------------------------------------------------------------- engines
def cmd_engines(_: argparse.Namespace) -> None:
    from dubby.engines.registry import all_infos

    table = Table(title="🧩 Dubby engines", border_style="grey35", header_style="bold white", title_style="bold white", show_lines=True)
    for col in ("kind", "id", "name", "family", "languages", "description"):
        table.add_column(col, overflow="fold")
    for info in all_infos():
        langs = ", ".join(info.source_languages + [f"→{t}" for t in info.targets])
        table.add_row(info.kind, info.id, info.name, info.family, langs, info.description)
    console.print(table)


# ------------------------------------------------------------------- languages
def cmd_languages(_: argparse.Namespace) -> None:
    from dubby import languages as L
    from dubby import recommend

    table = Table(title="🌍 Languages & recommended engines", border_style="grey35", header_style="bold white", title_style="bold white", show_lines=True)
    for col in ("code", "language", "spoken", "dub", "ASR (spoken)", "TTS (dub)", "OmniVoice data"):
        table.add_column(col, overflow="fold")
    for lang in L.LANGUAGES.values():
        asr = " › ".join(r.engine for r in recommend.recommendations("asr", lang.code, "en")) if lang.source else "—"
        tts = " › ".join(r.engine for r in recommend.recommendations("tts", "en", lang.code)) if lang.target else "—"
        table.add_row(lang.code, f"{lang.name} · {lang.native}", "✓" if lang.source else "", "✓" if lang.target else "", asr, tts, f"{lang.omnivoice_hours:,.0f} h")
    console.print(table)
    pairs = Table(title="🔁 Translation (top pick per pair from English)", border_style="grey35", header_style="bold white", title_style="bold white")
    pairs.add_column("pair")
    pairs.add_column("ranked engines")
    for tgt in L.TARGET_CODES:
        pairs.add_row(f"en → {tgt}", " › ".join(r.engine for r in recommend.recommendations("translation", "en", tgt)))
    console.print(pairs)


# -------------------------------------------------------------------- projects
def cmd_projects(_: argparse.Namespace) -> None:
    from dubby.core.storage import ProjectStore

    settings = load_settings()
    table = Table(title="🎞️  Projects", border_style="grey35", header_style="bold white", title_style="bold white")
    for col in ("id", "title", "segments", "translated", "voiced", "render"):
        table.add_column(col)
    for p in ProjectStore(settings.projects_dir).list():
        s = p.summary()
        table.add_row(p.id, p.title[:50], str(s["segments"]), str(s["translated"]), str(s["voiced"]), f"v{p.render.version}" if p.render.video else "—")
    console.print(table)


# ------------------------------------------------------------------------- dub
def cmd_dub(args: argparse.Namespace) -> None:
    from dubby.core.studio import Studio, StudioError

    settings = load_settings()
    studio = Studio(settings)
    studio.bus.subscribe(TerminalReporter(verbose=args.verbose))
    banner(extra={"Source": args.url, "Target": args.target, "Device": settings.resolved_device()})

    def check(stage: str) -> None:
        st = studio.wait(project.id, stage)
        if st.status != "done":
            studio.shutdown()
            console.print(f"[red]{stage} did not complete: {st.error or st.status}[/red]")
            sys.exit(1)

    try:
        if Path(args.url).exists():
            project = studio.create_project_from_file(Path(args.url).name, Path(args.url).read_bytes(), args.source, args.target)
        else:
            project = studio.create_project(args.url, args.source, args.target)
        check("download")
        if args.source == "auto":
            check("langid")
        settings = studio.store.get(project.id).settings
        console.print(
            Text("  🧭 Engines  ", style="grey62")
            + Text(f"ASR {args.asr or settings.asr.engine} · translation {args.translation or settings.translation.engine} · TTS {args.tts or settings.tts.engine}", style="bold white")
        )
        studio.run_asr(project.id, args.asr, _params(args.asr_param))
        check("asr")
        studio.run_translation(project.id, args.translation, _params(args.translation_param))
        check("translation")
        mode, _, value = args.voice.partition(":")
        if mode == "preset":
            studio.set_voice(project.id, {"mode": "preset", "preset": value or "Mohamed"})
        elif mode == "clip":
            a, _, b = value.partition("-")
            studio.set_voice(project.id, {"mode": "clip", "clip_start": float(a), "clip_end": float(b)})
        elif mode == "file":
            studio.upload_voice(project.id, Path(value).name, Path(value).read_bytes(), args.ref_text or "")
        else:
            studio.set_voice(project.id, {"mode": "auto"})
        studio.run_tts(project.id, args.tts, _params(args.tts_param))
        check("tts")
        studio.render(project.id)
        check("render")
        items = studio.export(project.id, args.export)
        for item in items:
            console.print(Text(f"  📦 {item.kind:<16}", style="grey62") + Text(item.path, style="bold white"))
    except StudioError as exc:
        console.print(f"[red]❌ {exc}[/red]")
        sys.exit(1)
    finally:
        studio.shutdown()


def main(argv: List[str] | None = None) -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # emoji & Arabic on Windows terminals
    except AttributeError:
        pass
    # Keep the studio terminal readable: Dubby reports progress itself.
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
    parser = argparse.ArgumentParser(prog="dubby", description="Dubby 🐨 — YouTube dubbing studio")
    parser.add_argument("--version", action="version", version=f"dubby {__version__}")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("serve", help="start the studio web app")
    p.add_argument("--host")
    p.add_argument("--port", type=int)
    p.add_argument("--open", action=argparse.BooleanOptionalAction, default=True, help="open the browser")
    p.add_argument("-v", "--verbose", action="store_true", help="show raw worker output")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("dev", help="run the backend and the Vite dev UI together (hot reload)")
    p.add_argument("--port", type=int)
    p.add_argument("--open", action=argparse.BooleanOptionalAction, default=True, help="open the browser")
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(func=cmd_dev)

    p = sub.add_parser("build-ui", help="build the web UI with npm")
    p.add_argument("--fresh", action="store_true", help="npm install instead of npm ci")
    p.set_defaults(func=cmd_build_ui)

    p = sub.add_parser("doctor", help="check tools, interpreters and engines")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_doctor)

    sub.add_parser("engines", help="list engines").set_defaults(func=cmd_engines)
    sub.add_parser("languages", help="supported languages and recommended engines").set_defaults(func=cmd_languages)
    sub.add_parser("projects", help="list projects").set_defaults(func=cmd_projects)

    p = sub.add_parser("dub", help="dub a video end-to-end without the UI")
    p.add_argument("url", help="YouTube URL or local video file")
    p.add_argument("--source", default="auto", choices=["auto", *SOURCE_CODES], help="spoken language (auto = detect)")
    p.add_argument("--target", default="arz", choices=list(TARGET_CODES), help="dub language")
    p.add_argument("--asr", default=None, help="ASR engine (default: recommended for the language)")
    p.add_argument("--asr-param", action="append", metavar="KEY=VALUE")
    p.add_argument("--translation", default=None, help="translation engine (default: recommended)")
    p.add_argument("--translation-param", action="append", metavar="KEY=VALUE")
    p.add_argument("--tts", default=None, help="TTS engine (default: recommended)")
    p.add_argument("--tts-param", action="append", metavar="KEY=VALUE")
    p.add_argument("--voice", default="preset:Mohamed", help="preset:NAME | auto | clip:START-END | file:PATH")
    p.add_argument("--ref-text", default="", help="transcript of the file: voice")
    p.add_argument("--export", help="export directory")
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(func=cmd_dub)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return
    try:
        args.func(args)
    except KeyboardInterrupt:
        console.print("\n[grey62]Bye 🐨[/grey62]")
