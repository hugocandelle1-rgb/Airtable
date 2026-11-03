"""Usinage, tolérances et budget de pente (référence « précision » et variante
économique).

1. Conversion défaut de forme → pente locale (méthode du skill
   tolerancement-iso-gps) : forme cylindrique (pire cas d'un défaut de flèche δ
   sur la zone percée), bombé sphérique, ondulation (λ, A) filtrée par le palet
   Ø30 (moyenne sur disque : facteur 2·J1(x)/x, x = π·D/λ).
2. Tolérances déduites des allocations (référence 30 µrad, économique : on
   chiffre la pente résultante de 15–20 µm).
3. Temps machine du perçage (≈ 6 000 et ≈ 17 000 trous) et de la finition.
4. Budget de pente complet des deux variantes, à partir des résultats de
   support_study, thermal et kinematic_coupling.

    python3 -m calc.structure.machining
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
from scipy.special import j1

from calc.common.params import REPO_ROOT, load_params
from calc.structure.homogenization import hex_hole_count

RES = REPO_ROOT / "calc" / "structure" / "results"


# -----------------------------------------------------------------------------
# 1) Défaut de forme → pente
# -----------------------------------------------------------------------------

def slope_cylinder(delta, a_zone, s_eval):
    """Défaut cylindrique w = δ·(x/a)² (flèche δ au bord de la zone de demi-côté
    a, PV = δ) : pente max dans le carré |x| ≤ s_eval. Le plan retiré ne change
    pas la pente d'une forme symétrique."""
    return 2 * delta * s_eval / a_zone**2


def slope_bowl(delta, a_zone, s_eval):
    """Bombé sphérique w = δ·(x²+y²)/(2a²) (PV δ entre centre et coin de la zone
    percée) : pente max au coin de la zone d'évaluation."""
    return delta * np.sqrt(2) * s_eval / a_zone**2


def puck_filter(lam, D=0.030):
    x = np.pi * D / lam
    return 2 * j1(x) / x


def slope_wave(pv, lam, D=0.030):
    """Ondulation sinusoïdale PV, longueur d'onde λ : pente crête vue par le palet."""
    return np.pi * pv / lam * abs(puck_filter(lam, D))


def flatness_for_slope(theta, a_zone, s_eval):
    """Tolérance de planéité (forme cylindrique, pire cas) donnant la pente θ."""
    return theta * a_zone**2 / (2 * s_eval)


# -----------------------------------------------------------------------------
# 3) Temps de perçage
# -----------------------------------------------------------------------------

def drilling_time(n_holes, h_mm, cb_mm=2.0, orifice_mm=0.30, through_coolant=True, rate_eur_h=90.0, web_mm=1.20):
    """Temps machine (h) et coût indicatif du perçage. Hypothèses d'atelier
    (centre d'usinage 24 000 tr/min, forets carbure) :
      lamage : avant-trou 2×D puis foret long à lubrification centrale
               vc 120 m/min, f 0,04 mm/tr ; sans lubrification centrale : débourrages ⇒ ×2,2 ;
      orifice : foret carbure Ø0,3–0,4, 24 000 tr/min, f = 0,0125·d mm/tr, 3 débourrages ;
      positionnement 0,3 s par trou et par opération ; changement préventif du
      foret d'orifice tous les 1 500 trous (1,5 min), du foret long tous les 1 500 trous ;
      2 mises en position (face inférieure, face supérieure) × 2 h, contrôle d'échantillonnage."""
    depth = h_mm - web_mm
    n_cb = min(24000, 120e3 / (np.pi * cb_mm))
    t_cb = depth / (n_cb * 0.04) * 60 + 2.0 + 0.6 + 0.3      # perçage + entrée lente du foret long + avant-trou + position
    if not through_coolant:
        t_cb *= 2.2
    f_o = 0.0125 * orifice_mm
    t_or = (web_mm + 0.35) / (24000 * f_o) * 60 + 3 * 0.15 + 0.3
    tool_changes = 2 * np.ceil(n_holes / 1500)
    t_total = n_holes * (t_cb + t_or) / 3600 + tool_changes * 1.5 / 60 + 4.0 + 0.002 * n_holes / 60 * 20
    drills = dict(orifice=int(np.ceil(n_holes / 1500)) + 1, counterbore=int(np.ceil(n_holes / 1500)) + 1)
    cost = t_total * rate_eur_h + drills["orifice"] * 35 + drills["counterbore"] * 90
    return dict(n_holes=n_holes, t_counterbore_s=t_cb, t_orifice_s=t_or, hours=t_total, drills=drills,
                cost_eur=cost, rate_eur_h=rate_eur_h)


# -----------------------------------------------------------------------------
# 4) Budget
# -----------------------------------------------------------------------------

def load(name):
    f = RES / name
    return json.loads(f.read_text()) if f.exists() else None


def rss(vals):
    return float(np.sqrt(np.sum(np.square(vals))))


def run(P=None, verbose=True):
    P = P or load_params()
    pt = P["performance_targets"]
    a_perf = P["zones"]["perforated_square_mm"] / 2 * 1e-3
    s_work = P["zones"]["working_square_mm"] / 2 * 1e-3
    out = {}

    # 1-2) tolérances
    conv = []
    for d_um in (2, 3, 4, 6, 10, 15, 20):
        d = d_um * 1e-6
        conv.append(dict(flatness_um=d_um, cylinder_urad=slope_cylinder(d, a_perf, s_work) * 1e6,
                         bowl_urad=slope_bowl(d, a_perf, s_work) * 1e6))
    waves = []
    for lam_mm in (10, 20, 30, 50, 80, 100, 150):
        lam = lam_mm * 1e-3
        waves.append(dict(lambda_mm=lam_mm, filter=float(puck_filter(lam)),
                          slope_urad_per_um=slope_wave(1e-6, lam) * 1e6))
    alloc_ref = 30e-6
    t_ref = flatness_for_slope(alloc_ref * 0.85, a_perf, s_work)      # 85 % de l'allocation sur la forme
    # tolérance locale sur 100 × 100 : ondulation λ = 100 mm (pire cas peu filtré), 50 % de l'allocation
    t_loc = 0.5 * alloc_ref / (np.pi / 0.100 * puck_filter(0.100))
    out["tolerancing"] = dict(conversion=conv, waviness=waves,
                              reference=dict(allocation_urad=alloc_ref * 1e6, flatness_perforated_um=t_ref * 1e6,
                                             flatness_100_um=t_loc * 1e6,
                                             cdc_6um_cylinder_urad=slope_cylinder(6e-6, a_perf, s_work) * 1e6,
                                             cdc_2um_per_100_urad=slope_wave(2e-6, 0.1) * 1e6))
    # variante économique : surfaçage 15–20 µm + traces de fraise
    eco = []
    for d_um in (15, 20):
        form = slope_cylinder(d_um * 1e-6, a_perf, s_work)
        marks = slope_wave(2e-6, 0.080)            # traces de passes (fraise Ø100, pas de balayage 80 mm), 2 µm PV
        eco.append(dict(flatness_um=d_um, form_urad=form * 1e6, marks_urad=marks * 1e6,
                        total_urad=(form + marks) * 1e6))
    out["tolerancing"]["economique"] = eco
    if verbose:
        tr = out["tolerancing"]["reference"]
        print(f"Planéité → pente (zone percée {2*a_perf*1e3:.0f}, évaluée sur {2*s_work*1e3:.0f}) : " +
              ", ".join(f"{c['flatness_um']} µm → {c['cylinder_urad']:.0f} µrad" for c in conv))
        print(f"  CdC 6 µm (cylindrique) → {tr['cdc_6um_cylinder_urad']:.0f} µrad ; 2 µm/100 (λ = 100) → "
              f"{tr['cdc_2um_per_100_urad']:.0f} µrad")
        print(f"  Référence (allocation 30 µrad) : planéité zone percée ≤ {tr['flatness_perforated_um']:.1f} µm, "
              f"locale ≤ {tr['flatness_100_um']:.2f} µm/100×100")
        for e in eco:
            print(f"  Économique {e['flatness_um']} µm : forme {e['form_urad']:.0f} + traces {e['marks_urad']:.0f} = "
                  f"{e['total_urad']:.0f} µrad crête (à cartographier/compenser)")

    # 3) perçage
    hm = []
    for p_mm, d_o in ((5.0, 0.30), (4.82, 0.30), (4.23, 0.30), (2.94, 0.30)):
        n = hex_hole_count(P["zones"]["perforated_square_mm"], p_mm, margin_mm=1.0)
        for cool in (True, False):
            r = drilling_time(n, 35.0, 2.0, d_o, cool)
            r.update(pitch_mm=p_mm, orifice_mm=d_o, through_coolant=cool)
            hm.append(r)
    out["drilling"] = hm
    if verbose:
        for r in hm:
            print(f"Perçage pas {r['pitch_mm']} ({r['n_holes']} trous, Ø{r['orifice_mm']}, "
                  f"{'lubr. centrale' if r['through_coolant'] else 'débourrage'}) : {r['t_counterbore_s']:.1f} + "
                  f"{r['t_orifice_s']:.1f} s/trou → {r['hours']:.0f} h machine, ≈ {r['cost_eur']:.0f} €")

    # 4) budget
    ss, th, kc = load("support_study.json"), load("thermal.json"), load("kinematic_coupling.json")
    budget = {}
    if ss and th and kc:
        sel = ss["selected"]["by_thickness"]["35"]["B"]
        G = sel["G"]["slope_peak_urad"]
        Pp = sel["P"]["slope_peak_urad"]
        fr = sel["friction"]["mu0.15"]["worst_urad"]
        fin = sel["finishing"]
        P294 = max(r["P_B_urad"] for r in ss["pitch_sensitivity"] if r["h_mm"] == 35)
        step = kc["wedge"]["reference_motorise"]["urad_per_step"]
        # inclinaison : quantification + bruit ADXL355 moyenné (25 µg/√Hz, 4 capteurs, 100 s) + offset résiduel
        noise = 25 / np.sqrt(2 * 100) / np.sqrt(4)
        off = th["adxl_base"]["offset_residual_typ_urad"]
        tilt = rss([step / np.sqrt(3), noise, off, th["adxl_base"]["tilt_feet_urad"]])
        therm = th["step_1K"]["Qmax"]["peak_urad_per_K"] * 1.0           # écart air/plaque ≤ 1 K
        dead_ref = rss([fin["rss_urad"], 0.05 * fin["box_missing_urad"], fr])
        rows_ref = [("Inclinaison globale résiduelle (pas 0,64 µrad, 4 ADXL355 moyennés 100 s, offset compensé)", 5, tilt),
                    ("Défaut de planéité d'usinage (si ⏥ 3 µm / 0,8 µm sur 100×100 atteints)", 30, 30.0),
                    ("Poids propre : finition sur appuis de service (positions ±0,5 mm, lest ±5 %, frottement µ 0,15)", 10, dead_ref),
                    (f"Pression 0 → {P['operating']['p_plenum_max_Pa']:.0f} Pa (chemin B, e = 35, pas 5,00 ; pire pas 2,94 : {P294:.1f})", 5, Pp),
                    ("Thermique (écart air/plaque ≤ 1 K, transitoire)", 5, therm),
                    ("Sol / bâtiment (non calculé, surveillé par les ADXL355)", 5, 5.0)]
        dead_eco_fix = dead_ref
        rows_eco = [("Inclinaison globale (réglage manuel différentiel 0,26 µrad/div, lecture ADXL355)", 5, rss([1.0, noise, off])),
                    ("Planéité surfaçage 15–20 µm (forme + traces)", None, eco[1]["total_urad"]),
                    ("Poids propre : surfaçage sur montage 3 appuis (sinon +%.0f µrad)" % G, 10, dead_eco_fix),
                    ("Pression (identique)", 5, Pp),
                    ("Thermique (identique)", 5, therm),
                    ("Sol / paillasse (non calculé)", 5, 10.0)]
        for name, rows in (("reference", rows_ref), ("economique", rows_eco)):
            tot = rss([r[2] for r in rows])
            budget[name] = dict(rows=[dict(poste=r[0], allocation_urad=r[1], prevu_urad=r[2]) for r in rows],
                                total_rss_urad=tot)
        # variante économique après cartographie / compensation : la carte statique est retirée ;
        # restent la non-répétabilité (thermique, pression non compensée, frottement) et l'incertitude de carte
        map_unc = 10.0                       # incertitude de la carte de pente (dérive des palets, 10 mm de pas)
        resid = rss([tilt, Pp * 0.3, therm, fr, map_unc, 5.0])
        budget["economique"]["after_compensation_urad"] = resid
        budget["economique"]["map_uncertainty_urad"] = map_unc
        budget["economique"]["without_fixture_G_urad"] = G
        if verbose:
            for name in ("reference", "economique"):
                b = budget[name]
                print(f"Budget {name} :")
                for r in b["rows"]:
                    al = "—" if r["allocation_urad"] is None else f"{r['allocation_urad']:.0f}"
                    print(f"   {r['poste'][:95]:95s} alloc {al:>3s}  prévu {r['prevu_urad']:6.1f} µrad")
                print(f"   total (somme quadratique) : {b['total_rss_urad']:.1f} µrad"
                      + (f" ; après cartographie et compensation : ≈ {b['after_compensation_urad']:.0f} µrad" if name == "economique" else ""))
    out["budget"] = budget
    RES.mkdir(parents=True, exist_ok=True)
    (RES / "machining_budget.json").write_text(json.dumps(out, indent=1, default=float, ensure_ascii=False))
    if verbose:
        print("→ results/machining_budget.json")
    return out


if __name__ == "__main__":
    run()
