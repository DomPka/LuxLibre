#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Offscreen VTK renders of EDCO Mini v0.1 (both sizes; run under xvfb-run).  Uses the studio, materials and framing
of the FlashKa v0.7 renderer (hardware/flashka-keychain-v07/tools/housing/render.py); the parts are rebuilt from
edco_mini.py, so section views can cut them.

usage:  xvfb-run -a python3 edco_mini_render.py <out_dir> [--only a,b] [--finish black|natural|both]
"""
import argparse
import os
import sys

import vtk

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "flashka-keychain-v07", "tools", "housing"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "edco-v02", "tools", "housing"))

import render as R  # noqa: E402  (FlashKa v0.7 renderer)
import edco_mini as H  # noqa: E402

R.MATS.update({
    "anod_black": ((0.045, 0.046, 0.050), 0.75, 0.46, 1.0),
    "anod_natural": ((0.62, 0.62, 0.60), 1.00, 0.50, 1.0),
    "anod_ti": ((0.36, 0.37, 0.40), 1.00, 0.42, 1.0),
    "steel_pol": ((0.80, 0.80, 0.82), 1.00, 0.16, 1.0),
    "steel_sat": ((0.72, 0.72, 0.74), 1.00, 0.34, 1.0),
    "silicone": ((0.06, 0.06, 0.065), 0.00, 0.70, 1.0),
    "pom": ((0.032, 0.032, 0.034), 0.00, 0.75, 1.0),
    "nickel": ((0.70, 0.68, 0.62), 1.00, 0.35, 1.0),
    "polyimide": ((0.85, 0.50, 0.12), 0.00, 0.40, 1.0),
    "wrap14": ((0.10, 0.22, 0.45), 0.00, 0.45, 1.0),
    "wrap16": ((0.42, 0.30, 0.08), 0.00, 0.45, 1.0),
    "cell_top": ((0.75, 0.75, 0.76), 1.00, 0.30, 1.0),
    "usb_black": ((0.025, 0.025, 0.027), 0.00, 0.55, 1.0),
    "engrave_black": ((0.58, 0.58, 0.58), 0.00, 0.80, 1.0),
    "engrave_natural": ((0.16, 0.16, 0.17), 0.30, 0.65, 1.0),
    "fr4": ((0.016, 0.016, 0.018), 0.00, 0.58, 1.0),
    "chip": ((0.03, 0.03, 0.035), 0.00, 0.45, 1.0),
    "pass": ((0.45, 0.38, 0.28), 0.00, 0.50, 1.0),
    "lens": ((0.90, 0.95, 1.00), 0.00, 0.03, 0.30),
    "pmma_pipe": ((0.92, 0.96, 1.00), 0.00, 0.05, 0.55),
    "quartz": ((0.94, 0.95, 1.00), 0.00, 0.03, 0.45),
    "copper": ((0.80, 0.45, 0.30), 1.00, 0.30, 1.0),
    "magnet": ((0.62, 0.62, 0.64), 1.00, 0.28, 1.0),
})
GREEN = (0.20, 0.95, 0.45)
RED = (1.00, 0.16, 0.10)
UV = (0.55, 0.25, 1.00)
R.CYAN = GREEN


# per-part glow colours: the FlashKa studio paints every glowing part in R.CYAN; this version uses pt.glow_color
def _set_parts(self, parts, bg=(1, 1, 1)):
    self.ren.RemoveAllViewProps()
    self.mren.RemoveAllViewProps()
    self.ren.SetBackground(*bg)
    self.parts, self.pairs = parts, []
    for pt in parts:
        col = getattr(pt, "glow_color", R.CYAN)
        if pt.glow:
            pt.actor.GetProperty().SetColor(*col)
        self.ren.AddActor(pt.actor)
        a = vtk.vtkActor()
        a.SetMapper(pt.actor.GetMapper())
        pr = a.GetProperty()
        pr.LightingOff()
        pr.SetColor(*(col if pt.glow else (0, 0, 0)))
        self.mren.AddActor(a)
        self.pairs.append((pt.actor, a))
    self.has_glow = any(pt.glow for pt in parts)


R.Studio.set_parts = _set_parts


def mat_map(finish, size):
    al = {"black": "anod_black", "natural": "anod_natural", "ti": "anod_ti"}[finish]
    eng = "engrave_black" if finish == "black" else "engrave_natural"
    return {"body": al, "ring": al, "insert": al, "label": eng, "face_oring": "silicone", "gasket": "silicone",
            "optic_holder": "pc_black", "optic_lens": "lens", "mcpcb": "copper", "led": "led", "phosphor": "phosphor",
            "usb_shell": "metal", "usb_tongue": "usb_black", "usb_seal": "silicone", "usb_body": "usb_black",
            "sled": "pom", "board": "fr4", "membrane": "pmma_pipe", "btn_collar": "steel_pol", "cap": "steel_pol",
            "pin": "pmma_pipe", "uv_rod": "quartz", "red_rod": "pmma_pipe", "cell": "wrap" + size,
            "cell_plus": "cell_top", "strip_plus": "nickel", "strip_minus": "nickel", "insulator": "polyimide",
            "magnet": "magnet", "split_ring": "steel_sat"}


def mat_of(name, mm):
    if name in mm:
        return mm[name]
    if name.startswith("bp_"):
        n = name[3:]
        return {"sw_body": "metal", "sw_act": "black", "halo_led": "led", "uv_led": "led", "red_led": "led",
                "top_passives": "pass"}.get(n, "chip")
    return "black"


INSIDE = ("sled", "board", "pin", "cell", "cell_plus", "strip_plus", "strip_minus", "insulator",
          "face_oring", "mcpcb", "usb_body", "usb_seal")
CUT = ("body", "ring", "insert", "face_oring", "gasket", "optic_holder", "optic_lens", "mcpcb", "sled", "membrane",
       "btn_collar", "cap", "pin", "cell", "cell_plus", "insulator", "label", "usb_shell", "usb_tongue", "usb_seal",
       "usb_body", "magnet")


class Model:
    def __init__(self, size):
        self.p = H.P(size=size)
        self.d = H.build_all(self.p)
        self._pd = {}

    def pd(self, name, shape=None, key=None):
        k = key or name
        if k not in self._pd:
            s = shape if shape is not None else self.d[name]
            self._pd[k] = R.polydata_from_shape(H.solid(s), tol=0.008, ang=0.12)
        return self._pd[k]

    def parts(self, finish="black", skip=(), offsets=None, glow=(), cut=False, shift=(0, 0, 0)):
        """glow: dict part name -> colour"""
        mm = mat_map(finish, self.p.size)
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


HALO = {"membrane": GREEN, "pin": GREEN}


def closed_skip(m):
    return INSIDE + tuple(n for n in m.d if n.startswith("bp_"))


def shoot(parts, name, out, **kw):
    R.studio()
    return R.shoot(parts, name, out, **kw)


def views(out, finish, only):
    want = (lambda n: only is None or n in only)
    sfx = "" if finish == "black" else "_" + finish
    m14 = Model("14")
    if want("hero" + sfx):
        parts = m14.parts(finish, skip=closed_skip(m14), glow=HALO)
        shoot(parts, "mini14_hero%s.png" % sfx, out, direction=(-0.42, 0.55, 1.0), up=(-0.55, -0.45, 0.6),
              ratio=0.62, fill=0.90, view_angle=18.0, glow_radius=2.4, glow_strength=0.9)
    if finish != "black":
        return
    if want("front"):
        parts = m14.parts(finish, skip=closed_skip(m14) + ("split_ring",))
        shoot(parts, "mini14_front.png", out, direction=(-1.0, -0.45, 0.42), up=(0, 0, 1), ratio=0.62, fill=0.88,
              view_angle=18.0)
    if want("port"):
        parts = m14.parts(finish, skip=closed_skip(m14) + ("split_ring",))
        shoot(parts, "mini14_port.png", out, direction=(-0.30, -0.50, -1.0), up=(-1.0, 0.0, 0.0), ratio=0.62,
              fill=0.88, view_angle=16.0)
    if want("uv"):
        g = dict(HALO)
        g["uv_rod"] = UV
        parts = m14.parts(finish, skip=closed_skip(m14) + ("split_ring",), glow=g)
        shoot(parts, "mini14_side_uv.png", out, direction=(-0.55, 0.35, 1.0), up=(-1.0, 0.0, 0.3), ratio=0.62,
              fill=0.88, view_angle=16.0, glow_radius=3.0, glow_strength=1.0)
    if want("red"):
        g = dict(HALO)
        g["red_rod"] = RED
        parts = m14.parts(finish, skip=closed_skip(m14) + ("split_ring",), glow=g)
        shoot(parts, "mini14_side_red.png", out, direction=(-0.55, 0.35, 1.0), up=(-1.0, 0.0, 0.3), ratio=0.62,
              fill=0.88, view_angle=16.0, glow_radius=3.0, glow_strength=1.0)
    if want("tail"):
        parts = m14.parts(finish, skip=closed_skip(m14))
        shoot(parts, "mini14_tail.png", out, direction=(1.0, -0.5, 0.45), up=(0, 0, 1), ratio=0.62, fill=0.88,
              view_angle=18.0)
    if want("section"):
        p = m14.p
        parts = m14.parts(finish, skip=("split_ring",), cut=True, glow=HALO)
        labels = [("Crenellated bezel, M17 x 0.5", (1.0, 0.0, p.RH + 2.5), "T"),
                  ("SST-20 under a TIR optic", (p.x_opt0 + 3.0, 0.0, -3.0), "B"),
                  ("Red + UV side lights", (p.x_win, 0.0, p.RH + 2.5), "T"),
                  ("Stainless button, glowing membrane", (p.x_btn + 1.0, 0.0, p.RH + 2.5), "T"),
                  ("Waterproof USB-C", (p.x_btn, 0.0, -p.RH - 1.0), "B"),
                  ("%s cell" % p.cell_name, (p.x_cell0 + 18, 0.0, -2.0), "B"),
                  ("Magnet in the tail", (p.L - 1.0, 0.0, -p.R - 1.0), "B")]
        shoot(parts, "mini14_section.png", out, direction=(0.0, -1.0, 0.16), up=(0, 0, 1), ratio=0.42, fill=0.92,
              view_angle=12.0, labels=labels)
    if want("exploded"):
        p = m14.p
        grp = {"ring": (-48.0, 0.0), "gasket": (-34.0, 0.0), "optic_holder": (-33.0, 0.0), "optic_lens": (-33.0, 0.0),
               "mcpcb": (-22.0, 0.0), "led": (-22.0, 0.0), "phosphor": (-22.0, 0.0),
               "insert": (-11.0, 0.0), "face_oring": (-11.0, 0.0),
               "sled": (0.0, -13.0), "membrane": (0.0, 11.0), "btn_collar": (0.0, 13.5), "cap": (0.0, 16.0),
               "pin": (0.0, 8.0), "uv_rod": (0.0, 9.0), "red_rod": (0.0, 9.0),
               "body": (0.0, -32.0), "label": (0.0, -32.0), "split_ring": (0.0, -32.0),
               "magnet": (8.0, -32.0)}
        cart = ("cell", "cell_plus", "strip_plus", "strip_minus", "insulator")
        offs = {}
        for nm in m14.d:
            x, z = grp.get(nm, (0.0, 0.0))
            if nm in cart:
                x = 5.0
            offs[nm] = (x, 0.0, z)
        parts = m14.parts(finish, offsets=offs)
        labels = [("Crenellated bezel", (-48.0 + 2.0, 0.0, 10.5), "T"),
                  ("Optic + gasket", (-33.0 + 6.0, 0.0, 9.0), "T"),
                  ("SST-20 on its copper board", (-22.0 + p.x_opt1, 0.0, 8.0), "T"),
                  ("Head insert + face O-ring", (-11.0 + 12.0, 0.0, 9.0), "T"),
                  ("Button parts, light rods", (p.x_btn, 0.0, 16.0 + 9.5), "T"),
                  ("Main board + waterproof USB-C", (p.board_x1 - 3, 0.0, -2.0), "B"),
                  ("%s cell" % p.cell_name, (5.0 + p.x_cell0 + 18, 0.0, 8.0), "T"),
                  ("POM sled", (22.0, 0.0, -13.0 - 8.0), "B"),
                  ("Body, magnet", (45.0, 0.0, -32.0 - 10.0), "B")]
        shoot(parts, "mini14_exploded.png", out, direction=(-0.10, -1.0, 0.30), up=(0, 0, 1), ratio=0.58,
              fill=0.94, view_angle=14.0, labels=labels)
    if want("sizes"):
        m16 = Model("16")
        pa = m14.parts("black", skip=closed_skip(m14) + ("split_ring",), glow=HALO, shift=(0, -14.0, 0))
        pb = m16.parts("natural", skip=closed_skip(m16) + ("split_ring",), glow=HALO, shift=(0, 14.0, 0))
        labels = [("Mini-14: 14350, Ø%g x %.1f mm" % (m14.p.body_od, m14.p.L), (0.0, -14.0, 0.0), "T"),
                  ("Mini-16: 16340, Ø%g x %.1f mm" % (m16.p.body_od, m16.p.L), (0.0, 14.0, 0.0), "T")]
        shoot(pa + pb, "mini_sizes.png", out, direction=(-0.15, 0.25, 1.0), up=(-1.0, 0.0, 0.0), ratio=0.95,
              fill=0.90, view_angle=16.0, glow_radius=2.2, labels=labels)
    if want("family"):
        import edco_v02 as V
        m16 = Model("16")
        v18 = V.P(size="18")
        dv = V.build_all(v18, 180.0)
        vm = R.MATS
        skip_v = ("sled", "board", "pin", "cell", "cell_plus", "strip_plus", "strip_minus", "insulator", "membrane",
                  "face_oring", "mcpcb", "split_ring")
        pv = []
        for nm, s in dv.items():
            if nm in skip_v or nm.startswith("bp_") or s is None:
                continue
            mat = {"label": "engrave_black", "optic_lens": "lens", "optic_holder": "pc_black", "led": "led",
                   "phosphor": "phosphor", "cap": "steel_pol", "btn_collar": "steel_pol",
                   "port_gasket": "silicone", "gasket": "silicone"}.get(nm, "anod_black")
            pv.append(R.Part(R.polydata_from_shape(V.solid(s), tol=0.01, ang=0.12), mat, (0, -38.0, 0), nm))
        pa = m14.parts("black", skip=closed_skip(m14) + ("split_ring",), shift=(0, 0.0, 0))
        pb = m16.parts("black", skip=closed_skip(m16) + ("split_ring",), shift=(0, 30.0, 0))
        labels = [("EDCO-18 v0.2, %.1f mm" % v18.L, (0.0, -38.0, 0.0), "T"),
                  ("Mini-14, %.1f mm" % m14.p.L, (0.0, 0.0, 0.0), "T"),
                  ("Mini-16, %.1f mm" % m16.p.L, (0.0, 30.0, 0.0), "T")]
        del vm
        shoot(pv + pa + pb, "mini_family.png", out, direction=(-0.15, 0.25, 1.0), up=(-1.0, 0.0, 0.0), ratio=1.1,
              fill=0.90, view_angle=16.0, labels=labels)


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
