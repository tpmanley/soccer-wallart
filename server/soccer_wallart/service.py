"""Glue: fetch fixtures → build board → render → panel buffer."""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .art.poster import render_board
from .competitions import style_for
from .config import Config
from .data.cache import JsonCache
from .data.espn import EspnProvider
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


class Service:
    def __init__(self, cfg: Config, provider: EspnProvider | None = None):
        self.cfg = cfg
        self.provider = provider or EspnProvider(JsonCache(cfg.cache_dir, cfg.cache_ttl_minutes * 60))

    def board(self, now: datetime | None = None) -> Board:
        now = now or datetime.now(timezone.utc)
        local_today = now.astimezone(self.cfg.tz).date()
        # ESPN's scoreboard days are US-centric, so scan one day either side.
        matches = self.provider.matches(self.cfg.all_leagues(), local_today - timedelta(days=1),
                                        local_today + timedelta(days=self.cfg.lookahead_days + 1))
        board = build_board(matches, self.cfg, now)
        if board.featured is None:
            board.featured = self._next_team_fixture(now)
        return board

    def _next_team_fixture(self, now: datetime):
        """Off-season fallback: feature a favourite team's next fixture even if it's months away."""
        best = None
        for team in self.cfg.teams:
            for slug in team.leagues:
                comp_name = style_for(slug).title.title()
                for m in self.provider.team_schedule(slug, team.espn_id, comp_name):
                    if m.state == "pre" and m.kickoff > now and (best is None or m.kickoff < best.kickoff):
                        best = m
        return best

    def frame(self, now: datetime | None = None, layout: str | None = None, battery: int | None = None) -> Frame:
        now = now or datetime.now(timezone.utc)
        board = self.board(now)
        return self.render(board, now, layout, battery)

    def render(self, board: Board, now: datetime, layout: str | None = None, battery: int | None = None) -> Frame:
        design = render_board(board, self.cfg, now, layout=layout, battery=battery)
        idx = to_panel(design, self.cfg.display.width, self.cfg.display.height)
        native = pack_native(idx)
        # The ETag hashes the board *content* (plus the local date, since "TODAY"/"TOMORROW" labels
        # change at midnight) rather than the pixels, so the "updated" footer clock alone never
        # forces a slow e-ink refresh.
        sig = repr([(m.id, m.state, m.home_score, m.away_score, m.kickoff) for m in
                    ([board.featured] if board.featured else []) + board.upcoming])
        sig += f"|{layout}|{battery // 10 if battery is not None else None}|{now.astimezone(self.cfg.tz).date()}"
        etag = hashlib.sha1(sig.encode()).hexdigest()[:16]
        return Frame(board, indices_to_png(idx), native, etag, next_wake_seconds(board, self.cfg, now))
