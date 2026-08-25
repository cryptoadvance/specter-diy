# `mock_app/tools/requirements.txt` não instala em Python 3.14

**Destino:** `miketlk/specter-bootloader` @ `port_esp32-p4`
**Severidade:** baixa; afeta só a ferramenta de telemetria do mock

## Sintoma

O README do port instrui:

```sh
python -m pip install --require-hashes \
  -r platforms/esp32-p4-wifi6-touch-lcd/mock_app/tools/requirements.txt
```

Em Python 3.14 isso falha:

```
Building wheel for cbor2 (pyproject.toml): finished with status 'error'
  error: can't find Rust compiler
ERROR: Failed building wheel for cbor2
```

O `requirements.txt` pina `cbor2==6.1.2` com hash. Não há wheel pré-compilada
para cp314, então o pip tenta construir da fonte, e a build do `cbor2` 6.1.2
exige uma toolchain Rust que não é declarada como dependência de sistema.

Tentar `CBOR2_BUILD_C_EXTENSION=0` não ajuda — a falha ocorre antes, na
resolução do backend de build.

## Impacto

`mock_telemetry.py` é a única forma documentada de ler a telemetria CBOR do mock
firmware pela serial. Sem ele, quem estiver em Python 3.14 fica sem o
decodificador de referência.

## Contorno usado

Escrevemos um decodificador CBOR mínimo em Python puro, reaproveitando o mesmo
enquadramento SPMF do `mock_telemetry.py` (magic `SPMF`, versão, flags,
comprimento big-endian de 4 bytes, payload, CRC32 big-endian). Funcionou:

```
quadros SPMF validos (CRC32 conferido): 4
```

## Sugestões

1. Declarar a faixa de Python suportada no README do port, já que o pin com
   `--require-hashes` amarra a versão do `cbor2`.
2. Ou afrouxar para uma faixa que tenha wheels em Python recente
   (`cbor2>=5.6,<7`), mantendo `--require-hashes` com os hashes das wheels.
3. Ou documentar `apt install rustc cargo` como pré-requisito, embora seja
   pesado para um decodificador de telemetria.

A opção 2 parece a melhor relação custo-benefício.
