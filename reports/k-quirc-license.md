# `k_quirc` sem licença identificável

**Destino:** https://github.com/odudex/k_quirc
**Natureza:** bloqueio jurídico para reuso, não defeito técnico

## O fato

A API do GitHub retorna para `odudex/k_quirc`:

```json
{"license": "NOASSERTION"}
```

`NOASSERTION` significa que o detector de licenças não conseguiu identificar um
texto de licença reconhecível no repositório.

O `k_quirc` é submódulo do Kern (`components/k_quirc`) e é descrito como
"adapted from quirc". O `quirc` original, de Daniel Beer, é distribuído sob
**ISC**, que é permissiva e compatível com MIT — mas isso precisa estar
explícito no derivado, com a atribuição original preservada.

Para comparação, os outros submódulos do Kern estão claros:

| Componente | Licença |
|---|---|
| `odudex/Kern` | MIT |
| `odudex/cUR` | BSD-2-Clause-Patent |
| `odudex/k_quirc` | **NOASSERTION** |
| `odudex/libwally-core` | herda do upstream |

## Por que importa aqui

O `specter-diy` é MIT (`Copyright (c) 2019 cryptoadvance`). Vendorizar o
`k_quirc` para o pipeline de QR por câmera exige clareza sobre os termos e
sobre a atribuição devida ao autor do `quirc`.

O `cUR`, sob BSD-2-Clause-Patent, é compatível com MIT, mas tem cláusula de
patente e exige manutenção do aviso — vale registrar em `NOTICE` se for
vendorizado.

## Sugestão

Adicionar ao `k_quirc` um `LICENSE` explícito, preservando o texto e a
atribuição ISC do `quirc` original, e um cabeçalho nos arquivos derivados
indicando origem e modificações. É mudança de minutos que destrava o reuso a
jusante.

## Ação deste port

Não vendorizar o `k_quirc` até haver definição. A fase de câmera pode começar
pelo pipeline de captura (`esp_video`/`esp_cam_sensor`), que é da Espressif e
tem licença clara, deixando a decodificação de QR para quando a licença estiver
resolvida — ou usando outra implementação se não estiver.
