"""Poster art layouts. Each draws the illustrated area of the featured-match poster.

Signature: layout(c, art_box, home: Kit, away: Kit) — art_box = (x0, y0, x1, y1).
The banner above and name block below are drawn by poster.py.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import motifs
from .canvas import Canvas
from .emblems import EMBLEMS


@dataclass
class Kit:
    team_id: str
    abbr: str
    primary: str
    secondary: str

    @property
    def shirt(self):
        return self.primary

    @property
    def shorts(self):
        return self.secondary if self.secondary != "yellow" or self.primary == "white" else self.primary

    @property
    def trim(self):
        for col in (self.secondary, "yellow", "red"):
            if col != self.primary and col not in ("black",):
                return col
        return "white"


def _shield(c, x, y, kit: Kit, w=70, h=90):
    """A club's look-alike emblem if we have one, otherwise a generated shield."""
    emblem = EMBLEMS.get(kit.team_id)
    if emblem:
        emblem(c, x, y, w, h)
    else:
        motifs.shield(c, x, y, w, h, kit.primary, kit.secondary, kit.abbr, kit.team_id)


def sunburst(c: Canvas, box, home: Kit, away: Kit):
    """Yellow/white rays, red sun disc, halftone corners, kicking player, green pitch."""
    x0, y0, x1, y1 = box
    cx = (x0 + x1) / 2
    cy = y0 + (y1 - y0) * 0.55
    ray_bg = "yellow"
    c.rect(x0, y0, x1, y1, fill=ray_bg)
    motifs.sunburst(c, box, cx, cy, "white", rays=36)
    disc = "red" if home.shirt != "red" else "blue"
    motifs.halftone(c, (x0, y0, x1, y1 - 45), disc, cx, cy)
    c.ellipse(cx, cy, 112, fill=disc)
    c.ellipse(cx, cy, 100, outline="white", width=3)
    pitch_top = y1 - 45
    motifs.pitch_band(c, x0, x1, pitch_top, y1, cx)

    k = 1.0
    hx, hy = cx - 20, pitch_top - 52
    motifs.player(c, hx, hy, k, home.shirt, home.shorts, home.trim)
    bx, by = motifs.ball_offset(k)
    motifs.ball(c, hx + bx, hy + by, 20)

    _shield(c, x0 + 30, y0 + 40, home)
    _shield(c, x1 - 100, y0 + 40, away)


def diagonal(c: Canvas, box, home: Kit, away: Kit):
    """Field split diagonally in the two clubs' colors; players clash over the ball."""
    x0, y0, x1, y1 = box
    a_col = home.primary if home.primary not in ("black",) else home.secondary
    b_col = away.primary if away.primary not in ("black", a_col) else (
        away.secondary if away.secondary not in ("black", a_col) else
        next(col for col in ("yellow", "red", "blue", "green", "white") if col != a_col))
    c.rect(x0, y0, x1, y1, fill=a_col)
    lay = c.layer(b_col)
    split = [(x0 + (x1 - x0) * 0.62, y0), (x1, y0), (x1, y1), (x0 + (x1 - x0) * 0.38, y1)]
    c.paste_poly(lay, split)
    # halftone overlays for texture
    motifs.halftone_linear(c, (x0, y0, x0 + (x1 - x0) * 0.5, y1), "white" if a_col != "white" else "yellow", "up")
    motifs.halftone_linear(c, (x0 + (x1 - x0) * 0.5, y0, x1, y1), "black", "down", max_r=2.6)
    # black lightning split
    mx_top, mx_bot = x0 + (x1 - x0) * 0.62, x0 + (x1 - x0) * 0.38
    c.poly([(mx_top - 7, y0), (mx_top + 7, y0), (mx_bot + 7, y1), (mx_bot - 7, y1)], fill="black")

    ground = y1 - 18
    c.rect(x0, ground, x1, y1, fill="green")
    c.line([(x0, ground), (x1, ground)], fill="white", width=2)
    k = 0.92
    cx = (x0 + x1) / 2
    hy = ground - 94 * k + 2
    motifs.player(c, cx - 125, hy, k, home.shirt, home.shorts, home.trim)
    motifs.player(c, cx + 125, hy, k, away.shirt, away.shorts, away.trim, mirror=True)
    motifs.ball(c, cx, hy + 14 * k, 19, streaks=None)
    # starburst VS medallion
    motifs.star(c, cx, y0 + 62, 46, "yellow", outline="black")
    c.ellipse(cx, y0 + 62, 24, fill="black")
    c.text(cx, y0 + 63, "VS", c.slab(20), "yellow", "mm")
    _shield(c, x0 + 22, y0 + 34, home, 62, 80)
    _shield(c, x1 - 84, y0 + 34, away, 62, 80)


def deco(c: Canvas, box, home: Kit, away: Kit):
    """Art-deco night match: floodlit stadium, ball rising like a moon, concentric arches."""
    x0, y0, x1, y1 = box
    cx = (x0 + x1) / 2
    sky = "blue" if "blue" not in (home.primary,) else "black"
    c.rect(x0, y0, x1, y1, fill=sky)
    base = y1 - 26
    # concentric arches
    for i, r in enumerate(range(250, 60, -28)):
        c.ellipse(cx, base, r, r, outline="yellow" if i % 2 == 0 else "white", width=3)
    motifs.halftone(c, (x0, y0, x1, base), "white", cx, base - 40, inner=230, ramp=90, pitch=10, max_r=2.6)
    # moon-ball
    c.ellipse(cx, base - 150, 54, fill="black")
    motifs.ball(c, cx, base - 150, 50, streaks=None)
    # floodlight beams
    for sx, ex in ((x0 + 18, cx - 40), (x1 - 18, cx + 40)):
        c.poly([(sx, base - 95), (ex - 30, y0), (ex + 30, y0)], fill="yellow")
    motifs.stadium(c, x0, x1, base, 76, color="black", light="yellow")
    c.rect(x0, base, x1, y1, fill="green")
    c.line([(x0, base), (x1, base)], fill="white", width=2)
    k = 0.8
    feet = y1 - 4
    motifs.player(c, cx - 140, feet - 94 * k, k, home.shirt, home.shorts, home.trim)
    motifs.player(c, cx + 140, feet - 94 * k, k, away.shirt, away.shorts, away.trim, mirror=True)
    _shield(c, x0 + 22, y0 + 30, home, 56, 72)
    _shield(c, x1 - 78, y0 + 30, away, 56, 72)


LAYOUTS = {"sunburst": sunburst, "diagonal": diagonal, "deco": deco}
