// SPDX-License-Identifier: MIT OR Apache-2.0
//! Aurora++ v0.5 flashlight - hardware independent logic.
//!
//! Everything that can be decided without touching a register lives here:
//! the profile tables and their clamping, the Bluetooth packet formats, the
//! button gesture parser, battery / runtime estimation, the protection rules,
//! the charger control, the RGB status patterns, the settings record that is
//! stored in flash and, tying it all together, [`controller::Controller`], the
//! state machine of the light.
//!
//! The firmware crate (`aurora-fw`) only samples inputs, feeds them to the
//! controller and applies the [`controller::Outputs`] to the hardware.
//!
//! All times are milliseconds from boot (`u64`), currents are mA, voltages
//! mV and temperatures 0.1 degC (`i16`, "dC").
#![cfg_attr(not(test), no_std)]
#![forbid(unsafe_code)]

pub mod battery;
pub mod charger;
pub mod config;
pub mod controller;
pub mod gesture;
pub mod hw;
pub mod mathx;
pub mod profile;
pub mod protection;
pub mod protocol;
pub mod rgb;
pub mod settings;

pub use controller::{BootInfo, Controller, Outputs, Sensors};
pub use profile::{Level, Profile, ProfileId};
