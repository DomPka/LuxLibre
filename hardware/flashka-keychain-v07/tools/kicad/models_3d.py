#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Simple 3D models (STEP) of the FlashKa parts the KiCad library has no model for, so that the
STEP exports of both boards carry every part (cad/FlashKa_main_pcb.step, cad/FlashKa_keys_pcb.step):

  Pogo_Harwin_P70-1010045R.step      SMT pogo pin at FREE height (5.0 mm): base d2.0 x 0.4,
                                     barrel d1.54 up to 3.3 mm, plunger d0.9 with a rounded tip.
                                     Working height 4.0 mm (Harwin range 3.7-4.2): the plunger
                                     tip is then 1.0 mm lower.  Envelope model, not the
                                     manufacturer drawing.
  SW_Alps_SKRK.step                  Alps SKRKAEE020 top-push switch 3.9 x 2.9 mm, 2.0 mm high
                                     with the actuator (body 1.5 + actuator d1.6 x 0.5), two
                                     terminal tabs on the pads (x -/+2.1)
  LED_RGB_1010_NH-B1010RGBT.step     1.0 x 1.0 mm RGB LED, worst-case height 0.85 mm

Frame: KiCad 3D model frame (x right, y up, z up from the board face the part sits on, origin
= footprint origin).  usage:  python3 tools/kicad/models_3d.py [kicad/FlashKa.3dshapes]
"""
import os
import sys

import cadquery as cq

POGO = {"base_d": 2.0, "base_h": 0.4, "barrel_d": 1.54, "barrel_h": 3.3, "plunger_d": 0.9,
        "free_h": 5.0, "working_h": 4.0}


def pogo():
    p = POGO
    base = cq.Workplane("XY").circle(p["base_d"] / 2).extrude(p["base_h"])
    barrel = cq.Workplane("XY").workplane(offset=p["base_h"]).circle(p["barrel_d"] / 2) \
        .extrude(p["barrel_h"] - p["base_h"])
    r = p["plunger_d"] / 2
    plunger = cq.Workplane("XY").workplane(offset=p["barrel_h"]).circle(r) \
        .extrude(p["free_h"] - p["barrel_h"]).faces(">Z").edges().fillet(r * 0.6)
    return base.union(barrel).union(plunger)


def skrk():
    body = cq.Workplane("XY").rect(3.9, 2.9).extrude(1.5).edges("|Z").fillet(0.15)
    act = cq.Workplane("XY").workplane(offset=1.5).circle(0.8).extrude(0.5)
    tabs = None
    for sx in (-1, 1):
        t = cq.Workplane("XY").center(sx * 2.15, 0).rect(0.5, 1.0).extrude(0.15)
        tabs = t if tabs is None else tabs.union(t)
    return body.union(act).union(tabs)


def led1010():
    sub = cq.Workplane("XY").rect(1.0, 1.0).extrude(0.2)
    lens = cq.Workplane("XY").workplane(offset=0.2).rect(0.9, 0.9).extrude(0.65).edges(">Z").fillet(0.1)
    return sub.union(lens)


MODELS = {"Pogo_Harwin_P70-1010045R": pogo, "SW_Alps_SKRK": skrk, "LED_RGB_1010_NH-B1010RGBT": led1010}


def write(outdir):
    os.makedirs(outdir, exist_ok=True)
    out = []
    for name, f in MODELS.items():
        path = os.path.join(outdir, name + ".step")
        cq.exporters.export(f(), path, "STEP")
        # no date / tool stamp in the file: same bytes on every build
        txt = open(path, encoding="utf-8", errors="replace").read()
        import re
        txt = re.sub(r"FILE_NAME\('[^']*','[^']*'", f"FILE_NAME('{name}.step','2026-10-21T00:00:00'", txt, count=1)
        open(path, "w", encoding="utf-8").write(txt)
        out.append(path)
    return out


if __name__ == "__main__":
    print(write(sys.argv[1] if len(sys.argv) > 1 else "kicad/FlashKa.3dshapes"))
