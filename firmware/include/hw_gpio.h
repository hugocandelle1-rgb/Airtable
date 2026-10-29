// Accès GPIO rapides et sûrs en interruption (registres), valables pour GPIO 0-48 (ESP32-S3).
#pragma once
#include <Arduino.h>
#include "soc/gpio_reg.h"
#include "soc/soc.h"

#ifndef IRAM_ATTR
#define IRAM_ATTR
#endif

static inline void IRAM_ATTR gpioFastWrite(int pin, bool high) {
  if (pin < 32) {
    REG_WRITE(high ? GPIO_OUT_W1TS_REG : GPIO_OUT_W1TC_REG, 1UL << pin);
  } else {
    REG_WRITE(high ? GPIO_OUT1_W1TS_REG : GPIO_OUT1_W1TC_REG, 1UL << (pin - 32));
  }
}

static inline bool IRAM_ATTR gpioFastRead(int pin) {
  return pin < 32 ? ((REG_READ(GPIO_IN_REG) >> pin) & 1U) != 0
                  : ((REG_READ(GPIO_IN1_REG) >> (pin - 32)) & 1U) != 0;
}
