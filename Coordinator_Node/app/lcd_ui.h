#pragma once

#include <stdint.h>
#include <stdbool.h>

// ===== INIT & LOW-LEVEL API =====
// Init LCD + GLIB. Draws frame with title "COORDINATOR"
bool lcdUiInit(void);

// Legacy: Draw text at specific line (deprecated, use set_* functions)
void lcdUiPrintLine(uint8_t line, const char *text);

// Check if LCD is ready
bool lcdUiIsReady(void);

// Show tag overlay in footer area
void lcdUiOverlayTag(const char *tag);

// ===== REALTIME DATA API =====
// Update data from Zigbee callbacks (non-blocking, sets dirty flag)
void lcd_ui_set_flow(uint16_t flow);
void lcd_ui_set_battery(uint8_t percent);
void lcd_ui_set_valve(bool on);  // on=true -> OPEN, false -> CLOSED

// Update network status in footer
void lcd_ui_set_network(const char *status);

// Call from main loop / tick to render when dirty
void lcd_ui_process(void);
