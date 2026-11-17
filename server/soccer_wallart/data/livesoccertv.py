"""Fill in TV/streaming listings ESPN leaves blank, from livesoccertv.com.

ESPN publishes no US broadcasters for some competitions (notably the Premier League).
LiveSoccerTV does, per match and per country. We find the match on the site's daily
schedule page by kickoff time and team names, then read that country's row from the
match page's "International Coverage" table.

Pages are HTML, so this is best-effort: any failure just leaves a match's broadcasts empty.
"""
from __future__ import annotations

import html
import json
import logging
import platform
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher
from zoneinfo import ZoneInfo

import httpx

from .cache import JsonCache
from .models import Match

log = logging.getLogger(__name__)

BASE = "https://www.livesoccertv.com"
# The site lays out its daily schedules in US Eastern time.
SITE_TZ = ZoneInfo("America/New_York")
# A listing within this much of ESPN's kickoff counts as the same slot.
KICKOFF_SLACK = timedelta(minutes=30)
# Subscription bundles and radio: real, but never the answer to "which channel is it on?",
# so they go after the networks and services that actually carry the match.
_DEMOTE = ("fubo", "sling", "directv", "youtube tv", "hulu", "siriusxm", "vix", "radio")
# Words that don't help tell clubs apart ("Brighton & Hove Albion FC" vs "Brighton").
_FILLER = {"fc", "afc", "cf", "sc", "ac", "the", "and", "club", "de", "hove", "albion"}


@dataclass(frozen=True)
class Listing:
    url: str            # site path, e.g. /match/liverpool-vs-manchester-united/17y15
    kickoff: datetime   # timezone-aware UTC
    home: str
    away: str


def _norm_team(name: str) -> str:
    s = unicodedata.normalize("NFKD", html.unescape(name)).encode("ascii", "ignore").decode().lower()
    words = [w for w in re.findall(r"[a-z0-9]+", s) if w not in _FILLER]
    return " ".join(words)


def _team_score(listed: str, *espn_names: str) -> float:
    """How well a site team name matches any of ESPN's names for a team, 0..1."""
    a = _norm_team(listed)
    best = 0.0
    for n in espn_names:
        b = _norm_team(n)
        if not a or not b:
            continue
        if a == b or a.startswith(b + " ") or b.startswith(a + " "):
            return 1.0
        best = max(best, SequenceMatcher(None, a, b).ratio())
    return best


def parse_schedule(page: str) -> list[Listing]:
    """Every match row on a /schedules/YYYY-MM-DD/ (or competition) page."""
    out = []
    # Most rows are class="matchrow", but some are class="" — anything with a kickoff counts,
    # except "repeatrow" (re-airs of a match, at the wrong time and on the wrong channels).
    for cls, row in re.findall(r'<tr id="\d+" class="([^"]*)"([^>]*data-ko=.*?</tr>)', page, re.S):
        if "repeatrow" in cls:
            continue
        ko = re.search(r"dv='(\d+)'", row)
        link = re.search(r'<a href="(/match/[^"#]+)[^"]*" title="([^"]*)"', row)
        if not ko or not link:
            continue
        teams = html.unescape(link.group(2)).split(" vs ")
        if len(teams) != 2:
            continue
        kickoff = datetime.fromtimestamp(int(ko.group(1)) / 1000, tz=timezone.utc)
        out.append(Listing(link.group(1), kickoff, teams[0].strip(), teams[1].strip()))
    return out


def parse_channels(page: str, country: str = "USA") -> list[str]:
    """Channel names listed for `country` on a match page, in the site's order."""
    want = country.strip().lower()
    for row in re.findall(r"<tr><td[^>]*><span class=\"flag [^\"]*\">([^<]*)</span></td>(.*?)</tr>", page, re.S):
        if row[0].strip().lower() == want:
            return _dedupe(html.unescape(n).strip() for n in re.findall(r"<a [^>]*>([^<]+)</a>", row[1]))
    # Fallback: the schema.org data some pages carry for a subset of countries.
    names = []
    for blk in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S):
        try:
            graph = json.loads(blk).get("@graph", [])
        except (ValueError, AttributeError):
            continue
        for node in graph:
            if not isinstance(node, dict) or node.get("@type") != "BroadcastEvent":
                continue
            svc = node.get("publishedOn") or {}
            if ((svc.get("areaServed") or {}).get("name") or "").strip().lower() == want:
                names.append(svc.get("name") or "")
    return _dedupe(names)


def _dedupe(names) -> list[str]:
    out: list[str] = []
    for n in names:
        if n and n not in out:
            out.append(n)
    return out


def order_channels(names: list[str]) -> list[str]:
    """Networks and services first, bundles and radio last (stable otherwise)."""
    return sorted(names, key=lambda n: any(d in n.lower() for d in _DEMOTE))


def find_listing(match: Match, listings: list[Listing]) -> Listing | None:
    """The site's row for an ESPN match: kickoff within KICKOFF_SLACK and both teams matching."""
    best, best_score = None, 0.0
    for lst in listings:
        if abs(lst.kickoff - match.kickoff) > KICKOFF_SLACK:
            continue
        h = (match.home.name, match.home.short_name)
        a = (match.away.name, match.away.short_name)
        # The site sometimes lists the teams the other way round.
        score = max(min(_team_score(lst.home, *h), _team_score(lst.away, *a)),
                    min(_team_score(lst.home, *a), _team_score(lst.away, *h)))
        if score > best_score:
            best, best_score = lst, score
    return best if best_score >= 0.6 else None


class LiveSoccerTV:
    def __init__(self, cache: JsonCache, country: str = "USA", client: httpx.Client | None = None):
        self.cache = cache
        self.country = country
        self.client = client or httpx.Client(timeout=15, follow_redirects=True,
                                             headers={"User-Agent": f"python/{platform.python_version()}"})

    def _page(self, path: str, parse, key: str):
        """Fetch and parse a page, caching the parsed result; stale cache on failure."""
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        try:
            r = self.client.get(BASE + path)
            r.raise_for_status()
            value = parse(r.text)
        except (httpx.HTTPError, ValueError) as e:
            log.warning("LiveSoccerTV request failed %s: %s", path, e)
            return self.cache.get(key, allow_stale=True)
        self.cache.set(key, value)
        return value

    def schedule(self, day: date) -> list[Listing]:
        rows = self._page(f"/schedules/{day.isoformat()}/",
                          lambda t: [[l.url, l.kickoff.isoformat(), l.home, l.away] for l in parse_schedule(t)],
                          f"lstv:schedule:{day.isoformat()}")
        return [Listing(u, datetime.fromisoformat(k), h, a) for u, k, h, a in rows or []]

    def channels(self, url: str) -> list[str]:
        return self._page(url, lambda t: parse_channels(t, self.country),
                          f"lstv:channels:{self.country}:{url}") or []

    def broadcasts(self, match: Match) -> list[str]:
        """The channels carrying `match` in our country, or [] if it can't be found."""
        site_day = match.kickoff.astimezone(SITE_TZ).date()
        for day in (site_day, site_day - timedelta(days=1), site_day + timedelta(days=1)):
            listing = find_listing(match, self.schedule(day))
            if listing:
                return order_channels(self.channels(listing.url))
        log.info("LiveSoccerTV has no listing for %s v %s at %s",
                 match.home.short_name, match.away.short_name, match.kickoff)
        return []

    def fill(self, matches: list[Match]) -> None:
        """Set broadcasts on upcoming matches that ESPN left without any."""
        for m in matches:
            if m.broadcasts or m.is_finished:
                continue
            try:
                m.broadcasts = self.broadcasts(m)
            except Exception:  # an HTML change must never take the frame down
                log.exception("LiveSoccerTV lookup failed for match %s", m.id)
