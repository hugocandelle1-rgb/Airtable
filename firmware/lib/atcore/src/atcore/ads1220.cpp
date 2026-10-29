#include "atcore/ads1220.h"

namespace atc {
namespace ads1220 {

void encodeRegisters(const Config& c, uint8_t r[4]) {
  r[0] = static_cast<uint8_t>((c.mux << 4) | (c.gain << 1) | (c.pga_bypass ? 1 : 0));
  r[1] = static_cast<uint8_t>((c.rate << 5) | (0 << 3) | (c.continuous ? 0x04 : 0));
  r[2] = static_cast<uint8_t>((c.vref << 6) | ((c.fir & 3) << 4));
  r[3] = static_cast<uint8_t>(c.drdy_on_dout ? 0x02 : 0x00);
}

int32_t raw24(uint8_t b2, uint8_t b1, uint8_t b0) {
  int32_t v = (static_cast<int32_t>(b2) << 16) | (static_cast<int32_t>(b1) << 8) | b0;
  if (v & 0x800000) v -= 0x1000000;
  return v;
}

float toVolts(int32_t code, float vref, int gain) {
  return static_cast<float>(code) / 8388608.0f * vref / static_cast<float>(gain);
}

float toMicrometers(float volts, const DispChannelCal& cal) {
  return cal.offset_um + cal.sens_um_per_V * volts * cal.divider;
}

}  // namespace ads1220
}  // namespace atc
