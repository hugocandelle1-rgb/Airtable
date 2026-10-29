// Supervision de sécurité : calage ventilateur, surpression, capteurs absents, chien de
// garde hôte, fin de course. Logique pure (pas de matériel) : le firmware lui fournit les
// entrées mesurées et applique les sorties.
//
// État SAFE : ventilateur à la PWM de repos (boucle ouverte), moteurs de nivellement arrêtés
// et inhibés. Les défauts « critiques » sont verrouillés (latched) jusqu'à CLEAR, qui n'est
// accepté que si la cause a disparu.
#pragma once
#include <stdint.h>

namespace atc {

enum Fault : uint16_t {
  FAULT_NONE = 0,
  FAULT_STALL = 1u << 0,         // tachymètre nul avec PWM élevée
  FAULT_OVERPRESSURE = 1u << 1,  // pression plenum > limite
  FAULT_SENSOR_LOST = 1u << 2,   // trop peu de capteurs de pression valides
  FAULT_HOST_WDT = 1u << 3,      // liaison hôte silencieuse (si activé)
  FAULT_LIMIT_SWITCH = 1u << 4,  // fin de course touché hors prise d'origine (moteurs seuls)
  FAULT_TILT_LOST = 1u << 5,     // inclinomètre absent/invalide (nivellement auto inhibé)
  FAULT_MANUAL = 1u << 6,        // commande SAFE de l'opérateur
  FAULT_FAN_OVERSPEED = 1u << 7  // vitesse > limite (tachy aberrant)
};

constexpr uint16_t kCriticalFaults = FAULT_STALL | FAULT_OVERPRESSURE | FAULT_SENSOR_LOST |
                                     FAULT_HOST_WDT | FAULT_MANUAL | FAULT_FAN_OVERSPEED;
constexpr uint16_t kMotorFaults = FAULT_LIMIT_SWITCH | FAULT_TILT_LOST | kCriticalFaults;

struct SafetyConfig {
  float p_limit_Pa = 480.0f;        // 1,2 × pmax
  uint32_t overpressure_ms = 200;   // durée de dépassement avant défaut (anti-pic)
  float stall_duty = 0.25f;         // PWM au-dessus de laquelle le ventilateur DOIT tourner
  float stall_rpm = 300.0f;         // seuil de calage [tr/min]
  uint32_t stall_ms = 3000;
  float overspeed_rpm = 0.0f;       // 0 = désactivé
  int min_valid_pressure = 2;       // capteurs de pression valides requis
  uint32_t sensor_lost_ms = 500;
  uint32_t host_timeout_ms = 0;     // 0 = chien de garde hôte désactivé
};

struct SafetyInputs {
  uint32_t now_ms = 0;
  float p_max_meas_Pa = 0.0f;       // max des capteurs de pression valides
  int n_valid_pressure = 0;
  float duty = 0.0f;                // PWM commandée
  float rpm_min = 0.0f;             // vitesse du ventilateur le plus lent
  float rpm_max = 0.0f;
  bool limit_hit = false;           // fin de course actif hors procédure d'origine
  bool tilt_valid = true;
  uint32_t last_host_ms = 0;        // dernière ligne reçue de l'hôte
};

enum class SafetyState : uint8_t { Ok = 0, Safe = 1 };

class Safety {
 public:
  void configure(const SafetyConfig& c) { cfg_ = c; reset(); }
  const SafetyConfig& config() const { return cfg_; }
  void setHostTimeoutMs(uint32_t ms) { cfg_.host_timeout_ms = ms; }
  void reset();

  // Évalue les entrées ; retourne l'état. À appeler à chaque tour de régulation (≥ 20 Hz).
  SafetyState update(const SafetyInputs& in);
  void raise(Fault f) { latched_ |= f; }                // déclenchement externe (ex. SAFE manuel)
  // Acquitte les défauts verrouillés si aucune cause active. Retourne true si effacés.
  bool clear();

  SafetyState state() const { return (latched_ & kCriticalFaults) ? SafetyState::Safe : SafetyState::Ok; }
  uint16_t latched() const { return latched_; }
  uint16_t active() const { return active_; }
  bool motorsInhibited() const { return (latched_ & kMotorFaults) != 0; }
  bool fanSafe() const { return (latched_ & kCriticalFaults) != 0; }

 private:
  SafetyConfig cfg_;
  uint16_t latched_ = 0, active_ = 0;
  // Débuts des conditions (0 = inactive) ; `armed_*` distingue t = 0 d'une condition inactive.
  uint32_t t_over_ = 0, t_stall_ = 0, t_sensor_ = 0;
  bool a_over_ = false, a_stall_ = false, a_sensor_ = false;
};

const char* faultName(Fault f);

}  // namespace atc
