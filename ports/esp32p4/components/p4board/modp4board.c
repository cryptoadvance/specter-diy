/**
 * @file modp4board.c
 * @brief MicroPython bindings for the Waveshare ESP32-P4 4.3-C board.
 *
 * Exposes the panel framebuffer directly as a writable memoryview so that
 * MicroPython's built-in framebuf.FrameBuffer can draw into it with no copy,
 * and so an LVGL draw buffer can later point at the same memory.
 */

#include "board_config.h"
#include "esp_err.h"
#include "p4board.h"
#include "py/objarray.h"
#include "py/runtime.h"

static void check(esp_err_t err, const char *what) {
    if (err != ESP_OK) {
        mp_raise_msg_varg(&mp_type_OSError, MP_ERROR_TEXT("%s: %s"), what,
            esp_err_to_name(err));
    }
}

static mp_obj_t p4board_init(void) {
    check(p4board_display_init(), "display");
    /* Touch failure is not fatal: the panel is still usable, and a board with
     * a detached touch flex should still boot to a REPL that can say so. */
    esp_err_t touch = p4board_touch_init();
    return touch == ESP_OK ? mp_const_true : mp_const_false;
}
static MP_DEFINE_CONST_FUN_OBJ_0(p4board_init_obj, p4board_init);

static mp_obj_t p4board_deinit(void) {
    p4board_touch_deinit();
    p4board_display_deinit();
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(p4board_deinit_obj, p4board_deinit);

static mp_obj_t p4board_backlight_fn(mp_obj_t percent_in) {
    mp_int_t percent = mp_obj_get_int(percent_in);
    if (percent < 0 || percent > 100) {
        mp_raise_ValueError(MP_ERROR_TEXT("backlight must be 0..100"));
    }
    check(p4board_backlight((uint32_t)percent), "backlight");
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(p4board_backlight_obj, p4board_backlight_fn);

static mp_obj_t p4board_display_fn(mp_obj_t on_in) {
    check(p4board_display_enabled(mp_obj_is_true(on_in)), "display");
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(p4board_display_obj, p4board_display_fn);

static mp_obj_t p4board_size(void) {
    mp_obj_t items[2] = {
        MP_OBJ_NEW_SMALL_INT(P4BOARD_LCD_WIDTH),
        MP_OBJ_NEW_SMALL_INT(P4BOARD_LCD_HEIGHT),
    };
    return mp_obj_new_tuple(2, items);
}
static MP_DEFINE_CONST_FUN_OBJ_0(p4board_size_obj, p4board_size);

static mp_obj_t p4board_framebuffer_fn(void) {
    uint16_t *fb = p4board_framebuffer();
    if (!fb) {
        mp_raise_msg(&mp_type_OSError, MP_ERROR_TEXT("display not initialised"));
    }
    /* RGB565: two bytes per pixel. Handed out as bytes so framebuf can wrap it
     * directly with framebuf.RGB565. */
    size_t nbytes = (size_t)P4BOARD_LCD_WIDTH * P4BOARD_LCD_HEIGHT * 2u;
    return mp_obj_new_memoryview('B' | MP_OBJ_ARRAY_TYPECODE_FLAG_RW, nbytes, fb);
}
static MP_DEFINE_CONST_FUN_OBJ_0(p4board_framebuffer_obj, p4board_framebuffer_fn);

static mp_obj_t p4board_flush_fn(size_t n_args, const mp_obj_t *args) {
    mp_int_t y = n_args > 0 ? mp_obj_get_int(args[0]) : 0;
    mp_int_t height = n_args > 1 ? mp_obj_get_int(args[1])
                                 : P4BOARD_LCD_HEIGHT - y;
    if (y < 0 || height < 0 || y + height > P4BOARD_LCD_HEIGHT) {
        mp_raise_ValueError(MP_ERROR_TEXT("flush region out of range"));
    }
    check(p4board_flush((uint16_t)y, (uint16_t)height), "flush");
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(p4board_flush_obj, 0, 2, p4board_flush_fn);

static mp_obj_t p4board_touch_fn(void) {
    p4board_touch_point_t points[P4BOARD_TOUCH_MAX_POINTS];
    uint8_t count = 0;
    esp_err_t err = p4board_touch_read(points, P4BOARD_TOUCH_MAX_POINTS, &count);
    if (err == ESP_ERR_INVALID_STATE) {
        mp_raise_msg(&mp_type_OSError, MP_ERROR_TEXT("touch not initialised"));
    }
    /* A malformed frame is reported as "no points" rather than an exception:
     * callers poll this in a loop and a transient bad read should not abort
     * the UI. Genuine absence and a rejected frame both yield an empty tuple. */
    mp_obj_t items[P4BOARD_TOUCH_MAX_POINTS];
    for (uint8_t i = 0; i < count; ++i) {
        mp_obj_t point[4] = {
            MP_OBJ_NEW_SMALL_INT(points[i].id),
            MP_OBJ_NEW_SMALL_INT(points[i].x),
            MP_OBJ_NEW_SMALL_INT(points[i].y),
            MP_OBJ_NEW_SMALL_INT(points[i].size),
        };
        items[i] = mp_obj_new_tuple(4, point);
    }
    return mp_obj_new_tuple(count, items);
}
static MP_DEFINE_CONST_FUN_OBJ_0(p4board_touch_obj, p4board_touch_fn);

static mp_obj_t p4board_touch_address_fn(void) {
    return MP_OBJ_NEW_SMALL_INT(p4board_touch_address());
}
static MP_DEFINE_CONST_FUN_OBJ_0(p4board_touch_address_obj, p4board_touch_address_fn);

static mp_obj_t p4board_radio_off_fn(void) {
    check(p4board_radio_off(), "radio");
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(p4board_radio_off_obj, p4board_radio_off_fn);

static const mp_rom_map_elem_t p4board_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__),      MP_ROM_QSTR(MP_QSTR_p4board) },
    { MP_ROM_QSTR(MP_QSTR_init),          MP_ROM_PTR(&p4board_init_obj) },
    { MP_ROM_QSTR(MP_QSTR_deinit),        MP_ROM_PTR(&p4board_deinit_obj) },
    { MP_ROM_QSTR(MP_QSTR_backlight),     MP_ROM_PTR(&p4board_backlight_obj) },
    { MP_ROM_QSTR(MP_QSTR_display),       MP_ROM_PTR(&p4board_display_obj) },
    { MP_ROM_QSTR(MP_QSTR_size),          MP_ROM_PTR(&p4board_size_obj) },
    { MP_ROM_QSTR(MP_QSTR_framebuffer),   MP_ROM_PTR(&p4board_framebuffer_obj) },
    { MP_ROM_QSTR(MP_QSTR_flush),         MP_ROM_PTR(&p4board_flush_obj) },
    { MP_ROM_QSTR(MP_QSTR_touch),         MP_ROM_PTR(&p4board_touch_obj) },
    { MP_ROM_QSTR(MP_QSTR_touch_address), MP_ROM_PTR(&p4board_touch_address_obj) },
    { MP_ROM_QSTR(MP_QSTR_radio_off),     MP_ROM_PTR(&p4board_radio_off_obj) },
    { MP_ROM_QSTR(MP_QSTR_WIDTH),         MP_ROM_INT(P4BOARD_LCD_WIDTH) },
    { MP_ROM_QSTR(MP_QSTR_HEIGHT),        MP_ROM_INT(P4BOARD_LCD_HEIGHT) },
};
static MP_DEFINE_CONST_DICT(p4board_module_globals, p4board_module_globals_table);

const mp_obj_module_t p4board_user_cmodule = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&p4board_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_p4board, p4board_user_cmodule);
