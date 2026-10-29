# Reprise CAO (phase 1, interrompue sur quota) — aucun commit git

## Fait
- 87 pièces valides, 0 interférence (68 paires testées par booléen), masse totale ~70 kg
  (plaque complète analytique 16,81 kg ; plenum 16,1 ; bâti 27,6 ; options 6,3 ; nivellement 2,5 ; aéro 0,6).
- 5739 trous (hex 5 mm) ; CSV + DXF vérifiés. Génération ~25 s sans SVG, ~55 s avec SVG.
- Exports dans cad/export/ : STEP/STL pièces, barres/, assemblage.step, SVG+PNG, DXF, CSV,
  liste_debit_profiles.csv, rapport_cao.json (dernier run : `--full` abandonné à 600 s).
- Essai de surcharges (`--set`, `--out`) OK : tout suit les paramètres.

## État des fichiers cad/
- Finis : common.py, parts/{plate,plenum,aero,leveling,frame}.py, assembly.py, README.md.
- build_all.py : fonctionnel, mais les derniers ajouts (2 contrôles « trous », `tole_perforee`,
  `--out`, masse_cad plaque complète) n'ont PAS été relancés en entier (syntaxe vérifiée seulement).
- Plaque complète `--full` : NON validée dans build_all (>600 s avec 2 booléens successifs, run chargé).
  Mesures isolées : 294 s (2 coupes, valide, masse 16,81 kg) ; 226 s avec outil étagé unique
  + `cadquery.occ_impl.shapes.cut` (OBB) — export STEP/STL non mesuré, essai interrompu.

## Clés DEFAULTS à figer (cad/common.py)
plate.* (edge_band, witness_holes, pocket/insert/ball, tap_*, pin_*), support.* (radius_mm,
angles_deg, insert_types, roles, column_d), plenum.* (profile, panel_*, bride_t, membrane_*,
ring_*, baffle_*, column_hole_d), leveling.*, fan.* (size, outlet, offset, standoff, mass),
aero.* (manchon, adapter, diffuser_*, bell_*, filter_*), frame.* (footprint, table_height, foot_*),
platine.*, screen.*, gantry.*.

## Étapes restantes
1. Remplacer la coupe de `plate.build_plate(mode="full")` par l'outil étagé unique + `shapes.cut`
   (OBB), mesurer build + STEP + STL, relancer `--full`, noter le temps dans README.
2. Relancer `python3 -m cad.build_all` complet et vérifier que les nouveaux contrôles passent.
3. Phase 2 : intégrer cotes figées (appuis, nivellement, bâti/plenum/diffuseur) ; passage étanche
   des colonnes, vis de bride, tasseaux de tôle, masses profilés sourcées (docs/research/).
4. Contrôler que le plenum (cadre 45x45 + coins) reste compatible avec la plaque 520.

## Commandes
    python3 -m cad.build_all [--no-svg] [--full --full-timeout 900] [--out DIR] [--set sec.cle=val]
    python3 -m cad.assembly ; python3 -m cad.parts.plate
