"""Calibration par palets lâchés : pente locale de la plaque à partir de trajectoires (x, y, t).

Principe. Un palet porté par le film d'air, lâché sans vitesse, n'est soumis qu'à la composante de
la pesanteur dans le plan (et à un amortissement visqueux faible). Sur chaque axe :

        x(t) = x0 + v0·t + ½·a·t²                           (sans amortissement)
        v̇ = a − v/τ   ⇒   x(t) = x0 + v0·φ1(t) + a·φ2(t)      (amortissement visqueux, k = 1/τ)
        φ1 = (1 − e^(−kt))/k ,   φ2 = (kt − 1 + e^(−kt))/k²    (→ t et t²/2 quand k → 0)

et la pente locale (au sens « pente descendante vers +x ») est θ = a/g. Pour k fixé le modèle est
linéaire en (x0, v0, a) : moindres carrés ; k (commun à x et y) est cherché par balayage 1D
(projection de variable), retenu seulement si le critère BIC l'exige.

CONVENTIONS DE SIGNE (communes à tout le projet) :
  * θ_x = a_x/g > 0 : le palet dérive vers +X, la plaque DESCEND vers +X ;
  * le firmware raisonne en pente montante : tilt_x = ∂z/∂x = −θ_x ;
  * la correction renvoyée est la VARIATION de ∂z/∂x, ∂z/∂y à appliquer : d = +θ_moyen. Elle s'envoie
    par `LEVEL MOVE X d` / `LEVEL MOVE Y d` (déplacement immédiat des vérins) ou, pour que la boucle
    inclinométrique la conserve, par `LEVEL TARGET (cible_actuelle + d)`.

Unités : positions en mm, temps en s, accélérations en mm/s², pentes en µrad.
La détection vidéo (OpenCV) est facultative : `track_pucks_video` importe cv2 à l'appel.
"""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Sequence

import numpy as np

G_DEFAULT = 9.81   # m/s² (params/design.toml : environment.g)
MM_PER_M = 1000.0


def design_defaults() -> dict:
    """Valeurs de params/design.toml si le dépôt est accessible (lancement depuis la racine)."""
    d = {"g": G_DEFAULT, "slope_peak_urad": 50.0, "working_square_mm": 300.0}
    try:  # pragma: no cover - dépend du répertoire courant
        from calc.common.params import load_params
        P = load_params()
        d["g"] = float(P["environment"]["g"])
        d["slope_peak_urad"] = float(P["performance_targets"]["residual_slope_peak_urad"])
        d["working_square_mm"] = float(P["zones"]["working_square_mm"])
    except Exception:
        pass
    return d


# =============================================================================================
#  Trajectoires et repère caméra
# =============================================================================================

@dataclass
class Trajectory:
    id: str
    t: np.ndarray      # s
    x: np.ndarray      # mm
    y: np.ndarray      # mm
    meta: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.t = np.asarray(self.t, float)
        self.x = np.asarray(self.x, float)
        self.y = np.asarray(self.y, float)
        if not (self.t.shape == self.x.shape == self.y.shape):
            raise ValueError("t, x, y de tailles différentes")
        order = np.argsort(self.t, kind="stable")
        self.t, self.x, self.y = self.t[order], self.x[order], self.y[order]

    def __len__(self) -> int:
        return len(self.t)


@dataclass
class CameraFrame:
    """Passage du repère caméra au repère plaque (celui de l'inclinomètre) : P = R·F·(P_cam − O)."""
    rot_deg: float = 0.0
    flip_x: bool = False
    flip_y: bool = False
    origin_mm: tuple[float, float] = (0.0, 0.0)

    def matrix(self) -> np.ndarray:
        th = math.radians(self.rot_deg)
        R = np.array([[math.cos(th), -math.sin(th)], [math.sin(th), math.cos(th)]])
        F = np.diag([-1.0 if self.flip_x else 1.0, -1.0 if self.flip_y else 1.0])
        return R @ F

    def apply(self, trajs: Sequence[Trajectory]) -> list[Trajectory]:
        M = self.matrix()
        o = np.asarray(self.origin_mm, float)
        out = []
        for tr in trajs:
            p = (np.stack([tr.x, tr.y], axis=1) - o) @ M.T
            out.append(Trajectory(tr.id, tr.t.copy(), p[:, 0], p[:, 1], dict(tr.meta)))
        return out


_ALIASES = {
    "id": ("id", "traj", "trajectory", "drop", "puck", "puck_id", "lacher", "essai"),
    "t": ("t", "t_s", "time", "time_s", "temps", "temps_s"),
    "t_ms": ("t_ms", "time_ms"),
    "frame": ("frame", "image"),
    "x": ("x", "x_mm"),
    "y": ("y", "y_mm"),
}


def _col(header: list[str], key: str) -> int | None:
    low = [h.strip().lower() for h in header]
    for a in _ALIASES[key]:
        if a in low:
            return low.index(a)
    return None


def load_trajectories_csv(path: str | Path, fps: float | None = None, scale: float = 1.0) -> list[Trajectory]:
    """Lit un CSV (en-tête obligatoire) : colonnes id (facultative), t|t_ms|frame, x, y [mm].

    `scale` multiplie x et y (ex. 0,2 si le CSV est en pixels à 0,2 mm/px) ; `fps` est requis si le
    temps est donné en numéro d'image (colonne frame).
    """
    with open(path, newline="", encoding="utf-8-sig") as f:
        sample = f.read(4096)
        f.seek(0)
        delim = ";" if sample.count(";") > sample.count(",") else ","
        rd = csv.reader(f, delimiter=delim)
        header = next(rd)
        ix, iy = _col(header, "x"), _col(header, "y")
        it, itms, ifr = _col(header, "t"), _col(header, "t_ms"), _col(header, "frame")
        iid = _col(header, "id")
        if ix is None or iy is None or (it is None and itms is None and ifr is None):
            raise ValueError(f"{path} : colonnes x, y et t (ou t_ms / frame) requises ; trouvé {header}")
        if it is None and itms is None and fps is None:
            raise ValueError("temps en numéro d'image : préciser fps")
        groups: dict[str, list[tuple[float, float, float]]] = {}
        for lineno, row in enumerate(rd, start=2):
            if not row or all(not c.strip() for c in row):
                continue
            try:
                if it is not None:
                    tt = float(row[it])
                elif itms is not None:
                    tt = float(row[itms]) / 1000.0
                else:
                    tt = float(row[ifr]) / float(fps)   # type: ignore[arg-type]
                xx, yy = float(row[ix]) * scale, float(row[iy]) * scale
            except (ValueError, IndexError) as e:
                raise ValueError(f"{path}:{lineno} : ligne illisible ({e})") from None
            if not (math.isfinite(tt) and math.isfinite(xx) and math.isfinite(yy)):
                continue                                  # point non détecté (NaN) : ignoré
            key = row[iid].strip() if iid is not None else "traj0"
            groups.setdefault(key, []).append((tt, xx, yy))
    out = []
    for key, pts in groups.items():
        a = np.array(pts)
        out.append(Trajectory(key, a[:, 0], a[:, 1], a[:, 2]))
    return out


def write_trajectories_csv(path: str | Path, trajs: Iterable[Trajectory]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "t_s", "x_mm", "y_mm"])
        for tr in trajs:
            for t, x, y in zip(tr.t, tr.x, tr.y):
                w.writerow([tr.id, f"{t:.6f}", f"{x:.5f}", f"{y:.5f}"])


# =============================================================================================
#  Ajustement d'une trajectoire
# =============================================================================================

def _phi(t: np.ndarray, k: float) -> tuple[np.ndarray, np.ndarray]:
    """Fonctions de base (φ1, φ2) du modèle à amortissement visqueux ; développement limité si kt petit."""
    t = np.asarray(t, float)
    if k <= 0.0:
        return t.copy(), 0.5 * t ** 2
    kt = k * t
    small = kt < 1e-3
    with np.errstate(over="ignore", invalid="ignore"):
        phi1 = np.where(small, t * (1 - kt / 2 + kt ** 2 / 6), -np.expm1(-kt) / k)
        phi2 = np.where(small, 0.5 * t ** 2 * (1 - kt / 3 + kt ** 2 / 12), (kt + np.expm1(-kt)) / k ** 2)
    return phi1, phi2


@dataclass
class AxisFit:
    x0: float
    v0: float
    a: float                 # mm/s²
    sigma_x0: float
    sigma_v0: float
    sigma_a: float           # conditionnel à k
    rms: float               # résidu rms [mm]
    n: int


def _design(t: np.ndarray, k: float, fix_v0: float | None) -> np.ndarray:
    p1, p2 = _phi(t, k)
    if fix_v0 is None:
        return np.stack([np.ones_like(t), p1, p2], axis=1)
    return np.stack([np.ones_like(t), p2], axis=1)


def _solve(A: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, float, np.ndarray]:
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    r = y - A @ coef
    rss = float(r @ r)
    cov0 = np.linalg.pinv(A.T @ A)
    return coef, rss, cov0


def _fit_axis(t: np.ndarray, x: np.ndarray, k: float, fix_v0: float | None,
              sigma_pos: float | None) -> tuple[AxisFit, float]:
    A = _design(t, k, fix_v0)
    p1, _ = _phi(t, k)
    y = x if fix_v0 is None else x - fix_v0 * p1
    coef, rss, cov0 = _solve(A, y)
    n, p = len(t), A.shape[1]
    s_res = math.sqrt(rss / max(n - p, 1))
    s = max(s_res, sigma_pos or 0.0)
    cov = cov0 * s ** 2
    if fix_v0 is None:
        x0, v0, a = coef
        sx0, sv0, sa = (math.sqrt(max(cov[i, i], 0.0)) for i in range(3))
    else:
        x0, a = coef
        v0 = fix_v0
        sx0, sa = math.sqrt(max(cov[0, 0], 0.0)), math.sqrt(max(cov[1, 1], 0.0))
        sv0 = 0.0
    return AxisFit(float(x0), float(v0), float(a), sx0, sv0, sa, s_res, n), rss


def _auto_k_grid(duration: float) -> np.ndarray:
    # τ de 0,3·T à 1000·T (au-delà, indiscernable de k = 0)
    return np.geomspace(1.0 / (1000.0 * duration), 3.0 / duration, 41)


@dataclass
class TrajFit:
    id: str
    x: AxisFit
    y: AxisFit
    k: float                         # 1/τ [1/s] (0 : pas d'amortissement)
    k_fitted: bool
    theta_x_urad: float              # a_x/g : pente descendante vers +X
    theta_y_urad: float
    sigma_theta_x_urad: float
    sigma_theta_y_urad: float
    x_mean_mm: float
    y_mean_mm: float
    duration_s: float
    n_used: int
    n_total: int
    ok: bool = True
    reason: str = ""

    @property
    def tau_s(self) -> float:
        return math.inf if self.k <= 0 else 1.0 / self.k


def fit_trajectory(traj: Trajectory, damping: str | float = "none", fix_v0: float | None = None,
                   t_min: float | None = None, t_max: float | None = None,
                   sigma_pos_mm: float | None = None, robust: bool = True,
                   g: float = G_DEFAULT, bic_margin: float = 2.0, min_points: int = 8) -> TrajFit:
    """Ajuste x(t), y(t) d'une trajectoire et en déduit θ = a/g.

    damping : "none" (k = 0), "fit" (k commun à x et y estimé, retenu si ΔBIC > bic_margin) ou un
    nombre = τ imposé en secondes. fix_v0 : vitesse initiale imposée (0.0 pour un lâcher sans vitesse).
    t_min/t_max : fenêtre en secondes depuis le premier échantillon (exclure lâcher et rebonds).
    """
    t_all = traj.t - traj.t[0] if len(traj) else traj.t
    sel = np.isfinite(t_all) & np.isfinite(traj.x) & np.isfinite(traj.y)
    if t_min is not None:
        sel &= t_all >= t_min
    if t_max is not None:
        sel &= t_all <= t_max
    t = t_all[sel]
    xs, ys = traj.x[sel], traj.y[sel]
    n_total = int(sel.sum())

    def fail(reason: str) -> TrajFit:
        z = AxisFit(0, 0, 0, math.inf, math.inf, math.inf, math.inf, 0)
        return TrajFit(traj.id, z, z, 0.0, False, math.nan, math.nan, math.inf, math.inf,
                       float(np.mean(xs)) if n_total else math.nan, float(np.mean(ys)) if n_total else math.nan,
                       float(t[-1] - t[0]) if n_total > 1 else 0.0, 0, n_total, False, reason)

    p_axis = 2 if fix_v0 is not None else 3
    if n_total < max(min_points, p_axis + 3):
        return fail(f"trop peu de points ({n_total})")
    dur = float(t[-1] - t[0])
    if dur <= 0:
        return fail("durée nulle")
    t = t - t[0]

    mask = np.ones(len(t), bool)
    k = 0.0
    k_fitted = False
    grid = _auto_k_grid(dur)

    def total_rss(kk: float, m: np.ndarray) -> float:
        return (_fit_axis(t[m], xs[m], kk, fix_v0, sigma_pos_mm)[1]
                + _fit_axis(t[m], ys[m], kk, fix_v0, sigma_pos_mm)[1])

    for _ in range(4 if robust else 1):
        if isinstance(damping, (int, float)) and not isinstance(damping, bool):
            if damping <= 0:
                raise ValueError("tau imposé doit être > 0")
            k, k_fitted = 1.0 / float(damping), False
        elif damping == "fit":
            rss0 = total_rss(0.0, mask)
            vals = np.array([total_rss(kk, mask) for kk in grid])
            j = int(np.argmin(vals))
            lo, hi = grid[max(j - 1, 0)], grid[min(j + 1, len(grid) - 1)]
            # raffinement par section dorée en log(k)
            a_, b_ = math.log(lo), math.log(hi)
            gr = (math.sqrt(5) - 1) / 2
            c_, d_ = b_ - gr * (b_ - a_), a_ + gr * (b_ - a_)
            fc, fd = total_rss(math.exp(c_), mask), total_rss(math.exp(d_), mask)
            for _i in range(40):
                if fc < fd:
                    b_, d_, fd = d_, c_, fc
                    c_ = b_ - gr * (b_ - a_)
                    fc = total_rss(math.exp(c_), mask)
                else:
                    a_, c_, fc = c_, d_, fd
                    d_ = a_ + gr * (b_ - a_)
                    fd = total_rss(math.exp(d_), mask)
            k_best = math.exp((a_ + b_) / 2)
            rss_k = total_rss(k_best, mask)
            n_eq = 2 * int(mask.sum())
            dbic = n_eq * math.log(max(rss0, 1e-300) / max(rss_k, 1e-300)) - math.log(n_eq)
            if dbic > bic_margin and rss_k < rss0:
                k, k_fitted = k_best, True
            else:
                k, k_fitted = 0.0, False
        elif damping == "none":
            k, k_fitted = 0.0, False
        else:
            raise ValueError("damping : 'none', 'fit' ou τ en secondes")

        fx, _ = _fit_axis(t[mask], xs[mask], k, fix_v0, sigma_pos_mm)
        fy, _ = _fit_axis(t[mask], ys[mask], k, fix_v0, sigma_pos_mm)
        if not robust:
            break
        # rejet des valeurs aberrantes (MAD) sur les résidus des deux axes
        rx = xs - _model(t, fx, k)
        ry = ys - _model(t, fy, k)
        new = mask.copy()
        for r in (rx, ry):
            s = 1.4826 * float(np.median(np.abs(r[mask] - np.median(r[mask]))))
            s = max(s, 1e-9)
            new &= np.abs(r - np.median(r[mask])) < 5.0 * s
        if new.sum() < max(min_points, p_axis + 3) or np.array_equal(new, mask):
            break
        mask = new

    fx, rss_x = _fit_axis(t[mask], xs[mask], k, fix_v0, sigma_pos_mm)
    fy, rss_y = _fit_axis(t[mask], ys[mask], k, fix_v0, sigma_pos_mm)
    n_used = int(mask.sum())

    # Incertitude systématique due à k quand il est estimé : plage de a sur {k : ΔRSS ≤ 1 σ²}
    sa_x, sa_y = fx.sigma_a, fy.sigma_a
    if k_fitted or damping == "fit":
        rss_min = rss_x + rss_y
        dof = max(2 * n_used - 2 * p_axis - 1, 1)
        lim = rss_min * (1.0 + 1.0 / dof)
        ax_vals, ay_vals = [fx.a], [fy.a]
        for kk in np.concatenate([[0.0], grid]):
            if total_rss(float(kk), mask) <= lim:
                ax_vals.append(_fit_axis(t[mask], xs[mask], float(kk), fix_v0, sigma_pos_mm)[0].a)
                ay_vals.append(_fit_axis(t[mask], ys[mask], float(kk), fix_v0, sigma_pos_mm)[0].a)
        sa_x = math.hypot(sa_x, 0.5 * (max(ax_vals) - min(ax_vals)))
        sa_y = math.hypot(sa_y, 0.5 * (max(ay_vals) - min(ay_vals)))

    to_urad = 1e6 / (g * MM_PER_M)          # mm/s² → µrad
    return TrajFit(traj.id, fx, fy, k, k_fitted, fx.a * to_urad, fy.a * to_urad,
                   sa_x * to_urad, sa_y * to_urad, float(np.mean(xs[mask])), float(np.mean(ys[mask])),
                   dur, n_used, n_total, True, "")


def _model(t: np.ndarray, f: AxisFit, k: float) -> np.ndarray:
    p1, p2 = _phi(t, k)
    return f.x0 + f.v0 * p1 + f.a * p2


def expected_sigma_theta_urad(duration_s: float, n_points: int, sigma_pos_mm: float,
                              fix_v0: float | None = None, k: float = 0.0, g: float = G_DEFAULT) -> float:
    """Incertitude théorique (1σ) sur θ = a/g pour un lâcher de durée T, n images, bruit de position σ."""
    t = np.linspace(0.0, duration_s, n_points)
    A = _design(t, k, fix_v0)
    cov = np.linalg.inv(A.T @ A) * sigma_pos_mm ** 2
    return math.sqrt(cov[-1, -1]) * 1e6 / (g * MM_PER_M)


# =============================================================================================
#  Échantillons de pente, carte, champ de hauteur
# =============================================================================================

@dataclass
class SlopeSamples:
    x_mm: np.ndarray
    y_mm: np.ndarray
    theta_x: np.ndarray     # µrad, pente descendante vers +X (a/g)
    theta_y: np.ndarray
    sigma_x: np.ndarray
    sigma_y: np.ndarray
    ids: list[str]

    def __len__(self) -> int:
        return len(self.x_mm)


def slope_samples(fits: Sequence[TrajFit], max_sigma_urad: float = 100.0) -> SlopeSamples:
    use = [f for f in fits if f.ok and f.sigma_theta_x_urad < max_sigma_urad
           and f.sigma_theta_y_urad < max_sigma_urad]
    return SlopeSamples(
        np.array([f.x_mean_mm for f in use]), np.array([f.y_mean_mm for f in use]),
        np.array([f.theta_x_urad for f in use]), np.array([f.theta_y_urad for f in use]),
        np.array([max(f.sigma_theta_x_urad, 1e-3) for f in use]),
        np.array([max(f.sigma_theta_y_urad, 1e-3) for f in use]), [f.id for f in use])


@dataclass
class SlopeMap:
    x_centers: np.ndarray
    y_centers: np.ndarray
    theta_x: np.ndarray      # (ny, nx) µrad, NaN si cellule vide
    theta_y: np.ndarray
    sigma_x: np.ndarray
    sigma_y: np.ndarray
    count: np.ndarray

    def to_text(self) -> str:
        lines = ["carte de pente de dérive θ = a/g [µrad] (X|Y), lignes de y décroissant :"]
        for j in range(len(self.y_centers) - 1, -1, -1):
            cells = []
            for i in range(len(self.x_centers)):
                if self.count[j, i] == 0:
                    cells.append("      --      ")
                else:
                    cells.append(f"{self.theta_x[j, i]:+6.1f}|{self.theta_y[j, i]:+6.1f}")
            lines.append(f"y={self.y_centers[j]:+7.1f} : " + "  ".join(cells))
        lines.append("x =           " + "  ".join(f"{x:^13.1f}" for x in self.x_centers))
        return "\n".join(lines)


def slope_map(s: SlopeSamples, extent_mm: tuple[float, float, float, float] = (-150, 150, -150, 150),
              nx: int = 5, ny: int = 5) -> SlopeMap:
    """Moyenne pondérée (1/σ²) des pentes par cellule d'une grille régulière."""
    x0, x1, y0, y1 = extent_mm
    xe, ye = np.linspace(x0, x1, nx + 1), np.linspace(y0, y1, ny + 1)
    xc, yc = 0.5 * (xe[:-1] + xe[1:]), 0.5 * (ye[:-1] + ye[1:])
    shape = (ny, nx)
    tx, ty = np.full(shape, np.nan), np.full(shape, np.nan)
    sx, sy = np.full(shape, np.nan), np.full(shape, np.nan)
    cnt = np.zeros(shape, int)
    ix = np.clip(np.searchsorted(xe, s.x_mm, side="right") - 1, 0, nx - 1)
    iy = np.clip(np.searchsorted(ye, s.y_mm, side="right") - 1, 0, ny - 1)
    inside = (s.x_mm >= x0) & (s.x_mm <= x1) & (s.y_mm >= y0) & (s.y_mm <= y1)
    for j in range(ny):
        for i in range(nx):
            m = inside & (ix == i) & (iy == j)
            if not m.any():
                continue
            wx, wy = 1.0 / s.sigma_x[m] ** 2, 1.0 / s.sigma_y[m] ** 2
            tx[j, i] = float(np.sum(wx * s.theta_x[m]) / wx.sum())
            ty[j, i] = float(np.sum(wy * s.theta_y[m]) / wy.sum())
            sx[j, i], sy[j, i] = 1 / math.sqrt(wx.sum()), 1 / math.sqrt(wy.sum())
            cnt[j, i] = int(m.sum())
    return SlopeMap(xc, yc, tx, ty, sx, sy, cnt)


def _terms(order: int) -> list[tuple[int, int]]:
    return [(i, d - i) for d in range(1, order + 1) for i in range(d, -1, -1)]


@dataclass
class HeightField:
    """Surface z(x, y) polynomiale reconstruite à partir des pentes (à une constante près)."""
    order: int
    center_mm: tuple[float, float]
    scale_mm: float
    terms: list[tuple[int, int]]
    coef_um: np.ndarray            # coefficients des monômes u^i v^j [µm]
    cov_um2: np.ndarray
    chi2_red: float
    cond: float

    def _uv(self, x, y):
        return (np.asarray(x, float) - self.center_mm[0]) / self.scale_mm, \
               (np.asarray(y, float) - self.center_mm[1]) / self.scale_mm

    def gradient_rows(self, x, y) -> tuple[np.ndarray, np.ndarray]:
        """Lignes (n, p) donnant ∂z/∂x et ∂z/∂y [µrad] comme fonctions linéaires des coefficients."""
        u, v = self._uv(x, y)
        u, v = np.atleast_1d(u), np.atleast_1d(v)
        K = 1e3 / self.scale_mm
        gx = np.zeros((len(u), len(self.terms)))
        gy = np.zeros_like(gx)
        for c, (i, j) in enumerate(self.terms):
            if i > 0:
                gx[:, c] = K * i * u ** (i - 1) * v ** j
            if j > 0:
                gy[:, c] = K * j * u ** i * v ** (j - 1)
        return gx, gy

    def surface_gradient_urad(self, x, y) -> tuple[np.ndarray, np.ndarray]:
        gx, gy = self.gradient_rows(x, y)
        return gx @ self.coef_um, gy @ self.coef_um

    def drift_slope_urad(self, x, y) -> tuple[np.ndarray, np.ndarray]:
        """θ = −∂z/∂(x,y) : pente descendante, la grandeur mesurée par les palets."""
        a, b = self.surface_gradient_urad(x, y)
        return -a, -b

    def height_um(self, x, y) -> np.ndarray:
        u, v = self._uv(x, y)
        u, v = np.atleast_1d(u), np.atleast_1d(v)
        return sum(c * u ** i * v ** j for c, (i, j) in zip(self.coef_um, self.terms))


def fit_height_field(s: SlopeSamples, order: int = 3,
                     extent_mm: tuple[float, float, float, float] = (-150, 150, -150, 150)) -> HeightField:
    """Ajuste z(x,y) polynomial (degré `order`, termes de degré 1..order) sur les pentes mesurées.

    Chaque trajectoire donne deux équations (∂z/∂x = −θx, ∂z/∂y = −θy) pondérées par 1/σ.
    """
    x0, x1, y0, y1 = extent_mm
    center = (0.5 * (x0 + x1), 0.5 * (y0 + y1))
    scale = 0.5 * max(x1 - x0, y1 - y0)
    terms = _terms(order)
    p = len(terms)
    if 2 * len(s) < p:
        raise ValueError(f"{len(s)} trajectoires insuffisantes pour un polynôme de degré {order} ({p} coefficients)")
    hf = HeightField(order, center, scale, terms, np.zeros(p), np.zeros((p, p)), math.nan, math.nan)
    gx, gy = hf.gradient_rows(s.x_mm, s.y_mm)
    A = np.vstack([gx / s.sigma_x[:, None], gy / s.sigma_y[:, None]])
    b = np.concatenate([-s.theta_x / s.sigma_x, -s.theta_y / s.sigma_y])
    coef, *_ = np.linalg.lstsq(A, b, rcond=None)
    r = b - A @ coef
    dof = max(len(b) - p, 1)
    chi2 = float(r @ r) / dof
    cov = np.linalg.pinv(A.T @ A) * max(chi2, 1.0)    # inflation si le modèle ne suffit pas
    hf.coef_um, hf.cov_um2, hf.chi2_red = coef, cov, chi2
    hf.cond = float(np.linalg.cond(A))
    return hf


# =============================================================================================
#  Correction d'inclinaison (plan moyen)
# =============================================================================================

@dataclass
class Correction:
    method: str                                   # "samples" ou "field"
    criterion: str                                # "mean" ou "peak"
    d_slope_urad: tuple[float, float]             # variation de ∂z/∂x, ∂z/∂y à appliquer = +θ_moyen
    sigma_urad: tuple[float, float]
    residual_rms_urad: float                      # pente non plane restante (rms du module)
    residual_peak_urad: float                     # (crête du module)
    n_samples: int
    warnings: list[str] = field(default_factory=list)

    def level_move_commands(self, min_urad: float = 0.5) -> list[str]:
        cmds = []
        for axis, d in zip("XY", self.d_slope_urad):
            if abs(d) >= min_urad:
                cmds.append(f"LEVEL MOVE {axis} {d:.2f}")
        return cmds

    def level_target_command(self, current_target: tuple[float, float] = (0.0, 0.0)) -> str:
        return (f"LEVEL TARGET {current_target[0] + self.d_slope_urad[0]:.2f} "
                f"{current_target[1] + self.d_slope_urad[1]:.2f}")


def _min_enclosing_center(pts: np.ndarray, iters: int = 2000) -> np.ndarray:
    """Centre du plus petit cercle englobant (algorithme de Bădoiu–Clarkson, approché)."""
    c = pts.mean(axis=0)
    for i in range(1, iters + 1):
        far = pts[np.argmax(np.linalg.norm(pts - c, axis=1))]
        c = c + (far - c) / (i + 1)
    return c


def plan_correction(s: SlopeSamples, field_: HeightField | None = None, method: str = "auto",
                    criterion: str = "mean",
                    extent_mm: tuple[float, float, float, float] = (-150, 150, -150, 150),
                    grid_n: int = 41) -> Correction:
    """Calcule la correction d'inclinaison (plan moyen) de la zone de travail.

    method "samples" : moyenne pondérée des pentes mesurées (suppose un échantillonnage uniforme de la
    zone) ; "field" : moyenne du champ ajusté sur la zone (robuste à un échantillonnage inégal) ;
    "auto" : champ si disponible. criterion "mean" : minimise la pente rms restante ; "peak" : minimise
    la pente crête (centre du cercle englobant du champ de pentes).
    """
    warnings: list[str] = []
    if len(s) == 0:
        raise ValueError("aucune trajectoire exploitable")
    if method == "auto":
        method = "field" if field_ is not None else "samples"
    x0, x1, y0, y1 = extent_mm
    gx_, gy_ = np.meshgrid(np.linspace(x0, x1, grid_n), np.linspace(y0, y1, grid_n))
    if method == "field":
        if field_ is None:
            raise ValueError("method='field' exige un champ ajusté")
        tx, ty = field_.drift_slope_urad(gx_.ravel(), gy_.ravel())
        field_pts = np.stack([tx, ty], axis=1)
        if criterion == "mean":
            d = field_pts.mean(axis=0)
            rx, ry = field_.gradient_rows(gx_.ravel(), gy_.ravel())
            m = np.array([rx.mean(axis=0), ry.mean(axis=0)])          # moyenne du gradient de surface
            cov = m @ field_.cov_um2 @ m.T
            sig = (math.sqrt(max(cov[0, 0], 0)), math.sqrt(max(cov[1, 1], 0)))
        else:
            d = _min_enclosing_center(field_pts)
            sig = (0.0, 0.0)
            warnings.append("critère 'peak' : incertitude non propagée")
        res = np.linalg.norm(field_pts - d, axis=1)
        resid_rms, resid_peak = float(np.sqrt(np.mean(res ** 2))), float(res.max())
        if field_.chi2_red > 4.0:
            warnings.append(f"ajustement du champ médiocre (χ²réd = {field_.chi2_red:.1f}) : "
                            "augmenter le degré ou le nombre de lâchers")
    else:
        pts = np.stack([s.theta_x, s.theta_y], axis=1)
        wx, wy = 1.0 / s.sigma_x ** 2, 1.0 / s.sigma_y ** 2
        if criterion == "mean":
            d = np.array([np.sum(wx * s.theta_x) / wx.sum(), np.sum(wy * s.theta_y) / wy.sum()])
            stat = np.array([1 / math.sqrt(wx.sum()), 1 / math.sqrt(wy.sum())])
            scat = np.array([np.std(s.theta_x, ddof=1), np.std(s.theta_y, ddof=1)]) / math.sqrt(len(s)) \
                if len(s) > 1 else stat
            sig = tuple(float(max(a, b)) for a, b in zip(stat, scat))
        else:
            d = _min_enclosing_center(pts)
            sig = (0.0, 0.0)
            warnings.append("critère 'peak' : incertitude non propagée")
        res = np.linalg.norm(pts - d, axis=1)
        resid_rms, resid_peak = float(np.sqrt(np.mean(res ** 2))), float(res.max())
        if len(s) < 6:
            warnings.append(f"seulement {len(s)} trajectoires : répartition de la zone de travail incertaine")
    return Correction(method, criterion, (float(d[0]), float(d[1])), (float(sig[0]), float(sig[1])),
                      resid_rms, resid_peak, len(s), warnings)


# =============================================================================================
#  Analyse complète
# =============================================================================================

@dataclass
class DriftAnalysis:
    fits: list[TrajFit]
    samples: SlopeSamples
    slope_map: SlopeMap
    height_field: HeightField | None
    correction: Correction
    tau_median_s: float | None
    rejected: list[tuple[str, str]]
    warnings: list[str] = field(default_factory=list)


def analyze(trajs: Sequence[Trajectory], damping: str | float = "fit", fix_v0: float | None = None,
            grid: tuple[int, int] = (5, 5), poly_order: int = 3,
            extent_mm: tuple[float, float, float, float] | None = None, method: str = "auto",
            criterion: str = "mean", g: float | None = None, sigma_pos_mm: float | None = None,
            t_min: float | None = None, t_max: float | None = None,
            frame: CameraFrame | None = None) -> DriftAnalysis:
    """Chaîne complète : repère → ajustements → échantillons → carte → champ → correction."""
    dd = design_defaults()
    g = dd["g"] if g is None else g
    if extent_mm is None:
        h = dd["working_square_mm"] / 2
        extent_mm = (-h, h, -h, h)
    if frame is not None:
        trajs = frame.apply(trajs)
    fits = [fit_trajectory(tr, damping=damping, fix_v0=fix_v0, t_min=t_min, t_max=t_max,
                           sigma_pos_mm=sigma_pos_mm, g=g) for tr in trajs]
    rejected = [(f.id, f.reason) for f in fits if not f.ok]
    samples = slope_samples(fits)
    if len(samples) == 0:
        raise ValueError("aucune trajectoire exploitable : " + "; ".join(f"{i}: {r}" for i, r in rejected))
    smap = slope_map(samples, extent_mm, grid[0], grid[1])
    field_ = None
    warns: list[str] = []
    if len(samples) >= max(6, len(_terms(poly_order)) // 2 + 1):
        try:
            field_ = fit_height_field(samples, poly_order, extent_mm)
        except ValueError as e:
            warns.append(str(e))
    corr = plan_correction(samples, field_, method=method, criterion=criterion, extent_mm=extent_mm)
    taus = [f.tau_s for f in fits if f.ok and f.k_fitted]
    tau_med = float(np.median(taus)) if taus else None
    outside = int(np.sum((samples.x_mm < extent_mm[0]) | (samples.x_mm > extent_mm[1])
                         | (samples.y_mm < extent_mm[2]) | (samples.y_mm > extent_mm[3])))
    if outside:
        warns.append(f"{outside} trajectoire(s) centrée(s) hors de la zone de travail")
    return DriftAnalysis(fits, samples, smap, field_, corr, tau_med, rejected, warns + corr.warnings)


def format_report(an: DriftAnalysis, slope_peak_target_urad: float | None = None) -> str:
    c = an.correction
    tgt = design_defaults()["slope_peak_urad"] if slope_peak_target_urad is None else slope_peak_target_urad
    L = [f"{len(an.fits)} trajectoires, {len(an.samples)} exploitables ({len(an.rejected)} rejetées)"]
    if an.tau_median_s is not None:
        L.append(f"amortissement visqueux : τ médian = {an.tau_median_s:.1f} s")
    L.append("")
    L.append(an.slope_map.to_text())
    L.append("")
    L.append(f"correction ({c.method}, critère {c.criterion}) : "
             f"dz/dx {c.d_slope_urad[0]:+.2f} ± {c.sigma_urad[0]:.2f} µrad ; "
             f"dz/dy {c.d_slope_urad[1]:+.2f} ± {c.sigma_urad[1]:.2f} µrad")
    L.append(f"pente non plane restante après correction : rms {c.residual_rms_urad:.1f} µrad, "
             f"crête {c.residual_peak_urad:.1f} µrad (cible crête ≤ {tgt:.0f} µrad : "
             f"{'OK' if c.residual_peak_urad <= tgt else 'DÉPASSÉE'})")
    L.append("commandes : " + " ; ".join(c.level_move_commands() or ["(aucune : correction < 0,5 µrad)"]))
    L.append("ou, pour la conserver en boucle fermée : " + c.level_target_command())
    for w in an.warnings:
        L.append("AVERTISSEMENT : " + w)
    return "\n".join(L)


# =============================================================================================
#  Détection de palets sur vidéo (OpenCV facultatif)
# =============================================================================================

def track_pucks_video(path: str | Path, mm_per_px: float, dark_pucks: bool = False,
                      min_area_px: float = 60.0, max_area_px: float = 40000.0, min_circularity: float = 0.6,
                      max_jump_px: float = 40.0, max_missing: int = 3, min_len: int = 10,
                      origin_px: tuple[float, float] | None = None, flip_y: bool = True,
                      homography: Sequence[Sequence[float]] | None = None,
                      max_frames: int | None = None,
                      progress: Callable[[int], None] | None = None) -> list[Trajectory]:
    """Détecte des palets (disques clairs sur fond sombre, ou l'inverse) et construit leurs trajectoires.

    Seuillage d'Otsu → contours → centroïdes (précision sub-pixel par moments) → association au plus
    proche voisin avec seuil de saut. Conversion en mm : `homography` (3×3, px → mm) si fournie, sinon
    échelle `mm_per_px` autour de `origin_px` (centre de l'image par défaut), y inversé par défaut
    (axe y de l'image vers le bas). La précision dépend de l'optique : corriger la distorsion en amont.
    """
    try:
        import cv2  # type: ignore
    except ImportError as e:
        raise RuntimeError("OpenCV est requis pour la détection vidéo : pip install opencv-python-headless "
                           "(ou fournir des trajectoires CSV)") from e
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise FileNotFoundError(f"vidéo illisible : {path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    if fps <= 0:
        raise ValueError("fps de la vidéo inconnu")
    H = np.asarray(homography, float) if homography is not None else None
    tracks: list[dict] = []
    idx = 0
    while True:
        ok, img = cap.read()
        if not ok or (max_frames is not None and idx >= max_frames):
            break
        if origin_px is None:
            origin_px = (img.shape[1] / 2.0, img.shape[0] / 2.0)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        mode = cv2.THRESH_BINARY_INV if dark_pucks else cv2.THRESH_BINARY
        _, bw = cv2.threshold(gray, 0, 255, mode | cv2.THRESH_OTSU)
        bw = cv2.morphologyEx(bw, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        cnts, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        dets = []
        for c in cnts:
            area = cv2.contourArea(c)
            if not (min_area_px <= area <= max_area_px):
                continue
            per = cv2.arcLength(c, True)
            if per <= 0 or 4 * math.pi * area / per ** 2 < min_circularity:
                continue
            m = cv2.moments(c)
            if m["m00"] <= 0:
                continue
            dets.append((m["m10"] / m["m00"], m["m01"] / m["m00"]))
        used = set()
        for tr in tracks:
            if tr["missing"] > max_missing:
                continue
            best, bd = None, max_jump_px
            for j, (cx, cy) in enumerate(dets):
                if j in used:
                    continue
                d = math.hypot(cx - tr["last"][0], cy - tr["last"][1])
                if d < bd:
                    best, bd = j, d
            if best is None:
                tr["missing"] += 1
            else:
                used.add(best)
                tr["pts"].append((idx / fps, *dets[best]))
                tr["last"], tr["missing"] = dets[best], 0
        for j, d in enumerate(dets):
            if j not in used:
                tracks.append({"pts": [(idx / fps, *d)], "last": d, "missing": 0})
        idx += 1
        if progress and idx % 50 == 0:
            progress(idx)
    cap.release()
    out = []
    for n, tr in enumerate(t for t in tracks if len(t["pts"]) >= min_len):
        a = np.array(tr["pts"])
        if H is not None:
            p = np.c_[a[:, 1], a[:, 2], np.ones(len(a))] @ H.T
            xm, ym = p[:, 0] / p[:, 2], p[:, 1] / p[:, 2]
        else:
            xm = (a[:, 1] - origin_px[0]) * mm_per_px
            ym = (origin_px[1] - a[:, 2] if flip_y else a[:, 2] - origin_px[1]) * mm_per_px
        out.append(Trajectory(f"v{n}", a[:, 0], xm, ym, {"source": str(path)}))
    return out
