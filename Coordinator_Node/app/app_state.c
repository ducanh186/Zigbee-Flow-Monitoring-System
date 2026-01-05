#include "app_state.h"
#include "lcd_ui.h"
#include <string.h>

AppState g_state;

uint16_t   g_flow = 0;
uint8_t    g_batteryPercent = 0;

app_mode_t g_mode = MODE_MANUAL;
void appStateInit(void)
{
  memset(&g_state, 0, sizeof(g_state));
  strcpy(g_state.valveStr, "closed");
  g_state.battery = 100;
  g_state.joined = false;
  g_state.flow = 0;
}


void appStateSetFlow(uint16_t flow)
{
  if (g_state.flow != flow) {
    g_state.flow = flow;
    appStateNotifyChanged();
  }
}

void appStateSetBattery(uint8_t battery)
{
  if (g_state.battery != battery) {
    g_state.battery = battery;
    appStateNotifyChanged();
  }
}


void appStateSetValveStr(const char *s)
{
  if (!s) return;
  if (strncmp(g_state.valveStr, s, sizeof(g_state.valveStr)) != 0) {
    strncpy(g_state.valveStr, s, sizeof(g_state.valveStr) - 1);
    g_state.valveStr[sizeof(g_state.valveStr) - 1] = '\0';
    appStateNotifyChanged();
  }
}

void appStateSetJoined(bool joined)
{
  if (g_state.joined != joined) {
    g_state.joined = joined;
    appStateNotifyChanged();
  }
}
bool       g_uartGatewayEnabled = true;
void appStateNotifyChanged(void)
{
  //lcdUiShowData(g_state.flow, g_state.valveStr, g_state.battery, g_state.joined);
}
