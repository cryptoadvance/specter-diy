/**
 * @file radio.c
 * @brief Hold the ESP32-C6 companion radio in reset.
 *
 * The pin and the technique come from odudex/Kern,
 * components/wave_43/wave_43.c. The ESP32-P4 has no radio of its own, but this
 * board carries an ESP32-C6 whose CHIP_EN is active high with an external
 * pull-up, so it powers up enabled. For an air-gapped signer that is the wrong
 * default.
 *
 * Latching the pad keeps CHIP_EN low across soft resets and watchdog resets;
 * only a power-on reset releases it.
 */

#include "board_config.h"
#include "esp_log.h"
#include "esp_sleep.h"
#include "p4board.h"

static const char *TAG = "p4board-radio";

esp_err_t p4board_radio_off(void) {
    gpio_config_t config = {
        .pin_bit_mask = 1ULL << P4BOARD_C6_WIFI_EN_GPIO,
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_ENABLE,
    };
    esp_err_t result = gpio_config(&config);
    if (result != ESP_OK) {
        return result;
    }
    result = gpio_set_level(P4BOARD_C6_WIFI_EN_GPIO, 0);
    if (result != ESP_OK) {
        return result;
    }
    /* Hold the pad through soft and watchdog resets. */
    result = gpio_hold_en(P4BOARD_C6_WIFI_EN_GPIO);
    if (result == ESP_OK) {
        ESP_LOGI(TAG, "ESP32-C6 held in reset on GPIO %d", P4BOARD_C6_WIFI_EN_GPIO);
    }
    return result;
}
