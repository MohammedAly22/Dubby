"""Shared text-normalization pipeline for TTS.

Each dub language supplies a :class:`Rules` object (number words, currencies, units,
abbreviations, date/time phrasing…). :class:`Normalizer` runs the same ordered passes
for every language:

    cleanup → emails / URLs / handles / hashtags → abbreviations → phone numbers
    → times → dates → money → percentages → units → ordinals → fractions → ranges
    → remaining numbers → symbols → acronyms → spacing and punctuation

Every pass works on plain strings and is deterministic, so the processed text shown in
the studio is exactly what the TTS model receives.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Tuple

# --------------------------------------------------------------------------- characters
_DIGITS = {}
for _block in ("٠١٢٣٤٥٦٧٨٩", "۰۱۲۳۴۵۶۷۸۹", "०१२३४५६७८९", "０１２３４５６７８９"):
    for _i, _ch in enumerate(_block):
        _DIGITS[ord(_ch)] = str(_i)
_DIGITS[ord("٫")] = "."  # Arabic decimal separator
_DIGITS[ord("٬")] = ","  # Arabic thousands separator
_DIGITS[ord("٪")] = "%"
_DIGITS[ord("％")] = "%"
_DIGITS[ord("\u00a0")] = " "
_DIGITS[ord("\u2009")] = " "
_DIGITS[ord("\u2212")] = "-"  # minus sign

_ZERO_WIDTH = re.compile("[\u200b\u200e\u200f\u2060\ufeff]")
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U00002B00-\U00002BFF\U0001F900-\U0001F9FF\ufe0f\u20e3]"
)
_TATWEEL = re.compile("\u0640")
CJK = "\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff66-\uff9f"
_CJK_SPACE = re.compile(f"(?<=[{CJK}，。！？、：；])\\s+(?=[{CJK}，。！？、：；])")

URL_RE = re.compile(r"\b(?:https?://|www\.)[^\s<>\"']+[^\s<>\"'.,;:!?)\]]")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9][\w.+-]*@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+\b")
HANDLE_RE = re.compile(r"(?<![\w@])@([A-Za-z_][\w.]*\w|[A-Za-z_])")
HASHTAG_RE = re.compile(r"(?<![\w#&])#([^\s#\d.,;:!?]\w*)")
PHONE_RE = re.compile(
    r"(?<![\w+])(\+\d{1,3}[\s.-]?)?(\(?\d{2,4}\)?[\s.-]?)?\d{3,4}[\s.-]\d{3,4}(?:[\s.-]\d{2,4})?(?![\d\w])"
    r"|(?<![\w+])\+\d{8,14}(?!\d)|(?<![\w\d])0\d{9,10}(?!\d)"
)
TIME_RE = re.compile(
    r"(?<![\d:.])([01]?\d|2[0-4]):([0-5]\d)(?::([0-5]\d))?(?![\d:])"
    # "pm" / "PM" / "p.m." — a plain "pm." keeps its sentence-ending period
    r"(?:\s?([AaPp])(?:\.\s?[Mm]\.|[Mm](?![A-Za-z])))?"
)
DATE_RE = re.compile(r"(?<![\w/.-])(\d{1,4})([/.-])(\d{1,2})\2(\d{2}|\d{4})(?![\w/-]|\.\d)")
FRACTION_GLYPHS = "½⅓⅔¼¾⅕⅖⅗⅘⅙⅚⅛⅜⅝⅞"

LATIN_LETTER = re.compile(r"[A-Za-z]")
# Letters that may not directly follow a unit ("5 km" but not "5 kmx"). Punctuation such as the Arabic comma
# "،", the Hindi danda "।" or the Chinese "，" is deliberately excluded.
WORD_LETTERS = "A-Za-zÀ-ɏء-يٱ-ۓऀ-ॣ぀-ヿ㐀-鿿"
_SCALES = {"k": 3, "K": 3, "thousand": 3, "M": 6, "m": 6, "mln": 6, "million": 6, "B": 9, "bn": 9, "billion": 9}

# symbol / ISO code → ISO currency code. Languages add local spellings via Rules.currency_aliases.
CURRENCY_SYMBOLS: Dict[str, str] = {
    "US$": "USD", "$": "USD", "USD": "USD", "€": "EUR", "EUR": "EUR", "£": "GBP", "GBP": "GBP",
    "E£": "EGP", "EGP": "EGP", "LE": "EGP", "L.E.": "EGP", "SAR": "SAR", "SR": "SAR", "AED": "AED",
    "¥": "JPY", "JPY": "JPY", "CNY": "CNY", "RMB": "CNY", "₹": "INR", "INR": "INR", "Rs.": "INR", "Rs": "INR",
}

UNIT_KEYS = (
    "km/h", "kmh", "kph", "mph", "m/s", "km²", "m²", "cm²", "km2", "m2", "m³", "m3", "cm³",
    "°C", "ºC", "°F", "ºF", "GiB", "MiB", "Gbps", "Mbps", "kbps", "kWh", "mAh",
    "km", "cm", "mm", "kg", "mg", "ml", "mL", "GB", "MB", "KB", "kB", "TB", "fps", "kHz", "MHz", "GHz", "Hz",
    "kW", "hrs", "hr", "min", "mins", "sec", "secs", "ms", "ft", "lbs", "lb", "oz", "mi", "px",
    "m", "g", "l", "L", "W", "V", "h", "s", "°", "x",
)


@dataclass
class Noun:
    """How a counted word is written. ``two``/``few``/``acc`` are only used by Arabic."""

    one: str
    many: str
    two: Optional[str] = None
    few: Optional[str] = None
    acc: Optional[str] = None
    feminine: bool = False


@dataclass
class Money:
    main: Noun
    sub: Optional[Noun] = None


def num_pattern(decimal: str, groups: str) -> str:
    seps = re.escape(decimal + groups)
    return rf"\d+(?:[{seps}]\d+)*"


class Rules:
    """Language data and spelling. Subclasses fill in the tables and number spellers."""

    code = "xx"
    latin_script = True  # Latin-script language: spell acronyms, read Latin-glued numbers natively
    cjk = False  # written without spaces between words
    decimal = "."
    groups = ","
    date_order = "DMY"  # used when a numeric date is ambiguous

    words: Dict[str, str] = {}
    months: List[str] = []
    abbreviations: Dict[str, str] = {}
    abbreviation_patterns: List[Tuple[str, str]] = []
    currencies: Dict[str, Money] = {}
    currency_aliases: Dict[str, str] = {}
    units: Dict[str, Noun] = {}
    unit_aliases: Dict[str, str] = {}
    fraction_words: Dict[str, str] = {}
    ordinal_pattern: Optional[str] = None  # regex with groups (number)(suffix)
    pronounceable: frozenset = frozenset()

    # ------------------------------------------------------------ numbers
    def cardinal(self, n: int) -> str:  # pragma: no cover - interface
        raise NotImplementedError

    def ordinal(self, n: int, feminine: bool = False) -> str:
        return self.cardinal(n)

    def digit_words(self, digits: str) -> str:
        return self.join(*(self.cardinal(int(d)) for d in digits if d.isdigit()))

    def decimal_words(self, integer: int, fraction: str) -> str:
        return self.join(self.cardinal(integer), self.words["point"], self.digit_words(fraction))

    def year(self, n: int) -> str:
        return self.cardinal(n)

    def cardinal_before(self, n: int, next_word: str) -> str:
        """A bare number, knowing the word that follows (for gender / apocope agreement)."""
        return self.cardinal(n)

    def scale(self, token: str, integer: int, fraction: str, exponent: int, normalizer: "Normalizer") -> str:
        """``1.5M``: Latin languages say "one point five million"; others read the full value."""
        key = {3: "thousand", 6: "million", 9: "billion"}[exponent]
        if self.latin_script and key in self.words:
            one = integer == 1 and not fraction
            word = self.words.get(key if one else key + "s", self.words[key])
            return self.join(self.number(integer, fraction), word)
        value = Decimal(f"{integer}.{fraction or 0}") * (Decimal(10) ** exponent)
        return self.number(int(value), "")

    def negative(self, words: str) -> str:
        return self.join(self.words["minus"], words)

    def number(self, integer: int, fraction: str = "") -> str:
        return self.decimal_words(integer, fraction) if fraction else self.cardinal(integer)

    # ------------------------------------------------------------ phrases
    def join(self, *parts: str) -> str:
        sep = "" if self.cjk else " "
        return sep.join(p for p in parts if p)

    def count(self, integer: int, fraction: str, noun: Noun) -> str:
        words = self.number(integer, fraction)
        form = noun.one if integer == 1 and not fraction else noun.many
        return self.join(words, form)

    def money(self, integer: int, fraction: str, code: str) -> str:
        money = self.currencies.get(code)
        if money is None:
            return self.join(self.number(integer, fraction), code)
        cents = fraction[:2].ljust(2, "0") if fraction else ""
        if money.sub and cents and len(fraction) <= 2:
            main = self.count(integer, "", money.main) if integer else ""
            sub = self.count(int(cents), "", money.sub) if int(cents) else ""
            joiner = self.words.get("money_and", self.words["and"])
            return self.join(main, joiner, sub) if main and sub else (main or sub or self.count(0, "", money.main))
        return self.count(integer, fraction.rstrip("0"), money.main)

    def percent(self, words: str) -> str:
        return self.join(words, self.words["percent"])

    def per_mille(self, words: str) -> str:
        return self.join(words, self.words["per_mille"])

    def range(self, a: str, b: str) -> str:
        return self.join(a, self.words["to"], b)

    def fraction(self, a: int, b: int) -> Optional[str]:
        return None

    def time(self, hour: int, minute: int, period: Optional[str]) -> str:  # pragma: no cover - interface
        raise NotImplementedError

    def date(self, day: int, month: int, year: Optional[int]) -> str:
        parts = [self.cardinal(day), self.months[month - 1]]
        if year is not None:
            parts.append(self.year(year))
        return self.join(*parts)

    def spell_letters(self, token: str) -> str:
        return " ".join(token)

    # ------------------------------------------------------------ hooks
    def before(self, text: str) -> str:
        """Language-specific passes that must run first (e.g. French 14h30)."""
        return text

    def after(self, text: str) -> str:
        return text

    def is_year(self, value: int, before: str, after: str) -> bool:
        return False


# --------------------------------------------------------------------------- the pipeline
def _english():
    from dubby.text.en import EnglishRules

    return EnglishRules()


class Normalizer:
    def __init__(self, rules: Rules):
        self.r = rules
        self.num = num_pattern(rules.decimal, rules.groups)
        self._en: Optional[Rules] = None

    # ------------------------------------------------------------ helpers
    def english(self) -> Rules:
        if self._en is None:
            self._en = self.r if self.r.code == "en" else _english()
        return self._en

    def parse(self, token: str) -> Optional[Tuple[int, str]]:
        """``"1,234.5"`` → ``(1234, "5")`` using this language's separators."""
        token = token.strip()
        seps = [c for c in token if not c.isdigit()]
        if not seps:
            return int(token), ""
        kinds = set(seps)
        dec, groups = self.r.decimal, self.r.groups
        if len(kinds) > 1:
            last = max(token.rfind(s) for s in kinds)
            integer, fraction = token[:last], token[last + 1:]
            integer = re.sub(r"\D", "", integer)
        else:
            sep = seps[0]
            grouped = re.fullmatch(rf"\d{{1,3}}(?:{re.escape(sep)}\d{{3}})+", token)
            if sep == dec:
                if len(seps) > 1 and grouped:
                    return int(re.sub(r"\D", "", token)), ""
                if len(seps) > 1:
                    return None
                integer, fraction = token.split(sep)
            elif sep in groups:
                if grouped:
                    return int(re.sub(r"\D", "", token)), ""
                if len(seps) > 1 or sep == " ":
                    return None
                integer, fraction = token.split(sep)
            else:
                if len(seps) > 1:
                    return None
                integer, fraction = token.split(sep)
        if not integer.isdigit() or not fraction.isdigit():
            return None
        return int(integer), fraction

    def say(self, token: str) -> Optional[str]:
        parsed = self.parse(token)
        if parsed is None:
            # not one number (a version "1.2.3", a list "1,2,3"): read each part, speak dots, keep commas
            out = []
            for piece in re.split(r"([.,\s])", token):
                if piece.isdigit():
                    out.append(self.say(piece) or piece)
                elif piece == ".":
                    out.append(self.r.words["dot"])
                elif piece.strip():
                    out.append(piece)
            return " ".join(out)
        integer, fraction = parsed
        digits = re.sub(r"\D", "", token)
        if len(digits) > 15:
            return self.r.digit_words(digits)
        if not fraction and len(token) > 1 and token.startswith("0"):
            return self.r.digit_words(token)  # 007, 0123 → digit by digit
        return self.r.number(integer, fraction)

    def _sub(self, pattern: str, fn, text: str, flags: int = 0) -> str:
        def replace(m: re.Match) -> str:
            result = fn(m)
            return m.group(0) if result is None else _pad(result, m, text)

        return re.sub(pattern, replace, text, flags=flags)

    # ------------------------------------------------------------ passes
    def cleanup(self, text: str) -> str:
        text = text.translate(_DIGITS)
        text = _ZERO_WIDTH.sub("", text)
        text = _EMOJI.sub(" ", text)
        text = _TATWEEL.sub("", text)
        text = re.sub("[\u2018\u2019\u02bc]", "'", text)
        text = re.sub("[\u201c\u201d\u201e\u00ab\u00bb]", '"', text)
        text = re.sub(r"\s+([-–—])\s+", r" \1 ", text)
        text = re.sub(r"([!?؟])\1+", r"\1", text)
        text = re.sub(r"\.{3,}", "…", text)
        return re.sub(r"[ \t]+", " ", text).strip()

    def contacts(self, text: str) -> str:
        w = self.r.words

        def spoken(chunk: str) -> str:
            chunk = re.sub(r"\.", f" {w['dot']} ", chunk)
            chunk = chunk.replace("/", f" {w['slash']} ").replace("_", f" {w['underscore']} ").replace("-", f" {w['dash']} ")
            chunk = re.sub(r"\d+", lambda m: self.english().digit_words(m.group(0)) if not self.r.latin_script else self.r.digit_words(m.group(0)), chunk)
            return " ".join(chunk.split())

        def url(m: re.Match) -> str:
            value = re.sub(r"^https?://", "", m.group(0), flags=re.I)
            value = re.sub(r"^www\.", "", value, flags=re.I).rstrip("/")
            value = value.split("?")[0].split("#")[0]
            return f" {spoken(value)} "

        def email(m: re.Match) -> str:
            local, domain = m.group(0).split("@", 1)
            return f" {spoken(local)} {w['at']} {spoken(domain)} "

        text = URL_RE.sub(url, text)
        text = EMAIL_RE.sub(email, text)
        text = HANDLE_RE.sub(lambda m: f" {w['at']} {m.group(1).replace('_', ' ')} ", text)
        text = HASHTAG_RE.sub(lambda m: f" {w['hashtag']} {_split_camel(m.group(1))} ", text)
        return text

    def abbreviations(self, text: str) -> str:
        for pattern, replacement in self.r.abbreviation_patterns:
            text = re.sub(pattern, replacement, text)
        letters = "A-Za-z\u00c0-\u024f\u0600-\u06ff\u0900-\u097f"
        for abbr, full in sorted(self.r.abbreviations.items(), key=lambda kv: -len(kv[0])):
            text = re.sub(rf"(?<![{letters}.]){re.escape(abbr)}(?![{letters}])", full, text)
        return text

    def phones(self, text: str) -> str:
        def phone(m: re.Match) -> Optional[str]:
            raw = m.group(0).strip()
            digits = re.sub(r"\D", "", raw)
            groups = [g for g in re.split(r"[\s.()-]+", raw.lstrip("+")) if g]
            # "2024 2025" is two years, not a phone: need a +, a (, a leading 0 or 3+ groups
            if len(digits) < 8 or DATE_RE.fullmatch(raw) or not (raw[0] in "+(0" or len(groups) >= 3):
                return None
            if len(groups) == 1:
                g = groups[0]
                groups = [g[i:i + 3] for i in range(0, len(g), 3)]
            spoken = ", ".join(self.r.digit_words(g) for g in groups)
            return (self.r.words["plus"] + " " if raw.strip().startswith("+") else "") + spoken

        return self._sub(PHONE_RE.pattern, phone, text)

    def times(self, text: str) -> str:
        def time(m: re.Match) -> Optional[str]:
            hour, minute = int(m.group(1)), int(m.group(2))
            period = (m.group(4) or "").lower() or None
            if period and not 1 <= hour <= 12:
                return None
            return self.r.time(hour % 24 if hour != 24 else 0, minute, period)

        return self._sub(TIME_RE.pattern, time, text)

    def dates(self, text: str) -> str:
        def date(m: re.Match) -> Optional[str]:
            a, sep, b, c = m.group(1), m.group(2), int(m.group(3)), m.group(4)
            if len(a) == 4:  # ISO: year-month-day
                year, month, day = int(a), b, int(c)
            else:
                if len(c) == 2 and sep != "/":
                    return None
                x, year = int(a), int(c)
                if len(c) == 2:
                    year += 2000 if year < 50 else 1900
                if x > 12 and b <= 12:
                    day, month = x, b
                elif b > 12 and x <= 12:
                    day, month = b, x
                elif self.r.date_order == "MDY":
                    day, month = b, x
                else:
                    day, month = x, b
            if not (1 <= month <= 12 and 1 <= day <= 31 and 1 <= year <= 2999):
                return None
            return self.r.date(day, month, year)

        return self._sub(DATE_RE.pattern, date, text)

    def money(self, text: str) -> str:
        aliases = {**CURRENCY_SYMBOLS, **self.r.currency_aliases}
        symbols = "|".join(re.escape(s) for s in sorted(aliases, key=len, reverse=True))
        scales = r"(?:\s?(?P<scale>thousand|million|billion|mln|bn|[kKMB])(?![A-Za-z]))?"
        before = rf"(?P<sym>{symbols})\s?(?P<neg>-)?(?P<num>{self.num}){scales}"
        after = rf"(?P<neg>-)?(?P<num>{self.num}){scales}\s?(?P<sym>{symbols})(?![A-Za-z])"

        def money(m: re.Match) -> Optional[str]:
            parsed = self.parse(m.group("num"))
            if parsed is None:
                return None
            integer, fraction = parsed
            scale = m.group("scale")
            if scale:
                try:
                    value = Decimal(f"{integer}.{fraction or 0}") * (Decimal(10) ** _SCALES[scale])
                except InvalidOperation:
                    return None
                integer, fraction = int(value), ""
            code = aliases[m.group("sym")]
            if code == "JPY" and self.r.code == "zh" and m.group("sym") == "¥":
                code = "CNY"
            words = self.r.money(integer, fraction, code)
            return self.r.negative(words) if m.group("neg") else words

        text = self._sub(before, money, text)
        return self._sub(after, money, text)

    def percents(self, text: str) -> str:
        def pct(m: re.Match) -> Optional[str]:
            words = self.say(m.group(2))
            if words is None:
                return None
            words = self.r.negative(words) if m.group(1) else words
            return self.r.per_mille(words) if m.group(3) == "‰" else self.r.percent(words)

        # only ASCII letters/digits block a match: in CJK and Arabic text a number often touches a word
        return self._sub(rf"(?<![A-Za-z0-9.,])(-)?({self.num})\s?(%|‰)", pct, text)

    def units(self, text: str) -> str:
        table = {k: k for k in UNIT_KEYS if k in self.r.units}
        table.update({alias: key for alias, key in self.r.unit_aliases.items() if key in self.r.units})
        if not table:
            return text
        names = "|".join(re.escape(u) for u in sorted(table, key=len, reverse=True))
        letters = WORD_LETTERS

        def unit(m: re.Match) -> Optional[str]:
            parsed = self.parse(m.group(2))
            key = table[m.group(3)]
            if parsed is None:
                return None
            if key == "x" and not self.r.units.get("x"):
                return None
            integer, fraction = parsed
            words = self.r.count(integer, fraction, self.r.units[key])
            return self.r.negative(words) if m.group(1) else words

        pattern = rf"(?<![A-Za-z0-9.,])(-)?({self.num})\s?({names})(?![{letters}0-9²³/])"
        return self._sub(pattern, unit, text)

    def ordinals(self, text: str) -> str:
        if not self.r.ordinal_pattern:
            return text

        def ordinal(m: re.Match) -> Optional[str]:
            suffix = m.group(2) or ""
            feminine = suffix in ("ª", "a", "re", "ère", "ª.")
            return self.r.ordinal(int(m.group(1)), feminine)

        return self._sub(self.r.ordinal_pattern, ordinal, text)

    def fractions(self, text: str) -> str:
        def glyph(m: re.Match) -> Optional[str]:
            words = self.r.fraction_words.get(m.group(2))
            if not words:
                return None
            if m.group(1):
                return self.r.join(self.r.cardinal(int(m.group(1))), self.r.words["and"], words)
            return words

        text = self._sub(rf"(?<![\d.,])(\d+)?\s?([{FRACTION_GLYPHS}])", glyph, text)

        def slash(m: re.Match) -> Optional[str]:
            a, b = int(m.group(1)), int(m.group(2))
            spoken = self.r.fraction(a, b) if 0 < a < b <= 10 else None
            return spoken or self.r.join(self.r.cardinal(a), self.r.cardinal(b))

        return self._sub(r"(?<![A-Za-z0-9/.,])(\d{1,2})/(\d{1,2})(?![A-Za-z0-9/])", slash, text)

    def ranges(self, text: str) -> str:
        def rng(m: re.Match) -> Optional[str]:
            a, b = self.say(m.group(1)), self.say(m.group(2))
            if a is None or b is None:
                return None
            return self.r.range(a, b)

        return self._sub(rf"(?<![A-Za-z\d.,:/-])({self.num})\s?[-–—]\s?({self.num})(?![\w:/-])", rng, text)

    def scaled(self, text: str) -> str:
        """``10k`` / ``1.5M`` / ``3B`` outside money."""

        def scale(m: re.Match) -> Optional[str]:
            parsed = self.parse(m.group(1))
            if parsed is None:
                return None
            key = _SCALES[m.group(2)]
            return self.r.scale(m.group(1), parsed[0], parsed[1], key, self)

        return self._sub(rf"(?<![A-Za-z0-9.,])({self.num})\s?(k|K|M|B|bn|mln)(?![A-Za-z0-9])", scale, text)

    def numbers(self, text: str) -> str:
        text = re.sub(r"(?<=[A-Za-z])-(?=\d)", " ", text)  # "COVID-19" → "COVID 19"

        def number(m: re.Match) -> Optional[str]:
            token = m.group(2)
            start, end = m.span()
            before, after = text[max(0, start - 24):start], text[end:end + 24]
            speaker, helper = self.r, self
            if re.search(r"[A-Za-z]\s?$", before) and not self.r.latin_script:
                # "GPT 4", "iPhone 15" stay English inside Arabic / Hindi / Chinese / Japanese text
                speaker = self.english()
                helper = Normalizer(speaker) if speaker is not self.r else self
            parsed = helper.parse(token)
            if parsed is None:
                words = helper.say(token)
            else:
                integer, fraction = parsed
                following = re.match(r"\s*([^\W\d_]+)", after)
                if not fraction and not m.group(1) and len(token) == 4 and token.isdigit() and speaker.is_year(integer, before, after):
                    words = speaker.year(integer)
                elif not fraction and len(token) <= 15 and not (len(token) > 1 and token.startswith("0")):
                    words = speaker.cardinal_before(integer, following.group(1) if following else "")
                else:
                    words = helper.say(token)
            if words is None:
                return None
            return self.r.negative(words) if m.group(1) else words

        # a "-" is a minus sign only at the start of a word ("-5", "( -3"), never inside "COVID-19"
        return self._sub(rf"(?:(?<![\w.,-])(-))?(?<![\d.,])({self.num})(?!\d)", number, text)

    def multiplication(self, text: str) -> str:
        """``3x4`` / ``3 × 4`` / ``1920*1080`` → ``3 × 4`` (read as "times" by the symbols pass)."""
        return re.sub(r"(?<=\d)\s?[x×*]\s?(?=\d)", " × ", text)

    def symbols(self, text: str) -> str:
        w = self.r.words
        replacements = [
            (r"\s*&\s*", f" {w['and']} "),
            (r"\s*\+\s*", f" {w['plus']} "),
            (r"\s*=\s*", f" {w['equals']} "),
            (r"\s*≠\s*", f" {w['not_equal']} "),
            (r"\s*≤\s*", f" {w['less_equal']} "),
            (r"\s*≥\s*", f" {w['greater_equal']} "),
            (r"(?<=\s)<(?=\s)", f" {w['less']} "),
            (r"(?<=\s)>(?=\s)", f" {w['greater']} "),
            (r"\s*×\s*", f" {w['times']} "),
            (r"\s*÷\s*", f" {w['divided']} "),
            (r"(?:^|(?<=\s))[~≈]\s*", f"{w['approx']} "),
            (r"\s*°", f" {w['degrees']}"),
            (r"%", f" {w['percent']}"),
            (r"(?<=[^\W\d_])/(?=[^\W\d_])", f" {w['or']} "),
            (r"@", f" {w['at']} "),
        ]
        for pattern, replacement in replacements:
            text = re.sub(pattern, replacement, text)
        text = re.sub(r"[()\[\]{}]", ", ", text)
        text = re.sub(r"\s[-–—]\s|—|–(?=\s)", ", ", text)
        text = re.sub(r"[•·▪►▶→←↔⇒|\\^`*_#~]", " ", text)
        text = re.sub(r"(?<![\w'])['\"]|['\"](?![\w'])", " ", text)
        text = re.sub(r"[©®™]", "", text)
        return text

    def acronyms(self, text: str) -> str:
        if not self.r.latin_script:
            return text
        vowels = set("AEIOUY")

        def acronym(m: re.Match) -> str:
            token, plural = m.group(1), m.group(2) or ""
            if token in self.r.pronounceable or (len(token) >= 4 and set(token) & vowels):
                return m.group(0)
            spelled = self.r.spell_letters(token)
            return spelled + (plural and f" {plural}")

        return re.sub(r"(?<![\w'])([A-Z]{2,5})(s)?(?![\w'])", acronym, text)

    def finish(self, text: str) -> str:
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\s+([,.;:!?،؛؟।。、，！？…])", r"\1", text)
        text = re.sub(r"([,،])(?:\s*[,،])+", r"\1", text)
        text = re.sub(r"^[\s,،;:]+|[\s,،;]+$", "", text)
        text = re.sub(r"(?<=[,،;:])(?=[^\s\d])", " ", text) if not self.r.cjk else text
        if self.r.cjk:
            text = _CJK_SPACE.sub("", text)
        return text.strip()

    # ------------------------------------------------------------ run
    def __call__(self, text: str) -> str:
        if not text or not text.strip():
            return ""
        t = self.cleanup(text)
        t = self.r.before(t)
        t = self.contacts(t)
        t = self.abbreviations(t)
        t = self.phones(t)
        t = self.times(t)
        t = self.dates(t)
        t = self.money(t)
        t = self.percents(t)
        t = self.scaled(t)
        t = self.units(t)
        t = self.ordinals(t)
        t = self.fractions(t)
        t = self.multiplication(t)
        t = self.ranges(t)
        t = self.numbers(t)
        t = self.symbols(t)
        t = self.acronyms(t)
        t = self.r.after(t)
        return self.finish(t)


def _split_camel(tag: str) -> str:
    return re.sub(r"(?<=[a-z])(?=[A-Z])|_", " ", tag)


def _pad(replacement: str, m: re.Match, text: str) -> str:
    """Keep replacements from gluing onto neighbouring words."""
    start, end = m.span()
    left = " " if start > 0 and not text[start - 1].isspace() and not replacement.startswith(" ") else ""
    right = " " if end < len(text) and not text[end].isspace() and not replacement.endswith(" ") else ""
    return f"{left}{replacement}{right}"
