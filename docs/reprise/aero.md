# Reprise — lot aéraulique / paliers à air (calc/aero)

> État final au 2026-11-03 : **mission terminée** (points 1 à 10). Aucun commit git ;
> `params/design.toml` non modifié. Note de calcul complète : `docs/02_aeraulique.md`.

## (a) Résultats principaux (détail et figures dans `docs/02_aeraulique.md`)

- **Configuration retenue** (critère d'origine : J minimal, départage débit puis nombre de
  trous ; contrainte « ≤ 8 500 trous » annulée par l'utilisateur) : **hex 5,00 mm, Ø0,30 ±
  0,005, voile L = 1,20 ± 0,05, perçage borgne Ø2**, ≈ 6 000 trous.
- **Entrefer cible dépendant de la masse** : h = 130,2 − 24,8·ln(m[g]) µm borné [80 ; 140]
  (113 µm à 2 g, 90 à 5 g, 80 dès 7,5 g). C'est ce qui fait gagner hex 5 / Ø0,30 :
  J = 32,7 µrad RMS (pire masse 10 g ; crête 57), contre 33–35 pour hex 2,94 (17 300 trous,
  débit ×2,3), 56–65 pour les pas magiques 4,23/4,82, 90 pour la baseline Ø0,40.
- Robustesse (retenu) : Ø palet ±0,2 → 33–36 ; arrondi d'arête 0,2/0,5 mm → 34/40 ; bord
  abrupt 41 ; δ_min ×0,5/×2 → 62/27 µrad. Incertitude principale = terme de quantité de mouvement.
- Pas magiques : basculement 24 µrad nominal (4,23, 10 g) mais 13–36 µrad pour Ø ±0,2 mm
  (minimum étroit) ; total 54–67 µrad. Informatif seulement.
- Monte-Carlo : Ø ±0,005 → 5–8,5 µrad RMS ; ±0,010 → 10–16 ; trou bouché 136–159 µrad ;
  bavure 25 % → 20–29 µrad.
- Consignes : ps 65,5 Pa (2 g) → 265 Pa (10 g) ; enveloppe 57–297 Pa ; Q 6,5–20 m³/h ;
  spécification ventilateur (marges ×1,15) max ≈ 23 m³/h / ≈ 375 Pa, min ≈ 5,7 m³/h / ≈ 53 Pa
  (valeurs exactes : `results/network.json`, `fan_spec`).
- 9BMC24P2G001 validé au point max (≈ 42 % PWM, marge ×4,6) ; point min inaccessible par la
  vitesse ⇒ **vanne de décharge à deux états** (Ø ≈ 39 mm, commutation ≈ 238 Pa). Alternative
  9BMB24P2G01 mieux adaptée (vitesse mini à mesurer).
- Dynamique stable (V critique ≥ 20× perçage) ; thermique : gradient ≤ 5 mK, τ ≈ 14 min ;
  courants d'air admissibles 17 mm/s (2 g) ⇒ écran 120 mm.
- Compensation logicielle (§ 11 de la note) : crantage périodique de moyenne nulle,
  pente, balourd, Couette = déterministes ; dispersion des orifices, courants d'air,
  colmatage = aléatoires.

## (b) État des fichiers

| Fichier | État |
|---|---|
| `calc/aero/common.py` | fini ; + `h_target_for(m)` (loi h(m) de setpoints.json) |
| `calc/aero/orifice.py`, `film.py` | finis (inchangés) |
| `calc/aero/optimize.py` | refondu : h optimal par masse (étapes B/C/D), D_cb selon le pas, < 5 min (≈ 190 s) |
| `calc/aero/setpoints.py` | fini : loi h(m), table, enveloppe → `results/setpoints.json` (format firmware conservé, 12 points) |
| `calc/aero/cogging.py` | fini : cartes, balayage du pas, comparaison, robustesse, validation DF |
| `calc/aero/montecarlo.py` | fini |
| `calc/aero/dynamics.py` | mis à jour (h(m)) |
| `calc/aero/network.py` | mis à jour : buse Ø30, validation 9BMC, vanne de décharge, alternative 9BMB |
| `calc/aero/jets.py`, `thermal.py` | finis |
| `calc/aero/run_all.py` | fini (≈ 5 min ; `--skip-optimize` possible) ; journal `results/run_all.json` |
| `calc/aero/results/recommended_params.toml` | écrit |
| `docs/02_aeraulique.md` | écrit (CAO, firmware, compensation logicielle, risques) |

## (c) Étapes restantes (hors lot ou vague 2)

1. Coordinateur : fusionner `recommended_params.toml` dans `params/design.toml`
   (orifice_d_mm 0,30, orifice_length_mm 1,2, orifice_tol_mm 0,005, p_plenum 57–297 Pa,
   fan, baffle_open_area 0,057).
2. Décision utilisateur : compensation logicielle du crantage acceptée ou non.
3. Plaque d'essai 100 × 100 (pas 5 / Ø0,30) : Cd réel, table ps(m), crantage mesuré.
4. Mesurer la vitesse mini des 9BMC/9BMB sous 20 % PWM ; choisir la vanne de décharge.
5. Lot firmware : hystérésis de la vanne, table de 12 points (format inchangé).

## (d) Commandes

```bash
cd /home/user/Airtable
python3 -m calc.aero.run_all               # chaîne complète ≈ 5 min (4 cœurs)
python3 -m calc.aero.run_all --skip-optimize
python3 -m calc.aero.optimize              # ≈ 190 s
python3 -m calc.aero.setpoints             # ≈ 12 s ; cogging ≈ 75 s ; les autres < 10 s
```
`OPENBLAS_NUM_THREADS=1` est forcé par `calc/aero/__init__.py` (sinon ×100 plus lent).
