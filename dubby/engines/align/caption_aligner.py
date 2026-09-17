"""Word timings for the dub captions: wav2vec2 forced alignment on the rendered dub voice track.

After a render, each placed clip (already sped up / trimmed exactly as in the final video) is
aligned against its translated text on the clean voice-only track, so the highlighted words
in burned-in captions follow the dubbed speech. Words the aligner can't place (numbers,
symbols) get interpolated times.
"""

from __future__ import annotations

from typing import Any, Dict, List

from dubby import languages as L
from dubby.engines.base import Engine, EngineInfo
from dubby.pipeline.captions import estimate_words
from dubby.workers.protocol import TaskContext, track


class CaptionAligner(Engine):
    info = EngineInfo(
        id="caption-align",
        kind="alignment",
        name="Dub caption aligner (wav2vec2)",
        family="core",
        description="Forced alignment of the rendered dub audio for word-highlighted captions.",
        targets=list(L.TARGET_CODES),
        requires=["whisperx"],
        install="pip install whisperx",
    )

    def load(self, ctx: TaskContext) -> None:
        return None  # the alignment model depends on the language: loaded in align()

    def align(self, payload: Dict[str, Any], ctx: TaskContext) -> Dict[str, Any]:
        import whisperx

        from dubby.engines.asr.common import load_audio
        from dubby.pipeline.chunking import fill_word_times

        language = payload["language"]
        iso = L.iso(language) if language in L.LANGUAGES else language
        device = "cuda" if self.is_cuda else "cpu"
        ctx.progress(0.02, "Loading the dub audio…")
        audio = load_audio(payload["audio"])
        with track("model", f"Load wav2vec2 aligner · {iso}"):
            model, metadata = whisperx.load_align_model(language_code=iso, device=device)
        segments: List[Dict[str, Any]] = payload["segments"]
        aligned = 0
        for index, seg in enumerate(segments, start=1):
            text = str(seg.get("text", "")).strip()
            words: List[Dict[str, Any]] = []
            if text:
                try:
                    with track("alignment", f"Align dub clip {index}/{len(segments)}", clip=seg["id"]):
                        result = whisperx.align([{"start": seg["start"], "end": seg["end"], "text": text}], model, metadata, audio, device, return_char_alignments=False)
                    words = [
                        {"text": w.get("word", ""), "start": w.get("start"), "end": w.get("end")}
                        for part in result.get("segments", [])
                        for w in part.get("words", [])
                    ]
                    if any(w["start"] is not None for w in words):
                        aligned += 1
                    else:
                        words = []
                except Exception as exc:  # one bad clip must not stop the rest
                    ctx.log(f"Alignment failed for clip {seg['id']} ({exc}); using estimated timing.", "warning")
            if not words:
                words = estimate_words(text, float(seg["start"]), float(seg["end"]), language)
            words = fill_word_times(words, float(seg["start"]), float(seg["end"]))
            ctx.result("caption_words", {"id": seg["id"], "words": words})
            ctx.progress(index / max(1, len(segments)), f"Aligned {index}/{len(segments)} dub clips")
        return {"aligned": aligned, "total": len(segments)}
