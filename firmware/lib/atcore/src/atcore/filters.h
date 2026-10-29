// Filtres élémentaires (en-tête seul).
#pragma once
#include <math.h>
#include <stdint.h>

namespace atc {

// Filtre passe-bas du 1er ordre (IIR), pas de temps variable : α = dt/(τ+dt).
class Iir1 {
 public:
  explicit Iir1(float tau_s = 0.1f) : tau_(tau_s) {}
  void setTau(float tau_s) { tau_ = tau_s; }
  void reset(float v) { y_ = v; init_ = true; }
  bool initialized() const { return init_; }
  float value() const { return y_; }
  float update(float x, float dt) {
    if (!init_) { y_ = x; init_ = true; return y_; }
    if (tau_ <= 0.0f || dt <= 0.0f) { y_ = x; return y_; }
    const float a = dt / (tau_ + dt);
    y_ += a * (x - y_);
    return y_;
  }

 private:
  float tau_;
  float y_ = 0.0f;
  bool init_ = false;
};

// Moyenne glissante sur N échantillons (N ≤ CAP), sans allocation.
template <int CAP>
class MovingAverage {
 public:
  void setLength(int n) { n_ = (n < 1) ? 1 : (n > CAP ? CAP : n); reset(); }
  void reset() { count_ = 0; head_ = 0; sum_ = 0.0; }
  float update(float x) {
    if (count_ == n_) sum_ -= buf_[head_]; else ++count_;
    buf_[head_] = x;
    sum_ += x;
    head_ = (head_ + 1) % n_;
    return static_cast<float>(sum_ / count_);
  }
  int count() const { return count_; }
  float value() const { return count_ ? static_cast<float>(sum_ / count_) : 0.0f; }

 private:
  float buf_[CAP] = {};
  int n_ = CAP, count_ = 0, head_ = 0;
  double sum_ = 0.0;
};

inline float clampf(float x, float lo, float hi) { return x < lo ? lo : (x > hi ? hi : x); }

}  // namespace atc
