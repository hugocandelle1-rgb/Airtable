---
name: airtable-projet
description: Conventions, organisation et chaîne de vérification du projet de table à coussin d'air de précision (dépôt Airtable). À utiliser dès qu'on modifie un paramètre de conception, une note de calcul, la CAO, le firmware ou la nomenclature de ce dépôt, ou qu'on répond à une question sur la table (plaque perforée, plenum, ventilateur, nivellement, capteurs), même si l'utilisateur ne cite pas le projet explicitement.
---

# Projet table à coussin d'air — conventions

Le projet est un système couplé : un changement de pas de perçage modifie le débit,
donc le ventilateur, donc le plenum, donc la rigidité de plaque, donc le budget de pente.
Ces conventions servent à garder une seule vérité et à propager chaque changement.

## Organisation

| Dossier | Contenu |
|---|---|
| `params/design.toml` | **Source unique de vérité** des paramètres (unités SI, suffixes `_mm`, `_Pa`, `_urad`…) |
| `docs/00_cahier_des_charges.md` | Besoin, exigences, **budget d'erreur de pente** |
| `docs/0x_*.md` | Notes de calcul et dossiers (aéraulique, structure, usinage, nivellement, instrumentation…) |
| `calc/<domaine>/` | Scripts Python ; `figures/` (PNG) et `results/` (JSON/TOML) générés |
| `cad/` | Modèles CadQuery paramétriques + exports STEP/STL/SVG |
| `firmware/` | Contrôleur embarqué (PlatformIO) ; `host/` : logiciel PC (Python) |
| `bom/` | Nomenclature (CSV/XLSX) |

## Règles

1. **Lire les paramètres via** `from calc.common.params import load_params` ; ne jamais
   recopier une valeur en dur dans un script, un modèle CAO ou le firmware (le firmware
   reçoit un en-tête généré ou un JSON de consignes).
2. **Modifier un paramètre** = éditer `params/design.toml` + relancer la chaîne
   (`python3 -m calc.run_all` si présent, sinon chaque module de `calc/`) + mettre à jour
   la note de calcul concernée + régénérer la CAO touchée. Indiquer le changement dans
   la section « Historique » de la note.
3. **Langue** : documentation en français ; identifiants de code en anglais, commentaires
   en français.
4. **Lancer les scripts depuis la racine** : `python3 -m calc.aero.film_model`.
5. **Tout chiffre de composant du commerce cite sa source** (URL de fiche technique)
   dans `docs/research/`.
6. **Pas de régression du budget** : après toute modification, vérifier que la pente
   locale résiduelle prévue reste ≤ `performance_targets.residual_slope_peak_urad`
   et que l'entrefer de chaque masse reste dans `[gap_min_um, gap_max_um]`.

## Grandeurs à garder en tête

- a = g·θ : 0,01° = 175 µrad → 1,7 mm/s² ; la cible 50 µrad → 0,5 mm/s².
- Pente d'un bombé de flèche δ sur L : ≈ 4δ/L (5 µm sur 360 mm ≈ 56 µrad).
- Seule la part **non plane** d'une déformée compte : le plan moyen est rattrapé par
  le nivellement. Toujours retirer le plan des moindres carrés avant d'évaluer une pente.
- Portance moyenne requise : W/A = 27,7 Pa (2 g) à 139 Pa (10 g) pour Ø30 mm.

## Liste de vérification avant de livrer

- [ ] Scripts de `calc/` exécutés sans erreur, figures régénérées
- [ ] `params/design.toml` cohérent avec les notes (mêmes valeurs)
- [ ] CAO régénérée si une cote a changé (`python3 -m cad.build_all` si présent)
- [ ] Nomenclature à jour (références, quantités)
- [ ] Budget de pente et entrefers re-vérifiés

Skills voisins : `film-air-orifices` (physique du coussin), `tolerancement-iso-gps`
(cotation de la plaque), `cadquery-mecanique` (CAO), `firmware-banc` (contrôleur).
