# Reprise — firmware, hôte Python, contrôle-commande

Mis à jour après la décision de l'utilisateur « inclinaison par 4 accéléromètres ADXL355 » (plus d'inclinomètre
métrologique ni de SCL3300 comme référence). Aucun commit git effectué ; `params/design.toml` non modifié.

## (a) Ce qui est écrit et vérifié

Commandes exactes et résultats réels (depuis la racine du dépôt `/home/user/Airtable`) :

| Commande | Résultat |
|---|---|
| `make -C firmware test` (g++ seul, shim Unity) | 6 suites, 97 tests, 0 échec |
| `make -C firmware syntax` | OK (18 fichiers) |
| `pio test -d firmware -e native` (vrai Unity) | 97 cas passés |
| `pio run -d firmware -e esp32s3` | SUCCESS, 0 warning, RAM 7,4 %, Flash 11,4 % |
| `pio run -d firmware -e esp32s3_scl3300` | SUCCESS, 0 warning (option SCL3300-D01, 1 capteur) |
| `pio run -d firmware -e esp32s3_flip` | SUCCESS, 0 warning (avec retournement motorisé) |
| `python3 -m pytest host/tests -q` | 144 passés, 1 ignoré (test vidéo : OpenCV non installé) |
| `python3 firmware/tools/gen_design_params.py --check` | en-tête `design_params.h` à jour |

Rien n'a été exécuté sur matériel réel.

## (b) État des modules

**Fini (compile + testé sur PC)** — `firmware/lib/atcore/src/atcore/` : `crc`, `filters`, `pid`, `fan_model`,
`pressure_controller`, `setpoints`, `tach`, `sdp8xx`, `airphys`, `scl3300`, `adxl355`, `tmp117`, `ads1220`,
`inclinometer`, `leveling`, `stepgen`, `safety`, `commands`, `json`, et **nouveau `tilt_array`** (compensation
thermique polynomiale ordre 1–2 + apprentissage par moindres carrés + recalage du biais, estimateur de bruit,
fusion pondérée 1/σ² avec rejet par la médiane et cas N = 1…4, écart inter-capteurs, ajustement de courbure
`z_xx, z_xy, z_yy` + rotationnel, séquence de retournement 0° → 180° → 0°). Tests : `firmware/test/test_*/` (dont
`test_tilt_array`, 32 tests ; `test_protocol` étendu aux commandes v2).

**Fini (compile pour esp32s3, non testé sur matériel)** — `firmware/include/` + `firmware/src/` : tous les modules
précédents, plus : `flip_actuator` (servo LEDC 50 Hz + contact d'index, option `-DUSE_FLIP_ACTUATOR`),
`env_sensors` (TMP117 ×4 des bases d'ADXL355 sur le canal 7 du TCA9548A), `settings` (NVS par capteur : biais,
rotation, signes, modèle thermique, masque d'utilisation), `app.cpp` (réseau de capteurs : lecture synchronisée,
fusion, gel du nivellement pendant retournement/apprentissage), `console.cpp` (protocole version 2, télémétrie par
capteur). **ADXL355 ×4 est la configuration par défaut** ; `-DUSE_SCL3300` (env `esp32s3_scl3300`) sélectionne le
SCL3300-D01 seul.

**Fini (hôte)** — `host/airtable_host/` : `protocol` (miroir C++ + commandes v2, parité fuzz), `client`, `logger`,
`sim` (simulateur à N capteurs, thermique, retournement motorisé), `tilt_calibration` (retournement N capteurs,
champ de pente, retournement motorisé, planification, biais vs température), `drift_calibration`, **`slope_export`**
(carte de pente / efforts parasites JSON/CSV + lecture côté robots), `cli` (nouvelles sous-commandes `flip-auto`,
`flip-schedule`, `therm-learn`, `tilt-report`, `slope-export`, `cal-tilt-flip --all/--sensor`).

**Documentation** : `docs/07_controle_commande.md` **écrit** (architecture, câblage SPI des 4 ADXL355, boucles,
sécurités, protocole, procédures, carte de pente, liste à valider).

## (c) Étapes restantes, dans l'ordre

1. À valider sur matériel (liste complète : `docs/07_controle_commande.md` §12) : sélection SPI/I²C et bruit réel
   des ADXL355 ; coefficients thermiques ; seuils 40 µrad (rejet) / 20 µrad (déformation) ; positions des capteurs
   (`TILT_POS_*_MM`, à reprendre de la CAO) ; reproductibilité de l'appui du retournement motorisé, largeurs
   d'impulsion du servo, polarité de l'index ; GPIO 35/36/37 (module **sans** PSRAM octale) et GPIO 3 (strapping) ;
   `FAN_P_FULL_PA`, seuil de calage, Cd de la buse, `DIR_INVERT`, fins de course, RGB (GPIO 48 v1.0 / 38 v1.1),
   écriture NVS interdite pendant mouvement, comportement `Serial` USB-CDC non connecté.
2. Synchronisation matérielle des ADXL355 (broche SYNC) : non implémentée (lecture séquentielle dans le même tour).
3. Optionnel : installer `opencv-python-headless` et lancer `test_video_optionnelle` ; test pytest du CLI sur
   `sim://` (seul `slope-export` est testé via le CLI), `host/README` d'usage, `pyproject`.
4. Cohérence amont : `docs/research/capteurs.md` présente toujours les MEMS comme « dégrossissage » ; la décision
   utilisateur (4 ADXL355 + thermique + retournement + palets) est consignée dans `00_coordination.md` et
   `07_controle_commande.md` §1. `.claude/skills/firmware-banc/SKILL.md` parle encore d'« inclinomètre » au singulier.
5. Hygiène git (coordinateur) : `firmware/.build_native/` a été committé dans un commit WIP avant l'ajout de
   `firmware/.gitignore` ; faire `git rm -r --cached firmware/.build_native`. Rappel : `firmware/.pio/` doit rester ignoré.

## (d) Commandes de compilation et de test

```
make -C firmware test                 # tests natifs sans PlatformIO
make -C firmware syntax               # g++ -fsyntax-only de la logique portable
pio test -d firmware -e native        # tests Unity PlatformIO
pio run -d firmware -e esp32s3        # firmware ESP32-S3 : 4 × ADXL355 (défaut)
pio run -d firmware -e esp32s3_scl3300   # option SCL3300-D01 (1 capteur)
pio run -d firmware -e esp32s3_flip      # + retournement 180° motorisé (servo GPIO 37, index GPIO 3)
python3 firmware/tools/gen_design_params.py [--check]   # en-tête depuis params/design.toml
python3 -m pytest host/tests -q       # tests hôte (parité C++/Python incluse, nécessite g++)
python3 -m host.airtable_host --port sim:// status       # essai sans matériel
python3 -m host.airtable_host slope-export lachers.csv -o carte_pente.json --grid-out 31x31
```
