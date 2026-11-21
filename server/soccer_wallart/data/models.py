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
    # Finished matches only: "home"/"away" when ESPN flags a winner (it does for shootouts,
    # where the score is level), and False for "post" games that never finished (postponed).
    winner: str | None = None
    completed: bool = True

    @property
    def team_ids(self) -> set[str]:
        return {self.home.id, self.away.id}

    @property
    def is_live(self) -> bool:
        return self.state == "in"

    @property
    def is_finished(self) -> bool:
        return self.state == "post"

    @property
    def is_result(self) -> bool:
        """Finished with a final score (not postponed or abandoned)."""
        return self.is_finished and self.completed and self.home_score is not None \
            and self.away_score is not None

    def outcome_for(self, team_id: str) -> str | None:
        """"W", "D" or "L" from that team's point of view; a shootout counts as W/L."""
        if not self.is_result or team_id not in self.team_ids:
            return None
        home = team_id == self.home.id
        us, them = (self.home_score, self.away_score) if home else (self.away_score, self.home_score)
        if us != them:
            return "W" if us > them else "L"
        if self.winner:
            return "W" if (self.winner == "home") == home else "L"
        return "D"
