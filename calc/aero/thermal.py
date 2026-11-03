"""Thermique aéraulique : échauffement de l'air par le ventilateur et gradients dans la plaque.

1. Échauffement de l'air : ΔT = P_élec/(ρ c_p Q_ventilateur) (toute la puissance
   électrique finit en chaleur dans l'air, moteur dans la veine). Deux stratégies :
   (a) modulation de vitesse ; (b) vitesse constante + vanne de décharge en aval
   du ventilateur (la chaleur part en partie avec l'air déchargé).
2. Établissement thermique dans les perçages d'alimentation (Graetz) :
   L_th ≈ 0,05·Re·Pr·D ⇒ l'air prend la température de la plaque en quelques mm.
3. Modèle 1D transitoire dans l'épaisseur (méthode des lignes) :
     (1−f) ρ_s c_s ∂T/∂z… :  C ∂T/∂t = k_eff ∂²T/∂z² + ρ c_p u (T_a − T)/L_th
     ∂T_a/∂z = −(T_a − T)/L_th  (air montant, entrée en z = 0 à T_air)
   faces : convection h_top (dessus, vers le local), h_bot (dessous, plenum).
   Gradient stationnaire, puis réponse à un échelon de régime (2 g → 10 g).
4. Conversion en pente : courbure κ = α ΔT_épaisseur / e, pente au bord du carré
   de travail ≈ κ·L/2 (plaque libre de se courber).

Écrit results/thermal.json et une figure.
Lancement : ``python3 -m calc.aero.thermal`` (≈ 5 s).
"""
from __future__ import annotations

import numpy as np
from scipy.integrate import solve_ivp

from calc.aero.common import (RHO, CP_AIR, NU, PR_AIR, P, PERF_SQUARE, WORK_SQUARE, PLATE_T,
                              recommended_config, load_json, count_holes_square_zone,
                              setup_style, savefig, save_json, SERIES, INK2, MUTED)

PL = P["plate"]
K_AL = 117.0                       # W/(m·K), EN AW-5083 coulée (ordre de grandeur)
C_AL = 900.0                       # J/(kg·K)
RHO_AL = float(PL["rho"])
ALPHA_TH = float(PL["alpha_th"])
H_TOP = 8.0                        # W/(m²·K), convection naturelle + rayonnement (dessus)
H_BOT = 5.0                        # W/(m²·K), face inférieure (entre perçages)
ETA_FAN = 0.25                     # rendement global d'un petit centrifuge au point de travail
P_FAN_MIN_W = 4.6                  # 9BMC24P2G001 à 20 % PWM (0,19 A × 24 V, fiche)
P_FAN_CONST_W = 12.0               # stratégie « vitesse constante » (9BMC à n ≈ 0,55 : 74 W × n³)
GRAD_LIMIT_K = P["performance_targets"]["thermal_gradient_K"]     # 0,05 K


def fan_power(Q, dp):
    return max(Q * dp / ETA_FAN, P_FAN_MIN_W)


def porosity(cfg):
    return np.pi * cfg.D_cb**2 / 4 * cfg.density


def plate_1d(cfg, Q_of_t, Tair_of_t, t_end, N=60, T0=None):
    """Méthode des lignes ; renvoie t, z, T(z, t) (écarts à la température du local)."""
    e = PLATE_T
    f = porosity(cfg)
    keff = K_AL * (1 - f)
    Cv = (1 - f) * RHO_AL * C_AL
    z = (np.arange(N) + 0.5) * e / N
    dz = e / N
    A = PERF_SQUARE**2

    def Lth(Q):
        qh = Q / count_holes_square_zone(cfg)
        Vb = qh / (np.pi * cfg.D_cb**2 / 4)
        Re = Vb * cfg.D_cb / NU
        return max(0.05 * Re * PR_AIR * cfg.D_cb, 0.2 * dz)

    def rhs(t, T):
        Q = Q_of_t(t)
        u = Q / A
        Ta_in = Tair_of_t(t)
        L = Lth(Q)
        # température de l'air le long de z (intégration exacte cellule par cellule)
        Ta = np.empty(N)
        src = np.empty(N)
        ta = Ta_in
        for i in range(N):
            dec = np.exp(-dz / L)
            ta_out = T[i] + (ta - T[i]) * dec
            src[i] = RHO * CP_AIR * u * (ta - ta_out) / dz       # W/m³ cédé à la plaque
            Ta[i] = 0.5 * (ta + ta_out)
            ta = ta_out
        lap = np.empty(N)
        lap[1:-1] = (T[2:] - 2 * T[1:-1] + T[:-2]) / dz**2
        # bords : flux convectifs (demi-maille)
        qb = H_BOT * (Ta_in - T[0])
        qt = H_TOP * (0.0 - T[-1])
        lap[0] = (T[1] - T[0]) / dz**2 + qb / (keff * dz)
        lap[-1] = (T[-2] - T[-1]) / dz**2 + qt / (keff * dz)
        return (keff * lap + src) / Cv

    T0 = np.zeros(N) if T0 is None else T0
    sol = solve_ivp(rhs, (0, t_end), T0, method="BDF", rtol=1e-7, atol=1e-10,
                    t_eval=np.linspace(0, t_end, 400))
    return sol.t, z, sol.y


def main():
    cfg = recommended_config()
    sp = load_json("setpoints.json")
    tab = {r["mass_g"]: r for r in sp["table"]}
    env = sp["envelope"]
    # 1. échauffement de l'air
    cases = {}
    for m in (2.0, 5.0, 10.0):
        r = tab[m]
        Q = r["Q_total_m3h"] / 3600
        Pw = fan_power(Q, r["dp_fan_dirty_Pa"])
        cases[str(m)] = dict(Q_m3h=Q * 3600, dp_fan_Pa=r["dp_fan_dirty_Pa"], P_elec_W=Pw,
                             dT_air_speed_mod_K=Pw / (RHO * CP_AIR * Q))
    # stratégie b : vitesse constante, décharge ; débit ventilateur ≈ débit max + 20 %
    Qc = 1.2 * env["Q_max_m3h"] / 3600
    dT_const = P_FAN_CONST_W / (RHO * CP_AIR * Qc)
    # 2. établissement thermique dans les perçages
    Lth = {}
    for m in (2.0, 10.0):
        Q = tab[m]["Q_total_m3h"] / 3600
        qh = Q / count_holes_square_zone(cfg)
        Vb = qh / (np.pi * cfg.D_cb**2 / 4)
        Re = Vb * cfg.D_cb / NU
        Lth[str(m)] = dict(V_bore_m_s=Vb, Re_bore=Re, L_th_mm=0.05 * Re * PR_AIR * cfg.D_cb * 1e3)
    # 3. stationnaire (10 g, modulation de vitesse) et échelon 2 g → 10 g
    Q2, Q10 = tab[2.0]["Q_total_m3h"] / 3600, tab[10.0]["Q_total_m3h"] / 3600
    dT2 = cases["2.0"]["dT_air_speed_mod_K"]
    dT10 = cases["10.0"]["dT_air_speed_mod_K"]
    t_long = 6 * 3600.0
    t, z, Ts = plate_1d(cfg, lambda t: Q2, lambda t: dT2, t_long)
    T_init = Ts[:, -1]
    grad_ss2 = float(T_init[0] - T_init[-1])
    t, z, Tstep = plate_1d(cfg, lambda t: Q10, lambda t: dT10, t_long, T0=T_init)
    grad = Tstep[0] - Tstep[-1]
    Tmean = Tstep.mean(0)
    grad_ss10 = float(grad[-1])
    # échelon court : résolution fine des premières minutes
    t2, _, Tfast = plate_1d(cfg, lambda t: Q10, lambda t: dT10, 600.0, T0=T_init)
    grad_fast = Tfast[0] - Tfast[-1]
    # démarrage à froid (plaque à la température du local, air à +ΔT10) : cas le plus sévère
    t3, _, Tcold = plate_1d(cfg, lambda t: Q10, lambda t: dT10, 600.0)
    grad_cold = Tcold[0] - Tcold[-1]
    t4, _, Tcl = plate_1d(cfg, lambda t: Q10, lambda t: dT10, 4 * 3600.0)
    gmax = float(max(np.max(np.abs(grad_fast)), np.max(np.abs(grad_cold))))
    # constante de temps globale (63 % de la montée de la température moyenne, démarrage)
    dTm = Tcl.mean(0)
    tau = float(np.interp(0.632 * dTm[-1], dTm, t4))
    dTm = Tmean - Tmean[0]
    kappa = ALPHA_TH * gmax / PLATE_T
    slope_edge = kappa * WORK_SQUARE / 2
    res = dict(config=cfg, porosity=porosity(cfg), k_eff=K_AL * (1 - porosity(cfg)),
               h_top=H_TOP, h_bot=H_BOT, eta_fan=ETA_FAN,
               air_heating=cases, constant_speed=dict(Q_fan_m3h=Qc * 3600, P_W=P_FAN_CONST_W, dT_air_K=dT_const),
               thermal_entry=Lth,
               gradient_steady_2g_K=grad_ss2, gradient_steady_10g_K=grad_ss10,
               gradient_transient_max_K=gmax, gradient_limit_K=GRAD_LIMIT_K,
               plate_tau_s=tau, plate_tau_min=tau / 60,
               mean_T_change_step_2g_to_10g_K=float(dTm[-1]),
               gradient_cold_start_max_K=float(np.max(np.abs(grad_cold))),
               gradient_step_max_K=float(np.max(np.abs(grad_fast))),
               slope_from_transient_gradient_urad=slope_edge * 1e6)
    save_json("thermal.json", res)

    plt = setup_style()
    fig, axs = plt.subplots(1, 2, figsize=(11, 4.2))
    ax = axs[0]
    ax.plot(t2 / 60, grad_fast * 1e3, color=SERIES[0], label="échelon 2 g → 10 g")
    ax.plot(t3 / 60, grad_cold * 1e3, color=SERIES[2], label="démarrage à froid (10 g)")
    ax.axhline(GRAD_LIMIT_K * 1e3, color=INK2, ls="--", lw=0.8)
    ax.text(0.3, GRAD_LIMIT_K * 1e3 * 0.92, "limite 50 mK", fontsize=7.5, color=INK2)
    ax.set_xlabel("temps après l'échelon 2 g → 10 g (min)")
    ax.set_ylabel("ΔT dessous − dessus (mK)")
    ax.set_title("Gradient dans l'épaisseur (modulation de vitesse)")
    ax.legend(fontsize=8)
    ax = axs[1]
    ax.plot(t4 / 3600, Tcl.mean(0) * 1e3, color=SERIES[1], label="démarrage à froid (10 g)")
    ax.plot(t / 3600, Tmean * 1e3, color=SERIES[0], label="échelon 2 g → 10 g")
    ax.axhline(dT10 * 1e3, color=MUTED, ls=":", lw=0.8)
    ax.set_xlabel("temps (h)")
    ax.set_ylabel("écart à la température initiale du local (mK)")
    ax.set_title(f"Mise en température (τ ≈ {tau/60:.0f} min)")
    ax.legend(fontsize=8)
    savefig(fig, "thermique_plaque.png")
    print({k: {a: round(b, 3) for a, b in v.items()} for k, v in cases.items()})
    print("vitesse constante", res["constant_speed"], "L_th", Lth)
    print(f"gradient stationnaire 2 g {grad_ss2*1e3:.2f} mK, 10 g {grad_ss10*1e3:.2f} mK ; transitoire max "
          f"{gmax*1e3:.2f} mK ; τ = {tau/60:.0f} min ; pente {slope_edge*1e6:.2f} µrad")


if __name__ == "__main__":
    main()
