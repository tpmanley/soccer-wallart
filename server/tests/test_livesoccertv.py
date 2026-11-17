from datetime import datetime, timezone
from pathlib import Path

from soccer_wallart.data.cache import JsonCache
from soccer_wallart.data.livesoccertv import (
    LiveSoccerTV, Listing, find_listing, order_channels, parse_channels, parse_schedule)
from soccer_wallart.data.models import Competition, Match, Team

FIX = Path(__file__).parent / "fixtures"
SCHEDULE = (FIX / "lstv_schedule_20261122.html").read_text()
MATCH_PAGE = (FIX / "lstv_match_newcastle_arsenal.html").read_text()
EPL = Competition("eng.1", "English Premier League")


def team(id, name, short):
    return Team(id=id, name=name, short_name=short, abbreviation=short[:3].upper())


def match(home, away, kickoff, broadcasts=None, state="pre"):
    return Match(id=f"{home[0]}-{away[0]}", competition=EPL, home=team("1", *home), away=team("2", *away),
                 kickoff=kickoff, state=state, broadcasts=broadcasts or [])


LIV_MUN = match(("Liverpool", "Liverpool"), ("Manchester United", "Man United"),
                datetime(2026, 11, 22, 16, 30, tzinfo=timezone.utc))


def test_parse_schedule_rows():
    rows = parse_schedule(SCHEDULE)
    liv = next(r for r in rows if r.home == "Liverpool")
    assert liv.away == "Manchester United"
    assert liv.url == "/match/liverpool-vs-manchester-united/17y15"
    # 11:30am Eastern on the site; the row carries the absolute time.
    assert liv.kickoff == datetime(2026, 11, 22, 16, 30, tzinfo=timezone.utc)
    assert {r.home for r in rows} >= {"Chicago Fire", "Racing Santander", "Sassuolo"}


def test_parse_schedule_reads_unclassed_rows_and_skips_replays():
    rows = parse_schedule(SCHEDULE)
    # Some live rows have class="" rather than class="matchrow".
    city = next(r for r in rows if r.home == "Manchester City")
    assert city.away == "Fulham" and city.kickoff == datetime(2026, 11, 21, 12, 30, tzinfo=timezone.utc)
    # Re-airs ("repeatrow") are not the live broadcast.
    assert not any(r.home == "United States U17" for r in rows)


def test_parse_channels_for_country():
    assert parse_channels(MATCH_PAGE, "USA") == ["fuboTV", "USA Network", "Telemundo",
                                                  "Telemundo Deportes En Vivo"]
    assert "DAZN Canada" in parse_channels(MATCH_PAGE, "canada")
    assert parse_channels(MATCH_PAGE, "Narnia") == []


def test_parse_channels_falls_back_to_structured_data():
    # Without the coverage table, the schema.org data still names the US broadcasters.
    only_ld = MATCH_PAGE.split("<body>")[0]
    assert parse_channels(only_ld, "USA") == ["fuboTV", "USA Network", "Telemundo",
                                               "Telemundo Deportes En Vivo"]


def test_order_channels_puts_bundles_and_radio_last():
    assert order_channels(["fuboTV", "USA Network", "SiriusXM FC", "Telemundo"]) == \
        ["USA Network", "Telemundo", "fuboTV", "SiriusXM FC"]


def test_find_listing_matches_names_and_time():
    rows = parse_schedule(SCHEDULE)
    assert find_listing(LIV_MUN, rows).url == "/match/liverpool-vs-manchester-united/17y15"
    # Teams listed the other way round still match.
    swapped = match(("Manchester United", "Man United"), ("Liverpool", "Liverpool"), LIV_MUN.kickoff)
    assert find_listing(swapped, rows).url == "/match/liverpool-vs-manchester-united/17y15"


def test_find_listing_rejects_wrong_time_or_teams():
    rows = parse_schedule(SCHEDULE)
    two_hours_late = match(("Liverpool", "Liverpool"), ("Manchester United", "Man United"),
                           datetime(2026, 11, 22, 18, 30, tzinfo=timezone.utc))
    assert find_listing(two_hours_late, rows) is None
    wrong_teams = match(("Everton", "Everton"), ("Leeds United", "Leeds"), LIV_MUN.kickoff)
    assert find_listing(wrong_teams, rows) is None


def test_find_listing_tells_simultaneous_matches_apart():
    ko = datetime(2026, 11, 21, 15, 0, tzinfo=timezone.utc)
    rows = [Listing("/match/a", ko, "Brighton & Hove Albion", "Brentford"),
            Listing("/match/b", ko, "Wolverhampton Wanderers", "West Ham United"),
            Listing("/match/c", ko, "Nottingham Forest", "AFC Bournemouth")]
    m = match(("AFC Bournemouth", "Bournemouth"), ("Nottingham Forest", "Nottm Forest"), ko)
    assert find_listing(m, rows).url == "/match/c"
    m = match(("Brighton & Hove Albion", "Brighton"), ("Brentford", "Brentford"), ko)
    assert find_listing(m, rows).url == "/match/a"
    m = match(("Wolverhampton Wanderers", "Wolves"), ("West Ham United", "West Ham"), ko)
    assert find_listing(m, rows).url == "/match/b"


class FakeResponse:
    def __init__(self, text, status=200):
        self.text, self.status_code = text, status

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx
            raise httpx.HTTPStatusError("boom", request=None, response=None)


class FakeClient:
    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def get(self, url):
        self.calls.append(url)
        return FakeResponse(*self.pages.get(url, ("", 404)))


def test_fill_sets_broadcasts_only_where_espn_had_none(tmp_path):
    client = FakeClient({
        "https://www.livesoccertv.com/schedules/2026-11-22/": (SCHEDULE,),
        "https://www.livesoccertv.com/match/liverpool-vs-manchester-united/17y15": (MATCH_PAGE,),
    })
    lstv = LiveSoccerTV(JsonCache(tmp_path, 3600), "USA", client=client)
    ucl = match(("Arsenal", "Arsenal"), ("Dortmund", "Dortmund"),
                datetime(2026, 11, 24, 20, 0, tzinfo=timezone.utc), broadcasts=["Paramount+"])
    done = match(("Liverpool", "Liverpool"), ("Manchester United", "Man United"),
                 LIV_MUN.kickoff, state="post")
    liv = match(("Liverpool", "Liverpool"), ("Manchester United", "Man United"), LIV_MUN.kickoff)
    lstv.fill([ucl, done, liv])
    assert ucl.broadcasts == ["Paramount+"]           # ESPN's listing is kept
    assert done.broadcasts == []                       # finished matches aren't looked up
    assert liv.broadcasts == ["USA Network", "Telemundo", "Telemundo Deportes En Vivo", "fuboTV"]
    # Parsed pages are cached: a second board build makes no new requests.
    n = len(client.calls)
    liv.broadcasts = []
    lstv.fill([liv])
    assert len(client.calls) == n and liv.broadcasts


def test_fill_survives_site_failures(tmp_path):
    lstv = LiveSoccerTV(JsonCache(tmp_path, 3600), "USA", client=FakeClient({}))
    liv = match(("Liverpool", "Liverpool"), ("Manchester United", "Man United"), LIV_MUN.kickoff)
    lstv.fill([liv])
    assert liv.broadcasts == []
