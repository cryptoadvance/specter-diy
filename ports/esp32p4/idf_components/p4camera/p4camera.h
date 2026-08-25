/**
 * @file p4camera.h
 * @brief MIPI-CSI camera capture for the Waveshare ESP32-P4 4.3-C.
 */

#ifndef P4CAMERA_H
#define P4CAMERA_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "esp_err.h"

/** Sensor detectado no barramento SCCB. */
typedef enum {
    P4CAM_SENSOR_NONE = 0,
    P4CAM_SENSOR_OV5647,
    P4CAM_SENSOR_SC2336,
} p4camera_sensor_t;

/**
 * @brief Inicializa a camera em tons de cinza.
 *
 * Reusa o barramento I2C do p4board -- nesta placa o SCCB da camera e o touch
 * compartilham GPIO 8/7, e abrir um segundo master bus nos mesmos pinos falha.
 * Exige que p4board_touch_init() tenha rodado antes.
 */
esp_err_t p4camera_init(void);
void p4camera_deinit(void);

p4camera_sensor_t p4camera_sensor(void);
const char *p4camera_sensor_name(void);
void p4camera_size(uint16_t *width, uint16_t *height);

/** Etapa em que a ultima inicializacao parou -- diagnostico via Python. */
const char *p4camera_init_stage(void);

/** FourCC do formato de pixel escolhido. */
uint32_t p4camera_format(void);

/**
 * @brief Captura um quadro.
 *
 * Devolve ponteiro para o buffer mapeado do driver, valido ate a proxima
 * chamada de p4camera_capture() ou p4camera_release(). Nao copia.
 */
esp_err_t p4camera_capture(uint8_t **data, size_t *length);

/** Devolve o buffer ao driver. Obrigatorio depois de cada capture(). */
esp_err_t p4camera_release(void);

#endif  // P4CAMERA_H
