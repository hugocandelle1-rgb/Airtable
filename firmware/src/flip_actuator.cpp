#include "flip_actuator.h"

#include "config.h"

#if !defined(ESP_ARDUINO_VERSION_MAJOR)
#define ESP_ARDUINO_VERSION_MAJOR 2
#endif

static constexpr int kServoBits = 14;
static constexpr uint32_t kServoHz = 50;

void FlipActuator::writeUs(uint32_t us) {
  const uint32_t period_us = 1000000UL / kServoHz;
  const uint32_t duty = static_cast<uint32_t>((static_cast<uint64_t>(us) * ((1UL << kServoBits) - 1)) / period_us);
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcWrite(PIN_FLIP_SERVO, duty);
#else
  ledcWrite(FLIP_LEDC_CHANNEL, duty);
#endif
}

void FlipActuator::begin() {
  pinMode(PIN_FLIP_INDEX, INPUT_PULLUP);
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcAttach(PIN_FLIP_SERVO, kServoHz, kServoBits);
#else
  ledcSetup(FLIP_LEDC_CHANNEL, kServoHz, kServoBits);
  ledcAttachPin(PIN_FLIP_SERVO, FLIP_LEDC_CHANNEL);
#endif
  writeUs(0);                                     // servo libre jusqu'à la première commande
  target_deg_ = 0.0f;
  known_ = indexActive();                         // embase déjà à 0° au démarrage ?
}

bool FlipActuator::indexActive() const {
  const bool lvl = digitalRead(PIN_FLIP_INDEX) != 0;
  return FLIP_INDEX_ACTIVE_LOW ? !lvl : lvl;
}

void FlipActuator::setTarget(float deg, uint32_t now_ms) {
  const float t = deg >= 90.0f ? 180.0f : 0.0f;
  if (t == target_deg_ && !fault_ && (moving_ || known_)) return;
  target_deg_ = t;
  moving_ = true;
  fault_ = false;
  t_start_ = now_ms;
  writeUs(t == 0.0f ? FLIP_SERVO_US_0 : FLIP_SERVO_US_180);
}

void FlipActuator::service(uint32_t now_ms) {
  if (!moving_) return;
  if (static_cast<uint32_t>(now_ms - t_start_) < FLIP_TRAVEL_MS) return;
  moving_ = false;
  release();
  const bool idx = indexActive();
  const bool ok = target_deg_ == 0.0f ? idx : !idx;
  if (ok) known_ = true;
  else fault_ = true;                              // bloqué, servo débranché ou contact défaillant
}

void FlipActuator::release() { writeUs(0); }

bool FlipActuator::atTarget() const {
  if (moving_ || fault_) return false;
  const bool idx = indexActive();
  return target_deg_ == 0.0f ? idx : !idx;
}
