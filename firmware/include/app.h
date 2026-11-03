// Application : ordonnanceur coopératif, régulation, sécurités et protocole série.
#pragma once
#include <Arduino.h>

#include "atcore/commands.h"
#include "atcore/filters.h"
#include "atcore/inclinometer.h"
#include "atcore/json.h"
#include "atcore/leveling.h"
#include "atcore/pressure_controller.h"
#include "atcore/safety.h"
#include "atcore/tilt_array.h"
#include "atcore/setpoints.h"
#include "config.h"
#include "displacement_sensors.h"
#include "env_sensors.h"
#include "fan.h"
#include "flip_actuator.h"
#include "i2c_bus.h"
#include "inclinometer_drivers.h"
#include "level_actuators.h"
#include "pressure_sensors.h"
#include "settings.h"

class App {
 public:
  enum class Mode : uint8_t { Off, Manual, Regulate, Safe };

  void begin();
  void tick();                          // à appeler en boucle ; ne bloque jamais

 private:
  // --- tâches périodiques
  void controlTask(uint32_t now_ms);
  void tiltPoll();
  void tiltTask(uint32_t now_ms);
  void flipTask(uint32_t now_ms);
  void levelTask(uint32_t now_ms);
  void ledTask(uint32_t now_ms);
  void streamTask(uint32_t now_ms);
  // --- liaison série
  void pollSerial(uint32_t now_ms);
  void handleLine(const char* line, uint32_t now_ms);
  void execute(const atc::Command& c, uint32_t now_ms);
  void replyOk();
  void replyErr(const char* msg);
  void sendLine(const char* s);
  void writeStatus(atc::JsonWriter& j, bool as_reply);
  void writeConfig(atc::JsonWriter& j);
  // --- aides
  atc::SafetyInputs safetyInputs(uint32_t now_ms) const;
  bool startRegulation(float p_Pa, const char** err);
  float flowM3h() const;
  void applySettings();
  static constexpr bool flipHardware() {
#ifdef USE_FLIP_ACTUATOR
    return true;
#else
    return false;
#endif
  }
  bool flipBusy() const;                // séquence en cours ou embase hors de 0° : nivellement et étalonnages gelés
  bool flipExcludesSensor(uint32_t now_ms);   // le capteur retournable est exclu de la fusion (pendant et après la séquence)
  bool targetSensors(int idx, int* first, int* last) const;   // idx = -1 → tous les capteurs présents
  void resetTiltAverages();
  void writeFlipResult(atc::JsonWriter& j);

  // matériel
  Tca9548a mux_;
  PressureSensors press_;
  EnvSensors env_;
  FanBank fans_;
  LevelActuators lvl_;
#ifdef USE_SCL3300
  Scl3300Driver drv_[1] = {Scl3300Driver(SPI, PIN_CS_TILT[0])};
#else
  Adxl355Driver drv_[TILT_MAX_SENSORS] = {Adxl355Driver(SPI, PIN_CS_TILT[0]), Adxl355Driver(SPI, PIN_CS_TILT[1]),
                                          Adxl355Driver(SPI, PIN_CS_TILT[2]), Adxl355Driver(SPI, PIN_CS_TILT[3])};
#endif
  // Un canal par accéléromètre : échantillon brut, température de la base, sortie corrigée
  struct TiltChannel {
    atc::Inclinometer* drv = nullptr;
    bool present = false;           // répondait au démarrage
    bool have = false;              // au moins un échantillon reçu
    bool valid = false;             // échantillon récent, sain et température disponible si le modèle thermique est actif
    uint32_t last_ok_ms = 0;
    atc::TiltSample s;              // dernier échantillon (brut, repère capteur)
    float T = NAN;                  // température de la base [°C]
    atc::Vec2 comp;                 // brut compensé thermiquement (avant biais/rotation)
    atc::Vec2 plate;                // pente dans le repère plaque (biais, rotation, signes appliqués)
    atc::RunningSigma sd;
  };
  TiltChannel ch_[atc::kMaxTilt];
  int n_tilt_ = 0;
  atc::FuseConfig fuse_cfg_;
  atc::FuseResult fuse_;
  atc::SlopeField field_;
  uint8_t used_prev_ = 0;
  atc::ThermalLearner learner_[atc::kMaxTilt];
  bool learning_ = false;
  FlipActuator flip_act_;
  atc::FlipSequencer flip_;
  bool flip_new_sample_ = false;
  uint32_t flip_last_busy_ms_ = 0;      // dernier instant où l'embase était hors de 0° ou en mouvement
  DisplacementSensors disp_;

  // logique
  atc::PressureController ctl_;
  atc::SetpointTable table_;
  atc::Safety safety_;
  atc::LevelController level_;
  Settings settings_;

  // état
  Mode mode_ = Mode::Off;
  float manual_duty_ = 0.0f;
  float mass_g_ = 0.0f;
  bool auto_level_ = false;
  atc::Vec2 tilt_plate_{0.0f, 0.0f};      // pente plaque fusionnée instantanée (10 Hz)
  atc::MovingAverage<64> avg_x_, avg_y_;  // moyenne glissante pour la boucle de nivellement
  atc::Vec2 tilt_avg_{0.0f, 0.0f};
  uint32_t tilt_last_ok_ms_ = 0;
  bool tilt_valid_ = false;
  uint32_t last_host_ms_ = 0;
  bool inhibited_prev_ = false;

  // ordonnancement
  uint32_t t_pressure_ = 0, t_control_ = 0, t_tach_ = 0, t_tilt_poll_ = 0, t_tilt_out_ = 0;
  uint32_t t_env_ = 0, t_level_ = 0, t_led_ = 0, t_stream_ = 0;
  uint32_t last_control_ms_ = 0;
  uint32_t stream_period_ms_ = 0;         // 0 = flux arrêté
  uint32_t dropped_ = 0;

  char line_[SERIAL_LINE_MAX + 2];
  size_t line_len_ = 0;
  bool line_overflow_ = false;
};
