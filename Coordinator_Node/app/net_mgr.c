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
    appLogLog("NET", "form_skip", "\"reason\":\"already_in_network\",\"src\":\"%s\"", src ? src : "");
    return false;
  }

#ifdef SL_CATALOG_ZIGBEE_NETWORK_CREATOR_SECURITY_PRESENT
  (void)emberAfPluginNetworkCreatorSecurityStart(true);
#endif

#ifdef SL_CATALOG_ZIGBEE_NETWORK_CREATOR_PRESENT
  EmberStatus st = emberAfPluginNetworkCreatorNetworkForm(true, panId, txPwrDbm, ch);
  appLogLog("NET", "form_start", "\"zstatus\":\"0x%02X\",\"pan_id\":\"0x%04X\",\"ch\":%u,\"pwr\":%d,\"src\":\"%s\"",
    (unsigned)st, (unsigned)panId, (unsigned)ch, (int)txPwrDbm, src ? src : "");
  return (st == EMBER_SUCCESS);
#else
  appLogLog("NET", "form_fail", "\"reason\":\"network_creator_missing\",\"src\":\"%s\"", src ? src : "");
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
    appLogLog("NET", "form_skip", "\"reason\":\"already_in_network\",\"src\":\"%s\"", src ? src : "");
    return false;
  }

  g_pendingForm = true;
  g_pendingCfg = cfg;
  strncpy(g_pendingSrc, (src ? src : "uart"), sizeof(g_pendingSrc) - 1);
  g_pendingSrc[sizeof(g_pendingSrc) - 1] = 0;

  EmberStatus st = emberLeaveNetwork();
  appLogLog("NET", "leave_req", "\"zstatus\":\"0x%02X\",\"src\":\"%s\"", (unsigned)st, src ? src : "");
  return (st == EMBER_SUCCESS);
}

void netMgrTick(void)
{
#ifdef SL_CATALOG_ZIGBEE_NETWORK_CREATOR_SECURITY_PRESENT
  if (g_networkOpen && (msTick() - g_openTick >= OPEN_JOIN_MS)) {
    EmberStatus st = emberAfPluginNetworkCreatorSecurityCloseNetwork();
    appLogLog("NET", "close_join", "\"zstatus\":\"0x%02X\",\"after_ms\":%u", (unsigned)st, (unsigned)OPEN_JOIN_MS);
    g_networkOpen = false;
  }
#endif
}

// callback: formed network
void emberAfPluginNetworkCreatorCompleteCallback(const EmberNetworkParameters *network,
                                                bool usedSecondaryChannels)
{
  (void)usedSecondaryChannels;
  appLogLog("NET", "formed", "\"pan_id\":\"0x%04X\",\"ch\":%u", (unsigned)network->panId, (unsigned)network->radioChannel);
  lcd_ui_set_network("NET: ONLINE");

#ifdef SL_CATALOG_ZIGBEE_NETWORK_CREATOR_SECURITY_PRESENT
  EmberStatus st = emberAfPluginNetworkCreatorSecurityOpenNetwork();
  appLogLog("NET", "open_join", "\"zstatus\":\"0x%02X\"", (unsigned)st);
  g_networkOpen = true;
  g_openTick = msTick();
#endif

  appLogEmitHeartbeat();  // Emit @INFO immediately after network formed
}

// callback: stack status (used for pending form)
void emberAfStackStatusCallback(EmberStatus status)
{
  // Log stack status change
  appLogLog("NET", "stack_status", "\"zstatus\":\"0x%02X\"", (unsigned)status);

  // Update LCD with network status
  if (status == EMBER_NETWORK_UP) {
    lcd_ui_set_network("NET: ONLINE");
    appLogEmitHeartbeat();  // Emit @INFO on network up
  } else if (status == EMBER_NETWORK_DOWN) {
    lcd_ui_set_network("NET: OFFLINE");
    appLogEmitHeartbeat();  // Emit @INFO on network down
  }

  if (status == EMBER_NETWORK_DOWN && g_pendingForm) {
    g_pendingForm = false;
    (void)startNetworkForm(g_pendingCfg.panId, g_pendingCfg.txPowerDbm, g_pendingCfg.ch, g_pendingSrc);
  }
}
