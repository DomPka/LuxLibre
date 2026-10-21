#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""FlashKa Keychain v0.6 - complete bill of materials and cost workbook.

    python3 tools/parts_list.py [out.xlsx] [--no-recalc] [--check-only]

Writes FlashKa_Parts_List_v0.6.xlsx (8 sheets: Summary, JLCPCB order, Main PCB BOM,
Housing, Bought parts, Hidden costs, Tools, Ordering checklist), recalculates it with
LibreOffice so that every formula has a cached value, then re-opens the file and checks it:

  * no #REF!/#VALUE!/#NAME?/#DIV/0!/#N/A cells
  * every total in the workbook equals an independent Python calculation (model())
  * every LCSC number of COMPONENTS is in the BOM sheet with the right quantity and designators; the BOM
    sheet is line by line identical to tools/kicad/build_all.py bom() AND to production/BOM_JLCPCB.csv
    (= order_files/1_JLCPCB/BOM_JLCPCB.csv); its designators are the ones of production/CPL_JLCPCB.csv; the
    solder-joint count of every line is the pad count of its footprint in the routed board
  * the print kit is consistent: its parts are the ones tools/housing/flashka_housing.py puts on the sprues,
    its STL volume covers them, and no part is ordered both inside the kit and as a separate print
  * every file of ORDER_FILES exists in order_files/ and every order_files/ path in the workbook text is one of them,
    and no text points to a file location or a name from before the rename
  * the housing JSON and the STL files come from the same build (volumes agree within 1 %), and the sizes written
    into texts (pad cuts, lid height) are those of the geometry
  * docs/bom_notes.md names the input cells (quotes, switches, shipping) at their right addresses

Sources of truth
  electronics   tools/kicad/flashka_parts.py (COMPONENTS, EXTERNAL_BOM); the BOM is derived here with
                the same grouping as build_all.bom() (build_all.py itself is NOT run: it re-routes the PCB)
  housing       cad/housing_interface.json (version 0.6: volumes, tray bounding box, PCB outline, skin layout,
                wall checks) and the cad/*.stl files (bounding boxes; volume of the print kit and of the laser
                sleeve, which the JSON does not list); falls back to the snapshot embedded below when the JSON
                is not found
  ordering      JLCCNC gets tray, lid, cap_main (1 per light) and cap_slide (2 per light), each as STEP + PDF;
                JLC3DP gets ONE part, cad/FlashKa_print_kit.stl (RF window insert, spacer ring, antenna spacer,
                light-pipe tube, resin main cap and two resin slide caps on 1 mm sprues): one kit per light +
                one spare kit; the seven parts stay as information rows (quantity 0)
  file names    every upload instruction names the ready-to-upload folder of the package:
                order_files/1_JLCPCB/, order_files/2_JLCCNC/, order_files/3_JLC3DP/ (see ORDER_FILES; the names
                are those of the files that exist there, verify() checks it)
  prices        read from the vendor pages (see bom_notes.md and the Source columns). v0.6 keeps the v0.5
                readings that did not change (date V05_DATE); what could not be read on CHECK (the JLCPCB and
                LCSC pages of the new parts could not be read) is a labelled ESTIMATE (blue number on amber)

Colour code in the workbook: blue = typed-in number (change it), blue on amber = ESTIMATE (no public
price - replace by a real quote), black = formula, green = taken from another sheet.
"""
import ast
import csv
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from collections import Counter

from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "kicad"))
from flashka_parts import COMPONENTS, EXTERNAL_BOM  # noqa: E402

V05_DATE = "2026-10-14"       # v0.5 price check: every price, fee and stock figure that did not change keeps this date
CHECK = "2026-10-18"          # v0.6 price check: new parts and housing estimates (the JLCPCB / LCSC pages of the new parts could not be read)
RESEARCH_DATE = "2026-10-16"  # day the JLCCNC / JLC3DP pages and the Alps switch pages were read for v0.6 (v0.6 parts research)
FX_DATE = "2026-10-13"        # ECB reference rate date (not refreshed in v0.6)

# ----------------------------------------------------------------------------------------------
# source URLs (every fee/price in the workbook carries one of these and the date it was read)
# ----------------------------------------------------------------------------------------------
U_FEES = "https://jlcpcb.com/help/article/pcb-assembly-price"
U_FAQ2 = "https://jlcpcb.com/help/article/pcb-assembly-faqs-part-2"
U_PANEL = "https://jlcpcb.com/help/article/Panelizing-your-PCB-for-Assembly"
U_ASM = "https://jlcpcb.com/pcb-assembly"
U_QUOTE = "https://cart.jlcpcb.com/quote"
U_CAPAB = "https://jlcpcb.com/capabilities/pcb-capabilities"
U_VAT = "https://jlcpcb.com/help/article/EU-VAT-E-commerce-Rules-%26-Adjustments"
U_CUST = "https://jlcpcb.com/help/article/eu-customs-reform-faq"
U_EC = "https://trade.ec.europa.eu/access-to-markets/en/news/eu-applies-eu3-customs-duty-item-low-value-e-commerce-consignments"
U_ECB = ("https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/"
         "eurofxref-graph-usd.en.html")
U_CHIP = "https://chiptron.eu/jlcpcb-reduces-shipping-costs-pcb-order-with-shipping-worth-bad-beer/"
U_EEV = "https://eevblog.com/forum/manufacture/jlcpcb-pcb-assembly-optimal-shipping-for-eu"
U_PCBSYNC = "https://pcbsync.com/pcb-prototype-services-compared/"
U_GHI = "https://forums.ghielectronics.com/t/enig-or-hasl-for-pcb-finish/23438"
U_BASIC = "https://jlcpcb.com/parts/basic_parts"
U_JLCNC = "https://jlccnc.com/cnc-machining-quote"
U_JLCNC_HOME = "https://jlccnc.com/"
U_JLCNC_CAP = "https://jlccnc.com/capabilities/cnc-machining-service"
U_JLCNC_ORD = "https://jlccnc.com/help/article/cnc-machining-ordering-guidelines"
U_JLCNC_FIN = "https://jlccnc.com/finishes"
U_JLCNC_SS = "https://jlccnc.com/cnc-machining"
U_JLCNC_TURN = "https://jlccnc.com/cnc-machining-service/cnc-turning"
U_JLCNC_COST = "https://jlccnc.com/blog/cnc-machining-cost-factors"
U_3DP = "https://jlc3dp.com/3d-printing-quote"
U_3DP_HOME = "https://jlc3dp.com/"
U_3DP_8001 = "https://jlc3dp.com/help/article/photosensitive-8001-resin"
U_3DP_BUILD = "https://jlc3dp.com/help/article/1219-What-is-the-build-time-of-the-3D-printing-parts"
U_3DP_EU = "https://jlc3dp.com/news/eu-customs-reform2026"
U_LASER = "https://en.wikipedia.org/wiki/Laser_safety"
U_EN50689 = "https://ul.com/insights/understand-new-laser-product-safety-standards-europe"
LCSC_URL = "https://www.lcsc.com/product-detail/{}.html"
JLC_PART_URL = "https://jlcpcb.com/partdetail/{}"
ALI_ITEM = "https://www.aliexpress.com/item/{}.html"
ALI_SEARCH = "https://www.aliexpress.com/wholesale?SearchText={}"

# ----------------------------------------------------------------------------------------------
# styles (same look as the v0.4 generator: Arial, blue typed-in numbers, check date, LCSC links)
# ----------------------------------------------------------------------------------------------
ARIAL = "Arial"
HEAD = Font(name=ARIAL, bold=True, color="FFFFFF")
BODY = Font(name=ARIAL, size=10)
INPUT = Font(name=ARIAL, size=10, color="0000FF")          # typed-in numbers (blue)
XREF = Font(name=ARIAL, size=10, color="008000")           # taken from another sheet (green)
BOLD = Font(name=ARIAL, size=10, bold=True)
BIG = Font(name=ARIAL, size=14, bold=True)
SMALL = Font(name=ARIAL, size=9, color="555555")
LINK = Font(name=ARIAL, size=10, color="1F5FBF", underline="single")
FILL = PatternFill("solid", fgColor="2F4A66")
SUB = PatternFill("solid", fgColor="DCE6F0")
WARN = PatternFill("solid", fgColor="FFF2CC")              # estimates / things to check
TOTAL = PatternFill("solid", fgColor="E2EFDA")
thin = Side(style="thin", color="B0B7C0")
BOX = Border(left=thin, right=thin, top=thin, bottom=thin)
USD2 = '"$"#,##0.00'
USD4 = '"$"#,##0.0000'
EUR2 = '"€"#,##0.00'
INT0 = '#,##0'
PCT1 = '0.0%'

# ----------------------------------------------------------------------------------------------
# LCSC data (price tiers = (min qty, USD per piece), "stock" = LCSC retail stock). Every line was read on V05_DATE
# (the v0.5 price check) and is unchanged in v0.6, except the lines with est=True: C115357 and C25104 are new in v0.6
# and their JLCPCB and LCSC pages could not be read on CHECK, so their tiers, stock and type are ESTIMATES (see "note").
# type = JLCPCB library type read on https://jlcpcb.com/partdetail/<LCSC> ("Preferred" is not shown there;
# it only matters for the Economic PCBA service, which cannot do double-sided boards); type_est = not read.
# read = date the tiers were read; pads = solder joints of the part (JLC counts joints/pads; verify() compares them
# with the pads of the routed board); cls = placement-loss class (see ATTRITION)
# ----------------------------------------------------------------------------------------------
LCSC_DATA = {
    "C15850": dict(mpn="CL21A106KAYNNNE", mfr="Samsung Electro-Mechanics", type="Basic", stock=20, pads=2, cls="p0603",
                   tiers=[(20, .0695), (200, .0513), (600, .0419), (2000, .0342), (10000, .0315), (20000, .0297)],
                   role="Smoothing capacitor on the USB 5 V input (25 V rating needed).",
                   note="LOW: only 20 pcs at LCSC retail; JLC's own stock is separate - the BOM upload flags a shortage. "
                        "Any 10 uF 25 V X5R 0805 Basic part is a substitute."),
    "C19702": dict(mpn="CL10A106KP8NNNC", mfr="Samsung Electro-Mechanics", type="Basic", stock=181020, pads=2, cls="p0603",
                   tiers=[(20, .0311), (200, .023), (600, .0195), (4000, .0168), (8000, .0157), (20000, .015)],
                   role="10 uF capacitors that smooth the supply next to the chips (C2, C13, C15).", note=""),
    "C59461": dict(mpn="CL10A226MQ8NRNC", mfr="Samsung Electro-Mechanics", type="Basic", stock=4416440, pads=2, cls="p0603",
                   tiers=[(20, .0315), (200, .0236), (600, .0201), (4000, .0174), (8000, .0164), (20000, .0157)],
                   role="22 uF capacitors for the buck converter / power rails (C5, C8).", note=""),
    "C1555": dict(mpn="0402CG220J500NT", mfr="FH", type="Basic", stock=798400, pads=2, cls="p0402",
                  tiers=[(100, .0027), (1000, .002), (3000, .0017), (10000, .0014), (50000, .0012)],
                  role="22 pF feed-forward capacitor in the LED-driver loop (C9).", note=""),
    "C15195": dict(mpn="CL05B103KB5NNNC", mfr="Samsung Electro-Mechanics", type="Basic", stock=0, pads=2, cls="p0402",
                   tiers=[(100, .005), (1000, .0038), (3000, .0033), (10000, .0029), (50000, .0028), (100000, .0027)],
                   role="10 nF capacitor (C11, filter in the LED-current loop).",
                   note="LCSC retail shows OUT OF STOCK; JLC lists it as Basic and has its own warehouse - the BOM upload "
                        "shows the real JLC stock. If flagged, pick another Basic 10 nF 0402 and update flashka_parts.py."),
    "C52923": dict(mpn="CL05A105KA5NQNC", mfr="Samsung Electro-Mechanics", type="Basic", stock=598000, pads=2, cls="p0402",
                   tiers=[(50, .0085), (500, .0067), (1500, .0059), (10000, .0053), (20000, .005), (50000, .0049)],
                   role="1 uF 25 V capacitors for supply decoupling (C12, C14, C17, C18).", note=""),
    "C1525": dict(mpn="CL05B104KO5NNNC", mfr="Samsung Electro-Mechanics", type="Basic", stock=0, pads=2, cls="p0402",
                  tiers=[(100, .0046), (1000, .0035), (3000, .003), (10000, .0026), (50000, .0025), (100000, .0024)],
                  role="100 nF capacitors: one next to each chip's supply pin (C7, C10, C16, C19, C20).",
                  note="LCSC retail shows OUT OF STOCK, but the JLC basic-parts list shows 23,496,493 pcs (read "
                       + V05_DATE + "), so JLC can assemble it."),
    "C82044": dict(mpn="ESD5Z5.0T1G", mfr="onsemi", type="Extended", stock=370780, pads=2, cls="semi",
                   tiers=[(20, .0371), (200, .029), (600, .0245), (3000, .0204), (9000, .0181), (21000, .0168)],
                   role="D1: protects the board from static / voltage spikes on the USB 5 V line.", note=""),
    "C165948": dict(mpn="TYPE-C-31-M-12", mfr="Korean Hroparts Elec", type="Extended", stock=375745, pads=20, cls="mod",
                    tiers=[(5, .1729), (50, .1365), (150, .1187), (1000, .0963), (2000, .092), (5000, .0894)],
                    role="J1: USB-C socket (charging and data). 16 signal pads + 4 shell legs = 20 joints.", note=""),
    "C602028": dict(mpn="FHD4020S-1R0MT", mfr="cjiang", type="Extended", stock=8210, pads=2, cls="mod",
                    tiers=[(10, .1102), (100, .086), (300, .0726), (3000, .0645), (6000, .0575), (9000, .0538)],
                    role="L1: 1 uH power inductor of the buck converter U2 (LED driver).", note=""),
    "C2874113": dict(mpn="NH-B1010RGBT-HF", mfr="NATIONSTAR", type="Extended", stock=345020, pads=4, cls="semi",
                     tiers=[(20, .0081), (200, .0072), (600, .0068), (2000, .0065), (10000, .0063), (20000, .0053)],
                     role="LED3, LED4: the two RGB ring LEDs (1 x 1 mm, 4 pads under the package) that light the ring around the main button.", note=""),
    "C15127": dict(mpn="AO3401A", mfr="AOS", type="Basic", stock=164910, pads=3, cls="semi",
                   tiers=[(5, .1026), (50, .0829), (150, .0728), (500, .0644), (3000, .0615), (6000, .0596)],
                   role="Q1: P-channel MOSFET, the on/off switch of the laser.", note=""),
    "C5224240": dict(mpn="2N7002W-7-F-ES", mfr="ElecSuper", type="Extended", stock=17000, pads=3, cls="semi",
                     tiers=[(50, .0224), (500, .017), (3000, .0141), (6000, .0123), (24000, .0108), (51000, .0099)],
                     role="Q2, Q4, Q5: small N-channel MOSFET switches (LED current sink, laser gate, reset pulse).",
                     note=""),
    "C25905": dict(mpn="0402WGF5101TCE", mfr="UNI-ROYAL", type="Basic", stock=2302500, pads=2, cls="p0402",
                   tiers=[(100, .0024), (1000, .0019), (3000, .0015), (10000, .0014), (50000, .0012)],
                   role="R1, R2: 5.1 k resistors on the USB-C CC pins (tell a charger to supply 5 V).", note=""),
    "C25890": dict(mpn="0402WGF3301TCE", mfr="UNI-ROYAL", type="Basic", stock=867600, pads=2, cls="p0402",
                   tiers=[(100, .0036), (1000, .0027), (3000, .0023), (10000, .002), (50000, .0018)],
                   role="R3: 3.3 k resistor, sets the battery charge current (about 280 mA).", note=""),
    "C25764": dict(mpn="0402WGF2003TCE", mfr="UNI-ROYAL", type="Basic", stock=1520700, pads=2, cls="p0402",
                   tiers=[(100, .0018), (1000, .0014), (3000, .0011), (10000, .001), (50000, .0009)],
                   role="R10: 200 k resistor (voltage divider of the buck converter).", note=""),
    "C25792": dict(mpn="0402WGF4702TCE", mfr="UNI-ROYAL", type="Basic", stock=3114700, pads=2, cls="p0402",
                   tiers=[(100, .0026), (1000, .002), (3000, .0017), (10000, .0015), (50000, .0013)],
                   role="R12: 47 k resistor.", note=""),
    "C25744": dict(mpn="0402WGF1002TCE", mfr="UNI-ROYAL", type="Basic", stock=2846900, pads=2, cls="p0402",
                   tiers=[(100, .0033), (1000, .0026), (3000, .0022), (10000, .0021), (50000, .0017)],
                   role="10 k resistors: pull-ups / pull-downs (R8, R9, R13, R18, R21, R22).", note=""),
    "C25879": dict(mpn="0402WGF2201TCE", mfr="UNI-ROYAL", type="Basic", stock=586000, pads=2, cls="p0402",
                   tiers=[(100, .0018), (1000, .0013), (3000, .0011), (50000, .0009)],
                   role="R14: 2.2 k resistor (LED-current loop). R31: 2.2 k resistor of the button ladder (previous button).", note=""),
    "C4109": dict(mpn="0402WGF2001TCE", mfr="UNI-ROYAL", type="Basic", stock=5789500, pads=2, cls="p0402",
                  tiers=[(100, .0026), (1000, .002), (3000, .0016), (10000, .0015), (50000, .0012)],
                  role="R16: 2 k resistor.", note=""),
    "C11702": dict(mpn="0402WGF1001TCE", mfr="UNI-ROYAL", type="Basic", stock=0, pads=2, cls="p0402",
                   tiers=[(100, .0031), (1000, .0024), (3000, .002), (10000, .0018), (50000, .0016)],
                   role="R19: 1 k resistor (laser gate). R30: 1 k resistor of the button ladder (next button).",
                   note="LCSC retail shows OUT OF STOCK; JLC lists it as Basic - check the JLC stock at BOM upload."),
    "C25076": dict(mpn="0402WGF1000TCE", mfr="UNI-ROYAL", type="Basic", stock=4360400, pads=2, cls="p0402",
                   tiers=[(100, .0013), (1000, .001), (3000, .0009), (10000, .0008)],
                   role="R24, R25, R33, R34: 100 ohm resistors (green and blue leg of each ring LED).", note=""),
    "C26083": dict(mpn="0402WGF1004TCE", mfr="UNI-ROYAL", type="Basic", stock=541000, pads=2, cls="p0402",
                   tiers=[(100, .0024), (1000, .0018), (3000, .0016), (10000, .0014), (50000, .0011)],
                   role="R27, R28: 1 M resistors.", note=""),
    "C25741": dict(mpn="0402WGF1003TCE", mfr="UNI-ROYAL", type="Basic", stock=3791500, pads=2, cls="p0402",
                   tiers=[(100, .0015), (1000, .0012), (3000, .001), (10000, .0009), (50000, .0008)],
                   role="100 k resistors: pull-ups / dividers (7 of them).", note=""),
    "C92740": dict(mpn="MS05W2F200MT5E", mfr="UNI-ROYAL", type="Extended", stock=4880, pads=2, cls="p0603",
                   tiers=[(20, .0183), (200, .018), (600, .0177), (2000, .0174)],
                   role="RS1: 20 milliohm current-sense resistor (measures the LED current).", note=""),
    "C77130": dict(mpn="NCP15WF104F03RC", mfr="muRata", type="Extended", stock=298120, pads=2, cls="p0402",
                   tiers=[(20, .0219), (200, .0173), (600, .0147), (2000, .0132), (10000, .0119), (20000, .0112)],
                   role="RT1: 100 k NTC thermistor = temperature sensor at the front edge of the PCB.", note=""),
    # --- new in v0.6 (S1 = C110293 SKRTLAE010 is gone). The JLCPCB part page and the LCSC page of both numbers could not
    #     be read on CHECK: ESTIMATE lines.
    "C115357": dict(mpn="SKRKAEE020", mfr="ALPSALPINE", type="Extended", type_est=True, stock=None, pads=2, cls="mod", est=True, read=CHECK,
                    tiers=[(10, .0759), (100, .0616)],
                    role="SW1, SW2, SW3: the three push buttons (main, next, previous). Alps top-push tact switch 3.9 x 2.9 x 2.0 mm, 1.6 N, 200k cycles, on the bottom side.",
                    note="ESTIMATE, page not read: JLCPCB and LCSC pages of C115357 could not be read on " + CHECK + ". Tiers = the sibling Alps SKRPABE010 "
                         "(C115360) read on LCSC on " + RESEARCH_DATE + " (qty 10 $0.0759, qty 100 $0.0616). Stock unknown. Library type 'Extended' assumed "
                         "(every Alps tact switch checked on JLCPCB is Extended).",
                    src="ESTIMATE - LCSC and JLCPCB pages of C115357 could not be read on " + CHECK + ". Tiers of the sibling C115360 (LCSC, read "
                        + RESEARCH_DATE + "): qty 10 $0.0759, qty 100 $0.0616."),
    "C25104": dict(mpn="0402WGF3300TCE", mfr="UNI-ROYAL", type="Basic", type_est=True, stock=None, pads=2, cls="p0402", est=True, read=CHECK,
                   tiers=[(100, .0024), (1000, .0019), (3000, .0015), (10000, .0014), (50000, .0012)],
                   role="R23, R32: 330 ohm resistors (red leg of the two ring LEDs).",
                   note="ESTIMATE, page not read: JLCPCB and LCSC pages of C25104 could not be read on " + CHECK + ". Tiers copied from the sibling 5.1 k resistor "
                        "C25905 (read " + V05_DATE + "); part number inferred from the UNI-ROYAL naming; library type 'Basic' assumed (same series as the other "
                        "Basic 0402 resistors). Stock unknown.",
                   src="ESTIMATE - LCSC and JLCPCB pages of C25104 could not be read on " + CHECK + ". Tiers of the sibling C25905 (LCSC, read " + V05_DATE + ")."),
    "C431540": dict(mpn="MSK12C02", mfr="SHOU HAN", type="Extended", stock=170330, pads=7, cls="mod",
                    tiers=[(10, .0543), (100, .0444), (300, .0394), (3000, .0337), (6000, .0323), (9000, .0312)],
                    role="S2: slide switch = the laser safety interlock.", note=""),
    "C12044": dict(mpn="TP4057-42-SOT26-R", mfr="TOP POWER ASIC", type="Extended", stock=32025, pads=6, cls="semi",
                   tiers=[(5, .1426), (50, .1166), (150, .1036), (500, .0938), (3000, .0761), (6000, .0722)],
                   role="U1: battery charger chip (500 mA linear Li-ion charger).", note=""),
    "C485117": dict(mpn="TLV62585DRLR", mfr="Texas Instruments", type="Extended", stock=925, pads=6, cls="semi",
                    tiers=[(5, .261), (50, .2052), (150, .178), (500, .1537), (3000, .147), (6000, .143)],
                    role="U2: 3 A buck converter that drives the LED.",
                    note="LOW stock at LCSC (925 pcs) - fine for 5 boards, check at BOM upload."),
    "C181502": dict(mpn="TLV333IDCKR", mfr="Texas Instruments", type="Extended", stock=18425, pads=5, cls="semi",
                    tiers=[(5, .3543), (50, .2788), (150, .2465), (500, .1927), (3000, .1747), (6000, .1639)],
                    role="U3: precision op-amp in the LED-current control loop.", note=""),
    "C2838502": dict(mpn="ESP32-C3-MINI-1-N4", mfr="Espressif", type="Extended", stock=8387, pads=53, cls="mod",
                     tiers=[(1, 3.0672), (10, 2.7002), (30, 2.5127), (100, 2.1441), (650, 2.0536), (1300, 2.0141)],
                     role="U4: the brain - ESP32-C3 module with Bluetooth LE / Wi-Fi, 4 MB flash and antenna.",
                     note="Marked NRND (not recommended for new designs) by Espressif; the successor ESP32-C3-MINI-1-H4X "
                          "(C41349510) is the drop-in alternative if this one disappears."),
    "C841192": dict(mpn="RT9080-33GJ5", mfr="Richtek", type="Extended", stock=27375, pads=5, cls="semi",
                    tiers=[(5, .1207), (50, .0982), (150, .087), (500, .0786), (3000, .0613), (6000, .058)],
                    role="U5: 3.3 V voltage regulator for the ESP32 module.", note=""),
}
# placement-loss classes: JLC buys a few more pieces than the boards need (they are billed inside the component
# price and discarded). JLC publishes no table; these numbers are ESTIMATES in the style of typical JLC quotes.
ATTRITION = [("p0402", 10, "0402 resistors / capacitors / NTC (tiny, easily lost by the pick-and-place machine)"),
             ("p0603", 5, "0603 and 0805 capacitors, current-sense resistor"),
             ("semi", 2, "small semiconductors: MOSFETs, ICs, TVS diode, RGB LED"),
             ("mod", 1, "big or expensive parts: ESP32 module, USB-C socket, inductor, switches")]
# solder joints per footprint (checked against the routed board by verify()): U4 53 pads (the footprint draws the exposed
# pad 49 as 10 pieces: 62 pad shapes), J1 16 signal pads + 4 shell legs, S2 7, U2 6, U1 6, U3 5, U5 5, LED3/LED4 4,
# Q1/Q2/Q4/Q5 3, SW1-SW3 2, everything else 2. J2/J3/J5 are wire pads (no LCSC number, not assembled).

for _d in LCSC_DATA.values():
    _d.setdefault("read", V05_DATE)       # date the tiers and the stock were read
    _d.setdefault("est", False)           # True = ESTIMATE (page not read)
    _d.setdefault("type_est", False)      # True = library type assumed, not read
    _d.setdefault("src", "")              # price source text of an ESTIMATE line

# ----------------------------------------------------------------------------------------------
# housing snapshot (cad/housing_interface.json of the v0.6 housing build) - used only when that file cannot be found
# ----------------------------------------------------------------------------------------------
HOUSING_DIR = "cad"
HOUSING_SNAPSHOT = {
    "volumes_mm3": {"FlashKa_tray": 8401.2, "FlashKa_lid": 2643.3, "FlashKa_rf_window": 184.1, "FlashKa_tube": 178.1,
                    "FlashKa_cap_main": 108.9, "FlashKa_cap_slide": 40.0, "FlashKa_spacer_ring": 83.9,
                    "FlashKa_antenna_spacer": 926.8},
    "mass_g": {"FlashKa_tray": 22.68, "FlashKa_lid": 7.14, "FlashKa_rf_window": 0.21, "FlashKa_tube": 0.2,
               "FlashKa_cap_main": 0.86, "FlashKa_cap_slide": 0.32, "FlashKa_spacer_ring": 0.1,
               "FlashKa_antenna_spacer": 1.07},
    "tray_bbox": [-0.0033966036196133686, 94.4083680440771, -10.00455267570433, 10.00385386049766,
                  -0.008368044077099413, 16.00385386049766],
    "pcb_outline": [[10.100000000000001, -8.25], [32.8, -8.25], [32.8, 8.25], [10.100000000000001, 8.25],
                    [8.8, 6.95], [8.8, -6.95]],
    "derived": {"Z_lid": 14.5},
    "params": {"W": 20.0, "H": 16.0, "R_edge": 2.0, "lid_t": 1.5, "win_d": 10.0, "ring_od": 10.1, "ring_id": 7.2,
               "las_d": 6.0, "las_len": 12.0, "m16_tap": 1.25, "m2_tap": 1.6, "lan_slot_w": 4.4, "lan_slot_len": 7.6,
               "rfw_flange": 0.8, "rfw_flange_t": 0.6, "rfw_flange_drop": 0.2, "tube_od": 8.4, "tube_rim": [8.8, 1.1, 1.5],
               "main_hole": 8.45, "slide_hole": 3.6, "main_cap": [5.8, 6.6, 0.6, 3.0], "slide_cap": [3.4, 5.0, 0.6, 2.0],
               "boss_box": [22.1, 30.9, -7.6, 4.8], "boss2_box": [15.65, 19.35, 0.05, 3.25], "pad_t0": 1.0, "pad2_t0": 1.0},
    # the three thinnest metal walls of min_walls (for the JLCCNC wall note) and the metal under the thinnest seam groove
    "min_walls": {"LED wire groove (top) to lid seat": 0.8, "front screw tap to head rear face": 0.875,
                  "lid around the RF window flange pocket": 0.9},
    "skin_min_metal_under_mm": 1.11,
}
# V-groove length added by the v0.6 skin (mm, the lid-front V-ring excluded: it exists in v0.5 too), see skin_lengths()
SKIN_SNAPSHOT = {"tray": 646.5, "lid": 220.2}
# min_walls entries that are air gaps or the 0.2 mm radial seat of the tube rim (a step in a 1.5 mm floor), not metal walls
WALL_NOT_METAL = ("laser module top below the PCB", "tube body to the +Y trough wall (gap, not a wall)",
                  "floor: counterbore ledge (radial, rim seat)")

# facts of the finished v0.5 housing (housing script parameters knurl_* and sgroove_* of the v0.5 package; its
# estimate in the v0.5 workbook): used for the "removed" lines of the fine-feature table in sheet 'Housing'
V05_GEOM = dict(
    feat_tray=36.0, feat_lid=8.0,           # fine-feature minutes of the v0.5 estimate (one lump per part)
    knurl_mm=717.0,                         # diamond knurl 41 x 12.4 mm, pitch 1.6: 613 mm of lines + 103 mm border, per face (floor and lid)
    side_groove_mm=164.0,                   # 4 side grooves (2 per side, Z 5.5 and 10.5), 41 mm each
)

# totals of the v0.5 cost workbook (sheet 'Summary', price check 2026-10-14, exchange rate 1.1188) in USD:
# only used by the "what changed from v0.5" group of the Summary. A = 1 light, B = 5 lights (the same scenarios as in v0.6).
V05_SUMMARY = {
    "A": dict(pcb=169.309736586, house=65.9595627902, parts=56.75, cons=18.29, tax=219.32326265268, total=529.63256202888, per=529.63256202888),
    "B": dict(pcb=196.671591465, house=225.397813951, parts=211.3, cons=18.29, tax=329.894924957896, total=981.554330373896, per=196.310866074779),
}


def thinnest_walls(H, n=3):
    """[(mm, what), ...] the n thinnest metal walls listed in housing_interface.json (min_walls + the metal under the seam grooves)."""
    w = dict(H.get("min_walls", {}))
    w.update(H.get("texture_walls", {}))
    if isinstance(H.get("skin_min_metal_under_mm"), (int, float)):
        w["metal under the thinnest seam groove"] = H["skin_min_metal_under_mm"]
    return sorted((v, k) for k, v in w.items() if k not in WALL_NOT_METAL and isinstance(v, (int, float)))[:n]


# bounding boxes and volumes measured from cad/*.stl (binary STL) on CHECK, mm (x, y, z) and mm3 - rounded like
# load_housing() rounds them. The JSON has no volume for the print kit and the laser sleeve: theirs come from here.
STL_SNAPSHOT = {
    "FlashKa_tray": (94.40, 20.00, 16.00, 8401.4), "FlashKa_lid": (90.20, 20.00, 5.20, 2643.1),
    "FlashKa_rf_window": (8.40, 15.50, 1.70, 184.1), "FlashKa_tube": (8.80, 8.80, 8.20, 178.0),
    "FlashKa_cap_main": (6.60, 6.60, 7.00, 108.7), "FlashKa_cap_slide": (5.00, 5.00, 7.00, 40.0),
    "FlashKa_spacer_ring": (2.40, 10.10, 10.10, 83.9), "FlashKa_antenna_spacer": (6.00, 16.80, 14.15, 926.8),
    "FlashKa_laser_sleeve": (10.00, 6.00, 5.97, 110.9), "FlashKa_print_kit": (57.20, 16.80, 14.15, 1576.2),
}
HOUSING_KEYS = ("FlashKa_tray", "FlashKa_lid", "FlashKa_rf_window", "FlashKa_tube", "FlashKa_cap_main", "FlashKa_cap_slide",
                "FlashKa_spacer_ring", "FlashKa_antenna_spacer")
# the seven resin parts that tools/housing/flashka_housing.py joins with 1 mm sprues into FlashKa_print_kit, in the order they
# sit on the sprues (side by side along X); the two slide caps are the same part twice
PRINT_KIT_KEYS = ("FlashKa_rf_window", "FlashKa_spacer_ring", "FlashKa_antenna_spacer", "FlashKa_tube",
                  "FlashKa_cap_main", "FlashKa_cap_slide", "FlashKa_cap_slide")
# names of the entries in the build_print_kit(...) call of flashka_housing.py -> part (verify() reads that call with ast)
KIT_SCRIPT_NAMES = {"rf_window": "FlashKa_rf_window", "spacer_ring": "FlashKa_spacer_ring",
                    "antenna_spacer": "FlashKa_antenna_spacer", "tube": "FlashKa_tube", "cap_main_resin": "FlashKa_cap_main",
                    "cap_slide_resin_1": "FlashKa_cap_slide", "cap_slide_resin_2": "FlashKa_cap_slide"}
PAD_CAN_MM = (8.8, 12.4)     # hold-down pad cut from the 1.0 mm thermal gap pad (module can boss, params 'boss_box'); verify() compares
PAD_FRONT_MM = (3.7, 3.2)    # hold-down pad cut from the 1.0 mm rubber sheet (front boss, params 'boss2_box')
LID_HEIGHT_MM = 5.2          # lid height (hold-down bosses included) written into texts; verify() compares it with cad/FlashKa_lid.stl
RESIN_DENS = 1.15e-3     # g per mm3, the resin density flashka_housing.py uses for mass_g (for parts the JSON does not list)
STEEL_DENS = 7.93e-3     # g per mm3, SUS304

# ready-to-upload folder of the delivered package (these files exist in order_files/; verify() checks it):
# (folder, file name in the folder, where the packaging step takes it from). Upload instructions use ofp()/ofd().
ORDER_FILES = [
    ("1_JLCPCB", "FlashKa_main_gerbers.zip", "production/FlashKa_main_gerbers.zip (written by tools/kicad/build_all.py)"),
    ("1_JLCPCB", "BOM_JLCPCB.csv", "production/BOM_JLCPCB.csv"),
    ("1_JLCPCB", "CPL_JLCPCB.csv", "production/CPL_JLCPCB.csv"),
    ("2_JLCCNC", "FlashKa_tray.step", "cad/FlashKa_tray.step"),
    ("2_JLCCNC", "FlashKa_tray.pdf", "cad/FlashKa_tray_drawing.pdf (2 sheets), copied under the STEP name"),
    ("2_JLCCNC", "FlashKa_lid.step", "cad/FlashKa_lid.step"),
    ("2_JLCCNC", "FlashKa_lid.pdf", "cad/FlashKa_lid_drawing.pdf, copied under the STEP name"),
    ("2_JLCCNC", "FlashKa_cap_main.step", "cad/FlashKa_cap_main.step (turned part, axis through the origin)"),
    ("2_JLCCNC", "FlashKa_cap_main.pdf", "cad/FlashKa_cap_main_drawing.pdf, copied under the STEP name"),
    ("2_JLCCNC", "FlashKa_cap_slide.step", "cad/FlashKa_cap_slide.step (turned part, axis through the origin)"),
    ("2_JLCCNC", "FlashKa_cap_slide.pdf", "cad/FlashKa_cap_slide_drawing.pdf, copied under the STEP name"),
    ("2_JLCCNC", "FlashKa_marking_lid_class2.dxf", "cad/FlashKa_marking_lid_class2.dxf (laser marking of the lid, Class 2 laser)"),
    ("2_JLCCNC", "FlashKa_marking_lid_class3R.dxf", "cad/FlashKa_marking_lid_class3R.dxf (laser marking of the lid, only for a module above 1 mW)"),
    ("2_JLCCNC", "FlashKa_marking_bottom.dxf", "cad/FlashKa_marking_bottom.dxf (laser marking of the bottom face)"),
    ("2_JLCCNC", "FlashKa_marking_minus_y.dxf", "cad/FlashKa_marking_minus_y.dxf (laser marking of the -Y side, USB-C side)"),
    ("2_JLCCNC", "FlashKa_marking_plus_y.dxf", "cad/FlashKa_marking_plus_y.dxf (laser marking of the +Y side, S2 side)"),
    ("3_JLC3DP", "FlashKa_print_kit.stl", "cad/FlashKa_print_kit.stl"),
    ("3_JLC3DP", "FlashKa_laser_sleeve.stl", "cad/FlashKa_laser_sleeve.stl (optional, only for a 4.5 mm laser)"),
]


def ofd(folder):
    """'order_files/<folder>/' for a folder of ORDER_FILES."""
    if not any(f == folder for f, _, _ in ORDER_FILES):
        raise KeyError("no order_files folder " + folder)
    return "order_files/%s/" % folder


def ofp(name):
    """Full path of an upload file inside order_files/ (KeyError for a name that is not in ORDER_FILES)."""
    for f, n, _ in ORDER_FILES:
        if n == name:
            return ofd(f) + n
    raise KeyError("no order file " + name)


def stl_bbox_volume(path):
    """(dx, dy, dz, volume) of a binary or ASCII STL, or None."""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return None
    tris = []
    if len(data) >= 84 and 84 + 50 * struct.unpack("<I", data[80:84])[0] == len(data):
        n = struct.unpack("<I", data[80:84])[0]
        for i in range(n):
            v = struct.unpack("<12fH", data[84 + 50 * i:134 + 50 * i])
            tris.append((v[3:6], v[6:9], v[9:12]))
    else:
        nums = re.findall(rb"vertex\s+(\S+)\s+(\S+)\s+(\S+)", data)
        pts = [tuple(float(x) for x in t) for t in nums]
        tris = [tuple(pts[i:i + 3]) for i in range(0, len(pts) - 2, 3)]
    if not tris:
        return None
    xs = [p[0] for t in tris for p in t]
    ys = [p[1] for t in tris for p in t]
    zs = [p[2] for t in tris for p in t]
    vol = 0.0
    for a, b, c in tris:
        vol += (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0])
                + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6.0
    return (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs), abs(vol))


def load_housing():
    """Return (data dict, source text, stl dict) of the v0.6 housing: cad/housing_interface.json and cad/*.stl.

    The embedded snapshot is used only when the JSON is missing, incomplete or not version 0.6 (or, per file, when an STL
    is missing; the source text then names the files that came from the snapshot)."""
    d = os.path.join(REPO, HOUSING_DIR)
    p = os.path.join(d, "housing_interface.json")
    try:
        with open(p) as f:
            j = json.load(f)
        why = "incomplete or not version 0.6"
    except (OSError, ValueError):
        j, why = None, "not found"
    if j is not None and str(j.get("version")) == "0.6" and all(k in j.get("volumes_mm3", {}) for k in HOUSING_KEYS) \
            and "tray_bbox" in j and "pcb_outline" in j and "skin_layout" in j and "params" in j:
        stl, from_snapshot = {}, []
        for k in STL_SNAPSHOT:
            r = stl_bbox_volume(os.path.join(d, k + ".stl"))
            if r:
                stl[k] = tuple(round(x, 2) if i < 3 else round(x, 1) for i, x in enumerate(r))
            else:
                stl[k] = STL_SNAPSHOT[k]
                from_snapshot.append(k + ".stl")
        src = "%s/housing_interface.json (version %s) + %s/*.stl" % (HOUSING_DIR, j.get("version", "?"), HOUSING_DIR)
        if from_snapshot:
            src += " (embedded snapshot used for the missing %s)" % ", ".join(from_snapshot)
        return j, src, stl
    return (HOUSING_SNAPSHOT, "embedded snapshot of %s/housing_interface.json and %s/*.stl (the JSON was %s)" % (HOUSING_DIR, HOUSING_DIR, why),
            dict(STL_SNAPSHOT))


def skin_lengths(H):
    """(tray_mm, lid_mm): length of the V-grooves of the v0.6 skin cut into the tray and into the lid.

    Source: 'skin_layout' of housing_interface.json (19 grooves: 11 frame pieces, 8 stringers). The V ring at the lid's front
    edge is not counted: v0.5 had it too (it is inside the v0.5 lump). A stringer on the lid face belongs to the lid, every
    other stringer to the tray. A frame runs along the apex loop of the cross-section (s = 0 at the top centre, then round the
    +Y side, the bottom and the -Y side, total length 'tot'); the part of it that lies on the lid (flat top, the two corner
    arcs and the 0.6 mm lip down the sides, up to Z 'lid_lip_z') is cut into the lid, the rest into the tray."""
    lay = H.get("skin_layout")
    par = H.get("params", {})
    if not lay or "skin_depth" not in par:
        return SKIN_SNAPSHOT["tray"], SKIN_SNAPSHOT["lid"]
    d = par["skin_depth"]
    hw, hh, r = par["W"] / 2 - d, par["H"] / 2 - d, par["R_edge"] - d
    tot = 4 * (hw - r) + 4 * (hh - r) + 2 * math.pi * r
    z_arc0 = par["H"] - d - r                                   # Z where the corner arc meets the side wall
    half_lid = (hw - r) + math.pi / 2 * r + max(0.0, z_arc0 - par["lid_lip_z"])
    all_len = lid_len = 0.0
    for it in lay:
        if it["kind"] == "frame":
            all_len += it["s1"] - it["s0"]
            for k in (0, 1, 2):
                lid_len += max(0.0, min(it["s1"], k * tot + half_lid) - max(it["s0"], k * tot - half_lid))
        else:
            ln = math.dist(it["a"], it["b"])
            all_len += ln
            if it.get("face") == "top":
                lid_len += ln
    return all_len - lid_len, lid_len


def holddown_note(H):
    """Risk text about the two silicone hold-down pads; the lift numbers are read from 'holddown' of housing_interface.json."""
    head = "HOLD-DOWN PADS: the two silicone pads (sheet 'Bought parts') are not in the kit. "
    hd = H.get("holddown") or {}
    btn = hd.get("buttons") or {}
    par = H.get("params", {})
    vals = []
    for key, lab in (("SW1 main", "SW1"), ("SW2 next", "SW2"), ("SW3 previous", "SW3")):
        v = (btn.get(key) or {}).get("displacement_10N_mm")
        if isinstance(v, (int, float)):
            vals.append((lab, v))
    if not vals:
        return head + "The housing report calculates how far the board lifts under a 10 N press; a firmer rubber under a button that lifts too far helps."
    lim = hd.get("lift_limit_mm", 0.05)
    over = [lab for lab, v in vals if v > lim + 1e-9]
    txt = head + "The housing calculation (cad/housing_interface.json, 'holddown') gives a board lift at 10 N of %s against a limit of %.2f mm" \
        % (", ".join("%.3f mm (%s)" % (v, lab) for lab, v in vals), lim)
    if "pad_E_mpa" in par and "pad2_E_mpa" in par:
        txt += ", with assumed pad moduli of %.1f MPa (thermal pad) and %.1f MPa (rubber sheet)" % (par["pad_E_mpa"], par["pad2_E_mpa"])
    txt += ". "
    if over:
        txt += "%s %s above the limit in that calculation: a firmer pad under the button that lifts too far helps. " % (", ".join(over), "is" if len(over) == 1 else "are")
    return txt + "Real boards are stiffer than the plate model."


def feature_rows(H):
    """Fine-feature table of the aluminium parts (sheet 'Housing', section 4), v0.5 lump -> v0.6.

    (id, label, kind, tray, lid, note); kind 'min' = minutes of machining, 'mm' = millimetres of V-groove, which cost
    groove_min_m minutes per metre (the same rate for the groove lines that are removed and the ones that are added)."""
    t_skin, l_skin = skin_lengths(H)
    return [
        ("lump", "v0.5 fine-feature time (one lump per part, from the v0.5 workbook)", "min", V05_GEOM["feat_tray"], V05_GEOM["feat_lid"],
         "Tray 36 min = diamond knurl on the bottom, four side grooves, V ring at the lid seam, thumb dish, lanyard slot and the holes. "
         "Lid 8 min = four countersunk holes, RF-window pocket and the knurl panel. Unchanged v0.5 ESTIMATE."),
        ("knurl", "minus the v0.5 diamond knurl (V-groove lines)", "mm", -V05_GEOM["knurl_mm"], -V05_GEOM["knurl_mm"],
         "Knurl 41 x 12.4 mm, pitch 1.6 mm = 613 mm of lines + 103 mm of border = 717 mm on the tray bottom and 717 mm on the lid. Gone in v0.6."),
        ("sgroove", "minus the four v0.5 side grooves", "mm", -V05_GEOM["side_groove_mm"], 0.0,
         "2 per side x 2 sides x 41 mm. Gone in v0.6 (the side stringers of the skin take their place)."),
        ("skin", "plus the v0.6 skin seams (frames and stringers, V 90 deg, 0.25 deep)", "mm", round(t_skin, 1), round(l_skin, 1),
         "Length of the 19 entries of 'skin_layout' in housing_interface.json (6 frames in 11 pieces, 8 stringers): frames wrap round the section, so the lid "
         "takes only the part on its top, corners and 0.6 mm lip, plus the two top stringers; the rest is in the tray. The V ring at the lid front "
         "(v0.5 too) stays in the lump."),
        ("holes", "plus the floor holes: main bore 8.45 with counterbore 8.85, two slide holes 3.6 with 0.2 mm chamfer", "min", 3.0, 0.0,
         "3 stepped or chamfered holes, about 1 min each (new in v0.6: the push buttons are on the bottom face)."),
        ("rfwin", "plus the floor RF window 5.1 x 14.0 mm (through the 1.5 mm floor)", "min", 1.0, 0.0,
         "Rounded-rectangle opening, closed by the plug of the antenna spacer."),
        ("rabbet", "plus the 0.6 mm lid rabbet and the 0.3 mm gussets in the cavity corners", "min", 1.5, 1.0,
         "Contour pass round the opening of the tray (about 190 mm) and the lip on the underside of the lid, so that the skin seams cross the joint on the flat side."),
        ("bosses", "plus the two hold-down bosses under the lid (8.8 x 12.4 x 1.3 and 3.7 x 3.2 x 3.7 mm)", "min", 0.0, 1.5,
         "The lid is now a 5.2 mm tall part: the bulk removal is in 'material to remove', the small contours of the bosses are fine work."),
        ("s1", "minus the S1 hole, thumb dish and ledge gap (S1 is removed)", "min", -2.0, 0.0,
         "Side-button features of v0.5 that no longer exist."),
    ]


# ----------------------------------------------------------------------------------------------
# BOM derivation - same grouping and ordering as tools/kicad/build_all.py bom()
# ----------------------------------------------------------------------------------------------
def refkey(s):
    p = s.rstrip("0123456789")
    return (p, int("0" + s[len(p):]))


def derive_bom():
    """Group COMPONENTS by (value, footprint, LCSC); skip parts without LCSC number and DNP parts."""
    groups = {}
    for r in COMPONENTS:
        if not r["lcsc"] or r.get("dnp"):
            continue
        groups.setdefault((r["value"], r["fp"].split(":")[1], r["lcsc"]), []).append(r)
    lines = []
    for (val, fpn, lcsc), rs in sorted(groups.items(), key=lambda kv: refkey(kv[1][0]["ref"])):
        refs = sorted((x["ref"] for x in rs), key=refkey)
        d = LCSC_DATA[lcsc]
        descs = {x["desc"] for x in rs}
        desc = rs[0]["desc"] if len(descs) == 1 else "; ".join(
            "%s: %s" % (x["ref"], x["desc"]) for x in sorted(rs, key=lambda q: refkey(q["ref"])))
        lines.append(dict(value=val, fp=fpn, lcsc=lcsc, refs=refs, qty=len(refs), desc=desc, **d))
    return lines


def not_assembled():
    return [r for r in COMPONENTS if not r["lcsc"] or r.get("dnp")]


# ----------------------------------------------------------------------------------------------
# typed-in parameters. v = value, u = unit, src = URL, d = date read, e = True for an ESTIMATE, n = note
# ----------------------------------------------------------------------------------------------
def prm(v, u="", src="", d=V05_DATE, e=False, n=""):
    """d defaults to V05_DATE: a fee or estimate that v0.6 keeps unchanged carries the date and source it had in v0.5."""
    return dict(v=v, u=u, src=src, d=d, e=e, n=n)


P = {
    # --- global
    "fx": prm(1.1188, "USD per EUR", U_ECB, FX_DATE, n="ECB euro reference rate of 13 Oct 2026. Change it to the rate of your bank/card."),
    "lightsA": prm(1, "lights", "", "", n="Scenario A: you build one light."),
    "lightsB": prm(5, "lights", "", "", n="Scenario B: you build five lights (all JLC minimums are used up)."),
    "min_asm": prm(2, "boards", U_ASM, n="JLCPCB assembles from 2 boards; one light therefore still pays for 2 assembled boards (1 spare)."),
    "min_pcb": prm(5, "boards", U_QUOTE, n="JLCPCB sells at least 5 bare boards per design."),
    "sides": prm(2, "sides", "", "", n="Parts are on both sides of the board = double-sided Standard PCBA (Economic PCBA is single-sided only)."),
    # --- JLCPCB Standard PCBA fees (2026 price page "Last updated on Sep 09, 2026")
    "setup_side": prm(25.56, "USD per side", U_FEES, n="Standard PCBA set-up fee: $25.56 single-sided / $51.12 double-sided. Covers the engineering check (no separate engineering fee)."),
    "stencil_side": prm(8.21, "USD per side", U_FEES, n="Standard PCBA stencil: $8.21 single-sided / $16.42 double-sided."),
    "smt_joint": prm(0.0016, "USD per joint", U_FEES, n="SMT assembly price per solder joint (1-50,000 joints)."),
    "feeder_unique": prm(1.53, "USD per unique part", U_FEES, n="Feeder loading, Standard PCBA: $1.53 for every unique part number, Basic and Extended alike (no separate engineering fee and no separate extended-part fee)."),
    "ext_extra": prm(0.0, "USD per unique Extended part", U_FEES, n="Only Economic PCBA charges an extra $3.07 per Extended part. In Standard PCBA (this order) every unique part, Basic or Extended, pays the same feeder-loading fee instead, so there is no separate extended-part fee. Type 3.00 here to test the effect of such a fee."),
    "eng_fee": prm(0.0, "USD per order", U_FEES, n="No separate engineering fee on the 2026 page; the set-up fee covers it."),
    "confirm": prm(0.45, "USD per order", U_FEES, n="'Confirm parts placement': JLC sends a photo of the placement for your OK. Strongly recommended for a first order."),
    "xray_per_board": prm(3, "parts per board", U_FEES, V05_DATE, n="Fee page: 'X-ray inspection is required for components such as BGA, QFN and other leadless packages', charged per component. The COUNT is a v0.6 assumption (the fee page itself was not re-read in v0.6): v0.6 budgets the three parts of this board with hidden joints: U4 (ESP32 module, pads under it), LED3 and LED4 (pads under the package) = 3 per board (v0.5: 2, there was one ring LED). Set 0 if your cart does not ask for it."),
    "panel_board": prm(0.46, "USD per board", U_PANEL, n="JLC panelises small boards for assembly; page quotes a minimum processing cost of $0.46 per board. ASSUMED to apply (24 x 16.5 mm is a small board)."),
    "pack_base": prm(0.50, "USD per order", U_FEES, n="Packing, Standard PCBA: $0.50 + $0.00003 per cm2 of board."),
    "pack_cm2": prm(0.00003, "USD per cm2", U_FEES, n="See above (negligible for a 4 cm2 board)."),
    "hand_labour": prm(3.58, "USD per order", U_FEES, n="Hand-soldering labour. Not needed: no through-hole parts. Quantity 0."),
    "prereflow": prm(0.016, "USD per joint", U_FEES, n="Row 'pre-reflow soldering' on the fee page, not explained there. Quantity 0 - check your quote."),
    "single_board": prm(0.48, "USD per order", U_FEES, n="Single-board surcharge; prototypes are exempt. Quantity 0."),
    "fixture": prm(8.21, "USD per fixture", U_FEES, n="Test/assembly fixture (minimum 2). Not needed. Quantity 0."),
    "storage": prm(4.93, "USD per item", U_FEES, n="Stencil or fixture storage. Not needed. Quantity 0."),
    "large": prm(57.46, "USD per order", U_FEES, n="Large-size surcharge for boards above 650 cm2. Not applicable (board is 24 x 16.5 mm). Quantity 0."),
    # --- bare PCB (price only shown after the Gerber upload)
    "pcb_fab5": prm(25.0, "USD for 5 boards", U_QUOTE, e=True, n="ESTIMATE. JLCPCB shows the price only after the Gerber upload. Anchors: 100 x 100 mm 4-layer x 5 is about $32.90 (pcbsync, Jul 2026); ENIG adds roughly $12-20 on small runs; 0.8 mm is a normal thickness; 24 x 16.5 mm is far smaller than 100 x 100 mm."),
    "pcb_fab_low": prm(12.0, "USD for 5 boards", "", e=True, n="Optimistic end of the estimate range (information only)."),
    "pcb_fab_high": prm(40.0, "USD for 5 boards", "", e=True, n="Pessimistic end of the estimate range (information only)."),
    # --- housing: CNC (JLCCNC) model
    "al_kg": prm(8.0, "USD per kg", U_JLCNC_COST, e=True, n="ESTIMATE: 6061-T6 plate/bar incl. cutting waste. JLCCNC publishes no price list."),
    "al_dens": prm(2.70, "g per cm3", "", "", n="Density of 6061 aluminium."),
    "allow": prm(2.0, "mm per side", "", "", e=True, n="ESTIMATE: stock block is the part's bounding box plus this on every side."),
    "mrr": prm(6.0, "cm3 per min", "", "", e=True, n="ESTIMATE: material removal rate of a small 3-axis mill in aluminium."),
    "rate_min": prm(0.60, "USD per min", U_JLCNC_COST, e=True, n="ESTIMATE: machine time rate (calibrated so that one tray+lid costs about what the v0.4 estimate gave: $31 + $12)."),
    "setup_fee": prm(3.50, "USD per set-up", "", "", e=True, n="ESTIMATE: one-off cost per workpiece set-up (each re-clamping of the part)."),
    "tap_fee": prm(0.25, "USD per thread", "", "", e=True, n="ESTIMATE: tapping one M1.6 or M2 thread."),
    "groove_min_m": prm(6.0, "min per metre", U_JLCNC_COST, RESEARCH_DATE, e=True, n="ESTIMATE (new in v0.6): machine time per metre of V-groove (90 deg cutter, 0.25 mm deep, many short pieces and corner arcs). The SAME rate prices the v0.5 grooves that are removed and the v0.6 skin grooves that are added (section 4)."),
    "mark_on": prm(1, "1 or 0", "", "", n="v0.6: 1 = JLCCNC laser-marks the warning text and the artwork on 4 faces (lid, bottom, -Y side, +Y side). 0 = no laser marking (stick an adhesive label with the same text instead; section 10). v0.5 left the marking out of the estimate."),
    "mark_face": prm(2.0, "USD per marked face", U_JLCNC_FIN, RESEARCH_DATE, e=True, n="ESTIMATE (new in v0.6): laser marking of one face of one part after anodising. JLCCNC lists laser marking as a finish but publishes no price. Faces per light: lid 1, tray 3 (bottom, -Y, +Y)."),
    "mark_lot": prm(5.0, "USD per order", U_JLCNC_FIN, RESEARCH_DATE, e=True, n="ESTIMATE (new in v0.6): one-off cost per order for loading the five DXF artworks and the marking set-up."),
    # --- housing: stainless caps (JLCCNC)
    "caps_steel": prm(1, "1 or 0", "", "", n="v0.6: 1 = order the three caps in SUS304 stainless from JLCCNC (cap_main x1 and cap_slide x2 per light + 1 spare of each, bead blasted). 0 = use the resin caps of the print kit instead: no extra cost (the kit holds them in both cases)."),
    "cap_first": prm(8.0, "USD per cap type", U_JLCNC_HOME, RESEARCH_DATE, e=True, n="ESTIMATE (new in v0.6): first piece of one cap type, set-up, programming and bead blast included. JLCCNC publishes no per-part price, only 'CNC milling/turning from $5.00'; tiny turned stainless parts usually quote at $5-15 for one piece."),
    "cap_next": prm(4.0, "USD per further piece", U_JLCNC_HOME, RESEARCH_DATE, e=True, n="ESTIMATE (new in v0.6): each further piece of the same cap type in the same order (set-up already paid), about half of the first piece."),
    # --- housing: resin (JLC3DP)
    "resin_cm3": prm(0.30, "USD per cm3", U_3DP_HOME, e=True, n="ESTIMATE from the headline 'SLA from $0.30'. The instant quote shows the real price per part."),
    "resin_min": prm(0.60, "USD per part", U_3DP, e=True, n="ESTIMATE: minimum price of one printed part. The print kit (the seven resin parts on sprues, ONE part for JLC3DP) and the laser sleeve are so small that this minimum decides."),
    # --- hidden costs: EU import
    "vat": prm(0.21, "fraction", U_VAT, n="Lithuania standard VAT 21 %. JLC collects it at checkout for orders up to EUR 150 (IOSS)."),
    "ioss_eur": prm(150.0, "EUR", U_VAT, n="IOSS limit: intrinsic value (goods only, without shipping/VAT) up to EUR 150 per consignment."),
    "flat_duty": prm(3.0, "EUR per customs line", U_EC, n="Flat customs duty on low-value consignments, EUR 3 per item category (HS code) per parcel, 1 Jul 2026 - 1 Jul 2028 (Council Reg. 2026/382; JLC FAQ " + U_CUST + ")."),
    "formal_fee_min": prm(15.0, "EUR per parcel", U_CUST, n="Above EUR 150 the parcel goes through formal customs clearance; the carrier charges a disbursement fee, e.g. DHL Germany 2 % min EUR 15, UPS 3 % min EUR 15.70, FedEx 2.5 % min EUR 15."),
    "formal_fee_pct": prm(0.02, "fraction of VAT+duty", U_CUST, n="See above (DHL Germany example)."),
    "card_pct": prm(0.015, "fraction", "", "", e=True, n="ESTIMATE: card / currency-conversion fee of your bank on the USD payments to JLC (0-3 % depending on the bank). Set your own."),
    "ship_mode": prm(2, "1 or 2", "", "", n="1 = economy shipping, 2 = express (DHL/UPS/FedEx). Default express: fastest, and DDP (taxes paid at checkout) works most reliably."),
    "ali_ship": prm(2.0, "USD per parcel", "", e=True, n="ESTIMATE: AliExpress shipping to Lithuania per seller parcel (many items are free, some cost $1-4)."),
    "ali_parcels": prm(8, "parcels", "", "", e=True, n="ESTIMATE: number of separate seller parcels if you buy each item where it is cheapest (cells, LED board, laser, window, screws, rings, wire, tapes+epoxy+silicone pads)."),
    "ali_parcels_consol": prm(3, "parcels", "", "", e=True, n="Parcels if you buy the small hardware (screws, rings, wire, tapes, silicone pads, epoxy) from ONE EU web shop."),
    "risk_pcb_f": prm(1.0, "fraction", "", "", n="Risk reserve = this fraction of the JLCPCB order (landed) as a second PCB order after a first-article problem. Not in the totals."),
    "risk_house_f": prm(1.0, "fraction", "", "", n="Risk reserve = this fraction of the JLCCNC order (landed) as a second housing order. Not in the totals."),
}

# shipping per parcel (USD): economy A, express A, economy B, express B  - ESTIMATES, JLC shows the real price in the cart
SHIPPING = [
    ("JLCPCB (PCB + assembly)", 6.50, 21.50, 6.50, 21.50,
     "Anchors (Chiptron, 10 Jun 2025): DHL Express $21.50, EuroPacket $6.50, Global Standard Direct Line $1.50 for a small order; EEVblog 2024: FedEx about $16 to Spain. JLC publishes no rate table - the cart shows 'Shipping Estimate'."),
    ("JLCCNC (tray, lid, steel caps)", 7.00, 22.00, 9.00, 25.00,
     "ESTIMATE. JLCCNC shows the shipping price on the invoice after you accept the quote. Aluminium parts are heavier than PCBs: 5 sets weigh about 0.2 kg; the stainless caps add a few grams."),
    ("JLC3DP (resin print kit)", 6.50, 21.50, 6.50, 21.50,
     "ESTIMATE. A few grams of resin: shipping is the same as for a small JLCPCB parcel."),
]
PARCELS = [  # name, customs lines, duty rate in the formal route (assumed)
    ("JLCPCB (PCB + assembly)", 2, 0.0, "Bare and assembled PCBs: HS 8534/8543, normally 0 % duty (assumption - check the invoice)."),
    ("JLCCNC (tray, lid, steel caps)", 1, 0.06, "Aluminium articles HS 7616 99 90, 6 %; the three stainless caps are a second customs line (steel articles, HS 7326, about 3 %): 6 % is used for the whole parcel (assumption - check the invoice). The line count is 1 + the stainless-caps switch."),
    ("JLC3DP (resin print kit)", 1, 0.065, "Plastic articles HS 3926 90, 6.5 % (assumption - check the invoice)."),
    ("AliExpress / web shops", 1, 0.0, "Mixed small hardware; each parcel is far below EUR 150, so the flat EUR 3 per line applies."),
]
XRAY_TIERS = [(1, 1.64), (11, 0.82), (51, 0.49), (201, 0.33), (501, 0.25), (1001, 0.16), (3001, 0.082)]

# CNC finishes: name, tray USD/part, lid USD/part, lot fee USD/order, note  (ALL ESTIMATES - JLCCNC prices them in the quote)
FINISHES = [
    ("As machined (no finish)", 0.0, 0.0, 0.0, "Tool marks visible, bare aluminium dulls and marks with fingerprints. Cheapest, fine for a fit test."),
    ("Bead blast only", 1.5, 1.0, 3.0, "Uniform matt grey surface, hides tool marks. Not corrosion-protected."),
    ("Black anodize only", 2.0, 1.2, 8.0, "Black coating on the machined surface (tool marks still visible); the drawings ask for type II, 8-12 um (JLCCNC range 8-25 um). Thickness changes the holes slightly: say so in the quote."),
    ("Bead blast + black anodize", 2.5, 1.5, 8.0, "THE DESIGN CHOICE: matt black, scratch-resistant. On JLCCNC bead blast is not included in the plain anodize option - pick the combined option."),
    ("Bead blast + clear anodize", 2.5, 1.5, 8.0, "Silver matt aluminium look, protected."),
]
FINISH_DEFAULT = "Bead blast + black anodize"

# bought parts: id, item, used for, exact spec, search term, USD per pack, pack size, pack unit, per light, per order,
#               category, price basis, link, price is estimate
BOUGHT = [
    dict(id="cell", item="LiPo cell LP601646 with protection board (PCM) and wire leads",
         use="Power. Two cells in parallel lie flat on top of each other in the cell bay of the tray, protection-board end towards the PCB (BT1).",
         spec="3.7 V lithium-polymer pouch cell, ~400 mAh each (pair ~800 mAh). Size LP601646 = about 6.0 x 16 x 46 mm; the bay takes 6.0 x 16 x 47 mm INCLUDING the protection board, so a cell with a bigger board will not fit. "
              "Must already have the protection board (PCM) and two wire leads (red +, black -). Never use a bare cell. Buy both cells of a light together from one seller. Check the listed continuous discharge rating: >= 2C (0.8 A per cell, the Balanced profile allows 1.6 A for the pair), >= 3C for the Extreme profile (2.6 A) - docs/ble_protocol.md lists the limits.",
         search="LP601646 400mAh 3.7V lipo battery with protection board wire", price=4.50, pack=1, unit="cell", per_light=2, per_order=1,
         cat="Part", basis="ESTIMATE. AliExpress search result " + V05_DATE + ": US $4.76 for a 400 mAh 071740 cell with PCM (item 32662761434) - same price class but a DIFFERENT size (7 x 17 x 40 mm, too thick for this bay); search for LP601646 by name.",
         link=ALI_ITEM.format("32662761434"), est=True),
    dict(id="led", item="Luminus SST-20-W LED on a 10 mm round DTP copper board (ready-made)",
         use="The main white light (D2): sits in the head behind the glass window, wires go to pads J3.",
         spec="Round board 10.0 mm diameter x 1.6 mm thick (the head bore takes 10.0 + 0.2 mm), copper-core 'DTP' (direct thermal path) so the heat leaves through the copper, "
              "emitter Luminus SST-20 white (5000-6500 K), two solder pads for wires. If the seller only has 16 or 20 mm boards the tray will NOT fit - ask for 10 mm.",
         search="SST-20 DTP 10mm led board copper", price=5.40, pack=1, unit="board", per_light=1, per_order=1,
         cat="Part", basis="ESTIMATE. AliExpress search result " + V05_DATE + ": US $5.42 for an SST-20 6500K on a 16/20 mm DTP board (item 32884236179); a 10 mm board may cost a little more or be rarer.",
         link=ALI_ITEM.format("32884236179"), est=True),
    dict(id="laser", item="Green laser module 520 nm, Class 2 (<= 1 mW), 6 x 12 mm, driver built in",
         use="The laser pointer (LS1). Switched by Q1 and the slide-switch interlock S2; wires go to pads J5.",
         spec="Body 6.0 mm diameter x 12 mm long (the tray bore is 6.1 mm), 520 nm green, output power <= 1 mW (Class 2, see the explanation below the table), constant-power (APC) driver inside, "
              "3 V class supply (design note LS1 '3 V'; check that the seller's range includes 3.0-4.2 V), two wire leads. A 4.5 mm module needs the printed sleeve. Ask the seller for a measured output power.",
         search="520nm green laser module 6x12mm 1mW APC", price=23.50, pack=1, unit="module", per_light=1, per_order=0,
         cat="Part", basis="ESTIMATE. AliExpress search result " + V05_DATE + ": US $23.5 for a 6 mm 520 nm 1 mW APC module (item 32869119160).",
         link=ALI_ITEM.format("32869119160"), est=True),
    dict(id="window", item="Round glass window 10.0 x 1.0 mm (flat, clear)",
         use="Closes the head in front of the LED (window 10.0 mm, 1.0 mm thick, sits 0.2 mm recessed).",
         spec="Flat round glass disc 10.0 mm diameter (tolerance -0.1 mm, the bore is 10.2 mm), 1.0 mm thick, clear or anti-reflection coated; no curved lens.",
         search="10mm x 1mm round glass lens flat flashlight", price=2.95, pack=5, unit="5 pcs", per_light=1, per_order=1,
         cat="Part", basis="ESTIMATE. AliExpress search result " + V05_DATE + ": US $2.95 for 5 pcs flat glass lens (item 4001014613249); the exact size of that listing was not verified.",
         link=ALI_ITEM.format("4001014613249"), est=True),
    dict(id="m16", item="Screw M1.6 x 4 mm, countersunk, stainless (lid)",
         use="Four screws hold the lid (two at the front, two at the rear).",
         spec="ISO 7046 / DIN 965 M1.6 x 4, A2 stainless, head diameter <= 3.1 mm (countersink 3.3 mm). Tray thread M1.6 (tap drill 1.25 mm), lid clearance hole 1.8 mm. Phillips or hex head - match your screwdriver. Buy extra: they are tiny and get lost.",
         search="M1.6x4 countersunk screw A2 stainless 100pcs", price=2.00, pack=100, unit="100 pcs", per_light=4, per_order=10,
         cat="Part", basis="ESTIMATE. AliExpress search result " + V05_DATE + ": US $1.5 for 100 pcs M1.6 x 3 countersunk (item 32917852857); M1.6 x 4 priced slightly higher.",
         link=ALI_ITEM.format("32917852857"), est=True),
    dict(id="m2", item="Set screw M2 x 2 mm, cup point, hex socket",
         use="Locks the laser module in its bore from the bottom face (thread length 2.85 mm).",
         spec="M2 x 2 (M2 x 2.5 also fits), cup point, A2 or steel, hex socket for a 0.9 mm hex key. The thread is only 2.85 mm long: an M2 x 3 or longer screw sticks out of the bottom face when it clamps the module. The tray tap is 1.6 mm.",
         search="M2x2 set screw cup point hex socket", price=2.00, pack=50, unit="50 pcs", per_light=1, per_order=4,
         cat="Part", basis="ESTIMATE (typical price of a 50-pack set screw listing).", link=ALI_SEARCH.format("M2x2+set+screw+cup+point"), est=True),
    dict(id="ring", item="Split ring 20-25 mm, stainless",
         use="Key ring through the lanyard slot in the tail (slot 4.4 x 7.6 mm).",
         spec="Stainless split ring, inner diameter 20-25 mm, wire thickness <= 3 mm so that it fits the 4.4 mm slot.",
         search="split key ring 25mm stainless steel", price=2.00, pack=20, unit="20 pcs", per_light=1, per_order=1,
         cat="Part", basis="ESTIMATE (typical price of a 20-pack key ring listing).", link=ALI_SEARCH.format("split+key+ring+25mm+stainless"), est=True),
    dict(id="wire", item="PTFE wire 28 AWG, red + black, 5 m of each",
         use="LED wires (J3 to the LED board), laser wires (J5), cell wires (J2). About 0.3 m per light.",
         spec="28 AWG (about 0.08 mm2) tinned copper with PTFE (Teflon) insulation, outer diameter <= 0.8 mm (the LED wire hole in the tray is 1.3 mm). PTFE does not melt when you solder. Keep the LED leads short (60 mm).",
         search="28AWG PTFE wire red black 5m", price=6.00, pack=5, unit="5 m", per_light=0.3, per_order=0.7,
         cat="Consumable", basis="ESTIMATE (typical price of a 5 m PTFE wire listing).", link=ALI_SEARCH.format("28AWG+PTFE+wire+red+black"), est=True),
    dict(id="thermal", item="Thermal transfer tape 0.15 mm, double-sided, 1 roll",
         use="Sticks the LED board to the floor of the head and carries the heat into the aluminium (a disc of 10 mm).",
         spec="Thickness 0.15 mm (the design uses 0.15 mm), thermally conductive double-sided adhesive, >= 1 W/mK, width >= 10 mm (3M 8805 class).",
         search="thermal conductive double sided tape 0.15mm", price=3.79, pack=1, unit="roll", per_light=0, per_order=1,
         cat="Consumable", basis="AliExpress search result " + V05_DATE + ": US $3.79 for thermal tape (item 33014898122).", link=ALI_ITEM.format("33014898122"), est=True),
    dict(id="kapton", item="Kapton (polyimide) tape 5-10 mm wide, 1 roll",
         use="Insulates bare metal near the PCB and the laser module's back.", spec="Polyimide tape (amber), 5-10 mm wide, about 0.06 mm thick, heat resistant.",
         search="kapton tape 10mm polyimide", price=2.50, pack=1, unit="roll", per_light=0, per_order=1,
         cat="Consumable", basis="ESTIMATE (typical price).", link=ALI_SEARCH.format("kapton+tape+10mm"), est=True),
    dict(id="foam", item="Double-sided foam tape 1 mm x 10 mm, 1 roll",
         use="Holds the two cells in the bay without squeezing them.", spec="Soft foam core, about 1 mm thick, 10 mm wide, double-sided adhesive.",
         search="double sided foam tape 1mm 10mm", price=2.50, pack=1, unit="roll", per_light=0, per_order=1,
         cat="Consumable", basis="ESTIMATE (typical price).", link=ALI_SEARCH.format("double+sided+foam+tape+1mm"), est=True),
    dict(id="epoxy", item="Clear two-part epoxy, 5 minute, small syringe (or UV-curing clear adhesive)",
         use="Glues the glass window and the RF window (resin) into their pockets and the light-pipe tube into its counterbore in the floor.",
         spec="Clear, 5-minute cure, small syringe or sachets (a clear UV-curing adhesive with a UV torch also works). Use a thin bead only. Do NOT use cyanoacrylate (super glue) on the clear resin parts: its vapour leaves a white bloom. "
              "The tube sits in the 8.45 mm hole with 0.025 mm per side and a 0.2 mm ledge: glue it, do not press it.",
         search="clear epoxy 5 minute syringe AB glue", price=3.50, pack=1, unit="syringe", per_light=0, per_order=1,
         cat="Consumable", basis="ESTIMATE (typical price).", link=ALI_SEARCH.format("clear+epoxy+AB+glue+5+minute"), est=True),
    dict(id="pad_can", item="Silicone thermal gap pad 1.0 mm, Shore 00 70-80, sheet at least 20 x 20 mm",
         use="Hold-down of the PCB at the module can: a piece 8.8 x 12.4 mm sticks to the can boss under the lid (X 22.1-30.9, Y -7.6 to 4.8) and is compressed to 0.8 mm (20 %) when the lid is closed.",
         spec="Soft silicone gap filler (thermal pad), thickness 1.0 mm (tolerance 0.1 mm), hardness about Shore 00 70-80 (E about 1 MPa); thermal rating does not matter, softness does. A harder pad lifts the buttons less but the model assumed this softness. "
              "Cut with a sharp knife on a cutting mat. One sheet gives many pieces: buy one sheet per order.",
         search="silicone thermal pad 1mm 100x100 soft", price=3.50, pack=1, unit="sheet", per_light=0, per_order=1,
         cat="Consumable", basis="ESTIMATE (typical price of a 100 x 100 x 1 mm silicone thermal pad listing); no listing was read for v0.6.", link=ALI_SEARCH.format("silicone+thermal+pad+1mm+100x100"), est=True),
    dict(id="pad_front", item="Silicone rubber sheet 1.0 mm, Shore A 70, sheet at least 20 x 20 mm",
         use="Second hold-down next to the next-button SW2: a piece 3.7 x 3.2 mm sticks to the front boss under the lid (X 15.65-19.35, Y 0.05-3.25) and is compressed to 0.8 mm.",
         spec="Solid silicone rubber sheet, thickness 1.0 mm, hardness Shore A 70 (E about 5 MPa, much firmer than the thermal pad), any colour. Cut with a sharp knife. One sheet per order.",
         search="silicone rubber sheet 1mm shore A 70", price=3.50, pack=1, unit="sheet", per_light=0, per_order=1,
         cat="Consumable", basis="ESTIMATE (typical price of a small silicone rubber sheet listing); no listing was read for v0.6.", link=ALI_SEARCH.format("silicone+rubber+sheet+1mm+shore+70"), est=True),
    dict(id="siladh", item="Silicone adhesive (small tube, clear or neutral-cure RTV)",
         use="Sticks the two hold-down pads onto their lid bosses (a drop on each boss), so that they stay on the lid when it is opened.",
         spec="Neutral-cure silicone (no acetic acid smell: acetic cure can attack the copper of the PCB). A drop per boss only; keep it off the board.",
         search="neutral cure silicone adhesive small tube 20ml", price=2.50, pack=1, unit="tube", per_light=0, per_order=1,
         cat="Consumable", basis="ESTIMATE (typical price).", link=ALI_SEARCH.format("silicone+adhesive+tube+neutral+cure"), est=True),
]

# tools (one-time): item, why, spec, search, USD each, qty, needed (1 = buy it, 0 = optional)
TOOLS = [
    ("Soldering iron with fine tip", "Solder the wires to the pads J2, J3, J5 and fix small faults.", "Temperature controlled (about 300-350 C), conical or chisel tip 0.4-1 mm, e.g. Pinecil / TS101 / Hakko FX-888D class.", "pinecil soldering iron", 35.0, 1, 1),
    ("Solder wire 0.5 mm with flux core", "Hand soldering.", "0.5 mm diameter, Sn63Pb37 or lead-free SAC305, flux core, 50 g reel.", "solder wire 0.5mm rosin core", 8.0, 1, 1),
    ("Flux (gel syringe or pen)", "Makes the solder flow on the small pads.", "No-clean flux gel in a syringe (e.g. Amtech NC-559 class) or flux pen.", "no clean flux gel syringe", 6.0, 1, 1),
    ("Fine tweezers", "Hold small parts and wires.", "ESD-safe, pointed tips, stainless; 2-3 shapes.", "ESD tweezers set precision", 5.0, 1, 1),
    ("Precision screwdriver and hex key set", "Lid screws (M1.6) and the M2 laser set screw.", "Phillips PH000/PH00 or hex 0.9 mm bits, hex key 0.9 mm for the M2 set screw.", "precision screwdriver set hex 0.9mm", 8.0, 1, 1),
    ("Multimeter", "Check battery voltage, shorts and continuity before the first power-up.", "Any basic digital multimeter with continuity buzzer, DC voltage and current.", "digital multimeter", 15.0, 1, 1),
    ("Laser safety glasses for 520 nm", "Eye protection whenever the laser is powered on the bench.", "Rated for 520 nm green, OD 4+ (e.g. '190-540 nm OD4+' or 532 nm goggles); CE / EN 207 marked.", "laser safety glasses 520nm 532nm OD4", 14.0, 1, 1),
    ("Side cutters (flush)", "Trim wires and cut the resin parts off the sprues of the print kit.", "Small flush cutters.", "flush cutter mini", 5.0, 1, 1),
    ("Hobby knife and cutting mat", "Cut the two silicone hold-down pads to size (8.8 x 12.4 mm and 3.7 x 3.2 mm).", "Scalpel or hobby knife with spare blades, small self-healing cutting mat (A5).", "hobby knife cutting mat set", 7.0, 1, 1),
    ("Wire stripper (fine)", "Strip 28 AWG PTFE wire without cutting the strands.", "For 20-30 AWG wire.", "precision wire stripper 28AWG", 7.0, 1, 1),
    ("Isopropyl alcohol 99 % and swabs", "Clean flux residue and the contact surfaces before taping.", "99 % isopropyl alcohol 100-250 ml, lint-free swabs.", "isopropyl alcohol 99 percent", 6.0, 1, 1),
    ("USB-C data cable", "Charge the light and update the firmware over USB. A charge-only cable will NOT work for data.", "USB-C to USB-A or USB-C, labelled 'data', 0.5-1 m.", "usb c data cable", 4.0, 1, 1),
    ("Digital caliper", "Measure the laser module (6.0 mm), the cells and the window before the housing is ordered.", "Resolution 0.01 mm, range 150 mm.", "digital caliper 150mm", 12.0, 1, 1),
    ("Desoldering braid", "Remove solder bridges.", "2 mm wide.", "desoldering wick braid", 3.0, 1, 1),
    ("Magnifier or USB microscope", "Inspect the 0402 joints of the assembled board.", "x10-x20 loupe or a USB microscope.", "usb microscope", 15.0, 1, 0),
    ("Bench power supply with current limit", "Safer first power-up (limit 0.5 A).", "0-5 V, adjustable current limit.", "bench power supply adjustable current limit", 30.0, 1, 0),
    ("Laser power meter", "Check that the laser module really emits <= 1 mW (Class 2).", "Handheld optical power meter that covers 520 nm and 1 mW.", "laser power meter handheld 520nm", 45.0, 1, 0),
    ("Hand taps M1.6 and M2 with wrench", "Only if JLCCNC cannot cut M1.6 threads: order plain 1.25 mm / 1.6 mm holes and tap them yourself.", "M1.6 x 0.35 and M2 x 0.4 taps.", "M1.6 M2 hand tap set", 10.0, 1, 0),
]


# ----------------------------------------------------------------------------------------------
# housing parts (volumes from housing_interface.json, boxes from tray_bbox / the STL files)
# ----------------------------------------------------------------------------------------------
def jlc3dp_size_ok(box):
    """JLC3DP minimum build size (SLA 8001 page): a box of at least 5 x 5 x 5 mm, or 10 x 2 x 2 mm."""
    a, c = max(box), min(box)
    return c >= 5 or (a >= 10 and c >= 2)


def dims(box):
    """'94.4 x 20 x 16 mm' (one decimal, trailing zeros dropped)."""
    return " x ".join(("%.1f" % x).rstrip("0").rstrip(".") for x in box) + " mm"


def and_list(words):
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


def housing_parts(H, stl):
    """List of mechanical parts with geometry. CNC = JLCCNC aluminium, STEEL = JLCCNC stainless caps, RESIN = JLC3DP.

    JLC3DP gets ONE resin part, the print kit (kit=True): the seven resin parts of PRINT_KIT_KEYS (RF window insert, LED spacer
    ring, antenna spacer with floor plug, light-pipe tube, main cap and two slide caps in resin) joined by 1 mm sprues, one kit per
    light + one spare kit, priced from the kit's own STL volume (the size check uses its STL box). The seven stay in the list as
    information rows with quantity 0 (in_kit=True; the slide cap has count 2). The three stainless caps are separate CNC parts
    (STEEL): the resin caps in the kit have the same geometry and are their fallback. The laser sleeve is a separate optional print
    (quantity 0 unless the laser module is 4.5 mm)."""
    bb = H["tray_bbox"]
    tray_box = tuple(round(bb[2 * i + 1] - bb[2 * i], 1) for i in range(3))
    vol = H["volumes_mm3"]
    mass = H.get("mass_g", {})
    par = H.get("params", {})

    def box(key):
        return stl[key][:3]

    def v(key):
        return vol[key] if key in vol else stl[key][3]

    def m(key):
        return mass[key] if key in mass else round(v(key) * RESIN_DENS, 1)

    def m_resin(key):
        return round(v(key) * RESIN_DENS, 2)
    names = {"FlashKa_rf_window": "RF window insert", "FlashKa_spacer_ring": "LED spacer ring", "FlashKa_antenna_spacer": "antenna spacer with floor plug",
             "FlashKa_tube": "light-pipe tube", "FlashKa_cap_main": "resin main cap", "FlashKa_cap_slide": "resin slide cap"}
    kit_names = [names[k] if k != "FlashKa_cap_slide" else "2 resin slide caps" for k in dict.fromkeys(PRINT_KIT_KEYS)]
    small = [names[k] for k in dict.fromkeys(PRINT_KIT_KEYS) if not jlc3dp_size_ok(box(k))]
    why = ("because the %s alone %s below JLC3DP's minimum build size (5 x 5 x 5 mm or 10 x 2 x 2 mm); the other parts ride along, so that one part, one "
           "minimum price and one customs line cover all seven" % (and_list(small), "is" if len(small) == 1 else "are")) if small else \
        "so that JLC3DP prints and ships one part instead of seven"
    inkit = "Included in the print kit (cut apart at home). "

    def alone(key):
        return "" if jlc3dp_size_ok(box(key)) else " Alone it is below the minimum build size: that is why it is printed in the kit."
    rfw_t = par.get("rfw_flange_t", 0.6) + par.get("rfw_flange_drop", 0.0)   # flange = pocket depth + drop
    mc, sc_ = par.get("main_cap") or [5.8, 6.6, 0.6, 3.0], par.get("slide_cap") or [3.4, 5.0, 0.6, 2.0]
    out = [
        dict(id="tray", key="FlashKa_tray", label="Tray (main body, %s)" % dims(tray_box), proc="CNC", box=tray_box, vol=v("FlashKa_tray"),
             mass=mass.get("FlashKa_tray", 0), per_light=1, spare=0, factor=1.10, setups=5, taps=5, marks=3,
             note="4 x M1.6 lid threads + 1 x M2 laser set-screw thread, window and laser bores, cell bay, three floor holes for the caps and the tube, floor RF window, "
                  "lanyard slot, skin seams (frames and stringers), laser marking of 3 faces (bottom, -Y, +Y)."),
        dict(id="lid", key="FlashKa_lid", label="Lid (%s)" % dims(box("FlashKa_lid")), proc="CNC", box=box("FlashKa_lid"), vol=v("FlashKa_lid"),
             mass=mass.get("FlashKa_lid", 0), per_light=1, spare=0, factor=1.30, setups=3, taps=0, marks=1,
             note="1.5 mm plate with two hold-down bosses (up to 5.2 mm tall), 0.6 mm rabbet lip, 4 countersunk holes, RF-window pocket, skin seams and the label field "
                  "(laser marking of the lid face). Thin parts are harder to clamp, hence the factor 1.30."),
        dict(id="capm", key="FlashKa_cap_main", label="Main cap, stainless SUS304 (head dia %s, flange dia %s, %s)" % (mc[0], mc[1], dims(box("FlashKa_cap_main"))),
             proc="STEEL", box=box("FlashKa_cap_main"), vol=v("FlashKa_cap_main"), mass=mass.get("FlashKa_cap_main", round(v("FlashKa_cap_main") * STEEL_DENS, 2)),
             per_light=1, spare=1,
             note="Turned part with a domed head, bead blasted, no coating. 1 per light + 1 spare. Tiny: JLCCNC may refuse it by size (see section 10); "
                  "the resin main cap of the print kit is the fallback."),
        dict(id="caps", key="FlashKa_cap_slide", label="Slide cap, stainless SUS304 (head dia %s, flange dia %s, %s)" % (sc_[0], sc_[1], dims(box("FlashKa_cap_slide"))),
             proc="STEEL", box=box("FlashKa_cap_slide"), vol=v("FlashKa_cap_slide"), mass=mass.get("FlashKa_cap_slide", round(v("FlashKa_cap_slide") * STEEL_DENS, 2)),
             per_light=2, spare=1,
             note="Same turned part for the next and the previous button, bead blasted. 2 per light + 1 spare. The resin slide caps of the print kit are the fallback."),
        dict(id="kit", key="FlashKa_print_kit", label="Print kit = the 7 resin parts below on 1 mm sprues (ONE part at JLC3DP)", proc="RESIN", kit=True,
             box=box("FlashKa_print_kit"), vol=v("FlashKa_print_kit"), mass=m("FlashKa_print_kit"), per_light=1, spare=1,
             note="What you order at JLC3DP: the %s joined by 1 mm sprues, %s. One kit per light + one spare kit. "
                  "Volume and box are measured from the kit's own STL; you cut the parts apart at home with flush cutters."
                  % (and_list(kit_names), why)),
        dict(id="rfw", key="FlashKa_rf_window", label="   RF window insert - in the print kit", proc="RESIN", in_kit=True, count=1,
             box=box("FlashKa_rf_window"), vol=v("FlashKa_rf_window"), mass=m("FlashKa_rf_window"), per_light=0, spare=0,
             note=inkit + "Translucent resin lets the Bluetooth signal out; glued into the lid with epoxy. Flange %.1f mm thick." % rfw_t
                  + alone("FlashKa_rf_window")),
        dict(id="ring", key="FlashKa_spacer_ring", label="   LED spacer ring - in the print kit", proc="RESIN", in_kit=True, count=1,
             box=box("FlashKa_spacer_ring"), vol=v("FlashKa_spacer_ring"), mass=m("FlashKa_spacer_ring"), per_light=0, spare=0,
             note=inkit + "Ring OD %s / ID %s mm between the LED board and the glass window." % (par.get("ring_od", 10.1), par.get("ring_id", 7.2))
                  + alone("FlashKa_spacer_ring")),
        dict(id="ant", key="FlashKa_antenna_spacer", label="   Antenna spacer with floor plug - in the print kit", proc="RESIN", in_kit=True, count=1,
             box=box("FlashKa_antenna_spacer"), vol=v("FlashKa_antenna_spacer"), mass=m("FlashKa_antenna_spacer"), per_light=0, spare=0,
             note=inkit + "Keeps the cells away from the ESP32 antenna; its plug closes the floor RF window." + alone("FlashKa_antenna_spacer")),
        dict(id="tube", key="FlashKa_tube", label="   Light-pipe tube - in the print kit", proc="RESIN", in_kit=True, count=1,
             box=box("FlashKa_tube"), vol=v("FlashKa_tube"), mass=m("FlashKa_tube"), per_light=0, spare=0,
             note=inkit + "Carries the light of the two ring LEDs round the main cap; OD %s, rim %s mm, glued into the counterbore of the floor (clear epoxy, not cyanoacrylate)."
                  % (par.get("tube_od", 8.4), (par.get("tube_rim") or [8.8])[0]) + alone("FlashKa_tube")),
        dict(id="capmr", key="FlashKa_cap_main", label="   Main cap in resin (fallback of the steel cap) - in the print kit", proc="RESIN", in_kit=True, count=1,
             box=box("FlashKa_cap_main"), vol=v("FlashKa_cap_main"), mass=m_resin("FlashKa_cap_main"), per_light=0, spare=0,
             note=inkit + "Same geometry as the steel main cap: fit check, or the replacement if the steel cap is refused or not wanted." + alone("FlashKa_cap_main")),
        dict(id="capsr", key="FlashKa_cap_slide", label="   Slide cap in resin, 2 per kit (fallback of the steel caps) - in the print kit", proc="RESIN", in_kit=True, count=2,
             box=box("FlashKa_cap_slide"), vol=v("FlashKa_cap_slide"), mass=m_resin("FlashKa_cap_slide"), per_light=0, spare=0,
             note=inkit + "Two identical caps in each kit (next and previous button), same geometry as the steel slide cap." + alone("FlashKa_cap_slide")),
        dict(id="sleeve", key="FlashKa_laser_sleeve", label="Laser sleeve (optional, separate print)", proc="RESIN",
             box=box("FlashKa_laser_sleeve"), vol=v("FlashKa_laser_sleeve"), mass=m("FlashKa_laser_sleeve"), per_light=0, spare=0,
             note="ONLY if your laser module is 4.5 mm instead of 6.0 mm: set 'Per light' to 1. Not part of the kit: it is a separate STL "
                  "(%s) and big enough to be printed on its own." % ofp("FlashKa_laser_sleeve.stl")),
    ]
    return out


def tier_price(tiers, qty):
    """LCSC price for buying qty pieces: price of the largest tier whose minimum quantity <= qty, else the first tier."""
    n = sum(1 for q, _ in tiers if q <= qty)
    return tiers[max(1, n) - 1][1]


def ceil_div(a, b):
    return math.ceil(round(a / b, 9))


def polygon_area_mm2(poly):
    s = 0.0
    for i, (x1, y1) in enumerate(poly):
        x2, y2 = poly[(i + 1) % len(poly)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


# ----------------------------------------------------------------------------------------------
# independent Python model: every number the workbook computes with formulas is computed here again
# ----------------------------------------------------------------------------------------------
def model(P, lines, H, hparts, finish_name, bought, tools):
    v = {k: x["v"] for k, x in P.items()}
    cp = {}
    EXTRA = {c: n for c, n, _ in ATTRITION}
    area_cm2 = polygon_area_mm2(H["pcb_outline"]) / 100.0
    xs = [p[0] for p in H["pcb_outline"]]
    ys = [p[1] for p in H["pcb_outline"]]
    cp["pcb_w"] = max(xs) - min(xs)
    cp["pcb_h"] = max(ys) - min(ys)
    cp["pcb_area_cm2"] = area_cm2
    joints = sum(l["qty"] * l["pads"] for l in lines)
    cp["placements"] = sum(l["qty"] for l in lines)
    cp["joints"] = joints
    cp["n_lines"] = len(lines)
    cp["n_ext"] = sum(1 for l in lines if l["type"] == "Extended")
    cp["n_basic"] = sum(1 for l in lines if l["type"] == "Basic")
    fx = v["fx"]
    cp["fx"] = fx
    res = {}
    for sc in "AB":
        lights = v["lights" + sc]
        boards = max(lights, v["min_asm"])
        pcbs = math.ceil(max(v["min_pcb"], boards) / 5.0) * 5
        cp["boards_" + sc] = boards
        cp["pcbs_" + sc] = pcbs
        # components
        comps = 0.0
        extra_cost = 0.0
        for i, l in enumerate(lines):
            buy = l["qty"] * boards + EXTRA[l["cls"]]
            up = tier_price(l["tiers"], buy)
            cp["bom_buy_%s_%d" % (sc, i)] = buy
            cp["bom_up_%s_%d" % (sc, i)] = up
            cp["bom_tot_%s_%d" % (sc, i)] = buy * up
            comps += buy * up
            extra_cost += EXTRA[l["cls"]] * up
        cp["comps_" + sc] = comps
        cp["extra_cost_" + sc] = extra_cost
        # fees
        xr_qty = v["xray_per_board"] * boards
        xr_rate = 0.0
        if xr_qty > 0:
            n = sum(1 for q, _ in XRAY_TIERS if q <= xr_qty)
            xr_rate = XRAY_TIERS[max(1, n) - 1][1]
        fees = {
            "setup": v["setup_side"] * v["sides"],
            "stencil": v["stencil_side"] * v["sides"],
            "smt": v["smt_joint"] * joints * boards,
            "feeder": v["feeder_unique"] * len(lines),
            "ext": v["ext_extra"] * cp["n_ext"],
            "eng": v["eng_fee"] * 1,
            "confirm": v["confirm"] * 1,
            "xray": xr_qty * xr_rate,
            "panel": v["panel_board"] * boards,
            "pack_base": v["pack_base"] * 1,
            "pack_area": v["pack_cm2"] * area_cm2 * boards,
            "hand": v["hand_labour"] * 0, "prereflow": v["prereflow"] * 0, "single": v["single_board"] * 0,
            "fixture": v["fixture"] * 0, "storage": v["storage"] * 0, "large": v["large"] * 0,
        }
        for k, x in fees.items():
            cp["fee_%s_%s" % (k, sc)] = x
        fee_total = sum(fees.values())
        fab = v["pcb_fab5"] * pcbs / 5.0
        goods = fab + fee_total + comps
        cp["fab_" + sc] = fab
        cp["fees_" + sc] = fee_total
        cp["jlc_goods_" + sc] = goods
        cp["jlc_goods_eur_" + sc] = goods / fx
        cp["jlc_line_gap_" + sc] = v["ioss_eur"] - goods / fx
        res[sc] = dict(lights=lights, boards=boards, pcbs=pcbs, goods=goods)

    # --- housing
    fin = next(f for f in FINISHES if f[0] == finish_name)
    # fine-feature minutes (section 4 of sheet 'Housing'): minute rows + millimetres of V-groove x minutes per metre
    feat = {"tray": 0.0, "lid": 0.0}
    for _id, _lab, kind, t_, l_, _note in feature_rows(H):
        k = v["groove_min_m"] / 1000.0 if kind == "mm" else 1.0
        feat["tray"] += t_ * k
        feat["lid"] += l_ * k
    cp["feat_tray"] = feat["tray"]
    cp["feat_lid"] = feat["lid"]
    cnc_var = {}
    cnc_set = {}
    for p in hparts:
        if p["proc"] != "CNC":
            continue
        x, y, z = p["box"]
        a = v["allow"]
        stock = (x + 2 * a) * (y + 2 * a) * (z + 2 * a) / 1000.0
        removed = stock - p["vol"] / 1000.0
        mat = stock * v["al_dens"] / 1000.0 * v["al_kg"]
        minutes = removed / v["mrr"] + feat[p["id"]]
        mach = minutes * v["rate_min"] * p["factor"]
        taps = p["taps"] * v["tap_fee"]
        finish = fin[1] if p["id"] == "tray" else fin[2]
        mark = v["mark_on"] * p["marks"] * v["mark_face"]
        var = mat + mach + taps + finish + mark
        cnc_var[p["id"]] = var
        cnc_set[p["id"]] = p["setups"] * v["setup_fee"]
        cp["cnc_stock_" + p["id"]] = stock
        cp["cnc_removed_" + p["id"]] = removed
        cp["cnc_mat_" + p["id"]] = mat
        cp["cnc_min_" + p["id"]] = minutes
        cp["cnc_mach_" + p["id"]] = mach
        cp["cnc_mark_" + p["id"]] = mark
        cp["cnc_var_" + p["id"]] = var
        cp["cnc_setup_" + p["id"]] = cnc_set[p["id"]]
    for p in hparts:
        if p["proc"] == "RESIN":
            cp["resin_size_" + p["id"]] = 1.0 if jlc3dp_size_ok(p["box"]) else 0.0
    for sc in "AB":
        lights = v["lights" + sc]
        alu = sum((lights * p["per_light"] + p["spare"]) * cnc_var[p["id"]] for p in hparts if p["proc"] == "CNC") \
            + sum(cnc_set.values()) + fin[3] + v["mark_on"] * v["mark_lot"]
        caps = 0.0
        for p in hparts:
            if p["proc"] != "STEEL":
                continue
            n = lights * p["per_light"] + p["spare"]
            c = v["caps_steel"] * (v["cap_first"] + max(0, n - 1) * v["cap_next"])
            cp["cap_qty_%s_%s" % (p["id"], sc)] = n
            cp["cap_cost_%s_%s" % (p["id"], sc)] = c
            caps += c
        cp["cnc_alu_" + sc] = alu
        cp["cap_" + sc] = caps
        cnc = alu + caps
        cp["cnc_" + sc] = cnc
        resin = 0.0
        for p in hparts:
            if p["proc"] != "RESIN":
                continue
            unit = max(v["resin_min"], v["resin_cm3"] * p["vol"] / 1000.0)
            qty = lights * p["per_light"] + p["spare"]
            cp["resin_unit_" + p["id"]] = unit
            cp["resin_qty_%s_%s" % (p["id"], sc)] = qty
            resin += unit * qty
        cp["resin_" + sc] = resin
        cp["housing_" + sc] = cnc + resin

    # --- bought parts
    for sc in "AB":
        lights = v["lights" + sc]
        tot = {"Part": 0.0, "Consumable": 0.0}
        spare_val = 0.0
        for b in bought:
            need = lights * b["per_light"] + b["per_order"]
            packs = ceil_div(need, b["pack"])
            cp["bp_packs_%s_%s" % (b["id"], sc)] = packs
            cp["bp_cost_%s_%s" % (b["id"], sc)] = packs * b["price"]
            tot[b["cat"]] += packs * b["price"]
            spare_val += packs * b["price"] - lights * b["per_light"] / b["pack"] * b["price"]
        cp["parts_" + sc] = tot["Part"]
        cp["cons_" + sc] = tot["Consumable"]
        cp["bp_spare_" + sc] = spare_val

    # --- hidden costs: landed cost per parcel
    mode = v["ship_mode"]
    names = [p[0] for p in PARCELS]
    tot = {}
    for sc in "AB":
        goods_by = {names[0]: cp["jlc_goods_" + sc], names[1]: cp["cnc_" + sc], names[2]: cp["resin_" + sc],
                    names[3]: cp["parts_" + sc] + cp["cons_" + sc]}
        sums = dict(goods=0.0, ship=0.0, duty=0.0, vat=0.0, fee=0.0, landed=0.0)
        jlc_landed = 0.0
        for i, (nm, lines_, rate, _) in enumerate(PARCELS):
            if i == 1:
                lines_ = lines_ + v["caps_steel"]       # second customs line: the stainless caps
            g = goods_by[nm]
            n = v["ali_parcels"] if i == 3 else 1
            sh = SHIPPING[i] if i < 3 else None
            if i < 3:
                ship = (sh[1] if mode == 1 else sh[2]) if sc == "A" else (sh[3] if mode == 1 else sh[4])
            else:
                ship = v["ali_ship"] * n
            per_eur = g / n / fx
            formal = per_eur > v["ioss_eur"]
            if formal:
                duty = rate * (g + ship)
                vat = v["vat"] * (g + ship + duty)
                fee = n * max(v["formal_fee_min"] * fx, v["formal_fee_pct"] * (duty + vat) / n)
            else:
                duty = lines_ * n * v["flat_duty"] * fx
                vat = v["vat"] * (g + ship)
                fee = 0.0
            landed = g + ship + duty + vat + fee
            key = "%s_%d" % (sc, i)
            cp["hc_goods_" + key] = g
            cp["hc_per_eur_" + key] = per_eur
            cp["hc_formal_" + key] = 1.0 if formal else 0.0
            cp["hc_ship_" + key] = ship
            cp["hc_duty_" + key] = duty
            cp["hc_vat_" + key] = vat
            cp["hc_fee_" + key] = fee
            cp["hc_landed_" + key] = landed
            for k2, x in (("goods", g), ("ship", ship), ("duty", duty), ("vat", vat), ("fee", fee), ("landed", landed)):
                sums[k2] += x
            if i < 3:
                jlc_landed += landed
        card = v["card_pct"] * jlc_landed
        for k2, x in sums.items():
            cp["hc_sum_%s_%s" % (k2, sc)] = x
        cp["card_" + sc] = card
        tot[sc] = sums
        cp["tax_other_" + sc] = sums["ship"] + sums["duty"] + sums["vat"] + sums["fee"] + card
    # the EUR 150 cliff for the JLCPCB parcel of scenario A: landed cost on the IOSS route vs the formal route
    g0, s0 = cp["hc_goods_A_0"], cp["hc_ship_A_0"]
    cp["route_ioss_A"] = g0 + s0 + PARCELS[0][1] * v["flat_duty"] * fx + v["vat"] * (g0 + s0)
    d0 = PARCELS[0][2] * (g0 + s0)
    v0 = v["vat"] * (g0 + s0 + d0)
    cp["route_formal_A"] = g0 + s0 + d0 + v0 + max(v["formal_fee_min"] * fx, v["formal_fee_pct"] * (d0 + v0))
    cp["route_diff_A"] = cp["route_formal_A"] - cp["route_ioss_A"]
    # consolidation saving (AliExpress parcels): each avoided parcel saves shipping + flat duty
    cp["consol_saving_A"] = (v["ali_parcels"] - v["ali_parcels_consol"]) * (v["ali_ship"] + PARCELS[3][1] * v["flat_duty"] * fx)

    # --- summary
    for sc in "AB":
        lights = v["lights" + sc]
        pcb_asm = cp["jlc_goods_" + sc]
        housing = cp["housing_" + sc]
        parts = cp["parts_" + sc]
        cons = cp["cons_" + sc]
        other = cp["tax_other_" + sc]
        total = pcb_asm + housing + parts + cons + other
        cp["sum_pcb_" + sc] = pcb_asm
        cp["sum_housing_" + sc] = housing
        cp["sum_parts_" + sc] = parts
        cp["sum_cons_" + sc] = cons
        cp["sum_ship_" + sc] = tot[sc]["ship"]
        cp["sum_vat_" + sc] = tot[sc]["vat"]
        cp["sum_duty_" + sc] = tot[sc]["duty"] + tot[sc]["fee"]
        cp["sum_card_" + sc] = cp["card_" + sc]
        cp["sum_other_" + sc] = other
        cp["sum_total_" + sc] = total
        cp["sum_total_eur_" + sc] = total / fx
        cp["sum_per_" + sc] = total / lights
        cp["sum_per_eur_" + sc] = total / lights / fx
    la, lb = v["lightsA"], v["lightsB"]
    cp["sum_marginal"] = (cp["sum_total_B"] - cp["sum_total_A"]) / (lb - la) if lb != la else 0.0
    cp["sum_marginal_eur"] = cp["sum_marginal"] / fx
    cp["tools_total"] = sum(t[4] * t[5] * t[6] for t in tools)
    cp["tools_optional"] = sum(t[4] * t[5] * (1 - t[6]) for t in tools)
    cp["risk_pcb"] = v["risk_pcb_f"] * cp["hc_landed_A_0"]
    cp["risk_house"] = v["risk_house_f"] * cp["hc_landed_A_1"]
    cp["grand_A"] = cp["sum_total_A"] + cp["tools_total"]
    cp["grand_B"] = cp["sum_total_B"] + cp["tools_total"]
    # --- change from v0.5 (typed-in v0.5 totals, V05_SUMMARY)
    for sc in "AB":
        o = V05_SUMMARY[sc]
        for key, mk in (("pcb", "sum_pcb_"), ("house", "sum_housing_"), ("parts", "sum_parts_"), ("cons", "sum_cons_"),
                        ("tax", "sum_other_"), ("total", "sum_total_"), ("per", "sum_per_")):
            cp["d_%s_%s" % (key, sc)] = cp[mk + sc] - o[key]
    return cp


# ----------------------------------------------------------------------------------------------
# workbook infrastructure: named cell registry (so formulas can refer to cells by name) + sheet helper
# ----------------------------------------------------------------------------------------------
class Book:
    def __init__(self, addr=None):
        self.wb = Workbook()
        self.wb.remove(self.wb.active)
        self.addr = addr if addr is not None else {}
        self.seen = set()
        self.missing = set()

    def reg(self, name, sheet, col, row):
        if name in self.seen:
            raise ValueError("duplicate cell name " + name)
        self.seen.add(name)
        self.addr[name] = (sheet, col, row)

    def ref(self, name, frm):
        if name not in self.addr:
            self.missing.add(name)
            return "$A$1"
        sheet, col, row = self.addr[name]
        a = "$%s$%d" % (get_column_letter(col), row)
        return a if sheet == frm else "'%s'!%s" % (sheet, a)

    def rng(self, n1, n2, frm):
        if n1 not in self.addr or n2 not in self.addr:
            self.missing.update([n for n in (n1, n2) if n not in self.addr])
            return "$A$1:$A$2"
        s1, c1, r1 = self.addr[n1]
        s2, c2, r2 = self.addr[n2]
        a = "$%s$%d:$%s$%d" % (get_column_letter(c1), r1, get_column_letter(c2), r2)
        return a if s1 == frm else "'%s'!%s" % (s1, a)


FONTS = {"text": (BODY, None), "in": (INPUT, None), "est": (INPUT, WARN), "calc": (BODY, None), "x": (XREF, None),
         "head": (HEAD, FILL), "bold": (BOLD, None), "sub": (BOLD, SUB), "tot": (BOLD, TOTAL), "note": (SMALL, None),
         "link": (LINK, None), "title": (BIG, None), "warn": (BODY, WARN), "xtot": (Font(name=ARIAL, size=10, bold=True, color="008000"), TOTAL)}


class Sh:
    def __init__(self, book, title, widths):
        self.b = book
        self.t = title
        self.ws = book.wb.create_sheet(title)
        self.widths = list(widths)
        for i, w in enumerate(widths, 1):
            self.ws.column_dimensions[get_column_letter(i)].width = w
        self.ws.sheet_view.zoomScale = 100
        self.merges = {}

    def ref(self, name):
        return self.b.ref(name, self.t)

    def rng(self, n1, n2):
        return self.b.rng(n1, n2, self.t)

    def put(self, r, c, v, kind="text", fmt=None, name=None, link=None, border=True, align=None, wrap=True):
        cell = self.ws.cell(row=r, column=c, value=v)
        font, fill = FONTS[kind]
        cell.font = font
        if fill is not None:
            cell.fill = fill
        if kind in ("title", "note"):
            border = False
        if border:
            cell.border = BOX
        h = align
        if h is None and isinstance(v, (int, float)) and not isinstance(v, bool):
            h = "right"
        cell.alignment = Alignment(vertical="top", wrap_text=(wrap and kind != "title"), horizontal=h)
        if fmt:
            cell.number_format = fmt
        if link:
            cell.hyperlink = link
            cell.font = LINK
        if name:
            self.b.reg(name, self.t, c, r)
        return cell

    def merge(self, r, c1, c2, text, kind="text", border=False, link=None, name=None, fmt=None):
        cell = self.put(r, c1, text, kind, border=border, link=link, name=name, fmt=fmt)
        for c in range(c1 + 1, c2 + 1):
            if border:
                self.ws.cell(row=r, column=c).border = BOX
            if kind == "head":
                self.ws.cell(row=r, column=c).fill = FILL
        self.ws.merge_cells(start_row=r, start_column=c1, end_row=r, end_column=c2)
        self.merges[(r, c1)] = sum(self.widths[c1 - 1:c2])
        return cell

    def head(self, r, labels, c0=1):
        for i, lab in enumerate(labels):
            if lab is not None:
                self.put(r, c0 + i, lab, "head")

    def param(self, r, key, label=None, fmt=None, c_val=2, c_note=4, c_end=10, kind=None, with_src=True):
        """Typed-in parameter: label | value | unit | note (+ source URL and date) merged to c_end. Registers cell as key."""
        p = P[key]
        self.put(r, 1, label or key, "text")
        u = p["u"]
        if fmt is None:
            fmt = USD2 if u.startswith("USD") else (PCT1 if u.startswith("fraction") else None)
            if key in ("smt_joint", "prereflow", "pack_cm2"):
                fmt = USD4 if key != "pack_cm2" else '"$"0.00000'
            if fmt is None and isinstance(p["v"], float):
                fmt = "0.00"
        self.put(r, c_val, p["v"], kind or ("est" if p["e"] else "in"), fmt=fmt, name=key)
        self.put(r, c_val + 1, u, "text")
        txt = p["n"]
        if with_src and p["src"]:
            txt += "  Source: " + p["src"] + (("  (read " + p["d"] + ")") if p["d"] else "")
        elif with_src and p["d"]:
            txt += "  (" + p["d"] + ")"
        if p["e"]:
            txt = "ESTIMATE. " + txt if not txt.startswith("ESTIMATE") else txt
        self.merge(r, c_note, c_end, txt, "text", border=True)


def autofit(sh, min_h=15.0, line_h=12.6):
    """Set row heights from the wrapped text length (merged ranges use their total width)."""
    ws = sh.ws
    for row in ws.iter_rows():
        need = 1
        for cell in row:
            v = cell.value
            if not isinstance(v, str) or v.startswith("="):
                continue
            w = sh.merges.get((cell.row, cell.column))
            if w is None:
                w = sh.widths[cell.column - 1] if cell.column - 1 < len(sh.widths) else 10
            if cell.font.size and cell.font.size > 12:      # titles do not wrap
                continue
            fs = (cell.font.size or 10) / 10.0
            cpl = max(4.0, w * (1.0 if cell.font.bold else 1.12) / fs)
            lines = sum(max(1, math.ceil(len(par) / cpl)) for par in v.split("\n"))
            need = max(need, lines)
        h = max(min_h, line_h * need + 3)
        if need > 1:
            ws.row_dimensions[row[0].row].height = min(409.0, h)
        elif row[0].row == 1:
            ws.row_dimensions[1].height = 24


def colname(c):
    return get_column_letter(c)


# ----------------------------------------------------------------------------------------------
# sheet: Main PCB BOM
# ----------------------------------------------------------------------------------------------
BOM_HDR = 8
BOM_R0 = 9


def build_bom(book, lines):
    S = "Main PCB BOM"
    widths = [5, 24, 14, 30, 11, 21, 20, 40, 46, 8, 8, 10, 10, 11, 46, 8, 7, 9, 11, 11, 9, 11, 11] + [8] * 6 + [9] * 6 + [46]
    s = Sh(book, S, widths)
    ws = s.ws
    n = len(lines)
    r1 = BOM_R0 + n - 1
    s.put(1, 1, "Main PCB bill of materials - what JLCPCB assembles on the board", "title")
    s.merge(2, 1, 9, ("One line per component type (grouped by LCSC number), generated from tools/kicad/flashka_parts.py with the same grouping and "
                      "ordering as tools/kicad/build_all.py, which writes the BOM you upload as %s: %d lines, %d placements, %d solder joints per board. "
                      "Wire pads (J2 cell, J3 LED, J5 laser) have no LCSC number: they are NOT assembled, you solder the wires by hand. "
                      "The LED board, the cells and the laser are bought parts (sheet 'Bought parts'). New in v0.6: SW1-SW3 (Alps SKRKAEE020, three push buttons on the bottom side), "
                      "LED4 (second ring LED), R30-R34 (button ladder and LED resistors); S1 is gone.")
            % (ofp("BOM_JLCPCB.csv"), n, sum(l["qty"] for l in lines), sum(l["qty"] * l["pads"] for l in lines)))
    s.merge(3, 1, 9, "Unit price = the LCSC price tier that matches the quantity JLCPCB has to buy = (quantity per board x boards assembled) + extra pieces for "
            "placement loss (columns P-Q). Prices were read from the LCSC product pages on %s (v0.5 price check; the lines that did not change keep that date) "
            "(columns X-AI hold the tier tables, typed in from the page). The two NEW lines whose pages could not be read on %s (C115357, C25104) are blue on amber = ESTIMATE: "
            "tiers copied from the sibling parts named in the 'Price source' column. JLC buys from LCSC/its own warehouse; the real component price shows in the JLC cart "
            "after the BOM upload." % (V05_DATE, CHECK))
    s.merge(4, 1, 9, "Basic / Extended = JLCPCB library type read on jlcpcb.com/partdetail/<LCSC number> on %s (assumed, amber, for the two new lines: Extended for C115357, Basic for C25104 - "
            "check them in the JLC BOM upload). In 2026 Standard PCBA every unique part costs the same feeder fee, "
            "Basic or Extended (see sheet 'JLCPCB order'); the 'Preferred' tag (only relevant for the single-sided Economic PCBA) was not shown on any of these pages. "
            "'LCSC stock' is LCSC's retail stock, NOT JLC's warehouse; JLC flags real shortages when you upload the BOM." % V05_DATE)
    s.put(5, 2, "Boards assembled, scenario A", "bold")
    s.put(5, 3, "='JLCPCB order'!%s" % "$E$1", "x", fmt="0", name="bom_boards_A")      # placeholder, replaced below
    s.put(6, 2, "Boards assembled, scenario B", "bold")
    s.put(6, 3, "='JLCPCB order'!%s" % "$G$1", "x", fmt="0", name="bom_boards_B")
    ws.cell(row=5, column=3).value = "=" + book.ref("boards_A", S)
    ws.cell(row=6, column=3).value = "=" + book.ref("boards_B", S)
    hd = ["#", "Designators", "Value", "Footprint", "LCSC #", "Manufacturer part no.", "Manufacturer", "Description (flashka_parts.py)",
          "What it does", "Qty / board", "Solder joints / part", "JLC part type", "JLC part page", "LCSC stock (retail)",
          "Stock note", "Loss class", "Extra pcs", "Buy qty A", "Unit USD A", "Line USD A", "Buy qty B", "Unit USD B", "Line USD B"] \
        + ["Tier %d from qty" % i for i in range(1, 7)] + ["Tier %d USD" % i for i in range(1, 7)] + ["Price source"]
    s.head(BOM_HDR, hd)
    ws.row_dimensions[BOM_HDR].height = 42
    att0 = r1 + 9      # first row of the attrition table
    for i, l in enumerate(lines):
        r = BOM_R0 + i
        s.put(r, 1, i + 1, "text", fmt="0")
        s.put(r, 2, ",".join(l["refs"]), "text")
        s.put(r, 3, l["value"], "text")
        s.put(r, 4, l["fp"], "text")
        s.put(r, 5, l["lcsc"], "link", link=LCSC_URL.format(l["lcsc"]), name="bom_lcsc_%d" % i)
        s.put(r, 6, l["mpn"], "text")
        s.put(r, 7, l["mfr"], "text")
        s.put(r, 8, l["desc"], "text")
        s.put(r, 9, l["role"], "text")
        s.put(r, 10, "=LEN(B{0})-LEN(SUBSTITUTE(B{0},\",\",\"\"))+1".format(r), "calc", fmt="0", name="bom_qty_%d" % i)
        s.put(r, 11, l["pads"], "in", fmt="0", name="bom_pads_%d" % i)
        s.put(r, 12, l["type"], "est" if l["type_est"] else "in")
        s.put(r, 13, "JLC page", "link", link=JLC_PART_URL.format(l["lcsc"]))
        if l["stock"] is None:
            s.put(r, 14, "unknown", "est")
        else:
            s.put(r, 14, l["stock"], "in", fmt=INT0)
        s.put(r, 15, l["note"] or ("OK" if l["stock"] >= 1000 else ""), "warn" if l["note"] else "text")
        s.put(r, 16, l["cls"], "in")
        s.put(r, 17, "=INDEX({1},MATCH(P{0},{2},0))".format(r, s.rng("att_n_0", "att_n_3"), s.rng("att_c_0", "att_c_3")), "calc", fmt="0")
        for sc, cb, cu, ct, bn in (("A", 18, 19, 20, "$C$5"), ("B", 21, 22, 23, "$C$6")):
            s.put(r, cb, "=J{0}*{1}+Q{0}".format(r, bn), "calc", fmt="0", name="bom_buy_%s_%d" % (sc, i))
            s.put(r, cu, "=INDEX($AD{0}:$AI{0},MAX(1,COUNTIF($X{0}:$AC{0},\"<=\"&{1}{0})))".format(r, colname(cb)), "calc", fmt=USD4,
                  name="bom_up_%s_%d" % (sc, i))
            s.put(r, ct, "={1}{0}*{2}{0}".format(r, colname(cb), colname(cu)), "calc", fmt=USD4, name="bom_tot_%s_%d" % (sc, i))
        tiers = l["tiers"]
        for k in range(6):
            if k < len(tiers):
                s.put(r, 24 + k, tiers[k][0], "est" if l["est"] else "in", fmt=INT0)
                s.put(r, 30 + k, tiers[k][1], "est" if l["est"] else "in", fmt=USD4)
            else:
                s.put(r, 24 + k, None, "text")
                s.put(r, 30 + k, None, "text")
        if l["est"]:
            s.put(r, 36, l["src"], "warn", link=LCSC_URL.format(l["lcsc"]))
        else:
            s.put(r, 36, LCSC_URL.format(l["lcsc"]) + "  (read " + l["read"] + ")", "link", link=LCSC_URL.format(l["lcsc"]))
    t = r1 + 1
    s.put(t, 2, "TOTAL per board / per order", "tot")
    for c in range(3, 24):
        s.put(t, c, None, "tot")
    s.put(t, 10, "=SUM(J%d:J%d)" % (BOM_R0, r1), "tot", fmt="0", name="placements")
    s.put(t, 11, "=SUMPRODUCT(J%d:J%d,K%d:K%d)" % (BOM_R0, r1, BOM_R0, r1), "tot", fmt="0", name="joints")
    s.put(t, 20, "=SUM(T%d:T%d)" % (BOM_R0, r1), "tot", fmt=USD2, name="comps_A")
    s.put(t, 23, "=SUM(W%d:W%d)" % (BOM_R0, r1), "tot", fmt=USD2, name="comps_B")
    for k, lab in enumerate(("Lines (unique LCSC numbers = feeder-fee count)", "of which Extended library parts", "of which Basic library parts",
                             "Extra pieces for placement loss, included in the totals above (USD)")):
        s.merge(t + 1 + k, 2, 9, lab, "text", border=True)
    s.put(t + 1, 2, "Lines (unique LCSC numbers = feeder-fee count)", "text")
    s.put(t + 1, 10, "=COUNTA(E%d:E%d)" % (BOM_R0, r1), "calc", fmt="0", name="n_lines")
    s.put(t + 2, 2, "of which Extended library parts", "text")
    s.put(t + 2, 10, "=COUNTIF(L%d:L%d,\"Extended\")" % (BOM_R0, r1), "calc", fmt="0", name="n_ext")
    s.put(t + 3, 2, "of which Basic library parts", "text")
    s.put(t + 3, 10, "=COUNTIF(L%d:L%d,\"Basic\")" % (BOM_R0, r1), "calc", fmt="0", name="n_basic")
    s.put(t + 4, 2, "Extra pieces for placement loss, included in the totals above (USD)", "text")
    s.put(t + 4, 20, "=SUMPRODUCT(Q%d:Q%d,S%d:S%d)" % (BOM_R0, r1, BOM_R0, r1), "calc", fmt=USD2, name="extra_cost_A")
    s.put(t + 4, 23, "=SUMPRODUCT(Q%d:Q%d,V%d:V%d)" % (BOM_R0, r1, BOM_R0, r1), "calc", fmt=USD2, name="extra_cost_B")
    # attrition table
    a = att0 - 1
    s.put(a, 2, "Placement-loss classes (ESTIMATES - JLC publishes no table; the cart shows the real quantities)", "bold", border=False)
    s.head(att0, [None, "Class", "Extra pieces", "Applies to"])
    for k, (cls, nx, what) in enumerate(ATTRITION):
        rr = att0 + 1 + k
        s.put(rr, 2, cls, "text", name="att_c_%d" % k)
        s.put(rr, 3, nx, "est", fmt="0", name="att_n_%d" % k)
        s.merge(rr, 4, 9, what, "text", border=True)
    # parts without LCSC number
    w = att0 + len(ATTRITION) + 3
    s.merge(w - 1, 2, 9, "Parts without an LCSC number - NOT assembled by JLCPCB (hand-soldered wires)", "sub", border=True)
    s.head(w, [None, "Ref", "Value", "Footprint", None, None, None, "Description"])
    for k, rc in enumerate(not_assembled()):
        rr = w + 1 + k
        s.put(rr, 2, rc["ref"], "text")
        s.put(rr, 3, rc["value"], "text")
        s.put(rr, 4, rc["fp"].split(":")[-1], "text")
        s.merge(rr, 8, 9, rc["desc"], "text", border=True)
    e0 = w + len(not_assembled()) + 3
    s.merge(e0 - 1, 2, 9, "Bought parts (EXTERNAL_BOM in flashka_parts.py) - see sheet 'Bought parts'", "sub", border=True)
    s.head(e0, [None, "Ref", "What", None, None, None, None, "How it is bought"])
    for k, (ref, what, lc, how) in enumerate(EXTERNAL_BOM):
        rr = e0 + 1 + k
        s.put(rr, 2, ref, "text")
        s.merge(rr, 3, 7, what, "text", border=True)
        s.merge(rr, 8, 9, how, "text", border=True)
    ws.freeze_panes = "C%d" % BOM_R0
    autofit(s)
    ws.row_dimensions[BOM_HDR].height = 42
    return s


# ----------------------------------------------------------------------------------------------
# sheet: JLCPCB order
# ----------------------------------------------------------------------------------------------
def build_jlc(book, lines, H):
    S = "JLCPCB order"
    s = Sh(book, S, [46, 14, 24, 12, 14, 12, 14, 12, 46, 62])
    ws = s.ws
    s.put(1, 1, "JLCPCB order - bare PCB + Standard PCBA (parts on both sides)", "title")
    s.merge(2, 1, 10, "What you order at jlcpcb.com in ONE order: 5 bare 4-layer boards and the assembly (soldering of all SMD parts) of 2 or 5 of them. "
           "Column E = scenario A (you build 1 light), column G = scenario B (you build 5 lights). Every fee is a blue input with the date it was read and "
           "its URL: the fee page says 'Last updated on Sep 09, 2026' and was read on %s (v0.5 price check, not repeated in v0.6; only the X-ray count changed). Prices change - re-check before you pay." % V05_DATE)
    s.merge(3, 1, 10, "Colour code: blue = typed-in number, blue on amber = ESTIMATE (no public price), black = formula, green = taken from another sheet.", "note")
    r = 5
    # ---- 1. cart settings
    s.merge(r, 1, 10, "1. What to select in the JLCPCB cart (https://cart.jlcpcb.com/quote)", "sub", border=True)
    r += 1
    s.put(r, 1, "Setting", "head")
    s.merge(r, 2, 4, "Value", "head", border=True)
    s.merge(r, 5, 10, "Why / what to watch", "head", border=True)
    rows = [
        ("Base material / layers", "FR-4, 4 layers", "The board is designed as a 4-layer stack-up. Do not change the layer count."),
        ("Dimensions", "24.0 x 16.5 mm (JLC reads it from the Gerber)", "Outline from housing_interface.json pcb_outline, see section 2."),
        ("PCB quantity", "5", "JLCPCB minimum. Four spare boards cost almost nothing and cover first-article problems."),
        ("Different designs", "1", ""),
        ("PCB thickness", "0.8 mm", "The housing is built around a 0.8 mm board (pcb_t 0.8)."),
        ("Surface finish", "ENIG (immersion gold)", "Flat pads for the fine-pitch module and LED; costs extra, included in the bare-PCB estimate."),
        ("Solder mask / silkscreen / copper", "Defaults (green mask, white silkscreen, 1 oz outer, 0.5 oz inner)", "Default options carry no surcharge."),
        ("Order number on the board", "Default (JLC prints a code in a free area)", "Removing the code costs extra."),
        ("PCB Assembly", "ON - Standard PCBA, assemble BOTH sides", "Economic PCBA cannot do two-sided boards; set-up and stencil are charged per side."),
        ("Assembly quantity", "2 (for one light) or 5", "JLCPCB assembles from 2 boards. The extra board is your spare."),
        ("Upload", "%s, then %s and %s" % (ofp("FlashKa_main_gerbers.zip"), ofp("BOM_JLCPCB.csv"), ofp("CPL_JLCPCB.csv")),
         "The three files of %s (written by tools/kicad/build_all.py, copied there by the packaging step). Check that all %d BOM lines are matched (no red rows) "
         "and look at the placement preview." % (ofd("1_JLCPCB"), len(lines))),
        ("Confirm parts placement", "Yes (recommended for the first order)", "JLC sends you a photo of the placed parts for your OK; the rotation of U4, U1, U2, U3, U5, Q1, Q2, Q4, Q5, J1, SW1-SW3, LED3 and LED4 is the classic problem. For the new SW1-SW3 (SKRKAEE020) and LED3/LED4 (NH-B1010RGBT) the rotation and pin 1 in the JLC library are NOT verified: look at the placement preview."),
        ("Shipping", "Your choice (see sheet 'Hidden costs')", "Choose DDP / 'taxes paid' so the VAT is collected at checkout and nothing is asked at your door."),
    ]
    for (a, b, c) in rows:
        r += 1
        s.put(r, 1, a, "text")
        s.merge(r, 2, 4, b, "text", border=True)
        s.merge(r, 5, 10, c, "text", border=True)
    # ---- 2. board outline
    r += 2
    s.merge(r, 1, 10, "2. Board outline (read from housing_interface.json -> pcb_outline, mm)", "sub", border=True)
    r += 1
    s.head(r, ["Vertex", "x (mm)", "y (mm)", "next x", "next y", "x*next y - next x*y"])
    poly = H["pcb_outline"]
    v0 = r + 1
    for i, (x, y) in enumerate(poly):
        r += 1
        nxt = v0 + (i + 1) % len(poly)
        s.put(r, 1, "vertex %d" % (i + 1), "text")
        s.put(r, 2, round(x, 4), "in", fmt="0.00", name="ov_x_%d" % i)
        s.put(r, 3, round(y, 4), "in", fmt="0.00", name="ov_y_%d" % i)
        s.put(r, 4, "=B%d" % nxt, "calc", fmt="0.00")
        s.put(r, 5, "=C%d" % nxt, "calc", fmt="0.00")
        s.put(r, 6, "=B%d*E%d-D%d*C%d" % (r, r, r, r), "calc", fmt="0.0000")
    v1 = r
    r += 1
    s.put(r, 1, "Board width (mm)", "bold")
    s.put(r, 2, "=MAX(B%d:B%d)-MIN(B%d:B%d)" % (v0, v1, v0, v1), "calc", fmt="0.0", name="pcb_w")
    r += 1
    s.put(r, 1, "Board height (mm)", "bold")
    s.put(r, 2, "=MAX(C%d:C%d)-MIN(C%d:C%d)" % (v0, v1, v0, v1), "calc", fmt="0.0", name="pcb_h")
    r += 1
    s.put(r, 1, "Board area (cm2, shoelace formula)", "bold")
    s.put(r, 2, "=ABS(SUM(F%d:F%d))/2/100" % (v0, v1), "calc", fmt="0.00", name="pcb_area_cm2")
    s.merge(r, 3, 10, "Two corners are chamfered 1.3 mm, so the area is a little smaller than width x height. JLCPCB measures the Gerber itself; the area only feeds the tiny packing fee.", "note")
    # ---- 3. quantities
    r += 2
    s.merge(r, 1, 10, "3. Quantities (JLCPCB minimums: 5 bare boards, assembly from 2 boards)", "sub", border=True)
    for key, lab in (("min_asm", "Minimum boards JLCPCB assembles"), ("min_pcb", "Minimum bare boards per design"),
                     ("sides", "Assembled sides (double-sided)"), ("xray_per_board", "X-ray inspected parts per board (optional)")):
        r += 1
        s.param(r, key, lab, fmt="0")
    r += 1
    s.head(r, ["", None, None, None, "Scenario A", None, "Scenario B"])
    r += 1
    s.put(r, 1, "Lights you build", "text")
    s.put(r, 5, "=" + s.ref("lightsA"), "x", fmt="0")
    s.put(r, 7, "=" + s.ref("lightsB"), "x", fmt="0")
    rl = r
    r += 1
    s.put(r, 1, "Boards assembled by JLCPCB = MAX(lights, minimum)", "text")
    s.put(r, 5, "=MAX(E%d,%s)" % (rl, s.ref("min_asm")), "calc", fmt="0", name="boards_A")
    s.put(r, 7, "=MAX(G%d,%s)" % (rl, s.ref("min_asm")), "calc", fmt="0", name="boards_B")
    rb = r
    r += 1
    s.put(r, 1, "Bare PCBs ordered (sold in steps of 5)", "text")
    s.put(r, 5, "=CEILING(MAX(%s,E%d),5)" % (s.ref("min_pcb"), rb), "calc", fmt="0", name="pcbs_A")
    s.put(r, 7, "=CEILING(MAX(%s,G%d),5)" % (s.ref("min_pcb"), rb), "calc", fmt="0", name="pcbs_B")
    # ---- 4. bare PCB
    r += 2
    s.merge(r, 1, 10, "4. Bare PCB fabrication (4 layers, 0.8 mm, ENIG, 24.0 x 16.5 mm) - the price is shown by JLCPCB only AFTER the Gerber upload", "sub", border=True)
    r += 1
    s.param(r, "pcb_fab5", "Bare PCBs, price for 5 boards (ESTIMATE)")
    r += 1
    s.param(r, "pcb_fab_low", "  low end of the range (information)")
    r += 1
    s.param(r, "pcb_fab_high", "  high end of the range (information)")
    r += 1
    s.merge(r, 1, 10, "Anchors used for the estimate: a 100 x 100 mm 4-layer board costs about $32.90 for 5 (%s, 2026); ENIG adds roughly 12-20 %% on small runs (same source) and "
            "one forum post quotes $16 for ENIG on a small run (%s, 2020); thickness 0.8 mm is a normal option; the board here is 16 times smaller than 100 x 100 mm. "
            "Real price: upload %s at %s, choose the options of section 1 and type the price shown for 5 boards into the amber cell above." % (U_PCBSYNC, U_GHI, ofp("FlashKa_main_gerbers.zip"), U_QUOTE), "note")
    r += 1
    s.put(r, 1, "Bare PCB cost (price for 5 x boards ordered / 5)", "bold")
    s.put(r, 5, "=%s*%s/5" % (s.ref("pcb_fab5"), s.ref("pcbs_A")), "calc", fmt=USD2, name="fab_A")
    s.put(r, 7, "=%s*%s/5" % (s.ref("pcb_fab5"), s.ref("pcbs_B")), "calc", fmt=USD2, name="fab_B")
    # ---- 5. fees
    r += 2
    s.merge(r, 1, 10, "5. Standard PCBA fees (JLCPCB 'PCB assembly price' page, last updated Sep 09, 2026, read %s) - %s" % (V05_DATE, U_FEES), "sub", border=True)
    r += 1
    s.head(r, ["Fee", "Rate (USD)", "Unit", "Qty A", "Cost A (USD)", "Qty B", "Cost B (USD)", "Date read", "Source", "Note"])
    ws.row_dimensions[r].height = 28
    fee_first = r + 1

    def fee(key, nm, label, qa, qb, qkind="calc", rate_text=None, cost=None, unit=None):
        nonlocal r
        r += 1
        p = P[key]
        s.put(r, 1, label, "text")
        if rate_text is None:
            fmt = USD4 if key in ("smt_joint", "prereflow") else ('"$"0.00000' if key == "pack_cm2" else USD2)
            s.put(r, 2, p["v"], "est" if p["e"] else "in", fmt=fmt, name=key)
        else:
            s.put(r, 2, rate_text, "text")
        s.put(r, 3, unit or p["u"], "text")
        s.put(r, 4, qa, qkind)
        s.put(r, 6, qb, qkind)
        ca = cost("D") if cost else "=B%d*D%d" % (r, r)
        cb = cost("F") if cost else "=B%d*F%d" % (r, r)
        s.put(r, 5, ca, "calc", fmt=USD2, name="fee_%s_A" % nm)
        s.put(r, 7, cb, "calc", fmt=USD2, name="fee_%s_B" % nm)
        s.put(r, 8, p["d"], "text")
        s.put(r, 9, p["src"], "link" if p["src"] else "text", link=p["src"] or None)
        s.put(r, 10, p["n"], "text")

    jn = s.ref("joints")
    sd = "=" + s.ref("sides")
    fee("setup_side", "setup", "Set-up fee (Standard PCBA), per assembled side", sd, sd)
    fee("stencil_side", "stencil", "Stencil (Standard PCBA), per assembled side", sd, sd)
    fee("smt_joint", "smt", "SMT assembly, per solder joint (joints per board x boards)", "=%s*%s" % (jn, s.ref("boards_A")), "=%s*%s" % (jn, s.ref("boards_B")))
    fee("feeder_unique", "feeder", "Feeder loading, per unique part (Basic and Extended alike)", "=" + s.ref("n_lines"), "=" + s.ref("n_lines"))
    fee("ext_extra", "ext", "Extra fee per unique Extended part (Economic PCBA only - none in Standard)", "=" + s.ref("n_ext"), "=" + s.ref("n_ext"))
    fee("eng_fee", "eng", "Engineering fee (not on the 2026 page)", 1, 1, qkind="in")
    fee("confirm", "confirm", "Confirm parts placement (optional, recommended)", 1, 1, qkind="in")
    xl = s.rng("xr_lo_0", "xr_lo_6")
    xp = s.rng("xr_pr_0", "xr_pr_6")
    fee("xray_per_board", "xray", "X-ray inspection (optional): parts inspected = parts per board x boards", "=%s*%s" % (s.ref("xray_per_board"), s.ref("boards_A")),
        "=%s*%s" % (s.ref("xray_per_board"), s.ref("boards_B")), rate_text="tiered (section 7)", unit="USD per part (tiered)",
        cost=lambda q: "=IF(%s%d=0,0,%s%d*INDEX(%s,MATCH(%s%d,%s,1)))" % (q, r, q, r, xp, q, r, xl))
    fee("panel_board", "panel", "Panelisation processing by JLC (small board), per board", "=" + s.ref("boards_A"), "=" + s.ref("boards_B"))
    fee("pack_base", "pack_base", "Packing (Standard PCBA), base per order", 1, 1, qkind="in")
    fee("pack_cm2", "pack_area", "Packing, per cm2 of board (board area x boards)", "=%s*%s" % (s.ref("pcb_area_cm2"), s.ref("boards_A")),
        "=%s*%s" % (s.ref("pcb_area_cm2"), s.ref("boards_B")))
    for key, nm, lab in (("hand_labour", "hand", "Hand-soldering labour (not needed) - quantity 0"),
                         ("prereflow", "prereflow", "'Pre-reflow soldering' per joint (unexplained row) - quantity 0"),
                         ("single_board", "single", "Single-board surcharge (prototypes exempt) - quantity 0"),
                         ("fixture", "fixture", "Fixtures (not needed) - quantity 0"),
                         ("storage", "storage", "Stencil / fixture storage (not needed) - quantity 0"),
                         ("large", "large", "Large-size surcharge (not applicable) - quantity 0")):
        fee(key, nm, lab, 0, 0, qkind="in")
    fee_last = r
    r += 1
    s.put(r, 1, "Assembly fees, subtotal", "tot")
    for c in range(2, 11):
        s.put(r, c, None, "tot")
    s.put(r, 5, "=SUM(E%d:E%d)" % (fee_first, fee_last), "tot", fmt=USD2, name="fees_A")
    s.put(r, 7, "=SUM(G%d:G%d)" % (fee_first, fee_last), "tot", fmt=USD2, name="fees_B")
    # ---- 6. totals
    r += 2
    s.merge(r, 1, 10, "6. Total of the JLCPCB order (before shipping, VAT and customs)", "sub", border=True)
    r += 1
    s.head(r, ["", None, None, None, "Scenario A", None, "Scenario B"])
    r += 1
    s.put(r, 1, "Bare PCBs", "text")
    s.put(r, 5, "=" + s.ref("fab_A"), "calc", fmt=USD2)
    s.put(r, 7, "=" + s.ref("fab_B"), "calc", fmt=USD2)
    ra = r
    r += 1
    s.put(r, 1, "Assembly fees (section 5)", "text")
    s.put(r, 5, "=" + s.ref("fees_A"), "calc", fmt=USD2)
    s.put(r, 7, "=" + s.ref("fees_B"), "calc", fmt=USD2)
    r += 1
    s.put(r, 1, "Components bought by JLCPCB (sheet 'Main PCB BOM')", "text")
    s.put(r, 5, "=" + s.ref("comps_A"), "x", fmt=USD2)
    s.put(r, 7, "=" + s.ref("comps_B"), "x", fmt=USD2)
    s.merge(r, 9, 10, "Includes the extra pieces JLC buys for placement loss (they are billed and thrown away).", "note")
    r += 1
    s.put(r, 1, "  of which extra pieces for placement loss (information)", "text")
    s.put(r, 5, "=" + s.ref("extra_cost_A"), "x", fmt=USD2)
    s.put(r, 7, "=" + s.ref("extra_cost_B"), "x", fmt=USD2)
    r += 1
    s.put(r, 1, "TOTAL JLCPCB order before shipping/VAT (USD)", "tot")
    for c in range(2, 5):
        s.put(r, c, None, "tot")
    s.put(r, 5, "=E%d+E%d+E%d" % (ra, ra + 1, ra + 2), "tot", fmt=USD2, name="jlc_goods_A")
    s.put(r, 6, None, "tot")
    s.put(r, 7, "=G%d+G%d+G%d" % (ra, ra + 1, ra + 2), "tot", fmt=USD2, name="jlc_goods_B")
    rt = r
    r += 1
    s.put(r, 1, "  the same in EUR", "text")
    s.put(r, 5, "=E%d/%s" % (rt, s.ref("fx")), "calc", fmt=EUR2, name="jlc_goods_eur_A")
    s.put(r, 7, "=G%d/%s" % (rt, s.ref("fx")), "calc", fmt=EUR2, name="jlc_goods_eur_B")
    r += 1
    s.put(r, 1, "Distance below the EUR 150 IOSS line (negative = above)", "bold")
    s.put(r, 5, "=%s-E%d" % (s.ref("ioss_eur"), r - 1), "calc", fmt=EUR2, name="jlc_line_gap_A")
    s.put(r, 7, "=%s-G%d" % (s.ref("ioss_eur"), r - 1), "calc", fmt=EUR2, name="jlc_line_gap_B")
    s.merge(r, 9, 10, "Up to EUR 150 JLC collects 21 % VAT at checkout and the flat EUR 3 duty; above EUR 150 the parcel needs formal customs clearance and the carrier adds a "
            "fee of about EUR 15. Scenario A sits very close to this line, so its VAT/customs cost can jump by about EUR 10-15 with a small price change - see sheet 'Hidden costs'.", "note")
    rg = r
    r += 1
    s.put(r, 1, "Route", "text")
    s.put(r, 5, "=IF(E%d<0,\"formal clearance\",\"IOSS\")" % rg, "calc")
    s.put(r, 7, "=IF(G%d<0,\"formal clearance\",\"IOSS\")" % rg, "calc")
    # ---- 7. xray table
    r += 2
    s.merge(r, 1, 10, "7. X-ray price table (per inspected part, by the total number of inspected parts in the order) - %s, read %s" % (U_FEES, V05_DATE), "sub", border=True)
    r += 1
    s.head(r, ["Total parts inspected from", "USD per part"])
    for i, (lo, pr) in enumerate(XRAY_TIERS):
        r += 1
        s.put(r, 1, lo, "in", fmt="0", name="xr_lo_%d" % i)
        s.put(r, 2, pr, "in", fmt='"$"0.000', name="xr_pr_%d" % i)
    # ---- 8. notes
    r += 2
    s.merge(r, 1, 10, "8. Things to know", "sub", border=True)
    notes = [
        "Basic vs Extended: %d of the %d BOM lines are Basic, %d are Extended (JLC part type read on jlcpcb.com/partdetail/<LCSC> on %s; the two new lines C115357 and C25104 are ASSUMED, their pages could not be read on %s). In the 2026 Standard PCBA price list every unique part pays the same feeder-loading fee, Basic or Extended, so Extended parts cost no extra here (the separate $3.07 per Extended part belongs to Economic PCBA; the input above is kept at 0). Re-check this if your cart shows an extended-part line." % (sum(1 for l in lines if l["type"] == "Basic"), len(lines), sum(1 for l in lines if l["type"] == "Extended"), V05_DATE, CHECK),
        "Parts that JLC cannot supply (out of stock) stop the order: JLC tells you by e-mail and you may substitute. Low-stock lines are marked in sheet 'Main PCB BOM'. Retail stock at LCSC is not JLC's warehouse stock.",
        "Placement loss: JLC buys a few pieces more than needed (they are billed inside the component price, see " + U_FAQ2 + "). The extra counts are estimates in sheet 'Main PCB BOM'.",
        "JLC assembles from 2 boards (" + U_ASM + "). Going from 2 to 5 assembled boards only adds the per-joint price, more components, the panelisation fee and the optional X-ray (compare columns E and G of section 6).",
        "Pre-reflow soldering, hand soldering, fixtures, storage and the large-size fee are listed on the fee page but do not apply to this board; they are kept at quantity 0 so you can switch them on if your quote shows them.",
        "ENIG, 0.8 mm and 4 layers are all standard options at JLCPCB (" + U_CAPAB + "), only the price of the bare board is unknown until you upload the Gerber.",
    ]
    for t in notes:
        r += 1
        s.merge(r, 1, 10, t, "text", border=True)
    ws.freeze_panes = "A5"
    autofit(s)
    return s


# ----------------------------------------------------------------------------------------------
# sheet: Housing
# ----------------------------------------------------------------------------------------------
def build_housing(book, hparts, hsrc, H):
    S = "Housing"
    s = Sh(book, S, [40, 15, 12, 12, 12, 14, 12, 12, 12, 34, 58])
    ws = s.ws
    s.put(1, 1, "Housing - aluminium tray + lid and stainless caps (JLCCNC), resin print kit (JLC3DP)", "title")
    s.merge(2, 1, 11, "Tray and lid are CNC-milled from aluminium 6061-T6 with bead blast + black anodize and laser marking at JLCCNC. The three caps (cap_main x1, cap_slide x2 per light) "
            "are turned from SUS304 stainless steel and bead blasted, also at JLCCNC. The RF window insert, LED spacer ring, antenna spacer with floor plug, light-pipe tube and the resin "
            "copies of the three caps are printed in translucent SLA resin 8001 at JLC3DP as ONE print kit: seven parts joined by 1 mm sprues, which you cut apart at home. JLCCNC and "
            "JLC3DP show their real price only after you upload the files, and JLCCNC publishes no per-part price at all, so every price on this sheet is an ESTIMATE made from the "
            "volume, the bounding box and the finish with the method written below. When you have the instant quote, type it into the 'real quote' cells (sections 6, 7 and 8): the "
            "workbook then uses your number.")
    s.merge(3, 1, 11, "Geometry source: %s. Files to upload: %s (JLCCNC) and %s (JLC3DP); the JLCCNC drawings there are cad/FlashKa_tray_drawing.pdf, FlashKa_lid_drawing.pdf, "
            "FlashKa_cap_main_drawing.pdf and FlashKa_cap_slide_drawing.pdf renamed to the names of their STEP files (FlashKa_tray.pdf, FlashKa_lid.pdf, FlashKa_cap_main.pdf, "
            "FlashKa_cap_slide.pdf)." % (hsrc, ofd("2_JLCCNC"), ofd("3_JLC3DP")), "note")
    r = 5
    s.merge(r, 1, 11, "1. Parts and geometry (volumes from housing_interface.json 'volumes_mm3', for the print kit and the laser sleeve from their STL files; boxes from "
            "'tray_bbox' and the STL files)", "sub", border=True)
    r += 1
    s.head(r, ["Part", "Process", "Box X (mm)", "Box Y (mm)", "Box Z (mm)", "Volume (mm3)", "Mass (g)", "Per light", "Spare per order", "File (STEP / STL)", "Note"])
    ws.row_dimensions[r].height = 28

    def part_file(p):
        if p.get("in_kit"):
            return "%s/%s.stl (geometry only - not uploaded, it is in the kit)" % (HOUSING_DIR, p["key"])
        if p["proc"] in ("CNC", "STEEL"):
            return "%s + %s.pdf" % (ofp(p["key"] + ".step"), p["key"])
        return ofp(p["key"] + ".stl")
    proc_name = {"CNC": "CNC aluminium", "STEEL": "CNC stainless", "RESIN": "SLA resin"}
    for p in hparts:
        r += 1
        i = p["id"]
        s.put(r, 1, p["label"], "bold" if p.get("kit") else "text")
        s.put(r, 2, proc_name[p["proc"]], "text")
        for k, ax in enumerate("xyz"):
            s.put(r, 3 + k, round(p["box"][k], 2), "in", fmt="0.00", name="h_%s_%s" % (ax, i))
        s.put(r, 6, round(p["vol"], 1), "in", fmt="#,##0.0", name="h_vol_%s" % i)
        s.put(r, 7, p["mass"], "in", fmt="0.00")
        s.put(r, 8, p["per_light"], "in", fmt="0", name="h_per_%s" % i)
        s.put(r, 9, p["spare"], "in", fmt="0", name="h_spare_%s" % i)
        s.put(r, 10, part_file(p), "text")
        s.put(r, 11, p["note"], "text")
    # ---- 2. CNC method
    r += 2
    s.merge(r, 1, 11, "2. JLCCNC estimate - method (all inputs are ESTIMATES; JLCCNC publishes no price list, " + U_JLCNC_COST + ")", "sub", border=True)
    r += 1
    s.merge(r, 1, 11, "Cost of one aluminium part = aluminium (stock block weight x price) + machining (minutes x rate x complexity) + threads + finish + laser marking. "
            "Stock block = bounding box + allowance on every side. Machining minutes = material to remove / removal rate + minutes for fine features (grooves, holes, pockets: section 4). "
            "Per order you also pay set-ups (each re-clamping of the part), the anodizing lot fee and the marking set-up once. Calibrated in v0.5 so that one tray + lid costs about the "
            "same as the v0.4 estimate (tray $31, lid $12) plus finish and set-ups; v0.6 keeps these inputs and changes only what the new design changes (sections 4 and 5).", "note")
    for key, lab in (("al_kg", "Aluminium 6061 price (USD per kg)"), ("al_dens", "Aluminium density (g per cm3)"), ("allow", "Stock allowance per side (mm)"),
                     ("mrr", "Material removal rate (cm3 per minute)"), ("rate_min", "Machine time rate (USD per minute)"),
                     ("setup_fee", "Set-up cost (USD per set-up)"), ("tap_fee", "Tapping (USD per thread)"),
                     ("groove_min_m", "V-groove machining time (minutes per metre)"), ("mark_on", "Laser marking: 1 = ordered, 0 = not ordered"),
                     ("mark_face", "Laser marking (USD per marked face)"), ("mark_lot", "Laser marking set-up (USD per order)")):
        r += 1
        s.param(r, key, lab, c_end=11)
    # ---- 3. finishes
    r += 2
    s.merge(r, 1, 11, "3. Surface finish choices at JLCCNC for aluminium (prices are ESTIMATES; " + U_JLCNC_FIN + ", read " + V05_DATE + " and again " + RESEARCH_DATE + ")", "sub", border=True)
    r += 1
    s.head(r, ["Finish", "Tray (USD per part)", "Lid (USD per part)", "Lot fee (USD per order)"])
    s.merge(r, 5, 11, "What you get", "head", border=True)
    ws.row_dimensions[r].height = 28
    f0 = r + 1
    for i, (nm, tf, lf, lot, note) in enumerate(FINISHES):
        r += 1
        s.put(r, 1, nm, "text", name="fin_name_%d" % i)
        s.put(r, 2, tf, "est", fmt=USD2, name="fin_tray_%d" % i)
        s.put(r, 3, lf, "est", fmt=USD2, name="fin_lid_%d" % i)
        s.put(r, 4, lot, "est", fmt=USD2, name="fin_lot_%d" % i)
        s.merge(r, 5, 11, note, "text", border=True)
    f1 = r
    r += 1
    s.put(r, 1, "Chosen finish (drop-down)", "bold")
    s.merge(r, 2, 4, FINISH_DEFAULT, "in", border=True, name="finish_sel")
    dv = DataValidation(type="list", formula1="=$A$%d:$A$%d" % (f0, f1), allow_blank=False)
    ws.add_data_validation(dv)
    dv.add(ws.cell(row=r, column=2))
    s.merge(r, 5, 11, "Pick the finish here; the tray/lid/lot prices below follow. The design assumes 'Bead blast + black anodize' (type II, 8-12 um on the drawings; JLCCNC range 8-25 um). "
            "The V grooves of the skin are 0.25 mm deep and stay visible after blasting and anodizing. The stainless caps are bead blasted only (JLCCNC offers no anodizing, passivation or "
            "polishing for stainless): their price is in section 7.", "note")
    nm_rng = s.rng("fin_name_0", "fin_name_%d" % (len(FINISHES) - 1))
    for lab, col_key, nmx in (("Finish cost per tray (USD)", "fin_tray", "fin_tray"), ("Finish cost per lid (USD)", "fin_lid", "fin_lid"),
                              ("Anodizing lot fee per order (USD)", "fin_lot", "fin_lot")):
        r += 1
        s.put(r, 1, lab, "text")
        s.put(r, 2, "=INDEX(%s,MATCH(%s,%s,0))" % (s.rng(col_key + "_0", col_key + "_%d" % (len(FINISHES) - 1)), s.ref("finish_sel"), nm_rng),
              "calc", fmt=USD2, name=nmx)
    # ---- 4. fine-feature time
    r += 2
    s.merge(r, 1, 11, "4. Fine-feature time of the aluminium parts - what changed from v0.5 (ESTIMATES; the v0.6 skin adds V-groove seams and marking, the knurl and the side grooves are gone)", "sub", border=True)
    r += 1
    s.merge(r, 1, 11, "v0.5 priced all fine work as one lump per part (tray 36 min, lid 8 min). v0.6 keeps that lump, takes out the features that no longer exist and adds the new ones. "
            "V-groove work is counted in millimetres at ONE rate (minutes per metre, section 2) for the grooves that go and the grooves that come, so the groove part of the change "
            "follows the real geometry (the skin lengths are read from housing_interface.json 'skin_layout'). Other changes are typed-in minutes. Laser marking is a separate cost (section 5).", "note")
    r += 1
    s.head(r, ["Feature", "Tray (mm or min)", "Lid (mm or min)", "Unit", "Tray (min)", "Lid (min)"])
    s.merge(r, 7, 11, "Basis", "head", border=True)
    ws.row_dimensions[r].height = 28
    fr0 = r + 1
    gm = s.ref("groove_min_m")
    for fid, lab, kind, tv, lv, note in feature_rows(H):
        r += 1
        s.put(r, 1, lab, "text")
        s.put(r, 2, tv, "est" if kind == "min" else "in", fmt="0.0")
        s.put(r, 3, lv, "est" if kind == "min" else "in", fmt="0.0")
        s.put(r, 4, "min" if kind == "min" else "mm of V-groove", "text")
        for c, src in ((5, "B"), (6, "C")):
            s.put(r, c, ("=%s%d" % (src, r)) if kind == "min" else ("=%s%d/1000*%s" % (src, r, gm)), "calc", fmt="0.00")
        s.merge(r, 7, 11, note, "text", border=True)
    fr1 = r
    r += 1
    s.put(r, 1, "Fine-feature time, v0.6 (min)", "tot")
    for c in (2, 3, 4):
        s.put(r, c, None, "tot")
    s.put(r, 5, "=SUM(E%d:E%d)" % (fr0, fr1), "tot", fmt="0.00", name="feat_tray")
    s.put(r, 6, "=SUM(F%d:F%d)" % (fr0, fr1), "tot", fmt="0.00", name="feat_lid")
    s.merge(r, 7, 11, "v0.5 had 36.0 min (tray) and 8.0 min (lid). Total V-groove length: v0.5 %.0f mm, v0.6 %.0f mm (tray %.0f + lid %.0f)."
            % (2 * V05_GEOM["knurl_mm"] + V05_GEOM["side_groove_mm"], sum(skin_lengths(H)), skin_lengths(H)[0], skin_lengths(H)[1]), "note")
    # ---- 5. CNC per part
    r += 2
    s.merge(r, 1, 11, "5. JLCCNC estimate - one aluminium part", "sub", border=True)
    r += 1
    s.head(r, ["Step", "Tray", "Lid"])
    s.merge(r, 4, 11, "How it is computed", "head", border=True)
    cnc = [p for p in hparts if p["proc"] == "CNC"]
    al = s.ref("allow")

    def row(label, fn, fmt, kind, how, nm=None):
        nonlocal r
        r += 1
        s.put(r, 1, label, "text")
        for k, p in enumerate(cnc):
            v = fn(p, r)
            s.put(r, 2 + k, v, kind, fmt=fmt, name=("%s_%s" % (nm, p["id"])) if nm else None)
        s.merge(r, 4, 11, how, "text", border=True)
        return r

    def cl(p):
        return colname(2 + cnc.index(p))
    ra = row("Stock block volume (cm3)", lambda p, rr: "=(%s+2*%s)*(%s+2*%s)*(%s+2*%s)/1000" % (s.ref("h_x_" + p["id"]), al, s.ref("h_y_" + p["id"]), al, s.ref("h_z_" + p["id"]), al),
             "0.00", "calc", "(X + 2 x allowance) x (Y + 2 x allowance) x (Z + 2 x allowance) / 1000. The v0.6 lid is 5.2 mm tall (hold-down bosses), so its block is much bigger than the 1.5 mm plate of v0.5.", "cnc_stock")
    rb = row("Part volume (cm3)", lambda p, rr: "=%s/1000" % s.ref("h_vol_" + p["id"]), "0.00", "calc", "volume / 1000")
    rc = row("Material to remove (cm3)", lambda p, rr: "=%s%d-%s%d" % (cl(p), ra, cl(p), rb), "0.00", "calc", "stock block - part", "cnc_removed")
    row("Aluminium cost (USD)", lambda p, rr: "=%s%d*%s/1000*%s" % (cl(p), ra, s.ref("al_dens"), s.ref("al_kg")), USD2, "calc",
        "stock volume x density / 1000 x price per kg (you pay for the whole block)", "cnc_mat")
    rf = row("Fine-feature time (min)", lambda p, rr: "=" + s.ref("feat_" + p["id"]), "0.00", "calc", "from section 4 (v0.5: tray 36.0, lid 8.0)")
    rm = row("Machining time (min)", lambda p, rr: "=%s%d/%s+%s%d" % (cl(p), rc, s.ref("mrr"), cl(p), rf), "0.0", "calc",
             "material to remove / removal rate + fine-feature time", "cnc_min")
    rx = row("Complexity factor", lambda p, rr: p["factor"], "0.00", "est",
             "ESTIMATE, v0.5 -> v0.6: tray 1.00 -> 1.10, because the frames of the skin wrap round the rounded corners and the two sides (indexed or 4th-axis work), where v0.5 had four straight side grooves; "
             "lid 1.25 -> 1.30, a 1.5 mm plate that now also carries bosses up to 5.2 mm tall and a 0.6 mm lip (clamping, vibration)", "factor")
    rh = row("Machining cost (USD)", lambda p, rr: "=%s%d*%s*%s%d" % (cl(p), rm, s.ref("rate_min"), cl(p), rx), USD2, "calc",
             "minutes x rate x complexity factor", "cnc_mach")
    rt = row("Threads to cut (number)", lambda p, rr: p["taps"], "0", "in", "Tray: 4 x M1.6 (lid screws) + 1 x M2 (laser set screw). Lid: none (clearance holes).", "taps")
    rtc = row("Tapping cost (USD)", lambda p, rr: "=%s%d*%s" % (cl(p), rt, s.ref("tap_fee")), USD2, "calc", "threads x cost per thread")
    rfin = row("Finish cost per part (USD)", lambda p, rr: "=" + s.ref("fin_tray" if p["id"] == "tray" else "fin_lid"), USD2, "calc", "from section 3 (chosen finish)")
    rmf = row("Faces to laser-mark (number)", lambda p, rr: p["marks"], "0", "in",
              "Tray: bottom, -Y side (USB-C side), +Y side (S2 side) = FlashKa_marking_bottom / _minus_y / _plus_y.dxf. Lid: top face = FlashKa_marking_lid_class2.dxf "
              "(or _class3R.dxf for a module above 1 mW).", "marks")
    row("Laser marking cost (USD)", lambda p, rr: "=%s*%s%d*%s" % (s.ref("mark_on"), cl(p), rmf, s.ref("mark_face")), USD2, "calc",
        "marking switch x faces x cost per face (the set-up is paid once per order, section 6)", "cnc_mark")
    row("Variable cost per part (USD)", lambda p, rr: "=%s%d+%s%d+%s%d+%s%d+%s%d" % (cl(p), ra + 3, cl(p), rh, cl(p), rtc, cl(p), rfin, cl(p), rmf + 1), USD2, "bold",
        "aluminium + machining + tapping + finish + laser marking", "cnc_var")
    rs = row("Set-ups (number)", lambda p, rr: p["setups"], "0", "in",
             "ESTIMATE, v0.5 -> v0.6: tray 3 -> 5 (top, bottom, -Y side, +Y side, ends), lid 2 -> 3 (top, bottom, sides and lip); the skin needs the side faces", "setups")
    row("Set-up cost per order (USD)", lambda p, rr: "=%s%d*%s" % (cl(p), rs, s.ref("setup_fee")), USD2, "calc", "set-ups x set-up cost, paid once per order", "cnc_setup")
    # ---- 6. aluminium totals
    r += 2
    s.merge(r, 1, 11, "6. JLCCNC total for the order - tray and lid (aluminium)", "sub", border=True)
    r += 1
    s.head(r, ["", "Scenario A", "Scenario B"])
    s.merge(r, 4, 11, "Note", "head", border=True)
    r += 1
    s.put(r, 1, "Lights you build", "text")
    s.put(r, 2, "=" + s.ref("lightsA"), "x", fmt="0")
    s.put(r, 3, "=" + s.ref("lightsB"), "x", fmt="0")
    rl = r
    pieces = {}
    for p in cnc:
        r += 1
        s.put(r, 1, "%s pieces ordered = lights x per light + spare" % p["id"].capitalize(), "text")
        s.put(r, 2, "=B%d*%s+%s" % (rl, s.ref("h_per_" + p["id"]), s.ref("h_spare_" + p["id"])), "calc", fmt="0")
        s.put(r, 3, "=C%d*%s+%s" % (rl, s.ref("h_per_" + p["id"]), s.ref("h_spare_" + p["id"])), "calc", fmt="0")
        pieces[p["id"]] = r
    r += 1
    s.put(r, 1, "Variable cost (pieces x cost per part)", "text")
    for k, colx in enumerate(("B", "C")):
        s.put(r, 2 + k, "=" + "+".join("%s%d*%s" % (colx, pieces[p["id"]], s.ref("cnc_var_" + p["id"])) for p in cnc), "calc", fmt=USD2)
    rv = r
    r += 1
    s.put(r, 1, "Set-ups + anodizing lot fee + marking set-up (once per order)", "text")
    for k in range(2):
        s.put(r, 2 + k, "=" + "+".join(s.ref("cnc_setup_" + p["id"]) for p in cnc) + "+" + s.ref("fin_lot") + "+" + s.ref("mark_on") + "*" + s.ref("mark_lot"), "calc", fmt=USD2)
    r += 1
    s.put(r, 1, "ESTIMATE of tray + lid (USD)", "bold")
    s.put(r, 2, "=B%d+B%d" % (rv, r - 1), "calc", fmt=USD2, name="cnc_alu_est_A")
    s.put(r, 3, "=C%d+C%d" % (rv, r - 1), "calc", fmt=USD2, name="cnc_alu_est_B")
    s.merge(r, 4, 11, "Ordering 5 sets at once is much cheaper per set than 1 set, because the set-ups, the anodizing lot fee and the marking set-up are paid once.", "note")
    re_ = r
    r += 1
    s.put(r, 1, "REAL instant-quote price for tray + lid (type it in, USD incl. finish and marking, without shipping)", "bold")
    s.put(r, 2, None, "in", fmt=USD2, name="cnc_alu_quote_A")
    s.put(r, 3, None, "in", fmt=USD2, name="cnc_alu_quote_B")
    s.merge(r, 4, 11, "Upload FlashKa_tray.step + FlashKa_tray.pdf and FlashKa_lid.step + FlashKa_lid.pdf from " + ofd("2_JLCCNC") + " (each drawing PDF has the name of its STEP file) at "
            + U_JLCNC + " and type the price shown for your quantity here. Leave empty to use the estimate.", "note")
    rq = r
    r += 1
    s.put(r, 1, "Tray + lid used in the totals (USD)", "tot")
    s.put(r, 2, "=IF(ISNUMBER(B%d),B%d,B%d)" % (rq, rq, re_), "tot", fmt=USD2, name="cnc_alu_A")
    s.put(r, 3, "=IF(ISNUMBER(C%d),C%d,C%d)" % (rq, rq, re_), "tot", fmt=USD2, name="cnc_alu_B")
    # ---- 7. stainless caps
    r += 2
    s.merge(r, 1, 11, "7. JLCCNC stainless caps (SUS304, turned, bead blasted) - ESTIMATE; fallback: the resin caps that are already in the print kit (cost 0 extra)", "sub", border=True)
    r += 1
    s.merge(r, 1, 11, "JLCCNC lists SUS304 as a CNC material (the only stainless grade) with bead blasting, brushing and laser marking as finishes; passivation and polishing are not offered for stainless "
            "(" + U_JLCNC_SS + ", " + U_JLCNC_FIN + ", read " + RESEARCH_DATE + "). It publishes NO per-part price: only 'CNC milling/turning from $5.00' (" + U_JLCNC_HOME + ") and a minimum order of one piece. "
            "The caps are tiny turned parts (flange dia 6.6 and 5.0 mm, 7.0 mm long, domed heads dia 5.8 and 3.4 mm): the price is dominated by the set-up and programming of each part number, "
            "so the estimate is a first-piece price plus a lower price for every further piece of the same cap in the same order. Instant quotes work up to 20 pieces.", "note")
    for key, lab in (("caps_steel", "Stainless caps ordered: 1 = yes, 0 = use the resin caps of the kit"), ("cap_first", "First piece of one cap type (USD)"),
                     ("cap_next", "Each further piece of the same cap type (USD)")):
        r += 1
        s.param(r, key, lab, c_end=11)
    r += 1
    s.head(r, ["Cap", "Pieces A", "Cost A (USD)", "Pieces B", "Cost B (USD)"])
    s.merge(r, 6, 11, "How", "head", border=True)
    steel = [p for p in hparts if p["proc"] == "STEEL"]
    c0 = r + 1
    for p in steel:
        r += 1
        i = p["id"]
        s.put(r, 1, p["label"], "text")
        for sc, cq_, cc_, lt in (("A", 2, 3, "lightsA"), ("B", 4, 5, "lightsB")):
            s.put(r, cq_, "=%s*%s+%s" % (s.ref(lt), s.ref("h_per_" + i), s.ref("h_spare_" + i)), "calc", fmt="0", name="cap_qty_%s_%s" % (i, sc))
            s.put(r, cc_, "=%s*(%s+MAX(0,%s%d-1)*%s)" % (s.ref("caps_steel"), s.ref("cap_first"), colname(cq_), r, s.ref("cap_next")), "calc", fmt=USD2,
                  name="cap_cost_%s_%s" % (i, sc))
        s.merge(r, 6, 11, "pieces = lights x per light + spare (section 1); cost = switch x (first piece + (pieces - 1) x further piece)", "text", border=True)
    c1 = r
    r += 1
    s.put(r, 1, "ESTIMATE of the stainless caps (USD)", "bold")
    s.put(r, 3, "=SUM(C%d:C%d)" % (c0, c1), "calc", fmt=USD2, name="cap_est_A")
    s.put(r, 5, "=SUM(E%d:E%d)" % (c0, c1), "calc", fmt=USD2, name="cap_est_B")
    rce = r
    r += 1
    s.put(r, 1, "REAL instant-quote price for the caps (type it in, USD, without shipping)", "bold")
    s.put(r, 3, None, "in", fmt=USD2, name="cap_quote_A")
    s.put(r, 5, None, "in", fmt=USD2, name="cap_quote_B")
    s.merge(r, 6, 11, "Upload FlashKa_cap_main.step + FlashKa_cap_main.pdf and FlashKa_cap_slide.step + FlashKa_cap_slide.pdf (%s), material SUS304, finish bead blasting, and type the price shown "
            "for the pieces above. If the instant quote refuses the parts by size, leave this empty and use another CNC service or the resin caps (section 10)." % ofd("2_JLCCNC"), "note")
    rcq = r
    r += 1
    s.put(r, 1, "Stainless caps used in the totals (USD)", "tot")
    s.put(r, 2, None, "tot")
    s.put(r, 3, "=IF(%s=0,0,IF(ISNUMBER(C%d),C%d,C%d))" % (s.ref("caps_steel"), rcq, rcq, rce), "tot", fmt=USD2, name="cap_A")
    s.put(r, 4, None, "tot")
    s.put(r, 5, "=IF(%s=0,0,IF(ISNUMBER(E%d),E%d,E%d))" % (s.ref("caps_steel"), rcq, rcq, rce), "tot", fmt=USD2, name="cap_B")
    r += 1
    s.put(r, 1, "JLCCNC ORDER used in the totals: tray + lid + caps (USD)", "tot")
    s.put(r, 2, None, "tot")
    s.put(r, 3, "=%s+%s" % (s.ref("cnc_alu_A"), s.ref("cap_A")), "tot", fmt=USD2, name="cnc_A")
    s.put(r, 4, None, "tot")
    s.put(r, 5, "=%s+%s" % (s.ref("cnc_alu_B"), s.ref("cap_B")), "tot", fmt=USD2, name="cnc_B")
    s.merge(r, 6, 11, "Scenario A in column C, scenario B in column E.", "note")
    # ---- 8. resin
    r += 2
    s.merge(r, 1, 11, "8. JLC3DP print kit (SLA 8001 translucent) - ESTIMATE; real price from the instant quote after uploading " + ofp("FlashKa_print_kit.stl")
            + " (" + U_3DP + ")", "sub", border=True)
    for key, lab in (("resin_cm3", "Resin price (USD per cm3)"), ("resin_min", "Minimum price per part (USD)")):
        r += 1
        s.param(r, key, lab, c_end=11)
    r += 1
    s.head(r, ["Part", "Volume (cm3)", "Unit price (USD)", "Qty A", "Cost A (USD)", "Qty B", "Cost B (USD)", "Size check"])
    s.merge(r, 9, 11, "Note. Size check: JLC3DP builds parts with a box of at least 5 x 5 x 5 mm or 10 x 2 x 2 mm (red = a part that is too small "
            "and is ordered on its own)", "head", border=True)
    ws.row_dimensions[r].height = 42
    res = [p for p in hparts if p["proc"] == "RESIN"]
    r0 = r + 1
    for p in res:
        r += 1
        i = p["id"]
        s.put(r, 1, p["label"], "bold" if p.get("kit") else "text")
        s.put(r, 2, "=%s/1000" % s.ref("h_vol_" + i), "calc", fmt="0.000")
        s.put(r, 3, "=MAX(%s,%s*B%d)" % (s.ref("resin_min"), s.ref("resin_cm3"), r), "calc", fmt=USD2, name="resin_unit_" + i)
        s.put(r, 4, "=%s*%s+%s" % (s.ref("lightsA"), s.ref("h_per_" + i), s.ref("h_spare_" + i)), "calc", fmt="0", name="resin_qty_%s_A" % i)
        s.put(r, 5, "=C%d*D%d" % (r, r), "calc", fmt=USD2)
        s.put(r, 6, "=%s*%s+%s" % (s.ref("lightsB"), s.ref("h_per_" + i), s.ref("h_spare_" + i)), "calc", fmt="0", name="resin_qty_%s_B" % i)
        s.put(r, 7, "=C%d*F%d" % (r, r), "calc", fmt=USD2)
        bx, by, bz = (s.ref("h_x_" + i), s.ref("h_y_" + i), s.ref("h_z_" + i))
        s.put(r, 8, "=IF(OR(MIN(%s,%s,%s)>=5,AND(MAX(%s,%s,%s)>=10,MIN(%s,%s,%s)>=2)),\"OK\",\"TOO SMALL\")" % (bx, by, bz, bx, by, bz, bx, by, bz),
              "calc", name="resin_size_" + i)
        s.merge(r, 9, 11, "Quantity = lights x per light + spare (section 1). " + p["note"], "text", border=True)
    r1 = r
    # red only where it matters: a too-small part that is ordered on its own (quantity A or B > 0); the parts inside the
    # print kit keep their plain "TOO SMALL" as the explanation why the kit exists
    ws.conditional_formatting.add("H%d:H%d" % (r0, r1), FormulaRule(
        formula=['AND($H%d="TOO SMALL",OR($D%d>0,$F%d>0))' % (r0, r0, r0)], font=Font(name=ARIAL, size=10, bold=True, color="C00000"),
        fill=PatternFill(start_color="F8CBAD", end_color="F8CBAD", fill_type="solid")))
    r += 1
    s.put(r, 1, "ESTIMATE of the JLC3DP order (USD)", "bold")
    s.put(r, 5, "=SUM(E%d:E%d)" % (r0, r1), "calc", fmt=USD2, name="resin_est_A")
    s.put(r, 7, "=SUM(G%d:G%d)" % (r0, r1), "calc", fmt=USD2, name="resin_est_B")
    rse = r
    r += 1
    s.put(r, 1, "REAL instant-quote price (type it in, USD, without shipping)", "bold")
    s.put(r, 5, None, "in", fmt=USD2, name="resin_quote_A")
    s.put(r, 7, None, "in", fmt=USD2, name="resin_quote_B")
    s.merge(r, 8, 11, "Upload %s (+ %s only for a 4.5 mm laser) at %s, quantity = one kit per light + one spare kit, and type the price shown here. "
            "Leave empty to use the estimate." % (ofp("FlashKa_print_kit.stl"), ofp("FlashKa_laser_sleeve.stl"), U_3DP), "note")
    rsq = r
    r += 1
    s.put(r, 1, "JLC3DP order used in the totals (USD)", "tot")
    s.put(r, 5, "=IF(ISNUMBER(E%d),E%d,E%d)" % (rsq, rsq, rse), "tot", fmt=USD2, name="resin_A")
    s.put(r, 7, "=IF(ISNUMBER(G%d),G%d,G%d)" % (rsq, rsq, rse), "tot", fmt=USD2, name="resin_B")
    r += 1
    s.put(r, 1, "HOUSING TOTAL: aluminium + stainless caps + resin print kit (USD)", "tot")
    for c in range(2, 5):
        s.put(r, c, None, "tot")
    s.put(r, 5, "=%s+E%d" % (s.ref("cnc_A"), r - 1), "tot", fmt=USD2, name="housing_A")
    s.put(r, 6, None, "tot")
    s.put(r, 7, "=%s+G%d" % (s.ref("cnc_B"), r - 1), "tot", fmt=USD2, name="housing_B")
    # ---- 9. quote forms
    r += 2
    s.merge(r, 1, 11, "9. What to enter on the quote forms", "sub", border=True)
    kit = next(p for p in hparts if p.get("kit"))
    members = [p for p in hparts if p.get("in_kit")]
    small = [p for p in members if not jlc3dp_size_ok(p["box"])]
    sname = {"rfw": "RF window insert", "ring": "LED spacer ring", "ant": "antenna spacer with floor plug", "tube": "light-pipe tube",
             "capmr": "resin main cap", "capsr": "2 resin slide caps"}
    small_txt = and_list(["%s (%s)" % (sname.get(p["id"], p["id"]), dims(p["box"])) for p in small]) if small else ""
    walls = thinnest_walls(H)
    if walls:
        wall_txt = "Thinnest metal wall in the design is %s mm (%s)" % (walls[0][0], walls[0][1]) + \
            ("; next: %s" % "; ".join("%s mm (%s)" % (v_, k_) for v_, k_ in walls[1:]) if len(walls) > 1 else "")
        wall_why = "JLCCNC recommends 0.8 mm minimum wall in metal (absolute minimum 0.5 mm), so it is accepted but with %s margin (values from housing_interface.json min_walls and the metal under the skin grooves: %s mm)." % (
            "no" if walls[0][0] <= 0.8 + 1e-9 else "little", H.get("skin_min_metal_under_mm", "n/a"))
    else:
        wall_txt, wall_why = "See the drawing notes for the thinnest walls", "JLCCNC recommends 0.8 mm minimum wall in metal."
    forms = [
        ("JLCCNC files", "%s: FlashKa_tray.step + FlashKa_tray.pdf, FlashKa_lid.step + FlashKa_lid.pdf, FlashKa_cap_main.step + FlashKa_cap_main.pdf, FlashKa_cap_slide.step + FlashKa_cap_slide.pdf "
         "(each drawing PDF has the SAME file name as its STEP file)" % ofd("2_JLCCNC"),
         "STEP is mandatory, a drawing is recommended, names must match (" + U_JLCNC_ORD + "). The PDFs are cad/FlashKa_tray_drawing.pdf (2 sheets), FlashKa_lid_drawing.pdf, "
         "FlashKa_cap_main_drawing.pdf and FlashKa_cap_slide_drawing.pdf, renamed to the STEP names; they carry the threads and tolerances."),
        ("JLCCNC process / material", "Tray and lid: CNC milling 3-axis (the skin may need indexing), aluminium 6061-T6. Caps: CNC turning, stainless steel SUS304", "Capabilities: " + U_JLCNC_CAP + "; turning: " + U_JLCNC_TURN),
        ("JLCCNC tolerance", "ISO 2768-m (medium)", "Standard tolerance; the cavity fits were designed with clearances of 0.1-0.25 mm. The tube sits in its hole with 0.025 mm per side: glue it."),
        ("JLCCNC surface", "Tray and lid: bead blast + black anodize (combined option). Caps: bead blasting only", "Anodizing alone does not include bead blast unless the combined option is selected; the drawings ask for type II 8-12 um (JLCCNC range 8-25 um), on every surface incl. the bores. "
         "Stainless: JLCCNC offers as machined, bead blasting, brushing and laser marking; no passivation or polishing."),
        ("JLCCNC threads", "M1.6 x 0.35 (4 in the tray), M2 x 0.4 (1 in the tray), marked on the drawing / in the notes", "Threads are supported, but M1.6 is not listed on the capability page: ask in the quote chat. Fallback: order the 1.25 mm / 1.6 mm holes plain and tap them by hand (hand taps, sheet 'Tools')."),
        ("JLCCNC walls", wall_txt, wall_why),
        ("JLCCNC laser marking", "Class 2 module (<= 1 mW): %s on the lid; %s only for a module measured above 1 mW (Class 3R) instead. Tray: %s, %s, %s"
         % (ofp("FlashKa_marking_lid_class2.dxf"), ofp("FlashKa_marking_lid_class3R.dxf"), ofp("FlashKa_marking_bottom.dxf"), ofp("FlashKa_marking_minus_y.dxf"), ofp("FlashKa_marking_plus_y.dxf")),
         "Laser marking after anodizing (layer MARK = laser, layer REF = outline, do not mark), only if JLCCNC offers it for your order; the warning label is required for a laser product, so use the "
         "adhesive-label fallback (section 10) if it does not. Use a Class 2 module only (see the laser notes in sheet 'Bought parts')."),
        ("JLCCNC caps", "FlashKa_cap_main: quantity 1 per light + 1 spare; FlashKa_cap_slide: quantity 2 per light + 1 spare; SUS304, bead blast, no coating",
         "Confirm with the instant quote; if refused (JLCCNC's FAQ says rotary-axis metal parts must be longer than 20 mm and thicker than 4 mm; the caps are 7.0 mm long with flanges of 6.6 and 5.0 mm), "
         "any CNC service (PCBWay, Xometry, a local shop) can make them from the same STEP + PDF, or use the resin caps from the print kit."),
        ("JLCCNC quantity / lead time", "1 or 5 sets; standard lead time from 3 working days, SUS304 as fast as 5 days, + about 1 day transfer", "Quote within 24 h; more than 20 pieces goes to manual review."),
        ("JLC3DP files", "%s: ONE part, the %s on 1 mm sprues (%s); quantity = one kit per light + one spare kit (+ %s only for a 4.5 mm laser)"
         % (ofp("FlashKa_print_kit.stl"), and_list([sname[p["id"]] for p in members]), dims(kit["box"]), ofp("FlashKa_laser_sleeve.stl")),
         ("The %s alone %s below the minimum build size; the kit is not. " % (and_list([sname[p["id"]] for p in small]), "is" if len(small) == 1 else "are") if small else "")
         + "Cut the parts off the sprues at home with flush cutters and file the stubs flat."),
        ("JLC3DP material", "SLA resin 8001 translucent, as printed (support removal only, no sanding)", "Tolerance +/-0.2 mm or 0.3 %, hole tolerance +/-0.3 mm, wall > 0.8 mm, minimum build size 5 x 5 x 5 mm or 10 x 2 x 2 mm, build time 2 days (" + U_3DP_8001
         + "). 'Transparent' 8001 is sanded and oil-sprayed by default (extra cost, polished look): a kit is ONE part with ONE material."),
    ]
    r += 1
    s.put(r, 1, "Item", "head")
    s.merge(r, 2, 6, "Enter", "head", border=True)
    s.merge(r, 7, 11, "Why / source", "head", border=True)
    for a, b, c in forms:
        r += 1
        s.put(r, 1, a, "text")
        s.merge(r, 2, 6, b, "text", border=True)
        s.merge(r, 7, 11, c, "text", border=True)
    # ---- 10. risks
    r += 2
    s.merge(r, 1, 11, "10. Risks and open points in the housing order", "sub", border=True)
    par = H.get("params", {})
    rfw_t = par.get("rfw_flange_t", 0.6) + par.get("rfw_flange_drop", 0.0)   # flange = pocket depth + drop
    mcap_t = (par.get("main_cap") or [0, 0, 0.6])[2]
    scap_t = (par.get("slide_cap") or [0, 0, 0.6])[2]
    thin = [f"{n} ({t:.1f} mm)" for n, t in (("RF window insert", rfw_t), ("resin main cap flange", mcap_t), ("resin slide cap flange", scap_t)) if t < 0.8 - 1e-9]
    thin_txt = ("The %s stay below the 0.8 mm minimum wall of the resin page, so the quote may still show a thin-wall "
                "warning: accept it or ask JLC3DP support. " % and_list(thin)) if thin else ""
    risks = [
        ("PRINT KIT INSTEAD OF SEPARATE RESIN PARTS: the %s alone %s below JLC3DP's minimum build size (5 x 5 x 5 mm or 10 x 2 x 2 mm), so all seven resin parts are ordered as "
         "ONE print kit (%s, 1 mm sprues), which is above it, with one minimum price and one customs line. " % (small_txt, "is" if len(small) == 1 else "are", dims(kit["box"])) if small else
         "PRINT KIT: all seven resin parts are ordered as ONE print kit (%s, 1 mm sprues). " % dims(kit["box"]))
        + thin_txt + "Cut the parts off the sprues with flush cutters and file the stubs flat; the spare kit covers a part that breaks.",
        "STAINLESS CAPS REFUSED BY SIZE: JLCCNC states a minimum part size of 5 x 5 x 1 mm and a turning diameter of at least 3 mm, but its FAQ also says rotary-axis metal parts need length > 20 mm and diameter > 4 mm; "
        "the caps are 7.0 mm long. Confirm with the instant quote. If it is refused, any CNC service (PCBWay, Xometry, a local shop) can make them from the same STEP + PDF, or use the resin caps from the "
        "print kit (set 'Stainless caps ordered' in section 7 to 0: the housing then costs the caps' estimate less, and the resin caps are already in the kit). The price in section 7 is an ESTIMATE.",
        "TUBE GLUE: the light-pipe tube sits in an 8.45 mm hole with 0.025 mm per side and a 0.2 mm ledge, and the resin hole tolerance is +/-0.3 mm: test-fit, then glue with clear two-part epoxy or UV-curing "
        "clear adhesive. Do not use cyanoacrylate: it leaves a white bloom on clear resin. The 8001 print can show bubbles and layer texture; 'Transparent' 8001 (sanded and oil-sprayed) is clearer but costs more.",
        holddown_note(H),
        "FILES: upload exactly the files of %s and %s (sheet 'Ordering checklist', file map). JLCCNC pairs each drawing with its STEP file by the file name, so keep the "
        "names FlashKa_tray.pdf, FlashKa_lid.pdf, FlashKa_cap_main.pdf and FlashKa_cap_slide.pdf." % (ofd("2_JLCCNC"), ofd("3_JLC3DP")),
        "ANODIZING THICKNESS: the drawings ask for type II black, 8-12 um (JLCCNC quotes 8-25 um as its range); it grows on every surface including the 6.1 mm laser bore, the 10.2 mm window "
        "bore, the threads and the 0.25 mm V grooves. The drawings say: tolerances apply after finishing, threads are tapped before anodizing and gauged after it (drawing note 3) - ask JLCCNC to confirm, "
        "chase a tight thread with an M1.6 tap, and test-fit the first set before ordering 5.",
        "LASER MARKING (%s): only possible if JLCCNC offers laser marking for your order; the cheap alternative is a printed adhesive label with the same text "
        "('LASER RADIATION, DO NOT STARE INTO BEAM, CLASS 2 LASER PRODUCT, 520 nm P < 1 mW EN 60825-1:2014'). FlashKa_marking_lid_class3R.dxf in the same folder is the marking "
        "for a module that measures above 1 mW (Class 3R). The marking price in section 2 is an ESTIMATE; set 'Laser marking' to 0 if you label by hand." % ofp("FlashKa_marking_lid_class2.dxf"),
        "SET-UP COSTS: the set-ups, the anodizing lot fee and the marking set-up are paid once per order, which is why 5 sets cost far less than 5 x the price of one set.",
    ]
    for t in risks:
        r += 1
        s.merge(r, 1, 11, t, "text", border=True)
    ws.freeze_panes = "A5"
    autofit(s)
    return s


# ----------------------------------------------------------------------------------------------
# sheet: Bought parts
# ----------------------------------------------------------------------------------------------
def build_bought(book, bought):
    S = "Bought parts"
    s = Sh(book, S, [4, 34, 32, 62, 30, 11, 9, 10, 9, 10, 9, 11, 9, 11, 12, 52, 46])
    ws = s.ws
    s.put(1, 1, "Bought parts and consumables (not on the JLCPCB board)", "title")
    s.merge(2, 1, 14, "Everything the PCB order does not contain: cells, LED board, laser, window, screws, wire, tapes, the two silicone hold-down pads (new in v0.6), adhesives. Prices are typical AliExpress/web-shop prices found with search on %s "
            "(AliExpress item pages cannot be read automatically, so the prices come from search-result snippets; v0.6 kept them, and the new pads and adhesive are typical-price ESTIMATES that were not looked up) - "
            "they are ESTIMATES, change the blue number when you see a real listing. "
            "'Packs' = how many packs you must buy (rounded up): quantity needed = lights x 'per light' + 'fixed per order' (spares, one roll of tape, one sheet of pad material...)." % V05_DATE)
    s.merge(3, 1, 14, "Prices exclude VAT and shipping here; both are added on sheet 'Hidden costs' (21 % VAT, shipping per parcel, EUR 3 flat duty per parcel).", "note")
    hr = 5
    s.head(hr, ["#", "Item", "Used for", "Exact spec that matters", "Search term (AliExpress / web shop)", "Price per pack (USD)", "Pack size", "Pack unit", "Per light",
                "Fixed per order", "Packs A", "Cost A (USD)", "Packs B", "Cost B (USD)", "Category", "Price basis (source, date)", "Link example"])
    ws.row_dimensions[hr].height = 42
    r0 = hr + 1
    for i, b in enumerate(bought):
        r = r0 + i
        s.put(r, 1, i + 1, "text", fmt="0")
        s.put(r, 2, b["item"], "bold")
        s.put(r, 3, b["use"], "text")
        s.put(r, 4, b["spec"], "text")
        s.put(r, 5, b["search"], "text")
        s.put(r, 6, b["price"], "est" if b["est"] else "in", fmt=USD2, name="bp_price_" + b["id"])
        s.put(r, 7, b["pack"], "in", name="bp_pack_" + b["id"])
        s.put(r, 8, b["unit"], "text")
        s.put(r, 9, b["per_light"], "in", name="bp_per_" + b["id"])
        s.put(r, 10, b["per_order"], "in", name="bp_fix_" + b["id"])
        for sc, cp_, cc_, lt in (("A", 11, 12, "lightsA"), ("B", 13, 14, "lightsB")):
            s.put(r, cp_, "=ROUNDUP(ROUND((%s*I%d+J%d)/G%d,9),0)" % (s.ref(lt), r, r, r), "calc", fmt="0", name="bp_packs_%s_%s" % (b["id"], sc))
            s.put(r, cc_, "=%s%d*F%d" % (colname(cp_), r, r), "calc", fmt=USD2, name="bp_cost_%s_%s" % (b["id"], sc))
        s.put(r, 15, b["cat"], "text")
        s.put(r, 16, b["basis"], "warn" if b["est"] else "text")
        s.put(r, 17, b["link"], "link", link=b["link"])
    r1 = r0 + len(bought) - 1
    r = r1 + 1
    s.put(r, 2, "Bought parts (cells, LED, laser, window, screws, ring)", "tot")
    for c in range(3, 18):
        s.put(r, c, None, "tot")
    s.put(r, 12, "=SUMIF($O$%d:$O$%d,\"Part\",L%d:L%d)" % (r0, r1, r0, r1), "tot", fmt=USD2, name="parts_A")
    s.put(r, 14, "=SUMIF($O$%d:$O$%d,\"Part\",N%d:N%d)" % (r0, r1, r0, r1), "tot", fmt=USD2, name="parts_B")
    r += 1
    s.put(r, 2, "Consumables (wire, tapes, silicone pads, adhesives)", "tot")
    for c in range(3, 18):
        s.put(r, c, None, "tot")
    s.put(r, 12, "=SUMIF($O$%d:$O$%d,\"Consumable\",L%d:L%d)" % (r0, r1, r0, r1), "tot", fmt=USD2, name="cons_A")
    s.put(r, 14, "=SUMIF($O$%d:$O$%d,\"Consumable\",N%d:N%d)" % (r0, r1, r0, r1), "tot", fmt=USD2, name="cons_B")
    r += 1
    s.put(r, 2, "of which spares and left-over pack content (information)", "text")
    s.put(r, 12, "=SUM(L%d:L%d)-SUMPRODUCT(%s*I%d:I%d/G%d:G%d*F%d:F%d)" % (r0, r1, s.ref("lightsA"), r0, r1, r0, r1, r0, r1), "calc", fmt=USD2, name="bp_spare_A")
    s.put(r, 14, "=SUM(N%d:N%d)-SUMPRODUCT(%s*I%d:I%d/G%d:G%d*F%d:F%d)" % (r0, r1, s.ref("lightsB"), r0, r1, r0, r1, r0, r1), "calc", fmt=USD2, name="bp_spare_B")
    # laser explanation
    r += 2
    s.merge(r, 1, 14, "Why the laser must be Class 2 (<= 1 mW)", "sub", border=True)
    laser = [
        "Laser classes (IEC/EN 60825-1) for visible light (400-700 nm): Class 1 = harmless in normal use; Class 2 = up to 1 mW continuous - safe for accidental exposure because the blink / aversion "
        "reflex (about 0.25 s) closes the eye before damage; Class 3R = up to 5 mW - low risk but a direct look into the beam can hurt, it is not meant for a keychain; Class 3B and 4 = dangerous. "
        "(" + U_LASER + ")",
        "This light is a keychain that people carry and use in public, so the module must be Class 2: 520 nm green at <= 1 mW. Green looks about five times brighter than red at the same power "
        "because the eye is most sensitive near 555 nm, so 1 mW green is already a clearly visible dot.",
        "Cheap modules sold as '1 mW' often emit several mW. The housing marking text (FlashKa_marking_lid_class2.dxf: 'CLASS 2 LASER PRODUCT, 520 nm P < 1 mW EN 60825-1:2014') is only true if the module "
        "really is <= 1 mW. Buy from a seller that states a measured power, or measure it (optional laser power meter, sheet 'Tools'). If it is stronger it is a Class 3R product: do not use the Class 2 marking.",
        "For consumer laser products in the EU the standard EN 50689:2021 applies in addition (" + U_EN50689 + "). If you only build for yourself this is a recommendation; if you sell or give lights away, read it first.",
        "Always wear 520 nm safety glasses (sheet 'Tools') when the laser is powered on the bench, and never point it at people, animals, aircraft or vehicles.",
    ]
    for t in laser:
        r += 1
        s.merge(r, 1, 14, t, "text", border=True)
    r += 2
    s.merge(r, 1, 14, "Buying tips", "sub", border=True)
    tips = [
        "Search with the exact term in column E, sort by orders/rating, check the listed dimensions against the spec column, and read the reviews with photos. Ask the seller for the power measurement of the laser and the exact size of the LED board.",
        "Each seller ships its own parcel: 8 parcels mean 8 shipping fees and 8 x EUR 3 customs duty. Buy the small hardware (screws, rings, wire, tapes, silicone pads, epoxy) together in ONE EU web shop - see 'Hidden costs' for the saving.",
        "Order the laser, cells and LED board FIRST (delivery 2-5 weeks), measure them with a caliper, and only then order the housing, so that a different module size does not waste a CNC order.",
    ]
    for t in tips:
        r += 1
        s.merge(r, 1, 14, t, "text", border=True)
    ws.freeze_panes = "C%d" % r0
    autofit(s)
    ws.row_dimensions[hr].height = 42
    return s


# ----------------------------------------------------------------------------------------------
# sheet: Hidden costs
# ----------------------------------------------------------------------------------------------
def build_hidden(book, tools):
    S = "Hidden costs"
    s = Sh(book, S, [50, 13, 13, 13, 13, 13, 13, 13, 13, 13, 13, 62])
    ws = s.ws
    s.put(1, 1, "Hidden costs - shipping, EU VAT, customs, bank fees, spares and risk", "title")
    s.merge(2, 1, 12, "What you pay on top of the prices of the other sheets. JLCPCB, JLCCNC and JLC3DP are three separate shops and ship three separate parcels; every AliExpress seller ships its own "
            "parcel. For Lithuania (EU) each parcel gets VAT 21 %% and, since 1 July 2026, a flat EUR 3 customs duty per customs line (up to EUR 150), or formal customs clearance with a carrier fee "
            "above EUR 150. All inputs are blue; everything marked ESTIMATE has no public price (JLC shows shipping only in the cart). Read %s (v0.5 price check; v0.6 changed nothing here except the stainless-caps customs line)." % V05_DATE)
    r = 4
    s.merge(r, 1, 12, "1. Inputs: EU import rules, bank fee, shipping choice, parcels", "sub", border=True)
    items = (("vat", "VAT rate Lithuania", None), ("ioss_eur", "IOSS limit: goods value per parcel (EUR)", None),
             ("flat_duty", "Flat customs duty per customs line (EUR), up to the limit", None),
             ("formal_fee_min", "Formal clearance: carrier fee minimum (EUR per parcel)", None),
             ("formal_fee_pct", "Formal clearance: carrier fee percent of VAT + duty", None),
             ("card_pct", "Card / currency conversion fee on JLC payments", None),
             ("ship_mode", "Shipping mode (1 = economy, 2 = express)", "0"),
             ("ali_ship", "AliExpress shipping per seller parcel (USD)", None),
             ("ali_parcels", "Number of separate AliExpress / web-shop parcels", "0"),
             ("ali_parcels_consol", "  parcels if the small hardware comes from ONE EU web shop", "0"),
             ("risk_pcb_f", "Risk reserve: share of a second PCB order", PCT1),
             ("risk_house_f", "Risk reserve: share of a second housing order", PCT1))
    for key, lab, fmt in items:
        r += 1
        s.param(r, key, lab, fmt=fmt, c_end=12)
        if key == "ship_mode":
            dv = DataValidation(type="list", formula1='"1,2"', allow_blank=False)
            ws.add_data_validation(dv)
            dv.add(ws.cell(row=r, column=2))
    fx = s.ref("fx")
    # ---- 2. shipping
    r += 2
    s.merge(r, 1, 12, "2. Shipping per parcel (USD, ESTIMATES - the JLC cart shows the real 'Shipping Estimate' before you pay)", "sub", border=True)
    r += 1
    s.head(r, ["Parcel", "Economy A", "Express A", "Economy B", "Express B", "Chosen A", "Chosen B"])
    s.merge(r, 8, 12, "Basis", "head", border=True)
    mode = s.ref("ship_mode")
    for i, (nm, ea, xa, eb, xb, note) in enumerate(SHIPPING):
        r += 1
        s.put(r, 1, nm, "text")
        for c, v in ((2, ea), (3, xa), (4, eb), (5, xb)):
            s.put(r, c, v, "est", fmt=USD2)
        s.put(r, 6, "=IF(%s=1,B%d,C%d)" % (mode, r, r), "calc", fmt=USD2, name="ship_A_%d" % i)
        s.put(r, 7, "=IF(%s=1,D%d,E%d)" % (mode, r, r), "calc", fmt=USD2, name="ship_B_%d" % i)
        s.merge(r, 8, 12, note, "text", border=True)
    # ---- 3. parcel parameters
    r += 2
    s.merge(r, 1, 12, "3. Customs parameters per parcel", "sub", border=True)
    r += 1
    s.head(r, ["Parcel", "Customs lines per parcel", "Duty rate in formal clearance", "Parcels"])
    s.merge(r, 5, 12, "Note (rates are ASSUMPTIONS - the invoice / HS code decides; in the flat-duty case the EUR 3 per line replaces the tariff)", "head", border=True)
    ws.row_dimensions[r].height = 42
    for i, (nm, ln, rate, note) in enumerate(PARCELS):
        r += 1
        s.put(r, 1, nm, "text")
        if i == 1:      # JLCCNC parcel: aluminium articles + (if the stainless caps are ordered) steel articles = 1 + switch
            s.put(r, 2, "=%d+%s" % (ln, s.ref("caps_steel")), "calc", fmt="0", name="pl_lines_%d" % i)
        else:
            s.put(r, 2, ln, "in", fmt="0", name="pl_lines_%d" % i)
        s.put(r, 3, rate, "est", fmt=PCT1, name="pl_rate_%d" % i)
        if i < 3:
            s.put(r, 4, 1, "in", fmt="0", name="pl_n_%d" % i)
        else:
            s.put(r, 4, "=" + s.ref("ali_parcels"), "calc", fmt="0", name="pl_n_%d" % i)
        s.merge(r, 5, 12, note, "text", border=True)

    # ---- 4/5. landed cost
    def landed(sc, title):
        nonlocal r
        r += 2
        s.merge(r, 1, 12, title, "sub", border=True)
        r += 1
        s.head(r, ["Parcel", "Goods (USD)", "Parcels", "Goods per parcel (EUR)", "Route", "Shipping (USD)", "Duty (USD)", "VAT (USD)", "Carrier fee (USD)", "Landed cost (USD)"])
        s.merge(r, 11, 12, "How", "head", border=True)
        ws.row_dimensions[r].height = 42
        first = r + 1
        srcs = {0: "jlc_goods_" + sc, 1: "cnc_" + sc, 2: "resin_" + sc}
        how = ["Route = IOSS if goods per parcel <= EUR 150, otherwise formal clearance. IOSS: VAT on goods + shipping, flat duty per line. Formal: duty = rate x (goods + shipping), VAT on goods + shipping + duty, carrier fee = max(minimum, % of VAT + duty).",
               "Same rules for the aluminium parts and the stainless caps (two customs lines).", "Same rules for the resin print kit.",
               "Goods = bought parts + consumables; shipping and flat duty are paid for every parcel."]
        for i, (nm, _, _, _) in enumerate(PARCELS):
            r += 1
            s.put(r, 1, nm, "text")
            goods = "=" + s.ref(srcs[i]) if i < 3 else "=%s+%s" % (s.ref("parts_" + sc), s.ref("cons_" + sc))
            s.put(r, 2, goods, "x", fmt=USD2, name="hc_goods_%s_%d" % (sc, i))
            s.put(r, 3, "=" + s.ref("pl_n_%d" % i), "calc", fmt="0")
            s.put(r, 4, "=B%d/C%d/%s" % (r, r, fx), "calc", fmt=EUR2, name="hc_per_eur_%s_%d" % (sc, i))
            s.put(r, 5, "=IF(D%d>%s,\"formal\",\"IOSS\")" % (r, s.ref("ioss_eur")), "calc", name="hc_route_%s_%d" % (sc, i))
            ship = ("=" + s.ref("ship_%s_%d" % (sc, i))) if i < 3 else "=%s*C%d" % (s.ref("ali_ship"), r)
            s.put(r, 6, ship, "calc", fmt=USD2, name="hc_ship_%s_%d" % (sc, i))
            s.put(r, 7, "=IF(E%d=\"formal\",%s*(B%d+F%d),%s*C%d*%s*%s)" % (r, s.ref("pl_rate_%d" % i), r, r, s.ref("pl_lines_%d" % i), r, s.ref("flat_duty"), fx),
                  "calc", fmt=USD2, name="hc_duty_%s_%d" % (sc, i))
            s.put(r, 8, "=%s*(B%d+F%d+IF(E%d=\"formal\",G%d,0))" % (s.ref("vat"), r, r, r, r), "calc", fmt=USD2, name="hc_vat_%s_%d" % (sc, i))
            s.put(r, 9, "=IF(E%d=\"formal\",C%d*MAX(%s*%s,%s*(G%d+H%d)/C%d),0)" % (r, r, s.ref("formal_fee_min"), fx, s.ref("formal_fee_pct"), r, r, r),
                  "calc", fmt=USD2, name="hc_fee_%s_%d" % (sc, i))
            s.put(r, 10, "=B%d+F%d+G%d+H%d+I%d" % (r, r, r, r, r), "calc", fmt=USD2, name="hc_landed_%s_%d" % (sc, i))
            s.merge(r, 11, 12, how[i], "note")
        last = r
        r += 1
        s.put(r, 1, "All parcels", "tot")
        s.put(r, 3, None, "tot")
        s.put(r, 4, None, "tot")
        s.put(r, 5, None, "tot")
        for c, nm in ((2, "goods"), (6, "ship"), (7, "duty"), (8, "vat"), (9, "fee"), (10, "landed")):
            s.put(r, c, "=SUM(%s%d:%s%d)" % (colname(c), first, colname(c), last), "tot", fmt=USD2, name="hc_sum_%s_%s" % (nm, sc))
        rt = r
        r += 1
        s.put(r, 1, "Card / currency fee on the three JLC payments", "text")
        s.put(r, 10, "=%s*(J%d+J%d+J%d)" % (s.ref("card_pct"), first, first + 1, first + 2), "calc", fmt=USD2, name="card_" + sc)
        r += 1
        s.put(r, 1, "Shipping + VAT + duty + carrier fees + card fee (to the Summary)", "tot")
        for c in range(2, 10):
            s.put(r, c, None, "tot")
        s.put(r, 10, "=F%d+G%d+H%d+I%d+J%d" % (rt, rt, rt, rt, r - 1), "tot", fmt=USD2, name="tax_other_" + sc)
        return first

    landed("A", "4. Landed cost per parcel - scenario A (one light)")
    landed("B", "5. Landed cost per parcel - scenario B (five lights)")
    # ---- 6. savings and reserves
    r += 2
    s.merge(r, 1, 12, "6. Savings and risk reserves (not in the totals)", "sub", border=True)
    r += 1
    s.put(r, 1, "Saving if the small hardware comes from ONE EU web shop (USD)", "text")
    s.put(r, 2, "=(%s-%s)*(%s+%s*%s*%s)" % (s.ref("ali_parcels"), s.ref("ali_parcels_consol"), s.ref("ali_ship"), s.ref("pl_lines_3"), s.ref("flat_duty"), fx),
          "calc", fmt=USD2, name="consol_saving_A")
    s.merge(r, 3, 12, "Every avoided seller parcel saves its shipping and its flat EUR 3 customs duty. Look for an EU shop that sells M1.6 screws, M2 set screws, split rings, PTFE wire, Kapton, "
            "foam tape, silicone sheet or pads and epoxy (electronics and model-making shops).", "note")
    G0, S0 = s.ref("hc_goods_A_0"), s.ref("hc_ship_A_0")
    r += 1
    s.put(r, 1, "EUR 150 cliff: JLCPCB parcel A if it is on the IOSS route (USD, landed)", "text")
    s.put(r, 2, "=%s+%s+%s*%s*%s+%s*(%s+%s)" % (G0, S0, s.ref("pl_lines_0"), s.ref("flat_duty"), fx, s.ref("vat"), G0, S0), "calc", fmt=USD2, name="route_ioss_A")
    s.merge(r, 3, 12, "Goods + shipping + flat EUR 3 per customs line + VAT on goods and shipping.", "note")
    r += 1
    s.put(r, 1, "EUR 150 cliff: JLCPCB parcel A if it is on the formal-clearance route (USD, landed)", "text")
    dd = "%s*(%s+%s)" % (s.ref("pl_rate_0"), G0, S0)
    vv = "%s*(%s+%s+%s)" % (s.ref("vat"), G0, S0, dd)
    s.put(r, 2, "=%s+%s+%s+%s+MAX(%s*%s,%s*(%s+%s))" % (G0, S0, dd, vv, s.ref("formal_fee_min"), fx, s.ref("formal_fee_pct"), dd, vv), "calc", fmt=USD2, name="route_formal_A")
    s.merge(r, 3, 12, "Goods + shipping + tariff + VAT on goods, shipping and tariff + carrier disbursement fee (minimum EUR 15).", "note")
    r += 1
    s.put(r, 1, "EUR 150 cliff: formal route minus IOSS route (USD)", "bold")
    s.put(r, 2, "=B%d-B%d" % (r - 1, r - 2), "calc", fmt=USD2, name="route_diff_A")
    s.merge(r, 3, 12, "How much the first order costs MORE when the JLCPCB goods value is above EUR 150. If the real PCB price or the component prices are a few euros lower, the bill drops by about this amount.", "note")
    r += 1
    s.put(r, 1, "Risk reserve: second PCB + assembly order after a first-article problem (USD)", "text")
    s.put(r, 2, "=%s*%s" % (s.ref("risk_pcb_f"), s.ref("hc_landed_A_0")), "calc", fmt=USD2, name="risk_pcb")
    s.merge(r, 3, 12, "A new board design almost never works perfectly the first time (wrong footprint, rotation, missing pull-up). The second order costs the same JLCPCB order again, with shipping and tax. "
            "The 4 spare bare boards of the first order can be re-assembled by hand, which saves the PCB price but not the assembly.", "note")
    r += 1
    s.put(r, 1, "Risk reserve: second housing order (USD)", "text")
    s.put(r, 2, "=%s*%s" % (s.ref("risk_house_f"), s.ref("hc_landed_A_1")), "calc", fmt=USD2, name="risk_house")
    s.merge(r, 3, 12, "If the first tray does not fit the real laser/cells (or the stainless caps are refused and must be re-ordered elsewhere). Reduce the risk by measuring the delivered parts before the order and ordering ONE set first.", "note")
    # ---- 7. list of hidden costs
    r += 2
    s.merge(r, 1, 12, "7. The costs people forget (amounts for scenario A and B where they are in the totals)", "sub", border=True)
    r += 1
    s.put(r, 1, "Cost", "head")
    s.put(r, 2, "A (USD)", "head")
    s.put(r, 3, "B (USD)", "head")
    s.merge(r, 4, 12, "What it is and what to do", "head", border=True)
    ci = next((i for i, t in enumerate(tools) if t[0].startswith("USB-C data cable")), None)

    rows = [
        ("Shipping of the 3 JLC parcels (JLCPCB, JLCCNC, JLC3DP)", "=%s+%s+%s" % (s.ref("hc_ship_A_0"), s.ref("hc_ship_A_1"), s.ref("hc_ship_A_2")),
         "=%s+%s+%s" % (s.ref("hc_ship_B_0"), s.ref("hc_ship_B_1"), s.ref("hc_ship_B_2")),
         "JLCPCB, JLCCNC and JLC3DP ship separately, three shipping fees. JLC publishes no rate table; anchors: DHL Express about $21.50, EuroPacket about $6.50, Global Standard Direct Line about $1.50 for a small "
         "parcel (" + U_CHIP + ", June 2025), FedEx about $16 to Spain (" + U_EEV + ", 2024). Economy takes weeks and may be slow at customs: use express for the first order."),
        ("EU VAT 21 % (Lithuania)", "=" + s.ref("hc_sum_vat_A"), "=" + s.ref("hc_sum_vat_B"),
         "VAT is charged on goods + shipping. Up to EUR 150 per parcel JLC collects it at checkout (IOSS, " + U_VAT + "); above EUR 150 you pay VAT and customs fees to the carrier (or at checkout with DDP)."),
        ("Customs duty + carrier handling fees", "=%s+%s" % (s.ref("hc_sum_duty_A"), s.ref("hc_sum_fee_A")), "=%s+%s" % (s.ref("hc_sum_duty_B"), s.ref("hc_sum_fee_B")),
         "Since 1 July 2026 every low-value parcel pays a flat EUR 3 duty per customs line (" + U_EC + "; JLC FAQ " + U_CUST + "). Above EUR 150 the normal tariff and formal clearance apply and the carrier adds a "
         "disbursement fee (DHL Germany 2 % min EUR 15, UPS 3 % min EUR 15.70, FedEx 2.5 % min EUR 15). A unified EU handling fee (about EUR 2 per parcel) is planned from about Nov 2026 and is not included."),
        ("THE EUR 150 CLIFF", "=" + s.ref("jlc_line_gap_A"), "=" + s.ref("jlc_line_gap_B"),
         "EUR left until the JLCPCB order passes the IOSS limit (negative = already above). Close to the line a few euros of price change can switch the parcel to formal clearance (about EUR 10-15 more). "
         "Keep the three JLC orders separate parcels and below EUR 150 where you can (for example do not add optional services you do not need)."),
        ("AliExpress / web shops: shipping + flat duty", "=%s+%s" % (s.ref("hc_ship_A_3"), s.ref("hc_duty_A_3")), "=%s+%s" % (s.ref("hc_ship_B_3"), s.ref("hc_duty_B_3")),
         "Each seller parcel pays its own shipping and its own EUR 3 duty. See the saving in section 6."),
        ("Card / currency conversion fee", "=" + s.ref("card_A"), "=" + s.ref("card_B"),
         "JLC charges in USD. Your bank may add a conversion fee; use a card without one if you can."),
        ("Spares already inside the totals: pieces JLC buys for placement loss", "=" + s.ref("extra_cost_A"), "=" + s.ref("extra_cost_B"),
         "JLC buys a few more resistors, capacitors and chips than the boards need (lost by the placement machine). You pay for them but do not receive them."),
        ("Spares already inside the totals: bought parts and left-over packs", "=" + s.ref("bp_spare_A"), "=" + s.ref("bp_spare_B"),
         "Third cell, second LED board, extra screws (you WILL lose an M1.6 screw), spare glass windows, left-over pad sheets. Screws and rings come in packs of 20-100. "
         "(The spare resin parts come as one spare print kit and the spare caps as +1 piece each, both inside the housing total.)"),
        ("First-article risk: second PCB + assembly order (NOT in the totals)", "=" + s.ref("risk_pcb"), None,
         "Budget for it. If a fix is needed, the same fees (set-up, stencil, feeder loading) are paid again."),
        ("First-article risk: second housing order (NOT in the totals)", "=" + s.ref("risk_house"), None, "See section 6."),
        ("USB-C DATA cable (in Tools, NOT in the per-light cost)", ("=" + s.ref("tool_cost_%d" % ci)) if ci is not None else None, None,
         "Needed to charge the light and update its firmware. A charge-only cable does not work for data. You only pay if you do not have one."),
        ("Price changes between now and your order", None, None,
         "LCSC prices and stock change weekly; JLC re-prices in the cart. Re-open the LCSC links in sheet 'Main PCB BOM' and watch for red lines in the JLC BOM upload."),
        ("Your time and mistakes", None, None,
         "Not counted: soldering the wires, assembling the housing, testing, waiting 2-5 weeks for parcels."),
    ]
    for lab, fa, fb, txt in rows:
        r += 1
        s.put(r, 1, lab, "text")
        s.put(r, 2, fa, "x" if fa else "text", fmt=EUR2 if lab.startswith("THE EUR") else USD2)
        s.put(r, 3, fb, "x" if fb else "text", fmt=EUR2 if lab.startswith("THE EUR") else USD2)
        s.merge(r, 4, 12, txt, "text", border=True)
    ws.freeze_panes = "A4"
    autofit(s)
    return s


# ----------------------------------------------------------------------------------------------
# sheet: Tools
# ----------------------------------------------------------------------------------------------
def build_tools(book, tools):
    S = "Tools"
    s = Sh(book, S, [4, 34, 46, 52, 32, 11, 6, 9, 11, 36])
    ws = s.ws
    s.put(1, 1, "Tools you need once (not part of the per-light cost)", "title")
    s.merge(2, 1, 10, "JLCPCB solders all SMD parts, so you do NOT need a hot-air station, solder paste or a reflow oven. You only solder a few wires by hand (cells, LED, laser) and "
            "screw the housing together (and cut two small silicone pads). Prices are typical 2026 web-shop prices (ESTIMATES, USD, excl. VAT and shipping). 'Needed' = 1 counts the tool in the Summary, 0 = optional, not counted. "
            "If you already own a tool, set its 'Needed' to 0.")
    hr = 4
    s.head(hr, ["#", "Tool", "Why you need it", "Spec that matters", "Search term", "Price each (USD)", "Qty", "Needed (1/0)", "Cost (USD)", "Basis"])
    ws.row_dimensions[hr].height = 30
    r0 = hr + 1
    for i, (nm, why, spec, search, price, qty, need) in enumerate(tools):
        r = r0 + i
        s.put(r, 1, i + 1, "text", fmt="0")
        s.put(r, 2, nm, "bold")
        s.put(r, 3, why, "text")
        s.put(r, 4, spec, "text")
        s.put(r, 5, search, "text")
        s.put(r, 6, price, "est", fmt=USD2)
        s.put(r, 7, qty, "in", fmt="0")
        s.put(r, 8, need, "in", fmt="0")
        s.put(r, 9, "=F%d*G%d*H%d" % (r, r, r), "calc", fmt=USD2, name="tool_cost_%d" % i)
        s.put(r, 10, "ESTIMATE (typical price; first priced " + V05_DATE + (", added in v0.6 on " + CHECK if nm.startswith("Hobby knife") else "") + ")", "text")
    r1 = r0 + len(tools) - 1
    r = r1 + 1
    s.put(r, 2, "TOOLS, one-time (needed = 1)", "tot")
    for c in range(3, 11):
        s.put(r, c, None, "tot")
    s.put(r, 9, "=SUM(I%d:I%d)" % (r0, r1), "tot", fmt=USD2, name="tools_total")
    r += 1
    s.put(r, 2, "Optional tools not counted (needed = 0)", "text")
    s.put(r, 9, "=SUMPRODUCT(F%d:F%d,G%d:G%d,1-H%d:H%d)" % (r0, r1, r0, r1, r0, r1), "calc", fmt=USD2, name="tools_optional")
    ws.freeze_panes = "C%d" % r0
    autofit(s)
    ws.row_dimensions[hr].height = 30
    return s


# ----------------------------------------------------------------------------------------------
# sheet: Ordering checklist
# ----------------------------------------------------------------------------------------------
def build_checklist(book, lines):
    S = "Ordering checklist"
    s = Sh(book, S, [6, 18, 24, 48, 64, 34, 58, 13, 13])
    ws = s.ws
    s.put(1, 1, "Ordering checklist - what to buy, in which order, which file goes where", "title")
    s.merge(2, 1, 9, "Follow the steps from top to bottom. Lead times are typical values (the shops show the real ones at the checkout). 'Charge' = what the order costs you in total at that shop "
            "(goods + shipping + VAT/duty), from sheet 'Hidden costs'; with DDP/IOSS the taxes are paid at the checkout.")
    hr = 4
    s.head(hr, ["Step", "When", "Shop", "What to order", "Files to upload and settings", "Typical lead time", "Check before you pay", "Charge A (USD)", "Charge B (USD)"])
    ws.row_dimensions[hr].height = 30
    nlines = len(lines)

    def folder_list(folder):
        return "%s (%s)" % (ofd(folder), ", ".join(n for f, n, _ in ORDER_FILES if f == folder))
    steps = [
        ("0", "Today", "Your computer", "Nothing yet: update the prices.",
         "Open the LCSC links in sheet 'Main PCB BOM' (column E) and check the stock note column. Read sheet 'Summary' and change the blue cells you know better.",
         "1 hour", "Is every line still in stock? Low or zero retail stock at LCSC on " + V05_DATE + ": " + ", ".join(l["lcsc"] for l in lines if l["stock"] is not None and l["stock"] < 1000)
         + "; stock NOT read (pages not readable on " + CHECK + "): " + ", ".join(l["lcsc"] for l in lines if l["stock"] is None) + " (see the stock notes).", None, None),
        ("1", "Day 1", "AliExpress / EU web shop", "Bought parts: 2 cells per light + 1 spare, LED board 10 mm (+1 spare), laser module Class 2 (+ read its measured power), glass windows, screws, split rings, wire, tapes, silicone pad sheets (thermal gap pad 1.0 mm, rubber sheet 1.0 mm Shore A 70) and silicone adhesive, epoxy.",
         "Sheet 'Bought parts': search term, spec and link example for every item. Buy the small hardware from ONE web shop to save parcels.",
         "2-5 weeks (AliExpress), 3-7 days (EU shop)", "Size of the cells and of the LED board in the listing; laser power stated; shipping to Lithuania included; VAT shown.", "bp", None),
        ("2", "Day 1", "Your computer", "Check the order files of the package (nothing has to be generated).",
         "Ready to upload: %s; %s; %s. Only after a change of the design: re-run tools/kicad/build_all.py (re-routes the PCB, takes long; writes production/) or the housing "
         "build, and replace the files in order_files/." % (folder_list("1_JLCPCB"), folder_list("2_JLCCNC"), folder_list("3_JLC3DP")),
         "10 minutes", "%s must have %d lines and %d parts; its LCSC numbers are exactly column E of sheet 'Main PCB BOM'." % (ofp("BOM_JLCPCB.csv"), nlines, sum(l["qty"] for l in lines)), None, None),
        ("3", "Day 1-2", "jlcpcb.com", "5 bare PCBs + PCB assembly (Standard PCBA, both sides) of 2 boards (one light) or 5 boards.",
         "Gerber: %s. Settings: 4 layers, 0.8 mm, ENIG, qty 5, PCB Assembly ON, both sides, qty 2 or 5, confirm parts placement. "
         "Then upload %s and %s (see sheet 'JLCPCB order', section 1)." % (ofp("FlashKa_main_gerbers.zip"), ofp("BOM_JLCPCB.csv"), ofp("CPL_JLCPCB.csv")),
         "PCB 3-5 days + assembly 3-5 days + express shipping 3-5 days = about 2 weeks (the cart shows the exact build time)",
         "All BOM lines matched; part rotation and pin 1 in the placement preview (U4, U1, U2, U3, U5, Q1, Q2, Q4, Q5, J1, SW1-SW3, LED3, LED4); total below EUR 150 or accept the formal-clearance fee; shipping DDP.", "jlc0", None),
        ("4", "when the laser and cells have arrived", "Your desk", "Measure the delivered parts with a caliper.",
         "Laser body 6.0 mm x 12 mm; cell 6.0 x 16 x 47 mm incl. protection board; LED board 10.0 mm; glass 10.0 x 1.0 mm. Check the laser power if you have a meter.",
         "30 minutes", "Everything fits the spec of sheet 'Bought parts'; otherwise change the housing BEFORE ordering it.", None, None),
        ("5", "after step 4", "jlccnc.com", "Tray + lid, aluminium 6061-T6, bead blast + black anodize, laser marking; the three stainless caps (cap_main x1, cap_slide x2 per light, +1 spare of each), SUS304, bead blast.",
         "Files from %s: FlashKa_tray.step + FlashKa_tray.pdf, FlashKa_lid.step + FlashKa_lid.pdf, FlashKa_cap_main.step + FlashKa_cap_main.pdf, FlashKa_cap_slide.step + FlashKa_cap_slide.pdf "
         "(each drawing PDF has the SAME name as its STEP file); laser marking FlashKa_marking_lid_class2.dxf (or _class3R), FlashKa_marking_bottom.dxf, FlashKa_marking_minus_y.dxf, "
         "FlashKa_marking_plus_y.dxf. Settings: see sheet 'Housing', section 9. Order ONE set first." % ofd("2_JLCCNC"),
         "Quote within 24 h, 3 working days (SUS304: as fast as 5 days) + 1 day transfer + shipping 3-6 days = about 10-12 days",
         "Instant quote price -> type it in sheet 'Housing' (sections 6 and 7); M1.6 threads accepted; anodize tolerance note; the caps may be refused by size - then use another CNC service or the resin caps.", "jlc1", None),
        ("6", "after step 4", "jlc3dp.com", "Print kit: RF window insert, LED spacer ring, antenna spacer with floor plug, light-pipe tube, resin main cap and 2 resin slide caps on 1 mm sprues, ONE part - one kit per light + one spare kit. "
         "Laser sleeve only for a 4.5 mm laser.",
         "File: %s (+ %s only for a 4.5 mm laser). SLA resin 8001 translucent, as printed." % (ofp("FlashKa_print_kit.stl"), ofp("FlashKa_laser_sleeve.stl")),
         "build 2 days + shipping 3-6 days = about 1 week",
         "Quantity = kits (one per light + one spare). The kit is above the minimum build size; the quote may still warn about the 0.6 mm thin flanges of the "
         "resin caps (see 'Housing' section 10).", "jlc2", None),
        ("7", "when everything is there", "At home", "Inspect, assemble, test.",
         "Check every delivery against this list. Cut the resin parts off the print kit (flush cutters) and file the stubs flat; cut the two silicone pads to size (8.8 x 12.4 mm and 3.7 x 3.2 mm) "
         "and stick them on the lid bosses with a drop of silicone adhesive; glue the tube into the floor with clear epoxy (no cyanoacrylate). Solder the wires to J2 (cells), J3 (LED) "
         "and J5 (laser); check for shorts with the multimeter BEFORE connecting the cells; wear laser glasses when the laser is on.",
         "1-2 evenings", "Multimeter: no short between BAT+ and GND; cells at 3.6-4.2 V.", None, None),
        ("8", "after the first light works", "-", "Order the other lights (scenario B).",
         "The one-time costs (set-ups, stencil, anodizing lot, marking set-up) are already paid, so every additional light costs much less (see 'Summary', extra cost per additional light).",
         "-", "Keep the first light as the reference for the next batch.", None, None),
    ]
    r = hr
    for stp, when, shop, what, files, lead, chk, ck, _ in steps:
        r += 1
        s.put(r, 1, stp, "bold")
        s.put(r, 2, when, "text")
        s.put(r, 3, shop, "text")
        s.put(r, 4, what, "text")
        s.put(r, 5, files, "text")
        s.put(r, 6, lead, "text")
        s.put(r, 7, chk, "text")
        for c, sc in ((8, "A"), (9, "B")):
            if ck == "bp":
                f = "=" + s.ref("hc_landed_%s_3" % sc)
            elif ck and ck.startswith("jlc"):
                f = "=" + s.ref("hc_landed_%s_%s" % (sc, ck[3]))
            else:
                f = None
            s.put(r, c, f, "x" if f else "text", fmt=USD2)
    r += 1
    s.put(r, 3, "Total of the checkout charges (without the card fee)", "tot")
    for c in range(1, 10):
        if c != 3:
            s.put(r, c, None, "tot")
    s.put(r, 8, "=SUM(H%d:H%d)" % (hr + 1, r - 1), "tot", fmt=USD2)
    s.put(r, 9, "=SUM(I%d:I%d)" % (hr + 1, r - 1), "tot", fmt=USD2)
    r += 2
    s.merge(r, 1, 9, "File map", "sub", border=True)
    fm = [("JLCPCB", "%s: FlashKa_main_gerbers.zip, BOM_JLCPCB.csv, CPL_JLCPCB.csv  (the files tools/kicad/build_all.py writes to production/)" % ofd("1_JLCPCB")),
          ("JLCCNC", "%s: FlashKa_tray, FlashKa_lid, FlashKa_cap_main, FlashKa_cap_slide (each as .step + .pdf); laser marking FlashKa_marking_lid_class2.dxf (Class 2 module) or "
                     "FlashKa_marking_lid_class3R.dxf (only for a module measured above 1 mW), FlashKa_marking_bottom.dxf, FlashKa_marking_minus_y.dxf, FlashKa_marking_plus_y.dxf  "
                     "(from cad/; the PDFs are cad/FlashKa_tray_drawing.pdf, FlashKa_lid_drawing.pdf, FlashKa_cap_main_drawing.pdf and FlashKa_cap_slide_drawing.pdf renamed to the STEP names)" % ofd("2_JLCCNC")),
          ("JLC3DP", "%s: FlashKa_print_kit.stl (one kit per light + one spare kit); FlashKa_laser_sleeve.stl only for a 4.5 mm laser  (from cad/)" % ofd("3_JLC3DP")),
          ("Nowhere", "Upload only the files of order_files/. cad/ and production/ hold their sources (and the parts of the kit as single files); kicad/*, firmware/*, "
                      "app/* are for assembly and programming, not for ordering.")]
    for a, b in fm:
        r += 1
        s.merge(r, 1, 2, a, "bold", border=True)
        s.merge(r, 3, 9, b, "text", border=True)
    ws.freeze_panes = "A5"
    autofit(s)
    ws.row_dimensions[hr].height = 30
    return s


# ----------------------------------------------------------------------------------------------
# sheet: Summary
# ----------------------------------------------------------------------------------------------
def build_summary(book, lines):
    S = "Summary"
    s = Sh(book, S, [58, 14, 14, 14, 14, 14, 14, 14, 14, 11, 64])
    ws = s.ws
    s.put(1, 1, "FlashKa Keychain v0.6 - what it really costs", "title")
    s.merge(2, 1, 11, "Complete cost of building the light from scratch: electronics (JLCPCB), aluminium housing and stainless caps (JLCCNC), resin print kit (JLC3DP), bought parts, consumables, shipping, EU VAT and "
            "customs for Lithuania. Scenario A = you build ONE light (JLCPCB still sells 5 bare boards and assembles at least 2), scenario B = you build FIVE (change B to 2 to see two lights). "
            "Prices that did not change from v0.5 were read on %s; the pages of the new parts could not be read on %s, so those prices are ESTIMATES. "
            "Blue on amber cells are ESTIMATES because the shop shows its price only after you upload the files (or the page could not be read) - replace them with the real quote." % (V05_DATE, CHECK))
    s.merge(3, 1, 11, "Colour code: blue = typed-in number, blue on amber = ESTIMATE, black = formula, green = taken from another sheet. USD is the main currency, EUR = USD / rate.", "note")
    r = 5
    s.merge(r, 1, 11, "Inputs", "sub", border=True)
    r += 1
    s.param(r, "fx", "Exchange rate (USD per EUR)", fmt="0.0000", c_end=11)
    r += 1
    s.param(r, "lightsA", "Scenario A: lights you build", fmt="0", c_end=11)
    r += 1
    s.param(r, "lightsB", "Scenario B: lights you build", fmt="0", c_end=11)
    r += 1
    s.put(r, 1, "Price check date (v0.6)", "text")
    s.put(r, 2, CHECK, "in")
    s.merge(r, 3, 11, "v0.6 check. Prices and fees that did not change keep the date they were read, %s (v0.5 check; LCSC and JLC pages). The JLCPCB and LCSC pages of the new parts "
            "(C115357, C25104) could not be read on this date: those lines are ESTIMATES. Re-check before ordering." % V05_DATE, "note")
    r += 2
    s.merge(r, 1, 11, "Total cost", "sub", border=True)
    r += 1
    s.head(r, ["Cost group", "A: total (USD)", "A: total (EUR)", "A: per light (USD)", "A: per light (EUR)", "B: total (USD)", "B: total (EUR)",
               "B: per light (USD)", "B: per light (EUR)", "Share of B", "Basis"])
    ws.row_dimensions[r].height = 30
    lA, lB, fx = s.ref("lightsA"), s.ref("lightsB"), s.ref("fx")
    s.put(r + 1, 1, "Lights built", "text")
    s.put(r + 1, 2, "=" + lA, "calc", fmt="0")
    s.put(r + 1, 6, "=" + lB, "calc", fmt="0")
    r += 1
    rows = {}

    def line(key, label, fa, fb, kind="text", basis="", share=False, namea=None, nameb=None):
        nonlocal r
        r += 1
        rows[key] = r
        kk = "tot" if kind == "tot" else ("bold" if kind == "bold" else "text")
        s.put(r, 1, label, kk)
        s.put(r, 2, fa, "xtot" if kind == "tot" else "x" if kind != "calc" else "calc", fmt=USD2, name=namea)
        s.put(r, 3, "=B%d/%s" % (r, fx), "tot" if kind == "tot" else "calc", fmt=EUR2)
        s.put(r, 4, "=B%d/%s" % (r, lA), "tot" if kind == "tot" else "calc", fmt=USD2)
        s.put(r, 5, "=D%d/%s" % (r, fx), "tot" if kind == "tot" else "calc", fmt=EUR2)
        s.put(r, 6, fb, "xtot" if kind == "tot" else "x" if kind != "calc" else "calc", fmt=USD2, name=nameb)
        s.put(r, 7, "=F%d/%s" % (r, fx), "tot" if kind == "tot" else "calc", fmt=EUR2)
        s.put(r, 8, "=F%d/%s" % (r, lB), "tot" if kind == "tot" else "calc", fmt=USD2)
        s.put(r, 9, "=H%d/%s" % (r, fx), "tot" if kind == "tot" else "calc", fmt=EUR2)
        s.put(r, 10, None, "tot" if kind == "tot" else "text", fmt=PCT1)
        s.put(r, 11, basis, "tot" if kind == "tot" else "text")

    g = s.ref
    line("pcb", "1. PCB + assembly (JLCPCB)", "=" + g("jlc_goods_A"), "=" + g("jlc_goods_B"), "bold",
         "Fees: JLCPCB price page, read " + V05_DATE + " (v0.5 check, not refreshed). Parts: LCSC prices read " + V05_DATE + "; the two new lines are ESTIMATES (pages not readable on " + CHECK + "). Bare PCB: ESTIMATE.",
         namea="sum_pcb_A", nameb="sum_pcb_B")
    line("pcb1", "     of which bare PCBs (4 layers, 0.8 mm, ENIG)", "=" + g("fab_A"), "=" + g("fab_B"), "x", "ESTIMATE - the price appears only after the Gerber upload.")
    line("pcb2", "     of which assembly fees (set-up, stencil, joints, feeder, X-ray, ...)", "=" + g("fees_A"), "=" + g("fees_B"), "x", "JLCPCB fee page, sheet 'JLCPCB order'.")
    line("pcb3", "     of which components (%d lines, %d parts per board, incl. spares for placement loss)" % (len(lines), sum(l["qty"] for l in lines)), "=" + g("comps_A"), "=" + g("comps_B"), "x", "LCSC price tiers, sheet 'Main PCB BOM'.")
    line("house", "2. Housing (aluminium tray + lid, stainless caps, resin print kit)", "=" + g("housing_A"), "=" + g("housing_B"), "bold", "ESTIMATE - replace by the JLCCNC / JLC3DP instant quotes.",
         namea="sum_housing_A", nameb="sum_housing_B")
    line("house1", "     of which aluminium tray + lid (JLCCNC, bead blast + black anodize, laser marking)", "=" + g("cnc_alu_A"), "=" + g("cnc_alu_B"), "x", "ESTIMATE from volume, box, finish and marking, sheet 'Housing'.")
    line("house1b", "     of which stainless caps (JLCCNC, SUS304: main x1 + slide x2 per light, +1 spare of each)", "=" + g("cap_A"), "=" + g("cap_B"), "x",
         "ESTIMATE - JLCCNC publishes no per-part price. Fallback: the resin caps in the print kit (0 extra); switch in sheet 'Housing', section 7.")
    line("house2", "     of which resin print kit (JLC3DP, one kit per light + one spare)", "=" + g("resin_A"), "=" + g("resin_B"), "x", "ESTIMATE, sheet 'Housing'.")
    line("parts", "3. Bought parts (cells, LED board, laser, window, screws, split ring)", "=" + g("parts_A"), "=" + g("parts_B"), "bold",
         "Typical AliExpress prices (ESTIMATES), sheet 'Bought parts'.", namea="sum_parts_A", nameb="sum_parts_B")
    line("cons", "4. Consumables (wire, thermal tape, Kapton, foam tape, silicone pads and adhesive, epoxy)", "=" + g("cons_A"), "=" + g("cons_B"), "bold",
         "Typical prices (ESTIMATES), sheet 'Bought parts'.", namea="sum_cons_A", nameb="sum_cons_B")
    line("tax", "5. Shipping, VAT, customs duty, carrier and bank fees", "=" + g("tax_other_A"), "=" + g("tax_other_B"), "bold",
         "Computed from EU rules and shipping ESTIMATES, sheet 'Hidden costs'.", namea="sum_other_A", nameb="sum_other_B")
    line("tax1", "     of which shipping (3 JLC parcels + AliExpress parcels)", "=" + g("hc_sum_ship_A"), "=" + g("hc_sum_ship_B"), "x", "Shipping per parcel are ESTIMATES (JLC shows them in the cart).",
         namea="sum_ship_A", nameb="sum_ship_B")
    line("tax2", "     of which VAT 21 %", "=" + g("hc_sum_vat_A"), "=" + g("hc_sum_vat_B"), "x", "Lithuania 21 %, collected by JLC at checkout up to EUR 150 per parcel.",
         namea="sum_vat_A", nameb="sum_vat_B")
    line("tax3", "     of which customs duty and carrier fees", "=%s+%s" % (g("hc_sum_duty_A"), g("hc_sum_fee_A")), "=%s+%s" % (g("hc_sum_duty_B"), g("hc_sum_fee_B")), "x",
         "Flat EUR 3 per customs line up to EUR 150 per parcel; formal clearance + carrier fee above.", namea="sum_duty_A", nameb="sum_duty_B")
    line("tax4", "     of which card / currency conversion fee", "=" + g("card_A"), "=" + g("card_B"), "x", "ESTIMATE 1.5 % on the USD payments to JLC.",
         namea="sum_card_A", nameb="sum_card_B")
    r += 1
    s.put(r, 1, "     JLCPCB order vs the EUR 150 IOSS line (EUR left; negative = above, formal customs)", "text")
    s.put(r, 2, "=" + g("jlc_line_gap_A"), "x", fmt=EUR2)
    s.put(r, 6, "=" + g("jlc_line_gap_B"), "x", fmt=EUR2)
    s.merge(r, 7, 11, "Above the line the JLCPCB parcel pays a carrier fee of about EUR 15 (sheet 'Hidden costs', section 6).", "note")
    rt = r + 1
    line("total", "TOTAL for the lights (1 + 2 + 3 + 4 + 5)", "=B%d+B%d+B%d+B%d+B%d" % (rows["pcb"], rows["house"], rows["parts"], rows["cons"], rows["tax"]),
         "=F%d+F%d+F%d+F%d+F%d" % (rows["pcb"], rows["house"], rows["parts"], rows["cons"], rows["tax"]), "tot", "Per-light columns divide by the number of lights built.",
         namea="sum_total_A", nameb="sum_total_B")
    # register the remaining total cells under their model names
    book.reg("sum_total_eur_A", S, 3, rt)
    book.reg("sum_per_A", S, 4, rt)
    book.reg("sum_per_eur_A", S, 5, rt)
    book.reg("sum_total_eur_B", S, 7, rt)
    book.reg("sum_per_B", S, 8, rt)
    book.reg("sum_per_eur_B", S, 9, rt)
    for k in ("pcb", "house", "parts", "cons", "tax"):
        rr = rows[k]
        ws.cell(row=rr, column=10).value = "=F%d/F%d" % (rr, rt)
        ws.cell(row=rr, column=10).number_format = PCT1
    r += 1
    s.put(r, 1, "Extra cost of each additional light (scenario B vs A)", "bold")
    s.put(r, 2, "=IF(%s=%s,0,(F%d-B%d)/(%s-%s))" % (lB, lA, rt, rt, lB, lA), "calc", fmt=USD2, name="sum_marginal")
    s.put(r, 3, "=B%d/%s" % (r, fx), "calc", fmt=EUR2, name="sum_marginal_eur")
    s.merge(r, 4, 11, "Set-up fees, stencil, feeder loading, the anodizing lot fee, the marking set-up and most shipping are paid once, so the 2nd to 5th light is much cheaper than the first.", "note")
    # ---- what changed from v0.5
    r += 2
    s.merge(r, 1, 11, "What changed from v0.5 (same scenarios and exchange rate; USD)", "sub", border=True)
    r += 1
    s.merge(r, 1, 11, "The v0.5 values are typed in from the v0.5 cost workbook (sheet 'Summary', price check %s; the v0.5 package keeps that workbook). "
            "Board: %d BOM lines, %d placements, %d solder joints (v0.5: 33, 60, 217) - three push buttons instead of one, a second ring LED, five more resistors, no S1. "
            "Housing: new stainless caps and laser marking, a 5.2 mm lid with hold-down bosses, a print kit of seven parts instead of four."
            % (V05_DATE, len(lines), sum(l["qty"] for l in lines), sum(l["qty"] * l["pads"] for l in lines)), "note")
    r += 1
    s.head(r, ["Cost group", "v0.5: A", "v0.6: A", "Change A", "v0.5: B", "v0.6: B", "Change B"])
    s.merge(r, 8, 11, "What changed", "head", border=True)
    ws.row_dimensions[r].height = 28
    chg = [
        ("pcb", "pcb", "1. PCB + assembly (JLCPCB)", "More parts per board (SW1-SW3, LED4, R30-R34; S1 gone): more joints and components, one more unique BOM line (feeder fee) and one more X-ray part per board; the two new price lines are ESTIMATES. With five lights the X-ray price per part falls to the next tier (15 inspected parts instead of 10), so scenario B is slightly cheaper than in v0.5."),
        ("house", "house", "2. Housing", "Stainless caps (ESTIMATE) and laser marking (ESTIMATE) are new; the lid is a 5.2 mm part with bosses (bigger block); more set-ups and a higher complexity factor (sheet 'Housing', sections 4 and 5); the print kit has seven parts instead of four, still at the minimum price."),
        ("parts", "parts", "3. Bought parts", "Unchanged: cells, LED board, laser, window, screws, ring."),
        ("cons", "cons", "4. Consumables", "New: two silicone hold-down pad sheets and silicone adhesive (ESTIMATES)."),
        ("tax", "tax", "5. Shipping, VAT, customs, fees", "Follows from the larger orders: mostly VAT on the dearer housing and JLCPCB order, a second customs line for the stainless caps and a bigger card fee; shipping is unchanged (same parcels). Check the EUR 150 line of the JLCPCB order."),
        ("total", "total", "TOTAL for the lights", "Sum of the lines above."),
    ]
    for key, rk, lab, why in chg:
        r += 1
        bold = "tot" if key == "total" else "text"
        s.put(r, 1, lab, "tot" if key == "total" else "text")
        s.put(r, 2, V05_SUMMARY["A"][key], "in", fmt=USD2)
        s.put(r, 3, "=B%d" % rows[rk], "calc", fmt=USD2)
        s.put(r, 4, "=C%d-B%d" % (r, r), "calc", fmt=USD2, name="d_%s_A" % key)
        s.put(r, 5, V05_SUMMARY["B"][key], "in", fmt=USD2)
        s.put(r, 6, "=F%d" % rows[rk], "calc", fmt=USD2)
        s.put(r, 7, "=F%d-E%d" % (r, r), "calc", fmt=USD2, name="d_%s_B" % key)
        s.merge(r, 8, 11, why, "text", border=True)
    r += 1
    s.put(r, 1, "TOTAL per light (A: 1 light, B: 5 lights)", "bold")
    s.put(r, 2, V05_SUMMARY["A"]["per"], "in", fmt=USD2)
    s.put(r, 3, "=D%d" % rows["total"], "calc", fmt=USD2)
    s.put(r, 4, "=C%d-B%d" % (r, r), "calc", fmt=USD2, name="d_per_A")
    s.put(r, 5, V05_SUMMARY["B"]["per"], "in", fmt=USD2)
    s.put(r, 6, "=H%d" % rows["total"], "calc", fmt=USD2)
    s.put(r, 7, "=F%d-E%d" % (r, r), "calc", fmt=USD2, name="d_per_B")
    s.merge(r, 8, 11, "Per-light price in USD; the EUR values are in the table above.", "note")
    r += 2
    s.merge(r, 1, 11, "Not in the per-light cost", "sub", border=True)
    r += 1
    s.put(r, 1, "Tools (one-time purchase, only the tools marked 'needed')", "text")
    s.put(r, 2, "=" + g("tools_total"), "x", fmt=USD2, name="sum_tools")
    s.put(r, 3, "=B%d/%s" % (r, fx), "calc", fmt=EUR2)
    s.merge(r, 4, 11, "Sheet 'Tools'. If you already own soldering equipment, set 'Needed' to 0 there.", "note")
    rtl = r
    r += 1
    s.put(r, 1, "TOTAL including tools", "tot")
    s.put(r, 2, "=B%d+B%d" % (rt, rtl), "tot", fmt=USD2, name="grand_A")
    s.put(r, 3, "=B%d/%s" % (r, fx), "tot", fmt=EUR2)
    s.put(r, 4, None, "tot")
    s.put(r, 5, None, "tot")
    s.put(r, 6, "=F%d+B%d" % (rt, rtl), "tot", fmt=USD2, name="grand_B")
    s.put(r, 7, "=F%d/%s" % (r, fx), "tot", fmt=EUR2)
    s.put(r, 8, None, "tot")
    s.put(r, 9, None, "tot")
    r += 1
    s.put(r, 1, "Optional tools not counted", "text")
    s.put(r, 2, "=" + g("tools_optional"), "x", fmt=USD2)
    s.put(r, 3, "=B%d/%s" % (r, fx), "calc", fmt=EUR2)
    r += 1
    s.put(r, 1, "Risk reserve: second PCB + assembly order (not in any total)", "text")
    s.put(r, 2, "=" + g("risk_pcb"), "x", fmt=USD2)
    s.put(r, 3, "=B%d/%s" % (r, fx), "calc", fmt=EUR2)
    s.merge(r, 4, 11, "A new board often needs a second round. Landed cost of a second JLCPCB order like scenario A.", "note")
    r += 1
    s.put(r, 1, "Risk reserve: second housing order (not in any total)", "text")
    s.put(r, 2, "=" + g("risk_house"), "x", fmt=USD2)
    s.put(r, 3, "=B%d/%s" % (r, fx), "calc", fmt=EUR2)
    s.merge(r, 4, 11, "If the first tray does not fit the delivered laser / cells.", "note")
    # ---- how sure are we
    r += 2
    s.merge(r, 1, 11, "How reliable is each part of the total?", "sub", border=True)
    r += 1
    s.put(r, 1, "Item", "head")
    s.merge(r, 2, 4, "Status", "head", border=True)
    s.merge(r, 5, 11, "Where to replace it with a real number", "head", border=True)
    qual = [
        ("JLCPCB assembly fees", "READ from the JLCPCB price page (last updated Sep 09, 2026)", "Sheet 'JLCPCB order' section 5; the cart shows the final fee list."),
        ("Components at LCSC / JLC", "READ from the LCSC product pages on " + V05_DATE + " (v0.5 check) for %d lines; ESTIMATE for the %d new lines %s (pages not readable on " % (sum(1 for l in lines if not l["est"]), sum(1 for l in lines if l["est"]), " and ".join(l["lcsc"] for l in lines if l["est"])) + CHECK + ")",
         "Sheet 'Main PCB BOM' (amber cells); the JLC cart shows the real component price after the BOM upload."),
        ("Bare PCB price", "ESTIMATE (shown only after the Gerber upload)", "Sheet 'JLCPCB order' section 4: type the price from the cart."),
        ("Aluminium tray + lid", "ESTIMATE from volume, box, finish and laser marking", "Sheet 'Housing' section 6: type the JLCCNC instant quote."),
        ("Stainless caps", "ESTIMATE (JLCCNC publishes no per-part price; may be refused by size)", "Sheet 'Housing' section 7: type the JLCCNC instant quote, or switch to the resin caps."),
        ("Resin print kit", "ESTIMATE", "Sheet 'Housing' section 8: type the JLC3DP instant quote."),
        ("Bought parts and consumables", "ESTIMATES from AliExpress search snippets (" + V05_DATE + ") and typical prices; the new pads and adhesive are typical prices", "Sheet 'Bought parts': change the blue prices."),
        ("Shipping", "ESTIMATES (JLC publishes no rate table)", "Sheet 'Hidden costs' section 2: type the 'Shipping Estimate' of each cart."),
        ("VAT and customs", "COMPUTED from the EU rules; duty rates of the formal route are assumptions", "Sheet 'Hidden costs'. Watch the EUR 150 line of the JLCPCB order."),
        ("Tools", "ESTIMATES (typical prices)", "Sheet 'Tools'."),
    ]
    for a, b, c in qual:
        r += 1
        s.put(r, 1, a, "text")
        s.merge(r, 2, 4, b, "warn" if "ESTIMATE" in b else "text", border=True)
        s.merge(r, 5, 11, c, "text", border=True)
    r += 2
    s.merge(r, 1, 11, "Sheets: Summary | JLCPCB order | Main PCB BOM | Housing | Bought parts | Hidden costs | Tools | Ordering checklist. Notes on sources, estimates and what to re-check: docs/bom_notes.md; rebuild: python3 tools/parts_list.py.", "note")
    ws.freeze_panes = "A5"
    autofit(s)
    ws.row_dimensions[r].height = 15
    return s


# ----------------------------------------------------------------------------------------------
# build, recalculate, verify
# ----------------------------------------------------------------------------------------------
ERROR_CODES = ("#REF!", "#VALUE!", "#NAME?", "#DIV/0!", "#N/A", "#NUM!", "#NULL!")


def build_workbook(addr=None):
    lines = derive_bom()
    H, hsrc, stl = load_housing()
    hparts = housing_parts(H, stl)
    book = Book(addr)
    build_summary(book, lines)
    build_jlc(book, lines, H)
    build_bom(book, lines)
    build_housing(book, hparts, hsrc, H)
    build_bought(book, BOUGHT)
    build_hidden(book, TOOLS)
    build_tools(book, TOOLS)
    build_checklist(book, lines)
    wb = book.wb
    for ws in wb.worksheets:
        ws.page_setup.orientation = "landscape"
        ws.page_setup.paperSize = ws.PAPERSIZE_A4
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.print_options.gridLines = False
        ws.page_margins.left = ws.page_margins.right = 0.4
        ws.page_margins.top = ws.page_margins.bottom = 0.5
    wb["Main PCB BOM"].print_area = "A1:W%d" % (BOM_R0 + len(lines) + 40)
    wb.active = 0
    wb.properties.title = "FlashKa Keychain v0.6 - parts list and cost"
    wb.properties.creator = "tools/parts_list.py"
    return book, lines, H, hparts, hsrc


def make_book():
    b1 = build_workbook()[0]                      # pass 1 registers every cell name
    out = build_workbook(b1.addr)                 # pass 2 writes formulas with the real addresses
    if out[0].missing:
        raise SystemExit("unresolved cell names: %s" % sorted(out[0].missing))
    return out


def find_recalc():
    """Optional external recalculation script (path in FLASHKA_RECALC); otherwise LibreOffice is used."""
    env = os.environ.get("FLASHKA_RECALC")
    if env and os.path.isfile(env):
        return env
    return None


def recalc(path):
    """Let LibreOffice calculate every formula so that the file carries cached values."""
    rc = find_recalc()
    if rc:
        r = subprocess.run([sys.executable, os.path.basename(rc), path, "180"], cwd=os.path.dirname(rc), capture_output=True, text=True, timeout=400)
        try:
            j = json.loads(r.stdout)
        except ValueError:
            raise SystemExit("recalc.py gave no JSON: %s %s" % (r.stdout[-500:], r.stderr[-500:]))
        if "error" in j or j.get("status") != "success":
            raise SystemExit("recalculation problem: %s" % json.dumps(j)[:1500])
        print("recalculated with LibreOffice via %s: %s formulas, %s errors" % (rc, j.get("total_formulas"), j.get("total_errors")))
        return
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        print("WARNING: LibreOffice not found - formulas have no cached values (Excel will calculate them when it opens the file)")
        return
    tmp = tempfile.mkdtemp(prefix="flashka_recalc_")
    try:
        subprocess.run([soffice, "--headless", "--convert-to", "xlsx", "--outdir", tmp, path], check=True, capture_output=True, timeout=300)
        shutil.move(os.path.join(tmp, os.path.basename(path)), path)
        print("recalculated with plain soffice --convert-to")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build_all_bom_rows():
    """Run build_all.bom() (extracted with ast, build_all.py itself is not imported or run) into a temp dir."""
    src = open(os.path.join(HERE, "kicad", "build_all.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    fns = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ("refkey", "bom")]
    if len(fns) != 2:
        return None
    ns = {"csv": csv, "COMPONENTS": COMPONENTS}
    exec(compile(ast.Module(body=fns, type_ignores=[]), "build_all_bom", "exec"), ns)
    d = tempfile.mkdtemp(prefix="flashka_bom_")
    try:
        p = os.path.join(d, "BOM_JLCPCB.csv")
        ns["bom"](p)
        with open(p, newline="", encoding="utf-8") as f:
            return list(csv.reader(f))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def board_pads():
    """{reference: solder joints} read from the routed board kicad/FlashKa_main/FlashKa_main.kicad_pcb, or None if the file is missing.

    Counting rule (what JLCPCB bills as joints): every thru_hole pad counts; an smd pad with a name counts once per name (the
    exposed pad of the ESP32 module is drawn in 10 pieces with the same name = 1 joint); an smd pad without a name counts each
    (the four mounting tabs of the slide switch); np_thru_hole pads are holes, not joints."""
    path = os.path.join(REPO, "kicad", "FlashKa_main", "FlashKa_main.kicad_pcb")
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read().split("\n")
    except OSError:
        return None
    pads, cur = {}, None
    for ln in text:
        if ln.startswith("  (footprint "):
            cur = dict(ref=None, named=set(), unnamed=0, tht=0)
            continue
        if cur is None:
            continue
        m = re.search(r'\(fp_text reference "([^"]+)"', ln)
        if m:
            cur["ref"] = m.group(1)
        m = re.match(r'\s+\(pad "([^"]*)" (\w+) ', ln)
        if m:
            name, typ = m.groups()
            if typ == "smd":
                if name:
                    cur["named"].add(name)
                else:
                    cur["unnamed"] += 1
            elif typ == "thru_hole":
                cur["tht"] += 1
        if ln == "  )" and cur["ref"]:
            pads[cur["ref"]] = len(cur["named"]) + cur["unnamed"] + cur["tht"]
            cur = None
    return pads


def housing_script_kit():
    """Parts that tools/housing/flashka_housing.py puts on the sprues of FlashKa_print_kit, in order (read with ast), or None."""
    path = os.path.join(HERE, "housing", "flashka_housing.py")
    try:
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
    except (OSError, SyntaxError):
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", "")) == "build_print_kit" and len(node.args) >= 2 \
                and isinstance(node.args[1], ast.List):
            names = []
            for t in node.args[1].elts:
                if isinstance(t, ast.Tuple) and t.elts and isinstance(t.elts[0], ast.Constant):
                    names.append(t.elts[0].value)
            return names
    return None


def verify(path, book, lines, H, hparts):
    """Re-open the saved workbook and check it. Returns the list of problems (empty = all good)."""
    problems = []
    wbv = load_workbook(path, data_only=True)
    wbf = load_workbook(path)
    n_form = 0
    for ws in wbf.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and c.value.startswith("="):
                    n_form += 1
    n_err = 0
    n_none = 0
    for ws in wbv.worksheets:
        wf = wbf[ws.title]
        for row in ws.iter_rows():
            for c in row:
                v = c.value
                if isinstance(v, str) and (v in ERROR_CODES or v.startswith("Err:")):
                    n_err += 1
                    problems.append("error value %s in %s!%s" % (v, ws.title, c.coordinate))
                fv = wf[c.coordinate].value
                if isinstance(fv, str) and fv.startswith("=") and v is None:
                    n_none += 1
                    if n_none <= 5:
                        problems.append("formula without cached value %s!%s" % (ws.title, c.coordinate))
    print("workbook: %d sheets, %d formulas, %d error cells, %d formulas without value" % (len(wbf.worksheets), n_form, n_err, n_none))

    def val(name):
        sh, col, row = book.addr[name]
        return wbv[sh].cell(row=row, column=col).value

    # 1. every number of the Python model equals the workbook
    cp = model(P, lines, H, hparts, FINISH_DEFAULT, BOUGHT, TOOLS)
    n_cmp = 0
    skipped = []
    for k, exp in cp.items():
        if k not in book.addr:
            skipped.append(k)
            continue
        if k.startswith("resin_size_"):               # text cell (OK / TOO SMALL), compared below
            continue
        got = val(k)
        n_cmp += 1
        if not isinstance(got, (int, float)) or abs(got - exp) > 1e-6 * max(1.0, abs(exp)) + 1e-9:
            problems.append("model mismatch %s: workbook %r, python %r" % (k, got, exp))
    for k in skipped:
        if not (k.startswith("hc_formal_") or k.startswith("resin_size_")):
            problems.append("model value without a workbook cell: " + k)
    for k, exp in cp.items():
        if k.startswith("resin_size_"):
            n_cmp += 1
            if val(k) != ("OK" if exp else "TOO SMALL"):
                problems.append("size check mismatch %s: %r" % (k, val(k)))
    for k, exp in cp.items():
        if k.startswith("hc_formal_"):
            nm = "hc_route_" + k[len("hc_formal_"):]
            if val(nm) != ("formal" if exp else "IOSS"):
                problems.append("route mismatch %s: %r" % (nm, val(nm)))
    print("model check: %d workbook cells compared with the independent Python calculation" % n_cmp)

    # 2. BOM sheet vs COMPONENTS, vs build_all.bom(), vs production/BOM_JLCPCB.csv, vs the placement file, vs the routed board
    ws = wbv["Main PCB BOM"]
    rows = []
    for i in range(len(lines)):
        r = BOM_R0 + i
        rows.append([ws.cell(row=r, column=3).value, ws.cell(row=r, column=2).value, ws.cell(row=r, column=4).value,
                     ws.cell(row=r, column=5).value, ws.cell(row=r, column=10).value])
    exp_q = {}
    exp_refs = {}
    for rc in COMPONENTS:
        if rc["lcsc"] and not rc.get("dnp"):
            exp_q[rc["lcsc"]] = exp_q.get(rc["lcsc"], 0) + 1
            exp_refs.setdefault(rc["lcsc"], set()).add(rc["ref"])
    got_q = {}
    for v_, refs, fp_, lc, q in rows:
        got_q[lc] = got_q.get(lc, 0) + (q or 0)
        if set(refs.split(",")) != exp_refs.get(lc, set()):
            problems.append("designators differ for %s" % lc)
    if got_q != exp_q:
        problems.append("BOM quantities differ from COMPONENTS: %s" % {k: (got_q.get(k), exp_q.get(k)) for k in set(got_q) | set(exp_q) if got_q.get(k) != exp_q.get(k)})
    print("BOM check: %d lines, %d LCSC numbers, %d placements - all COMPONENTS LCSC numbers present with the right quantity: %s"
          % (len(rows), len(exp_q), sum(got_q.values()), "yes" if got_q == exp_q else "NO"))
    ref_rows = build_all_bom_rows()
    if ref_rows is None:
        print("note: build_all.py bom() could not be extracted; line-by-line comparison skipped")
    else:
        body = ref_rows[1:]
        if len(body) != len(rows):
            problems.append("build_all.bom() has %d lines, workbook %d" % (len(body), len(rows)))
        for i, (a, b) in enumerate(zip(body, rows)):
            if [a[0], a[1], a[2], a[3], int(a[4])] != [b[0], b[1], b[2], b[3], b[4]]:
                problems.append("line %d differs from build_all.bom(): %s vs %s" % (i + 1, a, b))
        print("BOM check: workbook agrees line by line with build_all.bom() (%d lines)" % len(body))
    for rel in ("production/BOM_JLCPCB.csv", "order_files/1_JLCPCB/BOM_JLCPCB.csv"):
        try:
            with open(os.path.join(REPO, rel), newline="", encoding="utf-8") as f:
                body = list(csv.reader(f))[1:]
        except OSError:
            problems.append("cannot read " + rel)
            continue
        bad = len(body) != len(rows)
        if bad:
            problems.append("%s has %d lines, workbook %d" % (rel, len(body), len(rows)))
        for i, (a, b) in enumerate(zip(body, rows)):
            if [a[0], a[1], a[2], a[3], int(a[4])] != [b[0], b[1], b[2], b[3], b[4]]:
                bad = True
                problems.append("line %d differs from %s: %s vs %s" % (i + 1, rel, a, b))
        print("BOM check: workbook agrees line by line with %s (%d lines): %s" % (rel, len(body), "NO" if bad else "yes"))
    refs_all = sorted(ref for l in lines for ref in l["refs"])
    try:
        with open(os.path.join(REPO, "production", "CPL_JLCPCB.csv"), newline="", encoding="utf-8") as f:
            cpl = sorted(r[0] for r in list(csv.reader(f))[1:])
        if cpl != refs_all:
            problems.append("designators of production/CPL_JLCPCB.csv differ from the BOM sheet: %s" % sorted(set(cpl) ^ set(refs_all)))
        print("BOM check: the %d designators of the BOM sheet are exactly the %d rows of production/CPL_JLCPCB.csv: %s"
              % (len(refs_all), len(cpl), "yes" if cpl == refs_all else "NO"))
    except OSError:
        problems.append("cannot read production/CPL_JLCPCB.csv")
    pads = board_pads()
    if pads is None:
        print("note: kicad/FlashKa_main/FlashKa_main.kicad_pcb not found; solder-joint check skipped")
        exp_joints = sum(l["qty"] * l["pads"] for l in lines)
    else:
        exp_joints = 0
        for l in lines:
            for ref in l["refs"]:
                if pads.get(ref) != l["pads"]:
                    problems.append("solder joints of %s: BOM line %s says %s, routed board has %s" % (ref, l["lcsc"], l["pads"], pads.get(ref)))
                exp_joints += pads.get(ref, 0)
        print("BOM check: solder joints per footprint agree with the pads of the routed board, %d joints per board" % exp_joints)
    for nm, exp in (("placements", len(refs_all)), ("joints", exp_joints), ("n_lines", len(rows))):
        if val(nm) != exp:
            problems.append("%s is %r, expected %d" % (nm, val(nm), exp))

    # 3. print kit: geometry consistent with its seven parts, above the minimum build size, ordered once per light + one spare,
    #    parts and order as in the housing script, and none of its parts ordered a second time as a separate print
    kits = [p for p in hparts if p.get("kit")]
    members = [p for p in hparts if p.get("in_kit")]
    flat = [p["key"] for p in members for _ in range(p.get("count", 1))]
    if len(kits) != 1 or flat != list(PRINT_KIT_KEYS):
        problems.append("print kit rows wrong: %d kit rows, parts %s" % (len(kits), flat))
    else:
        kit = kits[0]
        vsum = sum(p["vol"] * p.get("count", 1) for p in members)
        if not (vsum * 0.995 <= kit["vol"] <= vsum * 1.05):
            problems.append("print kit volume %.1f mm3 does not match its seven parts (%.1f mm3): kit STL and housing_interface.json from different builds?" % (kit["vol"], vsum))
        for p in members:
            if any(p["box"][k] > kit["box"][k] + 0.05 for k in (1, 2)):
                problems.append("part %s (%s) does not fit the print kit box (%s)" % (p["key"], dims(p["box"]), dims(kit["box"])))
        length = sum(p["box"][0] * p.get("count", 1) for p in members) + 2.5 * (len(flat) - 1)
        if abs(length - kit["box"][0]) > 0.3:
            problems.append("print kit is %.1f mm long, its seven parts side by side with 2.5 mm gaps need %.1f mm" % (kit["box"][0], length))
        if not jlc3dp_size_ok(kit["box"]):
            problems.append("print kit %s is below the JLC3DP minimum build size" % dims(kit["box"]))
        script = housing_script_kit()
        if script is None:
            print("note: tools/housing/flashka_housing.py build_print_kit call not found; kit contents not compared with the housing script")
        else:
            got = [KIT_SCRIPT_NAMES.get(n_, "?" + n_) for n_ in script]
            if got != flat:
                problems.append("print kit in flashka_housing.py is %s, the workbook assumes %s" % (got, flat))
        for sc in "AB":
            lights = P["lights" + sc]["v"]
            qk = val("resin_qty_kit_" + sc)
            if qk != lights + 1:
                problems.append("print kits ordered in scenario %s: %r, expected one per light + one spare = %d" % (sc, qk, lights + 1))
            twice = [p["key"] for p in members if (val("resin_qty_%s_%s" % (p["id"], sc)) or 0) != 0]
            if qk and twice:
                problems.append("scenario %s orders %s both in the print kit and as separate prints" % (sc, ", ".join(twice)))
        print("print kit check: %s, %.1f mm3 = seven parts %.1f mm3 + sprues %.1f mm3; same parts and order as flashka_housing.py: %s; %s kits (A) / %s kits (B), separate parts 0: %s"
              % (dims(kit["box"]), kit["vol"], vsum, kit["vol"] - vsum, "yes" if script is not None and got == flat else "not checked",
                 val("resin_qty_kit_A"), val("resin_qty_kit_B"),
                 "yes" if not any(val("resin_qty_%s_%s" % (p["id"], sc)) for p in members for sc in "AB") else "NO"))
    # the stainless caps are CNC parts of their own: quantities = lights x per light + spare, both cap files in the order folder
    for sc in "AB":
        lights = P["lights" + sc]["v"]
        for p in hparts:
            if p["proc"] == "STEEL":
                n_ = val("cap_qty_%s_%s" % (p["id"], sc))
                if n_ != lights * p["per_light"] + p["spare"]:
                    problems.append("%s pieces in scenario %s: %r" % (p["key"], sc, n_))
    print("cap check: stainless caps main %s / %s pieces, slide %s / %s pieces (scenario A / B), one STEP + one PDF each in %s"
          % (val("cap_qty_capm_A"), val("cap_qty_capm_B"), val("cap_qty_caps_A"), val("cap_qty_caps_B"), ofd("2_JLCCNC")))
    # housing data: the JSON and the STL files come from the same build
    if H is not HOUSING_SNAPSHOT:
        stl_ = load_housing()[2]
        for k in HOUSING_KEYS:
            a_, b_ = H["volumes_mm3"][k], stl_[k][3]
            if abs(a_ - b_) > 0.01 * a_:
                problems.append("volume of %s: JSON %.1f mm3, STL %.1f mm3 (different builds?)" % (k, a_, b_))
        t_, l_ = skin_lengths(H)
        if not (0 < l_ < t_):
            problems.append("skin lengths look wrong: tray %.1f mm, lid %.1f mm" % (t_, l_))
        # sizes that are written into texts (pad cut sizes, lid height) must still be the ones of the geometry
        par_ = H["params"]
        for nm, (w_, h_) in (("boss_box", PAD_CAN_MM), ("boss2_box", PAD_FRONT_MM)):
            bx = par_.get(nm)
            if not bx or abs((bx[1] - bx[0]) - w_) > 0.05 or abs((bx[3] - bx[2]) - h_) > 0.05:
                problems.append("hold-down boss %s is %s in housing_interface.json, the texts say a pad of %.1f x %.1f mm" % (nm, bx, w_, h_))
        if abs(stl_["FlashKa_lid"][2] - LID_HEIGHT_MM) > 0.05:
            problems.append("the lid is %.2f mm tall in cad/FlashKa_lid.stl, the texts say %.1f mm" % (stl_["FlashKa_lid"][2], LID_HEIGHT_MM))
        print("housing check: JSON volumes agree with the STL files (1 %%); skin grooves tray %.1f mm + lid %.1f mm; pad sizes %s and %s and lid height %.1f mm agree with the texts"
              % (t_, l_, dims(PAD_CAN_MM), dims(PAD_FRONT_MM), LID_HEIGHT_MM))

    # 4. order files: every file of ORDER_FILES exists in order_files/ and nothing else is there (README.txt of each folder excepted)
    n_of = 0
    for fold, name, _src in ORDER_FILES:
        n_of += 1
        if not os.path.isfile(os.path.join(REPO, "order_files", fold, name)):
            problems.append("missing order file order_files/%s/%s" % (fold, name))
    for fold in sorted({f for f, _, _ in ORDER_FILES}):
        d_ = os.path.join(REPO, "order_files", fold)
        extra = [n_ for n_ in sorted(os.listdir(d_)) if n_ != "README.txt" and (fold, n_) not in {(f, n) for f, n, _ in ORDER_FILES}] if os.path.isdir(d_) else []
        if extra:
            problems.append("files in order_files/%s/ that ORDER_FILES does not list: %s" % (fold, ", ".join(extra)))
    print("order files: %d files of ORDER_FILES found in order_files/ and no unlisted file in its three folders: %s"
          % (n_of, "yes" if not any(p.startswith(("missing order file", "files in order_files")) for p in problems) else "NO"))

    # 5. texts: no stale file locations, and every order_files/ path names a file of the package layout (ORDER_FILES)
    stale = [r"housing05", r"repo05", r"v0\.4 (set|drawings?|files|STEP|PDF)", r"\b(is|are) (the )?(OLD )?v0\.4\b", r"regenerat\w* (the )?(v0\.5 )?drawings?",
             r"production/ folder does not exist", r"[a]urora", r"button cap"]      # [a]urora = any file name from before the rename to FlashKa
    known = {(f, n) for f, n, _ in ORDER_FILES}
    n_txt = n_paths = 0
    for ws_ in wbf.worksheets:
        for row in ws_.iter_rows():
            for c in row:
                t = c.value
                if not isinstance(t, str) or t.startswith("="):
                    continue
                n_txt += 1
                for pat in stale:
                    if re.search(pat, t, re.I):
                        problems.append("stale text (%s) in %s!%s: %s" % (pat, ws_.title, c.coordinate, t[:120]))
                for m_ in re.finditer(r"order_files/([^/\s]+)/([A-Za-z0-9_.\-]*[A-Za-z0-9])?", t):
                    n_paths += 1
                    fold, name = m_.group(1), m_.group(2)
                    if not any(f == fold for f, _ in known) or (name and (fold, name) not in known):
                        problems.append("unknown order file %s in %s!%s" % (m_.group(0), ws_.title, c.coordinate))
    print("text check: %d text cells, %d order_files/ paths; all paths in the package layout, no stale file locations: %s"
          % (n_txt, n_paths, "yes" if not any(p.startswith(("stale text", "unknown order file")) for p in problems) else "NO"))

    # 6. docs/bom_notes.md says in which cells the real quotes and the main switches are typed: those must be cells of this workbook,
    #    and the quote cells must be empty (otherwise the totals are not the estimates)
    cells = [("pcb_fab5", False), ("cnc_alu_quote_A", True), ("cnc_alu_quote_B", True), ("cap_quote_A", True), ("cap_quote_B", True),
             ("resin_quote_A", True), ("resin_quote_B", True), ("ship_mode", False), ("finish_sel", False), ("caps_steel", False),
             ("mark_on", False), ("fx", False), ("lightsA", False), ("lightsB", False)]
    refs = []
    for nm, must_be_empty in cells:
        sh, col, row = book.addr[nm]
        refs.append("%s!%s%d" % (sh, get_column_letter(col), row))
        if must_be_empty and val(nm) is not None:
            problems.append("quote cell %s is not empty: the totals would not be the estimates" % refs[-1])
    r0, r2 = book.addr["ship_A_0"][2], book.addr["ship_A_2"][2]
    refs.append("%s!B%d:E%d" % (book.addr["ship_A_0"][0], r0, r2))
    try:
        with open(os.path.join(REPO, "docs", "bom_notes.md"), encoding="utf-8") as f:
            notes = f.read()
    except OSError:
        notes = None
    if notes is None:
        print("note: docs/bom_notes.md not found; its cell references were not checked")
    else:
        miss = [x for x in refs if x not in notes]
        for x in miss:
            problems.append("docs/bom_notes.md does not name the cell %s (cell addresses changed?)" % x)
        print("notes check: docs/bom_notes.md names all %d input cells at their right addresses (%s ...), the quote cells are empty: %s"
              % (len(refs), ", ".join(refs[:3]), "yes" if not miss else "NO"))
    return problems, cp


def report(cp):
    f = cp["fx"]
    print("\nRESULT (price check %s, fx %.4f USD/EUR)" % (CHECK, f))
    for sc, lab in (("A", "1 light "), ("B", "5 lights")):
        print("  %s: total $%.2f = EUR %.2f ; per light $%.2f = EUR %.2f   [PCB+asm %.2f, housing %.2f, parts %.2f, consumables %.2f, ship/VAT/fees %.2f]" % (
            lab, cp["sum_total_" + sc], cp["sum_total_eur_" + sc], cp["sum_per_" + sc], cp["sum_per_eur_" + sc], cp["sum_pcb_" + sc], cp["sum_housing_" + sc],
            cp["sum_parts_" + sc], cp["sum_cons_" + sc], cp["sum_other_" + sc]))
    print("  housing (1 / 5 lights): JLCCNC tray + lid $%.2f / $%.2f + stainless caps $%.2f / $%.2f; JLC3DP order $%.2f / $%.2f (print kits %d / %d at $%.2f each)" % (
        cp["cnc_alu_A"], cp["cnc_alu_B"], cp["cap_A"], cp["cap_B"], cp["resin_A"], cp["resin_B"], cp["resin_qty_kit_A"], cp["resin_qty_kit_B"], cp["resin_unit_kit"]))
    print("  change from v0.5 (1 / 5 lights): total %+.2f / %+.2f USD, per light %+.2f / %+.2f USD" % (cp["d_total_A"], cp["d_total_B"], cp["d_per_A"], cp["d_per_B"]))
    print("  extra cost per additional light $%.2f (EUR %.2f); tools $%.2f; risk reserve PCB $%.2f, housing $%.2f" % (
        cp["sum_marginal"], cp["sum_marginal_eur"], cp["tools_total"], cp["risk_pcb"], cp["risk_house"]))


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    flags = {a for a in argv[1:] if a.startswith("--")}
    out = os.path.abspath(args[0]) if args else os.path.join(REPO, "FlashKa_Parts_List_v0.6.xlsx")
    book, lines, H, hparts, hsrc = make_book()
    print("housing data: " + hsrc)
    if "--check-only" not in flags:
        book.wb.save(out)
        print("wrote", out)
        if "--no-recalc" in flags:
            print("recalculation skipped (--no-recalc): the file holds formulas without cached values, so the checks are skipped too.")
            print("Excel and LibreOffice calculate them when the file is opened; run without --no-recalc to verify the workbook.")
            return 0
        recalc(out)
    problems, cp = verify(out, book, lines, H, hparts)
    report(cp)
    if problems:
        print("\nPROBLEMS (%d):" % len(problems))
        for p in problems[:60]:
            print("  -", p)
        return 1
    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
