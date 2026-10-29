# Reprise — lot Structure (arrêt quota, 2026-10-29)
Aucun commit git. `params/design.toml` n'a pas été modifié.

## Résultats
**Vérifiés**
- `plate_fe.py` (Kirchhoff, élément BFS) : comparé à Navier (plaque simplement appuyée),
  l'erreur est < 0,01 % dès n = 8. Un appui placé hors nœud converge.
- Homogénéisation (hexagonal, pas 5 mm, Ø2, voile 1 mm). Porosité f = 0,145 ; μ = 0,60.
  - Cellule 2D : E*/E = 0,662 et ν* = 0,332, comme Mori-Tanaka (0,663).
  - Cellule 3D : rigidité supérieure de 1,8 à 2 % au stratifié retenu, qui est donc prudent.
  - D_percé/D_plein = 0,705 / 0,698 / 0,692 / 0,689 pour e = 20 / 25 / 30 / 35 mm.
  - Masse de la plaque : 13,4 / 16,8 / 20,1 / 23,5 kg.

**Provisoires** (maillage 10 mm, positions non optimisées)
Pente crête après retrait du plan, zone 300×300.

| Schéma | e (mm) | chemin | poids propre (µrad) | 0→400 Pa (µrad) |
|---|---|---|---|---|
| 3 pts sur le cadre : (0 ; 242,5), (±242,5 ; −242,5) | 25 | A / B | 35,4 / 48,1 | 20,6 / 8,3 |
| idem | 30 | A / B | 24,7 / 32,1 | 12,0 / 4,8 |
| 4 pts aux coins (1 µm de défaut de hauteur → 0,92 µrad) | 30 | A / B | 23,9 / 30,5 | 11,9 / 4,8 |
| Élastomère au pourtour (10 µm de gauche du cadre → 27 µrad) | 30 | A / B | 9,5 / 10,6 | 5,5 / 4,2 |

Ce qu'on en tire :
- Les appuis au bord sont hors budget (10 µrad en poids propre). Il faut soit rapprocher
  les appuis (Kelvin optimisé dans la bande pleine 190–245 mm, sur colonnettes à travers le
  plenum, ou whiffletree 9 points), soit faire la finition sur les appuis de service.
- Le chemin B divise la sensibilité à la pression par environ 2,5.
- Épaisseur minimale provisoire : 30 mm.

## État des fichiers
- `calc/structure/plate_fe.py` et `homogenization.py` : finis et vérifiés.
- `calc/structure/support_study.py` : écrit, mais trop lent (arrêté après plus de 10 min).
  Les fonctions d'évaluation marchent. Optimisations et figures : jamais exécutées.
- `calc/structure/results/recommended_params.toml` : provisoire.
- Non commencés : `thermal.py`, `materials.py`, `kinematic_coupling.py`, `frame.py`,
  les notes `docs/03`, `04` et `05`, et `docs/research/structure_composants.md`.

## Étapes restantes
1. Accélérer `support_study.py` : maxiter 120, un seul point de départ, whiffletree en
   chemin A seulement, n = 104 seulement pour e = 30 et 35, supprimer le double appel
   `optimize_wt9(band=False)`. Puis l'exécuter et vérifier les figures.
2. Choisir le schéma d'appui. Ajouter le moment de frottement aux appuis (μN·e/2) et la
   variante « finition sur appuis ».
3. `thermal.py` : κ = αΔT/e = αq/k, échauffement de l'air, constantes de temps.
4. `materials.py` : tableau comparatif (α/k, E/ρ, contraintes résiduelles, coût).
5. `kinematic_coupling.py`. Pistes :
   - Maxwell à 3 vés, billes Ø20 sur rouleaux trempés (Hertz ≈ 1,3 GPa, ≈ 4·10⁷ N/m) ;
   - précharge par tige et ressort ;
   - vérins à coin 1:5 + vis M6×0,25 + NEMA17, soit ≈ 0,6 µrad par pas ;
   - course ±3,1 mm.
6. `frame.py` : EF poutres du bâti Rexroth 45×45/45×90 (fréquences > 30 Hz), panneaux sous
   400 Pa, membrane semi-circulaire.
7. Rédiger `docs/03_structure_plaque.md`, `docs/05_nivellement.md` et
   `docs/04_usinage_tolerances.md` (méthode du skill `tolerancement-iso-gps`).
8. Compléter `recommended_params.toml` et relancer tous les scripts.

## Commandes (depuis la racine)
`python3 -m calc.structure.plate_fe` (2 s) ; `python3 -m calc.structure.homogenization` (70 s) ;
`python3 -m calc.structure.support_study` (à accélérer d'abord).
