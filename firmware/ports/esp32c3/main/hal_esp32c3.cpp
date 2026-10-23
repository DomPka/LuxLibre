// SPDX-License-Identifier: GPL-3.0-or-later
// LuxLibre firmware - HAL for the ESP32-C3 with ESP-IDF 5.x (boards: FlashKa Keychain v0.5, v0.6).
//
// Resources: LEDC 13-bit 9.77 kHz (LED current set point + 3 RGB channels, active low),
// ADC1 oneshot with curve-fitting calibration (VBAT / 2 on GPIO0, NTC on GPIO1), light sleep
// with GPIO wake-up (button) and timer wake-up, NVS blob for the settings, USB-Serial-JTAG
// for the text console, task watchdog 3 s.
//
// The button is one of two kinds (board.h):
//  * one digital button: LX_ESP_GPIO_BTN, low = pressed, internal pull-up on (v0.5);
//  * a resistor ladder, several buttons on one net, each at its own voltage (v0.6):
//    LX_ESP_BTN_LADDER_ADC_GPIO is read with ADC1 at 2.5 dB and its own calibration, and
//    "pressed" means below LX_ESP_BTN_MAIN_BELOW_MV (the main button; the others are ignored).
//    LX_ESP_BTN_WAKE_GPIO, a second pin on the same net, is a digital input (internal pull-up
//    off) that goes low for any button and wakes the chip from light sleep. Without a
//    calibrated reading the wake pin decides, and any button counts as the main button.
//
// Status: EXPERIMENTAL - written against the ESP-IDF 5.x API but not yet compiled with ESP-IDF
// or tested on the board; the GitHub workflow builds it with the espressif/idf container.
// The resistor-ladder path is untested on hardware as well. The original FlashKa Rust firmware
// (Bluetooth app, deep sleep) stays the reference until this port has been verified on hardware.
#include <string.h>

#include "driver/gpio.h"
#include "driver/ledc.h"
#include "driver/usb_serial_jtag.h"
#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"
#include "esp_adc/adc_oneshot.h"
#include "esp_idf_version.h"
#include "esp_sleep.h"
#include "esp_system.h"
#include "esp_task_wdt.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "nvs.h"
#include "nvs_flash.h"

#include "../../../core/lx_board.h"
#include "../../../core/lx_thermal.h"
#include "../../../hal/lx_hal.h"
#include "../../../hal/lx_ntc.h"

#if ESP_IDF_VERSION >= ESP_IDF_VERSION_VAL(5, 2, 0)
#define LX_ADC_ATTEN ADC_ATTEN_DB_12
#else
#define LX_ADC_ATTEN ADC_ATTEN_DB_11
#endif

#if defined(LX_ESP_BTN_LADDER_ADC_GPIO)
#define LX_ESP_LADDER 1
#if defined(LX_ESP_GPIO_BTN)
#error "board.h: define LX_ESP_GPIO_BTN (one button) or the LX_ESP_BTN_LADDER_ macros (resistor ladder), not both"
#endif
#if !defined(LX_ESP_BTN_WAKE_GPIO) || !defined(LX_ESP_BTN_MAIN_BELOW_MV)
#error "board.h: a resistor ladder also needs LX_ESP_BTN_WAKE_GPIO and LX_ESP_BTN_MAIN_BELOW_MV"
#endif
static_assert(LX_ESP_BTN_LADDER_ADC_GPIO >= 0 && LX_ESP_BTN_LADDER_ADC_GPIO <= 4,
              "on the ESP32-C3 only GPIO0-GPIO4 are ADC1 inputs (GPIOn = ADC1 channel n)");
static_assert(LX_ESP_BTN_WAKE_GPIO != LX_ESP_BTN_LADDER_ADC_GPIO,
              "the wake pin must be a second pin on the ladder net: an ADC pin has no digital input");
static_assert(LX_ESP_BTN_MAIN_BELOW_MV > 0 && LX_ESP_BTN_MAIN_BELOW_MV < 1050,
              "the main threshold must lie inside the 2.5 dB range (0 to 1050 mV)");
#else
#define LX_ESP_LADDER 0
#endif

namespace {

constexpr uint32_t PWM_FULL = 8191;                       // 13 bit
constexpr ledc_channel_t CH_LED = LEDC_CHANNEL_0;
constexpr ledc_channel_t CH_R = LEDC_CHANNEL_1;
constexpr ledc_channel_t CH_G = LEDC_CHANNEL_2;
constexpr ledc_channel_t CH_B = LEDC_CHANNEL_3;
constexpr lx::ntc::Table<LX_ESP_NTC_RFIX, LX_ESP_NTC_R25, LX_ESP_NTC_BETA> k_ntc{};

adc_oneshot_unit_handle_t g_adc = nullptr;
adc_cali_handle_t g_cali_vbat = nullptr;
adc_cali_handle_t g_cali_ntc = nullptr;
#if LX_ESP_LADDER
constexpr adc_channel_t CH_BTN = (adc_channel_t)LX_ESP_BTN_LADDER_ADC_GPIO;   // ADC1 channel n = GPIOn
constexpr gpio_num_t PIN_WAKE = (gpio_num_t)LX_ESP_BTN_WAKE_GPIO;
adc_cali_handle_t g_cali_btn = nullptr;
#endif
nvs_handle_t g_nvs = 0;
uint8_t g_store[LX_STORAGE_SIZE];
TickType_t g_last_wake = 0;
bool g_console = false;

// charger: CHG_SET low = charge (~300 mA; v0.7: ~500 mA), high = off, floating = 10 mA trickle.
// The FlashKa has no VBUS sense pin: while charging is off, CHG_SET is floated for one 100 ms
// period every 5 s so that the TP4057 status pins show whether USB is plugged in - but only while
// the core allows charging (cell temperature inside the window, design rule CHG-3).
bool g_usb = false;
uint8_t g_chg_status = hal::CHG_NONE;
uint16_t g_probe_ctr = 0;
bool g_probing = false;
bool g_chg_allowed = false;   // last "allowed" from the core, also used while asleep

void out_pin(int gpio, int level) {
    gpio_config_t c;
    memset(&c, 0, sizeof c);
    c.pin_bit_mask = 1ULL << gpio;
    c.mode = GPIO_MODE_OUTPUT;
    c.pull_up_en = GPIO_PULLUP_DISABLE;
    c.pull_down_en = GPIO_PULLDOWN_DISABLE;
    c.intr_type = GPIO_INTR_DISABLE;
    gpio_set_level((gpio_num_t)gpio, level);
    gpio_config(&c);
    gpio_set_level((gpio_num_t)gpio, level);
}

void in_pin(int gpio, bool pull_up) {
    gpio_config_t c;
    memset(&c, 0, sizeof c);
    c.pin_bit_mask = 1ULL << gpio;
    c.mode = GPIO_MODE_INPUT;
    c.pull_up_en = pull_up ? GPIO_PULLUP_ENABLE : GPIO_PULLUP_DISABLE;
    c.pull_down_en = GPIO_PULLDOWN_DISABLE;
    c.intr_type = GPIO_INTR_DISABLE;
    gpio_config(&c);
}

#if LX_ESP_LADDER
void analog_pin(int gpio) {   // no digital input or output, no pull-up or pull-down
    gpio_config_t c;
    memset(&c, 0, sizeof c);
    c.pin_bit_mask = 1ULL << gpio;
    c.mode = GPIO_MODE_DISABLE;
    c.pull_up_en = GPIO_PULLUP_DISABLE;
    c.pull_down_en = GPIO_PULLDOWN_DISABLE;
    c.intr_type = GPIO_INTR_DISABLE;
    gpio_config(&c);
}
#endif

void ledc_ch(ledc_channel_t ch, int gpio, bool invert) {
    ledc_channel_config_t c;
    memset(&c, 0, sizeof c);
    c.gpio_num = gpio;
    c.speed_mode = LEDC_LOW_SPEED_MODE;
    c.channel = ch;
    c.intr_type = LEDC_INTR_DISABLE;
    c.timer_sel = LEDC_TIMER_0;
    c.duty = 0;
    c.hpoint = 0;
    c.flags.output_invert = invert ? 1 : 0;
    ledc_channel_config(&c);
}

void ledc_duty(ledc_channel_t ch, uint32_t duty) {
    ledc_set_duty(LEDC_LOW_SPEED_MODE, ch, duty);
    ledc_update_duty(LEDC_LOW_SPEED_MODE, ch);
}

adc_cali_handle_t make_cali(adc_channel_t ch, adc_atten_t atten) {
    adc_cali_handle_t h = nullptr;
    adc_cali_curve_fitting_config_t c;
    memset(&c, 0, sizeof c);
    c.unit_id = ADC_UNIT_1;
    c.chan = ch;
    c.atten = atten;
    c.bitwidth = ADC_BITWIDTH_DEFAULT;
    if (adc_cali_create_scheme_curve_fitting(&c, &h) != ESP_OK) h = nullptr;
    return h;
}

int read_mv(adc_channel_t ch, adc_cali_handle_t cali) {
    int sum = 0, n = 0;
    for (int i = 0; i < 4; i++) {
        int raw = 0, mv = 0;
        if (adc_oneshot_read(g_adc, ch, &raw) != ESP_OK) continue;
        if (cali && adc_cali_raw_to_voltage(cali, raw, &mv) == ESP_OK) sum += mv;
        else sum += raw * 2500 / 4095;           // uncalibrated fallback (approximate)
        n++;
    }
    return n ? sum / n : -1;
}

#if LX_ESP_LADDER
// True while the main button is pressed: one calibrated reading of the ladder below the main
// threshold (a slightly negative result near 0 V also counts). Without a calibrated reading
// (conversion failed, or no calibration for 2.5 dB) only the wake pin is left, and any button
// counts as the main button: the single-button behaviour of v0.5, as in the FlashKa firmware.
bool ladder_main() {
    int raw = 0, mv = 0;
    if (g_adc && g_cali_btn && adc_oneshot_read(g_adc, CH_BTN, &raw) == ESP_OK &&
        adc_cali_raw_to_voltage(g_cali_btn, raw, &mv) == ESP_OK)
        return mv < LX_ESP_BTN_MAIN_BELOW_MV;
    return gpio_get_level(PIN_WAKE) == 0;
}
#endif

void chg_pin(int mode) {   // 0 = low (charge), 1 = high (off), 2 = float (probe / trickle)
    if (mode == 2) {
        in_pin(LX_ESP_GPIO_CHG_SET, false);
    } else {
        out_pin(LX_ESP_GPIO_CHG_SET, mode);
    }
}

}  // namespace

namespace hal {

void init() {
    // 1. light and laser off before anything else (they also have 100 k pull-downs)
    out_pin(LX_ESP_GPIO_LED_EN, 0);
#if LX_HAS_LASER
    out_pin(LX_ESP_GPIO_LASER, 0);
#endif
    // 2. inputs
#if LX_ESP_LADDER
    // Resistor ladder: its levels assume the board's pull-up alone, so neither pin may add the
    // chip's internal one. The wake pin (a strap pin, pulled up inside the chip at reset) becomes
    // a plain digital input; the ladder pin becomes analog (the ADC setup below does that too).
    in_pin(LX_ESP_BTN_WAKE_GPIO, false);
    analog_pin(LX_ESP_BTN_LADDER_ADC_GPIO);
#else
    in_pin(LX_ESP_GPIO_BTN, true);
#endif
    in_pin(LX_ESP_GPIO_CHG_STAT, true);
    in_pin(LX_ESP_GPIO_CHG_DONE, true);
    chg_pin(1);                                   // charger off until the core decides (first tick)
    // 3. LEDC: 13 bit at 9.77 kHz
    ledc_timer_config_t t;
    memset(&t, 0, sizeof t);
    t.speed_mode = LEDC_LOW_SPEED_MODE;
    t.duty_resolution = LEDC_TIMER_13_BIT;
    t.timer_num = LEDC_TIMER_0;
    t.freq_hz = 9765;
    t.clk_cfg = LEDC_AUTO_CLK;
    ledc_timer_config(&t);
    ledc_ch(CH_LED, LX_ESP_GPIO_LED_PWM, false);
    ledc_ch(CH_R, LX_ESP_GPIO_RGB_R, true);       // common anode: invert, duty = brightness
    ledc_ch(CH_G, LX_ESP_GPIO_RGB_G, true);
    ledc_ch(CH_B, LX_ESP_GPIO_RGB_B, true);
    // 4. ADC
    adc_oneshot_unit_init_cfg_t u;
    memset(&u, 0, sizeof u);
    u.unit_id = ADC_UNIT_1;
    adc_oneshot_new_unit(&u, &g_adc);
    adc_oneshot_chan_cfg_t cc;
    memset(&cc, 0, sizeof cc);
    cc.atten = LX_ADC_ATTEN;
    cc.bitwidth = ADC_BITWIDTH_DEFAULT;
    adc_oneshot_config_channel(g_adc, ADC_CHANNEL_0, &cc);
    adc_oneshot_config_channel(g_adc, ADC_CHANNEL_1, &cc);
    g_cali_vbat = make_cali(ADC_CHANNEL_0, LX_ADC_ATTEN);
    g_cali_ntc = make_cali(ADC_CHANNEL_1, LX_ADC_ATTEN);
#if LX_ESP_LADDER
    // the ladder at 2.5 dB (0 to 1050 mV): its low levels sit in the ADC's most accurate range
    // (the driver keeps a copy of the channel settings, so cc can be reused)
    cc.atten = ADC_ATTEN_DB_2_5;
    adc_oneshot_config_channel(g_adc, CH_BTN, &cc);
    g_cali_btn = make_cali(CH_BTN, ADC_ATTEN_DB_2_5);
#endif
    // 5. settings in NVS
    if (nvs_flash_init() != ESP_OK) {
        nvs_flash_erase();
        nvs_flash_init();
    }
    memset(g_store, 0xFF, sizeof g_store);
    if (nvs_open("luxlibre", NVS_READWRITE, &g_nvs) == ESP_OK) {
        size_t len = sizeof g_store;
        if (nvs_get_blob(g_nvs, "store", g_store, &len) != ESP_OK) memset(g_store, 0xFF, sizeof g_store);
    }
    // 6. console over USB-Serial-JTAG
    usb_serial_jtag_driver_config_t uc = USB_SERIAL_JTAG_DRIVER_CONFIG_DEFAULT();
    g_console = usb_serial_jtag_driver_install(&uc) == ESP_OK;
    // 7. watchdog (the task watchdog is started by ESP-IDF, see sdkconfig.defaults)
    esp_task_wdt_add(nullptr);
    g_last_wake = xTaskGetTickCount();
}

void watchdog_kick() { esp_task_wdt_reset(); }

void reboot() { esp_restart(); }

uint32_t millis() { return (uint32_t)(esp_timer_get_time() / 1000); }

void wait_tick() { vTaskDelayUntil(&g_last_wake, pdMS_TO_TICKS(LX_TICK_MS)); }

#if LX_ESP_LADDER
// Resistor ladder: any button pulls the wake pin low and wakes the chip; the ladder then shows
// whether it was the main button. Any other button is ignored and the port sleeps again. While
// such a button stays pressed it holds the wake pin low, so a low-level wake-up would fire again
// at once: the port then wakes when the pin goes high (released) and reads the ladder every
// LADDER_POLL_MS for the main button, which wins over the others. After LADDER_STUCK_MS (a slide
// button squeezed in a pocket) it reads only every LADDER_STUCK_POLL_MS (design rules BAT-6,
// BAT-7). LuxLibre port defaults; the last two equal the core's stuck-button time and check period.
constexpr uint32_t LADDER_POLL_MS = 50;
constexpr uint32_t LADDER_STUCK_MS = 10000;
constexpr uint32_t LADDER_STUCK_POLL_MS = 2000;

bool sleep(uint32_t max_ms, bool wake_on_button) {
    esp_sleep_disable_wakeup_source(ESP_SLEEP_WAKEUP_ALL);
    // USB plugged in while asleep: the charger status pins wake the chip, exactly as in the
    // single-button version below (same conditions, same hardware caveat).
    bool usb_wake = g_chg_allowed && !g_usb;
    if (usb_wake) {
        chg_pin(2);
        vTaskDelay(1);                            // let the pin settle (1 ms)
        usb_wake = gpio_get_level((gpio_num_t)LX_ESP_GPIO_CHG_STAT) == 1 &&
                   gpio_get_level((gpio_num_t)LX_ESP_GPIO_CHG_DONE) == 1;
        if (usb_wake) {
            gpio_wakeup_enable((gpio_num_t)LX_ESP_GPIO_CHG_STAT, GPIO_INTR_LOW_LEVEL);
            gpio_wakeup_enable((gpio_num_t)LX_ESP_GPIO_CHG_DONE, GPIO_INTR_LOW_LEVEL);
        } else {
            chg_pin(1);
        }
    }
    const uint32_t t0 = millis();
    bool other = false;                           // a button other than main holds the wake pin low
    uint32_t other_since = 0;                     // millis() when that press began
    bool by_button = false;
    bool by_usb = false;
    for (;;) {
        uint32_t now = millis();
        uint32_t timer_ms = 0;                    // 0 = no timer wake-up
        if (max_ms) {
            if (now - t0 >= max_ms) break;        // the caller's time is over
            timer_ms = max_ms - (now - t0);
        }
        esp_sleep_disable_wakeup_source(ESP_SLEEP_WAKEUP_ALL);
        if (wake_on_button) {
            gpio_wakeup_enable(PIN_WAKE, other ? GPIO_INTR_HIGH_LEVEL : GPIO_INTR_LOW_LEVEL);
            if (other) {
                uint32_t poll = (now - other_since >= LADDER_STUCK_MS) ? LADDER_STUCK_POLL_MS : LADDER_POLL_MS;
                if (timer_ms == 0 || timer_ms > poll) timer_ms = poll;
            }
        }
        if (wake_on_button || usb_wake) esp_sleep_enable_gpio_wakeup();
        if (timer_ms) esp_sleep_enable_timer_wakeup((uint64_t)timer_ms * 1000ULL);
        esp_task_wdt_reset();
        // RAM and registers are kept; millis() continues. ESP-IDF may reject the sleep, for example
        // when the wake-up level is already present (a button held before the first round).
        esp_err_t slept = esp_light_sleep_start();
        if (wake_on_button) gpio_wakeup_disable(PIN_WAKE);
        // USB power: with the charge-set pin floating, a powered charger pulls a status pin low
        by_usb = usb_wake && (gpio_get_level((gpio_num_t)LX_ESP_GPIO_CHG_STAT) == 0 ||
                              gpio_get_level((gpio_num_t)LX_ESP_GPIO_CHG_DONE) == 0);
        bool was_other = other;
        if (wake_on_button) {
            bool low = gpio_get_level(PIN_WAKE) == 0;
            if (low && !other) {                  // a new press: let the contacts settle first
                vTaskDelay(pdMS_TO_TICKS(LX_TICK_MS));
                low = gpio_get_level(PIN_WAKE) == 0;
            }
            by_button = low && ladder_main();
            if (low && !other) other_since = millis();
            other = low && !by_button;            // not the main button: ignored
        }
        if (by_button || by_usb) break;
        // A rejected sleep with nothing changed ends the call, as in the single-button version
        // (the core sleeps again later); if the button state changed, the next round arms the
        // other wake-up level and sleeps.
        if (slept != ESP_OK && other == was_other) break;
    }
    esp_sleep_disable_wakeup_source(ESP_SLEEP_WAKEUP_ALL);
    if (usb_wake) {
        gpio_wakeup_disable((gpio_num_t)LX_ESP_GPIO_CHG_STAT);
        gpio_wakeup_disable((gpio_num_t)LX_ESP_GPIO_CHG_DONE);
        if (by_usb) {
            g_probing = true;                     // the next set_charge() reads the status pins
        } else {
            chg_pin(1);
        }
    }
    g_last_wake = xTaskGetTickCount();
    return by_button;
}
#else
bool sleep(uint32_t max_ms, bool wake_on_button) {
    esp_sleep_disable_wakeup_source(ESP_SLEEP_WAKEUP_ALL);
    if (wake_on_button) gpio_wakeup_enable((gpio_num_t)LX_ESP_GPIO_BTN, GPIO_INTR_LOW_LEVEL);
    // USB plugged in while asleep: with CHG_SET floating, a powered TP4057 pulls its status
    // pins low, which wakes the chip so that the core can start charging. Only if charging is
    // allowed (temperature window) and the pins are idle now (no wake-up loop).
    // TO VERIFY ON HARDWARE: no leakage from the pull-ups into the unpowered charger.
    bool usb_wake = g_chg_allowed && !g_usb;
    if (usb_wake) {
        chg_pin(2);
        vTaskDelay(1);                            // let the pin settle (1 ms)
        usb_wake = gpio_get_level((gpio_num_t)LX_ESP_GPIO_CHG_STAT) == 1 &&
                   gpio_get_level((gpio_num_t)LX_ESP_GPIO_CHG_DONE) == 1;
        if (usb_wake) {
            gpio_wakeup_enable((gpio_num_t)LX_ESP_GPIO_CHG_STAT, GPIO_INTR_LOW_LEVEL);
            gpio_wakeup_enable((gpio_num_t)LX_ESP_GPIO_CHG_DONE, GPIO_INTR_LOW_LEVEL);
        } else {
            chg_pin(1);
        }
    }
    if (wake_on_button || usb_wake) esp_sleep_enable_gpio_wakeup();
    if (max_ms) esp_sleep_enable_timer_wakeup((uint64_t)max_ms * 1000ULL);
    esp_task_wdt_reset();
    esp_light_sleep_start();                      // RAM and registers are kept; millis() continues
    bool by_gpio = esp_sleep_get_wakeup_cause() == ESP_SLEEP_WAKEUP_GPIO;
    bool by_button = by_gpio && gpio_get_level((gpio_num_t)LX_ESP_GPIO_BTN) == 0;
    if (wake_on_button) gpio_wakeup_disable((gpio_num_t)LX_ESP_GPIO_BTN);
    if (usb_wake) {
        gpio_wakeup_disable((gpio_num_t)LX_ESP_GPIO_CHG_STAT);
        gpio_wakeup_disable((gpio_num_t)LX_ESP_GPIO_CHG_DONE);
        if (by_gpio && !by_button) {
            g_probing = true;                     // the next set_charge() reads the status pins
        } else {
            chg_pin(1);
        }
    }
    g_last_wake = xTaskGetTickCount();
    return by_button;
}
#endif

#if LX_ESP_LADDER
bool button_down() { return ladder_main(); }
#else
bool button_down() { return gpio_get_level((gpio_num_t)LX_ESP_GPIO_BTN) == 0; }
#endif

uint16_t battery_mv() {
    int mv = read_mv(ADC_CHANNEL_0, g_cali_vbat);
    return mv > 0 ? (uint16_t)(mv * LX_ESP_VBAT_DIV) : 0;
}

lx::temp_dc_t temperature() {
    int mv = read_mv(ADC_CHANNEL_1, g_cali_ntc);
    if (mv < 0) return lx::thermal::NO_SENSOR;
    return k_ntc.temp_dc((uint32_t)mv, 3300u);    // the divider runs from the 3.3 V rail
}

bool usb_present() { return g_usb; }
uint8_t charger_status() { return g_chg_status; }

void set_main(lx::power_t power) {
    uint32_t ma = (uint32_t)power * LX_MAIN_MAX_MA / 65535u;
    uint32_t duty = (ma * PWM_FULL + LX_ESP_LED_FULL_MA / 2) / LX_ESP_LED_FULL_MA;
    if (power && !duty) duty = 1;
    ledc_duty(CH_LED, power ? duty : 0);
    gpio_set_level((gpio_num_t)LX_ESP_GPIO_LED_EN, power ? 1 : 0);
}

void set_aux(uint8_t r, uint8_t g, uint8_t b) {
    ledc_duty(CH_R, (uint32_t)r * PWM_FULL / 255u);
    ledc_duty(CH_G, (uint32_t)g * PWM_FULL / 255u);
    ledc_duty(CH_B, (uint32_t)b * PWM_FULL / 255u);
}

#if LX_HAS_LASER
void set_laser(bool on) { gpio_set_level((gpio_num_t)LX_ESP_GPIO_LASER, on ? 1 : 0); }
#else
void set_laser(bool) {}   // boards without a laser (EDCO)
#endif

void set_charge(bool enable, bool allowed) {
    // called every 100 ms by the core
    g_chg_allowed = allowed;
    bool chrg = gpio_get_level((gpio_num_t)LX_ESP_GPIO_CHG_STAT) == 0;
    bool done = gpio_get_level((gpio_num_t)LX_ESP_GPIO_CHG_DONE) == 0;
    if (enable || g_probing) {
        g_usb = chrg || done;
        g_chg_status = done ? CHG_DONE : (chrg ? CHG_CHARGING : CHG_NONE);
    }
    if (enable) {
        g_probing = false;
        chg_pin(0);
        return;
    }
    if (!allowed) {
        // Outside the temperature window: no current into the cell at all, so no probing
        // either. USB presence cannot be known then and is reported as absent (the light may
        // sleep, and USB does not release the low-voltage latch); the core wakes up once a
        // minute to check the temperature, and probing resumes when charging is allowed.
        g_probing = false;
        g_probe_ctr = 0;
        g_usb = false;
        g_chg_status = CHG_NONE;
        chg_pin(1);
        return;
    }
    // disabled: charger off, float for one period every 5 s to look for USB
    if (g_probing) {
        g_probing = false;
        chg_pin(1);
    } else if (++g_probe_ctr >= 50) {
        g_probe_ctr = 0;
        g_probing = true;
        chg_pin(2);
    } else {
        chg_pin(1);
    }
    if (!g_usb) g_chg_status = CHG_NONE;
}

void storage_read(uint16_t addr, void* dst, uint16_t len) {
    uint8_t* d = (uint8_t*)dst;
    for (uint16_t i = 0; i < len; i++) d[i] = (uint32_t)(addr + i) < LX_STORAGE_SIZE ? g_store[addr + i] : 0xFF;
}

bool storage_write(uint16_t addr, const void* src, uint16_t len) {
    if ((uint32_t)addr + len > LX_STORAGE_SIZE || !g_nvs) return false;
    if (memcmp(g_store + addr, src, len) == 0) return true;      // unchanged: no flash write
    // The RAM copy changes only after the flash write succeeded, so that a failed write is
    // retried by the next save instead of being skipped as "unchanged".
    static uint8_t next[LX_STORAGE_SIZE];
    memcpy(next, g_store, sizeof next);
    memcpy(next + addr, src, len);
    if (nvs_set_blob(g_nvs, "store", next, sizeof next) != ESP_OK) return false;
    if (nvs_commit(g_nvs) != ESP_OK) return false;
    memcpy(g_store, next, sizeof g_store);
    return true;
}

int console_getc() {
    if (!g_console) return -1;
    uint8_t c;
    return usb_serial_jtag_read_bytes(&c, 1, 0) == 1 ? c : -1;
}

void console_write(const char* s) {
    if (g_console) usb_serial_jtag_write_bytes(s, strlen(s), 0);
}

}  // namespace hal
