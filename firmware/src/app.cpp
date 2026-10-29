#include "app.h"

#include <esp_system.h>
#include <esp_task_wdt.h>
#include <math.h>

#include "atcore/sdp8xx.h"

#if !defined(ESP_ARDUINO_VERSION_MAJOR)
#define ESP_ARDUINO_VERSION_MAJOR 2
#endif

using namespace atc;

static inline bool due(uint32_t now, uint32_t* last, uint32_t period) {
  if (static_cast<uint32_t>(now - *last) >= period) { *last = now; return true; }
  return false;
}

// ============================================================================================
//  Démarrage
// ============================================================================================

void App::begin() {
  Serial.begin(SERIAL_BAUD);
  last_host_ms_ = millis();

  settings_.load();

  // Chien de garde matériel : toute boucle bloquée > WDT_TIMEOUT_S redémarre le contrôleur
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  esp_task_wdt_config_t wcfg = {WDT_TIMEOUT_S * 1000, 0, true};
  esp_task_wdt_reconfigure(&wcfg);
#else
  esp_task_wdt_init(WDT_TIMEOUT_S, true);
#endif
  esp_task_wdt_add(nullptr);

  // Ventilateur à l'arrêt (PWM 0 %) tant que rien n'est demandé
  fans_.begin();
  fans_.setDuty(0.0f);

  SPI.begin(PIN_SPI_SCK, PIN_SPI_MISO, PIN_SPI_MOSI, -1);
  mux_.begin(Wire, TCA_ADDR, PIN_TCA_RESET);
  press_.begin(mux_);
  env_.begin(mux_);
#ifdef USE_ADXL355
  incl_ = &adxl_;
#else
  incl_ = &scl_;
#endif
  incl_->begin();
  disp_.begin(SPI);
  lvl_.begin();

  applySettings();

  PressureControllerConfig pc;
  pc.p_min_Pa = DESIGN_P_MIN_PA;
  pc.p_max_Pa = DESIGN_P_MAX_PA;
  pc.duty_min = FAN_DUTY_MIN;
  pc.duty_max = FAN_DUTY_MAX;
  pc.ramp_up_Pa_s = pc.ramp_down_Pa_s = CTRL_RAMP_PA_S;
  pc.meas_tau_s = CTRL_MEAS_TAU_S;
  pc.kp_norm = CTRL_KP_NORM;
  pc.ti_s = CTRL_TI_S;
  pc.ref_tau_s = CTRL_REF_TAU_S;
  pc.settle_tol_Pa = DESIGN_P_REGULATION_PA;
  FanModelConfig fm;
  fm.p_full_Pa = settings_.fan_p_full;
  ctl_.configure(pc, fm);

  SafetyConfig sc;
  sc.p_limit_Pa = SAFE_P_LIMIT_PA;
  sc.overpressure_ms = SAFE_OVERPRESSURE_MS;
  sc.stall_duty = SAFE_STALL_DUTY;
  sc.stall_rpm = SAFE_STALL_RPM;
  sc.stall_ms = SAFE_STALL_MS;
  sc.overspeed_rpm = SAFE_OVERSPEED_RPM;
  sc.min_valid_pressure = SAFE_MIN_VALID_PRESSURE;
  sc.sensor_lost_ms = SAFE_SENSOR_LOST_MS;
  safety_.configure(sc);

  LevelConfig lc;
  lc.deadband_urad = settings_.level_deadband;
  lc.confirm_n = LEVEL_CONFIRM_N;
  lc.gain = LEVEL_GAIN;
  lc.max_move_urad = LEVEL_MAX_MOVE_URAD;
  lc.settle_ms = LEVEL_SETTLE_MS;
  level_.configure(lc);
  level_.setTarget(settings_.level_target_x, settings_.level_target_y);
  avg_x_.setLength(TILT_AVG_SAMPLES);
  avg_y_.setLength(TILT_AVG_SAMPLES);

  pinMode(PIN_LED_EXT, OUTPUT);
  line_len_ = 0;
}

void App::applySettings() {
  for (int i = 0; i < NUM_PLENUM_SENSORS; ++i) press_.offset[i] = settings_.p_offset[i];
  press_.nozzle_offset = settings_.nozzle_offset;
}

// ============================================================================================
//  Boucle coopérative
// ============================================================================================

void App::tick() {
  const uint32_t now = millis();
  esp_task_wdt_reset();

  pollSerial(now);

  if (due(now, &t_tilt_poll_, T_TILT_POLL_MS)) incl_->poll(micros());
  if (due(now, &t_pressure_, T_PRESSURE_MS)) press_.update(now);
  if (due(now, &t_tach_, T_TACH_MS)) fans_.updateRpm(micros());
  disp_.poll(now);                                   // machine à états : teste DRDY à chaque tour
  if (due(now, &t_env_, T_ENV_MS)) env_.update(now);
  if (due(now, &t_tilt_out_, T_TILT_OUT_MS)) tiltTask(now);
  if (due(now, &t_control_, T_CONTROL_MS)) controlTask(now);
  if (due(now, &t_level_, T_LEVEL_MS)) levelTask(now);
  lvl_.service(now);
  if (due(now, &t_led_, T_LED_MS)) ledTask(now);
  streamTask(now);
}

SafetyInputs App::safetyInputs(uint32_t now_ms) const {
  SafetyInputs in;
  in.now_ms = now_ms;
  in.p_max_meas_Pa = press_.max;
  in.n_valid_pressure = press_.n_valid;
  in.duty = fans_.duty();
  in.rpm_min = fans_.rpmMin();
  in.rpm_max = fans_.rpmMax();
  in.limit_hit = lvl_.limitFault();
  in.tilt_valid = tilt_valid_;
  in.last_host_ms = last_host_ms_;
  return in;
}

// ---- régulation de pression + sécurités (50 Hz) -----------------------------------------------

void App::controlTask(uint32_t now_ms) {
  const float dt = last_control_ms_ ? (now_ms - last_control_ms_) * 1e-3f : T_CONTROL_MS * 1e-3f;
  last_control_ms_ = now_ms;

  safety_.update(safetyInputs(now_ms));
  const bool inhibit = safety_.motorsInhibited();
  if (inhibit != inhibited_prev_) { lvl_.setInhibit(inhibit); inhibited_prev_ = inhibit; }

  if (safety_.fanSafe()) {                           // état SAFE : PWM de repos, boucle ouverte
    if (mode_ != Mode::Safe) { ctl_.disable(); mode_ = Mode::Safe; auto_level_ = false; }
    fans_.setDuty(FAN_DUTY_REST);
    return;
  }
  switch (mode_) {
    case Mode::Off:
      fans_.setDuty(0.0f);
      break;
    case Mode::Manual:
      fans_.setDuty(manual_duty_);
      break;
    case Mode::Regulate:
      if (press_.n_valid > 0) fans_.setDuty(ctl_.update(press_.mean, dt));   // sinon : garde la dernière PWM
      break;
    case Mode::Safe:                                 // défaut acquitté (CLEAR) : retour à l'arrêt
      mode_ = Mode::Off;
      break;
  }
}

// ---- inclinomètre (10 Hz) --------------------------------------------------------------------

void App::tiltTask(uint32_t now_ms) {
  TiltSample s;
  if (incl_->read(&s) && s.valid) {
    tilt_sample_ = s;
    tilt_plate_ = applyTiltCal(settings_.tilt, {s.x_urad, s.y_urad});
    tilt_avg_ = {avg_x_.update(tilt_plate_.x), avg_y_.update(tilt_plate_.y)};
    tilt_last_ok_ms_ = now_ms;
  }
  tilt_valid_ = incl_->healthy() && (now_ms - tilt_last_ok_ms_) < TILT_TIMEOUT_MS && avg_x_.count() > 0;
}

// ---- nivellement automatique (1 Hz) ------------------------------------------------------------

void App::levelTask(uint32_t now_ms) {
  if (!auto_level_ || !lvl_.homed() || lvl_.inhibited() || lvl_.busy()) { level_.reset(); return; }
  // Attend une moyenne complète avant toute décision
  if (avg_x_.count() < TILT_AVG_SAMPLES) return;
  Vec2 ds;
  if (level_.update(now_ms, tilt_avg_, tilt_valid_, &ds)) {
    const uint32_t ms = lvl_.moveSlope(ds);
    if (ms) {
      level_.commit(now_ms, ms);
      avg_x_.reset();                                // repart d'une moyenne propre après le mouvement
      avg_y_.reset();
    }
  }
}

// ---- LED d'état ----------------------------------------------------------------------------------

void App::ledTask(uint32_t now_ms) {
  uint8_t r = 0, g = 0, b = 0;
  const bool blink = ((now_ms / 500) & 1) != 0;
  if (safety_.fanSafe()) { r = blink ? 40 : 4; }                              // rouge clignotant : SAFE
  else if (lvl_.busy()) { b = 30; }                                           // bleu : vérins en mouvement
  else if (safety_.latched() || press_.n_valid < NUM_PLENUM_SENSORS) { r = 25; g = 15; }   // orange : alerte
  else if (mode_ == Mode::Regulate) { g = ctl_.settled() ? 30 : (blink ? 30 : 5); }   // vert fixe : établi
  else { g = blink ? 6 : 0; }                                                 // vert faible : repos
  neopixelWrite(PIN_LED_RGB, r, g, b);
  digitalWrite(PIN_LED_EXT, (r || g || b) ? HIGH : LOW);
}

float App::flowM3h() const {
  const float q = nozzleFlow_m3s(press_.nozzle_dp, env_.rho, settings_.nozzle_cd, nozzleArea_m2(settings_.nozzle_diam_mm));
  return q * 3600.0f;
}
