// Réseau de capteurs de pression : 5 × SDP810-500Pa (plenum) + 1 × SDP810-125Pa (buse).
// Chaque capteur est derrière un canal du TCA9548A (adresse fixe 0x25).
#pragma once
#include <Arduino.h>

#include "atcore/filters.h"
#include "atcore/sdp8xx.h"
#include "config.h"
#include "i2c_bus.h"

class Sdp8xxSensor {
 public:
  void configure(Tca9548a* mux, uint8_t channel, float fallback_scale);
  bool begin();                         // arrêt éventuel + mesure continue (moyenne jusqu'à lecture)
  // Lecture non bloquante : retourne true si une mesure valide a été obtenue.
  bool read(uint32_t now_ms, float* dp_Pa, float* temp_C);
  bool valid() const { return valid_; }
  uint32_t errors() const { return crc_errors_ + bus_errors_; }
  uint32_t crcErrors() const { return crc_errors_; }

 private:
  Tca9548a* mux_ = nullptr;
  uint8_t ch_ = 0;
  float fallback_scale_ = 60.0f;
  bool valid_ = false;
  bool started_ = false;
  int fails_ = 0;
  uint32_t ready_at_ms_ = 0, next_retry_ms_ = 0;
  uint32_t crc_errors_ = 0, bus_errors_ = 0;
};

class PressureSensors {
 public:
  void begin(Tca9548a& mux);
  void update(uint32_t now_ms);         // à appeler à T_PRESSURE_MS

  // Résultats (offset retiré, filtrés)
  float p[NUM_PLENUM_SENSORS] = {};
  bool valid[NUM_PLENUM_SENSORS] = {};
  float temp_C[NUM_PLENUM_SENSORS] = {};
  float mean = 0.0f, max = 0.0f, min = 0.0f;
  int n_valid = 0;
  float uniformity_pct = 0.0f;          // (max−min)/moyenne
  float nozzle_dp = 0.0f;
  bool nozzle_valid = false;
  float offset[NUM_PLENUM_SENSORS] = {};   // zéro de chaque capteur (CAL PZERO)
  float nozzle_offset = 0.0f;

  // Mesure les offsets (ventilateur à l'arrêt, plenum à la pression ambiante). Retourne false
  // si un capteur est invalide ou si l'offset dépasse P_ZERO_MAX_PA.
  bool zeroOffsets();
  uint32_t errors() const;

 private:
  Sdp8xxSensor plenum_[NUM_PLENUM_SENSORS];
  Sdp8xxSensor nozzle_;
  atc::Iir1 filt_[NUM_PLENUM_SENSORS];
  atc::Iir1 nozzle_filt_;
  float raw_[NUM_PLENUM_SENSORS] = {};
  float nozzle_raw_ = 0.0f;
  uint32_t last_ms_ = 0;
};
