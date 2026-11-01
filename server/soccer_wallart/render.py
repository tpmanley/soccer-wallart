"""Turn a supersampled design into panel pixels: downsample, snap to 6 colors, pack 4bpp."""
from __future__ import annotations

import io

import numpy as np
from PIL import Image

from .art.canvas import DESIGN_H, DESIGN_W
from .art.palette import COLORS, NATIVE_CODE, ORDER


_HUES = {"red": 0.0, "yellow": 50.0, "green": 140.0, "blue": 225.0}


def snap(img: Image.Image) -> np.ndarray:
    """Return an (H, W) array of palette indices into ORDER.

    Anti-aliased edges are blends of two palette colors, and plain RGB distance maps those
    blends badly (red+white "pink" lands on yellow, grey edges land on green). So:
      * low-chroma pixels may only become black or white;
      * other pixels pick the chromatic color nearest in *hue*, then choose between that
        color, black and white by RGB distance.
    """
    a = np.asarray(img.convert("RGB"), dtype=np.float32)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    mx, mn = a.max(-1), a.min(-1)
    chroma = mx - mn
    safe = np.where(chroma == 0, 1, chroma)
    hue = np.where(mx == r, ((g - b) / safe) % 6,
                   np.where(mx == g, (b - r) / safe + 2, (r - g) / safe + 4)) * 60.0

    names = list(_HUES)
    hue_d = np.stack([np.minimum(abs(hue - h), 360 - abs(hue - h)) for h in _HUES.values()], -1)
    chroma_pick = np.array([ORDER.index(n) for n in names])[hue_d.argmin(-1)]  # (H, W) palette idx

    pal = np.array([COLORS[n] for n in ORDER], dtype=np.float32)
    def dist(idx):
        return ((a - pal[idx]) ** 2).sum(-1)
    d_black = dist(np.zeros_like(chroma_pick))
    d_white = dist(np.ones_like(chroma_pick))
    d_chroma = dist(chroma_pick)
    d_chroma = np.where(chroma < 48, np.inf, d_chroma)

    out = np.where(d_black <= d_white, 0, 1)
    best = np.minimum(d_black, d_white)
    out = np.where(d_chroma < best, chroma_pick, out)
    return out.astype(np.uint8)


def to_panel(design: Image.Image, width: int = DESIGN_W, height: int = DESIGN_H) -> np.ndarray:
    """Fit the 800x480 design into the panel (letterboxed in white if aspect differs)."""
    scale = min(width / DESIGN_W, height / DESIGN_H)
    w, h = round(DESIGN_W * scale), round(DESIGN_H * scale)
    # BOX (area average) rather than LANCZOS: no ringing halos around flat shapes.
    small = design.resize((w, h), Image.BOX)
    if (w, h) != (width, height):
        canvas = Image.new("RGB", (width, height), COLORS["white"])
        canvas.paste(small, ((width - w) // 2, (height - h) // 2))
        small = canvas
    return snap(small)


def indices_to_png(idx: np.ndarray, upscale: int = 1) -> bytes:
    pal = np.array([COLORS[n] for n in ORDER], dtype=np.uint8)
    img = Image.fromarray(pal[idx], "RGB")
    if upscale > 1:
        img = img.resize((img.width * upscale, img.height * upscale), Image.NEAREST)
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def pack_native(idx: np.ndarray) -> bytes:
    """Pack to the panel's native 4-bit format: 2 px/byte, left pixel in the high nibble."""
    lut = np.array([NATIVE_CODE[n] for n in ORDER], dtype=np.uint8)
    codes = lut[idx]
    if codes.shape[1] % 2:
        raise ValueError("panel width must be even")
    return ((codes[:, 0::2] << 4) | codes[:, 1::2]).astype(np.uint8).tobytes()
