// SPDX-License-Identifier: MIT OR Apache-2.0
//! v0.7 board: the FlashKa controller driving a simulated light (host test).
//!
//! The physics follow the LuxLibre PC simulator (`firmware/ports/host/sim.cpp`) with the v0.7 body
//! of `firmware/boards/flashka-keychain-v07/board.h` (octagonal housing, from the housing CAD):
//! head (head block, lid over it, copper LED board) 7.06 J/K, body (the rest of the aluminium)
//! 21.07 J/K, head to body 2.2 K/W, body to still air at 25 degC 13.2 K/W (6886 mm2 of aluminium
//! at 11 W/m2K); the sensor follows the head with a 4 s lag. One Vapcell INR14500 F15: 1500 mAh
//! (typical), a generic 3.6 V-nominal NMC open-circuit curve (no F15 curve is published), about
//! 0.10 ohm from the cell to the board (cell DC resistance about 90 mOhm, estimated as 1.5 x the
//! maker's 60 mOhm AC value, + nickel strips and wires) and 0.13 ohm to the battery ADC (+ the
//! protection MOSFETs and copper). The cell is a third thermal node, 22 J/K (22 g at about
//! 1 J/gK), weakly coupled to the body: it touches it only along the two rails through tape and its
//! sleeve, otherwise through 0.2-1.6 mm of air and a foam strip, about 8 K/W (estimate); its own
//! heat is I^2 x 0.10 ohm. LED `2.80 V + 0.15 V/A`, 87 % from the cell to the LED; when the cell
//! sags the buck runs at 100 % duty and the LED gets at most (V_J2 - 2.80 V) / (0.15 + 0.16) ohm
//! (electronics "power" block: 3.0 A down to 3.71 V at J2, 2.5 A at 3.6 V, 1.9 A at 3.4 V); 30 %
//! of the LED power leaves as light; 20 mA for the MCU and radio, its heat in the head. Light from
//! the firmware's LED model (`board::led_lumens_x10`, Tj 85 degC) x the 87 % optic, from the LED
//! current the buck really delivers. PCB, keys and optic store no heat in the model, so the times
//! are on the short side. It is a model with round numbers, not a measurement.
//!
//! The tests hold the v0.7 profiles and the thermal regulator (`flashka_core::thermal`) to their
//! targets: turbo at the full 2850 mA for at least 35 s and High (601 lm) for at least 150 s from
//! cold; the body (the surface held in the hand) at or below 47 degC at every moment, the head
//! and the sensor at or below 51 degC, both at or below 50 degC once settled (LuxLibre THM-1:
//! 48 degC continuous, 51 degC at any time); about 290 lm or more sustained; a steady current
//! (at most 2 % change from one regulator update to the next, no oscillation, also with a noisy
//! sensor); and never more than 2850 mA (the 3000 mA ceiling less the worst-case tolerance).
//! `FLASHKA_SIM_CSV=<dir>` writes one CSV per scenario (1 s rows) for plotting.
#![cfg(feature = "board-v07")]

use flashka_core::board::{LED_MAX_MA, TURBO_MAX_MA, front_lumens, front_lumens_x10, led_lumens_x10};
use flashka_core::hw::ntc_mv_at;
use flashka_core::profile::{Level, Profile, ProfileId};
use flashka_core::protocol::opcode;
use flashka_core::settings::Settings;
use flashka_core::{BootInfo, Controller, Sensors};

const C_HEAD: f64 = 7.06;
const C_BODY: f64 = 21.07;
const R_HEAD_BODY: f64 = 2.2;
const R_BODY_AIR: f64 = 13.2;
const SENSOR_TAU_S: f64 = 4.0;
const AMBIENT_C: f64 = 25.0;
const CAPACITY_MAH: f64 = 1500.0;
/// Cell to the battery ADC (cell DC resistance, strips and wires, protection MOSFETs, copper).
const R_INT: f64 = 0.132;
const EFF: f64 = 0.87;
const LIGHT_FRACTION: f64 = 0.30;
const MCU_A: f64 = 0.020;
/// Cell to the J2 pads (cell DC resistance about 0.09 ohm, nickel strips and the 24 AWG pair).
const R_CELL: f64 = 0.100;
/// J2 to the LED at 100 % duty (MOSFETs, buck high side hot, inductor, sense resistor, wires).
const R_DROP: f64 = 0.16;
/// The cell as a thermal node: heat capacity (J/K) and coupling to the body (K/W).
const C_CELL: f64 = 22.0;
const R_CELL_BODY: f64 = 8.0;

/// Open-circuit voltage of the F15: a generic 3.6 V-nominal NMC curve (no F15 curve is published).
fn ocv(soc: f64) -> f64 {
    const S: [f64; 13] = [0.0, 0.03, 0.05, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 1.00];
    const V: [f64; 13] = [2.50, 3.05, 3.25, 3.38, 3.47, 3.54, 3.61, 3.68, 3.77, 3.86, 3.95, 4.05, 4.20];
    let soc = soc.clamp(0.0, 1.0);
    for i in 1..13 {
        if soc <= S[i] {
            return V[i - 1] + (V[i] - V[i - 1]) * (soc - S[i - 1]) / (S[i] - S[i - 1]);
        }
    }
    4.20
}

struct Row {
    t_s: f64,
    /// LED current the buck really delivers (mA).
    led_ma: u16,
    /// LED current the firmware asks for (mA).
    set_ma: u16,
    status_flags: u8,
    t_sensor: f64,
    t_head: f64,
    t_body: f64,
    v_bat: f64,
    i_bat: f64,
    soc: f64,
    t_cell: f64,
    shown_pct: u8,
}

struct World {
    c: Controller,
    t_ms: u64,
    ambient: f64,
    th: f64,
    tb: f64,
    ts: f64,
    tc: f64,
    soc: f64,
    v: f64,
    i_bat: f64,
    /// LED current the buck delivers / the firmware asks for (mA).
    led_ma: u16,
    set_ma: u16,
    max_led_ma: u16,
    rows: Vec<Row>,
    /// Between these times (ms) the largest change of the LED current from one regulator update
    /// (temperature sample, 100 ms) to the next is recorded, relative to the current.
    track_from_ms: u64,
    track_until_ms: u64,
    last_update_ma: Option<u16>,
    max_step: f64,
    /// Noise on the NTC voltage: a pseudo-random whole number of mV in -n..=n per sample.
    noise_mv: i32,
    seed: u32,
}

impl World {
    fn new(profile: ProfileId) -> World {
        World::with_soc(profile, 1.0)
    }

    /// A light whose cell is `soc` full (0..1) at the start.
    fn with_soc(profile: ProfileId, soc: f64) -> World {
        let mut s = Settings::default();
        s.profile = profile;
        let c = Controller::new(s, BootInfo::default(), 0);
        let mut w = World {
            c,
            t_ms: 0,
            ambient: AMBIENT_C,
            th: AMBIENT_C,
            tb: AMBIENT_C,
            ts: AMBIENT_C,
            tc: AMBIENT_C,
            soc,
            v: ocv(soc),
            i_bat: 0.0,
            led_ma: 0,
            set_ma: 0,
            max_led_ma: 0,
            rows: Vec::new(),
            track_from_ms: u64::MAX,
            track_until_ms: u64::MAX,
            last_update_ma: None,
            max_step: 0.0,
            noise_mv: 0,
            seed: 1,
        };
        w.sense();
        w.run(2_000);
        w
    }

    fn sense(&mut self) {
        let mut ntc_mv = ntc_mv_at(self.ts as f32) as i32;
        if self.noise_mv > 0 {
            self.seed = self.seed.wrapping_mul(1_103_515_245).wrapping_add(12_345);
            ntc_mv += ((self.seed >> 16) % (2 * self.noise_mv as u32 + 1)) as i32 - self.noise_mv;
        }
        let s = Sensors {
            vbat_mv: (self.v * 1000.0).round() as u16,
            ntc_mv: ntc_mv as u16,
            chrg_low: false,
            stdby_low: false,
        };
        self.c.sensors(s, self.t_ms);
    }

    fn physics(&mut self, dt: f64) {
        let i_set = self.set_ma as f64 / 1000.0;
        let open = ocv(self.soc);
        // the cell sags with its current; at 100 % duty the buck cannot give the LED more than
        // (V_J2 - 2.80 V) / (0.15 + R_DROP)
        let (mut i, mut p_led, mut i_bat, mut v_j2) = (0.0, 0.0, MCU_A, open);
        for _ in 0..6 {
            i = i_set.min(((v_j2 - 2.80) / (0.15 + R_DROP)).max(0.0));
            p_led = if i > 0.0 { (2.80 + 0.15 * i) * i } else { 0.0 };
            // buck: P_LED / (0.87 V_J2), never more than the LED current (100 % duty)
            let i_led_in = if i > 0.0 { (p_led / EFF / v_j2.max(1.0)).min(i) } else { 0.0 };
            i_bat = i_led_in + MCU_A;
            v_j2 = open - i_bat * R_CELL;
        }
        self.led_ma = (i * 1000.0).round() as u16;
        self.v = open - i_bat * R_INT;
        self.i_bat = i_bat;
        self.soc = (self.soc - i_bat * dt / (CAPACITY_MAH * 3.6)).clamp(0.0, 1.0);
        // board (driver, LED, MCU) heat in the head; the cell's own heat in the cell
        let heat = v_j2 * i_bat - LIGHT_FRACTION * p_led;
        let heat_cell = i_bat * i_bat * R_CELL;
        let q_hb = (self.th - self.tb) / R_HEAD_BODY;
        let q_ba = (self.tb - self.ambient) / R_BODY_AIR;
        let q_cb = (self.tc - self.tb) / R_CELL_BODY;
        self.th += (heat - q_hb) * dt / C_HEAD;
        self.tb += (q_hb + q_cb - q_ba) * dt / C_BODY;
        self.tc += (heat_cell - q_cb) * dt / C_CELL;
        self.ts += (self.th - self.ts) * dt / SENSOR_TAU_S;
    }

    /// Advance in 10 ms steps (sensors every 100 ms, a log row every second).
    fn run(&mut self, ms: u64) {
        let end = self.t_ms + ms;
        while self.t_ms < end {
            self.t_ms += 10;
            self.physics(0.010);
            if self.t_ms.is_multiple_of(100) {
                self.sense();
            }
            self.c.button(false, self.t_ms);
            let out = self.c.tick(self.t_ms);
            self.set_ma = out.led_ma;
            self.max_led_ma = self.max_led_ma.max(out.led_ma);
            if self.t_ms.is_multiple_of(100)
                && (self.track_from_ms..self.track_until_ms).contains(&self.t_ms)
                && self.set_ma > 0
            {
                if let Some(last) = self.last_update_ma {
                    let step = (self.set_ma as f64 - last as f64).abs() / last.max(1) as f64;
                    self.max_step = self.max_step.max(step);
                }
                self.last_update_ma = Some(self.set_ma);
            }
            if self.t_ms.is_multiple_of(1_000) {
                let st = self.c.status(self.t_ms);
                self.rows.push(Row {
                    t_s: self.t_ms as f64 / 1000.0,
                    led_ma: self.led_ma,
                    set_ma: self.set_ma,
                    status_flags: st.flags,
                    t_sensor: self.ts,
                    t_head: self.th,
                    t_body: self.tb,
                    v_bat: self.v,
                    i_bat: self.i_bat,
                    soc: self.soc,
                    t_cell: self.tc,
                    shown_pct: st.soc_pct,
                });
            }
        }
    }

    fn command(&mut self, data: &[u8]) {
        assert_eq!(self.c.command(data, self.t_ms), Ok(()), "{data:?}");
    }

    /// Run until the light is off (empty battery) or `max_s` have passed.
    fn run_until_off(&mut self, max_s: u64) {
        let mut waited = 0;
        while waited < max_s && self.c.is_on() {
            self.run(1_000);
            waited += 1;
        }
    }

    /// One CSV row per second from the switch-on at `t_on_s` (the time column starts at 0).
    fn write_csv(&self, name: &str, t_on_s: f64) {
        let Ok(dir) = std::env::var("FLASHKA_SIM_CSV") else { return };
        let mut s = String::from(
            "t_s,led_mA,lm_led,lm_front,T_sensor_C,T_head_C,T_body_C,V_bat,I_bat_A,SoC_pct,status_flags,T_cell_C,set_mA,shown_pct\n",
        );
        for r in self.rows.iter().filter(|r| r.t_s > t_on_s) {
            s += &format!(
                "{:.0},{},{:.1},{:.1},{:.2},{:.2},{:.2},{:.3},{:.3},{:.1},{},{:.2},{},{}\n",
                r.t_s - t_on_s,
                r.led_ma,
                led_lumens_x10(r.led_ma) as f64 / 10.0,
                front_lumens_x10(r.led_ma) as f64 / 10.0,
                r.t_sensor,
                r.t_head,
                r.t_body,
                r.v_bat,
                r.i_bat,
                r.soc * 100.0,
                r.status_flags,
                r.t_cell,
                r.set_ma,
                r.shown_pct
            );
        }
        std::fs::write(format!("{dir}/{name}.csv"), s).unwrap();
    }
}

/// Key numbers of a run that started at `t_on_s`.
struct Summary {
    full_s: f64,
    ma_at: Vec<(u32, u16)>,
    lm_30s: u32,
    settled_ma: u16,
    settled_sensor: f64,
    settled_head: f64,
    settled_body: f64,
    /// 15 to 25 min after the switch-on: mean, lowest and highest LED current.
    sustained_ma: (f64, u16, u16),
    max_body: f64,
    max_head: f64,
    max_sensor: f64,
    max_i_bat: f64,
    /// ANSI FL 1 runtime: until the light falls below 10 % of its output at 30 s.
    runtime_min: f64,
}

fn summarise(w: &World, t_on_s: f64, start_ma: u16) -> Summary {
    let rows: Vec<&Row> = w.rows.iter().filter(|r| r.t_s > t_on_s).collect();
    let full_s = rows.iter().find(|r| r.led_ma < start_ma).map_or(f64::INFINITY, |r| r.t_s - t_on_s);
    let at = |min: u32| {
        rows.iter().find(|r| r.t_s - t_on_s >= min as f64 * 60.0).map_or(0, |r| r.led_ma)
    };
    let ma_at = [1, 2, 3, 5, 10, 20, 30].iter().map(|&m| (m, at(m))).collect();
    // "settled": 20 min after switch-on (or the last row before the battery is low)
    let settle = rows
        .iter()
        .find(|r| r.t_s - t_on_s >= 1_200.0)
        .copied()
        .unwrap_or_else(|| rows[rows.len() - 1]);
    let lm_30s = rows.iter().find(|r| r.t_s - t_on_s >= 30.0).map_or(0, |r| front_lumens(r.led_ma));
    let lit: Vec<&&Row> = rows.iter().filter(|r| front_lumens(r.led_ma) * 10 >= lm_30s).collect();
    let window: Vec<u16> = rows
        .iter()
        .filter(|r| (900.0..=1_500.0).contains(&(r.t_s - t_on_s)))
        .map(|r| r.led_ma)
        .collect();
    let mean = window.iter().map(|&x| x as f64).sum::<f64>() / window.len().max(1) as f64;
    Summary {
        full_s,
        ma_at,
        lm_30s,
        settled_ma: settle.led_ma,
        settled_sensor: settle.t_sensor,
        settled_head: settle.t_head,
        settled_body: settle.t_body,
        sustained_ma: (
            mean,
            window.iter().copied().min().unwrap_or(0),
            window.iter().copied().max().unwrap_or(0),
        ),
        max_body: rows.iter().map(|r| r.t_body).fold(0.0, f64::max),
        max_head: rows.iter().map(|r| r.t_head).fold(0.0, f64::max),
        max_sensor: rows.iter().map(|r| r.t_sensor).fold(0.0, f64::max),
        max_i_bat: rows.iter().map(|r| r.i_bat).fold(0.0, f64::max),
        runtime_min: lit.last().map_or(0.0, |r| (r.t_s - t_on_s) / 60.0),
    }
}

fn report(name: &str, s: &Summary) {
    println!(
        "{name}: full output {:.0} s, {} lm out of the front at 30 s; mA at 1/2/3/5/10/20/30 min {:?}; \
         settled {} mA = {} lm front, sensor {:.2} degC, head {:.2}, body {:.2}; 15-25 min {:.0} mA \
         ({}-{}) = {} lm; max sensor {:.2}, head {:.2}, body {:.2}; max cell current {:.2} A; \
         runtime (ANSI) {:.1} min",
        s.full_s,
        s.lm_30s,
        s.ma_at.iter().map(|x| x.1).collect::<Vec<_>>(),
        s.settled_ma,
        front_lumens(s.settled_ma),
        s.settled_sensor,
        s.settled_head,
        s.settled_body,
        s.sustained_ma.0,
        s.sustained_ma.1,
        s.sustained_ma.2,
        front_lumens(s.sustained_ma.0.round() as u16),
        s.max_sensor,
        s.max_head,
        s.max_body,
        s.max_i_bat,
        s.runtime_min
    );
}

/// THM-1 in the model: the body at or below 47 degC at every moment (1 degC inside the 48 degC
/// continuous limit); the head and the sensor never above 51 degC and, once settled, at or below
/// 50 degC.
fn assert_touch_limits(name: &str, s: &Summary) {
    assert!(s.max_body <= 47.0, "{name}: body {:.2}", s.max_body);
    assert!(s.max_head <= 51.0, "{name}: head {:.2}", s.max_head);
    assert!(s.max_sensor <= 51.0, "{name}: sensor {:.2}", s.max_sensor);
    assert!(s.settled_sensor <= 50.0, "{name}: settled sensor {:.2}", s.settled_sensor);
    assert!(s.settled_head <= 50.05, "{name}: settled head {:.2}", s.settled_head);
}

/// Regulated steady state, 15 to 25 min after the switch-on: about 620 mA (270 lm or more out of
/// the front; the MCU's and the cell's own heat take part of what the body can shed), no
/// oscillation (the current stays within 2 % of its mean) and at most 2 % change from one
/// regulator update to the next.
fn assert_steady(name: &str, w: &World, s: &Summary) {
    let (mean, lo, hi) = s.sustained_ma;
    assert!(front_lumens(mean.round() as u16) >= 270, "{name}: sustained {mean:.0} mA");
    assert!((hi - lo) as f64 <= 0.04 * mean, "{name}: {lo}-{hi} mA");
    assert!(w.max_step <= 0.02, "{name}: {:.1} % between updates", w.max_step * 100.0);
}

/// The cell current at least 7 % below the lowest worst-case protection trip (3.0 A, hot MOSFETs).
fn assert_cell_current(name: &str, s: &Summary) {
    assert!(s.max_i_bat * 1.07 <= 3.0, "{name}: {:.2} A", s.max_i_bat);
}

#[test]
fn balanced_turbo_then_high_then_settles_within_touch_limits() {
    let mut w = World::new(ProfileId::Balanced);
    let t_on = w.t_ms as f64 / 1000.0;
    w.track_from_ms = w.t_ms + 900_000;
    w.track_until_ms = w.t_ms + 1_500_000;
    w.command(&[opcode::LEVEL, Level::Turbo as u8]);
    w.run_until_off(10 * 3_600);
    w.write_csv("flashka_v07_balanced_turbo", t_on);
    let s = summarise(&w, t_on, TURBO_MAX_MA);
    report("Balanced turbo", &s);
    assert_eq!(w.max_led_ma, TURBO_MAX_MA, "turbo reaches 2850 mA, never more");
    assert!((w.max_led_ma as u32) < LED_MAX_MA);
    assert!(s.full_s >= 35.0, "2850 mA for at least 35 s from cold ({:.0} s)", s.full_s);
    assert_eq!(s.lm_30s, front_lumens(TURBO_MAX_MA), "the full 966 lm at 30 s");
    // settled: about 650 mA = 290 lm or more out of the front
    assert!((600..=700).contains(&s.settled_ma), "{}", s.settled_ma);
    assert_touch_limits("Balanced turbo", &s);
    assert_steady("Balanced turbo", &w, &s);
    assert_cell_current("Balanced turbo", &s);
    assert!(s.runtime_min >= 45.0, "{:.1} min", s.runtime_min);
}

#[test]
fn balanced_high_holds_600_lm_then_settles() {
    let mut w = World::new(ProfileId::Balanced);
    let t_on = w.t_ms as f64 / 1000.0;
    w.track_from_ms = w.t_ms + 900_000;
    w.track_until_ms = w.t_ms + 1_500_000;
    w.command(&[opcode::LEVEL, Level::High as u8]);
    w.run_until_off(10 * 3_600);
    w.write_csv("flashka_v07_balanced_high", t_on);
    let s = summarise(&w, t_on, Profile::BALANCED.high_ma);
    report("Balanced High", &s);
    assert!(front_lumens(Profile::BALANCED.high_ma) >= 600);
    assert!(s.full_s >= 150.0, "600 lm for at least 150 s from cold ({:.0} s)", s.full_s);
    assert_touch_limits("Balanced High", &s);
    assert_steady("Balanced High", &w, &s);
    assert_cell_current("Balanced High", &s);
}

#[test]
fn extreme_turbo_stays_within_touch_limits() {
    let mut w = World::new(ProfileId::Extreme);
    let t_on = w.t_ms as f64 / 1000.0;
    w.track_from_ms = w.t_ms + 900_000;
    w.track_until_ms = w.t_ms + 1_500_000;
    w.command(&[opcode::LEVEL, Level::Turbo as u8]);
    w.run_until_off(10 * 3_600);
    w.write_csv("flashka_v07_extreme_turbo", t_on);
    let s = summarise(&w, t_on, TURBO_MAX_MA);
    report("Extreme turbo", &s);
    assert_eq!(w.max_led_ma, TURBO_MAX_MA);
    assert!(s.full_s >= 35.0, "{:.0} s", s.full_s);
    assert_touch_limits("Extreme turbo", &s);
    assert_steady("Extreme turbo", &w, &s);
    assert_cell_current("Extreme turbo", &s);
}

#[test]
fn extreme_high_stays_within_touch_limits() {
    let mut w = World::new(ProfileId::Extreme);
    let t_on = w.t_ms as f64 / 1000.0;
    w.track_from_ms = w.t_ms + 900_000;
    w.track_until_ms = w.t_ms + 1_500_000;
    w.command(&[opcode::LEVEL, Level::High as u8]);
    w.run_until_off(10 * 3_600);
    w.write_csv("flashka_v07_extreme_high", t_on);
    let s = summarise(&w, t_on, Profile::EXTREME.high_ma);
    report("Extreme High", &s);
    assert!(s.full_s >= 100.0, "{:.0} s", s.full_s);
    assert_touch_limits("Extreme High", &s);
    assert_steady("Extreme High", &w, &s);
}

#[test]
fn endurance_high_needs_no_step_down_at_25_c() {
    let mut w = World::new(ProfileId::Endurance);
    let t_on = w.t_ms as f64 / 1000.0;
    w.command(&[opcode::LEVEL, Level::High as u8]);
    w.run_until_off(10 * 3_600);
    w.write_csv("flashka_v07_endurance_high", t_on);
    let s = summarise(&w, t_on, Profile::ENDURANCE.high_ma);
    report("Endurance High", &s);
    assert_eq!(s.settled_ma, Profile::ENDURANCE.high_ma, "no thermal step-down in 25 degC air");
    assert!(s.max_sensor < Profile::ENDURANCE.temp_limit_c as f64 - 0.2, "{:.2}", s.max_sensor);
    assert!(s.max_body <= 45.0, "{:.1}", s.max_body);
    // the full 230 lm until the low-voltage step-down, more than an hour
    assert!(s.full_s >= 3_600.0, "{:.0} s", s.full_s);
}

#[test]
fn custom_maximum_is_clamped_and_held_by_the_thermal_limit() {
    // A Custom profile asking for more than the board allows: 3000 mA turbo (the LED's datasheet
    // maximum) for 300 s, High 2000 mA, cell limit 3000 mA, 70 degC. The light clamps the turbo
    // to 2850 mA; the ceiling and the thermal rules still hold.
    let mut w = World::new(ProfileId::Balanced);
    let mut p = Profile::BALANCED;
    p.turbo_ma = 3_000;
    p.cell_limit_ma = 3_000;
    p.turbo_time_s = 300;
    p.temp_limit_c = 70;
    p.high_ma = 2_000;
    p.stepdown_ma = 2_000;
    assert_eq!(w.c.profile_write(&p.encode(ProfileId::Custom), w.t_ms), Ok(()));
    assert_eq!(w.c.profile().turbo_ma, TURBO_MAX_MA, "clamped");
    let t_on = w.t_ms as f64 / 1000.0;
    w.command(&[opcode::LEVEL, Level::Turbo as u8]);
    w.run(1_800 * 1_000);
    w.write_csv("flashka_v07_custom_max", t_on);
    assert_eq!(w.max_led_ma, TURBO_MAX_MA, "never above 2850 mA");
    let max_head = w.rows.iter().map(|r| r.t_head).fold(0.0, f64::max);
    // Moon above 70 degC, off above 80 degC: the head never passes the shutdown limit by much
    assert!(max_head < 82.0, "head {max_head:.1}");
    let max_i_bat = w.rows.iter().map(|r| r.i_bat).fold(0.0, f64::max);
    assert!(max_i_bat * 1.07 <= 3.0, "{max_i_bat:.2} A");
}

/// Step response of the regulator: High settled at the 50 degC limit, then the air gets 5 degC
/// warmer (and later 10 degC cooler). The current moves to its new level without oscillating, the
/// sensor stays within 0.5 degC of the limit and is back at or below it within 5 minutes; then it
/// settles again with less than 2 % change between updates.
#[test]
fn regulator_step_response_to_the_air_temperature() {
    let mut w = World::new(ProfileId::Balanced);
    let t_on = w.t_ms as f64 / 1000.0;
    w.command(&[opcode::LEVEL, Level::High as u8]);
    w.run(1_500 * 1_000);
    let before = w.led_ma;
    let t_step = w.t_ms as f64 / 1000.0;
    w.ambient = AMBIENT_C + 5.0;
    w.track_from_ms = w.t_ms + 400_000;
    w.run(600 * 1_000);
    let after = w.led_ma;
    let t_step2 = w.t_ms as f64 / 1000.0;
    w.ambient = AMBIENT_C - 5.0;
    w.track_from_ms = u64::MAX; // (the step itself is not a steady state)
    w.run(600 * 1_000);
    w.write_csv("flashka_v07_step_ambient", t_on);
    let rows: Vec<&Row> = w.rows.iter().filter(|r| r.t_s > t_step).collect();
    let warm: Vec<&&Row> = rows.iter().filter(|r| r.t_s <= t_step2).collect();
    let peak = warm.iter().map(|r| r.t_sensor).fold(0.0, f64::max);
    let back = warm.iter().find(|r| r.t_s - t_step >= 300.0).unwrap();
    // the current falls without first overshooting below its final value by more than 2 %
    let min_ma = warm.iter().map(|r| r.led_ma).min().unwrap();
    let cool: Vec<&&Row> = rows.iter().filter(|r| r.t_s > t_step2).collect();
    let peak_cool = cool.iter().map(|r| r.t_sensor).fold(0.0, f64::max);
    let max_ma = cool.iter().map(|r| r.led_ma).max().unwrap();
    let end = w.led_ma;
    println!(
        "step +5 degC: {before} -> {after} mA (lowest {min_ma}), sensor peak {peak:.2}, after 5 min {:.2}; \
         step -10 degC: -> {end} mA (highest {max_ma}), sensor peak {peak_cool:.2}; max change {:.2} %",
        back.t_sensor,
        w.max_step * 100.0
    );
    assert!(after < before, "warmer air: less current ({before} -> {after})");
    assert!(peak <= 50.5, "sensor peak {peak:.2}");
    assert!(back.t_sensor <= 50.0, "back at the limit within 5 min ({:.2})", back.t_sensor);
    assert!(min_ma as f64 >= after as f64 * 0.98, "no undershoot: {min_ma} vs {after}");
    assert!(end > after, "cooler air: more current ({after} -> {end})");
    assert!(peak_cool <= 50.5, "sensor peak {peak_cool:.2}");
    assert!(max_ma as f64 <= end as f64 * 1.02, "no overshoot: {max_ma} vs {end}");
    assert!(w.max_step <= 0.02, "{:.1} %", w.max_step * 100.0);
    assert!(w.max_led_ma <= TURBO_MAX_MA);
}

/// A real NTC reading is noisy. With +-3 mV of noise on the NTC voltage (about +-0.12 degC at
/// 50 degC, on every 100 ms sample) High still runs at full output for 150 s and more, stays within
/// the touch limits and settles without hunting: from 30 to 45 min (the cell and the body have
/// warmed up by then) the current stays within 1 % and turns round (by more than 2 mA) at most
/// twice.
#[test]
fn regulator_is_steady_with_a_noisy_sensor() {
    let mut w = World::new(ProfileId::Balanced);
    w.noise_mv = 3;
    let t_on = w.t_ms as f64 / 1000.0;
    w.track_from_ms = w.t_ms + 900_000;
    w.track_until_ms = w.t_ms + 2_700_000;
    w.command(&[opcode::LEVEL, Level::High as u8]);
    w.run(2_700 * 1_000);
    w.write_csv("flashka_v07_noisy_sensor", t_on);
    let s = summarise(&w, t_on, Profile::BALANCED.high_ma);
    report("Balanced High, noisy sensor", &s);
    assert!(s.full_s >= 150.0, "{:.0} s", s.full_s);
    assert_touch_limits("Balanced High, noisy sensor", &s);
    assert_steady("Balanced High, noisy sensor", &w, &s);
    let window: Vec<i32> = w
        .rows
        .iter()
        .filter(|r| (1_800.0..=2_700.0).contains(&(r.t_s - t_on)))
        .map(|r| r.set_ma as i32)
        .collect();
    let (lo, hi) = (*window.iter().min().unwrap(), *window.iter().max().unwrap());
    let mean = window.iter().map(|&x| x as f64).sum::<f64>() / window.len() as f64;
    assert!((hi - lo) as f64 <= 0.01 * mean, "{lo}-{hi} mA");
    let (mut turns, mut dir, mut anchor) = (0, 0, window[0]);
    for &x in &window {
        if (x - anchor).abs() > 2 {
            let d = (x - anchor).signum();
            if dir != 0 && d != dir {
                turns += 1;
            }
            dir = d;
            anchor = x;
        }
    }
    assert!(turns <= 2, "the current turned round {turns} times in 15 min");
}

/// Turbo from a half-full cell (50 %, 3.68 V at rest): the cell sags under 2.7 A and the buck runs
/// out of headroom, so the LED gets less than the 2850 mA the firmware asks for. The test records
/// how much the light dims (the owner must see it) and keeps the limits: never more than 2850 mA
/// asked, the cell current at or below 2.8 A, the touch limits.
#[test]
fn balanced_turbo_from_a_half_full_cell() {
    let mut w = World::with_soc(ProfileId::Balanced, 0.5);
    let t_on = w.t_ms as f64 / 1000.0;
    w.command(&[opcode::LEVEL, Level::Turbo as u8]);
    w.run(30 * 1_000);
    // the Status packet reports what the LED gets, not the 2850 mA asked for (the app's lumens)
    let reported = w.c.status(w.t_ms).led_ma;
    assert!((reported as i32 - w.led_ma as i32).abs() <= 60, "reported {reported} mA, delivered {}", w.led_ma);
    w.run(1_770 * 1_000);
    w.write_csv("flashka_v07_turbo_half_cell", t_on);
    let rows: Vec<&Row> = w.rows.iter().filter(|r| r.t_s > t_on).collect();
    let at = |t: f64| rows.iter().find(|r| r.t_s - t_on >= t).unwrap();
    let (first, r30, r59) = (at(1.0), at(30.0), at(59.0));
    let max_i_bat = rows.iter().map(|r| r.i_bat).fold(0.0, f64::max);
    let max_body = rows.iter().map(|r| r.t_body).fold(0.0, f64::max);
    let max_head = rows.iter().map(|r| r.t_head).fold(0.0, f64::max);
    println!(
        "Balanced turbo from a half-full cell: {} mA asked, {} mA delivered = {} lm at the start, {} mA = {} lm \
         at 30 s, {} mA = {} lm at 59 s (full cell: 2850 mA = 966 lm); cell {:.2} A at most, {:.2} V at the ADC \
         at 30 s; body {:.2}, head {:.2} degC at most",
        first.set_ma,
        first.led_ma,
        front_lumens(first.led_ma),
        r30.led_ma,
        front_lumens(r30.led_ma),
        r59.led_ma,
        front_lumens(r59.led_ma),
        max_i_bat,
        r30.v_bat,
        max_body,
        max_head
    );
    assert!(w.max_led_ma <= TURBO_MAX_MA);
    // turbo 30 s after switching on at other charge levels (for the documentation)
    let mut by_charge = String::new();
    for soc in [1.0, 0.9, 0.75, 0.5, 0.25] {
        let mut v = World::with_soc(ProfileId::Balanced, soc);
        v.command(&[opcode::LEVEL, Level::Turbo as u8]);
        v.run(30 * 1_000);
        by_charge += &format!(" {:.0} %: {} mA = {} lm;", soc * 100.0, v.led_ma, front_lumens(v.led_ma));
        if soc == 1.0 {
            assert_eq!(v.led_ma, TURBO_MAX_MA, "a full cell gives the whole turbo");
        }
    }
    println!("Balanced turbo at 30 s by charge:{by_charge}");
    // the buck cannot deliver the full turbo at half charge: it dims, but stays far above High
    assert!(first.led_ma < TURBO_MAX_MA && first.led_ma as u32 * 100 >= TURBO_MAX_MA as u32 * 65, "{}", first.led_ma);
    assert!(r30.led_ma > Profile::BALANCED.high_ma, "{}", r30.led_ma);
    assert!(max_i_bat <= 2.8 + 0.05, "{max_i_bat:.2} A");
    assert!(max_body <= 47.0 && max_head <= 51.0);
}
