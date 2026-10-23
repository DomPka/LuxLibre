<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
# LuxLibre tools

`lux_calc.py` is a small command-line calculator for choosing flashlight parts. Each
subcommand checks one number that a [design rule](../docs/design-rules.md) asks for:
standby drain, cell current, beam distance, heat, trace width, battery divider and NTC
thermistor. It needs Python 3.8 or newer and nothing outside the standard library.

```sh
python3 tools/lux_calc.py -h                 # list of subcommands
python3 tools/lux_calc.py thermal -h         # options of one subcommand
python3 -m unittest tools/test_lux_calc.py   # run the tests (from the repository root)
```

The tool gives estimates for comparing parts. It does not replace the datasheet or a
measurement of the finished light (see [docs/testing.md](../docs/testing.md)).

## Common behaviour

- Every result is a short list of labelled values with units, then one `formula:` line
  with the equation used, then notes.
- `--json` prints the same result as JSON for scripts. It works before or after the
  subcommand name. Values that are infinite or not available become `null`.
- Resistances accept the suffixes `k` and `M`: `100k`, `4.7k`, `1M`.
- Bad input (a negative capacity, two modes at once) prints an error and exits with code 2.
- The functions in `lux_calc.py` are pure and documented, so other scripts can
  `import lux_calc` and call, for example, `lux_calc.trace_width(3.0)`.

### Defaults

Some defaults are standards or come from a source. Others are LuxLibre defaults: project
choices for a first estimate. Replace them with datasheet values as soon as you have them.

| Option | Default | Kind |
|---|---|---|
| `standby --percent-per-month` | 3 | [BAT-6](../docs/design-rules.md#bat-6) limit |
| `runtime --cell-v` | 3.6 V | Li-ion nominal voltage |
| `runtime --usable` | 0.9 | LuxLibre default |
| `--driver-eff` | 0.9 | LuxLibre default |
| `--vf0`, `--rs` | 2.75 V, 0.15 Ω | LuxLibre default, a straight-line fit; use the LED datasheet curve |
| `cellcurrent --r-int` | 0.05 Ω | LuxLibre default; check the cell datasheet |
| `throw --optic-eff` | 0.7 | LuxLibre default |
| `thermal --finish` | anodised, h = 11 W/m²K (bare 6.5) | derived values, see [thermal](#thermal) |
| `thermal --ambient` | 25 °C | test condition of [THM-6](../docs/design-rules.md#thm-6) |
| `thermal --surface-max` | 48 °C | [THM-1](../docs/design-rules.md#thm-1), ISO 13732-1 metal, 10 min contact ([CENELEC Guide 29](https://boss.cenelec.eu/media/Guides/CLC/29_cenelecguide29.pdf)) |
| `thermal --material` | aluminium | typical specific heat values; check your alloy |
| `trace --oz`, `--rise-c` | 1 oz, 10 °C | the [DRV-5](../docs/design-rules.md#drv-5) check case |
| `divider --tolerance-pct` | 1 % | common resistor tolerance |
| `ntc --adc-bits` | 12 | common ADC resolution |

## Subcommands

| Subcommand | What it gives | Design rule |
|---|---|---|
| [`standby`](#standby) | largest standby current, or drain per month | [BAT-6](../docs/design-rules.md#bat-6) |
| [`runtime`](#runtime) | runtime at a constant LED power or current | [REQ-2](../docs/design-rules.md#req-2) |
| [`cellcurrent`](#cellcurrent) | current from the cell and its voltage under load | [BAT-1](../docs/design-rules.md#bat-1) |
| [`throw`](#throw) | peak intensity, beam distance, lux | [REQ-2](../docs/design-rules.md#req-2) |
| [`thermal`](#thermal) | sustainable heat, turbo time | [THM-2](../docs/design-rules.md#thm-2), [THM-3](../docs/design-rules.md#thm-3) |
| [`trace`](#trace) | PCB trace width (IPC-2221) | [DRV-5](../docs/design-rules.md#drv-5) |
| [`divider`](#divider) | battery-voltage divider check or suggestion | [BAT-9](../docs/design-rules.md#bat-9) |
| [`ntc`](#ntc) | NTC resistance, temperature, ADC reading | [THM-4](../docs/design-rules.md#thm-4) |

### standby

Supports [BAT-6](../docs/design-rules.md#bat-6): standby drain at most 3 % of the capacity
per month. Standby current is what the light draws while it is off (MCU asleep, protection
IC, dividers).

- `--capacity-mah C` (required) and `--percent-per-month` (default 3) give the largest
  allowed current: I = C × pct/100 / 730 h × 1000 µA. 730 h is one average month
  (8760 h / 12).
- Add `--current-ua I` with a measured current to get the drain in % per month, the months
  from full to empty, and a BAT-6 pass/fail.

```console
$ python3 tools/lux_calc.py standby --capacity-mah 800
Standby drain (BAT-6)
  capacity             800 mAh
  allowed drain        3 % per month
  max standby current  32.9 µA
  formula: I_max = C * pct/100 / 730 h * 1000  [µA]
  note: 730 h = one average month. Measure the real standby current.
```

With `--json` (here for a measured 12 µA):

```console
$ python3 tools/lux_calc.py standby --capacity-mah 800 --current-ua 12 --json
{
  "command": "standby",
  "capacity_mah": 800.0,
  "current_ua": 12.0,
  "bat6_ok": true,
  "percent_per_month": 1.095,
  "months_to_empty": 91.32420091324201,
  "formula": "pct = I/1000 * 730 h / C * 100;  months = 100 / pct",
  "notes": [
    "730 h = one average month. Measure the real standby current."
  ]
}
```

### runtime

Helps with [REQ-2](../docs/design-rules.md#req-2) before a prototype exists. It assumes
the driver holds a constant power until the usable energy is gone.

- `--capacity-mah C` (required), `--cell-v` (default 3.6 V), `--usable` (default 0.9).
- The LED load is either `--led-w P` or `--led-a I`. With `--led-a` the forward voltage
  (the voltage across the LED) comes from a straight line Vf = vf0 + rs × I, set with
  `--vf0` and `--rs`.
- `--driver-eff` (default 0.9): P_in = P_led / eff, hours = C/1000 × cell_v × usable / P_in.

Example: a 3000 mAh cell such as the Samsung 30Q
([datasheet](https://e2e.ti.com/cfs-file/__key/communityserver-discussions-components-files/196/samsung_5F00_30q_5F00_data_5F00_sheet.pdf))
driving an LED at 1.5 A:

```console
$ python3 tools/lux_calc.py runtime --capacity-mah 3000 --led-a 1.5
Runtime estimate at constant power (REQ-2)
  LED current          1.5 A
  LED Vf (vf0 + rs*I)  2.98 V
  LED power            4.46 W
  driver efficiency    90 %
  input power          4.96 W
  energy used          9.72 Wh (3000 mAh x 3.6 V x 0.9)
  runtime              1.96 h (118 min)
  formula: P_in = P_led / eff;  t = C/1000 * cell_v * usable / P_in  [h]
  note: Constant-power estimate. FL 1 runtime (to 10 % of the 30 s output) must be measured.
```

The ANSI/PLATO FL 1 runtime is measured from the 30 s output until the output falls to
10 % of it ([Lupine](https://www.lupine.de/about_lupine/fl1-standard)). Thermal step-down
changes it a lot, so treat this result as a first estimate only.

### cellcurrent

Supports [BAT-1](../docs/design-rules.md#bat-1): continuous cell current at most 70 % of
the rated maximum. The cell has an internal resistance R, so its voltage drops under load
and the current rises.

- LED load as in `runtime` (`--led-w` or `--led-a` with `--vf0`, `--rs`), `--driver-eff`.
- `--cell-v V` (required): cell voltage at the state of charge you care about. A low cell
  gives the highest current.
- `--r-int` (default 0.05 Ω): add contact and spring resistance if you know it.
- `--cell-max-a A`: the datasheet maximum continuous current. The tool then prints the
  share of the rating and the BAT-1 verdict.
- The tool solves P_in = (V − I×R) × I and takes the smaller root. If there is no real root,
  it says the cell cannot deliver that power and prints the maximum, V²/(4R).

Example: 3 A into the LED from a cell at 3.6 V rated 15 A continuous (the Samsung 30Q
rating at 25 °C, [datasheet](https://e2e.ti.com/cfs-file/__key/communityserver-discussions-components-files/196/samsung_5F00_30q_5F00_data_5F00_sheet.pdf)):

```console
$ python3 tools/lux_calc.py cellcurrent --led-a 3 --cell-v 3.6 --cell-max-a 15
Cell current (BAT-1)
  LED current              3 A
  LED Vf (vf0 + rs*I)      3.20 V
  LED power                9.60 W
  input power              10.7 W (eff 90 %)
  cell current             3.10 A
  cell voltage under load  3.45 V
  share of cell rating     20.6 % of 15 A
  BAT-1 (<= 70 %)          pass
  formula: P_in = (V - I*R) * I, smaller root I = (V - sqrt(V^2 - 4*R*P_in)) / (2*R)
  note: Add contact and spring resistance to --r-int if known.
```

Set the firmware parameter `BAT_MAX_MA` from this result (see
[docs/firmware/parameters.md](../docs/firmware/parameters.md)).

### throw

Supports [REQ-2](../docs/design-rules.md#req-2). Peak intensity in candela (cd) is the
brightness at the centre of the beam. ANSI/PLATO FL 1 defines the beam distance as the
distance where the light falls to 0.25 lx, which is 2 × √cd metres
([Lupine](https://www.lupine.de/about_lupine/fl1-standard)). Give exactly one of three
modes:

- `--cd X`: beam distance, and the illuminance at `--at-m` (default 1 m), E = cd / d².
- `--lux L --distance-m d`: a lux-meter reading at a known distance. cd = L × d², then the
  beam distance. FL 1 measures at 2, 10 or 30 m.
- `--lumens F --die-mm2 A --optic-mm D` with `--optic-eff` (default 0.7): an estimate from
  the parts. The source luminance (brightness per area of the LED die, Lambertian:
  equally bright from every angle) is L = F / (π × A), and cd = eff × L × π × (D/2)². This
  is an upper bound for a reflector or TIR optic filled by the source. As a rule of thumb,
  not a standard, real lights reach roughly 50-80 % of it.

```console
$ python3 tools/lux_calc.py throw --lux 250 --distance-m 2
Throw (REQ-2, ANSI/PLATO FL 1)
  reading                  250 lx at 2 m
  peak intensity           1000 cd
  beam distance (0.25 lx)  63.2 m
  formula: cd = E * d^2;  beam = 2 * sqrt(cd)  [m]
```

### thermal

Supports [THM-2](../docs/design-rules.md#thm-2) (sustainable heat from the outer surface)
and [THM-3](../docs/design-rules.md#thm-3) (turbo duration from thermal mass).

Surface and steady state:

- `--area-cm2 A`, or `--diameter-mm d --length-mm L` for a cylinder: side π×d×L plus two
  ends 2×π×(d/2)².
- `--finish anodised` (h = 11 W/m²K, default) or `bare` (6.5 W/m²K), or `--h` for your own
  value. h is the heat transfer coefficient: watts shed per square metre per kelvin of
  temperature difference. Both values are for still air and include radiation. They are
  derived values: free convection in gases is 2-25 W/m²K
  ([Incropera, via MTU](https://pages.mtu.edu/~fmorriso/cm3120/typical_values_heat_transfer_coefficient.pdf)),
  radiation adds about 5-6 W/m²K near 50 °C
  ([Electronics Cooling](https://www.electronics-cooling.com/2001/02/dont-underestimate-radiation-in-electronic-cooling/)).
  For a 25 mm cylinder at 45 °C in 25 °C air this gives about 5.9 + 5.1 ≈ 11 W/m²K
  anodised, about 6.5 W/m²K bare aluminium.
- `--ambient` (default 25 °C), `--surface-max` (default 48 °C).
- Result: P = h × A × (Tmax − Tamb), the heat the light can shed for as long as you like.

Turbo timing (lumped model: the whole body at one temperature, starting at ambient):

- `--mass-g m`, `--material` (aluminium 0.90, copper 0.385, brass 0.38, stainless 0.50,
  titanium 0.52 J/gK; typical values, check your alloy) or `--c`, and `--heat-w Q`.
- R = 1/(h×A) K/W, C = m×c J/K, tau = R×C s, steady rise Q×R. The time to reach the limit
  is t = −tau × ln(1 − (Tmax − Tamb)/(Q×R)). If Q×R is not above Tmax − Tamb, the surface
  never reaches the limit.

Heat helper: `--input-w W --lumens F` gives heat = W − F/320. 320 lm per optical watt is an
approximation of the luminous efficacy of radiation of a white LED. If `--heat-w` is not
given, this heat is used for the turbo timing.

Example: a 25 mm × 90 mm anodised aluminium body of 60 g, turbo with 10 W into the LED
giving 1000 lm:

```console
$ python3 tools/lux_calc.py thermal --diameter-mm 25 --length-mm 90 --mass-g 60 --input-w 10 --lumens 1000
Thermal (THM-2, THM-3)
  heat from 10 W and 1000 lm  6.88 W
  surface area (cylinder)     80.5 cm² (25 x 90 mm)
  h (anodised)                11 W/m²K
  ambient / surface limit     25 / 48 °C
  sustainable heat            2.04 W
  mass / c (aluminium)        60 g / 0.9 J/gK
  heat in turbo               6.88 W
  R, C, tau                   11.3 K/W, 54.0 J/K, 610 s
  steady-state surface        103 °C
  time to surface limit       214 s (3.57 min)
  formula: heat = W - F/320;  P = h * A * (Tmax - Tamb);  R = 1/(h*A), C = m*c, t = -R*C * ln(1 - (Tmax-Tamb)/(Q*R))
  note: 320 lm per optical watt is an approximation for white LEDs.
  note: h for still air (convection + radiation), derived values; see THM-2. Verify with the THM-6 test.
  note: Lumped model: the whole body at one temperature, starting at ambient. The LED and driver get hotter than the surface.
```

THM-3 asks you to state turbo duration honestly: a real body is not at one temperature, a
hand adds cooling, a pocket removes it. Confirm with the
[THM-6](../docs/design-rules.md#thm-6) test.

### trace

Supports [DRV-5](../docs/design-rules.md#drv-5): size copper for current. Uses the IPC-2221
formula for the trace cross-section:

- `--current-a I` (required), `--oz` copper weight (default 1 oz, 1.378 mil thick per oz),
  `--rise-c` allowed temperature rise (default 10 °C), `--layer external|internal`.
- area = (I / (k × dT^0.44))^(1/0.725) mil², k = 0.048 external, 0.024 internal;
  width = area / thickness. 1 mil = 0.0254 mm.

```console
$ python3 tools/lux_calc.py trace --current-a 3
PCB trace width, IPC-2221 (DRV-5)
  current           3 A
  copper / layer    1 oz, external
  temperature rise  10 °C
  cross-section     74.2 mil²
  thickness         1.38 mil
  width             53.8 mil = 1.37 mm
  formula: A = (I / (k * dT^0.44))^(1/0.725) mil², k = 0.048 (external); w = A / (1.378 * oz)
  note: IPC-2152 is the newer method; IPC-2221 is conservative for outer layers.
```

The results match the DRV-5 values (1 A 0.30 mm, 3 A 1.37 mm, 5 A 2.77 mm), which agree
with the [Farnell calculator](https://uk.farnell.com/pcb-trace-width).

### divider

Supports [BAT-9](../docs/design-rules.md#bat-9): battery voltage measured to 1 % after
calibration. A resistor divider (r-top from the battery to the ADC pin, r-bottom from the
pin to ground) scales the battery voltage below the ADC reference.

- `--v-max V` (highest battery voltage) and `--adc-ref Vref` are required.
- With `--r-top` and `--r-bottom`: the ratio Rb/(Rt+Rb), the voltage at the pin at v-max
  and whether it fits under the reference, the divider current at v-max, and the
  worst-case ratio error with both resistors at opposite ends of `--tolerance-pct`.
- Without resistors: a suggestion from the E24 series (the standard set of 24 resistor
  values per decade) with a total near 1 MΩ (0.8-1.25 MΩ) and at least 10 % headroom
  under the reference, followed by the same check.

```console
$ python3 tools/lux_calc.py divider --v-max 4.2 --adc-ref 1.1
Battery voltage divider (BAT-9)
  target ratio (10 % headroom)  0.2357
  suggested r-top (E24)         910 kΩ
  suggested r-bottom (E24)      270 kΩ
  ratio                         0.2288
  ADC pin at 4.2 V              0.9610 V (reference 1.1 V)
  fits under reference          yes, 12.6 % headroom
  divider current               3.56 µA at v-max
  worst-case ratio error        1.55 % (1 % resistors)
  formula: ratio = Rb/(Rt+Rb);  V_adc = v_max * ratio;  I = v_max/(Rt+Rb);  error with Rt, Rb at opposite tolerance limits
  note: Advice: a high-value divider needs a capacitor at the ADC pin (e.g. 100 nF) so the ADC sample-and-hold sees a low source impedance.
  note: BAT-9 asks for <= 1 % error after calibration with BAT_CAL.
```

The divider current counts towards the standby budget of
[BAT-6](../docs/design-rules.md#bat-6). Calibrate with the `BAT_CAL` parameter.

### ntc

Supports [THM-4](../docs/design-rules.md#thm-4). An NTC thermistor is a resistor whose
resistance falls as it gets warmer. The beta equation links resistance and temperature:
1/T = 1/298.15 + ln(R/R25)/B, with T in kelvin, R25 the resistance at 25 °C and B the beta
constant from the datasheet.

- `--r25 R` and `--beta B` are required. Give exactly one mode:
- `--temp-c T`: the NTC resistance. With `--r-fix Rf` (resistor from the ADC reference to
  the pin, NTC from the pin to ground) and `--adc-bits` (default 12) it also prints the
  ratio r = Rntc/(Rfix+Rntc), the ADC code r × 2^bits, and the sensitivity in °C per LSB
  (one ADC step), from a numerical derivative.
- `--ohms R`: the temperature for a measured resistance.
- `--table`: a table from −20 to 100 °C in 10 °C steps (with ADC columns if `--r-fix` is
  given).

```console
$ python3 tools/lux_calc.py ntc --r25 100k --beta 4250 --temp-c 50 --r-fix 100k
NTC thermistor, beta equation (THM-4)
  R25 / beta                      100 kΩ / 4250 K
  r-fix (reference to pin) / ADC  100 kΩ / 12 bit
  temperature                     50 °C
  NTC resistance                  33.2 kΩ
  ADC ratio                       0.2492
  ADC code                        1021 of 4096
  sensitivity                     0.0321 °C per LSB
  formula: 1/T = 1/298.15 + ln(R/R25)/B  (T in K);  r = Rntc/(Rfix+Rntc), code = r * 2^bits
  note: Calibrate THM_OFFSET and the sensor-to-surface difference (THM-4).
```

The beta equation is an approximation over a limited range. Check it against the
resistance table in the thermistor datasheet, then calibrate `THM_OFFSET`.

## Tests

`test_lux_calc.py` checks the values given in the design rules (32.9 µA and 123 µA for
BAT-6, the DRV-5 trace widths, 33.2 kΩ for a 100 kΩ B4250 NTC at 50 °C), round trips
(NTC temperature to resistance and back, lux to cd to beam distance), the formulas against
hand calculations, and every subcommand in text and JSON form. Run it from the repository
root with either command:

```sh
python3 -m unittest tools/test_lux_calc.py
python3 tools/test_lux_calc.py
```

## Comparison charts

`comparison_charts.py` draws the charts of [docs/comparison.md](../docs/comparison.md) from
[docs/data/flashlights.json](../docs/data/flashlights.json), in a light and a dark version. It needs
matplotlib.

```sh
python3 tools/comparison_charts.py           # writes docs/img/compare_*_{light,dark}.png
```
