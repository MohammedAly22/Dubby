from __future__ import annotations

from dubby.engines.base import EngineInfo, ParamSpec, SeparationEngine, option
from dubby.workers.protocol import TaskContext


class DemucsEngine(SeparationEngine):
    info = EngineInfo(
        id="demucs",
        kind="separation",
        name="Demucs v4",
        family="core",
        description="Hybrid Transformer Demucs: removes the original voice and keeps music & ambience under the dub.",
        requires=["demucs"],
        install="pip install demucs",
        badges=["background music"],
        links={"code": "https://github.com/adefossez/demucs"},
        params=[ParamSpec("model", "Model", "select", "htdemucs", [option("htdemucs"), option("htdemucs_ft"), option("mdx_extra")])],
    )
    load_params = ("model",)

    def load(self, ctx: TaskContext) -> None:
        from demucs.pretrained import get_model

        ctx.progress(0.02, f"Loading Demucs {self.params['model']}…")
        self.model = get_model(self.params["model"]).to(self.device).eval()

    def separate(self, audio_path: str, vocals_out: str, background_out: str, ctx: TaskContext) -> None:
        import numpy as np
        import soundfile as sf
        import torch
        from demucs.apply import apply_model

        wav, sr = sf.read(audio_path, dtype="float32", always_2d=True)
        if sr != self.model.samplerate:
            import librosa

            wav = librosa.resample(wav.T, orig_sr=sr, target_sr=self.model.samplerate).T
            sr = self.model.samplerate
        if wav.shape[1] == 1:
            wav = np.repeat(wav, 2, axis=1)
        mix = torch.from_numpy(np.ascontiguousarray(wav.T[:2]))
        ref = mix.mean(0)
        mean, std = ref.mean(), ref.std() + 1e-8
        ctx.progress(0.1, "Separating vocals from background…")
        with torch.inference_mode():
            sources = apply_model(self.model, ((mix - mean) / std)[None], device=self.device, split=True, overlap=0.25, progress=False)[0]
        sources = sources * std + mean
        vocals = sources[self.model.sources.index("vocals")]
        background = sources.sum(0) - vocals
        sf.write(vocals_out, vocals.cpu().numpy().T, sr)
        sf.write(background_out, background.cpu().numpy().T, sr)
        ctx.progress(1.0, "Separation finished")
