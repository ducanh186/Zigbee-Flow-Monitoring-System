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
  // A1: For errors when id=0 (auto mode), use @LOG instead of @ACK
  // A2: For valid id, ACK will be sent in tx_done callback (not here)
  
  if (emberAfNetworkState() != EMBER_JOINED_NETWORK) {
    if (id == 0) {
      appLogLog("ZB", "valve_reject", "\"reason\":\"not_joined\"");
    } else {
      appLogAck(id, false, "not joined");
    }
    return false;
  }
  if (g_tx.active) {
    if (id == 0) {
      appLogLog("ZB", "valve_reject", "\"reason\":\"tx_pending\"");
    } else {
      appLogAck(id, false, "busy: tx_pending");
    }
    return false;
  }

  bool canDirect = (g_valveNodeId != EMBER_NULL_NODE_ID);
  bool useDirect = false;

  if (g_valvePath == VALVE_PATH_DIRECT) useDirect = true;
  else if (g_valvePath == VALVE_PATH_BINDING) useDirect = false;
  else useDirect = canDirect; // AUTO

  if (useDirect && !canDirect) {
    if (id == 0) {
      appLogLog("ZB", "valve_reject", "\"reason\":\"direct_requires_node_id\"");
    } else {
      appLogAck(id, false, "direct requires valve_node_id");
    }
    return false;
  }

  EmberStatus st = queueValveOnOff(wantOpen, useDirect);
  if (st != EMBER_SUCCESS) {
    if (id == 0) {
      appLogLog("ZB", "valve_reject", "\"reason\":\"send_fail\",\"zstatus\":\"0x%02X\"", (unsigned)st);
    } else {
      char buf[48];
      snprintf(buf, sizeof(buf), "send_fail_immediate:0x%02X", st);
      appLogAck(id, false, buf);
    }
    return false;
  }

  g_tx.active = true;
  g_tx.cmdId = id;
  g_tx.wantOpen = wantOpen;
  g_tx.usedDirect = useDirect;
  g_tx.dstOrIndex = useDirect ? (uint16_t)g_valveNodeId : (uint16_t)g_valveBindIndex;

  // A1: Progress log (not ACK) - ACK will come in tx_done callback
  appLogLog("ZB", "valve_queued", "\"id\":%lu,\"path\":\"%s\",\"want\":\"%s\"",
    (unsigned long)id,
    useDirect ? "direct" : "binding",
    wantOpen ? "open" : "close"
  );
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
      bool txOk = (status == EMBER_SUCCESS);
      
      // A2: Send final @ACK only for valid command IDs (not auto mode id=0)
      if (g_tx.cmdId != 0) {
        if (txOk) {
          appLogAckZb(g_tx.cmdId, true, "done", status, "done");
        } else {
          appLogAckZb(g_tx.cmdId, false, "tx_failed", status, "done");
        }
      }
      
      // A1: Always log tx result for debugging
      appLogLog("ZB", txOk ? "tx_done" : "tx_fail",
        "\"id\":%lu,\"zstatus\":\"0x%02X\",\"path\":\"%s\",\"dst\":\"0x%04X\",\"want\":\"%s\"",
        (unsigned long)g_tx.cmdId,
        (unsigned)status,
        g_tx.usedDirect ? "direct" : "binding",
        (unsigned)g_tx.dstOrIndex,
        g_tx.wantOpen ? "open" : "close"
      );

      if (txOk) {
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

#ifdef DEBUG_NET_PRINTS
  // Log all TC join events for debugging
  char euiStr[17];
  for (int i = 0; i < 8; i++) {
    sprintf(&euiStr[i * 2], "%02X", newNodeEui64[i]);
  }
  euiStr[16] = '\0';

  appLogLog("NET", "tc_join",
    "\"node_id\":\"0x%04X\",\"eui64\":\"%s\",\"status\":%u,\"decision\":%u",
    (unsigned)newNodeId, euiStr, (unsigned)status, (unsigned)decision
  );
#endif

  if (!g_valveKnown) return;

  if (memcmp(newNodeEui64, g_valveEuiLe, EUI64_SIZE) == 0) {
    g_valveNodeId = newNodeId;
    (void)emberSetBindingRemoteNodeId(g_valveBindIndex, newNodeId);

    appLogLog("ZB", "valve_nodeid_update",
      "\"node_id\":\"0x%04X\",\"status\":%u",
      (unsigned)newNodeId, (unsigned)status
    );
    appLogInfo();
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
