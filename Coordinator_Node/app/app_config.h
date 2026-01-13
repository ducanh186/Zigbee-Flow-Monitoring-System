#ifndef APP_CONFIG_H
#define APP_CONFIG_H

#include <stdint.h>

// ===== App constants (OK) =====
#define COORD_EP_TELEM       1
#define COORD_EP_CONTROL     2
#define VALVE_EP_DEFAULT     1

#define OPEN_JOIN_MS         180000u

#define DEFAULT_PAN_ID       0xBEEFu
#define DEFAULT_CHANNEL      11u
#define DEFAULT_TX_POWER_DBM 8

#define UART_LINE_MAX        220u
#define PB0_LONG_PRESS_MS    1500u

// ===== APS option naming compatibility (OK to keep) =====
#ifndef EMBER_APS_OPTION_ACK_REQUEST
  #ifdef EMBER_OPTIONS_ACK_REQUESTED
    #define EMBER_APS_OPTION_ACK_REQUEST EMBER_OPTIONS_ACK_REQUESTED
  #endif
#endif

#ifndef EMBER_APS_OPTION_RETRY
  #ifdef EMBER_OPTIONS_RETRY
    #define EMBER_APS_OPTION_RETRY EMBER_OPTIONS_RETRY
  #endif
#endif

// ===== Debug print control =====
// Comment out to disable debug prints (improves UART reliability)
// #define DEBUG_LCD_PRINTS     1
// #define DEBUG_NET_PRINTS     1
// #define DEBUG_VALVE_PRINTS   1

// Keep protocol prints (required for Gateway communication)
#define ENABLE_PROTOCOL_PRINTS  1

#endif
