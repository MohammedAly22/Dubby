"""Captions burned into the video, with the same per-word highlighting as the studio player.

Builds an ASS (Advanced SubStation Alpha) file where every word gets its own event, so the
current word is bold and lime, spoken words are bright and upcoming words are dimmed. The
file is burned into the frames with ffmpeg's libass ``ass`` filter.

    original captions — dark box, current word lime   (like the player's source line)
    dub captions      — lime box, current word bold   (like the player's dubbed line)
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

from dubby import languages as L
from dubby.media import ffmpeg
from dubby.schemas import Project, Segment

MODES = ("original", "dub", "both")

# ASS colours are &HAABBGGRR (alpha 00 = opaque)
WHITE_SPOKEN = "&H00E5E5E5&"
GREY_UPCOMING = "&H008A8A8A&"
LIME_CURRENT = "&H006FECC8&"  # #c8ec6f
DUB_INK = "&H00051A0F&"  # #0f1a05
BOX_DARK = "&H40000000"  # black, 75% opaque
BOX_LIME = "&H003CD29B"  # #9BD23C


def font_for(language: str) -> str:
    iso = L.iso(language) if language in L.LANGUAGES else language
    if os.name == "nt":
        return {"hi": "Nirmala UI", "zh": "Microsoft YaHei", "ja": "Yu Gothic UI"}.get(iso, "Arial")
    return {"ar": "Noto Sans Arabic", "hi": "Noto Sans Devanagari", "zh": "Noto Sans CJK SC", "ja": "Noto Sans CJK JP"}.get(iso, "Noto Sans")


def estimate_words(text: str, start: float, end: float, language: str) -> List[Dict[str, float]]:
    """Spread a line over its words in proportion to their length (used until alignment finishes)."""
    tokens = L.tokenize(text, language) if language in L.LANGUAGES else text.split()
    if not tokens:
        return []
    weights = [max(1, len(t)) for t in tokens]
    total, span, cursor = float(sum(weights)), max(0.05, end - start), start
    out = []
    for token, weight in zip(tokens, weights):
        duration = span * weight / total
        out.append({"text": token, "start": round(cursor, 3), "end": round(cursor + duration, 3)})
        cursor += duration
    return out


def _ts(seconds: float) -> str:
    cs = int(round(max(0.0, seconds) * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _clean(word: str) -> str:
    return re.sub(r"[{}\\\n\r]", " ", word).strip()


RLM = "\u200f"  # right-to-left mark


def _line(texts: Sequence[str], current: int, tags: Dict[str, str], joiner: str, rtl: bool) -> str:
    """The whole line with the current word highlighted.

    Consecutive words sharing a state (spoken / current / upcoming) form one styled run.
    libass orders the runs of a right-to-left line correctly but lays out the words inside a
    run left to right, so for RTL scripts the words of each run are reversed and wrapped in
    RLM marks (which also keeps trailing punctuation on the correct side of its word).
    """
    runs: List[List] = []
    for j, text in enumerate(texts):
        state = "current" if j == current else "spoken" if j < current else "upcoming"
        if runs and runs[-1][0] == state:
            runs[-1][1].append(text)
        else:
            runs.append([state, [text]])
    if rtl:
        return joiner.join(tags[state] + joiner.join(f"{RLM}{w}{RLM}" for w in reversed(words)) for state, words in runs)
    return joiner.join(tags[state] + joiner.join(words) for state, words in runs)


def _events(words: Sequence[Dict], seg_start: float, seg_end: float, style: str, tags: Dict[str, str], language: str) -> List[str]:
    """One Dialogue per word interval: the whole line, with the current word highlighted."""
    words = [w for w in words if _clean(str(w["text"]))]
    if not words:
        return []
    known = language in L.LANGUAGES
    joiner = " " if not known or L.get(language).spaced else ""
    rtl = known and L.get(language).rtl
    texts = [_clean(str(w["text"])) for w in words]
    lines = []
    first = float(words[0]["start"])
    lead_in = first > seg_start + 0.05
    if lead_in:  # before the first word: everything upcoming
        lines.append(f"Dialogue: 0,{_ts(seg_start)},{_ts(first)},{style},,0,0,0,,{_line(texts, -1, tags, joiner, rtl)}")
    for i, w in enumerate(words):
        start = float(w["start"]) if i or lead_in else min(float(w["start"]), seg_start)
        end = float(words[i + 1]["start"]) if i + 1 < len(words) else max(float(w["end"]), seg_end)
        if end - start < 0.01:
            continue
        lines.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},{style},,0,0,0,,{_line(texts, i, tags, joiner, rtl)}")
    return lines


# original: current word lime + bold, spoken words bright, upcoming words grey
ORIGINAL_TAGS = {
    "spoken": rf"{{\c{WHITE_SPOKEN}\b0}}",
    "current": rf"{{\c{LIME_CURRENT}\b1}}",
    "upcoming": rf"{{\c{GREY_UPCOMING}\b0}}",
}
# dub: dark ink on lime, current word bold, upcoming words faded
DUB_TAGS = {
    "spoken": r"{\1a&H00&\b0}",
    "current": r"{\1a&H00&\b1}",
    "upcoming": r"{\1a&H78&\b0}",
}


def build_ass(project: Project, mode: str, width: int, height: int) -> str:
    if mode not in MODES:
        raise ValueError(f"caption mode must be one of {MODES}")
    source, target = project.settings.source_language, project.settings.target
    orig_size, dub_size = round(height * 0.042), round(height * 0.05)
    margin_side, margin_bottom = round(width * 0.06), round(height * 0.07)
    orig_margin = margin_bottom + (round(dub_size * 2.9) if mode == "both" else 0)
    pad = max(2, round(height * 0.008))
    header = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Original,{font_for(source)},{orig_size},&H00E5E5E5,&H00E5E5E5,{BOX_DARK},{BOX_DARK},0,0,0,0,100,100,0,0,3,{pad},0,2,{margin_side},{margin_side},{orig_margin},1",
        f"Style: Dub,{font_for(target)},{dub_size},{DUB_INK},{DUB_INK},{BOX_LIME},{BOX_LIME},0,0,0,0,100,100,0,0,3,{pad},0,2,{margin_side},{margin_side},{margin_bottom},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    events: List[str] = []
    for seg in project.segments:
        if mode in ("original", "both") and seg.text.strip():
            words = [w.model_dump() for w in seg.words] or estimate_words(seg.text, seg.start, seg.end, source)
            events += _events(words, seg.start, seg.end, "Original", ORIGINAL_TAGS, source)
        if mode in ("dub", "both") and seg.translation.strip() and seg.tts.status == "done":
            words = [w.model_dump() for w in seg.dub_words]
            if not words:
                clip = next((c for c in project.render.clips if c.get("id") == seg.id), None)
                start, end = (clip["start"], clip["end"]) if clip else (seg.start, seg.end)
                words = estimate_words(seg.translation, start, end, target)
            if words:
                events += _events(words, float(words[0]["start"]), float(words[-1]["end"]), "Dub", DUB_TAGS, target)
    return "\n".join(header + events) + "\n"


def burn(project: Project, project_dir: Path, mode: str, progress: Callable[[float, str], None]) -> Path:
    """Burn captions into the rendered video; cached per caption content."""
    if not project.render.video:
        raise RuntimeError("Render the dubbed video first.")
    video = project_dir / project.render.video
    width, height = ffmpeg.video_size(video)
    ass = build_ass(project, mode, width, height)
    digest = hashlib.sha1(ass.encode("utf-8")).hexdigest()[:8]
    out_dir = video.parent
    out = out_dir / f"{video.stem}_captions-{mode}-{digest}.mp4"
    if out.exists():
        progress(1.0, "Captioned video already up to date")
        return out
    executable = ffmpeg.caption_binary()  # fail fast, with a fix, when no ffmpeg here has libass
    ass_name = f"captions-{mode}-{digest}.ass"
    (out_dir / ass_name).write_text(ass, encoding="utf-8")
    total = ffmpeg.duration(video)
    progress(0.02, f"Burning {mode} captions into the video…")
    ffmpeg.run_with_progress(
        ["-i", video.name, "-map", "0", "-vf", f"ass={ass_name}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
         "-c:a", "copy", "-c:s", "copy", "-movflags", "+faststart", out.name],
        total,
        lambda v: progress(0.02 + 0.97 * v, f"Burning {mode} captions · {int(v * 100)}%"),
        cwd=out_dir,
        executable=executable,
    )
    return out
