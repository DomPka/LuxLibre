// SPDX-License-Identifier: MIT OR Apache-2.0
//! The GATT database (`docs/ble_protocol.md` section 2). Depends only on
//! trouble-host and flashka-core, so its layout can also be checked on the host.

use flashka_core::hid::{HID_INFORMATION, PNP_ID, PROTOCOL_MODE_REPORT, REPORT_MAP, REPORT_REFERENCE_INPUT};
use flashka_core::presenter::PRESENTER_LEN;
use flashka_core::protocol::{COMMAND_MAX_LEN, INFO_TEXT, PROFILE_LEN, STATUS_LEN};
use trouble_host::prelude::*;

/// Report Map as a slice (read-only characteristic).
static REPORT_MAP_SLICE: &[u8] = &REPORT_MAP;

/// GATT database: GAP + GATT services (added by `new_with_config`), then the
/// services below in this order. Do not reorder: paired computers cache it.
#[gatt_server]
pub struct Server {
    pub battery: BatteryService,
    pub dis: DeviceInformationService,
    pub hid: HidService,
    pub control: FlashkaService,
}

/// Standard Battery Service (0x180F).
#[gatt_service(uuid = service::BATTERY)]
pub struct BatteryService {
    /// State of charge, 0-100 %.
    #[characteristic(uuid = characteristic::BATTERY_LEVEL, read, notify)]
    pub level: u8,
}

/// Device Information (0x180A) with the PnP ID HID hosts read.
#[gatt_service(uuid = service::DEVICE_INFORMATION)]
pub struct DeviceInformationService {
    /// PnP ID: USB-IF VID 0x1209 (pid.codes), PID 0x0001 (test PID), version 0.6.0.
    #[characteristic(uuid = characteristic::PNP_ID, read, value = PNP_ID)]
    pub pnp_id: [u8; 7],
}

/// HID service (0x1812): boot-keyboard layout without report ID.
/// Report Map, Input Report (+ its CCCD) and Report Reference need an
/// encrypted link; HID Information, Control Point and Protocol Mode do not
/// (trouble-host 0.6 would answer a refused write *command* with an error
/// response, which ATT does not allow, so the two write-without-response
/// characteristics stay open).
#[gatt_service(uuid = service::HUMAN_INTERFACE_DEVICE)]
pub struct HidService {
    /// bcdHID 1.11, country 0, flags: normally connectable.
    #[characteristic(uuid = characteristic::HID_INFORMATION, read, value = HID_INFORMATION)]
    pub hid_info: [u8; 4],
    /// Report Map (45 bytes, read with Read Blob when longer than MTU - 1).
    #[characteristic(uuid = characteristic::REPORT_MAP, read, permissions(read = encrypted), value = REPORT_MAP_SLICE)]
    pub report_map: &'static [u8],
    /// HID Control Point: suspend / exit suspend (ignored).
    #[characteristic(uuid = characteristic::HID_CONTROL_POINT, write_without_response)]
    pub control_point: u8,
    /// Protocol Mode: report (1); boot (0) uses the same 8-byte report.
    #[characteristic(uuid = characteristic::PROTOCOL_MODE, read, write_without_response, value = PROTOCOL_MODE_REPORT)]
    pub protocol_mode: u8,
    /// Keyboard input report: modifiers, reserved, 6 key codes. Its CCCD and
    /// Report Reference follow the value handle (see `needs_pairing`).
    #[descriptor(uuid = descriptors::REPORT_REFERENCE, read = encrypted, value = REPORT_REFERENCE_INPUT)]
    #[characteristic(uuid = characteristic::REPORT, read, notify, permissions(encrypted))]
    pub input_report: [u8; 8],
}

/// FlashKa Control service (the v1 "Aurora Control Service", same UUIDs).
/// The UUID literals are those of `flashka_core::protocol::*_UUID_STR` (the
/// macro needs literals).
#[gatt_service(uuid = "a7d40001-3c5e-4b8a-9f61-2d0c8e5b7a13")]
pub struct FlashkaService {
    /// Status, 20 bytes, read / notify.
    #[characteristic(uuid = "a7d40002-3c5e-4b8a-9f61-2d0c8e5b7a13", read, notify)]
    pub status: [u8; STATUS_LEN],
    /// Command, 1-3 bytes, write with response.
    #[characteristic(uuid = "a7d40003-3c5e-4b8a-9f61-2d0c8e5b7a13", write)]
    pub command: [u8; COMMAND_MAX_LEN],
    /// Profile, 20 bytes, read / write.
    #[characteristic(uuid = "a7d40004-3c5e-4b8a-9f61-2d0c8e5b7a13", read, write)]
    pub profile: [u8; PROFILE_LEN],
    /// Info text, read only.
    #[characteristic(uuid = "a7d40005-3c5e-4b8a-9f61-2d0c8e5b7a13", read, value = INFO_TEXT)]
    pub info: &'static str,
    /// Presenter settings, 4 bytes, read / write (protocol version 2).
    #[characteristic(uuid = "a7d40006-3c5e-4b8a-9f61-2d0c8e5b7a13", read, write)]
    pub presenter: [u8; PRESENTER_LEN],
}

/// A FlashKa Control attribute (value or the Status CCCD).
pub fn is_control_handle(server: &Server<'_>, h: u16) -> bool {
    let c = &server.control;
    h == c.status.handle
        || c.status.cccd_handle == Some(h)
        || h == c.command.handle
        || h == c.profile.handle
        || h == c.info.handle
        || h == c.presenter.handle
}

/// The HID attributes that need an encrypted link: Report Map, and the
/// Input Report value, its CCCD and its Report Reference descriptor (the
/// three attributes from the value handle on; checked on the host:
/// value 24, CCCD 25, Report Reference 26).
pub fn needs_pairing(server: &Server<'_>, h: u16) -> bool {
    let r = server.hid.input_report.handle;
    h == server.hid.report_map.handle || (r..=r + 2).contains(&h)
}
