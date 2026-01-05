#include "app_utils.h"
#include "app/framework/include/af.h"

#include <string.h>
#include <ctype.h>
#include <stdlib.h>

uint32_t msTick(void) { return halCommonGetInt32uMillisecondTick(); }

uint16_t u16le(const uint8_t *p) { return (uint16_t)p[0] | ((uint16_t)p[1] << 8); }

const char *skipSpaces(const char *s)
{
  while (s && *s && isspace((unsigned char)*s)) s++;
  return s;
}

static int hexNibble(char c)
{
  if (c >= '0' && c <= '9') return (c - '0');
  if (c >= 'a' && c <= 'f') return (c - 'a' + 10);
  if (c >= 'A' && c <= 'F') return (c - 'A' + 10);
  return -1;
}

// Parse EUI64 string (human big-endian) -> EmberEUI64 (internal little-endian)
bool parseHexEui64(const char *s, EmberEUI64 outLe)
{
  if (!s || !outLe) return false;

  char hex[16];
  uint8_t n = 0;
  bool extra = false;

  while (*s) {
    int h = hexNibble(*s);
    if (h >= 0) {
      if (n < 16) hex[n++] = *s;
      else extra = true;
    }
    s++;
  }
  if (n != 16 || extra) return false;

  uint8_t tmpBE[8];
  for (uint8_t i = 0; i < 8; i++) {
    int hi = hexNibble(hex[2*i]);
    int lo = hexNibble(hex[2*i + 1]);
    if (hi < 0 || lo < 0) return false;
    tmpBE[i] = (uint8_t)((hi << 4) | lo);
  }
  for (uint8_t i = 0; i < 8; i++) outLe[i] = tmpBE[7 - i];
  return true;
}

void eui64ToStringBigEndian(char *outStr, uint32_t outSize, const EmberEUI64 euiLe)
{
  if (!outStr || outSize < 17) return;
  static const char *hex = "0123456789ABCDEF";
  for (uint8_t i = 0; i < 8; i++) {
    uint8_t b = euiLe[7 - i];
    outStr[2*i]     = hex[(b >> 4) & 0x0F];
    outStr[2*i + 1] = hex[b & 0x0F];
  }
  outStr[16] = 0;
}

bool parseUintField(const char *json, const char *key, uint32_t *out)
{
  if (!json || !key || !out) return false;

  const char *p = strstr(json, key);
  if (!p) return false;

  p = strchr(p, ':');
  if (!p) return false;
  p++;
  p = skipSpaces(p);

  uint32_t v = 0;
  bool any = false;
  while (*p && isdigit((unsigned char)*p)) {
    any = true;
    v = (v * 10u) + (uint32_t)(*p - '0');
    p++;
  }
  if (!any) return false;

  *out = v;
  return true;
}

bool parseStringField(const char *json, const char *key, char *out, uint32_t outSize)
{
  if (!json || !key || !out || outSize == 0) return false;

  const char *p = strstr(json, key);
  if (!p) return false;

  p = strchr(p, ':');
  if (!p) return false;
  p++;
  p = skipSpaces(p);

  if (*p == '\"') {
    p++;
    uint32_t i = 0;
    while (*p && *p != '\"' && i + 1 < outSize) out[i++] = *p++;
    out[i] = 0;
    return (*p == '\"');
  } else {
    uint32_t i = 0;
    while (*p && *p != ',' && *p != '}' && !isspace((unsigned char)*p) && i + 1 < outSize) {
      out[i++] = *p++;
    }
    out[i] = 0;
    return (i > 0);
  }
}

// supports "0xbeef" OR "48879"
bool parseU32FieldAutoBase(const char *json, const char *key, uint32_t *out)
{
  char tmp[24] = {0};
  if (!parseStringField(json, key, tmp, sizeof(tmp))) return false;

  char *endp = NULL;
  unsigned long v = strtoul(tmp, &endp, 0);
  if (endp == tmp) return false;

  *out = (uint32_t)v;
  return true;
}

bool parseU32FieldAny(const char *json, const char *key, uint32_t *out)
{
  if (parseU32FieldAutoBase(json, key, out)) return true;
  return parseUintField(json, key, out);
}
