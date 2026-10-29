// Vérins de nivellement : 2 × NEMA17 + TMC2209 (UART pour la configuration, STEP/DIR pour le mouvement).
// Les impulsions sont générées par une interruption de timer (atc::StepGen, entier, trapézoïdal) :
// aucun pas n'est produit par loop(), donc aucune gigue due aux lectures de capteurs.
// ATTENTION : ne PAS écrire en flash (NVS, SAVE) pendant un mouvement (code d'ISR en flash).
#pragma once
#include <Arduino.h>

#include "atcore/leveling.h"
#include "atcore/stepgen.h"
#include "config.h"

class LevelActuators {
 public:
  enum class Home : uint8_t { Idle, Seek, Center, Done, Failed };

  bool begin();                           // GPIO, drivers TMC2209, timer ISR
  void service(uint32_t now_ms);          // machine à états de prise d'origine, surveillance
  void enableDrivers(bool on);

  void startHoming();
  Home homeState() const { return home_; }
  bool homed() const { return home_ == Home::Done; }

  // Déplacements relatifs ; retournent la durée estimée [ms], 0 si refusé (non référencé, inhibé...)
  uint32_t moveSlope(atc::Vec2 ds_urad);  // variation de pente voulue [µrad], découplée
  uint32_t jog(int idx, float um);        // un seul vérin, en µm de levée
  uint32_t goZero();                      // retour au centre de course
  void stop();                            // arrêt avec rampe
  void emergencyStop();                   // arrêt immédiat
  void setInhibit(bool inhibit);          // sécurité : arrête et refuse tout mouvement

  bool busy() const;
  int32_t position(int i) const { return gen_[i].position(); }
  int32_t target(int i) const { return gen_[i].target(); }
  atc::Vec2 slopeFromCenter() const;      // pente induite par rapport au centre [µrad]
  bool limitFault() const { return limit_fault_; }
  void clearLimitFault() { limit_fault_ = false; limit_seen_[0] = limit_seen_[1] = false; }
  bool limitActive(int i) const;
  bool driversOk() const { return drivers_ok_; }
  bool inhibited() const { return inhibit_; }
  const atc::Decoupling& decoupling() const { return dec_; }
  const atc::LevelGeometry& geometry() const { return geom_; }
  int32_t halfRangeSteps(int i) const { return half_[i]; }

  static void IRAM_ATTR onTimer();

 private:
  void IRAM_ATTR isrTick();
  atc::StepGen gen_[2];
  volatile bool pulse_[2] = {false, false};
  volatile bool limit_seen_[2] = {false, false};
  atc::LevelGeometry geom_;
  atc::Decoupling dec_;
  int32_t half_[2] = {0, 0};
  Home home_ = Home::Idle;
  bool found_[2] = {false, false};
  bool drivers_ok_ = false;
  bool limit_fault_ = false;
  bool inhibit_ = false;
  bool timer_started_ = false;
  uint32_t home_t0_ = 0;
};
