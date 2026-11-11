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

// Survives deep sleep (lost on a full power loss, which just means one extra redraw).
RTC_DATA_ATTR char lastEtag[40] = "";
// Last access point, so the next wake can skip the Wi-Fi scan.
RTC_DATA_ATTR uint8_t lastBssid[6];
RTC_DATA_ATTR int32_t lastChannel = 0;

static XPowersPMU pmu;
static bool pmuOk = false;

// Wake the AXP2101 from the sleep mode set in pmicSleep(), the way Waveshare's power test does:
// a low pulse on its IRQ line.
static void wakePmic() {
  pinMode(PMIC_IRQ_PIN, OUTPUT);
  digitalWrite(PMIC_IRQ_PIN, LOW);
  delay(100);
  digitalWrite(PMIC_IRQ_PIN, HIGH);
  delay(200);
  pinMode(PMIC_IRQ_PIN, INPUT_PULLUP);
}

// Same rail/charger setup as Waveshare's power_bsp.cpp (Custom_PmicRegisterInit), plus switching
// the 3.3 V rails back on, since pmicSleep() turned them off.
static void initPmic() {
  wakePmic();
  pmuOk = pmu.begin(Wire, PMIC_ADDR, PMIC_SDA_PIN, PMIC_SCL_PIN);
  if (!pmuOk) {
    Serial.println("pmic: init failed");
    return;
  }
  pmu.disableSleep();
  pmu.setVbusCurrentLimit(XPOWERS_AXP2101_VBUS_CUR_LIM_2000MA);
  if (pmu.getDC1Voltage() != 3300) pmu.setDC1Voltage(3300);
  if (pmu.getALDO1Voltage() != 3300) pmu.setALDO1Voltage(3300);
  if (pmu.getALDO2Voltage() != 3300) pmu.setALDO2Voltage(3300);
  if (pmu.getALDO3Voltage() != 3300) pmu.setALDO3Voltage(3300);
  if (pmu.getALDO4Voltage() != 3300) pmu.setALDO4Voltage(3300);
  pmu.enableALDO1();
  pmu.enableALDO2();
  pmu.enableALDO3();
  pmu.enableALDO4();
  pmu.setPrechargeCurr(XPOWERS_AXP2101_PRECHARGE_50MA);
  pmu.setChargerConstantCurr(XPOWERS_AXP2101_CHG_CUR_500MA);
  pmu.setChargerTerminationCurr(XPOWERS_AXP2101_CHG_ITERM_25MA);
}

// Before deep sleep: cut every rail except DC1 (the ESP32's own supply), which powers down the
// panel, SD card, audio codec, amplifier and sensor. Sequence from Waveshare's power test
// (04_PowerConsumptionTest/bsp_fac.h, axp_basic_sleep_start). Unlike theirs, battery measurement
// stays on so the fuel gauge keeps tracking.
static void pmicSleep() {
  if (!pmuOk) return;
  pmu.disableIRQ(XPOWERS_AXP2101_ALL_IRQ);
  pmu.clearIrqStatus();
  pmu.wakeupControl(XPOWERS_AXP2101_WAKEUP_DC_DLO_SELECT, true);
  pmu.wakeupControl(XPOWERS_AXP2101_WAKEUP_PWROK_TO_LOW, false);
  pmu.wakeupControl(XPOWERS_AXP2101_WAKEUP_IRQ_PIN_TO_LOW, true);
  pmu.enableSleep();
  pmu.disableDC2();
  pmu.disableDC3();
  pmu.disableDC4();
  pmu.disableDC5();
  pmu.disableALDO1();
  pmu.disableALDO2();
  pmu.disableALDO3();
  pmu.disableALDO4();
  pmu.disableBLDO1();
  pmu.disableBLDO2();
  pmu.disableCPUSLDO();
  pmu.disableDLDO1();
  pmu.disableDLDO2();
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
  pmicSleep();
  esp_sleep_enable_timer_wakeup((uint64_t)seconds * 1000000ULL);
  // KEY (GPIO4) is active-low; keep it pulled up in deep sleep, as Waveshare's firmware does.
  rtc_gpio_pulldown_dis((gpio_num_t)KEY_BUTTON_PIN);
  rtc_gpio_pullup_en((gpio_num_t)KEY_BUTTON_PIN);
  esp_sleep_enable_ext1_wakeup(1ULL << KEY_BUTTON_PIN, ESP_EXT1_WAKEUP_ANY_LOW);
  esp_deep_sleep_start();
}

static bool waitForWifi(uint32_t timeoutMs) {
  uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED) {
    if (millis() - start > timeoutMs) return false;
    delay(50);
  }
  return true;
}

static bool connectWifi() {
  WiFi.persistent(false);  // don't rewrite the credentials to flash on every wake
  WiFi.mode(WIFI_STA);
  bool ok = false;
  if (lastChannel > 0) {
    // Fast path: go straight to the last access point and channel, skipping the scan.
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD, lastChannel, lastBssid);
    ok = waitForWifi(5000);
    if (!ok) {
      Serial.println("wifi: cached AP failed, scanning");
      WiFi.disconnect();
    }
  }
  if (!ok) {
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    ok = waitForWifi(WIFI_TIMEOUT_MS);
  }
  if (!ok) {
    lastChannel = 0;
    return false;
  }
  lastChannel = WiFi.channel();
  memcpy(lastBssid, WiFi.BSSID(), sizeof(lastBssid));
  Serial.printf("wifi ok %s (ch %d)\n", WiFi.localIP().toString().c_str(), (int)lastChannel);
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
  WiFi.mode(WIFI_OFF);    // save power during the long refresh
  setCpuFrequencyMhz(80);  // the CPU only waits on the panel from here on

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
