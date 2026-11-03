"""Chaîne complète du lot structure, puis écriture de
results/recommended_params.toml à partir des résultats.

    OPENBLAS_NUM_THREADS=1 python3 -m calc.structure.run_all            (≈ 3,5 min)
    python3 -m calc.structure.run_all --full     (+ cellules 3D d'homogénéisation, +70 s)
    python3 -m calc.structure.run_all --params-only   (réécrit seulement le TOML)

Ordre : plate_fe (validation) → homogenization → support_study → thermal →
materials → frame → kinematic_coupling → machining (budget).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from calc.common.params import REPO_ROOT

RES = REPO_ROOT / "calc" / "structure" / "results"

STEPS = [
    ("calc.structure.plate_fe", []),
    ("calc.structure.homogenization", ["--quick"]),
    ("calc.structure.support_study", []),
    ("calc.structure.thermal", []),
    ("calc.structure.materials", []),
    ("calc.structure.frame", []),
    ("calc.structure.kinematic_coupling", []),
    ("calc.structure.machining", []),
]


def run_steps(full=False):
    env = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1")
    t00 = time.time()
    for mod, args in STEPS:
        if full and mod.endswith("homogenization"):
            args = []
        t0 = time.time()
        print(f"=== {mod} {' '.join(args)}", flush=True)
        r = subprocess.run([sys.executable, "-m", mod, *args], cwd=REPO_ROOT, env=env,
                           capture_output=True, text=True)
        tail = "\n".join(r.stdout.strip().splitlines()[-4:])
        print(tail)
        if r.returncode != 0:
            print(r.stderr)
            raise SystemExit(f"échec de {mod} (code {r.returncode})")
        print(f"    ({time.time()-t0:.0f} s)", flush=True)
    print(f"Chaîne structure terminée en {time.time()-t00:.0f} s")


def j(name):
    return json.loads((RES / name).read_text())


def write_recommended():
    ss, th, kc, fr, mb = (j("support_study.json"), j("thermal.json"), j("kinematic_coupling.json"),
                          j("frame.json"), j("machining_budget.json"))
    hp = j("homogenization_pitch.json")
    sel = ss["selected"]
    s35 = sel["by_thickness"]["35"]["B"]
    pts = sel["points_mm"]
    hk = kc["hertz"]
    wd = kc["wedge"]
    ref_frame = next(c for c in fr["cases"] if c["kind"] == "reference" and c["bracing"] == "3faces"
                     and c["joint_factor"] < 1)
    eco_frame = next(c for c in fr["cases"] if c["kind"] == "paillasse" and c["bracing"] == "3faces")
    D = {(r["pitch_mm"], r["counterbore_mm"]): r for r in hp if r["h_mm"] == 35 and abs(r["orifice_mm"] - 0.4) < 1e-9}
    psens = {(r["pitch_mm"], r["counterbore_mm"]): r for r in ss["pitch_sensitivity"] if r["h_mm"] == 35}
    bud = mb["budget"]
    tol = mb["tolerancing"]
    drill = {(r["pitch_mm"], r["through_coolant"]): r for r in mb["drilling"]}

    def f(x, n=2):
        return f"{x:.{n}f}"

    lines = f'''# =============================================================================
#  STRUCTURE — VALEURS RECOMMANDÉES (générées par calc/structure/run_all.py)
#  Ne remplace pas params/design.toml : à fusionner par le coordinateur.
#  Notes : docs/03_structure_plaque.md, docs/04_usinage_tolerances.md,
#          docs/05_nivellement.md
# =============================================================================

[meta]
status = "verified"                 # chaîne complète exécutée (run_all)
date = "{time.strftime('%Y-%m-%d')}"
source = "calc/structure/*.py (plate_fe vérifié Navier ; homogénéisation vérifiée cellule 2D/3D)"

[plate]
material = "EN AW-5083 coulée détensionnée (ACP 5080 / Formodal 030 / MIC-6)"
thickness_mm = 35.0                 # 30 mm : pression 4,6 µrad (pas 4,82) mais 6,8 µrad au pas 2,94 ⇒ 35 mm robuste
outer_square_mm = 520.0
counterbore_d_mm = 2.0              # Ø2 convient à tous les pas à e = 35 ; Ø1,5 seulement si e = 30 et pas 2,94
counterbore_depth_mm = 34.0         # = e − voile 1,0
orifice_length_mm = 1.0
study_pitch_mm = 4.82               # pas utilisé pour l'étude principale (lot aéro) ; voir [plate.pitch_sensitivity]
D_ratio_perforated = {f(D[(4.82, 2.0)]["D_ratio"], 3)}         # e = 35, pas 4,82, Ø2 (stratifié prudent)
E_ratio_perforated_layer = {f(D[(4.82, 2.0)]["E_ratio_layer"], 3)}
mass_kg = {f(D[(4.82, 2.0)]["mass_kg"], 1)}                    # plaque percée 520×520×35
alpha_th = 24.2e-6
k_W_mK = 110.0                      # borne basse 110–140 (fiche ACP 5080R)

[plate.pitch_sensitivity]           # e = 35, chemin B, schéma retenu : D*/D ; pente pression crête (µrad) ; nb de trous
'''
    for (p, cb), r in sorted(D.items()):
        ps = psens[(p, cb)]
        lines += (f'p{str(p).replace(".", "_")}_cb{str(cb).replace(".", "_")} = {{ D_ratio = {r["D_ratio"]:.3f}, '
                  f'pressure_slope_urad = {ps["P_B_urad"]:.2f}, n_holes = {r["n_holes"]}, mass_kg = {r["mass_kg"]:.1f} }}\n')
    lines += f'''
[support]
scheme = "3pt-kelvin-frame"         # 3 appuis cinématiques (Maxwell 3 vés) sur le cadre supérieur, hors plenum
pressure_path = "B"                 # caisson de plenum suspendu à la plaque (poussée auto-équilibrée)
points_mm = {json.dumps([[round(x, 1), round(y, 1)] for x, y in pts])}   # repère : centre plaque, +y = arrière
fixed_point = 0                     # appui arrière fixe ; appuis 1 et 2 (côtés) motorisés
reactions_N = {json.dumps([round(v, 1) for v in s35["R_G_N"]])}       # poids propre (plaque + caisson + accessoires)
slope_deadweight_urad = {f(s35["G"]["slope_peak_urad"], 1)}       # sans finition sur appuis (hors budget 10)
slope_deadweight_finished_on_supports_urad = {f(bud["reference"]["rows"][2]["prevu_urad"], 1)}
slope_pressure_urad = {f(s35["P"]["slope_peak_urad"], 2)}          # 0 → 400 Pa (budget 5)
friction_mu = 0.15
slope_friction_worst_urad = {f(s35["friction"]["mu0.15"]["worst_urad"], 2)}
finishing_on_service_supports = true   # finition avec lest du caisson (±5 %) ; caisson absent : {f(s35["finishing"]["box_missing_urad"], 1)} µrad
radius_ratio = 0.0                  # sans objet (positions explicites ci-dessus)

[support.coupling]
ball_d_mm = {f(hk["ball_d_mm"], 1)}                   # bille G10 100Cr6 collée dans un logement H8 de la plaque, centre 2 mm sous la face
roller_d_mm = {f(hk["roller_d_mm"], 0)}                   # 2 rouleaux trempés rectifiés h6 par vé, vé à 90°
vee_axis_angle_deg = {json.dumps([round(v, 1) for v in kc["geometry"]["vee_axis_angle_deg"]])}   # axes des vés vers le barycentre
preload_N = {f(hk["preload_N"], 0)}                     # aucune : poids seul + butées anti-soulèvement (jeu 0,5 mm)
hertz_pmax_GPa = {f(max(c["pmax_GPa"] for c in hk["contacts"]), 2)}
k_support_N_per_um = {f(min(kc["stiffness"]["k_support_chain"]) / 1e6, 0)}

[leveling]
mechanism = "vérin à coin 1:5 sur cage à aiguilles, tête guidée par lames flexibles"
wedge_tan = 0.2
screw = "M6×0,25 (écrou bronze rattrapé par ressort), irréversible"
motor = "NEMA17 200 pas/tr, double arbre (bouton gradué 100 div côté manuel), TMC2209"
resolution_urad_per_full_step = {f(wd["reference_motorise"]["urad_per_step"], 2)}
resolution_urad_per_knob_div = {f(wd["reference_motorise"]["urad_per_div"], 2)}
vertical_range_pm_mm = {f(kc["geometry"]["z_range_pm_mm"], 2)}
wedge_travel_pm_mm = {f(wd["reference_motorise"]["wedge_travel_pm_mm"], 1)}
screw_force_N = {f(wd["reference_motorise"]["F_screw_N"], 0)}
screw_torque_mNm = {f(wd["reference_motorise"]["torque_Nm"] * 1e3, 1)}
lever_pitch_mm = {f(kc["geometry"]["L_pitch_mm"], 0)}
lever_roll_mm = {f(kc["geometry"]["L_roll_mm"], 0)}
coarse = "4 pieds M16×2 sous le bâti (≈ 4 mrad/tour)"

[leveling.economique]
mechanism = "même coin 1:5 entraîné par ajusteur différentiel du commerce (type Thorlabs DAS110)"
resolution_urad_per_rev_fine = {f(wd["eco_differentiel_fin"]["urad_per_rev"], 1)}
resolution_urad_per_div = {f(wd["eco_differentiel_fin"]["urad_per_div"], 2)}
coarse_urad_per_rev = {f(wd["eco_differentiel_grossier"]["urad_per_rev"], 0)}
screw_force_N = {f(wd["eco_differentiel_fin"]["F_screw_N"], 0)}     # charge de l'ajusteur à confirmer sur fiche

[tilt_sensors]
type = "ADXL355 ×4 sur embases isothermes rotatives indexées (retournement 180°)"
positions_mm = [[-220.0, 220.0], [220.0, 220.0], [-220.0, -220.0], [220.0, -220.0]]   # face supérieure, bande pleine
note = "moyenne des 4 = inclinaison du plan (le dôme de pression s'annule par symétrie)"
base_block_mm = [60.0, 60.0, 20.0]
base_feet_height_mm = 12.0
base_feet_spacing_mm = 40.0
slope_base_gradient_urad = {f(th["adxl_base"]["tilt_feet_urad"], 2)}      # pour 50 mK de gradient latéral
offset_residual_typ_urad = {f(th["adxl_base"]["offset_residual_typ_urad"], 1)}

[thermal]
air_minus_plate_max_K = 1.0         # pente transitoire {f(th["step_1K"]["Qmax"]["peak_urad_per_K"], 1)} µrad/K (Qmax)
dT_through_max_mK = {f(th["budget"]["dT_through_max_K"]["35"] * 1e3, 0)}            # gradient haut/bas admissible (e = 35)
settle_time_min = {f(th["step_1K"]["Qmin"]["settle_min"], 0)}             # après changement de débit (Qmin, pire)
fan_air_heating_K_max = {f(th["fan_heating"]["max"]["dT_air_K"], 2)}

[plenum]
inner_square_mm = 430.0             # caisson suspendu (chemin B) ; design.toml : 440
wall_mm = 6.0
bottom_mm = 6.0
box_mass_kg = {f(fr["panels"]["box"]["total_kg"], 1)}
attachment_line_half_mm = 218.0     # axe des parois sur la face inférieure de la plaque

[frame]
profile_system = "Bosch Rexroth rainure 10 (45×90 cadre supérieur et montants, 45×45 ceintures et écharpes)"
profile_main_mm = 45
top_ring_axis_half_mm = 250.0       # cadre 545×545 hors tout, 45×90 posé de chant
ring_axis_height_mm = 745.0         # dessus du cadre 790, dessus de plaque 900 mm
bracing = "écharpes 45×45 sur 3 faces (arrière, gauche, droite)"
f1_Hz = {f(ref_frame["f_Hz"][0], 0)}                     # assemblages semi-rigides ; sans écharpes : {f(fr["cases"][0]["f_Hz"][0], 0)} Hz
mass_profiles_kg = {f(ref_frame["frame_mass_kg"], 1)}
economique = "paillasse : cadre 45×45, montants 300 mm, écharpes 3 faces, posé sur table existante"
economique_f1_Hz = {f(eco_frame["f_Hz"][0], 0)}           # bâti seul ; la table support domine

[machining]
finish_reference = "surfaçage diamant mono-pointe sur appuis de service (lest du caisson), ou rodage + carte"
flatness_perforated_um_required = {f(tol["reference"]["flatness_perforated_um"], 1)}   # pour 30 µrad (85 % forme)
flatness_100_um_required = {f(tol["reference"]["flatness_100_um"], 2)}
cdc_6um_gives_urad = {f(tol["reference"]["cdc_6um_cylinder_urad"], 0)}             # incohérence du CdC à arbitrer
finish_economique = "surfaçage fraise sur CN de précision, sur montage 3 appuis, 15–20 µm"
economique_slope_urad = [{f(tol["economique"][0]["total_urad"], 0)}, {f(tol["economique"][1]["total_urad"], 0)}]   # 15 / 20 µm, avant compensation
drilling_hours_6000 = {f(drill[(4.82, True)]["hours"], 0)}
drilling_hours_17000 = {f(drill[(2.94, True)]["hours"], 0)}

[budget]
reference_rss_urad = {f(bud["reference"]["total_rss_urad"], 1)}
economique_rss_urad = {f(bud["economique"]["total_rss_urad"], 0)}
economique_after_compensation_urad = {f(bud["economique"]["after_compensation_urad"], 0)}
'''
    (RES / "recommended_params.toml").write_text(lines)
    import tomllib
    tomllib.loads(lines)   # contrôle de syntaxe
    print("→ results/recommended_params.toml (syntaxe TOML vérifiée)")


if __name__ == "__main__":
    if "--params-only" not in sys.argv:
        run_steps(full="--full" in sys.argv)
    write_recommended()
