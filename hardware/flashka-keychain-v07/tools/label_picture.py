#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
The laser warning label as a picture for the build guide and the packaging, made from the label artwork.

usage (from hardware/flashka-keychain-v07):
    python3 tools/label_picture.py

Input:  order_files/optional_laser_label/FlashKa_laser_label_lid_class2.dxf (tools/housing/laser_label.py),
        layer MARK = the label itself (warning sign and text); the reference layer is left out
Output: assets/v07/laser_label_class2.png, black on white, 40 px per mm
The build guide prints it in its section "Laser safety": the light itself carries no marking, so the label
belongs in the manual and on the packaging (a light given or sold to others needs it on the light: the DXF).
Needs: ezdxf, matplotlib, Pillow.
"""
import os

import ezdxf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                      # noqa: E402
from ezdxf.addons.drawing import Frontend, RenderContext              # noqa: E402
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend        # noqa: E402
from ezdxf.addons.drawing.config import BackgroundPolicy, ColorPolicy, Configuration   # noqa: E402
from PIL import Image, ImageDraw, ImageOps                           # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
SRC = os.path.join(PROJ, "order_files", "optional_laser_label", "FlashKa_laser_label_lid_class2.dxf")
OUT = os.path.join(PROJ, "assets", "v07", "laser_label_class2.png")
PX_PER_MM = 40


def main():
    doc = ezdxf.readfile(SRC)
    msp = doc.modelspace()
    for e in list(msp):                                              # keep the label, drop the lid reference
        if e.dxf.layer != "MARK":
            msp.delete_entity(e)
    fig = plt.figure()
    ax = fig.add_axes([0, 0, 1, 1])
    cfg = Configuration(color_policy=ColorPolicy.BLACK, background_policy=BackgroundPolicy.WHITE)
    Frontend(RenderContext(doc), MatplotlibBackend(ax), config=cfg).draw_layout(msp, finalize=True)
    x0, x1 = ax.get_xlim()                                           # the backend sizes the figure itself
    dpi = PX_PER_MM * (x1 - x0) / fig.get_size_inches()[0]
    tmp = OUT + ".tmp.png"
    fig.savefig(tmp, dpi=dpi, facecolor="white")
    plt.close(fig)
    im = Image.open(tmp).convert("L")
    os.remove(tmp)
    ImageDraw.Draw(im).rectangle([0, 0, im.width - 1, im.height - 1], outline=255, width=8)   # no canvas edge
    bbox = ImageOps.invert(im).point(lambda v: 255 if v > 40 else 0).getbbox()
    im = im.crop(bbox)                                               # the marks only, then a white margin
    im = ImageOps.expand(im, border=int(1.2 * PX_PER_MM), fill=255)
    im = im.point(lambda v: 0 if v < 128 else 255).convert("L")      # pure black on white
    framed = ImageOps.expand(im, border=3, fill=0)                    # thin frame: the edge of the label
    framed = ImageOps.expand(framed, border=int(0.4 * PX_PER_MM), fill=255)
    framed.save(OUT, optimize=True)
    print("wrote %s  %s" % (os.path.relpath(OUT, PROJ), framed.size))


if __name__ == "__main__":
    main()
