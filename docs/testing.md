<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
# Testing a flashlight

This guide takes a LuxLibre light from the first power-up of a new board to the numbers you
publish. Every procedure works with a small budget. Each section ends with a short note on
what a professional lab does differently, so you know where your numbers stop being exact.

Rule IDs such as [THM-1](design-rules.md#thm-1) point to the design rules. Numbers from
standards carry their source. Numbers marked "LuxLibre rule", "LuxLibre default" or
"LuxLibre suggestion" are project choices, not standards.

> **Safety while testing**
>
> - **Li-ion cells can burn.** A shorted, punctured, crushed or overheated cell can vent
>   flames. Never short a cell, never pierce or bend one, and do not test with damaged cells.
> - **Charge on a non-flammable surface** (stone, metal tray, ceramic tile), not on a bed or
>   a desk covered in paper, and stay nearby during the first charges of a new board.
> - **Eyes.** Do not look into a high-output LED or a laser, not even "just to check". Point
>   the light at a matte wall or into the lumen tube. Never look into a laser beam or its
>   reflection.
> - **Burns.** A head in turbo gets hot enough to burn within seconds. Let it cool before you
>   touch it and keep it away from plastics and paper.
>
> Read [SAFETY.md](../SAFETY.md) before you start.

## Overview

A light is tested in six stages. Stages (a) to (c) happen for every new board. Stages (d)
and (e) happen for every hardware release. Stage (f) collects the results.

1. **(a) Bench bring-up** of a new board: is it assembled correctly and safe to power?
2. **(b) Firmware in the simulator**: does the code do what it should with this board's
   settings?
3. **(c) Firmware on the board**: do the gestures and protections work on real hardware?
4. **(d) Performance rating** in the ANSI/PLATO FL 1 style ([REQ-2](design-rules.md#req-2)):
   output, runtime, intensity, beam distance.
5. **(e) Safety and durability**: touch temperature, battery and charging, flicker, drop,
   water, optical safety.
6. **(f) Release test report** from [templates/test-report.md](../templates/test-report.md).

The times below are rough LuxLibre estimates for a first pass by one person.

| Test | What it proves | Rule IDs | Equipment | Time needed |
|---|---|---|---|---|
| Bench bring-up | Board assembled right, outputs off by default, readings calibrated, standby drain known | [DRV-7](design-rules.md#drv-7), [DRV-9](design-rules.md#drv-9), [FW-1](design-rules.md#fw-1), [BAT-9](design-rules.md#bat-9), [BAT-6](design-rules.md#bat-6), [DRV-2](design-rules.md#drv-2), [REQ-4](design-rules.md#req-4) | Multimeter, current-limited supply, programmer | 2-4 h |
| Firmware in the simulator | Code and board parameters behave as intended | [FW-8](design-rules.md#fw-8), [FW-2](design-rules.md#fw-2), [FW-5](design-rules.md#fw-5) | PC | Minutes (CI); 1 h for a new board header |
| Firmware on the board | Gestures and protections work on hardware | [FW-3](design-rules.md#fw-3), [FW-6](design-rules.md#fw-6), [BAT-5](design-rules.md#bat-5), [BAT-7](design-rules.md#bat-7), [THM-5](design-rules.md#thm-5), [DRV-8](design-rules.md#drv-8) | Supply, multimeter, USB console | 2-3 h |
| Output and runtime | Lumens at 30 s and 2 min, runtime to 10 %, sustained output | [REQ-2](design-rules.md#req-2) | Lumen tube, lux meter, reference light | Half a day to a day (one full runtime per mode) |
| Intensity and beam distance | Peak intensity (cd) and beam distance | [REQ-2](design-rules.md#req-2) | Lux meter, tape measure, dark corridor | 1 h |
| Thermal and touch temperature | Hottest touchable point stays within the burn limits | [THM-1](design-rules.md#thm-1), [THM-4](design-rules.md#thm-4), [THM-6](design-rules.md#thm-6) | Thermocouple meter | 3-4 h |
| Battery and charging | Charge voltage and current, temperature window, USB-C, reversed cell | [BAT-4](design-rules.md#bat-4), [BAT-5](design-rules.md#bat-5), [CHG-1](design-rules.md#chg-1), [CHG-2](design-rules.md#chg-2), [CHG-3](design-rules.md#chg-3), [CHG-6](design-rules.md#chg-6) | USB power meter, multimeter, supply, cables | 3-5 h (one full charge) |
| Flicker | No visible flicker at any level | [LED-6](design-rules.md#led-6), [FW-4](design-rules.md#fw-4) | Phone camera; photodiode + oscilloscope | 1 h |
| Durability | Survives drops, then water | [MEC-2](design-rules.md#mec-2), [MEC-3](design-rules.md#mec-3) | Concrete floor, water tube | 2 h |
| Optical safety | LED risk group known, laser class verified, interlock works | [LED-5](design-rules.md#led-5), [LAS-1](design-rules.md#las-1), [LAS-2](design-rules.md#las-2), [LAS-3](design-rules.md#las-3) | Datasheets; laser power meter | 1-2 h |
| Release test report | Every requirement has a result | [REQ-1](design-rules.md#req-1), [REQ-4](design-rules.md#req-4), [FW-8](design-rules.md#fw-8) | Template | 1-2 h |

## Equipment

### Budget kit

| Item | Used for | Notes |
|---|---|---|
| Multimeter with a µA range | Rail resistance, voltages, LED current, standby current | Note its accuracy on the voltage range: [BAT-9](design-rules.md#bat-9) needs 1 %, so the meter must be better than that. |
| Bench power supply with current limit | First power-up, LVP test, reversed-cell test | Most cheap supplies cannot sink current: do not let a charger push current into them (see [Battery and charging](#battery-and-charging)). |
| USB power meter (inline, USB-C) | Charge current, charge energy, termination | Measures on the USB side, so it includes the charger's losses. |
| Thermocouple meter (type K) with thin-wire probes | Touch temperature, reference for the NTC calibration | Check it in ice water: it should read 0 °C. |
| Lux meter | Lumen tube, intensity at a distance | Check it against a second meter if you can. |
| Home-made lumen tube | Relative output and runtime | Calibrate it against a light with a published measured output (see [Output and runtime](#output-and-runtime)). |
| Phone camera | Quick flicker check, photos for the report | A video at a fast shutter speed shows PWM as stripes. |
| Kitchen scale | Weight for the spec sheet | |
| Tape measure, foil or polyimide tape | Distances, fixing thermocouples | |
| Bucket or a capped tube taller than 1 m | IPX7 test | The lowest point of the light must be 1 m under water. |
| Programmer | Flashing the MCU | UPDI, WCH-LinkE (SWIO) or plain USB, see [docs/firmware/README.md](firmware/README.md). |

### Better tools

| Tool | What it adds |
|---|---|
| µA logger (source-measure unit or power profiler) | Standby current with its wake-up spikes, without burden-voltage problems; a source-measure unit can also replace the cell and sink charge current. |
| Integrating sphere | Absolute lumens instead of relative tube readings. |
| Photodiode + oscilloscope | Flicker waveform, frequency and modulation depth. |
| Laser power meter | The real laser output for the class check ([LAS-3](design-rules.md#las-3)). |
| Thermal camera | Finds the hottest touchable point in one look. |
| Climate chamber | A controlled 25 °C for thermal tests; cold and hot tests of the charge window. |

## Bring-up of a new board

Do these steps in order. Stop at the first failure and fix it before you go on.

1. **Visual inspection.** Under a magnifier, check solder bridges (especially on fine-pitch
   ICs and USB-C pins), part rotation and polarity (LED, diodes, cell connector, MCU pin 1),
   and missing parts. Compare with the assembly drawing.
2. **Resistance checks.** With nothing connected, measure from each supply rail (battery +,
   VBUS, the MCU supply) to ground. A reading near 0 Ω means a short. A reading that climbs
   slowly is normal: the capacitors are charging from the meter. Compare with a known-good
   board when you have one.
3. **First power from a current-limited supply.** Set the supply to the nominal cell
   voltage and the current limit low: LuxLibre suggests 100 mA. Why low: a solder bridge or
   a reversed part then only gets warm instead of burning, and an unprogrammed board with all
   outputs off should draw far less than that. If the supply sits at its current limit,
   switch off and look for the short. Touch-check (carefully) for parts that warm up.
4. **Default-off check ([DRV-7](design-rules.md#drv-7), [FW-1](design-rules.md#fw-1)).**
   With a blank MCU, and again while you hold the MCU in reset (for example during
   programming), measure the LED driver enable and the laser gate at the pins: both must be
   low, and the LED must be dark. On laser boards do this with the interlock armed, because
   that is the worst case. A status LED may blink at boot (on the FlashKa, the red LED shares
   the ESP32-C3 boot-log pin); that is not a main output.
5. **Program the MCU** over UPDI, SWIO or USB as described in
   [docs/firmware/README.md](firmware/README.md). Raise the current limit step by step now
   that the firmware controls the outputs.
6. **Read `ver` and `status`** on boards with a console. `ver` must print the firmware
   version and the board name, for example `LuxLibre 0.4.0 / FlashKa Keychain v0.6`
   ([REQ-4](design-rules.md#req-4)). Write it into the report.
7. **Battery voltage calibration ([BAT-9](design-rules.md#bat-9)).** Measure the voltage
   at the cell terminals with the multimeter at the same moment you read `cell_mV` from
   `status`, with the light off. Set `BAT_CAL` to the current value plus
   (multimeter - `cell_mV`) and `save`. Repeat at a low and a high voltage (for example
   3.0 V and 4.2 V from the supply) to see whether the error is only an offset. Pass: within
   1 % at both ends.
8. **Standby current ([BAT-6](design-rules.md#bat-6), [DRV-3](design-rules.md#drv-3)).**
   See the procedure below.
9. **LED current per level ([DRV-2](design-rules.md#drv-2)).** Use `level N` for a set of
   levels (for example 1, 30, 60, 90, 120, 150) and measure the LED current. For low levels
   put the meter's mA range in series with the LED. For high levels measure the voltage
   across the sense resistor at its test point and divide by its value: a series ammeter
   adds resistance and changes the result. Compare with the table in
   [docs/firmware/user-interface.md](firmware/user-interface.md) and your board header
   (`LX_MAIN_MAX_MA`, `LX_OUT_MIN_Q16`). Keep high levels short when the LED is not yet in
   its housing: a bare LED board overheats in seconds.

On boards where the console runs over USB (the FlashKa), the USB cable is also a charger
connection. While it is plugged in the main LED is limited to `CHG_MAXLVL`
([CHG-6](design-rules.md#chg-6)) and the light does not sleep. For the LED current test,
`set CHG_MAXLVL 150` temporarily and put it back afterwards. Do not power such a board from a
bench supply in place of the cell while USB is connected unless the supply can sink current:
the charger would push current into it.

### Measuring standby current without resetting the MCU

A multimeter on its µA range puts a shunt resistor in series. The voltage across it (the
burden voltage) is shunt resistance times current. When the MCU wakes up, the current jumps,
the burden voltage jumps with it, and the MCU can brown out and reset. The trick is to bypass
the meter while the current is high.

1. Disconnect USB. The firmware does not sleep while USB is present or within 30 s of the
   last console input.
2. Put the meter in series with the negative cell lead, at the cell side so that the
   protection circuit and charger leakage are included. Put a jumper wire or a switch across
   the meter.
3. Power up with the jumper closed. Switch the light off (and, as a second case, lock it)
   and wait at least a minute.
4. Open the jumper and read. If the light blinks, the reading jumps or the MCU resets, the
   burden is too high: use the next higher range, or a shunt resistor with a mV reading
   (100 Ω gives 1 mV per 10 µA). Close the jumper before you press the button again.
5. The MCU wakes up briefly from time to time, so the meter shows an average that wanders.
   Write down the typical value. A µA logger shows the spikes and gives the true average.

Compare with [BAT-6](design-rules.md#bat-6): at most 3 % of the capacity per month, which is
33 µA for 800 mAh and 123 µA for 3000 mAh (a month is about 730 h). For reference, the
ESP32-C3-MINI-1 module alone needs 5 µA in deep sleep
([Espressif](https://documentation.espressif.com/esp32-c3-mini-1_datasheet_en.html)), so
the rest of the board has to stay well below the limit as well.

**What a lab does differently:** an X-ray of leadless parts instead of a visual check, a
source-measure unit for standby current, and a calibrated reference for voltage.

## Firmware tests

### In CI and in the simulator

`make test` in `firmware/` runs the unit and behaviour tests on the PC. Every change must
pass it in CI ([FW-8](design-rules.md#fw-8)). The behaviour tests cover lockout across a
reboot, the stuck button, LVP, thermal regulation without flicker, sensor faults and the
charge window.

A new board header ([FW-2](design-rules.md#fw-2)) is first checked in the simulator. Run the
scenarios from [docs/firmware/simulator.md](firmware/simulator.md) with the board's limits,
for example:

```sh
cd firmware
make sim
build/luxsim --preset 18650 --set THM_LIMIT=50 --csv turbo.csv "2C W600000"
```

Check that thermal regulation settles, turbo steps down after `TURBO_S`, and LVP ends in a
cut-off.

### On the board: gesture checklist

The button map is in [docs/firmware/user-interface.md](firmware/user-interface.md). Use the
layout your board sets with `UI_STYLE`.

| Gesture | Expected | Rule |
|---|---|---|
| 1C from off, 1C again | On at the remembered level, then off | [FW-3](design-rules.md#fw-3) |
| Hold from off | Moon, then brighter (ramp layout) or the next mode (modes layout) | [FW-3](design-rules.md#fw-3) |
| 2C | Turbo; steps down to `TURBO_DOWN` after `TURBO_S`; 2C again returns to the previous level | [FW-3](design-rules.md#fw-3) |
| 3C | Battery voltage as blinks (3.8 V = 3 blinks, pause, 8 blinks); compare with the multimeter | [FW-3](design-rules.md#fw-3) |
| 4C | Lockout (3 blinks of the main LED, or the lock colour on boards with an indicator LED). Clicks give only a short flash; hold gives moon only if `LOCK_MOON` = 1. 4C unlocks. | [BAT-7](design-rules.md#bat-7) |
| 4C, then remove the cell (or `reboot`, or switch off the supply), reconnect | Still locked | [FW-6](design-rules.md#fw-6) |
| 9C | 5 blinks of the main LED (or the reset colour on boards with an indicator LED); all parameters back to defaults except the calibration (`BAT_CAL`, `THM_OFFSET`) | [FW-5](design-rules.md#fw-5) |
| Laser gesture (click, then click-and-hold) in lockout | No laser | [LAS-2](design-rules.md#las-2) |

The factory reset keeps the calibration values `BAT_CAL` and `THM_OFFSET`; they are also
stored in their own block, so they survive a firmware update that changes the parameter list.
The console command `defaults all` clears them as well.

### On the board: protections

- **Low-voltage protection ([BAT-5](design-rules.md#bat-5)).** Replace the cell with the
  bench supply, USB disconnected (USB releases the cut-off latch). Read the thresholds with
  `get LVP_WARN`, `get LVP_CUT` and `get LVP_RESUME` first. Switch on a middle level and
  lower the voltage slowly; LuxLibre suggests 20 mV steps with at least 10 s per step,
  because the firmware filters the reading. Expected: below `LVP_WARN` the light steps down
  10 levels every 5 s; below `LVP_CUT` it switches off; a click is then refused. Raise the
  voltage: the light stays off until the cell rests above `LVP_RESUME` or USB is connected.
  The cut-off never goes below the floor for the chemistry (2700 mV per cell for Li-ion), even
  if `LVP_CUT` is set lower, and the step-down always starts at least 200 mV above it.
  On boards with a built-in cell, continue below `LVP_CUT` with the supply on the cell side
  of the protection circuit and check that it cuts off at the threshold in its datasheet
  ([BAT-3](design-rules.md#bat-3)).
- **Thermal regulation ([THM-5](design-rules.md#thm-5)).** Run turbo and watch `status`:
  `temp_dC` (tenths of a degree) rises, and `thermal_cap` falls as the reading approaches
  `THM_LIMIT`. The output must settle, not oscillate. For the shutdown path, avoid high
  temperatures: temporarily `set THM_SHUTDN 40` (its lowest allowed value) and run turbo
  until the light switches off; it must refuse to switch on until 5 °C cooler. Restore the
  value and check with `get`. If you warm the head with a heat gun to test the sensor
  response, keep it at a distance, heat the head only, never the cell, and stop well below
  the cell's maximum discharge temperature (see its datasheet).
- **Sensor fault.** If the design lets you, disconnect or short the NTC (power off first).
  Expected: output capped at `THM_FLOOR`, no laser, and no charging.
- **Stuck button ([BAT-7](design-rules.md#bat-7), [FW-6](design-rules.md#fw-6)).** Lock the
  light, then hold the button down with a clothes peg for 30 s. Expected: dark after 10 s
  (moon before that only if `LOCK_MOON` = 1), still locked after you release it. Then unlock,
  switch off and clamp the button again: the light comes on and ramps (a hold is a normal
  gesture), and after `POCKET_S` (default 30 s) it switches off and locks itself. A click
  after the release must do nothing until 4C.
- **Reset and watchdog ([DRV-8](design-rules.md#drv-8)).** `reboot` restarts the MCU: the
  light must go dark during the restart and come back in its saved state (off or locked),
  never on. `wdtest` switches the main LED to moon and stops the firmware on purpose: the
  watchdog must restart the MCU within its time (1 s on the ATtiny1616, 4 s on the CH32V003,
  3 s on the ESP32-C3) and the light must come back dark. If the moon stays on, the watchdog
  does not work: remove the cell and fix the port before anything else. On boards without a
  console, check the watchdog setup in the port by review.

**What a lab does differently:** automated button actuators and a programmable supply run
the same sequences hundreds of times and log every transition.

## Output and runtime

[REQ-2](design-rules.md#req-2) asks for ratings in the ANSI/PLATO FL 1 way. FL 1 measures
the output in an integrating sphere between 30 s and 2 min after switch-on, and the runtime
from the 30 s value until the output falls to 10 % of it
([Lupine](https://www.lupine.de/about_lupine/fl1-standard),
[Streamlight](https://www.streamlight.com/docs/default-source/ansi-documents/ansi-pres.pdf)).
LuxLibre adds the sustained output after 10 min.

### Why the 30 s value matters

Many lights start bright and step down within seconds. Measured examples from
[1Lumen](https://1lumen.com):

| Light | Claimed (lm) | At switch-on (lm) | At 30 s (lm) | 30 s as % of claim |
|---|---|---|---|---|
| TS10 | 1400 | 1454 | 129 | 9 % |
| SC31T Pro | 2210 | 1581 | 886 | 40 % |
| TS25 (50 °C limit) | 4000 | 3616 | 701 | 18 % |

A rating at switch-on hides this. Always publish the 30 s value.

The 2025 edition of FL 1 adds a test for short-duration elevated brightness (turbo), dust
ratings and a stopwatch icon, and widens the scope to area lights and spotlights
([Business Wire](https://www.businesswire.com/news/home/20260216389772/en)). The details of
the turbo test are not public. Until they are, LuxLibre suggests publishing the output at
switch-on and the time until turbo steps down, clearly labelled as not the FL 1 method.

### Lumen tube method

A lumen tube is a light-tight tube, white inside, with a diffuser and a lux meter sensor at
a fixed port. The lux reading is proportional to the light that enters the tube.

1. **Calibrate** with a reference light that has a published measured output (sphere
   measurement, not the maker's claim), in the same state as in the measurement (fully
   charged cell, same mode, read at 30 s). Factor k = published lumens / tube lux.
2. Use a reference with a similar beam and colour temperature to your light, because the
   tube and the lux meter respond differently to different beams and spectra. Check k with a
   second reference light if you have one.
3. **Uncertainty.** The result is relative to the reference. With careful calibration,
   expect roughly 10-20 % (a rough LuxLibre estimate, not a measured value).
4. **Measure** each mode with a fully charged cell at 25 °C ambient (LuxLibre choice, the
   same as the thermal test): switch on, read at
   30 s and at 2 min, then log every 30 s until the output is below 10 % of the 30 s value
   or the light switches off. Record runtime from the 30 s point.
5. Write the log as CSV with the columns `t_s,lumens,T_sensor_C`. Fill `T_sensor_C` with
   `temp_dC / 10` from `status`, or, without a console, with a thermocouple reading on the
   head (and say so in the report). Then plot it next to the simulator prediction with
   [firmware/tools/plot_sim.py](../firmware/tools/plot_sim.py) (`--title` and `--xlabel`
   change the labels for other kinds of runs):

```sh
cd firmware
build/luxsim --preset 18650 --csv sim.csv "2C W7200000"
python3 tools/plot_sim.py turbo.png measured.csv:"Measured" sim.csv:"Simulator" --limit 50
```

A large difference between measurement and simulator means the thermal model or the board
header is wrong ([THM-3](design-rules.md#thm-3)); fix the model before you publish.

**What a lab does differently:** an integrating sphere calibrated with standard lamps, a
spectroradiometer for colour temperature and CRI, a controlled 25 °C, and several samples
per model.

## Intensity and beam distance

Peak intensity is the light per solid angle in the brightest part of the beam, in candela
(cd). FL 1 measures the illuminance (lux) at 2, 10 or 30 m and computes cd = lux × d²; the
beam distance is the distance at which the illuminance falls to 0.25 lx, which is
2 √cd metres ([Lupine](https://www.lupine.de/about_lupine/fl1-standard)).

1. Use a dark corridor or a field at night. Measure at 5 m or more (LuxLibre suggestion for
   a home setup; the beam must have formed).
2. Fix the light, switch on, wait 30 s (same rule as output), and move the lux meter until
   you find the highest reading.
3. Subtract the reading with the light off (stray light).
4. Compute cd = lux × d² and beam distance = 2 √cd. Example: 50 lx at 5 m gives 1250 cd
   and a beam distance of about 71 m. [tools/lux_calc.py](../tools/lux_calc.py) `throw` does
   this arithmetic; run it with `--help` for its arguments.

**What a lab does differently:** a goniophotometer measures the whole beam pattern, not only
the peak, at the distances the standard sets.

## Thermal and touch temperature

This section verifies [THM-1](design-rules.md#thm-1) with the procedure of
[THM-6](design-rules.md#thm-6) and calibrates the sensor ([THM-4](design-rules.md#thm-4)).

### Burn thresholds

ISO 13732-1 burn thresholds for touching a hot surface, in °C:

| Contact time | Metal | Plastic |
|---|---|---|
| 1 s | 65 | 85 |
| 10 s | 55 | 70 |
| 1 min | 51 | 60 |
| 10 min | 48 | 48 |
| 8 h | 43 | 43 |

Sources: 1 min to 8 h from CENELEC Guide 29 Table A.1
([CENELEC](https://boss.cenelec.eu/media/Guides/CLC/29_cenelecguide29.pdf)); 1 s and 10 s
from EN 13202 via IEEE PSTC slides
([IEEE PSTC](https://ewh.ieee.org/r4/chicago/pstc/content/Accessible-hot-surfaces-and-burn-hazards.pdf)).

**Pass criteria ([THM-1](design-rules.md#thm-1)):** the hottest touchable surface stays at
or below 48 °C in continuous use and never exceeds 51 °C (metal).

### Setup

- 25 °C still air, no fan, no sun. Hang the light from a string (the case without a hand
  to cool it) or hold it in the hand as a user would, and record which. If your room is not at 25 °C,
  record the ambient; adding (25 °C - ambient) to the result is only a rough LuxLibre
  approximation.
- Find the hottest touchable point: with a thermal camera, or by probing the head and body
  with the thermocouple after a few minutes of turbo. It is usually near the LED, but not
  always.
- Tape a thin-wire thermocouple to that point with foil or polyimide tape, bead flat on the
  surface.
- Log the surface temperature, `temp_dC` and the level every 10 s.

### Procedure

1. **Calibrate `THM_OFFSET`.** Leave the light off (and not charging) for 1 h next to the
   reference thermocouple so that everything is at room temperature. `set THM_OFFSET 0`,
   read `temp_dC`, then set `THM_OFFSET` to the reference minus `temp_dC / 10`, rounded, and
   `save`. The charge window uses the same reading, so the offset must make the sensor read
   the true temperature.
2. **Each mode for 10 min**, starting cold each time. Record the highest surface value.
3. **Turbo until regulated**: run turbo (with `set TURBO_S 0` if you want to see the
   thermal regulator alone) until the level and temperatures are steady.
4. **Set `THM_LIMIT`.** At steady state, the sensor reads hotter than the surface by a
   difference Δ = sensor - surface. Take the smallest Δ you measured and set
   `THM_LIMIT` to 48 + Δ, rounded down (allowed range 30-70 °C). Repeat step 3 and check that the surface stays at or
   below 48 °C and never above 51 °C, including the overshoot when turbo starts.
5. Put `TURBO_S` back to its board default and `save`.

**What a lab does differently:** a climate chamber at exactly 25 °C, several thermocouples
logged at once, a thermal camera with a known emissivity setting, and the measurement
conditions of the product safety standard.

## Battery and charging

- **Charge current and termination ([CHG-2](design-rules.md#chg-2)).** Start with a
  half-empty cell. Log the USB power meter every minute: the current should stay roughly
  constant (CC phase), then fall (CV phase) and stop at termination. The charge current must
  be at or below the cell's standard charge current from its datasheet (for example 1.5 A
  for the Samsung 30Q,
  [datasheet](https://e2e.ti.com/cfs-file/__key/communityserver-discussions-components-files/196/samsung_5F00_30q_5F00_data_5F00_sheet.pdf)).
  The USB meter includes the charger's losses; measure at the cell for the exact value.
- **End-of-charge voltage.** Measure at the cell terminals when the charger reports done:
  4.20 V ± 1 %, so 4.158-4.242 V ([CHG-2](design-rules.md#chg-2)). Measure again after 1 h
  off the charger and write both values down.
- **Charge temperature window ([CHG-3](design-rules.md#chg-3)).** Read `CHG_TMIN` and
  `CHG_TMAX` with `get`; the LuxLibre default is 0-45 °C, but use the window in your cell's
  datasheet if it is narrower. To test without extreme temperatures, move the limits towards
  room temperature: `set CHG_TMAX 30` and warm the light gently (hand, warm air) until
  `temp_dC` passes 30 °C: charging must pause and resume when it cools. Then `set CHG_TMIN 20`
  and cool the light in a fridge, in a sealed bag against condensation: charging must pause
  below 20 °C. Restore the values and check with `get`.
- **USB-C ([CHG-1](design-rules.md#chg-1)).** Charge with a C-to-C cable from a USB-C
  charger and with an A-to-C cable, in both plug orientations. A USB-C charger only switches
  on VBUS when it sees the correct resistors on the CC pins, so a CHG-1 fault shows only on
  C-to-C; the A-to-C cable always supplies 5 V and hides it. Try several chargers.
- **Charge indicator and level limit ([CHG-6](design-rules.md#chg-6)).** On USB, the
  indicator shows charging and charged, and turbo is limited to `CHG_MAXLVL` (check `level`
  in `status`).
- **Low-voltage protection ([BAT-5](design-rules.md#bat-5)) and standby drain
  ([BAT-6](design-rules.md#bat-6))** are tested in [Bring-up](#bring-up-of-a-new-board) and
  [Firmware tests](#firmware-tests).
- **Reversed cell ([BAT-4](design-rules.md#bat-4)),** for removable-cell lights. First use
  the bench supply at the cell voltage, reversed, with a low current limit (LuxLibre
  suggests 100 mA): the current must stay near zero, the light must stay dark and nothing
  may warm up. Then connect it the right way round and check that it works. Only a design
  that passes this is tried with a real (protected) cell.

Never charge a light that failed the water test or has a damaged cell.

**What a lab does differently:** a battery cycler logs charge and discharge curves over many
cycles, and a climate chamber tests the charge window at the real limits, cold and hot.

## Flicker

Flicker is the periodic change of light output, for example from PWM (pulse-width
modulation: switching the LED on and off fast). [LED-6](design-rules.md#led-6) and
[FW-4](design-rules.md#fw-4) require constant current or PWM at 3 kHz or more (LuxLibre
rule).

1. **Quick check with a phone camera.** Film the lit wall at a fast shutter speed (or use
   the slow-motion mode). Dark stripes rolling through the picture mean PWM. No stripes is
   only a hint, not a proof.
2. **Photodiode and oscilloscope.** Point the light at a photodiode with a load resistor
   (keep it out of saturation) and record the waveform. Read the frequency f and the maximum
   and minimum, Lmax and Lmin.
3. **Compute** the modulation depth: Mod% = 100 (Lmax - Lmin) / (Lmax + Lmin).
4. **Test at** the lowest level, a middle level, the highest level, and during thermal
   regulation (the level changes in small steps; it must not flicker,
   [FW-4](design-rules.md#fw-4)). The lowest level is often the worst case.
5. **Compare with IEEE 1789-2015** (table below). Pass for LuxLibre: inside the NOEL
   region at every tested level.

IEEE 1789-2015 limits
([standard copy](https://lee.org/flicker/wp-content/uploads/2024/12/IEEE-2015-STANDARDS-1789-Standard-Free-Download.pdf)),
f = flicker frequency in Hz:

| Region | Below 90 Hz | From 90 Hz up to the limit | No limit from |
|---|---|---|---|
| Low risk | Mod% < 0.025 f | Mod% < 0.08 f (up to 1250 Hz) | 1250 Hz |
| No observable effect (NOEL) | Mod% < 0.01 f | Mod% < 0.0333 f (up to 3000 Hz) | 3000 Hz |

Example: at 1000 Hz, NOEL allows Mod% < 33.3 %. IEEE has listed 1789 as
"Inactive-Reserved" since 26 March 2026
([IEEE](https://standards.ieee.org/ieee/1789/4479/)): it is no longer maintained, but it
remains the common reference, and LuxLibre keeps its NOEL region as the target (LuxLibre
choice).

**What a lab does differently:** a calibrated flicker meter that also reports the flicker
index and stroboscopic visibility measures.

## Durability

Do the drop test first and the water test after it, as FL 1 requires
([Lupine](https://www.lupine.de/about_lupine/fl1-standard)).

- **Drop ([MEC-3](design-rules.md#mec-3)).** FL 1: at least 1 m onto concrete, 6 drops;
  pass = no cracks and the light works. LuxLibre suggests six different orientations (head,
  tail and four sides). Record the orientation and whether the light was on. After the
  drops, run the gesture checklist and compare the output with the lumen tube.
- **Water ([MEC-2](design-rules.md#mec-2)).** IEC 60529 IPX7: 30 min with the lowest point
  1 m below the surface (the alternative "top 0.15 m below the surface" is meant for tall
  enclosures, not for flashlights); IPX8: maker's conditions harsher than IPX7 ([IP code](https://en.wikipedia.org/wiki/IP_code)). FL 1
  uses 1 m for 30 min for IPX7 and the maker's depth for 4 h for IPX8. A capped drain pipe
  taller than 1 m plus the light's length works as a test tank. Leave the light on at a low
  level so you see a failure.
- **Inspect for water inside.** Dry the outside, open the light over a paper towel, and look
  for drops or fogging on the lens, the board and the cell compartment.
- **O-rings and USB cover.** Check the O-rings for cuts, flat spots and dry areas (lubricate,
  [MEC-4](design-rules.md#mec-4)), and that the USB cover seats fully and is not torn.

**What a lab does differently:** a drop rig with a defined release and orientation, a
pressure chamber for IPX8, and dust tests for the new FL 1 dust ratings.

## Optical safety

### LED ([LED-5](design-rules.md#led-5))

IEC 62471 sorts light sources by blue-light hazard: Exempt (no hazard within 10 000 s),
RG1 (no hazard within 100 s), RG2 (no hazard within 0.25 s, the eye's aversion response),
RG3 (hazardous even for a momentary exposure). Flashlights are not general lighting and are
assessed at 200 mm. IEC TR 62778 gives a threshold distance; above RG1 at 200 mm, the
hazard distance is marked on the product. IEC 62471-7:2023 is the newer part for visible
products. (Secondary source; check the standard text before you claim a group.)

Without a lab, a maker can:

- Get the LED maker's photobiological safety report or the IEC 62471 group in the datasheet.
- Remember that the optic changes the apparent source, so the emitter's group is a starting
  point, not the product's group.
- Label throwers and high-output lights with an eye warning, as LED-5 asks, and never claim
  a risk group you have not measured.

### Laser ([LAS-1](design-rules.md#las-1) to [LAS-3](design-rules.md#las-3))

IEC 60825-1 classes for visible lasers: Class 2 ≤ 1 mW continuous; Class 3R ≤ 5 mW;
EN 50689 allows only Class 1, 2 or restricted 3R in consumer products, and only Class 1 in
products that appeal to children
([UK government](https://www.gov.uk/government/publications/laser-radiation-safety-advice/laser-radiation-safety-advice),
[UL](https://www.ul.com/insights/understand-new-laser-product-safety-standards-europe)).

1. **Never look into the beam.** Remove watches and rings, keep mirrors and shiny tools away,
   aim only at the power meter sensor or a matte wall, and wear laser safety glasses rated
   for the wavelength.
2. **Measure the power ([LAS-3](design-rules.md#las-3)).** Put the whole beam on the sensor
   of a laser power meter set to the laser's wavelength. Measure with a full cell, at the
   start and at the end of a `LASER_S` emission. The seller's label is not a measurement.
   The whole-beam value is at least as high as the value under the aperture conditions of
   IEC 60825-1, so it is a conservative check.
3. **Interlock ([LAS-2](design-rules.md#las-2)).** With the hardware interlock open (on the
   FlashKa, the slide switch S2), do the laser gesture: the MCU laser pin goes high (measure
   it) but there must be no emission. With the interlock armed: emission only with the
   deliberate gesture, the emission indicator lights, and the firmware refuses in lockout,
   above `LASER_TMAX` and below `LASER_VMIN`, and stops after `LASER_S`.
4. **Labels.** Class label and warning per IEC 60825-1 on the product and in the manual.

**What a lab does differently:** a spectroradiometer and imaging radiometer for IEC 62471,
and laser power and beam measurements under the exact IEC 60825-1 conditions.

## Writing the report

1. Copy [templates/test-report.md](../templates/test-report.md) and fill it in.
2. Record the firmware version from `ver`, the board header (for example
   [firmware/boards/flashka-keychain-v05/board.h](../firmware/boards/flashka-keychain-v05/board.h)),
   the git commit, the hardware revision on the silkscreen
   ([REQ-4](design-rules.md#req-4)), and every parameter you changed from the default
   (`list` prints them all).
3. Keep the raw data with the report: CSV logs, oscilloscope screenshots, photos, and the
   calibration values (`BAT_CAL`, `THM_OFFSET`, the lumen tube factor and its reference).
4. Link the report from the hardware folder README, for example
   [hardware/flashka-keychain-v05/README.md](../hardware/flashka-keychain-v05/README.md).
5. A release is tested when every requirement in the requirement sheet
   ([templates/requirements.md](../templates/requirements.md),
   [REQ-1](design-rules.md#req-1)) has a result: pass, fail, or not tested with the reason.
   Every board release needs this report ([FW-8](design-rules.md#fw-8)).
