#include "i2c_bus.h"

#include "config.h"

bool Tca9548a::begin(TwoWire& wire, uint8_t addr, int reset_pin) {
  wire_ = &wire;
  addr_ = addr;
  reset_pin_ = reset_pin;
  if (reset_pin_ >= 0) {
    pinMode(reset_pin_, OUTPUT);
    digitalWrite(reset_pin_, LOW);     // impulsion de reset : repart avec tous les canaux coupés
    delayMicroseconds(10);
    digitalWrite(reset_pin_, HIGH);
    delayMicroseconds(100);
  }
  wire_->begin(PIN_I2C_SDA, PIN_I2C_SCL, I2C_FREQ_HZ);
  wire_->setTimeOut(5);                // ms : jamais de blocage long sur le bus
  invalidate();
  present_ = disableAll();
  return present_;
}

bool Tca9548a::select(uint8_t channel) {
  if (channel > 7) return false;
  if (current_ == channel) return true;
  wire_->beginTransmission(addr_);
  wire_->write(static_cast<uint8_t>(1U << channel));
  if (wire_->endTransmission() != 0) {
    ++errors_;
    invalidate();
    return false;
  }
  current_ = channel;
  return true;
}

bool Tca9548a::disableAll() {
  wire_->beginTransmission(addr_);
  wire_->write(static_cast<uint8_t>(0));
  const bool ok = (wire_->endTransmission() == 0);
  if (ok) current_ = 0xFF; else ++errors_;
  return ok;
}

void Tca9548a::recover() {
  wire_->end();
  pinMode(PIN_I2C_SDA, INPUT_PULLUP);
  pinMode(PIN_I2C_SCL, OUTPUT);
  for (int i = 0; i < 9; ++i) {        // 9 horloges libèrent un esclave bloqué en milieu d'octet
    digitalWrite(PIN_I2C_SCL, LOW);
    delayMicroseconds(5);
    digitalWrite(PIN_I2C_SCL, HIGH);
    delayMicroseconds(5);
  }
  if (reset_pin_ >= 0) {               // le reset du TCA débloque aussi le segment aval
    digitalWrite(reset_pin_, LOW);
    delayMicroseconds(10);
    digitalWrite(reset_pin_, HIGH);
    delayMicroseconds(100);
  }
  wire_->begin(PIN_I2C_SDA, PIN_I2C_SCL, I2C_FREQ_HZ);
  wire_->setTimeOut(5);
  invalidate();
}

bool i2cWrite16(TwoWire& w, uint8_t addr, uint16_t cmd) {
  w.beginTransmission(addr);
  w.write(static_cast<uint8_t>(cmd >> 8));
  w.write(static_cast<uint8_t>(cmd & 0xFF));
  return w.endTransmission() == 0;
}

bool i2cWriteReg16(TwoWire& w, uint8_t addr, uint8_t reg, uint16_t value) {
  w.beginTransmission(addr);
  w.write(reg);
  w.write(static_cast<uint8_t>(value >> 8));
  w.write(static_cast<uint8_t>(value & 0xFF));
  return w.endTransmission() == 0;
}

bool i2cReadReg16(TwoWire& w, uint8_t addr, uint8_t reg, uint16_t* value) {
  w.beginTransmission(addr);
  w.write(reg);
  if (w.endTransmission(false) != 0) return false;
  if (w.requestFrom(static_cast<int>(addr), 2) != 2) return false;
  const uint8_t hi = w.read();
  const uint8_t lo = w.read();
  *value = static_cast<uint16_t>((hi << 8) | lo);
  return true;
}
