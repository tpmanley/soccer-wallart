"""HTTP API for the e-ink frame.

  GET /frame.bin   packed 4bpp native buffer for the panel; honours If-None-Match.
                   Headers: ETag, X-Sleep-Seconds. Query: battery=<0-100>, layout=<name>
  GET /preview.png the same image as a PNG (?scale=2 for a bigger view)
  GET /board.json  what's on the board (debugging)
  GET /gallery     every layout rendered from offline sample data
  GET /gallery/{match}/{layout}.png
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse

from .art.layouts import LAYOUTS
from .config import load_config
from .sample import sample_board, sample_matches
from .service import Frame, Service

app = FastAPI(title="Soccer Wall Art")
_cfg = load_config()
_svc = Service(_cfg)
_lock = threading.Lock()
_memo: dict[tuple, tuple[float, Frame]] = {}
MEMO_SECONDS = 60


def _frame(layout: str | None, battery: int | None) -> Frame:
    """Render at most once a minute per (layout, battery bucket); ESPN data is cached separately."""
    key = (layout, None if battery is None else battery // 10)
    with _lock:
        hit = _memo.get(key)
        if hit and time.time() - hit[0] < MEMO_SECONDS:
            return hit[1]
        frame = _svc.frame(datetime.now(timezone.utc), layout=layout, battery=battery)
        _memo[key] = (time.time(), frame)
        return frame


def _check_layout(layout: str | None):
    if layout is not None and layout not in LAYOUTS:
        raise HTTPException(400, f"unknown layout; choose from {sorted(LAYOUTS)}")


@app.get("/frame.bin")
def frame_bin(request: Request, battery: int | None = Query(None, ge=0, le=100), layout: str | None = None):
    _check_layout(layout)
    f = _frame(layout, battery)
    headers = {"ETag": f'"{f.etag}"', "X-Sleep-Seconds": str(f.sleep_seconds), "Cache-Control": "no-cache"}
    inm = request.headers.get("if-none-match", "").strip('"')
    if inm == f.etag:
        return Response(status_code=304, headers=headers)
    return Response(f.native, media_type="application/octet-stream", headers=headers)


@app.get("/preview.png")
def preview(layout: str | None = None, battery: int | None = Query(None, ge=0, le=100),
            scale: int = Query(1, ge=1, le=4)):
    _check_layout(layout)
    f = _frame(layout, battery)
    png = f.png if scale == 1 else _rescale(f.png, scale)
    return Response(png, media_type="image/png", headers={"X-Sleep-Seconds": str(f.sleep_seconds)})


def _rescale(png: bytes, scale: int) -> bytes:
    import io
    from PIL import Image
    im = Image.open(io.BytesIO(png))
    buf = io.BytesIO()
    im.resize((im.width * scale, im.height * scale), Image.NEAREST).save(buf, "PNG")
    return buf.getvalue()


@app.get("/board.json")
def board_json():
    f = _frame(None, None)

    def m(x):
        return None if x is None else {
            "id": x.id, "competition": x.competition.slug, "home": x.home.name, "away": x.away.name,
            "kickoff": x.kickoff.isoformat(), "state": x.state, "score": [x.home_score, x.away_score],
            "venue": x.venue,
        }
    return {"featured": m(f.board.featured), "upcoming": [m(x) for x in f.board.upcoming],
            "etag": f.etag, "sleep_seconds": f.sleep_seconds}


@app.get("/gallery", response_class=HTMLResponse)
def gallery():
    rows = []
    for mt in sorted(sample_matches(), key=lambda x: x.id):
        imgs = "".join(
            f'<figure><img src="/gallery/{mt.id}/{name}.png" width="800" height="480">'
            f"<figcaption>{name}</figcaption></figure>" for name in LAYOUTS)
        rows.append(f"<h2>{mt.home.name} vs {mt.away.name}</h2><div class=row>{imgs}</div>")
    return ("<!doctype html><title>Soccer Wall Art gallery</title><style>body{font-family:sans-serif;"
            "background:#888;margin:20px}.row{display:flex;gap:16px;flex-wrap:wrap}figure{margin:0}"
            "img{image-rendering:pixelated;box-shadow:0 2px 8px #0006}</style>" + "".join(rows))


@app.get("/gallery/{match_id}/{layout}.png")
def gallery_png(match_id: str, layout: str):
    _check_layout(layout)
    if match_id not in {m.id for m in sample_matches()}:
        raise HTTPException(404)
    b = sample_board(match_id)
    f = _svc.render(b, b.generated_at, layout=layout)
    return Response(f.png, media_type="image/png")
