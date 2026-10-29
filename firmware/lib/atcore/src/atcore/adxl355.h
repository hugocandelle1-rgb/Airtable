// Analog Devices ADXL355 (SPI) : registres et conversions (logique pure).
#pragma once
#include <stdint.h>

namespace atc {
namespace adxl355 {

constexpr uint8_t kRegDevIdAd = 0x00;    // 0xAD
constexpr uint8_t kRegDevIdMst = 0x01;   // 0x1D
constexpr uint8_t kRegPartId = 0x02;     // 0xED
constexpr uint8_t kRegStatus = 0x04;
constexpr uint8_t kRegTemp2 = 0x06;
constexpr uint8_t kRegXData3 = 0x08;     // 9 octets : X3 X2 X1 Y3 Y2 Y1 Z3 Z2 Z1
constexpr uint8_t kRegFilter = 0x28;     // ODR_LPF[3:0]
constexpr uint8_t kRegRange = 0x2C;      // 01 ±2 g, 10 ±4 g, 11 ±8 g
constexpr uint8_t kRegPowerCtl = 0x2D;   // bit0 STANDBY (0 = mesure)
constexpr uint8_t kRegReset = 0x2F;      // écrire 0x52
constexpr uint8_t kResetCode = 0x52;
constexpr uint8_t kOdr125Hz = 0x05;      // ODR 125 Hz, LPF 31,25 Hz
constexpr uint8_t kOdr31Hz = 0x07;       // ODR 31,25 Hz, LPF 7,8 Hz

enum class Range : uint8_t { G2 = 1, G4 = 2, G8 = 3 };

inline uint8_t spiRead(uint8_t reg) { return static_cast<uint8_t>((reg << 1) | 1U); }
inline uint8_t spiWrite(uint8_t reg) { return static_cast<uint8_t>(reg << 1); }

// Mot 20 bits cadré à gauche sur 3 octets [b3, b2, b1] → entier signé.
int32_t raw20(uint8_t b3, uint8_t b2, uint8_t b1);
// Sensibilité [LSB/g] : 256000 (±2 g), 128000 (±4 g), 64000 (±8 g).
float lsbPerG(Range r);
inline float toG(int32_t raw, Range r) { return static_cast<float>(raw) / lsbPerG(r); }
// Température [°C] (12 bits) : 25 + (1885 − raw)/9,05 (valeurs typiques, à étalonner).
float tempC(uint16_t raw12);

}  // namespace adxl355
}  // namespace atc
