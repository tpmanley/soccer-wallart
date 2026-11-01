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

Docker: `docker build -t soccer-wallart . && docker run -p 8080:8080 -v $PWD/server:/config soccer-wallart`
(the mounted directory must contain `config.yaml`).

### How it decides what to show
- **Featured match**: the first entry in `featured_priority` that has a match in the next `lookahead_days`. `teams` means any of your teams; you can also use a league slug or a team id. A live match beats a later match at the same priority. A finished match stays up, showing the score, for `after_match_minutes`.
- **Off-season**: if nothing at all is scheduled this week, it features your team's next fixture, even if that's months away.
- **Refresh timing**: the device wakes at `daily_at`, at every listed kickoff, after each match ends, and every `live_minutes` while a match is live.
- **ETag**: hashes the board's content, not its pixels, so the frame only flashes when something actually changes.

### Art
- `art/layouts.py` holds three poster layouts: **sunburst**, **diagonal** (team-color split) and **deco** (floodlit stadium). Each match gets one, chosen by a stable hash of the match. Force one with `?layout=`.
- Team colors come from ESPN, mapped to the panel colors by hue. `CLUB_OVERRIDES` in `art/palette.py` and per-team `colors:` in the config fix clubs whose ESPN colors don't match the kit (for example, Barcelona as blue and red).
- Named derbies (El Clásico, the North London Derby, …) get a ribbon. Add more in `competitions.py`.
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
