// SPDX-License-Identifier: MIT OR Apache-2.0
//! TP4057 charge control through GPIO20 (CHG_SET) and USB detection through
//! the CHRG (GPIO4) / STDBY (GPIO5) open-drain status outputs.
//!
//! CHG_SET: output LOW = ~280 mA, INPUT (floating) = 10 mA trickle through the
//! 100 k to GND, output HIGH = charger off. HIGH is only driven while USB
//! power is present.
//!
//! There is no direct VBUS sense: USB is "present" when CHRG or STDBY is low.
//! While the charger is switched off with CHG_SET high, the TP4057 may release
//! both status pins although USB is still plugged in, so during a pause the
//! last known presence is kept and re-checked every [`USB_PROBE_PERIOD_MS`] by
//! floating CHG_SET (10 mA trickle) for [`USB_PROBE_MS`].

use crate::config::{
    CHARGE_HYST_DC, CHARGE_MAX_DC, CHARGE_MIN_DC, CHARGE_PAUSE_LED_MA, USB_GONE_MS,
    USB_PROBE_MS, USB_PROBE_PERIOD_MS,
};
use crate::hw::TempReading;

/// Requested state of the CHG_SET pin.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ChargePin {
    /// Input, no pull: 10 mA trickle (also the state without firmware).
    Float,
    /// Output low: fast charge (~280 mA).
    Low,
    /// Output high: charger off. Only while USB is present.
    High,
}

/// Charger state machine.
#[derive(Clone, Copy, Debug)]
pub struct Charger {
    usb_present: bool,
    pins_low_seen: bool,
    gone_since: Option<u64>,
    pin: ChargePin,
    probe_until: Option<u64>,
    next_probe: u64,
    temp_ok: bool,
    charging: bool,
    complete: bool,
}

impl Default for Charger {
    fn default() -> Self {
        Self::new()
    }
}

impl Charger {
    pub const fn new() -> Self {
        Self {
            usb_present: false,
            pins_low_seen: false,
            gone_since: None,
            pin: ChargePin::Float,
            probe_until: None,
            next_probe: 0,
            temp_ok: false,
            charging: false,
            complete: false,
        }
    }

    pub fn usb_present(&self) -> bool {
        self.usb_present
    }

    /// TP4057 is charging (CHRG low) - Status bit 2.
    pub fn charging(&self) -> bool {
        self.charging
    }

    /// TP4057 reports charge complete (STDBY low) - Status bit 3.
    pub fn complete(&self) -> bool {
        self.complete
    }

    /// Fast charge current selected and the charger reports charging.
    pub fn fast_charging(&self) -> bool {
        self.charging && self.pin == ChargePin::Low
    }

    pub fn pin(&self) -> ChargePin {
        self.pin
    }

    fn update_temp_ok(&mut self, temp: TempReading) {
        self.temp_ok = match temp.valid() {
            None => false,
            Some(t) => {
                if self.temp_ok {
                    (CHARGE_MIN_DC..=CHARGE_MAX_DC).contains(&t)
                } else {
                    (CHARGE_MIN_DC + CHARGE_HYST_DC..=CHARGE_MAX_DC - CHARGE_HYST_DC).contains(&t)
                }
            }
        };
    }

    /// Update with the status pins (`true` = pin reads low), the board
    /// temperature and the LED current that is being driven. Returns the
    /// requested CHG_SET state.
    pub fn update(
        &mut self,
        now: u64,
        chrg_low: bool,
        stdby_low: bool,
        temp: TempReading,
        led_ma: u16,
    ) -> ChargePin {
        let raw = chrg_low || stdby_low;
        self.update_temp_ok(temp);

        if let Some(until) = self.probe_until {
            // Probing: CHG_SET is floating, the charger trickles if USB is there.
            if raw {
                self.pins_low_seen = true;
            }
            if now >= until {
                self.probe_until = None;
                self.usb_present = self.pins_low_seen;
                self.next_probe = now + USB_PROBE_PERIOD_MS;
                self.gone_since = None;
            }
        } else if self.pin == ChargePin::High {
            // Paused: the status pins may be released by the TP4057, keep the
            // last presence and probe periodically.
            if raw {
                self.usb_present = true;
            }
            if now >= self.next_probe {
                self.probe_until = Some(now + USB_PROBE_MS);
                self.pins_low_seen = raw;
            }
        } else if raw {
            self.usb_present = true;
            self.gone_since = None;
        } else if self.usb_present {
            let since = *self.gone_since.get_or_insert(now);
            if now.saturating_sub(since) >= USB_GONE_MS {
                self.usb_present = false;
                self.gone_since = None;
            }
        }

        let wanted = if !self.usb_present {
            ChargePin::Float
        } else if self.temp_ok && led_ma <= CHARGE_PAUSE_LED_MA {
            ChargePin::Low
        } else {
            ChargePin::High
        };

        self.pin = if self.probe_until.is_some() {
            ChargePin::Float
        } else {
            if wanted == ChargePin::High && self.pin != ChargePin::High {
                // entering a pause: first probe after the full period
                self.next_probe = now + USB_PROBE_PERIOD_MS;
            }
            wanted
        };

        self.charging = self.usb_present && chrg_low && self.pin != ChargePin::High;
        self.complete = self.usb_present && stdby_low;
        self.pin
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const WARM: TempReading = TempReading::Valid(250);

    #[test]
    fn no_usb_floats() {
        let mut c = Charger::new();
        assert_eq!(c.update(0, false, false, WARM, 0), ChargePin::Float);
        assert!(!c.usb_present());
    }

    #[test]
    fn usb_plugged_fast_charge() {
        let mut c = Charger::new();
        assert_eq!(c.update(0, true, false, WARM, 0), ChargePin::Low);
        assert!(c.usb_present() && c.charging() && c.fast_charging());
        // charge complete
        assert_eq!(c.update(100, false, true, WARM, 0), ChargePin::Low);
        assert!(c.complete() && !c.charging());
    }

    #[test]
    fn usb_removed_after_debounce() {
        let mut c = Charger::new();
        c.update(0, true, false, WARM, 0);
        assert_eq!(c.update(100, false, false, WARM, 0), ChargePin::Low);
        assert!(c.usb_present());
        c.update(900, false, false, WARM, 0);
        assert!(c.usb_present());
        assert_eq!(c.update(1_200, false, false, WARM, 0), ChargePin::Float);
        assert!(!c.usb_present());
    }

    #[test]
    fn temperature_window_with_hysteresis() {
        let mut c = Charger::new();
        assert_eq!(c.update(0, true, false, TempReading::Valid(460), 0), ChargePin::High);
        assert!(!c.charging(), "paused is not charging");
        // must cool to 43.0 before resuming
        assert_eq!(c.update(100, true, false, TempReading::Valid(440), 0), ChargePin::High);
        assert_eq!(c.update(200, true, false, TempReading::Valid(430), 0), ChargePin::Low);
        assert_eq!(c.update(300, true, false, TempReading::Valid(449), 0), ChargePin::Low);
        assert_eq!(c.update(400, true, false, TempReading::Valid(451), 0), ChargePin::High);
        // too cold
        let mut c = Charger::new();
        assert_eq!(c.update(0, true, false, TempReading::Valid(-10), 0), ChargePin::High);
        assert_eq!(c.update(1, true, false, TempReading::Valid(15), 0), ChargePin::High);
        assert_eq!(c.update(2, true, false, TempReading::Valid(20), 0), ChargePin::Low);
        // sensor fault -> no charging
        assert_eq!(c.update(3, true, false, TempReading::Open, 0), ChargePin::High);
    }

    #[test]
    fn led_above_500ma_pauses() {
        let mut c = Charger::new();
        assert_eq!(c.update(0, true, false, WARM, 500), ChargePin::Low);
        assert_eq!(c.update(100, true, false, WARM, 501), ChargePin::High);
        assert_eq!(c.update(200, true, false, WARM, 400), ChargePin::Low);
    }

    #[test]
    fn pause_keeps_usb_and_probes() {
        let mut c = Charger::new();
        c.update(0, true, false, WARM, 0);
        assert_eq!(c.update(100, true, false, WARM, 900), ChargePin::High);
        // the TP4057 releases both pins while switched off: still "present"
        for t in (200..10_000).step_by(100) {
            assert_eq!(c.update(t, false, false, WARM, 900), ChargePin::High, "t={t}");
            assert!(c.usb_present());
        }
        // probe at 10.1 s: float, pins come back low -> still present
        assert_eq!(c.update(10_100, false, false, WARM, 900), ChargePin::Float);
        assert_eq!(c.update(10_200, true, false, WARM, 900), ChargePin::Float);
        assert_eq!(c.update(10_300, false, false, WARM, 900), ChargePin::High);
        assert!(c.usb_present());
        // next probe: pins stay high -> USB was removed
        assert_eq!(c.update(20_300, false, false, WARM, 900), ChargePin::Float);
        assert_eq!(c.update(20_400, false, false, WARM, 900), ChargePin::Float);
        assert_eq!(c.update(20_500, false, false, WARM, 900), ChargePin::Float);
        assert!(!c.usb_present());
    }
}
