#include "atcore/sdp8xx.h"

#include <math.h>

#include "atcore/crc.h"

namespace atc {

bool decodeSdp8xx(const uint8_t b[9], float fallback_scale, Sdp8xxSample* out) {
  if (!out) return false;
  out->ok = false;
  if (!sensirionWordOk(&b[0]) || !sensirionWordOk(&b[3]) || !sensirionWordOk(&b[6])) return false;
  const int16_t dp_raw = static_cast<int16_t>((b[0] << 8) | b[1]);
  const int16_t t_raw = static_cast<int16_t>((b[3] << 8) | b[4]);
  const uint16_t sc = static_cast<uint16_t>((b[6] << 8) | b[7]);
  const float scale = sc ? static_cast<float>(sc) : fallback_scale;
  if (scale <= 0.0f) return false;
  out->scale = scale;
  out->dp_Pa = static_cast<float>(dp_raw) / scale;
  out->temp_C = static_cast<float>(t_raw) / 200.0f;
  out->ok = true;
  return true;
}

float nozzleArea_m2(float diameter_mm) {
  const float d = diameter_mm * 1e-3f;
  return 3.14159265358979f * d * d * 0.25f;
}

float nozzleFlow_m3s(float dp_Pa, float rho, float cd, float area_m2) {
  if (rho <= 0.0f) return 0.0f;
  const float q = cd * area_m2 * sqrtf(2.0f * fabsf(dp_Pa) / rho);
  return dp_Pa < 0.0f ? -q : q;
}

}  // namespace atc
