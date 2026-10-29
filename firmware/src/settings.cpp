#include "settings.h"

#include <Preferences.h>

static const char* kNs = "airtable";

void Settings::load() {
  Preferences p;
  if (!p.begin(kNs, true)) return;
  tilt.bias_x_urad = p.getFloat("tbx", 0.0f);
  tilt.bias_y_urad = p.getFloat("tby", 0.0f);
  tilt.mount_rot_deg = p.getFloat("trot", 0.0f);
  tilt.sign_x = p.getFloat("tsx", 1.0f);
  tilt.sign_y = p.getFloat("tsy", 1.0f);
  for (int i = 0; i < NUM_PLENUM_SENSORS; ++i) {
    char k[8];
    snprintf(k, sizeof k, "pz%d", i);
    p_offset[i] = p.getFloat(k, 0.0f);
  }
  nozzle_offset = p.getFloat("pzn", 0.0f);
  nozzle_cd = p.getFloat("ncd", NOZZLE_CD_DEFAULT);
  nozzle_diam_mm = p.getFloat("nd", NOZZLE_DIAM_MM_DEFAULT);
  fan_p_full = p.getFloat("pfull", FAN_P_FULL_PA);
  level_target_x = p.getFloat("ltx", 0.0f);
  level_target_y = p.getFloat("lty", 0.0f);
  level_deadband = p.getFloat("ldb", LEVEL_DEADBAND_URAD);
  p.end();
}

bool Settings::save() const {
  Preferences p;
  if (!p.begin(kNs, false)) return false;
  p.putFloat("tbx", tilt.bias_x_urad);
  p.putFloat("tby", tilt.bias_y_urad);
  p.putFloat("trot", tilt.mount_rot_deg);
  p.putFloat("tsx", tilt.sign_x);
  p.putFloat("tsy", tilt.sign_y);
  for (int i = 0; i < NUM_PLENUM_SENSORS; ++i) {
    char k[8];
    snprintf(k, sizeof k, "pz%d", i);
    p.putFloat(k, p_offset[i]);
  }
  p.putFloat("pzn", nozzle_offset);
  p.putFloat("ncd", nozzle_cd);
  p.putFloat("nd", nozzle_diam_mm);
  p.putFloat("pfull", fan_p_full);
  p.putFloat("ltx", level_target_x);
  p.putFloat("lty", level_target_y);
  p.putFloat("ldb", level_deadband);
  p.end();
  return true;
}
