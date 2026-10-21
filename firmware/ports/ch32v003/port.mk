# SPDX-License-Identifier: GPL-3.0-or-later
# CH32V003 port: make ch32v003 BOARD=example-ch32v003-buck
# Needs riscv64-unknown-elf-gcc / g++ (GCC 13 has the rv32ec multilib). Flash with a WCH-LinkE
# over the one-wire SWIO pin, e.g. minichlink -w build/ch32v003-<board>.bin flash -b

RV_CXX ?= riscv64-unknown-elf-g++
RV_OBJCOPY ?= riscv64-unknown-elf-objcopy
RV_SIZE ?= riscv64-unknown-elf-size
CH32_BOARD := $(if $(BOARD),$(BOARD),example-ch32v003-buck)
CH32_OUT := $(BUILD)/ch32v003-$(CH32_BOARD)
CH32_FLAGS := -march=rv32ec_zicsr -mabi=ilp32e -std=c++17 -Os -g -Wall -Wextra -ffreestanding \
              -fno-exceptions -fno-rtti -fno-threadsafe-statics -fno-use-cxa-atexit \
              -ffunction-sections -fdata-sections -msmall-data-limit=8 \
              -Iboards/$(CH32_BOARD) -Icore -Ihal
CH32_LDFLAGS := -nostartfiles -nostdlib -Wl,--gc-sections -T ports/ch32v003/link.ld
CH32_SRC := $(CORE_SRC) ports/ch32v003/hal_ch32v003.cpp ports/ch32v003/main.cpp

$(CH32_OUT).elf: $(CH32_SRC) ports/ch32v003/startup.S ports/ch32v003/link.ld ports/ch32v003/ch32v003_regs.h boards/$(CH32_BOARD)/board.h | $(BUILD)
	$(RV_CXX) $(CH32_FLAGS) $(CH32_LDFLAGS) -o $@ ports/ch32v003/startup.S $(CH32_SRC) -lgcc
	$(RV_SIZE) $@

$(CH32_OUT).bin: $(CH32_OUT).elf
	$(RV_OBJCOPY) -O binary $< $@

ch32v003: $(CH32_OUT).bin
