# CAO paramétrique — table à coussin d'air (phase 2 : cotes figées)

Modèles CadQuery 2.8 pilotés par `params/design.toml` (V3.1-merged) ; les cotes de détail absentes du TOML
viennent du bloc `DEFAULTS` de `cad/common.py`, chacune avec la note source en commentaire
([02] `docs/02_aeraulique.md` §13, [03] `03_structure_plaque.md` §8, [04] `04_usinage_tolerances.md` §7,
[05] `05_nivellement.md` §7). Aucun affichage graphique : tout sort en fichiers dans `cad/export/`.

## Régénérer

Depuis la racine du dépôt :

    python3 -m cad.build_all                 # ~1 min : STEP, STL, SVG, DXF, CSV, plans, rapport
    python3 -m cad.build_all --no-svg --no-plans   # ~12 s
    python3 -m cad.build_all --full          # + plaque complète (5935 trous), délai max 600 s (--full-timeout)
    python3 -m cad.build_all --out DIR --set plate.thickness_mm=30 --set platine.plot_h_mm=25
    python3 -m cad.drawings                  # plans 2D seuls (cad/export/plans/)
    python3 -m cad.parts.plate               # test rapide de la plaque

`--set section.cle=valeur` surcharge un paramètre sans toucher au TOML. La plaque complète est construite dans
un sous-processus (outil étagé unique Ø2 / cône 118° / Ø0,30, un seul `occ_impl.shapes.cut` avec OBB) : au-delà de
`--full-timeout` elle est abandonnée et documentée dans le rapport ; `cad/export/*_full.*` est ignoré par git.

## Repère et conventions

- **Origine = centre de la face supérieure de la plaque, Z vers le haut**, +Y vers l'arrière, +X à droite.
  z_CAD = z_notes − 900 (dessus de plaque à 900 du sol) ; dessous de plaque z = −35 ; sol z = −900.
- Unités mm et kg. Pièces construites directement en coordonnées globales (pas de contraintes) ;
  les interférences se testent par intersection booléenne (tolérance 1 mm³ ; les contacts face à face sont admis).
- Cotes dérivées calculées une seule fois dans `common.levels(P)`. Profilés : `PROFILES` (40x40, 45x45, 40x80, 45x90),
  `bar`, `cut_list` ; masse = masse linéique catalogue **estimée, non sourcée** (à confirmer dans `docs/research/`).

## Pièces (≈ 117)

| Module | Contenu |
|---|---|
| `parts/plate.py` | plaque 520×520×35 EN AW-5083, 5935 trous (hex pas 5, lamage Ø2 fond 118°, orifice Ø0,30 × 1,2), sièges de billes Ø25,4, datums B/C, 32 M5, 12 M4, 4 M10, chanfreins ; billes ; `hole_centers`, CSV, DXF |
| `parts/plenum.py` | caisson suspendu (parois/fond 6, int. 430), joint EPDM 6×2, cornière 15×15×3, tôle inox Ø2 pas 8, média, déflecteur Ø200 + plots ; **plus de membrane** |
| `parts/leveling.py` | 3 blocs de vé + 6 rouleaux Ø20, vérins à coin 1:5 (boîtier, coin, tête, vis, accouplement, NEMA17, bouton) en P1/P2, rehausse fixe en P0, 3 étriers + patins PTFE, 4 embases ADXL355 |
| `parts/aero.py` | ventilateur San Ace 9BMC (enveloppe 97×95×33), manchon L100, adaptateur, diffuseur Ø50→Ø80 L245, conduit + vanne de décharge, aspiration déportée (caisson 320×220×320, filtre ePM1, buse col Ø30, tube) |
| `parts/frame.py` | bâti Rexroth : montants 45×90, cadre 45×90 (545 hors tout), ceintures 45×45, écharpes sur 3 faces, 4 pieds Ø80, platine + 4 plots + 2 traverses, écran PMMA 120 + couvercle, portique caméra libre |
| `drafting.py`, `drawings.py` | moteur de mise en plan (matplotlib) et 6 plans cotés |

## Sorties (`cad/export/`)

`assemblage.step`, `pieces/*.step|stl`, `barres/*.step`, `plaque_trous.dxf` (calques LAMAGES, ORIFICES, APPUIS, TARAUDAGES, ADXL, DATUMS,
MANUTENTION…), `plaque_centres_trous.csv`, `liste_debit_profiles.csv`, vues `{plaque,plenum,aero,bati,assemblage}_{dessus,face,iso}.svg`,
coupes `*_coupe_y0.svg`, `assemblage_*.png`, `rapport_cao.json`.

**Mises en plan 2D cotées** (`cad/export/plans/*.svg|pdf`, cartouche ISO 2768-mK, A2/A3) : `plan_plaque` (cotation ISO GPS de [04] :
planéité lue dans `performance_targets`, ⊕ Ø0,05 | A | B | C, Ø0,30 ±0,005, datums A/B/C, détail de l'orifice), `plan_vee`, `plan_verin`,
`plan_adxl`, `plan_caisson` (avec détail joint/cornière), `plan_aero` (diffuseur, adaptateur, buse). Les valeurs de planéité suivent le TOML.

## Points ouverts / arbitrages

- Sortie rectangulaire du 9BMC : absente de `docs/research/ventilateurs.md` → boîte 42×30 « à confirmer » (`fan.outlet_mm`).
- Jeu moteur NEMA17 / caisson porté à 3,5 mm (moteur + bouton décalés de 3 mm, accouplement Oldham).
- M10 de l'axe x décalés à y = −100 (hors datums B/C en (±240 ; 0)).
- **Conflit notes 03/05** : les blocs de vé P1/P2 (axe à 28°/152°) débordent de 3–4 mm dans la paroi du caisson (x = 215–221) ; le
  caisson reçoit un dégagement local (voir `caisson`), à arbitrer par la structure.
- Écharpes en deux étages (l'étagère à z = 420 coupe la diagonale unique des notes) ; coupes d'extrémité à ajuster.
- Aspiration déportée devant le bâti (le caisson 320×320×220 ne tient pas dans le cadre) ; portique caméra libre (la plaque dépasse du cadre).
