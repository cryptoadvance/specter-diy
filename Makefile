TARGET_DIR = bin
BOARD ?= STM32F469DISC
FLAVOR ?= SPECTER
USER_C_MODULES ?= ../../../usermods
MPY_DIR ?= f469-disco/micropython
FROZEN_MANIFEST_DISCO ?= ../../../../manifests/disco.py
FROZEN_MANIFEST_DEBUG ?= ../../../../manifests/debug.py
FROZEN_MANIFEST_UNIX ?= ../../../../manifests/unix.py
DEBUG ?= 0
USE_DBOOT ?= 0
GIT_INFO ?= src/git_info.py

$(TARGET_DIR):
	mkdir -p $(TARGET_DIR)

# check submodules
$(MPY_DIR)/mpy-cross/Makefile:
	git submodule update --init --recursive

# cross-compiler
mpy-cross: $(TARGET_DIR) $(MPY_DIR)/mpy-cross/Makefile
	@echo Building cross-compiler
	make -C $(MPY_DIR)/mpy-cross \
	DEBUG=$(DEBUG) && \
	cp $(MPY_DIR)/mpy-cross/mpy-cross $(TARGET_DIR)

# embed git metadata for firmware builds
.PHONY: git-info
git-info:
	./tools/embed_git_info.py $(GIT_INFO)

# disco board with bitcoin library
disco: $(TARGET_DIR) mpy-cross $(MPY_DIR)/ports/stm32 git-info
	@echo Building firmware
	make -C $(MPY_DIR)/ports/stm32 \
		BOARD=$(BOARD) \
		FLAVOR=$(FLAVOR) \
		USE_DBOOT=$(USE_DBOOT) \
		USER_C_MODULES=$(USER_C_MODULES) \
		FROZEN_MANIFEST=$(FROZEN_MANIFEST_DISCO) \
		DEBUG=$(DEBUG) && \
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
		DEBUG=$(DEBUG) && \
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
		FROZEN_MANIFEST=$(FROZEN_MANIFEST_UNIX) && \
	cp $(MPY_DIR)/ports/unix/micropython $(TARGET_DIR)/micropython_unix

simulate: unix
	$(TARGET_DIR)/micropython_unix simulate.py

test: unix
	$(TARGET_DIR)/micropython_unix tests/run_tests.py

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

.PHONY: all clean git-info
