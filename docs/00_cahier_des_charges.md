# 00 — Cahier des charges et budget d'erreur

> Table à coussin d'air pour palets-robots cylindriques Ø30 mm, 2 à 10 g.
> Version V3 (reprise complète après les versions précédentes).
> Les valeurs numériques font foi dans `params/design.toml`.

## 1. Besoin

Mettre en mouvement des palets-robots (cylindres pleins Ø30 mm, actionneurs sur les
faces latérales verticales) sur un plan où **l'effet de la gravité dans le plan est
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

## 3. Budget d'erreur de pente (cible ≤ 50 µrad crête, objectif ≤ 20 µrad)

| Poste | Allocation | Moyen de maîtrise |
|---|---|---|
| Inclinaison globale résiduelle après réglage | ≤ 5 µrad | réglage motorisé 2 axes, résolution ≤ 2 µrad, inclinomètre + calibration par palet |
| Défaut de planéité usinage (statique) | ≤ 30 µrad | planéité ≤ 6 µm sur zone percée, ≤ 2 µm sur 100 × 100 mm |
| Flèche sous poids propre sur appuis | ≤ 10 µrad | appuis isostatiques à position optimisée, plaque épaisse |
| Variation de flèche avec la pression | ≤ 5 µrad | ≤ 1,5 µm entre p = 0 et p = pmax |
| Gradient thermique à travers l'épaisseur | ≤ 5 µrad | ≤ 0,05 K (échangeur naturel : l'air traverse la plaque) |
| Dérive du sol / bâtiment | ≤ 5 µrad | sol béton, surveillance continue, recalage automatique |
| **Somme quadratique** | **≈ 33 µrad** | |

## 4. Exigences fonctionnelles

1. **Portance** : chaque palet de la gamme flotte avec un entrefer 80–250 µm à un point
   de fonctionnement atteignable par modulation de vitesse du (des) ventilateur(s).
2. **Uniformité** : pression statique du plenum uniforme à ± 1 % sur la zone percée ;
   pas de jet résiduel du ventilateur sous la plaque.
3. **Stabilité du film** : pas de marteau pneumatique (volume aval des orifices minimal),
   pas d'effet de « crantage » perceptible lié au pas des trous.
4. **Écoulement propre** : zone de travail sans turbulence ni courant transverse ;
   écran anti-courant d'air recommandé.
5. **Planéité / rigidité** : voir budget § 3.
6. **Réglage d'inclinaison** 2 axes, résolution ≤ 2 µrad (≈ 0,0001°), course ± 0,25°,
   manuel **et** motorisé (boucle numérique).
7. **Étanchéité** entre chaque étage : ventilateur → adaptateur → diffuseur →
   chambre de distribution → chambre de tranquillisation → plaque.
8. **Instrumentation** : inclinaison 2 axes, pression (plusieurs points), débit,
   vitesse de rotation, températures (plaque haut/bas, air, local), déformation de
   plaque (mesure directe), avec boucles de régulation.
9. **Structure** : squelette en profilés aluminium du commerce, panneaux maintenus
   dans les rainures avec joints, pièces sur mesure limitées et usinables en atelier.
10. **Propreté** : air filtré (les orifices de 0,4 mm ne doivent jamais se boucher).

## 5. Hypothèses

- Air à 20 °C, ρ = 1,204 kg/m³, μ = 1,81·10⁻⁵ Pa·s.
- Laboratoire tempéré (± 1 K/h), sol béton de rez-de-chaussée de préférence.
- La face inférieure des palets est plane à 5 µm près (à garantir côté palets ; voir
  `docs/` recommandations palets).
