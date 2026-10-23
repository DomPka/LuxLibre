#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Offscreen VTK renders of EDCO v0.1 (run under xvfb-run).  Reuses the studio, materials and framing of the
FlashKa v0.7 renderer (hardware/flashka-keychain-v07/tools/housing/render.py).

usage:  xvfb-run -a python3 edco_render.py <out_dir> [--only name1,name2] [--finish black|natural|both]

All pictures are renders of the design.  The parts are rebuilt from edco_housing.py (same parameters as the
STEP files), so a section view can cut them.
"""
import argparse
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "flashka-keychain-v07", "tools", "housing"))

import cadquery as cq  # noqa: E402
import render as R  # noqa: E402  (FlashKa v0.7 renderer)
import edco_housing as H  # noqa: E402

R.MATS.update({
    "anod_black": ((0.045, 0.046, 0.050), 0.75, 0.46, 1.0),       # bead-blasted, black anodised 6061
    "anod_natural": ((0.62, 0.62, 0.60), 1.00, 0.50, 1.0),        # bead-blasted, clear anodised (titanium look)
    "steel_pol": ((0.80, 0.80, 0.82), 1.00, 0.16, 1.0),           # polished stainless (button cap, collar)
    "steel_sat": ((0.72, 0.72, 0.74), 1.00, 0.34, 1.0),           # satin stainless (split ring)
    "silicone": ((0.06, 0.06, 0.065), 0.00, 0.70, 1.0),
    "pom": ((0.032, 0.032, 0.034), 0.00, 0.75, 1.0),
    "nickel": ((0.70, 0.68, 0.62), 1.00, 0.35, 1.0),
    "polyimide": ((0.85, 0.50, 0.12), 0.00, 0.40, 1.0),
    "wrap": ((0.05, 0.30, 0.22), 0.00, 0.45, 1.0),                # cell sleeve (green)
    "cell_top": ((0.75, 0.75, 0.76), 1.00, 0.30, 1.0),
    "usb_black": ((0.025, 0.025, 0.027), 0.00, 0.55, 1.0),
    "engrave_black": ((0.58, 0.58, 0.58), 0.00, 0.80, 1.0),       # laser mark on black anodising (light grey)
    "engrave_natural": ((0.16, 0.16, 0.17), 0.30, 0.65, 1.0),     # laser mark on clear anodising (dark)
    "fr4": ((0.016, 0.016, 0.018), 0.00, 0.58, 1.0),
    "chip": ((0.03, 0.03, 0.035), 0.00, 0.45, 1.0),
    "pass": ((0.45, 0.38, 0.28), 0.00, 0.50, 1.0),
    "lens": ((0.90, 0.95, 1.00), 0.00, 0.03, 0.30),
    "pmma_pipe": ((0.92, 0.96, 1.00), 0.00, 0.05, 0.55),
})
GREEN = (0.20, 0.95, 0.45)
R.CYAN = GREEN     # the indicator glows green (charged / ready)


def mat_map(finish):
    al = "anod_black" if finish == "black" else "anod_natural"
    eng = "engrave_black" if finish == "black" else "engrave_natural"
    m = {"body": al, "ring": al, "head": al, "label": eng, "oring": "silicone", "optic_holder": "pc_black",
         "optic_lens": "lens", "mcpcb": "metal", "led": "led", "phosphor": "phosphor", "sled": "pom",
         "board": "fr4", "membrane": "silicone", "collar": "steel_pol", "cap": "steel_pol", "pin": "pom",
         "lightpipe": "pmma_pipe", "cell": "wrap", "cell_plus": "cell_top", "strip_plus": "nickel",
         "strip_minus": "nickel", "flex": "polyimide", "insulator": "polyimide", "tail_board": "fr4",
         "tail_parts": "chip", "usb_body": "usb_black", "usb_housing": "usb_black", "usb_seal": "silicone",
         "usb_shell": "metal", "usb_tongue": "usb_black", "split_ring": "steel_sat"}
    return m


def mat_of(name, mm):
    if name in mm:
        return mm[name]
    if name.startswith("bp_"):
        n = name[3:]
        if n in ("sw_body",):
            return "metal"
        if n == "sw_act":
            return "black"
        if n == "ind_led":
            return "led"
        if n == "pads":
            return "solder"
        if n.endswith("passives") or n.startswith("b_c") or n == "b_rsense":
            return "pass"
        if n == "b_ind":
            return "chip"
        return "chip"
    return "black"


class Model:
    def __init__(self):
        self.p = H.P()
        self.d = H.build_all(self.p)
        self._pd = {}

    def pd(self, name, shape=None, key=None):
        k = key or name
        if k not in self._pd:
            s = shape if shape is not None else self.d[name]
            self._pd[k] = R.polydata_from_shape(H.solid(s), tol=0.01, ang=0.12)
        return self._pd[k]

    def parts(self, finish="black", names=None, skip=(), offsets=None, glow_ind=False, cut=False):
        mm = mat_map(finish)
        out = []
        offsets = offsets or {}
        for nm in (names or self.d.keys()):
            if nm in skip or self.d.get(nm) is None:
                continue
            if cut and nm in CUT_PARTS:
                pd = self.pd(nm, self.cut_shape(nm), key="cut_" + nm)
            else:
                pd = self.pd(nm)
            glow = glow_ind and nm == "lightpipe"
            out.append(R.Part(pd, mat_of(nm, mm), offsets.get(nm, (0, 0, 0)), nm, glow=glow))
        return out

    def cut_shape(self, nm):
        """half section: keep y >= 0 (the viewer looks from -Y, head on the left)"""
        keep = H.box(-5, self.p.L + 10, 0.0, 20, -20, 20)
        return self.d[nm].intersect(keep)


CUT_PARTS = ("body", "ring", "head", "oring", "sled", "optic_holder", "optic_lens", "mcpcb", "membrane",
             "collar", "cap", "pin", "lightpipe", "cell", "cell_plus", "tail_board", "usb_body", "usb_housing",
             "usb_seal", "usb_shell", "usb_tongue", "insulator", "label")
INSIDE = ("sled", "board", "pin", "cell", "cell_plus", "strip_plus", "strip_minus", "flex", "insulator",
          "tail_board", "tail_parts", "usb_body", "membrane", "oring", "mcpcb")


def shoot(parts, name, out, **kw):
    R.studio()  # create
    R.CYAN = GREEN
    return R.shoot(parts, name, out, **kw)


def views(m, out, finish, only=None):
    p = m.p
    L = p.L
    sfx = "" if finish == "black" else "_natural"
    want = (lambda n: only is None or n in only)
    closed_skip = INSIDE + tuple(n for n in m.d if n.startswith("bp_"))

    if want("hero" + sfx):
        parts = m.parts(finish, skip=closed_skip, glow_ind=True)
        shoot(parts, "edco_hero%s.png" % sfx, out, direction=(-0.30, 0.55, 1.0), up=(-0.55, -0.45, 0.6),
              ratio=0.62, fill=0.90, view_angle=18.0, glow_radius=2.0, glow_strength=0.9)
    if want("button" + sfx):
        parts = m.parts(finish, skip=closed_skip + ("split_ring",), glow_ind=True)
        fit = [pt for pt in parts if pt.name in ("cap", "collar", "lightpipe", "label")]
        shoot(parts, "edco_button_macro%s.png" % sfx, out, direction=(-0.30, 0.45, 1.0), up=(-1.0, -0.55, 0.35),
              ratio=0.62, fill=0.55, view_angle=12.0, fit_parts=fit, glow_radius=2.5, crop=False)
    if want("tail" + sfx):
        parts = m.parts(finish, skip=closed_skip)
        shoot(parts, "edco_tail_usb%s.png" % sfx, out, direction=(1.0, -0.55, 0.42), up=(0.0, 0.0, 1.0),
              ratio=0.62, fill=0.88, view_angle=18.0)
    if want("front" + sfx):
        parts = m.parts(finish, skip=closed_skip + ("split_ring",))
        shoot(parts, "edco_front%s.png" % sfx, out, direction=(-1.0, -0.42, 0.36), up=(0.0, 0.0, 1.0),
              ratio=0.62, fill=0.88, view_angle=18.0)
    if want("section") and finish == "black":
        parts = m.parts(finish, skip=("split_ring",), cut=True, glow_ind=True)
        labels = [
            ("Bezel ring, M18 x 0.75, locked", (2.5, 0.0, 10.0), "T"),
            ("TIR optic", (3.5, 0.0, 3.0), "B"),
            ("Head: LED holder, O-ring", (9.5, 0.0, -7.2), "B"),
            ("Stainless button on a sealed membrane", (p.btn_x, 0.0, 9.6), "T"),
            ("Indicator light pipe", (p.ind_x, 0.0, 8.6), "T"),
            ("Main board in POM sled", (24.0, 0.0, 3.8), "B"),
            ("14500 cell, 1,500 mAh", (58.0, 0.0, -6.0), "B"),
            ("EDCO on the label flat", (47.0, 0.0, 9.1), "T"),
            ("Tail board", (p.tail_board_x0 + 0.4, 0.0, -4.0), "B"),
            ("Sealed USB-C", (L - 1.5, 0.0, 1.8), "T"),
        ]
        shoot(parts, "edco_section.png", out, direction=(0.0, -1.0, 0.16), up=(0.0, 0.0, 1.0), ratio=0.40,
              fill=0.92, view_angle=12.0, labels=labels)
    if want("exploded") and finish == "black":
        grp = {
            "ring": (-44.0, 0.0), "optic_holder": (-31.0, 0.0), "optic_lens": (-31.0, 0.0),
            "mcpcb": (-21.0, 0.0), "led": (-21.0, 0.0), "phosphor": (-21.0, 0.0),
            "head": (-11.0, 0.0), "oring": (-11.0, 0.0), "sled": (0.0, -15.0),
            "membrane": (0.0, 13.0), "collar": (0.0, 16.0), "cap": (0.0, 19.0), "pin": (0.0, 9.0),
            "lightpipe": (0.0, 9.0), "body": (0.0, -36.0), "label": (0.0, -36.0), "split_ring": (0.0, -36.0),
        }
        cart = ("cell", "cell_plus", "strip_plus", "strip_minus", "flex", "insulator")
        tail = ("tail_board", "tail_parts", "usb_body", "usb_housing", "usb_seal", "usb_shell", "usb_tongue")
        offs = {}
        for nm in m.d:
            x, z = grp.get(nm, (0.0, 0.0))
            if nm in cart:
                x = 6.0
            if nm in tail:
                x = 14.0
            offs[nm] = (x, 0.0, z)
        parts = m.parts(finish, offsets=offs)
        labels = [
            ("Bezel ring", (-44.0 + 3.0, 0.0, 10.0), "T"),
            ("TIR optic", (-31.0 + 4.0, 0.0, 5.0), "T"),
            ("LED board", (-21.0 + 8.3, 0.0, 5.0), "T"),
            ("Head + O-ring", (-11.0 + 6.0, 0.0, 8.0), "T"),
            ("Button, pin, light pipe", (p.btn_x, 0.0, 19.0 + 9.6), "T"),
            ("Main board", (28.0, 0.0, 4.4), "T"),
            ("14500 cell", (6.0 + 58.0, 0.0, 7.0), "T"),
            ("Tail board + sealed USB-C", (14.0 + p.L - 4.0, 0.0, 3.0), "T"),
            ("POM sled", (16.0, 0.0, -15.0 - 7.5), "B"),
            ("Body tube", (60.0, 0.0, -36.0 - 10.0), "B"),
        ]
        shoot(parts, "edco_exploded.png", out, direction=(-0.10, -1.0, 0.30), up=(0.0, 0.0, 1.0), ratio=0.55,
              fill=0.94, view_angle=14.0, labels=labels)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    ap.add_argument("--only", default=None)
    ap.add_argument("--finish", default="both")
    a = ap.parse_args()
    only = set(a.only.split(",")) if a.only else None
    m = Model()
    for fin in (("black", "natural") if a.finish == "both" else (a.finish,)):
        views(m, a.out_dir, fin, only)


if __name__ == "__main__":
    main()
