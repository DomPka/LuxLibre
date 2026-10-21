// SPDX-License-Identifier: MIT OR Apache-2.0
//! Persistent settings and their wear-friendly flash log.
//!
//! Record (64 bytes, little-endian):
//!
//! | Offset | Size | Field |
//! |---|---|---|
//! | 0 | 4 | magic `"AUR5"` |
//! | 4 | 1 | format version (1) |
//! | 5 | 1 | selected profile (0..3) |
//! | 6 | 1 | remembered level (0..3) |
//! | 7 | 1 | flags: bit0 lockout, bit1 battery-empty latch |
//! | 8 | 4 | sequence number |
//! | 12 | 20 | Custom profile (Profile packet format, id = 3) |
//! | 32 | 28 | reserved (0xFF) |
//! | 60 | 4 | CRC-32 (IEEE) of bytes 0..60 |
//!
//! The store uses two 4 KiB flash sectors as a log of 64 records each. A save
//! appends a record after the newest one; when a sector is full the *other*
//! sector is erased and the log continues there. The newest valid record
//! (highest sequence number, correct CRC) wins, so a power failure during a
//! write or an erase never loses the previous settings. Nothing is written
//! when the settings did not change.

use crate::profile::{Level, Profile, ProfileId};

pub const RECORD_LEN: usize = 64;
pub const MAGIC: [u8; 4] = *b"AUR5";
pub const FORMAT_VERSION: u8 = 1;
pub const SECTOR_SIZE: u32 = 4_096;
pub const SECTORS: u32 = 2;
pub const SLOTS_PER_SECTOR: u32 = SECTOR_SIZE / RECORD_LEN as u32;
/// Flash space the store needs (two sectors).
pub const STORE_SIZE: u32 = SECTOR_SIZE * SECTORS;

const FLAG_LOCKOUT: u8 = 0x01;
const FLAG_EMPTY: u8 = 0x02;

/// The persisted settings.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Settings {
    pub profile: ProfileId,
    /// Remembered level for switch-on (Moon..High, never Turbo).
    pub level: Level,
    pub lockout: bool,
    /// Battery-empty latch (survives deep sleep, which is a reboot).
    pub empty_latch: bool,
    pub custom: Profile,
}

impl Default for Settings {
    /// Factory defaults: Balanced, Low, unlocked, Custom = Balanced.
    fn default() -> Self {
        Settings {
            profile: ProfileId::Balanced,
            level: Level::Low,
            lockout: false,
            empty_latch: false,
            custom: Profile::CUSTOM_DEFAULT,
        }
    }
}

/// CRC-32 (IEEE 802.3, reflected, init/xorout 0xFFFFFFFF).
pub fn crc32(data: &[u8]) -> u32 {
    let mut crc = 0xffff_ffffu32;
    for &b in data {
        crc ^= b as u32;
        for _ in 0..8 {
            let mask = (crc & 1).wrapping_neg();
            crc = (crc >> 1) ^ (0xedb8_8320 & mask);
        }
    }
    !crc
}

impl Settings {
    /// The profile that is active.
    pub fn active_profile(&self) -> Profile {
        Profile::builtin(self.profile).unwrap_or(self.custom)
    }

    pub fn encode(&self, seq: u32) -> [u8; RECORD_LEN] {
        let mut r = [0xffu8; RECORD_LEN];
        r[0..4].copy_from_slice(&MAGIC);
        r[4] = FORMAT_VERSION;
        r[5] = self.profile as u8;
        r[6] = self.level as u8;
        r[7] = (if self.lockout { FLAG_LOCKOUT } else { 0 }) | (if self.empty_latch { FLAG_EMPTY } else { 0 });
        r[8..12].copy_from_slice(&seq.to_le_bytes());
        r[12..32].copy_from_slice(&self.custom.encode(ProfileId::Custom));
        let crc = crc32(&r[..60]);
        r[60..64].copy_from_slice(&crc.to_le_bytes());
        r
    }

    /// Decode a record; `None` if blank, corrupt or of another format.
    pub fn decode(r: &[u8; RECORD_LEN]) -> Option<(u32, Settings)> {
        if r[0..4] != MAGIC || r[4] != FORMAT_VERSION {
            return None;
        }
        let crc = u32::from_le_bytes([r[60], r[61], r[62], r[63]]);
        if crc32(&r[..60]) != crc {
            return None;
        }
        let profile = ProfileId::from_u8(r[5])?;
        let level = Level::from_u8(r[6]).filter(|l| l.is_memorable())?;
        let seq = u32::from_le_bytes([r[8], r[9], r[10], r[11]]);
        let mut pkt = [0u8; 20];
        pkt.copy_from_slice(&r[12..32]);
        let (_, custom) = Profile::decode_raw(&pkt);
        Some((
            seq,
            Settings {
                profile,
                level,
                lockout: r[7] & FLAG_LOCKOUT != 0,
                empty_latch: r[7] & FLAG_EMPTY != 0,
                custom: custom.clamped(),
            },
        ))
    }
}

/// Minimal flash access the store needs. Offsets are relative to the start of
/// the reserved region ([`STORE_SIZE`] bytes, sector aligned).
pub trait FlashIo {
    type Error;
    fn read(&mut self, offset: u32, buf: &mut [u8]) -> Result<(), Self::Error>;
    fn write(&mut self, offset: u32, data: &[u8]) -> Result<(), Self::Error>;
    fn erase_sector(&mut self, offset: u32) -> Result<(), Self::Error>;
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct Slot {
    sector: u32,
    index: u32,
}

impl Slot {
    fn offset(self) -> u32 {
        self.sector * SECTOR_SIZE + self.index * RECORD_LEN as u32
    }
}

/// Where the next record goes and whether that needs an erase first.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct NextWrite {
    slot: Slot,
    erase: bool,
}

/// Settings log in flash.
#[derive(Clone, Copy, Debug)]
pub struct SettingsStore {
    seq: u32,
    next: NextWrite,
    stored: Option<Settings>,
}

/// Errors of [`SettingsStore::save`].
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum StoreError<E> {
    Flash(E),
    /// Written data did not read back correctly.
    Verify,
}

impl SettingsStore {
    /// Scan the region. Returns the store and the newest valid settings (or
    /// the defaults if there are none).
    pub fn load<F: FlashIo>(flash: &mut F) -> Result<(SettingsStore, Option<Settings>), F::Error> {
        let mut best: Option<(u32, Slot, Settings)> = None;
        let mut blank = [[false; SLOTS_PER_SECTOR as usize]; SECTORS as usize];
        for sector in 0..SECTORS {
            for index in 0..SLOTS_PER_SECTOR {
                let slot = Slot { sector, index };
                let mut r = [0u8; RECORD_LEN];
                flash.read(slot.offset(), &mut r)?;
                blank[sector as usize][index as usize] = r.iter().all(|&b| b == 0xff);
                if let Some((seq, s)) = Settings::decode(&r)
                    && best.is_none_or(|(b, _, _)| seq > b)
                {
                    best = Some((seq, slot, s));
                }
            }
        }
        let (seq, next, stored) = match best {
            Some((seq, slot, s)) => {
                // first blank slot after the newest record in the same sector
                let next = (slot.index + 1..SLOTS_PER_SECTOR)
                    .find(|&i| blank[slot.sector as usize][i as usize])
                    .map(|index| NextWrite {
                        slot: Slot {
                            sector: slot.sector,
                            index,
                        },
                        erase: false,
                    })
                    .unwrap_or(NextWrite {
                        slot: Slot {
                            sector: 1 - slot.sector,
                            index: 0,
                        },
                        erase: true,
                    });
                (seq, next, Some(s))
            }
            None => (
                0,
                NextWrite {
                    slot: Slot { sector: 0, index: 0 },
                    erase: !blank[0][0],
                },
                None,
            ),
        };
        Ok((SettingsStore { seq, next, stored }, stored))
    }

    /// A store that knows nothing about the flash contents (used when the
    /// region could not be read): the first save erases sector 0.
    pub fn blank() -> SettingsStore {
        SettingsStore {
            seq: 0,
            next: NextWrite {
                slot: Slot { sector: 0, index: 0 },
                erase: true,
            },
            stored: None,
        }
    }

    /// Settings currently in flash.
    pub fn stored(&self) -> Option<Settings> {
        self.stored
    }

    /// Persist `s` if it differs from what is stored. Returns `Ok(true)` if a
    /// record was written.
    pub fn save<F: FlashIo>(&mut self, flash: &mut F, s: &Settings) -> Result<bool, StoreError<F::Error>> {
        if self.stored.as_ref() == Some(s) {
            return Ok(false);
        }
        // Up to two attempts: if a slot does not verify (worn or disturbed),
        // move on to a freshly erased sector.
        for _ in 0..2 {
            let target = self.next;
            if target.erase {
                flash
                    .erase_sector(target.slot.sector * SECTOR_SIZE)
                    .map_err(StoreError::Flash)?;
            }
            let seq = self.seq.wrapping_add(1);
            let rec = s.encode(seq);
            flash.write(target.slot.offset(), &rec).map_err(StoreError::Flash)?;
            let mut back = [0u8; RECORD_LEN];
            flash.read(target.slot.offset(), &mut back).map_err(StoreError::Flash)?;
            let ok = back == rec;
            // advance the write position either way
            self.next = if target.slot.index + 1 < SLOTS_PER_SECTOR {
                NextWrite {
                    slot: Slot {
                        sector: target.slot.sector,
                        index: target.slot.index + 1,
                    },
                    erase: false,
                }
            } else {
                NextWrite {
                    slot: Slot {
                        sector: 1 - target.slot.sector,
                        index: 0,
                    },
                    erase: true,
                }
            };
            if ok {
                self.seq = seq;
                self.stored = Some(*s);
                return Ok(true);
            }
            // force the retry into the other sector
            self.next = NextWrite {
                slot: Slot {
                    sector: 1 - target.slot.sector,
                    index: 0,
                },
                erase: true,
            };
        }
        Err(StoreError::Verify)
    }
}

#[cfg(test)]
#[allow(clippy::field_reassign_with_default)]
pub(crate) mod tests {
    use super::*;

    /// NOR flash model: erase sets 0xFF, write can only clear bits.
    pub struct MockFlash {
        pub mem: Vec<u8>,
        pub erases: u32,
        pub writes: u32,
        /// Fail (stop) a write after this many bytes, to simulate power loss.
        pub cut_write_after: Option<usize>,
    }

    impl MockFlash {
        pub fn new() -> Self {
            MockFlash {
                mem: vec![0xff; STORE_SIZE as usize],
                erases: 0,
                writes: 0,
                cut_write_after: None,
            }
        }
    }

    impl FlashIo for MockFlash {
        type Error = ();
        fn read(&mut self, offset: u32, buf: &mut [u8]) -> Result<(), ()> {
            let o = offset as usize;
            buf.copy_from_slice(&self.mem[o..o + buf.len()]);
            Ok(())
        }
        fn write(&mut self, offset: u32, data: &[u8]) -> Result<(), ()> {
            self.writes += 1;
            let o = offset as usize;
            let n = self.cut_write_after.unwrap_or(data.len()).min(data.len());
            for (i, &b) in data[..n].iter().enumerate() {
                self.mem[o + i] &= b;
            }
            if n < data.len() { Err(()) } else { Ok(()) }
        }
        fn erase_sector(&mut self, offset: u32) -> Result<(), ()> {
            assert_eq!(offset % SECTOR_SIZE, 0);
            self.erases += 1;
            let o = offset as usize;
            self.mem[o..o + SECTOR_SIZE as usize].fill(0xff);
            Ok(())
        }
    }

    #[test]
    fn crc_reference() {
        assert_eq!(crc32(b"123456789"), 0xcbf4_3926);
        assert_eq!(crc32(b""), 0);
    }

    #[test]
    fn record_roundtrip() {
        let mut s = Settings::default();
        s.profile = ProfileId::Custom;
        s.level = Level::Moon;
        s.lockout = true;
        s.empty_latch = true;
        s.custom.turbo_ma = 2_500;
        let r = s.encode(77);
        assert_eq!(&r[0..4], b"AUR5");
        assert_eq!(Settings::decode(&r), Some((77, s)));
        // any corruption is detected
        for i in 0..RECORD_LEN {
            let mut bad = r;
            bad[i] ^= 0x10;
            assert_eq!(Settings::decode(&bad), None, "byte {i}");
        }
        assert_eq!(Settings::decode(&[0xff; RECORD_LEN]), None);
    }

    #[test]
    fn empty_flash_gives_none_and_first_save_needs_no_erase() {
        let mut f = MockFlash::new();
        let (mut st, s) = SettingsStore::load(&mut f).unwrap();
        assert_eq!(s, None);
        assert_eq!(st.save(&mut f, &Settings::default()), Ok(true));
        assert_eq!(f.erases, 0);
        let (_, s) = SettingsStore::load(&mut f).unwrap();
        assert_eq!(s, Some(Settings::default()));
    }

    #[test]
    fn unchanged_is_not_written() {
        let mut f = MockFlash::new();
        let (mut st, _) = SettingsStore::load(&mut f).unwrap();
        let s = Settings::default();
        assert_eq!(st.save(&mut f, &s), Ok(true));
        let w = f.writes;
        assert_eq!(st.save(&mut f, &s), Ok(false));
        assert_eq!(f.writes, w);
        // also after a reload
        let (mut st, _) = SettingsStore::load(&mut f).unwrap();
        assert_eq!(st.save(&mut f, &s), Ok(false));
    }

    #[test]
    fn log_rotates_with_few_erases() {
        let mut f = MockFlash::new();
        let (mut st, _) = SettingsStore::load(&mut f).unwrap();
        let mut s = Settings::default();
        for i in 0..1_000u32 {
            // stays a valid (already clamped) profile: moon 1..=30 <= low 30
            s.custom.moon_ma = 1 + (i % 30) as u16;
            s.level = if i % 2 == 0 { Level::High } else { Level::Low };
            assert_eq!(st.save(&mut f, &s), Ok(true));
            if i % 97 == 0 {
                // reboot in between
                let (st2, got) = SettingsStore::load(&mut f).unwrap();
                assert_eq!(got, Some(s));
                st = st2;
            }
        }
        // 64 records per erase
        assert!(f.erases <= 1_000 / 64 + 1, "erases {}", f.erases);
        let (_, got) = SettingsStore::load(&mut f).unwrap();
        assert_eq!(got, Some(s));
    }

    #[test]
    fn power_loss_during_write_keeps_previous() {
        let mut f = MockFlash::new();
        let (mut st, _) = SettingsStore::load(&mut f).unwrap();
        let mut a = Settings::default();
        a.level = Level::Medium;
        st.save(&mut f, &a).unwrap();
        let mut b = a;
        b.level = Level::High;
        f.cut_write_after = Some(30);
        assert!(st.save(&mut f, &b).is_err());
        f.cut_write_after = None;
        let (mut st, got) = SettingsStore::load(&mut f).unwrap();
        assert_eq!(got, Some(a));
        // the torn slot is skipped, the next save works
        assert_eq!(st.save(&mut f, &b), Ok(true));
        let (_, got) = SettingsStore::load(&mut f).unwrap();
        assert_eq!(got, Some(b));
    }

    #[test]
    fn sector_switch_keeps_old_until_new_written() {
        let mut f = MockFlash::new();
        let (mut st, _) = SettingsStore::load(&mut f).unwrap();
        let mut s = Settings::default();
        for i in 0..SLOTS_PER_SECTOR {
            s.custom.low_ma = 30 + i as u16;
            st.save(&mut f, &s).unwrap();
        }
        assert_eq!(f.erases, 0);
        // sector 0 full; next save erases sector 1 only
        s.custom.low_ma = 200;
        st.save(&mut f, &s).unwrap();
        assert_eq!(f.erases, 1);
        let (_, got) = SettingsStore::load(&mut f).unwrap();
        assert_eq!(got.unwrap().custom.low_ma, 200);
    }

    #[test]
    fn garbage_region_is_recovered() {
        let mut f = MockFlash::new();
        for (i, b) in f.mem.iter_mut().enumerate() {
            *b = (i * 7 + 3) as u8;
        }
        let (mut st, got) = SettingsStore::load(&mut f).unwrap();
        assert_eq!(got, None);
        assert_eq!(st.save(&mut f, &Settings::default()), Ok(true));
        assert_eq!(f.erases, 1);
        let (_, got) = SettingsStore::load(&mut f).unwrap();
        assert_eq!(got, Some(Settings::default()));
    }
}
