# Reprise — lot aéraulique / paliers à air (calc/aero)

> Arrêt sur demande du coordinateur (quota), 2026-10-29. Aucun commit git.
> Ce fichier permet de reprendre la mission (points 1 à 10) sans refaire l'exploration.

## (a) Rapport intermédiaire — résultats chiffrés

Légende : **[V]** vérifié (recoupé par deux méthodes ou script final exécuté), **[P]** provisoire.

### 1. Loi débit-pression d'un trou (`orifice.py`, exécuté)
- Modèle de référence : corrélation de Lichtarowicz, Duggins & Markland (1965), tubes
  courts à entrée vive, Re basé sur la vitesse idéale √(2Δp/ρ). Recoupée par un modèle
  analytique (Shah 1978 : développement laminaire + ζ_entrée + énergie de sortie). **[V]**
- d = 0,40 / L = 1,0 mm, Δp = 250 Pa : q = 1,72·10⁻⁶ m³/s, V = 13,7 m/s, Re = 363,
  Cd = 0,67. Dispersion entre modèles à Δp donné : −12 % (Shah, arête vive) à +8 %
  (modèle de la pré-étude, K = 1,5). **[V]**
- Sensibilités à 250 Pa : q ∝ d^2,3 (±0,01 mm → ±5,8 %) ; q ∝ L^−0,16 (±0,05 mm →
  ∓0,8 %) ; entrée conique (pointe 118° du perçage Ø2) +5,9 % ; **bavure obstruant
  10 % / 25 % de l'entrée : −6 % / −18 %** (ébavurage impératif) ; chanfrein de sortie
  0,05 mm : +0,8 % ; perçage borgne Ø2 : 0,8 % de la perte. **[V]**
- Compressibilité : Mach 0,04, facteur de détente 0,999 à 400 Pa → négligeable. **[V]**

### 2. Film d'air (`film.py`, bibliothèque testée)
- Trois modèles implantés et recoupés **[V]** :
  1. axisymétrique homogénéisé **avec correction « de puits »** (Peaceman) — sans elle,
     le modèle de la pré-étude surestime la portance de ~11 % (pic de pression local
     autour de chaque trou : ~60 Pa à h = 100 µm) ;
  2. discret exact (fonction de Green du disque, méthode des images, W et M en forme close) ;
  3. différences finies 2D (Shortley–Weller, singularités soustraites) pour film incliné.
  Écarts : DF ↔ Green 0,04 % sur W, 0,5 % sur M ; homogénéisé ↔ moyenne discrète 0,1 % ;
  k_θ homogénéisé ↔ DF 1–2,5 %.
- Points de fonctionnement baseline (d 0,4 / L 1,0 / hex 5, h = 120 µm, K_c = 0,5) :
  ps = 50 Pa (2 g), 137 Pa (5 g), 304 Pa (10 g). Pré-étude : à corriger (elle surestime h). **[V]**
- **Force latérale d'un palet basculé** : F = −½·W·α (pression normale −W·α, cisaillement
  de Poiseuille +½W·α), soit une pente équivalente α/2. Exact en lubrification. **[V]**
- **Sensibilité au balourd des palets** : k_θ/W ≈ 0,3–0,5 m ⇒ pente équivalente
  ≈ e/(2·k_θ/W) ≈ **1–1,7 µrad par µm de décentrage du centre de gravité**. Un
  décentrage de 0,1 mm vaut 100–170 µrad (≫ budget 50 µrad). **Risque majeur côté palets**
  (équilibrage ≤ 5–10 µm, ou étalonnage et compensation par l'actionneur). **[V]**
- **Crantage** (position du palet dans le réseau), deux mécanismes :
  - basculement induit par l'asymétrie de portance : 50–85 µrad RMS en baseline hex 5 mm ;
    fortement dépendant du rapport D/pas, avec des **« pas magiques »** aux zéros de J₃
    (p = 4πR/(√3·j₃,ₖ) en hex : 2,84 / 3,09 / 3,39 / 3,76 / **4,23** / 4,82 mm) où il
    tombe à 5–10 µrad (d = 0,3 mm). Théorie et calcul concordent. **[V]** (modèle) ;
    robuste au modèle de bord (abrupt/continu) : 8–14 µrad au pas 4,23. **[P]**
  - **poussée de quantité de mouvement du film** (trous proches du bord qui « soufflent »
    sous l'arête ; F_palet = −½ Φ exact par symétrie du film) : 20–100 µrad RMS, croît
    avec ps (∝ q²), peu sensible au pas. Dépend d'une régularisation (δ_min = max(d, 2h)) :
    incertitude facteur ~2. **Domine pour les palets lourds.** **[P]**
  - estimation séparée des jets de bord (β = 0,1) : 5–40 µrad. **[P]** (ordre de grandeur)
  - Un dégagement périphérique de la face du palet **aggrave** le basculement (effet de jupe,
    k_θ plus faible) : piste écartée pour le mécanisme de basculement. **[P]**
  - Total actuel ≈ 25–100 µrad RMS selon masse et géométrie ⇒ **le crantage dépasse le
    budget de pente ; c'est le risque technique n° 1 de la table**. Plaque d'essai à
    prévoir pour mesure.

### 2c/2d. Dynamique (`dynamics.py`, exécuté)
- Restriction en haut : stable pour toutes les masses. f verticale (amortie) 20 / 40 / 48 Hz,
  ζ = 0,85 / 0,36 / 0,19 (2 / 5 / 10 g) ; basculement 34–43 Hz, ζ 0,44–0,10. **[V]**
- Marteau pneumatique : n'apparaît que pour un volume aval par trou ≥ 18× (10 g) à 170×
  (2 g) le volume du perçage Ø2×24 mm ; même la « restriction en bas » resterait stable
  (amortissement d'écrasement dominant aux faibles pressions) mais avec une marge réduite
  pour 10 g. Restriction en haut confirmée. **[V]**
- dh/dps = 3,3 / 0,87 / 0,28 µm/Pa (2 / 5 / 10 g) ⇒ ±0,3 Pa de régulation = ±1 µm. **[V]**
- Amortissement visqueux (Couette) à h = 120 µm : τ = m·h/(μA) = 19 / 47 / 94 s
  (translation et rotation identiques). **[V]**

### 5–6. Réseau et chaîne (`network.py`, exécuté avec la config **baseline** et des bornes
de pression provisoires 45–363 Pa) **[P]**
- 6017 trous (hex 5) : Q = 12,9–46,4 m³/h ; Δp total ventilateur 49–406 Pa.
- Enveloppe ventilateur (marges ×1,15) : **max ≈ 53 m³/h sous 467 Pa ; min ≈ 11 m³/h
  sous 43 Pa** ; rapport de vitesse ≈ 3,2 (courbe réseau non quadratique, exposant 1,3–1,7).
- Chaîne proposée : filtre ePM1 287×287 en caisson 320×320×220, buse col Ø45 (Δp 3–41 Pa),
  centrifuge EC, adaptateur → Ø50, diffuseur conique 2θ = 7° Ø50→Ø80 (L ≈ 245 mm),
  manchon souple L100, conduit Ø80, entrée centrale par le fond avec disque déflecteur Ø200
  à 25 mm, chambre de distribution 62 mm, tôle inox ép. 1 trous Ø2 pas 8 quinconce
  (β = 5,7 %) + nappe média, tranquillisation 80 mm. Rapport Δp tôle / pression
  dynamique amont ≈ 140 ; non-uniformité estimée ≤ 0,03 % (≪ ±1 %). τ plenum 4–11 ms.

## (b) État des fichiers

| Fichier | État |
|---|---|
| `calc/aero/__init__.py` | fini (force BLAS mono-thread : indispensable, sinon ×100 plus lent) |
| `calc/aero/common.py` | fini (config, réseau de trous, style, JSON) |
| `calc/aero/orifice.py` | fini, exécuté (2 figures, `orifice.json`) |
| `calc/aero/film.py` | fini (bibliothèque : axi, Green, DF 2D, crantage) ; pas de `main` |
| `calc/aero/dynamics.py` | fini, exécuté (3 figures, `dynamics.json`) — à relancer après optimize |
| `calc/aero/optimize.py` | fini ; exécution en cours/terminée — voir § (f) |
| `calc/aero/network.py` | fini, exécuté avec la baseline — à relancer après optimize + setpoints |
| `calc/aero/cogging.py` | **non commencé** (cartes de crantage, comparaison pas 4/5/6, équilibre DF complet) |
| `calc/aero/montecarlo.py` | **non commencé** |
| `calc/aero/setpoints.py` | **non commencé** — `results/setpoints.json` actuel n'est PAS de moi (exemple provisoire à 3 points écrit par un autre lot) |
| `calc/aero/jets.py` | **non commencé** |
| `calc/aero/thermal.py` | **non commencé** |
| `calc/aero/run_all.py` | **non commencé** |
| `calc/aero/results/recommended_params.toml` | **non écrit** (valeurs provisoires au § f) |
| `docs/02_aeraulique.md` | **non commencé** |

## (c) Étapes restantes (ordre conseillé)

1. Relire `results/optimization.json` (robustesse : diamètre palet ±0,2 mm, bord abrupt,
   δ_min ×0,5/×2 ; étude de h cible 80–140 µm). Si J reste > 50 µrad, envisager un
   h cible dépendant de la masse (h plus faible pour les lourds : la poussée ∝ q²).
2. `cogging.py` (point 2b) : cartes ΔW/W, Δh, vecteur pente sur la cellule (hex 5 baseline
   et config recommandée) ; tableau pas 4/5/6 hex/carré ; validation de l'équilibre DF
   complet `FD2D.equilibrium` (h0, a, b) contre la linéarisation θ = M/k_θ sur 3 positions ;
   balourd e = 100 µm par DF ; courbe crantage vs pas avec pas magiques.
3. `montecarlo.py` (point 3) : champ aléatoire de d (σ = tol/3, tol ±0,005/0,01/0,015/0,02)
   + L (±0,05) via `film._solve_scaled` (facteur s_i = q(d_i)/q(d0) à ps/2) ; dispersion de
   W (→ Δh) et pente aléatoire (RMS, p95) ; recommander la tolérance (allocation suggérée
   ≤ 10 µrad RMS) et l'étalonnage d'une carte d'efforts parasites.
4. `setpoints.py` (point 4) : ps(m) pour m = 2…10 g pas 0,5 g à h cible (modèle discret
   moyenné sur la cellule), h à ±10 % de ps (`axi_solve_h`), ondulation Δh, bande
   d'incertitude modèle (shah_sharp / coord, K_c 0–1), Q total et Δp ventilateur
   (`network.total_flow`, `fan_total_pressure`), ajustement ps(m) pour le firmware ;
   écrire `results/setpoints.json` avec une clé `envelope` {ps_min_Pa, ps_max_Pa}
   (attendue par `network.py`) et garder la clé `points` [{mass_g, p_Pa}] du format
   provisoire existant (déjà consommé par un autre lot).
5. Relancer `dynamics.py` et `network.py` avec la config recommandée.
6. `jets.py` (point 7) : V, Re des jets, jet laminaire (Schlichting r½ = 5,94x/Re) vs
   turbulent (r½ = 0,094x) → hauteur de coalescence ; vitesse moyenne ascendante Q/A et
   vitesse « quantité de mouvement » V√φ ; entraînement ; traînée des courants d'air
   (½ρC_dDHv² → pente équivalente, exigence v ≤ ~0,02 m/s) ; écran (≈ 120 mm, PMMA/verre,
   couvercle en toile/nid d'abeille).
7. `thermal.py` (point 8) : échauffement ΔT = P_élec/(ρc_pQ) (≈ 0,7–1,8 K), longueur
   d'établissement thermique dans les perçages Ø2 (≈ 5 mm ⇒ air à la température de plaque),
   modèle 1D transitoire dans l'épaisseur (méthode des lignes), gradient stationnaire
   (~0,003 K) et transitoire après échelon de vitesse (~0,02 K), τ = 20–100 min ;
   recommandations (rampes lentes, option vitesse constante + vanne de décharge).
8. `run_all.py` (ordre : orifice → optimize → setpoints → cogging → montecarlo →
   dynamics → network → jets → thermal), vérifier chaque script < 5 min.
9. `docs/02_aeraulique.md` : hypothèses, équations, résultats, figures
   (`../calc/aero/figures/...`), recommandations, limites, « Données pour la CAO »,
   « Données pour le firmware ».
10. `results/recommended_params.toml` définitif (mêmes clés que `params/design.toml`).
    Ne pas modifier `params/design.toml`.

## (d) Commandes

```bash
cd /home/user/Airtable
python3 -m calc.aero.orifice      # ~2 s
python3 -m calc.aero.optimize     # ~3–8 min sur 4 cœurs (plus si CPU partagé)
python3 -m calc.aero.dynamics     # ~8 s
python3 -m calc.aero.network      # ~2 s
```
Pour des essais hors module : `OPENBLAS_NUM_THREADS=1 PYTHONPATH=. python3 script.py`
(sans la variable, les petits `np.linalg.solve` sont ~100× plus lents sur cette machine).

## (e) Valeurs recommandées provisoires

Voir § (f) ; `recommended_params.toml` reste à écrire.

## (f) Résultat de l'optimisation (exécution terminée, 706 s, CPU partagé) **[P]**

- 1150 configurations, 840 admissibles, crantage calculé sur 444.
- Retenu : **d = 0,30 mm, L = 1,20 mm, maille hexagonale, pas 2,94 mm, h cible 100 µm**,
  J (pente équivalente RMS, pire masse) = 45 µrad. Écrit dans `results/recommended_hole.json`
  et `results/optimization.json` (robustesse et étude de h incluses, non encore relues).
- À vérifier à la reprise : ~17 000 trous (coût d'usinage), débit max ≈ 48 m³/h, J reste
  proche du budget de 50 µrad. Comparer avec hex 4,23 mm / d 0,30 (≈ 8 300 trous).
  `dynamics.py` et `network.py` n'ont **pas** été relancés avec cette configuration.
- Lamage provisoire : Ø2,0 mm (perte 0,8 %, Ø1,5 → −1 % de débit).
