#include "atcore/pressure_controller.h"

#include <math.h>

namespace atc {

void PressureController::configure(const PressureControllerConfig& c, const FanModelConfig& fan) {
  cfg_ = c;
  FanModelConfig f = fan;
  f.duty_min = c.duty_min;
  f.duty_max = c.duty_max;
  fan_.configure(f);
  PidConfig pc;
  pc.out_min = c.duty_min;
  pc.out_max = c.duty_max;
  pid_.configure(pc);
  ramp_.configure(c.ramp_up_Pa_s, c.ramp_down_Pa_s);
  meas_.setTau(c.meas_tau_s);
  target_ = c.p_min_Pa;
}

void PressureController::setTarget(float p) {
  if (p < cfg_.p_min_Pa) p = cfg_.p_min_Pa;
  if (p > cfg_.p_max_Pa) p = cfg_.p_max_Pa;
  target_ = p;
}

void PressureController::enable(float p_meas, float duty_now) {
  meas_.reset(p_meas);
  ramp_.reset(p_meas < cfg_.p_min_Pa ? cfg_.p_min_Pa : p_meas);
  // Intégrale initialisée pour que la sortie démarre à la PWM courante (sans à-coup).
  const float ff = fan_.dutyForPressure(ramp_.value());
  pid_.reset(duty_now - ff);
  duty_ = duty_now;
  steady_time_ = 0.0f;
  enabled_ = true;
}

float PressureController::update(float p_meas, float dt) {
  if (!enabled_) return duty_;
  const float pf = meas_.update(p_meas, dt);
  const float sp = ramp_.update(target_, dt);
  const float ff = fan_.dutyForPressure(sp);

  float kp, ki;
  if (cfg_.gain_schedule) {
    const float g = fan_.plantGain(sp);              // dp/dduty [Pa]
    kp = cfg_.kp_norm / (g > 1.0f ? g : 1.0f);
    ki = (cfg_.ti_s > 0.0f) ? kp / cfg_.ti_s : 0.0f;
  } else {
    kp = cfg_.kp_fixed;
    ki = cfg_.ki_fixed;
  }
  pid_.setGains(kp, ki, 0.0f);
  duty_ = pid_.update(sp, pf, dt, ff);

  // Adaptation lente du modèle FF quand la boucle est établie.
  const bool steady = ramp_.atTarget(target_, 0.01f) && fabsf(pf - target_) < 3.0f * cfg_.settle_tol_Pa;
  steady_time_ = steady ? steady_time_ + dt : 0.0f;
  fan_.adapt(pf, duty_, dt, steady_time_ > 3.0f);
  return duty_;
}

bool PressureController::settled() const {
  return enabled_ && ramp_.atTarget(target_, 0.01f) && fabsf(meas_.value() - target_) <= cfg_.settle_tol_Pa;
}

}  // namespace atc
