// Nivellement : conversions mécaniques µrad ↔ µm ↔ pas, matrice de découplage
// vérins → pentes, étalonnage de l'inclinomètre (biais/rotation) et boucle à bande morte.
//
// Géométrie : la plaque repose sur un pivot fixe (origine) et deux vérins A et B en
// (xA,yA), (xB,yB) [mm] par rapport au pivot. Pour une pente (sx,sy) = (∂z/∂x, ∂z/∂y) :
//     zA = sx·xA + sy·yA ,  zB = sx·xB + sy·yB       →   z = M·s   (M en µm/µrad)
// Le découplage est l'inversion de M : pour obtenir une variation de pente voulue, on
// commande z = M·Δs. M singulière (vérins alignés avec le pivot) est refusée.
#pragma once
#include <stdint.h>

namespace atc {

struct Vec2 { float x = 0.0f, y = 0.0f; };
struct Mat2 {
  float a = 1, b = 0, c = 0, d = 1;   // [[a b],[c d]]
  Vec2 mul(const Vec2& v) const { return {a * v.x + b * v.y, c * v.x + d * v.y}; }
  float det() const { return a * d - b * c; }
};

// ---- mécanique d'un vérin (moteur pas à pas → vis → pente) ---------------------------------
struct StepperMech {
  float screw_pitch_mm = 0.5f;   // pas de la vis de réglage fin
  float gear_ratio = 1.0f;       // réduction (tours moteur / tour de vis)
  int full_steps_per_rev = 200;  // NEMA17 : 1,8°
  int microsteps = 16;
  // Déplacement linéaire par micro-pas [µm]
  float umPerMicrostep() const {
    return screw_pitch_mm * 1000.0f / (static_cast<float>(full_steps_per_rev) * microsteps * gear_ratio);
  }
};

// Un vérin attaquant un bras de levier de longueur L [mm] : pente = z/L.
float stepsToMicrons(int32_t steps, float um_per_step);
int32_t micronsToSteps(float um, float um_per_step);                 // arrondi au plus proche
float uradToMicrons(float urad, float lever_mm);                     // z = θ·L
float micronsToUrad(float um, float lever_mm);
int32_t uradToSteps(float urad, float lever_mm, float um_per_step);
float stepsToUrad(int32_t steps, float lever_mm, float um_per_step);

// ---- découplage deux axes ------------------------------------------------------------------
struct LevelGeometry {
  float x_mm[2] = {400.0f, 0.0f};   // positions des vérins A, B / pivot fixe
  float y_mm[2] = {0.0f, 400.0f};
  float um_per_step[2] = {0.0156f, 0.0156f};
};

struct Decoupling {
  Mat2 M;      // µm de levée = M · µrad de pente
  Mat2 Minv;   // µrad de pente = Minv · µm de levée
  bool valid = false;
};
// Construit M et son inverse ; valid = false si |det| trop faible (géométrie dégénérée).
Decoupling buildDecoupling(const LevelGeometry& g);
// Variation de pente voulue [µrad] → pas à commander (relatifs) sur chaque vérin.
void slopeToSteps(const Decoupling& d, const LevelGeometry& g, Vec2 ds_urad, int32_t steps[2]);
// Positions des vérins [pas, relatives à l'origine] → pente induite [µrad].
Vec2 stepsToSlope(const Decoupling& d, const LevelGeometry& g, const int32_t steps[2]);

// ---- étalonnage de l'inclinomètre ----------------------------------------------------------
struct TiltCal {
  float bias_x_urad = 0.0f;
  float bias_y_urad = 0.0f;
  float mount_rot_deg = 0.0f;   // rotation capteur → repère plaque
  float sign_x = 1.0f;          // ±1 : inversions d'axes de montage
  float sign_y = 1.0f;
};
// pente plaque = Rot(mount_rot)·diag(sign)·(brut − biais)
Vec2 applyTiltCal(const TiltCal& c, Vec2 raw_urad);

// ---- boucle de nivellement à bande morte -------------------------------------------------
struct LevelConfig {
  float deadband_urad = 3.0f;     // pas de mouvement si |erreur| < bande morte (par axe)
  int confirm_n = 5;              // échantillons consécutifs hors bande avant de bouger
  float gain = 0.8f;              // fraction de l'erreur corrigée à chaque mouvement
  float max_move_urad = 200.0f;   // plafond par mouvement et par axe
  uint32_t settle_ms = 4000;      // silence après un mouvement (vibrations, thermique)
};

class LevelController {
 public:
  void configure(const LevelConfig& c) { cfg_ = c; reset(); }
  const LevelConfig& config() const { return cfg_; }
  void setTarget(float tx_urad, float ty_urad) { target_ = {tx_urad, ty_urad}; reset(); }
  Vec2 target() const { return target_; }
  void reset() { count_ = 0; }

  // Alimente avec la pente filtrée (repère plaque). Retourne true si un mouvement relatif
  // `ds` [µrad] doit être exécuté ; le contrôleur est alors muet pendant settle_ms
  // + `move_ms` (durée estimée du mouvement, passée à commit()).
  bool update(uint32_t now_ms, Vec2 tilt, bool valid, Vec2* ds);
  void commit(uint32_t now_ms, uint32_t move_ms) { hold_until_ms_ = now_ms + move_ms + cfg_.settle_ms; hold_ = true; count_ = 0; }
  int pending() const { return count_; }

 private:
  LevelConfig cfg_;
  Vec2 target_;
  int count_ = 0;
  bool hold_ = false;
  uint32_t hold_until_ms_ = 0;
};

// Limites logicielles : ramène une cible (pas) dans [lo, hi] ; retourne true si saturée.
bool clampSteps(int32_t* target, int32_t lo, int32_t hi);

}  // namespace atc
