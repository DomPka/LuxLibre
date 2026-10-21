// SPDX-License-Identifier: MIT OR Apache-2.0
//! Battery state of charge, cell current and runtime estimation.

use crate::config::{
    CELL_CAPACITY_MAH, CHARGE_FAST_MA, LOAD_CORR_MV_PER_A, MCU_AWAKE_MA, SOC_DEADBAND_X10,
    SOC_RECOVER_HYST_X10, SOC_SLEW_X10_PER_S,
};
use crate::mathx::lerp_i64;
use crate::protocol::RUNTIME_UNKNOWN;

/// LiPo open-circuit voltage curve: (mV, %).
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

/// Forward voltage model of the SST-20: `V_LED = 2.75 V + 0.15 V/A * I` (mV).
pub fn led_voltage_mv(led_ma: u32) -> u32 {
    2_750 + led_ma * 3 / 20
}

/// Estimated battery current of the LED path, `V_LED(I) * I / (0.9 * V_BAT)` (mA).
pub fn led_cell_current_ma(led_ma: u16, vbat_mv: u16) -> u32 {
    if led_ma == 0 {
        return 0;
    }
    let i = led_ma as u64;
    let v = (vbat_mv as u64).max(2_500);
    // (2750 + 3I/20) * I / (0.9 V)  ==  (55000 + 3I) * I / (18 V)
    (((55_000 + 3 * i) * i + 9 * v) / (18 * v)) as u32
}

/// Total estimated cell current while awake: LED path + MCU/radio.
pub fn total_cell_current_ma(led_ma: u16, vbat_mv: u16) -> u32 {
    led_cell_current_ma(led_ma, vbat_mv) + MCU_AWAKE_MA
}

/// Largest LED current whose estimated cell current stays within `cell_limit_ma`.
///
/// Solves `3 I^2 + 55000 I - 18 V Ic <= 0` for `I`.
pub fn max_led_ma_for_cell(vbat_mv: u16, cell_limit_ma: u16) -> u16 {
    let v = (vbat_mv as u64).max(2_500);
    let c = cell_limit_ma as u64;
    let disc = 55_000u64 * 55_000 + 4 * 3 * 18 * v * c;
    let i = (disc.isqrt() - 55_000) / 6;
    i.min(u16::MAX as u64) as u16
}

/// Runtime at the present output: remaining capacity / cell current (minutes).
pub fn runtime_minutes(soc_x10: u16, cell_ma: u32) -> u16 {
    if cell_ma == 0 {
        return RUNTIME_UNKNOWN;
    }
    // mAh * 60 / mA ; remaining = 800 * soc/100 -> 800 * soc_x10 / 1000
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
        assert_eq!(soc_x10_from_ocv(3_825), 550);
        assert_eq!(soc_x10_from_ocv(3_375), 25);
        // monotonic
        let mut last = 0;
        for mv in 3_200..4_300 {
            let s = soc_x10_from_ocv(mv);
            assert!(s >= last);
            last = s;
        }
    }

    #[test]
    fn cell_current_formula() {
        // 1 A LED at 3.6 V: V_LED = 2.9 V, P = 2.9 W, I = 2.9 / (0.9*3.6) = 0.895 A
        assert_eq!(led_cell_current_ma(1_000, 3_600), 895);
        assert_eq!(led_cell_current_ma(0, 3_600), 0);
        // 2.2 A at 3.7 V: V_LED = 3.08, P = 6.776 W -> 2.035 A
        let i = led_cell_current_ma(2_200, 3_700);
        assert!((2_030..=2_040).contains(&i), "{i}");
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
        // Endurance (800 mA cell) at 3.3 V allows about 826 mA LED
        let i = max_led_ma_for_cell(3_300, 800);
        assert!((820..=830).contains(&i), "{i}");
    }

    #[test]
    fn runtime() {
        // 50 % of 800 mAh = 400 mAh at 400 mA -> 60 min
        assert_eq!(runtime_minutes(500, 400), 60);
        assert_eq!(runtime_minutes(1_000, 0), RUNTIME_UNKNOWN);
        // 800 mAh at 1 mA = 48000 min (still below the 0xFFFF "unknown" marker)
        assert_eq!(runtime_minutes(1_000, 1), 48_000);
        assert_eq!(runtime_minutes(0, 500), 0);
    }

    #[test]
    fn load_correction() {
        let no = ChargeInfo::default();
        // 1 A LED at 3.6 V -> 895 mA cell current -> +107 mV
        assert_eq!(SocEstimator::ocv_estimate(3_600, 1_000, no), 3_600 + 107);
        // LED off: no correction
        assert_eq!(SocEstimator::ocv_estimate(3_600, 0, no), 3_600);
        let fast = ChargeInfo {
            usb_present: true,
            fast_charging: true,
            complete: false,
        };
        // light off while charging at 280 mA -> -33 mV
        assert_eq!(SocEstimator::ocv_estimate(4_000, 0, fast), 4_000 - 33);
    }

    #[test]
    fn filter_no_jump_on_load_step() {
        let mut s = SocEstimator::new();
        let no = ChargeInfo::default();
        s.update(0, 3_850, 0, no);
        assert_eq!(s.percent(), 60);
        // turbo on: voltage sags 250 mV; correction gives back ~245 mV
        for k in 1..100 {
            s.update(k * 100, 3_600, 2_200, no);
        }
        let p = s.percent();
        assert!((57..=60).contains(&p), "{p}");
        // off again: the voltage recovers, the percentage must not jump up
        for k in 100..200 {
            s.update(k * 100, 3_852, 0, no);
        }
        assert!(s.percent() <= p + 1);
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
