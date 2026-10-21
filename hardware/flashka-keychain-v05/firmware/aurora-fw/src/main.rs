// SPDX-License-Identifier: MIT OR Apache-2.0
//! Aurora++ v0.5 keychain flashlight firmware (ESP32-C3-MINI-1-N4).
//!
//! Hardware I/O and async glue only - every decision is made by
//! `aurora_core::Controller` (host-tested). See `docs/firmware.md`.
//!
//! Tasks (one embassy executor on esp-rtos):
//! * `main` - the control loop: every 10 ms sample the button, every 100 ms
//!   the ADC and charger pins, run the controller, apply its outputs, store
//!   settings, feed the watchdog, enter deep sleep when idle;
//! * `ble::host_task` - the trouble-host runner;
//! * `ble::peripheral_task` - advertising windows and GATT connections.
//!
//! The Bluetooth controller is brought up lazily, the first time the
//! controller asks for a radio window while no button gesture is in progress:
//! its start-up (PHY calibration) blocks the executor, and doing it at boot
//! would make the button deaf right after a wake-up - exactly when the second
//! click of a "double click from sleep" arrives. Wake-ups that never open a
//! window (lockout, laser, stray presses) never power the radio at all.

#![no_std]
#![no_main]
#![deny(unsafe_op_in_unsafe_fn)]

mod ble;
mod board;
mod io;
mod power;
mod storage;

use core::cell::RefCell;

use aurora_core::settings::SettingsStore;
use aurora_core::{BootInfo, Controller};
use embassy_executor::Spawner;
use embassy_sync::blocking_mutex::Mutex;
use embassy_sync::blocking_mutex::raw::CriticalSectionRawMutex;
use embassy_time::{Duration, Instant, Ticker, Timer};
use esp_hal::analog::adc::{Adc, AdcCalCurve, AdcConfig, Attenuation};
use esp_hal::clock::CpuClock;
use esp_hal::gpio::{AnyPin, DriveMode, Flex, Input, InputConfig, Level, Output, OutputConfig, Pin, Pull};
use esp_hal::interrupt::software::SoftwareInterruptControl;
use esp_hal::ledc::channel::{self, ChannelIFace};
use esp_hal::ledc::timer::{self, TimerIFace};
use esp_hal::ledc::{LSGlobalClkSource, Ledc, LowSpeed};
use esp_hal::peripherals::ADC1;
use esp_hal::rtc_cntl::Rtc;
use esp_hal::time::Rate;
use esp_hal::timer::timg::{MwdtStage, TimerGroup};
use log::{error, info, warn};
use static_cell::StaticCell;

esp_bootloader_esp_idf::esp_app_desc!();

/// Control loop period.
const CONTROL_PERIOD_MS: u64 = 10;
/// ADC / charger pin sampling period.
const SENSOR_PERIOD_MS: u64 = 100;
/// Watchdog timeout (longer than a worst-case flash sector erase).
const WATCHDOG_S: u64 = 3;
/// Advertising must have been off this long before deep sleep (lets the BLE
/// task stop the radio cleanly).
const SLEEP_ADV_QUIET_MS: u64 = 500;

/// The light's state machine, shared by the control loop and the BLE task.
static CONTROLLER: Mutex<CriticalSectionRawMutex, RefCell<Option<Controller>>> =
    Mutex::new(RefCell::new(None));

/// Run `f` with exclusive access to the controller.
pub fn with_controller<R>(f: impl FnOnce(&mut Controller) -> R) -> Option<R> {
    CONTROLLER.lock(|c| c.borrow_mut().as_mut().map(f))
}

/// Milliseconds since boot.
pub fn now_ms() -> u64 {
    Instant::now().as_millis()
}

static LEDC: StaticCell<Ledc<'static>> = StaticCell::new();
static PWM_TIMER: StaticCell<timer::Timer<'static, LowSpeed>> = StaticCell::new();

#[esp_rtos::main]
async fn main(spawner: Spawner) -> ! {
    let p = esp_hal::init(esp_hal::Config::default().with_cpu_clock(CpuClock::_80MHz));

    // 1. Safety: the two dangerous outputs are driven low before anything else
    //    (the 100 k pull-downs have kept them low through reset and boot).
    let led_en = Output::new(p.GPIO7, Level::Low, OutputConfig::default());
    let laser = Output::new(p.GPIO10, Level::Low, OutputConfig::default());

    esp_println::logger::init_logger_from_env();
    // Heap for esp-radio (BLE controller, its task stack): 100 KiB as the
    // esp-radio documentation recommends - 64 KiB in the RAM the 2nd-stage
    // bootloader used (free once the app runs) plus 36 KiB of normal RAM.
    esp_alloc::heap_allocator!(#[esp_hal::ram(reclaimed)] size: 64 * 1024);
    esp_alloc::heap_allocator!(size: 36 * 1024);

    // The peripherals below are picked by name; make sure they agree with the
    // board map (board.rs mirrors tools/kicad/aurora_parts.py).
    macro_rules! check_pins {
        ($($pin:expr => $gpio:expr),* $(,)?) => {
            $( if $pin.number() != $gpio {
                error!("board map mismatch: {} is GPIO{}", stringify!($gpio), $pin.number());
            } )*
        };
    }
    check_pins!(
        p.GPIO0 => board::GPIO_VBAT_ADC,
        p.GPIO1 => board::GPIO_NTC_ADC,
        p.GPIO2 => board::GPIO_RGB_B,
        p.GPIO3 => board::GPIO_BTN,
        p.GPIO4 => board::GPIO_CHG_STAT,
        p.GPIO5 => board::GPIO_CHG_DONE,
        p.GPIO6 => board::GPIO_LED_PWM,
        p.GPIO8 => board::GPIO_RGB_G,
        p.GPIO9 => board::GPIO_BTN_STRAP, // never configured: boot strap
        p.GPIO20 => board::GPIO_CHG_SET,
        p.GPIO21 => board::GPIO_RGB_R,
    );

    // 2. Why are we running? Release the deep-sleep wake pin state.
    let wake = power::take_wake_info(&p.GPIO3, &p.GPIO4, &p.GPIO5);
    let button = Input::new(p.GPIO3, InputConfig::default().with_pull(Pull::Up));
    let chg_stat = Input::new(p.GPIO4, InputConfig::default().with_pull(Pull::Up));
    let chg_done = Input::new(p.GPIO5, InputConfig::default().with_pull(Pull::Up));
    let woke_by_button = wake.woke_by_button(button.is_low());
    info!(
        "Aurora++ fw {} - reset {:?}, gpio wake {} (status {:#08b}), timer wake {}, button wake {}",
        env!("CARGO_PKG_VERSION"),
        wake.reset_reason,
        wake.gpio_wake,
        wake.wake_status,
        wake.timer_wake,
        woke_by_button
    );

    // 3. Settings from flash.
    let mut flash = storage::SettingsFlash::new(esp_storage::FlashStorage::new(p.FLASH));
    let (mut store, loaded) = match SettingsStore::load(&mut flash) {
        Ok(v) => v,
        Err(e) => {
            error!("[flash] settings read failed: {:?}", e);
            (SettingsStore::blank(), None)
        }
    };
    let settings = loaded.unwrap_or_default();
    info!(
        "[settings] {} profile {:?} level {:?} lockout {} empty {}",
        if loaded.is_some() { "loaded" } else { "defaults," },
        settings.profile,
        settings.level,
        settings.lockout,
        settings.empty_latch
    );

    // 4. PWM: LED current set point (ch0) and RGB (ch1..3), 13 bit @ 9.77 kHz.
    let ledc: &'static mut Ledc<'static> = LEDC.init(Ledc::new(p.LEDC));
    ledc.set_global_slow_clock(LSGlobalClkSource::APBClk);
    let pwm_timer = PWM_TIMER.init(ledc.timer::<LowSpeed>(timer::Number::Timer0));
    if let Err(e) = pwm_timer.configure(timer::config::Config {
        duty: timer::config::Duty::Duty13Bit,
        clock_source: timer::LSClockSource::APBClk,
        frequency: Rate::from_hz(board::PWM_FREQ_HZ),
    }) {
        error!("[pwm] timer: {:?}", e);
    }
    let pwm_timer: &'static timer::Timer<'static, LowSpeed> = pwm_timer;
    let ch = |n: channel::Number, pin: AnyPin<'static>, duty_pct: u8| {
        let mut c = ledc.channel::<LowSpeed>(n, pin);
        if let Err(e) = c.configure(channel::config::Config {
            timer: pwm_timer,
            duty_pct,
            drive_mode: DriveMode::PushPull,
        }) {
            error!("[pwm] channel {:?}: {:?}", n, e);
        }
        c
    };
    // LED current 0 %, RGB channels 100 % (= cathode high = dark)
    let led_pwm = ch(channel::Number::Channel0, p.GPIO6.degrade(), 0);
    let rgb_r = ch(channel::Number::Channel1, p.GPIO21.degrade(), 100);
    let rgb_g = ch(channel::Number::Channel2, p.GPIO8.degrade(), 100);
    let rgb_b = ch(channel::Number::Channel3, p.GPIO2.degrade(), 100);

    // CHG_SET starts floating (10 mA trickle, the no-firmware state).
    let mut chg_set = Flex::new(p.GPIO20);
    chg_set.apply_input_config(&InputConfig::default().with_pull(Pull::None));
    chg_set.apply_output_config(&OutputConfig::default());
    chg_set.set_output_enable(false);

    let mut act = io::Actuators::new(led_en, laser, chg_set, led_pwm, [rgb_r, rgb_g, rgb_b]);

    // 5. ADC1: VBAT (GPIO0) and NTC (GPIO1), 11 dB, curve-fitting calibration.
    let mut adc_cfg = AdcConfig::<ADC1<'static>>::new();
    let vbat = adc_cfg.enable_pin_with_cal::<_, AdcCalCurve<ADC1<'static>>>(p.GPIO0, Attenuation::_11dB);
    let ntc = adc_cfg.enable_pin_with_cal::<_, AdcCalCurve<ADC1<'static>>>(p.GPIO1, Attenuation::_11dB);
    let adc = Adc::new(p.ADC1, adc_cfg);
    let mut sensors = io::SensorInputs::new(adc, vbat, ntc, chg_stat, chg_done);

    // 6. Watchdog (TIMG1 MWDT, system reset).
    let timg1 = TimerGroup::new(p.TIMG1);
    let mut wdt = timg1.wdt;
    wdt.set_timeout(MwdtStage::Stage0, esp_hal::time::Duration::from_secs(WATCHDOG_S));
    wdt.enable();

    let mut rtc = Rtc::new(p.LPWR);

    // 7. RTOS scheduler (needed by esp-radio and the async executor).
    let timg0 = TimerGroup::new(p.TIMG0);
    let sw_int = SoftwareInterruptControl::new(p.SW_INTERRUPT);
    esp_rtos::start(timg0.timer0, sw_int.software_interrupt0);

    // 8. The controller starts now, with the button level sampled last thing
    //    before the loop (the boot time itself is not counted in gestures).
    let button_low = button.is_low();
    let boot = BootInfo {
        woke_by_button,
        button_pressed: button_low,
        woke_by_timer: wake.timer_wake,
    };
    CONTROLLER.lock(|c| *c.borrow_mut() = Some(Controller::new(settings, boot, now_ms())));

    // 9. Control loop. Bluetooth is started on demand (see the module docs);
    //    if it fails the flashlight keeps working without it.
    let mut bt = Some(p.BT);
    let mut ticker = Ticker::every(Duration::from_millis(CONTROL_PERIOD_MS));
    let mut next_sample = 0u64;
    let mut save_failures = 0u8;
    let mut next_save_try = 0u64;
    let mut adv_on_at = 0u64;
    loop {
        let now = now_ms();
        if now >= next_sample {
            next_sample = now + SENSOR_PERIOD_MS;
            if let Some(s) = sensors.sample() {
                with_controller(|c| c.sensors(s, now));
            }
        }
        let pressed = button.is_low();
        if let Some((out, gesture_busy)) = with_controller(|c| {
            c.button(pressed, now);
            (c.tick(now), c.button_busy())
        }) {
            act.apply(&out);
            ble::set_adv_mode(out.adv);
            if out.adv != aurora_core::controller::AdvMode::Off {
                adv_on_at = now;
                if !gesture_busy && let Some(bt) = bt.take() {
                    info!("[ble] starting");
                    wdt.feed();
                    if let Err(e) = ble::start(&spawner, bt) {
                        error!("[ble] not available: {}", e);
                    }
                    wdt.feed();
                }
            }

            // Persist settings (only written when changed). After repeated
            // flash errors give up, so that sleep and reboot still happen.
            let mut save_blocking = false;
            if let Some(s) = out.save
                && save_failures < 3
            {
                if now >= next_save_try {
                    match store.save(&mut flash, &s) {
                        Ok(written) => {
                            if written {
                                info!("[settings] saved");
                            }
                            with_controller(|c| c.saved(s));
                        }
                        Err(e) => {
                            save_failures += 1;
                            next_save_try = now + 2_000;
                            warn!("[settings] save failed ({}): {:?}", save_failures, e);
                            save_blocking = true;
                        }
                    }
                } else {
                    save_blocking = true;
                }
            }

            if out.reboot && !save_blocking {
                info!("[power] factory reset: rebooting");
                act.all_off();
                // let the BLE task send the write response first
                Timer::after(Duration::from_millis(500)).await;
                esp_hal::system::software_reset();
            }
            if out.sleep && !save_blocking && now.saturating_sub(adv_on_at) >= SLEEP_ADV_QUIET_MS {
                info!("[power] deep sleep (button wake {})", out.wake_on_button);
                act.all_off();
                power::deep_sleep(&mut rtc, out.wake_on_button);
            }
        }
        wdt.feed();
        ticker.next().await;
    }
}
