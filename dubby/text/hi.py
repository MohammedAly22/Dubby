"""Hindi normalization rules (Indian numbering: हज़ार, लाख, करोड़, अरब)."""

from __future__ import annotations

import re
from typing import Optional

from dubby.text.common import Money, Noun, Rules

# 0–99 are irregular in Hindi, so they are listed in full.
_BELOW_100 = (
    "शून्य एक दो तीन चार पाँच छह सात आठ नौ दस ग्यारह बारह तेरह चौदह पंद्रह सोलह सत्रह अठारह उन्नीस "
    "बीस इक्कीस बाईस तेईस चौबीस पच्चीस छब्बीस सत्ताईस अट्ठाईस उनतीस तीस इकतीस बत्तीस तैंतीस चौंतीस पैंतीस "
    "छत्तीस सैंतीस अड़तीस उनतालीस चालीस इकतालीस बयालीस तैंतालीस चवालीस पैंतालीस छियालीस सैंतालीस अड़तालीस "
    "उनचास पचास इक्यावन बावन तिरपन चौवन पचपन छप्पन सत्तावन अट्ठावन उनसठ साठ इकसठ बासठ तिरसठ चौंसठ पैंसठ "
    "छियासठ सड़सठ अड़सठ उनहत्तर सत्तर इकहत्तर बहत्तर तिहत्तर चौहत्तर पचहत्तर छिहत्तर सतहत्तर अठहत्तर उनासी "
    "अस्सी इक्यासी बयासी तिरासी चौरासी पचासी छियासी सत्तासी अट्ठासी नवासी नब्बे इक्यानबे बानबे तिरानबे चौरानबे "
    "पंचानबे छियानबे सत्तानबे अट्ठानबे निन्यानबे"
).split()
assert len(_BELOW_100) == 100
_ORDINALS = {1: "पहला", 2: "दूसरा", 3: "तीसरा", 4: "चौथा", 5: "पाँचवाँ", 6: "छठा"}
_MONTHS = ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"]


def _n(word: str) -> Noun:
    return Noun(word, word)


class HindiRules(Rules):
    code = "hi"
    latin_script = False
    groups = ","
    words = {
        "point": "दशमलव", "minus": "माइनस", "and": "और", "to": "से", "percent": "प्रतिशत", "per_mille": "प्रति हज़ार",
        "dot": "डॉट", "slash": "स्लैश", "underscore": "अंडरस्कोर", "dash": "डैश", "at": "एट", "hashtag": "हैशटैग",
        "plus": "प्लस", "equals": "बराबर", "not_equal": "बराबर नहीं", "less_equal": "से कम या बराबर",
        "greater_equal": "से ज़्यादा या बराबर", "less": "से कम", "greater": "से ज़्यादा", "times": "गुणा",
        "divided": "भाग", "approx": "लगभग", "degrees": "डिग्री", "or": "या",
    }
    months = _MONTHS
    abbreviations = {
        "डॉ.": "डॉक्टर", "प्रो.": "प्रोफ़ेसर", "श्री.": "श्री", "सुश्री.": "सुश्री", "कि.मी.": "किलोमीटर",
        "कि.ग्रा.": "किलोग्राम", "से.मी.": "सेंटीमीटर", "मि.मी.": "मिलीमीटर", "ई.पू.": "ईसा पूर्व", "ई.": "ईसवी",
        "रु.": "रुपये", "नं.": "नंबर", "पृ.": "पृष्ठ", "सं.": "संख्या", "etc.": "वगैरह", "Dr.": "डॉक्टर", "Mr.": "मिस्टर",
    }
    abbreviation_patterns = [(r"#\s?(?=\d)", "नंबर ")]
    currency_aliases = {"रु.": "INR", "रू.": "INR", "₨": "INR"}
    currencies = {
        "INR": Money(Noun("रुपया", "रुपये"), Noun("पैसा", "पैसे")),
        "USD": Money(_n("डॉलर"), _n("सेंट")),
        "EUR": Money(_n("यूरो"), _n("सेंट")),
        "GBP": Money(_n("पाउंड"), _n("पेंस")),
        "EGP": Money(_n("मिस्री पाउंड")),
        "SAR": Money(_n("सऊदी रियाल")),
        "AED": Money(_n("दिरहम")),
        "JPY": Money(_n("येन")),
        "CNY": Money(_n("युआन")),
    }
    units = {
        "km": _n("किलोमीटर"), "m": _n("मीटर"), "cm": _n("सेंटीमीटर"), "mm": _n("मिलीमीटर"), "mi": _n("मील"), "ft": _n("फ़ुट"),
        "kg": _n("किलोग्राम"), "g": _n("ग्राम"), "mg": _n("मिलीग्राम"), "lb": _n("पाउंड"), "lbs": _n("पाउंड"), "oz": _n("औंस"),
        "l": _n("लीटर"), "L": _n("लीटर"), "ml": _n("मिलीलीटर"), "mL": _n("मिलीलीटर"), "km/h": _n("किलोमीटर प्रति घंटा"),
        "kmh": _n("किलोमीटर प्रति घंटा"), "kph": _n("किलोमीटर प्रति घंटा"), "mph": _n("मील प्रति घंटा"),
        "m/s": _n("मीटर प्रति सेकंड"), "km²": _n("वर्ग किलोमीटर"), "m²": _n("वर्ग मीटर"), "m2": _n("वर्ग मीटर"),
        "m³": _n("घन मीटर"), "°C": _n("डिग्री सेल्सियस"), "ºC": _n("डिग्री सेल्सियस"), "°F": _n("डिग्री फ़ारेनहाइट"),
        "°": _n("डिग्री"), "GB": _n("जीबी"), "MB": _n("एमबी"), "KB": _n("केबी"), "TB": _n("टीबी"), "Mbps": _n("एमबीपीएस"),
        "fps": _n("फ़्रेम प्रति सेकंड"), "Hz": _n("हर्ट्ज़"), "W": _n("वाट"), "kW": _n("किलोवाट"), "kWh": _n("यूनिट"),
        "V": _n("वोल्ट"), "mAh": _n("एमएएच"), "h": Noun("घंटा", "घंटे"), "hr": Noun("घंटा", "घंटे"), "hrs": Noun("घंटा", "घंटे"),
        "min": _n("मिनट"), "mins": _n("मिनट"), "s": _n("सेकंड"), "sec": _n("सेकंड"), "ms": _n("मिलीसेकंड"),
        "px": _n("पिक्सेल"), "x": _n("गुना"),
    }
    unit_aliases = {"किमी": "km", "मी": "m", "सेमी": "cm", "किग्रा": "kg", "ग्रा": "g", "ली": "l"}
    fraction_words = {"½": "आधा", "¼": "चौथाई", "¾": "पौना", "⅓": "एक तिहाई", "⅔": "दो तिहाई"}

    def cardinal(self, n: int) -> str:
        if n < 100:
            return _BELOW_100[n]
        parts = []
        for value, name in ((10**11, "खरब"), (10**9, "अरब"), (10**7, "करोड़"), (10**5, "लाख"), (10**3, "हज़ार"), (100, "सौ")):
            if n >= value:
                count, n = divmod(n, value)
                parts.append(f"{self.cardinal(count)} {name}")
        if n:
            parts.append(_BELOW_100[n])
        return " ".join(parts)

    def ordinal(self, n: int, feminine: bool = False) -> str:
        word = _ORDINALS.get(n) or f"{self.cardinal(n)}वाँ"
        if feminine:
            word = re.sub(r"(ला|रा|था|ठा|वाँ)$", lambda m: {"ला": "ली", "रा": "री", "था": "थी", "ठा": "ठी", "वाँ": "वीं"}[m.group(1)], word)
        return word

    def year(self, n: int) -> str:
        if 1100 <= n <= 1999:  # 1998 → उन्नीस सौ अट्ठानबे
            return f"{self.cardinal(n // 100)} सौ {self.cardinal(n % 100)}" if n % 100 else f"{self.cardinal(n // 100)} सौ"
        return self.cardinal(n)

    def is_year(self, value: int, before: str, after: str) -> bool:
        return 1100 <= value <= 2099 and bool(re.search(r"(सन्|साल|वर्ष|में)\s*$", before) or re.match(r"\s*(में|से|तक|का|की|के)\b", after))

    def count(self, integer: int, fraction: str, noun: Noun) -> str:
        words = self.number(integer, fraction)
        return f"{words} {noun.one if integer == 1 and not fraction else noun.many}"

    def fraction(self, a: int, b: int) -> Optional[str]:
        return {(1, 2): "आधा", (1, 4): "चौथाई", (3, 4): "पौना", (1, 3): "एक तिहाई", (2, 3): "दो तिहाई"}.get((a, b))

    def time(self, hour: int, minute: int, period: Optional[str], part: Optional[str] = None) -> str:
        if period == "p" and hour < 12:
            hour += 12
        elif period == "a" and hour == 12:
            hour = 0
        if part is None and (period or hour > 12):  # only say the part of day when the clock makes it clear
            if hour < 5:
                part = "रात"
            elif hour < 12:
                part = "सुबह"
            elif hour < 16:
                part = "दोपहर"
            elif hour < 20:
                part = "शाम"
            else:
                part = "रात"
        h = hour % 12 or 12
        nxt = h % 12 + 1
        if minute == 0:
            spoken = f"{self.cardinal(h)} बजे"
        elif minute == 30:
            spoken = {1: "डेढ़ बजे", 2: "ढाई बजे"}.get(h, f"साढ़े {self.cardinal(h)} बजे")
        elif minute == 15:
            spoken = f"सवा {self.cardinal(h)} बजे"
        elif minute == 45:
            spoken = f"पौने {self.cardinal(nxt)} बजे"
        else:
            spoken = f"{self.cardinal(h)} बजकर {self.cardinal(minute)} मिनट"
        return f"{part} {spoken}" if part else spoken

    def date(self, day: int, month: int, year: Optional[int]) -> str:
        spoken = f"{self.cardinal(day)} {self.months[month - 1]}"
        return f"{spoken} {self.year(year)}" if year else spoken

    def parse_indian(self, text: str) -> str:
        # Indian digit grouping "1,00,000" → "100000" before the generic parser sees it
        return re.sub(r"(?<![\d,])\d{1,2}(?:,\d{2})+,\d{3}(?![\d,])", lambda m: m.group(0).replace(",", ""), text)

    def before(self, text: str) -> str:
        text = self.parse_indian(text)

        # "सुबह 10:30 बजे" → "सुबह साढ़े दस बजे" (keep the written part of day, don't repeat बजे)
        def clock(m: re.Match) -> str:
            spoken = self.time(int(m.group(2)), int(m.group(3)), None, m.group(1))
            return spoken if m.group(4) or spoken.endswith("मिनट") else spoken

        text = re.sub(r"(?:(सुबह|दोपहर|शाम|रात)\s+)?(?<![\d:])(\d{1,2}):([0-5]\d)(?![\d:])(\s*बजे)?", clock, text)
        return text.replace("।", "। ").replace("  ", " ")
