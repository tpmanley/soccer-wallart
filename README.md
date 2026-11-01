# Soccer Wall Art

A color e-ink wall display that shows upcoming soccer matches as a retro, vintage-poster
style print: one big illustrated poster for the featured match, plus a "NEXT UP" list.

```
ESPN public API ──► render server (Python) ──► /frame.bin (800×480, 4bpp, 192 KB)
                         │ config.yaml                    ▲
                         └─ /preview.png, /gallery        │ wake → GET → draw → deep sleep
                                                     ESP32 e-paper frame
```

All artwork is drawn procedurally (sunbursts, halftone, deco stadiums, angular players,
original club shields in team colors) using only the 6 colors an E Ink Spectra 6 panel can
show, so the result is crisp with no dithering.

## Hardware

**Waveshare ESP32-S3-PhotoPainter** (~$84 with battery): a 7.3" E Ink Spectra 6 panel
(800×480, 6 colors) in a wooden photo frame with a wall hook. It has an ESP32-S3 with
8 MB PSRAM, an AXP2101 power chip and a 1500 mAh battery. See
[docs/DESIGN.md](docs/DESIGN.md) for why we chose it over the alternatives.

You also need an always-on machine on your network to run the server (Pi, NAS, Mac, small VM).

## Server

```sh
cd server
uv venv && uv pip install -e ".[dev]"     # or: python -m venv .venv && pip install -e ".[dev]"
cp config.example.yaml config.yaml         # pick your teams/leagues
.venv/bin/soccer-wallart find-team usa.1 minnesota   # look up ESPN team ids
.venv/bin/soccer-wallart render -o board.png        # one-off render with live data
.venv/bin/soccer-wallart serve --port 8080          # run the HTTP server
```

| Endpoint | |
|---|---|
| `GET /frame.bin` | Native panel buffer (2 px/byte, left pixel in high nibble). Headers `ETag` and `X-Sleep-Seconds`; replies `304` when `If-None-Match` matches. `?battery=NN` draws the battery level in the footer. |
| `GET /preview.png?scale=2` | The same image as a PNG |
| `GET /board.json` | What's on the board, for debugging |
| `GET /gallery` | Every layout rendered from offline sample data |
| `GET /healthz` | Quick health check (also used by Docker) |

The server refuses to start without a config file, and says where it looked. That way a
wrong path never quietly gives you a board without your teams.

## Running it with Docker

```sh
git clone <this repo> soccer-wallart && cd soccer-wallart
mkdir -p config && cp server/config.example.yaml config/config.yaml   # then edit it
docker compose up -d --build
curl http://localhost:8080/healthz      # {"ok": true, "teams": [...], ...}
```

- `./config` is mounted at `/config` and holds `config.yaml` plus the ESPN cache (`.cache/`). Rebuilding or recreating the container keeps both.
- The container restarts automatically (`restart: unless-stopped`) and has a health check.
- To update: `git pull && docker compose up -d --build`.
- To see logs: `docker compose logs -f`.

### On Proxmox

Use either a VM or an LXC container. For an **LXC** (e.g. Debian 12):

1. Turn on **Options → Features → Nesting**. For an unprivileged container, also turn on **keyctl**. Docker won't start inside an LXC without these. From the Proxmox host shell: `pct set <id> --features nesting=1,keyctl=1`, then restart the container.
2. In the container, install Docker (`curl -fsSL https://get.docker.com | sh`), then follow the steps above.
3. Give the container a fixed address (a static IP or a DHCP reservation on your router). The frame's `FRAME_URL` points at it, e.g. `http://192.168.1.20:8080/frame.bin`.
4. Open `http://<container-ip>:8080/preview.png` in a browser to check the board.

### How it decides what to show
- **Featured match**: the first entry in `featured_priority` that has a match in the next `lookahead_days`. `teams` means any of your teams; you can also use a league slug or a team id. A live match beats a later match at the same priority. A finished match stays up, showing the score, for `after_match_minutes`.
- **Off-season**: if nothing at all is scheduled this week, it features your team's next fixture, even if that's months away.
- **Refresh timing**: the device wakes at `daily_at`, at every listed kickoff, after each match ends, and every `live_minutes` while a match is live.
- **ETag**: hashes the board's content, not its pixels, so the frame only flashes when something actually changes.

### Art
- `art/layouts.py` holds three poster layouts: **sunburst**, **diagonal** (team-color split) and **deco** (floodlit stadium). Each match gets one, chosen by a stable hash of the match. Force one with `?layout=`.
- Team colors come from ESPN, mapped to the panel colors by hue. `CLUB_OVERRIDES` in `art/palette.py` and per-team `colors:` in the config fix clubs whose ESPN colors don't match the kit (for example, Barcelona as blue and red).
- Named derbies (El Clásico, the North London Derby, …) get a ribbon. Add more in `competitions.py`.
- Favorite clubs get a hand-drawn look-alike emblem: Minnesota United, Real Madrid, Barcelona, Liverpool, Crystal Palace and PSG so far. To add a club, write a drawing function in `art/emblems.py` and register its ESPN team id in `EMBLEMS`. Every other club gets a generated shield.
- Fonts are bundled under the SIL Open Font License: Arvo, Alfa Slab One, Bebas Neue, Jost.

Data comes from ESPN's public, unofficial site API, with no key needed. Responses are cached
on disk (`cache_ttl_minutes`), and if ESPN is unreachable the server falls back to stale
cached data.

## Firmware

```sh
cd firmware
cp include/secrets.example.h include/secrets.h   # Wi-Fi + FRAME_URL
pio run -t upload && pio device monitor
```

On each wake the device:
1. Sets up the AXP2101 power chip and connects to Wi-Fi.
2. Sends `GET /frame.bin` with the last ETag and its battery % (read from the power chip).
3. On a `304`, goes straight back to deep sleep without redrawing.
4. On a `200`, downloads the 192 KB frame into PSRAM, sends it as-is to the panel, refreshes (~25 s) and puts the panel to sleep.
5. Deep-sleeps for `X-Sleep-Seconds`, clamped to 15 minutes – 12 hours.

Press **KEY** to wake it and force a redraw. The panel driver (`src/epd_spectra6.cpp`) uses
Waveshare's init sequence, and the server's frame format matches the panel's native layout
byte for byte, so there's no image library on the device.

## Tests

```sh
cd server && .venv/bin/pytest
```

## License

MIT; see [LICENSE](LICENSE). The bundled fonts are under the SIL Open Font License
(their license files sit next to them in `server/soccer_wallart/art/fonts/`). Fixture data
comes from ESPN's public site API at runtime and isn't part of this repo; the test data in
`server/tests/fixtures/` is a minimal subset of fields, kept only for parser tests.
