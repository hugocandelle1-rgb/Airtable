#include "atcore/fan_model.h"

#include <math.h>

namespace atc {

float FanModel::pressureForDuty(float duty) const {
  if (duty <= 0.0f) return 0.0f;
  return cfg_.p_full_Pa * powf(duty, cfg_.exponent);
}

float FanModel::dutyForPressure(float p_Pa) const {
  if (p_Pa <= 0.0f || cfg_.p_full_Pa <= 0.0f) return cfg_.duty_min;
  float d = powf(p_Pa / cfg_.p_full_Pa, 1.0f / cfg_.exponent);
  if (d < cfg_.duty_min) d = cfg_.duty_min;
  if (d > cfg_.duty_max) d = cfg_.duty_max;
  return d;
}

float FanModel::plantGain(float p_Pa) const {
  const float d = dutyForPressure(p_Pa);
  // dp/dd = n·p_full·d^(n−1) = n·p/d  (évalué sur la loi, pas sur la mesure)
  const float p = pressureForDuty(d);
  return cfg_.exponent * p / d;
}

void FanModel::adapt(float p_meas_Pa, float duty, float dt, bool steady) {
  if (!steady || cfg_.adapt_rate_per_s <= 0.0f) return;
  if (duty < 0.2f || duty > cfg_.duty_max * 0.98f || p_meas_Pa <= 1.0f) return;
  const float est = p_meas_Pa / powf(duty, cfg_.exponent);
  const float a = fminf(1.0f, cfg_.adapt_rate_per_s * dt);
  cfg_.p_full_Pa += a * (est - cfg_.p_full_Pa);
  const float lo = nominal_ * (1.0f - cfg_.adapt_span), hi = nominal_ * (1.0f + cfg_.adapt_span);
  if (cfg_.p_full_Pa < lo) cfg_.p_full_Pa = lo;
  if (cfg_.p_full_Pa > hi) cfg_.p_full_Pa = hi;
}

}  // namespace atc
