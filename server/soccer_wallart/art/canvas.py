"""Supersampled drawing surface in 800x480 'design units'."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw, ImageFont

from .palette import COLORS

FONT_DIR = Path(__file__).parent / "fonts"
DESIGN_W, DESIGN_H = 800, 480


@lru_cache(maxsize=256)
def _font(file: str, px: int, weight: int | None = None) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(FONT_DIR / file), px)
    if weight is not None:
        f.set_variation_by_axes([weight])
    return f


def C(color) -> tuple[int, int, int]:
    return COLORS[color] if isinstance(color, str) else color


class Canvas:
    def __init__(self, scale: float = 3.0, bg="white"):
        self.s = scale
        self.img = Image.new("RGB", (round(DESIGN_W * scale), round(DESIGN_H * scale)), C(bg))
        self.d = ImageDraw.Draw(self.img)

    # -- coordinates -------------------------------------------------------
    def P(self, *pts):
        return [(x * self.s, y * self.s) for x, y in pts]

    def w(self, width: float) -> int:
        return max(1, round(width * self.s))

    # -- fonts (sizes in design units) -------------------------------------
    def slab(self, size: float):      # Rockwell-ish slab serif for names
        return _font("Arvo-Bold.ttf", round(size * self.s))

    def heavy_slab(self, size: float):
        return _font("AlfaSlabOne-Regular.ttf", round(size * self.s))

    def condensed(self, size: float):  # DIN-ish condensed caps
        return _font("BebasNeue-Regular.ttf", round(size * self.s))

    def geo(self, size: float, weight: int = 700):  # Futura-ish geometric sans
        return _font("Jost-Variable.ttf", round(size * self.s), weight)

    # -- primitives ----------------------------------------------------------
    def rect(self, x0, y0, x1, y1, fill=None, outline=None, width=0):
        self.d.rectangle(self.P((x0, y0), (x1, y1)), fill=fill and C(fill),
                         outline=outline and C(outline), width=self.w(width) if outline else 0)

    def poly(self, pts, fill=None, outline=None, width=0):
        self.d.polygon(self.P(*pts), fill=fill and C(fill), outline=outline and C(outline),
                       width=self.w(width) if outline else 0)

    def ellipse(self, cx, cy, rx, ry=None, fill=None, outline=None, width=0):
        ry = rx if ry is None else ry
        self.d.ellipse(self.P((cx - rx, cy - ry), (cx + rx, cy + ry)), fill=fill and C(fill),
                       outline=outline and C(outline), width=self.w(width) if outline else 0)

    def line(self, pts, fill, width=1):
        self.d.line(self.P(*pts), fill=C(fill), width=self.w(width))

    # -- layers ----------------------------------------------------------------
    def layer(self, bg) -> "Canvas":
        """A same-size scratch canvas, to be composited through a mask."""
        return Canvas(self.s, bg)

    def paste_clipped(self, layer: "Canvas", clip: Callable[[ImageDraw.ImageDraw, "Canvas"], None]):
        mask = Image.new("L", self.img.size, 0)
        clip(ImageDraw.Draw(mask), self)
        self.img.paste(layer.img, (0, 0), mask)
        self.d = ImageDraw.Draw(self.img)

    def paste_rect(self, layer: "Canvas", x0, y0, x1, y1):
        self.paste_clipped(layer, lambda md, c: md.rectangle(c.P((x0, y0), (x1, y1)), fill=255))

    def paste_poly(self, layer: "Canvas", pts):
        self.paste_clipped(layer, lambda md, c: md.polygon(c.P(*pts), fill=255))

    # -- text ------------------------------------------------------------------
    def text_width(self, s: str, font, spacing: float = 0) -> float:
        if not s:
            return 0
        if not spacing:
            return self.d.textlength(s, font=font) / self.s
        return (sum(self.d.textlength(ch, font=font) for ch in s) + spacing * self.s * (len(s) - 1)) / self.s

    def text(self, x, y, s: str, font, fill, anchor="la", spacing: float = 0):
        """anchor: first char l/m/r horizontal, second char a/m/s/d vertical (PIL anchors)."""
        if not spacing:
            self.d.text((x * self.s, y * self.s), s, font=font, fill=C(fill), anchor=anchor)
            return
        total = self.text_width(s, font, spacing)
        if anchor[0] == "m":
            x -= total / 2
        elif anchor[0] == "r":
            x -= total
        cx = x * self.s
        for ch in s:
            self.d.text((cx, y * self.s), ch, font=font, fill=C(fill), anchor="l" + anchor[1])
            cx += self.d.textlength(ch, font=font) + spacing * self.s

    def fit(self, s: str, font_fn, max_size: float, max_width: float, min_size: float = 8,
            spacing: float = 0):
        """Largest font (from font_fn(size)) such that s fits within max_width. Returns (font, size)."""
        size = max_size
        while size > min_size:
            f = font_fn(size)
            if self.text_width(s, f, spacing) <= max_width:
                return f, size
            size -= 1
        return font_fn(min_size), min_size
