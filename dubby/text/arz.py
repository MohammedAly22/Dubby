"""Egyptian Arabic (عامية مصرية) normalization — a faithful port of VoiceTut-TTS's ArabicNormalizer.

Same steps, same order and same rules as ``voicetut_tts.normalization`` (numbers, colloquial
clock times, Egyptian phone prefixes, dates, currencies, percentages, emails / URLs / handles,
abbreviations, symbols and English → Arabic names), with two deliberate differences:

* **no diacritics are added** — the diacritics lexicon is not applied, and the word tables are
  the originals with their harakat removed, so the output is plain processed text;
* **tashkeel already in the text is kept** (VoiceTut strips it before re-adding its own), so
  diacritics typed with the studio's diacritics bar reach the TTS untouched.
"""

from __future__ import annotations

import re
from typing import Dict, List

_HARAKAT = re.compile("[ً-ْٰ]")


def _plain(text: str) -> str:
    return _HARAKAT.sub("", text)


# --------------------------------------------------------------------------- digits
ARABIC_INDIC = "٠١٢٣٤٥٦٧٨٩"
ASCII_DIGITS = "0123456789"
_AR2ASCII = {ord(a): d for a, d in zip(ARABIC_INDIC, ASCII_DIGITS)}

# --------------------------------------------------------------------------- number words (VoiceTut tables, harakat removed)
_ONES = [_plain(w) for w in ["", "وَاحِد", "اِتْنِين", "تَلَاتَة", "أَرْبَعَه", "خَمْسَه", "سِتَّه", "سَبْعَه", "تَمَانْيَه", "تِسْعَه"]]
_TEENS = [_plain(w) for w in ["عَشَرَه", "حِدَاشَر", "اِتْنَاشَر", "تَلاتَّاشّر", "أَرْبَعْتَاشَر", "خَمَسْتَاشَر",
                              "سِتَّاشَر", "سَبَعْتَاشَر", "تَمَنْتَاشَر", "تِسَعْتَاشَر"]]
_TENS = [_plain(w) for w in ["", "عَشَرَه", "عِشْرين", "تلاتين", "أَرْبِعين", "خَمْسِين", "سِتِّين", "سَبْعين", "تَمانين", "تِسعين"]]
_HUNDREDS = [_plain(w) for w in ["", "مِية", "مِتِين", "تُلْتٌمِية", "رُبْعُمِية", "خُمْسُمِية",
                                 "سُتُّمِية", "سُبْعُمِية", "تُمْنُمِية", "تُسْعُمِية"]]
_SCALES = [(1_000_000_000, "مليار"), (1_000_000, "مليون"), (1_000, "ألف")]


def _three_digits_to_words(n: int) -> str:
    """0..999 -> Egyptian Arabic words."""
    parts: List[str] = []
    h, rem = divmod(n, 100)
    if h:
        parts.append(_HUNDREDS[h])
    if rem:
        if rem < 10:
            parts.append(_ONES[rem])
        elif rem < 20:
            parts.append(_TEENS[rem - 10])
        else:
            t, o = divmod(rem, 10)
            parts.append((_ONES[o] + " و" + _TENS[t]) if o else _TENS[t])
    return " و".join(parts)


def number_to_arabic_words(n: int) -> str:
    """Convert a non-negative integer to Egyptian-Arabic words."""
    if n == 0:
        return "صفر"
    if n < 0:
        return "سالب " + number_to_arabic_words(-n)
    words: List[str] = []
    for value, name in _SCALES:
        if n >= value:
            count, n = divmod(n, value)
            if count == 1:
                words.append(name)
            elif count == 2:
                words.append(name + "ين" if name == "ألف" else "اتنين " + name)
            elif count <= 10:
                words.append(_three_digits_to_words(count) + " " + ("آلاف" if name == "ألف" else name))
            else:
                words.append(_three_digits_to_words(count) + " " + name)
    if n:
        words.append(_three_digits_to_words(n))
    return " و".join(w for w in words if w)


def _read_decimal(num_str: str) -> str:
    """'3.5' -> 'تلاتة فاصلة خمسة' (digit-by-digit fraction)."""
    if "." not in num_str:
        return number_to_arabic_words(int(num_str))
    intp, frac = num_str.split(".", 1)
    out = number_to_arabic_words(int(intp or "0")) + " " + _plain("فَاصْلَة") + " "
    out += " ".join(_ONES[int(d)] if d != "0" else "صفر" for d in frac)
    return out


# --------------------------------------------------------------------------- time (colloquial Egyptian)
_HOUR_FEM = {k: _plain(v) for k, v in {
    1: "وَاحْدَه", 2: "اتنين", 3: "تَلَاتَة", 4: "أَرْبَعَه", 5: "خَمْسَه", 6: "سِتَّه",
    7: "سَبْعَه", 8: "تَمَانْيَه", 9: "تِسْعَه", 10: "عَشَرَه", 11: "حِدَاشَر", 12: "اِتْنَاشَر",
}.items()}
_MIN_FRACTION = {k: _plain(v) for k, v in {5: "خَمْسَه", 10: "عَشَرَه", 15: "رُبع", 20: "تِلْت", 30: "نُصّ"}.items()}


def _hour_word(h: int) -> str:
    h = h % 12
    if h == 0:
        h = 12
    return _HOUR_FEM[h]


def _say_time(h: int, mn: int) -> str:
    """3:30 -> تلاتة و نص · 7:45 -> تمانية الا ربع · 5:25 -> خمسة و نص الا خمسة."""
    hour = _hour_word(h)
    if mn == 0:
        return hour
    if mn in _MIN_FRACTION:
        return f"{hour} و {_MIN_FRACTION[mn]}"
    if mn == 25:
        return f"{hour} و {_plain('نٌصّ اِلَّا خَمْسَه')}"
    if mn == 35:
        return f"{hour} و {_plain('نُصّ و خَمْسَه')}"
    if mn > 30:
        nxt = _hour_word((h % 12) + 1 if (h % 12) != 0 else 1)
        rem = 60 - mn
        frac = _MIN_FRACTION.get(rem, number_to_arabic_words(rem))
        return f"{nxt} الا {frac}"
    return f"{hour} و {number_to_arabic_words(mn)} دقيقة"


# --------------------------------------------------------------------------- Egyptian phone numbers
PHONE_PREFIX = {k: _plain(v) for k, v in {
    "010": "زيرو عَشَرَه",
    "011": "زيرو حْدَاشَر",
    "012": "زيرو اِتْنَاشَر",
    "015": "زيرو خَمَسْتَاشَر",
}.items()}


def _say_phone_number(raw: str) -> str:
    """Operator prefix, then 2-digit groups separated by Arabic commas (short pauses)."""
    digits = re.sub(r"\D", "", raw)
    plus = raw.strip().startswith("+") or digits.startswith("20")
    if digits.startswith("20"):
        digits = "0" + digits[2:]
    out: List[str] = []
    rest = digits
    if digits[:3] in PHONE_PREFIX:
        out.append(PHONE_PREFIX[digits[:3]])
        rest = digits[3:]
    i = 0
    while i < len(rest):
        pair = rest[i:i + 2]
        if len(pair) == 2:
            if pair[0] == "0":
                out.append("زيرو " + number_to_arabic_words(int(pair[1])) if pair[1] != "0" else "زيرو زيرو")
            else:
                out.append(number_to_arabic_words(int(pair)))
        else:
            out.append(number_to_arabic_words(int(pair)) if pair != "0" else "زيرو")
        i += 2
    spoken = "، ".join(out)
    return (" زائد " if plus else " ") + spoken + " "


# --------------------------------------------------------------------------- tables
ABBREVIATIONS: Dict[str, str] = {k: _plain(v) for k, v in {
    "د.": "دكتور", "أ.": "أستاذ", "م.": "مهندس", "ج.م": "جنيه مصري", "ج.م.": "جنيه مصري",
    "كجم": "كيلو جرام", "كج": "كيلو", "كم": "كيلومتر", "سم": "سنتيمتر", "مم": "مليمتر",
    "ص": "صباحًا", "م": "مساءً", "ق.م": "قبل الميلاد", "إلخ": "إلى آخره", "الخ": "إلى آخره",
    "Dr.": "دكتور", "Mr.": "مستر", "Eng.": "مهندس", "etc.": "إلى آخره", "e.g.": "على سبيل المثال",
    "i.e.": "أي", "vs.": "في مقابل",
}.items()}

CURRENCY = {
    "ج.م": "جنيه", "جنيه": "جنيه", "EGP": "جنيه", "LE": "جنيه", "£": "جنيه",
    "$": "دولار", "USD": "دولار", "€": "يورو", "EUR": "يورو",
    "ر.س": "ريال", "SAR": "ريال", "د.إ": "درهم", "AED": "درهم",
}

MONTHS = {1: "يناير", 2: "فبراير", 3: "مارس", 4: "أبريل", 5: "مايو", 6: "يونيو",
          7: "يوليو", 8: "أغسطس", 9: "سبتمبر", 10: "أكتوبر", 11: "نوفمبر", 12: "ديسمبر"}

SYMBOL_WORDS = {"@": " آت ", "&": " اند ", "%": " في المية ", "+": " زائد ",
                "=": " يساوي ", "#": " هاشتاج ", "_": " ", "/": " ", "-": " "}

# English name -> Arabic spelling, so names are pronounced the Egyptian way (VoiceTut's names table)
NAMES: Dict[str, str] = {k.lower(): v for k, v in {
    "Ahmed": "أحمد", "Ahmad": "أحمد", "Mohamed": "محمد", "Mohammed": "محمد", "Muhammad": "محمد", "Mahmoud": "محمود",
    "Mostafa": "مصطفى", "Mustafa": "مصطفى", "Mahmood": "محمود", "Ali": "علي", "Aly": "علي", "Omar": "عمر", "Amr": "عمرو",
    "Khaled": "خالد", "Khalid": "خالد", "Hassan": "حسن", "Hussein": "حسين", "Hossam": "حسام", "Tarek": "طارق",
    "Tariq": "طارق", "Sayed": "سيد", "Kamal": "كمال", "Abdullah": "عبد الله", "Abdelrahman": "عبد الرحمن",
    "Abdulrahman": "عبد الرحمن", "Zaki": "زكي", "Yousef": "يوسف", "Youssef": "يوسف", "Yusuf": "يوسف",
    "Ibrahim": "إبراهيم", "Ismail": "إسماعيل", "Karim": "كريم", "Kareem": "كريم", "Mazen": "مازن", "Ziad": "زياد",
    "Adel": "عادل", "Sherif": "شريف", "Ashraf": "أشرف", "Tamer": "تامر", "Wael": "وائل", "Hany": "هاني", "Hani": "هاني",
    "Sameh": "سامح", "Ramy": "رامي", "Rami": "رامي", "Nour": "نور", "Noor": "نور", "Mona": "منى", "Mariam": "مريم",
    "Maryam": "مريم", "Sara": "سارة", "Sarah": "سارة", "Salma": "سلمى", "Nada": "ندى", "Hana": "هنا", "Hanan": "حنان",
    "Yasmin": "ياسمين", "Yasmine": "ياسمين", "Esraa": "إسراء", "Asmaa": "أسماء", "Marwa": "مروة", "Heba": "هبة",
    "Dina": "دينا", "Reem": "ريم", "Farida": "فريدة", "Habiba": "حبيبة", "Malak": "ملك", "Nourhan": "نورهان",
    "Aya": "آية", "Fatma": "فاطمة", "Fatima": "فاطمة", "Amira": "أميرة", "Doaa": "دعاء", "Shaimaa": "شيماء",
    "Rana": "رنا", "Layla": "ليلى", "Laila": "ليلى",
}.items()}

URL_RE = re.compile(r"\b(?:https?://|www\.)\S+\b")
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
HANDLE_RE = re.compile(r"(?<!\w)@(\w+)")
TIME_RE = re.compile(r"\b(\d{1,2}):(\d{2})\b")
DATE_RE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b")
PHONE_RE = re.compile(r"(?<!\d)(\+?\d[\d\s-]{6,}\d)(?!\d)")
PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
NUMBER_RE = re.compile(r"(?<![\w@])(\d+(?:\.\d+)?)(?![\w@])")
_AR = "ء-ي"


class EgyptianNormalizer:
    """VoiceTut's Egyptian pipeline without diacritics (see module docstring)."""

    code = "arz"

    # ------------------------------------------------------------ steps (same order as VoiceTut)
    @staticmethod
    def normalize_orthography(text: str) -> str:
        text = text.translate(_AR2ASCII)
        text = re.sub("[ـ]", "", text)
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def expand_abbreviations(text: str) -> str:
        for abbr, full in sorted(ABBREVIATIONS.items(), key=lambda x: -len(x[0])):
            text = re.sub(rf"(?<![A-Za-z{_AR}]){re.escape(abbr)}(?![A-Za-z{_AR}])", " " + full + " ", text)
        return text

    @staticmethod
    def _say_email(s: str) -> str:
        local, _, domain = s.partition("@")
        spell = lambda x: x.replace(".", " dot ").replace("-", " ").replace("_", " ")  # noqa: E731
        return f" {spell(local)} at {spell(domain)} "

    @staticmethod
    def _say_url(s: str) -> str:
        s = re.sub(r"^https?://", "", s).rstrip("/")
        s = s.replace("www.", "")
        return " " + s.replace(".", " dot ").replace("/", " slash ") + " "

    def expand_contacts(self, text: str) -> str:
        text = URL_RE.sub(lambda m: self._say_url(m.group(0)), text)
        text = EMAIL_RE.sub(lambda m: self._say_email(m.group(0)), text)
        text = HANDLE_RE.sub(lambda m: " آت " + m.group(1) + " ", text)
        text = PHONE_RE.sub(lambda m: _say_phone_number(m.group(1)), text)
        return text

    @staticmethod
    def expand_dates_times(text: str) -> str:
        def _date(m: re.Match) -> str:
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            y = y + 2000 if y < 100 else y
            return f"{number_to_arabic_words(d)} {MONTHS.get(mo, number_to_arabic_words(mo))} {number_to_arabic_words(y)}"

        text = DATE_RE.sub(_date, text)
        return TIME_RE.sub(lambda m: _say_time(int(m.group(1)), int(m.group(2))), text)

    @staticmethod
    def expand_currency(text: str) -> str:
        for sym, word in sorted(CURRENCY.items(), key=lambda x: -len(x[0])):
            esym = re.escape(sym)
            rb = r"\b" if sym[-1].isalnum() else ""
            text = re.sub(rf"(\d+(?:\.\d+)?)\s*{esym}{rb}", lambda m: _read_decimal(m.group(1)) + " " + word, text)
            text = re.sub(rf"{esym}\s*(\d+(?:\.\d+)?)", lambda m: _read_decimal(m.group(1)) + " " + word, text)
        return text

    @staticmethod
    def expand_numbers(text: str) -> str:
        text = PERCENT_RE.sub(lambda m: _read_decimal(m.group(1)) + " في المية", text)
        return NUMBER_RE.sub(lambda m: _read_decimal(m.group(1)), text)

    @staticmethod
    def transliterate_names(text: str) -> str:
        return re.sub(r"[A-Za-z]+", lambda m: NAMES.get(m.group(0).lower(), m.group(0)), text)

    # ------------------------------------------------------------ pipeline
    def __call__(self, text: str) -> str:
        if not text:
            return ""
        text = self.normalize_orthography(text)
        text = self.expand_abbreviations(text)
        text = self.expand_contacts(text)
        text = self.expand_dates_times(text)
        text = self.expand_currency(text)
        text = self.expand_numbers(text)
        for sym, word in SYMBOL_WORDS.items():
            if sym in "@&%+=#":
                text = text.replace(sym, word)
        text = self.transliterate_names(text)
        return re.sub(r"\s+", " ", text).strip()
