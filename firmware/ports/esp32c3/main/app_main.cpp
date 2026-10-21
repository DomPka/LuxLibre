// SPDX-License-Identifier: GPL-3.0-or-later
#include "../../../core/lx_light.h"
#include "../../../hal/lx_hal.h"

extern "C" void app_main(void) {
    lx::light::init();
    for (;;) {
        hal::wait_tick();
        lx::light::tick();
    }
}
