#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for tools/lux_calc.py.

Run from the repository root with either of:
    python3 -m unittest tools/test_lux_calc.py
    python3 tools/test_lux_calc.py
"""

import contextlib
import io
import json
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lux_calc as lc  # noqa: E402


def run_cli(*argv):
    """Run the CLI with the given arguments and return its stdout."""
    buf = io.StringIO()
    code = lc.main(list(argv), out=buf)
    assert code == 0
    return buf.getvalue()


class StandbyTest(unittest.TestCase):
    def test_bat6_check_values(self):
        self.assertAlmostEqual(lc.standby_max_current_ua(800), 32.9, places=1)
        self.assertAlmostEqual(lc.standby_max_current_ua(3000), 123, delta=0.5)

    def test_drain_round_trip(self):
        i = lc.standby_max_current_ua(800, 3.0)
        d = lc.standby_drain(800, i)
        self.assertAlmostEqual(d["percent_per_month"], 3.0, places=9)
        self.assertAlmostEqual(d["months_to_empty"], 100 / 3.0, places=9)

    def test_zero_current_never_empties(self):
        self.assertEqual(lc.standby_drain(800, 0)["months_to_empty"], math.inf)

    def test_rejects_bad_capacity(self):
        with self.assertRaises(ValueError):
            lc.standby_max_current_ua(0)


class RuntimeTest(unittest.TestCase):
    def test_led_power_model(self):
        # Vf = 2.75 + 0.15 * 1.5 = 2.975 V; P = 4.4625 W
        self.assertAlmostEqual(lc.led_vf(1.5), 2.975, places=9)
        self.assertAlmostEqual(lc.led_power_w(1.5), 4.4625, places=9)

    def test_runtime(self):
        r = lc.runtime_hours(3000, 5.0, cell_v=3.6, usable=0.9, driver_eff=0.9)
        self.assertAlmostEqual(r["p_in_w"], 5.0 / 0.9, places=9)
        self.assertAlmostEqual(r["hours"], 3.0 * 3.6 * 0.9 / (5.0 / 0.9), places=9)
        self.assertAlmostEqual(r["minutes"], r["hours"] * 60, places=9)
        self.assertAlmostEqual(r["hours"], 1.75, places=2)

    def test_efficiency_above_one_rejected(self):
        with self.assertRaises(ValueError):
            lc.runtime_hours(3000, 5.0, driver_eff=1.2)


class CellCurrentTest(unittest.TestCase):
    def test_root_satisfies_equation(self):
        c = lc.cell_current(10.0, 3.6, 0.05)
        i = c["current_a"]
        self.assertAlmostEqual((3.6 - i * 0.05) * i, 10.0, places=9)
        self.assertAlmostEqual(c["loaded_v"], 3.6 - i * 0.05, places=12)
        # smaller root: below the current at maximum power V/(2R)
        self.assertLess(i, 3.6 / (2 * 0.05))

    def test_zero_resistance(self):
        self.assertAlmostEqual(lc.cell_current(7.2, 3.6, 0)["current_a"], 2.0, places=12)

    def test_no_real_root(self):
        # maximum power V^2/(4R) = 64.8 W
        with self.assertRaises(ValueError):
            lc.cell_current(65.0, 3.6, 0.05)
        out = run_cli("cellcurrent", "--led-w", "100", "--cell-v", "3.6")
        self.assertIn("cannot deliver", out)

    def test_bat1_verdict(self):
        data = json.loads(run_cli("cellcurrent", "--led-a", "3", "--cell-v", "3.6",
                                  "--cell-max-a", "15", "--json"))
        self.assertTrue(data["bat1_ok"])
        self.assertAlmostEqual(data["rating_pct"], data["current_a"] / 15 * 100, places=9)
        data = json.loads(run_cli("cellcurrent", "--led-a", "3", "--cell-v", "3.6",
                                  "--cell-max-a", "4", "--json"))
        self.assertFalse(data["bat1_ok"])


class ThrowTest(unittest.TestCase):
    def test_beam_distance(self):
        self.assertAlmostEqual(lc.beam_distance_m(10000), 200.0, places=9)
        self.assertAlmostEqual(lc.lux_at(10000, 2.0), 2500.0, places=9)

    def test_beam_distance_is_quarter_lux(self):
        cd = 12345.0
        self.assertAlmostEqual(lc.lux_at(cd, lc.beam_distance_m(cd)), 0.25, places=12)

    def test_lux_cd_beam_round_trip(self):
        cd = lc.cd_from_lux(250.0, 2.0)
        self.assertAlmostEqual(cd, 1000.0, places=9)
        self.assertAlmostEqual(lc.lux_at(cd, 2.0), 250.0, places=9)
        self.assertAlmostEqual(lc.beam_distance_m(cd), 2 * math.sqrt(1000.0), places=9)

    def test_estimate(self):
        t = lc.throw_estimate(560, 2.0, 20, 0.7)
        lum = 560 / (math.pi * 2.0e-6)
        self.assertAlmostEqual(t["luminance_cd_m2"], lum, delta=lum * 1e-12)
        cd = 0.7 * lum * math.pi * 0.010 ** 2
        self.assertAlmostEqual(t["cd"], cd, delta=cd * 1e-12)
        # simplifies to eff * F * (D/2)^2 / A with consistent units
        self.assertAlmostEqual(t["cd"], 0.7 * 560 * 10.0 ** 2 / 2.0, places=6)


class ThermalTest(unittest.TestCase):
    def test_cylinder_area(self):
        a = lc.cylinder_area_cm2(25, 90)
        self.assertAlmostEqual(a, (math.pi * 25 * 90 + 2 * math.pi * 12.5 ** 2) / 100,
                               places=12)
        self.assertAlmostEqual(a, 80.5, places=1)

    def test_sustainable_heat(self):
        self.assertAlmostEqual(lc.sustainable_heat_w(100, 11.0, 25, 48),
                               11.0 * 0.01 * 23, places=12)

    def test_turbo_time(self):
        t = lc.turbo_time(80.0, 11.0, 60, 0.90, 6.875, 25, 48)
        r = 1 / (11.0 * 80e-4)
        tau = r * 54.0
        self.assertAlmostEqual(t["r_k_w"], r, places=12)
        self.assertAlmostEqual(t["tau_s"], tau, places=9)
        expected = -tau * math.log(1 - 23 / (6.875 * r))
        self.assertAlmostEqual(t["time_s"], expected, places=9)
        # the lumped curve reaches exactly the limit at that time
        rise = 6.875 * r * (1 - math.exp(-t["time_s"] / tau))
        self.assertAlmostEqual(rise, 23.0, places=9)

    def test_turbo_never(self):
        t = lc.turbo_time(80.0, 11.0, 60, 0.90, 1.0, 25, 48)
        self.assertIsNone(t["time_s"])
        self.assertIn("never", run_cli("thermal", "--area-cm2", "80", "--mass-g", "60",
                                       "--heat-w", "1"))

    def test_heat_from_light(self):
        self.assertAlmostEqual(lc.heat_from_light(10, 1000), 10 - 1000 / 320, places=12)
        with self.assertRaises(ValueError):
            lc.heat_from_light(1, 1000)

    def test_constants(self):
        self.assertEqual(lc.H_FINISH, {"anodised": 11.0, "bare": 6.5})
        self.assertEqual(lc.C_MATERIAL["aluminium"], 0.90)
        self.assertEqual(lc.C_MATERIAL["copper"], 0.385)


class TraceTest(unittest.TestCase):
    def test_drv5_check_values(self):
        self.assertAlmostEqual(lc.trace_width(1)["width_mm"], 0.30, delta=0.01)
        self.assertAlmostEqual(lc.trace_width(3)["width_mm"], 1.37, delta=0.02)
        self.assertAlmostEqual(lc.trace_width(5)["width_mm"], 2.77, delta=0.03)

    def test_formula_inverts(self):
        t = lc.trace_width(2.0, oz=2, rise_c=20, layer="internal")
        self.assertAlmostEqual(0.024 * 20 ** 0.44 * t["area_mil2"] ** 0.725, 2.0, places=9)
        self.assertAlmostEqual(t["thickness_mil"], 2 * 1.378, places=12)

    def test_internal_wider(self):
        self.assertGreater(lc.trace_width(2, layer="internal")["width_mm"],
                           lc.trace_width(2, layer="external")["width_mm"])


class DividerTest(unittest.TestCase):
    def test_check(self):
        d = lc.divider_check(4.2, 1.1, 750e3, 220e3, 1.0)
        self.assertAlmostEqual(d["ratio"], 220 / 970, places=12)
        self.assertAlmostEqual(d["v_adc"], 4.2 * 220 / 970, places=12)
        self.assertTrue(d["fits"])
        self.assertAlmostEqual(d["current_ua"], 4.2 / 970e3 * 1e6, places=9)
        hi = 222.2 / (742.5 + 222.2)
        self.assertAlmostEqual(d["ratio_error_pct"], (hi / (220 / 970) - 1) * 100, places=9)

    def test_equal_resistors_error(self):
        # Rb/(Rt+Rb) with 1 % at opposite limits: 1.01 / 2.00 -> +1.0 %
        d = lc.divider_check(8.4, 2.5, 100e3, 100e3, 1.0)
        self.assertAlmostEqual(d["ratio_error_pct"], 1.0, places=9)
        self.assertFalse(d["fits"])

    def test_suggestion(self):
        for v_max, ref in ((4.2, 1.1), (4.2, 3.3), (8.4, 2.5), (12.6, 1.2)):
            s = lc.divider_suggest(v_max, ref)
            rt, rb = s["r_top"], s["r_bottom"]
            ratio = rb / (rt + rb)
            self.assertLessEqual(ratio, 0.9 * ref / v_max)
            self.assertLessEqual(v_max * ratio, 0.9 * ref + 1e-12)
            self.assertTrue(0.8e6 <= rt + rb <= 1.25e6)
            for r in (rt, rb):
                mant = r / 10 ** math.floor(math.log10(r))
                self.assertIn(round(mant * 10), lc.E24)
        out = run_cli("divider", "--v-max", "4.2", "--adc-ref", "1.1")
        self.assertIn("100 nF", out)

    def test_no_divider_needed(self):
        self.assertIsNone(lc.divider_suggest(2.0, 3.3)["r_top"])


class NtcTest(unittest.TestCase):
    def test_thm4_check_value(self):
        self.assertAlmostEqual(lc.ntc_resistance(50, 100e3, 4250), 33.2e3, delta=50)
        self.assertAlmostEqual(lc.ntc_resistance(25, 100e3, 4250), 100e3, places=6)

    def test_temp_ohms_temp_round_trip(self):
        for t in range(-20, 101, 5):
            r = lc.ntc_resistance(t, 10e3, 3950)
            self.assertAlmostEqual(lc.ntc_temperature(r, 10e3, 3950), t, places=9)

    def test_adc_and_sensitivity(self):
        a = lc.ntc_adc(50, 100e3, 4250, 100e3, 12)
        rn = lc.ntc_resistance(50, 100e3, 4250)
        self.assertAlmostEqual(a["ratio"], rn / (100e3 + rn), places=12)
        self.assertEqual(a["code"], round(a["ratio"] * 4096))
        # analytic derivative: dcode/dT = 4096 * Rf/(Rf+Rn)^2 * Rn*B/T^2
        t_k = 323.15
        slope = 4096 * 100e3 / (100e3 + rn) ** 2 * rn * 4250 / t_k ** 2
        self.assertAlmostEqual(a["c_per_lsb"], 1 / slope, delta=1e-6)

    def test_table(self):
        rows = lc.ntc_table(100e3, 4250, r_fix=100e3)
        self.assertEqual([r["temp_c"] for r in rows], list(range(-20, 101, 10)))
        codes = [r["code"] for r in rows]
        self.assertEqual(codes, sorted(codes, reverse=True))

    def test_parse_ohms(self):
        self.assertEqual(lc.parse_ohms("100k"), 100e3)
        self.assertEqual(lc.parse_ohms("4.7k"), 4700.0)
        self.assertEqual(lc.parse_ohms("1M"), 1e6)
        self.assertEqual(lc.parse_ohms("220"), 220.0)


class CliTest(unittest.TestCase):
    CASES = [
        ["standby", "--capacity-mah", "800"],
        ["standby", "--capacity-mah", "800", "--current-ua", "12"],
        ["runtime", "--capacity-mah", "3000", "--led-a", "1.5"],
        ["cellcurrent", "--led-w", "5", "--cell-v", "3.6"],
        ["throw", "--lumens", "560", "--die-mm2", "2", "--optic-mm", "20"],
        ["thermal", "--diameter-mm", "25", "--length-mm", "90", "--mass-g", "60",
         "--input-w", "10", "--lumens", "1000"],
        ["trace", "--current-a", "3"],
        ["divider", "--v-max", "4.2", "--adc-ref", "1.1", "--r-top", "750k",
         "--r-bottom", "220k"],
        ["ntc", "--r25", "100k", "--beta", "4250", "--r-fix", "100k", "--table"],
    ]

    def test_text_has_formula(self):
        for case in self.CASES:
            self.assertIn("formula:", run_cli(*case), case)

    def test_json_parses(self):
        for case in self.CASES:
            data = json.loads(run_cli(*(case + ["--json"])))
            self.assertEqual(data["command"], case[0])
            self.assertTrue(data["formula"])
            # also accepted before the subcommand
            data = json.loads(run_cli(*(["--json"] + case)))
            self.assertEqual(data["command"], case[0])

    def test_check_values_in_text(self):
        self.assertIn("32.9 µA", run_cli("standby", "--capacity-mah", "800"))
        self.assertIn("123 µA", run_cli("standby", "--capacity-mah", "3000"))
        self.assertIn("1.37 mm", run_cli("trace", "--current-a", "3"))
        self.assertIn("33.2 kΩ", run_cli("ntc", "--r25", "100k", "--beta", "4250",
                                         "--temp-c", "50"))

    def test_bad_input_exits(self):
        err = io.StringIO()
        with self.assertRaises(SystemExit) as ctx, contextlib.redirect_stderr(err):
            lc.main(["throw", "--cd", "5", "--lux", "3"], out=io.StringIO())
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("exactly one", err.getvalue())


if __name__ == "__main__":
    unittest.main()
