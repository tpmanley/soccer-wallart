from __future__ import annotations

from typing import Literal

import os
import re
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
    rotate: Literal[0, 180] = 0  # 180 if the frame hangs the other way up


# US over-the-air networks: free with an antenna, so they count as "available" by default.
FREE_NETWORKS = ["ABC", "CBS", "NBC", "FOX", "Telemundo", "Univision", "UniMás"]


def _norm(name: str) -> str:
    """'Paramount+' == 'paramount plus', 'Apple TV' == 'AppleTV'."""
    return re.sub(r"[^a-z0-9]", "", name.lower().replace("+", "plus"))


class WatchConfig(BaseModel):
    # Services you have, most preferred first, e.g. [Peacock, Apple TV, Paramount+].
    # Matched against ESPN's broadcast names ignoring case, spaces and punctuation.
    services: list[str] = Field(default_factory=list)
    # Also treat free over-the-air networks (FREE_NETWORKS) as available, after `services`.
    include_free: bool = True


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
    watch: WatchConfig = Field(default_factory=WatchConfig)
    # Relative paths are resolved against the directory containing config.yaml.
    cache_dir: str = ".cache"
    cache_ttl_minutes: int = 60

    @field_validator("timezone")
    @classmethod
    def _valid_tz(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as e:
            raise ValueError(f"unknown timezone {v!r} (use an IANA name like America/Chicago)") from e
        return v

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

    def pick_broadcast(self, broadcasts: list[str]) -> str | None:
        """The broadcast to show: your first-listed service carrying it, else a free network,
        else whatever ESPN lists first."""
        prefs = [*self.watch.services, *(FREE_NETWORKS if self.watch.include_free else [])]
        by_name = {_norm(b): b for b in reversed(broadcasts)}
        for p in prefs:
            if (hit := by_name.get(_norm(p))) is not None:
                return hit
        return broadcasts[0] if broadcasts else None

    def team_color_overrides(self) -> dict[str, list[str]]:
        return {t.espn_id: t.colors for t in self.teams if t.colors}


class ConfigError(RuntimeError):
    pass


def load_config(path: str | os.PathLike | None = None, required: bool = True) -> Config:
    """Load config.yaml. Path order: argument, $SOCCER_WALLART_CONFIG, ./config.yaml.

    A missing file is an error unless required=False (used by commands like `gallery`
    that work fine on defaults) — otherwise a typo in a volume mount would silently
    give you a board with none of your teams."""
    path = Path(path or os.environ.get("SOCCER_WALLART_CONFIG", "config.yaml")).expanduser()
    if not path.exists():
        if required:
            raise ConfigError(
                f"config file not found: {path.resolve()} — copy config.example.yaml there "
                "(in Docker: mount a folder containing config.yaml at /config)")
        return Config()
    try:
        data = yaml.safe_load(path.read_text()) or {}
        cfg = Config.model_validate(data)
    except (yaml.YAMLError, ValueError) as e:
        raise ConfigError(f"invalid config {path}: {e}") from e
    cache = Path(cfg.cache_dir).expanduser()
    if not cache.is_absolute():
        cfg.cache_dir = str((path.resolve().parent / cache))
    return cfg
