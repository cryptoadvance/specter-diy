# Kern `wave_43` declara ausência de SD card, mas a placa tem SDMMC

**Destino:** https://github.com/odudex/Kern
**Natureza:** capacidade de hardware não exposta

## O fato

`components/wave_43/include/bsp/esp32_p4_wifi6_touch_lcd_43.h` declara:

```c
#define BSP_CAPS_SDCARD 0
```

E `sdkconfig.defaults.wave_43` não define nenhum pino de SD:

```
CONFIG_KERN_BOARD_WAVE_43=y
CONFIG_LV_FONT_MONTSERRAT_22=y
CONFIG_LV_FONT_MONTSERRAT_30=y
CONFIG_ESPTOOLPY_FLASHMODE_QIO=y
```

O `components/sd_card/Kconfig` faz todos os GPIOs default `-1`, isto é, confia
no IOMUX padrão do slot SDMMC. Para esta placa isso não corresponde à fiação.

## Evidência de que a placa tem SDMMC

O `board_config.h` do `miketlk/specter-bootloader` mapeia o slot explicitamente:

```c
#define SPECTER_SDMMC_D0_GPIO  GPIO_NUM_39
#define SPECTER_SDMMC_D1_GPIO  GPIO_NUM_40
#define SPECTER_SDMMC_D2_GPIO  GPIO_NUM_41
#define SPECTER_SDMMC_D3_GPIO  GPIO_NUM_42
#define SPECTER_SDMMC_CLK_GPIO GPIO_NUM_43
#define SPECTER_SDMMC_CMD_GPIO GPIO_NUM_44
```

E o controlador responde no hardware. Com o slot vazio, a sondagem chega até o
`send_op_cond` e expira, que é exatamente o esperado sem cartão — o periférico
está inicializado e falando:

```
E (32289) sdmmc_common: sdmmc_init_ocr: send_op_cond (1) returned 0x107
E (32289) vfs_fat_sdmmc: sdmmc_card_init failed (0x107).
W (32289) specter-media: microSD mount probe failed: ESP_ERR_TIMEOUT
```

**Confirmado com cartão inserido.** Um microSD de 2 GB foi detectado, montado
como FAT, lido, escrito e desmontado nesses pinos, sob MicroPython no
ESP32-P4:

```
present   : True
info      : (1967128576, 512)
montado   : OK
conteudo  : ['System Volume Information', ...]
espaco    : 1.96 GB total
leitura   : escrita pelo ESP32-P4
remocao   : OK
desmontado: OK
```

Ou seja, o slot não só existe: funciona por completo com a fiação 39-44.

## Impacto

Para um signer airgapped, o SD é o segundo canal de transferência além do QR.
Na `wave_43` ele está indisponível hoje, enquanto outras placas do Kern o têm.
O `components/sd_card` já é genérico e parametrizado por Kconfig, então habilitar
parece ser questão de configuração, não de código novo.

## Sugestão

Definir em `sdkconfig.defaults.wave_43`:

```
CONFIG_SD_CLK_GPIO=43
CONFIG_SD_CMD_GPIO=44
CONFIG_SD_D0_GPIO=39
CONFIG_SD_D1_GPIO=40
CONFIG_SD_D2_GPIO=41
CONFIG_SD_D3_GPIO=42
CONFIG_SD_BUS_WIDTH=4
```

E trocar `BSP_CAPS_SDCARD` para `1` no header da placa. Os pinos estão agora
verificados com cartão presente, leitura e escrita inclusas, então a mudança é
de configuração e não carrega risco de fiação errada.
