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
#include <stdarg.h>

// ===== HEARTBEAT / UPTIME TRACKING =====
static uint32_t s_bootTick = 0;
static uint32_t s_lastHeartbeatTick = 0;
static bool s_initialized = false;

static void ensureInit(void)
{
  if (!s_initialized) {
    s_bootTick = msTick();
    s_lastHeartbeatTick = s_bootTick;
    s_initialized = true;
  }
}

uint32_t appLogGetUptimeSec(void)
{
  ensureInit();
  return (msTick() - s_bootTick) / 1000u;
}

// ===== HEARTBEAT TICK =====
void appLogHeartbeatTick(void)
{
  ensureInit();
  uint32_t now = msTick();
  if ((now - s_lastHeartbeatTick) >= HEARTBEAT_INTERVAL_MS) {
    s_lastHeartbeatTick = now;
    appLogInfo();  // Emit @INFO as heartbeat
  }
}

void appLogEmitHeartbeat(void)
{
  ensureInit();
  s_lastHeartbeatTick = msTick();  // Reset timer
  appLogInfo();
}

// ===== HELPER: EUI64 -> hex string =====
static void eui64ToHexStr(const uint8_t eui[8], char out[17])
{
  for (int i = 0; i < 8; i++) {
    sprintf(&out[i * 2], "%02X", eui[i]);
  }
  out[16] = '\0';
}

// ===== LEGACY: printInfoToPC (deprecated, use appLogInfo) =====
void printInfoToPC(void)
{
  appLogInfo();  // Redirect to standard function
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

// Extended ACK with Zigbee status code
void appLogAckZb(uint32_t id, bool ok, const char *msg, uint8_t zstatus, const char *stage)
{
  if (!msg) msg = "";
  if (!stage) stage = "";
  emberAfCorePrintln(
    "@ACK {\"id\":%lu,\"ok\":%s,\"msg\":\"%s\",\"zstatus\":\"0x%02X\",\"stage\":\"%s\","
    "\"mode\":\"%s\",\"valve\":\"%s\"}",
    (unsigned long)id,
    ok ? "true" : "false",
    msg,
    (unsigned)zstatus,
    stage,
    modeStr(),
    valveCtrlIsOpen() ? "open" : "closed"
  );
}

// Variadic LOG with tag, event, and extra key-value pairs
void appLogLog(const char *tag, const char *event, const char *fmt, ...)
{
  char extra[128] = "";
  if (fmt && fmt[0] != '\0') {
    va_list args;
    va_start(args, fmt);
    vsnprintf(extra, sizeof(extra), fmt, args);
    va_end(args);
  }

  // Build JSON - if extra is non-empty, append it
  if (extra[0] != '\0') {
    emberAfCorePrintln(
      "@LOG {\"tag\":\"%s\",\"event\":\"%s\",%s,\"uptime\":%lu}",
      tag ? tag : "",
      event ? event : "",
      extra,
      (unsigned long)appLogGetUptimeSec()
    );
  } else {
    emberAfCorePrintln(
      "@LOG {\"tag\":\"%s\",\"event\":\"%s\",\"uptime\":%lu}",
      tag ? tag : "",
      event ? event : "",
      (unsigned long)appLogGetUptimeSec()
    );
  }
}

void appLogInfo(void)
{
  ensureInit();
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
    "\"valve_path\":\"%s\",\"valve_known\":%s,\"valve_eui64\":\"%s\","
    "\"valve_node_id\":\"0x%04X\",\"bind_index\":%u,\"uptime\":%lu}",
    nodeId, euiStr, panId, ch, (int)pwr, st,
    g_uartGatewayEnabled ? "true" : "false",
    modeStr(),
    valveCtrlPathStr(),
    valveCtrlIsKnown() ? "true" : "false",
    valveEuiStr,
    (uint16_t)valveCtrlGetNodeId(),
    (unsigned)valveCtrlGetBindIndex(),
    (unsigned long)appLogGetUptimeSec()
  );
}
