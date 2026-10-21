// SPDX-License-Identifier: MIT OR Apache-2.0
//! Bluetooth LE HID keyboard (HID over GATT) constants for presenter mode,
//! and the guard against the trouble-host 0.6 OOB pairing panic.
//!
//! The report map is the standard boot keyboard (8-byte input report:
//! modifiers, reserved, six key codes) **without a report ID** and without the
//! LED output report: one Report characteristic, no output report needed.

/// A key the presenter sends (HID usage page 0x07).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum HidKey {
    PageDown,
    PageUp,
    Right,
    Left,
    F5,
    Escape,
    B,
}

impl HidKey {
    /// Usage ID on the keyboard page (HID Usage Tables, page 0x07).
    pub const fn usage(self) -> u8 {
        match self {
            HidKey::B => 0x05,
            HidKey::Escape => 0x29,
            HidKey::F5 => 0x3e,
            HidKey::PageUp => 0x4b,
            HidKey::PageDown => 0x4e,
            HidKey::Right => 0x4f,
            HidKey::Left => 0x50,
        }
    }
}

/// Length of the keyboard input report.
pub const KEY_REPORT_LEN: usize = 8;

/// Input report with one key pressed (no modifier).
pub const fn key_report(key: HidKey) -> [u8; KEY_REPORT_LEN] {
    [0, 0, key.usage(), 0, 0, 0, 0, 0]
}

/// Input report "all keys released".
pub const KEY_RELEASE: [u8; KEY_REPORT_LEN] = [0; KEY_REPORT_LEN];

/// Report Map (0x2A4B): boot keyboard input report, no report ID, no LEDs.
pub const REPORT_MAP: [u8; 45] = [
    0x05, 0x01, // Usage Page (Generic Desktop)
    0x09, 0x06, // Usage (Keyboard)
    0xa1, 0x01, // Collection (Application)
    0x05, 0x07, //   Usage Page (Keyboard/Keypad)
    0x19, 0xe0, //   Usage Minimum (Left Control)
    0x29, 0xe7, //   Usage Maximum (Right GUI)
    0x15, 0x00, //   Logical Minimum (0)
    0x25, 0x01, //   Logical Maximum (1)
    0x75, 0x01, //   Report Size (1)
    0x95, 0x08, //   Report Count (8)
    0x81, 0x02, //   Input (Data, Variable, Absolute) - modifier byte
    0x95, 0x01, //   Report Count (1)
    0x75, 0x08, //   Report Size (8)
    0x81, 0x01, //   Input (Constant) - reserved byte
    0x95, 0x06, //   Report Count (6)
    0x75, 0x08, //   Report Size (8)
    0x15, 0x00, //   Logical Minimum (0)
    0x25, 0x65, //   Logical Maximum (101)
    0x05, 0x07, //   Usage Page (Keyboard/Keypad)
    0x19, 0x00, //   Usage Minimum (0)
    0x29, 0x65, //   Usage Maximum (101)
    0x81, 0x00, //   Input (Data, Array) - six key codes
    0xc0, // End Collection
];

/// Report Reference descriptor (0x2908) of the input report: report ID 0
/// (none), report type 1 = input.
pub const REPORT_REFERENCE_INPUT: [u8; 2] = [0x00, 0x01];

/// HID Information (0x2A4A): bcdHID 1.11, country code 0, flags bit1
/// "normally connectable".
pub const HID_INFORMATION: [u8; 4] = [0x11, 0x01, 0x00, 0x02];

/// Protocol Mode (0x2A4E) value "report protocol". The report map is the boot
/// keyboard layout, so the same 8-byte report is valid in both modes.
pub const PROTOCOL_MODE_REPORT: u8 = 0x01;

/// PnP ID (0x2A50): vendor ID source 2 (USB-IF), VID 0x1209 (pid.codes),
/// PID 0x0001 (pid.codes test PID - apply for a free PID before
/// distributing), product version 0x0060 (0.6.0). Little-endian.
pub const PNP_ID: [u8; 7] = [0x02, 0x09, 0x12, 0x01, 0x00, 0x60, 0x00];

/// GAP appearance "Keyboard" (category 0x00F, subcategory 0x001).
pub const APPEARANCE_KEYBOARD: u16 = 0x03c1;

/// 16-bit UUID of the HID service.
pub const HID_SERVICE_UUID16: u16 = 0x1812;

/// L2CAP channel of the LE Security Manager Protocol.
const L2CAP_CID_SMP: u16 = 0x0006;
/// SMP Pairing Request opcode.
const SMP_PAIRING_REQUEST: u8 = 0x01;
/// AuthReq bit "Secure Connections".
const SMP_AUTHREQ_SC: u8 = 0x08;

/// Guard for trouble-host 0.6.0, whose peripheral pairing code reaches
/// `todo!("OOB not implemented")` (a panic) when a central's Pairing Request
/// sets the "OOB data present" flag.
///
/// `l2cap` = the payload of an incoming ACL packet (first fragment), starting
/// with the 4-byte L2CAP basic header. If it is an SMP Pairing Request with
/// the OOB flag set, the request's Secure Connections bit is cleared in place:
/// trouble-host then refuses the request at once with Pairing Failed (it only
/// supports LE Secure Connections) and never reaches the OOB code.
/// Returns `true` if the packet was changed.
pub fn smp_reject_oob(l2cap: &mut [u8]) -> bool {
    // L2CAP header (len, cid) + SMP code, IO cap, OOB flag, AuthReq, ...
    if l2cap.len() < 4 + 7 {
        return false;
    }
    let len = u16::from_le_bytes([l2cap[0], l2cap[1]]);
    let cid = u16::from_le_bytes([l2cap[2], l2cap[3]]);
    if cid != L2CAP_CID_SMP || len < 7 || l2cap[4] != SMP_PAIRING_REQUEST || l2cap[6] == 0 {
        return false;
    }
    l2cap[7] &= !SMP_AUTHREQ_SC;
    true
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Walk the short items of the report map: collections balance and the
    /// input report is 64 bits = 8 bytes.
    #[test]
    fn report_map_is_an_8_byte_keyboard() {
        let mut i = 0;
        let (mut size, mut count, mut depth, mut input_bits) = (0u32, 0u32, 0i32, 0u32);
        let mut saw_report_id = false;
        while i < REPORT_MAP.len() {
            let prefix = REPORT_MAP[i];
            let n = match prefix & 0x03 {
                3 => 4,
                k => k as usize,
            };
            let data = if n > 0 { REPORT_MAP[i + 1] as u32 } else { 0 };
            match prefix & 0xfc {
                0x74 => size = data,
                0x94 => count = data,
                0x80 => input_bits += size * count,
                0xa0 => depth += 1,
                0xc0 => depth -= 1,
                0x84 => saw_report_id = true,
                0x90 => panic!("output report present"),
                _ => {}
            }
            i += 1 + n;
        }
        assert_eq!(i, REPORT_MAP.len());
        assert_eq!(depth, 0);
        assert_eq!(input_bits, 8 * KEY_REPORT_LEN as u32);
        assert!(!saw_report_id, "HOGP report without report ID");
    }

    #[test]
    fn key_codes() {
        assert_eq!(HidKey::PageDown.usage(), 0x4e);
        assert_eq!(HidKey::PageUp.usage(), 0x4b);
        assert_eq!(HidKey::Right.usage(), 0x4f);
        assert_eq!(HidKey::Left.usage(), 0x50);
        assert_eq!(HidKey::F5.usage(), 0x3e);
        assert_eq!(HidKey::Escape.usage(), 0x29);
        assert_eq!(HidKey::B.usage(), 0x05);
        assert_eq!(key_report(HidKey::B), [0, 0, 0x05, 0, 0, 0, 0, 0]);
        assert_eq!(KEY_RELEASE, [0; 8]);
    }

    #[test]
    fn gatt_constants() {
        assert_eq!(REPORT_REFERENCE_INPUT, [0, 1]);
        assert_eq!(u16::from_le_bytes([HID_INFORMATION[0], HID_INFORMATION[1]]), 0x0111);
        assert_eq!(HID_INFORMATION[3] & 0x02, 0x02);
        assert_eq!(PNP_ID[0], 2);
        assert_eq!(u16::from_le_bytes([PNP_ID[1], PNP_ID[2]]), 0x1209);
        assert_eq!(u16::from_le_bytes([PNP_ID[3], PNP_ID[4]]), 0x0001);
        assert_eq!(APPEARANCE_KEYBOARD, (0x00f << 6) | 0x001);
    }

    #[test]
    fn oob_guard() {
        // L2CAP len 7, CID 6, Pairing Request: IO NoInputNoOutput, OOB present,
        // AuthReq bonding|MITM|SC, key 16, init kd 0x0d, resp kd 0x0d
        let mut req = [0x07, 0x00, 0x06, 0x00, 0x01, 0x03, 0x01, 0x0d, 0x10, 0x0d, 0x0d];
        assert!(smp_reject_oob(&mut req));
        assert_eq!(req[7], 0x05, "SC bit cleared, the rest kept");
        // without OOB: untouched
        let mut req = [0x07, 0x00, 0x06, 0x00, 0x01, 0x03, 0x00, 0x0d, 0x10, 0x0d, 0x0d];
        let before = req;
        assert!(!smp_reject_oob(&mut req));
        assert_eq!(req, before);
        // other SMP commands, other channels, short frames: untouched
        let mut rsp = [0x07, 0x00, 0x06, 0x00, 0x02, 0x03, 0x01, 0x0d, 0x10, 0x0d, 0x0d];
        assert!(!smp_reject_oob(&mut rsp));
        let mut att = [0x07, 0x00, 0x04, 0x00, 0x01, 0x03, 0x01, 0x0d, 0x10, 0x0d, 0x0d];
        assert!(!smp_reject_oob(&mut att));
        let mut short = [0x03, 0x00, 0x06, 0x00, 0x01, 0x03, 0x01];
        assert!(!smp_reject_oob(&mut short));
    }
}
