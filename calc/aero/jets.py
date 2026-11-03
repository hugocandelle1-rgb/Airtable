"""Jets libres au-dessus de la plaque, écoulement dans la zone de travail, courants d'air.

1. Jets des trous non couverts : vitesse V, Reynolds Re = V d/ν, nature du jet.
   - jet rond laminaire (Schlichting) : demi-largeur r½ = 5,94·x/Re (x depuis l'orifice) ;
   - jet rond turbulent auto-similaire : r½ = 0,094·x (Hussein et al. 1994).
   Hauteur de coalescence x_c : r½ = p/2 (jets voisins qui se rejoignent).
2. Écoulement moyen ascendant au-dessus de la zone percée : U = Q/A_zone, et
   vitesse « quantité de mouvement » U_J = V·√φ (φ = taux d'ouverture) qui fixe
   la quantité de mouvement verticale du panache fusionné.
3. Courants d'air horizontaux : traînée sur la face latérale du palet
   F = ½ρ C_d(Re) D H v², convertie en pente équivalente F/(m g) ;
   vitesse admissible pour 5 µrad (allocation suggérée) ; dimensionnement de l'écran.
4. Entraînement en bordure de zone percée (aspiration latérale vers le panache).

Écrit results/jets.json et une figure.
Lancement : ``python3 -m calc.aero.jets`` (≈ 2 s).
"""
from __future__ import annotations

import numpy as np

from calc.aero.common import (RHO, NU, G, R_PUCK, PERF_SQUARE, WORK_SQUARE, recommended_config,
                              count_holes_square_zone, load_json, setup_style, savefig, save_json,
                              SERIES, INK2, MUTED)
from calc.aero.orifice import q_free

H_PUCK = 10e-3            # hauteur supposée des palets (m), comme dynamics.py
ALLOC_DRAFT_URAD = 5.0    # allocation suggérée aux courants d'air résiduels
ALPHA_ENTR = 0.05         # coefficient d'entraînement d'un panache plan (laminaire–transitoire)


def cd_cylinder(Re):
    """C_d d'un cylindre en écoulement transverse (White 2006, approximation 1 < Re < 2·10⁵)."""
    Re = np.maximum(np.asarray(Re, float), 1e-3)
    return 1.0 + 10.0 / Re ** (2.0 / 3.0)


def drag_slope_urad(v, m_g, H=H_PUCK, D=2 * R_PUCK):
    Re = v * D / NU
    F = 0.5 * RHO * cd_cylinder(Re) * D * H * v**2
    return F / (m_g * 1e-3 * G) * 1e6


def main():
    cfg = recommended_config()
    N = count_holes_square_zone(cfg)
    try:
        env = load_json("setpoints.json")["envelope"]
        ps_list = {"ps_min": env["ps_min_Pa"], "ps_max": env["ps_max_Pa"]}
    except (FileNotFoundError, KeyError):
        ps_list = {"ps_min": 40.0, "ps_max": 215.0}
    p = cfg.pitch
    phi = cfg.A * cfg.density
    A_zone = PERF_SQUARE**2
    jets = {}
    for tag, ps in ps_list.items():
        q = float(q_free(ps, cfg))
        V = q / cfg.A
        Re = V * cfg.d / NU
        x_lam = p / 2 * Re / 5.94
        x_turb = p / 2 / 0.094
        Q = N * q
        U = Q / A_zone
        UJ = V * np.sqrt(phi)
        jets[tag] = dict(ps_Pa=ps, q_m3s=q, V_m_s=V, Re=Re, x_coalescence_laminar_mm=x_lam * 1e3,
                         x_coalescence_turbulent_mm=x_turb * 1e3, x_coalescence_over_d_laminar=x_lam / cfg.d,
                         U_mean_up_m_s=U, U_momentum_m_s=UJ, Q_m3h=Q * 3600,
                         dyn_pressure_merged_Pa=0.5 * RHO * U**2,
                         # entraînement latéral en bord de zone (ordre de grandeur)
                         v_entrainment_edge_m_s=ALPHA_ENTR * UJ)
    # courants d'air : pente équivalente vs vitesse, pour 2 / 5 / 10 g
    vv = np.logspace(-3, np.log10(0.5), 120)
    drafts = {}
    for m in (2.0, 5.0, 10.0):
        sl = drag_slope_urad(vv, m)
        v_adm = float(np.interp(ALLOC_DRAFT_URAD, sl, vv))
        drafts[str(m)] = dict(v_admissible_m_s=v_adm,
                              slope_at_0p02_urad=float(drag_slope_urad(0.02, m)),
                              slope_at_0p05_urad=float(drag_slope_urad(0.05, m)),
                              slope_at_0p10_urad=float(drag_slope_urad(0.10, m)),
                              slope_at_0p20_urad=float(drag_slope_urad(0.20, m)))
    v_entr = jets["ps_max"]["v_entrainment_edge_m_s"]
    screen = dict(
        height_mm=120.0,
        rule="hauteur ≥ ~10 × la hauteur de coalescence des jets et ≥ 4 × la hauteur du palet ; "
             "le panache fusionné (U ≈ 0,03–0,1 m/s) doit sortir verticalement par le haut",
        walls="PMMA ou verre 4–6 mm, joint au cadre, sans fente basse (pas d'aspiration rasante)",
        top="couvercle respirant : nid d'abeille aluminium cellule 3–6 mm × 20 mm ou toile filtrante "
            "(perte ≪ 1 Pa), pour casser les courants du local sans recirculation dans l'enceinte",
        clearance_mm=30.0,
        note="à 30 mm du bord de la zone de travail (bande percée périphérique) ; "
             f"vitesse d'entraînement latérale estimée en bord de zone ≈ {v_entr*1e3:.1f} mm/s")
    # entraînement en bord de zone, à la pression de consigne de chaque masse
    entr = {}
    try:
        tab = load_json("setpoints.json")["table"]
        pts = [(r["mass_g"], r["ps_discrete_Pa"]) for r in tab if r["mass_g"] in (2.0, 5.0, 10.0)]
    except (FileNotFoundError, KeyError):
        pts = [(2.0, 46.0), (5.0, 101.0), (10.0, 192.0)]
    for m, ps in pts:
        UJ = float(q_free(ps, cfg)) / cfg.A * np.sqrt(phi)
        ve = ALPHA_ENTR * UJ
        entr[str(m)] = dict(ps_Pa=ps, U_momentum_m_s=UJ, v_entrainment_m_s=ve,
                            slope_urad=float(drag_slope_urad(ve, m)))
    res = dict(config=cfg, n_holes=N, open_ratio=phi, jets=jets, drafts=drafts,
               alloc_draft_urad=ALLOC_DRAFT_URAD, H_puck_mm=H_PUCK * 1e3, screen=screen,
               entrainment_at_setpoint=entr,
               entrainment_note="ordre de grandeur (α = 0,05) : écoulement d'entraînement horizontal près "
                                "du bord de la zone percée ; nul par symétrie au centre de la zone")
    save_json("jets.json", res)

    plt = setup_style()
    fig, axs = plt.subplots(1, 2, figsize=(11, 4.2))
    ax = axs[0]
    x = np.linspace(0, 40e-3, 200)
    for (tag, j), col in zip(jets.items(), SERIES):
        ax.plot(x * 1e3, 5.94 * x / j["Re"] * 1e3, color=col, label=f"laminaire, ps = {j['ps_Pa']:.0f} Pa "
                f"(Re = {j['Re']:.0f})")
    ax.plot(x * 1e3, 0.094 * x * 1e3, color=MUTED, ls="--", label="turbulent (borne haute)")
    ax.axhline(p / 2 * 1e3, color=INK2, ls=":", lw=0.8)
    ax.text(1, p / 2 * 1e3 * 1.05, "demi-pas : coalescence", fontsize=7.5, color=INK2)
    ax.set_xlabel("hauteur au-dessus de la plaque (mm)")
    ax.set_ylabel("demi-largeur du jet r½ (mm)")
    ax.set_title("Épanouissement des jets et coalescence")
    ax.legend(fontsize=7.5)
    ax = axs[1]
    for m, col in zip((2.0, 5.0, 10.0), SERIES):
        ax.loglog(vv * 1e3, drag_slope_urad(vv, m), color=col, label=f"{m:g} g")
    ax.axhline(ALLOC_DRAFT_URAD, color=INK2, ls=":", lw=0.8)
    ax.axhline(50, color=INK2, ls="--", lw=0.8)
    ax.text(1.2, 55, "budget 50 µrad", fontsize=7.5, color=INK2)
    ax.text(1.2, ALLOC_DRAFT_URAD * 1.1, "allocation 5 µrad", fontsize=7.5, color=INK2)
    ax.set_xlabel("vitesse du courant d'air horizontal (mm/s)")
    ax.set_ylabel("pente équivalente (µrad)")
    ax.set_title(f"Traînée d'un courant d'air sur le palet (Ø30 × {H_PUCK*1e3:.0f} mm)")
    ax.legend(fontsize=8)
    savefig(fig, "jets_coalescence_courants_air.png")
    for k, j in jets.items():
        print(k, {a: round(b, 4) for a, b in j.items()})
    print("courants d'air", drafts)
    print("entraînement de bord", entr)


if __name__ == "__main__":
    main()
