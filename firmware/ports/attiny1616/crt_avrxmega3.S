/* SPDX-License-Identifier: GPL-3.0-or-later
 * LuxLibre - start-up code for tinyAVR 0/1-series (avrxmega3), used instead of avr-libc's
 * crtattiny1616.o, which older avr-libc releases do not ship.
 *
 *  - interrupt vector table: 2-word JMP per vector (devices with more than 8 KB flash)
 *  - zero register, status register, stack pointer
 *  - .data copy and .bss clearing come from libgcc (__do_copy_data / __do_clear_bss in
 *    section .init4); the compiler references them whenever .data or .bss is used
 *  - call main()
 */

        .set    LX_SREG, 0x3F
        .set    LX_SPL, 0x3D
        .set    LX_SPH, 0x3E
        .set    LX_RAMEND, 0x3FFF        /* ATtiny1614/16/17: SRAM 0x3800 ... 0x3FFF */

        .section .vectors, "ax", @progbits
        .global __vectors
        .type   __vectors, @function
__vectors:
        jmp     __init
        .irp    n, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30
        .weak   __vector_\n
        .set    __vector_\n, __bad_interrupt
        jmp     __vector_\n
        .endr

        .text
        .global __bad_interrupt
        .type   __bad_interrupt, @function
__bad_interrupt:
        jmp     __vectors                /* unexpected interrupt: restart */

        .section .init0, "ax", @progbits
        .global __init
        .type   __init, @function
__init:

        .section .init2, "ax", @progbits
        clr     r1
        out     LX_SREG, r1
        ldi     r28, lo8(LX_RAMEND)
        ldi     r29, hi8(LX_RAMEND)
        out     LX_SPL, r28
        out     LX_SPH, r29

        .section .init9, "ax", @progbits
        call    main
1:      rjmp    1b
