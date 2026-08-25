# MicroPython user C module: LVGL 9.3 e o modulo `udisplay` para a Waveshare 4.3-C.
#
# Reaproveita duas coisas do bundle f469-disco @ micropython-upgrade em vez de
# recriar:
#
#   * lvgl/          -- LVGL v9.3.0 vendorizado (fork miketlk/lvgl com o QR
#                       code estendido que o Specter usa)
#   * lv_mpy.c       -- o binding MicroPython do LVGL, ja GERADO. Sao 47 mil
#                       linhas produzidas por lv_binding_micropython a partir
#                       dos headers; regenerar exigiria rodar o gerador com
#                       pycparser. Como o binding e independente de plataforma,
#                       o gerado serve.
#   * fonts/         -- roboto mono 12/16/22/28 e a fonte square, referenciadas
#                       pelo codigo da GUI.
#
# O que e nosso: lv_conf.h (RGB565 em vez de ARGB8888), lv_p4_hal.c (ligacao ao
# painel e ao touch) e moddisplay.c (a superficie Python).

set(BUNDLE_DIR ${CMAKE_CURRENT_LIST_DIR}/../../../../f469-disco/usermods/udisplay_f469)
cmake_path(NORMAL_PATH BUNDLE_DIR)

if(NOT EXISTS ${BUNDLE_DIR}/lv_mpy.c)
    message(FATAL_ERROR
        "Bundle do LVGL nao encontrado em ${BUNDLE_DIR}. "
        "Rode: git submodule update --init --recursive f469-disco")
endif()

add_library(usermod_lvgl_p4 INTERFACE)

# Nucleo do LVGL. O upstream nao expoe uma lista de fontes para CMake, entao
# varremos src/ -- e o mesmo que lvgl.mk faz do lado Makefile.
file(GLOB_RECURSE LVGL_SOURCES ${BUNDLE_DIR}/lvgl/src/*.c)
file(GLOB LVGL_FONTS ${BUNDLE_DIR}/fonts/*.c)

target_sources(usermod_lvgl_p4 INTERFACE
    ${LVGL_SOURCES}
    ${LVGL_FONTS}
    ${CMAKE_CURRENT_LIST_DIR}/lv_p4_hal.c
    ${CMAKE_CURRENT_LIST_DIR}/moddisplay.c
)

target_include_directories(usermod_lvgl_p4 INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}
    ${BUNDLE_DIR}
    ${BUNDLE_DIR}/lvgl
    ${CMAKE_CURRENT_LIST_DIR}/../p4board
)

target_compile_definitions(usermod_lvgl_p4 INTERFACE
    LV_CONF_INCLUDE_SIMPLE=1
)

# O LVGL gera muitos avisos de conversao com -Wextra e o binding gerado tem
# funcoes sem uso por configuracao. Nao sao codigo nosso.
target_compile_options(usermod_lvgl_p4 INTERFACE
    -Wno-unused-function
    -Wno-error=unused-function
    -Wno-error=sign-compare
    -Wno-error=missing-field-initializers
)

target_link_libraries(usermod INTERFACE usermod_lvgl_p4)
