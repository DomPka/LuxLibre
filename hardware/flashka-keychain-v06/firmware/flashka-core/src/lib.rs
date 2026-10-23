// SPDX-License-Identifier: MIT OR Apache-2.0
//! FlashKa Keychain v0.6 / v0.7 firmware - hardware independent logic.
//!
//! Everything that can be decided without touching a register lives here:
//! the profile tables and their clamping, the Bluetooth packet formats, the
//! three-button ladder and the gesture parsers, presenter mode (HID keys,
//! settings), battery / runtime estimation, the protection rules, the charger
//! control, the RGB ring patterns, the settings and bond records that are
//! stored in flash and, tying it all together, [`controller::Controller`],
//! the state machine of the light.
//!
//! The firmware crate (`flashka-fw`) only samples inputs, feeds them to the
//! controller and applies the [`controller::Outputs`] to the hardware.
//!
//! The main board (v0.6 or v0.7) is chosen at build time with the Cargo feature
//! `board-v07`; [`board`] holds every constant that differs between them, and the v0.7
//! build regulates the temperature with `thermal` instead of the linear derating.
//!
//! All times are milliseconds from boot (`u64`), currents are mA, voltages
//! mV and temperatures 0.1 degC (`i16`, "dC").
#![cfg_attr(not(test), no_std)]
#![forbid(unsafe_code)]

pub mod battery;
pub mod board;
pub mod bonds;
pub mod buttons;
pub mod charger;
pub mod config;
pub mod controller;
pub mod gesture;
pub mod hid;
pub mod hw;
pub mod mathx;
pub mod presenter;
pub mod profile;
pub mod protection;
pub mod protocol;
pub mod rgb;
pub mod settings;
#[cfg(feature = "board-v07")]
pub mod thermal;

pub use buttons::ButtonClass;
pub use controller::{BootInfo, Controller, Outputs, Sensors};
pub use profile::{Level, Profile, ProfileId};
