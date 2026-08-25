/**
 * @file board_config.h
 * @brief Waveshare ESP32-P4-WIFI6-Touch-LCD-4.3-C pin and panel constants.
 *
 * Consolidated from two independent implementations of this board:
 *
 *   - miketlk/specter-bootloader @ port_esp32-p4, lcd-4p3/board_config.h
 *   - odudex/Kern, components/wave_43/include/bsp/esp32_p4_wifi6_touch_lcd_43.h
 *
 * Both agree on every panel timing, on the DSI parameters and on the I2C,
 * reset and backlight pins. They diverge on the touch reset line and on SD
 * card support; see reports/touch-reset-gpio-divergence.md and
 * reports/kern-wave43-no-sdcard.md for the evidence behind the choices here.
 */

#ifndef P4BOARD_BOARD_CONFIG_H
#define P4BOARD_BOARD_CONFIG_H

#include "driver/gpio.h"

#define P4BOARD_NAME "ESP32-P4-WIFI6-Touch-LCD-4.3-C"

/* Panel: ST7701 over MIPI DSI. Both sources agree on all of these. */
#define P4BOARD_LCD_WIDTH                 480U
#define P4BOARD_LCD_HEIGHT                800U
#define P4BOARD_LCD_DPI_CLOCK_MHZ         30U
#define P4BOARD_LCD_DSI_LANES             2U
#define P4BOARD_LCD_DSI_LANE_BITRATE_MBPS 500U
#define P4BOARD_LCD_DSI_LDO_CHANNEL       3
#define P4BOARD_LCD_DSI_LDO_MV            2500

#define P4BOARD_LCD_HSYNC_BACK_PORCH   42U
#define P4BOARD_LCD_HSYNC_PULSE_WIDTH  12U
#define P4BOARD_LCD_HSYNC_FRONT_PORCH  42U
#define P4BOARD_LCD_VSYNC_BACK_PORCH    2U
#define P4BOARD_LCD_VSYNC_PULSE_WIDTH   8U
#define P4BOARD_LCD_VSYNC_FRONT_PORCH  60U

#define P4BOARD_LCD_RESET_GPIO         GPIO_NUM_27
#define P4BOARD_LCD_RESET_ACTIVE_HIGH  false
#define P4BOARD_LCD_BACKLIGHT_GPIO     GPIO_NUM_26
#define P4BOARD_LCD_BACKLIGHT_INVERTED true

/* Touch: GT911 on I2C port 1, shared with the camera on this board. */
#define P4BOARD_TOUCH_I2C_PORT          1
#define P4BOARD_TOUCH_I2C_SCL_GPIO      GPIO_NUM_8
#define P4BOARD_TOUCH_I2C_SDA_GPIO      GPIO_NUM_7
#define P4BOARD_TOUCH_I2C_FREQUENCY_HZ  400000U
#define P4BOARD_TOUCH_GT911_ADDRESS     0x5du
#define P4BOARD_TOUCH_GT911_BACKUP_ADDR 0x14u
#define P4BOARD_TOUCH_MAX_POINTS        5U
#define P4BOARD_TOUCH_POINT_BYTES       8U

/*
 * Touch reset. The two sources disagree: miketlk drives GPIO 23, Kern leaves
 * it unconnected and probes both I2C addresses instead. We do both -- drive
 * the reset so the address is deterministic, and keep the dual-address probe
 * as a fallback. The combination is strictly more robust than either alone,
 * and costs one GPIO configuration.
 */
#define P4BOARD_TOUCH_RESET_GPIO GPIO_NUM_23
#define P4BOARD_TOUCH_HAS_RESET  1

/*
 * ESP32-C6 radio co-processor CHIP_EN, active high with an external pull-up.
 * Only Kern documents this pin. Driving it low holds the radio in reset, which
 * matters for an air-gapped signer: this board has no radio in the P4 itself,
 * but the companion chip does.
 */
#define P4BOARD_C6_WIFI_EN_GPIO GPIO_NUM_54

/*
 * SDMMC. Only miketlk maps these; Kern declares BSP_CAPS_SDCARD 0 for this
 * board. The slot answers on these pins -- verified on hardware by probing
 * with no card inserted, which reached send_op_cond and timed out as expected.
 * Not yet exercised with a card present.
 */
#define P4BOARD_SDMMC_D0_GPIO  GPIO_NUM_39
#define P4BOARD_SDMMC_D1_GPIO  GPIO_NUM_40
#define P4BOARD_SDMMC_D2_GPIO  GPIO_NUM_41
#define P4BOARD_SDMMC_D3_GPIO  GPIO_NUM_42
#define P4BOARD_SDMMC_CLK_GPIO GPIO_NUM_43
#define P4BOARD_SDMMC_CMD_GPIO GPIO_NUM_44

#endif  // P4BOARD_BOARD_CONFIG_H
