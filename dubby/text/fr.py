"""French normalization rules."""

from __future__ import annotations

import re
from typing import Optional

from dubby.text.common import Money, Noun, Rules

_UNITS = ["zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix", "onze", "douze",
          "treize", "quatorze", "quinze", "seize"]
_TENS = {2: "vingt", 3: "trente", 4: "quarante", 5: "cinquante", 6: "soixante"}
_MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
_FEMININE = {"heure", "heures", "fois", "personne", "personnes", "minute", "minutes", "seconde", "secondes", "semaine",
             "semaines", "année", "années", "journée", "journées", "page", "pages", "femme", "femmes", "ville", "villes",
             "chose", "choses", "voiture", "voitures", "maison", "maisons", "question", "questions", "fille", "filles",
             "étoile", "étoiles", "place", "places", "tonne", "tonnes", "livre", "livres", "photo", "photos", "vidéo", "vidéos"}


def _below_100(n: int) -> str:
    if n <= 16:
        return _UNITS[n]
    if n < 20:
        return "dix-" + _UNITS[n - 10]
    if n < 70:
        tens, ones = divmod(n, 10)
        return _TENS[tens] + ("" if ones == 0 else " et un" if ones == 1 else "-" + _UNITS[ones])
    if n < 80:
        return "soixante et onze" if n == 71 else "soixante-" + _below_100(n - 60)
    return "quatre-vingts" if n == 80 else "quatre-vingt-" + _below_100(n - 80)


def _below_1000(n: int, final: bool) -> str:
    hundreds, rest = divmod(n, 100)
    parts = []
    if hundreds:
        parts.append("cent" if hundreds == 1 else f"{_UNITS[hundreds]} cent{'s' if rest == 0 and final else ''}")
    if rest:
        word = _below_100(rest)
        parts.append(word[:-1] if not final and word.endswith("vingts") else word)
    return " ".join(parts)


class FrenchRules(Rules):
    code = "fr"
    decimal = ","
    groups = " . "
    words = {
        "point": "virgule", "minus": "moins", "and": "et", "to": "à", "percent": "pour cent", "per_mille": "pour mille",
        "dot": "point", "slash": "slash", "underscore": "tiret bas", "dash": "tiret", "at": "arobase", "hashtag": "hashtag",
        "plus": "plus", "equals": "égale", "not_equal": "différent de", "less_equal": "inférieur ou égal à",
        "greater_equal": "supérieur ou égal à", "less": "inférieur à", "greater": "supérieur à", "times": "fois",
        "divided": "divisé par", "approx": "environ", "degrees": "degrés", "or": "ou",
        "thousand": "mille", "thousands": "mille", "million": "million", "millions": "millions",
        "billion": "milliard", "billions": "milliards",
    }
    months = _MONTHS
    abbreviations = {
        "M.": "monsieur", "MM.": "messieurs", "Mme": "madame", "Mmes": "mesdames", "Mlle": "mademoiselle",
        "Mlles": "mesdemoiselles", "Dr": "docteur", "Dr.": "docteur", "Pr": "professeur", "Pr.": "professeur",
        "Ste": "sainte", "etc.": "et cetera", "p. ex.": "par exemple", "c.-à-d.": "c'est-à-dire", "env.": "environ",
        "av. J.-C.": "avant Jésus-Christ", "apr. J.-C.": "après Jésus-Christ", "bd": "boulevard", "bd.": "boulevard",
        "av.": "avenue", "cf.": "confer", "tél.": "téléphone", "éd.": "édition", "janv.": "janvier", "févr.": "février",
        "avr.": "avril", "juil.": "juillet", "sept.": "septembre", "oct.": "octobre", "nov.": "novembre", "déc.": "décembre",
        "lun.": "lundi", "mer.": "mercredi", "jeu.": "jeudi", "ven.": "vendredi", "sam.": "samedi", "dim.": "dimanche",
        "SVP": "s'il vous plaît", "svp": "s'il vous plaît", "vs": "contre", "vs.": "contre",
    }
    abbreviation_patterns = [
        (r"\b[Nn][°º]\s?(?=\d)", "numéro "),
        (r"#\s?(?=\d)", "numéro "),
        (r"\bp\.\s?(?=\d)", "page "),
        (r"\bchap\.\s?(?=\d)", "chapitre "),
        (r"\bvol\.\s?(?=\d)", "volume "),
        (r"\bSt(?=[\s-][A-Z])", "saint"),
    ]
    currencies = {
        "EUR": Money(Noun("euro", "euros"), Noun("centime", "centimes")),
        "USD": Money(Noun("dollar", "dollars"), Noun("cent", "cents")),
        "GBP": Money(Noun("livre sterling", "livres sterling", feminine=True), Noun("penny", "pence")),
        "EGP": Money(Noun("livre égyptienne", "livres égyptiennes", feminine=True), Noun("piastre", "piastres", feminine=True)),
        "SAR": Money(Noun("riyal saoudien", "riyals saoudiens"), Noun("halala", "halalas")),
        "AED": Money(Noun("dirham", "dirhams"), Noun("fils", "fils")),
        "JPY": Money(Noun("yen", "yens")),
        "CNY": Money(Noun("yuan", "yuans")),
        "INR": Money(Noun("roupie", "roupies", feminine=True), Noun("paisa", "paisas")),
    }
    units = {
        "km": Noun("kilomètre", "kilomètres"), "m": Noun("mètre", "mètres"), "cm": Noun("centimètre", "centimètres"),
        "mm": Noun("millimètre", "millimètres"), "mi": Noun("mile", "miles"), "ft": Noun("pied", "pieds"),
        "kg": Noun("kilogramme", "kilogrammes"), "g": Noun("gramme", "grammes"), "mg": Noun("milligramme", "milligrammes"),
        "lb": Noun("livre", "livres", feminine=True), "lbs": Noun("livre", "livres", feminine=True),
        "oz": Noun("once", "onces", feminine=True), "l": Noun("litre", "litres"), "L": Noun("litre", "litres"),
        "ml": Noun("millilitre", "millilitres"), "mL": Noun("millilitre", "millilitres"),
        "km/h": Noun("kilomètre heure", "kilomètres heure"), "kmh": Noun("kilomètre heure", "kilomètres heure"),
        "kph": Noun("kilomètre heure", "kilomètres heure"), "mph": Noun("mile à l'heure", "miles à l'heure"),
        "m/s": Noun("mètre par seconde", "mètres par seconde"), "km²": Noun("kilomètre carré", "kilomètres carrés"),
        "km2": Noun("kilomètre carré", "kilomètres carrés"), "m²": Noun("mètre carré", "mètres carrés"),
        "m2": Noun("mètre carré", "mètres carrés"), "cm²": Noun("centimètre carré", "centimètres carrés"),
        "m³": Noun("mètre cube", "mètres cubes"), "m3": Noun("mètre cube", "mètres cubes"),
        "cm³": Noun("centimètre cube", "centimètres cubes"),
        "°C": Noun("degré Celsius", "degrés Celsius"), "ºC": Noun("degré Celsius", "degrés Celsius"),
        "°F": Noun("degré Fahrenheit", "degrés Fahrenheit"), "ºF": Noun("degré Fahrenheit", "degrés Fahrenheit"),
        "°": Noun("degré", "degrés"), "GB": Noun("gigaoctet", "gigaoctets"), "Go": Noun("gigaoctet", "gigaoctets"),
        "GiB": Noun("gibioctet", "gibioctets"), "MB": Noun("mégaoctet", "mégaoctets"), "Mo": Noun("mégaoctet", "mégaoctets"),
        "MiB": Noun("mébioctet", "mébioctets"), "KB": Noun("kilooctet", "kilooctets"), "kB": Noun("kilooctet", "kilooctets"),
        "TB": Noun("téraoctet", "téraoctets"), "Gbps": Noun("gigabit par seconde", "gigabits par seconde"),
        "Mbps": Noun("mégabit par seconde", "mégabits par seconde"), "kbps": Noun("kilobit par seconde", "kilobits par seconde"),
        "fps": Noun("image par seconde", "images par seconde", feminine=True), "Hz": Noun("hertz", "hertz"),
        "kHz": Noun("kilohertz", "kilohertz"), "MHz": Noun("mégahertz", "mégahertz"), "GHz": Noun("gigahertz", "gigahertz"),
        "W": Noun("watt", "watts"), "kW": Noun("kilowatt", "kilowatts"), "kWh": Noun("kilowattheure", "kilowattheures"),
        "V": Noun("volt", "volts"), "mAh": Noun("milliampère-heure", "milliampères-heures"),
        "h": Noun("heure", "heures", feminine=True), "hr": Noun("heure", "heures", feminine=True),
        "hrs": Noun("heure", "heures", feminine=True), "min": Noun("minute", "minutes", feminine=True),
        "mins": Noun("minute", "minutes", feminine=True), "s": Noun("seconde", "secondes", feminine=True),
        "sec": Noun("seconde", "secondes", feminine=True), "ms": Noun("milliseconde", "millisecondes", feminine=True),
        "px": Noun("pixel", "pixels"), "x": Noun("fois", "fois", feminine=True),
    }
    unit_aliases = {"Go": "Go", "Mo": "Mo"}
    fraction_words = {"½": "un demi", "⅓": "un tiers", "⅔": "deux tiers", "¼": "un quart", "¾": "trois quarts",
                      "⅕": "un cinquième", "⅛": "un huitième"}
    ordinal_pattern = r"(?<![\w.,])(\d+)(ère|re|er|ème|ième|eme|e|è)(?![\w])"
    pronounceable = frozenset({"OTAN", "ONU", "UNESCO", "UNICEF", "COVID", "FIFA", "UEFA", "OPEP", "IKEA", "SIDA", "OVNI",
                               "NASA", "SMIC", "PACS", "RAM", "OK", "CAF", "ZAD", "ENA"})

    def cardinal(self, n: int, feminine: bool = False) -> str:
        if n == 0:
            return "zéro"
        parts = []
        for value, one, many in ((10**12, "billion", "billions"), (10**9, "milliard", "milliards"), (10**6, "million", "millions")):
            if n >= value:
                count, n = divmod(n, value)
                parts.append(f"{self.cardinal(count)} {one if count == 1 else many}")
        thousands, n = divmod(n, 1000)
        if thousands:
            parts.append("mille" if thousands == 1 else f"{_below_1000(thousands, False)} mille")
        if n:
            parts.append(_below_1000(n, True))
        words = " ".join(parts)
        return words + "e" if feminine and words.endswith("un") else words

    def ordinal(self, n: int, feminine: bool = False) -> str:
        if n == 1:
            return "première" if feminine else "premier"
        words = self.cardinal(n)
        if words.endswith("cinq"):
            words += "u"
        elif words.endswith("neuf"):
            words = words[:-1] + "v"
        elif words.endswith(("e", "s")):
            words = words[:-1]
        return words + "ième"

    def decimal_words(self, integer: int, fraction: str) -> str:
        spoken = self.digit_words(fraction) if fraction.startswith("0") or len(fraction) > 2 else self.cardinal(int(fraction))
        return f"{self.cardinal(integer)} virgule {spoken}"

    def count(self, integer: int, fraction: str, noun: Noun) -> str:
        words = self.decimal_words(integer, fraction) if fraction else self.cardinal(integer, feminine=noun.feminine)
        form = noun.one if integer < 2 else noun.many
        if not fraction and integer >= 10**6 and integer % 10**6 == 0:
            return f"{words} {'d’' if form[0] in 'aeiouéèêhy' else 'de '}{form}".replace("’", "'")  # "un million d'euros"
        return f"{words} {form}"

    def cardinal_before(self, n: int, next_word: str) -> str:
        word = next_word.lower()
        feminine = word in _FEMININE or bool(re.search(r"(tion|sion|té|tés|ure|ures|ette|ettes|ence|ences|ance|ances|ée|ées)$", word))
        return self.cardinal(n, feminine=feminine)

    def fraction(self, a: int, b: int) -> Optional[str]:
        names = {2: ("demi", "demis"), 3: ("tiers", "tiers"), 4: ("quart", "quarts")}
        if b in names:
            return f"{self.cardinal(a)} {names[b][0] if a == 1 else names[b][1]}"
        return f"{self.cardinal(a)} {self.ordinal(b)}{'s' if a > 1 else ''}"

    def time(self, hour: int, minute: int, period: Optional[str]) -> str:
        if period == "p" and hour < 12:
            hour += 12
        elif period == "a" and hour == 12:
            hour = 0
        if hour == 0:
            head = "minuit"
        elif hour == 12:
            head = "midi"
        else:
            head = f"{self.cardinal(hour, feminine=True)} heure{'s' if hour > 1 else ''}"
        return head if minute == 0 else f"{head} {self.cardinal(minute)}"

    def date(self, day: int, month: int, year: Optional[int]) -> str:
        spoken = f"{'premier' if day == 1 else self.cardinal(day)} {self.months[month - 1]}"
        return f"{spoken} {self.cardinal(year)}" if year else spoken

    def before(self, text: str) -> str:
        # "14h30", "9 h 05", "18h" → spoken time
        def hours(m: re.Match) -> str:
            return f" {self.time(int(m.group(1)), int(m.group(2) or 0), None)} "

        text = re.sub(r"(?<![\w,.])([01]?\d|2[0-3])\s?h\s?([0-5]\d)?(?![\w])", hours, text)
        return re.sub(rf"(?<![\d.,])1(?:er)?(?=\s+(?:{'|'.join(_MONTHS)})\b)", "premier", text, flags=re.I)
