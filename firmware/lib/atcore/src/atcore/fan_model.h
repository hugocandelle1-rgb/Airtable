// Modèle statique du ventilateur + plenum : p = p_full · duty^n  (n = 2 : loi p ∝ N²,
// la vitesse N étant proportionnelle au rapport cyclique PWM sur un 4 fils).
// Sert d'anticipation (feed-forward) et de gain de planification du PI.
#pragma once

namespace atc {

struct FanModelConfig {
  float p_full_Pa = 600.0f;  // pression plenum à duty = 1 (identifiée, adaptable)
  float exponent = 2.0f;     // n
  float duty_min = 0.10f;    // en dessous, le ventilateur décroche / reste à vitesse mini
  float duty_max = 1.00f;
  float adapt_rate_per_s = 0.02f;  // vitesse d'adaptation de p_full (0 = figé)
  float adapt_span = 0.5f;         // p_full reste dans nominal·[1−span ; 1+span]
};

class FanModel {
 public:
  void configure(const FanModelConfig& c) { cfg_ = c; nominal_ = c.p_full_Pa; }
  const FanModelConfig& config() const { return cfg_; }
  float pFull() const { return cfg_.p_full_Pa; }

  // PWM nécessaire pour la pression p (saturé dans [duty_min, duty_max]).
  float dutyForPressure(float p_Pa) const;
  // Pression statique prédite pour un rapport cyclique donné.
  float pressureForDuty(float duty) const;
  // Gain local dp/dduty [Pa] au point de fonctionnement p (pour planifier les gains).
  float plantGain(float p_Pa) const;
  // Adaptation lente de p_full en régime établi (appelée seulement si « steady »).
  void adapt(float p_meas_Pa, float duty, float dt, bool steady);

 private:
  FanModelConfig cfg_;
  float nominal_ = 600.0f;
};

}  // namespace atc
