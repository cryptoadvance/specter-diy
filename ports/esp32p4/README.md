# Port do Specter DIY para ESP32-P4

Alvo: **Waveshare ESP32-P4-WIFI6-Touch-LCD-4.3-C** (480x800 MIPI DSI ST7701,
touch GT911, câmera OV5647, 32 MB PSRAM, 16 MB de flash usada de 32 MB físicos).

Trabalho em andamento. Nada aqui é firmware utilizável ainda.

## Perfil de segurança

Enquanto durar o desenvolvimento: **Secure Boot desativado, flash encryption
desativada, nenhum eFuse queimado.** Toda gravação é reversível.

## Restrições que moldam o port

**MicroPython.** O board `ESP32_GENERIC_P4` existe apenas no `master` do
MicroPython; não está em v1.25.0 nem v1.26.0. O fork MicroPython do Specter
(`miketlk/micropython-specter-diy` @ `merge-with-upstream`) está em v1.25.0 e
traz somente `ESP32_GENERIC`. O baseline parte do `master` upstream.

**ESP-IDF.** As três fontes exigem versões incompatíveis:

| Projeto | ESP-IDF |
|---|---|
| MicroPython | 5.3–5.5.4 (recomendada 5.5.2) |
| `miketlk/specter-bootloader` | 5.5.5 pinado |
| `odudex/Kern` | 6.0.2 |

Por isso o código do Kern entra como **referência traduzida**, não como
componente plugado. Detalhes em `reports/micropython-p4-unreleased.md`.

## Procedência de cada driver

| Área | Origem | Situação |
|---|---|---|
| Painel ST7701 + timings | miketlk e Kern (idênticos) | validado no hardware |
| Backlight GPIO 26 (PWM, invertido) | ambos | validado |
| Touch GT911 (0x5D / 0x14) | ambos | validado |
| Reset do touch GPIO 23 | miketlk | divergente do Kern — ver reports |
| SDMMC 39–44 | miketlk | slot responde; falta testar com cartão |
| Rádio C6 em reset (GPIO 54) | Kern | adotado por ser airgapped |
| Câmera OV5647 / MIPI-CSI | Kern | pendente; depende de `esp_video` em 5.5.x |
| Decodificação de QR | Kern (`k_quirc`) | **bloqueado por licença** |

## Origem do app

O app Specter tem 11.184 linhas de Python e apenas 4 arquivos tocam hardware,
com 26 call sites no total:

| Arquivo | Call sites |
|---|---:|
| `src/platform.py` | 19 |
| `src/hosts/qr.py` | 4 |
| `src/hosts/usb.py` | 2 |
| `src/gui/tcp_gui.py` | 1 |

Existe precedente de shim: `f469-disco/libs/unix/pyb.py` finge o módulo `pyb`
inteiro em 117 linhas para o simulador rodar em Linux. O shim ESP32 segue esse
molde, mapeando para `machine.UART`, `machine.Pin` e `esp32`.

## Estrutura

```
boards/WAVESHARE_P4_43/   definição de board do MicroPython
components/               BSP revisado (display, touch, sd, câmera)
tools/                    scripts de build e gravação
```

## Créditos

Trabalho derivado de dois projetos MIT, ambos com revisão própria antes de uso:

- [`miketlk/specter-bootloader`](https://github.com/miketlk/specter-bootloader)
  @ `port_esp32-p4` — bootloader ESP32-P4, mapa de pinos, timings do painel
- [`odudex/Kern`](https://github.com/odudex/Kern) — BSP `wave_43`, pipeline de
  câmera, componente de SD, desligamento do rádio

Divergências e problemas encontrados nessas fontes estão documentados em
`reports/` na raiz deste repositório.

## Estado do baseline

Compilação **funcionando**. MicroPython `master` para `ESP32_GENERIC_P4`,
variante `PRE_REV3`, com ESP-IDF v5.5.5:

```
micropython.bin binary size 0x190e70 bytes.
Smallest app partition is 0x1f0000 bytes. 0x5f190 bytes (19%) free.
```

Gravado e **verificado na placa**. Banner do REPL:

```
MicroPython 8cf130db34-dirty on 2026-08-25; Generic ESP32P4 with pre revision 3 chip with ESP32-P4
>>> import sys; print(sys.implementation)
(name='micropython', version=(1, 30, 0, 'preview'), _machine='Generic ESP32P4 with pre
 revision 3 chip with ESP32-P4', _mpy=143110, _build='ESP32_GENERIC_P4-PRE_REV3', _thread='GIL')
```

Confirmado no hardware:

| Item | Resultado |
|---|---|
| Variante ativa | `ESP32_GENERIC_P4-PRE_REV3` (no próprio banner) |
| Clock | 360 MHz |
| PSRAM | `gc.mem_free()` = 33.091.696 B (~31,6 MB) |
| Filesystem | LFS montado, 7680 blocos de 4096 B (~30 MB) |
| Escrita/leitura | arquivo criado, lido e removido com sucesso |
| Partição da app | `('factory', 65536, 2031616)` |

**Atenção ao primeiro flash:** gravar por cima do layout do bootloader do
Specter deixa resíduo e o MicroPython acusa `filesystem appears to be
corrupted`. Um `esptool erase_flash` antes do primeiro flash resolve; depois
disso o boot fica limpo.

### Duas descobertas do baseline

**A placa exige `BOARD_VARIANT=PRE_REV3`.** A telemetria do mock firmware
reportou `chip_revision: 103`, que no encoding do ESP-IDF é major 1, minor 3, ou
seja **v1.3**. O `board.md` do MicroPython é explícito: revisões 0.x e 1.x
precisam das variantes `PRE_REV3`. O build padrão define
`CONFIG_ESP32P4_REV_MIN_300=y` e não sobe neste silício.

**ESP-IDF 5.5.5 funciona**, apesar de não constar na lista oficial do
MicroPython (5.3, 5.4, 5.4.1, 5.4.2, 5.5.1, 5.5.2, 5.5.4). Isso permite
reaproveitar o checkout já pinado pelo bootloader e o toolchain em
`/home/sm/.espressif-specter-p4`, sem uma segunda árvore de 2,6 GB.

**Nenhuma variante de WiFi.** A placa tem um ESP32-C6, mas o alvo é airgapped.
O rádio fica fora do build e, adiante, será mantido em reset por hardware pelo
GPIO 54, como o Kern faz.

### Reproduzir

```sh
. ports/esp32p4/tools/env.sh
make -C "$MICROPYTHON_DIR/mpy-cross" -j"$(nproc)"
make -C "$MICROPYTHON_DIR/ports/esp32" BOARD=$MP_BOARD BOARD_VARIANT=$MP_VARIANT submodules
ports/esp32p4/tools/build-baseline.sh build
PORT=/dev/ttyACM0 ports/esp32p4/tools/build-baseline.sh flash
```

`idf.py flash` **não** funciona nesta combinação: o wrapper procura
`components/esptool_py/esptool.py`, que não existe mais (o esptool virou pacote
pip, v4.12.0). O `build-baseline.sh flash` chama o módulo direto.

## Fase 2 — display e touch sob MicroPython

Board `WAVESHARE_P4_43` e módulo C `p4board`, **validados no hardware**.

### API

```python
import p4board, framebuf
p4board.init()                      # display + touch; devolve True se o touch subiu
g = framebuf.FrameBuffer(p4board.framebuffer(),
                         p4board.WIDTH, p4board.HEIGHT, framebuf.RGB565)
g.fill_rect(40, 60, 400, 90, 0xF800)
p4board.flush()                     # ou flush(y, altura) para uma faixa
p4board.backlight(100)              # 0..100
p4board.touch()                     # ((id, x, y, size), ...)
p4board.radio_off()                 # segura o ESP32-C6 em reset
```

`framebuffer()` devolve um `memoryview` gravável apontando **direto** para a
memória que o controlador DPI varre — sem cópia. É o que permite usar o
`framebuf` embutido do MicroPython hoje e apontar um draw buffer do LVGL para
o mesmo endereço depois.

### Verificado na placa

| Item | Resultado |
|---|---|
| `import p4board` | 480 x 800 |
| `p4board.init()` | `True` (display e touch) |
| `framebuffer()` | 768.000 bytes = 480 x 800 x 2 |
| Desenho + `flush()` | padrão de barras visível no painel |
| Touch | 819 pontos em 20 s a 50 Hz, cobrindo x 4–475, y 8–797 |
| Endereço do GT911 | **0x14** (backup) |

### O endereço 0x14

Dirigimos o GPIO 23 como reset do touch (fonte: miketlk) **e** mantivemos a
sondagem dupla de endereço (fonte: Kern). O controlador subiu no endereço de
backup mesmo com o reset pulsado.

Ou seja, nesta unidade a sondagem dupla do Kern não é redundância defensiva —
**é o que faz o touch funcionar**. Uma implementação que fixasse 0x5D falharia.
Evidência completa em `reports/touch-reset-gpio-divergence.md`.

### Compilar e gravar

```sh
. ports/esp32p4/tools/env.sh
ports/esp32p4/tools/build.sh build
PORT=/dev/ttyACM0 ports/esp32p4/tools/build.sh flash
```

### Duas armadilhas do build

**Generator expressions não funcionam nos includes do usermod.** O MicroPython
achata os `target_include_directories` de um usermod na lista `INCLUDE_DIRS` do
componente, e o ESP-IDF então verifica que cada entrada é um diretório real. Um
`$<TARGET_PROPERTY:idf::driver,INTERFACE_INCLUDE_DIRECTORIES>` chega literal e o
build morre com *"is not a directory"*. O `components/p4board/micropython.cmake`
resolve os componentes para caminhos absolutos com `idf_component_get_property`.

**O `mpconfigboard.h` precisa desligar rádio explicitamente.** Sem
`MICROPY_PY_BLUETOOTH (0)` o build tenta compilar o NimBLE e falha por falta dos
headers. O `MICROPY_HW_ENABLE_UART_REPL (1)` também é obrigatório: o REPL desta
placa chega pela ponte CH343, não por USB nativo.

## Fase 3 — secp256k1

`secp256k1-embedded` compilado como usermod CMake e **verificado na placa**
contra constantes públicas.

| Teste | Resultado |
|---|---|
| Chave privada 1 → ponto gerador da curva | **OK** |
| ECDSA: assina, verifica, rejeita mensagem errada | **OK** |
| BIP340 vetor 0: pubkey x-only | **OK** |
| BIP340 vetor 0: assinatura Schnorr | **OK, idêntica byte a byte** |

A assinatura Schnorr gerada no ESP32-P4 confere com
`bip-0340/test-vectors.csv` do repositório `bitcoin/bips`, índice 0:

```
E907831F80848D1069A5371B402410364BDF1C5F8307B0084C55F1CE2DCA8215
25F66A4A85EA8B71E482A74F382D2CE5EBEEE8FDB2172F477DF4900D310536C0
```

Isso exercita o caminho inteiro — campo 10x26 e escalar 8x32, ou seja, a
implementação de 32 bits — sobre RISC-V. Rodar:

```sh
mpremote cp ports/esp32p4/test_secp256k1.py :test_secp256k1.py
mpremote exec "import test_secp256k1; test_secp256k1.run()"
```

### Origem e correções

O submódulo aponta para `sandman21vs/secp256k1-embedded` @
`micropython-master-api`, um fork de `miketlk/secp256k1-embedded` @
`micropython-upgrade` com duas correções que precisamos fazer:

1. **APIs de inteiro do MicroPython.** `mp_obj_int_to_bytes_impl()` foi removida
   e `mp_binary_set_int()` mudou de assinatura. Substituídas por
   `mp_obj_int_to_bytes()`, que cobre small e long ints numa chamada.
2. **Qstrs perdidos.** O corpo do módulo está sob `#if MODULE_SECP256K1_ENABLED`,
   e o `usermod_gather_sources()` do MicroPython não propaga
   `INTERFACE_COMPILE_DEFINITIONS` ao passe de qstr — então o pré-processador vê
   um arquivo vazio e a compilação falha com `MP_QSTR_secp256k1 undeclared`.

As duas estão documentadas em `reports/` para reporte upstream. Voltar ao
repositório do miketlk é trocar `url` e `branch` no `.gitmodules`.

### Armadilha da API

`xonly_pubkey_from_pubkey()` devolve uma tupla cujo primeiro item é a struct
interna de 64 bytes do libsecp256k1, **não** a chave x-only serializada, e não
existe `xonly_pubkey_serialize`. Para a x-only, tire o byte de prefixo da pubkey
comprimida. Comparar a struct interna com o vetor BIP340 dá um falso negativo.

### Regeneração de qstr

A regra ninja de `genhdr/qstr.i.last` depende só dos `.c`. Mudar um header que
altera o pré-processamento não dispara regeneração — se uma correção em header
parecer não ter efeito, apague `build-W43/genhdr` antes de concluir qualquer
coisa.
