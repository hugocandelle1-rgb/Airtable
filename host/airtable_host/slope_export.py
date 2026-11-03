"""Export de la carte de pente / d'efforts parasites de la plaque pour le contrôle des robots.

Entrée : une `DriftAnalysis` (calibration par palets, drift_calibration.analyze). Sortie : une grille
régulière (x, y) → pente de dérive (θx, θy) et accélération équivalente (ax, ay), en JSON ou CSV, pour que le
contrôleur des robots compense par anticipation (feed-forward) la force que le plan incliné exerce sur un palet.

CONVENTIONS (identiques à drift_calibration, voir son en-tête) :
  * repère PLAQUE, x, y en mm, origine au centre de la zone de travail (comme les trajectoires) ;
  * θx > 0 : un palet libre dérive vers +X (la plaque DESCEND vers +X) ; θx = −∂z/∂x ;
  * accélération d'un palet libre (perturbation) : ax = g·θx , ay = g·θy ; en mm/s² : ax = g·θx·1e-3 (θ en µrad,
    g en m/s²) ; l'effort parasite sur un palet de masse m est F = m·a ;
  * anticipation : la commande doit ajouter F_ff = −m·a(x, y) (ou retrancher l'accélération a à l'accélération
    de consigne) ;
  * `plane = "raw"` : état mesuré de la plaque ; `plane = "corrected"` : après application de la correction du plan
    moyen (LEVEL MOVE / LEVEL TARGET) calculée par l'analyse — à utiliser une fois la correction appliquée.

Forme des données : `source = "field"` (surface polynomiale ajustée sur les pentes, lisse, avec incertitude) ou
`source = "map"` (moyennes par cellule de la carte, valeurs NaN/null là où aucun palet n'est passé).
`valid = false` signale une extrapolation (loin de toute trajectoire mesurée) ou une cellule vide.

Format JSON `airtable-slope-map` (version 1) : voir `docs/07_controle_commande.md` §« Carte de pente pour les robots ».
"""
from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import numpy as np

from . import drift_calibration as dc

FORMAT_NAME = "airtable-slope-map"
FORMAT_VERSION = 1

CONVENTIONS = (
    "repère plaque, x et y en mm ; theta = pente de dérive (µrad), theta_x > 0 : un palet libre dérive vers +x "
    "(theta_x = -dz/dx) ; accélération de perturbation a = g*theta (mm/s²) ; effort parasite F = m*a ; "
    "anticipation : ajouter -m*a à la commande"
)


@dataclass
class SlopeGrid:
    x_mm: np.ndarray                       # (nx,) croissant
    y_mm: np.ndarray                       # (ny,) croissant
    theta_x_urad: np.ndarray               # (ny, nx)
    theta_y_urad: np.ndarray
    sigma_x_urad: np.ndarray               # NaN si inconnu
    sigma_y_urad: np.ndarray
    valid: np.ndarray                      # (ny, nx) bool
    source: str                            # "field" ou "map"
    plane: str                             # "raw" ou "corrected"
    g: float = dc.G_DEFAULT
    correction_applied_urad: tuple[float, float] = (0.0, 0.0)
    n_trajectories: int = 0
    warnings: list[str] = field(default_factory=list)

    # accélérations équivalentes [mm/s²] : a = g·θ ; θ en µrad → ×1e-6, m → mm ×1e3
    @property
    def a_x_mm_s2(self) -> np.ndarray:
        return self.g * self.theta_x_urad * 1e-3

    @property
    def a_y_mm_s2(self) -> np.ndarray:
        return self.g * self.theta_y_urad * 1e-3

    def stats(self) -> dict:
        m = self.valid & np.isfinite(self.theta_x_urad) & np.isfinite(self.theta_y_urad)
        if not m.any():
            return {"n_valid": 0}
        mod = np.hypot(self.theta_x_urad[m], self.theta_y_urad[m])
        amod = np.hypot(self.a_x_mm_s2[m], self.a_y_mm_s2[m])
        return {"n_valid": int(m.sum()), "theta_rms_urad": float(np.sqrt(np.mean(mod ** 2))),
                "theta_peak_urad": float(mod.max()), "a_rms_mm_s2": float(np.sqrt(np.mean(amod ** 2))),
                "a_peak_mm_s2": float(amod.max()),
                "theta_mean_urad": [float(np.mean(self.theta_x_urad[m])), float(np.mean(self.theta_y_urad[m]))]}


def _nan_to_none(a: np.ndarray, nd: int = 4) -> list:
    return [[None if not math.isfinite(v) else round(float(v), nd) for v in row] for row in a]


def build_slope_grid(an: dc.DriftAnalysis, nx: int = 31, ny: int = 31,
                     extent_mm: tuple[float, float, float, float] | None = None, source: str = "auto",
                     plane: str = "raw", g: float | None = None, max_extrapolation_mm: float | None = None) -> SlopeGrid:
    """Échantillonne la carte de pente de `an` sur une grille régulière nx × ny couvrant `extent_mm`."""
    if source not in ("auto", "field", "map"):
        raise ValueError("source : auto, field ou map")
    if plane not in ("raw", "corrected"):
        raise ValueError("plane : raw ou corrected")
    dd = dc.design_defaults()
    g = dd["g"] if g is None else g
    if extent_mm is None:
        h = dd["working_square_mm"] / 2
        extent_mm = (-h, h, -h, h)
    x0, x1, y0, y1 = extent_mm
    xs, ys = np.linspace(x0, x1, nx), np.linspace(y0, y1, ny)
    gx, gy = np.meshgrid(xs, ys)
    pts_x, pts_y = gx.ravel(), gy.ravel()
    warns = list(an.warnings)
    if source == "auto":
        source = "field" if an.height_field is not None else "map"
    nan = np.full(gx.shape, np.nan)
    if source == "field":
        hf = an.height_field
        if hf is None:
            raise ValueError("source='field' exige un champ ajusté (trop peu de trajectoires)")
        tx, ty = hf.drift_slope_urad(pts_x, pts_y)
        rx, ry = hf.gradient_rows(pts_x, pts_y)
        sx = np.sqrt(np.maximum(np.einsum("ij,jk,ik->i", rx, hf.cov_um2, rx), 0.0))
        sy = np.sqrt(np.maximum(np.einsum("ij,jk,ik->i", ry, hf.cov_um2, ry), 0.0))
        theta_x, theta_y = tx.reshape(gx.shape), ty.reshape(gx.shape)
        sig_x, sig_y = sx.reshape(gx.shape), sy.reshape(gx.shape)
        # extrapolation : distance au palet le plus proche
        S = an.samples
        span = max(x1 - x0, y1 - y0)
        radius = max_extrapolation_mm if max_extrapolation_mm is not None else 0.3 * span
        dist = np.min(np.hypot(pts_x[:, None] - S.x_mm[None, :], pts_y[:, None] - S.y_mm[None, :]), axis=1)
        valid = (dist <= radius).reshape(gx.shape)
        if not valid.all():
            warns.append(f"{int((~valid).sum())} points de grille à plus de {radius:.0f} mm de toute trajectoire "
                         "(extrapolation, marqués valid=false)")
    else:
        sm = an.slope_map
        # chaque point de grille prend la valeur de sa cellule ; NaN (cellule vide) → invalide
        xe = np.concatenate([[sm.x_centers[0] - (sm.x_centers[1] - sm.x_centers[0]) / 2 if len(sm.x_centers) > 1 else x0],
                             (sm.x_centers[:-1] + sm.x_centers[1:]) / 2,
                             [sm.x_centers[-1] + (sm.x_centers[-1] - sm.x_centers[-2]) / 2 if len(sm.x_centers) > 1 else x1]])
        ye = np.concatenate([[sm.y_centers[0] - (sm.y_centers[1] - sm.y_centers[0]) / 2 if len(sm.y_centers) > 1 else y0],
                             (sm.y_centers[:-1] + sm.y_centers[1:]) / 2,
                             [sm.y_centers[-1] + (sm.y_centers[-1] - sm.y_centers[-2]) / 2 if len(sm.y_centers) > 1 else y1]])
        ix = np.clip(np.searchsorted(xe, gx, side="right") - 1, 0, len(sm.x_centers) - 1)
        iy = np.clip(np.searchsorted(ye, gy, side="right") - 1, 0, len(sm.y_centers) - 1)
        theta_x, theta_y = sm.theta_x[iy, ix], sm.theta_y[iy, ix]
        sig_x, sig_y = sm.sigma_x[iy, ix], sm.sigma_y[iy, ix]
        outside = (gx < xe[0]) | (gx > xe[-1]) | (gy < ye[0]) | (gy > ye[-1])
        valid = np.isfinite(theta_x) & np.isfinite(theta_y) & ~outside
        theta_x, theta_y = np.where(valid, theta_x, nan), np.where(valid, theta_y, nan)
    d = (0.0, 0.0)
    if plane == "corrected":
        d = an.correction.d_slope_urad          # variation de dz/dx à appliquer = +θ_moyen ; θ' = θ − d
        theta_x, theta_y = theta_x - d[0], theta_y - d[1]
    return SlopeGrid(xs, ys, theta_x, theta_y, sig_x, sig_y, valid, source, plane, g, (float(d[0]), float(d[1])),
                     len(an.fits), warns)


# ---- écriture -----------------------------------------------------------------------------------------

def to_dict(grid: SlopeGrid, created_utc: str | None = None) -> dict:
    """Représentation JSON (NaN → null) du format airtable-slope-map v1."""
    return {
        "format": FORMAT_NAME,
        "format_version": FORMAT_VERSION,
        "created_utc": created_utc or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "frame": "plate",
        "units": {"length": "mm", "theta": "urad", "accel": "mm/s^2", "sigma": "urad"},
        "conventions": CONVENTIONS,
        "g_m_s2": grid.g,
        "source": grid.source,
        "plane": grid.plane,
        "correction_applied_urad": list(grid.correction_applied_urad),
        "n_trajectories": grid.n_trajectories,
        "grid": {"nx": len(grid.x_mm), "ny": len(grid.y_mm), "x_mm": [round(float(v), 3) for v in grid.x_mm],
                 "y_mm": [round(float(v), 3) for v in grid.y_mm],
                 "layout": "fields[k][j][i] = valeur en (x_mm[i], y_mm[j]) ; j (y) croissant"},
        "fields": {
            "theta_x_urad": _nan_to_none(grid.theta_x_urad),
            "theta_y_urad": _nan_to_none(grid.theta_y_urad),
            "sigma_x_urad": _nan_to_none(grid.sigma_x_urad),
            "sigma_y_urad": _nan_to_none(grid.sigma_y_urad),
            "a_x_mm_s2": _nan_to_none(grid.a_x_mm_s2, 5),
            "a_y_mm_s2": _nan_to_none(grid.a_y_mm_s2, 5),
            "valid": [[bool(v) for v in row] for row in grid.valid],
        },
        "stats": grid.stats(),
        "warnings": grid.warnings,
    }


CSV_COLUMNS = ["x_mm", "y_mm", "theta_x_urad", "theta_y_urad", "sigma_x_urad", "sigma_y_urad",
               "a_x_mm_s2", "a_y_mm_s2", "valid"]


def write_json(grid: SlopeGrid, path: str | Path) -> None:
    Path(path).write_text(json.dumps(to_dict(grid), ensure_ascii=False, allow_nan=False, indent=1), encoding="utf-8")


def write_csv(grid: SlopeGrid, path: str | Path) -> None:
    """CSV : lignes de métadonnées `# clé: valeur` (pandas : comment='#'), puis une ligne par point de grille
    (y croissant en boucle externe, x croissant en boucle interne)."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        for k, v in (("format", f"{FORMAT_NAME} {FORMAT_VERSION}"), ("frame", "plate"), ("units", "x,y mm ; theta,sigma urad ; a mm/s^2"),
                     ("g_m_s2", grid.g), ("source", grid.source), ("plane", grid.plane),
                     ("conventions", CONVENTIONS)):
            f.write(f"# {k}: {v}\n")
        w = csv.writer(f)
        w.writerow(CSV_COLUMNS)
        ax, ay = grid.a_x_mm_s2, grid.a_y_mm_s2

        def cell(a, j, i, nd=4):
            v = a[j, i]
            return "" if not math.isfinite(v) else f"{v:.{nd}f}"
        for j, y in enumerate(grid.y_mm):
            for i, x in enumerate(grid.x_mm):
                w.writerow([f"{x:.3f}", f"{y:.3f}", cell(grid.theta_x_urad, j, i), cell(grid.theta_y_urad, j, i),
                            cell(grid.sigma_x_urad, j, i), cell(grid.sigma_y_urad, j, i),
                            cell(ax, j, i, 5), cell(ay, j, i, 5), int(grid.valid[j, i])])


def export(grid: SlopeGrid, path: str | Path, fmt: str = "json") -> list[Path]:
    """Écrit `path` (+ extension si fmt='both')."""
    p = Path(path)
    if fmt == "json":
        write_json(grid, p)
        return [p]
    if fmt == "csv":
        write_csv(grid, p)
        return [p]
    if fmt == "both":
        a, b = p.with_suffix(".json"), p.with_suffix(".csv")
        write_json(grid, a)
        write_csv(grid, b)
        return [a, b]
    raise ValueError("format : json, csv ou both")


# ---- côté consommateur (contrôle des robots) -------------------------------------------------------------

class SlopeMapField:
    """Lecture d'un export JSON et interpolation bilinéaire : accélération de perturbation et effort d'anticipation."""

    def __init__(self, data: dict):
        if data.get("format") != FORMAT_NAME or data.get("format_version") != FORMAT_VERSION:
            raise ValueError("fichier non reconnu (format airtable-slope-map v1 attendu)")
        self.x = np.asarray(data["grid"]["x_mm"], float)
        self.y = np.asarray(data["grid"]["y_mm"], float)
        f = data["fields"]
        conv = lambda a: np.array([[np.nan if v is None else v for v in row] for row in a], float)  # noqa: E731
        self.theta_x, self.theta_y = conv(f["theta_x_urad"]), conv(f["theta_y_urad"])
        self.valid = np.array(f["valid"], bool)
        self.g = float(data["g_m_s2"])
        self.meta = {k: data[k] for k in ("source", "plane", "created_utc", "n_trajectories")}

    @classmethod
    def load(cls, path: str | Path) -> "SlopeMapField":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def _interp(self, a: np.ndarray, x: float, y: float) -> float:
        i = int(np.clip(np.searchsorted(self.x, x) - 1, 0, len(self.x) - 2))
        j = int(np.clip(np.searchsorted(self.y, y) - 1, 0, len(self.y) - 2))
        tx = float(np.clip((x - self.x[i]) / (self.x[i + 1] - self.x[i]), 0.0, 1.0))
        ty = float(np.clip((y - self.y[j]) / (self.y[j + 1] - self.y[j]), 0.0, 1.0))
        v = (a[j, i] * (1 - tx) * (1 - ty) + a[j, i + 1] * tx * (1 - ty) + a[j + 1, i] * (1 - tx) * ty
             + a[j + 1, i + 1] * tx * ty)
        return float(v)

    def theta_urad(self, x_mm: float, y_mm: float) -> tuple[float, float]:
        """Pente de dérive (θx, θy) [µrad] ; NaN si la position est hors zone ou entourée de cellules invalides."""
        return self._interp(self.theta_x, x_mm, y_mm), self._interp(self.theta_y, x_mm, y_mm)

    def disturbance_accel_mm_s2(self, x_mm: float, y_mm: float) -> tuple[float, float]:
        tx, ty = self.theta_urad(x_mm, y_mm)
        return self.g * tx * 1e-3, self.g * ty * 1e-3

    def feedforward_force_N(self, mass_kg: float, x_mm: float, y_mm: float) -> tuple[float, float]:
        """Force à AJOUTER à la commande pour annuler l'effort parasite : −m·a (a en m/s²)."""
        ax, ay = self.disturbance_accel_mm_s2(x_mm, y_mm)
        return -mass_kg * ax * 1e-3, -mass_kg * ay * 1e-3
