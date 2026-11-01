import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from soccer_wallart.art.palette import COLORS, NATIVE_CODE, ORDER, nearest, team_colors
from soccer_wallart.config import Config, TeamConfig
from soccer_wallart.data.espn import parse_scoreboard, parse_team_schedule
from soccer_wallart.render import pack_native, snap, to_panel
from soccer_wallart.sample import sample_board, sample_matches
from soccer_wallart.selection import build_board, next_wake_seconds
from soccer_wallart.service import Service

FIX = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


def load(name):
    return json.loads((FIX / name).read_text())


def cfg(**kw):
    base = dict(
        teams=[TeamConfig(name="Minnesota United", espn_id="17362", leagues=["usa.1"])],
        leagues=["eng.1", "uefa.champions", "esp.1"],
        featured_priority=["teams", "uefa.champions", "eng.1"],
        cache_dir="/tmp/soccer-wallart-test-cache",
    )
    base.update(kw)
    return Config(**base)


# --- ESPN parsing -----------------------------------------------------------
def test_parse_scoreboard_premier_league():
    ms = parse_scoreboard(load("eng1_20261107.json"), "eng.1")
    assert len(ms) == 4
    m = next(m for m in ms if m.home.name == "Arsenal")
    assert m.away.name == "Hull City"
    assert m.kickoff == datetime(2026, 11, 7, 15, 0, tzinfo=timezone.utc)
    assert m.venue == "Emirates Stadium"
    assert m.state == "pre" and m.home_score is None
    assert m.home.color == "e20520" and m.home.abbreviation == "ARS"
    assert m.competition.name == "English Premier League"


def test_parse_scoreboard_ucl_broadcasts():
    ms = parse_scoreboard(load("ucl_20261104.json"), "uefa.champions")
    assert len(ms) == 9
    assert any("Paramount+" in m.broadcasts for m in ms)


def test_parse_team_schedule_object_scores():
    data = {"events": [{
        "id": "1", "date": "2026-03-15T20:30Z",
        "competitions": [{"date": "2026-03-15T20:30Z",
                          "status": {"type": {"state": "post", "shortDetail": "FT"}},
                          "competitors": [
                              {"homeAway": "home", "team": {"id": "9727", "displayName": "Vancouver"},
                               "score": {"value": 6.0, "displayValue": "6"}},
                              {"homeAway": "away", "team": {"id": "17362", "displayName": "Minnesota"},
                               "score": {"value": 0.0}}]}]}]}
    (m,) = parse_team_schedule(data, "usa.1", colors={"17362": ("000000", "9bcde4")})
    assert (m.home_score, m.away_score) == (6, 0)
    assert m.away.color == "000000"


# --- selection --------------------------------------------------------------
def test_featured_prefers_favourite_team():
    b = build_board(sample_matches(NOW), cfg(), NOW)
    assert b.featured.id == "s2"          # LAFC vs Minnesota
    assert all(m.id != "s2" for m in b.upcoming)
    assert [m.kickoff for m in b.upcoming] == sorted(m.kickoff for m in b.upcoming)
    assert len(b.upcoming) <= 5


def test_featured_falls_back_to_league_priority():
    b = build_board(sample_matches(NOW), cfg(teams=[]), NOW)
    assert b.featured.competition.slug == "uefa.champions"


def test_unconfigured_leagues_filtered():
    b = build_board(sample_matches(NOW), cfg(leagues=["eng.1"], teams=[]), NOW)
    slugs = {m.competition.slug for m in [b.featured, *b.upcoming]}
    assert slugs == {"eng.1"}


def test_finished_matches_drop_off_after_window():
    ms = sample_matches(NOW)
    later = NOW + timedelta(days=2)
    b = build_board(ms, cfg(), later)
    assert all(m.kickoff + timedelta(minutes=150) >= later for m in [b.featured, *b.upcoming])


def test_next_wake_is_clamped_and_hits_kickoff():
    c = cfg()
    b = build_board(sample_matches(NOW), c, NOW)
    secs = next_wake_seconds(b, c, NOW)
    first_kick = min(m.kickoff for m in [b.featured, *b.upcoming])
    assert secs == int((first_kick - NOW).total_seconds())
    assert 15 * 60 <= secs <= 12 * 3600


# --- palette / rendering ------------------------------------------------------
@pytest.mark.parametrize("hexc,expected", [
    ("e20520", "red"), ("ffffff", "white"), ("000000", "black"), ("0606fa", "blue"),
    ("ffee00", "yellow"), ("288A00", "green"), ("99c5ea", "blue"), ("990000", "red"),
])
def test_nearest(hexc, expected):
    assert nearest(hexc) == expected


def test_team_color_overrides():
    assert team_colors("83", "990000", "FCE38A") == ("blue", "red")
    assert team_colors("999", "e20520", "e20520")[1] != "red"
    assert team_colors("999", "e20520", None, {"999": ["green", "white"]}) == ("green", "white")


def test_snap_keeps_blends_sane():
    # red/white blend (pink) must never become yellow; grey must stay neutral
    img = Image.new("RGB", (3, 1))
    img.putdata([(228, 143, 143), (128, 128, 128), (200, 30, 30)])
    idx = snap(img)[0]
    names = [ORDER[i] for i in idx]
    assert names[0] in ("red", "white")
    assert names[1] in ("black", "white")
    assert names[2] == "red"


def test_pack_native():
    idx = np.array([[ORDER.index("black"), ORDER.index("white"), ORDER.index("green"), ORDER.index("red")]],
                   dtype=np.uint8)
    out = pack_native(idx)
    assert out == bytes([(NATIVE_CODE["black"] << 4) | NATIVE_CODE["white"],
                         (NATIVE_CODE["green"] << 4) | NATIVE_CODE["red"]])


@pytest.mark.parametrize("layout", ["sunburst", "diagonal", "deco"])
def test_full_render_only_palette_colors(layout):
    c = cfg()
    svc = Service(c, provider=object())
    b = sample_board("s1", NOW)
    f = svc.render(b, NOW, layout=layout)
    assert len(f.native) == 800 * 480 // 2
    valid = set(NATIVE_CODE.values())
    arr = np.frombuffer(f.native, dtype=np.uint8)
    assert set(np.unique(arr >> 4)) <= valid and set(np.unique(arr & 0xF)) <= valid
    im = Image.open(__import__("io").BytesIO(f.png))
    assert im.size == (800, 480)
    assert {c for _, c in im.getcolors()} <= set(COLORS.values())


def test_etag_stable_across_clock_but_changes_with_score():
    c = cfg()
    svc = Service(c, provider=object())
    b = sample_board("s1", NOW)
    e1 = svc.render(b, NOW).etag
    e2 = svc.render(b, NOW + timedelta(minutes=5)).etag
    assert e1 == e2
    b.featured.state, b.featured.home_score, b.featured.away_score = "in", 1, 0
    assert svc.render(b, NOW).etag != e1


def test_letterbox_other_panel_size():
    design = Image.new("RGB", (2400, 1440), (255, 255, 255))
    idx = to_panel(design, 1600, 1200)
    assert idx.shape == (1200, 1600)
