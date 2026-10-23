// SPDX-License-Identifier: GPL-3.0-or-later
// LuxLibre firmware - HAL for the ATtiny1616 (tinyAVR 1-series), the MCU of many current
// enthusiast flashlights. Register names come from tiny1x_io.h (generated from the ATDF).
//
// Resources: CLK_PER 10 MHz (OSC20M / 2), TCA0 single-slope 10-bit PWM (9.8 kHz) for the
// main channel, TCB0 10 ms tick, RTC PIT (1 Hz, 32 kHz ULP oscillator) as the clock in power-down,
// ADC0 for VDD (= cell voltage, MCU powered from the cell) and the internal temperature sensor,
// EEPROM for the settings, WDT 1 s.
//
// Status: compiles and links (make tiny1616); not yet tested on hardware.
#include "../../hal/lx_hal.h"
#include "../../core/lx_board.h"
#include "../../core/lx_thermal.h"
#include "tiny1x_io.h"

#ifndef LX_TINY_PWM_WO
#define LX_TINY_PWM_WO 0          // TCA0 WO0 = PB0
#endif
#ifndef LX_TINY_BTN_PIN
#define LX_TINY_BTN_PIN 2         // PA2 (fully asynchronous: wakes from power-down on any edge)
#endif
#ifndef LX_TINY_TEMP_OFFSET_DC
#define LX_TINY_TEMP_OFFSET_DC 0  // calibration of the internal sensor, deci-degC
#endif

#define LX_PWM_TOP 1023u

namespace {

volatile uint32_t g_ms = 0;
volatile uint8_t g_tick = 0;
volatile uint8_t g_btn_irq = 0;

inline void sei_() { __asm__ __volatile__("sei" ::: "memory"); }
inline void cli_() { __asm__ __volatile__("cli" ::: "memory"); }
inline void wdr_() { __asm__ __volatile__("wdr" ::: "memory"); }
inline void sleep_() { __asm__ __volatile__("sleep" ::: "memory"); }

// Protected register write (CCP): the write must follow within 4 cycles.
inline void ccp_write_io(volatile uint8_t& reg, uint8_t value) {
    CPU_CCP = CPU_CCP_IOREG_gc;
    reg = value;
}

uint16_t adc_read(uint8_t muxpos, uint8_t refsel, bool samp_cap, uint8_t sampnum) {
    ADC0_CTRLC = (uint8_t)(refsel | ADC_PRESC_DIV8_gc | (samp_cap ? ADC_SAMPCAP_bm : 0));
    ADC0_CTRLD = ADC_INITDLY_DLY32_gc;
    ADC0_SAMPCTRL = 4;
    ADC0_MUXPOS = muxpos;
    ADC0_CTRLB = sampnum;                             // accumulate 4 or 16 samples
    ADC0_CTRLA = ADC_ENABLE_bm | ADC_RESSEL_10BIT_gc;
    ADC0_INTFLAGS = ADC_RESRDY_bm;
    ADC0_COMMAND = ADC_STCONV_bm;
    while (!(ADC0_INTFLAGS & ADC_RESRDY_bm)) {}
    uint16_t r = ADC0_RES;                            // sum of the 10-bit samples
    ADC0_CTRLA = 0;                                   // ADC off between readings (saves power)
    return r;
}

void pwm_pin_output(bool on) {
    if (on) PORTB_DIRSET = (uint8_t)(1u << LX_TINY_PWM_WO);
    PORTB_OUTCLR = (uint8_t)(1u << LX_TINY_PWM_WO);
}

}  // namespace

// TCB0: 10 ms tick
extern "C" void __vector_13(void) __attribute__((signal, used, externally_visible));
void __vector_13(void) {
    TCB0_INTFLAGS = TCB_CAPT_bm;
    g_ms += LX_TICK_MS;
    g_tick = 1;
}

// RTC PIT: 1 s while in power-down
extern "C" void __vector_7(void) __attribute__((signal, used, externally_visible));
void __vector_7(void) {
    RTC_PITINTFLAGS = RTC_PI_bm;
    g_ms += 1000;
}

// PORTA pin change: button wake-up
extern "C" void __vector_3(void) __attribute__((signal, used, externally_visible));
void __vector_3(void) {
    PORTA_INTFLAGS = 0xFF;
    g_btn_irq = 1;
}

namespace hal {

void init() {
    // 1. light off before anything else
    PORTB_OUTCLR = (uint8_t)(1u << LX_TINY_PWM_WO);
    PORTB_DIRSET = (uint8_t)(1u << LX_TINY_PWM_WO);
    // 2. clock: 20 MHz oscillator / 2 = 10 MHz (allowed from 2.7 V)
    ccp_write_io(CLKCTRL_MCLKCTRLB, (uint8_t)(CLKCTRL_PDIV_2X_gc | CLKCTRL_PEN_bm));
    // 3. button with pull-up, no interrupt while awake
    (&PORTA_PIN0CTRL)[LX_TINY_BTN_PIN] = (uint8_t)(PORT_PULLUPEN_bm | PORT_ISC_INTDISABLE_gc);
    // 4. PWM: TCA0 single slope, 10 bit, WOn output
    TCA0_SINGLE_PER = LX_PWM_TOP;
    (&TCA0_SINGLE_CMP0)[LX_TINY_PWM_WO] = 0;
    TCA0_SINGLE_CTRLB = (uint8_t)(TCA_SINGLE_WGMODE_SINGLESLOPE_gc | (TCA_SINGLE_CMP0EN_bm << LX_TINY_PWM_WO));
    TCA0_SINGLE_CTRLA = (uint8_t)(TCA_SINGLE_CLKSEL_DIV1_gc | TCA_SINGLE_ENABLE_bm);
    // 5. tick: TCB0 periodic interrupt, 10 MHz / 2 = 5 MHz -> LX_TICK_MS
    TCB0_CCMP = (uint16_t)(5000u * LX_TICK_MS - 1u);
    TCB0_CTRLB = TCB_CNTMODE_INT_gc;
    TCB0_INTCTRL = TCB_CAPT_bm;
    TCB0_CTRLA = (uint8_t)(TCB_CLKSEL_CLKDIV2_gc | TCB_ENABLE_bm);
    // 6. RTC on the 32 kHz ULP oscillator for timekeeping in power-down
    RTC_CLKSEL = RTC_CLKSEL_INT32K_gc;
    // 7. internal reference 1.1 V for the ADC
    VREF_CTRLA = VREF_ADC0REFSEL_1V1_gc;
    // 8. watchdog ~1 s
    ccp_write_io(WDT_CTRLA, WDT_PERIOD_1KCLK_gc);
    sei_();
}

void watchdog_kick() { wdr_(); }

void reboot() {
    ccp_write_io(RSTCTRL_SWRR, RSTCTRL_SWRE_bm);
    for (;;) {}
}

uint32_t millis() {
    cli_();
    uint32_t t = g_ms;
    sei_();
    return t;
}

void wait_tick() {
    SLPCTRL_CTRLA = (uint8_t)(SLPCTRL_SMODE_IDLE_gc | SLPCTRL_SEN_bm);
    while (!g_tick) sleep_();            // the TCB0 interrupt wakes the CPU
    g_tick = 0;
    SLPCTRL_CTRLA = 0;
}

bool sleep(uint32_t max_ms, bool wake_on_button) {
    uint32_t t0 = millis();
    // stop the tick, start the 1 Hz RTC interrupt, arm the button interrupt
    TCB0_INTCTRL = 0;
    while (RTC_PITSTATUS & 1u) {}        // CTRLBUSY
    RTC_PITINTCTRL = RTC_PI_bm;
    RTC_PITCTRLA = (uint8_t)(RTC_PERIOD_CYC32768_gc | RTC_PITEN_bm);
    g_btn_irq = 0;
    if (wake_on_button)
        (&PORTA_PIN0CTRL)[LX_TINY_BTN_PIN] = (uint8_t)(PORT_PULLUPEN_bm | PORT_ISC_BOTHEDGES_gc);
    ccp_write_io(WDT_CTRLA, WDT_PERIOD_OFF_gc);   // the watchdog would also run in power-down
    bool by_button = false;
    SLPCTRL_CTRLA = (uint8_t)(SLPCTRL_SMODE_PDOWN_gc | SLPCTRL_SEN_bm);
    for (;;) {
        sleep_();
        if (wake_on_button && (g_btn_irq || button_down())) { by_button = true; break; }
        if (max_ms && (uint32_t)(millis() - t0) >= max_ms) break;
    }
    SLPCTRL_CTRLA = 0;
    (&PORTA_PIN0CTRL)[LX_TINY_BTN_PIN] = (uint8_t)(PORT_PULLUPEN_bm | PORT_ISC_INTDISABLE_gc);
    RTC_PITCTRLA = 0;
    RTC_PITINTCTRL = 0;
    ccp_write_io(WDT_CTRLA, WDT_PERIOD_1KCLK_gc);
    TCB0_INTFLAGS = TCB_CAPT_bm;
    TCB0_INTCTRL = TCB_CAPT_bm;
    return by_button;
}

bool button_down() { return !(PORTA_IN & (1u << LX_TINY_BTN_PIN)); }

uint16_t battery_mv() {
    // VDD as reference, measure the 1.1 V internal reference: VDD = 1.1 V * 1023 / reading
    uint16_t sum = adc_read(ADC_MUXPOS_INTREF_gc, ADC_REFSEL_VDDREF_gc, false, ADC_SAMPNUM_ACC4_gc);
    if (sum == 0) return 0;
    return (uint16_t)((1100UL * 1023UL * 4UL) / sum);
}

lx::temp_dc_t temperature() {
    // Internal sensor with the factory calibration in the signature row (datasheet formula,
    // K = (adc - offset) * gain / 256). One ADC count is about 1 degC, so 16 samples are
    // summed and the fraction is kept: ADC noise then gives readings finer than 1 degC.
    uint16_t sum = adc_read(ADC_MUXPOS_TEMPSENSE_gc, ADC_REFSEL_INTREF_gc, true, ADC_SAMPNUM_ACC16_gc);
    int8_t offset = (int8_t)SIGROW_TEMPSENSE1;
    uint8_t gain = SIGROW_TEMPSENSE0;
    int32_t raw_q4 = (int32_t)sum - 16 * (int32_t)offset;  // ADC counts * 16
    int32_t dc = (raw_q4 * gain * 10 + 2048) / 4096 - 2732; // deci-degC
    return (lx::temp_dc_t)(dc + LX_TINY_TEMP_OFFSET_DC);
}

bool usb_present() { return false; }
uint8_t charger_status() { return CHG_NONE; }

void set_main(lx::power_t power) {
    uint32_t duty = ((uint32_t)power * LX_PWM_TOP + 32767u) / 65535u;
    if (power && !duty) duty = 1;
    (&TCA0_SINGLE_CMP0)[LX_TINY_PWM_WO] = (uint16_t)duty;
    pwm_pin_output(true);
}

void set_aux(uint8_t, uint8_t, uint8_t) {}
void set_laser(bool) {}
void set_side(uint8_t, uint8_t) {}
void set_color(uint16_t, uint16_t, uint16_t) {}
void set_charge(bool, bool) {}

void storage_read(uint16_t addr, void* dst, uint16_t len) {
    uint8_t* d = (uint8_t*)dst;
    for (uint16_t i = 0; i < len; i++) {
        uint16_t a = (uint16_t)(addr + i);
        d[i] = a < MEM_EEPROM_SIZE ? LX_SFR8(MEM_EEPROM_START + a) : 0xFF;
    }
}

bool storage_write(uint16_t addr, const void* src, uint16_t len) {
    const uint8_t* s = (const uint8_t*)src;
    for (uint16_t i = 0; i < len; i++) {
        uint16_t a = (uint16_t)(addr + i);
        if (a >= MEM_EEPROM_SIZE) return false;
        if (LX_SFR8(MEM_EEPROM_START + a) == s[i]) continue;   // skip unchanged bytes (wear)
        while (NVMCTRL_STATUS & NVMCTRL_EEBUSY_bm) wdr_();
        LX_SFR8(MEM_EEPROM_START + a) = s[i];                   // into the page buffer
        CPU_CCP = CPU_CCP_SPM_gc;
        NVMCTRL_CTRLA = NVMCTRL_CMD_PAGEERASEWRITE_gc;
    }
    while (NVMCTRL_STATUS & NVMCTRL_EEBUSY_bm) wdr_();
    return true;
}

int console_getc() { return -1; }
void console_write(const char*) {}

}  // namespace hal
