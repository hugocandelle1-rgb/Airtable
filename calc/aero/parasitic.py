"""Forces parasites dans le plan exprimées comme ERREUR DE MESURE (table de caractérisation).

Contexte : les palets portent des actionneurs électrostatiques radiaux ; la table sert
à caractériser le mouvement produit par une force d'actionnement F_act. Toute force
dans le plan qui dépend de la position (crantage, poussée de bord, pente) ou du temps
(courants d'air) est une erreur de mesure.

1. Bilan des forces parasites par masse (crête / RMS en µN, accélération en mm/s²) :
   crantage (basculement + quantité de mouvement du film, carte `trap.Field`), jets de
   bord (ordre de grandeur), pente résiduelle de la plaque, dispersion des orifices
   (`montecarlo.json`), courants d'air résiduels, balourd du palet.
2. Erreur de trajectoire sur une fenêtre de mesure T ∈ {1, 5, 10, 30} s, pour une force
   d'actionnement constante F_act (0,1 µN … 1 mN), départ au repos en position aléatoire :
       m ẍ = F_act ê + m g [s(x) + θ_s] − c ẋ
   comparée à la trajectoire idéale x_id(t) = (F_act/c)(t − τ(1 − e^{−t/τ})) ê.
   Fenêtre tronquée quand le palet sort de la zone de travail (300 mm).
   Cas : crantage seul ; pente seule ; crantage + pente.
3. Correction a posteriori par une carte de forces étalonnée (post-traitement des
   trajectoires mesurées, pas de pilotage) : résidu du crantage pour une carte décalée
   (recalage du réseau δ = 0,05 / 0,1 / 0,2 mm) et d'amplitude erronée (±10 %), plus
   les termes non cartographiables (dispersion des orifices, courants d'air).
4. Leviers de réduction (crantage à 10 g) : entrefer, Ø d'orifice, pas.

Écrit results/parasitic.json et 2 figures.
Lancement : ``python3 -m calc.aero.parasitic`` (≈ 1–2 min).
"""
from __future__ import annotations

import os
import time
from multiprocessing import Pool

import numpy as np

from calc.aero.common import (G, MU, A_PUCK, WORK_SQUARE, recommended_config, h_target_for,
                              load_json, setup_style, savefig, save_json, SERIES, INK2, MUTED)
from calc.aero import trap as T
from calc.aero.optimize import crant

MASSES = (2.0, 5.0, 10.0)
F_ACT_N = tuple(np.logspace(-7, -3, 9))          # 0,1 µN … 1 mN
WINDOWS_S = (1.0, 5.0, 10.0, 30.0)
THETA_S_URAD = (10.0, 30.0)                       # pente résiduelle de plaque (optimiste / budget structure)
N_ENS = 48
F_AIR_N = 0.1e-6                                  # courant d'air résiduel ≈ 17 mm/s sous écran
UNBALANCE_UM = 5.0                                # décentrage du centre de gravité du palet
TRAVEL_MAX = WORK_SQUARE                          # 300 mm


def ideal(F, m, tau, t):
    return F / (m / tau) * (t - tau * (1 - np.exp(-t / tau)))


def traj_error(fld, m_g, h, F, theta_s, rng, with_cog=True, n=N_ENS):
    """Erreur de position |x(T) − x_id(T)| (m) aux fenêtres WINDOWS_S, ensemble aléatoire."""
    m = m_g * 1e-3
    tau = m * h / (MU * A_PUCK)
    a_act = F / m
    vmax = min(a_act * tau, np.sqrt(2 * a_act * TRAVEL_MAX))
    p = float(np.hypot(*fld.a1))
    dt = min(0.02, 0.05 * p / max(vmax, 1e-9))
    # instant de sortie de la zone (trajectoire idéale)
    tt = np.linspace(0, max(WINDOWS_S), 3000)
    xi = ideal(F, m, tau, tt)
    t_exit = tt[np.argmax(xi > TRAVEL_MAX)] if np.any(xi > TRAVEL_MAX) else np.inf
    t_end = min(max(WINDOWS_S), t_exit)
    ang = rng.random(n) * 2 * np.pi
    e = np.stack([np.cos(ang), np.sin(ang)], 1)
    angs = rng.random(n) * 2 * np.pi
    es = np.stack([np.cos(angs), np.sin(angs)], 1) * theta_s * 1e-6
    X = rng.random((n, 1)) * fld.a1 + rng.random((n, 1)) * fld.a2
    X0 = X.copy()
    V = np.zeros_like(X)
    out = {}
    t = 0.0
    targets = [w for w in WINDOWS_S if w <= t_end + 1e-9]
    k = 0
    while k < len(targets):
        s = fld(X) if with_cog else 0.0
        acc = a_act * e + G * (s + es) - V / tau
        V += dt * acc
        X += dt * V
        t += dt
        if t >= targets[k] - 1e-12:
            err = (X - X0) - ideal(F, m, tau, t) * e
            d = np.hypot(*err.T)
            out[str(targets[k])] = dict(rms_um=float(np.sqrt(np.mean(d**2)) * 1e6),
                                        p95_um=float(np.percentile(d, 95) * 1e6),
                                        travel_mm=float(ideal(F, m, tau, t) * 1e3))
            k += 1
    for w in WINDOWS_S:
        out.setdefault(str(w), None)
    return out, dt


def _mass_job(args):
    cfg, m = args
    rng = np.random.default_rng(int(7 * m))
    h = h_target_for(m)
    fd = T.build_field(cfg, m, h)
    fld = T.Field(fd)
    st = fld.stats()
    W = m * 1e-3 * G
    # carte de crantage avec jets de bord (estimation) : RMS séparé
    c = crant(cfg, h, n=10, masses=(m,))[m]
    # 3. résidu après correction par une carte étalonnée
    nf = fld.nf
    uf = np.arange(nf) / nf
    Uf, Vf = np.meshgrid(uf, uf, indexing="ij")
    Xf = Uf.reshape(-1, 1) * fld.a1 + Vf.reshape(-1, 1) * fld.a2
    S0 = fld(Xf)
    corr = {}
    for dpos in (0.05e-3, 0.1e-3, 0.2e-3):
        for amp in (0.9, 1.0, 1.1):
            res = []
            for a in np.radians(np.arange(0, 360, 30)):
                Sm = amp * fld(Xf + dpos * np.array([np.cos(a), np.sin(a)]))
                res.append(np.mean(np.sum((S0 - Sm) ** 2, 1)))
            corr[f"δ={dpos*1e3:.2f} mm, amplitude ×{amp:.1f}"] = float(np.sqrt(np.max(res)) * 1e6)
    # 2. erreurs de trajectoire
    traj = []
    for F in F_ACT_N:
        for case, th_s, cog in (("crantage", 0.0, True), ("pente 30 µrad", 30.0, False),
                                ("crantage + pente 10 µrad", 10.0, True),
                                ("crantage + pente 30 µrad", 30.0, True)):
            r, dt = traj_error(fld, m, h, F, th_s, rng, with_cog=cog)
            traj.append(dict(F_act_N=F, case=case, dt_s=dt, windows=r))
    return dict(mass_g=m, h_um=h * 1e6, ps_Pa=fd["ps"], tau_s=m * 1e-3 * h / (MU * A_PUCK), W_N=W,
                cog_rms_urad=st["rms_urad"], cog_peak_urad=st["peak_urad"],
                cog_with_jets_rms_urad=c["tot"] if False else None,
                jets_rms_urad=c["jet"], frac_conservative=st["frac_conservative"],
                correction_residual_rms_urad=corr, trajectories=traj)


def _lever_job(args):
    cfg, h_um, tag = args
    try:
        c = crant(cfg, h_um * 1e-6, n=12, masses=(10.0,))[10.0]
    except ValueError:
        return dict(case=tag, ok=False)
    return dict(case=tag, ok=True, h_um=h_um, ps_Pa=c["ps"], rms_urad=c["tot"], peak_urad=c["tot_max"],
                tilt_urad=c["tilt"], mom_urad=c["mom"])


def main():
    t0 = time.time()
    cfg = recommended_config()
    levers = [(cfg, 80.0, "retenu hex 5 Ø0,30 L1,2, h 80"), (cfg, 70.0, "h 70 µm (CdC : ≥ 80)"),
              (cfg.with_(d=0.25e-3, L=1.0e-3), 80.0, "Ø0,25 L1,0 hex 5 (usinabilité ?)"),
              (cfg.with_(d=0.25e-3, L=1.0e-3, pitch=4.0e-3), 80.0, "Ø0,25 L1,0 hex 4"),
              (cfg.with_(pitch=2.94e-3, D_cb=1.5e-3), 80.0, "hex 2,94 Ø0,30"),
              (cfg.with_(pitch=3.5e-3), 80.0, "hex 3,5 Ø0,30")]
    with Pool(min(4, os.cpu_count() or 1)) as pool:
        lv = pool.map_async(_lever_job, levers)
        res_m = pool.map(_mass_job, [(cfg, m) for m in MASSES])
        lv = lv.get()
    print(f"calculs ({time.time()-t0:.0f} s)")
    # 1. bilan des forces parasites
    mc = {r["mass_g"]: r for r in load_json("montecarlo.json")["results"]
          if abs(r["tol_mm"] - 0.005) < 1e-9}
    unb = load_json("cogging.json")["unbalance"]
    budget = []
    for r in res_m:
        m = r["mass_g"]
        W = r["W_N"]
        terms = {  # pente équivalente (µrad) : (RMS, crête)
            "crantage (basculement + quantité de mouvement)": (r["cog_rms_urad"], r["cog_peak_urad"]),
            "jets de bord (ordre de grandeur)": (r["jets_rms_urad"], 2.5 * r["jets_rms_urad"]),
            "dispersion des orifices ±0,005 mm": (mc[m]["slope_rms_urad"], mc[m]["slope_p95_urad"]),
            "pente résiduelle de plaque (budget structure)": (30.0 / np.sqrt(2), 30.0),
            "courants d'air résiduels (0,1 µN)": (F_AIR_N / W * 1e6, 2 * F_AIR_N / W * 1e6),
            f"balourd {UNBALANCE_UM:.0f} µm": (UNBALANCE_UM * unb[str(m)]["slope_urad_per_um"],
                                                UNBALANCE_UM * unb[str(m)]["slope_urad_per_um"]),
        }
        rows = []
        for k, (rms, pk) in terms.items():
            rows.append(dict(term=k, rms_urad=rms, peak_urad=pk, rms_uN=rms * 1e-6 * W * 1e6,
                             peak_uN=pk * 1e-6 * W * 1e6, rms_acc_mm_s2=rms * 1e-6 * G * 1e3,
                             peak_acc_mm_s2=pk * 1e-6 * G * 1e3))
        tot_rms = float(np.sqrt(sum(x["rms_urad"] ** 2 for x in rows)))
        tot_pk = float(sum(x["peak_urad"] for x in rows))
        budget.append(dict(mass_g=m, rows=rows, total_rss_rms_urad=tot_rms, total_linear_peak_urad=tot_pk,
                           total_rms_uN=tot_rms * 1e-6 * W * 1e6, total_peak_uN=tot_pk * 1e-6 * W * 1e6,
                           total_rms_acc_mm_s2=tot_rms * 1e-6 * G * 1e3))
    # correction a posteriori : résidu total
    post = []
    for r, b in zip(res_m, budget):
        m = r["mass_g"]
        cogres = r["correction_residual_rms_urad"]["δ=0.10 mm, amplitude ×1.1"]
        unmap = [mc[m]["slope_rms_urad"], F_AIR_N / r["W_N"] * 1e6]
        slope_map_unc = 3.0                       # carte de pente basse fréquence (dérive + ADXL), µrad
        jets_unc = 0.5 * r["jets_rms_urad"]
        rss = float(np.sqrt(cogres**2 + sum(u**2 for u in unmap) + slope_map_unc**2 + jets_unc**2))
        post.append(dict(mass_g=m, cog_residual_urad=cogres, unmappable_urad=unmap,
                         slope_map_uncertainty_urad=slope_map_unc, jets_uncertainty_urad=jets_unc,
                         total_after_correction_rms_urad=rss,
                         total_before_rms_urad=b["total_rss_rms_urad"],
                         gain=b["total_rss_rms_urad"] / rss,
                         total_after_rms_uN=rss * 1e-6 * r["W_N"] * 1e6))
    res = dict(config=cfg, F_act_N=F_ACT_N, windows_s=WINDOWS_S, budget=budget, masses=res_m,
               post_correction=post, levers_10g=lv, runtime_s=time.time() - t0)
    save_json("parasitic.json", res)

    plt = setup_style()
    fig, axs = plt.subplots(1, 3, figsize=(13, 4.2), sharey=True)
    for ax, r in zip(axs, res_m):
        for (case, ls), w, col in [((c, l), w, col) for (c, l) in (("crantage", "-"), ("crantage + pente 30 µrad", "--"))
                                   for w, col in zip(WINDOWS_S, SERIES)]:
            pts = [t for t in r["trajectories"] if t["case"] == case]
            F = [t["F_act_N"] * 1e6 for t in pts if t["windows"][str(w)]]
            rel = [t["windows"][str(w)]["rms_um"] / 1e3 / max(t["windows"][str(w)]["travel_mm"], 1e-9)
                   for t in pts if t["windows"][str(w)]]
            ax.loglog(F, rel, ls, color=col, lw=1.4, label=f"T = {w:g} s" + (" (+ pente)" if ls == "--" else ""))
        ax.set_xlabel("force d'actionnement F_act (µN)")
        ax.set_title(f"{r['mass_g']:g} g — crantage {r['cog_rms_urad']*r['W_N']:.2f} µN RMS", fontsize=9.5)
        ax.axhline(0.01, color=INK2, ls=":", lw=0.8)
    axs[0].set_ylabel("erreur de trajectoire RMS / déplacement")
    axs[0].legend(fontsize=7, ncol=2)
    savefig(fig, "parasite_erreur_trajectoire.png")

    fig, ax = plt.subplots(figsize=(9, 4.4))
    terms = [x["term"] for x in budget[0]["rows"]]
    y = np.arange(len(terms))
    for k, (b, col) in enumerate(zip(budget, SERIES)):
        ax.barh(y + (k - 1) * 0.26, [x["rms_uN"] for x in b["rows"]], height=0.26, color=col,
                label=f"{b['mass_g']:g} g (total RSS {b['total_rms_uN']:.2f} µN)")
    ax.set_yticks(y, terms, fontsize=8)
    ax.invert_yaxis()
    ax.set_xscale("log")
    ax.set_xlabel("force parasite RMS (µN)")
    ax.set_title("Bilan des forces parasites dans le plan")
    ax.legend(fontsize=8)
    savefig(fig, "parasite_bilan.png")

    for b in budget:
        print(f"{b['mass_g']} g : total RSS {b['total_rss_rms_urad']:.1f} µrad = {b['total_rms_uN']:.2f} µN "
              f"({b['total_rms_acc_mm_s2']:.3f} mm/s²) ; crête linéaire {b['total_peak_uN']:.2f} µN")
        for x in b["rows"]:
            print(f"     {x['term']:48s} {x['rms_urad']:6.1f} / {x['peak_urad']:6.1f} µrad  {x['rms_uN']:.3f} µN")
    for p in post:
        print(f"correction {p['mass_g']} g : {p['total_before_rms_urad']:.1f} → {p['total_after_correction_rms_urad']:.1f} "
              f"µrad RMS (crantage résiduel {p['cog_residual_urad']:.1f})")
    for r in res_m:
        print(r["mass_g"], "résidus carte :", {k: round(v, 1) for k, v in r["correction_residual_rms_urad"].items()})
        for t in r["trajectories"]:
            if t["case"] in ("crantage", "crantage + pente 30 µrad"):
                print(f"   F={t['F_act_N']*1e6:9.2f} µN {t['case']:26s}",
                      {w: (round(v['rms_um'], 1), round(v['travel_mm'], 1)) if v else None for w, v in t["windows"].items()})
    for x in lv:
        print("levier", x)
    print(f"Terminé en {time.time()-t0:.0f} s")


if __name__ == "__main__":
    main()
