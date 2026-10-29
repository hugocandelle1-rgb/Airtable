// Tests : analyse des commandes série et écrivain JSON.
#include <unity.h>

#include <math.h>
#include <stdio.h>
#include <string.h>

#include "atcore/commands.h"
#include "atcore/json.h"

using namespace atc;

void setUp(void) {}
void tearDown(void) {}

static Command parseOk(const char* line) {
  Command c;
  const ParseError e = parseCommand(line, &c);
  if (e != ParseError::Ok) {
    char m[120];
    snprintf(m, sizeof m, "'%s' rejetee: %s", line, parseErrorText(e));
    TEST_FAIL_MESSAGE(m);
  }
  return c;
}
static ParseError parseErr(const char* line) { Command c; return parseCommand(line, &c); }

void test_set_pression() {
  Command c = parseOk("SET P 120.0");
  TEST_ASSERT_TRUE(c.type == CmdType::SetP);
  TEST_ASSERT_FLOAT_WITHIN(1e-6, 120.0, c.f[0]);
  c = parseOk("  set   p   87.5  ");                       // casse et espaces tolérés
  TEST_ASSERT_TRUE(c.type == CmdType::SetP);
  TEST_ASSERT_FLOAT_WITHIN(1e-6, 87.5, c.f[0]);
  c = parseOk("SET P 1e2\r\n");                           // notation scientifique, CRLF
  TEST_ASSERT_FLOAT_WITHIN(1e-6, 100.0, c.f[0]);
}

void test_set_masse_duty_gains() {
  Command c = parseOk("SET MASS 5.0");
  TEST_ASSERT_TRUE(c.type == CmdType::SetMass);
  TEST_ASSERT_FLOAT_WITHIN(1e-6, 5.0, c.f[0]);
  c = parseOk("SET DUTY 0.35");
  TEST_ASSERT_TRUE(c.type == CmdType::SetDuty);
  c = parseOk("SET GAINS 0.8 1.0");
  TEST_ASSERT_TRUE(c.type == CmdType::SetGains);
  TEST_ASSERT_FLOAT_WITHIN(1e-6, 0.8, c.f[0]);
  TEST_ASSERT_FLOAT_WITHIN(1e-6, 1.0, c.f[1]);
  c = parseOk("SET NOZZLE 0.97 20");
  TEST_ASSERT_TRUE(c.type == CmdType::SetNozzle);
  c = parseOk("SET WDT 5");
  TEST_ASSERT_TRUE(c.type == CmdType::SetWdt);
  c = parseOk("SET RAMP 80");
  TEST_ASSERT_TRUE(c.type == CmdType::SetRamp);
}

void test_niveau() {
  Command c = parseOk("LEVEL AUTO ON");
  TEST_ASSERT_TRUE(c.type == CmdType::LevelAuto);
  TEST_ASSERT_TRUE(c.flag);
  c = parseOk("level auto off");
  TEST_ASSERT_FALSE(c.flag);
  c = parseOk("LEVEL MOVE X -25.5");
  TEST_ASSERT_TRUE(c.type == CmdType::LevelMove);
  TEST_ASSERT_EQUAL_INT(0, c.axis);
  TEST_ASSERT_FLOAT_WITHIN(1e-6, -25.5, c.f[0]);
  c = parseOk("LEVEL MOVE y 100");
  TEST_ASSERT_EQUAL_INT(1, c.axis);
  c = parseOk("LEVEL JOG B 50");
  TEST_ASSERT_TRUE(c.type == CmdType::LevelJog);
  TEST_ASSERT_EQUAL_INT(1, c.axis);
  TEST_ASSERT_TRUE(parseOk("LEVEL ZERO").type == CmdType::LevelZero);
  TEST_ASSERT_TRUE(parseOk("LEVEL HOME").type == CmdType::LevelHome);
  TEST_ASSERT_TRUE(parseOk("LEVEL STOP").type == CmdType::LevelStop);
  c = parseOk("LEVEL TARGET 12 -3.5");
  TEST_ASSERT_TRUE(c.type == CmdType::LevelTarget);
  TEST_ASSERT_FLOAT_WITHIN(1e-6, -3.5, c.f[1]);
  c = parseOk("LEVEL DEADBAND 2.5");
  TEST_ASSERT_TRUE(c.type == CmdType::LevelDeadband);
}

void test_divers() {
  TEST_ASSERT_TRUE(parseOk("PING").type == CmdType::Ping);
  TEST_ASSERT_TRUE(parseOk("GET STATUS").type == CmdType::GetStatus);
  TEST_ASSERT_TRUE(parseOk("get config").type == CmdType::GetConfig);
  TEST_ASSERT_TRUE(parseOk("GET VERSION").type == CmdType::GetVersion);
  TEST_ASSERT_TRUE(parseOk("CLEAR").type == CmdType::Clear);
  TEST_ASSERT_TRUE(parseOk("SAFE").type == CmdType::Safe);
  TEST_ASSERT_TRUE(parseOk("FAN ON").type == CmdType::FanOn);
  TEST_ASSERT_TRUE(parseOk("FAN OFF").type == CmdType::FanOff);
  Command c = parseOk("STREAM ON 10");
  TEST_ASSERT_TRUE(c.type == CmdType::StreamOn);
  TEST_ASSERT_FLOAT_WITHIN(1e-6, 10.0, c.f[0]);
  TEST_ASSERT_FLOAT_WITHIN(1e-6, 10.0, parseOk("STREAM ON").f[0]);   // cadence par défaut
  TEST_ASSERT_TRUE(parseOk("STREAM OFF").type == CmdType::StreamOff);
  c = parseOk("TABLE ADD 2.0 70.5");
  TEST_ASSERT_TRUE(c.type == CmdType::TableAdd);
  TEST_ASSERT_FLOAT_WITHIN(1e-6, 70.5, c.f[1]);
  TEST_ASSERT_TRUE(parseOk("TABLE CLEAR").type == CmdType::TableClear);
  TEST_ASSERT_TRUE(parseOk("TABLE H 120").type == CmdType::TableH);
  c = parseOk("CAL TILT BIAS 12.5 -8");
  TEST_ASSERT_TRUE(c.type == CmdType::CalTiltBias);
  TEST_ASSERT_FLOAT_WITHIN(1e-6, -8.0, c.f[1]);
  TEST_ASSERT_TRUE(parseOk("CAL TILT ROT 90").type == CmdType::CalTiltRot);
  TEST_ASSERT_TRUE(parseOk("CAL TILT CLEAR").type == CmdType::CalTiltClear);
  TEST_ASSERT_TRUE(parseOk("CAL PZERO").type == CmdType::CalPZero);
}

void test_erreurs() {
  TEST_ASSERT_TRUE(parseErr("") == ParseError::Empty);
  TEST_ASSERT_TRUE(parseErr("   \t ") == ParseError::Empty);
  TEST_ASSERT_TRUE(parseErr("FOO") == ParseError::UnknownCommand);
  TEST_ASSERT_TRUE(parseErr("GET") == ParseError::MissingArg);
  TEST_ASSERT_TRUE(parseErr("GET TRUC") == ParseError::UnknownCommand);
  TEST_ASSERT_TRUE(parseErr("SET P") == ParseError::MissingArg);
  TEST_ASSERT_TRUE(parseErr("SET P 100 200") == ParseError::ExtraArg);
  TEST_ASSERT_TRUE(parseErr("SET P abc") == ParseError::BadNumber);
  TEST_ASSERT_TRUE(parseErr("SET P 12x") == ParseError::BadNumber);       // reste non numérique
  TEST_ASSERT_TRUE(parseErr("SET P nan") == ParseError::BadNumber);
  TEST_ASSERT_TRUE(parseErr("SET P inf") == ParseError::BadNumber);
  TEST_ASSERT_TRUE(parseErr("SET P -5") == ParseError::OutOfRange);
  TEST_ASSERT_TRUE(parseErr("SET P 99999") == ParseError::OutOfRange);
  TEST_ASSERT_TRUE(parseErr("SET DUTY 1.5") == ParseError::OutOfRange);
  TEST_ASSERT_TRUE(parseErr("SET MASS 0") == ParseError::OutOfRange);
  TEST_ASSERT_TRUE(parseErr("LEVEL MOVE Z 10") == ParseError::BadAxis);
  TEST_ASSERT_TRUE(parseErr("LEVEL MOVE A 10") == ParseError::BadAxis);   // A/B réservés à JOG
  TEST_ASSERT_TRUE(parseErr("LEVEL JOG X 10") == ParseError::BadAxis);
  TEST_ASSERT_TRUE(parseErr("LEVEL MOVE X 1e6") == ParseError::OutOfRange);
  TEST_ASSERT_TRUE(parseErr("LEVEL AUTO MAYBE") == ParseError::BadFlag);
  TEST_ASSERT_TRUE(parseErr("FAN") == ParseError::MissingArg);
  TEST_ASSERT_TRUE(parseErr("STREAM ON 1000") == ParseError::OutOfRange);
  TEST_ASSERT_TRUE(parseErr("PING PONG") == ParseError::ExtraArg);
  char longline[300];
  memset(longline, 'A', sizeof longline - 1);
  longline[sizeof longline - 1] = '\0';
  TEST_ASSERT_TRUE(parseErr(longline) == ParseError::TooLong);
  TEST_ASSERT_TRUE(parseErr("A B C D E F G H") == ParseError::ExtraArg);
  TEST_ASSERT_EQUAL_STRING("out_of_range", parseErrorText(ParseError::OutOfRange));
}

void test_erreur_ne_modifie_pas_commande_valide() {
  Command c;
  TEST_ASSERT_TRUE(parseCommand("SET P abc", &c) != ParseError::Ok);
  TEST_ASSERT_TRUE(c.type == CmdType::SetP || c.type == CmdType::None);   // jamais une commande exécutable fantôme
}

// ---- JSON ----------------------------------------------------------------------------------

void test_json_objet_status() {
  char buf[256];
  JsonWriter j(buf, sizeof buf);
  const float p[3] = {101.25f, 100.5f, 99.0f};
  j.beginObject().kv("t", static_cast<uint32_t>(12345)).kvArray("p", p, 3, 1).kv("pwm", 42.5f, 1)
      .kv("ok", true).kv("name", "a\"b").key("o").beginObject().kv("n", static_cast<int32_t>(-3)).endObject()
      .endObject();
  TEST_ASSERT_TRUE(j.ok());
  TEST_ASSERT_EQUAL_STRING("{\"t\":12345,\"p\":[101.2,100.5,99.0],\"pwm\":42.5,\"ok\":true,\"name\":\"a\\\"b\",\"o\":{\"n\":-3}}", buf);
}

void test_json_nan_zero_negatif_debordement() {
  char buf[64];
  JsonWriter j(buf, sizeof buf);
  j.beginArray().value(NAN, 2).value(-0.001f, 2).value(INFINITY, 1).endArray();
  TEST_ASSERT_EQUAL_STRING("[null,0.00,null]", buf);
  char tiny[8];
  JsonWriter k(tiny, sizeof tiny);
  k.beginObject().kv("une_cle_trop_longue", 1.0f).endObject();
  TEST_ASSERT_FALSE(k.ok());                 // débordement détecté, tampon toujours terminé par \0
  TEST_ASSERT_TRUE(strlen(tiny) < sizeof tiny);
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_set_pression);
  RUN_TEST(test_set_masse_duty_gains);
  RUN_TEST(test_niveau);
  RUN_TEST(test_divers);
  RUN_TEST(test_erreurs);
  RUN_TEST(test_erreur_ne_modifie_pas_commande_valide);
  RUN_TEST(test_json_objet_status);
  RUN_TEST(test_json_nan_zero_negatif_debordement);
  return UNITY_END();
}
