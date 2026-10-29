// Propriétés de l'air (densité à partir de BME280) — logique pure.
#pragma once

namespace atc {

// Pression de vapeur saturante [Pa] (formule de Magnus, −45…60 °C).
float saturationVaporPressure_Pa(float T_C);
// Densité de l'air humide [kg/m³] : p_atm [Pa], T [°C], humidité relative [0..100 %].
float airDensity(float p_atm_Pa, float T_C, float rh_pct);

}  // namespace atc
