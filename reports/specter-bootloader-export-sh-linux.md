# `tools/idf.sh` falha silenciosamente em Linux (dash)

**Destino:** `miketlk/specter-bootloader` @ `port_esp32-p4`
**Severidade:** bloqueia o build em Linux; diagnóstico difícil por ser mudo
**Status:** contornável sem alterar o repositório

## Sintoma

Em Ubuntu, qualquer build do port ESP32-P4 termina com **exit 1 e nenhuma saída**:

```
$ platforms/esp32-p4-wifi6-touch-lcd/tools/build.sh plaintext-dev boot-a build
$ echo $?
1
```

Nem stdout nem stderr. `build.sh` roda até o fim e faz `exec` no `tools/idf.sh`,
que morre sem imprimir nada.

## Causa

`tools/idf.sh` termina com:

```sh
. "$pinned_idf/export.sh" >/dev/null
exec "$pinned_idf/tools/idf.py" "$@"
```

O `export.sh` do ESP-IDF descobre a própria localização por mecanismos
específicos de shell — `$BASH_SOURCE` em bash, equivalentes em zsh. Sob o
`/bin/sh` do Debian/Ubuntu, que é **dash**, nada disso existe. Ele cai no
fallback `idf_path=.`, testa `./tools/idf.py` a partir do diretório corrente
(a raiz do repositório, não o ESP-IDF), não encontra e retorna 1.

Como `idf.sh` roda sob `set -eu`, o script morre nesse ponto. E como o stdout do
`export.sh` foi redirecionado para `/dev/null`, a mensagem que explicaria tudo
some junto:

```
+ . /.../third_party/esp-idf/export.sh
+ idf_path=.
+ [ ! -f ./tools/idf.py ]
+ echo Could not automatically detect IDF_PATH from script location...
+ echo To use the IDF_PATH set in the environment, you can enforce it by setting 'export IDF_PATH_FORCE=1'
+ return 1
```

O README do port usa caminhos `/dev/cu.usbmodemXXXX`, o que indica
desenvolvimento em macOS, onde `/bin/sh` é bash 3.2 e a auto-detecção funciona.

## Contorno

Sem tocar no repositório. O `idf.sh` já aceita um `IDF_PATH` do ambiente desde
que aponte para o checkout pinado — ele só recusa um caminho divergente:

```sh
export IDF_PATH="$REPO/third_party/esp-idf"
export IDF_PATH_FORCE=1
```

Com isso o build passa e o ESP-IDF v5.5.5 ativa normalmente, inclusive sob
Python 3.14.

## Sugestões

1. **Não engolir o stderr.** Trocar `>/dev/null` por algo que preserve a
   mensagem em caso de falha, ou testar o retorno e reemitir o erro. Um exit 1
   mudo custa muito tempo de diagnóstico.
2. **Exportar `IDF_PATH` e `IDF_PATH_FORCE` dentro do próprio `idf.sh`** antes de
   dar source no `export.sh`. O script já conhece o caminho pinado e já valida
   que o checkout bate com o gitlink, então a auto-detecção não agrega nada.
3. **Ou trocar o shebang para `#!/usr/bin/env bash`**, já que o script é
   utilitário de build e não tem requisito de POSIX estrito.

A sugestão 2 é a mais direta e mantém o comportamento em macOS.

## Ambiente onde ocorreu

Ubuntu, `/bin/sh -> dash`, git 2.53.0, Python 3.14.4, gcc 15.2.0,
ESP-IDF v5.5.5 (`b774170f`), `riscv32-esp-elf-gcc` 14.2.0.
