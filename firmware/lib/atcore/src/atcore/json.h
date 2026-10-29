// Écrivain JSON minimal dans un tampon fixe (pas d'allocation, pas de String Arduino).
// Les virgules sont gérées automatiquement ; NaN/inf sont émis comme null.
#pragma once
#include <stddef.h>
#include <stdint.h>

namespace atc {

class JsonWriter {
 public:
  JsonWriter(char* buf, size_t cap);

  JsonWriter& beginObject();
  JsonWriter& endObject();
  JsonWriter& beginArray();
  JsonWriter& endArray();
  JsonWriter& key(const char* k);          // à suivre d'une valeur / d'un objet / d'un tableau
  JsonWriter& value(float v, int decimals = 2);
  JsonWriter& value(int32_t v);
  JsonWriter& value(uint32_t v);
  JsonWriter& value(bool v);
  JsonWriter& value(const char* s);        // chaîne (échappée)
  JsonWriter& null();

  // Raccourcis clé:valeur
  JsonWriter& kv(const char* k, float v, int decimals = 2) { return key(k).value(v, decimals); }
  JsonWriter& kv(const char* k, int32_t v) { return key(k).value(v); }
  JsonWriter& kv(const char* k, uint32_t v) { return key(k).value(v); }
  JsonWriter& kv(const char* k, bool v) { return key(k).value(v); }
  JsonWriter& kv(const char* k, const char* s) { return key(k).value(s); }
  JsonWriter& kvArray(const char* k, const float* v, int n, int decimals = 2);

  bool ok() const { return !overflow_; }   // false si le tampon a débordé
  size_t size() const { return len_; }
  const char* c_str() const { return buf_; }

 private:
  void sep();
  void put(char c);
  void puts_(const char* s);
  char* buf_;
  size_t cap_, len_ = 0;
  bool overflow_ = false;
  bool need_comma_ = false;
  bool after_key_ = false;
};

}  // namespace atc
