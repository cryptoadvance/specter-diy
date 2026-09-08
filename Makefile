TARGET_DIR = bin
BOARD ?= STM32F469DISC
FLAVOR ?= SPECTER
USER_C_MODULES ?= ../../../usermods
MPY_DIR ?= f469-disco/micropython
EMBIT_INIT ?= f469-disco/libs/common/embit/src/embit/__init__.py
ifeq ($(shell uname),Linux)
    MPY_CFLAGS ?= -Wno-dangling-pointer -Wno-enum-int-mismatch
else
    MPY_CFLAGS ?=
endif
FROZEN_MANIFEST_DISCO ?= ../../../../manifests/disco.py
FROZEN_MANIFEST_DEBUG ?= ../../../../manifests/debug.py
FROZEN_MANIFEST_UNIX ?= ../../../../manifests/unix.py
DEBUG ?= 0
USE_DBOOT ?= 0
REPRODUCIBLE ?= 0
GIT_INFO ?= src/git_info.py

$(TARGET_DIR):
	mkdir -p $(TARGET_DIR)

# check submodules
$(MPY_DIR)/mpy-cross/Makefile:
	git submodule update --init --recursive

$(EMBIT_INIT): | $(MPY_DIR)/mpy-cross/Makefile
	git submodule update --init --recursive

# cross-compiler
mpy-cross: $(TARGET_DIR) $(MPY_DIR)/mpy-cross/Makefile $(EMBIT_INIT)
	@echo Building cross-compiler
	make -C $(MPY_DIR)/mpy-cross \
        DEBUG=$(DEBUG) \
        CFLAGS_EXTRA="$(MPY_CFLAGS)" && \
	cp $(MPY_DIR)/mpy-cross/mpy-cross $(TARGET_DIR)

# embed git metadata for firmware builds
.PHONY: git-info
git-info:
	./tools/embed_git_info.py $(if $(filter 1,$(REPRODUCIBLE)),--reproducible) $(GIT_INFO)

# disco board with bitcoin library
disco: $(TARGET_DIR) mpy-cross $(MPY_DIR)/ports/stm32 git-info
	@echo Building firmware
	make -C $(MPY_DIR)/ports/stm32 \
        BOARD=$(BOARD) \
        FLAVOR=$(FLAVOR) \
        USE_DBOOT=$(USE_DBOOT) \
        USER_C_MODULES=$(USER_C_MODULES) \
        FROZEN_MANIFEST=$(FROZEN_MANIFEST_DISCO) \
        DEBUG=$(DEBUG) \
        CFLAGS_EXTRA="$(MPY_CFLAGS)" && \
	arm-none-eabi-objcopy -O binary \
        $(MPY_DIR)/ports/stm32/build-STM32F469DISC/firmware.elf \
        $(TARGET_DIR)/specter-diy.bin && \
        cp $(MPY_DIR)/ports/stm32/build-STM32F469DISC/firmware.hex \
                $(TARGET_DIR)/specter-diy.hex

# disco board with bitcoin library
debug: $(TARGET_DIR) mpy-cross $(MPY_DIR)/ports/stm32 git-info
	@echo Building firmware
	make -C $(MPY_DIR)/ports/stm32 \
        BOARD=$(BOARD) \
        FLAVOR=$(FLAVOR) \
        USE_DBOOT=$(USE_DBOOT) \
        USER_C_MODULES=$(USER_C_MODULES) \
        FROZEN_MANIFEST=$(FROZEN_MANIFEST_DEBUG) \
        DEBUG=$(DEBUG) \
        CFLAGS_EXTRA="$(MPY_CFLAGS)" && \
	arm-none-eabi-objcopy -O binary \
        $(MPY_DIR)/ports/stm32/build-STM32F469DISC/firmware.elf \
        $(TARGET_DIR)/debug.bin && \
	cp $(MPY_DIR)/ports/stm32/build-STM32F469DISC/firmware.hex \
        $(TARGET_DIR)/debug.hex


# unixport (simulator)
unix: $(TARGET_DIR) mpy-cross $(MPY_DIR)/ports/unix git-info
	@echo Building binary with frozen files
	make -C $(MPY_DIR)/ports/unix \
        USER_C_MODULES=$(USER_C_MODULES) \
        FROZEN_MANIFEST=$(FROZEN_MANIFEST_UNIX) \
        CFLAGS_EXTRA="$(MPY_CFLAGS)" && \
	cp $(MPY_DIR)/ports/unix/micropython $(TARGET_DIR)/micropython_unix

simulate: unix
	$(TARGET_DIR)/micropython_unix simulate.py

frozen-import-smoke: unix
	cd /tmp && $(abspath $(TARGET_DIR)/micropython_unix) -c 'import asyncio; import asyncio.core; import microur.encoder; import microur.decoder; import microur.util.bytewords; import embit.bip39; import embit.bip85; import embit.compact; import embit.ec; import embit.hashes; import embit.networks; import embit.psbt; import embit.psbtview; import embit.script; import embit.transaction; import embit.descriptor; import embit.descriptor.arguments; import embit.descriptor.checksum; import embit.liquid; import embit.liquid.addresses; import embit.liquid.descriptor; import embit.liquid.networks; import embit.liquid.pset; import embit.liquid.psetview; import embit.liquid.slip77; import embit.liquid.transaction'

test: unix frozen-import-smoke
	cd test && ../$(TARGET_DIR)/micropython_unix run_tests.py

all: mpy-cross disco unix

clean:
	rm -rf $(TARGET_DIR)
	make -C $(MPY_DIR)/mpy-cross clean
	make -C $(MPY_DIR)/ports/unix \
		USER_C_MODULES=$(USER_C_MODULES) \
		FROZEN_MANIFEST=$(FROZEN_MANIFEST_UNIX) clean
	make -C $(MPY_DIR)/ports/stm32 \
		BOARD=$(BOARD) \
		USER_C_MODULES=$(USER_C_MODULES) \
		FROZEN_MANIFEST=$(FROZEN_MANIFEST_DISCO) clean

.PHONY: all clean git-info frozen-import-smoke
