"""Readable live log of studio events, for the terminal and the UI's Logs drawer.

The reporter builds every line once as rich ``Text``. It prints to the terminal (``echo``) and/or
hands a structured copy to ``feed`` — text spans with their colour and weight — so the Logs drawer
shows exactly what the terminal shows: stage rules, progress bars, clip lines, ✅ / ⏸ / ❌.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from dubby import __version__

STAGE_META = {
    "download": ("⬇️ ", "Download"),
    "langid": ("🌐", "Language detection"),
    "asr": ("🎙️ ", "Transcription"),
    "translation": ("🌍", "Translation"),
    "voice": ("🧬", "Reference voice"),
    "tts": ("🔊", "Voice generation"),
    "separation": ("🎚️ ", "Vocal separation"),
    "render": ("🎬", "Render"),
    "captions": ("💬", "Caption alignment"),
    "export": ("📦", "Export"),
}

console = Console(highlight=False, soft_wrap=False)
_span_console = Console(width=400, color_system="truecolor", force_terminal=True, highlight=False, soft_wrap=True)

Feed = Callable[[Dict[str, Any]], None]


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


def spans(text: Text) -> List[Dict[str, Any]]:
    """Rich text → [{t: text, c: colour name, b: bold}], merging neighbours with the same style."""
    out: List[Dict[str, Any]] = []
    flat = Text()
    flat.append(text)  # turns a base style into a span, so it survives rendering
    for segment in flat.render(_span_console, end=""):
        if not segment.text or segment.control:
            continue
        style = segment.style
        color = style.color.name if style is not None and style.color is not None else None
        bold = bool(style is not None and style.bold)
        if out and out[-1]["c"] == color and out[-1]["b"] == bold:
            out[-1]["t"] += segment.text
        else:
            out.append({"t": segment.text, "c": color, "b": bold})
    return out


def banner(host: str | None = None, port: int | None = None, extra: Dict[str, str] | None = None) -> None:
    title = Text("  Dubby 🐨  ", style="bold black on white")
    body = Text()
    body.append("YouTube dubbing studio · 9 dub languages\n", style="white")
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
    def __init__(self, verbose: bool = False, echo: bool = True, feed: Optional[Feed] = None):
        self.verbose = verbose
        self.echo = echo
        self.feed = feed
        self._progress: Dict[Tuple[str, str], Tuple[float, str, float]] = {}
        self._started: Dict[Tuple[str, str], float] = {}
        self._titles: Dict[str, str] = {}
        self._asr_seen: Dict[str, int] = {}

    def __call__(self, event: Dict[str, Any]) -> None:
        handler = getattr(self, f"on_{event.get('type')}", None)
        if handler:
            self._project = event.get("project_id")
            handler(event)

    # ---------------------------------------------------------------- output
    def _record(self, kind: str, **data: Any) -> None:
        if self.feed:
            self.feed({"type": "console", "id": uuid.uuid4().hex[:12], "ts": time.time(), "kind": kind,
                       "project_id": getattr(self, "_project", None), **data})

    def line(self, text: Text, tone: Optional[str] = None) -> None:
        if self.echo:
            console.print(text)
        self._record("line", spans=spans(text), tone=tone)

    def rule(self, title: Text) -> None:
        if self.echo:
            console.rule(title, style="grey35")
        self._record("rule", spans=spans(title))

    def panel(self, body: Text, title: str, tone: str) -> None:
        if self.echo:
            console.print(Panel(body, title=title, border_style=tone))
        self._record("panel", title=title, tone=tone, lines=[spans(part) for part in body.split("\n")])

    def table(self, title: str, columns: List[str], rows: List[List[str]], show_header: bool = True) -> None:
        if self.echo:
            table = Table(title=title, title_style="bold white", border_style="grey35", header_style="bold white", expand=False, show_header=show_header)
            for i, column in enumerate(columns):
                table.add_column(column, style="white" if i == len(columns) - 1 else "grey62", max_width=90 if i == len(columns) - 1 else None,
                                 overflow="ellipsis", no_wrap=i == len(columns) - 1)
            for row in rows:
                table.add_row(*row)
            console.print(table)
        self._record("table", title=title, columns=columns if show_header else [], rows=rows)

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
            self.line(self._tag(pid) + Text(f"{icon} {label} queued", style="grey62"))
        elif status == "running":
            if key not in self._started:
                self._started[key] = time.time()
                engine = f" · {st['engine']}" if st.get("engine") else ""
                self.rule(Text(f" {icon} {label}{engine} ", style="bold white"))
            last_v, last_msg, last_t = self._progress.get(key, (-1.0, "", 0.0))
            v, msg = float(st.get("progress", 0)), st.get("message", "")
            if v - last_v >= 0.1 or (msg != last_msg and time.time() - last_t > 1.5) or v >= 1.0:
                self.line(Text("  ") + bar(v) + Text(f"  {msg}", style="grey70"), tone="progress")
                self._progress[key] = (v, msg, time.time())
        elif status in ("done", "error", "cancelled", "paused"):
            took = time.time() - self._started.pop(key, time.time())
            self._progress.pop(key, None)
            if status == "done":
                self.line(Text(f"  ✅ {label} finished in {took:.1f}s", style="bold green") + Text(f"  {st.get('message', '')}", style="grey70"), tone="success")
            elif status == "cancelled":
                self.line(Text(f"  ⏹  {label} cancelled", style="yellow"), tone="warning")
            elif status == "paused":
                self.line(Text(f"  ⏸  {label} paused after {took:.1f}s", style="bold yellow") + Text(f"  {st.get('message', '')}", style="grey70"), tone="warning")
                if st.get("error"):
                    self.line(Text(f"     {st['error']}", style="yellow"), tone="warning")
            else:
                self.panel(Text(st.get("error") or "unknown error", style="red"), f"❌ {label} failed", "red")

    def on_segments(self, e: Dict[str, Any]) -> None:
        pid = e["project_id"]
        segs = e.get("segments", [])
        if e.get("final"):
            self._asr_seen.pop(pid, None)
            rows = [[str(i + 1), ts(s["start"]), ts(s["end"]), str(len(s.get("words", []))), s["text"]] for i, s in enumerate(segs[:15])]
            if len(segs) > 15:
                rows.append(["…", "", "", "", f"+{len(segs) - 15} more"])
            self.table(f"🎙️  {len(segs)} dubbing chunks", ["#", "start", "end", "words", "text"], rows)
            return
        start = 0 if e.get("replace") else self._asr_seen.get(pid, 0)
        for s in segs[start:]:
            self.line(Text(f"  {ts(s['start'])} → {ts(s['end'])}  ", style="grey62") + Text(s["text"], style="white"))
        self._asr_seen[pid] = len(segs)

    def on_segment(self, e: Dict[str, Any]) -> None:
        s, idx, what = e["segment"], e.get("index", 0) + 1, e.get("change")
        if what == "translation" and s.get("translation_status") == "done":
            self.line(Text(f"  #{idx:<4}", style="grey62") + Text(s["text"][:80], style="grey70"))
            self.line(Text("       ↳ ", style="grey50") + Text(s["translation"], style="bold white"))
        elif what == "tts":
            tts = s.get("tts", {})
            if tts.get("status") == "done":
                slot = max(0.01, s["end"] - s["start"])
                ratio = (tts.get("duration") or 0) / slot
                style = "green" if ratio <= 1.05 else ("yellow" if ratio <= 1.35 else "red")
                self.line(Text(f"  🔊 #{idx:<4}", style="grey62") + Text(f"{tts.get('duration', 0):5.2f}s", style="bold white") + Text(f" / slot {slot:5.2f}s ", style="grey62")
                          + Text(f"({ratio * 100:.0f}%)", style=style) + Text(f"  {s['translation'][:70]}", style="grey70"))
            elif tts.get("status") == "error":
                self.line(Text(f"  ⚠️  #{idx} TTS failed: {tts.get('error')}", style="red"), tone="error")

    def on_log(self, e: Dict[str, Any]) -> None:
        level = e.get("level", "info")
        if level == "debug" and not self.verbose:
            return
        style = {"error": "red", "warning": "yellow", "info": "grey62", "debug": "grey42"}.get(level, "grey62")
        tone = {"error": "error", "warning": "warning"}.get(level)
        source = e.get("source", "dubby")
        msg = str(e.get("message", ""))
        if level == "error" and "\n" in msg:
            tail = "\n".join(msg.rstrip().splitlines()[-14:])
            self.panel(Text(tail, style="red"), f"{source} · traceback (full text in the Logs drawer)", "red")
            return
        self.line(Text(f"  │ {source:<14} ", style="grey42") + Text(msg[:400], style=style), tone=tone)

    def on_export(self, e: Dict[str, Any]) -> None:
        self.table("📦 Export", ["kind", "path"], [[item["kind"], item["path"]] for item in e.get("items", [])], show_header=False)
