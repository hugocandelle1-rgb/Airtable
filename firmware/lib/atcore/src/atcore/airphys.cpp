#include "atcore/airphys.h"

#include <math.h>

namespace atc {

float saturationVaporPressure_Pa(float T_C) {
  return 611.2f * expf(17.62f * T_C / (243.12f + T_C));
}

float airDensity(float p, float T_C, float rh) {
  if (rh < 0.0f) rh = 0.0f;
  if (rh > 100.0f) rh = 100.0f;
  const float T = T_C + 273.15f;
  const float e = rh * 0.01f * saturationVaporPressure_Pa(T_C);
  const float rd = 287.058f, rv = 461.495f;
  return (p - e) / (rd * T) + e / (rv * T);
}

}  // namespace atc
