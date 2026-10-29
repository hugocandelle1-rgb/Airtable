---
name: tolerancement-iso-gps
description: Méthode pour dériver des tolérances de fabrication à partir d'un budget fonctionnel et les écrire en cotation ISO GPS (ISO 1101, ISO 2768, ISO 286, ISO 21920/1302, DIN 876), avec gamme d'usinage et plan de contrôle. À utiliser pour toute mise en plan, spécification de planéité/parallélisme/position, choix de procédé de finition (rectification, rodage, surfaçage diamant), contrôle de planéité (MMT, méthode de Moody, niveau électronique, autocollimateur), en particulier pour la plaque perforée et les pièces d'appui de la table à air, même si la demande dit seulement « quelle précision faut-il ».
---

# Tolérancement fonctionnel ISO GPS

## Démarche (toujours dans cet ordre)

1. **Partir de l'effet fonctionnel**, pas de l'habitude d'atelier : pour la table à air,
   tout défaut géométrique se traduit en pente locale θ (µrad) ⇒ accélération g·θ.
2. **Allouer** un budget par contributeur (somme quadratique pour les termes
   indépendants, arithmétique pour les termes corrélés).
3. **Convertir** l'allocation en tolérance géométrique :
   - bombé/creux de flèche δ sur L → pente max ≈ 4δ/L ;
   - ondulation d'amplitude δ, longueur d'onde λ → pente max 2πδ/λ ;
   - le palet Ø30 mm moyenne les défauts de longueur d'onde < ~30 mm (filtre spatial).
4. **Choisir le procédé capable** (Cp ≥ 1,33 sur la tolérance) et le contrôle capable
   (incertitude ≤ 1/4 à 1/10 de la tolérance).
5. **Écrire la cotation** et le tableau « tolérance → effet → justification ».

## Références utiles

| Norme | Usage |
|---|---|
| ISO 1101 | Planéité, parallélisme, position, zones communes (CZ), zone restreinte (« 0,002 / 100×100 ») |
| ISO 2768-1/-2 (classe m ou f / K) | Tolérances générales non indiquées |
| ISO 286 | Ajustements des alésages/arbres (ex. pions Ø6 H7/m6) |
| ISO 21920 (remplace ISO 4287) / ISO 1302 | Rugosité Ra, Rz |
| ISO 13715 | États d'arêtes (bavures, chanfreins) |
| DIN 876 / ISO 8512-2 | Plans de référence : t = c·(1 + L/1000) µm, L = diagonale (mm) ; classe 00 : c = 2 ; 0 : c = 4 ; 1 : c = 8 ; 2 : c = 16 |
| ISO 230-1, ASME B89.3.7 | Mesure de planéité : méthode de Moody (« Union Jack »), grille, niveau électronique, autocollimateur |

## Capabilités de procédés (ordre de grandeur, aluminium)

| Procédé | Planéité sur ~500 mm | Ra |
|---|---|---|
| Fraisage CN standard | 20–50 µm | 0,8–3,2 µm |
| Surfaçage à la fraise à surfacer sur CN de précision, plaque bridée sans contrainte | 10–20 µm | 0,4–1,6 µm |
| Surfaçage diamant mono-pointe (fly-cut) sur machine ultra-précise | 2–5 µm | < 0,1 µm |
| Rectification plane (plateau à dépression, alu) | 5–10 µm | 0,2–0,8 µm |
| Rodage/lapping | 1–3 µm | < 0,2 µm |

Points de vigilance aluminium : préférer une tôle **coulée détensionnée** (ACP 5080R,
MIC-6, ALCA PLUS) car le laminé se voile en libérant ses contraintes quand on retire de
la matière ; usinage symétrique et en passes légères ; laisser reposer 24 h entre
ébauche et finition ; bridage sans contrainte (dépression ou appuis isostatiques) pour la
finition ; pas d'anodisation après finition (risque de déformation et de bouchage des
orifices) sauf essai préalable.

## Modèle de cotation (plaque perforée)

    Face A (supérieure) :  ⏥ 0,006  (zone percée 360×360)
                           ⏥ 0,002 / 100×100
                           Ra 0,4 ; arêtes des orifices vives sans bavure (ISO 13715 : −0,02/0)
    Orifices :  6xxx × Ø0,40 ±0,01  ⌖ Ø0,05 | A | B | C
    Lamages  :  6xxx × Ø2,0 H11 ↧ (e − 1,0) ; ⌖ Ø0,2 | A | B | C
    Appuis   :  plages d'appui ⏥ 0,005, ∥ 0,01 | A
    Générale :  ISO 2768-mK ; matière EN AW-5083 coulée détensionnée

Toujours accompagner la cotation d'un **plan de contrôle** : quoi, avec quel instrument,
quelle incertitude, quel échantillonnage (ex. Ø d'orifice : 1 trou sur 50 au microscope
de mesure + mesure de débit par zones).
