<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
[LuxLibre](../../../README.md) › [Lights](../../../hardware/README.md) › [EDCO Prism](../README.md) › Drawings and CAD

# EDCO Prism: drawings and CAD

The files of the EDCO Prism housing, made from the design scripts in [../tools/](../tools/) (nothing is drawn by hand). STEP files open in FreeCAD, Fusion, Onshape or any CAD program; DXF in LibreCAD, QCAD or any CAD program; PDF and PNG are for reading. The design page explains every part: [EDCO Prism](../README.md).

## Drawings

The M body is drawn: the plain body is the same without the two magnet pockets (item 9 on the sheet).

**EDCO Prism body drawing, A3 at 2:1** ([PDF](EDCO_Prism_body_drawing.pdf), [DXF](EDCO_Prism_body_drawing.dxf), [PNG](EDCO_Prism_body_drawing.png))

[![EDCO Prism body drawing, A3 at 2:1](EDCO_Prism_body_drawing.png)](EDCO_Prism_body_drawing.pdf)

## 3D models

| File | What it is |
|---|---|
| `EDCO_PrismM_body` ([STEP](EDCO_PrismM_body.step)) | body; M version (with the magnet pockets) |
| `EDCO_PrismM_v0.1_assembly` ([STEP](EDCO_PrismM_v0.1_assembly.step)) | every part in place, with stand-ins for the boards and the socket; M version (with the magnet pockets) |
| `EDCO_Prism_bezel` ([STEP](EDCO_Prism_bezel.step)) | bezel (screws onto the body's thread) |
| `EDCO_Prism_body` ([STEP](EDCO_Prism_body.step)) | body |
| `EDCO_Prism_insert` ([STEP](EDCO_Prism_insert.step)) | head insert (holds the LED board and the optic) |
| `EDCO_Prism_v0.1_assembly` ([STEP](EDCO_Prism_v0.1_assembly.step)) | every part in place, with stand-ins for the boards and the socket |

## Data

| File | What it is |
|---|---|
| [`edco_prism_interface.json`](edco_prism_interface.json) | sizes, walls, fits, masses and the interference check (written by the CAD script, read by the checks) |

The drawings are made by [hardware/tools/edco_drawings.py](../../tools/edco_drawings.py) and checked against the solids ([report](../../tools/edco_drawings_check.txt)).
