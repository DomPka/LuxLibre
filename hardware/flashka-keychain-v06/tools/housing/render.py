#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Offscreen VTK renders of the v0.6 housing (run under xvfb-run).

usage:  xvfb-run -a python3 render.py <cad_dir> <out_dir> [--pcb-step FILE] [--kicad-pcb FILE]
                                      [--only name1,name2]

  <cad_dir>    folder written by flashka_housing.py (FlashKa_*.stl, _ref_*.stl)
  <out_dir>    PNG folder (1600 px wide each)
  --pcb-step   KiCad STEP export of the main PCB (frame: housing X, Y; Z = 0 on the
               PCB bottom face - the script lifts it by P.Z_pcb_bot).  Without it the
               simplified stand-in PCB (_ref_pcb.stl + parts) is drawn instead.
  --kicad-pcb  .kicad_pcb of the same board (positions of the L1 / LED3 stand-ins)
  --only       comma separated subset of the picture names below

Marking textures: <cad_dir>/_mark_<face>.png (written by flashka_marking.py --tex-dir <cad_dir>).

Pictures (1600 px wide, tight crop, white background):
  housing_closed_bottom.png        from below: three stainless caps, the ring lit cyan, bottom marking
  housing_bottom_flat.png          straight from below
  housing_closed_lid.png           straight from above: laser label, seams, rivets
  housing_closed_control_side.png  -Y side with the USB-C port
  housing_closed_rear.png          +Y side with the S2 slot and SAFE / ARM
  housing_front.png                front: window, LED, laser aperture
  housing_open_top.png / _open_iso.png / housing_exploded.png / housing_print_kit.png
"""
import argparse
import os
import sys

import numpy as np
import vtk
from PIL import Image, ImageDraw, ImageFont
from vtk.util.numpy_support import numpy_to_vtk, vtk_to_numpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

OUT_W = 1600                      # final picture width, px
SS = 2.5                          # supersampling of the final picture
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

ANOD = (0.22, 0.23, 0.26)
RESIN = (0.96, 0.93, 0.85)        # printed 8001 translucent resin: pale warm white
COL = {
    "FlashKa_tray": ANOD, "FlashKa_lid": (0.29, 0.30, 0.33),
    "FlashKa_cap_main": (0.68, 0.70, 0.74), "FlashKa_cap_slide": (0.68, 0.70, 0.74),
    "FlashKa_tube": RESIN, "_ref_pad": (0.55, 0.56, 0.58), "_ref_pad2": (0.80, 0.52, 0.45),
    "_ref_sw1": (0.15, 0.15, 0.15), "_ref_sw2": (0.15, 0.15, 0.15), "_ref_sw3": (0.15, 0.15, 0.15),
    "_ref_sw1_act": (0.9, 0.9, 0.9), "_ref_sw2_act": (0.9, 0.9, 0.9), "_ref_sw3_act": (0.9, 0.9, 0.9),
    "_ref_led3": (0.95, 0.95, 0.85), "_ref_led4": (0.95, 0.95, 0.85),
    "FlashKa_spacer_ring": RESIN,
    "FlashKa_antenna_spacer": RESIN, "FlashKa_laser_sleeve": RESIN,
    "FlashKa_rf_window": RESIN, "FlashKa_print_kit": RESIN,
    "_ref_pcb": (0.08, 0.42, 0.20), "_ref_module": (0.07, 0.36, 0.17),
    "_ref_module_can": (0.62, 0.64, 0.68), "_ref_cell1": (0.88, 0.70, 0.30),
    "_ref_cell2": (0.88, 0.70, 0.30), "_ref_window": (0.70, 0.86, 1.00),
    "_ref_mcpcb": (0.80, 0.50, 0.22), "_ref_led": (1.00, 0.98, 0.80),
    "_ref_laser": (0.78, 0.62, 0.32), "_ref_usb": (0.80, 0.80, 0.82),
    "_ref_s2": (0.15, 0.15, 0.15), "_ref_s2_knob": (0.9, 0.9, 0.9),
    "_ref_L1": (0.25, 0.25, 0.25), "_ref_splitring": (0.78, 0.79, 0.81),
    "_ref_lidscrews": (0.62, 0.64, 0.68),
}
OPAC = {"_ref_window": 0.40, "FlashKa_rf_window": 0.78, "FlashKa_tube": 0.88, "FlashKa_antenna_spacer": 0.9,
        "FlashKa_spacer_ring": 0.9, "FlashKa_print_kit": 0.92, "FlashKa_laser_sleeve": 0.9}


# --------------------------------------------------------------------------
# geometry -> actors
# --------------------------------------------------------------------------
def polydata_from_stl(path):
    r = vtk.vtkSTLReader()
    r.SetFileName(path)
    r.Update()
    return r.GetOutput()


def polydata_from_shape(shape, tol=0.02, ang=0.25):
    """cadquery Shape -> vtkPolyData (triangles)"""
    verts, tris = shape.tessellate(tol, ang)
    pts = np.array([[v.x, v.y, v.z] for v in verts], dtype=float).reshape(-1, 3)
    cells = np.array(tris, dtype=np.int64).reshape(-1, 3)
    pd = vtk.vtkPolyData()
    vp = vtk.vtkPoints()
    vp.SetData(numpy_to_vtk(pts, deep=True))
    pd.SetPoints(vp)
    ca = vtk.vtkCellArray()
    offs = np.arange(0, 3 * len(cells) + 1, 3, dtype=np.int64)
    ca.SetData(numpy_to_vtk(offs, deep=True, array_type=vtk.VTK_ID_TYPE),
               numpy_to_vtk(cells.ravel(), deep=True, array_type=vtk.VTK_ID_TYPE))
    pd.SetPolys(ca)
    return pd


class Part:
    def __init__(self, pd, color, opacity=1.0, offset=(0, 0, 0), name="", shininess=0.35):
        n = vtk.vtkPolyDataNormals()
        n.SetInputData(pd)
        n.SetFeatureAngle(35)
        n.SplittingOn()
        n.Update()
        m = vtk.vtkPolyDataMapper()
        m.SetInputConnection(n.GetOutputPort())
        a = vtk.vtkActor()
        a.SetMapper(m)
        pr = a.GetProperty()
        pr.SetColor(*color)
        pr.SetOpacity(opacity)
        pr.SetSpecular(shininess)
        pr.SetSpecularPower(30)
        pr.SetDiffuse(0.85)
        pr.SetAmbient(0.26)
        a.SetPosition(*offset)
        self.actor, self.name = a, name


class MarkQuad:
    """laser-marking texture (RGBA PNG from flashka_marking.py) on a flat face, 0.03 mm proud of it.
    face: lid | bottom | minus_y | plus_y"""

    def __init__(self, face, path, p, lit=0.9):
        L, W, H = p.L, p.W, p.H
        e = 0.03
        if face == "lid":
            pts = [(0, -W / 2, H + e), (L, -W / 2, H + e), (L, W / 2, H + e), (0, W / 2, H + e)]
            st = [(0, 0), (1, 0), (1, 1), (0, 1)]
        elif face == "bottom":
            pts = [(0, -W / 2, -e), (L, -W / 2, -e), (L, W / 2, -e), (0, W / 2, -e)]
            st = [(0, 1), (1, 1), (1, 0), (0, 0)]
        elif face == "minus_y":
            pts = [(0, -W / 2 - e, 0), (L, -W / 2 - e, 0), (L, -W / 2 - e, H), (0, -W / 2 - e, H)]
            st = [(0, 0), (1, 0), (1, 1), (0, 1)]
        else:
            pts = [(0, W / 2 + e, 0), (L, W / 2 + e, 0), (L, W / 2 + e, H), (0, W / 2 + e, H)]
            st = [(1, 0), (0, 0), (0, 1), (1, 1)]
        vp = vtk.vtkPoints()
        tc = vtk.vtkFloatArray()
        tc.SetNumberOfComponents(2)
        for q, t in zip(pts, st):
            vp.InsertNextPoint(*q)
            tc.InsertNextTuple2(*t)
        ca = vtk.vtkCellArray()
        for tri in ((0, 1, 2), (0, 2, 3)):
            ca.InsertNextCell(3, tri)
        pd = vtk.vtkPolyData()
        pd.SetPoints(vp)
        pd.SetPolys(ca)
        pd.GetPointData().SetTCoords(tc)
        rd = vtk.vtkPNGReader()
        rd.SetFileName(path)
        rd.Update()
        tex = vtk.vtkTexture()
        tex.SetInputConnection(rd.GetOutputPort())
        tex.InterpolateOn()
        tex.MipmapOn()
        m = vtk.vtkPolyDataMapper()
        m.SetInputData(pd)
        a = vtk.vtkActor()
        a.SetMapper(m)
        a.SetTexture(tex)
        pr = a.GetProperty()
        pr.SetAmbient(lit)
        pr.SetDiffuse(1.0 - lit)
        pr.SetSpecular(0.0)
        self.actor, self.name = a, "mark_" + face


class Cad:
    """lazy access to the STL files of one run folder"""

    def __init__(self, folder):
        self.folder = folder
        self._pd = {}

    def has(self, name):
        return os.path.exists(os.path.join(self.folder, name + ".stl"))

    def pd(self, name):
        if name not in self._pd:
            self._pd[name] = polydata_from_stl(os.path.join(self.folder, name + ".stl"))
        return self._pd[name]

    def part(self, name, offset=(0, 0, 0), color=None, opacity=None):
        return Part(self.pd(name), color or COL.get(name, (0.5, 0.5, 0.5)),
                    OPAC.get(name, 1.0) if opacity is None else opacity, offset, name)


# --------------------------------------------------------------------------
# PCB parts (STEP) -> coloured parts
# --------------------------------------------------------------------------
def pcb_colour(name, model):
    n = (name or "").upper()
    m = (model or "")
    if name == "PCB":
        return (0.07, 0.40, 0.19)
    if n in ("SW1", "SW2", "SW3", "S2"):
        return (0.78, 0.79, 0.82)
    if n.startswith("J"):
        return (0.80, 0.80, 0.82)
    if m.startswith("C_") or (n.startswith("C") and n[1:2].isdigit()):
        return (0.72, 0.56, 0.34)
    if n.startswith("L"):
        return (0.30, 0.30, 0.32)
    if n.startswith("LED"):
        return (0.95, 0.95, 0.85)
    return (0.11, 0.11, 0.12)        # resistors, ICs, FETs, diodes


class PcbSet:
    """tessellated PCB assembly (STEP + stand-ins) built once, instanced per picture"""

    def __init__(self, step, kicad, p, dm):
        import fit_pcb
        items, _ = fit_pcb.pcb_items(step, p, dm, kicad, verbose=False)
        self.items = []
        for it in items:
            if it["name"] == "U4" and it["kind"] == "standin":
                self.items.append(("U4a", polydata_from_shape(dm["module"].val()), COL["_ref_module"]))
                self.items.append(("U4b", polydata_from_shape(dm["module_can"].val()), COL["_ref_module_can"]))
                continue
            col = (0.80, 0.80, 0.83) if it["name"] == "J1" else pcb_colour(it["name"], it["model"])
            self.items.append((it["name"], polydata_from_shape(it["solid"], 0.01, 0.3), col))

    def parts(self, offset=(0, 0, 0)):
        return [Part(pd, col, 1.0, offset, nm) for nm, pd, col in self.items]


class SimplePcb:
    def __init__(self, cad):
        self.cad = cad

    def parts(self, offset=(0, 0, 0)):
        names = ["_ref_pcb", "_ref_module", "_ref_module_can", "_ref_usb", "_ref_sw1", "_ref_sw1_act",
                 "_ref_sw2", "_ref_sw2_act", "_ref_sw3", "_ref_sw3_act", "_ref_led3", "_ref_led4",
                 "_ref_s2", "_ref_s2_knob", "_ref_L1"]
        return [self.cad.part(n, offset) for n in names if self.cad.has(n)]


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------
def make_renderer(parts):
    ren = vtk.vtkRenderer()
    ren.SetBackground(1, 1, 1)
    ren.AutomaticLightCreationOff()
    for pt in parts:
        ren.AddActor(pt.actor)
    key = vtk.vtkLight()
    key.SetLightTypeToCameraLight()
    key.SetPosition(0.5, 0.7, 1.0)
    key.SetIntensity(0.95)
    ren.AddLight(key)
    fill = vtk.vtkLight()
    fill.SetLightTypeToCameraLight()
    fill.SetPosition(-1.0, -0.2, 0.6)
    fill.SetIntensity(0.55)
    ren.AddLight(fill)
    rim = vtk.vtkLight()
    rim.SetLightTypeToSceneLight()
    rim.SetPosition(-250, 300, 350)
    rim.SetFocalPoint(50, 0, 0)
    rim.SetIntensity(0.35)
    ren.AddLight(rim)
    return ren


def _grab(win):
    f = vtk.vtkWindowToImageFilter()
    f.SetInput(win)
    f.ReadFrontBufferOff()
    f.SetInputBufferTypeToRGB()
    f.Update()
    img = f.GetOutput()
    w, h, _ = img.GetDimensions()
    return vtk_to_numpy(img.GetPointData().GetScalars()).reshape(h, w, 3)[::-1].copy()


def _content_box(arr, thr=10):
    diff = (255 - arr.astype(np.int16)).max(axis=2) > thr
    ys, xs = np.where(diff)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def shoot(parts, fname, out_dir, direction, up=(0, 0, 1), focal=None, fill=0.90, ratio=0.62,
          view_angle=20.0, labels=None, margin=0.03):
    """Render `parts` seen from focal + direction, fit the content to the frame, crop it
    and write a PNG OUT_W px wide.
    labels: [(text, (x, y, z), side)] - callouts in a column left ('L') or right ('R') of the
    picture, with a leader line to the world point (side None: the nearer picture side)."""
    ren = make_renderer(parts)
    win = vtk.vtkRenderWindow()
    win.SetOffScreenRendering(1)
    win.AddRenderer(ren)
    win.SetAlphaBitPlanes(1)
    win.SetMultiSamples(0)
    ren.SetUseDepthPeeling(1)
    ren.SetMaximumNumberOfPeels(12)
    ren.SetOcclusionRatio(0.0)
    cam = ren.GetActiveCamera()
    b = [0.0] * 6
    ren.ComputeVisiblePropBounds(b)
    if focal is None:
        focal = ((b[0] + b[1]) / 2, (b[2] + b[3]) / 2, (b[4] + b[5]) / 2)
    d = np.array(direction, float)
    d /= np.linalg.norm(d)
    upv0 = np.array(up, float)
    cam.SetViewAngle(view_angle)
    cam.SetViewUp(*up)
    cam.SetFocalPoint(*focal)
    cam.SetPosition(*(np.array(focal) + d * 100))
    ren.ResetCamera(b)
    cam.SetFocalPoint(*focal)
    cam.SetPosition(*(np.array(focal) + d * cam.GetDistance()))
    W0 = 900
    win.SetSize(W0, int(W0 * ratio))
    ren.ResetCameraClippingRange()
    win.Render()
    # fit loop: zoom / pan until the content fills `fill` of the frame (never touching the border)
    for it in range(10):
        arr = _grab(win)
        H0, W1 = arr.shape[:2]
        bb = _content_box(arr)
        if bb is None:
            break
        x0, y0, x1, y1 = bb
        touching = x0 <= 1 or y0 <= 1 or x1 >= W1 - 2 or y1 >= H0 - 2
        s = min(fill * W1 / max(x1 - x0 + 1, 1), fill * H0 / max(y1 - y0 + 1, 1))
        cx, cy = (x0 + x1) / 2, (H0 - 1 - (y0 + y1) / 2)
        dxp, dyp = cx - W1 / 2, cy - H0 / 2
        if not touching and abs(s - 1) < 0.015 and abs(dxp) < 0.01 * W1 and abs(dyp) < 0.01 * H0:
            break
        dist = cam.GetDistance()
        wpp = 2 * dist * np.tan(np.radians(cam.GetViewAngle() / 2)) / H0
        right = np.cross(-d, upv0)
        right /= np.linalg.norm(right)
        upv = np.cross(right, -d)
        shift = right * dxp * wpp + upv * dyp * wpp
        cam.SetFocalPoint(*(np.array(cam.GetFocalPoint()) + shift))
        cam.SetPosition(*(np.array(cam.GetPosition()) + shift))
        cam.Zoom(s if not touching else min(s, 0.9))
        ren.ResetCameraClippingRange()
        win.Render()
    # final render, supersampled
    W2 = int(OUT_W * SS)
    H2 = int(round(W2 * ratio))
    win.SetSize(W2, H2)
    ren.ResetCameraClippingRange()
    win.Render()
    arr = _grab(win)
    x0, y0, x1, y1 = _content_box(arr)
    m = int(margin * max(x1 - x0, y1 - y0))
    cx0, cy0 = max(x0 - m, 0), max(y0 - m, 0)
    cx1, cy1 = min(x1 + m, arr.shape[1] - 1), min(y1 + m, arr.shape[0] - 1)
    model = Image.fromarray(arr[cy0:cy1 + 1, cx0:cx1 + 1])
    anchors = []
    for text, xyz, side in (labels or []):
        ren.SetWorldPoint(float(xyz[0]), float(xyz[1]), float(xyz[2]), 1.0)
        ren.WorldToDisplay()
        px, py, _ = ren.GetDisplayPoint()
        anchors.append((text, px - cx0, (H2 - 1 - py) - cy0, side))
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, fname)
    if not anchors:
        im = model.resize((OUT_W, int(round(model.height * OUT_W / model.width))), Image.LANCZOS)
    else:
        im = _compose_labels(model, anchors)
    im.save(path)
    print("wrote", path, im.size, flush=True)
    return path


def _compose_labels(model, anchors, fs=26, pad=26, gap=10):
    """model image + callouts -> OUT_W wide picture (drawn at 2x, then reduced).
    side 'L' / 'R': text columns left / right of the picture; 'T' / 'B': text rows above / below."""
    K = 2
    font = ImageFont.truetype(FONT, fs * K)
    tmp = ImageDraw.Draw(Image.new("RGB", (10, 10)))

    def tw(t):
        return tmp.textlength(t, font=font) / K

    wm = model.width
    items = []
    for text, ax_, ay_, side in anchors:
        if side is None:
            side = "L" if ax_ < wm / 2 else "R"
        lines = text.split("\n")
        items.append({"lines": lines, "ax": ax_, "ay": ay_, "side": side,
                      "w": max(tw(t) for t in lines), "h": fs * 1.2 * len(lines)})

    def colw(sd):
        sel = [i["w"] for i in items if i["side"] == sd]
        return max(sel) + pad + 14 if sel else 0
    Lw, Rw = colw("L"), colw("R")
    s = (OUT_W - Lw - Rw) / wm
    mh = int(round(model.height * s))
    for side in ("L", "R"):                       # text columns: vertical positions (model top = 0)
        y = None
        for i in sorted([i for i in items if i["side"] == side], key=lambda i: i["ay"]):
            t = i["ay"] * s - i["h"] / 2
            if y is not None:
                t = max(t, y + gap)
            i["ty"] = t
            y = t + i["h"]
    for side in ("T", "B"):                       # text rows: horizontal positions, stacked rows
        rows = []
        for i in sorted([i for i in items if i["side"] == side], key=lambda i: i["ax"]):
            xc = Lw + i["ax"] * s
            x0 = min(max(xc - i["w"] / 2, 6), OUT_W - 6 - i["w"])
            for r, occ in enumerate(rows):
                if all(x0 > q1 + 16 or x0 + i["w"] < q0 - 16 for q0, q1 in occ):
                    occ.append((x0, x0 + i["w"]))
                    i["row"] = r
                    break
            else:
                rows.append([(x0, x0 + i["w"])])
                i["row"] = len(rows) - 1
            i["tx"] = x0
        for i in items:
            if i["side"] == side:
                rh = fs * 1.2 * 2 + 6
                i["ty"] = (-(i["row"] + 1) * rh - 4 if side == "T" else mh + 8 + i["row"] * rh)
    top = min([0] + [i["ty"] for i in items]) - 8
    bot = max([mh] + [i["ty"] + i["h"] for i in items]) + 8
    H = int(round(bot - top))
    canvas = Image.new("RGB", (OUT_W * K, H * K), (255, 255, 255))
    canvas.paste(model.resize((int(round((OUT_W - Lw - Rw) * K)), int(round(mh * K))), Image.LANCZOS),
                 (int(Lw * K), int(-top * K)))
    dr = ImageDraw.Draw(canvas)
    ink = (60, 65, 75)
    for i in items:
        axf, ayf, tyf = Lw + i["ax"] * s, i["ay"] * s - top, i["ty"] - top
        sd = i["side"]
        for k, ln in enumerate(i["lines"]):
            if sd == "L":
                xx = Lw - 14 - tw(ln)
            elif sd == "R":
                xx = OUT_W - Rw + 14
            else:
                xx = i["tx"] + (i["w"] - tw(ln)) / 2
            dr.text((xx * K, (tyf + k * fs * 1.2) * K), ln, font=font, fill=(25, 28, 34))
        if sd == "L":
            p0 = (Lw - 8, tyf + i["h"] / 2)
        elif sd == "R":
            p0 = (OUT_W - Rw + 8, tyf + i["h"] / 2)
        elif sd == "T":
            p0 = (i["tx"] + i["w"] / 2, tyf + i["h"] + 3)
        else:
            p0 = (i["tx"] + i["w"] / 2, tyf - 3)
        dr.line([(p0[0] * K, p0[1] * K), (axf * K, ayf * K)], fill=ink, width=2 * K)
        r = 4 * K
        dr.ellipse([axf * K - r, ayf * K - r, axf * K + r, ayf * K + r], fill=ink)
    return canvas.resize((OUT_W, H), Image.LANCZOS)



# --------------------------------------------------------------------------
def glow(part, color):
    """self-lit colour (the LED-lit light-pipe ring)"""
    pr = part.actor.GetProperty()
    pr.SetColor(*color)
    pr.SetAmbient(1.0)
    pr.SetDiffuse(0.15)
    pr.SetSpecular(0.0)
    return part


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cad_dir", nargs="?", default="cad")
    ap.add_argument("out_dir", nargs="?", default="renders")
    ap.add_argument("--pcb-step", default=None)
    ap.add_argument("--kicad-pcb", default=None)
    ap.add_argument("--only", default=None)
    a = ap.parse_args()
    cad = Cad(a.cad_dir)
    only = set(a.only.split(",")) if a.only else None

    import flashka_housing as H
    p = H.P()
    if a.pcb_step:
        pcbset = PcbSet(a.pcb_step, a.kicad_pcb, p, H.build_dummies(p))
    else:
        pcbset = SimplePcb(cad)

    def want(n):
        return only is None or n in only

    CYAN = (0.30, 0.95, 1.0)
    bt = p.btn_y
    pos = {"FlashKa_cap_main": p.X_main, "FlashKa_cap_slide": p.X_next}

    def caps(dz=0.0, dzt=0.0, lit=False):
        """tube + three stainless caps in place (the STLs are centred on their axes); dz / dzt lower them (exploded)"""
        out = []
        t = cad.part("FlashKa_tube", (0, 0, dzt))
        out.append(glow(t, CYAN) if lit else t)
        out.append(cad.part("FlashKa_cap_main", (p.X_main, bt, dz)))
        out.append(cad.part("FlashKa_cap_slide", (p.X_next, bt, dz)))
        out.append(cad.part("FlashKa_cap_slide", (p.X_prev, bt, dz)))
        return out

    def marks(*faces):
        out = []
        for f in faces:
            path = os.path.join(a.cad_dir, "_mark_%s.png" % f)
            if os.path.exists(path):
                out.append(MarkQuad(f, path, p))
        return out

    def housing(extra=()):
        return [cad.part(n) for n in ("FlashKa_tray", "FlashKa_lid", "FlashKa_rf_window", "FlashKa_antenna_spacer") + tuple(extra)]

    xm = p.L / 2
    if want("closed_bottom"):      # bottom face: three stainless caps, the ring lit cyan, marking
        shoot(housing(["_ref_splitring"]) + caps(lit=True) + marks("bottom", "minus_y"), "housing_closed_bottom.png",
              a.out_dir, direction=(0.45, -0.75, -1.0), up=(0, 0, -1), focal=(xm + 6, 0, 8))
    if want("bottom_flat"):
        shoot(housing() + caps(lit=True) + marks("bottom"), "housing_bottom_flat.png", a.out_dir,
              direction=(0.0, 0.0, -1.0), up=(0, 1, 0), focal=(xm, 0, 0), ratio=0.30, fill=0.94,
              view_angle=12, margin=0.02)
    if want("closed_lid"):
        shoot(housing(["_ref_lidscrews"]) + caps() + marks("lid"), "housing_closed_lid.png", a.out_dir,
              direction=(0.0, -0.18, 1.0), up=(0, 1, 0), focal=(xm, 0, 16), ratio=0.30, fill=0.94,
              view_angle=12, margin=0.02)
    if want("closed_control_side"):
        shoot(housing(["_ref_splitring", "_ref_lidscrews"]) + caps() + pcbset.parts() + marks("minus_y", "lid"),
              "housing_closed_control_side.png", a.out_dir,
              direction=(-0.45, -1.0, 0.45), focal=(xm + 6, 0, 8))
    if want("closed_rear"):
        shoot(housing(["_ref_splitring", "_ref_lidscrews"]) + caps() + marks("plus_y", "lid"),
              "housing_closed_rear.png", a.out_dir, direction=(0.55, 1.0, 0.5), focal=(xm + 6, 0, 8))
    if want("front"):
        shoot(housing(["_ref_window", "_ref_led", "_ref_laser", "_ref_lidscrews"]) + caps() + pcbset.parts(),
              "housing_front.png", a.out_dir, direction=(-1.0, -0.55, 0.32), focal=(0, 0, 8), fill=0.88,
              ratio=0.75, view_angle=28)
    open_parts = [cad.part(n) for n in ("FlashKa_tray", "FlashKa_spacer_ring", "FlashKa_antenna_spacer", "_ref_cell1",
                                        "_ref_cell2", "_ref_window", "_ref_mcpcb", "_ref_led", "_ref_laser",
                                        "_ref_pad", "_ref_pad2")] + caps()
    if want("open_top"):
        lab = [("S2 laser\ninterlock", (14, 7.5, 11.5), "T"),
               ("2 x 601646 cells (in parallel)", (62, 0, 13.7), "T"),
               ("lanyard slot", (90.2, 0, 14.5), "T"),
               ("hold-down pads\n(under the lid bosses)", (26.5, 0, 13.0), "T"),
               ("head block: window bore\n+ laser bore", (3, -4, 14.5), "B"),
               ("4-layer PCB", (20, -4, 10.3), "B"),
               ("RF-window zone\n(ESP32 antenna)", (35.5, -2, 10.8), "B")]
        shoot(open_parts + pcbset.parts(), "housing_open_top.png", a.out_dir,
              direction=(0.0, -0.45, 1.0), up=(0, 1, 0), focal=(xm, 0, 8), ratio=0.45, fill=0.92,
              labels=lab, margin=0.02)
    if want("open_iso"):
        shoot(open_parts + pcbset.parts(), "housing_open_iso.png", a.out_dir,
              direction=(-0.5, -1.0, 0.95), focal=(xm, 0, 8))
    if want("exploded"):
        ex = [cad.part("FlashKa_tray"),
              cad.part("FlashKa_lid", (0, 0, 36)),
              cad.part("FlashKa_rf_window", (0, 0, 24)),
              cad.part("_ref_lidscrews", (0, 0, 46)),
              cad.part("_ref_pad", (0, 0, 14)),
              cad.part("_ref_pad2", (0, 0, 14)),
              cad.part("FlashKa_antenna_spacer", (0, 0, 4)),
              cad.part("_ref_cell1", (0, 0, 12)),
              cad.part("_ref_cell2", (0, 0, 20)),
              cad.part("FlashKa_spacer_ring", (-14, 0, 0)),
              cad.part("_ref_window", (-22, 0, 0)),
              cad.part("_ref_led", (-6, 0, 0)),
              cad.part("_ref_mcpcb", (-6, 0, 0)),
              cad.part("_ref_laser", (-24, 0, 0))] + caps(dz=-11, dzt=-5)
        if cad.has("FlashKa_laser_sleeve"):
            ex.append(cad.part("FlashKa_laser_sleeve", (-38, 0, 0)))
        lab = [("lid", (60, 8, 52), "R"),
               ("4 x M1.6 countersunk screws", (88, 7, 59), "R"),
               ("RF window insert (resin,\nglued in from inside)", (35, 0, 41), "L"),
               ("cells 2 x 601646", (62, 0, 34), "R"),
               ("4-layer PCB", (20, 0, 20.5), "L"),
               ("antenna spacer (resin)", (36, 0, 14), "R"),
               ("light-pipe tube (resin)", (p.X_main, bt, -4), "R"),
               ("3 stainless caps", (p.X_prev, bt, -10), "R"),
               ("spacer ring (resin)", (-12.5, -3.8, 13), "L"),
               ("glass window", (-21.5, -3.8, 13), "L"),
               ("LED + 10 mm DTP board", (-4, -3.8, 13), "L"),
               ("laser module", (-16, 5.85, 8.9), "L"),
               ("laser sleeve (optional)", (-33, 5.85, 8.9), "L")]
        shoot(ex + pcbset.parts((0, 0, 9)), "housing_exploded.png", a.out_dir,
              direction=(-0.55, -1.0, 0.72), focal=None, fill=0.90, labels=lab, margin=0.02)
    if want("print_kit") and cad.has("FlashKa_print_kit"):
        shoot([cad.part("FlashKa_print_kit")], "housing_print_kit.png", a.out_dir,
              direction=(-0.2, -1.0, 0.75), up=(0, 0, 1), fill=0.90, ratio=0.55, view_angle=15, margin=0.03)


if __name__ == "__main__":
    main()
