"""Accouplement cinématique (Maxwell, 3 billes / 3 vés) et mécanisme de
nivellement fin (vérins à coin), versions motorisée et manuelle.

Contenu :
  1. Contact de Hertz bille / rouleau (vé formé de deux rouleaux trempés
     parallèles) : pression maximale, ellipse de contact, enfoncement, raideur
     tangente ; raideur verticale d'un appui (2 contacts à 45°).
  2. Géométrie de nivellement : bras de levier des appuis mobiles, course
     verticale requise pour ±0,25° (+ marge), orientation des vés (Maxwell :
     axes des vés vers le barycentre des appuis).
  3. Vérin à coin : pente du coin, vis fine, moteur pas à pas → µrad par pas,
     course, effort et couple, irréversibilité ; version manuelle (bouton
     gradué sur l'arbre arrière du moteur) et variante économique (ajusteur
     différentiel du commerce + coin).
  4. Fréquence de « pompage » de la plaque sur ses 3 appuis.

Les réactions d'appui sont lues dans results/support_study.json (schéma retenu).

    python3 -m calc.structure.kinematic_coupling
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np

from calc.common.params import REPO_ROOT, load_params

RES = REPO_ROOT / "calc" / "structure" / "results"

E_STEEL, NU_STEEL = 210e9, 0.30


def hertz_ball_cylinder(W, R_ball, R_cyl, E1=E_STEEL, nu1=NU_STEEL, E2=E_STEEL, nu2=NU_STEEL):
    """Contact elliptique bille (R_ball) / cylindre (R_cyl, axe y) sous effort
    normal W. Approximations de Hamrock & Brewe (1983). SI."""
    Rx = 1 / (1 / R_ball + 1 / R_cyl)
    Ry = R_ball
    ar = Ry / Rx
    k = ar ** (2 / np.pi)
    Eell = 1 + (np.pi / 2 - 1) / ar
    Fell = np.pi / 2 + (np.pi / 2 - 1) * np.log(ar)
    Rp = 1 / (1 / Rx + 1 / Ry)
    Ep = 2 / ((1 - nu1**2) / E1 + (1 - nu2**2) / E2)
    a = (6 * k**2 * Eell * W * Rp / (np.pi * Ep)) ** (1 / 3)      # demi-grand axe (selon y)
    b = (6 * Eell * W * Rp / (np.pi * k * Ep)) ** (1 / 3)         # demi-petit axe
    delta = Fell * (9 / (2 * Eell * Rp) * (W / (np.pi * k * Ep)) ** 2) ** (1 / 3)
    pmax = 3 * W / (2 * np.pi * a * b)
    kn = 1.5 * W / delta                                           # raideur tangente (δ ∝ W^(2/3))
    return dict(a_mm=a * 1e3, b_mm=b * 1e3, delta_um=delta * 1e6, pmax_GPa=pmax / 1e9, k_N_m=kn)


def support_reactions():
    """Réactions de poids propre du schéma retenu (chemin B), N, et positions (m)."""
    f = RES / "support_study.json"
    if f.exists():
        d = json.loads(f.read_text())
        sel = d["selected"]
        pts = np.array(sel["points_mm"]) * 1e-3
        by = sel["by_thickness"]
        h = "35" if "35" in by else sorted(by)[-1]
        return pts, np.array(by[h]["B"]["R_G_N"]), f"support_study.json (e = {h} mm, chemin B)"
    pts = np.array([[0.0, 0.2425], [0.2425, -0.1455], [-0.2425, -0.1455]])
    W = 36 * 9.81
    return pts, np.array([0.375, 0.3125, 0.3125]) * W, "estimation (support_study non exécuté)"


def lever_arms(pts):
    """Bras de levier : distance de chaque appui à la droite des deux autres,
    et entraxes utiles pour le tangage (arrière ↔ ligne avant) et le roulis."""
    arms = []
    for i in range(3):
        p, q, r = pts[i], pts[(i + 1) % 3], pts[(i + 2) % 3]
        u = (r - q) / np.linalg.norm(r - q)
        v = p - q
        arms.append(abs(v[0] * u[1] - v[1] * u[0]))
    return np.array(arms)


def run(P=None, verbose=True):
    P = P or load_params()
    perf = P["performance_targets"]
    res_target = perf["leveling_resolution_urad"] * 1e-6
    range_rad = np.deg2rad(perf["leveling_range_deg"])
    pts, R, src = support_reactions()
    out = dict(source=src, points_mm=(pts * 1e3).tolist(), reactions_N=R.tolist())

    # --- 1) Hertz -----------------------------------------------------------------
    # bille Ø30 G10 (100Cr6), rouleaux Ø20 h6 trempés rectifiés (arbres de guidage) : p_max ≤ 1,5 GPa
    # (≪ 4 GPa d'enfoncement permanent ; cible usuelle des couplages répétables 1–2 GPa)
    R_ball, R_roll = 0.015, 0.010
    preload = 40.0                          # N, ressort de maintien par tige à travers l'appui
    vee_half = np.deg2rad(45)
    hz = []
    for i, Ri in enumerate(R):
        N = Ri + preload
        W = N / (2 * np.cos(vee_half))       # effort normal par contact
        h = hertz_ball_cylinder(W, R_ball, R_roll)
        kz = 2 * h["k_N_m"] * np.cos(vee_half) ** 2   # raideur verticale (2 contacts)
        h.update(N_vertical=N, W_contact=W, k_vertical_N_m=kz)
        hz.append(h)
    out["hertz"] = dict(ball_d_mm=2 * R_ball * 1e3, roller_d_mm=2 * R_roll * 1e3, preload_N=preload,
                        vee_included_deg=90, contacts=hz)
    # ruine statique (enfoncement permanent ~ 1e-4 D) vers 4 GPa ; cible repetabilité < 1,5–2 GPa
    if verbose:
        print(f"Réactions ({src}) : {np.round(R, 1).tolist()} N ; précharge {preload:.0f} N")
        for i, h in enumerate(hz):
            print(f"  appui {i} : W/contact {h['W_contact']:.0f} N → p_max {h['pmax_GPa']:.2f} GPa, ellipse "
                  f"{2*h['a_mm']:.2f}×{2*h['b_mm']:.2f} mm, δ {h['delta_um']:.2f} µm, k_z {h['k_vertical_N_m']:.2e} N/m")

    # --- 2) Géométrie de nivellement ----------------------------------------------
    arms = lever_arms(pts)
    L_pitch = pts[0][1] - pts[1][1]                         # arrière ↔ ligne des appuis avant
    L_roll = abs(pts[1][0] - pts[2][0])                     # entre appuis avant
    L_min = min(arms[1], arms[2], L_pitch, L_roll)          # appuis mobiles = 1 et 2 (avant)
    z_range = range_rad * max(L_pitch, L_roll) * 1.15       # +15 % de marge (tangage + roulis combinés)
    centroid = pts.mean(axis=0)
    vee_dirs = [float(np.degrees(np.arctan2(*(centroid - p_)[::-1]))) for p_ in pts]
    out["geometry"] = dict(arms_mm=(arms * 1e3).tolist(), L_pitch_mm=L_pitch * 1e3, L_roll_mm=L_roll * 1e3,
                           L_min_mm=L_min * 1e3, z_range_pm_mm=z_range * 1e3,
                           centroid_mm=(centroid * 1e3).tolist(), vee_axis_angle_deg=vee_dirs)
    if verbose:
        print(f"Bras de levier : {np.round(arms*1e3,0).tolist()} mm ; tangage {L_pitch*1e3:.0f} mm, roulis {L_roll*1e3:.0f} mm ; "
              f"course verticale requise ±{z_range*1e3:.2f} mm (±{perf['leveling_range_deg']}° + 15 %)")
        print(f"  axes des vés (vers le barycentre {np.round(centroid*1e3,1).tolist()} mm) : {np.round(vee_dirs,1).tolist()}°")

    # --- 3) Vérins à coin -----------------------------------------------------------
    designs = {}
    # (a) référence motorisée : coin 1:5, vis M6×0,25 (écrou bronze rattrapé par ressort), NEMA17 200 pas
    def wedge(name, tan_a, lead_mm, steps_rev, micro, mu_wedge, mu_thread, d_thread_mm, N, manual_div=None):
        dz_rev = lead_mm * 1e-3 * tan_a
        dz_step = dz_rev / steps_rev
        urad_step = dz_step / L_min * 1e6
        wedge_travel = z_range / tan_a
        turns = wedge_travel / (lead_mm * 1e-3)
        F_ax = N * (tan_a + mu_wedge) / (1 - mu_wedge * tan_a)          # effort sur la vis (montée)
        F_down = N * (tan_a - mu_wedge) / (1 + mu_wedge * tan_a)        # effort de retour (descente)
        lam = np.arctan(lead_mm / (np.pi * d_thread_mm))
        phi = np.arctan(mu_thread / np.cos(np.deg2rad(30)))
        eta = np.tan(lam) / np.tan(lam + phi)
        T = F_ax * lead_mm * 1e-3 / (2 * np.pi * eta)
        d = dict(tan_wedge=tan_a, lead_mm=lead_mm, dz_per_rev_um=dz_rev * 1e6, dz_per_step_um=dz_step * 1e6,
                 urad_per_step=urad_step, urad_per_rev=dz_rev / L_min * 1e6, steps_per_rev=steps_rev,
                 microsteps=micro, wedge_travel_pm_mm=wedge_travel * 1e3, screw_turns_pm=turns,
                 F_screw_N=F_ax, F_return_N=F_down, thread_efficiency=eta, self_locking=bool(lam < phi),
                 torque_Nm=T, N_support_N=N, meets_resolution=bool(urad_step <= res_target * 1e6))
        if manual_div:
            d["manual_div_per_rev"] = manual_div
            d["urad_per_div"] = dz_rev / L_min * 1e6 / manual_div
        designs[name] = d
        return d

    N_max = max(R[1:]) + preload
    wedge("reference_motorise", 0.2, 0.25, 200, 16, 0.005, 0.15, 6.0, N_max, manual_div=100)
    # (b) variante économique manuelle : coin 1:5 + ajusteur différentiel du commerce
    #     (Thorlabs DAS110 : 25 µm/tour en fin, 318 µm/tour en grossier — docs/research/profiles_alu_et_mecanique.md)
    wedge("eco_differentiel_fin", 0.2, 0.025, 1, 1, 0.10, 0.15, 6.35, N_max, manual_div=50)
    wedge("eco_differentiel_grossier", 0.2, 0.318, 1, 1, 0.10, 0.15, 6.35, N_max, manual_div=50)
    out["wedge"] = designs
    if verbose:
        for k, d in designs.items():
            line = (f"  {k}: dz/tour {d['dz_per_rev_um']:.2f} µm → {d['urad_per_rev']:.2f} µrad/tour ; ")
            if d["steps_per_rev"] > 1:
                line += f"pas entier {d['dz_per_step_um']*1e3:.0f} nm = {d['urad_per_step']:.2f} µrad ; "
            if "urad_per_div" in d:
                line += f"{d['urad_per_div']:.2f} µrad/graduation ({d['manual_div_per_rev']} div) ; "
            line += (f"course coin ±{d['wedge_travel_pm_mm']:.1f} mm = ±{d['screw_turns_pm']:.0f} tours ; "
                     f"effort vis {d['F_screw_N']:.0f} N (retour {d['F_return_N']:.0f} N), couple {d['torque_Nm']*1e3:.1f} mN·m, "
                     f"irréversible : {d['self_locking']}")
            print(line)

    # temps de course (référence) à 2 tr/s
    ref = designs["reference_motorise"]
    out["stroke_time_s"] = ref["screw_turns_pm"] * 2 / 2.0
    # --- 4) Raideurs et fréquence de pompage ----------------------------------------
    k_wedge = 2.0e8           # cage à aiguilles sous le coin (ordre de grandeur, à confirmer fournisseur)
    k_screw_h = 210e9 * np.pi * 0.0049**2 / 4 / 0.040    # noyau M6 fin, 40 mm libres
    k_screw_v = k_screw_h / ref["tan_wedge"] ** 2
    k_ring = 3.0e7            # profilé 45×90 sous un appui (valeur basse de frame.py si disponible)
    ff = RES / "frame.json"
    if ff.exists():
        k_ring = min(json.loads(ff.read_text())["k_local_support_N_m"])
    chain = []
    for h in hz:
        k = 1 / (1 / h["k_vertical_N_m"] + 1 / k_wedge + 1 / k_screw_v)
        chain.append(k)
    m_tot = R.sum() / 9.81
    f_bounce = np.sqrt(sum(chain) / m_tot) / (2 * np.pi)
    out["stiffness"] = dict(k_hertz=[h["k_vertical_N_m"] for h in hz], k_wedge=k_wedge, k_screw_vertical=k_screw_v,
                            k_support_chain=chain, k_frame_local_assumed=k_ring, mass_kg=m_tot,
                            f_bounce_Hz=f_bounce,
                            f_bounce_with_frame_Hz=np.sqrt(sum(1 / (1 / k + 1 / k_ring) for k in chain) / m_tot) / (2 * np.pi))
    if verbose:
        st = out["stiffness"]
        print(f"Raideur d'appui (Hertz + coin + vis) : {np.round(np.array(chain)/1e6,0).tolist()} N/µm ; "
              f"pompage {f_bounce:.0f} Hz (avec cadre local {st['f_bounce_with_frame_Hz']:.0f} Hz) ; masse portée {m_tot:.1f} kg")
        print(f"Temps de course totale (référence, 2 tr/s) : {out['stroke_time_s']:.0f} s")
    RES.mkdir(parents=True, exist_ok=True)
    (RES / "kinematic_coupling.json").write_text(json.dumps(out, indent=1, default=float))
    if verbose:
        print("→ results/kinematic_coupling.json")
    return out


if __name__ == "__main__":
    run()
