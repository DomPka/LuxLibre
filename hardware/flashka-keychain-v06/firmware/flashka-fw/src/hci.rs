// SPDX-License-Identifier: MIT OR Apache-2.0
//! HCI transport wrapper around esp-radio's `BleConnector` that guards
//! against the trouble-host 0.6.0 OOB pairing panic.
//!
//! trouble-host's peripheral pairing code calls `todo!("OOB not implemented")`
//! when a central sends an SMP Pairing Request with the "OOB data present"
//! flag. Every packet from the controller passes through [`GuardedConnector`]
//! before the host sees it; such a request has its Secure Connections bit
//! cleared (`flashka_core::hid::smp_reject_oob`, host-tested), which makes
//! trouble-host refuse it at once with Pairing Failed instead of panicking.
//! (A panic would only reset the light - the panic handler switches LED and
//! laser off first - but a pairing attempt should never reset it.)

use bt_hci::data::AclPacketBoundary;
use bt_hci::transport::Transport;
use bt_hci::{ControllerToHostPacket, FromHciBytes, HostToControllerPacket};
use esp_radio::ble::controller::{BleConnector, BleConnectorError};
use log::warn;

/// `BleConnector` with the OOB pairing guard on the receive path.
pub struct GuardedConnector {
    inner: BleConnector<'static>,
}

impl GuardedConnector {
    pub fn new(inner: BleConnector<'static>) -> Self {
        GuardedConnector { inner }
    }
}

impl embedded_io::ErrorType for GuardedConnector {
    type Error = BleConnectorError;
}

impl Transport for GuardedConnector {
    async fn read<'a>(&self, rx: &'a mut [u8]) -> Result<ControllerToHostPacket<'a>, Self::Error> {
        let base = rx.as_ptr() as usize;
        // First pass with a short borrow: where does the packet end, and where
        // is the L2CAP frame of a first ACL fragment?
        let (end, acl) = {
            let pkt = <BleConnector<'static> as Transport>::read(&self.inner, &mut *rx).await?;
            let (data, acl_first): (&[u8], bool) = match &pkt {
                ControllerToHostPacket::Acl(a) => (a.data(), !matches!(a.boundary_flag(), AclPacketBoundary::Continuing)),
                ControllerToHostPacket::Event(e) => (e.data, false),
                ControllerToHostPacket::Sync(s) => (s.data(), false),
                ControllerToHostPacket::Iso(i) => (i.data(), false),
            };
            let start = data.as_ptr() as usize - base;
            (start + data.len(), acl_first.then_some((start, data.len())))
        };
        if let Some((start, len)) = acl
            && flashka_core::hid::smp_reject_oob(&mut rx[start..start + len])
        {
            warn!("[smp] pairing request with OOB data: refused (not supported)");
        }
        // Second pass: hand the (possibly changed) packet to the host.
        let rx: &'a [u8] = rx;
        Ok(ControllerToHostPacket::from_hci_bytes_complete(&rx[..end])?)
    }

    async fn write<T: HostToControllerPacket>(&self, val: &T) -> Result<(), Self::Error> {
        <BleConnector<'static> as Transport>::write(&self.inner, val).await
    }
}
