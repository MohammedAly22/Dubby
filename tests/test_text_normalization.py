"""Text normalization for TTS: one table of (input → expected spoken text) per dub language.

Run: ``python -m pytest tests/test_text_normalization.py -q``
Add a case whenever you fix or extend a language's rules.
"""

import re

import pytest

from dubby.text import SUPPORTED, normalize, normalize_safe

CASES = {
    "en": [
        ("Dr. Smith paid $1,250.50 on May 5, 2024 at 3:30 pm.",
         "Doctor Smith paid one thousand two hundred fifty dollars and fifty cents on May fifth, twenty twenty-four at three thirty p m."),
        ("Call +1 (555) 123-4567.", "Call plus one, five five five, one two three, four five six seven."),
        ("The 21st century, 72°F, 5 km, 10GB, 60 fps.", "The twenty-first century, seventy-two degrees Fahrenheit, five kilometers, ten gigabytes, sixty frames per second."),
        ("COVID-19 hit in the 1990s; 1.5M users; v1.2.3", "COVID nineteen hit in the nineteen nineties; one point five million users; v one dot two dot three"),
        ("Email john.doe@gmail.com", "Email john dot doe at gmail dot com"),
        ("Wait 10s, ½ price, 3/4 done, 24/7.", "Wait ten seconds, one half price, three quarters done, twenty-four seven."),
    ],
    "es": [
        ("El Dr. García pagó 1.250,50 € el 1 de mayo de 2024 a las 15:45.",
         "El doctor García pagó mil doscientos cincuenta euros con cincuenta céntimos el primero de mayo de dos mil veinticuatro a las cuatro menos cuarto de la tarde."),
        ("Tengo 21 años, 21 libras, 200 horas, 1 km, 31 millas.", "Tengo veintiún años, veintiuna libras, doscientas horas, un kilómetro, treinta y una millas."),
        ("La 1ª vez, el 3er puesto, $5M.", "La primera vez, el tercer puesto, cinco millones de dólares."),
    ],
    "fr": [
        ("M. Dupont a payé 1 250,50 € le 1er mai 2024 à 14h30.",
         "monsieur Dupont a payé mille deux cent cinquante euros et cinquante centimes le premier mai deux mille vingt-quatre à quatorze heures trente."),
        ("71 personnes, 80 euros, 81 %, 1 000 000 €.", "soixante et onze personnes, quatre-vingts euros, quatre-vingt-un pour cent, un million d'euros."),
    ],
    "it": [
        ("Il Dott. Rossi ha pagato 1.250,50 € il 1° maggio 2024 alle 15:45.",
         "Il dottor Rossi ha pagato milleduecentocinquanta euro e cinquanta centesimi il primo maggio duemilaventiquattro alle sedici meno un quarto."),
        ("Ho 1 ora, 23 euro, 180 km e 5k follower.", "Ho un'ora, ventitré euro, centottanta chilometri e cinquemila follower."),
    ],
    "arb": [
        ("دفع د. أحمد 1,250.50 $ يوم 5/6/2024 الساعة 10:30 ص.",
         "دفع الدكتور أحمد ألف ومئتان وخمسون دولارا وخمسون سنتا يوم الخامس من يونيو عام ألفين وأربعة وعشرين الساعة العاشرة والنصف صباحا."),
        ("وصل 3 ساعات و 11 دقيقة و 1 ثانية.", "وصل ثلاث ساعات وإحدى عشرة دقيقة وثانية واحدة."),
    ],
    "arz": [
        ("عندي meeting الساعة 3:30 وهيكلفني حوالي 250 جنيه", "عندي meeting الساعة تلاتة و نص وهيكلفني حوالي متين وخمسين جنيه"),
        ("خصم 25% و Ahmed هيكلمك الساعة 7:45", "خصم خمسه وعشرين في المية و أحمد هيكلمك الساعة تمانيه الا ربع"),
    ],
    "hi": [
        ("डॉ. शर्मा ने 1,00,000 रुपये सुबह 10:30 बजे दिए।", "डॉक्टर शर्मा ने एक लाख रुपये सुबह साढ़े दस बजे दिए।"),
        ("सन् 1998 में 45% लोग थे।", "सन् उन्नीस सौ अट्ठानबे में पैंतालीस प्रतिशत लोग थे।"),
    ],
    "zh": [
        ("他有2个孩子，跑了2公里，温度25°C，增长了15%。", "他有两个孩子，跑了两公里，温度二十五摄氏度，增长了百分之十五。"),
        ("第3章有10010个字，2024年5月5日下午3:30。", "第三章有一万零一十个字，二零二四年五月五日下午三点半。"),
    ],
    "ja": [
        ("時速60km/hで走り、気温は25°C、成長率は15%です。", "時速六十キロで走り、気温は二十五度、成長率は十五パーセントです。"),
        ("会議は14:30から2時間、費用は$1,200です。", "会議は十四時半から二時間、費用は千二百ドルです。"),
    ],
}


@pytest.mark.parametrize("language,text,expected", [(lang, a, b) for lang, cases in CASES.items() for a, b in cases])
def test_normalize(language, text, expected):
    assert normalize(text, language) == expected


def test_every_language_has_cases():
    assert set(SUPPORTED) == set(CASES)


def test_unsupported_language_only_cleans_whitespace():
    assert normalize("  a   1  ", "xx") == "a 1"


def test_normalize_safe_never_raises():
    text, error = normalize_safe("12 kg", "en")
    assert text == "twelve kilograms" and error is None


def test_egyptian_keeps_user_tashkeel():
    assert "إِزَّيَّك" in normalize("إِزَّيَّك يا Ahmed", "arz")


def test_egyptian_matches_voicetut_without_diacritics():
    vt = pytest.importorskip("voicetut_tts.normalization")
    strip = lambda s: re.sub("[ً-ْٰ]", "", s)  # noqa: E731
    reference = vt.ArabicNormalizer(apply_diacritics=False)
    for sentence in [
        "اتصل بيا على 01147450629 أو ابعتلي على ahmed.ali@gmail.com",
        "الحلقة دي نزلت يوم 14/3/2024 على https://youtube.com/voicetut",
        "الكتاب بـ 1500 EGP والشحن 75$ بس",
        "المسافة 12 كم والوزن 3.5 كجم",
    ]:
        assert normalize(sentence, "arz") == strip(reference(sentence))
