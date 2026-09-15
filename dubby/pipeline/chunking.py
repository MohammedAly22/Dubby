"""Turn raw ASR output into dubbing chunks.

A good dubbing chunk is a sentence-like unit short enough for TTS to voice in
one go and long enough to carry natural prosody. We rebuild chunks from word
timestamps: split on sentence punctuation, long pauses, and a hard duration cap
(preferring clause punctuation), then fold tiny leftovers into their neighbours.

Scripts written without spaces (Chinese, Japanese) are aligned per character,
so tokens are joined without separators there.
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List

# Latin, Arabic, CJK full-width and Devanagari sentence / clause marks
SENTENCE_END = re.compile(r"[.!?؟…。！？।]+[\"'»”」』)\]）]*$")
CLAUSE_END = re.compile(r"[,،;؛:，、；：]+[\"'»”」』)\]）]*$")


def new_id() -> str:
    return uuid.uuid4().hex[:10]


def _join(tokens: List[str], spaced: bool) -> str:
    return (" " if spaced else "").join(t for t in tokens if t).strip()


def fill_word_times(words: List[Dict[str, Any]], seg_start: float, seg_end: float) -> List[Dict[str, Any]]:
    """Interpolate missing word timestamps (aligners skip out-of-vocabulary tokens)."""
    out = [dict(w) for w in words if str(w.get("text", w.get("word", ""))).strip()]
    for w in out:
        if "text" not in w:
            w["text"] = w.pop("word", "")
        w["text"] = str(w["text"]).strip()
        for k in ("start", "end"):
            if w.get(k) is not None:
                w[k] = float(w[k])
    n = len(out)
    i = 0
    while i < n:
        if out[i].get("start") is not None and out[i].get("end") is not None:
            i += 1
            continue
        j = i
        while j < n and (out[j].get("start") is None or out[j].get("end") is None):
            j += 1
        left = out[i - 1]["end"] if i > 0 else seg_start
        right = out[j]["start"] if j < n and out[j].get("start") is not None else seg_end
        span = max(0.0, right - left)
        count = j - i
        chars = [max(1, len(out[k]["text"])) for k in range(i, j)]
        total = float(sum(chars))
        cursor = left
        for idx, k in enumerate(range(i, j)):
            dur = span * (chars[idx] / total) if total else span / count
            out[k]["start"] = round(cursor, 3)
            out[k]["end"] = round(cursor + dur, 3)
            cursor += dur
        i = j
    return out


def _chunk_from_words(words: List[Dict[str, Any]], spaced: bool) -> Dict[str, Any]:
    return {
        "id": new_id(),
        "start": round(words[0]["start"], 3),
        "end": round(words[-1]["end"], 3),
        "text": _join([w["text"] for w in words], spaced),
        "words": [{"text": w["text"], "start": round(w["start"], 3), "end": round(w["end"], 3), "score": w.get("score")} for w in words],
    }


def build_chunks(
    segments: List[Dict[str, Any]],
    max_seconds: float = 12.0,
    min_seconds: float = 1.2,
    max_gap: float = 0.9,
    spaced: bool = True,
) -> List[Dict[str, Any]]:
    chunks: List[Dict[str, Any]] = []
    stream: List[Dict[str, Any]] = []

    def flush_stream() -> None:
        if not stream:
            return
        current: List[Dict[str, Any]] = []
        for w in stream:
            if current:
                prev = current[-1]
                cur_dur = prev["end"] - current[0]["start"]
                gap = w["start"] - prev["end"]
                if gap > max_gap or (SENTENCE_END.search(prev["text"]) and cur_dur >= min_seconds):
                    chunks.append(_chunk_from_words(current, spaced))
                    current = []
                elif w["end"] - current[0]["start"] > max_seconds:
                    split_at = 0
                    for k in range(len(current) - 1, 0, -1):
                        if CLAUSE_END.search(current[k - 1]["text"]) or SENTENCE_END.search(current[k - 1]["text"]):
                            split_at = k
                            break
                    if split_at and current[split_at - 1]["end"] - current[0]["start"] >= min_seconds:
                        chunks.append(_chunk_from_words(current[:split_at], spaced))
                        current = current[split_at:]
                    else:
                        chunks.append(_chunk_from_words(current, spaced))
                        current = []
            current.append(w)
        if current:
            chunks.append(_chunk_from_words(current, spaced))
        stream.clear()

    for seg in sorted(segments, key=lambda s: float(s["start"])):
        text = str(seg.get("text", "")).strip()
        if not text:
            continue
        words = seg.get("words") or []
        if words:
            stream.extend(fill_word_times(words, float(seg["start"]), float(seg["end"])))
        else:
            flush_stream()
            chunks.append({"id": new_id(), "start": round(float(seg["start"]), 3), "end": round(float(seg["end"]), 3), "text": text, "words": []})
    flush_stream()
    return _merge_tiny(chunks, min_seconds, max_seconds, max_gap, spaced)


def _short_text(text: str, spaced: bool) -> bool:
    return len(text.split()) <= 2 if spaced else len(text.replace(" ", "")) <= 4


def _merge_tiny(chunks: List[Dict[str, Any]], min_seconds: float, max_seconds: float, max_gap: float, spaced: bool) -> List[Dict[str, Any]]:
    if not chunks:
        return chunks
    merged: List[Dict[str, Any]] = [chunks[0]]
    for c in chunks[1:]:
        prev = merged[-1]
        prev_short = prev["end"] - prev["start"] < min_seconds * 0.6
        cur_short = c["end"] - c["start"] < min_seconds * 0.6
        close = c["start"] - prev["end"] <= max_gap
        fits = c["end"] - prev["start"] <= max_seconds
        if ((prev_short or cur_short) and close and fits and not SENTENCE_END.search(prev["text"])) or (
            cur_short and close and fits and _short_text(c["text"], spaced)
        ):
            prev["end"] = c["end"]
            prev["text"] = _join([prev["text"], c["text"]], spaced)
            prev["words"] = prev["words"] + c["words"]
        else:
            merged.append(c)
    return merged


def split_segment_words(seg: Dict[str, Any], word_index: int, spaced: bool = True) -> List[Dict[str, Any]]:
    """Split a chunk before ``word_index`` (used by the editor)."""
    words = seg.get("words") or []
    if not 0 < word_index < len(words):
        raise ValueError("word_index must split the segment into two non-empty parts")
    return [_chunk_from_words(words[:word_index], spaced), _chunk_from_words(words[word_index:], spaced)]
