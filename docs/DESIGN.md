# Soccer Wall Art — Design

## Goal

A framed color e-ink display on the wall that shows upcoming soccer matches as a retro,
vintage-poster-style print. You choose leagues (e.g. Premier League, Champions League) and
teams (e.g. Minnesota United). The layout is one big illustrated poster for the featured
match, plus a "NEXT UP" list of the following fixtures.

## Architecture

```
ESPN public API ──► render server (Python, Pillow) ──► GET /frame.bin  (800×480, 4bpp, 192 KB)
                         │ config.yaml                         ▲
                         └─ /preview.png, /gallery             │ wake → GET → refresh → deep sleep
                                                     Waveshare ESP32-S3-PhotoPainter
```

The server does all the work: it fetches fixtures, chooses what to show, draws the poster,
reduces it to the panel's 6 colors and packs it in the panel's native byte layout. The frame
is a thin client. It wakes, downloads the bytes, sends them to the panel and sleeps. This
keeps the battery-powered device simple, and lets the art change without reflashing.

---

## Decisions

### 1. Hardware: Waveshare ESP32-S3-PhotoPainter

**Requirements:** color e-ink, at least ~7" so it reads as a poster from across a room,
looks good hanging on a wall, runs on battery for weeks to months, and is reasonably cheap.

**Options considered**

| Option | Summary | Why not / why |
|---|---|---|
| Raspberry Pi Zero 2 W + Pimoroni Inky Impression (7.3" or 13.3" Spectra 6) | Everything runs in Python on the device | Needs constant mains power (a Pi doesn't deep-sleep usefully) and a separate frame. Rejected early in favor of an ESP32 battery frame. |
| Seeed reTerminal E1002 | 7.3" Spectra 6, ESP32-S3, 2000 mAh battery, ~$99 list (seen $91–127) | Best-documented Arduino path (Seeed publishes GxEPD2 examples), and our first firmware targeted it. But it comes in a plastic device housing that looks like a gadget, not wall art, and costs more. |
| DIY: Waveshare/Good Display 7.3" Spectra 6 panel + ESP32-S3 driver board | Same panel, any board | Most flexible, but we'd have to source a battery and charger, and build a frame. More work and cost for no benefit here. |
| **Waveshare ESP32-S3-PhotoPainter** ✅ | 7.3" Spectra 6 (800×480), ESP32-S3-WROOM-1-N16R8 (16 MB flash, 8 MB PSRAM), AXP2101 power chip, 1500 mAh battery, RTC, KEY button, **wooden photo frame with stand and wall hook**, ~$84 with battery | **Chosen.** |

**Why the PhotoPainter**
- **Made to hang on a wall.** It ships in a wooden photo frame with a white border and a wall hook, which suits a vintage poster far better than a plastic gadget housing.
- **Cheapest option** with a battery and an enclosure included.
- **Same panel as the alternatives** (7.3" Spectra 6, 800×480), so the server, art and frame format didn't need to change.
- **Enough memory and power features:** 8 MB PSRAM holds the whole 192 KB frame; the AXP2101 handles charging and reports battery %; the KEY button gives a "refresh now" wake.
- Everything else it has (mics, speaker, SD card, temperature/humidity sensor) is unused but harmless.

**Trade-offs we accepted**
- **Smaller battery:** 1500 mAh vs the E1002's 2000 mAh. Waveshare only says sleep current is "≤ 1 mA". At that worst case, sleep alone would drain the battery in about 2 months; the real figure should be lower but hasn't been measured. The firmware only refreshes when the content changes, which keeps the ~25 s refreshes to a few a day.
- **No vendor Arduino example for the display.** Waveshare's demo is ESP-IDF. We got the pins, power-chip setup and panel init sequence from Waveshare's own source ([waveshareteam/ESP32-S3-PhotoPainter](https://github.com/waveshareteam/ESP32-S3-PhotoPainter): `user_app.cpp`, `display_bsp.cpp`, `power_bsp.cpp`, `button_bsp.c`) and ported them to a small Arduino driver.
- **An unconfirmed community report** of resets when USB and the battery are both connected. Watch for it during bring-up.

### 2. Firmware: a minimal native driver, not GxEPD2

Waveshare's driver uses a packed 4-bit frame: byte = `y*400 + x/2`, with the even pixel in
the high nibble, and colors black=0, white=1, yellow=2, red=3, blue=5, green=6. The server
already produces exactly that layout. So the firmware streams the downloaded bytes straight
into the panel (command `0x10`) using Waveshare's init and refresh sequence, with no image
library and no per-pixel work on the device.

Pin map, from Waveshare's source:

| Function | GPIOs |
|---|---|
| e-paper | MOSI 11, SCK 10, DC 8, CS 9, RST 12, BUSY 13 (high = idle) |
| AXP2101 power chip | I2C SDA 47, SCL 48, address 0x34 |
| KEY button | GPIO 4, active-low; deep-sleep wake via ext1 with RTC pull-up |

### 3. Art: procedural, original, palette-native

**Options considered:**
- **Procedural vector art:** chosen.
- **AI-generated images per match:** richer art, but costs per image, needs an API key, and has to be dithered down to 6 colors.
- **Hybrid:** pre-made backgrounds with code-rendered text.

The reference look is the vintage soccer posters on AllPosters. Those are copyrighted, so
we generate **original** art in that style and never reuse those images or real club crests.
Shields are stylized and made up (stripes, sash, hoops and so on) in each club's colors.

Everything is drawn only in the panel's 6 colors, at 3× resolution, then downsampled and
snapped to the palette. Flat colors stay crisp with no dithering, and the halftone texture is
real vector dots. Snapping is hue-aware: blended edge pixels can only become one of the two
colors they came from, so a red/white edge never turns yellow and grey never turns green.

There are three layouts (sunburst, diagonal team-color split, deco floodlit stadium). Each
match gets one, chosen by a stable hash of the match.

### 4. Data: ESPN public site API

**Options considered:**
- **ESPN's site API:** chosen.
- **football-data.org:** its free tier doesn't include MLS.
- **API-Football:** needs a key, and has quotas.

ESPN needs no key and covers the Premier League, Champions League, MLS, La Liga and more,
including team colors. It is unofficial and could change, so the provider sits behind one
module (`data/espn.py`), responses are cached on disk, and stale cache is used if ESPN is
unreachable.

What we learned about the API:
- Date-range scoreboard queries return 400, so we query one day at a time.
- Team schedules leave out playoff matches, so we scan league scoreboards day by day and use the team schedule only for the off-season "next fixture" fallback.

### 5. Refresh timing and ETags

The server tells the device when to wake next (`X-Sleep-Seconds`): at the daily refresh
time, at each kickoff, after each match ends, and every 30 minutes while a match is live.
The bounds are 15 minutes to 12 hours.

The ETag hashes the board's *content* (matches, states, scores, local date, battery decile),
not its pixels. A wake where nothing changed costs one HTTP request and no 25 s refresh flash.

---

## Bring-up checklist (first time on real hardware)

1. Flash and watch the serial log. Expect `pmic` init OK, Wi-Fi OK, `GET … -> 200`, then the refresh, then `sleeping N s`.
2. Check the colors and orientation match `/preview.png`. If the image is mirrored or rotated, fix it on the server rather than on the device.
3. Press KEY and confirm it wakes and redraws.
4. Leave it on battery for a few days and track the battery % in the poster footer, to estimate real battery life.
5. Confirm the panel's deep-sleep command (`0x07 0xA5`, the usual one for this controller family) behaves. It isn't in Waveshare's driver; if the panel misbehaves, remove `epd::sleep()`.
