// Estimation de vitesse de rotation à partir d'un compteur d'impulsions + horodatage du
// dernier front (relevés par une interruption côté matériel). Fenêtre glissante :
// rpm = Δimpulsions / (pulses_per_rev · Δt entre fronts), précis même à bas régime.
#pragma once
#include <stdint.h>

namespace atc {

class TachEstimator {
 public:
  static constexpr int kRing = 16;

  void configure(float pulses_per_rev = 2.0f, uint32_t window_us = 400000, uint32_t timeout_us = 1500000);
  // À appeler à cadence régulière (≈10 Hz) avec : l'heure, le compteur cumulé de fronts et
  // l'horodatage (µs) du dernier front.
  void sample(uint32_t now_us, uint32_t edge_count, uint32_t last_edge_us);
  float rpm() const { return rpm_; }
  void reset();

 private:
  struct Entry { uint32_t count; uint32_t t_us; };
  Entry ring_[kRing] = {};
  int n_ = 0, head_ = 0;
  float ppr_ = 2.0f;
  uint32_t window_us_ = 400000, timeout_us_ = 1500000;
  float rpm_ = 0.0f;
  uint32_t last_count_ = 0;
  bool have_last_ = false;
};

}  // namespace atc
