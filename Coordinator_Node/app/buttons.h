#ifndef BUTTONS_H
#define BUTTONS_H

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Process pending button actions (called from main loop)
 * 
 * Button ISR sets flags, this function processes them safely
 * in main context where Zigbee stack calls are allowed.
 * 
 * Button actions:
 * - PB0 short press: Form network
 * - PB0 long press (>=1.5s): Toggle UART gateway
 * - PB1 press: Open network for joining (180s window)
 */
void buttonsTick(void);

#ifdef __cplusplus
}
#endif

#endif // BUTTONS_H
