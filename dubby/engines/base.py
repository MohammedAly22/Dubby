"""Engine contracts.

Engine modules must stay importable without their heavy dependencies: import
``torch``/``transformers``/model packages *inside* methods, never at module level.
The studio imports engine classes only to read their :class:`EngineInfo`.
"""

from __future__ import annotations

import gc
from dataclasses import asdict, dataclass, field
from typing import Any, ClassVar, Dict, Iterator, List, Optional, Sequence, Tuple

from dubby.workers.protocol import TaskContext


@dataclass
class ParamSpec:
    key: str
    label: str
    type: str = "text"  # select | number | bool | text | textarea
    default: Any = None
    options: Optional[List[Dict[str, Any]]] = None
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    help: str = ""


def option(value: Any, label: Optional[str] = None) -> Dict[str, Any]:
    return {"value": value, "label": label or str(value)}


QUANTIZATION_LABELS = {
    "auto": "Auto — 16-bit if it fits this GPU, otherwise 4-bit",
    "none": "None (16-bit)",
    "8bit": "8-bit (bitsandbytes)",
    "4bit": "4-bit NF4 (bitsandbytes)",
}


def quantization_param(modes: Sequence[str] = ("none", "8bit", "4bit"), default: str = "auto") -> ParamSpec:
    """Standard ``quantization`` parameter; pair it with :func:`resolve_quantization`."""
    return ParamSpec(
        "quantization",
        "Quantization",
        "select",
        default,
        [option(m, QUANTIZATION_LABELS[m]) for m in ("auto", *modes)],
        help="Lower precision needs less VRAM (4-bit ≈ ⅓ of 16-bit) with a small quality cost. 8/4-bit need an NVIDIA GPU.",
    )


def resolve_quantization(mode: str, sizes: Dict[str, float], vram_gb: Optional[float]) -> str:
    """Turn ``auto`` into 16-bit when it fits ``vram_gb``, otherwise 4-bit.

    8-bit is only used when chosen explicitly: bitsandbytes' int8 kernels are several
    times slower than NF4 4-bit, so 4-bit is both lighter and faster on small GPUs.
    """
    if mode != "auto":
        return mode
    if vram_gb is None:
        return "none"  # CPU (or unknown): full precision
    for candidate in ("none", "4bit", "8bit"):
        if candidate in sizes and sizes[candidate] <= vram_gb + 0.1:
            return candidate
    return min(sizes, key=lambda k: sizes[k])


@dataclass
class EngineInfo:
    id: str
    kind: str  # asr | translation | tts | separation
    name: str
    family: str = "core"
    description: str = ""
    source_languages: List[str] = field(default_factory=list)  # en / ar
    targets: List[str] = field(default_factory=list)  # arz / arb (translation & tts)
    requires: List[str] = field(default_factory=list)  # importable top-level modules
    install: str = ""
    params: List[ParamSpec] = field(default_factory=list)
    links: Dict[str, str] = field(default_factory=dict)
    gated: bool = False
    badges: List[str] = field(default_factory=list)
    vram_gb: Optional[float] = None  # approximate GPU memory at default params (see Engine.required_vram_gb)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def defaults(self) -> Dict[str, Any]:
        return {p.key: p.default for p in self.params}


class Engine:
    info: ClassVar[EngineInfo]
    # Parameters whose change requires reloading the model.
    load_params: ClassVar[Tuple[str, ...]] = ()

    def __init__(self, device: str, params: Dict[str, Any]):
        self.device = device
        self.params = {**self.info.defaults(), **(params or {})}

    @classmethod
    def load_key(cls, params: Dict[str, Any]) -> Tuple:
        merged = {**cls.info.defaults(), **(params or {})}
        return (cls.info.id,) + tuple(str(merged.get(k)) for k in cls.load_params)

    # --------------------------------------------------------------- hardware
    @classmethod
    def required_vram_gb(cls, params: Dict[str, Any], vram_gb: Optional[float] = None) -> Optional[float]:
        """Approximate GPU memory (GB) needed with ``params``; ``None`` means small or unknown.

        ``vram_gb`` is the detected GPU size so ``quantization="auto"`` can resolve. The
        worker refuses to load a model that cannot fit, and the UI greys out options
        that exceed the GPU — so keep these estimates honest (weights + working memory).
        """
        return cls.info.vram_gb

    @classmethod
    def needs_cuda(cls, params: Dict[str, Any], vram_gb: Optional[float] = None) -> bool:
        """True when these params cannot run on CPU (e.g. bitsandbytes checkpoints)."""
        return False

    @classmethod
    def preview(cls, params: Dict[str, Any], source: Optional[str], target: Optional[str]) -> Dict[str, str]:
        """Resolved values shown under the parameters in the UI (e.g. a prompt template)."""
        return {}

    def load(self, ctx: TaskContext) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def unload(self) -> None:
        for name in list(vars(self)):
            if name not in ("device", "params"):
                setattr(self, name, None)
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    # helpers ---------------------------------------------------------------
    @property
    def is_cuda(self) -> bool:
        return str(self.device).startswith("cuda")

    def torch_dtype(self, prefer: str = "bfloat16"):
        import torch

        if not self.is_cuda:
            return torch.float32
        if prefer == "bfloat16" and not torch.cuda.is_bf16_supported():
            return torch.float16
        return getattr(torch, prefer)

    def gpu_vram_gb(self) -> Optional[float]:
        if not self.is_cuda:
            return None
        import torch

        return torch.cuda.get_device_properties(0).total_memory / 1024**3

    def quantization_config(self, mode: str):
        """``BitsAndBytesConfig`` for ``8bit``/``4bit`` (``None`` for full precision)."""
        if mode not in ("8bit", "4bit"):
            return None
        if not self.is_cuda:
            raise RuntimeError("bitsandbytes quantization requires a CUDA GPU")
        from transformers import BitsAndBytesConfig

        if mode == "8bit":
            return BitsAndBytesConfig(load_in_8bit=True)
        return BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=self.torch_dtype(),
        )


class ASREngine(Engine):
    def transcribe(self, audio_path: str, language: str, ctx: TaskContext) -> List[Dict[str, Any]]:
        """Return raw segments: ``[{start, end, text, words: [{text,start,end,score}]}]``.

        Implementations should call ``ctx.result("asr_partial", {"segments": [...]})``
        whenever new text is available so the UI can show it live.
        """
        raise NotImplementedError


class TranslationEngine(Engine):
    def supports(self, source: str, target: str) -> bool:
        return source in self.info.source_languages and target in self.info.targets

    def translate(
        self, items: Sequence[Dict[str, Any]], source: str, target: str, ctx: TaskContext
    ) -> Iterator[Tuple[str, str]]:
        """Yield ``(segment_id, translation)`` one by one as they are ready."""
        raise NotImplementedError


@dataclass
class TTSItem:
    id: str
    text: str
    out_path: str
    ref_audio: Optional[str] = None
    ref_text: Optional[str] = None
    duration: Optional[float] = None  # target duration in seconds (slot length)


class TTSEngine(Engine):
    def synthesize(self, items: Sequence[TTSItem], target: str, ctx: TaskContext) -> Iterator[Tuple[TTSItem, float]]:
        """Write each item's wav to ``out_path`` and yield ``(item, duration_seconds)``."""
        raise NotImplementedError

    def presets(self) -> List[Dict[str, Any]]:
        return []


class SeparationEngine(Engine):
    def separate(self, audio_path: str, vocals_out: str, background_out: str, ctx: TaskContext) -> None:
        raise NotImplementedError
