# MicroPython user C module: libsecp256k1-zkp bindings.
#
# Traducao do micropython.mk de miketlk/secp256k1-embedded @ micropython-upgrade
# para o build CMake da porta esp32. O upstream so tem a variante Makefile, que
# a porta esp32 nao usa.
#
# A branch micropython-upgrade e a que ja foi adaptada para a API moderna do
# MicroPython (MP_ERROR_TEXT, criacao de string nova, MP_REGISTER_MODULE de dois
# argumentos). A master do mesmo repo ainda usa a forma de tres argumentos e nao
# compila aqui.
#
# Configuracao herdada de mpy/config/libsecp256k1-config.h: campo 10x26 e
# escalar 8x32, ou seja, a implementacao de 32 bits -- correta para o RISC-V do
# ESP32-P4. Modulos habilitados: ECDH, extrakeys, schnorrsig, recovery,
# generator, rangeproof (com prealocacao) e surjectionproof.

set(SECP256K1_DIR ${CMAKE_CURRENT_LIST_DIR}/secp256k1)

add_library(usermod_secp256k1 INTERFACE)

target_sources(usermod_secp256k1 INTERFACE
    ${SECP256K1_DIR}/mpy/config/secp256k1_build.c
    ${SECP256K1_DIR}/mpy/config/ext_callbacks.c
    ${SECP256K1_DIR}/mpy/libsecp256k1.c
)

target_include_directories(usermod_secp256k1 INTERFACE
    ${SECP256K1_DIR}/secp256k1
    ${SECP256K1_DIR}/secp256k1/src
    ${SECP256K1_DIR}/mpy/config
)

target_compile_definitions(usermod_secp256k1 INTERFACE
    HAVE_CONFIG_H
    MODULE_SECP256K1_ENABLED=1
)

# libsecp256k1 e compilada como uma unidade de traducao unica (secp256k1_build.c
# faz include de secp256k1.c), o que deixa muitas funcoes estaticas sem uso em
# cada configuracao. O upstream silencia tudo com -w; mantemos o mesmo conjunto
# para nao divergir do que a biblioteca espera.
target_compile_options(usermod_secp256k1 INTERFACE
    -Wno-unused-function
    -Wno-error=unused-function
)

target_link_libraries(usermod INTERFACE usermod_secp256k1)
