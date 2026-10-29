"""Client série du banc (pyserial) avec transport interchangeable (simulateur pour les tests)."""
from __future__ import annotations

import json
import time
from collections import deque
from pathlib import Path
from typing import Iterator

from . import protocol as proto
from .protocol import DeviceError, ProtocolError


class Transport:
    """Interface minimale attendue (pyserial.Serial la satisfait)."""

    def write(self, data: bytes) -> int: ...      # pragma: no cover
    def readline(self) -> bytes: ...              # pragma: no cover
    def close(self) -> None: ...                  # pragma: no cover


def open_transport(port: str, baud: int = 115200, timeout: float = 0.2):
    """Ouvre un port série réel, ou le simulateur pour « sim:// »."""
    if port.startswith("sim://"):
        from .sim import SimDevice
        return SimDevice()
    try:
        import serial  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("pyserial est requis : pip install pyserial") from e
    ser = serial.serial_for_url(port, baudrate=baud, timeout=timeout, write_timeout=2.0)
    # Le DevKitC redémarre à l'ouverture du port (DTR/RTS) : laisser le firmware démarrer
    time.sleep(0.05)
    ser.reset_input_buffer()
    return ser


class AirtableClient:
    """Envoie des commandes ligne par ligne et lit les réponses JSON.

    Les trames de télémétrie reçues pendant l'attente d'une réponse sont conservées dans
    `self.telemetry` (file bornée) et jamais perdues silencieusement.
    """

    def __init__(self, port: str | None = None, baud: int = 115200, timeout: float = 2.0,
                 transport=None):
        if transport is None:
            if port is None:
                raise ValueError("port série ou transport requis")
            transport = open_transport(port, baud)
        self._t = transport
        self.timeout = timeout
        self.telemetry: deque[dict] = deque(maxlen=2000)
        self.bad_lines = 0

    # -- cycle de vie ----------------------------------------------------------------------------
    def close(self) -> None:
        try:
            self._t.close()
        except Exception:  # pragma: no cover
            pass

    def __enter__(self) -> "AirtableClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- commandes --------------------------------------------------------------------------------
    def command(self, line: str, timeout: float | None = None, raise_on_error: bool = True) -> dict:
        """Envoie une commande et retourne la réponse (dict). DeviceError si ok == false."""
        if len(line) > proto.MAX_LINE:
            raise ValueError("ligne trop longue pour le firmware")
        self._t.write((line.strip() + "\n").encode("ascii"))
        deadline = time.monotonic() + (self.timeout if timeout is None else timeout)
        while True:
            raw = self._t.readline()
            if not raw:
                if time.monotonic() > deadline:
                    raise TimeoutError(f"pas de réponse à « {line} »")
                continue
            try:
                obj = proto.parse_line(raw)
            except ProtocolError:
                self.bad_lines += 1
                continue
            if proto.is_reply(obj):
                if raise_on_error and not obj.get("ok"):
                    raise DeviceError(str(obj.get("err", "unknown")), obj)
                return obj
            if proto.is_telemetry(obj):
                self.telemetry.append(obj)

    # raccourcis ---------------------------------------------------------------------------------------
    def ping(self) -> dict:
        return self.command("PING")

    def version(self) -> dict:
        return self.command("GET VERSION")

    def config(self) -> dict:
        return self.command("GET CONFIG")

    def status(self) -> dict:
        return self.command("GET STATUS")

    def set_pressure(self, p_pa: float) -> dict:
        return self.command(proto.cmd_set_pressure(p_pa))

    def set_mass(self, m_g: float) -> dict:
        return self.command(proto.cmd_set_mass(m_g))

    def set_duty(self, d: float) -> dict:
        return self.command(proto.cmd_set_duty(d))

    def fan_off(self) -> dict:
        return self.command("FAN OFF")

    def level_auto(self, on: bool) -> dict:
        return self.command("LEVEL AUTO " + ("ON" if on else "OFF"))

    def level_move(self, axis: str, urad: float) -> dict:
        return self.command(proto.cmd_level_move(axis, urad))

    def level_zero(self) -> dict:
        return self.command("LEVEL ZERO")

    def level_home(self) -> dict:
        return self.command("LEVEL HOME")

    def level_stop(self) -> dict:
        return self.command("LEVEL STOP")

    def level_target(self, x_urad: float, y_urad: float) -> dict:
        return self.command(proto.cmd_level_target(x_urad, y_urad))

    def safe(self) -> dict:
        return self.command("SAFE")

    def clear(self) -> dict:
        return self.command("CLEAR")

    def save(self) -> dict:
        return self.command("SAVE")

    def wait_homed(self, timeout: float = 240.0, poll_s: float = 1.0) -> dict:
        """Attend la fin de la prise d'origine (home == 3). Lève TimeoutError / DeviceError."""
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            st = self.status()
            if st.get("home") == 3:
                return st
            if st.get("home") == 4:
                raise DeviceError("homing_failed", st)
            time.sleep(poll_s)
        raise TimeoutError("prise d'origine trop longue")

    # -- table masse → pression ---------------------------------------------------------------------
    def load_setpoints(self, path: str | Path) -> int:
        """Envoie calc/aero/results/setpoints.json au firmware (TABLE CLEAR/H/ADD). Retourne n points."""
        h, pts = read_setpoints(path)
        self.command("TABLE CLEAR")
        if h is not None:
            self.command(f"TABLE H {proto.fmt(h)}")
        for m, p in pts:
            self.command(proto.cmd_table_add(m, p))
        return len(pts)

    # -- flux --------------------------------------------------------------------------------------------
    def stream(self, hz: float = 10.0, duration_s: float | None = None,
               count: int | None = None) -> Iterator[dict]:
        """Itère sur les trames de télémétrie ; `duration_s` est mesurée sur l'horloge du firmware."""
        self.command(proto.cmd_stream_on(hz))
        n = 0
        t0: float | None = None
        deadline = time.monotonic() + (self.timeout + 3.0 / max(hz, 0.1))
        try:
            while True:
                if self.telemetry:
                    obj = self.telemetry.popleft()
                else:
                    raw = self._t.readline()
                    if not raw:
                        if time.monotonic() > deadline:
                            raise TimeoutError("flux de télémétrie interrompu")
                        continue
                    try:
                        obj = proto.parse_line(raw)
                    except ProtocolError:
                        self.bad_lines += 1
                        continue
                    if not proto.is_telemetry(obj):
                        continue
                deadline = time.monotonic() + (self.timeout + 3.0 / max(hz, 0.1))
                if t0 is None:
                    t0 = obj["t"]
                yield obj
                n += 1
                if count is not None and n >= count:
                    return
                if duration_s is not None and (obj["t"] - t0) / 1000.0 >= duration_s:
                    return
        finally:
            try:
                self.command("STREAM OFF", raise_on_error=False)
            except Exception:  # pragma: no cover
                pass

    def collect_tilt_raw(self, n: int, hz: float = 10.0, discard: int = 5) -> list[tuple[float, float]]:
        """n échantillons de pente brute (repère capteur, sans biais) ; ignore les trames invalides."""
        out: list[tuple[float, float]] = []
        skipped = 0
        for fr in self.stream(hz=hz):
            tr = fr.get("traw")
            if not tr or tr[0] is None or tr[1] is None or not fr.get("tok", True):
                continue
            if skipped < discard:
                skipped += 1
                continue
            out.append((float(tr[0]), float(tr[1])))
            if len(out) >= n:
                break
        return out


def read_setpoints(path: str | Path) -> tuple[float | None, list[tuple[float, float]]]:
    """Lit {"h_target_um":..,"points":[{"mass_g":..,"p_Pa":..},...]} ; valide et trie par masse."""
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    pts_raw = d.get("points")
    if not isinstance(pts_raw, list) or not pts_raw:
        raise ValueError(f"{path} : clé « points » absente ou vide")
    pts = sorted((float(p["mass_g"]), float(p["p_Pa"])) for p in pts_raw)
    masses = [m for m, _ in pts]
    if len(set(masses)) != len(masses):
        raise ValueError(f"{path} : masses en double")
    if any(m <= 0 or p < 0 for m, p in pts):
        raise ValueError(f"{path} : masse ou pression invalide")
    h = d.get("h_target_um")
    return (float(h) if h is not None else None), pts


def interpolate_setpoint(points: list[tuple[float, float]], mass_g: float) -> float:
    """Miroir de atc::SetpointTable::interpolate (interpolation linéaire, saturée aux extrémités)."""
    if len(points) == 1 or mass_g <= points[0][0]:
        return points[0][1]
    if mass_g >= points[-1][0]:
        return points[-1][1]
    for (m0, p0), (m1, p1) in zip(points, points[1:]):
        if m0 <= mass_g <= m1:
            return p0 + (mass_g - m0) / (m1 - m0) * (p1 - p0)
    raise AssertionError("inatteignable")
