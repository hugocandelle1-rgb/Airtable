// Capteurs d'environnement sur le canal 6 du multiplexeur :
// 4 × TMP117 (plaque dessus/dessous, air plenum, local) + BME280 (pression atmo, humidité).
#pragma once
#include <Arduino.h>

#include "i2c_bus.h"

class EnvSensors {
 public:
  void begin(Tca9548a& mux);
  void update(uint32_t now_ms);          // à T_ENV_MS (lecture seule : mesures continues)

  float T[4] = {};                       // °C : 0 dessus, 1 dessous, 2 air plenum, 3 local
  bool T_valid[4] = {};
  float p_atm_Pa = 101325.0f;
  float rh_pct = 50.0f;
  float T_bme = 20.0f;
  bool bme_valid = false;
  float rho = 1.204f;                    // densité de l'air [kg/m³] (valeur de conception si BME absent)
  // Écart de température à travers la plaque [K] (dessus − dessous) ; NAN si invalide
  float plateGradient() const;
  uint32_t errors() const { return errors_; }

 private:
  Tca9548a* mux_ = nullptr;
  bool bme_started_ = false;
  uint32_t errors_ = 0;
  uint32_t next_bme_retry_ = 0;
  bool tmp_started_[4] = {false, false, false, false};
};
