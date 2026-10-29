// Murata SCL3300-D01 : codage/décodage des trames SPI 32 bits (logique pure).
//
// Trame : [OP(8) | DATA(16) | CRC(8)]. Le protocole est « décalé » : la réponse à une
// requête arrive dans la trame SUIVANTE (off-frame). RS (2 bits de poids faible de OP) :
// 00 démarrage, 01 normal, 11 erreur.
#pragma once
#include <stdint.h>

namespace atc {
namespace scl3300 {

// Trames de commande précalculées (CRC inclus) — vérifiées par les tests unitaires.
constexpr uint32_t kCmdBank0 = 0xFC000073;
constexpr uint32_t kCmdBank1 = 0xFC00016E;   // CRC calculé (algorithme validé sur les autres trames)
constexpr uint32_t kCmdReadAccX = 0x040000F7;
constexpr uint32_t kCmdReadAccY = 0x080000FD;
constexpr uint32_t kCmdReadAccZ = 0x0C0000FB;
constexpr uint32_t kCmdReadSto = 0x100000E9;
constexpr uint32_t kCmdReadTemp = 0x140000EF;
constexpr uint32_t kCmdReadStatus = 0x180000E5;
constexpr uint32_t kCmdReadAngX = 0x240000C7;
constexpr uint32_t kCmdReadAngY = 0x280000CD;
constexpr uint32_t kCmdReadAngZ = 0x2C0000CB;
constexpr uint32_t kCmdReadWhoAmI = 0x40000091;
constexpr uint32_t kCmdReadSerial1 = 0x640000A7;
constexpr uint32_t kCmdReadSerial2 = 0x680000AD;
constexpr uint32_t kCmdReadMode = 0xB400001F;
constexpr uint32_t kCmdSetMode1 = 0xB400001F;
constexpr uint32_t kCmdSetMode2 = 0xB4000102;
constexpr uint32_t kCmdSetMode3 = 0xB4000225;
constexpr uint32_t kCmdSetMode4 = 0xB4000338;
constexpr uint32_t kCmdSwReset = 0xB4002098;
constexpr uint32_t kCmdEnableAngles = 0xB0001F6F;
constexpr uint8_t kWhoAmI = 0xC1;

enum class Mode : uint8_t { M1 = 1, M2 = 2, M3 = 3, M4 = 4 };

// Construit une trame (écriture ou lecture) : op = octet de tête, data = 16 bits.
uint32_t makeFrame(uint8_t op, uint16_t data);

struct Response {
  uint8_t op = 0;
  uint8_t rs = 0;       // statut de retour (0..3)
  uint16_t data = 0;
  bool crc_ok = false;
};
Response parseResponse(uint32_t frame);

inline int16_t toSigned(uint16_t v) { return static_cast<int16_t>(v); }

// Sensibilité d'accélération [LSB/g] selon le mode (D01).
float lsbPerG(Mode m);
inline float accToG(int16_t raw, Mode m) { return static_cast<float>(raw) / lsbPerG(m); }
// Température [°C] : T = −273 + raw/18,9.
inline float tempC(uint16_t raw) { return -273.0f + static_cast<float>(toSigned(raw)) / 18.9f; }
// Sortie d'angle interne [°] : raw/2^14 · 90 (résolution 0,0055° — trop grossière pour le
// nivellement fin ; on préfère calculer l'angle à partir de l'accélération moyennée).
inline float angleDeg(int16_t raw) { return static_cast<float>(raw) * (90.0f / 16384.0f); }

// Inclinaisons [µrad] à partir des accélérations [g] : pente montante selon +X / +Y
// (positive quand l'axe pointe vers le haut), sin θx = ax/|a| ...
void tiltFromAcc(float ax_g, float ay_g, float az_g, float* tx_urad, float* ty_urad);

}  // namespace scl3300
}  // namespace atc
