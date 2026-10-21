// SPDX-License-Identifier: GPL-3.0-or-later
// LuxLibre firmware - HAL for the WCH CH32V003 (RV32EC, 48 MHz max, 16 KB flash, 2 KB RAM),
// a microcontroller that costs about $0.13 in quantity and runs from 2.7 to 5.5 V, so it
// can sit directly on a Li-ion cell.
//
// Resources: HSI 24 MHz (no PLL), SysTick 10 ms tick, TIM1 CH1 (PD2) 10-bit PWM at 23 kHz
// for the main channel (duty -> LED current set point of a buck driver, or FET gate),
// ADC1 for VDD (through the 1.2 V internal reference), an NTC and the button on PC1
// (EXTI1), standby with auto-wake-up (AWU) once per second as the clock while asleep,
// IWDG 4 s, settings emulated in the last 256 bytes of flash (four 64-byte pages).
//
// Status: compiles and links (make ch32v003); not yet tested on hardware.
#include "../../core/lx_board.h"
#include "../../core/lx_thermal.h"
#include "../../hal/lx_hal.h"
#include "../../hal/lx_ntc.h"
#include "ch32v003_regs.h"

// ---- board options (defaults = boards/example-ch32v003-buck) ----
#ifndef LX_CH32_BTN_PORT
#define LX_CH32_BTN_PORT CH_GPIOC_BASE
#define LX_CH32_BTN_PORTSEL 2u            // EXTICR code: 0 = PA, 2 = PC, 3 = PD
#endif
#ifndef LX_CH32_BTN_PIN
#define LX_CH32_BTN_PIN 1u
#endif
#ifndef LX_CH32_EN_PORT                   // driver enable output (optional)
#define LX_CH32_EN_PORT CH_GPIOC_BASE
#define LX_CH32_EN_PIN 3u
#endif
#ifndef LX_CH32_NTC_ADC_CH                // NTC on an ADC channel; -1 = none
#define LX_CH32_NTC_ADC_CH 0              // A0 = PA2
#define LX_CH32_NTC_PORT CH_GPIOA_BASE
#define LX_CH32_NTC_PIN 2u
#endif
#ifndef LX_CH32_NTC_RFIX
#define LX_CH32_NTC_RFIX 100000L
#endif
#ifndef LX_CH32_NTC_R25
#define LX_CH32_NTC_R25 100000L
#endif
#ifndef LX_CH32_NTC_BETA
#define LX_CH32_NTC_BETA 4250L
#endif
#ifndef LX_CH32_VREFINT_MV
#define LX_CH32_VREFINT_MV 1200u          // datasheet typical; calibrate with BAT_CAL
#endif

#define LX_PWM_TOP 1023u
#define LX_HCLK_HZ 24000000u
#define LX_SETTINGS_ADDR 0x3F00u          // must match link.ld
#define LX_PAGE 64u

static_assert(LX_STORAGE_SIZE == 256, "the CH32V003 port emulates exactly 256 bytes");

namespace {

volatile uint32_t g_ms = 0;
volatile uint8_t g_tick = 0;
volatile uint8_t g_btn_irq = 0;
uint8_t g_mirror[LX_STORAGE_SIZE];

constexpr lx::ntc::Table<LX_CH32_NTC_RFIX, LX_CH32_NTC_R25, LX_CH32_NTC_BETA> k_ntc{};

inline void irq_enable() { __asm__ volatile("csrs mstatus, %0" ::"r"(0x8u) : "memory"); }
inline void irq_disable() { __asm__ volatile("csrc mstatus, %0" ::"r"(0x8u) : "memory"); }
inline void wfi() { __asm__ volatile("wfi" ::: "memory"); }

void pin_config(uint32_t port, uint32_t pin, uint32_t cfg) {
    uint32_t v = GPIO_CFGLR(port);
    v &= ~(0xFu << (pin * 4u));
    v |= cfg << (pin * 4u);
    GPIO_CFGLR(port) = v;
}

void iwdg_reload() { IWDG_CTLR = 0xAAAAu; }

uint16_t adc_read(uint32_t ch) {
    ADC_RSQR3 = ch;
    uint32_t sum = 0;
    for (int i = 0; i < 4; i++) {
        ADC_CTLR2 |= ADC_CTLR2_SWSTART;
        while (!(ADC_STATR & ADC_STATR_EOC)) {}
        sum += ADC_RDATAR & 0x3FFu;
    }
    return (uint16_t)(sum / 4u);
}

void flash_wait() {
    while (FLASH_STATR & FLASH_STATR_BSY) {}
}

void flash_write_page(uint32_t offset) {   // offset inside the settings area, page aligned
    uint32_t addr = FLASH_PROG_BASE + LX_SETTINGS_ADDR + offset;
    FLASH_KEYR = FLASH_KEY1;
    FLASH_KEYR = FLASH_KEY2;
    FLASH_MODEKEYR = FLASH_KEY1;
    FLASH_MODEKEYR = FLASH_KEY2;
    // erase the 64-byte page
    FLASH_CTLR = FLASH_CTLR_PAGE_ER;
    FLASH_ADDR = addr;
    FLASH_CTLR = FLASH_CTLR_PAGE_ER | FLASH_CTLR_STRT;
    flash_wait();
    FLASH_CTLR = 0;
    // program it through the 64-byte buffer
    FLASH_CTLR = FLASH_CTLR_PAGE_PG;
    FLASH_CTLR = FLASH_CTLR_PAGE_PG | FLASH_CTLR_BUFRST;
    flash_wait();
    for (uint32_t i = 0; i < LX_PAGE; i += 4) {
        uint32_t w = (uint32_t)g_mirror[offset + i] | ((uint32_t)g_mirror[offset + i + 1] << 8) |
                     ((uint32_t)g_mirror[offset + i + 2] << 16) | ((uint32_t)g_mirror[offset + i + 3] << 24);
        *(volatile uint32_t*)(addr + i) = w;
        FLASH_CTLR = FLASH_CTLR_PAGE_PG | FLASH_CTLR_BUFLOAD;
        flash_wait();
    }
    FLASH_ADDR = addr;
    FLASH_CTLR = FLASH_CTLR_PAGE_PG | FLASH_CTLR_STRT;
    flash_wait();
    FLASH_CTLR = FLASH_CTLR_LOCK | FLASH_CTLR_FLOCK;
}

}  // namespace

extern "C" {
void systick_handler(void) __attribute__((interrupt("machine"), used));
void systick_handler(void) {
    STK_SR = 0;
    g_ms += LX_TICK_MS;
    g_tick = 1;
}
void exti7_0_handler(void) __attribute__((interrupt("machine"), used));
void exti7_0_handler(void) {
    EXTI_INTFR = 0xFFu;
    g_btn_irq = 1;
}
void awu_handler(void) __attribute__((interrupt("machine"), used));
void awu_handler(void) {
    EXTI_INTFR = 1u << EXTI_LINE_AWU;
    g_ms += 1000;
}
}

namespace hal {

void init() {
    // clocks for GPIO A/C/D, AFIO, ADC, TIM1, PWR
    RCC_APB2PCENR |= RCC_APB2_AFIOEN | RCC_APB2_IOPAEN | RCC_APB2_IOPCEN | RCC_APB2_IOPDEN | RCC_APB2_ADC1EN |
                     RCC_APB2_TIM1EN;
    RCC_APB1PCENR |= RCC_APB1_PWREN;
    RCC_CFGR0 &= ~RCC_CFGR0_HPRE_MASK;    // HCLK = HSI 24 MHz
    FLASH_ACTLR = 0;                      // zero wait states up to 24 MHz

    // 1. light off: driver enable low, PWM pin low until the timer runs
    GPIO_BCR(LX_CH32_EN_PORT) = 1u << LX_CH32_EN_PIN;
    pin_config(LX_CH32_EN_PORT, LX_CH32_EN_PIN, GPIO_CFG_OUT_PP);
    GPIO_BCR(CH_GPIOD_BASE) = 1u << 2;
    pin_config(CH_GPIOD_BASE, 2, GPIO_CFG_OUT_PP);

    // 2. PWM: TIM1 CH1 on PD2, PWM mode 1, 10 bit
    TIM1_PSC = 0;
    TIM1_ATRLR = LX_PWM_TOP;
    TIM1_CHCVR(0) = 0;
    TIM1_CHCTLR1 = (TIM_OCM_PWM1 << 4) | TIM_OCPE;
    TIM1_CCER = 1u;                       // CC1E
    TIM1_BDTR = TIM_BDTR_MOE;             // advanced timer: main output enable
    TIM1_CTLR1 = TIM_CTLR1_ARPE | TIM_CTLR1_CEN;
    TIM1_SWEVGR = TIM_SWEVGR_UG;
    pin_config(CH_GPIOD_BASE, 2, GPIO_CFG_AF_PP);

    // 3. button with pull-up, EXTI line on falling edge (enabled only for sleep)
    pin_config(LX_CH32_BTN_PORT, LX_CH32_BTN_PIN, GPIO_CFG_IN_PULL);
    GPIO_BSHR(LX_CH32_BTN_PORT) = 1u << LX_CH32_BTN_PIN;          // OUTDR = 1 -> pull-up
    AFIO_EXTICR = (AFIO_EXTICR & ~(3u << (2u * LX_CH32_BTN_PIN))) | (LX_CH32_BTN_PORTSEL << (2u * LX_CH32_BTN_PIN));
    EXTI_FTENR |= 1u << LX_CH32_BTN_PIN;

    // 4. ADC: VDD via the internal reference, NTC channel; slowest sampling (241 cycles)
#if LX_CH32_NTC_ADC_CH >= 0
    pin_config(LX_CH32_NTC_PORT, LX_CH32_NTC_PIN, GPIO_CFG_IN_ANALOG);
#endif
    ADC_SAMPTR2 = 0x3FFFFFFFu;
    ADC_RSQR1 = 0;                        // one conversion
    ADC_CTLR2 = ADC_CTLR2_ADON | ADC_CTLR2_EXTSEL_SWSTART | ADC_CTLR2_EXTTRIG;
    for (volatile int i = 0; i < 1000; i++) {}
    ADC_CTLR2 |= ADC_CTLR2_RSTCAL;
    while (ADC_CTLR2 & ADC_CTLR2_RSTCAL) {}
    ADC_CTLR2 |= ADC_CTLR2_CAL;
    while (ADC_CTLR2 & ADC_CTLR2_CAL) {}

    // 5. LSI for AWU and IWDG; watchdog 4 s (LSI 128 kHz / 256 = 500 Hz, reload 2000)
    RCC_RSTSCKR |= RCC_LSION;
    while (!(RCC_RSTSCKR & RCC_LSIRDY)) {}
    IWDG_CTLR = 0x5555u;
    IWDG_PSCR = 6u;
    IWDG_RLDR = 2000u;
    IWDG_CTLR = 0xCCCCu;

    // 6. settings mirror from flash
    for (uint32_t i = 0; i < LX_STORAGE_SIZE; i++) g_mirror[i] = *(const volatile uint8_t*)(LX_SETTINGS_ADDR + i);

    // 7. SysTick 10 ms
    STK_CTLR = 0;
    STK_SR = 0;
    STK_CNT = 0;
    STK_CMP = LX_HCLK_HZ / 1000u * LX_TICK_MS - 1u;
    STK_CTLR = STK_CTLR_STE | STK_CTLR_STIE | STK_CTLR_STCLK | STK_CTLR_STRE;
    PFIC_IENR(IRQ_SYSTICK / 32u) = 1u << (IRQ_SYSTICK % 32u);
    irq_enable();
}

void watchdog_kick() { iwdg_reload(); }

void reboot() {
    PFIC_CFGR = PFIC_CFGR_SYSRESET;
    for (;;) {}
}

uint32_t millis() {
    irq_disable();
    uint32_t t = g_ms;
    irq_enable();
    return t;
}

void wait_tick() {
    while (!g_tick) wfi();
    g_tick = 0;
}

bool sleep(uint32_t max_ms, bool wake_on_button) {
    uint32_t t0 = millis();
    STK_CTLR = 0;                                             // tick off
    PFIC_IRER(IRQ_SYSTICK / 32u) = 1u << (IRQ_SYSTICK % 32u);
    // auto-wake-up every ~1 s: LSI 128 kHz / 2048 = 62.5 Hz, window 62
    PWR_AWUPSC = 0xBu;                                        // prescaler 2048
    PWR_AWUWR = 62u;
    PWR_AWUCSR = PWR_AWUCSR_AWUEN;
    EXTI_RTENR |= 1u << EXTI_LINE_AWU;
    EXTI_INTENR |= 1u << EXTI_LINE_AWU;
    PFIC_IENR(IRQ_AWU / 32u) = 1u << (IRQ_AWU % 32u);
    g_btn_irq = 0;
    if (wake_on_button) {
        EXTI_INTFR = 1u << LX_CH32_BTN_PIN;
        EXTI_INTENR |= 1u << LX_CH32_BTN_PIN;
        PFIC_IENR(IRQ_EXTI7_0 / 32u) = 1u << (IRQ_EXTI7_0 % 32u);
    }
    PWR_CTLR |= PWR_CTLR_PDDS;                                // standby on WFI
    PFIC_SCTLR |= PFIC_SCTLR_SLEEPDEEP;
    bool by_button = false;
    for (;;) {
        iwdg_reload();
        wfi();
        if (wake_on_button && (g_btn_irq || button_down())) { by_button = true; break; }
        if (max_ms && (uint32_t)(millis() - t0) >= max_ms) break;
    }
    PFIC_SCTLR &= ~PFIC_SCTLR_SLEEPDEEP;
    PWR_CTLR &= ~PWR_CTLR_PDDS;
    EXTI_INTENR &= ~((1u << LX_CH32_BTN_PIN) | (1u << EXTI_LINE_AWU));
    PWR_AWUCSR = 0;
    PFIC_IRER(IRQ_AWU / 32u) = 1u << (IRQ_AWU % 32u);
    PFIC_IRER(IRQ_EXTI7_0 / 32u) = 1u << (IRQ_EXTI7_0 % 32u);
    // the HSI is the clock again after standby; restart the tick
    STK_CNT = 0;
    STK_SR = 0;
    STK_CTLR = STK_CTLR_STE | STK_CTLR_STIE | STK_CTLR_STCLK | STK_CTLR_STRE;
    PFIC_IENR(IRQ_SYSTICK / 32u) = 1u << (IRQ_SYSTICK % 32u);
    return by_button;
}

bool button_down() { return !(GPIO_INDR(LX_CH32_BTN_PORT) & (1u << LX_CH32_BTN_PIN)); }

uint16_t battery_mv() {
    uint16_t ref = adc_read(ADC_CH_VREFINT);                  // VDD is the ADC reference
    if (!ref) return 0;
    return (uint16_t)((uint32_t)LX_CH32_VREFINT_MV * 1023u / ref);
}

lx::temp_dc_t temperature() {
#if LX_CH32_NTC_ADC_CH >= 0
    return k_ntc.temp_dc(adc_read(LX_CH32_NTC_ADC_CH), 1023u);
#else
    return lx::thermal::NO_SENSOR;
#endif
}

bool usb_present() { return false; }
uint8_t charger_status() { return CHG_NONE; }

void set_main(lx::power_t power) {
    uint32_t duty = ((uint32_t)power * LX_PWM_TOP + 32767u) / 65535u;
    if (power && !duty) duty = 1;
    TIM1_CHCVR(0) = duty;
    if (power) GPIO_BSHR(LX_CH32_EN_PORT) = 1u << LX_CH32_EN_PIN;
    else GPIO_BCR(LX_CH32_EN_PORT) = 1u << LX_CH32_EN_PIN;
}

void set_aux(uint8_t, uint8_t, uint8_t) {}
void set_laser(bool) {}
void set_charge(bool, bool) {}

void storage_read(uint16_t addr, void* dst, uint16_t len) {
    uint8_t* d = (uint8_t*)dst;
    for (uint16_t i = 0; i < len; i++) d[i] = (uint32_t)(addr + i) < LX_STORAGE_SIZE ? g_mirror[addr + i] : 0xFF;
}

bool storage_write(uint16_t addr, const void* src, uint16_t len) {
    if ((uint32_t)addr + len > LX_STORAGE_SIZE) return false;
    const uint8_t* s = (const uint8_t*)src;
    uint8_t dirty = 0;   // one bit per 64-byte page
    for (uint16_t i = 0; i < len; i++) {
        if (g_mirror[addr + i] != s[i]) {
            g_mirror[addr + i] = s[i];
            dirty |= (uint8_t)(1u << ((addr + i) / LX_PAGE));
        }
    }
    for (uint32_t pg = 0; pg < LX_STORAGE_SIZE / LX_PAGE; pg++) {
        if (dirty & (1u << pg)) {
            iwdg_reload();
            irq_disable();
            flash_write_page(pg * LX_PAGE);
            irq_enable();
        }
    }
    return true;
}

int console_getc() { return -1; }
void console_write(const char*) {}

}  // namespace hal
