"""Dérive passive d'un palet libre dans le champ de crantage (fonctionnement sans compensation).

Équation du mouvement plan (palet non piloté) :

    m ẍ = m g [ s(x) + θ0 ê ] − c ẋ ,     c = μ A / h(m)   (Couette),  τ = m/c

- s(x) : pente équivalente de crantage (basculement + quantité de mouvement du film,
  `film.cogging_stats`), calculée sur une grille n × n de la cellule primitive puis
  **périodisée exactement** par série de Fourier sur le réseau réciproque ;
- θ0 : pente résiduelle uniforme (réglage + planéité + balourd), direction variable ;
- bruit optionnel : pente aléatoire d'Ornstein-Uhlenbeck (courants d'air, σ, t_c).

Analyses :
1. décomposition de Helmholtz du champ (part conservative = gradient, part
   solénoïdale = rotationnel) ; potentiel U(x) et barrière d'échappement (percolation) ;
2. simulation d'ensembles (Verlet amorti, dt = 0,02 s) : piégeage, amplitude et temps
   d'amortissement, seuil de « dépiégeage » θ_dep, vitesse moyenne de dérive vs θ0,
   pour des vitesses initiales 0 / 1 / 10 mm/s ;
3. mitigation passive : crête du crantage à 10 g selon l'entrefer et l'arête du palet.

Écrit results/drift_sim.json et 3 figures.
Lancement : ``python3 -m calc.aero.drift_sim`` (≈ 2–3 min).
"""
from __future__ import annotations

import os
import time
from multiprocessing import Pool

import numpy as np
from scipy import ndimage

from calc.aero.common import (G, MU, A_PUCK, R_PUCK, recommended_config, h_target_for,
                              lattice_vectors, setup_style, savefig, save_json, seq_cmap,
                              SERIES, INK, INK2, MUTED)
from calc.aero import film as F
from calc.aero.optimize import ps_for, crant
from calc.aero.cogging import edge_round_dR

MASSES = (2.0, 5.0, 10.0)
N_GRID = 24
THETA0_URAD = (0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0, 60.0, 80.0)
V0_MM_S = (0.0, 1.0, 10.0)
ANGLES_DEG = (0.0, 15.0, 30.0)     # direction de θ0 par rapport à a1 (symétrie hex : 0–30°)
N_PER = 12                          # palets par (θ0, v0, angle)
DT = 0.02


# ---------------------------------------------------------------------------
# 1. Champ de crantage périodique
# ---------------------------------------------------------------------------
class PeriodicField:
    """s(x) = Σ_G C_G e^{iG·x} (vecteur de pente, rad), à partir d'une grille n × n."""

    def __init__(self, cfg, S, n, keep=2e-3):
        a1, a2 = lattice_vectors(cfg)
        A = np.array([a1, a2])                    # lignes = vecteurs du réseau
        self.A = A
        self.B = 2 * np.pi * np.linalg.inv(A).T   # lignes = vecteurs réciproques
        Cx = np.fft.fft2(S[:, :, 0]) / n**2
        Cy = np.fft.fft2(S[:, :, 1]) / n**2
        k = np.fft.fftfreq(n, 1.0 / n).astype(int)
        K, L = np.meshgrid(k, k, indexing="ij")
        ok = (np.abs(K) < n // 2) & (np.abs(L) < n // 2)
        amp = np.hypot(np.abs(Cx), np.abs(Cy))
        ok &= amp > keep * amp.max()
        self.Gv = K[ok][:, None] * self.B[0] + L[ok][:, None] * self.B[1]
        self.C = np.stack([Cx[ok], Cy[ok]], axis=1)     # (M, 2) complexe
        self.M = len(self.Gv)

    def __call__(self, X):
        ph = X @ self.Gv.T
        c, s = np.cos(ph), np.sin(ph)
        return c @ self.C.real - s @ self.C.imag

    def helmholtz(self):
        g = np.hypot(self.Gv[:, 0], self.Gv[:, 1])
        nz = g > 0
        gh = np.zeros_like(self.Gv)
        gh[nz] = self.Gv[nz] / g[nz, None]
        CL = (np.sum(self.C * gh, axis=1))[:, None] * gh
        CT = self.C - CL
        CT[~nz] = self.C[~nz]                     # moyenne (G = 0) : uniforme
        CL[~nz] = 0
        eL = float(np.sum(np.abs(CL) ** 2))
        eT = float(np.sum(np.abs(CT[nz]) ** 2))
        mean = np.abs(self.C[~nz]).ravel() if np.any(~nz) else np.zeros(2)
        UG = np.zeros(self.M, complex)
        UG[nz] = 1j * np.sum(self.C[nz] * gh[nz], axis=1) / g[nz]
        return dict(frac_conservative=eL / (eL + eT), frac_solenoidal=eT / (eL + eT),
                    mean_urad=float(np.hypot(*np.abs(mean[:2])) * 1e6) if len(mean) >= 2 else 0.0), UG

    def potential(self, X, UG):
        return np.real(np.exp(1j * (X @ self.Gv.T)) @ UG)

    def curl(self, X):
        ph = np.exp(1j * (X @ self.Gv.T))
        cz = 1j * (self.Gv[:, 0] * self.C[:, 1] - self.Gv[:, 1] * self.C[:, 0])
        return np.real(ph @ cz)


def escape_barrier(U, n):
    """Plus petit niveau L tel que {U ≤ L} percole à travers le domaine (3 × 3 cellules)."""
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


def build_field(cfg, m, n=N_GRID):
    h = h_target_for(m)
    ps = ps_for(cfg, m, h)
    kth = F.axi_ktheta(cfg, ps, h)
    kz = F.axi_kz(cfg, ps, h)
    a1, a2 = lattice_vectors(cfg)
    u = np.arange(n) / n
    U, V = np.meshgrid(u, u, indexing="ij")
    pos = U.reshape(-1, 1) * a1 + V.reshape(-1, 1) * a2
    st = F.cogging_stats(cfg, ps, h, kth, kz, momentum=True, positions=pos)
    S = st["slope"].reshape(n, n, 2)
    return dict(m=m, h=h, ps=ps, S=S, pos=pos)


# ---------------------------------------------------------------------------
# 2. Simulation d'ensembles
# ---------------------------------------------------------------------------
def simulate(fld, tau, theta_vec, X0, V0, T, noise=None, rng=None, rec_every=50):
    """Verlet semi-implicite amorti ; θ0 par palet (N, 2). Retourne x(t) échantillonné."""
    X, Vv = X0.copy(), V0.copy()
    nst = int(T / DT)
    traj = [X.copy()]
    eta = np.zeros_like(X)
    for k in range(nst):
        a = G * (fld(X) + theta_vec) - Vv / tau
        if noise is not None:
            sig, tc = noise
            eta += -eta * DT / tc + sig * np.sqrt(2 * DT / tc) * rng.standard_normal(X.shape)
            a += G * eta
        Vv += DT * a
        X += DT * Vv
        if (k + 1) % rec_every == 0:
            traj.append(X.copy())
    return np.array(traj), Vv


def _mass_job(args):
    cfg, m = args
    rng = np.random.default_rng(int(100 * m))
    fd = build_field(cfg, m)
    fld = PeriodicField(cfg, fd["S"], N_GRID)
    hz, UG = fld.helmholtz()
    a1, a2 = lattice_vectors(cfg)
    p = cfg.pitch
    tau = m * 1e-3 * fd["h"] / (MU * A_PUCK)
    # potentiel et barrière (grille fine)
    nf = 72
    u = np.arange(nf) / nf
    Uu, Vv = np.meshgrid(u, u, indexing="ij")
    Xf = Uu.reshape(-1, 1) * a1 + Vv.reshape(-1, 1) * a2
    Uf = fld.potential(Xf, UG).reshape(nf, nf)          # (rad·m) ; énergie/masse = g·U
    dU = escape_barrier(Uf, nf)
    curl = fld.curl(Xf)
    smag = np.hypot(*fld(Xf).T)
    v_trap = np.sqrt(2 * G * dU)
    # ensembles
    combos = [(th, v0, ang) for th in THETA0_URAD for v0 in V0_MM_S for ang in ANGLES_DEG]
    N = len(combos) * N_PER
    th = np.repeat([c[0] for c in combos], N_PER) * 1e-6
    v0 = np.repeat([c[1] for c in combos], N_PER) * 1e-3
    ang = np.radians(np.repeat([c[2] for c in combos], N_PER))
    e = np.stack([np.cos(ang), np.sin(ang)], axis=1)
    X0 = rng.random((N, 1)) * a1 + rng.random((N, 1)) * a2
    phi = rng.random(N) * 2 * np.pi
    V0 = v0[:, None] * np.stack([np.cos(phi), np.sin(phi)], axis=1)
    T = max(8 * tau, 160.0)
    traj, _ = simulate(fld, tau, th[:, None] * e, X0, V0, T)
    tt = np.arange(len(traj)) * DT * 50
    half = len(traj) // 2
    disp = traj[-1] - traj[half]
    vdrift = disp / (tt[-1] - tt[half])
    vpar = np.sum(vdrift * e, axis=1)
    trapped = np.hypot(*disp.T) < 0.5 * p
    # trajectoire « libre » sans crantage : v = g θ0 τ
    rows = []
    for (thc, v0c, angc) in combos:
        sel = (np.isclose(th, thc * 1e-6)) & (np.isclose(v0, v0c * 1e-3)) & (np.isclose(np.degrees(ang), angc))
        idx = np.nonzero(sel)[0]
        # excursion avant piégeage et temps de stabilisation (vitesse < 0,02 mm/s)
        exc = np.max(np.hypot(*(traj[:, idx] - traj[0, idx]).transpose(2, 0, 1)), axis=0)
        sp = np.hypot(*np.diff(traj[:, idx], axis=0).transpose(2, 0, 1)) / (DT * 50)
        settle = []
        for j in range(len(idx)):
            moving = np.nonzero(sp[:, j] > 2e-5)[0]
            settle.append(tt[moving[-1] + 1] if len(moving) else 0.0)
        rows.append(dict(theta0_urad=thc, v0_mm_s=v0c, angle_deg=angc,
                         trapped_fraction=float(np.mean(trapped[idx])),
                         v_drift_mean_mm_s=float(np.mean(vpar[idx]) * 1e3),
                         v_drift_free_mm_s=G * thc * 1e-6 * tau * 1e3,
                         excursion_max_mm=float(np.max(exc) * 1e3),
                         excursion_median_mm=float(np.median(exc) * 1e3),
                         settle_time_median_s=float(np.median(settle)),
                         settle_time_max_s=float(np.max(settle))))
    # seuil de dépiégeage (v0 = 0) : plus petit θ0 où moins de la moitié reste piégée, par direction
    thr = {}
    for angc in ANGLES_DEG:
        r = [x for x in rows if x["v0_mm_s"] == 0.0 and x["angle_deg"] == angc]
        esc = [x["theta0_urad"] for x in r if x["trapped_fraction"] < 0.5]
        thr[str(angc)] = min(esc) if esc else np.inf
    # bruit (courants d'air) : θ0 = 0 et 10 µrad, σ = 5 µrad, t_c = 2 s
    noise_res = {}
    for thn in (0.0, 10.0):
        Nn = 48
        Xn = rng.random((Nn, 1)) * a1 + rng.random((Nn, 1)) * a2
        trn, _ = simulate(fld, tau, np.tile([thn * 1e-6, 0.0], (Nn, 1)), Xn, np.zeros((Nn, 2)),
                          max(6 * tau, 120.0), noise=(5e-6, 2.0), rng=rng)
        d = trn[-1] - trn[len(trn) // 2]
        noise_res[str(thn)] = dict(trapped_fraction=float(np.mean(np.hypot(*d.T) < 0.5 * p)),
                                   v_drift_mean_mm_s=float(np.mean(d[:, 0]) / (len(trn) // 2 * DT * 50) * 1e3),
                                   rms_wander_um=float(np.sqrt(np.mean(np.sum((trn[len(trn) // 2:] - trn[len(trn) // 2:].mean(0)) ** 2, axis=2))) * 1e6))
    # trajectoires d'illustration (θ0 = 0, v0 = 1 mm/s ; θ0 = 1,2·seuil)
    ill = {}
    for key, thc, v0c in (("trap_v1", 0.0, 1.0), ("trap_v10", 0.0, 10.0), ("drift_th40", 40.0, 0.0)):
        sel = np.nonzero(np.isclose(th, thc * 1e-6) & np.isclose(v0, v0c * 1e-3) & np.isclose(ang, 0.0))[0][:4]
        ill[key] = (traj[:, sel] * 1e3).tolist()
    return dict(mass_g=m, h_um=fd["h"] * 1e6, ps_Pa=fd["ps"], tau_s=tau, n_modes=fld.M,
                helmholtz=hz, slope_rms_urad=float(np.sqrt(np.mean(smag**2)) * 1e6),
                slope_max_urad=float(smag.max() * 1e6),
                curl_rms_rad_per_m=float(np.sqrt(np.mean(curl**2))),
                barrier_rad_m=dU, barrier_equiv_height_um=dU * 1e6,
                v_trap_mm_s=v_trap * 1e3, omega_trap_rad_s=None,
                potential_grid=Uf.tolist(), runs=rows, depinning_urad_by_angle=thr,
                depinning_urad=float(min(thr.values())),
                depinning_force_uN=float(min(thr.values()) * 1e-6 * m * 1e-3 * G * 1e6),
                noise=noise_res, illustr=ill, t_sample_s=(tt[:len(traj)]).tolist(), T_s=T)


def _mitig_job(args):
    cfg, m, h_um, dD, r_e, tag = args
    R = R_PUCK + 0.5 * dD * 1e-3 - edge_round_dR(r_e * 1e-3, h_um * 1e-6)
    c = crant(cfg, h_um * 1e-6, n=16, R=R, masses=(m,))[m]
    return dict(case=tag, mass_g=m, h_um=h_um, rms_urad=c["tot"], peak_urad=c["tot_max"],
                tilt_urad=c["tilt"], mom_urad=c["mom"], ps_Pa=c["ps"])


def main():
    t0 = time.time()
    cfg = recommended_config()
    with Pool(min(4, os.cpu_count() or 1)) as pool:
        mit_jobs = [(cfg, 10.0, h, 0.0, 0.0, f"h = {h:.0f} µm") for h in (70.0, 75.0, 80.0, 90.0, 100.0)]
        mit_jobs += [(cfg, 10.0, 80.0, 0.0, r, f"arrondi r = {r:.1f} mm") for r in (0.1, 0.2, 0.3)]
        mit_jobs += [(cfg, 10.0, 80.0, dD, 0.0, f"Ø palet {30 + dD:.1f} mm") for dD in (-0.2, 0.2)]
        mit_jobs += [(cfg.with_(pitch=2.94e-3, D_cb=1.5e-3), 10.0, 80.0, 0.0, 0.0, "hex 2,94"),
                     (cfg.with_(pitch=3.5e-3), 10.0, 80.0, 0.0, 0.0, "hex 3,5")]
        mit = pool.map_async(_mitig_job, mit_jobs)
        res_m = pool.map(_mass_job, [(cfg, m) for m in MASSES])
        mit = mit.get()
    print(f"simulations ({time.time()-t0:.0f} s)")
    res = dict(config=cfg, dt_s=DT, theta0_urad=THETA0_URAD, v0_mm_s=V0_MM_S, angles_deg=ANGLES_DEG,
               n_per=N_PER, masses=res_m, mitigation_10g=mit)
    save_json("drift_sim.json", res)

    plt = setup_style()
    # vitesse de dérive vs θ0
    fig, axs = plt.subplots(1, 3, figsize=(13, 4.0), sharey=True)
    for ax, r in zip(axs, res_m):
        for v0c, col in zip(V0_MM_S, SERIES):
            pts = [x for x in r["runs"] if x["v0_mm_s"] == v0c]
            ths = sorted(set(x["theta0_urad"] for x in pts))
            vm = [np.mean([x["v_drift_mean_mm_s"] for x in pts if x["theta0_urad"] == t]) for t in ths]
            ax.plot(ths, np.maximum(vm, 1e-4), "-o", ms=3.5, color=col, label=f"v0 = {v0c:g} mm/s")
        ths = np.array(THETA0_URAD)
        ax.plot(ths, np.maximum(G * ths * 1e-6 * r["tau_s"] * 1e3, 1e-4), color=MUTED, ls="--",
                label="sans crantage (g θ0 τ)")
        ax.axhline(0.3, color=INK2, ls=":", lw=0.8)
        ax.axvline(r["depinning_urad"], color=INK2, lw=0.8)
        ax.set_yscale("log")
        ax.set_ylim(1e-4, 50)
        ax.set_xlabel("pente résiduelle uniforme θ0 (µrad)")
        ax.set_title(f"{r['mass_g']:g} g — τ = {r['tau_s']:.0f} s, seuil {r['depinning_urad']:.0f} µrad", fontsize=9.5)
    axs[0].set_ylabel("vitesse moyenne de dérive (mm/s)")
    axs[0].legend(fontsize=7.5)
    savefig(fig, "derive_vitesse_vs_pente.png")
    # potentiel + trajectoires
    fig, axs = plt.subplots(1, 3, figsize=(13, 4.2))
    a1, a2 = lattice_vectors(cfg)
    for ax, r in zip(axs, res_m):
        Uf = np.array(r["potential_grid"])
        nf = Uf.shape[0]
        u = np.arange(nf) / nf
        Uu, Vv = np.meshgrid(u, u, indexing="ij")
        X = (Uu[..., None] * a1 + Vv[..., None] * a2) * 1e3
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                off = (di * a1 + dj * a2) * 1e3
                ax.pcolormesh(X[..., 0] + off[0], X[..., 1] + off[1], (Uf - Uf.min()) * 1e6 * G,
                              cmap=seq_cmap(), shading="auto", vmin=0,
                              vmax=(Uf.max() - Uf.min()) * 1e6 * G)
        for key, col in (("trap_v1", SERIES[1]), ("trap_v10", SERIES[3]), ("drift_th40", SERIES[7])):
            tr = np.array(r["illustr"][key])
            for j in range(min(2, tr.shape[1])):
                ax.plot(tr[:, j, 0], tr[:, j, 1], color=col, lw=0.9)
        ax.set_aspect("equal")
        ax.set_xlim(-8, 12)
        ax.set_ylim(-8, 12)
        ax.set_xlabel("x (mm)")
        ax.set_title(f"{r['mass_g']:g} g : potentiel g·U (µJ/kg), barrière {r['barrier_equiv_height_um']*G:.2f} µJ/kg",
                     fontsize=8.5)
    axs[0].set_ylabel("y (mm)")
    savefig(fig, "derive_potentiel_trajectoires.png")
    # mitigation
    fig, ax = plt.subplots(figsize=(8, 4))
    y = np.arange(len(mit))
    ax.barh(y + 0.2, [x["peak_urad"] for x in mit], height=0.38, color=SERIES[1], label="crête")
    ax.barh(y - 0.2, [x["rms_urad"] for x in mit], height=0.38, color=SERIES[0], label="RMS")
    ax.axvline(50, color=INK2, ls="--", lw=0.8)
    ax.set_yticks(y, [x["case"] for x in mit], fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("pente équivalente de crantage, 10 g (µrad)")
    ax.set_title("Mitigation passive du crantage (palet de 10 g)")
    ax.legend(fontsize=8)
    savefig(fig, "derive_mitigation_10g.png")

    for r in res_m:
        print(f"{r['mass_g']} g h={r['h_um']:.0f} τ={r['tau_s']:.0f} s modes={r['n_modes']} "
              f"conservatif {r['helmholtz']['frac_conservative']:.2f} solénoïdal {r['helmholtz']['frac_solenoidal']:.2f} "
              f"RMS {r['slope_rms_urad']:.1f} max {r['slope_max_urad']:.1f} barrière→v_trap {r['v_trap_mm_s']:.2f} mm/s "
              f"seuil {r['depinning_urad_by_angle']} F_dep {r['depinning_force_uN']:.2f} µN")
        for x in r["runs"]:
            if x["angle_deg"] == 0.0:
                print(f"   θ0={x['theta0_urad']:4.0f} v0={x['v0_mm_s']:4.1f} piégé {x['trapped_fraction']:.2f} "
                      f"v={x['v_drift_mean_mm_s']:.3f} (libre {x['v_drift_free_mm_s']:.2f}) mm/s exc méd "
                      f"{x['excursion_median_mm']:.2f} max {x['excursion_max_mm']:.1f} mm t_stab {x['settle_time_median_s']:.0f} s")
        print("   bruit", r["noise"])
    for x in mit:
        print(f"mitig {x['case']:22s} RMS {x['rms_urad']:.1f} crête {x['peak_urad']:.1f} ps {x['ps_Pa']:.0f}")
    print(f"Terminé en {time.time()-t0:.0f} s")


if __name__ == "__main__":
    main()
