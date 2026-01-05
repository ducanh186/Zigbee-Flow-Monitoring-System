#include "app_log.h"
#include "app_config.h"
#include "app_state.h"
#include "app_utils.h"
#include "net_mgr.h"
#include "valve_ctrl.h"


#include "app/framework/include/af.h"
#include "stack/include/ember.h"

#include <string.h>
#include <stdio.h>
#include "app/framework/include/af.h"
#include "stack/include/ember.h"
#include <stdio.h>
#include <string.h>

#include "app_log.h"

// Convert EUI64 -> hex string (16 chars + null)
static void eui64ToHexStr(const uint8_t eui[8], char out[17])
{
  for (int i = 0; i < 8; i++) {
    sprintf(&out[i * 2], "%02X", eui[i]);
  }
  out[16] = '\0';
}

void printInfoToPC(void)
{
  EmberNodeId nodeId = emberGetNodeId();

  EmberEUI64 eui;
  // AF helper
  emberAfGetEui64(eui);
  // Hoắc dùng macro:
  // memcpy(eui, emberGetEui64(), 8);

  char euiStr[17];
  eui64ToHexStr(eui, euiStr);

  EmberNetworkParameters params;
  EmberStatus st = emberGetNetworkParameters(&params); // CHỈ 1 THAM SỐ

  if (st == EMBER_SUCCESS) {
    emberAfCorePrintln(
      "@INFO {\"node_id\":\"0x%04X\",\"eui64\":\"%s\",\"pan_id\":\"0x%04X\",\"channel\":%u,\"tx_power\":%d}",
      (unsigned)nodeId,
      euiStr,
      (unsigned)params.panId,
      (unsigned)params.radioChannel,
      (int)params.radioTxPower
    );
  } else {
    emberAfCorePrintln(
      "@INFO {\"node_id\":\"0x%04X\",\"eui64\":\"%s\",\"net\":\"down\"}",
      (unsigned)nodeId,
      euiStr
    );
  }
}

static const char *modeStr(void) { return (g_mode == MODE_AUTO) ? "auto" : "manual"; }

void appLogData(void)
{
  emberAfCorePrintln(
    "@DATA {\"flow\":%u,\"valve\":\"%s\",\"battery\":%u,\"mode\":\"%s\""
    ",\"tx_pending\":%s,\"valve_path\":\"%s\""
    ",\"valve_node_id\":\"0x%04X\",\"valve_known\":%s}",
    g_flow,
    valveCtrlIsOpen() ? "open" : "closed",
    g_batteryPercent,
    modeStr(),
    valveCtrlTxActive() ? "true" : "false",
    valveCtrlPathStr(),
    (uint16_t)valveCtrlGetNodeId(),
    valveCtrlIsKnown() ? "true" : "false"
  );
}

void appLogAck(uint32_t id, bool ok, const char *msg)
{
  if (!msg) msg = "";
  emberAfCorePrintln(
    "@ACK {\"id\":%lu,\"ok\":%s,\"msg\":\"%s\",\"mode\":\"%s\",\"valve\":\"%s\"}",
    (unsigned long)id,
    ok ? "true" : "false",
    msg,
    modeStr(),
    valveCtrlIsOpen() ? "open" : "closed"
  );
}

void appLogLog(const char *event, const char *src, const char *msg)
{
  emberAfCorePrintln("@LOG {\"event\":\"%s\",\"src\":\"%s\",\"msg\":\"%s\"}",
                     event ? event : "", src ? src : "", msg ? msg : "");
}

void appLogInfo(void)
{
  EmberNetworkStatus st = emberAfNetworkState();
  EmberNodeId nodeId = emberGetNodeId();

  EmberEUI64 eui;
  memcpy(eui, emberGetEui64(), EUI64_SIZE);

  char euiStr[17];
  eui64ToStringBigEndian(euiStr, sizeof(euiStr), eui);

  uint16_t panId = g_netCfg.panId;
  uint8_t ch = g_netCfg.ch;
  int8_t pwr = g_netCfg.txPowerDbm;

  EmberNodeType nodeType;
  EmberNetworkParameters params;
  if (emberAfGetNetworkParameters(&nodeType, &params) == EMBER_SUCCESS) {
    panId = params.panId;
    ch = params.radioChannel;
  }

  char valveEuiStr[17] = "0000000000000000";
  if (valveCtrlIsKnown()) {
    const EmberEUI64 *ve = valveCtrlGetEuiLe();
    if (ve) eui64ToStringBigEndian(valveEuiStr, sizeof(valveEuiStr), *ve);
  }

  emberAfCorePrintln(
    "@INFO {\"node_id\":\"0x%04X\",\"eui64\":\"%s\",\"pan_id\":\"0x%04X\",\"ch\":%u,"
    "\"tx_power\":%d,\"net_state\":%d,\"uart_gateway\":%s,\"mode\":\"%s\","
    "\"valve_path\":\"%s\",\"valve_known\":%s,\"valve_eui64\":\"%s\",\"valve_node_id\":\"0x%04X\",\"bind_index\":%u}",
    nodeId, euiStr, panId, ch, (int)pwr, st,
    g_uartGatewayEnabled ? "true" : "false",
    modeStr(),
    valveCtrlPathStr(),
    valveCtrlIsKnown() ? "true" : "false",
    valveEuiStr,
    (uint16_t)valveCtrlGetNodeId(),
    (unsigned)valveCtrlGetBindIndex()
  );
}
