// Soccer Wall Art — Waveshare ESP32-S3-PhotoPainter client.
//
// Each wake: PMIC setup → Wi-Fi → GET FRAME_URL (If-None-Match: last ETag) → on 200 push the
// 4bpp frame to the panel and refresh → deep sleep for X-Sleep-Seconds. A 304 skips the
// refresh entirely, which saves battery and avoids the ~25 s full-color refresh flash.
// Pressing KEY wakes the frame and forces a redraw.

#include <Arduino.h>
#include <HTTPClient.h>
#include <WiFi.h>
#include <Wire.h>
#include <driver/rtc_io.h>
#include <esp_sleep.h>

#define XPOWERS_CHIP_AXP2101
#include <XPowersLib.h>

#include "config.h"
#include "epd_spectra6.h"
#if __has_include("secrets.h")
#include "secrets.h"
#else
#error "Copy include/secrets.example.h to include/secrets.h and fill it in"
#endif

static const size_t FRAME_BYTES = PANEL_W * PANEL_H / 2;

// Survives deep sleep.
RTC_DATA_ATTR char lastEtag[40] = "";

static XPowersPMU pmu;
static bool pmuOk = false;

// Same rail/charger setup as Waveshare's power_bsp.cpp (Custom_PmicRegisterInit).
static void initPmic() {
  pmuOk = pmu.begin(Wire, PMIC_ADDR, PMIC_SDA_PIN, PMIC_SCL_PIN);
  if (!pmuOk) {
    Serial.println("pmic: init failed");
    return;
  }
  pmu.setVbusCurrentLimit(XPOWERS_AXP2101_VBUS_CUR_LIM_2000MA);
  if (pmu.getDC1Voltage() != 3300) pmu.setDC1Voltage(3300);
  if (pmu.getALDO1Voltage() != 3300) pmu.setALDO1Voltage(3300);
  if (pmu.getALDO2Voltage() != 3300) pmu.setALDO2Voltage(3300);
  if (pmu.getALDO3Voltage() != 3300) pmu.setALDO3Voltage(3300);
  if (pmu.getALDO4Voltage() != 3300) pmu.setALDO4Voltage(3300);
  pmu.setPrechargeCurr(XPOWERS_AXP2101_PRECHARGE_50MA);
  pmu.setChargerConstantCurr(XPOWERS_AXP2101_CHG_CUR_500MA);
  pmu.setChargerTerminationCurr(XPOWERS_AXP2101_CHG_ITERM_25MA);
}

static int batteryPercent() {
  if (!pmuOk || !pmu.isBatteryConnect()) return -1;
  int pct = pmu.getBatteryPercent();
  return (pct >= 0 && pct <= 100) ? pct : -1;
}

static void goToSleep(uint32_t seconds) {
  if (seconds < SLEEP_MIN_S) seconds = SLEEP_MIN_S;
  if (seconds > SLEEP_MAX_S) seconds = SLEEP_MAX_S;
  Serial.printf("sleeping %u s\n", seconds);
  Serial.flush();
  WiFi.disconnect(true);
  WiFi.mode(WIFI_OFF);
  esp_sleep_enable_timer_wakeup((uint64_t)seconds * 1000000ULL);
  // KEY (GPIO4) is active-low; keep it pulled up in deep sleep, as Waveshare's firmware does.
  rtc_gpio_pulldown_dis((gpio_num_t)KEY_BUTTON_PIN);
  rtc_gpio_pullup_en((gpio_num_t)KEY_BUTTON_PIN);
  esp_sleep_enable_ext1_wakeup(1ULL << KEY_BUTTON_PIN, ESP_EXT1_WAKEUP_ANY_LOW);
  esp_deep_sleep_start();
}

static bool connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED) {
    if (millis() - start > WIFI_TIMEOUT_MS) return false;
    delay(100);
  }
  Serial.printf("wifi ok %s\n", WiFi.localIP().toString().c_str());
  return true;
}

void setup() {
  Serial.begin(115200);
  delay(200);
  bool forced = esp_sleep_get_wakeup_cause() == ESP_SLEEP_WAKEUP_EXT1;
  Serial.printf("wake cause %d, last etag '%s'%s\n", (int)esp_sleep_get_wakeup_cause(), lastEtag,
                forced ? " (KEY pressed: forcing redraw)" : "");

  initPmic();

  if (!connectWifi()) {
    Serial.println("wifi failed");
    goToSleep(SLEEP_ON_ERROR_S);
  }

  String url = FRAME_URL;
  int batt = batteryPercent();
  if (batt >= 0) url += String(url.indexOf('?') >= 0 ? "&" : "?") + "battery=" + batt;

  HTTPClient http;
  http.setTimeout(HTTP_TIMEOUT_MS);
  http.begin(url);
  const char* keep[] = {"ETag", "X-Sleep-Seconds"};
  http.collectHeaders(keep, 2);
  if (lastEtag[0] && !forced) http.addHeader("If-None-Match", String("\"") + lastEtag + "\"");

  int code = http.GET();
  uint32_t sleepS = http.header("X-Sleep-Seconds").toInt();
  if (sleepS == 0) sleepS = SLEEP_ON_ERROR_S;
  Serial.printf("GET %s -> %d, sleep %u\n", url.c_str(), code, sleepS);

  if (code == 304) {
    http.end();
    goToSleep(sleepS);
  }
  if (code != 200) {
    http.end();
    goToSleep(SLEEP_ON_ERROR_S);
  }

  uint8_t* buf = (uint8_t*)ps_malloc(FRAME_BYTES);
  if (!buf) {
    Serial.println("no PSRAM for frame");
    http.end();
    goToSleep(SLEEP_ON_ERROR_S);
  }
  WiFiClient* stream = http.getStreamPtr();
  size_t got = 0;
  uint32_t start = millis();
  while (got < FRAME_BYTES && (http.connected() || stream->available()) && millis() - start < HTTP_TIMEOUT_MS) {
    size_t avail = stream->available();
    if (avail) {
      got += stream->readBytes(buf + got, min(avail, FRAME_BYTES - got));
    } else {
      delay(2);
    }
  }
  String etag = http.header("ETag");
  http.end();
  WiFi.disconnect(true);
  WiFi.mode(WIFI_OFF);  // save power during the long refresh

  if (got != FRAME_BYTES) {
    Serial.printf("short read %u/%u\n", (unsigned)got, (unsigned)FRAME_BYTES);
    free(buf);
    goToSleep(SLEEP_ON_ERROR_S);
  }

  epd::begin();
  epd::init();
  epd::writeFrame(buf, FRAME_BYTES);
  epd::refresh();
  epd::sleep();
  free(buf);

  etag.replace("\"", "");
  strncpy(lastEtag, etag.c_str(), sizeof(lastEtag) - 1);
  goToSleep(sleepS);
}

void loop() {}
