"""Table de consigne masse → pression plenum, loi d'entrefer h(m) et enveloppe ventilateur.

1. Loi d'entrefer cible h(m) : pour chaque masse, on cherche l'entrefer qui
   minimise la pente équivalente de crantage RMS (basculement + quantité de
   mouvement du film, modèle discret sur la cellule, `optimize.crant`) sous la
   contrainte h ≥ 80 µm (cahier des charges). Les palets lourds ont intérêt à
   voler plus bas : la poussée de quantité de mouvement croît comme q², donc
   comme ps². La loi est lissée (affine en ln m) puis bornée à [80, 140] µm.
2. Pour m = 2…10 g (pas 0,5 g) : ps(m) au h(m) — modèle axisymétrique corrigé
   « puits » et modèle discret moyenné sur la cellule —, h à ±10 % de ps,
   ondulation de portance et de h sur la cellule, bande d'incertitude du modèle
   (lois d'orifice shah_sharp / coord, K_c = 0 / 1), débit total et Δp
   ventilateur (`network.total_flow`, `network.fan_total_pressure`).
3. Table pour le firmware (≤ 16 points, format `points` [{mass_g, p_Pa}] lu par
   `firmware/lib/atcore/setpoints.cpp` et `host/airtable_host/client.py`),
   ajustement polynomial ps(m), enveloppe {ps_min_Pa, ps_max_Pa, Q, Δp} lue par
   `network.py`.

Écrit results/setpoints.json et deux figures.
Lancement : ``python3 -m calc.aero.setpoints`` (≈ 1–2 min sur 4 cœurs).
"""
from __future__ import annotations

import os
import time
from multiprocessing import Pool

import numpy as np
from scipy.optimize import brentq

from calc.aero.common import (G, P, A_PUCK, recommended_config, unit_cell_positions,
                              setup_style, savefig, save_json, SERIES, INK2, MUTED, GRID)
from calc.aero import film as F
from calc.aero.optimize import crant, ps_for
from calc.aero import network as NW

H_MIN_UM = P["performance_targets"]["gap_min_um"]          # 80 µm
H_MAX_LAW_UM = 140.0
H_GRID_UM = (70.0, 80.0, 90.0, 100.0, 110.0, 120.0, 130.0, 140.0)
M_LAW = (2.0, 3.0, 4.0, 5.0, 6.0, 7.5, 10.0)
M_TABLE = tuple(np.round(np.arange(2.0, 10.0 + 1e-9, 0.5), 2))
M_FIRMWARE = (2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0)   # ≤ 16 points
PS_ADJ = 0.10                                          # ±10 % de réglage autour de la consigne


# ---------------------------------------------------------------------------
def _crant_job(args):
    cfg, m, h_um = args
    try:
        c = crant(cfg, h_um * 1e-6, n=10, masses=(m,))[m]
    except ValueError:
        return None
    return dict(m=m, h_um=h_um, tot=c["tot"], tilt=c["tilt"], mom=c["mom"], ps=c["ps"],
                tot_max=c["tot_max"], jet=c["jet"])


def h_law_from_grid(rows):
    """Minimum de J(h) par masse (raffinement parabolique), puis lissage affine en ln m."""
    hopt = []
    for m in M_LAW:
        rr = sorted([r for r in rows if r and r["m"] == m and r["h_um"] >= H_MIN_UM - 1e-9],
                    key=lambda r: r["h_um"])
        hs = np.array([r["h_um"] for r in rr])
        Js = np.array([r["tot"] for r in rr])
        k = int(np.argmin(Js))
        if 0 < k < len(hs) - 1:
            a, b, _ = np.polyfit(hs[k - 1:k + 2], Js[k - 1:k + 2], 2)
            hk = -b / (2 * a) if a > 0 else hs[k]
            hk = float(np.clip(hk, hs[k - 1], hs[k + 1]))
        else:
            hk = float(hs[k])
        hopt.append(hk)
    hopt = np.array(hopt)
    c1, c0 = np.polyfit(np.log(M_LAW), hopt, 1)
    law = lambda m: float(np.clip(c0 + c1 * np.log(m), H_MIN_UM, H_MAX_LAW_UM))
    return hopt, (c0, c1), law


def W_cell(cfg, ps, h, pos):
    """Portance moyenne sur la cellule (modèle discret, fonction de Green)."""
    return float(np.mean([F.green_solve(cfg, ps, h, center=c)["W"] for c in pos]))


def ps_discrete(cfg, m, h, ps0, pos):
    Wt = m * 1e-3 * G
    return brentq(lambda p: W_cell(cfg, p, h, pos) - Wt, 0.9 * ps0, 1.1 * ps0, rtol=1e-6)


def _table_job(args):
    cfg, m, h = args
    mk = m * 1e-3
    ps = ps_for(cfg, m, h)
    pos = unit_cell_positions(cfg, 6)
    psd = ps_discrete(cfg, m, h, ps, pos)
    kz = F.axi_kz(cfg, ps, h)
    kth = F.axi_ktheta(cfg, ps, h)
    st = F.cogging_stats(cfg, ps, h, kth, kz, n=8)
    h_lo = F.axi_solve_h(cfg, (1 - PS_ADJ) * ps, mk)
    h_hi = F.axi_solve_h(cfg, (1 + PS_ADJ) * ps, mk)
    dps = 0.02 * ps
    dhdp = (F.axi_solve_h(cfg, ps + dps, mk) - F.axi_solve_h(cfg, ps - dps, mk)) / (2 * dps)
    sol = F.axi_solve(cfg, ps, h)
    # bande d'incertitude du modèle : ps requis pour h, et h obtenu à ps nominal
    var = {}
    for tag, c2 in (("shah_sharp", cfg.with_(model="shah_sharp")), ("coord", cfg.with_(model="coord")),
                    ("K_c=0", cfg.with_(K_c=0.0)), ("K_c=1", cfg.with_(K_c=1.0))):
        var[tag] = dict(ps_for_h=ps_for(c2, m, h), h_at_ps_nom_um=F.axi_solve_h(c2, ps, mk) * 1e6)
    Q = NW.total_flow(ps, cfg)
    return dict(mass_g=m, h_um=h * 1e6, ps_axi_Pa=ps, ps_discrete_Pa=psd,
                ps_ratio_disc_axi=psd / ps, W_over_A_Pa=mk * G / A_PUCK,
                h_at_ps_minus10pct_um=h_lo * 1e6, h_at_ps_plus10pct_um=h_hi * 1e6,
                dh_dps_um_per_Pa=dhdp * 1e6, kz_N_m=kz, ktheta_Nm_rad=kth,
                W_ripple_pp_rel=st["W_ripple_pp"], dh_ripple_pp_um=st["dh_pp"] * 1e6,
                Q_under_puck_m3h=sol["Q"] * 3600, variants=var,
                ps_band_Pa=[min(v["ps_for_h"] for v in var.values()) if var else ps,
                            max(v["ps_for_h"] for v in var.values()) if var else ps],
                h_band_um=[min(v["h_at_ps_nom_um"] for v in var.values()),
                           max(v["h_at_ps_nom_um"] for v in var.values())],
                Q_total_m3h=Q * 3600, dp_fan_clean_Pa=NW.fan_total_pressure(ps, Q),
                dp_fan_dirty_Pa=NW.fan_total_pressure(ps, Q, dirty=True))


def main():
    t0 = time.time()
    cfg = recommended_config()
    jobs = [(cfg, m, h) for m in M_LAW for h in H_GRID_UM]
    with Pool(min(4, os.cpu_count() or 1)) as pool:
        rows = pool.map(_crant_job, jobs, chunksize=2)
        hopt, (c0, c1), law = h_law_from_grid(rows)
        print(f"loi h(m) : h_opt = {np.round(hopt, 1)} µm ; h = {c0:.1f} {c1:+.1f}·ln(m) "
              f"({time.time()-t0:.0f} s)")
        # J sur la loi retenue (vérification)
        Jlaw = pool.map(_crant_job, [(cfg, m, law(m)) for m in M_LAW])
        tab = pool.map(_table_job, [(cfg, float(m), law(float(m)) * 1e-6) for m in M_TABLE])
    print(f"table calculée ({time.time()-t0:.0f} s)")
    ms = np.array([r["mass_g"] for r in tab])
    psd = np.array([r["ps_discrete_Pa"] for r in tab])
    # ajustement polynomial pour le firmware (quadratique en m)
    cf = np.polyfit(ms, psd, 2)
    fit_err = float(np.max(np.abs(np.polyval(cf, ms) - psd)))
    # table firmware : sous-ensemble ≤ 16 points ; erreur d'interpolation linéaire
    fw = [(m, float(np.interp(m, ms, psd))) for m in M_FIRMWARE]
    interp = np.interp(ms, [m for m, _ in fw], [p for _, p in fw])
    dhdp = np.array([r["dh_dps_um_per_Pa"] for r in tab])
    interp_err_Pa = float(np.max(np.abs(interp - psd)))
    interp_err_um = float(np.max(np.abs(interp - psd) * dhdp))
    # enveloppe : ±10 % de réglage autour de la bande d'incertitude du modèle
    r2, r10 = tab[0], tab[-1]
    ps_min = (1 - PS_ADJ) * min(r2["ps_band_Pa"][0], r2["ps_discrete_Pa"])
    ps_max = (1 + PS_ADJ) * max(r10["ps_band_Pa"][1], r10["ps_discrete_Pa"])
    Q_min, Q_max = NW.total_flow(ps_min, cfg), NW.total_flow(ps_max, cfg)
    env = dict(ps_min_Pa=ps_min, ps_max_Pa=ps_max,
               ps_nominal_range_Pa=[float(psd[0]), float(psd[-1])],
               Q_min_m3h=Q_min * 3600, Q_max_m3h=Q_max * 3600,
               dp_fan_min_Pa=NW.fan_total_pressure(ps_min, Q_min),
               dp_fan_max_clean_Pa=NW.fan_total_pressure(ps_max, Q_max),
               dp_fan_max_dirty_Pa=NW.fan_total_pressure(ps_max, Q_max, dirty=True),
               basis="ps_min = 0,9 × min(bande modèle, ps nominal) à 2 g ; ps_max = 1,1 × max(bande "
                     "modèle, ps nominal) à 10 g ; débits = trous libres de la zone percée + fuites "
                     "(network.total_flow) ; Δp ventilateur = ps + pertes de chaîne (network.py), "
                     "sans les marges ×1,15 appliquées par network.py")
    h5 = law(5.0)
    out = {
        "h_target_um": round(h5, 1),
        "points": [{"mass_g": m, "p_Pa": round(p, 2), "h_um": round(law(m), 1)} for m, p in fw],
        "status": "table finale du lot aéraulique (setpoints.py) : ps = modèle discret moyenné sur "
                  "la cellule au h(m) de la clé h_law ; h_target_um = h(5 g) (indicatif, l'entrefer "
                  "cible dépend de la masse) ; à recaler sur banc (span capteur, Cd réel des trous)",
        "config": cfg,
        "h_law": dict(mass_g=list(M_TABLE), h_um=[round(law(m), 2) for m in M_TABLE],
                      formula_um=f"h = clip({c0:.2f} {c1:+.2f}·ln(m_g), {H_MIN_UM:.0f}, {H_MAX_LAW_UM:.0f})",
                      h_opt_raw_um=dict(zip([str(m) for m in M_LAW], hopt.tolist())),
                      criterion="minimum de la pente équivalente de crantage RMS par masse, h ≥ 80 µm"),
        "envelope": env,
        "fit_quadratic": dict(coeffs_c2_c1_c0=cf.tolist(), formula="ps_Pa = c2·m² + c1·m + c0 (m en g)",
                              max_error_Pa=fit_err),
        "firmware_interp": dict(n_points=len(fw), max_error_Pa=interp_err_Pa, max_error_h_um=interp_err_um),
        "table": tab,
        "J_grid": [r for r in rows if r],
        "J_on_law": [r for r in Jlaw if r],
        "J_fixed_h100": [r for r in rows if r and abs(r["h_um"] - 100.0) < 1e-6],
        "runtime_s": time.time() - t0,
    }
    save_json("setpoints.json", out)

    # --- figures
    plt = setup_style()
    fig, axs = plt.subplots(1, 2, figsize=(11, 4.2))
    ax = axs[0]
    for m, col in zip(M_LAW, SERIES):
        rr = sorted([r for r in rows if r and r["m"] == m], key=lambda r: r["h_um"])
        ax.plot([r["h_um"] for r in rr], [r["tot"] for r in rr], "-o", ms=3.5, color=col, label=f"{m:g} g")
    ax.axvline(H_MIN_UM, color=MUTED, ls=":", lw=0.8)
    ax.axhline(50, color=INK2, ls="--", lw=0.8)
    ax.text(H_GRID_UM[0], 51, "budget 50 µrad", fontsize=7.5, color=INK2)
    ax.set_xlabel("entrefer h (µm)")
    ax.set_ylabel("pente équivalente de crantage RMS (µrad)")
    ax.set_title("Crantage en fonction de l'entrefer cible")
    ax.legend(fontsize=7.5, ncol=2)
    ax = axs[1]
    mm = np.linspace(2, 10, 100)
    ax.plot(mm, [law(m) for m in mm], color=SERIES[0], label="loi retenue h(m)")
    ax.scatter(M_LAW, hopt, color=SERIES[1], s=18, zorder=4, label="minimum par masse")
    ax.set_xlabel("masse du palet (g)")
    ax.set_ylabel("entrefer cible (µm)")
    ax.set_title("Loi d'entrefer cible")
    ax.legend(fontsize=8)
    savefig(fig, "setpoints_loi_entrefer.png")

    fig, axs = plt.subplots(1, 2, figsize=(11, 4.2))
    ax = axs[0]
    lo = np.array([r["ps_band_Pa"][0] for r in tab])
    hi = np.array([r["ps_band_Pa"][1] for r in tab])
    ax.fill_between(ms, lo, hi, color=GRID, label="bande d'incertitude du modèle")
    ax.plot(ms, psd, color=SERIES[0], label="ps consigne (modèle discret)")
    ax.plot(ms, [r["W_over_A_Pa"] for r in tab], color=MUTED, ls="--", label="W/A (seuil de décollage)")
    ax.scatter([m for m, _ in fw], [p for _, p in fw], color=SERIES[1], s=14, zorder=5,
               label=f"points firmware ({len(fw)})")
    ax.set_xlabel("masse du palet (g)")
    ax.set_ylabel("pression plenum (Pa)")
    ax.set_title("Consigne de pression ps(m)")
    ax.legend(fontsize=8)
    ax = axs[1]
    ax.plot(ms, [r["Q_total_m3h"] for r in tab], color=SERIES[0], label="débit total (m³/h)")
    ax2 = ax.twinx()
    ax2.plot(ms, [r["dp_fan_clean_Pa"] for r in tab], color=SERIES[1], label="Δp ventilateur, filtre neuf")
    ax2.plot(ms, [r["dp_fan_dirty_Pa"] for r in tab], color=SERIES[1], ls="--", label="filtre colmaté")
    ax2.set_ylabel("Δp total ventilateur (Pa)")
    ax2.grid(False)
    ax.set_xlabel("masse du palet (g)")
    ax.set_ylabel("débit total (m³/h)")
    ax.set_title("Point de fonctionnement du ventilateur")
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, fontsize=8, loc="upper left")
    savefig(fig, "setpoints_consigne.png")

    for r in tab:
        print(f"{r['mass_g']:4.1f} g h={r['h_um']:.0f} ps={r['ps_discrete_Pa']:.1f} (axi {r['ps_axi_Pa']:.1f}) "
              f"band {r['ps_band_Pa'][0]:.0f}-{r['ps_band_Pa'][1]:.0f} h±10% {r['h_at_ps_minus10pct_um']:.0f}/"
              f"{r['h_at_ps_plus10pct_um']:.0f} Q={r['Q_total_m3h']:.1f} dp={r['dp_fan_clean_Pa']:.0f}")
    print("J sur la loi :", [(r["m"], round(r["h_um"]), round(r["tot"], 1)) for r in Jlaw if r])
    print("enveloppe", {k: (round(v, 1) if isinstance(v, float) else v) for k, v in env.items() if k != "basis"})
    print(f"interp firmware : {interp_err_Pa:.2f} Pa = {interp_err_um:.2f} µm ; fit quad {fit_err:.2f} Pa")
    print(f"Terminé en {time.time()-t0:.0f} s")


if __name__ == "__main__":
    main()
