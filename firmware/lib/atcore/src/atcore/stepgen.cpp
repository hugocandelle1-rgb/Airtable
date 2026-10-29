#include "atcore/stepgen.h"

namespace atc {

namespace {
constexpr uint64_t kOne = 1ULL << 32;
}

void StepGen::configure(uint32_t tick_hz, uint32_t vmax_sps, uint32_t accel_sps2, uint32_t vmin_sps) {
  tick_hz_ = tick_hz ? tick_hz : 1;
  vmin_sps_ = vmin_sps ? vmin_sps : 1;
  vmax_sps_ = vmax_sps;
  accel_sps2_ = accel_sps2 ? accel_sps2 : 1;
  setMaxSpeed(vmax_sps);
  setAccel(accel_sps2_);
  v_ = 0;
  phase_ = 0;
}

void StepGen::setMaxSpeed(uint32_t vmax_sps) {
  const uint32_t cap = tick_hz_ / 2;
  if (vmax_sps > cap) vmax_sps = cap;
  if (vmax_sps < vmin_sps_) vmax_sps = vmin_sps_;
  vmax_sps_ = vmax_sps;
  vmax_q_ = (static_cast<uint64_t>(vmax_sps) << 32) / tick_hz_;
  vmin_q_ = (static_cast<uint64_t>(vmin_sps_) << 32) / tick_hz_;
}

void StepGen::setAccel(uint32_t a) {
  accel_sps2_ = a ? a : 1;
  // dv = a / tick² en Q32 (pas/tick par tick)
  dv_q_ = (static_cast<uint64_t>(accel_sps2_) << 32) / (static_cast<uint64_t>(tick_hz_) * tick_hz_);
  if (dv_q_ == 0) dv_q_ = 1;
}

uint64_t StepGen::stopDistQ32(uint64_t v) const {
  // v²/(2·dv) : v ≤ 2^31 donc v² ≤ 2^62, pas de débordement.
  return (v * v) / (2 * dv_q_);
}

uint32_t StepGen::speedSps() const { return static_cast<uint32_t>((v_ * tick_hz_) >> 32); }

void StepGen::stop() {
  if (v_ == 0) { target_ = pos_; return; }
  const uint64_t d = stopDistQ32(v_) >> 32;
  target_ = pos_ + (dir_ > 0 ? 1 : -1) * static_cast<int32_t>(d + 1);
}

void StepGen::emergencyStop() {
  v_ = 0;
  phase_ = 0;
  target_ = pos_;
}

bool StepGen::setPosition(int32_t p) {
  if (v_ != 0) return false;
  pos_ = p;
  target_ = p;
  return true;
}

bool StepGen::tick() {
  const int32_t rem = target_ - pos_;
  const int8_t want = rem > 0 ? 1 : (rem < 0 ? -1 : 0);
  const uint32_t absrem = static_cast<uint32_t>(rem > 0 ? rem : -rem);

  if (v_ == 0) {
    if (want == 0) return false;
    if (want != dir_) { dir_ = want; return false; }   // tick d'établissement de DIR
    v_ = vmin_q_;                                      // démarrage
    phase_ = kOne >> 1;                                // première impulsion rapide
  } else if (want == 0) {
    // Arrivé alors que la vitesse est non nulle (cible changée / profil arrondi) : arrêt net.
    v_ = 0;
    phase_ = 0;
    return false;
  }

  if (want != dir_) {
    // Cible de l'autre côté : décélérer jusqu'à l'arrêt, puis repartir en sens inverse.
    v_ = (v_ > dv_q_ + vmin_q_) ? v_ - dv_q_ : 0;
    if (v_ == 0) { phase_ = 0; return false; }
  } else {
    const uint64_t rem_q = static_cast<uint64_t>(absrem) << 32;
    const uint64_t vnext = (v_ + dv_q_ > vmax_q_) ? vmax_q_ : v_ + dv_q_;
    if (rem_q <= stopDistQ32(v_)) {
      v_ = (v_ > dv_q_ + vmin_q_) ? v_ - dv_q_ : vmin_q_;      // décélération
    } else if (v_ < vmax_q_ && rem_q > stopDistQ32(vnext) + kOne) {
      v_ = vnext;                                                // accélération
    } else if (v_ > vmax_q_) {
      v_ = (v_ > dv_q_ + vmax_q_) ? v_ - dv_q_ : vmax_q_;      // vitesse max abaissée en cours de route
    }
  }

  phase_ += v_;
  if (phase_ >= kOne) {
    phase_ -= kOne;
    pos_ += dir_;
    return true;
  }
  return false;
}

uint32_t StepGen::estimateMs(uint32_t n) const {
  if (n == 0) return 0;
  const double v = static_cast<double>(vmax_sps_), a = static_cast<double>(accel_sps2_);
  const double n_acc = v * v / (2.0 * a);              // pas pour atteindre vmax
  double t;
  if (static_cast<double>(n) >= 2.0 * n_acc) t = 2.0 * v / a + (static_cast<double>(n) - 2.0 * n_acc) / v;
  else t = 2.0 * __builtin_sqrt(static_cast<double>(n) / a);
  return static_cast<uint32_t>(t * 1000.0) + 1;
}

}  // namespace atc
