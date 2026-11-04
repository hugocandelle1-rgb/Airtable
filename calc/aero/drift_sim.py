"""Dérive passive d'un palet libre dans le champ de crantage (fonctionnement sans compensation).

Équation du mouvement plan (palet non piloté, actionneurs arrêtés) :

    m ẍ = m g [ s(x) + θ0 ê ] − c ẋ + F_b(t) ,    c = μ A / h(m) (Couette),  τ = m/c

- s(x) : pente équivalente de crantage (`trap.build_field` / `trap.Field` : carte
  pré-calculée sur la cellule, périodisée par Fourier, interpolée bilinéairement) ;
- θ0 : pente résiduelle uniforme (réglage + planéité + balourd), direction ê ;
- F_b : force aléatoire (courants d'air résiduels), Ornstein-Uhlenbeck, σ_F, t_c.

Grandeurs calculées pour chaque masse (configuration de `recommended_config()`) :
1. seuil de **maintien** statique θ_hold (palet posé au fond d'un puits, pente
   appliquée lentement ; pire direction) — `trap.static_threshold` ;
2. puits : barrière, vitesse de capture v_cap = √(2 g ΔU), période et facteur de
   qualité des oscillations (Q = ω τ), temps d'amortissement 2τ ;
3. **capture d'un palet en mouvement** (actionneurs coupés à la vitesse v0, départ
   au fond d'un puits, 6 directions) : fraction capturée, distance parcourue,
   vitesse de dérive à long terme vs θ0 ; seuil de re-capture θ_cap(v0) (≥ 90 % des palets immobiles sur le dernier tiers) ;
4. robustesse au bruit de force (σ_F = 0,1 µN ≈ courant d'air de 17 mm/s).

Écrit results/drift_sim.json et 2 figures.
Lancement : ``python3 -m calc.aero.drift_sim`` (≈ 1 min).
"""
from __future__ import annotations

import os
import time
from multiprocessing import Pool

import numpy as np

from calc.aero.common import (G, recommended_config, h_target_for, setup_style, savefig, save_json,
                              seq_cmap, SERIES, INK, INK2, MUTED)
from calc.aero import trap as T

MASSES = (2.0, 5.0, 10.0)
THETA0_URAD = (0.0, 1.0, 2.0, 3.0, 5.0, 7.5, 10.0, 15.0, 20.0, 30.0)
V0_MM_S = (0.3, 1.0, 3.0, 10.0)
N_DIR = 6
N_REP = 3
DT = 0.02
SIGMA_F_N = 0.1e-6          # force aléatoire RMS (≈ ½ρC_d D H v², v ≈ 17 mm/s)
TC_NOISE_S = 2.0


def simulate(fld, tau, theta_vec, X0, V0, T, m_kg=None, noise=None, rng=None, rec_every=50):
    """Verlet semi-implicite amorti, vectorisé sur l'ensemble des palets."""
    X, V = X0.copy(), V0.copy()
    nst = int(T / DT)
    traj = [X.copy()]
    eta = np.zeros_like(X)
    for k in range(nst):
        a = G * (fld(X) + theta_vec) - V / tau
        if noise is not None:
            sigF, tc = noise
            eta += -eta * DT / tc + sigF * np.sqrt(2 * DT / tc) * rng.standard_normal(X.shape)
            a += eta / m_kg
        V += DT * a
        X += DT * V
        if (k + 1) % rec_every == 0:
            traj.append(X.copy())
    return np.array(traj), V


def capture_study(fld, m, h, pitch, theta0_urad=THETA0_URAD, v0_mm_s=V0_MM_S, n_dir=N_DIR,
                  n_rep=N_REP, seed=0, T=None):
    """Palets lâchés au fond d'un puits avec la vitesse v0 sous la pente θ0."""
    rng = np.random.default_rng(seed)
    tau = m * 1e-3 * h / (T_MU_A())
    T = T or max(6 * tau, 120.0)
    i, j = min(fld.minima(), key=lambda ij: fld.Uf[ij])
    xmin = (i / fld.nf) * fld.a1 + (j / fld.nf) * fld.a2
    combos = [(th, v0, d) for th in theta0_urad for v0 in v0_mm_s for d in range(n_dir)]
    N = len(combos) * n_rep
    th = np.repeat([c[0] for c in combos], n_rep) * 1e-6
    v0 = np.repeat([c[1] for c in combos], n_rep) * 1e-3
    ang = np.repeat([c[2] for c in combos], n_rep) * (2 * np.pi / n_dir) + rng.random(N) * 0.2
    e = np.stack([np.cos(ang), np.sin(ang)], 1)
    phi = rng.random(N) * 2 * np.pi
    V0 = v0[:, None] * np.stack([np.cos(phi), np.sin(phi)], 1)
    X0 = np.tile(xmin, (N, 1))
    traj, Vend = simulate(fld, tau, th[:, None] * e, X0, V0, T)
    tt = np.arange(len(traj)) * DT * 50
    half = (2 * len(traj)) // 3
    disp = traj[-1] - traj[half]
    captured = np.hypot(*disp.T) < 0.5 * pitch           # immobile (dans un puits) sur le dernier tiers
    vdr = np.sum(disp * e, 1) / (tt[-1] - tt[half])
    # distance parcourue jusqu'à la position finale (palets capturés)
    dist = np.hypot(*(traj[-1] - traj[0]).T)
    rows = []
    for thc in theta0_urad:
        for v0c in v0_mm_s:
            sel = np.isclose(th, thc * 1e-6) & np.isclose(v0, v0c * 1e-3)
            rows.append(dict(theta0_urad=thc, v0_mm_s=v0c, captured_fraction=float(captured[sel].mean()),
                             v_drift_mm_s=float(np.mean(vdr[sel]) * 1e3),
                             v_drift_free_mm_s=G * thc * 1e-6 * tau * 1e3,
                             distance_median_mm=float(np.median(dist[sel]) * 1e3),
                             distance_max_mm=float(np.max(dist[sel]) * 1e3)))
    thr = {}
    for v0c in v0_mm_s:
        ok = [r["theta0_urad"] for r in rows if r["v0_mm_s"] == v0c and r["captured_fraction"] >= 0.9]
        bad = [r["theta0_urad"] for r in rows if r["v0_mm_s"] == v0c and r["captured_fraction"] < 0.9]
        thr[str(v0c)] = float(max([t for t in ok if not bad or t < min(bad)], default=0.0))
    return dict(tau_s=tau, T_s=T, rows=rows, theta_capture_urad_by_v0=thr)


def T_MU_A():
    from calc.aero.common import MU, A_PUCK
    return MU * A_PUCK


def noise_study(fld, m, h, theta_hold_urad, seed=1):
    rng = np.random.default_rng(seed)
    tau = m * 1e-3 * h / T_MU_A()
    i, j = min(fld.minima(), key=lambda ij: fld.Uf[ij])
    xmin = (i / fld.nf) * fld.a1 + (j / fld.nf) * fld.a2
    out = {}
    for frac in (0.0, 0.5):
        N = 48
        ang = rng.random(N) * 2 * np.pi
        e = np.stack([np.cos(ang), np.sin(ang)], 1)
        th = frac * theta_hold_urad * 1e-6
        tr, _ = simulate(fld, tau, th * e, np.tile(xmin, (N, 1)), np.zeros((N, 2)), max(6 * tau, 120.0),
                         m_kg=m * 1e-3, noise=(SIGMA_F_N, TC_NOISE_S), rng=rng)
        d = tr[-1] - tr[0]
        out[f"theta0={frac:.1f}·θ_hold"] = dict(
            theta0_urad=th * 1e6, kept_fraction=float(np.mean(np.hypot(*d.T) < 0.5 * fld_pitch(fld))),
            wander_rms_um=float(np.sqrt(np.mean(np.sum((tr - tr[0]) ** 2, 2))) * 1e6))
    return out


def fld_pitch(fld):
    return float(np.hypot(*fld.a1))


def _mass_job(args):
    cfg, m = args
    h = h_target_for(m)
    fd = T.build_field(cfg, m, h)
    fld = T.Field(fd)
    st = T.static_threshold(fld, cfg.pitch)
    wp = T.well_properties(fld, m, h)
    cap = capture_study(fld, m, h, cfg.pitch, seed=int(10 * m))
    nz = noise_study(fld, m, h, st["theta_dep_urad"])
    return dict(mass_g=m, h_um=h * 1e6, ps_Pa=fd["ps"], field=fld.stats(), hold=st, well=wp,
                capture=cap, noise=nz, F_hold_uN=st["theta_dep_urad"] * 1e-6 * m * 1e-3 * G * 1e6,
                potential=fld.Uf.tolist(), a1=fld.a1.tolist(), a2=fld.a2.tolist())


def main():
    t0 = time.time()
    cfg = recommended_config()
    with Pool(min(4, os.cpu_count() or 1)) as pool:
        res_m = pool.map(_mass_job, [(cfg, m) for m in MASSES])
    res = dict(config=cfg, dt_s=DT, sigma_F_N=SIGMA_F_N, tc_noise_s=TC_NOISE_S, masses=res_m,
               runtime_s=time.time() - t0)
    save_json("drift_sim.json", res)

    plt = setup_style()
    fig, axs = plt.subplots(1, 3, figsize=(13, 4.0), sharey=True)
    for ax, r in zip(axs, res_m):
        for v0c, col in zip(V0_MM_S, SERIES):
            rr = [x for x in r["capture"]["rows"] if x["v0_mm_s"] == v0c]
            ax.plot([x["theta0_urad"] for x in rr], np.maximum([x["v_drift_mm_s"] for x in rr], 1e-4), "-o",
                    ms=3.5, color=col, label=f"lâché à {v0c:g} mm/s")
        ths = np.array(THETA0_URAD)
        ax.plot(ths, np.maximum(G * ths * 1e-6 * r["capture"]["tau_s"] * 1e3, 1e-4), color=MUTED, ls="--",
                label="sans crantage (g θ0 τ)")
        ax.axhline(0.3, color=INK2, ls=":", lw=0.8)
        ax.axvline(r["hold"]["theta_dep_urad"], color=INK2, lw=0.8)
        ax.set_yscale("log")
        ax.set_ylim(1e-4, 30)
        ax.set_xlabel("pente résiduelle uniforme θ0 (µrad)")
        ax.set_title(f"{r['mass_g']:g} g — τ = {r['capture']['tau_s']:.0f} s ; maintien statique "
                     f"{r['hold']['theta_dep_urad']:.0f} µrad", fontsize=9)
    axs[0].set_ylabel("vitesse moyenne de dérive à long terme (mm/s)")
    axs[0].legend(fontsize=7.5)
    savefig(fig, "derive_vitesse_vs_pente.png")

    fig, axs = plt.subplots(1, 3, figsize=(13, 4.2))
    for ax, r in zip(axs, res_m):
        Uf = np.array(r["potential"])
        nf = Uf.shape[0]
        a1, a2 = np.array(r["a1"]), np.array(r["a2"])
        u = np.arange(nf) / nf
        Uu, Vv = np.meshgrid(u, u, indexing="ij")
        X = (Uu[..., None] * a1 + Vv[..., None] * a2) * 1e3
        vmax = (Uf.max() - Uf.min()) * G * 1e6
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                off = (di * a1 + dj * a2) * 1e3
                pc = ax.pcolormesh(X[..., 0] + off[0], X[..., 1] + off[1], (Uf - Uf.min()) * G * 1e6,
                                   cmap=seq_cmap(), shading="auto", vmin=0, vmax=vmax)
        ax.set_aspect("equal")
        ax.set_xlim(-6, 9)
        ax.set_ylim(-6, 9)
        ax.set_xlabel("x (mm)")
        ax.set_title(f"{r['mass_g']:g} g : potentiel (µJ/kg), barrière {r['well']['barrier_J_per_kg']*1e6:.2f}, "
                     f"v_cap {r['well']['v_capture_mm_s']:.2f} mm/s", fontsize=8.5)
        fig.colorbar(pc, ax=ax, shrink=0.8)
    axs[0].set_ylabel("y (mm)")
    savefig(fig, "derive_potentiel.png")

    for r in res_m:
        w, h_ = r["well"], r["hold"]
        print(f"{r['mass_g']:4.1f} g h={r['h_um']:.0f} µm : maintien statique {h_['theta_dep_urad']:.1f} µrad "
              f"(meilleure dir. {h_['theta_dep_best_dir_urad']:.1f}) F={r['F_hold_uN']:.2f} µN ; conservatif "
              f"{r['field']['frac_conservative']:.2f} ; barrière {w['barrier_J_per_kg']*1e6:.2f} µJ/kg "
              f"v_cap {w['v_capture_mm_s']:.2f} mm/s ; T {w['period_s']:.1f} s Q {w['Q_factor']:.0f} τ {w['tau_s']:.0f} s")
        print("     capture θ0 max (≥ 90 %) par v0 :", r["capture"]["theta_capture_urad_by_v0"])
        print("     bruit :", r["noise"])
    print(f"Terminé en {time.time()-t0:.0f} s")


if __name__ == "__main__":
    main()
