/* VENDORIZADO -- modificacao local.
 *
 * O macro STATIC foi removido do MicroPython; substituido por `static`.
 *
 * O corpo deste arquivo esta sob #if MODULE_HASHLIB_ENABLED. No caminho CMake
 * do MicroPython esse define nao chega ao passe de extracao de qstr, entao o
 * pre-processador ve um arquivo vazio e a compilacao falha depois com
 * MP_QSTR_hashlib undeclared. Ver reports/micropython-usermod-qstr-defines.md.
 */
#ifndef MODULE_HASHLIB_ENABLED
#define MODULE_HASHLIB_ENABLED 1
#endif

#include <assert.h>
#include <string.h>
#include "py/obj.h"
#include "py/runtime.h"
#include "py/builtin.h"
#include "crypto/sha2.h"
#include "crypto/hmac.h"

#if MODULE_HASHLIB_ENABLED

#define DIGEST_HMAC_SHA256 sizeof(HMAC_SHA256_CTX)
#define DIGEST_HMAC_SHA512 sizeof(HMAC_SHA512_CTX)

typedef struct _mp_obj_hmac_t {
    mp_obj_base_t base;
    size_t digestmod;
    char state[0];
} mp_obj_hmac_t;

/****************************** HMAC ******************************/

static mp_obj_t hmac_HMAC_update(mp_obj_t self_in, mp_obj_t arg);

static mp_obj_t hmac_HMAC_make_new_helper(const mp_obj_type_t *type, size_t n_args, const mp_obj_t *pos_args, mp_map_t *kwargs){
    mp_arg_check_num(n_args, 0, 0, 3, true);

    enum { ARG_key, ARG_message, ARG_digestmod };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_key, MP_ARG_OBJ, {.u_rom_obj = MP_ROM_NONE} },
        { MP_QSTR_msg, MP_ARG_OBJ, {.u_rom_obj = MP_ROM_NONE} },
        { MP_QSTR_digestmod, MP_ARG_OBJ, {.u_rom_obj = MP_ROM_NONE} },
    };
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args, pos_args, kwargs, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    // digestmode
    mp_buffer_info_t digestmodbuf;
    mp_get_buffer_raise(args[ARG_digestmod].u_obj, &digestmodbuf, MP_BUFFER_READ);
    size_t digestmod = 0;
    // only sha256 or sha512 are supported
    if(strcmp(digestmodbuf.buf, "sha256") == 0){
        digestmod = DIGEST_HMAC_SHA256;
    }else if(strcmp(digestmodbuf.buf, "sha512") == 0){
        digestmod = DIGEST_HMAC_SHA512;
    }else{
        mp_raise_ValueError(MP_ERROR_TEXT("Unsupported hash type"));
        return mp_const_none;
    }

    mp_obj_hmac_t *o = m_new_obj_var(mp_obj_hmac_t, state, char, digestmod+sizeof(size_t));
    o->digestmod = digestmod;
    o->base.type = type;

    mp_buffer_info_t key;
    mp_get_buffer_raise(args[ARG_key].u_obj, &key, MP_BUFFER_READ);
    if(digestmod == DIGEST_HMAC_SHA256){
        hmac_sha256_Init((HMAC_SHA256_CTX*)o->state, key.buf, key.len);
    }else if(digestmod == DIGEST_HMAC_SHA512){
        hmac_sha512_Init((HMAC_SHA512_CTX*)o->state, key.buf, key.len);
    }
    if (args[ARG_message].u_obj != mp_const_none) {
        hmac_HMAC_update(MP_OBJ_FROM_PTR(o), args[ARG_message].u_obj);
    }
    return MP_OBJ_FROM_PTR(o);
}

static mp_obj_t hmac_HMAC_make_new(const mp_obj_type_t *type, size_t n_args, size_t n_kw, const mp_obj_t *args) {
    mp_arg_check_num(n_args, n_kw, 0, MP_OBJ_FUN_ARGS_MAX, true);

    mp_map_t kw_args;
    mp_map_init_fixed_table(&kw_args, n_kw, args + n_args);
    return hmac_HMAC_make_new_helper(type, n_args, args, &kw_args);
}

static mp_obj_t hmac_HMAC_copy(mp_obj_t self_in) {
    mp_obj_hmac_t *self = MP_OBJ_TO_PTR(self_in);
    mp_obj_hmac_t *o = m_new_obj_var(mp_obj_hmac_t, state, char, self->digestmod+sizeof(size_t));
    o->base.type = self->base.type;
    o->digestmod = self->digestmod;
    memcpy(o->state, self->state, self->digestmod);
    return MP_OBJ_FROM_PTR(o);
}

static mp_obj_t hmac_HMAC_update(mp_obj_t self_in, mp_obj_t arg) {
    mp_obj_hmac_t *self = MP_OBJ_TO_PTR(self_in);
    mp_buffer_info_t bufinfo;
    mp_get_buffer_raise(arg, &bufinfo, MP_BUFFER_READ);
    if(self->digestmod == DIGEST_HMAC_SHA256){
        hmac_sha256_Update((HMAC_SHA256_CTX*)self->state, bufinfo.buf, bufinfo.len);
    }else if(self->digestmod == DIGEST_HMAC_SHA512){
        hmac_sha512_Update((HMAC_SHA512_CTX*)self->state, bufinfo.buf, bufinfo.len);
    }
    return mp_const_none;
}

static mp_obj_t hmac_HMAC_digest(mp_obj_t self_in) {
    mp_obj_hmac_t *self = MP_OBJ_TO_PTR(self_in);
    vstr_t vstr;
    if(self->digestmod == DIGEST_HMAC_SHA256){
        vstr_init_len(&vstr, SHA256_DIGEST_LENGTH);
        hmac_sha256_Final((HMAC_SHA256_CTX*)self->state, (byte*)vstr.buf);
    }else if(self->digestmod == DIGEST_HMAC_SHA512){
        vstr_init_len(&vstr, SHA512_DIGEST_LENGTH);
        hmac_sha512_Final((HMAC_SHA512_CTX*)self->state, (byte*)vstr.buf);
    }
    return mp_obj_new_bytes_from_vstr(&vstr);
}

static MP_DEFINE_CONST_FUN_OBJ_2(hmac_HMAC_update_obj, hmac_HMAC_update);
static MP_DEFINE_CONST_FUN_OBJ_1(hmac_HMAC_digest_obj, hmac_HMAC_digest);
static MP_DEFINE_CONST_FUN_OBJ_1(hmac_HMAC_copy_obj, hmac_HMAC_copy);

static const mp_rom_map_elem_t hmac_HMAC_locals_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR_update), MP_ROM_PTR(&hmac_HMAC_update_obj) },
    { MP_ROM_QSTR(MP_QSTR_digest), MP_ROM_PTR(&hmac_HMAC_digest_obj) },
    { MP_ROM_QSTR(MP_QSTR_copy), MP_ROM_PTR(&hmac_HMAC_copy_obj) },
};

static MP_DEFINE_CONST_DICT(hmac_HMAC_locals_dict, hmac_HMAC_locals_dict_table);

static const MP_DEFINE_CONST_OBJ_TYPE(
    hmac_HMAC_type,
    MP_QSTR_HMAC,
    MP_TYPE_FLAG_NONE,
    make_new, hmac_HMAC_make_new,
    locals_dict, &hmac_HMAC_locals_dict
);

// key, msg=None, digestmod
static mp_obj_t hmac_new(size_t n_args, const mp_obj_t *args, mp_map_t *kwargs) {
    return hmac_HMAC_make_new_helper(&hmac_HMAC_type, n_args, args, kwargs);
}
static MP_DEFINE_CONST_FUN_OBJ_KW(hmac_new_obj, 0, hmac_new);


/****************************** MODULE ******************************/

static const mp_rom_map_elem_t hmac_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_hmac) },
    { MP_ROM_QSTR(MP_QSTR_new), MP_ROM_PTR(&hmac_new_obj) },
    { MP_ROM_QSTR(MP_QSTR_HMAC), MP_ROM_PTR(&hmac_new_obj) },
};

static MP_DEFINE_CONST_DICT(hmac_module_globals, hmac_module_globals_table);

const mp_obj_module_t hmac_user_cmodule = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t*)&hmac_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_hmac, hmac_user_cmodule);

#endif // MODULE_HASHLIB_ENABLED