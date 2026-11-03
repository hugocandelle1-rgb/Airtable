"""Monte-Carlo : dispersion de fabrication des orifices → efforts parasites aléatoires.

Chaque trou i reçoit un diamètre d_i = d0 + N(0, σ_d) (σ_d = tolérance/3) et une
longueur L_i = L0 + N(0, σ_L) (voile ±0,05 mm à 3σ). Son débit est mis à
l'échelle s_i = (d_i/d0)^a·(L_i/L0)^b, exposants locaux de la loi d'orifice
évalués à Δp = ps/2 (le trou couvert travaille sous ≈ ps − p̄). Le film est résolu
par le modèle discret (`film.green_solve(..., scale=s)`) ; on retranche la
solution nominale à la même position pour isoler la part aléatoire :

* dispersion de portance → Δh = ΔW/k_z ;
* moment parasite → basculement θ = M/k_θ → pente équivalente ½θ ;
* poussée de quantité de mouvement du film (débit au bord modifié).

S'y ajoutent : décalage systématique du diamètre (foret hors cote sur tout le
lot) → décalage d'entrefer ; trou bouché à 25 % (bavure) ou à 100 % (poussière)
sous le palet → effort localisé (justifie l'ébavurage et la filtration).

Écrit results/montecarlo.json et une figure.
Lancement : ``python3 -m calc.aero.montecarlo`` (≈ 30 s).
"""
from __future__ import annotations

import os
import time
from multiprocessing import Pool

import numpy as np

from calc.aero.common import (G, R_PUCK, recommended_config, h_target_for, lattice_vectors,
                              setup_style, savefig, save_json, SERIES, INK2, MUTED)
from calc.aero import film as F
from calc.aero.optimize import ps_for
from calc.aero.orifice import q_free

MASSES = (2.0, 5.0, 10.0)
TOLS_MM = (0.005, 0.010, 0.015, 0.020)      # tolérance ± sur d (3σ)
TOL_L_MM = 0.05                              # tolérance ± sur L (3σ)
N_REAL = 300
ALLOC_URAD = 10.0                            # allocation suggérée au budget (RMS)


def exponents(cfg, dp):
    """Exposants a = dln q/dln d, b = dln q/dln L à Δp donné."""
    e = 1e-3
    q0 = float(q_free(dp, cfg))
    a = np.log(float(q_free(dp, cfg.with_(d=cfg.d * (1 + e)))) / q0) / np.log(1 + e)
    b = np.log(float(q_free(dp, cfg.with_(L=cfg.L * (1 + e)))) / q0) / np.log(1 + e)
    return a, b


def slope_of(sol, cfg, h, kth, W):
    """Pente équivalente (vecteur, rad) : basculement −½·M/k_θ + quantité de mouvement."""
    return -0.5 * sol["M"] / kth + F.momentum_force(sol, h, cfg) / W


def _job(args):
    cfg, m, tol_mm, seed = args
    rng = np.random.default_rng(seed)
    h = h_target_for(m)
    ps = ps_for(cfg, m, h)
    kth = F.axi_ktheta(cfg, ps, h)
    kz = F.axi_kz(cfg, ps, h)
    a, b = exponents(cfg, 0.5 * ps)
    W0 = m * 1e-3 * G
    a1, a2 = lattice_vectors(cfg)
    dW, dS = [], []
    for k in range(N_REAL):
        c = rng.random() * a1 + rng.random() * a2
        xy = F.covered_holes(cfg, c)
        nom = F.green_solve(cfg, ps, h, xy=xy)
        d = cfg.d + rng.normal(0, tol_mm * 1e-3 / 3, len(xy))
        L = cfg.L + rng.normal(0, TOL_L_MM * 1e-3 / 3, len(xy))
        s = (d / cfg.d) ** a * (L / cfg.L) ** b
        rnd = F.green_solve(cfg, ps, h, xy=xy, scale=s, q0=nom["q"])
        dW.append(rnd["W"] - nom["W"])
        dS.append(slope_of(rnd, cfg, h, kth, W0) - slope_of(nom, cfg, h, kth, W0))
    dW = np.array(dW)
    dS = np.array(dS) * 1e6
    mag = np.hypot(dS[:, 0], dS[:, 1])
    return dict(mass_g=m, tol_mm=tol_mm, h_um=h * 1e6, ps=ps, exp_d=a, exp_L=b,
                dh_rms_um=float(np.std(dW) / kz * 1e6),
                slope_rms_urad=float(np.sqrt(np.mean(mag**2))),
                slope_p95_urad=float(np.percentile(mag, 95)),
                slope_max_urad=float(mag.max()))


def _blocked_job(args):
    """Trou partiellement/totalement bouché sous le palet : pente maximale selon sa position."""
    cfg, m, frac = args
    h = h_target_for(m)
    ps = ps_for(cfg, m, h)
    kth = F.axi_ktheta(cfg, ps, h)
    kz = F.axi_kz(cfg, ps, h)
    W0 = m * 1e-3 * G
    xy = F.covered_holes(cfg, (0.0, 0.0))
    nom = F.green_solve(cfg, ps, h, xy=xy)
    rho = np.hypot(xy[:, 0], xy[:, 1])
    out = []
    for i in np.argsort(rho):
        s = np.ones(len(xy))
        s[i] = max(1.0 - frac, 1e-6)
        r = F.green_solve(cfg, ps, h, xy=xy, scale=s, q0=nom["q"])
        dsl = (slope_of(r, cfg, h, kth, W0) - slope_of(nom, cfg, h, kth, W0)) * 1e6
        out.append((rho[i] * 1e3, float(np.hypot(*dsl)), float((r["W"] - nom["W"]) / kz * 1e6)))
    out = np.array(out)
    return dict(mass_g=m, blocked_fraction=frac, rho_mm=out[:, 0].tolist(), slope_urad=out[:, 1].tolist(),
                dh_um=out[:, 2].tolist(), slope_max_urad=float(out[:, 1].max()),
                dh_min_um=float(out[:, 2].min()))


def main():
    t0 = time.time()
    cfg = recommended_config()
    jobs = [(cfg, m, t, 1000 + 17 * k) for k, (m, t) in enumerate((m, t) for m in MASSES for t in TOLS_MM)]
    with Pool(min(4, os.cpu_count() or 1)) as pool:
        mc = pool.map(_job, jobs, chunksize=1)
        bl = pool.map(_blocked_job, [(cfg, m, f) for m in MASSES for f in (0.25, 1.0)])
    # tolérance recommandée : la plus large telle que la pente RMS ≤ allocation pour toutes les masses
    ok = [t for t in TOLS_MM if all(r["slope_rms_urad"] <= ALLOC_URAD for r in mc if r["tol_mm"] == t)]
    tol_rec = max(ok) if ok else min(TOLS_MM)
    # décalage systématique du lot (tout le perçage à d0 ± 0,01 mm)
    sysd = {}
    for m in MASSES:
        h = h_target_for(m)
        ps = ps_for(cfg, m, h)
        sysd[str(m)] = {f"{dd:+.3f}": F.axi_solve_h(cfg.with_(d=cfg.d + dd * 1e-3), ps, m * 1e-3) * 1e6
                        for dd in (-0.01, 0.0, 0.01)}
    res = dict(config=cfg, n_real=N_REAL, tol_L_mm=TOL_L_MM, allocation_urad=ALLOC_URAD,
               results=mc, recommended_tol_mm=tol_rec, systematic_d_shift_h_um=sysd, blocked=bl,
               runtime_s=time.time() - t0)
    save_json("montecarlo.json", res)

    plt = setup_style()
    fig, axs = plt.subplots(1, 2, figsize=(11, 4.2))
    for m, col in zip(MASSES, SERIES):
        rr = [r for r in mc if r["mass_g"] == m]
        axs[0].plot([r["tol_mm"] * 1e3 for r in rr], [r["slope_rms_urad"] for r in rr], "-o", color=col,
                    ms=4, label=f"{m:g} g — RMS")
        axs[0].plot([r["tol_mm"] * 1e3 for r in rr], [r["slope_p95_urad"] for r in rr], "--", color=col,
                    lw=1.2, label=f"{m:g} g — 95 %")
    axs[0].axhline(ALLOC_URAD, color=INK2, ls=":", lw=0.8)
    axs[0].set_xlabel("tolérance ± sur le diamètre d'orifice (µm, 3σ)")
    axs[0].set_ylabel("pente équivalente aléatoire (µrad)")
    axs[0].set_title(f"Dispersion de fabrication des orifices (L ± {TOL_L_MM:.2f} mm)")
    axs[0].legend(fontsize=7.5, ncol=2)
    for m, col in zip(MASSES, SERIES):
        b = next(r for r in bl if r["mass_g"] == m and r["blocked_fraction"] == 1.0)
        axs[1].scatter(b["rho_mm"], b["slope_urad"], s=10, color=col, label=f"{m:g} g, trou bouché")
    axs[1].axhline(50, color=INK2, ls="--", lw=0.8)
    axs[1].set_xlabel("distance du trou bouché au centre du palet (mm)")
    axs[1].set_ylabel("pente équivalente (µrad)")
    axs[1].set_yscale("log")
    axs[1].set_title("Trou bouché sous le palet")
    axs[1].legend(fontsize=8)
    savefig(fig, "montecarlo_dispersion.png")
    for r in mc:
        print(f"{r['mass_g']:4.1f} g tol ±{r['tol_mm']*1e3:.0f} µm : pente RMS {r['slope_rms_urad']:.1f} "
              f"p95 {r['slope_p95_urad']:.1f} max {r['slope_max_urad']:.1f} µrad ; Δh RMS {r['dh_rms_um']:.2f} µm "
              f"(a={r['exp_d']:.2f}, b={r['exp_L']:.2f})")
    for b in bl:
        print(f"bouché {b['blocked_fraction']:.0%} {b['mass_g']} g : pente max {b['slope_max_urad']:.0f} µrad, "
              f"Δh min {b['dh_min_um']:.1f} µm")
    print("tolérance recommandée ±", tol_rec, "mm ; décalage systématique", sysd)
    print(f"Terminé en {time.time()-t0:.0f} s")


if __name__ == "__main__":
    main()
