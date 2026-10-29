#include "atcore/setpoints.h"

#include <ctype.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>

namespace atc {

void SetpointTable::clear() { n_ = 0; h_target_um_ = 0.0f; }

bool SetpointTable::add(float mass_g, float p_Pa) {
  if (!(mass_g > 0.0f) || !(p_Pa >= 0.0f) || !isfinite(mass_g) || !isfinite(p_Pa)) return false;
  for (size_t i = 0; i < n_; ++i) {
    if (fabsf(pts_[i].mass_g - mass_g) < 1e-6f) { pts_[i].p_Pa = p_Pa; return true; }
  }
  if (n_ >= kMaxPoints) return false;
  size_t i = n_;
  while (i > 0 && pts_[i - 1].mass_g > mass_g) { pts_[i] = pts_[i - 1]; --i; }
  pts_[i] = {mass_g, p_Pa};
  ++n_;
  return true;
}

bool SetpointTable::interpolate(float m, float* p, bool* clamped, bool extrapolate) const {
  if (n_ == 0 || !p) return false;
  if (clamped) *clamped = false;
  if (n_ == 1) { *p = pts_[0].p_Pa; if (clamped) *clamped = (m != pts_[0].mass_g); return true; }
  size_t lo, hi;
  if (m <= pts_[0].mass_g) {
    if (m < pts_[0].mass_g && clamped) *clamped = true;
    if (!extrapolate || m == pts_[0].mass_g) { *p = pts_[0].p_Pa; return true; }
    lo = 0; hi = 1;
  } else if (m >= pts_[n_ - 1].mass_g) {
    if (m > pts_[n_ - 1].mass_g && clamped) *clamped = true;
    if (!extrapolate || m == pts_[n_ - 1].mass_g) { *p = pts_[n_ - 1].p_Pa; return true; }
    lo = n_ - 2; hi = n_ - 1;
  } else {
    lo = 0;
    while (pts_[lo + 1].mass_g < m) ++lo;
    hi = lo + 1;
  }
  const float f = (m - pts_[lo].mass_g) / (pts_[hi].mass_g - pts_[lo].mass_g);
  float v = pts_[lo].p_Pa + f * (pts_[hi].p_Pa - pts_[lo].p_Pa);
  if (v < 0.0f) v = 0.0f;
  *p = v;
  return true;
}

// ---- parseur JSON minimal -------------------------------------------------------------

namespace {

// Cherche `"key"` à partir de `from` (et avant `end`) ; retourne un pointeur juste après le « : ».
const char* findKey(const char* from, const char* end, const char* key) {
  const size_t kl = strlen(key);
  for (const char* p = from; p + kl + 2 <= end; ++p) {
    if (*p == '"' && strncmp(p + 1, key, kl) == 0 && p[1 + kl] == '"') {
      const char* q = p + kl + 2;
      while (q < end && isspace(static_cast<unsigned char>(*q))) ++q;
      if (q < end && *q == ':') return q + 1;
    }
  }
  return nullptr;
}

bool readNumber(const char* p, const char* end, float* out) {
  while (p < end && isspace(static_cast<unsigned char>(*p))) ++p;
  if (p >= end) return false;
  char* e = nullptr;
  const double v = strtod(p, &e);
  if (e == p || !isfinite(v)) return false;
  *out = static_cast<float>(v);
  return true;
}

}  // namespace

int SetpointTable::loadJson(const char* text) {
  if (!text) return -1;
  const char* end = text + strlen(text);
  SetpointTable tmp;
  float h = 0.0f;
  const char* hp = findKey(text, end, "h_target_um");
  if (hp && readNumber(hp, end, &h)) tmp.h_target_um_ = h;
  const char* arr = findKey(text, end, "points");
  if (!arr) return -1;
  const char* q = strchr(arr, '[');
  if (!q) return -1;
  const char* close = strchr(q, ']');
  if (!close) return -1;
  // Chaque objet { ... } du tableau
  const char* p = q + 1;
  while (p < close) {
    const char* ob = strchr(p, '{');
    if (!ob || ob >= close) break;
    const char* oe = strchr(ob, '}');
    if (!oe || oe > close) return -1;
    float m, pr;
    const char* mp = findKey(ob, oe, "mass_g");
    const char* pp = findKey(ob, oe, "p_Pa");
    if (!mp || !pp || !readNumber(mp, oe, &m) || !readNumber(pp, oe, &pr)) return -1;
    if (!tmp.add(m, pr)) return -1;
    p = oe + 1;
  }
  if (tmp.n_ == 0) return -1;
  *this = tmp;
  return static_cast<int>(n_);
}

}  // namespace atc
