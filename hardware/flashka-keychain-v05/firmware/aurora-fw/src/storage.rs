// SPDX-License-Identifier: MIT OR Apache-2.0
//! Settings storage in the on-chip SPI flash.
//!
//! The log format and the wear/power-fail logic live in
//! `aurora_core::settings`; this module only provides raw flash access to the
//! first 8 KiB of the `nvs` data partition (see `firmware/partitions.csv`).
//! Nothing else on this firmware uses that partition: ESP-IDF NVS is not used
//! by esp-radio's BLE controller.

use aurora_core::settings::{FlashIo, SECTOR_SIZE, STORE_SIZE};
use embedded_storage::nor_flash::{NorFlash, ReadNorFlash};
use esp_bootloader_esp_idf::partitions::{
    DataPartitionSubType, PARTITION_TABLE_MAX_LEN, PartitionType, read_partition_table,
};
use esp_storage::{FlashStorage, FlashStorageError};
use log::{info, warn};

/// Offset of the `nvs` partition in the default / shipped partition table,
/// used if the partition table cannot be read.
pub const DEFAULT_SETTINGS_OFFSET: u32 = 0x9000;

/// Flash region holding the settings log.
pub struct SettingsFlash {
    flash: FlashStorage<'static>,
    base: u32,
}

impl SettingsFlash {
    /// Find the settings region in the partition table (falls back to 0x9000).
    pub fn new(mut flash: FlashStorage<'static>) -> Self {
        let base = locate(&mut flash);
        info!("[flash] settings log at {:#x} ({} bytes)", base, STORE_SIZE);
        SettingsFlash { flash, base }
    }
}

fn locate(flash: &mut FlashStorage<'static>) -> u32 {
    let mut buf = [0u8; PARTITION_TABLE_MAX_LEN];
    match read_partition_table(flash, &mut buf) {
        Ok(table) => match table.find_partition(PartitionType::Data(DataPartitionSubType::Nvs)) {
            Ok(Some(p)) if p.len() >= STORE_SIZE && p.offset() % SECTOR_SIZE == 0 => p.offset(),
            Ok(Some(p)) => {
                warn!(
                    "[flash] nvs partition at {:#x} size {:#x} unusable, using default",
                    p.offset(),
                    p.len()
                );
                DEFAULT_SETTINGS_OFFSET
            }
            Ok(None) => {
                warn!("[flash] no nvs partition, using default offset");
                DEFAULT_SETTINGS_OFFSET
            }
            Err(e) => {
                warn!("[flash] partition table search failed: {:?}", e);
                DEFAULT_SETTINGS_OFFSET
            }
        },
        Err(e) => {
            warn!("[flash] cannot read partition table: {:?}", e);
            DEFAULT_SETTINGS_OFFSET
        }
    }
}

impl FlashIo for SettingsFlash {
    type Error = FlashStorageError;

    fn read(&mut self, offset: u32, buf: &mut [u8]) -> Result<(), Self::Error> {
        if offset as usize + buf.len() > STORE_SIZE as usize {
            return Err(FlashStorageError::OutOfBounds);
        }
        ReadNorFlash::read(&mut self.flash, self.base + offset, buf)
    }

    fn write(&mut self, offset: u32, data: &[u8]) -> Result<(), Self::Error> {
        if offset as usize + data.len() > STORE_SIZE as usize {
            return Err(FlashStorageError::OutOfBounds);
        }
        NorFlash::write(&mut self.flash, self.base + offset, data)
    }

    fn erase_sector(&mut self, offset: u32) -> Result<(), Self::Error> {
        if offset % SECTOR_SIZE != 0 || offset + SECTOR_SIZE > STORE_SIZE {
            return Err(FlashStorageError::OutOfBounds);
        }
        NorFlash::erase(&mut self.flash, self.base + offset, self.base + offset + SECTOR_SIZE)
    }
}
