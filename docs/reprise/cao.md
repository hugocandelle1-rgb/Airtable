# Reprise CAO (phase 2 interrompue sur quota) — aucun commit, TOML inchangé

## État : phase 2 À MOITIÉ — `python3 -m cad.build_all` NE FONCTIONNE PLUS (frame/assembly/build_all périmés)

### Fini et testé (pièces valides, 0 interférence dans leur groupe)
- `cad/common.py` : DEFAULTS phase 2 (chaque cote cite sa note [02]/[03]/[04]/[05]), `support_points`
  (3 vés du TOML), `vee_geometry`, `levels(P)` (z_CAD = z_notes − 900 ; cadre, appuis, caisson, chaîne, platine).
  Profilés 45x45 / 45x90 / 40x40 / 40x80 et `bar(...)` conservés (inchangés).
- `cad/parts/plate.py` : plaque 520x520x35, 5935 trous (outil étagé Ø2 / cône 118° / Ø0,30, comb + `shapes.cut` OBB),
  sièges de billes Ø25,4, datums B/C, 32 M5, 12 M4 ADXL, 4 M10 (conflit [04] : x décalés à y=−100), chanfreins ;
  masse plaque complète ≈ 23,4 kg (notes : 23,5). Billes Ø25,4. CSV/DXF mis à jour (non rejoués).
- `cad/parts/plenum.py` : caisson suspendu 430 / parois 6, joint EPDM, cornière, tôle Ø2 pas 8 (5,5 %), média, déflecteur. Membrane supprimée.
- `cad/parts/leveling.py` : blocs de vé + rouleaux, vérins à coin (boîtier, coin 1:5, tête, vis, moteur, bouton),
  rehausse P0, étriers + patins PTFE, 4 embases ADXL355 (socle, plateau, billes, carte, capot).
- `cad/parts/aero.py` : ventilateur 9BMC, manchon L100, adaptateur, diffuseur Ø50→Ø80 L245, conduit + vanne,
  aspiration déportée (caisson 320x220x320, filtre, buse Ø30, tube). Sortie du ventilateur (42x30) NON documentée.

### Non fait / périmé
- `cad/parts/frame.py` : ANCIEN bâti (phase 1), incompatible avec le nouveau `levels` → à réécrire :
  montants 45x90 en (±250 ; ±227,5), cadre 45x90 (x-poutres ±227,5, y-poutres ±182,5), ceintures 45x45
  (z=150, 420 → CAD −750, −480), écharpes en 2 étages (rear/gauche/droite, mitrées par intersection), 4 pieds Ø80,
  platine [200x440] + 4 plots, traverses à y=±200, écran PMMA 5 mm (parois à 0,5 du bord de zone, |x|,|y|≤179,5),
  couvercle nid d'abeille, portique libre à x=±325.
- `assembly.py`, `build_all.py` : à adapter (anciens appels plate/plenum, nouvelle liste de modules, groupes `appuis`, `capteurs`).
- Plaque `--full` : mesure en cours interrompue (outil étagé + OBB : coupe ≈ 226 s en phase 1) ; STEP/STL non mesurés.
- Mises en plan 2D cotées : NON COMMENCÉES (prévu : `cad/drafting.py` matplotlib SVG+PDF, A2 plaque/caisson, A3 autres,
  cartouche ISO 2768-mK, GD&T de [04] §7).
- Contrôles masses vs notes, `rapport_cao.json`, `cad/README.md` : à refaire après le bâti.

## Étapes restantes (ordre)
1. Réécrire `frame.py` ; adapter `assembly.py`/`build_all.py` ; lancer `python3 -m cad.build_all --no-svg` ; corriger interférences.
2. Rejouer `--full` (timeout 900 s) et noter les temps ; mettre à jour README.
3. Écrire `cad/drafting.py` + `cad/drawings.py` (plaque, vé, vérin, embase ADXL, caisson/cornière, aéro) ; exports PDF/SVG.
4. Contrôles (isValid, interférences, masses vs notes : plaque 23,5 kg), `rapport_cao.json`, mise à jour de ce fichier.
5. Points à arbitrer : jeu moteur NEMA/caisson 0,5 mm, M10 vs datums, sortie du 9BMC, implantation du caisson d'aspiration.

## Commandes
    python3 -m cad.parts.plate          # plaque légère (OK)
    python3 -c "from cad.common import *; from cad.parts import plenum,leveling,aero; P=get_params(); print(len(plenum.build(P)+leveling.build(P)+aero.build(P)))"
    python3 -m cad.build_all --no-svg   # CASSÉ tant que frame/assembly/build_all ne sont pas adaptés
