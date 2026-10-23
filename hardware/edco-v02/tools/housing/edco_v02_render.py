#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Offscreen VTK renders of EDCO v0.2 (both sizes; run under xvfb-run).  Uses the studio, materials and framing of
the FlashKa v0.7 renderer (hardware/flashka-keychain-v07/tools/housing/render.py); the parts are rebuilt from
edco_v02.py, so section views can cut them.

usage:  xvfb-run -a python3 edco_v02_render.py <out_dir> [--only a,b] [--finish black|natural|both]
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "flashka-keychain-v07", "tools", "housing"))

import render as R  # noqa: E402  (FlashKa v0.7 renderer)
import edco_v02 as H  # noqa: E402

R.MATS.update({
    "anod_black": ((0.045, 0.046, 0.050), 0.75, 0.46, 1.0),
    "anod_natural": ((0.62, 0.62, 0.60), 1.00, 0.50, 1.0),
    "anod_black_collar": ((0.040, 0.041, 0.045), 0.75, 0.40, 1.0),
    "steel_pol": ((0.80, 0.80, 0.82), 1.00, 0.16, 1.0),
    "steel_sat": ((0.72, 0.72, 0.74), 1.00, 0.34, 1.0),
    "silicone": ((0.06, 0.06, 0.065), 0.00, 0.70, 1.0),
    "pom": ((0.032, 0.032, 0.034), 0.00, 0.75, 1.0),
    "nickel": ((0.70, 0.68, 0.62), 1.00, 0.35, 1.0),
    "polyimide": ((0.85, 0.50, 0.12), 0.00, 0.40, 1.0),
    "wrap18": ((0.45, 0.06, 0.08), 0.00, 0.45, 1.0),
    "wrap14": ((0.05, 0.30, 0.22), 0.00, 0.45, 1.0),
    "cell_top": ((0.75, 0.75, 0.76), 1.00, 0.30, 1.0),
    "usb_black": ((0.025, 0.025, 0.027), 0.00, 0.55, 1.0),
    "engrave_black": ((0.58, 0.58, 0.58), 0.00, 0.80, 1.0),
    "engrave_natural": ((0.16, 0.16, 0.17), 0.30, 0.65, 1.0),
    "fr4": ((0.016, 0.016, 0.018), 0.00, 0.58, 1.0),
    "chip": ((0.03, 0.03, 0.035), 0.00, 0.45, 1.0),
    "pass": ((0.45, 0.38, 0.28), 0.00, 0.50, 1.0),
    "lens": ((0.90, 0.95, 1.00), 0.00, 0.03, 0.30),
    "pmma_pipe": ((0.92, 0.96, 1.00), 0.00, 0.05, 0.55),
    "copper": ((0.80, 0.45, 0.30), 1.00, 0.30, 1.0),
})
GREEN = (0.20, 0.95, 0.45)
R.CYAN = GREEN


def mat_map(finish, size):
    al = "anod_black" if finish == "black" else "anod_natural"
    eng = "engrave_black" if finish == "black" else "engrave_natural"
    return {"body": al, "ring": al, "insert": al, "collar": al if finish != "black" else "anod_black_collar",
            "label": eng, "face_oring": "silicone", "gasket": "silicone", "optic_holder": "pc_black",
            "optic_lens": "lens", "mcpcb": "copper", "led": "led", "phosphor": "phosphor",
            "port_gasket": "silicone", "sled": "pom",
            "board": "fr4", "membrane": "pmma_pipe", "btn_collar": "steel_pol", "cap": "steel_pol",
            "pin": "pmma_pipe", "cell": "wrap" + size, "cell_plus": "cell_top", "strip_plus": "nickel",
            "strip_minus": "nickel", "insulator": "polyimide", "split_ring": "steel_sat"}


def mat_of(name, mm):
    if name in mm:
        return mm[name]
    if name.startswith("bp_"):
        n = name[3:]
        return {"sw_body": "metal", "sw_act": "black", "halo_led": "led", "usb_body": "usb_black",
                "usb_shell": "metal", "usb_tongue": "usb_black", "top_passives": "pass"}.get(n, "chip")
    return "black"


INSIDE = ("sled", "board", "pin", "cell", "cell_plus", "strip_plus", "strip_minus", "insulator", "membrane",
          "face_oring", "mcpcb")
CUT = ("body", "ring", "insert", "face_oring", "gasket", "optic_holder", "optic_lens", "mcpcb", "collar",
       "port_gasket", "sled", "membrane", "btn_collar", "cap", "pin", "cell", "cell_plus",
       "insulator", "label")


class Model:
    def __init__(self, size, collar_angle=0.0):
        self.p = H.P(size=size)
        self.d = H.build_all(self.p, collar_angle)
        self._pd = {}

    def pd(self, name, shape=None, key=None):
        k = key or name
        if k not in self._pd:
            s = shape if shape is not None else self.d[name]
            self._pd[k] = R.polydata_from_shape(H.solid(s), tol=0.01, ang=0.12)
        return self._pd[k]

    def parts(self, finish="black", skip=(), offsets=None, glow=False, cut=False, shift=(0, 0, 0)):
        mm = mat_map(finish, self.p.size)
        out = []
        offsets = offsets or {}
        for nm in self.d:
            if nm in skip or self.d.get(nm) is None:
                continue
            if cut and nm in CUT:
                keep = H.box(-5, self.p.L + 15, 0.0, 30, -30, 30)
                pd = self.pd(nm, self.d[nm].intersect(keep), key="cut_" + nm)
            else:
                pd = self.pd(nm)
            o = offsets.get(nm, (0, 0, 0))
            o = (o[0] + shift[0], o[1] + shift[1], o[2] + shift[2])
            g = glow and nm in ("membrane", "pin")
            out.append(R.Part(pd, mat_of(nm, mm), o, nm, glow=g))
        return out


def closed_skip(m):
    return INSIDE + tuple(n for n in m.d if n.startswith("bp_") and n not in ("bp_usb_body", "bp_usb_shell",
                                                                            "bp_usb_tongue"))


def shoot(parts, name, out, **kw):
    R.studio()
    R.CYAN = GREEN
    return R.shoot(parts, name, out, **kw)


def views(out, finish, only):
    want = (lambda n: only is None or n in only)
    sfx = "" if finish == "black" else "_natural"
    m18c = Model("18", collar_angle=180.0)     # collar closed (window up)
    if want("hero" + sfx):
        parts = m18c.parts(finish, skip=closed_skip(m18c), glow=True)
        shoot(parts, "edco18_hero%s.png" % sfx, out, direction=(-0.42, 0.55, 1.0), up=(-0.55, -0.45, 0.6),
              ratio=0.62, fill=0.90, view_angle=18.0, glow_radius=2.4, glow_strength=0.9)
    if finish != "black":
        return
    if want("front"):
        parts = m18c.parts(finish, skip=closed_skip(m18c) + ("split_ring",))
        shoot(parts, "edco18_front.png", out, direction=(-1.0, -0.45, 0.42), up=(0, 0, 1), ratio=0.62, fill=0.88,
              view_angle=18.0)
    m18o = Model("18", collar_angle=0.0)       # collar open (window down over the port)
    if want("port"):
        parts = m18o.parts(finish, skip=closed_skip(m18o))
        fit = [pt for pt in parts if pt.name in ("collar", "ring")]
        shoot(parts, "edco18_port_open.png", out, direction=(-0.25, -0.55, -1.0), up=(-1.0, 0.0, 0.0), ratio=0.62,
              fill=0.70, view_angle=16.0, fit_parts=fit, crop=False)
    if want("tail"):
        parts = m18c.parts(finish, skip=closed_skip(m18c))
        shoot(parts, "edco18_tail.png", out, direction=(1.0, -0.5, 0.45), up=(0, 0, 1), ratio=0.62, fill=0.88,
              view_angle=18.0)
    if want("section"):
        p = m18o.p
        parts = m18o.parts(finish, skip=("split_ring",), cut=True, glow=True)
        labels = [("Crenellated bezel, M22 x 0.75", (1.0, 0.0, 12.5), "T"),
                  ("SST-40 under a TIR optic", (8.0, 0.0, 4.0), "B"),
                  ("Twist collar over the port gasket", (p.x_win, 0.0, 12.0), "T"),
                  ("USB-C, looking down through the port", (p.x_win, 0.0, -8.0), "B"),
                  ("Stainless button, glowing membrane", (p.x_btn, 0.0, 11.5), "T"),
                  ("Main board in POM sled", (p.board_x[1] - 3, 0.0, -2.0), "B"),
                  ("18500 cell", (p.x_cell0 + 25, 0.0, 6.0), "B"),
                  ("Six flats, EDCO label", (p.x_cell0 + 12, 0.0, p.flat_r), "T"),
                  ("Tail grooves, lanyard holes", (p.L - 4.0, 0.0, -11.0), "B")]
        shoot(parts, "edco18_section.png", out, direction=(0.0, -1.0, 0.16), up=(0, 0, 1), ratio=0.42, fill=0.92,
              view_angle=12.0, labels=labels)
    if want("exploded"):
        p = m18o.p
        grp = {"ring": (-64.0, 0.0), "gasket": (-46.0, 0.0), "optic_holder": (-44.0, 0.0), "optic_lens": (-44.0, 0.0),
               "mcpcb": (-30.0, 0.0), "led": (-30.0, 0.0), "phosphor": (-30.0, 0.0),
               "insert": (-14.0, 0.0), "face_oring": (-14.0, 0.0),
               "collar": (-4.0, 18.0),
               "sled": (0.0, -16.0), "membrane": (0.0, 14.0), "btn_collar": (0.0, 17.0), "cap": (0.0, 20.0),
               "pin": (0.0, 10.0), "body": (0.0, -40.0), "label": (0.0, -40.0), "split_ring": (0.0, -40.0),
               "port_gasket": (0.0, -40.0)}
        cart = ("cell", "cell_plus", "strip_plus", "strip_minus", "insulator")
        offs = {}
        for nm in m18o.d:
            x, z = grp.get(nm, (0.0, 0.0))
            if nm in cart:
                x = 6.0
            offs[nm] = (x, 0.0, z)
        parts = m18o.parts(finish, offsets=offs)
        labels = [("Crenellated bezel", (-64.0 + 3.0, 0.0, 13.0), "T"),
                  ("Optic + gasket", (-44.0 + 7.0, 0.0, 10.5), "T"),
                  ("SST-40 on its copper board", (-30.0 + p.x_opt1, 0.0, 10.0), "T"),
                  ("Head insert + face O-ring", (-14.0 + 15.0, 0.0, 11.0), "T"),
                  ("Twist collar", (-4.0 + p.x_win, 0.0, 18.0 + 12.5), "T"),
                  ("Button parts", (p.x_btn, 0.0, 20.0 + 11.5), "T"),
                  ("Main board + USB-C", (p.board_x[1] - 4, 0.0, 0.0), "B"),
                  ("18500 cell", (6.0 + p.x_cell0 + 25, 0.0, 9.5), "T"),
                  ("POM sled", (25.0, 0.0, -16.0 - 9.5), "B"),
                  ("Body: band, flats, tail", (60.0, 0.0, -40.0 - 12.0), "B")]
        shoot(parts, "edco18_exploded.png", out, direction=(-0.10, -1.0, 0.30), up=(0, 0, 1), ratio=0.58,
              fill=0.94, view_angle=14.0, labels=labels)
    if want("sizes"):
        m14 = Model("14", collar_angle=180.0)
        pa = m18c.parts("black", skip=closed_skip(m18c) + ("split_ring",), glow=True, shift=(0, -16.0, 0))
        pb = m14.parts("natural", skip=closed_skip(m14) + ("split_ring",), glow=True, shift=(0, 16.0, 0))
        labels = [("EDCO-18: 18500, Ø24 x 99 mm", (m18c.p.L / 2, -16.0, 14.0), "T"),
                  ("EDCO-14: 14500, Ø20 x 96 mm", (m14.p.L / 2, 16.0, 12.0), "T")]
        shoot(pa + pb, "edco_v02_sizes.png", out, direction=(-0.15, 0.25, 1.0), up=(-1.0, 0.0, 0.0), ratio=0.95,
              fill=0.90, view_angle=16.0, glow_radius=2.2, labels=labels)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    ap.add_argument("--only", default=None)
    ap.add_argument("--finish", default="both")
    a = ap.parse_args()
    only = set(a.only.split(",")) if a.only else None
    for fin in (("black", "natural") if a.finish == "both" else (a.finish,)):
        views(a.out_dir, fin, only)


if __name__ == "__main__":
    main()
