"""Glue: fetch fixtures → build board → render → panel buffer."""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np

from .art.poster import render_board
from .competitions import style_for
from .config import Config
from .data.cache import JsonCache
from .data.espn import EspnProvider
from .data.livesoccertv import LiveSoccerTV
from .render import indices_to_png, pack_native, to_panel
from .selection import Board, build_board, next_wake_seconds

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
        # ESPN's scoreboard days are US-centric, so scan one day either side.
        matches = self.provider.matches(self.cfg.all_leagues(), local_today - timedelta(days=1),
                                        local_today + timedelta(days=self.cfg.lookahead_days + 1))
        board = build_board(matches, self.cfg, now)
        if board.featured is None or len(board.upcoming) < self.cfg.list_size:
            # International breaks and off-seasons leave the lookahead window (nearly) empty.
            # Fill the gaps with the favourite teams' next fixtures, even if they're weeks away.
            shown = {m.id for m in ([board.featured] if board.featured else []) + board.upcoming}
            later = [m for m in self._team_fixtures(now) if m.id not in shown]
            if board.featured is None and later:
                board.featured = later.pop(0)
            board.upcoming += later[: self.cfg.list_size - len(board.upcoming)]
        if self.listings:
            self.listings.fill(([board.featured] if board.featured else []) + board.upcoming)
        return board

    def _team_fixtures(self, now: datetime) -> list:
        """The favourite teams' upcoming fixtures from their full schedules, soonest first."""
        found = {}
        for team in self.cfg.teams:
            for slug in team.leagues:
                comp_name = style_for(slug).title.title()
                for m in self.provider.team_schedule(slug, team.espn_id, comp_name):
                    if m.state == "pre" and m.kickoff > now:
                        found.setdefault(m.id, m)
        return sorted(found.values(), key=lambda m: m.kickoff)

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
        sig += f"|{layout}|{self.cfg.display.rotate}|{battery_state(battery, self.cfg.display.low_battery_percent)}|{now.astimezone(self.cfg.tz).date()}"
        etag = hashlib.sha1(sig.encode()).hexdigest()[:16]
        return Frame(board, indices_to_png(idx), native, etag, next_wake_seconds(board, self.cfg, now))
