"""Bibliothèque : champ de crantage périodique, puits de potentiel et seuil de décrochage.

Le crantage est décrit par la « pente équivalente » s(x) (vecteur, rad) : force
latérale parasite / (m g) en fonction de la position x du centre du palet. Elle est
calculée sur une grille de la cellule primitive (`film.cogging_stats` : basculement
+ quantité de mouvement du film), puis :

- périodisée exactement par série de Fourier sur le réseau réciproque ;
- décomposée (Helmholtz) en partie conservative (gradient d'un potentiel U, en rad·m,
  énergie par unité de masse g·U) et partie solénoïdale (circulation) ;
- ré-échantillonnée sur une grille fine en coordonnées réduites et interpolée
  bilinéairement (évaluation rapide pour les simulations d'ensemble).

Seuil de décrochage statique θ_dep(ê) : pente uniforme θ ê ajoutée lentement (rampe
quasi statique, dynamique sur-amortie ẋ ∝ s(x) + θ ê) ; θ_dep est la valeur à laquelle
le palet quitte définitivement son puits (déplacement > 3 pas). On retient le minimum
sur les directions (pire direction de la pente résiduelle) et sur les puits de la cellule.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage

from calc.aero.common import G, MU, A_PUCK, R_PUCK, lattice_vectors
from calc.aero import film as F
from calc.aero.optimize import ps_for

N_GRID = 24          # positions de calcul par vecteur du réseau
N_FINE = 96          # grille d'interpolation


def build_field(cfg, m, h, n=N_GRID, R=R_PUCK, lattice=None, scale_fn=None):
    """Carte s(x) sur la cellule (n × n, coordonnées réduites u, v ∈ [0, 1)).

    lattice  : (a1, a2) d'une super-cellule (motif modulé) ; défaut = réseau du perçage.
    scale_fn : fonction (positions absolues des trous (k, 2)) → facteur de débit par trou.
    """
    ps = ps_for(cfg, m, h)
    kth = F.axi_ktheta(cfg, ps, h)
    kz = F.axi_kz(cfg, ps, h)
    a1, a2 = lattice if lattice is not None else lattice_vectors(cfg)
    u = np.arange(n) / n
    U, V = np.meshgrid(u, u, indexing="ij")
    pos = U.reshape(-1, 1) * a1 + V.reshape(-1, 1) * a2
    if scale_fn is None:
        st = F.cogging_stats(cfg, ps, h, kth, kz, momentum=True, positions=pos, R=R)
        S, W = st["slope"], st["W"]
    else:
        W0 = m * 1e-3 * G
        S = np.zeros((len(pos), 2))
        W = np.zeros(len(pos))
        for k, c in enumerate(pos):
            xy = F.covered_holes(cfg, c, R)
            s = scale_fn(xy + c)
            sol = F.green_solve(cfg, ps, h, xy=xy, R=R, scale=s)
            W[k] = sol["W"]
            S[k] = -0.5 * sol["M"] / kth + F.momentum_force(sol, h, cfg, R) / W0
    return dict(m=m, h=h, ps=ps, kth=kth, kz=kz, S=S.reshape(n, n, 2), W=W.reshape(n, n),
                a1=np.asarray(a1), a2=np.asarray(a2), n=n)


class Field:
    """Champ périodique s(x) : série de Fourier + grille fine interpolée."""

    def __init__(self, fd, keep=1e-3, nf=N_FINE):
        n = fd["n"]
        self.a1, self.a2 = fd["a1"], fd["a2"]
        self.A = np.array([self.a1, self.a2])
        self.Ainv = np.linalg.inv(self.A)
        B = 2 * np.pi * self.Ainv.T
        Cx = np.fft.fft2(fd["S"][:, :, 0]) / n**2
        Cy = np.fft.fft2(fd["S"][:, :, 1]) / n**2
        k = np.fft.fftfreq(n, 1.0 / n).astype(int)
        K, L = np.meshgrid(k, k, indexing="ij")
        ok = (np.abs(K) < n // 2) & (np.abs(L) < n // 2)
        amp = np.hypot(np.abs(Cx), np.abs(Cy))
        ok &= amp > keep * amp.max()
        self.Gv = K[ok][:, None] * B[0] + L[ok][:, None] * B[1]
        self.C = np.stack([Cx[ok], Cy[ok]], axis=1)
        g = np.hypot(self.Gv[:, 0], self.Gv[:, 1])
        nz = g > 0
        gh = np.zeros_like(self.Gv)
        gh[nz] = self.Gv[nz] / g[nz, None]
        CL = np.sum(self.C * gh, axis=1)[:, None] * gh
        CT = self.C - CL
        eL = float(np.sum(np.abs(CL[nz]) ** 2))
        eT = float(np.sum(np.abs(CT[nz]) ** 2))
        self.frac_conservative = eL / (eL + eT)
        self.UG = np.zeros(len(g), complex)
        self.UG[nz] = 1j * np.sum(self.C[nz] * gh[nz], axis=1) / g[nz]
        self.CT = CT
        # grille fine (coordonnées réduites) pour l'interpolation
        self.nf = nf
        uf = np.arange(nf) / nf
        Uf, Vf = np.meshgrid(uf, uf, indexing="ij")
        self.Xf = Uf.reshape(-1, 1) * self.a1 + Vf.reshape(-1, 1) * self.a2
        ph = np.exp(1j * (self.Xf @ self.Gv.T))
        self.Sf = np.real(ph @ self.C).reshape(nf, nf, 2)
        self.Uf = np.real(ph @ self.UG).reshape(nf, nf)
        self.STf = np.real(ph @ CT).reshape(nf, nf, 2)
        cz = 1j * (self.Gv[:, 0] * self.C[:, 1] - self.Gv[:, 1] * self.C[:, 0])
        self.curl_f = np.real(ph @ cz).reshape(nf, nf)
        self._S = np.concatenate([self.Sf, self.Sf[:1]], 0)
        self._S = np.concatenate([self._S, self._S[:, :1]], 1)

    def __call__(self, X):
        """s(X) par interpolation bilinéaire périodique (X : (N, 2) en m)."""
        uv = (X @ self.Ainv) * self.nf
        i0 = np.floor(uv).astype(int)
        t = uv - i0
        i = np.mod(i0[:, 0], self.nf)
        j = np.mod(i0[:, 1], self.nf)
        S = self._S
        tx, ty = t[:, :1], t[:, 1:]
        return ((1 - tx) * (1 - ty) * S[i, j] + tx * (1 - ty) * S[i + 1, j]
                + (1 - tx) * ty * S[i, j + 1] + tx * ty * S[i + 1, j + 1])

    # -- puits -----------------------------------------------------------------
    def minima(self):
        """Minima locaux du potentiel sur la grille fine (périodique)."""
        U = self.Uf
        mn = ndimage.minimum_filter(U, size=5, mode="wrap")
        idx = np.argwhere(U <= mn + 1e-30)
        return [(int(a), int(b)) for a, b in idx]

    def barrier(self):
        """Barrière d'échappement minimale (percolation de {U ≤ niveau} sur 3 × 3 cellules)."""
        U = self.Uf
        T = np.tile(U, (3, 3))
        lo, hi = U.min(), U.max()
        for _ in range(40):
            L = 0.5 * (lo + hi)
            lab, _ = ndimage.label(T <= L, structure=np.ones((3, 3)))
            span = (set(lab[0, :]) & set(lab[-1, :])) | (set(lab[:, 0]) & set(lab[:, -1]))
            span.discard(0)
            if span:
                hi = L
            else:
                lo = L
        return hi - U.min()

    def hessian_at(self, ij):
        """Raideur du puits : valeurs propres de −∂s/∂x (1/m) au minimum (grille fine)."""
        i, j = ij
        nf = self.nf
        X0 = (i / nf) * self.a1 + (j / nf) * self.a2
        e = 1e-5
        Jm = np.zeros((2, 2))
        for k, d in enumerate(np.eye(2) * e):
            Jm[:, k] = (self(np.array([X0 + d]))[0] - self(np.array([X0 - d]))[0]) / (2 * e)
        Ks = -0.5 * (Jm + Jm.T)
        return np.linalg.eigvalsh(Ks), X0

    def stats(self):
        mag = np.hypot(self.Sf[..., 0], self.Sf[..., 1])
        return dict(rms_urad=float(np.sqrt(np.mean(mag**2)) * 1e6), peak_urad=float(mag.max() * 1e6),
                    frac_conservative=self.frac_conservative,
                    curl_part_rms_urad=float(np.sqrt(np.mean(np.sum(self.STf**2, -1))) * 1e6),
                    potential_range_rad_m=float(self.Uf.max() - self.Uf.min()))


def static_threshold(fld, pitch, angles_deg=tuple(range(0, 60, 5)), dtheta=0.5e-6, theta_max=200e-6,
                     n_relax=150, step=0.02):
    """Seuil de décrochage statique (rampe quasi statique, dynamique sur-amortie).

    Départ : tous les minima de la cellule (relaxés à θ = 0). Retourne θ_dep par
    direction (minimum et maximum sur les puits) et le minimum global.
    """
    mins = fld.minima()
    X0 = np.array([(i / fld.nf) * fld.a1 + (j / fld.nf) * fld.a2 for i, j in mins])
    ang = np.radians(np.array(angles_deg, float))
    nA, nM = len(ang), len(X0)
    X = np.repeat(X0[None], nA, 0).reshape(-1, 2).copy()
    e = np.repeat(np.stack([np.cos(ang), np.sin(ang)], 1), nM, 0)
    # pas de relaxation : déplacement ≈ step·pas pour une pente ~ pic
    smax = max(np.max(np.hypot(fld.Sf[..., 0], fld.Sf[..., 1])), 1e-9)
    eta = step * pitch / smax
    for _ in range(4 * n_relax):
        X += eta * fld(X)
    start = X.copy()
    thr = np.full(len(X), np.inf)
    th = 0.0
    while th < theta_max and np.any(np.isinf(thr)):
        th += dtheta
        act = np.isinf(thr)
        Xa = X[act]
        for _ in range(n_relax):
            Xa += eta * (fld(Xa) + th * e[act])
        X[act] = Xa
        esc = act.copy()
        esc[act] = np.hypot(*(Xa - start[act]).T) > 3 * pitch
        thr[esc] = th
    thr = thr.reshape(nA, nM)
    by_angle = thr.min(1)
    return dict(angles_deg=list(angles_deg), theta_dep_min_urad_by_angle=(by_angle * 1e6).tolist(),
                theta_dep_max_urad_by_angle=(thr.max(1) * 1e6).tolist(),
                theta_dep_urad=float(by_angle.min() * 1e6),
                theta_dep_best_dir_urad=float(by_angle.max() * 1e6), n_minima=nM)


def well_properties(fld, m, h):
    """Profondeur du puits, fréquence et amortissement des oscillations, vitesse de capture."""
    dU = fld.barrier()
    ev, _ = fld.hessian_at(min(fld.minima(), key=lambda ij: fld.Uf[ij]))
    k_min = max(ev.min(), 1e-12)
    omega = np.sqrt(G * k_min)
    tau = m * 1e-3 * h / (MU * A_PUCK)
    return dict(barrier_rad_m=dU, barrier_J_per_kg=G * dU, v_capture_mm_s=np.sqrt(2 * G * dU) * 1e3,
                omega_rad_s=omega, period_s=2 * np.pi / omega, tau_s=tau, Q_factor=omega * tau / 1.0,
                amplitude_decay_time_s=2 * tau,
                oscillation_amp_mm_for_v0_0p1=0.1 / omega)
