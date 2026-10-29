// Tests : CRC, décodeurs de capteurs, physique de l'air, tachymètre, accumulateur d'inclinaison.
#include <unity.h>

#include <math.h>
#include <string.h>

#include "atcore/adxl355.h"
#include "atcore/ads1220.h"
#include "atcore/airphys.h"
#include "atcore/crc.h"
#include "atcore/inclinometer.h"
#include "atcore/scl3300.h"
#include "atcore/sdp8xx.h"
#include "atcore/tach.h"
#include "atcore/tmp117.h"

using namespace atc;

void setUp(void) {}
void tearDown(void) {}

void test_crc_sensirion_vecteur_fiche() {
  const uint8_t d[2] = {0xBE, 0xEF};
  TEST_ASSERT_EQUAL_HEX8(0x92, crc8Sensirion(d, 2));
  const uint8_t w[3] = {0xBE, 0xEF, 0x92};
  TEST_ASSERT_TRUE(sensirionWordOk(w));
  const uint8_t bad[3] = {0xBE, 0xEF, 0x93};
  TEST_ASSERT_FALSE(sensirionWordOk(bad));
}

void test_crc_scl3300_trames_connues() {
  // Trames de la fiche Murata : le CRC calculé doit redonner l'octet de poids faible.
  const uint32_t frames[] = {
      scl3300::kCmdBank0,     scl3300::kCmdBank1,       scl3300::kCmdReadAccX,  scl3300::kCmdReadAccY,
      scl3300::kCmdReadAccZ,  scl3300::kCmdReadSto,     scl3300::kCmdReadTemp,  scl3300::kCmdReadStatus,
      scl3300::kCmdReadAngX,  scl3300::kCmdReadAngY,    scl3300::kCmdReadAngZ,  scl3300::kCmdReadWhoAmI,
      scl3300::kCmdReadSerial1, scl3300::kCmdReadSerial2, scl3300::kCmdSetMode1, scl3300::kCmdSetMode2,
      scl3300::kCmdSetMode3,  scl3300::kCmdSetMode4,    scl3300::kCmdSwReset,   scl3300::kCmdEnableAngles};
  for (uint32_t f : frames) {
    TEST_ASSERT_EQUAL_HEX8(f & 0xFF, crc8Scl3300(f));
  }
  TEST_ASSERT_EQUAL_HEX32(scl3300::kCmdReadAccX, scl3300::makeFrame(0x04, 0x0000));
  TEST_ASSERT_EQUAL_HEX32(scl3300::kCmdSetMode4, scl3300::makeFrame(0xB4, 0x0003));
  TEST_ASSERT_EQUAL_HEX32(scl3300::kCmdSwReset, scl3300::makeFrame(0xB4, 0x0020));
}

void test_scl3300_parse_reponse() {
  const uint32_t f = scl3300::makeFrame(0x05, 0xFFF6);   // RS = 01, donnée = −10
  const scl3300::Response r = scl3300::parseResponse(f);
  TEST_ASSERT_TRUE(r.crc_ok);
  TEST_ASSERT_EQUAL_UINT8(1, r.rs);
  TEST_ASSERT_EQUAL_INT(-10, scl3300::toSigned(r.data));
  // Corruption d'un bit de donnée : le CRC doit le détecter.
  TEST_ASSERT_FALSE(scl3300::parseResponse(f ^ 0x00000100u).crc_ok);
}

void test_scl3300_conversions() {
  TEST_ASSERT_FLOAT_WITHIN(1e-6, 1.0, scl3300::accToG(12000, scl3300::Mode::M4));
  TEST_ASSERT_FLOAT_WITHIN(1e-6, 1.0, scl3300::accToG(6000, scl3300::Mode::M1));
  TEST_ASSERT_FLOAT_WITHIN(0.05, 25.0, scl3300::tempC(static_cast<uint16_t>((25.0 + 273.0) * 18.9)));
  TEST_ASSERT_FLOAT_WITHIN(1e-4, 90.0, scl3300::angleDeg(16384));
}

void test_tilt_from_acc_signe_et_amplitude() {
  float tx, ty;
  const float th = 100e-6f;   // 100 µrad, +X vers le haut
  scl3300::tiltFromAcc(sinf(th), 0.0f, cosf(th), &tx, &ty);
  TEST_ASSERT_FLOAT_WITHIN(0.01, 100.0, tx);
  TEST_ASSERT_FLOAT_WITHIN(0.01, 0.0, ty);
  scl3300::tiltFromAcc(0.0f, -sinf(th), cosf(th), &tx, &ty);
  TEST_ASSERT_FLOAT_WITHIN(0.01, -100.0, ty);
}

void test_acc_accumulator_dithering_sub_lsb() {
  // Vrai angle 20 µrad = 0,24 LSB (12000 LSB/g) : un échantillon quantifié vaut 0 ou 1 LSB,
  // mais la moyenne d'un signal bruité retrouve la valeur à quelques µrad.
  AccAccumulator acc;
  uint32_t s = 12345;
  auto rnd = [&]() { s = s * 1664525u + 1013904223u; return (s >> 8) / 16777216.0f; };
  const double true_g = 20e-6;
  for (int i = 0; i < 4000; ++i) {
    double noise = (rnd() + rnd() + rnd() - 1.5f) * 2.0 / 12000.0;   // ≈ 1 LSB rms
    int raw = static_cast<int>(lround((true_g + noise) * 12000.0));
    acc.add(static_cast<float>(raw) / 12000.0f, 0.0f, 1.0f, 25.0f);
  }
  TiltSample t;
  TEST_ASSERT_TRUE(acc.flush(&t));
  TEST_ASSERT_TRUE(t.valid);
  TEST_ASSERT_EQUAL_UINT16(4000, t.n_avg);
  TEST_ASSERT_FLOAT_WITHIN(5.0, 20.0, t.x_urad);
  TEST_ASSERT_FALSE(acc.flush(&t));   // vidé
}

void test_sdp8xx_decodage() {
  // dp = +150 / 60 = 2,5 Pa ; T = 21,5 °C → 4300 ; échelle 60
  uint8_t b[9];
  auto word = [&](int i, int16_t v) {
    b[i] = static_cast<uint8_t>(static_cast<uint16_t>(v) >> 8);
    b[i + 1] = static_cast<uint8_t>(v & 0xFF);
    b[i + 2] = crc8Sensirion(&b[i], 2);
  };
  word(0, 150); word(3, 4300); word(6, 60);
  Sdp8xxSample s;
  TEST_ASSERT_TRUE(decodeSdp8xx(b, 60.0f, &s));
  TEST_ASSERT_FLOAT_WITHIN(1e-4, 2.5, s.dp_Pa);
  TEST_ASSERT_FLOAT_WITHIN(1e-3, 21.5, s.temp_C);
  TEST_ASSERT_FLOAT_WITHIN(1e-4, 60.0, s.scale);
  word(0, -300);   // pression négative
  TEST_ASSERT_TRUE(decodeSdp8xx(b, 60.0f, &s));
  TEST_ASSERT_FLOAT_WITHIN(1e-4, -5.0, s.dp_Pa);
  b[4] ^= 0x01;    // corruption de la température
  TEST_ASSERT_FALSE(decodeSdp8xx(b, 60.0f, &s));
  TEST_ASSERT_FALSE(s.ok);
}

void test_sdp8xx_echelle_repli() {
  uint8_t b[9];
  auto word = [&](int i, int16_t v) {
    b[i] = static_cast<uint8_t>(static_cast<uint16_t>(v) >> 8);
    b[i + 1] = static_cast<uint8_t>(v & 0xFF);
    b[i + 2] = crc8Sensirion(&b[i], 2);
  };
  word(0, 240); word(3, 0); word(6, 0);   // échelle lue = 0 → repli
  Sdp8xxSample s;
  TEST_ASSERT_TRUE(decodeSdp8xx(b, 240.0f, &s));
  TEST_ASSERT_FLOAT_WITHIN(1e-4, 1.0, s.dp_Pa);
}

void test_debit_buse_et_densite() {
  const float rho = airDensity(101325.0f, 20.0f, 0.0f);
  TEST_ASSERT_FLOAT_WITHIN(0.002, 1.2041, rho);
  TEST_ASSERT_TRUE(airDensity(101325.0f, 20.0f, 60.0f) < rho);          // l'air humide est plus léger
  TEST_ASSERT_TRUE(airDensity(95000.0f, 20.0f, 0.0f) < rho);
  // Buse Ø20 mm, Cd 0,97, Δp 25 Pa : v = √(2·25/1,204) = 6,444 m/s ; Q = 0,97·3,1416e-4·6,444
  const float A = nozzleArea_m2(20.0f);
  TEST_ASSERT_FLOAT_WITHIN(1e-8, 3.14159e-4, A);
  const float q = nozzleFlow_m3s(25.0f, 1.204f, 0.97f, A);
  TEST_ASSERT_FLOAT_WITHIN(2e-6, 0.97 * 3.14159e-4 * 6.4437, q);
  TEST_ASSERT_TRUE(nozzleFlow_m3s(-25.0f, 1.204f, 0.97f, A) < 0.0f);
  TEST_ASSERT_FLOAT_WITHIN(1e-9, 0.0, nozzleFlow_m3s(0.0f, 1.204f, 0.97f, A));
}

void test_tmp117_adxl355_ads1220() {
  TEST_ASSERT_FLOAT_WITHIN(1e-4, 25.0, tmp117::toC(3200));          // 25 °C / 0,0078125
  TEST_ASSERT_FLOAT_WITHIN(1e-4, -0.0078125, tmp117::toC(0xFFFF));
  TEST_ASSERT_FALSE(tmp117::plausible(0x8000));
  // ADXL355 : +1 g en ±2 g = 256000 LSB = 0x3E800 → octets cadrés à gauche
  const int32_t raw = 256000;
  const uint8_t b3 = (raw >> 12) & 0xFF, b2 = (raw >> 4) & 0xFF, b1 = (raw & 0x0F) << 4;
  TEST_ASSERT_EQUAL_INT32(raw, adxl355::raw20(b3, b2, b1));
  TEST_ASSERT_EQUAL_INT32(-1, adxl355::raw20(0xFF, 0xFF, 0xF0));
  TEST_ASSERT_FLOAT_WITHIN(1e-6, 1.0, adxl355::toG(raw, adxl355::Range::G2));
  TEST_ASSERT_EQUAL_UINT8(0x11, adxl355::spiRead(0x08));            // 0x08<<1 | 1
  TEST_ASSERT_EQUAL_UINT8(0x5A, adxl355::spiWrite(0x2D));
  // ADS1220 : pleine échelle = Vref/gain
  TEST_ASSERT_EQUAL_INT32(-1, ads1220::raw24(0xFF, 0xFF, 0xFF));
  TEST_ASSERT_FLOAT_WITHIN(1e-6, 2.048, ads1220::toVolts(8388607 + 1, 2.048f, 1));
  TEST_ASSERT_FLOAT_WITHIN(1e-6, 1.024, ads1220::toVolts(4194304, 2.048f, 1));
  TEST_ASSERT_FLOAT_WITHIN(1e-6, 0.256, ads1220::toVolts(4194304, 2.048f, 4));
  ads1220::Config c;
  c.mux = ads1220::kAin1Avss; c.gain = ads1220::kG1; c.rate = ads1220::kSps90;
  uint8_t r[4];
  ads1220::encodeRegisters(c, r);
  TEST_ASSERT_EQUAL_HEX8(0x91, r[0]);   // MUX 1001, gain 000, PGA bypass 1
  TEST_ASSERT_EQUAL_HEX8(0x40, r[1]);   // 90 SPS (010), mode normal, single-shot
  TEST_ASSERT_EQUAL_HEX8(0x10, r[2]);   // Vref interne, FIR 50/60 Hz
  TEST_ASSERT_EQUAL_HEX8(0x43, ads1220::cmdWreg(0, 3));
  TEST_ASSERT_EQUAL_HEX8(0x23, ads1220::cmdRreg(0, 3));
  ads1220::DispChannelCal cal; cal.sens_um_per_V = 500.0f; cal.offset_um = -10.0f; cal.divider = 2.0f;
  TEST_ASSERT_FLOAT_WITHIN(1e-4, 490.0, ads1220::toMicrometers(0.5f, cal));
}

void test_tach_estimateur() {
  TachEstimator t;
  t.configure(2.0f, 300000, 1500000);
  // 3000 tr/min = 100 impulsions/s (2 imp/tr), échantillonné à 10 Hz
  uint32_t count = 0, now = 0;
  for (int k = 0; k < 30; ++k) {
    now += 100000;
    count = k * 10 + 10;
    t.sample(now, count, now - 20000);
  }
  TEST_ASSERT_FLOAT_WITHIN(15.0, 3000.0, t.rpm());
  // Arrêt : plus aucun front pendant 2 s
  for (int k = 0; k < 20; ++k) { now += 100000; t.sample(now, count, now - (k + 1) * 100000 - 20000 + 0); }
  TEST_ASSERT_FLOAT_WITHIN(0.1, 0.0, t.rpm());
}

void test_tach_bas_regime_et_debordement() {
  TachEstimator t;
  t.configure(2.0f, 400000, 1500000);
  // 300 tr/min = 10 imp/s, horloge µs proche du débordement 32 bits
  uint32_t now = 0xFFFFFFFFu - 1000000u;
  uint32_t count = 0xFFFFFFF0u;   // compteur aussi près du débordement
  for (int k = 0; k < 40; ++k) {
    now += 100000;
    count += 1;                    // 1 front par 100 ms
    t.sample(now, count, now - 5000);
  }
  TEST_ASSERT_FLOAT_WITHIN(5.0, 300.0, t.rpm());
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_crc_sensirion_vecteur_fiche);
  RUN_TEST(test_crc_scl3300_trames_connues);
  RUN_TEST(test_scl3300_parse_reponse);
  RUN_TEST(test_scl3300_conversions);
  RUN_TEST(test_tilt_from_acc_signe_et_amplitude);
  RUN_TEST(test_acc_accumulator_dithering_sub_lsb);
  RUN_TEST(test_sdp8xx_decodage);
  RUN_TEST(test_sdp8xx_echelle_repli);
  RUN_TEST(test_debit_buse_et_densite);
  RUN_TEST(test_tmp117_adxl355_ads1220);
  RUN_TEST(test_tach_estimateur);
  RUN_TEST(test_tach_bas_regime_et_debordement);
  return UNITY_END();
}
