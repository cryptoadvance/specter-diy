/**
 * @file p4board.h
 * @brief Board support surface exposed to the MicroPython module.
 */

#ifndef P4BOARD_H
#define P4BOARD_H

#include <stdbool.h>
#include <stdint.h>

#include "esp_err.h"

/* Display */
esp_err_t p4board_display_init(void);
void p4board_display_deinit(void);
esp_err_t p4board_backlight(uint32_t percent);
esp_err_t p4board_display_enabled(bool enabled);
uint16_t *p4board_framebuffer(void);
esp_err_t p4board_flush(uint16_t y, uint16_t height);

/* Touch */
typedef struct {
    uint16_t x;
    uint16_t y;
    uint16_t size;
    uint8_t id;
} p4board_touch_point_t;

esp_err_t p4board_touch_init(void);
void p4board_touch_deinit(void);
esp_err_t p4board_touch_read(p4board_touch_point_t *points, uint8_t capacity,
    uint8_t *count);
uint8_t p4board_touch_address(void);

/* Radio co-processor */
esp_err_t p4board_radio_off(void);

#endif  // P4BOARD_H
