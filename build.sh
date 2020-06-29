#!/bin/bash
# mpy cross-compiler
pushd f469-disco/micropython/mpy-cross
make
popd
# f469 board
pushd f469-disco/micropython/ports/stm32
make BOARD=STM32F469DISC SKIP_USBINIT=1 MICROPY_HW_SDCARD_MOUNT_AT_BOOT=0 USER_C_MODULES=../../../usermods FROZEN_MANIFEST=../../../../manifest.py
arm-none-eabi-objcopy -O binary build-STM32F469DISC/firmware.elf ../../../../specter-diy.bin
popd
