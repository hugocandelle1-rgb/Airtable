"""Effets thermiques sur la planéité de la plaque et sur les accéléromètres.

1. Courbure thermique d'une plaque libre : κ = (12 α / e³) ∫ (T − T̄)(z − e/2) dz.
   Pour un flux stationnaire q traversant l'épaisseur : κ = α·q / k (indépendant
   de e). La pente résiduelle d'une courbure sphérique, après retrait du plan, est
   maximale au coin de la zone de travail : θ = κ·s·√2 (s = demi-côté).
2. Modèle 1D transitoire à travers l'épaisseur de la zone percée : l'air du plenum
   (température T_a) remonte dans les lamages et échange avec la plaque
   (laminaire établi, Nu = 3,66) ; la face supérieure échange avec le local
   (h_top). On en tire la courbure stationnaire et transitoire pour un écart
   T_a − T_plaque, les constantes de temps et l'exigence sur la température de
   l'air soufflé.
3. Échauffement de l'air par le ventilateur (puissance électrique dissipée
   dans le flux).
4. Embase isotherme des accéléromètres ADXL355 : pente parasite due à un
   gradient local (dilatation différentielle des pieds, flexion du bloc) et à la
   dérive d'offset résiduelle après compensation par TMP117.

    python3 -m calc.structure.thermal
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np

from calc.common.params import REPO_ROOT, load_params
from calc.structure.homogenization import hex_porosity

RES = REPO_ROOT / "calc" / "structure" / "results"
FIG = REPO_ROOT / "calc" / "structure" / "figures"

# Propriétés thermiques de l'EN AW-5083 coulée (docs/research/materiaux_plaque.md :
# λ = 110–140 W/(m·K) ; on prend la borne basse, défavorable)
K_PLATE = 110.0          # W/(m·K)
C_PLATE = 900.0          # J/(kg·K)
CP_AIR = 1005.0          # J/(kg·K)
K_AIR = 0.026            # W/(m·K)
H_TOP = (3.0, 5.0, 10.0)  # W/(m²·K) : convection naturelle + rayonnement (alu nu ε≈0,1 → 10 si anodisé noir)
ETA_FAN_EL = 0.25        # rendement électrique global estimé (petit centrifuge EC, à recaler sur la fiche)

STUDY_PITCH_MM = 4.82    # cf. support_study (piste lot aéraulique)
STUDY_THICKNESS_MM = 35.0  # épaisseur recommandée (support_study)
STUDY_CB_MM = 2.0


def slope_from_curvature(kappa, s_work):
    """Pente crête (rad) d'une courbure sphérique après retrait du plan."""
    return kappa * s_work * np.sqrt(2)


def flow_envelope():
    """(Q_min, Q_max) en m³/s et puissance d'air max, lus dans calc/aero si présent."""
    f = REPO_ROOT / "calc" / "aero" / "results" / "network.json"
    if f.exists():
        d = json.loads(f.read_text())
        qmin = d["operating_min"]["Q_m3s"]
        qmax = d["operating_max"]["Q_m3s"]
        dpmin = d["operating_min"]["dp_fan_total"]
        dpmax = d["operating_max"]["dp_fan_total_dirty"]
        return qmin, qmax, dpmin, dpmax, "calc/aero/results/network.json"
    return 12.9 / 3600, 46.4 / 3600, 49.0, 406.0, "valeurs par défaut (lot aéro, 2026-10-29)"


class Through1D:
    """Plaque percée, modèle 1D en z (0 = face inférieure), différences finies
    implicites. L'air entre en bas à T_a, échange dans les lamages, sort en haut."""

    def __init__(self, P, h, Q, pitch_mm=STUDY_PITCH_MM, cb_mm=STUDY_CB_MM, h_top=5.0, nz=80):
        pl = P["plate"]
        env = P["environment"]
        self.h, self.nz = h, nz
        self.alpha = pl["alpha_th"]
        p, d = pitch_mm * 1e-3, cb_mm * 1e-3
        f = hex_porosity(p, d)
        self.f = f
        A_perf = (P["zones"]["perforated_square_mm"] * 1e-3) ** 2
        self.G = Q * env["air_rho"] * CP_AIR / A_perf                 # W/(m²·K) capacité du débit
        n_area = 1 / (np.sqrt(3) / 2 * p**2)                          # trous par m²
        h_hole = 3.66 * K_AIR / d
        self.Hp = n_area * np.pi * d * h_hole                          # W/(m³·K) échange volumique
        self.k = K_PLATE * (1 - f)
        self.rc = pl["rho"] * C_PLATE * (1 - f)
        self.h_top = h_top
        self.h_bot = 5.0                                               # face inférieure / air du plenum
        self.z = np.linspace(0, h, nz)
        self.dz = self.z[1] - self.z[0]
        self.web = h - pl["orifice_length_mm"] * 1e-3                  # au-dessus : voile (échange négligé)

    def air_profile(self, T, Ta):
        """Température de l'air le long du lamage (quasi stationnaire)."""
        Tair = np.empty_like(T)
        Tair[0] = Ta
        for i in range(1, self.nz):
            if self.z[i] > self.web:
                Tair[i] = Tair[i - 1]
                continue
            e = np.exp(-self.Hp * self.dz / self.G)
            Tair[i] = T[i] + (Tair[i - 1] - T[i]) * e
        return Tair

    def step(self, T, Ta, Troom, dt):
        """Un pas implicite (échange air linéarisé sur le profil courant)."""
        n, dz = self.nz, self.dz
        Tair = self.air_profile(T, Ta)
        act = (self.z <= self.web).astype(float)
        A = np.zeros((n, n))
        b = self.rc * T / dt
        for i in range(n):
            w = dz if 0 < i < n - 1 else dz / 2
            A[i, i] = self.rc * w / dt
            b[i] = self.rc * w / dt * T[i]
            if i > 0:
                A[i, i] += self.k / dz; A[i, i - 1] -= self.k / dz
            if i < n - 1:
                A[i, i] += self.k / dz; A[i, i + 1] -= self.k / dz
            # échange avec l'air (bilan local : Hp·w·(Tair − T))
            A[i, i] += self.Hp * w * act[i]
            b[i] += self.Hp * w * act[i] * Tair[i]
        A[0, 0] += self.h_bot; b[0] += self.h_bot * Ta
        A[-1, -1] += self.h_top; b[-1] += self.h_top * Troom
        return np.linalg.solve(A, b)

    def curvature(self, T):
        zc = self.z - self.h / 2
        w = np.full(self.nz, self.dz); w[0] = w[-1] = self.dz / 2
        Tm = np.sum(w * T) / self.h
        return 12 * self.alpha / self.h**3 * np.sum(w * (T - Tm) * zc)

    def steady(self, Ta, Troom):
        T = np.full(self.nz, Troom)
        for _ in range(60):
            T = self.step(T, Ta, Troom, 1e6)
        return T

    def time_constant(self):
        """τ de mise en équilibre de la plaque avec l'air (capacité / conductances)."""
        return self.rc * self.h / (self.G + self.h_top)


def run(P=None, verbose=True):
    P = P or load_params()
    pl = P["plate"]
    s_work = P["zones"]["working_square_mm"] / 2 * 1e-3
    budget = 5e-6
    qmin, qmax, dpmin, dpmax, src = flow_envelope()
    out = dict(source_flow=src, k_plate=K_PLATE, alpha=pl["alpha_th"])

    # 1) relations de base
    kappa_max = budget / (s_work * np.sqrt(2))
    q_max = kappa_max * K_PLATE / pl["alpha_th"]
    out["budget"] = dict(slope_urad=budget * 1e6, kappa_max_per_m=kappa_max, q_max_W_m2=q_max,
                         dT_through_max_K={str(e): kappa_max * e * 1e-3 / pl["alpha_th"] for e in (25, 30, 35)})
    if verbose:
        print(f"Budget thermique 5 µrad → κ ≤ {kappa_max:.2e} 1/m ; flux traversant ≤ {q_max:.0f} W/m² ; "
              f"ΔT haut/bas ≤ " + ", ".join(f"{v*1e3:.0f} mK (e={k})" for k, v in out["budget"]["dT_through_max_K"].items()))

    # 2) échauffement de l'air par le ventilateur
    rho = P["environment"]["air_rho"]
    fan = {}
    for name, Q, dp in (("min", qmin, dpmin), ("max", qmax, dpmax)):
        Pel = Q * dp / ETA_FAN_EL
        fan[name] = dict(Q_m3h=Q * 3600, dp_Pa=dp, P_el_W=Pel, dT_air_K=Pel / (rho * CP_AIR * Q))
    out["fan_heating"] = fan
    if verbose:
        for k, v in fan.items():
            print(f"Ventilateur {k} : Q {v['Q_m3h']:.1f} m³/h, Δp {v['dp_Pa']:.0f} Pa, P_él ≈ {v['P_el_W']:.1f} W "
                  f"→ échauffement de l'air {v['dT_air_K']:.2f} K")

    # 3) modèle 1D : stationnaire et transitoire
    h = STUDY_THICKNESS_MM * 1e-3
    rows = []
    for name, Q in (("Qmin", qmin), ("Qmax", qmax)):
        for htop in H_TOP:
            m = Through1D(P, h, Q, h_top=htop)
            T = m.steady(1.0, 0.0)          # air +1 K par rapport au local
            kap = m.curvature(T)
            rows.append(dict(flow=name, h_top=htop, G_W_m2K=m.G, decay_mm=m.G / m.Hp * 1e3,
                             T_plate_mean_K=float(T.mean()), dT_through_mK=float((T[0] - T[-1]) * 1e3),
                             kappa_per_K=kap, slope_urad_per_K=slope_from_curvature(abs(kap), s_work) * 1e6,
                             tau_min=m.time_constant() / 60))
    out["steady_per_K_air"] = rows
    if verbose:
        print(f"Stationnaire, air soufflé +1 K / local (e = {h*1e3:.0f} mm) :")
        for r in rows:
            print(f"  {r['flow']} h_top={r['h_top']:4.1f} : longueur d'échange {r['decay_mm']:.1f} mm, ΔT haut/bas "
                  f"{r['dT_through_mK']:.2f} mK, pente {r['slope_urad_per_K']:.2f} µrad/K, τ = {r['tau_min']:.0f} min")

    # transitoire : échelon +1 K de l'air (changement de débit, démarrage)
    trans = {}
    for name, Q in (("Qmin", qmin), ("Qmax", qmax)):
        m = Through1D(P, h, Q, h_top=5.0)
        T = np.zeros(m.nz)
        dt = 5.0
        t_hist, s_hist = [], []
        for k in range(int(4 * 3600 / dt)):
            T = m.step(T, 1.0, 0.0, dt)
            if k % 6 == 0:
                t_hist.append((k + 1) * dt)
                s_hist.append(slope_from_curvature(abs(m.curvature(T)), s_work) * 1e6)
        s_hist = np.array(s_hist); t_hist = np.array(t_hist)
        s_ss = s_hist[-1]
        peak = s_hist.max()
        # temps pour revenir sous 1,1 × stationnaire + 0,1 µrad
        idx = np.where(s_hist > 1.1 * s_ss + 0.1)[0]
        t_settle = float(t_hist[idx[-1]]) if len(idx) else 0.0
        trans[name] = dict(peak_urad_per_K=float(peak), steady_urad_per_K=float(s_ss), settle_min=t_settle / 60,
                           t_s=t_hist[::10].tolist(), slope=s_hist[::10].tolist())
    out["step_1K"] = trans
    dTa_allow = {k: budget * 1e6 / v["peak_urad_per_K"] for k, v in trans.items()}
    out["air_minus_plate_allow_K"] = dTa_allow
    if verbose:
        for k, v in trans.items():
            print(f"Échelon +1 K de l'air ({k}) : pente crête transitoire {v['peak_urad_per_K']:.2f} µrad/K "
                  f"(stationnaire {v['steady_urad_per_K']:.2f}), stabilisation {v['settle_min']:.0f} min "
                  f"→ écart air/plaque admissible {dTa_allow[k]:.2f} K")

    # rampe du local 1 K/h, air aspiré dans le local (+ échauffement ventilateur constant)
    ramp = {}
    for name, Q in (("Qmin", qmin), ("Qmax", qmax)):
        m = Through1D(P, h, Q, h_top=5.0)
        T = np.zeros(m.nz)
        dt = 10.0
        smax = 0.0
        for k in range(int(3 * 3600 / dt)):
            tr = (k + 1) * dt / 3600.0
            T = m.step(T, tr, tr, dt)
            smax = max(smax, slope_from_curvature(abs(m.curvature(T)), s_work) * 1e6)
        ramp[name] = dict(slope_urad=smax, lag_K=float(tr - T.mean()))
    out["room_ramp_1K_per_h"] = ramp
    if verbose:
        for k, v in ramp.items():
            print(f"Rampe du local 1 K/h ({k}) : pente {v['slope_urad']:.2f} µrad, retard de la plaque {v['lag_K']:.2f} K")

    # 4) embase isotherme ADXL355
    base = dict(alpha=23e-6, foot_height=0.012, foot_spacing=0.040, block_t=0.015, sensor_offset=0.005,
                dT_lat=0.05, dT_vert=0.02, tempco_typ_urad_K=20.0, tempco_max_urad_K=150.0,
                comp_residual=0.1, dT_day=0.5)
    b = base
    tilt_feet = b["alpha"] * b["foot_height"] * b["dT_lat"] / b["foot_spacing"] * 1e6
    kap_block = b["alpha"] * b["dT_vert"] / b["block_t"]
    tilt_block = kap_block * b["sensor_offset"] * 1e6
    off_typ = b["tempco_typ_urad_K"] * b["comp_residual"] * b["dT_day"]
    off_max = b["tempco_max_urad_K"] * b["comp_residual"] * b["dT_day"]
    # capot isolant : constante de temps du bloc vis-à-vis de l'air (bloc couplé à la plaque)
    lam_ins, t_ins, A_cap = 0.035, 0.010, 0.06 * 0.06 + 4 * 0.06 * 0.035
    R_cap = t_ins / (lam_ins * A_cap)
    R_contact = 0.3                                                   # K/W, 3 pieds vissés + pâte thermique
    m_block = 0.06 * 0.06 * 0.02 * 2700
    tau_block = m_block * 900 * R_contact / 60
    att = R_contact / (R_cap + R_contact)                            # fraction d'un écart d'air vue par le bloc / plaque
    out["adxl_base"] = dict(hyp=base, tilt_feet_urad=tilt_feet, tilt_block_bending_urad=tilt_block,
                            offset_residual_typ_urad=off_typ, offset_residual_max_urad=off_max,
                            R_cap_K_W=R_cap, R_contact_K_W=R_contact, tau_block_min=tau_block,
                            air_to_block_coupling=att)
    if verbose:
        print(f"Embase ADXL355 : gradient latéral {b['dT_lat']*1e3:.0f} mK → {tilt_feet:.3f} µrad (pieds h = 12, entraxe 40) ; "
              f"gradient vertical {b['dT_vert']*1e3:.0f} mK → {tilt_block:.3f} µrad (excentrement 5 mm) ; "
              f"offset résiduel après compensation TMP117 (10 %, ΔT jour {b['dT_day']} K) : {off_typ:.1f} µrad typ / {off_max:.1f} max ; "
              f"capot R = {R_cap:.0f} K/W, couplage air→bloc {att*100:.1f} %, τ bloc/plaque {tau_block:.1f} min")

    RES.mkdir(parents=True, exist_ok=True)
    (RES / "thermal.json").write_text(json.dumps(out, indent=1, default=float))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(6.5, 4))
    for k, v in trans.items():
        ax.plot(np.array(v["t_s"]) / 60, v["slope"], label=f"échelon +1 K de l'air, {k}")
    ax.axhline(5, color="r", ls="--", lw=1, label="budget 5 µrad")
    ax.set_xlabel("temps (min)"); ax.set_ylabel("pente crête (µrad par K d'écart)")
    ax.set_xscale("log"); ax.grid(alpha=0.3, which="both"); ax.legend(fontsize=8)
    ax.set_title(f"Courbure thermique transitoire, e = {STUDY_THICKNESS_MM:.0f} mm (modèle 1D)", fontsize=10)
    fig.tight_layout(); fig.savefig(FIG / "thermal_step.png", dpi=130); plt.close(fig)
    if verbose:
        print("→ results/thermal.json, figures/thermal_step.png")
    return out


if __name__ == "__main__":
    run()
