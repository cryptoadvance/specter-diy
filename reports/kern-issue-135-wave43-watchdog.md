# Kern issue #135 — travamento no boot da Waveshare 4.3

**Destino:** https://github.com/odudex/Kern/issues/135
**Status upstream:** aberta desde 2026-08-11, sem reprodução pelo mantenedor
**Natureza deste report:** contraprova de hardware, não correção

## A issue

`dongyang4222-coder` reporta que o firmware `wave_43` do Kern trava no boot em
uma Waveshare ESP32-P4-WiFi6-Touch-LCD-4.3 rotulada **JC4880P443C**. Tela preta,
`task_wdt` disparando a cada ~30 s com `MEPC : 0x480a4e5c` idêntico entre o build
de CI e a pré-release v0.0.3, com e sem a câmera OV5647 conectada.

O odudex respondeu que testou o web flasher com o CI mais recente e a v0.0.15 e
funcionou nos dois casos, e levantou a hipótese de **revisão de hardware
diferente**. A issue está parada nesse ponto.

## Por que este report ajuda

Temos uma placa da mesma família rodando um firmware ESP32-P4 **independente**
do Kern, com sequência de inicialização própria, e o painel e o touch funcionam.
Isso ajuda a separar "hardware diferente" de "caminho de init do Kern".

O firmware usado foi o `port_esp32-p4` do `miketlk/specter-bootloader`
(commit `4efca5be`), compilado localmente e gravado via esptool em perfil
plaintext, sem Secure Boot e sem flash encryption.

## Evidência

Identificação da placa, lida pela própria placa via telemetria CBOR:

```json
"platform": {
  "platform_id": "esp32-p4-wifi6-touch-lcd-4p3",
  "board": "lcd-4p3",
  "chip_model": 18,
  "chip_revision": 103,
  "configured_flash_size": 16777216,
  "detected_flash_size": 33554432,
  "detected_psram_size": 33554432,
  "display_width": 480,
  "display_height": 800
}
```

Boot completo, sem watchdog:

```
W (32269) specter-ui: UI hardware diagnostic succeeded
E (32289) sdmmc_common: sdmmc_init_ocr: send_op_cond (1) returned 0x107
W (32289) specter-media: microSD mount probe failed: ESP_ERR_TIMEOUT
I (32349) specter-board-4p3: initializing ESP32-P4-WIFI6-Touch-LCD-4.3-C
I (32519) specter-board-4p3: ST7701 480x800 framebuffer active: DSI=2 lanes at 500 Mbps, LDO=3/2500 mV
I (32529) specter-board-4p3: backlight=100% duty=1023/1023 inverted=1
I (32539) specter-ui: alert rendered: Bootloader Error (480x800, ok=1)
```

(O `ESP_ERR_TIMEOUT` do SDMMC é apenas ausência de cartão. O `Bootloader Error`
é esperado nesse fluxo: não há approval record gravado.)

Touch GT911 respondendo com coordenadas reais durante o diagnóstico:

```
I (30309) specter-touch: raw snapshot 0x814e..0x8156 (1 point)
I (30309) specter-ui: touch id=0 x=471 y=747 size=41
I (30549) specter-ui: touch id=0 x=474 y=745 size=40
I (30569) specter-touch: raw snapshot 0x814e..0x814e (0 points)
```

## Diferenças de init que podem explicar o travamento

O bootloader do miketlk e o `wave_43` do Kern **concordam integralmente** nos
timings do painel (`hsync` 42/12/42, `vsync` 2/8/60), no ST7701, em 2 lanes DSI
a 500 Mbps e no LDO canal 3 / 2500 mV. Divergem em um ponto:

| | miketlk | Kern `wave_43` |
|---|---|---|
| Reset do touch | `GPIO_NUM_23`, `TOUCH_HAS_RESET 1` | `BSP_LCD_TOUCH_RST` = `GPIO_NUM_NC` |
| Endereço GT911 | reset controlado determina o endereço | sonda 0x5D e cai para 0x14 |

O comentário no `wave_43.c` do Kern reconhece a dependência:

> GT911 can respond at either 0x5D (primary) or 0x14 (backup) depending on
> INT/RST timing — probe both and fall back.

Se em alguma revisão a linha de reset do GT911 ficar flutuando, a sondagem em
I²C pode bloquear. Como o I²C do `wave_43` é **compartilhado com a câmera**
(`BSP_CAM_I2C_SCL` = `BSP_I2C_SCL`), um barramento travado nessa fase explicaria
o hang antes de qualquer UI, e explicaria também por que remover a câmera não
muda nada — o barramento é o mesmo.

Isso é hipótese, não diagnóstico: não reproduzimos o travamento e não gravamos
o Kern nesta placa.

## Sugestão

1. Pedir ao reportante um `idf.py monitor` com `addr2line` sobre o ELF exato, ou
   o `.elf` do build, para resolver `MEPC 0x480a4e5c` num símbolo. Sem isso o
   endereço não diz nada entre builds.
2. Instrumentar `bsp_touch_new` com log antes e depois da sondagem I²C, e
   publicar um build de debug para o reportante.
3. Considerar dirigir o reset do GT911 pelo GPIO 23 em vez de sondar dois
   endereços, alinhando com a implementação do miketlk que funciona aqui.

## Como reproduzir nossa contraprova

```bash
git clone -b port_esp32-p4 https://github.com/miketlk/specter-bootloader
cd specter-bootloader && git submodule update --init --recursive
export IDF_PATH="$PWD/third_party/esp-idf" IDF_PATH_FORCE=1
third_party/esp-idf/install.sh esp32p4
SPECTER_BOARD=4p3 SPECTER_KEYS=test \
  platforms/esp32-p4-wifi6-touch-lcd/tools/build.sh plaintext-dev boot-a build flash monitor
```

Ver também `specter-bootloader-export-sh-linux.md` neste diretório: sem
`IDF_PATH_FORCE=1` o build falha silenciosamente em Linux.
