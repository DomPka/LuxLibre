<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
# The simulator

The LuxLibre firmware runs unchanged on a PC against a simulated flashlight: a cell, an LED
with its driver, a body that heats up and cools down, a temperature sensor with lag and noise,
and a USB charger. The same simulation runs the behaviour tests (`make test`) and the
command-line tool `luxsim`, which answers questions such as "how long does turbo last?" or
"what happens on a hot day?" before any hardware exists.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../img/thermal-regulation-dark.png">
  <img alt="Simulated turbo for two lights: output (top) steps down smoothly as the sensor temperature (bottom) reaches the 50 °C limit, then holds about 250 lm for the keychain and 380 lm for the 18650 light" src="../img/thermal-regulation-light.png">
</picture>

*Turbo without a timer, 25 °C still air: the keychain model at 2.2 A (blue) and the 18650 model
at 5 A (orange). Output holds until the predicted sensor temperature reaches `THM_LIMIT`, then
the regulator steps down without oscillating.*

The simulator is a model with round numbers, not a measurement. Use it to compare designs and
settings, to test firmware changes, and to plan the tests; publish only measured values
([REQ-2](../design-rules.md#req-2)).

## Running luxsim

```sh
cd firmware
make sim                                        # builds build/luxsim
build/luxsim --csv turbo.csv --set TURBO_S=0 "2C W600000"
```

```text
simulated 602.7 s
peak output        783 lm
output at 30 s     757 lm   (ANSI FL 1 measures from 30 s)
output at 120 s    522 lm
peak sensor       51.0 degC
final           level 128, 252 lm, 50.0 degC, 3.95 V, 82 %
log written to turbo.csv
```

### The script

The last argument is a time line of button presses and events, separated by spaces:

| Token | Meaning |
|---|---|
| `2C` | 2 quick clicks (any number: `1C`, `3C`, `4C`, `9C`) |
| `H1500` | hold the button for 1500 ms |
| `CH3000` | one click, then hold for 3000 ms (laser or momentary gesture) |
| `W60000` | wait 60 s |
| `USB1`, `USB0` | plug in or unplug USB power |
| `AMB40` | ambient temperature becomes 40 °C |

### Options

| Option | Meaning |
|---|---|
| `--preset keychain` / `--preset 18650` / `--preset board` | body and cell model (table below); default keychain, or `board` when the board header has a model of its own |
| `--ambient C` | ambient temperature at the start (default 25 °C) |
| `--soc 0..1` | state of charge at the start (default 1.0 = full) |
| `--capacity mAh` | cell capacity |
| `--imax A` | LED current at level 150 |
| `--noise C`, `--step C` | temperature sensor noise (peak) and resolution |
| `--set NAME=VALUE` | set a firmware parameter before the script starts (repeatable) |
| `--csv FILE` | write the log, one row every 100 ms |
| `--extra MS` | keep running after the script (default 2000 ms) |

### Examples

```sh
# Runtime of the keychain model at level 120 (about 180 lm): the log shows about 2 h until
# the output falls below 10 % of the 30 s value
build/luxsim --csv run.csv --set MEMORY=0 --set MEM_LEVEL=120 "1C W14400000"

# The same light on a hot day, turbo:
build/luxsim --ambient 40 "2C W600000"

# A nearly empty cell: warning, step-down, cut-off
build/luxsim --soc 0.06 --capacity 150 --set TURBO_S=0 "2C W900000"

# Charging for an hour, then unplugged and switched on
build/luxsim --soc 0.3 "USB1 W3600000 USB0 1C W60000"

# Is the thermal regulator calm with a coarse, noisy sensor (1 °C steps)?
build/luxsim --noise 0.4 --step 1 --csv coarse.csv --set TURBO_S=0 "2C W600000"
```

## Simulating your own board

`make sim BOARD=<board>` builds the simulator with your board header instead of the generic
host board. The LED and driver model of the header (`LX_MAIN_MAX_MA`, `LX_LED_VF0_MV`,
`LX_LED_RS_MOHM`, `LX_DRIVER_EFF_PCT`) then replaces the preset's, and all your `LX_DEF_`
defaults apply. The preset still sets the body and the cell:

```sh
make sim BOARD=flashka-keychain-v05            # or flashka-keychain-v06: the same model
build/luxsim-flashka-keychain-v05 "2C W200000"

make sim BOARD=example-ch32v003-buck
build/luxsim-example-ch32v003-buck --preset 18650 --set TURBO_S=0 "2C W600000"
```

A header can also describe its own body, cell and LED: the `board` preset. The `LX_SIM_` macros
go together, and a header that has them gets `board` as its default preset. The flux table and
the optic factor are optional; whatever the header does not describe keeps the keychain value:

| Macro | Meaning |
|---|---|
| `LX_SIM_CAPACITY_MAH`, `LX_SIM_RINT_MOHM` | cell capacity and resistance of the whole cell path |
| `LX_SIM_C_HEAD_MJ`, `LX_SIM_C_BODY_MJ` | heat capacities of head and body, mJ/K |
| `LX_SIM_R_HEAD_BODY_MK`, `LX_SIM_R_BODY_AMB_MK` | head to body and body to air, mK/W |
| `LX_SIM_SENSOR_TAU_MS` | sensor lag |
| `LX_SIM_OCV_V` | optional: the cell's own open-circuit curve, 13 values in V at 0, 3, 5, 10, 20, 30 ... 100 % (default: the built-in NMC curve) |
| `LX_SIM_DROP_MOHM` | optional: resistance from the battery (under load) to the LED when the driver runs at 100 % duty, mΩ; the LED current is then at most (V - Vf0) / (Rs + this), so the light dims as the cell sags (default: not modelled) |
| `LX_LED_LM_MA`, `LX_LED_LM` | flux table of the LED: currents in mA and lumens at the LED (the datasheet's rating temperature), same number of points |
| `LX_OPTIC_PCT` | part of the light that leaves the front (optic, window), in % |

The FlashKa Keychain v0.7 header
([boards/flashka-keychain-v07/board.h](../../firmware/boards/flashka-keychain-v07/board.h))
has all of them, from the housing CAD and the LED and optic datasheets:

```sh
make sim BOARD=flashka-keychain-v07
build/luxsim-flashka-keychain-v07 --csv v07.csv "2C W3600000"
```

```text
simulated 3602.7 s
peak output       1111 lm
output at 30 s    1111 lm   (ANSI FL 1 measures from 30 s)
output at 120 s    545 lm
peak sensor       51.0 degC
final           level 123, 349 lm, 50.1 degC, 3.67 V, 58 %
(lumens are at the LED; out of the front x 0.87: peak 966 lm, final 304 lm)
```

The simulated light has one button. On a board with several buttons on one pin (a resistor
ladder, such as the FlashKa Keychain v0.6) it is the main button: the ESP32-C3 port ignores the
others ([porting.md](porting.md#resistor-ladder-buttons-esp32-c3)).

This is the first test of a new board header ([FW-2](../design-rules.md#fw-2)): turbo must step
down, the low-voltage protection must end in a cut-off, and the settled temperature must sit at
`THM_LIMIT`.

## The log and plots

The CSV has one row per 100 ms with the columns `t_s`, `level`, `led_A`, `lumens`,
`T_sensor_C`, `T_body_C`, `V_pack`, `SoC_pct`, `laser` and `lumens_front` (the light out of the
front: `lumens` times the optic factor of the board header, the same as `lumens` without one).
Open it in a spreadsheet, or plot output and temperature with:

```sh
python3 tools/plot_sim.py turbo.png turbo.csv:"Keychain" --limit 50
python3 tools/plot_sim.py turbo-dark.png turbo.csv:"Keychain" --limit 50 --dark
python3 tools/plot_sim.py run.png run.csv:"Memory level" --title "Runtime" --xlabel "Time (min)"
```

The plot has two panels with a shared time axis (light output above, sensor temperature below)
and uses colours that stay distinguishable for colour-blind readers, in a light and a dark
version. Measurements written in the same CSV format (at least `t_s`, `lumens`, `T_sensor_C`)
can be plotted next to a simulation ([testing.md](../testing.md#output-and-runtime)).

## The models

| | keychain preset | 18650 preset | FlashKa v0.7 header (`board`) |
|---|---|---|---|
| Cell | 800 mAh, 0.12 Ω | 3000 mAh, 0.05 Ω | one 14500 cell (Vapcell F15): 1500 mAh, 0.132 Ω, its own curve (3.68 V at 50 %); driver headroom 0.128 Ω |
| LED at level 150 | 2.2 A | 5.0 A | 2.85 A |
| LED voltage | 2.75 V + 0.15 Ω × I | 2.80 V + 0.10 Ω × I | 2.80 V + 0.15 Ω × I |
| Driver efficiency | 90 % | 90 % | 87 % |
| Light | 400 lm/A, droop 5 %/A | 380 lm/A, droop 3 %/A | flux table (SST-20 Gen 2 at Tj 85 °C), optic 87 % |
| Head: heat capacity | 8 J/K | 20 J/K | 7.06 J/K |
| Body: heat capacity | 19 J/K | 52 J/K | 21.07 J/K (the cell's 22 J/K, weakly coupled, is not in this model) |
| Head to body | 2.0 K/W | 1.0 K/W | 2.2 K/W |
| Body to air | 13 K/W (about 68 cm², h ≈ 11 W/m²K) | 8.5 K/W | 13.2 K/W (68.9 cm² of aluminium, h ≈ 11 W/m²K) |
| Sensor lag | 4 s | 3 s | 4 s |
| Sensor noise | 0.2 °C peak | 0.2 °C peak | 0.2 °C peak |

- **Cell:** open-circuit voltage from a typical NMC curve (4.20 V full, 3.30 V at 3 %, 2.70 V
  empty) or the header's own (`LX_SIM_OCV_V`) times the number of cells, minus the internal
  resistance times the current; the charge is counted in mAh. With `LX_SIM_DROP_MOHM` the driver
  runs out of headroom when the cell sags: the LED gets less than the set current.
- **LED and driver:** the current is the output fraction times the full-scale current; LED
  power = current × (Vf0 + Rs × current); input power = LED power / efficiency.
- **Light:** lumens = current × lm/A × (1 - droop × current) × (1 - 0.003 per °C above 25 °C at
  the head). With a flux table (`LX_LED_LM_MA`, `LX_LED_LM`) the lumens are straight lines
  between its points instead, at the table's rating temperature (no temperature factor); the
  light out of the front is that times the optic factor.
- **Heat:** the input power minus 30 % of the LED power (the light that leaves) heats the head;
  heat flows to the body and from the body to the air (convection plus radiation as one
  resistance, [THM-2](../design-rules.md#thm-2)).
- **Sensor:** follows the head temperature with a first-order lag, plus repeatable noise,
  rounded to the resolution.
- **USB:** a constant charge current (0.3 A) that tapers above 90 %, only while the firmware
  enables the charger.

To model your own light more closely, add a preset in `ports/host/sim.cpp` with measured values:
the thermal resistances follow from a turbo test (the rise and the time constant of the surface
temperature), the LED model from two current and voltage measurements.

## Writing behaviour tests

Tests live in `firmware/tests/test_sim.cpp` and use the same simulation through a small API:

```cpp
TEST(lockout_survives_reboot) {
    fresh();                      // new simulated light, 0.5 s settled
    sim::click(4);                // lock
    sim::run_script(1500);        // run the time line, then 1.5 s more
    sim::Config c = sim::keychain_preset();
    c.keep_storage = true;        // keep the emulated EEPROM: a reboot, not a new light
    sim::reset(c);
    sim::run_for(300);
    CHECK(ui::state() == ui::S_LOCK);
}
```

Useful calls: `sim::click(n)`, `sim::hold(clicks, ms)`, `sim::press_at(t, down)`,
`sim::usb_at(t, on)`, `sim::ambient_at(t, c)`, `sim::wait(ms)`, `sim::run_script(extra)`,
`sim::run_for(ms)`, and the observers `sim::level()`, `sim::lumens()`, `sim::t_sensor()`,
`sim::v_pack()`, `sim::laser()`, `sim::sleeping()`, `sim::log()`. The console is reached with
`sim::console_in("...")` and `sim::console_take()`. Every bug that is fixed gets a test.
