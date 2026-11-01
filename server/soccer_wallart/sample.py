"""Sample data for previews and the /gallery page (no network needed)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .data.models import Competition, Match, Team
from .selection import Board

EPL = Competition("eng.1", "English Premier League")
UCL = Competition("uefa.champions", "UEFA Champions League")
MLS = Competition("usa.1", "MLS")
LIGA = Competition("esp.1", "Spanish LALIGA")

T = {
    "rma": Team("86", "Real Madrid", "Real Madrid", "RMA", "ffffff", "1B4D3E"),
    "bar": Team("83", "Barcelona", "Barcelona", "BAR", "990000", "FCE38A"),
    "min": Team("17362", "Minnesota United FC", "Minnesota", "MIN", "000000", "9bcde4"),
    "lafc": Team("18966", "LAFC", "LAFC", "LAFC", "000000", "c39e6d"),
    "ars": Team("359", "Arsenal", "Arsenal", "ARS", "e20520", "003399"),
    "liv": Team("364", "Liverpool", "Liverpool", "LIV", "d11317", "FFFFFF"),
    "mci": Team("382", "Manchester City", "Man City", "MNC", "99c5ea", "000000"),
    "nfo": Team("393", "Nottingham Forest", "Nottm Forest", "NFO", "c8102e", "1B3624"),
    "dor": Team("124", "Borussia Dortmund", "Dortmund", "DOR", "ffee00", "272726"),
    "bet": Team("244", "Real Betis", "Betis", "BET", "288A00", "0A422D"),
    "che": Team("363", "Chelsea", "Chelsea", "CHE", "034694", "ffffff"),
    "tot": Team("367", "Tottenham Hotspur", "Spurs", "TOT", "ffffff", "0B1426"),
    "cry": Team("384", "Crystal Palace", "Crystal Palace", "CRY", "0202fb", "000000"),
    "psg": Team("160", "Paris Saint-Germain", "PSG", "PSG", "011F68", "ffffff"),
}


def sample_matches(now: datetime | None = None) -> list[Match]:
    now = now or datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
    d = lambda days, h, mnt=0: (now + timedelta(days=days)).replace(hour=h, minute=mnt, second=0, microsecond=0)
    return [
        Match("s1", LIGA, T["rma"], T["bar"], d(6, 20), venue="Santiago Bernabéu", broadcasts=["ESPN+"]),
        Match("s2", MLS, T["lafc"], T["min"], d(1, 1, 30), venue="BMO Stadium", broadcasts=["Apple TV"]),
        Match("s3", UCL, T["dor"], T["bet"], d(3, 20), venue="Signal Iduna Park"),
        Match("s4", EPL, T["liv"], T["ars"], d(0, 16, 30), venue="Anfield"),
        Match("s5", EPL, T["nfo"], T["mci"], d(6, 17, 30), venue="The City Ground"),
        Match("s6", EPL, T["tot"], T["che"], d(7, 14), venue="Tottenham Hotspur Stadium"),
        Match("s7", EPL, T["cry"], T["liv"], d(5, 15), venue="Selhurst Park"),
        Match("s8", UCL, T["psg"], T["bar"], d(2, 20), venue="Parc des Princes"),
    ]


def sample_board(featured_id: str = "s1", now: datetime | None = None) -> Board:
    now = now or datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
    ms = sorted(sample_matches(now), key=lambda m: m.kickoff)
    featured = next(m for m in ms if m.id == featured_id)
    return Board(featured=featured, upcoming=[m for m in ms if m.id != featured_id][:5], generated_at=now)
