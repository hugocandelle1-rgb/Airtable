"""Optimisation du perçage de la plaque (d, L, pas, maille, entrefer cible).

Étape A — balayage complet (modèle axisymétrique homogénéisé corrigé « puits »,
validé contre le modèle discret à 0,1 % près) : pressions extrêmes ps(2 g, h = 120 µm)
et ps(10 g, h = 80 µm), nombre de trous sous le palet, débit total de la zone
percée, contraintes d'usinabilité (d ≥ 0,30 mm, voile ≥ 0,8 mm, L/d ≤ 4).

Étape B — crantage (modèle discret, fonction de Green) des configurations
admissibles : pente équivalente RMS = basculement + quantité de mouvement du
film, pour 2, 5 et 10 g, sur la cellule primitive du réseau, **à l'entrefer
optimal de chaque masse** (h cible dépendant de la masse, h ≥ 80 µm).

Étape C — présélection (J ≤ 1,15·Jmin) : h(m) sur grille fine, J sous deux
variantes de modèle (δ_min ×0,5, bord abrupt) ; choix selon le critère d'origine.

Étape D — affinage du pas (±0,1 mm) en évitant un minimum « en pointe ».
La robustesse détaillée (Ø palet, arrondi d'arête, δ_min ×2) est dans cogging.py.

Critère (d'origine) : minimiser J = max_m(pente RMS) sous contraintes ; départage
parmi J ≤ 1,1·Jmin (et enveloppe des variantes ≤ 1,1 × la meilleure) par le débit
total puis le nombre de trous.

Écrit results/optimization.json et results/recommended_hole.json.
Lancement : ``python3 -m calc.aero.optimize`` (≈ 4 min sur 4 cœurs).
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
# Entrefers candidats par masse (h ≥ 80 µm ; les optimums observés sont 110–140 µm à 2 g,
# 80–120 µm à 5 g, 80–100 µm à 10 g) : étape B (criblage) et étape C (fin).
H_B = {2.0: (100e-6, 120e-6, 140e-6), 5.0: (80e-6, 100e-6, 120e-6), 10.0: (80e-6, 100e-6)}
H_C = {2.0: tuple(np.arange(100, 141, 10) * 1e-6), 5.0: tuple(np.arange(80, 131, 10) * 1e-6),
       10.0: tuple(np.arange(80, 111, 10) * 1e-6)}
H_LO_PRESS, H_HI_PRESS = 120e-6, 80e-6
T_HOLE_S = 9.0              # temps d'usinage indicatif par trou (s), cf. cogging.py
WEB_BORE_MIN = 1.40e-3      # paroi minimale entre perçages borgnes voisins (dérive du foret)


def counterbore_for(pitch, D_design=None):
    """Diamètre du perçage borgne d'alimentation compatible avec le pas :
    paroi ≥ 1,4 mm entre perçages voisins (dérive d'un foret Ø1,5–2 sur ~25 mm de
    l'ordre de 0,02–0,05 mm par trou) et porosité de plaque limitée ; arrondi
    au 0,1 mm inférieur, plafonné à la valeur de design.toml."""
    D_design = P["plate"]["counterbore_d_mm"] * 1e-3 if D_design is None else D_design
    return min(D_design, np.floor((pitch - WEB_BORE_MIN) * 1e4 + 1e-6) / 1e4)
MASSES = (2.0, 5.0, 10.0)


def ps_for(cfg, m_g, h):
    """Pression plenum donnant W = m g à l'entrefer h (modèle axisymétrique).

    Encadrement serré (ps > W/A toujours) pour limiter le nombre d'évaluations."""
    Wt = m_g * 1e-3 * G
    f = lambda p: F.axi_W(cfg, p, h) - Wt
    lo = 1.0001 * Wt / (np.pi * R_PUCK**2)
    hi = 2.5 * lo
    while f(hi) < 0:
        lo, hi = hi, 2.5 * hi
        if hi > 3e4:
            raise ValueError("ps hors domaine")
    return brentq(f, lo, hi, rtol=1e-6)


def stage_a(cfg):
    """Admissibilité et débit (indépendants de l'entrefer cible, bornes extrêmes :
    2 g à h = 120 µm pour la pression basse, 10 g à h = 80 µm pour la haute)."""
    try:
        p2 = ps_for(cfg, 2.0, H_LO_PRESS)
        p10 = ps_for(cfg, 10.0, H_HI_PRESS)
    except ValueError:
        return None
    nh = [len(F.covered_holes(cfg, c, rim="abrupt")) for c in unit_cell_positions(cfg, 6)]
    ntot = count_holes_square_zone(cfg)
    qmax = ntot * float(q_free(1.1 * p10, cfg))
    return dict(cfg=cfg, ps2=p2, ps10=p10, n_under_min=min(nh), n_under_max=max(nh),
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


def crant_best_h(cfg, m, hs, n=8):
    """Crantage d'une masse à l'entrefer optimal parmi `hs` (h ≥ 80 µm, ps ≤ 400 Pa)."""
    best = None
    for h in hs:
        try:
            c = crant(cfg, h, n=n, masses=(m,))[m]
        except ValueError:
            continue
        if c["ps"] > PS_MAX:
            continue
        c = dict(c, h_um=h * 1e6)
        if best is None or c["tot"] < best["tot"]:
            best = c
    return best


def stage_b(args):
    """J = max_m min_h pente RMS (entrefer cible dépendant de la masse)."""
    r, n, hgrid = args
    c = {m: crant_best_h(r["cfg"], m, hgrid[m], n=n) for m in MASSES}
    r = dict(r)
    r["crant"] = c
    r["J"] = max(v["tot"] for v in c.values()) if all(c.values()) else np.inf
    r["h_um"] = {m: (v["h_um"] if v else None) for m, v in c.items()}
    r["Q_max_m3h"] = r["n_total"] * float(q_free(1.1 * c[10.0]["ps"], r["cfg"])) * 3600 if c[10.0] else np.inf
    return r


def _variant_job(args):
    """J d'un candidat à ses h(m) retenus, pour une variante de modèle."""
    r, case = args
    old = F.d_min
    rim = None
    if case == "delta_min_x0.5":
        F.d_min = lambda cfg, h: 0.5 * max(cfg.d, 2 * h)
    elif case == "rim_abrupt":
        rim = "abrupt"
    try:
        J = max(crant(r["cfg"], r["h_um"][m] * 1e-6, n=10, rim=rim, masses=(m,))[m]["tot"]
                for m in MASSES)
    finally:
        F.d_min = old
    return J


def _feasible(r):
    return (r["n_under_min"] >= N_MIN and r["ps10"] <= PS_MAX and 0.9 * r["ps2"] >= PS_MIN)


def main():
    t0 = time.time()
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    base = baseline_config()
    hex_magic = [p for p in F.magic_pitches("hex") * 1e3 if 2.7 < p < 5.3]
    sq_magic = [p for p in F.magic_pitches("square") * 1e3 if 2.7 < p < 5.0]
    grid = []
    # d = 0,50 mm retiré du balayage (exécution complète 2026-10-29 : dominé en débit et en
    # crantage, comme d = 0,45 conservé ici pour montrer la tendance) — temps < 5 min.
    for d in (0.30, 0.35, 0.40, 0.45):
        for L in (0.8, 1.0, 1.2, 1.4, 1.6, 2.0):
            if L / d > LD_MAX + 1e-9 or L < WEB_MIN * 1e3 - 1e-9 or d < D_MIN * 1e3 - 1e-9:
                continue
            for pat, mags in (("hex", hex_magic), ("square", sq_magic)):
                pitches = sorted(set([3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0] + [round(p, 3) for p in mags]))
                for p in pitches:
                    grid.append(base.with_(d=d * 1e-3, L=L * 1e-3, pitch=p * 1e-3, pattern=pat))
    print(f"Étape A : {len(grid)} configurations")
    with Pool(min(4, os.cpu_count() or 1)) as pool:
        A = [r for r in pool.map(stage_a, grid, chunksize=8) if r is not None]
        feas = [r for r in A if _feasible(r)]
        # crantage : d ≤ 0,35 mm, L ≥ 1,0 mm ; d = 0,40 mm à L = 1,0 mm seulement (exécution
        # complète 2026-10-29 : J ≥ 86 µrad pour tous les L à d = 0,40 ; L = 0,8 mm toujours
        # dominé par L = 1,0 à d égal) — temps < 5 min.
        cand = [r for r in feas if r["cfg"].L >= 1.0e-3 - 1e-9 and (r["cfg"].d <= 0.35e-3 + 1e-9
                or (r["cfg"].d <= 0.40e-3 + 1e-9 and abs(r["cfg"].L - 1.0e-3) < 1e-9))]
        print(f"  admissibles : {len(feas)} ; étape B sur {len(cand)}  ({time.time()-t0:.0f} s)")
        B = pool.map(stage_b, [(r, 7, H_B) for r in cand], chunksize=2)
        B.sort(key=lambda r: r["J"])
        Jmin = B[0]["J"]
        print(f"  étape B : J min = {Jmin:.1f} µrad ({B[0]['cfg'].label()})  ({time.time()-t0:.0f} s)")

        # --- Étape C : présélection (J ≤ 1,15·Jmin, 6 au plus), h(m) fin, variantes de modèle
        short = [r for r in B if r["J"] <= 1.15 * Jmin][:6]
        C = pool.map(stage_b, [(r, 10, H_C) for r in short], chunksize=1)
        var = pool.map(_variant_job, [(r, case) for r in C for case in ("delta_min_x0.5", "rim_abrupt")])
        for k, r in enumerate(C):
            r["J_delta_min_x0.5"], r["J_rim_abrupt"] = var[2 * k], var[2 * k + 1]
            r["J_env"] = max(r["J"], *var[2 * k:2 * k + 2])
        JminC = min(r["J"] for r in C)
        JenvC = min(r["J_env"] for r in C)
        # critère d'origine : J minimal ; départage parmi J ≤ 1,1·Jmin (et enveloppe des
        # variantes de modèle ≤ 1,1 × la meilleure) par le débit puis le nombre de trous
        ok = [r for r in C if r["J"] <= 1.10 * JminC and r["J_env"] <= 1.10 * JenvC] or \
            [min(C, key=lambda r: r["J"])]
        ok.sort(key=lambda r: (round(r["Q_max_m3h"], 0), r["n_total"]))
        best = ok[0]
        print(f"  étape C : retenu {best['cfg'].label()} J={best['J']:.1f} J_env={best['J_env']:.1f} "
              f"Q={best['Q_max_m3h']:.1f} m3/h  ({time.time()-t0:.0f} s)")

        # --- Étape D : affinage du pas (±0,1 mm) avec h(m) au voisinage du choix
        cb = best["cfg"]
        hD = {m: tuple(h for h in H_C[m] if abs(h * 1e6 - best["h_um"][m]) <= 10.0 + 1e-6) for m in MASSES}
        pitches = np.round(cb.pitch * 1e3 + np.arange(-0.10, 0.101, 0.025), 3)
        AD = pool.map(stage_a, [cb.with_(pitch=p * 1e-3) for p in pitches])
        BD = pool.map(stage_b, [(r, 10, hD) for r in AD if r is not None])
    # choix : J minimal mais en évitant un minimum « en pointe » : on prend le pas
    # qui minimise la moyenne glissante de J sur ±0,025 mm
    BCp = sorted(BD, key=lambda r: r["cfg"].pitch)
    Js = np.array([r["J"] for r in BCp])
    Jsm = np.convolve(np.pad(Js, 1, mode="edge"), np.ones(3) / 3, mode="valid")
    kbest = int(np.argmin(Jsm))
    # cote ronde (multiple de 0,05 mm) préférée si équivalente (moyenne glissante ≤ +3 %)
    pD = np.array([r["cfg"].pitch * 1e3 for r in BCp])
    rnd = [k for k in range(len(BCp)) if abs(pD[k] / 0.05 - round(pD[k] / 0.05)) < 1e-6
           and abs(pD[k] - pD[kbest]) <= 0.0251 and Jsm[k] <= 1.03 * Jsm[kbest]]
    if rnd:
        kbest = min(rnd, key=lambda k: Jsm[k])
    rec = BCp[kbest]
    cfg_rec = rec["cfg"]
    print(f"  affinage : pas retenu {cfg_rec.pitch*1e3:.3f} mm J={rec['J']:.1f}  ({time.time()-t0:.0f} s)")

    def summ(r):
        return dict(label=r["cfg"].label(), d_mm=r["cfg"].d * 1e3, L_mm=r["cfg"].L * 1e3,
                    pattern=r["cfg"].pattern, pitch_mm=r["cfg"].pitch * 1e3,
                    h_um={str(k): v for k, v in r.get("h_um", {}).items()}, ps2_h120=r["ps2"],
                    ps10_h80=r["ps10"], n_under_min=r["n_under_min"],
                    n_under_max=r["n_under_max"], n_total=r["n_total"], Q_max_m3h=r["Q_max_m3h"],
                    Q_min_m3h=r["Q_min_m3h"], J=r.get("J"), J_env=r.get("J_env"),
                    J_delta_min_x05=r.get("J_delta_min_x0.5"), J_rim_abrupt=r.get("J_rim_abrupt"),
                    machining_h=r["n_total"] * T_HOLE_S / 3600,
                    crant={str(k): v for k, v in r.get("crant", {}).items()})

    res = dict(
        constraints=dict(ps_max=PS_MAX, ps_min=PS_MIN, n_under_min=N_MIN, d_min_mm=D_MIN * 1e3,
                         web_min_mm=WEB_MIN * 1e3, L_over_d_max=LD_MAX),
        h_grid_stageB_um={str(m): [h * 1e6 for h in v] for m, v in H_B.items()},
        h_grid_stageC_um={str(m): [h * 1e6 for h in v] for m, v in H_C.items()},
        stageA=[summ(r) for r in A], stageB=[summ(r) for r in B], stageC=[summ(r) for r in C],
        stageD=[summ(r) for r in BCp], recommended=summ(rec),
        magic_pitches_hex_mm=hex_magic, magic_pitches_square_mm=sq_magic,
        runtime_s=time.time() - t0)
    save_json("optimization.json", res)
    # perçage borgne adapté au pas (le crantage est insensible à D_cb : −1 % de débit)
    cfg_out = cfg_rec.with_(D_cb=counterbore_for(cfg_rec.pitch))
    save_json("recommended_hole.json", dict(config=cfg_out, h_target_um=rec["h_um"][5.0],
                                            h_um_by_mass={str(m): v for m, v in rec["h_um"].items()},
                                            J_urad=rec["J"], n_holes=rec["n_total"],
                                            counterbore_rule="paroi ≥ 1,4 mm entre perçages borgnes",
                                            note="écrit par optimize.py ; entrefer dépendant de la masse : "
                                                 "voir setpoints.json (h_law)"))

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
                         and r["cfg"].pattern == pat],
                        key=lambda r: r["cfg"].pitch)
            if rr:
                ax.plot([r["cfg"].pitch * 1e3 for r in rr], [r["J"] for r in rr], "-o", ms=4,
                        color=col, label=f"d={d:.2f}, L={L:.1f}")
        for pm in (hex_magic if pat == "hex" else sq_magic):
            ax.axvline(pm, color=MUTED, lw=0.6, ls=":")
        ax.set_xlabel("pas (mm)")
        ax.set_title(f"Maille {'hexagonale' if pat == 'hex' else 'carrée'} — h optimal par masse"
                     " (pointillés : pas « magiques » J3)", fontsize=9)
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
