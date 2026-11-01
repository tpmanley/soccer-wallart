"""Command line: preview renders, team id lookup, and running the server."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from .config import load_config


def _service(args):
    from .service import Service
    return Service(load_config(args.config))


def cmd_render(args):
    """Render the live board (real ESPN data) to a PNG + native .bin."""
    svc = _service(args)
    frame = svc.frame(layout=args.layout)
    out = Path(args.out)
    out.write_bytes(frame.png)
    out.with_suffix(".bin").write_bytes(frame.native)
    b = frame.board
    print(f"featured: {b.featured.home.name} vs {b.featured.away.name} ({b.featured.competition.name})"
          if b.featured else "featured: none")
    for m in b.upcoming:
        print(f"  {m.kickoff:%Y-%m-%d %H:%MZ}  {m.competition.slug:16} {m.home.name} vs {m.away.name}")
    print(f"wrote {out} and {out.with_suffix('.bin')}; next wake in {frame.sleep_seconds}s; etag {frame.etag}")


def cmd_gallery(args):
    """Render every layout with offline sample data."""
    from .art.layouts import LAYOUTS
    from .sample import sample_board, sample_matches
    from .service import Service
    cfg = load_config(args.config)
    svc = Service(cfg, provider=None)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    ids = [args.match] if args.match else [m.id for m in sample_matches()]
    for mid in ids:
        for name in LAYOUTS:
            b = sample_board(mid)
            f = svc.render(b, b.generated_at, layout=name)
            path = out / f"{mid}-{name}.png"
            path.write_bytes(f.png)
            print("wrote", path)


def cmd_find_team(args):
    from .data.cache import JsonCache
    from .data.espn import EspnProvider
    cfg = load_config(args.config)
    p = EspnProvider(JsonCache(cfg.cache_dir, cfg.cache_ttl_minutes * 60))
    hits = p.find_team(args.league, args.query)
    if not hits:
        print(f"no team matching {args.query!r} in {args.league}", file=sys.stderr)
        return 1
    for h in hits:
        print(f"{h['id']:>8}  {h['abbreviation']:5} {h['name']}")


def cmd_serve(args):
    import os
    import uvicorn
    if args.config:
        os.environ["SOCCER_WALLART_CONFIG"] = args.config
    uvicorn.run("soccer_wallart.app:app", host=args.host, port=args.port)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="soccer-wallart")
    ap.add_argument("-c", "--config", default=None, help="config.yaml path")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("render", help="render the live board to PNG/.bin")
    r.add_argument("-o", "--out", default="board.png")
    r.add_argument("--layout", choices=["sunburst", "diagonal", "deco"])
    r.set_defaults(fn=cmd_render)

    g = sub.add_parser("gallery", help="render all layouts from sample data")
    g.add_argument("-o", "--out", default="gallery")
    g.add_argument("--match", help="sample match id (s1..s6)")
    g.set_defaults(fn=cmd_gallery)

    f = sub.add_parser("find-team", help="look up an ESPN team id")
    f.add_argument("league", help="ESPN league slug, e.g. usa.1, eng.1")
    f.add_argument("query")
    f.set_defaults(fn=cmd_find_team)

    s = sub.add_parser("serve", help="run the HTTP server")
    s.add_argument("--host", default="0.0.0.0")
    s.add_argument("--port", type=int, default=8080)
    s.set_defaults(fn=cmd_serve)

    args = ap.parse_args(argv)
    return args.fn(args) or 0


if __name__ == "__main__":
    sys.exit(main())
