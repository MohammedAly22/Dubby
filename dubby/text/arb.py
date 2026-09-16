"""Modern Standard Arabic (فصحى) normalization rules.

Numbers are written in words without diacritics, in the nominative, with counted nouns
following the standard agreement rules: 1 → noun + واحد, 2 → dual, 3–10 → plural with
gender polarity, 11–99 → singular (accusative), 100+ → singular.
"""

from __future__ import annotations

import re
from typing import Optional

from dubby.text.common import Money, Noun, Rules

_ONES = ["صفر", "واحد", "اثنان", "ثلاثة", "أربعة", "خمسة", "ستة", "سبعة", "ثمانية", "تسعة", "عشرة"]
_ONES_FEM = ["صفر", "واحدة", "اثنتان", "ثلاث", "أربع", "خمس", "ست", "سبع", "ثماني", "تسع", "عشر"]
_TEENS_FEM = ["عشر", "إحدى عشرة", "اثنتا عشرة", "ثلاث عشرة", "أربع عشرة", "خمس عشرة", "ست عشرة", "سبع عشرة", "ثماني عشرة", "تسع عشرة"]
# plurals of feminine nouns commonly counted in speech (3–10 then take the short number: ثلاث ساعات)
_FEMININE_PLURALS = {"ساعات", "دقائق", "ثوان", "ثواني", "سنوات", "سنين", "مرات", "سيارات", "دول", "مدن", "كلمات",
                     "صفحات", "ليال", "ليالي", "نساء", "بنات", "طالبات", "شركات", "قصص", "مقالات", "حلقات", "رسائل",
                     "غرف", "أفكار", "جمل", "لغات", "فتيات", "أمهات", "أخوات", "مباريات", "عمليات", "شهادات", "درجات",
                     "نقاط", "مراحل", "دقيقة", "ساعة", "ثانية", "سنة", "مرة", "سيارة", "دولة", "مدينة", "كلمة", "صفحة"}
_TEENS = ["عشرة", "أحد عشر", "اثنا عشر", "ثلاثة عشر", "أربعة عشر", "خمسة عشر", "ستة عشر", "سبعة عشر", "ثمانية عشر", "تسعة عشر"]
_TENS = ["", "", "عشرون", "ثلاثون", "أربعون", "خمسون", "ستون", "سبعون", "ثمانون", "تسعون"]
_HUNDREDS = ["", "مئة", "مئتان", "ثلاثمئة", "أربعمئة", "خمسمئة", "ستمئة", "سبعمئة", "ثمانمئة", "تسعمئة"]
_ORD = ["", "الأول", "الثاني", "الثالث", "الرابع", "الخامس", "السادس", "السابع", "الثامن", "التاسع", "العاشر"]
_ORD_FEM = ["", "الواحدة", "الثانية", "الثالثة", "الرابعة", "الخامسة", "السادسة", "السابعة", "الثامنة", "التاسعة", "العاشرة"]
_MONTHS = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
_GENITIVE = {"اثنان": "اثنين", "اثنا": "اثني", "اثنتان": "اثنتين", "ألفان": "ألفين", "مئتان": "مئتين",
             "مليونان": "مليونين", "ملياران": "مليارين"}
_TIME_WORDS = {15: "والربع", 20: "والثلث", 30: "والنصف"}


def _scale_noun(count: int, one: str, two: str, few: str, acc: str) -> str:
    if count == 1:
        return one
    if count == 2:
        return two
    rest = count % 100
    if 3 <= count <= 10:
        return f"{_below_1000(count)} {few}"
    if 11 <= rest <= 99:
        return f"{_below_1000(count)} {acc}"
    return f"{_below_1000(count)} {one}"


def _below_1000(n: int) -> str:
    hundreds, rest = divmod(n, 100)
    parts = []
    if hundreds:
        parts.append(_HUNDREDS[hundreds])
    if rest:
        if rest <= 10:
            parts.append(_ONES[rest])
        elif rest < 20:
            parts.append(_TEENS[rest - 10])
        else:
            tens, ones = divmod(rest, 10)
            parts.append(f"{_ONES[ones]} و{_TENS[tens]}" if ones else _TENS[tens])
    return " و".join(parts)


def _below_1000_fem(n: int) -> str:
    """0..999 agreeing with a feminine noun: ثلاث، إحدى عشرة، ثلاث وعشرون."""
    hundreds, rest = divmod(n, 100)
    parts = []
    if hundreds:
        parts.append(_HUNDREDS[hundreds])
    if rest:
        if rest <= 10:
            parts.append(_ONES_FEM[rest])
        elif rest < 20:
            parts.append(_TEENS_FEM[rest - 10])
        else:
            tens, ones = divmod(rest, 10)
            unit = {1: "إحدى", 2: "اثنتان"}.get(ones, _ONES_FEM[ones])
            parts.append(f"{unit} و{_TENS[tens]}" if ones else _TENS[tens])
    return " و".join(parts)


class MSARules(Rules):
    code = "arb"
    latin_script = False
    words = {
        "point": "فاصلة", "minus": "سالب", "and": "و", "to": "إلى", "percent": "بالمئة", "per_mille": "بالألف",
        "dot": "نقطة", "slash": "شرطة مائلة", "underscore": "شرطة سفلية", "dash": "شرطة", "at": "آت", "hashtag": "وسم",
        "plus": "زائد", "equals": "يساوي", "not_equal": "لا يساوي", "less_equal": "أصغر من أو يساوي",
        "greater_equal": "أكبر من أو يساوي", "less": "أصغر من", "greater": "أكبر من", "times": "ضرب",
        "divided": "مقسوما على", "approx": "حوالي", "degrees": "درجة", "or": "أو",
    }
    months = _MONTHS
    abbreviations = {
        "أ.د.": "الأستاذ الدكتور", "أ.د": "الأستاذ الدكتور", "إلخ": "إلى آخره", "الخ": "إلى آخره",
        "ص.ب": "صندوق بريد", "ق.م": "قبل الميلاد", "ج.م.ع": "جمهورية مصر العربية", "ت:": "هاتف:",
    }
    abbreviation_patterns = [
        (r"(?<![؀-ۿ.])د\.\s?(?=[؀-ۿ])", "الدكتور "),
        (r"(?<![؀-ۿ.])م\.\s?(?=[؀-ۿ])", "المهندس "),
        (r"(?<![؀-ۿ.])أ\.\s?(?=[؀-ۿ])", "الأستاذ "),
        (r"(?<![؀-ۿ.])ش\.\s?(?=[؀-ۿ])", "شارع "),
        (r"(?<![\w])رقم\s?#?\s?(?=\d)", "رقم "),
        (r"#\s?(?=\d)", "رقم "),
    ]
    currency_aliases = {"ج.م": "EGP", "ج م": "EGP", "ر.س": "SAR", "د.إ": "AED", "دولار": "USD"}
    currencies = {
        "USD": Money(Noun("دولار", "دولارات", two="دولاران", acc="دولارا"), Noun("سنت", "سنتات", two="سنتان", acc="سنتا")),
        "EUR": Money(Noun("يورو", "يورو", two="يورو", acc="يورو"), Noun("سنت", "سنتات", two="سنتان", acc="سنتا")),
        "GBP": Money(Noun("جنيه إسترليني", "جنيهات إسترلينية", two="جنيهان إسترلينيان", acc="جنيها إسترلينيا"),
                     Noun("بنس", "بنسات", two="بنسان", acc="بنسا")),
        "EGP": Money(Noun("جنيه", "جنيهات", two="جنيهان", acc="جنيها"), Noun("قرش", "قروش", two="قرشان", acc="قرشا")),
        "SAR": Money(Noun("ريال", "ريالات", two="ريالان", acc="ريالا"), Noun("هللة", "هللات", two="هللتان", acc="هللة", feminine=True)),
        "AED": Money(Noun("درهم", "دراهم", two="درهمان", acc="درهما"), Noun("فلس", "فلوس", two="فلسان", acc="فلسا")),
        "JPY": Money(Noun("ين", "ين", two="ين", acc="ين")),
        "CNY": Money(Noun("يوان", "يوان", two="يوان", acc="يوان")),
        "INR": Money(Noun("روبية", "روبيات", two="روبيتان", acc="روبية", feminine=True)),
    }
    units = {
        "km": Noun("كيلومتر", "كيلومترات", two="كيلومتران", acc="كيلومترا"),
        "m": Noun("متر", "أمتار", two="متران", acc="مترا"),
        "cm": Noun("سنتيمتر", "سنتيمترات", two="سنتيمتران", acc="سنتيمترا"),
        "mm": Noun("مليمتر", "مليمترات", two="مليمتران", acc="مليمترا"),
        "mi": Noun("ميل", "أميال", two="ميلان", acc="ميلا"), "ft": Noun("قدم", "أقدام", two="قدمان", acc="قدما"),
        "kg": Noun("كيلوغرام", "كيلوغرامات", two="كيلوغرامان", acc="كيلوغراما"),
        "g": Noun("غرام", "غرامات", two="غرامان", acc="غراما"), "mg": Noun("مليغرام", "مليغرامات", two="مليغرامان", acc="مليغراما"),
        "lb": Noun("رطل", "أرطال", two="رطلان", acc="رطلا"), "lbs": Noun("رطل", "أرطال", two="رطلان", acc="رطلا"),
        "oz": Noun("أونصة", "أونصات", two="أونصتان", acc="أونصة", feminine=True),
        "l": Noun("لتر", "لترات", two="لتران", acc="لترا"), "L": Noun("لتر", "لترات", two="لتران", acc="لترا"),
        "ml": Noun("مليلتر", "مليلترات", two="مليلتران", acc="مليلترا"), "mL": Noun("مليلتر", "مليلترات", two="مليلتران", acc="مليلترا"),
        "km/h": Noun("كيلومتر في الساعة", "كيلومترات في الساعة", two="كيلومتران في الساعة", acc="كيلومترا في الساعة"),
        "kmh": Noun("كيلومتر في الساعة", "كيلومترات في الساعة", two="كيلومتران في الساعة", acc="كيلومترا في الساعة"),
        "mph": Noun("ميل في الساعة", "أميال في الساعة", two="ميلان في الساعة", acc="ميلا في الساعة"),
        "m/s": Noun("متر في الثانية", "أمتار في الثانية", two="متران في الثانية", acc="مترا في الثانية"),
        "km²": Noun("كيلومتر مربع", "كيلومترات مربعة", two="كيلومتران مربعان", acc="كيلومترا مربعا"),
        "m²": Noun("متر مربع", "أمتار مربعة", two="متران مربعان", acc="مترا مربعا"),
        "m³": Noun("متر مكعب", "أمتار مكعبة", two="متران مكعبان", acc="مترا مكعبا"),
        "°C": Noun("درجة مئوية", "درجات مئوية", two="درجتان مئويتان", acc="درجة مئوية", feminine=True),
        "ºC": Noun("درجة مئوية", "درجات مئوية", two="درجتان مئويتان", acc="درجة مئوية", feminine=True),
        "°F": Noun("درجة فهرنهايت", "درجات فهرنهايت", two="درجتان فهرنهايت", acc="درجة فهرنهايت", feminine=True),
        "°": Noun("درجة", "درجات", two="درجتان", acc="درجة", feminine=True),
        "GB": Noun("غيغابايت", "غيغابايت", two="غيغابايت", acc="غيغابايت"), "MB": Noun("ميغابايت", "ميغابايت", two="ميغابايت", acc="ميغابايت"),
        "KB": Noun("كيلوبايت", "كيلوبايت", two="كيلوبايت", acc="كيلوبايت"), "TB": Noun("تيرابايت", "تيرابايت", two="تيرابايت", acc="تيرابايت"),
        "Mbps": Noun("ميغابت في الثانية", "ميغابت في الثانية", two="ميغابت في الثانية", acc="ميغابت في الثانية"),
        "fps": Noun("إطار في الثانية", "إطارات في الثانية", two="إطاران في الثانية", acc="إطارا في الثانية"),
        "Hz": Noun("هرتز", "هرتز", two="هرتز", acc="هرتز"), "W": Noun("واط", "واطات", two="واطان", acc="واطا"),
        "kW": Noun("كيلوواط", "كيلوواطات", two="كيلوواطان", acc="كيلوواطا"), "kWh": Noun("كيلوواط ساعة", "كيلوواط ساعة", two="كيلوواط ساعة", acc="كيلوواط ساعة"),
        "V": Noun("فولت", "فولتات", two="فولتان", acc="فولتا"), "mAh": Noun("ملي أمبير ساعة", "ملي أمبير ساعة", two="ملي أمبير ساعة", acc="ملي أمبير ساعة"),
        "h": Noun("ساعة", "ساعات", two="ساعتان", acc="ساعة", feminine=True),
        "hr": Noun("ساعة", "ساعات", two="ساعتان", acc="ساعة", feminine=True),
        "min": Noun("دقيقة", "دقائق", two="دقيقتان", acc="دقيقة", feminine=True),
        "s": Noun("ثانية", "ثوان", two="ثانيتان", acc="ثانية", feminine=True),
        "sec": Noun("ثانية", "ثوان", two="ثانيتان", acc="ثانية", feminine=True),
        "ms": Noun("جزء من الثانية", "أجزاء من الثانية", two="جزءان من الثانية", acc="جزءا من الثانية"),
        "px": Noun("بكسل", "بكسل", two="بكسل", acc="بكسل"), "x": Noun("مرة", "مرات", two="مرتان", acc="مرة", feminine=True),
    }
    unit_aliases = {"كم": "km", "كلم": "km", "م": "m", "سم": "cm", "مم": "mm", "ملم": "mm", "كجم": "kg", "كغ": "kg",
                    "كغم": "kg", "جم": "g", "غ": "g", "غم": "g", "ل": "l", "مل": "ml", "كم/س": "km/h", "كم/ساعة": "km/h",
                    "م²": "m²", "م2": "m²", "م³": "m³", "°م": "°C", "درجة مئوية": "°C", "ساعة": "h", "دقيقة": "min", "ثانية": "s"}
    fraction_words = {"½": "نصف", "⅓": "ثلث", "⅔": "ثلثان", "¼": "ربع", "¾": "ثلاثة أرباع", "⅕": "خمس", "⅛": "ثمن"}

    # ------------------------------------------------------------ numbers
    def cardinal(self, n: int) -> str:
        if n == 0:
            return "صفر"
        parts = []
        for value, forms in ((10**9, ("مليار", "ملياران", "مليارات", "مليارا")),
                             (10**6, ("مليون", "مليونان", "ملايين", "مليونا")),
                             (10**3, ("ألف", "ألفان", "آلاف", "ألفا"))):
            if n >= value:
                count, n = divmod(n, value)
                phrase = _scale_noun(count, *forms)
                parts.append(phrase.replace("مئتان ", "مئتا "))
        if n:
            parts.append(_below_1000(n))
        return " و".join(parts)

    def cardinal_fem(self, n: int) -> str:
        rest = n % 1000
        if n < 1000:
            return _below_1000_fem(n)
        if rest == 0:
            return self.cardinal(n)
        return f"{self.cardinal(n - rest)} و{_below_1000_fem(rest)}"

    def cardinal_before(self, n: int, next_word: str) -> str:
        return self.cardinal_fem(n) if next_word in _FEMININE_PLURALS else self.cardinal(n)

    def is_year(self, value: int, before: str, after: str) -> bool:
        return 1000 <= value <= 2100 and bool(re.search(r"(عام|سنة|في|منذ|حتى|قبل|بعد|من|إلى)\s*$", before))

    def ordinal(self, n: int, feminine: bool = False) -> str:
        table = _ORD_FEM if feminine else _ORD
        if 1 <= n <= 10:
            return table[n]
        if 11 <= n <= 19:
            unit = ("الحادية" if feminine else "الحادي") if n == 11 else table[n - 10]
            return f"{unit} {'عشرة' if feminine else 'عشر'}"
        if 20 <= n <= 99:
            tens, ones = divmod(n, 10)
            ten_word = "ال" + _TENS[tens]
            if not ones:
                return ten_word
            unit = ("الحادية" if feminine else "الحادي") if ones == 1 else table[ones]
            return f"{unit} و{ten_word}"
        return self.cardinal(n)

    def genitive(self, words: str) -> str:
        out = []
        for word in words.split(" "):
            prefix = "و" if word.startswith("و") and (word[1:] in _GENITIVE or word[1:] in _TENS) else ""
            core = word[len(prefix):]
            if core in _GENITIVE:
                core = _GENITIVE[core]
            elif core in _TENS and core.endswith("ون"):
                core = core[:-2] + "ين"
            out.append(prefix + core)
        return " ".join(out)

    def decimal_words(self, integer: int, fraction: str) -> str:
        spoken = self.digit_words(fraction) if fraction.startswith("0") or len(fraction) > 2 else self.cardinal(int(fraction))
        return f"{self.cardinal(integer)} فاصلة {spoken}"

    def year(self, n: int) -> str:
        return self.genitive(self.cardinal(n))

    def count(self, integer: int, fraction: str, noun: Noun) -> str:
        if fraction:
            return f"{self.decimal_words(integer, fraction)} {noun.acc or noun.one}"
        if integer == 1:
            return f"{noun.one} {'واحدة' if noun.feminine else 'واحد'}"
        if integer == 2:
            return noun.two or f"{self.cardinal(2)} {noun.one}"
        rest = integer % 100
        number = self.cardinal_fem if noun.feminine else self.cardinal
        if 3 <= integer <= 10:
            return f"{number(integer)} {noun.many}"
        if 11 <= rest <= 99:
            return f"{number(integer)} {noun.acc or noun.one}"
        return f"{number(integer)} {noun.one}"

    def percent(self, words: str) -> str:
        return f"{words} بالمئة"

    def range(self, a: str, b: str) -> str:
        return f"من {a} إلى {b}"

    def fraction(self, a: int, b: int) -> Optional[str]:
        names = {2: "نصف", 3: "ثلث", 4: "ربع"}
        if a == 1 and b in names:
            return names[b]
        if b == 3 and a == 2:
            return "ثلثان"
        if b == 4 and a == 3:
            return "ثلاثة أرباع"
        return None

    def time(self, hour: int, minute: int, period: Optional[str]) -> str:
        tail = ""
        if period:
            tail = " صباحا" if period == "a" else " مساء"
        elif hour >= 12:
            tail = " ظهرا" if hour < 15 else " مساء"
        elif hour < 12:
            tail = " صباحا" if hour >= 5 else " ليلا"
        h = hour % 12 or 12
        if minute == 45 or minute == 40:
            h = h % 12 + 1
            phrase = " إلا ربعا" if minute == 45 else " إلا ثلثا"
        elif minute in _TIME_WORDS:
            phrase = " " + _TIME_WORDS[minute]
        elif minute == 0:
            phrase = ""
        else:
            phrase = " و" + self.count(minute, "", self.units["min"])
        return f"الساعة {self.ordinal(h, feminine=True)}{phrase}{tail}"

    def date(self, day: int, month: int, year: Optional[int]) -> str:
        spoken = f"{self.ordinal(day)} من {self.months[month - 1]}"
        return f"{spoken} عام {self.year(year)}" if year else spoken

    def before(self, text: str) -> str:
        text = re.sub(r"الساعة\s+(?=\d{1,2}:\d{2})", "", text)  # the spoken time says "الساعة" itself
        # "2024م" / "1445هـ" → "عام ألفين وأربعة وعشرين ميلادية"
        text = re.sub(r"(\d{3,4})\s?م(?![ء-ي])", lambda m: f"{self.year(int(m.group(1)))} ميلادية", text)
        text = re.sub(r"(\d{3,4})\s?هـ?(?![ء-ي])", lambda m: f"{self.year(int(m.group(1)))} هجرية", text)

        # "10:30 ص" / "م"
        def ampm(m: re.Match) -> str:
            return self.time(int(m.group(1)), int(m.group(2)), "a" if m.group(3) == "ص" else "p")

        text = re.sub(r"(?<![\d:])(\d{1,2}):([0-5]\d)\s?(ص|م)(?![ء-ي])", ampm, text)

        # the number one follows its noun: "1 ثانية" → "ثانية واحدة", "1 كتاب" → "كتاب واحد"
        def one(m: re.Match) -> str:
            noun = m.group(1)
            if noun in self.unit_aliases or noun in self.currency_aliases:
                return m.group(0)
            return f"{noun} {'واحدة' if noun.endswith('ة') else 'واحد'}"

        return re.sub(r"(?<![\d.,])1\s+([ء-ي]{2,})(?![ء-ي])", one, text)

    def after(self, text: str) -> str:
        text = re.sub(r"(?<![^\s])و\s+(?=[؀-ۿ])", "و", text)  # "و خمسون" → "وخمسون"
        return text.replace(",", "،").replace("?", "؟").replace(";", "؛")
