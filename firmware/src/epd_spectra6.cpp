#include "epd_spectra6.h"

#include <SPI.h>

#include "config.h"

namespace epd {
namespace {
SPIClass spi(FSPI);
const SPISettings kSettings(EPD_SPI_HZ, MSBFIRST, SPI_MODE0);

void waitIdle(uint32_t timeoutMs = 60000) {
  uint32_t start = millis();
  while (digitalRead(EPD_BUSY_PIN) == LOW) {
    if (millis() - start > timeoutMs) {
      Serial.println("epd: busy timeout");
      return;
    }
    delay(10);
  }
}

void command(uint8_t c) {
  digitalWrite(EPD_DC_PIN, LOW);
  digitalWrite(EPD_CS_PIN, LOW);
  spi.beginTransaction(kSettings);
  spi.transfer(c);
  spi.endTransaction();
  digitalWrite(EPD_CS_PIN, HIGH);
}

void data(std::initializer_list<uint8_t> bytes) {
  digitalWrite(EPD_DC_PIN, HIGH);
  for (uint8_t b : bytes) {
    digitalWrite(EPD_CS_PIN, LOW);
    spi.beginTransaction(kSettings);
    spi.transfer(b);
    spi.endTransaction();
    digitalWrite(EPD_CS_PIN, HIGH);
  }
}

void cmd(uint8_t c, std::initializer_list<uint8_t> bytes) {
  command(c);
  data(bytes);
}
}  // namespace

void begin() {
  pinMode(EPD_CS_PIN, OUTPUT);
  pinMode(EPD_DC_PIN, OUTPUT);
  pinMode(EPD_RST_PIN, OUTPUT);
  pinMode(EPD_BUSY_PIN, INPUT);
  digitalWrite(EPD_CS_PIN, HIGH);
  spi.begin(EPD_SCK_PIN, -1, EPD_MOSI_PIN, -1);
}

void init() {
  digitalWrite(EPD_RST_PIN, HIGH);
  delay(50);
  digitalWrite(EPD_RST_PIN, LOW);
  delay(20);
  digitalWrite(EPD_RST_PIN, HIGH);
  delay(50);
  waitIdle();
  delay(50);

  cmd(0xAA, {0x49, 0x55, 0x20, 0x08, 0x09, 0x18});
  cmd(0x01, {0x3F});
  cmd(0x00, {0x5F, 0x69});
  cmd(0x03, {0x00, 0x54, 0x00, 0x44});
  cmd(0x05, {0x40, 0x1F, 0x1F, 0x2C});
  cmd(0x06, {0x6F, 0x1F, 0x17, 0x49});
  cmd(0x08, {0x6F, 0x1F, 0x1F, 0x22});
  cmd(0x30, {0x03});
  cmd(0x50, {0x3F});
  cmd(0x60, {0x02, 0x00});
  cmd(0x61, {0x03, 0x20, 0x01, 0xE0});  // 800 x 480
  cmd(0x84, {0x01});
  cmd(0xE3, {0x2F});
  command(0x04);  // power on
  waitIdle();
}

void writeFrame(const uint8_t* buf, size_t len) {
  command(0x10);
  digitalWrite(EPD_DC_PIN, HIGH);
  digitalWrite(EPD_CS_PIN, LOW);
  spi.beginTransaction(kSettings);
  spi.writeBytes(buf, len);
  spi.endTransaction();
  digitalWrite(EPD_CS_PIN, HIGH);
}

void refresh() {
  command(0x04);  // power on
  waitIdle();
  cmd(0x06, {0x6F, 0x1F, 0x17, 0x49});
  cmd(0x12, {0x00});  // display refresh
  waitIdle();
  cmd(0x02, {0x00});  // power off
  waitIdle();
}

void sleep() {
  cmd(0x07, {0xA5});  // deep sleep; only a hardware reset wakes it
}
}  // namespace epd
