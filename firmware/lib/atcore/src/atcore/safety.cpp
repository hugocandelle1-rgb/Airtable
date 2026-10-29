#include "atcore/safety.h"

namespace atc {

void Safety::reset() {
  latched_ = active_ = 0;
  a_over_ = a_stall_ = a_sensor_ = false;
}

namespace {
// Durée écoulée robuste au débordement de millis().
inline uint32_t since(uint32_t now, uint32_t t0) { return now - t0; }
}  // namespace

SafetyState Safety::update(const SafetyInputs& in) {
  uint16_t act = 0;

  // Surpression (avec temporisation anti-pic)
  if (in.n_valid_pressure > 0 && in.p_max_meas_Pa > cfg_.p_limit_Pa) {
    if (!a_over_) { a_over_ = true; t_over_ = in.now_ms; }
    if (since(in.now_ms, t_over_) >= cfg_.overpressure_ms) act |= FAULT_OVERPRESSURE;
  } else {
    a_over_ = false;
  }

  // Calage : le ventilateur doit tourner quand la PWM dépasse stall_duty
  if (in.duty > cfg_.stall_duty && in.rpm_min < cfg_.stall_rpm) {
    if (!a_stall_) { a_stall_ = true; t_stall_ = in.now_ms; }
    if (since(in.now_ms, t_stall_) >= cfg_.stall_ms) act |= FAULT_STALL;
  } else {
    a_stall_ = false;
  }

  if (cfg_.overspeed_rpm > 0.0f && in.rpm_max > cfg_.overspeed_rpm) act |= FAULT_FAN_OVERSPEED;

  // Capteurs de pression absents / invalides
  if (in.n_valid_pressure < cfg_.min_valid_pressure) {
    if (!a_sensor_) { a_sensor_ = true; t_sensor_ = in.now_ms; }
    if (since(in.now_ms, t_sensor_) >= cfg_.sensor_lost_ms) act |= FAULT_SENSOR_LOST;
  } else {
    a_sensor_ = false;
  }

  // Chien de garde de la liaison hôte (optionnel)
  if (cfg_.host_timeout_ms > 0 && since(in.now_ms, in.last_host_ms) > cfg_.host_timeout_ms)
    act |= FAULT_HOST_WDT;

  if (in.limit_hit) act |= FAULT_LIMIT_SWITCH;
  if (!in.tilt_valid) act |= FAULT_TILT_LOST;

  active_ = act;
  // Le défaut « inclinomètre perdu » n'est pas verrouillé : il s'efface seul à la reprise.
  latched_ = static_cast<uint16_t>((latched_ & static_cast<uint16_t>(~FAULT_TILT_LOST)) | act);
  return state();
}

bool Safety::clear() {
  // Les défauts manuels et ceux dont la cause a disparu peuvent être acquittés.
  const uint16_t keep = active_ & ~static_cast<uint16_t>(FAULT_MANUAL);
  if (keep & kCriticalFaults) return false;
  latched_ = keep;   // un défaut moteur encore actif reste présent
  a_over_ = a_stall_ = a_sensor_ = false;
  return true;
}

const char* faultName(Fault f) {
  switch (f) {
    case FAULT_STALL: return "stall";
    case FAULT_OVERPRESSURE: return "overpressure";
    case FAULT_SENSOR_LOST: return "sensor_lost";
    case FAULT_HOST_WDT: return "host_wdt";
    case FAULT_LIMIT_SWITCH: return "limit_switch";
    case FAULT_TILT_LOST: return "tilt_lost";
    case FAULT_MANUAL: return "manual";
    case FAULT_FAN_OVERSPEED: return "overspeed";
    default: return "none";
  }
}

}  // namespace atc
