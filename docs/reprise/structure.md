# Reprise — lot structure (état au 2026-11-04)

Aucun commit git n'a été fait par ce lot, et `params/design.toml` n'a pas été modifié.
**Les étapes 1 à 8 de la reprise précédente sont terminées.**

## Commandes

| Commande | Effet |
|---|---|
| `OPENBLAS_NUM_THREADS=1 python3 -m calc.structure.run_all` | chaîne complète, ≈ 2,3 min. Ordre : plate_fe → homogenization --quick → support_study (≈ 2,1 min) → thermal → materials → frame → kinematic_coupling → machining → passive_budget. Écrit ensuite `results/recommended_params.toml` (syntaxe vérifiée) |
| `python3 -m calc.structure.run_all --full` | ajoute les cellules 3D d'homogénéisation (+70 s) |
| `python3 -m calc.structure.run_all --params-only` | réécrit seulement le TOML |

Les scripts lisent `calc/aero/results/network.json` (débits, pour la thermique). Il faut
relancer après chaque mise à jour du lot aéro.

## Résultats principaux

Notes : `docs/03_structure_plaque.md`, `docs/04_usinage_tolerances.md`,
`docs/05_nivellement.md`. Chacune a une section « Données pour la CAO ».

- **Plaque.** EN AW-5083 coulée, **35 mm** d'épaisseur, 23,5 kg. Perçage de la
  configuration aéro retenue : **hex 5,00 (5 935 trous), orifice Ø0,30 ±0,005, voile
  1,20, lamage Ø2** (sommet du cône à z = 33,8).
  - L'homogénéisation est paramétrée sur le pas (`pitch_study`). D*/D vaut :
    - 0,364 au pas 2,94/Ø2 (0,560 avec un lamage Ø1,5) ;
    - 0,606 au pas 4,23 ;
    - 0,676 au pas 4,82 ;
    - **0,694 au pas 5,0 (retenu)**.
  - L'écart entre 4,82 et 5,0 est négligeable.
- **Appuis.** 3 appuis Maxwell sur le cadre, hors plenum : P0 (0 ; 242,5) fixe, P1 et P2
  (±242,5 ; −145,5) motorisés.
  - **Chemin B** (caisson suspendu à la plaque).
  - Pentes à 35 mm :
    - poids propre 15,5 µrad bruts, puis **1,7 µrad** avec finition sur appuis de
      service, caisson monté ;
    - pression **2,7 µrad** à 400 Pa (≤ 2,6 à 375 Pa ; 4,3 au pas 2,94/Ø2) ;
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
  - **20 h** machine pour 5 935 trous (pas 5,00, retenu) ;
  - 51 h pour 17 131 trous (pas 2,94).
- **Budget de référence :** 30,6 µrad, mais **seulement si ⏥ 2,8 µm** est atteint.
- **Variante économique** : non applicable (supposait une compensation).

## Révision du 2026-11-04 : budget de force parasite

**Décisions de l'utilisateur :**

- aucune compensation logicielle ;
- les palets portent des actionneurs électrostatiques radiaux, et la table sert à
  **caractériser** leur mouvement. Toute force parasite dans le plan est une erreur de
  mesure.

L'hypothèse retenue pour l'instant est l'absence d'interaction électrostatique entre
palet et plaque. L'exigence « plaque = référence de potentiel » a été retirée, et le lot
électrostatique est reporté.

**`calc/structure/passive_budget.py`** (dans `run_all`). Paramètre : θ = a_par/g, aux
niveaux 5 / 10 / 20 / 30 / 50 µrad.

- Critère : somme quadratique de tous les postes ≤ θ. Les postes sont la structure, le
  crantage, la dispersion des orifices, le balourd (0,9 µrad/µm) et les courants d'air.
- Sorties :
  - répartition et exigences par niveau ;
  - erreur ½aT² pour T = 1 / 5 / 10 / 30 s, et sa valeur amortie (τ Couette) ;
  - rapport F_par/F_act pour m = 2 / 5 / 10 g et F_act = 0,1 µN … 1 mN.
- Fichiers produits : `passive_budget.json`, `passive_budget_table.md`,
  `figures/passive_budget.png` ; section `[parasitic_budget]` du TOML.

**Résultats :**

- planchers techniques : **10,1 µrad** ⇒ θ = 5 et 10 sont non réalisables. Sans
  correction a posteriori du crantage, le minimum est de 33,7 µrad ;
- conception actuelle : **47 µrad** (planéité 2,8 µm, crantage brut 33, orifices ±5 µm,
  balourd 10 µm) ⇒ θ = 50 est tenu, coût relatif ≈ 1,3 ;
- θ = 30 : ⏥ 1,6 µm (tournage diamant ultra-précis), correction du crantage, coût ≈ 3 ;
- θ = 20 : ⏥ 1,1 µm (finition optique de pointe), coût ≈ 9, à la limite ;
- exploitation : recalage d'inclinaison automatique toutes les heures, local ±0,5 K
  entre recalages, rampe ≤ 2,2 K/h, écart air/plaque ≤ 0,7 K ;
- F_par = 0,98 µN (2 g) à 4,9 µN (10 g) à θ = 50. Pour 1 % d'erreur, il faut
  F_act ≥ 100–500 µN.

**Documents mis à jour :**

- `docs/00_cahier_des_charges.md` § 3 réécrit (ancienne version en note) ; exigence 11
  « équilibrage des palets » ajoutée ;
- docs 03, 04 et 05 : variante économique **non applicable** ; `04` § 6 donne les
  exigences de planéité par niveau.

**Points ouverts :**

1. Le niveau θ à viser dépend de la plus petite F_act à caractériser. **C'est une donnée
   à obtenir de l'utilisateur.**
2. Correction a posteriori du crantage (carte étalonnée, soustraite de la mesure) :
   à décider par l'utilisateur pour tout niveau < 34 µrad.
3. Hypothèses d'exploitation à confirmer sur site : sol 1 µrad/h, gradient du bâti égal
   à 10 % de la variation du local.
4. Le crantage brut (33 µrad RMS) reste le poste dominant (lot aéro).

## Points ouverts antérieurs (à arbitrer par le coordinateur)

1. **Planéité ⏥ 2,8 µm ferme** (pas de compensation). Le prestataire n'est toujours pas
   trouvé ; θ = 30 demanderait 1,6 µm.
2. **Fusion dans `params/design.toml`.** Clés touchées :
   - `plate.thickness_mm` : 35 ; `plate.orifice_length_mm` : 1,20 et `plate.orifice_d_mm` : 0,30 (lot aéro) ;
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
