# Waveshare ESP32-P4-WIFI6-Touch-LCD-4.3-C
#
# A revisao de silicio testada e v1.3 (chip_revision 103 no encoding do
# ESP-IDF: major*100 + minor). O board.md do MicroPython exige as variantes
# PRE_REV3 para revisoes 0.x e 1.x, entao sdkconfig.p4_pre_rev3 entra sempre --
# nao como variante opcional. Ele define ESP32P4_REV_MIN_0, que tambem cobre
# silicio 3.x, logo este board serve as duas familias.
#
# Sem variante de WiFi de proposito: a placa carrega um ESP32-C6, mas o alvo e
# um dispositivo airgapped e o radio fica fora do build.

set(IDF_TARGET esp32p4)

set(SDKCONFIG_DEFAULTS
    boards/sdkconfig.base
    boards/sdkconfig.p4
    boards/sdkconfig.p4_pre_rev3
    ${CMAKE_CURRENT_LIST_DIR}/sdkconfig.board
)
