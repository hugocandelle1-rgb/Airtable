"""Protocole série du banc : construction/analyse des commandes et des trames JSON.

Une commande par ligne (texte), une réponse JSON d'une ligne :
  - toute réponse à une commande contient la clé "ok" ;
  - une trame de télémétrie (STREAM ON) contient "t" et PAS "ok".

`parse_command` est le miroir Python du parseur C++ (firmware/lib/atcore/src/atcore/commands.cpp) ;
le test host/tests/test_cpp_parity.py vérifie qu'ils acceptent/rejettent les mêmes lignes.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any

MAX_LINE = 120

FAULT_NAMES = ("stall", "overpressure", "sensor_lost", "host_wdt", "limit_switch",
               "tilt_lost", "manual", "overspeed")


class ProtocolError(Exception):
    """Ligne reçue illisible ou réponse inattendue."""


class DeviceError(Exception):
    """Le firmware a répondu {"ok": false, "err": ...}."""

    def __init__(self, err: str, reply: dict | None = None):
        super().__init__(err)
        self.err = err
        self.reply = reply or {}


def fmt(x: float) -> str:
    """Nombre au format compact et sans perte utile pour le firmware."""
    if not math.isfinite(x):
        raise ValueError(f"valeur non finie : {x}")
    s = f"{x:.6g}"
    return s


# ---- construction des commandes ---------------------------------------------------------------

def cmd_set_pressure(p_pa: float) -> str:
    return f"SET P {fmt(p_pa)}"


def cmd_set_mass(m_g: float) -> str:
    return f"SET MASS {fmt(m_g)}"


def cmd_set_duty(d: float) -> str:
    return f"SET DUTY {fmt(d)}"


def cmd_level_move(axis: str, urad: float) -> str:
    axis = axis.upper()
    if axis not in ("X", "Y"):
        raise ValueError("axe X ou Y")
    return f"LEVEL MOVE {axis} {fmt(urad)}"


def cmd_level_jog(act: str, um: float) -> str:
    act = act.upper()
    if act not in ("A", "B"):
        raise ValueError("vérin A ou B")
    return f"LEVEL JOG {act} {fmt(um)}"


def cmd_level_target(x_urad: float, y_urad: float) -> str:
    return f"LEVEL TARGET {fmt(x_urad)} {fmt(y_urad)}"


def cmd_cal_tilt_bias(x_urad: float, y_urad: float) -> str:
    return f"CAL TILT BIAS {fmt(x_urad)} {fmt(y_urad)}"


def cmd_table_add(mass_g: float, p_pa: float) -> str:
    return f"TABLE ADD {fmt(mass_g)} {fmt(p_pa)}"


def cmd_stream_on(hz: float) -> str:
    return f"STREAM ON {fmt(hz)}"


# ---- miroir Python du parseur C++ -----------------------------------------------------------------

@dataclass
class ParsedCommand:
    type: str = "None"
    f: list[float] = field(default_factory=lambda: [0.0, 0.0])
    axis: int = 0
    flag: bool = False


class ParseError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


_NUM_RANGES = {
    "SET P": (0.0, 1000.0), "SET MASS": (0.01, 1000.0), "SET DUTY": (0.0, 1.0), "SET RAMP": (0.1, 5000.0),
    "SET WDT": (0.0, 3600.0),
}


def _num(tok: str, lo: float, hi: float) -> float:
    try:
        if "X" in tok or "_" in tok or not tok.isascii():   # hexadécimal / séparateurs : refusés comme en C++
            raise ValueError
        v = float(tok)
    except ValueError:
        raise ParseError("bad_number") from None
    if not math.isfinite(v):
        raise ParseError("bad_number")
    if v < lo or v > hi:
        raise ParseError("out_of_range")
    return v


def _flag(tok: str) -> bool:
    if tok in ("ON", "1", "TRUE"):
        return True
    if tok in ("OFF", "0", "FALSE"):
        return False
    raise ParseError("bad_flag")


def _need(tk: list[str], n: int) -> None:
    if len(tk) < n:
        raise ParseError("missing_argument")
    if len(tk) > n:
        raise ParseError("extra_argument")


def parse_command(line: str) -> ParsedCommand:
    """Analyse une ligne comme le firmware ; lève ParseError(code) avec les mêmes codes."""
    if len(line) > MAX_LINE:
        raise ParseError("line_too_long")
    tk = line.upper().split()
    if len(tk) == 0:
        raise ParseError("empty")
    if len(tk) > 6:
        raise ParseError("extra_argument")
    out = ParsedCommand()
    c0 = tk[0]

    def simple(t: str, n: int) -> ParsedCommand:
        _need(tk, n)
        out.type = t
        return out

    if c0 == "PING":
        return simple("Ping", 1)
    if c0 == "CLEAR":
        return simple("Clear", 1)
    if c0 == "SAFE":
        return simple("Safe", 1)
    if c0 == "SAVE":
        return simple("Save", 1)
    if c0 == "GET":
        if len(tk) < 2:
            raise ParseError("missing_argument")
        names = {"STATUS": "GetStatus", "CONFIG": "GetConfig", "VERSION": "GetVersion", "TABLE": "GetTable"}
        if tk[1] in names:
            return simple(names[tk[1]], 2)
        raise ParseError("unknown_command")
    if c0 == "SET":
        if len(tk) < 2:
            raise ParseError("missing_argument")
        s = tk[1]
        single = {"P": ("SetP", "SET P"), "MASS": ("SetMass", "SET MASS"), "DUTY": ("SetDuty", "SET DUTY"),
                  "RAMP": ("SetRamp", "SET RAMP"), "WDT": ("SetWdt", "SET WDT")}
        if s in single:
            _need(tk, 3)
            out.type = single[s][0]
            lo, hi = _NUM_RANGES[single[s][1]]
            out.f[0] = _num(tk[2], lo, hi)
            return out
        if s == "GAINS":
            _need(tk, 4)
            out.type = "SetGains"
            out.f[0] = _num(tk[2], 0.0, 10.0)
            out.f[1] = _num(tk[3], 0.05, 100.0)
            return out
        if s == "NOZZLE":
            _need(tk, 4)
            out.type = "SetNozzle"
            out.f[0] = _num(tk[2], 0.1, 1.2)
            out.f[1] = _num(tk[3], 0.5, 200.0)
            return out
        raise ParseError("unknown_command")
    if c0 == "FAN":
        _need(tk, 2)
        out.type = "FanOn" if _flag(tk[1]) else "FanOff"
        return out
    if c0 == "STREAM":
        if len(tk) < 2:
            raise ParseError("missing_argument")
        if tk[1] == "OFF":
            return simple("StreamOff", 2)
        if tk[1] == "ON":
            out.type = "StreamOn"
            if len(tk) == 2:
                out.f[0] = 10.0
                return out
            _need(tk, 3)
            out.f[0] = _num(tk[2], 0.1, 100.0)
            return out
        raise ParseError("bad_flag")
    if c0 == "TABLE":
        if len(tk) < 2:
            raise ParseError("missing_argument")
        if tk[1] == "CLEAR":
            return simple("TableClear", 2)
        if tk[1] == "H":
            _need(tk, 3)
            out.type = "TableH"
            out.f[0] = _num(tk[2], 0.0, 1000.0)
            return out
        if tk[1] == "ADD":
            _need(tk, 4)
            out.type = "TableAdd"
            out.f[0] = _num(tk[2], 0.01, 1000.0)
            out.f[1] = _num(tk[3], 0.0, 2000.0)
            return out
        raise ParseError("unknown_command")
    if c0 == "LEVEL":
        if len(tk) < 2:
            raise ParseError("missing_argument")
        s = tk[1]
        for name, t in (("ZERO", "LevelZero"), ("HOME", "LevelHome"), ("STOP", "LevelStop")):
            if s == name:
                return simple(t, 2)
        if s == "AUTO":
            _need(tk, 3)
            out.type = "LevelAuto"
            out.flag = _flag(tk[2])
            return out
        if s in ("MOVE", "JOG"):
            _need(tk, 4)
            move = s == "MOVE"
            ax = tk[2]
            if move and ax in ("X", "Y"):
                out.axis = 0 if ax == "X" else 1
            elif not move and ax in ("A", "B"):
                out.axis = 0 if ax == "A" else 1
            else:
                raise ParseError("bad_axis")
            out.type = "LevelMove" if move else "LevelJog"
            out.f[0] = _num(tk[3], -5000.0, 5000.0)
            return out
        if s == "TARGET":
            _need(tk, 4)
            out.type = "LevelTarget"
            out.f[0] = _num(tk[2], -5000.0, 5000.0)
            out.f[1] = _num(tk[3], -5000.0, 5000.0)
            return out
        if s == "DEADBAND":
            _need(tk, 3)
            out.type = "LevelDeadband"
            out.f[0] = _num(tk[2], 0.1, 1000.0)
            return out
        raise ParseError("unknown_command")
    if c0 == "CAL":
        if len(tk) < 2:
            raise ParseError("missing_argument")
        if tk[1] == "PZERO":
            return simple("CalPZero", 2)
        if tk[1] == "TILT":
            if len(tk) < 3:
                raise ParseError("missing_argument")
            if tk[2] == "CLEAR":
                return simple("CalTiltClear", 3)
            if tk[2] == "ROT":
                _need(tk, 4)
                out.type = "CalTiltRot"
                out.f[0] = _num(tk[3], -360.0, 360.0)
                return out
            if tk[2] == "BIAS":
                _need(tk, 5)
                out.type = "CalTiltBias"
                out.f[0] = _num(tk[3], -50000.0, 50000.0)
                out.f[1] = _num(tk[4], -50000.0, 50000.0)
                return out
        raise ParseError("unknown_command")
    raise ParseError("unknown_command")


# ---- trames JSON -------------------------------------------------------------------------------------

def parse_line(line: str | bytes) -> dict[str, Any]:
    """Décode une ligne JSON ; lève ProtocolError si ce n'est pas un objet JSON."""
    if isinstance(line, bytes):
        line = line.decode("utf-8", errors="replace")
    line = line.strip()
    try:
        obj = json.loads(line)
    except json.JSONDecodeError as e:
        raise ProtocolError(f"ligne non JSON : {line[:80]!r}") from e
    if not isinstance(obj, dict):
        raise ProtocolError(f"objet JSON attendu : {line[:80]!r}")
    return obj


def is_reply(obj: dict) -> bool:
    return "ok" in obj


def is_telemetry(obj: dict) -> bool:
    return "t" in obj and "ok" not in obj


_T_NAMES = ("T_top", "T_bottom", "T_air", "T_local")

# Colonnes du journal CSV (ordre fixe : le fichier reste lisible même si le firmware omet des champs)
CSV_FIELDS = (
    ["t_ms", "st", "flt", "pm", "pu", "nv", "psp", "pr", "set", "dpn", "q", "rho"]
    + [f"p{i}" for i in range(5)]
    + ["rpm0", "rpm1", "pwm", "tilt_x", "tilt_y", "traw_x", "traw_y", "tt", "tok"]
    + list(_T_NAMES)
    + ["pa", "rh", "disp0", "disp1", "disp2", "stp0", "stp1", "home", "auto", "lbusy", "drop"]
)


def flatten(frame: dict[str, Any]) -> dict[str, Any]:
    """Aplatit une trame de télémétrie en colonnes scalaires (None pour null/absent)."""
    out: dict[str, Any] = {k: None for k in CSV_FIELDS}

    def arr(key: str, names: list[str]) -> None:
        v = frame.get(key)
        if isinstance(v, list):
            for n, x in zip(names, v):
                out[n] = x

    for k, v in frame.items():
        if k in ("ok", "faults"):
            continue
        if k == "t":
            out["t_ms"] = v
        elif k in out and not isinstance(v, list):
            out[k] = v
    arr("p", [f"p{i}" for i in range(5)])
    arr("rpm", ["rpm0", "rpm1"])
    arr("tilt", ["tilt_x", "tilt_y"])
    arr("traw", ["traw_x", "traw_y"])
    arr("T", list(_T_NAMES))
    arr("disp", ["disp0", "disp1", "disp2"])
    arr("stp", ["stp0", "stp1"])
    return out
