# Reprise — coordination du projet (état au 2026-10-29)

Arrêt volontaire à 75 % du quota : les sous-agents actifs ont terminé leur étape en
cours puis écrit leur propre fichier de reprise dans ce dossier. **Les vagues 2 et 3
n'ont pas été lancées.**

## Fichiers de reprise par domaine

| Domaine | Fichier | Agent d'origine |
|---|---|---|
| Aéraulique (film d'air, perçage, débit, plenum, diffuseur) | `aero.md` | Opus, effort élevé |
| Structure (plaque, appuis, thermique, bâti, nivellement, usinage) | `structure.md` | Opus, effort élevé |
| Firmware ESP32-S3 + logiciel hôte Python | `firmware.md` | Sonnet, effort élevé |
| CAO CadQuery paramétrique (phase 1) | `cao.md` | Sonnet, effort élevé |
| Veille technique (terminée) | `../research/*.md` | Sonnet, effort moyen |

Si un de ces fichiers manque, l'agent correspondant n'a pas pu l'écrire avant l'arrêt :
repartir de son dossier (`calc/aero/`, `calc/structure/`, `firmware/`, `host/`, `cad/`).

## Ce qui est fait

- Socle : `params/design.toml` (source unique de vérité, valeurs **baseline** non encore
  fusionnées avec les recommandations des agents), `docs/00_cahier_des_charges.md`
  (exigences + budget de pente ≤ 50 µrad crête), chargeur `calc/common/params.py`.
- Skills projet dans `.claude/skills/` : `airtable-projet`, `film-air-orifices`
  (+ `scripts/quick_float.py`), `tolerancement-iso-gps`, `cadquery-mecanique`, `firmware-banc`.
- Veille sourcée complète dans `docs/research/`.

## Enseignements clés de la veille (à intégrer)

1. **Ventilateur** : meilleur candidat San Ace 9BMC24P2G001 (24 V, PWM 25 kHz + tachy ;
   1640 Pa à 30 m³/h, 1130 Pa à 60 m³/h à 100 %). Mais 121 Pa déjà à 20 % PWM ⇒ prévoir
   une **vanne de décharge réglable** (ou un étranglement) pour les faibles pressions
   (palets 2 g). Alternatives : ebm-papst RER 120-26/14/2 TDP, G1G108-AB17-02 (marge faible).
2. **Pression** : SDP810-500Pa obligatoire pour 400 Pa ; erreur de span 3 % ⇒ étalonnage in situ.
3. **Inclinaison** : seuls Wyler Zerotronic 3 et Leica Nivel220 approchent 2 µrad (dérive
   ≈ 5 µrad/°C) ; les MEMS (SCL3300, ADXL355) sont trop grossiers en absolu ⇒ référence
   absolue = **calibration par dérive des palets** + inclinomètre métrologique pour le suivi.
4. **Plaque** : brut coulé 5083 ≈ 80 µm de planéité sur 520 mm ⇒ rectification/rodage après
   perçage indispensable ; **aucun prestataire confirmé pour 6 µm sur 500×500 en alu** —
   risque n° 1. Piste à évaluer : plaque **circulaire** surfacée au diamant (tour de
   reprise d'optique), ou rodage. Céramique/alu poreux (Metapor) écartés (trop résistifs).
5. **Nivellement** : les actionneurs motorisés du commerce portent ≤ 40–60 N et ont une
   course fine insuffisante pour ±0,25° ⇒ mécanisme porteur dédié (vis fine + réduction
   ou levier/coin) ; réglage grossier aux pieds du bâti.

## Prochaines étapes (ordre recommandé)

1. Relire `aero.md` et `structure.md` ; finir les étapes restantes listées (relancer les
   mêmes agents ou un agent neuf avec ces fichiers comme contexte).
2. **Fusionner** `calc/aero/results/recommended_params.toml` et
   `calc/structure/results/recommended_params.toml` dans `params/design.toml`
   (arbitrer : pas/Ø des trous, épaisseur, schéma d'appui, forme carrée vs circulaire).
3. **Vague 2** : sélection finale du ventilateur sur la courbe réseau (+ vanne de décharge),
   CAO phase 2 avec les cotes figées (voir `cao.md`, clés DEFAULTS), firmware avec la
   table `calc/aero/results/setpoints.json`, dossier instrumentation `docs/06_instrumentation.md`.
4. **Vague 3** : nomenclature `bom/` (agent Haiku, effort faible), revue de cohérence
   croisée (agent Opus, effort élevé), synthèse `docs/01_architecture.md`.

## Git

Branche de travail : `claude/air-cushion-table-design-clodgs` (tout est commité et poussé).
