# Reprise — lot aéraulique (calc/aero) — arrêt propre (quota), 2026-11-03

Aucun commit. `params/design.toml` non modifié par ce lot (fusion V3.1 faite par le coordinateur :
hex 5, Ø0,30, L1,2, plaque 35 mm). Note complète : `docs/02_aeraulique.md` (état antérieur au
complément « dérive passive » : sa section 11 « Compensation logicielle » est à requalifier).

## (a) Résultats acquis
- Configuration : hex 5,00 / Ø0,30 ± 0,005 / L1,2 / perçage Ø2 ; h(m) = 130,2 − 24,8 ln m, [80 ; 140] µm.
  Crantage 25–34 µrad RMS, crête 48–61 µrad (10 g). `run_all` passe (303 s). [V modèle]
- Ventilateur 9BMC validé au point max ; vanne de décharge à deux états requise. [V]

## (b) Dérive passive (`drift_sim.py`, exécuté une fois, 465 s) — confiance moyenne [P]
Hypothèses : champ de crantage du modèle nominal (δ_min ×1), périodisé par Fourier ; Couette seul
(τ = m h/μA = 18 / 35 / 63 s pour 2 / 5 / 10 g) ; pente uniforme θ0 ; bruit OU σ = 5 µrad, t_c = 2 s.
- Champ **à 95–97 % conservatif** (rotationnel 3–5 %) ⇒ potentiel, piégeage possible, pas de dérive
  moyenne à θ0 = 0 (vérifié : v ≈ 0).
- Puits **peu profonds** : barrière ⇒ vitesse de capture 1,0 / 0,87 / 0,77 mm/s ; **seuil de
  dépiégeage θ_dep ≈ 15 µrad (2 g), 5–10 µrad (5 et 10 g)** (résolution 5 µrad), bien inférieur à
  la crête (50–68 µrad) : l'échappement passe par des cols.
- Au-delà du seuil : régime glissant, v ≈ g θ0 τ (crantage ≈ sans effet) : 0,87 / 1,73 / 3,1 mm/s
  pour 5 µrad. Bistabilité (piégé/glissant) près du seuil, faible amortissement.
- Palet lancé (θ0 = 0) : parcourt ≈ v0 τ avant capture (10 mm/s → 17–58 cm ; 1 mm/s → 1–4 cm) ;
  stabilisation en plusieurs τ (minutes).
- Bruit 5 µrad (courants d'air) : 2 g reste piégé (96 %, errance 0,5 mm) ; 10 g dépiégé (8 %
  piégés, errance ≈ 20 mm).
- Critère « dérive ≤ 0,3 mm/s » en glissement ⇒ θ_eff ≤ 1,7 / 0,9 / 0,5 µrad (2 / 5 / 10 g) :
  **hors d'atteinte** (budget actuel 50 µrad). Seule voie passive : rester piégé ⇒ pente totale
  (réglage + planéité locale + balourd + courants d'air) ≤ ≈ 5 µrad (10 g) à 15 µrad (2 g).
- Force de décrochage à vaincre par les actionneurs : 0,29 / 0,25 / 0,49 µN (= m g θ_dep),
  négligeable ; le crantage **aide** (seul mécanisme de maintien) plus qu'il ne gêne.
- Mitigation crête 10 g (cellule 16×16) : h 70 → 59 µrad, 90 → 75, 100 → 103 ; arrondi 0,2 mm → 59 ;
  hex 2,94 → 54 ; aucune option ne passe sous 50 µrad dans les contraintes (h ≥ 80, d ≥ 0,3).
  En fonctionnement passif, réduire le crantage **réduit** le piégeage : ne pas mitiger.

## (c) État des fichiers
| Fichier | État |
|---|---|
| `calc/aero/drift_sim.py` | fonctionnel mais **465 s (> 5 min)** ; résultats dans `results/drift_sim.json` + 3 figures `derive_*.png` |
| autres scripts `calc/aero/*.py`, `run_all.py` | finis ; `drift_sim` pas encore dans `run_all` |
| `docs/02_aeraulique.md` | section « Fonctionnement passif sans compensation » **non écrite** ; § 11 à requalifier |

## (d) Étapes restantes
1. Accélérer `drift_sim.py` (< 5 min) : `keep=1e-2` dans `PeriodicField` (526 → ~100 modes),
   THETA0 = (0, 2.5, 5, 7.5, 10, 15, 20, 30, 50), T = max(6τ, 120 s), illustration `drift_th30` ;
   affiner le seuil (pas 1 µrad) ; ajouter variante « piégeage renforcé » (Ø0,40/L1,0, 10 g) et
   variantes δ_min ×0,5/×2 (le seuil dépend du modèle). L'ajouter à `run_all.py`.
2. Écrire la section « Fonctionnement passif sans compensation » dans `docs/02_aeraulique.md`
   (résultats § b), requalifier le § 11 (compensation exclue : garder seulement la nature
   déterministe/aléatoire), mettre à jour la synthèse et les risques.
3. Remonter au coordinateur : le critère passif impose ≈ 5 µrad de pente totale (×10 plus
   sévère que le budget) ou un mécanisme de maintien (piégeage renforcé, amortissement accru).

## (e) Commandes
```bash
cd /home/user/Airtable
python3 -m calc.aero.run_all            # ≈ 5 min
python3 -m calc.aero.drift_sim          # ≈ 8 min avant accélération
```
