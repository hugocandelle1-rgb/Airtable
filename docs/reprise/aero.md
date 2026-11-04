# Reprise — lot aéraulique (calc/aero) — état au 2026-11-04

Aucun commit. `params/design.toml` est intact : la fusion V3.1 (hex 5, Ø0,30, L1,2,
plaque 35 mm) a été faite par le coordinateur. La note complète est
`docs/02_aeraulique.md` ; son § 11 a été réécrit le 2026-11-04.

## (a) Résultats acquis
- Configuration : hex 5,00 / Ø0,30 ± 0,005 / L1,2 / perçage Ø2. Loi d'entrefer
  h(m) = 130,2 − 24,8 ln m, bornée à [80 ; 140] µm.
  - Crantage : 25–33 µrad RMS, crête 50–67 µrad à 10 g. [V modèle]
  - Ventilateur : 9BMC validé au point max ; vanne de décharge à deux états requise. [V]
- **Décisions utilisateur.** La table caractérise des actionneurs électrostatiques
  radiaux, sans aucune compensation en ligne. Les forces parasites sont donc des erreurs
  de mesure. Piste « piégeage volontaire » ANNULÉE.
- Champ de crantage (`drift_sim.py`) [P, confiance moyenne] :
  - Il est **conservatif à 95–97 %** et de moyenne nulle : pas de dérive par circulation.
  - Ses puits sont peu profonds : barrière 0,3–0,5 µJ/kg, vitesse de capture 0,8–1 mm/s,
    période 6,6 s, Q = 16–60.
  - Maintien statique : 43 / 30 / 34 µrad, pire direction, pour 2 / 5 / 10 g.
  - Re-capture d'un palet lâché à ≥ 1 mm/s : seulement si θ ≤ 0–5 µrad. Sinon il glisse à
    g·θ·τ, soit 0,17 / 0,35 / 0,61 mm/s par µrad.
  - **Correction** : le « seuil 5–15 µrad » du 2026-11-03 est un seuil de re-capture, pas
    un seuil de maintien.
- Bilan des forces parasites (`parasitic.py`) :
  - Total RSS : 0,69 / 1,78 / 4,0 µN, soit 0,35–0,40 mm/s².
  - Le crantage et la pente de plaque (30 µrad) dominent.
  - Rapport signal/parasite de 10 pour F_act ≥ 7 / 18 / 40 µN.
- Erreur de trajectoire :
  - Crantage : erreur bornée de 1–4 mm à faible F_act. Elle tombe sous 0,5 mm dès
    F_act ≥ 100 µN.
  - Pente : erreur en ½ g θ T², soit 14 mm en 10 s pour 30 µrad.
- Correction a posteriori par carte étalonnée : gain ≈ 2 (41 → 21 µrad à 10 g) avec un
  recalage du réseau à 0,1 mm. Avec des mires à 0,05 mm : ≈ 12–14 µrad.
- Levier de réduction : **Ø0,25 / L1,0 / hex 5** donne un crantage de −34 % (22 / 38 µrad
  à 10 g, crête < 50 µrad pour toutes les masses, ps 310 Pa). La limite d ≥ 0,30 est à
  lever avec l'usineur. h = 70 µm ne gagne que 8 %. Le pas et la maille sont sans levier.

## (b) État des fichiers
| Fichier | État |
|---|---|
| `calc/aero/trap.py` | nouveau : carte périodique (Fourier + interpolation), Helmholtz, puits, seuil statique |
| `calc/aero/drift_sim.py` | réécrit, ≈ 10 s : maintien, capture, bruit → `results/drift_sim.json`, figures `derive_*.png` |
| `calc/aero/parasitic.py` | nouveau, ≈ 8 s : bilan µN / mm/s², erreur de trajectoire vs F_act et T, correction, leviers |
| `calc/aero/run_all.py` | + drift_sim et parasitic ; chaîne complète 248 s, toutes les étapes < 5 min |
| `calc/aero/results/recommended_params.toml` | + `[aero.passive]`, `[aero.option_d025]` |
| `docs/02_aeraulique.md` | § 11 « Fonctionnement passif sans compensation » ; § 0, 3, 13, 14, 15 et historique mis à jour |
| figures obsolètes | `derive_potentiel_trajectoires.png`, `derive_mitigation_10g.png` supprimées (ancienne version) |

## (c) Étapes restantes
1. Plaque d'essai : deux zones Ø0,30 et Ø0,25. Y mesurer Cd, ps(m) et le crantage réel
   (oscillations libres, dérive) pour recaler le terme de quantité de mouvement.
2. Arbitrage du coordinateur et de l'utilisateur :
   - Ø0,25 ou non : passer la clé `[aero.option_d025]` dans design.toml si oui, puis
     relancer `run_all` (optimize borne d ≥ 0,30 : modifier `D_MIN`) ;
   - pente de plaque ≤ 10 µrad ;
   - mires de recalage du réseau en CAO.
3. Réviser le cahier des charges : y exprimer l'exigence en force parasite (µN) ou en
   erreur de trajectoire, plutôt qu'en pente seule.
4. Monte-Carlo de dispersion à Ø0,25 (non fait ; estimé à ≈ 10 µrad RMS).

## (d) Commandes
```bash
cd /home/user/Airtable
python3 -m calc.aero.run_all               # ≈ 4–5 min (optimize ≈ 100–190 s)
python3 -m calc.aero.run_all --skip-optimize
python3 -m calc.aero.drift_sim             # ≈ 10 s
python3 -m calc.aero.parasitic             # ≈ 8 s
```
`OPENBLAS_NUM_THREADS=1` est forcé par `calc/aero/__init__.py`.
