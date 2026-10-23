<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
[LuxLibre](../../../README.md) › [Lights](../../../hardware/README.md) › [EDCO v0.1](../README.md) › Drawings and CAD

# EDCO v0.1: drawings and CAD

The files of the EDCO v0.1 housing, made from the design scripts in [../tools/](../tools/) (nothing is drawn by hand). STEP files open in FreeCAD, Fusion, Onshape or any CAD program; DXF in LibreCAD, QCAD or any CAD program; PDF and PNG are for reading. The design page explains every part: [EDCO v0.1](../README.md).

## Drawings

**EDCO body drawing, A3 at 2:1** ([PDF](EDCO_body_drawing.pdf), [DXF](EDCO_body_drawing.dxf), [PNG](EDCO_body_drawing.png))

[![EDCO body drawing, A3 at 2:1](EDCO_body_drawing.png)](EDCO_body_drawing.pdf)

## 3D models

| File | What it is |
|---|---|
| `EDCO_bezel_ring` ([STEP](EDCO_bezel_ring.step)) | bezel ring (screws onto the body's thread) |
| `EDCO_body` ([STEP](EDCO_body.step)) | body |
| `EDCO_head` ([STEP](EDCO_head.step)) | head (holds the LED board and the optic) |
| `EDCO_v0.1_assembly` ([STEP](EDCO_v0.1_assembly.step)) | every part in place, with stand-ins for the boards and the socket |

## Data

| File | What it is |
|---|---|
| [`edco_interface.json`](edco_interface.json) | sizes, walls, fits, masses and the interference check (written by the CAD script, read by the checks) |

The drawings are made by [hardware/tools/edco_drawings.py](../../tools/edco_drawings.py) and checked against the solids ([report](../../tools/edco_drawings_check.txt)).
