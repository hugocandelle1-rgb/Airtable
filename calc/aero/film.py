"""Modèles du film d'air sous un palet (bibliothèque).

Équation de Reynolds stationnaire, incompressible (Δp ≪ p_atm), film mince :

    ∇·( h³/(12μ) ∇p ) = − Σ_i q_i δ(x − x_i)         sur le disque r < R, p(R) = 0

avec, pour chaque trou couvert, la loi série « trou + rideau » :

    ps − p_i = Δp_trou(q_i) + K_c·ρ/2·(q_i/(π d h_i))²

où p_i est la pression du film au rayon du trou r_h = d/2 (bord du rideau).

Trois niveaux de modèle :

1. ``axi_*`` — modèle axisymétrique homogénéisé (sources réparties de densité n),
   avec, en option, la correction « de puits » (Peaceman) qui relie la pression
   au trou à la pression moyenne de sa cellule :
       p_trou − p̄ = 6μq/(π h³) · [ln(r_e/r_h) − 3/4],  π r_e² = 1/n.
   Donne W(h, ps), k_z, k_θ (mode m = 1 linéarisé), débit sous palet.
2. ``green_*`` — modèle discret exact pour film parallèle (h uniforme) : fonction
   de Green de Dirichlet du disque (méthode des images) ; sources ponctuelles aux
   positions réelles des trous. Portance et moment en forme close :
       W = 12μ/h³ Σ q_i (R² − ρ_i²)/4 ,   M = 12μ/h³ Σ q_i ξ_i (R² − ρ_i²)/8.
3. ``FD2D`` — différences finies 2D (grille cartésienne, frontière circulaire de
   Shortley–Weller) pour un film incliné h = h0 + a·x + b·y ; la singularité
   logarithmique de chaque source est soustraite analytiquement (p = Σ c_i G0_i + w)
   et seule la partie régulière w est discrétisée. Sert à k_θ « exact » et à
   l'équilibre complet (h0, a, b) du palet.

Force latérale sur un palet incliné (pression normale à la face + cisaillement
de Poiseuille, intégration par parties, p = 0 au bord) :

    F = −∫ p ∇h dA + ½ ∫ p ∇h dA = −½ W (a, b)

soit une « pente équivalente » F/(m g) = −(a, b)/2 quand W = m g.
"""
from __future__ import annotations

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla
from scipy.optimize import brentq

from calc.aero.common import HoleConfig, MU, RHO, G, R_PUCK, holes_near
from calc.aero.orifice import (dp_hole, ddp_hole, dp_curtain, ddp_curtain_dq,
                               ddp_curtain_dh, invert)

TWO_PI = 2 * np.pi


# ===========================================================================
# 1. Modèle axisymétrique homogénéisé
# ===========================================================================
def _dp_well(q, h, cfg: HoleConfig):
    r_e = 1.0 / np.sqrt(np.pi * cfg.density)
    return 6 * MU * q / (np.pi * h**3) * (np.log(r_e / cfg.r_h) - 0.75)


def g_smeared(q, h, cfg, well=True):
    out = dp_hole(q, cfg) + dp_curtain(q, h, cfg)
    if well:
        out = out + _dp_well(q, h, cfg)
    return out


def dg_smeared_dq(q, h, cfg, well=True):
    out = ddp_hole(q, cfg) + ddp_curtain_dq(q, h, cfg)
    if well:
        out = out + _dp_well(1.0, h, cfg)
    return out


def dg_smeared_dh(q, h, cfg, well=True):
    out = ddp_curtain_dh(q, h, cfg)
    if well:
        out = out - 3 * _dp_well(q, h, cfg) / h
    return out


def axi_solve(cfg: HoleConfig, ps: float, h: float, well=True, N=160, R=R_PUCK):
    """Résout le modèle axisymétrique (volumes finis, Newton).

    Retourne dict(r, p, q, W, Q, dr, gq, gh) — q par trou (m³/s) à chaque rayon.
    """
    n = cfg.density
    k = h**3 / (12 * MU)
    dr = R / N
    r = (np.arange(N) + 0.5) * dr
    rf = np.arange(N + 1) * dr                      # faces
    # opérateur de diffusion (Dirichlet p=0 sur la face r=R, demi-maille)
    main = np.zeros(N)
    up = np.zeros(N - 1)
    lo = np.zeros(N - 1)
    for i in range(N):
        if i < N - 1:
            c = k * rf[i + 1] / dr
            main[i] -= c
            up[i] += c
        else:
            main[i] -= k * rf[N] / (0.5 * dr)
        if i > 0:
            c = k * rf[i] / dr
            main[i] -= c
            lo[i - 1] += c
    A = np.diag(main) + np.diag(up, 1) + np.diag(lo, -1)
    vol = r * dr
    p = np.zeros(N)
    fun = lambda qq: g_smeared(qq, h, cfg, well)
    dfun = lambda qq: dg_smeared_dq(qq, h, cfg, well)
    q = invert(fun, dfun, np.full(N, ps))
    for _ in range(60):
        q = invert(fun, dfun, ps - p, q0=q)
        dqdp = -1.0 / dfun(q)
        F = A @ p + n * q * vol
        J = A + np.diag(n * dqdp * vol)
        dp = np.linalg.solve(J, -F)
        p = p + dp
        if np.max(np.abs(dp)) < 1e-9 * max(ps, 1.0):
            break
    q = invert(fun, dfun, ps - p, q0=q)
    W = float(np.sum(p * TWO_PI * r * dr))
    Q = float(np.sum(n * q * TWO_PI * r * dr))
    return dict(r=r, p=p, q=q, W=W, Q=Q, dr=dr, A=A, k=k, rf=rf,
                gq=dfun(q), gh=dg_smeared_dh(q, h, cfg, well))


def axi_W(cfg, ps, h, well=True):
    return axi_solve(cfg, ps, h, well)["W"]


def axi_kz(cfg, ps, h, well=True, rel=0.02):
    """Raideur verticale quasi statique k_z = −dW/dh (N/m)."""
    return -(axi_W(cfg, ps, h * (1 + rel), well) - axi_W(cfg, ps, h * (1 - rel), well)) / (
        2 * rel * h)


def axi_ktheta(cfg, ps, h, well=True, sol=None):
    """Raideur en basculement k_θ (N·m/rad), mode m = 1 linéarisé.

    h = h0 + θ r cos φ ; p = p0(r) + θ p1(r) cos φ ;
    h0³[(1/r)(r p1')' − p1/r²] + 3 h0² (1/r)(r² p0')' = 12μ n (p1 + g_h r)/g_q.
    """
    s = sol or axi_solve(cfg, ps, h, well)
    r, p0, dr, rf, A = s["r"], s["p"], s["dr"], s["rf"], s["A"]
    N = len(r)
    n = cfg.density
    k = s["k"]
    # terme source (1/r)(r² p0')' × r dr = [r² p0']_faces
    dp0 = np.zeros(N + 1)
    dp0[1:N] = (p0[1:] - p0[:-1]) / dr
    dp0[N] = (0 - p0[-1]) / (0.5 * dr)
    src = 3 * h**2 / (12 * MU) * (rf[1:] ** 2 * dp0[1:] - rf[:-1] ** 2 * dp0[:-1])
    vol = r * dr
    M = A - np.diag(k * dr / r) - np.diag(n * vol / s["gq"])
    rhs = -src + n * s["gh"] * r * vol / s["gq"]
    p1 = np.linalg.solve(M, rhs)
    return float(-np.pi * np.sum(p1 * r**2 * dr))


def axi_solve_h(cfg, ps, m_kg, well=True, hlo=5e-6, hhi=1.5e-3):
    """Entrefer h tel que W = m g (modèle axisymétrique)."""
    W = m_kg * G
    f = lambda h: axi_W(cfg, ps, h, well) - W
    if f(hhi) > 0:
        return np.inf
    if f(hlo) < 0:
        return np.nan
    return brentq(f, hlo, hhi, xtol=1e-9, rtol=1e-7)


# ===========================================================================
# 2. Modèle discret, film parallèle : fonction de Green du disque
# ===========================================================================
def green_matrix(xy: np.ndarray, r_h: float, R=R_PUCK):
    """Matrice G_D(x_j, x_i) (sans le facteur 12μ/h³) ; diagonale au rayon r_h."""
    x = xy[:, None, :]
    xi = xy[None, :, :]
    d2 = np.sum((x - xi) ** 2, axis=-1)
    rx2 = np.sum(x**2, axis=-1)
    rxi2 = np.sum(xi**2, axis=-1)
    dot = np.sum(x * xi, axis=-1)
    num = rxi2 * rx2 - 2 * R**2 * dot + R**4
    np.fill_diagonal(d2, r_h**2)
    Gm = np.log(num / (R**2 * d2)) / (4 * np.pi)
    # trou à moins de r_h/2 du bord : pas de contre-pression propre (jet libre)
    dg = np.diagonal(Gm).copy()
    np.fill_diagonal(Gm, np.maximum(dg, 0.0))
    return Gm


RIM_MODEL = "smooth"       # "smooth" (transition continue) ou "abrupt" (ρ < R − r_h)


def covered_holes(cfg: HoleConfig, center, R=R_PUCK, rim=None):
    """Trous couverts ou partiellement couverts (relatifs au centre du palet).

    Un trou dont le centre est à ρ < R + r_h interagit avec le film. Pour assurer
    une transition continue lorsqu'un trou passe sous le bord (le jet est
    progressivement recouvert sur une course d = 2 r_h), les trous de la bande
    R − r_h < ρ < R + r_h sont placés à la distance effective au bord
    δ_eff = (R + r_h − ρ)/2 ∈ [0, r_h] (même direction). Leur portance
    (∝ R² − ρ'²) tend ainsi continûment vers 0 au découvrement.
    """
    if (rim or RIM_MODEL) == "abrupt":
        return holes_near(cfg, np.asarray(center, float), R - cfg.r_h)
    xy = holes_near(cfg, np.asarray(center, float), R + cfg.r_h)
    rho = np.hypot(xy[:, 0], xy[:, 1])
    band = rho > R - cfg.r_h
    if np.any(band):
        d_eff = 0.5 * (R + cfg.r_h - rho[band])
        xy = xy.copy()
        xy[band] *= ((R - d_eff) / rho[band])[:, None]
        keep = np.ones(len(xy), bool)
        keep[np.nonzero(band)[0][d_eff < 1e-3 * cfg.r_h]] = False
        xy = xy[keep]
    return xy


def solve_sources(Gm, ps, h_i, cfg: HoleConfig, q0=None, dps=None):
    """Résout Δp_trou(q)+Δp_rideau(q,h)+Gm·q = ps − dps (Newton, q ≥ 0).

    dps : décalage optionnel par trou (Pa) — sert au Monte-Carlo (trous de
    diamètres différents traités par un facteur d'échelle de débit).
    """
    n = Gm.shape[0]
    tgt = ps - (0 if dps is None else dps)
    q = np.full(n, 0.3) * (q0 if q0 is not None else 1e-6) if np.isscalar(q0) or q0 is None \
        else np.array(q0, float)
    for it in range(80):
        F = dp_hole(q, cfg) + dp_curtain(q, h_i, cfg) + Gm @ q - tgt
        J = Gm + np.diag(ddp_hole(q, cfg) + ddp_curtain_dq(q, h_i, cfg))
        dq = np.linalg.solve(J, -F)
        lam = 1.0
        qn = q + dq
        while np.any(qn < 0) and lam > 1e-3:
            lam *= 0.5
            qn = q + lam * dq
        q = np.maximum(qn, 0.0)
        if np.max(np.abs(dq)) < 1e-10 * max(np.max(q), 1e-12):
            break
    return q


def green_solve(cfg: HoleConfig, ps: float, h: float, center=(0.0, 0.0), xy=None,
                q0=None, R=R_PUCK, scale=None):
    """Modèle discret, film parallèle. Retourne q, p_i, W, M(2), Q, xy.

    scale : facteur multiplicatif optionnel sur le débit de chaque trou
            (dispersion de diamètre) — appliqué via une loi q_i = s_i·q(Δp).
    """
    if xy is None:
        xy = covered_holes(cfg, center, R)
    n = len(xy)
    if n == 0:
        return dict(q=np.zeros(0), p=np.zeros(0), W=0.0, M=np.zeros(2), Q=0.0, xy=xy)
    c = 12 * MU / h**3
    Gm = c * green_matrix(xy, cfg.r_h, R)
    hi = np.full(n, h)
    if scale is None:
        q = solve_sources(Gm, ps, hi, cfg, q0=q0)
    else:
        q = _solve_scaled(Gm, ps, hi, cfg, scale, q0)
    rho2 = np.sum(xy**2, axis=1)
    wgt = (R**2 - rho2)
    W = c * np.sum(q * wgt) / 4
    M = c * np.sum((q * wgt)[:, None] * xy, axis=0) / 8
    p = Gm @ q
    return dict(q=q, p=p, W=float(W), M=M, Q=float(q.sum()), xy=xy, n=n)


def _solve_scaled(Gm, ps, hi, cfg, s, q0):
    """Variante de solve_sources où le trou i suit Δp = Δp_trou(q/s_i)."""
    n = Gm.shape[0]
    q = np.full(n, 3e-7) if q0 is None else np.array(q0, float)
    for _ in range(80):
        F = dp_hole(q / s, cfg) + dp_curtain(q, hi, cfg) + Gm @ q - ps
        J = Gm + np.diag(ddp_hole(q / s, cfg) / s + ddp_curtain_dq(q, hi, cfg))
        dq = np.linalg.solve(J, -F)
        lam = 1.0
        qn = q + dq
        while np.any(qn < 0) and lam > 1e-3:
            lam *= 0.5
            qn = q + lam * dq
        q = np.maximum(qn, 0.0)
        if np.max(np.abs(dq)) < 1e-10 * max(np.max(q), 1e-12):
            break
    return q


def rim_outflow(sol: dict, R=R_PUCK, nphi=720):
    """Débit sortant par unité de longueur au bord (noyau de Poisson), φ, q_n."""
    phi = np.linspace(0, TWO_PI, nphi, endpoint=False)
    xb = R * np.stack([np.cos(phi), np.sin(phi)], axis=1)
    xy, q = sol["xy"], sol["q"]
    d2 = np.sum((xb[:, None, :] - xy[None, :, :]) ** 2, axis=-1)
    ker = (R**2 - np.sum(xy**2, axis=1))[None, :] / (TWO_PI * R * d2)
    return phi, ker @ q


def momentum_force(sol: dict, h: float, cfg: HoleConfig, R=R_PUCK, share=0.5):
    """Force sur le palet due au flux de quantité de mouvement sortant au bord,
    profil de Poiseuille (facteur 6/5), part `share` attribuée au palet.

    Régularisation : pour un trou à une distance δ du bord, le noyau de Poisson
    concentre la sortie sur un arc ~δ et ∮q_n² diverge en 1/δ ; hors du domaine
    de la lubrification (δ ≲ max(d, 2h)) on borne donc δ à δ_min = max(d, 2h),
    ce qui ramène l'effort d'un trou de bord à ~0,3·(d/h)·ρqV, cohérent avec le
    flux de quantité de mouvement du jet. Les effets propres aux jets de bord
    (déviation par l'arête, Coanda) sont estimés à part par `rim_jet_force`."""
    xy = sol["xy"]
    rho = np.maximum(np.hypot(xy[:, 0], xy[:, 1]), 1e-12)
    rho_reg = np.minimum(rho, R - d_min(cfg, h))
    sub = dict(xy=xy * (rho_reg / rho)[:, None], q=sol["q"])
    phi, qn = rim_outflow(sub, R)
    n = np.stack([np.cos(phi), np.sin(phi)], axis=1)
    flux = 1.2 * RHO * qn**2 / h
    return -share * np.sum(flux[:, None] * n, axis=0) * R * (TWO_PI / len(phi))


def d_min(cfg: HoleConfig, h: float) -> float:
    return max(cfg.d, 2 * h)


def rim_jet_force(cfg: HoleConfig, center, ps, beta=0.1, R=R_PUCK):
    """Estimation (ordre de grandeur) de l'effort horizontal des jets des trous
    situés dans la bande |ρ − R| < d autour du bord du palet (jet partiellement
    recouvert, déviation par l'arête, effet Coanda sur la face latérale) :
    F = −β·Σ w_i·ρ q V·n̂_i, poids en triangle w_i = 1 − |ρ_i − R|/d."""
    from calc.aero.orifice import q_free
    xy = holes_near(cfg, np.asarray(center, float), R + cfg.d)
    rho = np.hypot(xy[:, 0], xy[:, 1])
    band = np.abs(rho - R) < cfg.d
    if not np.any(band):
        return np.zeros(2)
    qf = float(q_free(ps, cfg))
    J = RHO * qf * qf / cfg.A
    w = 1 - np.abs(rho[band] - R) / cfg.d
    nhat = xy[band] / rho[band][:, None]
    return -beta * J * np.sum(w[:, None] * nhat, axis=0)


def green_solve_h(cfg, ps, m_kg, center=(0.0, 0.0), hlo=5e-6, hhi=1.5e-3):
    """Entrefer h tel que W = m g pour une position donnée (modèle discret)."""
    xy = covered_holes(cfg, center)
    W = m_kg * G
    f = lambda h: green_solve(cfg, ps, h, xy=xy)["W"] - W
    if f(hhi) > 0:
        return np.inf
    if f(hlo) < 0:
        return np.nan
    return brentq(f, hlo, hhi, xtol=1e-10, rtol=1e-8)


# ===========================================================================
# 3. Différences finies 2D, film incliné (et dégagement de bord optionnel)
# ===========================================================================
def _G0(dx, dy, r_min):
    return -0.5 * np.log(np.maximum(dx * dx + dy * dy, r_min * r_min)) / TWO_PI


class Relief:
    """Dégagement périphérique de la face inférieure du palet :
    e(ρ) = e_max·s^k, s = (ρ − (R − w))/w ∈ [0, 1] (k = 2 : raccordement tangent,
    k = 1 : chanfrein conique)."""

    def __init__(self, w=0.0, e_max=0.0, k=2, R=R_PUCK):
        self.w, self.e, self.k, self.R = w, e_max, k, R

    def active(self):
        return self.w > 0 and self.e > 0

    def _s(self, rho):
        return np.clip((rho - (self.R - self.w)) / self.w, 0.0, 1.0)

    def value(self, x, y):
        if not self.active():
            return 0.0 * x
        return self.e * self._s(np.hypot(x, y)) ** self.k

    def grad(self, x, y):
        if not self.active():
            return 0.0 * x, 0.0 * y
        rho = np.maximum(np.hypot(x, y), 1e-12)
        s = self._s(rho)
        de = self.k * self.e * s ** (self.k - 1) / self.w * ((s > 0) & (s < 1))
        return de * x / rho, de * y / rho


NO_RELIEF = Relief()


class FD2D:
    """Solveur de Reynolds 2D sur le disque, film h = h0 + a x + b y + e(ρ)."""

    def __init__(self, N=150, R=R_PUCK, nsub=4):
        self.R = R
        self.N = N
        self.D = 2 * R / N
        D = self.D
        x = -R + (np.arange(N) + 0.5) * D
        self.x = x
        X, Y = np.meshgrid(x, x, indexing="ij")
        self.X, self.Y = X, Y
        inside = X**2 + Y**2 < R**2
        self.inside = inside
        idx = -np.ones((N, N), int)
        idx[inside] = np.arange(inside.sum())
        self.idx = idx
        self.nn = int(inside.sum())
        s = (np.arange(10) + 0.5) / 10 - 0.5
        SX, SY = np.meshgrid(s, s)
        frac = np.zeros((N, N))
        for ox, oy in zip(SX.ravel(), SY.ravel()):
            frac += ((X + ox * D) ** 2 + (Y + oy * D) ** 2 < R**2)
        self.frac = frac / 100.0
        self.wq = self.frac * D * D            # poids de quadrature
        so = (np.arange(nsub) + 0.5) / nsub - 0.5
        self.sub = [(ox * D, oy * D) for ox in so for oy in so]
        I, J = np.nonzero(inside)
        self.I, self.J = I, J
        links = []
        for (di, dj) in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ii, jj = I + di, J + dj
            ok = (ii >= 0) & (ii < N) & (jj >= 0) & (jj < N)
            nb = np.full(I.shape, -1)
            nb[ok] = idx[ii[ok], jj[ok]]
            xn, yn = X[I, J], Y[I, J]
            dist = np.full(I.shape, D)
            xb = xn + di * D
            yb = yn + dj * D
            bnd = nb < 0
            if di != 0:
                sq = np.sqrt(R**2 - yn[bnd] ** 2)
                dist[bnd] = np.where(di > 0, sq - xn[bnd], xn[bnd] + sq)
                xb[bnd] = xn[bnd] + di * dist[bnd]
            else:
                sq = np.sqrt(R**2 - xn[bnd] ** 2)
                dist[bnd] = np.where(dj > 0, sq - yn[bnd], yn[bnd] + sq)
                yb[bnd] = yn[bnd] + dj * dist[bnd]
            dist = np.maximum(dist, 1e-4 * D)
            links.append(dict(nb=nb, dist=dist, xb=xb, yb=yb,
                              xm=0.5 * (xn + xb), ym=0.5 * (yn + yb)))
        self.links = links
        self.ghost_I, self.ghost_J = np.nonzero(~inside)
        gx, gy = X[~inside], Y[~inside]
        rr = np.hypot(gx, gy)
        self.ghost_xb = gx * R / rr
        self.ghost_yb = gy * R / rr
        self.relief = NO_RELIEF

    # -- géométrie du film ---------------------------------------------------
    def h_at(self, x, y):
        return self.h0 + self.a * x + self.b * y + self.relief.value(x, y)

    def grad_h(self, x, y):
        gx, gy = self.relief.grad(x, y)
        return self.a + gx, self.b + gy

    # -- assemblage de l'opérateur ∇·(h³∇·) -----------------------------------
    def assemble(self, h0, a, b, relief=None):
        self.h0, self.a, self.b = h0, a, b
        self.relief = relief if relief is not None else NO_RELIEF
        rows, cols, vals = [], [], []
        diag = np.zeros(self.nn)
        bnd = []
        row = np.arange(self.nn)
        Lk = self.links
        for k, lk in enumerate(Lk):
            opp = Lk[k ^ 1]
            span = 0.5 * (lk["dist"] + opp["dist"])
            hm = self.h_at(lk["xm"], lk["ym"])
            coef = hm**3 / (lk["dist"] * span)
            diag -= coef
            inn = lk["nb"] >= 0
            rows.append(row[inn]); cols.append(lk["nb"][inn]); vals.append(coef[inn])
            bnd.append((row[~inn], coef[~inn], lk["xb"][~inn], lk["yb"][~inn]))
        rows.append(row); cols.append(row); vals.append(diag)
        A = sp.csc_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
                          shape=(self.nn, self.nn))
        self.bnd = bnd
        self.lu = spla.splu(A)

    # -- réponses unitaires w_i (c_i = 1) ---------------------------------------
    def unit_responses(self, xy, r_h):
        """Partie régulière w_i de la réponse à une source unitaire c_i = 1 :
        ∇·(h³∇w_i) = −3h²∇h·∇G0_i,  w_i = −G0_i sur le bord."""
        I, J = self.I, self.J
        xn, yn = self.X[I, J], self.Y[I, J]
        nh = len(xy)
        rhs = np.zeros((self.nn, nh))
        tilted = (self.a != 0) or (self.b != 0) or self.relief.active()
        if tilted:
            acc = np.zeros((self.nn, nh))
            for ox, oy in self.sub:
                xs = (xn + ox)[:, None]
                ys = (yn + oy)[:, None]
                dx = xs - xy[None, :, 0]
                dy = ys - xy[None, :, 1]
                r2 = np.maximum(dx * dx + dy * dy, r_h * r_h)
                hs = self.h_at(xs, ys)
                gx, gy = self.grad_h(xs, ys)
                acc += 3 * hs**2 * (gx * dx + gy * dy) / (TWO_PI * r2)
            rhs += acc / len(self.sub)
        for (rr, coef, xb, yb) in self.bnd:
            gb = -_G0(xb[:, None] - xy[None, :, 0], yb[:, None] - xy[None, :, 1], r_h)
            np.add.at(rhs, rr, -coef[:, None] * gb)
        w = self.lu.solve(rhs)
        full = np.zeros((self.N, self.N, nh))
        full[I, J, :] = w
        gI, gJ = self.ghost_I, self.ghost_J
        full[gI, gJ, :] = -_G0(self.ghost_xb[:, None] - xy[None, :, 0],
                               self.ghost_yb[:, None] - xy[None, :, 1], r_h)
        return full

    def interp(self, full, pts):
        """Interpolation bilinéaire de champs (N,N,k) aux points pts (m,2)."""
        D, R = self.D, self.R
        fx = (pts[:, 0] + R) / D - 0.5
        fy = (pts[:, 1] + R) / D - 0.5
        i0 = np.clip(np.floor(fx).astype(int), 0, self.N - 2)
        j0 = np.clip(np.floor(fy).astype(int), 0, self.N - 2)
        tx = fx - i0
        ty = fy - j0
        return ((1 - tx)[:, None] * (1 - ty)[:, None] * full[i0, j0]
                + tx[:, None] * (1 - ty)[:, None] * full[i0 + 1, j0]
                + (1 - tx)[:, None] * ty[:, None] * full[i0, j0 + 1]
                + tx[:, None] * ty[:, None] * full[i0 + 1, j0 + 1])

    def solve(self, cfg: HoleConfig, ps, xy, h0, a=0.0, b=0.0, relief=None, q0=None,
              want_field=False):
        """Résout le film ; retourne q, W, M, F (force latérale), Q.

        F = −½∫p∇h dA = −½[(a, b)·W + ∫p∇e dA] (pression + cisaillement).
        """
        R = self.R
        self.assemble(h0, a, b, relief)
        full = self.unit_responses(xy, cfg.r_h)
        wij = self.interp(full, xy)
        dx = xy[:, None, 0] - xy[None, :, 0]
        dy = xy[:, None, 1] - xy[None, :, 1]
        G0m = _G0(dx, dy, 1e-30)
        G0m[np.diag_indices_from(G0m)] = _G0(np.array(cfg.r_h), np.array(0.0), 0.0)
        hi = self.h_at(xy[:, 0], xy[:, 1])
        ci = 12 * MU / hi**3
        Gm = (G0m + wij) * ci[None, :]
        dg = np.diagonal(Gm).copy()
        Gm[np.diag_indices_from(Gm)] = np.maximum(dg, 0.0)
        q = solve_sources(Gm, ps, hi, cfg, q0=q0)
        rho2 = np.sum(xy**2, axis=1)
        IG0 = -R**2 * np.log(R) / 2 + (R**2 - rho2) / 4
        IxG0 = xy * ((R**2 / 2 - rho2 / 4) / 2)[:, None]
        wq = self.wq[:, :, None]
        Iw = np.sum(full * wq, axis=(0, 1))
        Ixw = np.sum(full * (wq * self.X[:, :, None]), axis=(0, 1))
        Iyw = np.sum(full * (wq * self.Y[:, :, None]), axis=(0, 1))
        cq = ci * q
        W = float(np.sum(cq * (IG0 + Iw)))
        M = np.array([np.sum(cq * (IxG0[:, 0] + Ixw)), np.sum(cq * (IxG0[:, 1] + Iyw))])
        F = -0.5 * np.array([a, b]) * W
        out = dict(q=q, W=W, M=M, Q=float(q.sum()), xy=xy, h_i=hi)
        if self.relief.active() or want_field:
            G0g = _G0(self.X[:, :, None] - xy[None, None, :, 0],
                      self.Y[:, :, None] - xy[None, None, :, 1], cfg.r_h)
            pg = np.sum((G0g + full) * cq[None, None, :], axis=2)
            gx, gy = self.relief.grad(self.X, self.Y)
            F = F - 0.5 * np.array([np.sum(pg * gx * self.wq), np.sum(pg * gy * self.wq)])
            out["p_grid"] = pg
        out["F"] = F
        return out

    def ktheta(self, cfg, ps, xy, h0, dth=2e-7, relief=None):
        """k_θ = −dM_x/da (N·m/rad) par différence centrée (a = ±dth rad)."""
        sp_ = self.solve(cfg, ps, xy, h0, +dth, 0.0, relief)
        sm_ = self.solve(cfg, ps, xy, h0, -dth, 0.0, relief)
        return -(sp_["M"][0] - sm_["M"][0]) / (2 * dth), sp_, sm_

    def equilibrium(self, cfg, ps, xy, m_kg, x_cg=(0.0, 0.0), h_init=None,
                    kth=None, relief=None, tol=1e-7, itmax=8):
        """Équilibre complet (h0, a, b) : W = m g et M = m g·x_cg (Newton)."""
        Wt = m_kg * G
        Mt = Wt * np.asarray(x_cg, float)
        z = np.array([h_init if h_init else 120e-6, 0.0, 0.0])
        if kth is not None:
            s0 = self.solve(cfg, ps, xy, z[0], relief=relief)
            z[1:] = (s0["M"] - Mt) / kth
        hist = []
        sc = np.array([Wt, Wt * R_PUCK, Wt * R_PUCK])
        Jm = None
        for it in range(itmax):
            s = self.solve(cfg, ps, xy, *z, relief=relief)
            res = np.array([s["W"] - Wt, *(s["M"] - Mt)])
            hist.append(float(np.abs(res / sc).max()))
            if hist[-1] < tol:
                break
            if Jm is None:
                Jm = np.zeros((3, 3))
                steps = [z[0] * 1e-3, 2e-7, 2e-7]
                for k in range(3):
                    zz = z.copy()
                    zz[k] += steps[k]
                    s2 = self.solve(cfg, ps, xy, *zz, relief=relief, q0=s["q"])
                    Jm[:, k] = (np.array([s2["W"] - Wt, *(s2["M"] - Mt)]) - res) / steps[k]
            z = z - np.linalg.solve(Jm, res)
        return dict(h0=z[0], a=z[1], b=z[2], sol=s, hist=hist, F=s["F"])


# ===========================================================================
# 4. Crantage : statistiques sur une cellule du réseau
# ===========================================================================
def magic_pitches(pattern="hex", R=R_PUCK, kmax=12):
    """Pas « magiques » annulant le premier anneau du réseau réciproque pour le
    moment de portance d'un débit uniforme (zéros de J3 : |G1|·R = j3,k)."""
    from scipy.special import jn_zeros
    j = jn_zeros(3, kmax)
    if pattern == "hex":
        return 4 * np.pi * R / (np.sqrt(3) * j)
    return 2 * np.pi * R / j


def cogging_stats(cfg: HoleConfig, ps: float, h: float, kth: float, kz: float,
                  n=10, R=R_PUCK, rim=None, momentum=False, positions=None):
    """Portance, moment, basculement et force latérale sur la cellule primitive.

    Retourne un dict de tableaux (positions, W, M, tilt, slope_vec) et de
    statistiques. La pente équivalente est F_lat/W avec F_lat = −½W·θ
    (+ terme de quantité de mouvement si momentum=True)."""
    from calc.aero.common import unit_cell_positions
    pos = unit_cell_positions(cfg, n) if positions is None else positions
    W = np.zeros(len(pos))
    M = np.zeros((len(pos), 2))
    Fm = np.zeros((len(pos), 2))
    Fj = np.zeros((len(pos), 2))
    nh = np.zeros(len(pos), int)
    for k, c in enumerate(pos):
        xy = covered_holes(cfg, c, R, rim)
        s = green_solve(cfg, ps, h, xy=xy, R=R)
        W[k], M[k], nh[k] = s["W"], s["M"], s["n"]
        if momentum:
            Fm[k] = momentum_force(s, h, cfg, R)
            Fj[k] = rim_jet_force(cfg, c, ps, R=R)
    rms = lambda v: float(np.sqrt(np.mean(np.sum(v**2, 1))))
    tilt = M / kth
    slope_tilt = -0.5 * tilt                  # mécanisme de basculement
    slope = slope_tilt + Fm / W[:, None]      # + quantité de mouvement du film
    sl = np.hypot(slope[:, 0], slope[:, 1])
    slope_all = slope + Fj / W[:, None]       # + estimation jets de bord
    sla = np.hypot(slope_all[:, 0], slope_all[:, 1])
    return dict(pos=pos, W=W, M=M, tilt=tilt, slope=slope, Fmom=Fm, Fjet=Fj, n_holes=nh,
                slope_tilt=slope_tilt, slope_tilt_rms=rms(slope_tilt),
                slope_all=slope_all, slope_all_rms=float(np.sqrt(np.mean(sla**2))),
                slope_all_max=float(sla.max()),
                Fjet_rms_over_W=rms(Fj / W[:, None]),
                W_mean=float(W.mean()), W_ripple_pp=float((W.max() - W.min()) / W.mean()),
                W_std_rel=float(W.std() / W.mean()), dh_pp=float((W.max() - W.min()) / kz),
                slope_rms=float(np.sqrt(np.mean(sl**2))), slope_max=float(sl.max()),
                tilt_rms=float(np.sqrt(np.mean(np.sum(tilt**2, 1)))),
                Fmom_rms_over_W=rms(Fm / W[:, None]),
                n_min=int(nh.min()), n_max=int(nh.max()))
