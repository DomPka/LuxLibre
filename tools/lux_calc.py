#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""lux_calc - small calculator for choosing flashlight parts (LuxLibre).

Python 3.8+, standard library only. Every subcommand prints a short labelled result with
units and the formula it used; add --json for machine-readable output. All functions
below the CLI line are pure and importable (``import lux_calc``).

Resistances accept the suffixes k and M (``100k``, ``1M``, ``4.7k``).

Usage examples (one per subcommand):

    # BAT-6: largest standby current that drains 3 % of an 800 mAh cell per month
    python3 tools/lux_calc.py standby --capacity-mah 800
    # ... or check a measured standby current
    python3 tools/lux_calc.py standby --capacity-mah 800 --current-ua 12

    # REQ-2: runtime estimate at a constant LED power or LED current
    python3 tools/lux_calc.py runtime --capacity-mah 3000 --led-w 5
    python3 tools/lux_calc.py runtime --capacity-mah 3000 --led-a 1.5 --vf0 2.75 --rs 0.15

    # BAT-1: current drawn from the cell, with internal resistance
    python3 tools/lux_calc.py cellcurrent --led-a 3 --cell-v 3.6 --r-int 0.05 --cell-max-a 15

    # REQ-2: beam distance from intensity, from a lux reading, or an estimate from the optic
    python3 tools/lux_calc.py throw --cd 10000 --at-m 2
    python3 tools/lux_calc.py throw --lux 250 --distance-m 2
    python3 tools/lux_calc.py throw --lumens 560 --die-mm2 2.0 --optic-mm 20

    # THM-2 / THM-3: sustainable heat from the surface, turbo time from thermal mass
    python3 tools/lux_calc.py thermal --diameter-mm 25 --length-mm 90
    python3 tools/lux_calc.py thermal --diameter-mm 25 --length-mm 90 --mass-g 60 \\
        --material aluminium --input-w 10 --lumens 1000

    # DRV-5: PCB trace width (IPC-2221)
    python3 tools/lux_calc.py trace --current-a 3

    # BAT-9: battery-voltage divider check or suggestion
    python3 tools/lux_calc.py divider --v-max 4.2 --adc-ref 1.1 --r-top 750k --r-bottom 220k
    python3 tools/lux_calc.py divider --v-max 4.2 --adc-ref 1.1

    # THM-4: NTC thermistor (beta equation)
    python3 tools/lux_calc.py ntc --r25 100k --beta 4250 --temp-c 50 --r-fix 100k
    python3 tools/lux_calc.py ntc --r25 100k --beta 4250 --ohms 33.2k
    python3 tools/lux_calc.py ntc --r25 100k --beta 4250 --r-fix 100k --table

Numbers marked "LuxLibre default" are project choices, not standards. Check the datasheet
of every part and measure the finished light.
"""

import argparse
import json
import math
import sys

# ---------------------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------------------

HOURS_PER_MONTH = 730.0  # 8760 h per year / 12
KELVIN_OFFSET = 273.15
T25_K = 298.15  # 25 °C in kelvin, reference point of the NTC beta equation

# Still-air heat transfer coefficients in W/m²K (convection + radiation). Derived values:
# Incropera free-convection range 2-25 W/m²K plus radiation ~5-6 W/m²K at ~50 °C
# (electronics-cooling.com); see docs/design-rules.md THM-2.
H_FINISH = {"anodised": 11.0, "bare": 6.5}

# Specific heat in J/(g*K).
C_MATERIAL = {
    "aluminium": 0.90,
    "copper": 0.385,
    "brass": 0.38,
    "stainless": 0.50,
    "titanium": 0.52,
}

# Luminous efficacy of radiation of a white LED, lm per optical watt (approximation).
LER_WHITE_LM_PER_W = 320.0

# IPC-2221 trace constants.
IPC2221_K = {"external": 0.048, "internal": 0.024}
MIL_PER_OZ = 1.378  # copper thickness in mil per oz/ft²
MM_PER_MIL = 0.0254

E24 = (10, 11, 12, 13, 15, 16, 18, 20, 22, 24, 27, 30,
       33, 36, 39, 43, 47, 51, 56, 62, 68, 75, 82, 91)

BAT1_MAX_FRACTION = 0.70  # BAT-1: continuous cell current <= 70 % of the rated maximum
BAT6_MAX_PCT_MONTH = 3.0  # BAT-6: standby drain <= 3 % of capacity per month


# ---------------------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------------------

def _positive(name, value):
    if value is None or not value > 0:
        raise ValueError("{} must be greater than zero (got {})".format(name, value))
    return value


def _non_negative(name, value):
    if value is None or value < 0:
        raise ValueError("{} must not be negative (got {})".format(name, value))
    return value


def standby_max_current_ua(capacity_mah, percent_per_month=3.0):
    """Largest standby current that drains ``percent_per_month`` of the cell per month.

    capacity_mah: cell capacity in mAh. percent_per_month: allowed drain in % per month.
    Returns current in µA:  I = C * pct/100 / 730 h * 1000.
    """
    _positive("capacity", capacity_mah)
    _positive("percent per month", percent_per_month)
    return capacity_mah * percent_per_month / 100.0 / HOURS_PER_MONTH * 1000.0


def standby_drain(capacity_mah, current_ua):
    """Drain of a given standby current.

    capacity_mah: mAh. current_ua: standby current in µA.
    Returns dict: percent_per_month (% of capacity per month) and months_to_empty
    (months from full to empty, ``math.inf`` for zero current).
    """
    _positive("capacity", capacity_mah)
    _non_negative("standby current", current_ua)
    pct = current_ua / 1000.0 * HOURS_PER_MONTH / capacity_mah * 100.0
    months = math.inf if pct == 0 else 100.0 / pct
    return {"percent_per_month": pct, "months_to_empty": months}


def led_vf(led_a, vf0=2.75, rs=0.15):
    """LED forward voltage from a straight-line model: Vf = vf0 + rs * I (V, A, ohm)."""
    _non_negative("LED current", led_a)
    return vf0 + rs * led_a


def led_power_w(led_a, vf0=2.75, rs=0.15):
    """LED electrical power in W: P = Vf * I with Vf = vf0 + rs * I."""
    return led_vf(led_a, vf0, rs) * led_a


def runtime_hours(capacity_mah, led_w, cell_v=3.6, usable=0.9, driver_eff=0.9):
    """Runtime at a constant LED power.

    capacity_mah: mAh. led_w: power into the LED in W. cell_v: nominal cell voltage in V.
    usable: fraction of the capacity used (0..1). driver_eff: driver efficiency (0..1).
    Returns dict: p_led_w, p_in_w (W from the cell), hours, minutes.
        P_in = P_led / eff;  hours = C/1000 * cell_v * usable / P_in
    """
    _positive("capacity", capacity_mah)
    _positive("LED power", led_w)
    _positive("cell voltage", cell_v)
    _positive("usable fraction", usable)
    _positive("driver efficiency", driver_eff)
    if usable > 1 or driver_eff > 1:
        raise ValueError("usable fraction and driver efficiency must be <= 1")
    p_in = led_w / driver_eff
    hours = capacity_mah / 1000.0 * cell_v * usable / p_in
    return {"p_led_w": led_w, "p_in_w": p_in, "hours": hours, "minutes": hours * 60.0}


def cell_current(p_in_w, cell_v, r_int=0.05):
    """Current drawn from a cell with internal resistance for a given input power.

    p_in_w: power the driver takes in W. cell_v: open-circuit cell voltage in V.
    r_int: cell internal resistance in ohm (plus contacts, if known).
    Solves P_in = (V - I*R) * I and takes the smaller root.
    Returns dict: current_a, loaded_v (V at the cell under load), max_power_w (V²/4R).
    Raises ValueError if there is no real root (the cell cannot deliver that power).
    """
    _positive("input power", p_in_w)
    _positive("cell voltage", cell_v)
    _non_negative("internal resistance", r_int)
    if r_int == 0:
        current = p_in_w / cell_v
        max_power = math.inf
    else:
        max_power = cell_v * cell_v / (4.0 * r_int)
        disc = cell_v * cell_v - 4.0 * r_int * p_in_w
        if disc < 0:
            raise ValueError(
                "the cell cannot deliver {:.3g} W: with {:.3g} V and {:.3g} ohm the maximum "
                "is V^2/(4R) = {:.3g} W".format(p_in_w, cell_v, r_int, max_power))
        current = (cell_v - math.sqrt(disc)) / (2.0 * r_int)
    return {"current_a": current, "loaded_v": cell_v - current * r_int,
            "max_power_w": max_power}


def beam_distance_m(cd):
    """ANSI/PLATO FL 1 beam distance in m (distance to 0.25 lx): d = 2 * sqrt(cd)."""
    _non_negative("intensity", cd)
    return 2.0 * math.sqrt(cd)


def lux_at(cd, distance_m):
    """Illuminance in lx at a distance in m from a source of ``cd`` candela: E = cd / d²."""
    _non_negative("intensity", cd)
    _positive("distance", distance_m)
    return cd / (distance_m * distance_m)


def cd_from_lux(lux, distance_m):
    """Peak intensity in cd from a lux reading at a distance in m: cd = E * d²."""
    _non_negative("illuminance", lux)
    _positive("distance", distance_m)
    return lux * distance_m * distance_m


def throw_estimate(lumens, die_mm2, optic_mm, optic_eff=0.7):
    """Upper-bound peak intensity for a reflector or TIR optic filled by the source.

    lumens: LED flux in lm. die_mm2: emitting area in mm². optic_mm: optic exit diameter
    in mm. optic_eff: optic efficiency (0..1).
    Returns dict: luminance_cd_m2 (L = F / (pi * A), Lambertian), cd
    (= eff * L * pi * (D/2)²), beam_m. Areas are converted to m².
    """
    _positive("lumens", lumens)
    _positive("die area", die_mm2)
    _positive("optic diameter", optic_mm)
    _positive("optic efficiency", optic_eff)
    if optic_eff > 1:
        raise ValueError("optic efficiency must be <= 1")
    area_m2 = die_mm2 * 1e-6
    radius_m = optic_mm * 1e-3 / 2.0
    luminance = lumens / (math.pi * area_m2)
    cd = optic_eff * luminance * math.pi * radius_m * radius_m
    return {"luminance_cd_m2": luminance, "cd": cd, "beam_m": beam_distance_m(cd)}


def cylinder_area_cm2(diameter_mm, length_mm):
    """Outer area of a closed cylinder in cm²: side pi*d*L plus two ends 2*pi*(d/2)²."""
    _positive("diameter", diameter_mm)
    _positive("length", length_mm)
    side = math.pi * diameter_mm * length_mm
    ends = 2.0 * math.pi * (diameter_mm / 2.0) ** 2
    return (side + ends) / 100.0


def sustainable_heat_w(area_cm2, h, ambient_c=25.0, surface_max_c=48.0):
    """Heat a surface can shed at steady state: P = h * A * (Tmax - Tamb).

    area_cm2: outer area in cm². h: heat transfer coefficient in W/m²K.
    ambient_c, surface_max_c: temperatures in °C. Returns W.
    """
    _positive("area", area_cm2)
    _positive("h", h)
    if surface_max_c <= ambient_c:
        raise ValueError("surface limit must be above the ambient temperature")
    return h * area_cm2 * 1e-4 * (surface_max_c - ambient_c)


def heat_from_light(input_w, lumens):
    """Approximate heat in W: electrical input minus optical power, heat = W - F/320.

    input_w: electrical power into the LED in W. lumens: emitted flux in lm.
    320 lm per optical watt is an approximation for white LEDs.
    """
    _positive("input power", input_w)
    _non_negative("lumens", lumens)
    heat = input_w - lumens / LER_WHITE_LM_PER_W
    if heat < 0:
        raise ValueError("lumens / 320 is larger than the input power; check the inputs")
    return heat


def turbo_time(area_cm2, h, mass_g, c_j_gk, heat_w, ambient_c=25.0, surface_max_c=48.0):
    """Lumped thermal model: time for the body to reach the surface limit at a given heat.

    area_cm2: outer area in cm². h: W/m²K. mass_g: mass in g. c_j_gk: specific heat in
    J/(g*K). heat_w: heat in W. Temperatures in °C; the body starts at ambient.
        R = 1/(h*A) [K/W], C = m*c [J/K], tau = R*C [s], steady rise = Q*R [K]
        t = -tau * ln(1 - (Tmax - Tamb) / (Q*R))   if Q*R > Tmax - Tamb, else never
    Returns dict: r_k_w, c_j_k, tau_s, steady_rise_k, steady_c, time_s (None = never).
    """
    _positive("area", area_cm2)
    _positive("h", h)
    _positive("mass", mass_g)
    _positive("specific heat", c_j_gk)
    _positive("heat", heat_w)
    if surface_max_c <= ambient_c:
        raise ValueError("surface limit must be above the ambient temperature")
    r = 1.0 / (h * area_cm2 * 1e-4)
    c = mass_g * c_j_gk
    tau = r * c
    rise = heat_w * r
    limit = surface_max_c - ambient_c
    time_s = -tau * math.log(1.0 - limit / rise) if rise > limit else None
    return {"r_k_w": r, "c_j_k": c, "tau_s": tau, "steady_rise_k": rise,
            "steady_c": ambient_c + rise, "time_s": time_s}


def trace_width(current_a, oz=1.0, rise_c=10.0, layer="external"):
    """IPC-2221 trace width.

    current_a: A. oz: copper weight in oz/ft². rise_c: allowed temperature rise in °C.
    layer: "external" or "internal".
        area_mil2 = (I / (k * dT^0.44))^(1/0.725), k = 0.048 external, 0.024 internal
        thickness_mil = 1.378 * oz;  width = area / thickness
    Returns dict: area_mil2, thickness_mil, width_mil, width_mm.
    """
    _positive("current", current_a)
    _positive("copper weight", oz)
    _positive("temperature rise", rise_c)
    if layer not in IPC2221_K:
        raise ValueError("layer must be 'external' or 'internal'")
    k = IPC2221_K[layer]
    area = (current_a / (k * rise_c ** 0.44)) ** (1.0 / 0.725)
    thickness = MIL_PER_OZ * oz
    width = area / thickness
    return {"area_mil2": area, "thickness_mil": thickness, "width_mil": width,
            "width_mm": width * MM_PER_MIL}


def divider_check(v_max, adc_ref, r_top, r_bottom, tolerance_pct=1.0):
    """Check a battery-voltage divider (r_top from battery to ADC pin, r_bottom to ground).

    v_max: highest battery voltage in V. adc_ref: ADC reference in V. r_top, r_bottom: ohm.
    tolerance_pct: resistor tolerance in %.
    Returns dict: ratio (Rb/(Rt+Rb)), v_adc (V at the pin at v_max), fits (v_adc <= Vref),
    headroom_pct (100 * (1 - v_adc/Vref)), current_ua (at v_max), ratio_error_pct
    (worst case with both resistors at opposite tolerance limits).
    """
    _positive("v-max", v_max)
    _positive("ADC reference", adc_ref)
    _positive("r-top", r_top)
    _positive("r-bottom", r_bottom)
    _non_negative("tolerance", tolerance_pct)
    t = tolerance_pct / 100.0
    ratio = r_bottom / (r_top + r_bottom)
    v_adc = v_max * ratio
    hi = r_bottom * (1 + t) / (r_top * (1 - t) + r_bottom * (1 + t))
    lo = r_bottom * (1 - t) / (r_top * (1 + t) + r_bottom * (1 - t))
    err = max(hi / ratio - 1.0, 1.0 - lo / ratio) * 100.0
    return {"ratio": ratio, "v_adc": v_adc, "fits": v_adc <= adc_ref,
            "headroom_pct": (1.0 - v_adc / adc_ref) * 100.0,
            "current_ua": v_max / (r_top + r_bottom) * 1e6, "ratio_error_pct": err}


def _e24_values(lo_ohm, hi_ohm):
    values = []
    decade = 1.0
    while decade * 10 <= hi_ohm * 10:
        for base in E24:
            v = round(base * decade / 10.0, 6)
            if lo_ohm <= v <= hi_ohm:
                values.append(v)
        decade *= 10.0
    return sorted(set(values))


def divider_suggest(v_max, adc_ref, headroom=0.10, total_ohm=1e6, window=1.25):
    """Suggest E24 r_top / r_bottom so the pin sees at most (1 - headroom) * Vref at v_max.

    v_max, adc_ref: V. headroom: fraction below the reference (0.10 = 10 %).
    total_ohm: target total resistance in ohm; the pair must lie within total/window ..
    total*window. Among those pairs the one with the ratio closest to (but not above) the
    target is chosen. Returns dict: r_top, r_bottom, target_ratio, or None for both
    resistors if v_max is already below the target (no divider needed).
    """
    _positive("v-max", v_max)
    _positive("ADC reference", adc_ref)
    target = (1.0 - headroom) * adc_ref / v_max
    if target >= 1.0:
        return {"r_top": None, "r_bottom": None, "target_ratio": target}
    lo, hi = total_ohm / window, total_ohm * window
    values = _e24_values(1.0, hi)
    best = None
    for rb in values:
        for rt in values:
            total = rt + rb
            if not lo <= total <= hi:
                continue
            ratio = rb / total
            if ratio > target:
                continue
            key = (target - ratio, abs(math.log(total / total_ohm)))
            if best is None or key < best[0]:
                best = (key, rt, rb)
    if best is None:
        raise ValueError("no E24 pair found near {:.3g} ohm".format(total_ohm))
    return {"r_top": best[1], "r_bottom": best[2], "target_ratio": target}


def ntc_resistance(temp_c, r25, beta):
    """NTC resistance in ohm at temp_c (°C) from the beta equation.

    1/T = 1/298.15 + ln(R/R25)/B  (T in K)  ->  R = R25 * exp(B * (1/T - 1/298.15)).
    """
    _positive("R25", r25)
    _positive("beta", beta)
    t_k = temp_c + KELVIN_OFFSET
    _positive("absolute temperature", t_k)
    return r25 * math.exp(beta * (1.0 / t_k - 1.0 / T25_K))


def ntc_temperature(ohms, r25, beta):
    """Temperature in °C of an NTC with resistance ``ohms``: 1/T = 1/298.15 + ln(R/R25)/B."""
    _positive("resistance", ohms)
    _positive("R25", r25)
    _positive("beta", beta)
    inv_t = 1.0 / T25_K + math.log(ohms / r25) / beta
    _positive("1/T", inv_t)
    return 1.0 / inv_t - KELVIN_OFFSET


def ntc_adc(temp_c, r25, beta, r_fix, adc_bits=12):
    """ADC reading for an NTC from the pin to ground with r_fix from the reference to the pin.

    Returns dict: ohms, ratio r = Rntc/(Rfix+Rntc), code_exact (r * 2^bits), code (rounded,
    limited to 2^bits - 1), c_per_lsb (°C per ADC step at temp_c, central difference).
    """
    _positive("r-fix", r_fix)
    if int(adc_bits) != adc_bits or not 1 <= adc_bits <= 24:
        raise ValueError("ADC bits must be a whole number from 1 to 24")
    full = 2 ** int(adc_bits)

    def code_at(t):
        rn = ntc_resistance(t, r25, beta)
        return rn / (r_fix + rn) * full

    ohms = ntc_resistance(temp_c, r25, beta)
    ratio = ohms / (r_fix + ohms)
    step = 0.01
    slope = (code_at(temp_c + step) - code_at(temp_c - step)) / (2.0 * step)  # LSB per °C
    c_per_lsb = math.inf if slope == 0 else 1.0 / abs(slope)
    exact = ratio * full
    return {"ohms": ohms, "ratio": ratio, "code_exact": exact,
            "code": min(int(round(exact)), full - 1), "c_per_lsb": c_per_lsb}


def ntc_table(r25, beta, r_fix=None, adc_bits=12, start_c=-20, stop_c=100, step_c=10):
    """Rows for temperatures start_c..stop_c (°C): ohms, and ADC values if r_fix is given."""
    rows = []
    t = start_c
    while t <= stop_c:
        row = {"temp_c": t, "ohms": ntc_resistance(t, r25, beta)}
        if r_fix is not None:
            adc = ntc_adc(t, r25, beta, r_fix, adc_bits)
            row.update({"ratio": adc["ratio"], "code": adc["code"],
                        "c_per_lsb": adc["c_per_lsb"]})
        rows.append(row)
        t += step_c
    return rows


# ---------------------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------------------

def fmt(x, sig=3):
    """Format a number with ``sig`` significant figures, without exponent notation."""
    if x is None:
        return "-"
    if isinstance(x, float) and math.isinf(x):
        return "infinite"
    if x == 0:
        return "0"
    d = int(math.floor(math.log10(abs(x))))
    decimals = max(sig - 1 - d, 0)
    value = round(x, sig - 1 - d)
    return "{:.{}f}".format(value, decimals)


def fin(x):
    """Echo an input value as the user gave it (shortest form, no padding zeros)."""
    return "{:g}".format(x)


def fmt_ohms(r, sig=3, echo=False):
    """Format a resistance with an ohm, kOhm or MOhm unit (echo=True: as given)."""
    if r is None:
        return "-"
    f = fin if echo else (lambda x: fmt(x, sig))
    if r >= 1e6:
        return f(r / 1e6) + " MΩ"
    if r >= 1e3:
        return f(r / 1e3) + " kΩ"
    return f(r) + " Ω"


def parse_ohms(text):
    """Parse a resistance such as '100k', '4.7k', '1M', '220' or '1e6' into ohm."""
    s = str(text).strip().replace("Ω", "").replace("ohm", "")
    mult = 1.0
    if s and s[-1] in "kK":
        mult, s = 1e3, s[:-1]
    elif s and s[-1] == "M":
        mult, s = 1e6, s[:-1]
    try:
        value = float(s) * mult
    except ValueError:
        raise argparse.ArgumentTypeError("not a resistance: {!r}".format(text))
    return value


class Report(object):
    """Result of one subcommand: title, labelled rows, one-line formula, notes, data."""

    def __init__(self, command, title):
        self.command = command
        self.title = title
        self.rows = []
        self.formula = ""
        self.notes = []
        self.data = {}

    def row(self, label, value, unit=""):
        self.rows.append((label, value + (" " + unit if unit else "")))

    def text(self):
        lines = [self.title]
        width = max([len(label) for label, _ in self.rows] + [0])
        for label, value in self.rows:
            lines.append("  {:<{}}  {}".format(label, width, value))
        if self.formula:
            lines.append("  formula: " + self.formula)
        for note in self.notes:
            lines.append("  note: " + note)
        return "\n".join(lines)

    def as_json(self):
        def clean(v):
            if isinstance(v, float) and (math.isinf(v) or math.isnan(v)):
                return None
            if isinstance(v, dict):
                return {k: clean(x) for k, x in v.items()}
            if isinstance(v, list):
                return [clean(x) for x in v]
            return v
        out = {"command": self.command}
        out.update(clean(self.data))
        out["formula"] = self.formula
        out["notes"] = self.notes
        return json.dumps(out, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------------------
# CLI layer
# ---------------------------------------------------------------------------------------

def _led_power_from_args(args, rep):
    """Fill LED rows and return the LED power in W from --led-w or --led-a/--vf0/--rs."""
    if args.led_w is not None:
        rep.row("LED power", fin(args.led_w), "W")
        rep.data["p_led_w"] = args.led_w
        return args.led_w
    vf = led_vf(args.led_a, args.vf0, args.rs)
    p = vf * args.led_a
    rep.row("LED current", fin(args.led_a), "A")
    rep.row("LED Vf (vf0 + rs*I)", fmt(vf), "V")
    rep.row("LED power", fmt(p), "W")
    rep.data.update({"led_a": args.led_a, "led_vf": vf, "p_led_w": p})
    return p


def cmd_standby(args):
    rep = Report("standby", "Standby drain (BAT-6)")
    rep.row("capacity", fin(args.capacity_mah), "mAh")
    rep.data["capacity_mah"] = args.capacity_mah
    if args.current_ua is None:
        i_max = standby_max_current_ua(args.capacity_mah, args.percent_per_month)
        rep.row("allowed drain", fin(args.percent_per_month), "% per month")
        rep.row("max standby current", fmt(i_max), "µA")
        rep.formula = "I_max = C * pct/100 / 730 h * 1000  [µA]"
        rep.data.update({"percent_per_month": args.percent_per_month,
                         "max_current_ua": i_max})
    else:
        d = standby_drain(args.capacity_mah, args.current_ua)
        ok = d["percent_per_month"] <= BAT6_MAX_PCT_MONTH
        rep.row("standby current", fin(args.current_ua), "µA")
        rep.row("drain", fmt(d["percent_per_month"]), "% per month")
        rep.row("full to empty", fmt(d["months_to_empty"]), "months")
        rep.row("BAT-6 (<= 3 %/month)", "pass" if ok else "fail")
        rep.formula = "pct = I/1000 * 730 h / C * 100;  months = 100 / pct"
        rep.data.update({"current_ua": args.current_ua, "bat6_ok": ok})
        rep.data.update(d)
    rep.notes.append("730 h = one average month. Measure the real standby current.")
    return rep


def cmd_runtime(args):
    rep = Report("runtime", "Runtime estimate at constant power (REQ-2)")
    p_led = _led_power_from_args(args, rep)
    r = runtime_hours(args.capacity_mah, p_led, args.cell_v, args.usable, args.driver_eff)
    rep.row("driver efficiency", fin(args.driver_eff * 100), "%")
    rep.row("input power", fmt(r["p_in_w"]), "W")
    rep.row("energy used", fmt(args.capacity_mah / 1000 * args.cell_v * args.usable),
            "Wh ({} mAh x {} V x {})".format(fin(args.capacity_mah), fin(args.cell_v),
                                             fin(args.usable)))
    rep.row("runtime", fmt(r["hours"]), "h ({} min)".format(fmt(r["minutes"])))
    rep.formula = "P_in = P_led / eff;  t = C/1000 * cell_v * usable / P_in  [h]"
    rep.notes.append("Constant-power estimate. FL 1 runtime (to 10 % of the 30 s output) "
                     "must be measured.")
    rep.data.update({"capacity_mah": args.capacity_mah, "cell_v": args.cell_v,
                     "usable": args.usable, "driver_eff": args.driver_eff})
    rep.data.update(r)
    return rep


def cmd_cellcurrent(args):
    rep = Report("cellcurrent", "Cell current (BAT-1)")
    p_led = _led_power_from_args(args, rep)
    p_in = p_led / args.driver_eff
    rep.row("input power", fmt(p_in), "W (eff {} %)".format(fin(args.driver_eff * 100)))
    rep.data.update({"p_in_w": p_in, "cell_v": args.cell_v, "r_int": args.r_int})
    rep.formula = "P_in = (V - I*R) * I, smaller root I = (V - sqrt(V^2 - 4*R*P_in)) / (2*R)"
    try:
        c = cell_current(p_in, args.cell_v, args.r_int)
    except ValueError as exc:
        rep.row("result", "the cell cannot deliver this power")
        rep.notes.append(str(exc))
        rep.data.update({"current_a": None, "deliverable": False})
        return rep
    rep.row("cell current", fmt(c["current_a"]), "A")
    rep.row("cell voltage under load", fmt(c["loaded_v"]), "V")
    rep.data.update(c)
    rep.data["deliverable"] = True
    if args.cell_max_a is not None:
        pct = c["current_a"] / args.cell_max_a * 100.0
        ok = pct <= BAT1_MAX_FRACTION * 100.0
        rep.row("share of cell rating", fmt(pct), "% of {} A".format(fin(args.cell_max_a)))
        rep.row("BAT-1 (<= 70 %)", "pass" if ok else "fail")
        rep.data.update({"cell_max_a": args.cell_max_a, "rating_pct": pct, "bat1_ok": ok})
    rep.notes.append("Add contact and spring resistance to --r-int if known.")
    return rep


def cmd_throw(args):
    modes = [args.cd is not None, args.lux is not None, args.lumens is not None]
    if sum(modes) != 1:
        raise ValueError("give exactly one of --cd, --lux (with --distance-m) or "
                         "--lumens (with --die-mm2 and --optic-mm)")
    rep = Report("throw", "Throw (REQ-2, ANSI/PLATO FL 1)")
    if args.cd is not None:
        beam = beam_distance_m(args.cd)
        e = lux_at(args.cd, args.at_m)
        rep.row("peak intensity", fin(args.cd), "cd")
        rep.row("beam distance (0.25 lx)", fmt(beam), "m")
        rep.row("illuminance at {} m".format(fin(args.at_m)), fmt(e), "lx")
        rep.formula = "d = 2 * sqrt(cd)  [m];  E = cd / d^2  [lx]"
        rep.data.update({"cd": args.cd, "beam_m": beam, "at_m": args.at_m, "lux": e})
    elif args.lux is not None:
        if args.distance_m is None:
            raise ValueError("--lux needs --distance-m")
        cd = cd_from_lux(args.lux, args.distance_m)
        beam = beam_distance_m(cd)
        rep.row("reading", "{} lx at {} m".format(fin(args.lux), fin(args.distance_m)))
        rep.row("peak intensity", fmt(cd), "cd")
        rep.row("beam distance (0.25 lx)", fmt(beam), "m")
        rep.formula = "cd = E * d^2;  beam = 2 * sqrt(cd)  [m]"
        rep.data.update({"lux": args.lux, "distance_m": args.distance_m, "cd": cd,
                         "beam_m": beam})
    else:
        if args.die_mm2 is None or args.optic_mm is None:
            raise ValueError("--lumens needs --die-mm2 and --optic-mm")
        t = throw_estimate(args.lumens, args.die_mm2, args.optic_mm, args.optic_eff)
        rep.row("source luminance", fmt(t["luminance_cd_m2"] / 1e6), "Mcd/m²")
        rep.row("peak intensity (upper bound)", fmt(t["cd"]), "cd")
        rep.row("beam distance (upper bound)", fmt(t["beam_m"]), "m")
        rep.formula = ("L = F / (pi * A_die);  cd = eff * L * pi * (D/2)^2;  "
                       "beam = 2 * sqrt(cd)")
        rep.notes.append("Upper-bound estimate for a reflector or TIR filled by the source. "
                         "Rule of thumb (not a standard): real lights reach roughly 50-80 % "
                         "of it. Measure lux at a known distance.")
        rep.data.update({"lumens": args.lumens, "die_mm2": args.die_mm2,
                         "optic_mm": args.optic_mm, "optic_eff": args.optic_eff})
        rep.data.update(t)
    return rep


def cmd_thermal(args):
    rep = Report("thermal", "Thermal (THM-2, THM-3)")
    have_surface = args.area_cm2 is not None or args.diameter_mm is not None
    helper = args.input_w is not None or args.lumens is not None
    if not have_surface and not helper:
        raise ValueError("give --area-cm2 or --diameter-mm/--length-mm (or --input-w with "
                         "--lumens for the heat helper)")
    formulas = []
    heat = args.heat_w
    if helper:
        if args.input_w is None or args.lumens is None:
            raise ValueError("the heat helper needs both --input-w and --lumens")
        derived = heat_from_light(args.input_w, args.lumens)
        rep.row("heat from {} W and {} lm".format(fin(args.input_w), fin(args.lumens)),
                fmt(derived), "W")
        formulas.append("heat = W - F/320")
        rep.notes.append("320 lm per optical watt is an approximation for white LEDs.")
        rep.data.update({"input_w": args.input_w, "lumens": args.lumens,
                         "heat_from_light_w": derived})
        if heat is None:
            heat = derived
    if not have_surface:
        rep.formula = "; ".join(formulas)
        return rep

    if args.area_cm2 is not None:
        if args.diameter_mm is not None or args.length_mm is not None:
            raise ValueError("give either --area-cm2 or --diameter-mm/--length-mm")
        area = _positive("area", args.area_cm2)
        rep.row("surface area", fmt(area), "cm²")
    else:
        if args.length_mm is None:
            raise ValueError("--diameter-mm needs --length-mm")
        area = cylinder_area_cm2(args.diameter_mm, args.length_mm)
        rep.row("surface area (cylinder)", fmt(area),
                "cm² ({} x {} mm)".format(fin(args.diameter_mm), fin(args.length_mm)))
    if args.h is not None:
        h, finish = args.h, "custom"
    elif args.finish == "custom":
        raise ValueError("--finish custom needs --h")
    else:
        h, finish = H_FINISH[args.finish], args.finish
    p = sustainable_heat_w(area, h, args.ambient, args.surface_max)
    rep.row("h ({})".format(finish), fin(h), "W/m²K")
    rep.row("ambient / surface limit",
            "{} / {} °C".format(fin(args.ambient), fin(args.surface_max)))
    rep.row("sustainable heat", fmt(p), "W")
    formulas.append("P = h * A * (Tmax - Tamb)")
    rep.data.update({"area_cm2": area, "h": h, "finish": finish, "ambient_c": args.ambient,
                     "surface_max_c": args.surface_max, "sustainable_w": p})
    if finish != "custom":
        rep.notes.append("h for still air (convection + radiation), derived values; "
                         "see THM-2. Verify with the THM-6 test.")

    timing = args.mass_g is not None or args.heat_w is not None
    if timing:
        if args.mass_g is None or heat is None:
            raise ValueError("turbo timing needs --mass-g and --heat-w "
                             "(or --input-w with --lumens)")
        if args.c is not None:
            c, material = args.c, "custom"
        elif args.material == "custom":
            raise ValueError("--material custom needs --c")
        else:
            c, material = C_MATERIAL[args.material], args.material
        t = turbo_time(area, h, args.mass_g, c, heat, args.ambient, args.surface_max)
        rep.row("mass / c ({})".format(material),
                "{} g / {} J/gK".format(fin(args.mass_g), fin(c)))
        rep.row("heat in turbo", fmt(heat), "W")
        rep.row("R, C, tau", "{} K/W, {} J/K, {} s".format(
            fmt(t["r_k_w"]), fmt(t["c_j_k"]), fmt(t["tau_s"])))
        rep.row("steady-state surface", fmt(t["steady_c"]), "°C")
        if t["time_s"] is None:
            rep.row("time to surface limit", "never (steady state below the limit)")
        else:
            rep.row("time to surface limit", fmt(t["time_s"]),
                    "s ({} min)".format(fmt(t["time_s"] / 60.0)))
        formulas.append("R = 1/(h*A), C = m*c, t = -R*C * ln(1 - (Tmax-Tamb)/(Q*R))")
        rep.notes.append("Lumped model: the whole body at one temperature, starting at "
                         "ambient. The LED and driver get hotter than the surface.")
        rep.data.update({"mass_g": args.mass_g, "c_j_gk": c, "material": material,
                         "heat_w": heat})
        rep.data.update(t)
    rep.formula = ";  ".join(formulas)
    return rep


def cmd_trace(args):
    rep = Report("trace", "PCB trace width, IPC-2221 (DRV-5)")
    t = trace_width(args.current_a, args.oz, args.rise_c, args.layer)
    rep.row("current", fin(args.current_a), "A")
    rep.row("copper / layer", "{} oz, {}".format(fin(args.oz), args.layer))
    rep.row("temperature rise", fin(args.rise_c), "°C")
    rep.row("cross-section", fmt(t["area_mil2"]), "mil²")
    rep.row("thickness", fmt(t["thickness_mil"]), "mil")
    rep.row("width", "{} mil = {} mm".format(fmt(t["width_mil"]), fmt(t["width_mm"])))
    rep.formula = ("A = (I / (k * dT^0.44))^(1/0.725) mil², k = {} ({}); "
                   "w = A / (1.378 * oz)".format(IPC2221_K[args.layer], args.layer))
    rep.notes.append("IPC-2152 is the newer method; IPC-2221 is conservative for outer "
                     "layers.")
    rep.data.update({"current_a": args.current_a, "oz": args.oz, "rise_c": args.rise_c,
                     "layer": args.layer})
    rep.data.update(t)
    return rep


def cmd_divider(args):
    rep = Report("divider", "Battery voltage divider (BAT-9)")
    given = [args.r_top is not None, args.r_bottom is not None]
    if any(given) and not all(given):
        raise ValueError("give both --r-top and --r-bottom, or neither for a suggestion")
    rep.data.update({"v_max": args.v_max, "adc_ref": args.adc_ref,
                     "tolerance_pct": args.tolerance_pct})
    rt, rb = args.r_top, args.r_bottom
    if rt is None:
        s = divider_suggest(args.v_max, args.adc_ref)
        rep.data.update({"suggested": True, "target_ratio": s["target_ratio"]})
        if s["r_top"] is None:
            rep.row("v-max / ADC reference",
                    "{} V / {} V".format(fin(args.v_max), fin(args.adc_ref)))
            rep.row("suggestion", "no divider needed (v-max is 10 % or more below the "
                                  "reference)")
            rep.formula = "target ratio = 0.9 * Vref / v_max"
            return rep
        rt, rb = s["r_top"], s["r_bottom"]
        rep.row("target ratio (10 % headroom)", fmt(s["target_ratio"], 4))
        rep.row("suggested r-top (E24)", fmt_ohms(rt, echo=True))
        rep.row("suggested r-bottom (E24)", fmt_ohms(rb, echo=True))
        rep.notes.append("Advice: a high-value divider needs a capacitor at the ADC pin "
                         "(e.g. 100 nF) so the ADC sample-and-hold sees a low source "
                         "impedance.")
    else:
        rep.data["suggested"] = False
        rep.row("r-top / r-bottom", "{} / {}".format(fmt_ohms(rt, echo=True), fmt_ohms(rb, echo=True)))
    d = divider_check(args.v_max, args.adc_ref, rt, rb, args.tolerance_pct)
    rep.row("ratio", fmt(d["ratio"], 4))
    rep.row("ADC pin at {} V".format(fin(args.v_max)),
            "{} V (reference {} V)".format(fmt(d["v_adc"], 4), fin(args.adc_ref)))
    rep.row("fits under reference", "yes, {} % headroom".format(fmt(d["headroom_pct"]))
            if d["fits"] else "NO, over the reference")
    rep.row("divider current", fmt(d["current_ua"]), "µA at v-max")
    rep.row("worst-case ratio error", fmt(d["ratio_error_pct"]),
            "% ({} % resistors)".format(fin(args.tolerance_pct)))
    rep.formula = ("ratio = Rb/(Rt+Rb);  V_adc = v_max * ratio;  I = v_max/(Rt+Rb);  "
                   "error with Rt, Rb at opposite tolerance limits")
    rep.notes.append("BAT-9 asks for <= 1 % error after calibration with BAT_CAL.")
    rep.data.update({"r_top": rt, "r_bottom": rb})
    rep.data.update(d)
    return rep


def cmd_ntc(args):
    modes = [args.temp_c is not None, args.ohms is not None, args.table]
    if sum(modes) != 1:
        raise ValueError("give exactly one of --temp-c, --ohms or --table")
    rep = Report("ntc", "NTC thermistor, beta equation (THM-4)")
    rep.row("R25 / beta", "{} / {} K".format(fmt_ohms(args.r25, echo=True), fin(args.beta)))
    rep.data.update({"r25": args.r25, "beta": args.beta})
    beta_f = "1/T = 1/298.15 + ln(R/R25)/B  (T in K)"
    adc_f = "r = Rntc/(Rfix+Rntc), code = r * 2^bits"
    if args.r_fix is not None:
        rep.row("r-fix (reference to pin) / ADC",
                "{} / {} bit".format(fmt_ohms(args.r_fix, echo=True), args.adc_bits))
        rep.data.update({"r_fix": args.r_fix, "adc_bits": args.adc_bits})
    if args.ohms is not None:
        t = ntc_temperature(args.ohms, args.r25, args.beta)
        rep.row("resistance", fmt_ohms(args.ohms, echo=True))
        rep.row("temperature", fmt(t), "°C")
        rep.formula = beta_f
        rep.data.update({"ohms": args.ohms, "temp_c": t})
    elif args.temp_c is not None:
        r = ntc_resistance(args.temp_c, args.r25, args.beta)
        rep.row("temperature", fin(args.temp_c), "°C")
        rep.row("NTC resistance", fmt_ohms(r))
        rep.data.update({"temp_c": args.temp_c, "ohms": r})
        rep.formula = beta_f
        if args.r_fix is not None:
            a = ntc_adc(args.temp_c, args.r25, args.beta, args.r_fix, args.adc_bits)
            rep.row("ADC ratio", fmt(a["ratio"], 4))
            rep.row("ADC code", "{} of {}".format(a["code"], 2 ** args.adc_bits))
            rep.row("sensitivity", fmt(a["c_per_lsb"]), "°C per LSB")
            rep.formula = beta_f + ";  " + adc_f
            rep.data.update(a)
    else:
        rows = ntc_table(args.r25, args.beta, args.r_fix, args.adc_bits)
        rep.formula = beta_f + (";  " + adc_f if args.r_fix is not None else "")
        rep.data["table"] = rows
        header = "  {:>6}  {:>10}".format("°C", "R")
        if args.r_fix is not None:
            header += "  {:>7}  {:>6}  {:>9}".format("ratio", "code", "°C/LSB")
        lines = [header]
        for row in rows:
            line = "  {:>6}  {:>10}".format(row["temp_c"], fmt_ohms(row["ohms"]))
            if args.r_fix is not None:
                line += "  {:>7}  {:>6}  {:>9}".format(
                    fmt(row["ratio"], 4), row["code"], fmt(row["c_per_lsb"]))
            lines.append(line)
        rep.table_lines = lines
    rep.notes.append("Calibrate THM_OFFSET and the sensor-to-surface difference (THM-4).")
    return rep


def build_parser():
    """Build the argparse parser with one subparser per calculation."""
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                        help="print the result as JSON")

    p = argparse.ArgumentParser(
        prog="lux_calc.py",
        description="Flashlight part-selection calculator (LuxLibre). "
                    "Use '<subcommand> -h' for the options of each calculation.")
    p.add_argument("--json", action="store_true", help="print the result as JSON")
    sub = p.add_subparsers(dest="command", metavar="subcommand")
    sub.required = True

    def add(name, help_text, func):
        sp = sub.add_parser(name, parents=[common], help=help_text, description=help_text)
        sp.set_defaults(func=func)
        return sp

    def led_args(sp):
        g = sp.add_mutually_exclusive_group(required=True)
        g.add_argument("--led-w", type=float, help="power into the LED, W")
        g.add_argument("--led-a", type=float, help="LED current, A (uses --vf0 and --rs)")
        sp.add_argument("--vf0", type=float, default=2.75,
                        help="LED Vf line intercept, V (LuxLibre default 2.75; fit the "
                             "datasheet curve)")
        sp.add_argument("--rs", type=float, default=0.15,
                        help="LED Vf line slope, ohm (LuxLibre default 0.15)")
        sp.add_argument("--driver-eff", type=float, default=0.9,
                        help="driver efficiency 0..1 (LuxLibre default 0.9)")

    sp = add("standby", "standby current limit or drain (BAT-6)", cmd_standby)
    sp.add_argument("--capacity-mah", type=float, required=True, help="cell capacity, mAh")
    sp.add_argument("--percent-per-month", type=float, default=3.0,
                    help="allowed drain, %% per month (BAT-6: 3)")
    sp.add_argument("--current-ua", type=float,
                    help="measured standby current, µA (gives %% per month instead)")

    sp = add("runtime", "runtime at constant LED power or current (REQ-2)", cmd_runtime)
    sp.add_argument("--capacity-mah", type=float, required=True, help="cell capacity, mAh")
    sp.add_argument("--cell-v", type=float, default=3.6,
                    help="nominal cell voltage, V (default 3.6, Li-ion nominal)")
    sp.add_argument("--usable", type=float, default=0.9,
                    help="usable fraction of capacity 0..1 (LuxLibre default 0.9)")
    led_args(sp)

    sp = add("cellcurrent", "current from the cell with internal resistance (BAT-1)",
             cmd_cellcurrent)
    led_args(sp)
    sp.add_argument("--cell-v", type=float, required=True, help="cell voltage, V")
    sp.add_argument("--r-int", type=float, default=0.05,
                    help="cell internal resistance, ohm (LuxLibre default 0.05; check "
                         "the datasheet)")
    sp.add_argument("--cell-max-a", type=float,
                    help="cell rated maximum continuous current, A (datasheet)")

    sp = add("throw", "intensity, beam distance and lux (REQ-2)", cmd_throw)
    sp.add_argument("--cd", type=float, help="peak intensity, cd")
    sp.add_argument("--at-m", type=float, default=1.0,
                    help="distance for the lux value, m (default 1)")
    sp.add_argument("--lux", type=float, help="measured illuminance, lx")
    sp.add_argument("--distance-m", type=float, help="distance of the lux reading, m")
    sp.add_argument("--lumens", type=float, help="LED flux, lm (estimate mode)")
    sp.add_argument("--die-mm2", type=float, help="LED emitting area, mm²")
    sp.add_argument("--optic-mm", type=float, help="reflector/TIR exit diameter, mm")
    sp.add_argument("--optic-eff", type=float, default=0.7,
                    help="optic efficiency 0..1 (LuxLibre default 0.7)")

    sp = add("thermal", "sustainable heat and turbo time (THM-2, THM-3)", cmd_thermal)
    sp.add_argument("--area-cm2", type=float, help="outer surface area, cm²")
    sp.add_argument("--diameter-mm", type=float, help="body diameter, mm (cylinder)")
    sp.add_argument("--length-mm", type=float, help="body length, mm (cylinder)")
    sp.add_argument("--finish", choices=["anodised", "bare", "custom"], default="anodised",
                    help="surface finish: h = 11.0 anodised, 6.5 bare W/m²K (still air)")
    sp.add_argument("--h", type=float, help="custom heat transfer coefficient, W/m²K")
    sp.add_argument("--ambient", type=float, default=25.0, help="ambient, °C (default 25)")
    sp.add_argument("--surface-max", type=float, default=48.0,
                    help="surface limit, °C (default 48, THM-1)")
    sp.add_argument("--mass-g", type=float, help="body mass, g (turbo timing)")
    sp.add_argument("--material", default="aluminium",
                    choices=sorted(C_MATERIAL) + ["custom"],
                    help="body material for the specific heat (default aluminium)")
    sp.add_argument("--c", type=float, help="custom specific heat, J/gK")
    sp.add_argument("--heat-w", type=float, help="heat in turbo, W")
    sp.add_argument("--input-w", type=float,
                    help="electrical input to the LED, W (heat helper)")
    sp.add_argument("--lumens", type=float, help="emitted flux, lm (heat helper)")

    sp = add("trace", "PCB trace width, IPC-2221 (DRV-5)", cmd_trace)
    sp.add_argument("--current-a", type=float, required=True, help="current, A")
    sp.add_argument("--oz", type=float, default=1.0, help="copper weight, oz (default 1)")
    sp.add_argument("--rise-c", type=float, default=10.0,
                    help="allowed temperature rise, °C (default 10)")
    sp.add_argument("--layer", choices=["external", "internal"], default="external")

    sp = add("divider", "battery voltage divider check or E24 suggestion (BAT-9)",
             cmd_divider)
    sp.add_argument("--v-max", type=float, required=True,
                    help="highest battery voltage, V")
    sp.add_argument("--adc-ref", type=float, required=True, help="ADC reference, V")
    sp.add_argument("--r-top", type=parse_ohms, help="battery to ADC pin, ohm (k/M ok)")
    sp.add_argument("--r-bottom", type=parse_ohms, help="ADC pin to ground, ohm (k/M ok)")
    sp.add_argument("--tolerance-pct", type=float, default=1.0,
                    help="resistor tolerance, %% (default 1)")

    sp = add("ntc", "NTC thermistor resistance, temperature, ADC (THM-4)", cmd_ntc)
    sp.add_argument("--r25", type=parse_ohms, required=True,
                    help="resistance at 25 °C, ohm (k/M ok)")
    sp.add_argument("--beta", type=float, required=True, help="beta constant, K")
    sp.add_argument("--r-fix", type=parse_ohms,
                    help="fixed resistor from the ADC reference to the pin, ohm")
    sp.add_argument("--adc-bits", type=int, default=12, help="ADC resolution (default 12)")
    sp.add_argument("--temp-c", type=float, help="temperature, °C")
    sp.add_argument("--ohms", type=parse_ohms, help="measured NTC resistance, ohm")
    sp.add_argument("--table", action="store_true",
                    help="table from -20 to 100 °C in 10 °C steps")
    return p


def main(argv=None, out=None):
    """Run the CLI. Returns the exit code (0 ok, 2 bad input)."""
    out = out or sys.stdout
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        rep = args.func(args)
    except ValueError as exc:
        parser.exit(2, "{} {}: error: {}\n".format(parser.prog, args.command, exc))
    if getattr(args, "json", False):
        out.write(rep.as_json() + "\n")
    else:
        text = rep.text()
        table = getattr(rep, "table_lines", None)
        if table:
            head, _, tail = text.partition("\n  formula:")
            text = head + "\n" + "\n".join(table) + "\n  formula:" + tail
        out.write(text + "\n")
    return 0


if __name__ == "__main__":
    try:  # avoid crashes on consoles that cannot show °, µ, Ω or ²
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    sys.exit(main())
