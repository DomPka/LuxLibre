// SPDX-License-Identifier: MIT OR Apache-2.0
//! Protection rules (`docs/ble_protocol.md` section 6).

use crate::config::{
    LASER_MAX_TEMP_DC, LASER_MIN_MV, LV_MOON_DELAY_MS, LV_MOON_MV, LV_OFF_DELAY_MS, LV_OFF_MV,
    LV_STEP_PERIOD_MS, THERMAL_DERATE_SPAN_DC, THERMAL_MOON_DC, THERMAL_OFF_DC,
};
use crate::hw::TempReading;
use crate::profile::Level;

/// Thermal current limit.
///
/// Above the profile limit the current falls linearly from the requested value
/// to Low over 15 degC; above 70 degC it is limited to Moon; above 80 degC the
/// light must be switched off (returns 0).
pub fn thermal_cap_ma(temp_dc: i16, limit_dc: i16, requested_ma: u16, low_ma: u16, moon_ma: u16) -> u16 {
    if temp_dc > THERMAL_OFF_DC {
        return 0;
    }
    let mut cap = requested_ma;
    if temp_dc > limit_dc && requested_ma > low_ma {
        let over = (temp_dc - limit_dc) as i32;
        if over >= THERMAL_DERATE_SPAN_DC {
            cap = low_ma;
        } else {
            let span = (requested_ma - low_ma) as i32;
            cap = (requested_ma as i32 - span * over / THERMAL_DERATE_SPAN_DC) as u16;
        }
    }
    if temp_dc > THERMAL_MOON_DC {
        cap = cap.min(moon_ma);
    }
    cap
}

/// Result of a low-voltage update.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum LvEvent {
    None,
    /// The level cap changed (control source = automatic).
    CapChanged,
    /// Below 3.00 V: switch off and latch "battery empty".
    Empty,
}

/// Low-voltage protection state.
///
/// * below the profile step-down voltage (under load): one level down every 5 s;
/// * below 3.10 V: Moon;
/// * below 3.00 V: off ([`LvEvent::Empty`]).
///
/// The cap is cleared by [`LowVoltage::reset`], which the controller calls on
/// every explicit level change and when the light is switched off; the rule
/// re-engages if the voltage is still low.
#[derive(Clone, Copy, Debug, Default)]
pub struct LowVoltage {
    cap: Option<Level>,
    below_sd_since: Option<u64>,
    last_step: u64,
    below_moon_since: Option<u64>,
    below_off_since: Option<u64>,
}

impl LowVoltage {
    pub const fn new() -> Self {
        Self {
            cap: None,
            below_sd_since: None,
            last_step: 0,
            below_moon_since: None,
            below_off_since: None,
        }
    }

    pub fn reset(&mut self) {
        *self = Self::new();
    }

    /// Current level cap (`None` = no limit).
    pub fn cap(&self) -> Option<Level> {
        self.cap
    }

    fn set_cap(&mut self, l: Level) -> bool {
        let new = match self.cap {
            Some(c) => c.min(l),
            None => l,
        };
        let changed = self.cap != Some(new);
        self.cap = Some(new);
        changed
    }

    /// `effective` = level of the output actually being driven.
    pub fn update(&mut self, now: u64, vbat_mv: u16, stepdown_mv: u16, effective: Level, light_on: bool) -> LvEvent {
        if !light_on {
            self.below_sd_since = None;
            self.below_moon_since = None;
            self.below_off_since = None;
            return LvEvent::None;
        }
        if vbat_mv < LV_OFF_MV {
            let since = *self.below_off_since.get_or_insert(now);
            if now - since >= LV_OFF_DELAY_MS {
                return LvEvent::Empty;
            }
        } else {
            self.below_off_since = None;
        }
        let mut changed = false;
        if vbat_mv < LV_MOON_MV {
            let since = *self.below_moon_since.get_or_insert(now);
            if now - since >= LV_MOON_DELAY_MS {
                changed |= self.set_cap(Level::Moon);
            }
        } else {
            self.below_moon_since = None;
        }
        if vbat_mv < stepdown_mv {
            if self.below_sd_since.is_none() {
                self.below_sd_since = Some(now);
                self.last_step = now;
            }
            let since = self.below_sd_since.unwrap_or(now);
            if now - since >= LV_STEP_PERIOD_MS && now - self.last_step >= LV_STEP_PERIOD_MS {
                self.last_step = now;
                changed |= self.set_cap(effective.step_down());
            }
        } else {
            self.below_sd_since = None;
        }
        if changed { LvEvent::CapChanged } else { LvEvent::None }
    }
}

/// The laser may be (kept) on: not in lockout, temperature known and <= 60 degC,
/// battery >= 3.20 V. (The 60 s limit and the gesture are handled by the controller.)
pub fn laser_permitted(temp: TempReading, vbat_mv: u16, lockout: bool) -> bool {
    !lockout
        && vbat_mv >= LASER_MIN_MV
        && matches!(temp, TempReading::Valid(t) if t <= LASER_MAX_TEMP_DC)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn thermal_linear_derating() {
        // limit 50 degC, request 1200, low 30, moon 3
        assert_eq!(thermal_cap_ma(500, 500, 1_200, 30, 3), 1_200);
        assert_eq!(thermal_cap_ma(575, 500, 1_200, 30, 3), 1_200 - 1_170 / 2);
        assert_eq!(thermal_cap_ma(650, 500, 1_200, 30, 3), 30);
        assert_eq!(thermal_cap_ma(690, 500, 1_200, 30, 3), 30);
        assert_eq!(thermal_cap_ma(701, 500, 1_200, 30, 3), 3);
        assert_eq!(thermal_cap_ma(800, 500, 1_200, 30, 3), 3);
        assert_eq!(thermal_cap_ma(801, 500, 1_200, 30, 3), 0);
        // requests at or below Low are not derated (until 70 / 80 degC)
        assert_eq!(thermal_cap_ma(600, 500, 30, 30, 3), 30);
        assert_eq!(thermal_cap_ma(600, 500, 3, 30, 3), 3);
        // monotonic in temperature
        let mut last = u16::MAX;
        for t in 400..820 {
            let c = thermal_cap_ma(t, 550, 2_200, 40, 3);
            assert!(c <= last);
            last = c;
        }
    }

    #[test]
    fn lv_steps_every_5s() {
        let mut lv = LowVoltage::new();
        // 3.30 V threshold, at 3.25 V under load
        assert_eq!(lv.update(0, 3_250, 3_300, Level::Turbo, true), LvEvent::None);
        assert_eq!(lv.update(4_900, 3_250, 3_300, Level::Turbo, true), LvEvent::None);
        assert_eq!(lv.update(5_000, 3_250, 3_300, Level::Turbo, true), LvEvent::CapChanged);
        assert_eq!(lv.cap(), Some(Level::High));
        assert_eq!(lv.update(7_000, 3_250, 3_300, Level::High, true), LvEvent::None);
        assert_eq!(lv.update(10_000, 3_250, 3_300, Level::High, true), LvEvent::CapChanged);
        assert_eq!(lv.cap(), Some(Level::Medium));
        // recovered: no further steps, cap stays
        assert_eq!(lv.update(16_000, 3_350, 3_300, Level::Medium, true), LvEvent::None);
        assert_eq!(lv.cap(), Some(Level::Medium));
        lv.reset();
        assert_eq!(lv.cap(), None);
    }

    #[test]
    fn lv_moon_and_empty() {
        let mut lv = LowVoltage::new();
        assert_eq!(lv.update(0, 3_090, 3_300, Level::High, true), LvEvent::None);
        assert_eq!(lv.update(1_000, 3_090, 3_300, Level::High, true), LvEvent::CapChanged);
        assert_eq!(lv.cap(), Some(Level::Moon));
        assert_eq!(lv.update(1_100, 2_990, 3_300, Level::Moon, true), LvEvent::None);
        assert_eq!(lv.update(3_000, 2_990, 3_300, Level::Moon, true), LvEvent::None);
        assert_eq!(lv.update(3_100, 2_990, 3_300, Level::Moon, true), LvEvent::Empty);
        // a short dip does not trigger
        let mut lv = LowVoltage::new();
        lv.update(0, 2_950, 3_300, Level::Turbo, true);
        lv.update(500, 3_200, 3_300, Level::Turbo, true);
        assert_eq!(lv.update(2_500, 2_950, 3_300, Level::Turbo, true), LvEvent::None);
    }

    #[test]
    fn laser_rules() {
        assert!(laser_permitted(TempReading::Valid(300), 3_700, false));
        assert!(laser_permitted(TempReading::Valid(600), 3_200, false));
        assert!(!laser_permitted(TempReading::Valid(601), 3_700, false));
        assert!(!laser_permitted(TempReading::Valid(300), 3_199, false));
        assert!(!laser_permitted(TempReading::Valid(300), 3_700, true));
        assert!(!laser_permitted(TempReading::Open, 3_700, false));
        assert!(!laser_permitted(TempReading::Unknown, 3_700, false));
    }
}
