#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""FlashKa Keychain v0.6: animated renders (GIF), the LuxLibre banner pictures and the still renders with
the real PCB.

Rebuild everything with one command (from tools/housing/, about 3 min on 2 CPU cores):

    xvfb-run -a python3 render_anim.py

Outputs (all are computer renders of the design; FlashKa has not been built yet):
    ../../assets/v06/flashka_v06_turntable.gif   closed light, ring lit, one turn about its long axis
                                                 (800 px wide, 60 frames x 70 ms, loop)
    ../../assets/v06/flashka_v06_exploded.gif    assembly with the real PCB model separating along Z and back
                                                 (800 px wide, 30 steps out + 28 back, about 6.3 s loop)
    <LuxLibre>/docs/img/luxlibre_banner_light.png  README banner for GitHub's light theme (1600 x 520)
    <LuxLibre>/docs/img/luxlibre_banner_dark.png   README banner for GitHub's dark theme (1600 x 520)
    <LuxLibre>/docs/img/social_preview.png         GitHub social preview (1280 x 640)
    ../../renders/housing_open_top.png, housing_open_iso.png, housing_exploded.png  (stage "stills": render.py,
                                                 unchanged, with --pcb-step / --kicad-pcb; copied to assets/v06/)

Options:
    --only turntable,exploded,banner,stills   build a subset (default: all four stages)
    --frames N                         turntable frames, 36 to 60 (default 60)
    --tmp DIR                          frame folder (default: a new temporary folder, removed at the end)
    --keep                             keep the frame folder
    --out-dir DIR                      write every output into DIR instead (previews)
    --cad DIR  --pcb-step FILE  --kicad-pcb FILE   inputs (defaults: the v0.6 cad/ folder, the PCB STEP and
                                       the .kicad_pcb of kicad/FlashKa_main/)

Needs python3 with vtk, cadquery, numpy and PIL, plus ffmpeg and xvfb-run.  Parts, colours and the
laser-marking textures come from render.py (imported, not changed); the PCB is the real KiCad STEP
model (with the stand-ins render.py adds for parts the STEP lacks).  GIFs: ffmpeg palettegen +
paletteuse with exact per-frame delays.
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
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import render as R  # noqa: E402  (parts, colours, marking quads, PCB loader)

V6 = os.path.normpath(os.path.join(HERE, "..", ".."))
REPO = os.path.normpath(os.path.join(V6, "..", ".."))
CYAN = (0.30, 0.95, 1.0)                   # the lit light-pipe ring, as render.py

OUT_TURNTABLE = os.path.join(V6, "assets", "v06", "flashka_v06_turntable.gif")
OUT_EXPLODED = os.path.join(V6, "assets", "v06", "flashka_v06_exploded.gif")
OUT_BANNER_LIGHT = os.path.join(REPO, "docs", "img", "luxlibre_banner_light.png")
OUT_BANNER_DARK = os.path.join(REPO, "docs", "img", "luxlibre_banner_dark.png")
OUT_SOCIAL = os.path.join(REPO, "docs", "img", "social_preview.png")


def log(*a):
    print(*a, flush=True)


# --------------------------------------------------------------------------
# scene
# --------------------------------------------------------------------------
def _window(ren, peel=True):
    win = vtk.vtkRenderWindow()
    win.SetOffScreenRendering(1)
    win.AddRenderer(ren)
    win.SetAlphaBitPlanes(1)
    win.SetMultiSamples(0)
    if peel:
        ren.SetUseDepthPeeling(1)
        ren.SetMaximumNumberOfPeels(12)
        ren.SetOcclusionRatio(0.0)
    return win


class Rig:
    """The parts in one renderer (lights as render.py) plus, optionally, a glow-mask renderer that
    shares the camera: every part black except the glowing ones (the lit ring of the light-pipe tube),
    used for a soft bloom around the ring."""

    def __init__(self, parts, glow=(), bg=(1.0, 1.0, 1.0), extra_lights=()):
        self.parts = parts
        self.ren = R.make_renderer(parts)
        self.ren.SetBackground(*bg)
        for lt in extra_lights:
            self.ren.AddLight(lt)
        self.win = _window(self.ren)
        self.cam = self.ren.GetActiveCamera()
        self.pairs = []
        self.mren = None
        if glow:
            self.mren = vtk.vtkRenderer()
            self.mren.SetBackground(0, 0, 0)
            self.mren.AutomaticLightCreationOff()
            self.mren.SetActiveCamera(self.cam)
            for pt in parts:
                if pt.name.startswith("mark_"):
                    continue
                a = vtk.vtkActor()
                a.SetMapper(pt.actor.GetMapper())
                pr = a.GetProperty()
                pr.SetDiffuse(0.0)
                pr.SetSpecular(0.0)
                if pt.name in glow:
                    pr.SetColor(*CYAN)
                    pr.SetAmbient(1.0)
                else:
                    pr.SetColor(0, 0, 0)
                    pr.SetAmbient(0.0)
                self.mren.AddActor(a)
                self.pairs.append((pt.actor, a))
            self.mwin = _window(self.mren, peel=False)

    def size(self, w, h):
        self.win.SetSize(int(w), int(h))
        if self.mren is not None:
            self.mwin.SetSize(int(w), int(h))

    def shot(self, glow=True):
        """-> (RGB image, glow mask image or None) of the current state"""
        self.ren.ResetCameraClippingRange()
        self.win.Render()
        img = R._grab(self.win)
        g = None
        if glow and self.mren is not None:
            for a, m in self.pairs:
                m.SetPosition(a.GetPosition())
                m.SetUserMatrix(a.GetUserMatrix())
            self.mren.ResetCameraClippingRange()
            self.mwin.Render()
            g = R._grab(self.mwin)
        return img, g


def unit(v):
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


def rot_x_about(theta_deg, centre):
    """4x4 vtkMatrix: rotation about the X axis through `centre` (0, cy, cz)"""
    t = vtk.vtkTransform()
    t.PostMultiply()
    t.Translate(-centre[0], -centre[1], -centre[2])
    t.RotateX(theta_deg)
    t.Translate(*centre)
    m = vtk.vtkMatrix4x4()
    m.DeepCopy(t.GetMatrix())
    return m


def visible_bounds(ren):
    b = [0.0] * 6
    ren.ComputeVisiblePropBounds(b)
    return b


def union_box(a, b):
    if a is None:
        return b
    if b is None:
        return a
    return min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])


def content_box(arr, bg, thr=10):
    """bounding box of the pixels that differ from the background colour bg (0-255 RGB)"""
    diff = np.abs(arr.astype(np.int16) - np.array(bg, np.int16)).max(axis=2) > thr
    ys, xs = np.where(diff)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def fit_camera(rig, states, apply_state, direction, up=(0, 0, 1), view_angle=20.0, fill=0.92, W0=640,
               aspect=None, bg=(255, 255, 255)):
    """Point the camera along `direction` (from the scene towards the camera) and zoom / pan until the
    union of the content of all `states` fills `fill` of the window, centred.  With aspect=None the
    window aspect follows the content.  Returns the window aspect (height / width)."""
    cam = rig.cam
    d = unit(direction)
    upv0 = unit(up)
    B = None
    for s in states:
        apply_state(s)
        b = visible_bounds(rig.ren)
        B = b if B is None else [min(B[0], b[0]), max(B[1], b[1]), min(B[2], b[2]), max(B[3], b[3]),
                                 min(B[4], b[4]), max(B[5], b[5])]
    focal = np.array([(B[0] + B[1]) / 2, (B[2] + B[3]) / 2, (B[4] + B[5]) / 2])
    cam.SetViewAngle(view_angle)
    cam.SetViewUp(*upv0)
    cam.SetFocalPoint(*focal)
    cam.SetPosition(*(focal + d * 100))
    rig.ren.ResetCamera(B)
    cam.SetFocalPoint(*focal)
    cam.SetPosition(*(focal + d * cam.GetDistance()))
    cam.SetViewUp(*upv0)
    asp = 0.6 if aspect is None else aspect
    for it in range(12):
        H0 = max(int(round(W0 * asp)), 48)
        rig.size(W0, H0)
        box = None
        for s in states:
            apply_state(s)
            img, _ = rig.shot(glow=False)
            box = union_box(box, content_box(img, bg))
        if box is None:
            break
        x0, y0, x1, y1 = box
        bw, bh = x1 - x0 + 1, y1 - y0 + 1
        touching = x0 <= 1 or y0 <= 1 or x1 >= W0 - 2 or y1 >= H0 - 2
        if aspect is None:
            # window aspect follows the content; the vertical view angle is kept, so a window of a
            # different height scales the content by new_asp / asp: compensate in the zoom
            new_asp = min(max(bh / bw, 0.2), 1.6)
            s = fill * W0 / bw * (asp / new_asp)
        else:
            new_asp = asp
            s = min(fill * W0 / bw, fill * H0 / bh)
        cx, cy = (x0 + x1) / 2, (H0 - 1 - (y0 + y1) / 2)
        dxp, dyp = cx - W0 / 2, cy - H0 / 2
        if (not touching and abs(s - 1) < 0.01 and abs(dxp) < 0.004 * W0 and abs(dyp) < 0.004 * H0
                and abs(new_asp - asp) < 0.01):
            break
        dist = cam.GetDistance()
        wpp = 2 * dist * np.tan(np.radians(cam.GetViewAngle() / 2)) / H0
        right = unit(np.cross(-d, upv0))
        upv = np.cross(right, -d)
        shift = right * dxp * wpp + upv * dyp * wpp
        cam.SetFocalPoint(*(np.array(cam.GetFocalPoint()) + shift))
        cam.SetPosition(*(np.array(cam.GetPosition()) + shift))
        cam.Zoom(s if not touching else min(s, 0.85))
        asp = new_asp
    return asp


def bloom(img, mask, radius, strength=0.9):
    """screen-blend a blurred copy of the glow mask onto the picture (two radii: core + halo)"""
    if mask is None:
        return img
    m = Image.fromarray(mask)
    g1 = np.asarray(m.filter(ImageFilter.GaussianBlur(radius)), np.float32) / 255
    g2 = np.asarray(m.filter(ImageFilter.GaussianBlur(radius * 3.0)), np.float32) / 255
    g = np.clip((0.75 * g1 + 0.55 * g2) * strength, 0, 1)
    base = img.astype(np.float32) / 255
    out = 1 - (1 - base) * (1 - g)
    return (out * 255 + 0.5).astype(np.uint8)


# --------------------------------------------------------------------------
# GIF writer: ffmpeg palettegen + paletteuse, exact per-frame delays (centiseconds)
# --------------------------------------------------------------------------
def write_gif(frames, delays_cs, out, tmp, dither="sierra2_4a", colors=256, stats="full"):
    lst = os.path.join(tmp, os.path.splitext(os.path.basename(out))[0] + ".ffconcat")
    with open(lst, "w") as f:
        f.write("ffconcat version 1.0\n")
        for p, d in zip(frames, delays_cs):
            f.write("file '%s'\noption framerate 100\nduration %.2f\n" % (os.path.abspath(p), d / 100.0))
    vf = ("split[a][b];[a]palettegen=max_colors=%d:stats_mode=%s[p];"
          "[b][p]paletteuse=dither=%s:diff_mode=rectangle" % (colors, stats, dither))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-vf", vf,
           "-fps_mode", "vfr", "-loop", "0", "-final_delay", str(int(delays_cs[-1])), out]
    subprocess.run(cmd, check=True)
    log("wrote %s  (%d frames, %.2f MB, loop %.2f s)" % (out, len(frames), os.path.getsize(out) / 1e6,
                                                        sum(delays_cs) / 100.0))
    return out


def save_frames(raw, tmp, name, box, out_w, margin):
    """crop every raw frame to the common content box (+ margin) and scale to out_w px wide"""
    x0, y0, x1, y1 = box
    m = int(round(margin * (x1 - x0)))
    paths = []
    for k, arr in enumerate(raw):
        h, w = arr.shape[:2]
        cx0, cy0, cx1, cy1 = max(x0 - m, 0), max(y0 - m, 0), min(x1 + m, w - 1), min(y1 + m, h - 1)
        im = Image.fromarray(arr[cy0:cy1 + 1, cx0:cx1 + 1])
        oh = int(round(im.height * out_w / im.width / 2.0)) * 2
        im = im.resize((out_w, oh), Image.LANCZOS)
        p = os.path.join(tmp, "%s_%03d.png" % (name, k))
        im.save(p, compress_level=1)
        paths.append(p)
    return paths


# --------------------------------------------------------------------------
# parts
# --------------------------------------------------------------------------
def split_down_faces(pd, nz=-0.7):
    """triangles whose outward normal points down (n_z < nz) and the rest, as two vtkPolyData"""
    from vtk.util.numpy_support import numpy_to_vtk, vtk_to_numpy
    tri = vtk.vtkTriangleFilter()
    tri.SetInputData(pd)
    tri.Update()
    t = tri.GetOutput()
    pts = vtk_to_numpy(t.GetPoints().GetData()).astype(float)
    cells = vtk_to_numpy(t.GetPolys().GetConnectivityArray()).reshape(-1, 3)
    a, b, c = pts[cells[:, 0]], pts[cells[:, 1]], pts[cells[:, 2]]
    n = np.cross(b - a, c - a)
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    down = n[:, 2] < nz

    def build(sel):
        out = vtk.vtkPolyData()
        vp = vtk.vtkPoints()
        vp.SetData(numpy_to_vtk(pts, deep=True))
        out.SetPoints(vp)
        cs = cells[sel].astype(np.int64)
        ca = vtk.vtkCellArray()
        offs = np.arange(0, 3 * len(cs) + 1, 3, dtype=np.int64)
        ca.SetData(numpy_to_vtk(offs, deep=True, array_type=vtk.VTK_ID_TYPE),
                   numpy_to_vtk(cs.ravel(), deep=True, array_type=vtk.VTK_ID_TYPE))
        out.SetPolys(ca)
        return out
    return build(down), build(~down)


class Model:
    def __init__(self, cad_dir, pcb_step, kicad_pcb):
        import flashka_housing as H
        self.p = H.P()
        self.cad_dir = cad_dir
        self.cad = R.Cad(cad_dir)
        t0 = time.time()
        if pcb_step and os.path.exists(pcb_step):
            self.pcb = R.PcbSet(pcb_step, kicad_pcb if kicad_pcb and os.path.exists(kicad_pcb) else None,
                                self.p, H.build_dummies(self.p))
            self.pcb_kind = "real PCB STEP model (%d parts)" % len(self.pcb.items)
        else:
            self.pcb = R.SimplePcb(self.cad)
            self.pcb_kind = "simplified stand-in PCB (no STEP found)"
        log("PCB: %s, %.1f s" % (self.pcb_kind, time.time() - t0))

    def part(self, name, offset=(0, 0, 0)):
        return self.cad.part(name, offset)

    def caps(self, dz=0.0, dzt=0.0, lit=False):
        """tube + three stainless caps in place.  lit: only the downward faces of the light-pipe tube (the
        visible ring ID 6.0 / OD 8.4 on the bottom face) glow cyan; the rest of the tube stays plain resin,
        so it does not shine through the USB-C port."""
        p, bt = self.p, self.p.btn_y
        if lit:
            ring, body = split_down_faces(self.cad.pd("FlashKa_tube"))
            tube = [R.glow(R.Part(ring, CYAN, 1.0, (0, 0, dzt), "FlashKa_tube_ring"), CYAN),
                    R.Part(body, R.COL["FlashKa_tube"], R.OPAC["FlashKa_tube"], (0, 0, dzt), "FlashKa_tube")]
        else:
            tube = [self.part("FlashKa_tube", (0, 0, dzt))]
        return tube + [self.part("FlashKa_cap_main", (p.X_main, bt, dz)),
                       self.part("FlashKa_cap_slide", (p.X_next, bt, dz)),
                       self.part("FlashKa_cap_slide", (p.X_prev, bt, dz))]

    def marks(self, *faces):
        """laser-marking layers (render.py's MarkQuad).  Drawn in the opaque pass: as translucent
        quads 0.03 mm above the face they hide the translucent resin windows behind them."""
        out = []
        for f in faces:
            path = os.path.join(self.cad_dir, "_mark_%s.png" % f)
            if os.path.exists(path):
                q = R.MarkQuad(f, path, self.p)
                q.actor.ForceOpaqueOn()
                out.append(q)
        return out

    def closed(self, lit=True, splitring=False):
        """the closed light with everything inside (seen through the windows and the USB-C port)"""
        names = ["FlashKa_tray", "FlashKa_lid", "FlashKa_rf_window", "FlashKa_antenna_spacer", "_ref_lidscrews",
                 "_ref_window", "_ref_led", "_ref_mcpcb", "_ref_laser", "FlashKa_spacer_ring",
                 "_ref_cell1", "_ref_cell2", "_ref_pad", "_ref_pad2"]
        if splitring:
            names.append("_ref_splitring")
        parts = [self.part(n) for n in names if self.cad.has(n)]
        return parts + self.caps(lit=lit) + self.pcb.parts() + self.marks("lid", "bottom", "minus_y", "plus_y")


# --------------------------------------------------------------------------
# 1. turntable
# --------------------------------------------------------------------------
def turntable(model, tmp, out=OUT_TURNTABLE, frames=60, delay_cs=7, out_w=800, ss=2.5):
    p = model.p
    parts = model.closed(lit=True)
    rig = Rig(parts, glow={"FlashKa_tube_ring"})
    centre = (0.0, 0.0, p.H / 2)

    def apply(theta):
        m = rot_x_about(theta, centre)
        for pt in parts:
            pt.actor.SetUserMatrix(m)

    theta0 = 205.0                                     # first frame: bottom face (caps, lit ring) towards the camera
    thetas = [theta0 + 360.0 * k / frames for k in range(frames)]
    direction, up = (-0.50, -0.80, 0.60), (0, 0, 1)
    fill = 0.90
    asp = fit_camera(rig, thetas[::3], apply, direction, up, view_angle=18.0, fill=fill)
    margin = 0.035
    Wf = int(round(out_w * ss / (fill * (1 + 2 * margin))))
    Hf = int(round(Wf * asp))
    rig.size(Wf, Hf)
    log("turntable: %d frames, render %d x %d, aspect %.3f" % (frames, Wf, Hf, asp))
    raw, box = [], None
    t0 = time.time()
    for k, th in enumerate(thetas):
        apply(th)
        img, g = rig.shot()
        img = bloom(img, g, radius=0.9 * ss * 2.2, strength=0.85)
        raw.append(img)
        box = union_box(box, content_box(img, (255, 255, 255)))
    log("  rendered in %.1f s" % (time.time() - t0))
    paths = save_frames(raw, tmp, "tt", box, out_w, margin)
    write_gif(paths, [delay_cs] * len(paths), out, tmp, dither="sierra2_4a")
    return paths


# --------------------------------------------------------------------------
# 2. exploded view, animated
# --------------------------------------------------------------------------
def ease(x):
    x = min(max(x, 0.0), 1.0)
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def explode_groups(model):
    """(static parts, [(label, parts, dz, t0, t1)]): the exploded view moves every group straight along Z by dz mm
    (+ up, - down) between the times t0 and t1 of the 0..1 explosion (staggered: the outer parts leave first).
    The Z offsets keep a gap of >= 4 mm between neighbours in the exploded state and a visible gap in the picture
    (camera about 31 degrees above the horizon).  Parts that overlap in X and Y never cross: the upper one leaves
    first and moves further (e.g. the module's antenna overhang, Z 10.0, lies 0.4 mm above the antenna spacer, top
    Z 9.6 under it, so the spacer moves less than the PCB).  The tube and the caps go down: the caps first and
    further, so the main cap leaves the tube downwards.  The head parts (window, LED board, laser) stay put."""
    p, cad = model.p, model.cad
    bt = p.btn_y
    static = ([cad.part(n) for n in ("FlashKa_tray", "FlashKa_spacer_ring", "_ref_window", "_ref_led", "_ref_mcpcb",
                                     "_ref_laser") if cad.has(n)] + model.marks("bottom", "minus_y", "plus_y"))
    caps = [cad.part("FlashKa_cap_main", (p.X_main, bt, 0)), cad.part("FlashKa_cap_slide", (p.X_next, bt, 0)),
            cad.part("FlashKa_cap_slide", (p.X_prev, bt, 0))]
    groups = [   # label, parts, dz, t0, t1      # Z assembled -> exploded (tray rim Z 13.9)
        ("4 x M1.6 lid screws", [cad.part("_ref_lidscrews")], 55.0, 0.00, 0.42),   # 12.0-16.0  -> 67.0-71.0
        ("lid", [cad.part("FlashKa_lid")] + model.marks("lid"), 46.0, 0.04, 0.48),  # 10.8-16.0  -> 56.8-62.0
        ("RF window insert", [cad.part("FlashKa_rf_window")], 34.0, 0.10, 0.54),    # 14.3-16.0  -> 48.3-50.0
        ("hold-down pads", [cad.part("_ref_pad"), cad.part("_ref_pad2")], 27.0, 0.16, 0.60),  # 10.0-13.2 -> 37.0-40.2
        ("PCB + module", model.pcb.parts(), 22.0, 0.22, 0.66),                      # 5.99-12.4  -> 28.0-34.4
        ("upper cell", [cad.part("_ref_cell2")], 27.0, 0.24, 0.68),                 # 7.65-13.65 -> 34.65-40.65
        ("antenna spacer", [cad.part("FlashKa_antenna_spacer")], 18.0, 0.26, 0.70),  # 0-14.15    -> 18.0-32.15
        ("lower cell", [cad.part("_ref_cell1")], 17.0, 0.30, 0.74),                 # 1.6-7.6    -> 18.6-24.6
        ("3 stainless caps", caps, -35.0, 0.38, 0.86),                              # -0.1-6.9   -> -35.1--28.1
        ("light-pipe tube", [cad.part("FlashKa_tube")], -21.0, 0.46, 0.94),         # 0-8.2      -> -21.0--12.8
    ]
    return static, groups


EXPLODED_VIEW = (-0.45, -1.0, 0.66)          # from the front, the control side (-Y, USB-C) and above


def exploded(model, tmp, out=OUT_EXPLODED, steps=30, out_w=800, ss=2.5):
    """The assembly with the real PCB model separates along Z (explode_groups) and comes back."""
    static, groups = explode_groups(model)
    parts = static + [pt for g in groups for pt in g[1]]
    rig = Rig(parts)
    base = {id(pt): np.array(pt.actor.GetPosition(), float) for pt in parts}

    def apply(u):
        for _, gparts, dz, s0, s1 in groups:
            f = ease((u - s0) / (s1 - s0))
            for pt in gparts:
                pt.actor.SetPosition(*(base[id(pt)] + np.array([0.0, 0.0, dz * f])))

    us = [k / (steps - 1) for k in range(steps)]
    fill, margin = 0.92, 0.03
    asp = fit_camera(rig, [0.0, 0.5, 0.75, 1.0], apply, EXPLODED_VIEW, view_angle=20.0, fill=fill)
    Wf = int(round(out_w * ss / (fill * (1 + 2 * margin))))
    Hf = int(round(Wf * asp))
    rig.size(Wf, Hf)
    log("exploded: %d steps, render %d x %d, aspect %.3f" % (steps, Wf, Hf, asp))
    raw, box = [], None
    t0 = time.time()
    for u in us:
        apply(u)
        img, _ = rig.shot(glow=False)
        raw.append(img)
        box = union_box(box, content_box(img, (255, 255, 255)))
    log("  rendered in %.1f s" % (time.time() - t0))
    paths = save_frames(raw, tmp, "ex", box, out_w, margin)
    # assembled (hold 1.2 s) -> explode (60 ms frames) -> exploded (hold 2.0 s) -> back (the same frames
    # reversed, 50 ms frames) -> loop
    seq = paths + paths[-2:0:-1]
    delays = [6] * len(paths) + [5] * (len(paths) - 2)
    delays[0] = 120
    delays[len(paths) - 1] = 200
    write_gif(seq, delays, out, tmp, dither="sierra2_4a")
    return paths


# --------------------------------------------------------------------------
# 3. banner pictures for the LuxLibre README and the social preview
# --------------------------------------------------------------------------
FONTS = {   # TeX Gyre Heros (a Helvetica-style face, GUST licence); DejaVu Sans as the fallback
    "bold": ["/usr/share/texmf/fonts/opentype/public/tex-gyre/texgyreheros-bold.otf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "regular": ["/usr/share/texmf/fonts/opentype/public/tex-gyre/texgyreheros-regular.otf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
}
THEMES = {
    # card colours of GitHub's light / dark theme (primer "subtle canvas", border, text, muted text);
    # the dark card sits on GitHub's #0d1117 page, the light card on #ffffff
    "light": {"bg": (246, 248, 250), "border": (208, 215, 222), "grid": (226, 231, 236),
              "text": (31, 35, 40), "muted": (89, 99, 110), "accent": (9, 150, 168), "shadow": 0.16},
    "dark": {"bg": (22, 27, 34), "border": (48, 54, 61), "grid": (35, 42, 51),
             "text": (230, 237, 243), "muted": (145, 152, 161), "accent": (77, 222, 240), "shadow": 0.45},
}


def font(kind, size):
    for path in FONTS[kind]:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


class Cutout:
    """one camera view of the closed light as a premultiplied RGB + alpha pair (rendered on black and on
    white), plus the glow mask of the lit ring"""

    def __init__(self, model, direction, up, view_angle, px_w, ss=2.5, splitring=True, rim=False):
        parts = model.closed(lit=True, splitring=splitring)
        lights = []
        if rim:                                    # extra light from behind for the dark background
            lt = vtk.vtkLight()
            lt.SetLightTypeToSceneLight()
            lt.SetPosition(*(np.array([47.0, 0, 8]) - unit(direction) * 300 + np.array([0, 0, 250])))
            lt.SetFocalPoint(47.0, 0, 8)
            lt.SetIntensity(0.6)
            lights.append(lt)
        rig = Rig(parts, glow={"FlashKa_tube_ring"}, extra_lights=lights)
        fill, margin = 0.92, 0.02
        asp = fit_camera(rig, [0], lambda s: None, direction, up, view_angle=view_angle, fill=fill)
        Wf = int(round(px_w * ss / (fill * (1 + 2 * margin))))
        Hf = int(round(Wf * asp))
        rig.size(Wf, Hf)
        rig.ren.SetBackground(0, 0, 0)
        blk, g = rig.shot(glow=True)
        rig.ren.SetBackground(1, 1, 1)
        wht, _ = rig.shot(glow=False)
        box = content_box(wht, (255, 255, 255))
        x0, y0, x1, y1 = box
        m = int(round(margin * (x1 - x0)))
        x0, y0, x1, y1 = max(x0 - m, 0), max(y0 - m, 0), min(x1 + m, Wf - 1), min(y1 + m, Hf - 1)
        blk, wht, g = (im[y0:y1 + 1, x0:x1 + 1] for im in (blk, wht, g))
        a = 1.0 - (wht.astype(np.float32) - blk.astype(np.float32)).mean(axis=2) / 255.0
        a = np.clip(a, 0, 1)
        self.pre = blk.astype(np.float32) / 255.0                  # colour x alpha (rendered on black)
        self.alpha = a
        self.glow = g

    def scaled(self, w):
        """(premultiplied RGB, alpha, glow) resized to w px wide, float arrays 0..1"""
        h = int(round(self.alpha.shape[0] * w / self.alpha.shape[1]))

        def rs(arr, mode):
            im = Image.fromarray((np.clip(arr, 0, 1) * 255 + 0.5).astype(np.uint8), mode)
            return np.asarray(im.resize((w, h), Image.LANCZOS), np.float32) / 255.0
        return rs(self.pre, "RGB"), rs(self.alpha, "L"), rs(self.glow.astype(np.float32) / 255.0, "RGB")


def paste_cutout(canvas, cut, x, y, w, shadow=0.0, glow_strength=0.85, glow_radius=3.0):
    """composite the cutout (w px wide, top-left at x, y) onto the float RGB canvas, with an optional soft
    drop shadow below it and the bloom of the lit ring on top"""
    pre, a, g = cut.scaled(w)
    h = a.shape[0]
    H, W = canvas.shape[:2]
    if shadow > 0:
        sh = Image.fromarray((a * 255).astype(np.uint8), "L")
        pad = 60
        big = Image.new("L", (w + 2 * pad, h + 2 * pad), 0)
        big.paste(sh, (pad, pad))
        big = big.filter(ImageFilter.GaussianBlur(16))
        s = np.asarray(big, np.float32) / 255.0 * shadow
        ox, oy = x - pad + 6, y - pad + 16
        _blend_region(canvas, ox, oy, 0.0, s)
    region = canvas[y:y + h, x:x + w]
    region[:] = pre + (1 - a[..., None]) * region
    if glow_strength > 0:
        gi = Image.fromarray((g * 255).astype(np.uint8), "RGB")
        g1 = np.asarray(gi.filter(ImageFilter.GaussianBlur(glow_radius)), np.float32) / 255
        g2 = np.asarray(gi.filter(ImageFilter.GaussianBlur(glow_radius * 3)), np.float32) / 255
        gg = np.clip((0.75 * g1 + 0.55 * g2) * glow_strength, 0, 1)
        region[:] = 1 - (1 - region) * (1 - gg)
    return x, y, w, h


def _blend_region(canvas, ox, oy, col, alpha):
    """canvas = canvas * (1 - alpha) + col * alpha in the window at ox, oy (clipped to the canvas)"""
    H, W = canvas.shape[:2]
    h, w = alpha.shape[:2]
    x0, y0, x1, y1 = max(ox, 0), max(oy, 0), min(ox + w, W), min(oy + h, H)
    if x1 <= x0 or y1 <= y0:
        return
    a = alpha[y0 - oy:y1 - oy, x0 - ox:x1 - ox][..., None]
    c = col[y0 - oy:y1 - oy, x0 - ox:x1 - ox] if np.ndim(col) == 3 else col
    canvas[y0:y1, x0:x1] = canvas[y0:y1, x0:x1] * (1 - a) + c * a


def grid_layer(W, H, step, x_from):
    """alpha of a faint square grid: fades in from x_from towards the right and out at the edges"""
    g = np.zeros((H, W), np.float32)
    g[:, ::step] = 1.0
    g[::step, :] = 1.0
    xs = np.arange(W, dtype=np.float32)
    ys = np.arange(H, dtype=np.float32)
    fade = np.clip((xs - x_from) / (0.35 * W), 0, 1) ** 1.5
    edge_x = np.clip(np.minimum(xs, W - 1 - xs) / 48.0, 0, 1)
    edge_y = np.clip(np.minimum(ys, H - 1 - ys) / 48.0, 0, 1)
    return g * (fade * edge_x)[None, :] * edge_y[:, None]


def compose(kind, theme_name, cuts, size, out):
    """kind: 'banner' (1600 x 520) or 'social' (1280 x 640)"""
    th = THEMES[theme_name]
    W, H = size
    canvas = np.empty((H, W, 3), np.float32)
    canvas[:] = np.array(th["bg"], np.float32) / 255.0
    # faint 32 px grid behind the render (right side)
    ga = grid_layer(W, H, 32, int(W * 0.40))
    gcol = np.array(th["grid"], np.float32) / 255.0
    canvas[:] = canvas * (1 - ga[..., None]) + gcol * ga[..., None]
    hero = cuts[theme_name]
    # render box (x0, y0, x1, y1): the hero is fitted into it, keeping its aspect
    bx0, by0, bx1, by1 = (690, 24, W - 40, H - 50) if kind == "banner" else (566, 150, W - 46, H - 52)
    asp = hero.alpha.shape[0] / hero.alpha.shape[1]
    rw = int(min(bx1 - bx0, (by1 - by0) / asp))
    rh = int(round(rw * asp))
    rx, ry = bx0 + (bx1 - bx0 - rw) // 2, by0 + (by1 - by0 - rh) // 2
    paste_cutout(canvas, hero, rx, ry, rw, shadow=th["shadow"])
    img = Image.fromarray((np.clip(canvas, 0, 1) * 255 + 0.5).astype(np.uint8), "RGB")
    dr = ImageDraw.Draw(img)
    if kind == "banner":
        tx, ty = 84, 150
        f_big, f_sub, f_note = font("bold", 112), font("regular", 31), font("regular", 21)
        sub = ["Open-source firmware, design rules", "and reference designs for flashlights"]
    else:
        tx, ty = 84, 118
        f_big, f_sub, f_note = font("bold", 112), font("regular", 32), font("regular", 21)
        sub = ["Open-source firmware, design rules", "and reference designs for flashlights"]
    dr.text((tx - 4, ty), "LuxLibre", font=f_big, fill=th["text"])
    bb = dr.textbbox((tx - 4, ty), "LuxLibre", font=f_big)
    yy = bb[3] + 30
    dr.rectangle([tx, yy, tx + 64, yy + 5], fill=th["accent"])
    yy += 30
    for ln in sub:
        dr.text((tx, yy), ln, font=f_sub, fill=th["muted"])
        yy += int(f_sub.size * 1.42)
    note = "FlashKa Keychain v0.6 - render"
    nb = dr.textbbox((0, 0), note, font=f_note)
    nx, ny = rx + rw - (nb[2] - nb[0]) - 24, min(ry + rh + 2, H - 30 - (nb[3] - nb[1]))
    dr.rounded_rectangle([nx + nb[0] - 8, ny + nb[1] - 5, nx + nb[2] + 8, ny + nb[3] + 6], radius=5, fill=th["bg"])
    dr.text((nx, ny), note, font=f_note, fill=th["muted"])
    # rounded corners + 1 px border for the banner (transparent outside the card)
    if kind == "banner":
        rad = 18
        mask = Image.new("L", (W * 4, H * 4), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, W * 4 - 1, H * 4 - 1], radius=rad * 4, fill=255)
        mask = mask.resize((W, H), Image.LANCZOS)
        border = Image.new("L", (W * 4, H * 4), 0)
        ImageDraw.Draw(border).rounded_rectangle([0, 0, W * 4 - 1, H * 4 - 1], radius=rad * 4, outline=255, width=4)
        border = border.resize((W, H), Image.LANCZOS)
        bcol = Image.new("RGB", (W, H), th["border"])
        img = Image.composite(bcol, img, border)
        img = img.convert("RGBA")
        img.putalpha(mask)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    img.save(out, optimize=True)
    log("wrote %s  %s  %.0f kB" % (out, img.size, os.path.getsize(out) / 1e3))
    return out


def banners(model, tmp, out_light=OUT_BANNER_LIGHT, out_dark=OUT_BANNER_DARK, out_social=OUT_SOCIAL):
    # seen from below the +Y side, head up and to the right: the three caps and the lit ring, the S2 slot
    # with SAFE / ARM (upright), the window and laser at the head, the split ring hanging from the tail
    view = dict(direction=(-0.45, 0.75, -1.0), up=(0, 0, 1), view_angle=18.0, px_w=1000)
    cuts = {"light": Cutout(model, **view), "dark": Cutout(model, rim=True, **view)}
    compose("banner", "light", cuts, (1600, 520), out_light)
    compose("banner", "dark", cuts, (1600, 520), out_dark)
    compose("social", "light", cuts, (1280, 640), out_social)


# --------------------------------------------------------------------------
# 4. still renders with the real PCB (render.py, unchanged)
# --------------------------------------------------------------------------
STILLS = ("housing_open_top.png", "housing_open_iso.png", "housing_exploded.png")


def stills(cad_dir, pcb_step, kicad_pcb, tmp, out_dir=None):
    """render.py draws the open top, open iso and exploded pictures with the real PCB STEP into renders/; they are
    copied to assets/v06/.  With out_dir (previews) render.py writes into the frame folder and the copies go to
    out_dir; renders/ and assets/v06/ are not touched."""
    rdir = tmp if out_dir else os.path.join(V6, "renders")
    adir = out_dir or os.path.join(V6, "assets", "v06")
    cmd = [sys.executable, os.path.join(HERE, "render.py"), cad_dir, rdir, "--pcb-step", pcb_step,
           "--kicad-pcb", kicad_pcb, "--only", "open_top,open_iso,exploded"]
    subprocess.run(cmd, check=True)
    os.makedirs(adir, exist_ok=True)
    for n in STILLS:
        shutil.copyfile(os.path.join(rdir, n), os.path.join(adir, n))
    log("copied %s to %s" % (", ".join(STILLS), adir))


# --------------------------------------------------------------------------
STAGES = ("turntable", "exploded", "banner", "stills")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default=",".join(STAGES))
    ap.add_argument("--tmp", default=None)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--cad", default=os.path.join(V6, "cad"))
    ap.add_argument("--pcb-step", default=os.path.join(V6, "cad", "FlashKa_main_pcb.step"))
    ap.add_argument("--kicad-pcb", default=os.path.join(V6, "kicad", "FlashKa_main", "FlashKa_main.kicad_pcb"))
    ap.add_argument("--frames", type=int, default=60, help="turntable frames (36 to 60)")
    ap.add_argument("--out-dir", default=None)
    a = ap.parse_args()
    if not 36 <= a.frames <= 60:
        ap.error("--frames must be 36 to 60")
    od = a.out_dir
    outs = {k: (os.path.join(od, os.path.basename(v)) if od else v) for k, v in
            (("tt", OUT_TURNTABLE), ("ex", OUT_EXPLODED), ("bl", OUT_BANNER_LIGHT), ("bd", OUT_BANNER_DARK),
             ("so", OUT_SOCIAL))}
    stages = [s.strip() for s in a.only.split(",") if s.strip()]
    bad = [s for s in stages if s not in STAGES]
    if bad:
        ap.error("unknown stage(s) %s; choose from %s" % (", ".join(bad), ",".join(STAGES)))
    tmp = a.tmp or tempfile.mkdtemp(prefix="flashka_anim_")
    os.makedirs(tmp, exist_ok=True)
    made = []

    def sub(name):
        d = os.path.join(tmp, name)
        os.makedirs(d, exist_ok=True)
        made.append(d)
        return d
    try:
        if {"turntable", "exploded", "banner"} & set(stages):
            model = Model(a.cad, a.pcb_step, a.kicad_pcb)
            if "turntable" in stages:
                turntable(model, sub("turntable"), outs["tt"], frames=a.frames)
            if "exploded" in stages:
                exploded(model, sub("exploded"), outs["ex"])
            if "banner" in stages:
                banners(model, sub("banner"), outs["bl"], outs["bd"], outs["so"])
        if "stills" in stages:
            stills(a.cad, a.pcb_step, a.kicad_pcb, sub("stills"), od)
    finally:
        if not a.keep:              # remove only what this run made (a given --tmp folder itself stays)
            for d in made:
                shutil.rmtree(d, ignore_errors=True)
            if not a.tmp:
                shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
