#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""FlashKa Keychain v0.7: animated renders (GIF).

Rebuild (from tools/housing/):

    xvfb-run -a python3 render_anim.py [--pcb-step FILE] [--kb-step FILE] [--kicad-pcb FILE] [--kb-kicad-pcb FILE]

Outputs (renders of the design; FlashKa has not been built yet):
    ../../assets/v07/flashka_v07_turntable.gif   closed light, ring lit, one turn about its long axis
                                                 (800 px wide, 48 frames x 80 ms, loop)
    ../../assets/v07/flashka_v07_exploded.gif    the assembly separating along Z and back (800 px wide)
    (copies in ../../renders/)

Options:
    --only turntable,exploded      build a subset (default: both)
    --frames N                     turntable frames, 36 to 60 (default 48)
    --cad DIR                      cad folder (default ../../cad)
    --out-dir DIR                  write the GIFs into DIR only (previews)
    --tmp DIR / --keep             frame folder (default: a new temporary folder, removed at the end)

Needs python3 with vtk, numpy and PIL, plus ffmpeg and xvfb-run.  Parts, materials and the studio come from
render.py.  GIFs: ffmpeg palettegen + paletteuse with exact per-frame delays.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time

import numpy as np
import vtk
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import render as R  # noqa: E402

V7 = os.path.normpath(os.path.join(HERE, "..", ".."))
OUT_TURNTABLE = os.path.join(V7, "assets", "v07", "flashka_v07_turntable.gif")
OUT_EXPLODED = os.path.join(V7, "assets", "v07", "flashka_v07_exploded.gif")


def log(*a):
    print(*a, flush=True)


def rot_x_about(theta_deg, centre):
    t = vtk.vtkTransform()
    t.PostMultiply()
    t.Translate(-centre[0], -centre[1], -centre[2])
    t.RotateX(theta_deg)
    t.Translate(*centre)
    m = vtk.vtkMatrix4x4()
    m.DeepCopy(t.GetMatrix())
    return m


def union_box(a, b):
    if a is None:
        return b
    if b is None:
        return a
    return min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])


def fit_camera(st, states, apply_state, direction, up=(0, 0, 1), view_angle=20.0, fill=0.92, W0=560):
    """camera along `direction`, zoom / pan until the union of the content of all states fills `fill`; the window
    aspect follows the content.  Returns the aspect (height / width)."""
    cam = st.ren.GetActiveCamera()
    d = R.unit(direction)
    upv0 = R.unit(up)
    B = None
    for s in states:
        apply_state(s)
        b = [0.0] * 6
        st.ren.ComputeVisiblePropBounds(b)
        B = b if B is None else [min(B[0], b[0]), max(B[1], b[1]), min(B[2], b[2]), max(B[3], b[3]),
                                 min(B[4], b[4]), max(B[5], b[5])]
    focal = np.array([(B[0] + B[1]) / 2, (B[2] + B[3]) / 2, (B[4] + B[5]) / 2])
    cam.SetViewAngle(view_angle)
    cam.SetViewUp(*upv0)
    cam.SetFocalPoint(*focal)
    cam.SetPosition(*(focal + d * 100))
    st.ren.ResetCamera(B)
    cam.SetFocalPoint(*focal)
    cam.SetPosition(*(focal + d * cam.GetDistance()))
    cam.SetViewUp(*upv0)
    asp = 0.6
    for it in range(12):
        H0 = max(int(round(W0 * asp)), 48)
        st.size(W0, H0)
        box = None
        for s in states:
            apply_state(s)
            img, _ = st.grab(glow=False)
            box = union_box(box, R.content_box(img))
        if box is None:
            break
        x0, y0, x1, y1 = box
        bw, bh = x1 - x0 + 1, y1 - y0 + 1
        touching = x0 <= 1 or y0 <= 1 or x1 >= W0 - 2 or y1 >= H0 - 2
        new_asp = min(max(bh / bw, 0.2), 1.6)
        s_ = fill * W0 / bw * (asp / new_asp)
        cx, cy = (x0 + x1) / 2, (H0 - 1 - (y0 + y1) / 2)
        dxp, dyp = cx - W0 / 2, cy - H0 / 2
        if (not touching and abs(s_ - 1) < 0.01 and abs(dxp) < 0.004 * W0 and abs(dyp) < 0.004 * H0
                and abs(new_asp - asp) < 0.01):
            break
        dist = cam.GetDistance()
        wpp = 2 * dist * np.tan(np.radians(cam.GetViewAngle() / 2)) / H0
        right = R.unit(np.cross(-d, upv0))
        upv = np.cross(right, -d)
        shift = right * dxp * wpp + upv * dyp * wpp
        cam.SetFocalPoint(*(np.array(cam.GetFocalPoint()) + shift))
        cam.SetPosition(*(np.array(cam.GetPosition()) + shift))
        cam.Zoom(s_ if not touching else min(s_, 0.85))
        asp = new_asp
    return asp


def write_gif(frames, delays_cs, out, tmp, dither="sierra2_4a", colors=256):
    lst = os.path.join(tmp, os.path.splitext(os.path.basename(out))[0] + ".ffconcat")
    with open(lst, "w") as f:
        f.write("ffconcat version 1.0\n")
        for pth, d in zip(frames, delays_cs):
            f.write("file '%s'\noption framerate 100\nduration %.2f\n" % (os.path.abspath(pth), d / 100.0))
    vf = ("split[a][b];[a]palettegen=max_colors=%d:stats_mode=full[p];"
          "[b][p]paletteuse=dither=%s:diff_mode=rectangle" % (colors, dither))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-vf", vf,
           "-fps_mode", "vfr", "-loop", "0", "-final_delay", str(int(delays_cs[-1])), "-map_metadata", "-1", out]
    subprocess.run(cmd, check=True)
    log("wrote %s  (%d frames, %.2f MB, loop %.2f s)" % (out, len(frames), os.path.getsize(out) / 1e6,
                                                        sum(delays_cs) / 100.0))
    return out


def save_frames(raw, tmp, name, box, out_w, margin):
    x0, y0, x1, y1 = box
    m = int(round(margin * (x1 - x0)))
    paths = []
    for k, arr in enumerate(raw):
        h, w = arr.shape[:2]
        cx0, cy0, cx1, cy1 = max(x0 - m, 0), max(y0 - m, 0), min(x1 + m, w - 1), min(y1 + m, h - 1)
        im = Image.fromarray(arr[cy0:cy1 + 1, cx0:cx1 + 1])
        oh = int(round(im.height * out_w / im.width / 2.0)) * 2
        im = im.resize((out_w, oh), Image.LANCZOS)
        pth = os.path.join(tmp, "%s_%03d.png" % (name, k))
        im.save(pth, compress_level=1)
        paths.append(pth)
    return paths


# --------------------------------------------------------------------------
def turntable(model, tmp, out, frames=48, delay_cs=8, out_w=800, ss=2.2):
    p = model.p
    parts = model.closed(lit=True)
    st = R.studio()
    st.set_parts(parts)
    centre = (0.0, 0.0, p.H / 2)

    def apply(theta):
        m = rot_x_about(theta, centre)
        for pt in parts:
            pt.actor.SetUserMatrix(m)

    theta0 = 205.0              # first frame: the bottom face (keys, lit ring) towards the camera
    thetas = [theta0 + 360.0 * k / frames for k in range(frames)]
    direction, up = (-0.50, -0.80, 0.60), (0, 0, 1)
    fill, margin = 0.90, 0.035
    asp = fit_camera(st, thetas[::4], apply, direction, up, view_angle=18.0, fill=fill)
    Wf = int(round(out_w * ss / (fill * (1 + 2 * margin))))
    Hf = int(round(Wf * asp))
    st.size(Wf, Hf)
    log("turntable: %d frames, render %d x %d" % (frames, Wf, Hf))
    raw, box = [], None
    t0 = time.time()
    for th in thetas:
        apply(th)
        img, g = st.grab()
        img = R.bloom(img, g, radius=0.9 * ss * 2.2, strength=0.85)
        raw.append(img)
        box = union_box(box, R.content_box(img))
    log("  rendered in %.1f s" % (time.time() - t0))
    for pt in parts:
        pt.actor.SetUserMatrix(None)
    paths = save_frames(raw, tmp, "tt", box, out_w, margin)
    return write_gif(paths, [delay_cs] * len(paths), out, tmp)


def ease(x):
    x = min(max(x, 0.0), 1.0)
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def explode_groups(model):
    """(static parts, [(label, parts, dz, t0, t1)]): every group moves straight along Z by dz between t0 and t1 of
    the 0..1 explosion; the keys and their plates go down, everything above the floor goes up"""
    m = model
    extras = m.extra_parts()
    static = [m.part(n) for n in ("FlashKa_tray", "_ref_optic_holder", "_ref_optic_lens", "_ref_led", "_ref_mcpcb",
                                  "_ref_laser") if m.cad.has(n)] + [x for x in extras if x.name != "laser_set_screw"]
    groups = [
        ("lid screws", [m.part("_ref_lidscrews")], 58.0, 0.00, 0.40),
        ("lid", [m.part("FlashKa_lid")], 48.0, 0.04, 0.46),
        ("laser set screw (under the lid)", [x for x in extras if x.name == "laser_set_screw"], 11.0, 0.12, 0.54),
        ("RF window insert", [m.part("FlashKa_rf_window")], 36.0, 0.10, 0.52),
        ("pads", [m.part(n) for n in ("_ref_pad", "_ref_pad2") if m.cad.has(n)], 29.0, 0.16, 0.58),
        ("main board", m.pcb.parts(), 23.0, 0.22, 0.64),
        ("cell", [m.part(n) for n in ("_ref_cell", "_ref_cell_strip_front", "_ref_cell_strip_rear",
                                      "_ref_cell_joint_front", "_ref_cell_joint_rear") if m.cad.has(n)], 26.0, 0.24, 0.66),
        ("antenna spacer", [m.part("FlashKa_antenna_spacer")], 16.0, 0.28, 0.70),
        ("key board screws", [m.part("_ref_kbscrews")], 13.0, 0.34, 0.76),
        ("key board", m.kb_free.parts(), 7.0, 0.38, 0.80),
        ("keys", m.keys(lit=True), -12.0, 0.46, 0.90),
    ]
    return static, groups


def exploded(model, tmp, out, steps=30, out_w=800, ss=2.2):
    static, groups = explode_groups(model)
    parts = static + [pt for g in groups for pt in g[1]]
    st = R.studio()
    st.set_parts(parts)
    base = {id(pt): np.array(pt.actor.GetPosition(), float) for pt in parts}

    def apply(u):
        for _, gparts, dz, s0, s1 in groups:
            f = ease((u - s0) / (s1 - s0))
            for pt in gparts:
                pt.actor.SetPosition(*(base[id(pt)] + np.array([0.0, 0.0, dz * f])))

    us = [k / (steps - 1) for k in range(steps)]
    fill, margin = 0.92, 0.03
    asp = fit_camera(st, [0.0, 0.5, 0.75, 1.0], apply, (-0.45, -1.0, 0.66), view_angle=20.0, fill=fill)
    Wf = int(round(out_w * ss / (fill * (1 + 2 * margin))))
    Hf = int(round(Wf * asp))
    st.size(Wf, Hf)
    log("exploded: %d steps, render %d x %d" % (steps, Wf, Hf))
    raw, box = [], None
    t0 = time.time()
    for u in us:
        apply(u)
        img, g = st.grab()
        img = R.bloom(img, g, radius=0.9 * ss * 2.2, strength=0.8)
        raw.append(img)
        box = union_box(box, R.content_box(img))
    log("  rendered in %.1f s" % (time.time() - t0))
    paths = save_frames(raw, tmp, "ex", box, out_w, margin)
    seq = paths + paths[-2:0:-1]
    delays = [6] * len(paths) + [5] * (len(paths) - 2)
    delays[0] = 120
    delays[len(paths) - 1] = 200
    return write_gif(seq, delays, out, tmp)


STAGES = ("turntable", "exploded")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default=",".join(STAGES))
    ap.add_argument("--tmp", default=None)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--cad", default=os.path.join(V7, "cad"))
    ap.add_argument("--pcb-step", default=None)
    ap.add_argument("--kb-step", default=None)
    ap.add_argument("--kicad-pcb", default=None)
    ap.add_argument("--kb-kicad-pcb", default=None)
    ap.add_argument("--frames", type=int, default=48)
    ap.add_argument("--out-dir", default=None)
    a = ap.parse_args()
    if not 36 <= a.frames <= 60:
        ap.error("--frames must be 36 to 60")
    stages = [s.strip() for s in a.only.split(",") if s.strip()]
    tmp = a.tmp or tempfile.mkdtemp(prefix="flashka_anim_")
    os.makedirs(tmp, exist_ok=True)
    od = a.out_dir
    outs = {"tt": os.path.join(od, os.path.basename(OUT_TURNTABLE)) if od else OUT_TURNTABLE,
            "ex": os.path.join(od, os.path.basename(OUT_EXPLODED)) if od else OUT_EXPLODED}
    try:
        model = R.Model(a.cad, a.pcb_step, a.kb_step, a.kicad_pcb, kb_kicad_pcb=a.kb_kicad_pcb)
        if "turntable" in stages:
            turntable(model, tmp, outs["tt"], frames=a.frames)
        if "exploded" in stages:
            exploded(model, tmp, outs["ex"])
        if not od:              # copies in renders/
            for k in ("tt", "ex"):
                if os.path.exists(outs[k]):
                    shutil.copyfile(outs[k], os.path.join(V7, "renders", os.path.basename(outs[k])))
    finally:
        if not a.keep and not a.tmp:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
