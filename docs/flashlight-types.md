<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
# Flashlight types

LuxLibre is meant for any kind of flashlight. The physics, the design rules and the firmware
are the same for all of them; what changes is which rules dominate and which settings fit.
This page goes through the common types and, for each, names the parts direction, the rules
that matter most and a starting point for the firmware settings.

Targets marked *suggestion* are LuxLibre starting points, not standards. The sustained output
of every type follows from its surface area ([THM-2](design-rules.md#thm-2)): compute it with
[tools/lux_calc.py](../tools/lux_calc.py) `thermal` before writing a specification.

| Type | Typical cells | Main constraint | Firmware starting point |
|---|---|---|---|
| [Keychain and mini](#keychain-and-mini-lights) | pouch, 10180, 10440, AAA | tiny surface, pocket carry | modes or simple layout, dark lockout |
| [Compact EDC](#compact-edc-14500-18350) | 14500, 18350 | heat in a small body | ramp layout, turbo timer |
| [EDC 18650 / 21700](#edc-18650-and-21700) | 18650, 21700 | sustained output vs peak | ramp layout, full feature set |
| [Headlamp and right-angle](#headlamps-and-right-angle-lights) | 14500-21700 | contact with skin, wide beam | ramp, low moon, lockout |
| [Thrower](#throwers) | 18650-26650 | intensity, eye safety | modes, high turbo, labels |
| [Flood, lantern, area](#flood-lantern-and-area-lights) | 18650 and up | colour quality, glare | ramp, high CRI |
| [Multi-cell high power](#multi-cell-high-power-lights) | 3-4 × 21700 and up | heat, cell current | short turbo, strict thermal |
| [Bicycle light](#bicycle-lights) | 18650, 21700 | road-traffic rules | simple modes, no flashing front light where required |
| [Dive light](#dive-lights) | 18650-26650 | pressure, switch through the housing | modes, thermal for use in air |
| [UV and IR](#uv-and-ir-lights) | any | invisible hazards | locked-out by default |
| [Tactical-style handheld](#tactical-style-handheld-lights) | 18650, 21700 | instant access | momentary, strobe with warning |
| [Work light](#work-lights) | 18650-21700 | runtime, colour, mounting | ramp, magnet-friendly UI |

---

## Keychain and mini lights

**Use:** always with you, short tasks, finding things in the dark. **Reference design:** the
FlashKa ([hardware/flashka-keychain-v07/](../hardware/flashka-keychain-v07/README.md), the
current design; [hardware/flashka-keychain-v06/](../hardware/flashka-keychain-v06/README.md),
the previous one).

- **Cells:** pouch cells, 10180, 10440 or AAA, or in a longer body a 14500 (FlashKa v0.7 has one
  Vapcell INR14500 F15). With built-in cells, plan replacement with common tools
  ([BAT-2](design-rules.md#bat-2)) and add a protection circuit ([BAT-3](design-rules.md#bat-3)).
- **Heat:** a very small surface. The FlashKa (about 69 cm² of aluminium) can lose roughly 1.7 W
  at a 23 K rise, so its turbo is a burst and its sustained output is in the low hundreds of
  lumens (simulated for FlashKa v0.7 with its TIR optic: about 1,000 lm for about 58 s, then
  about 280 lm out of the front).
- **Parts:** small efficient LEDs (SST-20, 519A), a buck driver or linear regulator, an MCU that
  sleeps at a few microamps: the standby budget is tiny (33 µA for 800 mAh,
  [BAT-6](design-rules.md#bat-6)).
- **Rules that dominate:** [BAT-6](design-rules.md#bat-6), [BAT-7](design-rules.md#bat-7),
  [THM-1](design-rules.md#thm-1), [MEC-7](design-rules.md#mec-7) (the keyring loop carries the
  keys), [DFM-3](design-rules.md#dfm-3) (tiny parts).
- **Firmware:** `UI_STYLE` 1 (modes) or 2 (simple), `BLINKY` 0, `LOCK_MOON` 0 (a dark lockout
  for the pocket), `POCKET_S` shorter than the default if the button is exposed (suggestion:
  15 s), `PREVIEW` 0 if a gesture must not flash the LED. The FlashKa board header is the example.

## Compact EDC (14500, 18350)

**Use:** pocket lights with real output in a small size.

- **Cells:** 14500 (for example Vapcell H10, 1000 mAh, 10 A) or 18350 (Vapcell M11 V2, 1100 mAh,
  10 A) ([choosing-parts.md](choosing-parts.md#cells)).
- **Heat:** peaks of 1000 lm and more are possible for seconds; sustained output is limited by
  the small body. A turbo timer next to the thermal regulator keeps the user informed.
- **Parts:** SST-20 or 519A on a copper DTP board, buck or linear driver, CH32V003 or ATtiny1616.
- **Rules that dominate:** [THM-3](design-rules.md#thm-3), [BAT-1](design-rules.md#bat-1)
  (10 A cells give only 7 A under the 70 % rule), [REQ-2](design-rules.md#req-2) (publish the
  30 s value).
- **Firmware:** ramp layout (`UI_STYLE` 0), `TURBO_S` 30-60, `BAT_MAX_MA` from the cell.

## EDC 18650 and 21700

**Use:** the everyday-carry light that does everything; the main theme of open lights with more
than 1000 lm.

- **Cells:** 18650 (Molicel P28A, Samsung 30Q) or 21700 (Molicel P42A, Samsung 40T).
- **Heat:** an 18650 light of 25 × 120 mm can lose about 2.6 W continuously; turbo at 1200-
  1600 lm lasts about two minutes before the regulator steps down (see the
  [worked example](choosing-parts.md#worked-example-a-1200-lm-18650-light)).
- **Parts:** SST-40 or a triple 519A for high CRI; linear, buck or boost driver
  ([DRV-1](design-rules.md#drv-1)); USB-C charging in the light.
- **Rules that dominate:** [THM-1](design-rules.md#thm-1) to [THM-6](design-rules.md#thm-6),
  [BAT-4](design-rules.md#bat-4) (removable cells), [CHG-1](design-rules.md#chg-1) to
  [CHG-4](design-rules.md#chg-4), [MEC-2](design-rules.md#mec-2), [MEC-3](design-rules.md#mec-3).
- **Firmware:** the defaults: ramp layout, `TURBO_S` 60, `BLINKY` 3 (beacon and SOS; strobe
  only when asked for), `LOCK_MOON` 1.

## Headlamps and right-angle lights

**Use:** hands-free work, running, camping.

- **Heat:** the light touches the forehead or rests in a strap, so treat the head as a surface
  in long contact ([THM-1](design-rules.md#thm-1): 48 °C for 10 min contact is the upper limit;
  stay below it with margin for skin contact, suggestion: 43 °C, the 8 h value).
- **Beam:** wide and even, often a TIR optic or a mule with a diffuser; a very low moon for
  tents and reading.
- **Rules that dominate:** [THM-1](design-rules.md#thm-1), [LED-4](design-rules.md#led-4),
  [LED-7](design-rules.md#led-7), [MEC-7](design-rules.md#mec-7) (strap mounts).
- **Firmware:** `RAMP_FLOOR` low, `MEMORY` 1, a lower `THM_LIMIT` matched to the measured skin-
  side surface, `POCKET_S` long enough for normal use (the button is on the head, rarely pressed
  by accident).

## Throwers

**Use:** seeing far: search, outdoors, inspection at a distance.

- **Parts:** a small, high-luminance die (SFT-40, XP-L HI, KW CSLNM1.TG) in a deep, wide smooth
  reflector or a TIR optic ([LED-1](design-rules.md#led-1)); estimate the intensity with
  `lux_calc.py throw --lumens --die-mm2 --optic-mm`.
- **Safety:** high intensity is an eye hazard at a distance. Assess it
  ([LED-5](design-rules.md#led-5)), mark the hazard distance where required, and warn against
  pointing it at people, vehicles and aircraft.
- **Rules that dominate:** [LED-1](design-rules.md#led-1), [LED-5](design-rules.md#led-5),
  [REQ-2](design-rules.md#req-2) (publish candela and beam distance), [LED-8](design-rules.md#led-8).
- **Firmware:** modes layout with few, well-spaced levels; a high `TURBO_LVL`; `LOCK_MOON` 0.

## Flood, lantern and area lights

**Use:** lighting a room, a camp or a work area; ANSI/PLATO FL 1 now includes area lights in its
scope ([Business Wire](https://www.businesswire.com/news/home/20260216389772/en)).

- **Parts:** several high-CRI LEDs, a diffuser or no optic, large surface for cooling.
- **Rules that dominate:** [LED-4](design-rules.md#led-4) (colour), [LED-6](design-rules.md#led-6)
  (flicker is very visible in a lit room and on video), [BAT-6](design-rules.md#bat-6) (long
  storage).
- **Firmware:** ramp layout with a high `RAMP_CEIL` and long runtimes in the middle levels.

## Multi-cell high-power lights

**Use:** the very bright "search" class with several cells (for example 3-4 × 21700) and
sometimes a fan.

- **Heat:** turbo is a few seconds to minutes; the regulated output is set by the surface and
  the fan. Publish both honestly ([REQ-2](design-rules.md#req-2)).
- **Cells:** in parallel, each cell carries part of the current; in series, the voltage rises and
  every cell carries the full current. Use matched cells from the same batch, and protection
  that handles the higher current ([BAT-1](design-rules.md#bat-1), [BAT-3](design-rules.md#bat-3)).
- **Parts:** boost or buck drivers at higher power, thick copper ([DRV-5](design-rules.md#drv-5)),
  springs with bypasses or solid contacts ([BAT-8](design-rules.md#bat-8)).
- **Firmware:** `BAT_CELLS` for series packs (1-4), strict `THM_LIMIT` and `TURBO_S`,
  `BAT_MAX_MA` per the cell rating. Fan control is not in LuxLibre yet (see
  [what LuxLibre does not cover yet](#what-luxlibre-does-not-cover-yet)).

## Bicycle lights

**Use:** riding at night. Road use is regulated, and the rules differ by country.

- **Germany, as an example:** front lights for road use need a type approval (the "K" mark under
  StVZO §22a, technical requirement TA 23): a clear cut-off line so that oncoming traffic is not
  dazzled, a minimum intensity at 10 m, steady light only (no flashing), and a low-battery
  indication ([TÜV NORD](https://www.tuv-nord.com/tw/en/homepage/product-and-service/mobility/k-mark-stvzo/)).
  Other countries have their own rules: check them before you sell a "bike light".
- **Parts:** an asymmetric optic with a cut-off for road lights; vibration-proof mounting and
  connectors; good sealing against spray.
- **Rules that dominate:** [MEC-2](design-rules.md#mec-2), [MEC-3](design-rules.md#mec-3) (and
  vibration), [CHG-6](design-rules.md#chg-6) (battery indication).
- **Firmware:** `UI_STYLE` 1 or 2 with fixed steps, `BLINKY` 0 for a front light where flashing
  is not allowed, `AUX_MODE` with the battery colour.

## Dive lights

**Use:** under water, where the light is the safety equipment.

- **Mechanics:** the rating is a depth, not IPX7: design and test the housing, O-rings and lens
  for the pressure at the rated depth plus margin ([MEC-2](design-rules.md#mec-2)). A push button
  through the housing is a leak path; magnetic (reed or Hall sensor), rotary or piezo switches
  avoid it.
- **Heat:** water cools very well, but the light is also switched on in air on the boat, where
  the same output overheats quickly: the thermal regulator must work for both
  ([THM-5](design-rules.md#thm-5)).
- **Firmware:** modes layout with few steps, simple to operate with gloves. A Hall or reed switch
  wired as the button works with LuxLibre's single-button input.

## UV and IR lights

**Use:** UV (often 365 nm) for fluorescence and inspection; IR for night-vision devices.

- **Safety:** both are invisible, so the aversion reflex of the eye does not protect it. Assess
  them under IEC 62471 ([LED-5](design-rules.md#led-5)), label them clearly, keep them away from
  children, and add a visible indicator that shows when the emitter is on.
- **Parts:** UV LEDs with a visible-light filter for clean fluorescence; IR LEDs at the
  wavelength of the night-vision device.
- **Firmware:** treat the emitter like the laser: lockout by default (set the stored state to
  locked before shipping) and an indicator while it emits. A dedicated output channel for such
  emitters is not in LuxLibre yet.

## Tactical-style handheld lights

**Use:** instant, momentary light with a tail switch.

- **Parts:** a tail button with a short, positive click; a high-current path from tail to head
  ([BAT-8](design-rules.md#bat-8)); a sturdy body ([MEC-3](design-rules.md#mec-3)).
- **Strobe:** flashing between 3 and 30 Hz is the range most likely to trigger seizures in
  people with photosensitive epilepsy ([Epilepsy Society](https://epilepsysociety.org.uk/node/3618)).
  Keep strobe out of the default modes and warn about it in the manual.
- **Firmware:** boards without a laser give momentary turbo on click-and-hold from off;
  add 4 (strobe) to `BLINKY` only when asked for; the `STROBE_HZ` description states the risk.

## Work lights

**Use:** workshops, cars, repairs: long runtimes, good colour, hands-free mounting.

- **Parts:** high-CRI flood LEDs ([LED-4](design-rules.md#led-4)), a magnetic tail or a clip,
  a large cell. A power-bank output (charging a phone from the light) needs a USB-C source
  controller, not only resistors.
- **Firmware:** ramp layout, `MEMORY` 1, `AUTOLOCK` 0 (no automatic lockout on the bench).

---

## What LuxLibre does not cover yet

The firmware today has one main LED channel, an optional RGB indicator, an optional laser and one
button. Not yet included (contributions welcome, see [CONTRIBUTING.md](../CONTRIBUTING.md)):

- several main channels (tint ramping between warm and cool LEDs, white + red, white + UV);
- two buttons (side switch plus tail switch) and rotary or magnetic ring controls;
- fan control for multi-cell lights;
- a Bluetooth app on the LuxLibre ESP32-C3 port (the FlashKa's original firmware has one, see
  its [folder](../hardware/flashka-keychain-v05/README.md));
- ports for more MCUs (PY32F002A, STM32C0, nRF52 are good candidates,
  [choosing-parts.md](choosing-parts.md#microcontrollers)).

How to add a board or an MCU: [firmware/porting.md](firmware/porting.md).
