// SPDX-License-Identifier: MIT OR Apache-2.0
//! ESP32-C3 pin map of the FlashKa Keychain v0.6 main board (the v0.7 board
//! uses the same GPIOs: its changes are in the LED power stage and the cell,
//! see `flashka_core::board`).
//!
//! Mirrors `GPIO_MAP` in `tools/kicad/flashka_parts.py` (the single source of
//! truth for the hardware); unchanged from v0.5 except for the button net,
//! which now carries the three-button ladder, and the RGB nets, which drive
//! the two ring LEDs (LED3, LED4) in parallel. Module pad numbers of the
//! ESP32-C3-MINI-1 in brackets.
//!
//! | GPIO | Pad | Net | Use in firmware |
//! |---|---|---|---|
//! | 0 | 12 | VBAT_ADC | ADC1_CH0, 11 dB, curve calibration; VBAT = 2 x V |
//! | 1 | 13 | NTC_ADC | ADC1_CH1, 11 dB; 100 k to 3V3, NTC 100 k B4250 to GND |
//! | 2 | 5 | RGB_B | LEDC ch3, active low, ring blue (strap, 10 k pull-up) |
//! | 3 | 6 | BTN | ADC1_CH3, 2.5 dB (0-1050 mV), curve calibration: button ladder; deep sleep: digital input, wake on low |
//! | 4 | 18 | CHG_STAT | input + pull-up, low = charging; wake source |
//! | 5 | 19 | CHG_DONE | input + pull-up, low = charge complete; wake source |
//! | 6 | 20 | LED_PWM | LEDC ch0, 13 bit, 9.77 kHz -> current set point |
//! | 7 | 21 | LED_EN | output, high = LED driver + op-amp on (100 k pull-down) |
//! | 8 | 22 | RGB_G | LEDC ch2, active low, ring green (strap, 10 k pull-up) |
//! | 9 | 23 | BTN | boot strap, same net: digital input, internal pull-up off after boot (R9 is external); low = any button; never driven |
//! | 10 | 16 | LASER_ON | output, high = laser on if S2 armed (100 k pull-down) |
//! | 18/19 | 26/27 | USB D-/D+ | USB-Serial-JTAG (console, flashing) - untouched |
//! | 20 | 30 | CHG_SET | low = ~300 mA, floating = 10 mA trickle, high = charger off |
//! | 21 | 31 | RGB_R | LEDC ch1, active low, ring red (U0TXD: ROM boot log flickers it) |
//!
//! Button ladder on BTN (R9 10 k to 3V3): ● main SW1 to GND (0 V), › next SW2
//! via R30 1 k (0.300 V), ‹ previous SW3 via R31 2.2 k (0.595 V), ‹ + ›
//! together 0.212 V. Every press is below GPIO9's VIL (0.825 V).

pub const GPIO_VBAT_ADC: u8 = 0;
pub const GPIO_NTC_ADC: u8 = 1;
pub const GPIO_RGB_B: u8 = 2;
pub const GPIO_BTN: u8 = 3;
pub const GPIO_CHG_STAT: u8 = 4;
pub const GPIO_CHG_DONE: u8 = 5;
pub const GPIO_LED_PWM: u8 = 6;
pub const GPIO_LED_EN: u8 = 7;
pub const GPIO_RGB_G: u8 = 8;
pub const GPIO_BTN_STRAP: u8 = 9;
pub const GPIO_LASER_ON: u8 = 10;
pub const GPIO_CHG_SET: u8 = 20;
pub const GPIO_RGB_R: u8 = 21;

/// GPIO output-register mask of the two outputs that must be low on every
/// fault path (used by the panic handler, which writes the register directly).
pub const SAFETY_OFF_MASK: u32 = (1 << GPIO_LED_EN) | (1 << GPIO_LASER_ON);

/// LEDC frequency of the LED current set point and the RGB channels: the
/// highest frequency with 13-bit resolution from the 80 MHz APB clock
/// (80 MHz / 8192 = 9765.6 Hz).
pub const PWM_FREQ_HZ: u32 = 9_765;

/// LEDC duty value for 100 % at 13 bits.
pub const PWM_FULL: u32 = 1 << 13;

// Firmware version as a string literal (the boot log inlines it into its text, as the v0.6 image
// did with `env!("CARGO_PKG_VERSION")`). Must equal flashka_core::board::FW_VERSION (checked below).
#[cfg(not(feature = "board-v07"))]
macro_rules! fw_version {
    () => {
        "0.6.0"
    };
}
#[cfg(feature = "board-v07")]
macro_rules! fw_version {
    () => {
        "0.7.0"
    };
}
pub(crate) use fw_version;

const _: () = {
    let (a, b) = (fw_version!().as_bytes(), flashka_core::board::FW_VERSION.as_bytes());
    assert!(a.len() == b.len(), "fw_version!() differs from flashka_core::board::FW_VERSION");
    let mut i = 0;
    while i < a.len() {
        assert!(a[i] == b[i], "fw_version!() differs from flashka_core::board::FW_VERSION");
        i += 1;
    }
};

// App descriptor of the v0.7 image: the same as the v0.6 one (`esp_app_desc!()` in main.rs) with
// the v0.7 firmware version instead of the crate version (0.6.0, kept for the v0.6 image).
#[cfg(feature = "board-v07")]
esp_bootloader_esp_idf::esp_app_desc!(
    flashka_core::board::FW_VERSION,
    env!("CARGO_PKG_NAME"),
    esp_bootloader_esp_idf::BUILD_TIME,
    esp_bootloader_esp_idf::BUILD_DATE,
    esp_bootloader_esp_idf::ESP_IDF_COMPATIBLE_VERSION,
    esp_bootloader_esp_idf::MMU_PAGE_SIZE,
    0,
    u16::MAX,
    esp_bootloader_esp_idf::SECURE_VERSION
);
