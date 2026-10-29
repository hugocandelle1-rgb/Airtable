# Ventilateurs (veille technique) — enveloppe provisoire 60 m³/h @ ~450 Pa, 12 m³/h @ ~40 Pa

> Date de la veille : 2026-10-29. Les points P-Q marqués « lu » ont été **lus graphiquement** sur la courbe des fiches
> constructeur (PDF téléchargés et rasterisés ; incertitude de lecture ≈ ±5 % de l'échelle). Les valeurs sans URL ou
> marquées « non confirmé » ne sont pas vérifiées. Ne pas figer la référence avant la note de calcul du plenum
> (`params/design.toml` → `[fan] reference = "TBD"`).

## 0. Rappels de dimensionnement (pour lire les tableaux)

- Les orifices : 6000 × Ø0,4 mm → surface totale 7,5·10⁻⁴ m². Loi d'orifice Q = Cd·A·√(2Δp/ρ) : à 400 Pa le jet est à ≈ 25,8 m/s
  → Q ≈ 70 m³/h × Cd (Cd ≈ 0,6–0,8 pour un orifice court, **non confirmé** — à mesurer). À 30 Pa : ≈ 19 m³/h × Cd.
  Le rapport de débit entre point haut et point bas (√(400/30) = 3,65) est cohérent avec l'enveloppe 12 → 60 m³/h. (Calcul propre, pas de source externe.)
- Lois de similitude (ventilateur à vitesse variable) : Q ∝ n, Δp ∝ n². Pour passer de ~450 Pa à ~40 Pa il faut **n_min/n_max ≈ √(40/450) ≈ 0,30**.
  La courbe système de la plaque étant en Δp ∝ Q², tous les points de fonctionnement sont **à iso-rendement** : la vitesse minimale PWM compte plus que la plage de débit.
- Le ventilateur doit donc : (i) donner ≥ 450 Pa à 60 m³/h avec marge ≈ 20 % (pertes du plenum/diffuseur/filtre non incluses), (ii) tenir ≈ 30 % de la vitesse max en régulation stable.

## 1. Tableau comparatif

| # | Référence | Type / dimensions | U nom. / plage | I / P nominal | n max | Débit libre | Δp max | PWM / commande | Bruit | L10 | Prix indicatif |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | **Sanyo Denki San Ace 9BMC24P2G001** | radial, 97 × 95 × 33 mm, 200 g | 24 V / 21,6–26,4 V | 3,1 A / 74,4 W | 8200 min⁻¹ | 1,85 m³/min (111 m³/h) | 1950 Pa | PWM 25 kHz + tachy (4 fils) | 69 dB(A) | 40 000 h @ 60 °C (70 000 h @ 40 °C) | 41–112 USD selon revendeur (agrégateur) |
| B | **ebm-papst RER 120-26/14/2 TDP** | radial à pales arrière, Ø120 × 54 mm, 0,43 kg | 24 V / 16–32 V | 78 W | 6100 min⁻¹ | 377 m³/h | ≈ 580 Pa (lu) | 0-10 V / PWM + tachy (sur agrégateur, non confirmé sur la fiche officielle) | LWA 8,2 B | 55 000 h @ 40 °C ; 35 000 h @ T max | ≈ 103–155 USD |
| C | **ebm-papst G1G108-AB17-02** | radial EC, carter petite bride, 108 mm, 1,4 kg | 24 V / 16–28 V | 2,0 A / 42 W | 3000 min⁻¹ (n nominal) | 200 m³/h | ≈ 410 Pa (U_N, lu) ; ≈ 520 Pa (courbe U_R, lu) | 0-10 V / PWM 1–10 kHz + tachy | non confirmé | non confirmé | non confirmé |
| D | **Micronel U97HL-024KM-4** (×2 en parallèle) | radial miniature, 358 g | 24 V / 15–26 V | 1,6 A libre / 26 W au point de travail | 18 600–20 100 min⁻¹ | 660 l/min (39,6 m³/h) | 2600 Pa | entrée « set speed » analogique 2–4,4 V (ou résistance) + tachy FG ; PWM non confirmé | 73,6 dB(A) @ 1000 Pa | non confirmé | non confirmé |
| E | San Ace 9BMB24P2K01 (**non évalué sur courbe**) | radial 97 × 33 mm | 24 V | 1,62 A / 38,9 W | 6850 min⁻¹ | 1,61 m³/min (96,6 m³/h) | 1280 Pa | PWM 25 kHz + pulse | 66 dB(A) | non confirmé | non confirmé |
| – | ebm-papst RG 160-28/14 N | radial à pales arrière, 220 × 220 × 56 mm | 24 V / 12–28 V | 20 W | 2850 min⁻¹ | 209 m³/h | ≈ 400 Pa (lu, extrapolé) | **pas de PWM** (option signal vitesse seulement) | LWA 6,6 B | 70 000 h @ 40 °C | non confirmé |
| – | ebm-papst RG 125-19/14 N | 180 × 180 × 40 mm | 24 V | 4,9 W | 2550 min⁻¹ | 87,5 m³/h | ≈ 160 Pa (lu) | pas de PWM | LWA 5,8 B | 62 500 h @ 40 °C | non confirmé |
| – | Delta BFB1224H | radial 2 phases | 24 V / 7–27,6 V | 0,35 A / 8,4 W | 2500 min⁻¹ | 0,821 m³/min | 21 mmH₂O ≈ 206 Pa | **pas de PWM** (fil de verrouillage -R00 seulement) | 51 dB(A) | 50 000 h @ 40 °C | non confirmé |

### Sources des données de ce tableau

- A : fiche San Ace B97 9BMC (catalogue C1111B002), https://cdn.components.ru/media/PDF/6729644.pdf ; distributeur https://azcus.digikey.com/en/products/detail/sanyo-denki-america-inc/9BMC24P2G001/7622264 ; prix https://www.edinventory.com/parts/9bmc24p2g001_sanyo-denki (agrégateur ; date/devise non confirmées).
- B : fiche ebm-papst officielle (approuvée 2016-06-22) https://img.ebmpapst.com/products/datasheets/DC-centrifugal-fan-RER12026142TDP-ENU.pdf ; PWM/0-10 V/tachy et « 800 min⁻¹ à 7 % » : agrégateur https://cn.elcodis.com/parts/2125323/RER120-26142TDP.html (**non confirmé** sur ebm-papst) ; prix https://www.electronicsdatasheets.com/manufacturers/ebmpapst/parts/rer120-26-14-2tdp et https://www.avnet.com/americas/product/ebm-papst/rer120-26-14-2tdp/evolve-3664105 (délai annoncé 133 semaines : **vérifier disponibilité**). Variante TDMP (5200 min⁻¹, 51 W, 320 m³/h) : https://img.ebmpapst.com/products/datasheets/DC-centrifugal-fan-RER12026142TDMP-ENU.pdf.
- C : fiche ebm-papst (Web data sheet B) https://media.distrelec.com/Web/Downloads/02/_e/emG1G108AB1702_e.pdf.
- D : https://inelso.ru/upload//specs/U97HL.pdf (version 23.10.2014).
- E et 9BMB24P2G01 : catalogue San Ace B97 9BMB https://datasheet.chipsmall.com/9BMB12F201/137425.pdf.
- RG 160 / RG 125 : https://img.ebmpapst.com/products/datasheets/DC-centrifugal-fan-RG1602814N-ENU.pdf et https://img.ebmpapst.com/products/datasheets/DC-centrifugal-fan-RG1251914N-ENU.pdf.
- Delta BFB1224H : https://www.delta-fan.com/Download/Spec/BFB1224H.pdf (fiche scannée 2005). Delta BFB1012H (12 V, 97 × 94 × 33 mm, 249 Pa, 0,72 m³/min, 3600 min⁻¹, 52 dB(A), **sans PWM**) : https://www.datasheets.com/delta-design/bfb1012h-f00 (page agrégateur ; la fiche constructeur https://www.delta-fan.com/Download/Spec/BFB1012H.pdf existe).

## 2. Points de courbe P-Q lus (≥ 4 points par candidat)

### A. San Ace 9BMC24P2G001 (24 V) — source : p. 499 de https://cdn.components.ru/media/PDF/6729644.pdf

| Débit (m³/h) | PWM 100 % (Δp, Pa) | PWM 60 % (Δp, Pa) | PWM 20 % (Δp, Pa) |
|---|---|---|---|
| 0 | ≈ 1900 | ≈ 890 | ≈ 120 (valeur tabulée de la fiche : 121 Pa) |
| 18 (0,3 m³/min) | ≈ 1790 | ≈ 780 | ≈ 90 |
| 30 (0,5 m³/min) | ≈ 1640 | ≈ 710 | ≈ 55 |
| 60 (1,0 m³/min) | ≈ 1130 | ≈ 405 | — (limite du débit à 20 % : 0,58 m³/min ≈ 35 m³/h) |
| 90 (1,5 m³/min) | ≈ 580 | — | — |
| 111 (1,85 m³/min) | 0 | — (≈ 1,38 m³/min = 83 m³/h) | — |

Points tabulés (texte de la fiche) : 100 % → 8200 min⁻¹, 1,85 m³/min, 1950 Pa, 3,1 A ; **20 % → 2800 min⁻¹, 0,58 m³/min, 121 Pa, 0,19 A, 44 dB(A)**. La courbe vitesse/PWM (lue) montre un coude en pointillé : vitesse nulle jusqu'à ≈ 8–10 % de rapport cyclique puis saut vers ≈ 1500 min⁻¹ (lu, non tabulé).
Note : « les modèles sans spécification à 0 % ont une vitesse nulle à 0 % » (même fiche) → **arrêt à 0 % PWM** ; la fiche ne donne pas le seuil de démarrage exact (non confirmé).

Lecture système : 60 m³/h exige ≈ 450 Pa → rapport cyclique ≈ 70–75 % (entre les courbes 60 % et 100 %, interpolation, non confirmé). Le point bas (12 m³/h, 40 Pa) demande n ≈ 30 % de n_max ≈ 2500 min⁻¹ : la courbe 20 % (2800 min⁻¹) donne encore ≈ 120 Pa à débit nul, donc **il faudra descendre sous 20 %** (zone de la courbe vitesse/PWM où la fiche est silencieuse) ou **étrangler/dissiper** (clapet, ou volume mort) — risque à valider expérimentalement.

### B. ebm-papst RER 120-26/14/2 TDP (24 V) — source : p. 4 de la fiche officielle (courbe pleine vitesse)

| Débit (m³/h) | Δp (Pa) lu |
|---|---|
| 0 | ≈ 580 |
| 60 | ≈ 565 |
| 100 | ≈ 550 |
| 200 | ≈ 445 |
| 300 | ≈ 250 |
| ≈ 380 | 0 |

Zone de fonctionnement recommandée par le constructeur (surface grisée) : entre ≈ 55 m³/h et ≈ 320 m³/h ; **à 60 m³/h on est tout juste à la limite basse de la zone grise** (risque de décrochage/instabilité à haute pression, constructeur). Marge de pression à 60 m³/h : ≈ 565 Pa pour 450 Pa requis (+25 %). Le point bas 12 m³/h est hors zone grise de la courbe à pleine vitesse ; il se situe en zone d'écoulement stable seulement à vitesse réduite (similitude) — non confirmé.

### C. ebm-papst G1G108-AB17-02 — source : p. 5 de https://media.distrelec.com/Web/Downloads/02/_e/emG1G108AB1702_e.pdf

| Débit (m³/h) | courbe noire U_N (Δp, Pa) | courbe rouge U_R (Δp, Pa) |
|---|---|---|
| 0 | ≈ 410 | ≈ 520 |
| 40 | ≈ 380 | ≈ 490 |
| 60 | ≈ 360 | ≈ 465 |
| 80 | ≈ 310 | ≈ 420 |
| ≈ 210 (flux libre) | 0 | ≈ 0 (point 1', ≈ 3230 min⁻¹, 55 W) |

La définition de U_R n'est pas dans le texte extrait ; le tableau de la fiche donne n = 3230–4100 min⁻¹ et P = 55–35 W aux points 1'–4' (rouges). **Marginal** : l'enveloppe 450 Pa à 60 m³/h n'est atteinte que sur la courbe rouge (≈ 465 Pa, marge ≈ 3 %). Commande : « ≈ 10 % PWM → n = min ; < 10 % → n = 0 ; ≈ 1 V → n = min ; < 1 V → n = 0 » (même fiche, p. 4) → **la vitesse minimale n'est PAS 0 : un plancher ≈ 10 % PWM, vitesse mini non chiffrée** (non confirmé).

### D. Micronel U97HL-024KM-4 — courbe 24 V, source : https://inelso.ru/upload//specs/U97HL.pdf

| Débit (l/min) | (m³/h) | Δp 24 V (Pa) lu |
|---|---|---|
| 0 | 0 | ≈ 2560 |
| 200 | 12 | ≈ 2230 |
| 300 | 18 | ≈ 1950 |
| 400 | 24 | ≈ 1400 |
| 500 | 30 | ≈ 880 |
| 600 | 36 | ≈ 410 |
| 660 | 39,6 | 0 |

Deux ventilateurs en parallèle donnent, à 450 Pa total, ≈ 2 × 35 m³/h = 70 m³/h (lu sur la courbe 24 V : ≈ 590 l/min à 450 Pa). Mais le débit max d'un seul est 40 m³/h : **1 seul ne suffit pas** ; la pression excédentaire (2500 Pa) est inutile (régime très élevé 19 000 min⁻¹, bruit 73,6 dB(A), durée de vie non confirmée). Commande : tension 0,5–2 V démarrage non garanti, 2–4,4 V proportionnel, > 4,4 V vitesse max (fiche) ; **pas de PWM natif confirmé**.

### E. Autres lectures (courbes San Ace 9BMB24P2G01, 24 V, 100 % — p. 403 du catalogue)

| Débit (m³/h) | Δp (Pa) lu |
|---|---|
| 0 | ≈ 755 |
| 24 | ≈ 675 |
| 36 | ≈ 580 |
| 48 | ≈ 430 |
| 60 | ≈ 290 |
| 72 | ≈ 135 |
| 80 (1,34 m³/min) | 0 |

→ 9BMB24P2G01 (760 Pa libre) **insuffisant** : ≈ 290 Pa à 60 m³/h. Source : https://datasheet.chipsmall.com/9BMB12F201/137425.pdf. À 50 % PWM, courbe lue : ≈ 300 Pa à 0 m³/h, ≈ 0,9 m³/min à Δp = 0 (même source).

### F. ebm-papst RG 160-28/14 N et RG 125-19/14 N (lecture)

- RG 160 (24 V, courbe à pleine vitesse, fiche p. 4) : ≈ 400 Pa @ 4 m³/h ; ≈ 315 Pa @ 50 m³/h ; ≈ 224 Pa @ 100 m³/h ; ≈ 132 Pa @ 150 m³/h ; ≈ 40 Pa @ 200 m³/h. → ≈ 295 Pa à 60 m³/h : **insuffisant seul** (≥ 2 en série requis, complexe).
- RG 125 : ≈ 165 Pa @ 0 ; ≈ 130 Pa @ 20 m³/h ; ≈ 100 Pa @ 40 m³/h ; ≈ 55 Pa @ 70 m³/h ; 0 @ ≈ 87 m³/h → **rejeté**.

## 3. Classement pour l'enveloppe (60 m³/h sous ≈ 450 Pa, 12 m³/h sous ≈ 40 Pa)

| Rang | Candidat | Pourquoi | Contraintes |
|---|---|---|---|
| **1** | **San Ace 9BMC24P2G001** (×1) | Marge de pression confortable (≈ 1130 Pa @ 60 m³/h à 100 %), PWM 25 kHz + tachy standard, compact (97 × 95 × 33 mm, 200 g), 24 V, fiche constructeur complète avec courbes à plusieurs duty. | Fonctionne à ≈ 70–75 % PWM au point haut (rendement non optimal, bruit de 60–69 dB(A)). Point bas 40 Pa : à ≈ 20 % PWM il fait encore ≈ 120 Pa à Q = 0 (fiche) ⇒ la limite basse est **la vitesse minimale PWM** (non tabulée, ≈ 8–10 % lu sur la courbe) ; arrêt à 0 % ; 4 fils. L10 = 40 000 h @ 60 °C seulement. Disponibilité : délai 16 semaines annoncé chez DigiKey (https://azcus.digikey.com/en/products/detail/sanyo-denki-america-inc/9BMC24P2G001/7622264). |
| **2** | **ebm-papst RER 120-26/14/2 TDP** (×1) | 565 Pa @ 60 m³/h à pleine vitesse (+25 % de marge), moteur 3 phases très régulier, roue à pales arrière, L10 55 000 h @ 40 °C ; 120 mm, 24 V, tachy + commande. | Plage grise recommandée commence à ≈ 55 m³/h : au point haut on est en bord de zone instable ; minimum de vitesse « ≈ 800 min⁻¹ @ 7 % PWM, arrêt à 0 % » **uniquement sur un agrégateur** (https://cn.elcodis.com/parts/2125323/RER120-26142TDP.html) ; courbe Δp@12 m³/h/40 Pa à vitesse réduite à vérifier (n/n_max ≈ 0,30 ⇒ ≈ 1800 min⁻¹ soit ≈ 30 % PWM si linéaire). Prix 100–155 USD, délai 133 semaines chez Avnet (stock distributeur à vérifier). Bruit 8,2 B (LWA). |
| **3** | **ebm-papst G1G108-AB17-02** (×1, ou ×2 en parallèle) | EC, 0-10 V / PWM 1–10 kHz + tachy, très bonne efficacité. | À 450 Pa/60 m³/h on est sur la courbe haute (≈ 3230–4100 min⁻¹) à 3 % de marge seulement ; en parallèle ×2 chaque machine ne débite que 30 m³/h à 450 Pa (≈ 360–465 Pa lus) : **faisable mais à vérifier** ; 1,4 kg, 42 W ; plancher PWM ≈ 10 % (vitesse non chiffrée). |
| 4 | Micronel U97HL-024KM-4 ×2 en parallèle | 2 × 40 m³/h libre, très haute pression (excédent inutile), très compact. | Vitesse 19 000 min⁻¹, bruit 73,6 dB(A), **pas de PWM natif confirmé**, durée de vie non confirmée, deux machines à synchroniser ; courbe système plate à la tension minimale (15 V : ≈ 1000 Pa max, 410 l/min libre). |
| 5 | San Ace 9BMB24P2K01 | 1280 Pa, 96,6 m³/h libre, PWM 25 kHz | **Non évalué sur la courbe** (non lue). Alternative 3e génération 9BMC. |

Éliminés (pression insuffisante pour 450 Pa) : Delta BFB1224H (≈ 206 Pa), Delta BFB1012H (≈ 249 Pa, 12 V, **sans PWM**), ebm-papst RG 125 (≈ 165 Pa), RG 160 (≈ 295 Pa à 60 m³/h), San Ace 9BMB24P2G01 (≈ 290 Pa à 60 m³/h).

Non traités (fiche non trouvée dans le temps imparti) : séries ebm-papst RV, RLF ; Delta PFR/GFB ; Sunon et Nidec (une recherche donne des blowers 97 × 94 × 33 mm à ≈ 107 Pa seulement, https://www.cuidevices.com/product/thermal-management/dc-fans/centrifugal-blowers/CBM-979433S-230-507-22, non confirmé) ; San Ace 9TD ; axiaux haute pression San Ace 9HV (la fiche trouvée est en **48 V**, 1050 Pa, 7,2 m³/min = 432 m³/h, 10 000 min⁻¹, 72 dB(A) : https://products.sanyodenki.com/en/sanace/dc/dc-fan/9HV1248P1H001/ — trop de débit pour 60 m³/h, point de fonctionnement en zone de décrochage). **Ne pas utiliser d'axial** : le débit requis est dans la zone de décrochage de ces machines.

## 4. Contraintes de commande à garder en tête pour le firmware

1. **0 % PWM = arrêt** (9BMC : fiche, « zero fan speed at 0 % » ; G1G108 : < 10 % = arrêt). Ne pas compter sur 0 % pour une vitesse minimale.
2. **Vitesse minimale** : plancher de l'ordre de 8–10 % de rapport cyclique, avec un saut de vitesse (coude en pointillé sur la courbe 9BMC). La boucle de pression doit tolérer cette marche (hystérésis, pas de régulation continue sous le seuil).
3. Fréquence PWM : 25 kHz (San Ace, conforme `pwm_freq_Hz = 25000` de `params/design.toml`) ; ebm-papst G1G108 : 1–10 kHz (donc **pas 25 kHz**), RER 120 TDP : non confirmé sur la fiche officielle.
4. Tachymètre : San Ace « pulse sensor » (nombre d'impulsions/tour **non confirmé**), Micronel FG = 3 impulsions/tour (f×20 = min⁻¹, fiche U97HL), ebm-papst G1G108 « tacho output » (non confirmé nb impulsions).
5. Alimentation : pic de courant (9BMC24 : 3,1 A à 100 %, 74 W), condensateur de découplage ; Delta recommande > 4,7 µF pour parallèles (https://www.delta-fan.com/Download/Spec/BFB1224H.pdf, note 13).
6. Bruit aéraulique et pulsations : un ventilateur radial à 8200 min⁻¹ (9BMC) génère un son à 137 Hz × pales ; le plenum et le diffuseur devront filtrer (voir `docs/00_cahier_des_charges.md` § 4 : pas de jet résiduel sous la plaque).
7. Régulation de la pression du plenum (30 → 400 Pa, ± 0,3 Pa) : la régulation fine devra utiliser un **actionneur auxiliaire** (clapet motorisé de fuite ou ventilateur de trim) car le PWM du ventilateur principal est discret et bruité — à discuter dans la note de calcul.

## 5. Questions ouvertes

- Courbe vitesse/PWM détaillée du RER 120 TDP et du G1G108 (non trouvée ; demander à ebm-papst).
- Cd réel des orifices Ø0,4 mm × 1 mm : à mesurer sur un coupon, il détermine le point de fonctionnement exact.
- Perte de charge du filtre ISO 16890 ePM10 50 % (`[plenum] filter`) et du diffuseur : non incluses dans les 450 Pa.
