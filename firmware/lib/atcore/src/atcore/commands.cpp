#include "atcore/commands.h"

#include <ctype.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>

namespace atc {

namespace {

constexpr int kMaxTok = 6;

struct Tokens {
  char buf[kMaxLineLen + 1];
  const char* t[kMaxTok];
  int n = 0;
};

bool tokenize(const char* line, Tokens* tk, ParseError* err) {
  const size_t len = strlen(line);
  if (len > kMaxLineLen) { *err = ParseError::TooLong; return false; }
  memcpy(tk->buf, line, len + 1);
  char* p = tk->buf;
  while (*p) {
    while (*p && isspace(static_cast<unsigned char>(*p))) ++p;
    if (!*p) break;
    if (tk->n >= kMaxTok) { *err = ParseError::ExtraArg; return false; }
    tk->t[tk->n++] = p;
    while (*p && !isspace(static_cast<unsigned char>(*p))) { *p = static_cast<char>(toupper(static_cast<unsigned char>(*p))); ++p; }
    if (*p) *p++ = '\0';
  }
  if (tk->n == 0) { *err = ParseError::Empty; return false; }
  return true;
}

bool is(const char* tok, const char* word) { return strcmp(tok, word) == 0; }

ParseError number(const char* tok, float lo, float hi, float* out) {
  char* end = nullptr;
  const double v = strtod(tok, &end);
  if (end == tok || *end != '\0' || !isfinite(v)) return ParseError::BadNumber;
  if (v < lo || v > hi) return ParseError::OutOfRange;
  *out = static_cast<float>(v);
  return ParseError::Ok;
}

ParseError flag(const char* tok, bool* out) {
  if (is(tok, "ON") || is(tok, "1") || is(tok, "TRUE")) { *out = true; return ParseError::Ok; }
  if (is(tok, "OFF") || is(tok, "0") || is(tok, "FALSE")) { *out = false; return ParseError::Ok; }
  return ParseError::BadFlag;
}

// Vérifie le nombre de jetons (n total, mot-clé de tête compris).
ParseError need(const Tokens& k, int n) {
  if (k.n < n) return ParseError::MissingArg;
  if (k.n > n) return ParseError::ExtraArg;
  return ParseError::Ok;
}

}  // namespace

ParseError parseCommand(const char* line, Command* out) {
  if (!line || !out) return ParseError::Empty;
  *out = Command();
  Tokens k;
  ParseError err = ParseError::Ok;
  if (!tokenize(line, &k, &err)) return err;
  const char* c0 = k.t[0];

  auto simple = [&](CmdType t, int ntok) {
    err = need(k, ntok);
    if (err == ParseError::Ok) out->type = t;
    return err;
  };

  if (is(c0, "PING")) return simple(CmdType::Ping, 1);
  if (is(c0, "CLEAR")) return simple(CmdType::Clear, 1);
  if (is(c0, "SAFE")) return simple(CmdType::Safe, 1);
  if (is(c0, "SAVE")) return simple(CmdType::Save, 1);

  if (is(c0, "GET")) {
    if (k.n < 2) return ParseError::MissingArg;
    if (is(k.t[1], "STATUS")) return simple(CmdType::GetStatus, 2);
    if (is(k.t[1], "CONFIG")) return simple(CmdType::GetConfig, 2);
    if (is(k.t[1], "VERSION")) return simple(CmdType::GetVersion, 2);
    if (is(k.t[1], "TABLE")) return simple(CmdType::GetTable, 2);
    return ParseError::UnknownCommand;
  }

  if (is(c0, "SET")) {
    if (k.n < 2) return ParseError::MissingArg;
    const char* s = k.t[1];
    if (is(s, "P")) { if ((err = need(k, 3)) != ParseError::Ok) return err; out->type = CmdType::SetP; return number(k.t[2], 0.0f, 1000.0f, &out->f[0]); }
    if (is(s, "MASS")) { if ((err = need(k, 3)) != ParseError::Ok) return err; out->type = CmdType::SetMass; return number(k.t[2], 0.01f, 1000.0f, &out->f[0]); }
    if (is(s, "DUTY")) { if ((err = need(k, 3)) != ParseError::Ok) return err; out->type = CmdType::SetDuty; return number(k.t[2], 0.0f, 1.0f, &out->f[0]); }
    if (is(s, "RAMP")) { if ((err = need(k, 3)) != ParseError::Ok) return err; out->type = CmdType::SetRamp; return number(k.t[2], 0.1f, 5000.0f, &out->f[0]); }
    if (is(s, "WDT")) { if ((err = need(k, 3)) != ParseError::Ok) return err; out->type = CmdType::SetWdt; return number(k.t[2], 0.0f, 3600.0f, &out->f[0]); }
    if (is(s, "GAINS")) {
      if ((err = need(k, 4)) != ParseError::Ok) return err;
      out->type = CmdType::SetGains;
      if ((err = number(k.t[2], 0.0f, 10.0f, &out->f[0])) != ParseError::Ok) return err;
      return number(k.t[3], 0.05f, 100.0f, &out->f[1]);
    }
    if (is(s, "NOZZLE")) {
      if ((err = need(k, 4)) != ParseError::Ok) return err;
      out->type = CmdType::SetNozzle;
      if ((err = number(k.t[2], 0.1f, 1.2f, &out->f[0])) != ParseError::Ok) return err;
      return number(k.t[3], 0.5f, 200.0f, &out->f[1]);
    }
    return ParseError::UnknownCommand;
  }

  if (is(c0, "FAN")) {
    if ((err = need(k, 2)) != ParseError::Ok) return err;
    bool on;
    if ((err = flag(k.t[1], &on)) != ParseError::Ok) return err;
    out->type = on ? CmdType::FanOn : CmdType::FanOff;
    return ParseError::Ok;
  }

  if (is(c0, "STREAM")) {
    if (k.n < 2) return ParseError::MissingArg;
    if (is(k.t[1], "OFF")) return simple(CmdType::StreamOff, 2);
    if (is(k.t[1], "ON")) {
      if (k.n == 2) { out->type = CmdType::StreamOn; out->f[0] = 10.0f; return ParseError::Ok; }
      if ((err = need(k, 3)) != ParseError::Ok) return err;
      out->type = CmdType::StreamOn;
      return number(k.t[2], 0.1f, 100.0f, &out->f[0]);
    }
    return ParseError::BadFlag;
  }

  if (is(c0, "TABLE")) {
    if (k.n < 2) return ParseError::MissingArg;
    if (is(k.t[1], "CLEAR")) return simple(CmdType::TableClear, 2);
    if (is(k.t[1], "H")) { if ((err = need(k, 3)) != ParseError::Ok) return err; out->type = CmdType::TableH; return number(k.t[2], 0.0f, 1000.0f, &out->f[0]); }
    if (is(k.t[1], "ADD")) {
      if ((err = need(k, 4)) != ParseError::Ok) return err;
      out->type = CmdType::TableAdd;
      if ((err = number(k.t[2], 0.01f, 1000.0f, &out->f[0])) != ParseError::Ok) return err;
      return number(k.t[3], 0.0f, 2000.0f, &out->f[1]);
    }
    return ParseError::UnknownCommand;
  }

  if (is(c0, "LEVEL")) {
    if (k.n < 2) return ParseError::MissingArg;
    const char* s = k.t[1];
    if (is(s, "ZERO")) return simple(CmdType::LevelZero, 2);
    if (is(s, "HOME")) return simple(CmdType::LevelHome, 2);
    if (is(s, "STOP")) return simple(CmdType::LevelStop, 2);
    if (is(s, "AUTO")) {
      if ((err = need(k, 3)) != ParseError::Ok) return err;
      out->type = CmdType::LevelAuto;
      return flag(k.t[2], &out->flag);
    }
    if (is(s, "MOVE") || is(s, "JOG")) {
      if ((err = need(k, 4)) != ParseError::Ok) return err;
      const bool move = is(s, "MOVE");
      const char* ax = k.t[2];
      if (move && is(ax, "X")) out->axis = 0;
      else if (move && is(ax, "Y")) out->axis = 1;
      else if (!move && is(ax, "A")) out->axis = 0;
      else if (!move && is(ax, "B")) out->axis = 1;
      else return ParseError::BadAxis;
      out->type = move ? CmdType::LevelMove : CmdType::LevelJog;
      return number(k.t[3], -5000.0f, 5000.0f, &out->f[0]);
    }
    if (is(s, "TARGET")) {
      if ((err = need(k, 4)) != ParseError::Ok) return err;
      out->type = CmdType::LevelTarget;
      if ((err = number(k.t[2], -5000.0f, 5000.0f, &out->f[0])) != ParseError::Ok) return err;
      return number(k.t[3], -5000.0f, 5000.0f, &out->f[1]);
    }
    if (is(s, "DEADBAND")) {
      if ((err = need(k, 3)) != ParseError::Ok) return err;
      out->type = CmdType::LevelDeadband;
      return number(k.t[2], 0.1f, 1000.0f, &out->f[0]);
    }
    return ParseError::UnknownCommand;
  }

  if (is(c0, "CAL")) {
    if (k.n < 2) return ParseError::MissingArg;
    if (is(k.t[1], "PZERO")) return simple(CmdType::CalPZero, 2);
    if (is(k.t[1], "TILT")) {
      if (k.n < 3) return ParseError::MissingArg;
      if (is(k.t[2], "CLEAR")) return simple(CmdType::CalTiltClear, 3);
      if (is(k.t[2], "ROT")) { if ((err = need(k, 4)) != ParseError::Ok) return err; out->type = CmdType::CalTiltRot; return number(k.t[3], -360.0f, 360.0f, &out->f[0]); }
      if (is(k.t[2], "BIAS")) {
        if ((err = need(k, 5)) != ParseError::Ok) return err;
        out->type = CmdType::CalTiltBias;
        if ((err = number(k.t[3], -50000.0f, 50000.0f, &out->f[0])) != ParseError::Ok) return err;
        return number(k.t[4], -50000.0f, 50000.0f, &out->f[1]);
      }
    }
    return ParseError::UnknownCommand;
  }

  return ParseError::UnknownCommand;
}

const char* parseErrorText(ParseError e) {
  switch (e) {
    case ParseError::Ok: return "ok";
    case ParseError::Empty: return "empty";
    case ParseError::TooLong: return "line_too_long";
    case ParseError::UnknownCommand: return "unknown_command";
    case ParseError::MissingArg: return "missing_argument";
    case ParseError::ExtraArg: return "extra_argument";
    case ParseError::BadNumber: return "bad_number";
    case ParseError::OutOfRange: return "out_of_range";
    case ParseError::BadAxis: return "bad_axis";
    case ParseError::BadFlag: return "bad_flag";
  }
  return "error";
}

}  // namespace atc
