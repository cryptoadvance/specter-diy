# Ambiente de build do baseline MicroPython para ESP32-P4.
#
#   . ports/esp32p4/tools/env.sh
#
# Reaproveita o ESP-IDF e o toolchain ja instalados para o bootloader, sem
# tocar em ~/esp nem ~/.espressif usados por outros projetos.

export IDF_TOOLS_PATH=/home/sm/.espressif-specter-p4
export MICROPYTHON_DIR=/home/sm/micropython-p4
export SPECTER_BOOTLOADER_DIR=/home/sm/specter-bootloader

# ESP-IDF v5.5.5, pinado como submodulo do specter-bootloader.
# Nao esta na lista oficialmente suportada pelo MicroPython (5.3-5.5.4), mas
# compila o alvo esp32p4 sem erro -- verificado nesta arvore.
. "$SPECTER_BOOTLOADER_DIR/third_party/esp-idf/export.sh" > /dev/null 2>&1

# A placa e ESP32-P4 revisao v1.3 (chip_revision 103 = major 1, minor 3).
# O board.md do MicroPython exige a variante PRE_REV3 para revisoes 0.x e 1.x;
# o build padrao mira revisao 3.0+ e nao sobe neste silicio.
export MP_BOARD=WAVESHARE_P4_43
export MP_BOARD_DIR=/home/sm/specter-diy/ports/esp32p4/boards/WAVESHARE_P4_43
export MP_USER_C_MODULES=/home/sm/specter-diy/ports/esp32p4/components/micropython.cmake

# Componentes ESP-IDF de verdade. Necessarios para dependencias gerenciadas: o
# MicroPython so le idf_component.yml de ports/esp32/main/, e um usermod nao
# pode declarar as suas.
export MP_EXTRA_COMPONENTS=/home/sm/specter-diy/ports/esp32p4/idf_components

# O board ja embute sdkconfig.p4_pre_rev3, entao nao ha variante a passar.
# ESP32P4_REV_MIN_0 cobre o silicio v1.3 desta placa e tambem o 3.x.

# Sem variante de WiFi de proposito: a placa tem um ESP32-C6, mas o alvo e um
# dispositivo airgapped. O radio fica de fora do build e, mais adiante, sera
# mantido em reset por hardware via GPIO 54.

echo "ESP32-P4 baseline:"
echo "  IDF            = $(idf.py --version 2>&1 | tail -1)"
echo "  IDF_TOOLS_PATH = $IDF_TOOLS_PATH"
echo "  BOARD          = $MP_BOARD"
