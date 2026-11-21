"""Choose the featured match + fixture list, and when the device should wake next."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from .config import Config
from .data.models import Match


WAKE_GRACE_MINUTES = 5


@dataclass
class Board:
    featured: Match | None
    upcoming: list[Match]
    generated_at: datetime
    # The LAST strip: each favourite team's latest result (never the featured match itself).
    recent: list[Match] = field(default_factory=list)
    # When the featured match is a held result: the moment it gives way to the next match.
    hold_until: datetime | None = None
    # What the right-hand column shows (see column_mode):
    #   "today"    today's games still to come (upcoming), then today's results to fill rows
    #   "results"  no games left today: today's results only
    #   "next"     nothing today: NEXT UP fixtures, plus the per-team LAST rows (recent)
    mode: str = "next"
    # Today's finished games listed in the column ("today" and "results" modes), newest first.
    results: list[Match] = field(default_factory=list)


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


def _daily(cfg: Config, day: date) -> datetime:
    """The daily_at refresh on a local calendar day."""
    hh, mm = (int(x) for x in cfg.refresh.daily_at.split(":"))
    return datetime.combine(day, time(hh, mm), tzinfo=cfg.tz)


def hold_end(m: Match, matches: list[Match], cfg: Config) -> datetime:
    """When a finished match stops being featured.

    next_match_day: the daily_at refresh on the local day of the next relevant match (the next
    kickoff after this one, even if that game has since finished), or hold_before_kickoff_hours before its kickoff if that's earlier. At most
    result_hold_max_hours after kickoff (rounded down to a daily_at refresh, which the frame
    wakes for anyway) and at least after_match_minutes.
    """
    r = cfg.refresh
    floor = m.kickoff + timedelta(minutes=r.after_match_minutes)
    if r.result_hold == "fixed" or not m.is_result:
        return floor
    cap = m.kickoff + timedelta(hours=r.result_hold_max_hours)
    end = _daily(cfg, cap.astimezone(cfg.tz).date())
    if end > cap:
        end = _daily(cfg, cap.astimezone(cfg.tz).date() - timedelta(days=1))
    # The next match after this one, finished or not (once it has kicked off, the next match
    # day has come), but not one that was postponed.
    nxt = min((x for x in matches
               if x.id != m.id and x.kickoff > m.kickoff and _relevant(x, cfg)
               and not (x.is_finished and not x.completed)),
              key=lambda x: x.kickoff, default=None)
    if nxt is not None:
        end = min(end, _daily(cfg, nxt.kickoff.astimezone(cfg.tz).date()),
                  nxt.kickoff - timedelta(hours=r.hold_before_kickoff_hours))
    return max(floor, end)


def match_day(cfg: Config, now: datetime) -> tuple[datetime, datetime]:
    """The match day `now` falls in: from one daily_at refresh to the next, so a game that
    kicks off at 12:30 AM belongs to the evening before. A wake a few minutes early (clock
    drift) for the daily refresh already counts as the new day."""
    local = (now + timedelta(minutes=WAKE_GRACE_MINUTES)).astimezone(cfg.tz)
    start = _daily(cfg, local.date())
    if start > local:
        start = _daily(cfg, local.date() - timedelta(days=1))
    return start, _daily(cfg, start.date() + timedelta(days=1))


def _still_shown(m: Match, matches: list[Match], cfg: Config, now: datetime) -> bool:
    if not m.is_finished:
        # Live games stay however long they run; ones ESPN never updates drop off eventually.
        return m.is_live or m.kickoff + timedelta(minutes=cfg.refresh.after_match_minutes) >= now
    end = hold_end(m, matches, cfg)
    if cfg.refresh.result_hold == "fixed":
        return end >= now
    # The frame is woken for `end`, and its clock can run a few minutes fast; that wake
    # must already see the hold as over.
    return now + timedelta(minutes=WAKE_GRACE_MINUTES) < end


def build_board(matches: list[Match], cfg: Config, now: datetime) -> Board:
    """`now` must be timezone-aware."""
    horizon = now + timedelta(days=cfg.lookahead_days)
    window = [
        m for m in matches
        if _relevant(m, cfg) and m.kickoff <= horizon and _still_shown(m, matches, cfg, now)
    ]
    window.sort(key=lambda m: m.kickoff)

    featured = None
    if window:
        live = [m for m in window if m.is_live]
        if live:
            # A live match takes the poster over anything that isn't live, held results
            # included; featured_priority (then kickoff) only decides between live matches.
            featured = min(live, key=lambda m: (_priority(m, cfg), m.kickoff))
        else:
            # Otherwise the earliest match of the best priority (a held result counts).
            featured = min(window, key=lambda m: (_priority(m, cfg), m.kickoff))
            if _priority(featured, cfg) == len(cfg.featured_priority):
                featured = window[0]

    rest = [m for m in window if featured is None or m.id != featured.id]
    # Finished games drop out of the list (they only linger as the featured result).
    rest = [m for m in rest if not m.is_finished]
    hold_until = None
    if featured is not None and featured.is_finished and cfg.refresh.result_hold != "fixed":
        hold_until = hold_end(featured, matches, cfg)
    board = Board(featured=featured, upcoming=rest[: cfg.list_size], generated_at=now,
                  hold_until=hold_until)
    _fill_column(board, matches, cfg, now)
    return board


def _fill_column(board: Board, matches: list[Match], cfg: Config, now: datetime) -> None:
    """Choose the column mode for the current match day (never repeating the featured match):

    1. "today":   games still to come today, soonest first; leftover rows get today's
                  results, newest first. No padding with tomorrow's fixtures.
    2. "results": no games left today but some finished: today's results, newest first.
    3. "next":    no games today: NEXT UP as usual (build_board's `upcoming`).
    """
    start, end = match_day(cfg, now)
    fid = board.featured.id if board.featured else None
    today = [m for m in matches
             if _relevant(m, cfg) and start <= m.kickoff < end and m.id != fid]
    # Same rule as the window: a "pre" game ESPN never updates drops off eventually.
    to_come = sorted((m for m in today if not m.is_finished and _still_shown(m, matches, cfg, now)),
                     key=lambda m: m.kickoff)
    done = sorted((m for m in today if m.is_result), key=lambda m: m.kickoff, reverse=True)
    n = cfg.list_size
    if to_come:
        board.mode, board.upcoming = "today", to_come[:n]
        board.results = done[: n - len(board.upcoming)]
    elif done:
        board.mode, board.upcoming, board.results = "results", [], done[:n]
    else:
        board.mode, board.results = "next", []


def team_perspective(m: Match, cfg: Config) -> str:
    """The favourite team a result is told from: the first configured team that played."""
    return next((t.espn_id for t in cfg.teams if t.espn_id in m.team_ids), m.home.id)


def pick_recent(results: list[Match], cfg: Config, now: datetime) -> list[Match]:
    """Each configured team's latest result within recent_days, in config order, one per match."""
    if cfg.recent_days <= 0:
        return []
    since = now - timedelta(days=cfg.recent_days)
    out: list[Match] = []
    for team in cfg.teams:
        mine = [m for m in results
                if team.espn_id in m.team_ids and m.is_result and since <= m.kickoff <= now]
        if mine:
            last = max(mine, key=lambda m: m.kickoff)
            if all(last.id != o.id for o in out):
                out.append(last)
    return out


def next_wake_seconds(board: Board, cfg: Config, now: datetime) -> int:
    """Seconds until the display should next refresh."""
    r = cfg.refresh
    local = now.astimezone(cfg.tz)
    daily = _daily(cfg, local.date())
    if daily <= local + timedelta(minutes=WAKE_GRACE_MINUTES):   # (this is the daily wake, early)
        daily = _daily(cfg, local.date() + timedelta(days=1))
    candidates = [daily]
    # A held result gives way to the next match at hold_until. That's usually the daily
    # refresh anyway; otherwise (an early kickoff, a second match the same day) wake for it.
    if board.hold_until is not None:
        candidates.append(board.hold_until)

    matches = ([board.featured] if board.featured else []) + board.upcoming
    for m in matches:
        if m.is_finished:
            continue
        halftime = m.kickoff + timedelta(minutes=r.halftime_minutes)
        fulltime = m.kickoff + timedelta(minutes=r.fulltime_minutes)
        candidates += [halftime, fulltime]
        # ESPN can still say "pre" a little after kickoff, so go by the clock as well as the state.
        if now >= fulltime and (m.is_live or m.kickoff <= now):
            candidates.append(now + timedelta(minutes=r.live_minutes))
    # The frame's clock drifts, so it can wake a minute or two before the time it was given.
    # A wake that's that close counts as reached; otherwise it would sleep the 15-minute
    # minimum and miss halftime.
    soon = now + timedelta(minutes=WAKE_GRACE_MINUTES)
    future = [c for c in candidates if c > soon]
    wake = min(future) if future else daily
    secs = int((wake - now).total_seconds())
    return max(r.min_minutes * 60, min(secs, int(r.max_hours * 3600)))
