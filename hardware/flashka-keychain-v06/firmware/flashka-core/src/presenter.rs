// SPDX-License-Identifier: MIT OR Apache-2.0
//! Presenter mode settings (the 4-byte Presenter characteristic) and the
//! mapping from presenter actions to HID keys.

use crate::config::{PRESENTER_IDLE_DEFAULT_MIN, PRESENTER_IDLE_MAX_MIN, PRESENTER_IDLE_MIN_MIN};
use crate::hid::HidKey;
use crate::protocol::CmdError;

/// Presenter characteristic length.
pub const PRESENTER_LEN: usize = 4;
/// Presenter flags bit 0: swap › and ‹.
pub const FLAG_SWAP: u8 = 0x01;

/// Keys used for next / previous slide.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(u8)]
pub enum KeySet {
    /// Page Down / Page Up (default; what most presenters send).
    PageUpDown = 0,
    /// Right / Left arrow (Keynote, Google Slides).
    Arrows = 1,
}

impl KeySet {
    pub fn from_u8(v: u8) -> Option<KeySet> {
        match v {
            0 => Some(KeySet::PageUpDown),
            1 => Some(KeySet::Arrows),
            _ => None,
        }
    }
}

/// What a presenter input does.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum PresenterAction {
    NextSlide,
    PreviousSlide,
    StartShow,
    EndShow,
    BlackScreen,
}

/// Persisted presenter settings.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct PresenterSettings {
    pub key_set: KeySet,
    /// Presenter mode ends after this many minutes without a button press (5-120).
    pub idle_min: u8,
    /// Swap › and ‹ (clicks and holds) in presenter mode.
    pub swap: bool,
}

impl Default for PresenterSettings {
    fn default() -> Self {
        PresenterSettings {
            key_set: KeySet::PageUpDown,
            idle_min: PRESENTER_IDLE_DEFAULT_MIN,
            swap: false,
        }
    }
}

impl PresenterSettings {
    /// Characteristic value: [key set, idle minutes, flags, reserved 0].
    pub fn encode(&self) -> [u8; PRESENTER_LEN] {
        [self.key_set as u8, self.idle_min, if self.swap { FLAG_SWAP } else { 0 }, 0]
    }

    /// Decode a write. Length must be 4 and the key set 0 or 1 (else 0x81);
    /// the idle time is clamped to 5-120 min, undefined flag bits and the
    /// reserved byte are ignored. Read back to see what is used.
    pub fn decode_write(data: &[u8]) -> Result<PresenterSettings, CmdError> {
        if data.len() != PRESENTER_LEN {
            return Err(CmdError::Invalid);
        }
        let key_set = KeySet::from_u8(data[0]).ok_or(CmdError::Invalid)?;
        Ok(PresenterSettings {
            key_set,
            idle_min: data[1].clamp(PRESENTER_IDLE_MIN_MIN, PRESENTER_IDLE_MAX_MIN),
            swap: data[2] & FLAG_SWAP != 0,
        })
    }

    /// Decode the stored bytes (settings record); invalid fields fall back to
    /// their defaults instead of failing the whole record.
    pub fn decode_stored(b: &[u8; PRESENTER_LEN]) -> PresenterSettings {
        let d = PresenterSettings::default();
        PresenterSettings {
            key_set: KeySet::from_u8(b[0]).unwrap_or(d.key_set),
            idle_min: if (PRESENTER_IDLE_MIN_MIN..=PRESENTER_IDLE_MAX_MIN).contains(&b[1]) {
                b[1]
            } else {
                d.idle_min
            },
            swap: b[2] != 0xff && b[2] & FLAG_SWAP != 0,
        }
    }

    /// Idle timeout in ms.
    pub fn idle_ms(&self) -> u64 {
        self.idle_min as u64 * 60_000
    }

    /// HID key of an action.
    pub fn key(&self, action: PresenterAction) -> HidKey {
        match (action, self.key_set) {
            (PresenterAction::NextSlide, KeySet::PageUpDown) => HidKey::PageDown,
            (PresenterAction::NextSlide, KeySet::Arrows) => HidKey::Right,
            (PresenterAction::PreviousSlide, KeySet::PageUpDown) => HidKey::PageUp,
            (PresenterAction::PreviousSlide, KeySet::Arrows) => HidKey::Left,
            (PresenterAction::StartShow, _) => HidKey::F5,
            (PresenterAction::EndShow, _) => HidKey::Escape,
            (PresenterAction::BlackScreen, _) => HidKey::B,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn defaults_and_encoding() {
        let d = PresenterSettings::default();
        assert_eq!(d.encode(), [0, 30, 0, 0]);
        assert_eq!(d.idle_ms(), 30 * 60_000);
        let s = PresenterSettings {
            key_set: KeySet::Arrows,
            idle_min: 90,
            swap: true,
        };
        assert_eq!(s.encode(), [1, 90, 1, 0]);
        assert_eq!(PresenterSettings::decode_write(&s.encode()), Ok(s));
    }

    #[test]
    fn write_validation_and_clamping() {
        assert_eq!(PresenterSettings::decode_write(&[0, 30, 0]), Err(CmdError::Invalid));
        assert_eq!(PresenterSettings::decode_write(&[0, 30, 0, 0, 0]), Err(CmdError::Invalid));
        assert_eq!(PresenterSettings::decode_write(&[2, 30, 0, 0]), Err(CmdError::Invalid));
        let s = PresenterSettings::decode_write(&[0, 1, 0xfe, 0x55]).unwrap();
        assert_eq!(s.idle_min, 5);
        assert!(!s.swap, "only bit 0 is defined");
        assert_eq!(s.encode(), [0, 5, 0, 0]);
        assert_eq!(PresenterSettings::decode_write(&[1, 200, 0xff, 0]).unwrap().idle_min, 120);
        assert_eq!(PresenterSettings::decode_write(&[1, 120, 0, 0]).unwrap().idle_min, 120);
    }

    #[test]
    fn stored_decoding_is_lenient() {
        assert_eq!(PresenterSettings::decode_stored(&[0xff; 4]), PresenterSettings::default());
        assert_eq!(
            PresenterSettings::decode_stored(&[1, 45, 1, 0]),
            PresenterSettings {
                key_set: KeySet::Arrows,
                idle_min: 45,
                swap: true
            }
        );
        assert_eq!(PresenterSettings::decode_stored(&[7, 2, 0, 0]), PresenterSettings::default());
    }

    #[test]
    fn key_sets() {
        let mut s = PresenterSettings::default();
        assert_eq!(s.key(PresenterAction::NextSlide), HidKey::PageDown);
        assert_eq!(s.key(PresenterAction::PreviousSlide), HidKey::PageUp);
        assert_eq!(s.key(PresenterAction::StartShow), HidKey::F5);
        assert_eq!(s.key(PresenterAction::EndShow), HidKey::Escape);
        assert_eq!(s.key(PresenterAction::BlackScreen), HidKey::B);
        s.key_set = KeySet::Arrows;
        assert_eq!(s.key(PresenterAction::NextSlide), HidKey::Right);
        assert_eq!(s.key(PresenterAction::PreviousSlide), HidKey::Left);
        assert_eq!(s.key(PresenterAction::StartShow), HidKey::F5);
    }
}
