#include "atcore/inclinometer.h"

#include "atcore/scl3300.h"

namespace atc {

bool AccAccumulator::flush(TiltSample* out) {
  if (n_ == 0 || !out) return false;
  const double inv = 1.0 / static_cast<double>(n_);
  scl3300::tiltFromAcc(static_cast<float>(sx_ * inv), static_cast<float>(sy_ * inv),
                       static_cast<float>(sz_ * inv), &out->x_urad, &out->y_urad);
  out->temp_C = static_cast<float>(st_ * inv);
  out->n_avg = count();
  out->valid = true;
  reset();
  return true;
}

}  // namespace atc
