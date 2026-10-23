// SPDX-License-Identifier: MIT OR Apache-2.0
//! v0.7 board: thermal regulator (feature `board-v07`).
//!
//! The v0.6 board keeps the protocol's linear law ([`crate::protection::thermal_cap_ma`]): above the
//! profile's temperature limit the current falls to Low over 15 degC. That law settles where the
//! heat matches what the body sheds, about 9 degC above the limit, so on the v0.7 the limit had to be
//! set low (41 degC) and the light started dimming while the body was still cool. On the v0.7 the
//! profile's temperature limit is instead the set point of a regulator: the light keeps the sensor
//! (NTC) at or just below the limit and gives the full current until the temperature, predicted a few
//! seconds ahead, gets there.
//!
//! Every temperature sample (100 ms):
//!
//! ```text
//! T      = filtered sensor temperature (one more filter, 1/16 per sample, about 1.6 s)
//! rate   = rate of rise of T (filtered, 1/32 per sample, about 3.2 s), less 0.03 degC/s;
//!          cooling counts as 0
//! T_pred = T + rate x LEAD_S                 (the sensor lags the head by about 4 s)
//! aim    = limit - MARGIN_DC
//! e      = T_pred - aim, or 0 while T_pred is within BAND_DC below the aim
//! I      = I - KI' x e x 0.1 s, kept between Low and the requested current (no wind-up; while it
//!          is too hot, the request plus the P part, so a lower request does not dip first);
//!          KI' = KI, falling in proportion to the error below I_SOFT_DC
//! cap    = I - KP x e', kept between Low and the requested current; e' = e less one step of the
//!          reading (P_GAP_DC): the proportional part starts 0.1 degC further out on either side
//! ```
//!
//! More than [`HOT_DC`] above the limit the cap is Low at once (a backstop). Requests at or below Low
//! are never reduced, as on the v0.6; Moon above 70 degC and off above 80 degC stay as in the protocol.
//! Set points above 65 degC act as 65 degC, so the regulator never runs into the Moon limit.
//!
//! Stability (linearised with the v0.7 thermal model of the octagonal body: head 7.06 J/K, body
//! 21.07 J/K, cell 22 J/K weakly coupled to the body, head to body 2.2 K/W, body to air 13.2 K/W,
//! sensor lag 4 s; the 100 ms sampling, both filters and one sample of delay included, the full
//! integral gain): at 0.62 to 2.85 A the loop crosses over at 0.16 to 0.20 rad/s (a period of
//! 31-39 s, between the head's 16 s and the body's minutes) with a phase margin of at least
//! 57 degrees and a gain margin of at least 10 dB. The prediction gives back the phase that the
//! sensor lag and the filters take away (without it, for slow changes: at least 43 degrees and
//! 12.8 dB). With the sensor lag doubled to 8 s, or the head-to-body resistance doubled, the margins
//! stay above 46 degrees and 9.1 dB. Near the aim the integral gain is smaller still. Within the band neither term acts, and the proportional
//! part only from one step of the reading beyond it, so the 0.1 degC steps and the noise of the
//! reading cannot make the current hunt: in the simulation the settled current does not change at
//! all, also with noise on the NTC voltage (tests/thermal_v07.rs, which also checks the step
//! response to a change of the air temperature).

/// Proportional gain: mA less per degC of predicted temperature above the limit.
pub const KP_MA_PER_C: i32 = 300;
/// Integral gain: mA per second less per degC above the limit.
pub const KI_MA_PER_C_S: i32 = 24;
/// The regulator acts on the temperature this many seconds ahead at the present rate of rise.
pub const LEAD_S: i32 = 8;
/// The regulator aims this far below the limit (0.1 degC), so that the sensor itself stays at or
/// below the limit although the reading has a resolution of 0.1 degC.
pub const MARGIN_DC: i32 = 1;
/// Within this distance below the aim (0.1 degC) the current is held.
pub const BAND_DC: i32 = 2;
/// The proportional part acts only this far (0.1 degC, one step of the reading) beyond the band on
/// either side. A reading that flicks between two values at the edge of the band then moves only the
/// slow integral part, not the current in steps of KP x 0.1 degC = 30 mA.
pub const P_GAP_DC: i32 = 1;
/// Below this error (0.1 degC) the integral gain falls in proportion to the error, so that the
/// integral term cannot overshoot the narrow band (one 0.1 degC step of the reading is only about
/// 2.5 mA of steady-state current).
pub const I_SOFT_DC: i32 = 5;
/// Rates of rise below this (0.001 degC/s) are not used for the prediction (the 0.1 degC steps of
/// a slowly drifting reading would otherwise look like short rises).
pub const RATE_MIN_MC_PER_S: i32 = 30;
/// More than this above the limit (0.1 degC): Low at once.
pub const HOT_DC: i32 = 50;
/// Highest set point (0.1 degC): 5 degC below the Moon limit of the protocol.
pub const SETPOINT_MAX_DC: i16 = crate::config::THERMAL_MOON_DC - 50;
/// Input filter: 1/2^n of the difference per sample (100 ms).
const T_SHIFT: i32 = 4;
/// Rate filter: 1/2^n of the difference per sample.
const RATE_SHIFT: i32 = 5;
/// Samples per second (one per [`crate::controller::Controller::sensors`] call).
const RATE_PER_S: i32 = 10;

/// State of the regulator (fixed point: temperatures in 0.1 degC x 256, currents in mA x 256).
#[derive(Clone, Copy, Debug)]
pub struct ThermalReg {
    valid: bool,
    started: bool,
    t_q: i32,
    prev_q: i32,
    rate_q: i32,
    i_q: i32,
    rem: i32,
    /// KP x e' (the proportional part), mA x 256 (positive = too hot).
    p_q: i32,
    hot: bool,
}

impl Default for ThermalReg {
    fn default() -> Self {
        Self::new()
    }
}

impl ThermalReg {
    pub const fn new() -> Self {
        Self { valid: false, started: false, t_q: 0, prev_q: 0, rate_q: 0, i_q: 0, rem: 0, p_q: 0, hot: false }
    }

    /// No usable temperature: the filters start again from the next valid sample (the integrator
    /// is kept).
    pub fn invalidate(&mut self) {
        self.valid = false;
    }

    /// One temperature sample. `temp_f16` = the controller's filtered temperature (0.1 degC x 16),
    /// `limit_dc` = the profile's limit, `req_ma` = the current the light asks for after the
    /// low-voltage rule (0 = off: the filters keep running, the integrator keeps its value).
    pub fn update(&mut self, temp_f16: i32, limit_dc: i16, req_ma: u16, low_ma: u16) {
        let t_in = temp_f16 * 16;
        if !self.valid {
            self.t_q = t_in;
            self.prev_q = t_in;
            self.rate_q = 0;
            self.valid = true;
        } else {
            self.t_q += (t_in - self.t_q) >> T_SHIFT;
        }
        let d = (self.t_q - self.prev_q) * RATE_PER_S;
        self.prev_q = self.t_q;
        self.rate_q += (d - self.rate_q) >> RATE_SHIFT;

        let limit_q = limit_dc.min(SETPOINT_MAX_DC) as i32 * 256;
        let lim_q = limit_q - MARGIN_DC * 256;
        let pred = self.t_q + (self.rate_q - RATE_MIN_MC_PER_S * 256 / 100).max(0) * LEAD_S;
        let over = pred - lim_q;
        let band = BAND_DC * 256;
        let e = if over > 0 {
            over
        } else if over < -band {
            over + band
        } else {
            0
        };
        // the proportional part starts one step of the reading further out (P_GAP_DC)
        let gap = P_GAP_DC * 256;
        let e_p = if over > gap {
            over - gap
        } else if over < -band - gap {
            over + band + gap
        } else {
            0
        };
        // KP [mA/degC] x e [0.1 degC x 256] / 10 = mA x 256
        self.p_q = KP_MA_PER_C * e_p / 10;
        self.hot = self.t_q - limit_q > HOT_DC * 256;
        if req_ma == 0 {
            return;
        }
        let floor = low_ma.min(req_ma) as i32 * 256;
        let top = req_ma as i32 * 256;
        if !self.started {
            self.i_q = top;
            self.rem = 0;
            self.started = true;
        }
        // KI [mA/(degC s)] x e / 10 [degC x 256] x 0.1 s = KI x e / 100 [mA x 256], with the gain
        // reduced in proportion below I_SOFT_DC of error
        let soft = I_SOFT_DC * 256;
        let num = KI_MA_PER_C_S as i64 * e as i64 * e.abs().min(soft) as i64 / soft as i64 + self.rem as i64;
        let step = (num / 100) as i32;
        self.rem = (num - step as i64 * 100) as i32;
        // The integrator stays between Low and the request; while it is too hot it may sit above the
        // request by the proportional part, so that a lower request (the end of turbo, a lower
        // level) does not first dip below the new level: the heat falls with the request anyway.
        let ceil = top + self.p_q.max(0);
        let i = self.i_q - step;
        if i <= floor || i >= ceil {
            self.rem = 0;
        }
        self.i_q = i.clamp(floor, ceil);
        if self.hot {
            self.i_q = floor;
            self.rem = 0;
        }
    }

    /// The thermal limit for a request of `req_ma` (mA): never below Low (or the request, when the
    /// request is at or below Low), never above the request.
    pub fn cap_ma(&self, req_ma: u16, low_ma: u16) -> u16 {
        if !self.valid || !self.started || req_ma == 0 {
            return req_ma;
        }
        let floor = low_ma.min(req_ma);
        if self.hot {
            return floor;
        }
        let u = (self.i_q - self.p_q).max(0) >> 8;
        (u.min(u16::MAX as i32) as u16).clamp(floor, req_ma)
    }

    /// Filtered temperature the regulator uses (0.1 degC).
    pub fn temperature_dc(&self) -> i32 {
        self.t_q / 256
    }

    /// Filtered rate of rise (0.1 degC per second).
    pub fn rate_dc_per_s(&self) -> i32 {
        self.rate_q / 256
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Feed `n` samples of a constant temperature (degC) with a request.
    fn feed(r: &mut ThermalReg, temp_c: f32, req: u16, low: u16, limit_c: i16, n: usize) {
        for _ in 0..n {
            r.update((temp_c * 160.0) as i32, limit_c * 10, req, low);
        }
    }

    #[test]
    fn full_current_below_the_band() {
        let mut r = ThermalReg::new();
        assert_eq!(r.cap_ma(1_530, 40), 1_530, "no sample yet: no limit");
        feed(&mut r, 30.0, 1_530, 40, 50, 100);
        assert_eq!(r.cap_ma(1_530, 40), 1_530);
        assert_eq!(r.cap_ma(2_850, 40), 2_850, "a higher request is not held back");
        let mut r = ThermalReg::new();
        feed(&mut r, 49.85, 1_530, 40, 50, 300);
        assert_eq!(r.cap_ma(1_530, 40), 1_530, "within the band below the limit: held");
    }

    #[test]
    fn too_hot_reduces_towards_low_and_never_below() {
        let mut r = ThermalReg::new();
        feed(&mut r, 51.0, 1_530, 40, 50, 1);
        assert!(r.cap_ma(1_530, 40) < 1_530, "1 degC too hot: less at once (P part)");
        let mut last = r.cap_ma(1_530, 40);
        for _ in 0..599 {
            feed(&mut r, 51.0, 1_530, 40, 50, 1);
            let c = r.cap_ma(1_530, 40);
            assert!(c <= last, "monotonic while too hot");
            last = c;
        }
        assert_eq!(last, 40, "1 degC too hot for a minute: down to Low");
        // requests at or below Low are never reduced
        assert_eq!(r.cap_ma(40, 40), 40);
        assert_eq!(r.cap_ma(3, 40), 3);
    }

    #[test]
    fn backstop_more_than_5_degc_above_the_limit() {
        let mut r = ThermalReg::new();
        feed(&mut r, 40.0, 2_850, 40, 50, 50);
        feed(&mut r, 55.6, 2_850, 40, 50, 100);
        assert_eq!(r.cap_ma(2_850, 40), 40);
        feed(&mut r, 54.0, 2_850, 40, 50, 20);
        assert!(r.cap_ma(2_850, 40) < 2_850, "the integrator restarts from Low");
    }

    #[test]
    fn set_point_is_kept_below_the_moon_limit() {
        let mut r = ThermalReg::new();
        feed(&mut r, 64.0, 1_000, 40, 70, 100);
        assert_eq!(r.cap_ma(1_000, 40), 1_000);
        feed(&mut r, 66.0, 1_000, 40, 70, 300);
        assert!(r.cap_ma(1_000, 40) < 1_000, "a 70 degC limit acts as 65 degC");
    }

    #[test]
    fn integrator_does_not_wind_up_and_recovers_when_cool() {
        let mut r = ThermalReg::new();
        feed(&mut r, 52.0, 1_530, 40, 50, 600);
        assert_eq!(r.cap_ma(1_530, 40), 40);
        // switched off for a while: the integrator keeps its value, the filters follow the sensor
        feed(&mut r, 30.0, 0, 40, 50, 600);
        assert_eq!(r.cap_ma(1_530, 40), 1_530, "cool again: the full current at once");
        feed(&mut r, 30.0, 250, 40, 50, 100);
        assert_eq!(r.cap_ma(250, 40), 250);
        assert_eq!(r.cap_ma(2_850, 40), 2_850);
    }

    #[test]
    fn rising_temperature_is_predicted() {
        // 0.4 degC/s, as at the end of turbo: the cap starts falling about LEAD_S before the
        // filtered temperature reaches the limit
        let mut r = ThermalReg::new();
        let mut t = 40.0f32;
        let mut first_cut = None;
        for i in 0..400 {
            r.update((t * 160.0) as i32, 500, 2_850, 40);
            if first_cut.is_none() && r.cap_ma(2_850, 40) < 2_850 {
                first_cut = Some((i, r.temperature_dc()));
            }
            t += 0.04;
        }
        let (_, t_dc) = first_cut.unwrap();
        assert!((460..=480).contains(&t_dc), "cut starts at {t_dc} (0.1 degC)");
    }

    #[test]
    fn a_lower_request_while_hot_does_not_dip_first() {
        // regulating turbo a little above the aim
        let mut r = ThermalReg::new();
        let mut t = 49.0f32;
        for _ in 0..200 {
            r.update((t * 160.0) as i32, 500, 2_850, 40);
            if t < 50.4 {
                t += 0.01;
            }
        }
        assert!(r.cap_ma(2_850, 40) < 2_850);
        // the turbo time is over: 1530 mA asked; the heat falls with it, so no dip below 1530 first
        r.update((t * 160.0) as i32, 500, 1_530, 40);
        assert_eq!(r.cap_ma(1_530, 40), 1_530);
        // still too hot a minute later: the integrator takes it down
        feed(&mut r, 50.4, 1_530, 40, 50, 600);
        assert!(r.cap_ma(1_530, 40) < 1_400, "{}", r.cap_ma(1_530, 40));
    }

    #[test]
    fn a_reading_flicking_at_the_edge_of_the_band_does_not_step_the_current() {
        // regulating at the aim: the reading flicks between 49.9 and 50.0 degC every 3 s
        let mut r = ThermalReg::new();
        feed(&mut r, 49.9, 700, 40, 50, 300);
        let mut last = r.cap_ma(700, 40);
        assert_eq!(last, 700);
        for k in 0..20 {
            let t = if k % 2 == 0 { 50.0 } else { 49.9 };
            for _ in 0..30 {
                feed(&mut r, t, 700, 40, 50, 1);
                let c = r.cap_ma(700, 40);
                assert!(c <= last && last - c <= 1, "only the slow integral part moves: {last} -> {c}");
                last = c;
            }
        }
        // two steps above the aim: the proportional part acts
        feed(&mut r, 50.1, 700, 40, 50, 50);
        assert!(r.cap_ma(700, 40) + 20 < last, "{} vs {last}", r.cap_ma(700, 40));
    }

    #[test]
    fn invalid_reading_restarts_the_filters() {
        let mut r = ThermalReg::new();
        feed(&mut r, 45.0, 1_530, 40, 50, 100);
        r.invalidate();
        assert_eq!(r.cap_ma(1_530, 40), 1_530);
        feed(&mut r, 30.0, 1_530, 40, 50, 1);
        assert_eq!(r.temperature_dc(), 300, "starts from the new reading, no rate jump");
        assert_eq!(r.rate_dc_per_s(), 0);
    }
}
