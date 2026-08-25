# `secp256k1-embedded` não compila no MicroPython master

**Destino:** `miketlk/secp256k1-embedded` @ `micropython-upgrade`
**Correções prontas:** `sandman21vs/secp256k1-embedded` @ `micropython-master-api`
**Severidade:** bloqueia o uso em MicroPython pós-v1.25

## Contexto

A branch `micropython-upgrade` foi adaptada para MicroPython v1.25 e é a base do
[PR #358](https://github.com/cryptoadvance/specter-diy/pull/358). Um port para
ESP32-P4 precisa do MicroPython `master`, porque `ESP32_GENERIC_P4` não existe
em nenhuma release (ver `micropython-p4-unreleased.md`). Nessa combinação
aparecem dois problemas.

## Problema 1 — APIs de inteiro removidas ou alteradas

`mpy/libsecp256k1.c` converte um inteiro Python para 8 bytes big-endian em dois
pontos. O código usa duas funções que mudaram:

- `mp_obj_int_to_bytes_impl()` **não existe mais** em `py/objint.h`.
- `mp_binary_set_int()` mudou a assinatura em `py/binary.h`, de
  `(val_sz, big_endian, dest, val)` para
  `(dest_sz, dest, val_sz, val, big_endian)`.

Erros resultantes:

```
error: implicit declaration of function 'mp_obj_int_to_bytes_impl'
error: too few arguments to function 'mp_binary_set_int'
error: passing argument 2 of 'mp_binary_set_int' makes pointer from integer without a cast
```

O substituto é `mp_obj_int_to_bytes()`, que trata small ints e long ints numa
chamada só, então o `#if MICROPY_LONGINT_IMPL` desaparece:

```c
mp_obj_int_to_bytes(valuearg, 8, buf, true, false, false);
```

Uma decisão fica em aberto para o mantenedor: o último argumento é
`overflow_check`. Mantivemos `false` para preservar o comportamento anterior,
que **truncava silenciosamente**. Para valores que representam quantias em
satoshis, truncar em silêncio talvez não seja o que se quer — mas mudar isso é
alteração de comportamento e não cabia a nós decidir.

## Problema 2 — qstrs perdidos no caminho CMake

O corpo inteiro de `libsecp256k1.c` está dentro de `#if MODULE_SECP256K1_ENABLED`
(linhas 22 a 1982). Pelo caminho Makefile isso funciona, porque
`CFLAGS_USERMOD` chega aos dois estágios. Pelo caminho CMake não:

```
error: 'MP_QSTR_secp256k1' undeclared here (not in a function)
error: 'MP_QSTR_ec_pubkey_create' undeclared here (not in a function)
```

A causa está no MicroPython, não aqui — `usermod_gather_sources()` não propaga
`INTERFACE_COMPILE_DEFINITIONS` ao passe de qstr. Detalhes e sugestões em
`micropython-usermod-qstr-defines.md`.

Do lado deste repositório, a correção barata é dar um valor padrão ao macro no
próprio `mpy/config/libsecp256k1-config.h`, que é incluído antes do guard e está
no caminho de include do passe de qstr:

```c
#ifndef MODULE_SECP256K1_ENABLED
#define MODULE_SECP256K1_ENABLED 1
#endif
```

Isso torna o módulo utilizável pelos dois caminhos de build sem depender da
correção upstream, e ainda permite desligá-lo com `-DMODULE_SECP256K1_ENABLED=0`.

## Falta um `micropython.cmake`

O repositório só traz `micropython.mk`. A porta esp32 usa exclusivamente CMake,
então todo consumidor precisa escrever a tradução. A nossa está em
`ports/esp32p4/components/secp256k1.cmake` e é curta — vale considerar incluí-la
no upstream ao lado do `.mk`.

## Resultado depois das correções

Compilado para ESP32-P4 (RISC-V 32 bits, campo 10x26, escalar 8x32) e executado
numa Waveshare 4.3-C. Quatro vetores, todos com valores públicos verificáveis:

| Teste | Resultado |
|---|---|
| Chave privada 1 → ponto gerador | **OK**, bate com a constante da curva |
| ECDSA assina, verifica, rejeita mensagem errada | **OK** |
| BIP340 vetor 0, pubkey x-only | **OK** |
| BIP340 vetor 0, assinatura Schnorr | **OK, idêntica byte a byte** |

A assinatura Schnorr produzida na placa:

```
E907831F80848D1069A5371B402410364BDF1C5F8307B0084C55F1CE2DCA8215
25F66A4A85EA8B71E482A74F382D2CE5EBEEE8FDB2172F477DF4900D310536C0
```

conferida contra `bip-0340/test-vectors.csv` do repositório `bitcoin/bips`,
linha de índice 0.

## Observação de API

`xonly_pubkey_from_pubkey()` devolve uma tupla cujo primeiro item é a struct
interna de 64 bytes do libsecp256k1, **não** a chave x-only serializada de 32
bytes, e o módulo não expõe `xonly_pubkey_serialize`. Quem quiser a x-only
serializada precisa tirar o byte de prefixo da pubkey comprimida. Não é defeito,
mas é uma armadilha fácil — custou um falso negativo no nosso primeiro teste.
Valeria uma linha no README.
