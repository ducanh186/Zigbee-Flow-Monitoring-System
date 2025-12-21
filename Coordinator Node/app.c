/***************************************************************************//**
 * @file app.c
 * @brief Coordinator: Zigbee Flow Monitoring + UART JSON Gateway
 *
 * UART output (PC parse):
 *   @DATA {"flow":55,"valve":"closed","battery":83}
 *   @INFO {"node_id":"0x0000",...}
 *   @LOG  {"event":"...",...}
 *
 * UART command (PC -> coordinator):
 *   @CMD {"id":1,"op":"valve_set","value":"open"}
 *   @CMD {"id":2,"op":"net_cfg_set","pan_id":"0xbeef","ch":11,"tx_power":8}
 *   @CMD {"id":3,"op":"net_form","pan_id":"0xbeef","ch":11,"tx_power":8,"force":1}
 *
 * UART ack (coordinator -> PC):
 *   @ACK {"id":1,"ok":true,"msg":"valve set","valve":"open"}
 ******************************************************************************/

#include "app/framework/include/af.h"
#include "sl_zigbee_debug_print.h"
#include "zap-id.h"

#include <string.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <ctype.h>
#include <stdlib.h>   // strtoul

#include "sl_iostream.h"   // sl_iostream_read(), SL_IOSTREAM_STDIN
#include "sl_status.h"

#include "stack/include/ember.h"
#include "stack/include/binding-table.h" // EmberBindingTableEntry, emberSetBinding

#include "sl_simple_button.h"
#include "sl_simple_button_instances.h"

#ifdef SL_CATALOG_ZIGBEE_NETWORK_CREATOR_PRESENT
#include "network-creator.h"
#endif
#ifdef SL_CATALOG_ZIGBEE_NETWORK_CREATOR_SECURITY_PRESENT
#include "network-creator-security.h"
#endif

#ifndef EUI64_SIZE
#define EUI64_SIZE 8u
#endif

// =================== Fallback defines ===================
#ifndef ZCL_POWER_CONFIGURATION_CLUSTER_ID
#define ZCL_POWER_CONFIGURATION_CLUSTER_ID 0x0001
#endif

#ifndef ZCL_FLOW_MEASUREMENT_CLUSTER_ID
#define ZCL_FLOW_MEASUREMENT_CLUSTER_ID   0x0404
#endif

#ifndef ZCL_REPORT_ATTRIBUTES_COMMAND_ID
#define ZCL_REPORT_ATTRIBUTES_COMMAND_ID  0x0A
#endif

#ifndef ZCL_INT16U_ATTRIBUTE_TYPE
#define ZCL_INT16U_ATTRIBUTE_TYPE 0x21
#endif

#ifndef ZCL_INT8U_ATTRIBUTE_TYPE
#define ZCL_INT8U_ATTRIBUTE_TYPE  0x20
#endif

// =================== CONFIG ===================
#define COORD_EP_TELEM       1   // Endpoint nhận flow/battery
#define COORD_EP_CONTROL     2   // Endpoint gửi On/Off
#define VALVE_EP             1

#define OPEN_JOIN_MS         180000u   // 180s mở cho join rồi đóng mạng

// Runtime defaults (có thể đổi bằng @CMD net_cfg_set)
#define DEFAULT_PAN_ID       0xBEEFu
#define DEFAULT_CHANNEL      11u
#define DEFAULT_TX_POWER_DBM 8

// Auto-control thresholds
static uint16_t g_flowCloseTh = 60u;   // flow > TH => close
// flow == 0 => open

// UART line buffer
#define UART_LINE_MAX        192u

// PB0 long-press threshold to toggle UART gateway
#define PB0_LONG_PRESS_MS    1500u

// =================== STATE ===================
static uint16_t g_flow = 0;
static uint8_t  g_batteryPercent = 0; // 0..100
static bool     g_valveOpen = true;   // true=open (ON), false=closed (OFF)

static bool     g_networkOpen = false;
static uint32_t g_openTick = 0;

// UART gateway enables reading @CMD lines (but will also "steal" CLI chars)
static bool     g_uartGatewayEnabled = true;

// Runtime network config (tương đương CLI parameters)
typedef struct {
  uint16_t panId;
  uint8_t  ch;
  int8_t   txPowerDbm;
} NetCfg_t;

static NetCfg_t g_netCfg = {
  .panId = (uint16_t)DEFAULT_PAN_ID,
  .ch = (uint8_t)DEFAULT_CHANNEL,
  .txPowerDbm = (int8_t)DEFAULT_TX_POWER_DBM,
};

// For force re-form (leave -> form)
static bool     g_pendingForm = false;
static NetCfg_t g_pendingCfg;
static char     g_pendingSrc[8] = "uart";

// PB0 press tracking (short press vs long press)
static uint32_t g_pb0PressTick = 0;

// =================== Prototypes ===================
static uint32_t msTick(void);
static uint16_t u16le(const uint8_t *p);

static void printDataToPC(void);
static void printLogToPC(const char *event, const char *src, uint16_t pan, uint8_t ch, int8_t pwr);
static void printLogTextToPC(const char *event, const char *src, const char *msg);
static void printAckToPC(uint32_t id, bool ok, const char *msg);
static void printAckBindToPC(uint32_t id, bool ok, uint32_t index, const char *msg);
static void printInfoToPC(void);

static const char *skipSpaces(const char *s);
static int hexNibble(char c);
static bool parseHexEui64(const char *s, EmberEUI64 outLe);
static void eui64ToStringBigEndian(char *outStr, uint32_t outSize, const EmberEUI64 euiLe);
static bool parseUintField(const char *json, const char *key, uint32_t *out);
static bool parseStringField(const char *json, const char *key, char *out, uint32_t outSize);
static bool parseU32FieldAutoBase(const char *json, const char *key, uint32_t *out);

static EmberStatus sendValveCommandRaw(bool open);
static bool setValveState(bool open, const char *reason);
static void autoControlLogic(void);

static bool startNetworkForm(uint16_t panId, int8_t txPwrDbm, uint8_t ch, const char *src);
static bool requestNetworkForm(NetCfg_t cfg, const char *src, bool force);

static void handleCmdLine(const char *line);
static void uartPoll(void);

// =================== Helpers ===================
static uint32_t msTick(void)
{
  return halCommonGetInt32uMillisecondTick();
}

static uint16_t u16le(const uint8_t *p)
{
  return (uint16_t)p[0] | ((uint16_t)p[1] << 8);
}

// ---------- UART JSON output ----------
static void printDataToPC(void)
{
  emberAfCorePrintln("@DATA {\"flow\":%u,\"valve\":\"%s\",\"battery\":%u}",
                     g_flow, g_valveOpen ? "open" : "closed", g_batteryPercent);
}

static void printLogToPC(const char *event, const char *src,
                         uint16_t pan, uint8_t ch, int8_t pwr)
{
  emberAfCorePrintln("@LOG {\"event\":\"%s\",\"src\":\"%s\",\"pan_id\":\"0x%04X\",\"ch\":%u,\"pwr\":%d}",
                     event ? event : "", src ? src : "",
                     pan, ch, (int)pwr);
}

static void printLogTextToPC(const char *event, const char *src, const char *msg)
{
  emberAfCorePrintln("@LOG {\"event\":\"%s\",\"src\":\"%s\",\"msg\":\"%s\"}",
                     event ? event : "", src ? src : "", msg ? msg : "");
}

static void printAckToPC(uint32_t id, bool ok, const char *msg)
{
  if (msg == NULL) msg = "";
  emberAfCorePrintln(
      "@ACK {\"id\":%lu,\"ok\":%s,\"msg\":\"%s\",\"valve\":\"%s\"}",
      (unsigned long)id, ok ? "true" : "false", msg,
      g_valveOpen ? "open" : "closed");
}

static void printAckBindToPC(uint32_t id, bool ok, uint32_t index, const char *msg)
{
  if (msg == NULL) msg = "";
  emberAfCorePrintln(
      "@ACK {\"id\":%lu,\"ok\":%s,\"msg\":\"%s\",\"index\":%lu}",
      (unsigned long)id, ok ? "true" : "false", msg,
      (unsigned long)index);
}

// =================== Minimal JSON-ish parsing for @CMD ===================
static const char *skipSpaces(const char *s)
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

// Parse EUI64 string (big-endian human) -> EmberEUI64 (little-endian internal)
static bool parseHexEui64(const char *s, EmberEUI64 outLe)
{
  if (!s || !outLe) return false;

  char hex[16];
  uint8_t n = 0;
  bool extraHex = false;

  while (*s) {
    int h = hexNibble(*s);
    if (h >= 0) {
      if (n < 16) {
        hex[n++] = *s;
      } else {
        extraHex = true;
      }
    }
    s++;
  }

  if (n != 16 || extraHex) return false;

  uint8_t tmpBE[8];
  for (uint8_t i = 0; i < 8; i++) {
    int hi = hexNibble(hex[2*i]);
    int lo = hexNibble(hex[2*i + 1]);
    if (hi < 0 || lo < 0) return false;
    tmpBE[i] = (uint8_t)((hi << 4) | lo);
  }

  for (uint8_t i = 0; i < 8; i++) {
    outLe[i] = tmpBE[7 - i]; // BE -> LE
  }
  return true;
}

static void eui64ToStringBigEndian(char *outStr, uint32_t outSize, const EmberEUI64 euiLe)
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

static bool parseUintField(const char *json, const char *key, uint32_t *out)
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

static bool parseStringField(const char *json, const char *key, char *out, uint32_t outSize)
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

// supports "0xbeef" or 48879, etc.
static bool parseU32FieldAutoBase(const char *json, const char *key, uint32_t *out)
{
  char tmp[24] = {0};

  if (!parseStringField(json, key, tmp, sizeof(tmp))) {
    return false;
  }

  char *endp = NULL;
  unsigned long v = strtoul(tmp, &endp, 0); // base 0 => supports 0x...
  if (endp == tmp) return false;

  *out = (uint32_t)v;
  return true;
}

// ---------- Zigbee On/Off send ----------
static EmberStatus sendValveCommandRaw(bool open)
{
  if (open) {
    emberAfFillCommandOnOffClusterOn();
  } else {
    emberAfFillCommandOnOffClusterOff();
  }

  emberAfSetCommandEndpoints(COORD_EP_CONTROL, VALVE_EP);
  return emberAfSendCommandUnicastToBindings();
}

static bool setValveState(bool open, const char *reason)
{
  EmberStatus st = sendValveCommandRaw(open);

  emberAfCorePrintln("Send valve %s via binding: 0x%02X (%s)",
                     open ? "OPEN(ON)" : "CLOSE(OFF)", st,
                     (reason != NULL) ? reason : "manual/auto");

  if (st == EMBER_SUCCESS) {
    g_valveOpen = open;
    return true;
  }
  return false;
}

static void autoControlLogic(void)
{
  if (g_flow > g_flowCloseTh) {
    if (g_valveOpen) {
      (void)setValveState(false, "auto(flow>th)");
    }
  } else if (g_flow == 0) {
    if (!g_valveOpen) {
      (void)setValveState(true, "auto(flow==0)");
    }
  }
}

static void printInfoToPC(void)
{
  EmberNetworkStatus st = emberAfNetworkState();
  EmberNodeId nodeId = emberGetNodeId();

  EmberEUI64 eui;
  memcpy(eui, emberGetEui64(), EUI64_SIZE);

  char euiStr[17];
  eui64ToStringBigEndian(euiStr, sizeof(euiStr), eui);

  // Defaults from runtime cfg
  uint16_t panId = g_netCfg.panId;
  uint8_t ch = g_netCfg.ch;
  int8_t pwr = g_netCfg.txPowerDbm;

  // If already in a network, read actual params from stack
  EmberNodeType nodeType;
  EmberNetworkParameters params;
  EmberStatus npSt = emberAfGetNetworkParameters(&nodeType, &params);
  if (npSt == EMBER_SUCCESS) {
    panId = params.panId;
    ch = params.radioChannel;
  }

  emberAfCorePrintln(
    "@INFO {\"node_id\":\"0x%04X\",\"eui64\":\"%s\",\"pan_id\":\"0x%04X\",\"ch\":%u,"
    "\"tx_power\":%d,\"net_state\":%d,\"uart_gateway\":%s}",
    nodeId, euiStr, panId, ch, (int)pwr, st, g_uartGatewayEnabled ? "true" : "false"
  );
}

// =================== Network form helpers ===================
static bool startNetworkForm(uint16_t panId, int8_t txPwrDbm, uint8_t ch, const char *src)
{
  EmberNetworkStatus ns = emberAfNetworkState();
  if (ns != EMBER_NO_NETWORK) {
    printLogTextToPC("net_form_skip", src, "already_in_network");
    return false;
  }

#ifdef SL_CATALOG_ZIGBEE_NETWORK_CREATOR_SECURITY_PRESENT
  EmberStatus stSec = emberAfPluginNetworkCreatorSecurityStart(true);
  emberAfCorePrintln("Creator security start: 0x%02X", stSec);
#endif

#ifdef SL_CATALOG_ZIGBEE_NETWORK_CREATOR_PRESENT
  printLogToPC("net_form_req", src, panId, ch, txPwrDbm);

  EmberStatus st = emberAfPluginNetworkCreatorNetworkForm(true, panId, txPwrDbm, ch);
  emberAfCorePrintln("Network form start: 0x%02X (PAN=0x%04X CH=%u PWR=%d)",
                     st, panId, ch, (int)txPwrDbm);
  return (st == EMBER_SUCCESS);
#else
  printLogTextToPC("net_form_fail", src, "network_creator_plugin_missing");
  return false;
#endif
}

static bool requestNetworkForm(NetCfg_t cfg, const char *src, bool force)
{
  EmberNetworkStatus ns = emberAfNetworkState();

  if (ns == EMBER_NO_NETWORK) {
    return startNetworkForm(cfg.panId, cfg.txPowerDbm, cfg.ch, src);
  }

  if (!force) {
    printLogTextToPC("net_form_skip", src, "already_in_network");
    return false;
  }

  // force: leave first, then form when network goes down
  g_pendingForm = true;
  g_pendingCfg = cfg;
  strncpy(g_pendingSrc, (src ? src : "uart"), sizeof(g_pendingSrc) - 1);
  g_pendingSrc[sizeof(g_pendingSrc) - 1] = 0;

  EmberStatus st = emberLeaveNetwork();
  emberAfCorePrintln("Leave network: 0x%02X", st);
  printLogTextToPC("net_leave_req", src, "leaving_then_form");
  return (st == EMBER_SUCCESS);
}

// =================== Button handler ===================
// PB0: short press -> form network by g_netCfg
//      long press  -> toggle UART gateway (so you can use CLI without being "eaten")
void sl_button_on_change(const sl_button_t *handle)
{
  sl_button_state_t st = sl_button_get_state(handle);

  if (handle == &sl_button_btn0) {
    if (st == SL_SIMPLE_BUTTON_PRESSED) {
      g_pb0PressTick = msTick();
      return;
    }
    if (st == SL_SIMPLE_BUTTON_RELEASED) {
      uint32_t dt = msTick() - g_pb0PressTick;
      if (dt >= PB0_LONG_PRESS_MS) {
        g_uartGatewayEnabled = !g_uartGatewayEnabled;
        printLogTextToPC("uart_gateway", "pb0_long", g_uartGatewayEnabled ? "ON" : "OFF");
      } else {
        (void)requestNetworkForm(g_netCfg, "pb0", false);
      }
      return;
    }
  }
}

// =================== Command handler ===================
static void handleCmdLine(const char *line)
{
  if (!line) return;

  const char *p = line;
  if (strncmp(p, "@CMD", 4) != 0) return;
  p += 4;
  p = skipSpaces(p);

  uint32_t id = 0;
  (void)parseUintField(p, "\"id\"", &id);

  char op[24] = {0};
  if (!parseStringField(p, "\"op\"", op, sizeof(op))) {
    printAckToPC(id, false, "missing op");
    return;
  }

  // ---- info ----
  if (strcmp(op, "info") == 0) {
    printInfoToPC();
    printAckToPC(id, true, "info");
    return;
  }

  // ---- uart gateway enable/disable ----
  if (strcmp(op, "uart_gateway_set") == 0) {
    uint32_t en = 1;
    (void)parseUintField(p, "\"enable\"", &en);
    g_uartGatewayEnabled = (en != 0);
    printLogTextToPC("uart_gateway", "uart", g_uartGatewayEnabled ? "ON" : "OFF");
    printAckToPC(id, true, "uart_gateway_set");
    return;
  }

  // ---- binding set ----
  if (strcmp(op, "bind_set") == 0) {
    uint32_t index = 0, srcEp = 0, dstEp = 0;

    if (!parseUintField(p, "\"index\"", &index)) { printAckBindToPC(id, false, 0, "missing index"); return; }
    if (!parseUintField(p, "\"src_ep\"", &srcEp)) { printAckBindToPC(id, false, index, "missing src_ep"); return; }
    if (!parseUintField(p, "\"dst_ep\"", &dstEp)) { printAckBindToPC(id, false, index, "missing dst_ep"); return; }

    char clusterStr[16] = {0};
    if (!parseStringField(p, "\"cluster\"", clusterStr, sizeof(clusterStr))) { printAckBindToPC(id, false, index, "missing cluster"); return; }
    char *endp = NULL;
    unsigned long cl = strtoul(clusterStr, &endp, 0);
    if (endp == clusterStr || cl > 0xFFFFul) { printAckBindToPC(id, false, index, "bad cluster"); return; }
    uint16_t clusterId = (uint16_t)cl;

    char euiStr[40] = {0};
    if (!parseStringField(p, "\"eui64\"", euiStr, sizeof(euiStr))) { printAckBindToPC(id, false, index, "missing eui64"); return; }

    EmberEUI64 euiLe;
    if (!parseHexEui64(euiStr, euiLe)) { printAckBindToPC(id, false, index, "bad eui64"); return; }

    EmberBindingTableEntry entry;
    memset(&entry, 0, sizeof(entry));
    entry.type = EMBER_UNICAST_BINDING;
    entry.local = (uint8_t)srcEp;
    entry.remote = (uint8_t)dstEp;
    entry.clusterId = clusterId;
    entry.networkIndex = 0;
    memcpy(entry.identifier, euiLe, EUI64_SIZE);

    EmberStatus bst = emberSetBinding((uint8_t)index, &entry);
    bool ok = (bst == EMBER_SUCCESS);

    printAckBindToPC(id, ok, index, ok ? "bind_set" : "bind_set failed");
    return;
  }

  // ---- valve control ----
  if (strcmp(op, "valve_set") == 0) {
    char value[16] = {0};
    if (!parseStringField(p, "\"value\"", value, sizeof(value))) {
      printAckToPC(id, false, "missing value");
      return;
    }

    bool wantOpen = false;
    if (strcmp(value, "open") == 0) wantOpen = true;
    else if (strcmp(value, "closed") == 0 || strcmp(value, "close") == 0) wantOpen = false;
    else { printAckToPC(id, false, "value must be open/closed"); return; }

    bool ok = setValveState(wantOpen, "manual(cmd)");
    printAckToPC(id, ok, ok ? "valve set" : "zigbee send failed");
    printDataToPC();
    return;
  }

  // ---- threshold ----
  if (strcmp(op, "threshold_set") == 0) {
    uint32_t closeTh = 0;
    if (!parseUintField(p, "\"close_th\"", &closeTh)) { printAckToPC(id, false, "missing close_th"); return; }
    if (closeTh > 65535u) { printAckToPC(id, false, "close_th too big"); return; }
    g_flowCloseTh = (uint16_t)closeTh;
    printAckToPC(id, true, "threshold updated");
    return;
  }

  // ---- set runtime net config (like CLI parameters) ----
  if (strcmp(op, "net_cfg_set") == 0) {
    uint32_t pan = g_netCfg.panId;
    uint32_t ch  = g_netCfg.ch;
    uint32_t pwr = (uint32_t)g_netCfg.txPowerDbm;

    (void)parseU32FieldAutoBase(p, "\"pan_id\"", &pan);
    (void)parseU32FieldAutoBase(p, "\"ch\"", &ch);
    (void)parseU32FieldAutoBase(p, "\"tx_power\"", &pwr);

    if (ch < 11 || ch > 26) { printAckToPC(id, false, "bad channel"); return; }

    g_netCfg.panId = (uint16_t)pan;
    g_netCfg.ch = (uint8_t)ch;
    g_netCfg.txPowerDbm = (int8_t)pwr;

    printLogToPC("net_cfg_set", "uart", g_netCfg.panId, g_netCfg.ch, g_netCfg.txPowerDbm);
    printAckToPC(id, true, "net cfg updated");
    return;
  }

  // ---- form network (optional force) ----
  if (strcmp(op, "net_form") == 0) {
    uint32_t pan = g_netCfg.panId;
    uint32_t ch  = g_netCfg.ch;
    uint32_t pwr = (uint32_t)g_netCfg.txPowerDbm;
    uint32_t force = 0;

    (void)parseU32FieldAutoBase(p, "\"pan_id\"", &pan);
    (void)parseU32FieldAutoBase(p, "\"ch\"", &ch);
    (void)parseU32FieldAutoBase(p, "\"tx_power\"", &pwr);
    (void)parseUintField(p, "\"force\"", &force);

    if (ch < 11 || ch > 26) { printAckToPC(id, false, "bad channel"); return; }

    NetCfg_t cfg = { (uint16_t)pan, (uint8_t)ch, (int8_t)pwr };
    bool ok = requestNetworkForm(cfg, "uart", (force != 0));

    printAckToPC(id, ok, ok ? "net_form accepted" : "net_form rejected");
    return;
  }

  printAckToPC(id, false, "unknown op");
}

// =================== UART Poll (non-blocking best-effort) ===================
static char   s_uartLine[UART_LINE_MAX];
static uint16_t s_uartLen = 0;

static void uartPoll(void)
{
  char c;
  size_t n = 0;
  sl_status_t st = sl_iostream_read(SL_IOSTREAM_STDIN, &c, 1, &n);

  while ((st == SL_STATUS_OK) && (n == 1)) {

    if (c == '\r') {
      // ignore CR
    } else if (c == '\n') {
      if (s_uartLen > 0) {
        s_uartLine[s_uartLen] = 0;

        if (strncmp(s_uartLine, "@CMD", 4) == 0) {
          handleCmdLine(s_uartLine);
        }

        s_uartLen = 0;
      }
    } else {
      if ((uint16_t)(s_uartLen + 1u) < (uint16_t)UART_LINE_MAX) {
        s_uartLine[s_uartLen++] = c;
      } else {
        s_uartLen = 0;
      }
    }

    n = 0;
    st = sl_iostream_read(SL_IOSTREAM_STDIN, &c, 1, &n);
  }
}

// =================== ZCL Report parser ===================
bool emberAfPreCommandReceivedCallback(EmberAfClusterCommand *cmd)
{
  if (cmd == NULL || cmd->apsFrame == NULL) return false;
  if (cmd->commandId != ZCL_REPORT_ATTRIBUTES_COMMAND_ID) return false;

  EmberAfClusterId clusterId = cmd->apsFrame->clusterId;

  const uint8_t *p = cmd->buffer + cmd->payloadStartIndex;
  uint16_t len = (uint16_t)(cmd->bufLen - cmd->payloadStartIndex);

  bool updated = false;
  uint16_t i = 0;

  while (i + 3 <= len) {
    uint16_t attrId = u16le(&p[i]);
    uint8_t type = p[i + 2];
    i += 3;

    if (clusterId == ZCL_FLOW_MEASUREMENT_CLUSTER_ID
        && attrId == 0x0000
        && type == ZCL_INT16U_ATTRIBUTE_TYPE) {

      if (i + 2 > len) break;
      uint16_t v = u16le(&p[i]);
      i += 2;

      if (g_flow != v) { g_flow = v; updated = true; }
    }
    else if (clusterId == ZCL_POWER_CONFIGURATION_CLUSTER_ID
             && attrId == 0x0021
             && type == ZCL_INT8U_ATTRIBUTE_TYPE) {

      if (i + 1 > len) break;
      uint8_t half = p[i];
      i += 1;

      uint8_t percent = (uint8_t)(half / 2u);
      if (g_batteryPercent != percent) { g_batteryPercent = percent; updated = true; }
    } else {
      // stop on unexpected format to avoid desync
      break;
    }
  }

  if (updated) {
    autoControlLogic();
    printDataToPC();
  }

  return false;
}

// =================== Network Creator callbacks ===================
void emberAfMainInitCallback(void)
{
  EmberNetworkStatus state = emberAfNetworkState();
  emberAfCorePrintln("Coordinator init, netState=%d", state);

  // Do NOT auto-form here (user controls via PB0 / dashboard / CLI)
  printLogToPC("net_cfg", "boot", g_netCfg.panId, g_netCfg.ch, g_netCfg.txPowerDbm);

  printInfoToPC();
  printDataToPC();
}

void emberAfPluginNetworkCreatorCompleteCallback(const EmberNetworkParameters *network,
                                                bool usedSecondaryChannels)
{
  (void)usedSecondaryChannels;

  emberAfCorePrintln("Formed network PAN=0x%04X CH=%u", network->panId, network->radioChannel);
  printLogToPC("net_formed", "stack", network->panId, network->radioChannel, g_netCfg.txPowerDbm);

#ifdef SL_CATALOG_ZIGBEE_NETWORK_CREATOR_SECURITY_PRESENT
  EmberStatus st = emberAfPluginNetworkCreatorSecurityOpenNetwork();
  emberAfCorePrintln("Open network: 0x%02X", st);
  g_networkOpen = true;
  g_openTick = msTick();
#endif

  printInfoToPC();
}

void emberAfStackStatusCallback(EmberStatus status)
{
  // When leaving completes, network goes down => do pending re-form
  if (status == EMBER_NETWORK_DOWN && g_pendingForm) {
    g_pendingForm = false;
    (void)startNetworkForm(g_pendingCfg.panId, g_pendingCfg.txPowerDbm, g_pendingCfg.ch, g_pendingSrc);
  }
}

void emberAfMainTickCallback(void)
{
  if (g_uartGatewayEnabled) {
    uartPoll();
  }

#ifdef SL_CATALOG_ZIGBEE_NETWORK_CREATOR_SECURITY_PRESENT
  if (g_networkOpen && (msTick() - g_openTick >= OPEN_JOIN_MS)) {
    EmberStatus st = emberAfPluginNetworkCreatorSecurityCloseNetwork();
    emberAfCorePrintln("Close network after %u ms: 0x%02X", OPEN_JOIN_MS, st);
    g_networkOpen = false;
    printLogTextToPC("net_close", "timer", "closed_open_join_window");
  }
#endif
}

void emberAfRadioNeedsCalibratingCallback(void)
{
  sl_mac_calibrate_current_channel();
}
