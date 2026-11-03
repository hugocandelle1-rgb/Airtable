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
  static_assert(TILT_MAX_SENSORS == atc::kMaxTilt, "config.h et atcore/tilt_array.h doivent concorder");
  static_assert(TILT_NUM_SENSORS >= 1 && TILT_NUM_SENSORS <= TILT_MAX_SENSORS, "TILT_NUM_SENSORS hors plage");
  // Réseau d'inclinomètres : détection des capteurs présents (DEVID / WHO_AM_I), un échec n'arrête pas les autres
  n_tilt_ = TILT_NUM_SENSORS;
  for (int i = 0; i < n_tilt_; ++i) {
    ch_[i].drv = &drv_[i];
    ch_[i].present = drv_[i].begin();
  }
#ifdef USE_FLIP_ACTUATOR
  flip_act_.begin();
#endif
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
  fuse_cfg_.reject_urad = TILT_REJECT_URAD;
  fuse_cfg_.sigma_floor_urad = TILT_SIGMA_FLOOR_URAD;
  fuse_cfg_.min_sensors = 1;
  FlipConfig fc;
  fc.settle_ms = FLIP_SETTLE_MS;
  fc.avg_ms = FLIP_AVG_MS;
  fc.move_timeout_ms = FLIP_MOVE_TIMEOUT_MS;
  fc.drift_limit_urad = FLIP_DRIFT_LIMIT_URAD;
  flip_.configure(fc);

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

  if (due(now, &t_tilt_poll_, T_TILT_POLL_MS)) tiltPoll();
  if (due(now, &t_pressure_, T_PRESSURE_MS)) press_.update(now);
  if (due(now, &t_tach_, T_TACH_MS)) fans_.updateRpm(micros());
  disp_.poll(now);                                   // machine à états : teste DRDY à chaque tour
  if (due(now, &t_env_, T_ENV_MS)) env_.update(now);
  if (due(now, &t_tilt_out_, T_TILT_OUT_MS)) tiltTask(now);
  flipTask(now);
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
  in.tilt_valid = tilt_valid_ || flipBusy();   // pendant un retournement le nivellement est gelé : pas de défaut
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

// ---- inclinomètres : lecture synchronisée, fusion (10 Hz) -------------------------------------------

// Les N capteurs sont lus l'un après l'autre dans le même tour de boucle (≈ 0,2 ms chacun à 1 MHz) :
// leurs échantillons partagent la même fenêtre d'acquisition de 100 ms, moyennée avant l'arctangente.
void App::tiltPoll() {
  const uint32_t t = micros();
  for (int i = 0; i < n_tilt_; ++i) {
    if (ch_[i].present) ch_[i].drv->poll(t);
  }
}

// Le capteur retournable reste exclu de la fusion pendant la séquence, tant que l'embase n'est pas revenue à 0°,
// en cas de défaut d'index, et FLIP_SETTLE_MS/2 après le retour (vibrations de l'appui, rééquilibrage thermique).
bool App::flipExcludesSensor(uint32_t now_ms) {
  const bool busy = flip_.active() || flip_act_.moving() || flip_act_.targetDeg() != 0.0f || flip_act_.fault();
  if (busy) flip_last_busy_ms_ = now_ms;
  return busy || (flip_last_busy_ms_ != 0 && static_cast<uint32_t>(now_ms - flip_last_busy_ms_) < FLIP_SETTLE_MS / 2);
}

bool App::flipBusy() const { return flip_.active() || flip_act_.moving(); }

void App::resetTiltAverages() {
  avg_x_.reset();
  avg_y_.reset();
}

void App::tiltTask(uint32_t now_ms) {
  FuseInput in[atc::kMaxTilt];
  const bool excl = flipExcludesSensor(now_ms);
  Vec2 plates[atc::kMaxTilt];
  for (int i = 0; i < n_tilt_; ++i) {
    TiltChannel& c = ch_[i];
    TiltSample s;
    bool fresh = false;
    if (c.present && c.drv->read(&s) && s.valid) {
      c.s = s;
      c.last_ok_ms = now_ms;
      c.have = true;
      fresh = true;
      if (i == FLIP_SENSOR_IDX) flip_new_sample_ = true;
    }
    // Température de la base : TMP117 accolé ; à défaut (SCL3300 seul) température interne du capteur
    const bool t117 = env_.Tb_valid[i];
    c.T = t117 ? env_.Tb[i] : (c.have ? c.s.temp_C : NAN);
    const SensorCal& cal = settings_.sens[i];
    const bool alive = c.present && c.have && c.drv->healthy() && (now_ms - c.last_ok_ms) < TILT_TIMEOUT_MS;
    c.valid = alive && (!cal.th.active() || t117);
    if (c.valid) {
      const Vec2 raw = {c.s.x_urad, c.s.y_urad};
      c.comp = compensateThermal(cal.th, raw, c.T);
      c.plate = applyTiltCal(cal.geo, c.comp);
      if (fresh) {
        c.sd.update(c.plate);
        if (learner_[i].active() && t117) learner_[i].add(c.T, raw.x, raw.y);
      }
    }
    plates[i] = c.plate;
    in[i].valid = c.valid && ((settings_.tilt_use_mask >> i) & 1) && !(excl && i == FLIP_SENSOR_IDX);
    in[i].tilt = c.plate;
    in[i].sigma_urad = c.sd.sigma(TILT_SIGMA_FLOOR_URAD);
  }

  fuse_ = fuseTilt(in, n_tilt_, fuse_cfg_);
  field_ = fitSlopeField(plates, TILT_POS_X_MM, TILT_POS_Y_MM, fuse_.used_mask, n_tilt_);
  if (fuse_.used_mask != used_prev_) {            // l'ensemble des capteurs retenus change : la moyenne glissante n'a plus de sens
    resetTiltAverages();
    level_.reset();
    used_prev_ = fuse_.used_mask;
  }
  if (fuse_.valid) {
    tilt_plate_ = fuse_.tilt;
    tilt_avg_ = {avg_x_.update(tilt_plate_.x), avg_y_.update(tilt_plate_.y)};
    tilt_last_ok_ms_ = now_ms;
  }
  tilt_valid_ = fuse_.valid && avg_x_.count() > 0;
}

// ---- retournement motorisé (à chaque tour) ------------------------------------------------------------

void App::flipTask(uint32_t now_ms) {
#ifdef USE_FLIP_ACTUATOR
  flip_act_.service(now_ms);
  if (flip_.state() == FlipState::Idle) return;
  if (flip_.active()) {
    const TiltChannel& c = ch_[FLIP_SENSOR_IDX];
    FlipInputs in;
    in.new_sample = flip_new_sample_;
    in.sample_valid = c.valid;
    in.sample = c.comp;
    in.T_C = c.T;
    in.at_target = flip_act_.atTarget();
    in.fault = flip_act_.fault() || safety_.fanSafe() || lvl_.busy();
    flip_.update(now_ms, in);
  }
  flip_new_sample_ = false;
  flip_act_.setTarget(flip_.targetDeg(), now_ms);   // Done / Failed : consigne 0°, l'embase revient
#else
  (void)now_ms;
#endif
}

// ---- nivellement automatique (1 Hz) ------------------------------------------------------------

void App::levelTask(uint32_t now_ms) {
  if (!auto_level_ || !lvl_.homed() || lvl_.inhibited() || lvl_.busy() || flipBusy() || learning_) { level_.reset(); return; }
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
