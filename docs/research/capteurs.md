# Capteurs (veille technique) — pression, débit, inclinaison, déformation, température, vitesse

> Date : 2026-10-29. Chaque valeur chiffrée porte son URL. « non confirmé » = non vérifié dans une fiche constructeur.
> Conversions utilisées : 1 mrad = 1000 µrad ; 1° = 17 453 µrad ; 1 arcsec = 4,848 µrad ; 1 mm/m = 1000 µrad ; 0,001° = 17,45 µrad.
> Objectif de conception (`docs/00_cahier_des_charges.md`) : résolution de réglage ≤ 2 µrad par axe, inclinaison résiduelle ≤ 5 µrad, dérive ≤ 5 µrad/h, pression régulée à ±0,3 Pa, déformation de plaque ≤ 1,5 µm.

## a) Pression différentielle basse (plenum 30 → 400 Pa ; buse de débit ≈ 5–110 Pa)

| Capteur | Étendue | Résolution | Précision / zéro | Stabilité de zéro | Interface / adresse I²C | Prix indicatif | Source |
|---|---|---|---|---|---|---|---|
| **Sensirion SDP810-125Pa** (SDP800 = version manifold) | ±125 Pa | 16 bit | zéro 0,08 Pa ; span 3 % de la lecture ; répétabilité zéro 0,04 Pa, span 0,5 % lecture ; dérive span < 0,5 %/10 °C | offset < 0,05 Pa/an | I²C ; **0x25** (SDP810/800), 0x26 pour les variantes SDP811/801 | ≈ 22–35 USD (agrégateur : https://www.edinventory.com/parts/sdp810-125pa_sensirion ; date non confirmée) | https://cdn.components.ru/media/PDF/8071819.pdf (datasheet v1.1, avril 2019) |
| **Sensirion SDP810-500Pa** | ±500 Pa | 16 bit | zéro 0,1 Pa ; span 3 % lecture (**≈ 12 Pa à 400 Pa**) ; répétabilité zéro 0,05 Pa ; span 0,5 % lecture (**≈ 2 Pa à 400 Pa**) | < 0,05 Pa/an | I²C 0x25 | non confirmé | même datasheet |
| **Sensirion SDP31 (±500 Pa) / SDP32 (±125 Pa)** | ±500 / ±125 Pa | 16 bit | zéro 0,1 / 0,08 Pa ; span 3 % lecture ; répétabilité zéro 0,03 / 0,025 Pa ; span 0,5 % | **< 0,01 Pa/an** | I²C ; adresse par résistance sur broche ADDR : **0x21 (GND), 0x22 (1,2 kΩ), 0x23 (2,7 kΩ)** → 3 capteurs/bus sans multiplexeur | SDP33 (1500 Pa) ≈ 26–30 USD (agrégateur : https://www.findchips.com/search/SDP33) | https://cdn.sparkfun.com/assets/0/e/9/e/9/SDP31_datasheet.pdf (version déc. 2017) |
| Sensirion SDP33 | ±1500 Pa | 16 bit | « lowest detectable < 0,06 Pa » (page produit) | non confirmé | I²C | idem | https://sensirion.com/products/catalog/SDP32 (page ; chiffres SDP31 < 0,02 Pa, SDP32 < 0,01 Pa) |
| **All Sensors DLHR-F50D / L01D / L02D / L05D** | ±125 / ±250 / ±500 / ±1250 Pa | 16/17/18 bit (≥ 15,7 / 16,7 / 17,7 bit sans code manquant) | total error band : F50D ±0,35 % typ (±1,5 % max) ; L01 ±0,25 % (±1 %) ; L02 ±0,25 % (±0,75 %) ; L05 ±0,20 % (±0,75 %) FSS | **dérive d'offset 1 an : ±0,25 % FSS (F50/L01/L02)** soit ±0,6 Pa pour L01D ; décalage thermique d'offset ±0,5 % FSS | I²C ou SPI ; **adresse fixe 41 déc. = 0x29** → multiplexeur nécessaire | non confirmé | https://allsensors.com/hubfs/Product-Data-Sheets/DS-0350.pdf (Rev C) |
| Superior Sensor ND130 / ND160 | ND130-SM02-R : 0,5–7,5 kPa (donc > 400 Pa) | 16 bit (page revendeur) | ±0,15 % (page revendeur) | non confirmé | I²C ou SPI | non confirmé | https://www.digikey.at/en/products/detail/superior-sensor-technology-inc/ND130-SM02-R/13682321 (revendeur ; **aucune variante ≤ 500 Pa confirmée**) |
| Honeywell TruStability HSC/SSC | ±1,6 mbar … ±10 bar | 12 bit (revendeur, non confirmé) | TEB ±1,5 % FSS (SSC, guide de gamme) | non confirmé | I²C/SPI | non confirmé | https://www.tti.com/content/dam/tti-commons/supplier/honeywell/doc/honeywell-board-mount-pressure-sensors-line-guide-ap.pdf |
| Sensirion SDP610 | non confirmé | non confirmé | non confirmé | non confirmé | non confirmé | non confirmé | non traité |

**Lecture pour la conception**
1. Le plenum monte à **400 Pa** : un SDP810-125Pa/SDP32 est **hors étendue** ; il faut **SDP810-500Pa / SDP31** (ou DLHR-L02D/L05D) pour le plenum. Les capteurs ±125 Pa conviennent au Δp de la buse de débit et aux points bas.
2. L'erreur de **span 3 % de la lecture** des SDP (≈ 12 Pa à 400 Pa) est grande devant les 0,3 Pa de stabilité demandés : la répétabilité (0,5 % ≈ 2 Pa à 400 Pa) l'est aussi. **Un étalonnage in situ** (manomètre de référence) et/ou une régulation sur un critère **relatif** (consigne de vitesse/PWM mémorisée) est nécessaire — l'exigence « 0,3 Pa » ne pourra pas être garantie en absolu par ces capteurs seuls (calcul propre à partir des datasheets).
3. **Zéro** : l'offset du SDP3x est le plus stable (< 0,01 Pa/an) ; les DLHR dérivent de ±0,25 % FSS/an (≈ ±0,6 Pa/an sur 250 Pa). Prévoir une **mesure de zéro périodique** (vanne trois voies ou prises ouvertes à l'arrêt).
4. **Multiplexage** : SDP3x = 3 adresses (0x21–0x23) ; SDP8xx = 1 adresse par variante (0x25, 0x26) ; DLHR = 0x29 fixe (multiplexeur type TCA9548A recommandé, **non confirmé**).
5. Compensation thermique / pression absolue : modes « mass-flow » ou « differential pressure » sélectionnables (commandes 0x3603/0x3608/0x3615/0x361E sur SDP8xx, datasheet SDP8xx ci-dessus).

## b) Débit

### b1. Capteurs de débit massique (Sensirion) — attention à la plage

| Capteur | Plage | Précision | Zéro / bruit | Résolution | I²C | Perte de charge | Source |
|---|---|---|---|---|---|---|---|
| **SFM3019** | −10 … +240 slm (**= 14,4 m³/h**) | ±2 % lecture typ. (±3 % max) sur 0…240 slm ; ±3 % typ. sur −10…0 | zéro 0,05 slm typ. (0,1 max) ; bruit zéro 0,1 slm | 16 bit | **0x2E** | < 80 Pa @ 60 slm ; < 500 Pa @ 200 slm | https://sensirion.com/media/documents/527C8187/66BDAB69/GF_DS_SFM3019.pdf (page produit : https://sensirion.com/products/catalog/SFM3019) |
| SFM3300-D (NRND, successeur SFM3304-D) | −250 … +250 slm (15 m³/h) | ±3 % lecture typ. | non confirmé | non confirmé | non confirmé | non confirmé | https://sensirion.com/products/catalog/SFM3300-D |
| SFM4300 | 20 ou 50 slm (1,2 ou 3 m³/h) | ±2 % lecture (revendeur) | non confirmé | non confirmé | non confirmé | non confirmé | https://www.digikey.co.uk/en/product-highlight/s/sensirion/sfm4300-flow-sensor |
| SFM3000 | non confirmé (fiche non trouvée : l'URL d'essai a renvoyé 404) | non confirmé | non confirmé | non confirmé | non confirmé | non confirmé | non traité |

⇒ **60 m³/h = 1000 slm** est **hors plage** de tous ces capteurs. Option : **montage en dérivation (shunt laminaire, rapport de division connu)**, avec les incertitudes de rapport ; ou, pour le point bas (12 m³/h = 200 slm), le SFM3019 mesure directement avec ≈ 500 Pa de perte de charge (inacceptable sur l'aspiration d'un point à 40 Pa). **Conclusion : privilégier la buse normalisée (§ b2) avec Δp SDP.**
Les anémomètres thermiques à fil chaud n'ont pas été évalués (non confirmé).

### b2. Méthode « buse d'entrée / venturi » — formules

Relation de base (ISO 5167, forme conservée même pour une buse d'entrée) :

Q_v = C · ε · A_t · √(2·Δp/ρ) / √(1 − β⁴), avec A_t = π d²/4, β = d/D, ρ = 1,204 kg/m³ (valeurs de `params/design.toml`).

- **Buse ISA 1932 (ISO 5167-3)** : C = 0,9900 − 0,2262 β^4,1 − [0,00175 β² − 0,0033 β^4,15]·(10⁶/Re_D)^1,15 — formule telle que reproduite par https://lmnoeng.com/nozzles.php (source secondaire ; **vérifier dans la norme**). Validité ISO 5167-3 : Re_D ≥ 10⁴ (≈ 7·10⁴ selon l'édition, non confirmé), **diamètre de conduite D ≥ 50 mm** (https://iteh.es/catalog/standards/iso/f54eaa2f-0665-4436-870c-35cd6ce0f5e9/iso-5167-3-2022 et page LMNO ci-dessus). Une buse montée sur une aspiration en Ø30–40 mm est **hors domaine d'application** de la norme.
- **Tuyère venturi (ISO 5167-3 / venturi-nozzle)** : C = 0,9858 − 0,196 β^4,5, valable 0,316 ≤ β ≤ 0,775, 1,5·10⁵ ≤ Re_D ≤ 2·10⁶, 65 mm ≤ D ≤ 500 mm (même source LMNO). **Hors domaine** pour nos Re (voir plus bas).
- **Buse à entrée libre (ISO 5801, banc de ventilateur)** : coefficient de l'ordre de 0,97–0,99 pour un col profilé, **non confirmé** (aucune fiche ISO 5801 consultée) ; typiquement ≈ 0,985 (soudé) à 0,995 (usiné) pour un venturi (https://neutrium.net/fluid-flow/discharge-coefficient-for-nozzles-and-orifices/).
- Compressibilité : à Δp ≤ 400 Pa et p₁ ≈ 101 325 Pa, ε ≈ 1 − Δp/(2κp₁) ≈ 0,9986 (κ = 1,4) — négligeable (calcul propre, développement du premier ordre).

**Dimensionnement indicatif (calcul propre, à confirmer par étalonnage)** — buse d'aspiration Ø40 mm, C ≈ 0,98 (hypothèse), β → 0 :

| Q (m³/h) | v au col (m/s) | Δp (Pa) | Re_d (ν = 1,5·10⁻⁵ m²/s) |
|---|---|---|---|
| 12 | 2,65 | ≈ 4,4 | ≈ 7 100 |
| 30 | 6,6 | ≈ 27 | ≈ 17 700 |
| 60 | 13,3 | ≈ 110 | ≈ 35 400 |

- Un SDP810-125Pa couvre 60 m³/h (110 Pa < 125 Pa) avec un zéro de 0,08 Pa ⇒ incertitude zéro ≈ 0,9 % du débit à 12 m³/h (δQ/Q = ½·δΔp/Δp) ; mais **span 3 % de la lecture ⇒ ≈ 1,5 % de Q** ; l'incertitude totale restera dominée par le Cd (non établi à Re < 10⁴) : **étalonner la buse in situ** avec un débitmètre de référence (SFM3019 sur le point bas, par exemple).
- À 12 m³/h, Re ≈ 7 100 est inférieur à 10⁴ : domaine hors norme, Cd inconnu ⇒ **courbe de Cd(Re) à mesurer**.

### b3. Vitesse débitante dans les orifices
Pas de mesure directe : le débit est déduit de la buse, la pression du plenum de l'orifice par Q = Cd_orifice·A·√(2Δp/ρ) (voir `ventilateurs.md` § 0).

## c) Inclinomètres — 3 gammes

Cible : **résolution ≤ 2 µrad, stabilité ≤ 5 µrad/h** → seules les gammes intermédiaire/métrologique approchent l'exigence ; **tous** nécessitent thermostatisation (≤ 0,05–0,1 K), moyennage et retournement/calibration (le « zéro » dérive de quelques µrad/°C à plusieurs dizaines).

| Gamme | Capteur | Étendue | Résolution / bruit | Stabilité de biais | Interface | Prix | Source |
|---|---|---|---|---|---|---|---|
| Économique | **Murata SCL3300-D01** (MEMS, 3 axes) | ±90° (modes 1/2), ±10° mode 3/4 | LSB angle 0,0055° (96 µrad) ; densité de bruit **0,0012–0,0024 °/√Hz** soit 21–42 µrad/√Hz (mode 4 : 0,0009–0,0012 °/√Hz) ; bruit intégré 0,06–0,13 mg RMS (mode 3/4) ≈ 60–130 µrad RMS, bande 10 Hz | offset ±20 mg (±1,15°) ; **dérive offset sur −40…+125 °C ±10 mg (±0,57°)** ; dérive de vie ±8 mg (±0,46°) ; valeurs ±3σ non garanties | SPI | puce ≈ 30–40 USD ; carte d'évaluation 77 USD (agrégateurs : https://www.findchips.com/search/SCL33) | https://www.murata.com/~/media/webrenewal/products/sensor/pdf/datasheet/datasheet_scl3300-d01.pdf (Rev. 4) ; flyer ±0,005 °/°C (non vérifié) |
| Économique | **Analog Devices ADXL355** (accéléromètre MEMS 3 axes) | ±2,048 / ±4,096 / ±8,192 g, 20 bit | bruit **25 µg/√Hz** (± 25 µrad/√Hz en inclinaison) ; 256 000 LSB/g (≈ 3,9 µrad/LSB) | offset vs T : **±0,02 mg/°C typ., ±0,15 mg/°C max** (= 20 à 150 µrad/°C) ; sensibilité ±0,01 %/°C | SPI/I²C | non confirmé | https://www.zeuthen.desy.de/~sulanke/Projects/ICECUBE/mDOM/mainboard/datasheets/sensor_inclino_accelero_adxl354_355.pdf (miroir de la datasheet ADI ; la révision C annonce 22,5 µg/√Hz) |
| Économique/interm. | Analog Devices ADIS16209 / ADIS16203, Murata SCA3300, TDK | non confirmé (fiches non récupérées : l'URL analog.com a renvoyé « empty reply ») | non confirmé | non confirmé | SPI | non confirmé | non traité |
| Économique (outil) | **Digi-Pas DWL-5000XY / DWL-5500XY** (2 axes, MEMS ?) | 0–±10° (1 axe) / 0–±5° (2 axes) | DWL-5000XY **0,01° (≈ 175 µrad)** ; **DWL-5500XY 0,001° (17,5 µrad, « 18 µm/m, 3,6 arcsec »)** ; DWL-5800XY 1 arcsec (≈ 4,8 µrad) | précision ±0,001° entre 0 et 2° (5500XY) ; ±0,003° ailleurs | RS-485 (5000XY) ; USB / RS-232 / RS-485 via boîtier de contrôle (5500XY), Bluetooth optionnel ; 9–12 V DC ; IP65 | non confirmé | https://www.digipas.com/product/precision-measurement/2-axis-inclination-sensor-module/ (résolution) ; tableau complet via revendeur https://manualshive.com/ru/manual/digi-pas/dwl5000xy/2496732?page=6 (non ré-ouvert : accès bloqué) ; **résolution 17,5 µrad : 9 fois trop grossière** pour 2 µrad |
| Intermédiaire | **Wyler ZEROTRONIC 3** (capteur capacitif à pendule, ±0,5° … ±10°) | ±0,5° (version la plus fine) | **0,108 arcsec = 0,52 µrad** (moyenne de 10 valeurs, 8 s) ; 0,36" = 1,75 µrad (1 s, 1 valeur) ; 0,738" = 3,6 µrad (0,1 s) | zéro 24 h : 0,070 % étendue = 1,26" = **6,1 µrad** ; 6 mois : 3,06" = 14,8 µrad ; **temp. 1,08"/°C = 5,2 µrad/°C** (réduit par la compensation « HTR ») ; dérive de zéro éliminable par mesure de retournement | numérique (RS-485/USB via interface Wyler) | non confirmé | https://symetrie.fr/wp-content/uploads/2025/03/Wyler_Chapter_Zerotronic2025.pdf (tableau « Technical specifications », ±0,5° colonne gauche) |
| Intermédiaire | **Wyler BlueLEVEL / BlueSYSTEM** | non confirmé | non confirmé | non confirmé | Bluetooth / USB | non confirmé | non confirmé (mentionnés dans le chapitre Wyler ci-dessus comme « BlueLEVEL typiquement utilisé en environnement contrôlé »), pas de chiffres |
| Intermédiaire | **Jewell Instruments LCF-3000** (inclinomètre à boucle fermée, 3 axes) | ±3° … ±90° | résolution et seuil **≤ 1,0 µrad** ; bande 3 Hz (±3°) | facteur d'échelle 100 ppm/°C max ; stabilité du zéro non confirmée | analogique | non confirmé | https://core.instrumart.com/assets/Jewell-LCF-3000-datasheet.pdf (via https://pdf.directindustry.com/ja/pdf-en/jewell-instruments/lcf-3000-data-sheet/29986-436521.html) |
| Métrologique | **Leica Nivel210 (RS-232) / Nivel220 (RS-485)** — 2 axes | ±1,51 mrad (classe A), ±2,51 (B), ±3,00 (C) | **0,001 mrad = 1 µrad (0,6 cc)** ; moyennage jusqu'à 128 mesures dans le capteur ; cycle 300 ms | précision ±4,7 µrad (A) ; **stabilité du zéro ≈ 4,7 µrad/°C (< 3 cc/°C)** ; température −20…+50 °C ; capteur de température intégré | RS-232 / RS-485 (1200–38 400 bauds) ; 32 adresses (RS-485) ; 9–15 V, 0,6 W | non confirmé | https://dr.leica-geosystems.com/-/media/files/leicageosystems/products/brochures/leica_nivel210-220_bro.ashx |
| Métrologique | **Jewell/Applied Geomechanics A701-2** (tiltmètre électrolytique) | A701-2A : ±800 µrad ; A701-2B : ±8000 µrad | **< 0,1 µrad** (2A) ; 1 µrad (2B) ; répétabilité statique 1 µrad | **coefficient de biais thermique ±3 µrad/°C typ.** (autre fiche : ±4 µrad/°C) ; « dérive à long terme pratiquement nulle » (revendeur) | analogique (mV) | non confirmé | https://www.jewellinstruments.com/Catalogs/Geo/files/basic-html/page38.html ; https://pdf.directindustry.com/pdf/jewell-instruments/a701-2-tiltmeter-datasheet/29986-654747.html ; chiffres contradictoires sur la variante 4X |
| Métrologique | Niveaux à bulle de précision 0,02 mm/m / 0,01 mm/m | n/a | 0,02 mm/m = **20 µrad** par division ; 0,01 mm/m = **10 µrad** (définition arithmétique) | dépend de la température (dilatation du liquide) | lecture visuelle | non confirmé | non traité (aucune fiche) — ne permet pas 2 µrad sans lecture d'interpolation ou capteur |

**Lecture pour la conception**
- Les MEMS (SCL3300, ADXL355) ont une dérive thermique de **20 à 100 µrad/°C** et un bruit de 20–40 µrad/√Hz : **inutilisables comme référence 2 µrad** sans thermostatisation à ≈ 0,05 K et moyennage long ; ils peuvent servir de **capteur de dégrossissage** et de surveillance de vibration.
- **Leica Nivel220** (1 µrad de résolution, 4,7 µrad/°C) et **Wyler ZEROTRONIC 3** (0,5 µrad de résolution moyennée, 5,2 µrad/°C compensés HTR en option) sont les candidats **métrologiques** réalistes ; avec une enceinte à ± 0,1 K, la dérive thermique se réduit à ≈ 0,5 µrad.
- **La stratégie recommandée** : mesure par **retournement (180°)** pour éliminer le zéro (Wyler le préconise), + **calibration par palet** (le comportement réel du palet est la mesure finale), + température du capteur dans la boucle.
- Aucun prix constructeur confirmé pour les gammes Wyler/Leica/Jewell : demander devis.

## d) Mesure de déformation de plaque (cible : résolution ≲ 0,1 µm, plage ≲ 50–200 µm)

| Technologie | Produit | Résolution | Étendue | Stabilité thermique / long terme | Interface | Prix | Source |
|---|---|---|---|---|---|---|---|
| Capacitif | **Micro-Epsilon capaNCDT 6110/6112** (DT6110) | 0,01 % FSO statique (**≈ 20 nm sur 0,2 mm**) ; 0,015 % FSO dynamique à 1 kHz | gammes 0,05 / 0,2 / 0,5 / 0,8 / 1 / 2 / 3 / 5 / 10 mm | **200 ppm/°C FSO** (≈ 40 nm/°C sur 0,2 mm) ; stabilité long terme < 0,05 % FSO/mois (≈ 100 nm/mois sur 0,2 mm) ; linéarité < 0,05 % FSO | analogique, numérique selon variante | non confirmé | https://cdn.bestech.com.au/wp-content/uploads/2019/05/capaNCDT-6112-ID-656.pdf ; page produit (résolution max 0,005 µm, linéarité max 0,025 µm — chiffres contradictoires avec la fiche ; non confirmé) https://www.micro-epsilon.com/distance-sensors/capacitive-sensors/capancdt-6110/?sLang=en |
| Capacitif | **Micro-Epsilon capaNCDT 6500** (multi-canaux) | « sub-nanométrique » (revendeur : 0,0375 nm max ; non confirmé) | idem | contrôleur 9 ppm/°C (revendeur, non confirmé) | numérique 7,8 kHz | non confirmé | https://www.micro-epsilon.com/distance-sensors/capacitive-sensors/capancdt-6500/ |
| Capacitif | **Lion Precision CPL190/290** | 0,0005 % @ 100 Hz ; 0,003 % @ 15 kHz (probe 0,5 mm, plage 10 µm : **0,06 nm @100 Hz, 0,5 nm @15 kHz** ; plage 50 µm : 0,30 nm @100 Hz, 3,0 nm @10 kHz) ; valeurs RMS, pointe-à-pointe 8-10× | de 10 µm à 12,5 mm selon la sonde | **dérive max 0,04 % FS/°C** (plage 50 µm → 20 nm/°C) ; température d'emploi 15–40 °C | ±10 V analogique | non confirmé | https://www.lionprecision.com/wp-content/uploads/2022/07/Brochure-CPL190_290.pdf |
| Palpeur inductif numérique | **Solartron Orbit 3 (DP/…/S)** | résolution sélectionnable jusqu'à **0,01 µm** (revendeur) | ±0,25 / ±0,5 / ±1 / ±1,5 mm | répétabilité typ. 0,05 µm (max 0,10–0,15 µm) ; linéarité 0,5 % de la lecture (0,25–1,5 µm) ; force de mesure 0,7 N (**contact : déformation locale, à éviter sur une plaque de 25 mm ?** non confirmé) | module Orbit (USB/Ethernet/RS-232, 3906 mesures/s) | non confirmé | https://scigate.com.sg/images/stories/scigate/products/Solartron/analogue-catalogue-en.pdf (tableau « Technical Specifications ») ; https://scigate.com.sg/products/40-solartron-metrology/1773-solartron-digital-orbit3-digital-probes-with-in-line-connector-spec |
| Règle optique | **Heidenhain MT 1281** (12 mm) | dépend de l'interpolation externe (1 Vpp, période 4 µm ; non confirmé) | 12 mm | **classe de précision ±0,2 µm** | 1 Vpp | non confirmé | https://www.heidenhain.com/product-details/length-gauges/383965-04 (via recherche ; page non ouverte) |
| Règle optique | **Heidenhain ST 1278** (12 mm) | pas de 0,2 µm avec interpolation ×10 (période 2 µm) ; autre version 0,8 µm | 12 mm | précision ±1,0 µm | TTL | non confirmé | https://www.heidenhain.com/product-details/length-gauges/359355-02 |
| Autres (Mahr, Mitutoyo LGF/LGK, courants de Foucault, interférométrie) | non confirmé | non confirmé | non confirmé | non confirmé | non confirmé | non confirmé | **non traités** : pas de fiche exploitable trouvée dans le temps imparti |
| Jauges de déformation | pont pleine/ demi-pont + **TI ADS1220** (24 bit, PGA 1–128) ou HX711 | ADS1220 : « jusqu'à 20 bits de résolution effective » ; dérive d'offset 0,08 µV/°C typ. (0,3 µV/°C max) | — | — | SPI | HX711 ≈ quelques USD (non confirmé) | https://www.ti.com/lit/gpn/ads1220 ; HX711 : ≈ 16 bits sans bruit en pratique selon forum https://forum.arduino.cc/t/hx711-noise-free-resolution-tests/351959 (**source faible**) |

**Lecture pour la conception**
- Une variation de flèche de **1,5 µm** entre p = 0 et p_max est le critère : capaNCDT 6110 (20 nm) ou CPL190 (≪ 10 nm) suffisent largement en résolution ; **la dérive thermique (200 ppm/°C FSO soit 40 nm/°C pour 0,2 mm ; 0,04 %/°C FS soit 20 nm/°C pour 50 µm) est le terme dominant** — mesurer **différentiellement** (réf. au plan de montage) et thermostater.
- Compter 3–5 capteurs capacitifs répartis (centre + bords) : dispositifs ou supports fixés au bâti, pas à la plaque.
- Les jauges de déformation sont plus économiques mais donnent la déformation locale, pas la flèche, et dérivent (colle, fluage) : **non recommandées pour 1,5 µm absolu** (jugement d'ingénieur).

## e) Température et hygrométrie/pression

| Capteur | Précision | Résolution | Stabilité | Interface | Source |
|---|---|---|---|---|---|
| **TI TMP117** | **±0,1 °C max (−20…+50 °C)** ; ±0,15 °C (−40…+70) ; ±0,25 °C (−55…+125) | 0,0078 °C (16 bit) | dérive typ. ±0,03 °C après 1000 h à 150 °C (non garantie) | I²C ; 4 adresses via broche ADD0 (GND, V+, SDA, SCL) | https://www.ti.com/lit/gpn/TMP117 ; dérive : https://e2e.ti.com/support/sensors/f/sensors-forum/812659/tmp117-long-term-stability-and-drift-parameter-interpretation |
| Analog Devices ADT7420 | ±0,20 °C (−10…+85 °C, 3,0 V) ; ±0,25 °C (−20…+105 °C) | 0,0078 °C (16 bit) | non confirmé | I²C ; **dernier achat (LTB)** | https://www-cce.cldnet.analog.com/media/en/technical-documentation/data-sheets/ADT7420.pdf (via recherche) |
| PT100/PT1000 + MAX31865 | non confirmé (fiche MAX31865 non récupérée : « empty reply ») ; ordre de grandeur possible : classe A/B de la sonde dominante | non confirmé | non confirmé | SPI | non traité |
| Sensirion SHT45 | ±0,1 °C typ. (0…75 °C) ; ±1,0 %RH typ. (25…75 %RH) | non confirmé | non confirmé | I²C | https://sensirion.com/products/catalog/SHT45 |
| **Bosch BME280** | pression : bruit **0,2 Pa RMS** ; coefficient thermique d'offset **±1,5 Pa/K** ; dérive long terme ±1,0 hPa/an ; humidité : 0,008 %RH, bruit 0,02 %RH, dérive 0,5 %RH/an ; T : bruit 0,005 °C, sortie 0,01 °C | voir colonne précision | voir colonne précision | I²C/SPI | https://cdn-shop.adafruit.com/datasheets/BST-BME280_DS001-10.pdf |
| Bosch BME680 | non confirmé | non confirmé | non confirmé | I²C/SPI | non traité |

**Lecture** : le gradient thermique à travers la plaque doit rester ≤ 0,05 K (`design.toml`). Le **TMP117 (0,0078 °C de LSB, ±0,1 °C absolu)** convient en **mesure différentielle** (deux TMP117 de même lot, mêmes conditions), la précision absolue de 0,1 °C ne garantit pas 0,05 K entre deux capteurs : **les apparier en bain/in situ**. Le BME280 sert au suivi ρ(T,p,HR), pas au contrôle de pression de plenum (coefficient thermique de 1,5 Pa/K).

## f) Vitesse du ventilateur

- **Tachymètre intégré** (sortie collecteur ouvert) : San Ace « pulse sensor » (impulsions par tour **non confirmées** dans la fiche 9BMC lue, https://cdn.components.ru/media/PDF/6729644.pdf) ; Micronel U97HL : **3 impulsions/tour**, n [min⁻¹] = 20·f [Hz] (https://inelso.ru/upload//specs/U97HL.pdf) ; ebm-papst G1G108 : sortie « tacho » (nombre d'impulsions non confirmé, https://media.distrelec.com/Web/Downloads/02/_e/emG1G108AB1702_e.pdf).
- Mesure par **capture de période** (timer matériel) : à 2800 min⁻¹ avec 2 impulsions/tour (hypothèse), f = 93 Hz ; avec un timer à 1 MHz la résolution est ≈ 0,1 %. À 1500 min⁻¹ (point bas) le temps de mise à jour de la boucle est de l'ordre de la période : prévoir moyenne glissante (calcul propre).
- Capteur optique/Hall additionnel : non confirmé (non traité) — pas nécessaire tant que le tachy est présent.
