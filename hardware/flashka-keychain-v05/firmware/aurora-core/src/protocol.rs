// SPDX-License-Identifier: MIT OR Apache-2.0
//! Bluetooth LE protocol version 1 (`docs/ble_protocol.md`): packet formats,
//! command decoding, error codes and UUIDs. All numbers little-endian.

use crate::profile::{Level, ProfileId};

/// Protocol version (Status byte 0).
pub const PROTOCOL_VERSION: u8 = 1;
/// Status characteristic length.
pub const STATUS_LEN: usize = 18;
/// Profile characteristic length.
pub const PROFILE_LEN: usize = 20;
/// Maximum Command write length.
pub const COMMAND_MAX_LEN: usize = 3;
/// Maximum Info text length.
pub const INFO_MAX_LEN: usize = 20;

/// Aurora Control Service UUID as text.
pub const SERVICE_UUID_STR: &str = "a7d40001-3c5e-4b8a-9f61-2d0c8e5b7a13";
/// Status characteristic UUID.
pub const STATUS_UUID_STR: &str = "a7d40002-3c5e-4b8a-9f61-2d0c8e5b7a13";
/// Command characteristic UUID.
pub const COMMAND_UUID_STR: &str = "a7d40003-3c5e-4b8a-9f61-2d0c8e5b7a13";
/// Profile characteristic UUID.
pub const PROFILE_UUID_STR: &str = "a7d40004-3c5e-4b8a-9f61-2d0c8e5b7a13";
/// Info characteristic UUID.
pub const INFO_UUID_STR: &str = "a7d40005-3c5e-4b8a-9f61-2d0c8e5b7a13";

/// Service UUID in over-the-air (little-endian) byte order, for the
/// "complete list of 128-bit service UUIDs" advertising structure.
pub const SERVICE_UUID_LE: [u8; 16] = uuid_le(SERVICE_UUID_STR);

/// Parse a canonical UUID string into little-endian bytes (const, used at
/// compile time; invalid input fails the build).
pub const fn uuid_le(s: &str) -> [u8; 16] {
    let b = s.as_bytes();
    assert!(b.len() == 36, "UUID must be 36 characters");
    let mut out = [0u8; 16];
    let mut i = 0; // index into string
    let mut n = 0; // byte index (big-endian order)
    while i < 36 {
        if b[i] == b'-' {
            i += 1;
            continue;
        }
        let hi = hex(b[i]);
        let lo = hex(b[i + 1]);
        out[15 - n] = (hi << 4) | lo;
        n += 1;
        i += 2;
    }
    assert!(n == 16, "UUID must have 32 hex digits");
    out
}

const fn hex(c: u8) -> u8 {
    match c {
        b'0'..=b'9' => c - b'0',
        b'a'..=b'f' => c - b'a' + 10,
        b'A'..=b'F' => c - b'A' + 10,
        _ => panic!("invalid hex digit in UUID"),
    }
}

/// ATT application error codes returned to a refused write.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(u8)]
pub enum CmdError {
    /// The button has priority (a button action in the last 3 s).
    ButtonPriority = 0x80,
    /// Invalid opcode or argument.
    Invalid = 0x81,
    /// Refused by protection (battery empty, too hot).
    Protection = 0x82,
    /// Lockout is active.
    Lockout = 0x83,
}

impl CmdError {
    pub fn code(self) -> u8 {
        self as u8
    }
}

/// Command opcodes.
pub mod opcode {
    pub const OFF: u8 = 0x01;
    pub const ON: u8 = 0x02;
    pub const LEVEL: u8 = 0x03;
    pub const PROFILE: u8 = 0x04;
    pub const OUTPUT_MA: u8 = 0x05;
    pub const LOCKOUT: u8 = 0x06;
    pub const IDENTIFY: u8 = 0x07;
    pub const SAVE: u8 = 0x08;
    pub const KEEPALIVE: u8 = 0x09;
    pub const FACTORY_RESET: u8 = 0x7f;
    /// Argument FACTORY_RESET must carry.
    pub const FACTORY_RESET_KEY: u8 = 0xa5;
}

/// A decoded Command write.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Command {
    Off,
    On,
    Level(Level),
    Profile(ProfileId),
    OutputMa(u16),
    Lockout(bool),
    Identify,
    Save,
    KeepAlive(u8),
    FactoryReset,
}

impl Command {
    /// Commands that switch or dim the light; refused with 0x80 during the
    /// 3 s app lock after a button action.
    pub fn yields_to_button(&self) -> bool {
        matches!(
            self,
            Command::Off | Command::On | Command::Level(_) | Command::Profile(_) | Command::OutputMa(_)
        )
    }
}

/// Decode a Command write. Lengths are exact: an opcode with missing or extra
/// argument bytes is invalid (0x81).
pub fn decode_command(data: &[u8]) -> Result<Command, CmdError> {
    use opcode::*;
    let (&op, args) = data.split_first().ok_or(CmdError::Invalid)?;
    let none = |c: Command| if args.is_empty() { Ok(c) } else { Err(CmdError::Invalid) };
    let one = || -> Result<u8, CmdError> {
        if args.len() == 1 {
            Ok(args[0])
        } else {
            Err(CmdError::Invalid)
        }
    };
    match op {
        OFF => none(Command::Off),
        ON => none(Command::On),
        LEVEL => Level::from_u8(one()?).map(Command::Level).ok_or(CmdError::Invalid),
        PROFILE => ProfileId::from_u8(one()?).map(Command::Profile).ok_or(CmdError::Invalid),
        OUTPUT_MA => {
            if args.len() != 2 {
                return Err(CmdError::Invalid);
            }
            Ok(Command::OutputMa(u16::from_le_bytes([args[0], args[1]])))
        }
        LOCKOUT => match one()? {
            0 => Ok(Command::Lockout(false)),
            1 => Ok(Command::Lockout(true)),
            _ => Err(CmdError::Invalid),
        },
        IDENTIFY => none(Command::Identify),
        SAVE => none(Command::Save),
        KEEPALIVE => Ok(Command::KeepAlive(one()?)),
        FACTORY_RESET => {
            if one()? == FACTORY_RESET_KEY {
                Ok(Command::FactoryReset)
            } else {
                Err(CmdError::Invalid)
            }
        }
        _ => Err(CmdError::Invalid),
    }
}

/// Status flag bits (Status byte 1).
pub mod status_flags {
    pub const LIGHT_ON: u8 = 1 << 0;
    pub const TURBO_ACTIVE: u8 = 1 << 1;
    pub const CHARGING: u8 = 1 << 2;
    pub const CHARGE_COMPLETE: u8 = 1 << 3;
    pub const USB_POWER: u8 = 1 << 4;
    pub const LOCKOUT: u8 = 1 << 5;
    pub const THERMAL_LIMIT: u8 = 1 << 6;
    pub const BATTERY_LIMIT: u8 = 1 << 7;
}

/// Level byte value for "exact current set by the app".
pub const LEVEL_EXACT: u8 = 0xff;
/// Runtime value for "unknown / off".
pub const RUNTIME_UNKNOWN: u16 = 0xffff;

/// Control source (Status byte 13).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(u8)]
pub enum ControlSource {
    None = 0,
    Button = 1,
    App = 2,
    /// Protection or timer.
    Auto = 3,
}

/// The Status characteristic (18 bytes).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Status {
    pub flags: u8,
    pub profile: u8,
    pub level: u8,
    pub led_ma: u16,
    pub vbat_mv: u16,
    pub soc_pct: u8,
    pub temp_dc: i16,
    pub turbo_left_s: u16,
    pub source: ControlSource,
    pub app_lock_s: u8,
    pub runtime_min: u16,
    pub laser_on: bool,
}

impl Status {
    pub fn encode(&self) -> [u8; STATUS_LEN] {
        let mut b = [0u8; STATUS_LEN];
        b[0] = PROTOCOL_VERSION;
        b[1] = self.flags;
        b[2] = self.profile;
        b[3] = self.level;
        b[4..6].copy_from_slice(&self.led_ma.to_le_bytes());
        b[6..8].copy_from_slice(&self.vbat_mv.to_le_bytes());
        b[8] = self.soc_pct;
        b[9..11].copy_from_slice(&self.temp_dc.to_le_bytes());
        b[11..13].copy_from_slice(&self.turbo_left_s.to_le_bytes());
        b[13] = self.source as u8;
        b[14] = self.app_lock_s;
        b[15..17].copy_from_slice(&self.runtime_min.to_le_bytes());
        b[17] = self.laser_on as u8;
        b
    }

    /// The part of the status whose change triggers an immediate notification.
    /// Battery voltage, temperature, turbo countdown, app-lock countdown and
    /// runtime change continuously and are carried by the 2 s periodic
    /// notification instead.
    pub fn change_key(&self) -> (u8, u8, u8, u16, u8, u8, bool) {
        (
            self.flags,
            self.profile,
            self.level,
            self.led_ma,
            self.soc_pct,
            self.source as u8,
            self.laser_on,
        )
    }
}

/// Text of the Info characteristic (<= 20 bytes UTF-8): product and firmware version.
pub const INFO_TEXT: &str = "Aurora++ fw 0.5.0";

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn uuid_bytes() {
        assert_eq!(
            SERVICE_UUID_LE,
            [
                0x13, 0x7a, 0x5b, 0x8e, 0x0c, 0x2d, 0x61, 0x9f, 0x8a, 0x4b, 0x5e, 0x3c, 0x01, 0x00, 0xd4,
                0xa7
            ]
        );
        assert_eq!(uuid_le(STATUS_UUID_STR)[12], 0x02);
    }

    #[test]
    fn info_fits() {
        assert!(INFO_TEXT.len() <= INFO_MAX_LEN, "{}", INFO_TEXT.len());
    }

    #[test]
    fn decode_valid() {
        assert_eq!(decode_command(&[0x01]), Ok(Command::Off));
        assert_eq!(decode_command(&[0x02]), Ok(Command::On));
        assert_eq!(decode_command(&[0x03, 4]), Ok(Command::Level(Level::Turbo)));
        assert_eq!(decode_command(&[0x04, 3]), Ok(Command::Profile(ProfileId::Custom)));
        assert_eq!(decode_command(&[0x05, 0xe8, 0x03]), Ok(Command::OutputMa(1_000)));
        assert_eq!(decode_command(&[0x06, 1]), Ok(Command::Lockout(true)));
        assert_eq!(decode_command(&[0x06, 0]), Ok(Command::Lockout(false)));
        assert_eq!(decode_command(&[0x07]), Ok(Command::Identify));
        assert_eq!(decode_command(&[0x08]), Ok(Command::Save));
        assert_eq!(decode_command(&[0x09, 200]), Ok(Command::KeepAlive(200)));
        assert_eq!(decode_command(&[0x7f, 0xa5]), Ok(Command::FactoryReset));
    }

    #[test]
    fn decode_invalid() {
        let bad: &[&[u8]] = &[
            &[],
            &[0x00],
            &[0x0a],
            &[0x01, 0],
            &[0x03],
            &[0x03, 5],
            &[0x04, 4],
            &[0x05, 1],
            &[0x05, 1, 2, 3],
            &[0x06, 2],
            &[0x09],
            &[0x7f, 0x00],
            &[0x7f],
            &[0x80],
        ];
        for b in bad {
            assert_eq!(decode_command(b), Err(CmdError::Invalid), "{b:?}");
        }
    }

    #[test]
    fn error_codes() {
        assert_eq!(CmdError::ButtonPriority.code(), 0x80);
        assert_eq!(CmdError::Invalid.code(), 0x81);
        assert_eq!(CmdError::Protection.code(), 0x82);
        assert_eq!(CmdError::Lockout.code(), 0x83);
    }

    #[test]
    fn button_priority_set() {
        assert!(Command::Off.yields_to_button());
        assert!(Command::Profile(ProfileId::Extreme).yields_to_button());
        assert!(Command::OutputMa(5).yields_to_button());
        assert!(!Command::Lockout(true).yields_to_button());
        assert!(!Command::KeepAlive(5).yields_to_button());
        assert!(!Command::Save.yields_to_button());
        assert!(!Command::Identify.yields_to_button());
    }

    #[test]
    fn status_layout() {
        let s = Status {
            flags: 0b1010_0101,
            profile: 1,
            level: 3,
            led_ma: 600,
            vbat_mv: 3_850,
            soc_pct: 61,
            temp_dc: -125,
            turbo_left_s: 42,
            source: ControlSource::App,
            app_lock_s: 2,
            runtime_min: 0xffff,
            laser_on: true,
        };
        let b = s.encode();
        assert_eq!(b.len(), 18);
        assert_eq!(b[0], 1);
        assert_eq!(b[1], 0b1010_0101);
        assert_eq!(b[2], 1);
        assert_eq!(b[3], 3);
        assert_eq!(u16::from_le_bytes([b[4], b[5]]), 600);
        assert_eq!(u16::from_le_bytes([b[6], b[7]]), 3_850);
        assert_eq!(b[8], 61);
        assert_eq!(i16::from_le_bytes([b[9], b[10]]), -125);
        assert_eq!(u16::from_le_bytes([b[11], b[12]]), 42);
        assert_eq!(b[13], 2);
        assert_eq!(b[14], 2);
        assert_eq!(u16::from_le_bytes([b[15], b[16]]), 0xffff);
        assert_eq!(b[17], 1);
    }
}
