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

Le biais calculé se règle avec `CAL TILT BIAS bx by [capteur]` (puis `SAVE`) : il est soustrait à la mesure
brute AVANT la rotation de montage éventuelle (CAL TILT ROT).

RÉSEAU DE N = 1…4 ACCÉLÉROMÈTRES. Chaque capteur a son biais ; la télémétrie donne pour chacun la lecture
brute compensée thermiquement `tr` (avant biais). Le retournement de TOUS les capteurs en même temps est
légitime : chaque capteur tourne autour de SA normale, la plaque ne bouge pas (`run_array_flip_procedure`).
Le retournement motorisé du capteur 0 (option matérielle) est piloté par le firmware (`FLIP RUN`) ;
`run_motorized_flip` le lance et lit le résultat, `schedule_flips` le répète (suivi du biais vs température).
Les pentes vraies (A − B)/2 aux positions des capteurs donnent, en plus, le champ de pente de la plaque
(courbure, gauchissement) : `fit_slope_field`.

Le biais d'un capteur est défini à la température de référence de son modèle thermique : la lecture `tr`
est déjà corrigée du décalage thermique ; si le modèle est inactif, le biais vaut à la température du retournement.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Callable, Sequence

import numpy as np

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
    sensor: int | None = None               # numéro du capteur (None : configuration à capteur unique)
    t_mean_c: float | None = None           # température moyenne de la base pendant la mesure

    @property
    def reliable(self) -> bool:
        return not any(w.startswith("dérive") or w.startswith("bruit") for w in self.warnings)

    def command(self) -> str:
        return proto.cmd_cal_tilt_bias(*self.bias_urad, sensor=self.sensor)

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
                     drift_sigmas: float = 4.0, max_bias_urad: float = 20000.0,
                     sensor: int | None = None) -> FlipResult:
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
    return FlipResult(bias, sig, slope, sig, a, b, drift, warnings, sensor)  # type: ignore[arg-type]


def run_flip_procedure(client, prompt: Callable[[str], None], n_samples: int = 100, hz: float = 10.0,
                       with_return: bool = True, apply: bool = False, save: bool = False,
                       out: Callable[[str], None] = print, sensor: int | None = None) -> FlipResult:
    """Procédure interactive de retournement d'UN capteur avec un AirtableClient.

    `prompt(message)` doit bloquer jusqu'à l'action de l'opérateur (input() en ligne de commande).
    `sensor` : numéro du capteur du réseau (None : configuration à capteur unique, commande sans indice).
    """
    def measure(label: str) -> list[Sample]:
        out(f"mesure {label} : {n_samples} échantillons à {hz:g} Hz ...")
        s = client.collect_tilt_raw(n_samples, hz=hz, sensor=sensor or 0)
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
    res = flip_calibration(a, b, a2, sensor=sensor)
    out(res.summary())
    if apply:
        if not res.reliable:
            raise RuntimeError("calibration non appliquée : résultat non fiable (voir avertissements)")
        client.command(res.command())
        if save:
            client.save()
        out(f"appliqué : {res.command()}" + (" + SAVE" if save else ""))
    return res


# =============================================================================================
#  Réseau de capteurs : retournement simultané, champ de pente, retournement motorisé
# =============================================================================================

DEFAULT_POSITIONS_MM: dict[int, tuple[float, float]] = {
    0: (-200.0, -200.0), 1: (200.0, -200.0), 2: (200.0, 200.0), 3: (-200.0, 200.0)}   # = firmware/include/config.h


@dataclass
class SlopeFieldFit:
    """Champ de pente θx = a0 + a1·x + a2·y, θy = b0 + b1·x + b2·y ajusté sur les capteurs [µrad, mm]."""
    mean_slope_urad: tuple[float, float]       # pente au barycentre des capteurs
    zxx: float                                 # ∂θx/∂x [µrad/m] = ∂²z/∂x²
    zxy: float                                 # ½(∂θx/∂y + ∂θy/∂x)
    zyy: float
    curl: float                                # ½(∂θx/∂y − ∂θy/∂x) : nul pour une surface réelle (erreur de mesure)
    spread_urad: tuple[float, float]           # max − min par axe
    residual_rms_urad: float                   # écart au modèle linéaire (nul à 3 capteurs)
    n: int

    @property
    def sag_um_per_100mm_span(self) -> float:
        """Flèche d'une cuvette de courbure z_xx sur 100 mm : κ·L²/8 [µm] (ordre de grandeur)."""
        return abs(self.zxx) * 0.1 ** 2 / 8.0


def fit_slope_field(positions_mm: Sequence[tuple[float, float]], slopes_urad: Sequence[tuple[float, float]]) -> SlopeFieldFit:
    """Ajuste le champ de pente sur ≥ 3 capteurs non alignés (miroir de atc::fitSlopeField)."""
    P = np.asarray(positions_mm, float) * 1e-3          # m
    S = np.asarray(slopes_urad, float)
    n = len(P)
    if n < 3:
        raise ValueError("au moins 3 capteurs pour ajuster un champ de pente")
    c = P.mean(axis=0)
    X = np.column_stack([np.ones(n), P[:, 0] - c[0], P[:, 1] - c[1]])
    if np.linalg.matrix_rank(X) < 3:
        raise ValueError("capteurs alignés : champ de pente indéterminé")
    coef, *_ = np.linalg.lstsq(X, S, rcond=None)        # colonnes : θx, θy
    res = S - X @ coef
    a1, a2, b1, b2 = coef[1, 0], coef[2, 0], coef[1, 1], coef[2, 1]
    return SlopeFieldFit((float(coef[0, 0]), float(coef[0, 1])), float(a1), float(0.5 * (a2 + b1)), float(b2),
                         float(0.5 * (a2 - b1)), (float(np.ptp(S[:, 0])), float(np.ptp(S[:, 1]))),
                         float(np.sqrt(np.mean(res ** 2))) if n > 3 else 0.0, n)


@dataclass
class ArrayResult:
    results: dict[int, FlipResult]
    slope_field: SlopeFieldFit | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def reliable(self) -> bool:
        return all(r.reliable for r in self.results.values())

    def commands(self) -> list[str]:
        return [r.command() for _, r in sorted(self.results.items())]

    def summary(self) -> str:
        lines = []
        for i, r in sorted(self.results.items()):
            lines.append(f"capteur {i} : biais ({r.bias_urad[0]:+8.2f}, {r.bias_urad[1]:+8.2f}) ± "
                         f"({r.bias_sigma_urad[0]:.2f}, {r.bias_sigma_urad[1]:.2f}) µrad ; pente au site "
                         f"({r.slope_a_urad[0]:+8.2f}, {r.slope_a_urad[1]:+8.2f}) µrad"
                         + ("" if r.reliable else "  [NON FIABLE]"))
        f = self.slope_field
        if f is not None:
            lines.append(f"champ de pente : plan moyen ({f.mean_slope_urad[0]:+.2f}, {f.mean_slope_urad[1]:+.2f}) µrad ; "
                         f"courbure zxx = {f.zxx:+.1f}, zxy = {f.zxy:+.1f}, zyy = {f.zyy:+.1f} µrad/m ; "
                         f"rotationnel {f.curl:+.1f} ; écart inter-capteurs ({f.spread_urad[0]:.1f}, {f.spread_urad[1]:.1f}) µrad")
        lines += [f"AVERTISSEMENT : {w}" for w in self.warnings]
        return "\n".join(lines)


def run_array_flip_procedure(client, prompt: Callable[[str], None], sensors: Sequence[int] = (0, 1, 2, 3),
                             positions_mm: dict[int, tuple[float, float]] | None = None, n_samples: int = 100,
                             hz: float = 10.0, with_return: bool = True, apply: bool = False, save: bool = False,
                             out: Callable[[str], None] = print) -> ArrayResult:
    """Retournement MANUEL simultané des capteurs `sensors` : une série A, B (et A2) pour tous à la fois.

    Chaque capteur est retourné de 180° autour de sa propre normale (embase à goupilles) ; la plaque ne
    bouge pas. Le résultat comporte un biais par capteur et le champ de pente de la plaque.
    """
    sensors = tuple(sensors)
    positions = positions_mm or DEFAULT_POSITIONS_MM

    def measure(label: str) -> dict[int, list[Sample]]:
        out(f"mesure {label} : {n_samples} échantillons à {hz:g} Hz sur {len(sensors)} capteurs ...")
        d = client.collect_tilt_array(n_samples, hz=hz, sensors=sensors)
        short = [i for i, v in d.items() if len(v) < n_samples]
        if short:
            raise RuntimeError(f"capteur(s) {short} : échantillons valides insuffisants en {label}")
        return d

    prompt(f"Position A : les capteurs {list(sensors)} sont posés sur leur semelle, plaque immobile et au repos "
           "(ventilateur dans l'état de fonctionnement habituel). Entrée pour mesurer.")
    a = measure("A")
    prompt("Retournez CHAQUE capteur de 180° autour de la normale à sa semelle, attendez la stabilisation, puis Entrée.")
    b = measure("B (retournés)")
    a2 = None
    if with_return:
        prompt("Remettez chaque capteur en position A, attendez la stabilisation, puis Entrée.")
        a2 = measure("A2 (retour)")
    results = {i: flip_calibration(a[i], b[i], a2[i] if a2 else None, sensor=i) for i in sensors}
    warns: list[str] = []
    fld = None
    if len(sensors) >= 3:
        try:
            fld = fit_slope_field([positions[i] for i in sensors], [results[i].slope_a_urad for i in sensors])
        except ValueError as e:
            warns.append(str(e))
    res = ArrayResult(results, fld, warns)
    out(res.summary())
    if apply:
        if not res.reliable:
            raise RuntimeError("calibration non appliquée : résultat non fiable (voir avertissements)")
        for line in res.commands():
            client.command(line)
        if save:
            client.save()
        out("appliqué : " + " ; ".join(res.commands()) + (" + SAVE" if save else ""))
    return res


def _flip_result_from_reply(rep: dict, sensor: int | None) -> FlipResult:
    zero = (0.0, 0.0)
    bias = tuple(rep["bias"])
    slope = tuple(rep["slope"])
    drift = tuple(rep.get("drift", zero))
    warns = [] if rep.get("reliable", True) else \
        [f"dérive entre les deux mesures à 0° : ({drift[0]:+.2f}, {drift[1]:+.2f}) µrad ; recommencer après stabilisation"]
    empty = SeriesStats(rep.get("na", 0), zero, zero, zero)
    return FlipResult(bias, zero, slope, zero, empty, SeriesStats(rep.get("nb", 0), zero, zero, zero),  # type: ignore[arg-type]
                      drift, warns, sensor, rep.get("T_mean"))


def run_motorized_flip(client, avg_s: float | None = None, apply: bool = False, save: bool = False,
                       poll_s: float = 2.0, timeout_s: float | None = None,
                       out: Callable[[str], None] = print, sleep: Callable[[float], None] = time.sleep,
                       now: Callable[[], float] = time.monotonic, sensor: int = 0) -> FlipResult:
    """Lance `FLIP RUN` (séquence automatique 0° → 180° → 0° dans le firmware), attend la fin, lit le résultat.

    Durée typique : 3 × durée de mesure + 2 rotations + attentes ≈ 90 s avec 20 s par position.
    Lève RuntimeError si la séquence échoue ; avec `apply`, envoie `FLIP APPLY` (+ `SAVE`) si le résultat est fiable.
    """
    avg = 20.0 if avg_s is None else avg_s
    client.flip_run(avg_s)
    deadline = now() + (timeout_s if timeout_s is not None else 3 * avg + 90.0)
    out(f"retournement motorisé lancé ({avg:g} s par position) ...")
    while True:
        st = client.flip_status()
        if st["state"] == "done":
            break
        if st["state"] == "failed":
            raise RuntimeError(f"retournement échoué : {st.get('err')}")
        if now() > deadline:
            client.flip_abort()
            raise TimeoutError("retournement motorisé trop long (abandon envoyé)")
        sleep(poll_s)
    res = _flip_result_from_reply(st, sensor)
    out(res.summary())
    if apply:
        if not res.reliable:
            raise RuntimeError("calibration non appliquée : résultat non fiable (voir avertissements)")
        client.flip_apply()
        if save:
            client.save()
        out("appliqué : FLIP APPLY" + (" + SAVE" if save else ""))
    return res


def fit_bias_vs_temperature(points: Sequence[tuple[float, float, float]], order: int = 1) -> dict:
    """Ajuste biais(T) = b0 + c1·(T − Tref) + c2·(T − Tref)² sur des retournements faits à des températures
    différentes (T, bx, by). Contrôle croisé de l'apprentissage thermique du firmware : seul le retournement
    isole le biais du capteur de la pente vraie de la plaque. Tref = première température."""
    if order not in (1, 2):
        raise ValueError("ordre 1 ou 2")
    pts = np.asarray(points, float)
    if len(pts) < order + 2:
        raise ValueError(f"au moins {order + 2} retournements pour l'ordre {order}")
    t_ref = float(pts[0, 0])
    d = pts[:, 0] - t_ref
    if np.ptp(pts[:, 0]) < 0.5:
        raise ValueError("excursion de température < 0,5 K : ajustement impossible")
    out = {"t_ref_C": t_ref, "order": order, "span_K": float(np.ptp(pts[:, 0]))}
    for a, name in ((1, "x"), (2, "y")):
        coef = np.polyfit(d, pts[:, a], order)[::-1]
        out[f"b0_{name}"] = float(coef[0])
        out[f"c1_{name}"] = float(coef[1])
        out[f"c2_{name}"] = float(coef[2]) if order >= 2 else 0.0
        out[f"rms_{name}"] = float(np.sqrt(np.mean((np.polyval(coef[::-1], d) - pts[:, a]) ** 2)))
    return out


def schedule_flips(client, every_s: float, count: int, avg_s: float | None = None, apply: bool = False,
                   save: bool = False, log_path: str | None = None, out: Callable[[str], None] = print,
                   sleep: Callable[[float], None] = time.sleep, now: Callable[[], float] = time.monotonic,
                   **flip_kwargs) -> list[dict]:
    """Planifie `count` retournements motorisés espacés de `every_s` secondes (début à début).

    Chaque résultat est consigné (température, biais, pente au site, dérive) et, si `log_path`, ajouté à un
    CSV. Un retournement non fiable ou échoué est consigné sans être appliqué. Retourne la liste des lignes.
    """
    rows: list[dict] = []
    t_next = now()
    for k in range(count):
        wait = t_next - now()
        if wait > 0:
            sleep(wait)
        t_start = now()
        row: dict = {"k": k, "t_s": round(t_start, 1)}
        try:
            r = run_motorized_flip(client, avg_s, apply=apply, save=save, out=out, sleep=sleep, now=now, **flip_kwargs)
            row.update(ok=True, reliable=r.reliable, T_C=r.t_mean_c, bias_x=r.bias_urad[0], bias_y=r.bias_urad[1],
                       slope_x=r.slope_a_urad[0], slope_y=r.slope_a_urad[1],
                       drift_x=(r.drift_urad or (0, 0))[0], drift_y=(r.drift_urad or (0, 0))[1])
        except (RuntimeError, TimeoutError) as e:
            row.update(ok=False, error=str(e))
            out(f"retournement {k + 1}/{count} : {e}")
        rows.append(row)
        if log_path:
            import csv
            from pathlib import Path
            fields = ["k", "t_s", "ok", "reliable", "T_C", "bias_x", "bias_y", "slope_x", "slope_y", "drift_x", "drift_y", "error"]
            new = not Path(log_path).exists()
            with open(log_path, "a", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=fields)
                if new:
                    w.writeheader()
                w.writerow({k2: row.get(k2) for k2 in fields})
        t_next += every_s
    return rows
