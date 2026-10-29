# Tests unitaires de la logique pure SANS PlatformIO (g++ seul).
#   make test      compile et exécute toutes les suites test/test_*/
#   make syntax    g++ -fsyntax-only de toute la bibliothèque portable (atcore)
#   make clean
# Les mêmes sources de test sont utilisées par `pio test -e native` (vrai Unity).
CXX      ?= g++
CXXFLAGS ?= -std=c++17 -O1 -g -Wall -Wextra -Wpedantic -Wno-unused-parameter
INC      := -Ilib/atcore/src -Itools/unity_shim
LIBSRC   := $(wildcard lib/atcore/src/atcore/*.cpp)
SUITES   := $(notdir $(wildcard test/test_*))
BUILD    := .build_native

.PHONY: test syntax clean $(SUITES)

test: $(SUITES)
	@echo "=== toutes les suites natives sont passées ==="

$(SUITES): %:
	@mkdir -p $(BUILD)
	$(CXX) $(CXXFLAGS) $(INC) -Itest/$@ test/$@/*.cpp $(LIBSRC) -o $(BUILD)/$@
	@$(BUILD)/$@

syntax:
	@for f in $(LIBSRC); do $(CXX) $(CXXFLAGS) $(INC) -fsyntax-only $$f || exit 1; done
	@echo "syntax OK ($(words $(LIBSRC)) fichiers)"

clean:
	rm -rf $(BUILD)
