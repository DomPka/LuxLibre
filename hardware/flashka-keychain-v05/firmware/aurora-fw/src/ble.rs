// SPDX-License-Identifier: MIT OR Apache-2.0
//! Bluetooth LE peripheral (`docs/ble_protocol.md`): GAP name and
//! advertising windows, Battery Service and the Aurora Control Service.
//!
//! All decisions are made by `aurora_core::Controller`; this module moves
//! bytes between the GATT attributes and the controller.

use core::sync::atomic::{AtomicU8, Ordering};
use core::fmt::Write as _;

use aurora_core::config::{
    ADV_FAST_INTERVAL_MS, ADV_SLOW_INTERVAL_MS, STATUS_NOTIFY_MIN_GAP_MS, STATUS_NOTIFY_PERIOD_MS,
};
use aurora_core::controller::AdvMode;
use aurora_core::protocol::{
    CmdError, COMMAND_MAX_LEN, INFO_TEXT, PROFILE_LEN, SERVICE_UUID_LE, STATUS_LEN,
};
use bt_hci::controller::ExternalController;
use embassy_executor::Spawner;
use embassy_futures::select::{Either, select};
use embassy_time::{Duration, Timer};
use esp_hal::efuse::{InterfaceMacAddress, interface_mac_address};
use esp_hal::peripherals::BT;
use esp_radio::ble::controller::BleConnector;
use log::{error, info, warn};
use static_cell::StaticCell;
use trouble_host::prelude::*;

use crate::{now_ms, with_controller};

/// One central at a time.
pub const CONNECTIONS_MAX: usize = 1;
/// L2CAP channels: signalling + ATT.
pub const L2CAP_CHANNELS_MAX: usize = 2;

pub type BleController = ExternalController<BleConnector<'static>, 20>;
pub type BleStack = Stack<'static, BleController, DefaultPacketPool>;
type Resources = HostResources<DefaultPacketPool, CONNECTIONS_MAX, L2CAP_CHANNELS_MAX>;

/// GATT database: GAP + GATT services (added by `new_with_config`), Battery
/// Service and Aurora Control Service.
#[gatt_server]
pub struct Server {
    pub battery: BatteryService,
    pub aurora: AuroraService,
}

/// Standard Battery Service (0x180F).
#[gatt_service(uuid = service::BATTERY)]
pub struct BatteryService {
    /// State of charge, 0-100 %.
    #[characteristic(uuid = characteristic::BATTERY_LEVEL, read, notify)]
    pub level: u8,
}

/// Aurora Control Service. The UUID literals are those of
/// `aurora_core::protocol::*_UUID_STR` (the macro needs literals).
#[gatt_service(uuid = "a7d40001-3c5e-4b8a-9f61-2d0c8e5b7a13")]
pub struct AuroraService {
    /// Status, 18 bytes, read / notify.
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
}

// ------------------------------------------------------------------ adv mode

static ADV_MODE: AtomicU8 = AtomicU8::new(0);

/// Called by the control loop with the controller's advertising request.
pub fn set_adv_mode(mode: AdvMode) {
    let v = match mode {
        AdvMode::Off => 0,
        AdvMode::Fast => 1,
        AdvMode::Slow => 2,
    };
    ADV_MODE.store(v, Ordering::Relaxed);
}

fn adv_mode() -> AdvMode {
    match ADV_MODE.load(Ordering::Relaxed) {
        1 => AdvMode::Fast,
        2 => AdvMode::Slow,
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

// ------------------------------------------------------------------ start

static RESOURCES: StaticCell<Resources> = StaticCell::new();
static STACK: StaticCell<BleStack> = StaticCell::new();
static SERVER: StaticCell<Server<'static>> = StaticCell::new();
static NAME: StaticCell<heapless::String<16>> = StaticCell::new();

/// `Aurora-XXXX`, XXXX = last two bytes of the BLE MAC (upper-case hex). The
/// controller's public address is the eFuse base MAC with the Bluetooth
/// offset - the same value esp-radio hands to the controller.
fn device_name() -> &'static str {
    let mac = interface_mac_address(InterfaceMacAddress::Bluetooth);
    let b = mac.as_bytes();
    let name = NAME.init(heapless::String::new());
    let _ = write!(name, "Aurora-{:02X}{:02X}", b[4], b[5]);
    info!("[ble] address {}, name {}", mac, name.as_str());
    name.as_str()
}

/// Bring up the controller and the host and spawn the BLE tasks. On error
/// the flashlight keeps working without Bluetooth.
pub fn start(spawner: &Spawner, bt: BT<'static>) -> Result<(), &'static str> {
    let config = esp_radio::ble::Config::default().with_max_connections(CONNECTIONS_MAX as u8);
    let connector = BleConnector::new(bt, config).map_err(|_| "BLE controller init failed")?;
    let controller: BleController = ExternalController::new(connector);
    let resources = RESOURCES.init(HostResources::new());
    let stack: &'static BleStack = STACK.init(trouble_host::new(controller, resources));
    let Host {
        peripheral, runner, ..
    } = stack.build();

    let name = device_name();
    let server = Server::new_with_config(GapConfig::Peripheral(PeripheralConfig {
        name,
        appearance: &appearance::light_source::GENERIC_LIGHT_SOURCE,
    }))?;
    let server: &'static Server<'static> = SERVER.init(server);
    refresh_all(server);

    spawner.spawn(host_task(runner).map_err(|_| "spawn host task")?);
    spawner.spawn(peripheral_task(peripheral, stack, server, name).map_err(|_| "spawn peripheral task")?);
    Ok(())
}

// ------------------------------------------------------------------ attribute values

fn refresh_status(server: &Server<'_>) {
    let now = now_ms();
    if let Some(s) = with_controller(|c| c.status(now).encode()) {
        let _ = server.set(&server.aurora.status, &s);
    }
}

fn refresh_profile(server: &Server<'_>) {
    if let Some(p) = with_controller(|c| c.profile_packet()) {
        let _ = server.set(&server.aurora.profile, &p);
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

#[embassy_executor::task]
async fn peripheral_task(
    mut peripheral: Peripheral<'static, BleController, DefaultPacketPool>,
    stack: &'static BleStack,
    server: &'static Server<'static>,
    name: &'static str,
) {
    // Advertising data: flags + the 128-bit Aurora service UUID (21 bytes).
    let mut adv_data = [0u8; 31];
    let adv_len = AdStructure::encode_slice(
        &[
            AdStructure::Flags(LE_GENERAL_DISCOVERABLE | BR_EDR_NOT_SUPPORTED),
            AdStructure::ServiceUuids128(&[SERVICE_UUID_LE]),
        ],
        &mut adv_data[..],
    )
    .unwrap_or(0);
    // Scan response: complete local name "Aurora-XXXX".
    let mut scan_data = [0u8; 31];
    let scan_len = AdStructure::encode_slice(&[AdStructure::CompleteLocalName(name.as_bytes())], &mut scan_data[..])
        .unwrap_or(0);

    loop {
        let mode = wait_adv_wanted().await;
        let interval = Duration::from_millis(if mode == AdvMode::Fast {
            ADV_FAST_INTERVAL_MS
        } else {
            ADV_SLOW_INTERVAL_MS
        });
        let params = AdvertisementParameters {
            interval_min: interval,
            interval_max: interval,
            ..Default::default()
        };
        let advertisement = Advertisement::ConnectableScannableUndirected {
            adv_data: &adv_data[..adv_len],
            scan_data: &scan_data[..scan_len],
        };
        let advertiser = match peripheral.advertise(&params, advertisement).await {
            Ok(a) => a,
            Err(e) => {
                warn!("[ble] advertising failed: {:?}", e);
                Timer::after(Duration::from_secs(1)).await;
                continue;
            }
        };
        info!("[ble] advertising every {} ms", interval.as_millis());
        // Dropping the advertiser (window closed or interval change) stops advertising.
        match select(advertiser.accept(), adv_mode_changed(mode)).await {
            Either::First(Ok(conn)) => match conn.with_attribute_server(server) {
                Ok(conn) => {
                    info!("[ble] connected");
                    with_controller(|c| c.ble_connected(true, now_ms()));
                    refresh_all(server);
                    connection(stack, server, &conn).await;
                    with_controller(|c| c.ble_connected(false, now_ms()));
                    info!("[ble] disconnected");
                }
                Err(e) => warn!("[ble] GATT setup failed: {:?}", e),
            },
            Either::First(Err(e)) => warn!("[ble] accept failed: {:?}", e),
            Either::Second(()) => {}
        }
    }
}

/// Serve one connection until it is closed.
async fn connection(stack: &BleStack, server: &Server<'_>, conn: &GattConnection<'_, '_, DefaultPacketPool>) {
    let events = async {
        loop {
            match conn.next().await {
                GattConnectionEvent::Disconnected { reason } => {
                    info!("[ble] disconnect reason {:?}", reason);
                    break;
                }
                GattConnectionEvent::Gatt { event } => gatt_event(server, event).await,
                GattConnectionEvent::RequestConnectionParams(req) => {
                    if let Err(e) = req.accept(None, stack).await {
                        warn!("[ble] connection parameter update failed: {:?}", e);
                    }
                }
                _ => {}
            }
        }
    };
    select(events, notifier(server, conn)).await;
}

/// Answer one ATT request. Reads refresh the value first; writes go through
/// the controller, whose error becomes the ATT application error code.
async fn gatt_event(server: &Server<'_>, event: GattEvent<'_, '_, DefaultPacketPool>) {
    let now = now_ms();
    let reply = match event {
        GattEvent::Read(ev) => {
            let h = ev.handle();
            if h == server.aurora.status.handle {
                refresh_status(server);
            } else if h == server.aurora.profile.handle {
                refresh_profile(server);
            } else if h == server.battery.level.handle {
                refresh_battery(server);
            }
            ev.accept()
        }
        GattEvent::Write(ev) => {
            let h = ev.handle();
            if h == server.aurora.command.handle {
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
            } else if h == server.aurora.profile.handle {
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
            } else {
                // CCCD writes and anything else: let the attribute server handle it
                ev.accept()
            }
        }
        other => other.accept(),
    };
    match reply {
        Ok(r) => r.send().await,
        Err(e) => warn!("[ble] reply failed: {:?}", e),
    }
}

/// Status notifications on every change (rate limited) and at least every
/// 2 s; Battery Level notifications when the percentage changes. A notify is a
/// no-op while the central is not subscribed.
async fn notifier(server: &Server<'_>, conn: &GattConnection<'_, '_, DefaultPacketPool>) {
    let mut last_key = None;
    let mut last_sent = 0u64;
    let mut last_battery: Option<u8> = None;
    loop {
        Timer::after(Duration::from_millis(50)).await;
        let now = now_ms();
        let Some((status, battery)) = with_controller(|c| (c.status(now), c.battery_percent())) else {
            continue;
        };
        let key = status.change_key();
        let since = now.saturating_sub(last_sent);
        if since >= STATUS_NOTIFY_PERIOD_MS || (last_key != Some(key) && since >= STATUS_NOTIFY_MIN_GAP_MS) {
            if let Err(e) = server.aurora.status.notify(conn, &status.encode()).await {
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
