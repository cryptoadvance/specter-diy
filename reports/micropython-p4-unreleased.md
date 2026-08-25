# `ESP32_GENERIC_P4` do MicroPython existe apenas no `master`

**Destino:** nota interna; relevante para qualquer um planejando port ESP32-P4
**Natureza:** restrição de disponibilidade, não defeito

## O fato

O board `ESP32_GENERIC_P4` está presente em `ports/esp32/boards/` no `master` do
`micropython/micropython`, junto com `mpconfigboard_esp32p4_common.cmake`,
`sdkconfig.p4`, `sdkconfig.p4_pre_rev3`, `sdkconfig.p4_wifi_c5` e
`sdkconfig.p4_wifi_c6`.

Ele **não existe** em nenhuma release publicada:

| Referência | `ESP32_GENERIC_P4` |
|---|---|
| `master` | presente |
| `v1.26.0` | ausente |
| `v1.25.0` | ausente |

Os commits que tocam esse diretório datam de fev–jun/2026 e ainda não entraram
num tag.

## Consequência para o port do Specter

O fork MicroPython do Specter (`miketlk/micropython-specter-diy` @
`merge-with-upstream`) está em v1.25.0 e traz apenas `ESP32_GENERIC` em
`ports/esp32/boards/`. Ou seja, **a base do PR #358 não serve diretamente**
para ESP32-P4.

Caminhos possíveis:

1. Basear o port no `master` do MicroPython e reaplicar por cima as
   customizações do Specter. Traz o P4 de graça, ao custo de acompanhar um alvo
   móvel.
2. Backportar o suporte a P4 para o fork em v1.25. Base estável, mas assume a
   manutenção do backport.
3. Esperar a release que incluir o P4.

Escolhemos (1) para a fase de baseline, porque o objetivo imediato é provar que
o MicroPython sobe nesta placa. A decisão de onde as customizações do Specter
entram fica para depois desse resultado.

## Restrição adicional de ESP-IDF

O `ports/esp32/README.md` do MicroPython declara suporte a ESP-IDF v5.3, v5.4,
v5.4.1, v5.4.2, v5.5.1, v5.5.4, com **v5.5.2 recomendada**. Não menciona a série
6.x.

Isso conflita com duas fontes que queremos aproveitar:

| Projeto | ESP-IDF |
|---|---|
| MicroPython | 5.3–5.5.4 (rec. 5.5.2) |
| `miketlk/specter-bootloader` | 5.5.5 pinado |
| `odudex/Kern` | 6.0.2 |

Nenhuma versão satisfaz os três. Por isso o plano trata o código do Kern como
referência a ser traduzida, não como componente a ser plugado.

Vale registrar que o README do port do bootloader já documenta o delta 5.5↔6.0
que ele precisou aplicar para compilar os exemplos da Waveshare em IDF 6:
remoção do caminho obsoleto de unit-test, `espressif/usb` 1.5.0, dependências
separadas de GPIO/I2C/I2S/SPI/SDMMC/LEDC, e tradução de campos de configuração
de LCD removidos na 6. Lido ao contrário, é o guia de backport de que
precisamos.

## Adendo: `esp_video` funciona em ESP-IDF 5.5.x

A tabela acima sugeria que a câmera exigiria a série 6, já que o Kern usa
6.0.2. **Não exige.** Verificado em duas etapas:

1. Um projeto de teste isolado com `espressif/esp_video: "^2"` resolveu para
   `esp_video 2.4.1` e `esp_cam_sensor 2.4.0` contra o ESP-IDF v5.5.5, e
   compilou sem um único erro.
2. No firmware real, com `CONFIG_CAMERA_OV5647=y`, o sensor foi detectado, o
   dispositivo V4L2 abriu e a captura rodou a **45,5 fps em 1280x960 RGB565**.

Ou seja, o Kern usar 6.0.2 é escolha do projeto, não exigência dos componentes
de câmera. Isso importa para quem precisa ficar em 5.5.x — como qualquer port
com MicroPython, que não suporta a série 6.
