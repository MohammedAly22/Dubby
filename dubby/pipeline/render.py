"""Final mix: place every dubbed clip on the original timeline and mux with the video."""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Callable, Dict, List

import numpy as np

from dubby.media import ffmpeg
from dubby.pipeline.subtitles import write_srt, write_vtt
from dubby.schemas import Project

MIX_SR = 44100
ProgressFn = Callable[[float, str], None]


def _load(path: Path, sr: int = MIX_SR, mono: bool = False) -> np.ndarray:
    import soundfile as sf

    data, file_sr = sf.read(str(path), dtype="float32", always_2d=True)  # (T, C)
    if file_sr != sr:
        import librosa

        data = librosa.resample(data.T, orig_sr=file_sr, target_sr=sr).T
    if mono:
        return np.ascontiguousarray(data.mean(axis=1))
    if data.shape[1] == 1:
        data = np.repeat(data, 2, axis=1)
    return np.ascontiguousarray(data[:, :2])


def _fit_length(x: np.ndarray, n: int) -> np.ndarray:
    if len(x) >= n:
        return x[:n]
    pad = np.zeros((n - len(x),) + x.shape[1:], dtype=x.dtype)
    return np.concatenate([x, pad])


def _smooth(env: np.ndarray, ramp_seconds: float = 0.12) -> np.ndarray:
    k = max(1, int(ramp_seconds * MIX_SR))
    kernel = np.ones(k, dtype=np.float32) / k
    return np.convolve(env, kernel, mode="same").astype(np.float32)


def render_project(project: Project, project_dir: Path, progress: ProgressFn) -> Dict:
    mix_cfg = project.settings.mix
    src = project.source
    if not src.audio_hq or not src.video:
        raise RuntimeError("Source media is missing — download the video first.")
    voiced = sorted([s for s in project.segments if s.tts.status == "done" and s.tts.audio], key=lambda s: s.start)
    if not voiced:
        raise RuntimeError("No voiced segments yet — generate the dubbed audio first.")

    progress(0.02, "Loading original audio…")
    original = _load(project_dir / src.audio_hq)
    total = len(original)
    total_s = total / MIX_SR

    # --------------------------------------------------------------- background
    if mix_cfg.background == "separated":
        if not src.background:
            raise RuntimeError("Background stem not available — run vocal separation first or pick another background mode.")
        background = _fit_length(_load(project_dir / src.background), total) * float(mix_cfg.outside_volume)
    elif mix_cfg.background == "original":
        env = np.full(total, float(mix_cfg.outside_volume), dtype=np.float32)
        for seg in voiced:
            a = max(0, int((seg.start - 0.15) * MIX_SR))
            b = min(total, int((seg.end + 0.15) * MIX_SR))
            env[a:b] = float(mix_cfg.background_volume)
        background = original * _smooth(env)[:, None]
    else:
        background = np.zeros_like(original)

    # --------------------------------------------------------------- dub track
    dub = np.zeros(total, dtype=np.float32)
    stats = {"placed": 0, "stretched": 0, "trimmed": 0, "max_rate": 1.0}
    clips: List[Dict] = []
    fade = int(0.04 * MIX_SR)
    with tempfile.TemporaryDirectory(prefix="dubby-render-") as tmp:
        for i, seg in enumerate(voiced):
            clip_path = project_dir / seg.tts.audio  # type: ignore[operator]
            if not clip_path.exists():
                continue
            nxt = voiced[i + 1].start if i + 1 < len(voiced) else total_s
            available = max(0.25, nxt - seg.start)
            clip = _load(clip_path, mono=True)
            length = len(clip) / MIX_SR
            rate = 1.0
            if mix_cfg.fit_mode == "stretch" and length > available * 1.02:
                rate = min(length / available, float(mix_cfg.max_speedup))
                if rate > 1.01:
                    import soundfile as sf

                    a, b = Path(tmp) / f"{seg.id}_in.wav", Path(tmp) / f"{seg.id}_out.wav"
                    sf.write(a, clip, MIX_SR)
                    ffmpeg.atempo(a, b, rate)
                    clip = _load(b, mono=True)
                    stats["stretched"] += 1
                    stats["max_rate"] = max(stats["max_rate"], round(rate, 3))
            limit = int(available * MIX_SR)
            if mix_cfg.fit_mode in ("stretch", "trim") and len(clip) > limit:
                clip = clip[:limit].copy()
                n = min(fade, len(clip))
                clip[-n:] *= np.linspace(1.0, 0.0, n, dtype=np.float32)
                stats["trimmed"] += 1
            start = int(seg.start * MIX_SR)
            end = min(total, start + len(clip))
            if end > start:
                dub[start:end] += clip[: end - start]
                stats["placed"] += 1
                clips.append({"id": seg.id, "start": round(start / MIX_SR, 3), "end": round(end / MIX_SR, 3), "rate": round(rate, 3)})
            progress(0.05 + 0.6 * (i + 1) / len(voiced), f"Placed {i + 1}/{len(voiced)} dubbed clips")

    progress(0.7, "Mixing…")
    mix = background + dub[:, None] * float(mix_cfg.dub_volume)
    peak = float(np.abs(mix).max()) if mix.size else 0.0
    if peak > 0.98:
        mix *= 0.98 / peak

    import soundfile as sf

    version = project.render.version + 1
    out_dir = project_dir / "render"
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*"):
        if old.is_file():
            old.unlink(missing_ok=True)
    mix_path = out_dir / f"dub_mix_v{version}.wav"
    voice_path = out_dir / f"dub_voice_v{version}.wav"
    sf.write(mix_path, mix, MIX_SR)
    sf.write(voice_path, np.clip(dub, -1, 1), MIX_SR)

    progress(0.8, "Writing subtitles…")
    subtitles: Dict[str, str] = {}
    mux_subs: List = []
    srt_ar = write_srt(project.segments, out_dir / f"subtitles_ar_v{version}.srt", "translation")
    srt_src = write_srt(project.segments, out_dir / f"subtitles_{project.settings.source_language}_v{version}.srt", "text")
    subtitles["ar_vtt"] = write_vtt(project.segments, out_dir / f"subtitles_ar_v{version}.vtt", "translation").name
    subtitles["src_vtt"] = write_vtt(project.segments, out_dir / f"subtitles_src_v{version}.vtt", "text").name
    subtitles["ar_srt"], subtitles["src_srt"] = srt_ar.name, srt_src.name
    if mix_cfg.subtitles:
        mux_subs = [(srt_ar, "ara"), (srt_src, "eng" if project.settings.source_language == "en" else "ara")]

    progress(0.88, "Muxing video…")
    video_out = out_dir / f"dubbed_v{version}.mp4"
    ffmpeg.mux(project_dir / src.video, mix_path, video_out, mux_subs)
    progress(1.0, "Render complete")
    return {
        "version": version,
        "video": f"render/{video_out.name}",
        "mix": f"render/{mix_path.name}",
        "voice": f"render/{voice_path.name}",
        "subtitles": {k: f"render/{v}" for k, v in subtitles.items()},
        "created_at": time.time(),
        "clips": clips,
        "stats": stats,
    }
