# CAO paramétrique — table à coussin d'air

Modèles CadQuery 2.8 pilotés par `params/design.toml` ; les cotes absentes du TOML
viennent du bloc `DEFAULTS` de `cad/common.py` (à figer en phase 2). Aucun affichage
graphique : tout sort en fichiers dans `cad/export/`.

## Régénérer

Depuis la racine du dépôt :

    python3 -m cad.build_all                 # ~1 min : STEP, STL, SVG, DXF, CSV, rapport
    python3 -m cad.build_all --no-svg        # ~25 s (sans les vues)
    python3 -m cad.build_all --full          # + plaque complète (5739 trous), délai max 600 s
    python3 -m cad.build_all --set plate.thickness_mm=30 --set support.radius_mm=150
    python3 -m cad.assembly                  # assemblage seul (cad/export/assemblage.step)
    python3 -m cad.parts.plate               # test rapide de la plaque

`--set section.cle=valeur` surcharge un paramètre sans toucher au TOML (essais de phase 2).
La plaque complète est construite dans un sous-processus : au-delà de `--full-timeout`
elle est abandonnée, documentée dans le rapport, et le modèle léger est conservé.
`cad/export/*_full.*` est ignoré par git.

## Repère et conventions

- **Origine = centre de la face supérieure de la plaque, Z vers le haut**, X/Y dans le plan.
  Dessous de plaque : z = −épaisseur ; sol : z = −`frame.table_height_mm` (−900).
- Unités : mm et kg. Toutes les pièces sont construites directement en coordonnées
  globales (pas de contraintes d'assemblage) : les positions sont exactes et les
  interférences se testent par intersection booléenne.
- Les cotes verticales et positions dérivées sont calculées **une seule fois** dans
  `common.levels(P)` ; chaque module les lit (changer une cote déplace tout ce qui en dépend).
- Appuis : angle mesuré depuis +X, rayon `support.radius_mm` (ou `support.radius_ratio` × demi-côté
  si le TOML le renseigne > 0), type d'insert `cone` / `ve` / `plat` (couplage de Kelvin) et rôle
  `pivot` / `verin`.
- Les profilés sont de simples enveloppes à rainures en T ; leur **masse vient de la masse
  linéique catalogue ESTIMÉE** (`common.PROFILES[...]["kg_m"]`, non sourcée, à confirmer dans
  `docs/research/`), pas du volume CAO.

## Pièces

| Module | Pièces |
|---|---|
| `parts/plate.py` | plaque 520×520×25 (logements d'inserts, taraudages M5 de la bride, 2 pions, trous), pastilles d'appui cône/vé/plat, billes de Kelvin ; `hole_centers(P)`, `export_csv`, `export_dxf` |
| `parts/plenum.py` | 4 montants + 8 traverses (profilé 45×45), 4 panneaux + fond (entrée centrale, 3 passages de colonnes), tôle perforée, bride supérieure, membrane EPDM en U, bride de serrage sous la plaque |
| `parts/aero.py` | ventilateur (enveloppe 97×97×33, sortie 30×26), cale, manchon souple, adaptateur rectangle→rond, diffuseur conique, buse d'entrée (bellmouth) + carter, filtre |
| `parts/leveling.py` | 3 colonnes Ø16 traversant le plenum, 1 pivot fixe, 2 vérins, 2 moteurs NEMA17 + accouplements (enveloppes) |
| `parts/frame.py` | 4 montants, cadres haut / bas / supérieur, traverses porteuses du plenum, 3 consoles d'appui, 4 pieds réglables, platine ventilateur + 4 plots + 2 traverses, écran PMMA amovible, option portique + caméra |
| `common.py` | `DEFAULTS`, `get_params`, `levels`, bibliothèque de profilés (`PROFILES`, `profile`, `bar`, `cut_list`), `PartSpec`, interférences, exports SVG |
| `assembly.py` | `build_parts(P)` (87 pièces) et `cq.Assembly` coloré |
| `build_all.py` | tous les exports + `rapport_cao.json` |

Bibliothèque de profilés : `40x40` (rainure 8), `45x45` (rainure 10), `40x80`, `45x90` ;
`bar(key, axis, start, length, tall=True)` place une barre selon X, Y ou Z ;
`cut_list(parts)` regroupe par (section, longueur).

## Sorties (`cad/export/`)

- `assemblage.step`, `pieces/*.step`, `pieces/*.stl` (plaque, brides, adaptateur, diffuseur,
  buse, platine : pièces imprimables ou usinables), `barres/profile_*_L*.step` (une barre par coupe) ;
- `plaque_trous.dxf` (calques CONTOUR, ZONE_PERCEE, TROUS_BORGNES Ø2, ORIFICES Ø0,4, APPUIS,
  TARAUDAGES, PIONS, AXES ; vue de dessus) et `plaque_centres_trous.csv` (index, x, y en mm) ;
- `liste_debit_profiles.csv` (section, longueur de coupe, quantité, masse estimée) ;
- vues SVG `{plaque,plenum,aero,bati,assemblage}_{dessus,face,iso}.svg`, `plaque_dessous.svg`,
  coupes `{plenum,assemblage}_coupe_y0.svg`, et PNG de contrôle `assemblage_*.png` (matplotlib) ;
- `rapport_cao.json` : masses, volumes, boîtes englobantes, nombre de trous, validité,
  interférences, temps, cotes dérivées, clés `DEFAULTS` utilisées.

## Plaque : modèle léger et modèle complet

- **Léger** (assemblage, STEP/STL par défaut) : plaque avec logements, taraudages, pions et 19 trous
  témoins ; sa masse affichée est celle du plein. Le rapport donne la masse complète analytique
  (`masse_plaque_complete_analytique_kg`) qui sert au total d'assemblage.
- **Complet** (`--full`) : un seul booléen composé (peigne de 5739 cylindres Ø2 + peigne d'orifices Ø0,4),
  validé ; la durée mesurée est dans `rapport_cao.json` (`plaque_complete`).
- Pour l'usinage on utilise le DXF/CSV (centres exacts), pas le STEP complet.

## Points ouverts (phase 2)

Les valeurs de `DEFAULTS` marquées « à figer » : schéma d'appui (rayon, angles, types, rôles),
mécanisme de nivellement (vérins, hauteurs, motorisation), cotes bâti / plenum / diffuseur,
choix du ventilateur et de la filtration, matières de panneaux, boîtier de passage étanche des
colonnes (non modélisé), vis de la bride et tasseaux de la tôle (non modélisés).
