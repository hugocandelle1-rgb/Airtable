# Profilés aluminium et mécanique de nivellement fin

> Date : 2026-10-29. « non confirmé » = pas de fiche exploitable. Les valeurs de profilés varient d'une variante (1N/2N/4N, « leicht ») à l'autre : **toujours vérifier la référence exacte avant l'achat** (par exemple Bosch Rexroth 45 × 45 : 11,7 cm⁴ ou 13,8 cm⁴ selon l'article).
> Contexte de conception (`params/design.toml`) : `profile_main_mm = 45`, `[frame] profile_system = "TBD (item MB / Bosch Rexroth / Misumi — rainure 8 ou 10)"` ; course de réglage ± 0,25° (= ±4,36 mrad), résolution ≤ 2 µrad par axe.

## 1. Profilés — propriétés de section

| Système | Profil | Réf. | Ix (cm⁴) | Iy (cm⁴) | Masse (kg/m) | Section (cm²) | Source |
|---|---|---|---|---|---|---|---|
| **item Profil 8** | 40 × 40 léger, 1 rainure fermée (1N) | 0.0.422.72 | 9,59 | 9,01 | 1,79 | 6,64 | https://www.item24.com/fr-be/profil-8-40x40-1n-leicht-natur-42272 |
| item Profil 8 | 40 × 40 léger 4 rainures | 0.0.026.33 | 9,00 | 9,00 | 1,74 | 6,46 | datasheet item via recherche (https://static.mercateo.com/ff/6996b3ad28464d939bc17e037ed63c99/pdf/7613335_eng_tds.pdf pour la variante RS 2N90 : 9,81 cm⁴, 1,85 kg/m, 6,84 cm²) |
| item Profil 8 | 80 × 40 léger 2N | 0.0.422.75 | 17,73 | 70,87 | 3,13 | 11,6 | https://www.item24.com/en-de/profile-8-80x40-2n-light-natural-42275/ |
| item Profil 8 | 80 × 80 léger 4N90 | 0.0.452.47 | 140 | 140 | 5,5 | 20,39 | https://item24.com/en-us/profile-8-80x80-4n90-light-natural-45247 |
| item Profil 8 | 80 × 80 D40 (profil lourd) | 0.0.408.28 | 222 | 222 | 10,04 | 37,2 | https://product.item24.de/directlink/en/pro/40828 (via recherche) |
| **Bosch Rexroth** | 45 × 45 4 rainures (rainure 10) | 38425… | 11,7 (autre article : 13,8) | 11,7 (13,8) | 1,6 (2,0) | 6,0 | https://directindustry.com/prod/bosch-rexroth-assembly-technology/product-127183-2537549.html ; autre article https://boxic24.com/english/bosch-rexroth-3842992969.html (**chiffres contradictoires, à lever sur la fiche Rexroth**) |
| Bosch Rexroth | 45 × 45 1N / 0N | – | 12,6 / 13,5 ; 13,5 / 13,5 | – | 1,8 | – | https://boxic24.com/english/datasheet/pdf/index/id/14548/ (via recherche) |
| Bosch Rexroth | 45 × 90 L (6 rainures) | 3842993084 | 82 | 23,6 | 3,0 | 11,3 | https://boxic24.com/english/bosch-rexroth-3842993084.html ; variante 4N : 83,6 / 25,2, 3,2 kg/m |
| Bosch Rexroth | 45 × 180 | – | 766,7 | – | 6,9 | – | https://www.directindustry.com/prod/bosch-rexroth-assembly-technology/product-127183-2537408.html (via recherche) |
| **Misumi HFS8** (série 8, rainure 10 mm) | HFS8-4040 | HFS8-4040 | 10,4 | 10,4 | 1,73 | 6,40 | https://mx.misumi-ec.com/en/vona2/detail/110302690040 |
| Misumi | HFS8-4080, HFS8-8080 | – | non confirmé | non confirmé | non confirmé | non confirmé | non trouvé dans la recherche |
| item MB Building Kit (Profil 8 40 × 40 « E » etc.) | non traité (MB = Profil 8 ; « E » = économique, non confirmé) | – | – | – | – | – | – |

**Notes.**
- **Rainure** : la « série 8 » est donnée avec une **largeur de rainure de 10 mm** (Misumi : « 8 Series / slot width 10 / 40 × 40 mm », https://cz.misumi-ec.com/vona2/detail/110302689950). Les fiches RS pour item écrivent « groove 8 mm » (https://static.mercateo.com/ff/6996b3ad28464d939bc17e037ed63c99/pdf/7613335_eng_tds.pdf) : la désignation « 8 » est la **taille de gamme**, pas l'ouverture ; la largeur d'ouverture de 10 mm est **non confirmée sur la fiche item**. Bosch Rexroth 45 × 45 : rainure 10 mm (ex. https://uk.rs-online.com/web/p/connecting-components/2673103 « groove size 10 mm »).
- **Force d'extraction de rainure** item (40 × 40 léger) : 2500 N (https://www.item24.com/fr-be/profil-8-40x40-1n-leicht-natur-42272).
- **Raideur de flexion** : E·I pour 45 × 45 (≈ 11,7 cm⁴) = 70 GPa × 11,7·10⁻⁸ m⁴ = **8,2 kN·m²** ; pour 80 × 80 léger (140 cm⁴) = **98 kN·m²**, soit un rapport 12 : à prendre en compte pour la flèche de l'ensemble plenum/plaque/appuis (calcul propre, E = 70 GPa de l'aluminium 6063 ; les fiches ne précisent pas E).
- Profilés item : 6063 (EN AW-6063), anodisation 15 µm (fiche RS ci-dessus).

## 2. Panneaux dans la rainure : épaisseurs admissibles, joints et profilés de fermeture

| Système | Produit | Réf. | Épaisseur de panneau | Matière | Source |
|---|---|---|---|---|---|
| item (Profil 8) | **Dichtprofil 8 2–4 mm**, noir | 0.0.436.83 (déduit de l'URL ; non confirmé) | 2–4 mm | TPV | https://www.item24.com/de-de/dichtprofil-8-2-4mm-schwarz-43683 (URL citée par la page 43686) |
| item (Profil 8) | **Dichtprofil 8 4–6 mm**, noir | **0.0.436.86** | 4–6 mm | TPV, 26 g/m | https://www.item24.com/de-de/dichtprofil-8-4-6mm-schwarz-43686 |
| item (Profil 8) | Dichtprofil 8 2–4 mm, gris RAL 7040 | URL …-48989 (réf. non affichée) | 2–4 mm | TPV | https://www.item24.com/de-de/dichtprofil-8-2-4mm-grau-aehnlich-ral-7040-48989 (via page 43686) |
| item (Profil 8) | **Einfassprofil 8 4–6 mm**, noir (profilé de bordure qui encadre la plaque entièrement dans la rainure) | **0.0.495.06** | 4–6 mm | TPE | https://www.item24.com/de-de/einfassprofil-8-4-6mm-schwarz-49506 |
| item (Profil 8) | Abdeckprofil 8 32×4 (profilé de fermeture de rainure, NBR) | 42902 (URL) | n/a | NBR | https://www.item24.com/de-de/abdeckprofil-8-32x4-schwarz-42902 |
| item (Profil 8) | Dichtung 8 80×80 PE, naturel (joint adhésif profilé/profilé) | 42079 (URL) | n/a | PE | https://www.item24.com/de-de/dichtung-8-80x80-pe-natur-42079/ |
| item (Profil 8) | Outils : Montagewerkzeug Dichtprofil 6-12 ; Allzweckschere | 0.0.493.28 ; 0.0.265.63 | – | – | https://www.item24.com/de-de/dichtprofil-8-4-6mm-schwarz-43686 |
| Bosch Rexroth (rainure 10) | joints de panneau 45 × 45 | non confirmé | non confirmé | – | **aucun joint de panneau n'a été trouvé** (la recherche ne renvoie que des connecteurs, panneau galvanisé 3842523243 ; https://uk.rs-online.com/web/p/door-components/2788995?gb=s) |
| Misumi HFS8 | joints/profilés de panneau | non confirmé | non confirmé | – | non traité |
| Autre fabricant (Fath) | joint disque TPE pour rainure 8/10 : **2–4 mm et 4–6 mm (jusqu'à 6 mm sur demande)** | non confirmé (n° dans le catalogue) | 2–6 mm | TPE | https://www.marek.eu/katalog-obrazku/produkt-32470/80686-fath-katalog-strana-709.pdf |

**Lecture** : la gamme de **joints de panneau item couvre 2–6 mm** (deux plages : 2–4 et 4–6 mm). Pour le **plenum** (pression ≈ 400 Pa, étanchéité à fuite faible) : panneaux de 4–6 mm avec Dichtprofil/Einfassprofil 4–6 mm. Les panneaux plus épais (> 6 mm) ne trouvent pas de joint prêt à l'emploi sur ces profils : prévoir fraisage d'une feuillure, un joint rapporté (mousse, PE), ou une fixation par équerres. **Le plan (`docs/00_cahier_des_charges.md` § 4.7)** impose l'étanchéité à tous les étages : l'étanchéité est testable en pression (voir les capteurs SDP).
Équerres, pieds de réglage, éléments de jonction : non traités faute de temps (références item/Rexroth à relever dans leurs catalogues) — **non confirmé**.

## 3. Nivellement fin et accouplement cinématique

### 3.1 Dimensionnement des exigences (calcul propre)
- Réglage 2 axes sur appui à trois points (1 fixe + 2 mobiles, schéma « 3pt-kelvin » de `design.toml`). Pour un bras de levier de 400 mm (hypothèse), une résolution de **2 µrad = 0,8 µm** de déplacement par actionneur, et une course de **±0,25° = ±4,36 mrad = ±1,75 mm** (soit 3,5 mm au total) ⇒ au moins **4400 pas distincts de 0,8 µm**.
- Charge axiale = poids du plenum + plaque (plaque 18 kg ; plenum non chiffré) répartie sur deux actionneurs : de l'ordre de **100–200 N par actionneur** pour 20–40 kg (hypothèse) ⇒ **les actionneurs à faible charge (Thorlabs Z8 : 40 N ; Newport TRA : 60 N ; Zaber NA08 : 19 N, NA11 : 58 N) sont insuffisants sans ressort de décharge ou contrepoids** : prévoir une transmission par levier/ressort de compensation ou un actionneur de plus forte charge (vis à rouleaux, vis + écrou à billes + moteur pas à pas).

### 3.2 Composants manuels (vis micrométriques / différentielles)

| Produit | Pas / sensibilité | Course | Charge axiale | Source |
|---|---|---|---|---|
| Thorlabs **DAS110** (1/4"-80, 1,00") | **25 µm/tour** (réduction différentielle) ; vis 80 TPI standard = 318 µm/tour | non confirmée | non confirmée | https://www.thorlabs.de/catalogpages/v20/522.pdf (pages 521/522/527 : https://www.thorlabs.us/catalogpages/v20/521.pdf) |
| Thorlabs **FAS100 … FAS300** (1/4"-80, 1" à 3") | 80 TPI (318 µm/tour) | – | non confirmée | https://www.thorlabs.de/catalogpages/392.pdf (via recherche) |
| Newport **DS-4F** (ajusteur haute précision, interface Ø9,5 mm) | **0,02 µm** de sensibilité | 8,0 mm gros + **0,3 mm fin** | **49 N** | https://np.s2.mks.com/f/ds-4f-high-precision-adjuster |
| Newport **AJS127-0.5** (127 TPI) | **0,56 µm** | 12,7 mm | 90 N (revendeur) | https://industrialautomationparts.com/products/ajs127-0-5-newport-adjustment-screw-127-tpi-12-7mm-travel-small-knob (non confirmé chez Newport) |
| Newport AJS254-0.5H | 280 nm de sensibilité | 12,7 mm | non confirmée | https://www.newport.com/p/AJS254-0.5H-NL |
| Newport DM-13 (micromètre différentiel) | 13,0 mm gros / 0,2 mm fin | – | 5 lb (≈ 22 N) | https://www.newport.com/p/DM-13 |
| Newport DM11-16 | 16,1 mm gros / 0,1 mm fin | – | 6,6 lb (≈ 29 N) | https://www.newport.com/p/DM11-16 |

**Lecture** : la course fine des différentiels (0,1–0,3 mm) est **trop courte pour ±1,75 mm** ; un étage grossier (vis M8/M10) + un étage fin différentiel est donc nécessaire. Sensibilité de DS-4F (0,02 µm) largement suffisante pour 0,8 µm, mais **charge 49 N**.

### 3.3 Actionneurs motorisés

| Produit | Course | Résolution / pas mini | Précision / répétabilité | Backlash | Charge axiale | Statut | Source |
|---|---|---|---|---|---|---|---|
| Thorlabs **Z825B** | 25 mm | 0,5 nm (calculé), 0,05 µm (étage) | non confirmée | < 15 µm | **40 N** | **obsolète depuis le 22/11/2023** | https://www.thorlabs.com/catalogpages/Obsolete/2023/Z825B.pdf |
| Thorlabs ZFS | non confirmé | non confirmé | non confirmé | non confirmé | non confirmé | non confirmé | non traité |
| Newport **TRA12CC / CONEX-TRA12CC** | 12 mm | **0,20 µm** | précision ±2,2 µm typ. (±4,0 garanti) ; répétabilité unidirectionnelle ±0,10 µm typ., bidirectionnelle ±1,25 µm garantie | non confirmé | **60 N** | catalogue | https://np.s2.mks.com/p/CONEX-TRA12CC |
| Newport TRA6CC | 6 mm | 0,20 µm | idem | non confirmé | 60 N | catalogue | https://www.newport.com/p/CONEX-TRA6CC |
| Newport TRB12CC | 12 mm | non confirmé | non confirmé | non confirmé | non confirmé | catalogue | https://www.newport.com/p/CONEX-TRB12CC |
| Zaber **NA08B30-T4** | 30 mm | 0,09525 µm (pas moteur) | précision unidirectionnelle 20 µm | non confirmé | poussée continue 19 N | **NA sans auto-détection : arrêté** | https://www.zaber.com/products/linear-actuators/NA/noAD |
| Zaber **NA11B30-T4** | 30 mm | 0,0992 µm | précision 25 µm ; répétabilité < 5 µm | < 18 µm (revendeur) | poussée continue **58 N** | idem | https://www.zaber.com/products/linear-actuators/NA/noAD ; https://photonics.laser2000.co.uk/?p=7826 |

**Lecture** : tous ces actionneurs ont un **pas de 0,1–0,2 µm** (ok pour 0,8 µm) mais une **charge ≤ 60 N** : ils ne portent pas directement le poids du plenum. Ils peuvent être utilisés **en parallèle d'un appui porteur** (bille/vé, ressort) **comme micro-réglage**. Le jeu (backlash 8–18 µm) impose une approche toujours **dans le même sens** et une boucle fermée sur l'inclinomètre.

### 3.4 Accouplement cinématique (billes / vés) et nivellement de machine
- Principe : trois billes dans trois vés ou « sphère-cône-plan » = 6 points de contact, **répétabilité sous-micrométrique possible** en théorie (brevet : https://patents.google.com/patent/US5678944) ; les ordres de grandeur pratiques sont « quelques microns » (https://cdn.shopify.com/s/files/1/0632/2123/5966/files/Tool_Probe_Mount_Explained_5-23-22.pdf). La limite est l'état de surface des contacts ; la capacité de charge est limitée par la contrainte de Hertz (https://pergatory.mit.edu/kinematiccouplings/html/about/kinematic.html).
- Références Thorlabs/Newport/Bal-tec (kits de couplage, billes G5) : **non trouvées** ; non confirmé.
- Vérins/cales de nivellement machine (pieds de réglage) : un article NHK indique que la charge admissible est fixée par la **longueur de filet engagé** (≈ 90 % de la charge sur les 5–7 premiers filets ; engagement ≥ 1,5 × diamètre) — source : https://nhkmachineryparts.com/thread-engagement-levelling-feet/ ; aucun chiffre de résolution ; **les pieds de réglage ne servent qu'au nivellement grossier** (course fine ±0,25° par le dispositif 3.2/3.3).

### 3.5 Drivers pas à pas
| Driver | Courant | Tension | Micropas | Particularités | Source |
|---|---|---|---|---|---|
| **TMC2209** | 2,8 A crête (2 A eff.) | 4,75–29 V | 256 µpas par interpolation MicroPlyer | StealthChop (silencieux), step/dir | https://wcm-cce.cldnet.analog.com/media/en/technical-documentation/data-sheets/TMC2209_datasheet_rev1.08.pdf |
| **TMC5160** | jusqu'à 20 A (MOSFETs externes ; « 20 A » non étiqueté crête dans l'extrait) | 8–60 V (comparatif) | 256 | contrôleur de mouvement SixPoint, SPI & UART | https://manualmachine.com/trinamic/tmc5160evalkit/24889998-datasheet ; https://uk.avaq.com/technology/tmc5160-vs-tmc2209-what-are-differences-2023 |

**Lecture** : pour une vis de pas 0,5 mm, 200 pas/tour × 256 micropas = 51 200 µpas/tour ⇒ 9,8 nm/µpas (calcul propre) ; la **résolution mécanique est limitée par la précision de la transmission et le jeu**, pas par le driver. Le TMC2209 suffit ; le silence (StealthChop) est utile (pas de vibration sur le palier d'air).
