#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""All LuxLibre reference designs standing side by side at true scale (render), for the web site and the README.

    xvfb-run -a python3 hardware/tools/lineup.py

writes docs/img/lineup.png    the lights standing on one baseline, heads up, seen straight from the button side with
                              a parallel projection (no perspective), on a transparent background (difference matting:
                              rendered once on white and once on black)
       docs/img/lineup.json   the picture's window in millimetres and each light's place in it, so a page can put
                              a ruler and labels on it at the right scale
       docs/img/lineup_light.png, lineup_dark.png   the same on a light and a dark stage, with a millimetre ruler and
                              each light's name and length (for the README)

Uses the FlashKa v0.7 renderer and the parts of each design's own render script. The black anodised finish is
shown; FlashKa's key ring and the EDCO buttons glow.
"""
import importlib.util
import json
import os
import sys

import numpy as np
import vtk
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
HW = os.path.dirname(HERE)
ROOT = os.path.dirname(HW)
PX_MM = 12.0            # output pixels per millimetre
SS = 2                  # supersampling
GAP = 15.0              # millimetres between the lights


def load(rel, name):
    path = os.path.join(HW, rel)
    sys.path.insert(0, os.path.dirname(path))
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


MR = load("edco-mini/tools/housing/edco_mini_render.py", "edco_mini_render")
R = MR.R
FK_CYAN = (0.133, 0.827, 0.933)


def lights():
    """(id, name, parts, length, half width across the view, orientation): parts in the design's own coordinates,
    the light along +X from its head at X = 0"""
    out = []
    ER = load("edco-v01/tools/housing/edco_render.py", "edco_render")
    VR = load("edco-v02/tools/housing/edco_v02_render.py", "edco_v02_render")
    PR = load("edco-prism/tools/housing/edco_prism_render.py", "edco_prism_render")
    fk_dir = os.path.join(HW, "flashka-keychain-v07", "cad")
    FK = R.Model(fk_dir)
    fk = FK.closed(lit=True)
    for pt in fk:
        if pt.glow:
            pt.glow_color = FK_CYAN
    out.append(("flashka", "FlashKa v0.7", fk, FK.p.L, -90.0, (0.0, 0.0, -FK.p.H / 2)))
    m = ER.Model()
    skip = ER.INSIDE + tuple(n for n in m.d if n.startswith("bp_")) + ("split_ring",)
    out.append(("edco-v01", "EDCO v0.1", m.parts("black", skip=skip, glow_ind=True), m.p.L, 90.0, (0, 0, 0)))
    for sz in ("18", "14"):
        m = VR.Model(sz, collar_angle=180.0)
        out.append(("edco-" + sz, "EDCO-%s" % sz, m.parts("black", skip=VR.closed_skip(m) + ("split_ring",), glow=True),
                    m.p.L, 90.0, (0, 0, 0)))
    m = PR.Model(magnet=True)
    out.append(("prism", "EDCO Prism", m.parts("black", skip=PR.closed_skip(m) + ("split_ring",), glow=PR.HALO),
                m.p.L, 90.0, (0, 0, 0)))
    for sz in ("16", "14"):
        m = MR.Model(sz, magnet=True)
        out.append(("mini-" + sz, "EDCO Mini-%s" % sz,
                    m.parts("black", skip=MR.closed_skip(m) + ("split_ring", "lanyard"), glow=MR.HALO),
                    m.p.L, 90.0, (0, 0, 0)))
    return out


def stand(parts, x_pos, length, rot_x, pre):
    """stand the light on the baseline Z = 0 with its head up, centred on X = x_pos, button side towards -Y"""
    t = vtk.vtkTransform()
    t.PostMultiply()
    t.Translate(*pre)
    t.RotateX(rot_x)
    t.RotateY(90.0)
    t.Translate(x_pos, 0.0, length)
    m = vtk.vtkMatrix4x4()
    m.DeepCopy(t.GetMatrix())
    for pt in parts:
        pt.actor.SetUserMatrix(m)


def bounds_x(st):
    b = [0.0] * 6
    st.ren.ComputeVisiblePropBounds(b)
    return b


def main():
    items = lights()
    items.sort(key=lambda it: -it[3])                 # longest first, from the left
    st = R.studio()
    placed, allparts = [], []
    x = 0.0
    for (key, name, parts, L, rx, pre) in items:
        st.set_parts(parts)
        stand(parts, 0.0, L, rx, pre)
        b = bounds_x(st)
        w0, w1 = b[0], b[1]
        xc = x - w0
        stand(parts, xc, L, rx, pre)
        placed.append(dict(id=key, name=name, length_mm=round(L, 2), x0=round(x, 2), x1=round(x + (w1 - w0), 2),
                           top=round(b[5], 2)))
        x += (w1 - w0) + GAP
        allparts += parts
    st.set_parts(allparts)
    b = bounds_x(st)
    pad = 4.0
    X0, X1, Z0, Z1 = b[0] - pad, b[1] + pad, -pad, b[5] + pad
    Wmm, Hmm = X1 - X0, Z1 - Z0
    W, H = int(round(Wmm * PX_MM * SS)), int(round(Hmm * PX_MM * SS))
    cam = st.ren.GetActiveCamera()
    cam.ParallelProjectionOn()
    cam.SetFocalPoint((X0 + X1) / 2, 0.0, (Z0 + Z1) / 2)
    cam.SetPosition((X0 + X1) / 2, -400.0, (Z0 + Z1) / 2)     # straight from the side: lengths at true scale
    cam.SetViewUp(0, 0, 1)
    cam.SetParallelScale(Hmm / 2.0)                              # half the window height in mm
    st.size(W, H)
    imgs = {}
    for bg in ((1, 1, 1), (0, 0, 0)):
        st.ren.SetBackground(*bg)
        img, _ = st.grab(glow=False)
        imgs[bg] = img.astype(np.float32) / 255.0
    w, k = imgs[(1, 1, 1)], imgs[(0, 0, 0)]
    alpha = np.clip(1.0 - (w - k).mean(axis=2), 0.0, 1.0)
    rgb = np.where(alpha[..., None] > 1e-3, k / np.maximum(alpha[..., None], 1e-3), 0.0)
    rgba = np.dstack([np.clip(rgb, 0, 1), alpha])
    im = Image.fromarray((rgba * 255 + 0.5).astype(np.uint8), "RGBA")
    im = im.resize((W // SS, H // SS), Image.LANCZOS)
    out_png = os.path.join(ROOT, "docs", "img", "lineup.png")
    im.save(out_png, optimize=True)
    info = dict(about="docs/img/lineup.png: the window in millimetres (X across, Z up, baseline Z = 0) and each "
                      "light's place; pixels per millimetre = width / (x1 - x0)",
                window=dict(x0=round(X0, 3), x1=round(X1, 3), z0=round(Z0, 3), z1=round(Z1, 3)),
                size_px=[im.width, im.height], lights=placed)
    json.dump(info, open(os.path.join(ROOT, "docs", "img", "lineup.json"), "w"), indent=1)
    print("wrote", out_png, im.size)
    for theme in ("light", "dark"):
        labelled(im, info, theme)


STAGES = {"light": dict(page=(255, 255, 255), stage=(234, 239, 245), ink=(18, 24, 32), ink2=(79, 93, 109),
                        rule=(138, 151, 166)),
          "dark": dict(page=(13, 17, 23), stage=(42, 52, 64), ink=(233, 238, 244), ink2=(158, 171, 187),
                       rule=(127, 140, 155))}


def font(size, bold=False):
    from PIL import ImageFont
    for f in (("/usr/share/fonts/opentype/inter/Inter-SemiBold.otf" if bold else "/usr/share/fonts/opentype/inter/Inter-Regular.otf"),
              "/usr/share/fonts/truetype/dejavu/DejaVuSans%s.ttf" % ("-Bold" if bold else "")):
        if os.path.exists(f):
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def labelled(im, info, theme, out_w=1800):
    """the lineup on a stage with a ruler on the left and a name and length under each light"""
    from PIL import ImageDraw
    c = STAGES[theme]
    w = info["window"]
    k = out_w / im.width
    pic = im.resize((out_w, round(im.height * k)), Image.LANCZOS)
    px_mm = pic.width / (w["x1"] - w["x0"])
    left, top, lab_h, pad = 90, 40, 86, 24
    W, H = left + pic.width + pad, top + pic.height + lab_h
    out = Image.new("RGB", (W, H), c["page"])
    d = ImageDraw.Draw(out)
    d.rounded_rectangle((0, 0, W - 1, H - 1), radius=28, fill=c["stage"])
    out.paste(pic, (left, top), pic)
    zpx = lambda z: top + (w["z1"] - z) * px_mm                 # noqa: E731
    xpx = lambda x: left + (x - w["x0"]) * px_mm               # noqa: E731
    f_small, f_name, f_len = font(20), font(25, True), font(22)
    for z in range(0, 101, 10):
        y = zpx(z)
        d.line((left - (26 if z % 20 == 0 else 14), y, left - 4, y), fill=c["rule"], width=2)
        if z % 20 == 0:
            t = "%d mm" % z if z == 0 else str(z)
            tw = d.textlength(t, font=f_small)
            d.text((left - 32 - tw, y - 12), t, fill=c["ink2"], font=f_small)
    d.line((left - 4, zpx(0), left - 4, zpx(100)), fill=c["rule"], width=2)
    d.line((left, zpx(0), left + pic.width - 8, zpx(0)), fill=c["rule"], width=1)
    for L in info["lights"]:
        xc = xpx((L["x0"] + L["x1"]) / 2)
        for (t, f, col, dy) in ((L["name"], f_name, c["ink"], 14), ("%.1f mm" % (L["length_mm"] + 1e-6), f_len, c["ink2"], 46)):
            tw = d.textlength(t, font=f)
            d.text((xc - tw / 2, zpx(0) + dy), t, fill=col, font=f)
    path = os.path.join(ROOT, "docs", "img", "lineup_%s.png" % theme)
    out.save(path, optimize=True)
    print("wrote", path, out.size)


if __name__ == "__main__":
    if "--labels" in sys.argv:       # only redraw the README versions from docs/img/lineup.png and lineup.json
        img = Image.open(os.path.join(ROOT, "docs", "img", "lineup.png"))
        meta = json.load(open(os.path.join(ROOT, "docs", "img", "lineup.json")))
        for th in ("light", "dark"):
            labelled(img, meta, th)
    else:
        main()
