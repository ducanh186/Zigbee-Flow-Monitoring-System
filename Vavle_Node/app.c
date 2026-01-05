#include "app/framework/include/af.h"
#include "network-steering.h"
#include "sl_simple_led_instances.h"
#include "zap-id.h"
#include "stack/include/ember.h"

void emberAfMainInitCallback(void)
{
  emberAfCorePrintln("Valve init: RxOnWhenIdle=1 -> start steering");
  if (emberAfNetworkState() != EMBER_JOINED_NETWORK) {
    EmberStatus st = emberAfPluginNetworkSteeringStart();
    emberAfCorePrintln("Steering start: 0x%02X", st);
  }
}

void emberAfPluginNetworkSteeringCompleteCallback(EmberStatus status,
                                                 uint8_t totalBeacons,
                                                 uint8_t joinAttempts,
                                                 uint8_t finalState)
{
  (void)totalBeacons; (void)joinAttempts; (void)finalState;
  emberAfCorePrintln("Join complete: 0x%02X", status);
}

void emberAfPostAttributeChangeCallback(uint8_t endpoint,
                                       EmberAfClusterId clusterId,
                                       EmberAfAttributeId attributeId,
                                       uint8_t mask,
                                       uint16_t manufacturerCode,
                                       uint8_t type,
                                       uint8_t size,
                                       uint8_t* value)
{
  (void)mask; (void)manufacturerCode; (void)type; (void)size; (void)value;

  if (endpoint == 1 && clusterId == ZCL_ON_OFF_CLUSTER_ID &&
      attributeId == ZCL_ON_OFF_ATTRIBUTE_ID) {

    uint8_t onOffValue = 0;
    EmberAfStatus st = emberAfReadServerAttribute(endpoint,
                                                 ZCL_ON_OFF_CLUSTER_ID,
                                                 ZCL_ON_OFF_ATTRIBUTE_ID,
                                                 &onOffValue,
                                                 sizeof(onOffValue));
    if (st == EMBER_ZCL_STATUS_SUCCESS) {
      if (onOffValue) {
        sl_led_turn_on(&sl_led_led0);
        emberAfCorePrintln("Valve OPEN (ON) -> LED ON");
      } else {
        sl_led_turn_off(&sl_led_led0);
        emberAfCorePrintln("Valve CLOSE (OFF) -> LED OFF");
      }
    } else {
      emberAfCorePrintln("Read OnOff attr err: 0x%02X", st);
    }
  }
}

bool emberAfPreCommandReceivedCallback(EmberAfClusterCommand *cmd)
{
  if (!cmd || !cmd->apsFrame) return false;

  if (cmd->apsFrame->clusterId == ZCL_ON_OFF_CLUSTER_ID) {
    emberAfCorePrintln("RX OnOff: cmdId=0x%02X src=0x%04X ep=%u",
                       cmd->commandId, cmd->source, cmd->apsFrame->destinationEndpoint);
  }
  return false;
}

void emberAfRadioNeedsCalibratingCallback(void)
{
  sl_mac_calibrate_current_channel();
}
