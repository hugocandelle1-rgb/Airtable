# 03 — Structure : plaque perforée, appuis, thermique, matériaux, bâti

> Lot structure / mécanique de précision.
>
> Scripts dans `calc/structure/`, à lancer depuis la racine : `OPENBLAS_NUM_THREADS=1
> python3 -m calc.structure.run_all` (≈ 2,5 min). La chaîne enchaîne `plate_fe`,
> `homogenization`, `support_study`, `thermal`, `materials`, `frame`,
> `kinematic_coupling` et `machining`.
>
> Résultats dans `calc/structure/results/` (`*.json`, `support_table.md`,
> `materials_table.md`, `recommended_params.toml`). Figures dans
> `calc/structure/figures/`.
>
> **Rien n'est fusionné dans `params/design.toml`** : les valeurs proposées sont dans
> `recommended_params.toml`.
>
> Notes associées : `04_usinage_tolerances.md` (finition, tolérances, temps de perçage)
> et `05_nivellement.md` (couplage cinématique, vérins, ADXL355).

## 0. Synthèse

| Décision | Valeur | Justification |
|---|---|---|
| Matériau | EN AW-5083 coulée détensionnée (ACP 5080, Formodal 030, MIC-6) | contraintes résiduelles très faibles, α/k favorable, perçage facile (§ 5) |
| Épaisseur | **35 mm** (23,3 kg percée au pas 4,82) | pente de pression ≤ 4,3 µrad pour **tous** les pas étudiés, y compris 2,94/Ø2 ; à 30 mm, le pas 2,94 donne 6,8 µrad, hors budget |
| Lamage | Ø2 (Ø1,5 seulement si l'on revient à 30 mm avec le pas 2,94) | § 1 |
| Chemin de la pression | **B : caisson de plenum suspendu à la plaque**, sans membrane | la poussée p·A est reprise par les parois du caisson et ne passe pas par les appuis : 2,8 µrad au lieu de 5,2 (chemin A) |
| Schéma d'appui | **3 appuis cinématiques sur le cadre supérieur, hors plenum** : (0 ; +242,5), (±242,5 ; −145,5) | isostatique (insensible au gauchissement du bâti), réalisable sans traverser le caisson |
| Poids propre | 15,7 µrad bruts (budget 10) ⇒ **finition de la face supérieure sur appuis de service**, caisson monté ⇒ résidu **1,7 µrad** (dont 1,7 µrad de frottement) | § 3 |
| Inclinomètres | 4 × ADXL355 en (±220 ; ±220), face supérieure, bande pleine | la moyenne des 4 annule le dôme de pression et le bombé thermique (§ 6) |
| Bâti | Bosch Rexroth rainure 10 : cadre 45×90, montants 45×90, ceintures et écharpes 45×45 sur 3 faces ; 1er mode **49 Hz** | > 30 Hz ; 26 Hz sans écharpes (§ 7) |
| Variante économique | même plaque et mêmes appuis ; surfaçage 15–20 µm sur montage 3 appuis ; bâti « paillasse » | 205–251 µrad avant compensation, ≈ 11 µrad après (`04` § 6) |

**Budget de pente (référence)**, somme quadratique **30,7 µrad** :

| Poste | Valeur |
|---|---|
| Inclinaison | 1,4 µrad |
| Usinage (allocation) | 30 µrad |
| Poids propre résiduel | 1,7 µrad |
| Pression | 2,8 µrad |
| Thermique | 1,4 µrad |
| Sol | 5 µrad |

Ce total ne tient **que si la face supérieure atteint ⏥ 2,8 µm**. Avec les 6 µm du CdC, le
poste usinage vaut à lui seul 56 µrad (`04` § 1).

## 1. Homogénéisation de la zone percée, en fonction du pas

`homogenization.py`, cellule périodique 2D vérifiée (Mori-Tanaka, cellule 3D : le
stratifié retenu est 2 % plus souple que la cellule 3D, donc prudent). Le calcul est
paramétré sur le pas (`pitch_study`, `homogenization_pitch.json`). Le tableau donne les
valeurs pour e = 35 mm, orifice Ø0,4 et voile de 1 mm. La pente de pression est calculée
pour le schéma retenu, chemin B.

| Pas hex (mm) | Lamage | Trous (zone 360) | Ligament | Porosité | E*/E couche | D*/D plein | Masse (kg) | Pente 0→400 Pa (µrad) | Poids propre brut (µrad) |
|---|---|---|---|---|---|---|---|---|---|
| 2,94 | Ø2,0 | 17 131 | 0,94 | 0,420 | 0,292 | **0,354** | 20,2 | **4,34** | 17,4 |
| 2,94 | Ø1,5 | 17 131 | 1,44 | 0,236 | 0,515 | 0,552 | 22,4 | 3,32 | 16,3 |
| 4,23 | Ø2,0 | 8 197 | 2,23 | 0,203 | 0,565 | 0,599 | 22,8 | 3,14 | 16,1 |
| 4,23 | Ø1,5 | 8 197 | 2,73 | 0,114 | 0,722 | 0,742 | 23,8 | 2,70 | 15,3 |
| **4,82** | **Ø2,0** | **6 333** | 2,82 | 0,156 | 0,642 | **0,670** | **23,3** | **2,91** | 15,7 |
| 4,82 | Ø1,5 | 6 333 | 3,32 | 0,088 | 0,776 | 0,793 | 24,1 | 2,58 | 15,0 |
| 5,00 | Ø2,0 | 5 935 | 3,00 | 0,145 | 0,662 | 0,689 | 23,5 | 2,85 | 15,6 |
| 5,00 | Ø1,5 | 5 935 | 3,50 | 0,082 | 0,790 | 0,806 | 24,2 | 2,55 | 14,9 |

Lecture du tableau :

- **4,82 et 5,0 mm sont quasi équivalents.** La rigidité ne diffère que de 2,6 % (0,670
  contre 0,689) et la pente de pression de 0,06 µrad.
- **Au pas 2,94 avec un lamage Ø2,** la porosité monte à 42 % et la rigidité de flexion
  de la zone percée tombe à 35 % de celle de la plaque pleine. La plaque reste dans le
  budget à 35 mm (4,3 µrad sur 5), mais pas à 30 mm (6,8 µrad). Le lamage Ø1,5 remonte
  D*/D à 0,55, mais impose un perçage à 23×D, à valider sur éprouvette. **Recommandation :**
  e = 35 et Ø2 pour tous les pas ; Ø1,5 seulement si l'épaisseur devait redescendre à
  30 mm.
- Le pas 2,94 triple le temps de perçage : 50 h au lieu de 21 h (`04` § 4).

## 2. Comparaison des schémas d'appui (`support_study.py`)

**Modèle.** Plaque de Kirchhoff (éléments BFS, maillage 5 mm), zone percée homogénéisée
et bordure pleine. Le chargement comprend :

- le poids propre ;
- 2 kg d'accessoires sur la bande pleine ;
- au chemin B, 10 kg de caisson sur la ligne d'attache.

La pente est la pente locale crête après retrait du plan des moindres carrés, sur la zone
300 × 300. Budgets : 10 µrad pour le poids propre, 5 µrad pour la pression.

Positions optimisées :

- 3 points dans la bande pleine (Nelder-Mead, 120 itérations) : (0 ; 190), (±190 ; −115).
  Ces points tombent à l'intérieur du plenum.
- 3 points sur le cadre (balayage le long de l'axe du cadre) : arrière (0 ; 242,5),
  côtés (±242,5 ; −145,5).

**e = 35 mm**, pas 4,82 / Ø2 (extrait de `support_table.md`) :

| Schéma | Chemin | Poids propre crête (µrad) | 0→400 Pa crête (µrad) | Réalisable |
|---|---|---|---|---|
| 3 pts cadre : milieu arrière + 2 coins avant | A / B | 19,5 / 25,7 | 7,5 / 2,8 | oui |
| **3 pts cadre, position optimisée** | A / **B** | 12,4 / **15,7** | 5,2 / **2,8** | **oui** |
| 3 pts optimisés dans la bande pleine (r ≈ 190–220) | A / B | 4,6 / 8,4 | 2,4 / 2,8 | A : colonnettes à travers le plenum ; B : non |
| Whiffletree 9 pts (bande pleine) | A / B | 2,4 / 3,1 | 1,8 / 2,8 | colonnettes ; B : non |
| Whiffletree 9 pts sous la zone percée (théorique) | A | 1,6 | 0,8 | non (trous supprimés dans la zone de travail) |
| 4 pts rigides aux coins du cadre | A / B | 18,9 / 24,5 | 7,5 / 2,8 | hyperstatique : 1 µm de défaut de hauteur ≈ 1 µrad |
| Bande élastomère périphérique (joint = appui) | A / B | 7,4 / 8,7 | 3,6 / 2,6 | hyperstatique : 10 µm de gauche du cadre ≈ 20–27 µrad |

À e = 30 mm (même schéma retenu) : poids propre 22,0 µrad (B), pression 4,4 µrad (B) et
8,3 µrad (A).

Lecture du tableau :

1. **Le chemin B est le seul qui tienne la pression** avec des appuis au cadre. Au
   chemin A, la poussée (≈ 70 N à 400 Pa) passe par 3 points et cintre la plaque.
2. **Aucun schéma réalisable hors du plenum ne tient 10 µrad en poids propre** sur une
   plaque de 520 mm. Les solutions sous 10 µrad demandent des colonnettes à travers le
   plenum (étanchéité, transmission des vibrations du caisson) ou des appuis dans la
   zone percée.
3. Les schémas hyperstatiques (4 points, périphérie) sont sensibles au gauchissement du
   bâti, ce qui est inacceptable pour une table réglée au µrad.

### Choix argumenté

On retient **3 appuis cinématiques sur le cadre (position optimisée), le chemin B et une
finition sur appuis de service**. Les raisons :

- **Isostatisme.** Le bâti en profilés peut se gauchir (serrage des pieds, sol, dilatation)
  sans déformer la plaque. Seule l'inclinaison d'ensemble change, et le nivellement la
  rattrape.
- **Le poids propre est statique et répétable.** Il est usiné « en négatif » si la face
  supérieure est finie avec la plaque posée sur des vés identiques, caisson monté.
  Analyse de sensibilité (`selected` dans `support_study.json`, e = 35) :
  - erreur de position des appuis de finition de ±0,5 mm : **0,20 µrad** (somme
    quadratique des 6 cas) ;
  - caisson absent sans lest : 3,3 µrad (lest à ±5 % : 0,16 µrad) ;
  - frottement aux appuis : ci-dessous (1,7 µrad).
- **Pression.** 2,8 µrad au pas 4,82 et 4,3 µrad au pire pas (2,94/Ø2), pour un budget
  de 5 µrad.
- **Réalisation.** Les vés reposent sur le cadre 45×90, hors du caisson, et restent
  accessibles. La répartition des charges est équilibrée : 130 / 108 / 108 N.

### Moment de frottement aux appuis

Une dilatation différentielle plaque/bâti, ou la rotation des appuis sous charge, fait
glisser les billes dans les vés. La force de frottement μN agit au contact, à
(e/2 + 11 mm) sous le plan moyen. Elle crée un moment μN·(e/2 + 11 mm) qui n'est pas
répétable (hystérésis).

| e (mm) | µ | Dilatation radiale (µrad) | Pire cas, 8 directions par appui (µrad) |
|---|---|---|---|
| 35 | 0,15 (graissé) | 0,93 | **1,67** |
| 35 | 0,30 (sec) | 1,86 | 3,35 |
| 30 | 0,15 | 1,22 | 2,19 |

Pour garder ce poste ≤ 1,7 µrad, il faut des contacts graissés et des rouleaux rectifiés.
Les rouleaux sont orientés vers le barycentre, ce qui donne un glissement purement radial
(`05`).

### Autres résultats

- **Effort de coupe.** La plaque fléchit de 0,06 µm/N au pire point (0,10 µm/N à 30 mm).
- **Palet de 10 g.** L'effet local est de 0,03 µrad, donc négligeable.
- **Fréquences propres** (plaque de 30 mm, k_appui = 4·10⁷ N/m) :
  - modes de corps rigide sur les appuis : 169 / 200 / 337 Hz ;
  - premier mode de flexion : 618 Hz.

Figures `support_slope_maps_G.png`, `support_slope_maps_P.png`,
`support_selected_maps.png` (schéma retenu, croix magenta : ADXL355),
`support_comparison_h30.png`, `support_thickness.png`, `support_modes_h30.png`,
`support_kelvin_radius_sweep.png`.

## 3. Variante « finition sur appuis de service » : conditions

1. **Mêmes vés.** Le montage de finition reproduit les 3 vés de service, au même diamètre
   de bille, aux positions ±0,5 mm et avec les mêmes axes de vé. La raideur des vés n'a
   aucune influence (isostatisme).
2. **Caisson monté** ou lest de 10,1 kg ±5 % réparti sur la ligne d'attache (demi-côté
   218). Les embases ADXL355 et l'écran (2 kg) sont montés, ou remplacés par un lest
   équivalent.
3. **Même orientation.** Face active vers le haut, gravité dans le même sens : le rodage
   sur rodoir est donc exclu.
4. **Démontage.** Après remontage sur le bâti, aucun réglage de hauteur des appuis n'est
   nécessaire (isostatique). Seuls le frottement et le positionnement des billes
   comptent.

## 4. Thermique (`thermal.py`)

Pour un flux traversant q, la courbure de la plaque vaut κ = α·q/k, indépendamment de
l'épaisseur. La pente crête qui en résulte sur la zone de travail est κ·s·√2.

**Exigences pour 5 µrad :**

- κ ≤ 2,4·10⁻⁵ m⁻¹ ;
- flux traversant ≤ 108 W/m² ;
- **ΔT haut/bas ≤ 34 mK** pour e = 35 (29 mK pour e = 30). Le CdC indique 50 mK : à
  corriger.

**Modèle 1D transitoire à travers l'épaisseur.** L'air remonte dans les lamages Ø2
(laminaire, Nu = 3,66) et échange avec la plaque sur les 1–4 premiers mm. La face
supérieure échange avec le local (h = 3–10 W/m²K). Débits lus dans
`calc/aero/results/network.json`, au moment du calcul : 6,5–20 m³/h.

| Cas (e = 35) | Résultat |
|---|---|
| Air soufflé +1 K, régime établi | 0,15–0,44 µrad/K ; ΔT haut/bas ≈ 1–3 mK |
| Échelon +1 K de l'air (démarrage, changement de débit) | pic transitoire **1,4 µrad/K** (Qmax), 0,6 µrad/K (Qmin) ; stabilisation 44–50 min |
| Constante de temps plaque/air | 21 min (Qmax) à 54 min (Qmin) |
| Rampe du local de 1 K/h (air aspiré dans le local) | 0,35–0,43 µrad ; retard de la plaque 0,3–0,8 K |
| Échauffement de l'air par le ventilateur (P_él ≈ Q·Δp/0,25) | 0,2 K (min) à 1,1 K (max) |

**Conclusions :**

- L'écart air/plaque admissible est de **3,6 K**. Il suffit de prévoir une attente de
  **≈ 45 min** après un changement de débit important, et de surveiller
  ΔT(air plenum − plaque) avec 2 TMP117.
- La thermique n'est pas dimensionnante : prévu 1,4 µrad pour un budget de 5.

**Embase des ADXL355 :**

- un gradient latéral de 50 mK dans l'embase (pieds de 12 mm, entraxe 40 mm) donne
  **0,35 µrad** ;
- un gradient vertical de 20 mK dans le bloc de 15 mm, avec un capteur excentré de 5 mm,
  donne 0,15 µrad ;
- la dérive d'offset ADXL355 après compensation par TMP117 (10 % résiduels, ±0,5 K/jour)
  vaut **1,0 µrad typique / 7,5 µrad maximum**. Elle est éliminée par le retournement à
  180° (`05`).

## 5. Matériaux (`materials.py`, `materials_table.md`)

| Matériau | ρ/E (rel.) | α/k (rel.) | e pour la même pente de poids propre | Points clés |
|---|---|---|---|---|
| **5083 coulée (réf.)** | 1,00 | 1,00 | 35 | contraintes résiduelles très faibles, perçage facile, ≈ 0,4 k€ brut |
| MIC-6 | 1,00 | 0,76 | 35 | équivalent (approvisionnement US) |
| 6061-T651 laminée | 1,03 | 0,64 | 36 | meilleur α/k mais **voilage** au perçage dissymétrique (17 % de matière ôtée sur une face) |
| Fonte GJL-250 | 1,72 | 0,99 | 46 | 68 kg, plus mauvaise en poids propre |
| Inox 1.4301 | 1,08 | 4,9 | 36 | thermiquement mauvais, perçage Ø0,4 difficile |
| Granit | 1,42 | 10,9 | 42 | rodage excellent, mais 6 000–17 000 trous Ø0,4 prohibitifs ; α/k désastreux |
| Alumine 96 % | 0,33 | 1,27 | 20 | rigide et légère, perçage laser coûteux |
| Invar 36 | 1,51 | 0,59 | 43 | 77 kg, cher, usinage difficile |

L'aluminium coulé reste le meilleur compromis. Les alternatives qui battent l'aluminium
sur un critère, comme l'alumine en ρ/E, perdent sur le perçage ou sur le coût.

## 6. Accéléromètres ADXL355 : emplacements

- **Positions :** 4 embases sur la face supérieure, en (−220 ; +220), (+220 ; +220),
  (−220 ; −220) et (+220 ; −220). Elles sont dans la bande pleine (entre 180 et 260 mm),
  hors zone percée, et loin des appuis (situés sous la plaque).
- **Pente locale par rapport au plan de la zone de travail** (e = 35, chemin B) :
  - **pression :** ±2,0 µrad sur chaque composante, de signes opposés d'un coin à
    l'autre. **La moyenne des 4 capteurs est nulle** (symétrie du dôme), et il en va de
    même pour un bombé thermique sphérique.
  - **poids propre :** +8,1 / +4,3 µrad (coins arrière) et −19,9 / −2,4 µrad (coins
    avant). Ces valeurs sont statiques : elles font partie de l'offset calibré par la
    dérive des palets.
- **Bonus :** la différence entre capteurs mesure la courbure de la plaque (déformation
  sous pression ou thermique). C'est la « mesure directe de déformation » demandée par
  le CdC § 4.8, avec une résolution limitée par le bruit (≈ 2 µrad en 100 s).

## 7. Bâti, caisson, panneaux (`frame.py`)

**Bâti de référence.** Profilés Bosch Rexroth rainure 10 :

- cadre supérieur 45×90 posé de chant, axe à 250 mm du centre, soit 545 × 545 hors tout,
  axe à z = 745 ;
- 4 montants 45×90 ;
- ceinture basse 45×45 à z = 150 et étagère 45×45 à z = 420 (ventilateur et caisson
  filtre) ;
- pieds M16 à rotule.

Le modèle EF utilise des poutres 3D, des assemblages semi-rigides (tronçons de 20 mm à
25 % d'inertie), la plaque et le caisson en corps rigide de 35 kg sur 3 ressorts
3·10⁷ N/m, et des pieds en rotule.

| Bâti | Contreventement | 1er / 2e / 3e mode | Masse des profilés |
|---|---|---|---|
| Référence | aucun | **26** (balancement y) / 31 / 44 Hz | 27,3 kg |
| **Référence** | **écharpes 45×45 sur 3 faces (arrière, gauche, droite)** | **49** (torsion) / 63 / 92 Hz | 31,1 kg |
| Référence | 4 faces | 63 / 77 / 96 Hz | 32,3 kg |
| Référence, assemblages rigides (borne haute) | 3 faces | 55 / 68 / 97 Hz | 31,1 kg |
| Paillasse (variante économique, montants de 300 mm) | aucun | 28 / 28 / 44 Hz | 5,1 kg |
| Paillasse | 3 faces | 86 / 104 / 155 Hz | 7,9 kg |

- La face avant reste ouverte pour l'accès.
- La raideur verticale du cadre sous les appuis vaut 33–54 N/µm.
- Pour la paillasse, la table support domine (souvent 15–30 Hz) : il faut l'évaluer sur
  place.
- La constante de torsion des profilés n'est pas publiée dans la veille. Le modèle prend
  J = 0,3·(Iy + Iz), une hypothèse à confirmer sur la fiche Rexroth.

**Caisson suspendu (chemin B).** Intérieur 430 × 430, parois et fond en aluminium de 6 mm,
tôle de distribution inox de 1 mm. Masse **10,1 kg**.

Panneaux sous 400 Pa (plaque simplement appuyée, calcul de Navier) :

| Panneau | Flèche | Contrainte |
|---|---|---|
| Fond alu 430 × 430 × 6 | 39 µm | 0,6 MPa |
| Paroi alu 6 mm | 2 µm | — |
| Hublot PC 6 mm | 65 µm | — |
| Fond PMMA 8 mm | 0,35 mm (à éviter) | — |

Les panneaux du bâti ne sont pas pressurisés au chemin B : on peut prendre des panneaux
composites de 4 mm dans les rainures, avec le joint item/Fath 4–6 mm.

**Manchon souple Ø80** (ventilateur → caisson) : poussée de 2,0 N à 400 Pa, reprise par le
caisson, effet négligeable.

**Membrane roulante semi-circulaire** (seulement au chemin A, variante non retenue) :

- boucle de rayon 8 mm, tension p·r = 3,2 N/m ;
- tissu enduit de 0,4 mm, soit 8 kPa ;
- l'aire efficace ne dépend que du jeu horizontal (±0,5 mm → ±0,6 % de la poussée).

## 8. Données pour la CAO

Repère : centre de la plaque, x à droite, y vers l'arrière, z vers le haut. z = 0 au sol
pour le bâti, et face inférieure de la plaque pour les cotes de plaque.

| Élément | Cotes |
|---|---|
| Plaque | 520 × 520 × **35**, EN AW-5083 coulée ; détail des perçages, datums et taraudages : `04` § 7 |
| Appuis (centres des billes, plan XY) | P0 (0 ; +242,5) fixe ; P1 (+242,5 ; −145,5) et P2 (−242,5 ; −145,5) motorisés |
| Billes | Ø25,4 G10 (100Cr6), collées dans un logement Ø25,4 H8 × 10,7 de la plaque, centre à 2 mm sous la face inférieure ; contacts sur les rouleaux 11 mm sous la face |
| Vés | 2 rouleaux Ø20 × 30 h6 trempés par vé, vé à 90°, axes orientés vers (0 ; −16,2) : P0 → −90°, P1 → 151,9°, P2 → 28,1° (angle depuis +x) |
| Caisson | intérieur 430 × 430, parois de 6 mm (demi-côtés 215–221), hauteur intérieure 160 (distribution 62 + tôle + tranquillisation 80 + marge), fond de 6 mm ; joint plat EPDM 6 × 2 sur la plaque ; cornière intérieure 15 × 15 × 3, 32 vis M5 sur le carré de demi-côté 208 |
| Jeu caisson / cadre | 6,5 mm (paroi extérieure 221, face intérieure du cadre 227,5) |
| Cadre supérieur | 4 × 45×90 de chant, axe sur le carré de demi-côté 250 (545 hors tout), axe à z = 745, dessus à z = 790. Empilement : vérin à mi-course 45 → dessus de tête 835 ; vé : axes des rouleaux à 847 ; centre de bille 863,05 (16,05 au-dessus des axes, entraxe des rouleaux 32,1) ; face inférieure de plaque 865 ; **dessus de plaque 900** |
| Montants | 4 × 45×90, de z = 0 à 790, aux coins (±250 ; ±250) |
| Ceinture basse / étagère | 45×45 à z = 150 et z = 420 |
| Écharpes | 45×45 dans les faces arrière, gauche et droite, de la ceinture basse (z = 150) au cadre (z = 745), en diagonale |
| Pieds | 4 × M16 × 2, rotule, patin Ø80 |
| Embases ADXL355 | 4 en (±220 ; ±220) sur la face supérieure (`05` § 5) |
| Variante paillasse | cadre 45×45 sur le carré de demi-côté 250 à z = 300 au-dessus de la table, montants 45×45 de 300, écharpes 45×45 sur 3 faces ; ventilateur posé à côté, sur la table |

## Historique

- 2026-10-29 : homogénéisation et plaque EF vérifiées ; sondage des schémas (provisoire).
- 2026-11-03 :
  - étude des appuis exécutée (accélérée : 2,2 min) ;
  - schéma retenu : 3 appuis cadre optimisés, chemin B, finition sur appuis ;
  - e = 35 mm ;
  - étude du pas (2,94 / 4,23 / 4,82 / 5,0, lamage Ø2 ou Ø1,5) ;
  - thermique, matériaux, bâti ;
  - emplacements des ADXL355.
