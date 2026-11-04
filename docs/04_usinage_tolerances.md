# 04 — Usinage, tolérances et contrôle de la plaque perforée

> Lot structure. Calculs : `calc/structure/machining.py` (tolérances, temps de perçage,
> budget), `calc/structure/support_study.py` (finition sur appuis de service).
> Résultats : `calc/structure/results/machining_budget.json`. Méthode : skill
> `tolerancement-iso-gps` (effet fonctionnel → allocation → tolérance → procédé capable
> → cotation → plan de contrôle). Valeurs proposées dans
> `calc/structure/results/recommended_params.toml` ; **`params/design.toml` n'est pas modifié**.

## 1. Effet fonctionnel : tout défaut de forme est une pente

Un palet sur un plan incliné de θ accélère de g·θ. Seule compte la pente **après retrait
du plan moyen**, puisque le nivellement rattrape le plan. Le palet Ø30 mm moyenne les
défauts courts : sur un disque, une ondulation de longueur d'onde λ est atténuée du
facteur 2·J1(x)/x, avec x = π·30/λ.

| Défaut (zone percée 360, pente évaluée sur la zone de travail 300) | Pente crête |
|---|---|
| Forme cylindrique (pire cas), flèche δ = 2 / 3 / 4 / 6 / 10 / 15 / 20 µm | 19 / 28 / 37 / **56** / 93 / 139 / 185 µrad |
| Bombé sphérique, même δ | pente cylindrique × 0,71 |
| Ondulation de 1 µm crête à crête, λ = 30 / 50 / 100 / 150 mm | 35 / 50 / 26 / 19 µrad (filtre du palet inclus) |

Formules : forme cylindrique w = δ·(x/a)², d'où θ = 2δ·s/a² (a = 180 mm, s = 150 mm).
Ondulation : θ = π·PV/λ × filtre.

### Constat : le cahier des charges est incohérent sur ce poste

Le CdC alloue **30 µrad** à la planéité d'usinage, mais il la traduit par « ⏥ 6 µm sur la
zone percée et 2 µm sur 100 × 100 ». Or :

- 6 µm de forme cylindrique donnent **56 µrad** à eux seuls, soit plus que le budget total
  de 50 µrad ;
- 2 µm sur 100 mm (λ ≈ 100 mm) donnent encore 56 µrad.

Pour tenir 30 µrad (dont 85 % pour la forme), il faut **⏥ 2,8 µm sur 360 × 360** et environ
**0,5–1 µm par carré de 100 × 100**. C'est le niveau d'une plaque de contrôle DIN 876
classe 00, atteignable seulement en surfaçage diamant mono-pointe sur machine
ultra-précise, ou en rodage.

**Proposition :** prendre comme critère de réception la **pente locale mesurée** :
au niveau électronique, base 50 mm, après retrait du plan, ≤ 30 µrad crête sur la zone
300 × 300. Garder ⏥ 0,003 / 0,001 par 100 × 100 comme spécification géométrique
associée. La compensation logicielle étant exclue (décision du 2026-11-03), un prestataire
qui ne garantit que 6 µm **ne convient pas**. Les exigences de planéité par niveau d'erreur
admissible θ sont au § 6.

## 2. Procédés et capabilité

| Procédé | Planéité sur ~500 mm (alu) | Compatible orifices Ø0,3–0,4 ? | Compatible « finition sur appuis de service » ? | Usage |
|---|---|---|---|---|
| Fraisage CN standard | 20–50 µm | oui | oui | ébauche |
| Surfaçage à la fraise (plaquettes PCD) sur CN de précision, montage 3 appuis | 10–20 µm | oui (pas d'abrasif) | **oui** | semi-finition seulement (variante économique non applicable) |
| Rectification plane (plateau à dépression) | 5–10 µm | risque de grains dans les orifices | non (plateau ≠ appuis) | non retenu |
| **Surfaçage diamant mono-pointe (fly-cut), machine ultra-précise** | **2–5 µm** | **oui** (efforts < 5 N, brouillard) | **oui** | **référence** |
| Rodage | 1–3 µm | non (abrasif dans 6 000–17 000 orifices) | non (face retournée sur le rodoir) | exclu |

**Effort de coupe :** sur ses 3 appuis, la plaque de 35 mm fléchit de **0,06 µm/N** au pire
point (0,10 µm/N pour 30 mm). Un fly-cut à 2–5 N donne donc ≤ 0,3 µm d'erreur
d'enlèvement : c'est acceptable en finition, avec une passe de 20 µm à vitesse constante.

## 3. Gamme d'usinage (référence)

| Phase | Opération | Points clés |
|---|---|---|
| 00 | Brut ACP 5080 (fraisé deux faces), 40 mm, découpé à 530 × 530 | coulée détensionnée ; certificat matière |
| 10 | Contournage à 520 × 520, chanfreins 1 × 45° | — |
| 20 | Ébauche **symétrique** des deux faces (−2 mm par face), puis épaisseur 35,5 | passes légères alternées |
| 30 | Repos 24 h. En option : 3 cycles 20 → 60 → 20 °C | ne pas dépasser 65 °C (5083 : sensibilisation) |
| 40 | Semi-finition de la face inférieure (⏥ 0,02). Alésages de pions (datums B, C), 3 sièges de billes, taraudages du caisson et des embases, trous de manutention | voir § 7 pour les cotes |
| 50 | Semi-finition de la face supérieure : épaisseur 35,25 (surépaisseur de finition 0,25) | référence de profondeur du voile |
| 60 | **Orifices** Ø0,30 ±0,005 depuis la face supérieure, borgnes, profondeur 1,75 mm (5,8×D) | carbure neuf, 24 000 tr/min, 3 débourrages ; changement tous les 1 500 trous ; contrôle 1 trou sur 50 |
| 70 | **Lamages** Ø2,0 depuis la face inférieure, foret 118°. Sommet du cône à 1,45 mm de la face supérieure semi-finie | avant-trou 2×D puis foret long carbure à lubrification centrale (≥ 20×D). Le cône recoupe proprement le fond des orifices borgnes : entrée conique, pas de bavure de sortie (gain de débit +5,9 % selon le lot aéro) |
| 80 | Nettoyage : soufflage inverse, bain à ultrasons, contrôle de débit par zones, endoscope par échantillonnage | aucun abrasif |
| 90 | Stabilisation 48 h à 20 ± 1 °C | — |
| 100 | **Finition de la face supérieure sur appuis de service** : plaque **avec son caisson monté** (ou un lest de 10 kg ±5 % réparti sur la ligne d'attache) posée sur 3 vés identiques aux vés de service (positions ±0,5 mm), sur rehausses de 300 mm. Fly-cut diamant : passes de 0,15 puis 0,02 mm. Plenum soufflé à 20–50 Pa pendant la coupe (les jets chassent les copeaux des orifices) | atelier à 20 ± 0,5 °C, plaque thermostatée 12 h avant. Voile final 1,20 ± 0,05 |
| 110 | Contrôle (§ 5) puis protection | **pas d'anodisation** |

**Pourquoi finir sur les appuis :** la flèche de poids propre (15,5 µrad sur le schéma
retenu, 26 µrad avec les appuis au coin) est alors **usinée en négatif**. Il ne reste que :

- les écarts de position des appuis (±0,5 mm → 0,20 µrad) ;
- le lest (±5 % → 0,2 µrad) ;
- le frottement aux appuis (≤ 1,65 µrad).

Si le caisson est absent à la finition sans lest de remplacement, l'erreur est de
**3,3 µrad** (35 mm).

## 4. Temps machine du perçage (centre d'usinage 24 000 tr/min, 90 €/h)

| Perçage | Trous (zone 360) | s/trou (lamage + orifice) | Lubrification centrale | Avec débourrages |
|---|---|---|---|---|
| **hex 5,00 / Ø0,30 (retenu)** | **5 935** | 5,6 + 1,8 | **20 h ≈ 2,4 k€** | 31 h ≈ 3,4 k€ |
| hex 4,82 / Ø0,30 | 6 333 | 5,6 + 1,8 | 21 h ≈ 2,7 k€ | 33 h ≈ 3,7 k€ |
| hex 4,23 / Ø0,30 | 8 197 | 5,6 + 1,8 | 26 h ≈ 3,3 k€ | 42 h ≈ 4,6 k€ |
| hex 2,94 / Ø0,30 | 17 131 | 5,6 + 1,8 | **51 h ≈ 6,2 k€** | 83 h ≈ 9,1 k€ |

Hypothèses :

- lamage : vc 120 m/min, f 0,04 mm/tr ;
- orifice : f = 0,0125·d mm/tr ;
- 0,3 s de positionnement par trou et par opération ;
- changement des forets tous les 1 500 trous ;
- 2 mises en position de 2 h.

Ce sont des ordres de grandeur d'atelier, à confirmer par devis. Au pas 2,94, le ligament
entre lamages Ø2 n'est que de 0,94 mm sur 34 mm de profondeur. Une dérive de foret de
±0,1 mm le réduit à 0,74 mm : c'est faisable, mais il faut le vérifier sur une éprouvette.
Le lamage Ø1,5 (ligament 1,44 mm) est plus sûr mais demande un foret de 23×D.

## 5. Plan de contrôle

| Caractéristique | Instrument | Incertitude visée | Échantillonnage |
|---|---|---|---|
| Pente locale (critère principal), zone 300 | niveau électronique 2 axes (Wyler/Leica, prêt ou labo), base 50 mm, grille 50 mm + Union Jack | ≤ 2 µrad | 100 % de la grille, 2 sens |
| ⏥ zone percée, ⏥ par 100 × 100 | reconstruction depuis les pentes (méthode de Moody) ou MMT sur palier d'air | ≤ 0,7 µm | 100 % |
| Ø des orifices (±0,005) | microscope de mesure / jauge de débit | ±1 µm | 1 sur 50 + débit par zones de 50 × 50 |
| Voile (longueur d'orifice) | endoscope ou coupe sur éprouvette ; palpeur sur la face inférieure | ±0,02 mm | 1 sur 200 |
| Bavures de sortie (face supérieure) | binoculaire ×20 | — | 1 sur 50, 100 % après finition |
| Position des sièges de billes | MMT | ±0,02 mm | 100 % |
| Validation fonctionnelle | **dérive de palets** (carte de pente, recette seulement) | ≈ 2–5 µrad | grille de 10 mm |

## 6. Exigences de planéité par niveau d'erreur admissible (budget de force parasite)

Calcul : `calc/structure/passive_budget.py` (`00_cahier_des_charges.md` § 3). θ = a_par/g
est l'accélération parasite admissible en pente équivalente. Elle comprend tous les
postes : structure, crantage, orifices, balourd, courants d'air.

| θ (µrad) | Part allouée à la planéité | ⏥ zone percée | ⏥ / 100 × 100 | Procédé capable | Prestataires plausibles (non contactés) | Faisabilité |
|---|---|---|---|---|---|---|
| 5 / 10 | — | — | — | — | — | **non réalisable** : la somme quadratique des planchers vaut 10,1 µrad (planéité 0,5 µm, crantage corrigé, orifices ±2 µm, balourd 2 µm) |
| 20 | 11,6 µrad | **1,1 µm** | 0,21 µm | tournage diamant optique + passes de correction sur carte mesurée. Polissage exclu (abrasif dans les orifices, arrondi des arêtes) | grands opticiens (Safran Reosc, Winlight, Fraunhofer IOF) | à la limite, coût relatif ≈ 9 ; correction du crantage requise |
| 30 | 17,6 µrad | **1,6 µm** | 0,31 µm | tournage / fly-cut diamant mono-pointe sur machine ultra-précise, sur appuis de service | ateliers d'optique métallique (Fraunhofer IOF/IPT, fabricants de miroirs aluminium) | réalisable, coût relatif ≈ 3 ; correction du crantage requise |
| 50 | 30,5 µrad | **2,8 µm** | 0,54 µm | fly-cut diamant de précision sur appuis de service (gamme du § 3) | ateliers de surfaçage de précision | **réalisable avec la conception actuelle**, coût relatif ≈ 1,3 |

La cotation du § 7 reste celle de la référence : ⏥ 0,003 et 0,001 par 100 × 100,
cohérente avec θ = 50. Pour θ = 30, il faut ⏥ 0,0016 / 0,0003 par 100 × 100, et un
contrôle interférométrique ou déflectométrique (incertitude ≤ 0,2 µm).

## 6 bis. Variante économique — NON APPLICABLE (pour mémoire)

Elle supposait une carte de pente compensée par le contrôle des robots. Cette
compensation a été exclue par l'utilisateur le 2026-11-03. La table caractérise des
actionneurs : les palets ne sont pas pilotés dans le plan. Les chiffres ci-dessous sont
conservés pour l'historique.

- **Procédé :** surfaçage à la fraise PCD Ø100 sur centre d'usinage de précision, plaque
  sur un montage 3 appuis aux positions de service, bridée seulement au droit des appuis
  (le poids propre reste usiné). Ra 0,4–0,8.
- **Pente prévue avant compensation :**
  - 15 µm : 139 µrad (forme) + 66 µrad (traces de passes, 2 µm crête à crête à
    λ = 80 mm) ≈ **205 µrad crête** ;
  - 20 µm : ≈ **251 µrad**.
- **Cartographie et compensation :** la carte statique est relevée par dérive des palets
  (grille de 10 mm) puis compensée par le contrôle des robots. Il reste la part non
  répétable (thermique, pression, frottement, inclinaison) et l'incertitude de la carte
  (10 µrad estimés), soit **≈ 12 µrad** (`machining_budget.json`). C'est en dessous de
  50 µrad, mais seulement si la carte reste stable : il faut la recaler (retournement des
  ADXL355, palets témoins) après chaque démontage.
- Si la plaque est surfacée bridée à plat sur la table de la machine au lieu du montage
  3 appuis, la flèche de poids propre (+16 µrad) s'ajoute à la carte (elle aussi
  compensable).
- **Gain :** pas de rectification ni de prestataire « 3 µm » (risque n° 1 levé) ;
  finition ≈ 2 h de CN au lieu d'un fly-cut ultra-précis.

## 7. Données pour la CAO

Repère : origine au centre de la plaque, x vers la droite, y vers l'arrière, z vers le
haut, z = 0 sur la face inférieure. Cotes en mm.

| Élément | Cotes |
|---|---|
| Plaque | 520 × 520 × **35** ; chanfreins 1 × 45° ; EN AW-5083 coulée |
| Zone percée | carré 360 × 360 centré ; réseau hexagonal, rangées selon x, origine au centre ; **pas 5,00** (5 935 trous à ≥ 1 mm du bord de zone ; le lot aéro annonce ≈ 6 000 : décompte de référence dans `docs/02_aeraulique.md` / CAO) |
| Orifice | **Ø0,30 ±0,005**, depuis la face supérieure, longueur fonctionnelle (voile) **1,20 ±0,05** |
| Lamage | Ø2,0 H11 depuis z = 0, foret 118°, sommet du cône à z = **33,80** (voile 1,20) |
| Datums | A = face supérieure (zone 300 × 300) ; B = alésage Ø6 H7 débouchant en (−240 ; 0) ; C = lumière 6 H7 × 10 en (+240 ; 0), grand axe selon x |
| Sièges des billes (face inférieure) | 3 logements Ø25,4 H8 prof. 10,7 pour billes Ø25,4 G10 collées (centre de bille 2,0 mm sous la face inférieure ; bord du logement à 4,8 mm du chant), aux points (0 ; +242,5), (+242,5 ; −145,5), (−242,5 ; −145,5) ; ⌖ Ø0,2 \| B \| C |
| Attache du caisson (face inférieure) | parois 6 mm du caisson entre demi-côtés 215 et 221 (axe 218) appuyées sur un joint plat EPDM 6 × 2 (pas de gorge dans la plaque) ; cornière intérieure 15 × 15 × 3 ; 32 × M5 prof. 10 taraudés de bas en haut sur le carré de demi-côté **208** (8 par côté, pas 52, symétriques) |
| Embases ADXL355 (face supérieure) | 4 × (3 × M4 prof. 8 sur Ø40 à 120°, un trou vers l'extérieur) centrées en (±220 ; ±220) ; zone sans perçage |
| Butées anti-soulèvement | pas de précharge (poids 108–130 N par appui) ; 3 brides sur le cadre, jeu 0,5 mm au-dessus de la face supérieure, au droit des appuis (bande pleine, hors zone percée) |
| Manutention | 4 × M10 prof. 20 sur les chants, au milieu de chaque côté |
| Générale | ISO 2768-mK ; état de surface face A Ra ≤ 0,4 (diamant < 0,1) ; face inférieure Ra 1,6 |
| Cotation face A (référence) | ⏥ 0,003 (360 × 360) ; ⏥ 0,001 / 100 × 100 ; pente locale (base 50) ≤ 30 µrad ; arêtes des orifices vives, sans bavure (ISO 13715 : −0,02/0) |
| Cotation face A (économique) | non applicable (pour mémoire : ⏥ 0,020 ; ⏥ 0,005 / 100 × 100) |
| Orifices | ⌖ Ø0,05 \| A \| B \| C ; lamages ⌖ Ø0,2 \| A \| B \| C |

## Historique

- 2026-11-03 : création (perçage recalé sur la configuration aéro retenue : hex 5,00, Ø0,30 ±0,005, voile 1,20). Gamme de finition sur appuis de service, incohérence 6 µm ↔ 30 µrad
  signalée, temps de perçage pour 6 000 et 17 000 trous, variante économique chiffrée.
- 2026-11-04 : variante économique déclarée non applicable (pas de compensation) ;
  exigences de planéité par niveau θ = a_par/g (§ 6).
