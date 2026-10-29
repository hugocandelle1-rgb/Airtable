// Option : 3 capteurs de déplacement analogiques lus par un ADS1220 (24 bits, SPI mode 1).
// Acquisition non bloquante : une machine à états enchaîne les 3 canaux en mode « single-shot ».
#pragma once
#include <Arduino.h>
#include <SPI.h>

#include "config.h"

class DisplacementSensors {
 public:
  bool begin(SPIClass& spi);
  void poll(uint32_t now_ms);

  float volts[NUM_DISP] = {};
  float um[NUM_DISP] = {};
  bool valid[NUM_DISP] = {};
  bool present = false;
  uint32_t errors() const { return errors_; }

 private:
  void spiCmd(uint8_t cmd);
  void writeReg(uint8_t reg, uint8_t v);
  uint8_t readReg(uint8_t reg);
  void startChannel(int ch);
  SPIClass* spi_ = nullptr;
  int ch_ = 0;
  bool converting_ = false;
  uint32_t t_start_ms_ = 0;
  uint32_t errors_ = 0;
};
