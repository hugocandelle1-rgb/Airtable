---
name: firmware-banc
description: Architecture et règles du firmware embarqué et du logiciel hôte d'un banc d'essai instrumenté (table à coussin d'air) — régulation de pression par PWM de ventilateur, lecture tachymètre, capteurs I²C/SPI (pression différentielle, inclinomètre, température), moteurs pas à pas de nivellement, protocole série, journalisation et calibration côté PC. À utiliser pour écrire, modifier ou déboguer le code dans firmware/ ou host/, ou pour concevoir une boucle de régulation du banc, même si la demande parle seulement de « piloter le ventilateur » ou « régler l'inclinaison automatiquement ».
---

# Firmware et logiciel hôte du banc

## Architecture

- Cible par défaut : **ESP32-S3** (PlatformIO, framework Arduino). Boucle coopérative
  non bloquante ; chaque tâche a sa période (`millis()`/`micros()`), aucune attente active.
- Fréquences typiques : pression 100 Hz (régulation 50 Hz), tachy 10 Hz, inclinomètre
  10–20 Hz (filtré), températures 1 Hz, nivellement 0,2–1 Hz, télémétrie 10 Hz.
- **PWM ventilateur 25 kHz** (norme 4 fils Intel) via LEDC ; tachy (2 impulsions/tr,
  collecteur ouvert, pull-up) via PCNT ou interruption + fenêtre glissante.
- I²C : capteurs Sensirion SDP8xx à adresse fixe ⇒ multiplexeur TCA9548A.
- Nivellement : 2 moteurs pas à pas via TMC2209 (UART, StealthChop) ou TMC5160 ;
  positions absolues après prise d'origine (fin de course), limites logicielles.

## Régulation

- **Pression** : PI(D) avec anticipation (feed-forward) issue de la loi ventilateur
  p ∝ N² ⇒ PWM_ff = f⁻¹(consigne) ; anti-windup par saturation conditionnelle ;
  rampe de consigne ; filtrage du capteur (IIR 1er ordre) ; consignes par masse de palet
  lues depuis `calc/aero/results/setpoints.json` (transmises par l'hôte).
- **Nivellement** : boucle lente à bande morte (ne pas « chasser » le bruit) ; mouvement
  seulement si l'écart filtré > seuil pendant N échantillons ; découplage des axes par la
  matrice géométrique (vérins → angles) ; option boucle externe sur la dérive des palets
  mesurée par caméra (côté hôte).
- Sécurités : calage moteur (tachy nulle avec PWM > seuil), surpression, capteur absent,
  fin de course, chien de garde ; état « SAFE » = ventilateur à la consigne de repos, moteurs arrêtés.

## Protocole série (USB CDC, 115200+)

Lignes texte, une commande par ligne, réponses JSON d'une ligne :

    SET P 120.0          -> {"ok":true}
    SET MASS 5.0         -> consigne depuis la table masse→pression
    LEVEL AUTO ON|OFF ; LEVEL MOVE <axe> <µrad> ; LEVEL ZERO
    GET STATUS           -> {"t":..,"p":[..],"rpm":..,"pwm":..,"tilt":[..],"T":[..],...}
    STREAM ON 10         -> télémétrie JSON à 10 Hz

## Hôte (Python, `host/`)

- `pyserial` + journalisation CSV/Parquet horodatée ; CLI (`argparse`) ;
- calibration de l'inclinomètre par **retournement 180°** (biais = moyenne des deux lectures) ;
- calibration par palets : suivi caméra (OpenCV), ajustement de x(t) = x0 + v0·t + a·t²/2
  ⇒ a = g·θ local ⇒ carte de pente et correction de l'inclinaison.

## Vérification

Compiler (`pio run`) si PlatformIO est disponible ; sinon au minimum tester la logique
(PID, conversions, parseur de commandes) dans des tests unitaires PC (`pio test -e native`
ou équivalent Python de la logique).
