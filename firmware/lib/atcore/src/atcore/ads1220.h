// TI ADS1220 (ADC 24 bits, SPI mode 1) : commandes, registres, conversions (logique pure).
#pragma once
#include <stdint.h>

namespace atc {
namespace ads1220 {

constexpr uint8_t kCmdReset = 0x06;
constexpr uint8_t kCmdStart = 0x08;
constexpr uint8_t kCmdPowerDown = 0x02;
constexpr uint8_t kCmdRdata = 0x10;
inline uint8_t cmdRreg(uint8_t reg, uint8_t n_minus_1) { return 0x20 | (reg << 2) | (n_minus_1 & 3); }
inline uint8_t cmdWreg(uint8_t reg, uint8_t n_minus_1) { return 0x40 | (reg << 2) | (n_minus_1 & 3); }

// MUX (REG0[7:4]) : entrées simples référencées à AVSS pour 3 capteurs 0…Vref.
enum Mux : uint8_t { kAin0Ain1 = 0x0, kAin0Avss = 0x8, kAin1Avss = 0x9, kAin2Avss = 0xA, kAin3Avss = 0xB };
enum Gain : uint8_t { kG1 = 0, kG2, kG4, kG8, kG16, kG32, kG64, kG128 };
enum DataRate : uint8_t { kSps20 = 0, kSps45, kSps90, kSps175, kSps330, kSps600, kSps1000 };
enum VRef : uint8_t { kVrefInternal = 0, kVrefExt0 = 1, kVrefExt1 = 2, kVrefAvdd = 3 };

struct Config {
  uint8_t mux = kAin0Avss;
  Gain gain = kG1;
  bool pga_bypass = true;        // gain 1 : PGA contourné (entrée jusqu'à AVDD)
  DataRate rate = kSps90;
  bool continuous = false;       // false = « single-shot » (un canal à la fois, multiplexé)
  VRef vref = kVrefInternal;
  uint8_t fir = 1;               // 01 : rejet simultané 50/60 Hz
  bool drdy_on_dout = false;
};

// Octets des registres 0..3 pour une configuration.
void encodeRegisters(const Config& c, uint8_t regs[4]);
inline float vrefVolts(VRef v) { return v == kVrefInternal ? 2.048f : (v == kVrefAvdd ? 3.3f : 2.5f); }
inline int gainValue(Gain g) { return 1 << static_cast<int>(g); }

// Mot 24 bits (3 octets) → entier signé.
int32_t raw24(uint8_t b2, uint8_t b1, uint8_t b0);
// Tension d'entrée [V] pour un code : code/2^23 · Vref/gain.
float toVolts(int32_t code, float vref, int gain);

// Capteur de déplacement : x[µm] = offset_um + sens_um_per_V · V.
struct DispChannelCal {
  float sens_um_per_V = 1000.0f;
  float offset_um = 0.0f;
  float divider = 1.0f;   // rapport du pont diviseur d'entrée (V_capteur / V_ADC)
};
float toMicrometers(float volts, const DispChannelCal& cal);

}  // namespace ads1220
}  // namespace atc
