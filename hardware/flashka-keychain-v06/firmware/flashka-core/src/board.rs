// SPDX-License-Identifier: MIT OR Apache-2.0
//! Board variant: every constant that depends on the main board.
//!
//! One code base drives two boards. The board is chosen when the firmware is built (Cargo
//! feature of `flashka-core` and `flashka-fw`; `BOARD=v07 firmware/build.sh`):
//!
//! | | default (no feature) | feature `board-v07` |
//! |---|---|---|
//! | Board | FlashKa Keychain v0.6 | FlashKa Keychain v0.7 |
//! | Firmware | 0.6.0 (unchanged) | 0.7.0 |
//! | LED | SST-20, flat window | SST-20 Gen 2 6500 K G1 behind a LEDiL LISA3 TIR optic |
//! | Driver full scale (100 % duty) | 3235 mA (VSET 2 k / 102 k) | 3552 mA (VSET 2.2 k / 102.2 k) |
//! | Hard LED current ceiling | full scale (levels end at 2200 mA) | **3000 mA** (LED datasheet maximum) |
//! | Highest level / Custom turbo | 3000 mA (protocol) | **2850 mA** (3000 mA less the 5 % worst-case tolerance) |
//! | Cells | 2 x LP601646, 800 mAh | 1 x Vapcell INR14500 F15, 1500 mAh (1400 mAh in the estimates), protection IC on the board |
//! | LED model for the cell current | 2.75 V + 0.15 V/A, buck 90 % | 2.80 V + 0.15 V/A, buck 87 % |
//! | Load correction of the SoC | 120 mV/A | 130 mV/A |
//! | Open-circuit voltage curve | LiPo (3.80 V at 50 %) | 3.6 V-nominal NMC cell (3.68 V at 50 %), [`crate::battery`] |
//! | Fast-charge current (SoC correction) | 280 mA (R3 3.3 k) | 475 mA (R3 2.0 k) |
//!
//! Everything else (pins, buttons, protocol, presenter mode, protection rules) is the same on
//! both boards. The profile tables are in [`crate::profile`]; the conversions that use these
//! constants in [`crate::hw`] (LED current -> PWM duty, the one place where the ceiling is
//! enforced) and [`crate::battery`] (cell current, runtime, state of charge).

/// Board name (logs and documentation).
#[cfg(not(feature = "board-v07"))]
pub const BOARD_NAME: &str = "FlashKa Keychain v0.6";
/// Board name (logs and documentation).
#[cfg(feature = "board-v07")]
pub const BOARD_NAME: &str = "FlashKa Keychain v0.7";

// The firmware version of each board's image: app descriptor, boot log, Info characteristic.
// firmware/build.sh reads the line of the board it builds (keep the "// build.sh:" tags).
#[cfg(not(feature = "board-v07"))]
pub const FW_VERSION: &str = "0.6.0"; // build.sh: v06
#[cfg(feature = "board-v07")]
pub const FW_VERSION: &str = "0.7.0"; // build.sh: v07

/// Text of the Info characteristic (<= 20 bytes): product and firmware version. The app tells
/// the boards apart by it: firmware 0.6.x runs on v0.6 boards, 0.7.x on v0.7 boards.
#[cfg(not(feature = "board-v07"))]
pub const INFO_TEXT: &str = "FlashKa fw 0.6.0";
/// Text of the Info characteristic (<= 20 bytes): product and firmware version. The app tells
/// the boards apart by it: firmware 0.6.x runs on v0.6 boards, 0.7.x on v0.7 boards.
#[cfg(feature = "board-v07")]
pub const INFO_TEXT: &str = "FlashKa fw 0.7.0";

/// Product version in the PnP ID (0xJJMN: 0x0060 = 0.6.0, 0x0070 = 0.7.0).
#[cfg(not(feature = "board-v07"))]
pub const PNP_VERSION: u16 = 0x0060;
/// Product version in the PnP ID (0xJJMN: 0x0060 = 0.6.0, 0x0070 = 0.7.0).
#[cfg(feature = "board-v07")]
pub const PNP_VERSION: u16 = 0x0070;

// ---------------------------------------------------------------- LED driver

/// LED current at 100 % PWM duty (mA): `I = duty x 3.3 V x R16 / (R15 + R16) / 20 mOhm`.
/// v0.6: R16 = 2 k -> 3235 mA. Calibrate on the bench (section "bring-up" of firmware.md).
#[cfg(not(feature = "board-v07"))]
pub const LED_FULL_SCALE_MA: u32 = 3_235;
/// LED current at 100 % PWM duty (mA): `I = duty x 3.3 V x R16 / (R15 + R16) / 20 mOhm`.
/// v0.7: R16 = 2.2 k -> 3.3 V x 2.2 / 102.2 / 0.020 = 3552 mA (electronics "power" block:
/// TPS62095 buck, TLV333 loop, RS1 20 mOhm). Calibrate on the bench (firmware.md, bring-up).
#[cfg(feature = "board-v07")]
pub const LED_FULL_SCALE_MA: u32 = 3_552;

/// Hard ceiling of the LED current set point (mA). [`crate::hw::led_duty_counts`] - the only
/// function that turns a current into a PWM duty - never goes above it, whatever it is asked
/// for. v0.6: the driver's full scale (the protocol already limits every level to 3000 mA).
#[cfg(not(feature = "board-v07"))]
pub const LED_MAX_MA: u32 = LED_FULL_SCALE_MA;
/// Hard ceiling of the LED current set point (mA). [`crate::hw::led_duty_counts`] - the only
/// function that turns a current into a PWM duty - never goes above it, whatever it is asked
/// for. v0.7: 3000 mA, the maximum DC current of the Luminus SST-20 Gen 2 (datasheet); the
/// driver could deliver 3552 mA. Nothing in the firmware asks for more than [`TURBO_MAX_MA`].
#[cfg(feature = "board-v07")]
pub const LED_MAX_MA: u32 = 3_000;

/// Highest current any level may have: the turbo limit of the Custom profile (protocol section
/// 5, "turbo max") and the largest turbo of the built-in profiles. v0.6: 3000 mA (protocol).
#[cfg(not(feature = "board-v07"))]
pub const TURBO_MAX_MA: u16 = 3_000;
/// Highest current any level may have: the turbo limit of the Custom profile (protocol section
/// 5, "turbo max") and the turbo of the built-in profiles. v0.7: 2850 mA. The current loop's
/// full scale has a tolerance of +-3 % (RSS) and +-5 % (worst case: 3.3 V rail +-2 %, divider
/// and sense resistor 1 %; electronics "power" block), so a 2850 mA set point gives at most
/// 2992 mA: the LED never sees more than its 3.0 A rating. It also keeps the cell current near
/// 2.9 A at most (2.7 A from a full cell); the turbo profiles' 2800 mA cell limit keeps it below the
/// board protection's worst-case trip (3.0-3.15 A with hot MOSFETs; typical 4.3-4.5 A hot). Light out
/// of the front at 2850 mA: 966 lm (LED model below, Tj 85 degC) against 1006 lm at 3000 mA.
#[cfg(feature = "board-v07")]
pub const TURBO_MAX_MA: u16 = 2_850;

/// Worst-case tolerance of the LED current loop's full scale, percent (electronics "power" block).
#[cfg(feature = "board-v07")]
pub const FULL_SCALE_TOL_WORST_PCT: u32 = 5;

// ---------------------------------------------------------------- cells

/// Usable capacity of the pack (runtime estimate), mAh.
/// v0.6: two LP601646 cells in parallel.
#[cfg(not(feature = "board-v07"))]
pub const CELL_CAPACITY_MAH: u32 = 800;
/// Usable capacity of the cell (runtime estimate), mAh.
/// v0.7: one Vapcell INR14500 F15: 1500 mAh typical, 1150 mAh minimum, both at 0.2C to 2.5 V
/// (maker). This light draws 0.4-1.9 A (sustained level to turbo) and stops at 3.0 V under load,
/// which costs a typical cell about 7 % (estimate): 1400 mAh. A cell at the maker's minimum runs
/// about 18 % shorter than the runtime shown.
#[cfg(feature = "board-v07")]
pub const CELL_CAPACITY_MAH: u32 = 1_400;

/// Load correction of the open-circuit voltage estimate, mV per A of cell current (the
/// resistance between the cells and the battery ADC). v0.6: about 0.12 ohm.
#[cfg(not(feature = "board-v07"))]
pub const LOAD_CORR_MV_PER_A: u32 = 120;
/// Load correction of the open-circuit voltage estimate, mV per A of cell current (the
/// resistance between the cell and the battery ADC). v0.7: about 0.13 ohm = the F15's DC
/// resistance, about 90 mOhm (estimated as 1.5 x the maker's 60 mOhm AC value at 1 kHz; not
/// measured) + nickel strips and the 24 AWG pair (about 10 mOhm) + protection MOSFETs
/// (2 x 14 mOhm) + copper (about 4 mOhm); the ADC measures against P- below the MOSFETs.
#[cfg(feature = "board-v07")]
pub const LOAD_CORR_MV_PER_A: u32 = 130;

/// Fast-charge current into the cell, mA (the SoC estimate corrects the measured voltage by it
/// while charging). v0.6: TP4057 with R3 = 3.3 k, about 280 mA.
#[cfg(not(feature = "board-v07"))]
pub const CHARGE_FAST_MA: u32 = 280;
/// Fast-charge current into the cell, mA. v0.7: TP4057 with R3 = 2.0 k, 494 mA (470-530 mA),
/// less about 20 mA for the MCU (the F15's standard charge is 500 mA).
#[cfg(feature = "board-v07")]
pub const CHARGE_FAST_MA: u32 = 475;

/// LED forward voltage model `V_LED = LED_VF0_MV + LED_RS_MOHM x I` (cell current estimate).
/// v0.6: SST-20, 2.75 V + 0.15 V/A.
#[cfg(not(feature = "board-v07"))]
pub const LED_VF0_MV: u32 = 2_750;
/// LED forward voltage model `V_LED = LED_VF0_MV + LED_RS_MOHM x I` (cell current estimate).
/// v0.7: SST-20 Gen 2, 2.80 V + 0.15 V/A (3.0 V at 1.5 A = datasheet typical at Tj 85 degC).
#[cfg(feature = "board-v07")]
pub const LED_VF0_MV: u32 = 2_800;
/// Slope of the forward voltage model, mOhm (both boards).
pub const LED_RS_MOHM: u32 = 150;
/// Driver efficiency in the cell current estimate `V_LED x I / (eff x V_BAT)`, percent.
/// v0.6: 90 %.
#[cfg(not(feature = "board-v07"))]
pub const DRIVER_EFF_PCT: u32 = 90;
/// Driver efficiency in the cell current estimate `V_LED x I / (eff x V_BAT)`, percent.
/// v0.7: 87 % = 9.75 W LED for about 11.2 W from the cells at 3.0 A (buck, inductor, sense
/// resistor, protection MOSFETs, copper: electronics estimate). Lower than the real value at
/// lower currents (about 92 % at 1.7 A), so the estimate errs on the safe side.
#[cfg(feature = "board-v07")]
pub const DRIVER_EFF_PCT: u32 = 87;

/// v0.7: resistance from the battery ADC node to the LED when the buck runs at 100 % duty, mOhm:
/// buck high-side switch (hot) about 62, inductor 23, sense resistor 20, LED wires and copper about
/// 23. With the LED model the buck then delivers at most `(V_BAT - 2.80 V) / (0.15 + 0.128) ohm`
/// (electronics "power" block: 3.0 A down to 3.71 V at the cell pads, 2.5 A at 3.6 V, 1.9 A at 3.4 V;
/// from the pads add the protection MOSFETs and copper, about 32 mOhm). A single cell sags enough
/// under turbo to reach this; the state of charge and runtime estimates use the deliverable current.
#[cfg(feature = "board-v07")]
pub const DROP_PATH_MOHM: u32 = 128;

// ---------------------------------------------------------------- LED flux (v0.7)

/// Flux of the Luminus SST-20 Gen 2, 6500 K, G1 bin, at the LED, Tj 85 degC: `(mA, lm)`,
/// straight lines in between (below 350 mA a straight line to zero).
///
/// * 680 lm at 1500 mA (bin minimum) and 1156 lm at 3000 mA ("for reference") are datasheet
///   values (Luminus SST-20-WS Gen 2, PDS-003350).
/// * 191, 361, 485 and 855 lm are **estimates**: 680 lm x the relative flux of the datasheets of
///   the same die family (SST-20-WE CRI70: 0.713 at 1.0 A and 1.257 at 2.0 A; SST-20-W Gen 1:
///   0.280 at 0.35 A and 0.530 at 0.7 A, each relative to 1.5 A). No Gen 2 curve was available.
///
/// Rating at Tj 85 degC (LuxLibre rule LED-2) is conservative: a cooler LED gives a few percent
/// more (the G1 minimum at 1.5 A is 748 lm at 25 degC).
#[cfg(feature = "board-v07")]
pub const LED_LM_TABLE: [(u16, u16); 7] =
    [(0, 0), (350, 191), (700, 361), (1_000, 485), (1_500, 680), (2_000, 855), (3_000, 1_156)];

/// Part of the LED's light that leaves the front (percent): LEDiL LISA3-RS-PIN with the SST-20
/// Gen 2 = 87 % (LEDiL datasheet FP16558, simulated by LEDiL). There is no front window.
#[cfg(feature = "board-v07")]
pub const OPTIC_PCT: u32 = 87;

/// Estimated flux at the LED, in 0.1 lm (Tj 85 degC; see [`LED_LM_TABLE`]). Currents above
/// the table end at its last point (the ceiling is 3000 mA anyway).
#[cfg(feature = "board-v07")]
pub fn led_lumens_x10(ma: u16) -> u32 {
    let ma = (ma as u32).min(LED_LM_TABLE[LED_LM_TABLE.len() - 1].0 as u32);
    let mut i = 1;
    while i < LED_LM_TABLE.len() - 1 && ma > LED_LM_TABLE[i].0 as u32 {
        i += 1;
    }
    let (a0, l0) = (LED_LM_TABLE[i - 1].0 as u32, LED_LM_TABLE[i - 1].1 as u32);
    let (a1, l1) = (LED_LM_TABLE[i].0 as u32, LED_LM_TABLE[i].1 as u32);
    // 10 x (l0 + (l1 - l0) x (ma - a0) / (a1 - a0)), rounded
    (10 * l0 * (a1 - a0) + 10 * (l1 - l0) * (ma - a0) + (a1 - a0) / 2) / (a1 - a0)
}

/// Estimated light out of the front, in 0.1 lm: [`led_lumens_x10`] x [`OPTIC_PCT`].
#[cfg(feature = "board-v07")]
pub fn front_lumens_x10(ma: u16) -> u32 {
    (led_lumens_x10(ma) * OPTIC_PCT + 50) / 100
}

/// Estimated light out of the front, whole lumens (rounded once, from [`led_lumens_x10`]).
#[cfg(feature = "board-v07")]
pub fn front_lumens(ma: u16) -> u32 {
    (led_lumens_x10(ma) * OPTIC_PCT + 500) / 1_000
}

// No built-in level and no Custom value can ask for more than TURBO_MAX_MA, and that stays
// below the LED ceiling: checked when the firmware is compiled (a failed check stops the
// build). `hw::led_duty_counts` enforces the ceiling at run time as well, whatever it is asked.
const _: () = {
    use crate::profile::{Profile, limits};
    assert!(LED_MAX_MA <= LED_FULL_SCALE_MA);
    assert!(TURBO_MAX_MA as u32 <= LED_MAX_MA);
    assert!(limits::TURBO_MAX == TURBO_MAX_MA && limits::HIGH_MAX <= TURBO_MAX_MA);
    // v0.7: even at the worst-case tolerance of the current loop the LED stays within 3.0 A
    #[cfg(feature = "board-v07")]
    assert!(TURBO_MAX_MA as u32 * (100 + FULL_SCALE_TOL_WORST_PCT) <= LED_MAX_MA * 100);
    let all = [Profile::EXTREME, Profile::BALANCED, Profile::ENDURANCE];
    let mut i = 0;
    while i < all.len() {
        let p = all[i];
        assert!(p.turbo_ma <= TURBO_MAX_MA && p.high_ma <= TURBO_MAX_MA && p.stepdown_ma <= TURBO_MAX_MA);
        assert!(p.cell_limit_ma <= limits::CELL_LIMIT_MA.1);
        i += 1;
    }
};

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn version_texts_agree() {
        assert!(INFO_TEXT.len() <= crate::protocol::INFO_MAX_LEN);
        assert!(INFO_TEXT.ends_with(FW_VERSION), "{INFO_TEXT} / {FW_VERSION}");
        let mut parts = FW_VERSION.split('.').map(|p| p.parse::<u16>().unwrap());
        let (major, minor, patch) = (parts.next().unwrap(), parts.next().unwrap(), parts.next().unwrap());
        assert_eq!(PNP_VERSION, (major << 8) | (minor << 4) | patch);
        // the firmware crate's version stays the v0.6 one (Cargo.toml); the v0.6 image is unchanged
        #[cfg(not(feature = "board-v07"))]
        assert_eq!(FW_VERSION, env!("CARGO_PKG_VERSION"));
        #[cfg(feature = "board-v07")]
        assert_eq!((FW_VERSION, INFO_TEXT, BOARD_NAME), ("0.7.0", "FlashKa fw 0.7.0", "FlashKa Keychain v0.7"));
    }

    #[test]
    fn ceiling_never_above_full_scale() {
        assert!(LED_MAX_MA <= LED_FULL_SCALE_MA);
        assert!(TURBO_MAX_MA as u32 <= LED_MAX_MA);
        #[cfg(not(feature = "board-v07"))]
        assert_eq!((LED_FULL_SCALE_MA, LED_MAX_MA, TURBO_MAX_MA), (3_235, 3_235, 3_000), "v0.6 unchanged");
        #[cfg(feature = "board-v07")]
        {
            assert_eq!(LED_MAX_MA, 3_000, "SST-20 Gen 2: 3.0 A DC maximum");
            // 3.3 V x 2.2 k / 102.2 k / 20 mOhm
            let fs = 3.3 * 2.2 / 102.2 / 0.020 * 1000.0;
            assert!((fs - LED_FULL_SCALE_MA as f64).abs() < 1.0, "{fs}");
            // the highest set point with the full scale 5 % high (worst case) stays within 3.0 A
            // (a 3000 mA set point could give 3150 mA); the electronics suggested 2850 mA for this
            assert_eq!(TURBO_MAX_MA, 2_850);
            let worst = TURBO_MAX_MA as u32 * (100 + FULL_SCALE_TOL_WORST_PCT) / 100;
            assert_eq!(worst, 2_992);
            assert!(worst <= LED_MAX_MA);
        }
    }

    #[cfg(feature = "board-v07")]
    #[test]
    fn led_model_anchors_and_shape() {
        // datasheet anchors (Tj 85 degC, G1)
        assert_eq!(led_lumens_x10(1_500), 6_800);
        assert_eq!(led_lumens_x10(3_000), 11_560);
        // out of the front: 87 %
        assert_eq!(front_lumens(3_000), 1_006);
        assert_eq!(front_lumens(TURBO_MAX_MA), 966);
        assert_eq!(front_lumens(1_500), 592);
        assert_eq!(front_lumens(0), 0);
        // above the table: held at the last point
        assert_eq!(led_lumens_x10(u16::MAX), 11_560);
        // monotonic, and lumens per ampere fall with the current (droop)
        let mut last = 0;
        let mut last_eff = u32::MAX;
        for ma in (50..=3_000u16).step_by(50) {
            let lm = led_lumens_x10(ma);
            assert!(lm > last, "{ma}");
            last = lm;
            let eff = lm * 1_000 / ma as u32; // 0.1 lm per A
            assert!(eff <= last_eff.saturating_add(1), "efficacy rises at {ma} mA");
            last_eff = eff;
        }
        // the points of the table are hit exactly
        for (ma, lm) in LED_LM_TABLE {
            assert_eq!(led_lumens_x10(ma), lm as u32 * 10);
        }
        // the estimated points agree with the datasheet ratios they come from (+-1 lm)
        let est = |ratio: f64| (680.0 * ratio).round() as u32;
        assert_eq!(led_lumens_x10(1_000) / 10, est(422.0 / 592.0)); // SST-20-WE 1.0 A / 1.5 A
        assert_eq!(led_lumens_x10(2_000) / 10, est(744.0 / 592.0)); // SST-20-WE 2.0 A / 1.5 A
        assert_eq!(led_lumens_x10(700) / 10, est(297.0 / 560.0)); // SST-20-W Gen 1 L3 0.7 A / 1.5 A
        assert_eq!(led_lumens_x10(350) / 10, est(157.0 / 560.0)); // Gen 1 L3 0.35 A (85 degC) / 1.5 A
    }
}
