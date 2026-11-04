# 00 — Cahier des charges et budget d'erreur

> Table à coussin d'air pour palets-robots cylindriques Ø30 mm, 2 à 10 g.
> Version V3.2 (2026-11-04) : budget révisé en « force parasite = erreur de mesure »,
> paramétré par θ = a_par/g (§ 3).
> Les valeurs numériques font foi dans `params/design.toml`.

## 1. Besoin

Caractériser le mouvement dans le plan de palets-robots (cylindres pleins Ø30 mm,
actionneurs électrostatiques radiaux sur les faces latérales verticales) sur un plan où
**toute force parasite dans le plan (gravité, crantage, balourd, courants d'air) est
négligeable** devant les efforts des actionneurs, et où le palet est porté par un film
d'air stable, sans turbulence, dans une zone de travail carrée de 300 × 300 mm.

| Donnée | Valeur |
|---|---|
| Diamètre palet | 30 mm (surface 7,07 cm²) |
| Masse palet | 2 g → 10 g (cas de calcul 2 / 3 / 5 / 7,5 / 10 g) |
| Pression moyenne de portance W/A | 27,7 Pa (2 g) → 139 Pa (10 g) |
| Zone de travail | carré 300 × 300 mm (le palet entier reste dedans) |
| Zone percée | carré 360 × 360 mm (300 + 2 × rayon + 2 × 15 mm de marge) |

## 2. Pourquoi les tolérances sont si serrées : la pente équivaut à une force

Un palet sans frottement sur un plan incliné de θ accélère à `a = g·sin θ ≈ g·θ`.

| Pente θ | en degrés | a (mm/s²) | dérive depuis l'arrêt en 2 s | en 5 s |
|---|---|---|---|---|
| 175 µrad | 0,01° | 1,71 | 3,4 mm | 21 mm |
| 50 µrad | 0,0029° | 0,49 | 1,0 mm | 6,1 mm |
| 20 µrad | 0,0011° | 0,20 | 0,4 mm | 2,5 mm |
| 5 µrad | 0,0003° | 0,05 | 0,1 mm | 0,6 mm |

Équivalence géométrique : une pente de 50 µrad, c'est **18 µm de dénivelé sur 360 mm**.
Un bombé (flèche δ sur une longueur L) a une pente maximale ≈ 4δ/L : δ = 5 µm sur
360 mm donne déjà 56 µrad. **La planéité de la plaque, sa déformation sous charge et
le réglage d'inclinaison sont donc trois termes du même budget.**

## 3. Budget de force parasite (révision du 2026-11-04)

### 3.1 Critère : une erreur de mesure, sans compensation

Les palets portent des actionneurs électrostatiques radiaux. La table sert à
**caractériser** le mouvement dans le plan que produit cet actionnement. Toute force
parasite dans le plan est donc une erreur de mesure :

- pente locale (réglage, planéité, flexions, thermique, sol) ;
- crantage du film d'air ;
- dispersion des orifices ;
- balourd des palets ;
- courants d'air.

Les palets ne sont pas pilotés dans le plan, et aucune compensation logicielle des
palets n'est prévue (décision du 2026-11-03).

Le paramètre principal est **l'accélération parasite admissible a_par**, exprimée en
pente équivalente θ = a_par/g. Pour un palet de masse m, la force parasite vaut
F_par = m·g·θ. Elle doit rester ≪ F_act. Le critère retenu est que la **somme
quadratique de tous les postes, exprimés en pente équivalente, reste ≤ θ**. Calcul :
`calc/structure/passive_budget.py` ; résultats dans
`calc/structure/results/passive_budget_table.md`.

### 3.2 Ce que représente chaque niveau

| θ (µrad) | a_par (µm/s²) | Erreur ½·a·T² à T = 1 / 5 / 10 / 30 s | F_par à 2 g / 10 g | F_act minimale pour F_par/F_act ≤ 1 % (2 g / 10 g) |
|---|---|---|---|---|
| 5 | 49 | 0,025 / 0,61 / 2,5 / 22 mm | 0,10 / 0,49 µN | 10 / 49 µN |
| 10 | 98 | 0,049 / 1,2 / 4,9 / 44 mm | 0,20 / 0,98 µN | 20 / 98 µN |
| 20 | 196 | 0,098 / 2,5 / 9,8 / 88 mm | 0,39 / 1,96 µN | 39 / 196 µN |
| 30 | 294 | 0,15 / 3,7 / 15 / 132 mm | 0,59 / 2,9 µN | 59 / 294 µN |
| 50 | 490 | 0,25 / 6,1 / 25 / 221 mm | 0,98 / 4,9 µN | 98 / 490 µN |

Le calcul ½·a·T² est balistique. Avec l'amortissement de Couette du film
(τ = 18 s à 2 g, 63 s à 10 g), l'erreur à 30 s est d'environ 60 % (2 g) à 85 % (10 g)
de cette valeur.

**Lecture :**

- pour F_act ≥ 1 mN, tous les niveaux donnent moins de 0,5 % d'erreur de force ;
- pour F_act ≈ 1 µN, il faudrait θ ≤ 1 µrad (2 g) pour rester à 10 % : c'est hors
  d'atteinte ;
- le niveau à viser se déduit de la plus petite F_act à caractériser.

**C'est une donnée d'entrée à fournir par l'utilisateur.**

### 3.3 Répartition et exigences par niveau

Les valeurs sont des pentes équivalentes en µrad. Pour chaque niveau, la somme
quadratique des postes doit rester ≤ θ.

| Poste | Plancher technique | Conception actuelle | θ = 20 | θ = 30 | θ = 50 |
|---|---|---|---|---|---|
| Planéité de la face supérieure | 5,4 | 30,5 (2,8 µm) | 11,6 | 17,6 | 30,5 |
| Crantage (lot aéro) | 7,5 (corrigé a posteriori) | 33 (brut) | 9,8 | 14,9 | 33 |
| Dispersion des orifices | 3,4 (±0,002) | 8,5 (±0,005) | 7,6 | 11,5 | 8,5 |
| Balourd des palets (0,9 µrad/µm) | 1,8 (2 µm) | 9,0 (10 µm) | 6,9 | 10,5 | 9,0 |
| Courants d'air résiduels | 1,0 | 5,0 | 6,9 | 10,5 | 5,0 |
| Réglage, stabilité, sol, poids propre, pression, thermique (6 postes) | 0,2–0,5 chacun | 1,0–2,0 chacun | idem | idem | idem |
| **Somme quadratique** | **10,1** | **47,0** | 20 | 30 | 47 |

Les niveaux **θ = 5 et 10 µrad ne sont pas réalisables** : la somme quadratique des
planchers vaut 10,1 µrad. Sans correction a posteriori du crantage, le minimum est de
**33,7 µrad**.

| Exigence | θ = 20 | θ = 30 | θ = 50 |
|---|---|---|---|
| Crantage | correction a posteriori de la mesure (résidu ≤ 10 µrad) | correction a posteriori (≤ 15 µrad) | brut acceptable |
| Planéité zone percée / par 100 × 100 | 1,1 / 0,21 µm | 1,6 / 0,31 µm | 2,8 / 0,54 µm |
| Procédé de finition | tournage diamant optique + passes de correction (grands opticiens ; capacité non confirmée) | tournage diamant mono-pointe ultra-précis (ateliers d'optique métallique) | fly-cut diamant de précision sur appuis de service |
| Équilibrage des palets (excentrement du centre de gravité) | ≤ 7,7 µm | ≤ 11,7 µm | ≤ 10 µm |
| Tolérance Ø orifices | ±4,5 µm | ±6,8 µm | ±5 µm |
| Vitesse d'air au niveau des palets | ≤ 20 mm/s | ≤ 25 mm/s | ≤ 17 mm/s |
| Écart air soufflé / plaque | ≤ 0,7 K | ≤ 0,7 K | ≤ 0,7 K |
| Rampe du local | ≤ 2,2 K/h | ≤ 2,2 K/h | ≤ 2,2 K/h |
| Variation du local entre recalages | ≤ 0,5 K | ≤ 0,5 K | ≤ 0,5 K |
| Recalage d'inclinaison (ADXL355, automatique) | toutes les heures | toutes les heures | toutes les heures |
| Retournement des ADXL355 | 1 fois par jour | 1 fois par jour | 1 fois par jour |
| Verdict | à la limite | réalisable (finition optique) | **réalisable avec la conception actuelle** |
| Coût relatif | ≈ 9 | ≈ 3 | ≈ 1,3 |

Notes :

- **Correction a posteriori du crantage.** Elle consiste à soustraire de la mesure la
  force de crantage connue, à partir d'une carte étalonnée et de la position du palet.
  Ce n'est pas un pilotage des palets, mais c'est **une décision utilisateur** à
  prendre pour tout niveau < 34 µrad.
- **Équilibrage et orifices.** Au niveau 50, les colonnes reprennent les valeurs de la
  conception actuelle (balourd 10 µm, orifices ±5 µm, air 17 mm/s). Aux niveaux 20 et
  30, ces postes sont redistribués pour compenser la planéité resserrée, et certaines
  valeurs se trouvent relâchées.
- **Hypothèses d'exploitation** (à confirmer sur site) : sol de rez-de-chaussée
  dérivant de 1 µrad/h ; gradient latéral du bâti égal à 10 % de la variation du local.

> **Ancienne version (V3, jusqu'au 2026-11-03), conservée pour l'historique.**
> Budget de pente ≤ 50 µrad crête (objectif ≤ 20 µrad), somme quadratique ≈ 33 µrad :
>
> - inclinaison ≤ 5 ;
> - planéité d'usinage ≤ 30 (« ⏥ 6 µm, 2 µm/100 × 100 ») ;
> - poids propre ≤ 10 ;
> - pression ≤ 5 ;
> - thermique ≤ 5 (0,05 K) ;
> - sol ≤ 5.
>
> Ce budget ignorait le crantage, la dispersion des orifices, le balourd et les courants
> d'air, qui relèvent du lot aéro et des palets. Il traduisait aussi 30 µrad par 6 µm,
> qui donnent en réalité 56 µrad (`docs/04_usinage_tolerances.md` § 1). Le gradient
> thermique admissible vaut 34 mK pour e = 35 mm, et non 50 mK.

## 4. Exigences fonctionnelles

1. **Portance** : chaque palet de la gamme flotte avec un entrefer 80–250 µm à un point
   de fonctionnement atteignable par modulation de vitesse du (des) ventilateur(s).
2. **Uniformité** : pression statique du plenum uniforme à ± 1 % sur la zone percée ;
   pas de jet résiduel du ventilateur sous la plaque.
3. **Stabilité du film** : pas de marteau pneumatique (volume aval des orifices minimal),
   pas d'effet de « crantage » perceptible lié au pas des trous.
4. **Écoulement propre** : zone de travail sans turbulence ni courant transverse ;
   écran anti-courant d'air recommandé.
5. **Planéité / rigidité** : voir budget § 3 (exigences par niveau θ).
6. **Réglage d'inclinaison** 2 axes, résolution ≤ 2 µrad (≈ 0,0001°), course ± 0,25°,
   manuel **et** motorisé (boucle numérique).
7. **Étanchéité** entre chaque étage : ventilateur → adaptateur → diffuseur →
   chambre de distribution → chambre de tranquillisation → plaque.
8. **Instrumentation** : inclinaison 2 axes, pression (plusieurs points), débit,
   vitesse de rotation, températures (plaque haut/bas, air, local), déformation de
   plaque (mesure directe), avec boucles de régulation.
9. **Structure** : squelette en profilés aluminium du commerce, panneaux maintenus
   dans les rainures avec joints, pièces sur mesure limitées et usinables en atelier.
10. **Propreté** : air filtré (les orifices de 0,30 mm ne doivent jamais se boucher).
11. **Équilibrage des palets** (nouveau) : le centre de gravité d'un palet doit coïncider
    avec l'axe du cylindre à ≤ 10 µm pour θ = 50 µrad, ≤ 12 µm pour θ = 30 µrad et
    ≤ 8 µm pour θ = 20 µrad. Chaque µm d'excentrement vaut 0,9 µrad de pente
    équivalente, et la force tourne avec le cap du palet. Il faut un contrôle par palet
    (balance à couteau ou dérive sur la table à 2–4 caps). Ce n'est pas une correction :
    les palets hors tolérance sont rééquilibrés.

## 5. Hypothèses

- Air à 20 °C, ρ = 1,204 kg/m³, μ = 1,81·10⁻⁵ Pa·s.
- Laboratoire tempéré (± 1 K/h), sol béton de rez-de-chaussée de préférence.
- La face inférieure des palets est plane à 5 µm près (à garantir côté palets ; voir
  `docs/` recommandations palets).
