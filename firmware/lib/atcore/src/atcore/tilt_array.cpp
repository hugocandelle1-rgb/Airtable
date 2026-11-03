#include "atcore/tilt_array.h"

#include <math.h>

namespace atc {

// ================================ thermique =================================================

Vec2 ThermalComp::offset(float T_C) const {
  if (order == 0) return {};
  const float d = T_C - t_ref_C;
  const float d2 = order >= 2 ? d * d : 0.0f;
  return {c1[0] * d + c2[0] * d2, c1[1] * d + c2[1] * d2};
}

Vec2 compensateThermal(const ThermalComp& th, Vec2 raw, float T_C) {
  const Vec2 o = th.offset(T_C);
  return {raw.x - o.x, raw.y - o.y};
}

void rebaseBias(SensorCal* cal, const ThermalComp& new_th, float T_now_C) {
  const Vec2 o_old = cal->th.offset(T_now_C);
  const Vec2 o_new = new_th.offset(T_now_C);
  cal->geo.bias_x_urad += o_old.x - o_new.x;
  cal->geo.bias_y_urad += o_old.y - o_new.y;
  cal->th = new_th;
}

void ThermalLearner::add(float T_C, float x, float y) {
  if (!active_ || !isfinite(T_C) || !isfinite(x) || !isfinite(y)) return;
  if (n_ == 0) {
    t0_ = T_C;
    y0_[0] = x;
    y0_[1] = y;
    t_min_ = t_max_ = T_C;
  }
  if (T_C < t_min_) t_min_ = T_C;
  if (T_C > t_max_) t_max_ = T_C;
  const double d = T_C - t0_;
  const double yy[2] = {x - y0_[0], y - y0_[1]};
  double p = 1.0;
  for (int k = 0; k < 5; ++k) { s_[k] += p; p *= d; }
  for (int a = 0; a < 2; ++a) {
    sy_[a][0] += yy[a];
    sy_[a][1] += d * yy[a];
    sy_[a][2] += d * d * yy[a];
    syy_[a] += yy[a] * yy[a];
  }
  ++n_;
}

namespace {
// Résout A·β = b (m ≤ 3) par élimination de Gauss avec pivot partiel ; false si singulière.
bool solve(double A[3][3], double b[3], int m, double* beta) {
  for (int c = 0; c < m; ++c) {
    int piv = c;
    for (int r = c + 1; r < m; ++r) if (fabs(A[r][c]) > fabs(A[piv][c])) piv = r;
    if (fabs(A[piv][c]) < 1e-12) return false;
    if (piv != c) {
      for (int k = 0; k < m; ++k) { const double t = A[c][k]; A[c][k] = A[piv][k]; A[piv][k] = t; }
      const double t = b[c]; b[c] = b[piv]; b[piv] = t;
    }
    for (int r = c + 1; r < m; ++r) {
      const double f = A[r][c] / A[c][c];
      for (int k = c; k < m; ++k) A[r][k] -= f * A[c][k];
      b[r] -= f * b[c];
    }
  }
  for (int r = m - 1; r >= 0; --r) {
    double v = b[r];
    for (int k = r + 1; k < m; ++k) v -= A[r][k] * beta[k];
    beta[r] = v / A[r][r];
  }
  return true;
}
}  // namespace

ThermalLearner::Status ThermalLearner::fit(int order, uint32_t min_samples, float min_span_K, ThermalComp* out,
                                           float rms_urad[2]) const {
  if (order < 1) order = 1;
  if (order > 2) order = 2;
  if (n_ < min_samples || n_ < 4) return Status::TooFewSamples;
  if (spanK() < min_span_K) return Status::SpanTooSmall;
  const int m = order + 1;
  ThermalComp res;
  res.t_ref_C = static_cast<float>(t0_);
  res.order = static_cast<uint8_t>(order);
  for (int a = 0; a < 2; ++a) {
    double A[3][3], b[3], beta[3] = {0, 0, 0};
    for (int i = 0; i < m; ++i) {
      for (int j = 0; j < m; ++j) A[i][j] = s_[i + j];
      b[i] = sy_[a][i];
    }
    if (!solve(A, b, m, beta)) return Status::Singular;
    // Somme des carrés des résidus : Σy² − βᵀ·Xᵀy  (y centré sur la première valeur)
    double sse = syy_[a];
    for (int i = 0; i < m; ++i) sse -= beta[i] * sy_[a][i];
    if (sse < 0.0) sse = 0.0;
    if (rms_urad) rms_urad[a] = static_cast<float>(sqrt(sse / static_cast<double>(n_)));
    res.c1[a] = static_cast<float>(beta[1]);
    res.c2[a] = order >= 2 ? static_cast<float>(beta[2]) : 0.0f;
  }
  *out = res;
  return Status::Ok;
}

// ================================ bruit =====================================================

void RunningSigma::update(Vec2 v, float alpha) {
  if (!init_) { mx_ = v.x; my_ = v.y; var_ = 0.0f; init_ = true; return; }
  const float dx = v.x - mx_, dy = v.y - my_;
  var_ += alpha * (0.5f * (dx * dx + dy * dy) - var_);
  mx_ += alpha * dx;
  my_ += alpha * dy;
}

float RunningSigma::sigma(float floor_urad) const {
  const float s = sqrtf(var_ > 0.0f ? var_ : 0.0f);
  return s > floor_urad ? s : floor_urad;
}

// ================================ fusion ====================================================

namespace {
float median(float* v, int n) {          // n ≤ 4, tri par insertion
  for (int i = 1; i < n; ++i) {
    const float x = v[i];
    int j = i - 1;
    while (j >= 0 && v[j] > x) { v[j + 1] = v[j]; --j; }
    v[j + 1] = x;
  }
  return (n & 1) ? v[n / 2] : 0.5f * (v[n / 2 - 1] + v[n / 2]);
}
}  // namespace

FuseResult fuseTilt(const FuseInput* in, int n, const FuseConfig& cfg) {
  FuseResult r;
  if (n > kMaxTilt) n = kMaxTilt;
  int idx[kMaxTilt];
  int nv = 0;
  for (int i = 0; i < n; ++i) {
    if (in[i].valid && isfinite(in[i].tilt.x) && isfinite(in[i].tilt.y)) {
      idx[nv++] = i;
      r.valid_mask = static_cast<uint8_t>(r.valid_mask | (1u << i));
    }
  }
  r.n_valid = nv;
  if (nv == 0) return r;

  bool acc[kMaxTilt] = {false, false, false, false};
  if (nv >= 3) {
    float vx[kMaxTilt], vy[kMaxTilt];
    for (int k = 0; k < nv; ++k) { vx[k] = in[idx[k]].tilt.x; vy[k] = in[idx[k]].tilt.y; }
    const float mx = median(vx, nv), my = median(vy, nv);
    for (int k = 0; k < nv; ++k) {
      const Vec2& t = in[idx[k]].tilt;
      const float d = fmaxf(fabsf(t.x - mx), fabsf(t.y - my));
      acc[k] = d <= cfg.reject_urad;
    }
  } else if (nv == 2) {
    const Vec2 &a = in[idx[0]].tilt, &b = in[idx[1]].tilt;
    const bool ok = fmaxf(fabsf(a.x - b.x), fabsf(a.y - b.y)) <= cfg.reject_urad;
    acc[0] = acc[1] = ok;
    if (!ok) r.inconsistent = true;
  } else {
    acc[0] = true;
  }
  int nu = 0;
  for (int k = 0; k < nv; ++k) {
    if (acc[k]) { ++nu; r.used_mask = static_cast<uint8_t>(r.used_mask | (1u << idx[k])); }
    else r.rejected_mask = static_cast<uint8_t>(r.rejected_mask | (1u << idx[k]));
  }
  if (nv >= 3 && nu < 2) r.inconsistent = true;
  r.n_used = nu;
  if (r.inconsistent || nu == 0 || nu < cfg.min_sensors) return r;

  double sw = 0, sx = 0, sy = 0;
  for (int k = 0; k < nv; ++k) {
    if (!acc[k]) continue;
    const float s = in[idx[k]].sigma_urad > cfg.sigma_floor_urad ? in[idx[k]].sigma_urad : cfg.sigma_floor_urad;
    const double w = 1.0 / (static_cast<double>(s) * s);
    sw += w;
    sx += w * in[idx[k]].tilt.x;
    sy += w * in[idx[k]].tilt.y;
  }
  r.tilt = {static_cast<float>(sx / sw), static_cast<float>(sy / sw)};
  r.sigma_urad = static_cast<float>(1.0 / sqrt(sw));
  float lo[2] = {1e30f, 1e30f}, hi[2] = {-1e30f, -1e30f};
  for (int k = 0; k < nv; ++k) {
    if (!acc[k]) continue;
    const Vec2& t = in[idx[k]].tilt;
    if (t.x < lo[0]) lo[0] = t.x;
    if (t.x > hi[0]) hi[0] = t.x;
    if (t.y < lo[1]) lo[1] = t.y;
    if (t.y > hi[1]) hi[1] = t.y;
    const float d = fmaxf(fabsf(t.x - r.tilt.x), fabsf(t.y - r.tilt.y));
    if (d > r.dev_max_urad) r.dev_max_urad = d;
  }
  r.spread = {hi[0] - lo[0], hi[1] - lo[1]};
  r.valid = true;
  return r;
}

SlopeField fitSlopeField(const Vec2* tilt, const float* x_mm, const float* y_mm, uint8_t mask, int n) {
  SlopeField f;
  if (n > kMaxTilt) n = kMaxTilt;
  int m = 0;
  double cx = 0, cy = 0, mx = 0, my = 0;
  for (int i = 0; i < n; ++i) {
    if (!(mask & (1u << i))) continue;
    ++m;
    cx += x_mm[i] * 1e-3; cy += y_mm[i] * 1e-3;
    mx += tilt[i].x; my += tilt[i].y;
  }
  if (m < 3) return f;
  cx /= m; cy /= m; mx /= m; my /= m;
  double sxx = 0, sxy = 0, syy = 0, tx_x = 0, tx_y = 0, ty_x = 0, ty_y = 0;
  for (int i = 0; i < n; ++i) {
    if (!(mask & (1u << i))) continue;
    const double x = x_mm[i] * 1e-3 - cx, y = y_mm[i] * 1e-3 - cy;
    const double ax = tilt[i].x - mx, ay = tilt[i].y - my;
    sxx += x * x; sxy += x * y; syy += y * y;
    tx_x += x * ax; tx_y += y * ax;
    ty_x += x * ay; ty_y += y * ay;
  }
  const double det = sxx * syy - sxy * sxy;
  if (sxx <= 0 || syy <= 0 || det < 0.05 * sxx * syy) return f;     // capteurs alignés
  const double a1 = (tx_x * syy - tx_y * sxy) / det, a2 = (sxx * tx_y - sxy * tx_x) / det;
  const double b1 = (ty_x * syy - ty_y * sxy) / det, b2 = (sxx * ty_y - sxy * ty_x) / det;
  f.zxx = static_cast<float>(a1);
  f.zxy = static_cast<float>(0.5 * (a2 + b1));
  f.zyy = static_cast<float>(b2);
  f.curl = static_cast<float>(0.5 * (a2 - b1));
  f.valid = true;
  return f;
}

// ================================ retournement ==============================================

const char* flipStateName(FlipState s) {
  switch (s) {
    case FlipState::Idle: return "idle";
    case FlipState::Settle0: return "settle0";
    case FlipState::Measure0: return "measure0";
    case FlipState::Rotate180: return "rotate";
    case FlipState::Settle180: return "settle180";
    case FlipState::Measure180: return "measure180";
    case FlipState::ReturnZero: return "return";
    case FlipState::SettleRet: return "settle_ret";
    case FlipState::MeasureRet: return "measure_ret";
    case FlipState::Done: return "done";
    case FlipState::Failed: return "failed";
  }
  return "?";
}

const char* flipErrorName(FlipError e) {
  switch (e) {
    case FlipError::None: return "none";
    case FlipError::Aborted: return "aborted";
    case FlipError::ActuatorTimeout: return "actuator_timeout";
    case FlipError::SensorInvalid: return "sensor_invalid";
    case FlipError::TooFewSamples: return "too_few_samples";
    case FlipError::Fault: return "fault";
  }
  return "?";
}

bool FlipSequencer::start(uint32_t now_ms) {
  if (active()) return false;
  a_.reset(); b_.reset(); a2_.reset();
  res_ = FlipResult();
  err_ = FlipError::None;
  target_deg_ = 0.0f;
  enter(FlipState::Settle0, now_ms);
  return true;
}

void FlipSequencer::abort() { if (active()) fail(FlipError::Aborted); }

void FlipSequencer::fail(FlipError e) {
  err_ = e;
  st_ = FlipState::Failed;
  target_deg_ = 0.0f;               // l'actionneur ramène l'embase à 0°
  res_.valid = false;
}

void FlipSequencer::enter(FlipState s, uint32_t now_ms) {
  st_ = s;
  t_enter_ = now_ms;
  last_valid_ms_ = now_ms;
  switch (s) {
    case FlipState::Rotate180: target_deg_ = 180.0f; break;
    case FlipState::ReturnZero: target_deg_ = 0.0f; break;
    default: break;
  }
}

void FlipSequencer::finish(uint32_t) {
  const Vec2 a = a_.mean(), b = b_.mean();
  Vec2 aeff = a;
  res_.reliable = true;
  res_.drift = {};
  if (cfg_.return_check && a2_.n > 0) {
    const Vec2 a2 = a2_.mean();
    res_.drift = {a2.x - a.x, a2.y - a.y};
    aeff = {0.5f * (a.x + a2.x), 0.5f * (a.y + a2.y)};
    res_.reliable = fmaxf(fabsf(res_.drift.x), fabsf(res_.drift.y)) <= cfg_.drift_limit_urad;
  }
  res_.a = a;
  res_.b = b;
  res_.bias = {0.5f * (aeff.x + b.x), 0.5f * (aeff.y + b.y)};
  res_.slope = {0.5f * (aeff.x - b.x), 0.5f * (aeff.y - b.y)};
  res_.t_mean_C = 0.5f * (a_.meanT() + b_.meanT());
  res_.n_a = static_cast<uint16_t>(a_.n > 65535 ? 65535 : a_.n);
  res_.n_b = static_cast<uint16_t>(b_.n > 65535 ? 65535 : b_.n);
  res_.valid = true;
  st_ = FlipState::Done;
  target_deg_ = 0.0f;
}

void FlipSequencer::update(uint32_t now_ms, const FlipInputs& in) {
  if (!active()) return;
  if (in.fault) { fail(FlipError::Fault); return; }
  const uint32_t dt = now_ms - t_enter_;

  auto measure = [&](Acc* acc, FlipState next) {
    if (!in.at_target) { fail(FlipError::Fault); return; }           // l'embase a bougé pendant la mesure
    if (in.new_sample && in.sample_valid) { acc->add(in.sample, in.T_C); last_valid_ms_ = now_ms; }
    if (static_cast<uint32_t>(now_ms - last_valid_ms_) > cfg_.invalid_timeout_ms) { fail(FlipError::SensorInvalid); return; }
    if (dt >= cfg_.avg_ms) {
      if (acc->n < cfg_.min_samples) { fail(FlipError::TooFewSamples); return; }
      if (next == FlipState::Done) finish(now_ms); else enter(next, now_ms);
    }
  };

  switch (st_) {
    case FlipState::Settle0:
      if (in.at_target && dt >= cfg_.settle_ms / 4) enter(FlipState::Measure0, now_ms);
      else if (dt > cfg_.move_timeout_ms + cfg_.settle_ms / 4) fail(FlipError::ActuatorTimeout);
      break;
    case FlipState::Measure0: measure(&a_, FlipState::Rotate180); break;
    case FlipState::Rotate180:
      if (in.at_target) enter(FlipState::Settle180, now_ms);
      else if (dt > cfg_.move_timeout_ms) fail(FlipError::ActuatorTimeout);
      break;
    case FlipState::Settle180:
      if (dt >= cfg_.settle_ms) enter(FlipState::Measure180, now_ms);
      break;
    case FlipState::Measure180: measure(&b_, FlipState::ReturnZero); break;
    case FlipState::ReturnZero:
      if (in.at_target) {
        if (cfg_.return_check) enter(FlipState::SettleRet, now_ms); else finish(now_ms);
      } else if (dt > cfg_.move_timeout_ms) {
        fail(FlipError::ActuatorTimeout);
      }
      break;
    case FlipState::SettleRet:
      if (dt >= cfg_.settle_ms) enter(FlipState::MeasureRet, now_ms);
      break;
    case FlipState::MeasureRet: measure(&a2_, FlipState::Done); break;
    default: break;
  }
}

}  // namespace atc
