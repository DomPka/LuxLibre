<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
# Design log

## How to use

Write one record for every important choice ([REQ-3](../docs/design-rules.md#req-3)): cell,
LED, optic, driver topology, MCU, charger, housing material, sealing, firmware layout. Start
the record when the question comes up (status "proposed"), list at least three options, and
score them with [decision-matrix.md](decision-matrix.md) if the choice is not obvious. Give
every source with a link and the date you read it, because datasheets and prices change.
Never delete a record: when a decision changes, write a new record and set the old one to
"replaced by D-xx". Number records D-01, D-02, ... and refer to requirement IDs (R1, R2, ...)
from [requirements.md](requirements.md) and rule IDs from
[docs/design-rules.md](../docs/design-rules.md).

## Index

| ID | Date | Question | Decision | Status |
|---|---|---|---|---|
| D-01 |  |  |  |  |
| D-02 |  |  |  |  |
| D-03 |  |  |  |  |

## Record template

Copy this block for each decision.

### D-`<nn>` `<short title>`

| Field | Entry |
|---|---|
| Date | `<YYYY-MM-DD>` |
| Author(s) | `<...>` |
| Question | `<what must be decided, in one sentence>` |
| Requirements and rules | `<R.., R..; BAT-1, ...>` |
| Status | `<proposed / accepted / replaced by D-xx>` |

**Options considered** (at least 3)

| Option | Short description | Passes must-have limits? |
|---|---|---|
| A | `<...>` | `<yes / no: why>` |
| B | `<...>` |  |
| C | `<...>` |  |

**Criteria and weights:** `<criterion (weight %), ...>`, matrix: `<link to the filled
decision-matrix.md or .csv>`

**Data and sources**

| Data | Value | Source (link) | Type | Accessed |
|---|---|---|---|---|
| `<parameter of option A>` | `<value with unit>` | `<link>` | `<datasheet / measurement / article / retailer>` | `<YYYY-MM-DD>` |
|  |  |  |  |  |

**Decision:** `<option chosen>`

**Why:** `<2-4 short points, linked to the criteria>`

**Consequences and risks:** `<what this choice forces elsewhere; what could go wrong;
mitigation>`

**Verification:** `<test or check that will prove the choice works; requirement and test
report section>`

## Example: D-03 Choose the 18650 cell

Part of an imaginary 18650 EDC light, > 1000 lm. Cell data: only the values below, from the
sources listed.

| Field | Entry |
|---|---|
| Date | 2026-10-15 |
| Author(s) | `<...>` |
| Question | Which 18650 cell do we specify and test with? |
| Requirements and rules | R18, R20, R24; [BAT-1](../docs/design-rules.md#bat-1), [BAT-2](../docs/design-rules.md#bat-2), [CHG-3](../docs/design-rules.md#chg-3) |
| Status | accepted |

**Options considered**

| Option | Short description | Passes must-have limits? |
|---|---|---|
| A | Molicel P28A | yes |
| B | Samsung 30Q | yes, if turbo cell current <= 70 % of 15 A |
| C | Murata VTC6 | only retailer data, no maker datasheet found ([BAT-1](../docs/design-rules.md#bat-1)) |

**Criteria and weights:** current headroom (40 %), capacity (30 %), charge temperature
window (15 %), data quality (15 %). Weights are illustrative; matrix: `<link>`.

**Data and sources**

| Data | Value | Source (link) | Type | Accessed |
|---|---|---|---|---|
| P28A capacity | 2800 mAh typ | [Molicel datasheet](https://www.rosebatteries.com/hubfs/INR18650P28A-V2-80093.pdf) | datasheet | 2026-10-15 |
| P28A max continuous discharge | 35 A | same | datasheet | 2026-10-15 |
| P28A charge temperature | 0-60 °C | same | datasheet | 2026-10-15 |
| 30Q capacity | 3000 mAh | [Samsung datasheet](https://e2e.ti.com/cfs-file/__key/communityserver-discussions-components-files/196/samsung_5F00_30q_5F00_data_5F00_sheet.pdf) | datasheet | 2026-10-15 |
| 30Q continuous discharge | 15 A | same | datasheet | 2026-10-15 |
| 30Q charge temperature | 0-50 °C | same | datasheet | 2026-10-15 |
| VTC6 capacity | 3000 mAh | [retailer page](https://www.imrbatteries.com/sony-murata-vtc6-18650-3000mah-15a-battery/) | retailer | 2026-10-15 |
| VTC6 continuous discharge | 15 A | same | retailer | 2026-10-15 |

**Decision:** Molicel P28A.

**Why:**

- Largest current rating, so turbo stays inside the 70 % limit of
  [BAT-1](../docs/design-rules.md#bat-1) with the most margin.
- Widest charge temperature window; the LuxLibre default charge window (CHG_TMIN /
  CHG_TMAX, [CHG-3](../docs/design-rules.md#chg-3)) fits inside it.
- Maker datasheet available; the VTC6 values come only from a retailer.

**Consequences and risks:**

- Lower typical capacity than the 30Q and VTC6, so less runtime per mode. Check R13-R16.
- Users will fit other 18650 cells ([BAT-2](../docs/design-rules.md#bat-2)). Set
  BAT_MAX_MA for a 15 A cell or state the minimum cell rating in the manual.
- Counterfeit cells: buy from authorised distributors only.

**Verification:** cell current at turbo from `status` (cell_mA) and a clamp meter, compared
with BAT_MAX_MA; runtime test per mode; both in [test-report.md](test-report.md).
