"""Google Gemini translation: context-aware batches sent in parallel.

Each request carries a batch of lines plus the source lines just before and after it, so the
model translates with context while many batches run at the same time. The system prompt is
the same editable template as the Instruct LLM engine.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

from dubby import languages as L
from dubby.engines import gemini_common as G
from dubby.engines.base import EngineInfo, ParamSpec, TranslationEngine
from dubby.engines.translation.llm import DEFAULT_SYSTEM_PROMPT, PLACEHOLDERS, clean_output, render_system_prompt
from dubby.workers.protocol import TaskContext, track

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "translations": {
            "type": "ARRAY",
            "items": {"type": "OBJECT", "properties": {"id": {"type": "STRING"}, "text": {"type": "STRING"}}, "required": ["id", "text"]},
        }
    },
    "required": ["translations"],
}

FORMAT_RULES = (
    "\n\nInput format: JSON with `context_before` and `context_after` (neighbouring source lines, for context only) "
    "and `lines` (objects with `id`, `text` and `seconds`, the spoken slot length). Translate every item in `lines` "
    "and return each `id` exactly once with its translation. Never merge or split lines."
)


class GeminiTranslator(TranslationEngine):
    info = EngineInfo(
        id="gemini-translate",
        kind="translation",
        name="Google Gemini (API)",
        family="cloud",
        description="Context-aware dubbing translation for any language pair. Batches of lines with their neighbours are translated in parallel, so long videos finish in seconds. Editable system prompt. Uses your Gemini API key.",
        source_languages=list(L.SOURCE_CODES),
        targets=list(L.TARGET_CODES),
        requires=["google.genai"],
        install="pip install google-genai",
        badges=["cloud API", "context-aware", "parallel"],
        links={"api key": G.KEY_URL, "models": "https://ai.google.dev/gemini-api/docs/models"},
        params=[
            ParamSpec("model", "Model", "select", "gemini-flash-latest", G.model_options(G.TEXT_MODELS)),
            ParamSpec("system_prompt", "System prompt", "textarea", DEFAULT_SYSTEM_PROMPT, help="Placeholders: " + " ".join("{" + p + "}" for p in PLACEHOLDERS)),
            ParamSpec("temperature", "Temperature", "number", 0.3, min=0, max=1.5, step=0.05, help="0 = most literal and repeatable"),
            ParamSpec("batch_size", "Lines per request", "number", 25, min=1, max=100, step=1),
            ParamSpec("parallel", "Parallel requests", "number", 4, min=1, max=16, step=1),
            ParamSpec("context_lines", "Context lines", "number", 8, min=0, max=40, step=1, help="Source lines before and after each batch shown as context"),
        ],
    )

    @classmethod
    def preview(cls, params: Dict[str, Any], source: Optional[str], target: Optional[str]) -> Dict[str, str]:
        try:
            return {"system_prompt": render_system_prompt(params.get("system_prompt"), source or "en", target or "arz")}
        except KeyError:
            return {}

    def load(self, ctx: TaskContext) -> None:
        G.api_key()
        self.client = G.client()

    def _request(self, system: str, before: List[str], lines: List[Dict[str, Any]], after: List[str]) -> Dict[str, str]:
        from google.genai import types

        model = self.params.get("model") or "gemini-flash-latest"
        payload = {
            "context_before": before,
            "lines": [{"id": it["id"], "text": it["text"].strip(), "seconds": round(float(it.get("duration") or 0), 1)} for it in lines],
            "context_after": after,
        }
        config = types.GenerateContentConfig(
            system_instruction=system + FORMAT_RULES,
            response_mime_type="application/json",
            response_schema=SCHEMA,
            temperature=float(self.params.get("temperature") if self.params.get("temperature") is not None else 0.3),
            thinking_config=G.thinking_off(model),
        )
        with track("translation", f"Gemini translate · {len(lines)} line{'s' if len(lines) != 1 else ''}", model=model, context=len(before) + len(after)):
            response = G.generate(self.client, model, json.dumps(payload, ensure_ascii=False), config)
        data = json.loads(response.text or "{}")
        return {str(t.get("id")): str(t.get("text", "")) for t in data.get("translations", []) if str(t.get("text", "")).strip()}

    def translate(self, items: Sequence[Dict[str, Any]], source: str, target: str, ctx: TaskContext) -> Iterator[Tuple[str, str]]:
        items = list(items)
        system = render_system_prompt(self.params.get("system_prompt"), source, target)
        size = max(1, int(self.params.get("batch_size") or 25))
        context = int(self.params.get("context_lines") or 0)
        batches = [(i, items[i:i + size]) for i in range(0, len(items), size)]

        def run(batch: Tuple[int, List[Dict[str, Any]]]) -> Dict[str, str]:
            start, lines = batch
            before = [it["text"].strip() for it in items[max(0, start - context):start]] if context else []
            after = [it["text"].strip() for it in items[start + len(lines):start + len(lines) + context]] if context else []
            result = self._request(system, before, lines, after)
            missing = [it for it in lines if it["id"] not in result]
            if missing:  # the model skipped some ids: ask again for just those
                result.update(self._request(system, before, missing, after))
            return result

        missing_total = 0
        for (_, lines), result in G.run_parallel(run, batches, int(self.params.get("parallel") or 4)):
            for it in lines:
                if it["id"] in result:
                    yield it["id"], clean_output(result[it["id"]])
                else:
                    missing_total += 1
        if missing_total:
            raise RuntimeError(f"Gemini returned no translation for {missing_total} segment(s); retranslate them to try again.")
