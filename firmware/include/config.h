// =============================================================================
//  config.h — brochage, constantes et réglages du contrôleur de la table à coussin d'air
//  Cible : ESP32-S3-DevKitC-1 (PlatformIO, framework Arduino).
//
//  Les valeurs de CONCEPTION (plage de pression, course de nivellement, nombre de
//  ventilateurs...) viennent de params/design.toml via design_params.h (généré).
//  Ce fichier ne contient que ce qui dépend du câblage et de la composante choisie ;
//  tout ce qui est « à valider sur matériel » est marqué [À VALIDER].
// =============================================================================
#pragma once

#include <stdint.h>

#include "design_params.h"

#define FW_NAME "airtable-fw"
#define FW_VERSION "0.1.0"
#define PROTOCOL_VERSION 1

// -----------------------------------------------------------------------------
//  Brochage ESP32-S3-DevKitC-1
//  Évités : GPIO0/3/45/46 (strapping), 19/20 (USB natif), 26-32 (flash), 33-37 (PSRAM
//  octale des modules R8), 43/44 (UART0 console).
// -----------------------------------------------------------------------------
// I²C principal (vers TCA9548A) — câble court, pull-ups 2,2 kΩ vers 3,3 V sur la carte
constexpr int PIN_I2C_SDA = 8;
constexpr int PIN_I2C_SCL = 9;
constexpr int PIN_TCA_RESET = 4;      // RESET# du TCA9548A (actif bas), pull-up 10 kΩ
constexpr uint32_t I2C_FREQ_HZ = 400000;
constexpr uint8_t TCA_ADDR = 0x70;    // A0=A1=A2=GND

// SPI (FSPI) partagé : SCL3300 (mode 0), ADXL355 (mode 0), ADS1220 (mode 1)
constexpr int PIN_SPI_MOSI = 11;
constexpr int PIN_SPI_SCK = 12;
constexpr int PIN_SPI_MISO = 13;
constexpr int PIN_CS_SCL3300 = 10;
constexpr int PIN_CS_ADXL355 = 14;
constexpr int PIN_CS_ADS1220 = 16;
constexpr int PIN_ADS1220_DRDY = 1;   // entrée, actif bas

// Ventilateurs 4 fils (PWM 25 kHz, tachymètre collecteur ouvert 2 imp/tr)
constexpr int MAX_FANS = 2;
constexpr int NUM_FANS = DESIGN_FAN_COUNT;           // 1 ou 2 (params/design.toml)
constexpr int PIN_FAN_PWM[MAX_FANS] = {5, 6};
constexpr int PIN_FAN_TACH[MAX_FANS] = {7, 15};      // pull-up 10 kΩ vers 3,3 V (JAMAIS 12 V)
constexpr int FAN_LEDC_CHANNEL[MAX_FANS] = {0, 1};
constexpr int FAN_LEDC_BITS = 11;                    // 80 MHz / 25 kHz = 3200 → 11 bits
constexpr float FAN_TACH_PULSES_PER_REV = 2.0f;
constexpr uint32_t FAN_TACH_MIN_EDGE_US = 150;       // anti-rebond : > 6,6 kHz impossible

// Moteurs pas à pas de nivellement : 2 × (NEMA17 + TMC2209)
constexpr int PIN_STEP[2] = {39, 41};
constexpr int PIN_DIR[2] = {40, 42};
constexpr int PIN_MOTOR_EN = 21;                     // EN# commun des TMC2209 (actif bas)
constexpr int PIN_TMC_TX = 17;                       // → PDN_UART via 1 kΩ (UART demi-duplex)
constexpr int PIN_TMC_RX = 18;                       // ← PDN_UART directement
constexpr uint8_t TMC_ADDR[2] = {0, 1};              // MS1/MS2 : 00 et 01
constexpr float TMC_R_SENSE = 0.11f;                 // Ω (cartes standard)
constexpr int PIN_LIMIT[2] = {47, 2};                // fins de course (NF vers GND, pull-up interne)
constexpr bool LIMIT_ACTIVE_LOW = false;             // NF : ouvert = déclenché (↔ fil coupé détecté)
constexpr bool DIR_INVERT[2] = {false, false};       // [À VALIDER] sens de montage des moteurs

// Divers
constexpr int PIN_LED_EXT = 38;                      // LED d'état externe (330 Ω)
constexpr int PIN_LED_RGB = 48;                      // WS2812 de la carte (v1.0 : 48 ; v1.1 : 38 → adapter)

// -----------------------------------------------------------------------------
//  Multiplexeur TCA9548A : affectation des canaux
// -----------------------------------------------------------------------------
constexpr int MUX_CH_PLENUM[5] = {0, 1, 2, 3, 4};    // SDP810-500Pa : 4 coins + centre
constexpr int MUX_CH_NOZZLE = 5;                     // SDP810-125Pa (buse d'entrée)
constexpr int MUX_CH_ENV = 6;                        // TMP117 ×4 (0x48-0x4B) + BME280 (0x76)
constexpr int NUM_PLENUM_SENSORS = 5;
constexpr uint8_t TMP117_ADDR[4] = {0x48, 0x49, 0x4A, 0x4B};
//   0 : plaque dessus, 1 : plaque dessous, 2 : air plenum, 3 : local (salle)
constexpr uint8_t BME280_ADDR = 0x76;

// -----------------------------------------------------------------------------
//  Périodes des tâches coopératives [ms] (aucune attente active dans loop())
// -----------------------------------------------------------------------------
constexpr uint32_t T_PRESSURE_MS = 10;               // lecture SDP810 : 100 Hz
constexpr uint32_t T_CONTROL_MS = 20;                // régulation de pression : 50 Hz
constexpr uint32_t T_TACH_MS = 100;                  // 10 Hz
constexpr uint32_t T_TILT_POLL_MS = 5;               // acquisition inclinomètre brute : 200 Hz
constexpr uint32_t T_TILT_OUT_MS = 100;              // sortie moyennée : 10 Hz
constexpr uint32_t T_ENV_MS = 1000;                  // températures + BME280 : 1 Hz
constexpr uint32_t T_LEVEL_MS = 1000;                // boucle de nivellement : 1 Hz
constexpr uint32_t T_DISP_MS = 50;                   // déplacement (ADS1220) : 20 Hz
constexpr uint32_t T_LED_MS = 100;
constexpr uint32_t WDT_TIMEOUT_S = 5;                // chien de garde matériel (TWDT)

// -----------------------------------------------------------------------------
//  Capteurs de pression
// -----------------------------------------------------------------------------
constexpr float SDP_SCALE_500PA = 60.0f;             // LSB/Pa (relu dans la trame)
constexpr float SDP_SCALE_125PA = 240.0f;
constexpr int SDP_FAIL_LIMIT = 3;                    // échecs consécutifs → capteur invalide
constexpr uint32_t SDP_RETRY_MS = 2000;              // nouvelle tentative d'initialisation
constexpr float P_SENSOR_TAU_S = 0.05f;              // filtre IIR par capteur
constexpr float P_ZERO_MAX_PA = 3.0f;                // CAL PZERO refuse un offset plus grand

// Buse d'entrée calibrée : Q = Cd·A·√(2Δp/ρ)            [À VALIDER : Cd par étalonnage]
constexpr float NOZZLE_CD_DEFAULT = 0.97f;
constexpr float NOZZLE_DIAM_MM_DEFAULT = 20.0f;

// -----------------------------------------------------------------------------
//  Ventilateur / régulation de pression
// -----------------------------------------------------------------------------
constexpr float FAN_DUTY_MIN = 0.10f;                // en dessous : décrochage / arrêt
constexpr float FAN_DUTY_MAX = 1.00f;
constexpr float FAN_DUTY_REST = 0.20f;               // PWM de repos (état SAFE, démarrage)
constexpr float FAN_P_FULL_PA = 600.0f;              // [À VALIDER] pression à PWM 100 % (identifier)
constexpr float CTRL_KP_NORM = 0.8f;                 // gain de boucle adimensionnel
constexpr float CTRL_TI_S = 0.8f;                    // ≈ constante de temps procédé
constexpr float CTRL_REF_TAU_S = 0.8f;
constexpr float CTRL_RAMP_PA_S = 150.0f;
constexpr float CTRL_MEAS_TAU_S = 0.08f;

// -----------------------------------------------------------------------------
//  Sécurités
// -----------------------------------------------------------------------------
constexpr float SAFE_P_LIMIT_PA = DESIGN_P_MAX_PA * 1.2f;   // surpression
constexpr uint32_t SAFE_OVERPRESSURE_MS = 200;
constexpr float SAFE_STALL_DUTY = 0.25f;
constexpr float SAFE_STALL_RPM = 300.0f;             // [À VALIDER] selon le ventilateur retenu
constexpr uint32_t SAFE_STALL_MS = 3000;
constexpr float SAFE_OVERSPEED_RPM = 0.0f;           // 0 = désactivé ; mettre ≈ 1,1 × rpm max
constexpr int SAFE_MIN_VALID_PRESSURE = 2;
constexpr uint32_t SAFE_SENSOR_LOST_MS = 500;

// -----------------------------------------------------------------------------
//  Inclinomètre
// -----------------------------------------------------------------------------
// Choix à la compilation : -DUSE_ADXL355 pour l'option ADXL355 (défaut : SCL3300-D01)
constexpr uint32_t SPI_SCL3300_HZ = 4000000;         // 4 MHz max
constexpr uint32_t SPI_ADXL355_HZ = 4000000;
constexpr uint32_t SPI_ADS1220_HZ = 2000000;
constexpr uint32_t TILT_TIMEOUT_MS = 1000;           // sans échantillon valide → invalide
constexpr int TILT_AVG_SAMPLES = 50;                 // moyenne glissante de la pente (50 × 100 ms = 5 s)

// -----------------------------------------------------------------------------
//  Nivellement : mécanique (valeurs de départ, à remplacer par la CAO)  [À VALIDER]
// -----------------------------------------------------------------------------
constexpr float LEVEL_SCREW_PITCH_MM = 0.5f;         // vis de réglage fin
constexpr float LEVEL_GEAR_RATIO = 10.0f;            // réducteur planétaire 10:1
constexpr int LEVEL_FULL_STEPS = 200;
constexpr int LEVEL_MICROSTEPS = 16;
// Positions des vérins A et B par rapport au pivot fixe [mm] (repère plaque, X vers A)
constexpr float LEVEL_ACT_X_MM[2] = {400.0f, 0.0f};
constexpr float LEVEL_ACT_Y_MM[2] = {0.0f, 400.0f};
constexpr uint32_t LEVEL_TMC_RUN_MA = 800;           // courant RMS de marche
constexpr float LEVEL_TMC_HOLD_MULT = 0.25f;         // courant de maintien (échauffement = dérive thermique)
constexpr uint32_t LEVEL_STEP_TICK_HZ = 20000;       // fréquence de l'ISR de pas
constexpr uint32_t LEVEL_VMAX_SPS = 3000;            // vitesse max [micro-pas/s]
constexpr uint32_t LEVEL_ACCEL_SPS2 = 15000;
constexpr uint32_t LEVEL_HOMING_SPS = 400;
constexpr float LEVEL_DEADBAND_URAD = 1.5f * DESIGN_LEVEL_RES_URAD;   // 3 µrad
constexpr int LEVEL_CONFIRM_N = 5;
constexpr float LEVEL_GAIN = 0.8f;
constexpr float LEVEL_MAX_MOVE_URAD = 200.0f;
constexpr uint32_t LEVEL_SETTLE_MS = 6000;           // > fenêtre de moyenne (5 s) : mesure renouvelée avant tout nouveau mouvement

// -----------------------------------------------------------------------------
//  Capteurs de déplacement analogiques (option, via ADS1220)   [À VALIDER]
// -----------------------------------------------------------------------------
constexpr int NUM_DISP = 3;
constexpr float DISP_SENS_UM_PER_V[NUM_DISP] = {1000.0f, 1000.0f, 1000.0f};
constexpr float DISP_OFFSET_UM[NUM_DISP] = {0.0f, 0.0f, 0.0f};
constexpr float DISP_DIVIDER[NUM_DISP] = {1.0f, 1.0f, 1.0f};    // pont diviseur d'entrée

// -----------------------------------------------------------------------------
//  Liaison série
// -----------------------------------------------------------------------------
constexpr uint32_t SERIAL_BAUD = 115200;             // ignoré en USB CDC natif
constexpr size_t SERIAL_LINE_MAX = 120;
constexpr size_t JSON_BUF = 1100;
