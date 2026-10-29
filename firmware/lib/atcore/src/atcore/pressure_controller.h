// Régulation de la pression plenum : consigne → rampe → PI (gains planifiés) + FF p∝N².
//
//   consigne ─► rampe ─┬─► FF : duty_ff = f⁻¹(p_rampe) ───────────────┐
//                       └─► modèle de référence (lag τ_p) ─► (−)        ▼
//                              p_mesuré filtré (IIR) ───────┘─► PI ─► (+) ─► sat ─► duty PWM
//   Le modèle de référence évite que l'intégrale s'accumule pendant les rampes (le procédé
//   suit la consigne avec un retard τ_p) : pas de dépassement en fin de rampe.
//   Gains du PI : Kp = kp_norm/G(p), Ki = Kp/ti, G = dp/dduty = n·p/duty (planification).
#pragma once
#include "atcore/fan_model.h"
#include "atcore/filters.h"
#include "atcore/pid.h"

namespace atc {

struct PressureControllerConfig {
  float p_min_Pa = 30.0f;     // bornes de consigne (design.toml : operating)
  float p_max_Pa = 400.0f;
  float duty_min = 0.10f;
  float duty_max = 1.00f;
  float ramp_up_Pa_s = 150.0f;    // rampe de consigne (montée)
  float ramp_down_Pa_s = 150.0f;  // (descente)
  float meas_tau_s = 0.08f;       // filtre de la mesure
  bool gain_schedule = true;      // Kp = kp_norm/G(p), Ki = Kp/ti
  float kp_norm = 0.8f;           // gain de boucle adimensionnel (Kp·G)
  float ti_s = 0.8f;              // temps d'intégrale ≈ constante de temps du procédé
  float kp_fixed = 0.0008f;       // [duty/Pa] si gain_schedule = false
  float ki_fixed = 0.0010f;       // [duty/(Pa·s)]
  float ref_tau_s = 0.8f;         // modèle de référence (≈ constante de temps du procédé) ; 0 = off
  float settle_tol_Pa = 0.3f;     // critère « établi » (pressure_regulation_Pa)
};

class PressureController {
 public:
  void configure(const PressureControllerConfig& c, const FanModelConfig& fan);
  const PressureControllerConfig& config() const { return cfg_; }

  void setTarget(float p_Pa);          // bornée à [p_min, p_max]
  float target() const { return target_; }
  float rampedTarget() const { return ramp_.value(); }

  // Active la régulation à partir de l'état courant (transfert sans à-coup).
  void enable(float p_meas_Pa, float duty_now);
  void disable() { enabled_ = false; }
  bool enabled() const { return enabled_; }

  // Un pas de régulation ; retourne le rapport cyclique PWM [duty_min, duty_max].
  float update(float p_meas_Pa, float dt);

  float filtered() const { return meas_.value(); }
  float duty() const { return duty_; }
  bool settled() const;               // |p_filtré − consigne finale| < tolérance, rampe finie
  void setGainsNorm(float kp_norm, float ti_s) { cfg_.kp_norm = kp_norm; cfg_.ti_s = ti_s; }
  void setRamp(float up, float down) { cfg_.ramp_up_Pa_s = up; cfg_.ramp_down_Pa_s = down; ramp_.configure(up, down); }
  FanModel& fan() { return fan_; }
  const Pid& pid() const { return pid_; }

 private:
  PressureControllerConfig cfg_;
  FanModel fan_;
  Pid pid_;
  RateLimiter ramp_;
  Iir1 meas_;
  Iir1 ref_;                         // modèle de référence : p_ref = lag(consigne rampée)
  float target_ = 0.0f;
  float duty_ = 0.0f;
  bool enabled_ = false;
  float steady_time_ = 0.0f;
};

}  // namespace atc
