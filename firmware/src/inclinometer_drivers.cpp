#include "inclinometer_drivers.h"

#include "atcore/adxl355.h"
#include "atcore/scl3300.h"
#include "config.h"

using namespace atc;

// =============================== SCL3300-D01 ===============================================

uint32_t Scl3300Driver::transfer(uint32_t frame) {
  spi_.beginTransaction(SPISettings(SPI_SCL3300_HZ, MSBFIRST, SPI_MODE0));
  digitalWrite(cs_, LOW);
  delayMicroseconds(1);
  const uint32_t r = spi_.transfer32(frame);
  digitalWrite(cs_, HIGH);
  spi_.endTransaction();
  delayMicroseconds(12);               // CS haut ≥ 10 µs entre deux trames
  return r;
}

bool Scl3300Driver::begin() {
  pinMode(cs_, OUTPUT);
  digitalWrite(cs_, HIGH);
  healthy_ = false;
  delay(25);                                         // démarrage (≥ 15 ms)
  transfer(scl3300::kCmdSwReset);
  delay(2);
  transfer(scl3300::kCmdSetMode4);                   // mode 4 : inclinaison, bas bruit (10 Hz)
  delay(120);                                        // établissement du filtre
  // Deux lectures de STATUS pour purger les erreurs de démarrage
  transfer(scl3300::kCmdReadStatus);
  transfer(scl3300::kCmdReadStatus);
  // Identité : la réponse arrive dans la trame suivante
  transfer(scl3300::kCmdReadWhoAmI);
  const scl3300::Response who = scl3300::parseResponse(transfer(scl3300::kCmdReadStatus));
  const scl3300::Response st = scl3300::parseResponse(transfer(scl3300::kCmdReadStatus));
  healthy_ = who.crc_ok && (who.data & 0xFF) == scl3300::kWhoAmI && st.crc_ok && st.rs == 1;
  acc_.reset();
  last_ok_ms_ = millis();
  consecutive_errors_ = healthy_ ? 0 : 10;
  return healthy_;
}

void Scl3300Driver::poll(uint32_t) {
  // Protocole « décalé » : la réponse à une requête arrive dans la trame suivante.
  const scl3300::Response r0 = scl3300::parseResponse(transfer(scl3300::kCmdReadAccX));    // ← STATUS précédent
  const scl3300::Response rx = scl3300::parseResponse(transfer(scl3300::kCmdReadAccY));    // ← ACC_X
  const scl3300::Response ry = scl3300::parseResponse(transfer(scl3300::kCmdReadAccZ));    // ← ACC_Y
  const scl3300::Response rz = scl3300::parseResponse(transfer(scl3300::kCmdReadTemp));    // ← ACC_Z
  const scl3300::Response rt = scl3300::parseResponse(transfer(scl3300::kCmdReadStatus));  // ← TEMP
  last_status_ = r0.data;
  const bool ok = rx.crc_ok && ry.crc_ok && rz.crc_ok && rt.crc_ok &&
                  rx.rs == 1 && ry.rs == 1 && rz.rs == 1 && rt.rs == 1;
  if (!ok) {
    ++errors_;
    if (++consecutive_errors_ >= 20) healthy_ = false;
    return;
  }
  consecutive_errors_ = 0;
  healthy_ = true;
  last_ok_ms_ = millis();
  const scl3300::Mode m = scl3300::Mode::M4;
  acc_.add(scl3300::accToG(scl3300::toSigned(rx.data), m), scl3300::accToG(scl3300::toSigned(ry.data), m),
           scl3300::accToG(scl3300::toSigned(rz.data), m), scl3300::tempC(rt.data));
}

bool Scl3300Driver::read(TiltSample* out) {
  if (acc_.flush(out)) return true;
  out->valid = false;
  return false;
}

// ================================ ADXL355 ==================================================

void Adxl355Driver::readRegs(uint8_t reg, uint8_t* buf, size_t n) {
  spi_.beginTransaction(SPISettings(SPI_ADXL355_HZ, MSBFIRST, SPI_MODE0));
  digitalWrite(cs_, LOW);
  spi_.transfer(adxl355::spiRead(reg));
  for (size_t i = 0; i < n; ++i) buf[i] = spi_.transfer(0);
  digitalWrite(cs_, HIGH);
  spi_.endTransaction();
}

void Adxl355Driver::writeReg(uint8_t reg, uint8_t v) {
  spi_.beginTransaction(SPISettings(SPI_ADXL355_HZ, MSBFIRST, SPI_MODE0));
  digitalWrite(cs_, LOW);
  spi_.transfer(adxl355::spiWrite(reg));
  spi_.transfer(v);
  digitalWrite(cs_, HIGH);
  spi_.endTransaction();
}

bool Adxl355Driver::begin() {
  pinMode(cs_, OUTPUT);
  digitalWrite(cs_, HIGH);
  healthy_ = false;
  writeReg(adxl355::kRegReset, adxl355::kResetCode);
  delay(20);
  uint8_t id[3];
  readRegs(adxl355::kRegDevIdAd, id, 3);
  if (id[0] != 0xAD || id[1] != 0x1D || id[2] != 0xED) return false;
  writeReg(adxl355::kRegRange, static_cast<uint8_t>(adxl355::Range::G2));
  writeReg(adxl355::kRegFilter, adxl355::kOdr125Hz);
  writeReg(adxl355::kRegPowerCtl, 0x00);             // mode mesure
  delay(100);
  acc_.reset();
  healthy_ = true;
  consecutive_errors_ = 0;
  last_ok_ms_ = millis();
  return true;
}

void Adxl355Driver::poll(uint32_t) {
  uint8_t status = 0;
  readRegs(adxl355::kRegStatus, &status, 1);
  if (!(status & 0x01)) return;                       // pas de nouvelle donnée
  uint8_t b[11];                                      // TEMP2 TEMP1 X3 X2 X1 Y3 Y2 Y1 Z3 Z2 Z1
  readRegs(adxl355::kRegTemp2, b, sizeof b);
  const uint16_t traw = static_cast<uint16_t>(((b[0] & 0x0F) << 8) | b[1]);
  const int32_t x = adxl355::raw20(b[2], b[3], b[4]);
  const int32_t y = adxl355::raw20(b[5], b[6], b[7]);
  const int32_t z = adxl355::raw20(b[8], b[9], b[10]);
  const adxl355::Range r = adxl355::Range::G2;
  if (traw == 0 && x == 0 && y == 0 && z == 0) {      // bus mort / capteur absent : tout à zéro
    ++errors_;
    if (++consecutive_errors_ >= 20) healthy_ = false;
    return;
  }
  consecutive_errors_ = 0;
  healthy_ = true;
  last_ok_ms_ = millis();
  acc_.add(adxl355::toG(x, r), adxl355::toG(y, r), adxl355::toG(z, r), adxl355::tempC(traw));
}

bool Adxl355Driver::read(TiltSample* out) {
  if (acc_.flush(out)) return true;
  out->valid = false;
  return false;
}
