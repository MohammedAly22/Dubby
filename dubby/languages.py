"""Language registry: codes, scripts and per-engine identifiers.

Dubby language codes:
  * source (spoken) languages: en · ar · es · fr · it · hi · zh · ja
  * target (dub) languages:    arz · arb · en · es · fr · it · hi · zh · ja
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, Iterable, List


@dataclass(frozen=True)
class Language:
    code: str
    name: str
    native: str
    flag: str  # UI flag asset key
    iso: str  # ISO 639-1 code used by ASR engines and aligners
    omnivoice: str  # OmniVoice language id
    nllb: str  # NLLB-200 / IndicTrans2 FLORES code
    qwen: str  # language name for Qwen3-ASR / Qwen3-TTS
    prompt_name: str  # English name used in translation prompts
    prompt_name_zh: str  # Chinese name (Hunyuan-MT template when Chinese is involved)
    spaced: bool = True  # False for scripts written without spaces between words
    rtl: bool = False
    source: bool = True
    target: bool = True
    omnivoice_hours: float = 0.0  # OmniVoice training data for this language

    def to_dict(self) -> dict:
        return asdict(self)


_ALL: List[Language] = [
    Language("en", "English", "English", "us", "en", "en", "eng_Latn", "English", "English", "英语", omnivoice_hours=206061),
    Language("ar", "Arabic", "العربية", "eg", "ar", "arb", "arb_Arab", "Arabic", "Arabic", "阿拉伯语", rtl=True, target=False, omnivoice_hours=1483),
    Language("arz", "Egyptian Arabic", "مصري", "eg", "ar", "arz", "arz_Arab", "Arabic", "Egyptian Arabic", "埃及阿拉伯语", rtl=True, source=False, omnivoice_hours=23),
    Language("arb", "Modern Standard Arabic", "فصحى", "sa", "ar", "arb", "arb_Arab", "Arabic", "Modern Standard Arabic", "阿拉伯语", rtl=True, source=False, omnivoice_hours=1483),
    Language("es", "Spanish", "Español", "es", "es", "es", "spa_Latn", "Spanish", "Spanish", "西班牙语", omnivoice_hours=27560),
    Language("fr", "French", "Français", "fr", "fr", "fr", "fra_Latn", "French", "French", "法语", omnivoice_hours=23675),
    Language("it", "Italian", "Italiano", "it", "it", "it", "ita_Latn", "Italian", "Italian", "意大利语", omnivoice_hours=9402),
    Language("hi", "Hindi", "हिन्दी", "in", "hi", "hi", "hin_Deva", "Hindi", "Hindi", "印地语", omnivoice_hours=117),
    Language("zh", "Chinese", "中文", "cn", "zh", "zh", "zho_Hans", "Chinese", "Simplified Chinese", "中文", spaced=False, omnivoice_hours=111343),
    Language("ja", "Japanese", "日本語", "jp", "ja", "ja", "jpn_Jpan", "Japanese", "Japanese", "日语", spaced=False, omnivoice_hours=36914),
]

LANGUAGES: Dict[str, Language] = {lang.code: lang for lang in _ALL}
SOURCE_CODES: List[str] = [lang.code for lang in _ALL if lang.source]
TARGET_CODES: List[str] = [lang.code for lang in _ALL if lang.target]
ARABIC_TARGETS = ("arz", "arb")


def get(code: str) -> Language:
    try:
        return LANGUAGES[code]
    except KeyError as exc:
        raise KeyError(f"Unsupported language '{code}'. Supported: {', '.join(LANGUAGES)}") from exc


def iso(code: str) -> str:
    return get(code).iso


def is_arabic(code: str) -> bool:
    return get(code).iso == "ar"


def same_language(source: str, target: str) -> bool:
    return iso(source) == iso(target)


def from_iso(iso_code: str) -> str | None:
    """Map a detected ISO code (e.g. from Whisper) to a Dubby source language."""
    iso_code = (iso_code or "").lower().split("-")[0]
    if iso_code in ("yue", "wuu"):
        iso_code = "zh"
    for lang in _ALL:
        if lang.source and lang.iso == iso_code:
            return lang.code
    return None


def join_tokens(tokens: Iterable[str], code: str) -> str:
    sep = " " if get(code).spaced else ""
    return sep.join(t.strip() for t in tokens if t and t.strip()).strip()


def tokenize(text: str, code: str) -> List[str]:
    """Word tokens for re-timing edited text (characters for unspaced scripts)."""
    if get(code).spaced:
        return text.split()
    return [ch for ch in text if not ch.isspace()]


def public() -> dict:
    return {
        "languages": [lang.to_dict() for lang in _ALL],
        "sources": SOURCE_CODES,
        "targets": TARGET_CODES,
    }
