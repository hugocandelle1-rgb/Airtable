#include "atcore/scl3300.h"

#include <math.h>

#include "atcore/crc.h"

namespace atc {
namespace scl3300 {

uint32_t makeFrame(uint8_t op, uint16_t data) {
  uint32_t f = (static_cast<uint32_t>(op) << 24) | (static_cast<uint32_t>(data) << 8);
  return f | crc8Scl3300(f);
}

Response parseResponse(uint32_t f) {
  Response r;
  r.op = static_cast<uint8_t>(f >> 24);
  r.rs = r.op & 0x03;
  r.data = static_cast<uint16_t>((f >> 8) & 0xFFFF);
  r.crc_ok = (crc8Scl3300(f) == static_cast<uint8_t>(f & 0xFF));
  return r;
}

float lsbPerG(Mode m) {
  switch (m) {
    case Mode::M1: return 6000.0f;
    case Mode::M2: return 3000.0f;
    default: return 12000.0f;  // modes 3 et 4 (inclinomètre)
  }
}

void tiltFromAcc(float ax, float ay, float az, float* tx, float* ty) {
  // θx = atan2(ax, √(ay²+az²)), θy = atan2(ay, √(ax²+az²)) : exact quel que soit l'angle.
  const float x = atan2f(ax, sqrtf(ay * ay + az * az));
  const float y = atan2f(ay, sqrtf(ax * ax + az * az));
  if (tx) *tx = x * 1e6f;
  if (ty) *ty = y * 1e6f;
}

}  // namespace scl3300
}  // namespace atc
