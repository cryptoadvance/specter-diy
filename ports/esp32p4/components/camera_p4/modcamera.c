/**
 * @file modcamera.c
 * @brief Modulo `camera` do MicroPython: captura MIPI-CSI em tons de cinza.
 *
 * A superficie e deliberadamente pequena. O objetivo e alimentar um
 * decodificador de QR, nao ser uma API de camera.
 *
 * capture() devolve um memoryview apontando para o buffer mapeado do driver,
 * sem copia. So ha dois buffers na fila, entao release() e obrigatorio antes do
 * proximo capture() -- segurar dois quadros trava o streaming. capture() chama
 * release() sozinho se necessario, mas contar com isso desperdica um quadro.
 */

#include "p4camera.h"
#include "py/objarray.h"
#include "py/runtime.h"

static void check(esp_err_t err, const char *what) {
    if (err != ESP_OK) {
        mp_raise_msg_varg(&mp_type_OSError, MP_ERROR_TEXT("%s: %s"), what,
            esp_err_to_name(err));
    }
}

static mp_obj_t camera_init_fn(void) {
    check(p4camera_init(), "camera");
    return mp_obj_new_str(p4camera_sensor_name(), strlen(p4camera_sensor_name()));
}
static MP_DEFINE_CONST_FUN_OBJ_0(camera_init_obj, camera_init_fn);

static mp_obj_t camera_deinit_fn(void) {
    p4camera_deinit();
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(camera_deinit_obj, camera_deinit_fn);

static mp_obj_t camera_size_fn(void) {
    uint16_t width = 0, height = 0;
    p4camera_size(&width, &height);
    mp_obj_t items[2] = {
        MP_OBJ_NEW_SMALL_INT(width),
        MP_OBJ_NEW_SMALL_INT(height),
    };
    return mp_obj_new_tuple(2, items);
}
static MP_DEFINE_CONST_FUN_OBJ_0(camera_size_obj, camera_size_fn);

static mp_obj_t camera_stage_fn(void) {
    const char *stage = p4camera_init_stage();
    return mp_obj_new_str(stage, strlen(stage));
}
static MP_DEFINE_CONST_FUN_OBJ_0(camera_stage_obj, camera_stage_fn);

static mp_obj_t camera_format_fn(void) {
    uint32_t fourcc = p4camera_format();
    char text[5] = {
        (char)fourcc, (char)(fourcc >> 8), (char)(fourcc >> 16),
        (char)(fourcc >> 24), 0,
    };
    return mp_obj_new_str(text, 4);
}
static MP_DEFINE_CONST_FUN_OBJ_0(camera_format_obj, camera_format_fn);

static mp_obj_t camera_sensor_fn(void) {
    return mp_obj_new_str(p4camera_sensor_name(), strlen(p4camera_sensor_name()));
}
static MP_DEFINE_CONST_FUN_OBJ_0(camera_sensor_obj, camera_sensor_fn);

static mp_obj_t camera_capture_fn(void) {
    uint8_t *data = NULL;
    size_t length = 0;
    check(p4camera_capture(&data, &length), "capture");
    /* Somente leitura: o buffer pertence ao driver e volta para a fila. */
    return mp_obj_new_memoryview('B', length, data);
}
static MP_DEFINE_CONST_FUN_OBJ_0(camera_capture_obj, camera_capture_fn);

static mp_obj_t camera_release_fn(void) {
    check(p4camera_release(), "release");
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(camera_release_obj, camera_release_fn);

static mp_obj_t camera_scan_fn(void) {
    /* K_QUIRC_MAX_PAYLOAD e a capacidade maxima de um QR; alocar na pilha
     * evita mexer no heap do GC a cada quadro do laco de leitura. */
    static uint8_t payload[4096];
    size_t length = 0;
    esp_err_t err = p4camera_scan(payload, sizeof(payload), &length);
    if (err == ESP_ERR_NOT_FOUND) {
        /* Nenhum QR legivel neste quadro: caso normal, nao erro. */
        return mp_const_none;
    }
    check(err, "scan");
    return mp_obj_new_bytes(payload, length);
}
static MP_DEFINE_CONST_FUN_OBJ_0(camera_scan_obj, camera_scan_fn);

static mp_obj_t camera_gray_size_fn(void) {
    uint16_t width = 0, height = 0;
    p4camera_gray_size(&width, &height);
    mp_obj_t items[2] = {
        MP_OBJ_NEW_SMALL_INT(width),
        MP_OBJ_NEW_SMALL_INT(height),
    };
    return mp_obj_new_tuple(2, items);
}
static MP_DEFINE_CONST_FUN_OBJ_0(camera_gray_size_obj, camera_gray_size_fn);

static const mp_rom_map_elem_t camera_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_camera) },
    { MP_ROM_QSTR(MP_QSTR_init),     MP_ROM_PTR(&camera_init_obj) },
    { MP_ROM_QSTR(MP_QSTR_deinit),   MP_ROM_PTR(&camera_deinit_obj) },
    { MP_ROM_QSTR(MP_QSTR_size),     MP_ROM_PTR(&camera_size_obj) },
    { MP_ROM_QSTR(MP_QSTR_sensor),   MP_ROM_PTR(&camera_sensor_obj) },
    { MP_ROM_QSTR(MP_QSTR_stage),    MP_ROM_PTR(&camera_stage_obj) },
    { MP_ROM_QSTR(MP_QSTR_format),   MP_ROM_PTR(&camera_format_obj) },
    { MP_ROM_QSTR(MP_QSTR_capture),  MP_ROM_PTR(&camera_capture_obj) },
    { MP_ROM_QSTR(MP_QSTR_release),  MP_ROM_PTR(&camera_release_obj) },
    { MP_ROM_QSTR(MP_QSTR_scan),     MP_ROM_PTR(&camera_scan_obj) },
    { MP_ROM_QSTR(MP_QSTR_gray_size), MP_ROM_PTR(&camera_gray_size_obj) },
};
static MP_DEFINE_CONST_DICT(camera_module_globals, camera_module_globals_table);

const mp_obj_module_t camera_user_cmodule = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&camera_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_camera, camera_user_cmodule);
