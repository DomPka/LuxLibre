# SPDX-License-Identifier: GPL-3.0-or-later
"""
Aurora++ v0.5 - single source of truth for the electronics capture.

Every component of the main PCB with: symbol, footprint, value, LCSC number,
pin -> net map, schematic block and schematic position.  The schematic, the
PCB, the BOM, the CPL file and the netlist check are all generated from this
table.

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
  TLV62585DRL      1 GND, 2 SW, 3 VIN, 4 EN, 5 FB, 6 NC
  TLV333 (DCK)     1 OUT, 2 V-, 3 +IN, 4 -IN, 5 V+
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


def R(ref, val, n1, n2, block, pos, rot=90, dnp=False):
    shown = val + "Ω" if val[-1].isdigit() else val
    return dict(ref=ref, sym=("kicad", "Device", "R"), value=shown,
                fp=R0402, lcsc=RES[val], desc=f"{val} 1% 0402 resistor",
                nets={"1": n1, "2": n2}, block=block, pos=pos, rot=rot, dnp=dnp)


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
    6: "Block 6: ESP32-C3-MINI-1 (BLE, USB), button, RGB LED, NTC, VBAT sense",
}

# block frames on the A3 sheet (x0, y0, x1, y1) in mm, KiCad page coordinates
FRAMES = {
    1: (12, 18, 148, 150),
    3: (12, 156, 148, 284),
    4: (152, 18, 288, 150),
    5: (152, 156, 288, 284),
    6: (292, 18, 410, 252),
}

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
    dict(ref="U1", sym=("aurora", "TP4057"), value="TP4057",
         fp="Package_TO_SOT_SMD:SOT-23-6", lcsc="C12044",
         desc="TP4057-42-SOT26-R 500 mA Li-ion linear charger (R3 3.3k = ~300 mA)",
         nets={"1": "CHG_STAT", "2": "GND", "3": "VBAT", "4": "VBUS", "5": "CHG_DONE",
               "6": "PROG"},
         block=1, pos=(112, 92), rot=0),
    # charge control without a transistor: R3 returns PROG to GPIO20 (CHG_SET).
    # GPIO low = full current (~300 mA); GPIO floating = 10 mA trickle through
    # R29 (so a flat cell still wakes up with no firmware running); GPIO high =
    # PROG pulled to 3.3 V = charger shut down (warm cell / turbo).
    R("R3", "3.3k", "PROG", "CHG_SET", 1, (128, 62), rot=90),
    R("R29", "100k", "CHG_SET", "GND", 1, (128, 112), rot=90),
    C("C2", "10uF", "VBAT", "GND", 1, (66, 40)),

    # ------------------------------------------------------------ block 3
    dict(ref="J2", sym=("kicad", "Connector_Generic", "Conn_01x02"), value="CELL",
         fp="Aurora:WirePad_SMD_2_P3.0mm", lcsc="", desc="cell wire pads BAT+/BAT- (2 cells in parallel: 2 wires per pad)",
         nets={"1": "VBAT", "2": "GND"}, block=3, pos=(34, 200), rot=0, external=True),
    dict(ref="U5", sym=("aurora", "RT9080"), value="RT9080-33GJ5",
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
         nets={"1": "RST_G", "2": "GND", "3": "EN"}, block=3, pos=(96, 250), rot=0),
    C("C17", "1uF", "VBUS", "RST_G", 3, (66, 238), rot=0),
    R("R7", "100k", "RST_G", "GND", 3, (78, 262), rot=90),

    # ------------------------------------------------------------ block 4
    dict(ref="U2", sym=("aurora", "TLV62585DRL"), value="TLV62585DRLR", fp="Package_TO_SOT_SMD:SOT-563",
         lcsc="C485117", desc="3 A sync buck, 100 % duty mode, SOT-563",
         nets={"1": "GND", "2": "SW", "3": "VBAT", "4": "LED_EN", "5": "FB"},
         nc=["6"], block=4, pos=(190, 74), rot=0),
    C("C5", "22uF6", "VBAT", "GND", 4, (164, 38)),
    C("C7", "100nF", "VBAT", "GND", 4, (180, 38)),
    R("R17", "100k", "LED_EN", "GND", 4, (160, 78), rot=0),
    dict(ref="L1", sym=("kicad", "Device", "L"), value="1uH", fp="Inductor_SMD:L_Changjiang_FNR4020S",
         lcsc="C602028", desc="1 uH 4x4 mm, Isat 11 A, 23 mOhm (cjiang FHD4020S-1R0MT)",
         nets={"1": "SW", "2": "VOUT"}, block=4, pos=(212, 36), rot=90),
    C("C8", "22uF6", "VOUT", "GND", 4, (232, 38)),
    R("R10", "200k", "VOUT", "FB", 4, (244, 38), rot=0),
    C("C9", "22pF", "VOUT", "FB", 4, (256, 38)),
    R("R11", "100k", "FB", "GND", 4, (244, 78), rot=0),
    dict(ref="J3", sym=("kicad", "Connector_Generic", "Conn_01x02"), value="LED",
         fp="Aurora:WirePad_SMD_TopBottom_1.6x1.8", lcsc="", desc="LED wire pads: LED+ top side, LED- bottom side (28 AWG PTFE to the DTP board)",
         nets={"1": "VOUT", "2": "ISNS"}, block=4, pos=(272, 40), rot=0, external=True),
    dict(ref="RS1", sym=("kicad", "Device", "R"), value="20mΩ", fp="Resistor_SMD:R_0805_2012Metric",
         lcsc="C92740", desc="20 mOhm 1 % 0.5 W 0805 current sense (Kelvin)",
         nets={"1": "ISNS", "2": "GND"}, block=4, pos=(270, 80), rot=0),
    dict(ref="Q2", sym=("kicad", "Device", "Q_NMOS_GSD"), value="2N7002W", fp="Package_TO_SOT_SMD:SOT-323_SC-70",
         lcsc="C5224240", desc="N-MOSFET current sink into FB (SOT-323)",
         nets={"1": "QG", "2": "QS", "3": "FB"}, block=4, pos=(232, 104), rot=0),
    R("R12", "47k", "QS", "GND", 4, (234, 128), rot=0),
    R("R13", "10k", "VC", "QG", 4, (204, 104), rot=90),
    dict(ref="U3", sym=("aurora", "OPAMP_DBV"), value="TLV333IDCKR", fp="Package_TO_SOT_SMD:SOT-353_SC-70-5",
         lcsc="C181502", desc="zero-drift op-amp SC-70-5 (DCK), powered from LED_EN",
         nets={"1": "VC", "2": "GND", "3": "VSET", "4": "INV", "5": "LED_EN"},
         block=4, pos=(190, 112), rot=0),
    C("C10", "100nF", "LED_EN", "GND", 4, (160, 112)),
    R("R14", "2.2k", "ISNS", "INV", 4, (258, 106), rot=90),
    C("C11", "10nF", "INV", "VC", 4, (212, 128), rot=90),
    R("R15", "100k", "LED_PWM", "VSET", 4, (164, 128), rot=90),
    R("R16", "2k", "VSET", "GND", 4, (182, 130), rot=0),
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
         fp="Aurora:WirePad_SMD_2_P2.54mm", lcsc="", desc="laser module wire pads",
         nets={"1": "LASER_P", "2": "GND"}, block=5, pos=(272, 200), rot=0, external=True),

    # ------------------------------------------------------------ block 6
    dict(ref="U4", sym=("aurora", "ESP32-C3-MINI-1"), value="ESP32-C3-MINI-1-N4",
         fp="Aurora:ESP32-C3-MINI-1", lcsc="C2838502",
         desc="ESP32-C3 BLE 5 / Wi-Fi module, 4 MB flash, PCB antenna (alt. -H4X C41349510)",
         nets=dict({"3": "3V3", "8": "EN", "12": "VBAT_ADC", "13": "NTC_ADC", "5": "RGB_B",
                    "6": "BTN", "18": "CHG_STAT", "19": "CHG_DONE", "20": "LED_PWM",
                    "21": "LED_EN", "22": "RGB_G", "23": "BTN", "16": "LASER_ON",
                    "26": "USB_DN", "27": "USB_DP", "30": "CHG_SET", "31": "RGB_R"},
                   **{p: "GND" for p in MOD_GND}),
         nc=MOD_NC, block=6, pos=(350, 104), rot=0),
    R("R8", "10k", "3V3", "EN", 6, (304, 176), rot=90),
    C("C18", "1uF", "EN", "GND", 6, (316, 176)),
    R("R9", "10k", "3V3", "BTN", 6, (300, 40), rot=0),
    R("R21", "10k", "3V3", "RGB_G", 6, (312, 40), rot=0),
    R("R22", "10k", "3V3", "RGB_B", 6, (324, 40), rot=0),
    dict(ref="S1", sym=("kicad", "Switch", "SW_Push"), value="SKRTLAE010",
         fp="Button_Switch_SMD:SW_Push_1P1T-MP_NO_Horizontal_Alps_SKRTLAE010",
         lcsc="C110293", desc="side-push tact switch (Alps)",
         nets={"1": "BTN", "2": "GND"}, block=6, pos=(306, 214), rot=0),
    dict(ref="LED3", sym=("kicad", "Device", "LED_ARGB"), value="NH-B1010RGBT-HF",
         fp="Aurora:LED_RGB_1010_NH-B1010RGBT", lcsc="C2874113",
         desc="RGB LED 1x1 mm, common anode (pin 1)",
         nets={"1": "3V3", "2": "R_K", "3": "G_K", "4": "B_K"}, block=6, pos=(350, 194), rot=0),
    R("R23", "1k", "R_K", "RGB_R", 6, (392, 182), rot=90),
    R("R24", "100", "G_K", "RGB_G", 6, (392, 194), rot=90),
    R("R25", "100", "B_K", "RGB_B", 6, (392, 206), rot=90),
    dict(ref="RT1", sym=("kicad", "Device", "Thermistor_NTC"), value="100k B4250",
         fp="Resistor_SMD:R_0402_1005Metric", lcsc="C77130",
         desc="NTC 100 k B25/50 4250 0402 (Murata NCP15WF104F03RC), PCB front edge",
         nets={"1": "NTC_ADC", "2": "GND"}, block=6, pos=(318, 232), rot=0),
    R("R26", "100k", "3V3", "NTC_ADC", 6, (304, 226), rot=0),
    C("C19", "100nF", "NTC_ADC", "GND", 6, (330, 232)),
    R("R27", "1M", "VBAT", "VBAT_ADC", 6, (350, 222), rot=0),
    R("R28", "1M", "VBAT_ADC", "GND", 6, (366, 236), rot=0),
    C("C20", "100nF", "VBAT_ADC", "GND", 6, (380, 236)),
]

# off-board items listed in the BOM but not on the main PCB
EXTERNAL_BOM = [
    ("D2", "Luminus SST-20-W on 10 mm DTP copper board", "", "bought ready-made (AliExpress)"),
    ("BT1", "2 x LP601646 3.7 V LiPo with PCM and leads, in parallel", "", "bought (AliExpress)"),
    ("LS1", "6 x 12 mm laser module with driver, 3 V", "", "bought (AliExpress)"),
]

# ESP32-C3 GPIO map (firmware/src/board.rs mirrors this)
GPIO_MAP = {
    0: "VBAT_ADC (ADC1_CH0, 1M/1M divider)",
    1: "NTC_ADC (ADC1_CH1, 100k NTC to GND, 100k to 3V3)",
    2: "RGB_B (low = on, 10k pull-up: strap must read 1)",
    3: "BTN (low = pressed, wakes from sleep) - tied to GPIO9",
    4: "CHG_STAT (TP4057 CHRG, open drain, low = charging)",
    5: "CHG_DONE (TP4057 STDBY, open drain, low = full)",
    6: "LED_PWM (LEDC 13-bit, 9.8 kHz -> RC filter -> current set point)",
    7: "LED_EN (high = LED driver + op-amp on, 100k pull-down)",
    8: "RGB_G (low = on, 10k pull-up: strap must read 1 for download mode)",
    9: "BTN (BOOT strap: held low at reset = ROM download mode)",
    10: "LASER_ON (high = laser on if S2 is armed, 100k pull-down)",
    18: "USB D- (native USB serial/JTAG)",
    19: "USB D+",
    20: "CHG_SET (U0RXD; low = charge ~300 mA, floating = 10 mA trickle, high = charger off)",
    21: "RGB_R (U0TXD; low = on; boot log makes it flicker at reset)",
}


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
    print(len(COMPONENTS), "components,", len(n), "nets")
