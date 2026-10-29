// TI TMP117 : registres et conversion (logique pure).
#pragma once
#include <stdint.h>

namespace atc {
namespace tmp117 {

constexpr uint8_t kRegTemp = 0x00;
constexpr uint8_t kRegConfig = 0x01;
constexpr uint8_t kRegDeviceId = 0x0F;
constexpr uint16_t kDeviceId = 0x0117;
constexpr uint16_t kConfigDataReady = 0x2000;   // bit 13 du registre de configuration
constexpr uint16_t kRawInvalid = 0x8000;        // −256 °C : valeur sentinelle de la fiche
constexpr float kLsbC = 0.0078125f;             // 2^-7 °C

inline float toC(uint16_t raw) { return static_cast<float>(static_cast<int16_t>(raw)) * kLsbC; }
inline bool plausible(uint16_t raw) { return raw != kRawInvalid && raw != 0xFFFF; }

}  // namespace tmp117
}  // namespace atc
