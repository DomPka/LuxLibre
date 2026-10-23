<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
[LuxLibre](../README.md) › Firmware

# LuxLibre firmware: source code

This folder is the source code of the LuxLibre firmware. **What the firmware does and how to use it** is explained in
[docs/firmware/](../docs/firmware/README.md); this page only says where things are.

| Folder | What is in it |
|---|---|
| [core/](core/) | the firmware itself, the same on every light: levels and ramp (`lx_ramp`), button gestures and the user interface (`lx_ui`), output (`lx_light`), thermal regulator (`lx_thermal`), battery (`lx_battery`), parameters (`lx_params`, the list in `lx_params_list.h`), storage, console, indicator and side lights (`lx_aux`), colour beam (`lx_color`), version (`lx_version.h`) |
| [hal/](hal/) | the hardware interface every port implements (`lx_hal.h`) |
| [ports/](ports/README.md) | one folder per microcontroller: ATtiny1616, CH32V003, ESP32-C3, and `host` (the PC build behind the simulator and the tests) |
| [boards/](boards/README.md) | one `board.h` per light: pins, LED, driver, limits, default settings and the thermal model for the simulator |
| [tests/](tests/) | unit tests and behaviour tests that run in the simulator |
| [tools/](tools/) | `luxsim` (the simulator), `gen_docs` (writes the parameter and button pages) and `plot_sim.py` |
| [Makefile](Makefile) | `make test`, `make sim BOARD=<name>`, `make docs` |

Quick start, from this folder (Linux, macOS, or Windows with WSL):

```sh
make test                                   # unit and behaviour tests
make sim BOARD=edco-prism                   # the simulator with one light's board header
build/luxsim-edco-prism --preset board "2C W600000"
```

More: [building and flashing](../docs/firmware/README.md#building), [the simulator](../docs/firmware/simulator.md),
[adding a board or a microcontroller](../docs/firmware/porting.md), [every parameter](../docs/firmware/parameters.md),
[every button gesture](../docs/firmware/user-interface.md).
