# `uhashlib` do f469-disco não compila no MicroPython master

**Destino:** `miketlk/f469-disco` @ `micropython-upgrade` (e o upstream
`diybitcoinhardware/f469-disco`)
**Severidade:** bloqueia o uso fora do MicroPython v1.25

## Contexto

A branch `micropython-upgrade` já modernizou parte deste usermod — o
`MP_REGISTER_MODULE` está na forma de dois argumentos, ao contrário da `master`,
que ainda usa a de três. Mas restam dois pontos que impedem o uso no `master` do
MicroPython, necessário para qualquer alvo ESP32-P4 (ver
`micropython-p4-unreleased.md`).

## Problema 1 — o macro `STATIC` foi removido

`hashlib.c` tem 52 ocorrências e `uhmac.c` tem 16 de `STATIC`, o macro que o
MicroPython usava no lugar de `static`. Ele não existe mais:

```
error: unknown type name 'STATIC'
error: expected '=', ',', ';', 'asm' or '__attribute__' before 'hmac_HMAC_update'
```

A substituição é mecânica: `STATIC` → `static`.

## Problema 2 — qstrs perdidos no caminho CMake

O corpo de ambos os arquivos está sob `#if MODULE_HASHLIB_ENABLED`. Pelo caminho
Makefile o define chega aos dois estágios via `CFLAGS_USERMOD`; pelo CMake não,
porque o `usermod_gather_sources()` do MicroPython não propaga
`INTERFACE_COMPILE_DEFINITIONS` ao passe de qstr. Resultado:

```
error: 'MP_QSTR_hashlib' undeclared here (not in a function)
```

Mesma causa raiz do que ocorre no `secp256k1-embedded`. Detalhes e sugestões em
`micropython-usermod-qstr-defines.md`; o report do secp está em
`secp256k1-embedded-micropython-master.md`.

## Falta um `micropython.cmake`

Como no `secp256k1-embedded`, só existe `micropython.mk`. A porta esp32 usa
exclusivamente CMake. A nossa tradução está em
`ports/esp32p4/components/uhashlib/micropython.cmake`.

## Colisão de nome com o `hashlib` embutido

O módulo registra-se como `hashlib`, o mesmo nome do embutido do MicroPython.
Na Discovery F469 isso não aparece porque o embutido está desligado. Em um build
onde os dois estejam ativos, há duas implementações disputando o nome.

Desligamos o embutido com `MICROPY_PY_HASHLIB (0)` no `mpconfigboard.h`, o que
é o comportamento desejado: o embutido só traz md5, sha1 e sha256, enquanto
Bitcoin precisa de sha512 (BIP32 usa HMAC-SHA512) e ripemd160 (endereços).

Valeria uma linha no README do usermod avisando disso — quem adotar o módulo num
board novo vai tropeçar.

## Resultado após as correções

Compilado para ESP32-P4 e verificado numa Waveshare 4.3-C:

| Vetor | Resultado |
|---|---|
| `sha256("abc")` | **OK** |
| `sha512("abc")` | **OK** |
| `ripemd160("abc")` | **OK** |
| `hmac_sha512`, RFC 4231 caso 1 | **OK** |
| `pbkdf2_hmac` sha512, semente BIP39 | **OK** |

## Armadilha de teste

A semente BIP39 do mnemônico `abandon ... about` tem dois valores muito citados:
com passphrase vazia dá `5eb00bbd...`, e com a passphrase `TREZOR` dos vetores
oficiais dá `c55257c3...`. Comparar um contra o outro produz um falso negativo
bem convincente. Aconteceu conosco.
