# MicroPython user C module: hashes que o Bitcoin precisa e o MicroPython nao traz.
#
# O MicroPython nativo oferece md5, sha1 e sha256. Faltam sha512 (BIP32 usa
# HMAC-SHA512) e ripemd160 (enderecos), alem de hmac_sha512 e pbkdf2_hmac
# (BIP39). Este modulo cobre isso.
#
# Vendorizado de miketlk/f469-disco @ micropython-upgrade,
# usermods/uhashlib -- a versao ja adaptada para a API moderna do MicroPython
# (MP_REGISTER_MODULE de dois argumentos). Os fontes em crypto/ vem da
# linhagem trezor-crypto, sob licenca BSD de tres clausulas, com os avisos de
# copyright preservados nos arquivos.
#
# Modificacao local: hashlib.c e uhmac.c ganharam um valor padrao para
# MODULE_HASHLIB_ENABLED, sem o qual o passe de qstr do caminho CMake produz
# um arquivo vazio. Ver reports/micropython-usermod-qstr-defines.md.

add_library(usermod_uhashlib INTERFACE)

target_sources(usermod_uhashlib INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}/hashlib.c
    ${CMAKE_CURRENT_LIST_DIR}/uhmac.c
    ${CMAKE_CURRENT_LIST_DIR}/crypto/ripemd160.c
    ${CMAKE_CURRENT_LIST_DIR}/crypto/sha2.c
    ${CMAKE_CURRENT_LIST_DIR}/crypto/hmac.c
    ${CMAKE_CURRENT_LIST_DIR}/crypto/pbkdf2.c
    ${CMAKE_CURRENT_LIST_DIR}/crypto/memzero.c
)

target_include_directories(usermod_uhashlib INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}
    ${CMAKE_CURRENT_LIST_DIR}/crypto
)

target_link_libraries(usermod INTERFACE usermod_uhashlib)
