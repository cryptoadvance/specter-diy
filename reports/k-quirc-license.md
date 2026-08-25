# `k_quirc`: licença MIT, detecção do GitHub falha

**Destino:** https://github.com/odudex/k_quirc
**Severidade:** cosmética — mas gerou um falso bloqueio aqui

## Correção de um relato anterior

A primeira versão deste arquivo afirmava que o `k_quirc` estava sem licença e
que isso bloqueava o reuso. **Estava errado.** A API do GitHub retorna
`"license": "NOASSERTION"`, mas o repositório **tem** um `LICENSE`, e ele é
**MIT**, com a cadeia de atribuição completa:

```
MIT License

Original Copyright (C) 2010-2012 Daniel Beer <dlbeer@gmail.com>
OpenMV modifications Copyright (c) 2013-2021 Ibrahim Abdelkader
OpenMV modifications Copyright (c) 2013-2021 Kwabena W. Agyeman
K-Quirc modifications Copyright (c) 2025 Kern contributors
```

Totalmente compatível com o `specter-diy`, que também é MIT. Não há bloqueio.

A lição, para nós: `NOASSERTION` significa "o detector não conseguiu
classificar", não "não há licença". Abrir o arquivo custa dez segundos e evita
uma decisão de arquitetura tomada em cima de nada.

## Por que a detecção falha

O `licensee`, usado pelo GitHub, casa o texto contra modelos conhecidos. Aqui o
cabeçalho tem **quatro linhas de copyright** entre o título `MIT License` e o
parágrafo `Permission is hereby granted`, o que afasta o texto o suficiente do
modelo para não bater.

## Sugestão

Adicionar um identificador legível por máquina resolve a detecção sem tocar no
texto legal:

1. `SPDX-License-Identifier: MIT` no topo do `LICENSE` e nos cabeçalhos dos
   fontes; ou
2. mover o bloco de copyright para depois do parágrafo de permissão, deixando o
   modelo MIT intacto no início.

Vale a pena: um `NOASSERTION` faz projetos a jusante hesitarem em vendorizar,
que é exatamente o que aconteceu aqui.
