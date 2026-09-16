"""English normalization rules (US conventions)."""

from __future__ import annotations

import re
from typing import Optional

from dubby.text.common import Money, Noun, Rules

_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
         "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
_SCALES = [(10**15, "quadrillion"), (10**12, "trillion"), (10**9, "billion"), (10**6, "million"), (10**3, "thousand")]
_ORDINAL_IRREGULAR = {"one": "first", "two": "second", "three": "third", "five": "fifth", "eight": "eighth",
                      "nine": "ninth", "twelve": "twelfth"}
_YEAR_CUES = re.compile(r"\b(in|since|from|until|till|by|of|year|during|circa|around|before|after|between|and|to|early|late|mid|spring|summer|autumn|fall|winter|january|february|march|april|may|june|july|august|september|october|november|december)\s*,?\s*$", re.I)


def _below_1000(n: int) -> str:
    parts = []
    hundreds, rest = divmod(n, 100)
    if hundreds:
        parts.append(f"{_ONES[hundreds]} hundred")
    if rest:
        if rest < 20:
            parts.append(_ONES[rest])
        else:
            tens, ones = divmod(rest, 10)
            parts.append(_TENS[tens] + (f"-{_ONES[ones]}" if ones else ""))
    return " ".join(parts)


class EnglishRules(Rules):
    code = "en"
    date_order = "MDY"
    words = {
        "point": "point", "minus": "minus", "and": "and", "to": "to", "percent": "percent", "per_mille": "per mille",
        "dot": "dot", "slash": "slash", "underscore": "underscore", "dash": "dash", "at": "at", "hashtag": "hashtag",
        "plus": "plus", "equals": "equals", "not_equal": "is not equal to", "less_equal": "is less than or equal to",
        "greater_equal": "is greater than or equal to", "less": "is less than", "greater": "is greater than",
        "times": "times", "divided": "divided by", "approx": "approximately", "degrees": "degrees", "or": "or",
        "thousand": "thousand", "million": "million", "billion": "billion",
    }
    months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    abbreviations = {
        "Mr.": "Mister", "Mrs.": "Missus", "Ms.": "Miss", "Dr.": "Doctor", "Prof.": "Professor", "Sr.": "Senior",
        "Jr.": "Junior", "Mt.": "Mount", "Ave.": "Avenue", "Blvd.": "Boulevard", "Rd.": "Road", "Ln.": "Lane",
        "Co.": "Company", "Corp.": "Corporation", "Inc.": "Incorporated", "Ltd.": "Limited", "Dept.": "Department",
        "Gov.": "Governor", "Gen.": "General", "Capt.": "Captain", "Lt.": "Lieutenant", "Sgt.": "Sergeant",
        "vs.": "versus", "vs": "versus", "etc.": "et cetera", "e.g.": "for example", "i.e.": "that is",
        "approx.": "approximately", "est.": "established", "govt.": "government", "misc.": "miscellaneous",
        "Jan.": "January", "Feb.": "February", "Mar.": "March", "Apr.": "April", "Aug.": "August", "Sept.": "September",
        "Sep.": "September", "Oct.": "October", "Nov.": "November", "Dec.": "December",
        "Mon.": "Monday", "Tue.": "Tuesday", "Tues.": "Tuesday", "Wed.": "Wednesday", "Thu.": "Thursday",
        "Thurs.": "Thursday", "Fri.": "Friday", "Sat.": "Saturday", "Sun.": "Sunday",
        "U.S.": "U S", "U.K.": "U K", "U.N.": "U N", "E.U.": "E U", "Ph.D.": "P H D", "a.k.a.": "also known as",
        "w/": "with", "w/o": "without",
    }
    abbreviation_patterns = [
        (r"\bSt\.(?=\s+[A-Z])", "Saint"),
        (r"\bSt\.", "Street"),
        (r"\b[Nn]o\.\s?(?=\d)", "number "),
        (r"\b[Nn]os\.\s?(?=\d)", "numbers "),
        (r"#\s?(?=\d)", "number "),
        (r"\bVol\.\s?(?=\d)", "volume "),
        (r"\bCh\.\s?(?=\d)", "chapter "),
        (r"\bpp\.\s?(?=\d)", "pages "),
        (r"\bp\.\s?(?=\d)", "page "),
        (r"\bFig\.\s?(?=\d)", "figure "),
    ]
    currencies = {
        "USD": Money(Noun("dollar", "dollars"), Noun("cent", "cents")),
        "EUR": Money(Noun("euro", "euros"), Noun("cent", "cents")),
        "GBP": Money(Noun("pound", "pounds"), Noun("penny", "pence")),
        "EGP": Money(Noun("Egyptian pound", "Egyptian pounds"), Noun("piastre", "piastres")),
        "SAR": Money(Noun("Saudi riyal", "Saudi riyals"), Noun("halala", "halalas")),
        "AED": Money(Noun("dirham", "dirhams"), Noun("fils", "fils")),
        "JPY": Money(Noun("yen", "yen")),
        "CNY": Money(Noun("yuan", "yuan"), Noun("fen", "fen")),
        "INR": Money(Noun("rupee", "rupees"), Noun("paisa", "paise")),
    }
    units = {
        "km": Noun("kilometer", "kilometers"), "m": Noun("meter", "meters"), "cm": Noun("centimeter", "centimeters"),
        "mm": Noun("millimeter", "millimeters"), "mi": Noun("mile", "miles"), "ft": Noun("foot", "feet"),
        "kg": Noun("kilogram", "kilograms"), "g": Noun("gram", "grams"), "mg": Noun("milligram", "milligrams"),
        "lb": Noun("pound", "pounds"), "lbs": Noun("pound", "pounds"), "oz": Noun("ounce", "ounces"),
        "l": Noun("liter", "liters"), "L": Noun("liter", "liters"), "ml": Noun("milliliter", "milliliters"), "mL": Noun("milliliter", "milliliters"),
        "km/h": Noun("kilometer per hour", "kilometers per hour"), "kmh": Noun("kilometer per hour", "kilometers per hour"),
        "kph": Noun("kilometer per hour", "kilometers per hour"), "mph": Noun("mile per hour", "miles per hour"),
        "m/s": Noun("meter per second", "meters per second"),
        "km²": Noun("square kilometer", "square kilometers"), "km2": Noun("square kilometer", "square kilometers"),
        "m²": Noun("square meter", "square meters"), "m2": Noun("square meter", "square meters"),
        "cm²": Noun("square centimeter", "square centimeters"), "m³": Noun("cubic meter", "cubic meters"),
        "m3": Noun("cubic meter", "cubic meters"), "cm³": Noun("cubic centimeter", "cubic centimeters"),
        "°C": Noun("degree Celsius", "degrees Celsius"), "ºC": Noun("degree Celsius", "degrees Celsius"),
        "°F": Noun("degree Fahrenheit", "degrees Fahrenheit"), "ºF": Noun("degree Fahrenheit", "degrees Fahrenheit"),
        "°": Noun("degree", "degrees"),
        "GB": Noun("gigabyte", "gigabytes"), "GiB": Noun("gibibyte", "gibibytes"), "MB": Noun("megabyte", "megabytes"),
        "MiB": Noun("mebibyte", "mebibytes"), "KB": Noun("kilobyte", "kilobytes"), "kB": Noun("kilobyte", "kilobytes"),
        "TB": Noun("terabyte", "terabytes"), "Gbps": Noun("gigabit per second", "gigabits per second"),
        "Mbps": Noun("megabit per second", "megabits per second"), "kbps": Noun("kilobit per second", "kilobits per second"),
        "fps": Noun("frame per second", "frames per second"), "Hz": Noun("hertz", "hertz"), "kHz": Noun("kilohertz", "kilohertz"),
        "MHz": Noun("megahertz", "megahertz"), "GHz": Noun("gigahertz", "gigahertz"),
        "W": Noun("watt", "watts"), "kW": Noun("kilowatt", "kilowatts"), "kWh": Noun("kilowatt hour", "kilowatt hours"),
        "V": Noun("volt", "volts"), "mAh": Noun("milliamp hour", "milliamp hours"),
        "h": Noun("hour", "hours"), "hr": Noun("hour", "hours"), "hrs": Noun("hour", "hours"),
        "min": Noun("minute", "minutes"), "mins": Noun("minute", "minutes"), "s": Noun("second", "seconds"),
        "sec": Noun("second", "seconds"), "secs": Noun("second", "seconds"), "ms": Noun("millisecond", "milliseconds"),
        "px": Noun("pixel", "pixels"), "x": Noun("times", "times"),
    }
    fraction_words = {"½": "one half", "⅓": "one third", "⅔": "two thirds", "¼": "one quarter", "¾": "three quarters",
                      "⅕": "one fifth", "⅛": "one eighth"}
    ordinal_pattern = r"(?<![\w.,])(\d+)(st|nd|rd|th)\b"
    pronounceable = frozenset({"NASA", "NATO", "UNESCO", "UNICEF", "COVID", "FIFA", "UEFA", "OPEC", "IKEA", "LASER", "RADAR",
                               "SCUBA", "AIDS", "ASCII", "JPEG", "GIF", "PIN", "RAM", "ROM", "LAN", "WAN", "SIM", "NASDAQ",
                               "OK", "SWAT", "ZIP", "SARS", "ISIS", "YOLO", "FOMO", "GIFs", "LOL", "ASAP"})

    def cardinal(self, n: int) -> str:
        if n == 0:
            return "zero"
        parts = []
        for value, name in _SCALES:
            if n >= value:
                count, n = divmod(n, value)
                parts.append(f"{_below_1000(count)} {name}")
        if n:
            parts.append(_below_1000(n))
        return " ".join(parts)

    def ordinal(self, n: int, feminine: bool = False) -> str:
        words = self.cardinal(n)
        head, sep, last = words.rpartition(" ") if "-" not in words.split(" ")[-1] else words.rpartition("-")
        if last in _ORDINAL_IRREGULAR:
            last = _ORDINAL_IRREGULAR[last]
        elif last.endswith("y"):
            last = last[:-1] + "ieth"
        else:
            last += "th"
        return f"{head}{sep}{last}"

    def year(self, n: int) -> str:
        if 2000 <= n <= 2009 or n % 1000 == 0 or not 1000 <= n <= 2999:
            return self.cardinal(n)
        high, low = divmod(n, 100)
        if low == 0:
            return f"{self.cardinal(high)} hundred"
        return f"{self.cardinal(high)} {'oh ' if low < 10 else ''}{self.cardinal(low)}"

    def is_year(self, value: int, before: str, after: str) -> bool:
        if not 1100 <= value <= 2099:
            return False
        return bool(_YEAR_CUES.search(before)) or bool(re.match(r"^s\b|^'s\b|^\s*(AD|BC|BCE|CE)\b", after))

    def count(self, integer: int, fraction: str, noun: Noun) -> str:
        words = self.number(integer, fraction)
        return f"{words} {noun.one if integer == 1 and not fraction else noun.many}"

    def fraction(self, a: int, b: int) -> Optional[str]:
        names = {2: ("half", "halves"), 3: ("third", "thirds"), 4: ("quarter", "quarters")}
        if b in names:
            return f"{self.cardinal(a)} {names[b][0] if a == 1 else names[b][1]}"
        return f"{self.cardinal(a)} {self.ordinal(b)}{'s' if a > 1 else ''}"

    def time(self, hour: int, minute: int, period: Optional[str]) -> str:
        suffix = ""
        if period:
            suffix = " a m" if period == "a" else " p m"
        elif hour == 0 and minute == 0:
            return "midnight"
        elif hour == 12 and minute == 0:
            return "noon"
        elif hour > 12:
            hour, suffix = hour - 12, " p m"
        elif hour == 0:
            hour, suffix = 12, " a m"
        if minute == 0:
            return f"{self.cardinal(hour)}{suffix}" if suffix else f"{self.cardinal(hour)} o'clock"
        minutes = f"oh {self.cardinal(minute)}" if minute < 10 else self.cardinal(minute)
        return f"{self.cardinal(hour)} {minutes}{suffix}"

    def date(self, day: int, month: int, year: Optional[int]) -> str:
        spoken = f"{self.months[month - 1]} {self.ordinal(day)}"
        return f"{spoken}, {self.year(year)}" if year else spoken

    def before(self, text: str) -> str:
        month = "|".join(self.months + [m[:3] for m in self.months])
        # "May 5, 2024" / "May 5th" → "May fifth, twenty twenty-four"
        def textual(m: re.Match) -> str:
            name = next(x for x in self.months if x.lower().startswith(m.group(1).lower()[:3]))
            spoken = f"{name} {self.ordinal(int(m.group(2)))}"
            return f"{spoken}, {self.year(int(m.group(3)))}" if m.group(3) else spoken

        text = re.sub(rf"\b({month})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?:,?\s+(\d{{4}}))?", textual, text)
        # decades: "the 1990s" → "the nineteen nineties", "the 80s" → "the eighties"
        def decade(m: re.Match) -> str:
            value = int(m.group(1))
            words = self.year(value) if value >= 1000 else self.cardinal(value)
            return words[:-1] + "ies" if words.endswith("y") else words + "s"

        # only unambiguous decades: "'80s", "1990s", "the 80s" (plain "10s" stays ten seconds)
        text = re.sub(r"(?<![\w'])'(\d0)s\b", decade, text)
        text = re.sub(r"(?<![\w'])(\d{3}0)s\b", decade, text)
        return re.sub(r"(?<=\bthe )(\d0)s\b", decade, text, flags=re.I)
