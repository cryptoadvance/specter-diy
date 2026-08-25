# Usermods CMake perdem qstrs quando o corpo depende de um define próprio

**Destino:** `micropython/micropython`
**Severidade:** média — falha real, mensagem de erro totalmente enganosa
**Afeta:** qualquer user C module construído pelo caminho CMake

## Sintoma

Um usermod cujo corpo está dentro de `#if MEU_MODULO_ENABLED`, com o define
fornecido por `target_compile_definitions`, compila com erros deste tipo:

```
error: 'MP_QSTR_secp256k1' undeclared here (not in a function);
       did you mean 'MP_QSTR_sha256'?
error: 'MP_QSTR_ec_pubkey_create' undeclared here (not in a function);
       did you mean 'secp256k1_ec_pubkey_create'?
```

O módulo aparece normalmente no log de configuração:

```
Including User C Module(s) from .../components/micropython.cmake
Found User C Module(s): usermod_p4board, usermod_secp256k1
```

E nada indica que o problema é o define.

## Causa

`py/usermod.cmake`, em `usermod_gather_sources()`, propaga apenas duas
propriedades do alvo INTERFACE:

```cmake
get_target_property(lib_sources ${LIB} INTERFACE_SOURCES)
get_target_property(lib_include_directories ${LIB} INTERFACE_INCLUDE_DIRECTORIES)
```

`INTERFACE_COMPILE_DEFINITIONS` não é coletada. Os fontes entram em
`MICROPY_SOURCE_USERMOD` e daí em `MICROPY_SOURCE_QSTR`, mas o passe de
extração de qstr roda o pré-processador **sem** os defines do módulo.

Resultado: a unidade de tradução inteira desaparece atrás do `#if`, nenhum
`MP_QSTR_*` é coletado, e a compilação posterior — que **recebe** o define via
o alvo do componente — falha ao referenciar qstrs que nunca foram gerados.

Comprovação neste caso: `-DMODULE_SECP256K1_ENABLED=1` aparece na linha de
compilação do `.o` e **não** aparece nos cflags do script de qstr.

O passe também não falha nem avisa. `makeqstrdefs.py` só levanta erro se o
pré-processador retornar código diferente de zero; um arquivo que preprocessa
para o vazio é indistinguível de um arquivo sem qstrs.

## Detalhe adicional

A regra ninja de `genhdr/qstr.i.last` lista apenas os `.c` como dependência.
Alterar um header que muda o resultado do pré-processamento **não** dispara a
regeneração. Ao investigar isto, uma correção correta parecia não funcionar até
apagar `build/genhdr` à mão.

## Reprodução mínima

Um usermod com:

```c
// mymod.c
#if MYMOD_ENABLED
// ... funções e tabela de globals com MP_QSTR_*
MP_REGISTER_MODULE(MP_QSTR_mymod, mymod_user_cmodule);
#endif
```

```cmake
add_library(usermod_mymod INTERFACE)
target_sources(usermod_mymod INTERFACE ${CMAKE_CURRENT_LIST_DIR}/mymod.c)
target_compile_definitions(usermod_mymod INTERFACE MYMOD_ENABLED=1)
target_link_libraries(usermod INTERFACE usermod_mymod)
```

Compila pelo caminho Makefile (que passa `CFLAGS_USERMOD` aos dois estágios) e
falha pelo caminho CMake.

## Sugestões

1. **Coletar as definições.** Adicionar `INTERFACE_COMPILE_DEFINITIONS` ao
   `usermod_gather_sources()` e repassá-las ao passe de qstr, do mesmo modo que
   os diretórios de include já são repassados. É a correção que fecha a
   diferença entre os dois caminhos de build.
2. **Avisar em vez de silenciar.** `makeqstrdefs.py` poderia registrar quando um
   fonte listado não contribui nenhuma linha para `qstr.i.last`. Quase sempre
   isso é um erro de configuração, e hoje só se descobre pelo erro de
   compilação, que aponta para o lugar errado.
3. **Dependências de header na regra de qstr**, para que a regeneração ocorra
   quando um header incluído mudar.

A sugestão 1 resolve; a 2 teria economizado a maior parte do tempo de
diagnóstico aqui.

## Contorno aplicado

Definimos o macro por padrão no header de configuração do próprio módulo, que é
incluído antes do guard e está no caminho de include do passe de qstr. Ver
`sandman21vs/secp256k1-embedded` @ `micropython-master-api`.

## Ambiente

MicroPython `master` (8cf130db34, 1.30.0-preview), porta esp32, alvo esp32p4,
ESP-IDF v5.5.5, CMake 4.2.3, ninja 1.13.2.
