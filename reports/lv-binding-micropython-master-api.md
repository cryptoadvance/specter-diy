# Binding LVGL gerado usa API removida do MicroPython

**Destino:** `lvgl/lv_binding_micropython` (gerador), e por consequência
`miketlk/f469-disco` @ `micropython-upgrade` (que carrega o `lv_mpy.c` gerado)
**Severidade:** baixa — uma linha, mas bloqueia a compilação

## O fato

`lv_mpy.c`, o binding gerado por `lv_binding_micropython`, contém:

```c
static unsigned long long mp_obj_get_ull(mp_obj_t obj)
{
    if (mp_obj_is_small_int(obj))
        return MP_OBJ_SMALL_INT_VALUE(obj);

    unsigned long long val = 0;
    bool big_endian = !(__BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__);
    mp_obj_int_to_bytes_impl(obj, big_endian, sizeof(val), (byte*)&val);
    return val;
}
```

`mp_obj_int_to_bytes_impl()` foi **removida** de `py/objint.h` no `master` do
MicroPython. Resultado:

```
error: implicit declaration of function 'mp_obj_int_to_bytes_impl';
       did you mean 'mp_obj_int_from_bytes_impl'?
```

Uma única ocorrência no arquivo inteiro de 47 mil linhas.

## Substituto

`mp_obj_int_to_bytes()`, que trata small ints e long ints numa chamada:

```c
mp_obj_int_to_bytes(obj, sizeof(val), (byte*)&val, big_endian, false, false);
```

Como o chamador já trata o caso small int antes, a troca é equivalente. O
`overflow_check` em `false` preserva o comportamento anterior.

## Onde corrigir

O trecho vem do gerador, não do LVGL — está sob o comentário
`// Missing implementation for 64bit integer conversion`. A correção pertence ao
template do `lv_binding_micropython`; corrigir o `lv_mpy.c` gerado resolve um
consumidor por vez.

Vale notar que é a **mesma quebra de API** que atinge o
`secp256k1-embedded` (ver `secp256k1-embedded-micropython-master.md`). Quem
mantém binding C para MicroPython provavelmente tem essa chamada em algum lugar.

## Contorno aplicado

Como o `lv_mpy.c` vive num submódulo, definimos a função antiga como
`static inline` sobre a nova, imediatamente antes do `#include "lv_mpy.c"`, em
`ports/esp32p4/components/lvgl_p4/moddisplay.c`. Contido e reversível assim que
o upstream corrigir.
