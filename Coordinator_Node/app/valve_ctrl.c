#include "valve_ctrl.h"
#include "app_config.h"
#include "app_state.h"
#include "app_utils.h"
#include "app_log.h"
#include "lcd_ui.h"

#include "stack/include/binding-table.h"

#include <string.h>
#include <stdio.h>
#include "app_log.h"

static uint16_t g_flowCloseTh = 60u;
static uint16_t g_flowOpenTh  = 5u;

// confirmed state by tx_done success
static bool g_valveOpen = false;

// Stable identity: EUI64
static bool       g_valveKnown = false;
static EmberEUI64  g_valveEuiLe = {0};
static EmberNodeId g_valveNodeId = EMBER_NULL_NODE_ID;
static uint8_t     g_valveDstEp = VALVE_EP_DEFAULT;

// Optional binding
static uint8_t g_valveBindIndex = 0;
static valve_path_t g_valvePath = VALVE_PATH_AUTO;

// TX tracking
typedef struct {
  bool active;
  uint32_t cmdId;
  bool wantOpen;
  bool usedDirect;
  uint16_t dstOrIndex;
} TxTrack_t;

static TxTrack_t g_tx = {0};

static EmberStatus queueValveOnOff(bool wantOpen, bool useDirect)
{
  uint8_t cmdId = wantOpen ? ZCL_ON_COMMAND_ID : ZCL_OFF_COMMAND_ID;

  emberAfFillExternalBuffer((uint8_t)(ZCL_CLUSTER_SPECIFIC_COMMAND | ZCL_FRAME_CONTROL_CLIENT_TO_SERVER),
                            ZCL_ON_OFF_CLUSTER_ID,
                            cmdId,
                            "");

  emberAfSetCommandEndpoints(COORD_EP_CONTROL, g_valveDstEp);

  EmberApsFrame *aps = emberAfGetCommandApsFrame();
  if (aps) {
#ifdef EMBER_APS_OPTION_ACK_REQUEST
    aps->options |= EMBER_APS_OPTION_ACK_REQUEST;
#endif
#ifdef EMBER_APS_OPTION_RETRY
    aps->options |= EMBER_APS_OPTION_RETRY;
#endif
  }

  if (useDirect) {
    return emberAfSendCommandUnicast(EMBER_OUTGOING_DIRECT, g_valveNodeId);
  } else {
    return emberAfSendCommandUnicast(EMBER_OUTGOING_VIA_BINDING, g_valveBindIndex);
  }
}

bool valveCtrlQueueTx(uint32_t id, bool wantOpen)
{
  if (emberAfNetworkState() != EMBER_JOINED_NETWORK) {
    appLogAck(id, false, "not joined");
    return false;
  }
  if (g_tx.active) {
    appLogAck(id, false, "busy: tx_pending");
    return false;
  }

  bool canDirect = (g_valveNodeId != EMBER_NULL_NODE_ID);
  bool useDirect = false;

  if (g_valvePath == VALVE_PATH_DIRECT) useDirect = true;
  else if (g_valvePath == VALVE_PATH_BINDING) useDirect = false;
  else useDirect = canDirect; // AUTO

  if (useDirect && !canDirect) {
    appLogAck(id, false, "direct requires valve_node_id");
    return false;
  }

  EmberStatus st = queueValveOnOff(wantOpen, useDirect);
  if (st != EMBER_SUCCESS) {
    char buf[48];
    snprintf(buf, sizeof(buf), "send_fail_immediate:0x%02X", st);
    appLogAck(id, false, buf);
    return false;
  }

  g_tx.active = true;
  g_tx.cmdId = id;
  g_tx.wantOpen = wantOpen;
  g_tx.usedDirect = useDirect;
  g_tx.dstOrIndex = useDirect ? (uint16_t)g_valveNodeId : (uint16_t)g_valveBindIndex;

  appLogAck(id, true, useDirect ? "queued:direct" : "queued:binding");
  appLogData();
  return true;
}

void valveCtrlAutoControl(void)
{
  if (g_mode != MODE_AUTO) return;

  // hysteresis
  if (g_valveOpen) {
    if (g_flow > g_flowCloseTh) {
      (void)valveCtrlQueueTx(0, false);
    }
  } else {
    if (g_flow < g_flowOpenTh) {
      (void)valveCtrlQueueTx(0, true);
    }
  }
}

void valveCtrlSetThresholds(uint16_t closeTh, uint16_t openTh)
{
  g_flowCloseTh = closeTh;
  g_flowOpenTh  = openTh;
}

void valveCtrlSetPath(valve_path_t p) { g_valvePath = p; }

void valveCtrlSetTarget(EmberNodeId nodeId, uint8_t dstEp)
{
  g_valveNodeId = nodeId;
  g_valveDstEp  = dstEp;
}

bool valveCtrlPair(const char *eui64Str, EmberNodeId nodeId, uint8_t bindIndex, uint8_t dstEp)
{
  EmberEUI64 euiLe;
  if (!parseHexEui64(eui64Str, euiLe)) return false;

  g_valveKnown = true;
  memcpy(g_valveEuiLe, euiLe, EUI64_SIZE);
  g_valveNodeId = nodeId;
  g_valveBindIndex = bindIndex;
  g_valveDstEp = dstEp;

  (void)emberSetBindingRemoteNodeId(g_valveBindIndex, g_valveNodeId);
  return true;
}

// FINAL TX result callback (exact signature you used)
bool emberAfMessageSentCallback(EmberOutgoingMessageType type,
                               uint16_t indexOrDestination,
                               EmberApsFrame *apsFrame,
                               uint16_t messageLength,
                               uint8_t *messageContents,
                               EmberStatus status)
{
  (void)type;
  (void)indexOrDestination;
  (void)messageLength;
  (void)messageContents;

  if (!apsFrame) return false;

  if (apsFrame->clusterId == ZCL_ON_OFF_CLUSTER_ID && apsFrame->sourceEndpoint == COORD_EP_CONTROL) {
    if (g_tx.active) {
      emberAfCorePrintln(
        "@LOG {\"event\":\"tx_done\",\"id\":%lu,\"st\":\"0x%02X\",\"path\":\"%s\",\"dst_or_index\":\"0x%04X\"}",
        (unsigned long)g_tx.cmdId,
        (unsigned)status,
        g_tx.usedDirect ? "direct" : "binding",
        (unsigned)g_tx.dstOrIndex
      );

      if (status == EMBER_SUCCESS) {
        g_valveOpen = g_tx.wantOpen;
        lcd_ui_set_valve(g_valveOpen);  // Update LCD when valve state confirmed
      }

      g_tx.active = false;
      appLogData();
    }
  }

  return false;
}

// Trust Center join callback (exact signature you used)
void emberAfTrustCenterJoinCallback(EmberNodeId newNodeId,
                                   EmberEUI64 newNodeEui64,
                                   EmberNodeId parentOfNewNode,
                                   EmberDeviceUpdate status,
                                   EmberJoinDecision decision)
{
  (void)parentOfNewNode;
  (void)decision;

  if (!g_valveKnown) return;  // newNodeEui64 is not NULL (it's an array param)

  if (memcmp(newNodeEui64, g_valveEuiLe, EUI64_SIZE) == 0) {
    g_valveNodeId = newNodeId;
    (void)emberSetBindingRemoteNodeId(g_valveBindIndex, newNodeId);

    emberAfCorePrintln("@LOG {\"event\":\"valve_nodeid_update\",\"node_id\":\"0x%04X\",\"status\":%u}",
                       (uint16_t)newNodeId, (unsigned)status);
    printInfoToPC();
  }
}


// ===== getters =====
bool valveCtrlIsOpen(void) { return g_valveOpen; }
bool valveCtrlTxActive(void) { return g_tx.active; }
valve_path_t valveCtrlGetPath(void) { return g_valvePath; }

const char *valveCtrlPathStr(void)
{
  switch (g_valvePath) {
    case VALVE_PATH_DIRECT:  return "direct";
    case VALVE_PATH_BINDING: return "binding";
    default: return "auto";
  }
}

bool valveCtrlIsKnown(void) { return g_valveKnown; }
EmberNodeId valveCtrlGetNodeId(void) { return g_valveNodeId; }
uint8_t valveCtrlGetBindIndex(void) { return g_valveBindIndex; }
uint8_t valveCtrlGetDstEp(void) { return g_valveDstEp; }
const EmberEUI64 *valveCtrlGetEuiLe(void) { return &g_valveEuiLe; }
