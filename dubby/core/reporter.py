"""Rich terminal reporter: turns studio events into a readable live log."""

from __future__ import annotations

import time
from typing import Any, Dict, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from dubby import __version__

STAGE_META = {
    "download": ("⬇️ ", "Download"),
    "asr": ("🎙️ ", "Transcription"),
    "translation": ("🌍", "Translation"),
    "voice": ("🧬", "Reference voice"),
    "tts": ("🔊", "Voice generation"),
    "separation": ("🎚️ ", "Vocal separation"),
    "render": ("🎬", "Render"),
}

console = Console(highlight=False, soft_wrap=False)


def ts(seconds: float) -> str:
    m, s = divmod(max(0.0, seconds), 60)
    return f"{int(m):02d}:{s:05.2f}"


def bar(value: float, width: int = 24) -> Text:
    filled = int(round(value * width))
    t = Text()
    t.append("━" * filled, style="bold white")
    t.append("━" * (width - filled), style="grey30")
    t.append(f" {value * 100:5.1f}%", style="bold")
    return t


def banner(host: str | None = None, port: int | None = None, extra: Dict[str, str] | None = None) -> None:
    title = Text("  Dubby 🐨  ", style="bold black on white")
    body = Text()
    body.append("YouTube dubbing studio · English → Egyptian Arabic / MSA\n", style="white")
    body.append(f"v{__version__}", style="grey62")
    if host:
        body.append("\n\n")
        body.append("Studio  ", style="grey62")
        body.append(f"http://{host}:{port}", style="bold underline white")
    for k, v in (extra or {}).items():
        body.append(f"\n{k:<8}", style="grey62")
        body.append(str(v), style="white")
    console.print(Panel(body, title=title, title_align="left", border_style="white", padding=(1, 2)))


class TerminalReporter:
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self._progress: Dict[Tuple[str, str], Tuple[float, str, float]] = {}
        self._started: Dict[Tuple[str, str], float] = {}
        self._titles: Dict[str, str] = {}
        self._asr_seen: Dict[str, int] = {}

    def __call__(self, event: Dict[str, Any]) -> None:
        handler = getattr(self, f"on_{event.get('type')}", None)
        if handler:
            handler(event)

    # ---------------------------------------------------------------- helpers
    def _tag(self, pid: str | None) -> Text:
        title = self._titles.get(pid or "", pid or "")
        return Text(f"[{title[:28]}] ", style="grey50")

    # ----------------------------------------------------------------- events
    def on_project(self, e: Dict[str, Any]) -> None:
        p = e.get("project") or {}
        if p.get("id"):
            self._titles[p["id"]] = p.get("title") or p["id"]

    def on_stage(self, e: Dict[str, Any]) -> None:
        pid, stage, st = e["project_id"], e["stage"], e["state"]
        key = (pid, stage)
        icon, label = STAGE_META.get(stage, ("•", stage))
        status = st.get("status")
        if status == "queued":
            console.print(self._tag(pid) + Text(f"{icon} {label} queued", style="grey62"))
        elif status == "running":
            if key not in self._started:
                self._started[key] = time.time()
                engine = f" · {st['engine']}" if st.get("engine") else ""
                console.rule(Text(f" {icon} {label}{engine} ", style="bold white"), style="grey35")
            last_v, last_msg, last_t = self._progress.get(key, (-1.0, "", 0.0))
            v, msg = float(st.get("progress", 0)), st.get("message", "")
            if v - last_v >= 0.1 or (msg != last_msg and time.time() - last_t > 1.5) or v >= 1.0:
                console.print(Text("  ") + bar(v) + Text(f"  {msg}", style="grey70"))
                self._progress[key] = (v, msg, time.time())
        elif status in ("done", "error", "cancelled"):
            took = time.time() - self._started.pop(key, time.time())
            self._progress.pop(key, None)
            if status == "done":
                console.print(Text(f"  ✅ {label} finished in {took:.1f}s", style="bold green") + Text(f"  {st.get('message', '')}", style="grey70"))
            elif status == "cancelled":
                console.print(Text(f"  ⏹  {label} cancelled", style="yellow"))
            else:
                console.print(Panel(Text(st.get("error") or "unknown error", style="red"), title=f"❌ {label} failed", border_style="red"))

    def on_segments(self, e: Dict[str, Any]) -> None:
        pid = e["project_id"]
        segs = e.get("segments", [])
        if e.get("final"):
            self._asr_seen.pop(pid, None)
            table = Table(title=f"🎙️  {len(segs)} dubbing chunks", title_style="bold white", border_style="grey35", header_style="bold white", expand=False)
            table.add_column("#", justify="right", style="grey62")
            table.add_column("start", style="grey70")
            table.add_column("end", style="grey70")
            table.add_column("words", justify="right", style="grey62")
            table.add_column("text", style="white", max_width=90, overflow="ellipsis", no_wrap=True)
            for i, s in enumerate(segs[:15]):
                table.add_row(str(i + 1), ts(s["start"]), ts(s["end"]), str(len(s.get("words", []))), s["text"])
            if len(segs) > 15:
                table.add_row("…", "", "", "", f"+{len(segs) - 15} more")
            console.print(table)
            return
        start = 0 if e.get("replace") else self._asr_seen.get(pid, 0)
        for s in segs[start:]:
            console.print(Text(f"  {ts(s['start'])} → {ts(s['end'])}  ", style="grey62") + Text(s["text"], style="white"))
        self._asr_seen[pid] = len(segs)

    def on_segment(self, e: Dict[str, Any]) -> None:
        s, idx, what = e["segment"], e.get("index", 0) + 1, e.get("change")
        if what == "translation" and s.get("translation_status") == "done":
            console.print(Text(f"  #{idx:<4}", style="grey62") + Text(s["text"][:80], style="grey70"))
            console.print(Text("       ↳ ", style="grey50") + Text(s["translation"], style="bold white"))
        elif what == "tts":
            tts = s.get("tts", {})
            if tts.get("status") == "done":
                slot = max(0.01, s["end"] - s["start"])
                ratio = (tts.get("duration") or 0) / slot
                style = "green" if ratio <= 1.05 else ("yellow" if ratio <= 1.35 else "red")
                console.print(Text(f"  🔊 #{idx:<4}", style="grey62") + Text(f"{tts.get('duration', 0):5.2f}s", style="bold white") + Text(f" / slot {slot:5.2f}s ", style="grey62") + Text(f"({ratio * 100:.0f}%)", style=style) + Text(f"  {s['translation'][:70]}", style="grey70"))
            elif tts.get("status") == "error":
                console.print(Text(f"  ⚠️  #{idx} TTS failed: {tts.get('error')}", style="red"))

    def on_log(self, e: Dict[str, Any]) -> None:
        level = e.get("level", "info")
        if level == "debug" and not self.verbose:
            return
        style = {"error": "red", "warning": "yellow", "info": "grey62", "debug": "grey42"}.get(level, "grey62")
        source = e.get("source", "dubby")
        msg = str(e.get("message", ""))
        if level == "error" and "\n" in msg:
            tail = "\n".join(msg.rstrip().splitlines()[-14:])
            console.print(Panel(Text(tail, style="red"), title=f"{source} · traceback (full text in the Logs drawer)", border_style="red"))
            return
        console.print(Text(f"  │ {source:<14} ", style="grey42") + Text(msg[:400], style=style))

    def on_export(self, e: Dict[str, Any]) -> None:
        table = Table(title="📦 Export", title_style="bold white", border_style="white", show_header=False)
        table.add_column(style="grey62")
        table.add_column(style="bold white")
        for item in e.get("items", []):
            table.add_row(item["kind"], item["path"])
        console.print(table)
