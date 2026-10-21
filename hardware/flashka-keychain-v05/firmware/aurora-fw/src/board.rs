// SPDX-License-Identifier: MIT OR Apache-2.0
//! ESP32-C3 pin map of the Aurora++ v0.5 main board.
//!
//! Mirrors `GPIO_MAP` in `tools/kicad/aurora_parts.py` (the single source of
//! truth for the hardware). Module pad numbers of the ESP32-C3-MINI-1 in brackets.
//!
//! | GPIO | Pad | Net | Use in firmware |
//! |---|---|---|---|
//! | 0 | 12 | VBAT_ADC | ADC1_CH0, 11 dB, curve calibration; VBAT = 2 x V |
//! | 1 | 13 | NTC_ADC | ADC1_CH1, 11 dB; 100 k to 3V3, NTC 100 k B4250 to GND |
//! | 2 | 5 | RGB_B | LEDC ch3, active low (strap, 10 k pull-up) |
//! | 3 | 6 | BTN | input, low = pressed; deep-sleep wake source |
//! | 4 | 18 | CHG_STAT | input + pull-up, low = charging; wake source |
//! | 5 | 19 | CHG_DONE | input + pull-up, low = charge complete; wake source |
//! | 6 | 20 | LED_PWM | LEDC ch0, 13 bit, 9.77 kHz -> current set point |
//! | 7 | 21 | LED_EN | output, high = LED driver + op-amp on (100 k pull-down) |
//! | 8 | 22 | RGB_G | LEDC ch2, active low (strap, 10 k pull-up) |
//! | 9 | 23 | BTN | boot strap, same button; never driven by the firmware |
//! | 10 | 16 | LASER_ON | output, high = laser on if S2 armed (100 k pull-down) |
//! | 18/19 | 26/27 | USB D-/D+ | USB-Serial-JTAG (console, flashing) - untouched |
//! | 20 | 30 | CHG_SET | low = ~300 mA, floating = 10 mA trickle, high = charger off |
//! | 21 | 31 | RGB_R | LEDC ch1, active low (U0TXD: ROM boot log flickers it) |

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
