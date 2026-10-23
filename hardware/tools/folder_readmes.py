#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""README pages for the cad/ and assets/ folders of the reference designs, so that a reader who opens one of these
folders on GitHub sees what each file is instead of a bare file list.

    python3 hardware/tools/folder_readmes.py

writes, for EDCO v0.1, EDCO v0.2, EDCO Mini, EDCO Prism and FlashKa v0.7:
    hardware/<design>/cad/README.md      drawings (with a picture of each sheet), 3D models (STEP), data files
    hardware/<design>/assets/README.md   every render and animation, with the caption the design page gives it

The pages are made from the files that are in the folders, so run this again after adding or renaming a file.
Captions come from the picture's alt text on the design page; a file the page does not use gets a caption made
from its name.
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
HW = os.path.dirname(HERE)
SEP = " › "
DESIGNS = [  # folder, name, render script, drawings note
    ("edco-v01", "EDCO v0.1", "tools/housing/edco_render.py", None),
    ("edco-v02", "EDCO v0.2", "tools/housing/edco_v02_render.py", None),
    ("edco-mini", "EDCO Mini", "tools/housing/edco_mini_render.py",
     "The M body is drawn: the plain body is the same without the two magnet pockets (item 9 on the sheet)."),
    ("edco-prism", "EDCO Prism", "tools/housing/edco_prism_render.py",
     "The M body is drawn: the plain body is the same without the two magnet pockets (item 9 on the sheet)."),
    ("flashka-keychain-v07", "FlashKa v0.7", "tools/housing/render.py", None),
]
FK_PARTS = {
    "FlashKa_tray": "tray: the lower part of the aluminium body (drawing FK-H-01)",
    "FlashKa_lid": "lid: the upper part of the aluminium body (FK-H-02)",
    "FlashKa_key_main": "main key, clear PMMA (FK-H-03)",
    "FlashKa_key_side": "side key, cast rubber (FK-H-04)",
    "FlashKa_key_side_with_plate": "side key with its stiffener plate",
    "FlashKa_key_stiffener": "stiffener glued into the side key",
    "FlashKa_rf_window": "RF window insert, POM-C (FK-H-05)",
    "FlashKa_antenna_spacer": "antenna spacer, POM-C (FK-H-05)",
    "FlashKa_laser_sleeve": "laser sleeve, POM-C (FK-H-05)",
    "FlashKa_pmma_kit": "machining kit: three main keys on tabs in a frame (FK-H-06)",
    "FlashKa_pom_kit": "machining kit: one set of POM-C parts and a spare insert (FK-H-07)",
    "FlashKa_key_mould": "casting mould for the side keys, aluminium version (FK-H-08)",
    "FlashKa_key_mould_cavity": "aluminium mould: cavity half",
    "FlashKa_key_mould_lid": "aluminium mould: lid half",
    "FlashKa_key_mould_resin": "casting mould for the side keys, printed resin version (FK-H-08)",
    "FlashKa_key_mould_resin_cavity": "resin mould: cavity half",
    "FlashKa_key_mould_resin_lid": "resin mould: lid half",
    "FlashKa_main_pcb": "3D model of the main board",
    "FlashKa_keys_pcb": "3D model of the key board",
    "FlashKa_assembly_reference": "every part in place",
}
FK_DRAWINGS = {
    "FlashKa_tray_drawing": "FK-H-01 tray, sheet 1: inside (holes, threads, fits, key-board bosses)",
    "FlashKa_tray_drawing_sheet2": "FK-H-01 tray, sheet 2: outside (facets, panels, grooves, key bezel)",
    "FlashKa_lid_drawing": "FK-H-02 lid",
    "FlashKa_key_main_drawing": "FK-H-03 main key (clear PMMA, polished, frosted ring)",
    "FlashKa_key_side_drawing": "FK-H-04 side key (cast rubber with a glued-in stiffener)",
    "FlashKa_pom_parts_drawing": "FK-H-05 POM-C parts (RF window insert, antenna spacer, laser sleeve)",
    "FlashKa_pmma_kit_drawing": "FK-H-06 machining kit: three PMMA main keys",
    "FlashKa_pom_kit_drawing": "FK-H-07 machining kit: one set of POM-C parts",
    "FlashKa_key_mould_drawing": "FK-H-08 casting mould for the side keys",
}
FK_DATA = {
    "housing_interface.json": "the contract between the housing and the boards: sizes, positions, walls",
    "pcb_placement.json": "where the main board's parts sit, as the housing checks them",
    "pcb_placement_keys.json": "the same for the key board",
    "drawings_dimension_table.txt": "every number on the drawings against its parameter, and the ray-probe cross-check",
    "key_mould_checks.txt": "the checks of the casting moulds",
}


def humanize(fn):
    s = os.path.splitext(fn)[0].replace("_", " ").replace("-", " ")
    return s[0].upper() + s[1:]


def alts(design_dir):
    """picture path (relative to the design folder) -> alt text, from the design page"""
    out = {}
    s = open(os.path.join(design_dir, "README.md")).read()
    for alt, path in re.findall(r"!\[([^\]]+)\]\(([^)\s]+)\)", s):
        out.setdefault(path, alt)
    return out


def crumbs(name, depth_to_root, last):
    up = "../" * depth_to_root
    return SEP.join(["[LuxLibre](%sREADME.md)" % up, "[Lights](%shardware/README.md)" % up,
                     "[%s](../README.md)" % name, last])


def step_desc(base, name):
    if base in FK_PARTS:
        return FK_PARTS[base]
    m = "M version (with the magnet pockets)" if re.search(r"(PrismM|-1[46]M)_", base + "_") else None
    for key, txt in (("_assembly", "every part in place, with stand-ins for the boards and the socket"),
                     ("_body", "body"), ("_bezel_ring", "bezel ring (screws onto the body's thread)"),
                     ("_bezel", "bezel (screws onto the body's thread)"), ("_insert", "head insert (holds the LED board and the optic)"),
                     ("_head", "head (holds the LED board and the optic)"), ("_collar", "twist collar over the USB-C port")):
        if key in base:
            size = re.search(r"(EDCO-1[48]|Mini-1[46])", base)
            pre = (size.group(1).replace("EDCO-", "EDCO-") + ": ") if size else ""
            return pre + txt + ("; " + m if m else "")
    return ""


def cad_readme(folder, name, note):
    d = os.path.join(HW, folder, "cad")
    files = sorted(os.listdir(d))
    bases = {}
    for f in files:
        if f == "README.md":
            continue
        b, e = os.path.splitext(f)
        bases.setdefault(b, []).append(e)
    L = ["<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->", crumbs(name, 3, "Drawings and CAD"), "",
         "# %s: drawings and CAD" % name, "",
         "The files of the %s housing, made from the design scripts in [../tools/](../tools/) (nothing is drawn by "
         "hand). STEP files open in FreeCAD, Fusion, Onshape or any CAD program; DXF in LibreCAD, QCAD or any CAD "
         "program; PDF and PNG are for reading. The design page explains every part: [%s](../README.md)." % (name, name), ""]
    drawings = [b for b in bases if b.endswith("_drawing") or b.endswith("_drawing_sheet2")]
    if drawings:
        L += ["## Drawings", ""]
        if note:
            L += [note, ""]
        for b in sorted(drawings, key=lambda x: FK_DRAWINGS.get(x, x)):
            desc = FK_DRAWINGS.get(b) or ("%s, A3 at 2:1" % humanize(b).replace(" drawing", " drawing:")
                                          .replace("EDCO ", "EDCO ").rstrip(":"))
            links = ", ".join("[%s](%s%s)" % (e[1:].upper(), b, e) for e in sorted(bases[b], key=[".pdf", ".dxf", ".png"].index))
            L += ["**%s** (%s)" % (desc, links), ""]
            if ".png" in bases[b]:
                target = b + (".pdf" if ".pdf" in bases[b] else ".png")
                L += ["[![%s](%s.png)](%s)" % (desc, b, target), ""]
    steps = [b for b in bases if any(e in (".step", ".stl") for e in bases[b]) and not b.startswith("_ref_")
             and b not in drawings]
    if steps:
        L += ["## 3D models", "", "| File | What it is |", "|---|---|"]
        for b in sorted(steps):
            links = ", ".join("[%s](%s%s)" % (e[1:].upper(), b, e) for e in sorted(bases[b]))
            L.append("| `%s` (%s) | %s |" % (b, links, step_desc(b, name)))
        L.append("")
    refs = [b for b in bases if b.startswith("_ref_")]
    if refs:
        L += ["`_ref_*` files (%d): simplified stand-ins (cell, boards, screws, optic, LEDs, pogo pins, moulds) for "
              "the renders and the fit checks. They are not parts to order." % len(refs), ""]
    data = [f for f in files if os.path.splitext(f)[1] in (".json", ".txt")]
    if data:
        L += ["## Data", "", "| File | What it is |", "|---|---|"]
        for f in data:
            desc = FK_DATA.get(f) or ("sizes, walls, fits, masses and the interference check (written by the CAD "
                                      "script, read by the checks)" if f.endswith("_interface.json") else "")
            L.append("| [`%s`](%s) | %s |" % (f, f, desc))
        L.append("")
    if folder.startswith("edco"):
        L += ["The drawings are made by [hardware/tools/edco_drawings.py](../../tools/edco_drawings.py) and checked "
              "against the solids ([report](../../tools/edco_drawings_check.txt)).", ""]
    else:
        L += ["The drawings are made by [tools/housing/drawings.py](../tools/housing/drawings.py); the parts to order "
              "are in [order_files/](../order_files/README.txt).", ""]
    open(os.path.join(d, "README.md"), "w").write("\n".join(L).rstrip("\n") + "\n")
    print("wrote", os.path.relpath(os.path.join(d, "README.md"), HW))


def assets_readme(folder, name, script, sub=""):
    base = os.path.join(HW, folder, "assets", sub)
    A = alts(os.path.join(HW, folder))
    files = sorted(f for f in os.listdir(base) if os.path.splitext(f)[1] in (".png", ".gif"))
    gifs = [f for f in files if f.endswith(".gif")]
    pngs = [f for f in files if f.endswith(".png")]
    rel = "assets/" + (sub + "/" if sub else "")
    depth = 4 if sub else 3

    def cap(f):
        a = A.get(rel + f)
        if a:
            a = re.sub(r"\s*\(render\)\s*$", "", a)
            return re.sub(r"\bRovyVon [A-Z][a-z]+ (?=[A-Z]\d)", "RovyVon ", a)   # model code only, no line name
        return humanize(f)

    def grid(items):
        out = []
        for i in range(0, len(items), 2):
            row = items[i:i + 2]
            out.append("| " + " | ".join("![%s](%s)" % (cap(f), f) for f in row) + (" | |" if len(row) == 1 else " |"))
            if i == 0:
                out.append("|---|---|")
            out.append("| " + " | ".join("%s<br>`%s`" % (cap(f), f) for f in row) + (" | |" if len(row) == 1 else " |"))
        return out
    up = "../" * depth
    L = ["<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->",
         SEP.join(["[LuxLibre](%sREADME.md)" % up, "[Lights](%shardware/README.md)" % up,
                   "[%s](%sREADME.md)" % (name, "../" * (2 if sub else 1)), "Pictures"]), "",
         "# %s: pictures" % name, "",
         "Renders and animations made from the design files. Nothing here is a photo: the light has not been built "
         "yet. The renders are made by [%s](%s%s)%s." % (
             os.path.basename(script), "../" * (2 if sub else 1), script,
             "" if folder.startswith("flashka") else ", the animations by "
             "[hardware/tools/edco_anim.py](../../tools/edco_anim.py)"), ""]
    if gifs:
        L += ["## Animations", ""] + grid(gifs) + [""]
    if pngs:
        L += ["## Renders", ""] + grid(pngs) + [""]
    path = os.path.join(base, "README.md")
    open(path, "w").write("\n".join(L).rstrip("\n") + "\n")
    print("wrote", os.path.relpath(path, HW))


def main():
    for folder, name, script, note in DESIGNS:
        cad_readme(folder, name, note)
        if folder == "flashka-keychain-v07":
            assets_readme(folder, name, script, sub="v07")
            open(os.path.join(HW, folder, "assets", "README.md"), "w").write(
                "<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->\n" + SEP.join(
                    ["[LuxLibre](../../../README.md)", "[Lights](../../README.md)", "[%s](../README.md)" % name,
                     "Pictures"]) + "\n\n# %s: pictures\n\nThe renders, animations and comparison pictures of v0.7 are "
                "in [v07/](v07/README.md).\n" % name)
        else:
            assets_readme(folder, name, script)


if __name__ == "__main__":
    main()
