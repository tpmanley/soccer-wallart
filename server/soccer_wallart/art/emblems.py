"""Hand-drawn look-alike emblems for favourite clubs.

These are simplified retro *impressions* of each club's crest, built from basic shapes in
the panel's 6 colors. They borrow the overall shape, colors and one or two key symbols so
the club is recognizable at a glance; they are deliberately not reproductions of the
trademarked crests.

Each emblem draws into the same box a generic shield would use: (x, y, w, h), with
ornaments (crowns, stars, gates) allowed to rise ~25 units above y.
To add a club: write a function with the same signature and register its ESPN team id
in EMBLEMS.
"""
from __future__ import annotations

import math
from typing import Callable

from .canvas import Canvas


class Box:
    """Map unit coordinates (0..1 across the emblem box) to design units."""

    def __init__(self, x, y, w, h):
        self.x, self.y, self.w, self.h = x, y, w, h

    def __call__(self, fx, fy):
        return (self.x + fx * self.w, self.y + fy * self.h)

    def pts(self, *uv):
        return [self(u, v) for u, v in uv]

    @property
    def cx(self):
        return self.x + self.w / 2


def arc(cx, cy, rx, ry, a0, a1, n=24):
    """Points along an ellipse arc, angles in degrees (0 = right, 90 = down)."""
    return [(cx + rx * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + ry * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def _clip(c: Canvas, outline_pts, bg, draw: Callable[[Canvas], None], border=3):
    """Fill `outline_pts` with bg + whatever draw() paints, clipped to the outline."""
    c.poly(outline_pts, fill="black")
    lay = c.layer(bg)
    draw(lay)
    c.paste_poly(lay, outline_pts)
    c.poly(outline_pts, outline="black", width=border)


def _label(c: Canvas, cx, cy, text, max_w, size, ink, font=None):
    f, _ = c.fit(text, font or c.slab, size, max_w)
    c.text(cx, cy, text, f, ink, "mm")


def _star4(c: Canvas, cx, cy, r, fill):
    k = r * 0.28
    c.poly([(cx, cy - r), (cx + k, cy - k), (cx + r, cy), (cx + k, cy + k),
            (cx, cy + r), (cx - k, cy + k), (cx - r, cy), (cx - k, cy - k)], fill=fill)


def _ball(c: Canvas, cx, cy, r):
    c.ellipse(cx, cy, r, fill="white", outline="black", width=max(1, r * 0.18))
    pr = r * 0.42
    c.poly([(cx + pr * math.cos(math.radians(-90 + 72 * i)), cy + pr * math.sin(math.radians(-90 + 72 * i)))
            for i in range(5)], fill="black")


def _flame(c: Canvas, cx, bottom, fw, fh, lean=1):
    """Teardrop flame: rounded base, flickering tip leaning outward; red core."""
    def drop(scale, fill):
        r = fw * scale / 2
        base_cy = bottom - r
        pts = arc(cx, base_cy, r, r, 0, 180, 12)
        tip = (cx + lean * r * 0.9, bottom - fh * scale)
        pts += [(cx - r * 0.9, base_cy - fh * scale * 0.25), (cx - lean * r * 0.1, base_cy - fh * scale * 0.5),
                tip, (cx + r * 0.8, base_cy - fh * scale * 0.3)]
        c.poly(pts, fill=fill, outline="black" if fill == "yellow" else None, width=1.2 if fill == "yellow" else 0)
    drop(1.0, "yellow")
    drop(0.5, "red")


def _heater_shield(b: Box, top=0.0):
    """Flat top, straight sides, round-bottomed point (classic heraldic shield)."""
    left = arc(b.x + b.w / 2, b.y + b.h * 0.55, b.w / 2, b.h * 0.45, 180, 90, 14)
    right = arc(b.x + b.w / 2, b.y + b.h * 0.55, b.w / 2, b.h * 0.45, 90, 0, 14)
    return [b(0, top), b(1, top)] + right[::-1][:-1] + [b(0.5, 1.0)] + left[::-1][1:]


# ---------------------------------------------------------------------------
# Clubs
# ---------------------------------------------------------------------------
def real_madrid(c: Canvas, x, y, w, h):
    """Gold-rimmed white roundel, bluish-mulberry band (upper left to lower right),
    interlaced gold MCF monogram, and a royal crown resting on the rim."""
    r = min(w / 2, h * 0.40)
    cx, cy = x + w / 2, y + h - r

    # roundel: thin black / gold rim / thin black / white field
    c.ellipse(cx, cy, r + 1.5, fill="black")
    c.ellipse(cx, cy, r, fill="yellow")
    c.ellipse(cx, cy, r * 0.88, fill="black")
    field = arc(cx, cy, r * 0.84, r * 0.84, 0, 360, 48)

    def inside(l: Canvas):
        # band runs upper-left to lower-right: centre line along (1, 1), width along (1, -1)
        bw, L = r * 0.24, r * 1.2
        ux, uy, nx, ny = 0.7071, 0.7071, 0.7071, -0.7071
        band = [(cx - L * ux + bw * nx, cy - L * uy + bw * ny), (cx + L * ux + bw * nx, cy + L * uy + bw * ny),
                (cx + L * ux - bw * nx, cy + L * uy - bw * ny), (cx - L * ux - bw * nx, cy - L * uy - bw * ny)]
        l.poly(band, fill="blue")
        l.line([band[0], band[1]], "black", 1.2)
        l.line([band[3], band[2]], "black", 1.2)
    _clip(c, field, "white", inside, border=0)

    # monogram reading M-C-F, letters overlapping like the interlaced original;
    # gold outlined in black. C is drawn last so it sits over both neighbours.
    stroke = max(0.7, r * 0.04)
    big, small = c.slab(r * 0.74), c.slab(r * 0.62)
    c.text(cx - r * 0.3, cy, "M", big, "yellow", "mm", stroke=stroke)
    c.text(cx + r * 0.5, cy + r * 0.04, "F", small, "yellow", "mm", stroke=stroke)
    c.text(cx + r * 0.16, cy + r * 0.06, "C", small, "yellow", "mm", stroke=stroke)

    _royal_crown(c, cx, cy - r * 0.86, r * 1.6, r * 0.9)


def _royal_crown(c: Canvas, cx, base, cw, ch):
    """Closed royal crown: red cap under gold arches, jewelled band, orb and cross.
    `base` is the bottom of the band; the crown rises ch above it."""
    band_h = ch * 0.2
    band_top = base - band_h
    # red cap
    c.poly(arc(cx, band_top, cw * 0.42, ch * 0.62, 180, 360, 20), fill="red")
    # arches: outer pair, inner pair, centre — gold with black edging
    def arch(rx, ry, a0, a1, width):
        pts = arc(cx, band_top, rx, ry, a0, a1, 14)
        c.line(pts, "black", width + 1.6)
        c.line(pts, "yellow", width)
    t = max(1.4, cw * 0.06)
    arch(cw * 0.46, ch * 0.66, 180, 270, t)
    arch(cw * 0.46, ch * 0.66, 270, 360, t)
    arch(cw * 0.2, ch * 0.66, 180, 270, t * 0.8)
    arch(cw * 0.2, ch * 0.66, 270, 360, t * 0.8)
    # band with gems
    c.rect(cx - cw / 2, band_top, cx + cw / 2, base, fill="yellow", outline="black", width=1.2)
    for i, gx in enumerate((-0.33, -0.11, 0.11, 0.33)):
        c.ellipse(cx + gx * cw, band_top + band_h / 2, band_h * 0.28, fill="red" if i % 2 == 0 else "blue")
    # orb and cross
    oy = band_top - ch * 0.66
    orb_r = max(1.8, ch * 0.09)
    c.ellipse(cx, oy - orb_r * 0.6, orb_r, fill="yellow", outline="black", width=1)
    ct = oy - orb_r * 1.6
    c.rect(cx - 0.9, ct - orb_r * 2.2, cx + 0.9, ct, fill="black")
    c.rect(cx - orb_r * 0.9, ct - orb_r * 1.6, cx + orb_r * 0.9, ct - orb_r * 1.15, fill="black")


def barcelona(c: Canvas, x, y, w, h):
    """'Pot' silhouette: St George's cross + senyera, FCB band, blaugrana stripes, ball."""
    b = Box(x, y, w, h)
    lower = arc(b.cx, y + h * 0.48, w / 2, h * 0.52, 0, 180, 24)
    outline = [b(0.0, -0.06), b(0.14, 0.02), b(0.5, 0.05), b(0.86, 0.02), b(1.0, -0.06)] + lower

    def inside(l: Canvas):
        mid, top_b, band_b = b.cx, y + h * 0.36, y + h * 0.50
        # St George's cross (left) and senyera (right)
        l.rect(x, y - h * 0.1, mid, top_b, fill="white")
        l.rect(x + w * 0.20, y - h * 0.1, x + w * 0.30, top_b, fill="red")
        l.rect(x, y + h * 0.14, mid, y + h * 0.22, fill="red")
        l.rect(mid, y - h * 0.1, x + w, top_b, fill="yellow")
        for i in range(4):
            sx = mid + w * (0.06 + i * 0.11)
            l.rect(sx, y - h * 0.1, sx + w * 0.05, top_b, fill="red")
        # FCB band
        l.rect(x, top_b, x + w, band_b, fill="white")
        l.line([(x, top_b), (x + w, top_b)], "black", 1.5)
        l.line([(x, band_b), (x + w, band_b)], "black", 1.5)
        _label(l, mid, (top_b + band_b) / 2 + 0.5, "FCB", w * 0.6, h * 0.12, "black")
        # blaugrana stripes + ball
        n = 5
        for i in range(n):
            l.rect(x + i * w / n, band_b, x + (i + 1) * w / n, y + h, fill="blue" if i % 2 == 0 else "red")
        _ball(l, mid, y + h * 0.73, w * 0.12)
        l.line([(mid, y - h * 0.1), (mid, top_b)], "black", 1.5)
    _clip(c, outline, "white", inside)


def liverpool(c: Canvas, x, y, w, h):
    """Red shield with a yellow liver bird, flanking flames and the gates above."""
    b = Box(x, y, w, h)
    # flames either side
    for sgn in (-1, 1):
        _flame(c, b.cx + sgn * (w / 2 + 6), y + h * 0.66, w * 0.15, h * 0.42, lean=sgn)
    # gates arch above
    gx0, gx1, gy = x + w * 0.1, x + w * 0.9, y - 2
    c.poly(arc(b.cx, gy, (gx1 - gx0) / 2, 14, 180, 360, 20) + [(gx1, gy)], fill="yellow", outline="black", width=1.5)
    c.poly(arc(b.cx, gy, (gx1 - gx0) / 2 - 5, 9, 180, 360, 20) + [(gx1 - 5, gy)], fill="red")
    for i in range(1, 6):
        gx = gx0 + 5 + i * (gx1 - gx0 - 10) / 6
        c.line([(gx, gy - 7), (gx, gy)], "yellow", 1.4)

    shield = _heater_shield(b)

    def inside(l: Canvas):
        bx, by = b(0.52, 0.48)
        s = w / 70
        # liver bird: body, raised wing, long neck, head, beak with sprig, legs
        l.poly([(bx - 14 * s, by + 4 * s), (bx - 2 * s, by - 10 * s), (bx + 12 * s, by - 6 * s),
                (bx + 14 * s, by + 8 * s), (bx + 2 * s, by + 16 * s), (bx - 10 * s, by + 14 * s)], fill="yellow")
        l.poly([(bx - 6 * s, by - 6 * s), (bx - 22 * s, by - 26 * s), (bx - 12 * s, by - 24 * s),
                (bx - 2 * s, by - 10 * s)], fill="yellow")
        l.poly([(bx + 6 * s, by - 8 * s), (bx + 10 * s, by - 26 * s), (bx + 16 * s, by - 26 * s),
                (bx + 13 * s, by - 6 * s)], fill="yellow")
        l.ellipse(bx + 13 * s, by - 29 * s, 5 * s, fill="yellow")
        l.poly([(bx + 16 * s, by - 31 * s), (bx + 27 * s, by - 28 * s), (bx + 16 * s, by - 26 * s)], fill="yellow")
        l.line([(bx + 24 * s, by - 28 * s), (bx + 30 * s, by - 22 * s)], "yellow", 1.6 * s)
        l.ellipse(bx + 30 * s, by - 21 * s, 2.2 * s, fill="yellow")
        l.line([(bx - 2 * s, by + 15 * s), (bx - 5 * s, by + 24 * s)], "yellow", 2.4 * s)
        l.line([(bx + 5 * s, by + 14 * s), (bx + 5 * s, by + 24 * s)], "yellow", 2.4 * s)
        l.rect(x, y + h * 0.80, x + w, y + h * 0.81, fill="yellow")
        _label(l, b.cx, y + h * 0.88, "LFC", w * 0.5, h * 0.12, "yellow")
    _clip(c, shield, "red", inside)


def crystal_palace(c: Canvas, x, y, w, h):
    """Red/blue halves, the glass palace's arched facade, eagle with spread wings on a ball."""
    b = Box(x, y, w, h)
    shield = _heater_shield(b)

    def inside(l: Canvas):
        l.rect(b.cx, y, x + w, y + h, fill="blue")
        # palace facade: arched roof with glass panes
        ay = y + h * 0.62
        rx, ry = w * 0.42, h * 0.36
        l.poly(arc(b.cx, ay, rx, ry, 180, 360, 24), fill="white")
        l.poly(arc(b.cx, ay, rx - 3.5, ry - 3.5, 180, 360, 24), fill="black")
        for i in range(-3, 4):
            px = b.cx + i * rx / 4
            top = ay - ry * math.sqrt(max(0.0, 1 - (i / 4) ** 2)) + 2
            l.line([(px, top), (px, ay)], "white", 1.3)
        l.line([(b.cx - rx, ay), (b.cx + rx, ay)], "white", 2)
        # ball and eagle
        bx, by = b.cx, y + h * 0.66
        _ball(l, bx, by + h * 0.06, w * 0.1)
        s = w / 70
        ey = by - 4 * s
        for sgn in (-1, 1):
            l.poly([(bx, ey), (bx + sgn * 30 * s, ey - 26 * s), (bx + sgn * 26 * s, ey - 16 * s),
                    (bx + sgn * 32 * s, ey - 16 * s), (bx + sgn * 24 * s, ey - 6 * s),
                    (bx + sgn * 28 * s, ey - 4 * s), (bx + sgn * 8 * s, ey + 2 * s)], fill="yellow")
        l.ellipse(bx, ey - 5 * s, 6 * s, 9 * s, fill="yellow")
        l.ellipse(bx, ey - 17 * s, 4 * s, fill="yellow")
        l.poly([(bx + 3 * s, ey - 19 * s), (bx + 9 * s, ey - 16 * s), (bx + 3 * s, ey - 14 * s)], fill="yellow")
        l.rect(x, y + h * 0.80, x + w, y + h * 0.81, fill="white")
        _label(l, b.cx, y + h * 0.88, "CPFC", w * 0.5, h * 0.11, "white")
    _clip(c, shield, "red", inside)


def psg(c: Canvas, x, y, w, h):
    """Round badge: white ring, navy field, red Eiffel Tower, white fleur-de-lis."""
    b = Box(x, y, w, h)
    r = min(w / 2, h * 0.5)
    cx, cy = b.cx, y + h - r
    c.ellipse(cx, cy, r + 2, fill="black")
    c.ellipse(cx, cy, r, fill="white")
    c.ellipse(cx, cy, r * 0.78, fill="red")
    disc = arc(cx, cy, r * 0.72, r * 0.72, 0, 360, 48)
    s = r / 40

    def inside(l: Canvas):
        # Eiffel tower: spire, upper shaft, platforms, splayed legs with arch
        top, mid1, mid2, base = cy - 26 * s, cy - 6 * s, cy + 6 * s, cy + 22 * s
        l.poly([(cx - 1.2 * s, top), (cx + 1.2 * s, top), (cx + 4 * s, mid1), (cx - 4 * s, mid1)], fill="red")
        l.rect(cx - 6.5 * s, mid1, cx + 6.5 * s, mid1 + 2.2 * s, fill="red")
        l.poly([(cx - 4.5 * s, mid1 + 2 * s), (cx + 4.5 * s, mid1 + 2 * s), (cx + 8 * s, mid2), (cx - 8 * s, mid2)], fill="red")
        l.rect(cx - 10 * s, mid2, cx + 10 * s, mid2 + 2.4 * s, fill="red")
        l.poly([(cx - 9 * s, mid2 + 2 * s), (cx + 9 * s, mid2 + 2 * s), (cx + 16 * s, base), (cx - 16 * s, base)], fill="red")
        l.poly(arc(cx, base, 7.5 * s, 9 * s, 180, 360, 16), fill="blue")
        # fleur-de-lis under the arch
        fy = base + 6 * s
        l.ellipse(cx, fy - 3 * s, 2 * s, 4.5 * s, fill="white")
        l.ellipse(cx - 4 * s, fy - 1 * s, 2.6 * s, 2 * s, fill="white")
        l.ellipse(cx + 4 * s, fy - 1 * s, 2.6 * s, 2 * s, fill="white")
        l.rect(cx - 5 * s, fy + 0.5 * s, cx + 5 * s, fy + 2 * s, fill="white")
    _clip(c, disc, "blue", inside, border=0)
    # ring lettering: P S G spaced around the top of the white ring
    f, _ = c.fit("PARIS", c.condensed, r * 0.24, r * 1.2)
    c.text(cx, cy - r * 0.89, "PARIS", f, "blue", "mm", spacing=1)
    if r >= 45:  # too small to read on the posters' badge sizes
        c.text(cx, cy + r * 0.9, "SAINT-GERMAIN", c.fit("SAINT-GERMAIN", c.condensed, r * 0.2, r * 1.3)[0], "blue", "mm")
    else:
        _star4(c, cx, cy + r * 0.89, r * 0.1, "blue")


def minnesota_united(c: Canvas, x, y, w, h):
    """Shield in Minnesota blue: a loon in flight with raised wings, the North Star, MNUFC."""
    b = Box(x, y, w, h)
    shield = _heater_shield(b)

    def inside(l: Canvas):
        s = w / 70
        bx, by = b(0.5, 0.52)
        # wings (raised V), body, neck, head and long beak
        for sgn in (-1, 1):
            l.poly([(bx + sgn * 2 * s, by), (bx + sgn * 30 * s, by - 26 * s), (bx + sgn * 33 * s, by - 20 * s),
                    (bx + sgn * 12 * s, by + 4 * s)], fill="black")
            # white wing spots, as on a loon's back
            for k in range(3):
                t = 0.35 + k * 0.2
                l.ellipse(bx + sgn * (2 + 28 * t) * s, by - 23 * t * s + 1.5 * s, 1.4 * s, fill="white")
        l.ellipse(bx, by + 4 * s, 13 * s, 6 * s, fill="black")
        l.poly([(bx - 10 * s, by + 2 * s), (bx - 20 * s, by - 4 * s), (bx - 18 * s, by), (bx - 8 * s, by + 6 * s)], fill="black")
        l.ellipse(bx - 21 * s, by - 5 * s, 4.5 * s, 3.8 * s, fill="black")
        l.poly([(bx - 24 * s, by - 6.5 * s), (bx - 34 * s, by - 3 * s), (bx - 24 * s, by - 3.5 * s)], fill="black")
        l.ellipse(bx - 21 * s, by - 6 * s, 0.9 * s, fill="red")
        _star4(l, b(0.78, 0.17)[0], b(0.78, 0.17)[1], 7 * s, "white")
        l.rect(x, y + h * 0.72, x + w, y + h * 1.1, fill="black")
        _label(l, b.cx, y + h * 0.82, "MNUFC", w * 0.62, h * 0.12, "white", font=c.condensed)
    _clip(c, shield, "blue", inside)


def _usa_shield(c: Canvas, x, y, w, h):
    """Straight-sided shield: navy chief with USA, red and white vertical stripes below."""
    b = Box(x, y, w, h)
    shield = b.pts((0, 0), (1, 0), (1, 0.62), (0.5, 1.0), (0, 0.62))
    chief = 0.36

    def inside(l: Canvas):
        n = 7  # red, white, red, … with red on both edges
        sw = w / n
        for i in range(0, n, 2):
            l.rect(x + i * sw, y, x + (i + 1) * sw, y + h, fill="red")
        l.rect(x, y, x + w, y + h * chief, fill="blue")
        l.rect(x, y + h * chief, x + w, y + h * chief + max(1.5, h * 0.025), fill="white")
        _label(l, b.cx, y + h * chief / 2 + 1, "USA", w * 0.74, h * 0.26, "white")
    _clip(c, shield, "white", inside)
    return b


def usa_men(c: Canvas, x, y, w, h):
    """US men's national team."""
    _usa_shield(c, x, y, w, h)


def usa_women(c: Canvas, x, y, w, h):
    """US women's national team: the same shield, with four stars above for the World Cups."""
    b = _usa_shield(c, x, y, w, h)
    r = max(4.0, w * 0.115)
    for i in range(4):
        sx = b.cx + (i - 1.5) * r * 2.25
        _star5(c, sx, y - r - 2, r, "yellow", outline=max(1.2, r * 0.28))


def _star5(c: Canvas, cx, cy, r, fill, outline=None):
    pts = []
    for i in range(10):
        rr = r if i % 2 == 0 else r * 0.42
        a = math.radians(-90 + 36 * i)
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    c.poly(pts, fill=fill, outline="black", width=outline or max(0.8, r * 0.15))


EMBLEMS: dict[str, Callable[..., None]] = {
    "86": real_madrid,
    "83": barcelona,
    "364": liverpool,
    "384": crystal_palace,
    "160": psg,
    "17362": minnesota_united,
    "660": usa_men,
    "2765": usa_women,
}
