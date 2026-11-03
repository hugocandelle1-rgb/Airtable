#include "settings.h"

#include <Preferences.h>

static const char* kNs = "airtable";

void Settings::load() {
  Preferences p;
  if (!p.begin(kNs, true)) return;
  tilt_use_mask = p.getUChar("tuse", 0x0F);
  for (int i = 0; i < atc::kMaxTilt; ++i) {
    char k[12];
    atc::SensorCal& c = sens[i];
    snprintf(k, sizeof k, "tb%dx", i); c.geo.bias_x_urad = p.getFloat(k, 0.0f);
    snprintf(k, sizeof k, "tb%dy", i); c.geo.bias_y_urad = p.getFloat(k, 0.0f);
    snprintf(k, sizeof k, "tr%d", i);  c.geo.mount_rot_deg = p.getFloat(k, 0.0f);
    snprintf(k, sizeof k, "tsx%d", i); c.geo.sign_x = p.getFloat(k, 1.0f);
    snprintf(k, sizeof k, "tsy%d", i); c.geo.sign_y = p.getFloat(k, 1.0f);
    snprintf(k, sizeof k, "to%d", i);  c.th.order = p.getUChar(k, 0);
    if (c.th.order > 2) c.th.order = 0;
    snprintf(k, sizeof k, "tt%d", i);  c.th.t_ref_C = p.getFloat(k, 20.0f);
    snprintf(k, sizeof k, "t1x%d", i); c.th.c1[0] = p.getFloat(k, 0.0f);
    snprintf(k, sizeof k, "t1y%d", i); c.th.c1[1] = p.getFloat(k, 0.0f);
    snprintf(k, sizeof k, "t2x%d", i); c.th.c2[0] = p.getFloat(k, 0.0f);
    snprintf(k, sizeof k, "t2y%d", i); c.th.c2[1] = p.getFloat(k, 0.0f);
  }
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
  p.putUChar("tuse", tilt_use_mask);
  for (int i = 0; i < atc::kMaxTilt; ++i) {
    char k[12];
    const atc::SensorCal& c = sens[i];
    snprintf(k, sizeof k, "tb%dx", i); p.putFloat(k, c.geo.bias_x_urad);
    snprintf(k, sizeof k, "tb%dy", i); p.putFloat(k, c.geo.bias_y_urad);
    snprintf(k, sizeof k, "tr%d", i);  p.putFloat(k, c.geo.mount_rot_deg);
    snprintf(k, sizeof k, "tsx%d", i); p.putFloat(k, c.geo.sign_x);
    snprintf(k, sizeof k, "tsy%d", i); p.putFloat(k, c.geo.sign_y);
    snprintf(k, sizeof k, "to%d", i);  p.putUChar(k, c.th.order);
    snprintf(k, sizeof k, "tt%d", i);  p.putFloat(k, c.th.t_ref_C);
    snprintf(k, sizeof k, "t1x%d", i); p.putFloat(k, c.th.c1[0]);
    snprintf(k, sizeof k, "t1y%d", i); p.putFloat(k, c.th.c1[1]);
    snprintf(k, sizeof k, "t2x%d", i); p.putFloat(k, c.th.c2[0]);
    snprintf(k, sizeof k, "t2y%d", i); p.putFloat(k, c.th.c2[1]);
  }
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
