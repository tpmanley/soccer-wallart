#pragma once
// Minimal driver for the 7.3" E Ink Spectra 6 panel on the Waveshare ESP32-S3-PhotoPainter.
//
// The init/refresh command sequence mirrors Waveshare's reference driver
// (components/port_bsp/display_bsp.cpp). The panel takes a packed 4-bit frame:
// byte index = y * 400 + x / 2, even x in the high nibble, colors
// black=0 white=1 yellow=2 red=3 blue=5 green=6 — exactly what the server's /frame.bin sends.
#include <Arduino.h>

namespace epd {
void begin();                               // SPI + GPIO setup
void init();                                // reset + panel init + power on
void writeFrame(const uint8_t* buf, size_t len);  // send full 192000-byte frame
void refresh();                             // power on, refresh (~25 s), power off
void sleep();                               // deep sleep; needs init() to wake
}  // namespace epd
