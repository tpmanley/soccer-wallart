"""Reusable retro-poster drawing motifs. All coordinates are design units (800x480)."""
from __future__ import annotations

import math
import zlib

from .canvas import Canvas


def seed_of(*parts: str) -> int:
    return zlib.crc32("|".join(parts).encode())


# ---------------------------------------------------------------------------
# Backgrounds
# ---------------------------------------------------------------------------
def sunburst(c: Canvas, box, cx, cy, ray_color, rays: int = 36, offset_deg: float = 0):
    """Alternating rays of ray_color over whatever is already in box."""
    x0, y0, x1, y1 = box
    layer = c.layer(ray_color)
    layer.img.paste(c.img.crop((0, 0) + c.img.size))
    r = 1200
    step = 360 / rays
    for i in range(0, rays, 2):
        a0 = math.radians(offset_deg + i * step)
        a1 = math.radians(offset_deg + (i + 1) * step)
        layer.poly([(cx, cy), (cx + r * math.cos(a0), cy + r * math.sin(a0)),
                    (cx + r * math.cos(a1), cy + r * math.sin(a1))], fill=ray_color)
    c.paste_rect(layer, x0, y0, x1, y1)


def halftone(c: Canvas, box, color, cx, cy, inner: float = 190, ramp: float = 70,
             pitch: float = 9, max_r: float = 3.6):
    """Vector halftone dots that grow with distance from (cx, cy)."""
    x0, y0, x1, y1 = box
    row = 0
    y = y0 + pitch / 2
    while y < y1:
        x = x0 + pitch / 2 + (pitch / 2 if row % 2 else 0)
        while x < x1:
            rr = max(0.0, (math.hypot(x - cx, y - cy) - inner) / ramp) * 2.2
            if rr > 0.45:
                rr = min(rr, max_r)
                c.ellipse(x, y, rr, fill=color)
            x += pitch
        y += pitch
        row += 1


def halftone_linear(c: Canvas, box, color, direction: str = "down", pitch: float = 8, max_r: float = 3.4):
    """Halftone fade across a box (dots grow toward `direction`)."""
    x0, y0, x1, y1 = box
    row = 0
    y = y0 + pitch / 2
    while y < y1:
        x = x0 + pitch / 2 + (pitch / 2 if row % 2 else 0)
        while x < x1:
            t = {"down": (y - y0) / (y1 - y0), "up": (y1 - y) / (y1 - y0),
                 "right": (x - x0) / (x1 - x0), "left": (x1 - x) / (x1 - x0)}[direction]
            rr = t * max_r
            if rr > 0.45:
                c.ellipse(x, y, rr, fill=color)
            x += pitch
        y += pitch
        row += 1


def pitch_band(c: Canvas, x0, x1, top, bottom, vanish_x, color="green", lines="white"):
    c.rect(x0, top, x1, bottom, fill=color)
    for k in range(-8, 9):
        c.line([(vanish_x + k * 30, top), (vanish_x + k * 75, bottom)], fill=lines, width=1)
    c.line([(x0, top), (x1, top)], fill=lines, width=2)


def stadium(c: Canvas, x0, x1, base, height, color="black", light="yellow"):
    """Stylized stand silhouette with arches and two floodlight towers."""
    c.poly([(x0, base), (x0, base - height * 0.55), (x0 + (x1 - x0) * 0.12, base - height * 0.7),
            (x1 - (x1 - x0) * 0.12, base - height * 0.7), (x1, base - height * 0.55), (x1, base)], fill=color)
    n = 9
    span = (x1 - x0 - 40) / n
    for i in range(n):
        ax = x0 + 20 + i * span + span / 2
        c.rect(ax - span * 0.3, base - height * 0.38, ax + span * 0.3, base - 2, fill=light)
        c.ellipse(ax, base - height * 0.38, span * 0.3, span * 0.3, fill=light)
    for tx in (x0 + 18, x1 - 18):
        c.rect(tx - 2.5, base - height * 1.25, tx + 2.5, base - height * 0.6, fill=color)
        c.rect(tx - 14, base - height * 1.38, tx + 14, base - height * 1.22, fill=color)
        for j in range(4):
            c.ellipse(tx - 9 + j * 6, base - height * 1.30, 2, fill=light)


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------
def _limb(c: Canvas, a, b, w, fill="black"):
    (x0, y0), (x1, y1) = a, b
    ang = math.atan2(y1 - y0, x1 - x0) + math.pi / 2
    dx, dy = math.cos(ang) * w / 2, math.sin(ang) * w / 2
    c.poly([(x0 + dx, y0 + dy), (x1 + dx * .8, y1 + dy * .8), (x1 - dx * .8, y1 - dy * .8), (x0 - dx, y0 - dy)], fill=fill)
    c.ellipse(x1, y1, w * .4, fill=fill)


def player(c: Canvas, hx, hy, k=1.0, shirt="white", shorts="white", trim="yellow", mirror=False,
           skin="black"):
    """Angular deco-style footballer mid-kick. (hx, hy) = hip; ball sits at ball_offset()."""
    m = -1 if mirror else 1

    def T(*pts):
        return [(hx + m * x * k, hy + y * k) for x, y in pts]

    def limb(a, b, w):
        (p,), (q,) = T(a), T(b)
        _limb(c, p, q, w * k, skin)

    # standing leg
    limb((-7, 0), (-26, 44), 22)
    limb((-26, 44), (-18, 86), 18)
    c.poly(T((-36, 82), (-4, 82), (0, 94), (-44, 94)), fill=skin)
    # kicking leg
    limb((10, 0), (54, 28), 22)
    limb((54, 28), (88, 14), 18)
    c.poly(T((80, 4), (102, 10), (100, 22), (84, 24)), fill=skin)
    # arms
    limb((26, -80), (56, -102), 15)
    limb((56, -102), (68, -136), 12)
    limb((-14, -78), (-46, -52), 15)
    limb((-46, -52), (-74, -58), 12)
    # shirt
    c.poly(T((-20, -88), (32, -92), (22, -12), (-16, -10)), fill="black")
    c.poly(T((-15, -83), (27, -87), (18, -17), (-11, -15)), fill=shirt)
    c.poly(T((0, -87), (12, -88), (6, -72)), fill="black")
    if trim and trim != shirt:
        c.line(T((-10, -48), (23, -50)), fill=trim, width=3.2 * k)
    # shorts
    c.poly(T((-18, -12), (24, -14), (30, 10), (8, 14), (2, 0), (-10, 14), (-24, 10)), fill="black")
    c.poly(T((-14, -9), (20, -11), (25, 7), (10, 9), (2, -5), (-9, 9), (-19, 7)), fill=shorts)
    # head
    limb((6, -86), (4, -98), 10)
    (hc,) = T((5, -114))
    c.ellipse(hc[0], hc[1], 16 * k, fill=skin)


def ball_offset(k=1.0, mirror=False):
    return (-124 * k if mirror else 124 * k), 14 * k


def ball(c: Canvas, bx, by, r=20, streaks: str | None = "left"):
    if streaks:
        sgn = -1 if streaks == "left" else 1
        for i, ln in enumerate((70, 52, 38)):
            yy = by - r / 2 + i * r / 2
            a = bx + sgn * (r + 8)
            c.line([(a, yy), (a + sgn * ln * r / 20, yy)], fill="black", width=3)
    c.ellipse(bx, by, r, fill="white", outline="black", width=3)
    pr = r * 0.4
    pent = [(bx + pr * math.cos(math.radians(-90 + 72 * i)), by + pr * math.sin(math.radians(-90 + 72 * i)))
            for i in range(5)]
    c.poly(pent, fill="black")
    for px, py in pent:
        c.line([(px, py), (bx + (px - bx) * 2.4, by + (py - by) * 2.4)], fill="black", width=2)


# ---------------------------------------------------------------------------
# Badges, ribbons, frames
# ---------------------------------------------------------------------------
def _shield_pts(x, y, w, h):
    return [(x, y), (x + w, y), (x + w, y + h * .6), (x + w / 2, y + h), (x, y + h * .6)]


SHIELD_PATTERNS = ("stripes", "halves", "sash", "hoops", "chevron", "quarters")
# Clubs whose identity *is* a pattern (ESPN team ids).
PATTERN_OVERRIDES = {"83": "stripes", "110": "stripes", "111": "stripes", "103": "stripes",
                     "86": "sash", "17362": "sash"}


def shield(c: Canvas, x, y, w, h, primary, secondary, abbr: str, team_id: str, pattern: str | None = None,
           ornament: str | None = None):
    """Original stylized club shield (never a real crest)."""
    sd = seed_of(team_id)
    pattern = pattern or PATTERN_OVERRIDES.get(team_id) or SHIELD_PATTERNS[sd % len(SHIELD_PATTERNS)]
    ornament = ornament or ("crown", "star", "none")[(sd // 7) % 3]
    pts = _shield_pts(x, y, w, h)
    c.poly(_shield_pts(x - 4, y - 4, w + 8, h + 10), fill="black")

    lay = c.layer(primary)
    if pattern == "stripes":
        n = 7
        for i in range(1, n, 2):
            lay.rect(x + i * w / n, y, x + (i + 1) * w / n, y + h, fill=secondary)
    elif pattern == "halves":
        lay.rect(x + w / 2, y, x + w, y + h, fill=secondary)
    elif pattern == "sash":
        lay.poly([(x + w * .1, y + h * .8), (x + w * .9, y + h * .2), (x + w, y + h * .33), (x + w * .25, y + h * .9)],
                 fill=secondary)
    elif pattern == "hoops":
        for i in range(1, 6, 2):
            lay.rect(x, y + i * h / 6, x + w, y + (i + 1) * h / 6, fill=secondary)
    elif pattern == "chevron":
        lay.poly([(x, y + h * .15), (x + w / 2, y + h * .55), (x + w, y + h * .15), (x + w, y + h * .42),
                  (x + w / 2, y + h * .82), (x, y + h * .42)], fill=secondary)
    elif pattern == "quarters":
        lay.rect(x + w / 2, y, x + w, y + h / 2, fill=secondary)
        lay.rect(x, y + h / 2, x + w / 2, y + h, fill=secondary)
    c.paste_poly(lay, pts)

    # chief band with abbreviation
    band_h = h * 0.27
    c.rect(x, y, x + w, y + band_h, fill="black")
    f, _ = c.fit(abbr, c.slab, band_h * 0.8, w * 0.85)
    c.text(x + w / 2, y + band_h / 2 + 1, abbr, f, "white", "mm")

    if ornament == "crown":
        cx = x + w / 2
        cw = w * 0.62
        c.poly([(cx - cw / 2, y - 6), (cx - cw / 2 + cw * .12, y - 22), (cx - cw / 4, y - 10), (cx, y - 26),
                (cx + cw / 4, y - 10), (cx + cw / 2 - cw * .12, y - 22), (cx + cw / 2, y - 6)],
               fill="yellow", outline="black", width=2)
    elif ornament == "star":
        star(c, x + w / 2, y - 14, 11, "yellow", outline="black")


def star(c: Canvas, cx, cy, r, fill, outline=None):
    pts = []
    for i in range(10):
        rr = r if i % 2 == 0 else r * 0.45
        a = math.radians(-90 + i * 36)
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    c.poly(pts, fill=fill, outline=outline, width=2 if outline else 0)


def ribbon(c: Canvas, cx, cy, text: str, fill="blue", ink="white", max_w=260, h=36):
    f, _ = c.fit(text, c.slab, 24, max_w - 50, spacing=2)
    tw = c.text_width(text, f, spacing=2)
    half = tw / 2 + 26
    notch = 12
    c.poly([(cx - half, cy - h / 2), (cx + half, cy - h / 2), (cx + half - notch, cy), (cx + half, cy + h / 2),
            (cx - half, cy + h / 2), (cx - half + notch, cy)], fill=fill, outline="black", width=2)
    c.text(cx, cy + 1, text, f, ink, "mm", spacing=2)
