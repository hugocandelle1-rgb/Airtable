#include "fan.h"

#include <esp_timer.h>

#if !defined(ESP_ARDUINO_VERSION_MAJOR)
#define ESP_ARDUINO_VERSION_MAJOR 2
#endif

static portMUX_TYPE g_tach_mux = portMUX_INITIALIZER_UNLOCKED;

void IRAM_ATTR Fan::onEdge(void* arg) {
  Fan* f = static_cast<Fan*>(arg);
  const uint32_t t = static_cast<uint32_t>(esp_timer_get_time());
  if (static_cast<uint32_t>(t - f->last_edge_us_) < FAN_TACH_MIN_EDGE_US) return;   // anti-rebond
  f->last_edge_us_ = t;
  f->edges_ = f->edges_ + 1;
}

void Fan::begin(int index) {
  idx_ = index;
  est_.configure(FAN_TACH_PULSES_PER_REV, 400000, 1500000);
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcAttach(PIN_FAN_PWM[idx_], DESIGN_FAN_PWM_HZ, FAN_LEDC_BITS);
#else
  ledcSetup(FAN_LEDC_CHANNEL[idx_], DESIGN_FAN_PWM_HZ, FAN_LEDC_BITS);
  ledcAttachPin(PIN_FAN_PWM[idx_], FAN_LEDC_CHANNEL[idx_]);
#endif
  setDuty(0.0f);
  pinMode(PIN_FAN_TACH[idx_], INPUT_PULLUP);   // pull-up externe 10 kΩ recommandée en plus
  attachInterruptArg(digitalPinToInterrupt(PIN_FAN_TACH[idx_]), Fan::onEdge, this, FALLING);
}

void Fan::setDuty(float d) {
  if (!(d > 0.0f)) d = 0.0f;               // couvre aussi NAN
  if (d > 1.0f) d = 1.0f;
  duty_ = d;
  const uint32_t maxv = (1UL << FAN_LEDC_BITS) - 1;
  const uint32_t v = static_cast<uint32_t>(d * static_cast<float>(maxv) + 0.5f);
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcWrite(PIN_FAN_PWM[idx_], v);
#else
  ledcWrite(FAN_LEDC_CHANNEL[idx_], v);
#endif
}

void Fan::updateRpm(uint32_t now_us) {
  uint32_t count, last;
  portENTER_CRITICAL(&g_tach_mux);
  count = edges_;
  last = last_edge_us_;
  portEXIT_CRITICAL(&g_tach_mux);
  est_.sample(now_us, count, last);
}

void FanBank::begin() {
  for (int i = 0; i < NUM_FANS; ++i) fans_[i].begin(i);
}

void FanBank::setDuty(float duty) {
  duty_ = duty;
  for (int i = 0; i < NUM_FANS; ++i) fans_[i].setDuty(duty);
}

void FanBank::updateRpm(uint32_t now_us) {
  for (int i = 0; i < NUM_FANS; ++i) fans_[i].updateRpm(now_us);
}

float FanBank::rpmMin() const {
  float m = fans_[0].rpm();
  for (int i = 1; i < NUM_FANS; ++i) if (fans_[i].rpm() < m) m = fans_[i].rpm();
  return m;
}

float FanBank::rpmMax() const {
  float m = fans_[0].rpm();
  for (int i = 1; i < NUM_FANS; ++i) if (fans_[i].rpm() > m) m = fans_[i].rpm();
  return m;
}
