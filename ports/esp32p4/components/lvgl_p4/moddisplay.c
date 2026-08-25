/**
 * @file moddisplay.c
 * @brief Modulos `display` e `lvgl` do MicroPython para a Waveshare 4.3-C.
 *
 * Modelado a partir de f469-disco/usermods/udisplay_f469/display.c. O app do
 * Specter usa apenas display.init() e display.update(); o resto existe para
 * paridade com a Discovery.
 *
 * Como no original, este arquivo inclui lv_mpy.c -- o binding LVGL gerado --
 * e registra os dois modulos.
 */

#include "lv_p4_hal.h"
#include "lvgl.h"
#include "p4board.h"
#include "py/builtin.h"
#include "py/obj.h"
#include "py/runtime.h"

static mp_obj_t display_init(void) {
    lv_init();
    tft_init();
    touchpad_init();
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(display_init_obj, display_init);

static mp_obj_t display_update(mp_obj_t dt_obj) {
    lv_tick_inc(mp_obj_get_int(dt_obj));
    lv_task_handler();
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(display_update_obj, display_update);

static mp_obj_t display_on(void) {
    p4board_display_enabled(true);
    p4board_backlight(100);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(display_on_obj, display_on);

static mp_obj_t display_off(void) {
    p4board_backlight(0);
    p4board_display_enabled(false);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(display_off_obj, display_off);

static mp_obj_t display_backlight(mp_obj_t percent_obj) {
    mp_int_t percent = mp_obj_get_int(percent_obj);
    if (percent < 0 || percent > 100) {
        mp_raise_ValueError(MP_ERROR_TEXT("backlight must be 0..100"));
    }
    p4board_backlight((uint32_t)percent);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(display_backlight_obj, display_backlight);

static mp_obj_t display_set_rotation(mp_obj_t rot_obj) {
    /* O painel e fixo em retrato 480x800 e o driver DPI nao gira o
     * framebuffer. Aceitar 0 mantem compatibilidade com o app; qualquer outra
     * coisa e recusada em vez de silenciosamente ignorada. */
    if (mp_obj_get_int(rot_obj) != 0) {
        mp_raise_ValueError(MP_ERROR_TEXT("only rotation 0 is supported"));
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(display_set_rotation_obj, display_set_rotation);

static const mp_rom_map_elem_t display_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__),     MP_ROM_QSTR(MP_QSTR_udisplay) },
    { MP_ROM_QSTR(MP_QSTR_init),         MP_ROM_PTR(&display_init_obj) },
    { MP_ROM_QSTR(MP_QSTR_update),       MP_ROM_PTR(&display_update_obj) },
    { MP_ROM_QSTR(MP_QSTR_on),           MP_ROM_PTR(&display_on_obj) },
    { MP_ROM_QSTR(MP_QSTR_off),          MP_ROM_PTR(&display_off_obj) },
    { MP_ROM_QSTR(MP_QSTR_backlight),    MP_ROM_PTR(&display_backlight_obj) },
    { MP_ROM_QSTR(MP_QSTR_set_rotation), MP_ROM_PTR(&display_set_rotation_obj) },
};
static MP_DEFINE_CONST_DICT(display_module_globals, display_module_globals_table);

const mp_obj_module_t display_user_cmodule = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&display_module_globals,
};

/* Shim de compatibilidade para o binding gerado.
 *
 * lv_mpy.c chama mp_obj_int_to_bytes_impl(), removida do py/objint.h do
 * MicroPython. O binding e codigo gerado por lv_binding_micropython e vive num
 * submodulo, entao a correcao fica aqui em vez de editar o gerado. Mesma
 * quebra de API que atingiu o secp256k1-embedded; ver
 * reports/lv-binding-micropython-master-api.md.
 *
 * A funcao antiga tratava apenas long ints; mp_obj_int_to_bytes trata os dois
 * casos, entao e um superconjunto. overflow_check fica off para preservar o
 * comportamento anterior.
 */
#include "py/objint.h"

static inline void mp_obj_int_to_bytes_impl(mp_obj_t self_in, bool big_endian,
    size_t len, byte *buf) {
    mp_obj_int_to_bytes(self_in, len, buf, big_endian, false, false);
}

#include "lv_mpy.c"

MP_REGISTER_MODULE(MP_QSTR_udisplay, display_user_cmodule);
MP_REGISTER_MODULE(MP_QSTR_lvgl, mp_module_lvgl);
