#include "atcore/adxl355.h"

namespace atc {
namespace adxl355 {

int32_t raw20(uint8_t b3, uint8_t b2, uint8_t b1) {
  int32_t v = (static_cast<int32_t>(b3) << 12) | (static_cast<int32_t>(b2) << 4) | (b1 >> 4);
  if (v & 0x80000) v -= 0x100000;  // extension de signe sur 20 bits
  return v;
}

float lsbPerG(Range r) {
  switch (r) {
    case Range::G2: return 256000.0f;
    case Range::G4: return 128000.0f;
    default: return 64000.0f;
  }
}

float tempC(uint16_t raw12) { return 25.0f + (1885.0f - static_cast<float>(raw12 & 0x0FFF)) / 9.05f; }

}  // namespace adxl355
}  // namespace atc
