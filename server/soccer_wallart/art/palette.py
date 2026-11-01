"""E Ink Spectra 6 palette and color helpers."""
from __future__ import annotations

import colorsys

from PIL import Image

# Approximate *perceived* panel colors (used for design + preview).
COLORS: dict[str, tuple[int, int, int]] = {
    "black": (0, 0, 0),
    "white": (255, 255, 255),
    "yellow": (240, 200, 0),
    "red": (200, 30, 30),
    "blue": (30, 60, 160),
    "green": (40, 130, 60),
}
BLACK, WHITE, YELLOW, RED, BLUE, GREEN = (COLORS[k] for k in ("black", "white", "yellow", "red", "blue", "green"))
CHROMATIC = ("yellow", "red", "blue", "green")

# Panel-native 4-bit color codes for the PhotoPainter's 7.3" Spectra 6 panel (per Waveshare's driver).
NATIVE_CODE: dict[str, int] = {"black": 0x0, "white": 0x1, "yellow": 0x2, "red": 0x3, "blue": 0x5, "green": 0x6}
ORDER = ["black", "white", "yellow", "red", "blue", "green"]  # palette-image index order


def palette_image() -> Image.Image:
    p = Image.new("P", (1, 1))
    flat = [c for name in ORDER for c in COLORS[name]]
    p.putpalette(flat + [0] * (768 - len(flat)))
    return p


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def nearest(hex_color: str | None) -> str | None:
    """Map an arbitrary team color to one of the 6 panel colors by hue, not raw RGB
    distance — so 'claret' becomes red and 'sky blue' becomes blue rather than white."""
    if not hex_color:
        return None
    try:
        r, g, b = (c / 255 for c in _hex_to_rgb(hex_color))
    except ValueError:
        return None
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    if s < 0.18 or l > 0.93 or l < 0.08:
        return "white" if l >= 0.5 else "black"
    deg = h * 360
    if deg < 20 or deg >= 300:
        return "red"
    if deg < 75:
        # orange/gold: deep orange reads red, gold/yellow reads yellow
        return "red" if deg < 35 and s > 0.6 and l < 0.55 else "yellow"
    if deg < 170:
        return "green"
    if deg < 270:
        return "blue"
    return "red"  # purples/magentas read best as red on this panel


# Hand-tuned club colors where ESPN's hex values don't capture the iconic kit.
CLUB_OVERRIDES: dict[str, list[str]] = {
    "83": ["blue", "red"],       # Barcelona — blaugrana
    "86": ["white", "yellow"],   # Real Madrid
    "17362": ["black", "blue"],  # Minnesota United — black & Minnesota blue
    "382": ["blue", "white"],    # Manchester City — sky blue
    "367": ["white", "blue"],    # Tottenham
    "110": ["blue", "black"],    # Inter
    "103": ["red", "black"],     # AC Milan
    "111": ["black", "white"],   # Juventus
    "124": ["yellow", "black"],  # Dortmund
}


def team_colors(team_id: str, color: str | None, alt: str | None,
                overrides: dict[str, list[str]] | None = None) -> tuple[str, str]:
    """Return (primary, secondary) Spectra color names for a team."""
    for table in (overrides or {}, CLUB_OVERRIDES):
        if team_id in table and table[team_id]:
            cols = list(table[team_id]) + ["white"]
            return cols[0], cols[1] if cols[1] != cols[0] else ("black" if cols[0] != "black" else "white")
    p = nearest(color) or "white"
    s = nearest(alt) or ("black" if p != "black" else "white")
    if s == p:
        s = "black" if p != "black" else "white"
    return p, s


def accent(primary: str, secondary: str, avoid: tuple[str, ...] = ("black",)) -> str:
    """A team color that reads on a black background: first chromatic one, else white."""
    for c in (primary, secondary):
        if c in CHROMATIC and c not in avoid:
            return c
    return "white"


def contrast_on(bg: str) -> str:
    return "black" if bg in ("white", "yellow") else "white"
