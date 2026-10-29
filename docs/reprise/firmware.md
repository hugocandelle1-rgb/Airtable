# Reprise — firmware, hôte Python, contrôle-commande

Rapport intermédiaire (arrêt demandé pour quota). Aucun commit effectué par l'ingénieur firmware.

## (a) Ce qui est écrit et vérifié

Commandes exactes et résultats réels (depuis la racine du dépôt `/home/user/Airtable`) :

| Commande | Résultat |
|---|---|
| `make -C firmware test` (g++ seul, shim Unity) | 5 suites, 64 tests, 0 échec |
| `make -C firmware syntax` | OK (`-fsyntax-only` de toute `lib/atcore`) |
| `pio test -d firmware -e native` (vrai Unity) | 64 cas passés (PlatformIO 6.2.0 installé via pip) |
| `pio run -d firmware -e esp32s3` | SUCCESS, 0 warning, RAM 7 %, Flash 11 % (toolchain xtensa téléchargée, Arduino core 2.0.17) |
| `python3 -m pytest host/tests -q` | 87 passés, 1 ignoré (test vidéo : OpenCV non installé) |
| `python3 firmware/tools/gen_design_params.py --check` | en-tête `design_params.h` à jour |

Non testé : `-DUSE_ADXL355` (option de compilation), `pio run` après le dernier ajout du champ `target` dans `writeConfig` de `console.cpp` (compilé OK lors du dernier `pio run`, SUCCESS). Rien n'a été exécuté sur matériel réel.

## (b) État des modules

**Fini (compile + testé sur PC)** — `firmware/lib/atcore/src/atcore/` : `crc`, `filters`, `pid` (PI(D), anti-windup conditionnel, `RateLimiter`), `fan_model`, `pressure_controller` (FF p∝N², gains planifiés, modèle de référence anti-dépassement), `setpoints` (table masse→pression + parseur JSON), `tach`, `sdp8xx`, `airphys`, `scl3300` (trames/CRC vérifiés), `adxl355`, `tmp117`, `ads1220`, `inclinometer` (interface + accumulateur), `leveling` (µrad/µm/pas, découplage, étalonnage, boucle à bande morte), `stepgen` (trapèze entier, ISR-safe), `safety`, `commands`, `json`. Tests : `firmware/test/test_*/`, `firmware/Makefile`, `firmware/tools/unity_shim/unity.h`.

**Fini (compile pour esp32s3, non testé sur matériel)** — `firmware/include/` + `firmware/src/` : `config.h`, `design_params.h` (généré), `i2c_bus` (TCA9548A), `pressure_sensors` (SDP810), `env_sensors` (TMP117 + BME280 Adafruit), `fan` (LEDC 25 kHz + tachy ISR), `inclinometer_drivers` (SCL3300, ADXL355), `displacement_sensors` (ADS1220), `level_actuators` (TMC2209 + ISR de pas + prise d'origine), `settings` (NVS), `app.cpp` (ordonnanceur, sécurités, nivellement), `console.cpp` (protocole), `main.cpp`, `platformio.ini`.

**Fini (hôte)** — `host/airtable_host/` : `protocol` (miroir Python du parseur C++, parité testée par fuzz), `client`, `logger`, `sim` (simulateur), `tilt_calibration` (retournement 180°), `drift_calibration` (ajustement avec/sans amortissement, carte, champ de hauteur, correction plan moyen, repère caméra, suivi vidéo OpenCV optionnel), `cli`. Tests dans `host/tests/`.

**Autres** : `calc/aero/results/setpoints.json` (exemple provisoire, 3 points issus de `dynamics.json`).

**Non commencé** : `docs/07_controle_commande.md` (livrable 5), `docs/research` n'a pas été complété pour les composants de contrôle (voir `docs/research/capteurs.md` déjà existant, écrit par un autre agent).

## (c) Étapes restantes, dans l'ordre

1. Écrire `docs/07_controle_commande.md` (en français) : schéma bloc (mermaid), câblage broche par broche (reprendre `firmware/include/config.h`), alimentations 12/24 V et découplage, blindage/longueurs I²C (TCA9548A : canaux 0-4 SDP810-500, 5 SDP810-125, 6 TMP117×4 + BME280), connecteurs, boucles (schémas, gains initiaux `kp_norm=0.8`, `ti=0.8 s`, période 20 ms, méthode de réglage : échelon de PWM → τ_p, `ref_tau_s`), nivellement (bande morte 3 µrad, 5 confirmations, silence 6 s), sécurités (tableau `safety.h`, SAFE = PWM de repos 0.20 + moteurs inhibés), protocole (reprendre l'en-tête de `commands.h` ; règle : réponse = clé `ok`, télémétrie = clé `t` sans `ok`), procédures (mise en route, préchauffage thermique, prise d'origine `LEVEL HOME`, nivellement, retournement `cal-tilt-flip`, calibration palets `drift-fit`), conventions de signe (`tilt = ∂z/∂x` ; θ de dérive = −tilt ; correction = +θ moyen ; `LEVEL TARGET`), et liste de ce qui reste à valider sur matériel. Citer `docs/research/capteurs.md` (dérive MEMS 20-100 µrad/°C : l'inclinomètre n'est pas une référence à 2 µrad sans thermostatisation et calibration palets).
2. Vérifier la construction `pio run -e esp32s3 -DUSE_ADXL355` (ajouter un env `esp32s3_adxl355` dans `platformio.ini` si souhaité).
3. Optionnel : installer `opencv-python-headless` et lancer `test_video_optionnelle`.
4. Optionnel : test pytest du CLI (`python3 -m host.airtable_host --port sim:// ...`), `host/README` d'usage, et `pytest.ini`/`pyproject` si on veut l'installer en paquet.
5. À valider sur matériel (à lister dans le doc) : valeurs `[À VALIDER]` de `config.h` (p_full, seuil de calage, géométrie et mécanique des vérins sens `DIR_INVERT`, fin de course NF, Cd de la buse, sensibilités des capteurs de déplacement), écriture NVS interdite pendant mouvement, comportement `Serial` USB-CDC non connecté, brochage RGB (GPIO 48 v1.0 / 38 v1.1), précisions SCL3300 (trame bank1 `kCmdBank1` calculée, non issue de la fiche).
6. Hygiène git (à faire par le coordinateur) : `firmware/.build_native/` (binaires) a été committé dans un commit WIP avant l'ajout de `firmware/.gitignore` ; faire `git rm -r --cached firmware/.build_native`.

## (d) Commandes de compilation et de test

```
make -C firmware test                 # tests natifs sans PlatformIO
make -C firmware syntax               # g++ -fsyntax-only de la logique portable
pio test -d firmware -e native        # tests Unity PlatformIO
pio run -d firmware -e esp32s3        # compilation firmware ESP32-S3
python3 firmware/tools/gen_design_params.py [--check]   # en-tête depuis params/design.toml
python3 -m pytest host/tests -q       # tests hôte (parité C++/Python incluse, nécessite g++)
python3 -m host.airtable_host --port sim:// status       # essai sans matériel
```
