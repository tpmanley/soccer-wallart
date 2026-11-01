from __future__ import annotations

import os
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from pydantic import BaseModel, Field, field_validator


class TeamConfig(BaseModel):
    name: str
    espn_id: str
    # Leagues/cups this team plays in; their scoreboards are scanned for the team's matches.
    leagues: list[str] = Field(default_factory=list)
    # Optional override of the poster colors, e.g. ["blue", "red"] (Spectra 6 color names).
    colors: list[str] | None = None

    @field_validator("espn_id", mode="before")
    @classmethod
    def _id_str(cls, v):
        return str(v)


class RefreshConfig(BaseModel):
    daily_at: str = "06:00"
    after_match_minutes: int = 150
    live_minutes: int = 30
    min_minutes: int = 15
    max_hours: float = 12


class DisplayConfig(BaseModel):
    width: int = 800
    height: int = 480
    clock: str = "12h"  # or "24h"


class Config(BaseModel):
    timezone: str = "America/Chicago"
    teams: list[TeamConfig] = Field(default_factory=list)
    leagues: list[str] = Field(default_factory=lambda: ["eng.1", "uefa.champions"])
    # Order used to choose the featured match. "teams" = any configured team.
    featured_priority: list[str] = Field(default_factory=lambda: ["teams"])
    list_size: int = 5
    lookahead_days: int = 7
    refresh: RefreshConfig = Field(default_factory=RefreshConfig)
    display: DisplayConfig = Field(default_factory=DisplayConfig)
    cache_dir: str = ".cache"
    cache_ttl_minutes: int = 60

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def team_ids(self) -> set[str]:
        return {t.espn_id for t in self.teams}

    def all_leagues(self) -> list[str]:
        seen: list[str] = []
        for slug in [*self.leagues, *(lg for t in self.teams for lg in t.leagues)]:
            if slug not in seen:
                seen.append(slug)
        return seen

    def team_color_overrides(self) -> dict[str, list[str]]:
        return {t.espn_id: t.colors for t in self.teams if t.colors}


def load_config(path: str | os.PathLike | None = None) -> Config:
    path = Path(path or os.environ.get("SOCCER_WALLART_CONFIG", "config.yaml"))
    if not path.exists():
        return Config()
    data = yaml.safe_load(path.read_text()) or {}
    return Config.model_validate(data)
