// Lit des lignes sur stdin, applique atc::parseCommand et écrit le résultat (comparé au miroir Python).
#include <cstdio>
#include <iostream>
#include <string>

#include "atcore/commands.h"

using namespace atc;

static const char* name(CmdType t) {
  switch (t) {
    case CmdType::None: return "None";
    case CmdType::Ping: return "Ping";
    case CmdType::GetStatus: return "GetStatus";
    case CmdType::GetConfig: return "GetConfig";
    case CmdType::GetVersion: return "GetVersion";
    case CmdType::GetTable: return "GetTable";
    case CmdType::SetP: return "SetP";
    case CmdType::SetMass: return "SetMass";
    case CmdType::SetDuty: return "SetDuty";
    case CmdType::SetRamp: return "SetRamp";
    case CmdType::SetGains: return "SetGains";
    case CmdType::SetNozzle: return "SetNozzle";
    case CmdType::SetWdt: return "SetWdt";
    case CmdType::FanOn: return "FanOn";
    case CmdType::FanOff: return "FanOff";
    case CmdType::LevelAuto: return "LevelAuto";
    case CmdType::LevelMove: return "LevelMove";
    case CmdType::LevelZero: return "LevelZero";
    case CmdType::LevelHome: return "LevelHome";
    case CmdType::LevelStop: return "LevelStop";
    case CmdType::LevelTarget: return "LevelTarget";
    case CmdType::LevelDeadband: return "LevelDeadband";
    case CmdType::LevelJog: return "LevelJog";
    case CmdType::CalTiltBias: return "CalTiltBias";
    case CmdType::CalTiltRot: return "CalTiltRot";
    case CmdType::CalTiltClear: return "CalTiltClear";
    case CmdType::CalPZero: return "CalPZero";
    case CmdType::TableClear: return "TableClear";
    case CmdType::TableAdd: return "TableAdd";
    case CmdType::TableH: return "TableH";
    case CmdType::StreamOn: return "StreamOn";
    case CmdType::StreamOff: return "StreamOff";
    case CmdType::Clear: return "Clear";
    case CmdType::Safe: return "Safe";
    case CmdType::Save: return "Save";
  }
  return "?";
}

int main() {
  std::string line;
  while (std::getline(std::cin, line)) {
    Command c;
    const ParseError e = parseCommand(line.c_str(), &c);
    if (e == ParseError::Ok)
      std::printf("OK %s %.6g %.6g %d %d\n", name(c.type), c.f[0], c.f[1], c.axis, c.flag ? 1 : 0);
    else
      std::printf("ERR %s\n", parseErrorText(e));
  }
  return 0;
}
