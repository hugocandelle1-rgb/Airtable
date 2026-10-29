// Mini-implémentation du sous-ensemble de Unity utilisé par les tests de ce projet.
// Sert au Makefile (g++ seul, sans PlatformIO) : les mêmes sources de test compilent avec
// le vrai Unity de PlatformIO (`pio test -e native`), qui prend alors le pas sur ce fichier.
#pragma once
#include <math.h>
#include <setjmp.h>
#include <stdio.h>
#include <string.h>

namespace unity_shim {
inline jmp_buf& jb() { static jmp_buf b; return b; }
inline int& failed() { static int f = 0; return f; }
inline int& run() { static int n = 0; return n; }
inline int& testFailed() { static int f = 0; return f; }
inline const char*& curName() { static const char* s = ""; return s; }
inline void fail(const char* file, int line, const char* msg) {
  printf("%s:%d:%s:FAIL: %s\n", file, line, curName(), msg);
  testFailed() = 1;
  longjmp(jb(), 1);
}
inline void failf(const char* file, int line, const char* what, double expected, double actual) {
  char m[160];
  snprintf(m, sizeof m, "%s Expected %.9g Was %.9g", what, expected, actual);
  fail(file, line, m);
}
}  // namespace unity_shim

void setUp(void);
void tearDown(void);

#define UNITY_BEGIN() (printf("-- tests natifs (shim Unity) --\n"), 0)
#define UNITY_END() (printf("%d Tests %d Failures\n%s\n", unity_shim::run(), unity_shim::failed(), \
                            unity_shim::failed() ? "FAIL" : "OK"), unity_shim::failed())
#define RUN_TEST(fn)                                  \
  do {                                                \
    unity_shim::curName() = #fn;                      \
    unity_shim::testFailed() = 0;                     \
    ++unity_shim::run();                              \
    setUp();                                          \
    if (setjmp(unity_shim::jb()) == 0) { fn(); }      \
    tearDown();                                       \
    if (unity_shim::testFailed()) ++unity_shim::failed(); \
    else printf("%s:PASS\n", #fn);                    \
  } while (0)

#define TEST_FAIL_MESSAGE(m) unity_shim::fail(__FILE__, __LINE__, (m))
#define TEST_ASSERT_TRUE(c) do { if (!(c)) unity_shim::fail(__FILE__, __LINE__, "Expected TRUE Was FALSE"); } while (0)
#define TEST_ASSERT_FALSE(c) do { if (c) unity_shim::fail(__FILE__, __LINE__, "Expected FALSE Was TRUE"); } while (0)
#define TEST_ASSERT_TRUE_MESSAGE(c, m) do { if (!(c)) unity_shim::fail(__FILE__, __LINE__, (m)); } while (0)
#define TEST_ASSERT_NOT_NULL(p) do { if ((p) == nullptr) unity_shim::fail(__FILE__, __LINE__, "Expected NOT NULL"); } while (0)
#define TEST_ASSERT_EQUAL_INT(e, a) do { long long _e = (e), _a = (a); if (_e != _a) unity_shim::failf(__FILE__, __LINE__, "INT", (double)_e, (double)_a); } while (0)
#define TEST_ASSERT_EQUAL_INT32(e, a) TEST_ASSERT_EQUAL_INT(e, a)
#define TEST_ASSERT_EQUAL(e, a) TEST_ASSERT_EQUAL_INT(e, a)
#define TEST_ASSERT_EQUAL_UINT8(e, a) TEST_ASSERT_EQUAL_INT(e, a)
#define TEST_ASSERT_EQUAL_UINT16(e, a) TEST_ASSERT_EQUAL_INT(e, a)
#define TEST_ASSERT_EQUAL_UINT32(e, a) TEST_ASSERT_EQUAL_INT(e, a)
#define TEST_ASSERT_EQUAL_HEX8(e, a) TEST_ASSERT_EQUAL_INT(e, a)
#define TEST_ASSERT_EQUAL_HEX32(e, a) TEST_ASSERT_EQUAL_INT(e, a)
#define TEST_ASSERT_INT_WITHIN(d, e, a) do { long long _e = (e), _a = (a), _d = (d); if (llabs(_e - _a) > _d) unity_shim::failf(__FILE__, __LINE__, "INT_WITHIN", (double)_e, (double)_a); } while (0)
#define TEST_ASSERT_FLOAT_WITHIN(d, e, a) do { double _e = (e), _a = (a), _d = (d); if (!(fabs(_e - _a) <= _d)) unity_shim::failf(__FILE__, __LINE__, "FLOAT_WITHIN", _e, _a); } while (0)
#define TEST_ASSERT_EQUAL_STRING(e, a) do { const char* _e = (e); const char* _a = (a); if (strcmp(_e, _a) != 0) { char _m[400]; snprintf(_m, sizeof _m, "STRING Expected %.150s Was %.150s", _e, _a); unity_shim::fail(__FILE__, __LINE__, _m); } } while (0)
