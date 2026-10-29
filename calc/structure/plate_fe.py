"""Modèle éléments finis de plaque de Kirchhoff (élément rectangle conforme
Bogner-Fox-Schmit, 16 ddl : w, w_x, w_y, w_xy par nœud).

Usage principal : plaque carrée de côté L, maillage régulier n × n, rigidité de
flexion D et masse surfacique définies élément par élément (zone percée
homogénéisée au centre, bordure pleine autour).

Conventions :
  - axe z vers le haut, w > 0 vers le haut, charges q > 0 vers le haut (N/m²) ;
  - origine au centre de la plaque, coordonnées en mètres ;
  - ddl global du nœud k : 4k + (0: w, 1: w_x, 2: w_y, 3: w_xy).

Fonctionnalités :
  - matrices de rigidité, de masse, de fondation élastique (Winkler) ;
  - charges réparties (par élément), ponctuelles en un point quelconque,
    linéiques sur un contour carré quelconque, moments ponctuels ;
  - résolution « plaque libre » pour un chargement auto-équilibré (les 3 modes
    rigides sont bloqués par 3 nœuds ; la solution est exacte à un mouvement de
    corps rigide près, sans importance puisqu'on retire le plan moyen) ;
  - post-traitement : pente locale résiduelle après retrait du plan des moindres
    carrés sur la zone de travail (crête, RMS, PV).

Validation (exécuter ce module) : plaque carrée simplement appuyée sous pression
uniforme comparée à la solution de Navier (série double), convergence en maillage.

    python3 -m calc.structure.plate_fe
"""
from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

# -----------------------------------------------------------------------------
# Fonctions d'Hermite 1D sur [0, a]
# -----------------------------------------------------------------------------


def hermite_1d(s: np.ndarray, a: float, der: int = 0) -> np.ndarray:
    """Retourne les 4 fonctions d'Hermite (valeur n0, pente n0, valeur n1,
    pente n1) ou leurs dérivées d'ordre `der` en x = s·a (s ∈ [0,1]).
    Sortie : tableau (len(s), 4)."""
    s = np.atleast_1d(np.asarray(s, dtype=float))
    if der == 0:
        H = np.stack([1 - 3 * s**2 + 2 * s**3,
                      a * (s - 2 * s**2 + s**3),
                      3 * s**2 - 2 * s**3,
                      a * (-s**2 + s**3)], axis=-1)
    elif der == 1:
        H = np.stack([(-6 * s + 6 * s**2) / a,
                      (1 - 4 * s + 3 * s**2),
                      (6 * s - 6 * s**2) / a,
                      (-2 * s + 3 * s**2)], axis=-1)
    elif der == 2:
        H = np.stack([(-6 + 12 * s) / a**2,
                      (-4 + 6 * s) / a,
                      (6 - 12 * s) / a**2,
                      (-2 + 6 * s) / a], axis=-1)
    elif der == 3:
        H = np.stack([12 / a**3 + 0 * s,
                      6 / a**2 + 0 * s,
                      -12 / a**3 + 0 * s,
                      6 / a**2 + 0 * s], axis=-1)
    else:
        raise ValueError(der)
    return H


# Numérotation locale : nœuds (ix, iy) = (0,0), (1,0), (1,1), (0,1) ;
# ddl par nœud : w, w_x, w_y, w_xy.
_LOCAL_NODES = [(0, 0), (1, 0), (1, 1), (0, 1)]


def bfs_shape(sx, sy, ax, ay, dx=0, dy=0) -> np.ndarray:
    """Fonctions de forme BFS (ou dérivées ∂^dx/∂x^dx ∂^dy/∂y^dy) aux points
    locaux (sx, sy) ∈ [0,1]² d'un élément ax × ay. Sortie (npts, 16)."""
    Hx = hermite_1d(sx, ax, dx)  # (n, 4)
    Hy = hermite_1d(sy, ay, dy)
    cols = []
    for ix, iy in _LOCAL_NODES:
        vx, px = Hx[:, 2 * ix], Hx[:, 2 * ix + 1]
        vy, py = Hy[:, 2 * iy], Hy[:, 2 * iy + 1]
        cols += [vx * vy, px * vy, vx * py, px * py]
    return np.stack(cols, axis=-1)


def gauss_1d(n: int):
    """Points et poids de Gauss sur [0,1]."""
    g, w = np.polynomial.legendre.leggauss(n)
    return 0.5 * (g + 1), 0.5 * w


def element_matrices(ax: float, ay: float, ng: int = 5):
    """Matrices élémentaires unitaires :
    Kb, Kn : rigidité K = D·(Kb + ν·Kn) ;
    Me     : ∫ Nᵀ N dA (masse/fondation pour une densité surfacique 1) ;
    fe     : ∫ N dA (charge répartie unitaire)."""
    s, w = gauss_1d(ng)
    SX, SY = np.meshgrid(s, s, indexing="ij")
    WX, WY = np.meshgrid(w, w, indexing="ij")
    sx, sy = SX.ravel(), SY.ravel()
    wt = (WX * WY).ravel() * ax * ay
    Nxx = bfs_shape(sx, sy, ax, ay, 2, 0)
    Nyy = bfs_shape(sx, sy, ax, ay, 0, 2)
    Nxy = bfs_shape(sx, sy, ax, ay, 1, 1)
    N = bfs_shape(sx, sy, ax, ay, 0, 0)
    # Courbures κ = [-w_xx, -w_yy, -2 w_xy] ; C = C0 + ν C1
    B = np.stack([Nxx, Nyy, 2 * Nxy], axis=1)  # (np, 3, 16) (signe sans effet)
    C0 = np.diag([1.0, 1.0, 0.5])
    C1 = np.array([[0, 1, 0], [1, 0, 0], [0, 0, -0.5]])
    Kb = np.einsum("p,pik,ij,pjl->kl", wt, B, C0, B)
    Kn = np.einsum("p,pik,ij,pjl->kl", wt, B, C1, B)
    Me = np.einsum("p,pk,pl->kl", wt, N, N)
    fe = np.einsum("p,pk->k", wt, N)
    return Kb, Kn, Me, fe


# -----------------------------------------------------------------------------
# Modèle de plaque carrée maillée régulièrement
# -----------------------------------------------------------------------------


class SquarePlate:
    """Plaque carrée L × L centrée en 0, maillage régulier n × n éléments BFS.

    D_elem, nu_elem, m_elem : tableaux (n, n) [ix, iy] de rigidité de flexion
    (N·m), coefficient de Poisson et masse surfacique (kg/m²) par élément.
    """

    def __init__(self, L: float, n: int, D_elem, nu_elem, m_elem):
        self.L, self.n = L, n
        self.a = L / n
        self.x = np.linspace(-L / 2, L / 2, n + 1)
        self.nn = (n + 1) ** 2
        self.ndof = 4 * self.nn
        self.D = np.broadcast_to(np.asarray(D_elem, float), (n, n)).copy()
        self.nu = np.broadcast_to(np.asarray(nu_elem, float), (n, n)).copy()
        self.m = np.broadcast_to(np.asarray(m_elem, float), (n, n)).copy()
        self.Kb, self.Kn, self.Me, self.fe = element_matrices(self.a, self.a)
        # centres d'éléments
        xc = 0.5 * (self.x[:-1] + self.x[1:])
        self.XC, self.YC = np.meshgrid(xc, xc, indexing="ij")
        # table de connectivité (n*n, 16)
        ix, iy = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
        ix, iy = ix.ravel(), iy.ravel()
        nodes = np.stack([self.node(ix, iy), self.node(ix + 1, iy),
                          self.node(ix + 1, iy + 1), self.node(ix, iy + 1)], -1)
        self.edofs = (4 * nodes[:, :, None] + np.arange(4)[None, None, :]).reshape(-1, 16)
        self.eix, self.eiy = ix, iy
        self._K = None
        self._free_solver = None

    # --- numérotation ---------------------------------------------------------
    def node(self, ix, iy):
        return np.asarray(ix) * (self.n + 1) + np.asarray(iy)

    def node_xy(self):
        X, Y = np.meshgrid(self.x, self.x, indexing="ij")
        return X.ravel(), Y.ravel()

    # --- assemblage -----------------------------------------------------------
    def _assemble(self, coef_elem, Kunit_fn):
        rows = np.repeat(self.edofs, 16, axis=1).ravel()
        cols = np.tile(self.edofs, (1, 16)).ravel()
        data = Kunit_fn(coef_elem).ravel()
        return sp.csc_matrix((data, (rows, cols)), shape=(self.ndof, self.ndof))

    def stiffness(self):
        if self._K is None:
            D = self.D[self.eix, self.eiy]
            nu = self.nu[self.eix, self.eiy]
            self._K = self._assemble(
                None, lambda _: D[:, None, None] * (self.Kb[None] + nu[:, None, None] * self.Kn[None]))
        return self._K

    def mass(self):
        m = self.m[self.eix, self.eiy]
        return self._assemble(None, lambda _: m[:, None, None] * self.Me[None])

    def foundation(self, k_elem):
        """Fondation de Winkler, k_elem (n, n) en N/m³."""
        k = np.broadcast_to(np.asarray(k_elem, float), (self.n, self.n))[self.eix, self.eiy]
        return self._assemble(None, lambda _: k[:, None, None] * self.Me[None])

    # --- charges --------------------------------------------------------------
    def load_area(self, q_elem) -> np.ndarray:
        """Charge répartie q (N/m², >0 vers le haut), tableau (n, n)."""
        q = np.broadcast_to(np.asarray(q_elem, float), (self.n, self.n))[self.eix, self.eiy]
        f = np.zeros(self.ndof)
        np.add.at(f, self.edofs.ravel(), (q[:, None] * self.fe[None]).ravel())
        return f

    def locate(self, x0, y0):
        """Élément contenant (x0, y0) → (ddl (16,), sx, sy)."""
        i = int(np.clip(np.floor((x0 + self.L / 2) / self.a), 0, self.n - 1))
        j = int(np.clip(np.floor((y0 + self.L / 2) / self.a), 0, self.n - 1))
        sx = (x0 - self.x[i]) / self.a
        sy = (y0 - self.x[j]) / self.a
        e = i * self.n + j
        return self.edofs[e], sx, sy

    def point_vector(self, x0, y0, dx=0, dy=0):
        """Vecteur global g tel que gᵀd = ∂^(dx+dy) w/∂x^dx∂y^dy au point."""
        dofs, sx, sy = self.locate(x0, y0)
        g = np.zeros(self.ndof)
        g[dofs] = bfs_shape([sx], [sy], self.a, self.a, dx, dy)[0]
        return g

    def load_point(self, x0, y0, F) -> np.ndarray:
        return F * self.point_vector(x0, y0)

    def load_point_moment(self, x0, y0, Mx_about_y, My_about_x=0.0) -> np.ndarray:
        """Moment ponctuel : travail = Mx_about_y·w_x + My_about_x·w_y
        (Mx_about_y > 0 fait monter le côté +x)."""
        return Mx_about_y * self.point_vector(x0, y0, 1, 0) + My_about_x * self.point_vector(x0, y0, 0, 1)

    def load_line_square(self, s, qline, ng=4) -> np.ndarray:
        """Charge linéique qline (N/m, >0 vers le haut) le long du contour carré
        de demi-côté s (centré)."""
        f = np.zeros(self.ndof)
        sg, wg = gauss_1d(ng)
        # subdivision suivant le maillage
        t = np.concatenate([[-s], self.x[(self.x > -s) & (self.x < s)], [s]])
        for k in range(len(t) - 1):
            seg = t[k + 1] - t[k]
            for sgi, wgi in zip(sg, wg):
                u = t[k] + sgi * seg
                for (xx, yy) in ((u, s), (u, -s), (s, u), (-s, u)):
                    xe = np.clip(xx, -self.L / 2 + 1e-12, self.L / 2 - 1e-12)
                    ye = np.clip(yy, -self.L / 2 + 1e-12, self.L / 2 - 1e-12)
                    f += qline * wgi * seg * self.point_vector(xe, ye)
        return f

    # --- modes rigides et résolution « plaque libre » --------------------------
    def rigid_modes(self) -> np.ndarray:
        X, Y = self.node_xy()
        R = np.zeros((self.ndof, 3))
        R[0::4, 0] = 1.0
        R[0::4, 1] = X
        R[1::4, 1] = 1.0
        R[0::4, 2] = Y
        R[2::4, 2] = 1.0
        return R

    def free_solver(self):
        """Factorisation de K avec w bloqué en 3 coins (modes rigides)."""
        if self._free_solver is None:
            K = self.stiffness().tolil()
            n = self.n
            fixed = [4 * self.node(0, 0), 4 * self.node(n, 0), 4 * self.node(0, n)]
            free = np.setdiff1d(np.arange(self.ndof), fixed)
            Kf = self.stiffness()[free][:, free]
            lu = spla.splu(Kf.tocsc())
            self._free_solver = (free, lu)
        return self._free_solver

    def solve_free(self, f: np.ndarray, check=True) -> np.ndarray:
        """Résout K d = f pour un chargement auto-équilibré (Rᵀf = 0)."""
        if check:
            R = self.rigid_modes()
            res = R.T @ f
            scale = np.abs(f).sum() + 1e-30
            if np.max(np.abs(res[0])) > 1e-6 * scale or np.max(np.abs(res[1:])) > 1e-6 * scale * self.L:
                raise ValueError(f"chargement non équilibré : {res}")
        free, lu = self.free_solver()
        d = np.zeros(self.ndof)
        d[free] = lu.solve(f[free])
        return d

    def solve_constrained(self, f, Kextra=None, dirichlet=None, values=None):
        """Résolution générale K(+Kextra) d = f avec ddl imposés (indices)."""
        K = self.stiffness()
        if Kextra is not None:
            K = K + Kextra
        d = np.zeros(self.ndof)
        if dirichlet is None or len(dirichlet) == 0:
            return spla.spsolve(K.tocsc(), f)
        dirichlet = np.asarray(dirichlet)
        if values is not None:
            d[dirichlet] = values
        free = np.setdiff1d(np.arange(self.ndof), dirichlet)
        rhs = f[free] - K[free][:, dirichlet] @ d[dirichlet]
        d[free] = spla.spsolve(K[free][:, free].tocsc(), rhs)
        return d

    # --- post-traitement ------------------------------------------------------
    def zone_nodes(self, half: float):
        X, Y = self.node_xy()
        tol = 1e-9
        sel = (np.abs(X) <= half + tol) & (np.abs(Y) <= half + tol)
        # poids des trapèzes (grille régulière)
        wx = np.where(np.isclose(np.abs(X), half), 0.5, 1.0)
        wy = np.where(np.isclose(np.abs(Y), half), 0.5, 1.0)
        return sel, (wx * wy)

    def residual_slope(self, d: np.ndarray, half: float):
        """Pente locale après retrait du plan des moindres carrés (sur w) dans
        le carré |x|,|y| ≤ half. Retourne un dict (µrad, µm)."""
        X, Y = self.node_xy()
        sel, wts = self.zone_nodes(half)
        x, y, wt = X[sel], Y[sel], wts[sel]
        w = d[0::4][sel]
        A = np.stack([np.ones_like(x), x, y], 1)
        Wa = A * wt[:, None]
        coef = np.linalg.solve(A.T @ Wa, Wa.T @ w)
        wr = w - A @ coef
        gx = d[1::4][sel] - coef[1]
        gy = d[2::4][sel] - coef[2]
        g = np.hypot(gx, gy)
        return dict(
            slope_peak_urad=float(g.max() * 1e6),
            slope_rms_urad=float(np.sqrt(np.sum(wt * g**2) / np.sum(wt)) * 1e6),
            slope_x_peak_urad=float(np.abs(gx).max() * 1e6),
            pv_um=float((wr.max() - wr.min()) * 1e6),
            plane_tilt_urad=float(np.hypot(coef[1], coef[2]) * 1e6),
            mean_w_um=float(coef[0] * 1e6),
        )

    def slope_map(self, d: np.ndarray, half: float):
        """Carte (X, Y, |∇w − plan|) sur la grille de la zone (pour figures)."""
        X, Y = self.node_xy()
        sel, wts = self.zone_nodes(half)
        x, y, wt = X[sel], Y[sel], wts[sel]
        w = d[0::4][sel]
        A = np.stack([np.ones_like(x), x, y], 1)
        Wa = A * wt[:, None]
        coef = np.linalg.solve(A.T @ Wa, Wa.T @ w)
        gx = d[1::4][sel] - coef[1]
        gy = d[2::4][sel] - coef[2]
        m = int(round(np.sqrt(sel.sum())))
        return (x.reshape(m, m), y.reshape(m, m), np.hypot(gx, gy).reshape(m, m),
                (w - A @ coef).reshape(m, m))

    def eval_w(self, d, pts):
        return np.array([self.point_vector(px, py) @ d for px, py in pts])


# -----------------------------------------------------------------------------
# Solutions analytiques de validation
# -----------------------------------------------------------------------------


def navier_ss_uniform(a: float, q: float, D: float, x, y, nterms: int = 99):
    """Plaque rectangulaire carrée a×a simplement appuyée, pression q (Navier).
    x, y mesurés depuis un coin. Retourne w, w_x."""
    w = np.zeros_like(np.asarray(x, float))
    wx = np.zeros_like(w)
    for m in range(1, nterms + 1, 2):
        for k in range(1, nterms + 1, 2):
            c = 16 * q / (np.pi**6 * D * m * k * (m**2 / a**2 + k**2 / a**2) ** 2)
            w += c * np.sin(m * np.pi * x / a) * np.sin(k * np.pi * y / a)
            wx += c * (m * np.pi / a) * np.cos(m * np.pi * x / a) * np.sin(k * np.pi * y / a)
    return w, wx


def validate(verbose=True):
    """Validation de l'élément BFS sur la plaque carrée simplement appuyée."""
    a, h, E, nu, q = 0.5, 0.025, 70e9, 0.33, 1000.0
    D = E * h**3 / (12 * (1 - nu**2))
    w_ref, _ = navier_ss_uniform(a, q, D, np.array(a / 2), np.array(a / 2))
    _, wx_ref = navier_ss_uniform(a, q, D, np.array(0.0), np.array(a / 2))
    _, wx_ref2 = navier_ss_uniform(a, q, D, np.array(a / 4), np.array(a / 4))
    rows = []
    for n in (4, 8, 16, 32, 64):
        pl = SquarePlate(a, n, D, nu, 1.0)
        f = pl.load_area(q)
        X, Y = pl.node_xy()
        edge_x = np.isclose(np.abs(X), a / 2)
        edge_y = np.isclose(np.abs(Y), a / 2)
        nodes = np.arange(pl.nn)
        bc = np.concatenate([4 * nodes[edge_x | edge_y],          # w = 0
                             4 * nodes[edge_x] + 2,                # w_y = 0 sur x = ±a/2
                             4 * nodes[edge_y] + 1])               # w_x = 0 sur y = ±a/2
        d = pl.solve_constrained(f, dirichlet=np.unique(bc))
        wc = pl.point_vector(0.0, 0.0) @ d
        wxe = pl.point_vector(-a / 2, 0.0, 1, 0) @ d
        wxq = pl.point_vector(-a / 4, -a / 4, 1, 0) @ d
        rows.append((n, wc, (wc / w_ref - 1) * 100, wxe, (wxe / wx_ref - 1) * 100,
                     (wxq / wx_ref2 - 1) * 100))
    if verbose:
        print(f"Validation Navier : w_c réf = {float(w_ref)*1e6:.4f} µm "
              f"(coef {float(w_ref)*D/(q*a**4):.6f} ; théorie 0.004062)")
        print(" n   w_c [µm]   err %    pente bord [µrad]  err %   pente (a/4,a/4) err %")
        for r in rows:
            print(f"{r[0]:3d} {r[1]*1e6:9.4f} {r[2]:8.4f}  {r[3]*1e6:12.3f}  {r[4]:8.4f}  {r[5]:8.4f}")
    return dict(w_ref=float(w_ref), wx_ref=float(wx_ref), rows=rows, D=D, q=q, a=a)


def validate_point_support(verbose=True):
    """Vérifie l'appui ponctuel en un point quelconque (hors nœud) : plaque
    carrée sur 4 appuis aux coins, résolue (1) par Dirichlet aux nœuds de coin,
    (2) par le solveur « plaque libre » + réactions statiquement réparties
    (symétrie → R = qa²/4) aux mêmes points (coins décalés d'une demi-maille pour
    tester l'évaluation hors nœud, solution comparée à celle d'un maillage qui
    passe par le point)."""
    a, h, E, nu, q = 0.5, 0.025, 70e9, 0.33, 1000.0
    D = E * h**3 / (12 * (1 - nu**2))
    out = []
    for n in (21, 40, 63):
        pl = SquarePlate(a, n, D, nu, 1.0)
        f = pl.load_area(q)
        c = a / 2 * 0.8
        # appuis en (±c, ±c) : par symétrie R = q a²/4 chacun
        for sx in (-1, 1):
            for sy in (-1, 1):
                f = f - q * a**2 / 4 * pl.point_vector(sx * c, sy * c)
        d = pl.solve_free(f)
        w0 = pl.point_vector(0, 0) @ d - pl.point_vector(c, c) @ d
        out.append((n, w0))
    if verbose:
        print("Appuis ponctuels hors nœud (4 points à 0,8·a/2) : w_centre − w_appui")
        for n, w0 in out:
            print(f"  n = {n:3d} : {w0*1e6:.4f} µm  (coef {w0*D/(q*a**4):.6f})")
    return out


if __name__ == "__main__":
    import json
    from calc.common.params import REPO_ROOT
    res = validate()
    res2 = validate_point_support()
    outdir = REPO_ROOT / "calc" / "structure" / "results"
    outdir.mkdir(parents=True, exist_ok=True)
    with open(outdir / "plate_fe_validation.json", "w") as fh:
        json.dump(dict(navier=dict(w_ref_um=res["w_ref"] * 1e6, wx_edge_ref_urad=res["wx_ref"] * 1e6,
                                   rows=[dict(n=r[0], w_c_um=r[1] * 1e6, err_w_pct=r[2],
                                              wx_edge_urad=r[3] * 1e6, err_wx_pct=r[4],
                                              err_wx_quarter_pct=r[5]) for r in res["rows"]]),
                       point_support=[dict(n=n, w_rel_um=w * 1e6) for n, w in res2]),
                  fh, indent=2)
    print("→ results/plate_fe_validation.json")
