#include "cmd_handler.h"
#include "app_config.h"
#include "app_state.h"
#include "app_utils.h"
#include "app_log.h"
#include "net_mgr.h"
#include "valve_ctrl.h"
#include "sl_cli.h"

#include <string.h>
#include <stdio.h>

// ===== COMMAND DEBOUNCE =====
// Prevent duplicate command processing (Dashboard may spam)
#define CMD_DEBOUNCE_MS       500   // Min interval between same-type commands
#define CMD_DEDUP_WINDOW_MS   2000  // Window to detect duplicate IDs

static uint32_t s_lastModeSetTick = 0;
static uint32_t s_lastValveSetTick = 0;
static uint32_t s_lastCmdId = 0xFFFFFFFF;
static uint32_t s_lastCmdTick = 0;

static bool isDuplicateCmd(uint32_t id)
{
  uint32_t now = halCommonGetInt32uMillisecondTick();
  
  // Check if same ID within dedup window
  if (id == s_lastCmdId && (now - s_lastCmdTick) < CMD_DEDUP_WINDOW_MS) {
    appLogLog("CMD", "duplicate", "\"id\":%lu,\"ignored\":true", (unsigned long)id);
    return true;
  }
  
  s_lastCmdId = id;
  s_lastCmdTick = now;
  return false;
}

void cmdHandleLine(const char *line)
{
  if (!line) return;

  const char *p = line;
  if (strncmp(p, "@CMD", 4) != 0) return;
  p += 4;
  p = skipSpaces(p);

  uint32_t id = 0;
  (void)parseUintField(p, "\"id\"", &id);
  
  // Duplicate detection
  if (isDuplicateCmd(id)) {
    return;  // Silently ignore duplicate
  }

  char op[28] = {0};
  if (!parseStringField(p, "\"op\"", op, sizeof(op))) {
    appLogAck(id, false, "missing op");
    return;
  }

  uint32_t now = halCommonGetInt32uMillisecondTick();

  if (strcmp(op, "info") == 0) {
    appLogInfo();
    appLogAck(id, true, "info");
    return;
  }

  if (strcmp(op, "mode_set") == 0) {
    // Debounce: ignore if too fast
    if ((now - s_lastModeSetTick) < CMD_DEBOUNCE_MS) {
      appLogAck(id, false, "debounced");
      return;
    }
    s_lastModeSetTick = now;
    
    char value[16] = {0};
    if (!parseStringField(p, "\"value\"", value, sizeof(value))) {
      appLogAck(id, false, "missing value");
      return;
    }
    if (strcmp(value, "auto") == 0) g_mode = MODE_AUTO;
    else if (strcmp(value, "manual") == 0) g_mode = MODE_MANUAL;
    else { appLogAck(id, false, "value must be auto/manual"); return; }

    appLogAck(id, true, "mode set");
    valveCtrlAutoControl();
    appLogData();
    return;
  }

  if (strcmp(op, "threshold_set") == 0) {
    uint32_t closeTh = 0, openTh = 0;
    if (!parseUintField(p, "\"close_th\"", &closeTh)) { appLogAck(id, false, "missing close_th"); return; }
    (void)parseUintField(p, "\"open_th\"", &openTh);

    if (openTh >= closeTh) { appLogAck(id, false, "open_th must be < close_th"); return; }
    if (closeTh > 65535u || openTh > 65535u) { appLogAck(id, false, "th too big"); return; }

    valveCtrlSetThresholds((uint16_t)closeTh, (uint16_t)openTh);

    appLogAck(id, true, "threshold updated");
    valveCtrlAutoControl();
    appLogData();
    return;
  }

  if (strcmp(op, "valve_path_set") == 0) {
    char value[16] = {0};
    if (!parseStringField(p, "\"value\"", value, sizeof(value))) { appLogAck(id, false, "missing value"); return; }

    if (strcmp(value, "auto") == 0) valveCtrlSetPath(VALVE_PATH_AUTO);
    else if (strcmp(value, "direct") == 0) valveCtrlSetPath(VALVE_PATH_DIRECT);
    else if (strcmp(value, "binding") == 0) valveCtrlSetPath(VALVE_PATH_BINDING);
    else { appLogAck(id, false, "value must be auto/direct/binding"); return; }

    appLogAck(id, true, "valve_path_set");
    appLogInfo();
    return;
  }

  if (strcmp(op, "valve_target_set") == 0) {
    uint32_t nodeId = 0;
    uint32_t dstEp = (uint32_t)VALVE_EP_DEFAULT;

    if (!parseU32FieldAny(p, "\"node_id\"", &nodeId)) { appLogAck(id, false, "missing node_id"); return; }
    (void)parseUintField(p, "\"dst_ep\"", &dstEp);

    valveCtrlSetTarget((EmberNodeId)nodeId, (uint8_t)dstEp);

    appLogAck(id, true, "valve_target_set");
    appLogInfo();
    return;
  }

  if (strcmp(op, "valve_pair") == 0) {
    char euiStr[40] = {0};
    uint32_t nodeId = 0;
    uint32_t bindIndex = 0;
    uint32_t dstEp = (uint32_t)VALVE_EP_DEFAULT;

    if (!parseStringField(p, "\"eui64\"", euiStr, sizeof(euiStr))) { appLogAck(id, false, "missing eui64"); return; }
    if (!parseU32FieldAny(p, "\"node_id\"", &nodeId)) { appLogAck(id, false, "missing node_id"); return; }
    (void)parseUintField(p, "\"bind_index\"", &bindIndex);
    (void)parseUintField(p, "\"dst_ep\"", &dstEp);

    bool ok = valveCtrlPair(euiStr, (EmberNodeId)nodeId, (uint8_t)bindIndex, (uint8_t)dstEp);
    appLogAck(id, ok, ok ? "valve_pair set" : "bad eui64");
    if (ok) appLogInfo();
    return;
  }

  if (strcmp(op, "valve_set") == 0) {
    // Debounce: ignore if too fast
    if ((now - s_lastValveSetTick) < CMD_DEBOUNCE_MS) {
      appLogAck(id, false, "debounced");
      return;
    }
    s_lastValveSetTick = now;
    
    if (g_mode == MODE_AUTO) {
      appLogAck(id, false, "rejected: AUTO mode");
      return;
    }

    char value[16] = {0};
    if (!parseStringField(p, "\"value\"", value, sizeof(value))) {
      appLogAck(id, false, "missing value");
      return;
    }

    bool wantOpen = false;
    if (strcmp(value, "open") == 0) wantOpen = true;
    else if (strcmp(value, "closed") == 0 || strcmp(value, "close") == 0) wantOpen = false;
    else { appLogAck(id, false, "value must be open/closed"); return; }

    (void)valveCtrlQueueTx(id, wantOpen);
    return;
  }

  if (strcmp(op, "net_cfg_set") == 0) {
    uint32_t pan = g_netCfg.panId, ch = g_netCfg.ch, pwr = (uint32_t)g_netCfg.txPowerDbm;
    (void)parseU32FieldAny(p, "\"pan_id\"", &pan);
    (void)parseU32FieldAny(p, "\"ch\"", &ch);
    (void)parseU32FieldAny(p, "\"tx_power\"", &pwr);

    if (ch < 11 || ch > 26) { appLogAck(id, false, "bad channel"); return; }

    g_netCfg.panId = (uint16_t)pan;
    g_netCfg.ch = (uint8_t)ch;
    g_netCfg.txPowerDbm = (int8_t)pwr;

    appLogAck(id, true, "net cfg updated");
    return;
  }

  if (strcmp(op, "net_form") == 0) {
    uint32_t pan = g_netCfg.panId, ch = g_netCfg.ch, pwr = (uint32_t)g_netCfg.txPowerDbm, force = 0;
    (void)parseU32FieldAny(p, "\"pan_id\"", &pan);
    (void)parseU32FieldAny(p, "\"ch\"", &ch);
    (void)parseU32FieldAny(p, "\"tx_power\"", &pwr);
    (void)parseUintField(p, "\"force\"", &force);

    if (ch < 11 || ch > 26) { appLogAck(id, false, "bad channel"); return; }

    NetCfg_t cfg = { (uint16_t)pan, (uint8_t)ch, (int8_t)pwr };
    bool ok = netMgrRequestForm(cfg, "uart", (force != 0));
    appLogAck(id, ok, ok ? "net_form accepted" : "net_form rejected");
    return;
  }

  if (strcmp(op, "uart_gateway_set") == 0) {
    uint32_t en = 1;
    (void)parseUintField(p, "\"enable\"", &en);
    g_uartGatewayEnabled = (en != 0);
    appLogAck(id, true, "uart_gateway_set");
    return;
  }

  appLogAck(id, false, "unknown op");
}

// ===== CLI COMMAND HANDLER =====
// Called by CLI framework when user types: json {"id":1,"op":"info"}
// This bridges CLI input to cmdHandleLine() by prepending @CMD prefix
void cli_json_command(sl_cli_command_arg_t *arguments)
{
  // Get the JSON string argument
  char *json_arg = sl_cli_get_argument_string(arguments, 0);
  if (!json_arg || json_arg[0] == '\0') {
    appLogLog("CMD", "cli_usage", "\"msg\":\"json {\\\"id\\\":N,\\\"op\\\":\\\"...\\\"}\"");
    return;
  }
  
  // Build @CMD line: "@CMD " + json
  static char cmdBuf[256];
  int n = snprintf(cmdBuf, sizeof(cmdBuf), "@CMD %s", json_arg);
  if (n < 0 || (size_t)n >= sizeof(cmdBuf)) {
    appLogLog("CMD", "cli_error", "\"msg\":\"command too long\"");
    return;
  }
  
  // Process through normal command handler
  cmdHandleLine(cmdBuf);
}
