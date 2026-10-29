"""Rigidité équivalente de la plaque perforée (homogénéisation).

Géométrie (params/design.toml [plate]) : réseau hexagonal (triangle équilatéral)
de pas p de perçages borgnes Ø d depuis la face inférieure, laissant un voile
plein d'épaisseur t_w traversé par un orifice Ø d_o.

Trois niveaux d'estimation :
  1. Littérature : efficacité de ligament μ = (p − d)/p ; formules de matériau
     poreux 2D (dilué, Mori-Tanaka = borne supérieure de Hashin-Shtrikman) ;
     ordre de grandeur ASME VIII-2 annexe 5-E / O'Donnell-Langer.
  2. Cellule élémentaire 2D (contraintes planes, conditions périodiques,
     maillage pixel Q4 avec fraction volumique par pixel) → E*, ν* de la couche
     percée (les plaques épaisses h/p > 2 se comportent comme en contraintes
     planes : c'est l'hypothèse ASME pour h/p ≥ 2).
  3. Cellule 3D (hexaèdres 8 nœuds, périodique en x, y, faces libres en z) sous
     déformations de membrane et courbures imposées → matrice ABD complète,
     rigidité de flexion réduite D* = D − B A⁻¹ B (plaque bicouche dissymétrique).

La fonction `plate_properties(P, h)` fournit au modèle de plaque : D de la zone
percée, ν, masse surfacique, et D de la bordure pleine.

    python3 -m calc.structure.homogenization
"""
from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

from calc.common.params import REPO_ROOT, load_params

RESULTS = REPO_ROOT / "calc" / "structure" / "results"
CACHE = RESULTS / "homogenization_cache.json"


# -----------------------------------------------------------------------------
# Géométrie de la cellule
# -----------------------------------------------------------------------------

def hex_porosity(p, d):
    """Fraction de vide d'un réseau hexagonal de trous Ø d au pas p."""
    return (np.pi * d**2 / 4) / (p**2 * np.sqrt(3) / 2)


def hole_centers(p):
    Ly = p * np.sqrt(3)
    return np.array([[0, 0], [p, 0], [0, Ly], [p, Ly], [p / 2, Ly / 2]])


def solid_fraction_pixels(p, d, nx, ny, nsub=6):
    """Fraction de matière de chaque pixel de la cellule rectangulaire p × p√3."""
    Ly = p * np.sqrt(3)
    hx, hy = p / nx, Ly / ny
    s = (np.arange(nsub) + 0.5) / nsub
    xs = (np.arange(nx)[:, None] + s[None, :]).ravel() * hx
    ys = (np.arange(ny)[:, None] + s[None, :]).ravel() * hy
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    solid = np.ones_like(X, dtype=bool)
    for cx, cy in hole_centers(p):
        solid &= (X - cx) ** 2 + (Y - cy) ** 2 > (d / 2) ** 2
    return solid.reshape(nx, nsub, ny, nsub).mean(axis=(1, 3))


# -----------------------------------------------------------------------------
# Littérature
# -----------------------------------------------------------------------------

def literature_estimates(p, d, nu=0.33):
    f = hex_porosity(p, d)
    mu = (p - d) / p
    return dict(
        porosity=f,
        ligament_efficiency=mu,
        E_ratio_dilute=1 - 3 * f,                       # trous circulaires dilués (contr. planes)
        E_ratio_mori_tanaka=(1 - f) / (1 + 2 * f),      # = borne sup. Hashin-Shtrikman 2D
        E_ratio_ligament=mu,                            # règle « efficacité de ligament » (prudente)
    )


# -----------------------------------------------------------------------------
# Cellule 2D contraintes planes
# -----------------------------------------------------------------------------

def q4_plane_stress(hx, hy, E, nu):
    C = E / (1 - nu**2) * np.array([[1, nu, 0], [nu, 1, 0], [0, 0, (1 - nu) / 2]])
    g = np.array([-1, 1]) / np.sqrt(3)
    K = np.zeros((8, 8))
    xi_n = np.array([-1, 1, 1, -1])
    eta_n = np.array([-1, -1, 1, 1])
    for xi in g:
        for eta in g:
            dNdxi = 0.25 * xi_n * (1 + eta * eta_n)
            dNdeta = 0.25 * eta_n * (1 + xi * xi_n)
            dNdx = dNdxi * 2 / hx
            dNdy = dNdeta * 2 / hy
            B = np.zeros((3, 8))
            B[0, 0::2] = dNdx
            B[1, 1::2] = dNdy
            B[2, 0::2] = dNdy
            B[2, 1::2] = dNdx
            K += B.T @ C @ B * (hx * hy / 4)
    return K


def cell2d(p, d, E=70e9, nu=0.33, nx=100):
    """Constantes effectives E*, ν*, G* de la couche percée (contraintes planes)."""
    Ly = p * np.sqrt(3)
    ny = int(round(nx * np.sqrt(3)))
    hx, hy = p / nx, Ly / ny
    phi = solid_fraction_pixels(p, d, nx, ny)
    Emod = np.maximum(phi, 1e-6)
    Ke = q4_plane_stress(hx, hy, 1.0, nu)
    # nœuds (i, j) i ∈ [0, nx], j ∈ [0, ny] ; maître périodique (i % nx, j % ny)
    I, J = np.meshgrid(np.arange(nx), np.arange(ny), indexing="ij")
    I, J = I.ravel(), J.ravel()
    def nid(i, j):
        return i * (ny + 1) + j
    def mid(i, j):
        return (i % nx) * ny + (j % ny)
    en = np.stack([nid(I, J), nid(I + 1, J), nid(I + 1, J + 1), nid(I, J + 1)], 1)
    em = np.stack([mid(I, J), mid(I + 1, J), mid(I + 1, J + 1), mid(I, J + 1)], 1)
    edof = np.stack([2 * en, 2 * en + 1], -1).reshape(-1, 8)
    emdof = np.stack([2 * em, 2 * em + 1], -1).reshape(-1, 8)
    ndof = 2 * (nx + 1) * (ny + 1)
    nmd = 2 * nx * ny
    E_el = E * Emod[I, J]
    data = (E_el[:, None, None] * Ke[None]).ravel()
    rows = np.repeat(edof, 8, 1).ravel()
    cols = np.tile(edof, (1, 8)).ravel()
    K = sp.csr_matrix((data, (rows, cols)), shape=(ndof, ndof))
    # matrice de périodicité P (ndof × nmd)
    Pm = sp.csr_matrix((np.ones(edof.size), (edof.ravel(), emdof.ravel())), shape=(ndof, nmd))
    Pm.data[:] = 1.0  # doublons → 1
    Pm = (Pm > 0).astype(float)
    Kp = (Pm.T @ K @ Pm).tocsc()
    keep = np.arange(2, nmd)  # bloque la translation du nœud maître 0
    lu = spla.splu(Kp[keep][:, keep])
    Xn = np.repeat(np.arange(nx + 1) * hx, ny + 1)
    Yn = np.tile(np.arange(ny + 1) * hy, nx + 1)
    U = []
    for eps in ([1, 0, 0], [0, 1, 0], [0, 0, 1]):
        exx, eyy, gxy = eps
        ua = np.zeros(ndof)
        ua[0::2] = exx * Xn + 0.5 * gxy * Yn
        ua[1::2] = eyy * Yn + 0.5 * gxy * Xn
        rhs = -(Pm.T @ (K @ ua))
        ut = np.zeros(nmd)
        ut[keep] = lu.solve(rhs[keep])
        U.append(ua + Pm @ ut)
    U = np.stack(U, 1)
    A = p * Ly
    C = U.T @ (K @ U) / A
    S = np.linalg.inv(C)
    Es = 1 / S[0, 0]
    nus = -S[0, 1] / S[0, 0]
    Gs = 1 / S[2, 2]
    return dict(E_ratio=Es / E, nu=nus, G_ratio=Gs / (E / (2 * (1 + nu))),
                isotropy_check=Gs / (Es / (2 * (1 + nus))), C=C.tolist(),
                porosity_mesh=1 - phi.mean(), porosity_exact=hex_porosity(p, d), nx=nx)


# -----------------------------------------------------------------------------
# Cellule 3D (ABD)
# -----------------------------------------------------------------------------

def hex8_stiffness(hx, hy, hz, nu):
    """Rigidité d'un hexaèdre 8 nœuds (E = 1), intégration 2×2×2."""
    lam = nu / ((1 + nu) * (1 - 2 * nu))
    mu = 1 / (2 * (1 + nu))
    C = np.zeros((6, 6))
    C[:3, :3] = lam
    C[np.arange(3), np.arange(3)] += 2 * mu
    C[3:, 3:] = np.eye(3) * mu
    sgn = np.array([[-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
                    [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1]], float)
    g = np.array([-1, 1]) / np.sqrt(3)
    K = np.zeros((24, 24))
    for a in g:
        for b in g:
            for c in g:
                dN = np.zeros((8, 3))
                dN[:, 0] = sgn[:, 0] * (1 + b * sgn[:, 1]) * (1 + c * sgn[:, 2]) / 8 * 2 / hx
                dN[:, 1] = sgn[:, 1] * (1 + a * sgn[:, 0]) * (1 + c * sgn[:, 2]) / 8 * 2 / hy
                dN[:, 2] = sgn[:, 2] * (1 + a * sgn[:, 0]) * (1 + b * sgn[:, 1]) / 8 * 2 / hz
                B = np.zeros((6, 24))
                B[0, 0::3] = dN[:, 0]
                B[1, 1::3] = dN[:, 1]
                B[2, 2::3] = dN[:, 2]
                B[3, 0::3] = dN[:, 1]; B[3, 1::3] = dN[:, 0]
                B[4, 1::3] = dN[:, 2]; B[4, 2::3] = dN[:, 1]
                B[5, 0::3] = dN[:, 2]; B[5, 2::3] = dN[:, 0]
                K += B.T @ C @ B * (hx * hy * hz / 8)
    return K, sgn


def cell3d_abd(p, d, h, t_w, d_o, E=70e9, nu=0.33, nx=20, dz_perf=1.0e-3, dz_web=0.25e-3):
    """Matrice ABD (référence plan moyen) de la cellule périodique 3D."""
    Ly = p * np.sqrt(3)
    ny = int(round(nx * np.sqrt(3)))
    hx, hy = p / nx, Ly / ny
    n_perf = max(4, int(round((h - t_w) / dz_perf)))
    n_web = max(2, int(round(t_w / dz_web)))
    dzs = np.concatenate([np.full(n_perf, (h - t_w) / n_perf), np.full(n_web, t_w / n_web)])
    zn = np.concatenate([[0], np.cumsum(dzs)])  # z depuis la face inférieure
    nz = len(dzs)
    phi_perf = solid_fraction_pixels(p, d, nx, ny)
    phi_web = solid_fraction_pixels(p, d_o, nx, ny)
    nn_xy = (nx + 1) * (ny + 1)
    def nid(i, j, k):
        return (k * (nx + 1) + i) * (ny + 1) + j
    def mid(i, j, k):
        return (k * nx + (i % nx)) * ny + (j % ny)
    I, J = np.meshgrid(np.arange(nx), np.arange(ny), indexing="ij")
    I, J = I.ravel(), J.ravel()
    ndof = 3 * nn_xy * (nz + 1)
    nmd = 3 * nx * ny * (nz + 1)
    rows_l, cols_l, data_l = [], [], []
    Pr, Pc = [], []
    Kcache = {}
    sgn = None
    for k in range(nz):
        hz = dzs[k]
        key = round(hz * 1e9)
        if key not in Kcache:
            Kcache[key], sgn = hex8_stiffness(hx, hy, hz, nu)
        Ke = Kcache[key]
        if sgn is None:
            _, sgn = hex8_stiffness(hx, hy, hz, nu)
        phi = phi_perf if k < n_perf else phi_web
        Ee = E * np.maximum(phi[I, J], 1e-6)
        corners = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]
        en = np.stack([nid(I + a, J + b, k + c) for a, b, c in corners], 1)
        em = np.stack([mid(I + a, J + b, k + c) for a, b, c in corners], 1)
        edof = np.stack([3 * en, 3 * en + 1, 3 * en + 2], -1).reshape(-1, 24)
        emdof = np.stack([3 * em, 3 * em + 1, 3 * em + 2], -1).reshape(-1, 24)
        rows_l.append(np.repeat(edof, 24, 1).ravel().astype(np.int32))
        cols_l.append(np.tile(edof, (1, 24)).ravel().astype(np.int32))
        data_l.append((Ee[:, None, None] * Ke[None]).ravel())
        Pr.append(edof.ravel()); Pc.append(emdof.ravel())
    K = sp.csr_matrix((np.concatenate(data_l), (np.concatenate(rows_l), np.concatenate(cols_l))),
                      shape=(ndof, ndof))
    del rows_l, cols_l, data_l
    Pr = np.concatenate(Pr); Pc = np.concatenate(Pc)
    Pm = sp.csr_matrix((np.ones(Pr.size), (Pr, Pc)), shape=(ndof, nmd))
    Pm = (Pm > 0).astype(float)
    Kp = (Pm.T @ K @ Pm).tocsc()
    keep = np.arange(3, nmd)
    lu = spla.splu(Kp[keep][:, keep], permc_spec="MMD_AT_PLUS_A")
    # coordonnées nodales
    kk, ii, jj = np.meshgrid(np.arange(nz + 1), np.arange(nx + 1), np.arange(ny + 1), indexing="ij")
    Xn, Yn = (ii * hx).ravel(), (jj * hy).ravel()
    Zn = zn[kk.ravel()] - h / 2  # référence : plan moyen
    U = []
    cases = np.eye(6)  # [exx, eyy, gxy, kxx, kyy, 2kxy]
    for c in cases:
        exx, eyy, gxy, kxx, kyy, kxy2 = c
        Exx = exx + Zn * kxx
        Eyy = eyy + Zn * kyy
        Exy = 0.5 * gxy + Zn * 0.5 * kxy2
        ua = np.zeros(ndof)
        ua[0::3] = Exx * Xn + Exy * Yn
        ua[1::3] = Exy * Xn + Eyy * Yn
        ua[2::3] = -0.5 * (kxx * Xn**2 + kyy * Yn**2 + kxy2 * Xn * Yn)
        rhs = -(Pm.T @ (K @ ua))
        ut = np.zeros(nmd)
        ut[keep] = lu.solve(rhs[keep])
        U.append(ua + Pm @ ut)
    U = np.stack(U, 1)
    ABD = U.T @ (K @ U) / (p * Ly)
    return ABD, dict(nx=nx, ny=ny, nz=nz, ndof=nmd)


def reduced_bending(ABD):
    A, B, D = ABD[:3, :3], ABD[:3, 3:], ABD[3:, 3:]
    return D - B @ np.linalg.solve(A, B)


# -----------------------------------------------------------------------------
# Stratifié analytique (couche percée homogénéisée + voile)
# -----------------------------------------------------------------------------

def Qmat(E, nu):
    return E / (1 - nu**2) * np.array([[1, nu, 0], [nu, 1, 0], [0, 0, (1 - nu) / 2]])


def laminate_abd(layers, h):
    """layers : liste (z_bas, z_haut, E, ν) avec z depuis la face inférieure."""
    A = np.zeros((3, 3)); B = np.zeros((3, 3)); D = np.zeros((3, 3))
    for z0, z1, E, nu in layers:
        Q = Qmat(E, nu)
        a, b = z0 - h / 2, z1 - h / 2
        A += Q * (b - a)
        B += Q * (b**2 - a**2) / 2
        D += Q * (b**3 - a**3) / 3
    ABD = np.block([[A, B], [B, D]])
    return ABD


@lru_cache(maxsize=None)
def _cell2d_cached(p_mm, d_mm, nu, E):
    """E*/E, ν* (cellule 2D) avec cache disque."""
    key = f"{p_mm:.4f}_{d_mm:.4f}_{nu:.3f}"
    cache = {}
    if CACHE.exists():
        cache = json.loads(CACHE.read_text())
    if key not in cache:
        r = cell2d(p_mm * 1e-3, d_mm * 1e-3, E, nu, nx=80)
        cache[key] = dict(E_ratio=r["E_ratio"], nu=r["nu"], G_ratio=r["G_ratio"])
        RESULTS.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(cache, indent=1))
    return cache[key]["E_ratio"], cache[key]["nu"], cache[key]["G_ratio"]


def plate_properties(P: dict, h: float | None = None, pitch_mm=None, d_mm=None):
    """Propriétés équivalentes pour le modèle de plaque (SI).

    Retourne dict(D_solid, nu, D_perf, nu_perf, m_solid, m_perf, h, ...)."""
    pl = P["plate"]
    E, nu, rho = pl["E"], pl["nu"], pl["rho"]
    h = pl["thickness_mm"] * 1e-3 if h is None else h
    p_mm = pl["pitch_mm"] if pitch_mm is None else pitch_mm
    d_mm = pl["counterbore_d_mm"] if d_mm is None else d_mm
    t_w = pl["orifice_length_mm"] * 1e-3
    d_o = pl["orifice_d_mm"] * 1e-3
    p = p_mm * 1e-3
    Er, nus, Gr = _cell2d_cached(float(p_mm), float(d_mm), float(nu), float(E))
    f_web = hex_porosity(p, d_o)
    Er_web = (1 - f_web) / (1 + 2 * f_web)
    ABD = laminate_abd([(0, h - t_w, E * Er, nus), (h - t_w, h, E * Er_web, nu)], h)
    Dr = reduced_bending(ABD)
    D_solid = E * h**3 / (12 * (1 - nu**2))
    f = hex_porosity(p, d_mm * 1e-3)
    m_solid = rho * h
    m_perf = rho * (h - f * (h - t_w) - f_web * t_w)
    return dict(h=h, E=E, nu=nu, rho=rho, D_solid=D_solid, D_perf=Dr[0, 0],
                nu_perf=Dr[0, 1] / Dr[0, 0], D_ratio=Dr[0, 0] / D_solid,
                m_solid=m_solid, m_perf=m_perf, porosity=f, E_ratio_layer=Er, nu_layer=nus,
                G_ratio_layer=Gr, kappaGh_perf=5 / 6 * E / (2 * (1 + nu)) * h * (1 - f))


# -----------------------------------------------------------------------------
# Programme principal
# -----------------------------------------------------------------------------

def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import time

    P = load_params()
    pl = P["plate"]
    E, nu, rho = pl["E"], pl["nu"], pl["rho"]
    p, d = pl["pitch_mm"] * 1e-3, pl["counterbore_d_mm"] * 1e-3
    t_w, d_o = pl["orifice_length_mm"] * 1e-3, pl["orifice_d_mm"] * 1e-3
    out = {}

    lit = literature_estimates(p, d, nu)
    out["literature"] = lit
    print(f"Porosité couche percée f = {lit['porosity']:.4f} ; efficacité de ligament μ = {lit['ligament_efficiency']:.3f}")
    print(f"E*/E : dilué {lit['E_ratio_dilute']:.3f} | Mori-Tanaka/HS {lit['E_ratio_mori_tanaka']:.3f} | μ {lit['E_ratio_ligament']:.3f}")

    # Convergence cellule 2D
    conv = []
    for nx in (40, 80, 160):
        t0 = time.time()
        r = cell2d(p, d, E, nu, nx)
        conv.append(dict(nx=nx, E_ratio=r["E_ratio"], nu=r["nu"], G_ratio=r["G_ratio"],
                         isotropy=r["isotropy_check"], porosity_mesh=r["porosity_mesh"]))
        print(f"cellule 2D nx={nx:4d} : E*/E = {r['E_ratio']:.4f}  ν* = {r['nu']:.4f}  "
              f"G*/G = {r['G_ratio']:.4f}  isotropie {r['isotropy_check']:.4f}  ({time.time()-t0:.1f} s)")
    out["cell2d_convergence"] = conv
    # Courbe E*/E et ν* en fonction de μ (pour d'autres choix pas/Ø)
    mus = np.linspace(0.3, 0.9, 13)
    curve = []
    for mu in mus:
        dd = p * (1 - mu)
        r = cell2d(p, dd, E, nu, 60)
        curve.append(dict(mu=float(mu), d_over_p=float(1 - mu), E_ratio=r["E_ratio"], nu=r["nu"],
                          mt=float((1 - hex_porosity(p, dd)) / (1 + 2 * hex_porosity(p, dd)))))
    out["cell2d_vs_mu"] = curve

    # Cellule 3D (h = 25 mm baseline et 30 mm)
    out["cell3d"] = []
    for h in (0.020, 0.025, 0.030):
        t0 = time.time()
        ABD, info = cell3d_abd(p, d, h, t_w, d_o, E, nu, nx=16, dz_perf=1.0e-3, dz_web=0.25e-3)
        Dr = reduced_bending(ABD)
        props = plate_properties(P, h)
        D_solid = E * h**3 / (12 * (1 - nu**2))
        rec = dict(h_mm=h * 1e3, D_solid=D_solid, D3d=Dr[0, 0], nu3d=Dr[0, 1] / Dr[0, 0],
                   D3d_ratio=Dr[0, 0] / D_solid, D_lam=props["D_perf"], D_lam_ratio=props["D_ratio"],
                   nu_lam=props["nu_perf"], ecart_pct=(props["D_perf"] / Dr[0, 0] - 1) * 100,
                   D66_iso_check=Dr[2, 2] / ((Dr[0, 0] - Dr[0, 1]) / 2), info=info,
                   time_s=time.time() - t0)
        out["cell3d"].append(rec)
        print(f"cellule 3D h={h*1e3:.0f} mm : D*/D_plein = {rec['D3d_ratio']:.4f} (ν {rec['nu3d']:.3f}) ; "
              f"stratifié {rec['D_lam_ratio']:.4f} → écart {rec['ecart_pct']:+.2f} % ; "
              f"isotropie D66 {rec['D66_iso_check']:.3f} ({rec['time_s']:.0f} s, {info['ndof']} ddl)")

    # Propriétés pour chaque épaisseur
    out["plate_properties"] = []
    for h_mm in (20, 25, 30, 35):
        pr = plate_properties(P, h_mm * 1e-3)
        L = P["plate"]["outer_square_mm"] * 1e-3
        Lp = P["zones"]["perforated_square_mm"] * 1e-3
        mass = pr["m_solid"] * (L**2 - Lp**2) + pr["m_perf"] * Lp**2
        pr.update(h_mm=h_mm, mass_kg=mass)
        out["plate_properties"].append({k: (float(v) if np.isscalar(v) else v) for k, v in pr.items()})
        print(f"h = {h_mm} mm : D_plein = {pr['D_solid']:.4g} N·m, D_percé = {pr['D_perf']:.4g} "
              f"(×{pr['D_ratio']:.3f}), m_plein {pr['m_solid']:.1f} kg/m², m_percé {pr['m_perf']:.1f} kg/m², "
              f"masse plaque {mass:.2f} kg")

    # Figure
    fig, ax = plt.subplots(1, 2, figsize=(10, 4))
    mu_ = [c["mu"] for c in curve]
    ax[0].plot(mu_, [c["E_ratio"] for c in curve], "o-", label="cellule 2D périodique (EF)")
    ax[0].plot(mu_, [c["mt"] for c in curve], "--", label="Mori-Tanaka / HS sup.")
    ax[0].plot(mu_, mu_, ":", label="E*/E = μ (règle prudente)")
    ax[0].axvline(lit["ligament_efficiency"], color="k", lw=0.8)
    ax[0].set_xlabel("efficacité de ligament μ = (p − d)/p")
    ax[0].set_ylabel("E*/E (couche percée, contraintes planes)")
    ax[0].grid(alpha=0.3); ax[0].legend(fontsize=8)
    ax[1].plot(mu_, [c["nu"] for c in curve], "o-")
    ax[1].axvline(lit["ligament_efficiency"], color="k", lw=0.8)
    ax[1].set_xlabel("μ"); ax[1].set_ylabel("ν*"); ax[1].grid(alpha=0.3)
    fig.suptitle("Réseau hexagonal : constantes effectives de la couche percée")
    fig.tight_layout()
    fig.savefig(REPO_ROOT / "calc/structure/figures/homogenization_E_nu.png", dpi=130)

    with open(RESULTS / "homogenization.json", "w") as fh:
        json.dump(out, fh, indent=2, default=float)
    print("→ results/homogenization.json, figures/homogenization_E_nu.png")


if __name__ == "__main__":
    main()
