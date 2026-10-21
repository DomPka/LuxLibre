#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Project footprint library "FlashKa" (KiCad 6 format), v0.6.

Footprints marked VERIFY were drawn from the best available public data
without the manufacturer drawing; in EasyEDA Pro replace them with the
LCSC-library footprint of the same C-number before ordering.
"""
import os
import sys

HDR = '(footprint "{name}" (version 20211014) (generator flashka) (layer "F.Cu")\n' \
      '  (tedit 6720A000)\n  (descr "{descr}")\n  (tags "{tags}")\n  (attr {attr})\n'


def txt(kind, text, x, y, layer, size=0.8):
    return (f'  (fp_text {kind} "{text}" (at {x} {y}) (layer "{layer}")\n'
            f'    (effects (font (size {size} {size}) (thickness {size * 0.15:.3f})))\n  )\n')


def rect(x0, y0, x1, y1, layer, w=0.05):
    return (f'  (fp_line (start {x0} {y0}) (end {x1} {y0}) (layer "{layer}") (width {w}))\n'
            f'  (fp_line (start {x1} {y0}) (end {x1} {y1}) (layer "{layer}") (width {w}))\n'
            f'  (fp_line (start {x1} {y1}) (end {x0} {y1}) (layer "{layer}") (width {w}))\n'
            f'  (fp_line (start {x0} {y1}) (end {x0} {y0}) (layer "{layer}") (width {w}))\n')


def line(x0, y0, x1, y1, layer, w=0.12):
    return f'  (fp_line (start {x0} {y0}) (end {x1} {y1}) (layer "{layer}") (width {w}))\n'


def circle(x, y, r, layer, w=0.12):
    return f'  (fp_circle (center {x} {y}) (end {x + r} {y}) (layer "{layer}") (width {w}))\n'


def smd(num, x, y, w, h, shape="roundrect", rr=0.2, layers='"F.Cu" "F.Paste" "F.Mask"'):
    extra = f" (roundrect_rratio {rr})" if shape == "roundrect" else ""
    return f'  (pad "{num}" smd {shape} (at {x} {y}) (size {w} {h}) (layers {layers}){extra})\n'


def tht(num, x, y, d, drill, shape="circle"):
    return (f'  (pad "{num}" thru_hole {shape} (at {x} {y}) (size {d} {d}) (drill {drill}) '
            f'(layers *.Cu *.Mask))\n')


def npth(x, y, d):
    return (f'  (pad "" np_thru_hole circle (at {x} {y}) (size {d} {d}) (drill {d}) '
            f'(layers *.Cu *.Mask))\n')


def fp(name, descr, tags, body, attr="smd"):
    return HDR.format(name=name, descr=descr, tags=tags, attr=attr) + body + ")\n"


def footprints():
    out = {}
    # --- wire pads (plated through holes; wire from one side, solder on the other)
    for pitch, drill, pad, nm in ((3.0, 1.0, 1.8, "WirePad_THT_2_P3.0mm_D1.0"),
                                  (2.54, 0.8, 1.5, "WirePad_THT_2_P2.54mm_D0.8")):
        h = pitch / 2
        b = txt("reference", "REF**", 0, -1.9, "F.SilkS") + txt("value", nm, 0, 1.9, "F.Fab")
        b += rect(-h - pad / 2 - 0.25, -pad / 2 - 0.25, h + pad / 2 + 0.25, pad / 2 + 0.25, "F.CrtYd")
        b += tht("1", -h, 0, pad, drill, "rect") + tht("2", h, 0, pad, drill)
        b += txt("user", "1", -h, -1.9 + 0.0001, "F.Fab", 0.5)
        out[nm] = fp(nm, f"2 wire pads, pitch {pitch} mm, drill {drill} mm (pad 1 square)",
                     "wire pad", b, attr="through_hole")
    # --- SMD wire pads, 3.0 mm pitch, for 24 AWG (LED)
    nm = "WirePad_SMD_2_P3.0mm"
    b = txt("reference", "REF**", 0, -2.0, "F.SilkS") + txt("value", nm, 0, 2.0, "F.Fab")
    # v0.6: courtyard 0.15 mm beyond the pads along the pad row too (was 0.5; after the
    # gen_pcb courtyard policy 0.15 all round): the cell pads share the rear corner with Q5
    b += rect(-2.75, -1.5, 2.75, 1.5, "F.CrtYd")
    b += smd("1", -1.5, 0, 2.0, 2.5) + smd("2", 1.5, 0, 2.0, 2.5)
    b += txt("user", "+", -1.5, -1.95, "F.SilkS", 0.8) + txt("user", "-", 1.5, -1.95, "F.SilkS", 0.8)
    out[nm] = fp(nm, "2 SMD wire pads 2.0 x 2.5 mm, pitch 3.0 mm (pad 1 = +)", "wire pad", b)
    # --- SMD wire pads, 3.0 mm pitch, narrow pads (laser J5): the 1.6 mm gap between the pads
    #     takes the 0.9 mm positioning peg of the slide switch S2 (hole edge >= 0.2 mm from copper)
    nm = "WirePad_SMD_2_P3.0mm_N"
    b = txt("reference", "REF**", 0, -1.8, "F.SilkS") + txt("value", nm, 0, 1.8, "F.Fab")
    b += rect(-2.45, -1.25, 2.45, 1.25, "F.CrtYd")
    b += smd("1", -1.5, 0, 1.4, 2.0) + smd("2", 1.5, 0, 1.4, 2.0)
    b += txt("user", "+", -1.5, -1.6, "F.SilkS", 0.7) + txt("user", "-", 1.5, -1.6, "F.SilkS", 0.7)
    out[nm] = fp(nm, "2 SMD wire pads 1.4 x 2.0 mm, pitch 3.0 mm (pad 1 = +), gap 1.6 mm", "wire pad", b)
    # --- SMD wire pads 2.54 mm (NTC from below the PCB, laser)
    nm = "WirePad_SMD_2_P2.54mm"
    b = txt("reference", "REF**", 0, -1.8, "F.SilkS") + txt("value", nm, 0, 1.8, "F.Fab")
    b += rect(-2.6, -1.25, 2.6, 1.25, "F.CrtYd")
    b += smd("1", -1.27, 0, 1.6, 2.0) + smd("2", 1.27, 0, 1.6, 2.0)
    b += txt("user", "+", -1.27, -1.6, "F.SilkS", 0.7) + txt("user", "-", 1.27, -1.6, "F.SilkS", 0.7)
    out[nm] = fp(nm, "2 SMD wire pads 1.6 x 2.0 mm, pitch 2.54 mm (pad 1 = +)", "wire pad", b)
    # --- UPDI pogo pads (round, 2.54 mm)
    nm = "Pogo_Pads_3_P2.54mm"
    b = txt("reference", "REF**", 0, -1.8, "F.SilkS") + txt("value", nm, 0, 1.8, "F.Fab")
    b += rect(-3.4, -1.2, 3.4, 1.2, "F.CrtYd")
    for i, x in enumerate((-2.54, 0, 2.54)):
        b += smd(str(i + 1), x, 0, 1.6, 1.6, shape="circle")
    b += line(-3.6, 0.9, -3.6, -0.9, "F.SilkS")
    out[nm] = fp(nm, "3 pogo-pin pads 1.6 mm, pitch 2.54 mm (1 VDD, 2 UPDI, 3 GND)", "UPDI pogo", b)
    # --- 1 uH FXL0530 molded inductor (5.4 x 5.2 x 3.0)  VERIFY
    nm = "L_FXL0530"
    b = txt("reference", "REF**", 0, -3.6, "F.SilkS") + txt("value", nm, 0, 3.6, "F.Fab")
    b += rect(-2.7, -2.6, 2.7, 2.6, "F.Fab", 0.1)
    b += rect(-3.25, -2.85, 3.25, 2.85, "F.CrtYd")
    b += smd("1", -2.15, 0, 1.8, 4.2, rr=0.1) + smd("2", 2.15, 0, 1.8, 4.2, rr=0.1)
    b += line(-1.1, -2.75, 1.1, -2.75, "F.SilkS") + line(-1.1, 2.75, 1.1, 2.75, "F.SilkS")
    out[nm] = fp(nm, "cjiang FXL0530 5.4x5.2 mm power inductor - VERIFY land pattern "
                     "against LCSC C475517 (replace with library footprint in EasyEDA)",
                 "inductor FXL0530", b)
    # --- NH-B1010RGBT-HF RGB LED 1.0 x 1.0 mm, common anode  VERIFY
    nm = "LED_RGB_1010_NH-B1010RGBT"
    b = txt("reference", "REF**", 0, -1.3, "F.SilkS", 0.6) + txt("value", nm, 0, 1.3, "F.Fab", 0.5)
    b += rect(-0.5, -0.5, 0.5, 0.5, "F.Fab", 0.05)
    b += rect(-0.85, -0.85, 0.85, 0.85, "F.CrtYd")
    p = 0.3
    b += smd("1", -p, -p, 0.32, 0.32, rr=0.1) + smd("2", p, -p, 0.32, 0.32, rr=0.1)
    b += smd("3", p, p, 0.32, 0.32, rr=0.1) + smd("4", -p, p, 0.32, 0.32, rr=0.1)
    b += circle(-0.95, -0.95, 0.06, "F.SilkS", 0.12)
    out[nm] = fp(nm, "NationStar NH-B1010RGBT-HF 1.0x1.0 mm RGB LED, 1 = common anode, "
                     "2 R, 3 G, 4 B - VERIFY pad map against LCSC C2874113",
                 "LED RGB 1010", b)
    # --- Luminus SST-40 (5.0 x 5.0), MCPCB use  VERIFY polarity
    nm = "LED_Luminus_SST-40"
    b = txt("reference", "REF**", 0, -3.4, "F.SilkS") + txt("value", nm, 0, 3.4, "F.Fab")
    b += rect(-2.5, -2.5, 2.5, 2.5, "F.Fab", 0.1)
    b += rect(-2.9, -2.9, 2.9, 2.9, "F.CrtYd")
    b += smd("1", -2.05, 0, 0.5, 4.8, rr=0.1)      # anode
    b += smd("3", 0, 0, 2.8, 4.8, rr=0.05)         # thermal pad (neutral)
    b += smd("2", 2.05, 0, 0.5, 4.8, rr=0.1)       # cathode
    b += txt("user", "+", -2.05, -3.0, "F.SilkS", 0.7)
    out[nm] = fp(nm, "Luminus SST-40 5050: anode 0.5x4.8, thermal 2.8x4.8 (neutral), "
                     "cathode 0.5x4.8, 0.4 gaps - VERIFY polarity with DWG-003015",
                 "LED SST-40", b)
    # --- wire hole + pad for the metal-core LED board (wire through an insulated
    #     hole, soldered to the pad on the LED side). Pad towards the LED.
    nm = "MCPCB_WireHole_Pad_1.5"
    b = txt("reference", "REF**", 1.6, 0, "F.SilkS", 0.5) + txt("value", nm, 0, 3.0, "F.Fab", 0.4)
    b += npth(0, 0, 1.5)
    b += smd("1", 0, 1.45, 1.2, 0.9, rr=0.25)
    b += rect(-0.95, -0.95, 0.95, 2.1, "F.CrtYd")
    out[nm] = fp(nm, "LED wire (24-26 AWG) through a 1.5 mm insulated hole, pad 1.45 mm "
                     "towards the LED", "MCPCB wire", b)
    nm = "MCPCB_WireHole_Pad_0.8"
    b = txt("reference", "REF**", 1.3, 0, "F.SilkS", 0.5) + txt("value", nm, 0, -2.4, "F.Fab", 0.4)
    b += npth(0, 0, 0.8)
    b += smd("1", 0, -1.2, 0.9, 0.8, rr=0.25)
    b += rect(-0.65, -1.8, 0.65, 0.65, "F.CrtYd")
    out[nm] = fp(nm, "NTC wire (30 AWG) through a 0.8 mm insulated hole, pad 1.2 mm "
                     "towards the LED", "MCPCB wire", b)
    # --- M1.6 mounting hole for the MCPCB
    nm = "MountingHole_1.8mm_M1.6"
    b = txt("reference", "REF**", 0, -2.2, "F.SilkS", 0.6) + txt("value", nm, 0, 2.2, "F.Fab", 0.5)
    b += npth(0, 0, 1.8) + circle(0, 0, 1.6, "F.CrtYd", 0.05) + circle(0, 0, 1.5, "Cmts.User", 0.1)
    out[nm] = fp(nm, "M1.6 clearance hole, screw head 3.0 mm", "mounting hole", b,
                 attr="exclude_from_pos_files exclude_from_bom")

    # --- ESP32-C3-MINI-1 (13.2 x 16.6 mm, 53 pads). Land pattern of the MINI-1
    #     family (identical to the ESP32-C6-MINI-1 footprint of the KiCad 10
    #     library); antenna area at y < -5.6 (beyond the PCB edge in FlashKa).
    nm = "ESP32-C3-MINI-1"
    b = txt("reference", "REF**", 0, 6.6, "F.SilkS") + txt("value", nm, 0, -8.3, "F.Fab")
    b += rect(-6.6, -11.0, 6.6, 5.6, "F.Fab", 0.1)
    b += line(-6.6, -5.6, 6.6, -5.6, "F.Fab", 0.1)
    b += txt("user", "ANTENNA", 0, -9.0, "F.Fab", 0.8)
    b += rect(-6.85, -11.25, 6.85, 5.85, "F.CrtYd")
    b += line(-6.75, 5.75, 6.75, 5.75, "F.SilkS") + line(-6.75, 5.75, -6.75, -5.75, "F.SilkS")
    b += line(6.75, 5.75, 6.75, -5.75, "F.SilkS")
    b += circle(-7.1, -4.0, 0.15, "F.SilkS", 0.2)
    for i in range(11):                     # pins 1..11, left column, top -> bottom
        b += smd(str(1 + i), -5.9, round(-4.0 + 0.8 * i, 3), 0.8, 0.4, shape="rect")
    for i in range(13):                     # pins 12..24, bottom row, left -> right
        b += smd(str(12 + i), round(-4.8 + 0.8 * i, 3), 4.9, 0.4, 0.8, shape="rect")
    for i in range(11):                     # pins 25..35, right column, bottom -> top
        b += smd(str(25 + i), 5.9, round(4.0 - 0.8 * i, 3), 0.8, 0.4, shape="rect")
    for i in range(13):                     # pins 36..48, top row, right -> left
        b += smd(str(36 + i), round(4.8 - 0.8 * i, 3), -4.9, 0.4, 0.8, shape="rect")
    # pin 49 (GND): a 3 x 3 grid of 1.45 mm pads (copper, mask and paste) on
    # one 5.4 x 5.4 copper pad without mask opening; the thermal vias sit in
    # the covered webs between the openings (tented, no solder wicking)
    b += smd("49", 0, 0, 5.4, 5.4, shape="rect", layers='"F.Cu"')
    for gx in (-1.975, 0.0, 1.975):
        for gy in (-1.975, 0.0, 1.975):
            b += smd("49", gx, gy, 1.45, 1.45, shape="rect")
    for (num, x, y) in (("50", 5.95, -4.95), ("51", 5.95, 4.95), ("52", -5.95, 4.95),
                        ("53", -5.95, -4.95)):
        b += smd(num, x, y, 0.7, 0.7, shape="rect")
    out[nm] = fp(nm, "Espressif ESP32-C3-MINI-1(-N4/-H4X) 13.2 x 16.6 mm, 53 pads "
                     "(MINI-1 family land pattern); antenna at -Y beyond the board edge",
                 "ESP32-C3 BLE module", b)
    # --- LED wire pads on both sides at the same spot: pad 1 top (LED+, from the
    #     upper wire hole), pad 2 bottom (LED-, from the lower wire hole)
    nm = "WirePad_SMD_TopBottom_1.6x1.8"
    b = txt("reference", "REF**", 0, -1.6, "F.SilkS", 0.6) + txt("value", nm, 0, 1.6, "F.Fab", 0.4)
    b += rect(-0.95, -1.05, 0.95, 1.05, "F.CrtYd") + rect(-0.95, -1.05, 0.95, 1.05, "B.CrtYd")
    b += smd("1", 0, 0, 1.6, 1.8, rr=0.15)
    b += smd("2", 0, 0, 1.6, 1.8, rr=0.15, layers='"B.Cu" "B.Mask"')
    b += txt("user", "LED+", 0, -1.35, "F.SilkS", 0.5)
    b += txt("user", "LED-", 0, -1.35, "B.SilkS", 0.5).replace("(thickness 0.075)))", "(thickness 0.075)) (justify mirror))")
    out[nm] = fp(nm, "LED wire pads: 1 = LED+ on F.Cu, 2 = LED- on B.Cu (same position)",
                 "wire pad", b)
    return out


def write(outdir):
    os.makedirs(outdir, exist_ok=True)
    for nm, s in footprints().items():
        with open(os.path.join(outdir, nm + ".kicad_mod"), "w") as f:
            f.write(s)
    return list(footprints())


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else "kicad/FlashKa.pretty"
    print(write(d))
