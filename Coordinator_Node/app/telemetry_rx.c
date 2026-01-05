#include "app_config.h"
#include "app_state.h"
#include "app_utils.h"
#include "app_log.h"
#include "valve_ctrl.h"
#include "app/framework/include/af.h"
#include "app_zcl_fallback.h"
#include "lcd_ui.h"
#include "app/framework/include/af.h"

#include <stdint.h>
#include <stdbool.h>

bool emberAfPreCommandReceivedCallback(EmberAfClusterCommand *cmd)
{
  if (cmd == NULL || cmd->apsFrame == NULL) return false;

  // 1) Telemetry reports (Flow + Battery)
  if (cmd->commandId == ZCL_REPORT_ATTRIBUTES_COMMAND_ID) {
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

        if (g_flow != v) { 
          g_flow = v; 
          updated = true;
          lcd_ui_set_flow(v);  // Update LCD
        }
      }
      else if (clusterId == ZCL_POWER_CONFIGURATION_CLUSTER_ID
               && attrId == 0x0021
               && type == ZCL_INT8U_ATTRIBUTE_TYPE) {

        if (i + 1 > len) break;
        uint8_t half = p[i];
        i += 1;

        uint8_t percent = (uint8_t)(half / 2u);
        if (g_batteryPercent != percent) { 
          g_batteryPercent = percent; 
          updated = true;
          lcd_ui_set_battery(percent);  // Update LCD
        }
      } else {
        break;
      }
    }

    if (updated) {
      //lcdUiShowMsg("RX", "DATA ARRIVED");
      valveCtrlAutoControl();
      appLogData();

    }
    return false;
  }

  // 2) Debug: ZCL Default Response from valve
  if (cmd->apsFrame->clusterId == ZCL_ON_OFF_CLUSTER_ID && cmd->commandId == 0x0B) {
    emberAfCorePrintln("@LOG {\"event\":\"zcl_default_rsp\",\"cluster\":\"0x0006\",\"src\":\"0x%04X\"}",
                       cmd->source);
  }

  return false;
}
