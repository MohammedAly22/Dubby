"""Shared ASR building blocks: audio loading, VAD chunking and forced alignment."""

from __future__ import annotations

import gc
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple, TypeVar

import numpy as np

from dubby.workers.protocol import TaskContext

SR = 16000
T = TypeVar("T")


def load_audio(path: str, sr: int = SR) -> np.ndarray:
    import soundfile as sf

    audio, file_sr = sf.read(path, dtype="float32", always_2d=True)
    audio = audio.mean(axis=1)
    if file_sr != sr:
        import librosa

        audio = librosa.resample(audio, orig_sr=file_sr, target_sr=sr)
    return np.ascontiguousarray(audio, dtype=np.float32)


def batched(items: Sequence[T], size: int) -> Iterator[List[T]]:
    size = max(1, int(size))
    for i in range(0, len(items), size):
        yield list(items[i:i + size])


def vad_regions(
    audio: np.ndarray,
    max_chunk: float = 25.0,
    merge_gap: float = 0.6,
    min_silence_ms: int = 300,
    speech_pad_ms: int = 150,
    sr: int = SR,
) -> List[Tuple[float, float]]:
    """Speech regions from Silero VAD merged into chunks no longer than ``max_chunk``."""
    import torch
    from silero_vad import get_speech_timestamps, load_silero_vad

    model = load_silero_vad()
    stamps = get_speech_timestamps(
        torch.from_numpy(audio),
        model,
        sampling_rate=sr,
        return_seconds=True,
        min_silence_duration_ms=min_silence_ms,
        speech_pad_ms=speech_pad_ms,
    )
    total = len(audio) / sr
    pieces: List[Tuple[float, float]] = []
    for st in stamps:
        s, e = float(st["start"]), min(float(st["end"]), total)
        while e - s > max_chunk:
            pieces.append((s, s + max_chunk))
            s += max_chunk
        if e - s > 0.05:
            pieces.append((s, e))
    chunks: List[Tuple[float, float]] = []
    for s, e in pieces:
        if chunks and s - chunks[-1][1] <= merge_gap and e - chunks[-1][0] <= max_chunk:
            chunks[-1] = (chunks[-1][0], e)
        else:
            chunks.append((s, e))
    return [(round(s, 3), round(e, 3)) for s, e in chunks]


def bundled_silero_vad(base_cls: Any, onset: float = 0.5, chunk_size: float = 30.0) -> Any:
    """A WhisperX/CohereX-compatible Silero VAD loaded from the pip ``silero-vad`` package.

    The upstream classes fetch the model through ``torch.hub`` (GitHub at runtime);
    this subclass keeps their interface but uses the weights bundled in the wheel.
    """
    from silero_vad import get_speech_timestamps, load_silero_vad

    class BundledSilero(base_cls):  # type: ignore[misc, valid-type]
        def __init__(self) -> None:
            base_cls.__mro__[1].__init__(self, onset)
            self.vad_onset = onset
            self.chunk_size = chunk_size
            self.vad_pipeline = load_silero_vad()
            self.get_speech_timestamps = get_speech_timestamps

    return BundledSilero()


def clip(audio: np.ndarray, start: float, end: float, sr: int = SR) -> np.ndarray:
    return audio[int(start * sr):int(end * sr)]


def align_words(
    segments: List[Dict[str, Any]],
    audio: np.ndarray,
    language: str,
    device: str,
    ctx: TaskContext,
    model_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Word timestamps via WhisperX wav2vec2 forced alignment.

    Works for any engine that only returns chunk-level text. On failure the
    segments are returned unchanged (word times are interpolated later).
    """
    if not segments:
        return segments
    from dubby import languages

    lang = languages.iso(language) if language in languages.LANGUAGES else language
    try:
        import whisperx

        ctx.progress(0.8, f"Loading {lang} alignment model…")
        dev = "cuda" if str(device).startswith("cuda") else "cpu"
        model_a, metadata = whisperx.load_align_model(language_code=lang, device=dev, model_name=model_name or None)
        ctx.progress(0.85, "Aligning words to audio…")
        payload = [{"start": s["start"], "end": s["end"], "text": s["text"]} for s in segments]
        result = whisperx.align(payload, model_a, metadata, audio, dev, return_char_alignments=False)
        del model_a
        gc.collect()
    except Exception as exc:  # alignment is an enhancement, never a hard failure
        ctx.log(f"Forced alignment failed ({exc}); keeping chunk-level timestamps.", "warning")
        return segments
    out = []
    for seg in result.get("segments", []):
        text = str(seg.get("text", "")).strip()
        if not text:
            continue
        out.append({
            "start": float(seg["start"]),
            "end": float(seg["end"]),
            "text": text,
            "words": [
                {"text": w.get("word", ""), "start": w.get("start"), "end": w.get("end"), "score": w.get("score")}
                for w in seg.get("words", [])
            ],
        })
    return out or segments


def plain_segments(regions: Iterable[Tuple[float, float]], texts: Iterable[str]) -> List[Dict[str, Any]]:
    return [
        {"start": s, "end": e, "text": t.strip(), "words": []}
        for (s, e), t in zip(regions, texts)
        if t and t.strip()
    ]
