// Régulateur PI(D) avec anticipation (feed-forward), anti-windup par intégration
// conditionnelle, dérivée sur la mesure filtrée, et limiteur de rampe.
#pragma once
#include <stdint.h>

namespace atc {

struct PidConfig {
  float kp = 0.0f;        // [unité sortie / unité erreur]
  float ki = 0.0f;        // [unité sortie / (unité erreur·s)]
  float kd = 0.0f;        // [unité sortie·s / unité erreur]
  float out_min = 0.0f;   // saturation basse de la sortie TOTALE (FF + PID)
  float out_max = 1.0f;   // saturation haute
  float d_tau_s = 0.05f;  // filtre de la dérivée
};

class Pid {
 public:
  void configure(const PidConfig& c) { cfg_ = c; }
  const PidConfig& config() const { return cfg_; }
  void setGains(float kp, float ki, float kd = 0.0f) { cfg_.kp = kp; cfg_.ki = ki; cfg_.kd = kd; }
  void setLimits(float lo, float hi) { cfg_.out_min = lo; cfg_.out_max = hi; }

  // Remet à zéro l'état ; `integral` permet un transfert sans à-coup.
  void reset(float integral = 0.0f);

  // sp : consigne, pv : mesure, dt : pas [s], ff : anticipation ajoutée à la sortie.
  // Retourne la sortie saturée dans [out_min, out_max].
  float update(float sp, float pv, float dt, float ff = 0.0f);

  float integral() const { return i_; }
  bool saturated() const { return sat_; }
  float lastError() const { return e_; }

 private:
  PidConfig cfg_;
  float i_ = 0.0f;
  float e_ = 0.0f;
  float pv_prev_ = 0.0f;
  float d_filt_ = 0.0f;
  bool first_ = true;
  bool sat_ = false;
};

// Limiteur de rampe (vitesse max, montée/descente éventuellement différentes).
class RateLimiter {
 public:
  void configure(float up_per_s, float down_per_s) { up_ = up_per_s; down_ = down_per_s; }
  void reset(float v) { y_ = v; }
  float value() const { return y_; }
  float update(float target, float dt);
  bool atTarget(float target, float tol = 1e-6f) const;

 private:
  float up_ = 1e9f, down_ = 1e9f, y_ = 0.0f;
};

}  // namespace atc
