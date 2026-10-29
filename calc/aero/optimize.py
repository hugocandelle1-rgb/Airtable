"""Optimisation du perçage de la plaque (d, L, pas, maille, entrefer cible).

Étape A — balayage complet (modèle axisymétrique homogénéisé corrigé « puits »,
validé contre le modèle discret à 0,1 % près) : pressions de consigne ps(2 g) et
ps(10 g) à l'entrefer cible, nombre de trous sous le palet, débit total de la
zone percée au point le plus chargé (+10 %), contraintes d'usinabilité.

Étape B — crantage (modèle discret, fonction de Green) des configurations
admissibles : pente équivalente RMS = basculement + quantité de mouvement du
film, pour 2, 5 et 10 g, sur la cellule primitive du réseau.

Étape C — affinage autour du meilleur candidat (pas ±0,1 mm), robustesse au
diamètre du palet (±0,2 mm), au modèle de bord, à la régularisation du terme de
quantité de mouvement et choix de l'entrefer cible.

Critère : minimiser J = max_m(pente RMS) sous contraintes ; départage par le
débit total puis le nombre de trous.

Écrit results/optimization.json et results/recommended_hole.json.
Lancement : ``python3 -m calc.aero.optimize`` (≈ 3–4 min sur 4 cœurs).
"""
from __future__ import annotations

import os
import time
from multiprocessing import Pool

import numpy as np
from scipy.optimize import brentq

from calc.aero.common import (G, P, PERF_SQUARE, baseline_config, count_holes_square_zone,
                              unit_cell_positions, setup_style, savefig, save_json,
                              SERIES, INK2, MUTED, HoleConfig, R_PUCK)
from calc.aero import film as F
from calc.aero.orifice import q_free

PS_MAX = P["operating"]["p_plenum_max_Pa"]       # 400 Pa
PS_MIN = P["operating"]["p_plenum_min_Pa"]       # 30 Pa
N_MIN = 30
D_MIN, WEB_MIN, LD_MAX = 0.30e-3, 0.80e-3, 4.0
MASSES = (2.0, 5.0, 10.0)


def ps_for(cfg, m_g, h):
    return brentq(lambda p: F.axi_W(cfg, p, h) - m_g * 1e-3 * G, 3.0, 30000.0, rtol=1e-6)


def stage_a(args):
    cfg, h = args
    try:
        p2 = ps_for(cfg, 2.0, h)
        p10 = ps_for(cfg, 10.0, h)
    except ValueError:
        return None
    nh = [len(F.covered_holes(cfg, c, rim="abrupt")) for c in unit_cell_positions(cfg, 6)]
    ntot = count_holes_square_zone(cfg)
    qmax = ntot * float(q_free(1.1 * p10, cfg))
    return dict(cfg=cfg, h=h, ps2=p2, ps10=p10, n_under_min=min(nh), n_under_max=max(nh),
                n_total=ntot, Q_max_m3h=qmax * 3600, Q_min_m3h=ntot * float(q_free(0.9 * p2, cfg)) * 3600)


def crant(cfg, h, n=8, R=R_PUCK, rim=None, masses=MASSES):
    out = {}
    for m in masses:
        ps = ps_for(cfg, m, h)
        kth = F.axi_ktheta(cfg, ps, h)
        kz = F.axi_kz(cfg, ps, h)
        st = F.cogging_stats(cfg, ps, h, kth, kz, n=n, R=R, rim=rim, momentum=True)
        out[m] = dict(ps=ps, kth=kth, kz=kz, tilt=st["slope_tilt_rms"] * 1e6,
                      mom=st["Fmom_rms_over_W"] * 1e6, tot=st["slope_rms"] * 1e6,
                      tot_max=st["slope_max"] * 1e6, jet=st["Fjet_rms_over_W"] * 1e6,
                      dh_pp_um=st["dh_pp"] * 1e6, W_ripple_pp=st["W_ripple_pp"])
    return out


def stage_b(args):
    r, n = args
    c = crant(r["cfg"], r["h"], n=n)
    r = dict(r)
    r["crant"] = c
    r["J"] = max(v["tot"] for v in c.values())
    return r


def _feasible(r):
    cfg = r["cfg"]
    return (r["n_under_min"] >= N_MIN and r["ps10"] <= PS_MAX and 0.9 * r["ps2"] >= PS_MIN)


def main():
    t0 = time.time()
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    base = baseline_config()
    hex_magic = [p for p in F.magic_pitches("hex") * 1e3 if 2.7 < p < 5.3]
    sq_magic = [p for p in F.magic_pitches("square") * 1e3 if 2.7 < p < 5.0]
    grid = []
    for d in (0.30, 0.35, 0.40, 0.45, 0.50):
        for L in (0.8, 1.0, 1.2, 1.4, 1.6, 2.0):
            if L / d > LD_MAX + 1e-9 or L < WEB_MIN * 1e3 - 1e-9 or d < D_MIN * 1e3 - 1e-9:
                continue
            for pat, mags in (("hex", hex_magic), ("square", sq_magic)):
                pitches = sorted(set([3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0] + [round(p, 3) for p in mags]))
                for p in pitches:
                    for h in (100e-6, 120e-6):
                        grid.append((base.with_(d=d * 1e-3, L=L * 1e-3, pitch=p * 1e-3,
                                                pattern=pat), h))
    print(f"Étape A : {len(grid)} configurations")
    with Pool(min(4, os.cpu_count() or 1)) as pool:
        A = [r for r in pool.map(stage_a, grid, chunksize=8) if r is not None]
        feas = [r for r in A if _feasible(r)]
        # crantage : on se limite aux d ≤ 0,40 mm (les plus gros sont dominés, cf. note)
        cand = [r for r in feas if r["cfg"].d <= 0.40e-3 + 1e-9]
        print(f"  admissibles : {len(feas)} ; étape B sur {len(cand)}  ({time.time()-t0:.0f} s)")
        B = pool.map(stage_b, [(r, 7) for r in cand], chunksize=4)
    B.sort(key=lambda r: r["J"])
    Jmin = B[0]["J"]
    # départage : parmi J ≤ 1,1·Jmin, le plus faible débit, puis le moins de trous
    short = [r for r in B if r["J"] <= 1.10 * Jmin]
    short.sort(key=lambda r: (round(r["Q_max_m3h"], 0), r["n_total"]))
    best = short[0]
    print(f"  meilleur (étape B) : {best['cfg'].label()} h={best['h']*1e6:.0f} J={best['J']:.1f} "
          f"Q={best['Q_max_m3h']:.1f} m3/h  ({time.time()-t0:.0f} s)")

    # --- Étape C : affinage du pas et robustesse
    cb = best["cfg"]
    pitches = np.round(cb.pitch * 1e3 + np.arange(-0.10, 0.101, 0.02), 3)
    jobsC = [(cb.with_(pitch=p * 1e-3), best["h"]) for p in pitches]
    with Pool(min(4, os.cpu_count() or 1)) as pool:
        AC = pool.map(stage_a, jobsC)
        BC = pool.map(stage_b, [(r, 10) for r in AC if r is not None])
    BC.sort(key=lambda r: r["J"])
    # choix : J minimal mais en évitant un minimum « en pointe » : on prend le pas
    # qui minimise la moyenne glissante de J sur ±0,02 mm
    BCp = sorted(BC, key=lambda r: r["cfg"].pitch)
    Js = np.array([r["J"] for r in BCp])
    Jsm = np.convolve(np.pad(Js, 1, mode="edge"), np.ones(3) / 3, mode="valid")
    kbest = int(np.argmin(Jsm))
    rec = BCp[kbest]
    cfg_rec = rec["cfg"]
    print(f"  affinage : pas retenu {cfg_rec.pitch*1e3:.2f} mm J={rec['J']:.1f}  ({time.time()-t0:.0f} s)")

    # robustesse : diamètre du palet, modèle de bord, régularisation δ_min
    rob = {}
    for dD in (-0.2, -0.1, 0.0, 0.1, 0.2):
        c = crant(cfg_rec, rec["h"], n=8, R=R_PUCK + 0.5 * dD * 1e-3)
        rob[f"D_puck{dD:+.1f}mm"] = {str(k): v["tot"] for k, v in c.items()}
    c = crant(cfg_rec, rec["h"], n=8, rim="abrupt")
    rob["rim_abrupt"] = {str(k): v["tot"] for k, v in c.items()}
    old = F.d_min
    for fac in (0.5, 2.0):
        F.d_min = lambda cfg, h, f=fac: f * max(cfg.d, 2 * h)
        c = crant(cfg_rec, rec["h"], n=8)
        rob[f"delta_min_x{fac}"] = {str(k): v["tot"] for k, v in c.items()}
    F.d_min = old
    # entrefer cible
    hstudy = {}
    for hh in (80e-6, 90e-6, 100e-6, 110e-6, 120e-6, 140e-6):
        try:
            c = crant(cfg_rec, hh, n=8)
            hstudy[f"{hh*1e6:.0f}"] = {str(k): dict(tot=v["tot"], tilt=v["tilt"], mom=v["mom"],
                                                    ps=v["ps"]) for k, v in c.items()}
        except ValueError:
            pass
    print(f"  robustesse terminée ({time.time()-t0:.0f} s)")

    def summ(r):
        return dict(label=r["cfg"].label(), d_mm=r["cfg"].d * 1e3, L_mm=r["cfg"].L * 1e3,
                    pattern=r["cfg"].pattern, pitch_mm=r["cfg"].pitch * 1e3,
                    h_um=r["h"] * 1e6, ps2=r["ps2"], ps10=r["ps10"], n_under_min=r["n_under_min"],
                    n_under_max=r["n_under_max"], n_total=r["n_total"], Q_max_m3h=r["Q_max_m3h"],
                    Q_min_m3h=r["Q_min_m3h"], J=r.get("J"),
                    crant={str(k): v for k, v in r.get("crant", {}).items()})

    res = dict(
        constraints=dict(ps_max=PS_MAX, ps_min=PS_MIN, n_under_min=N_MIN, d_min_mm=D_MIN * 1e3,
                         web_min_mm=WEB_MIN * 1e3, L_over_d_max=LD_MAX),
        stageA=[summ(r) for r in A], stageB=[summ(r) for r in B],
        stageC=[summ(r) for r in BCp], recommended=summ(rec), robustness=rob,
        h_study=hstudy, magic_pitches_hex_mm=hex_magic, magic_pitches_square_mm=sq_magic,
        runtime_s=time.time() - t0)
    save_json("optimization.json", res)
    save_json("recommended_hole.json", dict(config=cfg_rec, h_target_um=rec["h"] * 1e6,
                                            J_urad=rec["J"], note="écrit par optimize.py"))

    # --- Figures
    plt = setup_style()
    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    for d, col in zip((0.30, 0.35, 0.40), SERIES):
        for pat, mk in (("hex", "o"), ("square", "s")):
            rr = [r for r in B if abs(r["cfg"].d - d * 1e-3) < 1e-9 and r["cfg"].pattern == pat]
            if rr:
                ax.scatter([r["Q_max_m3h"] for r in rr], [r["J"] for r in rr], s=18, marker=mk,
                           color=col, alpha=0.75, edgecolor="none",
                           label=f"d = {d:.2f} mm, {'hexagonale' if pat == 'hex' else 'carrée'}")
    ax.scatter([rec["Q_max_m3h"]], [rec["J"]], s=120, facecolor="none", edgecolor=INK2, lw=1.5)
    ax.annotate("recommandé", (rec["Q_max_m3h"], rec["J"]), xytext=(10, 10),
                textcoords="offset points", fontsize=8, color=INK2)
    ax.set_xlabel("débit total de la zone percée à ps(10 g)·1,1 (m³/h)")
    ax.set_ylabel("J = max_m pente équivalente RMS (µrad)")
    ax.set_yscale("log")
    ax.set_title("Configurations admissibles : crantage vs débit")
    ax.legend(fontsize=7, ncol=2)
    savefig(fig, "optim_pareto.png")

    fig, axs = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
    for ax, pat in zip(axs, ("hex", "square")):
        for (d, L), col in zip(((0.30, 1.0), (0.30, 1.2), (0.35, 1.2), (0.40, 1.0)), SERIES):
            rr = sorted([r for r in B if abs(r["cfg"].d - d * 1e-3) < 1e-9 and abs(r["cfg"].L - L * 1e-3) < 1e-9
                         and r["cfg"].pattern == pat and abs(r["h"] - rec["h"]) < 1e-9],
                        key=lambda r: r["cfg"].pitch)
            if rr:
                ax.plot([r["cfg"].pitch * 1e3 for r in rr], [r["J"] for r in rr], "-o", ms=4,
                        color=col, label=f"d={d:.2f}, L={L:.1f}")
        for pm in (hex_magic if pat == "hex" else sq_magic):
            ax.axvline(pm, color=MUTED, lw=0.6, ls=":")
        ax.set_xlabel("pas (mm)")
        ax.set_title(f"Maille {'hexagonale' if pat == 'hex' else 'carrée'} — h = {rec['h']*1e6:.0f} µm"
                     " (pointillés : pas « magiques » J3)")
    axs[0].set_ylabel("J (µrad RMS, pire masse)")
    axs[0].legend(fontsize=8)
    savefig(fig, "optim_crantage_vs_pas.png")

    fig, ax = plt.subplots(figsize=(6.5, 4))
    ax.plot([r["cfg"].pitch * 1e3 for r in BCp], Js, "-o", color=SERIES[0], ms=4, label="J")
    ax.plot([r["cfg"].pitch * 1e3 for r in BCp], Jsm, "--", color=SERIES[1], label="moyenne glissante")
    ax.axvline(cfg_rec.pitch * 1e3, color=INK2, lw=0.8)
    ax.set_xlabel("pas (mm)")
    ax.set_ylabel("J (µrad)")
    ax.set_title(f"Affinage du pas — {cfg_rec.label()}")
    ax.legend()
    savefig(fig, "optim_affinage_pas.png")
    print(f"Terminé en {time.time()-t0:.0f} s")


if __name__ == "__main__":
    main()
