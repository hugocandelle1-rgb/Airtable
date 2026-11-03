// Retournement à 180° d'une embase de capteur : servo (PWM 50 Hz, LEDC) + contact d'index à 0°.
// Boucle ouverte (un servo n'a pas de retour de position) : le temps de course est attendu, puis le
// contact d'index valide la position 0° (actif) et l'éloignement de 0° (inactif à 180°). Après la
// course, la PWM est coupée (servo libre, pas de vibration ni d'échauffement de l'embase) : l'embase
// doit donc reposer sur son appui cinématique (3 plots / V-rainure) sous l'effet de son poids ou d'un ressort.
#pragma once
#include <Arduino.h>

class FlipActuator {
 public:
  void begin();
  void setTarget(float deg, uint32_t now_ms);     // 0 ou 180 ; sans effet si c'est déjà la consigne
  void service(uint32_t now_ms);                  // à chaque tour de loop()
  void release();                                 // coupe la PWM (servo libre)
  bool moving() const { return moving_; }
  bool atTarget() const;                          // course terminée ET index cohérent avec la consigne
  bool fault() const { return fault_; }           // index incohérent après la course
  void clearFault() { fault_ = false; }
  bool indexActive() const;
  float targetDeg() const { return target_deg_; }

 private:
  void writeUs(uint32_t us);
  float target_deg_ = 0.0f;
  bool moving_ = false;
  bool fault_ = false;
  bool known_ = false;                            // position connue (index vu à 0° au moins une fois)
  uint32_t t_start_ = 0;
};
