// GÉNÉRÉ par firmware/tools/gen_design_params.py depuis params/design.toml — NE PAS ÉDITER.
// params/design.toml : version V3.0-baseline (2026-10-29)
#pragma once

// Plage de pression plenum de consigne [Pa]
#define DESIGN_P_MIN_PA            30.0f
#define DESIGN_P_MAX_PA            400.0f
#define DESIGN_P_REGULATION_PA     0.30f   // stabilité visée
// Ventilateur(s)
#define DESIGN_FAN_COUNT           1
#define DESIGN_FAN_PWM_HZ          25000
// Palets
#define DESIGN_PUCK_MASS_MIN_G     2.00f
#define DESIGN_PUCK_MASS_MAX_G     10.00f
// Nivellement
#define DESIGN_LEVEL_RES_URAD      2.00f
#define DESIGN_LEVEL_RANGE_URAD    4363.3f   // course ± (0.25 deg)
#define DESIGN_SLOPE_PEAK_URAD     50.0f
#define DESIGN_TILT_STABILITY_URAD 5.0f
#define DESIGN_THERMAL_GRADIENT_K  0.050f
// Air
#define DESIGN_AIR_RHO             1.2040f
#define DESIGN_G                   9.810f
