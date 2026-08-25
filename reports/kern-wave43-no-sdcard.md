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

Não testamos com cartão inserido, então a confirmação de montagem FAT está
pendente. O que está demonstrado é que o slot existe e responde nesses pinos.

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

E trocar `BSP_CAPS_SDCARD` para `1` no header da placa. Validar com cartão FAT32
antes de publicar; os pinos vêm de terceiros e nossa verificação foi apenas a
sondagem sem cartão.
