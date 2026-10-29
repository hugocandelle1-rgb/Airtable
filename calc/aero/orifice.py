"""Loi débit-pression d'un trou de la plaque (orifice calibré court + perçage borgne).

Modèles d'orifice (Δp entre l'amont stagnant et la sortie en jet libre) :

* ``lichtarowicz`` (référence) — corrélation expérimentale pour tubes courts à
  entrée vive, 2 ≤ L/d ≤ 10, Re ≈ 10…2·10⁴ (Lichtarowicz, Duggins & Markland,
  J. Mech. Eng. Sci. 7(2), 1965) :
      1/Cd = 1/Cd_u + 20 (1 + 2,25 L/d) / Re_th ,  Cd_u = 0,827 − 0,0085 L/d
  avec Re_th = d·√(2Δp/ρ)/ν (Reynolds « idéal ») et q = Cd·A·√(2Δp/ρ).
  À bas Re, la loi tend vers une loi linéaire (laminaire) ; à haut Re, Cd → Cd_u.
* ``shah_sharp`` / ``shah_cone`` — modèle analytique : énergie cinétique de sortie
  (1) + perte d'entrée K_in (0,5 arête vive ; 0,25 pointe de foret 118°) +
  frottement apparent en écoulement laminaire en développement (Shah 1978,
  J. Fluids Eng. 100, f_app·Re = 3,44/√x⁺ + …, x⁺ = L/(d·Re)).
* ``coord`` — modèle de la pré-étude : R_lam·q + 1,5·ρ/2·(q/A)².

S'ajoutent en série : le perçage borgne Ø D_cb (Poiseuille + entrée), la perte
« rideau » à la sortie sous un palet (film), et optionnellement une bavure.

Lancement : ``python3 -m calc.aero.orifice`` (figures + results/orifice.json).
"""
from __future__ import annotations

import numpy as np

from calc.aero.common import (HoleConfig, RHO, MU, NU, P_ATM, baseline_config,
                              setup_style, savefig, save_json, SERIES, INK2)

CC_SHARP = 0.62      # coefficient de contraction d'une arête vive (Borda/Idelchik)


# ---------------------------------------------------------------------------
# Modèles d'orifice
# ---------------------------------------------------------------------------
def _lichtarowicz_coeffs(cfg: HoleConfig, L: float | None = None):
    L = cfg.L if L is None else L
    ld = L / cfg.d
    cdu = 0.827 - 0.0085 * ld
    if cfg.cone_inlet:
        # entrée conique (pointe 118° du perçage Ø D_cb) : ζ_entrée ≈ 0,5 → 0,3
        ku = 1.0 / cdu**2 - 0.2
        cdu = 1.0 / np.sqrt(ku)
    a = 1.0 / cdu
    b = 20.0 * (1.0 + 2.25 * ld)
    return a, b


def dp_orifice(q, cfg: HoleConfig, L: float | None = None):
    """Δp (Pa) de l'orifice calibré pour un débit volumique q (m³/s), vectorisé."""
    q = np.asarray(q, dtype=float)
    L = cfg.L if L is None else L
    A = cfg.A
    V = np.abs(q) / A
    s = np.sign(q)
    if cfg.model == "lichtarowicz":
        a, b = _lichtarowicz_coeffs(cfg, L)
        c = b * NU / cfg.d
        vth = 0.5 * (a * V + np.sqrt((a * V) ** 2 + 4.0 * c * V))
        return s * 0.5 * RHO * vth**2
    if cfg.model in ("shah_sharp", "shah_cone"):
        k_in = 0.5 if cfg.model == "shah_sharp" else 0.25
        Re = np.maximum(V * cfg.d / NU, 1e-9)
        xp = (L / cfg.d) / Re
        fre = 3.44 / np.sqrt(xp) + (1.25 / (4 * xp) + 16 - 3.44 / np.sqrt(xp)) / (
            1 + 0.00021 / xp**2)
        k_fric = 4.0 * fre / Re * (L / cfg.d)
        return s * 0.5 * RHO * V**2 * (1.0 + k_in + k_fric)
    if cfg.model == "coord":
        r_lam = 128 * MU * L / (np.pi * cfg.d**4)
        return s * (r_lam * np.abs(q) + 1.5 * 0.5 * RHO * V**2)
    raise ValueError(cfg.model)


def dp_bore(q, cfg: HoleConfig):
    """Perçage borgne d'alimentation Ø D_cb : Poiseuille + entrée vive (ζ=0,5)."""
    q = np.asarray(q, dtype=float)
    Ab = np.pi * cfg.D_cb**2 / 4
    vb = q / Ab
    return 128 * MU * cfg.L_bore * q / (np.pi * cfg.D_cb**4) + 0.5 * 0.5 * RHO * vb * np.abs(vb)


def zeta_burr(b: float) -> float:
    """Perte supplémentaire (rapportée à ρV²/2 dans l'orifice) d'une bavure
    obstruant la fraction b de la section d'entrée (contraction vive puis
    ré-expansion ; référence : arête vive déjà comptée)."""
    return (1 / (CC_SHARP * (1 - b)) - 1) ** 2 - (1 / CC_SHARP - 1) ** 2


def dp_hole(q, cfg: HoleConfig, burr: float = 0.0, chamfer: float = 0.0):
    """Δp total plenum → sortie libre d'un trou (Pa).

    burr    : fraction de section obstruée par une bavure en entrée d'orifice
    chamfer : profondeur (m) d'un chanfrein 45° en sortie (raccourcit l'orifice)
    """
    q = np.asarray(q, dtype=float)
    dp = dp_orifice(q, cfg, L=cfg.L - chamfer) + dp_bore(q, cfg)
    if burr > 0:
        V = q / cfg.A
        dp = dp + zeta_burr(burr) * 0.5 * RHO * V * np.abs(V)
    return dp


def ddp_hole(q, cfg: HoleConfig, **kw):
    q = np.asarray(q, dtype=float)
    e = 1e-5 * np.maximum(np.abs(q), 1e-10)
    return (dp_hole(q + e, cfg, **kw) - dp_hole(q - e, cfg, **kw)) / (2 * e)


def dp_curtain(q, h, cfg: HoleConfig):
    """Perte « rideau » à la sortie d'un trou couvert par le palet :
    K_c·ρ/2·(q/(π d h))² (section de passage cylindrique π·d·h)."""
    vc = np.asarray(q) / (np.pi * cfg.d * np.asarray(h))
    return cfg.K_c * 0.5 * RHO * vc * np.abs(vc)


def ddp_curtain_dq(q, h, cfg: HoleConfig):
    return cfg.K_c * RHO * np.abs(q) / (np.pi * cfg.d * np.asarray(h)) ** 2


def ddp_curtain_dh(q, h, cfg: HoleConfig):
    return -2.0 * dp_curtain(q, h, cfg) / np.asarray(h)


def invert(fun, dfun, target, q0=None, iters=60):
    """Résout fun(q) = target (fun croissante convexe, vectorisé) par Newton."""
    target = np.asarray(target, dtype=float)
    if q0 is None:
        s0 = dfun(np.full_like(target, 1e-12))
        q = np.maximum(target, 0) / s0
    else:
        q = np.array(q0, dtype=float)
    for _ in range(iters):
        f = fun(q) - target
        dq = f / dfun(q)
        q = np.maximum(q - dq, 0.0)
        if np.all(np.abs(dq) <= 1e-12 * np.maximum(q, 1e-15)):
            break
    return q


def q_free(dp, cfg: HoleConfig, **kw):
    """Débit (m³/s) d'un trou débouchant à l'air libre sous Δp (Pa)."""
    return invert(lambda q: dp_hole(q, cfg, **kw), lambda q: ddp_hole(q, cfg, **kw), dp)


def jet_velocity(dp, cfg: HoleConfig):
    return q_free(dp, cfg) / cfg.A


def discharge_coefficient(dp, cfg: HoleConfig):
    dp = np.asarray(dp, dtype=float)
    return q_free(dp, cfg) / (cfg.A * np.sqrt(2 * dp / RHO))


# ---------------------------------------------------------------------------
# Script principal
# ---------------------------------------------------------------------------
def main():
    plt = setup_style()
    cfg = baseline_config()
    dps = np.linspace(1, 500, 300)
    models = [("lichtarowicz", "Lichtarowicz 1965 (référence, arête vive)"),
              ("shah_sharp", "Shah 1978 + ζ_entrée 0,5"),
              ("shah_cone", "Shah 1978 + ζ_entrée 0,25"),
              ("coord", "Pré-étude : R_lam·q + 1,5·ρV²/2 (L = 1,0)")]
    res = {"config": cfg, "models": {}}

    fig, axs = plt.subplots(1, 2, figsize=(11, 4.2))
    ax = axs[0]
    for (m, lab), col in zip(models, SERIES):
        c = cfg.with_(model=m)
        q = q_free(dps, c)
        ax.plot(dps, q * 1e6, color=col, label=lab)
        pts = np.array([30, 50, 100, 150, 250, 400.0])
        qq = q_free(pts, c)
        res["models"][m] = {
            "dp_Pa": pts, "q_m3s": qq, "V_ms": qq / c.A,
            "Re": qq / c.A * c.d / NU,
            "Cd": qq / (c.A * np.sqrt(2 * pts / RHO))}
    c1 = cfg.with_(cone_inlet=True)
    ax.plot(dps, q_free(dps, c1) * 1e6, color=SERIES[4], ls="--",
            label="Lichtarowicz + entrée conique (pointe 118°)")
    ax.set_xlabel("Δp plenum → air libre (Pa)")
    ax.set_ylabel("q (10⁻⁶ m³/s par trou)")
    ax.set_title(f"Loi débit-pression d'un trou d={cfg.d*1e3:.2f} mm, L={cfg.L*1e3:.1f} mm")
    ax.legend(fontsize=8)

    ax = axs[1]
    Re = np.logspace(1.6, 3.5, 200)
    for ld, col in zip([1, 2, 3, 4, 5], SERIES):
        c = cfg.with_(L=ld * cfg.d)
        a, b = _lichtarowicz_coeffs(c)
        cd = 1 / (a + b / Re)
        ax.semilogx(Re, cd, color=col, label=f"L/d = {ld}")
    ax.axvspan(100, 2000, color="#f0efec", zorder=0)
    ax.set_xlabel("Re_th = d·√(2Δp/ρ)/ν")
    ax.set_ylabel("Cd")
    ax.set_title("Coefficient de décharge (Lichtarowicz, entrée vive)")
    ax.legend(fontsize=8, loc="lower right")
    savefig(fig, "orifice_loi_debit_pression.png")

    # --- Sensibilités à 250 Pa et 50 Pa
    sens = {}
    for dp0 in (50.0, 250.0):
        q0 = float(q_free(dp0, cfg))
        cases = {
            "d +0,01 mm": float(q_free(dp0, cfg.with_(d=cfg.d + 1e-5))),
            "d −0,01 mm": float(q_free(dp0, cfg.with_(d=cfg.d - 1e-5))),
            "L +0,05 mm": float(q_free(dp0, cfg.with_(L=cfg.L + 5e-5))),
            "L −0,05 mm": float(q_free(dp0, cfg.with_(L=cfg.L - 5e-5))),
            "entrée conique 118°": float(q_free(dp0, cfg.with_(cone_inlet=True))),
            "bavure 10 % section": float(q_free(dp0, cfg, burr=0.10)),
            "bavure 25 % section": float(q_free(dp0, cfg, burr=0.25)),
            "chanfrein sortie 0,05": float(q_free(dp0, cfg, chamfer=5e-5)),
            "chanfrein sortie 0,15": float(q_free(dp0, cfg, chamfer=1.5e-4)),
            "lamage Ø1,5 (vs Ø2)": float(q_free(dp0, cfg.with_(D_cb=1.5e-3))),
            "lamage Ø3,0 (vs Ø2)": float(q_free(dp0, cfg.with_(D_cb=3.0e-3))),
        }
        sens[f"{dp0:.0f}Pa"] = {"q_ref": q0,
                                "rel": {k: v / q0 - 1 for k, v in cases.items()}}
    # perte de charge du perçage borgne (part du total)
    q250 = float(q_free(250.0, cfg))
    bore_share = float(dp_bore(q250, cfg) / 250.0)
    # sensibilité exponentielle q ∝ d^n à 250 Pa
    n_d = float(np.log(q_free(250, cfg.with_(d=cfg.d * 1.01)) / q250) / np.log(1.01))
    n_L = float(np.log(q_free(250, cfg.with_(L=cfg.L * 1.01)) / q250) / np.log(1.01))
    # température : μ ∝ T^0,7, ρ ∝ 1/T, ν ∝ T^1,7 (effet à 250 Pa, +2 K)
    # (évalué par l'expression analytique : Re_th et ρ)
    import sys
    me = sys.modules[__name__]
    dT = 2.0
    T0 = 293.15
    old = (me.RHO, me.NU, me.MU)
    me.RHO = old[0] * T0 / (T0 + dT)
    me.MU = old[2] * ((T0 + dT) / T0) ** 0.7
    me.NU = me.MU / me.RHO
    q_T = float(q_free(250.0, cfg))
    me.RHO, me.NU, me.MU = old
    # compressibilité
    V250 = q250 / cfg.A
    mach = V250 / 343.0
    eps = 1 - 0.41 * 400 / (1.4 * P_ATM)      # facteur de détente ISO 5167, β→0
    rho_change = 400 / P_ATM / 1.4

    res.update({
        "sensitivities": sens, "bore_share_of_dp_at_250Pa": bore_share,
        "exponent_q_vs_d_at_250Pa": n_d, "exponent_q_vs_L_at_250Pa": n_L,
        "temperature_plus2K_rel_q_at_250Pa": q_T / q250 - 1,
        "compressibility": {"Mach_at_250Pa": mach, "expansion_factor_400Pa": eps,
                            "density_change_400Pa": rho_change},
        "R_lam_Pa_s_m3": 128 * MU * cfg.L / (np.pi * cfg.d**4),
    })

    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    keys = list(sens["250Pa"]["rel"].keys())
    y = np.arange(len(keys))
    ax.barh(y + 0.2, [sens["250Pa"]["rel"][k] * 100 for k in keys], height=0.38,
            color=SERIES[0], label="Δp = 250 Pa")
    ax.barh(y - 0.2, [sens["50Pa"]["rel"][k] * 100 for k in keys], height=0.38,
            color=SERIES[1], label="Δp = 50 Pa")
    ax.set_yticks(y, keys)
    ax.invert_yaxis()
    ax.axvline(0, color=INK2, lw=0.8)
    ax.set_xlabel("variation du débit d'un trou (%)")
    ax.set_title("Sensibilité du débit d'un trou aux défauts de fabrication")
    ax.legend()
    savefig(fig, "orifice_sensibilites.png")

    save_json("orifice.json", res)
    print("q(250 Pa) baseline =", q250, "m3/s ; V =", V250, "m/s ; Re =",
          V250 * cfg.d / NU, "; Cd =", q250 / (cfg.A * np.sqrt(500 / RHO)))
    for m in res["models"]:
        print(m, ["%.3e" % v for v in res["models"][m]["q_m3s"]])
    print("exposants q~d^%.2f, q~L^%.2f ; part perçage borgne %.1f %%" % (
        n_d, n_L, 100 * bore_share))
    for k in keys:
        print(f"  {k:24s} {sens['250Pa']['rel'][k]*100:+6.2f} %  {sens['50Pa']['rel'][k]*100:+6.2f} %")
    print("Mach", mach, "eps", eps, "dT+2K", q_T / q250 - 1)


if __name__ == "__main__":
    main()
