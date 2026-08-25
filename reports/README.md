# Reports

Achados levantados durante o port do Specter DIY para ESP32-P4
(Waveshare ESP32-P4-WIFI6-Touch-LCD-4.3-C), guardados para reporte posterior aos
projetos de origem.

Cada arquivo traz o fato observado, a evidência, o impacto e uma sugestão. Onde
não houve confirmação definitiva, isso está dito no texto — vários achados são
divergências entre fontes, não defeitos comprovados.

## Para `odudex/Kern`

| Arquivo | Assunto |
|---|---|
| [kern-issue-135-wave43-watchdog.md](kern-issue-135-wave43-watchdog.md) | Contraprova de hardware para a issue #135 (travamento no boot da 4.3), que o mantenedor não consegue reproduzir |
| [touch-reset-gpio-divergence.md](touch-reset-gpio-divergence.md) | Reset do GT911: GPIO 23 vs `GPIO_NUM_NC` |
| [kern-wave43-no-sdcard.md](kern-wave43-no-sdcard.md) | `BSP_CAPS_SDCARD 0` numa placa que tem SDMMC em 39–44 |
| [k-quirc-license.md](k-quirc-license.md) | `k_quirc` é MIT, mas o detector do GitHub reporta `NOASSERTION`; sugestão de SPDX |
| [wave43-panel-cross-validation.md](wave43-panel-cross-validation.md) | Nota positiva: parâmetros do painel batem com fonte independente |

## Para `miketlk/specter-bootloader`

| Arquivo | Assunto |
|---|---|
| [specter-bootloader-export-sh-linux.md](specter-bootloader-export-sh-linux.md) | `tools/idf.sh` falha mudo em Linux (dash sem `$BASH_SOURCE`) |
| [cbor2-python314.md](cbor2-python314.md) | `requirements.txt` do mock não instala em Python 3.14 |
| [touch-reset-gpio-divergence.md](touch-reset-gpio-divergence.md) | Mesmo achado, do outro lado |
| [wave43-panel-cross-validation.md](wave43-panel-cross-validation.md) | Nota positiva |

## Para `miketlk/secp256k1-embedded`

| Arquivo | Assunto |
|---|---|
| [secp256k1-embedded-micropython-master.md](secp256k1-embedded-micropython-master.md) | Não compila no MicroPython master: APIs de inteiro removidas e qstrs perdidos; correções prontas em fork |

## Para `miketlk/f469-disco`

| Arquivo | Assunto |
|---|---|
| [f469-disco-uhashlib-micropython-master.md](f469-disco-uhashlib-micropython-master.md) | `uhashlib` usa o macro `STATIC` removido, perde qstrs no CMake e colide com o `hashlib` embutido |

## Para `lvgl/lv_binding_micropython`

| Arquivo | Assunto |
|---|---|
| [lv-binding-micropython-master-api.md](lv-binding-micropython-master-api.md) | O binding gerado chama `mp_obj_int_to_bytes_impl()`, removida do MicroPython master |

## Para `micropython/micropython`

| Arquivo | Assunto |
|---|---|
| [micropython-usermod-qstr-defines.md](micropython-usermod-qstr-defines.md) | Usermods CMake perdem qstrs quando o corpo depende de um define próprio; erro resultante aponta para o lugar errado |

## Interno

| Arquivo | Assunto |
|---|---|
| [micropython-p4-unreleased.md](micropython-p4-unreleased.md) | `ESP32_GENERIC_P4` só existe no `master`; conflito de versões de ESP-IDF entre os três projetos |

## Prioridade sugerida de reporte

1. **kern-issue-135** — há uma issue aberta e parada esperando exatamente este
   tipo de dado de outra unidade.
2. **specter-bootloader-export-sh-linux** — bloqueia qualquer pessoa em Linux, e
   o modo de falha mudo torna o diagnóstico caro.
3. **micropython-usermod-qstr-defines** — afeta qualquer usermod CMake, e a
   mensagem de erro aponta para o lugar errado. Tem reprodução mínima e
   correção sugerida.
4. **secp256k1-embedded-micropython-master** — as correções já estão prontas
   num fork, é só abrir o PR.
5. **k-quirc-license** — cosmético, mas evita que outros hesitem em reusar.
6. O resto quando houver oportunidade.
