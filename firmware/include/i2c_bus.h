// Bus I²C principal + multiplexeur TCA9548A. Toutes les lectures sont courtes et bornées
// (timeout I²C configuré) ; en cas de blocage de SDA, `recover()` génère 9 impulsions SCL.
#pragma once
#include <Arduino.h>
#include <Wire.h>

class Tca9548a {
 public:
  bool begin(TwoWire& wire, uint8_t addr, int reset_pin);
  // Sélectionne UN canal (les autres sont déconnectés). Mémorise le canal courant.
  bool select(uint8_t channel);
  bool disableAll();
  void invalidate() { current_ = 0xFF; }
  TwoWire& wire() { return *wire_; }
  uint32_t errors() const { return errors_; }
  // Récupération d'un bus bloqué (esclave tenant SDA bas) ; ré-initialise Wire.
  void recover();
  bool present() const { return present_; }

 private:
  TwoWire* wire_ = nullptr;
  uint8_t addr_ = 0x70;
  int reset_pin_ = -1;
  uint8_t current_ = 0xFF;
  uint32_t errors_ = 0;
  bool present_ = false;
};

// Écriture d'une commande 16 bits (MSB d'abord) et lecture brute.
bool i2cWrite16(TwoWire& w, uint8_t addr, uint16_t cmd);
bool i2cWriteReg16(TwoWire& w, uint8_t addr, uint8_t reg, uint16_t value);
bool i2cReadReg16(TwoWire& w, uint8_t addr, uint8_t reg, uint16_t* value);
