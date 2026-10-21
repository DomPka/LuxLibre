// SPDX-License-Identifier: MIT OR Apache-2.0
//! Reset / wake-up handling, deep sleep and the panic handler.

use esp_hal::gpio::{RtcPin, RtcPinWithResistors};
use esp_hal::peripherals::{GPIO, GPIO3, GPIO4, GPIO5, LPWR};
use esp_hal::rtc_cntl::sleep::{RtcSleepConfig, RtcioWakeupSource, TimerWakeupSource, WakeSource, WakeupLevel};
use esp_hal::rtc_cntl::{Rtc, SocResetReason};
use esp_hal::system::SleepSource;

use crate::board::SAFETY_OFF_MASK;

/// Why the firmware is running.
#[derive(Clone, Copy, Debug)]
pub struct WakeInfo {
    pub reset_reason: Option<SocResetReason>,
    /// Woken from deep sleep by a GPIO (button or charger pins).
    pub gpio_wake: bool,
    /// Woken from deep sleep by the stuck-button re-check timer.
    pub timer_wake: bool,
    /// RTC GPIO wake-up status bits (which pad triggered the wake).
    pub wake_status: u8,
}

impl WakeInfo {
    /// The button (GPIO3) woke the chip. The C3 reports the pad in the 6-bit
    /// status field; depending on the documentation the bit order is either
    /// GPIO0..5 or reversed, so both positions of GPIO3 (bit 3 / bit 2) are
    /// accepted - neither collides with the other wake pins (GPIO4/5 = bits
    /// 4,5 or 1,0). If the status is empty, a still-pressed button decides.
    pub fn woke_by_button(&self, button_low: bool) -> bool {
        self.gpio_wake && (self.wake_status & 0b00_1100 != 0 || button_low)
    }
}

/// Read the reset reason and wake cause, then release what the previous
/// deep-sleep entry left behind on the wake pins (pad hold, wake enable).
/// Must run before GPIO3/4/5 are configured.
pub fn take_wake_info(gpio3: &GPIO3<'_>, gpio4: &GPIO4<'_>, gpio5: &GPIO5<'_>) -> WakeInfo {
    let reset_reason = esp_hal::system::reset_reason();
    let cause = esp_hal::system::wakeup_cause();
    let gpio_wake = matches!(cause, SleepSource::Gpio);
    let timer_wake = matches!(cause, SleepSource::Timer);
    let wake_status = LPWR::regs().gpio_wakeup().read().gpio_wakeup_status().bits();

    // like esp_deep_sleep_wakeup_io_reset() in ESP-IDF
    gpio3.rtcio_pad_hold(false);
    gpio4.rtcio_pad_hold(false);
    gpio5.rtcio_pad_hold(false);
    // SAFETY: 0 = interrupt type "disabled"; wake-up disabled for these pins.
    unsafe {
        gpio3.apply_wakeup(false, 0);
        gpio4.apply_wakeup(false, 0);
        gpio5.apply_wakeup(false, 0);
    }
    LPWR::regs()
        .gpio_wakeup()
        .modify(|_, w| w.gpio_wakeup_status_clr().set_bit());
    LPWR::regs()
        .gpio_wakeup()
        .modify(|_, w| w.gpio_wakeup_status_clr().clear_bit());

    WakeInfo {
        reset_reason,
        gpio_wake,
        timer_wake,
        wake_status,
    }
}

/// Enter deep sleep with wake-up on GPIO3 low (button) and GPIO4/GPIO5 low
/// (USB plugged in: TP4057 CHRG/STDBY). The caller has already switched the
/// LED driver, the laser and the RGB LED off and saved the settings.
///
/// `wake_on_button = false` (button stuck low in lockout): GPIO3 is left out
/// of the wake sources - it would wake the chip at once - and a timer wakes
/// it every `STUCK_RECHECK_MS` to look at the button again.
///
/// esp-hal's `Rtc::sleep_deep` panics (`unreachable!`) right after requesting
/// the sleep, while the RTC needs a few slow-clock cycles to power down; with a
/// reset-on-panic handler that would race. So the request is issued with
/// `Rtc::sleep` and the CPU waits here. If the chip is still running after
/// 100 ms the request was rejected (a wake level was already active) and the
/// firmware reboots instead.
pub fn deep_sleep(rtc: &mut Rtc<'_>, wake_on_button: bool) -> ! {
    // SAFETY: this function never returns. The input drivers that own these
    // pins are no longer used (the control loop is the caller), and the BLE
    // task never touches them.
    let mut btn = unsafe { GPIO3::steal() };
    let mut chrg = unsafe { GPIO4::steal() };
    let mut stdby = unsafe { GPIO5::steal() };
    let mut all: [(&mut dyn RtcPinWithResistors, WakeupLevel); 3] = [
        (&mut chrg, WakeupLevel::Low),
        (&mut stdby, WakeupLevel::Low),
        (&mut btn, WakeupLevel::Low),
    ];
    let pins = if wake_on_button { &mut all[..] } else { &mut all[..2] };
    let wake = RtcioWakeupSource::new(pins);
    let timer = TimerWakeupSource::new(core::time::Duration::from_millis(
        aurora_core::config::STUCK_RECHECK_MS,
    ));
    let sources: &[&dyn WakeSource] = if wake_on_button { &[&wake] } else { &[&wake, &timer] };

    // Do not print the ROM boot banner on the next wake-up: it is sent on
    // U0TXD = GPIO21 = red RGB cathode (and costs boot time).
    rtc.disable_rom_message_printing();

    let config = RtcSleepConfig::deep();
    critical_section::with(|_| {
        rtc.sleep(&config, sources);
        let delay = esp_hal::delay::Delay::new();
        delay.delay_millis(100);
    });
    log::warn!("[power] deep sleep request rejected, rebooting");
    esp_hal::system::software_reset()
}

/// Force LED_EN (GPIO7) and LASER_ON (GPIO10) low by writing the GPIO output
/// clear register directly - usable from any context, including a panic.
pub fn force_outputs_off() {
    // SAFETY: W1TC only clears the given output bits; both pins are GPIO
    // outputs owned by this firmware.
    GPIO::regs()
        .out_w1tc()
        .write(|w| unsafe { w.bits(SAFETY_OFF_MASK) });
}

#[panic_handler]
fn panic(info: &core::panic::PanicInfo) -> ! {
    // 1. the dangerous outputs first
    force_outputs_off();
    // 2. tell whoever listens on USB
    log::error!("PANIC: {}", info);
    // 3. reboot: after the reset every pin is an input again and the external
    //    100 k pull-downs keep LED_EN and LASER_ON low.
    esp_hal::system::software_reset()
}
