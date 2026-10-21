# SPDX-License-Identifier: GPL-3.0-or-later
# ATtiny1616 port: make tiny1616 BOARD=example-tiny1616-pwm
# Needs avr-gcc (7.3 or newer) and binutils-avr. avr-libc headers are not required for the
# chip (tiny1x_io.h replaces them); start-up code is in crt_avrxmega3.S.
# Flash with a UPDI programmer, e.g.:  pymcuprog write -t uart -u /dev/ttyUSB0 -d attiny1616 -f build/tiny1616-<board>.hex --erase

AVR_CXX ?= avr-g++
AVR_OBJCOPY ?= avr-objcopy
AVR_SIZE ?= avr-size
TINY_BOARD := $(if $(BOARD),$(BOARD),example-tiny1616-pwm)
TINY_OUT := $(BUILD)/tiny1616-$(TINY_BOARD)
TINY_FLAGS := -mmcu=attiny1616 -std=c++17 -Os -g -Wall -Wextra -Wno-cpp -fno-exceptions -fno-rtti \
              -fno-threadsafe-statics -ffunction-sections -fdata-sections -flto \
              -Iboards/$(TINY_BOARD) -Icore
TINY_LDFLAGS := -nostartfiles -nodefaultlibs -Wl,--gc-sections -flto
TINY_SRC := $(CORE_SRC) ports/attiny1616/hal_attiny1616.cpp ports/attiny1616/main.cpp

$(TINY_OUT).elf: $(TINY_SRC) ports/attiny1616/crt_avrxmega3.S ports/attiny1616/tiny1x_io.h boards/$(TINY_BOARD)/board.h | $(BUILD)
	$(AVR_CXX) $(TINY_FLAGS) $(TINY_LDFLAGS) -o $@ ports/attiny1616/crt_avrxmega3.S $(TINY_SRC) -lgcc -lc -lgcc
	$(AVR_SIZE) $@

$(TINY_OUT).hex: $(TINY_OUT).elf
	$(AVR_OBJCOPY) -O ihex -R .eeprom $< $@

tiny1616: $(TINY_OUT).hex

# Brown-out detector (design rule DRV-8). On the tinyAVR 1-series it is configured only by the
# BODCFG fuse (offset 1), which is 0x00 (off) from the factory; the firmware cannot enable it.
# 0x44 = level 2.6 V (BODLEVEL2), enabled while running, off in power-down (no sleep current).
# Write it once per chip:  make tiny1616-fuses UPDI_PORT=/dev/ttyUSB0
TINY_BODCFG ?= 0x44
UPDI_PORT ?= /dev/ttyUSB0
tiny1616-fuses:
	pymcuprog write -t uart -u $(UPDI_PORT) -d attiny1616 -m fuses -o 1 -l $(TINY_BODCFG)
