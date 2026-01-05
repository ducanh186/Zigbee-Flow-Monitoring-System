#include "lcd_ui.h"

#include <string.h>
#include <stdio.h>

#include "glib.h"
#include "dmd.h"
#include "em_gpio.h"
#include "app/framework/include/af.h"

// LCD is 128x128 pixels
#define LCD_WIDTH   128
#define LCD_HEIGHT  128

static GLIB_Context_t s_glib;
static bool s_ready = false;

// ===== UI STATE MACHINE =====
typedef struct {
  bool dirty;
  uint16_t flow;
  uint8_t batt;
  bool valve_on;
  bool have_flow;
  bool have_batt;
  bool have_valve;
} lcd_ui_state_t;

static lcd_ui_state_t s_ui = {0};

// helper: update LCD panel
static void flush_now(void)
{
  DMD_updateDisplay();
}

// helper: draw centered string at Y position
static void drawCentered(int32_t y, const char *s)
{
  if (s == NULL || s[0] == '\0') return;
  
  // Font is 6px wide per char
  int len = strlen(s);
  int textWidth = len * 6;
  int x = (LCD_WIDTH - textWidth) / 2;
  if (x < 0) x = 0;
  
  GLIB_drawString(&s_glib, s, len, x, y, false);
}

// helper: clear a rectangular area with white
static void clearArea(int32_t x0, int32_t y0, int32_t x1, int32_t y1)
{
  GLIB_Rectangle_t rect = {x0, y0, x1, y1};
  uint32_t savedFg = s_glib.foregroundColor;
  s_glib.foregroundColor = White;
  GLIB_drawRectFilled(&s_glib, &rect);
  s_glib.foregroundColor = savedFg;
}

// helper: draw a data row inside the frame (label: value)
static void drawDataRow(int32_t y, const char *label, const char *value)
{
  // Clear the row area (inside frame: x=6 to x=121)
  clearArea(6, y, 121, y + 11);
  
  // Draw label at x=10
  GLIB_drawString(&s_glib, label, strlen(label), 10, y + 2, false);
  
  // Draw value right-aligned at x=70
  int valLen = strlen(value);
  int valX = 118 - (valLen * 6);  // Right align
  if (valX < 70) valX = 70;
  GLIB_drawString(&s_glib, value, valLen, valX, y + 2, false);
}

// Draw the static frame (called once at init)
static void drawFrame(void)
{
  // Outer border
  GLIB_Rectangle_t outer = {0, 0, 127, 127};
  GLIB_drawRect(&s_glib, &outer);
  
  // Inner border (double line effect)
  GLIB_Rectangle_t inner = {2, 2, 125, 125};
  GLIB_drawRect(&s_glib, &inner);
  
  // Title bar background (inverted)
  GLIB_Rectangle_t titleBar = {3, 3, 124, 18};
  GLIB_drawRectFilled(&s_glib, &titleBar);
  
  // Title text (white on black)
  s_glib.foregroundColor = White;
  drawCentered(6, "COORDINATOR");
  s_glib.foregroundColor = Black;
  
  // Separator line below title
  GLIB_drawLineH(&s_glib, 3, 20, 124);
  
  // Data area separator lines
  GLIB_drawLineH(&s_glib, 5, 50, 122);   // Below FLOW
  GLIB_drawLineH(&s_glib, 5, 75, 122);   // Below BATT
  GLIB_drawLineH(&s_glib, 5, 100, 122);  // Below VALVE
  
  // Footer bar
  GLIB_drawLineH(&s_glib, 3, 110, 124);
}

bool lcdUiInit(void)
{
  emberAfCorePrintln("LCD: lcdUiInit() s_ready=%d", s_ready);
  
  if (s_ready) {
    emberAfCorePrintln("LCD: already inited");
    return true;
  }

  // CRITICAL: Enable display power via GPIO PD15
  GPIO_PinModeSet(gpioPortD, 15, gpioModePushPull, 1);
  emberAfCorePrintln("LCD: GPIO PD15 enabled");

  // Init DMD
  EMSTATUS dmdStatus = DMD_init(0);
  emberAfCorePrintln("LCD: DMD_init()=0x%X", dmdStatus);
  if (dmdStatus != DMD_OK) {
    emberAfCorePrintln("LCD: DMD FAIL!");
    s_ready = false;
    return false;
  }

  // Init GLIB
  EMSTATUS glibStatus = GLIB_contextInit(&s_glib);
  emberAfCorePrintln("LCD: GLIB_contextInit()=0x%X", glibStatus);
  if (glibStatus != GLIB_OK) {
    emberAfCorePrintln("LCD: GLIB FAIL!");
    s_ready = false;
    return false;
  }

  s_glib.backgroundColor = White;
  s_glib.foregroundColor = Black;
  GLIB_setFont(&s_glib, (GLIB_Font_t *)&GLIB_FontNarrow6x8);
  
  // Clear entire display
  GLIB_clear(&s_glib);
  
  // Draw static frame
  drawFrame();
  
  // Draw initial data
  drawDataRow(26, "FLOW:", "---");
  drawDataRow(51, "BATT:", "---");
  drawDataRow(76, "VALVE:", "---");
  
  // Footer: Network status
  clearArea(4, 112, 123, 123);
  drawCentered(114, "NET: STARTING");
  
  flush_now();
  
  s_ready = true;
  s_ui.dirty = false;  // Already drawn
  emberAfCorePrintln("LCD: init OK");
  return true;
}

bool lcdUiIsReady(void)
{
  return s_ready;
}

void lcdUiPrintLine(uint8_t line, const char *text)
{
  if (!s_ready) return;
  // Legacy function - draw at specific Y
  int32_t y = 26 + line * 25;
  if (y > 100) y = 100;
  clearArea(6, y, 121, y + 11);
  GLIB_drawString(&s_glib, text, strlen(text), 10, y + 2, false);
  flush_now();
}

void lcdUiOverlayTag(const char *tag)
{
  if (!s_ready) return;
  char buf[20];
  if (tag == NULL || tag[0] == '\0') {
    snprintf(buf, sizeof(buf), "TAG: ---");
  } else {
    snprintf(buf, sizeof(buf), "TAG: %s", tag);
  }
  clearArea(4, 112, 123, 123);
  drawCentered(114, buf);
  flush_now();
}

// ===== REALTIME DATA UPDATE =====
void lcd_ui_set_flow(uint16_t flow)
{
  emberAfCorePrintln("LCD: set_flow(%u) ready=%d", flow, s_ready);
  if (s_ui.flow != flow || !s_ui.have_flow) {
    s_ui.flow = flow;
    s_ui.have_flow = true;
    s_ui.dirty = true;
  }
}

void lcd_ui_set_battery(uint8_t percent)
{
  if (percent > 100) percent = 100;
  if (s_ui.batt != percent || !s_ui.have_batt) {
    s_ui.batt = percent;
    s_ui.have_batt = true;
    s_ui.dirty = true;
  }
}

void lcd_ui_set_valve(bool on)
{
  if (s_ui.valve_on != on || !s_ui.have_valve) {
    s_ui.valve_on = on;
    s_ui.have_valve = true;
    s_ui.dirty = true;
  }
}

// ===== RENDERING =====
void lcd_ui_process(void)
{
  if (!s_ready) return;
  if (!s_ui.dirty) return;
  
  emberAfCorePrintln("LCD: RENDER flow=%u batt=%u valve=%d", 
                     s_ui.flow, s_ui.batt, s_ui.valve_on);

  char buf[16];

  // FLOW row (y=26)
  if (s_ui.have_flow) {
    snprintf(buf, sizeof(buf), "%u L/m", s_ui.flow);
  } else {
    snprintf(buf, sizeof(buf), "---");
  }
  drawDataRow(26, "FLOW:", buf);

  // BATT row (y=51)
  if (s_ui.have_batt) {
    snprintf(buf, sizeof(buf), "%u %%", s_ui.batt);
  } else {
    snprintf(buf, sizeof(buf), "---");
  }
  drawDataRow(51, "BATT:", buf);

  // VALVE row (y=76)
  if (s_ui.have_valve) {
    snprintf(buf, sizeof(buf), "%s", s_ui.valve_on ? "OPEN" : "CLOSED");
  } else {
    snprintf(buf, sizeof(buf), "---");
  }
  drawDataRow(76, "VALVE:", buf);

  flush_now();
  s_ui.dirty = false;
}

// Update network status in footer
void lcd_ui_set_network(const char *status)
{
  if (!s_ready) return;
  clearArea(4, 112, 123, 123);
  drawCentered(114, status);
  flush_now();
}
