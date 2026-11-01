"""Fixture provider backed by ESPN's public (unofficial, keyless) site API.

Endpoints used:
  /apis/site/v2/sports/soccer/{league}/scoreboard?dates=YYYYMMDD   (one day per call; ranges 400)
  /apis/site/v2/sports/soccer/{league}/teams                        (team colors / id lookup)
  /apis/site/v2/sports/soccer/{league}/teams/{id}/schedule?fixture=true  (far-future fallback)
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

import httpx

from .cache import JsonCache
from .models import Competition, Match, Team

log = logging.getLogger(__name__)

BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"


def _parse_dt(s: str) -> datetime:
    # ESPN uses "2026-11-07T12:30Z" (no seconds) — fromisoformat handles both forms.
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def _score(v: Any) -> int | None:
    if v is None:
        return None
    if isinstance(v, dict):
        v = v.get("value", v.get("displayValue"))
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _team(t: dict, colors: dict[str, tuple[str | None, str | None]] | None = None) -> Team:
    tid = str(t.get("id"))
    color, alt = t.get("color"), t.get("alternateColor")
    if colors and tid in colors and not color:
        color, alt = colors[tid]
    return Team(
        id=tid,
        name=t.get("displayName") or t.get("name") or t.get("location") or "?",
        short_name=t.get("shortDisplayName") or t.get("displayName") or "?",
        abbreviation=t.get("abbreviation") or (t.get("displayName") or "???")[:3].upper(),
        color=color,
        alt_color=alt,
    )


def _event_to_match(ev: dict, comp: Competition, colors=None) -> Match | None:
    try:
        c = ev["competitions"][0]
        sides = {x["homeAway"]: x for x in c["competitors"]}
        home, away = sides["home"], sides["away"]
    except (KeyError, IndexError):
        return None
    status = (c.get("status") or ev.get("status") or {}).get("type", {})
    state = status.get("state", "pre")
    broadcasts: list[str] = []
    for b in c.get("broadcasts", []) or []:
        broadcasts.extend(b.get("names", []))
    return Match(
        id=str(ev["id"]),
        competition=comp,
        home=_team(home["team"], colors),
        away=_team(away["team"], colors),
        kickoff=_parse_dt(ev.get("date") or c["date"]),
        state=state,
        status_detail=status.get("shortDetail") or status.get("description") or "",
        home_score=_score(home.get("score")) if state != "pre" else None,
        away_score=_score(away.get("score")) if state != "pre" else None,
        venue=(c.get("venue") or {}).get("fullName"),
        broadcasts=broadcasts,
    )


def parse_scoreboard(data: dict, slug: str) -> list[Match]:
    league = (data.get("leagues") or [{}])[0]
    comp = Competition(slug=slug, name=league.get("name") or slug)
    out = []
    for ev in data.get("events", []):
        m = _event_to_match(ev, comp)
        if m:
            out.append(m)
    return out


def parse_team_schedule(data: dict, slug: str, colors=None, comp_name: str | None = None) -> list[Match]:
    comp = Competition(slug=slug, name=comp_name or slug)
    out = []
    for ev in data.get("events", []):
        m = _event_to_match(ev, comp, colors)
        if m:
            out.append(m)
    return out


def parse_teams(data: dict) -> list[dict]:
    try:
        return [t["team"] for t in data["sports"][0]["leagues"][0]["teams"]]
    except (KeyError, IndexError):
        return []


class EspnProvider:
    def __init__(self, cache: JsonCache, client: httpx.Client | None = None):
        self.cache = cache
        self.client = client or httpx.Client(timeout=15, headers={"User-Agent": "soccer-wallart/0.1"})

    def _get(self, url: str, params: dict | None = None, ttl_key: str | None = None) -> dict | None:
        key = ttl_key or (url + "?" + "&".join(f"{k}={v}" for k, v in sorted((params or {}).items())))
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        try:
            r = self.client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
        except (httpx.HTTPError, ValueError) as e:
            log.warning("ESPN request failed %s %s: %s", url, params, e)
            return self.cache.get(key, allow_stale=True)
        self.cache.set(key, data)
        return data

    def scoreboard(self, slug: str, day: date) -> list[Match]:
        data = self._get(f"{BASE}/{slug}/scoreboard", {"dates": day.strftime("%Y%m%d")})
        return parse_scoreboard(data, slug) if data else []

    def matches(self, slugs: Iterable[str], start: date, end: date) -> list[Match]:
        """All matches in the given leagues for days start..end inclusive, deduped."""
        seen: dict[str, Match] = {}
        for slug in slugs:
            d = start
            while d <= end:
                for m in self.scoreboard(slug, d):
                    seen.setdefault(m.id, m)
                d += timedelta(days=1)
        return sorted(seen.values(), key=lambda m: m.kickoff)

    def team_colors(self, slug: str) -> dict[str, tuple[str | None, str | None]]:
        data = self._get(f"{BASE}/{slug}/teams")
        return {str(t["id"]): (t.get("color"), t.get("alternateColor")) for t in parse_teams(data or {})}

    def team_schedule(self, slug: str, team_id: str, comp_name: str | None = None) -> list[Match]:
        data = self._get(f"{BASE}/{slug}/teams/{team_id}/schedule", {"fixture": "true"})
        if not data:
            return []
        return parse_team_schedule(data, slug, self.team_colors(slug), comp_name)

    def find_team(self, slug: str, query: str) -> list[dict]:
        q = query.lower()
        data = self._get(f"{BASE}/{slug}/teams")
        return [
            {"id": t["id"], "name": t.get("displayName"), "abbreviation": t.get("abbreviation")}
            for t in parse_teams(data or {})
            if q in (t.get("displayName") or "").lower() or q == (t.get("abbreviation") or "").lower()
        ]
