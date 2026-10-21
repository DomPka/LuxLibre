#!/usr/bin/env bash
# SPDX-License-Identifier: MIT OR Apache-2.0
# Build the FlashKa Keychain v0.6 firmware and the merged flash image for address 0x0.
#
#   firmware/build.sh            host tests + release build + merged image
#   SKIP_TESTS=1 firmware/build.sh
#
# Output (firmware/dist/):
#   flashka-fw-v<version>-merged.bin   bootloader + partition table + app, write at 0x0
#   flashka-fw-v<version>.elf          the release ELF (for espflash / debugging)
#
# Toolchains (override with environment variables):
#   FW_RUST_BIN   directory with the rustc/cargo used for the riscv32imc build
#                 (default /usr/lib/rust-1.91/bin; build-std needs RUSTC_BOOTSTRAP=1
#                 on a stable compiler, set below)
#   HOST_CARGO    cargo for the host tests of flashka-core (default: cargo on PATH)
#   ESPFLASH      espflash 4.x binary (default: espflash on PATH; installed with
#                 `cargo install espflash --locked` if missing)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE="$HERE/flashka-core"
FW="$HERE/flashka-fw"
DIST="$HERE/dist"
VERSION="$(sed -n 's/^version = "\(.*\)"/\1/p' "$FW/Cargo.toml" | head -n1)"
ELF="$HERE/target/riscv32imc-unknown-none-elf/release/flashka-fw"   # the workspace target folder
MERGED="$DIST/flashka-fw-v$VERSION-merged.bin"

FW_RUST_BIN="${FW_RUST_BIN:-/usr/lib/rust-1.91/bin}"
HOST_CARGO="${HOST_CARGO:-cargo}"
ESPFLASH="${ESPFLASH:-espflash}"
# no network access needed for building
export ESPFLASH_SKIP_UPDATE_CHECK=true
# Reproducible image: the app descriptor's build date/time comes from
# SOURCE_DATE_EPOCH instead of the clock. esp-bootloader-esp-idf 0.5.0 reads
# this value in MICROseconds; the default is 2026-10-17 00:00:00 UTC. It is
# compiled in when that crate is first built, so build from a clean
# firmware/target to get the published image byte for byte.
export SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-1792195200000000}"
# rust-lld links the firmware: a rustup toolchain finds its own, a distribution rustc
# (FW_RUST_BIN) may not ship one - then use the first rust-lld found
if [[ -z "${CARGO_TARGET_RISCV32IMC_UNKNOWN_NONE_ELF_LINKER:-}" ]]; then
    for c in "$FW_RUST_BIN"/../lib/rustlib/*/bin/rust-lld "$HOME"/.rustup/toolchains/*/lib/rustlib/*/bin/rust-lld; do
        if [[ -x "$c" ]]; then
            export CARGO_TARGET_RISCV32IMC_UNKNOWN_NONE_ELF_LINKER="$c"
            break
        fi
    done
fi

# Location-independent image: panic messages and debug information name source
# files by their path. Map the machine-specific prefixes (this folder, the cargo
# registry and git checkouts, the Rust sysroot) to fixed names, so the image does
# not depend on where the repository, cargo or the toolchain is installed.
CARGO_HOME_DIR="${CARGO_HOME:-$HOME/.cargo}"
remap_rustflags() {   # $1 = the rustc that builds the firmware
    local sysroot
    sysroot="$("$1" --print sysroot)"
    printf '["--remap-path-prefix=%s=firmware", "--remap-path-prefix=%s/registry/src=/cargo/registry/src", "--remap-path-prefix=%s/git/checkouts=/cargo/git/checkouts", "--remap-path-prefix=%s=/rust"]' \
        "$HERE" "$CARGO_HOME_DIR" "$CARGO_HOME_DIR" "$sysroot"
}

step() { printf '\n==> %s\n' "$*"; }

# 1. Logic tests on the host (flashka-core has no target config of its own,
#    so it builds for the host).
if [[ "${SKIP_TESTS:-0}" != "1" ]]; then
    step "flashka-core: cargo test (host)"
    (cd "$CORE" && "$HOST_CARGO" test --quiet)
fi

# 2. Firmware release build (target, linker and build-std come from
#    flashka-fw/.cargo/config.toml).
step "flashka-fw: cargo build --release (riscv32imc-unknown-none-elf)"
# The remap flags are added to the target rustflags of .cargo/config.toml
# (cargo joins arrays given with --config to the ones from the file).
if [[ -x "$FW_RUST_BIN/cargo" ]]; then
    (cd "$FW" && RUSTC="$FW_RUST_BIN/rustc" RUSTC_BOOTSTRAP=1 PATH="$FW_RUST_BIN:$PATH" \
        "$FW_RUST_BIN/cargo" build --release \
        --config "target.riscv32imc-unknown-none-elf.rustflags=$(remap_rustflags "$FW_RUST_BIN/rustc")")
else
    (cd "$FW" && RUSTC_BOOTSTRAP=1 cargo build --release \
        --config "target.riscv32imc-unknown-none-elf.rustflags=$(remap_rustflags rustc)")
fi

# 3. Merged image.
if ! command -v "$ESPFLASH" >/dev/null 2>&1; then
    step "installing espflash 4.x (host toolchain)"
    "$HOST_CARGO" install espflash --locked --version '^4'
    ESPFLASH=espflash
fi
step "espflash $("$ESPFLASH" --version | awk '{print $2}'): merged image"
mkdir -p "$DIST"
"$ESPFLASH" save-image \
    --chip esp32c3 \
    --merge \
    --skip-padding \
    --flash-size 4mb \
    --partition-table "$HERE/partitions.csv" \
    "$ELF" "$MERGED"
cp "$ELF" "$DIST/flashka-fw-v$VERSION.elf"

step "sizes"
size_of() { stat -c '%s' "$1"; }
printf '%-40s %10s bytes\n' "$(basename "$DIST/flashka-fw-v$VERSION.elf")" "$(size_of "$DIST/flashka-fw-v$VERSION.elf")"
printf '%-40s %10s bytes\n' "$(basename "$MERGED")" "$(size_of "$MERGED")"
app_bytes=$(( $(size_of "$MERGED") - 0x10000 ))
printf '%-40s %10s bytes (%d %% of the 0x3F0000 app partition)\n' "app image (from 0x10000)" \
    "$app_bytes" $(( app_bytes * 100 / 0x3F0000 ))
if command -v llvm-size >/dev/null 2>&1; then
    # ESP32-C3: 400 KiB SRAM shared by IRAM code (.trap/.rwtext*), data, bss
    # (incl. the 36 KiB heap) and the stack (the rest); the 64 KiB
    # reclaimed bootloader RAM (.dram2_uninit) is the second heap region.
    llvm-size -A "$ELF" | awk '
        $1 ~ /^\.(trap|rwtext|rwtext\.wifi)$/ { iram += $2 }
        $1 ~ /^\.(data|data\.wifi)$/ { data += $2 }
        $1 == ".bss" { bss += $2 }
        $1 == ".stack" { stack += $2 }
        $1 ~ /^\.(text|rodata|flash\.appdesc)$/ { flash += $2 }
        END {
            printf "%-40s %10d bytes\n", "flash: .text + .rodata + appdesc", flash
            printf "%-40s %10d bytes (IRAM code %d, data %d, bss %d)\n", "RAM, static", iram + data + bss, iram, data, bss
            printf "%-40s %10d bytes\n", "RAM, left for the stack", stack
        }'
fi
if command -v sha256sum >/dev/null 2>&1; then
    (cd "$DIST" && sha256sum "$(basename "$MERGED")")
fi
printf '\nFlash with a web flasher (or esptool/espflash) at offset 0x0.\n'
