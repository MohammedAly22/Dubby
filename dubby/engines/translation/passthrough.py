from __future__ import annotations

from typing import Any, Dict, Iterator, Sequence, Tuple

from dubby import languages as L
from dubby.engines.base import EngineInfo, TranslationEngine
from dubby.workers.protocol import TaskContext


class PassthroughTranslator(TranslationEngine):
    info = EngineInfo(
        id="passthrough",
        kind="translation",
        name="Keep original text",
        family="core",
        description="No translation: re-voice the video in its own language (e.g. replace the speaker's voice).",
        source_languages=list(L.SOURCE_CODES),
        targets=list(L.TARGET_CODES),
        badges=["same language", "instant"],
    )

    def load(self, ctx: TaskContext) -> None:
        return None

    def translate(self, items: Sequence[Dict[str, Any]], source: str, target: str, ctx: TaskContext) -> Iterator[Tuple[str, str]]:
        if not L.same_language(source, target):
            raise ValueError("'Keep original text' only works when the dub language matches the spoken language.")
        for item in items:
            yield item["id"], item["text"].strip()
