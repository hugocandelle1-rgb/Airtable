"""Comparaison des matériaux candidats pour la plaque perforée.

Indices de mérite pour notre problème (plaque carrée de côté L, épaisseur e,
3 appuis, chargée par son poids et par la pression) :
  - pente de poids propre      θ_G ∝ (ρ/E) · L³/e²
  - pente de pression          θ_P ∝ p · L³/(E·e³)
  - courbure thermique         κ   = α·q/k   → indice α/k (distorsion thermique)
  - inertie thermique          ρ·c (lisse les variations), diffusivité k/(ρc)
  - stabilité dimensionnelle   contraintes résiduelles (laminé ≫ coulé)
  - usinabilité des 6 000–17 000 orifices Ø0,3–0,4 et finition < 10 µm
Les épaisseurs « équivalentes » sont celles qui donnent la même pente que
l'aluminium coulé de référence (e_ref) en poids propre et en pression.

Valeurs : fiches citées dans docs/research/materiaux_plaque.md pour les plaques
coulées (ACP 5080, Formodal 030, MIC-6) ; valeurs de manuel (ordre de grandeur,
non sourcées au sens de la règle 5) pour les autres. Les prix sont des ordres de
grandeur indicatifs à confirmer par devis.

    python3 -m calc.structure.materials
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

# nom, E (GPa), ρ (kg/m³), α (1e-6/K), k (W/m/K), c (J/kg/K), contraintes résiduelles,
# perçage Ø0,4 × 6 000+, finition ≤ 6 µm sur 500, prix matière indicatif (€/kg), source
MATERIALS = [
    ("EN AW-5083 coulée détensionnée (ACP 5080, Formodal 030)", 70, 2660, 24.2, 110, 900,
     "très faibles (coulée + recuit)", "facile (copeaux longs, foret carbure poli)",
     "surfaçage diamant / rectification : oui", 12, "docs/research/materiaux_plaque.md"),
    ("MIC-6 (coulée stabilisée)", 71, 2690, 23.6, 142, 900,
     "très faibles", "facile", "oui", 15, "docs/research/materiaux_plaque.md (revendeurs)"),
    ("EN AW-6061-T651 laminée", 69, 2700, 23.6, 167, 900,
     "modérées (T651 détendu par traction) : risque de voilage au perçage dissymétrique",
     "facile", "oui mais voilage après perçage", 8, "valeurs de manuel"),
    ("EN AW-7075-T651 laminée", 72, 2810, 23.4, 130, 960,
     "élevées", "facile", "voilage probable", 14, "valeurs de manuel"),
    ("Fonte grise EN-GJL-250 vieillie", 110, 7200, 10.5, 48, 500,
     "faibles après vieillissement", "possible (fonte, poussière de graphite)",
     "rectification / grattage : oui", 6, "valeurs de manuel"),
    ("Acier inox 1.4301", 193, 7900, 17.3, 16, 500,
     "modérées", "difficile (écrouissage, forets Ø0,4 fragiles)", "rectification : oui", 6,
     "valeurs de manuel"),
    ("Granit noir", 50, 2700, 6.0, 2.5, 800,
     "nulles", "très difficile (ultrasons/laser, 6 000 trous : prohibitif)", "rodage : excellent", 4,
     "valeurs de manuel"),
    ("Alumine Al2O3 96 %", 300, 3800, 7.0, 25, 880,
     "nulles", "laser ou cru avant frittage (retrait) : coûteux", "rodage : excellent", 60,
     "valeurs de manuel"),
    ("Invar 36", 141, 8100, 1.3, 10, 515,
     "à stabiliser", "difficile", "oui", 40, "valeurs de manuel"),
]


def run(P=None, verbose=True, e_ref_mm=35.0):
    P = P or load_params()
    L = P["plate"]["outer_square_mm"] * 1e-3
    ref = MATERIALS[0]
    E0, r0, a0, k0 = ref[1] * 1e9, ref[2], ref[3] * 1e-6, ref[4]
    rows = []
    for (name, E, rho, a, k, c, rs, drill, fin, price, src) in MATERIALS:
        E_, a_ = E * 1e9, a * 1e-6
        # même pente de poids propre : (ρ/E)/e² constant → e = e_ref·√((ρ/E)/(ρ0/E0))
        e_G = e_ref_mm * np.sqrt((rho / E_) / (r0 / E0))
        # même pente de pression : 1/(E e³) constant
        e_P = e_ref_mm * (E0 / E_) ** (1 / 3)
        mass_ref = rho * L**2 * e_ref_mm * 1e-3
        rows.append(dict(material=name, E_GPa=E, rho=rho, alpha_e6=a, k=k, c=c,
                         rho_over_E_rel=(rho / E_) / (r0 / E0),
                         alpha_over_k_rel=(a_ / k) / (a0 / k0),
                         diffusivity_mm2_s=k / (rho * c) * 1e6,
                         e_same_G_mm=e_G, e_same_P_mm=e_P,
                         mass_at_e_ref_kg=mass_ref, mass_at_e_G_kg=rho * L**2 * e_G * 1e-3,
                         residual_stress=rs, drilling=drill, finishing=fin,
                         price_eur_kg=price, cost_blank_eur=price * mass_ref * 1.3, source=src))
    out = dict(e_ref_mm=e_ref_mm, L_mm=L * 1e3, rows=rows)
    RES.mkdir(parents=True, exist_ok=True)
    (RES / "materials.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    lines = ["| Matériau | E (GPa) | ρ | α (µm/m/K) | k (W/m/K) | (ρ/E) rel. | (α/k) rel. | e même θ_G (mm) | e même θ_P (mm) | masse à e_ref (kg) | contraintes résiduelles | perçage | brut indicatif (€) |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['material']} | {r['E_GPa']} | {r['rho']} | {r['alpha_e6']} | {r['k']} | "
                     f"{r['rho_over_E_rel']:.2f} | {r['alpha_over_k_rel']:.2f} | {r['e_same_G_mm']:.0f} | "
                     f"{r['e_same_P_mm']:.0f} | {r['mass_at_e_ref_kg']:.1f} | {r['residual_stress']} | {r['drilling']} | "
                     f"{r['cost_blank_eur']:.0f} |")
    (RES / "materials_table.md").write_text("\n".join(lines) + "\n")
    if verbose:
        print(f"Référence : {ref[0]}, e = {e_ref_mm} mm, plaque {L*1e3:.0f} mm")
        for r in rows:
            print(f"  {r['material'][:45]:45s} ρ/E {r['rho_over_E_rel']:.2f}  α/k {r['alpha_over_k_rel']:.2f}  "
                  f"e(θ_G) {r['e_same_G_mm']:.0f} mm  e(θ_P) {r['e_same_P_mm']:.0f} mm  masse {r['mass_at_e_ref_kg']:.1f} kg")
        print("→ results/materials.json, results/materials_table.md")
    return out


if __name__ == "__main__":
    run()
