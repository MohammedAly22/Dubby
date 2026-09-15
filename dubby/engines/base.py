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
    type: str = "text"  # select | number | bool | text
    default: Any = None
    options: Optional[List[Dict[str, Any]]] = None
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    help: str = ""


def option(value: Any, label: Optional[str] = None) -> Dict[str, Any]:
    return {"value": value, "label": label or str(value)}


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
