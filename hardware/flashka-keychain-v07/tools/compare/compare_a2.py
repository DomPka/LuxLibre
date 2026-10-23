#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""FlashKa Keychain v0.7 vs RovyVon Aurora A2: comparison pictures for the project page.

usage:  xvfb-run -a python3 compare_a2.py <cad_dir> <out_dir> [--fw-sim DIR] [--cargo-target-dir DIR]
                                         [--only beams,size,output,combined,md] [--draft]

  <cad_dir>      FlashKa v0.7 CAD folder: FlashKa_tray.stl, FlashKa_lid.stl and housing_interface.json
                 (required), the optic / key / screw STLs when present (housing frame of the CAD: X from the
                 front face to the tail, Y across, Z up from the bottom face, mm)
  <out_dir>      the pictures and sources_comparison.md are written here
  --fw-sim       folder with flashka_v07_balanced_turbo.csv and flashka_v07_balanced_high.csv (and, when present,
                 flashka_v07_turbo_half_cell.csv and thermal_v07_output.txt, the test's printed lines), the files
                 of the FlashKa firmware's thermal simulation; default: run that simulation now (cargo test
                 --offline --locked --features board-v07 --test thermal_v07 -- --nocapture in
                 hardware/flashka-keychain-v06/firmware/flashka-core, with the build folder in a temporary
                 folder, so nothing in the firmware folder changes)
  --cargo-target-dir  build folder for that cargo run, to reuse a build (default: a temporary folder)
  --draft        half resolution, for a quick look

Writes comparison_beams.png, comparison_size.png, comparison_output.png, comparison_combined.png,
comparison_combined_dark.png and sources_comparison.md.  Deterministic: fixed seeds, no clock.

PHOTOMETRY (SI units: lm, cd, lx = lm/m2, cd/m2)
  FlashKa v0.7: Luminus SST-20 Gen 2 (6500 K, G1 bin) under a LEDiL LISA3-RS-PIN TIR optic, no front window.
    LED lumens Phi_LED = the firmware's LED model at the simulated LED current (board.rs LED_LM_TABLE:
    datasheet values at Tj 85 C, linear between the points) x a junction-temperature factor
        f(Tj) = 1.10 - 0.10 (Tj - 25 C) / 60 C   (1.10 at 25 C, 1.00 at 85 C: datasheet G1 minimum 748 lm at
                                                   Tj 25 C and 680 lm at Tj 85 C, both at 1.5 A)
        Tj = T_head + 1.6 C/W x 0.70 x P_LED,  P_LED = (2.80 V + 0.15 V/A x I) x I
    T_head is the simulated head temperature, 1.6 C/W the datasheet's Rth j-sp, and 70 % of the LED's electrical
    power is taken as heat (30 % leaves as light, as in the simulation); the LED board to head interface is
    not counted.
    Optic, per LED lumen (LEDiL's simulated data for the SST-20 Gen 2: 87 %, 20 deg FWHM, 5.5 cd/lm):
        I(theta) / Phi_LED = a exp(-theta^2 / (2 sigma^2)) + b cos(theta) S(theta)
    S = raised-cosine edge from 50 to 70 deg (the spill).  Conditions: a + b = 5.5 cd/lm (peak),
    2 pi * integral(I sin theta dtheta) = 0.87 (efficiency) and I(10 deg) = I(0) / 2 (20 deg FWHM); solved for
    sigma, a and b.  The spill's share of the light and how it depends on the edge, the spill shape, the FWHM,
    the peak and the efficiency go to the sources file.  Out of the front = 0.87 Phi_LED; peak = 5.5 cd/lm x
    Phi_LED; ANSI throw = 2 sqrt(peak).
  RovyVon Aurora A2: SST-20 behind a TIR optic, modelled as a Gaussian hotspot plus a broad spill:
        I(theta) = I_h exp(-theta^2 / (2 sigma^2)) + I_s cos(theta) S(theta)
    with the same S.  Conditions: I(0) = I_h + I_s = the measured peak (1lumen, at switch-on),
    2 pi * integral(I sin theta dtheta) = the measured lumens, and an assumed spill share of 25 % of the
    flux; sigma follows from these.  ANSI throw 2 sqrt(I0) then equals the published throw.
  Surfaces: illuminance E = I(theta) cos(alpha) / d^2 (theta off the beam axis, alpha = angle of
    incidence, d = distance); matte surfaces have luminance L = rho E / pi.  Both beam panels use the
    same scene, camera, exposure and tone curve, so their relative brightness is true.
  Checks run every time and stop the script on failure: the simulator's LED lumens equal board.rs's table;
  the FlashKa optic model has the datasheet's peak, efficiency and FWHM, and its grid integral equals an
  adaptive quadrature of the formula; the A2 integral equals its lumens; the illuminance integrated over a
  large wall and over a finite inclined plane equals the flux into the solid angle they subtend; E d^2 = I0
  on axis; the illuminance integrated over the rendered wall pixels equals the flux into the visible wall
  area; the VTK objects and the numpy planes share one camera.  Both panels are tone-mapped with one white
  point (written to the sources file).
"""
import argparse
import csv
import glob
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile

import numpy as np

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
V7 = os.path.abspath(os.path.join(HERE, "..", ".."))
REPO = os.path.abspath(os.path.join(V7, "..", ".."))
FW_CORE = os.path.join(REPO, "hardware", "flashka-keychain-v06", "firmware", "flashka-core")
FW_TEST = ["test", "--offline", "--locked", "--features", "board-v07", "--test", "thermal_v07", "--", "--nocapture"]
FW_SCENARIOS = {"turbo": "flashka_v07_balanced_turbo", "high": "flashka_v07_balanced_high",
                "half": "flashka_v07_turbo_half_cell"}            # "half": optional (turbo from a half-full cell)
FW_PRINTED = "thermal_v07_output.txt"                               # the test's printed lines, kept with the CSV files
SEED = 20261021

# ----------------------------------------------------------------------------------------------
# data
# ----------------------------------------------------------------------------------------------
URL_1LUMEN = "https://1lumen.com/review/rovyvon-a2/"
URL_ADVC = "https://www.adventurecarry.com/products/aurora-a2-usb-c"
URL_KAPUGA = "https://kapuga.pl/produkt/rovyvon-aurora-a2-g4-silver-650-lm-keychain-flashlight"
URL_MUKAMA = "https://www.mukama.com/products/rovyvon-aurora-a2-stainless-steel-g4-flashlight"
URL_BLF = "https://budgetlightforum.com/t/-/54488"
URL_LUMINUS = "https://download.luminus.com/datasheets/Luminus_SST-20-WS_Gen%202_Datasheet.pdf"
URL_LEDIL = "https://www.ledil.com/data/prod/Lisa/16558/16558-ds.pdf"
URL_VAPCELL = "https://www.vapcelltech.com/h-pd-251.html"

A2 = {
    "name": "RovyVon Aurora A2",
    "generation": "Gen 4 (G4, USB-C, SST-20 cool white)",
    # maker's data (Gen 4 retail listings quoting RovyVon; Gen 3 maker table quoted by 1lumen)
    "spec_lm": 650, "spec_throw_m": 110, "spec_cd_gen3": 2500, "spec_step": "High steps down to 100 lm after 60 s",
    "length_mm": 57.3, "dia_mm": 15.6, "mass_g": (19.5, 33.9), "battery_mAh": 300,
    # independent measurement, 1lumen, Gen 3 (Sept 2022), High mode
    "meas_t_s": [0.0, 30.0, 600.0], "meas_lm": [633.0, 394.0, 118.0],
    "meas_cd": {0: 3775.0, 30: 2750.0}, "meas_throw_m": {0: 123, 30: 105},
    "runtime": "1 h 04 min to the ANSI end point, off at 1 h 07 min",
}
A2_SPILL_SHARE = 0.25            # assumed share of the A2 flux in the spill (TIR optic)
A2_SPILL_EDGE = (50.0, 70.0)     # deg, raised-cosine edge of the spill

# FlashKa v0.7 light (datasheets; the sources file gives every value with its source)
LED = {"name": "Luminus SST-20 Gen 2, 6500 K, G1 bin",
       "rth_jsp": 1.6,                     # C/W, junction to solder point (datasheet)
       "heat_frac": 0.70,                  # share of the LED's electrical power that is heat (assumption)
       "vf0": 2.80, "vf_slope": 0.15,      # V, V/A: the firmware's and the simulation's LED voltage model
       "f_lo": 1.10, "f_hi": 1.00, "tj_lo": 25.0, "tj_hi": 85.0,   # relative flux at Tj 25 / 85 C
       "lm_1500_25": 748, "lm_1500_85": 680, "lm_3000_85": 1156}   # G1 minimum (datasheet)
OPTIC = {"name": "LEDiL LISA3-RS-PIN (FP16558)", "eff": 0.87, "fwhm_deg": 20.0, "cd_per_lm": 5.5,
         "edge": (50.0, 70.0)}             # LEDiL datasheet, SST-20 Gen 2 row (simulated by LEDiL); spill edge: model
OPTIC_CASES = (("spill edge 35-55 deg", {"edge": (35.0, 55.0)}), ("spill edge 60-80 deg", {"edge": (60.0, 80.0)}),
               ("spill shape cos^2", {"spill_pow": 2}), ("FWHM 19 deg", {"fwhm": 19.0}),
               ("FWHM 21 deg", {"fwhm": 21.0}), ("peak 5.5 cd/lm - 5 %", {"peak": 5.5 * 0.95}),
               ("peak 5.5 cd/lm + 5 %", {"peak": 5.5 * 1.05}), ("efficiency 85 %", {"eff": 0.85}),
               ("efficiency 89 %", {"eff": 0.89}))
CELL = {"name": "Vapcell INR14500 F15", "n": 1, "mAh": 1500, "mAh_min": 1150, "V": 3.6, "max_A": 3.0,
        "size_mm": (14.0, 49.0), "g": 22.0, "r_ac_mohm": 60}   # maker's data (URL_VAPCELL): typical / minimum at 0.2C
ELECTRONICS_G = (("main board with the ESP32-C3 module", 2.7), ("key board and pogo pins", 0.7),
                 ("laser module", 1.2), ("LED", 0.05), ("lid and key-board screws", 0.6),
                 ("wires (24 AWG power, thin signal)", 0.5))     # estimate, not weighed

BLUE, ORANGE = "#2a78d6", "#eb6834"             # categorical slots 1 and 2 (light surface)
BLUE_D, ORANGE_D = "#3987e5", "#d95926"         # the same slots stepped for the dark surface


def log(*a):
    print(*a, flush=True)


# ----------------------------------------------------------------------------------------------
# FlashKa firmware simulation (thermal model + the firmware's controller) and the LED model
# ----------------------------------------------------------------------------------------------
def fw_command(target="<tmp>/target", csv_dir="<dir>"):
    return "FLASHKA_SIM_CSV=%s CARGO_TARGET_DIR=%s cargo %s" % (csv_dir, target, " ".join(FW_TEST))


def run_fw_sim(tmp, target_dir=None):
    """run the FlashKa firmware's thermal simulation for the v0.7 board and return the folder of its CSV files;
    cargo builds into a temporary folder (or target_dir), so nothing in the firmware folder changes"""
    cargo = shutil.which("cargo")
    if cargo is None or not os.path.isdir(FW_CORE):
        raise SystemExit("cannot run the FlashKa simulation (cargo or %s missing): pass --fw-sim DIR"
                         % os.path.relpath(FW_CORE, REPO))
    out = os.path.join(tmp, "fwsim")
    os.makedirs(out, exist_ok=True)
    target = os.path.abspath(target_dir) if target_dir else os.path.join(tmp, "target")
    env = dict(os.environ, FLASHKA_SIM_CSV=out, CARGO_TARGET_DIR=target)
    log("  running the FlashKa firmware simulation (cargo, offline, build folder outside the repository)")
    r = subprocess.run([cargo] + FW_TEST, cwd=FW_CORE, env=env, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("FlashKa simulation failed:\n%s\n%s" % (r.stdout[-2000:], r.stderr[-2000:]))
    with open(os.path.join(out, FW_PRINTED), "w") as fh:
        fh.write(r.stdout)
    return out


def fw_by_charge(folder):
    """{charge %: LED mA} of turbo 30 s after switching on, as printed by the simulation test, or None"""
    path = os.path.join(folder, FW_PRINTED)
    if not os.path.exists(path):
        return None
    m = re.search(r"Balanced turbo at 30 s by charge:(.*)", open(path).read())
    if not m:
        return None
    return {int(p): int(ma) for p, ma, _ in re.findall(r"(\d+) %: (\d+) mA = (\d+) lm", m.group(1))} or None


def load_fw_sim(folder):
    """{"turbo": {column: array}, "high": ...}: one row per second from the switch-on (t_s = 1, 2, ...)"""
    cols = ("t_s", "led_mA", "lm_led", "lm_front", "T_sensor_C", "T_head_C", "T_body_C", "V_bat", "SoC_pct")
    res = {}
    for key, name in FW_SCENARIOS.items():
        path = os.path.join(folder, name + ".csv")
        if not os.path.exists(path):
            if key == "half":
                continue
            raise SystemExit("missing %s" % path)
        with open(path, newline="") as fh:
            rows = list(csv.DictReader(fh))
        d = {c: np.array([float(r[c]) for r in rows]) for c in cols}
        if "T_cell_C" in rows[0]:
            d["T_cell_C"] = np.array([float(r["T_cell_C"]) for r in rows])
        if len(rows) < (60 if key == "half" else 1500) or d["t_s"][0] != 1.0 or np.any(np.diff(d["t_s"]) != 1.0):
            raise SystemExit("%s: expected 1 s rows from t = 1 s for at least 25 min" % path)
        d["name"] = name
        res[key] = d
    return res


def board_led_model():
    """LED_LM_TABLE (mA, lm at the LED, Tj 85 C) and OPTIC_PCT from the firmware's board.rs"""
    path = os.path.join(FW_CORE, "src", "board.rs")
    txt = open(path).read()
    m = re.search(r"pub const LED_LM_TABLE:[^=]*=\s*\[(.*?)\];", txt, re.S)
    o = re.search(r"pub const OPTIC_PCT:\s*u32\s*=\s*(\d+)\s*;", txt)
    if not m or not o:
        raise SystemExit("LED_LM_TABLE / OPTIC_PCT not found in %s" % path)
    table = [(int(a.replace("_", "")), int(b.replace("_", "")))
             for a, b in re.findall(r"\(\s*([\d_]+)\s*,\s*([\d_]+)\s*\)", m.group(1))]
    cap = re.search(r'#\[cfg\(feature = "board-v07"\)\]\s*pub const CELL_CAPACITY_MAH:\s*\w+\s*=\s*([\d_]+)\s*;', txt)
    return {"table": table, "optic_pct": int(o.group(1)), "path": os.path.relpath(path, REPO),
            "capacity_mah": int(cap.group(1).replace("_", "")) if cap else None}


def led_power_w(ma):
    i = np.asarray(ma, float) / 1000.0
    return np.where(i > 0, (LED["vf0"] + LED["vf_slope"] * i) * i, 0.0)


def junction_c(t_head, ma):
    """Tj = T_head + Rth j-sp x (heat share x electrical LED power)"""
    return np.asarray(t_head, float) + LED["rth_jsp"] * LED["heat_frac"] * led_power_w(ma)


def temp_factor(tj):
    """relative LED flux vs Tj: linear from f_lo at tj_lo to f_hi at tj_hi (the table is at tj_hi)"""
    return LED["f_lo"] + (LED["f_hi"] - LED["f_lo"]) * (np.asarray(tj, float) - LED["tj_lo"]) / (LED["tj_hi"] - LED["tj_lo"])


def apply_led_model(sims):
    for sc in sims.values():
        sc["Tj"] = junction_c(sc["T_head_C"], sc["led_mA"])
        sc["f"] = temp_factor(sc["Tj"])
        sc["phi"] = sc["lm_led"] * sc["f"]                 # LED lumens at the simulated Tj
        sc["otf"] = OPTIC["eff"] * sc["phi"]               # out of the front


def row_at(sc, t):
    i = int(np.argmin(np.abs(sc["t_s"] - t)))
    if abs(sc["t_s"][i] - t) > 0.5:
        raise SystemExit("no simulator row at t = %g s" % t)
    return i


def key_values(sims):
    """the numbers quoted in the pictures (FlashKa, Balanced profile)"""
    tb, hg = sims["turbo"], sims["high"]
    kv = {}
    for key, i in (("on", 0), ("30s", row_at(tb, 30))):
        kv[key] = {"t": tb["t_s"][i], "mA": tb["led_mA"][i], "T_head": tb["T_head_C"][i], "Tj": tb["Tj"][i],
                   "f": tb["f"][i], "lm_led85": tb["lm_led"][i], "phi": tb["phi"][i], "otf": tb["otf"][i]}
    i0 = 0
    kv["hot"] = {"mA": tb["led_mA"][i0], "Tj": LED["tj_hi"], "f": 1.0, "lm_led85": tb["lm_led"][i0],
                 "phi": tb["lm_led"][i0], "otf": OPTIC["eff"] * tb["lm_led"][i0]}
    for k in kv:
        kv[k]["cd"] = OPTIC["cd_per_lm"] * kv[k]["phi"]
        kv[k]["throw"] = throw_m(kv[k]["cd"])
    i10 = row_at(tb, 600)
    kv["10min"] = {"otf": tb["otf"][i10], "otf85": tb["lm_front"][i10], "mA": tb["led_mA"][i10],
                   "Tj": tb["Tj"][i10], "otf_high": hg["otf"][row_at(hg, 600)]}
    w = (tb["t_s"] >= 900) & (tb["t_s"] <= 1500)                       # 15-25 min after the switch-on
    kv["sustained"] = {"otf": float(tb["otf"][w].mean()), "otf85": float(tb["lm_front"][w].mean()),
                       "mA": float(tb["led_mA"][w].mean()), "Tj": float(tb["Tj"][w].mean()),
                       "T_head": float(tb["T_head_C"][w].mean()), "T_body": float(tb["T_body_C"][w].mean()),
                       "otf_high": float(hg["otf"][(hg["t_s"] >= 900) & (hg["t_s"] <= 1500)].mean())}
    full = tb["led_mA"] >= tb["led_mA"][0]
    # full-current time as the simulation reports it: the time of the first row below the start current
    kv["turbo_full_s"] = float(tb["t_s"][int(np.argmin(full))]) if not full.all() else float("inf")
    fullh = hg["led_mA"] >= hg["led_mA"][0]
    kv["high_full_s"] = float(hg["t_s"][int(np.argmin(fullh))]) if not fullh.all() else float("inf")
    kv["high_on"] = {"mA": hg["led_mA"][0], "otf": hg["otf"][0], "Tj": hg["Tj"][0], "otf85": hg["lm_front"][0]}
    lit = tb["otf"] >= 0.1 * kv["30s"]["otf"]                          # ANSI FL 1 runtime: 10 % of the 30 s value
    kv["runtime_min"] = float(tb["t_s"][np.nonzero(lit)[0][-1]]) / 60.0
    kv["off_min"] = float(tb["t_s"][-1]) / 60.0
    kv["T_body_max"] = float(max(tb["T_body_C"].max(), hg["T_body_C"].max()))
    kv["T_head_max"] = float(max(tb["T_head_C"].max(), hg["T_head_C"].max()))
    kv["Tj_max"] = float(max(tb["Tj"].max(), hg["Tj"].max()))
    kv["T_cell_max"] = (float(max(tb["T_cell_C"].max(), hg["T_cell_C"].max()))
                        if "T_cell_C" in tb and "T_cell_C" in hg else None)
    return kv


def turbo_by_charge(sims, printed, led_model):
    """turbo 30 s after switching on, by the cell's charge at switch-on: the LED current the simulation prints, the
    lumens with the LED at 85 C (the firmware's model x 0.87) and with this script's junction factor.  The head
    temperature for the factor comes from the full-cell and the half-full-cell runs (CSV); for other charges it is
    interpolated in LED power between those two runs (estimate)."""
    if not printed:
        return None
    xs = np.array([p[0] for p in led_model["table"]], float)
    ys = np.array([p[1] for p in led_model["table"]], float)
    anchors = {}
    for key, pct in (("turbo", 100), ("half", 50)):
        if key in sims:
            i = row_at(sims[key], 30)
            anchors[pct] = (float(sims[key]["led_mA"][i]), float(sims[key]["T_head_C"][i]))
    rows = []
    for pct in sorted(printed, reverse=True):
        ma = printed[pct]
        if pct in anchors:
            t_head, how = anchors[pct][1], "simulated head temperature"
            if abs(anchors[pct][0] - ma) > 0.5:
                raise SystemExit("turbo by charge: printed %d mA at %d %% but the CSV has %.0f mA" % (ma, pct,
                                                                                                anchors[pct][0]))
        elif len(anchors) == 2:
            (p1, t1), (p2, t2) = [(float(led_power_w(a[0])), a[1]) for a in (anchors[100], anchors[50])]
            t_head = t1 + (t2 - t1) * (float(led_power_w(ma)) - p1) / (p2 - p1)
            how = "head temperature interpolated (estimate)"
        else:
            t_head, how = None, None
        lm85 = float(np.interp(ma, xs, ys))
        row = {"pct": pct, "mA": ma, "otf85": OPTIC["eff"] * lm85, "how": how}
        if t_head is not None:
            row["Tj"] = float(junction_c(t_head, ma))
            row["otf"] = row["otf85"] * float(temp_factor(row["Tj"]))
        rows.append(row)
    return rows


# ----------------------------------------------------------------------------------------------
# photometry
# ----------------------------------------------------------------------------------------------
TH = np.radians(np.linspace(0.0, 90.0, 3601))      # 0.025 deg grid


class Beam:
    """rotationally symmetric intensity distribution I(theta) in cd"""

    def __init__(self, name, I, info):
        self.name, self.I_tab, self.info = name, np.asarray(I, float), dict(info)

    def I(self, theta):
        return np.interp(theta, TH, self.I_tab, right=0.0)

    @property
    def peak(self):
        return float(self.I_tab[0])

    def flux(self, theta_max=np.pi / 2):
        m = TH <= theta_max + 1e-12
        return float(2 * np.pi * np.trapezoid(self.I_tab[m] * np.sin(TH[m]), TH[m]))


def raised_edge(theta, a_deg, b_deg):
    a, b = np.radians(a_deg), np.radians(b_deg)
    x = np.clip((theta - a) / (b - a), 0.0, 1.0)
    return 0.5 * (1 + np.cos(np.pi * x))


def optic_shape(eff=OPTIC["eff"], peak=OPTIC["cd_per_lm"], fwhm=OPTIC["fwhm_deg"], edge=OPTIC["edge"], spill_pow=1):
    """intensity per LED lumen (cd/lm): a exp(-theta^2/(2 sigma^2)) + b cos^p(theta) S(theta) with a + b = peak,
    2 pi integral(I sin theta) = eff and I(fwhm/2) = peak/2.  For a given sigma, a and b follow linearly from the
    first two conditions; sigma is the one root of the third with a, b >= 0 (scan + bisection).  None if there
    is no such root."""
    g = np.cos(TH) ** spill_pow * raised_edge(TH, *edge)
    om_g = 2 * np.pi * np.trapezoid(g * np.sin(TH), TH)
    th_h = np.radians(fwhm / 2)
    g_h = float(np.interp(th_h, TH, g))

    def parts(sig):
        core = np.exp(-TH ** 2 / (2 * sig * sig))
        om_c = 2 * np.pi * np.trapezoid(core * np.sin(TH), TH)
        if abs(om_c - om_g) < 1e-12:
            return float("nan"), float("nan"), core, om_c
        a = (eff - peak * om_g) / (om_c - om_g)
        return a, peak - a, core, om_c

    def resid(sig):
        a, b, _, _ = parts(sig)
        return a * math.exp(-th_h ** 2 / (2 * sig * sig)) + b * g_h - peak / 2

    grid = np.radians(np.linspace(1.0, 40.0, 391))
    roots = []
    for s0, s1 in zip(grid[:-1], grid[1:]):
        r0, r1 = resid(s0), resid(s1)
        if not (np.isfinite(r0) and np.isfinite(r1)) or r0 * r1 > 0:
            continue
        lo, hi = s0, s1
        for _ in range(100):
            mid = 0.5 * (lo + hi)
            lo, hi = (lo, mid) if resid(lo) * resid(mid) <= 0 else (mid, hi)
        s = 0.5 * (lo + hi)
        a, b, _, _ = parts(s)
        if a >= 0 and b >= 0 and not any(abs(s - r) < 1e-6 for r in roots):
            roots.append(s)
    if len(roots) != 1:
        return None
    sig = roots[0]
    a, b, core, om_c = parts(sig)
    I = a * core + b * g
    I[-1] = 0.0
    m = (TH >= np.radians(25)) & (TH <= np.radians(45))
    return {"I": I, "a": float(a), "b": float(b), "sigma_deg": math.degrees(sig), "spill_share": float(b * om_g / eff),
            "core_share": float(a * om_c / eff), "spill_25_45": float(np.trapezoid(I[m] * np.sin(TH[m]), TH[m]) /
                                                                       np.trapezoid(np.sin(TH[m]), TH[m])),
            "eff": eff, "peak": peak, "fwhm": fwhm, "edge": edge, "spill_pow": spill_pow}


def optic_quad_flux(sh):
    """2 pi integral(I sin theta) of the optic formula by adaptive quadrature (independent of the TH grid)"""
    from scipy.integrate import quad
    sig = math.radians(sh["sigma_deg"])

    def f(t):
        s = float(raised_edge(np.array(t), *sh["edge"]))
        return (sh["a"] * math.exp(-t * t / (2 * sig * sig)) + sh["b"] * math.cos(t) ** sh["spill_pow"] * s) * math.sin(t)
    cuts = [0.0, 3 * sig, math.radians(sh["edge"][0]), math.radians(sh["edge"][1]), math.pi / 2]
    return 2 * math.pi * sum(quad(f, x0, x1, limit=200, epsabs=1e-13, epsrel=1e-11)[0] for x0, x1 in zip(cuts[:-1], cuts[1:]))


def flashka_beam(phi_led, shape, label):
    b = Beam("FlashKa", phi_led * shape["I"], {"phi_led": float(phi_led), "label": label})
    b.info["otf"] = b.flux()
    return b


def measured_fwhm(beam):
    I = beam.I_tab
    k = int(np.argmax(I < I[0] / 2))
    return 2 * math.degrees(float(np.interp(I[0] / 2, [I[k], I[k - 1]], [TH[k], TH[k - 1]])))


def optic_sensitivity(base):
    """spill share and spill brightness (25-45 deg) of the optic model for other assumptions"""
    rows = []
    for name, kw in OPTIC_CASES:
        sh = optic_shape(**kw)
        if sh is None:
            rows.append((name, None))
            continue
        rows.append((name, {"spill_share": sh["spill_share"], "sigma_deg": sh["sigma_deg"], "b": sh["b"],
                            "spill_rel": sh["spill_25_45"] / base["spill_25_45"]}))
    return rows


def flux_beyond(beam, deg):
    m = TH >= np.radians(deg)
    return float(2 * np.pi * np.trapezoid((beam.I_tab * np.sin(TH))[m], TH[m])) / beam.flux()


def a2_beam(I0, flux, share=A2_SPILL_SHARE, edge=A2_SPILL_EDGE):
    """Gaussian hotspot + cos spill with I(0) = I0, integral = flux, spill share = share"""
    gs = np.cos(TH) * raised_edge(TH, *edge)
    om_s = 2 * np.pi * np.trapezoid(gs * np.sin(TH), TH)
    I_s = share * flux / om_s
    I_h = I0 - I_s
    target = (1 - share) * flux / I_h               # solid angle the hotspot must have

    def om_h(sig):
        return 2 * np.pi * np.trapezoid(np.exp(-TH ** 2 / (2 * sig * sig)) * np.sin(TH), TH)
    lo, hi = np.radians(0.5), np.radians(40)
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if om_h(mid) < target else (lo, mid)
    sig = 0.5 * (lo + hi)
    I = I_h * np.exp(-TH ** 2 / (2 * sig * sig)) + I_s * gs
    b = Beam("A2", I, {"I0": I0, "flux": flux, "I_h": I_h, "I_s": I_s, "sigma_deg": float(np.degrees(sig)),
                        "fwhm_deg": float(2 * np.degrees(sig) * math.sqrt(2 * math.log(2))), "share": share,
                        "edge": edge})
    return b


def illuminance(beam, src, axis, pts, normals):
    """E (lx) at points pts (N,3, m) with unit normals (N,3) from a source at src (m) aimed along axis:
    E = I(theta) cos(alpha) / d^2; zero for back-facing surfaces"""
    d = pts - src
    r2 = np.einsum("ij,ij->i", d, d)
    r = np.sqrt(r2)
    u = d / r[:, None]
    cth = np.clip(u @ axis, -1, 1)
    th = np.arccos(cth)
    cal = -np.einsum("ij,ij->i", u, normals)
    E = beam.I(th) * np.clip(cal, 0, None) / r2
    E[cth <= 0] = 0.0
    return E


def throw_m(cd):
    return 2.0 * math.sqrt(cd)


# ----------------------------------------------------------------------------------------------
# FlashKa geometry at the front (housing_interface.json of the CAD, optic STL)
# ----------------------------------------------------------------------------------------------
def flashka_geo(cad_dir):
    path = os.path.join(cad_dir, "housing_interface.json")
    if not os.path.exists(path):
        raise SystemExit("missing %s" % path)
    hi = json.load(open(path))
    p, seat = hi.get("params", {}), hi.get("optic_seat", {})
    for k in ("Y_w", "Z_axis", "opt_bore", "opt_exit_d", "opt_recess"):
        if k not in p:
            raise SystemExit("%s: params.%s missing" % (path, k))
    g = {"version": str(hi.get("version")), "Y_w": float(p["Y_w"]), "Z_axis": float(p["Z_axis"]),
         "bore_d": float(p["opt_bore"]), "exit_d": float(p["opt_exit_d"]), "recess": float(p["opt_recess"])}
    rec = seat.get("optic_front_recess_behind_the_front_face", [g["recess"]] * 3)
    g["recess_range"] = tuple(float(v) for v in rec)
    # vignetting by the bore mouth: a ray from the edge of the exit clears it up to this angle
    g["clear_deg"] = {lab: math.degrees(math.atan((g["bore_d"] - g["exit_d"]) / 2 / r))
                      for lab, r in (("nominal", g["recess_range"][1]), ("deepest", g["recess_range"][2]))}
    lens = os.path.join(cad_dir, "_ref_optic_lens.stl")
    g["x_exit"], g["exit_src"] = g["recess"], "params.opt_recess in housing_interface.json"
    if os.path.exists(lens):
        pd = polydata_from_stl(lens)
        b = pd.GetBounds()
        g["x_exit"], g["exit_src"] = float(b[0]), "the lens in `_ref_optic_lens.stl`"
        g["lens_axis_yz"] = ((b[2] + b[3]) / 2, (b[4] + b[5]) / 2)
    g["optic_mass_g"] = hi.get("thermal_model_inputs", {}).get(
        "optic_mass_g (PMMA lens 1.19 + PC holder 1.20 g/cm3, drawn shape)")
    g["led_board_g"] = hi.get("summary", {}).get("thermal_model_inputs", {}).get("led_board_copper_mass_g")
    return g


# ----------------------------------------------------------------------------------------------
# energy-balance tests
# ----------------------------------------------------------------------------------------------
def _wall_integral(beam, d=2.0, half=7.5, n=6001):
    """illuminance integrated over a perpendicular square wall (side 2 half) at distance d (midpoint rule)"""
    s = (np.arange(n) + 0.5) / n * 2 * half - half
    h = 2 * half / n
    tot = 0.0
    src, ax = np.zeros(3), np.array([1.0, 0, 0])
    for i0 in range(0, n, 500):
        Y, Z = np.meshgrid(s[i0:i0 + 500], s)
        P = np.stack([np.full(Y.size, d), Y.ravel(), Z.ravel()], 1)
        N = np.tile([-1.0, 0, 0], (Y.size, 1))
        tot += illuminance(beam, src, ax, P, N).sum() * h * h
    return tot


def _tilted_check(beam, d=2.0, tilt_deg=40.0, half=(2.5, 2.0), n=(2501, 2001), nd=(1801, 3600)):
    """finite plane through (d,0,0), normal tilted by tilt_deg about z, region |u|<half0, |w|<half1:
    area integral of E vs the angular integral of I over the directions that hit the region"""
    t = np.radians(tilt_deg)
    nrm = np.array([-math.cos(t), -math.sin(t), 0.0])        # faces the source
    eu = np.array([-math.sin(t), math.cos(t), 0.0])         # in-plane, horizontal
    ew = np.array([0.0, 0.0, 1.0])
    c = np.array([d, 0.0, 0.0])
    su = (np.arange(n[0]) + 0.5) / n[0] * 2 * half[0] - half[0]
    sw = (np.arange(n[1]) + 0.5) / n[1] * 2 * half[1] - half[1]
    area = 0.0
    for i0 in range(0, n[0], 400):
        Uu, Ww = np.meshgrid(su[i0:i0 + 400], sw)
        P = c + Uu.ravel()[:, None] * eu + Ww.ravel()[:, None] * ew
        area += illuminance(beam, np.zeros(3), np.array([1.0, 0, 0]), P, np.tile(nrm, (len(P), 1))).sum()
    area *= (2 * half[0] / n[0]) * (2 * half[1] / n[1])
    # angular side: theta (off axis x) and phi grids, midpoint rule on the sphere
    th = (np.arange(nd[0]) + 0.5) / nd[0] * (np.pi / 2)
    ph = (np.arange(nd[1]) + 0.5) / nd[1] * 2 * np.pi
    dth, dph = (np.pi / 2) / nd[0], 2 * np.pi / nd[1]
    ang = 0.0
    for i0 in range(0, nd[0], 200):
        T_, P_ = np.meshgrid(th[i0:i0 + 200], ph, indexing="ij")
        dirs = np.stack([np.cos(T_), np.sin(T_) * np.cos(P_), np.sin(T_) * np.sin(P_)], -1).reshape(-1, 3)
        den = dirs @ (-nrm)
        hit = den > 1e-9
        s = np.where(hit, (c @ (-nrm)) / np.maximum(den, 1e-12), 0.0)
        X = dirs * s[:, None]
        rel = X - c
        inside = hit & (np.abs(rel @ eu) <= half[0]) & (np.abs(rel @ ew) <= half[1])
        w = (np.sin(T_).ravel() * dth * dph)
        ang += np.sum(beam.I(T_.ravel())[inside] * w[inside])
    return area, ang


def run_tests(M, report):
    ok = True

    def check(name, got, want, tol, absolute=False):
        nonlocal ok
        err = abs(got - want) if absolute else abs(got - want) / max(abs(want), 1e-12)
        good = err <= tol
        ok &= good
        if absolute:
            line = "  [%s] %-58s %12.4f vs %12.4f  (deviation %.3f, limit %.3f)" % ("PASS" if good else "FAIL", name, got,
                                                                                 want, err, tol)
        else:
            line = "  [%s] %-58s %12.4f vs %12.4f  (%.3f %%, limit %.2f %%)" % ("PASS" if good else "FAIL", name, got,
                                                                               want, err * 100, tol * 100)
        log(line)
        report.append(line.strip())

    # inputs: the simulator's LED lumens are board.rs's LED model, and the optic factor is LEDiL's 87 %
    lm = M["led_model"]
    xs, ys = np.array([p[0] for p in lm["table"]], float), np.array([p[1] for p in lm["table"]], float)
    dev, dev_f = 0.0, 0.0
    for sc in M["sims"].values():
        dev = max(dev, float(np.max(np.abs(np.interp(sc["led_mA"], xs, ys) - sc["lm_led"]))))
        dev_f = max(dev_f, float(np.max(np.abs(sc["lm_led"] * lm["optic_pct"] / 100.0 - sc["lm_front"]))))
    check("simulator LED lumens = board.rs LED_LM_TABLE, every row (lm)", dev, 0.0, 0.06, absolute=True)
    check("simulator front lumens = OPTIC_PCT x LED lumens, every row (lm)", dev_f, 0.0, 0.06, absolute=True)
    check("board.rs OPTIC_PCT = LEDiL efficiency used here (%)", float(lm["optic_pct"]), 100 * OPTIC["eff"], 1e-9,
          absolute=True)
    check("junction factor at Tj 25 C (datasheet 748 / 680 lm)", float(temp_factor(25.0)),
          LED["lm_1500_25"] / LED["lm_1500_85"], 1e-3)
    check("junction factor at Tj 85 C", float(temp_factor(85.0)), 1.0, 1e-12)
    # Lambertian sanity: I = Phi/pi cos(theta) integrates to Phi; on a centred square wall (half side a at
    # distance d) it delivers Phi times the view factor (4/pi) A/sqrt(1+A^2) atan(A/sqrt(1+A^2)), A = a/d
    lam = Beam("lambert", 1000.0 / np.pi * np.cos(TH), {})
    check("Lambertian 1000 lm: angular integral (lm)", lam.flux(), 1000.0, 1e-4)
    A = 20.0 / 2.0
    vf = 4 / np.pi * A / math.sqrt(1 + A * A) * math.atan(A / math.sqrt(1 + A * A))
    check("Lambertian 1000 lm: 40 m wall at 2 m = view factor (lm)", _wall_integral(lam, half=20.0, n=4001),
          1000.0 * vf, 2e-3)
    sh = M["shape"]
    check("FlashKa optic model: grid integral = quadrature (per LED lm)", float(2 * np.pi * np.trapezoid(sh["I"] * np.sin(TH), TH)),
          optic_quad_flux(sh), 1e-4)
    for b in (M["fk"], M["a2"]):
        if b.name == "A2":
            check("%s: angular integral = its lumens (lm)" % b.name, b.flux(), b.info["flux"], 1e-3)
            check("%s: peak = its candela (cd)" % b.name, b.peak, b.info["I0"], 1e-9)
        else:
            phi = b.info["phi_led"]
            check("%s: peak = %.1f cd/lm x LED lumens (cd)" % (b.name, OPTIC["cd_per_lm"]), b.peak,
                  OPTIC["cd_per_lm"] * phi, 1e-9)
            check("%s: angular integral = %.2f x LED lumens (lm)" % (b.name, OPTIC["eff"]), b.flux(), OPTIC["eff"] * phi,
                  1e-4)
            check("%s: full width at half maximum (deg)" % b.name, measured_fwhm(b), OPTIC["fwhm_deg"], 1e-3)
        check("%s: wall integral at 2 m = lumens (lm)" % b.name, _wall_integral(b), b.flux(), 5e-3)
        a, g = _tilted_check(b)
        check("%s: inclined plane (40 deg): area = solid-angle flux" % b.name, a, g, 5e-3)
        for d in (2.0, 5.0):
            E = illuminance(b, np.zeros(3), np.array([1.0, 0, 0]), np.array([[d, 0, 0]]),
                            np.array([[-1.0, 0, 0]]))[0]
            check("%s: E d^2 on axis at %.0f m = peak (cd)" % (b.name, d), E * d * d, b.peak, 1e-6)
    if not ok:
        raise SystemExit("photometry tests failed")
    return ok


# ----------------------------------------------------------------------------------------------
# pictures: common helpers
# ----------------------------------------------------------------------------------------------
INK, INK2, MUTED = (11, 11, 11), (82, 81, 78), (137, 135, 129)
GRID, AXIS = "#e1e0d9", "#c3c2b7"
PAGE_BG = (255, 255, 255)                  # GitHub light page
PAGE_BG_D = (13, 17, 23)                   # GitHub dark page (#0d1117)
INK_D, INK2_D, MUTED_D = (240, 239, 236), (195, 194, 183), (137, 135, 129)


_FONTS = {}


def font(size, bold=False):
    """DejaVu Sans (ships with matplotlib, so no system font path is needed)"""
    from PIL import ImageFont
    if bold not in _FONTS:
        import matplotlib.font_manager as fm
        _FONTS[bold] = fm.findfont(fm.FontProperties(family="DejaVu Sans", weight="bold" if bold else "normal"),
                                   fallback_to_default=True)
    return ImageFont.truetype(_FONTS[bold], int(round(size)))


def save_png(im, path):
    """PNG without any text, time, ICC or EXIF chunks (a fresh image from the raw pixels)"""
    from PIL import Image
    im = im.convert("RGB")
    clean = Image.frombytes("RGB", im.size, im.tobytes())
    clean.save(path, format="PNG", optimize=True)
    log("wrote", path, clean.size)


def fmt_int(x):
    return "{:,}".format(int(round(x)))


# ----------------------------------------------------------------------------------------------
# picture: output over time
# ----------------------------------------------------------------------------------------------
def _text_line_hits(fig, axes, rend):
    """text boxes that a data line passes through (display coordinates, lines densified to 0.5 px)"""
    hits = []
    texts = [t for t in fig.texts + [t for a in axes for t in a.texts] if t.get_text()]
    for a in axes:
        for ln in a.get_lines():
            if ln.get_gid() != "data":
                continue
            xy = a.transData.transform(np.column_stack(ln.get_data()))
            seg = []
            for p0, p1 in zip(xy[:-1], xy[1:]):
                n = max(2, int(np.hypot(*(p1 - p0)) / 0.5) + 1)
                seg.append(p0 + (p1 - p0) * np.linspace(0, 1, n)[:, None])
            pts = np.vstack(seg) if seg else xy
            for t in texts:
                b = t.get_window_extent(rend).padded(1.0)
                if np.any((pts[:, 0] > b.x0 + 1) & (pts[:, 0] < b.x1 - 1) & (pts[:, 1] > b.y0 + 1) & (pts[:, 1] < b.y1 - 1)):
                    hits.append((ln.get_label()[:24], t.get_text()[:30]))
    return hits


def picture_output(M, out_dir, scale=2.0):
    """lumens out of the front on one y-axis, as two panels with the same y scale: the first 2 minutes and the
    first 15 minutes.  FlashKa: simulated (Balanced turbo and High: LED datasheet lumens x junction factor x
    0.87) and its sustained level; A2: the three points measured by 1lumen."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.ticker import FuncFormatter
    from PIL import Image
    sims, kv = M["sims"], M["kv"]
    tb, hg = sims["turbo"], sims["high"]
    W, H = 1160, 730                                    # layout at 1x (px); rendered at `scale`
    dpi = 100 * scale
    px = 72.0 / 100                                     # points per 1x pixel
    plt.rcParams.update({"font.family": "DejaVu Sans", "axes.linewidth": 1.0 * px})
    fig = plt.figure(figsize=(W / 100, H / 100), dpi=dpi)
    fig.patch.set_facecolor("white")
    L, R, B, T = 100, 200, 196, 160                     # margins at 1x (px)
    gap, w1 = 40, 300                                   # gap between the panels, width of the first panel
    w2 = W - L - R - gap - w1
    ph = H - B - T
    ax1 = fig.add_axes([L / W, B / H, w1 / W, ph / H])
    ax2 = fig.add_axes([(L + w1 + gap) / W, B / H, w2 / W, ph / H])
    lw = 2.0 * px
    dash = (0, (3.2, 2.2))
    ymax = 1200
    sus = kv["sustained"]["otf"]
    ink, ink2 = "#0b0b0b", "#52514e"
    for ax, scl, t_end in ((ax1, 1.0, 120.0), (ax2, 60.0, 900.0)):
        for sc, ls, z, lab in ((hg, dash, 3, "FlashKa High"), (tb, "-", 4, "FlashKa Turbo")):
            m = sc["t_s"] <= t_end + 1e-6
            ax.plot(sc["t_s"][m] / scl, sc["otf"][m], color=BLUE, lw=lw, ls=ls, solid_capstyle="round",
                    solid_joinstyle="round", dash_capstyle="butt", zorder=z, gid="data", label=lab)
        tm = np.array(A2["meas_t_s"]) / scl
        keep = tm <= t_end / scl + 1e-9
        ax.plot(tm[keep], np.array(A2["meas_lm"])[keep], ls="none", marker="o", ms=9 * px, mfc=ORANGE, mec="white",
                mew=2 * px, zorder=6, clip_on=False, gid="marker")
        ax.set_xlim(0, t_end / scl)
        ax.set_ylim(0, ymax)
        ax.set_yticks(range(0, ymax + 1, 200))
        ax.grid(axis="y", color=GRID, lw=1.0 * px, zorder=0)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.spines["bottom"].set_color(AXIS)
        ax.tick_params(colors=ink2, length=0, pad=7, labelsize=11)
    ax1.yaxis.set_major_formatter(FuncFormatter(lambda v, _: "{:,}".format(int(v))))
    ax2.tick_params(labelleft=False)
    ax1.set_xticks([0, 30, 60, 90, 120])
    ax2.set_xticks(range(0, 16))
    # the sustained level, in the long panel
    ax2.plot([0, 15], [sus, sus], color=BLUE, lw=1.0 * px, ls=(0, (1, 2.6)), zorder=2, gid="ref")
    # the 30 s values (ANSI FL 1) of the FlashKa turbo, marked like the A2's
    i30 = row_at(tb, 30)
    ax1.plot([30], [tb["otf"][i30]], ls="none", marker="o", ms=9 * px, mfc=BLUE, mec="white", mew=2 * px, zorder=6,
             gid="marker")
    ax1.set_xlabel("Seconds after switching on", color=ink2, fontsize=11.5, labelpad=9)
    ax2.set_xlabel("Minutes after switching on", color=ink2, fontsize=11.5, labelpad=9)
    ax1.set_ylabel("Light out of the front (lm)", color=ink2, fontsize=11.5, labelpad=10)
    for ax, txt_ in ((ax1, "First 2 minutes"), (ax2, "First 15 minutes")):
        ax.text(0, 1.0, txt_, transform=ax.transAxes, fontsize=11, color=ink2, fontweight="bold", va="bottom",
                ha="left")
    txt = dict(fontsize=11, color=ink, va="center")
    on, s30, hon = kv["on"]["otf"], kv["30s"]["otf"], kv["high_on"]["otf"]
    # direct labels: each takes the first of its candidate places (offsets from its point in data units, and the
    # alignment) that stays inside its panel, overlaps no other label and has no data line through it, so the
    # labels follow the curves when the simulation changes
    fig.canvas.draw()
    rend = fig.canvas.get_renderer()
    line_pts, mark_pts = {}, {}
    for a in (ax1, ax2):
        pts = []
        mark_pts[a] = np.vstack([a.transData.transform(np.column_stack(ln.get_data())) for ln in a.get_lines()
                                 if ln.get_gid() == "marker"])
        for ln in a.get_lines():
            if ln.get_gid() != "data":
                continue
            xy = a.transData.transform(np.column_stack(ln.get_data()))
            for p0, p1 in zip(xy[:-1], xy[1:]):
                n = max(2, int(np.hypot(*(p1 - p0)) / 0.5) + 1)
                pts.append(p0 + (p1 - p0) * np.linspace(0, 1, n)[:, None])
        line_pts[a] = np.vstack(pts)
    placed = []

    def place(a, text, xy, cands):
        """cands: (dx, dy, ha) or (dx, dy, ha, other wording of the label, e.g. on two lines)"""
        box_ax = a.get_window_extent(rend)
        for cand in cands:
            dx, dy, ha = cand[:3]
            t = a.annotate(cand[3] if len(cand) > 3 else text, xy, xytext=(xy[0] + dx, xy[1] + dy), textcoords="data",
                           ha=ha, multialignment="center", linespacing=1.3, **txt)
            raw = t.get_window_extent(rend)
            b = raw.padded(3.0 * scale)                              # keep a visible gap around the label
            p, q, r = line_pts[a], mark_pts[a], 6.0 * scale          # r: marker radius + ring + gap (px)
            own = a.transData.transform(xy)
            q = q[np.hypot(q[:, 0] - own[0], q[:, 1] - own[1]) > 1.0]  # a label may sit next to its own marker
            inside = (raw.x0 >= box_ax.x0 + 2 and raw.x1 <= box_ax.x1 - 2 and raw.y0 >= box_ax.y0 + 2
                      and raw.y1 <= box_ax.y1 - 2)
            free = (inside
                    and not any(b.overlaps(o) for o in placed)
                    and not np.any((p[:, 0] > b.x0) & (p[:, 0] < b.x1) & (p[:, 1] > b.y0) & (p[:, 1] < b.y1))
                    and not np.any((q[:, 0] > b.x0 - r) & (q[:, 0] < b.x1 + r) & (q[:, 1] > b.y0 - r) & (q[:, 1] < b.y1 + r)))
            if free:
                placed.append(b)
                return t
            if os.environ.get("COMPARE_DEBUG_LABELS"):
                log("   label %r at %s: inside %s, overlaps %s, line %s, marker %s" % (
                    text, (dx, dy, ha), inside, [round(o.y0) for o in placed if b.overlaps(o)],
                    bool(np.any((p[:, 0] > b.x0) & (p[:, 0] < b.x1) & (p[:, 1] > b.y0) & (p[:, 1] < b.y1))),
                    bool(np.any((q[:, 0] > b.x0 - r) & (q[:, 0] < b.x1 + r) & (q[:, 1] > b.y0 - r) & (q[:, 1] < b.y1 + r)))))
            t.remove()
        raise SystemExit("output chart: no free place for the label %r - add a candidate place (COMPARE_DEBUG_LABELS=1 "
                         "shows why each place was rejected)" % text)

    p1 = A2["meas_lm"]
    place(ax1, "Turbo: %s lm at switch-on" % fmt_int(on), (1, on), [(1.5, 62, "left"), (1.5, 120, "left")])
    l30 = "%s lm at 30 s" % fmt_int(s30)
    place(ax1, l30, (30, s30), [(6, 6, "left"), (-3, -68, "center"), (0, -95, "center"),
                                (0, -95, "center", l30.replace(" at ", "\nat ")), (0, 66, "center"), (6, -60, "left")])
    place(ax1, "High: %s lm" % fmt_int(hon), (1, hon), [(2, 56, "left"), (2, -60, "left"), (2, 110, "left")])
    place(ax1, "%d lm" % p1[0], (0, p1[0]), [(3.5, -48, "left"), (3.5, 50, "left"), (3.5, -100, "left")])
    place(ax1, "%d lm at 30 s" % p1[1], (30, p1[1]), [(5, -4, "left"), (0, -58, "center"), (0, 60, "center")])
    place(ax2, "%d lm at 10 min" % p1[2], (10, p1[2]), [(0.35, 0, "left"), (0, -55, "center"), (0, 55, "center")])
    x_lab = ax2.transData.transform((15, 0))[0] + 14 * scale
    inv = ax2.transData.inverted().transform
    ax2.annotate("FlashKa sustained:\n%d lm" % round(sus), (15, sus), xytext=(inv((x_lab, 0))[0], sus),
                 textcoords="data", annotation_clip=False, linespacing=1.35, **txt)
    # title, subtitle, legend
    fig.text(L / W, 1 - 26 / H, "Light output over the first 15 minutes", fontsize=16, fontweight="bold",
             color=ink, va="center")
    fig.text(L / W, 1 - 53 / H, "Lumens out of the front at 25 °C.  FlashKa: simulated from datasheets, not yet built.  "
             "RovyVon Aurora A2: measured by 1lumen.", fontsize=11.5, color=ink2, va="center")
    handles = [Line2D([0], [0], color=BLUE, lw=lw),
               Line2D([0], [0], color=BLUE, lw=lw, ls=dash),
               Line2D([0], [0], color=ORANGE, ls="none", marker="o", ms=9 * px, mec="white", mew=2 * px)]
    labels = ["FlashKa v0.7, Turbo (simulated)", "FlashKa v0.7, High (simulated)", "RovyVon Aurora A2, High (measured)"]
    fig.legend(handles, labels, loc="center left", bbox_to_anchor=(L / W - 0.008, 1 - 92 / H), ncol=3,
               frameon=False, fontsize=10.5, handlelength=2.4, columnspacing=1.8, labelcolor=ink,
               handletextpad=0.6)
    kh = kv["hot"]
    note = ("FlashKa: firmware 0.7.0 thermal simulation (cargo test --features board-v07 --test thermal_v07), "
            "Balanced profile, 25 °C still air, full 1,500 mAh cell.\n"
            "Out of the front = LED datasheet lumens at Tj 85 °C (firmware board.rs) × junction factor (1.10 at 25 °C to "
            "1.00 at 85 °C; Tj = simulated head\n"
            "temperature + 1.6 °C/W × 70 %% of the LED power) × 0.87 optic (LEDiL data, simulated).  Turbo %s mA, High "
            "%s mA.  Sustained: mean of 15–25 min\n"
            "(%d lm with the LED at 85 °C; turbo at 85 °C: %d lm).  RovyVon Aurora A2 (Gen 3): "
            "1lumen.com/review/rovyvon-a2, three published points;\nthe curve between them is published only as a picture."
            % (fmt_int(kv["on"]["mA"]), fmt_int(kv["high_on"]["mA"]), round(kv["sustained"]["otf85"]), round(kh["otf"])))
    fig.text(L / W, 14 / H, note, fontsize=9.2, color=ink2, va="bottom", linespacing=1.5)
    # layout check: every text inside the figure, no two texts overlapping, no data line through a text
    fig.canvas.draw()
    rend = fig.canvas.get_renderer()
    wpx, hpx = fig.canvas.get_width_height()
    texts = [t for t in fig.texts + ax1.texts + ax2.texts if t.get_text()]
    boxes = [(t.get_text()[:30], t.get_window_extent(rend)) for t in texts]
    bad = []
    for i, (n1, b1) in enumerate(boxes):
        if b1.x0 < 0 or b1.y0 < 0 or b1.x1 > wpx or b1.y1 > hpx:
            bad.append(("outside", n1))
        for n2, b2 in boxes[i + 1:]:
            if b1.overlaps(b2):
                bad.append(("overlap", n1, n2))
    lg = fig.legends[0].get_window_extent(rend)
    if lg.x1 > wpx:
        bad.append(("legend outside", lg.x1, wpx))
    bad += [("line through text",) + h for h in _text_line_hits(fig, (ax1, ax2), rend)]
    if bad:
        log("  chart layout findings:", bad)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, facecolor="white", metadata={"Software": None})
    plt.close(fig)
    buf.seek(0)
    im = Image.open(buf).convert("RGB")
    path = os.path.join(out_dir, "comparison_output.png")
    save_png(im, path)
    return {"path": path, "layout_findings": bad}


# ----------------------------------------------------------------------------------------------
# 3D models (VTK poly data in mm)
# ----------------------------------------------------------------------------------------------
# PBR materials: base colour (linear), metallic, roughness
MAT = {
    "anodised": ((0.045, 0.046, 0.050), 0.30, 0.40),     # black bead-blasted anodised 6061
    "pom": ((0.035, 0.035, 0.036), 0.0, 0.70),            # matte black POM-C
    "rubber": ((0.018, 0.018, 0.018), 0.0, 0.90),
    "pmma": ((0.55, 0.60, 0.62), 0.0, 0.08),
    "steel": ((0.55, 0.56, 0.57), 1.0, 0.32),             # stainless screws
    "glass": ((0.04, 0.05, 0.06), 0.0, 0.05),
    "led": ((0.80, 0.70, 0.25), 0.0, 0.35),
    "standin": ((0.12, 0.122, 0.128), 0.35, 0.38),        # A2 size stand-in: neutral dark grey, no markings
    "standin_ring": ((0.30, 0.30, 0.31), 1.0, 0.35),
    "standin_lens": ((0.035, 0.04, 0.045), 0.0, 0.22),
    "brass": ((0.62, 0.50, 0.30), 1.0, 0.40),               # laser module front, seen through its aperture
    "pcb": ((0.012, 0.012, 0.013), 0.0, 0.45),             # black solder mask (v0.7 panel)
    "plastic_w": ((0.70, 0.70, 0.69), 0.0, 0.55),
    "optic_lens": ((0.62, 0.66, 0.68), 0.0, 0.06),         # clear PMMA lens of the TIR optic (drawn see-through)
    "optic_holder": ((0.020, 0.020, 0.021), 0.0, 0.50),    # black PC holder of the optic
}
SEE_THROUGH = {"glass": 0.28, "optic_lens": 0.30}         # opacity of the clear parts in the size views


def _vtk():
    import vtk
    return vtk


def polydata_from_stl(path):
    vtk = _vtk()
    r = vtk.vtkSTLReader()
    r.SetFileName(path)
    r.Update()
    return r.GetOutput()


def polydata_from_shape(shape, tol=0.01, ang=0.15):
    vtk = _vtk()
    from vtk.util.numpy_support import numpy_to_vtk
    verts, tris = shape.tessellate(tol, ang)
    pts = np.array([[v.x, v.y, v.z] for v in verts], float)
    cells = np.array(tris, np.int64).reshape(-1, 3)
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


def transformed(pd, rot_z_deg=0.0, translate=(0, 0, 0), rot_x_deg=0.0):
    vtk = _vtk()
    t = vtk.vtkTransform()
    t.PostMultiply()
    t.RotateX(rot_x_deg)
    t.RotateZ(rot_z_deg)
    t.Translate(*translate)
    f = vtk.vtkTransformPolyDataFilter()
    f.SetInputData(pd)
    f.SetTransform(t)
    f.Update()
    return f.GetOutput()


def flashka_parts(cad_dir):
    """[(name, polydata in the housing frame, material)] - tray and lid required; other exterior STLs when
    present and already in place (keys that are stored centred on their axes sit on the bottom face, which
    none of these views shows, so they are skipped)"""
    parts = []
    for req in ("FlashKa_tray", "FlashKa_lid"):
        p = os.path.join(cad_dir, req + ".stl")
        if not os.path.exists(p):
            raise SystemExit("missing %s" % p)
        parts.append((req, polydata_from_stl(p), "anodised"))
    refs = {"_ref_window": "glass", "_ref_led": "led", "_ref_lidscrews": "steel", "_ref_laser": "brass",
            "_ref_usb": "steel", "_ref_pcb": "pcb", "_ref_s2_knob": "plastic_w", "_ref_optic_lens": "optic_lens",
            "_ref_optic_holder": "optic_holder"}
    for p in sorted(glob.glob(os.path.join(cad_dir, "*.stl"))):
        n = os.path.splitext(os.path.basename(p))[0]
        low = n.lower()
        if n in ("FlashKa_tray", "FlashKa_lid") or any(w in low for w in ("stiffener", "spacer", "sleeve", "kit",
                                                                          "icon", "splitring", "mould")):
            continue                      # internal parts, tools (key moulds) and loose accessories
        if low in refs:
            mat = refs[low]
        elif "key_side" in low or ("key" in low and "main" not in low and not low.startswith("_ref_")):
            mat = "rubber"
        elif "key_main" in low or "cap_main" in low:
            mat = "pmma"
        elif "cap_slide" in low:
            mat = "rubber"
        elif low.startswith("flashka_") and any(k in low for k in ("rf_window", "insert", "plug")):
            mat = "pom"
        else:
            continue                      # internal parts (cells, key board, pogo pins, spacers, ...)
        pd = polydata_from_stl(p)
        b = pd.GetBounds()
        if (abs((b[0] + b[1]) / 2) < 4 and abs((b[2] + b[3]) / 2) < 4 and b[0] < 0):
            continue                      # stored centred on its own axis: not in place
        parts.append((n, pd, mat))
    return parts


def a2_standin_parts():
    """plain size stand-in of the A2 from its published size (57.3 x 15.6 mm): rounded tube, lens face,
    one clip ring. Axis = X, tail at X = 0, lens face at X = L. No logo, no copied details."""
    import cadquery as cq
    L, D = A2["length_mm"], A2["dia_mm"]
    R = D / 2
    body = cq.Workplane("YZ").circle(R).extrude(L)
    body = body.faces("<X").edges().fillet(2.2)
    body = body.faces(">X").edges().chamfer(0.7)
    body = body.cut(cq.Workplane("YZ").workplane(offset=L - 0.8).circle(R - 1.30).extrude(2))
    lens = cq.Workplane("YZ").workplane(offset=L - 1.1).circle(R - 1.36).extrude(0.5)   # face 0.6 behind the bezel
    ring = (cq.Workplane("YZ").workplane(offset=9.0).circle(R + 0.25).circle(R - 0.3).extrude(2.4)
            .edges().fillet(0.25))
    return [("A2_body", polydata_from_shape(body.val()), "standin"),
            ("A2_lens", polydata_from_shape(lens.val()), "standin_lens"),
            ("A2_ring", polydata_from_shape(ring.val()), "standin_ring")]


def light_in_scene(kind, cad_dir, geo):
    """parts placed in the beam scene (mm): beam along +x, front face at x = 0, beam axis at y = 0,
    the light resting on the table z = 0; returns (parts, emission point, axis)"""
    if kind == "fk":
        out = []
        for n, pd, mat in flashka_parts(cad_dir):
            # housing X (front -> tail) becomes -x, Y becomes -y; the LED axis (Y_w) lands on y = 0
            out.append((n, transformed(pd, 180.0, (0.0, geo["Y_w"], 0.0)), mat))
        src = np.array([-geo["x_exit"], 0.0, geo["Z_axis"]])     # centre of the optic's exit face
    else:
        out = []
        L, R = A2["length_mm"], A2["dia_mm"] / 2
        for n, pd, mat in a2_standin_parts():
            out.append((n, transformed(pd, 0.0, (-L, 0.0, R + 0.25)), mat))
        src = np.array([0.0, 0.0, R + 0.25])
    return out, src, np.array([1.0, 0.0, 0.0])


# ----------------------------------------------------------------------------------------------
# beam scene (mm): table top z = 0 for x <= EDGE_X, white wall at x = WALL_X, floor below
# ----------------------------------------------------------------------------------------------
WALL_X, EDGE_X, FLOOR_Z = 2000.0, 3.0, -750.0
RHO_WALL, RHO_TABLE, RHO_FLOOR = 0.85, 0.016, 0.20
E_AMB = 3.0                                    # lx: the dim room, on every surface, both panels
L_CEIL = E_AMB / np.pi                         # cd/m2 of the dim room / ceiling seen from the lights
KEY = {"pos": np.array([-760.0, -520.0, 640.0]), "aim": np.array([-45.0, 0.0, 6.0]), "I": 450.0,
       "cone": (4.0, 9.5), "radius": 60.0}    # soft spot lamp on the light body, same in both panels
HAZE_SIGMA = 0.004                             # 1/m, light haze (about 1 km visibility), isotropic scattering
CAM = {"pos": np.array([-230.0, -52.0, 84.0]), "look": None, "vfov": 55.0, "target": (0.53, 0.38)}
# colours (linear RGB, luminance Y = 1): both beams the same neutral white, so colour plays no part in the
# comparison; the lamp and the room are warm (staging, identical in both panels)
C_BEAM = np.array([1.0, 1.0, 1.0])
C_LAMP = np.array([1.10, 0.99, 0.84]) / (0.2126 * 1.10 + 0.7152 * 0.99 + 0.0722 * 0.84)
C_AMB = np.array([1.04, 0.995, 0.95]) / (0.2126 * 1.04 + 0.7152 * 0.995 + 0.0722 * 0.95)
TABLE_TINT = np.array([1.06, 1.0, 0.92])
TABLE_F0, TABLE_ALPHA = 0.04, 0.40             # satin finish of the dark table (GGX microfacet sheen)
PANEL = (1152, 864)                            # px per panel (final)


def normalize(v):
    v = np.asarray(v, float)
    return v / np.linalg.norm(v, axis=-1, keepdims=True)


def cam_basis(cam):
    f = normalize(cam["look"] - cam["pos"])
    r = normalize(np.cross(f, [0.0, 0.0, 1.0]))
    u = np.cross(r, f)
    return f, r, u


def pixel_rays(cam, W, H):
    f, r, u = cam_basis(cam)
    th = math.tan(math.radians(cam["vfov"]) / 2)
    j, i = np.mgrid[0:H, 0:W].astype(np.float32)
    sx = (2 * (i + 0.5) / W - 1) * th * (W / H)
    sy = (1 - 2 * (j + 0.5) / H) * th
    d = f[None, None, :] + sx[..., None] * r[None, None, :] + sy[..., None] * u[None, None, :]
    return normalize(d.reshape(-1, 3))


def project(cam, P, W, H):
    """world points (N,3) -> pixel coordinates (N,2) of the same pinhole as pixel_rays"""
    f, r, u = cam_basis(cam)
    th = math.tan(math.radians(cam["vfov"]) / 2)
    d = P - cam["pos"]
    z = d @ f
    sx, sy = (d @ r) / z, (d @ u) / z
    return np.stack([((sx / (th * W / H)) + 1) * W / 2 - 0.5, (1 - sy / th) * H / 2 - 0.5], 1)


def trace_planes(C, D):
    """nearest hit of rays C + t D with the table top, the wall and the floor:
    kind 0 none, 1 table, 2 wall, 3 floor; points (N,3)"""
    n = len(D)
    t = np.full(n, np.inf)
    kind = np.zeros(n, np.int8)
    with np.errstate(divide="ignore", invalid="ignore"):
        tw = np.where(D[:, 0] > 1e-9, (WALL_X - C[0]) / D[:, 0], np.inf)
        tt = np.where(D[:, 2] < -1e-9, (0.0 - C[2]) / D[:, 2], np.inf)
        tf = np.where(D[:, 2] < -1e-9, (FLOOR_Z - C[2]) / D[:, 2], np.inf)
    xt = C[0] + tt * D[:, 0]
    tt = np.where(xt <= EDGE_X, tt, np.inf)
    xf = C[0] + tf * D[:, 0]
    tf = np.where((xf > EDGE_X) & (xf < WALL_X), tf, np.inf)
    for k, tk in ((2, tw), (1, tt), (3, tf)):
        m = (tk > 0) & (tk < t)
        t[m] = tk[m]
        kind[m] = k
    P = C[None, :] + D * np.where(np.isfinite(t), t, 0.0)[:, None]
    return kind, P, t


def key_illuminance(P, normals):
    """the foreground lamp: a soft spot (smooth cone), E = I(psi) cos(alpha) / d^2 (lx, P in mm)"""
    d = P - KEY["pos"]
    r2 = np.einsum("ij,ij->i", d, d) / 1e6
    u = normalize(d)
    ax = normalize(KEY["aim"] - KEY["pos"])
    psi = np.degrees(np.arccos(np.clip(u @ ax, -1, 1)))
    a, b = KEY["cone"]
    prof = 0.5 * (1 + np.cos(np.pi * np.clip((psi - a) / (b - a), 0, 1)))
    cal = np.clip(-np.einsum("ij,ij->i", u, normals), 0, None)
    return KEY["I"] * prof * cal / r2


def _lattice_noise(x, y, cell, seed):
    """smooth value noise on a random lattice (bilinear with smoothstep), x, y in mm"""
    rng = np.random.default_rng(seed)
    n = 257
    g = rng.random((n, n)).astype(np.float32)
    gx, gy = x / cell, y / cell
    x0, y0 = np.floor(gx).astype(np.int64), np.floor(gy).astype(np.int64)
    fx, fy = gx - x0, gy - y0
    sx, sy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    i0, j0 = x0 % (n - 1), y0 % (n - 1)
    a = g[j0, i0]
    b = g[j0, i0 + 1]
    c = g[j0 + 1, i0]
    d = g[j0 + 1, i0 + 1]
    return (a * (1 - sx) + b * sx) * (1 - sy) + (c * (1 - sx) + d * sx) * sy


def fbm(x, y, cell, seed, octaves=4):
    tot, amp, norm = 0.0, 1.0, 0.0
    for o in range(octaves):
        tot = tot + amp * _lattice_noise(x, y, cell / (2 ** o), seed + 17 * o)
        norm += amp
        amp *= 0.5
    return tot / norm - 0.5


def surface_luminance(kind, P, beam, src, axis, shadow=None, ao=None, textured=True):
    """RGB luminance (cd/m2, N x 3) of the table / wall / floor points (mm): beam + room + lamp, matte
    (diffuse) part; also returns the beam illuminance E (lx) of every point"""
    L = np.zeros((len(P), 3), np.float64)
    nrm = np.zeros_like(P)
    nrm[kind == 2] = (-1.0, 0.0, 0.0)
    nrm[(kind == 1) | (kind == 3)] = (0.0, 0.0, 1.0)
    hit = kind > 0
    Pm, Nm = P[hit] / 1000.0, nrm[hit]
    Eb = np.zeros(hit.sum())
    if beam is not None:
        Eb = illuminance(beam, src / 1000.0, axis, Pm, Nm)
        # the table top blocks rays that pass below z = 0 before its edge (none for a light at the edge)
        d = Pm - src / 1000.0
        with np.errstate(divide="ignore", invalid="ignore"):
            s0 = np.where(d[:, 2] < 0, -(src[2] / 1000.0) / d[:, 2], np.inf)
        xb = src[0] / 1000.0 + s0 * d[:, 0]
        blocked = (s0 > 1e-6) & (s0 < 1 - 1e-6) & (xb <= EDGE_X / 1000.0) & (kind[hit] != 1)
        Eb[blocked] = 0.0
    Ek = key_illuminance(P[hit], Nm)
    k = kind[hit]
    sh = np.ones(hit.sum()) if shadow is None else shadow[hit]
    a = np.ones(hit.sum()) if ao is None else ao[hit]
    E = Eb[:, None] * C_BEAM + (Ek * sh)[:, None] * C_LAMP + (E_AMB * a)[:, None] * C_AMB
    rho = np.where(k == 2, RHO_WALL, np.where(k == 1, RHO_TABLE, RHO_FLOOR))[:, None] * np.ones(3)
    rho[k == 1] *= TABLE_TINT
    tex = np.ones(hit.sum())
    if textured:
        # textures attached to the surfaces (seeded): matte paint, dark wood grain
        x, y, z = P[hit, 0], P[hit, 1], P[hit, 2]
        w = k == 2
        tex[w] = 1 + 0.035 * fbm(y[w], z[w], 900.0, SEED + 1, 3) + 0.018 * fbm(y[w], z[w], 9.0, SEED + 2, 2)
        t_ = k == 1
        grain = fbm(x[t_] * 0.12, y[t_] * 2.2, 7.0, SEED + 3, 4)
        tex[t_] = 1 + 0.32 * grain + 0.12 * fbm(x[t_], y[t_], 1.2, SEED + 4, 2)
    L[hit] = rho * tex[:, None] * E / np.pi
    Eb_full = np.zeros(len(P))
    Eb_full[hit] = Eb
    return L, Eb_full


def table_sheen(P, V, beam, src, axis, n=40, chunk=150000):
    """glossy reflection (RGB cd/m2) of the satin table finish at table points P (mm) seen along the unit
    vectors V (point -> camera): GGX importance sampling, Schlick Fresnel (F0 = TABLE_F0) and Smith G; the
    reflected rays see the wall (its matte luminance from the same beam model), or the dim room"""
    a = TABLE_ALPHA
    rng = np.random.default_rng(SEED + 21)
    g = int(round(math.sqrt(n)))
    base = np.array([((i + 0.5) / g, (j + 0.5) / (n // g)) for i in range(g) for j in range(n // g)])
    out = np.zeros((len(P), 3))
    for i0 in range(0, len(P), chunk):
        Pc, Vc = P[i0:i0 + chunk], V[i0:i0 + chunk]
        m = len(Pc)
        rot = rng.random(m)                       # per-point rotation of the stratified pattern
        nv = np.clip(Vc[:, 2], 1e-4, 1)
        acc = np.zeros((m, 3))
        for (u1, u2) in base:
            uu = min(max(u1, 1e-6), 1 - 1e-6)
            ph = 2 * np.pi * ((u2 + rot) % 1.0)
            th = np.full(m, math.atan(a * math.sqrt(uu / (1 - uu))))
            h = np.stack([np.sin(th) * np.cos(ph), np.sin(th) * np.sin(ph), np.cos(th)], 1)
            vh = np.einsum("ij,ij->i", Vc, h)
            Ld = 2 * vh[:, None] * h - Vc
            nl = Ld[:, 2]
            ok = (nl > 1e-4) & (vh > 0)
            F = TABLE_F0 + (1 - TABLE_F0) * (1 - np.clip(vh, 0, 1)) ** 5
            G1 = lambda c: 2 * c / (c + np.sqrt(a * a + (1 - a * a) * c * c))  # noqa: E731
            wgt = F * G1(nv) * G1(np.clip(nl, 1e-4, 1)) * vh / (nv * np.cos(th))
            # incoming luminance along Ld
            Lin = np.tile(L_CEIL * C_AMB, (m, 1))
            hw = ok & (Ld[:, 0] > 1e-6)
            if hw.any():
                tt = (WALL_X - Pc[hw, 0]) / Ld[hw, 0]
                Q = Pc[hw] + Ld[hw] * tt[:, None]
                kq = np.full(len(Q), 2, np.int8)
                Lq, _ = surface_luminance(kq, Q, beam, src, axis, textured=False)
                Lin[hw] = Lq
            acc += np.where(ok[:, None], wgt[:, None] * Lin, 0.0)
        out[i0:i0 + chunk] = acc / len(base)
    return out


# ---- shadows of the light bodies on the table (VTK depth maps) ----------------------------------
def _depth_window(parts, W, H):
    vtk = _vtk()
    ren = vtk.vtkRenderer()
    ren.SetBackground(0, 0, 0)
    for _, pd, _ in parts:
        m = vtk.vtkPolyDataMapper()
        m.SetInputData(pd)
        a = vtk.vtkActor()
        a.SetMapper(m)
        ren.AddActor(a)
    win = vtk.vtkRenderWindow()
    win.SetOffScreenRendering(1)
    win.AddRenderer(ren)
    win.SetSize(W, H)
    win.SetMultiSamples(0)
    return ren, win


def _zbuffer(win):
    vtk = _vtk()
    from vtk.util.numpy_support import vtk_to_numpy
    f = vtk.vtkWindowToImageFilter()
    f.SetInput(win)
    f.ReadFrontBufferOff()
    f.SetInputBufferTypeToZBuffer()
    f.Update()
    img = f.GetOutput()
    w, h, _ = img.GetDimensions()
    return vtk_to_numpy(img.GetPointData().GetScalars()).reshape(h, w)[::-1].astype(np.float64)


def table_shadows(parts, P, sel, n_key=24, n_ao=40, res=640):
    """soft shadow of the lamp (n_key samples on its disk) and ambient occlusion (n_ao cosine-weighted
    directions) for the table points P[sel] (mm), from depth maps of the light bodies"""
    rng = np.random.default_rng(SEED + 11)
    b = np.array([0.0] * 6)
    ren, win = _depth_window(parts, res, res)
    ren.ComputeVisiblePropBounds(b)
    centre = np.array([(b[0] + b[1]) / 2, (b[2] + b[3]) / 2, (b[4] + b[5]) / 2])
    radius = 0.5 * math.sqrt((b[1] - b[0]) ** 2 + (b[3] - b[2]) ** 2 + (b[5] - b[4]) ** 2)
    Q = P[sel]
    cam = ren.GetActiveCamera()
    # lamp samples on a disk facing the aim point
    ax = normalize(KEY["aim"] - KEY["pos"])
    e1 = normalize(np.cross(ax, [0, 0, 1.0]))
    e2 = np.cross(e1, ax)
    lit = np.zeros(len(Q))
    for k in range(n_key):
        rr = KEY["radius"] * math.sqrt((k + rng.random()) / n_key)
        ph = 2 * math.pi * ((k * 0.618034) % 1.0)
        S = KEY["pos"] + rr * (math.cos(ph) * e1 + math.sin(ph) * e2)
        dist = np.linalg.norm(centre - S)
        n_, f_ = max(dist - 2 * radius, 1.0), dist + 3 * radius
        cam.ParallelProjectionOff()
        cam.SetPosition(*S)
        cam.SetFocalPoint(*centre)
        cam.SetViewUp(0, 0, 1)
        va = 2 * math.degrees(math.asin(min(radius * 1.3 / dist, 0.99)))
        cam.SetViewAngle(va)
        cam.SetClippingRange(n_, f_)
        win.Render()
        zb = _zbuffer(win)
        ze = n_ * f_ / (f_ - zb * (f_ - n_))
        ze[zb >= 1.0] = np.inf
        sc = {"pos": S, "look": centre, "vfov": va}
        px = project(sc, Q, res, res)
        fwd = normalize(centre - S)
        zq = (Q - S) @ fwd
        ii = np.clip(np.round(px[:, 0]).astype(int), 0, res - 1)
        jj = np.clip(np.round(px[:, 1]).astype(int), 0, res - 1)
        inside = (px[:, 0] >= 0) & (px[:, 0] < res) & (px[:, 1] >= 0) & (px[:, 1] < res)
        occ = inside & (ze[jj, ii] < zq - 0.25)
        lit += ~occ
    lit /= n_key
    # ambient occlusion: orthographic depth maps along cosine-weighted directions of the upper hemisphere
    vis = np.zeros(len(Q))
    for k in range(n_ao):
        u1, u2 = (k + rng.random()) / n_ao, rng.random()
        rr, ph = math.sqrt(u1), 2 * math.pi * u2
        wdir = np.array([rr * math.cos(ph), rr * math.sin(ph), math.sqrt(max(1 - u1, 0.0))])   # towards the sky
        if wdir[2] < 0.05:
            wdir[2] = 0.05
            wdir = normalize(wdir)
        S = centre + wdir * (6 * radius)
        cam.ParallelProjectionOn()
        cam.SetPosition(*S)
        cam.SetFocalPoint(*centre)
        up = [0, 0, 1] if abs(wdir[2]) < 0.95 else [1, 0, 0]
        cam.SetViewUp(*up)
        half = radius * 1.6
        cam.SetParallelScale(half)
        n_, f_ = 1.0, 12 * radius
        cam.SetClippingRange(n_, f_)
        win.Render()
        zb = _zbuffer(win)
        ze = n_ + zb * (f_ - n_)
        ze[zb >= 1.0] = np.inf
        fwd = -wdir
        r_ = normalize(np.cross(fwd, up))
        u_ = np.cross(r_, fwd)
        d = Q - S
        zq = d @ fwd
        ii = np.round(((d @ r_) / half + 1) * res / 2 - 0.5).astype(int)
        jj = np.round((1 - (d @ u_) / half) * res / 2 - 0.5).astype(int)
        inside = (ii >= 0) & (ii < res) & (jj >= 0) & (jj < res)
        occ = np.zeros(len(Q), bool)
        occ[inside] = ze[jj[inside], ii[inside]] < zq[inside] - 0.25
        vis += ~occ
    vis /= n_ao
    win.Finalize()
    return lit, vis


# ---- environment map seen from the light body (for the PBR objects) ----------------------------
def env_map(beam, src, axis, centre, w=512, h=256):
    """equirectangular luminance map (cd/m2) around `centre`, VTK convention (env up +z, right +x):
    row 0 = up, longitude from +x towards -y"""
    u = (np.arange(w) + 0.5) / w
    v = (np.arange(h) + 0.5) / h
    U, V = np.meshgrid(u, v)
    lon = (0.5 - U) * 2 * np.pi
    lat = (0.5 - V) * np.pi
    D = np.stack([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)], -1).reshape(-1, 3)
    kind, P, _ = trace_planes(centre, D)
    L, _ = surface_luminance(kind, P, beam, src, axis, textured=False)
    L[kind == 0] = L_CEIL * C_AMB
    # the lamp as a bright disk
    dk = KEY["pos"] - centre
    dist = np.linalg.norm(dk)
    ang = np.degrees(np.arccos(np.clip(D @ (dk / dist), -1, 1)))
    rad = math.degrees(math.atan(KEY["radius"] / dist))
    L_lamp = KEY["I"] / (math.pi * (KEY["radius"] / 1000.0) ** 2)
    L[ang < rad] = L_lamp * C_LAMP
    return L.reshape(h, w, 3)


def render_objects(parts, cam, W, H, env, scale):
    """PBR + image-based lighting from `env` (cd/m2); returns linear luminance RGB (cd/m2) and coverage.
    Two exposures (x1 and x1/16) are merged, because the frame buffer has 8 bits."""
    vtk = _vtk()
    from vtk.util.numpy_support import numpy_to_vtk, vtk_to_numpy

    def tex_from(img):
        img3 = img if img.ndim == 3 else np.repeat(img[..., None], 3, 2)
        arr = numpy_to_vtk(np.ascontiguousarray(img3[::-1].reshape(-1, 3).astype(np.float32)), deep=True)
        im = vtk.vtkImageData()
        im.SetDimensions(img.shape[1], img.shape[0], 1)
        im.GetPointData().SetScalars(arr)
        t = vtk.vtkTexture()
        t.SetInputData(im)
        t.SetColorModeToDirectScalars()
        t.MipmapOn()
        t.InterpolateOn()
        return t

    def setup(env_scale):
        ren = vtk.vtkRenderer()
        ren.SetBackground(0, 0, 0)
        ren.AutomaticLightCreationOff()
        ren.UseImageBasedLightingOn()
        ren.SetEnvironmentTexture(tex_from(env * env_scale), False)
        ren.SetEnvironmentUp(0, 0, 1)
        ren.SetEnvironmentRight(1, 0, 0)
        for _, pd, mat in parts:
            nf = vtk.vtkPolyDataNormals()
            nf.SetInputData(pd)
            nf.SetFeatureAngle(32)
            nf.SplittingOn()
            nf.Update()
            m = vtk.vtkPolyDataMapper()
            m.SetInputData(nf.GetOutput())
            a = vtk.vtkActor()
            a.SetMapper(m)
            pr = a.GetProperty()
            col, met, rough = MAT[mat]
            pr.SetInterpolationToPBR()
            pr.SetColor(*col)
            pr.SetMetallic(met)
            pr.SetRoughness(rough)
            ren.AddActor(a)
        c = ren.GetActiveCamera()
        c.SetPosition(*cam["pos"])
        f, r, u = cam_basis(cam)
        c.SetFocalPoint(*(cam["pos"] + f * 1000.0))
        c.SetViewUp(*u)
        c.SetViewAngle(cam["vfov"])
        c.SetClippingRange(20.0, 6000.0)
        win = vtk.vtkRenderWindow()
        win.SetOffScreenRendering(1)
        win.AddRenderer(ren)
        win.SetSize(W, H)
        win.SetMultiSamples(0)
        win.Render()
        return ren, win

    def grab(win):
        f = vtk.vtkWindowToImageFilter()
        f.SetInput(win)
        f.ReadFrontBufferOff()
        f.SetInputBufferTypeToRGB()
        f.Update()
        img = f.GetOutput()
        w, h, _ = img.GetDimensions()
        return vtk_to_numpy(img.GetPointData().GetScalars()).reshape(h, w, 3)[::-1].astype(np.float64) / 255.0

    out = None
    for k, s in enumerate((scale, scale / 16.0)):
        ren, win = setup(s)
        raw = grab(win)
        rgb = raw ** 2.2 / s                      # VTK's PBR output is gamma-encoded (1/2.2)
        if k == 0:
            cover = (_zbuffer(win) < 1.0).astype(np.float64)
            out = rgb
            clip = raw.max(axis=2) > 0.985        # these pixels come from the darker second exposure
        else:
            out[clip] = rgb[clip]
        win.Finalize()
    return out, cover


# ---- tone curve (one for every panel) ------------------------------------------------------------
TONE_STOPS, TONE_WHITE, TONE_G = 10.0, 1.10, 1.70


def tonemap(L, L_ref):
    """one filmic curve for every panel, in the log domain: luminance L (cd/m2) relative to the white point
    TONE_WHITE x L_ref (L_ref = the brightest wall point of all panels) spans TONE_STOPS stops from black
    to white, shaped by a power toe; output = display code values 0..1 (sRGB-encoded)"""
    x = np.maximum(L, 1e-12) / (L_ref * TONE_WHITE)
    t = np.clip(1.0 + np.log2(x) / TONE_STOPS, 0.0, 1.0)
    return t ** TONE_G


def downsample(img, k):
    if k == 1:
        return img
    H, W = img.shape[:2]
    return img[:H // k * k, :W // k * k].reshape(H // k, k, W // k, k, *img.shape[2:]).mean(axis=(1, 3))


def haze_luminance(beam, src, axis, C, D, tmax, n=48, chunk=400000):
    """single-scattering haze glow (cd/m2) along rays C + s D, s in [0, tmax] (mm), isotropic phase:
    L = sigma / (4 pi) * integral of I(theta(s)) / r(s)^2 ds, integrated with equiangular sampling about the
    closest approach h to the source: ds / r^2 = dphi / h, so the 1/r^2 peak is integrated exactly"""
    out = np.zeros(len(D))
    srcm = src / 1000.0
    for i0 in range(0, len(D), chunk):
        d = D[i0:i0 + chunk]
        tm = np.minimum(tmax[i0:i0 + chunk], 8000.0) / 1000.0
        w = srcm - C / 1000.0
        s_star = d @ w
        hv = (C / 1000.0)[None, :] + d * s_star[:, None] - srcm
        h = np.maximum(np.linalg.norm(hv, axis=1), 0.005)    # the head is a 10 mm aperture, not a point
        pa = np.arctan2(0.0 - s_star, h)
        pb = np.arctan2(tm - s_star, h)
        acc = np.zeros(len(d))
        for k in range(n):
            ph = pa + (pb - pa) * (k + 0.5) / n
            sk = s_star + h * np.tan(ph)
            X = (C / 1000.0)[None, :] + d * sk[:, None]
            v = X - srcm
            r = np.linalg.norm(v, axis=1)
            cth = (v @ axis) / np.maximum(r, 1e-9)
            acc += beam.I(np.arccos(np.clip(cth, -1, 1))) * (cth > 0)
        out[i0:i0 + chunk] = HAZE_SIGMA / (4 * np.pi) * acc * (pb - pa) / n / h
    return out


def aim_camera(cam, aspect=PANEL[0] / PANEL[1], beam_z=8.0):
    """choose the look-at point so that the beam centre on the wall lands at cam["target"] (fractions)"""
    if cam.get("look") is not None:
        return cam
    W, H = 1000, int(round(1000 / aspect))
    look = np.array([WALL_X, 0.0, beam_z])
    tgt = np.array(cam["target"])
    for _ in range(60):
        c = dict(cam, look=look)
        p0 = project(c, np.array([[WALL_X, 0.0, beam_z]]), W, H)[0] / [W, H]
        err = p0 - tgt
        if np.abs(err).max() < 1e-6:
            break
        J = np.zeros((2, 2))
        for k, dv in enumerate(([0, 10.0, 0], [0, 0, 10.0])):
            p1 = project(dict(cam, look=look + np.array(dv)), np.array([[WALL_X, 0.0, beam_z]]), W, H)[0] / [W, H]
            J[:, k] = (p1 - p0) / 10.0
        look = look - np.r_[0.0, np.linalg.solve(J, err)]
    cam["look"] = look
    return cam


def render_panel(M, kind, cad_dir, W, H, ss=2, beam_on=True):
    """linear luminance (cd/m2) of one panel at W x H (rendered at ss x and box-filtered)"""
    aim_camera(CAM)
    beam = M["fk"] if kind == "fk" else M["a2"]
    parts, src, axis = light_in_scene(kind, cad_dir, M["geo"])
    Ws, Hs = W * ss, H * ss
    D = pixel_rays(CAM, Ws, Hs)
    kindp, P, t = trace_planes(CAM["pos"], D)
    # shadows near the light body
    sel = (kindp == 1) & (np.abs(P[:, 0] + 50) < 240) & (np.abs(P[:, 1]) < 240)
    shadow = np.ones(len(P))
    ao = np.ones(len(P))
    if sel.any():
        lit, vis = table_shadows(parts, P, sel)
        shadow[sel], ao[sel] = lit, vis
    Lp, Eb = surface_luminance(kindp, P, beam if beam_on else None, src, axis, shadow, ao)
    Lp[kindp == 0] = L_CEIL * RHO_WALL * C_AMB
    tsel = kindp == 1
    if tsel.any():
        sh_img = np.zeros((len(P), 3))
        sh_img[tsel] = table_sheen(P[tsel], -D[tsel], beam if beam_on else None, src, axis)
        Lp[tsel] += masked_blur(sh_img.reshape(Hs, Ws, 3), tsel.reshape(Hs, Ws), 1.2 * ss).reshape(-1, 3)[tsel]

    # the light body: PBR, lit by the environment it sees (the lit wall, the room, the lamp)
    centre = np.array([-45.0 if kind == "fk" else -28.0, 0.0, 8.0])
    env = env_map(beam if beam_on else None, src, axis, centre)
    obj, cover = render_objects(parts, CAM, Ws, Hs, env, scale=1.0 / 12.0)
    cam_err = camera_check(parts, cover, Ws, Hs)
    Lh = np.zeros(len(D))
    if beam_on and HAZE_SIGMA > 0:
        tmax = np.where(np.isfinite(t), t, 8000.0)
        Lh = haze_luminance(beam, src, axis, CAM["pos"], D, tmax)
    L = (Lp + Lh[:, None] * C_BEAM).reshape(Hs, Ws, 3)
    L = obj * cover[..., None] + L * (1 - cover[..., None])
    info = {"kind": kindp.reshape(Hs, Ws), "t": t.reshape(Hs, Ws), "D": D, "src": src, "axis": axis,
            "beam": beam, "Eb": Eb.reshape(Hs, Ws), "ss": ss, "cover": cover, "Ws": Ws, "Hs": Hs, "cam_err": cam_err,
            "haze": _haze_share(kindp, Lh, Lp, Eb, Ws, Hs)}
    return downsample(L, ss), info


def _haze_share(kindp, Lh, Lp, Eb, Ws, Hs):
    """haze glow as a share of the wall luminance: at the marked wall centre, and the median and largest share
    inside the beam spot (wall pixels with at least 10 % of the brightest beam illuminance)"""
    wall = kindp == 2
    if not wall.any() or Eb[wall].max() <= 0:
        return {"centre": 0.0, "median": 0.0, "max": 0.0}
    spot = wall & (Eb >= 0.1 * Eb[wall].max())
    r = Lh / np.maximum(Lp[:, 1], 1e-9)
    c = project(CAM, np.array([[WALL_X, 0.0, 8.0]]), Ws, Hs)[0]
    ic = int(round(c[1])) * Ws + int(round(c[0]))
    return {"centre": float(r[ic]), "median": float(np.median(r[spot])), "max": float(np.max(r[spot]))}


def camera_check(parts, cover, Ws, Hs, tol_px=1.5):
    """the VTK render of the light body must sit exactly where the numpy camera projects its vertices"""
    from vtk.util.numpy_support import vtk_to_numpy
    pts = np.vstack([vtk_to_numpy(pd.GetPoints().GetData()) for _, pd, _ in parts])
    pr = project(CAM, pts, Ws, Hs)
    ys, xs = np.nonzero(cover > 0.5)
    got = np.array([xs.min(), ys.min(), xs.max(), ys.max()], float)
    want = np.array([pr[:, 0].min(), pr[:, 1].min(), pr[:, 0].max(), pr[:, 1].max()])
    err = np.abs(got - want).max()
    if err > tol_px * (Ws / PANEL[0] if Ws > PANEL[0] else 1):
        raise SystemExit("camera mismatch between VTK and numpy: %.2f px (%s vs %s)" % (err, got, want))
    return err


def masked_blur(img, mask, sigma):
    """Gaussian blur of img inside mask only (normalised), for the smooth sheen; sigma in px"""
    from scipy.ndimage import gaussian_filter
    m = mask.astype(np.float64)
    num = np.stack([gaussian_filter(img[..., c] * m, sigma) for c in range(img.shape[2])], -1)
    den = gaussian_filter(m, sigma)[..., None]
    return np.where(den > 1e-6, num / np.maximum(den, 1e-6), img)


def wall_energy_check(info, report, tol=5e-3):
    """end-to-end check of a rendered panel: the beam illuminance summed over the visible wall pixels
    (E x pixel area on the wall) equals the flux the beam sends into that visible wall area
    (angular integral of I over the directions that land on those pixels)"""
    Ws, Hs, beam, src = info["Ws"], info["Hs"], info["beam"], info["src"]
    th = math.tan(math.radians(CAM["vfov"]) / 2)
    j, i = np.mgrid[0:Hs, 0:Ws]
    sx = (2 * (i + 0.5) / Ws - 1) * th * (Ws / Hs)
    sy = (1 - 2 * (j + 0.5) / Hs) * th
    dsx, dsy = 2 * th * (Ws / Hs) / Ws, 2 * th / Hs
    omega = dsx * dsy / (1 + sx ** 2 + sy ** 2) ** 1.5
    D = info["D"].reshape(Hs, Ws, 3)
    vis = (info["kind"] == 2) & (info["cover"].reshape(Hs, Ws) < 0.5)
    area_m2 = omega * (info["t"] / 1000.0) ** 2 / np.maximum(np.abs(D[..., 0]), 1e-9)
    flux_img = float(np.sum(info["Eb"][vis] * area_m2[vis]))
    # directions from the source
    nth, nph = 2800, 2880
    tht = (np.arange(nth) + 0.5) / nth * np.radians(70.0)
    phs = (np.arange(nph) + 0.5) / nph * 2 * np.pi
    dth, dph = np.radians(70.0) / nth, 2 * np.pi / nph
    flux_ang = 0.0
    for a0 in range(0, nth, 200):
        T_, P_ = np.meshgrid(tht[a0:a0 + 200], phs, indexing="ij")
        dirs = np.stack([np.cos(T_), np.sin(T_) * np.cos(P_), np.sin(T_) * np.sin(P_)], -1).reshape(-1, 3)
        sdist = (WALL_X - src[0]) / dirs[:, 0]
        Q = src[None, :] + dirs * sdist[:, None]
        pix = project(CAM, Q, Ws, Hs)
        ii = np.round(pix[:, 0]).astype(int)
        jj = np.round(pix[:, 1]).astype(int)
        ok = (ii >= 0) & (ii < Ws) & (jj >= 0) & (jj < Hs)
        good = np.zeros(len(Q), bool)
        good[ok] = vis[jj[ok], ii[ok]]
        w = (beam.I(T_.ravel()) * np.sin(T_.ravel()) * dth * dph)
        flux_ang += float(np.sum(w[good]))
    rel = abs(flux_img - flux_ang) / flux_ang
    line = "[%s] %s panel: flux into the visible wall area, pixel sum %.2f lm vs angular %.2f lm (%.2f %%, limit %.1f %%)" % (
        "PASS" if rel <= tol else "FAIL", beam.name, flux_img, flux_ang, rel * 100, tol * 100)
    log("  " + line)
    report.append(line)
    if rel > tol:
        raise SystemExit("rendered-wall energy check failed")
    return flux_img, flux_ang


def to_display(L, L_ref, seed):
    """the one tone curve + triangular dither, to 8 bits"""
    y = tonemap(L, L_ref)
    rng = np.random.default_rng(seed)
    y = y + (rng.random(y.shape) - rng.random(y.shape)) / 255.0
    return (np.clip(y, 0, 1) * 255 + 0.5).astype(np.uint8)


def draw_text(d, xy, text, f, fill, anchor="la"):
    d.text(xy, text, font=f, fill=fill, anchor=anchor)
    return d.textlength(text, font=f)


def beam_labels(M):
    fk, a2 = M["fk"], M["a2"]
    E_fk = illuminance(fk, np.array([-M["geo"]["x_exit"], 0, 0]) / 1000.0, np.array([1.0, 0, 0]),
                       np.array([[WALL_X / 1000.0, 0, 0]]), np.array([[-1.0, 0, 0]]))[0]
    E_a2 = illuminance(a2, np.zeros(3), np.array([1.0, 0, 0]), np.array([[WALL_X / 1000.0, 0, 0]]),
                       np.array([[-1.0, 0, 0]]))[0]
    return {
        "fk": {"name": "FlashKa Keychain v0.7", "status": "simulated from the LED and optic datasheets, not yet built",
               "nums": "%s lm  ·  %s cd  ·  %d m throw (simulated, at switch-on)" % (
                   fmt_int(fk.flux()), fmt_int(fk.peak), round(throw_m(fk.peak))),
               "lux": E_fk, "colour": BLUE},
        "a2": {"name": "RovyVon Aurora A2 - size stand-in",
               "status": "beam: maker's data and 1lumen measurement; body: plain stand-in of its published size",
               "nums": "%s lm  ·  %s cd  ·  %d m throw (1lumen, at switch-on)" % (
                   fmt_int(a2.flux()), fmt_int(a2.peak), round(throw_m(a2.peak))),
               "lux": E_a2, "colour": ORANGE},
    }


def picture_beams(M, cad_dir, out_dir, report, draft=False):
    """comparison_beams.png: the two panels with one exposure, labels and caption; returns the panels"""
    W, H = PANEL if not draft else (PANEL[0] // 2, PANEL[1] // 2)
    ss = 2 if not draft else 1
    aim_camera(CAM)
    hdr, infos = {}, {}
    for kind in ("fk", "a2"):
        log("  rendering the %s panel (%d x %d, %dx supersampled)" % (kind, W, H, ss))
        hdr[kind], infos[kind] = render_panel(M, kind, cad_dir, W, H, ss)
        wall_energy_check(infos[kind], report)
        report.append("[PASS] %s panel: VTK light body and numpy camera agree within %.2f px (limit 1.5 px at "
                      "the final scale)" % (infos[kind]["beam"].name, infos[kind]["cam_err"] / ss))
        log("  " + report[-1])
        hz = infos[kind]["haze"]
        report.append("%s panel: the haze glow adds %.2f %% to the wall luminance at the marked wall centre and %.2f %% "
                      "in the middle of the beam spot (median of the wall points with at least 10 %% of the brightest "
                      "illuminance); at most %.0f %% just above the light, where the line of sight passes close to "
                      "its head" % (infos[kind]["beam"].name, 100 * hz["centre"], 100 * hz["median"], 100 * hz["max"]))
        log("  " + report[-1])
    # one exposure for both panels: white point just above the brightest wall point of the two panels
    lab = beam_labels(M)
    L_ref = RHO_WALL * (max(lab["fk"]["lux"], lab["a2"]["lux"]) + E_AMB) / np.pi
    report.append("exposure: one white point for both panels, %.3f x %.1f cd/m2 (brightest wall point); "
                  "tone curve: log2, %.1f stops, power %.2f" % (TONE_WHITE, L_ref, TONE_STOPS, TONE_G))
    imgs = {k: to_display(hdr[k], L_ref, SEED + (1 if k == "fk" else 2)) for k in hdr}
    # wall-centre pixel positions (for the small markers)
    centres = {}
    for k in ("fk", "a2"):
        centres[k] = project(CAM, np.array([[WALL_X, 0.0, 8.0]]), W, H)[0]
    return compose_beams(imgs, centres, lab, out_dir, W, H, L_ref)


def compose_beams(imgs, centres, lab, out_dir, W, H, L_ref, dark=False, fname="comparison_beams.png", header=True):
    from PIL import Image, ImageDraw
    k = W / PANEL[0]
    OUTW = int(round(2400 * k))
    m, g = int(32 * k), int(32 * k)
    bg = PAGE_BG_D if dark else PAGE_BG
    ink, ink2, mut = (INK_D, INK2_D, MUTED_D) if dark else (INK, INK2, MUTED)
    f_title, f_sub = font(34 * k, True), font(22 * k)
    f_name, f_stat, f_num = font(29 * k, True), font(21 * k), font(23 * k)
    f_cap, f_badge = font(19.5 * k), font(20 * k, True)
    y0 = int(112 * k) if header else int(24 * k)
    lab_h = int(168 * k)
    cap_h = int(84 * k)
    Htot = y0 + H + lab_h + cap_h
    im = Image.new("RGB", (OUTW, Htot), bg)
    d = ImageDraw.Draw(im)
    if header:
        draw_text(d, (m, int(30 * k)), "Beams on a white wall 2 m away", f_title, ink)
        draw_text(d, (m, int(76 * k)), "Turbo at switch-on.  Both panels share the scene, camera, exposure and tone "
                  "curve, so their brightness can be compared directly.", f_sub, ink2)
    for n, kind in enumerate(("fk", "a2")):
        x = m + n * (W + g)
        panel = Image.fromarray(imgs[kind])
        pd_ = ImageDraw.Draw(panel, "RGBA")
        # marker at the wall centre + badge with the illuminance there
        cx, cy = centres[kind]
        r = 7 * k
        pd_.ellipse([cx - r - 2 * k, cy - r - 2 * k, cx + r + 2 * k, cy + r + 2 * k], outline=(255, 255, 255, 220),
                    width=max(1, int(2 * k)))
        pd_.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(20, 22, 26, 230), width=max(1, int(2 * k)))
        txt = "%s lx" % fmt_int(lab[kind]["lux"])
        tw = pd_.textlength(txt, font=f_badge)
        bx, by = cx + 26 * k, cy - 58 * k
        pd_.line([(cx + r * 0.75, cy - r * 0.75), (bx, by + 30 * k)], fill=(20, 22, 26, 200), width=max(1, int(2 * k)))
        pd_.rounded_rectangle([bx, by, bx + tw + 22 * k, by + 34 * k], radius=8 * k, fill=(16, 18, 22, 205))
        pd_.text((bx + 11 * k, by + 17 * k), txt, font=f_badge, fill=(255, 255, 255, 255), anchor="lm")
        mask = Image.new("L", panel.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, W - 1, H - 1], radius=int(14 * k), fill=255)
        im.paste(panel, (x, y0), mask)
        # label block
        ly = y0 + H + int(22 * k)
        d.rounded_rectangle([x, ly + int(4 * k), x + int(7 * k), ly + int(112 * k)], radius=int(3 * k),
                            fill=lab[kind]["colour"])
        tx = x + int(22 * k)
        draw_text(d, (tx, ly), lab[kind]["name"], f_name, ink)
        draw_text(d, (tx, ly + int(40 * k)), lab[kind]["status"], f_stat, ink2)
        draw_text(d, (tx, ly + int(70 * k)), lab[kind]["nums"], f_num, ink)
        draw_text(d, (tx, ly + int(100 * k)), "%s lx at the wall centre" % fmt_int(lab[kind]["lux"]), f_num, ink)
    cy0 = y0 + H + lab_h + int(10 * k)
    draw_text(d, (m, cy0), "Render. FlashKa: simulated, not yet built. RovyVon Aurora A2: maker's data and 1lumen "
              "measurement.", f_cap, mut)
    draw_text(d, (m, cy0 + int(30 * k)), "Wall brightness from E = I(θ) cos α / d² for each beam model "
              "(lumens and candela above); white wall 2 m from the lights; one exposure for both panels.", f_cap, mut)
    path = os.path.join(out_dir, fname)
    save_png(im, path)
    return {"path": path, "imgs": imgs, "centres": centres, "lab": lab, "W": W, "H": H, "L_ref": L_ref}


# ----------------------------------------------------------------------------------------------
# picture: size, to scale (orthographic views)
# ----------------------------------------------------------------------------------------------
def cad_info(cad_dir):
    """housing version, size and mass: the parts in the CAD + the optic and LED board (housing_interface.json)
    + the cell (maker's data) and the electronics (estimate)"""
    hi = json.load(open(os.path.join(cad_dir, "housing_interface.json")))
    info = {"version": str(hi.get("version"))}
    mg = hi.get("mass_g", {})
    if "FlashKa_tray" not in mg or "FlashKa_lid" not in mg:
        raise SystemExit("housing_interface.json: mass_g of the tray and the lid missing")
    info["mass_parts"] = {k_: float(v) for k_, v in mg.items()}          # every part the housing CAD weighs
    info["mass_cad_g"] = float(sum(info["mass_parts"].values()))
    geo = flashka_geo(cad_dir)
    info["mass_optic_g"] = float(geo["optic_mass_g"]) if geo["optic_mass_g"] is not None else None
    info["mass_ledboard_g"] = float(geo["led_board_g"]) if geo["led_board_g"] is not None else None
    info["mass_cells_g"] = CELL["n"] * CELL["g"]
    info["mass_electronics_g"] = float(sum(g for _, g in ELECTRONICS_G))
    if info["mass_optic_g"] is None or info["mass_ledboard_g"] is None:
        raise SystemExit("housing_interface.json: optic or LED board mass missing")
    info["mass_g"] = (info["mass_cad_g"] + info["mass_optic_g"] + info["mass_ledboard_g"] + info["mass_cells_g"]
                      + info["mass_electronics_g"])
    import trimesh
    b = None
    for n in ("FlashKa_tray", "FlashKa_lid"):
        m = trimesh.load(os.path.join(cad_dir, n + ".stl"))
        b = m.bounds if b is None else np.vstack([np.minimum(b[0], m.bounds[0]), np.maximum(b[1], m.bounds[1])])
    info["size_mm"] = tuple(float(v) for v in (b[1] - b[0]))
    info["battery_mAh"] = CELL["n"] * CELL["mAh"]
    info["placeholder"] = info["version"] not in ("0.7", "0.7.0")
    return info


def studio_env(w=512, h=256):
    """equirectangular studio environment (VTK convention: row 0 = up, longitude from +x towards -y)"""
    u = (np.arange(w) + 0.5) / w
    v = (np.arange(h) + 0.5) / h
    U, V = np.meshgrid(u, v)
    lon = (0.5 - U) * 2 * np.pi
    lat = (0.5 - V) * np.pi
    D = np.stack([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)], -1)

    def box(direction, width, power):
        dd = normalize(np.array(direction, float))
        c = np.clip(D @ dd, -1, 1)
        return power * np.exp(-(np.arccos(c) ** 2) / (2 * width ** 2))
    env = 0.30 + 0.25 * np.clip(D[..., 2], 0, 1) + 0.35 * np.clip(-D[..., 2], 0, 1)
    env = env + box((-0.35, -0.45, 0.82), 0.30, 5.0)        # big softbox above, front left
    env = env + box((-0.85, 0.15, 0.35), 0.16, 2.2)         # strip light on the left
    env = env + box((0.55, 0.65, 0.50), 0.22, 1.6)          # rim light from behind
    rgb = np.stack([env * 1.0, env * 1.0, env * 1.02], -1)
    return rgb


def ortho_view(parts, view_dir, up, ppm, env, ss=2, margin_mm=2.0):
    """orthographic PBR render of parts (mm) seen along view_dir: returns display RGB (0..1), coverage,
    and a function world (N,3) -> pixel (N,2) at the final scale ppm (px per mm)"""
    vtk = _vtk()
    from vtk.util.numpy_support import numpy_to_vtk, vtk_to_numpy
    f = normalize(np.array(view_dir, float))
    r = normalize(np.cross(f, up))
    u = np.cross(r, f)
    pts = []
    for _, pd, _ in parts:
        b = pd.GetBounds()
        for x in b[0:2]:
            for y in b[2:4]:
                for z in b[4:6]:
                    pts.append((x, y, z))
    pts = np.array(pts)
    pr, pu = pts @ r, pts @ u
    r0, r1, u0, u1 = pr.min() - margin_mm, pr.max() + margin_mm, pu.min() - margin_mm, pu.max() + margin_mm
    Wpx, Hpx = int(math.ceil((r1 - r0) * ppm)), int(math.ceil((u1 - u0) * ppm))
    centre = r * (r0 + r1) / 2 + u * (u0 + u1) / 2 + f * (pts @ f).mean()
    ren = vtk.vtkRenderer()
    ren.SetBackground(0, 0, 0)
    ren.AutomaticLightCreationOff()
    ren.UseImageBasedLightingOn()
    arr = numpy_to_vtk(np.ascontiguousarray(env[::-1].reshape(-1, 3).astype(np.float32)), deep=True)
    im = vtk.vtkImageData()
    im.SetDimensions(env.shape[1], env.shape[0], 1)
    im.GetPointData().SetScalars(arr)
    t = vtk.vtkTexture()
    t.SetInputData(im)
    t.SetColorModeToDirectScalars()
    t.MipmapOn()
    t.InterpolateOn()
    ren.SetEnvironmentTexture(t, False)
    ren.SetEnvironmentUp(0, 0, 1)
    ren.SetEnvironmentRight(1, 0, 0)
    for _, pd, mat in parts:
        nf = vtk.vtkPolyDataNormals()
        nf.SetInputData(pd)
        nf.SetFeatureAngle(32)
        nf.SplittingOn()
        nf.Update()
        m = vtk.vtkPolyDataMapper()
        m.SetInputData(nf.GetOutput())
        a = vtk.vtkActor()
        a.SetMapper(m)
        p = a.GetProperty()
        col, met, rough = MAT[mat]
        p.SetInterpolationToPBR()
        p.SetColor(*col)
        p.SetMetallic(met)
        p.SetRoughness(rough)
        if mat in SEE_THROUGH:
            p.SetOpacity(SEE_THROUGH[mat])
        ren.AddActor(a)
    ren.SetUseDepthPeeling(1)
    ren.SetMaximumNumberOfPeels(8)
    ren.SetOcclusionRatio(0.0)
    cam = ren.GetActiveCamera()
    cam.ParallelProjectionOn()
    cam.SetFocalPoint(*centre)
    cam.SetPosition(*(centre - f * 600.0))
    cam.SetViewUp(*u)
    cam.SetParallelScale((u1 - u0) / 2)
    cam.SetClippingRange(100.0, 1200.0)
    win = vtk.vtkRenderWindow()
    win.SetOffScreenRendering(1)
    win.AddRenderer(ren)
    win.SetSize(Wpx * ss, Hpx * ss)
    win.SetMultiSamples(0)
    win.Render()
    g = vtk.vtkWindowToImageFilter()
    g.SetInput(win)
    g.ReadFrontBufferOff()
    g.SetInputBufferTypeToRGB()
    g.Update()
    img = g.GetOutput()
    w_, h_, _ = img.GetDimensions()
    rgb = vtk_to_numpy(img.GetPointData().GetScalars()).reshape(h_, w_, 3)[::-1].astype(np.float64) / 255.0
    zb = _zbuffer(win)
    win.Finalize()
    cover = (zb < 1.0).astype(np.float64)
    rgb = downsample(rgb * cover[..., None], ss)
    cover = downsample(cover, ss)
    rgb = np.where(cover[..., None] > 1e-6, rgb / np.maximum(cover[..., None], 1e-6), 0.0)

    def w2p(P):
        P = np.atleast_2d(P)
        return np.stack([((P @ r) - r0) * ppm, (u1 - (P @ u)) * ppm], 1)
    return rgb[:Hpx, :Wpx], cover[:Hpx, :Wpx], w2p


def size_parts(cad_dir):
    """FlashKa in its housing frame; the A2 stand-in in the same frame convention (head at X = 0, lying on
    Z = 0, axis on Y = 0)"""
    fk = flashka_parts(cad_dir)
    L, R = A2["length_mm"], A2["dia_mm"] / 2
    a2 = [(n, transformed(pd, 180.0, (L, 0.0, R + 0.25)), mat) for n, pd, mat in a2_standin_parts()]
    return fk, a2


def _soft_shadow(cover, offset_px, sigma_px, strength):
    from scipy.ndimage import gaussian_filter, shift
    s = gaussian_filter(shift(cover, (offset_px[1], offset_px[0]), order=1, mode="constant"), sigma_px)
    return 1.0 - strength * np.clip(s, 0, 1)


def _dim_h(d, x0, x1, y, text, f, ink, tick=10, above=True):
    d.line([(x0, y), (x1, y)], fill=ink, width=2)
    for x in (x0, x1):
        d.line([(x, y - tick), (x, y + tick)], fill=ink, width=2)
    tw = d.textlength(text, font=f)
    d.text(((x0 + x1) / 2 - tw / 2, y - 12 - f.size if above else y + 12), text, font=f, fill=ink)


def _dim_v(d, x, y0, y1, text, f, ink, tick=10, right=True):
    d.line([(x, y0), (x, y1)], fill=ink, width=2)
    for y in (y0, y1):
        d.line([(x - tick, y), (x + tick, y)], fill=ink, width=2)
    tw = d.textlength(text, font=f)
    if right:
        d.text((x + 14, (y0 + y1) / 2 - f.size * 0.6), text, font=f, fill=ink)
    else:
        d.text((x - 14 - tw, (y0 + y1) / 2 - f.size * 0.6), text, font=f, fill=ink)


def render_size_views(cad_dir, draft=False):
    """orthographic views of both lights at one scale (px per mm at the 2400 px layout)"""
    k = 0.5 if draft else 1.0
    ppm = 8.0 * k
    fk_parts, a2_parts = size_parts(cad_dir)
    env = studio_env()
    ss = 1 if draft else 2
    views = {}
    for name, parts in (("fk", fk_parts), ("a2", a2_parts)):
        views[name] = {"top": ortho_view(parts, (0, 0, -1), (0, 1, 0), ppm, env, ss),
                       "front": ortho_view(parts, (1, 0, 0), (0, 0, 1), ppm, env, ss),
                       "iso": ortho_view(parts, (0.95, 1.20, -0.80), (0, 0, 1), ppm, env, ss)}
    return {"views": views, "ppm": ppm, "k": k, "ci": cad_info(cad_dir)}


def _bbox(cov, thr=0.5):
    xs = np.nonzero(cov.max(axis=0) > thr)[0]
    ys = np.nonzero(cov.max(axis=1) > thr)[0]
    return xs.min(), ys.min(), xs.max(), ys.max()


def draw_size_block(SV, dark=False, scale=1.0, show_text=True):
    """the size comparison as an image (no header): rows = lights, columns = top, front, three-quarter.
    scale < 1 shrinks the whole block (the views stay at one common scale)"""
    from PIL import Image, ImageDraw
    from scipy.ndimage import gaussian_filter
    views, ppm, k, ci = SV["views"], SV["ppm"], SV["k"] * scale, SV["ci"]
    bg = PAGE_BG_D if dark else PAGE_BG
    ink, ink2, mut = (INK_D, INK2_D, MUTED_D) if dark else (INK, INK2, MUTED)
    dim_ink = (150, 155, 165) if dark else (95, 100, 110)
    f_name, f_txt, f_dim, f_small = font(27 * k, True), font(21 * k), font(20 * k), font(18 * k)
    sc = scale
    W = int(round(2400 * SV["k"] * sc))
    # column x positions and row y positions (in block pixels)
    def view(name, v):
        rgb, cov, w2p = views[name][v]
        if sc != 1.0:
            hh, ww = cov.shape
            nh, nw = max(1, int(round(hh * sc))), max(1, int(round(ww * sc)))
            rgb = np.asarray(Image.fromarray((np.clip(rgb, 0, 1) * 255).astype(np.uint8)).resize((nw, nh), Image.LANCZOS)) / 255.0
            cov = np.asarray(Image.fromarray((cov * 255).astype(np.uint8)).resize((nw, nh), Image.LANCZOS)) / 255.0
        return rgb, cov
    V = {(n, v): view(n, v) for n in ("fk", "a2") for v in ("top", "front", "iso")}
    x_top = int(76 * k)
    x_front = x_top + V[("fk", "top")][1].shape[1] + int(175 * k)
    x_iso = x_front + V[("fk", "front")][1].shape[1] + int(150 * k)
    y = int(44 * k)
    pos = {}
    rows = {}
    for name in ("fk", "a2"):
        top_h = V[(name, "top")][1].shape[0]
        iso_h = V[(name, "iso")][1].shape[0]
        row_h = max(top_h + int(110 * k if show_text else 62 * k), iso_h)
        yc = y + int(26 * k)                                   # top of the top view (after the length dimension)
        pos[(name, "top")] = (x_top, yc)
        pos[(name, "front")] = (x_front + (V[("fk", "front")][1].shape[1] - V[(name, "front")][1].shape[1]) // 2,
                                yc + (top_h - V[(name, "front")][1].shape[0]) // 2)
        pos[(name, "iso")] = (x_iso, y + (row_h - iso_h) // 2 - int(10 * k))
        rows[name] = (y, row_h)
        y += row_h + int(40 * k)
    H = y + int(10 * k)
    img = np.ones((H, W, 3)) * (np.array(bg) / 255.0)
    # soft contact shadows on the whole canvas, then the objects
    shadow = np.zeros((H, W))
    for (n, v), (x0, y0) in pos.items():
        rgb, cov = V[(n, v)]
        hh, ww = cov.shape
        oy, ox = int(round(3.0 * ppm * sc)), int(round(2.0 * ppm * sc))
        ys0, xs0 = y0 + oy, x0 + ox
        y1_, x1_ = min(H, ys0 + hh), min(W, xs0 + ww)
        shadow[ys0:y1_, xs0:x1_] = np.maximum(shadow[ys0:y1_, xs0:x1_], cov[:y1_ - ys0, :x1_ - xs0])
    shadow = gaussian_filter(shadow, 3.2 * ppm * sc * 0.6)
    img *= (1.0 - (0.22 if not dark else 0.40) * np.clip(shadow, 0, 1))[..., None]
    for (n, v), (x0, y0) in pos.items():
        rgb, cov = V[(n, v)]
        hh, ww = cov.shape
        sub = img[y0:y0 + hh, x0:x0 + ww]
        sub[:] = rgb * cov[..., None] + sub * (1 - cov[..., None])
    im = Image.fromarray((np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8))
    d = ImageDraw.Draw(im)
    d.text((x_top, int(6 * k)), "TOP", font=f_small, fill=mut)
    d.text((x_front, int(6 * k)), "FRONT", font=f_small, fill=mut)
    d.text((x_iso, int(6 * k)), "THREE-QUARTER VIEW", font=f_small, fill=mut)
    sz = ci["size_mm"]
    tick = int(9 * k)
    for name, Lmm, Wmm, Hmm in (("fk", sz[0], sz[1], sz[2]), ("a2", A2["length_mm"], A2["dia_mm"], A2["dia_mm"])):
        x0, y0 = pos[(name, "top")]
        bx0, by0, bx1, by1 = _bbox(V[(name, "top")][1])
        _dim_h(d, x0 + bx0, x0 + bx1, y0 + by0 - int(20 * k), "%.1f mm" % Lmm, f_dim, dim_ink, tick=tick)
        _dim_v(d, x0 + bx1 + int(22 * k), y0 + by0, y0 + by1,
               ("%.1f mm" % Wmm) if name == "fk" else ("Ø %.1f mm" % Wmm), f_dim, dim_ink, tick=tick)
        x0, y0 = pos[(name, "front")]
        bx0, by0, bx1, by1 = _bbox(V[(name, "front")][1])
        if name == "fk":
            _dim_v(d, x0 + bx1 + int(22 * k), y0 + by0, y0 + by1, "%.1f mm" % Hmm, f_dim, dim_ink, tick=tick)
        if not show_text:
            x0, y0 = pos[(name, "top")]
            ty = y0 + V[(name, "top")][1].shape[0] + int(14 * k)
            col = (BLUE_D if dark else BLUE) if name == "fk" else (ORANGE_D if dark else ORANGE)
            d.rounded_rectangle([x0, ty + int(3 * k), x0 + int(7 * k), ty + int(31 * k)], radius=max(1, int(3 * k)),
                                fill=col)
            d.text((x0 + int(20 * k), ty), "FlashKa Keychain v0.7" if name == "fk" else
                   "RovyVon Aurora A2 - size stand-in", font=font(23 * k, True), fill=ink)
        if show_text:
            x0, y0 = pos[(name, "top")]
            ty = y0 + V[(name, "top")][1].shape[0] + int(16 * k)
            col = BLUE if name == "fk" else ORANGE
            d.rounded_rectangle([x0, ty + int(4 * k), x0 + int(7 * k), ty + int(64 * k)], radius=max(1, int(3 * k)),
                                fill=col)
            if name == "fk":
                nm = "FlashKa Keychain v0.7"
                t1 = ("%.1f × %.1f × %.1f mm  ·  about %d g (estimate, not weighed)  ·  %s mAh"
                      " (one 14500 Li-ion cell)" % (sz[0], sz[1], sz[2], round(ci["mass_g"]), fmt_int(ci["battery_mAh"])))
            else:
                nm = "RovyVon Aurora A2 - size stand-in"
                t1 = ("%.1f mm × Ø %.1f mm  ·  %.1f g (1lumen) to %.1f g (Gen 4 listing)  ·  %d mAh "
                      "LiPo" % (A2["length_mm"], A2["dia_mm"], A2["mass_g"][0], A2["mass_g"][1], A2["battery_mAh"]))
            d.text((x0 + int(20 * k), ty), nm, font=f_name, fill=ink)
            d.text((x0 + int(20 * k), ty + int(38 * k)), t1, font=f_txt, fill=ink2)
    # scale bar (20 mm) under the front views
    sb_x = x_front
    sb_y = rows["a2"][0] + rows["a2"][1] - int(8 * k)
    L20 = 20 * ppm * sc
    d.rectangle([sb_x, sb_y - int(5 * k), sb_x + L20, sb_y], fill=dim_ink)
    d.text((sb_x + L20 + int(12 * k), sb_y - int(15 * k)), "20 mm", font=f_dim, fill=dim_ink)
    return im


def picture_size(M, SV, out_dir, dark=False, fname="comparison_size.png"):
    """comparison_size.png: header, the size block and the caption"""
    from PIL import Image, ImageDraw
    k = SV["k"]
    ci = SV["ci"]
    bg = PAGE_BG_D if dark else PAGE_BG
    ink, ink2, mut = (INK_D, INK2_D, MUTED_D) if dark else (INK, INK2, MUTED)
    block = draw_size_block(SV, dark)
    m = int(36 * k)
    head = int(118 * k)
    foot = int(92 * k)
    W = block.width
    im = Image.new("RGB", (W, head + block.height + foot), bg)
    im.paste(block, (0, head))
    d = ImageDraw.Draw(im)
    d.text((m, int(30 * k)), "Size, to scale", font=font(34 * k, True), fill=ink)
    d.text((m, int(76 * k)), "Top, front and three-quarter views of both lights at one common scale.",
           font=font(22 * k), fill=ink2)
    f_cap = font(19.5 * k)
    y = head + block.height + int(14 * k)
    d.text((m, y), size_caption(ci)[0], font=f_cap, fill=mut)
    d.text((m, y + int(30 * k)), size_caption(ci)[1], font=f_cap, fill=mut)
    path = os.path.join(out_dir, fname)
    save_png(im, path)
    return {"path": path}


def size_caption(ci):
    l1 = ("Render to scale. FlashKa: CAD model, not yet built; mass = parts in the CAD %.0f g + optic and LED board %.1f g + "
          "cell %.0f g (maker's data) + electronics %.1f g (estimate)."
          % (ci["mass_cad_g"], ci["mass_optic_g"] + ci["mass_ledboard_g"], ci["mass_cells_g"], ci["mass_electronics_g"]))
    l2 = ("RovyVon Aurora A2: plain stand-in of its published size (57.3 × 15.6 mm), not its real shape; data: maker's "
          "listings and 1lumen.  FlashKa battery: one %s (%s mAh typical, %s mAh minimum)."
          % (CELL["name"], fmt_int(CELL["mAh"]), fmt_int(CELL["mAh_min"])))
    if ci["placeholder"]:
        l2 = "Housing shape: the v%s model as a placeholder until the v0.7 housing is final.  " % ci["version"] + l2
    return l1, l2


# ----------------------------------------------------------------------------------------------
# picture: combined (README)
# ----------------------------------------------------------------------------------------------
def spec_rows(M, ci, out_info):
    """the spec strip: (label, FlashKa value, A2 value)"""
    fk, a2, kv = M["fk"], M["a2"], M["kv"]
    sz = ci["size_mm"]
    return [
        ("Light output", "%s lm" % fmt_int(fk.flux()), "%d lm" % round(a2.flux())),
        ("After 10 minutes", "%d lm" % round(kv["10min"]["otf"]), "%d lm" % round(A2["meas_lm"][2])),
        ("Peak intensity", "%s cd" % fmt_int(fk.peak), "%s cd" % fmt_int(a2.peak)),
        ("Throw (ANSI)", "%d m" % round(throw_m(fk.peak)), "%d m" % round(throw_m(a2.peak))),
        ("Size", "%.0f\u2009\u00d7\u2009%.0f\u2009\u00d7\u2009%.0f mm" % sz,
         "%.0f\u2009\u00d7\u2009\u00d8%.0f mm" % (A2["length_mm"], A2["dia_mm"])),
        ("Weight", "about %d g" % round(ci["mass_g"]), "%.1f–%d g" % (A2["mass_g"][0], round(A2["mass_g"][1]))),
        ("Battery", "%s mAh" % fmt_int(ci["battery_mAh"]), "%d mAh" % A2["battery_mAh"]),
        ("Extras", "Class 2 laser, Bluetooth presenter mode", "none listed"),
    ]


def picture_combined(M, beams, SV, out_info, out_dir, dark=False):
    from PIL import Image, ImageDraw
    k = SV["k"]
    OUTW = int(2400 * k)
    bg = PAGE_BG_D if dark else PAGE_BG
    ink, ink2, mut = (INK_D, INK2_D, MUTED_D) if dark else (INK, INK2, MUTED)
    rule = (48, 54, 61) if dark else (225, 224, 217)
    blue, orange = (BLUE_D, ORANGE_D) if dark else (BLUE, ORANGE)
    m = int(36 * k)
    # beams: the panels with their markers, no header, short names under them
    W, H = beams["W"], beams["H"]
    g = int(32 * k)
    # sizes
    f_title, f_sub = font(46 * k, True), font(23 * k)
    f_name, f_num = font(27 * k, True), font(21 * k)
    f_lab, f_val = font(18 * k), font(25 * k, True)
    f_cap = font(19.5 * k)
    size_block = draw_size_block(SV, dark, scale=1.0, show_text=False)
    rows = spec_rows(M, SV["ci"], out_info)
    y_title = int(34 * k)
    y_panels = int(150 * k)
    y_names = y_panels + H + int(18 * k)
    y_strip = y_names + int(92 * k)
    strip_h = int(176 * k)
    y_size = y_strip + strip_h + int(22 * k)
    y_cap = y_size + size_block.height + int(6 * k)
    Htot = y_cap + int(120 * k)
    im = Image.new("RGB", (OUTW, Htot), bg)
    d = ImageDraw.Draw(im)
    d.text((m, y_title), "FlashKa v0.7 vs RovyVon Aurora A2", font=f_title, fill=ink)
    d.text((m, y_title + int(64 * k)), "Render. FlashKa: simulated, not yet built. RovyVon Aurora A2: maker's data and "
           "1lumen measurement.", font=f_sub, fill=ink2)
    for n, kind in enumerate(("fk", "a2")):
        x = m + n * (W + g) - int(4 * k)
        from PIL import Image as _I
        panel = _I.fromarray(beams["imgs"][kind])
        pd_ = ImageDraw.Draw(panel, "RGBA")
        cx, cy = beams["centres"][kind]
        r = 7 * k
        pd_.ellipse([cx - r - 2 * k, cy - r - 2 * k, cx + r + 2 * k, cy + r + 2 * k], outline=(255, 255, 255, 220),
                    width=max(1, int(2 * k)))
        pd_.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(20, 22, 26, 230), width=max(1, int(2 * k)))
        txt = "%s lx" % fmt_int(beams["lab"][kind]["lux"])
        fb = font(20 * k, True)
        tw = pd_.textlength(txt, font=fb)
        bx, by = cx + 26 * k, cy - 58 * k
        pd_.line([(cx + r * 0.75, cy - r * 0.75), (bx, by + 30 * k)], fill=(20, 22, 26, 200), width=max(1, int(2 * k)))
        pd_.rounded_rectangle([bx, by, bx + tw + 22 * k, by + 34 * k], radius=8 * k, fill=(16, 18, 22, 205))
        pd_.text((bx + 11 * k, by + 17 * k), txt, font=fb, fill=(255, 255, 255, 255), anchor="lm")
        mask = _I.new("L", panel.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, W - 1, H - 1], radius=int(14 * k), fill=255)
        im.paste(panel, (x, y_panels), mask)
        col = blue if kind == "fk" else orange
        d.rounded_rectangle([x, y_names + int(4 * k), x + int(7 * k), y_names + int(62 * k)], radius=max(1, int(3 * k)),
                            fill=col)
        name = "FlashKa Keychain v0.7" if kind == "fk" else "RovyVon Aurora A2 - size stand-in"
        sub = ("simulated, not yet built  ·  %s lx at the wall centre" % fmt_int(beams["lab"]["fk"]["lux"])
               if kind == "fk" else "beam: maker's data and 1lumen measurement  ·  %s lx at the wall centre"
               % fmt_int(beams["lab"]["a2"]["lux"]))
        d.text((x + int(20 * k), y_names), name, font=f_name, fill=ink)
        d.text((x + int(20 * k), y_names + int(36 * k)), sub, font=f_num, fill=ink2)
    # spec strip
    d.line([(m, y_strip), (OUTW - m, y_strip)], fill=rule, width=max(1, int(2 * k)))
    d.line([(m, y_strip + strip_h), (OUTW - m, y_strip + strip_h)], fill=rule, width=max(1, int(2 * k)))
    # column widths from their content (label or dot + value, whichever is wider), the rest shared out evenly
    need = [max(d.textlength(lab.upper(), font=f_lab),
                int(22 * k) + max(d.textlength(vf, font=f_val), d.textlength(va, font=f_val))) + int(36 * k)
            for lab, vf, va in rows]
    spare = (OUTW - 2 * m) - sum(need)
    if spare < 0:
        log("  combined: spec strip %d px too wide" % -spare)
    cws = [n_ + spare / len(rows) for n_ in need]
    x0 = m
    for i, (lab, vf, va) in enumerate(rows):
        if i:
            d.line([(x0, y_strip + int(18 * k)), (x0, y_strip + strip_h - int(18 * k))], fill=rule, width=1)
        tx = x0 + int(16 * k)
        d.text((tx, y_strip + int(20 * k)), lab.upper(), font=f_lab, fill=mut)
        for j, (v, col) in enumerate(((vf, blue), (va, orange))):
            yy = y_strip + int(62 * k) + j * int(50 * k)
            d.ellipse([tx, yy + int(9 * k), tx + int(12 * k), yy + int(21 * k)], fill=col)
            d.text((tx + int(22 * k), yy), v, font=f_val, fill=ink)
        x0 += cws[i]
    # size block (views to scale, same scale for both lights)
    im.paste(size_block, (0, y_size))
    kv = M["kv"]
    l1 = ("Light out of the front at switch-on, 25 °C.  FlashKa: firmware 0.7.0 simulation with the LED and optic data "
          "(%s lm at 30 s; %d lm with the LED at 85 °C); size from the CAD; mass estimated, not weighed."
          % (fmt_int(kv["30s"]["otf"]), round(kv["hot"]["otf"])))
    l2 = ("RovyVon Aurora A2 (Gen 3/4): %d lm at switch-on and %d lm after 10 min measured by 1lumen; size, weight and "
          "battery from the maker's listings." % (A2["meas_lm"][0], A2["meas_lm"][2]))
    l3 = ("Wall: E = I(θ) cos α / d², white wall 2 m away, one exposure for both panels.  "
          "A2 body: plain size stand-in, not its real shape.")
    if SV["ci"]["placeholder"]:
        l3 += "  Housing shape: v%s placeholder." % SV["ci"]["version"]
    for n_, t_ in enumerate((l1, l2, l3)):
        d.text((m, y_cap + n_ * int(30 * k)), t_, font=f_cap, fill=mut)
    # layout check: the longest caption line must fit
    for t_ in (l1, l2, l3):
        if d.textlength(t_, font=f_cap) > OUTW - 2 * m:
            log("  combined: caption line too long (%d px): %s" % (d.textlength(t_, font=f_cap), t_[:60]))
    for i, (lab, vf, va) in enumerate(rows):
        for v in (vf, va):
            if int(22 * k) + d.textlength(v, font=f_val) > cws[i] - int(24 * k):
                log("  combined: spec value too wide:", v)
    path = os.path.join(out_dir, "comparison_combined%s.png" % ("_dark" if dark else ""))
    save_png(im, path)
    return path


# ----------------------------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------------------------
def fw_sim_constants():
    """the model constants written in the firmware's thermal simulation (for the sources file)"""
    path = os.path.join(FW_CORE, "tests", "thermal_v07.rs")
    txt = open(path).read()
    out = {"path": os.path.relpath(path, REPO)}
    for name in ("C_HEAD", "C_BODY", "R_HEAD_BODY", "R_BODY_AIR", "SENSOR_TAU_S", "AMBIENT_C", "CAPACITY_MAH", "R_INT",
                 "EFF", "LIGHT_FRACTION", "MCU_A", "C_CELL", "R_CELL_BODY", "R_CELL", "R_DROP"):
        m = re.search(r"const %s:\s*f64\s*=\s*([0-9.]+)\s*;" % name, txt)
        if not m and name in ("C_CELL", "R_CELL_BODY", "R_CELL", "R_DROP"):
            out[name] = None
            continue
        if not m:
            raise SystemExit("%s: constant %s not found" % (path, name))
        out[name] = float(m.group(1))
    return out


def table_bounce_lx(beam, src_mm, pt_mm=(-20.0, -30.0, 0.0)):
    """illuminance (lx) on the table top at pt from the light the lit wall reflects (diffuse wall, wall area above
    the table plane): integral of L_wall cos(t_table) cos(t_wall) / r^2 dA, L_wall = rho E / pi"""
    ys = (np.arange(1600) + 0.5) / 1600 * 8.0 - 4.0
    zs = (np.arange(600) + 0.5) / 600 * 3.0
    dA = (8.0 / 1600) * (3.0 / 600)
    Y, Z = np.meshgrid(ys, zs)
    Q = np.stack([np.full(Y.size, WALL_X / 1000.0), Y.ravel(), Z.ravel()], 1)
    Eb = illuminance(beam, np.asarray(src_mm) / 1000.0, np.array([1.0, 0, 0]), Q, np.tile([-1.0, 0, 0], (len(Q), 1)))
    P = np.asarray(pt_mm) / 1000.0
    d = Q - P
    r2 = np.einsum("ij,ij->i", d, d)
    ct, cw = d[:, 2] / np.sqrt(r2), d[:, 0] / np.sqrt(r2)
    return float(np.sum(RHO_WALL * Eb / np.pi * ct * cw / r2) * dA)


def write_sources(M, ci, out_info, rep, args):
    """sources_comparison.md next to the pictures: every number with its source"""
    fk, a2, sims, kv, sh, geo = M["fk"], M["a2"], M["sims"], M["kv"], M["shape"], M["geo"]
    tb, hg = sims["turbo"], sims["high"]
    eff, cdl = OPTIC["eff"], OPTIC["cd_per_lm"]
    lab = beam_labels(M)
    sz = ci["size_mm"]
    sc = M["sim_consts"]
    rel_out = os.path.relpath(os.path.abspath(args.out_dir), HERE)
    rel_cad = os.path.relpath(os.path.abspath(args.cad_dir), HERE)
    on, s30, hot, k10, sus = kv["on"], kv["30s"], kv["hot"], kv["10min"], kv["sustained"]
    tbl = M["led_model"]["table"]
    L = []
    w = L.append
    w("<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->")
    w("# FlashKa v0.7 vs RovyVon Aurora A2: sources of every number")
    w("")
    w("The pictures `comparison_beams.png`, `comparison_size.png`, `comparison_output.png`, `comparison_combined.png` "
      "and `comparison_combined_dark.png` in this folder are made by "
      "[`tools/compare/compare_a2.py`](%s). Rerun (needs Rust/cargo for the FlashKa "
      "firmware simulation, VTK, cadquery, trimesh, numpy, scipy, Pillow, matplotlib and an X server or `xvfb-run`):"
      % os.path.relpath(os.path.abspath(__file__), os.path.abspath(args.out_dir)))
    w("")
    w("```sh")
    w("cd hardware/flashka-keychain-v07/tools/compare")
    w("xvfb-run -a python3 compare_a2.py %s %s" % (rel_cad, rel_out))
    w("```")
    w("")
    w("**FlashKa Keychain v0.7 has not been built.** Its light figures are simulated: the FlashKa firmware 0.7.0 thermal "
      "simulation gives the LED current and the head temperature over time, the Luminus SST-20 Gen 2 datasheet gives the "
      "LED's lumens, and the LEDiL datasheet (LEDiL's own simulation) gives the optic's efficiency, beam width and "
      "intensity. Its size comes from the CAD; its mass is an estimate. Every picture of it is a render. The RovyVon "
      "Aurora A2 figures are the maker's data (retail listings) and the independent measurement published by 1lumen. "
      "Labels: *simulated*, *datasheet*, *model*, *CAD*, *estimate*, *maker's data*, *measured*.")
    w("")
    w("## Which RovyVon Aurora A2")
    w("")
    w("| Generation | What is known | Used here |")
    w("|---|---|---|")
    w("| Gen 1 (2018) | Cree XP-G3, 550 lm, 980 cd, 80 m, 130 mAh, micro-USB, 53.9 x 14.5 mm, 28 g ([BudgetLightForum review](%s)) | no: older design |" % URL_BLF)
    w("| Gen 3 (2022) | Luminus SST-20 cool white, 650 lm, 2,500 cd, 110 m, 300 mAh LiPo, USB-C, 57.3 x 15.6 mm; "
      "**measured by [1lumen](%s)** (September 2022) | the measurement: light output, intensity, throw |" % URL_1LUMEN)
    w("| Gen 4 (G4, sold in 2026) | SST-20 6500 K 650 lm (or Nichia 219C 420 lm), High 650 lm stepping down to 100 lm after "
      "60 s, 110 m, 300 mAh LiPo, USB-C, 57.3 x 15.6 mm, 33.9 g ([Adventure Carry](%s), [Kapuga](%s), [Mukama](%s)) | "
      "the maker's data: size, battery, weight, step-down |" % (URL_ADVC, URL_KAPUGA, URL_MUKAMA))
    w("")
    w("Gen 3 and Gen 4 share the LED, the 650 lm rating, the 110 m beam distance, the 300 mAh cell and the 57.3 x 15.6 mm "
      "size, so the Gen 3 measurement is the best public stand-in for the current light; no independent test of Gen 4 "
      "was found. That the two generations perform the same is an assumption. The official rovyvon.com product page "
      "could not be opened from the machine that made these pictures, so the maker's figures are taken from the "
      "specification table that 1lumen copied from the maker (Gen 3) and from the Gen 4 retail listings above.")
    w("")
    w("## Numbers in the pictures")
    w("")
    w("FlashKa values are for the Balanced profile (the default) at 25 °C in still air with a full battery; "
      "\"switch-on\" is the first simulated second.")
    w("")
    w("| Number | FlashKa v0.7 | Source / kind | RovyVon Aurora A2 | Source / kind |")
    w("|---|---|---|---|---|")
    w("| Light output at switch-on (out of the front) | %s lm | simulated: %s lm at the LED (datasheet model %s lm at %s mA "
      "and Tj 85 °C, x %.3f for Tj %.1f °C) x %.2f optic | %d lm | measured, [1lumen](%s), Gen 3 |" % (
          fmt_int(on["otf"]), fmt_int(on["phi"]), fmt_int(on["lm_led85"]), fmt_int(on["mA"]), on["f"], on["Tj"], eff,
          A2["meas_lm"][0], URL_1LUMEN))
    w("| Maker's rating | - | - | 650 lm | maker's data ([1lumen spec table](%s), [Adventure Carry](%s)) |" % (URL_1LUMEN, URL_ADVC))
    w("| Light output at 30 s (the ANSI FL 1 time) | %s lm | simulated: %s mA (thermal regulation from %d s), Tj %.1f °C, "
      "x %.3f | %d lm | measured, [1lumen](%s) |" % (fmt_int(s30["otf"]), fmt_int(s30["mA"]), round(kv["turbo_full_s"]),
                                                     s30["Tj"], s30["f"], A2["meas_lm"][1], URL_1LUMEN))
    w("| Light output with the LED at Tj 85 °C (datasheet reference, turbo current) | %d lm | datasheet model %s lm x %.2f; "
      "the simulation never gets the LED that hot (highest Tj %.0f °C) | - | - |" % (
          round(hot["otf"]), fmt_int(hot["phi"]), eff, kv["Tj_max"]))
    w("| Light output after 10 min | %d lm (turbo at the start), %d lm (High at the start) | simulated | %d lm | "
      "measured, [1lumen](%s) |" % (round(k10["otf"]), round(k10["otf_high"]), A2["meas_lm"][2], URL_1LUMEN))
    w("| Sustained output, 25 °C still air (mean of 15-25 min) | %d lm (about %d mA, Tj %.0f °C; %d lm with the LED at "
      "85 °C) | simulated | - | - |" % (round(sus["otf"]), round(sus["mA"]), sus["Tj"], round(sus["otf85"])))
    w("| Peak intensity | %s cd at switch-on (%s cd at 30 s; %s cd at Tj 85 °C) | %.1f cd per LED lumen (LEDiL datasheet, "
      "simulated) x LED lumens | %s cd at switch-on (2,750 cd at 30 s; maker: 2,500 cd for Gen 3) | measured, "
      "[1lumen](%s) |" % (fmt_int(on["cd"]), fmt_int(s30["cd"]), fmt_int(hot["cd"]), cdl, fmt_int(a2.peak), URL_1LUMEN))
    w("| Throw (ANSI FL 1: distance to 0.25 lx = 2 sqrt(cd)) | %.1f m at switch-on (%.1f m at 30 s; %.1f m at Tj 85 °C) | "
      "from the peak | %d m at switch-on (105 m at 30 s; maker: 110 m) | 1lumen's published value; maker's data |" % (
          on["throw"], s30["throw"], hot["throw"], round(throw_m(a2.peak))))
    w("| Illuminance at the wall centre, 2 m | {:,.1f} lx | E = I0 / d^2 (d from the optic's exit) | {:,.1f} lx | E = I0 / d^2 "
      "with 1lumen's 3,775 cd |".format(lab["fk"]["lux"], lab["a2"]["lux"]))
    w("| Size | %.1f x %.1f x %.1f mm | CAD (`%s`) | 57.3 mm x 15.6 mm diameter | maker's data, confirmed by 1lumen |" % (
        sz[0], sz[1], sz[2], os.path.relpath(os.path.join(os.path.abspath(args.cad_dir), "FlashKa_tray.stl"), V7)))
    w("| Weight | about %d g (%.1f g: breakdown below) | CAD + estimate, not weighed | 19.5 g (1lumen page) to 33.9 g "
      "(Gen 4 listing at Adventure Carry; 34 g for the stainless version at Mukama) | 1lumen / maker's data |" % (
          round(ci["mass_g"]), ci["mass_g"]))
    w("| Battery | %s mAh typical, %s mAh minimum (both at 0.2C): one [%s](%s) Li-ion cell, %.1f x %.1f mm, %.2f V "
      "nominal, %.0f A maximum continuous, about %.0f g; the firmware's runtime estimates use %s mAh, the simulation "
      "%s mAh | maker's data; firmware board.rs; simulation | 300 mAh LiPo, built in | maker's data |" % (
          fmt_int(CELL["mAh"]), fmt_int(CELL["mAh_min"]), CELL["name"], URL_VAPCELL, CELL["size_mm"][0],
          CELL["size_mm"][1], CELL["V"], CELL["max_A"], CELL["g"],
          fmt_int(M["led_model"]["capacity_mah"]) if M["led_model"].get("capacity_mah") else "-",
          fmt_int(sc["CAPACITY_MAH"])))
    w("| Extras | Class 2 laser, Bluetooth presenter mode | design | none listed by the maker | maker's data |")
    w("| Runtime from turbo (not in the pictures) | %.1f min to the ANSI end point (10 %% of the 30 s output), off after "
      "%.1f min | simulated | 1 h 04 min to the ANSI end point, off at 1 h 07 min | measured, [1lumen](%s) |" % (
          kv["runtime_min"], kv["off_min"], URL_1LUMEN))
    w("")
    w("Mass (estimate, not weighed): parts in the housing CAD %.2f g (%s; `housing_interface.json`, 6061 aluminium 2.70 "
      "g/cm3 and the other materials' densities); optic %.3f g and copper LED board %.3f g (same file); cell %.0f g (one "
      "%s, about %.0f g: maker's data); electronics %.2f g (estimate: %s). Not counted: tape, foam and the cell's nickel "
      "strips (a fraction of a gram)." % (
          ci["mass_cad_g"], ", ".join("%s %.3f g" % (k_.replace("FlashKa_", ""), v) for k_, v in ci["mass_parts"].items()),
          ci["mass_optic_g"], ci["mass_ledboard_g"], ci["mass_cells_g"], CELL["name"], CELL["g"],
          ci["mass_electronics_g"], ", ".join("%s %.2f g" % (n_, g_) for n_, g_ in ELECTRONICS_G)))
    w("")
    w("## FlashKa: simulated output")
    w("")
    cell_txt = ""
    if sc["C_CELL"] is not None and sc["R_CELL_BODY"] is not None:
        cell_txt = "the cell as a third node of %.0f J/K coupled to the body by %.0f K/W (estimate), " % (
            sc["C_CELL"], sc["R_CELL_BODY"])
    path_txt = ""
    if sc["R_CELL"] is not None and sc["R_DROP"] is not None:
        path_txt = ("%.2f ohm from the cell to the board and, when the cell sags and the buck runs at 100 %% duty, at "
                    "most (V - %.2f V) / %.2f ohm for the LED, " % (sc["R_CELL"], LED["vf0"], LED["vf_slope"] + sc["R_DROP"]))
    w("The FlashKa firmware's own controller (firmware 0.7.0 for the v0.7 board) drives a thermal and battery model of "
      "the light in a host test, [`%s`](%s): head %.2f J/K, body %.2f J/K, %shead to body %.1f K/W, body to still air at "
      "%.0f °C %.2f K/W, temperature sensor following the head with a %.0f s time constant; one cell of %s mAh with a "
      "generic 3.6 V open-circuit curve (no F15 curve is published), %sLED %.2f V + %.2f V/A, %.0f %% from the cell to "
      "the LED, %.0f %% of the LED power leaves as light, %.0f mA for the controller and radio. The boards, keys and "
      "optic store no heat in the model and nobody holds the light, so the times are on the short side. This script "
      "runs it (%s):" % (
          sc["path"], os.path.relpath(os.path.join(REPO, sc["path"]), os.path.abspath(args.out_dir)), sc["C_HEAD"],
          sc["C_BODY"], cell_txt, sc["R_HEAD_BODY"], sc["AMBIENT_C"], sc["R_BODY_AIR"], sc["SENSOR_TAU_S"],
          fmt_int(sc["CAPACITY_MAH"]), path_txt, LED["vf0"], LED["vf_slope"], 100 * sc["EFF"],
          100 * sc["LIGHT_FRACTION"], 1000 * sc["MCU_A"], M["sim_src"]))
    w("")
    w("```sh")
    w("cd hardware/flashka-keychain-v06/firmware/flashka-core")
    w(fw_command())
    w("```")
    w("")
    w("It writes one row per second; the scenarios used are `%s` (Turbo, %s mA, 60 s timer, then High) and `%s` "
      "(High, %s mA), both from a full cell. Turbo runs at full current for %d s, High for %d s; then the thermal "
      "regulation holds the head and both settle at the same level." % (
          FW_SCENARIOS["turbo"], fmt_int(on["mA"]), FW_SCENARIOS["high"], fmt_int(kv["high_on"]["mA"]),
          round(kv["turbo_full_s"]), round(kv["high_full_s"])))
    w("")
    w("| Time | Turbo: LED current | head | Tj | factor | LED lumens | out of the front | High: LED current | out of the front |")
    w("|---|---|---|---|---|---|---|---|---|")
    for t in (1, 10, 30, 57, 59, 60, 90, 120, 210, 300, 600, 900, 1200, 1800):
        i, j = row_at(tb, t), row_at(hg, t)
        lab_t = "%d s" % t if t < 120 else "%d min" % (t // 60)
        w("| %s | %s mA | %.1f °C | %.1f °C | %.3f | %s lm | %s lm | %s mA | %s lm |" % (
            lab_t, fmt_int(tb["led_mA"][i]), tb["T_head_C"][i], tb["Tj"][i], tb["f"][i], fmt_int(tb["phi"][i]),
            fmt_int(tb["otf"][i]), fmt_int(hg["led_mA"][j]), fmt_int(hg["otf"][j])))
    w("")
    w("Highest simulated temperatures: head %.1f °C, body %.1f °C (the surface held in the hand)%s, LED junction %.1f °C "
      "(Tj model below)." % (kv["T_head_max"], kv["T_body_max"],
                            ", cell %.1f °C" % kv["T_cell_max"] if kv["T_cell_max"] is not None else "", kv["Tj_max"]))
    w("")
    bc = M["by_charge"]
    if bc:
        w("### Turbo and the cell's charge")
        w("")
        hf = sims.get("half")
        half_txt = ""
        if hf is not None:
            half_txt = (" From a half-full cell (`%s`) turbo starts at %s mA = %s lm out of the front (junction factor; "
                        "%s lm with the LED at 85 °C) instead of %s lm." % (
                            FW_SCENARIOS["half"], fmt_int(hf["led_mA"][0]), fmt_int(hf["otf"][0]),
                            fmt_int(hf["lm_front"][0]), fmt_int(on["otf"])))
        w("One Li-ion cell sags under load: below a certain charge the buck runs at 100 %% duty and the LED gets less "
          "than the %s mA asked for.%s Turbo 30 s after switching on, by the charge at switch-on (LED current printed by "
          "the simulation test; lumens out of the front with the LED at 85 °C, the firmware's model, and with this "
          "script's junction factor; head temperature from the full-cell and half-full-cell runs, for the other charges "
          "interpolated in LED power, estimate):" % (fmt_int(on["mA"]), half_txt))
        w("")
        w("| Charge at switch-on | LED current at 30 s | Out of the front, LED at 85 °C | Out of the front, junction factor |")
        w("|---|---|---|---|")
        for r_ in bc:
            w("| %d %% | %s mA | %s lm | %s |" % (r_["pct"], fmt_int(r_["mA"]), fmt_int(r_["otf85"]),
                                                ("%s lm%s" % (fmt_int(r_["otf"]), "" if r_["how"].startswith("simulated")
                                                              else " (estimate)")) if "otf" in r_ else "-"))
        w("")
    w("## FlashKa: LED lumens and junction temperature")
    w("")
    w("- LED: %s. [Luminus datasheet](%s): G1 bin minimum %d lm at 1.5 A and %s lm at 3.0 A (both Tj 85 °C), %d lm at "
      "1.5 A and Tj 25 °C; thermal resistance junction to solder point %.1f °C/W; 3.0 A maximum DC." % (
          LED["name"], URL_LUMINUS, LED["lm_1500_85"], fmt_int(LED["lm_3000_85"]), LED["lm_1500_25"], LED["rth_jsp"]))
    w("- The firmware's LED model (`%s`, `LED_LM_TABLE`, mA -> lm at the LED, Tj 85 °C, linear between the points): %s. "
      "The 1.5 A and 3.0 A points are the datasheet's G1 minimum; the other points are the firmware's estimates, not "
      "datasheet values. The simulator's LED lumens are this table at the simulated "
      "current (checked below)." % (M["led_model"]["path"], ", ".join("%s mA %s lm" % (fmt_int(a_), fmt_int(b_)) for a_, b_ in tbl)))
    w("- Junction factor: relative flux %.2f at Tj %.0f °C to %.2f at Tj %.0f °C, linear (%d / %d lm = %.3f from the "
      "datasheet at 1.5 A; assumed to hold at every current)." % (LED["f_lo"], LED["tj_lo"], LED["f_hi"], LED["tj_hi"],
                                                                  LED["lm_1500_25"], LED["lm_1500_85"],
                                                                  LED["lm_1500_25"] / LED["lm_1500_85"]))
    w("- Tj = simulated head temperature + %.1f °C/W x %.0f %% x LED power, LED power = (%.2f V + %.2f V/A x I) x I (the "
      "simulation's LED model). Assumption: %.0f %% of the LED's electrical power is heat (the simulation counts the "
      "other %.0f %% as light). Not counted: the copper LED board and the 0.1 mm thermal paste between the LED's solder "
      "point and the head; at about 0.3 K/W (estimate for that paste layer over the 78.5 mm2 contact) they would add "
      "about 2 K at turbo, i.e. about 0.3 %% less light." % (
          LED["rth_jsp"], 100 * LED["heat_frac"], LED["vf0"], LED["vf_slope"], 100 * LED["heat_frac"],
          100 * (1 - LED["heat_frac"])))
    w("- Switch-on (first simulated second): head %.2f °C, %s mA, LED power %.2f W, Tj %.1f °C, factor %.3f, %s lm at the "
      "LED. At 30 s: head %.2f °C, %s mA, Tj %.1f °C, factor %.3f, %s lm. Hot reference: Tj 85 °C, factor 1.000, %s lm." % (
          on["T_head"], fmt_int(on["mA"]), float(led_power_w(on["mA"])), on["Tj"], on["f"], fmt_int(on["phi"]),
          s30["T_head"], fmt_int(s30["mA"]), s30["Tj"], s30["f"], fmt_int(s30["phi"]), fmt_int(hot["phi"])))
    w("")
    w("## FlashKa: optic model (no front window)")
    w("")
    w("- Optic: %s. [LEDiL datasheet](%s), row for the SST-20 Gen 2 (simulated by LEDiL, not measured): %.0f %% "
      "efficiency, %.0f deg FWHM, %.1f cd/lm. The firmware uses the same %d %% (`OPTIC_PCT` in board.rs). The optic's "
      "front face is the exit: no window in front of it." % (OPTIC["name"], URL_LEDIL, 100 * eff, OPTIC["fwhm_deg"], cdl,
                                                              M["led_model"]["optic_pct"]))
    w("- Intensity per LED lumen: I(theta) = a exp(-theta^2 / (2 sigma^2)) + b cos(theta) S(theta), S = raised-cosine edge "
      "from %.0f to %.0f deg. Conditions: a + b = %.1f cd/lm, 2 pi x integral(I sin theta dtheta) = %.2f, I(%.0f deg) = "
      "I(0) / 2. Solved: sigma = %.3f deg, a = %.4f cd/lm, b = %.4f cd/lm (%.1f %% of the peak). The core carries %.1f %% "
      "of the light out of the front, the spill %.1f %%." % (
          OPTIC["edge"][0], OPTIC["edge"][1], cdl, eff, OPTIC["fwhm_deg"] / 2, sh["sigma_deg"], sh["a"], sh["b"],
          100 * sh["b"] / cdl, 100 * sh["core_share"], 100 * sh["spill_share"]))
    w("- So the datasheet's three numbers need about %.1f %% of the light outside a Gaussian core. The peak, the lumens "
      "and the wall-centre illuminance do not depend on this split; the spill's brightness does:" % (100 * sh["spill_share"]))
    w("")
    w("| Assumption | Spill share | sigma | Spill brightness at 25-45 deg (base = 1) |")
    w("|---|---|---|---|")
    w("| base: edge %.0f-%.0f deg, cos spill, %.0f deg FWHM, %.1f cd/lm, %.0f %% | %.1f %% | %.2f deg | 1.00 |" % (
        OPTIC["edge"][0], OPTIC["edge"][1], OPTIC["fwhm_deg"], cdl, 100 * eff, 100 * sh["spill_share"], sh["sigma_deg"]))
    for name, r in M["sens"]:
        if r is None:
            w("| %s | no solution with a non-negative spill | - | - |" % name)
        else:
            w("| %s | %.1f %% | %.2f deg | %.2f |" % (name, 100 * r["spill_share"], r["sigma_deg"], r["spill_rel"]))
    w("")
    w("  The FWHM and the peak decide the split most: one degree of FWHM moves the spill share by about 10 points, so the "
      "spill in the picture is uncertain by a factor of about 2; the hotspot is not.")
    w("- Bore: the optic's front (holder rim) sits %.1f mm behind the front face (%.1f-%.1f mm with the optic's height tolerance) "
      "in the %.2f mm bore; a ray from the edge of the %.1f mm exit clears the bore mouth up to %.1f deg (nominal) or %.1f "
      "deg (deepest seat; `housing_interface.json`). The model sends %.2f %% of the light beyond %.1f deg and %.3f %% "
      "beyond %.1f deg, so the bore can take at most about %.1f %% (not subtracted)." % (
          geo["recess"], geo["recess_range"][0], geo["recess_range"][2], geo["bore_d"], geo["exit_d"],
          geo["clear_deg"]["nominal"], geo["clear_deg"]["deepest"], 100 * flux_beyond(fk, geo["clear_deg"]["deepest"]),
          geo["clear_deg"]["deepest"], 100 * flux_beyond(fk, geo["clear_deg"]["nominal"]), geo["clear_deg"]["nominal"],
          100 * flux_beyond(fk, geo["clear_deg"]["deepest"])))
    w("- Emission point in the beam scene: the centre of the optic's exit face, %.2f mm behind the light's front face "
      "(%s), on the LED axis." % (geo["x_exit"], geo["exit_src"]))
    w("- Plausibility: the model gives %.2f cd per lumen out of the front (%.1f / %.2f); the A2 measured %.2f cd/lm at "
      "switch-on (3,775 cd / 633 lm, 1lumen)." % (cdl / eff, cdl, eff, A2["meas_cd"][0] / A2["meas_lm"][0]))
    w("")
    w("## RovyVon Aurora A2: beam model (TIR optic)")
    w("")
    w("- I(theta) = I_h exp(-theta^2 / (2 sigma^2)) + I_s cos(theta) S(theta), S = raised-cosine edge from %.0f to %.0f deg." % A2_SPILL_EDGE)
    w("- Conditions: I(0) = I_h + I_s = %s cd and 2 pi x integral(I sin theta dtheta) = %d lm (1lumen, at switch-on); the spill "
      "carries an assumed %d %% of the light (TIR optics put most light into the hotspot; 1lumen describes \"a defined "
      "hotspot with a light spill\")." % (fmt_int(a2.peak), round(a2.flux()), round(100 * A2_SPILL_SHARE)))
    w("- Solved: I_h = %s cd, I_s = %.1f cd, sigma = %.2f deg (hotspot %.1f deg wide at half maximum). Peak and lumens are "
      "matched exactly; the ANSI throw 2 sqrt(I0) = %.0f m equals 1lumen's published %d m." % (
          fmt_int(a2.info["I_h"]), a2.info["I_s"], a2.info["sigma_deg"], a2.info["fwhm_deg"], throw_m(a2.peak),
          A2["meas_throw_m"][0]))
    w("- What the assumption changes: the wall-centre illuminance and the lumens do not depend on it. A spill share of 15 % or "
      "35 % would make the hotspot about 1 deg wider or narrower and the far spill about 40 % weaker or stronger.")
    w("")
    bright = "FlashKa's" if lab["fk"]["lux"] >= lab["a2"]["lux"] else "A2's"
    w("## How the beam picture is made")
    w("")
    w("- Scene (mm): dark matte table (reflectance %.3f, satin finish: GGX microfacet sheen, F0 = %.2f, roughness %.2f), "
      "each light resting at the table edge, white matte wall (reflectance %.2f) %.0f mm in front of the lights, a dim "
      "room (%.0f lx everywhere) and a small warm spot lamp on the light body that does not reach the wall; the same in "
      "both panels. Haze: %.3f /m, single scattering, isotropic." % (
          RHO_TABLE, TABLE_F0, TABLE_ALPHA, RHO_WALL, WALL_X, E_AMB, HAZE_SIGMA))
    w("- Wall and table luminance in numpy from E = I(theta) cos(alpha) / d^2 and L = rho E / pi (direct light). The "
      "light that the lit wall reflects onto the table (%.1f lx for the FlashKa and %.1f lx for the A2, on the table "
      "next to the head) is left out: on the dark table it stays below the black point of the tone curve, and it "
      "does not change the wall. Light bodies: VTK physically based rendering, lit by the environment they see (the "
      "computed wall, the room, the lamp); soft shadows and ambient occlusion from VTK depth maps. Both beams are drawn "
      "in the same neutral white, so colour plays no part in the comparison." % (
          table_bounce_lx(fk, (-geo["x_exit"], 0.0, geo["Z_axis"])),
          table_bounce_lx(a2, (0.0, 0.0, A2["dia_mm"] / 2 + 0.25))))
    w("- One exposure and one tone curve for both panels: white point = %.2f x the brightest wall luminance (the %s wall "
      "centre), a log2 curve over %.1f stops with a power toe of %.2f, sRGB output, dither. The same luminance gives "
      "the same pixel value in both panels." % (TONE_WHITE, bright, TONE_STOPS, TONE_G))
    w("- The A2 is drawn as a plain size stand-in (rounded tube, lens face, one clip ring) from its published size; "
      "no logo, no lettering and no design details of the real light.")
    w("- The size views show the CAD of the v0.7 housing with the optic (clear lens drawn see-through, black holder), "
      "the laser module, the USB-C socket, the screws and the RF window where they are visible; parts inside the body "
      "are left out.")
    w("")
    w("## Checks run with every picture")
    w("")
    for line in rep:
        w("- " + re.sub(r" {2,}", " ", line))
    w("")
    w("## Not verified")
    w("")
    w("- FlashKa v0.7 has not been built: no measured lumens, candela, runtime, temperatures or mass. The first build "
      "should measure them (docs/testing.md).")
    w("- The optic figures are LEDiL's simulation for the SST-20 Gen 2, not a measurement. How well the LED is centred "
      "and seated under the optic (pins cut off, optic glued in the bore) changes the peak and is not modelled. The "
      "core/spill split is a model choice (table above).")
    w("- The LED's flux between and below the datasheet's 1.5 A and 3.0 A points is the firmware's estimate; the junction "
      "factor assumes the 1.5 A ratio (25 °C / 85 °C) at every current; the LED board and paste under the LED are not in "
      "the Tj model; the thermal model has no hand, stores no heat in the boards, keys and optic, and couples the cell to "
      "the body with an estimated 8 K/W.")
    w("- The cell: no independent test of the %s at %.0f A was found; the simulation uses a generic open-circuit curve "
      "(no F15 curve is published) and about %.2f ohm from the cell to the board (its DC resistance estimated from the "
      "maker's %d mOhm AC value). The runtime is for a typical cell (%s mAh); a cell at the maker's minimum (%s mAh) "
      "would run about %d %% as long (proportional estimate). The electronics mass is an estimate." % (
          CELL["name"], CELL["max_A"], sc["R_CELL"] if sc["R_CELL"] is not None else float("nan"), CELL["r_ac_mohm"],
          fmt_int(sc["CAPACITY_MAH"]), fmt_int(CELL["mAh_min"]), round(100 * CELL["mAh_min"] / sc["CAPACITY_MAH"])))
    w("- No independent measurement of the Gen 4 A2 was found; the Gen 3 measurement stands in for it. The official "
      "rovyvon.com page could not be opened from here; 1lumen's runtime graphs exist only as pictures, so the chart "
      "shows the three published points (switch-on, 30 s, 10 min) without a line between them.")
    w("- The A2 beam shape (hotspot width, spill) is a model fitted to its lumens and candela with an assumed spill share; "
      "the real TIR beam has a sharper hotspot edge and faint rings.")
    w("- The weight of the A2 differs between sources: 19.5 g on 1lumen's page, 33.9 g at Adventure Carry (whose page "
      "names both an aluminium and a stainless body) and 34 g for the stainless Gen 4 at Mukama; the pictures show the "
      "range.")
    path = os.path.join(args.out_dir, "sources_comparison.md")
    open(path, "w").write("\n".join(L) + "\n")
    log("wrote", path)


def build_models(args, tmp):
    geo = flashka_geo(args.cad_dir)
    led_model = board_led_model()
    if args.fw_sim:
        folder, sim_src = os.path.abspath(args.fw_sim), "here from CSV files given with --fw-sim"
    else:
        folder, sim_src = run_fw_sim(tmp, args.cargo_target_dir), "the build folder stays outside the repository"
    sims = load_fw_sim(folder)
    apply_led_model(sims)
    kv = key_values(sims)
    shape = optic_shape()
    if shape is None:
        raise SystemExit("optic model: no solution for the datasheet values")
    fk = flashka_beam(kv["on"]["phi"], shape, "switch-on")
    a2 = a2_beam(A2["meas_cd"][0], A2["meas_lm"][0])
    return {"geo": geo, "led_model": led_model, "sims": sims, "sim_src": sim_src, "kv": kv, "shape": shape,
            "sens": optic_sensitivity(shape), "sim_consts": fw_sim_constants(), "fk": fk, "a2": a2,
            "by_charge": turbo_by_charge(sims, fw_by_charge(folder), led_model)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cad_dir")
    ap.add_argument("out_dir")
    ap.add_argument("--fw-sim", default=None, help="folder with the simulator CSV files (default: run the simulation)")
    ap.add_argument("--cargo-target-dir", default=None, help="cargo build folder for the simulation run")
    ap.add_argument("--only", default=None, help="comma list of: output, beams, size, combined, md (default: all)")
    ap.add_argument("--draft", action="store_true")
    args = ap.parse_args()
    only = set(args.only.split(",")) if args.only else {"output", "beams", "size", "combined", "md"}
    os.makedirs(args.out_dir, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="compare_a2_")
    try:
        M = build_models(args, tmp)
        a2, kv, sh = M["a2"], M["kv"], M["shape"]
        for key, name in (("on", "switch-on"), ("30s", "30 s"), ("hot", "Tj 85 C")):
            v = kv[key]
            log("FlashKa %-9s %4d mA  Tj %5.1f C  factor %.3f  LED %6.1f lm  front %6.1f lm  %6.0f cd  %5.1f m" % (
                name, v["mA"], v["Tj"], v["f"], v["phi"], v["otf"], v["cd"], v["throw"]))
        log("FlashKa after 10 min %.1f lm, sustained %.1f lm (%.1f lm at Tj 85 C), optic sigma %.3f deg, spill %.1f %%"
            % (kv["10min"]["otf"], kv["sustained"]["otf"], kv["sustained"]["otf85"], sh["sigma_deg"],
               100 * sh["spill_share"]))
        log("A2: %.0f lm, peak %.0f cd, throw %.1f m, hotspot sigma %.2f deg (FWHM %.1f), I_h %.0f cd, I_s %.1f cd"
            % (a2.flux(), a2.peak, throw_m(a2.peak), a2.info["sigma_deg"], a2.info["fwhm_deg"], a2.info["I_h"],
               a2.info["I_s"]))
        rep = []
        log("checks")
        run_tests(M, rep)
        out_info = picture_output(M, args.out_dir)
        beams = picture_beams(M, args.cad_dir, args.out_dir, rep, draft=args.draft) if \
            ({"beams", "combined"} & only) else None
        SV = render_size_views(args.cad_dir, draft=args.draft) if ({"size", "combined"} & only) else None
        if "size" in only:
            picture_size(M, SV, args.out_dir)
        if "combined" in only:
            picture_combined(M, beams, SV, out_info, args.out_dir)
            picture_combined(M, beams, SV, out_info, args.out_dir, dark=True)
        if "md" in only:
            write_sources(M, SV["ci"] if SV else cad_info(args.cad_dir), out_info, rep, args)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
