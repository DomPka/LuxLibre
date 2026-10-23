// SPDX-License-Identifier: MIT OR Apache-2.0
//! The flashlight state machine.
//!
//! The firmware drives it like this (see `flashka-fw/src/main.rs`):
//!
//! ```text
//! let mut c = Controller::new_with_class(settings_from_flash, boot_info, first_class, now);
//! loop {
//!     c.buttons(ladder_class, now);            // every 10 ms (ADC on GPIO3)
//!     every 100 ms: c.sensors(adc_and_pins, now);
//!     let out = c.tick(now);                    // apply out.led_ma, out.laser_on, ...
//!     BLE: c.command(..) / c.profile_write(..) / c.presenter_write(..)
//!          c.ble_connected(..) / c.hid_connected(..) / c.status(now)
//!          c.take_key() -> HID report, c.take_forget_hosts() -> erase bonds
//! }
//! ```
//!
//! v0.6 adds the slide buttons (› / ‹: level steps while on, ‹ + › for 2 s =
//! presenter mode) and the presenter mode itself: the light becomes a
//! Bluetooth keyboard, the main LED stays off, ● click = B, ● hold = laser.

use crate::battery::{self, ChargeInfo, SocEstimator};
use crate::buttons::{ButtonClass, Slide, SlideEvent, SlideParser};
use crate::charger::{ChargePin, Charger};
use crate::config::*;
use crate::gesture::{GestureEvent, GestureParser};
use crate::hid::HidKey;
use crate::hw::{self, TempReading};
use crate::mathx::div_ceil;
use crate::presenter::{PRESENTER_LEN, PresenterAction, PresenterSettings};
use crate::profile::{Level, Profile, ProfileId, FLAG_MEMORY, FLAG_SHOW_BATTERY};
use crate::protection::{self, LowVoltage, LvEvent};
use crate::protocol::{
    self, status_flags as sf, CmdError, Command, ControlSource, DeviceMode, Status, LEVEL_EXACT, PROFILE_LEN,
    RUNTIME_UNKNOWN,
};
use crate::rgb::{Rgb, RgbContext, RgbEngine, Shot};
use crate::settings::Settings;

/// What the main LED is doing.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Mode {
    Off,
    Level(Level),
    /// Exact current requested by the app (Status level 0xFF).
    Exact(u16),
}

/// How the MCU came out of reset.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct BootInfo {
    /// Woken from deep sleep by the button (GPIO3).
    pub woke_by_button: bool,
    /// Button level at the first sample.
    pub button_pressed: bool,
    /// Woken by the stuck-button re-check timer.
    pub woke_by_timer: bool,
}

/// One sample of the analog inputs and the charger status pins.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Sensors {
    /// Battery voltage, mV (already 2 x ADC).
    pub vbat_mv: u16,
    /// NTC node voltage, mV.
    pub ntc_mv: u16,
    /// TP4057 CHRG (GPIO4) reads low.
    pub chrg_low: bool,
    /// TP4057 STDBY (GPIO5) reads low.
    pub stdby_low: bool,
}

/// Requested advertising state.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum AdvMode {
    Off,
    /// 100 ms interval (first 30 s of a window).
    Fast,
    /// 500 ms interval.
    Slow,
    /// Presenter mode, HID keyboard advertising at 30 ms (first 30 s).
    HidFast,
    /// Presenter mode, HID keyboard advertising at 152.5 ms.
    HidSlow,
}

impl AdvMode {
    /// HID keyboard advertising (presenter mode).
    pub fn is_hid(self) -> bool {
        matches!(self, AdvMode::HidFast | AdvMode::HidSlow)
    }
}

/// Keys waiting for the Bluetooth task (fixed ring buffer).
#[derive(Clone, Copy, Debug)]
struct KeyQueue {
    buf: [HidKey; KEY_QUEUE_LEN],
    head: usize,
    len: usize,
}

impl KeyQueue {
    const fn new() -> Self {
        KeyQueue {
            buf: [HidKey::B; KEY_QUEUE_LEN],
            head: 0,
            len: 0,
        }
    }

    fn push(&mut self, k: HidKey) -> bool {
        if self.len == KEY_QUEUE_LEN {
            return false;
        }
        self.buf[(self.head + self.len) % KEY_QUEUE_LEN] = k;
        self.len += 1;
        true
    }

    fn pop(&mut self) -> Option<HidKey> {
        if self.len == 0 {
            return None;
        }
        let k = self.buf[self.head];
        self.head = (self.head + 1) % KEY_QUEUE_LEN;
        self.len -= 1;
        Some(k)
    }

    fn clear(&mut self) {
        self.len = 0;
    }
}

/// Everything the firmware has to apply after a [`Controller::tick`].
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Outputs {
    /// Main LED current (0 = LED_EN low). Set the duty first, then LED_EN.
    pub led_ma: u16,
    pub laser_on: bool,
    pub rgb: Rgb,
    pub charge_pin: ChargePin,
    pub adv: AdvMode,
    /// Everything is idle: enter deep sleep (after saving `save` if set).
    pub sleep: bool,
    /// Deep sleep wakes on the button (normal). `false` = the button is stuck
    /// (lockout, held >= 10 s): wake on the charger pins and on a timer
    /// ([`STUCK_RECHECK_MS`]) only.
    pub wake_on_button: bool,
    /// Write these settings to flash, then call [`Controller::saved`].
    pub save: Option<Settings>,
    /// Reboot (after saving) - factory reset.
    pub reboot: bool,
}

/// The light.
#[derive(Clone, Debug)]
pub struct Controller {
    settings: Settings,
    saved: Settings,
    save_pending: bool,

    mode: Mode,
    turbo_prev: Level,
    turbo_start: u64,
    turbo_expired: bool,
    source: ControlSource,
    app_lock_until: u64,

    gestures: GestureParser,
    slides: SlideParser,
    boot_timer_wake: bool,
    hold_steps: bool,
    laser_hold: bool,
    laser_start: u64,
    laser_blocked: bool,
    laser_on: bool,

    vbat_f16: i32,
    temp: TempReading,
    temp_f16: i32,
    temp_bad: u8,
    chrg_low: bool,
    stdby_low: bool,

    charger: Charger,
    lv: LowVoltage,
    thermal_shutdown: bool,
    soc: SocEstimator,
    rgb: RgbEngine,

    connected: bool,
    window_until: u64,
    adv_since: Option<u64>,

    led_ma: u16,
    thermal_active: bool,
    battery_active: bool,
    reboot: bool,
    boot_ms: u64,

    // presenter mode (v0.6)
    presenter: bool,
    /// A paired computer is connected and the link is encrypted.
    hid_connected: bool,
    bonded_hosts: u8,
    last_press: u64,
    presenter_low_since: Option<u64>,
    keys: KeyQueue,
    forget_request: bool,
    /// v0.7 board: the thermal regulator (instead of the linear derating).
    #[cfg(feature = "board-v07")]
    thermal_reg: crate::thermal::ThermalReg,
    /// v0.7: LED current through the same filter as the battery voltage (mA x 16), for the state
    /// of charge: a single cell sags so much that the unfiltered current would make the percentage
    /// jump for a second at every level change.
    #[cfg(feature = "board-v07")]
    soc_led_f16: i32,
}

impl Controller {
    /// `settings` = what was loaded from flash (or defaults), `now` = ms since boot.
    /// The button seen at the first sample is the main button if
    /// `boot.button_pressed` (v0.5 interface); see [`Controller::new_with_class`].
    pub fn new(settings: Settings, boot: BootInfo, now: u64) -> Self {
        let class = if boot.button_pressed { ButtonClass::Main } else { ButtonClass::None };
        Self::new_with_class(settings, boot, class, now)
    }

    /// Like [`Controller::new`], with the ladder class of the first ADC sample
    /// (the firmware knows which button woke it). `boot.button_pressed` is
    /// ignored; the main gesture parser starts pressed if `class` is Main.
    ///
    /// A wake-up whose press was already over at the first sample is taken as
    /// a click of the main button (as in v0.5): the chip cannot tell which
    /// button it was.
    pub fn new_with_class(settings: Settings, boot: BootInfo, class: ButtonClass, now: u64) -> Self {
        let main_pressed = class == ButtonClass::Main;
        let gestures = match (boot.woke_by_button, main_pressed, class) {
            (true, true, _) => GestureParser::new_pressed(now),
            (true, false, ButtonClass::None) => GestureParser::new_after_click(now),
            _ => GestureParser::new(now),
        };
        Controller {
            settings,
            saved: settings,
            save_pending: false,
            mode: Mode::Off,
            turbo_prev: settings.level,
            turbo_start: 0,
            turbo_expired: false,
            source: ControlSource::None,
            app_lock_until: 0,
            gestures,
            slides: SlideParser::new_with(class, now),
            boot_timer_wake: boot.woke_by_timer,
            hold_steps: false,
            laser_hold: false,
            laser_start: 0,
            laser_blocked: false,
            laser_on: false,
            vbat_f16: 0,
            temp: TempReading::Unknown,
            temp_f16: 0,
            temp_bad: 0,
            chrg_low: false,
            stdby_low: false,
            charger: Charger::new(),
            lv: LowVoltage::new(),
            thermal_shutdown: false,
            soc: SocEstimator::new(),
            rgb: RgbEngine::new(),
            connected: false,
            window_until: 0,
            adv_since: None,
            led_ma: 0,
            thermal_active: false,
            battery_active: false,
            reboot: false,
            boot_ms: now,
            presenter: false,
            hid_connected: false,
            bonded_hosts: 0,
            last_press: now,
            presenter_low_since: None,
            keys: KeyQueue::new(),
            forget_request: false,
            #[cfg(feature = "board-v07")]
            thermal_reg: crate::thermal::ThermalReg::new(),
            #[cfg(feature = "board-v07")]
            soc_led_f16: 0,
        }
    }

    // ------------------------------------------------------------ queries

    pub fn settings(&self) -> Settings {
        self.settings
    }

    pub fn profile(&self) -> Profile {
        self.settings.active_profile()
    }

    pub fn mode(&self) -> Mode {
        self.mode
    }

    pub fn is_on(&self) -> bool {
        self.mode != Mode::Off
    }

    /// A gesture is in progress: sample the button every 10 ms.
    pub fn button_busy(&self) -> bool {
        !self.gestures.is_idle() || !self.slides.is_idle()
    }

    /// Presenter mode is active.
    pub fn presenter_active(&self) -> bool {
        self.presenter
    }

    /// Mode for the Status packet.
    pub fn device_mode(&self) -> DeviceMode {
        match (self.presenter, self.hid_connected) {
            (false, _) => DeviceMode::Flashlight,
            (true, false) => DeviceMode::PresenterWaiting,
            (true, true) => DeviceMode::PresenterConnected,
        }
    }

    /// Next key to send to the computer (press + release), oldest first.
    pub fn take_key(&mut self) -> Option<HidKey> {
        self.keys.pop()
    }

    /// The paired computers are to be forgotten (button ‹ + › 10 s or
    /// FORGET_HOSTS). Returns `true` once per request.
    pub fn take_forget_hosts(&mut self) -> bool {
        core::mem::take(&mut self.forget_request)
    }

    /// Number of paired computers stored (reported in Status byte 19).
    pub fn set_bonded_hosts(&mut self, n: u8) {
        self.bonded_hosts = n;
    }

    pub fn bonded_hosts(&self) -> u8 {
        self.bonded_hosts
    }

    /// Presenter characteristic value.
    pub fn presenter_packet(&self) -> [u8; PRESENTER_LEN] {
        self.settings.presenter.encode()
    }

    /// Filtered battery voltage, mV (3700 before the first sample).
    pub fn vbat_mv(&self) -> u16 {
        if self.vbat_f16 == 0 {
            3_700
        } else {
            ((self.vbat_f16 + 8) / 16) as u16
        }
    }

    pub fn temperature(&self) -> TempReading {
        self.temp
    }

    pub fn battery_percent(&self) -> u8 {
        self.soc.percent()
    }

    pub fn usb_present(&self) -> bool {
        self.charger.usb_present()
    }

    pub fn connected(&self) -> bool {
        self.connected
    }

    /// Profile characteristic value: parameters of the active profile.
    pub fn profile_packet(&self) -> [u8; PROFILE_LEN] {
        self.profile().encode(self.settings.profile)
    }

    fn on_level(&self) -> Level {
        if self.profile().flags & FLAG_MEMORY != 0 {
            self.settings.level
        } else {
            Level::Low
        }
    }

    fn exact_in_turbo(p: &Profile, ma: u16) -> bool {
        p.has_turbo() && ma > p.stepdown_ma
    }

    fn in_turbo_region(&self) -> bool {
        let p = self.profile();
        match self.mode {
            Mode::Level(Level::Turbo) => p.has_turbo(),
            Mode::Exact(ma) => Self::exact_in_turbo(&p, ma.clamp(1, p.max_output_ma())),
            _ => false,
        }
    }

    fn turbo_running(&self) -> bool {
        self.in_turbo_region() && !self.turbo_expired
    }

    /// Turbo is refused within 5 degC of the profile limit (and without a valid temperature).
    fn turbo_temp_ok(&self) -> bool {
        let limit = self.profile().temp_limit_dc();
        matches!(self.temp, TempReading::Valid(t) if t < limit - TURBO_TEMP_MARGIN_DC)
    }

    /// The level the light is "at" for stepping and as turbo's return level.
    fn current_level(&self) -> Level {
        match self.mode {
            Mode::Level(l) if l != Level::Turbo => l,
            Mode::Level(_) => self.turbo_prev,
            _ => self.settings.level,
        }
    }

    // ------------------------------------------------------------ inputs

    /// Feed a raw sample of a single button (`true` = main button pressed);
    /// the v0.5 interface, same as `buttons(Main / None)`.
    pub fn button(&mut self, pressed: bool, now: u64) {
        self.buttons(if pressed { ButtonClass::Main } else { ButtonClass::None }, now);
    }

    /// Feed a raw ladder sample (class of the ADC reading of GPIO3).
    pub fn buttons(&mut self, raw: ButtonClass, now: u64) {
        let was_down = self.slides.level().is_pressed();
        let ev = self.gestures.update(raw == ButtonClass::Main, now);
        let sev = self.slides.update(raw, now);
        if !was_down && self.slides.level().is_pressed() {
            // any new press keeps presenter mode alive
            self.last_press = now;
        }
        for e in ev.as_slice() {
            self.on_gesture(*e, now);
        }
        for e in sev.as_slice() {
            self.on_slide(*e, now);
        }
    }

    /// Feed an analog / charger-pin sample (every ~100 ms).
    pub fn sensors(&mut self, s: Sensors, now: u64) {
        let _ = now;
        let v16 = s.vbat_mv as i32 * 16;
        self.vbat_f16 = if self.vbat_f16 == 0 {
            v16
        } else {
            self.vbat_f16 + (v16 - self.vbat_f16) / 8
        };
        match hw::ntc_temp(s.ntc_mv) {
            TempReading::Valid(t) => {
                self.temp_bad = 0;
                let t16 = t as i32 * 16;
                self.temp_f16 = if matches!(self.temp, TempReading::Valid(_)) {
                    self.temp_f16 + (t16 - self.temp_f16) / 4
                } else {
                    t16
                };
                self.temp = TempReading::Valid((self.temp_f16 / 16) as i16);
            }
            bad => {
                self.temp_bad = self.temp_bad.saturating_add(1);
                if self.temp_bad >= NTC_FAULT_SAMPLES || !matches!(self.temp, TempReading::Valid(_)) {
                    self.temp = bad;
                }
            }
        }
        self.chrg_low = s.chrg_low;
        self.stdby_low = s.stdby_low;
        #[cfg(feature = "board-v07")]
        {
            self.soc_led_f16 += (self.led_ma as i32 * 16 - self.soc_led_f16) / 8;
            self.update_thermal_reg();
        }
    }

    /// Presenter mode: the computer's link is up and encrypted (`true`) or
    /// gone (`false`). Keys are only queued while it is connected.
    pub fn hid_connected(&mut self, connected: bool, now: u64) {
        let connected = connected && self.presenter;
        if connected && !self.hid_connected {
            self.rgb.play(Shot::HostConnected, now);
        }
        if !connected {
            self.keys.clear();
        }
        self.hid_connected = connected;
    }

    /// A central connected / disconnected (any Bluetooth link, also the
    /// computer's in presenter mode).
    pub fn ble_connected(&mut self, connected: bool, now: u64) {
        if !connected && self.connected {
            self.window_until = self.window_until.max(now + BLE_WINDOW_AFTER_DISCONNECT_MS);
        }
        self.connected = connected;
    }

    /// The firmware stored `s` in flash.
    pub fn saved(&mut self, s: Settings) {
        self.saved = s;
        if self.settings == s {
            self.save_pending = false;
        }
    }

    // ------------------------------------------------------------ light actions

    fn switch_off(&mut self, src: ControlSource, now: u64, open_window: bool) {
        if !self.is_on() {
            return;
        }
        self.mode = Mode::Off;
        self.source = src;
        self.turbo_expired = false;
        self.hold_steps = false;
        self.lv.reset();
        if open_window {
            self.window_until = self.window_until.max(now + BLE_WINDOW_AFTER_OFF_MS);
        }
    }

    /// Change the mode of a light that may be off or on. `restart_turbo`:
    /// an explicit turbo request restarts an expired turbo timer.
    fn apply_mode(&mut self, mode: Mode, src: ControlSource, now: u64, restart_turbo: bool) {
        let was_on = self.is_on();
        let was_turbo = self.in_turbo_region();
        self.mode = mode;
        self.source = src;
        self.lv.reset();
        if self.in_turbo_region() && (!was_turbo || (restart_turbo && self.turbo_expired)) {
            self.turbo_start = now;
            self.turbo_expired = false;
        }
        if !self.in_turbo_region() {
            self.turbo_expired = false;
        }
        if !was_on && self.is_on() && self.profile().flags & FLAG_SHOW_BATTERY != 0 {
            self.rgb.show_battery(self.soc.percent(), now);
        }
    }

    fn try_switch_on(&mut self, mode: Mode, src: ControlSource, now: u64) -> Result<(), CmdError> {
        if self.settings.lockout {
            return Err(CmdError::Lockout);
        }
        if self.thermal_shutdown || self.temp == TempReading::Short || self.settings.empty_latch {
            return Err(CmdError::Protection);
        }
        self.apply_mode(mode, src, now, true);
        Ok(())
    }

    /// Button switch-on with feedback on refusal. Returns true if the light is on.
    fn button_on(&mut self, mode: Mode, now: u64) -> bool {
        match self.try_switch_on(mode, ControlSource::Button, now) {
            Ok(()) => true,
            Err(_) => {
                let shot = if self.settings.empty_latch { Shot::Empty } else { Shot::Refused };
                self.rgb.play(shot, now);
                false
            }
        }
    }

    /// Re-apply the level table after a profile change (no turbo restart).
    fn reapply(&mut self, was_turbo: bool, now: u64) {
        if self.in_turbo_region() && !was_turbo {
            self.turbo_start = now;
            self.turbo_expired = false;
        }
        if !self.in_turbo_region() {
            self.turbo_expired = false;
        }
        if let Mode::Exact(ma) = self.mode {
            self.mode = Mode::Exact(ma.clamp(1, self.profile().max_output_ma()));
        }
    }

    fn start_laser(&mut self, now: u64) {
        self.laser_hold = true;
        self.laser_start = now;
        self.laser_blocked = !protection::laser_permitted(self.temp, self.vbat_mv(), self.settings.lockout);
        if self.laser_blocked {
            self.rgb.play(Shot::Refused, now);
        }
    }

    fn stop_laser(&mut self) {
        self.laser_hold = false;
        self.laser_blocked = false;
        self.laser_on = false;
    }

    fn set_lockout(&mut self, locked: bool, src: ControlSource, now: u64) {
        self.source = src;
        if locked {
            if self.presenter {
                self.leave_presenter(src, now);
            }
            self.switch_off(src, now, true);
            if self.laser_hold {
                self.laser_blocked = true;
                self.laser_on = false;
            }
        }
        if self.settings.lockout != locked {
            self.settings.lockout = locked;
            self.save_pending = true;
        }
        self.rgb.play(if locked { Shot::Locked } else { Shot::Unlocked }, now);
    }

    // ------------------------------------------------------------ presenter mode

    fn enter_presenter(&mut self, src: ControlSource, now: u64) -> Result<(), CmdError> {
        if self.settings.lockout {
            return Err(CmdError::Lockout);
        }
        if self.vbat_mv() < PRESENTER_MIN_MV {
            return Err(CmdError::Protection);
        }
        if self.presenter {
            return Ok(());
        }
        // the main LED goes off; no app window (the radio switches to HID)
        self.switch_off(src, now, false);
        self.presenter = true;
        self.hid_connected = false;
        self.keys.clear();
        self.last_press = now;
        self.presenter_low_since = None;
        self.adv_since = None;
        self.source = src;
        self.rgb.play(Shot::PresenterToggle, now);
        Ok(())
    }

    fn leave_presenter(&mut self, src: ControlSource, now: u64) {
        if !self.presenter {
            return;
        }
        self.presenter = false;
        self.hid_connected = false;
        self.keys.clear();
        self.adv_since = None;
        self.source = src;
        self.rgb.play(Shot::PresenterToggle, now);
    }

    fn forget_hosts(&mut self, now: u64) {
        self.forget_request = true;
        self.bonded_hosts = 0;
        self.rgb.play(Shot::HostsForgotten, now);
    }

    /// Queue a key for the computer (only while one is connected).
    fn send_key(&mut self, action: PresenterAction, now: u64) {
        if !self.presenter || !self.hid_connected {
            return;
        }
        let key = self.settings.presenter.key(action);
        if self.keys.push(key) {
            self.rgb.play(Shot::KeySent, now);
        }
    }

    /// Handle a Presenter characteristic write (values clamped; read back to
    /// see what is used). Not blocked by the button priority: it neither
    /// switches nor dims the light.
    pub fn presenter_write(&mut self, data: &[u8], now: u64) -> Result<(), CmdError> {
        let _ = now;
        let p = PresenterSettings::decode_write(data)?;
        self.settings.presenter = p;
        Ok(())
    }

    // ------------------------------------------------------------ slide buttons

    fn on_slide(&mut self, e: SlideEvent, now: u64) {
        // lockout: everything except ● 4 clicks is ignored, without feedback
        if self.settings.lockout {
            return;
        }
        match e {
            SlideEvent::Both2s => {
                self.app_lock_until = now + APP_LOCK_MS;
                if self.presenter {
                    self.leave_presenter(ControlSource::Button, now);
                } else if self.enter_presenter(ControlSource::Button, now).is_err() {
                    self.rgb.play(Shot::Refused, now);
                }
            }
            SlideEvent::Both10s => {
                self.app_lock_until = now + APP_LOCK_MS;
                self.forget_hosts(now);
            }
            SlideEvent::Click(b) | SlideEvent::Hold(b) if self.presenter => {
                self.app_lock_until = now + APP_LOCK_MS;
                let b = if self.settings.presenter.swap { b.swapped() } else { b };
                let action = match (e, b) {
                    (SlideEvent::Click(_), Slide::Next) => PresenterAction::NextSlide,
                    (SlideEvent::Click(_), Slide::Prev) => PresenterAction::PreviousSlide,
                    (_, Slide::Next) => PresenterAction::StartShow,
                    (_, Slide::Prev) => PresenterAction::EndShow,
                };
                self.send_key(action, now);
            }
            SlideEvent::Click(b) | SlideEvent::Hold(b) => {
                // › / ‹ while off: ignored (no light, no LED, no app lock)
                if !self.is_on() {
                    return;
                }
                self.app_lock_until = now + APP_LOCK_MS;
                if let Mode::Exact(_) = self.mode {
                    let l = self.settings.level;
                    self.apply_mode(Mode::Level(l), ControlSource::Button, now, false);
                }
                let Mode::Level(cur) = self.mode else { return };
                let next = match b {
                    Slide::Next => cur.slide_up(),
                    Slide::Prev => cur.slide_down(),
                };
                self.source = ControlSource::Button;
                if let Some(l) = next {
                    self.apply_mode(Mode::Level(l), ControlSource::Button, now, false);
                    self.settings.level = l;
                }
            }
        }
    }

    // ------------------------------------------------------------ button UI

    fn on_gesture(&mut self, e: GestureEvent, now: u64) {
        use GestureEvent::*;
        // Every button action locks out app commands for 3 s.
        self.app_lock_until = now + APP_LOCK_MS;
        match e {
            Press | Release => return,
            HoldEnd(_) => {
                self.hold_steps = false;
                if self.laser_hold {
                    self.stop_laser();
                }
                return;
            }
            _ => {}
        }

        if self.settings.lockout {
            match e {
                Clicks(4) if !self.is_on() => self.set_lockout(false, ControlSource::Button, now),
                // feedback for clicks only: a button pressed in a pocket stays dark
                Clicks(_) => self.rgb.play(Shot::LockedPress, now),
                _ => {}
            }
            return;
        }

        if self.presenter {
            match e {
                Clicks(1) => self.send_key(PresenterAction::BlackScreen, now),
                // pocket safety: four clicks always lock (and leave presenter mode)
                Clicks(4) => self.set_lockout(true, ControlSource::Button, now),
                // laser while held, same rules as in flashlight mode
                HoldStart(_) => self.start_laser(now),
                _ => {}
            }
            return;
        }

        if self.is_on() {
            // A button action cancels an app-selected exact current.
            if matches!(e, Clicks(_) | HoldStart(_))
                && let Mode::Exact(_) = self.mode
            {
                let l = self.settings.level;
                self.apply_mode(Mode::Level(l), ControlSource::Button, now, false);
            }
            match e {
                Clicks(1) => {
                    self.switch_off(ControlSource::Button, now, true);
                    self.save_pending = true;
                }
                Clicks(2) => self.button_turbo_toggle(now),
                Clicks(3) => {
                    self.source = ControlSource::Button;
                    self.rgb.play(Shot::battery(self.soc.percent()), now);
                }
                HoldStart(0) | HoldStart(1) => {
                    self.hold_steps = true;
                    self.button_step(now);
                }
                HoldRepeat(_) if self.hold_steps => self.button_step(now),
                _ => {}
            }
        } else {
            match e {
                Clicks(1) => {
                    let l = self.on_level();
                    self.button_on(Mode::Level(l), now);
                }
                HoldStart(0) => {
                    let on = self.button_on(Mode::Level(Level::Moon), now);
                    if on {
                        self.settings.level = Level::Moon;
                    }
                }
                Clicks(2) => self.button_turbo_from_off(now),
                HoldStart(1) => self.start_laser(now),
                Clicks(3) => {
                    self.window_until = self.window_until.max(now + BLE_WINDOW_TRIPLE_CLICK_MS);
                    self.rgb.play(Shot::BtWindow, now);
                }
                Clicks(4) => self.set_lockout(true, ControlSource::Button, now),
                _ => {}
            }
        }
    }

    fn button_step(&mut self, now: u64) {
        let next = self.current_level().next_in_cycle();
        let next = if matches!(self.mode, Mode::Level(Level::Turbo)) { Level::Low } else { next };
        self.apply_mode(Mode::Level(next), ControlSource::Button, now, false);
        self.settings.level = next;
    }

    fn button_turbo_toggle(&mut self, now: u64) {
        if self.mode == Mode::Level(Level::Turbo) {
            let prev = self.turbo_prev;
            self.apply_mode(Mode::Level(prev), ControlSource::Button, now, false);
            return;
        }
        if self.profile().has_turbo() && !self.turbo_temp_ok() {
            self.rgb.play(Shot::Refused, now);
            return;
        }
        self.turbo_prev = self.current_level();
        self.apply_mode(Mode::Level(Level::Turbo), ControlSource::Button, now, true);
    }

    fn button_turbo_from_off(&mut self, now: u64) {
        self.turbo_prev = self.on_level();
        if self.profile().has_turbo() && !self.turbo_temp_ok() {
            if self.button_on(Mode::Level(Level::High), now) {
                self.rgb.play(Shot::Refused, now);
            }
            return;
        }
        self.button_on(Mode::Level(Level::Turbo), now);
    }

    // ------------------------------------------------------------ app interface

    /// Handle a Command characteristic write. `Err` = ATT application error.
    pub fn command(&mut self, data: &[u8], now: u64) -> Result<(), CmdError> {
        let cmd = protocol::decode_command(data)?;
        if cmd.yields_to_button() && now < self.app_lock_until {
            return Err(CmdError::ButtonPriority);
        }
        if self.presenter && cmd.switches_on() {
            return Err(CmdError::Invalid);
        }
        let p = self.profile();
        match cmd {
            Command::Presenter(true) => self.enter_presenter(ControlSource::App, now),
            Command::Presenter(false) => {
                self.leave_presenter(ControlSource::App, now);
                Ok(())
            }
            Command::ForgetHosts => {
                self.forget_hosts(now);
                Ok(())
            }
            Command::Off => {
                self.switch_off(ControlSource::App, now, true);
                Ok(())
            }
            Command::On => {
                if self.is_on() {
                    return Ok(());
                }
                let l = self.on_level();
                self.try_switch_on(Mode::Level(l), ControlSource::App, now)
            }
            Command::Level(l) => {
                if self.settings.lockout {
                    return Err(CmdError::Lockout);
                }
                if l == Level::Turbo && p.has_turbo() && !self.turbo_running() && !self.turbo_temp_ok() {
                    return Err(CmdError::Protection);
                }
                if l == Level::Turbo && self.mode != Mode::Level(Level::Turbo) {
                    self.turbo_prev = if self.is_on() { self.current_level() } else { self.on_level() };
                }
                if self.is_on() {
                    self.apply_mode(Mode::Level(l), ControlSource::App, now, true);
                } else {
                    self.try_switch_on(Mode::Level(l), ControlSource::App, now)?;
                }
                if l.is_memorable() {
                    self.settings.level = l;
                }
                Ok(())
            }
            Command::Profile(id) => {
                let was_turbo = self.in_turbo_region();
                self.settings.profile = id;
                self.source = ControlSource::App;
                self.lv.reset();
                self.reapply(was_turbo, now);
                Ok(())
            }
            Command::OutputMa(ma) => {
                if self.settings.lockout {
                    return Err(CmdError::Lockout);
                }
                if ma == 0 {
                    return Err(CmdError::Invalid);
                }
                let ma = ma.clamp(1, p.max_output_ma());
                if Self::exact_in_turbo(&p, ma) && !self.turbo_running() && !self.turbo_temp_ok() {
                    return Err(CmdError::Protection);
                }
                if self.is_on() {
                    self.apply_mode(Mode::Exact(ma), ControlSource::App, now, true);
                    Ok(())
                } else {
                    self.try_switch_on(Mode::Exact(ma), ControlSource::App, now)
                }
            }
            Command::Lockout(locked) => {
                self.set_lockout(locked, ControlSource::App, now);
                Ok(())
            }
            Command::Identify => {
                self.rgb.play(Shot::Identify, now);
                Ok(())
            }
            Command::Save => {
                self.save_pending = true;
                Ok(())
            }
            Command::KeepAlive(s) => {
                let s = (s as u64).min(BLE_KEEPALIVE_MAX_S);
                self.window_until = self.window_until.max(now + s * 1_000);
                Ok(())
            }
            Command::FactoryReset => {
                self.leave_presenter(ControlSource::App, now);
                self.switch_off(ControlSource::App, now, false);
                self.stop_laser();
                // settings only: paired computers are kept (FORGET_HOSTS forgets them)
                self.settings = Settings::default();
                self.save_pending = true;
                self.reboot = true;
                Ok(())
            }
        }
    }

    /// Handle a Profile characteristic write (always the Custom profile, which
    /// is then selected). Values are clamped; read back to see what is used.
    pub fn profile_write(&mut self, data: &[u8], now: u64) -> Result<(), CmdError> {
        let custom = Profile::decode_write(data)?;
        if now < self.app_lock_until {
            return Err(CmdError::ButtonPriority);
        }
        let was_turbo = self.in_turbo_region();
        self.settings.custom = custom;
        self.settings.profile = ProfileId::Custom;
        self.source = ControlSource::App;
        self.lv.reset();
        self.reapply(was_turbo, now);
        Ok(())
    }

    // ------------------------------------------------------------ periodic

    fn requested_ma(&self) -> u16 {
        let p = self.profile();
        match self.mode {
            Mode::Off => 0,
            Mode::Level(Level::Turbo) => {
                if !p.has_turbo() {
                    p.high_ma
                } else if self.turbo_expired {
                    p.stepdown_ma
                } else {
                    p.turbo_ma
                }
            }
            Mode::Level(l) => p.level_ma(l),
            Mode::Exact(ma) => {
                let ma = ma.clamp(1, p.max_output_ma());
                if self.turbo_expired && Self::exact_in_turbo(&p, ma) {
                    p.stepdown_ma
                } else {
                    ma
                }
            }
        }
    }

    /// Apply every limit. Returns (current, thermal limit active, battery limit active).
    fn limited_ma(&self, req: u16) -> (u16, bool, bool) {
        if req == 0 {
            return (0, false, false);
        }
        let p = self.profile();
        let mut out = req;
        let mut thermal = false;
        let mut battery = false;
        if let Some(cap) = self.lv.cap() {
            let c = p.level_ma(cap);
            if c < out {
                out = c;
                battery = true;
            }
        }
        match self.temp {
            TempReading::Valid(t) => {
                #[cfg(not(feature = "board-v07"))]
                let c = protection::thermal_cap_ma(t, p.temp_limit_dc(), out, p.low_ma, p.moon_ma);
                // v0.7: the regulator's limit; above 70 / 80 degC Moon / off as in the protocol
                #[cfg(feature = "board-v07")]
                let c = protection::thermal_cap_ma(
                    t,
                    THERMAL_OFF_DC,
                    self.thermal_reg.cap_ma(out, p.low_ma),
                    p.low_ma,
                    p.moon_ma,
                );
                if c < out {
                    out = c;
                    thermal = true;
                }
            }
            // No usable temperature: never above High.
            TempReading::Open | TempReading::Unknown => {
                if p.high_ma < out {
                    out = p.high_ma;
                    thermal = true;
                }
            }
            TempReading::Short => {
                out = 0;
                thermal = true;
            }
        }
        let c = battery::max_led_ma_for_cell(self.vbat_mv(), p.cell_limit_ma);
        if c < out {
            out = c;
            battery = true;
        }
        (out, thermal, battery)
    }

    /// Run the periodic logic and return what the hardware should do.
    pub fn tick(&mut self, now: u64) -> Outputs {
        let p = self.profile();
        let vbat = self.vbat_mv();

        // thermal shutdown (> 80 degC or shorted sensor)
        let hot = match self.temp {
            TempReading::Valid(t) => t > THERMAL_OFF_DC,
            TempReading::Short => true,
            _ => false,
        };
        if hot && !self.thermal_shutdown {
            self.thermal_shutdown = true;
            self.switch_off(ControlSource::Auto, now, true);
        }
        if self.thermal_shutdown && matches!(self.temp, TempReading::Valid(t) if t < THERMAL_OFF_CLEAR_DC) {
            self.thermal_shutdown = false;
        }

        // turbo timer
        if self.turbo_running() && now.saturating_sub(self.turbo_start) >= p.turbo_time_s as u64 * 1_000 {
            self.turbo_expired = true;
            self.source = ControlSource::Auto;
        }

        // laser: while the gesture is held, at most 60 s, protection rules
        if self.laser_hold
            && !self.laser_blocked
            && (now.saturating_sub(self.laser_start) >= LASER_MAX_MS
                || !protection::laser_permitted(self.temp, vbat, self.settings.lockout))
        {
            self.laser_blocked = true;
        }
        self.laser_on = self.laser_hold && !self.laser_blocked;

        // presenter mode ends after the idle time and when the battery is empty
        if self.presenter {
            if now.saturating_sub(self.last_press) >= self.settings.presenter.idle_ms() {
                self.leave_presenter(ControlSource::Auto, now);
            } else if vbat < PRESENTER_MIN_MV {
                let since = *self.presenter_low_since.get_or_insert(now);
                if now - since >= PRESENTER_EMPTY_DELAY_MS {
                    self.leave_presenter(ControlSource::Auto, now);
                    self.rgb.play(Shot::Empty, now);
                }
            } else {
                self.presenter_low_since = None;
            }
        }

        // main LED with all limits; the low-voltage rule looks at what is driven
        let (out, _, _) = self.limited_ma(self.requested_ma());
        match self.lv.update(now, vbat, p.lv_stepdown_mv(), p.level_for_current(out), self.is_on()) {
            LvEvent::Empty => {
                // window rule 2 applies to every switch-off, also this one
                self.switch_off(ControlSource::Auto, now, true);
                self.settings.empty_latch = true;
                self.save_pending = true;
                self.rgb.play(Shot::Empty, now);
            }
            LvEvent::CapChanged => self.source = ControlSource::Auto,
            LvEvent::None => {}
        }
        let (out, thermal, battery_lim) = self.limited_ma(self.requested_ma());
        if (thermal && !self.thermal_active) || (battery_lim && !self.battery_active) {
            self.source = ControlSource::Auto;
        }
        self.thermal_active = thermal;
        self.battery_active = battery_lim;
        self.led_ma = out;

        // charger and USB
        let pin = self.charger.update(now, self.chrg_low, self.stdby_low, self.temp, out);
        let usb = self.charger.usb_present();

        // empty latch: released above 3.30 V at rest or with USB
        if self.settings.empty_latch && !self.is_on() && (usb || vbat >= LV_RECOVER_MV) {
            self.settings.empty_latch = false;
        }

        // state of charge
        #[cfg(not(feature = "board-v07"))]
        let soc_led = out;
        #[cfg(feature = "board-v07")]
        let soc_led = ((self.soc_led_f16 + 8) / 16) as u16;
        self.soc.update(
            now,
            vbat,
            soc_led,
            ChargeInfo {
                usb_present: usb,
                fast_charging: self.charger.fast_charging(),
                complete: self.charger.complete(),
            },
        );

        // Bluetooth window and advertising
        let window = self.is_on() || usb || self.connected || now < self.window_until;
        let adv = if self.presenter {
            // presenter mode: keyboard advertising whenever no computer is linked
            if self.connected {
                self.adv_since = None;
                AdvMode::Off
            } else {
                let since = *self.adv_since.get_or_insert(now);
                if now - since < HID_ADV_FAST_PERIOD_MS { AdvMode::HidFast } else { AdvMode::HidSlow }
            }
        } else if window && !self.connected {
            let since = *self.adv_since.get_or_insert(now);
            if now - since < ADV_FAST_PERIOD_MS { AdvMode::Fast } else { AdvMode::Slow }
        } else {
            self.adv_since = None;
            AdvMode::Off
        };

        let rgb = self.rgb.render(
            &RgbContext {
                usb_present: usb,
                charging: self.charger.charging(),
                charge_complete: self.charger.complete(),
                window_open: window,
                connected: self.connected,
                light_on: self.is_on(),
                soc_pct: self.soc.percent(),
                laser_on: self.laser_on,
                presenter: self.presenter,
                host_connected: self.hid_connected,
            },
            now,
        );

        // A button held while it does nothing (lockout, or a slide button with
        // the light off; e.g. pressed in a pocket) must not keep the MCU awake.
        let stuck_after = if self.boot_timer_wake { STUCK_BUTTON_AFTER_WAKE_MS } else { STUCK_BUTTON_MS };
        let stuck = !self.is_on()
            && !self.laser_hold
            && !self.presenter
            && self.slides.down_since().is_some_and(|t| now.saturating_sub(t) >= stuck_after);
        let sleep = !self.is_on()
            && !self.laser_hold
            && !self.presenter
            && !window
            && !usb
            && ((self.gestures.is_idle() && self.slides.is_idle()) || stuck)
            && !self.rgb.busy(now)
            && now.saturating_sub(self.boot_ms)
                >= if self.boot_timer_wake { MIN_AWAKE_TIMER_WAKE_MS } else { MIN_AWAKE_MS }
            && !self.reboot;

        if self.settings == self.saved {
            self.save_pending = false;
        }
        let save = ((self.save_pending || sleep || self.reboot) && self.settings != self.saved)
            .then_some(self.settings);

        Outputs {
            led_ma: out,
            laser_on: self.laser_on,
            rgb,
            charge_pin: pin,
            adv,
            sleep,
            wake_on_button: !stuck,
            save,
            reboot: self.reboot,
        }
    }

    /// The Status characteristic.
    pub fn status(&self, now: u64) -> Status {
        let p = self.profile();
        let mut flags = 0u8;
        if self.is_on() {
            flags |= sf::LIGHT_ON;
        }
        let turbo = self.turbo_running();
        if turbo {
            flags |= sf::TURBO_ACTIVE;
        }
        if self.charger.charging() {
            flags |= sf::CHARGING;
        }
        if self.charger.complete() {
            flags |= sf::CHARGE_COMPLETE;
        }
        if self.charger.usb_present() {
            flags |= sf::USB_POWER;
        }
        if self.settings.lockout {
            flags |= sf::LOCKOUT;
        }
        if self.thermal_active || self.thermal_shutdown {
            flags |= sf::THERMAL_LIMIT;
        }
        if self.battery_active || self.settings.empty_latch {
            flags |= sf::BATTERY_LIMIT;
        }
        let level = match self.mode {
            Mode::Off => self.on_level() as u8,
            Mode::Level(Level::Turbo) if !p.has_turbo() => Level::High as u8,
            Mode::Level(l) => l as u8,
            Mode::Exact(_) => LEVEL_EXACT,
        };
        let turbo_left_s = if turbo {
            let total = p.turbo_time_s as u64 * 1_000;
            div_ceil(total.saturating_sub(now.saturating_sub(self.turbo_start)), 1_000) as u16
        } else {
            0
        };
        let app_lock_s = div_ceil(self.app_lock_until.saturating_sub(now), 1_000) as u8;
        let vbat = self.vbat_mv();
        let runtime_min = if self.is_on() {
            battery::runtime_minutes(self.soc.soc_x10(), battery::total_cell_current_ma(self.led_ma, vbat))
        } else {
            RUNTIME_UNKNOWN
        };
        #[cfg(not(feature = "board-v07"))]
        let led_ma = self.led_ma;
        // v0.7: the current the LED really gets - a sagging cell can leave the buck short of the
        // request (turbo from a half-full cell)
        #[cfg(feature = "board-v07")]
        let led_ma = battery::deliverable_led_ma(self.led_ma, vbat);
        Status {
            flags,
            profile: self.settings.profile as u8,
            level,
            led_ma,
            vbat_mv: vbat,
            soc_pct: self.soc.percent(),
            temp_dc: self.temp.report_dc(),
            turbo_left_s,
            source: self.source,
            app_lock_s,
            runtime_min,
            laser_on: self.laser_on,
            mode: self.device_mode(),
            bonded_hosts: self.bonded_hosts,
        }
    }
}

/// v0.7 board: feed the thermal regulator ([`crate::thermal`]) with every temperature sample.
#[cfg(feature = "board-v07")]
impl Controller {
    fn update_thermal_reg(&mut self) {
        let p = self.profile();
        let mut req = self.requested_ma();
        if let Some(cap) = self.lv.cap() {
            req = req.min(p.level_ma(cap));
        }
        match self.temp {
            TempReading::Valid(_) => self.thermal_reg.update(self.temp_f16, p.temp_limit_dc(), req, p.low_ma),
            _ => self.thermal_reg.invalidate(),
        }
    }

    /// The regulator's filtered temperature (0.1 degC) and rate of rise (0.1 degC/s), for tests.
    pub fn thermal_regulator(&self) -> (i32, i32) {
        (self.thermal_reg.temperature_dc(), self.thermal_reg.rate_dc_per_s())
    }
}

#[cfg(test)]
#[allow(clippy::field_reassign_with_default)]
mod tests {
    use super::*;
    use crate::hw::ntc_mv_at;
    use crate::protocol::opcode;

    /// The default (Balanced) profile of the board the tests are built for. Tests that only need
    /// "the default profile's current" read it here, so they run unchanged on both boards
    /// (v0.6: 3 / 30 / 200 / 600 mA, turbo 1200 mA for 60 s, 50 degC; v0.7: 3 / 40 / 250 /
    /// 1530 mA, turbo 2850 mA for 60 s, 50 degC).
    const BAL: Profile = Profile::BALANCED;

    /// OUTPUT_MA command bytes for a current.
    fn output_ma(ma: u16) -> [u8; 3] {
        let b = ma.to_le_bytes();
        [opcode::OUTPUT_MA, b[0], b[1]]
    }

    /// Simulated hardware around the controller.
    struct Sim {
        c: Controller,
        t: u64,
        pressed: bool,
        vbat: u16,
        temp_c: f32,
        chrg: bool,
        stdby: bool,
        out: Outputs,
        saves: Vec<Settings>,
        max_laser_ms: u64,
        laser_since: Option<u64>,
        /// v0.6: ladder class fed instead of `pressed` when set.
        class: Option<ButtonClass>,
        /// v0.6: keys taken from the controller (as the BLE task would).
        keys: Vec<HidKey>,
    }

    impl Sim {
        fn new() -> Sim {
            Sim::with(Settings::default(), BootInfo::default())
        }

        fn with(s: Settings, boot: BootInfo) -> Sim {
            Sim::build(s, boot, 3_900)
        }

        /// Start with a given (resting) battery voltage.
        fn build(s: Settings, boot: BootInfo, vbat: u16) -> Sim {
            let c = Controller::new(s, boot, 0);
            let mut sim = Sim {
                c,
                t: 0,
                pressed: boot.button_pressed,
                vbat,
                temp_c: 25.0,
                chrg: false,
                stdby: false,
                out: Outputs {
                    led_ma: 0,
                    laser_on: false,
                    rgb: Rgb::OFF,
                    charge_pin: ChargePin::Float,
                    adv: AdvMode::Off,
                    sleep: false,
                    wake_on_button: true,
                    save: None,
                    reboot: false,
                },
                saves: Vec::new(),
                max_laser_ms: 0,
                laser_since: None,
                class: None,
                keys: Vec::new(),
            };
            sim.sample();
            sim.out = sim.c.tick(0);
            sim
        }

        fn sample(&mut self) {
            let s = Sensors {
                vbat_mv: self.vbat,
                ntc_mv: ntc_mv_at(self.temp_c),
                chrg_low: self.chrg,
                stdby_low: self.stdby,
            };
            self.c.sensors(s, self.t);
        }

        /// Advance time in 10 ms steps.
        fn run(&mut self, ms: u64) {
            let end = self.t + ms;
            while self.t < end {
                self.t += 10;
                match self.class {
                    Some(c) => self.c.buttons(c, self.t),
                    None => self.c.button(self.pressed, self.t),
                }
                if self.t.is_multiple_of(100) {
                    self.sample();
                }
                self.out = self.c.tick(self.t);
                if let Some(s) = self.out.save {
                    self.saves.push(s);
                    self.c.saved(s);
                }
                while let Some(k) = self.c.take_key() {
                    self.keys.push(k);
                }
                if self.out.laser_on {
                    let since = *self.laser_since.get_or_insert(self.t);
                    self.max_laser_ms = self.max_laser_ms.max(self.t - since);
                } else {
                    self.laser_since = None;
                }
            }
        }

        fn press(&mut self, ms: u64) {
            self.pressed = true;
            self.run(ms);
            self.pressed = false;
        }

        fn click(&mut self) {
            self.press(120);
            self.run(150);
        }

        /// n clicks and wait until the gesture completes.
        fn clicks(&mut self, n: usize) {
            for _ in 0..n {
                self.click();
            }
            self.run(500);
        }

        fn cmd(&mut self, data: &[u8]) -> Result<(), CmdError> {
            let r = self.c.command(data, self.t);
            self.run(10);
            r
        }

        fn status(&self) -> Status {
            self.c.status(self.t)
        }

        /// Hold a ladder class for `ms`, then release and wait `after` ms.
        fn ladder(&mut self, c: ButtonClass, ms: u64, after: u64) {
            self.class = Some(c);
            self.run(ms);
            self.class = Some(ButtonClass::None);
            self.run(after);
            self.class = None;
        }

        fn slide_click(&mut self, c: ButtonClass) {
            self.ladder(c, 150, 100);
        }

        /// ‹ + › for `ms`.
        fn both(&mut self, ms: u64) {
            self.ladder(ButtonClass::Both, ms, 100);
        }

        /// Enter presenter mode with ‹ + › and connect a computer.
        fn presenter_connected(&mut self) {
            self.both(2_100);
            assert!(self.c.presenter_active());
            self.c.ble_connected(true, self.t);
            self.c.hid_connected(true, self.t);
            self.run(1_000);
        }
    }

    // -------------------------------------------------------------- button UI

    #[test]
    fn click_on_and_off_with_memory() {
        let mut s = Sim::new();
        assert_eq!(s.out.led_ma, 0);
        s.clicks(1);
        assert_eq!(s.c.mode(), Mode::Level(Level::Low)); // default remembered level
        assert_eq!(s.out.led_ma, BAL.low_ma); // v0.6: 30 mA
        assert_eq!(s.status().source, ControlSource::Button);
        // step to Medium with a hold, then off: Medium is remembered and saved
        s.press(500);
        s.run(200);
        assert_eq!(s.c.mode(), Mode::Level(Level::Medium));
        s.clicks(1);
        assert!(!s.c.is_on());
        assert_eq!(s.saves.last().unwrap().level, Level::Medium);
        s.clicks(1);
        assert_eq!(s.c.mode(), Mode::Level(Level::Medium));
    }

    #[test]
    fn hold_from_off_is_moon_and_does_not_step() {
        let mut s = Sim::new();
        s.press(3_000);
        assert_eq!(s.c.mode(), Mode::Level(Level::Moon));
        s.run(500);
        assert_eq!(s.c.mode(), Mode::Level(Level::Moon));
        assert_eq!(s.out.led_ma, 3);
    }

    #[test]
    fn hold_steps_every_600ms() {
        let mut s = Sim::new();
        s.clicks(1); // Low
        s.pressed = true;
        s.run(450); // hold detected at ~425 -> Medium
        assert_eq!(s.c.mode(), Mode::Level(Level::Medium));
        s.run(600); // High
        assert_eq!(s.c.mode(), Mode::Level(Level::High));
        s.run(600); // Low
        assert_eq!(s.c.mode(), Mode::Level(Level::Low));
        s.run(600); // Medium
        assert_eq!(s.c.mode(), Mode::Level(Level::Medium));
        s.pressed = false;
        s.run(1_000);
        assert_eq!(s.c.mode(), Mode::Level(Level::Medium));
    }

    #[test]
    fn double_click_turbo_with_timer_and_stepdown() {
        let mut s = Sim::new(); // Balanced: 1200 mA (v0.7: 3000) for 60 s, then 600 (v0.7: 1530)
        assert_eq!(BAL.turbo_time_s, 60);
        s.clicks(2);
        assert_eq!(s.c.mode(), Mode::Level(Level::Turbo));
        assert_eq!(s.out.led_ma, BAL.turbo_ma);
        let st = s.status();
        assert_ne!(st.flags & sf::TURBO_ACTIVE, 0);
        assert_eq!(st.level, 4);
        assert!((59..=60).contains(&st.turbo_left_s), "{}", st.turbo_left_s);
        s.run(30_000);
        assert!((29..=30).contains(&s.status().turbo_left_s));
        s.run(31_000);
        assert_eq!(s.out.led_ma, BAL.stepdown_ma);
        let st = s.status();
        assert_eq!(st.flags & sf::TURBO_ACTIVE, 0);
        assert_eq!(st.turbo_left_s, 0);
        assert_eq!(st.source, ControlSource::Auto);
        // two clicks: back to the previous level (Low)
        s.clicks(2);
        assert_eq!(s.c.mode(), Mode::Level(Level::Low));
    }

    #[test]
    fn turbo_toggle_from_on() {
        let mut s = Sim::new();
        s.clicks(1);
        s.press(500); // Medium
        s.run(300);
        s.clicks(2);
        assert_eq!(s.c.mode(), Mode::Level(Level::Turbo));
        s.clicks(2);
        assert_eq!(s.c.mode(), Mode::Level(Level::Medium));
    }

    #[test]
    fn turbo_without_turbo_profile_is_high() {
        let mut st = Settings::default();
        st.profile = ProfileId::Endurance;
        let mut s = Sim::with(st, BootInfo::default());
        s.clicks(2);
        assert_eq!(s.out.led_ma, Profile::ENDURANCE.high_ma); // v0.6: 300 mA
        assert_eq!(s.status().level, Level::High as u8);
        assert_eq!(s.status().flags & sf::TURBO_ACTIVE, 0);
    }

    #[test]
    fn turbo_refused_near_temperature_limit() {
        let mut s = Sim::new(); // limit 50 degC (both boards)
        s.temp_c = BAL.temp_limit_c as f32 - 4.0; // v0.6: 46 degC
        s.run(2_000);
        s.clicks(2); // from off: High instead of turbo + red blink
        assert_eq!(s.c.mode(), Mode::Level(Level::High));
        s.run(3_100);
        assert_eq!(s.cmd(&[opcode::LEVEL, 4]), Err(CmdError::Protection));
        assert_eq!(s.cmd(&output_ma(BAL.turbo_ma)), Err(CmdError::Protection)); // turbo > stepdown
        assert_eq!(s.cmd(&output_ma(BAL.stepdown_ma)), Ok(())); // stepdown is fine
        s.temp_c = BAL.temp_limit_c as f32 - 10.0; // v0.6: 40 degC
        s.run(2_000);
        assert_eq!(s.cmd(&[opcode::LEVEL, 4]), Ok(()));
    }

    #[test]
    fn triple_click_opens_window_light_stays_off() {
        let mut s = Sim::new();
        s.run(2_000);
        assert_eq!(s.out.adv, AdvMode::Off);
        assert!(s.out.sleep);
        s.clicks(3);
        assert!(!s.c.is_on());
        assert_eq!(s.out.adv, AdvMode::Fast);
        assert!(!s.out.sleep);
        s.run(30_000);
        assert_eq!(s.out.adv, AdvMode::Slow);
        s.run(90_000);
        assert_eq!(s.out.adv, AdvMode::Off);
        s.run(100);
        assert!(s.out.sleep);
    }

    #[test]
    fn lockout_toggle_and_only_four_clicks_work() {
        let mut s = Sim::new();
        s.clicks(4);
        assert!(s.c.settings().lockout);
        assert!(s.saves.last().unwrap().lockout, "lockout is persisted");
        assert_eq!(s.status().flags & sf::LOCKOUT, sf::LOCKOUT);
        s.clicks(1);
        assert!(!s.c.is_on());
        s.clicks(2);
        assert!(!s.c.is_on());
        s.clicks(3);
        assert_eq!(s.out.adv, AdvMode::Off, "triple click does nothing in lockout");
        s.press(1_000);
        s.run(500);
        assert!(!s.c.is_on());
        // laser gesture does nothing
        s.click();
        s.press(2_000);
        assert!(!s.out.laser_on);
        s.run(500);
        assert_eq!(s.cmd(&[opcode::ON]).err(), Some(CmdError::ButtonPriority));
        s.run(3_100);
        assert_eq!(s.cmd(&[opcode::ON]), Err(CmdError::Lockout));
        assert_eq!(s.cmd(&[opcode::LEVEL, 2]), Err(CmdError::Lockout));
        assert_eq!(s.cmd(&[opcode::OUTPUT_MA, 100, 0]), Err(CmdError::Lockout));
        s.clicks(4);
        assert!(!s.c.settings().lockout);
        s.clicks(1);
        assert!(s.c.is_on());
    }

    #[test]
    fn laser_click_hold_max_60s() {
        let mut s = Sim::new();
        s.click();
        s.pressed = true;
        s.run(1_000);
        assert!(s.out.laser_on);
        assert!(!s.c.is_on(), "main LED stays off");
        s.run(70_000);
        assert!(!s.out.laser_on, "60 s limit");
        assert!(s.max_laser_ms <= 60_000 + 20, "{}", s.max_laser_ms);
        s.pressed = false;
        s.run(500);
        // again
        s.click();
        s.pressed = true;
        s.run(1_000);
        assert!(s.out.laser_on);
        s.pressed = false;
        s.run(50);
        assert!(!s.out.laser_on, "off when released");
    }

    #[test]
    fn laser_protection_rules() {
        let mut s = Sim::new();
        s.temp_c = 61.0;
        s.run(3_000);
        s.click();
        s.press(1_000);
        assert!(!s.out.laser_on, "too hot");
        s.temp_c = 30.0;
        s.vbat = 3_150;
        s.run(5_000);
        s.click();
        s.press(1_000);
        assert!(!s.out.laser_on, "battery too low");
        s.vbat = 3_800;
        s.run(5_000);
        s.click();
        s.pressed = true;
        s.run(1_000);
        assert!(s.out.laser_on);
        s.temp_c = 65.0;
        s.run(3_000);
        assert!(!s.out.laser_on, "switched off when it gets hot");
        s.temp_c = 30.0;
        s.run(3_000);
        assert!(!s.out.laser_on, "stays off for the rest of this hold");
        s.pressed = false;
        s.run(100);
    }

    #[test]
    fn laser_never_from_ble() {
        let mut s = Sim::new();
        // no opcode exists for the laser; every opcode other than the defined ones is invalid
        // (v0.6: 0x0A PRESENTER and 0x0B FORGET_HOSTS are defined now; neither touches the laser)
        assert_eq!(s.c.command(&[opcode::PRESENTER], s.t), Err(CmdError::Invalid));
        assert_eq!(s.c.command(&[opcode::FORGET_HOSTS, 1], s.t), Err(CmdError::Invalid));
        for op in 0x0cu8..=0x7e {
            assert_eq!(s.c.command(&[op], s.t), Err(CmdError::Invalid));
            assert_eq!(s.c.command(&[op, 1], s.t), Err(CmdError::Invalid));
        }
        s.run(100);
        assert!(!s.out.laser_on);
    }

    // -------------------------------------------------------------- app

    #[test]
    fn app_commands_basic() {
        let mut s = Sim::new();
        s.run(100);
        assert_eq!(s.cmd(&[opcode::ON]), Ok(()));
        assert_eq!(s.out.led_ma, BAL.low_ma);
        assert_eq!(s.status().source, ControlSource::App);
        assert_eq!(s.cmd(&[opcode::LEVEL, 3]), Ok(()));
        assert_eq!(s.out.led_ma, BAL.high_ma);
        assert_eq!(s.cmd(&[opcode::PROFILE, 0]), Ok(()));
        assert_eq!(s.out.led_ma, Profile::EXTREME.high_ma, "level re-applied with the new table");
        assert_eq!(s.status().profile, 0);
        assert_eq!(s.cmd(&[opcode::OFF]), Ok(()));
        assert!(!s.c.is_on());
        assert_eq!(s.out.adv, AdvMode::Fast, "120 s window after off");
        assert_eq!(s.cmd(&[0x55]), Err(CmdError::Invalid));
        assert_eq!(s.cmd(&[opcode::LEVEL, 9]), Err(CmdError::Invalid));
    }

    #[test]
    fn button_priority_3s() {
        let mut s = Sim::new();
        s.clicks(1);
        // gesture completed ~400 ms ago; lock lasts 3 s from the last action
        assert_eq!(s.cmd(&[opcode::OFF]), Err(CmdError::ButtonPriority));
        assert_eq!(s.cmd(&[opcode::PROFILE, 2]), Err(CmdError::ButtonPriority));
        let st = s.status();
        assert!((1..=3).contains(&st.app_lock_s), "{}", st.app_lock_s);
        // commands that do not switch or dim are accepted
        assert_eq!(s.cmd(&[opcode::IDENTIFY]), Ok(()));
        assert_eq!(s.cmd(&[opcode::KEEPALIVE, 10]), Ok(()));
        assert_eq!(s.cmd(&[opcode::SAVE]), Ok(()));
        s.run(3_000);
        assert_eq!(s.status().app_lock_s, 0);
        assert_eq!(s.cmd(&[opcode::OFF]), Ok(()));
    }

    #[test]
    fn exact_current_clamped_and_cancelled_by_button() {
        let mut s = Sim::new();
        s.run(100);
        assert_eq!(s.cmd(&[opcode::OUTPUT_MA, 0x10, 0x27]), Ok(())); // 10000 mA
        assert_eq!(s.c.mode(), Mode::Exact(BAL.turbo_ma)); // clamped to the turbo current
        assert_eq!(s.status().level, LEVEL_EXACT);
        assert_eq!(s.out.led_ma, BAL.turbo_ma);
        assert_ne!(s.status().flags & sf::TURBO_ACTIVE, 0, "above step-down: turbo timer runs");
        s.run(61_000);
        assert_eq!(s.out.led_ma, BAL.stepdown_ma, "stepped down after the turbo time");
        assert_eq!(s.cmd(&[opcode::OUTPUT_MA, 0, 0]), Err(CmdError::Invalid));
        assert_eq!(s.cmd(&[opcode::OUTPUT_MA, 77, 0]), Ok(()));
        assert_eq!(s.out.led_ma, 77);
        assert_eq!(s.status().flags & sf::TURBO_ACTIVE, 0);
        // a button action cancels the exact current: hold steps from the remembered level
        s.press(500);
        s.run(200);
        assert_eq!(s.c.mode(), Mode::Level(Level::Medium));
    }

    #[test]
    fn profile_write_clamps_and_selects_custom() {
        let mut s = Sim::new();
        s.run(100);
        let mut p = Profile::EXTREME;
        p.turbo_ma = 5_000;
        p.temp_limit_c = 90;
        let pkt = p.encode(ProfileId::Custom);
        assert_eq!(s.c.profile_write(&pkt, s.t), Ok(()));
        let back = s.c.profile_packet();
        assert_eq!(back[0], 3);
        let (_, rp) = Profile::decode_raw(&back);
        #[cfg(not(feature = "board-v07"))]
        assert_eq!(rp.turbo_ma, 3_000);
        #[cfg(feature = "board-v07")]
        assert_eq!(rp.turbo_ma, 2_850, "v0.7: Custom turbo clamped to 2850 mA");
        assert_eq!(rp.temp_limit_c, 70);
        assert_eq!(s.status().profile, 3);
        // wrong id / length
        let bad = Profile::BALANCED.encode(ProfileId::Balanced);
        assert_eq!(s.c.profile_write(&bad, s.t), Err(CmdError::Invalid));
        assert_eq!(s.c.profile_write(&pkt[..10], s.t), Err(CmdError::Invalid));
        // reading returns the active profile
        assert_eq!(s.cmd(&[opcode::PROFILE, 2]), Ok(()));
        assert_eq!(s.c.profile_packet(), Profile::ENDURANCE.encode(ProfileId::Endurance));
    }

    #[test]
    fn save_only_when_changed() {
        let mut s = Sim::new();
        s.run(100);
        assert_eq!(s.cmd(&[opcode::SAVE]), Ok(()));
        s.run(100);
        assert!(s.saves.is_empty(), "defaults were not changed");
        assert_eq!(s.cmd(&[opcode::PROFILE, 0]), Ok(()));
        assert_eq!(s.cmd(&[opcode::SAVE]), Ok(()));
        s.run(100);
        assert_eq!(s.saves.len(), 1);
        assert_eq!(s.saves[0].profile, ProfileId::Extreme);
        assert_eq!(s.cmd(&[opcode::SAVE]), Ok(()));
        s.run(100);
        assert_eq!(s.saves.len(), 1);
    }

    #[test]
    fn factory_reset() {
        let mut st = Settings::default();
        st.profile = ProfileId::Custom;
        st.custom.high_ma = 1_500;
        st.lockout = true;
        let mut s = Sim::with(st, BootInfo::default());
        assert_eq!(s.cmd(&[opcode::FACTORY_RESET, 0x00]), Err(CmdError::Invalid));
        assert_eq!(s.cmd(&[opcode::FACTORY_RESET, 0xa5]), Ok(()));
        assert!(s.out.reboot);
        assert_eq!(*s.saves.last().unwrap(), Settings::default());
    }

    #[test]
    fn keepalive_and_disconnect_windows() {
        let mut s = Sim::new();
        s.clicks(3); // 120 s window
        s.c.ble_connected(true, s.t);
        s.run(200_000);
        assert_eq!(s.out.adv, AdvMode::Off, "no advertising while connected");
        assert!(!s.out.sleep, "connected keeps the window open");
        s.c.ble_connected(false, s.t);
        s.run(100);
        assert_eq!(s.out.adv, AdvMode::Fast, "30 s after disconnect");
        assert_eq!(s.cmd(&[opcode::KEEPALIVE, 200]), Ok(()));
        s.run(150_000);
        assert_ne!(s.out.adv, AdvMode::Off);
        s.run(51_000);
        assert_eq!(s.out.adv, AdvMode::Off);
    }

    // -------------------------------------------------------------- protection

    #[cfg(not(feature = "board-v07"))]
    #[test]
    fn thermal_derating_and_shutdown() {
        let mut s = Sim::new();
        s.run(100);
        s.cmd(&[opcode::LEVEL, 3]).unwrap(); // High 600, limit 50
        s.temp_c = BAL.temp_limit_c as f32 + 7.5; // halfway into the 15 degC span
        s.run(3_000);
        let ma = s.out.led_ma;
        let mid = (BAL.high_ma + BAL.low_ma) / 2; // v0.6: 315 mA
        assert!((mid - 15..=mid + 15).contains(&ma), "{ma}");
        assert_ne!(s.status().flags & sf::THERMAL_LIMIT, 0);
        assert_eq!(s.status().source, ControlSource::Auto);
        s.temp_c = 72.0;
        s.run(3_000);
        assert_eq!(s.out.led_ma, 3, "Moon above 70");
        s.temp_c = 82.0;
        s.run(3_000);
        assert!(!s.c.is_on(), "off above 80");
        s.run(3_100);
        assert_eq!(s.cmd(&[opcode::ON]), Err(CmdError::Protection));
        s.temp_c = 74.0;
        s.run(3_000);
        assert_eq!(s.cmd(&[opcode::ON]), Ok(()));
    }

    /// v0.7 board: the limit is the regulator's set point ([`crate::thermal`]). Within the band
    /// just below it the current is held; above it the current falls (at once by the P part, then
    /// steadily) down to Low, never below; Moon above 70 and off above 80 degC as on the v0.6.
    #[cfg(feature = "board-v07")]
    #[test]
    fn thermal_regulation_and_shutdown() {
        let mut s = Sim::new();
        s.temp_c = BAL.temp_limit_c as f32 - 0.1; // 49.9 degC: within the band
        s.run(30_000); // light off: the regulator's filters settle (no rate of rise left)
        s.cmd(&[opcode::LEVEL, 3]).unwrap(); // High 1530 mA, limit 50 degC
        s.run(60_000);
        assert_eq!(s.out.led_ma, BAL.high_ma, "held within the band below the limit");
        assert_eq!(s.status().flags & sf::THERMAL_LIMIT, 0);
        s.temp_c = BAL.temp_limit_c as f32 + 1.0; // 1 degC too hot
        s.run(3_000);
        let ma = s.out.led_ma;
        assert!(ma < BAL.high_ma - 300 && ma > BAL.low_ma, "{ma}");
        assert_ne!(s.status().flags & sf::THERMAL_LIMIT, 0);
        assert_eq!(s.status().source, ControlSource::Auto);
        s.run(10_000); // (the sudden step of the reading looks like a fast rise for a few seconds)
        let mut last = s.out.led_ma;
        for _ in 0..60 {
            s.run(1_000);
            assert!(s.out.led_ma <= last, "falls steadily while too hot");
            last = s.out.led_ma;
        }
        assert_eq!(s.out.led_ma, BAL.low_ma, "still too hot after a minute: Low, not less");
        // a request at or below Low is never reduced (as on the v0.6)
        s.cmd(&[opcode::LEVEL, 0]).unwrap();
        s.run(5_000);
        assert_eq!(s.out.led_ma, BAL.moon_ma);
        s.cmd(&[opcode::LEVEL, 3]).unwrap();
        s.temp_c = 72.0;
        s.run(3_000);
        assert_eq!(s.out.led_ma, 3, "Moon above 70");
        s.temp_c = 82.0;
        s.run(3_000);
        assert!(!s.c.is_on(), "off above 80");
        s.run(3_100);
        assert_eq!(s.cmd(&[opcode::ON]), Err(CmdError::Protection));
        s.temp_c = 74.0;
        s.run(3_000);
        assert_eq!(s.cmd(&[opcode::ON]), Ok(()));
        // cool again: the full current comes back
        s.temp_c = 30.0;
        s.run(10_000);
        s.cmd(&[opcode::LEVEL, 3]).unwrap();
        s.run(1_000);
        assert_eq!(s.out.led_ma, BAL.high_ma);
        assert_eq!(s.status().flags & sf::THERMAL_LIMIT, 0);
    }

    #[test]
    fn low_voltage_steps_moon_and_empty_latch() {
        let mut s = Sim::new(); // Balanced: step-down 3.35 V (v0.7: 3.20 V)
        s.run(100);
        s.cmd(&[opcode::LEVEL, 3]).unwrap();
        s.vbat = BAL.lv_stepdown_mv() - 50;
        // the filtered voltage crosses the threshold about 2 s later
        #[cfg(not(feature = "board-v07"))]
        assert_eq!(BAL.lv_stepdown_mv(), 3_350);
        #[cfg(feature = "board-v07")]
        assert_eq!(BAL.lv_stepdown_mv(), 3_200);
        s.run(2_000);
        assert_eq!(s.out.led_ma, BAL.high_ma);
        s.run(4_500);
        assert_eq!(s.out.led_ma, BAL.high_ma, "not before 5 s below the threshold");
        s.run(1_000);
        assert_eq!(s.out.led_ma, BAL.medium_ma, "one step after 5 s");
        assert_ne!(s.status().flags & sf::BATTERY_LIMIT, 0);
        assert_eq!(s.status().source, ControlSource::Auto);
        s.run(5_000);
        assert_eq!(s.out.led_ma, BAL.low_ma, "next step 5 s later");
        s.vbat = 3_050;
        s.run(3_000);
        assert_eq!(s.out.led_ma, BAL.moon_ma, "Moon below 3.10 V");
        s.vbat = 2_950;
        s.run(4_000);
        assert!(!s.c.is_on(), "off below 3.00 V");
        assert!(s.c.settings().empty_latch);
        assert!(s.saves.last().unwrap().empty_latch, "latch persisted for deep sleep");
        assert_ne!(s.out.adv, AdvMode::Off, "the 120 s window opens after every switch-off");
        s.vbat = 3_250; // rests at 3.25 V: still refused
        s.run(5_000);
        s.clicks(1);
        assert!(!s.c.is_on());
        s.run(3_100);
        assert_eq!(s.cmd(&[opcode::ON]), Err(CmdError::Protection));
        s.vbat = 3_350;
        s.run(5_000);
        assert!(!s.c.settings().empty_latch);
        s.clicks(1);
        assert!(s.c.is_on());
    }

    #[test]
    fn empty_latch_released_by_usb() {
        let mut st = Settings::default();
        st.empty_latch = true;
        let mut s = Sim::build(st, BootInfo::default(), 3_200);
        s.run(1_000);
        s.clicks(1);
        assert!(!s.c.is_on());
        s.chrg = true;
        s.run(500);
        assert!(!s.c.settings().empty_latch);
        s.clicks(1);
        assert!(s.c.is_on());
    }

    #[test]
    fn cell_current_limit() {
        let mut st = Settings::default();
        st.profile = ProfileId::Custom;
        st.custom.cell_limit_ma = 500;
        let mut s = Sim::build(st, BootInfo::default(), 3_700);
        s.run(1_000);
        s.cmd(&[opcode::LEVEL, 4]).unwrap();
        s.run(500);
        let ma = s.out.led_ma;
        let cell = battery::led_cell_current_ma(ma, s.c.vbat_mv());
        assert!(cell <= 500 && ma < 1_200, "ma={ma} cell={cell}");
        assert_ne!(s.status().flags & sf::BATTERY_LIMIT, 0);
    }

    #[test]
    fn ntc_open_limits_to_high_and_blocks_charging() {
        let mut s = Sim::new();
        s.temp_c = -30.0; // reads as open
        s.chrg = true;
        s.run(1_000);
        assert_eq!(s.c.temperature(), TempReading::Open);
        assert_eq!(s.out.charge_pin, ChargePin::High);
        s.run(3_100);
        assert_eq!(s.cmd(&[opcode::LEVEL, 4]), Err(CmdError::Protection));
        assert_eq!(s.cmd(&[opcode::OUTPUT_MA, 0x58, 0x02]), Ok(()));
        assert_eq!(s.out.led_ma, 600);
    }

    // -------------------------------------------------------------- charging, RGB, sleep

    #[test]
    fn charging_and_pause_above_500ma() {
        let mut s = Sim::new();
        s.chrg = true;
        s.run(500);
        assert!(s.c.usb_present());
        assert_eq!(s.out.charge_pin, ChargePin::Low);
        let st = s.status();
        assert_eq!(st.flags & (sf::USB_POWER | sf::CHARGING), sf::USB_POWER | sf::CHARGING);
        assert_ne!(s.out.adv, AdvMode::Off, "USB keeps the window open");
        assert!(s.out.rgb.r > 0 && s.out.rgb.g == 0, "red breathing");
        s.run(3_000);
        s.cmd(&[opcode::LEVEL, 4]).unwrap(); // 1200 mA
        s.run(200);
        assert_eq!(s.out.charge_pin, ChargePin::High);
        s.cmd(&[opcode::LEVEL, 1]).unwrap();
        s.run(200);
        assert_eq!(s.out.charge_pin, ChargePin::Low);
        // complete
        s.chrg = false;
        s.stdby = true;
        s.cmd(&[opcode::OFF]).unwrap();
        s.run(500);
        assert_ne!(s.status().flags & sf::CHARGE_COMPLETE, 0);
        assert_eq!(s.out.rgb, Rgb::GREEN.scale(120));
        // unplugged
        s.stdby = false;
        s.run(1_500);
        assert!(!s.c.usb_present());
        assert_eq!(s.out.charge_pin, ChargePin::Float);
    }

    #[test]
    fn battery_display_on_switch_on() {
        let mut s = Sim::new();
        s.vbat = 4_100;
        s.run(3_000);
        s.clicks(1);
        assert_eq!(s.out.rgb, Rgb::GREEN, "battery colour for 2 s");
        s.run(2_000);
        assert_ne!(s.out.rgb, Rgb::GREEN);
    }

    #[test]
    fn sleep_conditions() {
        let mut s = Sim::new();
        s.run(1_000);
        assert!(!s.out.sleep, "minimum awake time");
        s.run(600);
        assert!(s.out.sleep);
        s.clicks(1);
        assert!(!s.out.sleep);
        s.clicks(1);
        assert!(!s.out.sleep, "120 s window after switch-off");
        s.run(119_000);
        assert!(!s.out.sleep);
        s.run(1_500);
        assert!(s.out.sleep);
        s.chrg = true;
        s.run(200);
        assert!(!s.out.sleep, "USB present");
    }

    #[test]
    fn stuck_button_in_lockout_sleeps_without_button_wake() {
        let mut st = Settings::default();
        st.lockout = true;
        let mut s = Sim::with(st, BootInfo::default());
        s.run(2_000);
        assert!(s.out.sleep && s.out.wake_on_button);
        s.pressed = true; // pressed in a pocket
        s.run(5_000);
        assert!(!s.out.sleep, "a press may be a real gesture");
        assert_eq!(s.out.rgb, Rgb::OFF, "no feedback for a hold in lockout");
        s.run(6_000);
        assert!(s.out.sleep, "stuck after 10 s");
        assert!(!s.out.wake_on_button);
        // after the re-check timer wake with the button still pressed: back to sleep quickly
        let mut s = Sim::with(
            st,
            BootInfo {
                woke_by_button: false,
                button_pressed: true,
                woke_by_timer: true,
            },
        );
        s.pressed = true;
        s.run(300);
        assert!(!s.out.sleep);
        s.run(200);
        assert!(s.out.sleep && !s.out.wake_on_button);
        // released meanwhile: normal sleep with button wake
        s.pressed = false;
        s.run(500);
        assert!(s.out.sleep && s.out.wake_on_button);
        // not in lockout a held button switches the light on (Moon) - no sleep
        let mut s = Sim::new();
        s.pressed = true;
        s.run(15_000);
        assert!(s.c.is_on() && !s.out.sleep);
    }

    #[test]
    fn wake_by_button_click_turns_on() {
        // woken by a click that was already over at the first sample
        let mut s = Sim::with(
            Settings::default(),
            BootInfo {
                woke_by_button: true,
                button_pressed: false,
                woke_by_timer: false,
            },
        );
        s.run(600);
        assert!(s.c.is_on());
        // woken by a hold
        let mut s = Sim::with(
            Settings::default(),
            BootInfo {
                woke_by_button: true,
                button_pressed: true,
                woke_by_timer: false,
            },
        );
        s.pressed = true;
        s.run(600);
        assert_eq!(s.c.mode(), Mode::Level(Level::Moon));
    }

    #[test]
    fn status_when_off() {
        let s = Sim::new();
        let st = s.status();
        assert_eq!(st.flags & sf::LIGHT_ON, 0);
        assert_eq!(st.led_ma, 0);
        assert_eq!(st.runtime_min, RUNTIME_UNKNOWN);
        assert_eq!(st.level, Level::Low as u8);
        assert_eq!(st.profile, 1);
        assert_eq!(st.source, ControlSource::None);
        assert!(!st.laser_on);
    }

    #[test]
    fn runtime_estimate_when_on() {
        let mut s = Sim::build(Settings::default(), BootInfo::default(), 3_800); // 50 %
        s.run(1_000);
        s.cmd(&[opcode::LEVEL, 3]).unwrap(); // 600 mA (v0.7: 1530 mA)
        s.run(500);
        let st = s.status();
        // 400 mAh / (2.84 V*0.6 A/(0.9*3.8 V) + 20 mA) = 400 / 518 mA = 46 min
        #[cfg(not(feature = "board-v07"))]
        assert!((40..=52).contains(&st.runtime_min), "{}", st.runtime_min);
        // v0.7 (F15 curve: 3.8 V = 63 %): 1400 mAh x 63 % / (3.03 V*1.53 A/(0.87*3.8 V) + 20 mA)
        // = 886 / 1422 mA = 37 min
        #[cfg(feature = "board-v07")]
        assert!((34..=41).contains(&st.runtime_min), "{}", st.runtime_min);
    }

    // -------------------------------------------------------------- v0.6: slide buttons in flashlight mode

    use crate::buttons::ButtonClass as B;
    use crate::rgb::breath;

    #[test]
    fn slides_step_levels_without_wrap() {
        let mut s = Sim::new();
        s.clicks(1);
        assert_eq!(s.c.mode(), Mode::Level(Level::Low));
        s.run(3_100);
        s.slide_click(B::Next);
        assert_eq!(s.c.mode(), Mode::Level(Level::Medium));
        assert_eq!(s.status().source, ControlSource::Button);
        assert_eq!(s.cmd(&[opcode::LEVEL, 1]), Err(CmdError::ButtonPriority), "counts as a button action");
        s.slide_click(B::Next);
        assert_eq!(s.c.mode(), Mode::Level(Level::High));
        s.slide_click(B::Next);
        assert_eq!(s.c.mode(), Mode::Level(Level::High), "no wrap, no turbo");
        for want in [Level::Medium, Level::Low, Level::Moon, Level::Moon] {
            s.slide_click(B::Prev);
            assert_eq!(s.c.mode(), Mode::Level(want));
        }
        assert_eq!(s.out.led_ma, 3);
        // the level is remembered
        s.clicks(1);
        assert_eq!(s.saves.last().unwrap().level, Level::Moon);
    }

    #[test]
    fn slide_hold_steps_once() {
        let mut s = Sim::new();
        s.clicks(1);
        s.ladder(B::Next, 3_000, 100);
        assert_eq!(s.c.mode(), Mode::Level(Level::Medium), "one step at 0.8 s, no repeat");
    }

    #[test]
    fn slides_from_turbo() {
        let mut s = Sim::new();
        s.clicks(2);
        assert_eq!(s.c.mode(), Mode::Level(Level::Turbo));
        s.slide_click(B::Next);
        assert_eq!(s.c.mode(), Mode::Level(Level::Turbo), "› does nothing in turbo");
        s.slide_click(B::Prev);
        assert_eq!(s.c.mode(), Mode::Level(Level::High), "‹ goes to High");
        assert_eq!(s.out.led_ma, BAL.high_ma);
    }

    #[test]
    fn slides_ignored_while_off() {
        let mut s = Sim::new();
        s.run(2_000);
        s.slide_click(B::Next);
        s.ladder(B::Prev, 1_500, 100);
        assert!(!s.c.is_on());
        assert_eq!(s.out.rgb, Rgb::OFF, "no LED feedback");
        assert_eq!(s.out.adv, AdvMode::Off);
        assert_eq!(s.cmd(&[opcode::ON]), Ok(()), "no app lock either");
    }

    #[test]
    fn slide_cancels_app_current() {
        let mut s = Sim::new();
        s.run(100);
        assert_eq!(s.cmd(&[opcode::OUTPUT_MA, 77, 0]), Ok(()));
        s.slide_click(B::Next);
        // back to the remembered level (Low), then one step up
        assert_eq!(s.c.mode(), Mode::Level(Level::Medium));
    }

    #[test]
    fn slides_in_lockout_do_nothing() {
        let mut s = Sim::new();
        s.clicks(4);
        assert!(s.c.settings().lockout);
        s.run(2_000);
        s.slide_click(B::Next);
        s.both(2_500);
        assert!(!s.c.presenter_active(), "‹ + › ignored in lockout");
        s.both(10_500);
        assert!(!s.c.take_forget_hosts(), "forget ignored in lockout");
        assert!(!s.c.is_on());
    }

    #[test]
    fn main_button_wins_over_slides() {
        let mut s = Sim::new();
        s.clicks(1); // Low
        s.run(500);
        // › held, ● clicked meanwhile, › released: one main click (off), no step
        s.class = Some(B::Next);
        s.run(200);
        s.class = Some(B::Main);
        s.run(120);
        s.class = Some(B::Next);
        s.run(200);
        s.class = Some(B::None);
        s.run(600);
        s.class = None;
        assert!(!s.c.is_on(), "the main click switched the light off");
        s.clicks(1);
        assert_eq!(s.c.mode(), Mode::Level(Level::Low), "no level step from the slide press");
    }

    // -------------------------------------------------------------- v0.6: presenter mode

    #[test]
    fn both_2s_enters_and_leaves_presenter() {
        let mut s = Sim::new();
        s.clicks(1);
        assert!(s.c.is_on());
        s.class = Some(B::Both);
        s.run(1_900);
        assert!(!s.c.presenter_active(), "not before 2 s");
        s.run(300);
        assert!(s.c.presenter_active());
        assert!(!s.c.is_on(), "the main LED goes off");
        assert_eq!(s.out.led_ma, 0);
        assert_eq!(s.out.rgb, Rgb::MAGENTA, "magenta x2");
        s.class = Some(B::None);
        s.run(100);
        s.class = None;
        assert_eq!(s.out.adv, AdvMode::HidFast);
        assert_eq!(s.status().mode, DeviceMode::PresenterWaiting);
        s.run(1_000);
        assert_eq!(s.out.rgb, Rgb::CYAN.scale(breath(s.t, 2_000)), "cyan breathing while waiting");
        s.run(30_000);
        assert_eq!(s.out.adv, AdvMode::HidSlow);
        assert!(!s.out.sleep, "presenter mode keeps the radio on");
        // ● click does not switch the light on in presenter mode
        s.clicks(1);
        assert!(!s.c.is_on());
        // leave with ‹ + › 2 s
        s.both(2_100);
        assert!(!s.c.presenter_active());
        assert_eq!(s.status().mode, DeviceMode::Flashlight);
        assert!(!s.c.is_on());
        s.run(3_000);
        assert!(s.out.sleep, "back to normal sleep");
    }

    #[test]
    fn presenter_keys() {
        let mut s = Sim::new();
        s.presenter_connected();
        assert_eq!(s.status().mode, DeviceMode::PresenterConnected);
        s.slide_click(B::Next);
        s.slide_click(B::Prev);
        s.ladder(B::Next, 1_500, 100); // hold: F5 once at 0.8 s
        s.ladder(B::Prev, 3_000, 100); // hold: Esc once
        s.clicks(1); // ● click: B
        s.clicks(2); // ● double click: nothing
        assert_eq!(
            s.keys,
            vec![HidKey::PageDown, HidKey::PageUp, HidKey::F5, HidKey::Escape, HidKey::B]
        );
        assert!(!s.out.laser_on);
        assert!(!s.c.is_on());
    }

    #[test]
    fn presenter_key_blip_and_connect_blink() {
        let mut s = Sim::new();
        s.both(2_100);
        s.run(1_000);
        s.c.ble_connected(true, s.t);
        s.c.hid_connected(true, s.t);
        s.run(10);
        assert_eq!(s.out.rgb, Rgb::CYAN, "double blink on connect");
        s.run(1_000);
        assert_eq!(s.out.rgb, Rgb::OFF, "then off");
        // white 40 ms blip right after the key
        s.class = Some(B::Next);
        s.run(150);
        s.class = Some(B::None);
        // the click counts when the release is debounced (25 ms, 10 ms sampling)
        s.run(50);
        assert_eq!(s.out.rgb, Rgb::WHITE);
        s.run(40);
        assert_eq!(s.out.rgb, Rgb::OFF);
        s.class = None;
    }

    #[test]
    fn presenter_key_settings() {
        let mut s = Sim::new();
        s.run(100);
        assert_eq!(s.c.presenter_write(&[1, 45, 1, 0], s.t), Ok(()));
        assert_eq!(s.c.presenter_packet(), [1, 45, 1, 0]);
        assert_eq!(s.c.presenter_write(&[5, 45, 1, 0], s.t), Err(CmdError::Invalid));
        assert_eq!(s.c.presenter_packet(), [1, 45, 1, 0], "refused write changes nothing");
        s.presenter_connected();
        // arrows, › and ‹ swapped
        s.slide_click(B::Next);
        s.slide_click(B::Prev);
        s.ladder(B::Next, 1_000, 100);
        assert_eq!(s.keys, vec![HidKey::Left, HidKey::Right, HidKey::Escape]);
        // SAVE stores the presenter settings
        s.run(3_100);
        assert_eq!(s.cmd(&[opcode::SAVE]), Ok(()));
        s.run(20);
        assert_eq!(s.saves.last().unwrap().presenter.encode(), [1, 45, 1, 0]);
    }

    #[test]
    fn no_keys_without_a_computer() {
        let mut s = Sim::new();
        s.both(2_100);
        s.slide_click(B::Next);
        s.clicks(1);
        assert!(s.keys.is_empty(), "nothing is queued while waiting");
        // a link that is not encrypted yet does not count
        s.c.ble_connected(true, s.t);
        s.slide_click(B::Next);
        assert!(s.keys.is_empty());
        s.c.hid_connected(true, s.t);
        s.slide_click(B::Next);
        assert_eq!(s.keys, vec![HidKey::PageDown]);
        // after a disconnect: waiting again, advertising again
        s.c.hid_connected(false, s.t);
        s.c.ble_connected(false, s.t);
        s.run(20);
        assert_eq!(s.status().mode, DeviceMode::PresenterWaiting);
        assert_eq!(s.out.adv, AdvMode::HidFast);
        // hid_connected outside presenter mode is ignored
        s.both(2_100);
        s.c.hid_connected(true, s.t);
        assert_eq!(s.status().mode, DeviceMode::Flashlight);
    }

    #[test]
    fn presenter_laser_with_and_without_host() {
        let mut s = Sim::new();
        s.both(2_100);
        // ● hold = laser while held, no computer needed
        s.pressed = true;
        s.run(1_000);
        assert!(s.out.laser_on);
        assert!(!s.c.is_on());
        assert_eq!(s.out.rgb, Rgb::RED, "ring red while the laser is on");
        s.run(70_000);
        assert!(!s.out.laser_on, "60 s limit as in v0.5");
        assert!(s.max_laser_ms <= 60_000 + 20);
        s.pressed = false;
        s.run(200);
        assert!(!s.out.laser_on);
        // with a computer: same, and no key is sent for the hold
        s.c.ble_connected(true, s.t);
        s.c.hid_connected(true, s.t);
        s.pressed = true;
        s.run(1_000);
        assert!(s.out.laser_on);
        s.pressed = false;
        s.run(50);
        assert!(!s.out.laser_on, "off when released");
        assert!(s.keys.is_empty());
        // too hot: refused
        s.temp_c = 62.0;
        s.run(3_000);
        s.pressed = true;
        s.run(1_000);
        assert!(!s.out.laser_on, "too hot");
        s.pressed = false;
        s.run(100);
    }

    #[test]
    fn presenter_four_clicks_lock_and_leave() {
        let mut s = Sim::new();
        s.presenter_connected();
        s.clicks(4);
        assert!(!s.c.presenter_active());
        assert!(s.c.settings().lockout);
        // and the laser is refused in lockout
        s.click();
        s.press(1_000);
        assert!(!s.out.laser_on);
    }

    #[test]
    fn presenter_idle_timeout() {
        let mut s = Sim::new();
        s.both(2_100);
        s.run(29 * 60_000);
        assert!(s.c.presenter_active());
        s.slide_click(B::Next); // a press restarts the 30 min
        s.run(29 * 60_000);
        assert!(s.c.presenter_active());
        s.run(61_000);
        assert!(!s.c.presenter_active(), "30 min without a press");
        assert_eq!(s.status().source, ControlSource::Auto);
        s.run(2_000);
        assert!(s.out.sleep, "then deep sleep");
        // 5 min setting
        let mut s = Sim::new();
        s.c.presenter_write(&[0, 5, 0, 0], 0).unwrap();
        s.both(2_100);
        s.run(5 * 60_000 + 100);
        assert!(!s.c.presenter_active());
    }

    #[test]
    fn presenter_battery_rules() {
        let mut s = Sim::build(Settings::default(), BootInfo::default(), 3_150);
        s.run(2_000);
        s.class = Some(B::Both);
        s.run(2_100);
        assert!(!s.c.presenter_active(), "refused below 3.20 V");
        assert_eq!(s.out.rgb, Rgb::RED, "one red blink");
        s.class = Some(B::None);
        s.run(1_000);
        s.class = None;
        let mut s = Sim::new();
        s.both(2_100);
        assert!(s.c.presenter_active());
        s.vbat = 3_100;
        s.run(1_500);
        assert!(s.c.presenter_active(), "filtered voltage still above");
        s.run(6_000);
        assert!(!s.c.presenter_active(), "battery empty ends presenter mode");
    }

    #[test]
    fn forget_hosts_with_10s_hold() {
        let mut s = Sim::new();
        s.c.set_bonded_hosts(3);
        // from flashlight mode: presenter at 2 s, forget at 10 s (stays in presenter mode)
        s.class = Some(B::Both);
        s.run(10_200);
        assert!(s.c.take_forget_hosts());
        assert!(!s.c.take_forget_hosts(), "reported once");
        assert_eq!(s.c.bonded_hosts(), 0);
        assert_eq!(s.out.rgb, Rgb::WHITE, "white x3");
        s.class = Some(B::None);
        s.run(100);
        s.class = None;
        assert!(s.c.presenter_active());
        assert_eq!(s.status().bonded_hosts, 0);
        // from presenter mode: leaves at 2 s, forgets at 10 s
        s.class = Some(B::Both);
        s.run(10_200);
        s.class = Some(B::None);
        s.run(100);
        s.class = None;
        assert!(!s.c.presenter_active());
        assert!(s.c.take_forget_hosts());
    }

    #[test]
    fn presenter_commands() {
        let mut s = Sim::new();
        s.run(100);
        assert_eq!(s.cmd(&[opcode::PRESENTER, 2]), Err(CmdError::Invalid));
        assert_eq!(s.cmd(&[opcode::ON]), Ok(()));
        s.run(100);
        assert_eq!(s.cmd(&[opcode::PRESENTER, 1]), Ok(()));
        assert!(s.c.presenter_active());
        assert!(!s.c.is_on(), "entering switches the main LED off");
        assert_eq!(s.out.adv, AdvMode::HidFast);
        assert_eq!(s.status().source, ControlSource::App);
        // light commands are invalid in presenter mode
        assert_eq!(s.cmd(&[opcode::ON]), Err(CmdError::Invalid));
        assert_eq!(s.cmd(&[opcode::LEVEL, 2]), Err(CmdError::Invalid));
        assert_eq!(s.cmd(&[opcode::OUTPUT_MA, 50, 0]), Err(CmdError::Invalid));
        assert_eq!(s.cmd(&[opcode::PRESENTER, 1]), Ok(()), "already in: no change");
        assert_eq!(s.cmd(&[opcode::PRESENTER, 0]), Ok(()));
        assert!(!s.c.presenter_active());
        assert_eq!(s.cmd(&[opcode::PRESENTER, 0]), Ok(()), "already out: no change");
        // button priority and lockout
        s.clicks(1);
        assert_eq!(s.cmd(&[opcode::PRESENTER, 1]), Err(CmdError::ButtonPriority));
        s.clicks(1);
        s.clicks(4);
        s.run(3_100);
        assert_eq!(s.cmd(&[opcode::PRESENTER, 1]), Err(CmdError::Lockout));
        // FORGET_HOSTS
        s.c.set_bonded_hosts(2);
        assert_eq!(s.cmd(&[opcode::FORGET_HOSTS, 0x00]), Err(CmdError::Invalid));
        assert!(!s.c.take_forget_hosts());
        assert_eq!(s.cmd(&[opcode::FORGET_HOSTS, 0xa5]), Ok(()));
        assert!(s.c.take_forget_hosts());
        assert_eq!(s.status().bonded_hosts, 0);
        // low battery refuses entering
        let mut s = Sim::build(Settings::default(), BootInfo::default(), 3_100);
        s.run(2_000);
        assert_eq!(s.cmd(&[opcode::PRESENTER, 1]), Err(CmdError::Protection));
    }

    #[test]
    fn factory_reset_keeps_paired_computers() {
        let mut s = Sim::new();
        s.c.set_bonded_hosts(2);
        s.both(2_100);
        assert!(s.c.presenter_active());
        assert_eq!(s.c.presenter_write(&[1, 60, 1, 0], s.t), Ok(()));
        s.run(3_100);
        assert_eq!(s.cmd(&[opcode::FACTORY_RESET, 0xa5]), Ok(()));
        assert!(!s.c.presenter_active(), "presenter mode left");
        assert!(!s.c.take_forget_hosts(), "bonds are kept");
        assert_eq!(s.c.bonded_hosts(), 2);
        assert_eq!(s.c.settings().presenter, PresenterSettings::default(), "presenter settings reset");
    }

    #[test]
    fn status_v2_fields() {
        let mut s = Sim::new();
        s.c.set_bonded_hosts(2);
        let b = s.status().encode();
        assert_eq!(b.len(), 20);
        assert_eq!(b[0], 2);
        assert_eq!((b[18], b[19]), (0, 2));
        s.presenter_connected();
        let b = s.status().encode();
        assert_eq!((b[18], b[19]), (2, 2));
    }

    #[test]
    fn stuck_slide_button_sleeps_without_button_wake() {
        let mut s = Sim::new();
        s.run(2_000);
        s.class = Some(B::Prev);
        s.run(5_000);
        assert!(!s.out.sleep, "may still be a gesture");
        s.run(5_100);
        assert!(s.out.sleep && !s.out.wake_on_button, "stuck after 10 s");
        s.class = Some(B::None);
        s.run(100);
        assert!(s.out.sleep && s.out.wake_on_button);
        s.class = None;
    }

    #[test]
    fn wake_with_both_held_enters_presenter() {
        let boot = BootInfo {
            woke_by_button: true,
            button_pressed: false,
            woke_by_timer: false,
        };
        let mut s = Sim::with(Settings::default(), boot);
        s.c = Controller::new_with_class(Settings::default(), boot, B::Both, 0);
        s.class = Some(B::Both);
        s.run(2_050);
        assert!(s.c.presenter_active());
        assert!(!s.c.is_on(), "a slide press at wake-up is not a main click");
        // woken by › (still held at the first sample): ignored, the light stays off
        let mut s = Sim::with(Settings::default(), boot);
        s.c = Controller::new_with_class(Settings::default(), boot, B::Next, 0);
        s.class = Some(B::Next);
        s.run(100);
        s.class = Some(B::None);
        s.run(1_000);
        assert!(!s.c.is_on());
    }

    #[test]
    fn laser_ring_red_in_flashlight_mode() {
        let mut s = Sim::new();
        s.click();
        s.pressed = true;
        s.run(1_000);
        assert!(s.out.laser_on);
        assert_eq!(s.out.rgb, Rgb::RED);
        s.pressed = false;
        s.run(100);
        assert_ne!(s.out.rgb, Rgb::RED);
    }

    // -------------------------------------------------------------- LED ceiling (both boards)

    /// Random commands, Custom profiles with extreme values, button gestures, temperatures and
    /// battery voltages: the LED current never exceeds the highest level of the board (v0.7:
    /// 2850 mA) nor its hard ceiling (v0.7: 3000 mA), in the outputs, in Status, or as a PWM duty.
    #[test]
    fn never_above_the_led_ceiling() {
        let ceiling = crate::hw::LED_MAX_MA;
        let max_counts = crate::hw::led_duty_counts(u16::MAX);
        let mut seed = 0x2545_f491_u32;
        let mut rnd = move |n: u32| {
            seed ^= seed << 13;
            seed ^= seed >> 17;
            seed ^= seed << 5;
            seed % n
        };
        let mut peak = 0u16;
        for round in 0..40 {
            let mut s = Sim::new();
            s.run(500);
            for _ in 0..60 {
                match rnd(9) {
                    0 => {
                        let lv = rnd(5) as u8;
                        let _ = s.c.command(&[opcode::LEVEL, lv], s.t);
                    }
                    1 => {
                        let ma = [1u16, 600, 2_999, 3_000, 3_001, 3_552, 4_000, u16::MAX][rnd(8) as usize];
                        let _ = s.c.command(&output_ma(ma), s.t);
                    }
                    2 => {
                        let _ = s.c.command(&[opcode::PROFILE, rnd(4) as u8], s.t);
                    }
                    3 => {
                        // a Custom profile with random, often out-of-range values (the firmware clamps)
                        let mut b = [0u8; crate::protocol::PROFILE_LEN];
                        for x in b.iter_mut() {
                            *x = rnd(256) as u8;
                        }
                        b[0] = 3;
                        if rnd(2) == 0 {
                            b[10..12].copy_from_slice(&u16::MAX.to_le_bytes()); // turbo
                            b[8..10].copy_from_slice(&u16::MAX.to_le_bytes()); // high
                            b[18..20].copy_from_slice(&u16::MAX.to_le_bytes()); // cell limit
                        }
                        let _ = s.c.profile_write(&b, s.t);
                    }
                    4 => s.clicks(1 + rnd(2) as usize),
                    5 => s.press(500 + rnd(2_000) as u64),
                    6 => s.temp_c = [20.0, 40.0, 48.0, 55.0, 69.0, 75.0][rnd(6) as usize],
                    7 => s.vbat = [3_050, 3_400, 3_700, 4_200][rnd(4) as usize],
                    _ => s.run(rnd(70_000) as u64),
                }
                s.run(200);
                assert!(s.out.led_ma as u32 <= ceiling, "round {round}: {} mA", s.out.led_ma);
                assert!(s.out.led_ma <= crate::board::TURBO_MAX_MA, "round {round}: {} mA", s.out.led_ma);
                assert!(s.status().led_ma as u32 <= ceiling);
                assert!(crate::hw::led_duty_counts(s.out.led_ma) <= max_counts);
                peak = peak.max(s.out.led_ma);
            }
        }
        // the random walk does reach the top: turbo, an exact request or a clamped Custom turbo
        assert!(peak >= 2_200, "peak {peak}");
        #[cfg(feature = "board-v07")]
        assert_eq!(peak, crate::board::TURBO_MAX_MA, "the 2850 mA turbo is reached, never more");
        #[cfg(feature = "board-v07")]
        assert!((peak as u32) < ceiling);
    }
}
