"""Italian normalization rules."""

from __future__ import annotations

import re
from typing import Optional

from dubby.text.common import Money, Noun, Rules

_UNITS = ["zero", "uno", "due", "tre", "quattro", "cinque", "sei", "sette", "otto", "nove", "dieci", "undici", "dodici",
          "tredici", "quattordici", "quindici", "sedici", "diciassette", "diciotto", "diciannove"]
_TENS = {2: "venti", 3: "trenta", 4: "quaranta", 5: "cinquanta", 6: "sessanta", 7: "settanta", 8: "ottanta", 9: "novanta"}
_ORDINALS = ["", "primo", "secondo", "terzo", "quarto", "quinto", "sesto", "settimo", "ottavo", "nono", "decimo"]
_MONTHS = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]


def _below_100(n: int) -> str:
    if n < 20:
        return _UNITS[n]
    tens, ones = divmod(n, 10)
    word = _TENS[tens]
    if ones == 0:
        return word
    if ones in (1, 8):  # ventuno, ventotto
        word = word[:-1]
    return word + _UNITS[ones]


def _below_1000(n: int) -> str:
    hundreds, rest = divmod(n, 100)
    out = ""
    if hundreds:
        out = "cento" if hundreds == 1 else _UNITS[hundreds] + "cento"
    if rest:
        if hundreds and rest // 10 == 8:  # centottanta
            out = out[:-1]
        out += _below_100(rest)
    return out


class ItalianRules(Rules):
    code = "it"
    decimal = ","
    groups = ".  "
    words = {
        "point": "virgola", "minus": "meno", "and": "e", "to": "a", "percent": "per cento", "per_mille": "per mille",
        "dot": "punto", "slash": "slash", "underscore": "trattino basso", "dash": "trattino", "at": "chiocciola",
        "hashtag": "hashtag", "plus": "più", "equals": "uguale a", "not_equal": "diverso da",
        "less_equal": "minore o uguale a", "greater_equal": "maggiore o uguale a", "less": "minore di",
        "greater": "maggiore di", "times": "per", "divided": "diviso", "approx": "circa", "degrees": "gradi", "or": "o",
        "thousand": "mille", "thousands": "mila", "million": "milione", "millions": "milioni",
        "billion": "miliardo", "billions": "miliardi",
    }
    months = _MONTHS
    abbreviations = {
        "Sig.": "signor", "Sig.ra": "signora", "Sig.na": "signorina", "Sigg.": "signori", "Dott.": "dottor",
        "Dott.ssa": "dottoressa", "Prof.": "professor", "Prof.ssa": "professoressa", "Ing.": "ingegner",
        "Avv.": "avvocato", "Arch.": "architetto", "Geom.": "geometra", "On.": "onorevole", "ecc.": "eccetera",
        "p.es.": "per esempio", "p. es.": "per esempio", "es.": "esempio", "tel.": "telefono", "S.p.A.": "società per azioni",
        "S.r.l.": "società a responsabilità limitata", "a.C.": "avanti Cristo", "d.C.": "dopo Cristo", "ca.": "circa",
        "c.a": "circa", "gen.": "gennaio", "feb.": "febbraio", "apr.": "aprile", "giu.": "giugno", "lug.": "luglio",
        "ago.": "agosto", "set.": "settembre", "ott.": "ottobre", "nov.": "novembre", "dic.": "dicembre",
        "P.zza": "piazza", "V.le": "viale", "C.so": "corso", "vs": "contro", "vs.": "contro",
    }
    abbreviation_patterns = [
        (r"\bn\.\s?(?=\d)", "numero "),
        (r"\b[Nn][°º]\s?(?=\d)", "numero "),
        (r"#\s?(?=\d)", "numero "),
        (r"\bpagg?\.\s?(?=\d)", "pagina "),
        (r"\bcap\.\s?(?=\d)", "capitolo "),
    ]
    currencies = {
        "EUR": Money(Noun("euro", "euro"), Noun("centesimo", "centesimi")),
        "USD": Money(Noun("dollaro", "dollari"), Noun("centesimo", "centesimi")),
        "GBP": Money(Noun("sterlina", "sterline", feminine=True), Noun("penny", "pence")),
        "EGP": Money(Noun("sterlina egiziana", "sterline egiziane", feminine=True), Noun("piastra", "piastre", feminine=True)),
        "SAR": Money(Noun("riyal", "riyal")),
        "AED": Money(Noun("dirham", "dirham")),
        "JPY": Money(Noun("yen", "yen")),
        "CNY": Money(Noun("yuan", "yuan")),
        "INR": Money(Noun("rupia", "rupie", feminine=True), Noun("paisa", "paise", feminine=True)),
    }
    units = {
        "km": Noun("chilometro", "chilometri"), "m": Noun("metro", "metri"), "cm": Noun("centimetro", "centimetri"),
        "mm": Noun("millimetro", "millimetri"), "mi": Noun("miglio", "miglia"), "ft": Noun("piede", "piedi"),
        "kg": Noun("chilogrammo", "chilogrammi"), "g": Noun("grammo", "grammi"), "mg": Noun("milligrammo", "milligrammi"),
        "lb": Noun("libbra", "libbre", feminine=True), "lbs": Noun("libbra", "libbre", feminine=True),
        "oz": Noun("oncia", "once", feminine=True), "l": Noun("litro", "litri"), "L": Noun("litro", "litri"),
        "ml": Noun("millilitro", "millilitri"), "mL": Noun("millilitro", "millilitri"),
        "km/h": Noun("chilometro orario", "chilometri orari"), "kmh": Noun("chilometro orario", "chilometri orari"),
        "kph": Noun("chilometro orario", "chilometri orari"), "mph": Noun("miglio orario", "miglia orarie"),
        "m/s": Noun("metro al secondo", "metri al secondo"), "km²": Noun("chilometro quadrato", "chilometri quadrati"),
        "km2": Noun("chilometro quadrato", "chilometri quadrati"), "m²": Noun("metro quadrato", "metri quadrati"),
        "m2": Noun("metro quadrato", "metri quadrati"), "cm²": Noun("centimetro quadrato", "centimetri quadrati"),
        "m³": Noun("metro cubo", "metri cubi"), "m3": Noun("metro cubo", "metri cubi"), "cm³": Noun("centimetro cubo", "centimetri cubi"),
        "°C": Noun("grado Celsius", "gradi Celsius"), "ºC": Noun("grado Celsius", "gradi Celsius"),
        "°F": Noun("grado Fahrenheit", "gradi Fahrenheit"), "ºF": Noun("grado Fahrenheit", "gradi Fahrenheit"),
        "°": Noun("grado", "gradi"), "GB": Noun("gigabyte", "gigabyte"), "GiB": Noun("gibibyte", "gibibyte"),
        "MB": Noun("megabyte", "megabyte"), "MiB": Noun("mebibyte", "mebibyte"), "KB": Noun("kilobyte", "kilobyte"),
        "kB": Noun("kilobyte", "kilobyte"), "TB": Noun("terabyte", "terabyte"), "Gbps": Noun("gigabit al secondo", "gigabit al secondo"),
        "Mbps": Noun("megabit al secondo", "megabit al secondo"), "kbps": Noun("kilobit al secondo", "kilobit al secondo"),
        "fps": Noun("fotogramma al secondo", "fotogrammi al secondo"), "Hz": Noun("hertz", "hertz"),
        "kHz": Noun("kilohertz", "kilohertz"), "MHz": Noun("megahertz", "megahertz"), "GHz": Noun("gigahertz", "gigahertz"),
        "W": Noun("watt", "watt"), "kW": Noun("kilowatt", "kilowatt"), "kWh": Noun("kilowattora", "kilowattora"),
        "V": Noun("volt", "volt"), "mAh": Noun("milliampere ora", "milliampere ora"),
        "h": Noun("ora", "ore", feminine=True), "hr": Noun("ora", "ore", feminine=True), "hrs": Noun("ora", "ore", feminine=True),
        "min": Noun("minuto", "minuti"), "mins": Noun("minuto", "minuti"), "s": Noun("secondo", "secondi"),
        "sec": Noun("secondo", "secondi"), "secs": Noun("secondo", "secondi"), "ms": Noun("millisecondo", "millisecondi"),
        "px": Noun("pixel", "pixel"), "x": Noun("volta", "volte", feminine=True),
    }
    fraction_words = {"½": "un mezzo", "⅓": "un terzo", "⅔": "due terzi", "¼": "un quarto", "¾": "tre quarti",
                      "⅕": "un quinto", "⅛": "un ottavo"}
    ordinal_pattern = r"(?<![\w.,])(\d+)([ºª])(?![\w])"
    pronounceable = frozenset({"NATO", "ONU", "UNESCO", "UNICEF", "COVID", "FIFA", "UEFA", "OPEC", "IKEA", "AIDS", "RAI",
                               "IVA", "ANSA", "FIAT", "NASA", "OK", "INPS"})

    def cardinal(self, n: int, feminine: bool = False) -> str:
        if n == 0:
            return "zero"
        parts = []
        for value, one, many in ((10**9, "un miliardo", "miliardi"), (10**6, "un milione", "milioni")):
            if n >= value:
                count, n = divmod(n, value)
                parts.append(one if count == 1 else f"{self.cardinal(count)} {many}")
        thousands, n = divmod(n, 1000)
        words = ""
        if thousands:
            words = "mille" if thousands == 1 else _below_1000(thousands) + "mila"
        if n:
            words += _below_1000(n)
        if words:
            words = re.sub(r"(?<=\w)tre$", "tré", words)  # ventitré, centotré, milletré
            parts.append(words)
        result = " ".join(parts)
        if result == "uno" and feminine:
            return "una"
        return result

    def ordinal(self, n: int, feminine: bool = False) -> str:
        if n <= 10:
            word = _ORDINALS[n] if n else "zero"
        else:
            words = self.cardinal(n)
            if words.endswith("tré"):
                word = words[:-1] + "eesimo"
            elif words.endswith("sei"):
                word = words + "esimo"
            else:
                word = words[:-1] + "esimo"
        return word[:-1] + "a" if feminine and word.endswith("o") else word

    def decimal_words(self, integer: int, fraction: str) -> str:
        spoken = self.digit_words(fraction) if fraction.startswith("0") or len(fraction) > 2 else self.cardinal(int(fraction))
        return f"{self.cardinal(integer)} virgola {spoken}"

    def count(self, integer: int, fraction: str, noun: Noun) -> str:
        if fraction:
            words = self.decimal_words(integer, fraction)
        elif integer == 1:
            if noun.feminine:
                return f"un'{noun.one}" if noun.one[0] in "aeiou" else f"una {noun.one}"  # "un'ora"
            words = "un"
        else:
            words = self.cardinal(integer)
        of = " di" if not fraction and integer >= 10**6 and integer % 10**6 == 0 else ""
        return f"{words}{of} {noun.one if integer == 1 and not fraction else noun.many}"

    def cardinal_before(self, n: int, next_word: str) -> str:
        if n == 1 and next_word:
            return "una" if next_word.lower().endswith("a") else "un"
        return self.cardinal(n)

    def scale(self, token, integer, fraction, exponent, normalizer):
        if not fraction and exponent == 3:
            return self.cardinal(integer * 1000)  # "5k" → "cinquemila"
        return super().scale(token, integer, fraction, exponent, normalizer)

    def fraction(self, a: int, b: int) -> Optional[str]:
        names = {2: ("mezzo", "mezzi"), 3: ("terzo", "terzi"), 4: ("quarto", "quarti")}
        if b in names:
            return f"{'un' if a == 1 else self.cardinal(a)} {names[b][0] if a == 1 else names[b][1]}"
        return f"{'un' if a == 1 else self.cardinal(a)} {self.ordinal(b) if a == 1 else self.ordinal(b)[:-1] + 'i'}"

    def time(self, hour: int, minute: int, period: Optional[str]) -> str:
        if period == "p" and hour < 12:
            hour += 12
        elif period == "a" and hour == 12:
            hour = 0
        if minute == 45:
            hour, tail = (hour + 1) % 24, " meno un quarto"
        else:
            tail = {0: "", 15: " e un quarto", 30: " e mezza"}.get(minute, f" e {self.cardinal(minute)}")
        if hour == 0:
            head = "mezzanotte"
        elif hour == 12:
            head = "mezzogiorno"
        elif hour in (1, 13):
            head = "l'una"
        else:
            head = f"le {self.cardinal(hour)}"
        return head + tail

    def date(self, day: int, month: int, year: Optional[int]) -> str:
        spoken = f"{'primo' if day == 1 else self.cardinal(day)} {self.months[month - 1]}"
        return f"{spoken} {self.cardinal(year)}" if year else spoken

    def before(self, text: str) -> str:
        # "1 ora" → "un'ora": feminine noun starting with a vowel (ends in -a)
        text = re.sub(r"(?<![\d.,])1\s+(?=[aeiouàèéìòù]\w*a\b)", "un'", text)
        # "1° maggio", "3° posto": ordinal before a word (degrees are followed by C/F or nothing)
        text = re.sub(r"(?<![\w.,])(\d{1,2})°(?=\s+[a-zà-ù])", lambda m: self.ordinal(int(m.group(1))), text)

        # merge the clock's article with a preposition: "alle 15:30" → "alle quindici e mezza", "all'1:00" → "all'una"
        def clock(m: re.Match) -> str:
            prep = (m.group(1) or "").lower()
            spoken = self.time(int(m.group(2)), int(m.group(3)), None)
            base = re.sub(r"(le|l')$", "", prep)
            if not prep:
                return spoken
            if spoken.startswith(("mezzanotte", "mezzogiorno")):
                return f"{ {'al': 'a', 'dal': 'da', 'del': 'di'}.get(base, base) } {spoken}".strip()
            return base + spoken

        return re.sub(r"\b(alle|dalle|delle|le|all'|dall'|l')?\s*(?<![\d:])(\d{1,2}):([0-5]\d)(?![\d:])", clock, text, flags=re.I)
