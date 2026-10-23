<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
# Reference designs

Complete, editable designs that follow the [design rules](../docs/design-rules.md) and run
LuxLibre. Each folder can be built without anything else from this repository.

| Design | Type | Status |
|---|---|---|
| [EDCO v0.1](edco-v01/README.md) | round, sealed everyday-carry light: Ø20 × 93.5 mm aluminium tube with a closed tail, one 14500 cell (Vapcell INR14500 F15), no laser and no radio; charging, firmware updates and settings only through a sealed USB-C socket in the tail; the battery and electronics slide in from the front and a bezel ring screws on for good; one stainless button on a sealed membrane with a charge indicator; the FlashKa v0.7 light engine (about 966 lm and 162.5 m of throw, simulated); LuxLibre firmware | concept: housing modelled and checked by software, boards not drawn, not built |
| [FlashKa Keychain v0.7](flashka-keychain-v07/README.md) | the 1000 lm FlashKa: an SST-20 Gen 2 LED under a TIR optic, a 4 A driver, cell protection on the main board and one 14500 Li-ion cell (Vapcell INR14500 F15, 1,500 mAh) in a 99.2 × 20 × 18 mm faceted octagon (about 1,045 lm with a G1-bin LED and 162.5 m of throw at switch-on, about 280 lm sustained and about 137 min from turbo, simulated); the three keys on the centre line of the bottom face: a clear PMMA main key whose frosted ring glows in the ring colour and two black rubber keys with chevrons along the light, on a key board joined to the main board by six pogo pins (both boards in one JLCPCB panel); no 3D-printed part and no marking; textured panels on the facets; a comparison with the RovyVon Aurora A2. FlashKa firmware 0.7.0, built from the v0.6 sources; the web pages of v0.6 | current design; designed and checked by software, not yet built |
| [FlashKa Keychain v0.6](flashka-keychain-v06/README.md) | the v0.5 keychain light with three buttons (a stainless-steel main button in a glowing RGB light ring, plus next and previous) and a presenter mode: the light becomes a Bluetooth LE (Low Energy) keyboard that turns slides, with the laser as the pointer; "fighter-jet skin" on the aluminium body (engraved panel seams, laser-marked rivets and stencils) | previous design; designed and checked by software, not yet built; holds the firmware of both versions and the web pages |
| [FlashKa Keychain v0.5](flashka-keychain-v05/README.md) | keychain light, 2 LiPo pouch cells, SST-20 up to 2.2 A, Class 2 laser, USB-C, Bluetooth (ESP32-C3) | older design; designed and checked by software, not yet built |

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
