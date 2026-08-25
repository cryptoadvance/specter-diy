/**
 * @file touch.c
 * @brief GT911 capacitive touch over raw I2C register access.
 *
 * Adapted from miketlk/specter-bootloader @ port_esp32-p4,
 * platforms/esp32-p4-wifi6-touch-lcd/common/touch_hal.c and touch_decode.c.
 *
 * Like the original this talks to the GT911 registers directly rather than
 * pulling the managed esp_lcd_touch_gt911 component, which keeps the build
 * free of the component registry and working on ESP-IDF 5.5.x.
 *
 * One deliberate difference: we drive the reset line (GPIO 23, from miketlk)
 * *and* probe both I2C addresses (from Kern). The GT911 latches its address
 * from the INT level during reset, so driving reset makes the address
 * deterministic; the probe then costs nothing and covers the case where our
 * reading of the schematic is wrong. See
 * reports/touch-reset-gpio-divergence.md.
 */

#include <stddef.h>
#include <string.h>

#include "board_config.h"
#include "driver/i2c_master.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "p4board.h"

#define GT911_PRODUCT_ID_REGISTER 0x8140U
#define GT911_STATUS_REGISTER     0x814eU
#define GT911_POINT_REGISTER      0x814fU

static const char *TAG = "p4board-touch";
static i2c_master_bus_handle_t bus;
static i2c_master_dev_handle_t device;
static uint8_t device_address;

static bool read_register(uint16_t address, void *data, size_t size) {
    uint8_t request[2] = { (uint8_t)(address >> 8), (uint8_t)address };
    return device && i2c_master_transmit_receive(device, request,
        sizeof(request), data, size, 100) == ESP_OK;
}

static bool write_register(uint16_t address, uint8_t value) {
    uint8_t request[3] = { (uint8_t)(address >> 8), (uint8_t)address, value };
    return device && i2c_master_transmit(device, request, sizeof(request), 100) == ESP_OK;
}

#if P4BOARD_TOUCH_HAS_RESET
static void pulse_reset(void) {
    gpio_config_t reset_config = {
        .pin_bit_mask = 1ULL << P4BOARD_TOUCH_RESET_GPIO,
        .mode = GPIO_MODE_OUTPUT,
    };
    if (gpio_config(&reset_config) != ESP_OK) {
        return;
    }
    /* Active-low reset: hold, release, then let the controller settle before
     * the first transaction. The GT911 datasheet asks for >=10 ms after the
     * rising edge before I2C is valid. */
    gpio_set_level(P4BOARD_TOUCH_RESET_GPIO, 0);
    vTaskDelay(pdMS_TO_TICKS(10));
    gpio_set_level(P4BOARD_TOUCH_RESET_GPIO, 1);
    vTaskDelay(pdMS_TO_TICKS(50));
}
#endif

esp_err_t p4board_touch_init(void) {
    if (device) {
        return ESP_OK;
    }
#if P4BOARD_TOUCH_HAS_RESET
    pulse_reset();
#endif
    i2c_master_bus_config_t bus_config = {
        .i2c_port = P4BOARD_TOUCH_I2C_PORT,
        .scl_io_num = P4BOARD_TOUCH_I2C_SCL_GPIO,
        .sda_io_num = P4BOARD_TOUCH_I2C_SDA_GPIO,
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .glitch_ignore_cnt = 7,
        .flags.enable_internal_pullup = true,
    };
    esp_err_t result = i2c_new_master_bus(&bus_config, &bus);
    if (result != ESP_OK) {
        return result;
    }

    const uint8_t addresses[] = {
        P4BOARD_TOUCH_GT911_ADDRESS,
        P4BOARD_TOUCH_GT911_BACKUP_ADDR,
    };
    bool selected = false;
    for (size_t index = 0; index < sizeof(addresses) && !selected; ++index) {
        if (i2c_master_probe(bus, addresses[index], 100) == ESP_OK) {
            device_address = addresses[index];
            selected = true;
        }
    }
    if (!selected) {
        ESP_LOGE(TAG, "GT911 not found at 0x%02x or 0x%02x",
            P4BOARD_TOUCH_GT911_ADDRESS, P4BOARD_TOUCH_GT911_BACKUP_ADDR);
        p4board_touch_deinit();
        return ESP_ERR_NOT_FOUND;
    }

    i2c_device_config_t device_config = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = device_address,
        .scl_speed_hz = P4BOARD_TOUCH_I2C_FREQUENCY_HZ,
    };
    result = i2c_master_bus_add_device(bus, &device_config, &device);
    if (result != ESP_OK) {
        p4board_touch_deinit();
        return result;
    }

    char product_id[5] = { 0 };
    if (!read_register(GT911_PRODUCT_ID_REGISTER, product_id, 4)) {
        ESP_LOGE(TAG, "GT911 product id read failed");
        p4board_touch_deinit();
        return ESP_ERR_INVALID_RESPONSE;
    }
    ESP_LOGI(TAG, "GT911 product=%s address=0x%02x", product_id, device_address);
    return ESP_OK;
}

void p4board_touch_deinit(void) {
    if (device) {
        i2c_master_bus_rm_device(device);
        device = NULL;
    }
    if (bus) {
        i2c_del_master_bus(bus);
        bus = NULL;
    }
    device_address = 0;
}

uint8_t p4board_touch_address(void) {
    return device_address;
}

void *p4board_i2c_bus(void) {
    /* Devolvido como void* para nao obrigar quem chama a incluir o header do
     * driver I2C so para repassar o handle adiante. */
    return bus;
}

esp_err_t p4board_touch_read(p4board_touch_point_t *points, uint8_t capacity,
    uint8_t *count) {
    if (!count || (capacity && !points)) {
        return ESP_ERR_INVALID_ARG;
    }
    *count = 0;
    if (!device) {
        return ESP_ERR_INVALID_STATE;
    }

    uint8_t status = 0;
    if (!read_register(GT911_STATUS_REGISTER, &status, sizeof(status))) {
        return ESP_ERR_INVALID_RESPONSE;
    }
    /* Bit 7 is the "coordinates ready" flag; the low nibble is the point
     * count. Nothing to do until the controller raises it. */
    if (!(status & 0x80U)) {
        return ESP_OK;
    }
    uint8_t available = status & 0x0fU;
    if (available > P4BOARD_TOUCH_MAX_POINTS) {
        /* Corrupt count: clear the flag so the controller re-arms instead of
         * latching a bad frame forever. */
        write_register(GT911_STATUS_REGISTER, 0);
        return ESP_ERR_INVALID_RESPONSE;
    }

    esp_err_t result = ESP_OK;
    if (available) {
        uint8_t raw[P4BOARD_TOUCH_MAX_POINTS * P4BOARD_TOUCH_POINT_BYTES];
        size_t length = (size_t)available * P4BOARD_TOUCH_POINT_BYTES;
        if (!read_register(GT911_POINT_REGISTER, raw, length)) {
            result = ESP_ERR_INVALID_RESPONSE;
        } else {
            uint8_t returned = available < capacity ? available : capacity;
            for (uint8_t index = 0; index < returned; ++index) {
                const uint8_t *p = raw + (size_t)index * P4BOARD_TOUCH_POINT_BYTES;
                uint16_t x = (uint16_t)(p[1] | ((uint16_t)p[2] << 8));
                uint16_t y = (uint16_t)(p[3] | ((uint16_t)p[4] << 8));
                if (x >= P4BOARD_LCD_WIDTH || y >= P4BOARD_LCD_HEIGHT) {
                    result = ESP_ERR_INVALID_RESPONSE;
                    break;
                }
                points[index].x = x;
                points[index].y = y;
                points[index].size = (uint16_t)(p[5] | ((uint16_t)p[6] << 8));
                points[index].id = p[0] & 0x0fU;
                *count = index + 1;
            }
        }
    }

    /* The status flag must be cleared for the controller to report the next
     * frame, whether or not we could decode this one. */
    write_register(GT911_STATUS_REGISTER, 0);
    if (result != ESP_OK) {
        *count = 0;
    }
    return result;
}
