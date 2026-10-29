"""Calibration de l'inclinomètre par retournement de 180 degrés.

Principe : le capteur est posé sur sa semelle (embase à goupilles) ; on lit la pente brute (repère
capteur) en position A, on le retourne de 180° autour de la NORMALE à sa semelle, puis on relit
en position B. La pente vraie de la surface change de signe dans le repère du capteur, pas son
biais :

    A = +s + b          B = −s + b          ⇒   b = (A + B)/2 ,   s = (A − B)/2

b est le biais (offset) du capteur sur chaque axe [µrad] ; s la pente vraie de la surface dans le
repère de la position A. Une troisième série A2 (retour en A) quantifie la dérive pendant la
procédure : si A2 diffère de A au-delà du bruit, le résultat est signalé comme non fiable
(dérive thermique ou mécanique : attendre la stabilisation et recommencer) ; sinon A et A2 sont
moyennées, ce qui annule au 1er ordre une dérive linéaire.

Le biais calculé se règle avec `CAL TILT BIAS bx by` (puis `SAVE`) : il est soustrait à la mesure
brute AVANT la rotation de montage éventuelle (CAL TILT ROT).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Sequence

from . import protocol as proto

Sample = tuple[float, float]


@dataclass
class SeriesStats:
    n: int
    mean: tuple[float, float]
    sem: tuple[float, float]          # écart-type de la moyenne
    std: tuple[float, float]


def series_stats(samples: Sequence[Sample]) -> SeriesStats:
    n = len(samples)
    if n < 2:
        raise ValueError("au moins 2 échantillons par position")
    mean = []
    std = []
    for ax in (0, 1):
        vals = [s[ax] for s in samples]
        m = sum(vals) / n
        var = sum((v - m) ** 2 for v in vals) / (n - 1)
        mean.append(m)
        std.append(math.sqrt(var))
    sem = tuple(s / math.sqrt(n) for s in std)
    return SeriesStats(n, (mean[0], mean[1]), sem, (std[0], std[1]))  # type: ignore[arg-type]


@dataclass
class FlipResult:
    bias_urad: tuple[float, float]
    bias_sigma_urad: tuple[float, float]
    slope_a_urad: tuple[float, float]       # pente vraie de la surface, repère de la position A
    slope_sigma_urad: tuple[float, float]
    a: SeriesStats
    b: SeriesStats
    drift_urad: tuple[float, float] | None  # A2 − A (None si pas de série A2)
    warnings: list[str] = field(default_factory=list)

    @property
    def reliable(self) -> bool:
        return not any(w.startswith("dérive") or w.startswith("bruit") for w in self.warnings)

    def command(self) -> str:
        return proto.cmd_cal_tilt_bias(*self.bias_urad)

    def summary(self) -> str:
        lines = [
            f"biais capteur   : X = {self.bias_urad[0]:+9.2f} ± {self.bias_sigma_urad[0]:.2f} µrad   "
            f"Y = {self.bias_urad[1]:+9.2f} ± {self.bias_sigma_urad[1]:.2f} µrad",
            f"pente surface A : X = {self.slope_a_urad[0]:+9.2f} ± {self.slope_sigma_urad[0]:.2f} µrad   "
            f"Y = {self.slope_a_urad[1]:+9.2f} ± {self.slope_sigma_urad[1]:.2f} µrad",
            f"échantillons    : A = {self.a.n}, B = {self.b.n}",
        ]
        if self.drift_urad is not None:
            lines.append(f"dérive A2 − A    : X = {self.drift_urad[0]:+.2f}  Y = {self.drift_urad[1]:+.2f} µrad")
        lines += [f"AVERTISSEMENT : {w}" for w in self.warnings]
        return "\n".join(lines)


def flip_calibration(a_samples: Sequence[Sample], b_samples: Sequence[Sample],
                     a2_samples: Sequence[Sample] | None = None,
                     drift_sigmas: float = 4.0, max_bias_urad: float = 20000.0) -> FlipResult:
    """Calcule biais et pente vraie à partir des séries brutes A (et B, éventuellement A2)."""
    a, b = series_stats(a_samples), series_stats(b_samples)
    bias = tuple((a.mean[i] + b.mean[i]) / 2 for i in (0, 1))
    slope = tuple((a.mean[i] - b.mean[i]) / 2 for i in (0, 1))
    sig = tuple(0.5 * math.hypot(a.sem[i], b.sem[i]) for i in (0, 1))
    warnings: list[str] = []
    drift = None
    if a2_samples is not None:
        a2 = series_stats(a2_samples)
        drift = tuple(a2.mean[i] - a.mean[i] for i in (0, 1))
        for i, name in enumerate("XY"):
            tol = drift_sigmas * math.hypot(a.sem[i], a2.sem[i])
            if abs(drift[i]) > tol:
                warnings.append(f"dérive sur l'axe {name} entre A et A2 : {drift[i]:+.2f} µrad "
                                f"(> {tol:.2f}) ; attendre la stabilisation thermique et recommencer")
        # Avec dérive linéaire pendant A-B-A2, la moyenne pondérée A/A2 est un meilleur A
        a_eff = tuple((a.mean[i] + a2.mean[i]) / 2 for i in (0, 1))
        bias = tuple((a_eff[i] + b.mean[i]) / 2 for i in (0, 1))
        slope = tuple((a_eff[i] - b.mean[i]) / 2 for i in (0, 1))
    for i, name in enumerate("XY"):
        if abs(bias[i]) > max_bias_urad:
            warnings.append(f"biais {name} = {bias[i]:.0f} µrad anormalement grand : capteur mal retourné ?")
        if a.std[i] > 200.0:
            warnings.append(f"bruit trop élevé sur l'axe {name} ({a.std[i]:.0f} µrad rms) : vibrations ?")
    return FlipResult(bias, sig, slope, sig, a, b, drift, warnings)  # type: ignore[arg-type]


def run_flip_procedure(client, prompt: Callable[[str], None], n_samples: int = 100, hz: float = 10.0,
                       with_return: bool = True, apply: bool = False, save: bool = False,
                       out: Callable[[str], None] = print) -> FlipResult:
    """Procédure interactive de retournement avec un AirtableClient.

    `prompt(message)` doit bloquer jusqu'à l'action de l'opérateur (input() en ligne de commande).
    """
    def measure(label: str) -> list[Sample]:
        out(f"mesure {label} : {n_samples} échantillons à {hz:g} Hz ...")
        s = client.collect_tilt_raw(n_samples, hz=hz)
        if len(s) < n_samples:
            raise RuntimeError(f"seulement {len(s)}/{n_samples} échantillons valides en {label}")
        return s

    prompt("Position A : capteur posé sur sa semelle, plaque immobile et au repos "
           "(ventilateur dans l'état de fonctionnement habituel). Entrée pour mesurer.")
    a = measure("A")
    prompt("Retournez le capteur de 180° autour de la normale à sa semelle (embase à goupilles), "
           "attendez la stabilisation, puis Entrée.")
    b = measure("B (retourné)")
    a2 = None
    if with_return:
        prompt("Remettez le capteur en position A, attendez la stabilisation, puis Entrée.")
        a2 = measure("A2 (retour)")
    res = flip_calibration(a, b, a2)
    out(res.summary())
    if apply:
        if not res.reliable:
            raise RuntimeError("calibration non appliquée : résultat non fiable (voir avertissements)")
        client.command(res.command())
        if save:
            client.save()
        out(f"appliqué : {res.command()}" + (" + SAVE" if save else ""))
    return res
