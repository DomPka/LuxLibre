<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
# Choosing parts

This guide shows how to choose the parts of a flashlight so that every choice can be
explained and checked: first a method that works for any part, then what matters for each
part family, then a complete worked example (a 1200 lm 18650 everyday-carry light).

Numbers come from datasheets and measurements, with links. Prices and stock are from
October 2026 and change quickly: check them again before you order. Part names are examples,
not endorsements; the project has no commercial relationship with any maker or shop.

Contents: [the method](#the-method-in-six-steps) · [cells](#cells) · [LEDs](#leds) ·
[optics](#optics) · [drivers](#drivers) · [microcontrollers](#microcontrollers) ·
[chargers and protection](#chargers-and-protection) ·
[sensors, switches and small parts](#sensors-switches-and-small-parts) ·
[housing](#housing-and-materials) · [worked example](#worked-example-a-1200-lm-18650-light) ·
[cost](#cost-the-bom-is-not-the-price) · [search tools and AI assistants](#search-tools-and-ai-assistants)

---

## The method in six steps

| Step | Question | Output |
|---|---|---|
| 1. Limits | What must this part do, in numbers? | Must-have limits from the requirements |
| 2. Candidates | Which parts could do it? | A list of 3-8 candidates with datasheets |
| 3. Screen | Which candidates break a hard limit? | 2-4 survivors |
| 4. Score | Which survivor is best for this design? | A decision matrix |
| 5. Measure | Does the winner do what the datasheet says, in this design? | Prototype measurements |
| 6. Record | Why was it chosen? | A design-log record |

### 1. Turn the requirements into part limits

Start from the requirement sheet ([REQ-1](design-rules.md#req-1),
[templates/requirements.md](../templates/requirements.md)) and work out what each part must
handle. Example: "1200 lm at 30 s from one 18650 cell" means an LED that emits clearly more than
1200 lm at a junction temperature of 85 °C (the optic loses some light), at no more than 80 % of
its maximum current ([LED-2](design-rules.md#led-2)); a driver that delivers that current over
the cell's voltage range; and a cell that supplies the resulting current at no more than 70 % of
its rating ([BAT-1](design-rules.md#bat-1)).

Write the limits down as numbers: voltage range, current, power, size, temperature range,
interface, price per unit at your quantity, and how the board will be assembled
([DFM-3](design-rules.md#dfm-3)).

### 2. Find candidates

Look in several places and always end at the maker's datasheet:

- **Parametric search** at distributors (filter by voltage, current, package, stock). If the
  board will be assembled by a service, search its parts library first: a part it stocks is
  cheaper to place ([DFM-2](design-rules.md#dfm-2)).
- **Maker selection tools and product pages** for LEDs, regulators and MCUs.
- **Existing designs:** open-source drivers and lights (this project's boards, drivers supported
  by the Anduril firmware), teardowns and schematics in reviews.
- **Independent measurements:** cell tests (for example the
  [lygte-info Vapcell H10 review](https://lygte-info.dk/review/batteries2012/Vapcell%20INR14500%20H10%201000mAh%20(Purple)%202020%20UK.html)),
  flashlight output measurements ([1Lumen](https://1lumen.com)), driver efficiency
  measurements ([BLF thread](https://budgetlightforum.com/t/efficiency-measurements-of-flashlight-drivers-update-sc70/68528)).
- **Community discussion** shows what users want and what fails in practice; treat it as a
  lead to check, not as data.

### 3. Screen with hard limits

Remove every candidate that fails a must-have limit, before you compare anything else:

- Absolute maximum ratings with margin (voltage, current, temperature;
  [DRV-4](design-rules.md#drv-4), [LED-2](design-rules.md#led-2), [BAT-1](design-rules.md#bat-1)).
- Package that fits the board and the build method ([DFM-3](design-rules.md#dfm-3)).
- Available: active lifecycle, in stock at more than one shop, ideally with a pin-compatible
  alternative ([DFM-6](design-rules.md#dfm-6)).
- A real datasheet from the maker. No datasheet, no part.

### 4. Score the survivors

Use a weighted decision matrix ([templates/decision-matrix.md](../templates/decision-matrix.md)):
4-7 criteria, weights that add up to 100 %, a 1-5 score with a written meaning for each score,
the weighted total, and a sensitivity check (change the biggest weight by ±10 points: does the
winner change?). If the winner changes, the choice is close; say so in the design log and decide
with a measurement.

### 5. Measure

Datasheets give typical values under the maker's conditions. Measure what matters in your
design: LED current and forward voltage when hot, driver efficiency at your most-used levels,
standby current, the temperature of the part in the housing. Order samples of the top two
candidates when the matrix was close.

### 6. Record

Write a design-log record ([REQ-3](design-rules.md#req-3),
[templates/design-log.md](../templates/design-log.md)): question, options, criteria, data with
links and the date you read them, decision, reasons, risks, and how it will be verified.

---

## Cells

**What matters:** capacity (mAh) and energy (Wh) for runtime; the maximum continuous current
for turbo ([BAT-1](design-rules.md#bat-1)); size and terminal type (button top or flat top,
protected or unprotected); the charge temperature window ([CHG-3](design-rules.md#chg-3)); the
standard charge current ([CHG-2](design-rules.md#chg-2)); whether users can buy and replace it
([BAT-2](design-rules.md#bat-2)).

| Cell | Format | Capacity | Max continuous current | Notes | Source |
|---|---|---|---|---|---|
| Vapcell H10 | 14500 | 1000 mAh | 10 A | independent review | [lygte-info](https://lygte-info.dk/review/batteries2012/Vapcell%20INR14500%20H10%201000mAh%20(Purple)%202020%20UK.html) |
| Vapcell M11 V2 | 18350 | 1100 mAh | 10 A | retailer data | [retailer](https://illumn.com/18350-vapcell-inr18350-m11-v2-1100mah-10a-high-discharge-button-top.html) |
| Molicel P28A | 18650 | 2800 mAh typ (2700 min) | 35 A | charge 0-60 °C, standard charge 2.8 A, cut-off 2.5 V | [datasheet](https://www.rosebatteries.com/hubfs/INR18650P28A-V2-80093.pdf) |
| Samsung 30Q | 18650 | 3000 mAh | 15 A | charge 0-50 °C, standard charge 1.5 A, cut-off 2.5 V | [datasheet](https://e2e.ti.com/cfs-file/__key/communityserver-discussions-components-files/196/samsung_5F00_30q_5F00_data_5F00_sheet.pdf) |
| Murata VTC6 | 18650 | 3000 mAh | 15 A | retailer data | [retailer](https://www.imrbatteries.com/sony-murata-vtc6-18650-3000mah-15a-battery/) |
| Molicel P42A | 21700 | 4200 mAh | 45 A | | [datasheet](https://www.nkon.nl/novat/amfile/file/download/file/1170/product/3427/) |
| Samsung 40T | 21700 | 4000 mAh min | 35 A (45 A with an 80 °C cut-off) | | [datasheet](https://cdn.simpower.co.nz/wp-content/uploads/2021/09/INR21700-40T.pdf) |

**Rules of thumb.** In the same size, high-current cells have less capacity than high-capacity
cells; pick by what the light does most. An EDC light spends most of its life in low and middle
modes, so capacity usually matters more than a current rating far above the turbo current. Small
lights with a pouch cell (as the FlashKa, two pouch cells in parallel, about 800 mAh) need the
cell's own datasheet for current and charge limits, a protection circuit
([BAT-3](design-rules.md#bat-3)), and a plan for replacement ([BAT-2](design-rules.md#bat-2)).

**Traps.** Fake or relabelled cells (capacity claims far above the known cells of that size);
protected cells that are longer than the tube was designed for; flat-top cells that do not reach
the contact; datasheet cut-off voltages taken as normal use (set the low-voltage protection
higher, [BAT-5](design-rules.md#bat-5)).

## LEDs

**What matters:** light output at your current and at a hot junction (85 °C), luminance (for
throw, [LED-1](design-rules.md#led-1)), forward voltage (it decides the driver topology,
[DRV-1](design-rules.md#drv-1)), maximum current ([LED-2](design-rules.md#led-2)), colour
temperature and CRI ([LED-4](design-rules.md#led-4)), package and the available copper boards
([LED-3](design-rules.md#led-3)).

| LED | Size / emitting area | Max current | Datasheet output (condition) | Character | Source |
|---|---|---|---|---|---|
| Luminus SST-20-W | 2.0 mm² | 3 A (CRI 95 version 2 A) | min 530-585 lm at 1.5 A, 85 °C; Vf 3.0 V at 1.5 A | small, efficient, throw and general use | [datasheet](https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/5344/SST-20-W_Rev09_7-6-20.pdf) |
| Luminus SST-40-W | 4.0 mm² | 6 A | min 594-673 lm at 1.5 A; 986-1269 lm at 3 A; 1446-1861 lm at 5 A; 1640-2110 lm at 6 A (85 °C) | high output from one die | [datasheet](https://download.luminus.com/datasheets/Luminus_SST-40-W_Datasheet.pdf) |
| Luminus SFT-40-W | | 8 A | min 610-680 lm at 1.5 A, 85 °C; Vf 2.8 V at 1.5 A | "narrow beam angle, long beam distance" | [datasheet](https://download.luminus.com/datasheets/Luminus_SFT-40-WExx_Gen2_Datasheet.pdf) |
| Nichia 519A | 3.5 × 3.5 mm package | 2.2 A | typ 730 lm at 1.4 A, 25 °C pulsed (5000 K, Ra 70); Vf 2.94 V | Ra 70 / 80 / 90 (R9 ≥ 80), good colour | [datasheet](https://www.ledrise.eu/amfile/file/download/file/10835/product/11566/) |
| Samsung LH351D | 3.5 × 3.5 mm package | 3 A | see datasheet | CRI 70 / 80 / 90 | maker datasheet |
| Cree XHP50.3 HI | 5 × 5 mm package | 3 A (6 V configuration) | min 970-1120 lm at 6 V, 1.4 A, 85 °C; Vf 5.6 V | flood or wide beam, 6 V or 12 V | [datasheet](https://downloads.cree-led.com/files/ds/x/XLamp-XHP50.3.pdf) |
| Cree XP-L HI | 3.45 mm package | 3 A | see datasheet | throw | maker datasheet |
| ams OSRAM KW CSLNM1.TG | 0.96 × 0.96 mm² emitting area | 3 A | 280-450 lm at 1 A | very high luminance, long throw | maker datasheet |

**How to estimate output.** Read the flux at your current from the datasheet curve, correct it
to 85 °C if the datasheet gives 25 °C values, and subtract the optic and lens losses (measure,
or use the optic maker's efficiency). Compare LEDs only at the same conditions: a 25 °C pulsed
value (Nichia's table above) is not comparable with an 85 °C value (Luminus, Cree).

**Traps.** Choosing by the headline lumens at maximum current (the light cannot hold it,
[THM-2](design-rules.md#thm-2)); a 6 V or 12 V LED with a 3 V driver; high-CRI versions with a
lower maximum current; LEDs that only come on boards with a dielectric layer.

## Optics

- **Reflector** (smooth for throw, textured "orange peel" for a softer hotspot): the deeper and
  wider, the more light is collected into the beam.
- **TIR optic** (total internal reflection lens): compact, good for multi-LED lights and wide or
  narrow beams; slightly lower efficiency than a good reflector, depending on the design.
- **No optic** ("mule"): pure flood, for lanterns and headlamp close work.

For a reflector or TIR optic filled by the source, peak intensity is at most about
luminance × aperture area × optical efficiency. [tools/lux_calc.py](../tools/lux_calc.py)
`throw --lumens --die-mm2 --optic-mm` computes this upper bound; real lights reach roughly
50-80 % of it (rule of thumb). A small, bright die in a wide optic throws furthest
([LED-1](design-rules.md#led-1)).

## Drivers

**What matters:** the topology ([DRV-1](design-rules.md#drv-1)), current regulation and its
accuracy ([DRV-2](design-rules.md#drv-2)), efficiency at the levels used most and the
quiescent and shutdown current ([DRV-3](design-rules.md#drv-3), [BAT-6](design-rules.md#bat-6)),
the lowest stable level ([LED-7](design-rules.md#led-7)), size and heat.

| Part | Type | Key data | Typical use | Source |
|---|---|---|---|---|
| AMC7135 | linear current sink | 2.7-6 V, 340-380 mA each, 120 mV dropout, SOT-89 | several in parallel for budget regulated drivers | maker datasheet |
| TLV62585 | buck | 2.5-5.5 V in, 3 A, 1.5 MHz, 35 µA quiescent, 100 % duty, SOT-563 or 2 × 2 mm QFN | one Li-ion cell, white LED up to about 3 A (FlashKa) | [TI](https://www.ti.com/product/TLV62585) |
| TPS61088 | boost | 2.7-12 V, 10 A switch, Vout 4.5-12.6 V | 6 V or 12 V LEDs from one or two cells | maker datasheet |
| TPS61288 | boost | 15 A switch, 500 kHz | higher-power boost | maker datasheet |
| MP3429 | boost | 21.5 A current limit | high-power lights (named in driver efficiency tests) | [BLF thread](https://budgetlightforum.com/t/efficiency-measurements-of-flashlight-drivers-update-sc70/68528) |
| TPS63020 | buck-boost | 1.8-5.5 V in, 2 A out at 3.3 V (4 A switch), 25 µA quiescent | constant output over the whole discharge, moderate power | [TI](https://ti.com/product/TPS63020) |
| TPS63802 | buck-boost | 1.3-5.5 V in, 2 A out, 11 µA quiescent | small lights with constant output | maker datasheet |

**How to decide.** Plot the cell voltage over the discharge (4.2 V to the low-voltage cut-off,
under load) against the LED's forward voltage at the planned current. If the LED voltage sits
inside the cell's range (one Li-ion cell and a white LED), a buck regulates for most of the
discharge and runs at 100 % duty near the end, and a linear regulator is simpler but wastes
(Vcell - Vf) × I. If the LED voltage is above the cell's range (6 V LED, one cell), use a boost.
For constant output to the very end at moderate power, use a buck-boost. A FET direct drive is
the cheapest way to the highest peak, but its output falls with the cell voltage and the
lowest modes depend on PWM.

**Traps.** An inductor whose saturation current is below the peak current; a buck that drops
out of regulation earlier than expected because of resistance in springs and traces
([BAT-8](design-rules.md#bat-8)); an enable pin left on in standby (35 µA for the TLV62585 is
more than the whole standby budget of an 800 mAh light); low-level instability.

## Microcontrollers

**What matters:** supply voltage (can it run straight from a Li-ion cell, or does it need a
regulator, which adds standby current?), sleep current ([BAT-6](design-rules.md#bat-6)), PWM
resolution and frequency ([LED-6](design-rules.md#led-6), [LED-7](design-rules.md#led-7)), ADC
for voltage and temperature, programming interface ([DRV-9](design-rules.md#drv-9)), memory,
wireless needs, price and stock, and firmware support.

| MCU | Core | Flash / RAM | Supply | Sleep current | Notes | Price (LCSC, Oct 2026) | LuxLibre |
|---|---|---|---|---|---|---|---|
| ATtiny1616 | AVR, up to 20 MHz (at 4.5-5.5 V) | 16 KB / 2 KB | 1.8-5.5 V | 0.1 µA typ power-down | 10-bit ADC, UPDI, the MCU of many enthusiast drivers | $2.92 (1 pc), out of stock | port, builds |
| CH32V003 | RISC-V RV32EC, 48 MHz | 16 KB / 2 KB | 2.7-5.5 V | 8.76 µA standby (3.3 V, LSI off) | 10-bit ADC, one-wire SWIO programming | $0.25 (5 pcs), $0.13 (4000 pcs) | port, builds |
| PY32F002A | Cortex-M0+, 24 MHz | 20 KB / 3 KB | 1.7-5.5 V | about 5 µA stop | 12-bit ADC, SWD | $0.41 (5 pcs), $0.20 (5000 pcs) | not yet |
| ESP32-C3-MINI-1 | RISC-V, 160 MHz, module | 4 MB / 400 KB | 3.0-3.6 V | 5 µA deep sleep | Wi-Fi and Bluetooth LE 5, USB serial/JTAG | $1.29 (1 pc) | port, experimental |
| nRF52832 | Cortex-M4F, 64 MHz | 512 KB / 64 KB | 1.7-3.6 V | 0.3 µA System OFF | Bluetooth LE | $4.03 (1 pc) | not yet |
| STM32C011F6 | Cortex-M0+, 48 MHz | 32 KB / 6 KB | 2.0-3.6 V | see datasheet | 12-bit ADC, SWD | $1.49 (1 pc) | not yet |

Sources: [ATtiny1616](https://www.microchip.com/content/dam/mchp/documents/MCU08/ProductDocuments/DataSheets/ATtiny1614-16-17-DataSheet-DS40002204A.pdf),
[CH32V003](https://lcsc.com/product-detail/C5346354.html),
[PY32F002A](https://www.lcsc.com/de/product-detail/C5292058.html),
[ESP32-C3-MINI-1](https://documentation.espressif.com/esp32-c3-mini-1_datasheet_en.html);
the others from their makers' datasheets.

**Rules of thumb.** LuxLibre needs about 11 KB of flash and 0.5 KB of RAM today, so 16 KB parts
fit with room for board features. An MCU that runs straight from the cell (ATtiny1616,
CH32V003, PY32F002A) saves a regulator and its standby current. Choose a wireless MCU only when
the requirements ask for an app, and budget its standby current honestly. The CH32V003 port keeps
its low-speed oscillator on for the wake-up timer, so its real standby current is a little
above the datasheet's LSI-off figure: measure it.

## Chargers and protection

**What matters:** charge current ([CHG-2](design-rules.md#chg-2)), heat (a linear charger
burns (VBUS - Vcell) × I: at 5 V, 3.7 V and 1 A that is 1.3 W inside the light), a temperature
input ([CHG-3](design-rules.md#chg-3)), input voltage rating and over-voltage protection
([CHG-4](design-rules.md#chg-4)), status outputs for the indicator, and power path (running the
light while charging).

| Part | Type | Key data |
|---|---|---|
| TP4056 | linear | 1 A, SOP-8 |
| TP4057 | linear | 0.5 A, SOT-23-6, 6.5 V absolute maximum input |
| MCP73831 | linear | 0.5 A, SOT-23-5 |
| IP2312 | switching | 3 A, 6.5 V absolute maximum input, ESOP-8 |
| BQ25601 | switching | 3 A, NTC input |
| BQ24075 | linear with power path | 1.5 A, 28 V absolute maximum input |

Protection for built-in cells ([BAT-3](design-rules.md#bat-3)): DW01A controller with an FS8205A
dual MOSFET (27 mΩ at 4.5 V gate drive; typical DW01A thresholds 4.30 V over-charge,
2.40 V over-discharge), or an integrated part such as the XB5333A (4.30 V / 2.4 V, 3 A
over-current, 58 mΩ, SOT-23-5). High-current lights need protection rated for the turbo current,
or protected cells. Check all values in the datasheet of the exact part you buy.

Every USB-C receptacle that charges needs one 5.1 kΩ resistor per CC pin
([CHG-1](design-rules.md#chg-1)). Six-pin "power only" USB-C receptacles are easier to solder but
carry no data lines, so they cannot be used for a USB console or firmware updates over USB.

## Sensors, switches and small parts

- **Temperature sensor** ([THM-4](design-rules.md#thm-4)): an NTC thermistor (the FlashKa uses
  100 kΩ, B = 4250 K, with a 100 kΩ resistor to the reference) close to the LED board or driver,
  or the MCU's internal sensor when the MCU sits there. `lux_calc.py ntc --table` shows the
  resolution per ADC step; [firmware/hal/lx_ntc.h](../firmware/hal/lx_ntc.h) turns the reading
  into degrees.
- **Switch:** LuxLibre needs an electronic switch (a small tactile button read by the MCU). A
  mechanical tail switch that carries the whole current needs no standby power but cannot offer
  lockout, ramping or battery check; some lights combine both.
- **Capacitors:** derate ceramics for DC bias ([DRV-4](design-rules.md#drv-4)).
- **Resistors:** 1 % or better in voltage dividers ([BAT-9](design-rules.md#bat-9)); the current
  sense resistor needs a power rating for the turbo current (P = I² × R) and a low temperature
  coefficient.
- **ESD diodes** at every exposed conductor ([CHG-5](design-rules.md#chg-5)).

## Housing and materials

- **Aluminium 6061-T6** with hard anodising is the default for anything above about 1 W
  sustained ([MEC-1](design-rules.md#mec-1)); the FlashKa body and lid are CNC-machined 6061-T6,
  bead-blasted and black anodised.
- **Copper** heads spread heat best but are heavy; **titanium** and **stainless steel** look and
  wear well but conduct heat poorly; **plastic** housings limit the sustained output.
- **3D printing:** resin or nylon prints are fine for prototypes, fit checks and small parts
  (the FlashKa's light guides and button cap are printed in translucent resin). Thermal tests on
  a plastic prototype do not predict the metal light.
- Estimate the heat budget from the outer surface before choosing the LED current
  ([THM-2](design-rules.md#thm-2)).

---

## Worked example: a 1200 lm 18650 light

An everyday-carry light with one 18650 cell, at least 1200 lm at 30 s, a sustained output that
is honest about heat, and USB-C charging. The numbers below come from the datasheets in this
guide, [tools/lux_calc.py](../tools/lux_calc.py) and the LuxLibre simulator. Scores are
illustrative: your weights may differ.

### Step 1: requirements (summary)

| ID | Requirement | Target |
|---|---|---|
| R1 | Output at 30 s (FL 1) | ≥ 1200 lm |
| R2 | Surface temperature | ≤ 48 °C continuous, ≤ 51 °C peak ([THM-1](design-rules.md#thm-1)) |
| R3 | Cell | one 18650, user-replaceable ([BAT-2](design-rules.md#bat-2)) |
| R4 | Size | about 25 mm × 120 mm, aluminium |
| R5 | Charging | USB-C in the light, full in under 3 h |
| R6 | Water and impact | IPX7, 1 m drop |
| R7 | Colour | 4000-5000 K, CRI ≥ 70 (90 preferred) |
| R8 | Standby | ≤ 3 % per month ([BAT-6](design-rules.md#bat-6)) |

### Step 2: check the physics first

The heat budget does not depend on the parts. A 25 × 120 mm anodised cylinder has about
104 cm² of surface:

```console
$ python3 tools/lux_calc.py thermal --diameter-mm 25 --length-mm 120 --mass-g 80 --heat-w 14
```

It can lose about 2.6 W continuously at a 23 K rise ([THM-2](design-rules.md#thm-2)). In turbo
the light makes roughly 12.5-14 W of heat: about 17.5 W input with a 90 % switching driver, or
about 19 W with a linear regulator on a full cell (4.0 V × 4.8 A), minus about 5 W that leaves as
light. An 80 g light then reaches the 48 °C surface limit after about 130-150 s in the lumped
model ([THM-3](design-rules.md#thm-3)). So: 1200 lm at 30 s is realistic, 1200 lm for ten minutes is
not, and the sustained output will be a few hundred lumens. Writing this down now prevents a
specification the light cannot meet.

### Step 3: LED

Limits: clearly more than 1200 lm emitted at 85 °C (the optic loses part of it), at most 80 %
of the maximum current.

| Candidate | Data | Screen |
|---|---|---|
| SST-40 (CRI 70) | 1446-1861 lm at 5 A, 85 °C; max 6 A, so 4.8 A allowed | passes |
| XHP50.3 HI (CRI 70-95) | 970-1120 lm at 6 V, 1.4 A, 85 °C; max 3 A | passes with more current; needs a 6 V driver |
| 3 × Nichia 519A (Ra 90) in a triple optic | 730 lm typ each at 1.4 A, 25 °C pulsed | passes on paper; check the 85 °C curve; three LEDs on one board |
| SST-20 | min 530-585 lm at 1.5 A, 85 °C; max 3 A | fails: one LED cannot reach 1200 lm within 80 % of 3 A |

Scoring (illustrative): the SST-40 wins on simplicity and cost with a 3 V driver; the triple
519A wins on colour; the XHP50.3 HI wins if a boost driver is planned anyway. This example takes
the **SST-40 at up to 4.8 A** and notes the 519A triple as the high-CRI variant.

### Step 4: cell

Turbo cell current depends on the driver (step 5). With a switching driver at 90 % efficiency,
4.8 A at about 3.3 V is 15.7 W at the LED and 17.5 W from the cell; with 50 mΩ of cell
resistance that is 5.24 A at 3.34 V under load:

```console
$ python3 tools/lux_calc.py cellcurrent --led-a 4.8 --vf0 2.8 --rs 0.10 --driver-eff 0.9 --cell-v 3.6 --r-int 0.05 --cell-max-a 15
```

With a linear regulator the cell current simply equals the LED current, 4.8 A. The table uses
the larger value:

| Candidate | Capacity | 70 % of rating | Margin at 5.2 A | Charge window |
|---|---|---|---|---|
| Samsung 30Q | 3000 mAh | 10.5 A | good | 0-50 °C |
| Molicel P28A | 2800 mAh | 24.5 A | very large | 0-60 °C |
| Murata VTC6 | 3000 mAh | 10.5 A | good | retailer data only |

Both datasheet cells pass. The 30Q gives more runtime, the P28A more margin; users will fit
other cells anyway, so the firmware limit is set for a 15 A cell: `BAT_MAX_MA` = 10000.

### Step 5: driver

The LED needs about 3.3 V at 4.8 A; the cell gives 4.2 V down to about 3.0 V under load. The
LED voltage sits inside the cell's range, so:

| Option | Regulation over the discharge | Efficiency | Cost and size | Low modes |
|---|---|---|---|---|
| FET direct drive | none: output follows the cell | high in turbo | lowest | PWM only |
| Linear regulator (MOSFET + op-amp + sense resistor) | while Vcell > Vf + dropout | Vf / Vcell (about 80 %) | low | good with current control |
| Buck, 5-6 A class | until Vcell nears Vf, then 100 % duty | about 90 % | medium; few small parts at this current | good |
| Boost + 6 V LED (XHP50.3) | to the end of the discharge | about 90 % | medium; larger inductor | good |

This example takes the **linear current regulator**: simple, cheap, regulated for most of the
discharge, with stable low modes. Its price is heat: on a full cell it burns
(4.0 V - 3.3 V) × 4.8 A ≈ 3.4 W in the MOSFET, which shortens turbo (step 2) but is handled by
the thermal regulator. The decision matrix example in
[templates/decision-matrix.md](../templates/decision-matrix.md) works through the same
question and shows that the result is sensitive to the weights, which is a reason to measure a
prototype.

### Step 6: MCU, charger and the rest

- **MCU:** CH32V003: runs from the cell, LuxLibre port available, about $0.25. The ATtiny1616
  is the alternative with the most firmware history, but it was out of stock when this was
  written ([DFM-6](design-rules.md#dfm-6)). No app was required, so no wireless MCU.
- **Charger:** a switching charger such as the IP2312 (up to 3 A, less heat than a linear one);
  3000 mAh at 1.5 A charges in roughly 2.5 h including the CV phase. Add a TVS diode
  ([CHG-4](design-rules.md#chg-4)), two 5.1 kΩ CC resistors ([CHG-1](design-rules.md#chg-1)),
  ESD diodes ([CHG-5](design-rules.md#chg-5)) and an NTC near the cell or the driver.
- **Reverse-polarity protection:** a P-channel MOSFET in the supply ([BAT-4](design-rules.md#bat-4)).
- **Standby budget:** 3000 mAh × 3 % / 730 h = 123 µA; the CH32V003 in standby, the charger and
  the dividers fit easily if the driver is switched off ([BAT-6](design-rules.md#bat-6)).

### Step 7: board header and simulation

The choices become a LuxLibre board header ([firmware/porting.md](firmware/porting.md));
an excerpt:

```c
#define LX_BOARD_NAME "Example 18650 EDC"
#define LX_OUT_MIN_Q16 64            // level 1 = 1/1024 of full scale (lowest stable output)
#define LX_MAIN_MAX_MA 4800          // level 150: 80 % of the SST-40's 6 A maximum (LED-2); set to the measured value
#define LX_LED_VF0_MV 2800           // LED model: V = 2.8 V + 0.10 V/A x I (measure!)
#define LX_LED_RS_MOHM 100
#define LX_DRIVER_EFF_PCT 78         // linear regulator: Vf at turbo / 4.2 V, so the turbo cell current is not underestimated
#define LX_DEF_RAMP_CEIL 130         // about 1.9 A
#define LX_DEF_TURBO_LVL 150         // 4.8 A
#define LX_DEF_BAT_MAX_MA 10000      // 70 % of a 15 A cell (BAT-1)
#define LX_DEF_THM_LIMIT 50          // replace with 48 + measured sensor-to-surface difference
```

The simulator's 18650 model (an 80 g class aluminium light) with a 4.8 A LED predicts, for turbo
without a timer:

```console
$ cd firmware && make sim && build/luxsim --preset 18650 --imax 4.8 --set TURBO_S=0 "2C W600000"
simulated 602.7 s
peak output       1561 lm
output at 30 s    1509 lm   (ANSI FL 1 measures from 30 s)
output at 120 s   1158 lm
peak sensor       50.9 degC
final           level 122, 385 lm, 50.5 degC, 4.04 V, 90 %
```

This is a model, not a measurement: it shows that R1 is reachable and that the sustained output
will be around 400 lm. The model assumes a 90 % efficient driver; the linear regulator's extra
heat on a full cell makes the real step-down come somewhat earlier. The prototype's measurements ([testing.md](testing.md)) replace these
numbers in the specification.

### Step 8: record and review

One design-log record per step, then the review checklist
([templates/design-review-checklist.md](../templates/design-review-checklist.md)) before the
boards are ordered.

### The second example: FlashKa

The FlashKa keychain light went through the same steps with very different limits: a
20 × 16 mm cross-section, two small pouch cells, a Luminus SST-20 at up to 2.2 A from a TLV62585
buck with a current loop, an ESP32-C3 for the Bluetooth app, and a Class 2 laser behind a
hardware interlock. Its folder [hardware/flashka-keychain-v05/](../hardware/flashka-keychain-v05/README.md)
lists the parts, the reasons and the known limitations.

---

## Cost: the BOM is not the price

For a single prototype, the parts are a small share of the money. One FlashKa v0.5 delivered to
Lithuania cost $529.63; the electronic parts for two boards were $17.16 of that. Shipping, VAT,
customs duty and fees were 41 %, and assembly fees (setup per side, loading fees per unique part,
stencils, X-ray) were $127.15. Five lights cost about $196 each because these fixed costs are
shared. [DFM-1](design-rules.md#dfm-1) to [DFM-5](design-rules.md#dfm-5) list what to change
in the design to bring this down; the full breakdown is in the
[FlashKa folder](../hardware/flashka-keychain-v05/README.md#cost).

## Search tools and AI assistants

Search engines and AI assistants are fast at finding candidates and summarising datasheets, and
they also make mistakes with confidence. Use them for step 2 (candidates), never for the numbers
in step 3 onwards without checking the datasheet yourself.

A useful request names the limits and asks for sources:

```text
I am designing a single-cell 18650 flashlight. I need a buck LED driver IC:
input 2.9-4.2 V, LED current up to 5 A, LED forward voltage about 3.3 V, 100 % duty cycle
allowed, package at least 0.5 mm pitch, available at LCSC. List 5 candidates in a table with
input range, maximum current, quiescent current, package and a link to the maker's datasheet
for each. Mark any value you are not sure of. Do not include parts without a datasheet.
```

Then open every datasheet and copy the numbers yourself. Record in the design log which numbers
came from where ([REQ-3](design-rules.md#req-3)).
