#include "atcore/crc.h"

namespace atc {

uint8_t crc8Sensirion(const uint8_t* data, size_t len) {
  uint8_t crc = 0xFF;
  for (size_t i = 0; i < len; ++i) {
    crc ^= data[i];
    for (int b = 0; b < 8; ++b) {
      crc = (crc & 0x80) ? static_cast<uint8_t>((crc << 1) ^ 0x31)
                         : static_cast<uint8_t>(crc << 1);
    }
  }
  return crc;
}

bool sensirionWordOk(const uint8_t* t) { return crc8Sensirion(t, 2) == t[2]; }

// Transcription de l'algorithme bit à bit de la fiche Murata (SCL3300-D01).
uint8_t crc8Scl3300(uint32_t frame) {
  uint8_t crc = 0xFF;
  for (int bit = 31; bit > 7; --bit) {
    const bool in = ((frame >> bit) & 1U) != 0;
    bool top = (crc & 0x80) != 0;
    if (in) top = !top;
    crc = static_cast<uint8_t>(crc << 1);
    if (top) crc ^= 0x1D;
  }
  return static_cast<uint8_t>(~crc);
}

}  // namespace atc
