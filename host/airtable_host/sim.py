"""Simulateur du firmware (protocole identique) : tests unitaires et essais à vide (--port sim://).

Modèle volontairement simple : pression = filtre du 1er ordre vers la consigne, pente de la
plaque = pente vraie + biais capteur + bruit, retournement du capteur = signe de la pente vraie
inversé (le biais ne change pas). Le temps est simulé : `readline()` n'attend jamais.
"""
from __future__ import annotations

import json
import math
import random
from collections import deque

from . import protocol as proto


class SimDevice:
    def __init__(self, seed: int = 1, true_slope: tuple[float, float] = (120.0, -80.0),
                 sensor_bias: tuple[float, float] = (35.0, -20.0), tilt_noise_urad: float = 3.0,
                 p_noise_pa: float = 0.05, tau_p_s: float = 1.0):
        self.rng = random.Random(seed)
        self.true_slope = list(true_slope)       # pente de la plaque dz/dx, dz/dy [µrad]
        self.sensor_bias = list(sensor_bias)     # biais intrinsèque du capteur [µrad]
        self.tilt_noise = tilt_noise_urad
        self.p_noise = p_noise_pa
        self.tau_p = tau_p_s
        self.flipped = False                     # capteur retourné de 180° (démonstration du retournement)
        self.cal_bias = [0.0, 0.0]               # biais soustrait par le firmware (CAL TILT BIAS)
        self.t_ms = 0.0
        self.mode = "off"
        self.p = 0.0
        self.p_target = 0.0
        self.duty = 0.0
        self.homed = False
        self.auto = False
        self.table: list[tuple[float, float]] = []
        self.h_um = 0.0
        self.stream_hz = 0.0
        self.faults = 0
        self.level_target = [0.0, 0.0]
        self.log: list[str] = []                 # commandes reçues (pour les tests)
        self._out: deque[bytes] = deque()
        self._buf = b""

    # ---- transport -------------------------------------------------------------------------------
    def write(self, data: bytes) -> int:
        self._buf += data
        while b"\n" in self._buf:
            line, self._buf = self._buf.split(b"\n", 1)
            self._handle(line.decode("ascii", errors="replace").rstrip("\r"))
        return len(data)

    def readline(self) -> bytes:
        if self._out:
            return self._out.popleft()
        if self.stream_hz > 0:
            self._advance(1.0 / self.stream_hz)
            return (json.dumps(self._frame(), allow_nan=False) + "\n").encode()
        return b""

    def reset_input_buffer(self) -> None:
        self._out.clear()

    def close(self) -> None:
        pass

    # ---- physique ---------------------------------------------------------------------------------
    def rotate_sensor_180(self) -> None:
        """Retourne le capteur de 180° autour de la normale : la pente vue change de signe."""
        self.flipped = not self.flipped

    def _advance(self, dt: float) -> None:
        self.t_ms += dt * 1000.0
        if self.mode in ("run", "manual"):
            a = min(1.0, dt / self.tau_p)
            self.p += a * (self.p_target - self.p)
        else:
            self.p += min(1.0, dt / self.tau_p) * (0.0 - self.p)

    def _raw_tilt(self) -> tuple[float, float]:
        s = -1.0 if self.flipped else 1.0
        return tuple(s * self.true_slope[i] + self.sensor_bias[i] + self.rng.gauss(0, self.tilt_noise)
                     for i in range(2))  # type: ignore[return-value]

    @staticmethod
    def _r(v: float | None, n: int = 2):
        if v is None or not math.isfinite(v):
            return None
        return round(v, n)

    def _frame(self, reply: bool = False) -> dict:
        raw = self._raw_tilt()
        base = {
            "t": int(self.t_ms), "st": self.mode, "flt": self.faults, "faults": [],
            "p": [self._r(self.p + self.rng.gauss(0, self.p_noise)) for _ in range(5)],
            "pm": self._r(self.p), "pu": 0.5, "nv": 5,
            "psp": self._r(self.p_target, 1) if self.mode == "run" else None,
            "pr": self._r(self.p_target, 1) if self.mode == "run" else None,
            "set": self.mode == "run" and abs(self.p - self.p_target) < 0.3,
            "dpn": self._r(self.p * 0.05), "q": 12.0, "rho": 1.204,
            "rpm": [self._r(300 + 25 * math.sqrt(max(self.p, 0)) * 10, 0)],
            "pwm": self._r(self.duty * 100, 1),
            "tilt": [self._r(raw[0] - self.cal_bias[0]), self._r(raw[1] - self.cal_bias[1])],
            "traw": [self._r(raw[0]), self._r(raw[1])], "tt": 24.5, "tok": True,
            "T": [20.0, 20.01, 20.0, 19.9], "pa": 1013.2, "rh": 45.0,
            "stp": [0, 0], "home": 3 if self.homed else 0, "auto": self.auto, "lbusy": False, "drop": 0,
        }
        if reply:
            base = {"ok": True, **base}
        return base

    # ---- protocole -----------------------------------------------------------------------------------
    def _emit(self, obj: dict) -> None:
        self._out.append((json.dumps(obj, allow_nan=False) + "\n").encode())

    def _err(self, code: str) -> None:
        self._emit({"ok": False, "err": code})

    def _handle(self, line: str) -> None:
        self.log.append(line)
        try:
            c = proto.parse_command(line)
        except proto.ParseError as e:
            if e.code != "empty":
                self._err(e.code)
            return
        t = c.type
        if t == "Ping":
            self._emit({"ok": True, "pong": int(self.t_ms)})
        elif t == "GetStatus":
            self._emit(self._frame(reply=True))
        elif t == "GetVersion":
            self._emit({"ok": True, "fw": "airtable-sim", "ver": "0", "proto": 1, "incl": "sim", "reset": 1})
        elif t == "GetConfig":
            self._emit({"ok": True, "p_min": 30.0, "p_max": 400.0, "fans": 1, "target": list(self.level_target)})
        elif t == "GetTable":
            self._emit({"ok": True, "h_um": self.h_um, "points": [[m, p] for m, p in self.table]})
        elif t in ("SetP", "SetMass"):
            if t == "SetMass":
                if not self.table:
                    return self._err("no_table")
                p = proto_interp(self.table, c.f[0])
            else:
                p = c.f[0]
            if not 30.0 <= p <= 400.0:
                return self._err("out_of_range")
            self.mode, self.p_target = "run", p
            self._emit({"ok": True, "p": p} if t == "SetMass" else {"ok": True})
        elif t == "SetDuty":
            self.mode, self.duty = "manual", c.f[0]
            self.p_target = 600.0 * c.f[0] ** 2
            self._emit({"ok": True})
        elif t == "FanOff":
            self.mode, self.p_target, self.duty = "off", 0.0, 0.0
            self._emit({"ok": True})
        elif t == "FanOn":
            self.mode, self.duty = "manual", 0.2
            self._emit({"ok": True})
        elif t == "LevelHome":
            self.homed = True
            self._emit({"ok": True})
        elif t == "LevelAuto":
            if c.flag and not self.homed:
                return self._err("not_homed")
            self.auto = c.flag
            self._emit({"ok": True})
        elif t == "LevelMove":
            if not self.homed:
                return self._err("not_homed")
            self.true_slope[c.axis] += c.f[0]       # LEVEL MOVE = variation de dz/dx|dy
            self._emit({"ok": True, "ms": 1500})
        elif t == "LevelZero":
            if not self.homed:
                return self._err("not_homed")
            self._emit({"ok": True, "ms": 1000})
        elif t == "LevelTarget":
            self.level_target = [c.f[0], c.f[1]]
            self._emit({"ok": True})
        elif t == "CalTiltBias":
            self.cal_bias = [c.f[0], c.f[1]]
            self._emit({"ok": True})
        elif t == "CalTiltClear":
            self.cal_bias = [0.0, 0.0]
            self._emit({"ok": True})
        elif t == "TableClear":
            self.table.clear()
            self._emit({"ok": True})
        elif t == "TableAdd":
            self.table = sorted([x for x in self.table if x[0] != c.f[0]] + [(c.f[0], c.f[1])])
            self._emit({"ok": True})
        elif t == "TableH":
            self.h_um = c.f[0]
            self._emit({"ok": True})
        elif t == "StreamOn":
            self.stream_hz = c.f[0]
            self._emit({"ok": True})
        elif t == "StreamOff":
            self.stream_hz = 0.0
            self._emit({"ok": True})
        elif t == "Safe":
            self.faults |= 1 << 6
            self.mode = "safe"
            self._emit({"ok": True})
        elif t == "Clear":
            self.faults = 0
            if self.mode == "safe":
                self.mode = "off"
            self._emit({"ok": True})
        else:                                        # SetRamp, SetGains, SetNozzle, SetWdt, Save, ...
            self._emit({"ok": True})


def proto_interp(points: list[tuple[float, float]], m: float) -> float:
    from .client import interpolate_setpoint
    return interpolate_setpoint(points, m)
