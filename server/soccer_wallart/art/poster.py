"""Compose the full 800x480 board: featured-match poster (left) + fixture list (right)."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from PIL import Image

from ..competitions import derby_name, style_for
from ..data.models import Match, Team
from . import motifs
from .canvas import Canvas
from .layouts import LAYOUTS, Kit
from .palette import accent, contrast_on, team_colors

PX0, PY0, PX1, PY1 = 10, 10, 530, 470      # poster
LX0, LX1 = 542, 790                         # list column
BANNER_B = 54
NAMES_T = 345
STRIP_T = 449


class Formatter:
    def __init__(self, tz: ZoneInfo, clock: str, now: datetime):
        self.tz, self.clock, self.now = tz, clock, now.astimezone(tz)

    def local(self, dt: datetime) -> datetime:
        return dt.astimezone(self.tz)

    def time(self, dt: datetime) -> str:
        t = self.local(dt)
        if self.clock == "24h":
            return t.strftime("%H:%M")
        return t.strftime("%I:%M %p").lstrip("0")

    def tz_abbr(self, dt: datetime) -> str:
        name = self.local(dt).tzname() or ""
        # "CST"/"CDT" -> "CT" style for US zones
        if len(name) == 3 and name[1] in "SD" and name.endswith("T"):
            return name[0] + "T"
        return name

    def day(self, dt: datetime, relative=True) -> str:
        t = self.local(dt)
        if relative:
            delta = (t.date() - self.now.date()).days
            if delta == 0:
                return "TODAY"
            if delta == 1:
                return "TOMORROW"
        return t.strftime("%a %-d %b").upper()

    def weekday(self, dt: datetime) -> str:
        return self.local(dt).strftime("%A").upper()


def _kit(team: Team, overrides) -> Kit:
    p, s = team_colors(team.id, team.color, team.alt_color, overrides)
    return Kit(team.id, team.abbreviation[:4], p, s)


def _name(team: Team) -> str:
    return team.name.upper()


def choose_layout(match: Match) -> str:
    names = sorted(LAYOUTS)
    return names[motifs.seed_of(match.id) % len(names)]


# ---------------------------------------------------------------------------
def draw_featured(c: Canvas, m: Match, fmt: Formatter, overrides, layout: str | None):
    home, away = _kit(m.home, overrides), _kit(m.away, overrides)
    comp = style_for(m.competition.slug, m.competition.name)
    art_box = (PX0, BANNER_B, PX1, NAMES_T)
    # Draw the art on its own layer and clip it, so motifs can't bleed into the type areas.
    art = c.layer("white")
    LAYOUTS[layout or choose_layout(m)](art, art_box, home, away)
    c.paste_rect(art, PX0, BANNER_B, PX1, NAMES_T)
    c.rect(PX0, PY0, PX1, BANNER_B, fill="black")

    # banner
    title = comp.title
    f, _ = c.fit(title, lambda s: c.geo(s, 800), 19, PX1 - PX0 - 30, spacing=3)
    c.text((PX0 + PX1) / 2, (PY0 + BANNER_B) / 2 + 1, title, f, "yellow", "mm", spacing=3)

    # ribbon: status > derby > relative day
    if m.is_live:
        rib, rib_fill = f"LIVE  {m.status_detail}".strip().upper(), "red"
    elif m.is_finished:
        rib, rib_fill = "FULL TIME", "black"
    else:
        rib = derby_name(m.home.id, m.away.id)
        rib_fill = "blue"
        if not rib:
            d = fmt.day(m.kickoff)
            rib = d if d in ("TODAY", "TOMORROW") else fmt.weekday(m.kickoff)
            if rib == "TODAY" and fmt.local(m.kickoff).hour >= 17:
                rib = "TONIGHT"
    if layout_ribbon_ok(layout or choose_layout(m)):
        motifs.ribbon(c, (PX0 + PX1) / 2, BANNER_B + 26, rib, fill=rib_fill)

    # name block
    c.rect(PX0, NAMES_T, PX1, PY1, fill="black")
    maxw = PX1 - PX0 - 30
    home_name, away_name = _name(m.home), _name(m.away)
    fh, sh = c.fit(home_name, c.slab, 38, maxw, min_size=20, spacing=1)
    fa, sa = c.fit(away_name, c.slab, 38, maxw, min_size=20, spacing=1)
    size = min(sh, sa)
    away_ink = accent(away.primary, away.secondary)
    if away_ink == "white":
        away_ink = "yellow"
    c.text((PX0 + PX1) / 2, NAMES_T + 30, home_name, c.slab(size), "white", "mm", spacing=1)
    if m.home_score is not None and m.away_score is not None:
        mid = f"{m.home_score}  —  {m.away_score}"
        c.text((PX0 + PX1) / 2, NAMES_T + 57, mid, c.geo(17, 800), "yellow", "mm", spacing=2)
    else:
        c.text((PX0 + PX1) / 2, NAMES_T + 57, "— VS —", c.geo(14, 700), "yellow", "mm", spacing=4)
    c.text((PX0 + PX1) / 2, NAMES_T + 84, away_name, c.slab(size), away_ink, "mm", spacing=1)

    # info strip
    c.rect(PX0, STRIP_T, PX1, PY1, fill="yellow")
    parts = [fmt.day(m.kickoff, relative=False), f"{fmt.time(m.kickoff)} {fmt.tz_abbr(m.kickoff)}"]
    if m.venue:
        parts.append(m.venue.upper())
    if m.broadcasts:
        parts.append(m.broadcasts[0].upper())
    while True:
        info = "  ·  ".join(parts)
        f, sz = c.fit(info, c.condensed, 19, PX1 - PX0 - 20, min_size=14, spacing=1)
        if sz > 14 or len(parts) <= 2:
            break
        parts.pop()
    c.text((PX0 + PX1) / 2, (STRIP_T + PY1) / 2 + 1, info, f, "black", "mm", spacing=1)
    c.rect(PX0, PY0, PX1, PY1, outline="black", width=3)


def layout_ribbon_ok(layout: str) -> bool:
    return layout != "diagonal"  # diagonal uses a VS medallion in that spot


def draw_empty(c: Canvas, fmt: Formatter):
    box = (PX0, BANNER_B, PX1, NAMES_T)
    from .layouts import sunburst as sb
    sb(c, box, Kit("x", "", "white", "black"), Kit("y", "", "white", "black"))
    # cover the shields: plain poster
    c.rect(PX0, PY0, PX1, BANNER_B, fill="black")
    c.text((PX0 + PX1) / 2, 33, "THE BEAUTIFUL GAME", c.geo(19, 800), "yellow", "mm", spacing=3)
    c.rect(PX0, NAMES_T, PX1, PY1, fill="black")
    c.text((PX0 + PX1) / 2, NAMES_T + 42, "NO MATCHES", c.slab(38), "white", "mm", spacing=1)
    c.text((PX0 + PX1) / 2, NAMES_T + 84, "THIS WEEK", c.slab(30), "yellow", "mm", spacing=1)
    c.rect(PX0, PY0, PX1, PY1, outline="black", width=3)


# ---------------------------------------------------------------------------
def draw_list(c: Canvas, matches: list[Match], fmt: Formatter, favorites: set[str], updated: datetime,
              battery: int | None = None):
    c.rect(LX0, PY0, LX1, BANNER_B, fill="red")
    c.text((LX0 + LX1) / 2, (PY0 + BANNER_B) / 2 + 1, "NEXT UP", c.slab(24), "white", "mm", spacing=3)
    y, row_h = 64, 78
    text_x = LX0 + 54
    maxw = LX1 - text_x
    if not matches:
        c.text((LX0 + LX1) / 2, 230, "NOTHING ELSE", c.condensed(26), "black", "mm", spacing=1)
        c.text((LX0 + LX1) / 2, 258, "ON THE SCHEDULE", c.condensed(26), "black", "mm", spacing=1)
    for i, m in enumerate(matches):
        st = style_for(m.competition.slug, m.competition.name)
        c.rect(LX0, y, LX0 + 44, y + 70, fill=st.color)
        tf, _ = c.fit(st.tag, c.condensed, 22, 40)
        c.text(LX0 + 22, y + 36, st.tag, tf, contrast_on(st.color), "mm")
        if m.is_live:
            when, when_ink = f"LIVE {m.status_detail}  ·  {m.home_score}-{m.away_score}", "red"
        else:
            when, when_ink = f"{fmt.day(m.kickoff)}  ·  {fmt.time(m.kickoff)}", "red"
        c.text(text_x, y + 4, when, c.condensed(18), when_ink, "la", spacing=0.5)
        for j, (prefix, team) in enumerate((("", m.home), ("vs ", m.away))):
            label = team.short_name.upper()
            ink = "blue" if team.id in favorites else "black"
            f, sz = c.fit(prefix + label, lambda s: c.geo(s, 700), 16, maxw, min_size=12)
            if sz <= 12 and c.text_width(prefix + label, f) > maxw:
                label = team.abbreviation
            c.text(text_x, y + 24 + j * 22, prefix + label, f, ink, "la")
        y += row_h
        if i < len(matches) - 1:
            c.rect(text_x, y - 6, LX1, y - 4.5, fill="black")
    c.rect(LX0, 456, LX1, PY1, fill="black")
    foot = f"UPDATED {fmt.day(updated, relative=False)} {fmt.time(updated)}"
    if battery is not None:
        foot += f"  ·  BATT {battery}%"
    c.text((LX0 + LX1) / 2, 463.5, foot, c.condensed(13), "white", "mm", spacing=1)


def render_board(board, cfg, now: datetime | None = None, layout: str | None = None,
                 battery: int | None = None, scale: float = 3.0) -> Image.Image:
    """Return the full-resolution RGB design (not yet snapped to the panel palette)."""
    now = now or board.generated_at
    fmt = Formatter(cfg.tz, cfg.display.clock, now)
    c = Canvas(scale)
    if board.featured:
        draw_featured(c, board.featured, fmt, cfg.team_color_overrides(), layout)
    else:
        draw_empty(c, fmt)
    draw_list(c, board.upcoming, fmt, cfg.team_ids, board.generated_at, battery)
    return c.img
