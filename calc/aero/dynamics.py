"""Dynamique du palet sur son film : stabilité (marteau pneumatique), fréquences
propres verticale et en basculement, amortissements visqueux latéral et en rotation.

Modèle : équation de Reynolds instationnaire, film isotherme compressible,
linéarisée autour de l'équilibre du modèle axisymétrique homogénéisé (corrigé
« puits ») ; les trous réagissent quasi statiquement (inertance de l'orifice
négligeable : constante de temps ≈ ρL/(A·dΔp/dq) ≈ 10⁻⁴ s).

  ∂h/∂t + (h0 + n·V_pk)/p_a · ∂p/∂t = ∇·(h³/12μ ∇p) + n·q(ps − p, h)

V_pk est le volume aval de chaque restriction (entre la restriction et le film).
Deux cas sont comparés :
  A. restriction en face supérieure (baseline) : V_pk = chanfrein de sortie ;
  B. variante « restriction en bas » : V_pk = volume du perçage Ø D_cb (24 mm).

Le système (film discrétisé + palet m s² ε = F) est mis sous forme d'un problème
aux valeurs propres généralisé A x = s B x ; stabilité ⇔ Re(s) < 0 pour tout s.

Lancement : ``python3 -m calc.aero.dynamics``.
"""
from __future__ import annotations

import numpy as np
import scipy.linalg as sl
from scipy.optimize import brentq

from calc.aero.common import (G, MU, RHO, P_ATM, A_PUCK, R_PUCK, recommended_config,
                              h_target, setup_style, savefig, save_json, SERIES, INK2,
                              MASS_CASES_G)
from calc.aero import film as F

H_PUCK = 10e-3          # hauteur supposée des palets (m) — sert à l'inertie de basculement
KAPPA = 1.0             # exposant polytropique (film mince ⇒ isotherme)


def _operators(cfg, ps, h, mode, V_pk):
    s = F.axi_solve(cfg, ps, h)
    r, dr, rf, A, p0 = s["r"], s["dr"], s["rf"], s["A"], s["p"]
    N = len(r)
    n = cfg.density
    vol = r * dr
    dp0 = np.zeros(N + 1)
    dp0[1:N] = (p0[1:] - p0[:-1]) / dr
    dp0[N] = -p0[-1] / (0.5 * dr)
    C = (h + n * V_pk) / (KAPPA * P_ATM)
    Dq = np.diag(n * vol / s["gq"])
    if mode == "heave":
        S0 = 3 * h**2 / (12 * MU) * (rf[1:] * dp0[1:] - rf[:-1] * dp0[:-1]) \
            - n * vol * s["gh"] / s["gq"]
        Amat = A - Dq
        w = 2 * np.pi * r * dr                     # force = Σ P·2πr dr
        geo = vol                                  # ∂h/∂t = s·ε
    else:  # tilt (m = 1)
        S0 = 3 * h**2 / (12 * MU) * (rf[1:] ** 2 * dp0[1:] - rf[:-1] ** 2 * dp0[:-1]) \
            - n * vol * s["gh"] * r / s["gq"]
        Amat = A - np.diag(s["k"] * dr / r) - Dq
        w = np.pi * r**2 * dr                      # moment = π Σ P1 r² dr
        geo = r * vol                              # ∂h/∂t = s·θ·r cos φ
    return dict(Amat=Amat, S0=S0, C=C, vol=vol, w=w, geo=geo, sol=s)


def dynamic_stiffness(cfg, ps, h, omega, mode="heave", V_pk=0.0):
    """K(iω) = −F/ε (heave, N/m) ou −M/θ (tilt, N·m/rad)."""
    o = _operators(cfg, ps, h, mode, V_pk)
    out = []
    for om in np.atleast_1d(omega):
        s = 1j * om
        Msys = o["Amat"] - s * np.diag(o["C"] * o["vol"])
        rhs = -(o["S0"] - s * o["geo"])
        P = np.linalg.solve(Msys, rhs)
        out.append(-(o["w"] @ P))
    return np.array(out)


def eigen_modes(cfg, ps, h, inertia, mode="heave", V_pk=0.0):
    """Valeurs propres du système couplé film + palet (problème généralisé)."""
    o = _operators(cfg, ps, h, mode, V_pk)
    N = len(o["vol"])
    Am = np.zeros((N + 2, N + 2))
    Bm = np.zeros((N + 2, N + 2))
    Am[:N, :N] = o["Amat"]
    Am[:N, N] = o["S0"]
    Am[N, N + 1] = 1.0
    Am[N + 1, :N] = o["w"]
    Bm[:N, :N] = np.diag(o["C"] * o["vol"])
    Bm[:N, N] = o["geo"]
    Bm[N, N] = 1.0
    Bm[N + 1, N + 1] = inertia
    ev, vec = sl.eig(Am, Bm)
    ok = np.isfinite(ev)
    ev, vec = ev[ok], vec[:, ok]
    part = np.abs(vec[N, :]) / (np.abs(vec[N, :]) + np.max(np.abs(vec[:N, :]), axis=0)
                                * h / max(ps, 1.0))
    return ev, part


def puck_mode(ev, part):
    """Mode « palet » : valeur propre de plus grande participation du déplacement."""
    i = np.argsort(-part)[:2]
    k = i[np.argmax(ev[i].real)]
    return ev[k]


def main():
    plt = setup_style()
    cfg = recommended_config()
    ht = h_target()
    V_top = np.pi * cfg.d * (0.05e-3) ** 2           # chanfrein 0,05 × 45° (≈ anneau)
    V_bot = np.pi / 4 * cfg.D_cb**2 * cfg.L_bore     # perçage Ø D_cb sous le film
    res = {"config": cfg, "h_target_um": ht * 1e6, "H_puck_assumed_mm": H_PUCK * 1e3,
           "V_pocket_top_m3": V_top, "V_pocket_bottom_m3": V_bot, "cases": []}
    masses = [2.0, 5.0, 10.0]
    omega = np.logspace(0, 4.5, 200)
    fig, axs = plt.subplots(1, 2, figsize=(11, 4.2))
    for mg, col in zip(masses, SERIES):
        m = mg * 1e-3
        ps = brentq(lambda p: F.axi_W(cfg, p, ht) - m * G, 5, 20000)
        kz = F.axi_kz(cfg, ps, ht)
        kth = F.axi_ktheta(cfg, ps, ht)
        I_tilt = m * (3 * R_PUCK**2 + H_PUCK**2) / 12
        fz = np.sqrt(kz / m) / (2 * np.pi)
        fth = np.sqrt(kth / I_tilt) / (2 * np.pi)
        c_sq = 3 * np.pi * MU * R_PUCK**4 / (2 * ht**3)     # écrasement, disque plein sans trous
        case = {"mass_g": mg, "ps_Pa": ps, "kz_N_m": kz, "ktheta_Nm_rad": kth,
                "f_heave_quasistatic_Hz": fz, "f_tilt_quasistatic_Hz": fth,
                "zeta_squeeze_nofeed": c_sq / (2 * np.sqrt(kz * m))}
        for tag, V in (("top", V_top), ("bottom", V_bot)):
            ev, part = eigen_modes(cfg, ps, ht, m, "heave", V)
            s = puck_mode(ev, part)
            evt, partt = eigen_modes(cfg, ps, ht, I_tilt, "tilt", V)
            st = puck_mode(evt, partt)
            Kw = dynamic_stiffness(cfg, ps, ht, omega, "heave", V)
            case[f"heave_{tag}"] = {
                "eig_puck": [s.real, s.imag], "max_real_all": float(ev.real.max()),
                "f_Hz": abs(s.imag) / (2 * np.pi),
                "zeta": float(-s.real / abs(s)) if abs(s) > 0 else 1.0,
                "min_Kimag_over_omega": float(np.min(Kw.imag)),
                "stable": bool(ev.real.max() < 0)}
            case[f"tilt_{tag}"] = {
                "eig_puck": [st.real, st.imag], "max_real_all": float(evt.real.max()),
                "f_Hz": abs(st.imag) / (2 * np.pi),
                "zeta": float(-st.real / abs(st)) if abs(st) > 0 else 1.0,
                "stable": bool(evt.real.max() < 0)}
            if tag == "top":
                axs[0].semilogx(omega / (2 * np.pi), Kw.real / kz, color=col,
                                label=f"{mg:g} g — K'/k_z")
                axs[1].semilogx(omega / (2 * np.pi), Kw.imag / omega, color=col,
                                label=f"{mg:g} g, restriction en haut")
            else:
                axs[1].semilogx(omega / (2 * np.pi), Kw.imag / omega, color=col, ls="--",
                                label=f"{mg:g} g, restriction en bas (V = {V*1e9:.0f} mm³)")
        # dh/dps (transmission des fluctuations de pression du plenum)
        dps = 0.02 * ps
        hp = F.axi_solve_h(cfg, ps + dps, m)
        hm = F.axi_solve_h(cfg, ps - dps, m)
        case["dh_dps_um_per_Pa"] = (hp - hm) / (2 * dps) * 1e6
        # amortissements visqueux (Couette) latéral et en rotation
        c_lat = MU * A_PUCK / ht
        case["c_lateral_Ns_m"] = c_lat
        case["tau_lateral_s"] = m / c_lat
        case["tau_rotation_s"] = (m * R_PUCK**2 / 2) / (MU * np.pi * R_PUCK**4 / (2 * ht))
        # traînée aérodynamique sur la face latérale (C_d ≈ 1,0) à 50 mm/s
        v = 0.05
        case["drag_side_at_50mm_s_N"] = 0.5 * RHO * 1.0 * (2 * R_PUCK * H_PUCK) * v**2
        case["couette_at_50mm_s_N"] = c_lat * v
        res["cases"].append(case)
    axs[0].set_xlabel("fréquence (Hz)")
    axs[0].set_ylabel("K'(ω)/k_z")
    axs[0].set_title("Raideur dynamique verticale du film (partie réelle)")
    axs[0].legend(fontsize=8)
    axs[1].set_xlabel("fréquence (Hz)")
    axs[1].set_ylabel("amortissement équivalent K''/ω (N·s/m)")
    axs[1].set_yscale("symlog", linthresh=1e-2)
    axs[1].axhline(0, color=INK2, lw=0.8)
    axs[1].set_title("Amortissement du film : > 0 ⇒ pas de marteau pneumatique")
    axs[1].legend(fontsize=7)
    savefig(fig, "dynamique_raideur_amortissement.png")

    # constantes de temps visqueuses en fonction de h
    fig, ax = plt.subplots(figsize=(6.5, 4))
    hh = np.linspace(60e-6, 260e-6, 50)
    for mg, col in zip(MASS_CASES_G, SERIES):
        ax.plot(hh * 1e6, mg * 1e-3 * hh / (MU * A_PUCK), color=col, label=f"{mg:g} g")
    ax.axvline(ht * 1e6, color=INK2, lw=0.8, ls=":")
    ax.set_xlabel("entrefer h (µm)")
    ax.set_ylabel("τ = m·h/(μ·A) (s)")
    ax.set_title("Constante de temps de l'amortissement visqueux (translation = rotation)")
    ax.legend()
    savefig(fig, "dynamique_constantes_temps.png")

    # volume aval critique (marteau pneumatique) : balayage de V_pk
    fig, ax = plt.subplots(figsize=(6.5, 4))
    Vs = V_bot * np.logspace(-2, 2.5, 28)
    for mg, col, c in zip(masses, SERIES, res["cases"]):
        m = mg * 1e-3
        zs = []
        for V in Vs:
            ev, part = eigen_modes(cfg, c["ps_Pa"], ht, m, "heave", V)
            sm = puck_mode(ev, part)
            zs.append(-sm.real / abs(sm))
        zs = np.array(zs)
        ax.semilogx(Vs / V_bot, zs, color=col, label=f"{mg:g} g")
        crit = np.nan
        if np.any(zs < 0):
            k = np.argmax(zs < 0)
            crit = float(np.exp(np.interp(0, [zs[k], zs[k - 1]], [np.log(Vs[k]), np.log(Vs[k - 1])])))
        c["V_pocket_critical_m3"] = crit
        c["V_pocket_critical_over_bore"] = crit / V_bot
        c["V_pocket_critical_over_top"] = crit / V_top
    ax.axvline(1.0, color=INK2, ls="--", lw=0.8)
    ax.axvline(V_top / V_bot, color=INK2, ls=":", lw=0.8)
    ax.axhline(0, color=INK2, lw=0.8)
    ax.text(1.1, 0.9, "perçage Ø2 sous le film\n(restriction en bas)", fontsize=8, color=INK2)
    ax.set_xlabel("volume aval par trou / volume du perçage Ø D_cb")
    ax.set_ylabel("taux d'amortissement ζ du mode vertical")
    ax.set_title("Marge vis-à-vis du marteau pneumatique")
    ax.legend()
    savefig(fig, "dynamique_marteau_pneumatique.png")

    save_json("dynamics.json", res)
    for c in res["cases"]:
        print(f"{c['mass_g']:4.1f} g ps={c['ps_Pa']:.0f} kz={c['kz_N_m']:.0f} f_z={c['f_heave_quasistatic_Hz']:.1f}Hz "
              f"heave top: f={c['heave_top']['f_Hz']:.1f} ζ={c['heave_top']['zeta']:.2f} stable={c['heave_top']['stable']} | "
              f"bottom: f={c['heave_bottom']['f_Hz']:.1f} ζ={c['heave_bottom']['zeta']:.3f} "
              f"stable={c['heave_bottom']['stable']} minK''={c['heave_bottom']['min_Kimag_over_omega']:.2e} | "
              f"tilt top f={c['tilt_top']['f_Hz']:.1f} ζ={c['tilt_top']['zeta']:.2f} | τ={c['tau_lateral_s']:.1f}s "
              f"dh/dps={c['dh_dps_um_per_Pa']:.2f}um/Pa Vcrit/Vbore={c['V_pocket_critical_over_bore']:.0f}")


if __name__ == "__main__":
    main()
