// Interface commune des inclinomètres (SCL3300, ADXL355) + accumulateur de moyennage.
//
// Convention de signe (figée pour tout le projet) : tilt_x = ∂z/∂x de la plaque [µrad],
// positif quand l'axe +X du capteur monte ; idem pour Y. Un palet posé dérive donc vers −X
// quand tilt_x > 0 (θ_dérive = −tilt, cf. host/drift_calibration.py).
#pragma once
#include <stdint.h>

namespace atc {

struct TiltSample {
  float x_urad = 0.0f;
  float y_urad = 0.0f;
  float temp_C = 0.0f;
  uint16_t n_avg = 0;      // nombre d'échantillons bruts moyennés
  bool valid = false;
};

// Interface abstraite implémentée par les drivers matériels.
class Inclinometer {
 public:
  virtual ~Inclinometer() = default;
  virtual bool begin() = 0;                       // séquence de démarrage
  virtual void poll(uint32_t now_us) = 0;         // acquisition brute, non bloquante
  virtual bool read(TiltSample* out) = 0;         // moyenne depuis le dernier read()
  virtual const char* name() const = 0;
  virtual uint32_t errorCount() const = 0;        // erreurs CRC / statut cumulées
  virtual bool healthy() const = 0;
};

// Moyenne d'accélérations (g) puis conversion en angles : la moyenne se fait AVANT
// l'arctangente et en double précision pour exploiter le dithering du bruit (sub-LSB).
class AccAccumulator {
 public:
  void reset() { n_ = 0; sx_ = sy_ = sz_ = st_ = 0.0; }
  void add(float ax_g, float ay_g, float az_g, float temp_C) {
    sx_ += ax_g; sy_ += ay_g; sz_ += az_g; st_ += temp_C; ++n_;
  }
  uint16_t count() const { return static_cast<uint16_t>(n_ > 65535 ? 65535 : n_); }
  // Calcule l'échantillon moyen puis remet à zéro. Retourne false si aucun échantillon.
  bool flush(TiltSample* out);

 private:
  double sx_ = 0, sy_ = 0, sz_ = 0, st_ = 0;
  uint32_t n_ = 0;
};

}  // namespace atc
