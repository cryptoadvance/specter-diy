#!/usr/bin/env bash
# Compila e, opcionalmente, grava o baseline MicroPython na Waveshare 4.3-C.
#
#   ./build-baseline.sh build
#   PORT=/dev/ttyACM0 ./build-baseline.sh flash
#
# Na primeira vez rode tambem:
#   make -C "$MICROPYTHON_DIR/mpy-cross" -j"$(nproc)"
#   make -C "$MICROPYTHON_DIR/ports/esp32" BOARD=$MP_BOARD BOARD_VARIANT=$MP_VARIANT submodules

set -euo pipefail
. "$(dirname -- "$0")/env.sh" > /dev/null

BUILD_DIR="$MICROPYTHON_DIR/ports/esp32/build-P4"
PY="$IDF_TOOLS_PATH/python_env/idf5.5_py3.14_env/bin/python"

case "${1:-build}" in
  build)
    cd "$MICROPYTHON_DIR/ports/esp32"
    idf.py -D MICROPY_BOARD="$MP_BOARD" -D MICROPY_BOARD_VARIANT="$MP_VARIANT" \
           -B build-P4 build
    ;;
  flash)
    # idf.py flash falha aqui: o wrapper procura components/esptool_py/esptool.py,
    # que nao existe mais nesta versao (esptool virou pacote pip). Chamamos o
    # modulo direto, com os offsets do proprio flash_args do build.
    cd "$BUILD_DIR"
    "$PY" -m esptool --chip esp32p4 -p "${PORT:?defina PORT=/dev/ttyACM0}" \
      -b 460800 --before default_reset --after hard_reset \
      write_flash --flash_mode dio --flash_freq 40m --flash_size 16MB \
      0x2000   bootloader/bootloader.bin \
      0x8000   partition_table/partition-table.bin \
      0x10000  micropython.bin
    ;;
  *)
    echo "uso: $0 {build|flash}" >&2; exit 2
    ;;
esac
