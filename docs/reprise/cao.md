# Reprise CAO (phase 2 — état au 2026-11-04) — aucun commit, params/design.toml inchangé

## Fait (`python3 -m cad.build_all` fonctionne : 46 s avec SVG et plans, 12 s sans)
- 117 pièces valides, **0 interférence** (84 paires testées), masse totale 84,5 kg (plaque complète analytique 23,43 kg ;
  notes 23,5). 5935 trous = notes. Contrôles du rapport (`cad/export/rapport_cao.json`) tous vrais : validité,
  interférences, dessus de plaque à 900 du sol, empilement vérin 44,95 (≈45), jeu caisson/cadre 6,5, jeu moteur/caisson ≥ 3 mm.
- Modules : `common.py` (DEFAULTS sourcés [02]-[05], `levels`), `parts/{plate,plenum,leveling,aero,frame}.py`,
  `assembly.py`, `build_all.py`, `drafting.py` (moteur de plan), `drawings.py` (6 plans), `README.md` à jour.
- Plans 2D cotés SVG+PDF dans `cad/export/plans/` : plaque (A2, cotation ISO GPS de [04], planéité lue dans le TOML), vé/rouleaux,
  vérin à coin, embase ADXL355, caisson + détail joint/cornière, diffuseur/adaptateur/buse (A3) ; cartouche ISO 2768-mK.
- Arbitrages appliqués : sortie 9BMC non documentée (`docs/research/ventilateurs.md`) → boîte 42×30 « à confirmer » ;
  moteur NEMA17 + bouton décalés de 3 mm (jeu 3,5) ; M10 de l'axe x à y = −100.

## Plaque `--full`
Outil étagé unique + `occ_impl.shapes.cut` (OBB). Phase 1 : coupe ≈ 226–294 s. Dans `build_all`, la version précédente (coupe + STEP
dans le même délai) a été abandonnée à 600 s puis 900 s ; le worker envoie maintenant un message par étape (coupe, STL, STEP).
Voir le champ `plaque_complete` de `cad/export/rapport_cao.json` ou de la dernière exécution `--full` (état noté dans le README / ci-dessous).

## Points ouverts à arbitrer (structure)
1. **Conflit notes 03/05** : les blocs de vé P1/P2 débordent de 3–4 mm dans la paroi du caisson (215–221) ; dégagement local dans `caisson`
   (paroi ramenée à ~1 mm sur ~50 mm de long). Option : décaler les vés, ou une cornière de renfort.
2. Écharpes en deux étages (étagère z = 420) ; coupes d'extrémité mitrées par intersection (à ajuster en atelier).
3. Caisson d'aspiration 320×220×320 déporté devant le bâti (ne tient pas dans le cadre) ; portique caméra libre.
4. Tolérances de planéité/parallélisme des plans vé, vérin, embase, caisson : non chiffrées dans les notes (valeurs « à valider »).
5. Masse des profilés = masse linéique estimée non sourcée (docs/research/profiles_alu_et_mecanique.md à confirmer).

## Étapes restantes
- Valider/ajuster les plans avec le sous-traitant (hachures de coupe, dimensions complémentaires) ; plan du bloc de vé P0 (rehausse).
- Rejouer `python3 -m cad.build_all --full --full-timeout 1500` hors charge pour consigner les temps coupe/STL/STEP.
- Si le TOML resserre la planéité plaque : relancer `python3 -m cad.drawings` (les plans la relisent).

## Commandes
    python3 -m cad.build_all [--no-svg] [--no-plans] [--full --full-timeout 1500] [--out DIR] [--set sec.cle=val]
    python3 -m cad.drawings          # plans seuls
    python3 -m cad.parts.plate       # test plaque
