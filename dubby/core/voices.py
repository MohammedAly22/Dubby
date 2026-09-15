"""Reference voices: built-in presets and reference clips for OmniVoice cloning."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

PRESET_REPO = "mohammedaly22/VoiceTut-TTS"
REF_SR = 24000


@lru_cache(maxsize=1)
def _preset_dir() -> Path:
    from huggingface_hub import snapshot_download

    return Path(snapshot_download(PRESET_REPO, allow_patterns=["reference_speakers/*"])) / "reference_speakers"


def list_presets() -> List[Dict]:
    """The 17 VoiceTut studio voices — usable as references by every OmniVoice engine."""
    base = _preset_dir()
    entries = json.loads((base / "references.json").read_text(encoding="utf-8"))
    out = []
    for e in entries:
        audio = base / Path(e["audio_path"]).name
        out.append({
            "id": e["speaker_name"],
            "name": e["speaker_name"],
            "gender": e.get("gender", ""),
            "text": e["reference_text"],
            "audio": str(audio),
            "filename": audio.name,
        })
    return out


def get_preset(name: str) -> Dict:
    for p in list_presets():
        if p["id"].lower() == name.lower():
            return p
    raise KeyError(f"Unknown preset voice '{name}'")


def cut_reference(source: Path, start: float, end: float, out: Path, sr: int = REF_SR) -> float:
    """Cut ``[start, end]`` from ``source`` into a mono, peak-normalized reference wav."""
    import soundfile as sf

    info = sf.info(str(source))
    a = max(0, int(start * info.samplerate))
    b = min(info.frames, int(end * info.samplerate))
    if b - a < int(0.5 * info.samplerate):
        raise ValueError("Reference clip must be at least 0.5 s long")
    data, file_sr = sf.read(str(source), start=a, stop=b, dtype="float32", always_2d=True)
    mono = data.mean(axis=1)
    if file_sr != sr:
        import librosa

        mono = librosa.resample(mono, orig_sr=file_sr, target_sr=sr)
    peak = float(np.abs(mono).max()) or 1.0
    mono = mono * (0.95 / peak)
    out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out), mono, sr)
    return len(mono) / sr


def convert_upload(src: Path, out: Path, max_seconds: Optional[float] = 20.0) -> float:
    import soundfile as sf

    try:
        data, sr = sf.read(str(src), dtype="float32", always_2d=True)
    except Exception:
        from dubby.media import ffmpeg

        tmp = src.with_suffix(".conv.wav")
        ffmpeg.run(["-i", str(src), "-ac", "1", "-ar", str(REF_SR), str(tmp)])
        data, sr = sf.read(str(tmp), dtype="float32", always_2d=True)
    duration = len(data) / sr
    end = min(duration, max_seconds) if max_seconds else duration
    sf.write(str(src.with_suffix(".full.wav")), data, sr)
    return cut_reference(src.with_suffix(".full.wav"), 0.0, end, out)
