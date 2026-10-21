/* SPDX-License-Identifier: GPL-3.0-or-later
 * LuxLibre - linker script for the CH32V003 (16 KB flash, 2 KB SRAM).
 * The last 256 bytes of flash hold the emulated EEPROM (settings).
 */
ENTRY(_start)

MEMORY
{
    FLASH (rx)  : ORIGIN = 0x00000000, LENGTH = 16K - 256
    SETTINGS (r): ORIGIN = 0x00003F00, LENGTH = 256
    RAM (rwx)   : ORIGIN = 0x20000000, LENGTH = 2K
}

SECTIONS
{
    .init : { KEEP(*(.init)) } > FLASH
    .text : {
        . = ALIGN(4);
        *(.text .text.*)
        *(.rodata .rodata.* .srodata .srodata.*)
        . = ALIGN(4);
    } > FLASH
    .data : {
        . = ALIGN(4);
        __data_start = .;
        PROVIDE(__global_pointer$ = . + 0x800);
        *(.data .data.* .sdata .sdata.*)
        . = ALIGN(4);
        __data_end = .;
    } > RAM AT > FLASH
    __data_load = LOADADDR(.data);
    .bss (NOLOAD) : {
        . = ALIGN(4);
        __bss_start = .;
        *(.bss .bss.* .sbss .sbss.* COMMON)
        . = ALIGN(4);
        __bss_end = .;
    } > RAM
    __stack_top = ORIGIN(RAM) + LENGTH(RAM);
    __settings_start = ORIGIN(SETTINGS);
    /DISCARD/ : { *(.comment) *(.riscv.attributes) *(.eh_frame*) }
}
