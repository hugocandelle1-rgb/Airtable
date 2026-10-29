"""Comparaison des schémas d'appui de la plaque perforée.

Schémas :
  kelvin_eq    3 points en triangle équilatéral de rayon r (balayage de r) ;
  kelvin_ring  3 points sur l'axe du cadre supérieur (profilé 45×90, demi-côté
               s_ring) : 1 au milieu du côté arrière + 2 aux coins avant
               (au droit des pieds), ou position optimisée le long du cadre ;
  kelvin_opt   3 points (isocèle) optimisés dans la bande pleine de bordure
               (max(|x|,|y|) ∈ [s_min, s_max]) — demande des colonnettes à
               travers le plenum ;
  4pt          4 points aux coins d'un carré de demi-côté a (hyperstatique) ;
  wt9          « whiffletree » de Hindle 9 points (3 palonniers triangulaires,
               efforts égaux), optimisé dans la bande pleine ;
  perimeter    bande élastomère périmétrique (fondation de Winkler) qui sert
               aussi de joint.

Chemins d'effort de la pression :
  A  plenum solidaire du bâti + membrane souple : poussée p·A reprise par les
     appuis de la plaque (charge p sur le carré du joint, réactions variables) ;
  B  plenum (caisson) suspendu à la plaque : poussée auto-équilibrée (p vers le
     haut sur le carré intérieur du caisson, charge linéique vers le bas sur la
     ligne d'attache des parois) ; masse du caisson ajoutée au poids propre.

Pour chaque cas : flèche poids propre, variation 0 → p_max, pente locale
résiduelle (µrad) après retrait du plan des moindres carrés sur la zone de
travail (crête, RMS), PV, fréquences propres.

    python3 -m calc.structure.support_study          (≈ 2–3 min)
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla
from scipy.optimize import minimize

from calc.common.params import REPO_ROOT, load_params
from calc.structure.homogenization import plate_properties
from calc.structure.plate_fe import SquarePlate, bfs_shape

FIG = REPO_ROOT / "calc" / "structure" / "figures"
RES = REPO_ROOT / "calc" / "structure" / "results"

THICKNESSES_MM = (20, 25, 30, 35)

# -----------------------------------------------------------------------------
# Hypothèses géométriques de la structure (proposées ici, reportées dans
# results/recommended_params.toml)
# -----------------------------------------------------------------------------


def structure_hypotheses(P):
    pl, zo, pn = P["plate"], P["zones"], P["plenum"]
    s_in = pn["inner_square_mm"] / 2 * 1e-3            # face intérieure du cadre = paroi du plenum
    prof = 0.045                                         # largeur du profilé du cadre supérieur
    return dict(
        L=pl["outer_square_mm"] * 1e-3,
        s_work=zo["working_square_mm"] / 2 * 1e-3,
        s_perf=zo["perforated_square_mm"] / 2 * 1e-3,
        s_ring=s_in + prof / 2,                           # axe du cadre 45×90 (demi-côté)
        s_seal_A=s_in + 0.005,                            # ligne d'attache membrane sur la plaque (A)
        s_box_in_B=s_in,                                  # intérieur du caisson suspendu (B)
        s_box_wall_B=s_in + 0.005,                        # ligne d'attache des parois (B)
        m_box_B=8.0,                                      # masse caisson suspendu (parois Al 4 mm, fond 6 mm, déflecteur)
        s_min=zo["perforated_square_mm"] / 2 * 1e-3 + 0.010,   # bande pleine : ≥ 10 mm au-delà de la zone percée
        s_max=pl["outer_square_mm"] / 2 * 1e-3 - 0.015,        # ≥ 15 mm du bord
        p_max=P["operating"]["p_plenum_max_Pa"],
        g=P["environment"]["g"],
        k_support=4.0e7,          # raideur verticale d'un appui (Hertz + vérin), N/m (cf. kinematic_coupling)
        perim_band=(s_in + 0.0075, s_in + 0.0375),          # bande élastomère 30 mm de large
        perim_kf=2.0e9,           # N/m³ : EPDM 3 mm, module apparent de compression ~6 MPa
    )


# -----------------------------------------------------------------------------
# Construction du modèle
# -----------------------------------------------------------------------------


def build_plate(P, h_mm, n=104):
    H = structure_hypotheses(P)
    pr = plate_properties(P, h_mm * 1e-3)
    L = H["L"]
    pl = SquarePlate(L, n, 1.0, 1.0, 1.0)
    perf = (np.abs(pl.XC) < H["s_perf"]) & (np.abs(pl.YC) < H["s_perf"])
    D = np.where(perf, pr["D_perf"], pr["D_solid"])
    nu = np.where(perf, pr["nu_perf"], pr["nu"])
    m = np.where(perf, pr["m_perf"], pr["m_solid"])
    pl = SquarePlate(L, n, D, nu, m)
    pl.props = pr
    pl.H = H
    pl.mass_total = float((m * pl.a**2).sum())
    return pl


def square_mask(pl, s):
    return (np.abs(pl.XC) < s) & (np.abs(pl.YC) < s)


def loads(pl, path):
    """Vecteurs de charge (poids propre G, pression P à p_max) pour un chemin."""
    H = pl.H
    g, p = H["g"], H["p_max"]
    fG = pl.load_area(-pl.m * g)
    if path == "A":
        fP = pl.load_area(np.where(square_mask(pl, H["s_seal_A"] + 1e-9), p, 0.0))
    elif path == "B":
        s_w = H["s_box_wall_B"]
        fG = fG + pl.load_line_square(s_w, -H["m_box_B"] * g / (8 * s_w))
        A_in = (2 * H["s_box_in_B"]) ** 2
        fP = pl.load_area(np.where(square_mask(pl, H["s_box_in_B"] + 1e-9), p, 0.0))
        fP = fP + pl.load_line_square(s_w, -p * A_in / (8 * s_w))
    else:
        raise ValueError(path)
    return fG, fP


# -----------------------------------------------------------------------------
# Supports isostatiques généralisés (Kelvin = 3 pivots d'un point ;
# whiffletree = 3 pivots de 3 points, efforts répartis suivant λ)
# -----------------------------------------------------------------------------


class IsoSupport:
    """Calculateur rapide pour supports isostatiques : la répartition des
    réactions est connue par la statique, la déformée s'obtient par une
    résolution « plaque libre » d'un chargement auto-équilibré."""

    def __init__(self, pl):
        self.pl = pl
        self.R = pl.rigid_modes()
        self._green = {}

    def green(self, x, y):
        key = (round(x, 7), round(y, 7))
        if key not in self._green:
            self._green[key] = self.pl.solve_free_unchecked(self.pl.point_vector(x, y))
        return self._green[key]

    def solve(self, f, pivots):
        """pivots : liste de 3 listes [(x, y, λ), ...]. Retourne (d, réactions)."""
        res = self.R.T @ f  # [ΣF, ΣF·x, ΣF·y]
        cx = [sum(l * x for x, y, l in pv) for pv in pivots]
        cy = [sum(l * y for x, y, l in pv) for pv in pivots]
        A = np.array([[1, 1, 1], cx, cy])
        Rk = np.linalg.solve(A, -res)
        d = self.pl.solve_free_unchecked(f)
        for Rkk, pv in zip(Rk, pivots):
            for x, y, l in pv:
                d = d + Rkk * l * self.green(x, y)
        return d, Rk

    def support_plane_dev(self, d, pivots):
        """Flèche max (µm) par rapport au plan des pivots, zone de travail et plaque."""
        pl = self.pl
        z = [sum(l * (pl.point_vector(x, y) @ d) for x, y, l in pv) for pv in pivots]
        cx = [sum(l * x for x, y, l in pv) for pv in pivots]
        cy = [sum(l * y for x, y, l in pv) for pv in pivots]
        A = np.stack([np.ones(3), cx, cy], 1)
        c = np.linalg.solve(A, z)
        X, Y = pl.node_xy()
        wr = d[0::4] - (c[0] + c[1] * X + c[2] * Y)
        sel, _ = pl.zone_nodes(pl.H["s_work"])
        return float(np.abs(wr).max() * 1e6), float(np.abs(wr[sel]).max() * 1e6)


def _solve_free_unchecked(self, f):
    free, lu = self.free_solver()
    d = np.zeros(self.ndof)
    d[free] = lu.solve(f[free])
    return d


SquarePlate.solve_free_unchecked = _solve_free_unchecked


def kelvin_pivots(pts):
    return [[(x, y, 1.0)] for x, y in pts]


def equilateral(r, phi_deg=0.0):
    th = np.deg2rad(90 + phi_deg + np.array([0, 120, 240]))
    return [(r * np.cos(t), r * np.sin(t)) for t in th]


def isoceles(y1, x2, y2):
    return [(0.0, y1), (x2, y2), (-x2, y2)]


def wt9_pivots(r_in, r_out, beta_deg, phi_deg=0.0):
    """Hindle 9 points : triangle k = point intérieur (r_in, φk) + 2 extérieurs
    (r_out, φk ± β) ; pivot au barycentre → efforts égaux (λ = 1/3)."""
    pivots = []
    for k in range(3):
        ph = np.deg2rad(90 + phi_deg + 120 * k)
        b = np.deg2rad(beta_deg)
        pts = [(r_in * np.cos(ph), r_in * np.sin(ph)),
               (r_out * np.cos(ph + b), r_out * np.sin(ph + b)),
               (r_out * np.cos(ph - b), r_out * np.sin(ph - b))]
        pivots.append([(x, y, 1 / 3) for x, y in pts])
    return pivots


def band_violation(pl, pts):
    """Pénalité si un point sort de la bande pleine autorisée."""
    H = pl.H
    v = 0.0
    for x, y in pts:
        m = max(abs(x), abs(y))
        v += max(0, H["s_min"] - m) + max(0, m - H["s_max"])
    return v


# -----------------------------------------------------------------------------
# Évaluation
# -----------------------------------------------------------------------------


def eval_iso(iso, fG, fP, pivots, path):
    pl = iso.pl
    s = pl.H["s_work"]
    dG, RG = iso.solve(fG, pivots)
    dP, RP = iso.solve(fP, pivots)
    rG = pl.residual_slope(dG, s)
    rP = pl.residual_slope(dP, s)
    devG = iso.support_plane_dev(dG, pivots)
    devP = iso.support_plane_dev(dP, pivots)
    return dict(G=rG, P=rP, defl_G_plate_um=devG[0], defl_G_work_um=devG[1],
                defl_P_plate_um=devP[0], defl_P_work_um=devP[1],
                R_G_N=(-RG).tolist(), R_P_N=(-RP).tolist(), dG=dG, dP=dP)


def objective(r, wG=10.0, wP=5.0):
    return max(r["G"]["slope_peak_urad"] / wG, r["P"]["slope_peak_urad"] / wP)


def strip(r):
    return {k: v for k, v in r.items() if k not in ("dG", "dP")}


def eval_4pt(pl, fG, fP, a, delta=None):
    """4 appuis rigides en (±a, ±a), hyperstatique : compatibilité de
    planéité des 4 appuis (ou défaut de hauteur δ imposé)."""
    pts = [(a, a), (-a, a), (-a, -a), (a, -a)]
    Ns = [pl.point_vector(x, y) for x, y in pts]
    nvec = np.array([1, -1, 1, -1]) / 2.0
    hvec = sum(c * N for c, N in zip([1, -1, 1, -1], Ns))
    dh = pl.solve_free_unchecked(hvec)
    wh = nvec @ np.array([N @ dh for N in Ns])
    out = {}
    for name, f in (("G", fG), ("P", fP)):
        if f is None:
            continue
        Ftot = (pl.rigid_modes().T @ f)[0]
        f0 = f - Ftot / 4 * sum(Ns)
        d0 = pl.solve_free_unchecked(f0)
        w0 = nvec @ np.array([N @ d0 for N in Ns])
        t = -w0 / wh
        d = d0 + t * dh
        out[name] = (d, pl.residual_slope(d, pl.H["s_work"]))
    # sensibilité : défaut de hauteur de 1 µm sur un appui (charge nulle)
    t = 1e-6 * 0.5 / wh  # n·δ = 0.5 µm pour δ = (1,0,0,0) µm
    d = t * dh
    out["delta1um"] = (d, pl.residual_slope(d, pl.H["s_work"]), abs(t))
    return out


def eval_perimeter(pl, fG, fP, band, kf, warp_um=10.0):
    m = (np.maximum(np.abs(pl.XC), np.abs(pl.YC)) > band[0]) & \
        (np.maximum(np.abs(pl.XC), np.abs(pl.YC)) < band[1])
    Kf = pl.foundation(np.where(m, kf, 0.0))
    K = (pl.stiffness() + Kf).tocsc()
    lu = spla.splu(K)
    s = pl.H["s_work"]
    out = {}
    for name, f in (("G", fG), ("P", fP)):
        d = lu.solve(f)
        out[name] = (d, pl.residual_slope(d, s))
    # gauchissement du cadre : base en selle w_b = δ·x·y/s² (δ au coin du cadre)
    X, Y = pl.node_xy()
    sb = pl.H["s_ring"]
    delta = warp_um * 1e-6
    ub = np.zeros(pl.ndof)
    ub[0::4] = delta * X * Y / sb**2
    ub[1::4] = delta * Y / sb**2
    ub[2::4] = delta * X / sb**2
    ub[3::4] = delta / sb**2
    d = lu.solve(Kf @ ub)
    out["warp"] = (d, pl.residual_slope(d, s))
    # écrasement moyen sous poids propre (contrôle)
    out["crush_um"] = float(-np.mean(out["G"][0][0::4][np.isin(np.arange(pl.nn), np.where(
        (np.maximum(np.abs(X), np.abs(Y)) > band[0]) & (np.maximum(np.abs(X), np.abs(Y)) < band[1]))[0])]) * 1e6)
    return out


def modes(pl, spring_pts=None, kspring=None, Kextra=None, nmodes=6):
    K = pl.stiffness()
    if Kextra is not None:
        K = K + Kextra
    if spring_pts is not None:
        rows = []
        for x, y in spring_pts:
            g = pl.point_vector(x, y)
            nz = np.nonzero(g)[0]
            rows.append(sp.csc_matrix((g[nz], (nz, np.zeros(len(nz), int))), shape=(pl.ndof, 1)))
        G = sp.hstack(rows)
        K = K + kspring * (G @ G.T)
    M = pl.mass()
    vals, vecs = spla.eigsh(K.tocsc(), k=nmodes, M=M.tocsc(), sigma=-1.0, which="LM")
    f = np.sqrt(np.maximum(vals, 0)) / (2 * np.pi)
    idx = np.argsort(f)
    return f[idx], vecs[:, idx]


def shear_check(pl, d, kGh):
    """Angle de cisaillement γ = Q/(κGh) (Mindlin) estimé à partir des efforts
    tranchants de Kirchhoff, max sur la zone de travail (µrad)."""
    s = pl.H["s_work"]
    sel = (np.abs(pl.XC.ravel()) < s) & (np.abs(pl.YC.ravel()) < s)
    e = np.arange(pl.n * pl.n)[sel]
    de = d[pl.edofs[e]]
    N30 = bfs_shape([0.5], [0.5], pl.a, pl.a, 3, 0)[0]
    N12 = bfs_shape([0.5], [0.5], pl.a, pl.a, 1, 2)[0]
    N03 = bfs_shape([0.5], [0.5], pl.a, pl.a, 0, 3)[0]
    N21 = bfs_shape([0.5], [0.5], pl.a, pl.a, 2, 1)[0]
    D = pl.D[pl.eix[e], pl.eiy[e]]
    Qx = -D * (de @ N30 + de @ N12)
    Qy = -D * (de @ N03 + de @ N21)
    return float(np.hypot(Qx, Qy).max() / kGh * 1e6)


# -----------------------------------------------------------------------------
# Optimisations
# -----------------------------------------------------------------------------


def optimize_kelvin_band(pl, fG, fP, path, x0=(0.235, 0.22, -0.22)):
    iso = IsoSupport(pl)

    def J(v):
        pts = isoceles(*v)
        pen = band_violation(pl, pts)
        if pen > 0:
            return 10 + 1000 * pen
        r = eval_iso(iso, fG, fP, kelvin_pivots(pts), path)
        j = objective(r)
        return j

    starts = [x0, (0.21, 0.21, -0.21), (0.24, 0.24, -0.24), (0.20, 0.235, -0.20)]
    res = None
    for s0 in starts:
        rr = minimize(J, s0, method="Nelder-Mead", options=dict(xatol=1e-4, fatol=1e-4, maxiter=250))
        if res is None or rr.fun < res.fun:
            res = rr
    return res.x, res.fun


def optimize_kelvin_ring(pl, fG, fP, path):
    """Points sur l'axe du cadre : P1 = (0, s) ; P2,3 = (±s, y2) côtés ou
    (±x2, −s) avant. Balayage 1D du paramètre (abscisse curviligne)."""
    iso = IsoSupport(pl)
    s = pl.H["s_ring"]
    best = None
    rows = []
    for u in np.linspace(-0.9, 0.9, 37):  # u<0 : (±s, u·s... ) côtés ; u>=0 : avant
        if u <= 0:
            pts = [(0.0, s), (s, s * u), (-s, s * u)]   # sur les côtés, y2 = u·s ∈ [−0,9 s, 0]
        else:
            pts = [(0.0, s), (s * (1 - u), -s), (-s * (1 - u), -s)]  # sur le côté avant
        r = eval_iso(iso, fG, fP, kelvin_pivots(pts), path)
        rows.append((u, r["G"]["slope_peak_urad"], r["P"]["slope_peak_urad"], objective(r), pts))
        if best is None or objective(r) < best[3]:
            best = rows[-1]
    return best, rows


def optimize_wt9(pl, fG, fP, path, band=True):
    iso = IsoSupport(pl)

    def J(v):
        r_in, r_out, beta, phi = v
        pv = wt9_pivots(r_in, r_out, beta, phi)
        pts = [(x, y) for p in pv for x, y, l in p]
        pen = band_violation(pl, pts) if band else sum(
            max(0, max(abs(x), abs(y)) - pl.H["s_max"]) for x, y in pts)
        if pen > 0 or beta <= 5 or beta >= 55:
            return 10 + 1000 * pen
        return objective(eval_iso(iso, fG, fP, pv, path))

    starts = [(0.20, 0.30, 30, 0), (0.22, 0.32, 25, 15), (0.12, 0.25, 30, 0)] if band else \
             [(0.10, 0.22, 30, 0), (0.12, 0.25, 30, 15)]
    res = None
    for s0 in starts:
        rr = minimize(J, s0, method="Nelder-Mead", options=dict(xatol=1e-4, fatol=1e-4, maxiter=300))
        if res is None or rr.fun < res.fun:
            res = rr
    return res.x, res.fun


# -----------------------------------------------------------------------------
# Programme principal
# -----------------------------------------------------------------------------


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    t00 = time.time()
    P = load_params()
    H = structure_hypotheses(P)
    out = dict(hypotheses=H, cases=[], sweeps={})

    # ---------------- 1) balayage Kelvin équilatéral (chemin A) --------------
    radii = np.linspace(0.08, 0.30, 23)
    sweep = {}
    for h_mm in THICKNESSES_MM:
        pl = build_plate(P, h_mm, n=52)
        iso = IsoSupport(pl)
        fG, fP = loads(pl, "A")
        for phi in (0.0, 15.0):
            rows = []
            for r in radii:
                pts = equilateral(r, phi)
                if max(max(abs(x), abs(y)) for x, y in pts) > H["s_max"] + 1e-9:
                    rows.append((r, np.nan, np.nan, np.nan, np.nan)); continue
                rr = eval_iso(iso, fG, fP, kelvin_pivots(pts), "A")
                rows.append((r, rr["G"]["slope_peak_urad"], rr["G"]["slope_rms_urad"],
                             rr["P"]["slope_peak_urad"], rr["P"]["slope_rms_urad"]))
            sweep[f"h{h_mm}_phi{phi:.0f}"] = rows
    out["sweeps"]["kelvin_equilateral_A"] = {k: [list(map(float, r)) for r in v] for k, v in sweep.items()}
    print(f"[{time.time()-t00:5.1f} s] balayage Kelvin équilatéral terminé")

    fig, ax = plt.subplots(1, 2, figsize=(11, 4.2), sharex=True)
    for h_mm, c in zip(THICKNESSES_MM, ["C0", "C1", "C2", "C3"]):
        rows = np.array(sweep[f"h{h_mm}_phi0"], float)
        ax[0].plot(rows[:, 0] * 1e3, rows[:, 1], "-", color=c, label=f"e = {h_mm} mm")
        ax[1].plot(rows[:, 0] * 1e3, rows[:, 3], "-", color=c, label=f"e = {h_mm} mm")
        rows = np.array(sweep[f"h{h_mm}_phi15"], float)
        ax[0].plot(rows[:, 0] * 1e3, rows[:, 1], ":", color=c)
        ax[1].plot(rows[:, 0] * 1e3, rows[:, 3], ":", color=c)
    for a_, lim, tt in ((ax[0], 10, "poids propre"), (ax[1], 5, f"variation 0 → {H['p_max']:.0f} Pa (chemin A)")):
        a_.axhline(lim, color="r", lw=1, ls="--", label=f"budget {lim} µrad")
        a_.axvspan(H["s_min"] * 1e3, H["s_max"] * 1e3, color="g", alpha=0.08)
        a_.axvspan(0, H["s_perf"] * 1e3, color="0.5", alpha=0.08)
        a_.set_ylim(0, 40); a_.grid(alpha=0.3)
        a_.set_xlabel("rayon des 3 appuis r (mm)"); a_.set_title(tt, fontsize=10)
    ax[0].set_ylabel("pente locale résiduelle crête (µrad)")
    ax[0].legend(fontsize=8)
    fig.suptitle("Kelvin 3 points équilatéral (— un appui vers +y ; ··· tourné de 15°). "
                 "Gris : zone percée, vert : bande pleine", fontsize=10)
    fig.tight_layout(); fig.savefig(FIG / "support_kelvin_radius_sweep.png", dpi=130); plt.close(fig)

    # ---------------- 2) optimisations (maillage 10 mm) -----------------------
    opt = {}
    for path in ("A", "B"):
        for h_mm in (25, 30):
            pl = build_plate(P, h_mm, n=52)
            fG, fP = loads(pl, path)
            xk, jk = optimize_kelvin_band(pl, fG, fP, path)
            ring_best, ring_rows = optimize_kelvin_ring(pl, fG, fP, path)
            opt[(path, h_mm, "kelvin_opt")] = isoceles(*xk)
            opt[(path, h_mm, "kelvin_ring_opt")] = ring_best[4]
            if path == "A":
                out["sweeps"][f"kelvin_ring_A_h{h_mm}"] = [list(map(float, r[:4])) for r in ring_rows]
            print(f"[{time.time()-t00:5.1f} s] {path} e={h_mm} : Kelvin bande J={jk:.3f} {np.round(np.array(isoceles(*xk))*1e3,1).tolist()} ; "
                  f"cadre J={ring_best[3]:.3f} u={ring_best[0]:.2f}")
        pl = build_plate(P, 30, n=52)
        fG, fP = loads(pl, path)
        xw, jw = optimize_wt9(pl, fG, fP, path, band=True)
        opt[(path, "wt9")] = tuple(xw)
        print(f"[{time.time()-t00:5.1f} s] {path} : whiffletree 9 pts J={jw:.3f} paramètres {np.round(xw, 4).tolist()}")
    xw_free, jw_free = optimize_wt9(build_plate(P, 30, n=52), *loads(build_plate(P, 30, n=52), "A"), "A", band=False)
    opt[("A", "wt9_free")] = tuple(xw_free)
    print(f"[{time.time()-t00:5.1f} s] whiffletree théorique (sous zone percée) J={jw_free:.3f} {np.round(xw_free,4).tolist()}")

    # ---------------- 3) matrice complète (maillage 5 mm) ---------------------
    s = H["s_ring"]
    maps = {}
    for h_mm in THICKNESSES_MM:
        for path in ("A", "B"):
            pl = build_plate(P, h_mm, n=104)
            iso = IsoSupport(pl)
            fG, fP = loads(pl, path)
            hk = 30 if h_mm >= 30 else 25
            configs = [
                ("kelvin_ring", "3 pts sur cadre (milieu arrière + 2 coins avant)",
                 kelvin_pivots([(0.0, s), (s, -s), (-s, -s)])),
                ("kelvin_ring_opt", "3 pts sur cadre, position optimisée",
                 kelvin_pivots(opt[(path, hk, "kelvin_ring_opt")])),
                ("kelvin_opt", "3 pts optimisés dans la bande pleine",
                 kelvin_pivots(opt[(path, hk, "kelvin_opt")])),
                ("kelvin_eq_r200", "3 pts équilatéral r = 200 mm",
                 kelvin_pivots(equilateral(0.20))),
                ("wt9", "whiffletree 9 pts (bande pleine)", wt9_pivots(*opt[(path, "wt9")])),
            ]
            if path == "A":
                configs.append(("wt9_free", "whiffletree 9 pts théorique (sous la zone percée)",
                                wt9_pivots(*opt[("A", "wt9_free")])))
            for key, label, pv in configs:
                r = eval_iso(iso, fG, fP, pv, path)
                pts = [(x, y) for p_ in pv for x, y, l in p_]
                rec = dict(scheme=key, label=label, path=path, h_mm=h_mm, points_mm=(np.array(pts) * 1e3).round(1).tolist(),
                           **strip(r), objective=objective(r), mass_kg=pl.mass_total,
                           feasible=("posts" if key in ("kelvin_opt", "kelvin_eq_r200", "wt9", "wt9_free") and path == "A"
                                     else ("non" if key in ("kelvin_opt", "kelvin_eq_r200", "wt9", "wt9_free") else "oui")))
                rec["shear_gamma_G_urad"] = shear_check(pl, r["dG"], pl.props["kappaGh_perf"])
                out["cases"].append(rec)
                if h_mm == 30 or (h_mm == 25 and key == "kelvin_ring"):
                    maps[(key, path, h_mm)] = (pl, r["dG"], r["dP"], pts)
            # 4 points
            for a in (0.20, s):
                r4 = eval_4pt(pl, fG, fP, a)
                rec = dict(scheme="4pt", label=f"4 pts (±{a*1e3:.1f}, ±{a*1e3:.1f}) rigides", path=path, h_mm=h_mm,
                           points_mm=[[a * 1e3, a * 1e3]], G=r4["G"][1], P=r4["P"][1],
                           delta1um=r4["delta1um"][1], feasible="oui (hyperstatique)",
                           objective=max(r4["G"][1]["slope_peak_urad"] / 10, r4["P"][1]["slope_peak_urad"] / 5))
                out["cases"].append(rec)
                if h_mm == 30 and np.isclose(a, s):
                    maps[("4pt", path, h_mm)] = (pl, r4["G"][0], r4["P"][0], [(a, a), (-a, a), (-a, -a), (a, -a)])
            # périmètre élastomère (joint = appui)
            band = H["perim_band"]
            rp = eval_perimeter(pl, fG, fP, band, H["perim_kf"])
            rec = dict(scheme="perimeter", label=f"bande élastomère {band[0]*1e3:.1f}–{band[1]*1e3:.1f} mm, k = {H['perim_kf']:.1e} N/m³",
                       path=path, h_mm=h_mm, G=rp["G"][1], P=rp["P"][1], warp10um=rp["warp"][1],
                       crush_um=rp["crush_um"], feasible="oui (hyperstatique)",
                       objective=max(rp["G"][1]["slope_peak_urad"] / 10, rp["P"][1]["slope_peak_urad"] / 5))
            out["cases"].append(rec)
            if h_mm == 30:
                maps[("perimeter", path, h_mm)] = (pl, rp["G"][0], rp["P"][0], [])
        print(f"[{time.time()-t00:5.1f} s] e = {h_mm} mm évalué")

    # sensibilité du périmètre à la raideur de l'élastomère (e = 30, A)
    pl = build_plate(P, 30, n=52)
    fG, fP = loads(pl, "A")
    kf_rows = []
    for kf in np.logspace(7, 11, 9):
        rp = eval_perimeter(pl, fG, fP, H["perim_band"], kf)
        kf_rows.append([float(kf), rp["G"][1]["slope_peak_urad"], rp["P"][1]["slope_peak_urad"],
                        rp["warp"][1]["slope_peak_urad"], rp["crush_um"]])
    out["sweeps"]["perimeter_kf_A_h30"] = kf_rows

    # ---------------- 4) fréquences propres ---------------------------------
    freq = {}
    for h_mm in (25, 30):
        pl = build_plate(P, h_mm, n=52)
        f3, v3 = modes(pl, [(0.0, s), (s, -s), (-s, -s)], H["k_support"], nmodes=7)
        f3r, _ = modes(pl, [(0.0, s), (s, -s), (-s, -s)], 1e11, nmodes=4)
        f4, _ = modes(pl, [(s, s), (-s, s), (-s, -s), (s, -s)], H["k_support"], nmodes=7)
        bandm = (np.maximum(np.abs(pl.XC), np.abs(pl.YC)) > H["perim_band"][0]) & \
                (np.maximum(np.abs(pl.XC), np.abs(pl.YC)) < H["perim_band"][1])
        fp, _ = modes(pl, Kextra=pl.foundation(np.where(bandm, H["perim_kf"], 0.0)), nmodes=6)
        freq[h_mm] = dict(kelvin_ring_ksupport=f3.tolist(), kelvin_ring_rigid_first_flex=float(f3r[0]),
                          four_pt=f4.tolist(), perimeter=fp.tolist(), mass_kg=pl.mass_total)
        print(f"e = {h_mm} : modes 3 pts (k = {H['k_support']:.0e} N/m) {np.round(f3, 0).tolist()} Hz ; "
              f"1er mode de flexion sur appuis rigides {f3r[0]:.0f} Hz")
        if h_mm == 30:
            mode_plot = (pl, v3, f3)
    out["frequencies"] = freq

    # ---------------- 5) charges de palets (e = 30, A, cadre) --------------
    pl = build_plate(P, 30, n=104)
    iso = IsoSupport(pl)
    pv = kelvin_pivots([(0.0, s), (s, -s), (-s, -s)])
    puck = {}
    for name, (x, y) in (("centre", (0, 0)), ("coin_zone", (0.135, 0.135)), ("bord_avant", (0.0, -0.135))):
        f = pl.load_point(x, y, -1.0)
        d, _ = iso.solve(f, pv)
        puck[name] = pl.residual_slope(d, H["s_work"])
    out["puck_1N"] = puck

    # ---------------- figures -----------------------------------------------
    def draw_map(axx, pl, d, pts, title, vmax=None):
        X, Y, G, W = pl.slope_map(d, H["s_work"])
        G = G * 1e6
        im = axx.pcolormesh(X * 1e3, Y * 1e3, G, shading="gouraud", cmap="viridis",
                            vmin=0, vmax=vmax or G.max())
        axx.contour(X * 1e3, Y * 1e3, W * 1e6, 10, colors="w", linewidths=0.5)
        L2 = H["L"] / 2 * 1e3
        axx.plot([-L2, L2, L2, -L2, -L2], [-L2, -L2, L2, L2, -L2], "k-", lw=0.8)
        sp_ = H["s_perf"] * 1e3
        axx.plot([-sp_, sp_, sp_, -sp_, -sp_], [-sp_, -sp_, sp_, sp_, -sp_], "k:", lw=0.8)
        for x, y in pts:
            axx.plot(x * 1e3, y * 1e3, "r^", ms=7)
        axx.set_aspect("equal"); axx.set_xlim(-L2 - 5, L2 + 5); axx.set_ylim(-L2 - 5, L2 + 5)
        axx.set_title(title, fontsize=8.5)
        plt.colorbar(im, ax=axx, fraction=0.046, label="µrad")

    keys = [("kelvin_ring", "A"), ("kelvin_ring_opt", "A"), ("kelvin_opt", "A"), ("wt9", "A"),
            ("4pt", "A"), ("perimeter", "A")]
    for comp, idx in (("G", 1), ("P", 2)):
        fig, axs = plt.subplots(2, 3, figsize=(14, 8.6))
        for axx, (k, pth) in zip(axs.ravel(), keys):
            pl_, dG, dP, pts = maps[(k, pth, 30)]
            d = dG if comp == "G" else dP
            r = pl_.residual_slope(d, H["s_work"])
            draw_map(axx, pl_, d, pts, f"{k} — {pth} — e = 30 mm\ncrête {r['slope_peak_urad']:.1f} µrad, "
                     f"RMS {r['slope_rms_urad']:.1f} µrad, PV {r['pv_um']:.2f} µm")
        fig.suptitle(("Poids propre" if comp == "G" else f"Variation 0 → {H['p_max']:.0f} Pa") +
                     " : |pente locale| après retrait du plan (zone de travail 300×300, isolignes de w résiduel)",
                     fontsize=10)
        fig.tight_layout(); fig.savefig(FIG / f"support_slope_maps_{comp}.png", dpi=120); plt.close(fig)

    # carte du schéma retenu A et B
    fig, axs = plt.subplots(2, 2, figsize=(10, 8.6))
    for j, pth in enumerate(("A", "B")):
        pl_, dG, dP, pts = maps[("kelvin_ring", pth, 30)]
        for i, (d, nm) in enumerate(((dG, "poids propre"), (dP, f"0 → {H['p_max']:.0f} Pa"))):
            r = pl_.residual_slope(d, H["s_work"])
            draw_map(axs[i, j], pl_, d, pts, f"3 pts sur cadre — chemin {pth} — {nm}\ncrête {r['slope_peak_urad']:.2f} µrad, "
                     f"RMS {r['slope_rms_urad']:.2f} µrad, PV {r['pv_um']:.2f} µm")
    fig.tight_layout(); fig.savefig(FIG / "support_selected_maps.png", dpi=120); plt.close(fig)

    # barres comparatives e = 30
    cs = [c for c in out["cases"] if c["h_mm"] == 30]
    labels = [f"{c['scheme']}\n{c['path']}" for c in cs]
    fig, ax = plt.subplots(figsize=(14, 4.5))
    xx = np.arange(len(cs))
    ax.bar(xx - 0.2, [c["G"]["slope_peak_urad"] for c in cs], 0.4, label="poids propre (crête)")
    ax.bar(xx + 0.2, [c["P"]["slope_peak_urad"] for c in cs], 0.4, label=f"0→{H['p_max']:.0f} Pa (crête)")
    ax.axhline(10, color="C0", ls="--", lw=1); ax.axhline(5, color="C1", ls="--", lw=1)
    ax.set_xticks(xx); ax.set_xticklabels(labels, fontsize=7, rotation=0)
    ax.set_ylabel("µrad"); ax.set_yscale("log"); ax.grid(alpha=0.3, which="both"); ax.legend()
    ax.set_title("Comparaison des schémas d'appui, e = 30 mm (budgets : 10 µrad / 5 µrad)")
    fig.tight_layout(); fig.savefig(FIG / "support_comparison_h30.png", dpi=120); plt.close(fig)

    # effet de l'épaisseur (schéma cadre)
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    for sch, pth, st in (("kelvin_ring", "A", "o-"), ("kelvin_ring", "B", "s--"), ("kelvin_opt", "A", "^-"),
                         ("perimeter", "A", "d:")):
        cc = sorted([c for c in out["cases"] if c["scheme"] == sch and c["path"] == pth], key=lambda c: c["h_mm"])
        ax.plot([c["h_mm"] for c in cc], [c["G"]["slope_peak_urad"] for c in cc], st, color="C0")
        ax.plot([c["h_mm"] for c in cc], [c["P"]["slope_peak_urad"] for c in cc], st, color="C1",
                label=f"{sch} {pth}")
    ax.axhline(10, color="C0", ls="--", lw=0.8); ax.axhline(5, color="C1", ls="--", lw=0.8)
    ax.set_xlabel("épaisseur e (mm)"); ax.set_ylabel("pente crête (µrad) — bleu : poids propre, orange : pression")
    ax.set_yscale("log"); ax.grid(alpha=0.3, which="both"); ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "support_thickness.png", dpi=130); plt.close(fig)

    # modes
    pl_, v3, f3 = mode_plot
    fig, axs = plt.subplots(1, 4, figsize=(15, 3.6))
    X, Y = pl_.node_xy()
    m_ = pl_.n + 1
    for i, axx in enumerate(axs):
        w = v3[0::4, i + 3].reshape(m_, m_)
        axx.contourf(X.reshape(m_, m_) * 1e3, Y.reshape(m_, m_) * 1e3, w, 21, cmap="RdBu")
        for x, y in [(0.0, s), (s, -s), (-s, -s)]:
            axx.plot(x * 1e3, y * 1e3, "k^")
        axx.set_aspect("equal"); axx.set_title(f"mode {i+4} : {f3[i+3]:.0f} Hz", fontsize=9)
    fig.suptitle("Modes de flexion, e = 30 mm, 3 appuis sur cadre (modes 1–3 : corps rigide sur raideur d'appui)", fontsize=10)
    fig.tight_layout(); fig.savefig(FIG / "support_modes_h30.png", dpi=120); plt.close(fig)

    # sauvegarde
    def clean(o):
        if isinstance(o, dict):
            return {str(k): clean(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [clean(v) for v in o]
        if isinstance(o, (np.floating, np.integer)):
            return float(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        return o
    out["optimized_points_mm"] = {"|".join(map(str, k)): (np.array(v) * (1e3 if "wt9" not in str(k) else 1)).tolist()
                                  for k, v in opt.items()}
    with open(RES / "support_study.json", "w") as fh:
        json.dump(clean(out), fh, indent=1)

    # tableau markdown
    lines = ["| schéma | chemin | e (mm) | G crête | G RMS | G PV (µm) | flèche G zone (µm) | ΔP crête | ΔP RMS | ΔP PV (µm) | faisable |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for c in out["cases"]:
        lines.append(f"| {c['label']} | {c['path']} | {c['h_mm']} | {c['G']['slope_peak_urad']:.2f} | {c['G']['slope_rms_urad']:.2f} | "
                     f"{c['G']['pv_um']:.2f} | {c.get('defl_G_work_um', float('nan')):.2f} | {c['P']['slope_peak_urad']:.2f} | "
                     f"{c['P']['slope_rms_urad']:.2f} | {c['P']['pv_um']:.2f} | {c['feasible']} |")
    (RES / "support_table.md").write_text("\n".join(lines) + "\n")
    print(f"→ results/support_study.json, results/support_table.md, figures/support_*.png  ({time.time()-t00:.0f} s)")


if __name__ == "__main__":
    main()
