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
