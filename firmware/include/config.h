#pragma once
// Pin map for the Waveshare ESP32-S3-PhotoPainter, taken from Waveshare's own firmware
// (github.com/waveshareteam/ESP32-S3-PhotoPainter: user_app.cpp, power_bsp.h, config.h).
// Copy include/secrets.example.h to include/secrets.h and fill in Wi-Fi + server URL.

// --- e-paper (SPI) ---
#define EPD_SCK_PIN   10
#define EPD_MOSI_PIN  11
#define EPD_DC_PIN    8
#define EPD_CS_PIN    9
#define EPD_RST_PIN   12
#define EPD_BUSY_PIN  13      // HIGH = idle
#define EPD_SPI_HZ    20000000

// --- AXP2101 power management IC (I2C) ---
#define PMIC_SDA_PIN  47
#define PMIC_SCL_PIN  48
#define PMIC_ADDR     0x34

// --- KEY button: wakes the frame for an immediate refresh (active LOW) ---
#define KEY_BUTTON_PIN 4

// --- panel ---
#define PANEL_W 800
#define PANEL_H 480

// --- sleep bounds (server sends X-Sleep-Seconds; these clamp it) ---
#define SLEEP_MIN_S        (15 * 60)
#define SLEEP_MAX_S        (12 * 3600)
#define SLEEP_ON_ERROR_S   (60 * 60)
#define WIFI_TIMEOUT_MS    20000
#define HTTP_TIMEOUT_MS    30000
