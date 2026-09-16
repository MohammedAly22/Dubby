"""Chinese (Mandarin, simplified) normalization rules."""

from __future__ import annotations

import re
from typing import Optional

from dubby.text.common import Money, Noun, Rules

_D = "零一二三四五六七八九"
# measure words after which 2 is read 两
_MEASURES = set("个次位本张件条只天年岁米块元家种辆台部份杯瓶层双周倍名点项座间门颗句首篇场")


def _section(n: int) -> str:
    out, zero = "", False
    for value, unit in ((1000, "千"), (100, "百"), (10, "十"), (1, "")):
        digit, n = divmod(n, value)
        if digit == 0:
            zero = bool(out)
        else:
            if zero:
                out += "零"
                zero = False
            out += _D[digit] + unit
    return out


def _n(word: str) -> Noun:
    return Noun(word, word)


class ChineseRules(Rules):
    code = "zh"
    latin_script = False
    cjk = True
    words = {
        "point": "点", "minus": "负", "and": "和", "money_and": "", "to": "到", "percent": "百分之", "per_mille": "千分之",
        "dot": "点", "slash": "斜杠", "underscore": "下划线", "dash": "杠", "at": "艾特", "hashtag": "话题",
        "plus": "加", "equals": "等于", "not_equal": "不等于", "less_equal": "小于等于", "greater_equal": "大于等于",
        "less": "小于", "greater": "大于", "times": "乘以", "divided": "除以", "approx": "大约", "degrees": "度", "or": "或",
    }
    currency_aliases = {"元": "CNY", "美元": "USD", "欧元": "EUR", "英镑": "GBP", "日元": "JPY"}
    currencies = {
        "CNY": Money(_n("元"), _n("分")), "USD": Money(_n("美元"), _n("美分")), "EUR": Money(_n("欧元"), _n("欧分")),
        "GBP": Money(_n("英镑"), _n("便士")), "JPY": Money(_n("日元")), "INR": Money(_n("卢比")),
        "EGP": Money(_n("埃及镑")), "SAR": Money(_n("沙特里亚尔")), "AED": Money(_n("迪拉姆")),
    }
    units = {
        "km": _n("公里"), "m": _n("米"), "cm": _n("厘米"), "mm": _n("毫米"), "mi": _n("英里"), "ft": _n("英尺"),
        "kg": _n("公斤"), "g": _n("克"), "mg": _n("毫克"), "lb": _n("磅"), "lbs": _n("磅"), "oz": _n("盎司"),
        "l": _n("升"), "L": _n("升"), "ml": _n("毫升"), "mL": _n("毫升"), "km/h": _n("公里每小时"), "kmh": _n("公里每小时"),
        "kph": _n("公里每小时"), "mph": _n("英里每小时"), "m/s": _n("米每秒"), "km²": _n("平方公里"), "km2": _n("平方公里"),
        "m²": _n("平方米"), "m2": _n("平方米"), "cm²": _n("平方厘米"), "m³": _n("立方米"), "m3": _n("立方米"),
        "°C": _n("摄氏度"), "ºC": _n("摄氏度"), "°F": _n("华氏度"), "ºF": _n("华氏度"), "°": _n("度"),
        "GB": _n("G"), "GiB": _n("G"), "MB": _n("兆"), "MiB": _n("兆"), "KB": _n("K"), "kB": _n("K"), "TB": _n("T"),
        "Gbps": _n("千兆每秒"), "Mbps": _n("兆每秒"), "kbps": _n("K每秒"), "fps": _n("帧每秒"), "Hz": _n("赫兹"),
        "kHz": _n("千赫"), "MHz": _n("兆赫"), "GHz": _n("吉赫"), "W": _n("瓦"), "kW": _n("千瓦"), "kWh": _n("度电"),
        "V": _n("伏"), "mAh": _n("毫安时"), "h": _n("小时"), "hr": _n("小时"), "hrs": _n("小时"), "min": _n("分钟"),
        "mins": _n("分钟"), "s": _n("秒"), "sec": _n("秒"), "secs": _n("秒"), "ms": _n("毫秒"), "px": _n("像素"), "x": _n("倍"),
    }
    unit_aliases = {"公里": "km", "千米": "km", "厘米": "cm", "毫米": "mm", "公斤": "kg", "千克": "kg", "毫升": "ml",
                    "小时": "h", "分钟": "min", "秒钟": "s", "摄氏度": "°C", "℃": "°C", "℉": "°F"}
    fraction_words = {"½": "二分之一", "⅓": "三分之一", "⅔": "三分之二", "¼": "四分之一", "¾": "四分之三", "⅕": "五分之一", "⅛": "八分之一"}

    def cardinal(self, n: int) -> str:
        if n == 0:
            return "零"
        sections = []
        while n > 0:
            n, section = divmod(n, 10000)
            sections.append(section)
        units = ["", "万", "亿", "万亿"]
        out, gap = "", False
        for index in range(len(sections) - 1, -1, -1):
            section = sections[index]
            if section == 0:
                gap = bool(out)
                continue
            if out and (gap or section < 1000):
                out += "零"
            out += _section(section) + units[index]
            gap = False
        if out.startswith("一十"):
            out = out[1:]
        return re.sub(r"(^|[零万亿])二(?=[千万亿])", r"\1两", out)

    def ordinal(self, n: int, feminine: bool = False) -> str:
        return "第" + self.cardinal(n)

    def digit_words(self, digits: str) -> str:
        return "".join(_D[int(d)] for d in digits if d.isdigit())

    def decimal_words(self, integer: int, fraction: str) -> str:
        return f"{self.cardinal(integer)}点{self.digit_words(fraction)}"

    def year(self, n: int) -> str:
        return self.digit_words(str(n))

    def is_year(self, value: int, before: str, after: str) -> bool:
        return after.lstrip().startswith("年")

    def cardinal_before(self, n: int, next_word: str) -> str:
        if n == 2 and next_word and next_word[0] in _MEASURES:
            return "两"
        return self.cardinal(n)

    def count(self, integer: int, fraction: str, noun: Noun) -> str:
        words = "两" if integer == 2 and not fraction and noun.one not in ("度", "摄氏度", "华氏度") else self.number(integer, fraction.rstrip("0"))
        return words + noun.one

    def money(self, integer: int, fraction: str, code: str) -> str:
        money = self.currencies.get(code)
        name = money.main.one if money else code
        return self.count(integer, fraction, Noun(name, name))

    def percent(self, words: str) -> str:
        return "百分之" + words

    def per_mille(self, words: str) -> str:
        return "千分之" + words

    def negative(self, words: str) -> str:
        return "负" + words

    def range(self, a: str, b: str) -> str:
        return f"{a}到{b}"

    def fraction(self, a: int, b: int) -> Optional[str]:
        return f"{self.cardinal(b)}分之{self.cardinal(a)}"

    def time(self, hour: int, minute: int, period: Optional[str]) -> str:
        prefix = ""
        if period:
            prefix = "上午" if period == "a" else "下午"
        head = ("两" if hour == 2 else self.cardinal(hour)) + "点"
        if minute == 0:
            return prefix + head
        if minute == 30:
            return prefix + head + "半"
        return prefix + head + ("零" if minute < 10 else "") + self.cardinal(minute) + "分"

    def date(self, day: int, month: int, year: Optional[int]) -> str:
        spoken = f"{self.cardinal(month)}月{self.cardinal(day)}日"
        return f"{self.year(year)}年{spoken}" if year else spoken
