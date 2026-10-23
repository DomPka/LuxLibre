<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
[LuxLibre](../README.md) › Lights

# The lights

LuxLibre's reference designs: complete, editable lights that follow the [design rules](../docs/design-rules.md) and
run the LuxLibre firmware. Each folder can be built without anything else from this repository. None of them has
been built yet: every picture is a render and every light figure is simulated or estimated.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../docs/img/lineup_dark.png">
  <img alt="Render of the seven lights standing side by side at true scale with a millimetre ruler: FlashKa v0.7 99.2 mm, EDCO-18 97.8 mm, EDCO-14 95.6 mm, EDCO v0.1 93.5 mm, EDCO Prism 83.0 mm, EDCO Mini-16 73.5 mm, EDCO Mini-14 69.4 mm" src="../docs/img/lineup_light.png">
</picture>

## Current designs

<table>
<tr>
<td width="33%" valign="top">
<a href="flashka-keychain-v07/README.md"><img src="../docs/img/cards/flashka_v07.gif" width="100%" alt="FlashKa v0.7 turning (render)"></a>
<h3><a href="flashka-keychain-v07/README.md">FlashKa v0.7</a></h3>
Keychain light with a laser and a Bluetooth presenter mode. 99.2 × 20 × 18 mm, one 14500, about 1,045 lm.<br>
<sub>Boards drawn, order files ready; not yet built. <a href="flashka-keychain-v07/cad/README.md">Drawings</a> · <a href="flashka-keychain-v07/assets/v07/README.md">Pictures</a> · <a href="flashka-keychain-v07/FlashKa_v0.7_Build_Guide.pdf">Build guide</a></sub>
</td>
<td width="33%" valign="top">
<a href="edco-prism/README.md"><img src="../docs/img/cards/edco_prism.gif" width="100%" alt="EDCO Prism turning while its beam changes colour (render)"></a>
<h3><a href="edco-prism/README.md">EDCO Prism</a></h3>
A beam that is white or any colour. Ø28 × 83 mm, one 18350, about 1,250 lm.<br>
<sub>Concept: housing done, boards not drawn. <a href="edco-prism/cad/README.md">Drawings</a> · <a href="edco-prism/assets/README.md">Pictures</a> · <a href="../firmware/boards/edco-prism/board.h">Firmware</a></sub>
</td>
<td width="33%" valign="top">
<a href="edco-mini/README.md"><img src="../docs/img/cards/edco_mini.gif" width="100%" alt="EDCO Mini-16M turning (render)"></a>
<h3><a href="edco-mini/README.md">EDCO Mini</a></h3>
Sealed keychain light with red and UV side lights. Ø22 × 73.5 mm (16340) or Ø19 × 69.4 mm, about 950 lm.<br>
<sub>Concept: housing done, boards not drawn. <a href="edco-mini/cad/README.md">Drawings</a> · <a href="edco-mini/assets/README.md">Pictures</a> · <a href="../firmware/boards/edco-mini-16/board.h">Firmware</a></sub>
</td>
</tr>
<tr>
<td width="33%" valign="top">
<a href="edco-v02/README.md"><img src="../docs/img/cards/edco_v02.gif" width="100%" alt="EDCO-18 turning (render)"></a>
<h3><a href="edco-v02/README.md">EDCO v0.2</a></h3>
The bright one: an SST-40 at up to 5.7 A, about 1,760 lm. EDCO-18 (Ø26 × 97.8 mm) or EDCO-14 (Ø22 × 95.6 mm).<br>
<sub>Concept: housing done, boards not drawn. <a href="edco-v02/cad/README.md">Drawings</a> · <a href="edco-v02/assets/README.md">Pictures</a> · <a href="../firmware/boards/edco-v02-18/board.h">Firmware</a></sub>
</td>
<td width="33%" valign="top">
<a href="edco-v01/README.md"><img src="../docs/img/cards/edco_v01.gif" width="100%" alt="EDCO v0.1 turning (render)"></a>
<h3><a href="edco-v01/README.md">EDCO v0.1</a></h3>
A plain sealed tube with USB-C in the tail. Ø20 × 93.5 mm, one 14500, about 966 lm.<br>
<sub>Concept: housing done, boards not drawn. <a href="edco-v01/cad/README.md">Drawings</a> · <a href="edco-v01/assets/README.md">Pictures</a> · <a href="../firmware/boards/edco-v01/board.h">Firmware</a></sub>
</td>
<td width="33%" valign="top">
<h3><a href="../docs/comparison.md">How they compare</a></h3>
Every design against 14 popular lights of the same cell size: light at 30 s and after 10 minutes, throw, runtime,
size and price, with the reviewers' measurements and sources.<br><br>
<h3><a href="../templates/README.md">Make your own</a></h3>
Start from the requirement sheet and the <a href="../docs/README.md">design guide</a>, then see
<a href="#adding-a-design">Adding a design</a> below.
</td>
</tr>
</table>

## Older designs

| Design | What it is |
|---|---|
| [FlashKa v0.6](flashka-keychain-v06/README.md) | the previous FlashKa: three buttons with a glowing ring, the presenter mode. Its folder also holds the FlashKa firmware of v0.6 and v0.7 and the web pages |
| [FlashKa v0.5](flashka-keychain-v05/README.md) | the first FlashKa: two LiPo pouch cells, an SST-20 at up to 2.2 A, a Class 2 laser, USB-C and Bluetooth |

## What is in a design folder

Every design folder has the same layout, so once you know one you know them all.

| Path | What is in it |
|---|---|
| `README.md` | the design page: what the light is, specifications, simulated light and runtime, how it is built, cost, checks, open points |
| `cad/` | drawings (PDF, DXF, PNG) and 3D models (STEP), with a README that shows every sheet |
| `assets/` | renders and animations, with a README gallery |
| `tools/housing/` | the scripts that make the CAD, the checks and the renders |
| [`../firmware/boards/<name>/`](../firmware/boards/README.md) | the light's firmware board header |

The FlashKa folders also have `kicad/` (the circuit boards), `production/` (Gerbers, BOM, placement), `order_files/`
(upload-ready files for the shops), `docs/` (build guide and notes), the build guide and hardware package PDFs and
the parts and cost workbook.

## Shared tools

The drawings, animations, lineup, banner and folder pages of the EDCO designs are made by the scripts in
[tools/](tools/README.md).

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
