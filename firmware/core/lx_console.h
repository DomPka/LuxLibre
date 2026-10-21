// SPDX-License-Identifier: GPL-3.0-or-later
// LuxLibre firmware - text console (boards with LX_HAS_CONSOLE: USB serial, UART, BLE UART).
//
// One command per line, answers end with "ok" or "err <reason>":
//   help                 list the commands
//   ver                  firmware version and board name
//   status               state, level, temperature, battery, caps
//   list                 all parameters: NAME=value
//   get NAME             one parameter
//   set NAME VALUE       change a parameter (RAM; "save" stores it)
//   save                 store all parameters
//   defaults             all parameters back to their defaults (RAM; "save" stores)
//   level N | off        switch the main LED (the button always has priority; never the laser)
//   reboot
#pragma once

#include "lx_common.h"

namespace lx {
namespace console {

void reset();         // forget partial input and activity (called by light::init)
void poll();          // read available characters, execute complete lines
bool active();        // a command arrived recently (keeps the MCU awake)

// Helpers shared with the simulator.
void execute(const char* line);

}  // namespace console
}  // namespace lx
