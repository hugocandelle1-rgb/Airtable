"""Crantage : efforts parasites liés à la position du palet dans le réseau de trous.

1. Cartes sur la cellule primitive (baseline hex 5 / Ø0,40 / L1,0 à h = 120 µm et
   configuration recommandée à h(m)) : ondulation de portance ΔW/W, ondulation
   d'entrefer Δh, vecteur « pente équivalente » (basculement + quantité de
   mouvement du film) ; décomposition en harmoniques du réseau.
2. Courbe crantage vs pas (balayage fin, maille hexagonale, Ø0,30/L1,2, h(m)) avec les
   pas « magiques » (zéros de J3) ; comparaison des deux mécanismes.
3. Tableau comparatif : recommandé, hex 2,94, baseline, pas 4/5/6 hex/carré, pas magiques
   4,23 et 4,82 mm (Ø0,30/0,35/0,40, L1,0/1,2) — nombre de trous, temps
   d'usinage estimé, débit, crantage (entrefer optimal par masse parmi 80/100/120 µm).
4. Robustesse aux tolérances réelles (recommandé et pas magiques) : Ø palet
   30 ± 0,1/0,2 mm, arrondi de l'arête du palet (rayon effectif), modèle de bord,
   régularisation δ_min (×0,5/×2), toutes positions de la cellule (RMS et max).
5. Validation de l'équilibre complet DF 2D (h0, a, b) contre la linéarisation
   θ = M/k_θ (3 positions) et balourd e = 100 µm par DF.

Écrit results/cogging.json et 4 figures.
Lancement : ``python3 -m calc.aero.cogging`` (≈ 2–3 min sur 4 cœurs).
"""
from __future__ import annotations

import os
import time
from multiprocessing import Pool

import numpy as np

from calc.aero.common import (G, R_PUCK, baseline_config, recommended_config, h_target_for,
                              count_holes_square_zone, unit_cell_positions, lattice_vectors,
                              setup_style, savefig, save_json, diverging_cmap, seq_cmap,
                              SERIES, INK, INK2, MUTED)
from calc.aero import film as F
from calc.aero.optimize import crant, ps_for
from calc.aero.orifice import q_free

MASSES = (2.0, 5.0, 10.0)
BUDGET = 50.0                       # µrad crête (cahier des charges)
H_CHOICES = (80e-6, 100e-6, 120e-6)

# Temps d'usinage indicatif par trou (hypothèses, à confirmer par l'usineur) :
# positionnement 0,5 s ; perçage borgne Ø1,5–2 × ~24 mm au foret carbure à
# débourrage ≈ 5 s ; orifice Ø0,3–0,4 × 1–1,2 mm au micro-foret, débourrage
# 0,1–0,15 mm ≈ 3,5 s. Soit ≈ 9 s/trou hors changements d'outil et contrôle.
T_HOLE_S = 0.5 + 5.0 + 3.5


def machining_hours(n):
    return n * T_HOLE_S / 3600


def edge_round_dR(r_e, h):
    """Réduction du rayon porteur effectif due à un arrondi d'arête de rayon r_e :
    le film « s'arrête » où le jeu supplémentaire atteint h (e(x) = r_e − √(r_e² − x²)),
    soit x_h = √(2 r_e h − h²) au-delà du point de tangence (x_h ≤ r_e)."""
    if r_e <= 0:
        return 0.0
    xh = np.sqrt(max(2 * r_e * h - h * h, 0.0)) if h < r_e else r_e
    return r_e - min(xh, r_e)


# ---------------------------------------------------------------------------
def cell_map(cfg, m, h, n=16):
    ps = ps_for(cfg, m, h)
    kth = F.axi_ktheta(cfg, ps, h)
    kz = F.axi_kz(cfg, ps, h)
    st = F.cogging_stats(cfg, ps, h, kth, kz, n=n, momentum=True)
    return dict(ps=ps, kth=kth, kz=kz, pos=st["pos"], W=st["W"], slope=st["slope"],
                slope_tilt=st["slope_tilt"], Fmom=st["Fmom"], Fjet=st["Fjet"],
                dh=(st["W"] - st["W"].mean()) / kz, stats={k: v for k, v in st.items()
                                                          if np.isscalar(v)})


def harmonics(cfg, pos, vec, kmax=2):
    """Amplitude des harmoniques du réseau réciproque (anneaux |G| = 1, √3, 2…)."""
    a1, a2 = lattice_vectors(cfg)
    A = np.array([a1, a2])
    B = 2 * np.pi * np.linalg.inv(A).T          # vecteurs réciproques (lignes)
    out = []
    z = vec[:, 0] + 1j * vec[:, 1]
    seen = {}
    for i in range(-kmax, kmax + 1):
        for j in range(-kmax, kmax + 1):
            if i == 0 and j == 0:
                continue
            Gv = i * B[0] + j * B[1]
            g = round(float(np.hypot(*Gv) / np.hypot(*B[0])), 3)
            c = np.mean(z * np.exp(-1j * pos @ Gv))
            seen.setdefault(g, 0.0)
            seen[g] += abs(c) ** 2
    for g in sorted(seen):
        out.append(dict(ring_G_over_G1=g, amplitude=float(np.sqrt(seen[g]))))
    mean = abs(np.mean(z))
    return dict(mean=float(mean), rings=out[:4])


def _best_h_job(args):
    """J par masse avec l'entrefer optimal parmi H_CHOICES (h dépendant de la masse)."""
    cfg, tag = args
    res = {}
    for m in MASSES:
        best = None
        for h in H_CHOICES:
            try:
                c = crant(cfg, h, n=8, masses=(m,))[m]
            except ValueError:
                continue
            if c["ps"] > 400.0:
                continue
            if best is None or c["tot"] < best["tot"]:
                best = dict(c, h_um=h * 1e6)
        res[str(m)] = best
    vals = [v["tot"] for v in res.values() if v]
    J = max(vals) if len(vals) == len(MASSES) else np.nan
    n = count_holes_square_zone(cfg)
    ps10 = res["10.0"]["ps"] if res["10.0"] else np.nan
    return dict(tag=tag, label=cfg.label(), d_mm=cfg.d * 1e3, L_mm=cfg.L * 1e3, pattern=cfg.pattern,
                pitch_mm=cfg.pitch * 1e3, n_holes=n, machining_h=machining_hours(n),
                n_under=len(F.covered_holes(cfg, (0.0, 0.0), rim="abrupt")),
                Q_max_m3h=n * float(q_free(1.1 * ps10, cfg)) * 3600 if np.isfinite(ps10) else np.nan,
                J=J, per_mass=res)


def _law_job(args):
    """J sur la loi h(m) pour une config et un rayon de palet donnés."""
    cfg, R, rim, tag = args
    out = {}
    for m in MASSES:
        h = h_target_for(m)
        c = crant(cfg, h, n=10, R=R, rim=rim, masses=(m,))[m]
        out[str(m)] = dict(tot=c["tot"], tot_max=c["tot_max"], tilt=c["tilt"], mom=c["mom"],
                           jet=c["jet"], h_um=h * 1e6)
    return dict(tag=tag, J=max(v["tot"] for v in out.values()),
                J_max=max(v["tot_max"] for v in out.values()), per_mass=out)


def _sweep_job(args):
    cfg, h = args
    out = {}
    for m in MASSES:
        c = crant(cfg, h if h else h_target_for(m), n=8, masses=(m,))[m]
        out[str(m)] = dict(tot=c["tot"], tilt=c["tilt"], mom=c["mom"])
    return cfg.pitch * 1e3, out


def _fd_job(args):
    """Équilibre complet DF (h0, a, b) vs linéarisation, une position."""
    cfg, m, c, x_cg = args
    h = h_target_for(m)
    ps = ps_for(cfg, m, h)
    kth = F.axi_ktheta(cfg, ps, h)
    xy = F.covered_holes(cfg, c)
    fd = F.FD2D(N=140)
    hg = F.green_solve_h(cfg, ps, m * 1e-3, center=c)
    sg = F.green_solve(cfg, ps, hg, xy=xy)
    kth_fd, _, _ = fd.ktheta(cfg, ps, xy, hg)
    lin = (sg["M"] - m * 1e-3 * G * np.asarray(x_cg)) / kth_fd
    eq = fd.equilibrium(cfg, ps, xy, m * 1e-3, x_cg=x_cg, h_init=hg, kth=kth_fd)
    return dict(mass_g=m, center_mm=(np.asarray(c) * 1e3).tolist(), x_cg_um=(np.asarray(x_cg) * 1e6).tolist(),
                ps=ps, h_green_um=hg * 1e6, h_fd_um=eq["h0"] * 1e6,
                tilt_lin_urad=(lin * 1e6).tolist(), tilt_fd_urad=[eq["a"] * 1e6, eq["b"] * 1e6],
                kth_axi=kth, kth_fd=kth_fd, residual=eq["hist"][-1],
                slope_equiv_fd_urad=float(0.5 * np.hypot(eq["a"], eq["b"]) * 1e6))


def main():
    t0 = time.time()
    plt = setup_style()
    rec = recommended_config()
    base = baseline_config()
    res = dict(config=rec, baseline=base, budget_urad=BUDGET, T_hole_s=T_HOLE_S)

    # ---- 1. cartes
    maps = {}
    for tag, cfg, hfun in (("baseline", base, lambda m: 120e-6), ("recommande", rec, h_target_for)):
        maps[tag] = {m: cell_map(cfg, m, hfun(m)) for m in MASSES}
    res["maps"] = {tag: {str(m): dict(ps=v["ps"], h_um=(120.0 if tag == "baseline" else h_target_for(m) * 1e6),
                                      stats=v["stats"],
                                      W_ripple_pp_rel=float(np.ptp(v["W"]) / v["W"].mean()),
                                      dh_pp_um=float(np.ptp(v["dh"]) * 1e6),
                                      slope_rms_urad=float(np.sqrt(np.mean(np.sum(v["slope"]**2, 1)))) * 1e6,
                                      slope_max_urad=float(np.max(np.hypot(*v["slope"].T))) * 1e6,
                                      slope_mean_urad=float(np.hypot(*v["slope"].mean(0))) * 1e6,
                                      harmonics=harmonics(rec if tag == "recommande" else base, v["pos"],
                                                          v["slope"] * 1e6))
                           for m, v in mp.items()} for tag, mp in maps.items()}
    print(f"cartes ({time.time()-t0:.0f} s)")
    fig, axs = plt.subplots(2, 3, figsize=(13, 8))
    for row, (tag, cfg) in enumerate((("baseline", base), ("recommande", rec))):
        for col, m in enumerate(MASSES):
            v = maps[tag][m]
            ax = axs[row, col]
            p = v["pos"] * 1e3
            mag = np.hypot(*v["slope"].T) * 1e6
            sc = ax.scatter(p[:, 0], p[:, 1], c=mag, cmap=seq_cmap(), s=28, marker="h", vmin=0)
            ax.quiver(p[:, 0], p[:, 1], v["slope"][:, 0], v["slope"][:, 1], color=INK, scale=None,
                      width=0.004, alpha=0.8)
            a1, a2 = lattice_vectors(cfg)
            cell = np.array([[0, 0], a1, a1 + a2, a2, [0, 0]]) * 1e3
            ax.plot(cell[:, 0], cell[:, 1], color=MUTED, lw=0.8)
            ax.set_aspect("equal")
            ax.set_title(f"{'baseline hex 5 / Ø0,40' if tag == 'baseline' else 'recommandé ' + cfg.label()}"
                         f"\n{m:g} g — RMS {res['maps'][tag][str(m)]['slope_rms_urad']:.0f} µrad, "
                         f"Δh {res['maps'][tag][str(m)]['dh_pp_um']:.2f} µm c-à-c", fontsize=8.5)
            ax.set_xlabel("x centre palet (mm)")
            fig.colorbar(sc, ax=ax, shrink=0.8, label="pente équivalente (µrad)")
    axs[0, 0].set_ylabel("y (mm)")
    axs[1, 0].set_ylabel("y (mm)")
    savefig(fig, "crantage_cartes_cellule.png")

    with Pool(min(4, os.cpu_count() or 1)) as pool:
        # ---- 2. balayage fin du pas
        pitches = np.round(np.arange(2.70, 6.001, 0.05), 3)
        sw_cfg = rec.with_(pattern="hex")
        sweep = pool.map(_sweep_job, [(sw_cfg.with_(pitch=p * 1e-3), None) for p in pitches], chunksize=3)
        res["pitch_sweep_hlaw"] = [dict(pitch_mm=p, **o) for p, o in sweep]
        print(f"balayage du pas ({time.time()-t0:.0f} s)")

        # ---- 3. tableau comparatif
        comp = [(rec, "recommandé")]
        for pat in ("hex", "square"):
            for p in (4.0, 5.0, 6.0):
                comp.append((base.with_(pattern=pat, pitch=p * 1e-3), f"baseline Ø0,40/L1,0 {pat} {p:g}"))
        comp.append((rec.with_(d=0.30e-3, L=1.2e-3, pitch=2.94e-3, pattern="hex", D_cb=1.5e-3),
                     "hex 2,94 Ø0,30/L1,2 (candidat 10/2026)"))
        for p in (4.23, 4.82):
            for d in (0.30, 0.35, 0.40):
                for L in (1.0, 1.2):
                    comp.append((rec.with_(d=d * 1e-3, L=L * 1e-3, pitch=p * 1e-3, pattern="hex"),
                                 f"magique {p:g}"))
        table = pool.map(_best_h_job, comp, chunksize=1)
        res["comparison"] = table
        print(f"comparaison ({time.time()-t0:.0f} s)")

        # ---- 4. robustesse (sur la loi h(m))
        rob_cfgs = [(rec, "recommandé"),
                    (rec.with_(pitch=2.94e-3, D_cb=1.5e-3), "hex 2,94 Ø0,30/L1,2"),
                    (rec.with_(pitch=4.23e-3), "hex 4,23 Ø0,30/L1,2"),
                    (rec.with_(pitch=4.82e-3), "hex 4,82 Ø0,30/L1,2"),
                    (base, "baseline hex 5 Ø0,40/L1,0")]
        jobs = []
        for cfg, tag in rob_cfgs:
            for dD in (-0.2, -0.1, 0.0, 0.1, 0.2):
                jobs.append((cfg, R_PUCK + 0.5 * dD * 1e-3, None, (tag, f"ΔD={dD:+.1f} mm")))
            for r_e in (0.2, 0.5):
                dR = edge_round_dR(r_e * 1e-3, 100e-6)
                jobs.append((cfg, R_PUCK - dR, None, (tag, f"arrondi r={r_e:.1f} mm (ΔR={-dR*1e3:.2f} mm)")))
            jobs.append((cfg, R_PUCK, "abrupt", (tag, "bord abrupt")))
        rob = pool.map(_law_job, jobs, chunksize=2)
        # régularisation δ_min (séquentiel : modifie une fonction du module)
        old = F.d_min
        for fac in (0.5, 2.0):
            F.d_min = lambda cfg, h, f=fac: f * max(cfg.d, 2 * h)
            for cfg, tag in rob_cfgs:
                rob.append(_law_job((cfg, R_PUCK, None, (tag, f"δ_min ×{fac:g}"))))
        F.d_min = old
        res["robustness"] = [dict(config=r["tag"][0], case=r["tag"][1], J=r["J"], J_max=r["J_max"],
                                  per_mass=r["per_mass"]) for r in rob]
        print(f"robustesse ({time.time()-t0:.0f} s)")

        # ---- 5. validation DF 2D
        a1, a2 = lattice_vectors(rec)
        fdjobs = [(rec, 10.0, 0.0 * a1, (0.0, 0.0)), (rec, 10.0, 0.37 * a1 + 0.21 * a2, (0.0, 0.0)),
                  (rec, 2.0, 0.5 * a1 + 0.5 * a2, (0.0, 0.0)), (rec, 5.0, 0.0 * a1, (100e-6, 0.0)),
                  (rec, 10.0, 0.0 * a1, (100e-6, 0.0)), (rec, 2.0, 0.0 * a1, (100e-6, 0.0))]
        fdv = pool.map(_fd_job, fdjobs, chunksize=1)
        res["fd_validation"] = fdv
        print(f"validation DF ({time.time()-t0:.0f} s)")

    # balourd : sensibilité analytique k_θ/W
    unb = {}
    for m in MASSES:
        h = h_target_for(m)
        ps = ps_for(rec, m, h)
        kth = F.axi_ktheta(rec, ps, h)
        unb[str(m)] = dict(ktheta_over_W_m=kth / (m * 1e-3 * G),
                           slope_urad_per_um=1e-6 / (2 * kth / (m * 1e-3 * G)) * 1e6)
    res["unbalance"] = unb

    # ---- figures : balayage
    fig, axs = plt.subplots(1, 3, figsize=(13, 4.0), sharey=True)
    pm = [r["pitch_mm"] for r in res["pitch_sweep_hlaw"]]
    for ax, m in zip(axs, MASSES):
        ax.plot(pm, [r[str(m)]["tilt"] for r in res["pitch_sweep_hlaw"]], color=SERIES[0], lw=1.4,
                label="basculement seul")
        ax.plot(pm, [r[str(m)]["mom"] for r in res["pitch_sweep_hlaw"]], color=SERIES[1], lw=1.4,
                label="quantité de mouvement seule")
        ax.plot(pm, [r[str(m)]["tot"] for r in res["pitch_sweep_hlaw"]], color=INK, lw=1.8, label="total (vectoriel)")
        for p in F.magic_pitches("hex") * 1e3:
            if 2.7 < p < 6.0:
                ax.axvline(p, color=MUTED, lw=0.6, ls=":")
        ax.axhline(BUDGET, color=INK2, ls="--", lw=0.8)
        ax.set_yscale("log")
        ax.set_xlabel("pas hexagonal (mm)")
        ax.set_title(f"{m:g} g — Ø0,30 / L1,2, h = {h_target_for(m)*1e6:.0f} µm")
    axs[0].set_ylabel("pente équivalente RMS sur la cellule (µrad)")
    axs[0].legend(fontsize=7.5)
    savefig(fig, "crantage_vs_pas.png")

    # ---- figure : comparaison
    fig, ax = plt.subplots(figsize=(8, 4.6))
    for k, r in enumerate(table):
        col = SERIES[3] if "2,94" in r["tag"] else SERIES[0] if r["tag"] == "recommandé" else (SERIES[1] if r["tag"].startswith("magique") else SERIES[2])
        ax.scatter(r["n_holes"], r["J"], color=col, s=26, zorder=3)
    for r in table:
        if r["tag"] == "recommandé" or (r["tag"].startswith("magique") and abs(r["d_mm"] - 0.30) < 1e-6
                                        and abs(r["L_mm"] - 1.2) < 1e-6) or "hex 5" in r["tag"] or "2,94" in r["tag"]:
            ax.annotate(f"{r['label']}", (r["n_holes"], r["J"]), xytext=(5, 4), textcoords="offset points",
                        fontsize=7, color=INK2)
    ax.axhline(BUDGET, color=INK2, ls="--", lw=0.8)
    ax.set_xlabel("nombre de trous dans la zone percée 360 × 360")
    ax.set_ylabel("J = max_m pente équivalente RMS (µrad)")
    ax.set_yscale("log")
    ax.set_title("Crantage vs nombre de trous (bleu : recommandé, jaune : hex 2,94, orange : pas magiques, "
                 "vert : autres)", fontsize=8.5)
    savefig(fig, "crantage_comparaison.png")

    # ---- figure : robustesse
    fig, ax = plt.subplots(figsize=(9, 4.6))
    cases = [r["case"] for r in res["robustness"] if r["config"] == "recommandé"]
    x = np.arange(len(cases))
    for k, (cfg, tag) in enumerate(rob_cfgs):
        J = [next(r["J"] for r in res["robustness"] if r["config"] == tag and r["case"] == c) for c in cases]
        ax.bar(x + (k - 2) * 0.16, J, width=0.16, color=SERIES[k], label=tag)
    ax.axhline(BUDGET, color=INK2, ls="--", lw=0.8)
    ax.set_xticks(x, cases, rotation=35, ha="right", fontsize=7.5)
    ax.set_ylabel("J (µrad RMS, pire masse)")
    ax.set_title("Robustesse du crantage aux tolérances du palet et aux hypothèses du modèle")
    ax.legend(fontsize=7.5)
    savefig(fig, "crantage_robustesse.png")

    res["runtime_s"] = time.time() - t0
    save_json("cogging.json", res)
    for r in table:
        print(f"{r['tag']:32s} {r['label']:28s} N={r['n_holes']:6d} t≈{r['machining_h']:.0f} h J={r['J']:.1f} "
              f"Q={r['Q_max_m3h']:.1f} h*={[v['h_um'] if v else None for v in r['per_mass'].values()]}")
    for r in res["robustness"]:
        print(f"{r['config']:28s} {r['case']:36s} J={r['J']:.1f} max={r['J_max']:.1f}")
    for r in fdv:
        print(f"DF {r['mass_g']} g c={np.round(r['center_mm'],2)} e={r['x_cg_um']} h {r['h_green_um']:.2f}/"
              f"{r['h_fd_um']:.2f} tilt lin {np.round(r['tilt_lin_urad'],1)} fd {np.round(r['tilt_fd_urad'],1)} "
              f"kth {r['kth_axi']:.4f}/{r['kth_fd']:.4f}")
    print("balourd", unb)
    print(f"Terminé en {time.time()-t0:.0f} s")


if __name__ == "__main__":
    main()
