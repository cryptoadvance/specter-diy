# Divergência no reset do GT911 entre duas implementações da Waveshare 4.3

**Destino:** `odudex/Kern` e `miketlk/specter-bootloader`
**Natureza:** discrepância factual entre duas fontes independentes

## O fato

Duas implementações independentes da mesma placa
(Waveshare ESP32-P4-WiFi6-Touch-LCD-4.3) descrevem o pino de reset do
controlador de toque GT911 de formas incompatíveis.

`miketlk/specter-bootloader` @ `port_esp32-p4`,
`platforms/esp32-p4-wifi6-touch-lcd/lcd-4p3/board_config.h`:

```c
#define SPECTER_TOUCH_RESET_GPIO GPIO_NUM_23
#define SPECTER_TOUCH_HAS_RESET 1
#define SPECTER_TOUCH_INTERRUPT_GPIO GPIO_NUM_NC
#define SPECTER_TOUCH_GT911_ADDRESS 0x5du
#define SPECTER_TOUCH_GT911_BACKUP_ADDRESS 0x14u
```

`odudex/Kern`, `components/wave_43/include/bsp/esp32_p4_wifi6_touch_lcd_43.h`:

```c
#define BSP_LCD_TOUCH_RST (GPIO_NUM_NC)
#define BSP_LCD_TOUCH_INT (GPIO_NUM_NC)
```

Uma das duas está incompleta. Ambas tratam o endereço duplo 0x5D/0x14, o que é
consistente: o GT911 escolhe o endereço em função do nível de INT durante o
pulso de reset.

## Por que importa

Sem controlar o reset, o endereço do GT911 fica indeterminado — depende do
estado em que o chip foi deixado pelo boot anterior. O Kern contorna sondando os
dois endereços, e documenta a causa:

> GT911 can respond at either 0x5D (primary) or 0x14 (backup) depending on
> INT/RST timing — probe both and fall back.

Dirigir o reset elimina a indeterminação em vez de contorná-la. Além disso, o
I²C do `wave_43` é compartilhado com a câmera, então uma sondagem que trave
afeta os dois periféricos — possivelmente relacionado à issue #135 (ver
`kern-issue-135-wave43-watchdog.md`).

## Evidência de qual está certa

Parcial e a favor do GPIO 23: com o firmware do miketlk, que dirige esse pino,
o GT911 respondeu de forma estável nesta placa, com multitouch e coordenadas
coerentes ao longo de 30 s de leitura contínua a 50 Hz.

```
I (30309) specter-ui: touch id=0 x=471 y=747 size=41
I (30549) specter-ui: touch id=0 x=474 y=745 size=40
I (30569) specter-touch: raw snapshot 0x814e..0x814e (0 points)
```

Isso demonstra que o GPIO 23 **não atrapalha**, mas não prova sozinho que ele é
o reset — um pino não conectado também não atrapalharia. A confirmação
definitiva é o esquemático da Waveshare.

## Evidência nova: dirigir o GPIO 23 não seleciona o endereço primário

Implementamos as duas coisas juntas — reset dirigido no GPIO 23 **e** sondagem
dupla — e medimos o resultado no hardware sob MicroPython:

```
>>> p4board.init()
True
>>> print('addr = 0x%02x' % p4board.touch_address())
addr = 0x14
```

O controlador subiu no **endereço de backup 0x14**, não no primário 0x5D, apesar
do pulso de reset de 10 ms em nível baixo seguido de 50 ms de espera.

Isso enfraquece a hipótese de que o GPIO 23 seja o reset do GT911, ou indica que
o nível do INT durante o pulso é que decide — e o INT está como `GPIO_NUM_NC`
nas duas fontes. De qualquer forma:

- **A sondagem dupla do Kern não é defensiva, é necessária.** Nesta placa o
  endereço primário não responde. Uma implementação que fixasse 0x5D falharia.
- **A afirmação `SPECTER_TOUCH_HAS_RESET 1` do miketlk não produz o efeito
  esperado**, ao menos nesta unidade. O touch funciona, mas por causa do
  fallback, não do reset.

Com a combinação das duas abordagens o touch operou de forma estável: 819
pontos lidos em 20 s de varredura a 50 Hz, cobrindo todo o painel (x de 4 a 475,
y de 8 a 797, contra os limites 480x800).

## Sugestão

- Conferir contra o esquemático oficial em
  https://github.com/waveshareteam/ESP32-P4-WIFI6-Touch-LCD-X
- Se o GPIO 23 for o reset, definir `BSP_LCD_TOUCH_RST` no Kern e manter a
  sondagem dupla apenas como fallback defensivo.
- Se não for, corrigir o `board_config.h` do miketlk, que hoje afirma
  `TOUCH_HAS_RESET 1`.

## O que fizemos neste port

Adotamos o GPIO 23 como reset **e** mantivemos a sondagem dupla de endereço.
A medição acima justifica a decisão a posteriori: sem o fallback do Kern, o
touch não teria funcionado nesta unidade; sem o reset do miketlk, não teríamos
como saber que o reset não resolve o endereço.

Fica em aberto se o GPIO 23 tem alguma função aqui. Só o esquemático responde.
