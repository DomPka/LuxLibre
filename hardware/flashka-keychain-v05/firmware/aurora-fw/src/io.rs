// SPDX-License-Identifier: MIT OR Apache-2.0
//! Hardware outputs (LED driver, laser, RGB LED, charge control) and inputs
//! (ADC, charger status pins).

use aurora_core::charger::ChargePin;
use aurora_core::controller::Outputs;
use aurora_core::rgb::Rgb;
use aurora_core::{Sensors, hw as conv};
use esp_hal::Blocking;
use esp_hal::analog::adc::{Adc, AdcCalCurve, AdcChannel, AdcPin};
use esp_hal::gpio::{Flex, Input, Level, Output};
use esp_hal::ledc::LowSpeed;
use esp_hal::ledc::channel::{Channel, ChannelHW};
use esp_hal::peripherals::ADC1;

use crate::board::PWM_FULL;

/// Everything the controller drives.
pub struct Actuators {
    pub led_en: Output<'static>,
    pub laser: Output<'static>,
    pub chg_set: Flex<'static>,
    pub led_pwm: Channel<'static, LowSpeed>,
    pub rgb_r: Channel<'static, LowSpeed>,
    pub rgb_g: Channel<'static, LowSpeed>,
    pub rgb_b: Channel<'static, LowSpeed>,
    last_duty: Option<u16>,
    last_led_on: Option<bool>,
    last_laser: Option<bool>,
    last_rgb: Option<Rgb>,
    last_chg: Option<ChargePin>,
}

impl Actuators {
    pub fn new(
        led_en: Output<'static>,
        laser: Output<'static>,
        chg_set: Flex<'static>,
        led_pwm: Channel<'static, LowSpeed>,
        rgb: [Channel<'static, LowSpeed>; 3],
    ) -> Self {
        let [rgb_r, rgb_g, rgb_b] = rgb;
        let mut a = Actuators {
            led_en,
            laser,
            chg_set,
            led_pwm,
            rgb_r,
            rgb_g,
            rgb_b,
            last_duty: None,
            last_led_on: None,
            last_laser: None,
            last_rgb: None,
            last_chg: None,
        };
        a.all_off();
        a.set_charge_pin(ChargePin::Float);
        a
    }

    /// Main LED: set the duty first, then enable the driver; to switch off,
    /// disable the driver first, then zero the duty.
    fn set_led(&mut self, ma: u16) {
        if ma == 0 {
            if self.last_led_on != Some(false) {
                self.led_en.set_low();
                self.last_led_on = Some(false);
            }
            if self.last_duty != Some(0) {
                self.led_pwm.set_duty_hw(0);
                self.last_duty = Some(0);
            }
        } else {
            let duty = conv::led_duty_counts(ma);
            if self.last_duty != Some(duty) {
                self.led_pwm.set_duty_hw(duty as u32);
                self.last_duty = Some(duty);
            }
            if self.last_led_on != Some(true) {
                self.led_en.set_high();
                self.last_led_on = Some(true);
            }
        }
    }

    fn set_laser(&mut self, on: bool) {
        if self.last_laser != Some(on) {
            self.laser.set_level(if on { Level::High } else { Level::Low });
            self.last_laser = Some(on);
        }
    }

    /// The RGB LED is common anode with the cathodes on the GPIOs, so a
    /// channel is lit while its output is LOW: duty = full - brightness.
    fn set_rgb(&mut self, c: Rgb) {
        if self.last_rgb == Some(c) {
            return;
        }
        let [r, g, b] = c.to_duty(PWM_FULL);
        self.rgb_r.set_duty_hw(PWM_FULL - r.min(PWM_FULL));
        self.rgb_g.set_duty_hw(PWM_FULL - g.min(PWM_FULL));
        self.rgb_b.set_duty_hw(PWM_FULL - b.min(PWM_FULL));
        self.last_rgb = Some(c);
    }

    /// CHG_SET: LOW = fast charge, floating = trickle, HIGH = charger off.
    /// The level is written before the driver is enabled (no glitch).
    fn set_charge_pin(&mut self, pin: ChargePin) {
        if self.last_chg == Some(pin) {
            return;
        }
        match pin {
            ChargePin::Float => self.chg_set.set_output_enable(false),
            ChargePin::Low => {
                self.chg_set.set_low();
                self.chg_set.set_output_enable(true);
            }
            ChargePin::High => {
                self.chg_set.set_high();
                self.chg_set.set_output_enable(true);
            }
        }
        self.last_chg = Some(pin);
    }

    pub fn apply(&mut self, out: &Outputs) {
        self.set_led(out.led_ma);
        self.set_laser(out.laser_on);
        self.set_rgb(out.rgb);
        self.set_charge_pin(out.charge_pin);
    }

    /// LED driver off, laser off, RGB off (charge pin unchanged).
    pub fn all_off(&mut self) {
        self.last_led_on = None;
        self.last_duty = None;
        self.last_laser = None;
        self.last_rgb = None;
        self.set_led(0);
        self.set_laser(false);
        self.set_rgb(Rgb::OFF);
    }
}

type Adc1 = Adc<'static, ADC1<'static>, Blocking>;
type CalPin<P> = AdcPin<P, ADC1<'static>, AdcCalCurve<ADC1<'static>>>;

/// Analog inputs and charger status pins.
pub struct SensorInputs<PV, PN> {
    pub adc: Adc1,
    pub vbat: CalPin<PV>,
    pub ntc: CalPin<PN>,
    pub chg_stat: Input<'static>,
    pub chg_done: Input<'static>,
    failures: u8,
}

/// After this many consecutive failed conversions the ADC is considered dead.
const ADC_DEAD_AFTER: u8 = 5;

/// One calibrated conversion in mV (`None` if the ADC never finishes).
fn read_mv<P: AdcChannel>(adc: &mut Adc1, pin: &mut CalPin<P>) -> Option<u16> {
    for _ in 0..10_000 {
        if let Ok(v) = adc.read_oneshot(pin) {
            return Some(v);
        }
    }
    None
}

/// Average of `n` conversions.
fn read_avg<P: AdcChannel>(adc: &mut Adc1, pin: &mut CalPin<P>, n: u32) -> Option<u16> {
    let mut sum = 0u32;
    for _ in 0..n {
        sum += read_mv(adc, pin)? as u32;
    }
    Some((sum / n) as u16)
}

impl<PV: AdcChannel, PN: AdcChannel> SensorInputs<PV, PN> {
    pub fn new(adc: Adc1, vbat: CalPin<PV>, ntc: CalPin<PN>, chg_stat: Input<'static>, chg_done: Input<'static>) -> Self {
        SensorInputs {
            adc,
            vbat,
            ntc,
            chg_stat,
            chg_done,
            failures: 0,
        }
    }

    /// One sample of everything. `None` = an isolated conversion failure
    /// (skip this sample). If the ADC keeps failing, zeros are reported:
    /// VBAT 0 makes the protection switch the light off and NTC 0 V reads as a
    /// shorted sensor (thermal shutdown) - the protection is never left
    /// working with stale values.
    pub fn sample(&mut self) -> Option<Sensors> {
        let vbat = read_avg(&mut self.adc, &mut self.vbat, 4);
        let ntc = read_avg(&mut self.adc, &mut self.ntc, 4);
        let (vbat_adc, ntc_mv) = match (vbat, ntc) {
            (Some(v), Some(n)) => {
                self.failures = 0;
                (v, n)
            }
            _ => {
                self.failures = self.failures.saturating_add(1);
                if self.failures < ADC_DEAD_AFTER {
                    return None;
                }
                (vbat.unwrap_or(0), ntc.unwrap_or(0))
            }
        };
        Some(Sensors {
            vbat_mv: conv::vbat_from_adc_mv(vbat_adc),
            ntc_mv,
            chrg_low: self.chg_stat.is_low(),
            stdby_low: self.chg_done.is_low(),
        })
    }
}
