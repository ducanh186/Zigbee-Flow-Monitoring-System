#ifndef APP_UTILS_H
#define APP_UTILS_H

#include <stdint.h>
#include <stdbool.h>
#include "stack/include/ember-types.h"

uint32_t msTick(void);
uint16_t u16le(const uint8_t *p);

const char *skipSpaces(const char *s);

bool parseHexEui64(const char *s, EmberEUI64 outLe);
void eui64ToStringBigEndian(char *outStr, uint32_t outSize, const EmberEUI64 euiLe);

bool parseUintField(const char *json, const char *key, uint32_t *out);
bool parseStringField(const char *json, const char *key, char *out, uint32_t outSize);
bool parseU32FieldAutoBase(const char *json, const char *key, uint32_t *out);
bool parseU32FieldAny(const char *json, const char *key, uint32_t *out);

#endif
