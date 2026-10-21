#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Preview PNGs of the laser-marking DXF files (black on white).
usage: python3 render_marking.py <cad_dir> <out_dir>"""
import os
import sys

import ezdxf
from ezdxf.addons.drawing import Frontend, RenderContext, layout, config
from ezdxf.addons.drawing.pymupdf import PyMuPdfBackend

cad = sys.argv[1] if len(sys.argv) > 1 else "cad"
out = sys.argv[2] if len(sys.argv) > 2 else "renders"
os.makedirs(out, exist_ok=True)
for name in ("Aurora_marking_class2", "Aurora_marking_class3R"):
    doc = ezdxf.readfile(os.path.join(cad, name + ".dxf"))
    msp = doc.modelspace()
    be = PyMuPdfBackend()
    cfg = config.Configuration(background_policy=config.BackgroundPolicy.WHITE,
                               color_policy=config.ColorPolicy.BLACK)
    Frontend(RenderContext(doc), be, config=cfg).draw_layout(msp)
    page = layout.Page(120, 34, layout.Units.mm, margins=layout.Margins.all(3))
    png = be.get_pixmap_bytes(page, fmt="png", dpi=300)
    with open(os.path.join(out, name + ".png"), "wb") as f:
        f.write(png)
    print("wrote", name + ".png")
