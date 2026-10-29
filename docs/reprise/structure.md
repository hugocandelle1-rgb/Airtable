# Reprise — lot Structure / plaque / nivellement (arrêt intermédiaire, quota)

Date : 2026-10-29. Aucun commit. `params/design.toml` n'a pas été modifié.

## (a) Rapport intermédiaire : résultats chiffrés

### Vérifiés
- **Modèle EF de plaque** (`plate_fe.py`, Kirchhoff, élément BFS 16 ddl) : validé sur la
  plaque carrée simplement appuyée (Navier). Coefficient de flèche 0,004062 ; erreur
  < 0,01 % dès n = 8 sur la flèche et la pente de bord. Un appui ponctuel placé hors
  nœud converge (5,2129 / 5,2133 / 5,2134 µm pour n = 21/40/63).
- **Homogénéisation** (`homogenization.py`), réseau hexagonal pas 5, Ø2, voile 1 mm :
  - porosité de la couche percée f = 0,145 ; efficacité de ligament μ = 0,60 ;
  - cellule 2D périodique (contraintes planes) : **E*/E = 0,662, ν* = 0,332**, isotrope
    (convergé à nx = 40/80/160). Identique à Mori-Tanaka/HS (0,663). La règle « E*/E = μ »
    donne 0,60 (prudente) ;
  - cellule 3D périodique (ABD complet) : rigidité réelle supérieure de **+1,8 à +2 %** au
    stratifié (couche percée + voile). Le stratifié est donc **retenu, il est
    conservatif** ;
  - **D_percé / D_plein = 0,705 / 0,698 / 0,692 / 0,689** pour e = 20/25/30/35 mm ;
  - masse surfacique : 57,2 kg/m² percée contre 66,5 pleine (e = 25) ; masse de la plaque
    13,4 / 16,8 / 20,1 / 23,5 kg (e = 20/25/30/35).

### Provisoires (sondage rapide, maillage de 10 mm, pas d'optimisation)
Il s'agit de la pente locale crête/RMS après retrait du plan des moindres carrés, sur le
carré de travail 300×300. Budgets : 10 µrad pour le poids propre, 5 µrad pour la pression.

| Schéma | e | chemin | G crête / RMS (µrad) | ΔP 0→400 Pa crête / RMS (µrad) |
|---|---|---|---|---|
| 3 pts sur l'axe du cadre (0, 242,5), (±242,5, −242,5) | 25 | A | 35,4 / 19,0 | 20,6 / 10,9 |
| idem | 25 | B | 48,1 / 26,1 | 8,3 / 5,6 |
| idem | 30 | A | 24,7 / 13,2 | 12,0 / 6,4 |
| idem | 30 | B | 32,1 / 17,3 | **4,8** / 3,3 |
| 4 pts aux coins du cadre (rigides) | 30 | A / B | 23,9 / 30,5 | 11,9 / 4,8 |
| bande élastomère périmétrique (k = 2·10⁹ N/m³) | 30 | A | **9,5** | 5,5 |
| idem | 30 | B | 10,6 | 4,2 |

Ce qu'on en tire (provisoire) :
1. Les **appuis au bord** (sur le cadre 45×90, s = 242,5 mm) sont **hors budget en poids
   propre** (25 à 48 µrad), quel que soit le chemin. Il faut rapprocher les appuis :
   optimisation de Kelvin dans la bande pleine 190–245 mm (colonnettes à travers le plenum)
   ou whiffletree 9 points. Autre parade : **usiner la finition de la face supérieure sur
   les mêmes 3 appuis**, ce qui « usine » la flèche de poids propre (à évaluer).
2. Le chemin **B** (caisson suspendu à la plaque) divise la sensibilité à la pression
   par ≈ 2,5. En contrepartie, la masse du caisson (8 kg) aggrave la flèche de poids propre.
3. Sur 4 appuis, un défaut de hauteur de 1 µm sur un appui donne 0,92 µrad. La planéité
   du cadre (≈ 10–50 µm) rend ce schéma inacceptable sans calage.
4. L'appui **périmétrique élastomère** passe presque le budget en poids propre et en
   pression à e = 30. En revanche, un gauchissement du cadre de 10 µm donne **27–30 µrad** :
   ce schéma est rejeté, sauf avec un cadre rodé.
5. L'épaisseur de **25 mm ne suffit pas**. 30 mm est le minimum vraisemblable, 35 mm reste
   à évaluer.

## (b) État des fichiers

| Fichier | État |
|---|---|
| `calc/structure/__init__.py` | fini |
| `calc/structure/plate_fe.py` | **fini, vérifié** (s'exécute en 2 s ; produit `results/plate_fe_validation.json`) |
| `calc/structure/homogenization.py` | **fini, vérifié** (≈ 70 s ; produit `results/homogenization.json`, `homogenization_cache.json`, `figures/homogenization_E_nu.png`) |
| `calc/structure/support_study.py` | **écrit mais pas encore exécuté jusqu'au bout** : trop lent (> 10 min, interrompu). Les fonctions `build_plate`, `loads`, `IsoSupport`, `eval_iso`, `eval_4pt`, `eval_perimeter` fonctionnent (sondage ci-dessus). Les phases d'optimisation et les figures ne sont pas testées |
| `calc/structure/results/recommended_params.toml` | provisoire (minimal) |
| `thermal.py`, `materials.py`, `kinematic_coupling.py`, `frame.py` | non commencés |
| `docs/03_structure_plaque.md`, `docs/04_usinage_tolerances.md`, `docs/05_nivellement.md` | non commencés |
| `docs/research/structure_composants.md` (sources des composants du commerce, règle 5 du projet) | non commencé |

## (c) Étapes restantes (dans l'ordre)

1. **Accélérer `support_study.py`** (objectif < 5 min) :
   - faire toutes les optimisations sur n = 52 (déjà le cas) et réduire `maxiter` à 120 ;
   - lancer un seul point de départ par optimisation ;
   - optimiser le whiffletree pour un seul chemin (A) ;
   - la matrice complète en n = 104 coûte environ 4 s de factorisation par cas : n'y garder que
     e = 30 et e = 35, et passer e = 20 et e = 25 en n = 52 ;
   - supprimer l'appel `optimize_wt9(... band=False)` en double (`build_plate` y est
     appelé deux fois).

   Ensuite, exécuter le script et vérifier les figures `support_*.png`.
2. Trancher le schéma. Les candidats sont Kelvin optimisé dans la bande pleine (sur
   colonnettes dans le plenum, chemin A) et le whiffletree. Évaluer aussi la variante
   « finition usinée sur appuis de service ». Ajouter la sensibilité au frottement aux appuis
   (moment μN·e/2) et la charge des palets (déjà codée, cas `puck_1N`).
3. `thermal.py` (point 5) :
   - courbure κ = α·ΔT/e, avec une pente à r = 212 mm d'environ 2 µrad par 0,01 K pour e = 25 ;
   - noter que κ = α·q/k ne dépend pas de e ;
   - échauffement de l'air par le ventilateur ;
   - τ à travers l'épaisseur d'environ 1–2 s, τ global d'environ 10 min ;
   - frottement aux V lors de la dilatation (calcul EF avec `load_point_moment`).
4. `materials.py` (point 4) : tableau E, ρ, α, k, α/k, E/ρ, coût, contraintes résiduelles.
   Matériaux : 5083 coulé, 6061/7075 laminés, granite, verre, acier, céramique poreuse.
5. `kinematic_coupling.py` (point 6) :
   - Maxwell à 3 vés radiaux (bille 100Cr6 ou Si3N4 Ø20 sur 2 rouleaux trempés) ;
   - Hertz : environ 1,3 GPa et 4·10⁷ N/m pour 92 N par contact ;
   - précharge par tige à travers la gorge et ressort sous le bloc ;
   - non-décollement sous la poussée en chemin A (≈ 80 N contre un poids de 200 N) ;
   - 1 pivot fixe + 2 vérins à coin 1:5 sur glissières à rouleaux croisés, vis M6×0,25 et
     NEMA17 avec bouton arrière, soit ≈ 0,25 µm, ≈ 0,6 µrad par pas entier ;
   - course combinée ±3,1 mm pour ±0,25° sur les deux axes ;
   - couple ≈ 0,01 N·m ; découplage des axes par somme et différence.
6. `frame.py` (point 7) :
   - EF poutres 3D du bâti en Rexroth 45×45/45×90, avec raideur des liaisons et
     contreventement ; fréquences > 30 Hz ;
   - flèche du cadre sous les appuis et variation avec p (chemin A) ;
   - flèche des panneaux sous 400 Pa (Al 6 mm, Dibond, PMMA) ;
   - membrane semi-circulaire (longueur = π/2 × entrefer, force verticale ≈ 0).

   Hauteur de plan proposée : 900 mm. Le cadre supérieur 45×90, d'ouverture 440, sert de
   paroi de plenum : le fond se loge dans la rainure basse, le déflecteur dans la rainure
   haute.
7. `docs/03_structure_plaque.md` (points 1 à 5 et 7, avec « Données pour la CAO ») et
   `docs/05_nivellement.md`.
8. `docs/04_usinage_tolerances.md` (point 8). Suivre la méthode du skill
   `tolerancement-iso-gps`. Proposition : surfaçage diamant final après micro-perçage,
   sur les appuis de service ; pas d'anodisation ; contrôle Union Jack au niveau
   électronique.
9. Compléter `calc/structure/results/recommended_params.toml` (sections `[support]`,
   `[leveling]`, `[frame]`, `[plenum_box]`, `[seal]`), puis vérifier que tous les scripts
   tournent.

## (d) Commandes (depuis la racine du dépôt)

```bash
python3 -m calc.structure.plate_fe          # validation Navier (~2 s)
python3 -m calc.structure.homogenization    # cellules 2D/3D (~70 s)
python3 -m calc.structure.support_study     # comparaison des appuis (à accélérer d'abord)
```

## (e) Valeurs recommandées provisoires

- Plaque : 5083 coulée détensionnée. Épaisseur **30 mm (provisoire)** ; 25 mm est
  insuffisant.
- Rigidité de la zone percée : D_percé = 0,70·D_plein (vérifié).
- Appuis : **pas au bord**. Le schéma est à fixer après l'optimisation.
- Chemin de la pression : B meilleur pour la pression (4,8 µrad à e = 30, sur appuis au
  bord) mais pénalisant en poids propre. Décision en attente.
- Voir `calc/structure/results/recommended_params.toml` (statut « provisional »).
