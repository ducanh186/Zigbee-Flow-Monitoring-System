# Installed Components - Zigbee Coordinator Node

**Project**: Coordinator_Node  
**SDK**: Gecko SDK 4.5.0  
**Platform**: EFR32MG12P (BRD4162A)  
**Date**: January 5, 2026

---

## Hardware Components

### Bootloader
- ✅ **gecko_bootloader_interface** - Bootloader interface for application updates

### Device Initialization
- ✅ **device_init** - Core device initialization
- ✅ **device_init_clocks** - Clock configuration
- ✅ **device_init_core** - Core system initialization
- ✅ **device_init_dcdc** - DC-DC converter configuration
- ✅ **device_init_emu** - Energy management unit
- ✅ **device_init_hfxo** - High-frequency crystal oscillator
- ✅ **device_init_lfxo** - Low-frequency crystal oscillator
- ✅ **device_init_nvic** - Nested vector interrupt controller

### Display (LCD)
- ✅ **dmd_memlcd** - Memory LCD driver
- ✅ **glib** - Graphics library for LCD rendering
- ✅ **memlcd_usart** - USART interface for MemLCD

### Buttons & LEDs
- ✅ **simple_button** - Button framework
  - ✅ **simple_button_btn0** - Push Button 0 instance
  - ✅ **simple_button_btn1** - Push Button 1 instance
- ✅ **simple_led** - LED framework
  - ✅ **simple_led_led0** - LED 0 instance

### I/O & Debug
- ✅ **iostream** - I/O stream abstraction
- ✅ **iostream_uart_common** - Common UART I/O
- ✅ **iostream_usart** - USART I/O stream
- ✅ **retarget_stdio** - Standard I/O retargeting to UART

### Command Line Interface
- ✅ **cli** - Command-line interface framework
- ✅ **zigbee_cli** - Zigbee-specific CLI commands
- ✅ **zigbee_core_cli** - Zigbee core CLI
- ✅ **zigbee_zcl_cli** - Zigbee ZCL cluster CLI

---

## Core Libraries

### EMLIB
- ✅ **emlib_core** - Core EMLIB peripheral library
- ✅ **emlib_core_debug_config** - Debug configuration

### Legacy HAL
- ✅ **legacy_hal** - Legacy hardware abstraction layer
- ✅ **legacy_hal_soc** - SoC-specific HAL
- ✅ **legacy_hal_wdog** - Watchdog timer HAL

### Utilities
- ✅ **printf** - Printf implementation
- ✅ **legacy_printf** - Legacy printf support
- ✅ **sleeptimer** - Sleep timer service
- ✅ **power_manager** - Power management framework

---

## Storage & Security

### Non-Volatile Memory
- ✅ **nvm3** - NVM3 storage driver
- ✅ **token_manager** - Token management
- ✅ **token_manager_nvm3** - NVM3 token backend

### Flash
- ✅ **mx25_flash_shutdown_usart** - External flash shutdown (power saving)

---

## Radio & Physical Layer

### RAIL (Radio Abstraction Interface Layer)
- ✅ **rail_lib** - RAIL library
- ✅ **rail_util_ieee802154_phy_select** - IEEE 802.15.4 PHY selector
- ✅ **rail_util_ieee802154_stack_event** - Stack event handling
- ✅ **rail_util_pti** - Packet Trace Interface (debug)

### Zigbee PHY
- ✅ **zigbee_phy_2_4** - 2.4 GHz Zigbee PHY

---

## Zigbee Stack Components

### Core Stack
- ✅ **zigbee_pro_stack** - Zigbee PRO stack (full-featured)
- ✅ **zigbee_stack_common** - Common stack utilities
- ✅ **zigbee_app_framework_common** - Application framework core

### Network Formation & Management
- ✅ **zigbee_network_creator** - Network formation for coordinators
- ✅ **zigbee_network_creator_security** - Trust Center security
- ✅ **zigbee_network_steering** - Network joining assistance
- ✅ **zigbee_network_find** - Network discovery
- ✅ **zigbee_network_find_sub_ghz** - Sub-GHz network discovery
- ✅ **zigbee_form_and_join** - Network form/join utilities

### Device Binding
- ✅ **zigbee_find_and_bind_initiator** - Find and bind initiator role
- ✅ **zigbee_find_and_bind_target** - Find and bind target role

### Routing
- ✅ **zigbee_enhanced_routing** - Enhanced routing features
- ✅ **zigbee_source_route** - Source routing support
- ✅ **zigbee_scan_dispatch** - Scan coordination

### Security
- ✅ **zigbee_security_manager** - Centralized security management
- ✅ **zigbee_classic_key_storage** - Classic key storage
- ✅ **zigbee_update_tc_link_key** - Trust Center link key updates
- ✅ **zigbee_strong_random_api_radio** - Hardware random number generator

---

## Zigbee Cluster Library (ZCL)

### ZCL Framework
- ✅ **zigbee_zcl_framework_core** - ZCL framework core
- ✅ **zigbee_device_config** - Device type configuration

### ZCL Clusters (Server)
- ✅ **zigbee_basic** - Basic cluster (device info)
- ✅ **zigbee_identify** - Identify cluster
- ✅ **zigbee_zll_identify_server** - ZLL identify server

### ZCL Clusters (Client)
- ✅ **zigbee_on_off** - On/Off cluster client (valve control)
- ✅ **zigbee_groups_client** - Groups cluster client
- ✅ **zigbee_scenes_client** - Scenes cluster client

---

## Debug & Diagnostic Tools

### Debug Printing
- ✅ **connect_debug_print** - Debug print utilities
- ✅ **zigbee_debug_print** - Zigbee-specific debug

### Diagnostics
- ✅ **zigbee_counters** - Network/stack counters
- ✅ **zigbee_stack_diagnostics** - Stack diagnostic tools
- ✅ **zigbee_signature_decode** - Signature decoding

### Manufacturing
- ✅ **zigbee_mfglib** - Manufacturing library
- ✅ **zigbee_manufacturing_library_cli** - Manufacturing CLI

### Bootloader Support
- ✅ **zigbee_application_bootloader** - OTA bootloader integration

---

## Component Summary

| Category | Count |
|----------|-------|
| **Hardware & Drivers** | 18 |
| **Core Libraries** | 7 |
| **Storage & Security** | 4 |
| **Radio & PHY** | 5 |
| **Zigbee Stack** | 15 |
| **ZCL Framework** | 8 |
| **Debug & Tools** | 7 |
| **TOTAL** | **64 components** |

---

## Custom Application Modules

Located in `app/` directory (not SDK components):

- **app.c** - Main application callbacks
- **net_mgr.c** - Network formation/management
- **valve_ctrl.c** - Valve control logic (3 TX paths)
- **telemetry_rx.c** - ZCL attribute report handler
- **uart_link.c** - UART protocol parser
- **cmd_handler.c** - JSON command dispatcher
- **app_log.c** - Structured logging (@INFO/@DATA/@ACK/@LOG)
- **lcd_ui.c** - MemLCD user interface
- **app_state.c** - Global state management
- **buttons.c** - Button handlers (PB0/PB1)
- **app_utils.c** - Parsing and utility functions
- **cli_commands.c** - Custom CLI commands

---

## Configuration Files

- **Coordinator_Node.slcp** - Component selection (edit in Simplicity Studio)
- **config/zcl/zcl_config.zap** - ZCL cluster configuration (edit in ZAP tool)
- **app/app_config.h** - Application constants (PAN ID, channel, thresholds)

---

## Notes

- All components managed through Simplicity Studio GUI
- Changes to `.slcp` trigger autogeneration in `autogen/` folder
- Never manually edit `autogen/` or `gecko_sdk_4.5.0/` files
- To add/remove components: Open `.slcp` → SOFTWARE COMPONENTS tab
