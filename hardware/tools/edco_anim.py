#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Animated renders (GIF) of the EDCO lights, made with the FlashKa v0.7 renderer and animation helpers
(hardware/flashka-keychain-v07/tools/housing/render.py, render_anim.py) and the parts and materials of each
design's own render script.

    xvfb-run -a python3 hardware/tools/edco_anim.py [--only v01,v02,mini,prism] [--what turntable,exploded,colours]

Outputs (renders of the designs; none of these lights has been built yet):
    edco-v01/assets/edco_turntable.gif, edco_exploded.gif
    edco-v02/assets/edco18_turntable.gif, edco18_exploded.gif
    edco-mini/assets/mini16_turntable.gif, mini16_exploded.gif
    edco-prism/assets/prism_turntable.gif, prism_exploded.gif, prism_colours.gif

turntable: the closed light turning once about its long axis (48 frames x 80 ms, loop); the Prism's beam steps
           through its colours as it turns (72 frames)
exploded:  the parts moving apart along the axis and back
colours:   EDCO Prism seen from the front, its beam stepping through the colours of the firmware's list

Needs python3 with vtk, numpy, PIL and cadquery, plus ffmpeg and xvfb-run.
"""
import argparse
import importlib.util
import os
import shutil
import sys
import tempfile
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
HW = os.path.dirname(HERE)
OUT_W = 720


def load(rel, name):
    path = os.path.join(HW, rel)
    sys.path.insert(0, os.path.dirname(path))
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


RA = load("flashka-keychain-v07/tools/housing/render_anim.py", "render_anim")
R = RA.R
MR = load("edco-mini/tools/housing/edco_mini_render.py", "edco_mini_render")      # per-part glow colours
FONT = "/usr/share/fonts/truetype/google-fonts/Poppins-SemiBold.ttf"
if not os.path.exists(FONT):
    FONT = "/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf"


def log(*a):
    print(*a, flush=True)


# ------------------------------------------------------------------------------------------ designs
class Design:
    """name, output prefix, closed parts (lit), exploded parts with their final offsets, the light's length"""

    def __init__(self, key):
        self.key = key
        if key == "v01":
            ER = load("edco-v01/tools/housing/edco_render.py", "edco_render")
            m = ER.Model()
            skip = ER.INSIDE + tuple(n for n in m.d if n.startswith("bp_"))
            self.closed = lambda: m.parts("black", skip=skip, glow_ind=True)
            grp = {"ring": (-44.0, 0.0), "optic_holder": (-31.0, 0.0), "optic_lens": (-31.0, 0.0),
                   "mcpcb": (-21.0, 0.0), "led": (-21.0, 0.0), "phosphor": (-21.0, 0.0),
                   "head": (-11.0, 0.0), "oring": (-11.0, 0.0), "sled": (0.0, -15.0),
                   "membrane": (0.0, 13.0), "collar": (0.0, 16.0), "cap": (0.0, 19.0), "pin": (0.0, 9.0),
                   "lightpipe": (0.0, 9.0), "body": (0.0, -36.0), "label": (0.0, -36.0), "split_ring": (0.0, -36.0)}
            cart = ("cell", "cell_plus", "strip_plus", "strip_minus", "flex", "insulator")
            tail = ("tail_board", "tail_parts", "usb_body", "usb_housing", "usb_seal", "usb_shell", "usb_tongue")
            offs = {}
            for nm in m.d:
                x, z = grp.get(nm, (0.0, 0.0))
                x = 6.0 if nm in cart else 14.0 if nm in tail else x
                offs[nm] = (x, 0.0, z)
            self.exploded = lambda: (m.parts("black", offsets={}), offs)
            self.out, self.prefix, self.p = "edco-v01/assets", "edco", m.p
            self.direction = (-0.42, -0.80, 0.42)
        elif key == "v02":
            VR = load("edco-v02/tools/housing/edco_v02_render.py", "edco_v02_render")
            mc = VR.Model("18", collar_angle=180.0)
            mo = VR.Model("18")
            self.closed = lambda: mc.parts("black", skip=VR.closed_skip(mc), glow=True)
            grp = {"ring": (-64.0, 0.0), "gasket": (-46.0, 0.0), "optic_holder": (-44.0, 0.0),
                   "optic_lens": (-44.0, 0.0), "mcpcb": (-30.0, 0.0), "led": (-30.0, 0.0), "phosphor": (-30.0, 0.0),
                   "insert": (-14.0, 0.0), "face_oring": (-14.0, 0.0), "collar": (-4.0, 18.0),
                   "sled": (0.0, -16.0), "membrane": (0.0, 14.0), "btn_collar": (0.0, 17.0), "cap": (0.0, 20.0),
                   "pin": (0.0, 10.0), "body": (0.0, -40.0), "label": (0.0, -40.0), "split_ring": (0.0, -40.0),
                   "port_gasket": (0.0, -40.0)}
            cart = ("cell", "cell_plus", "strip_plus", "strip_minus", "insulator")
            offs = {nm: ((6.0 if nm in cart else grp.get(nm, (0.0, 0.0))[0]), 0.0, grp.get(nm, (0.0, 0.0))[1])
                    for nm in mo.d}
            self.exploded = lambda: (mo.parts("black"), offs)
            self.out, self.prefix, self.p = "edco-v02/assets", "edco18", mo.p
            self.direction = (-0.42, -0.80, 0.42)
        elif key == "mini":
            m = MR.Model("16", magnet=True)
            self.closed = lambda: m.parts("black", skip=MR.closed_skip(m), glow=MR.HALO)
            grp = {"ring": (-52.0, 0.0), "gasket": (-37.0, 0.0), "optic_holder": (-36.0, 0.0),
                   "optic_lens": (-36.0, 0.0), "mcpcb": (-24.0, 0.0), "led": (-24.0, 0.0), "phosphor": (-24.0, 0.0),
                   "insert": (-12.0, 0.0), "face_oring": (-12.0, 0.0), "sled": (0.0, -15.0),
                   "membrane": (0.0, 12.0), "btn_collar": (0.0, 15.0), "cap": (0.0, 18.0), "pin": (0.0, 9.0),
                   "uv_rod": (0.0, 10.0), "red_rod": (0.0, 10.0), "body": (0.0, -36.0), "label": (0.0, -36.0),
                   "split_ring": (0.0, -36.0), "lanyard": (0.0, -36.0), "magnet": (9.0, -36.0), "bar": (0.0, -36.0)}
            cart = ("cell", "cell_plus", "strip_plus", "strip_minus", "insulator")
            offs = {nm: ((5.0 if nm in cart else grp.get(nm, (0.0, 0.0))[0]), 0.0, grp.get(nm, (0.0, 0.0))[1])
                    for nm in m.d}
            self.exploded = lambda: (m.parts("black", skip=("lanyard",)), offs)
            self.closed = lambda: m.parts("black", skip=MR.closed_skip(m) + ("lanyard",), glow=MR.HALO)
            self.out, self.prefix, self.p = "edco-mini/assets", "mini16", m.p
            self.direction = (-0.42, -0.80, 0.42)
        elif key == "prism":
            PR = load("edco-prism/tools/housing/edco_prism_render.py", "edco_prism_render")
            m = PR.Model(magnet=True)
            self.PR, self.m = PR, m
            self.closed = lambda: m.parts("black", skip=PR.closed_skip(m), glow=PR.beam(m, "white"))
            grp = {"ring": (-56.0, 0.0), "gasket": (-40.0, 0.0), "optic_holder": (-39.0, 0.0),
                   "optic_lens": (-39.0, 0.0), "mcpcb": (-26.0, 0.0), "led": (-26.0, 0.0), "insert": (-13.0, 0.0),
                   "face_oring": (-13.0, 0.0), "sled": (0.0, -17.0), "membrane": (0.0, 13.0),
                   "btn_collar": (0.0, 16.0), "cap": (0.0, 19.0), "pin": (0.0, 10.0), "body": (0.0, -40.0),
                   "label": (0.0, -40.0), "split_ring": (0.0, -40.0), "magnet": (10.0, -40.0)}
            for nm in m.d:
                if nm.startswith("dome_"):
                    grp[nm] = (-26.0, 0.0)
            cart = ("cell", "cell_plus", "strip_plus", "strip_minus", "insulator")
            offs = {nm: ((5.0 if nm in cart else grp.get(nm, (0.0, 0.0))[0]), 0.0, grp.get(nm, (0.0, 0.0))[1])
                    for nm in m.d}
            self.exploded = lambda: (m.parts("black"), offs)
            self.out, self.prefix, self.p = "edco-prism/assets", "prism", m.p
            self.direction = (-0.42, -0.80, 0.42)
        else:
            raise SystemExit("unknown design " + key)


# ------------------------------------------------------------------------------------------ turntable
def turntable(d, tmp, frames=48, delay_cs=8, ss=2.2):
    """EDCO Prism: the beam steps through its colours while the light turns"""
    cur = {"parts": d.closed()}
    st = R.studio()
    st.set_parts(cur["parts"])
    centre = (d.p.L / 2.0, 0.0, 0.0)
    seq = colour_list(d.PR) if d.key == "prism" else None

    def apply(theta):
        mx = RA.rot_x_about(theta, centre)
        for pt in cur["parts"]:
            pt.actor.SetUserMatrix(mx)

    theta0 = -20.0                 # first frame: the button towards the camera, a little turned
    thetas = [theta0 + 360.0 * k / frames for k in range(frames)]
    fill, margin = 0.90, 0.035
    asp = RA.fit_camera(st, thetas[::4], apply, d.direction, (0, 0, 1), view_angle=18.0, fill=fill)
    Wf = int(round(OUT_W * ss / (fill * (1 + 2 * margin))))
    st.size(Wf, int(round(Wf * asp)))
    raw, box = [], None
    t0 = time.time()
    for k, th in enumerate(thetas):
        if seq:
            cur["parts"] = d.m.parts("black", skip=d.PR.closed_skip(d.m), glow=colour_glow(d.m, seq[k * len(seq) // frames]))
            st.set_parts(cur["parts"])
        apply(th)
        img, g = st.grab()
        img = R.bloom(img, g, radius=(3.0 if seq else 0.9 * 2.2) * ss, strength=1.2 if seq else 0.85)
        raw.append(img)
        box = RA.union_box(box, R.content_box(img))
    log("  %s turntable rendered in %.1f s" % (d.key, time.time() - t0))
    for pt in cur["parts"]:
        pt.actor.SetUserMatrix(None)
    paths = RA.save_frames(raw, tmp, d.key + "_tt", box, OUT_W, margin)
    out = os.path.join(HW, d.out, d.prefix + "_turntable.gif")
    return RA.write_gif(paths, [delay_cs] * len(paths), out, tmp)


# ------------------------------------------------------------------------------------------ exploded
def stages(offs):
    """groups of parts that move together, in the order they leave: the front parts one by one from the outermost,
    the button parts upwards, the cartridge, then the body downwards"""
    keys = sorted(set(offs.values()))
    front = sorted([k for k in keys if k[0] < 0 and k[2] <= 0], key=lambda k: k[0])
    front += sorted([k for k in keys if k[0] < 0 and k[2] > 0], key=lambda k: k[0])
    up = sorted([k for k in keys if k[0] >= 0 and k[2] > 0], key=lambda k: -k[2])
    cart = sorted([k for k in keys if k[0] > 0 and k[2] == 0])
    down = sorted([k for k in keys if k[2] < 0], key=lambda k: -k[2])
    order = front + up + cart + down
    n = len(order)
    t = {}
    for i, k in enumerate(order):
        s0 = 0.55 * i / max(n - 1, 1)
        t[k] = (s0, s0 + 0.45)
    return t


def exploded(d, tmp, steps=30, ss=2.2):
    parts, offs = d.exploded()
    st = R.studio()
    st.set_parts(parts)
    base = {id(pt): np.array(pt.actor.GetPosition(), float) for pt in parts}
    timing = stages({pt.name: offs.get(pt.name, (0.0, 0.0, 0.0)) for pt in parts})

    def apply(u):
        for pt in parts:
            o = offs.get(pt.name, (0.0, 0.0, 0.0))
            if o == (0.0, 0.0, 0.0):
                continue
            s0, s1 = timing[o]
            f = RA.ease((u - s0) / (s1 - s0))
            pt.actor.SetPosition(*(base[id(pt)] + np.array(o) * f))

    us = [k / (steps - 1) for k in range(steps)]
    fill, margin = 0.92, 0.03
    asp = RA.fit_camera(st, [0.0, 0.5, 0.75, 1.0], apply, (-0.10, -1.0, 0.30), view_angle=14.0, fill=fill)
    Wf = int(round(OUT_W * ss / (fill * (1 + 2 * margin))))
    st.size(Wf, int(round(Wf * asp)))
    raw, box = [], None
    t0 = time.time()
    for u in us:
        apply(u)
        img, g = st.grab()
        img = R.bloom(img, g, radius=0.9 * ss * 2.2, strength=0.8)
        raw.append(img)
        box = RA.union_box(box, R.content_box(img))
    log("  %s exploded rendered in %.1f s" % (d.key, time.time() - t0))
    apply(0.0)
    paths = RA.save_frames(raw, tmp, d.key + "_ex", box, OUT_W, margin)
    seq = paths + paths[-2:0:-1]
    delays = [6] * len(paths) + [5] * (len(paths) - 2)
    delays[0] = 120
    delays[len(paths) - 1] = 200
    out = os.path.join(HW, d.out, d.prefix + "_exploded.gif")
    return RA.write_gif(seq, delays, out, tmp)


def colour_list(PR):
    """(label, glowing LED domes, colour of the button halo and the lit optic) for each colour of the firmware's
    list (lx_color.cpp), white turbo first"""
    C = PR.COL
    amber = (1.00, 0.45, 0.05)
    return [("White (turbo, all four LEDs)", {"dome_white": PR.WHITE, "dome_red": C["red"], "dome_green": C["green"],
                                              "dome_blue": C["blue"]}, PR.WHITE),
            ("Red", {"dome_red": C["red"]}, C["red"]),
            ("Green", {"dome_green": C["green"]}, C["green"]),
            ("Blue", {"dome_blue": C["blue"]}, C["blue"]),
            ("Yellow (red + half green)", {"dome_red": C["red"], "dome_green": C["green"]}, (1.0, 0.85, 0.1)),
            ("Cyan", {"dome_green": C["green"], "dome_blue": C["blue"]}, (0.1, 0.95, 1.0)),
            ("Magenta", {"dome_red": C["red"], "dome_blue": C["blue"]}, (1.0, 0.2, 0.9)),
            ("White from red, green and blue", {"dome_red": C["red"], "dome_green": C["green"],
                                                "dome_blue": C["blue"]}, (0.95, 0.95, 1.0)),
            ("Custom (amber by default)", {"dome_red": C["red"], "dome_green": C["green"]}, amber)]


def colour_glow(m, entry):
    _, g, halo = entry
    glow = dict(g)
    glow["membrane"] = halo
    glow["pin"] = halo
    glow["optic_lens"] = tuple(0.50 * c for c in halo)      # the optic lit in the beam's colour
    return {k: v for k, v in glow.items() if k in m.d}


# ------------------------------------------------------------------------------------------ Prism colours
def colours(d, tmp, ss=2.2):
    """the Prism's colour list (firmware lx_color.cpp): white turbo, red, green, blue, yellow, cyan, magenta,
    white from the three colours, custom (amber by default); each colour lights its LEDs and the button halo"""
    PR, m = d.PR, d.m
    seq = colour_list(PR)
    st = R.studio()
    skip = PR.closed_skip(m) + ("split_ring",)
    direction = (-1.0, -0.20, 0.34)
    parts0 = m.parts("black", skip=skip, glow=colour_glow(m, seq[0]))
    st.set_parts(parts0)
    fill, margin = 0.86, 0.04
    asp = RA.fit_camera(st, [0], lambda s: None, direction, (0, 0, 1), view_angle=16.0, fill=fill)
    Wf = int(round(OUT_W * ss / (fill * (1 + 2 * margin))))
    Hf = int(round(Wf * asp))
    st.size(Wf, Hf)
    imgs, box = [], None
    for entry in seq:
        label = entry[0]
        st.set_parts(m.parts("black", skip=skip, glow=colour_glow(m, entry)))
        img, gm = st.grab()
        img = R.bloom(img, gm, radius=5.0 * ss, strength=1.6)
        imgs.append((label, img))
        box = RA.union_box(box, R.content_box(img))
    x0, y0, x1, y1 = box
    mg = int(round(margin * (x1 - x0)))
    font = ImageFont.truetype(FONT, 26)
    frames = []
    for label, img in imgs:
        h, w = img.shape[:2]
        im = Image.fromarray(img[max(y0 - mg, 0):min(y1 + mg, h - 1) + 1, max(x0 - mg, 0):min(x1 + mg, w - 1) + 1])
        oh = int(round(im.height * OUT_W / im.width / 2.0)) * 2
        im = im.resize((OUT_W, oh), Image.LANCZOS)
        canvas = Image.new("RGB", (OUT_W, oh + 56), (255, 255, 255))
        canvas.paste(im, (0, 0))
        dr = ImageDraw.Draw(canvas)
        tw = dr.textlength(label, font=font)
        dr.text(((OUT_W - tw) / 2, oh + 12), label, fill=(40, 40, 44), font=font)
        frames.append(canvas)
    # cross-fades between the colours
    paths, delays = [], []
    k = 0
    for i, fr in enumerate(frames):
        nxt = frames[(i + 1) % len(frames)]
        for j, a in enumerate((0.0, 0.33, 0.67)):
            im = fr if a == 0.0 else Image.blend(fr, nxt, a)
            pth = os.path.join(tmp, "col_%03d.png" % k)
            im.save(pth, compress_level=1)
            paths.append(pth)
            delays.append(110 if a == 0.0 else 6)
            k += 1
    out = os.path.join(HW, d.out, d.prefix + "_colours.gif")
    return RA.write_gif(paths, delays, out, tmp)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default="v01,v02,mini,prism")
    ap.add_argument("--what", default="turntable,exploded,colours")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    what = set(a.what.split(","))
    tmp = tempfile.mkdtemp(prefix="edco_anim_")
    try:
        for key in a.only.split(","):
            d = Design(key)
            if "turntable" in what:
                turntable(d, tmp, frames=72 if key == "prism" else 48)
            if "exploded" in what:
                exploded(d, tmp)
            if "colours" in what and key == "prism":
                colours(d, tmp)
    finally:
        if not a.keep:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
