# SPDX-License-Identifier: GPL-3.0-or-later
"""
FlashKa Keychain v0.7 - single source of truth for the electronics capture.

Every component of the light with: symbol, footprint, value, LCSC number,
pin -> net map, schematic block and position, and the board it sits on
("main" = main PCB, "keys" = key board).  The schematic, both PCBs, the BOMs,
the CPL files and the netlist checks are all generated from this table.

v0.7 power stage for >= 1000 lm (LED Luminus SST-20 Gen 2 at up to 3.0 A)
  * Buck U2 TLV62585DRL (3 A, SOT-563) -> TI TPS62095RGTR (4 A, 100 % duty mode, VFB 0.8 V,
    VQFN-16 3 x 3 mm): CP/CN charge-pump capacitor C23, DEF tied to VIN, VOS to the output,
    SS and PG open.  The TLV333 current loop is unchanged (R10/R11 now give 2.4 V with Q2 off).
  * Full scale 3.55 A: R16 2k -> 2.2k (VSET = duty x 3.3 V x 2.2/102.2 = 71.0 mV at 100 % across
    the unchanged 20 mOhm RS1); the 3.0 A LED ceiling = 84.5 % duty.
  * 22 uF input capacitor C5 next to PVIN/PGND (the data sheet asks for >= 22 uF; C7 100 nF dropped),
    second 22 uF on the output (C22, data sheet: 2 x 22 uF); the feed-forward capacitor C9 is
    dropped (the TPS62095 needs none; the TLV333 loop sets the dynamics).
  * 1-cell protection on the main board (the cell has none): DW01A U6 + dual N-MOSFET
    SE8830A Q3 in the cell minus (net BATN between the J2 BAT- pad and Q3; board GND = P-),
    R35/C24 supply filter, R36 in the CS line.  Over-current trip 120-180 mV across the two
    MOSFETs (Kelvin-sensed at Q3's pins): typically 4.3-4.5 A with hot MOSFETs, 3.0 A in the worst
    corner; the TP4057 charges through the two MOSFETs.
  * One 14500 cell (Vapcell INR14500 F15, 1500 mAh, 3 A) on J2, one 24 AWG wire per pad; charge
    current 500 mA, the cell's standard charge (R3 3.3k -> 2.0k: TP4057 I = 1000 x 1.0 V / R3).
  * J2 (BAT+ / BAT-) and J3 pads for 24 AWG wires.  J3 keeps the v0.6 faces (LED+ top, LED-
    bottom) but its two pads split: LED+ moves to the top face between the USB-C receptacle's two
    front shell legs (in line with the top LED wire hole of the head, next to the buck output),
    LED- stays on the bottom face behind the receptacle and joins the sense resistor RS1 on the top
    face through six vias.  The high-current paths are pours and wide tracks with several vias
    per layer change (3.5 A).

v0.7 changes against v0.6 (docs/ch14_v0.7_keys_and_skin.md)
  * New key board (KB, board "keys") screwed to the floor directly above the
    keys, so the three keys sit on the centre line of the light.  SW1-SW3,
    LED3, LED4, R23-R25, R32-R34, R30 and R31 move from the main board to the
    KB.  Values, nets and GPIOs are unchanged (firmware 0.6.0 runs as it is):
    ladder R30 1k / R31 2.2k with the R9 10k pull-up on the main board, ring
    LEDs common anode to 3V3 with R23/R32 330 ohm, R24/R33 and R25/R34 100 ohm;
    the strap pull-ups R21/R22 stay on the main board.
  * KB bottom face: SW1 main (22.9, 0, pads along X), SW2 next (15.9, 0) and
    SW3 previous (29.9, 0) with their pads along Y, LED3 (22.9, +2.4) and LED4
    (22.9, -2.4) emitting down into the clear main key.  KB top face: the
    eight resistors and six Harwin P70-1010045R SMT pogo pins P1-P6 (no peg,
    gold, free 5.0 / working 4.0 mm, 1.17 N).
  * Main board: J6 = six round ENIG target pads (d1.6, mask d1.8, no paste)
    on the bottom face, right above the pogo pins: 1 GND, 2 3V3, 3 RGB_R,
    4 RGB_G, 5 RGB_B, 6 BTN.  Every other part keeps its v0.6 position.
  * The KB nets BTN_NX, BTN_PV, R_K, G_K, B_K, R_K2, G_K2 and B_K2 now live on
    the KB only; GND, 3V3, RGB_R, RGB_G, RGB_B and BTN reach it through J6/P1-P6.

v0.6 changes against v0.5 (docs/ch13_v0.6_presenter.md, 13.3.1)
  * S1 (side button) removed.  Three Alps SKRKAEE020 top-push switches on the
    bottom face: SW1 main (BTN - GND), SW2 next (BTN_NX - GND), SW3 previous
    (BTN_PV - GND).  R30 1k and R31 2.2k make a resistor ladder on the BTN net
    (pull-up R9 10k): every press is a digital low on GPIO9, GPIO3 reads the level.
  * Ring LEDs LED3 + LED4 (NH-B1010RGBT-HF) on the bottom face, both driven from
    the same three GPIOs; R23/R32 330 ohm (red), R24/R33 and R25/R34 100 ohm.

v0.5 changes against v0.4
  * MCU: ESP32-C3-MINI-1 (Bluetooth LE, native USB). Firmware is flashed
    through the flashlight's own USB-C port from a web page - no programmer.
  * USB D+/D- wired to the module (GPIO19/GPIO18).
  * VBUS-edge reset (Q5): plugging in USB resets the MCU, so "hold the button
    while plugging in" starts the ROM download mode (button = GPIO9 strap).
  * 3.3 V LDO (RT9080, 2 uA quiescent) for the module.
  * Charger TP4056 (ESOP-8) -> TP4057 (SOT-23-6, ~300 mA); the MCU sets the
    charge current through the PROG return (R3 to GPIO20, R29 trickle path).  The two charge LEDs are gone: the RGB LED shows the
    charge state through the plastic RF window of the lid.
  * LED current set by a filtered 13-bit PWM (the ATtiny had a DAC).
  * Laser gate driven through Q4 (3.3 V MCU, gate at VBAT); interlock S2 kept.
  * NTC on the main PCB (off-the-shelf 10 mm DTP LED board has none).
  * 0402 passives; 4-layer board, assembled on both sides.

Pin numbers follow the manufacturers' datasheets (checked 2026-10-14):
  ESP32-C3-MINI-1  Espressif datasheet table 3 (53 pads, 49 = EPAD)
  TP4057           1 CHRG, 2 GND, 3 BAT, 4 VCC, 5 STDBY, 6 PROG
  RT9080-33GJ5     1 VIN, 2 GND, 3 EN, 4 NC, 5 VOUT
  TPS62095RGT      1-2 SW, 3 DEF, 4 PG, 5 FB, 6 AGND, 7 CP, 8 CN, 9 SS, 10 AVIN, 11-12 PVIN,
                   13 EN, 14-15 PGND, 16 VOS, 17 exposed pad (AGND)
  TLV333 (DCK)     1 OUT, 2 V-, 3 +IN, 4 -IN, 5 V+
  DW01A            1 OD, 2 CS, 3 OC, 4 TD, 5 VCC, 6 GND
  SE8830A          1 S1, 2 D, 3 S2, 4 G2, 5 D, 6 G1 (8205-type SOT-23-6, common drain)
  SOT-23 MOSFETs   1 G, 2 S, 3 D
"""

R0402 = "Resistor_SMD:R_0402_1005Metric"
C0402 = "Capacitor_SMD:C_0402_1005Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"

RES = {  # value -> LCSC (UNI-ROYAL 0402WGF, 1 %, JLC basic unless noted)
    "0": "C17168", "100": "C25076", "330": "C25104", "1k": "C11702",
    "2k": "C4109", "2.2k": "C25879", "3.3k": "C25890", "4.7k": "C25900",
    "5.1k": "C25905", "10k": "C25744", "47k": "C25792", "100k": "C25741",
    "200k": "C25764", "1M": "C26083",
}
CAP = {  # value -> (LCSC, footprint, description)
    "100nF": ("C1525", C0402, "100nF 16V X7R 0402"),
    "1uF": ("C52923", C0402, "1uF 25V X5R 0402"),
    "10nF": ("C15195", C0402, "10nF 50V X7R 0402"),
    "22pF": ("C1555", C0402, "22pF 50V C0G 0402"),
    "10uF": ("C19702", C0603, "10uF 10V X5R 0603"),
    "10uF25": ("C15850", C0805, "10uF 25V X5R 0805"),
    "22uF6": ("C59461", C0603, "22uF 6.3V X5R 0603"),
    "22uF": ("C45783", C0805, "22uF 25V X5R 0805"),
}


def R(ref, val, n1, n2, block, pos, rot=90, dnp=False, board="main"):
    shown = val + "Ω" if val[-1].isdigit() else val
    return dict(ref=ref, sym=("kicad", "Device", "R"), value=shown,
                fp=R0402, lcsc=RES[val], desc=f"{val} 1% 0402 resistor",
                nets={"1": n1, "2": n2}, block=block, pos=pos, rot=rot, dnp=dnp, board=board)


def C(ref, val, n1, n2, block, pos, rot=0, dnp=False):
    l, fp, d = CAP[val]
    shown = {"10uF25": "10uF", "22uF6": "22uF"}.get(val, val)
    return dict(ref=ref, sym=("kicad", "Device", "C"), value=shown, fp=fp, lcsc=l,
                desc=d, nets={"1": n1, "2": n2}, block=block, pos=pos, rot=rot,
                dnp=dnp)


BLOCKS = {
    1: "Blocks 1-2: USB-C (power + data), TP4057 charger with charge pause",
    3: "Block 3: cell pads, 3.3 V LDO, VBUS-edge reset",
    4: "Block 4: synchronous buck LED driver with cascaded current loop",
    5: "Block 5: laser load switch with hardware interlock (gate path)",
    6: "Block 6: ESP32-C3-MINI-1 (BLE, USB), NTC, VBAT sense, J6",
    7: "Block 7: KEY BOARD (own PCB): buttons, ring LEDs, pogo pins",
}

# block frames on the A3 sheet (x0, y0, x1, y1) in mm, KiCad page coordinates
FRAMES = {
    1: (12, 18, 148, 150),
    3: (12, 156, 148, 284),
    4: (152, 18, 288, 150),
    5: (152, 156, 288, 284),
    6: (292, 18, 410, 144),
    7: (292, 148, 410, 252),
}

# boards: "main" = main PCB (FlashKa_main), "keys" = key board (FlashKa_keys)
BOARDS = ("main", "keys")

MOD_NC = ["4", "7", "9", "10", "15", "17", "24", "25", "28", "29", "32", "33", "34", "35"]
MOD_GND = ["1", "2", "11", "14"] + [str(n) for n in range(36, 54)]

COMPONENTS = [
    # ------------------------------------------------------------ block 1
    dict(ref="J1", sym=("kicad", "Connector", "USB_C_Receptacle_USB2.0_16P"),
         value="TYPE-C-31-M-12", fp="Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
         lcsc="C165948", desc="USB-C 16P receptacle (USB 2.0 data), SMD + 4 shell legs",
         nets={"A4": "VBUS", "A9": "VBUS", "B4": "VBUS", "B9": "VBUS",
               "A1": "GND", "A12": "GND", "B1": "GND", "B12": "GND", "S1": "GND",
               "A5": "CC1", "B5": "CC2", "A6": "USB_DP", "B6": "USB_DP",
               "A7": "USB_DN", "B7": "USB_DN"},
         nc=["A8", "B8"], block=1, pos=(30, 92), rot=0),
    R("R1", "5.1k", "CC1", "GND", 1, (84, 40), rot=0),
    R("R2", "5.1k", "CC2", "GND", 1, (98, 40), rot=0),
    dict(ref="D1", sym=("kicad", "Device", "D_TVS"), value="ESD5Z5.0T1G",
         fp="Diode_SMD:D_SOD-523", lcsc="C82044",
         desc="5 V unidirectional TVS (VBUS), SOD-523",
         nets={"1": "VBUS", "2": "GND"}, block=1, pos=(22, 40), rot=90),
    C("C1", "10uF25", "VBUS", "GND", 1, (34, 40)),
    dict(ref="U1", sym=("flashka", "TP4057"), value="TP4057",
         fp="Package_TO_SOT_SMD:SOT-23-6", lcsc="C12044",
         desc="TP4057-42-SOT26-R 500 mA Li-ion linear charger (R3 2.0k = ~500 mA)",
         nets={"1": "CHG_STAT", "2": "GND", "3": "VBAT", "4": "VBUS", "5": "CHG_DONE",
               "6": "PROG"},
         block=1, pos=(112, 92), rot=0),
    # charge control without a transistor: R3 returns PROG to GPIO20 (CHG_SET).
    # GPIO low = full current (~500 mA = 1000 x 1.0 V / R3); GPIO floating = 10 mA trickle through
    # R29 (so a flat cell still wakes up with no firmware running); GPIO high =
    # PROG pulled to 3.3 V = charger shut down (warm cell / turbo).
    R("R3", "2k", "PROG", "CHG_SET", 1, (128, 62), rot=90),
    R("R29", "100k", "CHG_SET", "GND", 1, (128, 112), rot=90),
    C("C2", "10uF", "VBAT", "GND", 1, (66, 40)),

    # ------------------------------------------------------------ block 3
    dict(ref="J2", sym=("kicad", "Connector_Generic", "Conn_01x02"), value="CELL",
         fp="FlashKa:WirePad_SMD_2_P3.0mm_24AWG", lcsc="",
         desc="cell wire pads BAT+ / BAT- (BATN): one 14500 cell, one 24 AWG wire per pad (room for two)",
         nets={"1": "VBAT", "2": "BATN"}, block=3, pos=(34, 196), rot=0, external=True),
    # v0.7: 1-cell protection in the cell minus (the cell has no protection board)
    dict(ref="U6", sym=("flashka", "DW01A"), value="DW01A",
         fp="Package_TO_SOT_SMD:SOT-23-6", lcsc="C351410",
         desc="1-cell Li-ion protection IC (PUOLOP DW01A): 4.30 V / 2.4 V, over-current 150 mV, SOT-23-6",
         nets={"1": "PROT_OD", "2": "PROT_CS", "3": "PROT_OC", "5": "PROT_VCC", "6": "BATN"},
         nc=["4"], block=3, pos=(40, 254), rot=0),
    dict(ref="Q3", sym=("flashka", "SE8830A"), value="SE8830A",
         fp="Package_TO_SOT_SMD:SOT-23-6", lcsc="C238645",
         desc="dual N-MOSFET 20 V common drain, 11/14.5 mOhm at 4.5 V, SOT-23-6 (SINO-IC SE8830A): "
              "Q3A discharge (S1 = cell minus), Q3B charge (S2 = board GND)",
         nets={"1": "BATN", "2": "PROT_D", "3": "GND", "4": "PROT_OC", "5": "PROT_D", "6": "PROT_OD"},
         block=3, pos=(40, 224), rot=0),
    R("R35", "100", "VBAT", "PROT_VCC", 3, (72, 240), rot=0),
    C("C24", "100nF", "PROT_VCC", "BATN", 3, (86, 240)),
    R("R36", "1k", "PROT_CS", "GND", 3, (100, 240), rot=0),
    dict(ref="U5", sym=("flashka", "RT9080"), value="RT9080-33GJ5",
         fp="Package_TO_SOT_SMD:TSOT-23-5", lcsc="C841192",
         desc="3.3 V 600 mA LDO, Iq 2 uA (EN tied to VIN)",
         nets={"1": "VBAT", "2": "GND", "3": "VBAT", "5": "3V3"}, nc=["4"],
         block=3, pos=(84, 196), rot=0),
    C("C14", "1uF", "VBAT", "GND", 3, (60, 176)),
    C("C15", "10uF", "3V3", "GND", 3, (110, 176)),
    C("C16", "100nF", "3V3", "GND", 3, (122, 176)),
    dict(ref="Q5", sym=("kicad", "Device", "Q_NMOS_GSD"), value="2N7002W",
         fp="Package_TO_SOT_SMD:SOT-323_SC-70", lcsc="C5224240",
         desc="VBUS-edge reset (SOT-323): pulls EN low for ~0.1 s when USB is plugged in",
         nets={"1": "RST_G", "2": "GND", "3": "EN"}, block=3, pos=(134, 254), rot=0),
    C("C17", "1uF", "VBUS", "RST_G", 3, (112, 250), rot=0),
    R("R7", "100k", "RST_G", "GND", 3, (122, 270), rot=90),

    # ------------------------------------------------------------ block 4
    dict(ref="U2", sym=("flashka", "TPS62095"), value="TPS62095RGTR",
         fp="FlashKa:VQFN-16-1EP_3x3mm_P0.5mm_EP1.68x1.68mm_TV2",
         lcsc="C139643", desc="4 A sync buck (TI TPS62095), 100 % duty mode, VFB 0.8 V, 1.4 MHz, VQFN-16 3x3 (RGT)",
         nets={"1": "SW", "2": "SW", "3": "VBAT", "5": "FB", "6": "GND", "7": "BUCK_CP", "8": "BUCK_CN",
               "10": "VBAT", "11": "VBAT", "12": "VBAT", "13": "LED_EN", "14": "GND", "15": "GND",
               "16": "VOUT", "17": "GND"},
         nc=["4", "9"], block=4, pos=(190, 70), rot=0),
    C("C5", "22uF6", "VBAT", "GND", 4, (166, 32)),
    C("C23", "10nF", "BUCK_CP", "BUCK_CN", 4, (220, 88)),
    R("R17", "100k", "LED_EN", "GND", 4, (158, 86), rot=0),
    dict(ref="L1", sym=("kicad", "Device", "L"), value="1uH", fp="Inductor_SMD:L_Changjiang_FNR4020S",
         lcsc="C602028", desc="1 uH 4x4 mm, Isat 11 A, 23 mOhm (cjiang FHD4020S-1R0MT)",
         nets={"1": "SW", "2": "VOUT"}, block=4, pos=(222, 30), rot=90),
    C("C8", "22uF6", "VOUT", "GND", 4, (236, 32)),
    C("C22", "22uF6", "VOUT", "GND", 4, (248, 32)),
    R("R10", "200k", "VOUT", "FB", 4, (228, 62), rot=0),
    R("R11", "100k", "FB", "GND", 4, (252, 70), rot=0),
    dict(ref="J3", sym=("kicad", "Connector_Generic", "Conn_01x02"), value="LED",
         fp="FlashKa:WirePad_LED_Split_24AWG", lcsc="",
         desc="LED wire pads (24 AWG to the DTP board): LED+ on the top side between the USB-C shell "
              "legs (pad 1), LED- on the bottom side behind the USB-C receptacle (pad 2)",
         nets={"1": "VOUT", "2": "ISNS"}, block=4, pos=(272, 34), rot=0, external=True),
    dict(ref="RS1", sym=("kicad", "Device", "R"), value="20mΩ", fp="Resistor_SMD:R_0805_2012Metric",
         lcsc="C92740", desc="20 mOhm 1 % 0.5 W 0805 current sense (Kelvin)",
         nets={"1": "ISNS", "2": "GND"}, block=4, pos=(270, 80), rot=0),
    dict(ref="Q2", sym=("kicad", "Device", "Q_NMOS_GSD"), value="2N7002W", fp="Package_TO_SOT_SMD:SOT-323_SC-70",
         lcsc="C5224240", desc="N-MOSFET current sink into FB (SOT-323)",
         nets={"1": "QG", "2": "QS", "3": "FB"}, block=4, pos=(232, 104), rot=0),
    R("R12", "47k", "QS", "GND", 4, (234, 128), rot=0),
    R("R13", "10k", "VC", "QG", 4, (204, 104), rot=90),
    dict(ref="U3", sym=("flashka", "OPAMP_DBV"), value="TLV333IDCKR", fp="Package_TO_SOT_SMD:SOT-353_SC-70-5",
         lcsc="C181502", desc="zero-drift op-amp SC-70-5 (DCK), powered from LED_EN",
         nets={"1": "VC", "2": "GND", "3": "VSET", "4": "INV", "5": "LED_EN"},
         block=4, pos=(190, 112), rot=0),
    C("C10", "100nF", "LED_EN", "GND", 4, (160, 112)),
    R("R14", "2.2k", "ISNS", "INV", 4, (258, 106), rot=90),
    C("C11", "10nF", "INV", "VC", 4, (212, 128), rot=90),
    R("R15", "100k", "LED_PWM", "VSET", 4, (164, 128), rot=90),
    R("R16", "2.2k", "VSET", "GND", 4, (182, 130), rot=0),
    C("C12", "1uF", "VSET", "GND", 4, (194, 130)),

    # ------------------------------------------------------------ block 5
    dict(ref="Q1", sym=("kicad", "Device", "Q_PMOS_GSD"), value="AO3401A", fp="Package_TO_SOT_SMD:SOT-23",
         lcsc="C15127", desc="P-MOSFET laser load switch",
         nets={"1": "QL_G", "2": "VBAT", "3": "LASER_P"}, block=5, pos=(232, 196), rot=0),
    R("R18", "10k", "QL_G", "VBAT", 5, (214, 176), rot=0),
    R("R19", "1k", "QL_G", "S2_COM", 5, (208, 206), rot=90),
    dict(ref="S2", sym=("kicad", "Switch", "SW_SPDT"), value="MSK12C02", fp="Button_Switch_SMD:SW_SPDT_PCM12",
         lcsc="C431540", desc="SPDT slide switch, laser interlock (gate path only)",
         nets={"1": "LASER_N", "2": "S2_COM", "3": "VBAT"}, block=5, pos=(186, 236), rot=0),
    dict(ref="Q4", sym=("kicad", "Device", "Q_NMOS_GSD"), value="2N7002W", fp="Package_TO_SOT_SMD:SOT-323_SC-70",
         lcsc="C5224240", desc="N-MOSFET (SOT-323): 3.3 V LASER_ON -> pulls the Q1 gate path low",
         nets={"1": "LASER_ON", "2": "GND", "3": "LASER_N"}, block=5, pos=(214, 258), rot=0),
    R("R20", "100k", "LASER_ON", "GND", 5, (190, 270), rot=0),
    C("C13", "10uF", "LASER_P", "GND", 5, (252, 222)),
    dict(ref="J5", sym=("kicad", "Connector_Generic", "Conn_01x02"), value="LASER",
         fp="FlashKa:WirePad_SMD_2_P3.0mm_N", lcsc="", desc="laser module wire pads (+ nearer the front, 28 AWG)",
         nets={"1": "LASER_P", "2": "GND"}, block=5, pos=(272, 200), rot=0, external=True),

    # ------------------------------------------------------------ block 6
    dict(ref="U4", sym=("flashka", "ESP32-C3-MINI-1"), value="ESP32-C3-MINI-1-N4",
         fp="FlashKa:ESP32-C3-MINI-1", lcsc="C2838502",
         desc="ESP32-C3 BLE 5 / Wi-Fi module, 4 MB flash, PCB antenna (alt. -H4X C41349510)",
         nets=dict({"3": "3V3", "8": "EN", "12": "VBAT_ADC", "13": "NTC_ADC", "5": "RGB_B",
                    "6": "BTN", "18": "CHG_STAT", "19": "CHG_DONE", "20": "LED_PWM",
                    "21": "LED_EN", "22": "RGB_G", "23": "BTN", "16": "LASER_ON",
                    "26": "USB_DN", "27": "USB_DP", "30": "CHG_SET", "31": "RGB_R"},
                   **{p: "GND" for p in MOD_GND}),
         nc=MOD_NC, block=6, pos=(350, 96), rot=0),
    R("R8", "10k", "3V3", "EN", 6, (304, 66), rot=90),
    C("C18", "1uF", "EN", "GND", 6, (316, 66)),
    R("R9", "10k", "3V3", "BTN", 6, (300, 40), rot=0),
    R("R21", "10k", "3V3", "RGB_G", 6, (312, 40), rot=0),
    R("R22", "10k", "3V3", "RGB_B", 6, (324, 40), rot=0),
    dict(ref="RT1", sym=("kicad", "Device", "Thermistor_NTC"), value="100k B4250",
         fp="Resistor_SMD:R_0402_1005Metric", lcsc="C77130",
         desc="NTC 100 k B25/50 4250 0402 (Murata NCP15WF104F03RC), PCB front edge",
         nets={"1": "NTC_ADC", "2": "GND"}, block=6, pos=(318, 128), rot=0),
    R("R26", "100k", "3V3", "NTC_ADC", 6, (304, 124), rot=0),
    C("C19", "100nF", "NTC_ADC", "GND", 6, (330, 128)),
    R("R27", "1M", "VBAT", "VBAT_ADC", 6, (378, 124), rot=0),
    R("R28", "1M", "VBAT_ADC", "GND", 6, (392, 124), rot=0),
    C("C20", "100nF", "VBAT_ADC", "GND", 6, (404, 128)),
    # v0.7: six ENIG target pads on the bottom face for the key board's pogo pins (no part)
    dict(ref="J6", sym=("kicad", "Connector_Generic", "Conn_01x06"), value="KB contacts",
         fp="FlashKa:PogoTarget_6_D1.6_FlashKa", lcsc="",
         desc="6 round ENIG target pads d1.6 (mask d1.8, no paste), bottom face, for pogo pins P1-P6",
         nets={"1": "GND", "2": "3V3", "3": "RGB_R", "4": "RGB_G", "5": "RGB_B", "6": "BTN"},
         block=6, pos=(400, 64), rot=0, external=True),

    # ------------------------------------------------------------ block 7 (key board)
    dict(ref="SW1", sym=("kicad", "Switch", "SW_Push"), value="SKRKAEE020",
         fp="Button_Switch_SMD:SW_Push_SPST_NO_Alps_SKRK",
         lcsc="C115357", desc="main button: Alps top-push tact switch, 1.6 N, KB bottom face (main key)",
         nets={"1": "BTN", "2": "GND"}, block=7, pos=(338, 162), rot=0, board="keys"),
    dict(ref="SW2", sym=("kicad", "Switch", "SW_Push"), value="SKRKAEE020",
         fp="Button_Switch_SMD:SW_Push_SPST_NO_Alps_SKRK",
         lcsc="C115357", desc="next button (>): Alps top-push tact switch, KB bottom face",
         nets={"1": "BTN_NX", "2": "GND"}, block=7, pos=(338, 174), rot=0, board="keys"),
    dict(ref="SW3", sym=("kicad", "Switch", "SW_Push"), value="SKRKAEE020",
         fp="Button_Switch_SMD:SW_Push_SPST_NO_Alps_SKRK",
         lcsc="C115357", desc="previous button (<): Alps top-push tact switch, KB bottom face",
         nets={"1": "BTN_PV", "2": "GND"}, block=7, pos=(338, 186), rot=0, board="keys"),
    R("R30", "1k", "BTN", "BTN_NX", 7, (376, 168), rot=90, board="keys"),
    R("R31", "2.2k", "BTN", "BTN_PV", 7, (376, 180), rot=90, board="keys"),
    dict(ref="LED3", sym=("kicad", "Device", "LED_ARGB"), value="NH-B1010RGBT-HF",
         fp="FlashKa:LED_RGB_1010_NH-B1010RGBT", lcsc="C2874113",
         desc="ring RGB LED 1x1 mm, common anode (pin 1), KB bottom face, shines into the clear main key",
         nets={"1": "3V3", "2": "R_K", "3": "G_K", "4": "B_K"}, block=7, pos=(334, 212), rot=0, board="keys"),
    dict(ref="LED4", sym=("kicad", "Device", "LED_ARGB"), value="NH-B1010RGBT-HF",
         fp="FlashKa:LED_RGB_1010_NH-B1010RGBT", lcsc="C2874113",
         desc="ring RGB LED 1x1 mm, common anode (pin 1), KB bottom face, shines into the clear main key",
         nets={"1": "3V3", "2": "R_K2", "3": "G_K2", "4": "B_K2"}, block=7, pos=(334, 238), rot=0, board="keys"),
    R("R23", "330", "R_K", "RGB_R", 7, (362, 222), rot=0, board="keys"),
    R("R24", "100", "G_K", "RGB_G", 7, (369.6, 222), rot=0, board="keys"),
    R("R25", "100", "B_K", "RGB_B", 7, (377.2, 222), rot=0, board="keys"),
    R("R32", "330", "R_K2", "RGB_R", 7, (384.8, 222), rot=0, board="keys"),
    R("R33", "100", "G_K2", "RGB_G", 7, (392.4, 222), rot=0, board="keys"),
    R("R34", "100", "B_K2", "RGB_B", 7, (400, 222), rot=0, board="keys"),
    # two M1.6 x 2.5 pan-head screws into tapped floor bosses hold the key board (no copper)
    dict(ref="H1", sym=("kicad", "Mechanical", "MountingHole"), value="M1.6",
         fp="FlashKa:MountingHole_1.8mm_M1.6", lcsc="", desc="mounting hole d1.8 (NPTH), M1.6 x 2.5 pan head",
         nets={}, block=7, pos=(386, 196), rot=0, board="keys", external=True),
    dict(ref="H2", sym=("kicad", "Mechanical", "MountingHole"), value="M1.6",
         fp="FlashKa:MountingHole_1.8mm_M1.6", lcsc="", desc="mounting hole d1.8 (NPTH), M1.6 x 2.5 pan head",
         nets={}, block=7, pos=(398, 196), rot=0, board="keys", external=True),
] + [
    # pogo pins on the KB top face; Pn presses on main-board pad J6.n (same net)
    dict(ref=f"P{n}", sym=("kicad", "Connector_Generic", "Conn_01x01"), value="P70-1010045R",
         fp="FlashKa:Pogo_Harwin_P70-1010045R", lcsc="C22100007",
         desc="SMT pogo pin, gold, no peg, free 5.0 / working 4.0 mm, 1.17 N (Harwin P70-1010045R), KB top face",
         nets={"1": net}, block=7, pos=(310, 160 + 6 * (n - 1)), rot=0, board="keys")
    for n, net in enumerate(("GND", "3V3", "RGB_R", "RGB_G", "RGB_B", "BTN"), start=1)
]

for _c in COMPONENTS:
    _c.setdefault("board", "main")

# parts that moved from the main board (v0.6) to the key board (v0.7)
MOVED_TO_KEYS = ("SW1", "SW2", "SW3", "LED3", "LED4", "R23", "R24", "R25", "R32", "R33", "R34",
                 "R30", "R31")
# the nets the pogo pins carry (J6.n <-> Pn)
POGO_NETS = ("GND", "3V3", "RGB_R", "RGB_G", "RGB_B", "BTN")

# key board interface (housing coordinates: X from the front face, Y across, Z up from the bottom
# face; mm).  Agreed with the housing (docs/ch14_v0.7_keys_and_skin.md, cad/housing_interface.json)
KB = {
    "outline": (13.4, -7.4, 32.4, 7.4),        # X0, Y0, X1, Y1
    "corner_r": 1.0,
    "thickness": 0.8,
    "z_bottom": 4.4, "z_top": 5.2,             # pogo working height 9.2 - 5.2 = 4.0
    "holes": ((22.9, 5.8), (22.9, -5.8)),      # M1.6 x 2.5 pan head into tapped floor bosses
    "hole_d": 1.8,
    "keepout_d": 3.8,                          # no parts and no copper, both faces
    # bottom face: floor support areas (no parts, no exposed pads)
    "floor_supports": ((15.2, 5.9, 16.6, 7.4), (15.2, -7.4, 16.6, -5.9),
                       (29.2, 5.9, 30.6, 7.4), (29.2, -7.4, 30.6, -5.9)),
    # top face: under the USB-C receptacle J1 parts <= 0.4 mm; cell wires at X > 29.5, Y < -1.0
    "j1_shadow": ((13.4, -7.4, 20.2, 0.9), 0.4),
    "cell_wires": ((29.5, -7.4, 32.4, -1.0), 1.0),
    # bottom-face parts fixed by the keys: (X, Y, KiCad rotation on the bottom face)
    #   SW rot 0 = pads along X, rot 90 = pads along Y
    "bottom": {"SW1": (22.9, 0.0, 0), "SW2": (15.9, 0.0, 90), "SW3": (29.9, 0.0, 90),
               "LED3": (22.9, 2.4, 0), "LED4": (22.9, -2.4, 0)},
    # pogo pins (KB top face) = J6 pads (main-board bottom face), same X/Y
    "pogo": (("P1", 15.0, 2.5), ("P2", 17.8, 2.5), ("P3", 20.6, 2.5),
             ("P4", 25.0, 2.5), ("P5", 27.8, 2.5), ("P6", 30.6, 2.5)),
    "pogo_heights": {"free": 5.0, "working": 4.0, "max_working": 4.2, "min_working": 3.7,
                     "solid": 3.5, "force_n": 1.17, "force_tol_n": 0.29},
}

# off-board items listed in the BOM but not on the main PCB
EXTERNAL_BOM = [
    ("D2", "Luminus SST-20-W Gen 2, 6500 K, G1 bin, on 10 mm DTP copper board", "", "bought ready-made"),
    ("BT1", "1 x Vapcell INR14500 F15 3.6 V 1500 mAh Li-ion (3 A, flat top, no protection board), "
            "nickel strips spot-welded; alt. Vapcell INR14500 K10 1000 mAh (8 A)", "", "bought (shop)"),
    ("LS1", "6 x 12 mm laser module with driver, 3 V", "", "bought (AliExpress)"),
]

# ESP32-C3 GPIO map (firmware/src/board.rs mirrors this)
GPIO_MAP = {
    0: "VBAT_ADC (ADC1_CH0, 1M/1M divider)",
    1: "NTC_ADC (ADC1_CH1, 100k NTC to GND, 100k to 3V3)",
    2: "RGB_B (low = on, 10k pull-up: strap must read 1; both ring LEDs)",
    3: "BTN ladder (ADC1_CH3; none 3.30 V, main 0 V, </> together 0.212 V, > next 0.300 V, < prev 0.595 V) - tied to GPIO9",
    4: "CHG_STAT (TP4057 CHRG, open drain, low = charging)",
    5: "CHG_DONE (TP4057 STDBY, open drain, low = full)",
    6: "LED_PWM (LEDC 13-bit, 9.8 kHz -> RC filter -> current set point)",
    7: "LED_EN (high = LED driver + op-amp on, 100k pull-down)",
    8: "RGB_G (low = on, 10k pull-up: strap must read 1 for download mode)",
    9: "BTN (digital: any button = low; BOOT strap: held low at reset = ROM download mode)",
    10: "LASER_ON (high = laser on if S2 is armed, 100k pull-down)",
    18: "USB D- (native USB serial/JTAG)",
    19: "USB D+",
    20: "CHG_SET (U0RXD; low = charge ~500 mA, floating = 10 mA trickle, high = charger off)",
    21: "RGB_R (U0TXD; low = on; boot log makes it flicker at reset)",
}


def on_board(board, components=None):
    """the components of one board ("main" or "keys")"""
    return [c for c in (COMPONENTS if components is None else components) if c["board"] == board]


def nets_of(components=COMPONENTS):
    """net name -> list of (ref, pin)"""
    out = {}
    for c in components:
        for pin, net in c["nets"].items():
            out.setdefault(net, []).append((c["ref"], pin))
    return out


if __name__ == "__main__":
    n = nets_of()
    for k in sorted(n):
        print(f"{k:12s} {len(n[k]):2d}  " + " ".join(f"{r}.{p}" for r, p in n[k]))
    print(len(COMPONENTS), "components,", len(n), "nets;",
          ", ".join(f"{b}: {len(on_board(b))}" for b in BOARDS))
