# Validação cruzada do painel da Waveshare 4.3 entre dois projetos

**Destino:** `odudex/Kern` e `miketlk/specter-bootloader` — nota positiva
**Natureza:** confirmação independente, sem defeito

## Resumo

Duas implementações que não se referenciam chegaram a parâmetros **idênticos**
para o painel da Waveshare ESP32-P4-WiFi6-Touch-LCD-4.3. Registrar isso tem
valor: aumenta a confiança de quem for portar outra coisa para a mesma placa e
reduz o espaço de busca quando algo der errado.

## Parâmetros coincidentes

| Parâmetro | Valor | miketlk | Kern `wave_43` |
|---|---|:---:|:---:|
| Controlador | ST7701 | sim | sim |
| Resolução | 480 x 800 | sim | sim |
| Lanes MIPI DSI | 2 | sim | sim |
| Bitrate por lane | 500 Mbps | sim | sim |
| LDO do DPHY | canal 3, 2500 mV | sim | sim |
| `hsync_back_porch` | 42 | sim | sim |
| `hsync_pulse_width` | 12 | sim | sim |
| `hsync_front_porch` | 42 | sim | sim |
| `vsync_back_porch` | 2 | sim | sim |
| `vsync_pulse_width` | 8 | sim | sim |
| `vsync_front_porch` | 60 | sim | sim |
| LCD reset | GPIO 27 | sim | sim |
| Backlight | GPIO 26, PWM | sim | sim |
| I²C (touch) | SCL 8 / SDA 7 | sim | sim |
| GT911 | 0x5D, backup 0x14 | sim | sim |

Confirmado no hardware com o firmware do miketlk:

```
I (32519) specter-board-4p3: ST7701 480x800 framebuffer active: DSI=2 lanes at 500 Mbps, LDO=3/2500 mV
```

## Onde divergem

Dois pontos, cada um documentado em report próprio:

- **Reset do touch** — GPIO 23 no miketlk, `GPIO_NUM_NC` no Kern.
  Ver `touch-reset-gpio-divergence.md`.
- **SD card** — pinos SDMMC 39–44 no miketlk, `BSP_CAPS_SDCARD 0` no Kern.
  Ver `kern-wave43-no-sdcard.md`.

E um recurso presente apenas no Kern, que consideramos acerto:

- **`BSP_C6_WIFI_EN` (GPIO 54)** — o Kern segura o co-processador ESP32-C6 em
  reset no boot, com latch que sobrevive a soft reset e watchdog, de modo que só
  um power-on reset o libera. Para um dispositivo airgapped isso é uma garantia
  concreta e barata. O port do bootloader não faz. Adotamos.

## Observação de implementação vinda do Kern

Comentário em `mock_screen.c` do bootloader, que vale para qualquer um
desenhando neste painel:

> o texto só faz flush das próprias faixas de scanline; é preciso commitar
> também as linhas intocadas, senão as escritas RGB565 em cache aparecem como
> bandas largas e linhas horizontais fantasmas no painel DPI de varredura
> contínua

É o tipo de detalhe que só aparece olhando a tela, e custa horas quando não se
sabe.
