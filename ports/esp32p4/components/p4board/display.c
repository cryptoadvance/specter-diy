/*
 * SPDX-FileCopyrightText: 2024 Espressif Systems (Shanghai) CO LTD
 * SPDX-FileCopyrightText: 2026 Specter contributors
 * SPDX-License-Identifier: Apache-2.0
 *
 * ST7701 MIPI DSI panel and backlight for the Waveshare 4.3-C board.
 *
 * Adapted from miketlk/specter-bootloader @ port_esp32-p4,
 * platforms/esp32-p4-wifi6-touch-lcd/lcd-4p3/board_display.c, which in turn
 * adapts Waveshare's Apache-2.0 ESP32-P4-WIFI6-Touch-LCD-4.3 example. The
 * controller command sequence below is copied verbatim from that source: it is
 * validated on this exact panel, and the values are opaque magic numbers where
 * a transcription slip is silent and fatal.
 *
 * Changes from the original: the Specter bootloader HAL entry points are
 * replaced by the p4board_* surface consumed by the MicroPython module, and
 * the SPECTER_* configuration macros are renamed P4BOARD_*. The deliberate
 * property of the original is preserved -- no managed esp_lcd_st7701 component
 * is required, so this builds on ESP-IDF 5.5.x without the component registry.
 */

#include <inttypes.h>
#include <stddef.h>
#include <stdint.h>

#include "board_config.h"
#include "driver/ledc.h"
#include "esp_lcd_mipi_dsi.h"
#include "esp_lcd_panel_io.h"
#include "esp_lcd_panel_ops.h"
#include "esp_ldo_regulator.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "p4board.h"

#define ARRAY_SIZE(values) (sizeof(values) / sizeof((values)[0]))
#define BACKLIGHT_DUTY_MAX 1023U

typedef struct st7701_init_command {
  uint8_t command;
  uint8_t data[16];
  uint8_t data_size;
  uint16_t delay_ms;
} st7701_init_command_t;

static const st7701_init_command_t st7701_init_commands[] = {
    {0xff, {0x77, 0x01, 0x00, 0x00, 0x13}, 5, 0},
    {0xef, {0x08}, 1, 0},
    {0xff, {0x77, 0x01, 0x00, 0x00, 0x10}, 5, 0},
    {0xc0, {0x63, 0x00}, 2, 0},
    {0xc1, {0x0d, 0x02}, 2, 0},
    {0xc2, {0x17, 0x08}, 2, 0},
    {0xcc, {0x10}, 1, 0},
    {0xb0,
     {0x40, 0xc9, 0x94, 0x0e, 0x10, 0x05, 0x0b, 0x09, 0x08, 0x26, 0x04, 0x52,
      0x10, 0x69, 0x6b, 0x69},
     16,
     0},
    {0xb1,
     {0x40, 0xd2, 0x98, 0x0c, 0x92, 0x07, 0x09, 0x08, 0x07, 0x25, 0x02, 0x0e,
      0x0c, 0x6e, 0x78, 0x55},
     16,
     0},
    {0xff, {0x77, 0x01, 0x00, 0x00, 0x11}, 5, 0},
    {0xb0, {0x5d}, 1, 0},
    {0xb1, {0x4e}, 1, 0},
    {0xb2, {0x87}, 1, 0},
    {0xb3, {0x80}, 1, 0},
    {0xb5, {0x4e}, 1, 0},
    {0xb7, {0x85}, 1, 0},
    {0xb8, {0x21}, 1, 0},
    {0xb9, {0x10, 0x1f}, 2, 0},
    {0xbb, {0x03}, 1, 0},
    {0xbc, {0x00}, 1, 0},
    {0xc1, {0x78}, 1, 0},
    {0xc2, {0x78}, 1, 0},
    {0xd0, {0x88}, 1, 0},
    {0xe0, {0x00, 0x3a, 0x02}, 3, 0},
    {0xe1,
     {0x04, 0xa0, 0x00, 0xa0, 0x05, 0xa0, 0x00, 0xa0, 0x00, 0x40, 0x40},
     11,
     0},
    {0xe2,
     {0x30, 0x00, 0x40, 0x40, 0x32, 0xa0, 0x00, 0xa0, 0x00, 0xa0, 0x00, 0xa0,
      0x00},
     13,
     0},
    {0xe3, {0x00, 0x00, 0x33, 0x33}, 4, 0},
    {0xe4, {0x44, 0x44}, 2, 0},
    {0xe5,
     {0x09, 0x2e, 0xa0, 0xa0, 0x0b, 0x30, 0xa0, 0xa0, 0x05, 0x2a, 0xa0, 0xa0,
      0x07, 0x2c, 0xa0, 0xa0},
     16,
     0},
    {0xe6, {0x00, 0x00, 0x33, 0x33}, 4, 0},
    {0xe7, {0x44, 0x44}, 2, 0},
    {0xe8,
     {0x08, 0x2d, 0xa0, 0xa0, 0x0a, 0x2f, 0xa0, 0xa0, 0x04, 0x29, 0xa0, 0xa0,
      0x06, 0x2b, 0xa0, 0xa0},
     16,
     0},
    {0xeb, {0x00, 0x00, 0x4e, 0x4e, 0x00, 0x00, 0x00}, 7, 0},
    {0xec, {0x08, 0x01}, 2, 0},
    {0xed,
     {0xb0, 0x2b, 0x98, 0xa4, 0x56, 0x7f, 0xff, 0xff, 0xff, 0xff, 0xf7, 0x65,
      0x4a, 0x89, 0xb2, 0x0b},
     16,
     0},
    {0xef, {0x08, 0x08, 0x08, 0x45, 0x3f, 0x54}, 6, 0},
    {0xff, {0x77, 0x01, 0x00, 0x00, 0x00}, 5, 0},
    {0x3a, {0x55}, 1, 0},
    {0x11, {0}, 0, 120},
    {0x29, {0}, 0, 0},
};

static const char *TAG = "p4board-display";
static esp_ldo_channel_handle_t dsi_ldo;
static esp_lcd_dsi_bus_handle_t dsi_bus;
static esp_lcd_panel_io_handle_t panel_io;
static esp_lcd_panel_handle_t dpi_panel;
static uint16_t *lcd_framebuffer;
static bool backlight_timer_initialized;
static bool backlight_channel_initialized;

esp_err_t p4board_backlight(uint32_t percent) {
    if (percent > 100U) {
        return ESP_ERR_INVALID_ARG;
    }
    uint32_t duty = (BACKLIGHT_DUTY_MAX * percent) / 100U;
    esp_err_t result = ledc_set_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0, duty);
    if (result == ESP_OK) {
        result = ledc_update_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0);
    }
    return result;
}

static esp_err_t init_backlight(void) {
    ledc_timer_config_t timer_config = {
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .duty_resolution = LEDC_TIMER_10_BIT,
        .timer_num = LEDC_TIMER_1,
        .freq_hz = 5000,
        .clk_cfg = LEDC_AUTO_CLK,
    };
    esp_err_t result = ledc_timer_config(&timer_config);
    if (result != ESP_OK) {
        return result;
    }
    backlight_timer_initialized = true;
    ledc_channel_config_t channel_config = {
        .gpio_num = P4BOARD_LCD_BACKLIGHT_GPIO,
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .channel = LEDC_CHANNEL_0,
        .intr_type = LEDC_INTR_DISABLE,
        .timer_sel = LEDC_TIMER_1,
        .duty = 0,
        .hpoint = 0,
        .flags.output_invert = P4BOARD_LCD_BACKLIGHT_INVERTED,
    };
    result = ledc_channel_config(&channel_config);
    backlight_channel_initialized = (result == ESP_OK);
    return result;
}

static esp_err_t reset_lcd(void) {
    gpio_config_t reset_config = {
        .pin_bit_mask = 1ULL << P4BOARD_LCD_RESET_GPIO,
        .mode = GPIO_MODE_OUTPUT,
    };
    esp_err_t result = gpio_config(&reset_config);
    if (result != ESP_OK) {
        return result;
    }
    int active = P4BOARD_LCD_RESET_ACTIVE_HIGH ? 1 : 0;
    /* Idle, assert, release -- 10 ms each, as in the validated original. */
    const int levels[] = { !active, active, !active };
    for (size_t i = 0; i < ARRAY_SIZE(levels); ++i) {
        result = gpio_set_level(P4BOARD_LCD_RESET_GPIO, levels[i]);
        if (result != ESP_OK) {
            return result;
        }
        vTaskDelay(pdMS_TO_TICKS(10));
    }
    return ESP_OK;
}

static esp_err_t send_st7701_init(void) {
    for (size_t index = 0; index < ARRAY_SIZE(st7701_init_commands); ++index) {
        const st7701_init_command_t *item = &st7701_init_commands[index];
        esp_err_t result = esp_lcd_panel_io_tx_param(panel_io, item->command,
            item->data_size ? item->data : NULL, item->data_size);
        if (result != ESP_OK) {
            return result;
        }
        if (item->delay_ms) {
            vTaskDelay(pdMS_TO_TICKS(item->delay_ms));
        }
    }
    return ESP_OK;
}

esp_err_t p4board_display_init(void) {
    if (dpi_panel) {
        return ESP_OK;
    }
    esp_err_t result = init_backlight();
    if (result == ESP_OK) {
        result = p4board_backlight(0);
    }
    if (result != ESP_OK) {
        goto fail;
    }

    esp_ldo_channel_config_t ldo_config = {
        .chan_id = P4BOARD_LCD_DSI_LDO_CHANNEL,
        .voltage_mv = P4BOARD_LCD_DSI_LDO_MV,
    };
    if ((result = esp_ldo_acquire_channel(&ldo_config, &dsi_ldo)) != ESP_OK) {
        goto fail;
    }

    esp_lcd_dsi_bus_config_t bus_config = {
        .bus_id = 0,
        .num_data_lanes = P4BOARD_LCD_DSI_LANES,
        .phy_clk_src = MIPI_DSI_PHY_CLK_SRC_DEFAULT,
        .lane_bit_rate_mbps = P4BOARD_LCD_DSI_LANE_BITRATE_MBPS,
    };
    if ((result = esp_lcd_new_dsi_bus(&bus_config, &dsi_bus)) != ESP_OK) {
        goto fail;
    }

    esp_lcd_dbi_io_config_t io_config = {
        .virtual_channel = 0,
        .lcd_cmd_bits = 8,
        .lcd_param_bits = 8,
    };
    if ((result = esp_lcd_new_panel_io_dbi(dsi_bus, &io_config, &panel_io)) != ESP_OK) {
        goto fail;
    }

    esp_lcd_dpi_panel_config_t panel_config = {
        .virtual_channel = 0,
        .dpi_clk_src = MIPI_DSI_DPI_CLK_SRC_DEFAULT,
        .dpi_clock_freq_mhz = P4BOARD_LCD_DPI_CLOCK_MHZ,
        .in_color_format = LCD_COLOR_FMT_RGB565,
        .num_fbs = 1,
        .video_timing = {
            .h_size = P4BOARD_LCD_WIDTH,
            .v_size = P4BOARD_LCD_HEIGHT,
            .hsync_back_porch = P4BOARD_LCD_HSYNC_BACK_PORCH,
            .hsync_pulse_width = P4BOARD_LCD_HSYNC_PULSE_WIDTH,
            .hsync_front_porch = P4BOARD_LCD_HSYNC_FRONT_PORCH,
            .vsync_back_porch = P4BOARD_LCD_VSYNC_BACK_PORCH,
            .vsync_pulse_width = P4BOARD_LCD_VSYNC_PULSE_WIDTH,
            .vsync_front_porch = P4BOARD_LCD_VSYNC_FRONT_PORCH,
        },
        .flags.use_dma2d = true,
    };
    if ((result = esp_lcd_new_panel_dpi(dsi_bus, &panel_config, &dpi_panel)) != ESP_OK) {
        goto fail;
    }

    if ((result = reset_lcd()) != ESP_OK ||
        (result = send_st7701_init()) != ESP_OK ||
        (result = esp_lcd_panel_init(dpi_panel)) != ESP_OK ||
        (result = esp_lcd_dpi_panel_get_frame_buffer(dpi_panel, 1,
            (void **)&lcd_framebuffer, (void **)NULL)) != ESP_OK) {
        goto fail;
    }

    ESP_LOGI(TAG, "ST7701 %ux%u active: DSI=%u lanes at %u Mbps, LDO=%d/%d mV",
        P4BOARD_LCD_WIDTH, P4BOARD_LCD_HEIGHT, P4BOARD_LCD_DSI_LANES,
        P4BOARD_LCD_DSI_LANE_BITRATE_MBPS, P4BOARD_LCD_DSI_LDO_CHANNEL,
        P4BOARD_LCD_DSI_LDO_MV);
    return ESP_OK;

fail:
    ESP_LOGE(TAG, "display init failed: %s", esp_err_to_name(result));
    p4board_display_deinit();
    return result;
}

void p4board_display_deinit(void) {
    if (backlight_channel_initialized) {
        p4board_backlight(0);
        ledc_stop(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0, 0);
        gpio_reset_pin(P4BOARD_LCD_BACKLIGHT_GPIO);
        backlight_channel_initialized = false;
    }
    if (backlight_timer_initialized) {
        ledc_timer_pause(LEDC_LOW_SPEED_MODE, LEDC_TIMER_1);
        ledc_timer_config_t timer_config = {
            .speed_mode = LEDC_LOW_SPEED_MODE,
            .timer_num = LEDC_TIMER_1,
            .deconfigure = true,
        };
        ledc_timer_config(&timer_config);
        backlight_timer_initialized = false;
    }
    if (dpi_panel) {
        esp_lcd_panel_del(dpi_panel);
        dpi_panel = NULL;
        lcd_framebuffer = NULL;
    }
    if (panel_io) {
        esp_lcd_panel_io_del(panel_io);
        panel_io = NULL;
    }
    if (dsi_bus) {
        esp_lcd_del_dsi_bus(dsi_bus);
        dsi_bus = NULL;
    }
    if (dsi_ldo) {
        esp_ldo_release_channel(dsi_ldo);
        dsi_ldo = NULL;
    }
    gpio_reset_pin(P4BOARD_LCD_RESET_GPIO);
}

uint16_t *p4board_framebuffer(void) {
    return lcd_framebuffer;
}

esp_err_t p4board_display_enabled(bool enabled) {
    if (!panel_io) {
        return ESP_ERR_INVALID_STATE;
    }
    /* 0x29 = display on, 0x28 = display off. */
    return esp_lcd_panel_io_tx_param(panel_io, enabled ? 0x29 : 0x28, NULL, 0);
}

esp_err_t p4board_flush(uint16_t y, uint16_t height) {
    if (!dpi_panel || !lcd_framebuffer) {
        return ESP_ERR_INVALID_STATE;
    }
    if (y >= P4BOARD_LCD_HEIGHT || height > P4BOARD_LCD_HEIGHT - y) {
        return ESP_ERR_INVALID_ARG;
    }
    return esp_lcd_panel_draw_bitmap(dpi_panel, 0, y, P4BOARD_LCD_WIDTH,
        y + height, lcd_framebuffer);
}
