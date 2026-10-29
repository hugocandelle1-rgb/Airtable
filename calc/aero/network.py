"""Courbe réseau, chaîne aéraulique ventilateur → plaque et enveloppe du ventilateur.

Chaîne retenue (de l'amont vers l'aval) :
  1. caisson d'aspiration avec filtre plissé ISO 16890 ePM1 ≥ 55 % (face 287×287) ;
  2. buse d'entrée calibrée à profil arrondi (type ISO 5801), col Ø d_n, servant de
     débitmètre (Δp col / caisson) ;
  3. ventilateur centrifuge à vitesse variable (EC/PWM) ;
  4. adaptateur sortie rectangulaire → rond, puis diffuseur conique 2θ = 7° ;
  5. manchon souple anti-vibratile, conduit Ø D_d avec coude grand rayon ;
  6. entrée centrale par le fond du plenum, disque déflecteur (diffuseur radial) ;
  7. chambre de distribution, tôle perforée de distribution + nappe de média ;
  8. chambre de tranquillisation, plaque de travail perforée.

Toutes les pertes sont exprimées en fonction du débit Q (m³/s). La pression
totale que doit fournir le ventilateur est Δp_tF = ps + Σ pertes (le plenum est
au repos ; l'énergie cinétique des jets de la plaque est incluse dans la loi des
trous).

Lancement : ``python3 -m calc.aero.network`` (après setpoints.py).
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import brentq

from calc.aero.common import (RHO, MU, NU, P_ATM, P, PERF_SQUARE, recommended_config,
                              count_holes_square_zone, setup_style, savefig, save_json,
                              load_json, RES_DIR, SERIES, INK, INK2, MUTED, GRID)
from calc.aero.orifice import q_free, dp_hole

# ---------------------------------------------------------------------------
# Géométrie de la chaîne (mm sauf mention) — valeurs proposées pour la CAO
# ---------------------------------------------------------------------------
DESIGN = dict(
    filter_face_mm=(287.0, 287.0), filter_depth_mm=48.0,
    filter_dp_ref_Pa=120.0, filter_v_ref=2.7,      # perte initiale de référence (panneau ePM1 55 %)
    filter_dirty_factor=3.0,                         # fin de vie (colmatage)
    intake_box_mm=(320.0, 320.0, 220.0),             # caisson d'aspiration (l × p × h)
    nozzle_throat_mm=45.0, nozzle_alpha=0.98, nozzle_K=0.04,
    fan_inlet_mm=50.0,
    fan_outlet_mm=(50.0, 35.0),                      # sortie rectangulaire supposée (à adapter)
    adapter_round_mm=50.0, adapter_len_mm=60.0, adapter_K=0.05,
    diffuser_out_mm=80.0, diffuser_angle_deg=7.0, diffuser_eta=0.75,
    sleeve_len_mm=100.0, sleeve_K=0.15,
    duct_mm=80.0, duct_len_mm=400.0, duct_f=0.025, bend_K=0.20,
    inlet_K=1.5,                                     # sortie de conduit + retournement sous le déflecteur
    plenum_inner_mm=P["plenum"]["inner_square_mm"],
    plenum_height_mm=P["plenum"]["height_mm"],
    distribution_height_mm=62.0,
    deflector_d_mm=200.0, deflector_gap_mm=25.0,
    sheet_t_mm=1.0, sheet_hole_mm=2.0, sheet_pitch_mm=8.0,   # quinconce 60°
    media_dp_ref_Pa=3.0, media_v_ref=0.10,           # nappe polyester ISO coarse 10 mm (estimation)
    settling_height_mm=P["plenum"]["settling_height_mm"],
    seam_len_m=4.0, seam_gap_um=50.0, seam_width_mm=10.0,
)


def sheet_open_ratio(D=DESIGN):
    """Taux d'ouverture d'une tôle à trous ronds en quinconce 60°."""
    return np.pi / (2 * np.sqrt(3)) * (D["sheet_hole_mm"] / D["sheet_pitch_mm"]) ** 2


def zeta_perforated(beta):
    """Coefficient de perte d'une tôle perforée mince à arêtes vives (Idelchik,
    diagramme 8-1), rapporté à la vitesse d'approche, régime turbulent."""
    return (0.707 * np.sqrt(1 - beta) + 1 - beta) ** 2 / beta**2


def _A(dmm):
    return np.pi * (dmm * 1e-3) ** 2 / 4


def chain_losses(Q, D=DESIGN, dirty=False):
    """Pertes de charge (Pa) de chaque élément pour un débit Q (m³/s)."""
    Q = float(Q)
    out = {}
    fa = D["filter_face_mm"][0] * D["filter_face_mm"][1] * 1e-6
    vf = Q / fa
    out["filtre d'aspiration"] = D["filter_dp_ref_Pa"] * vf / D["filter_v_ref"] * (
        D["filter_dirty_factor"] if dirty else 1.0)
    qn = 0.5 * RHO * (Q / _A(D["nozzle_throat_mm"])) ** 2
    out["buse d'entrée"] = D["nozzle_K"] * qn + (1 - _A(D["nozzle_throat_mm"]) / _A(D["fan_inlet_mm"])) ** 2 * qn
    ao = D["fan_outlet_mm"][0] * D["fan_outlet_mm"][1] * 1e-6
    q_out = 0.5 * RHO * (Q / ao) ** 2
    out["adaptateur rect.→rond"] = D["adapter_K"] * q_out
    q1 = 0.5 * RHO * (Q / _A(D["adapter_round_mm"])) ** 2
    AR = _A(D["diffuser_out_mm"]) / _A(D["adapter_round_mm"])
    out["diffuseur conique"] = (1 - D["diffuser_eta"]) * (1 - 1 / AR**2) * q1
    qd = 0.5 * RHO * (Q / _A(D["duct_mm"])) ** 2
    out["manchon souple"] = D["sleeve_K"] * qd
    out["conduit + coude"] = (D["duct_f"] * D["duct_len_mm"] / D["duct_mm"] + D["bend_K"]) * qd
    out["entrée plenum + déflecteur"] = D["inlet_K"] * qd
    A_pl = (D["plenum_inner_mm"] * 1e-3) ** 2
    v0 = Q / A_pl
    beta = sheet_open_ratio(D)
    n_sheet = A_pl / (np.sqrt(3) / 2 * (D["sheet_pitch_mm"] * 1e-3) ** 2)
    qh = Q / n_sheet
    sampson = 24 * MU * qh / (D["sheet_hole_mm"] * 1e-3) ** 3
    out["tôle de distribution"] = zeta_perforated(beta) * 0.5 * RHO * v0**2 + sampson
    out["nappe de média"] = D["media_dp_ref_Pa"] * v0 / D["media_v_ref"]
    return out


def leak_flow(ps, D=DESIGN):
    """Fuites des joints (fente laminaire équivalente)."""
    h = D["seam_gap_um"] * 1e-6
    return h**3 * D["seam_len_m"] * ps / (12 * MU * D["seam_width_mm"] * 1e-3)


def total_flow(ps, cfg=None, n_holes=None, leak=True):
    """Débit total (m³/s) : trous de la zone percée (libres) + fuites."""
    cfg = cfg or recommended_config()
    n = n_holes or count_holes_square_zone(cfg)
    Q = n * float(q_free(ps, cfg))
    return Q + (leak_flow(ps) if leak else 0.0)


def fan_total_pressure(ps, Q, dirty=False):
    return ps + sum(chain_losses(Q, dirty=dirty).values())


def fan_curve(Q, n_rel, dp_shut, Q_free):
    """Courbe générique d'un centrifuge à aubes arrière : Δp = n²·Δp0·(1 − (Q/(n·Qf))²)."""
    return dp_shut * n_rel**2 * (1 - (Q / (Q_free * n_rel)) ** 2)


def main():
    plt = setup_style()
    cfg = recommended_config()
    N = count_holes_square_zone(cfg)
    try:
        sp = load_json("setpoints.json")
        ps_lo = sp["envelope"]["ps_min_Pa"]
        ps_hi = sp["envelope"]["ps_max_Pa"]
    except (FileNotFoundError, KeyError):
        # setpoints.json absent ou d'un autre format : bornes provisoires
        # (0,9·ps(2 g) et 1,1·ps(10 g) du modèle axisymétrique à h = 120 µm)
        ps_lo, ps_hi = 0.9 * 50.0, 1.1 * 330.0
    ps = np.linspace(5, 1.4 * ps_hi, 200)
    Qh = np.array([N * float(q_free(p, cfg)) for p in ps])
    Ql = np.array([leak_flow(p) for p in ps])
    Qt = Qh + Ql
    dpt = np.array([fan_total_pressure(p, q) for p, q in zip(ps, Qt)])
    dpt_dirty = np.array([fan_total_pressure(p, q, dirty=True) for p, q in zip(ps, Qt)])
    # exposant local de la courbe réseau Δp ∝ Q^k
    k_sys = np.gradient(np.log(dpt), np.log(Qt))

    Q_lo = total_flow(ps_lo, cfg, N)
    Q_hi = total_flow(ps_hi, cfg, N)
    dp_lo = fan_total_pressure(ps_lo, Q_lo)
    dp_hi = fan_total_pressure(ps_hi, Q_hi, dirty=True)
    # marges : loi d'orifice (±12 % sur q à Δp donné, cf. orifice.json), fuites, vieillissement
    mQ, mP = 1.15, 1.15
    spec_max = (Q_hi * mQ, dp_hi * mP)
    spec_min = (Q_lo / mQ, dp_lo / mP)
    # vitesse relative requise sur un ventilateur générique dimensionné pour que
    # le point max spécifié soit à ~70 % de la pression à débit nul
    dp_shut = spec_max[1] / 0.7 / (1 - 0.3)        # choisi pour passer par spec_max à n = 1
    Qf = spec_max[0] / np.sqrt(1 - spec_max[1] / dp_shut)

    def n_req(Q, dp):
        return brentq(lambda n: fan_curve(Q, n, dp_shut, Qf) - dp, 1e-3, 1.5)

    n_hi = n_req(Q_hi, fan_total_pressure(ps_hi, Q_hi))
    n_hi_d = n_req(Q_hi, dp_hi)
    n_lo = n_req(Q_lo, dp_lo)
    speed_ratio = n_hi_d / n_lo
    speed_ratio_quadratic = np.sqrt(dp_hi / dp_lo)

    # plenum : constante de temps pneumatique
    V_pl = (DESIGN["plenum_inner_mm"] * 1e-3) ** 2 * DESIGN["plenum_height_mm"] * 1e-3 + \
        _A(DESIGN["duct_mm"]) * DESIGN["duct_len_mm"] * 1e-3
    Cpn = V_pl / (1.4 * P_ATM)
    dQdp_hi = (total_flow(ps_hi * 1.01, cfg, N) - total_flow(ps_hi * 0.99, cfg, N)) / (0.02 * ps_hi)
    dQdp_lo = (total_flow(ps_lo * 1.01, cfg, N) - total_flow(ps_lo * 0.99, cfg, N)) / (0.02 * ps_lo)
    tau_hi, tau_lo = Cpn / dQdp_hi, Cpn / dQdp_lo

    # buse débitmétrique
    An = _A(DESIGN["nozzle_throat_mm"])
    dpn = lambda Q: 0.5 * RHO * (Q / (DESIGN["nozzle_alpha"] * An)) ** 2
    Re_n = lambda Q: Q / An * DESIGN["nozzle_throat_mm"] * 1e-3 / NU

    # uniformité de la pression statique sous la plaque (au point le plus défavorable : ps_lo)
    A_pl = (DESIGN["plenum_inner_mm"] * 1e-3) ** 2
    beta = sheet_open_ratio(DESIGN)
    def uniformity(Q, psx):
        v0 = Q / A_pl
        vj = v0 / beta
        dj = DESIGN["sheet_hole_mm"] * 1e-3
        x = DESIGN["settling_height_mm"] * 1e-3
        Kj = vj**2 * np.pi * dj**2 / 4
        uc_lam = 3 * Kj / (8 * np.pi * NU * x)                   # jet laminaire (Schlichting)
        uc_turb = 6.0 * vj * dj / x                              # jet turbulent
        u_wall = Q / (2 * np.pi * 0.5 * DESIGN["plenum_inner_mm"] * 1e-3
                      * DESIGN["deflector_gap_mm"] * 1e-3 * 2)   # jet radial arrivant aux parois
        dyn_up = 0.5 * RHO * u_wall**2
        dp_sheet = chain_losses(Q)["tôle de distribution"]
        return dict(
            v_settling=v0, dyn_settling_rel=0.5 * RHO * v0**2 / psx,
            v_sheet_jet=vj, Re_sheet_jet=vj * dj / NU,
            sheet_jet_residual_rel_laminar=0.5 * RHO * min(uc_lam, vj) ** 2 / psx,
            sheet_jet_residual_rel_turbulent=0.5 * RHO * min(uc_turb, vj) ** 2 / psx,
            ratio_sheet_dp_over_upstream_dyn=dp_sheet / dyn_up,
            sheet_flow_nonuniformity=0.5 * dyn_up / (dp_sheet + chain_losses(Q)["nappe de média"]),
            ratio_orifice_dp_over_plenum_dyn=psx / (0.5 * RHO * v0**2),
            ratio_orifice_dp_over_duct_dyn=psx / (0.5 * RHO * (Q / _A(DESIGN["duct_mm"])) ** 2),
            estimated_nonuniformity_pct=100 * (0.5 * RHO * v0**2
                                               + 0.5 * RHO * min(uc_lam, vj) ** 2) / psx)

    U_lo = uniformity(Q_lo, ps_lo)
    U_hi = uniformity(Q_hi, ps_hi)

    # diffuseur : contrôle géométrique
    d1, d2 = DESIGN["adapter_round_mm"], DESIGN["diffuser_out_mm"]
    th = np.radians(DESIGN["diffuser_angle_deg"] / 2)
    L_diff = (d2 - d1) / 2 / np.tan(th)
    diff = dict(D_in_mm=d1, D_out_mm=d2, AR=(d2 / d1) ** 2, total_angle_deg=DESIGN["diffuser_angle_deg"],
                length_mm=L_diff, L_over_R1=L_diff / (d1 / 2),
                Re_in_at_Qmax=Q_hi / _A(d1) * d1 * 1e-3 / NU,
                criterion="2θ ≤ 8° et L/R1 ≈ 5–20 : sous la ligne de premier décrochement "
                          "(Sovran & Klomp 1967) ; Cp attendu ≈ η·(1 − 1/AR²)")
    # disque déflecteur : diffuseur radial
    defl = dict(D_mm=DESIGN["deflector_d_mm"], gap_mm=DESIGN["deflector_gap_mm"],
                area_ratio_entry=np.pi * DESIGN["duct_mm"] * DESIGN["deflector_gap_mm"] / (np.pi * DESIGN["duct_mm"]**2 / 4),
                v_edge_at_Qmax=Q_hi / (np.pi * DESIGN["deflector_d_mm"] * 1e-3 * DESIGN["deflector_gap_mm"] * 1e-3))

    losses_hi = chain_losses(Q_hi, dirty=True)
    losses_hi_clean = chain_losses(Q_hi)
    res = dict(
        config=cfg, n_holes_zone=N, ps_range_Pa=[ps_lo, ps_hi],
        operating_min=dict(ps=ps_lo, Q_m3s=Q_lo, Q_m3h=Q_lo * 3600, dp_fan_total=dp_lo,
                           losses=chain_losses(Q_lo), leak_m3h=leak_flow(ps_lo) * 3600),
        operating_max=dict(ps=ps_hi, Q_m3s=Q_hi, Q_m3h=Q_hi * 3600, dp_fan_total_dirty=dp_hi,
                           dp_fan_total_clean=fan_total_pressure(ps_hi, Q_hi),
                           losses_dirty=losses_hi, losses_clean=losses_hi_clean,
                           leak_m3h=leak_flow(ps_hi) * 3600),
        fan_spec=dict(margin_Q=mQ, margin_dp=mP,
                      max_point=dict(Q_m3h=spec_max[0] * 3600, dp_total_Pa=spec_max[1]),
                      min_point=dict(Q_m3h=spec_min[0] * 3600, dp_total_Pa=spec_min[1]),
                      shaft_power_max_W=spec_max[0] * spec_max[1] / 0.45,
                      air_power_max_W=spec_max[0] * spec_max[1],
                      specific_speed_at_max=_specific_speed(spec_max[0], spec_max[1]),
                      speed_ratio_generic_fan=speed_ratio,
                      speed_ratio_quadratic_estimate=speed_ratio_quadratic,
                      n_rel_min=n_lo, n_rel_max_clean=n_hi, n_rel_max_dirty=n_hi_d,
                      system_exponent_range=[float(np.interp(Q_lo, Qt, k_sys)), float(np.interp(Q_hi, Qt, k_sys))]),
        plenum=dict(volume_m3=V_pl, tau_s_at_ps_max=tau_hi, tau_s_at_ps_min=tau_lo,
                    plate_pressure_load_N_at_ps_max=ps_hi * A_pl,
                    uniformity_at_ps_min=U_lo, uniformity_at_ps_max=U_hi),
        nozzle=dict(throat_mm=DESIGN["nozzle_throat_mm"], dp_at_Qmin_Pa=dpn(Q_lo), dp_at_Qmax_Pa=dpn(Q_hi),
                    Re_at_Qmin=Re_n(Q_lo), Re_at_Qmax=Re_n(Q_hi)),
        diffuser=diff, deflector=defl, sheet=dict(open_ratio=beta, zeta=zeta_perforated(beta)),
        design=DESIGN,
    )
    save_json("network.json", res)

    # --- figures : courbe réseau et enveloppe
    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    ax.plot(Qt * 3600, ps, color=SERIES[0], label="ps plenum (trous + fuites)")
    ax.plot(Qt * 3600, dpt, color=SERIES[1], label="Δp total ventilateur (filtre neuf)")
    ax.plot(Qt * 3600, dpt_dirty, color=SERIES[1], ls="--", label="Δp total ventilateur (filtre colmaté)")
    for nr in (0.3, 0.5, 0.7, 0.85, 1.0):
        qq = np.linspace(0, Qf * nr, 100)
        ax.plot(qq * 3600, fan_curve(qq, nr, dp_shut, Qf), color=MUTED, lw=0.8)
        ax.text(Qf * nr * 3600 * 0.55, fan_curve(Qf * nr * 0.55, nr, dp_shut, Qf), f"n={nr:.2f}",
                fontsize=7, color=MUTED)
    ax.scatter([spec_min[0] * 3600, spec_max[0] * 3600], [spec_min[1], spec_max[1]], color=INK, zorder=5,
               s=30)
    ax.annotate("point max spécifié", (spec_max[0] * 3600, spec_max[1]), xytext=(-110, 12),
                textcoords="offset points", fontsize=8)
    ax.annotate("point min", (spec_min[0] * 3600, spec_min[1]), xytext=(8, -14),
                textcoords="offset points", fontsize=8)
    ax.axhspan(ps_lo, ps_hi, color="#f0efec", zorder=0)
    ax.set_xlim(0, Qf * 3600 * 1.05)
    ax.set_ylim(0, dp_shut * 1.05)
    ax.set_xlabel("débit Q (m³/h)")
    ax.set_ylabel("pression (Pa)")
    ax.set_title("Courbe réseau et enveloppe du ventilateur (courbes grises : centrifuge générique)")
    ax.legend(fontsize=8, loc="upper left")
    savefig(fig, "reseau_courbe_ventilateur.png")

    fig, ax = plt.subplots(figsize=(7.5, 4))
    keys = list(losses_hi.keys())
    y = np.arange(len(keys))
    ax.barh(y + 0.2, [losses_hi_clean[k] for k in keys], height=0.38, color=SERIES[0], label="filtre neuf")
    ax.barh(y - 0.2, [losses_hi[k] for k in keys], height=0.38, color=SERIES[1], label="filtre colmaté")
    ax.set_yticks(y, keys)
    ax.invert_yaxis()
    ax.set_xlabel("perte de charge (Pa)")
    ax.set_title(f"Pertes de la chaîne au point max (Q = {Q_hi*3600:.1f} m³/h, ps = {ps_hi:.0f} Pa)")
    ax.legend()
    savefig(fig, "reseau_pertes_chaine.png")

    _schematic(plt)
    print(f"N trous = {N} ; ps {ps_lo:.0f}–{ps_hi:.0f} Pa ; Q {Q_lo*3600:.1f}–{Q_hi*3600:.1f} m3/h ; "
          f"Δp_tF {dp_lo:.0f}–{dp_hi:.0f} Pa")
    print("spec max", spec_max[0] * 3600, spec_max[1], "spec min", spec_min[0] * 3600, spec_min[1])
    print("rapport de vitesse", speed_ratio, "(quadratique", speed_ratio_quadratic, ")")
    print("tau plenum", tau_lo, tau_hi, "buse", dpn(Q_lo), dpn(Q_hi))
    print("uniformité", U_lo["estimated_nonuniformity_pct"], U_hi["estimated_nonuniformity_pct"],
          "ratio tôle", U_lo["ratio_sheet_dp_over_upstream_dyn"])
    print("diffuseur", diff)


def _specific_speed(Q, dp):
    """Vitesse spécifique Ω_s = ω√Q/(Δp/ρ)^{3/4} à 3000 tr/min (indicatif)."""
    w = 3000 * 2 * np.pi / 60
    return w * np.sqrt(Q) / (dp / RHO) ** 0.75


def _schematic(plt):
    """Coupe schématique de la chaîne aéraulique (cotes principales, mm)."""
    from matplotlib.patches import Rectangle, Polygon, Circle
    D = DESIGN
    fig, ax = plt.subplots(figsize=(11, 5.2))
    ax.set_aspect("equal")
    ax.axis("off")
    W = D["plenum_inner_mm"]
    H = D["plenum_height_mm"]
    x0 = 300
    # plenum
    ax.add_patch(Rectangle((x0, 0), W, H, fill=False, ec=INK, lw=1.2))
    hd = D["distribution_height_mm"]
    ax.plot([x0, x0 + W], [hd, hd], color=SERIES[0], lw=1.5, ls=(0, (2, 1)))
    ax.text(x0 + W + 8, hd, f"tôle perforée Ø{D['sheet_hole_mm']:.0f} pas {D['sheet_pitch_mm']:.0f} "
            f"(β={100*sheet_open_ratio():.1f} %) + nappe média", fontsize=7.5, va="center")
    ax.add_patch(Rectangle((x0 - 40, H), W + 80, 25, fc="#e1e0d9", ec=INK, lw=1))
    ax.text(x0 + W + 48, H + 12, "plaque perforée ép. 25", fontsize=7.5, va="center")
    ax.text(x0 + W + 8, (hd + H) / 2, f"tranquillisation {D['settling_height_mm']:.0f}", fontsize=7.5)
    ax.text(x0 + W + 8, hd / 2, f"distribution {hd:.0f}", fontsize=7.5)
    # déflecteur
    xc = x0 + W / 2
    ax.plot([xc - D["deflector_d_mm"] / 2, xc + D["deflector_d_mm"] / 2],
            [D["deflector_gap_mm"]] * 2, color=SERIES[1], lw=2.5)
    ax.text(xc + D["deflector_d_mm"] / 2 + 5, D["deflector_gap_mm"] + 4,
            f"déflecteur Ø{D['deflector_d_mm']:.0f} à {D['deflector_gap_mm']:.0f} du fond", fontsize=7.5)
    # conduit d'entrée par le fond
    dd = D["duct_mm"]
    ax.add_patch(Rectangle((xc - dd / 2, -120), dd, 120, fill=False, ec=INK, lw=1))
    ax.text(xc + dd / 2 + 5, -60, f"conduit Ø{dd:.0f}", fontsize=7.5)
    # coude + diffuseur horizontal
    ax.add_patch(Rectangle((xc - 300, -120 - dd), 300 - dd / 2, dd, fill=False, ec=INK, lw=1))
    Ld = (D["diffuser_out_mm"] - D["adapter_round_mm"]) / 2 / np.tan(np.radians(D["diffuser_angle_deg"] / 2))
    xd = xc - 300
    y_mid = -120 - dd / 2
    ax.add_patch(Polygon([[xd - Ld, y_mid - D["adapter_round_mm"] / 2], [xd, y_mid - dd / 2],
                          [xd, y_mid + dd / 2], [xd - Ld, y_mid + D["adapter_round_mm"] / 2]],
                         fill=False, ec=SERIES[2], lw=1.2))
    ax.text(xd - Ld, y_mid + 50, f"diffuseur 2θ={D['diffuser_angle_deg']:.0f}°, Ø{D['adapter_round_mm']:.0f}→Ø{D['diffuser_out_mm']:.0f}, "
            f"L≈{Ld:.0f}", fontsize=7.5)
    ax.text(xc - 230, y_mid - 55, f"manchon souple L{D['sleeve_len_mm']:.0f}", fontsize=7.5)
    # ventilateur + buse + caisson
    xf = xd - Ld - 60
    ax.add_patch(Circle((xf, y_mid), 55, fill=False, ec=INK, lw=1.2))
    ax.text(xf - 40, y_mid - 75, "ventilateur centrifuge EC", fontsize=7.5)
    bx = D["intake_box_mm"]
    ax.add_patch(Rectangle((xf - 60 - bx[0], y_mid - bx[2] / 2), bx[0], bx[2], fill=False, ec=INK, lw=1))
    ax.add_patch(Polygon([[xf - 60, y_mid - 22], [xf - 100, y_mid - 45], [xf - 100, y_mid + 45],
                          [xf - 60, y_mid + 22]], fill=False, ec=SERIES[4], lw=1.2))
    ax.text(xf - 60 - bx[0], y_mid + bx[2] / 2 + 8, f"caisson d'aspiration {bx[0]:.0f}×{bx[1]:.0f}×{bx[2]:.0f}, "
            f"buse col Ø{D['nozzle_throat_mm']:.0f}", fontsize=7.5)
    ax.plot([xf - 60 - bx[0]] * 2, [y_mid - 100, y_mid + 100], color=SERIES[5], lw=3)
    ax.text(xf - 70 - bx[0], y_mid - 125, "filtre ePM1 287×287", fontsize=7.5, ha="left")
    ax.annotate("", xy=(xc, D["deflector_gap_mm"] - 2), xytext=(xc, -100),
                arrowprops=dict(arrowstyle="->", color=SERIES[0]))
    ax.set_xlim(xf - 80 - bx[0], x0 + W + 330)
    ax.set_ylim(-280, H + 60)
    ax.set_title("Chaîne aéraulique — coupe schématique (non à l'échelle des épaisseurs, cotes en mm)")
    savefig(fig, "chaine_aeraulique_schema.png")


if __name__ == "__main__":
    main()
