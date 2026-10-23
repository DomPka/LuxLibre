// SPDX-License-Identifier: MIT OR Apache-2.0
//! Brightness levels, the built-in profiles and the Custom profile with its
//! clamping rules (`docs/ble_protocol.md` section 5).

use crate::protocol::{CmdError, PROFILE_LEN};

/// Brightness level (Status byte 3, LEVEL command argument).
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
#[repr(u8)]
pub enum Level {
    Moon = 0,
    Low = 1,
    Medium = 2,
    High = 3,
    Turbo = 4,
}

impl Level {
    pub fn from_u8(v: u8) -> Option<Level> {
        Some(match v {
            0 => Level::Moon,
            1 => Level::Low,
            2 => Level::Medium,
            3 => Level::High,
            4 => Level::Turbo,
            _ => return None,
        })
    }

    /// One step down (used by the low-voltage protection).
    pub fn step_down(self) -> Level {
        match self {
            Level::Turbo => Level::High,
            Level::High => Level::Medium,
            Level::Medium => Level::Low,
            Level::Low | Level::Moon => Level::Moon,
        }
    }

    /// Next level when stepping with the button held: Low -> Medium -> High -> Low.
    /// Moon and Turbo continue at Low.
    pub fn next_in_cycle(self) -> Level {
        match self {
            Level::Low => Level::Medium,
            Level::Medium => Level::High,
            Level::High | Level::Moon | Level::Turbo => Level::Low,
        }
    }

    /// Levels that can be remembered for the next switch-on (never Turbo).
    pub fn is_memorable(self) -> bool {
        self != Level::Turbo
    }

    /// › while the light is on: Moon -> Low -> Medium -> High, no wrap; never
    /// into Turbo (turbo only by the double click). `None` = no change.
    pub fn slide_up(self) -> Option<Level> {
        match self {
            Level::Moon => Some(Level::Low),
            Level::Low => Some(Level::Medium),
            Level::Medium => Some(Level::High),
            Level::High | Level::Turbo => None,
        }
    }

    /// ‹ while the light is on: High -> Medium -> Low -> Moon, no wrap; from
    /// Turbo to High. `None` = no change.
    pub fn slide_down(self) -> Option<Level> {
        match self {
            Level::Turbo => Some(Level::High),
            Level::High => Some(Level::Medium),
            Level::Medium => Some(Level::Low),
            Level::Low => Some(Level::Moon),
            Level::Moon => None,
        }
    }
}

/// Profile id (Status byte 2, PROFILE command argument, Profile byte 0).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(u8)]
pub enum ProfileId {
    Extreme = 0,
    Balanced = 1,
    Endurance = 2,
    Custom = 3,
}

impl ProfileId {
    pub fn from_u8(v: u8) -> Option<ProfileId> {
        Some(match v {
            0 => ProfileId::Extreme,
            1 => ProfileId::Balanced,
            2 => ProfileId::Endurance,
            3 => ProfileId::Custom,
            _ => return None,
        })
    }
}

/// Profile flag bit 0: turbo allowed.
pub const FLAG_TURBO: u8 = 0x01;
/// Profile flag bit 1: switch on at the last used level.
pub const FLAG_MEMORY: u8 = 0x02;
/// Profile flag bit 2: show the battery on the RGB LED when switched on.
pub const FLAG_SHOW_BATTERY: u8 = 0x04;
/// All defined flag bits.
pub const FLAGS_MASK: u8 = FLAG_TURBO | FLAG_MEMORY | FLAG_SHOW_BATTERY;

/// Clamping ranges of the Custom profile (section 5). `(min, max)`; the
/// minimum of a level is the level below it.
pub mod limits {
    pub const MOON: (u16, u16) = (1, 50);
    pub const LOW_MAX: u16 = 300;
    pub const MEDIUM_MAX: u16 = 1_000;
    pub const HIGH_MAX: u16 = 2_000;
    /// v0.6: 3000 mA (protocol); v0.7: 2850 mA ([`crate::board::TURBO_MAX_MA`]).
    pub const TURBO_MAX: u16 = crate::board::TURBO_MAX_MA;
    pub const TURBO_TIME_S: (u16, u16) = (0, 300);
    pub const TEMP_LIMIT_C: (u8, u8) = (40, 70);
    pub const LV_STEPDOWN: (u8, u8) = (10, 60);
    pub const CELL_LIMIT_MA: (u16, u16) = (200, 3_000);
}

/// The parameters of one profile (the 20-byte Profile packet without the id).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Profile {
    pub flags: u8,
    pub moon_ma: u16,
    pub low_ma: u16,
    pub medium_ma: u16,
    pub high_ma: u16,
    pub turbo_ma: u16,
    /// Turbo time limit, s (0 = turbo is the same as High).
    pub turbo_time_s: u16,
    /// Current after the turbo time has run out, mA.
    pub stepdown_ma: u16,
    /// Output is reduced above this board temperature, degC.
    pub temp_limit_c: u8,
    /// Low-voltage step-down threshold in 10 mV steps above 3.00 V.
    pub lv_stepdown: u8,
    /// Battery-side current limit, mA.
    pub cell_limit_ma: u16,
}

// The built-in profiles depend on the board ([`crate::board`]): v0.6 keeps the tables of
// firmware 0.6.0; v0.7 has its own (SST-20 Gen 2 behind a TIR optic, one 14500 cell (F15),
// 3.0 A LED ceiling, 2850 mA turbo). Light out of the front from the LED model,
// `board::front_lumens` (Tj 85 degC). The tables are checked against the LED ceiling when the
// firmware is compiled (board.rs).
//
// v0.7 temperature limits: on the v0.7 board the limit is the set point of the thermal regulator
// ([`crate::thermal`]): the sensor (NTC, near the driver, following the head) is held at or just
// below it, instead of the protocol's linear reduction to Low over 15 degC that v0.6 keeps. 50 degC
// at the sensor keeps the simulated body (the surface held in the hand) at about 46.5 degC in
// 25 degC still air, inside the 48 degC continuous touch limit (LuxLibre THM-1), and the head at
// or below 51 degC on the way there. The simulation is in tests/thermal_v07.rs; the numbers must be
// checked on a real light (THM-6).
//
// v0.7 cell limit 2800 mA (Extreme, Balanced): one Vapcell INR14500 F15, rated 3 A continuous.
// 2800 mA is 93 % of that, above the 70 % of LuxLibre BAT-1 (2100 mA): a documented deviation,
// because only turbo comes near it and turbo lasts at most 60 s and is thermally regulated (High
// draws 1.3-1.7 A, the sustained level about 0.7 A). It also stays 7-12 % below the board
// protection's worst-case trip (DW01A + SE8830A: 3.0-3.15 A hot; typical 4.3-4.5 A hot); a trip
// latches: the light is off until USB power is applied. A full cell gives the whole 2850 mA turbo
// (about 2.7 A from the cell); a half-full one cannot (the cell sags, the buck runs out of headroom).
//
// v0.7 low-voltage step-down 3.15 / 3.20 / 3.25 V (under load): the F15's open-circuit voltage is
// lower than a LiPo's over most of the charge (3.68 V at 50 %, battery.rs) and one cell sags more
// (0.13 ohm), so the v0.6-style 3.30-3.40 V would cut in with 10-20 % still in the cell. These
// values start the step-down at about 5-10 % left; Moon below 3.10 V and off below 3.00 V stay
// (the F15 may go to 2.5 V).
//
// v0.7 Endurance temperature limit 47 degC (was 45): with the MCU's own heat and the cell's in the
// model, its 500 mA High settles the sensor at about 45.3 degC in 25 degC still air; 47 degC keeps
// the regulator out of the way there (body about 42 degC).
impl Profile {
    /// Extreme: short bursts, 2.2 A turbo for 45 s.
    #[cfg(not(feature = "board-v07"))]
    pub const EXTREME: Profile = Profile {
        flags: FLAG_TURBO | FLAG_MEMORY | FLAG_SHOW_BATTERY,
        moon_ma: 3,
        low_ma: 40,
        medium_ma: 250,
        high_ma: 900,
        turbo_ma: 2_200,
        turbo_time_s: 45,
        stepdown_ma: 900,
        temp_limit_c: 55,
        lv_stepdown: 30,
        cell_limit_ma: 2_600,
    };

    /// Balanced (default): 1.2 A turbo for 60 s.
    #[cfg(not(feature = "board-v07"))]
    pub const BALANCED: Profile = Profile {
        flags: FLAG_TURBO | FLAG_MEMORY | FLAG_SHOW_BATTERY,
        moon_ma: 3,
        low_ma: 30,
        medium_ma: 200,
        high_ma: 600,
        turbo_ma: 1_200,
        turbo_time_s: 60,
        stepdown_ma: 600,
        temp_limit_c: 50,
        lv_stepdown: 35,
        cell_limit_ma: 1_600,
    };

    /// Endurance: never above 300 mA, no turbo ("turbo = High").
    #[cfg(not(feature = "board-v07"))]
    pub const ENDURANCE: Profile = Profile {
        flags: FLAG_MEMORY | FLAG_SHOW_BATTERY,
        moon_ma: 2,
        low_ma: 15,
        medium_ma: 100,
        high_ma: 300,
        turbo_ma: 300,
        turbo_time_s: 0,
        stepdown_ma: 300,
        temp_limit_c: 45,
        lv_stepdown: 40,
        cell_limit_ma: 800,
    };

    /// Extreme (v0.7): brighter levels - 2850 mA turbo (about 966 lm out of the front) for at
    /// most 60 s, High and the level after turbo 1.8 A (about 683 lm), Medium 400 mA (187 lm).
    /// Same 50 degC limit as Balanced: the regulator holds it whatever the level.
    #[cfg(feature = "board-v07")]
    pub const EXTREME: Profile = Profile {
        flags: FLAG_TURBO | FLAG_MEMORY | FLAG_SHOW_BATTERY,
        moon_ma: 3,
        low_ma: 50,
        medium_ma: 400,
        high_ma: 1_800,
        turbo_ma: 2_850,
        turbo_time_s: 60,
        stepdown_ma: 1_800,
        temp_limit_c: 50,
        lv_stepdown: 15,
        cell_limit_ma: 2_800,
    };

    /// Balanced (v0.7, default): 2850 mA turbo (about 966 lm out of the front) for at most 60 s,
    /// then High 1.53 A (about 600 lm) for as long as the temperature allows.
    #[cfg(feature = "board-v07")]
    pub const BALANCED: Profile = Profile {
        flags: FLAG_TURBO | FLAG_MEMORY | FLAG_SHOW_BATTERY,
        moon_ma: 3,
        low_ma: 40,
        medium_ma: 250,
        high_ma: 1_530,
        turbo_ma: 2_850,
        turbo_time_s: 60,
        stepdown_ma: 1_530,
        temp_limit_c: 50,
        lv_stepdown: 20,
        cell_limit_ma: 2_800,
    };

    /// Endurance (v0.7): no turbo, High 0.5 A (about 230 lm), a level the body can shed in still
    /// air at 25 degC without stepping down.
    #[cfg(feature = "board-v07")]
    pub const ENDURANCE: Profile = Profile {
        flags: FLAG_MEMORY | FLAG_SHOW_BATTERY,
        moon_ma: 2,
        low_ma: 15,
        medium_ma: 100,
        high_ma: 500,
        turbo_ma: 500,
        turbo_time_s: 0,
        stepdown_ma: 500,
        temp_limit_c: 47,
        lv_stepdown: 25,
        cell_limit_ma: 800,
    };

    /// Factory default of the Custom profile (= Balanced).
    pub const CUSTOM_DEFAULT: Profile = Profile::BALANCED;

    /// Built-in profile for an id (`None` for Custom).
    pub fn builtin(id: ProfileId) -> Option<Profile> {
        match id {
            ProfileId::Extreme => Some(Profile::EXTREME),
            ProfileId::Balanced => Some(Profile::BALANCED),
            ProfileId::Endurance => Some(Profile::ENDURANCE),
            ProfileId::Custom => None,
        }
    }

    /// Clamp every value to the safe range of section 5. Each level's minimum is
    /// the (already clamped) level below it, so the result is always ordered.
    pub fn clamped(self) -> Profile {
        let moon = self.moon_ma.clamp(limits::MOON.0, limits::MOON.1);
        let low = self.low_ma.clamp(moon, limits::LOW_MAX);
        let medium = self.medium_ma.clamp(low, limits::MEDIUM_MAX);
        let high = self.high_ma.clamp(medium, limits::HIGH_MAX);
        let turbo = self.turbo_ma.clamp(high, limits::TURBO_MAX);
        Profile {
            flags: self.flags & FLAGS_MASK,
            moon_ma: moon,
            low_ma: low,
            medium_ma: medium,
            high_ma: high,
            turbo_ma: turbo,
            turbo_time_s: self
                .turbo_time_s
                .clamp(limits::TURBO_TIME_S.0, limits::TURBO_TIME_S.1),
            stepdown_ma: self.stepdown_ma.clamp(low, high),
            temp_limit_c: self
                .temp_limit_c
                .clamp(limits::TEMP_LIMIT_C.0, limits::TEMP_LIMIT_C.1),
            lv_stepdown: self
                .lv_stepdown
                .clamp(limits::LV_STEPDOWN.0, limits::LV_STEPDOWN.1),
            cell_limit_ma: self
                .cell_limit_ma
                .clamp(limits::CELL_LIMIT_MA.0, limits::CELL_LIMIT_MA.1),
        }
    }

    /// Turbo exists: flag set, a time limit > 0 and a turbo current above High.
    pub fn has_turbo(&self) -> bool {
        self.flags & FLAG_TURBO != 0 && self.turbo_time_s > 0 && self.turbo_ma > self.high_ma
    }

    /// Nominal current of a level (Turbo is High when the profile has no turbo).
    pub fn level_ma(&self, level: Level) -> u16 {
        match level {
            Level::Moon => self.moon_ma,
            Level::Low => self.low_ma,
            Level::Medium => self.medium_ma,
            Level::High => self.high_ma,
            Level::Turbo => {
                if self.has_turbo() {
                    self.turbo_ma
                } else {
                    self.high_ma
                }
            }
        }
    }

    /// Highest current the app may request with OUTPUT_MA.
    pub fn max_output_ma(&self) -> u16 {
        self.level_ma(Level::Turbo)
    }

    /// Low-voltage step-down threshold, mV.
    pub fn lv_stepdown_mv(&self) -> u16 {
        3_000 + 10 * self.lv_stepdown as u16
    }

    /// Temperature limit in 0.1 degC.
    pub fn temp_limit_dc(&self) -> i16 {
        self.temp_limit_c as i16 * 10
    }

    /// Highest level whose nominal current does not exceed `ma`.
    pub fn level_for_current(&self, ma: u16) -> Level {
        if self.has_turbo() && ma >= self.turbo_ma {
            Level::Turbo
        } else if ma >= self.high_ma {
            Level::High
        } else if ma >= self.medium_ma {
            Level::Medium
        } else if ma >= self.low_ma {
            Level::Low
        } else {
            Level::Moon
        }
    }

    /// Encode as the 20-byte Profile packet.
    pub fn encode(&self, id: ProfileId) -> [u8; PROFILE_LEN] {
        let mut b = [0u8; PROFILE_LEN];
        b[0] = id as u8;
        b[1] = self.flags;
        b[2..4].copy_from_slice(&self.moon_ma.to_le_bytes());
        b[4..6].copy_from_slice(&self.low_ma.to_le_bytes());
        b[6..8].copy_from_slice(&self.medium_ma.to_le_bytes());
        b[8..10].copy_from_slice(&self.high_ma.to_le_bytes());
        b[10..12].copy_from_slice(&self.turbo_ma.to_le_bytes());
        b[12..14].copy_from_slice(&self.turbo_time_s.to_le_bytes());
        b[14..16].copy_from_slice(&self.stepdown_ma.to_le_bytes());
        b[16] = self.temp_limit_c;
        b[17] = self.lv_stepdown;
        b[18..20].copy_from_slice(&self.cell_limit_ma.to_le_bytes());
        b
    }

    /// Decode the raw fields of a 20-byte packet (no checks, no clamping).
    pub fn decode_raw(b: &[u8; PROFILE_LEN]) -> (u8, Profile) {
        let u = |i: usize| u16::from_le_bytes([b[i], b[i + 1]]);
        (
            b[0],
            Profile {
                flags: b[1],
                moon_ma: u(2),
                low_ma: u(4),
                medium_ma: u(6),
                high_ma: u(8),
                turbo_ma: u(10),
                turbo_time_s: u(12),
                stepdown_ma: u(14),
                temp_limit_c: b[16],
                lv_stepdown: b[17],
                cell_limit_ma: u(18),
            },
        )
    }

    /// Validate and clamp a Profile characteristic write: exactly 20 bytes and
    /// byte 0 = 3 (Custom), otherwise `0x81`.
    pub fn decode_write(data: &[u8]) -> Result<Profile, CmdError> {
        let b: &[u8; PROFILE_LEN] = data.try_into().map_err(|_| CmdError::Invalid)?;
        let (id, p) = Profile::decode_raw(b);
        if id != ProfileId::Custom as u8 {
            return Err(CmdError::Invalid);
        }
        Ok(p.clamped())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[cfg(not(feature = "board-v07"))]
    #[test]
    fn builtins_match_protocol_table() {
        let e = Profile::EXTREME;
        assert_eq!((e.moon_ma, e.low_ma, e.medium_ma, e.high_ma), (3, 40, 250, 900));
        assert_eq!((e.turbo_ma, e.turbo_time_s, e.stepdown_ma), (2_200, 45, 900));
        assert_eq!((e.temp_limit_c, e.lv_stepdown_mv(), e.cell_limit_ma), (55, 3_300, 2_600));
        let b = Profile::BALANCED;
        assert_eq!((b.moon_ma, b.low_ma, b.medium_ma, b.high_ma), (3, 30, 200, 600));
        assert_eq!((b.turbo_ma, b.turbo_time_s, b.stepdown_ma), (1_200, 60, 600));
        assert_eq!((b.temp_limit_c, b.lv_stepdown_mv(), b.cell_limit_ma), (50, 3_350, 1_600));
        let n = Profile::ENDURANCE;
        assert_eq!((n.moon_ma, n.low_ma, n.medium_ma, n.high_ma), (2, 15, 100, 300));
        assert!(!n.has_turbo());
        assert_eq!(n.level_ma(Level::Turbo), 300);
        assert_eq!((n.temp_limit_c, n.lv_stepdown_mv(), n.cell_limit_ma), (45, 3_400, 800));
        assert_eq!(Profile::CUSTOM_DEFAULT, Profile::BALANCED);
        // built-ins are already inside the clamping ranges
        for p in [Profile::EXTREME, Profile::BALANCED, Profile::ENDURANCE] {
            assert_eq!(p.clamped(), p);
        }
        assert!(Profile::EXTREME.has_turbo() && Profile::BALANCED.has_turbo());
    }

    /// v0.7 board: the table of docs/firmware.md (section "FlashKa v0.7").
    #[cfg(feature = "board-v07")]
    #[test]
    fn builtins_match_protocol_table() {
        let e = Profile::EXTREME;
        assert_eq!((e.moon_ma, e.low_ma, e.medium_ma, e.high_ma), (3, 50, 400, 1_800));
        assert_eq!((e.turbo_ma, e.turbo_time_s, e.stepdown_ma), (2_850, 60, 1_800));
        assert_eq!((e.temp_limit_c, e.lv_stepdown_mv(), e.cell_limit_ma), (50, 3_150, 2_800));
        let b = Profile::BALANCED;
        assert_eq!((b.moon_ma, b.low_ma, b.medium_ma, b.high_ma), (3, 40, 250, 1_530));
        assert_eq!((b.turbo_ma, b.turbo_time_s, b.stepdown_ma), (2_850, 60, 1_530));
        assert_eq!((b.temp_limit_c, b.lv_stepdown_mv(), b.cell_limit_ma), (50, 3_200, 2_800));
        let n = Profile::ENDURANCE;
        assert_eq!((n.moon_ma, n.low_ma, n.medium_ma, n.high_ma), (2, 15, 100, 500));
        assert!(!n.has_turbo());
        assert_eq!(n.level_ma(Level::Turbo), 500);
        assert_eq!((n.temp_limit_c, n.lv_stepdown_mv(), n.cell_limit_ma), (47, 3_250, 800));
        assert_eq!(Profile::CUSTOM_DEFAULT, Profile::BALANCED);
        for p in [Profile::EXTREME, Profile::BALANCED, Profile::ENDURANCE] {
            assert_eq!(p.clamped(), p);
        }
        assert!(Profile::EXTREME.has_turbo() && Profile::BALANCED.has_turbo());
    }

    /// v0.7 levels in light out of the front (LED model at Tj 85 degC x the 87 % optic): useful
    /// steps from moonlight to turbo, High about 600 lm, turbo 966 lm (about 1000 lm).
    #[cfg(feature = "board-v07")]
    #[test]
    fn v07_level_lumens() {
        use crate::board::{front_lumens, front_lumens_x10};
        let b = Profile::BALANCED;
        let lm: Vec<u32> = [b.moon_ma, b.low_ma, b.medium_ma, b.high_ma, b.turbo_ma]
            .iter()
            .map(|&ma| front_lumens(ma))
            .collect();
        assert_eq!(lm, [1, 19, 119, 601, 966]);
        assert_eq!(front_lumens_x10(b.moon_ma), 14, "moonlight 3 mA = 1.4 lm");
        assert!(front_lumens(b.high_ma) >= 600, "High ~600 lm out of the front");
        // every step is a clearly visible change (at least 1.6 x) and they grow from Moon up
        for w in lm.windows(2) {
            assert!(w[1] * 10 >= w[0] * 16, "{lm:?}");
        }
        let e = Profile::EXTREME;
        assert_eq!(
            [e.moon_ma, e.low_ma, e.medium_ma, e.high_ma, e.turbo_ma].map(front_lumens),
            [1, 24, 187, 683, 966]
        );
        let n = Profile::ENDURANCE;
        assert_eq!([n.moon_ma, n.low_ma, n.medium_ma, n.high_ma].map(front_lumens), [1, 7, 48, 230]);
        // no level above 2850 mA (3.0 A ceiling less the 5 % worst-case tolerance), turbo where
        // the profile has one is the full 2850 mA, no cell limit above 2800 mA (7 % below the board
        // protection's lowest worst-case trip, 3.0 A hot)
        for p in [e, b, n] {
            let top = p.level_ma(Level::Turbo).max(p.high_ma).max(p.stepdown_ma);
            assert!(top <= crate::board::TURBO_MAX_MA && top as u32 <= crate::board::LED_MAX_MA);
            assert!(p.cell_limit_ma <= 2_800);
        }
        assert_eq!((e.turbo_ma, b.turbo_ma), (crate::board::TURBO_MAX_MA, crate::board::TURBO_MAX_MA));
    }

    #[test]
    fn slide_stepping_no_wrap() {
        use Level::*;
        assert_eq!(Moon.slide_up(), Some(Low));
        assert_eq!(Low.slide_up(), Some(Medium));
        assert_eq!(Medium.slide_up(), Some(High));
        assert_eq!(High.slide_up(), None, "no wrap, no turbo");
        assert_eq!(Turbo.slide_up(), None);
        assert_eq!(Turbo.slide_down(), Some(High));
        assert_eq!(High.slide_down(), Some(Medium));
        assert_eq!(Medium.slide_down(), Some(Low));
        assert_eq!(Low.slide_down(), Some(Moon));
        assert_eq!(Moon.slide_down(), None, "no wrap");
    }

    #[test]
    fn encode_layout() {
        let b = Profile::EXTREME.encode(ProfileId::Extreme);
        assert_eq!(b.len(), 20);
        assert_eq!(b[0], 0);
        assert_eq!(b[1], 0x07);
        #[cfg(not(feature = "board-v07"))]
        let (turbo, time, temp, lv, cell) = (2_200, 45, 55, 30, 2_600);
        #[cfg(feature = "board-v07")]
        let (turbo, time, temp, lv, cell) = (2_850, 60, 50, 15, 2_800);
        assert_eq!(u16::from_le_bytes([b[10], b[11]]), turbo);
        assert_eq!(u16::from_le_bytes([b[12], b[13]]), time);
        assert_eq!(b[16], temp);
        assert_eq!(b[17], lv);
        assert_eq!(u16::from_le_bytes([b[18], b[19]]), cell);
        let (id, p) = Profile::decode_raw(&b);
        assert_eq!((id, p), (0, Profile::EXTREME));
    }

    #[test]
    fn clamping() {
        let wild = Profile {
            flags: 0xff,
            moon_ma: 0,
            low_ma: 0,
            medium_ma: 5_000,
            high_ma: 10,
            turbo_ma: 65_000,
            turbo_time_s: 1_000,
            stepdown_ma: 0,
            temp_limit_c: 99,
            lv_stepdown: 0,
            cell_limit_ma: 50,
        };
        let c = wild.clamped();
        assert_eq!(c.flags, 0x07);
        assert_eq!(c.moon_ma, 1);
        assert_eq!(c.low_ma, 1);
        assert_eq!(c.medium_ma, 1_000);
        assert_eq!(c.high_ma, 1_000); // below Medium -> raised to Medium
        #[cfg(not(feature = "board-v07"))]
        assert_eq!(c.turbo_ma, 3_000);
        #[cfg(feature = "board-v07")]
        assert_eq!(c.turbo_ma, 2_850, "v0.7: turbo clamped to 2850 mA");
        assert_eq!(c.turbo_time_s, 300);
        assert_eq!(c.stepdown_ma, 1); // Low..High
        assert_eq!(c.temp_limit_c, 70);
        assert_eq!(c.lv_stepdown, 10);
        assert_eq!(c.cell_limit_ma, 200);
        // monotonic after clamping
        assert!(c.moon_ma <= c.low_ma && c.low_ma <= c.medium_ma);
        assert!(c.medium_ma <= c.high_ma && c.high_ma <= c.turbo_ma);
        assert_eq!(c.clamped(), c, "clamping is idempotent");

        let mut p = Profile::BALANCED;
        p.moon_ma = 60;
        p.low_ma = 20;
        p.stepdown_ma = 5_000;
        p.temp_limit_c = 10;
        p.lv_stepdown = 200;
        p.cell_limit_ma = 9_000;
        let c = p.clamped();
        assert_eq!((c.moon_ma, c.low_ma), (50, 50));
        assert_eq!(c.stepdown_ma, c.high_ma);
        assert_eq!((c.temp_limit_c, c.lv_stepdown, c.cell_limit_ma), (40, 60, 3_000));
    }

    #[test]
    fn decode_write_rules() {
        let mut pkt = Profile::BALANCED.encode(ProfileId::Custom);
        assert_eq!(Profile::decode_write(&pkt), Ok(Profile::BALANCED));
        pkt[0] = 1;
        assert_eq!(Profile::decode_write(&pkt), Err(CmdError::Invalid));
        assert_eq!(Profile::decode_write(&pkt[..19]), Err(CmdError::Invalid));
        let mut long = [0u8; 21];
        long[0] = 3;
        assert_eq!(Profile::decode_write(&long), Err(CmdError::Invalid));
        let mut pkt = Profile::BALANCED.encode(ProfileId::Custom);
        pkt[10..12].copy_from_slice(&9_999u16.to_le_bytes());
        #[cfg(not(feature = "board-v07"))]
        assert_eq!(Profile::decode_write(&pkt).unwrap().turbo_ma, 3_000);
        #[cfg(feature = "board-v07")]
        assert_eq!(Profile::decode_write(&pkt).unwrap().turbo_ma, 2_850);
        // 3000 mA, the LED's datasheet maximum, is not accepted on the v0.7 board either
        #[cfg(feature = "board-v07")]
        {
            pkt[10..12].copy_from_slice(&3_000u16.to_le_bytes());
            assert_eq!(Profile::decode_write(&pkt).unwrap().turbo_ma, 2_850);
        }
    }

    #[test]
    fn turbo_rules() {
        let mut p = Profile::BALANCED;
        assert_eq!(p.max_output_ma(), p.turbo_ma); // v0.6: 1200 mA, v0.7: 2850 mA
        p.turbo_time_s = 0;
        assert!(!p.has_turbo());
        assert_eq!(p.level_ma(Level::Turbo), p.high_ma);
        assert_eq!(p.max_output_ma(), p.high_ma);
        let mut p = Profile::BALANCED;
        p.flags &= !FLAG_TURBO;
        assert!(!p.has_turbo());
    }

    #[test]
    fn level_steps() {
        assert_eq!(Level::Low.next_in_cycle(), Level::Medium);
        assert_eq!(Level::Medium.next_in_cycle(), Level::High);
        assert_eq!(Level::High.next_in_cycle(), Level::Low);
        assert_eq!(Level::Moon.next_in_cycle(), Level::Low);
        assert_eq!(Level::Turbo.next_in_cycle(), Level::Low);
        assert_eq!(Level::Turbo.step_down(), Level::High);
        assert_eq!(Level::Moon.step_down(), Level::Moon);
        // v0.6 Balanced: 1200 / 700 / 200 / 29 mA
        let p = Profile::BALANCED;
        assert_eq!(p.level_for_current(p.turbo_ma), Level::Turbo);
        assert_eq!(p.level_for_current(p.high_ma + 100), Level::High);
        assert_eq!(p.level_for_current(p.medium_ma), Level::Medium);
        assert_eq!(p.level_for_current(p.low_ma - 1), Level::Moon);
    }
}
