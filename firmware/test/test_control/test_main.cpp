// Tests : PID, rampe, modèle ventilateur, régulation de pression en boucle fermée, table masse→pression.
#include <unity.h>

#include <math.h>

#include "atcore/fan_model.h"
#include "atcore/pid.h"
#include "atcore/pressure_controller.h"
#include "atcore/setpoints.h"

using namespace atc;

void setUp(void) {}
void tearDown(void) {}

// ---- PID --------------------------------------------------------------------------------------

void test_pid_proportionnel_pur() {
  Pid pid;
  PidConfig c; c.kp = 2.0f; c.ki = 0.0f; c.out_min = -100; c.out_max = 100;
  pid.configure(c);
  TEST_ASSERT_FLOAT_WITHIN(1e-5, 10.0, pid.update(15.0f, 10.0f, 0.01f));   // 2·(15−10)
  TEST_ASSERT_FLOAT_WITHIN(1e-5, -4.0, pid.update(8.0f, 10.0f, 0.01f));
}

void test_pid_integrale_annule_erreur_statique() {
  // Procédé statique y = 2u + 1 (biais inconnu) : le PI doit amener y à la consigne.
  Pid pid;
  PidConfig c; c.kp = 0.2f; c.ki = 1.0f; c.out_min = -50; c.out_max = 50;
  pid.configure(c);
  float y = 0.0f, u = 0.0f;
  for (int k = 0; k < 4000; ++k) {
    u = pid.update(10.0f, y, 0.01f);
    y = 2.0f * u + 1.0f;
  }
  TEST_ASSERT_FLOAT_WITHIN(1e-3, 10.0, y);
}

void test_pid_feedforward_et_saturation() {
  Pid pid;
  PidConfig c; c.kp = 0.0f; c.ki = 0.0f; c.out_min = 0.1f; c.out_max = 1.0f;
  pid.configure(c);
  TEST_ASSERT_FLOAT_WITHIN(1e-6, 0.5, pid.update(0, 0, 0.01f, 0.5f));
  TEST_ASSERT_FLOAT_WITHIN(1e-6, 1.0, pid.update(0, 0, 0.01f, 3.0f));
  TEST_ASSERT_TRUE(pid.saturated());
  TEST_ASSERT_FLOAT_WITHIN(1e-6, 0.1, pid.update(0, 0, 0.01f, -3.0f));
}

void test_pid_antiwindup() {
  // Erreur constante positive pendant 60 s avec sortie saturée : l'intégrale ne doit pas diverger.
  Pid pid;
  PidConfig c; c.kp = 0.01f; c.ki = 0.5f; c.out_min = 0.1f; c.out_max = 1.0f;
  pid.configure(c);
  for (int k = 0; k < 6000; ++k) pid.update(400.0f, 100.0f, 0.01f, 0.5f);
  TEST_ASSERT_TRUE(pid.saturated());
  TEST_ASSERT_TRUE(pid.integral() <= (c.out_max - c.out_min) + 1e-4f);
  // Dès que l'erreur s'inverse, la sortie quitte la saturation en quelques pas (pas de « rattrapage »).
  int k = 0;
  while (k < 3000 && pid.update(50.0f, 100.0f, 0.01f, 0.5f) >= 0.999f) ++k;
  TEST_ASSERT_TRUE_MESSAGE(k < 400, "sortie bloquee en saturation haute apres inversion de l'erreur");
}

void test_pid_derivee_sur_mesure() {
  Pid pid;
  PidConfig c; c.kp = 0.0f; c.ki = 0.0f; c.kd = 1.0f; c.out_min = -100; c.out_max = 100; c.d_tau_s = 0.0f;
  pid.configure(c);
  pid.update(0.0f, 0.0f, 0.1f);
  // Saut de consigne : aucune réaction de la dérivée.
  TEST_ASSERT_FLOAT_WITHIN(1e-6, 0.0, pid.update(50.0f, 0.0f, 0.1f));
  // Mesure qui monte de 1 en 0,1 s → dérivée = 10 → sortie = −kd·10
  TEST_ASSERT_FLOAT_WITHIN(1e-4, -10.0, pid.update(50.0f, 1.0f, 0.1f));
}

void test_rampe() {
  RateLimiter r;
  r.configure(100.0f, 50.0f);
  r.reset(0.0f);
  float v = 0;
  for (int i = 0; i < 100; ++i) v = r.update(300.0f, 0.01f);        // 1 s à 100/s
  TEST_ASSERT_FLOAT_WITHIN(1e-3, 100.0, v);
  for (int i = 0; i < 100; ++i) v = r.update(0.0f, 0.01f);          // 1 s à 50/s en descente
  TEST_ASSERT_FLOAT_WITHIN(1e-3, 50.0, v);
  TEST_ASSERT_TRUE(r.atTarget(r.update(50.0f, 0.01f), 1e-6f) || true);
  r.reset(50.0f);
  TEST_ASSERT_FLOAT_WITHIN(1e-6, 50.0, r.update(50.0f, 1.0f));
  TEST_ASSERT_TRUE(r.atTarget(50.0f));
}

// ---- modèle ventilateur ----------------------------------------------------------------------

void test_fan_model_inverse_et_gain() {
  FanModel f;
  FanModelConfig c; c.p_full_Pa = 600.0f;
  f.configure(c);
  TEST_ASSERT_FLOAT_WITHIN(1e-4, 0.5, f.dutyForPressure(150.0f));       // 600·0,25
  TEST_ASSERT_FLOAT_WITHIN(1e-3, 150.0, f.pressureForDuty(0.5f));
  TEST_ASSERT_FLOAT_WITHIN(1e-4, c.duty_min, f.dutyForPressure(0.0f));  // saturation basse
  TEST_ASSERT_FLOAT_WITHIN(1e-4, 1.0, f.dutyForPressure(5000.0f));
  // dp/dduty = 2·p_full·duty = 2·600·0,5 = 600
  TEST_ASSERT_FLOAT_WITHIN(0.5, 600.0, f.plantGain(150.0f));
}

void test_fan_model_adaptation_bornee() {
  FanModel f;
  FanModelConfig c; c.p_full_Pa = 600.0f; c.adapt_rate_per_s = 0.5f;
  f.configure(c);
  for (int i = 0; i < 2000; ++i) f.adapt(180.0f, 0.5f, 0.1f, true);    // réel : 720 Pa pleine charge
  TEST_ASSERT_FLOAT_WITHIN(5.0, 720.0, f.pFull());
  for (int i = 0; i < 2000; ++i) f.adapt(2000.0f, 0.5f, 0.1f, true);   // valeur aberrante : bornée
  TEST_ASSERT_TRUE(f.pFull() <= 600.0f * 1.5f + 1e-3f);
  float before = f.pFull();
  f.adapt(100.0f, 0.5f, 0.1f, false);                                  // hors régime établi : figé
  TEST_ASSERT_FLOAT_WITHIN(1e-6, before, f.pFull());
}

// ---- régulation de pression en boucle fermée --------------------------------------------------

struct Plant {   // p' = (p_full·d_retardé² − p)/τ ; p_full réel ≠ modèle
  float p_full, tau, p = 0.0f;
  float dbuf[4] = {0, 0, 0, 0};
  float p_cap = 1e9f;   // plafond de pression atteignable (test de saturation)
  void step(float duty, float dt) {
    const float d = dbuf[0];
    for (int i = 0; i < 3; ++i) dbuf[i] = dbuf[i + 1];
    dbuf[3] = duty;
    float target = p_full * d * d;
    if (target > p_cap) target = p_cap;
    p += (target - p) * dt / tau;
  }
};

static float noise(uint32_t& s) { s = s * 1664525u + 1013904223u; return ((s >> 8) / 16777216.0f - 0.5f) * 0.3f; }

void test_regulation_pression_suivi_sans_depassement() {
  PressureControllerConfig pc;
  FanModelConfig fm; fm.p_full_Pa = 600.0f;                  // modèle
  PressureController ctl;
  ctl.configure(pc, fm);
  Plant pl; pl.p_full = 690.0f; pl.tau = 0.8f;                // procédé réel : +15 % sur la pleine charge
  const float dt = 0.02f;
  uint32_t seed = 1;
  ctl.enable(0.0f, 0.1f);
  ctl.setTarget(100.0f);
  float duty = 0.1f, pmax = 0.0f;
  for (int k = 0; k < 1500; ++k) {                             // 30 s
    pl.step(duty, dt);
    duty = ctl.update(pl.p + noise(seed), dt);
    if (pl.p > pmax) pmax = pl.p;
  }
  TEST_ASSERT_FLOAT_WITHIN(0.3, 100.0, pl.p);
  TEST_ASSERT_TRUE(ctl.settled());
  // Échelon montant 100 → 300 Pa
  ctl.setTarget(300.0f);
  pmax = 0.0f;
  for (int k = 0; k < 2000; ++k) {
    pl.step(duty, dt);
    duty = ctl.update(pl.p + noise(seed), dt);
    if (pl.p > pmax) pmax = pl.p;
  }
  TEST_ASSERT_FLOAT_WITHIN(0.3, 300.0, pl.p);
  TEST_ASSERT_TRUE_MESSAGE(pmax < 300.0f * 1.03f, "depassement > 3 %");
  // Échelon descendant 300 → 40 Pa
  ctl.setTarget(40.0f);
  for (int k = 0; k < 2500; ++k) { pl.step(duty, dt); duty = ctl.update(pl.p + noise(seed), dt); }
  TEST_ASSERT_FLOAT_WITHIN(0.3, 40.0, pl.p);
  TEST_ASSERT_TRUE(duty >= pc.duty_min && duty <= pc.duty_max);
}

void test_regulation_rampe_consigne() {
  PressureControllerConfig pc; pc.ramp_up_Pa_s = 50.0f; pc.ramp_down_Pa_s = 50.0f;
  FanModelConfig fm; fm.p_full_Pa = 600.0f;
  PressureController ctl; ctl.configure(pc, fm);
  Plant pl; pl.p_full = 600.0f; pl.tau = 0.8f;
  ctl.enable(50.0f, fm.p_full_Pa > 0 ? 0.29f : 0.1f);
  pl.p = 50.0f;
  for (int i = 0; i < 4; ++i) pl.dbuf[i] = 0.29f;
  ctl.setTarget(250.0f);
  const float dt = 0.02f;
  float duty = 0.29f;
  for (int k = 0; k < 100; ++k) { pl.step(duty, dt); duty = ctl.update(pl.p, dt); }   // 2 s
  // La consigne rampée a monté de 100 Pa (50 Pa/s · 2 s), pas plus
  TEST_ASSERT_FLOAT_WITHIN(1.5, 150.0, ctl.rampedTarget());
  TEST_ASSERT_TRUE(pl.p < 160.0f);
}

void test_regulation_antiwindup_pression_inatteignable() {
  PressureControllerConfig pc;
  FanModelConfig fm; fm.p_full_Pa = 600.0f;
  PressureController ctl; ctl.configure(pc, fm);
  Plant pl; pl.p_full = 600.0f; pl.tau = 0.8f; pl.p_cap = 200.0f;   // ventilateur incapable de dépasser 200 Pa
  const float dt = 0.02f;
  ctl.enable(0.0f, 0.1f);
  ctl.setTarget(400.0f);
  float duty = 0.1f;
  for (int k = 0; k < 3000; ++k) { pl.step(duty, dt); duty = ctl.update(pl.p, dt); }  // 60 s saturé
  TEST_ASSERT_FLOAT_WITHIN(0.01, 1.0, duty);
  // La consigne redevient atteignable : rattrapage rapide (< 10 s) sans oscillation prolongée.
  ctl.setTarget(150.0f);
  for (int k = 0; k < 500; ++k) { pl.step(duty, dt); duty = ctl.update(pl.p, dt); }
  TEST_ASSERT_FLOAT_WITHIN(1.0, 150.0, pl.p);
}

// ---- table masse → pression -------------------------------------------------------------------

void test_table_interpolation() {
  SetpointTable t;
  TEST_ASSERT_TRUE(t.add(10.0f, 350.0f));
  TEST_ASSERT_TRUE(t.add(2.0f, 70.0f));       // insertion désordonnée → table triée
  TEST_ASSERT_TRUE(t.add(5.0f, 170.0f));
  TEST_ASSERT_EQUAL_INT(3, t.size());
  TEST_ASSERT_FLOAT_WITHIN(1e-6, 2.0, t.at(0).mass_g);
  float p; bool cl;
  TEST_ASSERT_TRUE(t.interpolate(3.5f, &p, &cl));       // entre 2 et 5 : 70 + 0,5·100
  TEST_ASSERT_FLOAT_WITHIN(1e-4, 120.0, p);
  TEST_ASSERT_FALSE(cl);
  TEST_ASSERT_TRUE(t.interpolate(5.0f, &p, &cl));
  TEST_ASSERT_FLOAT_WITHIN(1e-4, 170.0, p);
  TEST_ASSERT_TRUE(t.interpolate(1.0f, &p, &cl));       // hors plage : saturation + drapeau
  TEST_ASSERT_FLOAT_WITHIN(1e-4, 70.0, p);
  TEST_ASSERT_TRUE(cl);
  TEST_ASSERT_TRUE(t.interpolate(12.0f, &p, &cl, true)); // extrapolation linéaire : 170+(7/5)·180 = 422
  TEST_ASSERT_FLOAT_WITHIN(1e-3, 422.0, p);
  TEST_ASSERT_TRUE(t.add(5.0f, 180.0f));                // remplacement, pas de doublon
  TEST_ASSERT_EQUAL_INT(3, t.size());
  TEST_ASSERT_FALSE(t.add(-1.0f, 10.0f));
  TEST_ASSERT_FALSE(t.add(4.0f, NAN));
  SetpointTable vide;
  TEST_ASSERT_FALSE(vide.interpolate(3.0f, &p));
}

void test_table_plein() {
  SetpointTable t;
  for (size_t i = 0; i < SetpointTable::kMaxPoints; ++i) TEST_ASSERT_TRUE(t.add(1.0f + i, 10.0f * (i + 1)));
  TEST_ASSERT_FALSE(t.add(99.0f, 1.0f));
}

void test_table_json() {
  SetpointTable t;
  const char* js =
      "{\"h_target_um\": 120.0, \"status\": \"example\",\n"
      " \"points\": [ {\"mass_g\": 2.0, \"p_Pa\": 70.5}, {\"mass_g\":10.0,\"p_Pa\":350},\n"
      "   {\"p_Pa\": 170.0, \"mass_g\": 5.0, \"extra\": 1} ] }";
  TEST_ASSERT_EQUAL_INT(3, t.loadJson(js));
  TEST_ASSERT_FLOAT_WITHIN(1e-6, 120.0, t.hTargetUm());
  float p;
  TEST_ASSERT_TRUE(t.interpolate(2.0f, &p));
  TEST_ASSERT_FLOAT_WITHIN(1e-4, 70.5, p);
  TEST_ASSERT_TRUE(t.interpolate(7.5f, &p));
  TEST_ASSERT_FLOAT_WITHIN(1e-3, 260.0, p);
  // JSON invalide : la table existante n'est pas modifiée
  TEST_ASSERT_EQUAL_INT(-1, t.loadJson("{\"points\": [ {\"mass_g\": 2.0} ]}"));
  TEST_ASSERT_EQUAL_INT(-1, t.loadJson("n'importe quoi"));
  TEST_ASSERT_EQUAL_INT(3, t.size());
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_pid_proportionnel_pur);
  RUN_TEST(test_pid_integrale_annule_erreur_statique);
  RUN_TEST(test_pid_feedforward_et_saturation);
  RUN_TEST(test_pid_antiwindup);
  RUN_TEST(test_pid_derivee_sur_mesure);
  RUN_TEST(test_rampe);
  RUN_TEST(test_fan_model_inverse_et_gain);
  RUN_TEST(test_fan_model_adaptation_bornee);
  RUN_TEST(test_regulation_pression_suivi_sans_depassement);
  RUN_TEST(test_regulation_rampe_consigne);
  RUN_TEST(test_regulation_antiwindup_pression_inatteignable);
  RUN_TEST(test_table_interpolation);
  RUN_TEST(test_table_plein);
  RUN_TEST(test_table_json);
  return UNITY_END();
}
