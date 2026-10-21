# SPDX-License-Identifier: GPL-3.0-or-later
# LuxLibre firmware build.
#
#   make test                         unit + behaviour tests on the PC (needs g++)
#   make sim [BOARD=<board>]          the PC simulator (build/luxsim, or build/luxsim-<board>)
#   make docs                         regenerate docs/firmware/parameters.md and user-interface.md
#   make tiny1616 BOARD=<board>       ATtiny1616 firmware (needs avr-gcc), e.g. example-tiny1616-pwm
#   make ch32v003 BOARD=<board>       CH32V003 firmware (needs riscv64-unknown-elf-gcc)
#   ESP32-C3: see ports/esp32c3/README.md (ESP-IDF, idf.py build)

CORE_SRC := core/lx_params.cpp core/lx_ramp.cpp core/lx_input.cpp core/lx_thermal.cpp \
            core/lx_battery.cpp core/lx_aux.cpp core/lx_storage.cpp core/lx_ui.cpp \
            core/lx_console.cpp core/lx_light.cpp
BUILD := build

# ---------------------------------------------------------------- PC (host)
HOST_CXX ?= g++
HOST_FLAGS := -std=c++17 -O2 -g -Wall -Wextra -Wshadow -Werror -DLX_HOST

.PHONY: all test sim docs clean tiny1616 tiny1616-fuses ch32v003 size

all: test

$(BUILD):
	mkdir -p $(BUILD)

$(BUILD)/test_units: tests/test_units.cpp $(CORE_SRC) ports/host/sim.cpp | $(BUILD)
	$(HOST_CXX) $(HOST_FLAGS) -Iboards/host-sim -Icore -o $@ tests/test_units.cpp $(CORE_SRC) ports/host/sim.cpp

$(BUILD)/test_sim: tests/test_sim.cpp $(CORE_SRC) ports/host/sim.cpp | $(BUILD)
	$(HOST_CXX) $(HOST_FLAGS) -Iboards/host-sim -Icore -o $@ tests/test_sim.cpp $(CORE_SRC) ports/host/sim.cpp

$(BUILD)/test_basic: tests/test_basic.cpp $(CORE_SRC) ports/host/sim.cpp | $(BUILD)
	$(HOST_CXX) $(HOST_FLAGS) -Iboards/host-sim-basic -Icore -o $@ tests/test_basic.cpp $(CORE_SRC) ports/host/sim.cpp

test: $(BUILD)/test_units $(BUILD)/test_sim $(BUILD)/test_basic
	./$(BUILD)/test_units
	./$(BUILD)/test_sim
	./$(BUILD)/test_basic

# make sim                 -> build/luxsim with the full-featured host-sim board
# make sim BOARD=<board>   -> build/luxsim-<board>: the simulator with a real board header
SIM_BOARD := $(if $(BOARD),$(BOARD),host-sim)
SIM_OUT := $(if $(BOARD),$(BUILD)/luxsim-$(BOARD),$(BUILD)/luxsim)

$(SIM_OUT): tools/luxsim.cpp $(CORE_SRC) ports/host/sim.cpp boards/$(SIM_BOARD)/board.h | $(BUILD)
	$(HOST_CXX) $(HOST_FLAGS) -Iboards/$(SIM_BOARD) -Icore -o $@ tools/luxsim.cpp $(CORE_SRC) ports/host/sim.cpp

sim: $(SIM_OUT)

$(BUILD)/gen_docs: tools/gen_docs.cpp $(CORE_SRC) ports/host/sim.cpp | $(BUILD)
	$(HOST_CXX) $(HOST_FLAGS) -Iboards/host-sim -Icore -o $@ tools/gen_docs.cpp $(CORE_SRC) ports/host/sim.cpp

docs: $(BUILD)/gen_docs
	./$(BUILD)/gen_docs ../docs/firmware

clean:
	rm -rf $(BUILD)

# ---------------------------------------------------------------- MCU ports
include ports/attiny1616/port.mk
include ports/ch32v003/port.mk
