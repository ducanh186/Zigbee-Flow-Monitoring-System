#include "net_mgr.h"
#include "app_config.h"
#include "app_utils.h"
#include "app_log.h"
#include "lcd_ui.h"

#include "app/framework/include/af.h"
#include "stack/include/ember.h"

#include <string.h>
#include <stdio.h>

#ifdef SL_CATALOG_ZIGBEE_NETWORK_CREATOR_PRESENT
#include "network-creator.h"
#endif
#ifdef SL_CATALOG_ZIGBEE_NETWORK_CREATOR_SECURITY_PRESENT
#include "network-creator-security.h"
#endif

NetCfg_t g_netCfg = {
  .panId = (uint16_t)DEFAULT_PAN_ID,
  .ch = (uint8_t)DEFAULT_CHANNEL,
  .txPowerDbm = (int8_t)DEFAULT_TX_POWER_DBM,
};

static bool     g_pendingForm = false;
static NetCfg_t g_pendingCfg;
static char     g_pendingSrc[8] = "uart";

static bool     g_networkOpen = false;
static uint32_t g_openTick = 0;

static bool startNetworkForm(uint16_t panId, int8_t txPwrDbm, uint8_t ch, const char *src)
{
  if (emberAfNetworkState() != EMBER_NO_NETWORK) {
    appLogLog("net_form_skip", src, "already_in_network");
    return false;
  }

#ifdef SL_CATALOG_ZIGBEE_NETWORK_CREATOR_SECURITY_PRESENT
  (void)emberAfPluginNetworkCreatorSecurityStart(true);
#endif

#ifdef SL_CATALOG_ZIGBEE_NETWORK_CREATOR_PRESENT
  EmberStatus st = emberAfPluginNetworkCreatorNetworkForm(true, panId, txPwrDbm, ch);
  emberAfCorePrintln("Network form start: 0x%02X (PAN=0x%04X CH=%u PWR=%d)",
                     st, panId, ch, (int)txPwrDbm);
  return (st == EMBER_SUCCESS);
#else
  appLogLog("net_form_fail", src, "network_creator_plugin_missing");
  return false;
#endif
}

bool netMgrRequestForm(NetCfg_t cfg, const char *src, bool force)
{
  EmberNetworkStatus ns = emberAfNetworkState();

  if (ns == EMBER_NO_NETWORK) {
    return startNetworkForm(cfg.panId, cfg.txPowerDbm, cfg.ch, src);
  }

  if (!force) {
    appLogLog("net_form_skip", src, "already_in_network");
    return false;
  }

  g_pendingForm = true;
  g_pendingCfg = cfg;
  strncpy(g_pendingSrc, (src ? src : "uart"), sizeof(g_pendingSrc) - 1);
  g_pendingSrc[sizeof(g_pendingSrc) - 1] = 0;

  EmberStatus st = emberLeaveNetwork();
  emberAfCorePrintln("Leave network: 0x%02X", st);
  appLogLog("net_leave_req", src, "leaving_then_form");
  return (st == EMBER_SUCCESS);
}

void netMgrTick(void)
{
#ifdef SL_CATALOG_ZIGBEE_NETWORK_CREATOR_SECURITY_PRESENT
  if (g_networkOpen && (msTick() - g_openTick >= OPEN_JOIN_MS)) {
    EmberStatus st = emberAfPluginNetworkCreatorSecurityCloseNetwork();
    emberAfCorePrintln("Close network after %u ms: 0x%02X", OPEN_JOIN_MS, st);
    g_networkOpen = false;
    appLogLog("net_close", "timer", "closed_open_join_window");
  }
#endif
}

// callback: formed network
void emberAfPluginNetworkCreatorCompleteCallback(const EmberNetworkParameters *network,
                                                bool usedSecondaryChannels)
{
  (void)usedSecondaryChannels;
  emberAfCorePrintln("Formed network PAN=0x%04X CH=%u", network->panId, network->radioChannel);
  lcd_ui_set_network("NET: ONLINE");

#ifdef SL_CATALOG_ZIGBEE_NETWORK_CREATOR_SECURITY_PRESENT
  EmberStatus st = emberAfPluginNetworkCreatorSecurityOpenNetwork();
  emberAfCorePrintln("Open network: 0x%02X", st);
  g_networkOpen = true;
  g_openTick = msTick();
#endif

  appLogInfo();
}

// callback: stack status (used for pending form)
void emberAfStackStatusCallback(EmberStatus status)
{
  // Update LCD with network status
  if (status == EMBER_NETWORK_UP) {
    lcd_ui_set_network("NET: ONLINE");
  } else if (status == EMBER_NETWORK_DOWN) {
    lcd_ui_set_network("NET: OFFLINE");
  }

  if (status == EMBER_NETWORK_DOWN && g_pendingForm) {
    g_pendingForm = false;
    (void)startNetworkForm(g_pendingCfg.panId, g_pendingCfg.txPowerDbm, g_pendingCfg.ch, g_pendingSrc);
  }
}
