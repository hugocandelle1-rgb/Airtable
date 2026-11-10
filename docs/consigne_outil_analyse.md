# Consigne de développement — Outil d'analyse des essais de dérive de palet sur table à air

> **Destinataire :** le développeur ou l'agent IA chargé de développer l'outil, dans le dépôt qui
> contient les données d'acquisition et les modèles d'analyse existants.
>
> **Règle n° 1 : ne rien inventer.** Toute information absente de cette consigne ou des données
> (format de colonne, unité, convention de signe, valeur d'un paramètre physique, nommage des
> dossiers…) fait l'objet d'une **question à l'utilisateur** avant d'être codée. Les valeurs
> marquées « proposé » sont des valeurs par défaut configurables, à confirmer ; elles ne doivent
> jamais être présentées comme des données mesurées.

---

## 1. Objet

Développer un outil Python d'analyse, de qualité scientifique et ingénieur, qui transforme les
trajectoires brutes de palets sur une table à air en **métriques physiques exploitables**,
avec leurs incertitudes, pour :

1. quantifier la dérive d'un palet mis en flottement ;
2. séparer ce qui relève du **décollage** (kick initial) de ce qui relève du **vol établi** ;
3. séparer, dans la dérive établie, la part **gravitaire** (inclinaison, planéité) de la part
   **aérodynamique** ;
4. étalonner l'effet de l'inclinaison et déterminer l'**inclinaison résiduelle vraie**, telle que
   le palet la voit ;
5. préparer la comparaison des futures configurations de palet (concavité, masse, vitesse des
   turbines) à partir d'une référence « palet plat ».

## 2. Contexte physique (à lire avant de coder)

- Sur coussin d'air, l'amortissement est quasi nul : temps caractéristique τ = m/c de l'ordre
  de la minute pour un palet plat de quelques grammes. Sur la fenêtre d'observation, le mouvement
  est **quasi balistique** : r(t) = r₀ + v₀·t + ½·a·t².
- Une inclinaison θ donne a = g·θ : 0,1 mrad → ≈ 1 mm/s² → ≈ 5 cm en 10 s. Le palet est
  un inclinomètre bien plus sensible que l'accéléromètre de la table.
- Modèle de travail en vol établi, sur chaque axe :

  **a = g·θ_eff(position) + F_air(position)/m**

  La part gravitaire est indépendante de la masse ; la part aérodynamique varie en 1/m.
- **Protocole de chaque essai :** le palet est posé à sa position initiale, **puis** les turbines
  sont allumées. Le palet, tenu par le frottement, décolle quand la portance dépasse son poids. Ce
  décollage est souvent asymétrique et produit un **kick initial**, que l'utilisateur pense observer
  surtout depuis le bord de la plaque. Chaque essai contient donc deux régimes à analyser
  séparément.

## 3. Plan d'expérience à analyser (campagne actuelle)

| Facteur | Niveaux | Remarque |
|---|---|---|
| Position initiale | 2 : centre, bord | coordonnées exactes à fournir (Q3, Q6) |
| Inclinaison du plan | 3 : droit, incliné 1, incliné 2 | **θx et θy connus précisément** pour chacune des 3 configurations (valeurs, unité et signe : Q3, Q4) |
| Masse du palet | 2 | palets **plats**, sans concavité ; valeurs : Q3 |
| Répétitions | 3 | |
| Vitesse des turbines | fixe | |

Plan factoriel complet : 2 × 3 × 2 × 3 = **36 essais**. L'outil doit cependant accepter un nombre
quelconque de niveaux et de facteurs (concavité, vitesse des turbines, orientation du palet…),
pour servir aux campagnes suivantes sans réécriture.

## 4. Données d'entrée (connu / à préciser)

**Connu :** un fichier CSV par échantillon (essai). Les échantillons sont rangés dans des
dossiers, un par expérience.

**À préciser avant de coder** (voir § 12) : noms et unités des colonnes, séparateur et
séparateur décimal, base de temps et fréquence d'acquisition, présence de ω(t) et de
l'accéléromètre dans chaque CSV, encodage des métadonnées (masse, position, inclinaison,
répétition) dans les noms de dossiers ou de fichiers, unité des positions (px ou mm), repère.

**Exigences de lecture :**

- La correspondance entre colonnes et grandeurs est décrite dans un **fichier de configuration**
  (par exemple `config/data_mapping.toml`), jamais en dur dans le code.
- Les métadonnées de chaque essai sont lues de manière déterministe (nom de dossier ou de fichier,
  ou table récapitulative) et **consolidées dans un manifeste** `manifest.csv` : une ligne par
  essai, avec chemin, empreinte SHA-256, facteurs, et statut de validation.
- Une commande `inventory` produit ce manifeste et un rapport d'inventaire **avant toute
  analyse** : essais trouvés, cellules du plan incomplètes, doublons, fichiers illisibles.
- **Aucun essai n'est écarté silencieusement.** Tout rejet est listé avec sa raison.

## 5. Architecture attendue

Avant de créer quoi que ce soit, **inventorier les modèles d'analyse déjà présents dans le dépôt**
et les réutiliser ou les étendre s'ils couvrent un besoin (ajustement balistique, changement de
repère, conventions de signe…). Ne pas les dupliquer. En cas de conflit de conventions, demander
(Q7).

Proposition de structure, à adapter à l'existant :

```
<package>/
  pyproject.toml
  config/
    analysis.toml          # seuils, fenêtres, horizons, options (commenté)
    data_mapping.toml      # colonnes, unités, repère, encodage des métadonnées
  src/<package>/
    io.py                  # découverte des dossiers, lecture CSV, manifeste
    schema.py              # structures typées : TrialMeta, Trial, SegmentResult, FitResult…
    frames.py              # unités, passage repère caméra → repère plaque → repère inclinaison
    quality.py             # bruit de position, points aberrants, trous, monotonie du temps
    segmentation.py        # t_on, t_lift, t_stab, fin de fenêtre (bord)
    fitting.py             # ajustement balistique (avec ou sans amortissement), incertitudes
    metrics.py             # métriques par essai
    aggregate.py           # statistiques par cellule du plan, cohérence directionnelle
    physics.py             # étalonnage inclinaison, séparation gravité / air
    stats.py               # ANOVA, MANOVA, tests, dimensionnement des campagnes
    plots.py               # figures normalisées
    report.py              # rapport Markdown/HTML (gabarit Jinja2)
    synthetic.py           # générateur de données synthétiques au format réel
    cli.py                 # interface en ligne de commande
  tests/
  notebooks/               # optionnel : exploration appelant le package
```

**Bibliothèques :**

| Rôle | Bibliothèque |
|---|---|
| Calcul numérique | `numpy`, `scipy` (optimisation, filtre de Savitzky-Golay, statistiques) |
| Tableaux | `pandas` |
| Modèles statistiques | `statsmodels` (OLS, ANOVA type II, MANOVA, modèles mixtes) |
| Figures | `matplotlib`, style sobre et homogène, palette accessible aux daltoniens, export PNG et PDF vectoriel |
| Configuration | `tomllib` et validation par `pydantic` |
| Interface | `typer` ou `argparse` |
| Rapport | `jinja2` (Markdown, et HTML autonome) |
| Qualité | `pytest`, `ruff`, `mypy` |

Version de Python et gestionnaire d'environnement : Q10.

**Interface en ligne de commande, au minimum :**

```
<cli> inventory <DATA_DIR>                  # manifeste + contrôle du plan
<cli> analyze   <DATA_DIR> -c config/ -o results/
<cli> report    results/                    # rapport à partir des résultats
<cli> synth     -c config/ -o synthetic/    # jeu synthétique de validation
```

## 6. Unités et conventions

- **Unités internes :** positions en mm ; temps en s ; vitesses en mm/s ; accélérations en mm/s² ;
  angles en µrad (affichage possible en mrad) ; masses en g dans les métadonnées et en kg dans les
  calculs de force ; forces en µN ; impulsions en µN·s ; g = 9,81 m/s², sauf valeur locale fournie.
- **Repère plaque :** axes X et Y à confirmer (Q4). Toutes les grandeurs vectorielles sont exprimées
  dans ce repère.
- **Convention de signe proposée (à confirmer, Q4) :** θ = a/g > 0 sur X signifie que le palet
  dérive vers +X, donc que la plaque descend vers +X. La convention de l'accéléromètre doit lui
  être rattachée explicitement, et l'outil doit **vérifier** cette cohérence sur les données
  (pente β > 0 au § 9.1).

## 7. Pipeline par essai

### 7.1 Qualité et pré-traitement

1. Lecture, conversion d'unités, passage au repère plaque.
2. Contrôles : temps strictement croissant ; trous d'échantillonnage (> 2 périodes : signalés) ;
   points aberrants (saut incompatible avec la cinématique, critère robuste fondé sur la MAD des
   différences secondes : signalés, puis exclus de l'ajustement).
3. **Bruit de position σ_pos :** écart-type robuste sur le segment immobile avant l'allumage. Si ce
   segment n'existe pas ou est trop court, ne pas inventer de valeur : signaler et demander (Q5).
4. **Position initiale r_init :** médiane des positions sur ce même segment.

### 7.2 Découpe temporelle

| Instant | Définition (seuils dans `analysis.toml`) |
|---|---|
| **t_on** | Allumage des turbines. Si ω(t) est disponible : premier instant où ω dépasse un seuil (proposé : 5 % de ω établie). Sinon : source à définir (Q2, Q5) |
| **t_lift** | Premier mouvement du palet : \|r(t) − r_init\| > k·σ_pos (k proposé : 3), maintenu pendant M échantillons consécutifs (M proposé : 5) |
| **t_stab** | Début du vol établi. Si ω(t) est disponible : premier instant après lequel ω reste dans ±2 % (proposé) de sa valeur établie (médiane de fin d'essai). **Sinon : t_stab = t_on + durée de montée en vitesse, à fournir par l'utilisateur (Q5), jamais estimée arbitrairement** |
| **t_end** | Fin de la fenêtre exploitable : fin du fichier, ou premier instant où le centre du palet arrive à moins de (rayon du palet + marge) d'un bord de la zone utile (rayon 15 mm ; marge proposée : 5 mm ; coordonnées des bords : Q4). Si la fin vient d'un bord, l'essai est marqué **censuré**, puis conservé |

Toujours vérifier l'ordre t_on ≤ t_lift ≤ t_stab < t_end. Si un essai ne le respecte pas (par
exemple, le palet bouge avant t_on), il est signalé et non corrigé en silence.

### 7.3 Ajustement du vol établi [t_stab ; t_end]

Sur chaque axe, avec τ' = t − t_stab :

- **Modèle sans amortissement :** x(τ') = x_s + v_s·τ' + ½·a·τ'².
- **Modèle avec amortissement visqueux** (k = 1/τ, commun aux deux axes) :
  x = x_s + v_s·φ₁ + a·φ₂, avec φ₁ = (1 − e^(−kτ'))/k et φ₂ = (kτ' − 1 + e^(−kτ'))/k².
  Linéaire en (x_s, v_s, a) à k fixé : moindres carrés pondérés par 1/σ_pos², avec k cherché par
  balayage 1D.
- **Choix du modèle :** critère BIC. Le modèle amorti n'est retenu que s'il est nettement meilleur
  (seuil configurable). Sinon, reporter une borne inférieure de τ.
- **Incertitudes :** covariance des paramètres, avec σ_pos estimé au § 7.1. Rapporter le χ² réduit.
  S'il dépasse nettement 1, le signaler : modèle insuffisant, accélération variable avec la position,
  ou bruit sous-estimé.
- **Test de courbure :** significativité d'un terme cubique, qui indique une force dépendant de la
  position. À signaler, sans le retenir dans le modèle de base.
- **Durée minimale de fenêtre** (configurable) : en dessous, a est marquée « non fiable » et l'essai
  n'entre pas dans les modèles du § 9. Il reste dans le rapport.

### 7.4 Décollage et kick [t_lift ; t_stab]

- **Vitesse du kick :** Δv_kick = v_s − a·(t_stab − t_lift). On retire ce que la dérive établie
  aurait produit pendant la durée du décollage. Cette approximation doit être documentée dans le
  rapport.
- **Impulsion :** J = m·Δv_kick, en µN·s.
- **Déplacement pendant le décollage :** d_kick = |r(t_stab) − r_init|.
- **Durée de décollage :** t_stab − t_lift ; **délai de décollage :** t_lift − t_on ; **ω_lift** = ω(t_lift),
  si ω(t) est disponible.
- **Incertitudes** propagées par Monte-Carlo sur les paramètres d'ajustement et sur σ_pos.

### 7.5 Métriques par essai (table `trials.csv`, une ligne par essai)

| Métrique | Définition | Unité |
|---|---|---|
| a_x, a_y, \|a\| (± σ) | accélération du vol établi | mm/s² |
| θeq_x, θeq_y, \|θeq\| | a/g : inclinaison équivalente | µrad |
| F_x, F_y | m·a = dp/dt : force résiduelle | µN |
| Δv_kick (x, y, norme, direction) | § 7.4 | mm/s, ° |
| J (x, y, norme) | m·Δv_kick | µN·s |
| d_kick | § 7.4 | mm |
| délai et durée de décollage, ω_lift | § 7.4 | s, tr/min |
| A(T) | d_kick + \|Δv_kick\|·T + ½·\|a\|·T², pour chaque horizon T (proposés : 5 s et 10 s) | mm |
| A_p95 mesurée | 95ᵉ percentile de \|r − r_init\| sur [t_on ; t_on + T], si l'essai n'est pas censuré avant T | mm |
| t_ε | temps de sortie d'un disque de rayon ε autour de r_init (ε proposés : 2 mm et 10 mm), avec indicateur de censure | s |
| τ ou borne inférieure, χ²_red, durée de fenêtre, indicateurs de qualité, censure | §§ 7.1 à 7.3 | |

L'outil calcule à la fois les métriques **cinématiques** (a, Δv) et les métriques **pondérées par
la masse** (F, J). Le choix de celles qui servent au classement des configurations relève de
l'utilisateur (Q8).

## 8. Agrégation par cellule du plan (`cells.csv`)

Pour chaque combinaison position × inclinaison × masse :

- moyenne, écart-type et intervalle de confiance à 95 % (loi de Student, n = 3) de chaque
  métrique scalaire ;
- moyenne vectorielle de a et de Δv_kick, avec ellipse de confiance ;
- **cohérence directionnelle du kick :** R = |Σ Δv_kick| / Σ |Δv_kick|, et test de Rayleigh
  d'uniformité de la direction, agrégé par position (18 essais par position). R proche de 1 : kick
  systématique ; R proche de 0 : kick aléatoire.

## 9. Modèles physiques (`model.json`, avec incertitudes)

### 9.1 Étalonnage de l'inclinaison et inclinaison résiduelle

Régression sur tous les essais fiables, axe par axe (axe k ∈ {x, y}) :

  **a_k = β_k · g·θ_plan,k + g·θ_res,k(position) + F_k(position)/m + ε**

- β_k doit valoir 1 (palet libre). Un β significativement inférieur à 1, surtout pour le palet
  lourd, indique du frottement ou un contact intermittent. Tester β × masse.
- θ_res,k(position) est l'**inclinaison résiduelle vraie** vue par le palet, à comparer au zéro de
  l'accéléromètre.
- F_k(position) est la **force aérodynamique résiduelle**.
- **Variantes à comparer** (test F emboîté et AIC) :
  - F dépendant de l'inclinaison (interaction) ;
  - terme croisé γ·g·θ_plan,autre axe, qui estime le **désalignement angulaire** entre le repère
    caméra et le repère de l'accéléromètre. Identifiable puisque θx et θy sont connus pour les trois
    configurations.
- **Diagnostics de régression** à fournir : résidus en fonction des valeurs ajustées et par cellule,
  points influents (distance de Cook).

### 9.2 Séparation gravité / air, cellule par cellule (contrôle)

Pour chaque couple inclinaison × position, avec les moyennes des deux masses m₁ et m₂ :

- **F_air** = (a₁ − a₂) / (1/m₁ − 1/m₂)
- **a_grav** = a₁ − F_air/m₁

Avec propagation des incertitudes. Ces estimations locales doivent être cohérentes avec le modèle
global du § 9.1 ; tout écart est signalé.

### 9.3 Modèle du kick

Même démarche pour Δv_kick, par axe :

  **Δv_kick = c(position) + J(position)/m + δ·g·θ_plan**

- J indépendant de m (donc Δv en 1/m) : impulsion de pression d'origine aérodynamique.
- Δv indépendant de m : kick cinématique (basculement du palet au décollage, vibration).
- δ doit être faible : le kick ne devrait presque pas dépendre de l'inclinaison.

## 10. Statistiques (`stats/`)

- **ANOVA à trois facteurs** (position, inclinaison, masse) avec interactions, sur a_x et a_y, sur
  la projection de a sur l'axe d'inclinaison, sur |Δv_kick| et sur les composantes de J. Utiliser
  le type II. Rapporter tailles d'effet (η² partiel) et intervalles de confiance, pas seulement les
  p-valeurs.
- **MANOVA** sur les vecteurs (a_x, a_y) et (Δv_x, Δv_y).
- **Hypothèses :** normalité des résidus et homogénéité des variances, contrôlées et commentées
  avec prudence (n = 3 par cellule).
- **Répétabilité :** écart-type intra-cellule de chaque métrique.
- **Dimensionnement des campagnes suivantes :** nombre de répétitions nécessaire pour détecter un
  écart donné (α = 5 %, puissance 80 %, valeurs configurables), à partir de la répétabilité mesurée.
- **Tenir compte de l'ordre des essais**, s'il est connu (Q3) : tendance temporelle, effet de session.

## 11. Sorties

### 11.1 Fichiers

```
results/
  manifest.csv  trials.csv  cells.csv  model.json  stats/*.csv
  figures/*.png  figures/*.pdf
  diagnostics/<essai>.png        # une fiche par essai
  report.md  report.html
  run_info.json                  # configuration complète, versions, hash git, empreintes des données
```

### 11.2 Figures (normalisées, unités SI sur les axes, IC à 95 % sur toutes les barres d'erreur)

1. Trajectoires (x, y) par cellule, répétitions superposées, contour de la zone utile, positions
   initiales.
2. **Fiche diagnostic par essai :** x(t), y(t) et ω(t) avec les marqueurs t_on, t_lift, t_stab et
   t_end, l'ajustement superposé, et les résidus normalisés par σ_pos.
3. a en fonction de g·θ_plan, par axe : couleur selon la masse, symbole selon la position, droite
   ajustée avec β ± IC, droite identité de référence.
4. a en fonction de 1/m, par position et par inclinaison.
5. Vecteurs de kick (diagramme polaire ou en flèches) par position et par masse, avec R et la
   p-valeur de Rayleigh.
6. A(T) par cellule, décomposé en contribution du kick et contribution de la dérive établie.
7. Graphiques d'interaction de l'ANOVA.
8. Tableau de bord qualité : χ²_red, durées de fenêtre, censures, rejets.

### 11.3 Rapport

Sections :

1. Inventaire et qualité des données
2. Décollage et kick
3. Dérive en vol établi
4. Étalonnage de l'inclinaison (β, θ_res, désalignement)
5. Séparation gravité / air
6. Effet de la position
7. Statistiques
8. Répétabilité et dimensionnement
9. Limites et hypothèses
10. Annexes : fiches diagnostic

Le rapport énonce des **constats chiffrés avec incertitudes**. Il ne formule pas d'interprétation
causale au-delà de ce que les tests établissent. Toute hypothèse et toute valeur « proposée »
utilisée y est rappelée.

## 12. Questions bloquantes à poser à l'utilisateur avant de coder

Les poser **toutes, en une fois**, en s'appuyant sur l'inspection d'un échantillon réel de
fichiers ; puis consigner les réponses dans `config/` et dans un fichier `docs/decisions.md`.

| # | Question |
|---|---|
| Q1 | Format exact des CSV : noms des colonnes, unités, séparateur, séparateur décimal, base de temps (s, ms, n° d'image), fréquence d'acquisition. Fournir au moins un fichier d'exemple par dossier d'expérience. |
| Q2 | ω(t) (tachymètre) et l'accéléromètre figurent-ils dans chaque CSV ? Sur la même horloge que la position ? Sinon, comment l'instant d'allumage t_on est-il repérable ? |
| Q3 | Comment sont encodées masse, position, inclinaison et répétition (nom de dossier, nom de fichier, table à part) ? Valeurs des deux masses (g), des positions initiales (mm), et de θx et θy pour chaque configuration (unité). L'ordre chronologique des essais est-il connu ? |
| Q4 | Repères : les positions sont-elles déjà en mm dans le repère plaque ? Orientation des axes caméra par rapport à la plaque et à l'accéléromètre ; origine ; coordonnées des bords de la zone utile ; convention de signe de θ fournie par l'accéléromètre. |
| Q5 | L'enregistrement démarre-t-il avant l'allumage des turbines, et combien de temps avant ? Durée de montée en vitesse des turbines, si ω(t) n'est pas enregistré. |
| Q6 | Position « bord » : le palet touche-t-il la paroi ? À quelle distance du bord, et de quel bord ? |
| Q7 | Quels modèles d'analyse existent déjà dans le dépôt, lesquels réutiliser, et avec quelles conventions ? |
| Q8 | Pour classer les futures configurations, priorité aux métriques cinématiques (a, Δv) ou pondérées par la masse (F, J) ? |
| Q9 | Valider ou modifier les valeurs « proposées » : seuils de découpe, marge au bord, horizons T, rayons ε, durée minimale de fenêtre. |
| Q10 | Version de Python, gestionnaire d'environnement (pip, conda, uv), contraintes de diffusion des données (confidentialité, données dans le dépôt ou non). |
| Q11 | Format du rapport final : Markdown, HTML, PDF ? |

Si, pendant le développement, les données contredisent une hypothèse de cette consigne (absence de
segment immobile, palet qui bouge avant t_on, fréquence irrégulière…), **s'arrêter et demander**
plutôt que de contourner.

## 13. Validation

### 13.1 Données synthétiques (obligatoire avant les données réelles)

`synthetic.py` génère des essais **au format exact des CSV réels**, avec des paramètres connus :

- a et F_air dépendant de la position, θ_plan, masse, kick (direction et intensité selon la position) ;
- montée en vitesse de ω, segment immobile initial, bruit de position, amortissement optionnel ;
- défauts injectés : points aberrants, trous, sortie par un bord (censure).

### 13.2 Tests automatisés (`pytest`)

- **Ajustement :** sur 1 000 tirages, la valeur vraie de a est dans ±3σ estimés dans au moins 99 %
  des cas ; χ²_red ≈ 1 en moyenne.
- **Découpe :** t_lift et t_stab retrouvés à quelques périodes d'échantillonnage près.
- **Modèle physique :** β, θ_res et F_air retrouvés dans leurs IC à 95 % ; désalignement angulaire
  injecté retrouvé.
- **Kick :** cohérence R et test de Rayleigh corrects, pour des kicks systématiques comme aléatoires.
- **Robustesse :** censure, colonne manquante, fichier vide, temps non monotone. Chaque cas donne
  un message explicite, jamais un résultat silencieusement faux.
- **Conventions :** repère tourné ou en miroir ; changement d'unités px → mm.

### 13.3 Critères de recette sur données réelles

- Les 36 essais apparaissent dans le manifeste ; chaque rejet est justifié.
- Aucune exception non gérée ; résultats reproductibles à l'identique (même configuration, mêmes
  données, même `run_info.json`).
- Rapport complet, figures lisibles en noir et blanc comme en couleur, toutes les grandeurs avec
  unité et incertitude.
- Revue des résultats avec l'utilisateur avant toute conclusion physique.

## 14. Jalons

| Jalon | Contenu | Livrable |
|---|---|---|
| J0 | Questions du § 12, inventaire de l'existant et des données | `docs/decisions.md`, `config/` rempli, `inventory` fonctionnel |
| J1 | Lecture, repères, qualité, générateur synthétique | tests §13.2 « robustesse » et « conventions » verts |
| J2 | Découpe et ajustement | tests « ajustement » et « découpe » verts, fiches diagnostic |
| J3 | Métriques par essai et agrégation | `trials.csv`, `cells.csv` |
| J4 | Modèles physiques et statistiques | `model.json`, `stats/`, tests « modèle physique » et « kick » verts |
| J5 | Figures et rapport | `report.md`, `report.html` |
| J6 | Passage sur les données réelles et revue avec l'utilisateur | recette du § 13.3 |

Chaque jalon donne lieu à un commit dédié, avec un message clair. Ne pas passer au jalon suivant si
les tests du jalon courant échouent.
