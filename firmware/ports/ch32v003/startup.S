/* SPDX-License-Identifier: GPL-3.0-or-later
 * LuxLibre - start-up code for the WCH CH32V003 (QingKe V2A, RV32EC).
 *  - vector table at the start of flash (word 0 jumps to the reset handler)
 *  - global pointer, stack, .data copy, .bss clear, then main()
 * mtvec = vector table | 3: the table holds absolute handler addresses.
 */
        .section .init, "ax", @progbits
        .global _start
        .align  2
_start:
        .option push
        .option norvc                       /* a full 4-byte jump keeps the table aligned */
        j       reset_handler
        .option pop
        .word   0
        .word   nmi_handler                 /* 2  NMI */
        .word   hardfault_handler           /* 3  HardFault */
        .word   0, 0, 0, 0, 0, 0, 0, 0      /* 4 ... 11 */
        .word   systick_handler             /* 12 SysTick */
        .word   0                           /* 13 */
        .word   default_handler             /* 14 SW */
        .word   0                           /* 15 */
        .word   default_handler             /* 16 WWDG */
        .word   default_handler             /* 17 PVD */
        .word   default_handler             /* 18 FLASH */
        .word   default_handler             /* 19 RCC */
        .word   exti7_0_handler             /* 20 EXTI7_0 */
        .word   awu_handler                 /* 21 AWU */
        .rept   17                          /* 22 ... 38: DMA, ADC, I2C, USART, SPI, TIM1, TIM2 */
        .word   default_handler
        .endr

        .text
        .align  2
reset_handler:
        .option push
        .option norelax
        la      gp, __global_pointer$
        .option pop
        la      sp, __stack_top
        /* copy .data from flash to RAM */
        la      a0, __data_load
        la      a1, __data_start
        la      a2, __data_end
1:      bgeu    a1, a2, 2f
        lw      t0, 0(a0)
        sw      t0, 0(a1)
        addi    a0, a0, 4
        addi    a1, a1, 4
        j       1b
2:      /* clear .bss */
        la      a1, __bss_start
        la      a2, __bss_end
3:      bgeu    a1, a2, 4f
        sw      zero, 0(a1)
        addi    a1, a1, 4
        j       3b
4:      /* vector table with absolute addresses */
        la      t0, _start
        ori     t0, t0, 3
        csrw    mtvec, t0
        call    main
5:      j       5b

        .weak   nmi_handler, hardfault_handler, systick_handler, exti7_0_handler, awu_handler
        .set    nmi_handler, default_handler
        .set    hardfault_handler, default_handler
        .set    systick_handler, default_handler
        .set    exti7_0_handler, default_handler
        .set    awu_handler, default_handler
        .global default_handler
default_handler:
        j       _start                      /* unexpected interrupt: restart */
