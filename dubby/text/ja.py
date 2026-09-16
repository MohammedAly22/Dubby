"""Japanese normalization rules (kanji numerals, 万/億 grouping)."""

from __future__ import annotations

from typing import Optional

from dubby.text.common import Money, Noun, Rules

_D = "〇一二三四五六七八九"


def _section(n: int) -> str:
    out = ""
    for value, unit in ((1000, "千"), (100, "百"), (10, "十")):
        digit, n = divmod(n, value)
        if digit:
            out += ("" if digit == 1 else _D[digit]) + unit
    if n:
        out += _D[n]
    return out


def _n(word: str) -> Noun:
    return Noun(word, word)


# units spoken before the number: 時速60キロ, 華氏70度
_PREFIXED = {"km/h": ("時速", "キロ"), "kmh": ("時速", "キロ"), "kph": ("時速", "キロ"), "mph": ("時速", "マイル"),
             "m/s": ("秒速", "メートル"), "°F": ("華氏", "度"), "ºF": ("華氏", "度")}


class JapaneseRules(Rules):
    code = "ja"
    latin_script = False
    cjk = True
    words = {
        "point": "点", "minus": "マイナス", "and": "と", "money_and": "", "to": "から", "percent": "パーセント",
        "per_mille": "パーミル", "dot": "ドット", "slash": "スラッシュ", "underscore": "アンダーバー", "dash": "ハイフン",
        "at": "アット", "hashtag": "ハッシュタグ", "plus": "プラス", "equals": "イコール", "not_equal": "ノットイコール",
        "less_equal": "以下", "greater_equal": "以上", "less": "未満", "greater": "より大きい", "times": "かける",
        "divided": "割る", "approx": "約", "degrees": "度", "or": "または",
    }
    currency_aliases = {"円": "JPY", "ドル": "USD", "ユーロ": "EUR", "元": "CNY"}
    currencies = {
        "JPY": Money(_n("円")), "USD": Money(_n("ドル"), _n("セント")), "EUR": Money(_n("ユーロ"), _n("セント")),
        "GBP": Money(_n("ポンド"), _n("ペンス")), "CNY": Money(_n("元")), "INR": Money(_n("ルピー")),
        "EGP": Money(_n("エジプトポンド")), "SAR": Money(_n("リヤル")), "AED": Money(_n("ディルハム")),
    }
    units = {
        "km": _n("キロメートル"), "m": _n("メートル"), "cm": _n("センチメートル"), "mm": _n("ミリメートル"), "mi": _n("マイル"),
        "ft": _n("フィート"), "kg": _n("キログラム"), "g": _n("グラム"), "mg": _n("ミリグラム"), "lb": _n("ポンド"),
        "lbs": _n("ポンド"), "oz": _n("オンス"), "l": _n("リットル"), "L": _n("リットル"), "ml": _n("ミリリットル"),
        "mL": _n("ミリリットル"), "km/h": _n("km/h"), "kmh": _n("kmh"), "kph": _n("kph"), "mph": _n("mph"), "m/s": _n("m/s"),
        "km²": _n("平方キロメートル"), "km2": _n("平方キロメートル"), "m²": _n("平方メートル"), "m2": _n("平方メートル"),
        "cm²": _n("平方センチメートル"), "m³": _n("立方メートル"), "m3": _n("立方メートル"), "°C": _n("度"), "ºC": _n("度"),
        "°F": _n("°F"), "ºF": _n("ºF"), "°": _n("度"), "GB": _n("ギガバイト"), "GiB": _n("ギビバイト"),
        "MB": _n("メガバイト"), "MiB": _n("メビバイト"), "KB": _n("キロバイト"), "kB": _n("キロバイト"), "TB": _n("テラバイト"),
        "Gbps": _n("ギガビット毎秒"), "Mbps": _n("メガビット毎秒"), "kbps": _n("キロビット毎秒"), "fps": _n("フレーム毎秒"),
        "Hz": _n("ヘルツ"), "kHz": _n("キロヘルツ"), "MHz": _n("メガヘルツ"), "GHz": _n("ギガヘルツ"), "W": _n("ワット"),
        "kW": _n("キロワット"), "kWh": _n("キロワット時"), "V": _n("ボルト"), "mAh": _n("ミリアンペアアワー"),
        "h": _n("時間"), "hr": _n("時間"), "hrs": _n("時間"), "min": _n("分"), "mins": _n("分"), "s": _n("秒"),
        "sec": _n("秒"), "secs": _n("秒"), "ms": _n("ミリ秒"), "px": _n("ピクセル"), "x": _n("倍"),
    }
    unit_aliases = {"キロ": "km", "℃": "°C", "℉": "°F"}
    fraction_words = {"½": "二分の一", "⅓": "三分の一", "⅔": "三分の二", "¼": "四分の一", "¾": "四分の三", "⅕": "五分の一", "⅛": "八分の一"}

    def cardinal(self, n: int) -> str:
        if n == 0:
            return "ゼロ"
        out, index, sections = "", 0, []
        while n > 0:
            n, section = divmod(n, 10000)
            sections.append(section)
        units = ["", "万", "億", "兆"]
        for index in range(len(sections) - 1, -1, -1):
            if sections[index]:
                out += _section(sections[index]) + units[index]
        return out

    def ordinal(self, n: int, feminine: bool = False) -> str:
        return "第" + self.cardinal(n)

    def decimal_words(self, integer: int, fraction: str) -> str:
        return f"{self.cardinal(integer)}点{''.join(_D[int(d)] for d in fraction)}"

    def is_year(self, value: int, before: str, after: str) -> bool:
        return after.lstrip().startswith("年")

    def before(self, text: str) -> str:
        import re

        # "時速60km/h" already says 時速: read "時速六十キロ" instead of doubling it
        def speed(m: re.Match) -> str:
            value = m.group(2)
            words = self.decimal_words(*[int(value.split(".")[0]), value.split(".")[1]]) if "." in value else self.cardinal(int(value))
            return f"{m.group(1)}{words}{'キロ' if m.group(3) != 'mph' else 'マイル'}"

        return re.sub(r"(時速|秒速)\s?(\d+(?:\.\d+)?)\s?(km/h|kmh|kph|キロ|mph)", speed, text)

    def count(self, integer: int, fraction: str, noun: Noun) -> str:
        words = self.number(integer, fraction.rstrip("0"))
        if noun.one in _PREFIXED:
            prefix, suffix = _PREFIXED[noun.one]
            return f"{prefix}{words}{suffix}"
        return words + noun.one

    def percent(self, words: str) -> str:
        return words + "パーセント"

    def negative(self, words: str) -> str:
        return "マイナス" + words

    def range(self, a: str, b: str) -> str:
        return f"{a}から{b}"

    def fraction(self, a: int, b: int) -> Optional[str]:
        return f"{self.cardinal(b)}分の{self.cardinal(a)}"

    def time(self, hour: int, minute: int, period: Optional[str]) -> str:
        prefix = ""
        if period:
            prefix = "午前" if period == "a" else "午後"
        head = f"{self.cardinal(hour)}時"
        if minute == 0:
            return prefix + head
        if minute == 30:
            return prefix + head + "半"
        return f"{prefix}{head}{self.cardinal(minute)}分"

    def date(self, day: int, month: int, year: Optional[int]) -> str:
        spoken = f"{self.cardinal(month)}月{self.cardinal(day)}日"
        return f"{self.cardinal(year)}年{spoken}" if year else spoken
