// Analyse des lignes de commande du protocole série (une commande par ligne, insensible à
// la casse). Logique pure : le résultat est un objet Command exécuté par le firmware.
//
//   PING | GET STATUS|CONFIG|VERSION|TABLE | CLEAR | SAFE | SAVE
//   SET P <Pa> | SET MASS <g> | SET DUTY <0..1> | SET RAMP <Pa/s> | SET GAINS <kp_norm> <ti_s>
//   SET NOZZLE <Cd> <d_mm> | SET WDT <s>
//   FAN ON|OFF
//   LEVEL AUTO ON|OFF | LEVEL MOVE X|Y <µrad> | LEVEL ZERO | LEVEL HOME | LEVEL STOP
//   LEVEL TARGET <x µrad> <y µrad> | LEVEL DEADBAND <µrad> | LEVEL JOG A|B <µm>
//   CAL TILT BIAS <x µrad> <y µrad> [idx] | CAL TILT ROT <deg> [idx] | CAL TILT CLEAR [idx] | CAL PZERO
//   CAL TILT USE <idx> ON|OFF                       (exclut / réintègre un capteur de la fusion)
//   CAL TILT THERM START | CAL TILT THERM FIT <ordre 1|2> [idx] | CAL TILT THERM CLEAR [idx]
//   FLIP RUN [<durée de mesure par position, s>] | FLIP ABORT | FLIP ZERO | FLIP APPLY | GET FLIP
//   (idx = numéro de capteur 0…3 ; absent = tous les capteurs, Command.axis = -1)
//   TABLE CLEAR | TABLE ADD <mass_g> <p_Pa> | TABLE H <h_um>
//   STREAM ON <Hz> | STREAM OFF
#pragma once
#include <stddef.h>

namespace atc {

enum class CmdType {
  None,
  Ping, GetStatus, GetConfig, GetVersion, GetTable, GetFlip,
  SetP, SetMass, SetDuty, SetRamp, SetGains, SetNozzle, SetWdt,
  FanOn, FanOff,
  LevelAuto, LevelMove, LevelZero, LevelHome, LevelStop, LevelTarget, LevelDeadband, LevelJog,
  CalTiltBias, CalTiltRot, CalTiltClear, CalTiltUse, CalTiltThermStart, CalTiltThermFit, CalTiltThermClear,
  CalPZero,
  FlipRun, FlipAbort, FlipZero, FlipApply,
  TableClear, TableAdd, TableH,
  StreamOn, StreamOff,
  Clear, Safe, Save
};

struct Command {
  CmdType type = CmdType::None;
  float f[2] = {0.0f, 0.0f};   // arguments numériques
  int axis = 0;                // 0 = X / A, 1 = Y / B ; numéro de capteur (0…3, -1 = tous) pour CAL TILT / FLIP
  bool flag = false;           // ON/OFF
};

enum class ParseError {
  Ok = 0, Empty, TooLong, UnknownCommand, MissingArg, ExtraArg, BadNumber, OutOfRange, BadAxis, BadFlag
};

constexpr size_t kMaxLineLen = 120;
constexpr int kMaxSensorIdx = 3;   // = kMaxTilt − 1 (atcore/tilt_array.h)

ParseError parseCommand(const char* line, Command* out);
const char* parseErrorText(ParseError e);

}  // namespace atc
