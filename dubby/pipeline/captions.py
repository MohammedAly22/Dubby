"""Captions burned into the video, drawn exactly like the studio player's caption overlay.

The player (``ui/src/components/CaptionOverlay.tsx``) and this renderer share one style spec
(``STYLE`` below / ``CAPTION_STYLE`` in ``ui/src/captionStyle.ts``), expressed in CSS pixels for a
760 px wide video and scaled to the real frame width. Both follow the same rules:

* original line — dark rounded box; the word being spoken is lime and semibold, spoken words
  bright, upcoming words grey
* dub line — lime gradient box with a soft glow; the current word is extra-bold, upcoming words
  at 50% opacity
* the UI's web fonts (Inter, IBM Plex Sans Arabic, Noto for Devanagari / CJK), right-to-left layout
  for Arabic, word wrapping, centering and line heights as the browser computes them

Every distinct caption state is drawn once with Pillow (raqm shaping) into a transparent PNG, and
ffmpeg overlays that image sequence on the rendered video.
"""

from __future__ import annotations

import bisect
import hashlib
import json
import math
import re
import shutil
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from dubby import languages as L
from dubby.media import ffmpeg
from dubby.schemas import Project, Segment

MODES = ("original", "dub", "both")
RENDERER_VERSION = 2
MIN_CAPTION_WIDTH = 1280  # smaller videos are upscaled for the captioned export

# CSS px at a 760 px wide video — keep in sync with ui/src/captionStyle.ts
STYLE = {
    "ref_width": 760,
    "bottom": 56,  # distance from the bottom of the video to the lowest box
    "gap": 4,  # between the original and the dub box
    "side": 24,  # container side padding
    "max_width": 0.92,  # box max width, fraction of the container content width
    "radius": 8,
    "original": {"size": 14, "line_height": 1.625, "pad_x": 12, "pad_y": 6, "background": (0, 0, 0, 191),
                 "plain": ("#ffffff", 400), "spoken": ("#e5e5e5", 400), "current": ("#c8ec6f", 600), "upcoming": ("#8a8a8a", 400)},
    "dub": {"size": 15, "line_height": 1.5, "pad_x": 12, "pad_y": 4, "ink": "#0f1a05",
            "plain": 600, "spoken": 500, "current": 800, "upcoming": 500, "upcoming_opacity": 0.5,
            "gradient": {"angle": 100, "stops": [(0.0, "#9bd23c"), (0.58, "#c3e657"), (1.0, "#f4e03a")], "size_x": 1.6},
            "shadow": {"y": 6, "blur": 20, "spread": -6, "color": (155, 210, 60, 0.7)}},
    "arabic_line_height": 1.9,  # the .arabic class
    "dub_linger": 0.15,  # the dub line stays this long after its clip ends
}


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


# ------------------------------------------------------------------ scripts & bidi

ARABIC = re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")
HEBREW = re.compile(r"[֐-׿]")
DEVANAGARI = re.compile(r"[ऀ-ॿ꣠-ꣿ]")
KANA = re.compile(r"[぀-ヿㇰ-ㇿ]")
HAN = re.compile(r"[㐀-䶿一-鿿豈-﫿　-〿＀-￯]")


def script_of(text: str, language: str, arabic_box: bool) -> str:
    if DEVANAGARI.search(text):
        return "devanagari"
    if KANA.search(text) or (HAN.search(text) and L.iso(language) == "ja" if language in L.LANGUAGES else False):
        return "kana"
    if HAN.search(text):
        return "han"
    if ARABIC.search(text) or arabic_box:
        return "arabic"
    return "latin"


def strong_direction(text: str) -> Optional[str]:
    """First strong bidi class of the text: 'R', 'L' or None (digits, punctuation)."""
    for ch in text:
        kind = unicodedata.bidirectional(ch)
        if kind in ("R", "AL"):
            return "R"
        if kind == "L":
            return "L"
    return None


def visual_order(directions: Sequence[Optional[str]], paragraph: str) -> List[int]:
    """Word-level bidi: runs of same-direction words, laid out in the paragraph direction.
    Neutral words (numbers, punctuation) take the direction of the previous strong word."""
    resolved, previous = [], paragraph
    for d in directions:
        previous = d or previous
        resolved.append(previous)
    runs: List[List[int]] = []
    for i, d in enumerate(resolved):
        if runs and resolved[runs[-1][0]] == d:
            runs[-1].append(i)
        else:
            runs.append([i])
    ordered = []
    for run in (reversed(runs) if paragraph == "R" else runs):
        ordered.extend(reversed(run) if resolved[run[0]] == "R" else run)
    return ordered


# ------------------------------------------------------------------ fonts & shaping


def _pil():
    from PIL import Image, ImageDraw, ImageFilter, ImageFont, features

    return Image, ImageDraw, ImageFilter, ImageFont, features


@lru_cache(maxsize=None)
def has_raqm() -> bool:
    return bool(_pil()[4].check("raqm"))


@lru_cache(maxsize=256)
def load_font(path: str, size: float):
    ImageFont = _pil()[3]
    engine = ImageFont.Layout.RAQM if has_raqm() else ImageFont.Layout.BASIC
    return ImageFont.truetype(path, size=size, layout_engine=engine)


def shaped(text: str) -> str:
    """Without raqm, Arabic letters need joining forms and visual order done by hand."""
    if has_raqm() or not ARABIC.search(text):
        return text
    try:
        import arabic_reshaper

        return arabic_reshaper.reshape(text)[::-1]
    except ImportError:
        return text[::-1]


@dataclass
class Token:
    text: str
    state: str  # plain | spoken | current | upcoming


@dataclass
class Box:
    kind: str  # original | dub
    tokens: List[Token]
    language: str


class Renderer:
    def __init__(self, width: int, height: int, fonts, source: str, target: str):
        self.W, self.H = width, height
        self.s = width / STYLE["ref_width"]
        self.fonts = fonts
        self.source, self.target = source, target
        self._backgrounds: Dict[Tuple, object] = {}

    # --------------------------------------------------------------- measuring
    def _spec(self, box: Box):
        spec = STYLE[box.kind]
        rtl_language = box.language in L.LANGUAGES and L.get(box.language).rtl
        spaced = box.language not in L.LANGUAGES or L.get(box.language).spaced
        line_height = STYLE["arabic_line_height"] if rtl_language else spec["line_height"]
        return spec, rtl_language, spaced, line_height

    def _style(self, box: Box, token: Token) -> Tuple[str, int, float]:
        spec = STYLE[box.kind]
        if box.kind == "original":
            color, weight = spec[token.state]
            return color, weight, 1.0
        return spec["ink"], spec[token.state], spec["upcoming_opacity"] if token.state == "upcoming" else 1.0

    def _font(self, script: str, weight: int, size: float):
        path = self.fonts.path(script, weight)
        if path is None:
            raise RuntimeError(f"No font available for {script} captions — check the network so Dubby can download the UI fonts.")
        return load_font(str(path), size)

    def layout(self, box: Box) -> Dict:
        spec, rtl_language, spaced, line_height = self._spec(box)
        size = spec["size"] * self.s
        lh = line_height * size
        pad_x, pad_y = spec["pad_x"] * self.s, spec["pad_y"] * self.s
        container = self.W - 2 * STYLE["side"] * self.s
        inner_max = container * STYLE["max_width"] - 2 * pad_x
        strut = self._font("arabic" if rtl_language else "latin", 400, size)

        items = []
        for token in box.tokens:
            color, weight, opacity = self._style(box, token)
            script = script_of(token.text, box.language, rtl_language)
            font = self._font(script, weight, size)
            text = shaped(token.text)
            items.append({"text": text, "font": font, "color": color, "opacity": opacity,
                          "width": font.getlength(text), "space": font.getlength(" ") if spaced else 0.0,
                          "dir": strong_direction(token.text)})
        paragraph = next((it["dir"] for it in items if it["dir"]), "L")

        lines: List[List[int]] = []
        used = 0.0
        for i, it in enumerate(items):
            add = it["width"] + (items[i - 1]["space"] if lines and lines[-1] else 0.0)
            if lines and lines[-1] and used + add > inner_max + 0.01:
                lines.append([i])
                used = it["width"]
            else:
                if not lines:
                    lines.append([])
                lines[-1].append(i)
                used += add
        widths = [sum(items[i]["width"] for i in line) + sum(items[i]["space"] for i in line[:-1]) for line in lines]
        inner = min(max(widths or [0.0]) if len(lines) == 1 else inner_max, inner_max)
        box_w = math.ceil(inner + 2 * pad_x)
        box_h = math.ceil(len(lines) * lh + 2 * pad_y)

        ascent, descent = strut.getmetrics()
        placed = []
        for row, (line, line_w) in enumerate(zip(lines, widths)):
            x = pad_x + (inner - line_w) / 2
            baseline = pad_y + row * lh + (lh - (ascent + descent)) / 2 + ascent
            order = visual_order([items[i]["dir"] for i in line], paragraph)
            for position, k in enumerate(order):
                it = items[line[k]]
                placed.append((x, baseline, it))
                # the space after a word sits on its trailing side in logical order
                x += it["width"] + (items[line[order[position + 1]]]["space"] if position + 1 < len(order) else 0.0)
        return {"box": box, "w": box_w, "h": box_h, "placed": placed}

    # --------------------------------------------------------------- drawing
    def _rounded_mask(self, w: int, h: int, radius: float, supersample: int = 4):
        Image, ImageDraw = _pil()[0], _pil()[1]
        big = Image.new("L", (w * supersample, h * supersample), 0)
        ImageDraw.Draw(big).rounded_rectangle((0, 0, w * supersample - 1, h * supersample - 1), radius=radius * supersample, fill=255)
        return big.resize((w, h), Image.LANCZOS)

    def _gradient(self, w: int, h: int):
        import numpy as np

        Image = _pil()[0]
        g = STYLE["dub"]["gradient"]
        bw = w * g["size_x"]  # background-size: 160% 100%, positioned at 0%
        angle = math.radians(g["angle"])
        dx, dy = math.sin(angle), -math.cos(angle)
        length = abs(bw * dx) + abs(h * dy)
        xs, ys = np.meshgrid(np.arange(w) + 0.5, np.arange(h) + 0.5)
        t = np.clip(((xs - bw / 2) * dx + (ys - h / 2) * dy) / length + 0.5, 0.0, 1.0)
        stops = [(pos, tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))) for pos, c in g["stops"]]
        rgb = np.zeros((h, w, 3))
        for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
            inside = (t >= p0) & (t <= p1)
            local = (t - p0) / max(1e-6, p1 - p0)
            for channel in range(3):
                rgb[..., channel] = np.where(inside, c0[channel] + (c1[channel] - c0[channel]) * local, rgb[..., channel])
        return Image.fromarray(rgb.round().astype("uint8"), "RGB")

    def background(self, kind: str, w: int, h: int):
        """The box (and its glow) as an RGBA sprite, with the offset of the box inside it."""
        key = (kind, w, h)
        if key in self._backgrounds:
            return self._backgrounds[key]
        Image, ImageDraw, ImageFilter = _pil()[0], _pil()[1], _pil()[2]
        radius = STYLE["radius"] * self.s
        mask = self._rounded_mask(w, h, radius)
        if kind == "original":
            sprite = Image.new("RGBA", (w, h), STYLE["original"]["background"][:3] + (0,))
            sprite.putalpha(mask.point(lambda v: v * STYLE["original"]["background"][3] // 255))
            result = (sprite, 0, 0)
        else:
            shadow = STYLE["dub"]["shadow"]
            blur = shadow["blur"] * self.s
            margin = int(math.ceil(blur * 1.6 + abs(shadow["y"] * self.s) + abs(shadow["spread"] * self.s)))
            size = (w + 2 * margin, h + 2 * margin)
            spread, offset = shadow["spread"] * self.s, shadow["y"] * self.s
            glow = Image.new("L", size, 0)
            ImageDraw.Draw(glow).rounded_rectangle(
                (margin - spread, margin - spread + offset, margin + w - 1 + spread, margin + h - 1 + spread + offset),
                radius=max(0.0, radius + spread), fill=int(255 * shadow["color"][3]))
            glow = glow.filter(ImageFilter.GaussianBlur(blur / 2))  # CSS blur radius = 2σ
            sprite = Image.new("RGBA", size, shadow["color"][:3] + (0,))  # the glow's colour, its shape in alpha
            sprite.putalpha(glow)
            fill = self._gradient(w, h).convert("RGBA")
            fill.putalpha(mask)
            sprite.alpha_composite(fill, (margin, margin))
            result = (sprite, margin, margin)
        self._backgrounds[key] = result
        return result

    def draw_box(self, layout: Dict):
        Image, ImageDraw = _pil()[0], _pil()[1]
        sprite, ox, oy = self.background(layout["box"].kind, layout["w"], layout["h"])
        image = sprite.copy()
        faded = [p for p in layout["placed"] if p[2]["opacity"] < 1.0]
        solid = [p for p in layout["placed"] if p[2]["opacity"] >= 1.0]
        if faded:  # opacity: blend a fully inked copy over the box
            inked = image.copy()
            draw = ImageDraw.Draw(inked)
            for x, baseline, it in faded:
                draw.text((ox + x, oy + baseline), it["text"], font=it["font"], fill=it["color"], anchor="ls")
            image = Image.blend(image, inked, faded[0][2]["opacity"])
        draw = ImageDraw.Draw(image)
        for x, baseline, it in solid:
            draw.text((ox + x, oy + baseline), it["text"], font=it["font"], fill=it["color"], anchor="ls")
        return image, ox, oy

    def frame_layout(self, boxes: Sequence[Box]) -> List[Tuple[Dict, int, int]]:
        """Stack the boxes bottom-up like the player's flex column: centered, gap between, lowest box at `bottom`."""
        layouts = [self.layout(b) for b in boxes]
        y = self.H - STYLE["bottom"] * self.s
        positions = []
        for lay in reversed(layouts):
            top = y - lay["h"]
            positions.append((lay, int(round((self.W - lay["w"]) / 2)), int(round(top))))
            y = top - STYLE["gap"] * self.s
        return list(reversed(positions))

    def render(self, boxes: Sequence[Box], region_top: int):
        Image = _pil()[0]
        canvas = Image.new("RGBA", (self.W, self.H - region_top), (0, 0, 0, 0))
        for lay, x, y in self.frame_layout(boxes):
            image, ox, oy = self.draw_box(lay)
            px, py = x - ox, y - oy - region_top
            # clip sprites that stick out of the frame (a glow near an edge)
            left, top = max(0, -px), max(0, -py)
            right, bottom = min(image.width, canvas.width - px), min(image.height, canvas.height - py)
            if right > left and bottom > top:
                canvas.alpha_composite(image.crop((left, top, right, bottom)), (px + left, py + top))
        return canvas


# ------------------------------------------------------------------ timeline


def _joined_tokens(text: str, language: str) -> List[str]:
    spaced = language not in L.LANGUAGES or L.get(language).spaced
    return text.split() if spaced else [ch for ch in text if not ch.isspace()]


def timeline(project: Project, mode: str) -> List[Tuple[float, float, Optional[str], List[Box]]]:
    """Caption states over time, following the player's rules in Rendered mode."""
    source, target = project.settings.source_language, project.settings.target
    segments = sorted(project.segments, key=lambda s: s.start)
    starts = [s.start for s in segments]
    by_id = {s.id: s for s in project.segments}
    clips = project.render.clips or [
        {"id": s.id, "start": s.start, "end": s.start + float(s.tts.duration or 0)} for s in project.segments if s.tts.status == "done" and s.tts.duration
    ]
    clips = sorted(clips, key=lambda c: c["start"])
    show_original, show_dub = mode in ("original", "both"), mode in ("dub", "both")

    marks = {0.0}
    if show_original:
        for seg in segments:
            marks.update((seg.start, seg.end))
            for w in seg.words:
                marks.update((w.start, w.end))
    if show_dub:
        for clip in clips:
            marks.update((clip["start"], clip["end"] + STYLE["dub_linger"]))
            words = by_id[clip["id"]].dub_words if clip["id"] in by_id else []
            for i, w in enumerate(words):
                marks.update((w.start, max(w.end, words[i + 1].start if i + 1 < len(words) else w.end)))
    points = sorted(m for m in marks if m >= 0)

    def original_at(t: float) -> Optional[Box]:
        i = bisect.bisect_right(starts, t) - 1
        seg = segments[i] if i >= 0 and segments[i].start <= t < segments[i].end else None
        if seg is None or not seg.text.strip():
            return None
        if seg.words:
            tokens = [Token(w.text, "current" if w.start <= t < w.end else "spoken" if t >= w.end else "upcoming") for w in seg.words if w.text.strip()]
        else:
            tokens = [Token(text, "plain") for text in _joined_tokens(seg.text, source)]
        return Box("original", tokens, source)

    def dub_at(t: float) -> Optional[Box]:
        clip = next((c for c in clips if c["start"] <= t < c["end"] + STYLE["dub_linger"]), None)
        seg: Optional[Segment] = by_id.get(clip["id"]) if clip else None
        if seg is None or not seg.translation.strip():
            return None
        words = seg.dub_words
        if words:
            tokens = []
            for i, w in enumerate(words):
                nxt = words[i + 1].start if i + 1 < len(words) else w.end
                state = "current" if w.start <= t < max(w.end, nxt) else "spoken" if t >= w.start else "upcoming"
                if w.text.strip():
                    tokens.append(Token(w.text, state))
        else:
            tokens = [Token(text, "plain") for text in _joined_tokens(seg.translation, target)]
        return Box("dub", tokens, target)

    states: List[Tuple[float, float, Optional[str], List[Box]]] = []
    for a, b in zip(points, points[1:] + [points[-1] + 1e9]):
        if b - a < 1e-3:
            continue
        mid = (a + b) / 2 if b < 1e8 else a + 0.001
        boxes = [box for box in ((original_at(mid) if show_original else None), (dub_at(mid) if show_dub else None)) if box]
        key = json.dumps([[bx.kind, bx.language, [[tk.text, tk.state] for tk in bx.tokens]] for bx in boxes], ensure_ascii=False) if boxes else None
        if states and states[-1][2] == key:
            states[-1] = (states[-1][0], b, key, boxes)
        else:
            states.append((a, b, key, boxes))
    return states


# ------------------------------------------------------------------ burn


def burn(project: Project, project_dir: Path, mode: str, progress: Callable[[float, str], None],
         fonts_dir: Optional[Path] = None, log: Callable[[str], None] = lambda message: None) -> Path:
    """Draw the captions into the rendered video; cached per caption content and style."""
    from dubby.media.fonts import FontSet

    if mode not in MODES:
        raise ValueError(f"caption mode must be one of {MODES}")
    if not project.render.video:
        raise RuntimeError("Render the dubbed video first.")
    video = project_dir / project.render.video
    source_w, source_h = ffmpeg.video_size(video)
    # captions are drawn at the frame's resolution: upscale small videos so the text stays crisp and readable
    factor = max(1.0, MIN_CAPTION_WIDTH / max(1, source_w))
    width, height = (int(round(source_w * factor / 2)) * 2, int(round(source_h * factor / 2)) * 2) if factor > 1 else (source_w, source_h)
    total = ffmpeg.duration(video)
    states = [st for st in timeline(project, mode) if st[0] < total + 1]

    fonts_dir = fonts_dir or _default_fonts_dir()
    fonts = FontSet(fonts_dir, log)
    scripts = {"latin"}
    for _, _, key, boxes in states:
        for box in boxes:
            rtl = box.language in L.LANGUAGES and L.get(box.language).rtl
            scripts.add("arabic" if rtl else "latin")
            scripts.update(script_of(tk.text, box.language, rtl) for tk in box.tokens)
    progress(0.01, "Preparing caption fonts…")
    fonts.ensure(scripts)

    digest_source = json.dumps({"v": RENDERER_VERSION, "style": STYLE, "size": [width, height], "raqm": has_raqm(),
                                "fonts": sorted(str(fonts.path(s, w)) for s in scripts for w in (400, 500, 600, 800)),
                                "states": [[round(a, 3), round(b, 3), key] for a, b, key, _ in states]}, ensure_ascii=False, default=str)
    digest = hashlib.sha1(digest_source.encode("utf-8")).hexdigest()[:8]
    out_dir = video.parent
    out = out_dir / f"{video.stem}_captions-{mode}-{digest}.mp4"
    if out.exists():
        progress(1.0, "Captioned video already up to date")
        return out

    renderer = Renderer(width, height, fonts, project.settings.source_language, project.settings.target)
    unique: Dict[str, List[Box]] = {key: boxes for _, _, key, boxes in states if key}
    # one overlay size for the whole video: the tallest caption stack plus its glow
    top = height
    for boxes in unique.values():
        for lay, _, y in renderer.frame_layout(boxes):
            glow = 0 if lay["box"].kind == "original" else STYLE["dub"]["shadow"]["blur"] * renderer.s * 1.6
            top = min(top, int(y - glow))
    region_top = max(0, min(top - 2, height - 2))

    frames = out_dir / f"captions-{mode}-{digest}"
    shutil.rmtree(frames, ignore_errors=True)
    frames.mkdir(parents=True)
    Image = _pil()[0]
    Image.new("RGBA", (width, height - region_top), (0, 0, 0, 0)).save(frames / "blank.png")
    names: Dict[str, str] = {}
    for index, (key, boxes) in enumerate(unique.items()):
        name = f"{index:06d}.png"
        renderer.render(boxes, region_top).save(frames / name, compress_level=1)
        names[key] = name
        if index % 25 == 0:
            progress(0.02 + 0.38 * index / max(1, len(unique)), f"Drawing captions · {index}/{len(unique)}")

    entries = ["ffconcat version 1.0"]
    cursor = 0.0
    for a, b, key, _ in states:
        a, b = max(a, cursor), min(b, total)
        if b <= a:
            continue
        if a > cursor + 1e-3:
            entries += ["file blank.png", f"duration {a - cursor:.3f}"]
        entries += [f"file {names[key] if key else 'blank.png'}", f"duration {b - a:.3f}"]
        cursor = b
    if cursor < total:
        entries += ["file blank.png", f"duration {total - cursor + 1:.3f}"]
    entries.append("file blank.png")  # the last entry's duration only applies when another file follows
    (frames / "captions.ffconcat").write_text("\n".join(entries) + "\n", encoding="utf-8")

    progress(0.4, f"Encoding the video with {mode} captions…")
    scale = f"scale={width}:{height}:flags=lanczos,setsar=1," if (width, height) != (source_w, source_h) else ""
    graph = f"[0:v]{scale}format=yuv420p[base];[1:v]format=rgba[caps];[base][caps]overlay=x=0:y={region_top}:eof_action=pass:format=auto,format=yuv420p[v]"
    base = ["-i", str(video), "-f", "concat", "-safe", "0", "-i", str(frames / "captions.ffconcat"),
            "-filter_complex", graph, "-map", "[v]", "-map", "0:a?", "-map", "0:s?", "-c:a", "copy", "-c:s", "copy", "-movflags", "+faststart"]
    report = lambda v: progress(0.4 + 0.59 * v, f"Encoding with {mode} captions · {int(v * 100)}%")  # noqa: E731
    encoders = ffmpeg.video_encoders()
    tmp = out.with_suffix(".part.mp4")
    try:
        done = False
        if encoders.get("h264_nvenc") and shutil.which("nvidia-smi"):
            try:
                ffmpeg.run_with_progress([*base, "-c:v", "h264_nvenc", "-preset", "p5", "-cq", "21", "-b:v", "0", str(tmp)], total, report, executable=encoders["h264_nvenc"])
                done = True
            except ffmpeg.FFmpegError as exc:
                log(f"GPU encoder unavailable ({str(exc).splitlines()[-1][:120]}); encoding on the CPU.")
        if not done:
            exe = encoders.get("libx264")
            if not exe:
                raise ffmpeg.FFmpegError("No ffmpeg here can encode H.264 (libx264). Fix: pip install imageio-ffmpeg, then export again.")
            ffmpeg.run_with_progress([*base, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(tmp)], total, report, executable=exe)
        tmp.replace(out)
    finally:
        tmp.unlink(missing_ok=True)
        shutil.rmtree(frames, ignore_errors=True)
    return out


def _default_fonts_dir() -> Path:
    from dubby.config import load_settings

    return load_settings().cache_dir / "fonts"
