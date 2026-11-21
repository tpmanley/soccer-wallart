"""Compose the full 800x480 board: featured-match poster (left) + fixture list (right)."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from PIL import Image

from ..competitions import derby_name, style_for
from ..data.models import Match, Team
from ..selection import team_perspective
from . import motifs
from .canvas import Canvas
from .layouts import LAYOUTS, Kit
from .palette import accent, contrast_on, team_colors

PX0, PY0, PX1, PY1 = 10, 10, 530, 470      # poster
LX0, LX1 = 542, 790                         # list column
BANNER_B = 54
NAMES_T = 345
STRIP_T = 449
LIST_T, LIST_B = 64, 454                    # NEXT UP rows (footer below)
ROW_H, ROW_BOX = 78, 70                     # NEXT UP row pitch and tag-box height
LAST_HEAD, LAST_ROW, LAST_MAX = 20, 42, 3   # LAST section at the bottom of the list column
LAST_ROW_MAX = 54                           # LAST rows grow into spare room up to this height
RESULT_INK = {"W": ("green", "white"), "D": ("yellow", "black"), "L": ("red", "white")}


def list_layout(n_upcoming: int, n_recent: int) -> tuple[int, int]:
    """How many NEXT UP rows and LAST rows fit in the list column.

    Without LAST rows NEXT UP is unchanged. LAST rows take room from the bottom: one result
    leaves four NEXT UP rows, two or three leave three. At least two NEXT UP rows stay."""
    if n_recent <= 0:
        return n_upcoming, 0
    n_recent = min(n_recent, LAST_MAX)
    while True:
        avail = LIST_B - LIST_T - (LAST_HEAD + n_recent * LAST_ROW)
        n_up = min(n_upcoming, int((avail + ROW_H - ROW_BOX) // ROW_H))
        if n_up >= min(2, n_upcoming) or n_recent == 1:
            return n_up, n_recent
        n_recent -= 1


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

    def month_day(self, dt: datetime) -> str:
        return self.local(dt).strftime("%b %-d").upper()  # "NOV 17"

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
def draw_featured(c: Canvas, m: Match, fmt: Formatter, overrides, layout: str | None,
                  broadcast: str | None = None):
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
    if broadcast:
        parts.append(broadcast.upper())
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
HEADERS = {"next": "NEXT UP", "today": "TODAY", "results": "TODAY'S RESULTS"}


def draw_list(c: Canvas, matches: list[Match], fmt: Formatter, favorites: set[str], updated: datetime,
              battery: int | None = None, pick_broadcast=lambda bs: bs[0] if bs else None,
              recent: list[Match] = (), perspective=lambda m: m.home.id,
              mode: str = "next", results: list[Match] = ()):
    """The right-hand column. `matches` are fixtures/live games, `results` today's finished games
    (modes "today"/"results"), `recent` the per-team LAST rows (mode "next" only)."""
    c.rect(LX0, PY0, LX1, BANNER_B, fill="red")
    head = HEADERS.get(mode, "NEXT UP")
    hf, _ = c.fit(head, c.slab, 24, LX1 - LX0 - 16, min_size=16, spacing=3)
    c.text((LX0 + LX1) / 2, (PY0 + BANNER_B) / 2 + 1, head, hf, "white", "mm", spacing=3)
    if mode != "next":
        recent = ()
    n_up, n_recent = list_layout(len(matches), len(recent))
    matches, recent = matches[:n_up], list(recent)[:n_recent]
    rows = [(m, False) for m in matches] + [(m, True) for m in results]
    if recent:
        up_bottom = LIST_T + max(0, n_up * ROW_H - (ROW_H - ROW_BOX))
        draw_recent(c, recent, perspective, fmt, max(up_bottom + 10, LIST_T + 140 if not matches else 0))
    if not rows:
        mid = 230 if not recent else (LIST_T + LIST_B - LAST_HEAD - n_recent * LAST_ROW) / 2 - 14
        c.text((LX0 + LX1) / 2, mid, "NOTHING ELSE", c.condensed(26), "black", "mm", spacing=1)
        c.text((LX0 + LX1) / 2, mid + 28, "ON THE SCHEDULE", c.condensed(26), "black", "mm", spacing=1)
    y = LIST_T
    for i, (m, is_result) in enumerate(rows):
        if is_result:
            _result_row(c, m, y, favorites, perspective)
        else:
            _fixture_row(c, m, y, fmt, favorites, pick_broadcast)
        y += ROW_H
        if i < len(rows) - 1:
            c.rect(LX0 + 54, y - 6, LX1, y - 4.5, fill="black")
    c.rect(LX0, 456, LX1, PY1, fill="black")
    foot = f"UPDATED {fmt.day(updated, relative=False)} {fmt.time(updated)}"
    if battery is not None:
        foot += f"  ·  BATT {battery}%"
    c.text((LX0 + LX1) / 2, 463.5, foot, c.condensed(13), "white", "mm", spacing=1)


def _fixture_row(c: Canvas, m: Match, y: float, fmt: Formatter, favorites: set[str], pick_broadcast):
    text_x = LX0 + 54
    maxw = LX1 - text_x
    st = style_for(m.competition.slug, m.competition.name)
    c.rect(LX0, y, LX0 + 44, y + ROW_BOX, fill=st.color)
    tf, _ = c.fit(st.tag, c.condensed, 22, 40)
    c.text(LX0 + 22, y + 36, st.tag, tf, contrast_on(st.color), "mm")
    if m.is_live:
        when, when_ink = f"LIVE {m.status_detail}  ·  {m.home_score}-{m.away_score}", "red"
    else:
        when, when_ink = f"{fmt.month_day(m.kickoff)}  ·  {fmt.time(m.kickoff).replace(' ', '')}", "red"
    when_font = c.condensed(18)
    c.text(text_x, y + 4, when, when_font, when_ink, "la", spacing=0.5)
    # Network right-aligned on the same line, only if it fits beside the date/time.
    if not m.is_live and (b := pick_broadcast(m.broadcasts)):
        room = maxw - c.text_width(when, when_font, 0.5) - 8
        bf, bsz = c.fit(b.upper(), c.condensed, 15, room, min_size=12, spacing=0.5)
        if c.text_width(b.upper(), bf, 0.5) <= room:
            c.text(LX1, y + 6, b.upper(), bf, "black", "ra", spacing=0.5)
    for j, (prefix, team) in enumerate((("", m.home), ("vs ", m.away))):
        label = team.short_name.upper()
        ink = "blue" if team.id in favorites else "black"
        f, sz = c.fit(prefix + label, lambda s: c.geo(s, 700), 16, maxw, min_size=12)
        if sz <= 12 and c.text_width(prefix + label, f) > maxw:
            label = team.abbreviation
        c.text(text_x, y + 24 + j * 22, prefix + label, f, ink, "la")


def _result_row(c: Canvas, m: Match, y: float, favorites: set[str], perspective):
    """A finished game, laid out like a fixture row: W/D/L from your team's side in the box
    (a neutral FT for league games without one of your teams), then the score on each line."""
    text_x = LX0 + 54
    st = style_for(m.competition.slug, m.competition.name)
    mine = bool(m.team_ids & favorites)
    outcome = m.outcome_for(perspective(m)) if mine else None
    if outcome:
        box, ink = RESULT_INK[outcome]
        c.rect(LX0, y, LX0 + 44, y + ROW_BOX, fill=box)
        c.text(LX0 + 22, y + ROW_BOX / 2 + 1, outcome, c.slab(30), ink, "mm")
    else:
        c.rect(LX0, y, LX0 + 44, y + ROW_BOX, fill="black")
        c.text(LX0 + 22, y + ROW_BOX / 2 + 1, "FT", c.condensed(26), "white", "mm", spacing=1)
    detail = [st.tag, "FULL TIME"]
    if m.winner and m.home_score == m.away_score:
        detail.append(f"{(m.home if m.winner == 'home' else m.away).abbreviation} ON PENS")
    c.text(text_x, y + 4, "  ·  ".join(detail), c.condensed(18), "red", "la", spacing=0.5)
    score_font = c.geo(18, 800)
    score_w = c.text_width("00", score_font)
    maxw = LX1 - text_x - score_w - 8
    for j, (prefix, team, goals) in enumerate((("", m.home, m.home_score), ("vs ", m.away, m.away_score))):
        label = team.short_name.upper()
        ink = "blue" if team.id in favorites else "black"
        f, sz = c.fit(prefix + label, lambda s: c.geo(s, 700), 16, maxw, min_size=12)
        if sz <= 12 and c.text_width(prefix + label, f) > maxw:
            label = team.abbreviation
        c.text(text_x, y + 24 + j * 22, prefix + label, f, ink, "la")
        c.text(LX1, y + 22 + j * 22, str(goals), score_font, "black", "ra")


def _last_day(fmt: Formatter, dt: datetime) -> str:
    return f"{fmt.local(dt).strftime('%a').upper()} {fmt.month_day(dt)}"   # "SAT NOV 15"


def draw_recent(c: Canvas, results: list[Match], perspective, fmt: Formatter, top: float):
    """The LAST section, from `top` down to the footer: a header band, then one row per result
    told from the favourite team's side:  [W]  MIN 2–1 vs ST. LOUIS / SAT OCT 24 · MLS."""
    row = min(LAST_ROW_MAX, (LIST_B - top - LAST_HEAD) / len(results))
    top = LIST_B - LAST_HEAD - row * len(results)      # spare room goes above the section
    c.rect(LX0, top, LX1, top + LAST_HEAD - 4, fill="black")
    head = "LAST RESULT" if len(results) == 1 else "LAST RESULTS"
    c.text((LX0 + LX1) / 2, top + (LAST_HEAD - 4) / 2 + 0.5, head, c.condensed(15), "yellow", "mm", spacing=2)
    text_x = LX0 + 54
    maxw = LX1 - text_x
    big = row >= 48                                     # one or two results: roomier type
    name_font, detail_font = c.geo(18 if big else 16, 700), c.condensed(18 if big else 16)
    y = top + LAST_HEAD + 2
    for m in results:
        team_id = perspective(m)
        outcome = m.outcome_for(team_id) or "D"
        box, ink = RESULT_INK[outcome]
        bh = row - 8
        c.rect(LX0, y, LX0 + 44, y + bh, fill=box)
        c.text(LX0 + 22, y + bh / 2 + 1, outcome, c.slab(28 if big else 22), ink, "mm")
        home = team_id == m.home.id
        us, them = (m.home, m.away) if home else (m.away, m.home)
        gf, ga = (m.home_score, m.away_score) if home else (m.away_score, m.home_score)
        lead = f"{us.abbreviation} {gf}–{ga} {'vs' if home else 'at'} "
        opp = them.short_name.upper()
        if c.text_width(lead + opp, name_font) > maxw:
            opp = them.abbreviation
        detail = [_last_day(fmt, m.kickoff), style_for(m.competition.slug, m.competition.name).tag]
        if m.winner and gf == ga:
            detail.append("PENS")
        # Two lines centred on the box, like the NEXT UP rows: teams + score, then when + where.
        y1 = y + bh / 2 - (22 if big else 19)
        c.text(text_x, y1, lead + opp, name_font, "black", "la")
        c.text(text_x, y1, us.abbreviation, name_font, "blue", "la")   # favourite in blue
        c.text(text_x, y1 + (23 if big else 20), "  ·  ".join(detail), detail_font, "red", "la", spacing=0.5)
        y += row


def render_board(board, cfg, now: datetime | None = None, layout: str | None = None,
                 battery: int | None = None, scale: float = 3.0) -> Image.Image:
    """Return the full-resolution RGB design (not yet snapped to the panel palette)."""
    now = now or board.generated_at
    fmt = Formatter(cfg.tz, cfg.display.clock, now)
    c = Canvas(scale)
    if board.featured:
        draw_featured(c, board.featured, fmt, cfg.team_color_overrides(), layout,
                      cfg.pick_broadcast(board.featured.broadcasts))
    else:
        draw_empty(c, fmt)
    draw_list(c, board.upcoming, fmt, cfg.team_ids, board.generated_at, battery,
              cfg.pick_broadcast, board.recent, lambda m: team_perspective(m, cfg),
              board.mode, board.results)
    return c.img
