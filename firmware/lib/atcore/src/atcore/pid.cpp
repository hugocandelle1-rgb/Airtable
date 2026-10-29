#include "atcore/pid.h"

#include <math.h>

namespace atc {

void Pid::reset(float integral) {
  i_ = integral;
  e_ = 0.0f;
  d_filt_ = 0.0f;
  first_ = true;
  sat_ = false;
}

float Pid::update(float sp, float pv, float dt, float ff) {
  if (dt <= 0.0f) dt = 1e-3f;
  const float e = sp - pv;
  e_ = e;

  // Dérivée sur la mesure (pas de « coup de pied » sur changement de consigne), filtrée.
  float d = 0.0f;
  if (cfg_.kd != 0.0f) {
    if (first_) pv_prev_ = pv;
    const float raw = (pv - pv_prev_) / dt;
    const float a = (cfg_.d_tau_s > 0.0f) ? dt / (cfg_.d_tau_s + dt) : 1.0f;
    d_filt_ += a * (raw - d_filt_);
    d = -cfg_.kd * d_filt_;
  }
  pv_prev_ = pv;
  first_ = false;

  const float u_unsat = ff + cfg_.kp * e + i_ + d;
  float u = u_unsat;
  if (u > cfg_.out_max) u = cfg_.out_max;
  if (u < cfg_.out_min) u = cfg_.out_min;
  sat_ = (u != u_unsat);

  // Anti-windup par intégration conditionnelle : on n'intègre pas quand la sortie est
  // saturée ET que l'erreur pousse plus loin dans la saturation.
  const bool push_hi = (u_unsat > cfg_.out_max) && (e > 0.0f);
  const bool push_lo = (u_unsat < cfg_.out_min) && (e < 0.0f);
  if (!push_hi && !push_lo) {
    i_ += cfg_.ki * e * dt;
  }
  // Borne de sûreté de l'intégrale : elle ne peut pas, seule, dépasser la plage de sortie.
  const float span = cfg_.out_max - cfg_.out_min;
  if (i_ > span) i_ = span;
  if (i_ < -span) i_ = -span;
  return u;
}

float RateLimiter::update(float target, float dt) {
  if (dt < 0.0f) dt = 0.0f;
  const float diff = target - y_;
  const float up = up_ * dt, dn = down_ * dt;
  if (diff > up) y_ += up;
  else if (diff < -dn) y_ -= dn;
  else y_ = target;
  return y_;
}

bool RateLimiter::atTarget(float target, float tol) const { return fabsf(target - y_) <= tol; }

}  // namespace atc
