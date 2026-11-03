// Protocole série : une commande texte par ligne, une réponse JSON d'une ligne.
//   - toute réponse à une commande contient la clé "ok" ;
//   - une trame de télémétrie (STREAM ON) contient "t" et PAS "ok".
#include <esp_system.h>
#include <math.h>
#include <string.h>

#include "app.h"
#include "atcore/sdp8xx.h"

using namespace atc;

// ============================================================================================
//  Entrée / sortie
// ============================================================================================

void App::sendLine(const char* s) {
  if (!Serial) return;                      // pas d'hôte connecté : on n'écrit pas (jamais de blocage)
  const size_t n = strlen(s);
  const size_t w = Serial.write(reinterpret_cast<const uint8_t*>(s), n);
  Serial.write('\n');
  if (w < n) ++dropped_;
}

void App::replyOk() { sendLine("{\"ok\":true}"); }

void App::replyErr(const char* msg) {
  char buf[96];
  JsonWriter j(buf, sizeof buf);
  j.beginObject().kv("ok", false).kv("err", msg).endObject();
  sendLine(buf);
}

void App::pollSerial(uint32_t now_ms) {
  int budget = 96;                          // octets traités par tour de boucle (jamais de monopolisation)
  while (budget-- > 0 && Serial.available() > 0) {
    const int c = Serial.read();
    if (c < 0) break;
    if (c == '\r') continue;
    if (c == '\n') {
      if (line_overflow_) { replyErr("line_too_long"); line_overflow_ = false; }
      else if (line_len_ > 0) { line_[line_len_] = '\0'; handleLine(line_, now_ms); }
      line_len_ = 0;
      continue;
    }
    if (line_len_ < SERIAL_LINE_MAX) line_[line_len_++] = static_cast<char>(c);
    else line_overflow_ = true;
  }
}

void App::handleLine(const char* line, uint32_t now_ms) {
  last_host_ms_ = now_ms;                   // toute ligne reçue réarme le chien de garde hôte
  Command c;
  const ParseError e = parseCommand(line, &c);
  if (e != ParseError::Ok) {
    if (e != ParseError::Empty) replyErr(parseErrorText(e));
    return;
  }
  execute(c, now_ms);
}

// ============================================================================================
//  Exécution des commandes
// ============================================================================================

bool App::startRegulation(float p, const char** err) {
  if (safety_.fanSafe()) { *err = "safe_state"; return false; }
  if (press_.n_valid < 1) { *err = "no_pressure_sensor"; return false; }
  if (p < DESIGN_P_MIN_PA || p > DESIGN_P_MAX_PA) { *err = "out_of_range"; return false; }
  ctl_.setTarget(p);
  if (mode_ != Mode::Regulate) {
    ctl_.enable(press_.mean, fans_.duty());
    mode_ = Mode::Regulate;
  }
  return true;
}

void App::execute(const Command& c, uint32_t now_ms) {
  char buf[JSON_BUF];
  JsonWriter j(buf, sizeof buf);
  const char* err = nullptr;

  switch (c.type) {
    case CmdType::Ping:
      j.beginObject().kv("ok", true).kv("pong", static_cast<uint32_t>(now_ms)).endObject();
      sendLine(buf);
      return;
    case CmdType::GetStatus:
      writeStatus(j, true);
      sendLine(buf);
      return;
    case CmdType::GetConfig:
      writeConfig(j);
      sendLine(buf);
      return;
    case CmdType::GetVersion:
      j.beginObject().kv("ok", true).kv("fw", FW_NAME).kv("ver", FW_VERSION)
          .kv("proto", static_cast<int32_t>(PROTOCOL_VERSION)).kv("incl", drv_[0].name()).kv("ntilt", static_cast<int32_t>(n_tilt_))
          .kv("reset", static_cast<int32_t>(esp_reset_reason())).endObject();
      sendLine(buf);
      return;
    case CmdType::GetFlip:
      writeFlipResult(j);
      sendLine(buf);
      return;
    case CmdType::GetTable: {
      j.beginObject().kv("ok", true).kv("h_um", table_.hTargetUm(), 1).key("points").beginArray();
      for (size_t i = 0; i < table_.size(); ++i) {
        j.beginArray().value(table_.at(i).mass_g, 2).value(table_.at(i).p_Pa, 2).endArray();
      }
      j.endArray().endObject();
      sendLine(buf);
      return;
    }

    // ---- ventilateur / pression
    case CmdType::SetP:
      if (!startRegulation(c.f[0], &err)) { replyErr(err); return; }
      mass_g_ = 0.0f;
      replyOk();
      return;
    case CmdType::SetMass: {
      float p;
      bool clamped = false;
      if (!table_.interpolate(c.f[0], &p, &clamped)) { replyErr("no_table"); return; }
      if (!startRegulation(p, &err)) { replyErr(err); return; }
      mass_g_ = c.f[0];
      j.beginObject().kv("ok", true).kv("p", p, 2).kv("clamped", clamped).endObject();
      sendLine(buf);
      return;
    }
    case CmdType::SetDuty:
      if (safety_.fanSafe()) { replyErr("safe_state"); return; }
      ctl_.disable();
      manual_duty_ = c.f[0];
      mode_ = Mode::Manual;
      replyOk();
      return;
    case CmdType::FanOn:
      if (safety_.fanSafe()) { replyErr("safe_state"); return; }
      ctl_.disable();
      manual_duty_ = FAN_DUTY_REST;
      mode_ = Mode::Manual;
      replyOk();
      return;
    case CmdType::FanOff:
      ctl_.disable();
      if (!safety_.fanSafe()) mode_ = Mode::Off;
      replyOk();
      return;
    case CmdType::SetRamp:
      ctl_.setRamp(c.f[0], c.f[0]);
      replyOk();
      return;
    case CmdType::SetGains:
      ctl_.setGainsNorm(c.f[0], c.f[1]);
      replyOk();
      return;
    case CmdType::SetNozzle:
      settings_.nozzle_cd = c.f[0];
      settings_.nozzle_diam_mm = c.f[1];
      replyOk();
      return;
    case CmdType::SetWdt:
      safety_.setHostTimeoutMs(static_cast<uint32_t>(c.f[0] * 1000.0f));
      replyOk();
      return;

    // ---- nivellement
    case CmdType::LevelAuto:
      if (c.flag && flipBusy()) { replyErr("flip_active"); return; }
      if (c.flag && (!lvl_.homed() || lvl_.inhibited())) { replyErr(lvl_.inhibited() ? "motors_inhibited" : "not_homed"); return; }
      auto_level_ = c.flag;
      level_.reset();
      replyOk();
      return;
    case CmdType::LevelHome:
      if (flipBusy()) { replyErr("flip_active"); return; }
      if (lvl_.inhibited()) { replyErr("motors_inhibited"); return; }
      auto_level_ = false;
      lvl_.startHoming();
      replyOk();
      return;
    case CmdType::LevelStop:
      auto_level_ = false;
      lvl_.stop();
      replyOk();
      return;
    case CmdType::LevelZero: {
      auto_level_ = false;
      const uint32_t ms = lvl_.goZero();
      if (!ms) { replyErr(lvl_.inhibited() ? "motors_inhibited" : "not_homed"); return; }
      j.beginObject().kv("ok", true).kv("ms", static_cast<uint32_t>(ms)).endObject();
      sendLine(buf);
      return;
    }
    case CmdType::LevelMove: {
      if (flipBusy()) { replyErr("flip_active"); return; }
      Vec2 ds = {c.axis == 0 ? c.f[0] : 0.0f, c.axis == 1 ? c.f[0] : 0.0f};
      const uint32_t ms = lvl_.moveSlope(ds);
      if (!ms) { replyErr(lvl_.inhibited() ? "motors_inhibited" : "not_homed"); return; }
      level_.commit(now_ms, ms);
      avg_x_.reset();
      avg_y_.reset();
      j.beginObject().kv("ok", true).kv("ms", static_cast<uint32_t>(ms)).endObject();
      sendLine(buf);
      return;
    }
    case CmdType::LevelJog: {
      if (flipBusy()) { replyErr("flip_active"); return; }
      const uint32_t ms = lvl_.jog(c.axis, c.f[0]);
      if (!ms) { replyErr(lvl_.inhibited() ? "motors_inhibited" : "not_homed"); return; }
      level_.commit(now_ms, ms);
      avg_x_.reset();
      avg_y_.reset();
      j.beginObject().kv("ok", true).kv("ms", static_cast<uint32_t>(ms)).endObject();
      sendLine(buf);
      return;
    }
    case CmdType::LevelTarget:
      settings_.level_target_x = c.f[0];
      settings_.level_target_y = c.f[1];
      level_.setTarget(c.f[0], c.f[1]);
      replyOk();
      return;
    case CmdType::LevelDeadband: {
      LevelConfig lc = level_.config();
      lc.deadband_urad = c.f[0];
      settings_.level_deadband = c.f[0];
      level_.configure(lc);
      level_.setTarget(settings_.level_target_x, settings_.level_target_y);
      replyOk();
      return;
    }

    // ---- étalonnages
    case CmdType::CalTiltBias:
    case CmdType::CalTiltRot:
    case CmdType::CalTiltClear: {
      int i0, i1;
      if (!targetSensors(c.axis, &i0, &i1)) { replyErr("no_such_sensor"); return; }
      for (int i = i0; i <= i1; ++i) {
        TiltCal& g = settings_.sens[i].geo;
        if (c.type == CmdType::CalTiltBias) { g.bias_x_urad = c.f[0]; g.bias_y_urad = c.f[1]; }
        else if (c.type == CmdType::CalTiltRot) g.mount_rot_deg = c.f[0];
        else g = TiltCal();
      }
      resetTiltAverages();
      replyOk();
      return;
    }
    case CmdType::CalTiltUse:
      if (c.axis >= n_tilt_) { replyErr("no_such_sensor"); return; }
      if (c.flag) settings_.tilt_use_mask = static_cast<uint8_t>(settings_.tilt_use_mask | (1u << c.axis));
      else settings_.tilt_use_mask = static_cast<uint8_t>(settings_.tilt_use_mask & ~(1u << c.axis));
      resetTiltAverages();
      replyOk();
      return;
    case CmdType::CalTiltThermStart:
      if (flipBusy() || lvl_.busy()) { replyErr("motors_busy"); return; }
      auto_level_ = false;                          // plaque immobile pendant l'apprentissage
      for (int i = 0; i < n_tilt_; ++i) learner_[i].start();
      learning_ = true;
      replyOk();
      return;
    case CmdType::CalTiltThermClear: {
      int i0, i1;
      if (!targetSensors(c.axis, &i0, &i1)) { replyErr("no_such_sensor"); return; }
      for (int i = i0; i <= i1; ++i) {
        learner_[i].stop();
        rebaseBias(&settings_.sens[i], ThermalComp(), isnan(ch_[i].T) ? 20.0f : ch_[i].T);
      }
      learning_ = false;
      for (int i = 0; i < n_tilt_; ++i) learning_ = learning_ || learner_[i].active();
      resetTiltAverages();
      replyOk();
      return;
    }
    case CmdType::CalTiltThermFit: {
      int i0, i1;
      if (!targetSensors(c.axis, &i0, &i1)) { replyErr("no_such_sensor"); return; }
      const int order = static_cast<int>(c.f[0]);
      ThermalLearner::Status first_err = ThermalLearner::Status::Ok;
      int n_ok = 0;
      j.beginObject().kv("ok", true).key("fit").beginArray();
      for (int i = i0; i <= i1; ++i) {
        if (!learner_[i].active()) continue;
        ThermalComp th;
        float rms[2] = {0, 0};
        const ThermalLearner::Status st =
            learner_[i].fit(order, THERM_MIN_SAMPLES, THERM_MIN_SPAN_K, &th, rms);
        if (st != ThermalLearner::Status::Ok) { if (first_err == ThermalLearner::Status::Ok) first_err = st; continue; }
        rebaseBias(&settings_.sens[i], th, isnan(ch_[i].T) ? th.t_ref_C : ch_[i].T);       // la sortie corrigée reste continue à la température courante
        learner_[i].stop();
        ++n_ok;
        j.beginArray().value(static_cast<int32_t>(i)).value(th.c1[0], 3).value(th.c1[1], 3)
            .value(th.c2[0], 4).value(th.c2[1], 4).value(rms[0], 3).value(rms[1], 3)
            .value(learner_[i].spanK(), 2).endArray();
      }
      j.endArray().endObject();
      learning_ = false;
      for (int i = 0; i < n_tilt_; ++i) learning_ = learning_ || learner_[i].active();
      if (n_ok == 0) {
        replyErr(first_err == ThermalLearner::Status::SpanTooSmall ? "span_too_small"
                 : first_err == ThermalLearner::Status::Singular ? "singular"
                 : first_err == ThermalLearner::Status::TooFewSamples ? "too_few_samples" : "not_learning");
        return;
      }
      resetTiltAverages();
      sendLine(buf);
      return;
    }

    // ---- retournement motorisé
    case CmdType::FlipRun: {
#ifndef USE_FLIP_ACTUATOR
      replyErr("no_flip_hardware");
      return;
#else
      if (safety_.fanSafe()) { replyErr("safe_state"); return; }
      if (flip_.active()) { replyErr("flip_busy"); return; }
      if (lvl_.busy()) { replyErr("motors_busy"); return; }
      if (learning_) { replyErr("learning_active"); return; }
      if (FLIP_SENSOR_IDX >= n_tilt_ || !ch_[FLIP_SENSOR_IDX].valid) { replyErr("sensor_invalid"); return; }
      FlipConfig fc = flip_.config();
      fc.avg_ms = c.f[0] > 0.0f ? static_cast<uint32_t>(c.f[0] * 1000.0f) : FLIP_AVG_MS;
      flip_.configure(fc);
      flip_act_.clearFault();
      flip_new_sample_ = false;
      flip_.start(now_ms);
      resetTiltAverages();
      replyOk();
      return;
#endif
    }
    case CmdType::FlipAbort:
      flip_.abort();
      replyOk();
      return;
    case CmdType::FlipZero:
#ifndef USE_FLIP_ACTUATOR
      replyErr("no_flip_hardware");
      return;
#else
      if (flip_.active()) { replyErr("flip_busy"); return; }
      flip_act_.clearFault();
      flip_act_.setTarget(0.0f, now_ms);
      replyOk();
      return;
#endif
    case CmdType::FlipApply: {
      const FlipResult& r = flip_.result();
      if (!r.valid) { replyErr("no_result"); return; }
      if (!r.reliable) { replyErr("unreliable"); return; }
      settings_.sens[FLIP_SENSOR_IDX].geo.bias_x_urad = r.bias.x;
      settings_.sens[FLIP_SENSOR_IDX].geo.bias_y_urad = r.bias.y;
      resetTiltAverages();
      j.beginObject().kv("ok", true).kv("idx", static_cast<int32_t>(FLIP_SENSOR_IDX))
          .key("bias").beginArray().value(r.bias.x, 3).value(r.bias.y, 3).endArray().endObject();
      sendLine(buf);
      return;
    }
    case CmdType::CalPZero:
      if (!(mode_ == Mode::Off || (mode_ == Mode::Manual && manual_duty_ < 0.01f)) || fans_.rpmMax() > 50.0f) {
        replyErr("fan_must_be_stopped");
        return;
      }
      if (!press_.zeroOffsets()) { replyErr("zero_failed"); return; }
      for (int i = 0; i < NUM_PLENUM_SENSORS; ++i) settings_.p_offset[i] = press_.offset[i];
      settings_.nozzle_offset = press_.nozzle_offset;
      replyOk();
      return;
    case CmdType::Save:
      if (lvl_.busy()) { replyErr("motors_busy"); return; }        // pas d'écriture flash pendant un mouvement
      settings_.fan_p_full = ctl_.fan().pFull();
      if (!settings_.save()) { replyErr("nvs_failed"); return; }
      replyOk();
      return;

    // ---- table masse → pression
    case CmdType::TableClear:
      table_.clear();
      replyOk();
      return;
    case CmdType::TableAdd:
      if (!table_.add(c.f[0], c.f[1])) { replyErr("table_full_or_invalid"); return; }
      replyOk();
      return;
    case CmdType::TableH:
      table_.setHTargetUm(c.f[0]);
      replyOk();
      return;

    // ---- flux et sécurité
    case CmdType::StreamOn:
      stream_period_ms_ = static_cast<uint32_t>(1000.0f / c.f[0]);
      if (stream_period_ms_ < 10) stream_period_ms_ = 10;
      t_stream_ = now_ms;
      replyOk();
      return;
    case CmdType::StreamOff:
      stream_period_ms_ = 0;
      replyOk();
      return;
    case CmdType::Safe:
      safety_.raise(FAULT_MANUAL);
      replyOk();
      return;
    case CmdType::Clear: {
      safety_.update(safetyInputs(now_ms));      // évalue les causes avec les entrées actuelles
      if (!safety_.clear()) { replyErr("fault_active"); return; }
      lvl_.clearLimitFault();
      replyOk();
      return;
    }
    default:
      replyErr("unknown_command");
      return;
  }
}

// ============================================================================================
//  Télémétrie
// ============================================================================================

void App::streamTask(uint32_t now_ms) {
  if (!stream_period_ms_ || static_cast<uint32_t>(now_ms - t_stream_) < stream_period_ms_) return;
  t_stream_ = now_ms;
  char buf[JSON_BUF];
  JsonWriter j(buf, sizeof buf);
  writeStatus(j, false);
  if (!j.ok()) { ++dropped_; return; }              // tampon débordé : jamais de JSON tronqué
  sendLine(buf);
}

void App::writeStatus(JsonWriter& j, bool as_reply) {
  static const char* kModes[] = {"off", "manual", "run", "safe"};
  const uint32_t now = millis();
  j.beginObject();
  if (as_reply) j.kv("ok", true);
  j.kv("t", now);
  j.kv("st", kModes[static_cast<int>(mode_)]);
  j.kv("flt", static_cast<uint32_t>(safety_.latched()));
  j.key("faults").beginArray();
  for (uint16_t bit = 1; bit != 0 && bit <= FAULT_FAN_OVERSPEED; bit = static_cast<uint16_t>(bit << 1)) {
    if (safety_.latched() & bit) j.value(faultName(static_cast<Fault>(bit)));
  }
  j.endArray();
  // Pressions
  float p[NUM_PLENUM_SENSORS];
  for (int i = 0; i < NUM_PLENUM_SENSORS; ++i) p[i] = press_.valid[i] ? press_.p[i] : NAN;
  j.kvArray("p", p, NUM_PLENUM_SENSORS, 2);
  j.kv("pm", press_.n_valid ? press_.mean : NAN, 2);
  j.kv("pu", press_.uniformity_pct, 2);
  j.kv("nv", static_cast<int32_t>(press_.n_valid));
  j.kv("psp", mode_ == Mode::Regulate ? ctl_.target() : NAN, 1);
  j.kv("pr", mode_ == Mode::Regulate ? ctl_.rampedTarget() : NAN, 1);
  j.kv("set", mode_ == Mode::Regulate && ctl_.settled());
  j.kv("dpn", press_.nozzle_valid ? press_.nozzle_dp : NAN, 2);
  j.kv("q", press_.nozzle_valid ? flowM3h() : NAN, 2);
  j.kv("rho", env_.rho, 4);
  // Ventilateur(s)
  float rpm[MAX_FANS];
  for (int i = 0; i < NUM_FANS; ++i) rpm[i] = fans_.rpm(i);
  j.kvArray("rpm", rpm, NUM_FANS, 0);
  j.kv("pwm", fans_.duty() * 100.0f, 1);
  // Inclinaison : fusion + détail par capteur (tableaux plats [x0,y0,x1,y1,…], NaN si invalide)
  const float tf[2] = {tilt_valid_ ? tilt_avg_.x : NAN, tilt_valid_ ? tilt_avg_.y : NAN};
  j.kvArray("tilt", tf, 2, 2);
  float tc[2 * atc::kMaxTilt], tr[2 * atc::kMaxTilt], tb[atc::kMaxTilt];
  for (int i = 0; i < n_tilt_; ++i) {
    const TiltChannel& c = ch_[i];
    tc[2 * i] = c.valid ? c.plate.x : NAN;
    tc[2 * i + 1] = c.valid ? c.plate.y : NAN;
    tr[2 * i] = c.valid ? c.comp.x : NAN;
    tr[2 * i + 1] = c.valid ? c.comp.y : NAN;
    tb[i] = env_.Tb_valid[i] ? env_.Tb[i] : NAN;
  }
  const float traw[2] = {tr[0], tr[1]};              // compatibilité : capteur 0, brut compensé (avant biais)
  j.kvArray("traw", traw, 2, 2);
  j.kvArray("tr", tr, 2 * n_tilt_, 2);
  j.kvArray("tc", tc, 2 * n_tilt_, 2);
  j.kvArray("Tb", tb, n_tilt_, 3);
  j.kv("tu", static_cast<int32_t>(fuse_.used_mask));
  j.kv("trj", static_cast<int32_t>(fuse_.rejected_mask));
  j.kv("tn", static_cast<int32_t>(fuse_.n_used));
  j.kv("tsg", fuse_.valid ? fuse_.sigma_urad : NAN, 3);
  const float dsp[2] = {fuse_.valid ? fuse_.spread.x : NAN, fuse_.valid ? fuse_.spread.y : NAN};
  j.kvArray("dsp", dsp, 2, 2);
  j.kv("dfm", fuse_.valid ? fuse_.dev_max_urad : NAN, 2);
  j.kv("dfw", fuse_.valid && fmaxf(fuse_.spread.x, fuse_.spread.y) > TILT_DEFORM_WARN_URAD);
  j.kv("tinc", fuse_.inconsistent);
  const float crv[4] = {field_.valid ? field_.zxx : NAN, field_.valid ? field_.zxy : NAN,
                        field_.valid ? field_.zyy : NAN, field_.valid ? field_.curl : NAN};
  j.kvArray("crv", crv, 4, 1);
  j.kv("tt", (n_tilt_ > 0 && !isnan(ch_[0].T)) ? ch_[0].T : NAN, 2);
  j.kv("tok", tilt_valid_);
  j.kv("flip", flipStateName(flip_.state()));
  // Températures
  float T[4];
  for (int i = 0; i < 4; ++i) T[i] = env_.T_valid[i] ? env_.T[i] : NAN;
  j.kvArray("T", T, 4, 3);
  j.kv("pa", env_.bme_valid ? env_.p_atm_Pa * 0.01f : NAN, 1);
  j.kv("rh", env_.bme_valid ? env_.rh_pct : NAN, 1);
  if (disp_.present) {
    float d[NUM_DISP];
    for (int i = 0; i < NUM_DISP; ++i) d[i] = disp_.valid[i] ? disp_.um[i] : NAN;
    j.kvArray("disp", d, NUM_DISP, 2);
  }
  // Vérins
  j.key("stp").beginArray().value(static_cast<int32_t>(lvl_.position(0))).value(static_cast<int32_t>(lvl_.position(1))).endArray();
  j.kv("home", static_cast<int32_t>(lvl_.homeState()));
  j.kv("auto", auto_level_);
  j.kv("lbusy", lvl_.busy());
  j.kv("drop", static_cast<uint32_t>(dropped_));
  j.endObject();
}

void App::writeConfig(JsonWriter& j) {
  j.beginObject().kv("ok", true);
  j.kv("p_min", DESIGN_P_MIN_PA, 1).kv("p_max", DESIGN_P_MAX_PA, 1).kv("fans", static_cast<int32_t>(NUM_FANS));
  j.kv("p_full", ctl_.fan().pFull(), 1).kv("kp_norm", ctl_.config().kp_norm, 3).kv("ti", ctl_.config().ti_s, 3);
  j.kv("cd", settings_.nozzle_cd, 3).kv("nozzle_mm", settings_.nozzle_diam_mm, 2);
  const LevelGeometry& g = lvl_.geometry();
  const float tgt[2] = {level_.target().x, level_.target().y};
  j.kv("um_step", g.um_per_step[0], 5).kv("half_steps", static_cast<int32_t>(lvl_.halfRangeSteps(0)));
  j.kv("deadband", level_.config().deadband_urad, 2);
  j.kvArray("target", (const float*)tgt, 2, 2);
  float bias[2 * atc::kMaxTilt], rot[atc::kMaxTilt], c1[2 * atc::kMaxTilt], c2[2 * atc::kMaxTilt], tref[atc::kMaxTilt],
      ord[atc::kMaxTilt], pres[atc::kMaxTilt];
  for (int i = 0; i < n_tilt_; ++i) {
    const SensorCal& k = settings_.sens[i];
    bias[2 * i] = k.geo.bias_x_urad;  bias[2 * i + 1] = k.geo.bias_y_urad;
    c1[2 * i] = k.th.c1[0];           c1[2 * i + 1] = k.th.c1[1];
    c2[2 * i] = k.th.c2[0];           c2[2 * i + 1] = k.th.c2[1];
    rot[i] = k.geo.mount_rot_deg;
    tref[i] = k.th.t_ref_C;
    ord[i] = k.th.order;
    pres[i] = ch_[i].present ? 1.0f : 0.0f;
  }
  j.kv("ntilt", static_cast<int32_t>(n_tilt_));
  j.kv("tuse", static_cast<int32_t>(settings_.tilt_use_mask));
  j.kvArray("tpres", pres, n_tilt_, 0);
  j.kvArray("tilt_bias", bias, 2 * n_tilt_, 3);
  j.kvArray("tilt_rot", rot, n_tilt_, 2);
  j.kvArray("th_c1", c1, 2 * n_tilt_, 3);
  j.kvArray("th_c2", c2, 2 * n_tilt_, 4);
  j.kvArray("th_ref", tref, n_tilt_, 2);
  j.kvArray("th_ord", ord, n_tilt_, 0);
  j.kv("flip_hw", flipHardware());
  j.kv("drivers", lvl_.driversOk());
  j.kv("errs", static_cast<uint32_t>(press_.errors() + env_.errors() + mux_.errors()));
  j.endObject();
}

// ============================================================================================
//  Aides de commande
// ============================================================================================

// idx = -1 : tous les capteurs ; sinon un seul. Faux si le capteur n'existe pas dans cette configuration.
bool App::targetSensors(int idx, int* first, int* last) const {
  if (idx < 0) { *first = 0; *last = n_tilt_ - 1; return n_tilt_ > 0; }
  if (idx >= n_tilt_) return false;
  *first = *last = idx;
  return true;
}

void App::writeFlipResult(JsonWriter& j) {
  const FlipResult& r = flip_.result();
  j.beginObject().kv("ok", true).kv("hw", flipHardware()).kv("state", flipStateName(flip_.state()))
      .kv("err", flipErrorName(flip_.error())).kv("idx", static_cast<int32_t>(FLIP_SENSOR_IDX))
      .kv("valid", r.valid).kv("reliable", r.reliable);
  const float bias[2] = {r.bias.x, r.bias.y}, slope[2] = {r.slope.x, r.slope.y}, drift[2] = {r.drift.x, r.drift.y};
  if (r.valid) {
    j.kvArray("bias", bias, 2, 3).kvArray("slope", slope, 2, 3).kvArray("drift", drift, 2, 3);
    j.kv("T_mean", r.t_mean_C, 2).kv("na", static_cast<int32_t>(r.n_a)).kv("nb", static_cast<int32_t>(r.n_b));
  }
  j.endObject();
}
