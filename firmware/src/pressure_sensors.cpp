#include "pressure_sensors.h"

#include <math.h>

#include "atcore/crc.h"

// ---- un capteur SDP8xx ------------------------------------------------------------------

void Sdp8xxSensor::configure(Tca9548a* mux, uint8_t channel, float fallback_scale) {
  mux_ = mux;
  ch_ = channel;
  fallback_scale_ = fallback_scale;
}

bool Sdp8xxSensor::begin() {
  valid_ = false;
  started_ = false;
  if (!mux_->select(ch_)) return false;
  TwoWire& w = mux_->wire();
  // Arrêt d'une éventuelle mesure continue (ignorer l'échec : le capteur peut être au repos)
  i2cWrite16(w, atc::sdp8xx::kI2cAddr, atc::sdp8xx::kCmdStop);
  delayMicroseconds(800);
  if (!i2cWrite16(w, atc::sdp8xx::kI2cAddr, atc::sdp8xx::kCmdStartContDpAvg)) {
    ++bus_errors_;
    return false;
  }
  started_ = true;
  ready_at_ms_ = millis() + 12;          // première mesure disponible après ≈ 8,5 ms
  fails_ = SDP_FAIL_LIMIT;               // « invalide » tant qu'aucune lecture n'a réussi
  return true;
}

bool Sdp8xxSensor::read(uint32_t now_ms, float* dp_Pa, float* temp_C) {
  if (!started_) {
    if (static_cast<int32_t>(now_ms - next_retry_ms_) >= 0) {
      next_retry_ms_ = now_ms + SDP_RETRY_MS;
      begin();
    }
    return false;
  }
  if (static_cast<int32_t>(now_ms - ready_at_ms_) < 0) return false;
  if (!mux_->select(ch_)) { ++fails_; goto failed; }
  {
    TwoWire& w = mux_->wire();
    if (w.requestFrom(static_cast<int>(atc::sdp8xx::kI2cAddr), 9) != 9) {
      while (w.available()) w.read();
      ++bus_errors_;
      ++fails_;
      goto failed;
    }
    uint8_t buf[9];
    for (int i = 0; i < 9; ++i) buf[i] = w.read();
    atc::Sdp8xxSample s;
    if (!atc::decodeSdp8xx(buf, fallback_scale_, &s)) {
      ++crc_errors_;
      ++fails_;
      goto failed;
    }
    fails_ = 0;
    valid_ = true;
    *dp_Pa = s.dp_Pa;
    *temp_C = s.temp_C;
    return true;
  }
failed:
  if (fails_ >= SDP_FAIL_LIMIT) {
    valid_ = false;
    started_ = false;                    // forcera une ré-initialisation après SDP_RETRY_MS
    next_retry_ms_ = now_ms + SDP_RETRY_MS;
    mux_->invalidate();
  }
  return false;
}

// ---- l'ensemble -------------------------------------------------------------------------

void PressureSensors::begin(Tca9548a& mux) {
  for (int i = 0; i < NUM_PLENUM_SENSORS; ++i) {
    plenum_[i].configure(&mux, MUX_CH_PLENUM[i], SDP_SCALE_500PA);
    plenum_[i].begin();
    filt_[i].setTau(P_SENSOR_TAU_S);
  }
  nozzle_.configure(&mux, MUX_CH_NOZZLE, SDP_SCALE_125PA);
  nozzle_.begin();
  nozzle_filt_.setTau(P_SENSOR_TAU_S);
}

void PressureSensors::update(uint32_t now_ms) {
  const float dt = last_ms_ ? (now_ms - last_ms_) * 1e-3f : T_PRESSURE_MS * 1e-3f;
  last_ms_ = now_ms;
  for (int i = 0; i < NUM_PLENUM_SENSORS; ++i) {
    float dp, t;
    if (plenum_[i].read(now_ms, &dp, &t)) {
      raw_[i] = dp;
      p[i] = filt_[i].update(dp - offset[i], dt);
      temp_C[i] = t;
    }
    valid[i] = plenum_[i].valid();
  }
  float dp, t;
  if (nozzle_.read(now_ms, &dp, &t)) {
    nozzle_raw_ = dp;
    nozzle_dp = nozzle_filt_.update(dp - nozzle_offset, dt);
  }
  nozzle_valid = nozzle_.valid();

  n_valid = 0;
  float sum = 0.0f, mx = -1e9f, mn = 1e9f;
  for (int i = 0; i < NUM_PLENUM_SENSORS; ++i) {
    if (!valid[i]) continue;
    ++n_valid;
    sum += p[i];
    if (p[i] > mx) mx = p[i];
    if (p[i] < mn) mn = p[i];
  }
  if (n_valid > 0) {
    mean = sum / n_valid;
    max = mx;
    min = mn;
    uniformity_pct = (mean > 1.0f) ? 100.0f * (mx - mn) / mean : 0.0f;
  } else {
    max = min = mean = 0.0f;
    uniformity_pct = 0.0f;
  }
}

bool PressureSensors::zeroOffsets() {
  // Valeur brute filtrée = sortie du filtre + offset courant
  float r[NUM_PLENUM_SENSORS];
  for (int i = 0; i < NUM_PLENUM_SENSORS; ++i) {
    r[i] = filt_[i].value() + offset[i];
    if (!valid[i] || fabsf(r[i]) > P_ZERO_MAX_PA) return false;
  }
  const float rn = nozzle_filt_.value() + nozzle_offset;
  if (nozzle_valid && fabsf(rn) > P_ZERO_MAX_PA) return false;
  for (int i = 0; i < NUM_PLENUM_SENSORS; ++i) {
    offset[i] = r[i];
    filt_[i].reset(0.0f);
    p[i] = 0.0f;
  }
  if (nozzle_valid) { nozzle_offset = rn; nozzle_filt_.reset(0.0f); nozzle_dp = 0.0f; }
  return true;
}

uint32_t PressureSensors::errors() const {
  uint32_t e = nozzle_.errors();
  for (int i = 0; i < NUM_PLENUM_SENSORS; ++i) e += plenum_[i].errors();
  return e;
}
