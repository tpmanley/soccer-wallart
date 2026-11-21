import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import numpy as np
import pytest
from PIL import Image

from soccer_wallart.art.palette import COLORS, NATIVE_CODE, ORDER, nearest, team_colors
from soccer_wallart.config import Config, TeamConfig
from soccer_wallart.data.espn import parse_scoreboard, parse_team_schedule
from soccer_wallart.render import pack_native, snap, to_panel
from soccer_wallart.sample import sample_board, sample_matches
from soccer_wallart.selection import Board, build_board, next_wake_seconds
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
        watch={"livesoccertv": False},   # tests never touch the network
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


def test_parse_team_schedule_broadcasts():
    data = {"events": [{
        "id": "1", "date": "2026-11-22T13:00Z",
        "competitions": [{"date": "2026-11-22T13:00Z",
                          "status": {"type": {"state": "pre"}},
                          "broadcasts": [
                              {"type": {"shortName": "TV"}, "media": {"shortName": "ESPN Deportes"}},
                              {"type": {"shortName": "STREAMING"}, "media": {"shortName": "ESPN+"}}],
                          "competitors": [
                              {"homeAway": "home", "team": {"id": "83", "displayName": "Barcelona"}},
                              {"homeAway": "away", "team": {"id": "102", "displayName": "Villarreal"}}]}],
    }]}
    (m,) = parse_team_schedule(data, "esp.1")
    assert m.broadcasts == ["ESPN Deportes", "ESPN+"]


def test_pick_broadcast_prefers_my_services():
    c = cfg(watch={"services": ["Peacock", "paramount plus"]})
    assert c.pick_broadcast(["ESPN+", "Paramount+", "Peacock"]) == "Peacock"
    assert c.pick_broadcast(["ESPN+", "Paramount+"]) == "Paramount+"
    assert c.pick_broadcast(["FS1", "FOX"]) == "FOX"          # free OTA beats one I don't have
    assert c.pick_broadcast(["FS1", "ESPN+"]) == "FS1"        # nothing matches: ESPN's order
    assert c.pick_broadcast([]) is None
    no_free = cfg(watch={"services": [], "include_free": False})
    assert no_free.pick_broadcast(["FS1", "FOX"]) == "FS1"


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


def test_next_wake_is_clamped_and_hits_halftime():
    c = cfg()
    b = build_board(sample_matches(NOW), c, NOW)
    secs = next_wake_seconds(b, c, NOW)
    first_kick = min(m.kickoff for m in [b.featured, *b.upcoming])
    assert secs == int((first_kick + timedelta(minutes=55) - NOW).total_seconds())
    assert 15 * 60 <= secs <= 12 * 3600


def _one_match_board(state, kickoff, now):
    m = sample_matches(NOW)[3]  # Liverpool v Arsenal
    m.state, m.kickoff = state, kickoff
    return Board(featured=m, upcoming=[], generated_at=now)


def test_game_day_wakes_at_halftime_then_full_time():
    c = cfg()
    kick = NOW + timedelta(hours=4)  # 10:00 AM Chicago, after the 6:00 daily wake
    # Before kickoff: no wake at kickoff itself, the first one is halftime.
    b = _one_match_board("pre", kick, kick - timedelta(hours=2))
    assert next_wake_seconds(b, c, kick - timedelta(hours=2)) == (2 * 60 + 55) * 60
    # At halftime (even if ESPN still says "pre"): next is full time.
    for state in ("in", "pre"):
        t = kick + timedelta(minutes=55)
        assert next_wake_seconds(_one_match_board(state, kick, t), c, t) == 60 * 60
    # Woke a minute early for halftime: still goes to full time, not a 15-minute nap.
    t = kick + timedelta(minutes=54)
    assert next_wake_seconds(_one_match_board("in", kick, t), c, t) == 61 * 60
    # Still going at full time: check again in live_minutes.
    t = kick + timedelta(minutes=115)
    assert next_wake_seconds(_one_match_board("in", kick, t), c, t) == 15 * 60


def test_today_scoreboards_use_short_cache(tmp_path):
    from datetime import date
    from soccer_wallart.data.cache import JsonCache
    from soccer_wallart.data.espn import LIVE_TTL_SECONDS, EspnProvider

    class Client:
        def __init__(self):
            self.urls = []

        def get(self, url, params=None):
            self.urls.append(params["dates"])
            return httpx.Response(200, json={"events": []}, request=httpx.Request("GET", url))

    client = Client()
    p = EspnProvider(JsonCache(tmp_path, 3600), client=client)
    today, far = date.today(), date.today() + timedelta(days=5)
    p.scoreboard("eng.1", today), p.scoreboard("eng.1", far)
    import os, time
    old = time.time() - LIVE_TTL_SECONDS - 10
    for f in tmp_path.glob("*.json"):
        os.utime(f, (old, old))
    p.scoreboard("eng.1", today), p.scoreboard("eng.1", far)
    assert client.urls.count(today.strftime("%Y%m%d")) == 2  # refetched
    assert client.urls.count(far.strftime("%Y%m%d")) == 1    # still cached


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


def test_battery_changes_only_redraw_when_crossing_low():
    c = cfg()
    svc = Service(c, provider=object())
    b = sample_board("s1", NOW)
    e = {pct: svc.render(b, NOW, battery=pct).etag for pct in (19, 25, 31, 72, 100, 5)}
    assert e[25] == e[31] == e[72] == e[100]        # charging/gauge jumps don't redraw
    assert e[19] == e[5] != e[25]                   # dropping below 20% does
    assert svc.render(b, NOW).etag not in (e[19], e[25])  # no battery reported is its own state


def test_letterbox_other_panel_size():
    design = Image.new("RGB", (2400, 1440), (255, 255, 255))
    idx = to_panel(design, 1600, 1200)
    assert idx.shape == (1200, 1600)


# --- config loading ------------------------------------------------------------
from soccer_wallart.config import ConfigError, load_config  # noqa: E402


def test_missing_config_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.yaml")
    assert load_config(tmp_path / "nope.yaml", required=False).teams == []


def test_bad_timezone_is_an_error(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("timezone: Mars/Olympus\n")
    with pytest.raises(ConfigError, match="unknown timezone"):
        load_config(p)


def test_relative_cache_dir_resolves_next_to_config(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("cache_dir: .cache\n")
    assert load_config(p).cache_dir == str(tmp_path.resolve() / ".cache")


# --- club emblems ----------------------------------------------------------------
from soccer_wallart.art.canvas import Canvas  # noqa: E402
from soccer_wallart.art.emblems import EMBLEMS  # noqa: E402


@pytest.mark.parametrize("team_id", sorted(EMBLEMS))
def test_emblem_draws_in_its_box(team_id):
    c = Canvas(3, bg="white")
    EMBLEMS[team_id](c, 100, 100, 70, 90)
    ink = np.argwhere(np.asarray(c.img.convert("L")) < 250)  # anything not white
    (y0, x0), (y1, x1) = ink.min(0) / 3, ink.max(0) / 3
    # body stays in the box; ornaments may rise above it, flames may sit just outside
    assert 70 <= x0 and x1 <= 200 and 55 <= y0 and y1 <= 195


def test_empty_week_fills_next_up_from_team_schedules():
    """International break: nothing within lookahead_days, so pull the teams' later fixtures."""
    later = [m for d in (12, 15, 20, 25, 30, 35, 40)
             for m in sample_matches(NOW + timedelta(days=d)) if m.team_ids & {"17362"}]
    for i, m in enumerate(later):
        m.id = f"later{i}"

    class Provider:
        def matches(self, *a):
            return []

        def team_schedule(self, *a, **k):
            return list(reversed(later)) + [later[0]]   # unsorted, with a duplicate

        def team_results(self, *a, **k):
            return []

    b = Service(cfg(), provider=Provider()).board(NOW)
    assert b.featured.id == "later0"
    ids = [m.id for m in b.upcoming]
    assert ids == [f"later{i}" for i in range(1, 6)]       # capped at list_size
    assert len(set(ids)) == len(ids)


def test_rotate_180_flips_only_the_device_buffer():
    board = sample_board("s1", NOW)
    up = Service(cfg()).render(board, NOW)
    c = cfg()
    c.display.rotate = 180
    down = Service(c).render(board, NOW)
    assert down.png == up.png                       # preview stays upright
    assert down.native != up.native
    assert down.etag != up.etag                     # frame redraws after the setting changes
    w = 800 // 2
    first_row = np.frombuffer(up.native[:w], np.uint8)
    last_row_flipped = np.frombuffer(down.native[-w:], np.uint8)[::-1]
    swap = (last_row_flipped >> 4) | ((last_row_flipped & 0xF) << 4)   # pixel order within a byte
    assert np.array_equal(first_row, swap)


# --- result hold (refresh.result_hold) --------------------------------------------
from zoneinfo import ZoneInfo  # noqa: E402

from soccer_wallart.art.poster import list_layout  # noqa: E402
from soccer_wallart.data.models import Match  # noqa: E402
from soccer_wallart.sample import EPL, MLS, T, sample_recent  # noqa: E402
from soccer_wallart.selection import hold_end, pick_recent  # noqa: E402

CT = ZoneInfo("America/Chicago")


def ct(day, hh, mm=0):
    """A Chicago time in Nov 2026 (CST): ct(21, 19, 30) = Sat 21 Nov, 7:30 PM."""
    return datetime(2026, 11, day, hh, mm, tzinfo=CT)


def mk(mid, kickoff, state="pre", score=None, comp=MLS, home="min", away="stl", winner=None):
    hs, as_ = score if score else (None, None)
    return Match(mid, comp, T[home], T[away], kickoff.astimezone(timezone.utc), state=state,
                 home_score=hs, away_score=as_, winner=winner)


SAT_RESULT = lambda: mk("res", ct(21, 19, 30), "post", (2, 1))   # noqa: E731


def test_result_held_until_next_match_day_refresh():
    c = cfg()
    nxt = mk("epl", ct(22, 8), comp=EPL, home="liv", away="ars")     # Sunday 8:00 AM
    ms = [SAT_RESULT(), nxt]
    assert hold_end(ms[0], ms, c) == ct(22, 6)                        # Sunday's 06:00 refresh
    for t in (ct(21, 23), ct(22, 2), ct(22, 5, 50)):
        b = build_board(ms, c, t)
        assert b.featured.id == "res" and b.hold_until == ct(22, 6)
        assert [m.id for m in b.upcoming] == ["epl"]
    # The 6:00 wake (or one a few minutes early, from clock drift) shows the next match.
    for t in (ct(22, 5, 57), ct(22, 6), ct(22, 6, 3)):
        b = build_board(ms, c, t)
        assert b.featured.id == "epl" and b.hold_until is None


def test_result_hold_ends_before_an_early_kickoff():
    c = cfg()
    early = mk("ucl", ct(22, 5), comp=EPL, home="liv", away="ars")    # kicks off before 06:00
    ms = [SAT_RESULT(), early]
    assert hold_end(ms[0], ms, c) == ct(22, 4, 30)                    # hold_before_kickoff_hours


def test_result_hold_is_at_least_after_match_minutes():
    c = cfg()
    res = mk("res", ct(21, 12), "post", (0, 0))
    later = mk("epl", ct(21, 14), comp=EPL, home="liv", away="ars")   # same day
    assert hold_end(res, [res, later], c) == ct(21, 14, 30)          # kickoff + 150 min


def test_result_hold_capped_at_a_daily_refresh_when_nothing_is_coming():
    c = cfg()
    res = SAT_RESULT()
    # Sat 7:30 PM + 48 h = Mon 7:30 PM; the last 06:00 refresh inside that is Monday's.
    assert hold_end(res, [res], c) == ct(23, 6)
    far = mk("far", ct(28, 18))                                       # a week later
    assert hold_end(res, [res, far], c) == ct(23, 6)
    assert build_board([res, far], c, ct(23, 5)).featured.id == "res"
    assert build_board([res, far], c, ct(23, 6)).featured.id == "far"


def test_fixed_result_hold_keeps_the_old_window():
    c = cfg(refresh={"result_hold": "fixed"})
    ms = [SAT_RESULT(), mk("epl", ct(22, 8), comp=EPL, home="liv", away="ars")]
    assert build_board(ms, c, ct(21, 21, 59)).featured.id == "res"
    b = build_board(ms, c, ct(21, 22, 1))
    assert b.featured.id == "epl" and b.hold_until is None


def test_live_match_beats_a_held_result():
    c = cfg()
    res = mk("res", ct(21, 12), "post", (1, 0))
    live = mk("live", ct(21, 13), "in", (0, 0), home="lafc", away="min")
    assert build_board([res, live], c, ct(21, 14)).featured.id == "live"


def test_postponed_game_is_not_held():
    c = cfg()
    pp = SAT_RESULT()
    pp.completed = False
    ms = [pp, mk("epl", ct(22, 8), comp=EPL, home="liv", away="ars")]
    assert build_board(ms, c, ct(21, 23)).featured.id == "epl"


def test_wake_at_hold_end_only_when_it_is_not_the_daily_refresh():
    c = cfg()
    # Hold ends at the 06:00 refresh: the wake is the daily one, nothing extra.
    ms = [SAT_RESULT(), mk("epl", ct(22, 8), comp=EPL, home="liv", away="ars")]
    t = ct(21, 23)
    assert next_wake_seconds(build_board(ms, c, t), c, t) == 7 * 3600
    # Early kickoff: one wake at 04:30 to put the match up, then halftime as usual.
    ms = [SAT_RESULT(), mk("ucl", ct(22, 5), comp=EPL, home="liv", away="ars")]
    assert next_wake_seconds(build_board(ms, c, t), c, t) == int(5.5 * 3600)
    t = ct(22, 4, 30)
    b = build_board(ms, c, t)
    assert b.featured.id == "ucl"
    assert next_wake_seconds(b, c, t) == int((ct(22, 5, 55) - t).total_seconds())   # halftime
    # Same-day doubleheader: wake when the result gives way (kickoff + 150), not at halftime.
    res = mk("res", ct(21, 12), "post", (0, 0))
    ms = [res, mk("epl", ct(21, 18), comp=EPL, home="liv", away="ars")]
    t = ct(21, 13, 55)
    assert next_wake_seconds(build_board(ms, c, t), c, t) == 35 * 60


# --- LAST strip (recent results) -----------------------------------------------------
def test_parse_team_results():
    ms = parse_team_schedule(load("usa1_team17362_results.json"), "usa.1")
    assert [m.kickoff.date().isoformat() for m in ms][:2] == ["2026-11-08", "2026-11-02"]
    m = ms[0]
    assert m.is_result and (m.home.abbreviation, m.home_score, m.away_score) == ("MIN", 3, 1)
    assert m.winner == "home" and m.outcome_for("17362") == "W" and m.outcome_for("191") == "L"
    assert ms[1].outcome_for("17362") == "W"                          # away win at LAFC


def test_shootout_counts_as_a_win():
    ms = parse_team_schedule(load("usaopen_team17362_results.json"), "usa.open")
    pens = next(m for m in ms if m.home_score == m.away_score)
    assert pens.winner == "away" and pens.outcome_for("17362") == "W"
    lost = next(m for m in ms if m is not pens)
    assert lost.outcome_for("17362") == "L"


def test_draw_and_postponed_outcomes():
    d = mk("d", ct(14, 19), "post", (1, 1))
    assert d.outcome_for("17362") == "D" and d.outcome_for("21812") == "D"
    data = {"events": [{"id": "9", "date": "2026-11-14T20:00Z", "competitions": [{
        "status": {"type": {"state": "post", "completed": False, "name": "STATUS_POSTPONED"}},
        "competitors": [{"homeAway": "home", "team": {"id": "17362"}, "score": "0"},
                        {"homeAway": "away", "team": {"id": "1"}, "score": "0"}]}]}]}
    (pp,) = parse_team_schedule(data, "usa.1")
    assert pp.is_finished and not pp.is_result and pp.outcome_for("17362") is None


def test_pick_recent_one_per_team_within_lookback():
    c = cfg(teams=[TeamConfig(name="Minnesota", espn_id="17362"),
                   TeamConfig(name="Arsenal", espn_id="359"),
                   TeamConfig(name="Liverpool", espn_id="364")])
    now = ct(21, 12)
    old = mk("old", ct(14, 19), "post", (0, 2))
    new = mk("new", ct(18, 19), "post", (2, 1))
    too_old = mk("ars-old", now - timedelta(days=15), "post", (1, 0), comp=EPL, home="ars", away="che")
    derby = mk("liv-ars", ct(20, 9), "post", (1, 1), comp=EPL, home="liv", away="ars")
    upcoming = mk("next", ct(22, 19))
    got = pick_recent([old, new, too_old, derby, upcoming], c, now)
    assert [m.id for m in got] == ["new", "liv-ars"]                  # config order, no repeats
    assert pick_recent([new], cfg(recent_days=0), now) == []


class _Provider:
    def __init__(self, matches, results):
        self._m, self._r = matches, results

    def matches(self, *a):
        return list(self._m)

    def team_schedule(self, *a, **k):
        return []

    def team_results(self, *a, **k):
        return list(self._r)


def test_service_adds_last_strip_and_hides_the_featured_result():
    c = cfg()
    now = ct(21, 23)
    older = mk("older", ct(14, 19), "post", (1, 3), home="stl", away="min")
    sched_copy = SAT_RESULT()
    sched_copy.home_score = 1   # stale copy in the team schedule; the scoreboard's 2–1 wins
    upcoming = [mk(f"u{i}", ct(22 + i, 14), comp=EPL, home="liv", away="ars") for i in range(7)]
    svc = Service(c, provider=_Provider([SAT_RESULT(), *upcoming], [older, sched_copy]))
    b = svc.board(now)
    assert b.featured.id == "res" and b.recent == []                  # featured: not shown twice
    later = ct(23, 7)                                                 # hold over (Monday 06:00)
    b = svc.board(later)
    assert b.featured.id == "u1"   # u0 (Sunday) is past its window by Monday morning
    assert [m.id for m in b.recent] == ["res"] and b.recent[0].home_score == 2
    assert len(b.upcoming) == list_layout(5, 1)[0] == 4               # one row given to LAST


def test_etag_changes_with_the_last_result_only():
    c = cfg()
    svc = Service(c, provider=object())
    b = sample_board("s1", NOW)
    e1 = svc.render(b, NOW).etag
    assert svc.render(b, NOW + timedelta(minutes=30)).etag == e1
    b.recent[0].away_score = 2                                        # score corrected
    e2 = svc.render(b, NOW).etag
    assert e2 != e1
    b.recent = sample_recent(NOW) + [mk("x", ct(1, 9), "post", (0, 1), comp=EPL, home="liv", away="ars")]
    assert svc.render(b, NOW).etag not in (e1, e2)
    no_last = sample_board("s1", NOW, recent=False)
    assert svc.render(no_last, NOW).etag != e1


def test_list_layout_makes_room_for_last_rows():
    assert list_layout(5, 0) == (5, 0)
    assert list_layout(5, 1) == (4, 1)
    assert list_layout(5, 2) == (3, 2)
    assert list_layout(5, 5) == (3, 3)
    assert list_layout(0, 2) == (0, 2)


@pytest.mark.parametrize("layout", ["sunburst", "diagonal", "deco"])
def test_render_with_several_results(layout):
    c = cfg(teams=[TeamConfig(name="Minnesota", espn_id="17362"), TeamConfig(name="Arsenal", espn_id="359")])
    b = sample_board("s1", NOW)
    b.recent = sample_recent(NOW) + [mk("p", ct(1, 9), "post", (0, 0), home="lafc", away="min", winner="home")]
    f = Service(c, provider=object()).render(b, NOW, layout=layout)
    im = Image.open(__import__("io").BytesIO(f.png))
    assert {c for _, c in im.getcolors()} <= set(COLORS.values())


# --- column modes (match day = daily_at to daily_at) -----------------------------------
from soccer_wallart.data.models import Competition  # noqa: E402
from soccer_wallart.selection import match_day  # noqa: E402

UCL_C = Competition("uefa.champions", "UEFA Champions League")


def epl(mid, kickoff, state="pre", score=None, home="liv", away="ars"):
    return mk(mid, kickoff, state, score, comp=EPL, home=home, away=away)


def ids(ms):
    return [m.id for m in ms]


def test_match_day_runs_from_daily_refresh_to_daily_refresh():
    c = cfg()
    assert match_day(c, ct(21, 23)) == (ct(21, 6), ct(22, 6))
    assert match_day(c, ct(22, 1)) == (ct(21, 6), ct(22, 6))       # after midnight: same day
    assert match_day(c, ct(22, 5, 57)) == (ct(22, 6), ct(23, 6))   # the 06:00 wake, early


def test_mode_today_lists_games_to_come_then_results():
    c = cfg()
    ms = [epl("e9", ct(21, 9), "post", (2, 1)), epl("e11", ct(21, 11, 30)), epl("e14", ct(21, 14)),
          mk("min", ct(21, 19, 30)), epl("sun", ct(22, 8))]
    b = build_board(ms, c, ct(21, 10, 30))
    assert b.featured.id == "min"                                    # team priority, as before
    assert b.mode == "today"
    assert ids(b.upcoming) == ["e11", "e14"]                         # no padding with Sunday
    assert ids(b.results) == ["e9"]


def test_mode_today_includes_a_game_just_after_midnight():
    c = cfg()
    ms = [epl("late", ct(22, 0, 30)), mk("min", ct(22, 18)), epl("e9", ct(21, 9), "post", (0, 0))]
    b = build_board(ms, c, ct(21, 23))
    assert b.mode == "today" and ids(b.upcoming) == ["late"] and ids(b.results) == ["e9"]
    late = ms[0]
    late.state, late.home_score, late.away_score = "post", 1, 1
    b = build_board(ms, c, ct(22, 2, 30))                             # it ended at 2:25 AM
    assert b.mode == "results" and ids(b.results) == ["late", "e9"]


def test_mode_results_after_the_last_game_then_next_up_at_0600():
    c = cfg()
    ms = [epl("e12", ct(21, 12), "post", (1, 0)), epl("e14", ct(21, 14), "post", (3, 3)),
          mk("min", ct(21, 19, 30)), epl("mon", ct(23, 14))]
    # MIN is on the poster, so the column has nothing left to come today: results, newest first.
    b = build_board(ms, c, ct(21, 15, 55))
    assert b.featured.id == "min" and b.mode == "results" and ids(b.results) == ["e14", "e12"]
    assert b.upcoming == []
    # The full-time wake of the last game: MIN's result joins the poster (held), column unchanged.
    ms[2].state, ms[2].home_score, ms[2].away_score = "post", 2, 0
    b = build_board(ms, c, ct(21, 21, 25))
    assert b.featured.id == "min" and b.mode == "results" and ids(b.results) == ["e14", "e12"]
    # Until the 06:00 refresh (a wake it already does), then NEXT UP.
    assert build_board(ms, c, ct(22, 5, 50)).mode == "results"
    for t in (ct(22, 5, 57), ct(22, 6)):
        b = build_board(ms, c, t)
        assert b.mode == "next" and b.results == [] and ids(b.upcoming) == ["mon"]
    # The 21:25 wake goes straight to Sunday's 06:00 refresh: no wake for the mode switch.
    t = ct(21, 21, 25)
    assert next_wake_seconds(build_board(ms, c, t), c, t) == int((ct(22, 6) - t).total_seconds())


def test_mode_today_overflow_shows_the_soonest_five():
    c = cfg()
    ms = [epl(f"g{h}", ct(21, h)) for h in range(9, 22, 2)]           # 7 games today
    b = build_board(ms, c, ct(21, 7))
    assert b.mode == "today" and len(b.upcoming) == 5 and b.results == []
    assert ids(b.upcoming) == [f"g{h}" for h in range(11, 20, 2)]   # g9 is on the poster


def test_mode_results_mixes_own_team_and_league_results():
    c = cfg()
    ms = [mk("min", ct(21, 13), "post", (1, 2), home="min", away="stl"),
          epl("e15", ct(21, 15), "post", (2, 2)), epl("e11", ct(21, 11), "post", (0, 1)),
          mk("ucl", ct(24, 14), comp=UCL_C, home="psg", away="bar")]
    t = ct(21, 23)
    b = build_board(ms, c, t)
    # The held EPL result is outranked by the Champions League match (featured_priority), so
    # all of today's results, own team and league, go in the column, newest first.
    assert b.mode == "results" and b.featured.id == "ucl"
    assert ids(b.results) == ["e15", "min", "e11"]
    assert ms[0].outcome_for("17362") == "L"
    for layout in ("sunburst", "deco"):
        f = Service(c, provider=object()).render(b, t, layout=layout)
        im = Image.open(__import__("io").BytesIO(f.png))
        assert {col for _, col in im.getcolors()} <= set(COLORS.values())


def test_mode_next_when_nothing_today():
    c = cfg()
    ms = [epl("sun", ct(22, 8)), epl("mon", ct(23, 14))]
    b = build_board(ms, c, ct(21, 7))
    assert b.mode == "next" and ids(b.upcoming) == ["mon"] and b.featured.id == "sun"


def test_wakes_cover_listed_games_today_and_the_featured_one():
    c = cfg()
    ms = [epl("e11", ct(21, 11, 30)), epl("e14", ct(21, 14)), mk("min", ct(21, 19, 30)),
          epl("sun", ct(22, 8))]
    t = ct(21, 10)
    b = build_board(ms, c, t)
    assert next_wake_seconds(b, c, t) == int((ct(21, 12, 25) - t).total_seconds())  # e11 halftime
    t = ct(21, 16, 30)                                                 # both EPL games done
    for m in ms[:2]:
        m.state, m.home_score, m.away_score = "post", 1, 0
    b = build_board(ms, c, t)
    assert b.mode == "results"
    assert next_wake_seconds(b, c, t) == int((ct(21, 20, 25) - t).total_seconds())  # MIN halftime


def test_service_column_modes_and_last_rows():
    c = cfg()
    res = [epl(f"r{h}", ct(21, h), "post", (1, h % 3)) for h in (9, 11, 13, 15, 17, 19)]
    later = [epl("mon", ct(23, 14))]
    older = mk("older", ct(14, 19), "post", (1, 3), home="stl", away="min")
    svc = Service(c, provider=_Provider(res + later, [older]))
    b = svc.board(ct(21, 22))
    assert b.mode == "results" and len(b.results) == 5 and b.recent == []   # no LAST band
    assert b.featured.id not in ids(b.results)
    b = svc.board(ct(22, 7))
    assert b.mode == "next" and ids(b.recent) == ["older"]


def test_etag_includes_mode_and_result_rows():
    c = cfg()
    svc = Service(c, provider=object())
    ms = [epl("e12", ct(21, 12), "post", (1, 0)), epl("e14", ct(21, 14), "post", (3, 3)),
          mk("min", ct(21, 19, 30))]
    t = ct(21, 16)
    e1 = svc.render(build_board(ms, c, t), t).etag
    assert svc.render(build_board(ms, c, ct(21, 16, 40)), ct(21, 16, 40)).etag == e1
    ms[1].away_score = 4
    assert svc.render(build_board(ms, c, t), t).etag != e1
    b = build_board(ms, c, t)
    b.mode = "next"
    assert svc.render(b, t).etag != svc.render(build_board(ms, c, t), t).etag


# --- live matches take the poster ---------------------------------------------------
def test_live_league_match_beats_higher_priority_days_away():
    c = cfg(teams=[])                    # featured_priority: teams, uefa.champions, eng.1
    ms = [epl("nas", ct(21, 11, 30), "in", (0, 0), home="che", away="ars"),
          mk("ucl", ct(24, 11, 45), comp=UCL_C, home="psg", away="bar")]
    b = build_board(ms, c, ct(21, 12))
    assert b.featured.id == "nas"
    assert "nas" not in ids(b.upcoming) + ids(b.results)
    # ESPN still saying "pre" a few minutes after kickoff doesn't move the poster.
    ms[0].state = "pre"
    assert build_board(ms, c, ct(21, 11, 33)).featured.id == "ucl"


def test_live_vs_live_uses_priority_then_kickoff():
    c = cfg()
    ms = [epl("e", ct(21, 11), "in", (0, 0)), mk("u", ct(21, 11, 30), "in", (1, 0), comp=UCL_C,
                                                  home="psg", away="bar"),
          mk("min", ct(21, 12), "in", (0, 0))]
    assert build_board(ms, c, ct(21, 12, 30)).featured.id == "min"   # teams first
    ms[2].state = "pre"
    ms[2].kickoff = ct(22, 12).astimezone(timezone.utc)
    assert build_board(ms, c, ct(21, 12, 30)).featured.id == "u"     # then uefa.champions
    ms[1].competition = EPL
    assert build_board(ms, c, ct(21, 12, 30)).featured.id == "e"     # same priority: earlier


def test_live_match_beats_held_result_then_becomes_the_held_result():
    c = cfg()
    held = mk("min", ct(21, 13), "post", (2, 0))
    live = epl("e", ct(21, 18), "in", (0, 0))
    nxt = epl("sun", ct(22, 9))
    ms = [held, live, nxt]
    b = build_board(ms, c, ct(21, 18, 55))
    assert b.featured.id == "e" and b.hold_until is None
    live.state, live.home_score, live.away_score = "post", 1, 1
    b = build_board(ms, c, ct(21, 19, 55))
    # MIN's hold ended when the next match (this one) came along; this one is now held.
    assert b.featured.id == "e" and b.hold_until == ct(22, 6)
    assert ids(b.results) == ["min"]


def test_latest_result_of_the_day_is_the_one_held():
    c = cfg(teams=[TeamConfig(name="Minnesota", espn_id="17362"), TeamConfig(name="Arsenal", espn_id="359")])
    ms = [epl("ars", ct(21, 9), "post", (0, 2), home="cry", away="ars"),
          epl("e11", ct(21, 11, 30), "post", (1, 1)),
          mk("min", ct(21, 19, 30), "post", (2, 1)), epl("tue", ct(24, 14))]
    b = build_board(ms, c, ct(21, 22))
    assert b.featured.id == "min" and b.hold_until == ct(23, 6)       # 48 h cap
    assert ids(b.results) == ["e11", "ars"]
