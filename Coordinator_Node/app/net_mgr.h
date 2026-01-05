#ifndef NET_MGR_H
#define NET_MGR_H

#include <stdint.h>
#include <stdbool.h>

typedef struct {
  uint16_t panId;
  uint8_t  ch;
  int8_t   txPowerDbm;
} NetCfg_t;

extern NetCfg_t g_netCfg;

bool netMgrRequestForm(NetCfg_t cfg, const char *src, bool force);
void netMgrTick(void);

#endif
