#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
v0.7 netlist check across the two boards.

  python3 tools/kicad/verify_v07.py kicad/FlashKa_main/FlashKa_main.kicad_pcb \
          kicad/FlashKa_keys/FlashKa_keys.kicad_pcb ../flashka-keychain-v06/flashka.net \
          [flashka.net] [docs/checks/netlist_v07.txt]

1. Contacts: every J6 pad (main PCB, bottom face) lies over the pogo pin of the same number
   (key board, top face) - same housing X/Y within 0.01 mm, facing faces (J6 on B.Cu, pin on
   F.Cu), same net name, and the plunger tip (d0.9) inside the d1.6 pad with the margin left
   for the mounting tolerance.  Both boards use the housing frame (x = 100 + X, y = 100 - Y,
   seen from the lid), so the bottom face of the main PCB and the top face of the key board
   need no mirroring: equal KiCad x/y means "on top of each other".
2. Connectivity: the pad nets of both routed boards (as KiCad stores them), joined through the
   six J6 / P pairs, must give exactly the v0.6 netlist (V6/flashka.net, schematic export) once
   J6, P1-P6, the mounting holes H1/H2 and the pins of the v0.7 power stage (POWER_PARTS) are
   left out: same net names, same pins per net.  The power-stage pins are compared one by one
   with POWER_STAGE, the intended connections written down from the TPS62095, DW01A and
   SE8830A data sheets (independent of flashka_parts.py); no other pad of those parts may
   carry a net.
3. Parts: every v0.6 part is on one of the two boards with the same value and footprint
   (ladder R30 1k / R31 2.2k with pull-up R9 10k; ring LED resistors R23/R32 330, R24/R25/R33/R34
   100 are listed) except the intended changes (CHANGED: the power stage, R16 for its current
   scale, R3 for the 500 mA charge current of the 14500 cell; REMOVED); nothing else is new but
   J6, P1-P6, H1, H2 and the power-stage parts.
4. The v0.7 schematic netlist (flashka.net) carries the same nets as the two boards.
Exit code 0 = all checks pass; the report is written to the last argument.
"""
import math
import os
import re
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from flashka_parts import KB, POGO_NETS  # noqa: E402
from verify_netlist import parse_kicad_net  # noqa: E402

NEW_PARTS = {"J6", "P1", "P2", "P3", "P4", "P5", "P6", "H1", "H2"}
PLUNGER_D, PAD_D = 0.9, 1.6
# v0.7 power stage (>= 1000 lm): buck TPS62095 (U2), second output capacitor C22, charge-pump
# capacitor C23, 1-cell protection DW01A (U6) + SE8830A (Q3) with R35, C24, R36 in the cell minus
# (BATN); J2 pin 2 is the cell minus BATN; C7 and the feed-forward capacitor C9 removed.  J3 keeps
# its v0.6 nets (1 = LED+ = VOUT top face, 2 = LED- = ISNS bottom face) and is checked against v0.6
# with everything else; only its footprint changes (split 24 AWG pads, CHANGED)
POWER_NEW = {"C22", "C23", "U6", "Q3", "R35", "R36", "C24"}
REMOVED = {"C7", "C9"}
POWER_PARTS = {"U2", "J2"} | POWER_NEW | REMOVED
POWER_STAGE = {
    ("U2", "1"): "SW", ("U2", "2"): "SW", ("U2", "3"): "VBAT", ("U2", "5"): "FB", ("U2", "6"): "GND",
    ("U2", "7"): "BUCK_CP", ("U2", "8"): "BUCK_CN", ("U2", "10"): "VBAT", ("U2", "11"): "VBAT",
    ("U2", "12"): "VBAT", ("U2", "13"): "LED_EN", ("U2", "14"): "GND", ("U2", "15"): "GND",
    ("U2", "16"): "VOUT", ("U2", "17"): "GND",
    ("J2", "1"): "VBAT", ("J2", "2"): "BATN",
    ("C22", "1"): "VOUT", ("C22", "2"): "GND", ("C23", "1"): "BUCK_CP", ("C23", "2"): "BUCK_CN",
    ("U6", "1"): "PROT_OD", ("U6", "2"): "PROT_CS", ("U6", "3"): "PROT_OC", ("U6", "5"): "PROT_VCC",
    ("U6", "6"): "BATN",
    ("Q3", "1"): "BATN", ("Q3", "2"): "PROT_D", ("Q3", "3"): "GND", ("Q3", "4"): "PROT_OC",
    ("Q3", "5"): "PROT_D", ("Q3", "6"): "PROT_OD",
    ("R35", "1"): "VBAT", ("R35", "2"): "PROT_VCC", ("R36", "1"): "PROT_CS", ("R36", "2"): "GND",
    ("C24", "1"): "PROT_VCC", ("C24", "2"): "BATN",
}
POWER_NC = {("U2", "4"), ("U2", "9"), ("U6", "4")}      # PG, SS (open = fastest start), TD
CHANGED = {"U2": ("TPS62095RGTR", "FlashKa:VQFN-16-1EP_3x3mm_P0.5mm_EP1.68x1.68mm_TV2"),
           "R16": ("2.2k", "Resistor_SMD:R_0402_1005Metric"),
           "R3": ("2k", "Resistor_SMD:R_0402_1005Metric"),      # TP4057 PROG: 500 mA for the 14500 cell
           "J2": ("CELL", "FlashKa:WirePad_SMD_2_P3.0mm_24AWG"),
           "J3": ("LED", "FlashKa:WirePad_LED_Split_24AWG")}


def mm(v):
    return pcbnew.ToMM(v)


def parse_components(path):
    """ref -> (value, footprint) from a KiCad netlist."""
    txt = open(path, encoding="utf-8").read()
    out = {}
    for m in re.finditer(r'\(comp \(ref "([^"]+)"\)\s*\(value "([^"]*)"\)\s*\(footprint "([^"]*)"\)', txt):
        out[m.group(1)] = (m.group(2), m.group(3))
    return out


def board_pads(path):
    """(ref, pad) -> dict(net, x, y, layers, value, fp) of a routed board."""
    b = pcbnew.LoadBoard(path)
    out = {}
    for f in b.GetFootprints():
        fpid = f.GetFPID()
        fpname = f"{fpid.GetLibNickname().wx_str()}:{fpid.GetLibItemName().wx_str()}"
        for p in f.Pads():
            if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH or not p.IsOnCopperLayer():
                continue        # holes, and the paste apertures of U2's exposed pad (no copper)
            ls = p.GetLayerSet()
            out[(f.GetReference(), p.GetNumber())] = dict(
                net=p.GetNetname(), x=mm(p.GetPosition().x), y=mm(p.GetPosition().y),
                F=ls.Contains(pcbnew.F_Cu), B=ls.Contains(pcbnew.B_Cu), value=f.GetValue(), fp=fpname)
    return out


def main(main_pcb, keys_pcb, v06_net, v07_net=None, report=None):
    lines, ok = [], True

    def say(s=""):
        lines.append(s)
    say("FlashKa Keychain v0.7 - netlist check across the main PCB and the key board")
    say(f"main PCB:  {os.path.basename(main_pcb)}   key board: {os.path.basename(keys_pcb)}")
    say(f"reference: v0.6 schematic netlist {os.path.basename(os.path.dirname(os.path.abspath(v06_net)))}/flashka.net")
    say("")
    mp, kp = board_pads(main_pcb), board_pads(keys_pcb)

    # 1. contacts
    say("1. Pogo contacts (housing X/Y; J6 on the main PCB's bottom face, Pn on the key board's top face)")
    say("   pad   net     J6 at (X, Y)       Pn at (X, Y)       offset  faces  net  tip in pad (margin)")
    mount_tol = 0.40       # design allowance for KB/main position tolerance (see the design chapter)
    for n, (pref, X, Y) in enumerate(KB["pogo"], start=1):
        j = mp.get(("J6", str(n)))
        p = kp.get((pref, "1"))
        if j is None or p is None:
            say(f"   J6.{n}  MISSING")
            ok = False
            continue
        jx, jy = j["x"] - 100, 100 - j["y"]
        px, py = p["x"] - 100, 100 - p["y"]
        off = math.hypot(jx - px, jy - py)
        faces = j["B"] and not j["F"] and p["F"] and not p["B"]
        same = j["net"] == p["net"] == POGO_NETS[n - 1]
        margin = PAD_D / 2 - off - PLUNGER_D / 2 * 0     # point tip: the contact point is the axis
        good = off < 0.01 and faces and same and abs(px - X) < 0.01 and abs(py - Y) < 0.01 and margin >= mount_tol
        ok &= good
        say(f"   J6.{n}  {j['net']:6s}  ({jx:6.3f}, {jy:6.3f})  ({px:6.3f}, {py:6.3f})  {off:.3f}   "
            f"{'B/F' if faces else 'BAD'}    {'ok' if same else 'BAD'}  {margin:.2f} mm {'ok' if good else 'FAIL'}")
    say(f"   the plunger axis may move {PAD_D / 2:.2f} mm off the pad centre before it leaves the d{PAD_D} pad; "
        f"design allowance {mount_tol:.2f} mm")
    say("")

    # 2. connectivity through the pairs
    say("2. Connectivity: both boards joined through J6.n <-> Pn, compared with the v0.6 netlist")
    parent = {}

    def node(board, net):
        k = (board, net)
        parent.setdefault(k, k)
        return k

    def find(k):
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    for (ref, pad), d in mp.items():
        if d["net"]:
            node("main", d["net"])
    for (ref, pad), d in kp.items():
        if d["net"]:
            node("keys", d["net"])
    for n, (pref, _X, _Y) in enumerate(KB["pogo"], start=1):
        j, p = mp.get(("J6", str(n))), kp.get((pref, "1"))
        if j and p and j["net"] and p["net"]:
            union(node("main", j["net"]), node("keys", p["net"]))
    merged = {}
    names = {}
    for board, pads in (("main", mp), ("keys", kp)):
        for (ref, pad), d in pads.items():
            if not d["net"] or ref in NEW_PARTS or ref in POWER_PARTS:
                continue
            r = find(node(board, d["net"]))
            merged.setdefault(r, set()).add((ref, pad))
            names.setdefault(r, set()).add(d["net"])
    got = {}
    for r, pins in merged.items():
        nm = sorted(names[r])
        if len(nm) != 1:
            say(f"   NET NAMES DIFFER ACROSS THE CONTACT: {nm}")
            ok = False
        got[nm[0]] = sorted(pins)
    want = {}
    for name, nodes in parse_kicad_net(v06_net).items():
        if name.startswith("unconnected-") or name.startswith("Net-("):
            continue
        nodes = [nd for nd in nodes if nd[0] not in POWER_PARTS]
        if nodes:
            want[name.lstrip("/")] = sorted(nodes)
    diff = 0
    for name in sorted(set(want) | set(got)):
        a, b = want.get(name), got.get(name)
        if a != b:
            diff += 1
            say(f"   DIFFERENT {name}: v0.6 {a}  v0.7 {b}")
    cross = sorted({n for n in got if any(r in ("SW1", "SW2", "SW3", "LED3", "LED4", "R23", "R24", "R25", "R32",
                                                    "R33", "R34", "R30", "R31") for r, _p in got[n])
                    and any(r not in ("SW1", "SW2", "SW3", "LED3", "LED4", "R23", "R24", "R25", "R32",
                                      "R33", "R34", "R30", "R31") for r, _p in got[n])})
    say(f"   nets: v0.6 {len(want)}, v0.7 (both boards joined) {len(got)}, different: {diff}")
    say(f"   nets that cross the contact: {', '.join(cross)} (= the pogo nets {', '.join(POGO_NETS)})")
    only_kb = sorted(n for n in got if all(r in ("SW1", "SW2", "SW3", "LED3", "LED4", "R23", "R24", "R25", "R32",
                                                 "R33", "R34", "R30", "R31") for r, _p in got[n]))
    say(f"   nets on the key board only: {', '.join(only_kb)}")
    ok &= diff == 0 and cross == sorted(POGO_NETS)
    say("   (pins of the power-stage parts " + ", ".join(sorted(POWER_PARTS - REMOVED)) + " left out here, see 2b)")
    say("")
    say("2b. Power stage (v0.7): pad nets of " + ", ".join(sorted(POWER_PARTS - REMOVED))
        + " against the intended connections")
    pbad = 0
    for (ref, pad), net in sorted(POWER_STAGE.items(), key=lambda kv: (kv[0][0], int(kv[0][1]))):
        d = mp.get((ref, pad))
        got_net = d["net"] if d else None
        if got_net != net:
            pbad += 1
            say(f"   WRONG {ref}.{pad}: want {net}, board {got_net}")
    for (ref, pad), d in sorted(mp.items()):
        if ref in POWER_PARTS and (ref, pad) not in POWER_STAGE:
            if d["net"] or (ref, pad) not in POWER_NC:
                pbad += 1
                say(f"   UNEXPECTED {ref}.{pad}: net {d['net'] or '(none)'}")
    gone = sorted(r for r in REMOVED if any(k[0] == r for k in mp))
    if gone:
        pbad += 1
        say(f"   STILL ON THE BOARD: {', '.join(gone)}")
    byn = {}
    for (ref, pad), net in POWER_STAGE.items():
        byn.setdefault(net, []).append(f"{ref}.{pad}")
    for net in ("BATN", "SW", "VOUT", "BUCK_CP", "BUCK_CN", "PROT_OD", "PROT_OC", "PROT_CS",
                "PROT_VCC", "PROT_D"):
        say(f"   {net:9s} " + " ".join(sorted(byn[net])))
    say(f"   {len(POWER_STAGE)} power-stage pins checked, open pins {', '.join(f'{r}.{p}' for r, p in sorted(POWER_NC))}, "
        f"removed {', '.join(sorted(REMOVED))}: " + ("all as intended" if pbad == 0 else f"{pbad} PROBLEMS"))
    ok &= pbad == 0
    say("")

    # 3. parts, values, footprints
    say("3. Parts: values and footprints against v0.6")
    v06c = parse_components(v06_net)
    have = {}
    for pads in (mp, kp):
        for (ref, pad), d in pads.items():
            have[ref] = (d["value"], d["fp"])
    pdiff = 0
    for ref in sorted(v06c):
        if ref in REMOVED:
            if ref in have:
                say(f"   STILL PRESENT {ref} (removed in v0.7)")
                pdiff += 1
            continue
        if ref not in have:
            say(f"   MISSING {ref}")
            pdiff += 1
        elif ref in CHANGED:
            if have[ref] != CHANGED[ref]:
                say(f"   CHANGED {ref}: want {CHANGED[ref]}  v0.7 {have[ref]}")
                pdiff += 1
            else:
                say(f"   intended change {ref}: v0.6 {v06c[ref][0]} {v06c[ref][1].split(':')[1]} -> "
                    f"v0.7 {have[ref][0]} {have[ref][1].split(':')[1]}")
        elif have[ref] != v06c[ref]:
            say(f"   CHANGED {ref}: v0.6 {v06c[ref]}  v0.7 {have[ref]}")
            pdiff += 1
    extra = sorted(set(have) - set(v06c))
    say(f"   v0.6 parts {len(v06c)}: all present except {', '.join(sorted(REMOVED))} (removed), value and "
        f"footprint unchanged apart from the intended changes: {'yes' if pdiff == 0 else 'NO'}")
    say(f"   new in v0.7: {', '.join(extra)} (expected {', '.join(sorted((NEW_PARTS | POWER_NEW) - {'H1', 'H2'}))}"
        f" plus the screw holes H1, H2 without pads)")
    for ref, want_v in (("R9", "10k"), ("R30", "1k"), ("R31", "2.2k"), ("R23", "330Ω"), ("R32", "330Ω"),
                        ("R24", "100Ω"), ("R25", "100Ω"), ("R33", "100Ω"), ("R34", "100Ω")):
        v = have.get(ref, ("?",))[0]
        board = "main" if any(k[0] == ref for k in mp) else "key board"
        say(f"   {ref:4s} {v:6s} ({board})" + ("" if v == want_v else f"  WANT {want_v}"))
        ok &= v == want_v
    ok &= pdiff == 0 and set(extra) <= NEW_PARTS | POWER_NEW
    say("")

    # 4. schematic netlist of v0.7 against the boards
    if v07_net:
        say("4. v0.7 schematic netlist (flashka.net) against the two boards")
        sch = {}
        for name, nodes in parse_kicad_net(v07_net).items():
            if name.startswith("unconnected-") or name.startswith("Net-("):
                continue
            sch[name.lstrip("/")] = sorted(nodes)
        brd = {}
        for pads in (mp, kp):
            for (ref, pad), d in pads.items():
                if d["net"]:
                    brd.setdefault(d["net"], []).append((ref, pad))
        brd = {k: sorted(v) for k, v in brd.items()}
        sdiff = [n for n in sorted(set(sch) | set(brd)) if sch.get(n) != brd.get(n)]
        for n in sdiff:
            say(f"   DIFFERENT {n}: schematic {sch.get(n)}  boards {brd.get(n)}")
        say(f"   nets: schematic {len(sch)}, boards {len(brd)}, different: {len(sdiff)}")
        ok &= not sdiff
        say("")
    say("RESULT: " + ("PASS - main PCB + key board through J6/P1-P6 equal the v0.6 netlist apart from the "
                      "v0.7 power stage, which matches its intended connections; the six pogo contacts "
                      "and the power-stage parts are the only new items" if ok else "FAIL"))
    txt = "\n".join(lines) + "\n"
    if report:
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        with open(report, "w", encoding="utf-8") as f:
            f.write(txt)
    print(txt)
    return ok


if __name__ == "__main__":
    a = sys.argv[1:]
    sys.exit(0 if main(a[0], a[1], a[2], a[3] if len(a) > 3 else None, a[4] if len(a) > 4 else None) else 1)
