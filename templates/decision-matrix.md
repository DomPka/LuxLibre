<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
# Weighted decision matrix

## How to use

Use a matrix when a choice has several good options and no obvious winner. First remove
options that break a hard limit (must-pass screen). Then pick 4-7 criteria taken from your
requirements, give them weights that sum to 100 %, write down what each score 1-5 means for
each criterion before you score, and score every option. Weighted total =
sum of (weight % x score) / 100, so it ranges from 1.00 to 5.00. Finish with the sensitivity
check; if the winner changes, the result is not robust and you need better data or a clearer
requirement. Copy the result into the decision record in [design-log.md](design-log.md). A
spreadsheet version is in [decision-matrix.csv](decision-matrix.csv).

Choosing criteria:

- Take them from the requirement sheet ([requirements.md](requirements.md)); name the
  requirement ID.
- Keep them independent (do not count the same property twice, e.g. "part count" and "size").
- Hard limits belong in the screen, not in the scores.
- 4-7 criteria. Fewer hides trade-offs; more makes every weight too small to matter.

## Form

**Decision:** D-`<nn>` `<question>`  **Date:** `<YYYY-MM-DD>`  **By:** `<...>`

### 1. Must-pass screen

An option that fails any line is removed and not scored.

| Hard limit (with requirement or rule ID) | Option A `<...>` | Option B `<...>` | Option C `<...>` | Option D `<...>` |
|---|---|---|---|---|
| `<e.g. current rating >= ... A>` | pass / fail | | | |
| `<e.g. in stock at the assembler>` | | | | |
| `<e.g. package fits the build method (DFM-3)>` | | | | |
| `<...>` | | | | |

### 2. Criteria, weights and score definitions

| Criterion (req. ID) | Weight % | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|---|
| `<criterion 1>` |  |  |  |  |  |  |
| `<criterion 2>` |  |  |  |  |  |  |
| `<criterion 3>` |  |  |  |  |  |  |
| `<criterion 4>` |  |  |  |  |  |  |
| `<criterion 5>` |  |  |  |  |  |  |
| `<criterion 6>` |  |  |  |  |  |  |
| `<criterion 7>` |  |  |  |  |  |  |
| **Sum** | **100** | | | | | |

### 3. Scores and weighted total

| Criterion | Weight % | Option A | Option B | Option C | Option D |
|---|---|---|---|---|---|
| `<criterion 1>` |  |  |  |  |  |
| `<criterion 2>` |  |  |  |  |  |
| `<criterion 3>` |  |  |  |  |  |
| `<criterion 4>` |  |  |  |  |  |
| `<criterion 5>` |  |  |  |  |  |
| `<criterion 6>` |  |  |  |  |  |
| `<criterion 7>` |  |  |  |  |  |
| **Weighted total** | **100** |  |  |  |  |
| **Rank** |  |  |  |  |  |

### 4. Sensitivity check

Change the biggest weight by +10 and by -10 points. Spread the opposite change evenly over
the other criteria so the sum stays 100 %. Recalculate the totals.

| Case | Weights used | Winner | Winner changed? |
|---|---|---|---|
| Base |  |  | - |
| Biggest weight +10 |  |  | yes / no |
| Biggest weight -10 |  |  | yes / no |

**Result and comment:** `<winner; robust or not; what data would settle it>`

## Example: LED driver topology for a single-cell 18650 light

Part of an imaginary 18650 EDC light, > 1000 lm, with a single 3 V class LED. Driver
topologies are explained in [docs/choosing-parts.md](../docs/choosing-parts.md) and
[DRV-1](../docs/design-rules.md#drv-1). **All weights and scores below are illustrative**,
chosen to show the method, not measured.

### Must-pass screen

| Hard limit | FET direct drive | Linear regulator | Buck | Boost + 6 V LED | Buck-boost |
|---|---|---|---|---|---|
| Turbo current from one cell possible | pass | pass | pass | pass | pass |
| Flicker-free dimming possible ([LED-6](../docs/design-rules.md#led-6)) | pass (PWM >= 3 kHz) | pass | pass | pass | pass |
| Parts in stock at the assembler | pass | pass | pass | pass | pass |

All five pass in this example. A real screen often removes one or two.

### Criteria, weights and score definitions

| Criterion | Weight % | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|---|
| Regulation over the discharge (R8, R9) | 25 | Output follows the cell voltage all the time | Regulated only in low modes | Regulated until the cell nears the LED voltage, then falls | Regulated except near the end of the discharge | Flat output from full to LVP cut-off |
| Efficiency in most-used modes ([DRV-3](../docs/design-rules.md#drv-3)) | 20 | Most of the power lost as heat | Poor in most-used modes | Good when the cell is low, poor when full | Good in all modes except a few | Good in all modes |
| Low-mode stability ([LED-7](../docs/design-rules.md#led-7)) | 15 | Moon flickers or differs unit to unit | Stable only with extra filtering | Stable, small unit-to-unit spread | Current-controlled, small spread | Current-controlled down to the lowest level |
| Cost | 15 | Most expensive of the options | | Middle | | Cheapest of the options |
| Size on the board | 15 | Does not fit without a bigger board | Fits with difficulty | Fits | Fits with room to spare | Fewest, smallest parts |
| Design complexity | 10 | New switching design, layout-critical, loop compensation | Switching design from a reference layout | Some analog design | Few parts, simple layout | Almost nothing to design |
| **Sum** | **100** | | | | | |

### Scores and weighted total (illustrative)

| Criterion | Weight % | FET direct drive | Linear regulator | Buck | Boost + 6 V LED | Buck-boost |
|---|---|---|---|---|---|---|
| Regulation over the discharge | 25 | 1 | 3 | 3 | 5 | 5 |
| Efficiency | 20 | 4 | 3 | 4 | 4 | 3 |
| Low-mode stability | 15 | 2 | 4 | 3 | 3 | 3 |
| Cost | 15 | 5 | 4 | 3 | 2 | 2 |
| Size | 15 | 5 | 4 | 3 | 2 | 2 |
| Complexity | 10 | 5 | 4 | 3 | 2 | 2 |
| **Weighted total** | **100** | 3.35 | **3.55** | 3.20 | 3.30 | 3.10 |
| **Rank** | | 2 | **1** | 4 | 3 | 5 |

Example calculation, linear regulator: (25 x 3 + 20 x 3 + 15 x 4 + 15 x 4 + 15 x 4 +
10 x 4) / 100 = 3.55.

### Sensitivity check (illustrative)

The biggest weight is regulation (25 %).

| Case | Weights used (reg / eff / low / cost / size / cplx) | Winner | Winner changed? |
|---|---|---|---|
| Base | 25 / 20 / 15 / 15 / 15 / 10 | Linear regulator (3.55) | - |
| Regulation +10 | 35 / 18 / 13 / 13 / 13 / 8 | Boost + 6 V LED (3.54; linear 3.47) | yes |
| Regulation -10 | 15 / 22 / 17 / 17 / 17 / 12 | FET direct drive (3.67; linear 3.63) | yes |

**Result and comment:** the winner changes in both directions, so this result is not robust.
It depends on how much flat output matters. Go back to the requirement sheet: if a flat
output at 30 s and after 10 min (R8, R9) is a Must, the boost or buck-boost wins; if cost
and size dominate, the FET or linear driver wins. Record the reasoning in the design log.
