// Ventilateurs 4 fils : PWM 25 kHz (LEDC) + tachymètre (interruption, fenêtre glissante).
#pragma once
#include <Arduino.h>

#include "atcore/tach.h"
#include "config.h"

class Fan {
 public:
  void begin(int index);
  void setDuty(float duty);              // 0..1 (bornée)
  float duty() const { return duty_; }
  void updateRpm(uint32_t now_us);       // à T_TACH_MS
  float rpm() const { return est_.rpm(); }
  uint32_t edges() const { return edges_; }

  // Appelé par l'ISR (public pour l'enregistrement du gestionnaire)
  static void IRAM_ATTR onEdge(void* arg);

 private:
  int idx_ = 0;
  float duty_ = 0.0f;
  volatile uint32_t edges_ = 0;
  volatile uint32_t last_edge_us_ = 0;
  atc::TachEstimator est_;
};

// Ensemble des ventilateurs (même rapport cyclique sur tous).
class FanBank {
 public:
  void begin();
  void setDuty(float duty);
  float duty() const { return duty_; }
  void updateRpm(uint32_t now_us);
  float rpm(int i) const { return fans_[i].rpm(); }
  float rpmMin() const;
  float rpmMax() const;

 private:
  Fan fans_[MAX_FANS];
  float duty_ = 0.0f;
};
