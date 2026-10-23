#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Offscreen VTK renders of EDCO Prism v0.1 (run under xvfb-run). Uses the studio, materials and framing of the
FlashKa v0.7 renderer (hardware/flashka-keychain-v07/tools/housing/render.py) and the materials of the EDCO Mini
renderer; the parts are rebuilt from edco_prism.py, so section views can cut them.

usage:  xvfb-run -a python3 edco_prism_render.py <out_dir> [--only a,b] [--finish black|natural|both]
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "flashka-keychain-v07", "tools", "housing"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "edco-mini", "tools", "housing"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "edco-v02", "tools", "housing"))

import edco_mini_render as MR  # noqa: E402  (materials, per-part glow colours, the studio set-up)
import edco_prism as H  # noqa: E402

R = MR.R
R.MATS.update({
    "wrap18": ((0.08, 0.30, 0.20), 0.00, 0.45, 1.0),
    "dome_red": ((0.75, 0.10, 0.08), 0.00, 0.20, 1.0),
    "dome_green": ((0.10, 0.62, 0.25), 0.00, 0.20, 1.0),
    "dome_blue": ((0.12, 0.20, 0.80), 0.00, 0.20, 1.0),
})
WHITE = (1.00, 0.97, 0.88)
COL = {"red": (1.00, 0.12, 0.08), "green": (0.15, 1.00, 0.35), "blue": (0.20, 0.35, 1.00), "white": WHITE}
HALO = {"membrane": (0.55, 0.30, 1.00), "pin": (0.55, 0.30, 1.00)}   # the RGB halo, shown violet


def mat_map(finish):
    al = {"black": "anod_black", "natural": "anod_natural"}[finish]
    eng = "engrave_black" if finish == "black" else "engrave_natural"
    return {"body": al, "ring": al, "insert": al, "label": eng, "face_oring": "silicone", "gasket": "silicone",
            "optic_holder": "pc_black", "optic_lens": "lens", "mcpcb": "copper", "led": "led",
            "dome_white": "phosphor", "dome_red": "dome_red", "dome_green": "dome_green", "dome_blue": "dome_blue",
            "usb_shell": "metal", "usb_tongue": "usb_black", "usb_seal": "silicone", "usb_body": "usb_black",
            "sled": "pom", "board": "fr4", "membrane": "pmma_pipe", "btn_collar": "steel_pol", "cap": "steel_pol",
            "pin": "pmma_pipe", "cell": "wrap18", "cell_plus": "cell_top", "strip_plus": "nickel",
            "strip_minus": "nickel", "insulator": "polyimide", "magnet": "magnet", "split_ring": "steel_sat"}


def mat_of(name, mm):
    if name in mm:
        return mm[name]
    if name.startswith("bp_"):
        n = name[3:]
        return {"sw_body": "metal", "sw_act": "black", "halo_led": "led", "top_passives": "pass",
                "t_ind": "chip"}.get(n, "chip")
    return "black"


INSIDE = ("sled", "board", "pin", "cell", "cell_plus", "strip_plus", "strip_minus", "insulator",
          "face_oring", "mcpcb", "usb_body", "usb_seal")
CUT = ("body", "ring", "insert", "face_oring", "gasket", "optic_holder", "optic_lens", "mcpcb", "sled", "membrane",
       "btn_collar", "cap", "pin", "cell", "cell_plus", "insulator", "label", "usb_shell", "usb_tongue", "usb_seal",
       "usb_body", "magnet")


class Model:
    def __init__(self, magnet=False):
        self.p = H.P(magnet=magnet)
        self.d = H.build_all(self.p)
        self._pd = {}

    def pd(self, name, shape=None, key=None):
        k = key or name
        if k not in self._pd:
            s = shape if shape is not None else self.d[name]
            self._pd[k] = R.polydata_from_shape(H.solid(s), tol=0.008, ang=0.12)
        return self._pd[k]

    def parts(self, finish="black", skip=(), offsets=None, glow=(), cut=False, shift=(0, 0, 0)):
        mm = mat_map(finish)
        out = []
        offsets = offsets or {}
        glow = dict(glow)
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
            pt = R.Part(pd, mat_of(nm, mm), o, nm, glow=nm in glow)
            if nm in glow:
                pt.glow_color = glow[nm]
            out.append(pt)
        return out


def closed_skip(m):
    return INSIDE + tuple(n for n in m.d if n.startswith("bp_"))


def beam(m, colour):
    """glow dict for the beam: turbo (all four LEDs), or one colour LED, plus the halo in the beam's colour"""
    if colour == "white":
        g = {"dome_white": WHITE, "dome_red": COL["red"], "dome_green": COL["green"], "dome_blue": COL["blue"],
             "membrane": WHITE, "pin": WHITE}
    else:
        g = {"dome_" + colour: COL[colour], "membrane": COL[colour], "pin": COL[colour]}
    return {k: v for k, v in g.items() if k in m.d}


def shoot(parts, name, out, **kw):
    R.studio()
    return R.shoot(parts, name, out, **kw)


def views(out, finish, only):
    want = (lambda n: only is None or n in only)
    mm = Model(magnet=True)              # the main renders: the M version
    p = mm.p
    if finish == "natural":
        if want("hero_natural"):
            m0 = Model(magnet=False)
            parts = m0.parts(finish, skip=closed_skip(m0), glow=beam(m0, "white"))
            shoot(parts, "prism_hero_natural.png", out, direction=(-0.42, 0.55, 1.0), up=(-0.55, -0.45, 0.6),
                  ratio=0.62, fill=0.90, view_angle=18.0, glow_radius=2.4, glow_strength=0.9)
        return
    if want("hero"):
        parts = mm.parts(finish, skip=closed_skip(mm), glow=HALO)
        shoot(parts, "prism_hero.png", out, direction=(-0.42, 0.55, 1.0), up=(-0.55, -0.45, 0.6),
              ratio=0.62, fill=0.90, view_angle=18.0, glow_radius=2.4, glow_strength=0.9)
    if want("front"):
        parts = mm.parts(finish, skip=closed_skip(mm) + ("split_ring",))
        shoot(parts, "prism_front.png", out, direction=(-1.0, -0.35, 0.30), up=(0, 0, 1), ratio=0.70, fill=0.88,
              view_angle=18.0)
    if want("colours"):
        allp = []
        labels = []
        for i, c in enumerate(("white", "red", "green", "blue")):
            if "dome_" + c not in mm.d and c != "white":
                continue
            dy = (1.5 - i) * 30.0
            allp += mm.parts(finish, skip=closed_skip(mm) + ("split_ring",), glow=beam(mm, c), shift=(0, dy, 0))
            labels.append(({"white": "White (turbo)", "red": "Red", "green": "Green", "blue": "Blue"}[c],
                           (0.0, dy, p.RH + 1.0), "T"))
        shoot(allp, "prism_colours.png", out, direction=(-1.0, -0.12, 0.42), up=(0, 0, 1), ratio=0.42, fill=0.92,
              view_angle=16.0, glow_radius=6.0, glow_strength=2.2, labels=labels)
    if want("port"):
        parts = mm.parts(finish, skip=closed_skip(mm) + ("split_ring",))
        shoot(parts, "prism_port.png", out, direction=(-0.30, -0.50, -1.0), up=(-1.0, 0.0, 0.0), ratio=0.62,
              fill=0.88, view_angle=16.0)
    if want("tail"):
        m0 = Model(magnet=False)
        parts = m0.parts(finish, skip=closed_skip(m0))
        shoot(parts, "prism_tail.png", out, direction=(1.0, -0.5, 0.45), up=(0, 0, 1), ratio=0.62, fill=0.88,
              view_angle=18.0)
    if want("tail_m"):
        parts = mm.parts(finish, skip=closed_skip(mm) + ("split_ring",))
        shoot(parts, "prism_m_tail.png", out, direction=(1.0, -0.5, 0.45), up=(0, 0, 1), ratio=0.62, fill=0.88,
              view_angle=18.0)
    if want("section"):
        parts = mm.parts(finish, skip=("split_ring",), cut=True, glow=HALO)
        labels = [("Crenellated bezel, M26 x 0.75", (1.0, 0.0, p.RH + 2.5), "T"),
                  ("Four LEDs under one quad optic", (p.x_opt0 + 5.0, 0.0, -4.0), "B"),
                  ("Stainless button, RGB-lit membrane", (p.x_btn + 1.0, 0.0, p.RH + 2.5), "T"),
                  ("Waterproof USB-C", (p.x_btn, 0.0, -p.RH - 1.0), "B"),
                  ("18350 cell", (p.x_cell0 + 18, 0.0, -2.0), "B"),
                  ("Tail tab: keyring hole, magnets", (p.L - 1.0, 0.0, -p.R - 1.0), "B")]
        shoot(parts, "prism_section.png", out, direction=(0.0, -1.0, 0.16), up=(0, 0, 1), ratio=0.42, fill=0.92,
              view_angle=12.0, labels=labels)
    if want("exploded"):
        grp = {"ring": (-56.0, 0.0), "gasket": (-40.0, 0.0), "optic_holder": (-39.0, 0.0), "optic_lens": (-39.0, 0.0),
               "mcpcb": (-26.0, 0.0), "led": (-26.0, 0.0), "insert": (-13.0, 0.0), "face_oring": (-13.0, 0.0),
               "sled": (0.0, -17.0), "membrane": (0.0, 13.0), "btn_collar": (0.0, 16.0), "cap": (0.0, 19.0),
               "pin": (0.0, 10.0), "body": (0.0, -40.0), "label": (0.0, -40.0), "split_ring": (0.0, -40.0),
               "magnet": (10.0, -40.0)}
        for nm in mm.d:
            if nm.startswith("dome_"):
                grp[nm] = (-26.0, 0.0)
        cart = ("cell", "cell_plus", "strip_plus", "strip_minus", "insulator")
        offs = {}
        for nm in mm.d:
            x, z = grp.get(nm, (0.0, 0.0))
            if nm in cart:
                x = 5.0
            offs[nm] = (x, 0.0, z)
        parts = mm.parts(finish, offsets=offs)
        labels = [("Crenellated bezel", (-56.0 + 2.0, 0.0, 13.0), "T"),
                  ("Quad optic + gasket", (-39.0 + 7.0, 0.0, 11.0), "T"),
                  ("Four LEDs on a 24 mm copper board", (-26.0 + p.x_opt1, 0.0, 10.5), "T"),
                  ("Head insert + face O-ring", (-13.0 + 15.0, 0.0, 11.5), "T"),
                  ("Button parts", (p.x_btn, 0.0, 19.0 + 10.5), "T"),
                  ("Main board + waterproof USB-C", (p.board_x1 - 3, 0.0, -2.0), "B"),
                  ("18350 cell", (5.0 + p.x_cell0 + 18, 0.0, 10.0), "T"),
                  ("POM sled", (25.0, 0.0, -17.0 - 10.0), "B"),
                  ("Body with the tail tab, magnets", (50.0, 0.0, -40.0 - 12.0), "B")]
        shoot(parts, "prism_exploded.png", out, direction=(-0.10, -1.0, 0.30), up=(0, 0, 1), ratio=0.58,
              fill=0.94, view_angle=14.0, labels=labels)
    if want("family"):
        import edco_mini as MH
        mini = MR.Model("16", magnet=True)
        pa = mm.parts("black", skip=closed_skip(mm) + ("split_ring",), glow=HALO)
        pb = mini.parts("black", skip=MR.closed_skip(mini) + ("split_ring",), glow=MR.HALO, shift=(0, 30.0, 0))
        labels = [("EDCO Prism: 18350, Ø%g x %.1f mm" % (p.body_od, p.L + 1e-6), (0.0, 0.0, 0.0), "T"),
                  ("EDCO Mini-16: 16340, Ø%g x %.1f mm" % (mini.p.body_od, mini.p.L + 1e-6), (0.0, 30.0, 0.0), "T")]
        _ = MH
        shoot(pa + pb, "prism_family.png", out, direction=(-0.15, 0.25, 1.0), up=(-1.0, 0.0, 0.0), ratio=0.95,
              fill=0.90, view_angle=16.0, glow_radius=2.2, labels=labels)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    ap.add_argument("--only", default=None)
    ap.add_argument("--finish", default="both")
    a = ap.parse_args()
    only = set(a.only.split(",")) if a.only else None
    fins = ("black", "natural") if a.finish == "both" else (a.finish,)
    for fin in fins:
        views(a.out_dir, fin, only)


if __name__ == "__main__":
    main()
