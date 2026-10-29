// Tests : conversions µrad ↔ µm ↔ pas, découplage des vérins, étalonnage inclinomètre, boucle à bande morte.
#include <unity.h>

#include <math.h>
#include <initializer_list>

#include "atcore/leveling.h"

using namespace atc;

void setUp(void) {}
void tearDown(void) {}

void test_um_par_micropas() {
  StepperMech m;
  m.screw_pitch_mm = 0.5f; m.gear_ratio = 10.0f; m.full_steps_per_rev = 200; m.microsteps = 16;
  // 0,5 mm / (200·16·10) = 15,625 nm
  TEST_ASSERT_FLOAT_WITHIN(1e-6, 0.015625, m.umPerMicrostep());
  m.gear_ratio = 1.0f; m.microsteps = 1;
  TEST_ASSERT_FLOAT_WITHIN(1e-6, 2.5, m.umPerMicrostep());     // 0,5 mm / 200
}

void test_conversions_urad_pas() {
  const float L = 400.0f, ups = 0.015625f;
  // 2 µrad × 400 mm = 0,8 µm → 51,2 pas
  TEST_ASSERT_FLOAT_WITHIN(1e-6, 0.8, uradToMicrons(2.0f, L));
  TEST_ASSERT_EQUAL_INT32(51, uradToSteps(2.0f, L, ups));
  TEST_ASSERT_EQUAL_INT32(-51, uradToSteps(-2.0f, L, ups));
  // aller-retour à ±1 pas près
  for (float u : {-4300.0f, -17.3f, 0.0f, 1.0f, 250.0f, 4363.0f}) {
    const int32_t n = uradToSteps(u, L, ups);
    const float back = stepsToUrad(n, L, ups);
    TEST_ASSERT_FLOAT_WITHIN(micronsToUrad(ups, L) * 0.51f, u, back);
  }
  TEST_ASSERT_FLOAT_WITHIN(1e-4, 2.0, micronsToUrad(0.8f, L));
  // course ±0,25° (4363 µrad) sur 400 mm = 1,745 mm
  TEST_ASSERT_FLOAT_WITHIN(0.5, 1745.0, uradToMicrons(4363.0f, L));
  TEST_ASSERT_EQUAL_INT32(0, micronsToSteps(1.0f, 0.0f));   // facteur invalide → 0
}

void test_decouplage_geometrie_orthogonale() {
  LevelGeometry g;   // vérin A en (400,0), B en (0,400)
  const Decoupling d = buildDecoupling(g);
  TEST_ASSERT_TRUE(d.valid);
  // Δsx = +10 µrad → seul le vérin A monte : 400 mm·10 µrad = 4 µm → 256 pas
  int32_t st[2];
  slopeToSteps(d, g, {10.0f, 0.0f}, st);
  TEST_ASSERT_EQUAL_INT32(256, st[0]);
  TEST_ASSERT_EQUAL_INT32(0, st[1]);
  slopeToSteps(d, g, {0.0f, -10.0f}, st);
  TEST_ASSERT_EQUAL_INT32(0, st[0]);
  TEST_ASSERT_EQUAL_INT32(-256, st[1]);
}

void test_decouplage_geometrie_oblique_aller_retour() {
  // Vérins non orthogonaux : le découplage doit tout de même restituer les pentes demandées.
  LevelGeometry g;
  g.x_mm[0] = 380.0f; g.y_mm[0] = 60.0f;
  g.x_mm[1] = 110.0f; g.y_mm[1] = 350.0f;
  g.um_per_step[0] = 0.01f; g.um_per_step[1] = 0.01f;
  const Decoupling d = buildDecoupling(g);
  TEST_ASSERT_TRUE(d.valid);
  const Vec2 want = {37.0f, -52.0f};
  int32_t st[2];
  slopeToSteps(d, g, want, st);
  const Vec2 got = stepsToSlope(d, g, st);
  TEST_ASSERT_FLOAT_WITHIN(0.2, want.x, got.x);   // erreur de quantification < 0,2 µrad
  TEST_ASSERT_FLOAT_WITHIN(0.2, want.y, got.y);
  // Découplage : une pente en X seule ne doit rien produire sur Y
  slopeToSteps(d, g, {100.0f, 0.0f}, st);
  const Vec2 g2 = stepsToSlope(d, g, st);
  TEST_ASSERT_FLOAT_WITHIN(0.2, 100.0, g2.x);
  TEST_ASSERT_FLOAT_WITHIN(0.2, 0.0, g2.y);
}

void test_decouplage_geometrie_degeneree() {
  LevelGeometry g;   // vérins alignés avec le pivot : impossible de commander 2 axes
  g.x_mm[0] = 200; g.y_mm[0] = 100; g.x_mm[1] = 400; g.y_mm[1] = 200;
  const Decoupling d = buildDecoupling(g);
  TEST_ASSERT_FALSE(d.valid);
  int32_t st[2] = {7, 7};
  slopeToSteps(d, g, {10.0f, 10.0f}, st);
  TEST_ASSERT_EQUAL_INT32(0, st[0]);
  TEST_ASSERT_EQUAL_INT32(0, st[1]);
}

void test_etalonnage_inclinometre() {
  TiltCal c;
  c.bias_x_urad = 30.0f; c.bias_y_urad = -10.0f;
  Vec2 v = applyTiltCal(c, {130.0f, 40.0f});
  TEST_ASSERT_FLOAT_WITHIN(1e-4, 100.0, v.x);
  TEST_ASSERT_FLOAT_WITHIN(1e-4, 50.0, v.y);
  c.mount_rot_deg = 90.0f;                      // capteur tourné de 90° : (x,y) → (−y, x)
  v = applyTiltCal(c, {130.0f, 40.0f});
  TEST_ASSERT_FLOAT_WITHIN(1e-3, -50.0, v.x);
  TEST_ASSERT_FLOAT_WITHIN(1e-3, 100.0, v.y);
  c.mount_rot_deg = 0.0f; c.sign_x = -1.0f;
  v = applyTiltCal(c, {130.0f, 40.0f});
  TEST_ASSERT_FLOAT_WITHIN(1e-4, -100.0, v.x);
}

void test_niveau_bande_morte_et_confirmation() {
  LevelController lc;
  LevelConfig cfg; cfg.deadband_urad = 3.0f; cfg.confirm_n = 5; cfg.gain = 0.8f; cfg.max_move_urad = 200.0f; cfg.settle_ms = 4000;
  lc.configure(cfg);
  lc.setTarget(0.0f, 0.0f);
  Vec2 ds;
  uint32_t t = 0;
  // Dans la bande morte : aucun mouvement, même sur la durée
  for (int i = 0; i < 100; ++i) { t += 1000; TEST_ASSERT_FALSE(lc.update(t, {2.5f, -2.9f}, true, &ds)); }
  // Écart de 20 µrad : mouvement seulement au 5e échantillon consécutif
  for (int i = 0; i < 4; ++i) { t += 1000; TEST_ASSERT_FALSE(lc.update(t, {20.0f, 0.5f}, true, &ds)); }
  t += 1000;
  TEST_ASSERT_TRUE(lc.update(t, {20.0f, 0.5f}, true, &ds));
  TEST_ASSERT_FLOAT_WITHIN(1e-4, -16.0, ds.x);   // −0,8·20
  TEST_ASSERT_FLOAT_WITHIN(1e-4, 0.0, ds.y);     // axe Y dans la bande morte : pas touché
  // Silence après le mouvement (settle + durée du mouvement)
  lc.commit(t, 1000);
  for (int i = 0; i < 4; ++i) { t += 1000; TEST_ASSERT_FALSE(lc.update(t, {20.0f, 0.0f}, true, &ds)); }
  t += 1100;   // 5100 ms après commit : fin du silence, compteur repart de zéro
  for (int i = 0; i < 4; ++i) { TEST_ASSERT_FALSE(lc.update(t, {20.0f, 0.0f}, true, &ds)); t += 1000; }
  TEST_ASSERT_TRUE(lc.update(t, {20.0f, 0.0f}, true, &ds));
}

void test_niveau_un_echantillon_isole_ne_declenche_pas() {
  LevelController lc;
  LevelConfig cfg; cfg.confirm_n = 3;
  lc.configure(cfg);
  Vec2 ds;
  uint32_t t = 0;
  for (int i = 0; i < 50; ++i) {
    t += 1000;
    const Vec2 v = (i % 2) ? Vec2{50.0f, 0.0f} : Vec2{0.0f, 0.0f};   // pic une fois sur deux
    TEST_ASSERT_FALSE(lc.update(t, v, true, &ds));
  }
}

void test_niveau_plafond_cible_invalide() {
  LevelController lc;
  LevelConfig cfg; cfg.confirm_n = 1; cfg.max_move_urad = 100.0f; cfg.gain = 1.0f;
  lc.configure(cfg);
  lc.setTarget(10.0f, -20.0f);
  Vec2 ds;
  TEST_ASSERT_FALSE(lc.update(1000, {0.0f, 0.0f}, false, &ds));          // mesure invalide : rien
  TEST_ASSERT_TRUE(lc.update(2000, {-1000.0f, 500.0f}, true, &ds));
  TEST_ASSERT_FLOAT_WITHIN(1e-4, 100.0, ds.x);                            // plafonné
  TEST_ASSERT_FLOAT_WITHIN(1e-4, -100.0, ds.y);
}

void test_niveau_boucle_fermee_convergence() {
  // Simulation : pente initiale (+120, −80) µrad ; chaque mouvement applique ds avec 5 % d'erreur d'échelle.
  LevelController lc;
  LevelConfig cfg; cfg.confirm_n = 3; cfg.settle_ms = 2000;
  lc.configure(cfg);
  Vec2 tilt = {120.0f, -80.0f}, ds;
  uint32_t t = 0;
  int moves = 0;
  for (int i = 0; i < 400; ++i) {
    t += 1000;
    if (lc.update(t, tilt, true, &ds)) {
      tilt.x += 0.95f * ds.x; tilt.y += 0.95f * ds.y;
      lc.commit(t, 500);
      ++moves;
    }
  }
  TEST_ASSERT_TRUE(fabsf(tilt.x) <= 3.0f && fabsf(tilt.y) <= 3.0f);
  TEST_ASSERT_TRUE(moves <= 10);
}

void test_limites_logicielles() {
  int32_t t = 50000;
  TEST_ASSERT_TRUE(clampSteps(&t, -40000, 40000));
  TEST_ASSERT_EQUAL_INT32(40000, t);
  t = -50000;
  TEST_ASSERT_TRUE(clampSteps(&t, -40000, 40000));
  TEST_ASSERT_EQUAL_INT32(-40000, t);
  t = 100;
  TEST_ASSERT_FALSE(clampSteps(&t, -40000, 40000));
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_um_par_micropas);
  RUN_TEST(test_conversions_urad_pas);
  RUN_TEST(test_decouplage_geometrie_orthogonale);
  RUN_TEST(test_decouplage_geometrie_oblique_aller_retour);
  RUN_TEST(test_decouplage_geometrie_degeneree);
  RUN_TEST(test_etalonnage_inclinometre);
  RUN_TEST(test_niveau_bande_morte_et_confirmation);
  RUN_TEST(test_niveau_un_echantillon_isole_ne_declenche_pas);
  RUN_TEST(test_niveau_plafond_cible_invalide);
  RUN_TEST(test_niveau_boucle_fermee_convergence);
  RUN_TEST(test_limites_logicielles);
  return UNITY_END();
}
