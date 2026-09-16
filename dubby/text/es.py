"""Spanish normalization rules."""

from __future__ import annotations

import re
from typing import Optional

from dubby.text.common import Money, Noun, Rules

_UNITS = ["cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez", "once", "doce",
          "trece", "catorce", "quince", "dieciséis", "diecisiete", "dieciocho", "diecinueve", "veinte", "veintiuno",
          "veintidós", "veintitrés", "veinticuatro", "veinticinco", "veintiséis", "veintisiete", "veintiocho", "veintinueve"]
_TENS = {3: "treinta", 4: "cuarenta", 5: "cincuenta", 6: "sesenta", 7: "setenta", 8: "ochenta", 9: "noventa"}
_HUNDREDS = ["", "ciento", "doscientos", "trescientos", "cuatrocientos", "quinientos", "seiscientos", "setecientos",
             "ochocientos", "novecientos"]
_ORDINALS = {1: "primero", 2: "segundo", 3: "tercero", 4: "cuarto", 5: "quinto", 6: "sexto", 7: "séptimo", 8: "octavo",
             9: "noveno", 10: "décimo", 11: "undécimo", 12: "duodécimo", 13: "decimotercero", 14: "decimocuarto",
             15: "decimoquinto", 16: "decimosexto", 17: "decimoséptimo", 18: "decimoctavo", 19: "decimonoveno",
             20: "vigésimo", 30: "trigésimo", 40: "cuadragésimo", 50: "quincuagésimo", 100: "centésimo"}
_FUNCTION_WORDS = {"y", "e", "o", "u", "de", "del", "a", "al", "en", "por", "para", "con", "sin", "que", "es", "son", "fue",
                   "era", "más", "menos", "entre", "hasta", "desde", "sobre", "como", "mil", "millones", "millón"}
_FEMININE = {"vez", "veces", "mujer", "mujeres", "noche", "noches", "clase", "clases", "parte", "partes", "gente", "calle",
             "calles", "llave", "llaves", "imagen", "imágenes", "razón", "razones", "flor", "flores", "luz", "luces", "voz",
             "voces", "nariz", "red", "redes", "piel", "sal", "miel", "leche", "carne", "fuente", "fuentes", "muerte", "suerte"}
_MASCULINE_A = {"día", "días", "mapa", "mapas", "problema", "problemas", "tema", "temas", "sistema", "sistemas", "programa",
                "programas", "idioma", "idiomas", "planeta", "planetas", "clima", "climas", "drama", "dramas", "poema",
                "poemas", "esquema", "esquemas", "dilema", "dilemas", "fantasma", "fantasmas", "cometa", "sofá", "sofás",
                "papá", "papás", "pijama", "pijamas", "atletas", "turistas", "artistas", "dentistas", "periodistas"}
_MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _below_1000(n: int, apocope: bool, feminine: bool) -> str:
    if n == 100:
        return "cien"
    hundreds, rest = divmod(n, 100)
    parts = []
    if hundreds:
        word = _HUNDREDS[hundreds]
        parts.append(word.replace("ientos", "ientas") if feminine and hundreds > 1 else word)
    if rest:
        if rest < 30:
            parts.append(_UNITS[rest])
        else:
            tens, ones = divmod(rest, 10)
            parts.append(_TENS[tens] + (f" y {_UNITS[ones]}" if ones else ""))
    words = " ".join(parts)
    if words.endswith("uno"):
        if feminine:
            words = words[:-3] + "una"
        elif apocope:
            words = words[:-3] + ("ún" if words.endswith("veintiuno") else "un")
    return words


class SpanishRules(Rules):
    code = "es"
    decimal = ","
    groups = ".  "
    words = {
        "point": "coma", "minus": "menos", "and": "y", "money_and": "con", "to": "a", "percent": "por ciento",
        "per_mille": "por mil", "dot": "punto", "slash": "barra", "underscore": "guion bajo", "dash": "guion",
        "at": "arroba", "hashtag": "hashtag", "plus": "más", "equals": "igual a", "not_equal": "distinto de",
        "less_equal": "menor o igual que", "greater_equal": "mayor o igual que", "less": "menor que",
        "greater": "mayor que", "times": "por", "divided": "entre", "approx": "aproximadamente", "degrees": "grados", "or": "o",
        "thousand": "mil", "thousands": "mil", "million": "millón", "millions": "millones",
        "billion": "mil millones", "billions": "mil millones",
    }
    months = _MONTHS
    abbreviations = {
        "Sr.": "señor", "Sra.": "señora", "Srta.": "señorita", "Sres.": "señores", "Dr.": "doctor", "Dra.": "doctora",
        "Lic.": "licenciado", "Lda.": "licenciada", "Ing.": "ingeniero", "Arq.": "arquitecto", "Prof.": "profesor",
        "Profa.": "profesora", "Ud.": "usted", "Uds.": "ustedes", "Vd.": "usted", "Dña.": "doña", "Sto.": "santo",
        "Sta.": "santa", "etc.": "etcétera", "p. ej.": "por ejemplo", "p.ej.": "por ejemplo", "aprox.": "aproximadamente",
        "tel.": "teléfono", "Av.": "avenida", "Avda.": "avenida", "c/": "calle", "C/": "calle", "dcha.": "derecha",
        "izq.": "izquierda", "EE. UU.": "Estados Unidos", "EE.UU.": "Estados Unidos", "S.A.": "sociedad anónima",
        "a. C.": "antes de Cristo", "d. C.": "después de Cristo", "a.C.": "antes de Cristo", "d.C.": "después de Cristo",
        "ene.": "enero", "feb.": "febrero", "abr.": "abril", "jun.": "junio", "jul.": "julio", "ago.": "agosto",
        "sept.": "septiembre", "oct.": "octubre", "nov.": "noviembre", "dic.": "diciembre", "máx.": "máximo",
        "mín.": "mínimo", "vs.": "contra",
    }
    abbreviation_patterns = [
        (r"\b(?:núm\.|n\.º|nº|No\.)\s?(?=\d)", "número "),
        (r"#\s?(?=\d)", "número "),
        (r"\bpágs?\.\s?(?=\d)", "página "),
        (r"\bcap\.\s?(?=\d)", "capítulo "),
    ]
    currencies = {
        "USD": Money(Noun("dólar", "dólares"), Noun("centavo", "centavos")),
        "EUR": Money(Noun("euro", "euros"), Noun("céntimo", "céntimos")),
        "GBP": Money(Noun("libra", "libras", feminine=True), Noun("penique", "peniques")),
        "EGP": Money(Noun("libra egipcia", "libras egipcias", feminine=True), Noun("piastra", "piastras", feminine=True)),
        "SAR": Money(Noun("rial saudí", "riales saudíes"), Noun("halala", "halalas", feminine=True)),
        "AED": Money(Noun("dírham", "dírhams"), Noun("fils", "fils")),
        "JPY": Money(Noun("yen", "yenes")),
        "CNY": Money(Noun("yuan", "yuanes")),
        "INR": Money(Noun("rupia", "rupias", feminine=True), Noun("paisa", "paisas", feminine=True)),
    }
    units = {
        "km": Noun("kilómetro", "kilómetros"), "m": Noun("metro", "metros"), "cm": Noun("centímetro", "centímetros"),
        "mm": Noun("milímetro", "milímetros"), "mi": Noun("milla", "millas", feminine=True), "ft": Noun("pie", "pies"),
        "kg": Noun("kilogramo", "kilogramos"), "g": Noun("gramo", "gramos"), "mg": Noun("miligramo", "miligramos"),
        "lb": Noun("libra", "libras", feminine=True), "lbs": Noun("libra", "libras", feminine=True),
        "oz": Noun("onza", "onzas", feminine=True), "l": Noun("litro", "litros"), "L": Noun("litro", "litros"),
        "ml": Noun("mililitro", "mililitros"), "mL": Noun("mililitro", "mililitros"),
        "km/h": Noun("kilómetro por hora", "kilómetros por hora"), "kmh": Noun("kilómetro por hora", "kilómetros por hora"),
        "kph": Noun("kilómetro por hora", "kilómetros por hora"), "mph": Noun("milla por hora", "millas por hora", feminine=True),
        "m/s": Noun("metro por segundo", "metros por segundo"), "km²": Noun("kilómetro cuadrado", "kilómetros cuadrados"),
        "km2": Noun("kilómetro cuadrado", "kilómetros cuadrados"), "m²": Noun("metro cuadrado", "metros cuadrados"),
        "m2": Noun("metro cuadrado", "metros cuadrados"), "cm²": Noun("centímetro cuadrado", "centímetros cuadrados"),
        "m³": Noun("metro cúbico", "metros cúbicos"), "m3": Noun("metro cúbico", "metros cúbicos"),
        "cm³": Noun("centímetro cúbico", "centímetros cúbicos"),
        "°C": Noun("grado Celsius", "grados Celsius"), "ºC": Noun("grado Celsius", "grados Celsius"),
        "°F": Noun("grado Fahrenheit", "grados Fahrenheit"), "ºF": Noun("grado Fahrenheit", "grados Fahrenheit"),
        "°": Noun("grado", "grados"), "GB": Noun("gigabyte", "gigabytes"), "GiB": Noun("gibibyte", "gibibytes"),
        "MB": Noun("megabyte", "megabytes"), "MiB": Noun("mebibyte", "mebibytes"), "KB": Noun("kilobyte", "kilobytes"),
        "kB": Noun("kilobyte", "kilobytes"), "TB": Noun("terabyte", "terabytes"),
        "Gbps": Noun("gigabit por segundo", "gigabits por segundo"), "Mbps": Noun("megabit por segundo", "megabits por segundo"),
        "kbps": Noun("kilobit por segundo", "kilobits por segundo"), "fps": Noun("fotograma por segundo", "fotogramas por segundo"),
        "Hz": Noun("hercio", "hercios"), "kHz": Noun("kilohercio", "kilohercios"), "MHz": Noun("megahercio", "megahercios"),
        "GHz": Noun("gigahercio", "gigahercios"), "W": Noun("vatio", "vatios"), "kW": Noun("kilovatio", "kilovatios"),
        "kWh": Noun("kilovatio hora", "kilovatios hora"), "V": Noun("voltio", "voltios"),
        "mAh": Noun("miliamperio hora", "miliamperios hora"), "h": Noun("hora", "horas", feminine=True),
        "hr": Noun("hora", "horas", feminine=True), "hrs": Noun("hora", "horas", feminine=True),
        "min": Noun("minuto", "minutos"), "mins": Noun("minuto", "minutos"), "s": Noun("segundo", "segundos"),
        "sec": Noun("segundo", "segundos"), "secs": Noun("segundo", "segundos"), "ms": Noun("milisegundo", "milisegundos"),
        "px": Noun("píxel", "píxeles"), "x": Noun("vez", "veces", feminine=True),
    }
    fraction_words = {"½": "un medio", "⅓": "un tercio", "⅔": "dos tercios", "¼": "un cuarto", "¾": "tres cuartos",
                      "⅕": "un quinto", "⅛": "un octavo"}
    ordinal_pattern = r"(?<![\w.,])(\d+)\.?(º|ª|er)(?![\w])"
    pronounceable = frozenset({"OTAN", "ONU", "UNESCO", "UNICEF", "COVID", "FIFA", "UEFA", "OPEP", "IKEA", "SIDA",
                               "OVNI", "RAM", "PIN", "SIM", "NASA", "OK"})

    def cardinal(self, n: int, apocope: bool = False, feminine: bool = False) -> str:
        if n == 0:
            return "cero"
        parts = []
        trillions, n = divmod(n, 10**12)
        if trillions:
            parts.append("un billón" if trillions == 1 else f"{self.cardinal(trillions, apocope=True)} billones")
        millions, n = divmod(n, 10**6)
        if millions:
            parts.append("un millón" if millions == 1 else f"{self.cardinal(millions, apocope=True)} millones")
        thousands, n = divmod(n, 1000)
        if thousands:
            parts.append("mil" if thousands == 1 else f"{_below_1000(thousands, True, feminine)} mil")
        if n:
            parts.append(_below_1000(n, apocope, feminine))
        return " ".join(parts)

    def ordinal(self, n: int, feminine: bool = False) -> str:
        if n in _ORDINALS:
            word = _ORDINALS[n]
        elif n < 100 and n // 10 * 10 in _ORDINALS:
            word = f"{_ORDINALS[n // 10 * 10]} {_ORDINALS[n % 10]}"
        else:
            return self.cardinal(n, feminine=feminine)
        return re.sub(r"o\b", "a", word) if feminine else word

    def decimal_words(self, integer: int, fraction: str) -> str:
        spoken = self.digit_words(fraction) if fraction.startswith("0") or len(fraction) > 2 else self.cardinal(int(fraction))
        return f"{self.cardinal(integer)} coma {spoken}"

    def count(self, integer: int, fraction: str, noun: Noun) -> str:
        if fraction:
            words = self.decimal_words(integer, fraction)
        else:
            words = self.cardinal(integer, apocope=not noun.feminine, feminine=noun.feminine)
        # "cinco millones de dólares"
        of = " de" if not fraction and integer >= 10**6 and integer % 10**6 == 0 else ""
        return f"{words}{of} {noun.one if integer == 1 and not fraction else noun.many}"

    def cardinal_before(self, n: int, next_word: str) -> str:
        word = next_word.lower()
        if not word or word in _FUNCTION_WORDS:
            return self.cardinal(n)
        feminine = word in _FEMININE or bool(re.search(r"(ción|sión|dad|tad|ciones|siones|dades|tades)$", word)) or (
            word.endswith(("a", "as")) and word not in _MASCULINE_A
        )
        return self.cardinal(n, apocope=not feminine, feminine=feminine)

    def scale(self, token, integer, fraction, exponent, normalizer):
        if integer == 1 and not fraction:
            return {3: "mil", 6: "un millón", 9: "mil millones"}[exponent]
        return super().scale(token, integer, fraction, exponent, normalizer)

    def fraction(self, a: int, b: int) -> Optional[str]:
        names = {2: "medio", 3: "tercio", 4: "cuarto", 5: "quinto", 6: "sexto", 7: "séptimo", 8: "octavo", 9: "noveno", 10: "décimo"}
        return f"{self.cardinal(a, apocope=True)} {names[b]}{'s' if a > 1 else ''}"

    def time(self, hour: int, minute: int, period: Optional[str]) -> str:
        tail = ""
        if period:
            tail = " de la mañana" if period == "a" else (" de la noche" if 8 <= hour <= 11 else " de la tarde")
        elif hour == 0:
            hour, tail = 12, " de la noche"
        elif hour > 12:
            tail = " de la tarde" if hour < 20 else " de la noche"
            hour -= 12
        if minute == 45:
            hour, phrase = hour % 12 + 1, " menos cuarto"
        elif minute == 0:
            phrase = "" if tail else " en punto"
        else:
            phrase = {15: " y cuarto", 30: " y media"}.get(minute, f" y {self.cardinal(minute)}")
        head = "la una" if hour == 1 else f"las {self.cardinal(hour)}"
        return f"{head}{phrase}{tail}"

    def date(self, day: int, month: int, year: Optional[int]) -> str:
        spoken = f"{'primero' if day == 1 else self.cardinal(day)} de {self.months[month - 1]}"
        return f"{spoken} de {self.cardinal(year)}" if year else spoken

    def before(self, text: str) -> str:
        months = "|".join(_MONTHS)
        text = re.sub(rf"(?<![\d.,])1(?=\s+de\s+(?:{months})\b)", "primero", text, flags=re.I)
        # the spoken time brings its own article: "a las 15:45" → "a las cuatro menos cuarto"
        text = re.sub(r"\b(las?)\s+(?=\d{1,2}:\d{2})", "", text, flags=re.I)
        # "1er" / "3er" are apocopated ordinals: "primer", "tercer"
        return re.sub(r"(?<![\w.,])([13])\.?er\b", lambda m: "primer" if m.group(1) == "1" else "tercer", text)
