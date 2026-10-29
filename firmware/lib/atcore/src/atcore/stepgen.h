// Générateur de pas non bloquant à profil trapézoïdal, en arithmétique entière
// (appelable depuis une interruption de timer : pas de flottants, pas d'allocation).
//
// tick() est appelé à fréquence fixe `tick_hz` ; il retourne true quand une impulsion STEP
// doit être émise (sens = dir()). La vitesse est bornée à tick_hz/2 pour garantir qu'il n'y
// a jamais deux impulsions sur des ticks consécutifs (STEP haut un tick, bas le suivant).
// Au retournement, le tick qui change de sens n'émet pas d'impulsion (temps d'établissement DIR).
#pragma once
#include <stdint.h>

// Sur ESP32, les fonctions appelées par l'ISR sont placées en IRAM ; sur PC la macro est vide.
#if defined(ESP_PLATFORM)
#include "esp_attr.h"
#define ATC_IRAM IRAM_ATTR
#else
#define ATC_IRAM
#endif

namespace atc {

class StepGen {
 public:
  void configure(uint32_t tick_hz, uint32_t vmax_sps, uint32_t accel_sps2, uint32_t vmin_sps = 40);
  void setMaxSpeed(uint32_t vmax_sps);
  void setAccel(uint32_t accel_sps2);

  void moveTo(int32_t target) { target_ = target; }
  void moveBy(int32_t delta) { target_ = pos_ + delta; }
  // Arrêt avec rampe de décélération (la cible devient le point d'arrêt le plus proche).
  void stop();
  // Arrêt immédiat (sécurité) : vitesse nulle, cible = position.
  void emergencyStop();
  // Redéfinit la position courante (après prise d'origine). Ignoré si en mouvement.
  bool setPosition(int32_t p);

  bool tick();
  int8_t dir() const { return dir_; }
  int32_t position() const { return pos_; }
  int32_t target() const { return target_; }
  bool busy() const { return v_ != 0 || target_ != pos_; }
  uint32_t speedSps() const;                    // vitesse instantanée [pas/s]
  uint32_t tickHz() const { return tick_hz_; }
  // Durée estimée d'un déplacement de n pas [ms] (profil trapézoïdal ou triangulaire).
  uint32_t estimateMs(uint32_t n_steps) const;

 private:
  uint32_t stopDistSteps(uint64_t v_q32) const; // distance d'arrêt (arrondie au pas supérieur), 32 bits
  uint32_t tick_hz_ = 20000;
  uint32_t vmax_sps_ = 4000, accel_sps2_ = 20000, vmin_sps_ = 40;
  uint64_t vmax_q_ = 0, vmin_q_ = 0, dv_q_ = 1;   // pas/tick et pas/tick² en Q32
  uint64_t v_ = 0, phase_ = 0;
  int32_t pos_ = 0, target_ = 0;
  int8_t dir_ = 1;
};

}  // namespace atc
