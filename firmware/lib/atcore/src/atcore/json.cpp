#include "atcore/json.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

namespace atc {

JsonWriter::JsonWriter(char* buf, size_t cap) : buf_(buf), cap_(cap) {
  if (cap_) buf_[0] = '\0';
}

void JsonWriter::put(char c) {
  if (len_ + 1 < cap_) { buf_[len_++] = c; buf_[len_] = '\0'; }
  else overflow_ = true;
}

void JsonWriter::puts_(const char* s) { while (*s) put(*s++); }

void JsonWriter::sep() {
  if (after_key_) { after_key_ = false; return; }
  if (need_comma_) put(',');
}

JsonWriter& JsonWriter::beginObject() { sep(); put('{'); need_comma_ = false; return *this; }
JsonWriter& JsonWriter::endObject() { put('}'); need_comma_ = true; return *this; }
JsonWriter& JsonWriter::beginArray() { sep(); put('['); need_comma_ = false; return *this; }
JsonWriter& JsonWriter::endArray() { put(']'); need_comma_ = true; return *this; }

JsonWriter& JsonWriter::key(const char* k) {
  sep();
  put('"'); puts_(k); put('"'); put(':');
  after_key_ = true;
  return *this;
}

JsonWriter& JsonWriter::value(float v, int decimals) {
  sep();
  if (!isfinite(v)) { puts_("null"); }
  else {
    char tmp[32];
    if (decimals < 0) decimals = 0;
    if (decimals > 6) decimals = 6;
    snprintf(tmp, sizeof tmp, "%.*f", decimals, static_cast<double>(v));
    // « -0.00 » → « 0.00 » pour un flux propre
    if (tmp[0] == '-') {
      bool zero = true;
      for (const char* p = tmp + 1; *p; ++p) if (*p != '0' && *p != '.') { zero = false; break; }
      if (zero) puts_(tmp + 1); else puts_(tmp);
    } else puts_(tmp);
  }
  need_comma_ = true;
  return *this;
}

JsonWriter& JsonWriter::value(int32_t v) {
  sep();
  char tmp[16];
  snprintf(tmp, sizeof tmp, "%ld", static_cast<long>(v));
  puts_(tmp);
  need_comma_ = true;
  return *this;
}

JsonWriter& JsonWriter::value(uint32_t v) {
  sep();
  char tmp[16];
  snprintf(tmp, sizeof tmp, "%lu", static_cast<unsigned long>(v));
  puts_(tmp);
  need_comma_ = true;
  return *this;
}

JsonWriter& JsonWriter::value(bool v) { sep(); puts_(v ? "true" : "false"); need_comma_ = true; return *this; }
JsonWriter& JsonWriter::null() { sep(); puts_("null"); need_comma_ = true; return *this; }

JsonWriter& JsonWriter::value(const char* s) {
  sep();
  put('"');
  for (; *s; ++s) {
    const char c = *s;
    if (c == '"' || c == '\\') { put('\\'); put(c); }
    else if (c == '\n') puts_("\\n");
    else if (c == '\r') puts_("\\r");
    else if (c == '\t') puts_("\\t");
    else if (static_cast<unsigned char>(c) < 0x20) { /* ignoré */ }
    else put(c);
  }
  put('"');
  need_comma_ = true;
  return *this;
}

JsonWriter& JsonWriter::kvArray(const char* k, const float* v, int n, int decimals) {
  key(k).beginArray();
  for (int i = 0; i < n; ++i) value(v[i], decimals);
  return endArray();
}

}  // namespace atc
