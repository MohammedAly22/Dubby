"""Burned-in captions: player-equivalent timeline, word-level bidi order and layout (no network)."""

import pytest

from dubby.pipeline import captions as C
from dubby.schemas import Project, Segment, TTSState, Word


def project() -> Project:
    p = Project(id="t")
    p.settings.source_language, p.settings.target = "en", "arz"
    p.segments = [
        Segment(id="a", start=1.0, end=3.0, text="Buy gold now",
                words=[Word(text="Buy", start=1.0, end=1.4), Word(text="gold", start=1.5, end=2.0), Word(text="now", start=2.2, end=2.8)],
                translation="اشتري دهب دلوقتي", tts=TTSState(status="done", duration=1.8),
                dub_words=[Word(text="اشتري", start=1.1, end=1.6), Word(text="دهب", start=1.7, end=2.1), Word(text="دلوقتي", start=2.2, end=2.9)]),
    ]
    p.render.clips = [{"id": "a", "start": 1.1, "end": 2.9, "rate": 1.0}]
    return p


def states_at(states, t):
    return next(boxes for a, b, _, boxes in states if a <= t < b)


def test_timeline_follows_player_rules():
    states = C.timeline(project(), "both")
    assert states_at(states, 0.5) == []
    boxes = states_at(states, 1.45)  # between "Buy" and "gold": no current source word; dub word 1 current
    original, dub = boxes
    assert [t.state for t in original.tokens] == ["spoken", "upcoming", "upcoming"]
    assert [t.state for t in dub.tokens] == ["current", "upcoming", "upcoming"]
    # the dub word stays current until the next word starts (gap 1.6-1.7)
    assert [t.state for t in states_at(states, 1.65)[1].tokens] == ["current", "upcoming", "upcoming"]
    # the dub line lingers 0.15 s after the clip, the source line ends with its segment
    assert [b.kind for b in states_at(states, 3.0)] == ["dub"]
    assert states_at(states, 3.1) == []


def test_modes_select_lines():
    assert {b.kind for _, _, _, boxes in C.timeline(project(), "dub") for b in boxes} == {"dub"}
    assert {b.kind for _, _, _, boxes in C.timeline(project(), "original") for b in boxes} == {"original"}


def test_visual_order_rtl_keeps_latin_runs_left_to_right():
    words = ["اشتري", "iPhone", "15", "دلوقتي."]
    dirs = [C.strong_direction(w) for w in words]
    assert dirs == ["R", "L", None, "R"]
    # right-to-left paragraph: laid out left→right as دلوقتي. | iPhone 15 | اشتري
    assert C.visual_order(dirs, "R") == [3, 1, 2, 0]
    assert C.visual_order(["L", "R", "R", "L"], "L") == [0, 2, 1, 3]


def test_small_videos_are_upscaled_for_captions():
    assert C.MIN_CAPTION_WIDTH >= 1280


@pytest.fixture(scope="module")
def fonts(tmp_path_factory):
    from dubby.media.fonts import FontSet

    fontset = FontSet(tmp_path_factory.mktemp("fonts"))  # empty: system fonts only, no download
    if fontset.path("latin", 400) is None or fontset.path("arabic", 400) is None:
        pytest.skip("no system fonts for the layout test")
    return fontset


def test_layout_wraps_centers_and_orders_rtl(fonts):
    renderer = C.Renderer(1280, 720, fonts, "en", "arz")
    long_line = C.Box("original", [C.Token(w, "upcoming") for w in ("word " * 60).split()], "en")
    lay = renderer.layout(long_line)
    rows = {round(baseline) for _, baseline, _ in lay["placed"]}
    assert len(rows) >= 2  # wrapped
    assert lay["w"] <= 1280 * 0.92  # respects max width

    rtl = C.Box("dub", [C.Token(w, "spoken") for w in ("اشتري", "دهب", "دلوقتي")], "arz")
    placed = renderer.layout(rtl)["placed"]
    xs = {it["text"]: x for x, _, it in placed}
    assert xs["اشتري"] > xs["دهب"] > xs["دلوقتي"]  # first word on the right

    image = renderer.render([long_line, rtl], 300)
    assert image.size == (1280, 420) and image.getbbox() is not None
