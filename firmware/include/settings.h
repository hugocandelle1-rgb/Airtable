// Réglages persistants (NVS) : étalonnages qui doivent survivre à une coupure.
// Écrire en flash pendant un mouvement des vérins est interdit (cf. level_actuators.h).
#pragma once
#include <Arduino.h>

#include "atcore/leveling.h"
#include "config.h"

struct Settings {
  atc::TiltCal tilt;                           // biais / rotation / signes de l'inclinomètre
  float p_offset[NUM_PLENUM_SENSORS] = {};     // zéros des capteurs de pression
  float nozzle_offset = 0.0f;
  float nozzle_cd = NOZZLE_CD_DEFAULT;
  float nozzle_diam_mm = NOZZLE_DIAM_MM_DEFAULT;
  float fan_p_full = FAN_P_FULL_PA;            // modèle de ventilateur (adapté en fonctionnement)
  float level_target_x = 0.0f, level_target_y = 0.0f;   // pente de consigne (CAL par palets)
  float level_deadband = LEVEL_DEADBAND_URAD;

  void load();
  bool save() const;
};
