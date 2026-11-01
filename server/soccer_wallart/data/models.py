from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Team:
    id: str
    name: str            # "Minnesota United FC"
    short_name: str      # "Minnesota"
    abbreviation: str    # "MIN"
    color: str | None = None      # hex without '#', ESPN "color"
    alt_color: str | None = None  # hex without '#', ESPN "alternateColor"


@dataclass(frozen=True)
class Competition:
    slug: str            # "eng.1"
    name: str            # "English Premier League"


@dataclass
class Match:
    id: str
    competition: Competition
    home: Team
    away: Team
    kickoff: datetime    # timezone-aware UTC
    state: str = "pre"   # pre | in | post
    status_detail: str = ""
    home_score: int | None = None
    away_score: int | None = None
    venue: str | None = None
    broadcasts: list[str] = field(default_factory=list)

    @property
    def team_ids(self) -> set[str]:
        return {self.home.id, self.away.id}

    @property
    def is_live(self) -> bool:
        return self.state == "in"

    @property
    def is_finished(self) -> bool:
        return self.state == "post"
