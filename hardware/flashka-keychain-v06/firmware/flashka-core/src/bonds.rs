// SPDX-License-Identifier: MIT OR Apache-2.0
//! Paired computers (Bluetooth bonds) and their flash record.
//!
//! Up to [`BONDS_MAX`] bonds are kept; a new pairing replaces the bond with the
//! same identity address, else takes a free entry, else replaces the oldest
//! pairing. Each bond stores what trouble-host needs to re-encrypt the link
//! (identity address, IRK, LTK, security level) and the client's CCCD table
//! (notification subscriptions must survive reconnects for bonded clients).
//!
//! Record (256 bytes, little-endian), kept in its own [`RecordLog`]
//! (region offset 0x2000, 16 records per 4 KiB sector):
//!
//! | Offset | Size | Field |
//! |---|---|---|
//! | 0 | 4 | magic `"FKB1"` |
//! | 4 | 1 | format version (1) |
//! | 5 | 1 | number of bonds (information only) |
//! | 6 | 2 | reserved (0xFF) |
//! | 8 | 4 | sequence number |
//! | 12 | 4 | next pairing number (age counter) |
//! | 16 | 4 x 59 | bonds (below) |
//! | 252 | 4 | CRC-32 (IEEE) of bytes 0..252 |
//!
//! Bond entry (59 bytes): flags (bit0 valid, bit1 IRK present, bit2
//! authenticated), identity address (6, as on air, LSB first), IRK (16), LTK
//! (16), pairing number (4), CCCD table: 4 x (attribute handle u16, value u16).

use crate::config::BONDS_MAX;
use crate::settings::{BONDS_BASE, LogRecord, RecordLog, crc32};

pub const BOND_RECORD_LEN: usize = 256;
pub const BOND_MAGIC: [u8; 4] = *b"FKB1";
pub const BOND_FORMAT_VERSION: u8 = 1;
/// CCCD entries stored per bond (the GATT database has 3 notifying characteristics).
pub const CCCD_SLOTS: usize = 4;
const ENTRY_LEN: usize = 59;
const ENTRIES_AT: usize = 16;

const F_VALID: u8 = 0x01;
const F_IRK: u8 = 0x02;
const F_AUTH: u8 = 0x04;

/// One paired computer.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct BondRecord {
    /// Identity address (public or random static), LSB first as on air.
    pub addr: [u8; 6],
    /// Identity resolving key, if the computer distributed one.
    pub irk: Option<[u8; 16]>,
    /// Long term key.
    pub ltk: [u8; 16],
    /// Paired with MITM protection (always `false` with Just Works).
    pub authenticated: bool,
    /// Client characteristic configuration: (CCCD handle, value), unused = (0, 0).
    pub cccd: [(u16, u16); CCCD_SLOTS],
    /// Pairing number: higher = paired more recently.
    pub order: u32,
}

impl BondRecord {
    pub fn new(addr: [u8; 6], irk: Option<[u8; 16]>, ltk: [u8; 16], authenticated: bool) -> Self {
        BondRecord {
            addr,
            irk,
            ltk,
            authenticated,
            cccd: [(0, 0); CCCD_SLOTS],
            order: 0,
        }
    }

    fn encode(&self, out: &mut [u8]) {
        out[0] = F_VALID | if self.irk.is_some() { F_IRK } else { 0 } | if self.authenticated { F_AUTH } else { 0 };
        out[1..7].copy_from_slice(&self.addr);
        out[7..23].copy_from_slice(&self.irk.unwrap_or([0; 16]));
        out[23..39].copy_from_slice(&self.ltk);
        out[39..43].copy_from_slice(&self.order.to_le_bytes());
        for (i, (h, v)) in self.cccd.iter().enumerate() {
            let o = 43 + i * 4;
            out[o..o + 2].copy_from_slice(&h.to_le_bytes());
            out[o + 2..o + 4].copy_from_slice(&v.to_le_bytes());
        }
    }

    fn decode(b: &[u8]) -> Option<BondRecord> {
        if b[0] & F_VALID == 0 || b[0] == 0xff {
            return None;
        }
        let mut addr = [0u8; 6];
        addr.copy_from_slice(&b[1..7]);
        let mut irk = [0u8; 16];
        irk.copy_from_slice(&b[7..23]);
        let mut ltk = [0u8; 16];
        ltk.copy_from_slice(&b[23..39]);
        let mut cccd = [(0u16, 0u16); CCCD_SLOTS];
        for (i, c) in cccd.iter_mut().enumerate() {
            let o = 43 + i * 4;
            *c = (u16::from_le_bytes([b[o], b[o + 1]]), u16::from_le_bytes([b[o + 2], b[o + 3]]));
        }
        Some(BondRecord {
            addr,
            irk: (b[0] & F_IRK != 0).then_some(irk),
            ltk,
            authenticated: b[0] & F_AUTH != 0,
            cccd,
            order: u32::from_le_bytes([b[39], b[40], b[41], b[42]]),
        })
    }
}

/// The paired computers.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct BondTable {
    pub entries: [Option<BondRecord>; BONDS_MAX],
    next_order: u32,
}

impl Default for BondTable {
    fn default() -> Self {
        Self::new()
    }
}

/// The paired-computer log.
pub type BondStore = RecordLog<BondTable, BOND_RECORD_LEN>;

impl BondTable {
    pub const fn new() -> Self {
        BondTable {
            entries: [None; BONDS_MAX],
            next_order: 1,
        }
    }

    pub fn count(&self) -> u8 {
        self.entries.iter().filter(|e| e.is_some()).count() as u8
    }

    pub fn iter(&self) -> impl Iterator<Item = &BondRecord> {
        self.entries.iter().flatten()
    }

    pub fn find(&self, addr: &[u8; 6]) -> Option<&BondRecord> {
        self.iter().find(|b| b.addr == *addr)
    }

    /// Add a new pairing. Returns the bond it pushed out (when the table was
    /// full), so the caller can also remove it from the Bluetooth stack.
    pub fn insert(&mut self, mut rec: BondRecord) -> Option<BondRecord> {
        rec.order = self.next_order;
        self.next_order = self.next_order.wrapping_add(1);
        if let Some(e) = self.entries.iter_mut().flatten().find(|b| b.addr == rec.addr) {
            *e = rec;
            return None;
        }
        if let Some(e) = self.entries.iter_mut().find(|e| e.is_none()) {
            *e = Some(rec);
            return None;
        }
        let oldest = self
            .entries
            .iter_mut()
            .min_by_key(|e| e.map_or(0, |b| b.order))
            .expect("BONDS_MAX > 0");
        oldest.replace(rec)
    }

    /// Store the CCCD table of a bonded computer. Returns `true` if it changed.
    pub fn set_cccd(&mut self, addr: &[u8; 6], cccd: &[(u16, u16)]) -> bool {
        let Some(b) = self.entries.iter_mut().flatten().find(|b| b.addr == *addr) else {
            return false;
        };
        let mut t = [(0u16, 0u16); CCCD_SLOTS];
        for (dst, src) in t.iter_mut().zip(cccd.iter()) {
            *dst = *src;
        }
        if b.cccd == t {
            return false;
        }
        b.cccd = t;
        true
    }

    /// Forget every computer.
    pub fn clear(&mut self) {
        self.entries = [None; BONDS_MAX];
    }
}

impl LogRecord<BOND_RECORD_LEN> for BondTable {
    const BASE: u32 = BONDS_BASE;

    fn encode(&self, seq: u32) -> [u8; BOND_RECORD_LEN] {
        let mut r = [0xffu8; BOND_RECORD_LEN];
        r[0..4].copy_from_slice(&BOND_MAGIC);
        r[4] = BOND_FORMAT_VERSION;
        r[5] = self.count();
        r[8..12].copy_from_slice(&seq.to_le_bytes());
        r[12..16].copy_from_slice(&self.next_order.to_le_bytes());
        for (i, e) in self.entries.iter().enumerate() {
            let o = ENTRIES_AT + i * ENTRY_LEN;
            match e {
                Some(b) => b.encode(&mut r[o..o + ENTRY_LEN]),
                None => r[o..o + ENTRY_LEN].fill(0),
            }
        }
        let crc = crc32(&r[..BOND_RECORD_LEN - 4]);
        r[BOND_RECORD_LEN - 4..].copy_from_slice(&crc.to_le_bytes());
        r
    }

    fn decode(r: &[u8; BOND_RECORD_LEN]) -> Option<(u32, Self)> {
        if r[0..4] != BOND_MAGIC || r[4] != BOND_FORMAT_VERSION {
            return None;
        }
        let crc = u32::from_le_bytes([r[252], r[253], r[254], r[255]]);
        if crc32(&r[..BOND_RECORD_LEN - 4]) != crc {
            return None;
        }
        let seq = u32::from_le_bytes([r[8], r[9], r[10], r[11]]);
        let mut t = BondTable::new();
        t.next_order = u32::from_le_bytes([r[12], r[13], r[14], r[15]]);
        for (i, e) in t.entries.iter_mut().enumerate() {
            let o = ENTRIES_AT + i * ENTRY_LEN;
            *e = BondRecord::decode(&r[o..o + ENTRY_LEN]);
        }
        Some((seq, t))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::settings::tests::MockFlash;
    use crate::settings::{STORE_SIZE, Settings, SettingsStore};

    fn bond(n: u8) -> BondRecord {
        BondRecord::new([n, 2, 3, 4, 5, 0xc0], n.is_multiple_of(2).then_some([n; 16]), [0x40 | n; 16], false)
    }

    #[test]
    fn layout_fits() {
        assert_eq!(ENTRIES_AT + BONDS_MAX * ENTRY_LEN + 4, BOND_RECORD_LEN);
        assert_eq!(43 + CCCD_SLOTS * 4, ENTRY_LEN);
    }

    #[test]
    fn insert_replace_and_evict_oldest() {
        let mut t = BondTable::new();
        for n in 1..=4 {
            assert_eq!(t.insert(bond(n)), None);
        }
        assert_eq!(t.count(), 4);
        // re-pairing computer 2 replaces its entry and makes it the newest
        let mut b2 = bond(2);
        b2.ltk = [0x99; 16];
        assert_eq!(t.insert(b2), None);
        assert_eq!(t.count(), 4);
        assert_eq!(t.find(&bond(2).addr).unwrap().ltk, [0x99; 16]);
        // a fifth computer pushes out the oldest pairing (1), then 3
        let out = t.insert(bond(5)).unwrap();
        assert_eq!(out.addr, bond(1).addr);
        let out = t.insert(bond(6)).unwrap();
        assert_eq!(out.addr, bond(3).addr);
        assert!(t.find(&bond(2).addr).is_some(), "re-paired computer kept");
        assert_eq!(t.count(), 4);
        t.clear();
        assert_eq!(t.count(), 0);
    }

    #[test]
    fn cccd_tables() {
        let mut t = BondTable::new();
        t.insert(bond(1));
        assert!(t.set_cccd(&bond(1).addr, &[(12, 1), (20, 1), (31, 0)]));
        assert!(!t.set_cccd(&bond(1).addr, &[(12, 1), (20, 1), (31, 0)]), "unchanged");
        assert_eq!(t.find(&bond(1).addr).unwrap().cccd, [(12, 1), (20, 1), (31, 0), (0, 0)]);
        assert!(!t.set_cccd(&bond(9).addr, &[(12, 1)]), "unknown computer");
    }

    #[test]
    fn record_roundtrip_and_corruption() {
        let mut t = BondTable::new();
        t.insert(bond(1));
        t.insert(bond(2));
        t.set_cccd(&bond(2).addr, &[(40, 1), (44, 2)]);
        let r = t.encode(7);
        assert_eq!(&r[0..4], b"FKB1");
        assert_eq!(r[5], 2);
        assert_eq!(BondTable::decode(&r), Some((7, t)));
        for i in 0..BOND_RECORD_LEN {
            let mut bad = r;
            bad[i] ^= 0x04;
            assert_eq!(BondTable::decode(&bad), None, "byte {i}");
        }
        assert_eq!(BondTable::decode(&[0xff; BOND_RECORD_LEN]), None);
        // empty table
        let e = BondTable::new();
        assert_eq!(BondTable::decode(&e.encode(1)), Some((1, e)));
    }

    #[test]
    fn bond_log_next_to_settings_log() {
        let mut f = MockFlash::new();
        let (mut ss, _) = SettingsStore::load(&mut f).unwrap();
        let (mut bs, none) = BondStore::load(&mut f).unwrap();
        assert_eq!(none, None);
        let mut t = BondTable::new();
        // 40 bond saves: 16 per sector -> the log rotates
        for n in 0..40u8 {
            t.insert(bond(n));
            assert_eq!(bs.save(&mut f, &t), Ok(true));
            let mut s = Settings::default();
            s.custom.moon_ma = 1 + n as u16 % 30;
            ss.save(&mut f, &s).unwrap();
        }
        let (_, got) = BondStore::load(&mut f).unwrap();
        assert_eq!(got, Some(t));
        let (_, s) = SettingsStore::load(&mut f).unwrap();
        assert_eq!(s.unwrap().custom.moon_ma, 1 + 39 % 30);
        // the bond log writes into its own 8 KiB (offset 0x2000)
        assert!(f.mem[STORE_SIZE as usize..].iter().any(|&b| b != 0xff));
        // forgetting = saving an empty table
        t.clear();
        bs.save(&mut f, &t).unwrap();
        let (_, got) = BondStore::load(&mut f).unwrap();
        assert_eq!(got.unwrap().count(), 0);
    }
}
