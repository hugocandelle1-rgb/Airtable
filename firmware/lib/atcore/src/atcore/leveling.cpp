#include "atcore/leveling.h"

#include <math.h>

namespace atc {

float stepsToMicrons(int32_t steps, float um_per_step) { return static_cast<float>(steps) * um_per_step; }
int32_t micronsToSteps(float um, float um_per_step) {
  if (um_per_step <= 0.0f) return 0;
  return static_cast<int32_t>(lroundf(um / um_per_step));
}
float uradToMicrons(float urad, float lever_mm) { return urad * lever_mm * 1e-3f; }
float micronsToUrad(float um, float lever_mm) { return lever_mm > 0.0f ? um / (lever_mm * 1e-3f) : 0.0f; }
int32_t uradToSteps(float urad, float lever_mm, float um_per_step) {
  return micronsToSteps(uradToMicrons(urad, lever_mm), um_per_step);
}
float stepsToUrad(int32_t steps, float lever_mm, float um_per_step) {
  return micronsToUrad(stepsToMicrons(steps, um_per_step), lever_mm);
}

Decoupling buildDecoupling(const LevelGeometry& g) {
  Decoupling d;
  // µm = mm · µrad · 1e-3
  d.M = {g.x_mm[0] * 1e-3f, g.y_mm[0] * 1e-3f, g.x_mm[1] * 1e-3f, g.y_mm[1] * 1e-3f};
  const float det = d.M.det();
  // Conditionnement minimal : |det| relatif à la norme des lignes.
  const float n0 = hypotf(d.M.a, d.M.b), n1 = hypotf(d.M.c, d.M.d);
  if (n0 <= 0.0f || n1 <= 0.0f || fabsf(det) < 0.05f * n0 * n1) { d.valid = false; return d; }
  d.Minv = {d.M.d / det, -d.M.b / det, -d.M.c / det, d.M.a / det};
  d.valid = true;
  return d;
}

void slopeToSteps(const Decoupling& d, const LevelGeometry& g, Vec2 ds, int32_t steps[2]) {
  if (!d.valid) { steps[0] = steps[1] = 0; return; }
  const Vec2 z = d.M.mul(ds);   // µm de levée
  steps[0] = micronsToSteps(z.x, g.um_per_step[0]);
  steps[1] = micronsToSteps(z.y, g.um_per_step[1]);
}

Vec2 stepsToSlope(const Decoupling& d, const LevelGeometry& g, const int32_t steps[2]) {
  if (!d.valid) return {};
  const Vec2 z = {stepsToMicrons(steps[0], g.um_per_step[0]), stepsToMicrons(steps[1], g.um_per_step[1])};
  return d.Minv.mul(z);
}

Vec2 applyTiltCal(const TiltCal& c, Vec2 raw) {
  const float x = c.sign_x * (raw.x - c.bias_x_urad);
  const float y = c.sign_y * (raw.y - c.bias_y_urad);
  const float th = c.mount_rot_deg * 3.14159265358979f / 180.0f;
  const float cs = cosf(th), sn = sinf(th);
  return {cs * x - sn * y, sn * x + cs * y};
}

bool LevelController::update(uint32_t now_ms, Vec2 tilt, bool valid, Vec2* ds) {
  if (hold_) {
    if (static_cast<int32_t>(now_ms - hold_until_ms_) < 0) { count_ = 0; return false; }
    hold_ = false;
  }
  if (!valid) { count_ = 0; return false; }
  const Vec2 e = {target_.x - tilt.x, target_.y - tilt.y};
  const bool out_x = fabsf(e.x) > cfg_.deadband_urad;
  const bool out_y = fabsf(e.y) > cfg_.deadband_urad;
  if (!out_x && !out_y) { count_ = 0; return false; }
  if (++count_ < cfg_.confirm_n) return false;
  count_ = 0;
  auto lim = [&](float v) {
    v *= cfg_.gain;
    if (v > cfg_.max_move_urad) v = cfg_.max_move_urad;
    if (v < -cfg_.max_move_urad) v = -cfg_.max_move_urad;
    return v;
  };
  if (ds) *ds = {out_x ? lim(e.x) : 0.0f, out_y ? lim(e.y) : 0.0f};
  return true;
}

bool clampSteps(int32_t* t, int32_t lo, int32_t hi) {
  if (*t < lo) { *t = lo; return true; }
  if (*t > hi) { *t = hi; return true; }
  return false;
}

}  // namespace atc
