#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Offscreen VTK renders of the FlashKa Keychain v0.7 housing (run under xvfb-run).

usage:  xvfb-run -a python3 render.py <cad_dir> <out_dir> [--pcb-step FILE] [--kb-step FILE] [--kicad-pcb FILE]
                                      [--kb-kicad-pcb FILE] [--only name1,name2] [--assets DIR]

  <cad_dir>       folder written by flashka_housing.py (FlashKa_*.stl, _ref_*.stl)
  <out_dir>       PNG folder (1600 px wide each)
  --pcb-step      KiCad STEP export of the main board (frame: housing X, Y; Z = 0 on the board's bottom face - lifted
                  by P.Z_pcb_bot).  Without it the simplified stand-in board (_ref_pcb.stl + parts) is drawn.
  --kb-step       KiCad STEP export of the key board (frame: housing X, Y; Z = 0 on the key board's bottom face -
                  lifted by P.kb_z0).  Without it the key-board stand-in (_ref_kb*.stl) is drawn.
  --kicad-pcb     .kicad_pcb of the main board (stand-ins for parts without a 3D model, copper pads)
  --kb-kicad-pcb  .kicad_pcb of the key board (copper pads); default ../../kicad/FlashKa_keys/FlashKa_keys.kicad_pcb
  --only          comma-separated subset of the picture names below
  --assets        also copy the pictures into this folder (the set the READMEs use)

All pictures are renders of the design without any marking.  Materials (physically based shading with a
procedural studio environment): black bead-blasted anodised aluminium (tray, lid), matte black rubber (side
keys with glossy chevron tops: polished chevron grooves in the mould), clear polished PMMA with the frosted ring glowing
cyan (main key), matte black POM-C (RF window inserts, antenna spacer), the LEDiL TIR optic (clear PMMA lens in a black
PC holder) in front of the LED.  Both boards (one panel) are ordered with black solder mask: matte black,
the copper pads ENIG - gold where no solder covers them (the J6 pogo targets), solder-silver where parts are
reflowed.  The white silkscreen is not drawn.

Pictures:
  housing_closed_bottom.png        hero: from below, the key cluster with the lit ring, split ring
  key_cluster_macro.png            close-up of the three keys
  housing_bottom_flat.png          straight from below
  housing_closed_lid.png           straight from above
  housing_closed_control_side.png  -Y side with the USB-C port
  housing_closed_rear.png          +Y side with the S2 slot
  housing_front.png                front: the TIR optic (LED behind the lens), laser aperture
  housing_open_top.png             open, from above, with labels
  housing_open_iso.png             open, iso view
  housing_exploded.png             exploded view with labels (key board and screws included)
  hero_dark.png                    the hero picture on a dark background (banner)
  key_mould.png                    the open resin casting mould (the default) with cast keys (build guide;
                                   needs the _ref_mould_resin_*.stl files of key_mould.py)
  key_mould_aluminium.png          the same with the aluminium mould (the durable option)
"""
import argparse
import os
import shutil
import sys

import numpy as np
import vtk
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from vtk.util.numpy_support import numpy_to_vtk, vtk_to_numpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

OUT_W = 1600
SS = 2.5
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
CYAN = (0.133, 0.827, 0.933)          # #22d3ee, the lit ring
DARK_BG = (0.051, 0.067, 0.090)       # #0d1117

# physically based materials: base colour (linear), metallic, roughness, opacity
MATS = {
    "anod":   ((0.050, 0.051, 0.056), 0.75, 0.42, 1.0),
    "rubber": ((0.050, 0.050, 0.053), 0.00, 0.60, 1.0),
    "pom":    ((0.032, 0.032, 0.034), 0.00, 0.75, 1.0),
    "pmma":   ((0.92, 0.96, 1.00), 0.00, 0.05, 0.26),
    "pcb":    ((0.016, 0.016, 0.018), 0.00, 0.58, 1.0),       # matte black solder mask (both boards)
    "solder": ((0.84, 0.84, 0.82), 1.00, 0.30, 1.0),          # reflowed pads
    "metal":  ((0.78, 0.78, 0.80), 1.00, 0.30, 1.0),
    "alu_blast": ((0.80, 0.80, 0.82), 1.00, 0.55, 1.0),       # bead-blasted aluminium (mould cavity half)
    "alu_mill": ((0.82, 0.82, 0.84), 1.00, 0.26, 1.0),        # machined aluminium (mould lid)
    "steel":  ((0.70, 0.70, 0.72), 1.00, 0.38, 1.0),
    "gold":   ((0.86, 0.66, 0.32), 1.00, 0.25, 1.0),
    "led":    ((0.92, 0.92, 0.88), 0.00, 0.40, 1.0),
    "cell":   ((0.80, 0.62, 0.22), 0.00, 0.55, 1.0),
    "glass":  ((0.85, 0.93, 1.00), 0.00, 0.05, 0.35),
    "lens_pmma": ((0.90, 0.95, 1.00), 0.00, 0.03, 0.30),      # TIR lens, clear PMMA
    "pc_black": ((0.020, 0.020, 0.022), 0.00, 0.35, 1.0),     # optic holder, black polycarbonate
    "phosphor": ((0.92, 0.80, 0.30), 0.00, 0.45, 1.0),        # LED phosphor dome
    "resin":  ((0.70, 0.70, 0.68), 0.00, 0.50, 1.0),          # SLA resin mould
    "copper": ((0.82, 0.48, 0.28), 1.00, 0.35, 1.0),
    "brass":  ((0.80, 0.62, 0.32), 1.00, 0.35, 1.0),
    "pad":    ((0.45, 0.45, 0.47), 0.00, 0.80, 1.0),
    "pad2":   ((0.10, 0.10, 0.11), 0.00, 0.85, 1.0),
    "lens":   ((0.02, 0.02, 0.025), 0.00, 0.08, 1.0),
    "rubber_gloss": ((0.050, 0.050, 0.053), 0.00, 0.22, 1.0),     # glossy top face of the chevrons
    "black":  ((0.03, 0.03, 0.03), 0.00, 0.50, 1.0),
    "ic":     ((0.04, 0.04, 0.045), 0.00, 0.45, 1.0),
    "cap":    ((0.62, 0.48, 0.30), 0.00, 0.45, 1.0),
    "white":  ((0.85, 0.85, 0.85), 0.00, 0.50, 1.0),
}

PART_MAT = {
    "FlashKa_tray": "anod", "FlashKa_lid": "anod", "FlashKa_rf_window": "pom", "FlashKa_antenna_spacer": "pom",
    "FlashKa_laser_sleeve": "pom", "FlashKa_key_main": "pmma", "_ref_optic_holder": "pc_black",
    "_ref_optic_lens": "lens_pmma",
    "FlashKa_key_side": "rubber", "_ref_key_side_prev": "rubber", "FlashKa_key_stiffener": "steel",
    "_ref_key_stiffener_prev": "steel", "_ref_pcb": "pcb", "_ref_module": "pcb", "_ref_module_can": "metal",
    "_ref_cell": "cell", "_ref_cell_strip_front": "metal", "_ref_cell_strip_rear": "metal",
    "_ref_cell_joint_front": "solder", "_ref_cell_joint_rear": "solder", "_ref_cell_pad_top": "pad2",
    "_ref_cell_pad_end": "pad2", "_ref_mcpcb": "copper", "_ref_led": "phosphor",
    "_ref_laser": "brass", "_ref_usb": "metal", "_ref_s2": "black", "_ref_s2_knob": "white", "_ref_L1": "ic",
    "_ref_splitring": "metal", "_ref_lidscrews": "metal", "_ref_kbscrews": "metal", "_ref_pad": "pad",
    "_ref_pad2": "pad2", "_ref_kb": "pcb", "_ref_kb_led3": "led", "_ref_kb_led4": "led",
}


CELL_REFS = ("_ref_cell", "_ref_cell_strip_front", "_ref_cell_strip_rear", "_ref_cell_joint_front",
             "_ref_cell_joint_rear", "_ref_cell_pad_top", "_ref_cell_pad_end")


def mat_for(name):
    if name in PART_MAT:
        return PART_MAT[name]
    n = name.replace("_ref_", "")
    if n.startswith("kb_sw") and n.endswith("_act"):
        return "black"
    if n.startswith("kb_sw"):
        return "metal"
    if n.startswith("kb_pogo") and n.endswith("_pl"):
        return "gold"
    if n.startswith("kb_pogo"):
        return "gold"
    if n.startswith("kb_screw"):
        return "metal"
    return "black"


# --------------------------------------------------------------------------
# geometry -> actors
# --------------------------------------------------------------------------
def polydata_from_stl(path):
    r = vtk.vtkSTLReader()
    r.SetFileName(path)
    r.Update()
    return r.GetOutput()


def polydata_from_shape(shape, tol=0.02, ang=0.25):
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
    def __init__(self, pd, mat, offset=(0, 0, 0), name="", glow=False, color=None, opacity=None):
        n = vtk.vtkPolyDataNormals()
        n.SetInputData(pd)
        n.SetFeatureAngle(32)
        n.SplittingOn()
        n.Update()
        m = vtk.vtkPolyDataMapper()
        m.SetInputConnection(n.GetOutputPort())
        a = vtk.vtkActor()
        a.SetMapper(m)
        pr = a.GetProperty()
        if glow:
            pr.SetColor(*CYAN)
            pr.LightingOff()
        else:
            col, met, rough, op = MATS[mat]
            pr.SetInterpolationToPBR()
            pr.SetColor(*(color or col))
            pr.SetMetallic(met)
            pr.SetRoughness(rough)
            pr.SetOpacity(op if opacity is None else opacity)
        a.SetPosition(*offset)
        self.actor, self.name, self.glow = a, name, glow


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

    def part(self, name, offset=(0, 0, 0), mat=None, glow=False, opacity=None):
        return Part(self.pd(name), mat or mat_for(name), offset, name, glow=glow, opacity=opacity)


# --------------------------------------------------------------------------
# boards: real STEP models or stand-ins
# --------------------------------------------------------------------------
def pcb_mat(name, model):
    n = (name or "").upper()
    m = model or ""
    if name in ("PCB", "KB_PCB"):
        return "pcb"
    if "pogo" in m.lower():
        return "gold"
    if n == "U4_PCB":
        return "pcb"
    if n in ("S2",) or n.startswith("J") or n.startswith("U4") or n.startswith("SW"):
        return "metal"
    if n.startswith("P") and n[1:].isdigit():
        return "gold"
    if m.startswith("C_") or (n.startswith("C") and n[1:2].isdigit()):
        return "cap"
    if n.startswith("LED"):
        return "led"
    return "ic"


class StepBoard:
    """tessellated board assembly (KiCad STEP + stand-ins), built once, instanced per picture"""

    def __init__(self, items):
        self.items = []
        for it in items:
            self.items.append((it["name"], polydata_from_shape(it["solid"], 0.01, 0.3), pcb_mat(it["name"], it["model"])))

    def parts(self, offset=(0, 0, 0)):
        return [Part(pd, m, offset, "pcb_" + nm) for nm, pd, m in self.items]


def pad_items(kicad_path, board_solid, tag, t=0.02):
    """the copper pads of a board as two thin layers on its faces (the KiCad STEP has the board body only):
    ENIG gold where no paste is printed (the J6 pogo targets), solder-silver on the reflowed pads.
    -> [(name, polydata, material)]"""
    import cadquery as cq
    import fit_pcb
    bb = board_solid.BoundingBox()
    groups = {"gold": [], "solder": []}
    for d in fit_pcb.parse_kicad_pads(kicad_path):
        for on, z0 in ((d["top"], bb.zmax), (d["bottom"], bb.zmin - t)):
            if not on:
                continue
            w, h = d["w"], d["h"]
            wp = cq.Workplane("XY", origin=(0, 0, z0))
            if d["shape"] == "circle":
                s = wp.circle(w / 2).extrude(t)
            elif d["shape"] == "oval":
                s = wp.slot2D(max(w, h), min(w, h), 0 if w >= h else 90).extrude(t)
            else:
                r = d["rratio"] * min(w, h) if d["shape"] == "roundrect" else 0.0
                sk = cq.Sketch().rect(w, h)
                s = wp.placeSketch(sk.vertices().fillet(r) if r > 1e-4 else sk).extrude(t)
            if d["angle"]:
                s = s.rotate((0, 0, 0), (0, 0, 1), d["angle"])
            groups["solder" if d["paste"] else "gold"].append(s.translate((d["x"], d["y"], 0)).val())
    return [("%s_pads_%s" % (tag, m), polydata_from_shape(cq.Compound.makeCompound(v), 0.005, 0.3), m)
            for m, v in groups.items() if v]


class SimpleBoard:
    def __init__(self, cad, names):
        self.cad, self.names = cad, names

    def parts(self, offset=(0, 0, 0)):
        return [self.cad.part(n, offset) for n in self.names if self.cad.has(n)]


MAIN_STANDINS = ["_ref_pcb", "_ref_module", "_ref_module_can", "_ref_usb", "_ref_s2", "_ref_s2_knob", "_ref_L1"]


def kb_standins(cad):
    names = ["_ref_kb", "_ref_kb_led3", "_ref_kb_led4"]
    for k in (1, 2, 3):
        names += ["_ref_kb_sw%d" % k, "_ref_kb_sw%d_act" % k]
    for k in range(1, 13):
        if cad.has("_ref_kb_pogo%d" % k):
            names += ["_ref_kb_pogo%d" % k, "_ref_kb_pogo%d_pl" % k]
    return names


# --------------------------------------------------------------------------
# studio: one renderer + window, reused for every picture (the environment is prefiltered once)
# --------------------------------------------------------------------------
def env_cube(N=32):
    """procedural photo studio: grey walls brighter towards the top, an overhead soft box, two strip lights"""
    cube = vtk.vtkTexture()
    cube.CubeMapOn()
    cube.MipmapOn()
    cube.InterpolateOn()
    u, v = np.meshgrid(np.linspace(-1, 1, N), np.linspace(-1, 1, N))
    dirs = {0: (np.ones_like(u), -v, -u), 1: (-np.ones_like(u), -v, u), 2: (u, np.ones_like(u), v),
            3: (u, -np.ones_like(u), -v), 4: (u, -v, np.ones_like(u)), 5: (-u, -v, -np.ones_like(u))}
    for i in range(6):
        x, y, z = dirs[i]
        n = np.sqrt(x * x + y * y + z * z)
        x, y, z = x / n, y / n, z / n
        base = 0.10 + 0.10 * np.clip(y, 0, 1)
        soft = np.exp(-(x ** 2 + (z - 0.2) ** 2) / 0.10) * (y > 0.6) * 3.0
        strip1 = np.exp(-((z - 0.75) ** 2) / 0.004) * (np.abs(y - 0.3) < 0.45) * (x > 0.2) * 2.2
        strip2 = np.exp(-((x + 0.8) ** 2) / 0.006) * (np.abs(y - 0.2) < 0.5) * 1.6
        img = np.clip(base + soft + strip1 + strip2, 0, 1)
        rgb = np.dstack([img, img, img * 1.02])
        t = vtk.vtkImageData()
        t.SetDimensions(N, N, 1)
        t.GetPointData().SetScalars(numpy_to_vtk((np.clip(rgb, 0, 1) * 255).astype(np.uint8).reshape(-1, 3),
                                                 deep=True, array_type=vtk.VTK_UNSIGNED_CHAR))
        cube.SetInputDataObject(i, t)
    return cube


class Studio:
    def __init__(self, bg=(1, 1, 1)):
        self.ren = vtk.vtkRenderer()
        self.ren.SetBackground(*bg)
        self.ren.AutomaticLightCreationOff()
        self.cube = env_cube()
        self.ren.SetEnvironmentTexture(self.cube, False)
        self.ren.UseImageBasedLightingOn()
        for pos, inten in (((0.35, 0.85, 1.0), 1.6), ((-1.0, -0.25, 0.55), 0.6), ((0.15, 1.0, -0.6), 0.9)):
            lt = vtk.vtkLight()
            lt.SetLightTypeToCameraLight()
            lt.SetPosition(*pos)
            lt.SetIntensity(inten)
            self.ren.AddLight(lt)
        self.win = vtk.vtkRenderWindow()
        self.win.SetOffScreenRendering(1)
        self.win.AddRenderer(self.ren)
        self.win.SetAlphaBitPlanes(1)
        self.win.SetMultiSamples(0)
        self.ren.SetUseDepthPeeling(1)
        self.ren.SetMaximumNumberOfPeels(12)
        self.ren.SetOcclusionRatio(0.0)
        # glow mask: the same geometry, everything black except the glowing parts
        self.mren = vtk.vtkRenderer()
        self.mren.SetBackground(0, 0, 0)
        self.mren.AutomaticLightCreationOff()
        self.mren.SetActiveCamera(self.ren.GetActiveCamera())
        self.mwin = vtk.vtkRenderWindow()
        self.mwin.SetOffScreenRendering(1)
        self.mwin.AddRenderer(self.mren)
        self.mwin.SetMultiSamples(0)
        self.parts, self.pairs = [], []

    def set_parts(self, parts, bg=(1, 1, 1)):
        self.ren.RemoveAllViewProps()
        self.mren.RemoveAllViewProps()
        self.ren.SetBackground(*bg)
        self.parts, self.pairs = parts, []
        for pt in parts:
            self.ren.AddActor(pt.actor)
            a = vtk.vtkActor()
            a.SetMapper(pt.actor.GetMapper())
            pr = a.GetProperty()
            pr.LightingOff()
            pr.SetColor(*(CYAN if pt.glow else (0, 0, 0)))
            self.mren.AddActor(a)
            self.pairs.append((pt.actor, a))
        self.has_glow = any(pt.glow for pt in parts)

    def size(self, w, h):
        self.win.SetSize(int(w), int(h))
        self.mwin.SetSize(int(w), int(h))

    def sync(self):
        for a, m in self.pairs:
            m.SetPosition(a.GetPosition())
            m.SetUserMatrix(a.GetUserMatrix())

    def grab(self, glow=True):
        self.ren.ResetCameraClippingRange()
        self.win.Render()
        img = _grab(self.win)
        g = None
        if glow and self.has_glow:
            self.sync()
            self.mren.ResetCameraClippingRange()
            self.mwin.Render()
            g = _grab(self.mwin)
        return img, g


_STUDIO = None


def studio():
    global _STUDIO
    if _STUDIO is None:
        _STUDIO = Studio()
    return _STUDIO


def _grab(win):
    f = vtk.vtkWindowToImageFilter()
    f.SetInput(win)
    f.ReadFrontBufferOff()
    f.SetInputBufferTypeToRGB()
    f.Update()
    img = f.GetOutput()
    w, h, _ = img.GetDimensions()
    return vtk_to_numpy(img.GetPointData().GetScalars()).reshape(h, w, 3)[::-1].copy()


def content_box(arr, bg=(255, 255, 255), thr=10):
    diff = np.abs(arr.astype(np.int16) - np.array(bg, np.int16)).max(axis=2) > thr
    ys, xs = np.where(diff)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def bloom(img, mask, radius, strength=0.9):
    """screen-blend a blurred copy of the glow mask onto the picture (core + halo)"""
    if mask is None:
        return img
    m = Image.fromarray(mask)
    g1 = np.asarray(m.filter(ImageFilter.GaussianBlur(radius)), np.float32) / 255
    g2 = np.asarray(m.filter(ImageFilter.GaussianBlur(radius * 3.0)), np.float32) / 255
    g = np.clip((0.75 * g1 + 0.55 * g2) * strength, 0, 1)
    base = img.astype(np.float32) / 255
    out = 1 - (1 - base) * (1 - g)
    return (out * 255 + 0.5).astype(np.uint8)


def unit(v):
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


def frame_camera(st, direction, up, focal, view_angle, fill, ratio, bg255, W0=900, iters=10):
    """point the camera along `direction` and zoom / pan until the content fills `fill` of the frame"""
    ren = st.ren
    cam = ren.GetActiveCamera()
    b = [0.0] * 6
    ren.ComputeVisiblePropBounds(b)
    if focal is None:
        focal = ((b[0] + b[1]) / 2, (b[2] + b[3]) / 2, (b[4] + b[5]) / 2)
    d = unit(direction)
    upv0 = unit(up)
    cam.SetViewAngle(view_angle)
    cam.SetViewUp(*upv0)
    cam.SetFocalPoint(*focal)
    cam.SetPosition(*(np.array(focal) + d * 100))
    ren.ResetCamera(b)
    cam.SetFocalPoint(*focal)
    cam.SetPosition(*(np.array(focal) + d * cam.GetDistance()))
    cam.SetViewUp(*upv0)
    st.size(W0, int(W0 * ratio))
    for it in range(iters):
        arr, _ = st.grab(glow=False)
        H0, W1 = arr.shape[:2]
        bb = content_box(arr, bg255)
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
        right = unit(np.cross(-d, upv0))
        upv = np.cross(right, -d)
        shift = right * dxp * wpp + upv * dyp * wpp
        cam.SetFocalPoint(*(np.array(cam.GetFocalPoint()) + shift))
        cam.SetPosition(*(np.array(cam.GetPosition()) + shift))
        cam.Zoom(s if not touching else min(s, 0.9))


def shoot(parts, fname, out_dir, direction, up=(0, 0, 1), focal=None, fill=0.90, ratio=0.62, view_angle=20.0,
          labels=None, margin=0.03, bg=(1, 1, 1), glow_radius=2.2, glow_strength=0.85, crop=True, fit_parts=None):
    """render `parts` seen from focal + direction, fit, crop and write a PNG OUT_W px wide.
    labels: [(text, (x, y, z), side)] callouts in a column left ('L') / right ('R') or rows above ('T') / below ('B').
    fit_parts: frame the camera on these parts only (close-ups), then draw all `parts`."""
    st = studio()
    bg255 = tuple(int(round(c * 255)) for c in bg)
    if fit_parts:
        st.set_parts(fit_parts, bg)
        frame_camera(st, direction, up, focal, view_angle, fill, ratio, bg255)
        st.set_parts(parts, bg)
    else:
        st.set_parts(parts, bg)
        frame_camera(st, direction, up, focal, view_angle, fill, ratio, bg255)
    W2 = int(OUT_W * SS)
    H2 = int(round(W2 * ratio))
    st.size(W2, H2)
    arr, g = st.grab(glow=True)
    arr = bloom(arr, g, radius=glow_radius * SS, strength=glow_strength)
    x0, y0, x1, y1 = content_box(arr, bg255)
    m = int(margin * max(x1 - x0, y1 - y0))
    if crop:
        cx0, cy0 = max(x0 - m, 0), max(y0 - m, 0)
        cx1, cy1 = min(x1 + m, arr.shape[1] - 1), min(y1 + m, arr.shape[0] - 1)
    else:
        cx0, cy0, cx1, cy1 = 0, 0, arr.shape[1] - 1, arr.shape[0] - 1
    model = Image.fromarray(arr[cy0:cy1 + 1, cx0:cx1 + 1])
    anchors = []
    for text, xyz, side in (labels or []):
        st.ren.SetWorldPoint(float(xyz[0]), float(xyz[1]), float(xyz[2]), 1.0)
        st.ren.WorldToDisplay()
        px, py, _ = st.ren.GetDisplayPoint()
        anchors.append((text, px - cx0, (H2 - 1 - py) - cy0, side))
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, fname)
    if not anchors:
        im = model.resize((OUT_W, int(round(model.height * OUT_W / model.width))), Image.LANCZOS)
    else:
        im = _compose_labels(model, anchors, bg=bg255)
    im.save(path, optimize=True)
    print("wrote", path, im.size, flush=True)
    return path


def _compose_labels(model, anchors, fs=26, pad=26, gap=10, bg=(255, 255, 255)):
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
    for side in ("L", "R"):
        y = None
        for i in sorted([i for i in items if i["side"] == side], key=lambda i: i["ay"]):
            t = i["ay"] * s - i["h"] / 2
            if y is not None:
                t = max(t, y + gap)
            i["ty"] = t
            y = t + i["h"]
    for side in ("T", "B"):
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
    canvas = Image.new("RGB", (OUT_W * K, H * K), bg)
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
class Model:
    """the parts of one cad folder plus the boards (real STEP or stand-ins)"""

    def __init__(self, cad_dir, pcb_step=None, kb_step=None, kicad_pcb=None, verbose=True, kb_kicad_pcb=None):
        import flashka_housing as H
        self.H = H
        self.p = H.P()
        self.cad = Cad(cad_dir)
        self.cad_dir = cad_dir
        dm = H.build_dummies(self.p)
        if kb_kicad_pcb is None:
            kb_kicad_pcb = os.path.join(HERE, "..", "..", "kicad", "FlashKa_keys", "FlashKa_keys.kicad_pcb")
        if pcb_step and os.path.exists(pcb_step):
            import fit_pcb
            items, _ = fit_pcb.pcb_items(pcb_step, self.p, dm, kicad_pcb, verbose=False)
            if any(it["name"] == "U4" and it["kind"] == "standin" for it in items):   # module board black, can metal
                items = [it for it in items if it["name"] != "U4"]
                items += [{"name": "U4_pcb", "model": "stand-in", "solid": dm["module"].val(), "kind": "standin"},
                          {"name": "U4_can", "model": "stand-in", "solid": dm["module_can"].val(), "kind": "standin"}]
            self.pcb = StepBoard(items)
            self.pcb_kind = "main board: KiCad STEP (%d solids)" % len(items)
            board = [it["solid"] for it in items if it["name"] == "PCB"]
            if kicad_pcb and os.path.exists(kicad_pcb) and board:
                self.pcb.items += pad_items(kicad_pcb, board[0], "main")
                self.pcb_kind += " + pads"
        else:
            self.pcb = SimpleBoard(self.cad, MAIN_STANDINS)
            self.pcb_kind = "main board: stand-in"
        if kb_step and os.path.exists(kb_step):
            import fit_pcb
            items = fit_pcb.kb_items(kb_step, self.p)
            # installed: the pogo plungers end on the J6 pads; exploded: at their free height (as in the STEP)
            inst = [dict(it, solid=fit_pcb.at_working_height(it["solid"], self.p))
                    if fit_pcb.is_plunger(it["name"], it["solid"], self.p) else it for it in items]
            self.kb = StepBoard(inst)
            self.kb_free = StepBoard(items)
            self.kb_kind = "key board: KiCad STEP (%d solids)" % len(items)
            board = [it["solid"] for it in items if it["name"] == "KB_PCB"]
            if kb_kicad_pcb and os.path.exists(kb_kicad_pcb) and board:
                pads = pad_items(kb_kicad_pcb, board[0], "kb")
                self.kb.items += pads
                self.kb_free.items += pads
                self.kb_kind += " + pads"
        else:
            self.kb = SimpleBoard(self.cad, kb_standins(self.cad))
            self.kb_free = self.kb
            self.kb_kind = "key board: stand-in"
        # small bought parts that only the pictures need: the lens of the laser module, the M1.6 x 5 laser set screw
        # (screwed in from the head-block top, under the lid)
        p = self.p
        lens = H.cyl_x(p.Y_l, p.Z_las, 3.0, p.las_recess - 0.03, p.las_recess - 0.005).val()
        grub = H.laser_set_screw(p)
        self.extras = [("laser_lens", polydata_from_shape(lens, 0.01), "lens"),
                       ("laser_set_screw", polydata_from_shape(grub, 0.01), "black")]
        # glossy chevron tops on the matte key face: the builder polishes the chevron grooves of the mould
        # (3_rubber_keys/README.txt); drawn as a 0.02 mm skin just outside each top
        sw = p.chevron[0]
        z_top = p.side_face_z - p.chevron_h
        self.chevron_caps = []
        for x, s in ((p.X_next, -1), (p.X_prev, 1)):
            cap = (H.cq.Workplane("XY", origin=(0, 0, z_top - 0.02)).polyline(H.chevron_pts(p, x, s))
                   .offset2D(sw / 2 - 0.03, "arc").extrude(0.02)).val()
            self.chevron_caps.append(polydata_from_shape(cap, 0.005))
        if verbose:
            print(self.pcb_kind, "|", self.kb_kind, flush=True)

    def part(self, name, offset=(0, 0, 0), **kw):
        return self.cad.part(name, offset, **kw)

    def keys(self, dz=0.0, lit=True, stiffeners=True):
        """the three keys; the side keys with their stiffener plate + doubler glued into the inner face"""
        out = [self.part("FlashKa_key_main", (0, 0, dz)), self.part("FlashKa_key_side", (0, 0, dz)),
               self.part("_ref_key_side_prev", (0, 0, dz))]
        out += [Part(pd, "rubber_gloss", (0, 0, dz), "chevron_cap") for pd in self.chevron_caps]
        if lit:
            out.append(self.part("_ref_ring_icon", (0, 0, dz), glow=True))
        if stiffeners:
            out += [self.part("FlashKa_key_stiffener", (0, 0, dz)), self.part("_ref_key_stiffener_prev", (0, 0, dz))]
        return out

    def shell(self, extra=()):
        names = ["FlashKa_tray", "FlashKa_lid", "FlashKa_rf_window", "FlashKa_antenna_spacer"] + list(extra)
        return [self.part(n) for n in names if self.cad.has(n)]

    def extra_parts(self, offset=(0, 0, 0)):
        return [Part(pd, m, offset, nm) for nm, pd, m in self.extras]

    def inside(self):
        names = ["_ref_optic_holder", "_ref_optic_lens", "_ref_mcpcb", "_ref_led", "_ref_laser", "_ref_pad", "_ref_pad2",
                 "_ref_kbscrews"] + list(CELL_REFS)
        return ([self.part(n) for n in names if self.cad.has(n)] + self.pcb.parts() + self.kb.parts()
                + self.extra_parts())

    def closed(self, lit=True, splitring=False, screws=True):
        extra = (["_ref_lidscrews"] if screws else []) + (["_ref_splitring"] if splitring else [])
        return self.shell(extra) + self.keys(lit=lit) + self.inside()


HERO = dict(direction=(0.45, -0.75, -1.0), up=(0, 0, -1))


def render_all(model, out_dir, only=None):
    p = model.p
    xm = p.L / 2
    made = []

    def want(n):
        return only is None or n in only

    if want("closed_bottom"):
        made.append(shoot(model.closed(splitring=True), "housing_closed_bottom.png", out_dir, focal=(xm + 6, 0, 8), **HERO))
    if want("hero_dark"):
        made.append(shoot(model.closed(splitring=True), "hero_dark.png", out_dir, focal=(xm + 6, 0, 8), bg=DARK_BG,
                          glow_strength=1.0, **HERO))
    if want("key_cluster_macro"):
        made.append(shoot(model.closed(), "key_cluster_macro.png", out_dir, direction=(0.30, -0.55, -1.0), up=(0, 0, -1),
                          focal=(p.X_main, 0, 0), view_angle=9.0, fill=0.62, ratio=0.62, crop=False,
                          fit_parts=model.keys(lit=False)))
    if want("bottom_flat"):
        made.append(shoot(model.closed(), "housing_bottom_flat.png", out_dir, direction=(0.0, 0.0, -1.0), up=(0, 1, 0),
                          focal=(xm, 0, 0), ratio=0.30, fill=0.94, view_angle=12, margin=0.02))
    if want("closed_lid"):
        made.append(shoot(model.closed(), "housing_closed_lid.png", out_dir, direction=(0.0, -0.18, 1.0), up=(0, 1, 0),
                          focal=(xm, 0, 16), ratio=0.30, fill=0.94, view_angle=12, margin=0.02))
    if want("closed_control_side"):
        made.append(shoot(model.closed(splitring=True), "housing_closed_control_side.png", out_dir,
                          direction=(-0.45, -1.0, 0.45), focal=(xm + 6, 0, 8)))
    if want("closed_rear"):
        made.append(shoot(model.closed(splitring=True), "housing_closed_rear.png", out_dir,
                          direction=(0.55, 1.0, 0.5), focal=(xm + 6, 0, 8)))
    if want("front"):
        made.append(shoot(model.closed(), "housing_front.png", out_dir, direction=(-1.0, -0.30, 0.20), focal=(0, 0, 8),
                          fill=0.88, ratio=0.75, view_angle=24))
    open_parts = ([model.part(n) for n in ("FlashKa_tray", "_ref_optic_holder", "_ref_optic_lens", "FlashKa_antenna_spacer",
                                           "_ref_mcpcb", "_ref_led", "_ref_laser", "_ref_pad", "_ref_pad2",
                                           "_ref_kbscrews") + CELL_REFS[:5] if model.cad.has(n)]
                  + model.keys(lit=False) + model.pcb.parts() + model.kb.parts() + model.extra_parts())
    if want("open_top"):
        dx = model.H.PCB_DX
        lab = [("S2 laser\ninterlock", (14 + dx, 7.5, 11.5), "T"),
               ("14500 cell (Vapcell F15) on two rails", (0.5 * (p.X_batt0 + p.X_batt1), 0,
                                                          model.H.cell_centre_z(p, p.cell_d) + p.cell_d / 2), "T"),
               ("lanyard slot", (p.X_lan, 0, 14.5), "T"),
               ("hold-down pads\n(under the lid bosses)", (26.5 + dx, 0, 13.0), "T"),
               ("head block: TIR optic +\nLED board, laser", (2.0, -4, p.H), "B"),
               ("4-layer main board", (20 + dx, -4, 10.3), "B"),
               ("RF-window zone\n(ESP32 antenna)", (35.5 + dx, -2, 10.8), "B")]
        made.append(shoot(open_parts, "housing_open_top.png", out_dir, direction=(0.0, -0.45, 1.0), up=(0, 1, 0),
                          focal=(xm, 0, 8), ratio=0.45, fill=0.92, labels=lab, margin=0.02))
    if want("open_iso"):
        made.append(shoot(open_parts, "housing_open_iso.png", out_dir, direction=(-0.5, -1.0, 0.95), focal=(xm, 0, 8)))
    if want("key_mould"):
        mp, ml = mould_parts(model, "resin")
        if mp:
            X, Y = p.mould_size
            made.append(shoot(mp, "key_mould.png", out_dir, direction=(0.18, -0.95, 1.25), focal=(X / 2 + 3.0, -6.0, -6.0),
                              fill=0.92, ratio=0.62, labels=ml, margin=0.02))
    if want("key_mould_aluminium"):
        mp, ml = mould_parts(model, "aluminium")
        if mp:
            X, Y = p.mould_size
            made.append(shoot(mp, "key_mould_aluminium.png", out_dir, direction=(0.18, -0.95, 1.25),
                              focal=(X / 2 + 3.0, -6.0, -6.0), fill=0.92, ratio=0.62, labels=ml, margin=0.02))
    if want("exploded"):
        made.append(shoot(exploded_parts(model), "housing_exploded.png", out_dir, direction=(-1.0, -0.95, 0.75),
                          focal=None, fill=0.90, labels=exploded_labels(model), margin=0.02))
    return made


EXPLODE = {   # part group -> Z offset (mm) of the exploded still
    "lidscrews": 50.0, "lid": 40.0, "rf_window": 30.0, "pads": 20.0, "pcb": 13.0, "cell": 21.0,
    "antenna_spacer": 6.0, "kbscrews": 7.0, "kb": 2.5, "keys": -12.0, "set_screw": 11.0,
    "optic": -22.0, "led_board": -12.0, "laser": -34.0, "sleeve": -52.0,         # X offsets (out of the bores)
}


def exploded_parts(model):
    e = EXPLODE
    m = model
    out = [m.part("FlashKa_tray"),
           m.part("FlashKa_lid", (0, 0, e["lid"])),
           m.part("FlashKa_rf_window", (0, 0, e["rf_window"])),
           m.part("_ref_lidscrews", (0, 0, e["lidscrews"])),
           m.part("_ref_pad", (0, 0, e["pads"])),
           m.part("FlashKa_antenna_spacer", (0, 0, e["antenna_spacer"])),
           ] + [m.part(n, (0, 0, e["cell"])) for n in CELL_REFS[:5] if m.cad.has(n)] + [
           m.part("_ref_optic_holder", (e["optic"], 0, 0)),
           m.part("_ref_optic_lens", (e["optic"], 0, 0)),
           m.part("_ref_led", (e["led_board"], 0, 0)),
           m.part("_ref_mcpcb", (e["led_board"], 0, 0)),
           m.part("_ref_laser", (e["laser"], 0, 0)),
           m.part("_ref_kbscrews", (0, 0, e["kbscrews"] + e["kb"]))]
    if m.cad.has("_ref_pad2"):
        out.append(m.part("_ref_pad2", (0, 0, e["pads"])))
    out += m.pcb.parts((0, 0, e["pcb"])) + m.kb_free.parts((0, 0, e["kb"]))
    out += m.keys(dz=e["keys"], lit=True)
    if m.cad.has("FlashKa_laser_sleeve"):
        out.append(m.part("FlashKa_laser_sleeve", (e["sleeve"], 0, 0)))
    lens, grub = m.extras
    out += [Part(lens[1], lens[2], (e["laser"], 0, 0), lens[0]), Part(grub[1], grub[2], (0, 0, EXPLODE["set_screw"]), grub[0])]
    return out


def exploded_labels(model):
    p, e = model.p, EXPLODE
    dx = model.H.PCB_DX
    zc = model.H.cell_centre_z(p, p.cell_d)
    return [("lid", (60, 6.0, p.H + e["lid"]), "R"),
            ("4 x M1.6 countersunk screws", (p.X_screw_back, p.screw_dy, p.H + e["lidscrews"]), "R"),
            ("RF window insert (POM-C)", (35 + dx, 0, p.H - p.pan_depth + e["rf_window"]), "L"),
            ("hold-down pads", (26 + dx, -1, 13.5 + e["pads"]), "L"),
            ("14500 cell with nickel strips", (0.5 * (p.X_batt0 + p.X_batt1), 0, zc + p.cell_d / 2 + e["cell"]), "R"),
            ("4-layer main board", (20 + dx, 0, 10 + e["pcb"]), "L"),
            ("antenna spacer (POM-C)", (36 + dx, 0, p.Z_pcb_top - 0.4 + e["antenna_spacer"]), "R"),
            ("2 x M1.6 x 2.5 screws", (p.kb_holes[0][0], p.kb_holes[0][1], 6.5 + e["kbscrews"] + e["kb"]), "R"),
            ("key board with 6 pogo pins", (31 + dx, -3, 5.2 + e["kb"]), "R"),
            ("main key (clear PMMA)", (p.X_main, 0, 2 + e["keys"]), "R"),
            ("side keys (rubber)", (p.X_prev, 0, 1.5 + e["keys"]), "R"),
            ("stiffener plates (stainless steel), glued in", (p.X_prev, 2.5, p.stiff_z0 + 0.3 + e["keys"]), "R"),
            ("TIR optic LEDiL LISA3\n(PMMA lens, black PC holder)",
             (p.opt_front_x + 3.0 + e["optic"], p.Y_w, p.Z_axis - p.opt_od / 2 + 0.1), "B"),
            ("LED + 10 mm DTP board", (p.x_led_board + p.mcpcb_t / 2 + e["led_board"], p.Y_w, p.Z_axis + p.mcpcb_d / 2 - 0.1), "L"),
            ("laser\nmodule", (p.las_recess + 6.0 + e["laser"], p.Y_l, p.Z_las - 3.0), "B"),
            ("laser set screw M1.6 x 5\n(from the top, under the lid)",
             (p.las_set[0], p.las_set[1], p.las_set_tip_z + p.las_set_len + e["set_screw"]), "L"),
            ("laser sleeve\n(option)", (p.las_recess + 7.0 + e["sleeve"], p.Y_l, p.Z_las - 3.0), "B")]


ASSET_SET = ("housing_closed_bottom.png", "key_cluster_macro.png", "housing_bottom_flat.png", "housing_closed_lid.png",
             "housing_closed_control_side.png", "housing_closed_rear.png", "housing_front.png", "housing_open_top.png",
             "housing_open_iso.png", "housing_exploded.png", "hero_dark.png", "key_mould.png", "key_mould_aluminium.png")


def transformed(pd, rot_x=0.0, rot_y=0.0, t=(0.0, 0.0, 0.0)):
    """polydata rotated about the X axis, then the Y axis (degrees, through the origin), then moved by t"""
    tf = vtk.vtkTransform()
    tf.PostMultiply()
    tf.RotateX(rot_x)
    tf.RotateY(rot_y)
    tf.Translate(*t)
    f = vtk.vtkTransformPolyDataFilter()
    f.SetInputData(pd)
    f.SetTransform(tf)
    f.Update()
    return f.GetOutput()


def mould_parts(model, version="resin"):
    """the open casting mould for the build guide: the cavity half with two freshly cast keys in their cavities (and
    the dowel pins of the aluminium version; the resin version has printed pins), the lid turned over beside it, two
    keys in front of it - one face up (chevron), one inner side up with the stiffener plate and the doubler glued in.
    None if key_mould.py has not written its STLs."""
    import key_mould as KM
    H, p, cad = model.H, model.p, model.cad
    resin = version == "resin"
    cn, ln = ("_ref_mould_resin_cavity", "_ref_mould_resin_lid") if resin else ("_ref_mould_cavity", "_ref_mould_lid")
    if not (cad.has(cn) and cad.has(ln)):
        return None, None
    X, Y = p.mould_size
    tc, tl = p.resin_t if resin else p.mould_t
    out = [cad.part(cn, mat="resin" if resin else "alu_blast")]
    lid = transformed(cad.pd(ln), rot_x=180.0, t=(X + 6.0, 0.0, -(tc - tl)))            # turned over, back on the table
    out.append(Part(lid, "resin" if resin else "alu_mill", (0, 0, 0), "mould_lid"))
    if not resin:
        bp = KM.bought_parts(p)
        for n in ("dowel1", "dowel2"):
            out.append(Part(polydata_from_shape(bp[n].val(), 0.01), "steel", (0, 0, 0), n))
    cxs = KM.cavity_x(p)
    for cx in cxs[:2]:
        out.append(Part(polydata_from_shape(KM.target_key(p, cx).val(), 0.005), "rubber", (0, 0, 0), "cast_key"))
    key = H.build_key_side(p, p.X_next, -1).translate((-p.X_next, -p.key_y, 0))
    y_front = -Y / 2 - 8.0
    t_up = (-9.0, y_front, -tc + p.Z_seat + p.flange_t)
    up = transformed(polydata_from_shape(key.val(), 0.005), rot_x=180.0, t=t_up)            # face up
    out.append(Part(up, "rubber", (0, 0, 0), "key_face_up"))
    cap = transformed(model.chevron_caps[0], rot_x=180.0)                                   # its glossy chevron top
    cap = transformed(cap, t=(t_up[0] - p.X_next, t_up[1] + p.key_y, t_up[2]))
    out.append(Part(cap, "rubber_gloss", (0, 0, 0), "chevron_cap"))
    dz = -tc - (p.side_face_z - p.chevron_h)                                                # inner side up, on its chevron
    out.append(Part(polydata_from_shape(key.val(), 0.005), "rubber", (5.0, y_front, dz), "key_inner_up"))
    plate, doub = H.build_key_stiffener(p, p.X_next, pieces=True)
    for nm, sld, mat in (("key_plate", plate, "steel"), ("key_doubler", doub, "metal")):
        sld = sld.translate((-p.X_next, -p.key_y, 0))
        out.append(Part(polydata_from_shape(sld.val(), 0.005), mat, (5.0, y_front, dz), nm))
    labels = [(("cavity half (SLA resin print): key face down,\nchevron groove in the floor" if resin else
                "cavity half (bead blasted): key face down,\npolished chevron groove in the floor"),
               (cxs[3] + 3.0, Y / 2 - 3.0, 0.0), "T"),
              ("lid, turned over: the plateaus\nform the plate recess", (X + 6.0 + cxs[3], 0.0, 0.47), "T"),
              ("freshly cast keys", (cxs[0], 0.0, 0.0), "T"),
              ("key face up", (-9.0, y_front, -tc + p.Z_seat + p.flange_t - p.side_face_z + p.chevron_h), "B"),
              ("plate + doubler\nglued in", (5.0, y_front + 2.0, dz + p.side_nub_z), "B")]
    return out, labels


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cad_dir", nargs="?", default=os.path.join(HERE, "..", "..", "cad"))
    ap.add_argument("out_dir", nargs="?", default=os.path.join(HERE, "..", "..", "renders"))
    ap.add_argument("--pcb-step", default=None)
    ap.add_argument("--kb-step", default=None)
    ap.add_argument("--kicad-pcb", default=None)
    ap.add_argument("--kb-kicad-pcb", default=None)
    ap.add_argument("--only", default=None)
    ap.add_argument("--assets", default=None)
    a = ap.parse_args()
    only = set(a.only.split(",")) if a.only else None
    model = Model(a.cad_dir, a.pcb_step, a.kb_step, a.kicad_pcb, kb_kicad_pcb=a.kb_kicad_pcb)
    made = render_all(model, a.out_dir, only)
    if a.assets:
        os.makedirs(a.assets, exist_ok=True)
        for pth in made:
            if os.path.basename(pth) in ASSET_SET:
                shutil.copyfile(pth, os.path.join(a.assets, os.path.basename(pth)))
        print("copied %d pictures to %s" % (len(made), a.assets))


if __name__ == "__main__":
    main()
