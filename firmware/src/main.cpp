// Contrôleur de la table à coussin d'air — point d'entrée.
// Toute la logique est dans App (src/app.cpp, src/console.cpp) et dans la bibliothèque
// portable lib/atcore (testée sur PC : `make -C firmware test` ou `pio test -e native`).
#include <Arduino.h>

#include "app.h"

static App g_app;

void setup() { g_app.begin(); }

void loop() { g_app.tick(); }
