"""Project data model shared by the server, the workers and the UI."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from dubby import languages

StageName = Literal["download", "langid", "asr", "translation", "voice", "tts", "separation", "render"]
STAGES: List[str] = ["download", "langid", "asr", "translation", "voice", "tts", "separation", "render", "captions", "export"]
StageStatus = Literal["idle", "queued", "running", "done", "error", "cancelled", "paused"]  # paused: stopped by a quota, partial results kept


class StageState(BaseModel):
    status: StageStatus = "idle"
    progress: float = 0.0
    message: str = ""
    engine: Optional[str] = None
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    error: Optional[str] = None


class Word(BaseModel):
    text: str
    start: float
    end: float
    score: Optional[float] = None


class TTSState(BaseModel):
    status: Literal["pending", "queued", "running", "done", "error"] = "pending"
    audio: Optional[str] = None  # path relative to the project dir
    duration: Optional[float] = None
    text: Optional[str] = None  # the text that produced `audio` (as written in the translation)
    normalized: Optional[str] = None  # what the TTS model actually received after normalization (None = off)
    engine: Optional[str] = None
    version: int = 0
    error: Optional[str] = None


class Segment(BaseModel):
    id: str
    start: float
    end: float
    text: str
    words: List[Word] = Field(default_factory=list)
    translation: str = ""
    translation_status: Literal["pending", "queued", "running", "done", "error"] = "pending"
    translation_source: Optional[str] = None  # source text that produced `translation`
    translation_error: Optional[str] = None
    tts: TTSState = Field(default_factory=TTSState)
    # word timings of the dubbed speech on the rendered timeline (for highlighted dub captions)
    dub_words: List[Word] = Field(default_factory=list)

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


class EngineChoice(BaseModel):
    engine: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)


class MixConfig(BaseModel):
    background: Literal["original", "separated", "none"] = "original"
    background_volume: float = 0.15  # original/background level under the dub
    outside_volume: float = 1.0  # original level between dubbed segments ("original" mode)
    dub_volume: float = 1.0
    fit_mode: Literal["stretch", "trim", "none"] = "stretch"
    max_speedup: float = 1.35
    subtitles: bool = True
    # captions drawn into the exported video frames, with per-word highlighting
    burn_captions: Literal["none", "original", "dub", "both"] = "none"


class VoiceConfig(BaseModel):
    mode: Literal["preset", "clip", "upload", "auto"] = "preset"
    preset: Optional[str] = "Mohamed"
    clip_start: Optional[float] = None
    clip_end: Optional[float] = None
    ref_audio: Optional[str] = None  # relative path of the prepared reference wav
    ref_text: str = ""
    ref_language: Optional[str] = None  # spoken language of the reference clip
    ref_text_status: Literal["idle", "queued", "running", "done", "error"] = "idle"
    upload_name: Optional[str] = None


class ProjectSettings(BaseModel):
    source_language: str = "en"
    target: str = "arz"
    asr: EngineChoice = Field(default_factory=lambda: EngineChoice(engine="whisperx"))
    translation: EngineChoice = Field(default_factory=lambda: EngineChoice(engine="emhotob"))
    tts: EngineChoice = Field(default_factory=lambda: EngineChoice(engine="voicetut"))
    mix: MixConfig = Field(default_factory=MixConfig)
    # dubbing chunk builder
    max_chunk_seconds: float = 12.0
    min_chunk_seconds: float = 1.2
    max_word_gap: float = 0.9

    @field_validator("source_language")
    @classmethod
    def _valid_source(cls, v: str) -> str:
        if v not in languages.SOURCE_CODES:
            raise ValueError(f"unsupported spoken language '{v}' (supported: {', '.join(languages.SOURCE_CODES)})")
        return v

    @field_validator("target")
    @classmethod
    def _valid_target(cls, v: str) -> str:
        if v not in languages.TARGET_CODES:
            raise ValueError(f"unsupported dub language '{v}' (supported: {', '.join(languages.TARGET_CODES)})")
        return v


class SourceInfo(BaseModel):
    kind: Literal["youtube", "upload"] = "youtube"
    url: Optional[str] = None
    title: Optional[str] = None
    uploader: Optional[str] = None
    duration: Optional[float] = None
    thumbnail: Optional[str] = None
    video: Optional[str] = None  # relative paths
    audio16k: Optional[str] = None
    audio_hq: Optional[str] = None
    vocals: Optional[str] = None
    background: Optional[str] = None
    # spoken-language detection
    auto_detect: bool = False
    detected_language: Optional[str] = None  # raw ISO code from the detector
    detected_probability: Optional[float] = None
    detected_candidates: List[List[Any]] = Field(default_factory=list)


class ExportItem(BaseModel):
    kind: str
    path: str  # absolute path on disk
    rel: Optional[str] = None  # path inside the project (for download)
    size: int = 0
    created_at: float = Field(default_factory=time.time)


class RenderInfo(BaseModel):
    video: Optional[str] = None
    mix: Optional[str] = None
    voice: Optional[str] = None
    subtitles: Dict[str, str] = Field(default_factory=dict)
    version: int = 0
    created_at: Optional[float] = None
    # where each dubbed clip sits in the render: [{id, start, end, rate}]
    clips: List[Dict[str, Any]] = Field(default_factory=list)
    # dub caption timing: {"method": "estimated" | "aligned", "aligned": n, "total": n}
    captions: Dict[str, Any] = Field(default_factory=dict)
    # videos with burned-in captions, by mode ("original" | "dub" | "both")
    burned: Dict[str, str] = Field(default_factory=dict)


class Project(BaseModel):
    id: str
    title: str = "Untitled"
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    source: SourceInfo = Field(default_factory=SourceInfo)
    settings: ProjectSettings = Field(default_factory=ProjectSettings)
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    stages: Dict[str, StageState] = Field(default_factory=lambda: {s: StageState() for s in STAGES})
    segments: List[Segment] = Field(default_factory=list)
    render: RenderInfo = Field(default_factory=RenderInfo)
    exports: List[ExportItem] = Field(default_factory=list)

    def segment(self, seg_id: str) -> Segment:
        for s in self.segments:
            if s.id == seg_id:
                return s
        raise KeyError(f"segment {seg_id} not found")

    def summary(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "source": self.source.model_dump(),
            "settings": {"source_language": self.settings.source_language, "target": self.settings.target},
            "stages": {k: v.model_dump() for k, v in self.stages.items()},
            "segments": len(self.segments),
            "translated": sum(1 for s in self.segments if s.translation_status == "done"),
            "voiced": sum(1 for s in self.segments if s.tts.status == "done"),
            "render": self.render.model_dump(),
        }
