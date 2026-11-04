"""Budget de force parasite dans le plan (table de caractérisation).

Correction de l'utilisateur (2026-11-04) : les palets portent des actionneurs
électrostatiques radiaux. La table sert à **caractériser** le mouvement dans le plan
que produit cet actionnement. Toute force parasite dans le plan est donc une
**erreur de mesure** et doit rester ≪ F_act. Les sources de force parasite sont la
pente locale, le crantage, le balourd et les courants d'air.

Le paramètre principal est l'accélération parasite admissible a_par, exprimée en
pente équivalente θ = a_par/g. Les niveaux étudiés sont 5, 10, 20, 30 et 50 µrad.
Pour chaque niveau, le script donne :
  1. la répartition du budget entre les postes (somme quadratique ≤ θ) ;
  2. les exigences déduites : planéité et procédé, thermique, recalage,
     équilibrage des palets, tolérance des orifices, courants d'air ;
  3. l'erreur de position sur une fenêtre de mesure T = 1 / 5 / 10 / 30 s ;
  4. le rapport F_par/F_act pour m = 2…10 g et F_act = 0,1 µN … 1 mN ;
  5. la faisabilité et le coût relatif.

Erreur de position. Le calcul balistique ½·a·T² est celui demandé. La valeur
amortie a·τ·[T − τ(1 − e^(−T/τ))] tient compte du frottement de Couette
(τ = m·h/(μA), soit 18 s à 2 g et 63 s à 10 g) ; elle est plus petite quand T est
de l'ordre de τ.

Répartition. Les postes d'exploitation (réglage, stabilité, sol, poids propre,
pression, thermique) gardent la valeur de la conception actuelle. Ils ne sont
réduits vers leur plancher que si nécessaire. Le reste de la variance va aux postes
coûteux (planéité, crantage, dispersion des orifices, balourd, courants d'air), au
prorata de `DRIVERS` et chacun au moins à son plancher. Un niveau est non
réalisable si la somme quadratique des planchers dépasse θ.

Crantage (lot aéro). Il vaut 25–34 µrad RMS brut, comme force périodique de
moyenne nulle. Seule une correction a posteriori de la mesure, par une carte de
crantage étalonnée, le ramène à 5–10 µrad. Un niveau qui exige moins que le
crantage brut suppose donc cette correction : c'est **une décision utilisateur à
prendre** (ce n'est pas un pilotage des palets).

Sources des sensibilités :
  - planéité : `machining.py` ;
  - poids propre, frottement, pression : `support_study.json` ;
  - thermique : `thermal.json` ;
  - réglage : `kinematic_coupling.json` ;
  - lot aéro (`docs/02_aeraulique.md`) : balourd 0,9 µrad/µm, dispersion des
    orifices 8,5 µrad RMS pour ±0,005 mm, courants d'air 5 µrad pour 17 mm/s,
    crantage 33 µrad RMS (10 g).

    python3 -m calc.structure.passive_budget
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np

from calc.common.params import REPO_ROOT, load_params
from calc.structure.machining import puck_filter

RES = REPO_ROOT / "calc" / "structure" / "results"
FIG = REPO_ROOT / "calc" / "structure" / "figures"

LEVELS_URAD = (5, 10, 20, 30, 50)  # pente équivalente admissible θ = a_par/g
THRESHOLDS_URAD = LEVELS_URAD
MARGIN = 1.0                       # somme quadratique ≤ θ
WINDOWS_S = (1, 5, 10, 30)
MASSES_G = (2, 5, 10)
TAU_S = {2: 18.0, 5: 35.0, 10: 63.0}   # amortissement de Couette (lot aéro)
F_ACT_N = (1e-7, 1e-6, 1e-5, 1e-4, 1e-3)
COGGING_RAW, COGGING_CORR = 33.0, 7.5  # µrad RMS : brut (10 g) / après correction a posteriori (5–10)

# Hypothèses d'exploitation (à confirmer sur site)
FRAME_TILT_PER_K_ROOM = 3.6        # µrad par K de variation du local : gradient latéral du bâti = 10 % de la variation, montants de 0,79 m sur 0,5 m
FLOOR_DRIFT_URAD_H = 1.0           # µrad/h, dalle béton de rez-de-chaussée (hypothèse ; 2–5 en étage)
UNBALANCE_URAD_PER_UM = 0.9        # µrad par µm de décentrage du centre de gravité (lot aéro)
DISPERSION_URAD_PER_UM = 8.5 / 5.0  # µrad RMS par µm de tolérance ± sur Ø0,30 (2 g)
AIR_REF = (5.0, 17.0)              # 5 µrad pour 17 mm/s (2 g) ; pente ∝ v²

# Parts de variance (somme = 1) et planchers techniques (µrad)
SHARE = {
    "planeite": 0.30, "crantage": 0.15, "dispersion_orifices": 0.15, "balourd": 0.08, "courants_air": 0.08,
    "reglage": 0.06, "stabilite_bati": 0.06, "sol": 0.06, "poids_propre": 0.04,
    "pression": 0.04, "thermique": 0.04,
}
LABELS = {
    "reglage": "Réglage global (pas moteur, bruit et offset des ADXL355)",
    "stabilite_bati": "Stabilité du nivellement entre deux recalages (thermique du bâti)",
    "sol": "Sol / bâtiment (dérive entre deux recalages)",
    "planeite": "Planéité de la face supérieure (forme + ondulation)",
    "poids_propre": "Poids propre sur appuis (finition sur appuis, frottement)",
    "pression": "Pression (écart à la pression de finition)",
    "thermique": "Thermique de la plaque (écart air/plaque, rampe du local)",
    "balourd": "Balourd des palets (0,9 µrad/µm)",
    "dispersion_orifices": "Dispersion des orifices (lot aéro)",
    "crantage": "Crantage (lot aéro ; < 33 µrad ⇒ correction a posteriori)",
    "courants_air": "Courants d'air résiduels (lot aéro)",
}


def load(name):
    f = RES / name
    return json.loads(f.read_text()) if f.exists() else None


def floors_and_nominal(P):
    """Plancher technique et valeur de la conception de référence actuelle, par poste (µrad)."""
    ss, th, kc = load("support_study.json"), load("thermal.json"), load("kinematic_coupling.json")
    a = P["zones"]["perforated_square_mm"] / 2 * 1e-3
    s = P["zones"]["working_square_mm"] / 2 * 1e-3
    sel = ss["selected"]["by_thickness"]["35"]["B"]
    fric = sel["friction"]["mu0.15"]["worst_urad"]
    pos = sel["finishing"]["rss_urad"]
    p_full = sel["P"]["slope_peak_urad"]
    p_op = P["operating"]
    # pression : finition à mi-plage de service ⇒ écart ±(p_max − p_min)/2
    p_range = (p_op["p_plenum_max_Pa"] - p_op["p_plenum_min_Pa"]) / 2
    p_mid = p_full * p_range / p_op["p_plenum_max_Pa"]
    step = kc["wedge"]["reference_motorise"]["urad_per_step"]
    emb = th["adxl_base"]["tilt_feet_urad"]
    therm_tr = th["step_1K"]["Qmax"]["peak_urad_per_K"]
    therm_ramp = max(v["slope_urad"] for v in th["room_ramp_1K_per_h"].values())
    slope_per_um = 2 * 1e-6 * s / a**2 * 1e6                         # µrad par µm de planéité (cylindre)
    floor = {
        "reglage": float(np.hypot(step / np.sqrt(3), emb)),          # bruit et offset réductibles (moyennage, retournements)
        "stabilite_bati": FRAME_TILT_PER_K_ROOM * 0.1,                # local à 0,1 K entre recalages
        "sol": FLOOR_DRIFT_URAD_H * 0.25,                             # recalage automatique toutes les 15 min
        "planeite": slope_per_um * 0.5 / 0.85,                        # 0,5 µm de forme (85 % du poste) : meilleur tournage diamant optique sur 520
        "poids_propre": float(np.hypot(pos, fric * 0.1)),             # rouleaux sur roulements : frottement ÷ 10
        "pression": 0.25 * p_mid,                                     # finition à la pression d'usage d'une seule masse
        "thermique": 0.3,                                             # air régulé à ±0,1 K de la plaque, local ±0,2 K/h
        "balourd": UNBALANCE_URAD_PER_UM * 2.0,                       # équilibrage à 2 µm
        "dispersion_orifices": DISPERSION_URAD_PER_UM * 2.0,          # ±0,002 mm (électroérosion / tri des forets)
        "courants_air": 1.0,                                          # enceinte fermée, v ≈ 8 mm/s
        "crantage": COGGING_CORR,                                     # carte étalonnée et soustraite de la mesure
    }
    nominal = {
        "reglage": 1.4, "stabilite_bati": FRAME_TILT_PER_K_ROOM * 0.5, "sol": FLOOR_DRIFT_URAD_H * 1.0,
        "planeite": slope_per_um * 2.8 / 0.85, "poids_propre": float(np.hypot(pos, fric)), "pression": p_full,
        "thermique": therm_tr, "balourd": UNBALANCE_URAD_PER_UM * 10, "dispersion_orifices": 8.5,
        "courants_air": 5.0, "crantage": COGGING_RAW,
    }
    sens = dict(slope_per_um=slope_per_um, a=a, s=s, therm_tr=therm_tr, therm_ramp=therm_ramp,
                step=step, emb=emb, p_full=p_full, p_mid=p_mid, fric=fric, pos=pos)
    return floor, nominal, sens


DRIVERS = {"planeite": 0.35, "crantage": 0.25, "dispersion_orifices": 0.15, "balourd": 0.125, "courants_air": 0.125}


def allocate(target, floor, nominal):
    """Répartition en deux niveaux.

    1. Les postes d'exploitation (réglage, stabilité, sol, poids propre, pression,
       thermique) gardent la valeur de la conception actuelle. Ils ne sont réduits vers
       leur plancher, d'un même facteur, que si le budget l'exige.
    2. La variance restante va aux postes « coûteux » (planéité, dispersion des orifices,
       balourd, courants d'air) au prorata de `DRIVERS`, chacun au moins à son plancher.

    Retourne None si les planchers ne tiennent pas dans la cible."""
    ops = [k for k in SHARE if k not in DRIVERS]
    if np.sqrt(sum(floor[k]**2 for k in SHARE)) > target:
        return None
    for lam in np.linspace(0.0, 1.0, 201):          # 0 : valeurs actuelles ; 1 : planchers
        alloc = {k: nominal[k] + lam * (floor[k] - nominal[k]) for k in ops}
        rem = target**2 - sum(v**2 for v in alloc.values())
        if rem <= 0:
            continue
        fixed = {}
        for _ in range(len(DRIVERS) + 1):
            free = [k for k in DRIVERS if k not in fixed]
            rv = rem - sum(v**2 for v in fixed.values())
            if rv <= 0 or not free:
                break
            w = sum(DRIVERS[k] for k in free)
            a = {k: np.sqrt(rv * DRIVERS[k] / w) for k in free}
            low = [k for k in free if a[k] < floor[k]]
            if not low:
                fixed.update(a)
                break
            for k in low:
                fixed[k] = floor[k]
        if len(fixed) == len(DRIVERS) and sum(v**2 for v in fixed.values()) <= rem * (1 + 1e-9):
            alloc.update(fixed)
            alloc["_ops_reduction"] = float(lam)
            return alloc
    return None


def finishing_process(delta_um):
    """Procédé capable, prestataires plausibles et coût relatif de la finition."""
    if delta_um >= 2.8:
        return ("fly-cut diamant de précision sur appuis de service (référence actuelle)",
                "ateliers de fly-cut et de surfaçage de précision (Europe) ; référence actuelle", 1.0)
    if delta_um >= 1.5:
        return ("tournage/fly-cut diamant mono-pointe sur machine ultra-précise (classe Moore, LT Ultra, Precitech), "
                "montage sur appuis de service, métrologie interférométrique ou déflectométrique",
                "ateliers d'optique métallique : instituts Fraunhofer (IOF, IPT), fabricants de miroirs aluminium "
                "(plausibles, non contactés)", 3.0)
    if delta_um >= 0.5:
        return ("tournage diamant optique + passes de correction sur carte mesurée ; le polissage optique est exclu "
                "(abrasif dans 5 935 orifices, bords de trous arrondis)",
                "grands opticiens (Safran Reosc, Winlight, Fraunhofer IOF) ; capacité 520 mm percée non confirmée", 8.0)
    return ("hors d'atteinte pour une plaque aluminium percée de 520 mm", "—", float("inf"))


def requirements(alloc, sens):
    a, s = sens["a"], sens["s"]
    pl = alloc["planeite"]
    # planéité : 85 % de l'allocation pour la forme (cylindre), 50 % pour l'ondulation λ = 100 mm
    delta = 0.85 * pl / sens["slope_per_um"]
    d100 = 0.5 * pl / (np.pi / 0.100 * puck_filter(0.100)) * 1e-6 * 1e6
    proc, suppliers, cost_fin = finishing_process(delta)
    # réglage : bruit admissible ⇒ temps de moyennage (4 capteurs, 25 µg/√Hz) ; offset ADXL résiduel
    off = 0.5 if alloc["reglage"] < 1.4 else 1.0
    n2 = alloc["reglage"]**2 - (sens["step"] / np.sqrt(3))**2 - sens["emb"]**2 - off**2
    if n2 <= 0.05:
        off = 0.3
        n2 = max(alloc["reglage"]**2 - (sens["step"] / np.sqrt(3))**2 - sens["emb"]**2 - off**2, 0.01)
    n = np.sqrt(n2)
    T_avg = (25 / (2 * n))**2 / 2
    rev_h = 24 if off >= 1.0 else (4 if off >= 0.5 else 1)
    # stabilité, sol
    dT_room = alloc["stabilite_bati"] / FRAME_TILT_PER_K_ROOM
    dt_recal_h = alloc["sol"] / FLOOR_DRIFT_URAD_H
    # poids propre
    pp = alloc["poids_propre"]
    if pp >= np.hypot(sens["pos"], sens["fric"]):
        pp_req = "finition sur appuis de service, rouleaux fixes graissés (µ 0,15)"
    elif pp >= np.hypot(sens["pos"], sens["fric"] * 0.1):
        pp_req = "finition sur appuis + rouleaux montés sur roulements (frottement de roulement)"
    else:
        pp_req = "non tenable"
    # pression
    pr = alloc["pression"]
    if pr >= sens["p_full"]:
        pr_req = "finition à 0 Pa ou à toute pression"
    elif pr >= sens["p_mid"]:
        pr_req = "finition avec le plenum à la pression médiane de service (soufflage pendant la coupe)"
    else:
        pr_req = "finition à la pression d'usage ; une seule plage de masse par réglage"
    # thermique : moitié de la variance à l'écart air/plaque, moitié à la rampe du local
    th = alloc["thermique"] / np.sqrt(2)
    dT_air = th / sens["therm_tr"]
    ramp = th / sens["therm_ramp"]
    # balourd, dispersion, courants
    e_um = alloc["balourd"] / UNBALANCE_URAD_PER_UM
    tol_um = alloc["dispersion_orifices"] / DISPERSION_URAD_PER_UM
    v_air = AIR_REF[1] * np.sqrt(alloc["courants_air"] / AIR_REF[0])
    cog = ("brut acceptable" if alloc["crantage"] >= COGGING_RAW - 1e-9 else
           f"correction a posteriori requise (résidu ≤ {alloc['crantage']:.0f} µrad RMS)")
    return dict(cogging=cog, flatness_360_um=delta, flatness_100_um=d100, process=proc, suppliers=suppliers,
                averaging_s=T_avg, reversal_every_h=rev_h, room_dT_between_recal_K=dT_room,
                recal_interval_h=dt_recal_h, room_ramp_K_h=ramp, air_minus_plate_K=dT_air,
                deadweight=pp_req, pressure=pr_req, puck_unbalance_um=e_um, orifice_tol_um=tol_um,
                air_speed_mm_s=v_air, cost_finishing=cost_fin)


def cost_index(req):
    """Coût relatif de la plaque, des palets et de l'installation (référence = 1)."""
    c = req["cost_finishing"]
    c += 0 if req["puck_unbalance_um"] >= 10 else (0.5 if req["puck_unbalance_um"] >= 4 else 1.5)
    c += 0 if req["orifice_tol_um"] >= 5 else (0.5 if req["orifice_tol_um"] >= 3 else 2.0)
    c += 0 if req["room_ramp_K_h"] >= 0.5 else (0.5 if req["room_ramp_K_h"] >= 0.2 else 2.0)
    c += 0 if req["air_minus_plate_K"] >= 1.0 else (0.3 if req["air_minus_plate_K"] >= 0.3 else 1.0)
    c += 0 if req["air_speed_mm_s"] >= 17 else (0.3 if req["air_speed_mm_s"] >= 10 else 1.0)
    return c


def measurement_error(theta_urad):
    """Erreur de position et rapport F_par/F_act pour une pente équivalente θ."""
    a = 9.81 * theta_urad * 1e-6
    pos = {}
    for T in WINDOWS_S:
        damped = {m: a * TAU_S[m] * (T - TAU_S[m] * (1 - np.exp(-T / TAU_S[m]))) for m in MASSES_G}
        pos[str(T)] = dict(ballistic_um=0.5 * a * T**2 * 1e6, damped_um={str(m): v * 1e6 for m, v in damped.items()})
    force = {}
    for m in MASSES_G:
        Fp = m * 1e-3 * a
        force[str(m)] = dict(F_par_N=Fp, ratio={f"{F:.0e}": Fp / F for F in F_ACT_N},
                             F_act_min_1pct_N=100 * Fp, F_act_min_10pct_N=10 * Fp)
    return dict(a_par_um_s2=a * 1e6, position=pos, force=force)


def run(P=None, verbose=True):
    P = P or load_params()
    floor, nominal, sens = floors_and_nominal(P)
    floor_rss = float(np.sqrt(sum(v**2 for v in floor.values())))
    nominal_rss = float(np.sqrt(sum(v**2 for v in nominal.values())))
    rows = []
    for th in THRESHOLDS_URAD:
        target = MARGIN * th
        # d'abord sans correction du crantage (plancher = crantage brut), sinon avec correction
        floor_nc = dict(floor, crantage=COGGING_RAW)
        if nominal_rss <= target:                       # la conception actuelle suffit
            alloc = dict(nominal, _ops_reduction=0.0)
        else:
            alloc = allocate(target, floor_nc, nominal)
        no_correction = alloc is not None
        if alloc is None:
            alloc = allocate(target, floor, nominal)
        feasible = alloc is not None
        ops_red = alloc.pop("_ops_reduction") if feasible else None
        if not feasible:
            alloc = dict(floor)
        rss = float(np.sqrt(sum(v**2 for v in alloc.values())))
        arith = float(sum(alloc.values()))
        req = requirements(alloc, sens)
        if feasible and not np.isfinite(req["cost_finishing"]):
            feasible = False
        cost = cost_index(req) if feasible else float("inf")
        tight = [k for k in DRIVERS if alloc[k] < nominal[k] - 1e-9]
        if not feasible:
            verdict = "non réalisable"
        elif not tight:
            verdict = f"réalisable avec la conception actuelle (somme quadratique {nominal_rss:.0f} µrad)"
        elif req["cost_finishing"] <= 1:
            verdict = "réalisable : palets, orifices et écran à resserrer"
        elif req["cost_finishing"] <= 3 and (ops_red or 0) == 0:
            verdict = "réalisable : finition optique (classe 1,5–2,8 µm)"
        else:
            verdict = "à la limite : finition optique de pointe, postes près du plancher"
        if feasible and alloc["crantage"] < COGGING_RAW - 1e-9:
            verdict += " ; suppose la correction a posteriori du crantage"
        rows.append(dict(theta_dep_urad=th, theta_urad=th, measurement=measurement_error(th),
                         feasible_without_cogging_correction=bool(no_correction), target_rss_urad=target, feasible=feasible, verdict=verdict,
                         ops_reduction=ops_red,
                         alloc_urad=alloc, rss_urad=rss, arithmetic_urad=arith,
                         requirements=req, cost_index=cost))
    floor_nc_rss = float(np.sqrt(sum(v**2 for v in dict(floor, crantage=COGGING_RAW).values())))
    out = dict(margin=MARGIN, floor_urad=floor, floor_rss_urad=floor_rss,
               min_theta_without_cogging_correction_urad=floor_nc_rss, nominal_urad=nominal,
               nominal_rss_urad=nominal_rss, min_feasible_theta_urad=floor_rss / MARGIN,
               hypotheses=dict(frame_tilt_per_K_room=FRAME_TILT_PER_K_ROOM, floor_drift_urad_h=FLOOR_DRIFT_URAD_H,
                               unbalance_urad_per_um=UNBALANCE_URAD_PER_UM,
                               dispersion_urad_per_um=DISPERSION_URAD_PER_UM, air_ref=AIR_REF, share=SHARE),
               sensitivities=sens, rows=rows, labels=LABELS)
    RES.mkdir(parents=True, exist_ok=True)
    (RES / "passive_budget.json").write_text(json.dumps(out, indent=1, default=float, ensure_ascii=False))

    # tableau markdown
    keys = list(SHARE)
    head = "| Poste | Plancher | Conception actuelle | " + " | ".join(f"θ = {t} µrad" for t in THRESHOLDS_URAD) + " |"
    lines = [head, "|---" * (3 + len(THRESHOLDS_URAD)) + "|"]
    for k in keys:
        lines.append(f"| {LABELS[k]} | {floor[k]:.1f} | {nominal[k]:.1f} | " +
                     " | ".join((f"{r['alloc_urad'][k]:.1f}" if r["feasible"] else "—") for r in rows) + " |")
    lines.append(f"| **Somme quadratique** (cible θ) | {floor_rss:.1f} | {nominal_rss:.1f} | " +
                 " | ".join((f"{r['rss_urad']:.1f}" if r["feasible"] else "**NR**") for r in rows) + " |")
    lines.append("")
    lines.append("| Exigence | " + " | ".join(f"θ = {t} µrad" for t in THRESHOLDS_URAD) + " |")
    lines.append("|---" * (1 + len(THRESHOLDS_URAD)) + "|")

    def rq(name, fmt):
        return f"| {name} | " + " | ".join((fmt(r["requirements"]) if r["feasible"] else "—") for r in rows) + " |"
    lines += [rq("Crantage", lambda q: q["cogging"]),
              rq("Planéité zone percée (µm)", lambda q: f"{q['flatness_360_um']:.1f}"),
              rq("Planéité par 100 × 100 (µm)", lambda q: f"{q['flatness_100_um']:.2f}"),
              rq("Procédé de finition", lambda q: q["process"].split(",")[0].split(";")[0].split("(")[0].strip()),
              rq("Procédé — prestataires plausibles", lambda q: q["suppliers"]),
              rq("Équilibrage des palets (µm)", lambda q: f"≤ {q['puck_unbalance_um']:.1f}"),
              rq("Tolérance Ø orifices (± µm)", lambda q: f"{q['orifice_tol_um']:.1f}"),
              rq("Vitesse d'air au niveau des palets (mm/s)", lambda q: f"≤ {q['air_speed_mm_s']:.0f}"),
              rq("Écart air soufflé / plaque (K)", lambda q: f"≤ {q['air_minus_plate_K']:.2f}"),
              rq("Rampe du local (K/h)", lambda q: f"≤ {q['room_ramp_K_h']:.2f}"),
              rq("Variation du local entre recalages (K)", lambda q: f"≤ {q['room_dT_between_recal_K']:.2f}"),
              rq("Intervalle de recalage d'inclinaison (h)", lambda q: f"{q['recal_interval_h']:.2f}"),
              rq("Retournement des ADXL355 (toutes les … h)", lambda q: f"{q['reversal_every_h']}"),
              rq("Moyennage ADXL355 (s)", lambda q: f"{q['averaging_s']:.0f}"),
              "| Verdict | " + " | ".join(r["verdict"] for r in rows) + " |",
              "| Coût relatif (finition + palets + installation ; référence 1) | " +
              " | ".join((f"{r['cost_index']:.1f}" if r["feasible"] else "∞") for r in rows) + " |"]
    # erreurs de mesure
    lines += ["", "| θ (µrad) | a_par (µm/s²) | " + " | ".join(f"½aT², T = {T} s (µm)" for T in WINDOWS_S) +
              " | amorti 2 g / 10 g, T = 30 s (µm) |", "|---" * (3 + len(WINDOWS_S)) + "|"]
    for r in rows:
        me = r["measurement"]
        lines.append(f"| {r['theta_urad']} | {me['a_par_um_s2']:.0f} | " +
                     " | ".join(f"{me['position'][str(T)]['ballistic_um']:.1f}" for T in WINDOWS_S) +
                     f" | {me['position']['30']['damped_um']['2']:.0f} / {me['position']['30']['damped_um']['10']:.0f} |")
    lines += ["", "| θ (µrad) | m (g) | F_par (µN) | " + " | ".join(f"F_par/F_act, F_act = {F*1e6:g} µN" for F in F_ACT_N) +
              " | F_act min. pour 1 % (µN) |", "|---" * (4 + len(F_ACT_N)) + "|"]
    for r in rows:
        for m in MASSES_G:
            fo = r["measurement"]["force"][str(m)]
            lines.append(f"| {r['theta_urad']} | {m} | {fo['F_par_N']*1e6:.3f} | " +
                         " | ".join(f"{fo['ratio'][f'{F:.0e}']:.2g}" for F in F_ACT_N) +
                         f" | {fo['F_act_min_1pct_N']*1e6:.1f} |")
    (RES / "passive_budget_table.md").write_text("\n".join(lines) + "\n")

    if verbose:
        print(f"Planchers techniques : somme quadratique {floor_rss:.1f} µrad ⇒ θ minimal réalisable ≈ "
              f"{floor_rss/MARGIN:.1f} µrad ; conception actuelle (crantage brut compris) : {nominal_rss:.1f} µrad")
        for r in rows:
            q = r["requirements"]
            if r["feasible"]:
                print(f"θ {r['theta_dep_urad']:2d} µrad (a_par {r['measurement']['a_par_um_s2']:.0f} µm/s², ½aT² à 10 s : {r['measurement']['position']['10']['ballistic_um']:.0f} µm) : {r['verdict']} ; RSS {r['rss_urad']:.1f} (arith. {r['arithmetic_urad']:.1f}) ; "
                      f"planéité {q['flatness_360_um']:.1f} µm ({q['flatness_100_um']:.2f}/100) ; balourd ≤ {q['puck_unbalance_um']:.1f} µm ; "
                      f"orifices ±{q['orifice_tol_um']:.1f} µm ; air ≤ {q['air_speed_mm_s']:.0f} mm/s ; ΔT air/plaque ≤ {q['air_minus_plate_K']:.2f} K ; "
                      f"local ≤ {q['room_ramp_K_h']:.2f} K/h ; recalage toutes les {q['recal_interval_h']:.1f} h ; coût ×{r['cost_index']:.1f}")
            else:
                print(f"θ {r['theta_dep_urad']:2d} µrad : {r['verdict']}")
        print("→ results/passive_budget.json, results/passive_budget_table.md, figures/passive_budget.png")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(9, 4.5))
    feas = [r for r in rows if r["feasible"]]
    x = np.arange(len(feas))
    bottom = np.zeros(len(feas))
    for k in keys:
        v = np.array([r["alloc_urad"][k] ** 2 for r in feas])
        ax.bar(x, v, bottom=bottom, label=LABELS[k], width=0.6)
        bottom += v
    ax.set_xticks(x)
    ax.set_xticklabels([f"θ = {r['theta_dep_urad']} µrad" for r in feas])
    ax.set_ylabel("variance allouée (µrad²)")
    ax.set_yscale("log")
    ax.set_title(f"Budget de force parasite : répartition de θ² ; planchers : {floor_rss:.1f} µrad RSS", fontsize=10)
    ax.legend(fontsize=7, loc="upper left")
    ax.grid(alpha=0.3, which="both", axis="y")
    fig.tight_layout()
    fig.savefig(FIG / "passive_budget.png", dpi=120)
    plt.close(fig)
    return out


if __name__ == "__main__":
    run()
