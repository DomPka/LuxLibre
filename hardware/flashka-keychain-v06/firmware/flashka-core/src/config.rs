// SPDX-License-Identifier: MIT OR Apache-2.0
//! Tunable constants.
//!
//! Every constant a user might want to adjust is collected here and listed in
//! `docs/firmware.md` ("Tunable constants"). Values marked *(protocol)* are
//! fixed by `docs/ble_protocol.md` and must not be changed without changing the
//! protocol document and the app as well.

// ---------------------------------------------------------------- button UI
/// A level change of the button must be stable this long to be accepted.
pub const DEBOUNCE_MS: u64 = 25;
/// A press shorter than this is a click, longer is a hold.
pub const CLICK_MAX_MS: u64 = 400;
/// Clicks closer together than this belong to the same gesture.
pub const CLICK_GAP_MS: u64 = 400;
/// While the button is held with the light on, the level steps this often.
pub const HOLD_REPEAT_MS: u64 = 600;
/// Every button action locks out app commands for this long *(protocol)*.
pub const APP_LOCK_MS: u64 = 3_000;

// ---------------------------------------------------------------- Bluetooth
/// Radio window after the main LED is switched off *(protocol)*.
pub const BLE_WINDOW_AFTER_OFF_MS: u64 = 120_000;
/// Radio window opened by a triple click while off *(protocol)*.
pub const BLE_WINDOW_TRIPLE_CLICK_MS: u64 = 120_000;
/// Radio window after a central disconnects *(protocol)*.
pub const BLE_WINDOW_AFTER_DISCONNECT_MS: u64 = 30_000;
/// Upper limit of a KEEPALIVE extension *(protocol)*.
pub const BLE_KEEPALIVE_MAX_S: u64 = 600;
/// Fast advertising lasts this long at the start of a window *(protocol)*.
pub const ADV_FAST_PERIOD_MS: u64 = 30_000;
/// Fast advertising interval *(protocol)*.
pub const ADV_FAST_INTERVAL_MS: u64 = 100;
/// Slow advertising interval *(protocol)*.
pub const ADV_SLOW_INTERVAL_MS: u64 = 500;
/// Status notifications are sent at least this often *(protocol)*.
pub const STATUS_NOTIFY_PERIOD_MS: u64 = 2_000;
/// Minimum spacing of change-triggered Status notifications.
pub const STATUS_NOTIFY_MIN_GAP_MS: u64 = 150;

// ---------------------------------------------------------------- laser
/// Longest continuous laser burst (the button must be released and the
/// gesture repeated afterwards) *(protocol)*.
pub const LASER_MAX_MS: u64 = 60_000;
/// Laser is switched off above this board temperature *(protocol)*.
pub const LASER_MAX_TEMP_DC: i16 = 600;
/// Laser is switched off below this battery voltage *(protocol)*.
pub const LASER_MIN_MV: u16 = 3_200;

// ---------------------------------------------------------------- thermal
/// Above the profile limit the current falls linearly to Low over this span *(protocol)*.
pub const THERMAL_DERATE_SPAN_DC: i32 = 150;
/// Above this temperature the output is limited to Moon *(protocol)*.
pub const THERMAL_MOON_DC: i16 = 700;
/// Above this temperature the light is switched off *(protocol)*.
pub const THERMAL_OFF_DC: i16 = 800;
/// After a thermal shutdown the light may be switched on again below this.
pub const THERMAL_OFF_CLEAR_DC: i16 = 750;
/// Turbo is refused within this distance of the profile limit *(protocol)*.
pub const TURBO_TEMP_MARGIN_DC: i16 = 50;
/// NTC node voltage above this is treated as an open sensor (or colder than about -7 degC).
pub const NTC_OPEN_MV: u16 = 2_800;
/// NTC node voltage below this is treated as a shorted sensor (hotter than about 135 degC).
pub const NTC_SHORT_MV: u16 = 100;
/// Number of consecutive bad NTC samples before a sensor fault is declared.
pub const NTC_FAULT_SAMPLES: u8 = 3;

// ---------------------------------------------------------------- battery
/// Low-voltage step-down: one level every this many ms below the profile voltage *(protocol)*.
pub const LV_STEP_PERIOD_MS: u64 = 5_000;
/// Below this (under load) the output is limited to Moon *(protocol)*.
pub const LV_MOON_MV: u16 = 3_100;
/// Below this (under load) the light is switched off *(protocol)*.
pub const LV_OFF_MV: u16 = 3_000;
/// After an empty-battery shutdown the light stays off until the resting
/// voltage is above this (or USB is present) *(protocol)*.
pub const LV_RECOVER_MV: u16 = 3_300;
/// The Moon limit needs the voltage below `LV_MOON_MV` for this long.
pub const LV_MOON_DELAY_MS: u64 = 1_000;
/// The empty shutdown needs the voltage below `LV_OFF_MV` for this long.
pub const LV_OFF_DELAY_MS: u64 = 2_000;
/// Usable capacity of the two LP601646 cells in parallel.
pub const CELL_CAPACITY_MAH: u32 = 800;
/// Load correction of the open-circuit voltage estimate, mV per A of cell current.
pub const LOAD_CORR_MV_PER_A: u32 = 120;
/// Current drawn by the MCU, radio and LDO while awake (used for runtime and SoC).
pub const MCU_AWAKE_MA: u32 = 20;
/// Assumed fast-charge current of the TP4057 with R3 = 3.3 k.
pub const CHARGE_FAST_MA: u32 = 280;
/// State of charge may change at most this fast (0.1 % per s) - the filter.
pub const SOC_SLEW_X10_PER_S: u32 = 5;
/// While discharging the SoC only rises again if the estimate is this much higher (0.1 %).
pub const SOC_RECOVER_HYST_X10: u16 = 30;
/// Ordinary dead band of the SoC filter (0.1 %).
pub const SOC_DEADBAND_X10: u16 = 5;

// ---------------------------------------------------------------- charging
/// Charging is allowed from this temperature ... *(protocol)*
pub const CHARGE_MIN_DC: i16 = 0;
/// ... up to this temperature *(protocol)*.
pub const CHARGE_MAX_DC: i16 = 450;
/// Hysteresis for resuming charging after a temperature pause.
pub const CHARGE_HYST_DC: i16 = 20;
/// Charging pauses while the LED runs above this current *(protocol)*.
pub const CHARGE_PAUSE_LED_MA: u16 = 500;
/// While charging is paused (CHG_SET high, the TP4057 may hide its status),
/// USB presence is re-checked this often ...
pub const USB_PROBE_PERIOD_MS: u64 = 10_000;
/// ... by releasing CHG_SET (10 mA trickle) for this long.
pub const USB_PROBE_MS: u64 = 200;
/// Both status pins must be high this long before USB counts as removed.
pub const USB_GONE_MS: u64 = 1_000;

// ---------------------------------------------------------------- RGB / UI
/// Battery display after switch-on *(protocol)*.
pub const BATTERY_DISPLAY_MS: u64 = 2_000;
/// Low battery red blink while the light is on, below this SoC *(protocol)*.
pub const LOW_BATTERY_PCT: u8 = 10;
/// Battery colour: green above this SoC *(protocol)*.
pub const SOC_GREEN_ABOVE_PCT: u8 = 50;
/// Battery colour: red below this SoC, yellow in between *(protocol)*.
pub const SOC_RED_BELOW_PCT: u8 = 20;

// ---------------------------------------------------------------- power
/// The MCU stays awake at least this long after boot before it may sleep
/// (lets a wake-up gesture finish and the sensors settle).
pub const MIN_AWAKE_MS: u64 = 1_500;
/// A button held this long while it does nothing (lockout, or a slide button
/// with the light off; e.g. pressed in a pocket) counts as stuck: the MCU then
/// sleeps with the button removed from the wake sources instead of staying awake.
pub const STUCK_BUTTON_MS: u64 = 10_000;
/// After a stuck-button timer wake the button counts as stuck again after this long.
pub const STUCK_BUTTON_AFTER_WAKE_MS: u64 = 300;
/// Minimum awake time after a stuck-button timer wake (no wake-up gesture to wait for).
pub const MIN_AWAKE_TIMER_WAKE_MS: u64 = 400;
/// While the button is stuck, a timer wakes the MCU this often to re-check it.
pub const STUCK_RECHECK_MS: u64 = 20_000;

// ---------------------------------------------------------------- buttons (v0.6 ladder)
// All three buttons share the BTN net (pull-up R9 10 k): main = 0 V, both slides
// = 0.212 V, › next = 0.300 V (R30 1 k), ‹ previous = 0.595 V (R31 2.2 k). GPIO3
// reads it with ADC1_CH3 at 2.5 dB (0-1050 mV). Thresholds are the midpoints.
/// ADC reading below this is the main button ● (mV) *(hardware)*.
pub const BTN_MAIN_BELOW_MV: u16 = 106;
/// From [`BTN_MAIN_BELOW_MV`] up to below this: ‹ and › together (mV) *(hardware)*.
pub const BTN_BOTH_BELOW_MV: u16 = 256;
/// From [`BTN_BOTH_BELOW_MV`] up to below this: › next (mV) *(hardware)*.
pub const BTN_NEXT_BELOW_MV: u16 = 448;
/// From [`BTN_NEXT_BELOW_MV`] up to and including this: ‹ previous; above: no button (mV) *(hardware)*.
pub const BTN_PREV_MAX_MV: u16 = 810;
/// A › or ‹ press this long is a hold (presenter: F5 / Esc).
pub const SLIDE_HOLD_MS: u64 = 800;
/// ‹ + › held this long: enter / leave presenter mode.
pub const BOTH_PRESENTER_MS: u64 = 2_000;
/// ‹ + › held this long: forget all paired computers.
pub const BOTH_FORGET_MS: u64 = 10_000;

// ---------------------------------------------------------------- presenter mode
/// Default idle time before presenter mode ends by itself (minutes) *(protocol)*.
pub const PRESENTER_IDLE_DEFAULT_MIN: u8 = 30;
/// Shortest idle time the app can set (minutes) *(protocol)*.
pub const PRESENTER_IDLE_MIN_MIN: u8 = 5;
/// Longest idle time the app can set (minutes) *(protocol)*.
pub const PRESENTER_IDLE_MAX_MIN: u8 = 120;
/// Presenter mode is refused / ended below this battery voltage ("battery empty";
/// the same limit as the laser).
pub const PRESENTER_MIN_MV: u16 = 3_200;
/// The voltage must stay below [`PRESENTER_MIN_MV`] this long before presenter mode ends.
pub const PRESENTER_EMPTY_DELAY_MS: u64 = 2_000;
/// HID advertising: fast interval (µs) for the first [`HID_ADV_FAST_PERIOD_MS`]
/// (Apple QA1931: 20 ms ... ; Windows Swift Pair: about 30 ms).
pub const HID_ADV_FAST_INTERVAL_US: u64 = 30_000;
/// HID advertising: length of the fast period after entering presenter mode or a disconnect.
pub const HID_ADV_FAST_PERIOD_MS: u64 = 30_000;
/// HID advertising: slow interval (µs), one of the values Apple QA1931 lists.
pub const HID_ADV_SLOW_INTERVAL_US: u64 = 152_500;
/// Keys waiting to be sent to the computer (older keys are kept, newer dropped).
pub const KEY_QUEUE_LEN: usize = 8;
/// Paired computers stored in flash; the oldest pairing is replaced by a new one.
pub const BONDS_MAX: usize = 4;
