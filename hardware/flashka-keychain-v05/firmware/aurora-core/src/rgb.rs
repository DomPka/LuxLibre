// SPDX-License-Identifier: MIT OR Apache-2.0
//! RGB status LED patterns.
//!
//! Priority (highest first):
//! 1. one-shot feedback (lockout, identify, battery check, refusals, BT window, empty);
//! 2. battery display for 2 s after switch-on (profile flag);
//! 3. USB: red slow breathing while charging, green steady when complete;
//! 4. low battery (< 10 %) red blink every 4 s while the light is on;
//! 5. Bluetooth: cyan (dim) while connected, blue double blink every 3 s while
//!    a window is open and nobody is connected.
//!
//! Blink layers only claim the LED while their blink is lit, so a low-battery
//! blink does not hide the Bluetooth indication between blinks.

use crate::config::{BATTERY_DISPLAY_MS, LOW_BATTERY_PCT, SOC_GREEN_ABOVE_PCT, SOC_RED_BELOW_PCT};

/// Logical colour, 0..=255 per channel (perceived brightness; per-channel
/// scaling for the different series resistors is applied by [`Rgb::to_duty`]).
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Rgb {
    pub r: u8,
    pub g: u8,
    pub b: u8,
}

impl Rgb {
    pub const OFF: Rgb = Rgb::new(0, 0, 0);
    pub const RED: Rgb = Rgb::new(255, 0, 0);
    pub const GREEN: Rgb = Rgb::new(0, 255, 0);
    pub const BLUE: Rgb = Rgb::new(0, 0, 255);
    pub const YELLOW: Rgb = Rgb::new(255, 160, 0);
    pub const CYAN: Rgb = Rgb::new(0, 255, 255);
    pub const CYAN_DIM: Rgb = Rgb::new(0, 40, 40);

    pub const fn new(r: u8, g: u8, b: u8) -> Rgb {
        Rgb { r, g, b }
    }

    pub fn scale(self, k: u8) -> Rgb {
        let s = |c: u8| ((c as u16 * k as u16 + 127) / 255) as u8;
        Rgb::new(s(self.r), s(self.g), s(self.b))
    }

    /// LEDC duty (`0..=max`, active-HIGH brightness) per channel. The firmware
    /// inverts it because the LED is common-anode (cathodes on the GPIOs).
    /// Red has a 1 k series resistor, green and blue 100 R, so green and blue
    /// are scaled down to roughly match.
    pub fn to_duty(self, max: u32) -> [u32; 3] {
        let ch = |c: u8, full: u32| c as u32 * full / 255 * max / 255;
        [
            ch(self.r, RGB_FULL_R as u32),
            ch(self.g, RGB_FULL_G as u32),
            ch(self.b, RGB_FULL_B as u32),
        ]
    }
}

/// Channel duty at full logical brightness (out of 255). Tune on the bench.
pub const RGB_FULL_R: u8 = 255;
pub const RGB_FULL_G: u8 = 70;
pub const RGB_FULL_B: u8 = 110;

/// Colour for a state of charge: green > 50 %, yellow 20-50 %, red < 20 %.
pub fn battery_color(soc_pct: u8) -> Rgb {
    if soc_pct > SOC_GREEN_ABOVE_PCT {
        Rgb::GREEN
    } else if soc_pct >= SOC_RED_BELOW_PCT {
        Rgb::YELLOW
    } else {
        Rgb::RED
    }
}

/// One-shot feedback patterns.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Shot {
    /// Lockout engaged: red x3.
    Locked,
    /// Lockout released: green x3.
    Unlocked,
    /// IDENTIFY command: cyan x3.
    Identify,
    /// Bluetooth window opened by a triple click: blue x2.
    BtWindow,
    /// A request was refused (turbo too hot, laser not allowed, ...): red x1.
    Refused,
    /// Button pressed during lockout: short red flash.
    LockedPress,
    /// Battery empty shutdown or switch-on refused for an empty battery: red x5 fast.
    Empty,
    /// Battery check: 1..=5 blinks (20 % per blink) in the battery colour.
    Battery { color: Rgb, blinks: u8 },
}

impl Shot {
    /// (colour, blink count, on ms, off ms)
    fn params(self) -> (Rgb, u8, u64, u64) {
        match self {
            Shot::Locked => (Rgb::RED, 3, 200, 200),
            Shot::Unlocked => (Rgb::GREEN, 3, 200, 200),
            Shot::Identify => (Rgb::CYAN, 3, 300, 300),
            Shot::BtWindow => (Rgb::BLUE, 2, 150, 150),
            Shot::Refused => (Rgb::RED, 1, 300, 200),
            Shot::LockedPress => (Rgb::RED, 1, 80, 120),
            Shot::Empty => (Rgb::RED, 5, 100, 100),
            Shot::Battery { color, blinks } => (color, blinks.clamp(1, 5), 300, 300),
        }
    }

    pub fn duration_ms(self) -> u64 {
        let (_, n, on, off) = self.params();
        n as u64 * (on + off)
    }

    /// Battery check pattern for a state of charge.
    pub fn battery(soc_pct: u8) -> Shot {
        Shot::Battery {
            color: battery_color(soc_pct),
            blinks: soc_pct.div_ceil(20).clamp(1, 5),
        }
    }
}

/// Inputs for one render.
#[derive(Clone, Copy, Debug, Default)]
pub struct RgbContext {
    pub usb_present: bool,
    pub charging: bool,
    pub charge_complete: bool,
    pub window_open: bool,
    pub connected: bool,
    pub light_on: bool,
    pub soc_pct: u8,
}

/// Pattern engine.
#[derive(Clone, Copy, Debug, Default)]
pub struct RgbEngine {
    shot: Option<(Shot, u64)>,
    battery_until: u64,
    battery_rgb: Rgb,
}

impl RgbEngine {
    pub const fn new() -> Self {
        Self {
            shot: None,
            battery_until: 0,
            battery_rgb: Rgb::OFF,
        }
    }

    /// Start a one-shot pattern (replaces a running one).
    pub fn play(&mut self, shot: Shot, now: u64) {
        self.shot = Some((shot, now));
    }

    /// Show the battery colour for 2 s (switch-on display).
    pub fn show_battery(&mut self, soc_pct: u8, now: u64) {
        self.battery_rgb = battery_color(soc_pct);
        self.battery_until = now + BATTERY_DISPLAY_MS;
    }

    /// A one-shot is still playing (sleep waits for it).
    pub fn busy(&self, now: u64) -> bool {
        matches!(self.shot, Some((s, t0)) if now < t0 + s.duration_ms())
    }

    pub fn render(&mut self, ctx: &RgbContext, now: u64) -> Rgb {
        if let Some((shot, t0)) = self.shot {
            let el = now.saturating_sub(t0);
            if el < shot.duration_ms() {
                let (c, _, on, off) = shot.params();
                return if el % (on + off) < on { c } else { Rgb::OFF };
            }
            self.shot = None;
        }
        if now < self.battery_until && ctx.light_on {
            return self.battery_rgb;
        }
        if ctx.usb_present {
            if ctx.charge_complete {
                return Rgb::GREEN.scale(120);
            }
            if ctx.charging {
                return Rgb::RED.scale(breath(now, 3_000));
            }
        }
        if ctx.light_on && ctx.soc_pct < LOW_BATTERY_PCT && now % 4_000 < 150 {
            return Rgb::RED;
        }
        if ctx.connected {
            return Rgb::CYAN_DIM;
        }
        if ctx.window_open {
            let ph = now % 3_000;
            if ph < 120 || (250..370).contains(&ph) {
                return Rgb::BLUE;
            }
        }
        Rgb::OFF
    }
}

/// Breathing brightness 0..=255 with the given period (triangle, squared).
pub fn breath(now: u64, period_ms: u64) -> u8 {
    let ph = now % period_ms;
    let half = period_ms / 2;
    let tri = if ph < half { ph * 255 / half } else { (period_ms - ph) * 255 / half };
    let tri = tri.min(255);
    ((tri * tri) / 255).max(6) as u8
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn colours_by_soc() {
        assert_eq!(battery_color(51), Rgb::GREEN);
        assert_eq!(battery_color(50), Rgb::YELLOW);
        assert_eq!(battery_color(20), Rgb::YELLOW);
        assert_eq!(battery_color(19), Rgb::RED);
        assert_eq!(Shot::battery(100), Shot::Battery { color: Rgb::GREEN, blinks: 5 });
        assert_eq!(Shot::battery(41), Shot::Battery { color: Rgb::YELLOW, blinks: 3 });
        assert_eq!(Shot::battery(0), Shot::Battery { color: Rgb::RED, blinks: 1 });
    }

    #[test]
    fn shot_overrides_and_expires() {
        let mut e = RgbEngine::new();
        let ctx = RgbContext {
            connected: true,
            ..Default::default()
        };
        e.play(Shot::Locked, 1_000);
        assert!(e.busy(1_000));
        assert_eq!(e.render(&ctx, 1_000), Rgb::RED);
        assert_eq!(e.render(&ctx, 1_250), Rgb::OFF);
        assert_eq!(e.render(&ctx, 1_400), Rgb::RED);
        assert!(!e.busy(2_200));
        assert_eq!(e.render(&ctx, 2_200), Rgb::CYAN_DIM);
    }

    #[test]
    fn priorities() {
        let mut e = RgbEngine::new();
        let mut ctx = RgbContext {
            usb_present: true,
            charging: true,
            window_open: true,
            soc_pct: 60,
            ..Default::default()
        };
        // charging breathes red even though the window is open
        let c = e.render(&ctx, 1_500);
        assert!(c.r > 200 && c.g == 0 && c.b == 0);
        ctx.charging = false;
        ctx.charge_complete = true;
        assert_eq!(e.render(&ctx, 1_500), Rgb::GREEN.scale(120));
        // no USB, window open, nobody connected: blue double blink every 3 s
        let ctx = RgbContext {
            window_open: true,
            soc_pct: 60,
            ..Default::default()
        };
        assert_eq!(e.render(&ctx, 3_000), Rgb::BLUE);
        assert_eq!(e.render(&ctx, 3_200), Rgb::OFF);
        assert_eq!(e.render(&ctx, 3_300), Rgb::BLUE);
        assert_eq!(e.render(&ctx, 4_000), Rgb::OFF);
        // battery display after switch-on wins over BLE
        let ctx_on = RgbContext {
            light_on: true,
            window_open: true,
            soc_pct: 30,
            ..Default::default()
        };
        e.show_battery(30, 10_000);
        assert_eq!(e.render(&ctx_on, 10_100), Rgb::YELLOW);
        assert_eq!(e.render(&ctx_on, 11_900), Rgb::YELLOW);
        assert_ne!(e.render(&ctx_on, 12_100), Rgb::YELLOW);
        // low battery red blink while on
        let low = RgbContext {
            light_on: true,
            window_open: true,
            soc_pct: 9,
            ..Default::default()
        };
        assert_eq!(e.render(&low, 16_000), Rgb::RED);
        assert_eq!(e.render(&low, 16_200), Rgb::OFF);
    }

    #[test]
    fn duty_scaling_and_breath() {
        assert_eq!(Rgb::RED.to_duty(8_192), [8_192, 0, 0]);
        assert_eq!(Rgb::OFF.to_duty(8_192), [0, 0, 0]);
        let [_, g, b] = Rgb::CYAN.to_duty(8_192);
        assert!(g < 8_192 && b < 8_192 && g > 0 && b > 0);
        assert_eq!(breath(0, 3_000), 6);
        assert_eq!(breath(1_500, 3_000), 255);
        assert!(breath(750, 3_000) < 128);
    }
}
