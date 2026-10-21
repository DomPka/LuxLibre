#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compare a KiCad netlist (kicad-cli sch export netlist) with aurora_parts.py.

usage: verify_netlist.py <file.net>
Exit code 0 = every intended net matches exactly and nothing else is connected.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aurora_parts import COMPONENTS, nets_of  # noqa: E402


def parse_kicad_net(path):
    txt = open(path, encoding="utf-8").read()
    nets = {}
    for m in re.finditer(r'\(net \(code "?\d+"?\) \(name "([^"]*)"\)(.*?)\)\s*(?=\(net |\)\s*\)\s*$)',
                         txt, re.S):
        name = m.group(1)
        nodes = re.findall(r'\(node \(ref "([^"]+)"\) \(pin "([^"]+)"\)', m.group(2))
        nets[name] = sorted(nodes)
    return nets


def main(path):
    got = parse_kicad_net(path)
    want = {k: sorted(v) for k, v in nets_of().items()}
    ok = True
    named = {}
    for name, nodes in got.items():
        if name.startswith("unconnected-") or name.startswith("Net-("):
            if len(nodes) > 1:
                print("UNNAMED NET WITH >1 NODE:", name, nodes)
                ok = False
            continue
        named[name.lstrip("/")] = nodes
    for net, nodes in want.items():
        g = named.get(net)
        if g is None:
            print("MISSING NET", net, nodes)
            ok = False
        elif sorted(g) != nodes:
            print("MISMATCH", net, "\n  want", nodes, "\n  got ", g)
            ok = False
    for net in named:
        if net not in want:
            print("EXTRA NET", net, named[net])
            ok = False
    # every intended NC pin must be single-node
    for c in COMPONENTS:
        for p in c.get("nc", []):
            hits = [n for n, nodes in got.items() if (c["ref"], str(p)) in nodes and len(nodes) > 1]
            if hits:
                print("NC PIN CONNECTED", c["ref"], p, hits)
                ok = False
    print("named nets:", len(named), "expected:", len(want), "->", "OK" if ok else "ERRORS")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main(sys.argv[1]) else 1)
