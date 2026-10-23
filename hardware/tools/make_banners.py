#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""The LuxLibre banner pictures and the GitHub social preview: all seven reference designs standing together.

    xvfb-run -a python3 hardware/tools/make_banners.py [--plain] [--keep DIR]

writes docs/img/luxlibre_banner_light.png   README banner for GitHub's light theme (1600 x 520, rounded card)
       docs/img/luxlibre_banner_dark.png    README banner for GitHub's dark theme (1600 x 520, rounded card)
       docs/img/social_preview.png          GitHub social preview (1280 x 640)

The lights (FlashKa v0.7, EDCO-18, EDCO-14, EDCO v0.1, EDCO Prism, EDCO Mini-16, EDCO Mini-14) stand on one
baseline, tallest first, each turned a little, seen from the front and a little above with perspective. They are
rendered once on white and once on black and cut out by difference matting, then placed on the card with a soft
shadow. The layout, colours, fonts and helpers (cut-out, shadow, grid, rounded card) are those of the FlashKa v0.7
banners (hardware/flashka-keychain-v07/tools/make_banners.py), so the look stays the same.
The optics are lit: warm white for FlashKa and the EDCO lights, the colour beam for the Prism (--plain: unlit).

Needs python3 with vtk, numpy, PIL and cadquery, and xvfb-run.
"""
import argparse
import importlib.util
import os
import shutil
import sys
import tempfile

import numpy as np
import vtk
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
HW = os.path.dirname(HERE)
ROOT = os.path.dirname(HW)
NOTE = "FlashKa v0.7 and the EDCO family - renders"
SUB = ["Open-source firmware, design rules", "and seven flashlights you can build"]


def load(path, name):
    sys.path.insert(0, os.path.dirname(path))
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


LU = load(os.path.join(HERE, "lineup.py"), "lineup")
FKB = load(os.path.join(HW, "flashka-keychain-v07", "tools", "make_banners.py"), "fk_make_banners")
R = LU.R
WARM = (1.00, 0.96, 0.86)
MAGENTA = (1.00, 0.25, 0.85)


def place(parts, x_pos, length, rot_x, pre, yaw):
    """stand the light (head up, button side towards -Y) and turn it by `yaw` degrees about its own axis"""
    t = vtk.vtkTransform()
    t.PostMultiply()
    t.Translate(*pre)
    t.RotateX(rot_x)
    t.RotateY(90.0)
    t.Translate(0.0, 0.0, length)
    t.RotateZ(yaw)
    t.Translate(x_pos, 0.0, 0.0)
    m = vtk.vtkMatrix4x4()
    m.DeepCopy(t.GetMatrix())
    for pt in parts:
        pt.actor.SetUserMatrix(m)


def light_up(key, parts):
    for pt in parts:
        if pt.name in ("optic_lens", "_ref_optic_lens"):
            pt.glow = True
            pt.glow_color = MAGENTA if key == "prism" else WARM


def render(out_dir, glow, gap=13.0, yaw=-28.0, W=3200, H=1500):
    items = LU.lights()
    items.sort(key=lambda it: -it[3])
    st = R.studio()
    allparts, x = [], 0.0
    for (key, name, parts, L, rx, pre) in items:
        if glow:
            light_up(key, parts)
        st.set_parts(parts)
        place(parts, 0.0, L, rx, pre, yaw)
        b = LU.bounds_x(st)
        place(parts, x - b[0], L, rx, pre, yaw)
        x += (b[1] - b[0]) + gap
        allparts += parts
    st.set_parts(allparts)
    b = LU.bounds_x(st)
    focal = np.array([(b[0] + b[1]) / 2, (b[2] + b[3]) / 2, (b[4] + b[5]) / 2])
    d = np.array([-0.32, -1.0, 0.42])
    d /= np.linalg.norm(d)
    cam = st.ren.GetActiveCamera()
    cam.ParallelProjectionOff()
    cam.SetViewAngle(16.0)
    cam.SetFocalPoint(*focal)
    cam.SetPosition(*(focal + d * 900.0))
    cam.SetViewUp(0, 0, 1)
    st.size(W, H)
    st.ren.ResetCamera(b)
    cam.SetFocalPoint(*focal)
    cam.SetPosition(*(focal + d * cam.GetDistance()))
    cam.Zoom(1.25)
    paths = {}
    for nm, bg in (("white", (1, 1, 1)), ("black", (0, 0, 0))):
        st.ren.SetBackground(*bg)
        img, g = st.grab(glow=glow)
        if glow:
            img = R.bloom(img, g, radius=7.0, strength=1.1)
        p = os.path.join(out_dir, "family_%s.png" % nm)
        Image.fromarray(img).save(p)
        paths[nm] = p
    return paths


def compose(kind, theme_name, cut, size, out):
    """the FlashKa v0.7 banner layout with the family render and the new subtitle and note"""
    th = FKB.THEMES[theme_name]
    W, H = size
    canvas = np.empty((H, W, 3), np.float32)
    canvas[:] = np.array(th["bg"], np.float32) / 255.0
    ga = FKB.grid_layer(W, H, 32, int(W * 0.40))
    gcol = np.array(th["grid"], np.float32) / 255.0
    canvas[:] = canvas * (1 - ga[..., None]) + gcol * ga[..., None]
    bx0, by0, bx1, by1 = (640, 20, W - 34, H - 52) if kind == "banner" else (60, 214, W - 60, H - 58)
    asp = cut.alpha.shape[0] / cut.alpha.shape[1]
    rw = int(min(bx1 - bx0, (by1 - by0) / asp))
    rh = int(round(rw * asp))
    rx, ry = bx0 + (bx1 - bx0 - rw) // 2, by0 + (by1 - by0 - rh) // 2
    FKB.paste_cutout(canvas, cut, rx, ry, rw, shadow=th["shadow"], glow_strength=0.5)
    img = Image.fromarray((np.clip(canvas, 0, 1) * 255 + 0.5).astype(np.uint8), "RGB")
    dr = ImageDraw.Draw(img)
    if kind == "banner":
        tx, ty = 84, 136
        f_big, f_sub, f_note = FKB.font("bold", 112), FKB.font("regular", 31), FKB.font("regular", 21)
    else:
        tx, ty = 84, 30
        f_big, f_sub, f_note = FKB.font("bold", 92), FKB.font("regular", 29), FKB.font("regular", 21)
    dr.text((tx - 4, ty), "LuxLibre", font=f_big, fill=th["text"])
    bb = dr.textbbox((tx - 4, ty), "LuxLibre", font=f_big)
    yy = bb[3] + 26
    dr.rectangle([tx, yy, tx + 64, yy + 5], fill=th["accent"])
    yy += 28
    for ln in (SUB if kind == "banner" else [" ".join(SUB)]):
        dr.text((tx, yy), ln, font=f_sub, fill=th["muted"])
        yy += int(f_sub.size * 1.42)
    nb = dr.textbbox((0, 0), NOTE, font=f_note)
    nx, ny = W - 34 - (nb[2] - nb[0]) - 24, H - 32 - (nb[3] - nb[1])
    dr.text((nx, ny), NOTE, font=f_note, fill=th["muted"])
    if kind == "banner":                                     # rounded corners + 1 px border, as in v0.7
        rad = 18
        mask = Image.new("L", (W * 4, H * 4), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, W * 4 - 1, H * 4 - 1], radius=rad * 4, fill=255)
        mask = mask.resize((W, H), Image.LANCZOS)
        border = Image.new("L", (W * 4, H * 4), 0)
        ImageDraw.Draw(border).rounded_rectangle([0, 0, W * 4 - 1, H * 4 - 1], radius=rad * 4, outline=255, width=4)
        border = border.resize((W, H), Image.LANCZOS)
        img = Image.composite(Image.new("RGB", (W, H), th["border"]), img, border)
        img = img.convert("RGBA")
        img.putalpha(mask)
    img.save(out, optimize=True)
    print("wrote %s  %s  %.0f kB" % (os.path.relpath(out, ROOT), img.size, os.path.getsize(out) / 1e3))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plain", action="store_true", help="optics not lit")
    ap.add_argument("--keep", default=None, help="keep the two family renders in this folder")
    ap.add_argument("--out-dir", default=os.path.join(ROOT, "docs", "img"))
    a = ap.parse_args()
    tmp = a.keep or tempfile.mkdtemp(prefix="luxlibre_banner_")
    os.makedirs(tmp, exist_ok=True)
    try:
        paths = render(tmp, not a.plain)
        cut = FKB.Cutout(paths["white"], paths["black"], (0, 0, 0))
        os.makedirs(a.out_dir, exist_ok=True)
        compose("banner", "light", cut, (1600, 520), os.path.join(a.out_dir, "luxlibre_banner_light.png"))
        compose("banner", "dark", cut, (1600, 520), os.path.join(a.out_dir, "luxlibre_banner_dark.png"))
        compose("social", "light", cut, (1280, 640), os.path.join(a.out_dir, "social_preview.png"))
    finally:
        if not a.keep:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
