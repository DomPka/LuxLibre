// SPDX-License-Identifier: GPL-3.0-or-later
// LuxLibre - the few CH32V003 registers the port uses.
//
// Peripheral base addresses, register offsets and bit positions are taken from the
// ch32-metapac crate (src/chips/ch32v003f4p6, src/registers/*), which is generated from
// WCH's SVD files; PWR and IWDG (missing there) follow the CH32V003 reference manual.
#pragma once
#include <stdint.h>

#define CH_REG(addr) (*(volatile uint32_t *)(addr))

// ---- base addresses ----
#define CH_TIM2_BASE   0x40000000u
#define CH_IWDG_BASE   0x40003000u
#define CH_PWR_BASE    0x40007000u
#define CH_AFIO_BASE   0x40010000u
#define CH_EXTI_BASE   0x40010400u
#define CH_GPIOA_BASE  0x40010800u
#define CH_GPIOC_BASE  0x40011000u
#define CH_GPIOD_BASE  0x40011400u
#define CH_ADC1_BASE   0x40012400u
#define CH_TIM1_BASE   0x40012C00u
#define CH_RCC_BASE    0x40021000u
#define CH_FLASH_BASE  0x40022000u
#define CH_PFIC_BASE   0xE000E000u
#define CH_STK_BASE    0xE000F000u

// ---- RCC ----
#define RCC_CTLR       CH_REG(CH_RCC_BASE + 0x00)
#define RCC_CFGR0      CH_REG(CH_RCC_BASE + 0x04)
#define RCC_APB2PCENR  CH_REG(CH_RCC_BASE + 0x18)
#define RCC_APB1PCENR  CH_REG(CH_RCC_BASE + 0x1C)
#define RCC_RSTSCKR    CH_REG(CH_RCC_BASE + 0x24)
#define RCC_HSION      (1u << 0)
#define RCC_CFGR0_HPRE_MASK (0xFu << 4)
#define RCC_APB2_AFIOEN  (1u << 0)
#define RCC_APB2_IOPAEN  (1u << 2)
#define RCC_APB2_IOPCEN  (1u << 4)
#define RCC_APB2_IOPDEN  (1u << 5)
#define RCC_APB2_ADC1EN  (1u << 9)
#define RCC_APB2_TIM1EN  (1u << 11)
#define RCC_APB1_PWREN   (1u << 28)
#define RCC_LSION        (1u << 0)
#define RCC_LSIRDY       (1u << 1)

// ---- FLASH ----
#define FLASH_ACTLR    CH_REG(CH_FLASH_BASE + 0x00)
#define FLASH_KEYR     CH_REG(CH_FLASH_BASE + 0x04)
#define FLASH_STATR    CH_REG(CH_FLASH_BASE + 0x0C)
#define FLASH_CTLR     CH_REG(CH_FLASH_BASE + 0x10)
#define FLASH_ADDR     CH_REG(CH_FLASH_BASE + 0x14)
#define FLASH_MODEKEYR CH_REG(CH_FLASH_BASE + 0x24)
#define FLASH_KEY1     0x45670123u
#define FLASH_KEY2     0xCDEF89ABu
#define FLASH_CTLR_STRT    (1u << 6)
#define FLASH_CTLR_LOCK    (1u << 7)
#define FLASH_CTLR_FLOCK   (1u << 15)
#define FLASH_CTLR_PAGE_PG (1u << 16)
#define FLASH_CTLR_PAGE_ER (1u << 17)
#define FLASH_CTLR_BUFLOAD (1u << 18)
#define FLASH_CTLR_BUFRST  (1u << 19)
#define FLASH_STATR_BSY    (1u << 0)
#define FLASH_STATR_EOP    (1u << 5)
#define FLASH_PROG_BASE    0x08000000u   // flash alias used for programming

// ---- GPIO (4 configuration bits per pin: MODE[1:0], CNF[3:2]) ----
#define GPIO_CFGLR(base) CH_REG((base) + 0x00)
#define GPIO_INDR(base)  CH_REG((base) + 0x08)
#define GPIO_OUTDR(base) CH_REG((base) + 0x0C)
#define GPIO_BSHR(base)  CH_REG((base) + 0x10)
#define GPIO_BCR(base)   CH_REG((base) + 0x14)
#define GPIO_CFG_IN_ANALOG   0x0u
#define GPIO_CFG_IN_PULL     0x8u          // CNF=10, MODE=00 (OUTDR selects up/down)
#define GPIO_CFG_OUT_PP      0x3u          // CNF=00, MODE=11 (fastest)
#define GPIO_CFG_AF_PP       0xBu          // CNF=10, MODE=11

// ---- AFIO / EXTI ----
#define AFIO_PCFR1     CH_REG(CH_AFIO_BASE + 0x04)
#define AFIO_EXTICR    CH_REG(CH_AFIO_BASE + 0x08)   // 2 bits per line: 00 PA, 10 PC, 11 PD
#define EXTI_INTENR    CH_REG(CH_EXTI_BASE + 0x00)
#define EXTI_EVENR     CH_REG(CH_EXTI_BASE + 0x04)
#define EXTI_RTENR     CH_REG(CH_EXTI_BASE + 0x08)
#define EXTI_FTENR     CH_REG(CH_EXTI_BASE + 0x0C)
#define EXTI_INTFR     CH_REG(CH_EXTI_BASE + 0x14)
#define EXTI_LINE_AWU  9u

// ---- ADC1 ----
#define ADC_STATR      CH_REG(CH_ADC1_BASE + 0x00)
#define ADC_CTLR1      CH_REG(CH_ADC1_BASE + 0x04)
#define ADC_CTLR2      CH_REG(CH_ADC1_BASE + 0x08)
#define ADC_SAMPTR2    CH_REG(CH_ADC1_BASE + 0x10)
#define ADC_RSQR1      CH_REG(CH_ADC1_BASE + 0x2C)
#define ADC_RSQR3      CH_REG(CH_ADC1_BASE + 0x34)
#define ADC_RDATAR     CH_REG(CH_ADC1_BASE + 0x4C)
#define ADC_STATR_EOC  (1u << 1)
#define ADC_CTLR2_ADON    (1u << 0)
#define ADC_CTLR2_CAL     (1u << 2)
#define ADC_CTLR2_RSTCAL  (1u << 3)
#define ADC_CTLR2_EXTSEL_SWSTART (7u << 17)
#define ADC_CTLR2_EXTTRIG (1u << 20)
#define ADC_CTLR2_SWSTART (1u << 22)
#define ADC_CH_VREFINT 8u                    // internal reference, 1.2 V typical

// ---- TIM1 (advanced timer) ----
#define TIM1_CTLR1     CH_REG(CH_TIM1_BASE + 0x00)
#define TIM1_SWEVGR    CH_REG(CH_TIM1_BASE + 0x14)
#define TIM1_CHCTLR1   CH_REG(CH_TIM1_BASE + 0x18)
#define TIM1_CHCTLR2   CH_REG(CH_TIM1_BASE + 0x1C)
#define TIM1_CCER      CH_REG(CH_TIM1_BASE + 0x20)
#define TIM1_PSC       CH_REG(CH_TIM1_BASE + 0x28)
#define TIM1_ATRLR     CH_REG(CH_TIM1_BASE + 0x2C)
#define TIM1_CHCVR(n)  CH_REG(CH_TIM1_BASE + 0x34 + 4u * (n))
#define TIM1_BDTR      CH_REG(CH_TIM1_BASE + 0x44)
#define TIM_CTLR1_CEN  (1u << 0)
#define TIM_CTLR1_ARPE (1u << 7)
#define TIM_SWEVGR_UG  (1u << 0)
#define TIM_BDTR_MOE   (1u << 15)
#define TIM_OCM_PWM1   6u                    // OCxM field value
#define TIM_OCPE       (1u << 3)

// ---- PWR / IWDG ----
#define PWR_CTLR       CH_REG(CH_PWR_BASE + 0x00)
#define PWR_AWUCSR     CH_REG(CH_PWR_BASE + 0x08)
#define PWR_AWUWR      CH_REG(CH_PWR_BASE + 0x0C)
#define PWR_AWUPSC     CH_REG(CH_PWR_BASE + 0x10)
#define PWR_CTLR_PDDS  (1u << 1)
#define PWR_AWUCSR_AWUEN (1u << 1)
#define IWDG_CTLR      CH_REG(CH_IWDG_BASE + 0x00)
#define IWDG_PSCR      CH_REG(CH_IWDG_BASE + 0x04)
#define IWDG_RLDR      CH_REG(CH_IWDG_BASE + 0x08)
#define IWDG_STATR     CH_REG(CH_IWDG_BASE + 0x0C)

// ---- PFIC (interrupt controller) and SysTick ----
#define PFIC_IENR(n)   CH_REG(CH_PFIC_BASE + 0x100 + 4u * (n))
#define PFIC_IRER(n)   CH_REG(CH_PFIC_BASE + 0x180 + 4u * (n))
#define PFIC_CFGR      CH_REG(CH_PFIC_BASE + 0x48)
#define PFIC_SCTLR     CH_REG(CH_PFIC_BASE + 0xD10)
#define PFIC_SCTLR_SLEEPDEEP (1u << 2)
#define PFIC_CFGR_SYSRESET   ((0xBEEFu << 16) | (1u << 7))
#define STK_CTLR       CH_REG(CH_STK_BASE + 0x00)
#define STK_SR         CH_REG(CH_STK_BASE + 0x04)
#define STK_CNT        CH_REG(CH_STK_BASE + 0x08)
#define STK_CMP        CH_REG(CH_STK_BASE + 0x10)
#define STK_CTLR_STE   (1u << 0)
#define STK_CTLR_STIE  (1u << 1)
#define STK_CTLR_STCLK (1u << 2)            // 1 = HCLK, 0 = HCLK/8
#define STK_CTLR_STRE  (1u << 3)            // reload at compare

// ---- interrupt numbers ----
#define IRQ_SYSTICK    12u
#define IRQ_EXTI7_0    20u
#define IRQ_AWU        21u
