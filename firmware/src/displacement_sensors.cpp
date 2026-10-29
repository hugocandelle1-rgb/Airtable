#include "displacement_sensors.h"

#include "atcore/ads1220.h"

using namespace atc;

static const uint8_t kMuxForChannel[NUM_DISP] = {ads1220::kAin0Avss, ads1220::kAin1Avss, ads1220::kAin2Avss};

void DisplacementSensors::spiCmd(uint8_t cmd) {
  spi_->beginTransaction(SPISettings(SPI_ADS1220_HZ, MSBFIRST, SPI_MODE1));
  digitalWrite(PIN_CS_ADS1220, LOW);
  spi_->transfer(cmd);
  digitalWrite(PIN_CS_ADS1220, HIGH);
  spi_->endTransaction();
}

void DisplacementSensors::writeReg(uint8_t reg, uint8_t v) {
  spi_->beginTransaction(SPISettings(SPI_ADS1220_HZ, MSBFIRST, SPI_MODE1));
  digitalWrite(PIN_CS_ADS1220, LOW);
  spi_->transfer(ads1220::cmdWreg(reg, 0));
  spi_->transfer(v);
  digitalWrite(PIN_CS_ADS1220, HIGH);
  spi_->endTransaction();
}

uint8_t DisplacementSensors::readReg(uint8_t reg) {
  spi_->beginTransaction(SPISettings(SPI_ADS1220_HZ, MSBFIRST, SPI_MODE1));
  digitalWrite(PIN_CS_ADS1220, LOW);
  spi_->transfer(ads1220::cmdRreg(reg, 0));
  const uint8_t v = spi_->transfer(0);
  digitalWrite(PIN_CS_ADS1220, HIGH);
  spi_->endTransaction();
  return v;
}

static ads1220::Config channelConfig(int ch) {
  ads1220::Config c;
  c.mux = kMuxForChannel[ch];
  c.gain = ads1220::kG1;
  c.pga_bypass = true;
  c.rate = ads1220::kSps90;
  c.continuous = false;
  c.vref = ads1220::kVrefInternal;
  c.fir = 1;                                  // rejet 50/60 Hz
  return c;
}

bool DisplacementSensors::begin(SPIClass& spi) {
  spi_ = &spi;
  pinMode(PIN_CS_ADS1220, OUTPUT);
  digitalWrite(PIN_CS_ADS1220, HIGH);
  pinMode(PIN_ADS1220_DRDY, INPUT_PULLUP);
  delay(2);
  spiCmd(ads1220::kCmdReset);
  delay(2);
  uint8_t regs[4];
  ads1220::encodeRegisters(channelConfig(0), regs);
  for (uint8_t r = 0; r < 4; ++r) writeReg(r, regs[r]);
  present = true;
  for (uint8_t r = 0; r < 4; ++r) present = present && (readReg(r) == regs[r]);   // relecture : détecte l'absence
  for (int i = 0; i < NUM_DISP; ++i) valid[i] = false;
  if (present) startChannel(0);
  return present;
}

void DisplacementSensors::startChannel(int ch) {
  ch_ = ch;
  uint8_t regs[4];
  ads1220::encodeRegisters(channelConfig(ch), regs);
  writeReg(0, regs[0]);
  spiCmd(ads1220::kCmdStart);                 // START/SYNC : une conversion
  converting_ = true;
  t_start_ms_ = millis();
}

void DisplacementSensors::poll(uint32_t now_ms) {
  if (!present || !converting_) return;
  if (digitalRead(PIN_ADS1220_DRDY) == LOW) {   // conversion terminée
    spi_->beginTransaction(SPISettings(SPI_ADS1220_HZ, MSBFIRST, SPI_MODE1));
    digitalWrite(PIN_CS_ADS1220, LOW);
    spi_->transfer(ads1220::kCmdRdata);
    const uint8_t b2 = spi_->transfer(0), b1 = spi_->transfer(0), b0 = spi_->transfer(0);
    digitalWrite(PIN_CS_ADS1220, HIGH);
    spi_->endTransaction();
    const int32_t code = ads1220::raw24(b2, b1, b0);
    const float v = ads1220::toVolts(code, ads1220::vrefVolts(ads1220::kVrefInternal), 1);
    volts[ch_] = v;
    ads1220::DispChannelCal cal;
    cal.sens_um_per_V = DISP_SENS_UM_PER_V[ch_];
    cal.offset_um = DISP_OFFSET_UM[ch_];
    cal.divider = DISP_DIVIDER[ch_];
    um[ch_] = ads1220::toMicrometers(v, cal);
    valid[ch_] = true;
    startChannel((ch_ + 1) % NUM_DISP);
  } else if (now_ms - t_start_ms_ > 100) {    // pas de DRDY : relance et marque invalide
    valid[ch_] = false;
    ++errors_;
    startChannel(ch_);
  }
}
