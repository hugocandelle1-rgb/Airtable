// Drivers d'inclinomètres (interface atc::Inclinometer) : SCL3300-D01 et ADXL355, en SPI.
// Convention : tilt_x = ∂z/∂x [µrad], positif quand l'axe +X du capteur monte.
#pragma once
#include <Arduino.h>
#include <SPI.h>

#include "atcore/inclinometer.h"

class Scl3300Driver : public atc::Inclinometer {
 public:
  Scl3300Driver(SPIClass& spi, int cs_pin) : spi_(spi), cs_(cs_pin) {}
  bool begin() override;
  void poll(uint32_t now_us) override;
  bool read(atc::TiltSample* out) override;
  const char* name() const override { return "SCL3300-D01"; }
  uint32_t errorCount() const override { return errors_; }
  bool healthy() const override { return healthy_; }
  uint16_t lastStatus() const { return last_status_; }

 private:
  uint32_t transfer(uint32_t frame);
  SPIClass& spi_;
  int cs_;
  atc::AccAccumulator acc_;
  bool healthy_ = false;
  uint32_t errors_ = 0;
  uint32_t last_ok_ms_ = 0;
  uint16_t last_status_ = 0;
  int consecutive_errors_ = 0;
};

class Adxl355Driver : public atc::Inclinometer {
 public:
  Adxl355Driver(SPIClass& spi, int cs_pin) : spi_(spi), cs_(cs_pin) {}
  bool begin() override;
  void poll(uint32_t now_us) override;
  bool read(atc::TiltSample* out) override;
  const char* name() const override { return "ADXL355"; }
  uint32_t errorCount() const override { return errors_; }
  bool healthy() const override { return healthy_; }

 private:
  void readRegs(uint8_t reg, uint8_t* buf, size_t n);
  void writeReg(uint8_t reg, uint8_t value);
  SPIClass& spi_;
  int cs_;
  atc::AccAccumulator acc_;
  bool healthy_ = false;
  uint32_t errors_ = 0;
  uint32_t last_ok_ms_ = 0;
  int consecutive_errors_ = 0;
};
