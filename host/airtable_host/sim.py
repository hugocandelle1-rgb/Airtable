"""Simulateur du firmware (protocole identique) : tests unitaires et essais à vide (--port sim://).

Modèle volontairement simple : pression = filtre du 1er ordre vers la consigne ; pente de la plaque
= pente vraie (+ courbure éventuelle de la plaque) + biais capteur + dérive thermique + bruit ;
retournement du capteur = signe de la pente vraie inversé (le biais ne change pas). `n_sensors` capteurs
(1 par défaut ; 4 pour le réseau d'ADXL355) avec compensation thermique, fusion, apprentissage thermique
et retournement motorisé instantané du capteur 0. Le temps est simulé : `readline()` n'attend jamais.
"""
from __future__ import annotations

import json
import math
import random
from collections import deque

import numpy as np

from . import protocol as proto


class SimDevice:
    def __init__(self, seed: int = 1, true_slope: tuple[float, float] = (120.0, -80.0),
                 sensor_bias: tuple[float, float] = (35.0, -20.0), tilt_noise_urad: float = 3.0,
                 p_noise_pa: float = 0.05, tau_p_s: float = 1.0, n_sensors: int = 1,
                 positions_mm: list[tuple[float, float]] | None = None,
                 curvature: tuple[float, float, float] = (0.0, 0.0, 0.0),
                 other_biases: list[tuple[float, float]] | None = None,
                 thermal_k1: list[tuple[float, float]] | None = None, temp_rate_k_s: float = 0.0,
                 has_flip: bool = True):
        self.rng = random.Random(seed)
        self.n = n_sensors
        self.positions = list(positions_mm or [(-200.0, -200.0), (200.0, -200.0), (200.0, 200.0), (-200.0, 200.0)])[:self.n]
        self.curvature = curvature                # z_xx, z_xy, z_yy [µrad/m]
        ob = other_biases or [(-12.0, 8.0), (25.0, -15.0), (5.0, 30.0)]
        self.biases = [list(sensor_bias)] + [list(b) for b in ob[:max(self.n - 1, 0)]]
        self.k1 = [tuple(k) for k in (thermal_k1 or [(0.0, 0.0)] * 4)][:self.n]      # dérive du zéro [µrad/K]
        self.T = [22.0] * self.n                  # températures des bases [°C]
        self.temp_rate = temp_rate_k_s
        self.rot180 = [False] * self.n            # capteur i retourné de 180°
        self.cal = [{"bias": [0.0, 0.0], "tref": 20.0, "order": 0, "c1": [0.0, 0.0], "c2": [0.0, 0.0]}
                    for _ in range(self.n)]
        self.use = [True] * self.n
        self.learning: list[list[tuple[float, float, float]]] | None = None
        self.has_flip = has_flip
        self.flip_state = "idle"
        self.flip_err = "none"
        self.flip_fail: str | None = None         # ex. "actuator_timeout" : fait échouer le prochain FLIP RUN
        self.flip_res: dict | None = None
        self.true_slope = list(true_slope)       # pente de la plaque dz/dx, dz/dy [µrad]
        self.sensor_bias = self.biases[0]        # biais intrinsèque du capteur 0 [µrad] (même liste)
        self.tilt_noise = tilt_noise_urad
        self.p_noise = p_noise_pa
        self.tau_p = tau_p_s
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
    @property
    def cal_bias(self) -> list[float]:
        """Biais soustrait par le firmware pour le capteur 0 (CAL TILT BIAS)."""
        return self.cal[0]["bias"]

    @property
    def flipped(self) -> bool:
        return self.rot180[0]

    def rotate_sensor_180(self, i: int = 0) -> None:
        """Retourne le capteur i de 180° autour de la normale : la pente vue change de signe."""
        self.rot180[i] = not self.rot180[i]

    def _advance(self, dt: float) -> None:
        self.t_ms += dt * 1000.0
        if self.mode in ("run", "manual"):
            a = min(1.0, dt / self.tau_p)
            self.p += a * (self.p_target - self.p)
        else:
            self.p += min(1.0, dt / self.tau_p) * (0.0 - self.p)
        for i in range(self.n):
            self.T[i] += self.temp_rate * dt

    def _site_slope(self, i: int) -> tuple[float, float]:
        """Pente vraie de la plaque à la position du capteur i (plan moyen + courbure)."""
        x, y = self.positions[i]
        zxx, zxy, zyy = self.curvature
        return (self.true_slope[0] + (zxx * x + zxy * y) * 1e-3, self.true_slope[1] + (zxy * x + zyy * y) * 1e-3)

    def _thermal_offset(self, i: int, T: float) -> tuple[float, float]:
        c = self.cal[i]
        if not c["order"]:
            return (0.0, 0.0)
        d = T - c["tref"]
        d2 = d * d if c["order"] >= 2 else 0.0
        return (c["c1"][0] * d + c["c2"][0] * d2, c["c1"][1] * d + c["c2"][1] * d2)

    def _raw_sensor(self, i: int, noise: bool = True) -> tuple[float, float]:
        """Lecture brute du capteur i (repère capteur, non compensée)."""
        sg = -1.0 if self.rot180[i] else 1.0
        s = self._site_slope(i)
        d = self.T[i] - 20.0
        return tuple(sg * s[a] + self.biases[i][a] + self.k1[i][a] * d
                     + (self.rng.gauss(0, self.tilt_noise) if noise else 0.0) for a in (0, 1))  # type: ignore[return-value]

    def _raw_tilt(self) -> tuple[float, float]:     # compatibilité : capteur 0
        return self._raw_sensor(0)

    def _fuse(self, tc: list[tuple[float, float]]) -> tuple[float, float] | None:
        idx = [i for i in range(self.n) if self.use[i]]
        if not idx:
            return None
        if len(idx) >= 3:
            mx = float(np.median([tc[i][0] for i in idx]))
            my = float(np.median([tc[i][1] for i in idx]))
            idx = [i for i in idx if max(abs(tc[i][0] - mx), abs(tc[i][1] - my)) <= 40.0]
        if not idx:
            return None
        return (sum(tc[i][0] for i in idx) / len(idx), sum(tc[i][1] for i in idx) / len(idx))

    @staticmethod
    def _r(v: float | None, n: int = 2):
        if v is None or not math.isfinite(v):
            return None
        return round(v, n)

    def _frame(self, reply: bool = False) -> dict:
        raws = [self._raw_sensor(i) for i in range(self.n)]
        if self.learning is not None:
            for i in range(self.n):
                self.learning[i].append((self.T[i], raws[i][0], raws[i][1]))
        tr = [tuple(raws[i][a] - self._thermal_offset(i, self.T[i])[a] for a in (0, 1)) for i in range(self.n)]
        tc = [tuple(tr[i][a] - self.cal[i]["bias"][a] for a in (0, 1)) for i in range(self.n)]
        fused = self._fuse(tc)
        flat = lambda arr: [self._r(v) for xy in arr for v in xy]          # noqa: E731
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
            "tilt": [self._r(fused[0]), self._r(fused[1])] if fused else [None, None],
            "traw": [self._r(tr[0][0]), self._r(tr[0][1])], "tt": self._r(self.T[0]), "tok": fused is not None,
            "tr": flat(tr), "tc": flat(tc), "Tb": [self._r(t, 3) for t in self.T],
            "tu": sum(1 << i for i in range(self.n) if self.use[i]), "trj": 0, "tn": sum(self.use),
            "tsg": self._r(self.tilt_noise / math.sqrt(max(sum(self.use), 1)), 3),
            "dsp": [self._r(max(c[a] for c in tc) - min(c[a] for c in tc)) for a in (0, 1)],
            "dfm": self._r(max(max(abs(c[0] - fused[0]), abs(c[1] - fused[1])) for c in tc) if fused else None),
            "dfw": False, "tinc": False,
            "crv": [self.curvature[0], self.curvature[1], self.curvature[2], 0.0] if self.n >= 3 else [None] * 4,
            "flip": self.flip_state,
            "T": [20.0, 20.01, 20.0, 19.9], "pa": 1013.2, "rh": 45.0,
            "stp": [0, 0], "home": 3 if self.homed else 0, "auto": self.auto, "lbusy": False, "drop": 0,
        }
        if reply:
            base = {"ok": True, **base}
        return base

    # ---- retournement motorisé et apprentissage thermique -------------------------------------------
    def _flip_run(self, avg_s: float) -> None:
        if not self.has_flip:
            return self._err("no_flip_hardware")
        if self.flip_fail:
            self.flip_state, self.flip_err, self.flip_res = "failed", self.flip_fail, None
            self.flip_fail = None
            return self._emit({"ok": True})
        n = max(int((avg_s or 20.0) * 10), 20)
        sd = self.tilt_noise / math.sqrt(n)

        def meas(rot: bool) -> tuple[float, float]:
            old = self.rot180[0]
            self.rot180[0] = rot
            raw = self._raw_sensor(0, noise=False)
            self.rot180[0] = old
            off = self._thermal_offset(0, self.T[0])
            return tuple(raw[a] - off[a] + self.rng.gauss(0, sd) for a in (0, 1))  # type: ignore[return-value]

        a, b = meas(False), meas(True)
        self.flip_res = {"bias": [(a[k] + b[k]) / 2 for k in (0, 1)], "slope": [(a[k] - b[k]) / 2 for k in (0, 1)],
                         "drift": [0.0, 0.0], "T_mean": self.T[0], "na": n, "nb": n}
        self.flip_state, self.flip_err = "done", "none"
        self._emit({"ok": True})

    def _therm_fit(self, order: int, sensors: list[int]) -> None:
        if self.learning is None:
            return self._err("not_learning")
        rows, first_err = [], None
        for i in sensors:
            data = np.array(self.learning[i])
            if len(data) < 50:
                first_err = first_err or "too_few_samples"
                continue
            span = float(data[:, 0].max() - data[:, 0].min())
            if span < 1.0:
                first_err = first_err or "span_too_small"
                continue
            tref = float(data[0, 0])
            d = data[:, 0] - tref
            c = self.cal[i]
            res = []
            for a in (0, 1):
                coef = np.polyfit(d, data[:, 1 + a], order)[::-1]       # c0, c1, c2
                res.append(coef)
            new = {"tref": tref, "order": order, "c1": [float(res[0][1]), float(res[1][1])],
                   "c2": [float(res[0][2]) if order >= 2 else 0.0, float(res[1][2]) if order >= 2 else 0.0]}
            old_off = self._thermal_offset(i, self.T[i])
            c.update(new)
            new_off = self._thermal_offset(i, self.T[i])
            c["bias"] = [c["bias"][a] + old_off[a] - new_off[a] for a in (0, 1)]   # sortie continue à T courante
            rms = [float(np.sqrt(np.mean((np.polyval(res[a][::-1], d) - data[:, 1 + a]) ** 2))) for a in (0, 1)]
            rows.append([i, new["c1"][0], new["c1"][1], new["c2"][0], new["c2"][1], rms[0], rms[1], span])
        if not rows:
            return self._err(first_err or "not_learning")
        self.learning = None
        self._emit({"ok": True, "fit": [[round(v, 4) if k else v for k, v in enumerate(r)] for r in rows]})

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
            self._emit({"ok": True, "fw": "airtable-sim", "ver": "0", "proto": 2, "incl": "sim", "ntilt": self.n,
                        "reset": 1})
        elif t == "GetConfig":
            self._emit({"ok": True, "p_min": 30.0, "p_max": 400.0, "fans": 1, "target": list(self.level_target),
                        "ntilt": self.n, "tuse": sum(1 << i for i in range(self.n) if self.use[i]),
                        "tilt_bias": [round(v, 3) for c in self.cal for v in c["bias"]],
                        "th_c1": [v for c in self.cal for v in c["c1"]], "th_c2": [v for c in self.cal for v in c["c2"]],
                        "th_ref": [c["tref"] for c in self.cal], "th_ord": [c["order"] for c in self.cal],
                        "flip_hw": self.has_flip})
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
        elif t in ("CalTiltBias", "CalTiltClear", "CalTiltRot", "CalTiltThermClear"):
            if c.axis >= self.n:
                return self._err("no_such_sensor")
            for i in (range(self.n) if c.axis < 0 else [c.axis]):
                if t == "CalTiltBias":
                    self.cal[i]["bias"] = [c.f[0], c.f[1]]
                elif t == "CalTiltClear":
                    self.cal[i]["bias"] = [0.0, 0.0]
                elif t == "CalTiltThermClear":
                    self.cal[i].update(order=0, c1=[0.0, 0.0], c2=[0.0, 0.0])
            self._emit({"ok": True})
        elif t == "CalTiltUse":
            if c.axis >= self.n:
                return self._err("no_such_sensor")
            self.use[c.axis] = c.flag
            self._emit({"ok": True})
        elif t == "CalTiltThermStart":
            self.learning = [[] for _ in range(self.n)]
            self._emit({"ok": True})
        elif t == "CalTiltThermFit":
            if c.axis >= self.n:
                return self._err("no_such_sensor")
            self._therm_fit(int(c.f[0]), list(range(self.n)) if c.axis < 0 else [c.axis])
        elif t == "FlipRun":
            self._flip_run(c.f[0])
        elif t == "FlipAbort":
            self._emit({"ok": True})
        elif t == "FlipZero":
            self._emit({"ok": True} if self.has_flip else {"ok": False, "err": "no_flip_hardware"})
        elif t == "GetFlip":
            r = self.flip_res
            ok = r is not None
            self._emit({"ok": True, "hw": self.has_flip, "state": self.flip_state, "err": self.flip_err, "idx": 0,
                        "valid": ok, "reliable": ok, **({k: v for k, v in r.items()} if r else {})})
        elif t == "FlipApply":
            if self.flip_res is None:
                return self._err("no_result")
            self.cal[0]["bias"] = list(self.flip_res["bias"])
            self._emit({"ok": True, "idx": 0, "bias": list(self.flip_res["bias"])})
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
