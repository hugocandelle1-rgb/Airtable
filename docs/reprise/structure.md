# Reprise — lot structure (état au 2026-11-03)

Aucun commit git n'a été fait par ce lot, et `params/design.toml` n'a pas été modifié.
**Les étapes 1 à 8 de la reprise précédente sont terminées.**

## Commandes

| Commande | Effet |
|---|---|
| `OPENBLAS_NUM_THREADS=1 python3 -m calc.structure.run_all` | chaîne complète, ≈ 2,3 min. Ordre : plate_fe → homogenization --quick → support_study (≈ 2,1 min) → thermal → materials → frame → kinematic_coupling → machining. Écrit ensuite `results/recommended_params.toml` (syntaxe vérifiée) |
| `python3 -m calc.structure.run_all --full` | ajoute les cellules 3D d'homogénéisation (+70 s) |
| `python3 -m calc.structure.run_all --params-only` | réécrit seulement le TOML |

Les scripts lisent `calc/aero/results/network.json` (débits, pour la thermique). Il faut
relancer après chaque mise à jour du lot aéro.

## Résultats principaux

Notes : `docs/03_structure_plaque.md`, `docs/04_usinage_tolerances.md`,
`docs/05_nivellement.md`. Chacune a une section « Données pour la CAO ».

- **Plaque.** EN AW-5083 coulée, **35 mm** d'épaisseur, lamage Ø2, voile 1 mm, 23,3 kg au
  pas 4,82.
  - L'homogénéisation est paramétrée sur le pas (`pitch_study`). D*/D vaut :
    - 0,354 au pas 2,94/Ø2 (0,552 avec un lamage Ø1,5) ;
    - 0,599 au pas 4,23 ;
    - 0,670 au pas 4,82 ;
    - 0,689 au pas 5,0.
  - L'écart entre 4,82 et 5,0 est négligeable.
- **Appuis.** 3 appuis Maxwell sur le cadre, hors plenum : P0 (0 ; 242,5) fixe, P1 et P2
  (±242,5 ; −145,5) motorisés.
  - **Chemin B** (caisson suspendu à la plaque).
  - Pentes à 35 mm :
    - poids propre 15,7 µrad bruts, puis **1,7 µrad** avec finition sur appuis de
      service, caisson monté ;
    - pression **2,8 µrad** (4,3 au pas 2,94/Ø2) ;
    - frottement 1,7 µrad (µ = 0,15).
- **Thermique.** κ = αq/k.
  - Exigence ΔT haut/bas ≤ 34 mK (le CdC dit 50).
  - Pic transitoire de 1,4 µrad par K d'écart air/plaque, stabilisation en 45 min.
- **Nivellement.** Coin 1:5, vis M6×0,25 et NEMA17 double arbre.
  - **0,64 µrad/pas** ; 1,29 µrad par graduation à la main.
  - Course ±2,43 mm ; vis 22 N.
  - Variante économique (DAS110 + coin) : 0,26 µrad/div.
- **ADXL355 ×4** en (±220 ; ±220).
  - La moyenne des 4 annule le dôme de pression.
  - Embase isotherme rotative à 2 jeux de 3 vés (retournement 180°).
  - Erreurs : 0,35 µrad pour 50 mK de gradient, offset résiduel 1 µrad typique.
- **Bâti.** Rexroth : cadre 45×90, montants 45×90, ceintures et écharpes 45×45 sur
  3 faces.
  - 1er mode 49 Hz (26 Hz sans écharpes).
  - Variante paillasse : 86 Hz (bâti seul).
- **Usinage.** Perçage :
  - 21 h machine pour 6 333 trous ;
  - **50 h** pour 17 131 trous (pas 2,94).
- **Budget de référence :** 30,7 µrad, mais **seulement si ⏥ 2,8 µm** est atteint.
- **Variante économique** (surfaçage 15–20 µm) : 205–251 µrad, ramenés à ≈ 12 µrad après
  cartographie et compensation.

## Points ouverts (à arbitrer par le coordinateur)

1. **Le CdC est incohérent.** 6 µm de planéité donnent 56 µrad pour une allocation de
   30. Il faut soit ⏥ 2,8 µm (fly-cut diamant ultra-précis, prestataire non trouvé),
   soit une carte de pente compensée, y compris pour la référence.
2. **Fusion dans `params/design.toml`.** Clés touchées :
   - `plate.thickness_mm` : 35 ;
   - `support.scheme` ;
   - `plenum.inner_square_mm` : 430 (caisson suspendu) ;
   - `frame.profile_system` ;
   - `performance_targets.thermal_gradient_K` : 0,034.
3. **CAO.** Le support passe des colonnettes à 3 appuis sur le cadre. Le plenum devient
   un caisson suspendu à la plaque. Le cadre passe en 45×90 de chant, z = 790.
4. **À confirmer sur fiche** (`docs/research/structure_composants.md`) :
   - constante de torsion des profilés Rexroth ;
   - charge admissible du DAS110 ;
   - existence d'une vis M6×0,25 ;
   - cages à aiguilles.
5. **Pas 2,94 avec lamage Ø2.** Le ligament de 0,94 mm sur 34 mm de profondeur est à
   valider sur éprouvette (dérive des forets).
