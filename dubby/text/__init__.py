"""Text normalization for TTS, per dub language.

    from dubby.text import normalize
    normalize("Meet me at 3:30 pm, it costs $12.50", "en")
    # → "Meet me at three thirty p m, it costs twelve dollars and fifty cents"

* Egyptian Arabic (``arz``) uses the VoiceTut-TTS pipeline without diacritics (``dubby.text.arz``).
* Every other language runs the shared pipeline (``dubby.text.common``) with its own rules:
  numbers, decimals, ordinals, money, percentages, units, dates, times, phone numbers,
  emails, URLs, handles, hashtags, abbreviations, symbols and acronyms.

Adding a language: subclass :class:`dubby.text.common.Rules` and register it in ``_RULES``.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Callable, Optional, Tuple

_RULES = {
    "en": ("dubby.text.en", "EnglishRules"),
    "es": ("dubby.text.es", "SpanishRules"),
    "fr": ("dubby.text.fr", "FrenchRules"),
    "it": ("dubby.text.it", "ItalianRules"),
    "arb": ("dubby.text.arb", "MSARules"),
    "hi": ("dubby.text.hi", "HindiRules"),
    "zh": ("dubby.text.zh", "ChineseRules"),
    "ja": ("dubby.text.ja", "JapaneseRules"),
}
SUPPORTED = ("arz", *_RULES)


@lru_cache(maxsize=None)
def normalizer_for(language: str) -> Callable[[str], str]:
    """The normalizer for a dub language code (``KeyError`` if unsupported)."""
    if language == "arz":
        from dubby.text.arz import EgyptianNormalizer

        return EgyptianNormalizer()
    import importlib

    from dubby.text.common import Normalizer

    module, cls = _RULES[language]
    return Normalizer(getattr(importlib.import_module(module), cls)())


def normalize(text: str, language: str) -> str:
    """Normalize ``text`` for ``language``. Unsupported languages only get whitespace cleanup."""
    if language not in SUPPORTED:
        return " ".join((text or "").split())
    return normalizer_for(language)(text or "")


def normalize_safe(text: str, language: str) -> Tuple[str, Optional[str]]:
    """Like :func:`normalize`, but never raises: returns ``(text, error)`` and falls back to the raw text."""
    try:
        return normalize(text, language), None
    except Exception as exc:  # a normalization bug must never block voice generation
        return " ".join((text or "").split()), f"{type(exc).__name__}: {exc}"
