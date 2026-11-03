# Composants du lot structure : références et statut des sources

> Date : 2026-11-03. Ce fichier recense les composants du commerce cités dans
> `docs/03_structure_plaque.md`, `docs/04_usinage_tolerances.md` et
> `docs/05_nivellement.md`.
>
> Statuts :
>
> - « sourcé » : un chiffre est tiré d'une fiche citée dans `docs/research/` ;
> - « non confirmé » : valeur de catalogue courante, **à vérifier avant achat**. Aucune
>   recherche web n'a été faite dans cette session.

| Composant | Utilisation | Chiffres utilisés | Statut | Source |
|---|---|---|---|---|
| Tôle coulée EN AW-5083 ACP 5080 / Formodal 030 / MIC-6 | plaque 520 × 520 × 35 (brut 40) | E 70 GPa, α 24,2·10⁻⁶, λ 110–140 W/m/K, ρ 2,66 | sourcé | `materiaux_plaque.md` |
| Profilés Bosch Rexroth 45×45 et 45×90 (rainure 10) | bâti | 45×45 : I 11,7 cm⁴ (valeur basse), 1,6 kg/m ; 45×90 : 82 / 23,6 cm⁴, 3,0 kg/m ; **constante de torsion non publiée** (hypothèse J = 0,3·ΣI) | sourcé (I, masse) ; non confirmé (J) | `profiles_alu_et_mecanique.md` |
| Joints de panneau 4–6 mm (item Dichtprofil 8 / Fath) | panneaux du bâti | plage 4–6 mm | sourcé (item) ; **pas de joint Rexroth trouvé** | `profiles_alu_et_mecanique.md` |
| Billes Ø25,4 G10 100Cr6 (DIN 5401 / ISO 3290) | appuis (3) | E 210 GPa | non confirmé (catalogue courant) | — |
| Arbres de guidage Ø20 h6 trempés rectifiés 60 HRC (Cf53 / 100Cr6) | rouleaux des vés (6) | — | non confirmé | — |
| Cages à aiguilles plates (type INA / Schneeberger) | coin des vérins | raideur supposée 2·10⁸ N/m | non confirmé | — |
| Vis de réglage fin M6 × 0,25 + écrou bronze | vérins | pas 0,25 mm | **non confirmé** : existence d'un M6 × 0,25 du commerce à vérifier. Repli : 1/4"-100 (0,254 mm) | — |
| NEMA17 double arbre, 200 pas/tr | vérins | couple de maintien ≈ 0,4 N·m | non confirmé (catalogue courant) | — |
| Driver TMC2209 | vérins | 256 µpas, StealthChop | sourcé | `profiles_alu_et_mecanique.md` § 3.5 |
| Thorlabs DAS110 (différentiel) | variante économique | 25 µm/tr (fin), 318 µm/tr (grossier) ; **charge et course non confirmées** | sourcé (pas) | `profiles_alu_et_mecanique.md` § 3.2 |
| Newport AJS127-0.5 | repli économique | 127 TPI, 12,7 mm, 90 N (revendeur) | partiellement sourcé | `profiles_alu_et_mecanique.md` § 3.2 |
| ADXL355 | inclinaison (×4) | bruit 25 µg/√Hz ; offset 0,02 mg/°C typique, 0,15 mg/°C maximum | sourcé | `capteurs.md` |
| TMP117 | température accolée aux ADXL355 | résolution 7,8 mK, ±0,1 °C | non confirmé ici (voir le lot firmware) | — |
| Pieds réglables M16 × 2 à rotule | bâti | — | non confirmé | — |
| XPS 10 mm (λ ≈ 0,035) | capots d'embase | — | non confirmé | — |

**À faire (vague 2, nomenclature)** : relever les références exactes chez Rexroth (fiche
45×90 avec Iₜ), INA (cages), Misumi (arbres, vis fines) et Thorlabs (charge du DAS110).
