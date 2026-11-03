// Tests : compensation thermique, apprentissage, fusion pondérée avec rejet, écart inter-capteurs,
// séquence de retournement à 180°.
#include <unity.h>

#include <math.h>
#include <stdint.h>

#include "atcore/tilt_array.h"

using namespace atc;

void setUp(void) {}
void tearDown(void) {}

// Générateur pseudo-aléatoire déterministe (LCG) + gaussienne par Box-Muller
static uint32_t g_seed = 12345;
static float urand() {
  g_seed = g_seed * 1664525u + 1013904223u;
  return (static_cast<float>(g_seed >> 8) + 0.5f) / 16777216.0f;
}
static float gauss(float sigma) {
  const float u1 = urand(), u2 = urand();
  return sigma * sqrtf(-2.0f * logf(u1)) * cosf(6.2831853f * u2);
}

// ---------------------------------------------------------------- thermique

void test_modele_thermique_polynome() {
  ThermalComp th;
  th.order = 2; th.t_ref_C = 20.0f;
  th.c1[0] = 30.0f; th.c1[1] = -10.0f; th.c2[0] = 1.5f; th.c2[1] = 0.0f;
  Vec2 o = th.offset(22.0f);                         // dT = 2
  TEST_ASSERT_FLOAT_WITHIN(1e-4, 30.0f * 2 + 1.5f * 4, o.x);
  TEST_ASSERT_FLOAT_WITHIN(1e-4, -20.0f, o.y);
  o = th.offset(20.0f);
  TEST_ASSERT_FLOAT_WITHIN(1e-6, 0.0f, o.x);
  th.order = 1;                                      // l'ordre 1 ignore c2
  TEST_ASSERT_FLOAT_WITHIN(1e-4, 60.0f, th.offset(22.0f).x);
  th.order = 0;                                      // inactif
  TEST_ASSERT_FLOAT_WITHIN(1e-6, 0.0f, th.offset(30.0f).x);
  const Vec2 c = compensateThermal(th, {100.0f, 50.0f}, 30.0f);
  TEST_ASSERT_FLOAT_WITHIN(1e-6, 100.0f, c.x);
}

void test_apprentissage_thermique_ordre2_recupere_coefficients() {
  g_seed = 7;
  ThermalLearner L;
  L.start();
  // Température qui monte de 20 à 26 °C ; dérive vraie : x : 45·d + 2·d², y : −20·d + 0,5·d² (+ bruit 2 µrad)
  for (int i = 0; i < 3000; ++i) {
    const float T = 20.0f + 6.0f * static_cast<float>(i) / 3000.0f;
    const float d = T - 20.0f;
    L.add(T, 120.0f + 45.0f * d + 2.0f * d * d + gauss(2.0f), -80.0f - 20.0f * d + 0.5f * d * d + gauss(2.0f));
  }
  ThermalComp th;
  float rms[2];
  TEST_ASSERT_TRUE(L.fit(2, 1200, 1.0f, &th, rms) == ThermalLearner::Status::Ok);
  TEST_ASSERT_EQUAL_UINT8(2, th.order);
  TEST_ASSERT_FLOAT_WITHIN(0.1f, 20.0f, th.t_ref_C);
  TEST_ASSERT_FLOAT_WITHIN(1.0f, 45.0f, th.c1[0]);
  TEST_ASSERT_FLOAT_WITHIN(0.3f, 2.0f, th.c2[0]);
  TEST_ASSERT_FLOAT_WITHIN(1.0f, -20.0f, th.c1[1]);
  TEST_ASSERT_FLOAT_WITHIN(0.3f, 0.5f, th.c2[1]);
  TEST_ASSERT_FLOAT_WITHIN(0.3f, 2.0f, rms[0]);      // le résidu vaut le bruit injecté
}

void test_apprentissage_thermique_ordre1_exact_sans_bruit() {
  ThermalLearner L;
  L.start();
  for (int i = 0; i < 100; ++i) {
    const float T = 18.0f + 0.05f * i;                // 5 K d'excursion
    L.add(T, 10.0f + 33.0f * (T - 18.0f), -4.0f - 12.0f * (T - 18.0f));
  }
  ThermalComp th;
  float rms[2];
  TEST_ASSERT_TRUE(L.fit(1, 50, 1.0f, &th, rms) == ThermalLearner::Status::Ok);
  TEST_ASSERT_FLOAT_WITHIN(1e-2, 33.0f, th.c1[0]);
  TEST_ASSERT_FLOAT_WITHIN(1e-2, -12.0f, th.c1[1]);
  TEST_ASSERT_FLOAT_WITHIN(1e-6, 0.0f, th.c2[0]);
  TEST_ASSERT_TRUE(rms[0] < 0.01f);
}

void test_apprentissage_refuse_donnees_insuffisantes() {
  ThermalLearner L;
  ThermalComp th;
  float rms[2];
  L.add(20.0f, 1.0f, 1.0f);                           // pas démarré : ignoré
  TEST_ASSERT_EQUAL_UINT32(0, L.count());
  L.start();
  for (int i = 0; i < 100; ++i) L.add(20.0f + 0.002f * i, 5.0f, 5.0f);   // 0,2 K seulement
  TEST_ASSERT_TRUE(L.fit(1, 50, 1.0f, &th, rms) == ThermalLearner::Status::SpanTooSmall);
  TEST_ASSERT_TRUE(L.fit(1, 500, 0.1f, &th, rms) == ThermalLearner::Status::TooFewSamples);
  L.start();                                          // température constante → matrice singulière / étendue nulle
  for (int i = 0; i < 100; ++i) L.add(21.0f, 5.0f, 5.0f);
  TEST_ASSERT_TRUE(L.fit(2, 50, 0.0f, &th, rms) == ThermalLearner::Status::Singular);
  L.add(NAN, 1.0f, 1.0f);                             // valeurs non finies ignorées
  TEST_ASSERT_EQUAL_UINT32(100, L.count());
}

void test_rebase_biais_sortie_continue() {
  SensorCal cal;
  cal.geo.bias_x_urad = 50.0f; cal.geo.bias_y_urad = -5.0f;
  cal.th.order = 1; cal.th.t_ref_C = 20.0f; cal.th.c1[0] = 10.0f;
  ThermalComp nth;
  nth.order = 2; nth.t_ref_C = 21.0f; nth.c1[0] = 40.0f; nth.c2[0] = 3.0f; nth.c1[1] = -2.0f;
  const float T = 23.0f, raw_x = 500.0f, raw_y = 77.0f;
  const Vec2 before = applyTiltCal(cal.geo, compensateThermal(cal.th, {raw_x, raw_y}, T));
  rebaseBias(&cal, nth, T);
  const Vec2 after = applyTiltCal(cal.geo, compensateThermal(cal.th, {raw_x, raw_y}, T));
  TEST_ASSERT_FLOAT_WITHIN(1e-3, before.x, after.x);
  TEST_ASSERT_FLOAT_WITHIN(1e-3, before.y, after.y);
  TEST_ASSERT_EQUAL_UINT8(2, cal.th.order);
}

void test_compensation_annule_derive_simulee() {
  // Un capteur dont le zéro dérive de 60 µrad/K : la sortie compensée reste constante à ±bruit
  ThermalComp th;
  th.order = 1; th.t_ref_C = 20.0f; th.c1[0] = 60.0f; th.c1[1] = 60.0f;
  for (float T = 18.0f; T <= 26.0f; T += 0.5f) {
    const Vec2 raw = {200.0f + 60.0f * (T - 20.0f), -100.0f + 60.0f * (T - 20.0f)};
    const Vec2 c = compensateThermal(th, raw, T);
    TEST_ASSERT_FLOAT_WITHIN(1e-3, 200.0f, c.x);
    TEST_ASSERT_FLOAT_WITHIN(1e-3, -100.0f, c.y);
  }
}

// ---------------------------------------------------------------- fusion

static FuseInput mk(float x, float y, float sigma = 1.0f, bool valid = true) {
  FuseInput f;
  f.tilt = {x, y};
  f.sigma_urad = sigma;
  f.valid = valid;
  return f;
}

void test_fusion_un_capteur() {
  const FuseInput in[1] = {mk(12.0f, -3.0f)};
  const FuseResult r = fuseTilt(in, 1, FuseConfig());
  TEST_ASSERT_TRUE(r.valid);
  TEST_ASSERT_EQUAL_INT(1, r.n_used);
  TEST_ASSERT_FLOAT_WITHIN(1e-5, 12.0f, r.tilt.x);
  TEST_ASSERT_FLOAT_WITHIN(1e-5, 1.0f, r.sigma_urad);
  TEST_ASSERT_FLOAT_WITHIN(1e-5, 0.0f, r.spread.x);
  const FuseInput none[1] = {mk(0, 0, 1.0f, false)};
  TEST_ASSERT_FALSE(fuseTilt(none, 1, FuseConfig()).valid);
}

void test_fusion_moyenne_ponderee_par_variance() {
  // σ = 1 et σ = 2 : poids 1 et 1/4 → (10·1 + 20·0,25)/1,25 = 12
  const FuseInput in[2] = {mk(10.0f, 0.0f, 1.0f), mk(20.0f, 0.0f, 2.0f)};
  FuseConfig cfg;
  cfg.reject_urad = 50.0f;
  const FuseResult r = fuseTilt(in, 2, cfg);
  TEST_ASSERT_TRUE(r.valid);
  TEST_ASSERT_FLOAT_WITHIN(1e-4, 12.0f, r.tilt.x);
  TEST_ASSERT_FLOAT_WITHIN(1e-4, 1.0f / sqrtf(1.25f), r.sigma_urad);   // 1/√Σw
  TEST_ASSERT_FLOAT_WITHIN(1e-4, 10.0f, r.spread.x);
}

void test_fusion_quatre_capteurs_egaux_reduit_bruit_de_moitie() {
  const FuseInput in[4] = {mk(5, 5), mk(5, 5), mk(5, 5), mk(5, 5)};
  const FuseResult r = fuseTilt(in, 4, FuseConfig());
  TEST_ASSERT_EQUAL_INT(4, r.n_used);
  TEST_ASSERT_FLOAT_WITHIN(1e-5, 0.5f, r.sigma_urad);      // σ/√4
}

void test_fusion_rejette_un_capteur_aberrant() {
  const FuseInput in[4] = {mk(10.0f, 4.0f), mk(11.0f, 5.0f), mk(500.0f, -300.0f), mk(9.0f, 3.0f)};
  const FuseResult r = fuseTilt(in, 4, FuseConfig());
  TEST_ASSERT_TRUE(r.valid);
  TEST_ASSERT_EQUAL_INT(3, r.n_used);
  TEST_ASSERT_EQUAL_UINT8(0x0B, r.used_mask);              // capteurs 0, 1, 3
  TEST_ASSERT_EQUAL_UINT8(0x04, r.rejected_mask);          // capteur 2
  TEST_ASSERT_FLOAT_WITHIN(1e-4, 10.0f, r.tilt.x);
  TEST_ASSERT_FLOAT_WITHIN(1e-4, 4.0f, r.tilt.y);
  TEST_ASSERT_FLOAT_WITHIN(1e-4, 2.0f, r.spread.x);
  // trois capteurs, un aberrant
  const FuseInput in3[3] = {mk(0, 0), mk(1, 1), mk(-200, 90)};
  const FuseResult r3 = fuseTilt(in3, 3, FuseConfig());
  TEST_ASSERT_TRUE(r3.valid);
  TEST_ASSERT_EQUAL_UINT8(0x04, r3.rejected_mask);
}

void test_fusion_ignore_capteurs_invalides() {
  const FuseInput in[4] = {mk(7, 7), mk(900, 900, 1.0f, false), mk(8, 6), mk(0, 0, 1.0f, false)};
  const FuseResult r = fuseTilt(in, 4, FuseConfig());
  TEST_ASSERT_TRUE(r.valid);
  TEST_ASSERT_EQUAL_UINT8(0x05, r.valid_mask);
  TEST_ASSERT_EQUAL_INT(2, r.n_used);
  TEST_ASSERT_FLOAT_WITHIN(1e-4, 7.5f, r.tilt.x);
  const FuseInput nan_in[2] = {mk(NAN, 0), mk(3, 3)};
  const FuseResult rn = fuseTilt(nan_in, 2, FuseConfig());
  TEST_ASSERT_EQUAL_INT(1, rn.n_used);                    // la valeur non finie est écartée
}

void test_fusion_deux_capteurs_en_desaccord_est_incoherente() {
  const FuseInput in[2] = {mk(0, 0), mk(200, 0)};
  const FuseResult r = fuseTilt(in, 2, FuseConfig());
  TEST_ASSERT_FALSE(r.valid);                             // impossible d'arbitrer : on ne fusionne pas
  TEST_ASSERT_TRUE(r.inconsistent);
  TEST_ASSERT_EQUAL_INT(2, r.n_valid);
}

void test_fusion_deux_groupes_incoherente() {
  const FuseInput in[4] = {mk(0, 0), mk(0, 0), mk(300, 0), mk(300, 0)};
  const FuseResult r = fuseTilt(in, 4, FuseConfig());
  TEST_ASSERT_FALSE(r.valid);
  TEST_ASSERT_TRUE(r.inconsistent);
}

void test_fusion_min_capteurs() {
  FuseConfig cfg;
  cfg.min_sensors = 2;
  const FuseInput in[2] = {mk(1, 1), mk(2, 2, 1.0f, false)};
  TEST_ASSERT_FALSE(fuseTilt(in, 2, cfg).valid);
  cfg.min_sensors = 1;
  TEST_ASSERT_TRUE(fuseTilt(in, 2, cfg).valid);
}

void test_fusion_statistique_bruit_gaussien() {
  // 4 capteurs σ = 8 µrad autour de 30 : l'écart-type de la fusion ≈ 4 µrad sur 400 tirages
  g_seed = 99;
  double s = 0, s2 = 0;
  const int N = 400;
  for (int k = 0; k < N; ++k) {
    FuseInput in[4];
    for (int i = 0; i < 4; ++i) in[i] = mk(30.0f + gauss(8.0f), 0.0f, 8.0f);
    const FuseResult r = fuseTilt(in, 4, FuseConfig());
    s += r.tilt.x; s2 += static_cast<double>(r.tilt.x) * r.tilt.x;
  }
  const double mean = s / N, sd = sqrt(s2 / N - mean * mean);
  TEST_ASSERT_FLOAT_WITHIN(1.0f, 30.0f, static_cast<float>(mean));
  TEST_ASSERT_FLOAT_WITHIN(0.8f, 4.0f, static_cast<float>(sd));
}

void test_sigma_courant_estime_le_bruit() {
  g_seed = 5;
  RunningSigma rs;
  for (int i = 0; i < 3000; ++i) rs.update({gauss(6.0f), gauss(6.0f)});
  TEST_ASSERT_FLOAT_WITHIN(1.2f, 6.0f, rs.sigma(0.3f));
  RunningSigma q;
  for (int i = 0; i < 50; ++i) q.update({1.0f, 1.0f});    // sortie constante → plancher
  TEST_ASSERT_FLOAT_WITHIN(1e-5, 0.3f, q.sigma(0.3f));
}

// ---------------------------------------------------------------- déformation

void test_champ_de_pente_cuvette() {
  // Surface z = κ/2 (x² + y²) : θx = κ x, θy = κ y ; coins à ±250 mm ; κ = 20 µrad/m
  const float xs[4] = {-250, 250, 250, -250}, ys[4] = {-250, -250, 250, 250};
  const float kappa = 20.0f;
  Vec2 th[4];
  for (int i = 0; i < 4; ++i) th[i] = {100.0f + kappa * xs[i] * 1e-3f, -40.0f + kappa * ys[i] * 1e-3f};  // + pente moyenne
  const SlopeField f = fitSlopeField(th, xs, ys, 0x0F, 4);
  TEST_ASSERT_TRUE(f.valid);
  TEST_ASSERT_FLOAT_WITHIN(1e-3, kappa, f.zxx);
  TEST_ASSERT_FLOAT_WITHIN(1e-3, kappa, f.zyy);
  TEST_ASSERT_FLOAT_WITHIN(1e-3, 0.0f, f.zxy);
  TEST_ASSERT_FLOAT_WITHIN(1e-3, 0.0f, f.curl);
}

void test_champ_de_pente_selle_gauchissement() {
  // z = γ·x·y : θx = γ y, θy = γ x → z_xy = γ (torsion), z_xx = z_yy = 0
  const float xs[4] = {-250, 250, 250, -250}, ys[4] = {-250, -250, 250, 250};
  const float gamma = 30.0f;
  Vec2 th[4];
  for (int i = 0; i < 4; ++i) th[i] = {gamma * ys[i] * 1e-3f, gamma * xs[i] * 1e-3f};
  const SlopeField f = fitSlopeField(th, xs, ys, 0x0F, 4);
  TEST_ASSERT_TRUE(f.valid);
  TEST_ASSERT_FLOAT_WITHIN(1e-3, gamma, f.zxy);
  TEST_ASSERT_FLOAT_WITHIN(1e-3, 0.0f, f.zxx);
  TEST_ASSERT_FLOAT_WITHIN(1e-3, 0.0f, f.curl);
}

void test_champ_de_pente_rotation_de_montage_donne_rotationnel() {
  // Un capteur monté tourné de 90° : θx et θy permutés → rotationnel non nul
  const float xs[4] = {-250, 250, 250, -250}, ys[4] = {-250, -250, 250, 250};
  Vec2 th[4];
  for (int i = 0; i < 4; ++i) th[i] = {10.0f * ys[i] * 1e-3f, -10.0f * xs[i] * 1e-3f};   // champ tournant (non conservatif)
  const SlopeField f = fitSlopeField(th, xs, ys, 0x0F, 4);
  TEST_ASSERT_TRUE(f.valid);
  TEST_ASSERT_TRUE(fabsf(f.curl) > 5.0f);
}

void test_champ_de_pente_exige_trois_capteurs_non_alignes() {
  const float xs[4] = {0, 100, 200, 300}, ys[4] = {0, 0, 0, 0};
  const Vec2 th[4] = {{1, 1}, {2, 2}, {3, 3}, {4, 4}};
  TEST_ASSERT_FALSE(fitSlopeField(th, xs, ys, 0x0F, 4).valid);     // alignés
  const float x3[4] = {-250, 250, 250, -250}, y3[4] = {-250, -250, 250, 250};
  TEST_ASSERT_FALSE(fitSlopeField(th, x3, y3, 0x03, 4).valid);     // 2 capteurs seulement
  TEST_ASSERT_TRUE(fitSlopeField(th, x3, y3, 0x07, 4).valid);      // 3 capteurs : exact
}

// ---------------------------------------------------------------- retournement

// Banc simulé : pente vraie s, biais b (dépend de T), embase à 0° ou 180° ; bruit gaussien.
struct FlipBench {
  Vec2 s{120.0f, -80.0f};
  Vec2 b{35.0f, -20.0f};
  Vec2 drift_per_s{0.0f, 0.0f};        // dérive de la pente vraie (thermique / mécanique)
  float noise = 3.0f;
  float T = 22.0f;
  // actionneur
  float angle = 0.0f;
  float cmd = 0.0f;
  uint32_t t_move_end = 0;
  uint32_t travel_ms = 1500;
  bool stuck = false;
  bool jam_on_rotate = false;         // se bloque dès la consigne de 180°
  bool index_ok = true;
  bool sensor_ok = true;
  uint32_t t_ms = 0;

  void command(float deg) {
    if (deg == cmd) return;
    cmd = deg;
    if (deg == 180.0f && jam_on_rotate) stuck = true;
    t_move_end = t_ms + travel_ms;
  }
  bool at_target() const { return !stuck && t_ms >= t_move_end && angle == cmd && index_ok; }
  void advance(uint32_t now) {
    t_ms = now;
    if (!stuck && t_ms >= t_move_end) angle = cmd;
  }
  Vec2 sample() {
    const float sign = (angle == 180.0f) ? -1.0f : 1.0f;
    const float dt = t_ms * 1e-3f;
    return {sign * (s.x + drift_per_s.x * dt) + b.x + gauss(noise), sign * (s.y + drift_per_s.y * dt) + b.y + gauss(noise)};
  }
};

// Exécute la séquence : boucle à 100 ms (tick) avec échantillon 10 Hz, comme le firmware.
static uint32_t run_flip(FlipSequencer& seq, FlipBench& bench, uint32_t max_ms = 400000, uint32_t abort_at = 0xFFFFFFFFu) {
  uint32_t t = 0;
  seq.start(t);
  while (t < max_ms && seq.active()) {
    t += 100;
    bench.advance(t);
    if (t >= abort_at) seq.abort();
    FlipInputs in;
    in.new_sample = true;
    in.sample_valid = bench.sensor_ok;
    in.sample = bench.sample();
    in.T_C = bench.T;
    in.at_target = bench.at_target();
    seq.update(t, in);
    bench.command(seq.targetDeg());                 // même ordre que App::flipTask : update puis consigne
  }
  return t;
}

static FlipConfig fast_cfg() {
  FlipConfig c;
  c.settle_ms = 4000; c.avg_ms = 10000; c.move_timeout_ms = 5000; c.drift_limit_urad = 3.0f; c.return_check = true;
  return c;
}

void test_retournement_biais_moyenne_des_deux_positions() {
  g_seed = 21;
  FlipBench bench;
  FlipSequencer seq;
  seq.configure(fast_cfg());
  run_flip(seq, bench);
  TEST_ASSERT_TRUE(seq.state() == FlipState::Done);
  const FlipResult& r = seq.result();
  TEST_ASSERT_TRUE(r.valid);
  TEST_ASSERT_TRUE(r.reliable);
  TEST_ASSERT_FLOAT_WITHIN(1.0f, 35.0f, r.bias.x);        // biais = (A + B)/2
  TEST_ASSERT_FLOAT_WITHIN(1.0f, -20.0f, r.bias.y);
  TEST_ASSERT_FLOAT_WITHIN(1.0f, 120.0f, r.slope.x);       // pente vraie = (A − B)/2
  TEST_ASSERT_FLOAT_WITHIN(1.0f, -80.0f, r.slope.y);
  TEST_ASSERT_TRUE(fabsf(r.drift.x) < 1.5f);
  TEST_ASSERT_TRUE(r.n_a >= 90 && r.n_b >= 90);
  TEST_ASSERT_FLOAT_WITHIN(1e-6, 0.0f, seq.targetDeg());         // embase ramenée à 0°
  TEST_ASSERT_TRUE(bench.angle == 0.0f);
}

void test_retournement_ordre_des_etats() {
  FlipBench bench;
  FlipSequencer seq;
  seq.configure(fast_cfg());
  seq.start(0);
  TEST_ASSERT_TRUE(seq.state() == FlipState::Settle0);
  TEST_ASSERT_FALSE(seq.start(0));                         // déjà en cours
  FlipState seen[16];
  int n = 0;
  FlipState last = seq.state();
  seen[n++] = last;
  uint32_t t = 0;
  while (seq.active() && t < 300000) {
    t += 100;
    bench.advance(t);
    FlipInputs in;
    in.new_sample = true; in.sample_valid = true; in.sample = bench.sample(); in.T_C = 22.0f; in.at_target = bench.at_target();
    seq.update(t, in);
    bench.command(seq.targetDeg());
    if (seq.state() != last && n < 16) { last = seq.state(); seen[n++] = last; }
  }
  const FlipState expect[] = {FlipState::Settle0, FlipState::Measure0, FlipState::Rotate180, FlipState::Settle180,
                              FlipState::Measure180, FlipState::ReturnZero, FlipState::SettleRet, FlipState::MeasureRet,
                              FlipState::Done};
  TEST_ASSERT_EQUAL_INT(9, n);
  for (int i = 0; i < 9; ++i) TEST_ASSERT_TRUE(seen[i] == expect[i]);
}

void test_retournement_biais_a_temperature_compensee() {
  // Le capteur dérive de 40 µrad/K ; le modèle thermique compense : la séquence reçoit le brut compensé
  g_seed = 3;
  ThermalComp th;
  th.order = 1; th.t_ref_C = 20.0f; th.c1[0] = 40.0f; th.c1[1] = 40.0f;
  FlipBench bench;
  bench.T = 25.0f;
  FlipSequencer seq;
  seq.configure(fast_cfg());
  uint32_t t = 0;
  seq.start(t);
  while (seq.active() && t < 300000) {
    t += 100;
    bench.advance(t);
    Vec2 raw = bench.sample();
    raw.x += 40.0f * (bench.T - 20.0f);                  // décalage thermique dans le repère capteur
    raw.y += 40.0f * (bench.T - 20.0f);
    FlipInputs in;
    in.new_sample = true; in.sample_valid = true;
    in.sample = compensateThermal(th, raw, bench.T);
    in.T_C = bench.T; in.at_target = bench.at_target();
    seq.update(t, in);
    bench.command(seq.targetDeg());
  }
  TEST_ASSERT_TRUE(seq.state() == FlipState::Done);
  TEST_ASSERT_FLOAT_WITHIN(1.0f, 35.0f, seq.result().bias.x);     // biais à t_ref, pas à 25 °C
  TEST_ASSERT_FLOAT_WITHIN(1.0f, -20.0f, seq.result().bias.y);
}

void test_retournement_derive_detectee() {
  g_seed = 8;
  FlipBench bench;
  bench.drift_per_s = {0.25f, 0.0f};                       // 0,25 µrad/s : > 3 µrad entre A et A2 (≥ 35 s)
  FlipSequencer seq;
  seq.configure(fast_cfg());
  run_flip(seq, bench);
  TEST_ASSERT_TRUE(seq.state() == FlipState::Done);
  TEST_ASSERT_TRUE(seq.result().valid);
  TEST_ASSERT_FALSE(seq.result().reliable);
  TEST_ASSERT_TRUE(fabsf(seq.result().drift.x) > 3.0f);
}

void test_retournement_sans_retour() {
  g_seed = 4;
  FlipBench bench;
  FlipSequencer seq;
  FlipConfig c = fast_cfg();
  c.return_check = false;
  seq.configure(c);
  run_flip(seq, bench);
  TEST_ASSERT_TRUE(seq.state() == FlipState::Done);
  TEST_ASSERT_TRUE(seq.result().reliable);
  TEST_ASSERT_FLOAT_WITHIN(1.5f, 35.0f, seq.result().bias.x);
}

void test_retournement_actionneur_bloque_timeout() {
  FlipBench bench;
  bench.stuck = true;                                      // l'embase ne tourne pas : at_target jamais vrai après la consigne
  FlipSequencer seq;
  seq.configure(fast_cfg());
  run_flip(seq, bench);
  TEST_ASSERT_TRUE(seq.state() == FlipState::Failed);
  TEST_ASSERT_TRUE(seq.error() == FlipError::ActuatorTimeout);
  TEST_ASSERT_FALSE(seq.result().valid);
  TEST_ASSERT_FLOAT_WITHIN(1e-6, 0.0f, seq.targetDeg());
}

void test_retournement_actionneur_bloque_au_retournement() {
  g_seed = 14;
  FlipBench bench;
  bench.jam_on_rotate = true;                               // la mesure à 0° est faite, puis l'embase se coince
  FlipSequencer seq;
  seq.configure(fast_cfg());
  run_flip(seq, bench);
  TEST_ASSERT_TRUE(seq.error() == FlipError::ActuatorTimeout);
  TEST_ASSERT_TRUE(seq.state() == FlipState::Failed);
  TEST_ASSERT_FALSE(seq.result().valid);
}

void test_retournement_capteur_invalide() {
  FlipBench bench;
  bench.sensor_ok = false;
  FlipSequencer seq;
  seq.configure(fast_cfg());
  run_flip(seq, bench);
  TEST_ASSERT_TRUE(seq.state() == FlipState::Failed);
  TEST_ASSERT_TRUE(seq.error() == FlipError::SensorInvalid);
}

void test_retournement_abandon_ramene_a_zero() {
  g_seed = 2;
  FlipBench bench;
  FlipSequencer seq;
  seq.configure(fast_cfg());
  // abandon en plein milieu de la mesure à 180° (≈ 4,5 + 10 + 1,5 + 4 + 5 s ≈ 25 s)
  run_flip(seq, bench, 400000, 25000);
  TEST_ASSERT_TRUE(seq.state() == FlipState::Failed);
  TEST_ASSERT_TRUE(seq.error() == FlipError::Aborted);
  TEST_ASSERT_FLOAT_WITHIN(1e-6, 0.0f, seq.targetDeg());
  TEST_ASSERT_FALSE(seq.result().valid);
  TEST_ASSERT_FALSE(seq.active());
  TEST_ASSERT_TRUE(seq.start(30000));                      // une nouvelle séquence peut être lancée
}

void test_retournement_defaut_externe() {
  FlipBench bench;
  FlipSequencer seq;
  seq.configure(fast_cfg());
  seq.start(0);
  FlipInputs in;
  in.fault = true;
  seq.update(100, in);
  TEST_ASSERT_TRUE(seq.error() == FlipError::Fault);
  TEST_ASSERT_TRUE(seq.state() == FlipState::Failed);
}

void test_retournement_embase_qui_bouge_pendant_la_mesure() {
  g_seed = 6;
  FlipBench bench;
  FlipSequencer seq;
  seq.configure(fast_cfg());
  uint32_t t = 0;
  seq.start(t);
  while (seq.active() && t < 300000) {
    t += 100;
    bench.advance(t);
    if (seq.state() == FlipState::Measure0 && t > 6000) bench.index_ok = false;   // contact d'index perdu en mesure
    FlipInputs in;
    in.new_sample = true; in.sample_valid = true; in.sample = bench.sample(); in.T_C = 22.0f; in.at_target = bench.at_target();
    seq.update(t, in);
    bench.command(seq.targetDeg());
  }
  TEST_ASSERT_TRUE(seq.error() == FlipError::Fault);
}

void test_noms_etats_et_erreurs() {
  TEST_ASSERT_EQUAL_STRING("measure180", flipStateName(FlipState::Measure180));
  TEST_ASSERT_EQUAL_STRING("failed", flipStateName(FlipState::Failed));
  TEST_ASSERT_EQUAL_STRING("actuator_timeout", flipErrorName(FlipError::ActuatorTimeout));
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_modele_thermique_polynome);
  RUN_TEST(test_apprentissage_thermique_ordre2_recupere_coefficients);
  RUN_TEST(test_apprentissage_thermique_ordre1_exact_sans_bruit);
  RUN_TEST(test_apprentissage_refuse_donnees_insuffisantes);
  RUN_TEST(test_rebase_biais_sortie_continue);
  RUN_TEST(test_compensation_annule_derive_simulee);
  RUN_TEST(test_fusion_un_capteur);
  RUN_TEST(test_fusion_moyenne_ponderee_par_variance);
  RUN_TEST(test_fusion_quatre_capteurs_egaux_reduit_bruit_de_moitie);
  RUN_TEST(test_fusion_rejette_un_capteur_aberrant);
  RUN_TEST(test_fusion_ignore_capteurs_invalides);
  RUN_TEST(test_fusion_deux_capteurs_en_desaccord_est_incoherente);
  RUN_TEST(test_fusion_deux_groupes_incoherente);
  RUN_TEST(test_fusion_min_capteurs);
  RUN_TEST(test_fusion_statistique_bruit_gaussien);
  RUN_TEST(test_sigma_courant_estime_le_bruit);
  RUN_TEST(test_champ_de_pente_cuvette);
  RUN_TEST(test_champ_de_pente_selle_gauchissement);
  RUN_TEST(test_champ_de_pente_rotation_de_montage_donne_rotationnel);
  RUN_TEST(test_champ_de_pente_exige_trois_capteurs_non_alignes);
  RUN_TEST(test_retournement_biais_moyenne_des_deux_positions);
  RUN_TEST(test_retournement_ordre_des_etats);
  RUN_TEST(test_retournement_biais_a_temperature_compensee);
  RUN_TEST(test_retournement_derive_detectee);
  RUN_TEST(test_retournement_sans_retour);
  RUN_TEST(test_retournement_actionneur_bloque_timeout);
  RUN_TEST(test_retournement_actionneur_bloque_au_retournement);
  RUN_TEST(test_retournement_capteur_invalide);
  RUN_TEST(test_retournement_abandon_ramene_a_zero);
  RUN_TEST(test_retournement_defaut_externe);
  RUN_TEST(test_retournement_embase_qui_bouge_pendant_la_mesure);
  RUN_TEST(test_noms_etats_et_erreurs);
  return UNITY_END();
}
