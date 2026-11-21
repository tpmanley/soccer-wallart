"""Glue: fetch fixtures → build board → render → panel buffer."""
from __future__ import annotations

import hashlib
import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np

from .art.poster import list_layout, render_board
from .competitions import style_for
from .config import Config
from .data.cache import JsonCache
from .data.espn import EspnProvider
from .data.livesoccertv import LiveSoccerTV
from .render import indices_to_png, pack_native, to_panel
from .selection import Board, build_board, next_wake_seconds, pick_recent

log = logging.getLogger(__name__)


@dataclass
class Frame:
    board: Board
    png: bytes
    native: bytes
    etag: str
    sleep_seconds: int


def battery_state(battery: int | None, low_percent: int) -> str | None:
    """The part of the battery level that is allowed to force a redraw."""
    if battery is None:
        return None
    return "low" if battery < low_percent else "ok"


class Service:
    def __init__(self, cfg: Config, provider: EspnProvider | None = None,
                 listings: LiveSoccerTV | None = None):
        self.cfg = cfg
        cache = JsonCache(cfg.cache_dir, cfg.cache_ttl_minutes * 60)
        self.provider = provider or EspnProvider(cache)
        if listings is None and cfg.watch.livesoccertv:
            listings = LiveSoccerTV(cache, cfg.watch.country)
        self.listings = listings

    def board(self, now: datetime | None = None) -> Board:
        now = now or datetime.now(timezone.utc)
        local_today = now.astimezone(self.cfg.tz).date()
        # ESPN's scoreboard days are US-centric, so scan one day either side, and further back
        # for results that are still held on the poster.
        back = 1
        if self.cfg.refresh.result_hold != "fixed":
            back += math.ceil(self.cfg.refresh.result_hold_max_hours / 24)
        matches = self.provider.matches(self.cfg.all_leagues(), local_today - timedelta(days=back),
                                        local_today + timedelta(days=self.cfg.lookahead_days + 1))
        board = build_board(matches, self.cfg, now)
        if board.featured is None or (board.mode == "next" and len(board.upcoming) < self.cfg.list_size):
            # International breaks and off-seasons leave the lookahead window (nearly) empty.
            # Fill the gaps with the favourite teams' next fixtures, even if they're weeks away.
            # (Only NEXT UP is padded; the "today"/"results" columns are today's games only.)
            shown = {m.id for m in ([board.featured] if board.featured else []) + board.upcoming}
            later = [m for m in self._team_fixtures(now) if m.id not in shown]
            if board.featured is None and later:
                board.featured = later.pop(0)
            if board.mode == "next":
                board.upcoming += later[: self.cfg.list_size - len(board.upcoming)]
        if board.featured is not None:   # the fallback above may have featured a listed game
            board.upcoming = [m for m in board.upcoming if m.id != board.featured.id]
            board.results = [m for m in board.results if m.id != board.featured.id]
        if board.mode == "next":
            # Per-team LAST rows, only under NEXT UP: in the other modes the column already
            # lists today's results.
            recent = pick_recent(self._team_results(matches), self.cfg, now)
            if board.featured is not None:
                recent = [m for m in recent if m.id != board.featured.id]   # already on the poster
            # The LAST rows take space from NEXT UP. Trim both to what's drawn, so the ETag and
            # the halftime/full-time wakes only cover matches that are actually on the frame.
            n_up, n_recent = list_layout(len(board.upcoming), len(recent))
            board.upcoming, board.recent = board.upcoming[:n_up], recent[:n_recent]
        if self.listings:
            self.listings.fill(([board.featured] if board.featured else []) + board.upcoming)
        return board

    def _team_fixtures(self, now: datetime) -> list:
        """The favourite teams' upcoming fixtures from their full schedules, soonest first.
        (ESPN's `fixture=true` schedule has no past games; results come from _team_results.)"""
        found = {}
        for team in self.cfg.teams:
            for slug in team.leagues:
                comp_name = style_for(slug).title.title()
                for m in self.provider.team_schedule(slug, team.espn_id, comp_name):
                    if m.state == "pre" and m.kickoff > now:
                        found.setdefault(m.id, m)
        return sorted(found.values(), key=lambda m: m.kickoff)

    def _team_results(self, matches: list) -> list:
        """Finished games of the favourite teams: their season results, with the scoreboards'
        copies (fresher, right after full time) taking precedence."""
        if self.cfg.recent_days <= 0:
            return []
        found = {}
        for team in self.cfg.teams:
            for slug in team.leagues:
                comp_name = style_for(slug).title.title()
                for m in self.provider.team_results(slug, team.espn_id, comp_name):
                    found[m.id] = m
        found.update({m.id: m for m in matches if m.is_finished and m.team_ids & self.cfg.team_ids})
        return list(found.values())

    def frame(self, now: datetime | None = None, layout: str | None = None, battery: int | None = None) -> Frame:
        now = now or datetime.now(timezone.utc)
        board = self.board(now)
        return self.render(board, now, layout, battery)

    def render(self, board: Board, now: datetime, layout: str | None = None, battery: int | None = None) -> Frame:
        design = render_board(board, self.cfg, now, layout=layout, battery=battery)
        idx = to_panel(design, self.cfg.display.width, self.cfg.display.height)
        # Only the device buffer is rotated; /preview.png stays upright.
        native = pack_native(np.rot90(idx, 2) if self.cfg.display.rotate == 180 else idx)
        # The ETag hashes the board *content* (plus the local date, since "TODAY"/"TOMORROW" labels
        # change at midnight) rather than the pixels, so the "updated" footer clock alone never
        # forces a slow e-ink refresh. The battery only counts as low/ok: the fuel gauge jumps
        # around while charging and for a while after, and each jump would otherwise redraw.
        sig = repr([(m.id, m.state, m.home_score, m.away_score, m.kickoff,
                     self.cfg.pick_broadcast(m.broadcasts)) for m in
                    ([board.featured] if board.featured else []) + board.upcoming])
        # Column mode and the result rows it lists (left out for a plain NEXT UP column without
        # LAST rows, so those boards keep the ETag they had before).
        rows = [(m.id, m.state, m.home_score, m.away_score, m.winner) for m in board.results + board.recent]
        if board.mode != "next" or rows:
            sig += f"|{board.mode}:{rows!r}"
        sig += f"|{layout}|{self.cfg.display.rotate}|{battery_state(battery, self.cfg.display.low_battery_percent)}|{now.astimezone(self.cfg.tz).date()}"
        etag = hashlib.sha1(sig.encode()).hexdigest()[:16]
        return Frame(board, indices_to_png(idx), native, etag, next_wake_seconds(board, self.cfg, now))
