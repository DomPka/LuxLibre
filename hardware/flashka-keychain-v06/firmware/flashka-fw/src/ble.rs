// SPDX-License-Identifier: MIT OR Apache-2.0
//! Bluetooth LE peripheral (`docs/ble_protocol.md`, version 2).
//!
//! * Flashlight mode: advertising windows for the app (FlashKa Control
//!   service UUID), no pairing - exactly as v0.5.
//! * Presenter mode: advertising as a HID keyboard (appearance 0x03C1,
//!   service 0x1812), bondable, LE Secure Connections "Just Works"; key
//!   presses go out as input report notifications (press, then release).
//!
//! GATT database (one layout for both modes, so that paired computers never
//! see it change): GAP + GATT, Battery Service, Device Information (PnP ID),
//! HID (HID Information, Report Map, HID Control Point, Protocol Mode, Input
//! Report + Report Reference) and the FlashKa Control service.
//!
//! All decisions are made by `flashka_core::Controller`; this module moves
//! bytes between the GATT attributes and the controller, and keeps the bonds
//! (paired computers) in sync between trouble-host and the flash record.

use core::cell::{Cell, RefCell};
use core::fmt::Write as _;
use core::sync::atomic::{AtomicU8, Ordering};

use bt_hci::controller::ExternalController;
use embassy_executor::Spawner;
use embassy_futures::select::{Either, Either3, select, select3};
use embassy_sync::blocking_mutex::Mutex;
use embassy_sync::blocking_mutex::raw::CriticalSectionRawMutex;
use embassy_time::{Duration, Timer};
use esp_hal::efuse::{InterfaceMacAddress, interface_mac_address};
use esp_hal::peripherals::BT;
use esp_hal::rng::Trng;
use esp_radio::ble::controller::BleConnector;
use flashka_core::bonds::{BondRecord, BondTable, CCCD_SLOTS};
use flashka_core::config::{
    ADV_FAST_INTERVAL_MS, ADV_SLOW_INTERVAL_MS, HID_ADV_FAST_INTERVAL_US, HID_ADV_SLOW_INTERVAL_US,
    STATUS_NOTIFY_MIN_GAP_MS, STATUS_NOTIFY_PERIOD_MS,
};
use flashka_core::controller::AdvMode;
use flashka_core::hid::{APPEARANCE_KEYBOARD, HID_SERVICE_UUID16, KEY_RELEASE, key_report};
use flashka_core::protocol::{CmdError, COMMAND_MAX_LEN, SERVICE_UUID_LE};
use log::{error, info, warn};
use static_cell::StaticCell;
use trouble_host::prelude::*;

pub use crate::gatt::Server;
use crate::gatt::{is_control_handle, needs_pairing};
use crate::hci::GuardedConnector;
use crate::{now_ms, with_controller};

/// One central at a time.
pub const CONNECTIONS_MAX: usize = 1;
/// L2CAP channels: signalling + ATT (SMP is a fixed channel).
pub const L2CAP_CHANNELS_MAX: usize = 2;
/// Presenter mode: a link that is not encrypted after this long is dropped,
/// so that a stray central cannot block the computer.
const PRESENTER_UNENCRYPTED_TIMEOUT_MS: u64 = 30_000;
/// Presenter mode: ask for security ourselves if the computer has not
/// started pairing / encryption after this long.
const PRESENTER_SECURITY_REQUEST_MS: u64 = 3_000;
/// Flashlight mode: a paired computer that reconnects on its own (HID
/// auto-reconnect) is dropped after this long unless it uses the FlashKa
/// Control service (the app running on that computer).
const HOST_IN_FLASHLIGHT_MODE_MS: u64 = 10_000;
/// Gap between the key-down and the key-up report.
const KEY_RELEASE_GAP_MS: u64 = 10;
/// After a mode change the link is dropped this much later, so that the
/// response to the app's PRESENTER write is sent first.
const MODE_CHANGE_DISCONNECT_MS: u64 = 300;

pub type BleController = ExternalController<GuardedConnector, 20>;
pub type BleStack = Stack<'static, BleController, DefaultPacketPool>;
type Resources = HostResources<DefaultPacketPool, CONNECTIONS_MAX, L2CAP_CHANNELS_MAX>;

// ------------------------------------------------------------------ adv mode

static ADV_MODE: AtomicU8 = AtomicU8::new(0);

/// Called by the control loop with the controller's advertising request.
pub fn set_adv_mode(mode: AdvMode) {
    let v = match mode {
        AdvMode::Off => 0,
        AdvMode::Fast => 1,
        AdvMode::Slow => 2,
        AdvMode::HidFast => 3,
        AdvMode::HidSlow => 4,
    };
    ADV_MODE.store(v, Ordering::Relaxed);
}

fn adv_mode() -> AdvMode {
    match ADV_MODE.load(Ordering::Relaxed) {
        1 => AdvMode::Fast,
        2 => AdvMode::Slow,
        3 => AdvMode::HidFast,
        4 => AdvMode::HidSlow,
        _ => AdvMode::Off,
    }
}

async fn wait_adv_wanted() -> AdvMode {
    loop {
        let m = adv_mode();
        if m != AdvMode::Off {
            return m;
        }
        Timer::after(Duration::from_millis(100)).await;
    }
}

async fn adv_mode_changed(from: AdvMode) {
    loop {
        Timer::after(Duration::from_millis(100)).await;
        if adv_mode() != from {
            return;
        }
    }
}

// ------------------------------------------------------------------ bonds

/// Paired computers shared between the BLE task (pairing, CCCD changes) and
/// the control loop (flash writes).
pub struct BondShared {
    pub table: BondTable,
    /// The table differs from the flash record.
    pub dirty: bool,
    /// The bonds must also be removed from trouble-host (forget request).
    forget_stack: bool,
}

static BONDS: Mutex<CriticalSectionRawMutex, RefCell<BondShared>> = Mutex::new(RefCell::new(BondShared {
    table: BondTable::new(),
    dirty: false,
    forget_stack: false,
}));

pub fn with_bonds<R>(f: impl FnOnce(&mut BondShared) -> R) -> R {
    BONDS.lock(|b| f(&mut b.borrow_mut()))
}

/// Bonds loaded from flash at boot.
pub fn init_bonds(table: BondTable) {
    with_bonds(|b| {
        b.table = table;
        b.dirty = false;
    });
}

/// Forget every paired computer (flash record and Bluetooth stack).
pub fn forget_all_bonds() {
    with_bonds(|b| {
        b.table.clear();
        b.dirty = true;
        b.forget_stack = true;
    });
}

fn identity_of(b: &BondRecord) -> Identity {
    Identity {
        bd_addr: BdAddr::new(b.addr),
        irk: b.irk.map(IdentityResolvingKey::from_le_bytes),
    }
}

fn bond_information(b: &BondRecord) -> BondInformation {
    let level = if b.authenticated {
        SecurityLevel::EncryptedAuthenticated
    } else {
        SecurityLevel::Encrypted
    };
    BondInformation::new(identity_of(b), LongTermKey::from_le_bytes(b.ltk), level, true)
}

fn record_of(bi: &BondInformation) -> BondRecord {
    let mut addr = [0u8; 6];
    addr.copy_from_slice(bi.identity.bd_addr.raw());
    BondRecord::new(
        addr,
        bi.identity.irk.map(|k| k.to_le_bytes()),
        bi.ltk.to_le_bytes(),
        bi.security_level == SecurityLevel::EncryptedAuthenticated,
    )
}

/// The bond of the computer behind this link (resolves private addresses with the IRK).
fn bond_of(conn: &Connection<'_, DefaultPacketPool>) -> Option<BondRecord> {
    let addr = conn.peer_address();
    with_bonds(|b| b.table.iter().find(|r| identity_of(r).match_address(&addr)).copied())
}

/// Apply a pending forget request to trouble-host. Returns `true` if one was applied.
fn apply_forget(stack: &BleStack) -> bool {
    if !with_bonds(|b| core::mem::take(&mut b.forget_stack)) {
        return false;
    }
    for bi in stack.get_bond_information() {
        if let Err(e) = stack.remove_bond_information(bi.identity) {
            warn!("[bonds] remove from stack: {:?}", e);
        }
    }
    info!("[bonds] all paired computers forgotten");
    true
}

// ------------------------------------------------------------------ start

static RESOURCES: StaticCell<Resources> = StaticCell::new();
static STACK: StaticCell<BleStack> = StaticCell::new();
static SERVER: StaticCell<Server<'static>> = StaticCell::new();
static NAME: StaticCell<heapless::String<16>> = StaticCell::new();

/// `FlashKa-XXXX`, XXXX = last two bytes of the BLE MAC (upper-case hex). The
/// controller's public address is the eFuse base MAC with the Bluetooth
/// offset - the same value esp-radio hands to the controller. It never
/// changes, so paired computers always find the light again.
fn device_name() -> &'static str {
    let mac = interface_mac_address(InterfaceMacAddress::Bluetooth);
    let b = mac.as_bytes();
    let name = NAME.init(heapless::String::new());
    let _ = write!(name, "FlashKa-{:02X}{:02X}", b[4], b[5]);
    info!("[ble] address {}, name {}", mac, name.as_str());
    name.as_str()
}

/// Bring up the controller and the host and spawn the BLE tasks. On error
/// the flashlight keeps working without Bluetooth.
pub fn start(spawner: &Spawner, bt: BT<'static>) -> Result<(), &'static str> {
    let config = esp_radio::ble::Config::default().with_max_connections(CONNECTIONS_MAX as u8);
    let connector = BleConnector::new(bt, config).map_err(|_| "BLE controller init failed")?;
    // The TRNG has an entropy source once the radio runs (esp-radio enables it
    // at the end of the BLE init); it seeds the security manager's CSPRNG.
    // Checked here: trouble-host's build() panics on an unseeded generator.
    let mut trng = Trng::try_new().map_err(|_| "no TRNG entropy source")?;
    let controller: BleController = ExternalController::new(GuardedConnector::new(connector));
    let resources = RESOURCES.init(HostResources::new());
    let stack: &'static BleStack =
        STACK.init(trouble_host::new(controller, resources).set_random_generator_seed(&mut trng));
    // LE Secure Connections "Just Works": no display, no keyboard.
    stack.set_io_capabilities(IoCapabilities::NoInputNoOutput);
    // Paired computers from flash (before advertising starts).
    let table = with_bonds(|b| b.table);
    for r in table.iter() {
        if let Err(e) = stack.add_bond_information(bond_information(r)) {
            warn!("[bonds] restore failed: {:?}", e);
        }
    }
    info!("[bonds] {} paired computer(s) restored", table.count());
    let Host {
        peripheral, runner, ..
    } = stack.build();

    let name = device_name();
    let server = Server::new_with_config(GapConfig::Peripheral(PeripheralConfig {
        name,
        appearance: &appearance::human_interface_device::KEYBOARD,
    }))?;
    let server: &'static Server<'static> = SERVER.init(server);
    refresh_all(server);
    // handle map for bring-up with a GATT client (nRF Connect)
    info!(
        "[ble] handles: battery {}, PnP ID {}, report map {}, input report {}, status {}, presenter {}",
        server.battery.level.handle,
        server.dis.pnp_id.handle,
        server.hid.report_map.handle,
        server.hid.input_report.handle,
        server.control.status.handle,
        server.control.presenter.handle
    );

    spawner.spawn(host_task(runner).map_err(|_| "spawn host task")?);
    spawner.spawn(peripheral_task(peripheral, stack, server, name).map_err(|_| "spawn peripheral task")?);
    Ok(())
}

// ------------------------------------------------------------------ attribute values

fn refresh_status(server: &Server<'_>) {
    let now = now_ms();
    if let Some(s) = with_controller(|c| c.status(now).encode()) {
        let _ = server.set(&server.control.status, &s);
    }
}

fn refresh_profile(server: &Server<'_>) {
    if let Some(p) = with_controller(|c| c.profile_packet()) {
        let _ = server.set(&server.control.profile, &p);
    }
}

fn refresh_presenter(server: &Server<'_>) {
    if let Some(p) = with_controller(|c| c.presenter_packet()) {
        let _ = server.set(&server.control.presenter, &p);
    }
}

fn refresh_battery(server: &Server<'_>) {
    if let Some(b) = with_controller(|c| c.battery_percent()) {
        let _ = server.set(&server.battery.level, &b);
    }
}

fn refresh_all(server: &Server<'_>) {
    refresh_status(server);
    refresh_profile(server);
    refresh_presenter(server);
    refresh_battery(server);
}

// ------------------------------------------------------------------ tasks

#[embassy_executor::task]
async fn host_task(mut runner: Runner<'static, BleController, DefaultPacketPool>) {
    loop {
        if let Err(e) = runner.run().await {
            error!("[ble] host stopped: {:?}", e);
            Timer::after(Duration::from_secs(1)).await;
        }
    }
}

/// Advertising and scan response data of both modes.
struct AdvData {
    app: ([u8; 31], usize),
    hid: ([u8; 31], usize),
    scan: ([u8; 31], usize),
}

fn adv_data(name: &str) -> AdvData {
    // Flashlight mode (as v0.5): flags + the 128-bit FlashKa Control service UUID (21 bytes).
    let mut app = [0u8; 31];
    let app_len = AdStructure::encode_slice(
        &[
            AdStructure::Flags(LE_GENERAL_DISCOVERABLE | BR_EDR_NOT_SUPPORTED),
            AdStructure::ServiceUuids128(&[SERVICE_UUID_LE]),
        ],
        &mut app[..],
    )
    .unwrap_or(0);
    // Presenter mode: flags + appearance "keyboard" + HID service + name (25 bytes).
    let appearance = APPEARANCE_KEYBOARD.to_le_bytes();
    let mut hid = [0u8; 31];
    let hid_len = AdStructure::encode_slice(
        &[
            AdStructure::Flags(LE_GENERAL_DISCOVERABLE | BR_EDR_NOT_SUPPORTED),
            AdStructure::Unknown {
                ty: 0x19,
                data: &appearance,
            },
            AdStructure::ServiceUuids16(&[HID_SERVICE_UUID16.to_le_bytes()]),
            AdStructure::CompleteLocalName(name.as_bytes()),
        ],
        &mut hid[..],
    )
    .unwrap_or(0);
    // Scan response: complete local name "FlashKa-XXXX".
    let mut scan = [0u8; 31];
    let scan_len =
        AdStructure::encode_slice(&[AdStructure::CompleteLocalName(name.as_bytes())], &mut scan[..]).unwrap_or(0);
    AdvData {
        app: (app, app_len),
        hid: (hid, hid_len),
        scan: (scan, scan_len),
    }
}

#[embassy_executor::task]
async fn peripheral_task(
    mut peripheral: Peripheral<'static, BleController, DefaultPacketPool>,
    stack: &'static BleStack,
    server: &'static Server<'static>,
    name: &'static str,
) {
    let data = adv_data(name);
    loop {
        apply_forget(stack);
        let mode = match select(wait_adv_wanted(), forget_requested()).await {
            Either::First(m) => m,
            Either::Second(()) => continue,
        };
        let interval = match mode {
            AdvMode::Fast => Duration::from_millis(ADV_FAST_INTERVAL_MS),
            AdvMode::Slow => Duration::from_millis(ADV_SLOW_INTERVAL_MS),
            AdvMode::HidFast => Duration::from_micros(HID_ADV_FAST_INTERVAL_US),
            AdvMode::HidSlow | AdvMode::Off => Duration::from_micros(HID_ADV_SLOW_INTERVAL_US),
        };
        let params = AdvertisementParameters {
            interval_min: interval,
            interval_max: interval,
            ..Default::default()
        };
        let (adv, adv_len) = if mode.is_hid() { &data.hid } else { &data.app };
        let advertisement = Advertisement::ConnectableScannableUndirected {
            adv_data: &adv[..*adv_len],
            scan_data: &data.scan.0[..data.scan.1],
        };
        let advertiser = match peripheral.advertise(&params, advertisement).await {
            Ok(a) => a,
            Err(e) => {
                warn!("[ble] advertising failed: {:?}", e);
                Timer::after(Duration::from_secs(1)).await;
                continue;
            }
        };
        info!(
            "[ble] advertising {} every {} us",
            if mode.is_hid() { "as keyboard" } else { "for the app" },
            interval.as_micros()
        );
        // Dropping the advertiser (window closed or interval change) stops advertising.
        match select3(advertiser.accept(), adv_mode_changed(mode), forget_requested()).await {
            Either3::First(Ok(conn)) => {
                let presenter = with_controller(|c| c.presenter_active()).unwrap_or(false);
                // Bonding only in presenter mode (default: not bondable).
                if let Err(e) = conn.set_bondable(presenter) {
                    warn!("[ble] set_bondable: {:?}", e);
                }
                let bonded = bond_of(&conn);
                match conn.with_attribute_server(server) {
                    Ok(conn) => {
                        info!(
                            "[ble] connected ({} mode{})",
                            if presenter { "presenter" } else { "flashlight" },
                            if bonded.is_some() { ", paired computer" } else { "" }
                        );
                        refresh_all(server);
                        connection(stack, server, &conn, presenter, bonded).await;
                        info!("[ble] disconnected");
                    }
                    Err(e) => warn!("[ble] GATT setup failed: {:?}", e),
                }
            }
            Either3::First(Err(e)) => warn!("[ble] accept failed: {:?}", e),
            Either3::Second(()) | Either3::Third(()) => {}
        }
    }
}

async fn forget_requested() {
    loop {
        Timer::after(Duration::from_millis(100)).await;
        if with_bonds(|b| b.forget_stack) {
            return;
        }
    }
}

/// State of one link, shared by the event handler and the notifier.
struct Link {
    /// Mode when the link was set up (a mode change drops the link).
    presenter: bool,
    since: u64,
    /// Identity address of the bond of this computer (known at connect, or after pairing).
    bond_addr: Cell<Option<[u8; 6]>>,
    encrypted: Cell<bool>,
    /// `ble_connected(true)` was reported to the controller.
    reported: Cell<bool>,
    /// The FlashKa Control service was used on this link.
    control_used: Cell<bool>,
    security_requested: Cell<bool>,
    disconnecting: Cell<bool>,
}

/// Serve one connection until it is closed.
async fn connection(
    stack: &'static BleStack,
    server: &Server<'_>,
    conn: &GattConnection<'_, '_, DefaultPacketPool>,
    presenter: bool,
    bonded: Option<BondRecord>,
) {
    let now = now_ms();
    let link = Link {
        presenter,
        since: now,
        bond_addr: Cell::new(bonded.map(|b| b.addr)),
        encrypted: Cell::new(false),
        reported: Cell::new(false),
        control_used: Cell::new(false),
        security_requested: Cell::new(false),
        disconnecting: Cell::new(false),
    };
    // A paired computer that reconnects in flashlight mode is most likely its
    // HID auto-reconnect, not the app: it is not reported to the controller
    // (it must not hold the radio window open) until it uses the FlashKa
    // Control service. Every other link is reported at once.
    if presenter || bonded.is_none() {
        with_controller(|c| c.ble_connected(true, now));
        link.reported.set(true);
    }
    let events = async {
        loop {
            match conn.next().await {
                GattConnectionEvent::Disconnected { reason } => {
                    info!("[ble] disconnect reason {:?}", reason);
                    break;
                }
                GattConnectionEvent::Gatt { event } => gatt_event(server, conn, &link, event).await,
                GattConnectionEvent::RequestConnectionParams(req) => {
                    if let Err(e) = req.accept(None, stack).await {
                        warn!("[ble] connection parameter update failed: {:?}", e);
                    }
                }
                GattConnectionEvent::PairingComplete { security_level, bond } => {
                    info!("[smp] pairing complete: {:?}, bonded {}", security_level, bond.is_some());
                    if let Some(bi) = bond {
                        let mut rec = record_of(&bi);
                        // keep the subscriptions made so far on this link
                        if let Some(t) = server.get_cccd_table(conn.raw()) {
                            for (dst, (h, v)) in rec.cccd.iter_mut().zip(t.inner().iter()) {
                                *dst = (*h, v.raw());
                            }
                        }
                        let evicted = with_bonds(|b| {
                            let e = b.table.insert(rec);
                            b.dirty = true;
                            e
                        });
                        if let Some(old) = evicted {
                            info!("[bonds] oldest paired computer replaced");
                            if let Err(e) = stack.remove_bond_information(identity_of(&old)) {
                                warn!("[bonds] remove from stack: {:?}", e);
                            }
                        }
                        link.bond_addr.set(Some(rec.addr));
                    }
                    if security_level != SecurityLevel::NoEncryption {
                        link_encrypted(server, conn, &link, false);
                    }
                }
                GattConnectionEvent::PairingFailed(e) => warn!("[smp] pairing failed: {:?}", e),
                GattConnectionEvent::PassKeyConfirm(_) => {
                    // not expected with "no input, no output"; refuse
                    let _ = conn.pass_key_cancel();
                }
                _ => {}
            }
        }
    };
    select(events, notifier(stack, server, conn, &link)).await;
    if link.reported.get() {
        with_controller(|c| c.ble_connected(false, now_ms()));
    }
    if link.presenter {
        with_controller(|c| c.hid_connected(false, now_ms()));
    }
}

/// The link became encrypted (pairing, or a paired computer re-encrypting
/// with its stored key). `restore`: put back the computer's stored
/// subscriptions (CCCDs must persist across connections for bonded clients).
fn link_encrypted(server: &Server<'_>, conn: &GattConnection<'_, '_, DefaultPacketPool>, link: &Link, restore: bool) {
    if link.encrypted.replace(true) {
        return;
    }
    if restore
        && let Some(addr) = link.bond_addr.get()
        && let Some(rec) = with_bonds(|b| b.table.find(&addr).copied())
        && let Some(t) = server.get_cccd_table(conn.raw())
    {
        let mut entries = t.inner().clone();
        for (h, v) in entries.iter_mut() {
            if let Some((_, stored)) = rec.cccd.iter().find(|(sh, _)| *sh != 0 && *sh == *h) {
                *v = CCCD::from(*stored);
            }
        }
        server.set_cccd_table(conn.raw(), CccdTable::new(entries));
        info!("[bonds] subscriptions restored");
    }
    if link.presenter {
        with_controller(|c| c.hid_connected(true, now_ms()));
        info!("[ble] computer connected (encrypted)");
    }
}

/// After a write from a paired computer: store its subscriptions if they changed.
fn save_cccd(server: &Server<'_>, conn: &GattConnection<'_, '_, DefaultPacketPool>, link: &Link) {
    let Some(addr) = link.bond_addr.get() else { return };
    if !link.encrypted.get() {
        return;
    }
    let Some(t) = server.get_cccd_table(conn.raw()) else { return };
    let mut pairs = [(0u16, 0u16); CCCD_SLOTS];
    for (dst, (h, v)) in pairs.iter_mut().zip(t.inner().iter()) {
        *dst = (*h, v.raw());
    }
    let n = t.inner().len().min(CCCD_SLOTS);
    with_bonds(|b| {
        if b.table.set_cccd(&addr, &pairs[..n]) {
            b.dirty = true;
        }
    });
}

/// Answer one ATT request. Reads refresh the value first; writes go through
/// the controller, whose error becomes the ATT application error code.
async fn gatt_event(
    server: &Server<'_>,
    conn: &GattConnection<'_, '_, DefaultPacketPool>,
    link: &Link,
    event: GattEvent<'_, '_, DefaultPacketPool>,
) {
    let now = now_ms();
    let mut wrote = false;
    let reply = match event {
        GattEvent::Read(ev) => {
            let h = ev.handle();
            if is_control_handle(server, h) {
                control_used(link, now);
            }
            if h == server.control.status.handle {
                refresh_status(server);
            } else if h == server.control.profile.handle {
                refresh_profile(server);
            } else if h == server.control.presenter.handle {
                refresh_presenter(server);
            } else if h == server.battery.level.handle {
                refresh_battery(server);
            }
            ev.accept()
        }
        GattEvent::Write(ev) => {
            let h = ev.handle();
            if is_control_handle(server, h) {
                control_used(link, now);
            }
            if h == server.control.command.handle {
                let res = if ev.data().is_empty() || ev.data().len() > COMMAND_MAX_LEN {
                    Err(CmdError::Invalid)
                } else {
                    with_controller(|c| c.command(ev.data(), now)).unwrap_or(Err(CmdError::Invalid))
                };
                match res {
                    Ok(()) => ev.accept(),
                    Err(e) => {
                        info!("[ble] command {:02x?} refused: {:#04x}", ev.data(), e.code());
                        ev.reject(AttErrorCode::new(e.code()))
                    }
                }
            } else if h == server.control.profile.handle {
                let res = with_controller(|c| c.profile_write(ev.data(), now)).unwrap_or(Err(CmdError::Invalid));
                match res {
                    Ok(()) => {
                        let reply = ev.accept();
                        // store what is really used (clamped) for the next read
                        refresh_profile(server);
                        reply
                    }
                    Err(e) => ev.reject(AttErrorCode::new(e.code())),
                }
            } else if h == server.control.presenter.handle {
                let res = with_controller(|c| c.presenter_write(ev.data(), now)).unwrap_or(Err(CmdError::Invalid));
                match res {
                    Ok(()) => {
                        let reply = ev.accept();
                        refresh_presenter(server);
                        reply
                    }
                    Err(e) => ev.reject(AttErrorCode::new(e.code())),
                }
            } else {
                // CCCD writes, HID Control Point, Protocol Mode: the attribute server stores them
                wrote = true;
                ev.accept()
            }
        }
        GattEvent::NotAllowed(ev) => {
            // Apple: pairing starts when a request is rejected with
            // Insufficient Authentication (trouble-host answers Insufficient
            // Encryption by default).
            let unencrypted = !link.encrypted.get()
                && conn.raw().security_level().unwrap_or(SecurityLevel::NoEncryption) == SecurityLevel::NoEncryption;
            match ev.payload().handle() {
                Some(h) if unencrypted && needs_pairing(server, h) => {
                    ev.reject(AttErrorCode::INSUFFICIENT_AUTHENTICATION)
                }
                _ => ev.accept(),
            }
        }
        other => other.accept(),
    };
    match reply {
        Ok(r) => r.send().await,
        Err(e) => warn!("[ble] reply failed: {:?}", e),
    }
    if wrote {
        save_cccd(server, conn, link);
    }
}

/// The app uses this link: report it to the controller (window stays open).
fn control_used(link: &Link, now: u64) {
    if !link.control_used.replace(true) && !link.reported.get() {
        with_controller(|c| c.ble_connected(true, now));
        link.reported.set(true);
    }
}

/// Periodic work on a link: key reports, Status / Battery notifications,
/// encryption tracking, timeouts, mode changes and forget requests.
async fn notifier(
    stack: &'static BleStack,
    server: &Server<'_>,
    conn: &GattConnection<'_, '_, DefaultPacketPool>,
    link: &Link,
) {
    let mut last_key = None;
    let mut last_sent = 0u64;
    let mut last_battery: Option<u8> = None;
    let mut mode_changed_at: Option<u64> = None;
    loop {
        Timer::after(Duration::from_millis(20)).await;
        let now = now_ms();
        let age = now.saturating_sub(link.since);

        // encryption without a PairingComplete event = a paired computer reconnected
        if !link.encrypted.get()
            && conn.raw().security_level().unwrap_or(SecurityLevel::NoEncryption) != SecurityLevel::NoEncryption
        {
            if link.bond_addr.get().is_none() {
                link.bond_addr.set(bond_of(conn.raw()).map(|b| b.addr));
            }
            link_encrypted(server, conn, link, true);
        }

        let presenter_now = with_controller(|c| c.presenter_active()).unwrap_or(false);
        let mut drop_reason = None;
        if presenter_now != link.presenter {
            let at = *mode_changed_at.get_or_insert(now);
            if now - at >= MODE_CHANGE_DISCONNECT_MS {
                drop_reason = Some("mode changed");
            }
        } else if link.presenter && !link.encrypted.get() {
            if age >= PRESENTER_UNENCRYPTED_TIMEOUT_MS {
                drop_reason = Some("not paired in time");
            } else if age >= PRESENTER_SECURITY_REQUEST_MS && !link.security_requested.replace(true) {
                // the computer did not start pairing / encryption itself
                if let Err(e) = conn.raw().request_security() {
                    warn!("[smp] security request: {:?}", e);
                }
            }
        } else if !link.presenter && !link.reported.get() && age >= HOST_IN_FLASHLIGHT_MODE_MS {
            drop_reason = Some("paired computer in flashlight mode");
        }
        if apply_forget(stack) && link.bond_addr.get().is_some() {
            drop_reason = Some("paired computers forgotten");
        }
        if let Some(why) = drop_reason
            && !link.disconnecting.replace(true)
        {
            info!("[ble] disconnecting: {}", why);
            conn.raw().disconnect();
        }

        // keys: press, then release
        if link.presenter && link.encrypted.get() {
            while let Some(k) = with_controller(|c| c.take_key()).flatten() {
                if let Err(e) = server.hid.input_report.notify(conn, &key_report(k)).await {
                    warn!("[hid] key report failed: {:?}", e);
                }
                Timer::after(Duration::from_millis(KEY_RELEASE_GAP_MS)).await;
                if let Err(e) = server.hid.input_report.notify(conn, &KEY_RELEASE).await {
                    warn!("[hid] release report failed: {:?}", e);
                }
            }
        }

        let Some((status, battery)) = with_controller(|c| (c.status(now), c.battery_percent())) else {
            continue;
        };
        let key = status.change_key();
        let since = now.saturating_sub(last_sent);
        if since >= STATUS_NOTIFY_PERIOD_MS || (last_key != Some(key) && since >= STATUS_NOTIFY_MIN_GAP_MS) {
            if let Err(e) = server.control.status.notify(conn, &status.encode()).await {
                warn!("[ble] status notify failed: {:?}", e);
            }
            last_key = Some(key);
            last_sent = now;
        }
        if last_battery != Some(battery) {
            if let Err(e) = server.battery.level.notify(conn, &battery).await {
                warn!("[ble] battery notify failed: {:?}", e);
            }
            last_battery = Some(battery);
        }
    }
}
