// SPDX-License-Identifier: MIT OR Apache-2.0
//! Conversions between physical quantities and the values the hardware sees.
//!
//! The circuit values come from `tools/kicad/flashka_parts.py` (unchanged since v0.5):
//! * LED current loop: `I_LED = VSET / 20 mOhm`, `VSET = 3.3 V * duty * R16 / (100k + R16)`
//!   -> 3235 mA (v0.6, R16 = 2k) or 3552 mA (v0.7, R16 = 2.2k) at 100 % duty of the 13-bit
//!   LEDC PWM on GPIO6. The set point never exceeds [`LED_MAX_MA`] (v0.7: 3000 mA).
//! * VBAT sense: 1 M / 1 M divider on GPIO0 -> `VBAT = 2 * V_adc`.
//! * NTC: 100 k from 3V3 to GPIO1, NTC 100 k B25/50 = 4250 K to GND.

use crate::config::{NTC_OPEN_MV, NTC_SHORT_MV};
use crate::mathx::ln_f32;

/// LED current at 100 % PWM duty (mA): 3235 (v0.6) or 3552 (v0.7), see [`crate::board`].
pub const LED_FULL_SCALE_MA: u32 = crate::board::LED_FULL_SCALE_MA;
/// Hard ceiling of the LED current (mA), enforced by [`led_duty_counts`]: v0.6 = full scale,
/// v0.7 = 3000 mA (SST-20 Gen 2 datasheet maximum).
pub const LED_MAX_MA: u32 = crate::board::LED_MAX_MA;
/// Largest 13-bit duty value used (8191 = 99.99 %).
pub const PWM_MAX_COUNTS: u32 = 8_191;
/// Supply of the NTC divider (mV).
pub const NTC_SUPPLY_MV: u32 = 3_300;
/// Fixed resistor of the NTC divider (ohm).
pub const NTC_R_FIXED: f32 = 100_000.0;
/// NTC nominal resistance at 25 degC (ohm).
pub const NTC_R25: f32 = 100_000.0;
/// NTC beta (B25/50, K).
pub const NTC_BETA: f32 = 4_250.0;

/// 13-bit duty for an LED current: `round(I / full scale * 8191)`. The only place where a
/// current becomes a PWM duty: requests above [`LED_MAX_MA`] are cut to it (the LED ceiling).
pub fn led_duty_counts(ma: u16) -> u16 {
    let ma = (ma as u32).min(LED_MAX_MA);
    ((ma * PWM_MAX_COUNTS + LED_FULL_SCALE_MA / 2) / LED_FULL_SCALE_MA) as u16
}

/// LED current produced by a duty value (inverse of [`led_duty_counts`]).
pub fn duty_to_ma(counts: u16) -> u16 {
    let c = (counts as u32).min(PWM_MAX_COUNTS);
    ((c * LED_FULL_SCALE_MA + PWM_MAX_COUNTS / 2) / PWM_MAX_COUNTS) as u16
}

/// Battery voltage from the calibrated ADC reading of GPIO0 (1 M / 1 M divider).
pub fn vbat_from_adc_mv(adc_mv: u16) -> u16 {
    (adc_mv as u32 * 2).min(u16::MAX as u32) as u16
}

/// Temperature reading of the board NTC.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TempReading {
    /// No sample yet.
    Unknown,
    /// Valid temperature in 0.1 degC.
    Valid(i16),
    /// Node voltage too high: sensor open (or colder than about -7 degC).
    Open,
    /// Node voltage too low: sensor or node shorted to ground.
    Short,
}

impl TempReading {
    /// Temperature if valid.
    pub fn valid(self) -> Option<i16> {
        match self {
            TempReading::Valid(t) => Some(t),
            _ => None,
        }
    }

    /// Value reported in the Status packet (0.1 degC). Faults are reported as
    /// clearly implausible values: open = -40.0 degC, short = +150.0 degC.
    pub fn report_dc(self) -> i16 {
        match self {
            TempReading::Valid(t) => t,
            TempReading::Unknown => 0,
            TempReading::Open => -400,
            TempReading::Short => 1_500,
        }
    }
}

/// NTC node voltage -> temperature (0.1 degC).
///
/// `R_ntc = 100k * V / (3.3 - V)`, `T = 1 / (1/298.15 + ln(R/100k) / 4250) - 273.15`.
pub fn ntc_temp(ntc_mv: u16) -> TempReading {
    if ntc_mv >= NTC_OPEN_MV {
        return TempReading::Open;
    }
    if ntc_mv <= NTC_SHORT_MV {
        return TempReading::Short;
    }
    let v = ntc_mv as f32;
    let r = NTC_R_FIXED * v / (NTC_SUPPLY_MV as f32 - v);
    let inv_t = 1.0 / 298.15 + ln_f32(r / NTC_R25) / NTC_BETA;
    let t_c = 1.0 / inv_t - 273.15;
    let dc = t_c * 10.0;
    // round to nearest without libm
    let dc = if dc >= 0.0 { dc + 0.5 } else { dc - 0.5 } as i32;
    TempReading::Valid(dc.clamp(-999, 2_000) as i16)
}

/// Inverse of [`ntc_temp`] for tests and documentation: node voltage (mV) at
/// a temperature (degC).
pub fn ntc_mv_at(temp_c: f32) -> u16 {
    // R = R25 * exp(B * (1/T - 1/T25)); exp via ln inverse (Newton) is overkill:
    // use the series of e^x since |x| < 4 in the useful range.
    let x = NTC_BETA * (1.0 / (temp_c + 273.15) - 1.0 / 298.15);
    let r = NTC_R25 * exp_f32(x);
    let v = NTC_SUPPLY_MV as f32 * r / (r + NTC_R_FIXED);
    (v + 0.5) as u16
}

/// e^x for moderate |x| (used only by [`ntc_mv_at`]).
fn exp_f32(x: f32) -> f32 {
    // range reduction: e^x = (e^(x/16))^16
    let y = x / 16.0;
    let mut term = 1.0f32;
    let mut sum = 1.0f32;
    let mut n = 1.0f32;
    while n < 12.0 {
        term *= y / n;
        sum += term;
        n += 1.0;
    }
    let mut r = sum;
    for _ in 0..4 {
        r *= r;
    }
    r
}

#[cfg(test)]
mod tests {
    use super::*;

    fn reference_temp_c(mv: f64) -> f64 {
        let r = 100_000.0 * mv / (3_300.0 - mv);
        1.0 / (1.0 / 298.15 + (r / 100_000.0).ln() / 4_250.0) - 273.15
    }

    #[test]
    fn duty_scaling() {
        assert_eq!(led_duty_counts(0), 0);
        #[cfg(not(feature = "board-v07"))]
        {
            assert_eq!(led_duty_counts(3_235), 8_191);
            assert_eq!(led_duty_counts(4_000), 8_191);
            // 1000 mA -> 1000/3235*8191 = 2531.99
            assert_eq!(led_duty_counts(1_000), 2_532);
            // Moon 3 mA -> 7.6 counts
            assert_eq!(led_duty_counts(3), 8);
        }
        #[cfg(feature = "board-v07")]
        {
            // 3000 mA -> 3000/3552*8191 = 6918.07 (84.5 %); anything above is cut to 3000 mA
            assert_eq!(led_duty_counts(3_000), 6_918);
            assert_eq!(led_duty_counts(3_235), 6_918);
            assert_eq!(led_duty_counts(4_000), 6_918);
            // 1000 mA -> 1000/3552*8191 = 2306.03
            assert_eq!(led_duty_counts(1_000), 2_306);
            // Moon 3 mA -> 6.9 counts (1 count = 0.43 mA)
            assert_eq!(led_duty_counts(3), 7);
            // High 1530 mA -> 3528.2 counts
            assert_eq!(led_duty_counts(1_530), 3_528);
            // turbo 2850 mA -> 6572.2 counts (80.2 % duty)
            assert_eq!(led_duty_counts(2_850), 6_572);
        }
        for ma in [1u16, 2, 15, 30, 200, 600, 900, 1200, 2200, 3000] {
            let back = duty_to_ma(led_duty_counts(ma));
            assert!((back as i32 - ma as i32).abs() <= 1, "{ma} -> {back}");
        }
    }

    /// The LED ceiling holds at the hardware boundary for every possible request: the duty for
    /// any u16 never gives more than LED_MAX_MA, neither by the firmware's scale nor with the
    /// LEDC's real duty (counts / 8192), and it rises monotonically up to the ceiling.
    #[test]
    fn ceiling_holds_for_every_request() {
        let max_counts = led_duty_counts(LED_MAX_MA as u16);
        let mut last = 0;
        for ma in 0..=u16::MAX {
            let c = led_duty_counts(ma);
            assert!(c <= max_counts, "{ma} mA -> {c} counts");
            assert!(c >= last, "not monotonic at {ma}");
            last = c;
            assert!(duty_to_ma(c) as u32 <= LED_MAX_MA, "{ma}");
            // real duty of the LEDC is counts / 2^13
            assert!(c as u32 * LED_FULL_SCALE_MA <= LED_MAX_MA * 8_192, "{ma}");
        }
        assert_eq!(led_duty_counts(u16::MAX), max_counts);
        #[cfg(feature = "board-v07")]
        {
            // 6918 / 8192 = 84.4 % of the 3552 mA full scale = 2999.6 mA; with the exact
            // hardware full scale (3.3 V x 2.2 / 102.2 / 20 mOhm = 3551.9 mA) 2999.5 mA
            assert_eq!(max_counts, 6_918);
            let fs = 3.3_f64 * 2.2 / 102.2 / 0.020 * 1000.0;
            assert!(max_counts as f64 / 8192.0 * fs <= 3_000.0);
            // one count below the ceiling is still a valid set point, one above would not be
            assert!((max_counts as u32 + 1) * LED_FULL_SCALE_MA > LED_MAX_MA * 8_191);
        }
    }

    #[test]
    fn vbat_divider() {
        assert_eq!(vbat_from_adc_mv(2_100), 4_200);
        assert_eq!(vbat_from_adc_mv(1_650), 3_300);
    }

    #[test]
    fn ntc_25c_and_formula() {
        assert_eq!(ntc_temp(1_650), TempReading::Valid(250));
        for mv in (150u16..2_790).step_by(37) {
            let TempReading::Valid(t) = ntc_temp(mv) else {
                panic!("{mv} invalid")
            };
            let reference = reference_temp_c(mv as f64) * 10.0;
            assert!(
                (t as f64 - reference).abs() <= 1.0,
                "mv={mv} got {t} want {reference}"
            );
        }
    }

    #[test]
    fn ntc_faults() {
        assert_eq!(ntc_temp(2_800), TempReading::Open);
        assert_eq!(ntc_temp(3_300), TempReading::Open);
        assert_eq!(ntc_temp(50), TempReading::Short);
        assert_eq!(TempReading::Open.report_dc(), -400);
        assert_eq!(TempReading::Short.report_dc(), 1_500);
    }

    #[test]
    fn ntc_inverse() {
        for c in [0.0f32, 25.0, 45.0, 55.0, 60.0, 70.0, 80.0] {
            let mv = ntc_mv_at(c);
            let back = ntc_temp(mv).valid().unwrap() as f32 / 10.0;
            assert!((back - c).abs() < 0.3, "{c} -> {mv} mV -> {back}");
        }
        // 80 degC is about 0.32 V, well inside the ADC range
        let mv80 = ntc_mv_at(80.0);
        assert!((300..350).contains(&mv80), "{mv80}");
    }
}
