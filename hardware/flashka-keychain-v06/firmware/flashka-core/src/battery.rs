// SPDX-License-Identifier: MIT OR Apache-2.0
//! Battery state of charge, cell current and runtime estimation.

use crate::config::{
    CELL_CAPACITY_MAH, CHARGE_FAST_MA, LOAD_CORR_MV_PER_A, MCU_AWAKE_MA, SOC_DEADBAND_X10,
    SOC_RECOVER_HYST_X10, SOC_SLEW_X10_PER_S,
};
use crate::mathx::lerp_i64;
use crate::protocol::RUNTIME_UNKNOWN;

/// Open-circuit voltage curve: (mV, %). v0.6: LiPo pouch cells.
#[cfg(not(feature = "board-v07"))]
pub const OCV_CURVE: [(u16, u8); 12] = [
    (4_200, 100),
    (4_100, 90),
    (4_000, 80),
    (3_920, 70),
    (3_850, 60),
    (3_800, 50),
    (3_750, 40),
    (3_710, 30),
    (3_670, 20),
    (3_600, 10),
    (3_450, 5),
    (3_300, 0),
];

/// Open-circuit voltage curve: (mV, %). v0.7: one Vapcell INR14500 F15 (3.60 V nominal). No curve
/// of the F15 is published: this is a generic curve of a 3.6 V-nominal NMC cell, so the percentage
/// is an estimate (about +-5 %).
#[cfg(feature = "board-v07")]
pub const OCV_CURVE: [(u16, u8); 12] = [
    (4_200, 100),
    (4_050, 90),
    (3_950, 80),
    (3_860, 70),
    (3_770, 60),
    (3_680, 50),
    (3_610, 40),
    (3_540, 30),
    (3_470, 20),
    (3_380, 10),
    (3_250, 5),
    (3_000, 0),
];

/// State of charge in 0.1 % (0..=1000) from an open-circuit voltage.
pub fn soc_x10_from_ocv(mv: u32) -> u16 {
    let first = OCV_CURVE[0];
    let last = OCV_CURVE[OCV_CURVE.len() - 1];
    if mv >= first.0 as u32 {
        return 1_000;
    }
    if mv <= last.0 as u32 {
        return 0;
    }
    for w in OCV_CURVE.windows(2) {
        let (hi_mv, hi_pct) = w[0];
        let (lo_mv, lo_pct) = w[1];
        if mv >= lo_mv as u32 {
            return lerp_i64(
                mv as i64,
                lo_mv as i64,
                hi_mv as i64,
                lo_pct as i64 * 10,
                hi_pct as i64 * 10,
            ) as u16;
        }
    }
    0
}

/// Forward voltage model of the LED: `V_LED = LED_VF0 + 0.15 V/A * I` (mV); v0.6 SST-20:
/// 2.75 V, v0.7 SST-20 Gen 2: 2.80 V ([`crate::board`]).
pub fn led_voltage_mv(led_ma: u32) -> u32 {
    crate::board::LED_VF0_MV + led_ma * 3 / 20
}

/// Estimated battery current of the LED path, `V_LED(I) * I / (0.9 * V_BAT)` (mA) - v0.6.
#[cfg(not(feature = "board-v07"))]
pub fn led_cell_current_ma(led_ma: u16, vbat_mv: u16) -> u32 {
    if led_ma == 0 {
        return 0;
    }
    let i = led_ma as u64;
    let v = (vbat_mv as u64).max(2_500);
    // (2750 + 3I/20) * I / (0.9 V)  ==  (55000 + 3I) * I / (18 V)
    (((55_000 + 3 * i) * i + 9 * v) / (18 * v)) as u32
}

/// Estimated battery current of the LED path, `V_LED(I) * I / (0.87 * V_BAT)` (mA) - v0.7
/// (SST-20 Gen 2 `2.80 V + 0.15 V/A`, buck path 87 %, [`crate::board`]).
#[cfg(feature = "board-v07")]
pub fn led_cell_current_ma(led_ma: u16, vbat_mv: u16) -> u32 {
    if led_ma == 0 {
        return 0;
    }
    let i = led_ma as u64;
    let v = (vbat_mv as u64).max(2_500);
    // (2800 + 3I/20) * I / (0.87 V)  ==  (280000 + 15I) * I / (87 V)
    (((280_000 + 15 * i) * i + 87 * v / 2) / (87 * v)) as u32
}

/// Total estimated cell current while awake: LED path + MCU/radio.
pub fn total_cell_current_ma(led_ma: u16, vbat_mv: u16) -> u32 {
    #[cfg(feature = "board-v07")]
    let led_ma = deliverable_led_ma(led_ma, vbat_mv);
    led_cell_current_ma(led_ma, vbat_mv) + MCU_AWAKE_MA
}

/// v0.7: the LED current the buck can really deliver at this battery voltage: at most the request,
/// and at 100 % duty `(V_BAT - V_LED0) / (R_LED + R_path)` ([`crate::board::DROP_PATH_MOHM`]). Used
/// by the state of charge and the runtime only; the cell-current limit keeps using the requested
/// current (an estimate that errs on the safe side).
#[cfg(feature = "board-v07")]
pub fn deliverable_led_ma(led_ma: u16, vbat_mv: u16) -> u16 {
    use crate::board::{DROP_PATH_MOHM, LED_RS_MOHM, LED_VF0_MV};
    let max = (vbat_mv as u32).saturating_sub(LED_VF0_MV) * 1_000 / (LED_RS_MOHM + DROP_PATH_MOHM);
    led_ma.min(max.min(u16::MAX as u32) as u16)
}

/// Largest LED current whose estimated cell current stays within `cell_limit_ma` - v0.6.
///
/// Solves `3 I^2 + 55000 I - 18 V Ic <= 0` for `I`.
#[cfg(not(feature = "board-v07"))]
pub fn max_led_ma_for_cell(vbat_mv: u16, cell_limit_ma: u16) -> u16 {
    let v = (vbat_mv as u64).max(2_500);
    let c = cell_limit_ma as u64;
    let disc = 55_000u64 * 55_000 + 4 * 3 * 18 * v * c;
    let i = (disc.isqrt() - 55_000) / 6;
    i.min(u16::MAX as u64) as u16
}

/// Largest LED current whose estimated cell current stays within `cell_limit_ma` - v0.7.
///
/// Solves `15 I^2 + 280000 I - 87 V Ic <= 0` for `I`.
#[cfg(feature = "board-v07")]
pub fn max_led_ma_for_cell(vbat_mv: u16, cell_limit_ma: u16) -> u16 {
    let v = (vbat_mv as u64).max(2_500);
    let c = cell_limit_ma as u64;
    let disc = 280_000u64 * 280_000 + 4 * 15 * 87 * v * c;
    let i = (disc.isqrt() - 280_000) / 30;
    i.min(u16::MAX as u64) as u16
}

/// Runtime at the present output: remaining capacity / cell current (minutes).
pub fn runtime_minutes(soc_x10: u16, cell_ma: u32) -> u16 {
    if cell_ma == 0 {
        return RUNTIME_UNKNOWN;
    }
    // mAh * 60 / mA ; remaining = capacity * soc/100 -> capacity * soc_x10 / 1000
    let remaining_mah_x1000 = CELL_CAPACITY_MAH as u64 * soc_x10 as u64; // mAh * 1000
    let minutes = remaining_mah_x1000 * 60 / (cell_ma as u64 * 1_000);
    minutes.min(RUNTIME_UNKNOWN as u64 - 1) as u16
}

/// What the charger is doing (for the SoC load correction).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Default)]
pub struct ChargeInfo {
    pub usb_present: bool,
    /// TP4057 reports charging and CHG_SET selects the fast current.
    pub fast_charging: bool,
    /// TP4057 reports charge complete.
    pub complete: bool,
}

/// Filtered state of charge.
///
/// The measured voltage is corrected for the load (`+0.12 V/A` of cell
/// current, `-0.12 V/A` of charge current) and converted with the OCV curve.
/// The displayed value then moves towards that estimate with a dead band and
/// a slew limit, and it only moves "against" the expected direction
/// (up while discharging, down while charging) when the estimate differs by
/// more than [`SOC_RECOVER_HYST_X10`] - so turning turbo on and off or
/// plugging USB in does not make the percentage jump.
#[derive(Clone, Copy, Debug, Default)]
pub struct SocEstimator {
    soc_x10: u16,
    initialized: bool,
    last_ms: u64,
    budget_x10_ms: u64,
}

impl SocEstimator {
    pub fn new() -> Self {
        Self::default()
    }

    /// Open-circuit voltage estimate (mV): `+0.12 V/A` of the estimated cell
    /// current of the LED path while the LED is on, `-0.12 V/A` of the charge
    /// current while fast charging.
    pub fn ocv_estimate(vbat_mv: u16, led_ma: u16, charge: ChargeInfo) -> u32 {
        #[cfg(feature = "board-v07")]
        let led_ma = deliverable_led_ma(led_ma, vbat_mv);
        let draw = led_cell_current_ma(led_ma, vbat_mv) as i64;
        let charge_ma = if charge.fast_charging { CHARGE_FAST_MA as i64 } else { 0 };
        let net = draw - charge_ma; // positive = discharging
        let corr = net * LOAD_CORR_MV_PER_A as i64 / 1_000;
        (vbat_mv as i64 + corr).max(0) as u32
    }

    /// Feed a filtered battery voltage (mV) with the LED current that was
    /// flowing when it was measured.
    pub fn update(&mut self, now: u64, vbat_mv: u16, led_ma: u16, charge: ChargeInfo) {
        let target = if charge.complete && charge.usb_present {
            1_000
        } else {
            soc_x10_from_ocv(Self::ocv_estimate(vbat_mv, led_ma, charge))
        };
        if !self.initialized {
            self.soc_x10 = target;
            self.initialized = true;
            self.last_ms = now;
            return;
        }
        let dt = now.saturating_sub(self.last_ms);
        self.last_ms = now;
        self.budget_x10_ms = (self.budget_x10_ms + dt * SOC_SLEW_X10_PER_S as u64).min(100_000);

        let cur = self.soc_x10;
        let (down_band, up_band) = if charge.usb_present {
            (SOC_RECOVER_HYST_X10, SOC_DEADBAND_X10)
        } else {
            (SOC_DEADBAND_X10, SOC_RECOVER_HYST_X10)
        };
        let want = if target + down_band < cur || target > cur + up_band {
            target
        } else {
            cur
        };
        if want == cur {
            return;
        }
        let max_step = (self.budget_x10_ms / 1_000) as u16;
        if max_step == 0 {
            return;
        }
        let step = want.abs_diff(cur).min(max_step);
        self.budget_x10_ms -= step as u64 * 1_000;
        self.soc_x10 = if want > cur { cur + step } else { cur - step };
    }

    pub fn initialized(&self) -> bool {
        self.initialized
    }

    /// State of charge in 0.1 %.
    pub fn soc_x10(&self) -> u16 {
        self.soc_x10
    }

    /// State of charge in % (rounded).
    pub fn percent(&self) -> u8 {
        ((self.soc_x10 + 5) / 10).min(100) as u8
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ocv_curve_points() {
        for (mv, pct) in OCV_CURVE {
            assert_eq!(soc_x10_from_ocv(mv as u32), pct as u16 * 10, "{mv}");
        }
        assert_eq!(soc_x10_from_ocv(4_300), 1_000);
        assert_eq!(soc_x10_from_ocv(3_000), 0);
        #[cfg(not(feature = "board-v07"))]
        {
            assert_eq!(soc_x10_from_ocv(3_825), 550);
            assert_eq!(soc_x10_from_ocv(3_375), 25);
        }
        // v0.7 (F15, 3.6 V-nominal NMC curve): half full at 3.68 V
        #[cfg(feature = "board-v07")]
        {
            assert_eq!(soc_x10_from_ocv(3_725), 550);
            assert_eq!(soc_x10_from_ocv(3_125), 25);
            assert_eq!(soc_x10_from_ocv(2_900), 0);
        }
        // monotonic
        let mut last = 0;
        for mv in 3_200..4_300 {
            let s = soc_x10_from_ocv(mv);
            assert!(s >= last);
            last = s;
        }
    }

    #[cfg(not(feature = "board-v07"))]
    #[test]
    fn cell_current_formula() {
        // 1 A LED at 3.6 V: V_LED = 2.9 V, P = 2.9 W, I = 2.9 / (0.9*3.6) = 0.895 A
        assert_eq!(led_cell_current_ma(1_000, 3_600), 895);
        assert_eq!(led_cell_current_ma(0, 3_600), 0);
        // 2.2 A at 3.7 V: V_LED = 3.08, P = 6.776 W -> 2.035 A
        let i = led_cell_current_ma(2_200, 3_700);
        assert!((2_030..=2_040).contains(&i), "{i}");
    }

    #[cfg(feature = "board-v07")]
    #[test]
    fn cell_current_formula() {
        // 1 A LED at 3.6 V: V_LED = 2.95 V, P = 2.95 W, I = 2.95 / (0.87*3.6) = 0.942 A
        assert_eq!(led_cell_current_ma(1_000, 3_600), 942);
        assert_eq!(led_cell_current_ma(0, 3_600), 0);
        // 3.0 A at 3.7 V: V_LED = 3.25 V, P = 9.75 W -> 3.029 A (electronics estimate 2.8-3.05 A)
        let i = led_cell_current_ma(3_000, 3_700);
        assert!((3_025..=3_032).contains(&i), "{i}");
        assert_eq!(led_voltage_mv(3_000), 3_250);
    }

    #[test]
    fn cell_limit_inverse() {
        for v in [3_000u16, 3_300, 3_700, 4_200] {
            for c in [200u16, 800, 1_600, 2_600, 3_000] {
                let i = max_led_ma_for_cell(v, c);
                assert!(led_cell_current_ma(i, v) <= c as u32 + 1, "v={v} c={c} i={i}");
                assert!(led_cell_current_ma(i + 2, v) > c as u32 - 1, "not tight v={v} c={c} i={i}");
            }
        }
        // Endurance (800 mA cell) at 3.3 V allows about 826 mA LED (v0.7: 787 mA)
        let i = max_led_ma_for_cell(3_300, 800);
        #[cfg(not(feature = "board-v07"))]
        assert!((820..=830).contains(&i), "{i}");
        #[cfg(feature = "board-v07")]
        assert!((782..=792).contains(&i), "{i}");
    }

    /// v0.7 cell: one Vapcell INR14500 F15 (3 A maximum continuous) behind a DW01A + SE8830A
    /// protection (Kelvin-sensed) that trips at 4.3-4.5 A with hot MOSFETs (5.3-5.6 A at 25 degC)
    /// and at as little as 3.0-3.15 A in the worst case (DW01A at its 120 mV minimum, MOSFETs hot
    /// at their maximum resistance; electronics "power" block).
    #[cfg(feature = "board-v07")]
    #[test]
    fn v07_battery_limits() {
        use crate::board::TURBO_MAX_MA;
        use crate::profile::Profile;
        // 2850 mA turbo: about 2.6 A at 4.00 V, 2.86 A at 3.70 V where the buck reaches
        // 100 % duty (the electronics estimate 3.0 A is held down to about 3.71 V)
        assert!((2_620..=2_660).contains(&led_cell_current_ma(TURBO_MAX_MA, 4_000)));
        assert!((2_850..=2_870).contains(&led_cell_current_ma(TURBO_MAX_MA, 3_700)));
        // the 2800 mA cell limit of the turbo profiles lets the full turbo through down to
        // about 3.78 V under load (estimated cell current; about 4.0 V at rest)
        assert!(max_led_ma_for_cell(3_780, 2_800) >= TURBO_MAX_MA);
        assert!(max_led_ma_for_cell(3_770, 2_800) < TURBO_MAX_MA);
        for p in [Profile::EXTREME, Profile::BALANCED, Profile::ENDURANCE] {
            for v in (3_000u16..=4_200).step_by(10) {
                let led = max_led_ma_for_cell(v, p.cell_limit_ma).min(p.turbo_ma.max(p.high_ma));
                let cell = led_cell_current_ma(led, v);
                assert!(cell <= p.cell_limit_ma as u32 + 1, "v={v} led={led} cell={cell}");
                // at least 7 % below the worst-case protection trip (3.0 A hot) and below the
                // F15's 3 A rating, a third below the typical trip with hot MOSFETs (4.3 A)
                assert!(cell * 107 / 100 <= 3_000, "v={v} cell={cell}");
                assert!(cell * 3 / 2 <= 4_300, "v={v} cell={cell}");
                // without turbo every level stays within LuxLibre BAT-1 (70 % of 3 A) down to the
                // profile's step-down voltage; only the timed, regulated turbo goes above it (the
                // documented BAT-1 deviation of the turbo profiles' 2800 mA)
                let high = max_led_ma_for_cell(v, p.cell_limit_ma).min(p.high_ma.max(p.stepdown_ma));
                if v >= p.lv_stepdown_mv() {
                    assert!(led_cell_current_ma(high, v) <= 3_000 * 70 / 100, "v={v} high={high}");
                }
            }
        }
        // the SoC load correction and the runtime use the F15
        assert_eq!(CELL_CAPACITY_MAH, 1_400);
        assert_eq!(LOAD_CORR_MV_PER_A, 130);
    }

    #[test]
    fn runtime() {
        #[cfg(not(feature = "board-v07"))]
        {
            // 50 % of 800 mAh = 400 mAh at 400 mA -> 60 min
            assert_eq!(runtime_minutes(500, 400), 60);
            // 800 mAh at 1 mA = 48000 min (still below the 0xFFFF "unknown" marker)
            assert_eq!(runtime_minutes(1_000, 1), 48_000);
        }
        #[cfg(feature = "board-v07")]
        {
            // 50 % of 1400 mAh = 700 mAh at 400 mA -> 105 min
            assert_eq!(runtime_minutes(500, 400), 105);
            // 1400 mAh at 2 mA = 42000 min
            assert_eq!(runtime_minutes(1_000, 2), 42_000);
        }
        assert_eq!(runtime_minutes(1_000, 0), RUNTIME_UNKNOWN);
        assert_eq!(runtime_minutes(0, 500), 0);
    }

    #[test]
    fn load_correction() {
        let no = ChargeInfo::default();
        // 1 A LED at 3.6 V -> 895 mA cell current -> +107 mV (v0.7: 942 mA x 130 mV/A = +122 mV)
        #[cfg(not(feature = "board-v07"))]
        assert_eq!(SocEstimator::ocv_estimate(3_600, 1_000, no), 3_600 + 107);
        #[cfg(feature = "board-v07")]
        assert_eq!(SocEstimator::ocv_estimate(3_600, 1_000, no), 3_600 + 122);
        // LED off: no correction
        assert_eq!(SocEstimator::ocv_estimate(3_600, 0, no), 3_600);
        let fast = ChargeInfo {
            usb_present: true,
            fast_charging: true,
            complete: false,
        };
        // light off while charging at 280 mA -> -33 mV (v0.7: 475 mA x 130 mV/A = -61 mV)
        #[cfg(not(feature = "board-v07"))]
        assert_eq!(SocEstimator::ocv_estimate(4_000, 0, fast), 4_000 - 33);
        #[cfg(feature = "board-v07")]
        assert_eq!(SocEstimator::ocv_estimate(4_000, 0, fast), 4_000 - 61);
    }

    #[test]
    fn filter_no_jump_on_load_step() {
        let mut s = SocEstimator::new();
        let no = ChargeInfo::default();
        #[cfg(not(feature = "board-v07"))]
        let v_rest = 3_850;
        #[cfg(feature = "board-v07")]
        let v_rest = 3_770;
        s.update(0, v_rest, 0, no);
        assert_eq!(s.percent(), 60);
        // turbo on: voltage sags 250 mV; correction gives back ~245 mV
        // (v0.7, one F15 at 60 %: High 1530 mA, 1.6 A from 0.13 ohm sags about 210 mV)
        #[cfg(not(feature = "board-v07"))]
        let (v_turbo, turbo_ma) = (3_600, 2_200);
        #[cfg(feature = "board-v07")]
        let (v_turbo, turbo_ma) = (3_560, 1_530);
        for k in 1..100 {
            s.update(k * 100, v_turbo, turbo_ma, no);
        }
        let p = s.percent();
        assert!((57..=60).contains(&p), "{p}");
        // off again: the voltage recovers, the percentage must not jump up
        for k in 100..200 {
            s.update(k * 100, v_rest + 2, 0, no);
        }
        assert!(s.percent() <= p + 1);
    }

    /// v0.7: a half-full F15 sags under turbo and the buck delivers less than asked; the state of
    /// charge and the runtime use the deliverable current, so the percentage does not jump.
    #[cfg(feature = "board-v07")]
    #[test]
    fn v07_deliverable_current_in_dropout() {
        // full cell under turbo (3.84 V at the ADC): the whole 2850 mA
        assert_eq!(deliverable_led_ma(2_850, 3_840), 2_850);
        // half-full cell (3.39 V under turbo): about 2120 mA
        let d = deliverable_led_ma(2_850, 3_390);
        assert!((2_100..=2_140).contains(&d), "{d}");
        assert_eq!(deliverable_led_ma(40, 3_390), 40);
        assert_eq!(deliverable_led_ma(2_850, 2_700), 0);
        // the estimate at 50 % stays at about 50 % during the dimmed turbo
        let pct = soc_x10_from_ocv(SocEstimator::ocv_estimate(3_390, 2_850, ChargeInfo::default()));
        assert!((480..=520).contains(&pct), "{pct}");
        assert_eq!(total_cell_current_ma(2_850, 3_390), led_cell_current_ma(d, 3_390) + MCU_AWAKE_MA);
        // the cell-current limit keeps the requested current (errs on the safe side)
        assert!(led_cell_current_ma(2_850, 3_390) > led_cell_current_ma(d, 3_390));
    }

    #[test]
    fn filter_slew_limited() {
        let mut s = SocEstimator::new();
        let no = ChargeInfo::default();
        s.update(0, 4_000, 0, no);
        let start = s.soc_x10();
        // estimate drops a lot at once: at most 0.5 %/s
        s.update(1_000, 3_600, 0, no);
        assert_eq!(start - s.soc_x10(), 5);
        s.update(11_000, 3_600, 0, no);
        assert_eq!(start - s.soc_x10(), 55);
    }

    #[test]
    fn charge_complete_is_full() {
        let mut s = SocEstimator::new();
        let done = ChargeInfo {
            usb_present: true,
            fast_charging: false,
            complete: true,
        };
        s.update(0, 4_150, 0, done);
        assert_eq!(s.percent(), 100);
    }
}
