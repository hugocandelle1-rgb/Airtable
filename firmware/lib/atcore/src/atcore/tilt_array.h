// Réseau de N = 1…4 accéléromètres d'inclinaison (ADXL355) : compensation thermique du zéro,
// estimation du bruit, fusion pondérée avec rejet d'un capteur aberrant, écart inter-capteurs
// (indicateur de déformation) et séquence de retournement à 180° d'une embase.
// Logique pure (aucun accès matériel) : testée sur PC dans test/test_tilt_array.
//
// Chaîne de traitement d'un capteur i (µrad ; X, Y = axes du capteur) :
//     brut_i ──(− décalage thermique(T_i))──► brut compensé ──(− biais, rotation, signes)──► pente plaque
// Le biais est défini à la température de référence t_ref du modèle thermique.
#pragma once
#include <stdint.h>

#include "atcore/leveling.h"

namespace atc {

constexpr int kMaxTilt = 4;

// ---- compensation thermique du zéro --------------------------------------------------------
// décalage(T) = c1·(T − t_ref) + c2·(T − t_ref)²  par axe ; order = 0 : modèle inactif.
struct ThermalComp {
  float t_ref_C = 20.0f;
  float c1[2] = {0.0f, 0.0f};   // µrad/K
  float c2[2] = {0.0f, 0.0f};   // µrad/K²
  uint8_t order = 0;            // 0 (inactif), 1 ou 2
  bool active() const { return order > 0; }
  Vec2 offset(float T_C) const;
};

// Brut → brut compensé (retire le décalage thermique ; sans effet si le modèle est inactif).
Vec2 compensateThermal(const ThermalComp& th, Vec2 raw_urad, float T_C);

struct SensorCal {
  TiltCal geo;        // biais (à t_ref), rotation de montage, signes
  ThermalComp th;
};

// Après un nouvel apprentissage, ajuste le biais pour que la sortie corrigée soit inchangée à la
// température courante : biais' = biais + décalage_ancien(T) − décalage_nouveau(T).
void rebaseBias(SensorCal* cal, const ThermalComp& new_th, float T_now_C);

// ---- apprentissage du modèle thermique (moindres carrés polynomiaux) --------------------------
class ThermalLearner {
 public:
  enum class Status { Ok, TooFewSamples, SpanTooSmall, Singular };
  void start() { *this = ThermalLearner(); active_ = true; }
  bool active() const { return active_; }
  void stop() { active_ = false; }
  // Un échantillon : température de l'embase [°C], brut non compensé [µrad].
  void add(float T_C, float x_urad, float y_urad);
  uint32_t count() const { return n_; }
  float spanK() const { return n_ ? t_max_ - t_min_ : 0.0f; }
  // Ajuste le polynôme d'ordre 1 ou 2 ; écrit `out` (t_ref = première température vue).
  Status fit(int order, uint32_t min_samples, float min_span_K, ThermalComp* out, float rms_urad[2]) const;

 private:
  bool active_ = false;
  uint32_t n_ = 0;
  double t0_ = 0, y0_[2] = {0, 0};          // origines (conditionnement)
  double s_[5] = {0, 0, 0, 0, 0};            // Σ d^k, k = 0…4
  double sy_[2][3] = {{0, 0, 0}, {0, 0, 0}}; // Σ d^k·y, k = 0…2
  double syy_[2] = {0, 0};                   // Σ y²
  float t_min_ = 0, t_max_ = 0;
};

// ---- bruit estimé d'un capteur (écart-type glissant de sa sortie 10 Hz) -----------------------
class RunningSigma {
 public:
  void update(Vec2 v, float alpha = 0.02f);
  float sigma(float floor_urad) const;
  void reset() { init_ = false; var_ = 0.0f; }

 private:
  bool init_ = false;
  float mx_ = 0, my_ = 0, var_ = 0;
};

// ---- fusion -----------------------------------------------------------------------------------
struct FuseConfig {
  float reject_urad = 40.0f;      // écart maximal admis à la médiane (≥ 3 capteurs) ou entre capteurs (2)
  float sigma_floor_urad = 0.3f;  // plancher de σ (évite un poids infini)
  int min_sensors = 1;            // nombre minimal de capteurs retenus pour déclarer la fusion valide
};

struct FuseInput {
  Vec2 tilt;            // pente plaque du capteur [µrad]
  float sigma_urad = 1.0f;
  bool valid = false;
};

struct FuseResult {
  bool valid = false;
  bool inconsistent = false;      // désaccord impossible à arbitrer (2 capteurs, ou < 2 retenus sur ≥ 3)
  Vec2 tilt;                      // moyenne pondérée par 1/σ²
  float sigma_urad = 0.0f;        // 1/√Σw
  uint8_t valid_mask = 0, used_mask = 0, rejected_mask = 0;
  int n_valid = 0, n_used = 0;
  Vec2 spread;                    // max − min des capteurs retenus, par axe [µrad]
  float dev_max_urad = 0.0f;      // plus grand écart d'un capteur retenu à la moyenne (max des axes)
};

FuseResult fuseTilt(const FuseInput* in, int n, const FuseConfig& cfg);

// Champ de pente ajusté sur les positions des capteurs retenus (≥ 3, non alignés) :
//   θx = a0 + a1·x + a2·y ,  θy = b0 + b1·x + b2·y   →   z_xx = a1 , z_xy = (a2 + b1)/2 , z_yy = b2.
// Unités µrad/m (≡ µm/m²). `curl` = (a2 − b1)/2 : nul pour une surface réelle, donc mesure d'erreur
// (rotation de montage, capteur défaillant).
struct SlopeField {
  bool valid = false;
  float zxx = 0, zxy = 0, zyy = 0, curl = 0;
};
SlopeField fitSlopeField(const Vec2* tilt, const float* x_mm, const float* y_mm, uint8_t mask, int n);

// ---- séquence de retournement à 180° ----------------------------------------------------------
struct FlipConfig {
  uint32_t settle_ms = 8000;         // attente après chaque rotation (mécanique, thermique, filtre)
  uint32_t avg_ms = 20000;           // durée de mesure par position
  uint32_t move_timeout_ms = 8000;   // délai pour atteindre la position demandée
  uint32_t invalid_timeout_ms = 3000;// capteur sans échantillon valide tolérée
  bool return_check = true;          // revient à 0° et mesure A2 (contrôle de dérive)
  float drift_limit_urad = 3.0f;     // |A2 − A| au-delà : résultat non fiable
  uint16_t min_samples = 20;
};

enum class FlipState : uint8_t {
  Idle, Settle0, Measure0, Rotate180, Settle180, Measure180, ReturnZero, SettleRet, MeasureRet,
  Done, Failed
};
enum class FlipError : uint8_t { None, Aborted, ActuatorTimeout, SensorInvalid, TooFewSamples, Fault };

const char* flipStateName(FlipState s);
const char* flipErrorName(FlipError e);

struct FlipResult {
  bool valid = false;               // la séquence est allée au bout
  bool reliable = false;            // dérive A/A2 sous la limite
  Vec2 bias;                        // biais du capteur (à t_ref s'il est compensé thermiquement)
  Vec2 slope;                       // pente vraie de la surface au site, repère de la position A
  Vec2 drift;                       // A2 − A (0 si pas de retour)
  Vec2 a, b;                        // moyennes en 0° et 180°
  float t_mean_C = 0.0f;
  uint16_t n_a = 0, n_b = 0;
};

struct FlipInputs {
  bool new_sample = false;          // un nouvel échantillon 10 Hz du capteur retournable est disponible
  bool sample_valid = false;
  Vec2 sample;                      // brut compensé thermiquement, repère capteur [µrad]
  float T_C = 0.0f;
  bool at_target = false;           // l'actionneur a atteint la position demandée (targetDeg())
  bool fault = false;               // défaut actionneur / sécurité : abandon
};

class FlipSequencer {
 public:
  void configure(const FlipConfig& c) { cfg_ = c; }
  const FlipConfig& config() const { return cfg_; }
  bool start(uint32_t now_ms);                     // false si déjà en cours
  void abort();                                    // abandon : retour à 0° puis Failed(Aborted)
  void update(uint32_t now_ms, const FlipInputs& in);
  bool active() const { return st_ != FlipState::Idle && st_ != FlipState::Done && st_ != FlipState::Failed; }
  FlipState state() const { return st_; }
  FlipError error() const { return err_; }
  float targetDeg() const { return target_deg_; }  // consigne d'angle de l'actionneur : 0 ou 180
  const FlipResult& result() const { return res_; }
  // Vrai tant que la consigne d'angle n'est pas 0° (le capteur est retourné ou en route).
  bool sensorRotated() const { return target_deg_ != 0.0f; }

 private:
  struct Acc {
    double sx = 0, sy = 0, st = 0;
    uint32_t n = 0;
    void reset() { *this = Acc(); }
    void add(Vec2 v, float T) { sx += v.x; sy += v.y; st += T; ++n; }
    Vec2 mean() const { return n ? Vec2{static_cast<float>(sx / n), static_cast<float>(sy / n)} : Vec2{}; }
    float meanT() const { return n ? static_cast<float>(st / n) : 0.0f; }
  };
  void fail(FlipError e);
  void enter(FlipState s, uint32_t now_ms);
  void finish(uint32_t now_ms);
  FlipConfig cfg_;
  FlipState st_ = FlipState::Idle;
  FlipError err_ = FlipError::None;
  FlipResult res_;
  Acc a_, b_, a2_;
  float target_deg_ = 0.0f;
  uint32_t t_enter_ = 0, last_valid_ms_ = 0;
};

}  // namespace atc
