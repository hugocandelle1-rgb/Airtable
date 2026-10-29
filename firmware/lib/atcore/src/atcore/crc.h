// Contrôles d'intégrité (CRC) des capteurs — logique pure, sans dépendance Arduino.
#pragma once
#include <stddef.h>
#include <stdint.h>

namespace atc {

// CRC-8 Sensirion (SDP8xx, SHT, ...) : polynôme 0x31, init 0xFF, pas de XOR final.
// Exemple de la fiche : crc8Sensirion({0xBE,0xEF}) == 0x92.
uint8_t crc8Sensirion(const uint8_t* data, size_t len);

// Vérifie un mot Sensirion de 3 octets : [MSB, LSB, CRC].
bool sensirionWordOk(const uint8_t* three_bytes);

// CRC-8 du SCL3300 (SPI) : polynôme 0x1D, init 0xFF, XOR final 0xFF, calculé sur
// les 24 bits de poids fort de la trame 32 bits (le CRC occupe l'octet de poids faible).
uint8_t crc8Scl3300(uint32_t frame);

}  // namespace atc
