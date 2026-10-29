// Tests : générateur de pas (profil trapézoïdal entier) et supervision de sécurité.
#include <unity.h>

#include <math.h>
#include <initializer_list>
#include <stdlib.h>

#include "atcore/safety.h"
#include "atcore/stepgen.h"

using namespace atc;

void setUp(void) {}
void tearDown(void) {}

struct Run {
  uint32_t ticks = 0;
  uint32_t steps = 0;
  uint32_t max_speed = 0;
  uint32_t min_gap_ticks = 1u << 30;   // plus petit écart entre deux impulsions
  int reversals = 0;
};

// Exécute jusqu'à l'arrêt complet (ou max_ticks) en vérifiant les invariants.
static Run runUntilIdle(StepGen& g, uint32_t max_ticks = 4000000) {
  Run r;
  uint32_t last = 0;
  int8_t last_dir = 0;
  while (g.busy() && r.ticks < max_ticks) {
    const bool s = g.tick();
    ++r.ticks;
    if (s) {
      ++r.steps;
      if (last && r.ticks - last < r.min_gap_ticks) r.min_gap_ticks = r.ticks - last;
      last = r.ticks;
      if (last_dir && g.dir() != last_dir) ++r.reversals;
      last_dir = g.dir();
    }
    if (g.speedSps() > r.max_speed) r.max_speed = g.speedSps();
  }
  return r;
}

void test_stepgen_atteint_exactement_la_cible() {
  StepGen g;
  g.configure(20000, 4000, 20000);
  for (int32_t target : {1, 2, 3, 10, 57, 500, 12345, 80000}) {
    g.setPosition(0);
    g.moveTo(target);
    const Run r = runUntilIdle(g);
    TEST_ASSERT_EQUAL_INT32(target, g.position());
    TEST_ASSERT_EQUAL_UINT32(static_cast<uint32_t>(target), r.steps);
    TEST_ASSERT_FALSE(g.busy());
    TEST_ASSERT_EQUAL_INT(0, r.reversals);
  }
}

void test_stepgen_direction_negative() {
  StepGen g;
  g.configure(20000, 4000, 20000);
  g.setPosition(1000);
  g.moveTo(-250);
  const Run r = runUntilIdle(g);
  TEST_ASSERT_EQUAL_INT32(-250, g.position());
  TEST_ASSERT_EQUAL_UINT32(1250, r.steps);
}

void test_stepgen_profil_trapezoidal() {
  StepGen g;
  g.configure(20000, 4000, 20000);          // vmax 4000 pas/s, a = 20000 pas/s²
  g.setPosition(0);
  g.moveTo(40000);                          // trapèze net : 10 s environ
  const Run r = runUntilIdle(g);
  TEST_ASSERT_EQUAL_UINT32(40000, r.steps);
  TEST_ASSERT_TRUE(r.max_speed <= 4000);
  TEST_ASSERT_TRUE(r.max_speed >= 3950);
  // durée théorique : n/v + v/a = 10 + 0,2 s = 10,2 s
  const float t = r.ticks / 20000.0f;
  TEST_ASSERT_FLOAT_WITHIN(0.1, 10.2, t);
  TEST_ASSERT_TRUE(r.min_gap_ticks >= 2);   // jamais d'impulsions sur deux ticks consécutifs
  // l'estimation de durée est cohérente
  TEST_ASSERT_INT_WITHIN(150, 10200, g.estimateMs(40000));
}

void test_stepgen_profil_triangulaire_court() {
  StepGen g;
  g.configure(20000, 8000, 10000);
  g.setPosition(0);
  g.moveTo(1000);                           // trop court pour atteindre vmax
  const Run r = runUntilIdle(g);
  TEST_ASSERT_EQUAL_UINT32(1000, r.steps);
  TEST_ASSERT_TRUE(r.max_speed < 5000);
  // vpic = √(a·n) = 3162 pas/s ; durée = 2√(n/a) = 0,632 s
  TEST_ASSERT_FLOAT_WITHIN(0.06, 0.632, r.ticks / 20000.0f);
}

void test_stepgen_vitesse_plafonnee_a_tick_sur_2() {
  StepGen g;
  g.configure(10000, 999999, 1000000);      // demande absurde : plafonnée à 5000 pas/s
  g.setPosition(0);
  g.moveTo(20000);
  const Run r = runUntilIdle(g);
  TEST_ASSERT_EQUAL_UINT32(20000, r.steps);
  TEST_ASSERT_TRUE(r.max_speed <= 5000);
  TEST_ASSERT_TRUE(r.min_gap_ticks >= 2);
}

void test_stepgen_changement_de_cible_en_vol() {
  StepGen g;
  g.configure(20000, 4000, 20000);
  g.setPosition(0);
  g.moveTo(20000);
  int s = 0;
  for (int i = 0; i < 20000 && g.busy(); ++i) s += g.tick() ? 1 : 0;     // 1 s de mouvement
  TEST_ASSERT_TRUE(g.position() > 1000);
  const int32_t p0 = g.position();
  g.moveTo(p0 + 50);          // cible plus proche que la distance d'arrêt (≈ 400 pas) :
  const Run r = runUntilIdle(g);   // dépassement en décélération, puis retour à la cible
  (void)s;
  TEST_ASSERT_FALSE(g.busy());
  TEST_ASSERT_EQUAL_INT32(p0 + 50, g.position());
  TEST_ASSERT_TRUE(r.steps > 50 && r.steps < 1000);   // pas d'arrêt brutal, dépassement borné
  TEST_ASSERT_EQUAL_INT(1, r.reversals);
}

void test_stepgen_retournement() {
  StepGen g;
  g.configure(20000, 4000, 20000);
  g.setPosition(0);
  g.moveTo(30000);
  for (int i = 0; i < 20000; ++i) g.tick();       // 1 s : en pleine vitesse
  const int32_t p1 = g.position();
  g.moveTo(p1 - 5000);                            // demi-tour
  const Run r = runUntilIdle(g);
  TEST_ASSERT_EQUAL_INT32(p1 - 5000, g.position());
  TEST_ASSERT_TRUE(r.steps > 5000);               // a dû finir de freiner avant de repartir
}

void test_stepgen_arret_et_urgence() {
  StepGen g;
  g.configure(20000, 4000, 20000);
  g.setPosition(0);
  g.moveTo(100000);
  for (int i = 0; i < 20000; ++i) g.tick();
  g.stop();
  const int32_t p_before = g.position();
  const Run r = runUntilIdle(g);
  TEST_ASSERT_FALSE(g.busy());
  TEST_ASSERT_TRUE(g.position() - p_before <= 410);   // v²/2a = 400 pas
  TEST_ASSERT_TRUE(r.steps > 0);
  // arrêt d'urgence : plus aucune impulsion immédiatement
  g.moveTo(g.position() + 100000);
  for (int i = 0; i < 5000; ++i) g.tick();
  g.emergencyStop();
  for (int i = 0; i < 100; ++i) TEST_ASSERT_FALSE(g.tick());
  TEST_ASSERT_FALSE(g.busy());
  TEST_ASSERT_TRUE(g.setPosition(0));
}

void test_stepgen_setposition_refuse_en_mouvement() {
  StepGen g;
  g.configure(20000, 4000, 20000);
  g.moveTo(10000);
  for (int i = 0; i < 2000; ++i) g.tick();
  TEST_ASSERT_FALSE(g.setPosition(0));
}

void test_stepgen_aleatoire_position_exacte() {
  // 400 déplacements aléatoires avec changements de cible en vol : la position finale doit
  // toujours être exactement la dernière cible, sans impulsions rapprochées.
  StepGen g;
  g.configure(20000, 3000, 15000);
  g.setPosition(0);
  uint32_t seed = 7;
  auto rnd = [&](int32_t lo, int32_t hi) { seed = seed * 1664525u + 1013904223u; return lo + static_cast<int32_t>((seed >> 8) % static_cast<uint32_t>(hi - lo + 1)); };
  for (int n = 0; n < 400; ++n) {
    g.moveTo(g.position() + rnd(-3000, 3000));
    const int run = rnd(0, 8000);
    bool prev = false;
    for (int i = 0; i < run; ++i) {
      const bool st = g.tick();
      TEST_ASSERT_FALSE(st && prev);
      prev = st;
      if ((i % 997) == 996) g.moveTo(g.position() + rnd(-1500, 1500));
    }
    if (n % 3 == 0) {
      const int32_t tgt = g.target();
      runUntilIdle(g);
      TEST_ASSERT_EQUAL_INT32(tgt, g.position());
    }
  }
  runUntilIdle(g);
  TEST_ASSERT_EQUAL_INT32(g.target(), g.position());
}

// ---- sécurité -----------------------------------------------------------------------------------

static SafetyInputs nominal(uint32_t t) {
  SafetyInputs in;
  in.now_ms = t; in.last_host_ms = t;
  in.p_max_meas_Pa = 100.0f; in.n_valid_pressure = 5;
  in.duty = 0.5f; in.rpm_min = 2500.0f; in.rpm_max = 2600.0f;
  return in;
}

void test_safety_nominal() {
  Safety s; s.configure(SafetyConfig());
  for (uint32_t t = 0; t < 10000; t += 20) TEST_ASSERT_TRUE(s.update(nominal(t)) == SafetyState::Ok);
  TEST_ASSERT_EQUAL_UINT16(0, s.latched());
  TEST_ASSERT_FALSE(s.motorsInhibited());
}

void test_safety_surpression_temporisee_et_verrouillee() {
  Safety s; s.configure(SafetyConfig());
  SafetyInputs in = nominal(0);
  in.p_max_meas_Pa = 600.0f;
  in.now_ms = 1000; TEST_ASSERT_TRUE(s.update(in) == SafetyState::Ok);       // début du dépassement
  in.now_ms = 1100; TEST_ASSERT_TRUE(s.update(in) == SafetyState::Ok);       // < 200 ms : toléré (pic)
  in.now_ms = 1250; TEST_ASSERT_TRUE(s.update(in) == SafetyState::Safe);
  TEST_ASSERT_TRUE(s.latched() & FAULT_OVERPRESSURE);
  TEST_ASSERT_TRUE(s.fanSafe());
  TEST_ASSERT_TRUE(s.motorsInhibited());
  // La pression redescend : le défaut reste verrouillé jusqu'à CLEAR
  in.p_max_meas_Pa = 100.0f;
  in.now_ms = 1300; TEST_ASSERT_TRUE(s.update(in) == SafetyState::Safe);
  TEST_ASSERT_TRUE(s.clear());
  TEST_ASSERT_TRUE(s.state() == SafetyState::Ok);
}

void test_safety_pic_bref_de_pression_ignore() {
  Safety s; s.configure(SafetyConfig());
  SafetyInputs in = nominal(0);
  for (uint32_t t = 0; t < 5000; t += 20) {
    in = nominal(t);
    if ((t / 100) % 5 == 0) in.p_max_meas_Pa = 700.0f;                 // pics de 100 ms
    TEST_ASSERT_TRUE(s.update(in) == SafetyState::Ok);
  }
}

void test_safety_calage_ventilateur() {
  Safety s; s.configure(SafetyConfig());
  SafetyInputs in = nominal(0);
  in.rpm_min = 0.0f;                                                     // tachy nul, PWM 50 %
  for (uint32_t t = 0; t < 2900; t += 100) { in.now_ms = t; TEST_ASSERT_TRUE(s.update(in) == SafetyState::Ok); }
  in.now_ms = 3000;
  TEST_ASSERT_TRUE(s.update(in) == SafetyState::Safe);
  TEST_ASSERT_TRUE(s.latched() & FAULT_STALL);
  // En SAFE la PWM retombe sous le seuil de calage : CLEAR possible
  in.duty = 0.15f; in.now_ms = 3100; s.update(in);
  TEST_ASSERT_TRUE(s.clear());
}

void test_safety_pwm_faible_pas_de_calage() {
  Safety s; s.configure(SafetyConfig());
  SafetyInputs in = nominal(0);
  in.duty = 0.12f; in.rpm_min = 0.0f;                                    // PWM trop faible pour exiger une rotation
  for (uint32_t t = 0; t < 20000; t += 100) { in.now_ms = t; TEST_ASSERT_TRUE(s.update(in) == SafetyState::Ok); }
}

void test_safety_capteurs_absents() {
  Safety s; s.configure(SafetyConfig());           // min 2 capteurs valides
  SafetyInputs in = nominal(0);
  in.n_valid_pressure = 3;                         // 2 capteurs perdus : on continue
  for (uint32_t t = 0; t < 2000; t += 50) { in.now_ms = t; TEST_ASSERT_TRUE(s.update(in) == SafetyState::Ok); }
  in.n_valid_pressure = 1;
  in.now_ms = 2000; TEST_ASSERT_TRUE(s.update(in) == SafetyState::Ok);
  in.now_ms = 2400; TEST_ASSERT_TRUE(s.update(in) == SafetyState::Ok);
  in.now_ms = 2550; TEST_ASSERT_TRUE(s.update(in) == SafetyState::Safe);
  TEST_ASSERT_TRUE(s.latched() & FAULT_SENSOR_LOST);
  // La cause persiste : CLEAR refusé
  in.now_ms = 2600; s.update(in);
  TEST_ASSERT_FALSE(s.clear());
  in.n_valid_pressure = 5; in.now_ms = 2700; s.update(in);
  TEST_ASSERT_TRUE(s.clear());
}

void test_safety_watchdog_hote_optionnel() {
  Safety s; s.configure(SafetyConfig());
  SafetyInputs in = nominal(0);
  in.last_host_ms = 0;
  in.now_ms = 600000; TEST_ASSERT_TRUE(s.update(in) == SafetyState::Ok);   // désactivé par défaut
  s.setHostTimeoutMs(2000);
  in.now_ms = 601000; in.last_host_ms = 600000; TEST_ASSERT_TRUE(s.update(in) == SafetyState::Ok);
  in.now_ms = 602500; TEST_ASSERT_TRUE(s.update(in) == SafetyState::Safe);
  TEST_ASSERT_TRUE(s.latched() & FAULT_HOST_WDT);
  in.last_host_ms = 602500; in.now_ms = 602520; s.update(in);
  TEST_ASSERT_TRUE(s.clear());
}

void test_safety_fin_de_course_et_inclinometre() {
  Safety s; s.configure(SafetyConfig());
  SafetyInputs in = nominal(0);
  in.limit_hit = true;
  TEST_ASSERT_TRUE(s.update(in) == SafetyState::Ok);        // pas SAFE : le ventilateur continue
  TEST_ASSERT_TRUE(s.motorsInhibited());                    // mais les moteurs sont inhibés
  TEST_ASSERT_FALSE(s.fanSafe());
  in.limit_hit = false; in.now_ms = 20; s.update(in);
  TEST_ASSERT_TRUE(s.motorsInhibited());                    // verrouillé jusqu'à CLEAR
  TEST_ASSERT_TRUE(s.clear());
  TEST_ASSERT_FALSE(s.motorsInhibited());
  // Inclinomètre perdu : s'efface tout seul à la reprise
  in.tilt_valid = false; in.now_ms = 40; s.update(in);
  TEST_ASSERT_TRUE(s.motorsInhibited());
  in.tilt_valid = true; in.now_ms = 60; s.update(in);
  TEST_ASSERT_FALSE(s.motorsInhibited());
}

void test_safety_manuel_et_debordement_millis() {
  Safety s; s.configure(SafetyConfig());
  s.raise(FAULT_MANUAL);
  TEST_ASSERT_TRUE(s.state() == SafetyState::Safe);
  TEST_ASSERT_TRUE(s.clear());
  // Fenêtre de calage à cheval sur le débordement de millis() (49,7 jours)
  SafetyInputs in = nominal(0);
  in.rpm_min = 0.0f;
  in.now_ms = 0xFFFFFFFFu - 1000u; s.update(in);
  in.now_ms = 1500u;
  TEST_ASSERT_TRUE(s.update(in) == SafetyState::Ok);      // 2500 ms < 3000 ms
  in.now_ms = 2200u;
  TEST_ASSERT_TRUE(s.update(in) == SafetyState::Safe);    // 3200 ms
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_stepgen_atteint_exactement_la_cible);
  RUN_TEST(test_stepgen_direction_negative);
  RUN_TEST(test_stepgen_profil_trapezoidal);
  RUN_TEST(test_stepgen_profil_triangulaire_court);
  RUN_TEST(test_stepgen_vitesse_plafonnee_a_tick_sur_2);
  RUN_TEST(test_stepgen_changement_de_cible_en_vol);
  RUN_TEST(test_stepgen_retournement);
  RUN_TEST(test_stepgen_arret_et_urgence);
  RUN_TEST(test_stepgen_setposition_refuse_en_mouvement);
  RUN_TEST(test_stepgen_aleatoire_position_exacte);
  RUN_TEST(test_safety_nominal);
  RUN_TEST(test_safety_surpression_temporisee_et_verrouillee);
  RUN_TEST(test_safety_pic_bref_de_pression_ignore);
  RUN_TEST(test_safety_calage_ventilateur);
  RUN_TEST(test_safety_pwm_faible_pas_de_calage);
  RUN_TEST(test_safety_capteurs_absents);
  RUN_TEST(test_safety_watchdog_hote_optionnel);
  RUN_TEST(test_safety_fin_de_course_et_inclinometre);
  RUN_TEST(test_safety_manuel_et_debordement_millis);
  return UNITY_END();
}
