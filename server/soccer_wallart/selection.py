"""Choose the featured match + fixture list, and when the device should wake next."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta

from .config import Config
from .data.models import Match


@dataclass
class Board:
    featured: Match | None
    upcoming: list[Match]
    generated_at: datetime


def _relevant(m: Match, cfg: Config) -> bool:
    if m.team_ids & cfg.team_ids:
        return True
    return m.competition.slug in cfg.leagues


def _priority(m: Match, cfg: Config) -> int:
    for i, key in enumerate(cfg.featured_priority):
        if key == "teams" and m.team_ids & cfg.team_ids:
            return i
        if key == m.competition.slug:
            return i
        if key == m.home.id or key == m.away.id:
            return i
    return len(cfg.featured_priority)


def build_board(matches: list[Match], cfg: Config, now: datetime) -> Board:
    """`now` must be timezone-aware."""
    keep_after = timedelta(minutes=cfg.refresh.after_match_minutes)
    horizon = now + timedelta(days=cfg.lookahead_days)
    window = [
        m for m in matches
        if _relevant(m, cfg) and m.kickoff + keep_after >= now and m.kickoff <= horizon
    ]
    window.sort(key=lambda m: m.kickoff)

    featured = None
    if window:
        # Live matches of the best priority win; otherwise the earliest of the best priority.
        featured = min(window, key=lambda m: (_priority(m, cfg), not m.is_live, m.kickoff))
        if _priority(featured, cfg) == len(cfg.featured_priority):
            featured = window[0]

    rest = [m for m in window if featured is None or m.id != featured.id]
    # Finished games drop out of the list (they only linger as the featured result).
    rest = [m for m in rest if not m.is_finished]
    return Board(featured=featured, upcoming=rest[: cfg.list_size], generated_at=now)


def next_wake_seconds(board: Board, cfg: Config, now: datetime) -> int:
    """Seconds until the display should next refresh."""
    r = cfg.refresh
    local = now.astimezone(cfg.tz)
    hh, mm = (int(x) for x in r.daily_at.split(":"))
    daily = datetime.combine(local.date(), time(hh, mm), tzinfo=cfg.tz)
    if daily <= local:
        daily += timedelta(days=1)
    candidates = [daily]

    matches = ([board.featured] if board.featured else []) + board.upcoming
    for m in matches:
        if m.is_live:
            candidates.append(now + timedelta(minutes=r.live_minutes))
        elif m.state == "pre":
            # Wake at kickoff (shows LIVE) and again once it's over (shows the result).
            candidates += [m.kickoff, m.kickoff + timedelta(minutes=r.after_match_minutes)]
        elif m.is_finished:
            candidates.append(m.kickoff + timedelta(minutes=r.after_match_minutes))
    future = [c for c in candidates if c > now]
    wake = min(future) if future else daily
    secs = int((wake - now).total_seconds())
    return max(r.min_minutes * 60, min(secs, int(r.max_hours * 3600)))
