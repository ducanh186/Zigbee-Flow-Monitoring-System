#ifndef VALVE_CTRL_H
#define VALVE_CTRL_H

#include <stdint.h>
#include <stdbool.h>

#include "app/framework/include/af.h"
#include "stack/include/ember.h"

typedef enum { VALVE_PATH_AUTO=0, VALVE_PATH_DIRECT=1, VALVE_PATH_BINDING=2 } valve_path_t;

bool valveCtrlQueueTx(uint32_t id, bool wantOpen);
void valveCtrlAutoControl(void);

void valveCtrlSetPath(valve_path_t p);
void valveCtrlSetTarget(EmberNodeId nodeId, uint8_t dstEp);
bool valveCtrlPair(const char *eui64Str, EmberNodeId nodeId, uint8_t bindIndex, uint8_t dstEp);
void valveCtrlSetThresholds(uint16_t closeTh, uint16_t openTh);

// getters for logs/info
bool valveCtrlIsOpen(void);
bool valveCtrlTxActive(void);
valve_path_t valveCtrlGetPath(void);
const char *valveCtrlPathStr(void);

bool valveCtrlIsKnown(void);
EmberNodeId valveCtrlGetNodeId(void);
uint8_t valveCtrlGetBindIndex(void);
uint8_t valveCtrlGetDstEp(void);
const EmberEUI64 *valveCtrlGetEuiLe(void);

#endif
