// Table masse du palet → pression plenum de consigne.
//
// Format du fichier produit par le calcul aéraulique (calc/aero/results/setpoints.json) :
//   {"h_target_um": 120.0, "points": [{"mass_g": 2.0, "p_Pa": 70.0}, {"mass_g": 10.0, "p_Pa": 350.0}]}
// Le firmware ne lit pas de fichier : l'hôte envoie les points (TABLE ADD) ; le parseur JSON
// ci-dessous sert aux tests, à un éventuel chargement depuis SPIFFS et au contrôle croisé.
#pragma once
#include <stddef.h>

namespace atc {

struct SetpointPoint {
  float mass_g;
  float p_Pa;
};

class SetpointTable {
 public:
  static constexpr size_t kMaxPoints = 16;

  void clear();
  // Ajoute (ou remplace si même masse) un point ; la table reste triée par masse.
  bool add(float mass_g, float p_Pa);
  size_t size() const { return n_; }
  const SetpointPoint& at(size_t i) const { return pts_[i]; }
  float hTargetUm() const { return h_target_um_; }
  void setHTargetUm(float h) { h_target_um_ = h; }

  // Interpolation linéaire. Hors plage : saturation aux extrémités (clamped = true) ou
  // extrapolation linéaire si `extrapolate`. Retourne false si la table a < 1 point.
  bool interpolate(float mass_g, float* p_Pa, bool* clamped = nullptr, bool extrapolate = false) const;

  // Charge le format JSON ci-dessus (parseur minimal, clés inconnues ignorées).
  // Retourne le nombre de points chargés, ou −1 si le texte est invalide.
  int loadJson(const char* text);

 private:
  SetpointPoint pts_[kMaxPoints] = {};
  size_t n_ = 0;
  float h_target_um_ = 0.0f;
};

}  // namespace atc
