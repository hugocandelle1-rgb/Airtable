#include "env_sensors.h"

#include <Adafruit_BME280.h>
#include <math.h>

#include "atcore/airphys.h"
#include "atcore/tmp117.h"
#include "config.h"

static Adafruit_BME280 g_bme;

void EnvSensors::begin(Tca9548a& mux) {
  mux_ = &mux;
  rho = DESIGN_AIR_RHO;
  if (!mux_->select(MUX_CH_ENV)) return;
  TwoWire& w = mux_->wire();
  for (int i = 0; i < 4; ++i) {
    uint16_t id = 0;
    // Identifiant 0x0117 attendu ; mesure continue 1 Hz, moyenne sur 8 (configuration par défaut)
    tmp_started_[i] = i2cReadReg16(w, TMP117_ADDR[i], atc::tmp117::kRegDeviceId, &id) &&
                      ((id & 0x0FFF) == atc::tmp117::kDeviceId);
  }
  if (g_bme.begin(BME280_ADDR, &w)) {
    // 1 mesure/s, filtre IIR x4, peu de sur-échantillonnage : limite l'auto-échauffement
    g_bme.setSampling(Adafruit_BME280::MODE_NORMAL, Adafruit_BME280::SAMPLING_X2,
                      Adafruit_BME280::SAMPLING_X4, Adafruit_BME280::SAMPLING_X1,
                      Adafruit_BME280::FILTER_X4, Adafruit_BME280::STANDBY_MS_1000);
    bme_started_ = true;
  }
}

void EnvSensors::update(uint32_t now_ms) {
  if (!mux_ || !mux_->select(MUX_CH_ENV)) {
    ++errors_;
    for (int i = 0; i < 4; ++i) T_valid[i] = false;
    bme_valid = false;
    return;
  }
  TwoWire& w = mux_->wire();
  for (int i = 0; i < 4; ++i) {
    uint16_t raw;
    if (i2cReadReg16(w, TMP117_ADDR[i], atc::tmp117::kRegTemp, &raw) && atc::tmp117::plausible(raw)) {
      T[i] = atc::tmp117::toC(raw);
      T_valid[i] = true;
    } else {
      T_valid[i] = false;
      ++errors_;
    }
  }
  if (!bme_started_ && static_cast<int32_t>(now_ms - next_bme_retry_) >= 0) {
    next_bme_retry_ = now_ms + 5000;
    bme_started_ = g_bme.begin(BME280_ADDR, &w);
  }
  if (bme_started_) {
    const float p = g_bme.readPressure();     // Pa
    const float t = g_bme.readTemperature();
    const float h = g_bme.readHumidity();
    if (isfinite(p) && isfinite(t) && isfinite(h) && p > 60000.0f && p < 115000.0f) {
      p_atm_Pa = p;
      T_bme = t;
      rh_pct = h;
      bme_valid = true;
      rho = atc::airDensity(p, t, h);
    } else {
      bme_valid = false;
      ++errors_;
    }
  } else {
    bme_valid = false;
  }
}

float EnvSensors::plateGradient() const {
  return (T_valid[0] && T_valid[1]) ? T[0] - T[1] : NAN;
}
