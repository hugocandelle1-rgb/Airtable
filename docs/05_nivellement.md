# 05 — Nivellement : couplage cinématique, vérins à coin, accéléromètres

> Lot structure. Calcul : `calc/structure/kinematic_coupling.py` (Hertz, bras de levier,
> vérins). Résultats : `results/kinematic_coupling.json`. Les données d'appui viennent
> de `support_study.json` et la thermique de l'embase de `thermal.json`.
>
> Exigences du CdC :
>
> - réglage 2 axes ;
> - résolution ≤ 2 µrad ;
> - course ±0,25° ;
> - réglage manuel **et** motorisé ;
> - inclinaison résiduelle ≤ 5 µrad.

## 1. Architecture

```
            P0 (0 ; +242,5)  vé fixe sur rehausse
                 ▲ arrière
   plaque 520 ×  │
   520 × 35      │      tangage : P1 + P2 montent ensemble (bras 388 mm)
                 │      roulis  : P1 − P2 en différentiel (bras 484 mm)
 P2 (−242,5 ; −145,5)          P1 (+242,5 ; −145,5)
   vérin à coin motorisé       vérin à coin motorisé
```

- **3 appuis Maxwell** (bille dans un vé). Les appuis sont sur le cadre supérieur
  45×90, hors du caisson de plenum (`03` § 2).
- **P0 est fixe.** P1 et P2 sont réglés par des vérins à coin. Le bâti est isostatique
  vis-à-vis de la plaque : son gauchissement ne change que l'inclinaison d'ensemble.
- **Réglage grossier :** 4 pieds M16 × 2 du bâti, environ 4 mrad par tour sur 500 mm. On
  amène la plaque à ±1 mrad, puis le réglage fin prend le relais.

## 2. Couplage bille / vé

| Grandeur | Valeur |
|---|---|
| Bille | Ø25,4 G10, 100Cr6, **collée** dans un logement Ø25,4 H8 × 10,7 de la plaque ; centre à 2 mm sous la face inférieure |
| Vé | 2 rouleaux Ø20 × 30 h6 trempés rectifiés (arbres de guidage 60 HRC), vé à 90°, entraxe 32,1 mm, serrés dans un bloc |
| Orientation des vés (Maxwell) | axes vers le barycentre (0 ; −16,2) : P0 −90°, P1 151,9°, P2 28,1° (depuis +x) |
| Réactions (poids propre, e = 35, caisson compris) | 130,0 / 108,3 / 108,3 N |
| Précharge | **aucune** : le poids suffit ; brides anti-soulèvement à 0,5 mm de jeu (manutention, choc) |
| Hertz bille/rouleau (par contact, 92 / 76 N) | p_max **1,54 / 1,45 GPa**, ellipse 0,44 × 0,26 mm, enfoncement 3,6 / 3,1 µm |
| Raideur verticale d'un appui (Hertz) | 3,7–3,9·10⁷ N/m ; chaîne avec coin et vis : 31–32 N/µm |
| Fréquence de pompage de la plaque | ≈ 260 Hz sur les appuis ; ≈ 185 Hz avec la souplesse locale du cadre |
| Lubrification | film de graisse fine sur les rouleaux : µ ≈ 0,15 → frottement ≤ 1,7 µrad (`03` § 2) ; à sec, µ = 0,3 → 3,4 µrad |

**Pression de contact.** p_max ≈ 1,5 GPa reste bien en dessous du seuil d'enfoncement
permanent (≈ 4 GPa pour l'acier à roulement), ce qui garantit une bonne répétabilité.
Une bille Ø30 sur des rouleaux Ø20 descendrait à 1,4 GPa, mais son logement viendrait
à moins de 3 mm du chant.

**Glissement thermique.** Si la plaque est 1 K plus chaude que le bâti, les billes
glissent radialement de 6 µm dans les vés, vers ou depuis le barycentre. C'est un
glissement pur : aucun effort de contrainte.

## 3. Vérin à coin (référence : motorisé + manuel)

| Élément | Choix |
|---|---|
| Coin | acier trempé, pente **1:5** (11,31°), 60 × 24 mm, sur cages à aiguilles plates dessus et dessous (pas de stick-slip) |
| Tête | guidée verticalement par 2 lames flexibles parallèles (acier ressort 0,3 × 20 × 30) : ni jeu ni frottement ; reçoit le bloc de vé |
| Vis | **M6 × 0,25** (vis de réglage fin, écrou bronze rattrapé par ressort de 50 N) ; irréversible (angle d'hélice 0,8° < angle de frottement) |
| Moteur | **NEMA17** 200 pas/tr à **double arbre**, accouplement à soufflet ; driver TMC2209 en 1/16 (silencieux) |
| Manuel | bouton Ø40 gradué en 100 divisions sur l'arbre arrière du moteur (driver désactivé) |

| Performance | Valeur |
|---|---|
| Déplacement vertical | 50 µm/tr ; **250 nm par pas entier** |
| Résolution angulaire | **0,64 µrad/pas** en tangage (bras 388 mm), 0,52 µrad en roulis, 0,61 µrad pour un seul vérin ; manuel : 1,29 µrad/graduation |
| Exigence | ≤ 2 µrad : **tenue** (×3 en pas entier ; le micropas sert au lissage, pas à la résolution) |
| Course verticale | ±2,43 mm (±0,25° + 15 % de marge, tangage et roulis combinés) |
| Course du coin | ±12,1 mm = **±49 tours** = ±9 700 pas ; course complète en ≈ 25 s à 2 tr/s |
| Effort sur la vis | 22 N à la montée, 21 N en retour (coin sur aiguilles) |
| Couple moteur | 12,5 mN·m (NEMA17 : ≈ 400 mN·m de maintien, marge > 30) |
| Thermique | **couper le courant moteur après réglage**. La vis étant irréversible, la position tient. Un NEMA17 alimenté dissipe 2–4 W à 250 mm du bord de la plaque : gradient inacceptable |
| Jeu | approche toujours dans le même sens (montée) : dépassement d'un tour puis retour ; écrou rattrapé |

**Boucle fermée.** La consigne est la moyenne des 4 ADXL355 (§ 5), filtrée sur 100 s
(bruit ≈ 0,9 µrad). Le contrôleur converge en 2–3 itérations, puis coupe les moteurs.
L'inclinaison résiduelle prévue est de **1,4 µrad** :

- quantification 0,37 µrad ;
- bruit 0,9 µrad ;
- offset résiduel 1,0 µrad ;
- embase 0,35 µrad.

L'allocation est de 5 µrad.

## 4. Variante économique (manuelle, composants du commerce)

| Élément | Choix |
|---|---|
| Coin | même coin 1:5, glissant sur bronze (sans cage à aiguilles) |
| Actionneur | ajusteur **différentiel** du commerce, type Thorlabs DAS110 (vis fine 25 µm/tr, grossière 318 µm/tr ; `docs/research/profiles_alu_et_mecanique.md`) |
| Résolution | fine : 5 µm/tr vertical, soit **12,9 µrad/tr** ; tambour de 50 divisions, soit **0,26 µrad/div** ; grossière : 164 µrad/tr |
| Effort | 33 N à la montée et 11 N en retour (coin sur bronze, µ = 0,1). **La charge admissible du DAS110 n'est pas confirmée.** Repli : Newport AJS127-0.5, 90 N, 0,2 mm/tr → 103 µrad/tr, 1 µrad/div sur 100 divisions |
| Course | grossière : ±12 mm de coin si l'ajusteur a 25 mm de course (à vérifier) ; sinon pieds du bâti |
| Bâti | « paillasse » posé sur une table existante (`03` § 7), 4 pieds M12 pour le grossier |
| Lecture | 4 ADXL355 (mêmes embases), affichage sur PC ; réglage à la main |

Le risque de stick-slip du coin sur bronze se gère en approchant toujours en montée.

## 5. Accéléromètres ADXL355 : emplacement, embase isotherme, retournement

**Emplacement.** 4 embases sur la face supérieure, en (±220 ; ±220) :

- dans la bande pleine, hors zone percée ;
- au droit d'aucun appui ;
- à 40 mm du bord de la zone percée.

La **moyenne des 4** donne l'inclinaison du plan : le dôme de pression (±2,0 µrad par
capteur) et un bombé thermique s'annulent par symétrie. La pente locale de poids propre
(−20 à +8 µrad selon le coin) est statique et entre dans l'offset calibré.

### Embase (par capteur)

| Pièce | Description |
|---|---|
| Socle | bloc 6082 de 60 × 60 × 20, 3 pieds Ø8 × 12 sur un cercle Ø40 à 120°, vissés M4 dans la plaque avec pâte thermique (R ≈ 0,3 K/W). La constante de temps du bloc vis-à-vis de la plaque est de 0,9 min : **le capteur suit la température de la plaque** |
| Plateau rotatif | Ø50 en alu, 3 billes Ø4 à 120° sur un rayon de 18 mm, reposant sur **6 vés radiaux à 60°** du socle. Les positions 0° et 180° utilisent deux jeux de 3 vés. Un ressort axial de 10 N assure l'assise, et l'axe central sert de pivot |
| Capteurs | carte ADXL355 + **TMP117 accolé** (même plage de cuivre), au centre du plateau ; axes alignés sur x/y à ±1° |
| Capot isolant | polystyrène extrudé de 10 mm (λ ≈ 0,035) doublé d'un film alu. R ≈ 24 K/W : l'air n'influe qu'à 1,2 % sur le bloc |
| Retournement manuel | levier à came (soulève de 0,5 mm), rotation de 180° jusqu'à la butée, reposé |
| Retournement motorisé | petit moto-réducteur pas à pas avec manchon à rampe hélicoïdale : soulève, tourne de 180°, repose. Moteur hors tension pendant la mesure |

**Mesure par retournement.** On a r₀ = θ + b et r₁₈₀ = −θ + b + c, où :

- b est l'offset du capteur ;
- c est l'écart constant entre les deux jeux de vés.

On en tire θ = (r₀ − r₁₈₀)/2 + c/2. La constante c est étalonnée une fois par dérive des
palets. Le terme b = (r₀ + r₁₈₀ − c)/2, suivi en fonction de T (TMP117), **réétalonne
automatiquement le coefficient thermique** d'offset.

**Erreurs estimées (`thermal.json`) :**

| Source | Erreur |
|---|---|
| Gradient latéral de 50 mK dans le socle | 0,35 µrad |
| Gradient vertical de 20 mK | 0,15 µrad |
| Dérive d'offset après compensation TMP117 (10 % résiduels, ±0,5 K/jour) | 1,0 µrad typique / 7,5 µrad maximum ; annulée à chaque retournement |
| Répétabilité d'assise (0,1 µm sur une base de 27 mm) | ≈ 3,7 µrad par retournement ; ≈ 1,9 µrad en moyenne sur 4 |

**Fréquence de retournement :** une fois par jour, ou dès que la température dérive de
plus de 0,2 K.

## 6. Procédure de mise à niveau

1. **Grossier.** Pieds du bâti, avec un niveau à bulle de 0,02 mm/m, jusqu'à ±1 mrad.
   Vérins fins à mi-course.
2. **Mise en régime.** Ventilateur à la pression de travail, attente de **45 min**
   (thermique, `03` § 4).
3. **Retournement des 4 ADXL355** : mise à jour des offsets.
4. **Boucle fine.** Moyenne des 4 capteurs sur 100 s, puis correction du tangage (P1 et
   P2 ensemble) et du roulis (P1 − P2), en approche montante. Répéter jusqu'à moins de
   2 µrad, puis couper les moteurs.
5. **Contrôle par palet témoin.** Dérive sur 10 s au centre et aux 4 coins. Avec la carte
   de pente (variante économique), le contrôle des robots compense le résidu.
6. **Surveillance continue.** Moyenne des ADXL355 et TMP117. Alarme si la pente dérive
   de plus de 3 µrad ou si l'écart air/plaque dépasse 1 K.

## 7. Données pour la CAO

| Élément | Cotes |
|---|---|
| Points d'appui (centres des billes, plan XY) | P0 (0 ; +242,5) ; P1 (+242,5 ; −145,5) ; P2 (−242,5 ; −145,5). Centre de bille à z_plaque = −2,0 |
| Logements des billes (plaque) | Ø25,4 H8, profondeur 10,7, bille collée (époxy structural) |
| Bloc de vé | 40 (le long de l'axe du vé) × 30 × 20 ; 2 rouleaux Ø20 × 30 h6, axes parallèles à l'axe du vé, entraxe 32,1, axes à 12 au-dessus de la base du bloc ; centre de bille à 16,05 au-dessus des axes |
| Axes des vés | P0 : −90° ; P1 : 151,9° ; P2 : 28,1° (depuis +x, vers le barycentre (0 ; −16,2)) |
| Vérin à coin (P1, P2) | boîtier 90 (le long du cadre) × 30 (radial) × 45 (haut, tête à mi-course) ; coin 60 × 24, pente 1:5, course ±12,1 ; tête à course verticale ±2,43, guidée par 2 lames de 0,3 × 20 × 30 ; vis M6 × 0,25 selon l'axe du cadre ; NEMA17 (42 × 42 × 40, double arbre) en bout, posé sur le cadre ; bouton Ø40 à 100 divisions |
| Rehausse de P0 | bloc fixe de 45 de haut (même hauteur que le vérin à mi-course), 40 × 30 |
| Hauteurs | dessus du cadre z = 790 ; dessus des têtes 835 ; axes des rouleaux 847 ; centre de bille 863 ; face inférieure de plaque 865 ; dessus de plaque 900 |
| Brides anti-soulèvement | 3 étriers sur le cadre, au droit de P0, P1 et P2, patin PTFE Ø10 à 0,5 mm au-dessus de la face supérieure |
| Embases ADXL355 | 4 en (±220 ; ±220) ; socle 60 × 60 × 20, 3 pieds Ø8 × 12 sur Ø40 (M4) ; plateau Ø50, 3 billes Ø4 sur R18, 6 vés à 60° ; capot 80 × 80 × 45 en XPS de 10 mm |
| Pieds du bâti | 4 × M16 × 2, patin Ø80 à rotule (variante paillasse : M12) |
| Variante économique | même coin et même vé ; l'ajusteur différentiel remplace vis et moteur (ajusteur Ø9,5 dans un palier de bride, axe selon le cadre) |

## Historique

- 2026-11-03 :
  - création ;
  - couplage Maxwell bille Ø25,4 / rouleaux Ø20 ;
  - vérin à coin 1:5 + M6×0,25 + NEMA17 : 0,64 µrad/pas ;
  - variante économique (ajusteur différentiel) : 0,26 µrad/div ;
  - 4 ADXL355 sur embases isothermes à retournement 180°.
