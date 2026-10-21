<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
# Reference designs

Complete, editable designs that follow the [design rules](../docs/design-rules.md) and run
LuxLibre. Each folder can be built without anything else from this repository.

| Design | Type | Status |
|---|---|---|
| [FlashKa Keychain v0.6](flashka-keychain-v06/README.md) | the v0.5 keychain light with three buttons (a stainless-steel main button in a glowing RGB light ring, plus next and previous) and a presenter mode: the light becomes a Bluetooth LE (Low Energy) keyboard that turns slides, with the laser as the pointer; "fighter-jet skin" on the aluminium body (engraved panel seams, laser-marked rivets and stencils) | current design; designed and checked by software, not yet built |
| [FlashKa Keychain v0.5](flashka-keychain-v05/README.md) | keychain light, 2 LiPo pouch cells, SST-20 up to 2.2 A, Class 2 laser, USB-C, Bluetooth (ESP32-C3) | previous design; designed and checked by software, not yet built |

## Adding a design

A reference design folder contains:

- `README.md`: what it is, specifications, status, how to build it, cost, known limitations,
  licences (use the FlashKa README as the pattern);
- editable sources: schematic and PCB (KiCad preferred), mechanical CAD as STEP plus the native
  files or generator scripts, drawings with tolerances ([MEC-8](../docs/design-rules.md#mec-8));
- production files: Gerbers, drill, BOM with manufacturer part numbers, pick-and-place
  ([DFM-7](../docs/design-rules.md#dfm-7));
- the LuxLibre board header in `firmware/boards/<name>/` ([FW-2](../docs/design-rules.md#fw-2));
- the filled requirement sheet, design log and review checklist
  ([templates/](../templates/README.md));
- test reports once it has been built ([docs/testing.md](../docs/testing.md)).

Design files are licensed CERN-OHL-W-2.0, scripts GPL-3.0-or-later, documents CC-BY-SA-4.0
([LICENSING.md](../LICENSING.md)).
