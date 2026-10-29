// Sensirion SDP8xx (SDP810-500Pa / 125Pa) : commandes, décodage, débit d'une buse.
#pragma once
#include <stdint.h>

namespace atc {

namespace sdp8xx {
constexpr uint8_t kI2cAddr = 0x25;
constexpr uint16_t kCmdStartContDpAvg = 0x3615;    // pression diff., moyenne jusqu'à la lecture
constexpr uint16_t kCmdStartContDp = 0x361E;       // pression diff., sans moyenne
constexpr uint16_t kCmdStartContMassAvg = 0x3603;  // (débit massique, non utilisé)
constexpr uint16_t kCmdStop = 0x3FF9;
constexpr uint16_t kCmdReadId1 = 0x367C;
constexpr uint16_t kCmdReadId2 = 0xE102;
constexpr uint8_t kGeneralCallReset = 0x06;        // à l'adresse 0x00
constexpr float kScale500Pa = 60.0f;               // LSB/Pa nominal SDP810-500Pa
constexpr float kScale125Pa = 240.0f;              // LSB/Pa nominal SDP810-125Pa
}  // namespace sdp8xx

struct Sdp8xxSample {
  float dp_Pa = 0.0f;
  float temp_C = 0.0f;
  float scale = 0.0f;   // facteur d'échelle réellement lu dans la trame [LSB/Pa]
  bool ok = false;
};

// Décode une trame de 9 octets [dp(2)+CRC, T(2)+CRC, scale(2)+CRC].
// `fallback_scale` est utilisé si le mot d'échelle lu vaut 0. Retourne false si un CRC est faux.
bool decodeSdp8xx(const uint8_t buf[9], float fallback_scale, Sdp8xxSample* out);

// Débit volumique d'une buse calibrée : Q = Cd·A·√(2|Δp|/ρ), signé comme Δp [m³/s].
float nozzleFlow_m3s(float dp_Pa, float rho, float cd, float area_m2);
float nozzleArea_m2(float diameter_mm);

}  // namespace atc
