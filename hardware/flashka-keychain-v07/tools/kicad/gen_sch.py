#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Generate the FlashKa Keychain v0.7 schematic (KiCad 6 format, version 20211123, one A3 page)
from flashka_parts.py: the whole light on one sheet, blocks 1-6 = main PCB, block 7 = key
board (its own PCB; pogo pins P1-P6 press on the main board's target pads J6).

Every pin gets a short wire stub and a local net label ("nets connect by label"), so a net
that crosses from the main PCB to the key board (GND, 3V3, RGB_R, RGB_G, RGB_B, BTN) keeps its
v0.6 name.  The file imports into EasyEDA Pro (Import > KiCad) and opens in KiCad 6+.
"""
import copy
import math
import os
import sys
import uuid

from kiutils.schematic import Schematic
from kiutils.symbol import Symbol, SymbolLib, SymbolPin
from kiutils.items.common import (Effects, Fill, Font, Justify, PageSettings,
                                  Position, Property, Stroke, TitleBlock)
from kiutils.items.schitems import (Connection, LocalLabel, NoConnect,
                                    PolyLine, SchematicSymbol, SymbolInstance,
                                    Text)
from kiutils.items.syitems import SyRect

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from flashka_parts import BLOCKS, COMPONENTS, FRAMES  # noqa: E402

KLIB = "/usr/share/kicad/symbols"
G = 2.54


NS = uuid.UUID("6f1d3c2e-8a4b-4c55-9d1e-a0a0a0a0a004")


_UID = [0]


def uid():
    """Item UUIDs from a counter (reset per build), so the schematic file is the same on every run."""
    _UID[0] += 1
    return str(uuid.uuid5(NS, f"FlashKa_main/item/{_UID[0]}"))


def sym_uuid(ref):
    """Deterministic symbol UUID so that the PCB can link footprints to symbols."""
    return str(uuid.uuid5(NS, "FlashKa_main/" + ref))


def kt(t):
    """KiCad text: escape newlines, avoid the overbar character."""
    return t.replace("~", "approx. ").replace("\n", "\\n")


def eff(size=1.27, hide=False, justify=None, bold=False):
    e = Effects(font=Font(height=size, width=size, bold=bold), hide=hide)
    if justify:
        e.justify = Justify(horizontally=justify)
    return e


# --------------------------------------------------------------------------
# custom symbols (library "FlashKa")
# --------------------------------------------------------------------------
def ic_symbol(name, left, right, ref="U", width=15.24, desc="", stacked=()):
    """Rectangle IC. left/right = [(number, name, etype), ...] top->bottom.
    stacked = [(number, name, etype, visible_pin_number), ...]: extra pins
    placed hidden on top of a visible pin (the module's many GND / NC pads)."""
    n = max(len(left), len(right))
    top = (n + 1) * G / 2
    top = round(top / 1.27) * 1.27
    sym = Symbol(libraryNickname="FlashKa", entryName=name, inBom=True,
                 onBoard=True, pinNamesOffset=0.508)
    sym.properties = [
        Property(key="Reference", value=ref, id=0,
                 position=Position(0, top + 1.905, 0), effects=eff()),
        Property(key="Value", value=name, id=1,
                 position=Position(0, -top - 1.905, 0), effects=eff()),
        Property(key="Footprint", value="", id=2, position=Position(0, 0, 0),
                 effects=eff(hide=True)),
        Property(key="Datasheet", value="", id=3, position=Position(0, 0, 0),
                 effects=eff(hide=True)),
        Property(key="ki_description", value=desc, id=4,
                 position=Position(0, 0, 0), effects=eff(hide=True)),
    ]
    body = Symbol(entryName=name, unitId=0, styleId=1)
    body.graphicItems.append(SyRect(
        start=Position(-width / 2, top), end=Position(width / 2, -top),
        stroke=Stroke(width=0.254), fill=Fill(type="background")))
    pins = Symbol(entryName=name, unitId=1, styleId=1)
    xl = -width / 2 - G
    xr = width / 2 + G
    for i, (num, pname, et) in enumerate(left):
        y = round((top - G * (i + 1)) / 1.27) * 1.27
        pins.pins.append(SymbolPin(electricalType=et, position=Position(xl, y, 0),
                                   length=G, name=pname, number=str(num),
                                   nameEffects=eff(), numberEffects=eff()))
    for i, (num, pname, et) in enumerate(right):
        y = round((top - G * (i + 1)) / 1.27) * 1.27
        pins.pins.append(SymbolPin(electricalType=et, position=Position(xr, y, 180),
                                   length=G, name=pname, number=str(num),
                                   nameEffects=eff(), numberEffects=eff()))
    at = {p.number: p for p in pins.pins}
    for (num, pname, et, on) in stacked:
        v = at[str(on)]
        pins.pins.append(SymbolPin(electricalType=et, position=Position(v.position.X, v.position.Y,
                                                                          v.position.angle),
                                   length=G, name=pname, number=str(num), hide=True,
                                   nameEffects=eff(), numberEffects=eff()))
    sym.units = [body, pins]
    return sym


def flashka_symbols():
    P, I, O, W, B, N = "passive", "input", "output", "power_in", "bidirectional", "no_connect"
    PO = "power_out"
    gnd = ["2", "11", "14"] + [str(n) for n in range(36, 54)]
    nc = ["4", "7", "9", "10", "15", "17", "24", "25", "28", "29", "32", "33", "34", "35"]
    return {
        "TP4057": ic_symbol("TP4057", [
            (4, "VCC", W), (6, "PROG", P), (2, "GND", W)], [
            (3, "BAT", P), (1, "~{CHRG}", O), (5, "~{STDBY}", O)],
            desc="500 mA Li-ion linear charger, SOT-23-6"),
        "RT9080": ic_symbol("RT9080", [
            (1, "VIN", W), (3, "EN", I), (2, "GND", W)], [
            (5, "VOUT", PO), (4, "NC", N)],
            desc="600 mA LDO, 2 uA quiescent, TSOT-23-5"),
        "TPS62095": ic_symbol("TPS62095", [
            (11, "PVIN", W), (12, "PVIN", W), (10, "AVIN", W), (3, "DEF", I), (13, "EN", I),
            (9, "SS", P), (7, "CP", P), (8, "CN", P)], [
            (1, "SW", O), (2, "SW", O), (16, "VOS", I), (5, "FB", I), (4, "PG", O),
            (14, "PGND", W), (15, "PGND", W), (6, "AGND", W), (17, "EP", P)],
            desc="4 A synchronous buck with 100 % duty mode, VQFN-16 3 x 3 mm (RGT)"),
        "DW01A": ic_symbol("DW01A", [
            (5, "VCC", W), (2, "CS", I), (4, "TD", P)], [
            (1, "OD", O), (3, "OC", O), (6, "GND", W)],
            desc="1-cell Li-ion protection IC, SOT-23-6"),
        "SE8830A": ic_symbol("SE8830A", [
            (1, "S1", P), (6, "G1", I), (3, "S2", P), (4, "G2", I)], [
            (2, "D", P), (5, "D", P)], ref="Q",
            desc="dual N-MOSFET, common drain (8205 type), SOT-23-6"),
        "OPAMP_DBV": ic_symbol("OPAMP_DBV", [
            (3, "+IN", I), (4, "-IN", I), (5, "V+", W)], [
            (1, "OUT", O), (2, "V-", W)],
            desc="single op-amp, SOT-23-5 / SC-70-5 pinout of the TI TLV333 (DBV = DCK)"),
        "ESP32-C3-MINI-1": ic_symbol("ESP32-C3-MINI-1", [
            (3, "3V3", W), (8, "EN", I), (12, "IO0/ADC1_0", B), (13, "IO1/ADC1_1", B),
            (5, "IO2", B), (6, "IO3", B), (18, "IO4", B), (19, "IO5", B), (20, "IO6", B),
            (21, "IO7", B)], [
            (22, "IO8", B), (23, "IO9/BOOT", B), (16, "IO10", B), (26, "IO18/USB_D-", B),
            (27, "IO19/USB_D+", B), (30, "IO20/RXD0", B), (31, "IO21/TXD0", B),
            (1, "GND", W), (4, "NC", N)],
            width=30.48, desc="ESP32-C3 BLE 5 / Wi-Fi module, 4 MB flash, PCB antenna (pads 1, 2, 11, "
                              "14, 36-53 = GND, 49 = EPAD)",
            stacked=[(n, "GND", W, 1) for n in gnd] + [(n, "NC", N, 4) for n in nc if n != "4"]),
    }


_LIBCACHE = {}


def kicad_symbol(lib, name):
    if lib not in _LIBCACHE:
        _LIBCACHE[lib] = SymbolLib.from_file(os.path.join(KLIB, lib + ".kicad_sym"))
    s = [x for x in _LIBCACHE[lib].symbols if x.entryName == name][0]
    s = copy.deepcopy(s)
    if s.extends:
        raise RuntimeError(f"{lib}:{name} is a derived symbol")
    s.libraryNickname = lib
    return s


# --------------------------------------------------------------------------
# geometry
# --------------------------------------------------------------------------
def pin_points(sym, pos, rot):
    """-> {pin_number: [(x, y, outward_angle_deg_screen)]} in page coords."""
    out = {}
    r = math.radians(rot)
    for u in sym.units:
        for p in u.pins:
            px, py = p.position.X, p.position.Y
            x = px * math.cos(r) - py * math.sin(r)
            y = px * math.sin(r) + py * math.cos(r)
            # pin angle points from the connection point towards the body
            a_body = (p.position.angle + rot) % 360
            a_out = (a_body + 180) % 360            # library (y-up) angle
            sx, sy = round(pos[0] + x, 3), round(pos[1] - y, 3)
            out.setdefault(str(p.number), []).append((sx, sy, a_out))
    return out


def label_for(x, y, a_out, net, stub=G):
    dx, dy = math.cos(math.radians(a_out)), -math.sin(math.radians(a_out))
    ex, ey = round(x + dx * stub, 3), round(y + dy * stub, 3)
    wire = Connection(type="wire", points=[Position(x, y), Position(ex, ey)],
                      stroke=Stroke(width=0), uuid=uid())
    ang = {0: 0, 90: 90, 180: 180, 270: 270}[int(round(a_out)) % 360]
    lab = LocalLabel(text=net, position=Position(ex, ey, ang),
                     effects=eff(1.27, justify="left" if ang in (0, 90) else "right"),
                     uuid=uid())
    return wire, lab


# --------------------------------------------------------------------------
def build(outdir, title="FlashKa Keychain v0.7", rev="v0.7"):
    _UID[0] = 0
    sch = Schematic.create_new()
    sch.version = "20211123"
    sch.generator = "eeschema"
    sch.uuid = uid()
    sch.paper = PageSettings(paperSize="A3")
    sch.titleBlock = TitleBlock(title=title, date="2026-10-21", revision=rev,
                                company="LuxLibre",
                                comments={1: "Main PCB (blocks 1-6) and key board (block 7); source: "
                                             "tools/kicad/flashka_parts.py - nets connect by label",
                                          2: "KiCad 7 projects kicad/FlashKa_main and kicad/FlashKa_keys; "
                                             "JLCPCB files in production/"})
    customs = flashka_symbols()
    used = {}
    placed_pins = {}

    for c in COMPONENTS:
        src = c["sym"]
        key = src[1] + ":" + src[2] if src[0] == "kicad" else "FlashKa:" + src[1]
        if key not in used:
            used[key] = kicad_symbol(src[1], src[2]) if src[0] == "kicad" else customs[src[1]]
        lsym = used[key]
        x, y = c["pos"]
        rot = c.get("rot", 0)
        su = sym_uuid(c["ref"])
        lib_nick, entry = key.split(":")
        rpos, vpos, just = (x + 3.0, y - 3.0), (x + 3.0, y + 3.0), "left"
        if src[0] == "flashka":   # v0.7: IC reference and value above / below the body, clear of the pin names
            ys = [p.position.Y for u in lsym.units for p in u.pins]
            rpos, vpos, just = (x, y - max(ys) - 5.0), (x, y - min(ys) + 5.0), None
        props = [
            Property(key="Reference", value=c["ref"], id=0,
                     position=Position(*rpos, 0), effects=eff(1.27, justify=just)),
            Property(key="Value", value=c["value"], id=1,
                     position=Position(*vpos, 0), effects=eff(1.0, justify=just)),
            Property(key="Footprint", value=c["fp"], id=2, position=Position(x, y, 0),
                     effects=eff(hide=True)),
            Property(key="Datasheet", value="", id=3, position=Position(x, y, 0),
                     effects=eff(hide=True)),
        ]
        extra = [("LCSC", c.get("lcsc", "")), ("Supplier", "LCSC" if c.get("lcsc") else ""),
                 ("Supplier Part", c.get("lcsc", "")), ("Description", c.get("desc", ""))]
        if c.get("dnp"):
            extra.append(("DNP", "DNP"))
        for i, (k, v) in enumerate(extra):
            props.append(Property(key=k, value=v, id=4 + i, position=Position(x, y, 0),
                                  effects=eff(1.0, hide=(k != "DNP"))))
        pins_u = {}
        for u in lsym.units:
            for p in u.pins:
                pins_u[str(p.number)] = uid()
        ss = SchematicSymbol(libraryNickname=lib_nick, entryName=entry,
                             position=Position(x, y, rot), unit=1,
                             inBom=not c.get("dnp", False), onBoard=True, uuid=su,
                             properties=props, pins=pins_u)
        sch.schematicSymbols.append(ss)
        sch.symbolInstances.append(SymbolInstance(path="/" + su, reference=c["ref"],
                                                  unit=1, value=c["value"],
                                                  footprint=c["fp"]))
        pts = pin_points(lsym, (x, y), rot)
        placed_pins[c["ref"]] = pts
        done = set()
        for pin, net in c["nets"].items():
            for (px, py, ao) in pts[str(pin)]:
                if (px, py) in done:
                    continue
                done.add((px, py))
                w, lab = label_for(px, py, ao, net)
                sch.graphicalItems.append(w)
                sch.labels.append(lab)
        for pin in c.get("nc", []):
            for (px, py, ao) in pts[str(pin)]:
                if (px, py) in done:
                    continue
                sch.noConnects.append(NoConnect(position=Position(px, py), uuid=uid()))

    for k, s in used.items():
        sch.libSymbols.append(s)

    # block frames and titles
    for b, (x0, y0, x1, y1) in FRAMES.items():
        pl = PolyLine(points=[Position(x0, y0), Position(x1, y0), Position(x1, y1),
                              Position(x0, y1), Position(x0, y0)],
                      stroke=Stroke(width=0.3, type="dash"), uuid=uid())
        sch.graphicalItems.append(pl)
        sch.texts.append(Text(text=BLOCKS[b], position=Position(x0 + 2, y0 + 4, 0),
                              effects=eff(1.8, justify="left", bold=True), uuid=uid()))
    notes = [
        ((14, 142), "USB-C: Rd 5.1 k on CC1 and CC2 (5 V sink). D+/D- go to the ESP32-C3 native USB (flashing, console).\n"
                    "TP4057: R3 2.0 k returns PROG to CHG_SET (GPIO20): low = ~500 mA, floating = 10 mA trickle via R29,\n"
                    "high = charger off (only while USB is present). CHRG/STDBY are read by GPIO4/GPIO5 (internal pull-ups)."),
        ((88, 212), "J2: one 14500 cell, one 24 AWG wire per pad:\n"
                    "red = BAT+ (pin 1), black = BAT- (pin 2, BATN).\n"
                    "U6 DW01A + Q3 in the cell minus: GND = P-;\n"
                    "over-current 120-180 mV across Q3 (Kelvin) =\n"
                    "4.3-4.5 A typ. hot, 3.0 A worst; 4.30 / 2.4 V\n"
                    "cell limits; the charger works through Q3."),
        ((14, 270), "U5 RT9080: 3.3 V, EN tied to VIN, 2 uA Iq.\n"
                    "Q5/C17/R7: plugging in USB pulls EN low for\n"
                    "~0.1 s (module restart); button held while\n"
                    "plugging in = ROM download mode."),
        ((154, 142), "VOUT = 0.8 V (1 + R10/R11) = 2.4 V with Q2 off; Q2 sinks current from FB, VOUT rises until I_LED x RS1 = VSET.\n"
                     "VSET = duty(GPIO6, 13-bit PWM) x 3.3 V x R16/(R15+R16): 100 % = 71.0 mV = 3.55 A (3.0 A ceiling = 84.5 %).\n"
                     "U3 is powered from LED_EN.  Kelvin: R14 from the top of RS1; R16, C12 and U3 pin 2 return to RS1's ground pad."),
        ((154, 277), "S2 SAFE (pin 3) ties the Q1 gate to VBAT; ARMED (pin 1) gives Q4 / LASER_ON (GPIO10) control.\n"
                     "S2 never carries laser current. R18 keeps Q1 off and R20 keeps Q4 off while the MCU is in reset."),
        ((336, 30), "GPIO map:\nIO0 VBAT/2 - IO1 NTC - IO2/IO8/IO21 RGB B/G/R (active low, two ring LEDs)\n"
                    "IO3+IO9 button ladder (IO9 digital any-press + boot strap, IO3 ADC)\n"
                    "IO4 CHRG - IO5 STDBY - IO6 LED_PWM - IO7 LED_EN - IO10 LASER_ON\n"
                    "IO18/IO19 USB D-/D+ - IO20 CHG_SET.  Antenna beyond the board edge."),
        ((352, 74), "J6 = 6 target pads on the bottom face (no part);\n"
                    "the key board's pogo pins P1-P6 press on them."),
        ((294, 198), "Key board, screwed to the floor (H1, H2):\n"
                     "bottom face SW1-SW3, LED3, LED4 (keys side);\n"
                     "top face resistors + pogo pins P1-P6 to J6.\n"
                     "Ladder: R9 10k (main PCB), R30 1k, R31 2.2k."),
    ]
    for (x, y), t in notes:
        if t:
            sch.texts.append(Text(text=kt(t), position=Position(x, y, 0),
                                  effects=eff(1.0, justify="left"), uuid=uid()))
    sch.texts.append(Text(text=kt("LED: Luminus SST-20 Gen 2 on a 10 mm DTP copper board, 24 AWG:\n"
                                  "LED- to J3.1 (top side), LED+ to J3.2 (bottom side)."),
                          position=Position(232, 50, 0), effects=eff(1.0, justify="left"),
                          uuid=uid()))
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, "FlashKa_main.kicad_sch")
    sch.to_file(path)
    return path, placed_pins, used


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "kicad/FlashKa_main"
    p, _, used = build(out)
    print("wrote", p, "symbols:", len(used))


# --------------------------------------------------------------------------
# layout check: label boxes vs. label boxes and symbol bodies
# --------------------------------------------------------------------------
def label_box(lab, size=1.27):
    x, y, a = lab.position.X, lab.position.Y, lab.position.angle
    L = 1.0 * size * len(lab.text) + 0.6
    h = size * 1.3
    if a == 0:
        return (x, y - h / 2, x + L, y + h / 2)
    if a == 180:
        return (x - L, y - h / 2, x, y + h / 2)
    if a == 90:
        return (x - h / 2, y - L, x + h / 2, y)
    return (x - h / 2, y, x + h / 2, y + L)


def overlap(a, b, m=0.2):
    return not (a[2] + m <= b[0] or b[2] + m <= a[0] or a[3] + m <= b[1] or b[3] + m <= a[1])


def check_layout(path):
    sch = Schematic.from_file(path)
    boxes = []
    for lab in sch.labels:
        boxes.append(("label " + lab.text, label_box(lab)))
    # symbol bodies: approximate from lib rectangles / pins extents
    libs = {s.libId: s for s in sch.libSymbols}
    for ss in sch.schematicSymbols:
        ls = libs[ss.libId]
        xs, ys = [], []
        for u in ls.units:
            for g in u.graphicItems:
                for attr in ("start", "end"):
                    if hasattr(g, attr):
                        p = getattr(g, attr)
                        xs.append(p.X)
                        ys.append(p.Y)
            for p in u.pins:
                xs.append(p.position.X)
                ys.append(p.position.Y)
        if not xs:
            continue
        r = math.radians(ss.position.angle)
        pts = []
        for X in (min(xs), max(xs)):
            for Y in (min(ys), max(ys)):
                x = X * math.cos(r) - Y * math.sin(r)
                y = X * math.sin(r) + Y * math.cos(r)
                pts.append((ss.position.X + x, ss.position.Y - y))
        ref = [p.value for p in ss.properties if p.key == "Reference"][0]
        bx = (min(p[0] for p in pts) + 0.3, min(p[1] for p in pts) + 0.3,
              max(p[0] for p in pts) - 0.3, max(p[1] for p in pts) - 0.3)
        boxes.append(("sym " + ref, bx))
    issues = []
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            if boxes[i][0].startswith("sym") and boxes[j][0].startswith("sym"):
                pass
            if overlap(boxes[i][1], boxes[j][1]):
                issues.append((boxes[i][0], boxes[j][0]))
    return issues
