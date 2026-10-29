#include "level_actuators.h"

#include <TMCStepper.h>

#include "hw_gpio.h"

#if !defined(ESP_ARDUINO_VERSION_MAJOR)
#define ESP_ARDUINO_VERSION_MAJOR 2
#endif

using namespace atc;

static TMC2209Stepper g_tmc0(&Serial1, TMC_R_SENSE, TMC_ADDR[0]);
static TMC2209Stepper g_tmc1(&Serial1, TMC_R_SENSE, TMC_ADDR[1]);
static TMC2209Stepper* const g_tmc[2] = {&g_tmc0, &g_tmc1};
static LevelActuators* g_inst = nullptr;
static hw_timer_t* g_timer = nullptr;

constexpr int32_t kSwitchMarginSteps = 1000;   // le fin de course est 1000 µpas au-delà de la limite logicielle

bool LevelActuators::begin() {
  g_inst = this;
  StepperMech mech;
  mech.screw_pitch_mm = LEVEL_SCREW_PITCH_MM;
  mech.gear_ratio = LEVEL_GEAR_RATIO;
  mech.full_steps_per_rev = LEVEL_FULL_STEPS;
  mech.microsteps = LEVEL_MICROSTEPS;
  for (int i = 0; i < 2; ++i) {
    geom_.x_mm[i] = LEVEL_ACT_X_MM[i];
    geom_.y_mm[i] = LEVEL_ACT_Y_MM[i];
    geom_.um_per_step[i] = mech.umPerMicrostep();
    // Levée maximale pour une pente de ±DESIGN_LEVEL_RANGE_URAD sur les deux axes
    const float lift_um = DESIGN_LEVEL_RANGE_URAD * (fabsf(geom_.x_mm[i]) + fabsf(geom_.y_mm[i])) * 1e-3f;
    half_[i] = static_cast<int32_t>(lift_um / geom_.um_per_step[i]);
    gen_[i].configure(LEVEL_STEP_TICK_HZ, LEVEL_VMAX_SPS, LEVEL_ACCEL_SPS2);
  }
  dec_ = buildDecoupling(geom_);

  pinMode(PIN_MOTOR_EN, OUTPUT);
  digitalWrite(PIN_MOTOR_EN, HIGH);              // drivers désactivés pendant la configuration
  for (int i = 0; i < 2; ++i) {
    pinMode(PIN_STEP[i], OUTPUT);
    pinMode(PIN_DIR[i], OUTPUT);
    digitalWrite(PIN_STEP[i], LOW);
    digitalWrite(PIN_DIR[i], LOW);
    pinMode(PIN_LIMIT[i], INPUT_PULLUP);
  }

  Serial1.begin(115200, SERIAL_8N1, PIN_TMC_RX, PIN_TMC_TX);
  drivers_ok_ = true;
  for (int i = 0; i < 2; ++i) {
    TMC2209Stepper& d = *g_tmc[i];
    d.begin();
    d.toff(5);
    d.blank_time(24);
    d.pdn_disable(true);                         // UART sur PDN_UART
    d.I_scale_analog(false);                     // courant réglé par UART, pas par le potentiomètre
    d.mstep_reg_select(true);                    // micro-pas par registre
    d.rms_current(LEVEL_TMC_RUN_MA, LEVEL_TMC_HOLD_MULT);
    d.microsteps(LEVEL_MICROSTEPS);
    d.en_spreadCycle(false);                     // StealthChop : silencieux, sans vibration parasite
    d.pwm_autoscale(true);
    d.TPOWERDOWN(20);
    if (d.test_connection() != 0) drivers_ok_ = false;   // 0 = communication OK
  }

#if ESP_ARDUINO_VERSION_MAJOR >= 3
  g_timer = timerBegin(1000000);
  timerAttachInterrupt(g_timer, &LevelActuators::onTimer);
  timerAlarm(g_timer, 1000000UL / LEVEL_STEP_TICK_HZ, true, 0);
#else
  g_timer = timerBegin(1, 80, true);             // 80 MHz / 80 = 1 µs
  timerAttachInterrupt(g_timer, &LevelActuators::onTimer, true);
  timerAlarmWrite(g_timer, 1000000UL / LEVEL_STEP_TICK_HZ, true);
  timerAlarmEnable(g_timer);
#endif
  timer_started_ = true;
  if (drivers_ok_) enableDrivers(true);
  return drivers_ok_;
}

void LevelActuators::enableDrivers(bool on) { digitalWrite(PIN_MOTOR_EN, on ? LOW : HIGH); }

bool LevelActuators::limitActive(int i) const {
  const bool lvl = digitalRead(PIN_LIMIT[i]) != 0;
  return LIMIT_ACTIVE_LOW ? !lvl : lvl;
}

// ---- interruption de pas (20 kHz) ----------------------------------------------------------

void IRAM_ATTR LevelActuators::onTimer() {
  if (g_inst) g_inst->isrTick();
}

void IRAM_ATTR LevelActuators::isrTick() {
  for (int i = 0; i < 2; ++i) {
    if (pulse_[i]) {                             // fin d'impulsion : largeur = 1 tick = 50 µs
      gpioFastWrite(PIN_STEP[i], false);
      pulse_[i] = false;
    }
    StepGen& g = gen_[i];
    const bool lvl = gpioFastRead(PIN_LIMIT[i]);
    const bool lim = LIMIT_ACTIVE_LOW ? !lvl : lvl;
    // Le fin de course est du côté négatif : tout mouvement vers lui est interdit.
    if (lim && (g.target() < g.position() || (g.dir() < 0 && g.speedSps() > 0))) {
      g.emergencyStop();
      limit_seen_[i] = true;
    }
    const bool step = g.tick();
    gpioFastWrite(PIN_DIR[i], (g.dir() > 0) != DIR_INVERT[i]);
    if (step) {
      gpioFastWrite(PIN_STEP[i], true);
      pulse_[i] = true;
    }
  }
}

// ---- commandes de mouvement ----------------------------------------------------------------

bool LevelActuators::busy() const { return gen_[0].busy() || gen_[1].busy(); }

uint32_t LevelActuators::moveSlope(Vec2 ds) {
  if (!homed() || inhibit_ || !dec_.valid) return 0;
  int32_t st[2];
  slopeToSteps(dec_, geom_, ds, st);
  uint32_t dur = 0;
  for (int i = 0; i < 2; ++i) {
    int32_t tgt = gen_[i].target() + st[i];
    clampSteps(&tgt, -half_[i], half_[i]);
    const int32_t d = tgt - gen_[i].position();
    gen_[i].moveTo(tgt);
    const uint32_t ms = gen_[i].estimateMs(static_cast<uint32_t>(d < 0 ? -d : d));
    if (ms > dur) dur = ms;
  }
  return dur ? dur : 1;
}

uint32_t LevelActuators::jog(int idx, float um) {
  if (!homed() || inhibit_ || idx < 0 || idx > 1) return 0;
  int32_t tgt = gen_[idx].target() + micronsToSteps(um, geom_.um_per_step[idx]);
  clampSteps(&tgt, -half_[idx], half_[idx]);
  const int32_t d = tgt - gen_[idx].position();
  gen_[idx].moveTo(tgt);
  return gen_[idx].estimateMs(static_cast<uint32_t>(d < 0 ? -d : d)) + 1;
}

uint32_t LevelActuators::goZero() {
  if (!homed() || inhibit_) return 0;
  uint32_t dur = 0;
  for (int i = 0; i < 2; ++i) {
    const int32_t d = gen_[i].position();
    gen_[i].moveTo(0);
    const uint32_t ms = gen_[i].estimateMs(static_cast<uint32_t>(d < 0 ? -d : d));
    if (ms > dur) dur = ms;
  }
  return dur ? dur : 1;
}

void LevelActuators::stop() {
  for (int i = 0; i < 2; ++i) gen_[i].stop();
  if (home_ == Home::Seek || home_ == Home::Center) home_ = Home::Idle;
}

void LevelActuators::emergencyStop() {
  for (int i = 0; i < 2; ++i) gen_[i].emergencyStop();
  if (home_ == Home::Seek || home_ == Home::Center) home_ = Home::Idle;
}

void LevelActuators::setInhibit(bool inhibit) {
  if (inhibit && !inhibit_) emergencyStop();
  inhibit_ = inhibit;
}

Vec2 LevelActuators::slopeFromCenter() const {
  const int32_t p[2] = {gen_[0].position(), gen_[1].position()};
  return stepsToSlope(dec_, geom_, p);
}

// ---- prise d'origine et surveillance ---------------------------------------------------------

void LevelActuators::startHoming() {
  if (inhibit_ || !drivers_ok_) return;
  limit_fault_ = false;
  found_[0] = found_[1] = false;
  limit_seen_[0] = limit_seen_[1] = false;
  home_t0_ = millis();
  for (int i = 0; i < 2; ++i) {
    gen_[i].setMaxSpeed(LEVEL_HOMING_SPS);
    gen_[i].moveTo(gen_[i].position() - 4 * half_[i]);   // vers le fin de course (côté négatif)
  }
  home_ = Home::Seek;
}

void LevelActuators::service(uint32_t now_ms) {
  switch (home_) {
    case Home::Seek: {
      for (int i = 0; i < 2; ++i) {
        if (!found_[i] && limit_seen_[i]) {
          found_[i] = true;
          limit_seen_[i] = false;
          noInterrupts();                         // l'ISR a déjà arrêté ce vérin ; on redéfinit l'origine
          gen_[i].setPosition(-(half_[i] + kSwitchMarginSteps));
          interrupts();
          gen_[i].setMaxSpeed(LEVEL_VMAX_SPS);
          gen_[i].moveTo(0);                      // sort du fin de course vers le centre
        }
      }
      if (found_[0] && found_[1]) home_ = Home::Center;
      // Temporisation : 4 × course à vitesse de recherche + marge
      const uint32_t max_ms = 10000UL + static_cast<uint32_t>(4000ULL * half_[0] / LEVEL_HOMING_SPS);
      if (now_ms - home_t0_ > max_ms) { emergencyStop(); home_ = Home::Failed; }
      break;
    }
    case Home::Center:
      if (!busy()) home_ = Home::Done;
      break;
    default:
      break;
  }
  // Fin de course atteint hors prise d'origine : défaut (les moteurs sont déjà arrêtés par l'ISR)
  if (home_ != Home::Seek) {
    for (int i = 0; i < 2; ++i) {
      if (limit_seen_[i]) { limit_fault_ = true; limit_seen_[i] = false; }
    }
  }
}
