"""Display metadata for competitions (ESPN league slugs)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CompStyle:
    title: str   # poster banner, e.g. "PREMIER LEAGUE"
    tag: str     # short tag for the fixture list, e.g. "EPL"
    color: str   # Spectra 6 color name for the tag


COMPETITIONS: dict[str, CompStyle] = {
    "eng.1": CompStyle("PREMIER LEAGUE", "EPL", "red"),
    "eng.fa": CompStyle("FA CUP", "FAC", "red"),
    "eng.league_cup": CompStyle("CARABAO CUP", "EFL", "green"),
    "esp.1": CompStyle("LA LIGA", "LIGA", "yellow"),
    "ger.1": CompStyle("BUNDESLIGA", "BUND", "red"),
    "ita.1": CompStyle("SERIE A", "SERA", "blue"),
    "fra.1": CompStyle("LIGUE 1", "L1", "blue"),
    "usa.1": CompStyle("MAJOR LEAGUE SOCCER", "MLS", "green"),
    "usa.open": CompStyle("U.S. OPEN CUP", "USOC", "red"),
    "usa.nwsl": CompStyle("NWSL", "NWSL", "blue"),
    "uefa.champions": CompStyle("CHAMPIONS LEAGUE", "UCL", "blue"),
    "uefa.europa": CompStyle("EUROPA LEAGUE", "UEL", "yellow"),
    "uefa.europa.conf": CompStyle("CONFERENCE LEAGUE", "UECL", "green"),
    "concacaf.champions": CompStyle("CONCACAF CHAMPIONS CUP", "CCC", "blue"),
    "concacaf.leagues.cup": CompStyle("LEAGUES CUP", "LC", "yellow"),
    "fifa.world": CompStyle("WORLD CUP", "WC", "red"),
    "fifa.friendly": CompStyle("INTERNATIONAL FRIENDLY", "INTL", "black"),
}


def style_for(slug: str, fallback_name: str | None = None) -> CompStyle:
    if slug in COMPETITIONS:
        return COMPETITIONS[slug]
    name = (fallback_name or slug).upper()
    tag = "".join(w[0] for w in name.split() if w[:1].isalpha())[:4] or slug[:4].upper()
    return CompStyle(name, tag, "black")


# Named rivalries → ribbon text. Keys are frozensets of ESPN team ids.
DERBIES: dict[frozenset[str], str] = {
    frozenset({"83", "86"}): "EL CLÁSICO",              # Barcelona / Real Madrid
    frozenset({"86", "1068"}): "DERBI MADRILEÑO",       # Real Madrid / Atlético
    frozenset({"364", "368"}): "MERSEYSIDE DERBY",      # Liverpool / Everton
    frozenset({"359", "367"}): "NORTH LONDON DERBY",    # Arsenal / Tottenham
    frozenset({"360", "382"}): "MANCHESTER DERBY",      # Man United / Man City
    frozenset({"360", "364"}): "NORTH WEST DERBY",      # Man United / Liverpool
    frozenset({"110", "111"}): "DERBY D'ITALIA",        # Inter / Juventus
    frozenset({"103", "110"}): "DERBY DELLA MADONNINA", # Inter / AC Milan
    frozenset({"124", "132"}): "DER KLASSIKER",         # Dortmund / Bayern
}


def derby_name(home_id: str, away_id: str) -> str | None:
    return DERBIES.get(frozenset({home_id, away_id}))
