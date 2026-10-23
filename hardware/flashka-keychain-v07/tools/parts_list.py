#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""FlashKa Keychain v0.7 - complete bill of materials and cost workbook.

    python3 tools/parts_list.py [out.xlsx] [--no-recalc] [--check-only] [--lights-b N]

Writes FlashKa_Parts_List_v0.7.xlsx (8 sheets: Summary, JLCPCB order, Panel BOM, Housing,
Bought parts, Hidden costs, Tools, Ordering checklist), recalculates it with LibreOffice so
that every formula has a cached value, then re-opens the file and checks it:

  * no #REF!/#VALUE!/#NAME?/#DIV/0!/#N/A cells
  * every total in the workbook equals an independent Python calculation (model())
  * every LCSC number of COMPONENTS (main PCB + key board) is in the BOM sheet with the right quantity
    and designators; the BOM sheet is line by line identical to tools/kicad/build_all.py bom() AND to
    production/BOM_JLCPCB.csv (= order_files/1_JLCPCB/BOM_JLCPCB.csv, the panel BOM); its designators
    are the rows of production/CPL_JLCPCB.csv; the solder-joint count of every line is the pad count
    of its footprint in the two routed boards
  * the two machining kits hold the parts the housing build put into them (cad/housing_interface.json
    'machining_kits'), both kits and the aluminium mould plates are above JLCCNC's minimum size for the
    instant quote, and the volumes used here are those of the housing files
  * every file of ORDER_FILES exists in order_files/ and every order_files/ path in the workbook text is
    one of them, and no text names a file, a part or a shop of an older version
  * the housing JSON, the mould JSON and the STL files come from the same build (volumes agree within 1 %), and
    the sizes written into texts (pad cuts and thicknesses, lid height) are those of the geometry
  * docs/bom_notes.md names the input cells (quotes, switches, shipping) at their right addresses

Sources of truth
  electronics   tools/kicad/flashka_parts.py (COMPONENTS of both boards, EXTERNAL_BOM); the BOM is derived
                here with the same grouping as build_all.bom() (build_all.py itself is NOT run: it
                re-routes both boards)
  housing       cad/housing_interface.json (version 0.7: volumes, tray bounding box, panel layout, walls,
                kits, hold-down), cad/key_mould_checks.json (the resin and the aluminium mould plates) and the
                cad/*.stl files (bounding boxes); falls back to the snapshot embedded below when a JSON is not found
  ordering      JLCPCB gets ONE panel (key board + main PCB); JLCCNC gets the aluminium tray and lid, the
                PMMA kit (three main keys) and the POM-C kit (one per light); JLC3DP, in the same merged order
                and parcel, prints the two resin plates of the casting mould (once per builder; the aluminium
                mould from JLCCNC is the durable option); the two rubber side keys are cast at home
  file names    every upload instruction names the ready-to-upload folder of the package:
                order_files/1_JLCPCB/, order_files/2_JLCCNC/, order_files/3_rubber_keys/ (see ORDER_FILES;
                the names are those of the files that exist there, verify() checks it)
  prices        read from the vendor pages (see bom_notes.md and the Source columns). v0.7 keeps the v0.5
                and v0.6 readings that did not change (with their dates); what could not be read is a
                labelled ESTIMATE (blue number on amber)

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

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "kicad"))
from flashka_parts import COMPONENTS, EXTERNAL_BOM  # noqa: E402

V05_DATE = "2026-10-14"       # v0.5 price check: every price, fee and stock figure that did not change keeps this date
V06_CHECK = "2026-10-18"      # v0.6 price check (the JLCPCB / LCSC pages of two v0.6 parts could not be read that day)
V06_RESEARCH = "2026-10-16"   # day the JLCCNC pages and the Alps switch pages were read for v0.6
CHECK = "2026-10-21"          # v0.7 price check: pogo pin, JLCPCB panel fees, JLCCNC plastic limits, casting supplies
CHECK_1000 = "2026-10-22"     # price check of the 1000 lm power stage: buck, protection, LED board, TIR optic, ECON 80, Sugru,
                              # JLC3DP resin, merged JLCCNC + JLC3DP ordering, EU customs rules
CHECK_CELL = "2026-10-23"     # price check of the one-cell layout: the Vapcell INR14500 F15 cell and the nickel strip (nkon.nl),
                              # R3 (C4109, LCSC), the Vapcell K10 alternative (illumn.com)
FX_DATE = "2026-10-13"        # ECB reference rate date (not refreshed since v0.5)
GBP_PER_EUR = 0.8446          # ECB reference rate of the same day (13 Oct 2026), read on CHECK_1000; converts the RS UK optic price
VERSION = "0.7"
OUT_NAME = "FlashKa_Parts_List_v0.7.xlsx"

# ----------------------------------------------------------------------------------------------
# source URLs (every fee/price in the workbook carries one of these and the date it was read)
# ----------------------------------------------------------------------------------------------
U_FEES = "https://jlcpcb.com/help/article/pcb-assembly-price"
U_FAQ2 = "https://jlcpcb.com/help/article/pcb-assembly-faqs-part-2"
U_PANEL = "https://jlcpcb.com/help/article/Panelizing-your-PCB-for-Assembly"
U_PANELIZE = "https://jlcpcb.com/help/article/96-PCB-Panelization"
U_EXTRA = "https://jlcpcb.com/help/article/In-what-cases-will-there-be-charged-extra"
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
U_ZBOTIC = "https://zbotic.in/how-to-order-pcb-from-jlcpcb-and-pcbway-india-cost-guide/"
U_BASIC = "https://jlcpcb.com/parts/basic_parts"
U_JLCNC = "https://jlccnc.com/cnc-machining-quote"
U_JLCNC_HOME = "https://jlccnc.com/"
U_JLCNC_CAP = "https://jlccnc.com/capabilities/cnc-machining-service"
U_JLCNC_ORD = "https://jlccnc.com/help/article/cnc-machining-ordering-guidelines"
U_JLCNC_HOWTO = "https://jlccnc.com/help/article/how-to-place-cnc-orders"
U_JLCNC_SIZE = "https://jlccnc.com/help/article/what-are-the-maximum-and-minimum-processing-sizes-for-cnc"
U_JLCNC_PMMA = "https://jlccnc.com/blog/acrylic-and-pmma-cnc-machining"
U_JLCNC_POLISH = "https://jlccnc.com/blog/acrylic-polishing-guide"
U_JLCNC_FIN = "https://jlccnc.com/finishes"
U_JLCNC_COST = "https://jlccnc.com/blog/cnc-machining-cost-factors"
U_KAUPO = "https://kaupo.de/shop/en/URETHANE-RUBBER/PMC-SERIE/PMC-780/PMC-780-1-dry-Urethane-Rubber.html"
U_SMOOTHON = "https://www.smooth-on.com/products/pmc-780-dry"
U_SMOOTHON_SHOP = "https://shop.smooth-on.com/urethane-rubber/pmc-trade-series"
U_FORMLABS = "https://formlabs.com/eu/blog/vacuum-casting-urethane-casting-polyurethane-casting/"
U_DIAMOND = "https://www.diamondhmi.co.uk/what-does-it-cost-to-tool-a-silicone-rubber-keypad"
U_DIGIKEY_POGO = "https://azcus.digikey.com/en/products/detail/harwin-inc/P70-1010045R/6211190"
U_POGO_CHEAP = "https://www.lcsc.com/product-detail/pogo-pin-spring-probe-connector_xinyangze-yz00615050r-08_C7429459.html"
U_FS8205 = "https://www.lcsc.com/product-detail/C2830320.html"
U_RS_OPTIC = "https://uk.rs-online.com/web/p/led-lenses-reflectors/1862699"
U_RS_OPTIC100 = "https://uk.rs-online.com/web/p/led-lenses-reflectors/1862399"
U_MOUSER_CLIP = "https://eu.mouser.com/ProductDetail/Ledil/FP18198_LISA3-RS-CLIP16?qs=Rp5uXu7WBW9W1JI96qOsiA%3D%3D"
U_LEDIL_DS = "https://www.ledil.com/data/prod/Lisa/16558/16558-ds.pdf"
U_ECB_GBP = "https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/eurofxref-graph-gbp.en.html"
U_KAIDOMAIN = "https://kaidomain.com/SST-20-Gen-2-10W-3A-1100-Lumens-SMD-3535-LED"
U_NKON_F15 = "https://www.nkon.nl/en/vapcell-f15-inr14500-1500mah-3a.html"
U_NKON_NI = "https://nkon.nl/en/1-meter-nikkel-batterijsoldeerstrip-5mm-0-2mm.html"
U_NKON_H10 = "https://www.nkon.nl/en/vapcell-inr14500-1000mah-10a.html"
U_VAPCELL_F15 = "https://www.vapcelltech.com/h-pd-251.html"
U_K10 = "https://illumn.com/14500-vapcell-inr14500-k10-1000mah-8a-high-discharge-flat-top-li-ion-battery.html"
U_LCSC_IMG = "https://www.lcsc.com/product-image/{}.html"
U_ECON = "https://www.kaupo.de/shop/en/URETHANE-RUBBER/ECON-SERIES/Econ-80/Econ-80-1-Polyurethan.html"
U_SMOOTHON_ECON = "https://shop.smooth-on.com/econ-80"
U_SUGRU = "https://toom.de/p/allzweckkleber-sugru-formbar-schwarz-3-x-35-g/8400437"
U_3DP_HOME = "https://jlc3dp.com/"
U_3DP = "https://jlc3dp.com/3d-printing-quote"
U_MERGED = "https://jlccnc.com/news/merged-ordering"
U_COMBINE = "https://jlccnc.com/help/article/how-to-combine-orders"
U_EC_GUIDE = ("https://taxation-customs.ec.europa.eu/document/download/053e5b4e-f0be-4f20-9a23-3e3b659a6676_en?"
              "filename=Customs+Guidance+on+EUR+3+customs+duty.pdf")
U_JLC_TAX = "https://jlcpcb.com/help/article/customs,-duties-and-taxes"
U_UPS_LT = "https://ups.com/assets/resources/webcontent/en_GB/additional-service-charge-lt.pdf"
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
# (the v0.5 price check) and is unchanged since, except: C115357 and C25104 (new in v0.6; their JLCPCB and LCSC pages
# could not be read on V06_CHECK, so their tiers, stock and type are ESTIMATES), C22100007 (the pogo pin, new in
# v0.7, read on LCSC on CHECK), the three parts of the 1000 lm power stage (C139643 and C351410 read on CHECK_1000;
# the page of C238645 could not be read: ESTIMATE) and R3 of the one-cell layout (C4109, read on CHECK_CELL on the LCSC
# product-image page; the product page itself could not be opened). type = JLCPCB library type read on https://jlcpcb.com/partdetail/<LCSC>
# ("Preferred" is not shown there; it only matters for the Economic PCBA service, which cannot do double-sided boards);
# type_est = not read. read = date the tiers were read; pads = solder joints of the part (JLC counts joints/pads;
# verify() compares them with the pads of the two routed boards); cls = placement-loss class (see ATTRITION).
# The panel carries both boards: the main PCB (60 parts) and the key board (19 parts: SW1-SW3, LED3, LED4, eight
# resistors and the six pogo pins P1-P6).
# ----------------------------------------------------------------------------------------------
LCSC_DATA = {
    "C15850": dict(mpn="CL21A106KAYNNNE", mfr="Samsung Electro-Mechanics", type="Basic", stock=20, pads=2, cls="p0603",
                   tiers=[(20, .0695), (200, .0513), (600, .0419), (2000, .0342), (10000, .0315), (20000, .0297)],
                   role="Smoothing capacitor on the USB 5 V input (25 V rating needed). Main PCB.",
                   note="LOW: only 20 pcs at LCSC retail; JLC's own stock is separate - the BOM upload flags a shortage. "
                        "Any 10 uF 25 V X5R 0805 Basic part is a substitute."),
    "C19702": dict(mpn="CL10A106KP8NNNC", mfr="Samsung Electro-Mechanics", type="Basic", stock=181020, pads=2, cls="p0603",
                   tiers=[(20, .0311), (200, .023), (600, .0195), (4000, .0168), (8000, .0157), (20000, .015)],
                   role="10 uF capacitors that smooth the supply next to the chips (C2, C13, C15). Main PCB.", note=""),
    "C59461": dict(mpn="CL10A226MQ8NRNC", mfr="Samsung Electro-Mechanics", type="Basic", stock=4416440, pads=2, cls="p0603",
                   tiers=[(20, .0315), (200, .0236), (600, .0201), (4000, .0174), (8000, .0164), (20000, .0157)],
                   role="22 uF capacitors for the buck converter / power rails (C5, C8, C22). Main PCB.", note=""),
    "C15195": dict(mpn="CL05B103KB5NNNC", mfr="Samsung Electro-Mechanics", type="Basic", stock=0, pads=2, cls="p0402",
                   tiers=[(100, .005), (1000, .0038), (3000, .0033), (10000, .0029), (50000, .0028), (100000, .0027)],
                   role="10 nF capacitors: C11 (filter in the LED-current loop) and C23 (charge-pump capacitor of the buck U2). Main PCB.",
                   note="LCSC retail shows OUT OF STOCK; JLC lists it as Basic and has its own warehouse - the BOM upload "
                        "shows the real JLC stock. If flagged, pick another Basic 10 nF 0402 and update flashka_parts.py."),
    "C52923": dict(mpn="CL05A105KA5NQNC", mfr="Samsung Electro-Mechanics", type="Basic", stock=598000, pads=2, cls="p0402",
                   tiers=[(50, .0085), (500, .0067), (1500, .0059), (10000, .0053), (20000, .005), (50000, .0049)],
                   role="1 uF 25 V capacitors for supply decoupling (C12, C14, C17, C18). Main PCB.", note=""),
    "C1525": dict(mpn="CL05B104KO5NNNC", mfr="Samsung Electro-Mechanics", type="Basic", stock=0, pads=2, cls="p0402",
                  tiers=[(100, .0046), (1000, .0035), (3000, .003), (10000, .0026), (50000, .0025), (100000, .0024)],
                  role="100 nF capacitors: next to the chips' supply pins (C10, C16, C19, C20) and the supply filter of the protection IC U6 (C24). Main PCB.",
                  note="LCSC retail shows OUT OF STOCK, but the JLC basic-parts list shows 23,496,493 pcs (read "
                       + V05_DATE + "), so JLC can assemble it."),
    "C82044": dict(mpn="ESD5Z5.0T1G", mfr="onsemi", type="Extended", stock=370780, pads=2, cls="semi",
                   tiers=[(20, .0371), (200, .029), (600, .0245), (3000, .0204), (9000, .0181), (21000, .0168)],
                   role="D1: protects the board from static / voltage spikes on the USB 5 V line. Main PCB.", note=""),
    "C165948": dict(mpn="TYPE-C-31-M-12", mfr="Korean Hroparts Elec", type="Extended", stock=375745, pads=20, cls="mod",
                    tiers=[(5, .1729), (50, .1365), (150, .1187), (1000, .0963), (2000, .092), (5000, .0894)],
                    role="J1: USB-C socket (charging and data). 16 signal pads + 4 shell legs = 20 joints. Main PCB.", note=""),
    "C602028": dict(mpn="FHD4020S-1R0MT", mfr="cjiang", type="Extended", stock=8210, pads=2, cls="mod",
                    tiers=[(10, .1102), (100, .086), (300, .0726), (3000, .0645), (6000, .0575), (9000, .0538)],
                    role="L1: 1 uH power inductor of the buck converter U2 (LED driver). Main PCB.", note=""),
    "C2874113": dict(mpn="NH-B1010RGBT-HF", mfr="NATIONSTAR", type="Extended", stock=345020, pads=4, cls="semi",
                     tiers=[(20, .0081), (200, .0072), (600, .0068), (2000, .0065), (10000, .0063), (20000, .0053)],
                     role="LED3, LED4: the two RGB ring LEDs (1 x 1 mm, 4 pads under the package) on the bottom face of the key board; they shine into the clear main key.", note=""),
    "C22100007": dict(mpn="P70-1010045R", mfr="Harwin", type="Extended", type_est=True, stock=100, pads=1, cls="mod", read=CHECK,
                      tiers=[(1, 1.89), (30, 1.44), (100, 1.26)],
                      role="P1-P6: the six gold spring contacts (pogo pins) on the top face of the key board; they press on the six round pads J6 of the main PCB "
                           "(SMT, no peg, free height 5.0 mm, working height 4.0 mm, 1.17 N).",
                      note="New in v0.7. LCSC retail stock 100 pcs on " + CHECK + " (enough for 2 or 5 panels). JLCPCB's own stock and library type were not read "
                           "('Extended' assumed): if the BOM upload shows no stock, buy the pins into your JLCPCB parts library first (Parts Manager, order from "
                           "LCSC stock). Other source: Digikey USD 0.696 at 100 pcs, 21 weeks lead time (" + U_DIGIKEY_POGO + ")."),
    "C15127": dict(mpn="AO3401A", mfr="AOS", type="Basic", stock=164910, pads=3, cls="semi",
                   tiers=[(5, .1026), (50, .0829), (150, .0728), (500, .0644), (3000, .0615), (6000, .0596)],
                   role="Q1: P-channel MOSFET, the on/off switch of the laser. Main PCB.", note=""),
    "C5224240": dict(mpn="2N7002W-7-F-ES", mfr="ElecSuper", type="Extended", stock=17000, pads=3, cls="semi",
                     tiers=[(50, .0224), (500, .017), (3000, .0141), (6000, .0123), (24000, .0108), (51000, .0099)],
                     role="Q2, Q4, Q5: small N-channel MOSFET switches (LED current sink, laser gate, reset pulse). Main PCB.",
                     note=""),
    "C25905": dict(mpn="0402WGF5101TCE", mfr="UNI-ROYAL", type="Basic", stock=2302500, pads=2, cls="p0402",
                   tiers=[(100, .0024), (1000, .0019), (3000, .0015), (10000, .0014), (50000, .0012)],
                   role="R1, R2: 5.1 k resistors on the USB-C CC pins (tell a charger to supply 5 V). Main PCB.", note=""),
    "C4109": dict(mpn="0402WGF2001TCE", mfr="UNI-ROYAL", type="Basic", stock=5175800, pads=2, cls="p0402", read=CHECK_CELL,
                  tiers=[(100, .0026), (1000, .002), (3000, .0016), (10000, .0015), (50000, .0012)],
                  role="R3: 2.0 k resistor, sets the battery charge current (about 494 mA, the standard charge of the 14500 cell). Main PCB.",
                  note="New for the 14500 cell (R3 was 3.3 k, C25890, about 280 mA). Tiers and stock read on LCSC's product-image page " + U_LCSC_IMG.format("C4109")
                       + " (the product page could not be opened); library type Basic as read on " + V05_DATE + " (the same part was R16 of v0.6)."),
    "C25764": dict(mpn="0402WGF2003TCE", mfr="UNI-ROYAL", type="Basic", stock=1520700, pads=2, cls="p0402",
                   tiers=[(100, .0018), (1000, .0014), (3000, .0011), (10000, .001), (50000, .0009)],
                   role="R10: 200 k resistor (voltage divider of the buck converter). Main PCB.", note=""),
    "C25792": dict(mpn="0402WGF4702TCE", mfr="UNI-ROYAL", type="Basic", stock=3114700, pads=2, cls="p0402",
                   tiers=[(100, .0026), (1000, .002), (3000, .0017), (10000, .0015), (50000, .0013)],
                   role="R12: 47 k resistor. Main PCB.", note=""),
    "C25744": dict(mpn="0402WGF1002TCE", mfr="UNI-ROYAL", type="Basic", stock=2846900, pads=2, cls="p0402",
                   tiers=[(100, .0033), (1000, .0026), (3000, .0022), (10000, .0021), (50000, .0017)],
                   role="10 k resistors: pull-ups / pull-downs (R8, R9, R13, R18, R21, R22). Main PCB.", note=""),
    "C25879": dict(mpn="0402WGF2201TCE", mfr="UNI-ROYAL", type="Basic", stock=586000, pads=2, cls="p0402",
                   tiers=[(100, .0018), (1000, .0013), (3000, .0011), (50000, .0009)],
                   role="2.2 k resistors: R14 (LED-current loop) and R16 (VSET divider: sets the full-scale LED current to 3,552 mA), main PCB; "
                        "R31 (button ladder, previous key), key board.", note=""),
    "C11702": dict(mpn="0402WGF1001TCE", mfr="UNI-ROYAL", type="Basic", stock=0, pads=2, cls="p0402",
                   tiers=[(100, .0031), (1000, .0024), (3000, .002), (10000, .0018), (50000, .0016)],
                   role="1 k resistors: R19 (laser gate) and R36 (current-sense input of the protection IC U6), main PCB; R30 (button ladder, next key), key board.",
                   note="LCSC retail shows OUT OF STOCK; JLC lists it as Basic - check the JLC stock at BOM upload."),
    "C25076": dict(mpn="0402WGF1000TCE", mfr="UNI-ROYAL", type="Basic", stock=4360400, pads=2, cls="p0402",
                   tiers=[(100, .0013), (1000, .001), (3000, .0009), (10000, .0008)],
                   role="100 ohm resistors: R24, R25, R33, R34 (green and blue leg of each ring LED), key board; R35 (supply filter of the protection IC U6), main PCB.", note=""),
    "C26083": dict(mpn="0402WGF1004TCE", mfr="UNI-ROYAL", type="Basic", stock=541000, pads=2, cls="p0402",
                   tiers=[(100, .0024), (1000, .0018), (3000, .0016), (10000, .0014), (50000, .0011)],
                   role="R27, R28: 1 M resistors. Main PCB.", note=""),
    "C25741": dict(mpn="0402WGF1003TCE", mfr="UNI-ROYAL", type="Basic", stock=3791500, pads=2, cls="p0402",
                   tiers=[(100, .0015), (1000, .0012), (3000, .001), (10000, .0009), (50000, .0008)],
                   role="100 k resistors: pull-ups / dividers (7 of them). Main PCB.", note=""),
    "C92740": dict(mpn="MS05W2F200MT5E", mfr="UNI-ROYAL", type="Extended", stock=4880, pads=2, cls="p0603",
                   tiers=[(20, .0183), (200, .018), (600, .0177), (2000, .0174)],
                   role="RS1: 20 milliohm current-sense resistor, 0.5 W (measures the LED current; 0.18 W at 3 A). Main PCB.", note=""),
    "C77130": dict(mpn="NCP15WF104F03RC", mfr="muRata", type="Extended", stock=298120, pads=2, cls="p0402",
                   tiers=[(20, .0219), (200, .0173), (600, .0147), (2000, .0132), (10000, .0119), (20000, .0112)],
                   role="RT1: 100 k NTC thermistor = temperature sensor at the front edge of the main PCB.", note=""),
    # --- new in v0.6. The JLCPCB part page and the LCSC page of both numbers could not be read on V06_CHECK: ESTIMATE lines
    #     (not read again for v0.7).
    "C115357": dict(mpn="SKRKAEE020", mfr="ALPSALPINE", type="Extended", type_est=True, stock=None, pads=2, cls="mod", est=True, read=V06_CHECK,
                    tiers=[(10, .0759), (100, .0616)],
                    role="SW1, SW2, SW3: the three key switches (main, next, previous) on the bottom face of the key board. Alps top-push tact switch 3.9 x 2.9 x 2.0 mm, 1.6 N, 200k cycles.",
                    note="ESTIMATE, page not read: JLCPCB and LCSC pages of C115357 could not be read on " + V06_CHECK + " (not read again in v0.7). Tiers = the sibling "
                         "Alps SKRPABE010 (C115360) read on LCSC on " + V06_RESEARCH + " (qty 10 $0.0759, qty 100 $0.0616). Stock unknown. Library type 'Extended' "
                         "assumed (every Alps tact switch checked on JLCPCB is Extended).",
                    src="ESTIMATE - LCSC and JLCPCB pages of C115357 could not be read on " + V06_CHECK + ". Tiers of the sibling C115360 (LCSC, read "
                        + V06_RESEARCH + "): qty 10 $0.0759, qty 100 $0.0616."),
    "C25104": dict(mpn="0402WGF3300TCE", mfr="UNI-ROYAL", type="Basic", type_est=True, stock=None, pads=2, cls="p0402", est=True, read=V06_CHECK,
                   tiers=[(100, .0024), (1000, .0019), (3000, .0015), (10000, .0014), (50000, .0012)],
                   role="R23, R32: 330 ohm resistors (red leg of the two ring LEDs). Key board.",
                   note="ESTIMATE, page not read: JLCPCB and LCSC pages of C25104 could not be read on " + V06_CHECK + " (not read again in v0.7). Tiers copied from "
                        "the sibling 5.1 k resistor C25905 (read " + V05_DATE + "); part number inferred from the UNI-ROYAL naming; library type 'Basic' assumed "
                        "(same series as the other Basic 0402 resistors). Stock unknown.",
                   src="ESTIMATE - LCSC and JLCPCB pages of C25104 could not be read on " + V06_CHECK + ". Tiers of the sibling C25905 (LCSC, read " + V05_DATE + ")."),
    "C431540": dict(mpn="MSK12C02", mfr="SHOU HAN", type="Extended", stock=170330, pads=7, cls="mod",
                    tiers=[(10, .0543), (100, .0444), (300, .0394), (3000, .0337), (6000, .0323), (9000, .0312)],
                    role="S2: slide switch = the laser safety interlock. Main PCB.", note=""),
    "C12044": dict(mpn="TP4057-42-SOT26-R", mfr="TOP POWER ASIC", type="Extended", stock=32025, pads=6, cls="semi",
                   tiers=[(5, .1426), (50, .1166), (150, .1036), (500, .0938), (3000, .0761), (6000, .0722)],
                   role="U1: battery charger chip (500 mA linear Li-ion charger). Main PCB.", note=""),
    # --- new with the 1000 lm power stage (CHECK_1000): the 4 A buck and the cell protection on the main PCB
    "C139643": dict(mpn="TPS62095RGTR", mfr="Texas Instruments", type="Extended", stock=2092, pads=17, cls="semi", read=CHECK_1000,
                    tiers=[(1, 1.35)],
                    role="U2: 4 A synchronous buck converter that drives the LED (100 % duty mode, VQFN-16 3 x 3 mm: 16 pins + exposed pad = 17 joints). Main PCB.",
                    note="New with the 1000 lm power stage. LCSC stock 2,092 on " + CHECK_1000 + "; only the price for 1 piece was read (used for every quantity)."),
    "C351410": dict(mpn="DW01A", mfr="PUOLOP", type="Extended", stock=109860, pads=6, cls="semi", read=CHECK_1000,
                    tiers=[(20, .025)],
                    role="U6: 1-cell Li-ion protection IC (over-charge, over-discharge, over-current, short circuit) for the 14500 cell, which has no "
                         "protection board of its own. Main PCB, bottom face.",
                    note="New with the 1000 lm power stage. Only the tier from 20 pieces was read (used for smaller quantities too)."),
    "C238645": dict(mpn="SE8830A", mfr="SINO-IC", type="Extended", type_est=True, stock=None, pads=6, cls="semi", est=True, read=CHECK_1000,
                    tiers=[(10, .10), (100, .08)],
                    role="Q3: dual N-MOSFET (13 / 14.5 mOhm typical / maximum at 4.5 V) in the cell minus, switched by U6, which senses its drop directly (Kelvin tracks); "
                         "the DW01A trips at about 4.3-4.5 A with hot MOSFETs (5.3-5.6 A at 25 C; 3.0-3.15 A in the worst case). Main PCB, bottom face.",
                    note="ESTIMATE, page not read: the LCSC page of C238645 could not be read on " + CHECK_1000 + " (price and stock unknown; library type 'Extended' "
                         "assumed). No drop-in substitute: an 8205A-type dual MOSFET has about twice the on-resistance, and the DW01A would then cut the light off "
                         "in turbo (trip at about 2-3 A). If the BOM upload shows no stock, buy it into your JLCPCB parts library from LCSC stock or wait for stock. "
                         "Before ordering, check the pin order in the data sheet: pins 1-6 must be S1, D, S2, G2, D, G1 (as on the FS8205A; the LCSC data sheet "
                         "shows it only as a picture). The board is laid out for exactly this order.",
                    src="ESTIMATE - the LCSC page of C238645 could not be read on " + CHECK_1000 + ". Priced at about twice the common FS8205A dual MOSFET (C2830320: "
                        "USD 0.050 from 10 pieces, LCSC, read " + CHECK_1000 + ")."),
    "C181502": dict(mpn="TLV333IDCKR", mfr="Texas Instruments", type="Extended", stock=18425, pads=5, cls="semi",
                    tiers=[(5, .3543), (50, .2788), (150, .2465), (500, .1927), (3000, .1747), (6000, .1639)],
                    role="U3: precision op-amp in the LED-current control loop. Main PCB.", note=""),
    "C2838502": dict(mpn="ESP32-C3-MINI-1-N4", mfr="Espressif", type="Extended", stock=8387, pads=53, cls="mod",
                     tiers=[(1, 3.0672), (10, 2.7002), (30, 2.5127), (100, 2.1441), (650, 2.0536), (1300, 2.0141)],
                     role="U4: the brain - ESP32-C3 module with Bluetooth LE / Wi-Fi, 4 MB flash and antenna. Main PCB.",
                     note="Marked NRND (not recommended for new designs) by Espressif; the successor ESP32-C3-MINI-1-H4X "
                          "(C41349510) is the drop-in alternative if this one disappears."),
    "C841192": dict(mpn="RT9080-33GJ5", mfr="Richtek", type="Extended", stock=27375, pads=5, cls="semi",
                    tiers=[(5, .1207), (50, .0982), (150, .087), (500, .0786), (3000, .0613), (6000, .058)],
                    role="U5: 3.3 V voltage regulator for the ESP32 module. Main PCB.", note=""),
}
# placement-loss classes: JLC buys a few more pieces than the boards need (they are billed inside the component
# price and discarded). JLC publishes no table; these numbers are ESTIMATES in the style of typical JLC quotes.
ATTRITION = [("p0402", 10, "0402 resistors / capacitors / NTC (tiny, easily lost by the pick-and-place machine)"),
             ("p0603", 5, "0603 and 0805 capacitors, current-sense resistor"),
             ("semi", 2, "small semiconductors: MOSFETs, ICs, TVS diode, RGB LED"),
             ("mod", 1, "big or expensive parts: ESP32 module, USB-C socket, inductor, switches, pogo pins")]
# solder joints per footprint (checked against the two routed boards by verify()): U4 53 pads (the footprint draws the
# exposed pad 49 as 10 pieces: 62 pad shapes), J1 16 signal pads + 4 shell legs, U2 17 (16 pins + the exposed pad; its two
# thermal vias and the paste windows of the exposed pad are not joints), S2 7, U1 6, U6 6, Q3 6, U3 5, U5 5, LED3/LED4 4,
# Q1/Q2/Q4/Q5 3, SW1-SW3 2, pogo pins P1-P6 1, everything else 2. J2/J3/J5 are wire pads and J6 the pogo target pads (no
# LCSC number, not assembled); H1/H2 are the key board's screw holes.

for _d in LCSC_DATA.values():
    _d.setdefault("read", V05_DATE)       # date the tiers and the stock were read
    _d.setdefault("est", False)           # True = ESTIMATE (page not read)
    _d.setdefault("type_est", False)      # True = library type assumed, not read
    _d.setdefault("src", "")              # price source text of an ESTIMATE line


# ----------------------------------------------------------------------------------------------
# housing snapshot (cad/housing_interface.json and cad/key_mould_checks.json of the v0.7 housing build) - used only when
# those files cannot be found
# ----------------------------------------------------------------------------------------------
HOUSING_DIR = "cad"
HOUSING_SNAPSHOT = {
    "version": "0.7",
    "volumes_mm3": {"FlashKa_tray": 8328.5, "FlashKa_lid": 3120.7, "FlashKa_rf_window": 117.5, "FlashKa_antenna_spacer": 825.4,
                    "FlashKa_key_main": 112.4, "FlashKa_key_side": 55.8, "FlashKa_key_stiffener": 11.0, "FlashKa_laser_sleeve": 110.9},
    "mass_g": {"FlashKa_tray": 22.487, "FlashKa_lid": 8.426, "FlashKa_rf_window": 0.166, "FlashKa_antenna_spacer": 1.164, "FlashKa_key_main": 0.134,
               "FlashKa_key_side": 0.064, "FlashKa_key_stiffener": 0.087, "FlashKa_laser_sleeve": 0.156},
    "tray_bbox": [-0.002, 99.2, -10.005, 10.003, -0.009, 18.003],
    "pcb_outline": [[10.1, -8.25], [32.8, -8.25], [32.8, 8.25], [10.1, 8.25], [8.8, 6.95], [8.8, -6.95]],
    "params": {"W": 20.0, "H": 18.0, "C_edge": 3.4, "lid_t": 1.5, "pan_depth": 0.3, "pan_r": 0.8, "tex_pitch": 0.9, "tex_depth": 0.2, "grv_depth": 0.3,
               "grv_head": [1.5, 2.7, 3.9], "grv_tail_off": [5.4, 4.2, 3.0], "frw_box": [36.35, 41.45, 5.4, 1.5],
               "boss_box": [24.85, 33.65, -7.6, 4.8], "boss2_box": [18.4, 22.1, 0.25, 3.25], "pad_t0": 1.5, "pad_gap": 1.15, "pad2_t0": 1.0,
               "pad2_gap": 0.75, "pad_E_mpa": 1.0, "pad2_E_mpa": 5.3, "las_d": 6.0, "opt_bore": 10.1, "opt_od": 10.0, "lan_slot_w": 3.6, "lan_slot_len": 4.6, "L_batt": 51.6,
               "cell_d": 14.0, "cell_len": 49.0, "cell_max": [14.5, 50.4], "kit_min": [30.0, 20.0, 8.0], "side_key": [4.2, 10.0, 1.5],
               "main_key": [6.8, 6.8, 1.0], "stiffener": [3.6, 9.4, 0.3, 0.8], "doubler": [2.0, 2.0, 0.3], "mould_n": 4, "mould_size": [48.0, 28.0],
               "resin_t": [6.0, 5.0]},
    "panel_layout": [
        {"name": "top PCB zone", "face": "top", "u0": 12.99, "u1": 32.75, "v0": -5.4, "v1": 5.4, "r": 0.8},
        {"name": "bottom bay 1 (with the RF window)", "face": "bottom", "u0": 36.35, "u1": 64.1, "v0": -5.4, "v1": 5.4, "r": 0.8},
        {"name": "top bay 1", "face": "top", "u0": 43.25, "u1": 64.1, "v0": -5.4, "v1": 5.4, "r": 0.8},
        {"name": "minus_y bay 1", "face": "minus_y", "u0": 43.25, "u1": 64.1, "v0": 4.6, "v1": 13.4, "r": 0.8},
        {"name": "plus_y bay 1", "face": "plus_y", "u0": 43.25, "u1": 64.1, "v0": 4.6, "v1": 13.4, "r": 0.8},
        {"name": "bottom bay 2", "face": "bottom", "u0": 65.3, "u1": 86.15, "v0": -5.4, "v1": 5.4, "r": 0.8},
        {"name": "top bay 2", "face": "top", "u0": 65.3, "u1": 86.15, "v0": -5.4, "v1": 5.4, "r": 0.8},
        {"name": "minus_y bay 2", "face": "minus_y", "u0": 65.3, "u1": 86.15, "v0": 4.6, "v1": 13.4, "r": 0.8},
        {"name": "plus_y bay 2", "face": "plus_y", "u0": 65.3, "u1": 86.15, "v0": 4.6, "v1": 13.4, "r": 0.8},
        {"name": "minus_y PCB zone", "face": "minus_y", "u0": 25.15, "u1": 42.05, "v0": 4.6, "v1": 13.4, "r": 0.8},
        {"name": "plus_y PCB zone", "face": "plus_y", "u0": 19.6, "u1": 42.05, "v0": 4.6, "v1": 13.4, "r": 0.8}],
    # the thinnest metal walls of min_walls (for the JLCCNC wall note; none below 0.5 mm), the 0.3 mm edge on the lid top and the metal under the texture
    "min_walls": {"front screw tap to the optic bore floor (thread crest)": 0.51, "front screw tap to head rear face (thread crest)": 0.51,
                  "front screw tap to the optic bore floor": 0.685, "wall front lid tap -Y - optic bore": 0.685,
                  "front screw tap to head rear face": 0.685, "LED wire groove (upper) to lid seat": 0.751,
                  "bezel edge to floor RF window (band)": 0.8, "tail front wall (bay to slot)": 0.8,
                  "lid top face: rear countersink edge to the slot chamfer": 0.3},
    "texture_min_metal_mm": 1.0,
    "machining_kits": {"FlashKa_pmma_kit": {"size": [52.8, 22.0, 8.5], "parts": [{"file": "FlashKa_key_main.step"}] * 3},
                       "FlashKa_pom_kit": {"size": [45.4, 39.3, 17.0],
                                           "parts": [{"file": "FlashKa_rf_window.step"}, {"file": "FlashKa_rf_window.step"},
                                                     {"file": "FlashKa_antenna_spacer.step"}]}},
    "holddown": {"preload_total_N": 39.68, "pogo_force_total_N": 7.37, "max_ledge_lift_mm": 0.0004, "lift_limit_mm": 0.02},
}
# cad/key_mould_checks.json: the resin mould (JLC3DP, the default) and the aluminium mould (JLCCNC, the durable option)
MOULD_RESIN = "resin (JLC3DP SLA, default)"
MOULD_ALU = "aluminium (JLCCNC, durable)"
MOULD_SNAPSHOT = {
    MOULD_ALU: {"cavity half": {"bbox_mm": [48.0, 28.0, 8.002], "volume_mm3": 10234.9, "mass_g": 27.6},
                "lid": {"bbox_mm": [48.0, 28.0, 8.471], "volume_mm3": 10186.0, "mass_g": 27.5}},
    MOULD_RESIN: {"cavity half": {"bbox_mm": [48.0, 28.0, 8.506], "volume_mm3": 6240.3},
                  "lid": {"bbox_mm": [48.0, 28.0, 5.472], "volume_mm3": 4821.4},
                  "cast key vs model key": {"cast_volume_mm3": 54.284}},
}
# the STL files of the two resin plates (what JLC3DP gets); verify() compares their volumes with key_mould_checks.json
RESIN_STL = {"cavity half": "FlashKa_key_mould_resin_cavity", "lid": "FlashKa_key_mould_resin_lid"}
# min_walls entries that are gaps, surface features, edges or thread lengths, not metal walls (the 0.3 mm land on the lid's top face
# between a rear countersink and the slot chamfer is an edge to break lightly: docs/housing_v07_notes.md, section 7)
WALL_NOT_METAL = ("laser module top below the PCB", "texture: groove width", "texture: land between grooves", "transverse groove width",
                  "transverse groove land", "KB tap: thread engagement of the M1.6 x 2.5 screw",
                  "laser set screw: hole behind the lid front edge (thread crest)", "lid top face: rear countersink edge to the slot chamfer")
# min_walls entries that measure the two front lid taps at the tap drill: the same walls as their thread-root entries (0.51 mm),
# which are the thinnest point, so the wall note names only those
WALL_AT_TAP_DRILL = ("front screw tap to the optic bore floor", "front screw tap to head rear face", "wall front lid tap -Y - optic bore")
# plain names for the wall note (the JSON names the thinnest point of an internal thread "thread crest": it is the thread root)
WALL_LABELS = {"front screw tap to head rear face (thread crest)": "the two front lid taps at the thread root, to the head's rear face and to the optic bore floor",
               "front screw tap to the optic bore floor (thread crest)": "the two front lid taps at the thread root, to the optic bore floor and to the head's rear face",
               "LED wire groove (upper) to lid seat": "the upper LED wire groove to the head-block top under the lid"}

# v0.6 facts used by the "removed" lines of the fine-feature table in sheet 'Housing': the fine-feature minutes of the
# v0.6 estimate (v0.6 workbook, sheet 'Housing', section 4) and the length of the v0.6 skin seams
V06_GEOM = dict(feat_tray=38.09, feat_lid=7.52, skin_tray_mm=646.5, skin_lid_mm=220.2)

# totals of the v0.6 cost workbook (sheet 'Summary', price check 2026-10-18, exchange rate 1.1188) in USD:
# only used by the "what changed from v0.6" group of the Summary. A = 1 light, B = 5 lights (the same scenarios as in v0.7).
V06_SUMMARY = {
    "A": dict(pcb=174.327736586, house=122.557509176, parts=56.75, cons=27.79, tax=238.7826868206, total=620.2079325826, per=620.2079325826),
    "B": dict(pcb=194.686691465, house=382.38754588, parts=211.3, cons=27.79, tax=378.822693718613, total=1194.98693106361, per=238.997386212723),
}
# totals of the FIRST v0.7 LAYOUT (its cost workbook, price check 2026-10-21: SST-20 behind a glass window, 2 x 400 mAh cells
# with protection boards, a 3 A buck, the aluminium casting mould, PMC-780 DRY rubber) in USD, for 1, 2 and 5 lights: only used
# by the "what changed since the first v0.7 layout" group of the Summary (and docs/bom_notes.md)
V07R_CHECK = "2026-10-21"
V07R_SUMMARY = {
    1: dict(pcb=228.66, house=169.16, parts=63.75, cons=142.19, tax=315.13, total=918.89, per=918.89),
    2: dict(pcb=228.66, house=242.46, parts=101.65, cons=142.19, tax=349.12, total=1064.08, per=532.04),
    5: dict(pcb=269.12, house=473.59, parts=218.30, cons=142.19, tax=452.61, total=1555.81, per=311.16),
}
V07R_DETAIL = {   # sub-items of the same workbook (1 / 2 / 5 lights) that changed since
    1: dict(alu=96.29, kit=37.75, mould=35.12, cast=114.40, ship=81.50, vat=146.31, duty=78.60, card=8.72, tools=174.00),
    2: dict(alu=156.59, kit=50.75, mould=35.12, cast=114.40, ship=84.50, vat=171.26, duty=83.18, card=10.19, tools=174.00),
    5: dict(alu=337.47, kit=101.00, mould=35.12, cast=114.40, ship=84.50, vat=255.70, duty=97.04, card=15.37, tools=174.00),
}
# totals of the TWO-POUCH-CELL LAYOUT that came just before the one-cell octagon (this workbook with two 320 mAh pouch cells in
# the 20 x 16 mm body, price check 2026-10-22) in USD, for 1, 2 and 5 lights: only used by the "what the battery and body change
# costs" group of the Summary (and docs/bom_notes.md)
V07P_CHECK = "2026-10-22"
V07P_SUMMARY = {
    1: dict(pcb=236.91, house=131.89, parts=73.85, cons=113.45, tax=298.71, total=854.81, per=854.81),
    2: dict(pcb=236.91, house=202.96, parts=110.34, cons=113.45, tax=353.29, total=1016.95, per=508.47),
    5: dict(pcb=282.08, house=427.41, parts=237.18, cons=113.45, tax=457.99, total=1518.11, per=303.62),
}
V07P_DETAIL = {   # sub-items of the same workbook (1 / 2 / 5 lights): tray + lid, kits, the cells (two per light + one spare), shipping, VAT, duty
    1: dict(alu=97.32, kit=31.25, cells=15.00, cell_each=5.00, ship=99.50, vat=137.68, duty=53.70, tools=164.00, parcels=9),
    2: dict(alu=158.64, kit=41.00, cells=25.00, cell_each=5.00, ship=102.50, vat=163.76, duty=77.45, tools=164.00, parcels=9),
    5: dict(alu=342.60, kit=81.50, cells=55.00, cell_each=5.00, ship=102.50, vat=249.85, duty=90.92, tools=164.00, parcels=9),
}


def v07r(lights):
    """The first-layout totals for this number of lights (the 5-light values for a number that the table does not hold)."""
    return V07R_SUMMARY.get(int(lights), V07R_SUMMARY[5])


def v07p(lights):
    """The two-pouch-cell totals for this number of lights (the 5-light values for a number that the table does not hold)."""
    return V07P_SUMMARY.get(int(lights), V07P_SUMMARY[5])


def thinnest_walls(H, n=3):
    """[(mm, what), ...] the n thinnest metal walls listed in housing_interface.json (min_walls)."""
    w = dict(H.get("min_walls", {}))
    return sorted((v, k) for k, v in w.items() if k not in WALL_NOT_METAL and isinstance(v, (int, float)))[:n]


def thin_walls(H, lim=0.8):
    """[(mm, what), ...] every metal wall of min_walls below lim (JLCCNC's recommended minimum), one entry per value (the pairwise
    wall list repeats some walls under a second name); the three thinnest if none is below lim."""
    out, seen = [], set()
    for v, k in thinnest_walls(H, n=10 ** 6):
        if v < lim - 1e-9 and v not in seen and k not in WALL_AT_TAP_DRILL:
            out.append((v, WALL_LABELS.get(k, k)))
            seen.add(v)
    return out or thinnest_walls(H)


# bounding boxes and volumes measured from cad/*.stl (binary STL) on CHECK_CELL (the octagon body), mm (x, y, z) and mm3 - rounded
# like load_housing() rounds them
STL_SNAPSHOT = {
    "FlashKa_tray": (99.20, 20.00, 18.00, 8328.9), "FlashKa_lid": (95.00, 20.00, 7.25, 3120.7),
    "FlashKa_rf_window": (8.30, 12.20, 1.40, 117.5), "FlashKa_antenna_spacer": (6.00, 16.80, 15.85, 825.4),
    "FlashKa_key_main": (7.60, 7.60, 2.75, 112.4), "FlashKa_key_side": (5.20, 11.00, 1.85, 55.8),
    "FlashKa_key_stiffener": (3.60, 9.40, 0.60, 11.0), "FlashKa_laser_sleeve": (10.00, 6.00, 5.97, 110.9),
}
HOUSING_KEYS = tuple(STL_SNAPSHOT)
# what the two machining kits hold (verify() compares this with 'machining_kits' of housing_interface.json)
KIT_PARTS = {"FlashKa_pmma_kit": ("FlashKa_key_main", "FlashKa_key_main", "FlashKa_key_main"),
             "FlashKa_pom_kit": ("FlashKa_rf_window", "FlashKa_rf_window", "FlashKa_antenna_spacer")}
PMMA_PER_KIT = 3             # main keys per PMMA kit
PAD_CAN_MM = (8.8, 12.4)     # hold-down pad cut from the thermal gap pad (module can boss, params 'boss_box'); verify() compares
PAD_CAN_T = (1.5, 1.15)      # gap pad: free thickness, compressed (params 'pad_t0', 'pad_gap')
PAD_FRONT_MM = (3.7, 3.0)    # hold-down pad cut from the rubber sheet (front boss, params 'boss2_box')
PAD_FRONT_T = (1.0, 0.75)    # rubber sheet: free thickness, compressed (params 'pad2_t0', 'pad2_gap')
LID_HEIGHT_MM = 7.25         # lid height (the 3.4 mm cap with the hold-down bosses) written into texts; verify() compares it with cad/FlashKa_lid.stl
PANEL_MM = (45.0, 32.5)      # the JLCPCB panel (tools/kicad/panel_jlc.py; its Gerber job file gives 45.1 x 32.6 with the 0.1 mm outline stroke)
KB_MM = (19.0, 14.8, 1.0)    # key board: width, height, corner radius (housing_interface.json 'key_board')

# ready-to-upload folder of the delivered package (these files exist in order_files/; verify() checks it):
# (folder, file name in the folder, where the packaging step takes it from). Upload instructions use ofp()/ofd().
ORDER_FILES = [
    ("1_JLCPCB", "FlashKa_panel_gerbers.zip", "production/FlashKa_panel_gerbers.zip (written by tools/kicad/build_all.py)"),
    ("1_JLCPCB", "BOM_JLCPCB.csv", "production/BOM_JLCPCB.csv (both boards)"),
    ("1_JLCPCB", "CPL_JLCPCB.csv", "production/CPL_JLCPCB.csv (both boards, panel coordinates)"),
    ("2_JLCCNC", "FlashKa_tray.step", "cad/FlashKa_tray.step"),
    ("2_JLCCNC", "FlashKa_tray.pdf", "cad/FlashKa_tray_drawing.pdf (2 sheets), copied under the STEP name"),
    ("2_JLCCNC", "FlashKa_lid.step", "cad/FlashKa_lid.step"),
    ("2_JLCCNC", "FlashKa_lid.pdf", "cad/FlashKa_lid_drawing.pdf, copied under the STEP name"),
    ("2_JLCCNC", "FlashKa_pmma_kit.step", "cad/FlashKa_pmma_kit.step (three main keys on tabs in a frame)"),
    ("2_JLCCNC", "FlashKa_pmma_kit.pdf", "cad/FlashKa_pmma_kit_drawing.pdf, copied under the STEP name"),
    ("2_JLCCNC", "FlashKa_pom_kit.step", "cad/FlashKa_pom_kit.step (lid RF insert x2 and the antenna spacer on tabs)"),
    ("2_JLCCNC", "FlashKa_pom_kit.pdf", "cad/FlashKa_pom_kit_drawing.pdf, copied under the STEP name"),
    ("2_JLCCNC", "FlashKa_key_main.step", "cad/FlashKa_key_main.step (single part, for shops that take small parts)"),
    ("2_JLCCNC", "FlashKa_key_main.pdf", "cad/FlashKa_key_main_drawing.pdf, copied under the STEP name"),
    ("2_JLCCNC", "FlashKa_rf_window.step", "cad/FlashKa_rf_window.step (single part)"),
    ("2_JLCCNC", "FlashKa_antenna_spacer.step", "cad/FlashKa_antenna_spacer.step (single part)"),
    ("2_JLCCNC", "FlashKa_pom_parts.pdf", "cad/FlashKa_pom_parts_drawing.pdf (drawing of the POM-C single parts and the laser sleeve)"),
    ("2_JLCCNC", "FlashKa_laser_sleeve.step", "cad/FlashKa_laser_sleeve.step (optional, only for a laser module thinner than 6 mm)"),
    ("3_rubber_keys", "FlashKa_key_side.step", "cad/FlashKa_key_side.step (cast rubber body)"),
    ("3_rubber_keys", "FlashKa_key_side.pdf", "cad/FlashKa_key_side_drawing.pdf, copied under the STEP name"),
    ("3_rubber_keys", "FlashKa_key_stiffener.step", "cad/FlashKa_key_stiffener.step (plate + doubler, 0.3 mm stainless steel shim)"),
    ("3_rubber_keys", "FlashKa_key_side_with_plate.step", "cad/FlashKa_key_side_with_plate.step (rubber body + stiffener as glued)"),
    ("3_rubber_keys", "FlashKa_key_mould_resin_cavity.stl", "cad/FlashKa_key_mould_resin_cavity.stl (resin mould part for JLC3DP, the default)"),
    ("3_rubber_keys", "FlashKa_key_mould_resin_lid.stl", "cad/FlashKa_key_mould_resin_lid.stl (resin mould part for JLC3DP)"),
    ("3_rubber_keys", "FlashKa_key_mould_resin.step", "cad/FlashKa_key_mould_resin.step (the resin mould closed with its four M3 bolts, reference)"),
    ("3_rubber_keys", "FlashKa_key_mould.step", "cad/FlashKa_key_mould.step (the aluminium mould, closed)"),
    ("3_rubber_keys", "FlashKa_key_mould.pdf", "cad/FlashKa_key_mould_drawing.pdf (both moulds), copied under the STEP name"),
    ("3_rubber_keys", "FlashKa_key_mould_cavity.step", "cad/FlashKa_key_mould_cavity.step (aluminium mould part for JLCCNC, the durable option)"),
    ("3_rubber_keys", "FlashKa_key_mould_lid.step", "cad/FlashKa_key_mould_lid.step (aluminium mould part for JLCCNC)"),
    ("optional_laser_label", "FlashKa_laser_label_lid_class2.dxf", "tools/housing/laser_label.py (only for a light sold or given to others)"),
    ("optional_laser_label", "FlashKa_laser_label_lid_class2.png", "tools/housing/laser_label.py (preview of the label)"),
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
    """Return (data dict, source text, stl dict, mould dict) of the v0.7 housing: cad/housing_interface.json,
    cad/key_mould_checks.json (both moulds: mould[MOULD_RESIN] and mould[MOULD_ALU]) and cad/*.stl.

    The embedded snapshots are used only when a JSON file is missing, incomplete or not version 0.7 (or, per file, when an
    STL is missing; the source text then names the files that came from the snapshot)."""
    d = os.path.join(REPO, HOUSING_DIR)
    try:
        with open(os.path.join(d, "housing_interface.json")) as f:
            j = json.load(f)
        why = "incomplete or not version " + VERSION
    except (OSError, ValueError):
        j, why = None, "not found"
    try:
        with open(os.path.join(d, "key_mould_checks.json")) as f:
            mould = json.load(f)
        if not all(k in mould.get(m, {}) for m in (MOULD_RESIN, MOULD_ALU) for k in ("cavity half", "lid")):
            raise ValueError
        msrc = "%s/key_mould_checks.json" % HOUSING_DIR
    except (OSError, ValueError, AttributeError):
        mould, msrc = MOULD_SNAPSHOT, "the embedded snapshot of %s/key_mould_checks.json" % HOUSING_DIR
    need = ("volumes_mm3", "tray_bbox", "pcb_outline", "params", "panel_layout", "machining_kits", "min_walls")
    if j is not None and str(j.get("version")) == VERSION and all(k in j for k in need) \
            and all(k in j["volumes_mm3"] for k in HOUSING_KEYS):
        stl, from_snapshot = {}, []
        for k in STL_SNAPSHOT:
            r = stl_bbox_volume(os.path.join(d, k + ".stl"))
            if r:
                stl[k] = tuple(round(x, 2) if i < 3 else round(x, 1) for i, x in enumerate(r))
            else:
                stl[k] = STL_SNAPSHOT[k]
                from_snapshot.append(k + ".stl")
        src = "%s/housing_interface.json (version %s) + %s + %s/*.stl" % (HOUSING_DIR, j.get("version", "?"), msrc, HOUSING_DIR)
        if from_snapshot:
            src += " (embedded snapshot used for the missing %s)" % ", ".join(from_snapshot)
        return j, src, stl, mould
    return (HOUSING_SNAPSHOT, "embedded snapshot of %s/housing_interface.json and %s/*.stl (the JSON was %s) + %s" % (HOUSING_DIR, HOUSING_DIR, why, msrc),
            dict(STL_SNAPSHOT), mould)


def panel_counts(H):
    """(tray panels, lid panels): the recessed panels of 'panel_layout' (the lid carries the 'top' panels)."""
    lay = H.get("panel_layout") or HOUSING_SNAPSHOT["panel_layout"]
    n_lid = sum(1 for q in lay if q["face"] == "top")
    return len(lay) - n_lid, n_lid


def texture_lengths(H):
    """(tray_mm, lid_mm): length of the 90 deg V grooves of the panel texture = panel area / pitch.

    Source: 'panel_layout' of housing_interface.json (11 recessed panels, corners R0.8) and the parameters 'tex_pitch' and
    'frw_box': the floor RF window opening inside the first bottom panel is a POM-C plug (textured in the POM-C kit), so its
    area is not aluminium texture. Panels on the face 'top' belong to the lid, all others to the tray."""
    par = H.get("params", {})
    lay = H.get("panel_layout") or HOUSING_SNAPSHOT["panel_layout"]
    pitch = par.get("tex_pitch", 0.9)
    fx0, fx1, fhy, fr = par.get("frw_box") or (36.2, 41.3, 7.0, 1.5)
    tray = lid = 0.0
    for q in lay:
        a = (q["u1"] - q["u0"]) * (q["v1"] - q["v0"]) - (4 - math.pi) * q["r"] ** 2
        if q["face"] == "bottom" and q["u0"] <= fx0 + 1e-6 and q["u1"] >= fx1 - 1e-6:
            a -= (fx1 - fx0) * 2 * fhy - (4 - math.pi) * fr ** 2
        if q["face"] == "top":
            lid += a / pitch
        else:
            tray += a / pitch
    return tray, lid


def octagon_facets(H):
    """(bottom/top facet, side facet, diagonal facet, perimeter) of the body section in mm: W x H with 45 deg legs C_edge."""
    par = H.get("params", {})
    W, Hh, c = par.get("W", 20.0), par.get("H", 18.0), par.get("C_edge", 3.4)
    ch = c * math.sqrt(2.0)
    return W - 2 * c, Hh - 2 * c, ch, 2 * (W - 2 * c) + 2 * (Hh - 2 * c) + 4 * ch


def groove_lengths(H):
    """(tray_mm, lid_mm): length of the transverse V grooves (0.3 deep) round the body.

    Section of the body: the octagon W x H with 45 deg legs C_edge (bottom and top facets W - 2c, side facets H - 2c, four
    diagonal facets c x sqrt 2). The head set (grv_head, 3 grooves at X 1.5-3.9) runs over the top, the bottom and the four
    diagonal facets only (the bores leave too little metal under the side facets), all in the tray (the lid starts at X 4.2);
    the tail set (3 grooves, 'grv_tail_off' = their distances from the tail face) runs all round: the lid is the cap above the
    edges between the side facets and the upper diagonal facets, so it takes the top facet and the two upper diagonal facets
    (no lip), the tray the rest."""
    par = H.get("params", {})
    flat, side, diag, full = octagon_facets(H)
    head = 2 * flat + 4 * diag
    lid_share = flat + 2 * diag
    n_head = len(par.get("grv_head") or [1.5, 2.7, 3.9])
    n_tail = len(par.get("grv_tail") or par.get("grv_tail_off") or [5.4, 4.2, 3.0])
    return n_head * head + n_tail * (full - lid_share), n_tail * lid_share


def holddown_note(H):
    """Risk text about the two silicone hold-down pads; the numbers are read from 'holddown' of housing_interface.json."""
    hd = H.get("holddown") or {}
    head = ("HOLD-DOWN PADS: the two silicone pads (sheet 'Bought parts') are bought and cut by you: %.1f x %.1f mm from the %.1f mm gap pad (compressed "
            "to %.2f mm) and %.1f x %.1f mm from the %.1f mm rubber sheet (compressed to %.2f mm). " % (PAD_CAN_MM[0], PAD_CAN_MM[1], PAD_CAN_T[0], PAD_CAN_T[1],
                                                                                              PAD_FRONT_MM[0], PAD_FRONT_MM[1], PAD_FRONT_T[0], PAD_FRONT_T[1]))
    if not all(isinstance(hd.get(k), (int, float)) for k in ("preload_total_N", "pogo_force_total_N", "max_ledge_lift_mm")):
        return head + "They hold the main PCB down against the six pogo pins of the key board."
    return head + ("They hold the main PCB down against the six pogo pins of the key board: preload %.2f N against %.2f N of pin force, board lift %.4f mm "
                   "(limit %.2f mm; plate model with pad moduli taken from the Shore hardness - cad/housing_interface.json, 'holddown'). A pad that is too "
                   "thin or too soft lets the pins lift the board." % (hd["preload_total_N"], hd["pogo_force_total_N"], hd["max_ledge_lift_mm"],
                                                                     hd.get("lift_limit_mm", 0.02)))


def feature_rows(H):
    """Fine-feature table of the tray and the lid (sheet 'Housing', section 4), v0.6 -> v0.7.

    (id, label, kind, tray, lid, note); kind 'min' = minutes of machining, 'mm' = millimetres of V-groove, which cost
    groove_min_m minutes per metre (the same rate for the v0.6 seams that are removed and the v0.7 grooves that are added)."""
    t_tex, l_tex = texture_lengths(H)
    t_grv, l_grv = groove_lengths(H)
    n_tray, n_lid = panel_counts(H)
    par = H.get("params", {})
    flat, side, diag, full = octagon_facets(H)
    return [
        ("v06", "v0.6 fine-feature time (the result of the v0.6 workbook)", "min", V06_GEOM["feat_tray"], V06_GEOM["feat_lid"],
         "v0.6 workbook, sheet 'Housing', section 4: the v0.5 lump (tray 36 min, lid 8 min) without the knurl and the side grooves, plus the skin seams, "
         "the floor holes, the floor RF window, the lid rabbet and the two hold-down bosses. Unchanged ESTIMATE."),
        ("skin", "minus the v0.6 skin seams (frames and stringers, 0.25 deep)", "mm", -V06_GEOM["skin_tray_mm"], -V06_GEOM["skin_lid_mm"],
         "The v0.6 'fighter-jet' seams are gone: tray 646.5 mm, lid 220.2 mm of V-groove (v0.6 housing_interface.json 'skin_layout')."),
        ("holes", "minus the v0.6 floor holes for the caps and the light tube", "min", -3.0, 0.0,
         "Main bore with counterbore and two slide holes: 3 stepped or chamfered holes, about 1 min each in the v0.6 estimate. Gone in v0.7."),
        ("bezel", "plus the key bezel (stadium recess 0.5 deep, 45 deg walls) and the three key openings with their flange seats", "min", 4.0, 0.0,
         "Bezel X 15.75-35.55, 11.6 wide; openings 7.0 x 7.0 (main key) and 2 x 4.4 x 10.3 (side keys) through the 1.0-1.5 mm floor, flange seats from the inside. "
         "About 1 min per opening and 1 min for the bezel."),
        ("octa", "plus the octagon: the four diagonal facets, the lid's cap pocket (45 deg walls, flat seat) and the two floor rails of the cell bay", "min", 1.5, 1.5,
         "Section %s x %s mm with 45 deg legs of %s mm (facets %.1f / %.1f / %.2f mm); the bulk removal is in 'material to remove'. Tray: the two lower diagonal facets "
         "with a 90 deg chamfer cutter and the two rails 1.2 x 1.1 mm the cell lies on; lid: the two upper diagonal facets, the 45 deg walls of the pocket under them "
         "and the flat seat (FK-H-02: flat 0.05). About 0.5 min per long facet or wall, ESTIMATE."
         % (("%.1f" % par.get("W", 20.0)).rstrip("0").rstrip("."), ("%.1f" % par.get("H", 18.0)).rstrip("0").rstrip("."), par.get("C_edge", 3.4), flat, side, diag)),
        ("kb", "plus the two key-board bosses (blind M1.6) and the four support ribs on the floor", "min", 1.5, 0.0,
         "Bosses d3.4 joined to the trough walls, ribs 1.4 wide at X 18.65 and 32.65; the two blind threads are counted in section 5 (threads)."),
        ("panels", "plus the recessed panels, 0.3 deep, corners R0.8 (%d on the tray, %d on the lid)" % (n_tray, n_lid), "min", 0.5 * n_tray, 0.5 * n_lid,
         "Pocket contours of the panels with a flat end mill, 0.5 min per panel (housing_interface.json 'panel_layout'). The bulk removal is in 'material to remove'."),
        ("texture", "plus the V texture in the panels (90 deg V, 0.2 deep, pitch 0.9, at 45 deg) - a priced option: x 'texture_on' (section 2)", "mm", round(t_tex, 1), round(l_tex, 1),
         "Groove length = panel area / pitch, from 'panel_layout' (the floor RF window opening is a textured POM-C plug, not aluminium). One 90 deg V engraving "
         "cutter; drawing FK-H-01 sheet 2, note 1. The minutes are multiplied by the switch 'texture_on' (1 = cut it, 0 = leave it out: the parts still fit "
         "and work, the panels stay plain)."),
        ("grooves", "plus the transverse V grooves, 0.3 deep: 3 at the head (top, bottom and diagonal facets), 3 at the tail (all round)", "mm", round(t_grv, 1), round(l_grv, 1),
         "Octagon: %.1f mm all round, %.1f mm without the side facets; at the tail the lid takes its top facet and the two upper diagonal facets (%.1f mm), the tray "
         "the rest." % (full, 2 * flat + 4 * diag, flat + 2 * diag)),
    ]


def mould_feature_rows():
    """Fine-feature table of the two plates of the aluminium mould (the durable option; sheet 'Housing', section 4b):
    (id, label, cavity half min, lid min, note). ESTIMATES."""
    return [
        ("cav", "4 cavities: cap and flange pockets with 1 deg draft, chevron groove (0.6 mm end mill), runner, gate and vent groove", 12.0, 0.0,
         "3 min per cavity: the chevron groove needs a 0.6 mm end mill (R0.3, the smallest radius); outlines and depths +/-0.02 (drawing FK-H-08)."),
        ("holes", "dowel holes (reamed in the cavity half, slip fit in the lid), 4 M3 holes, 2 pry slots", 2.0, 1.0,
         "The four M3 threads in the cavity half are counted in section 5 (threads)."),
        ("plateaus", "4 plateaus that form the plate recesses, each with a pour hole and a vent hole", 0.0, 5.0,
         "1.25 min per plateau (0.47 mm high, 3.8 x 9.6 R1.0)."),
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
    """d defaults to V05_DATE: a fee or estimate that v0.7 keeps unchanged carries the date and source it had in v0.5."""
    return dict(v=v, u=u, src=src, d=d, e=e, n=n)


P = {
    # --- global
    "fx": prm(1.1188, "USD per EUR", U_ECB, FX_DATE, n="ECB euro reference rate of 13 Oct 2026 (not refreshed since v0.5). Change it to the rate of your bank/card."),
    "lightsA": prm(1, "lights", "", "", n="Scenario A: you build one light."),
    "lightsB": prm(5, "lights", "", "", n="Scenario B: you build five lights (all JLC minimums are used up). Type 2 to see two lights."),
    "min_asm": prm(2, "panels", U_ASM, n="JLCPCB assembles from 2 boards; one light therefore still pays for 2 assembled panels (1 spare). The 'board' JLCPCB counts is the panel: key board + main PCB."),
    "min_pcb": prm(5, "panels", U_QUOTE, n="JLCPCB sells at least 5 bare boards (here: panels) per design."),
    "sides": prm(2, "sides", "", "", n="Parts are on both faces of both boards = double-sided Standard PCBA (Economic PCBA is single-sided only)."),
    # --- JLCPCB Standard PCBA fees (2026 price page "Last updated on Sep 09, 2026")
    "setup_side": prm(25.56, "USD per side", U_FEES, n="Standard PCBA set-up fee: $25.56 single-sided / $51.12 double-sided. Covers the engineering check (no separate engineering fee). Re-read on " + CHECK + ": unchanged."),
    "stencil_side": prm(8.21, "USD per side", U_FEES, n="Standard PCBA stencil: $8.21 single-sided / $16.42 double-sided. Re-read on " + CHECK + ": unchanged."),
    "smt_joint": prm(0.0016, "USD per joint", U_FEES, n="SMT assembly price per solder joint (1-50,000 joints)."),
    "feeder_unique": prm(1.53, "USD per unique part", U_FEES, n="Feeder loading, Standard PCBA: $1.53 for every unique part number, Basic and Extended alike (no separate engineering fee and no separate extended-part fee). Re-read on " + CHECK + ": unchanged."),
    "ext_extra": prm(0.0, "USD per unique Extended part", U_FEES, n="Only Economic PCBA charges an extra $3.07 per Extended part. In Standard PCBA (this order) every unique part, Basic or Extended, pays the same feeder-loading fee instead, so there is no separate extended-part fee. Type 3.00 here to test the effect of such a fee."),
    "eng_fee": prm(0.0, "USD per order", U_FEES, n="No separate engineering fee on the 2026 page; the set-up fee covers it."),
    "confirm": prm(0.45, "USD per order", U_FEES, n="'Confirm parts placement': JLC sends a photo of the placement for your OK. Strongly recommended for a first order."),
    "asm_panel_fee": prm(8.21, "USD per order", U_FEES, CHECK, n="Panel fee of Standard PCBA when the file holds more than one design (the panel carries the key board and the main PCB). Read on the fee page (last updated Sep 09, 2026)."),
    "xray_per_board": prm(4, "parts per panel", U_FEES, CHECK_1000, n="Fee page: 'X-ray inspection is required for components such as BGA, QFN and other leadless packages', charged per component. The COUNT is an assumption: U4 (ESP32 module, pads under it) and U2 (the buck TPS62095, a QFN without leads, new with the 1000 lm power stage) on the main PCB, LED3 and LED4 (pads under the package) on the key board = 4 per panel. Set 0 if your cart does not ask for it."),
    "panel_board": prm(0.46, "USD per panel", U_PANEL, n="JLC panelises small boards for assembly; the page quotes a minimum processing cost of $0.46 per board. ASSUMED to apply per panel (45.0 x 32.5 mm is below the 70 x 70 mm that JLCPCB names as the smallest Standard-assembly panel)."),
    "pack_base": prm(0.50, "USD per order", U_FEES, n="Packing, Standard PCBA: $0.50 + $0.00003 per cm2 of board."),
    "pack_cm2": prm(0.00003, "USD per cm2", U_FEES, n="See above (negligible for a 15 cm2 panel)."),
    "hand_labour": prm(3.58, "USD per order", U_FEES, n="Hand-soldering labour. Not needed: no through-hole parts. Quantity 0."),
    "prereflow": prm(0.016, "USD per joint", U_FEES, n="Row 'pre-reflow soldering' on the fee page, not explained there. Quantity 0 - check your quote."),
    "single_board": prm(0.48, "USD per order", U_FEES, n="Single-board surcharge; the panel avoids it. Quantity 0."),
    "fixture": prm(8.21, "USD per fixture", U_FEES, n="Test/assembly fixture (minimum 2). Not needed. Quantity 0."),
    "storage": prm(4.93, "USD per item", U_FEES, n="Stencil or fixture storage. Not needed. Quantity 0."),
    "large": prm(57.46, "USD per order", U_FEES, n="Large-size surcharge for boards above 650 cm2. Not applicable (the panel is 45.0 x 32.5 mm). Quantity 0."),
    # --- bare panels (price only shown after the Gerber upload)
    "pcb_fab5": prm(30.0, "USD for 5 panels", U_QUOTE, CHECK, e=True, n="ESTIMATE ($25-35 for 5): bare panels 45.0 x 32.5 mm, 4 layers, 0.8 mm, ENIG, black solder mask, white silkscreen. JLCPCB shows the price only after the Gerber upload (v0.6 estimated $25 for five 24 x 16.5 mm main PCBs). A colour surcharge, if the cart shows one, belongs here."),
    "pcb_fab_low": prm(25.0, "USD for 5 panels", "", CHECK, e=True, n="Low end of the estimate range (information only)."),
    "pcb_fab_high": prm(35.0, "USD for 5 panels", "", CHECK, e=True, n="High end of the estimate range (information only)."),
    "fab_design": prm(15.0, "USD per order", U_EXTRA, CHECK, e=True, n="ESTIMATE ($10-20): JLCPCB charges extra for more than one design in one Gerber file ('different design' fee, order option 'Different Design: 2'); the amount appears only in the calculator after the upload."),
    # --- housing: CNC (JLCCNC) aluminium model
    "al_kg": prm(8.0, "USD per kg", U_JLCNC_COST, e=True, n="ESTIMATE: 6061-T6 plate/bar incl. cutting waste. JLCCNC publishes no price list."),
    "al_dens": prm(2.70, "g per cm3", "", "", n="Density of 6061 aluminium."),
    "allow": prm(2.0, "mm per side", "", "", e=True, n="ESTIMATE: stock block is the part's bounding box plus this on every side."),
    "mrr": prm(6.0, "cm3 per min", "", "", e=True, n="ESTIMATE: material removal rate of a small 3-axis mill in aluminium."),
    "rate_min": prm(0.60, "USD per min", U_JLCNC_COST, e=True, n="ESTIMATE: machine time rate (calibrated in v0.5 so that one tray+lid costs about what the v0.4 estimate gave: $31 + $12)."),
    "setup_fee": prm(3.50, "USD per set-up", "", "", e=True, n="ESTIMATE: one-off cost per workpiece set-up (each re-clamping of the part)."),
    "tap_fee": prm(0.25, "USD per thread", "", "", e=True, n="ESTIMATE: tapping one M1.6 or M3 thread."),
    "groove_min_m": prm(6.0, "min per metre", U_JLCNC_COST, V06_RESEARCH, e=True, n="ESTIMATE (since v0.6): machine time per metre of V-groove (90 deg cutter, short pieces). The SAME rate prices the v0.6 seams that are removed and the v0.7 texture and grooves that are added (section 4)."),
    "texture_on": prm(1, "1 or 0", "", "", n="The panel texture is a priced option: 1 = the shop cuts the 0.2 mm V texture in the recessed panels of the tray and the lid (the order files carry it, the pictures show it), 0 = leave it out and price the tray and lid without it (plain panels; the parts fit and work the same). Section 4 multiplies the texture minutes by this switch; the saving is in the options table of the Summary."),
    "mould_blast": prm(1.00, "USD per part", U_JLCNC_FIN, V05_DATE, e=True, n="ESTIMATE: fine glass-bead blast of the aluminium mould's cavity half (matte key face) = the 'Bead blast only' price of a lid-size part (section 3). The mould lid stays as machined."),
    # --- housing: resin print (JLC3DP) of the casting mould - the default mould since the price check of the 1000 lm design
    "resin_cm3": prm(0.30, "USD per cm3", U_3DP_HOME, CHECK_1000, e=True, n="ESTIMATE from JLC3DP's headline 'SLA from $0.30' (re-read " + CHECK_1000 + "; the v0.6 workbook used the same rate for its resin parts). The instant quote shows the real price per part."),
    "resin_min": prm(0.60, "USD per part", U_3DP, V06_RESEARCH, e=True, n="ESTIMATE (as in v0.6): minimum price of one printed part."),
    # --- housing: PMMA and POM-C machining kits (JLCCNC)
    "pmma_first": prm(7.50, "USD per part type", U_JLCNC_PMMA, CHECK, e=True, n="ESTIMATE: first piece of the polished PMMA main key (research: $6-9 for a small acrylic part with polish; JLCCNC publishes no price for plastic parts, the instant quote shows it after the upload)."),
    "pom_first": prm(6.50, "USD per part type", U_JLCNC_HOWTO, CHECK, e=True, n="ESTIMATE: first piece of one POM-C part type (research: $5-8 per part type, first piece)."),
    "next_frac": prm(0.5, "share of the first piece", "", CHECK, e=True, n="ESTIMATE: every further piece of a part type in the same order costs this share of its first piece (set-up and programming already paid) - the rule the v0.6 workbook used for small CNC parts."),
    # --- hidden costs: EU import
    "vat": prm(0.21, "fraction", U_VAT, n="Lithuania standard VAT 21 %. JLC collects it at checkout for individuals on orders up to EUR 150 (IOSS; " + U_JLC_TAX + ", read " + CHECK_1000 + ")."),
    "ioss_eur": prm(150.0, "EUR", U_VAT, n="IOSS limit: intrinsic value (goods only, without shipping/VAT) up to EUR 150 per consignment."),
    "flat_duty": prm(3.0, "EUR per customs line", U_EC, n="Flat customs duty on low-value consignments, EUR 3 per item category (HS code = one declaration line, whatever the quantity) per parcel, 1 Jul 2026 - 1 Jul 2028 (Council Reg. 2026/382; EU guidance " + U_EC_GUIDE + " and JLC FAQ " + U_CUST + ", read again " + CHECK_1000 + "). Under IOSS JLC collects the VAT but not the EUR 3: you pay it at import unless the shipping channel is DDP."),
    "formal_fee_min": prm(15.0, "EUR per parcel", U_CUST, n="Above EUR 150 the parcel goes through formal customs clearance; the carrier charges a disbursement fee, e.g. DHL Germany 2 % min EUR 15, UPS 3 % min EUR 15.70, FedEx 2.5 % min EUR 15 (JLC FAQ); UPS Lithuania 2 % min EUR 12 (" + U_UPS_LT + ", read " + CHECK_1000 + ")."),
    "formal_fee_pct": prm(0.02, "fraction of VAT+duty", U_CUST, n="See above (DHL Germany example)."),
    "card_pct": prm(0.015, "fraction", "", "", e=True, n="ESTIMATE: card / currency-conversion fee of your bank on the USD payments to JLC (0-3 % depending on the bank). Set your own."),
    "ship_mode": prm(2, "1 or 2", "", "", n="1 = economy shipping, 2 = express (DHL/UPS/FedEx). Default express: fastest, and DDP (taxes paid at checkout) works most reliably."),
    "ali_ship": prm(2.0, "USD per parcel", "", e=True, n="ESTIMATE: AliExpress shipping to Lithuania per seller parcel (many items are free, some cost $1-4)."),
    "ali_parcels": prm(8, "parcels", "", CHECK_CELL, e=True, n="ESTIMATE: separate seller parcels if you buy each item where it is cheapest: LED board, laser, screws, set screw and split rings, wire, tapes + paste + foam + epoxy + silicone pads, mould hardware (M3 screws, washers, nuts), shim + glue + cups + polishes (the first v0.7 layout had 10, with the glass window and the cells; the TIR optics come from a distributor and the cell from an EU battery shop, each its own parcel)."),
    "ali_parcels_consol": prm(3, "parcels", "", "", e=True, n="Parcels if you buy the small hardware (screws, rings, wire, tapes, paste, foam, pads, epoxy, shim, glue) from ONE EU web shop."),
    "risk_pcb_f": prm(1.0, "fraction", "", "", n="Risk reserve = this fraction of the JLCPCB order (landed) as a second PCB order after a first-article problem. Not in the totals."),
    "risk_house_f": prm(1.0, "fraction", "", "", n="Risk reserve = this fraction of the JLCCNC order (landed) as a second housing order. Not in the totals."),
}

NKON_SHIP_EUR = 12.0            # ESTIMATE: nkon.nl courier rate for one small lithium-cell parcel to Lithuania (its shipping page could not be read)
# shipping per parcel (USD): economy A, express A, economy B, express B  - ESTIMATES, the shops show the real price in the cart.
# One row per single parcel (P_JLCPCB, P_CNC, P_EU, P_OPTIC, P_CELL); the AliExpress / web-shop parcels (P_WEB) use 'ali_ship' x 'ali_parcels'.
SHIPPING = [
    ("JLCPCB (panel: both PCBs, assembled)", 6.50, 21.50, 6.50, 21.50,
     "Anchors (Chiptron, 10 Jun 2025): DHL Express $21.50, EuroPacket $6.50, Global Standard Direct Line $1.50 for a small order; EEVblog 2024: FedEx about $16 to Spain. JLC publishes no rate table - the cart shows 'Shipping Estimate'."),
    ("JLCCNC + JLC3DP, one merged order (aluminium, PMMA and POM-C parts, resin mould)", 7.00, 22.00, 9.00, 25.00,
     "ESTIMATE, as in v0.6. JLCCNC merges its orders with JLC3DP ('merged ordering': one package, one shipping rate, select 'All' in the cart; " + U_MERGED + ", read " + CHECK_1000 + "), so the resin mould travels in the JLCCNC parcel. "
     "The price shows on the invoice after you accept the quote. Tray, lid and kits weigh about 40 g per light, the two resin plates about 13 g."),
    ("EU shop: casting supplies (urethane rubber, pigment, release)", 9.00, 18.00, 9.00, 18.00,
     "ESTIMATE, not read: a parcel of about 1-1.5 kg inside the EU (kaupo.de ships from Germany); the shop shows its rate at the checkout."),
    ("Electronics distributor: TIR optics (from a warehouse inside the EU)", 20.00, 20.00, 20.00, 20.00,
     "ESTIMATE, not read: distributors ship by courier and charge about EUR 15-20 below their free-shipping limit (orders for several lights or with other parts may pass it). "
     "The rate is the same in both shipping modes."),
    ("EU battery shop: the 14500 cell and the nickel strip (nkon.nl)", round(NKON_SHIP_EUR * P["fx"]["v"], 2), round(NKON_SHIP_EUR * P["fx"]["v"], 2),
     round(NKON_SHIP_EUR * P["fx"]["v"], 2), round(NKON_SHIP_EUR * P["fx"]["v"], 2),
     "ESTIMATE, not read: nkon.nl (Netherlands) sends lithium cells inside the EU by courier as dangerous goods; its shipping page could not be opened on %s. "
     "About EUR %.0f assumed (converted at %.4f USD/EUR); the shop shows the real rate at the checkout. The rate is the same in both shipping modes." % (CHECK_CELL, NKON_SHIP_EUR, P["fx"]["v"])),
]
P_JLCPCB, P_CNC, P_EU, P_OPTIC, P_CELL, P_WEB = range(6)
PARCELS = [  # name, customs lines, duty rate in the formal route (assumed), note
    ("JLCPCB (panel: both PCBs, assembled)", 2, 0.0, "Bare and assembled PCBs: HS 8534/8543, normally 0 % duty (assumption - check the invoice)."),
    ("JLCCNC + JLC3DP, one merged order (aluminium, PMMA and POM-C parts, resin mould)", 2, 0.06,
     "Aluminium articles HS 7616 99 90 (6 %) and plastic articles HS 3926 90 (PMMA, POM-C, the resin mould, 6.5 %): two customs lines; 6 % is used for the whole parcel (assumption - check the invoice)."),
    ("EU shop: casting supplies (urethane rubber, pigment, release)", 0, 0.0, "Inside the EU: no customs, no duty. 21 % VAT is added on goods and shipping; that is conservative if the shop's price already includes VAT (kaupo.de does not say)."),
    ("Electronics distributor: TIR optics (from a warehouse inside the EU)", 0, 0.0,
     "An EU site of the distributor (the same RS stock number, or Distrelec): no customs, no duty; 21 % VAT on goods and shipping. ASSUMPTION: the RS UK price is used; a UK delivery would go through customs."),
    ("EU battery shop: the 14500 cell and the nickel strip (nkon.nl)", 0, 0.0,
     "Inside the EU: no customs, no duty; 21 % VAT on goods and shipping (nkon.nl shows its prices with and without VAT; the workbook uses the price without VAT, and the "
     "VAT of the Netherlands and of Lithuania is 21 % alike)."),
    ("AliExpress / web shops", 1, 0.0, "Mixed small hardware; each parcel is far below EUR 150, so the flat EUR 3 per line applies."),
]
EU_PARCELS = (P_EU, P_OPTIC, P_CELL)   # parcels from inside the EU (no customs, VAT only)
EU_PARCEL = P_EU                       # the EU casting-shop parcel
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
SHOP_WEB = "AliExpress / web shop"
SHOP_EU = "EU casting shop"
SHOP_OPTIC = "Electronics distributor"
SHOP_CELL = "EU battery shop"
OPTIC_GBP = 13.11                # RS UK, stock no. 186-2699: GBP per pack of 5, excl. VAT (read on CHECK_1000)
ECON_EUR = 28.56                 # kaupo.de, ECON 80/1 0.86 kg (read on CHECK_1000)
SUGRU_EUR = 7.99                 # toom.de, Sugru black 3 x 3.5 g, incl. German VAT (read on CHECK_1000)
F15_EUR = 3.10                   # nkon.nl, Vapcell F15 INR14500 1500 mAh 3 A, excl. VAT (EUR 3.75 incl. VAT; 10 or more: EUR 2.85 excl.), in stock (read on CHECK_CELL)
NICKEL_EUR = 1.86                # nkon.nl, 1 m nickel welding strip 5 x 0.2 mm, nickel >= 99.7 %, excl. VAT (EUR 2.25 incl. VAT), in stock (read on CHECK_CELL)
K10_USD = 4.30                   # illumn.com (USA), Vapcell INR14500 K10 1000 mAh 8 A, flat top, in stock (read on CHECK_CELL) - the alternative, not in the totals
H10_EUR = 3.26                   # nkon.nl, Vapcell INR14500 H10 1000 mAh 10 A (14.3 x 49.4 mm), excl. VAT, OUT OF STOCK (read on CHECK_CELL)

# bought parts: id, item, used for, exact spec, search term, USD per pack, pack size, pack unit, per light, per order,
#               category, price basis, link, price is estimate, shop (parcel), group (light / mould / casting)
BOUGHT = [
    dict(id="cell", item="Li-ion cell Vapcell INR14500 F15, 1500 mAh, 3 A, flat top, no protection board",
         use="Power (BT1). One cell lies in the cell bay on two floor rails (polyimide tape on the rails), + end towards the head, held by a foam strip under the lid "
             "and a foam pad at the tail end. Nickel strips are spot-welded to both ends; one 24 AWG wire goes from each strip to J2. The protection IC U6 and the "
             "MOSFET Q3 on the main PCB protect it (the cell has no protection board of its own).",
         spec="Maker's data: 1500 mAh typical, 1150 mAh minimum (at 0.2C to 2.5 V), 3.60 V nominal, 4.20 V charged, 2.5 V end, 3 A maximum continuous, about 60 mOhm "
              "(AC, 1 kHz), 14.0 +/-0.2 x 49.0 +/-0.3 mm, about 22 g, flat top, no protection circuit; standard charge 500 mA (the light charges at about 494 mA). "
              "The firmware limits the cell current to 2.8 A in turbo (93 %% of the 3 A rating, a documented LuxLibre BAT-1 deviation; no independent test of the F15 at 3 A "
              "was found). The bay takes any FLAT-TOP 14500 up to 14.5 x 50.4 mm (button-top and protected cells are usually longer). Alternative: Vapcell "
              "INR14500 K10 (1000 mAh typical / 900 minimum, 8 A, 14.1 x 50.1 mm, flat top): sags less and keeps full turbo to a lower charge (not simulated), about a third less runtime; USD %.2f at "
              "illumn.com (USA, %s), no EU shop found in stock (nkon.nl lists the similar H10, 1000 mAh 10 A, at EUR %.2f excl. VAT: out of stock on %s). Buy the "
              "cell with welded nickel tabs if the shop offers it; otherwise weld the strips (sheet 'Tools'). Never solder onto the cell; never use a dented cell or one "
              "with a torn sleeve." % (K10_USD, U_K10, H10_EUR, CHECK_CELL),
         search="Vapcell F15 INR14500 1500mAh flat top", price=round(F15_EUR * P["fx"]["v"], 2), pack=1, unit="cell", per_light=1, per_order=1,
         cat="Part", basis="nkon.nl, read %s: EUR %.2f excl. VAT (EUR 3.75 incl. VAT; EUR 2.85 excl. VAT from 10 cells), in stock; converted at %.4f USD/EUR. "
                           "Maker's data: %s. One spare cell per order (a weld can go wrong)." % (CHECK_CELL, F15_EUR, P["fx"]["v"], U_VAPCELL_F15),
         link=U_NKON_F15, est=False, shop=SHOP_CELL),
    dict(id="nickel", item="Nickel strip 0.2 x 5 mm, pure nickel, 1 m",
         use="The cell's two tabs: a piece spot-welded to each end (BAT+ at the front, bent forward into the rebate of the antenna spacer; BAT- at the far end, bent "
             "into the lower -Y corner of the bay); the 24 AWG wires are soldered to the strips, never to the cell. Not needed for a cell bought with welded tabs.",
         spec="Pure nickel (>= 99.7 %, not nickel-plated steel), 0.2 mm thick, 5 mm wide; about 50 mm per light plus pieces to practise the weld. The bay allows 0.4 mm "
              "at each end for the strip with its fold and weld bumps.",
         search="pure nickel strip 0.2x5mm", price=round(NICKEL_EUR * P["fx"]["v"], 2), pack=1, unit="1 m", per_light=0.1, per_order=0,
         cat="Consumable", basis="nkon.nl, read %s: EUR %.2f excl. VAT per metre (EUR 2.25 incl. VAT), in stock; converted at %.4f USD/EUR. Bought with the cell (same parcel)."
                                 % (CHECK_CELL, NICKEL_EUR, P["fx"]["v"]),
         link=U_NKON_NI, est=False, shop=SHOP_CELL),
    dict(id="led", item="Luminus SST-20 Gen 2 LED, 6500 K, on a 10 mm round copper DTP board (ready-made)",
         use="The main white light (D2): lies on the floor of the head bore on a thin film of thermal paste, under the TIR optic; two 24 AWG wires go to the pads J3.",
         spec="Round board 10.0 mm diameter x 1.6 mm (the bore is 10.1 mm), copper core 'DTP' (direct thermal path), emitter SST-20 Gen 2 (data sheet: 3 A maximum, "
              "G1 bin at least 1,156 lm at 3 A and 85 C), 6500 K. Ask for the G1 bin (an F9 LED gives about 6 % less light: 1,088 lm at 3 A). Not the older SST-20 "
              "(Gen 1): it needs more current for the same light. A 16 or 20 mm board does NOT fit.",
         search="SST-20 Gen 2 6500K 10mm DTP copper board", price=2.99, pack=1, unit="board", per_light=1, per_order=1,
         cat="Part", basis="Kaidomain, read " + CHECK_1000 + ": USD 1.99 for the LED + USD 1.00 mounted on a 10 mm copper DTP board = USD 2.99, in stock; the flux bin is not "
                           "stated (the first v0.7 layout: USD 5.40 for an SST-20 on a DTP board from AliExpress).",
         link=U_KAIDOMAIN, est=False),
    dict(id="optic", item="TIR optic LEDiL LISA3-RS-PIN (FP16558), pack of 5",
         use="Focuses the LED into a narrow beam; it is also the light's front window. It stands on the LED board in the head bore and is glued with two-part epoxy on "
             "its holder rim (one per light; the rest are spares).",
         spec="LEDiL FP16558_LISA3-RS-PIN: round, 10.0 mm diameter, 6.9 mm high (6.93 +/-0.2 on the LEDiL drawing), clear PMMA lens in a black polycarbonate holder with "
              "two pins. Cut the two pins off flush: the 10 mm DTP board has no holes and the bore locates the optic. NOT the clip version LISA3-RS-CLIP16 (7.9 mm high: it "
              "would stand out of the head). LEDiL data for the SST-20 Gen 2 (simulated): 20 deg beam, 87 % efficiency, 5.5 cd/lm. No cyanoacrylate near it (white "
              "bloom on the PMMA).",
         search="LEDiL FP16558 LISA3-RS-PIN", price=round(OPTIC_GBP / GBP_PER_EUR * P["fx"]["v"], 2), pack=5, unit="pack of 5", per_light=1, per_order=1,
         cat="Part", basis="RS Components UK, stock no. 186-2699, read " + CHECK_1000 + ": GBP %.2f per pack of 5 excl. VAT (GBP %.3f each), 190 in stock; converted with the "
                           "ECB reference rates of 13 Oct 2026 (%.4f GBP and %.4f USD per EUR, %s). RS also sells it by 100 (186-2399, GBP 1.35 each); Mouser EU "
                           "sells only the clip version FP18198 (EUR 2.82 for 1)." % (OPTIC_GBP, OPTIC_GBP / 5, GBP_PER_EUR, P["fx"]["v"], U_ECB_GBP),
         link=U_RS_OPTIC, est=False, shop=SHOP_OPTIC),
    dict(id="laser", item="Green laser module 520 nm, Class 2 (<= 1 mW), 6 x 12 mm, driver built in",
         use="The laser pointer (LS1). Switched by Q1 and the slide-switch interlock S2; its two wire leads go to the pads J5.",
         spec="Body 6.0 mm diameter x 12 mm long (the tray bore is 6.1 mm), 520 nm green, output power <= 1 mW (Class 2, see the explanation below the table), constant-power (APC) driver inside, "
              "3 V class supply (design note LS1 '3 V'; check that the seller's range includes 3.0-4.2 V), two wire leads. A module thinner than 6 mm needs the optional POM-C laser sleeve (FlashKa_laser_sleeve.step). Ask the seller for a measured output power.",
         search="520nm green laser module 6x12mm 1mW APC", price=23.50, pack=1, unit="module", per_light=1, per_order=0,
         cat="Part", basis="ESTIMATE. AliExpress search result " + V05_DATE + ": US $23.5 for a 6 mm 520 nm 1 mW APC module (item 32869119160).",
         link=ALI_ITEM.format("32869119160"), est=True),
    dict(id="m16", item="Screw M1.6 x 6 mm, countersunk, stainless (lid)",
         use="Four screws hold the lid (two at the front, two at the rear, at Y +/-4.5 mm on the top facet).",
         spec="ISO 7046 / DIN 965 M1.6 x 6, stainless steel, head diameter <= 3.1 mm (countersink 3.3 mm). The screw passes the 3.4 mm of solid lid over the head and the tail "
              "blocks and engages 2.6 mm of thread in the tray (M1.6, tap drill 1.25 mm); lid clearance hole 1.8 mm. Phillips or hex head - match your screwdriver. Buy extra: "
              "they are tiny and get lost.",
         search="M1.6x6 countersunk screw stainless 100pcs", price=2.00, pack=100, unit="100 pcs", per_light=4, per_order=4,
         cat="Part", basis="ESTIMATE. AliExpress search result " + V05_DATE + ": US $1.5 for 100 pcs M1.6 x 3 countersunk (item 32917852857); M1.6 x 6 priced slightly higher.",
         link=ALI_ITEM.format("32917852857"), est=True),
    dict(id="kbscrew", item="Screw M1.6 x 2.5 mm, pan head, stainless (key board)",
         use="Two screws hold the key board on the two tapped bosses of the floor.",
         spec="ISO 7045 / DIN 7985 M1.6 x 2.5, stainless steel, pan head 3.0-3.2 mm diameter x 1.1-1.3 mm (the key board keeps a 3.8 mm circle free). NOT longer than 2.5 mm: the bosses are tapped blind and a 4 mm screw would hit the bottom of the hole "
              "(1.7 mm of thread engagement, 1.649 mm of metal under the drill point).",
         search="M1.6x2.5 pan head screw stainless DIN 7985", price=2.00, pack=100, unit="100 pcs", per_light=2, per_order=4,
         cat="Part", basis="ESTIMATE (research " + CHECK + "): no M1.6 x 2.5 pan-head listing was verified; priced like the M1.6 lid screws (AliExpress anchor US $1.5 per 100, item 32917852857). Industrial sources (SFS, minimum 1,000 pcs; RS) cost about EUR 0.5 per screw.",
         link=ALI_SEARCH.format("M1.6x2.5+pan+head+screw+stainless"), est=True),
    dict(id="setscrew", item="Set screw M1.6 x 5 mm, hex socket, stainless (laser)",
         use="Holds the laser module in its bore. Screwed in from the top of the head block, under the front end of the lid, with the lid off: no hole or screw shows on the closed light.",
         spec="ISO 4026 (flat point) or ISO 4029 (cup point) M1.6 x 5, stainless steel, hex socket for a 0.7 mm hex key. NOT longer than 5 mm: the thread runs 5.836 mm from the head-block top into the laser bore and the screw top stays 0.771 mm below the head-block top, so a longer screw would stop the lid from closing. Tray thread M1.6 (tap drill 1.25 mm).",
         search="M1.6x5 set screw stainless hex socket", price=2.00, pack=50, unit="50 pcs", per_light=1, per_order=4,
         cat="Part", basis="ESTIMATE (typical price of a 50-pack set screw listing; no listing read).", link=ALI_SEARCH.format("M1.6x5+set+screw+stainless"), est=True),
    dict(id="ring", item="Split ring 20-25 mm, stainless",
         use="Key ring through the lanyard slot in the tail (slot 3.6 x 4.6 mm, round a 1.45 mm bridge).",
         spec="Stainless split ring, inner diameter 20-25 mm, wire at most about 1.5 mm thick (its double coil must pass the 3.6 mm slot); a thin cord also fits.",
         search="split key ring 25mm stainless steel", price=2.00, pack=20, unit="20 pcs", per_light=1, per_order=1,
         cat="Part", basis="ESTIMATE (typical price of a 20-pack key ring listing).", link=ALI_SEARCH.format("split+key+ring+25mm+stainless"), est=True),
    dict(id="m3set", item="Socket head screws ISO 4762 M3 x 16 with M3 washers and nuts, stainless (resin casting mould)",
         use="Bolt the two resin plates of the casting mould together (four screws through both plates, a washer under each head and each nut). Once per builder.",
         spec="4 socket head screws ISO 4762 / DIN 912 M3 x 16 (hex socket 2.5 mm), 8 washers ISO 7089 M3, 4 hex nuts ISO 4032 M3, stainless steel. The resin carries no thread: "
              "tighten firmly, not hard.",
         search="M3x16 socket head screw stainless washer nut set", price=4.00, pack=1, unit="set (small packs)", per_light=0, per_order=1,
         cat="Part", basis="ESTIMATE (typical price of small packs: 10 screws, 20 washers, 20 nuts; no listing read).",
         link=ALI_SEARCH.format("M3x16+socket+head+screw+stainless"), est=True, grp="mould"),
    dict(id="wire", item="PTFE wire 24 AWG, red + black, 5 m of each",
         use="The two cell wires (one per J2 pad: BAT+ from the strip at the front end, BAT- from the strip at the far end along the lower -Y corner of the bay) and the "
             "two LED wires (J3 to the LED board). About 0.3 m per light. The laser module's own leads go to J5.",
         spec="24 AWG (0.2 mm2) tinned or silver-plated copper, thin-wall PTFE insulation, outer diameter <= 1.05 mm (the LED wire grooves and holes, the cell-wire "
              "rebate and the corner channel of the bay are sized for it). It carries the 2.8 A of turbo: thinner wire heats up and drops voltage. PTFE does not melt when you solder.",
         search="24AWG PTFE wire red black 5m silver plated", price=7.00, pack=5, unit="5 m", per_light=0.4, per_order=0.6,
         cat="Consumable", basis="ESTIMATE (typical price of a 5 m PTFE wire listing per colour pair; no listing read).", link=ALI_SEARCH.format("24AWG+PTFE+wire+red+black"), est=True),
    dict(id="paste", item="Thermal paste, non-curing silicone grease, small syringe",
         use="A thin film (0.1 mm) between the LED board and the floor of the head bore carries the heat into the aluminium.",
         spec="Thermally conductive, electrically non-conductive, non-curing paste, at least 1 W/mK; a 1-2 g syringe is plenty. No thermal tape or pad: the optic's seat "
              "is set for a 0.1 mm film under the board.",
         search="thermal paste syringe silicone grease", price=2.50, pack=1, unit="syringe", per_light=0, per_order=1,
         cat="Consumable", basis="ESTIMATE (typical price of a small syringe; no listing read).", link=ALI_SEARCH.format("thermal+paste+syringe"), est=True),
    dict(id="kapton", item="Kapton (polyimide) tape 5-10 mm wide, 1 roll",
         use="One layer on each of the two floor rails the cell lies on; it covers the welded strips and the two solder joints so that no bare metal can touch the "
             "aluminium (the cell keeps its own sleeve), and lines the lower -Y corner where the far-end joint lies.",
         spec="Polyimide tape (amber), 5-10 mm wide, about 0.05 mm thick (the bay is drawn with 0.05 mm on the rails), heat resistant.",
         search="kapton tape 10mm polyimide", price=2.50, pack=1, unit="roll", per_light=0, per_order=1,
         cat="Consumable", basis="ESTIMATE (typical price).", link=ALI_SEARCH.format("kapton+tape+10mm"), est=True),
    dict(id="foam", item="Closed-cell foam sheet 0.5 mm (PE or EVA), small sheet",
         use="Holds the cell without rattle: a strip 6 mm wide under the lid presses it onto the rails, a pad at the tail end takes up the length. Both are stacks of "
             "0.5 mm layers, each about 1.6 x the gap it fills: for a nominal F15 a 1.5 mm strip and a 3.0 mm pad (1.0-1.5 and 2.5-3.5 mm over its tolerance).",
         spec="Soft closed-cell foam (PE, EVA or neoprene) 0.5 mm thick, self-adhesive on one side is handy. Measure the cell with its welded strips and pick the stacks "
              "(build guide).",
         search="closed cell foam sheet 0.5mm self adhesive", price=2.50, pack=1, unit="sheet", per_light=0, per_order=1,
         cat="Consumable", basis="ESTIMATE (typical price).", link=ALI_SEARCH.format("closed+cell+foam+sheet+0.5mm"), est=True),
    dict(id="epoxy", item="Two-part epoxy, 5 minute, small syringe",
         use="Glues the TIR optic into the head bore: a thin bead on the holder rim, the optic held pressed onto the LED board while it cures.",
         spec="Two-part epoxy, 5-minute cure (a neutral-cure silicone also works). Use a tiny amount, keep it off the lens. Do NOT use cyanoacrylate (super glue) near the optic or the clear PMMA key: its vapour leaves a white bloom. "
              "The POM-C parts are not glued: the lid insert is held by its flange and the antenna spacer.",
         search="clear epoxy 5 minute syringe AB glue", price=3.50, pack=1, unit="syringe", per_light=0, per_order=1,
         cat="Consumable", basis="ESTIMATE (typical price).", link=ALI_SEARCH.format("clear+epoxy+AB+glue+5+minute"), est=True),
    dict(id="pad_can", item="Silicone thermal gap pad 1.5 mm, Shore 00 70-80, sheet at least 20 x 20 mm",
         use="Hold-down of the main PCB at the module can: a piece 8.8 x 12.4 mm sticks to the can boss under the lid (X 24.85-33.65, Y -7.6 to 4.8) and is compressed to 1.15 mm (23 %) when the lid is closed.",
         spec="Soft silicone gap filler (thermal pad), thickness 1.5 mm, hardness about Shore 00 70-80 (E about 1 MPa); the thermal rating does not matter, the softness does. "
              "Cut with a sharp knife on a cutting mat. One sheet gives many pieces: buy one sheet per order.",
         search="silicone thermal pad 1.5mm 100x100 soft", price=3.50, pack=1, unit="sheet", per_light=0, per_order=1,
         cat="Consumable", basis="ESTIMATE (typical price of a 100 x 100 mm silicone thermal pad listing); no listing was read.", link=ALI_SEARCH.format("silicone+thermal+pad+1.5mm+100x100"), est=True),
    dict(id="pad_front", item="Silicone rubber sheet 1.0 mm, Shore A 70, sheet at least 20 x 20 mm",
         use="Second hold-down at the front of the main PCB: a piece 3.7 x 3.0 mm sticks to the front boss under the lid (X 18.4-22.1, Y 0.25-3.25) and is compressed to 0.75 mm (25 %).",
         spec="Solid silicone rubber sheet, thickness 1.0 mm, hardness Shore A 70 (E about 5 MPa, much firmer than the thermal pad), any colour. Cut with a sharp knife. One sheet per order.",
         search="silicone rubber sheet 1mm shore A 70", price=3.50, pack=1, unit="sheet", per_light=0, per_order=1,
         cat="Consumable", basis="ESTIMATE (typical price of a small silicone rubber sheet listing); no listing was read.", link=ALI_SEARCH.format("silicone+rubber+sheet+1mm+shore+70"), est=True),
    dict(id="siladh", item="Silicone adhesive (small tube, clear or neutral-cure RTV)",
         use="Sticks the two hold-down pads onto their lid bosses (a drop on each boss), so that they stay on the lid when it is opened.",
         spec="Neutral-cure silicone (no acetic acid smell: acetic cure can attack the copper of the PCB). A drop per boss only; keep it off the board.",
         search="neutral cure silicone adhesive small tube 20ml", price=2.50, pack=1, unit="tube", per_light=0, per_order=1,
         cat="Consumable", basis="ESTIMATE (typical price).", link=ALI_SEARCH.format("silicone+adhesive+tube+neutral+cure"), est=True),
    # --- casting supplies of the rubber side keys (urethane, the default)
    dict(id="rubber", item="Castable urethane rubber Shore A 80: Smooth-On ECON 80, 0.86 kg trial unit (A + B)",
         use="The two side keys, cast at home in the resin mould (4 keys per pour). One unit lasts for many pours.",
         spec="Shore 80A (the drawing asks for 75-85), mix 1A:1B by volume (two syringes, no scale needed), pot life about 13 minutes, handling after 6 hours, cured "
              "overnight (24 hours), translucent: coloured black with the pigment (maker's data). Read the technical bulletin and the safety data sheet first. Four keys "
              "need about 0.22 cm3; a pour mixes 5 ml A + 5 ml B.",
         search="Smooth-On ECON 80 urethane rubber", price=round(ECON_EUR * P["fx"]["v"], 2), pack=1, unit="kit (0.86 kg)", per_light=0, per_order=1,
         cat="Consumable", basis="kaupo.de, read " + CHECK_1000 + ": EUR %.2f for ECON 80/1, 0.86 kg (A+B), converted at %.4f USD/EUR (VAT status not stated). Smooth-On's US "
                                 "shop lists the 1.9 lb trial unit at USD 24.93 (%s). About half the price of PMC-780 DRY (EUR 53.99 for 1.36 kg at kaupo.de, %s), "
                                 "which works as well (Shore 80A, 2A:1B by weight)." % (ECON_EUR, P["fx"]["v"], U_SMOOTHON_ECON, U_KAUPO),
         link=U_ECON, est=False, shop=SHOP_EU, grp="casting"),
    dict(id="pigment", item="Black pigment for urethane rubber (Smooth-On SO-Strong black, small bottle)",
         use="Colours the side keys black (ECON 80 cures translucent).",
         spec="Pigment made for urethane rubber, a few drops per pour at the maker's dose (too much can stop the cure); stir it into the mixed rubber.",
         search="SO-Strong black urethane colorant", price=12.00, pack=1, unit="bottle", per_light=0, per_order=1,
         cat="Consumable", basis="ESTIMATE (typical price of a small bottle; no listing read).", link=ALI_SEARCH.format("SO-Strong+black"), est=True, shop=SHOP_EU, grp="casting"),
    dict(id="release", item="Mould release for urethane rubber (Smooth-On Universal Mold Release, spray can)",
         use="Keeps the rubber from sticking to the resin mould: sprayed on every face that touches rubber before each pour.",
         spec="A release made for urethane rubber; let it dry as its label says. Without it the rubber sticks to the resin.",
         search="Universal Mold Release Smooth-On spray", price=18.00, pack=1, unit="can", per_light=0, per_order=1,
         cat="Consumable", basis="ESTIMATE (typical price; no listing read).", link=ALI_SEARCH.format("Universal+Mold+Release"), est=True, shop=SHOP_EU, grp="casting"),
    dict(id="shim", item="Stainless steel shim 0.3 mm (1.4301 / 304), small sheet",
         use="The stiffener of each side key: a plate 3.6 x 9.4 mm (corners clipped 0.8 x 45 deg) and a doubler 2.0 x 2.0 mm, glued into the recess of the cast key.",
         spec="0.3 mm stainless steel shim, flat, for example 100 x 100 mm (one sheet makes dozens of plates). Cut with tin snips, file to the line, deburr, press flat. Outline +0 / -0.2 mm for the plate.",
         search="stainless steel shim 0.3mm sheet 304", price=4.00, pack=1, unit="sheet", per_light=0, per_order=1,
         cat="Consumable", basis="ESTIMATE (typical price of a small shim sheet; no listing read).", link=ALI_SEARCH.format("stainless+steel+shim+0.3mm"), est=True, grp="casting"),
    dict(id="cyano", item="Cyanoacrylate glue, rubber-toughened, small bottle",
         use="Glues the doubler onto the plate and the plate into the recess of each cast key.",
         spec="Rubber-toughened cyanoacrylate (super glue) for rubber and metal; degrease with isopropyl alcohol and roughen first. Keep it away from the PMMA key and the TIR optic (white bloom).",
         search="rubber toughened cyanoacrylate glue", price=5.00, pack=1, unit="bottle", per_light=0, per_order=1,
         cat="Consumable", basis="ESTIMATE (typical price; no listing read).", link=ALI_SEARCH.format("rubber+toughened+cyanoacrylate"), est=True, grp="casting"),
    dict(id="cups", item="Mixing cups, two 5 ml syringes, wooden sticks and nitrile gloves",
         use="Measuring (1:1 by volume), mixing and pouring the urethane rubber.",
         spec="Two 5 ml syringes (one per part), small disposable cups (the cup must hold several times the rubber volume if you degas), wooden sticks or toothpicks, nitrile gloves.",
         search="5ml syringe disposable mixing cups wooden sticks nitrile gloves", price=5.00, pack=1, unit="set", per_light=0, per_order=1,
         cat="Consumable", basis="ESTIMATE (typical price; no listing read).", link=ALI_SEARCH.format("disposable+mixing+cups"), est=True, grp="casting"),
    dict(id="polish", item="Polishes and abrasive paper (plastic polish, metal polish, wet-and-dry 400-3000)",
         use="Plastic polish for the PMMA keys after the tabs are cut (if the shop did not polish them); metal polish for the chevron grooves of the mould (once); 400-grit "
             "paper for the matte key faces of the resin mould (once).",
         spec="A plastic polish for acrylic, a metal polish (paste), wet-and-dry paper 400, 1000, 2000 and 3000 grit. The frosted ring of the main key stays matte.",
         search="acrylic plastic polish kit metal polish", price=10.00, pack=1, unit="set", per_light=0, per_order=1,
         cat="Consumable", basis="ESTIMATE (typical price; no listing read).", link=ALI_SEARCH.format("acrylic+polish+kit"), est=True, grp="casting"),
]
# bought items of the OPTIONS (not in the totals; option_savings() prices them): the hardware of the aluminium mould, Sugru instead of
# the urethane rubber, pigment and release
BOUGHT_OPTIONS = [
    dict(id="dowel", item="Dowel pins ISO 8734, 2 mm m6 x 8 mm, stainless (aluminium mould option)",
         use="Locate the aluminium mould's lid on the cavity half (pressed into the two reamed holes).", spec="Parallel pins ISO 8734, 2 mm, m6, 8 mm, stainless steel.",
         search="dowel pin 2x8mm stainless m6", price=2.50, pack=10, unit="10 pcs", per_light=0, per_order=2,
         cat="Part", basis="ESTIMATE (typical price of a small dowel-pin pack; no listing read).", link=ALI_SEARCH.format("dowel+pin+2x8mm+stainless"), est=True, grp="mould"),
    dict(id="m3x12", item="Socket head screws ISO 4762 M3 x 12, stainless (aluminium mould option)",
         use="Close the aluminium mould (four screws into the M3 threads of the cavity half).", spec="ISO 4762 / DIN 912 M3 x 12, stainless steel, hex socket 2.5 mm.",
         search="M3x12 socket head cap screw stainless", price=2.50, pack=50, unit="50 pcs", per_light=0, per_order=4,
         cat="Part", basis="ESTIMATE (typical price of a 50-pack; no listing read).", link=ALI_SEARCH.format("M3x12+socket+head+screw+stainless"), est=True, grp="mould"),
    dict(id="sugru", item="Sugru mouldable glue, black, 3 x 3.5 g (Sugru option)",
         use="The two side keys pressed into the mould by hand instead of the urethane rubber (one sachet per pour).",
         spec="Shore 70A (softer than the 75-85 of the drawing), working time up to 30 minutes, about 24 hours of cure for the first 3 mm in open air (48 hours in the "
              "closed mould); bonds to the plate as it cures.",
         search="Sugru black 3 pack", price=round(SUGRU_EUR * P["fx"]["v"], 2), pack=1, unit="3 x 3.5 g", per_light=0, per_order=1,
         cat="Consumable", basis="toom.de, read " + CHECK_1000 + ": EUR %.2f incl. German VAT for 3 x 3.5 g black (the workbook adds Lithuanian VAT on top: on the safe side)." % SUGRU_EUR,
         link=U_SUGRU, est=False, shop=SHOP_EU, grp="casting"),
    dict(id="vaseline", item="Petroleum jelly (Vaseline), small tube (Sugru option)",
         use="The mould release of the Sugru keys: a thin film on every face that touches the Sugru, as its maker recommends.", spec="Plain petroleum jelly.",
         search="petroleum jelly small tube", price=2.00, pack=1, unit="tube", per_light=0, per_order=1,
         cat="Consumable", basis="ESTIMATE (typical price).", link=ALI_SEARCH.format("petroleum+jelly"), est=True, shop=SHOP_EU, grp="casting"),
]
for _b in BOUGHT + BOUGHT_OPTIONS:
    _b.setdefault("shop", SHOP_WEB)
    _b.setdefault("grp", "light")

# tools (one-time): item, why, spec, search, USD each, qty, needed (1 = buy it, 0 = optional), first priced (date)
TOOLS = [
    ("Soldering iron with fine tip", "Solder the wires to the pads J2, J3, J5 and the two cell wires to the nickel strips (never to the cell itself), and fix small faults.", "Temperature controlled (about 300-350 C), conical or chisel tip 0.4-1 mm, e.g. Pinecil / TS101 / Hakko FX-888D class.", "pinecil soldering iron", 35.0, 1, 1, V05_DATE),
    ("Solder wire 0.5 mm with flux core", "Hand soldering.", "0.5 mm diameter, Sn63Pb37 or lead-free SAC305, flux core, 50 g reel.", "solder wire 0.5mm rosin core", 8.0, 1, 1, V05_DATE),
    ("Flux (gel syringe or pen)", "Makes the solder flow on the small pads.", "No-clean flux gel in a syringe (e.g. Amtech NC-559 class) or flux pen.", "no clean flux gel syringe", 6.0, 1, 1, V05_DATE),
    ("Fine tweezers", "Hold small parts and wires.", "ESD-safe, pointed tips, stainless; 2-3 shapes.", "ESD tweezers set precision", 5.0, 1, 1, V05_DATE),
    ("Precision screwdriver and hex key set", "Lid screws and key-board screws (M1.6), the M1.6 laser set screw, the M3 screws of the mould (hold the nuts with pliers).", "Phillips PH000/PH00 bits (or the hex bits that match your screws), hex keys 0.7 mm (M1.6 set screw) and 2.5 mm (M3).", "precision screwdriver set hex 0.7mm", 8.0, 1, 1, V05_DATE),
    ("Multimeter", "Check battery voltage, shorts and continuity before the first power-up.", "Any basic digital multimeter with continuity buzzer, DC voltage and current.", "digital multimeter", 15.0, 1, 1, V05_DATE),
    ("Laser safety glasses for 520 nm", "Eye protection whenever the laser is powered on the bench.", "Rated for 520 nm green, OD 4+ (e.g. '190-540 nm OD4+' or 532 nm goggles); CE / EN 207 marked.", "laser safety glasses 520nm 532nm OD4", 14.0, 1, 1, V05_DATE),
    ("Side cutters (flush)", "Trim wires, cut the tabs of the two machining kits, the two pins of the TIR optic and the stubs of the cast keys.", "Small flush cutters.", "flush cutter mini", 5.0, 1, 1, V05_DATE),
    ("Hobby knife and cutting mat", "Cut the two silicone hold-down pads and the foam strip and pad of the cell to size, and trim the cast keys.", "Scalpel or hobby knife with spare blades, small self-healing cutting mat (A5).", "hobby knife cutting mat set", 7.0, 1, 1, V06_CHECK),
    ("Wire stripper (fine)", "Strip the 24 AWG PTFE wire and the laser's leads without cutting the strands.", "For 20-30 AWG wire.", "precision wire stripper 24AWG 28AWG", 7.0, 1, 1, V05_DATE),
    ("Isopropyl alcohol 99 % and swabs", "Clean flux residue, the mould and the glue faces of the side keys and the stiffeners.", "99 % isopropyl alcohol 100-250 ml, lint-free swabs.", "isopropyl alcohol 99 percent", 6.0, 1, 1, V05_DATE),
    ("USB-C data cable", "Charge the light and update the firmware over USB. A charge-only cable will NOT work for data.", "USB-C to USB-A or USB-C, labelled 'data', 0.5-1 m.", "usb c data cable", 4.0, 1, 1, V05_DATE),
    ("Digital caliper", "Measure the laser module (6.0 mm), the cell (14.0 x 49.0 mm; again with its welded strips, to pick the foam stacks), the TIR optic (10.0 x 6.9 mm), the pads and the cast keys.", "Resolution 0.01 mm, range 150 mm.", "digital caliper 150mm", 12.0, 1, 1, V05_DATE),
    ("Desoldering braid", "Remove solder bridges.", "2 mm wide.", "desoldering wick braid", 3.0, 1, 1, V05_DATE),
    ("Digital scale 0.01 g", "Only for PMC-780 DRY, which is mixed 2 parts A to 1 part B by weight. The default ECON 80 is mixed 1:1 by volume with two syringes: no scale needed.", "Pocket scale, 0.01 g resolution, 100-200 g range, with a calibration weight.", "pocket scale 0.01g", 10.0, 1, 0, CHECK),
    ("Small vice with soft jaws", "Flatten the cut shim pieces between two smooth blocks; with the aluminium mould (option) press its two dowel pins into the cavity half.", "Bench vice 50-75 mm with soft (aluminium or plastic) jaw covers.", "small bench vice soft jaws", 15.0, 1, 1, CHECK),
    ("Tin snips (small, straight)", "Cut the stiffener plates and doublers from the 0.3 mm stainless steel shim and the two pieces of 0.2 mm nickel strip.", "Small straight aviation or jeweller's snips for sheet up to 0.5 mm.", "small tin snips straight", 8.0, 1, 1, CHECK),
    ("Needle files", "File the tab stubs of the machining kits flush and the shim pieces to the line.", "Set of fine needle files (flat, half-round).", "needle file set", 6.0, 1, 1, CHECK),
    ("Magnifier or USB microscope", "Inspect the 0402 joints of the assembled boards and the cast chevrons.", "x10-x20 loupe or a USB microscope.", "usb microscope", 15.0, 1, 0, V05_DATE),
    ("Bench power supply with current limit", "Safer first power-up (limit 0.5 A).", "0-5 V, adjustable current limit.", "bench power supply adjustable current limit", 30.0, 1, 0, V05_DATE),
    ("Laser power meter", "Check that the laser module really emits <= 1 mW (Class 2).", "Handheld optical power meter that covers 520 nm and 1 mW.", "laser power meter handheld 520nm", 45.0, 1, 0, V05_DATE),
    ("Hand taps M1.6 (taper and bottoming) with wrench", "Only if JLCCNC cannot cut the M1.6 threads: order plain 1.25 mm holes and tap them yourself. The two key-board bosses are blind (drilled 2.375 mm deep for 1.7 mm of thread): finish them with the bottoming tap.", "M1.6 x 0.35 taper (or plug) tap and M1.6 x 0.35 bottoming tap (1-2 threads of chamfer), tap wrench.", "M1.6 hand tap bottoming", 10.0, 1, 0, V05_DATE),
    ("Vacuum chamber and pump", "Degas the mixed urethane rubber (optional: the casting steps work without it, with more care).", "Small degassing chamber (2-3 l) with a single-stage pump.", "vacuum degassing chamber pump", 60.0, 1, 0, CHECK),
    ("Small spot welder for nickel strip", "Weld the two nickel strips onto the ends of the cell: never solder onto the cell (the heat damages it). Not needed if you buy the "
     "cell with welded tabs or have a battery shop weld the strips: then set 'Needed' to 0.", "Portable spot welder for 0.1-0.2 mm pure nickel strip (its own battery or "
     "capacitors, adjustable pulse). Practise strip on strip first; two or three weld spots per end; wear safety glasses.", "portable spot welder 0.2mm "
     "nickel strip", 40.0, 1, 1, CHECK_CELL),
]


def dims(box):
    """'94.4 x 20 x 16 mm' (one decimal, trailing zeros dropped)."""
    return " x ".join(("%.2f" % x).rstrip("0").rstrip(".") for x in box) + " mm"


def and_list(words):
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


def kit_info(H, key):
    """(size, parts) of a machining kit from 'machining_kits' of housing_interface.json (or the snapshot)."""
    k = (H.get("machining_kits") or HOUSING_SNAPSHOT["machining_kits"]).get(key) or HOUSING_SNAPSHOT["machining_kits"][key]
    return tuple(k["size"]), [p["file"] for p in k["parts"]]


# ----------------------------------------------------------------------------------------------
# housing parts (volumes from housing_interface.json, boxes from tray_bbox / the STL files, mould from key_mould_checks.json)
# ----------------------------------------------------------------------------------------------
def housing_parts(H, stl, mould):
    """Mechanical parts. proc: CNC = JLCCNC aluminium (cost model of sections 2-6; the two plates of the aluminium mould are the
    durable OPTION, opt=True: priced with the same model but NOT in the totals), KIT = JLCCNC plastic machining kit (section 7),
    INKIT = a part inside a kit (information, quantity 0), PRINT = JLC3DP resin print in the merged JLCCNC order (the casting
    mould, section 6b), OPT = optional single part (quantity 0), HOME = made at home (the material is in sheet 'Bought parts')."""
    bb = H["tray_bbox"]
    tray_box = tuple(round(bb[2 * i + 1] - bb[2 * i], 1) for i in range(3))
    vol = H["volumes_mm3"]
    mass = H.get("mass_g", {})

    def box(key):
        return stl[key][:3]

    def v(key):
        return vol[key] if key in vol else stl[key][3]
    mc, ml = mould[MOULD_ALU]["cavity half"], mould[MOULD_ALU]["lid"]
    rc, rl = mould[MOULD_RESIN]["cavity half"], mould[MOULD_RESIN]["lid"]
    rt = (H.get("params", {}).get("resin_t") or [6.0, 5.0])
    pmma_size, _ = kit_info(H, "FlashKa_pmma_kit")
    pom_size, _ = kit_info(H, "FlashKa_pom_kit")
    par = H.get("params", {})
    sk = par.get("side_key") or [4.2, 10.0, 1.5]
    st, db = par.get("stiffener") or [3.6, 9.4, 0.3, 0.8], par.get("doubler") or [2.0, 2.0, 0.3]
    inkit = "In the kit (cut the tabs, file flush). "
    return [
        dict(id="tray", key="FlashKa_tray", label="Tray (main body, %s)" % dims(tray_box), proc="CNC", box=tray_box, vol=v("FlashKa_tray"),
             mass=mass.get("FlashKa_tray", 0), per_light=1, spare=0, factor=1.10, setups=5, taps=7, fin="tray",
             note="Octagon section %s x %s mm (eight facets, 45 deg legs of %s mm). 7 threads (4 x M1.6 lid screws, 2 x M1.6 BLIND in the key-board bosses, 1 x M1.6 for "
                  "the laser set screw from the head-block top, under the lid), the optic bore (d%.1f, flat floor, two LED wire grooves) and the laser bore, the cell bay "
                  "(%.1f mm long, two floor rails), key bezel with three key openings, floor RF window, 8 recessed panels with the V texture, 6 transverse grooves, lanyard "
                  "slot %.1f x %.1f mm. No marking." % (("%.1f" % par.get("W", 20.0)).rstrip("0").rstrip("."), ("%.1f" % par.get("H", 18.0)).rstrip("0").rstrip("."),
                                                       par.get("C_edge", 3.4), par.get("opt_bore", 10.1), par.get("L_batt", 51.6), par.get("lan_slot_w", 3.6),
                                                       par.get("lan_slot_len", 4.6))),
        dict(id="lid", key="FlashKa_lid", label="Lid (%s)" % dims(box("FlashKa_lid")), proc="CNC", box=box("FlashKa_lid"), vol=v("FlashKa_lid"),
             mass=mass.get("FlashKa_lid", 0), per_light=1, spare=0, factor=1.30, setups=3, taps=0, fin="lid",
             note="A cap 3.4 mm tall (the top facet and the two upper diagonal facets) that closes on a flat seat on the tray walls: pocketed from below over the cavity "
                  "(1.5 mm plate, 45 deg walls), solid over the head and the tail blocks; two hold-down bosses (%.2f mm tall overall), 4 countersunk holes for the M1.6 x 6 "
                  "screws, RF-window opening and pocket, 3 recessed panels with the V texture, 3 tail grooves. A thin-walled part is harder to clamp, hence the factor 1.30." % LID_HEIGHT_MM),
        dict(id="pmma", key="FlashKa_pmma_kit", label="PMMA kit: 3 main keys on tabs in a frame (%s)" % dims(pmma_size), proc="KIT", box=pmma_size,
             vol=None, mass=None, per_kit=PMMA_PER_KIT, need_light=1, need_spare=1, types=1, pieces=PMMA_PER_KIT, first="pmma_first",
             note="Clear cast PMMA (acrylic, not extruded), polished as drawing FK-H-03 asks (vapour or flame polish; the frosted ring stays matte). "
                  "Kits = ROUNDUP((lights + 1 spare key) / 3): one kit for 1 or 2 lights, two kits for 5 lights."),
        dict(id="keymain", key="FlashKa_key_main", label="   main key, clear PMMA - in the PMMA kit (3 per kit)", proc="INKIT", box=box("FlashKa_key_main"),
             vol=v("FlashKa_key_main"), mass=mass.get("FlashKa_key_main", 0), count=3,
             note=inkit + "6.8 x 6.8 R1.0, 2.75 tall, flange 7.6 x 7.6 x 0.45; the light guide of the RGB ring (frosted ring d4.4 x 0.5 on the outer face)."),
        dict(id="pom", key="FlashKa_pom_kit", label="POM-C kit: lid RF insert x2 and the antenna spacer (%s)" % dims(pom_size), proc="KIT", box=pom_size,
             vol=None, mass=None, per_kit=1, need_light=1, need_spare=0, types=2, pieces=3, first="pom_first",
             note="Black POM-C (acetal copolymer). One kit per light: the two POM-C parts of a light plus a spare lid insert (the first v0.7 layout also carried an LED "
                  "spacer ring: gone with the glass window). The textured faces carry the same V texture as the aluminium panels."),
        dict(id="rfw", key="FlashKa_rf_window", label="   lid RF window insert - in the POM-C kit (2 per kit)", proc="INKIT", box=box("FlashKa_rf_window"),
             vol=v("FlashKa_rf_window"), mass=mass.get("FlashKa_rf_window", 0), count=2,
             note=inkit + "Lets the Bluetooth signal out through the lid; held by its flange and the antenna spacer (POM-C does not bond well: no glue)."),
        dict(id="ant", key="FlashKa_antenna_spacer", label="   antenna spacer with the floor plug - in the POM-C kit", proc="INKIT", box=box("FlashKa_antenna_spacer"),
             vol=v("FlashKa_antenna_spacer"), mass=mass.get("FlashKa_antenna_spacer", 0), count=1,
             note=inkit + "Keeps the cell away from the ESP32 antenna; its textured plug closes the floor RF window; the front nickel strip (BAT+) is soldered to its "
                  "wire in the spacer's rebate, and both cell wires run there."),
        dict(id="rcav", key="FlashKa_key_mould_resin_cavity", label="Casting mould (default), resin cavity half (%s)" % dims(rc["bbox_mm"]), proc="PRINT",
             box=tuple(rc["bbox_mm"]), vol=rc["volume_mm3"], mass=None, per_light=0, spare=1,
             note="SLA resin print from JLC3DP, in the merged JLCCNC order, ONCE PER BUILDER (not per light). Plate 48 x 28 x %.1f mm with a ribbed back, four cavities key "
                  "face down (the chevron is a groove in the cavity floor), two printed pins d4.0 (the box includes them). Print with the parting face up, supports on the "
                  "back only (drawing FK-H-08)." % rt[0]),
        dict(id="rlid", key="FlashKa_key_mould_resin_lid", label="Casting mould (default), resin lid (%s)" % dims(rl["bbox_mm"]), proc="PRINT",
             box=tuple(rl["bbox_mm"]), vol=rl["volume_mm3"], mass=None, per_light=0, spare=1,
             note="SLA resin print from JLC3DP, once per builder. Plate 48 x 28 x %.1f mm with a ribbed back; four plateaus form the plate recesses; pour and vent holes, two "
                  "sockets d4.2 for the pins, four holes for the M3 x 16 bolts (no threads in the resin)." % rt[1]),
        dict(id="mcav", key="FlashKa_key_mould_cavity", label="Casting mould OPTION, aluminium cavity half (%s) - not in the totals" % dims(mc["bbox_mm"]), proc="CNC",
             box=tuple(mc["bbox_mm"]), opt=True,
             vol=mc["volume_mm3"], mass=mc.get("mass_g", 0), per_light=0, spare=1, factor=1.30, setups=2, taps=4, fin="blast",
             note="The durable option instead of the resin mould: aluminium 6061-T6 from JLCCNC, once per builder. Four cavities, key face down; the chevron groove needs a 0.6 mm "
                  "end mill; 2 reamed dowel holes, 4 x M3; fine glass-bead blast (matte key face), no anodising (drawing FK-H-08). Holds +/-0.02 mm and lasts for many pours."),
        dict(id="mlid", key="FlashKa_key_mould_lid", label="Casting mould OPTION, aluminium lid (%s) - not in the totals" % dims(ml["bbox_mm"]), proc="CNC",
             box=tuple(ml["bbox_mm"]), opt=True,
             vol=ml["volume_mm3"], mass=ml.get("mass_g", 0), per_light=0, spare=1, factor=1.30, setups=2, taps=0, fin="none",
             note="Aluminium 6061-T6, once per builder (option). Four plateaus form the plate recesses; pour and vent holes, dowel and screw holes; as machined."),
        dict(id="sleeve", key="FlashKa_laser_sleeve", label="Laser sleeve (optional, single POM-C part, not in a kit)", proc="OPT", box=box("FlashKa_laser_sleeve"),
             vol=v("FlashKa_laser_sleeve"), mass=mass.get("FlashKa_laser_sleeve", 0),
             note="ONLY for a laser module thinner than 6 mm. Too small for the JLCCNC instant quote and not in a kit (its slit needs a side setup): order it from a shop that "
                  "takes small parts (%s). Not in the totals." % ofp("FlashKa_laser_sleeve.step")),
        dict(id="keyside", key="FlashKa_key_side", label="Side key, cast urethane rubber Shore A 80 (made at home)", proc="HOME", box=box("FlashKa_key_side"),
             vol=v("FlashKa_key_side"), mass=mass.get("FlashKa_key_side", 0), per_light=2,
             note="%.1f x %.1f R%.1f, the same part for next and previous (turned 180 deg; the chevron points along the body); cast in the mould, 4 per pour (2 + 2 spares). "
                  "Material in sheet 'Bought parts' (urethane rubber, pigment, release)." % (sk[0], sk[1], sk[2])),
        dict(id="stiff", key="FlashKa_key_stiffener", label="Stiffener: plate + doubler, 0.3 mm stainless shim (made at home)", proc="HOME", box=box("FlashKa_key_stiffener"),
             vol=v("FlashKa_key_stiffener"), mass=mass.get("FlashKa_key_stiffener", 0), per_light=2,
             note="Plate %.1f x %.1f (corners clipped %.1f x 45 deg) + doubler %.1f x %.1f, cut with tin snips and glued into each side key with cyanoacrylate. Shim and glue in "
                  "sheet 'Bought parts'." % (st[0], st[1], st[3], db[0], db[1])),
    ]

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


def kit_count(lights, p):
    """Machining kits to order: ROUNDUP((lights x units per light + spare units) / units per kit)."""
    return ceil_div(lights * p["need_light"] + p["need_spare"], p["per_kit"])


def kit_cost(first, frac, n, p):
    """Price of n kits: every part type pays its first piece once, every further piece the share 'frac' of it."""
    if n <= 0:
        return 0.0
    return first * (p["types"] + (p["pieces"] * n - p["types"]) * frac)


def fin_cost(p, fin, v):
    """Finish of one aluminium part: tray / lid from the chosen finish, the mould's cavity half bead blasted, its lid as machined."""
    return {"tray": fin[1], "lid": fin[2], "blast": v["mould_blast"], "none": 0.0}[p["fin"]]


# ----------------------------------------------------------------------------------------------
# independent Python model: every number the workbook computes with formulas is computed here again
# ----------------------------------------------------------------------------------------------
def resin_unit(v, vol_mm3):
    """Price of one JLC3DP resin print: MAX(minimum per part, rate per cm3 x model volume)."""
    return max(v["resin_min"], v["resin_cm3"] * vol_mm3 / 1000.0)


def model(P, lines, H, hparts, finish_name, bought, tools, mould_kind="resin"):
    """Every number the workbook computes, computed again in Python. mould_kind = 'resin' (the default: the workbook's totals) or
    'alu' (the aluminium mould option: used only by option_savings(); the workbook keeps the resin mould in its totals)."""
    v = {k: x["v"] for k, x in P.items()}
    cp = {}
    EXTRA = {c: n for c, n, _ in ATTRITION}
    cp["pcb_w"], cp["pcb_h"] = PANEL_MM
    area_cm2 = PANEL_MM[0] * PANEL_MM[1] / 100.0
    cp["pcb_area_cm2"] = area_cm2
    joints = sum(l["qty"] * l["pads"] for l in lines)
    cp["placements"] = sum(l["qty"] for l in lines)
    cp["joints"] = joints
    cp["n_lines"] = len(lines)
    cp["n_ext"] = sum(1 for l in lines if l["type"] == "Extended")
    cp["n_basic"] = sum(1 for l in lines if l["type"] == "Basic")
    fx = v["fx"]
    cp["fx"] = fx
    for sc in "AB":
        lights = v["lights" + sc]
        boards = max(lights, v["min_asm"])
        pcbs = math.ceil(max(v["min_pcb"], boards) / 5.0) * 5
        cp["boards_" + sc] = boards
        cp["pcbs_" + sc] = pcbs
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
            "asmpanel": v["asm_panel_fee"] * 1,
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
        fabd = v["fab_design"] * 1
        goods = fab + fabd + fee_total + comps
        cp["fab_" + sc] = fab
        cp["fabd_" + sc] = fabd
        cp["fees_" + sc] = fee_total
        cp["jlc_goods_" + sc] = goods
        cp["jlc_goods_eur_" + sc] = goods / fx
        cp["jlc_line_gap_" + sc] = v["ioss_eur"] - goods / fx

    # --- housing: aluminium parts (tray, lid; the aluminium mould plates of the option)
    fin = next(f for f in FINISHES if f[0] == finish_name)
    feat = {"tray": 0.0, "lid": 0.0}
    tex = {"tray": 0.0, "lid": 0.0}
    for _id, _lab, kind, t_, l_, _note in feature_rows(H):
        k = v["groove_min_m"] / 1000.0 if kind == "mm" else 1.0
        if _id == "texture":
            k *= v["texture_on"]
            tex["tray"], tex["lid"] = t_ * k, l_ * k
            cp["tex_min_tray"], cp["tex_min_lid"] = tex["tray"], tex["lid"]
        feat["tray"] += t_ * k
        feat["lid"] += l_ * k
    feat["mcav"] = sum(r[2] for r in mould_feature_rows())
    feat["mlid"] = sum(r[3] for r in mould_feature_rows())
    for k in ("tray", "lid", "mcav", "mlid"):
        cp["feat_" + k] = feat[k]
    cnc = [p for p in hparts if p["proc"] == "CNC"]
    pmap = {p["id"]: p for p in cnc}
    var, setc = {}, {}
    for p in cnc:
        x, y, z = p["box"]
        a = v["allow"]
        stock = (x + 2 * a) * (y + 2 * a) * (z + 2 * a) / 1000.0
        removed = stock - p["vol"] / 1000.0
        mat = stock * v["al_dens"] / 1000.0 * v["al_kg"]
        minutes = removed / v["mrr"] + feat[p["id"]]
        mach = minutes * v["rate_min"] * p["factor"]
        taps = p["taps"] * v["tap_fee"]
        fc = fin_cost(p, fin, v)
        var[p["id"]] = mat + mach + taps + fc
        setc[p["id"]] = p["setups"] * v["setup_fee"]
        for nm, val in (("stock", stock), ("removed", removed), ("mat", mat), ("min", minutes), ("mach", mach), ("fin", fc),
                        ("var", var[p["id"]]), ("setup", setc[p["id"]])):
            cp["cnc_%s_%s" % (nm, p["id"])] = val
    # --- housing: the resin mould (JLC3DP, the default) - once per builder
    prints = [p for p in hparts if p["proc"] == "PRINT"]
    resin = 0.0
    for p in prints:
        u = resin_unit(v, p["vol"])
        cp["resin_unit_" + p["id"]] = u
        resin += p["spare"] * u
    kits = [p for p in hparts if p["proc"] == "KIT"]
    for sc in "AB":
        lights = v["lights" + sc]
        alu = sum((lights * p["per_light"] + p["spare"]) * var[p["id"]] for p in cnc if p["id"] in ("tray", "lid")) \
            + setc["tray"] + setc["lid"] + fin[3]
        mould_alu = sum((lights * p["per_light"] + p["spare"]) * var[p["id"]] for p in cnc if p["id"] in ("mcav", "mlid")) \
            + setc["mcav"] + setc["mlid"]
        kit = 0.0
        for p in kits:
            n = kit_count(lights, p)
            c = kit_cost(v[p["first"]], v["next_frac"], n, p)
            cp["kit_qty_%s_%s" % (p["id"], sc)] = n
            cp["kit_cost_%s_%s" % (p["id"], sc)] = c
            kit += c
        mould = resin if mould_kind == "resin" else mould_alu
        cp["alu_est_" + sc] = alu
        cp["alu_" + sc] = alu
        cp["mould_alu_est_" + sc] = mould_alu
        cp["mould_est_" + sc] = resin
        cp["mould_" + sc] = mould
        cp["kit_est_" + sc] = kit
        cp["kit_" + sc] = kit
        cp["cnc_" + sc] = alu + mould + kit
        cp["housing_" + sc] = alu + mould + kit
        cp["cnc_line_gap_" + sc] = v["ioss_eur"] - (alu + mould + kit) / fx
        # the panel texture inside the tray + lid cost (0 when 'texture_on' is 0)
        cp["tex_cost_" + sc] = sum((lights * pmap[i]["per_light"] + pmap[i]["spare"]) * tex[i] * v["rate_min"] * pmap[i]["factor"] for i in ("tray", "lid"))

    # --- bought parts
    for sc in "AB":
        lights = v["lights" + sc]
        tot = {"Part": 0.0, "Consumable": 0.0}
        spare_val = eu = optic = cellshop = cast = 0.0
        for b in bought:
            need = lights * b["per_light"] + b["per_order"]
            packs = ceil_div(need, b["pack"])
            cost = packs * b["price"]
            cp["bp_packs_%s_%s" % (b["id"], sc)] = packs
            cp["bp_cost_%s_%s" % (b["id"], sc)] = cost
            tot[b["cat"]] += cost
            spare_val += cost - lights * b["per_light"] / b["pack"] * b["price"]
            if b["shop"] == SHOP_EU:
                eu += cost
            if b["shop"] == SHOP_OPTIC:
                optic += cost
            if b["shop"] == SHOP_CELL:
                cellshop += cost
            if b["grp"] == "casting":
                cast += cost
        cp["parts_" + sc] = tot["Part"]
        cp["cons_" + sc] = tot["Consumable"]
        cp["bp_spare_" + sc] = spare_val
        cp["bp_eu_" + sc] = eu
        cp["bp_optic_" + sc] = optic
        cp["bp_cell_" + sc] = cellshop
        cp["bp_cast_" + sc] = cast

    # --- hidden costs: landed cost per parcel
    mode = v["ship_mode"]
    tot = {}
    for sc in "AB":
        goods_by = {P_JLCPCB: cp["jlc_goods_" + sc], P_CNC: cp["cnc_" + sc], P_EU: cp["bp_eu_" + sc], P_OPTIC: cp["bp_optic_" + sc],
                    P_CELL: cp["bp_cell_" + sc],
                    P_WEB: cp["parts_" + sc] + cp["cons_" + sc] - cp["bp_eu_" + sc] - cp["bp_optic_" + sc] - cp["bp_cell_" + sc]}
        sums = dict(goods=0.0, ship=0.0, duty=0.0, vat=0.0, fee=0.0, landed=0.0)
        jlc_landed = 0.0
        for i, (nm, lines_, rate, _) in enumerate(PARCELS):
            g = goods_by[i]
            n = v["ali_parcels"] if i == P_WEB else 1
            if i != P_WEB:
                sh = SHIPPING[i]
                ship = (sh[1] if mode == 1 else sh[2]) if sc == "A" else (sh[3] if mode == 1 else sh[4])
            else:
                ship = v["ali_ship"] * n
            per_eur = g / n / fx
            if i in EU_PARCELS:
                formal, duty, fee = False, 0.0, 0.0
                vat = v["vat"] * (g + ship)
            else:
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
            if i in (P_JLCPCB, P_CNC):
                jlc_landed += landed
        card = v["card_pct"] * jlc_landed
        for k2, x in sums.items():
            cp["hc_sum_%s_%s" % (k2, sc)] = x
        cp["card_" + sc] = card
        tot[sc] = sums
        cp["tax_other_" + sc] = sums["ship"] + sums["duty"] + sums["vat"] + sums["fee"] + card
    # the EUR 150 cliff for the JLCPCB parcel of scenario A: landed cost on the IOSS route vs the formal route
    g0, s0 = cp["hc_goods_A_%d" % P_JLCPCB], cp["hc_ship_A_%d" % P_JLCPCB]
    cp["route_ioss_A"] = g0 + s0 + PARCELS[P_JLCPCB][1] * v["flat_duty"] * fx + v["vat"] * (g0 + s0)
    d0 = PARCELS[P_JLCPCB][2] * (g0 + s0)
    v0 = v["vat"] * (g0 + s0 + d0)
    cp["route_formal_A"] = g0 + s0 + d0 + v0 + max(v["formal_fee_min"] * fx, v["formal_fee_pct"] * (d0 + v0))
    cp["route_diff_A"] = cp["route_formal_A"] - cp["route_ioss_A"]
    # consolidation saving (AliExpress parcels): each avoided parcel saves shipping + flat duty
    cp["consol_saving_A"] = (v["ali_parcels"] - v["ali_parcels_consol"]) * (v["ali_ship"] + PARCELS[P_WEB][1] * v["flat_duty"] * fx)

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
        cp["sum_fab_" + sc] = cp["fab_" + sc] + cp["fabd_" + sc]
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
    cp["risk_pcb"] = v["risk_pcb_f"] * cp["hc_landed_A_%d" % P_JLCPCB]
    cp["risk_house"] = v["risk_house_f"] * cp["hc_landed_A_%d" % P_CNC]
    cp["grand_A"] = cp["sum_total_A"] + cp["tools_total"]
    cp["grand_B"] = cp["sum_total_B"] + cp["tools_total"]
    # --- change from v0.6 (typed-in v0.6 totals, V06_SUMMARY), from the first v0.7 layout (V07R_SUMMARY) and from the two-pouch-cell
    #     layout just before the one-cell octagon (V07P_SUMMARY)
    for sc in "AB":
        o = V06_SUMMARY[sc]
        r = v07r(v["lights" + sc])
        q = v07p(v["lights" + sc])
        for key, mk in (("pcb", "sum_pcb_"), ("house", "sum_housing_"), ("parts", "sum_parts_"), ("cons", "sum_cons_"),
                        ("tax", "sum_other_"), ("total", "sum_total_"), ("per", "sum_per_")):
            cp["d_%s_%s" % (key, sc)] = cp[mk + sc] - o[key]
            cp["d07_%s_%s" % (key, sc)] = cp[mk + sc] - r[key]
            cp["dcell_%s_%s" % (key, sc)] = cp[mk + sc] - q[key]
    return cp


# the options of the Summary: what each one saves against the defaults (positive = cheaper), computed by running the model with the
# option switched on. (id, label, quality cost / what to do)
OPTIONS = [
    ("tex", "Leave out the panel texture (type 0 in 'texture_on', sheet 'Housing')",
     "Plain recessed panels instead of the V texture: the light looks different from the pictures, nothing else changes. The STEP files carry the texture: ask the shop "
     "to skip feature 17 of drawing FK-H-01 (or have texture-free STEP files made) - otherwise the quote still includes it."),
    ("eco", "Economy shipping instead of express (type 1 in 'ship_mode', sheet 'Hidden costs')",
     "Two to five weeks instead of about one; tracking and the customs handling are less predictable, and the EUR 3 per line may be asked at your door."),
    ("pogo", "Cheaper pogo pins: Xinyangze YZ00615050R-08 (LCSC C7429459) instead of the Harwin P70-1010045R",
     "LCSC does not state the plating or whether it has a locating peg (the key board has no hole for one); rated 1 A (plenty for these signals); 720 in stock. Not "
     "verified, so not the default: to use it, change the LCSC number in tools/kicad/flashka_parts.py and the panel BOM, and check the footprint first."),
    ("sugru", "Sugru instead of ECON 80 for the side keys (no pigment, no urethane release: petroleum jelly)",
     "Shore 70A, softer than the 75-85 of the drawing: the keys feel softer. 48 h cure in the closed mould; the stiffener is bedded in fresh Sugru because "
     "cyanoacrylate does not hold on cured Sugru."),
    ("alu", "Aluminium casting mould (JLCCNC) instead of the resin mould (a negative saving: it costs more)",
     "Better, not worse: +/-0.02 mm instead of the print's tolerance, lasts for many pours, bead-blasted matte key faces without sanding. Needs 2 dowel pins and 4 M3 x 12 "
     "screws instead of the M3 x 16 bolts, washers and nuts."),
]
POGO_CHEAP_TIERS = [(5, 0.319), (50, 0.25)]      # C7429459 at LCSC, read on CHECK_1000


def option_savings(lines, H, hparts):
    """{'opt_<id>_A': USD, 'opt_<id>_B': USD}: total of the defaults minus the total with the option (positive = the option is cheaper)."""
    base = model(P, lines, H, hparts, FINISH_DEFAULT, BOUGHT, TOOLS)
    runs = {}
    p = json.loads(json.dumps(P))
    p["texture_on"]["v"] = 0
    runs["tex"] = model(p, lines, H, hparts, FINISH_DEFAULT, BOUGHT, TOOLS)
    p = json.loads(json.dumps(P))
    p["ship_mode"]["v"] = 1
    runs["eco"] = model(p, lines, H, hparts, FINISH_DEFAULT, BOUGHT, TOOLS)
    lines2 = [dict(l, tiers=POGO_CHEAP_TIERS) if l["lcsc"] == "C22100007" else l for l in lines]
    runs["pogo"] = model(P, lines2, H, hparts, FINISH_DEFAULT, BOUGHT, TOOLS)
    opt = {b["id"]: b for b in BOUGHT_OPTIONS}
    sugru = [b for b in BOUGHT if b["id"] not in ("rubber", "pigment", "release")] + [opt["sugru"], opt["vaseline"]]
    runs["sugru"] = model(P, lines, H, hparts, FINISH_DEFAULT, sugru, TOOLS)
    alu = [b for b in BOUGHT if b["id"] != "m3set"] + [opt["dowel"], opt["m3x12"]]
    runs["alu"] = model(P, lines, H, hparts, FINISH_DEFAULT, alu, TOOLS, mould_kind="alu")
    out = {}
    for oid, _lab, _q in OPTIONS:
        for sc in "AB":
            out["opt_%s_%s" % (oid, sc)] = base["sum_total_" + sc] - runs[oid]["sum_total_" + sc]
    return out


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
# sheet: Panel BOM
# ----------------------------------------------------------------------------------------------
BOM_SHEET = "Panel BOM"
BOM_HDR = 8
BOM_R0 = 9


def build_bom(book, lines):
    S = BOM_SHEET
    widths = [5, 24, 14, 30, 11, 21, 20, 40, 46, 8, 8, 10, 10, 11, 46, 8, 7, 9, 11, 11, 9, 11, 11] + [8] * 6 + [9] * 6 + [46]
    s = Sh(book, S, widths)
    ws = s.ws
    n = len(lines)
    r1 = BOM_R0 + n - 1
    s.put(1, 1, "Panel bill of materials - what JLCPCB assembles on the two boards (main PCB + key board)", "title")
    s.merge(2, 1, 9, ("One line per component type (grouped by LCSC number), derived from tools/kicad/flashka_parts.py with the same grouping and "
                      "ordering as tools/kicad/build_all.py, which writes the BOM you upload as %s: %d lines, %d placements, %d solder joints per panel. "
                      "Wire pads (J2 cell, J3 LED, J5 laser), the pogo target pads J6 and the key board's screw holes H1, H2 have no LCSC number: they are NOT assembled. "
                      "The LED board, the TIR optic, the 14500 cell and the laser are bought parts (sheet 'Bought parts'). New in v0.7: the six pogo pins P1-P6 (Harwin "
                      "P70-1010045R); SW1-SW3, LED3, LED4 and eight resistors moved from the main PCB to the key board, which JLCPCB makes in the same panel; the 1000 lm power "
                      "stage added the 4 A buck TPS62095 (U2), the cell protection DW01A (U6) with the dual MOSFET SE8830A (Q3) and five small parts; for the 14500 cell R3 "
                      "is 2.0 k (C4109) instead of 3.3 k, so the charger gives about 494 mA instead of 280 mA.")
            % (ofp("BOM_JLCPCB.csv"), n, sum(l["qty"] for l in lines), sum(l["qty"] * l["pads"] for l in lines)))
    s.merge(3, 1, 9, "Unit price = the LCSC price tier that matches the quantity JLCPCB has to buy = (quantity per panel x panels assembled) + extra pieces for "
            "placement loss (columns P-Q). Prices were read from the LCSC product pages on %s (v0.5 price check; the lines that did not change keep that date), for the "
            "pogo pin C22100007 on %s, for the buck C139643 and the protection IC C351410 on %s and for R3 (C4109) on %s (columns X-AI hold the tier tables, typed in "
            "from the page). The three lines whose pages could not be read (C115357 and C25104 on %s, C238645 on %s) are blue on amber = ESTIMATE: tiers from the parts "
            "named in the 'Price source' column. JLC buys from LCSC/its own warehouse; the real component price shows in the JLC cart after the BOM upload."
            % (V05_DATE, CHECK, CHECK_1000, CHECK_CELL, V06_CHECK, CHECK_1000))
    s.merge(4, 1, 9, "Basic / Extended = JLCPCB library type read on jlcpcb.com/partdetail/<LCSC number> on %s (assumed, amber, for four lines: Extended for C115357, "
            "C22100007 and C238645, Basic for C25104 - check them in the JLC BOM upload). In 2026 Standard PCBA every unique part costs the same feeder fee, "
            "Basic or Extended (see sheet 'JLCPCB order'); the 'Preferred' tag (only relevant for the single-sided Economic PCBA) was not shown on any of these pages. "
            "'LCSC stock' is LCSC's retail stock, NOT JLC's warehouse; JLC flags real shortages when you upload the BOM." % V05_DATE)
    s.put(5, 2, "Panels assembled, scenario A", "bold")
    s.put(5, 3, "='JLCPCB order'!%s" % "$E$1", "x", fmt="0", name="bom_boards_A")      # placeholder, replaced below
    s.put(6, 2, "Panels assembled, scenario B", "bold")
    s.put(6, 3, "='JLCPCB order'!%s" % "$G$1", "x", fmt="0", name="bom_boards_B")
    ws.cell(row=5, column=3).value = "=" + book.ref("boards_A", S)
    ws.cell(row=6, column=3).value = "=" + book.ref("boards_B", S)
    hd = ["#", "Designators", "Value", "Footprint", "LCSC #", "Manufacturer part no.", "Manufacturer", "Description (flashka_parts.py)",
          "What it does (and on which board)", "Qty / panel", "Solder joints / part", "JLC part type", "JLC part page", "LCSC stock (retail)",
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
    s.put(t, 2, "TOTAL per panel / per order", "tot")
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
    s.merge(w - 1, 2, 9, "Parts without an LCSC number - NOT assembled by JLCPCB (wire pads, pogo target pads, screw holes)", "sub", border=True)
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
    s.put(1, 1, "JLCPCB order - one panel (key board + main PCB), bare panels + Standard PCBA (parts on both faces)", "title")
    s.merge(2, 1, 10, "What you order at jlcpcb.com in ONE order: 5 bare 4-layer panels (each holds the key board and the main PCB, black solder mask) and the assembly "
            "(soldering of all SMD parts) of 2 or 5 of them. Column E = scenario A (you build 1 light), column G = scenario B (you build 5 lights). Every fee is a blue input "
            "with the date it was read and its URL: the fee page says 'Last updated on Sep 09, 2026'; it was read on %s and its main rates were checked again on %s "
            "(the panel fee for two designs was read then). Prices change - re-check before you pay." % (V05_DATE, CHECK))
    s.merge(3, 1, 10, "Colour code: blue = typed-in number, blue on amber = ESTIMATE (no public price), black = formula, green = taken from another sheet.", "note")
    r = 5
    # ---- 1. cart settings
    s.merge(r, 1, 10, "1. What to select in the JLCPCB cart (https://cart.jlcpcb.com/quote)", "sub", border=True)
    r += 1
    s.put(r, 1, "Setting", "head")
    s.merge(r, 2, 4, "Value", "head", border=True)
    s.merge(r, 5, 10, "Why / what to watch", "head", border=True)
    rows = [
        ("Base material / layers", "FR-4, 4 layers", "Both boards use the same 4-layer stack-up with an inner ground plane. Do not change the layer count."),
        ("Dimensions", "%.1f x %.1f mm (JLC reads it from the Gerber)" % PANEL_MM, "One panel: key board left, main PCB right, two 6 mm rails with 3 fiducials and 4 tooling holes (section 2)."),
        ("PCB quantity", "5", "JLCPCB minimum. Four spare panels cost little and cover first-article problems."),
        ("Delivery format / panel format", "Panel by Customer, 1 x 1", "The Gerber already is the panel; do not let JLCPCB panelise it again."),
        ("Different design", "2", "Two different boards in one file: JLCPCB adds a surcharge, shown after the upload (section 4, ESTIMATE)."),
        ("PCB thickness", "0.8 mm", "The housing is built around 0.8 mm boards (main PCB on its ledges, key board on its bosses)."),
        ("Surface finish", "ENIG (immersion gold)", "Flat pads for the module and the fine-pitch parts, and gold pads J6 under the pogo pins."),
        ("Solder mask / silkscreen", "BLACK solder mask, WHITE silkscreen", "The design and all renders use black boards. A colour surcharge, if the cart shows one, belongs to the bare-panel price."),
        ("Copper / via covering", "1 oz outer, 0.5 oz inner; tented vias", "Defaults; the board is designed for them. Option: inner copper 1 oz (a small surcharge in the quote) "
         "halves the resistance of the 2 mm battery strip inside the board."),
        ("Edge rails / fiducials", "by customer (on the rails)", "If JLCPCB's review asks for a bigger panel for Standard assembly (it names 70 x 70 mm as the smallest), accept the edge rails it offers."),
        ("Order number on the board", "Default (JLC prints a code in a free area)", "Removing the code costs extra; it stays inside the closed body."),
        ("PCB Assembly", "ON - Standard PCBA, assemble BOTH sides", "Economic PCBA cannot do two-sided boards; set-up and stencil are charged per side."),
        ("Assembly quantity", "2 panels (for one light) or 5", "JLCPCB assembles from 2. The extra panel is your spare."),
        ("Upload", "%s, then %s and %s" % (ofp("FlashKa_panel_gerbers.zip"), ofp("BOM_JLCPCB.csv"), ofp("CPL_JLCPCB.csv")),
         "The three files of %s (written by tools/kicad/build_all.py). Check that all %d BOM lines are matched (no red rows) and look at the placement preview." % (ofd("1_JLCPCB"), len(lines))),
        ("Pogo pins P1-P6 (C22100007)", "must show stock", "If the JLCPCB parts library shows no stock, buy the pins into your JLCPCB parts library first (Parts Manager, order from LCSC stock), then place the order."),
        ("Power stage: C139643 (TPS62095), C351410 (DW01A), C238645 (SE8830A)", "must show stock", "Extended parts of the 1000 lm power stage. If one shows no stock, buy it into "
         "your JLCPCB parts library from LCSC stock (as for the pogo pins) or wait for stock. The SE8830A has no drop-in substitute: an 8205A-type dual MOSFET has about twice "
         "the on-resistance and the DW01A would then cut the light off in turbo (trip at about 2-3 A). Before ordering, check the SE8830A's pin order: pins 1-6 "
         "must be S1, D, S2, G2, D, G1 (as on the FS8205A; the LCSC data sheet shows it only as a picture); another pinout would disable the protection or short the cell."),
        ("Confirm parts placement", "Yes (recommended for the first order)", "JLC sends you a photo of the placed parts for your OK. Check pin 1 of every chip: the buck U2 (QFN, "
         "top face of the main PCB) has pin 1 at the corner nearest the inductor L1; on the bottom face the protection IC U6 sits right above the dual MOSFET Q3, both turned the "
         "same way. SW1-SW3 and LED3, LED4 sit on the bottom face of the key board (left board), the six pogo pins on its top face; the main PCB's six round gold pads J6 get no "
         "part. The rotation of the SKRKAEE020 and the NH-B1010RGBT in the JLC library is NOT verified."),
        ("Shipping", "Your choice (see sheet 'Hidden costs')", "Choose DDP / 'taxes paid' so the VAT is collected at checkout and nothing is asked at your door."),
    ]
    for (a, b, c) in rows:
        r += 1
        s.put(r, 1, a, "text")
        s.merge(r, 2, 4, b, "text", border=True)
        s.merge(r, 5, 10, c, "text", border=True)
    # ---- 2. panel and boards
    r += 2
    s.merge(r, 1, 10, "2. The panel and the two boards (mm)", "sub", border=True)
    r += 1
    s.put(r, 1, "Panel width (mm)", "text")
    s.put(r, 2, PANEL_MM[0], "in", fmt="0.0", name="pcb_w")
    s.merge(r, 3, 10, "tools/kicad/panel_jlc.py: key board left, main PCB right, 2.0 mm routed gaps, 6 mm rails top and bottom; the Gerber job file gives 45.1 x 32.6 mm "
            "(the 0.1 mm outline stroke included).", "note")
    r += 1
    s.put(r, 1, "Panel height (mm)", "text")
    s.put(r, 2, PANEL_MM[1], "in", fmt="0.0", name="pcb_h")
    r += 1
    s.put(r, 1, "Panel area (cm2)", "bold")
    s.put(r, 2, "=B%d*B%d/100" % (r - 2, r - 1), "calc", fmt="0.00", name="pcb_area_cm2")
    s.merge(r, 3, 10, "Only feeds the tiny packing fee. JLCPCB measures the Gerber itself. The panel stays inside the cheapest 4-layer size class (up to 50 x 50 mm).", "note")
    main_area = polygon_area_mm2(H["pcb_outline"]) / 100.0
    xs = [p[0] for p in H["pcb_outline"]]
    ys = [p[1] for p in H["pcb_outline"]]
    r += 1
    s.put(r, 1, "Main PCB (information)", "text")
    s.merge(r, 2, 10, "%.1f x %.1f mm, two corners chamfered 1.3 mm, %.2f cm2 (housing_interface.json 'pcb_outline'); unchanged from v0.6." % (max(xs) - min(xs), max(ys) - min(ys), main_area), "text", border=True)
    r += 1
    s.put(r, 1, "Key board (information)", "text")
    s.merge(r, 2, 10, "%.1f x %.1f mm, corners R%.1f, 0.8 mm, 4 layers: switches and ring LEDs on the bottom face, six pogo pins and eight resistors on the top face." % KB_MM, "text", border=True)
    # ---- 3. quantities
    r += 2
    s.merge(r, 1, 10, "3. Quantities (JLCPCB minimums: 5 bare panels, assembly from 2 panels)", "sub", border=True)
    for key, lab in (("min_asm", "Minimum panels JLCPCB assembles"), ("min_pcb", "Minimum bare panels per design"),
                     ("sides", "Assembled sides (double-sided)"), ("xray_per_board", "X-ray inspected parts per panel (optional)")):
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
    s.put(r, 1, "Panels assembled by JLCPCB = MAX(lights, minimum)", "text")
    s.put(r, 5, "=MAX(E%d,%s)" % (rl, s.ref("min_asm")), "calc", fmt="0", name="boards_A")
    s.put(r, 7, "=MAX(G%d,%s)" % (rl, s.ref("min_asm")), "calc", fmt="0", name="boards_B")
    rb = r
    r += 1
    s.put(r, 1, "Bare panels ordered (sold in steps of 5)", "text")
    s.put(r, 5, "=CEILING(MAX(%s,E%d),5)" % (s.ref("min_pcb"), rb), "calc", fmt="0", name="pcbs_A")
    s.put(r, 7, "=CEILING(MAX(%s,G%d),5)" % (s.ref("min_pcb"), rb), "calc", fmt="0", name="pcbs_B")
    # ---- 4. bare panels
    r += 2
    s.merge(r, 1, 10, "4. Bare panel fabrication (4 layers, 0.8 mm, ENIG, black solder mask, %.1f x %.1f mm) - shown by JLCPCB only AFTER the Gerber upload" % PANEL_MM, "sub", border=True)
    r += 1
    s.param(r, "pcb_fab5", "Bare panels, price for 5 (ESTIMATE)")
    r += 1
    s.param(r, "pcb_fab_low", "  low end of the range (information)")
    r += 1
    s.param(r, "pcb_fab_high", "  high end of the range (information)")
    r += 1
    s.param(r, "fab_design", "Surcharge for two designs in one file (ESTIMATE)")
    r += 1
    s.merge(r, 1, 10, "Anchors: a 100 x 100 mm 4-layer board costs about $32.90 for 5 (%s, 2026); a forum guide puts ENIG at +$5-10 on small orders (%s); v0.6 estimated $25 for 5 single "
            "main PCBs. The 'different design' fee exists on JLCPCB's panelisation pages (%s) but its amount appears only in the calculator. Real price: upload %s at %s, choose the "
            "options of section 1 and type the prices shown into the two amber cells above." % (U_PCBSYNC, U_ZBOTIC, U_PANELIZE, ofp("FlashKa_panel_gerbers.zip"), U_QUOTE), "note")
    r += 1
    s.put(r, 1, "Bare panel cost (price for 5 x panels ordered / 5)", "bold")
    s.put(r, 5, "=%s*%s/5" % (s.ref("pcb_fab5"), s.ref("pcbs_A")), "calc", fmt=USD2, name="fab_A")
    s.put(r, 7, "=%s*%s/5" % (s.ref("pcb_fab5"), s.ref("pcbs_B")), "calc", fmt=USD2, name="fab_B")
    r += 1
    s.put(r, 1, "Two-design surcharge (once per order)", "bold")
    s.put(r, 5, "=%s" % s.ref("fab_design"), "calc", fmt=USD2, name="fabd_A")
    s.put(r, 7, "=%s" % s.ref("fab_design"), "calc", fmt=USD2, name="fabd_B")
    # ---- 5. fees
    r += 2
    s.merge(r, 1, 10, "5. Standard PCBA fees (JLCPCB 'PCB assembly price' page, last updated Sep 09, 2026) - %s" % U_FEES, "sub", border=True)
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
    fee("smt_joint", "smt", "SMT assembly, per solder joint (joints per panel x panels)", "=%s*%s" % (jn, s.ref("boards_A")), "=%s*%s" % (jn, s.ref("boards_B")))
    fee("feeder_unique", "feeder", "Feeder loading, per unique part (Basic and Extended alike)", "=" + s.ref("n_lines"), "=" + s.ref("n_lines"))
    fee("ext_extra", "ext", "Extra fee per unique Extended part (Economic PCBA only - none in Standard)", "=" + s.ref("n_ext"), "=" + s.ref("n_ext"))
    fee("eng_fee", "eng", "Engineering fee (not on the 2026 page)", 1, 1, qkind="in")
    fee("confirm", "confirm", "Confirm parts placement (optional, recommended)", 1, 1, qkind="in")
    fee("asm_panel_fee", "asmpanel", "Panel fee: more than one design in the file (key board + main PCB)", 1, 1, qkind="in")
    xl = s.rng("xr_lo_0", "xr_lo_6")
    xp = s.rng("xr_pr_0", "xr_pr_6")
    fee("xray_per_board", "xray", "X-ray inspection (optional): parts inspected = parts per panel x panels", "=%s*%s" % (s.ref("xray_per_board"), s.ref("boards_A")),
        "=%s*%s" % (s.ref("xray_per_board"), s.ref("boards_B")), rate_text="tiered (section 7)", unit="USD per part (tiered)",
        cost=lambda q: "=IF(%s%d=0,0,%s%d*INDEX(%s,MATCH(%s%d,%s,1)))" % (q, r, q, r, xp, q, r, xl))
    fee("panel_board", "panel", "Panelisation processing by JLC (small board), per panel", "=" + s.ref("boards_A"), "=" + s.ref("boards_B"))
    fee("pack_base", "pack_base", "Packing (Standard PCBA), base per order", 1, 1, qkind="in")
    fee("pack_cm2", "pack_area", "Packing, per cm2 of panel (panel area x panels)", "=%s*%s" % (s.ref("pcb_area_cm2"), s.ref("boards_A")),
        "=%s*%s" % (s.ref("pcb_area_cm2"), s.ref("boards_B")))
    for key, nm, lab in (("hand_labour", "hand", "Hand-soldering labour (not needed) - quantity 0"),
                         ("prereflow", "prereflow", "'Pre-reflow soldering' per joint (unexplained row) - quantity 0"),
                         ("single_board", "single", "Single-board surcharge (the panel avoids it) - quantity 0"),
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
    s.put(r, 1, "Bare panels", "text")
    s.put(r, 5, "=" + s.ref("fab_A"), "calc", fmt=USD2)
    s.put(r, 7, "=" + s.ref("fab_B"), "calc", fmt=USD2)
    ra = r
    r += 1
    s.put(r, 1, "Two-design surcharge (section 4)", "text")
    s.put(r, 5, "=" + s.ref("fabd_A"), "calc", fmt=USD2)
    s.put(r, 7, "=" + s.ref("fabd_B"), "calc", fmt=USD2)
    r += 1
    s.put(r, 1, "Assembly fees (section 5)", "text")
    s.put(r, 5, "=" + s.ref("fees_A"), "calc", fmt=USD2)
    s.put(r, 7, "=" + s.ref("fees_B"), "calc", fmt=USD2)
    r += 1
    s.put(r, 1, "Components bought by JLCPCB (sheet '%s')" % BOM_SHEET, "text")
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
    s.put(r, 5, "=E%d+E%d+E%d+E%d" % (ra, ra + 1, ra + 2, ra + 3), "tot", fmt=USD2, name="jlc_goods_A")
    s.put(r, 6, None, "tot")
    s.put(r, 7, "=G%d+G%d+G%d+G%d" % (ra, ra + 1, ra + 2, ra + 3), "tot", fmt=USD2, name="jlc_goods_B")
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
            "fee of about EUR 15 - see sheet 'Hidden costs'.", "note")
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
        "Why one panel: both boards carry parts on both faces, so each needs Standard assembly with a set-up fee and a stencil per side. In one panel they share one order, one "
        "set-up per side, one stencil per side and the feeders of the parts they have in common, and the key board gets the main PCB's 4-layer 0.8 mm ENIG stack-up. Ordered "
        "separately (fall-back files in production/: FlashKa_main_gerbers.zip + BOM/CPL_JLCPCB_main.csv, FlashKa_keys_gerbers.zip + BOM/CPL_JLCPCB_keys.csv) the two orders "
        "would pay four set-ups and four stencils and two bare-board orders: about $208 in assembly fees (estimate) instead of the fees in section 5.",
        "Basic vs Extended: %d of the %d BOM lines are Basic, %d are Extended (JLC part type read on jlcpcb.com/partdetail/<LCSC> on %s; C115357, C25104, C22100007 and C238645 are ASSUMED). "
        "In the 2026 Standard PCBA price list every unique part pays the same feeder-loading fee, Basic or Extended, so Extended parts cost no extra here (the separate $3.07 per "
        "Extended part belongs to Economic PCBA; the input above is kept at 0)." % (sum(1 for l in lines if l["type"] == "Basic"), len(lines), sum(1 for l in lines if l["type"] == "Extended"), V05_DATE),
        "Parts that JLC cannot supply (out of stock) stop the order: JLC tells you by e-mail and you may substitute. Low-stock lines are marked in sheet '%s'. Retail stock at LCSC is "
        "not JLC's warehouse stock. The pogo pins (C22100007) had only 100 pcs at LCSC on %s; the stock of the SE8830A (C238645) could not be read on %s." % (BOM_SHEET, CHECK, CHECK_1000),
        "Placement loss: JLC buys a few pieces more than needed (they are billed inside the component price, see " + U_FAQ2 + "). The extra counts are estimates in sheet '%s'." % BOM_SHEET,
        "After delivery: break both boards out of the rails at the small perforated tabs and file the 0.3 mm nubs flush (two on each long side of each board).",
        "ENIG, 0.8 mm, 4 layers and black solder mask are standard options at JLCPCB (" + U_CAPAB + "); only the price of the bare panel is unknown until you upload the Gerber.",
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
PROC_NAME = {"CNC": "CNC aluminium", "KIT": "CNC plastic kit", "INKIT": "in a kit", "PRINT": "SLA resin print (JLC3DP)", "OPT": "CNC POM-C (option)",
             "HOME": "made at home"}


def part_file(p):
    if p["id"] == "mcav":
        return ofp("FlashKa_key_mould_cavity.step") + " + FlashKa_key_mould.pdf"
    if p["id"] == "mlid":
        return ofp("FlashKa_key_mould_lid.step") + " + FlashKa_key_mould.pdf"
    if p["proc"] == "PRINT":
        return ofp(p["key"] + ".stl") + " (drawing FlashKa_key_mould.pdf)"
    if p["id"] in ("tray", "lid", "pmma", "pom"):
        return ofp(p["key"] + ".step") + " + %s.pdf" % p["key"]
    if p["proc"] == "INKIT":
        return "%s (single file for shops that take small parts)" % ofp(p["key"] + ".step")
    if p["id"] == "keyside":
        return ofp("FlashKa_key_side.step") + " + FlashKa_key_side.pdf"
    return ofp(p["key"] + ".step")


def wall_texts(H):
    """(walls, why) for the JLCCNC quote form: every metal wall below 0.8 mm (housing_interface.json 'min_walls')."""
    walls = thin_walls(H)
    if not walls:
        return "See the drawing notes for the thinnest walls", "JLCCNC recommends 0.8 mm minimum wall in metal."
    txt = "Metal walls below 0.8 mm in the design: %s" % "; ".join("%s mm (%s)" % (v_, k_) for v_, k_ in walls)
    below_abs = [v_ for v_, k_ in walls if v_ < 0.5 - 1e-9]
    below_rec = [v_ for v_, k_ in walls if 0.5 - 1e-9 <= v_ < 0.8 - 1e-9]
    why = "JLCCNC recommends 0.8 mm minimum wall in metal (absolute minimum 0.5 mm)."
    if below_abs:
        why += (" %s mm %s below the absolute minimum: the shop must accept it in writing in the quote chat." % (" and ".join("%s" % x for x in below_abs),
                "is" if len(below_abs) == 1 else "are"))
    else:
        why += " No wall is below the absolute minimum (drawing FK-H-01 note 7)."
    if below_rec:
        why += " %s mm %s below the recommendation." % (", ".join("%s" % x for x in below_rec), "is" if len(below_rec) == 1 else "are")
    why += " Name them in the quote chat (housing_interface.json 'min_walls'; metal under the texture at least %s mm)." % H.get("texture_min_metal_mm", "n/a")
    return txt, why


def build_housing(book, hparts, hsrc, H):
    S = "Housing"
    s = Sh(book, S, [40, 15, 13, 13, 13, 14, 12, 12, 12, 34, 58])
    ws = s.ws
    s.put(1, 1, "Housing - aluminium tray + lid, PMMA and POM-C machining kits (JLCCNC), resin casting mould (JLC3DP, in the same order)", "title")
    s.merge(2, 1, 11, "The machined parts of v0.7 come from JLCCNC: the tray and the lid in aluminium 6061-T6 (bead blast + black anodise, no marking of any kind), the clear "
            "PMMA main keys in one machining kit and the two black POM-C parts of a light (with a spare lid insert) in a second kit. The casting mould for the rubber side keys "
            "- once per builder - is a resin print from JLC3DP by default; JLCCNC merges its orders with JLC3DP, so it comes in the same parcel. The aluminium mould from "
            "JLCCNC is the durable option (priced in section 6b, not in the totals). JLCCNC and JLC3DP show their prices only after you upload the files and publish no "
            "per-part price list, so every price on this sheet is an ESTIMATE made with the method written below. When you have the instant quotes, type them into the "
            "'real quote' cells (sections 6, 6b and 7): the workbook then uses your numbers.")
    s.merge(3, 1, 11, "Geometry source: %s. Files to upload: %s (tray, lid, the two kits) and the mould plates in %s; each drawing PDF there has the name of its STEP file "
            "(cad/FlashKa_tray_drawing.pdf -> FlashKa_tray.pdf, ...). The two rubber side keys are cast at home: their material is in sheet 'Bought parts'."
            % (hsrc, ofd("2_JLCCNC"), ofd("3_rubber_keys")), "note")
    r = 5
    s.merge(r, 1, 11, "1. Parts and geometry (volumes from housing_interface.json 'volumes_mm3' and key_mould_checks.json; boxes from 'tray_bbox', 'machining_kits', "
            "key_mould_checks.json and the STL files)", "sub", border=True)
    r += 1
    s.head(r, ["Part", "Process", "Box X (mm)", "Box Y (mm)", "Box Z (mm)", "Volume (mm3)", "Mass (g)", "Per light", "Fixed per order", "File (STEP / STL / PDF)", "Note"])
    ws.row_dimensions[r].height = 28
    for p in hparts:
        r += 1
        i = p["id"]
        s.put(r, 1, p["label"], "bold" if p["proc"] in ("CNC", "KIT", "PRINT") and not p.get("opt") else "text")
        s.put(r, 2, PROC_NAME[p["proc"]] + (" (option)" if p.get("opt") else ""), "text")
        for k, ax in enumerate("xyz"):
            s.put(r, 3 + k, p["box"][k], "in", fmt="0.00", name="h_%s_%s" % (ax, i))
        if p["vol"] is not None:
            s.put(r, 6, p["vol"], "in", fmt="#,##0.0", name="h_vol_%s" % i)
        else:
            s.put(r, 6, "-", "text", align="right")
        s.put(r, 7, p["mass"] if p["mass"] is not None else "-", "in" if p["mass"] is not None else "text", fmt="0.000", align="right")
        if p["proc"] in ("CNC", "PRINT"):
            s.put(r, 8, p["per_light"], "in", fmt="0", name="h_per_%s" % i)
            s.put(r, 9, p["spare"], "in", fmt="0", name="h_spare_%s" % i)
        elif p["proc"] == "KIT":
            s.put(r, 8, "section 7", "text", align="right")
            s.put(r, 9, "section 7", "text", align="right")
        elif p["proc"] == "INKIT":
            s.put(r, 8, "%d per kit" % p["count"], "text", align="right")
            s.put(r, 9, "-", "text", align="right")
        elif p["proc"] == "HOME":
            s.put(r, 8, p["per_light"], "text", fmt="0")
            s.put(r, 9, "-", "text", align="right")
        else:
            s.put(r, 8, 0, "text", fmt="0")
            s.put(r, 9, "-", "text", align="right")
        s.put(r, 10, part_file(p), "text")
        s.put(r, 11, p["note"], "text")
    # ---- 2. CNC method
    r += 2
    s.merge(r, 1, 11, "2. JLCCNC aluminium estimate - method (all inputs are ESTIMATES; JLCCNC publishes no price list, " + U_JLCNC_COST + ")", "sub", border=True)
    r += 1
    s.merge(r, 1, 11, "Cost of one aluminium part = aluminium (stock block weight x price) + machining (minutes x rate x complexity) + threads + finish. Stock block = bounding "
            "box + allowance on every side. Machining minutes = material to remove / removal rate + minutes for fine features (pockets, holes, grooves, texture: section 4). "
            "Per order you also pay the set-ups (each re-clamping of the part) and the anodizing lot fee once. Calibrated in v0.5 so that one tray + lid costs about the same as "
            "the v0.4 estimate; v0.6 and v0.7 keep these inputs and change only what the design changes (sections 4 and 5). The same model prices the two plates of the "
            "aluminium mould (option).", "note")
    for key, lab in (("al_kg", "Aluminium 6061 price (USD per kg)"), ("al_dens", "Aluminium density (g per cm3)"), ("allow", "Stock allowance per side (mm)"),
                     ("mrr", "Material removal rate (cm3 per minute)"), ("rate_min", "Machine time rate (USD per minute)"),
                     ("setup_fee", "Set-up cost (USD per set-up)"), ("tap_fee", "Tapping (USD per thread)"),
                     ("groove_min_m", "V-groove machining time (minutes per metre)"), ("mould_blast", "Bead blast of the aluminium mould's cavity half (USD per part)")):
        r += 1
        s.param(r, key, lab, c_end=11)
    r += 1
    s.param(r, "texture_on", "Panel texture: 1 = cut it, 0 = leave it out (priced option)", fmt="0", c_end=11)
    dv = DataValidation(type="list", formula1='"1,0"', allow_blank=False)
    ws.add_data_validation(dv)
    dv.add(ws.cell(row=r, column=2))
    # ---- 3. finishes
    r += 2
    s.merge(r, 1, 11, "3. Surface finish choices at JLCCNC for the tray and the lid (prices are ESTIMATES; " + U_JLCNC_FIN + ", read " + V05_DATE + " and again " + V06_RESEARCH + ")", "sub", border=True)
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
    s.merge(r, 5, 11, "Pick the finish here; the tray/lid/lot prices below follow. The design assumes 'Bead blast + black anodize' (type II, 8-12 um on the drawings; JLCCNC range "
            "8-25 um). The 0.2 mm texture and the 0.3 mm grooves stay visible after blasting and anodizing. The aluminium mould (option) is not anodised: its cavity half is "
            "bead blasted (section 2).", "note")
    nm_rng = s.rng("fin_name_0", "fin_name_%d" % (len(FINISHES) - 1))
    for lab, col_key in (("Finish cost per tray (USD)", "fin_tray"), ("Finish cost per lid (USD)", "fin_lid"), ("Anodizing lot fee per order (USD)", "fin_lot")):
        r += 1
        s.put(r, 1, lab, "text")
        s.put(r, 2, "=INDEX(%s,MATCH(%s,%s,0))" % (s.rng(col_key + "_0", col_key + "_%d" % (len(FINISHES) - 1)), s.ref("finish_sel"), nm_rng),
              "calc", fmt=USD2, name=col_key)
    # ---- 4. fine-feature time
    r += 2
    s.merge(r, 1, 11, "4. Fine-feature time of the tray and the lid - what changed from v0.6 (ESTIMATES; the v0.7 exterior adds panels, a V texture and transverse grooves, the v0.6 seams are gone)", "sub", border=True)
    r += 1
    s.merge(r, 1, 11, "v0.6 priced all fine work as tray 38.09 min and lid 7.52 min. v0.7 keeps that, takes out the features that no longer exist and adds the new ones. V-groove work is "
            "counted in millimetres at ONE rate (minutes per metre, section 2) for the seams that go and the texture and grooves that come, so the groove part of the change follows "
            "the real geometry (lengths computed from housing_interface.json 'panel_layout' and the groove parameters). Other changes are typed-in minutes. The texture row is "
            "multiplied by the switch 'texture_on' (section 2).", "note")
    r += 1
    s.head(r, ["Feature", "Tray (mm or min)", "Lid (mm or min)", "Unit", "Tray (min)", "Lid (min)"])
    s.merge(r, 7, 11, "Basis", "head", border=True)
    ws.row_dimensions[r].height = 28
    fr0 = r + 1
    gm = s.ref("groove_min_m")
    for fid, lab, kind, tv, lv, note in feature_rows(H):
        r += 1
        s.put(r, 1, lab, "text")
        s.put(r, 2, tv, "est" if kind == "min" else "in", fmt="0.0#")
        s.put(r, 3, lv, "est" if kind == "min" else "in", fmt="0.0#")
        s.put(r, 4, "min" if kind == "min" else "mm of V-groove", "text")
        for c, src, nmx in ((5, "B", "tray"), (6, "C", "lid")):
            if kind == "min":
                f = "=%s%d" % (src, r)
            elif fid == "texture":
                f = "=%s%d/1000*%s*%s" % (src, r, gm, s.ref("texture_on"))
            else:
                f = "=%s%d/1000*%s" % (src, r, gm)
            s.put(r, c, f, "calc", fmt="0.00", name=("tex_min_" + nmx) if fid == "texture" else None)
        s.merge(r, 7, 11, note, "text", border=True)
    fr1 = r
    r += 1
    s.put(r, 1, "Fine-feature time, v0.7 (min)", "tot")
    for c in (2, 3, 4):
        s.put(r, c, None, "tot")
    s.put(r, 5, "=SUM(E%d:E%d)" % (fr0, fr1), "tot", fmt="0.00", name="feat_tray")
    s.put(r, 6, "=SUM(F%d:F%d)" % (fr0, fr1), "tot", fmt="0.00", name="feat_lid")
    t_tex, l_tex = texture_lengths(H)
    t_grv, l_grv = groove_lengths(H)
    s.merge(r, 7, 11, "V-groove length: v0.6 %.0f mm of seams; v0.7 %.0f mm of texture and %.0f mm of transverse grooves." % (V06_GEOM["skin_tray_mm"] + V06_GEOM["skin_lid_mm"],
                                                                                                                          t_tex + l_tex, t_grv + l_grv), "note")
    # ---- 4b. mould
    r += 2
    s.merge(r, 1, 11, "4b. Fine-feature time of the two plates of the aluminium mould (option; ESTIMATES; drawing FK-H-08)", "sub", border=True)
    r += 1
    s.head(r, ["Feature", "Cavity half (min)", "Lid (min)"])
    s.merge(r, 4, 11, "Basis", "head", border=True)
    m0 = r + 1
    for fid, lab, cv, lv, note in mould_feature_rows():
        r += 1
        s.put(r, 1, lab, "text")
        s.put(r, 2, cv, "est", fmt="0.0")
        s.put(r, 3, lv, "est", fmt="0.0")
        s.merge(r, 4, 11, note, "text", border=True)
    m1 = r
    r += 1
    s.put(r, 1, "Fine-feature time of the aluminium mould plates (min)", "tot")
    s.put(r, 2, "=SUM(B%d:B%d)" % (m0, m1), "tot", fmt="0.00", name="feat_mcav")
    s.put(r, 3, "=SUM(C%d:C%d)" % (m0, m1), "tot", fmt="0.00", name="feat_mlid")
    # ---- 5. CNC per part
    r += 2
    s.merge(r, 1, 11, "5. JLCCNC estimate - one aluminium part", "sub", border=True)
    r += 1
    cnc = [p for p in hparts if p["proc"] == "CNC"]
    hname = {"tray": "Tray", "lid": "Lid", "mcav": "Alu mould cavity half (option)", "mlid": "Alu mould lid (option)"}
    s.head(r, ["Step"] + [hname[p["id"]] for p in cnc])
    s.merge(r, 2 + len(cnc), 11, "How it is computed", "head", border=True)
    ws.row_dimensions[r].height = 28
    al = s.ref("allow")
    c_how = 2 + len(cnc)

    def row(label, fn, fmt, kind, how, nm=None):
        nonlocal r
        r += 1
        s.put(r, 1, label, "text")
        for k, p in enumerate(cnc):
            s.put(r, 2 + k, fn(p, r), kind, fmt=fmt, name=("%s_%s" % (nm, p["id"])) if nm else None)
        s.merge(r, c_how, 11, how, "text", border=True)
        return r

    def cl(p):
        return colname(2 + cnc.index(p))
    ra = row("Stock block volume (cm3)", lambda p, rr: "=(%s+2*%s)*(%s+2*%s)*(%s+2*%s)/1000" % (s.ref("h_x_" + p["id"]), al, s.ref("h_y_" + p["id"]), al, s.ref("h_z_" + p["id"]), al),
             "0.00", "calc", "(X + 2 x allowance) x (Y + 2 x allowance) x (Z + 2 x allowance) / 1000", "cnc_stock")
    rb = row("Part volume (cm3)", lambda p, rr: "=%s/1000" % s.ref("h_vol_" + p["id"]), "0.00", "calc", "volume / 1000")
    rc = row("Material to remove (cm3)", lambda p, rr: "=%s%d-%s%d" % (cl(p), ra, cl(p), rb), "0.00", "calc", "stock block - part", "cnc_removed")
    rmat = row("Aluminium cost (USD)", lambda p, rr: "=%s%d*%s/1000*%s" % (cl(p), ra, s.ref("al_dens"), s.ref("al_kg")), USD2, "calc",
               "stock volume x density / 1000 x price per kg (you pay for the whole block)", "cnc_mat")
    rf = row("Fine-feature time (min)", lambda p, rr: "=" + s.ref("feat_" + p["id"]), "0.00", "calc", "from section 4 (tray, lid) and 4b (aluminium mould plates)")
    rm = row("Machining time (min)", lambda p, rr: "=%s%d/%s+%s%d" % (cl(p), rc, s.ref("mrr"), cl(p), rf), "0.0", "calc",
             "material to remove / removal rate + fine-feature time", "cnc_min")
    rx = row("Complexity factor", lambda p, rr: p["factor"], "0.00", "est",
             "ESTIMATE: tray 1.10 and lid 1.30 as in v0.6 (texture and grooves on the facets and the ends need indexed set-ups; the lid is a cap with a 1.5 mm plate over "
             "the cavity and two bosses); aluminium mould plates 1.30 (0.6 mm end mill for the chevron grooves, +/-0.02 mm on cavities and parting faces)", "factor")
    rh = row("Machining cost (USD)", lambda p, rr: "=%s%d*%s*%s%d" % (cl(p), rm, s.ref("rate_min"), cl(p), rx), USD2, "calc",
             "minutes x rate x complexity factor", "cnc_mach")
    rt = row("Threads to cut (number)", lambda p, rr: p["taps"], "0", "in",
             "Tray: 4 x M1.6 (lid screws) + 2 x M1.6 BLIND (key-board bosses) + 1 x M1.6 (laser set screw, from the head-block top under the lid). Lid: none (clearance holes). Aluminium mould cavity half: 4 x M3.", "taps")
    rtc = row("Tapping cost (USD)", lambda p, rr: "=%s%d*%s" % (cl(p), rt, s.ref("tap_fee")), USD2, "calc", "threads x cost per thread")
    rfin = row("Finish cost per part (USD)", lambda p, rr: {"tray": "=" + s.ref("fin_tray"), "lid": "=" + s.ref("fin_lid"), "blast": "=" + s.ref("mould_blast"),
                                                           "none": 0}[p["fin"]], USD2, "calc",
               "tray and lid: chosen finish (section 3); aluminium mould cavity half: bead blast (section 2); its lid: as machined", "cnc_fin")
    row("Variable cost per part (USD)", lambda p, rr: "=%s%d+%s%d+%s%d+%s%d" % (cl(p), rmat, cl(p), rh, cl(p), rtc, cl(p), rfin), USD2, "bold",
        "aluminium + machining + tapping + finish", "cnc_var")
    rs = row("Set-ups (number)", lambda p, rr: p["setups"], "0", "in",
             "ESTIMATE: tray 5 (top, bottom, -Y side, +Y side, ends; the diagonal facets from the bottom and side set-ups), lid 3 (top with its two diagonal facets, "
             "bottom with the pocket and the seat, ends), each aluminium mould plate 2 (both faces)", "setups")
    row("Set-up cost per order (USD)", lambda p, rr: "=%s%d*%s" % (cl(p), rs, s.ref("setup_fee")), USD2, "calc", "set-ups x set-up cost, paid once per order", "cnc_setup")
    # ---- 6. aluminium totals
    r += 2
    s.merge(r, 1, 11, "6. JLCCNC total for the tray and the lid (one set per light)", "sub", border=True)
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
        s.put(r, 1, "%s pieces = lights x per light + fixed per order" % hname[p["id"]], "text")
        s.put(r, 2, "=B%d*%s+%s" % (rl, s.ref("h_per_" + p["id"]), s.ref("h_spare_" + p["id"])), "calc", fmt="0")
        s.put(r, 3, "=C%d*%s+%s" % (rl, s.ref("h_per_" + p["id"]), s.ref("h_spare_" + p["id"])), "calc", fmt="0")
        pieces[p["id"]] = r

    def total_block(ids, lab_var, lab_set, set_extra, est_name, est_lab, est_note, quote=None):
        """variable + set-ups = estimate; quote = (quote_name, used_name, quote_lab, quote_note, used_lab) adds a quote cell and the used value."""
        nonlocal r
        r += 1
        s.put(r, 1, lab_var, "text")
        for k, colx in enumerate(("B", "C")):
            s.put(r, 2 + k, "=" + "+".join("%s%d*%s" % (colx, pieces[i], s.ref("cnc_var_" + i)) for i in ids), "calc", fmt=USD2)
        rv = r
        r += 1
        s.put(r, 1, lab_set, "text")
        for k in range(2):
            s.put(r, 2 + k, "=" + "+".join(s.ref("cnc_setup_" + i) for i in ids) + set_extra, "calc", fmt=USD2)
        r += 1
        s.put(r, 1, est_lab, "bold")
        s.put(r, 2, "=B%d+B%d" % (rv, r - 1), "calc", fmt=USD2, name=est_name + "_A")
        s.put(r, 3, "=C%d+C%d" % (rv, r - 1), "calc", fmt=USD2, name=est_name + "_B")
        s.merge(r, 4, 11, est_note, "note")
        re_ = r
        if quote:
            quote_name, used_name, quote_lab, quote_note, used_lab = quote
            r += 1
            s.put(r, 1, quote_lab, "bold")
            s.put(r, 2, None, "in", fmt=USD2, name=quote_name + "_A")
            s.put(r, 3, None, "in", fmt=USD2, name=quote_name + "_B")
            s.merge(r, 4, 11, quote_note, "note")
            rq = r
            r += 1
            s.put(r, 1, used_lab, "tot")
            s.put(r, 2, "=IF(ISNUMBER(B%d),B%d,B%d)" % (rq, rq, re_), "tot", fmt=USD2, name=used_name + "_A")
            s.put(r, 3, "=IF(ISNUMBER(C%d),C%d,C%d)" % (rq, rq, re_), "tot", fmt=USD2, name=used_name + "_B")

    total_block(("tray", "lid"), "Tray + lid: variable cost (pieces x cost per part)", "Tray + lid: set-ups + anodizing lot fee (once per order)",
                "+" + s.ref("fin_lot"), "alu_est", "ESTIMATE of tray + lid (USD)",
                "Ordering 5 sets at once is much cheaper per set than 1 set, because the set-ups and the anodizing lot fee are paid once.",
                ("cnc_alu_quote", "alu", "REAL instant-quote price for tray + lid (type it in, USD incl. finish, without shipping)",
                 "Upload FlashKa_tray.step + FlashKa_tray.pdf and FlashKa_lid.step + FlashKa_lid.pdf from " + ofd("2_JLCCNC") + " at " + U_JLCNC
                 + " and type the price shown for your quantity here. Leave empty to use the estimate.", "Tray + lid used in the totals (USD)"))
    r += 1
    s.put(r, 1, "  of which the panel texture (USD, in the estimate above; 0 when 'texture_on' is 0)", "text")
    for k, colx in enumerate(("B", "C")):
        s.put(r, 2 + k, "=%s%d*%s*%s*%s+%s%d*%s*%s*%s" % (colx, pieces["tray"], s.ref("tex_min_tray"), s.ref("rate_min"), s.ref("factor_tray"),
                                                       colx, pieces["lid"], s.ref("tex_min_lid"), s.ref("rate_min"), s.ref("factor_lid")),
              "calc", fmt=USD2, name="tex_cost_" + "AB"[k])
    s.merge(r, 4, 11, "Texture minutes (section 4) x machine rate x complexity factor x pieces. Leaving the texture out saves this and the VAT and duty on it (options table "
            "of the Summary).", "note")
    # ---- 6b. the casting mould
    r += 2
    s.merge(r, 1, 11, "6b. Casting mould for the rubber side keys, once per builder: resin print from JLC3DP (default, in the totals) or aluminium from JLCCNC (option)", "sub", border=True)
    r += 1
    s.merge(r, 1, 11, "Resin (default): two SLA plates printed by JLC3DP from %s and %s, ordered with the JLCCNC parts as one merged order (one package, one shipping "
            "rate: %s, read %s). JLC3DP publishes only the headline 'SLA from $0.30': the estimate is MAX(minimum per part, rate x model volume) per plate. "
            "Aluminium (option): the two 6061-T6 plates of drawing FK-H-08 priced with the aluminium model of sections 2-5; it holds +/-0.02 mm and lasts for many pours, "
            "the resin print is cheaper but does not hold that tolerance (try the first key in its opening)." % (ofp("FlashKa_key_mould_resin_cavity.stl"),
                                                                                                                ofp("FlashKa_key_mould_resin_lid.stl"), U_MERGED, CHECK_1000), "note")
    for key, lab in (("resin_cm3", "JLC3DP SLA resin, rate (USD per cm3 of model volume)"), ("resin_min", "JLC3DP minimum price per part (USD)")):
        r += 1
        s.param(r, key, lab, c_end=11)
    for p in [q for q in hparts if q["proc"] == "PRINT"]:
        r += 1
        s.put(r, 1, "%s: price per plate (USD)" % {"rcav": "Resin cavity half", "rlid": "Resin lid"}[p["id"]], "text")
        s.put(r, 2, "=MAX(%s,%s*%s/1000)" % (s.ref("resin_min"), s.ref("resin_cm3"), s.ref("h_vol_" + p["id"])), "calc", fmt=USD2, name="resin_unit_" + p["id"])
        s.merge(r, 4, 11, "MAX(minimum, rate x %.2f cm3); %d plate per builder (section 1, 'Fixed per order')." % (p["vol"] / 1000.0, p["spare"]), "note")
    prn = [q for q in hparts if q["proc"] == "PRINT"]
    r += 1
    s.put(r, 1, "ESTIMATE of the resin mould (USD)", "bold")
    for k in range(2):
        s.put(r, 2 + k, "=" + "+".join("%s*%s" % (s.ref("h_spare_" + q["id"]), s.ref("resin_unit_" + q["id"])) for q in prn), "calc", fmt=USD2,
              name="mould_est_" + "AB"[k])
    s.merge(r, 4, 11, "Once per builder: the same in both scenarios. The four M3 x 16 bolts with washers and nuts are in sheet 'Bought parts'.", "note")
    rme = r
    total_block(("mcav", "mlid"), "Aluminium mould (option): variable cost of the two plates", "Aluminium mould (option): set-ups (once per order)", "", "mould_alu_est",
                "ESTIMATE of the aluminium mould (option, NOT in the totals; USD)",
                "Research before the design was finished guessed $15-30 for a small two-plate mould; this estimate uses the same model as the tray and the lid (finer cutters, "
                "4 cavities). Its hardware (2 dowel pins, 4 M3 x 12 screws) is listed in the options table of the Summary, not in 'Bought parts'.")
    r += 1
    s.put(r, 1, "REAL quote of the mould you order (resin or aluminium; type it in, USD, without shipping)", "bold")
    s.put(r, 2, None, "in", fmt=USD2, name="mould_quote_A")
    s.put(r, 3, None, "in", fmt=USD2, name="mould_quote_B")
    s.merge(r, 4, 11, "Resin: upload the two STL files at %s (SLA, the standard resin of the quote). Aluminium: upload FlashKa_key_mould_cavity.step and "
            "FlashKa_key_mould_lid.step with FlashKa_key_mould.pdf from %s at JLCCNC. Leave empty to use the resin estimate; type 0 if you already have a mould."
            % (U_3DP, ofd("3_rubber_keys")), "note")
    rq = r
    r += 1
    s.put(r, 1, "Casting mould used in the totals (USD)", "tot")
    s.put(r, 2, "=IF(ISNUMBER(B%d),B%d,B%d)" % (rq, rq, rme), "tot", fmt=USD2, name="mould_A")
    s.put(r, 3, "=IF(ISNUMBER(C%d),C%d,C%d)" % (rq, rq, rme), "tot", fmt=USD2, name="mould_B")
    # ---- 7. plastic kits
    r += 2
    s.merge(r, 1, 11, "7. JLCCNC plastic machining kits (PMMA main keys, POM-C parts) - ESTIMATE", "sub", border=True)
    r += 1
    s.merge(r, 1, 11, "JLCCNC machines plastic parts only from 30 x 20 x 8 mm up (" + U_JLCNC_SIZE + ", read " + CHECK + "); the PMMA main key and every POM-C part are smaller, so they "
            "come as two kits (each one solid piece: a frame with the parts on small tabs). JLCCNC publishes no price for plastic parts: the estimate is a first-piece price per "
            "part type (research ranges: PMMA key with polish $6-9, POM-C $5-8 per part type) plus a share of it for every further piece of the same part type in the order "
            "(cost = first piece x (part types + (pieces - part types) x share)).", "note")
    for key, lab in (("pmma_first", "PMMA main key, first piece (USD)"), ("pom_first", "POM-C part, first piece of a part type (USD)"),
                     ("next_frac", "Each further piece: share of the first piece")):
        r += 1
        s.param(r, key, lab, fmt=("0.00" if key == "next_frac" else None), c_end=11)
    r += 1
    s.head(r, ["Kit", "Part types", "Pieces per kit", "Kits A", "Cost A (USD)", "Kits B", "Cost B (USD)"])
    s.merge(r, 8, 11, "How many kits", "head", border=True)
    ws.row_dimensions[r].height = 28
    kits = [p for p in hparts if p["proc"] == "KIT"]
    k0 = r + 1
    for p in kits:
        r += 1
        i = p["id"]
        s.put(r, 1, p["label"], "text")
        s.put(r, 2, p["types"], "in", fmt="0", name="kit_types_" + i)
        s.put(r, 3, p["pieces"], "in", fmt="0", name="kit_pieces_" + i)
        first = s.ref(p["first"])
        for sc, cq, cc in (("A", 4, 5), ("B", 6, 7)):
            s.put(r, cq, "=ROUNDUP((%s*%d+%d)/%d,0)" % (s.ref("lights" + sc), p["need_light"], p["need_spare"], p["per_kit"]), "calc", fmt="0", name="kit_qty_%s_%s" % (i, sc))
            s.put(r, cc, "=IF(%s%d=0,0,%s*(B%d+(C%d*%s%d-B%d)*%s))" % (colname(cq), r, first, r, r, colname(cq), r, r, s.ref("next_frac")), "calc", fmt=USD2,
                  name="kit_cost_%s_%s" % (i, sc))
        how = ("ROUNDUP((lights + 1 spare key) / 3 keys per kit)" if i == "pmma" else "one kit per light (it holds a spare lid insert)")
        s.merge(r, 8, 11, how, "text", border=True)
    k1 = r
    r += 1
    s.put(r, 1, "ESTIMATE of the two kits (USD)", "bold")
    s.put(r, 5, "=SUM(E%d:E%d)" % (k0, k1), "calc", fmt=USD2, name="kit_est_A")
    s.put(r, 7, "=SUM(G%d:G%d)" % (k0, k1), "calc", fmt=USD2, name="kit_est_B")
    rke = r
    r += 1
    s.put(r, 1, "REAL instant-quote price for the kits (type it in, USD, without shipping)", "bold")
    s.put(r, 5, None, "in", fmt=USD2, name="kit_quote_A")
    s.put(r, 7, None, "in", fmt=USD2, name="kit_quote_B")
    s.merge(r, 8, 11, "Upload FlashKa_pmma_kit.step + FlashKa_pmma_kit.pdf (material: acrylic / PMMA, clear, cast) and FlashKa_pom_kit.step + FlashKa_pom_kit.pdf (POM, black) "
            "from %s and type the price for the kits above." % ofd("2_JLCCNC"), "note")
    rkq = r
    r += 1
    s.put(r, 1, "Kits used in the totals (USD)", "tot")
    s.put(r, 5, "=IF(ISNUMBER(E%d),E%d,E%d)" % (rkq, rkq, rke), "tot", fmt=USD2, name="kit_A")
    s.put(r, 7, "=IF(ISNUMBER(G%d),G%d,G%d)" % (rkq, rkq, rke), "tot", fmt=USD2, name="kit_B")
    r += 1
    s.merge(r, 1, 11, "Not in the totals: the optional POM-C laser sleeve (only for a laser module thinner than 6 mm) is a single part below the instant-quote size and not in a kit; "
            "order it from a shop that takes small parts (%s)." % ofp("FlashKa_laser_sleeve.step"), "note")
    # ---- 8. totals
    r += 2
    s.merge(r, 1, 11, "8. JLCCNC + JLC3DP order and housing total", "sub", border=True)
    r += 1
    s.head(r, ["", "Scenario A", "Scenario B"])
    s.merge(r, 4, 11, "Note", "head", border=True)
    r += 1
    s.put(r, 1, "JLCCNC + JLC3DP ORDER used in the totals: tray + lid + resin mould + kits (USD)", "tot")
    s.put(r, 2, "=%s+%s+%s" % (s.ref("alu_A"), s.ref("mould_A"), s.ref("kit_A")), "tot", fmt=USD2, name="cnc_A")
    s.put(r, 3, "=%s+%s+%s" % (s.ref("alu_B"), s.ref("mould_B"), s.ref("kit_B")), "tot", fmt=USD2, name="cnc_B")
    s.merge(r, 4, 11, "One merged order (one parcel). The goods value decides the customs route in sheet 'Hidden costs'.", "note")
    r += 1
    s.put(r, 1, "Distance below the EUR 150 IOSS line (EUR; negative = above)", "bold")
    s.put(r, 2, "=%s-%s/%s" % (s.ref("ioss_eur"), s.ref("cnc_A"), s.ref("fx")), "calc", fmt=EUR2, name="cnc_line_gap_A")
    s.put(r, 3, "=%s-%s/%s" % (s.ref("ioss_eur"), s.ref("cnc_B"), s.ref("fx")), "calc", fmt=EUR2, name="cnc_line_gap_B")
    s.merge(r, 4, 11, "Up to EUR 150 the parcel pays VAT (IOSS) and EUR 3 per customs line; above it 6 % duty, VAT and a carrier fee of about EUR 15 (sheet 'Hidden costs').", "note")
    r += 1
    s.put(r, 1, "HOUSING TOTAL (USD)", "tot")
    s.put(r, 2, "=B%d" % (r - 2), "tot", fmt=USD2, name="housing_A")
    s.put(r, 3, "=C%d" % (r - 2), "tot", fmt=USD2, name="housing_B")
    s.merge(r, 4, 11, "All housing parts come from JLCCNC and JLC3DP; the rubber keys' material is in sheet 'Bought parts'.", "note")
    # ---- 9. quote forms
    r += 2
    s.merge(r, 1, 11, "9. What to enter on the JLCCNC and JLC3DP quote forms", "sub", border=True)
    wall_txt, wall_why = wall_texts(H)
    pmma_size, _ = kit_info(H, "FlashKa_pmma_kit")
    pom_size, _ = kit_info(H, "FlashKa_pom_kit")
    forms = [
        ("JLCCNC files", "%s: FlashKa_tray.step + FlashKa_tray.pdf, FlashKa_lid.step + FlashKa_lid.pdf, FlashKa_pmma_kit.step + FlashKa_pmma_kit.pdf, FlashKa_pom_kit.step + "
         "FlashKa_pom_kit.pdf" % ofd("2_JLCCNC"),
         "STEP is mandatory, a drawing is recommended, names must match (" + U_JLCNC_ORD + "). The PDFs are the drawings FK-H-01 (2 sheets), FK-H-02, FK-H-06 and FK-H-07, "
         "renamed to the STEP names; they carry the threads and tolerances."),
        ("JLC3DP files (same merged order)", "%s and %s: two parts, SLA resin (the standard resin of the quote), once per builder" % (ofp("FlashKa_key_mould_resin_cavity.stl"),
                                                                                                                                    ofp("FlashKa_key_mould_resin_lid.stl")),
         "Print with the parting face up, supports on the back only (drawing FK-H-08 in the same folder). Put the JLCCNC and the JLC3DP parts into one merged order "
         "(cart: 'All'; " + U_COMBINE + ") so that they ship as one parcel."),
        ("Process / material", "Tray, lid: CNC milling, aluminium 6061-T6. PMMA kit: CNC milling, acrylic (PMMA), clear, cast (not extruded). POM-C kit: CNC milling, POM (acetal copolymer), black",
         "Plastics listed by JLCCNC: PMMA (acrylic) and POM among others (" + U_JLCNC_HOWTO + "). Mixing materials in one order is probable but not stated on its pages."),
        ("Tolerance", "ISO 2768-mK (medium) for the tray, lid and POM-C parts, ISO 2768-fH (fine) for the PMMA main key; the critical values are on the drawings",
         "Key openings +0.05/0 and the optic bore d10.1 +0.05/0 (FK-H-01), the lid's seat flat to 0.05 (FK-H-02: otherwise a gap shows along the facet edge), main key "
         "outline -0.03/-0.08 (FK-H-03); the kit frames ISO 2768-c."),
        ("Surface", "Tray and lid: bead blast + black anodize (combined option), NO marking. PMMA kit: polished (vapour or flame polish as FK-H-03; the frosted ring stays matte). "
         "POM-C kit: as machined",
         "JLCCNC lists machine and CNC polishing for acrylic; vapour or flame polish is not confirmed as an option (" + U_JLCNC_POLISH + "): ask, or polish at home."),
        ("Threads", "Tray: 4 x M1.6 x 0.35 (lid screws), 2 x M1.6 x 0.35 BLIND (key-board bosses), 1 x M1.6 x 0.35 from the head-block top into the laser bore (laser set screw, under the lid)",
         "The drawing asks for every thread (FK-H-01 note 3: tapped before anodizing, gauged after finishing). M1.6 is not listed on the capability page: ask in the quote chat. Fallback: order plain 1.25 mm holes and tap them by hand (sheet 'Tools'); the two key-board taps are blind and must not break through the floor (by hand: finish with a bottoming tap)."),
        ("Texture and grooves", "Panels 0.3 deep with a 90 deg V texture (0.2 deep, pitch 0.9) and transverse V grooves 0.3 deep (FK-H-01 sheet 2, FK-H-02)",
         "One 90 deg V engraving cutter, before blasting and anodising. Ask for it in the quote; if the shop will not cut it, the parts still fit and work (the texture is a "
         "priced option: 'texture_on' in section 2)."),
        ("Walls", wall_txt, wall_why),
        ("Kits", "PMMA kit %s, POM-C kit %s, each one solid piece with the parts on 0.6 mm tabs" % (dims(pmma_size), dims(pom_size)),
         "Above JLCCNC's 30 x 20 x 8 mm minimum for plastic parts. Ask whether the shop accepts parts on tabs; on arrival cut the tabs and file flush (the witnesses sit on hidden faces)."),
        ("Quantity / lead time", "Tray + lid: one set per light (order ONE set first and test-fit it). PMMA kit: ROUNDUP((lights + 1) / 3). POM-C kit: one per light. Resin mould: one per builder",
         "Standard lead time from 3 working days, quote within 24 h; more than 20 pieces goes to manual review."),
        ("Aluminium mould (option)", "Instead of the resin print: FlashKa_key_mould_cavity.step + FlashKa_key_mould_lid.step with FlashKa_key_mould.pdf (%s), aluminium 6061-T6, "
         "cavity half fine glass-bead blast, lid as machined, no anodising, 4 x M3 in the cavity half, cavities and parting faces +/-0.02" % ofd("3_rubber_keys"),
         "The chevron groove needs a 0.6 mm end mill (R0.3); 48 x 28 x 8 mm plates, above the 30 x 20 x 8 mm minimum of the instant quote."),
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
    risks = [
        "NO PUBLIC PRICES: JLCCNC publishes no per-part price and JLC3DP only a headline rate. Every price on this sheet is an ESTIMATE until the instant quotes; get the quotes first. "
        "The plastic parts follow the research ranges (PMMA key with polish $6-9, POM-C $5-8 per part type), the aluminium parts the model of sections 2-5.",
        "PLASTIC MINIMUM SIZE: the PMMA and POM-C parts are smaller than JLCCNC's 30 x 20 x 8 mm, which is why they are ordered as two machining kits. If a quote is refused anyway, "
        "any CNC shop that takes small parts can make the single files in %s (same geometry)." % ofd("2_JLCCNC"),
        "PMMA POLISH: drawing FK-H-03 asks for a vapour or flame polish on every face (the key is the light guide of the ring). If the shop cannot do it, order as machined and "
        "polish at home with abrasive paper and plastic polish (sheet 'Bought parts'); keep the frosted ring matte. Clean PMMA with water and mild soap only: solvents craze it.",
        "TEXTURE: the 0.2 mm panel texture needs an engraving pass; some quick-quote shops do not offer it. The parts work without it ('texture_on' = 0 prices the tray and lid "
        "without it); the STEP files carry it, so a shop that skips it must be told so in the quote.",
        "WALLS: every metal wall is at least 0.5 mm, JLCCNC's absolute minimum (drawing FK-H-01 note 7). Below the recommended 0.8 mm are only %s: name them in the "
        "quote chat. The 0.3 mm land on the lid's top face between a rear countersink and the lanyard-slot chamfer is an edge to break lightly, not a wall."
        % "; ".join("%s mm (%s)" % (v_, k_) for v_, k_ in thin_walls(H)),
        holddown_note(H),
        "FILES: upload exactly the files named in section 9 (sheet 'Ordering checklist', file map). JLCCNC pairs each drawing with its STEP file by the file name, so keep the names.",
        "ANODIZING THICKNESS: the drawings ask for type II black, 8-12 um (JLCCNC quotes 8-25 um as its range); it grows on every surface including the bores, the key openings and "
        "the threads. The drawings say: tolerances apply after finishing, threads are tapped before anodizing and gauged after it, and the optic bore floor (the LED board's heat "
        "path) stays flat - ask JLCCNC to confirm, and test-fit the first set before ordering 5.",
        "MOULD: once per builder. The resin print does not hold the +/-0.02 mm of the aluminium mould: try the first cast key in its opening (outline -0.05/-0.15, drawing "
        "FK-H-04) and sand the cavity floors with 400-grit paper for the matte key face; polish the chevron grooves once for a glossy chevron top "
        "(order_files/3_rubber_keys/README.txt). If the JLCCNC and JLC3DP parts do not merge into one order, the mould ships in its own parcel (one more shipping fee). "
        "A builder who has a mould leaves it out of the order.",
        "SET-UP COSTS: the set-ups and the anodizing lot fee are paid once per order, which is why 5 sets cost far less than 5 x the price of one set.",
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
GROUP_NAME = {"light": "every light", "mould": "casting mould (once)", "casting": "casting the side keys"}


def build_bought(book, bought):
    S = "Bought parts"
    s = Sh(book, S, [4, 34, 32, 62, 30, 11, 9, 10, 9, 10, 9, 11, 9, 11, 12, 52, 46, 20, 16])
    ws = s.ws
    s.put(1, 1, "Bought parts and consumables (not on the JLCPCB panel, not from JLCCNC / JLC3DP)", "title")
    s.merge(2, 1, 14, "Everything the PCB and housing orders do not contain: the 14500 cell with its nickel strip, the LED board, the TIR optic, the laser, screws (two M1.6 x "
            "2.5 pan-head screws for the key board), set screw, split ring, wire, thermal paste, tapes, foam, the two silicone hold-down pads, adhesives - and what you need "
            "to cast the two rubber side keys at home: the urethane rubber, black pigment, mould release, 0.3 mm stainless shim for the stiffeners, glue, cups, syringes "
            "and polishes, plus the M3 bolts, washers and nuts of the resin casting mould. Prices: the v0.5 items keep their AliExpress search-result prices of %s (item "
            "pages cannot be read automatically); the LED board, the TIR optic and the urethane rubber were read on %s, the cell and the nickel strip on %s; the other items "
            "are typical-price ESTIMATES (no listing read). Change the blue number when you see a real listing. 'Packs' = how many packs you must buy (rounded up): quantity "
            "needed = lights x 'per light' + 'fixed per order' (spares, one roll of tape, one sheet of pad material, one rubber kit...)." % (V05_DATE, CHECK_1000, CHECK_CELL))
    s.merge(3, 1, 14, "Prices exclude VAT and shipping here; both are added on sheet 'Hidden costs' (21 % VAT, shipping per parcel, EUR 3 flat duty per customs line). Column R says "
            "which parcel an item travels in: the casting supplies come from an EU shop, the TIR optics from an electronics distributor and the cell with its nickel strip "
            "from an EU battery shop (all three inside the EU: no customs), everything else from AliExpress / web shops.", "note")
    hr = 5
    s.head(hr, ["#", "Item", "Used for", "Exact spec that matters", "Search term (AliExpress / web shop)", "Price per pack (USD)", "Pack size", "Pack unit", "Per light",
                "Fixed per order", "Packs A", "Cost A (USD)", "Packs B", "Cost B (USD)", "Category", "Price basis (source, date)", "Link example", "Shop (parcel)", "Needed for"])
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
        s.put(r, 18, b["shop"], "text")
        s.put(r, 19, GROUP_NAME[b["grp"]], "text")
    r1 = r0 + len(bought) - 1
    r = r1 + 1
    s.put(r, 2, "Bought parts (the cell, LED board, TIR optic, laser, screws, set screw, ring, mould hardware)", "tot")
    for c in range(3, 20):
        s.put(r, c, None, "tot")
    s.put(r, 12, "=SUMIF($O$%d:$O$%d,\"Part\",L%d:L%d)" % (r0, r1, r0, r1), "tot", fmt=USD2, name="parts_A")
    s.put(r, 14, "=SUMIF($O$%d:$O$%d,\"Part\",N%d:N%d)" % (r0, r1, r0, r1), "tot", fmt=USD2, name="parts_B")
    r += 1
    s.put(r, 2, "Consumables (nickel strip, wire, thermal paste, tapes, foam, silicone pads, adhesives, casting supplies)", "tot")
    for c in range(3, 20):
        s.put(r, c, None, "tot")
    s.put(r, 12, "=SUMIF($O$%d:$O$%d,\"Consumable\",L%d:L%d)" % (r0, r1, r0, r1), "tot", fmt=USD2, name="cons_A")
    s.put(r, 14, "=SUMIF($O$%d:$O$%d,\"Consumable\",N%d:N%d)" % (r0, r1, r0, r1), "tot", fmt=USD2, name="cons_B")
    r += 1
    s.put(r, 2, "of which spares and left-over pack content (information)", "text")
    s.put(r, 12, "=SUM(L%d:L%d)-SUMPRODUCT(%s*I%d:I%d/G%d:G%d*F%d:F%d)" % (r0, r1, s.ref("lightsA"), r0, r1, r0, r1, r0, r1), "calc", fmt=USD2, name="bp_spare_A")
    s.put(r, 14, "=SUM(N%d:N%d)-SUMPRODUCT(%s*I%d:I%d/G%d:G%d*F%d:F%d)" % (r0, r1, s.ref("lightsB"), r0, r1, r0, r1, r0, r1), "calc", fmt=USD2, name="bp_spare_B")
    r += 1
    s.put(r, 2, "of which bought from the EU casting shop (one parcel inside the EU, sheet 'Hidden costs')", "text")
    s.put(r, 12, "=SUMIF($R$%d:$R$%d,\"%s\",L%d:L%d)" % (r0, r1, SHOP_EU, r0, r1), "calc", fmt=USD2, name="bp_eu_A")
    s.put(r, 14, "=SUMIF($R$%d:$R$%d,\"%s\",N%d:N%d)" % (r0, r1, SHOP_EU, r0, r1), "calc", fmt=USD2, name="bp_eu_B")
    r += 1
    s.put(r, 2, "of which bought from the electronics distributor (the TIR optics: one parcel inside the EU, sheet 'Hidden costs')", "text")
    s.put(r, 12, "=SUMIF($R$%d:$R$%d,\"%s\",L%d:L%d)" % (r0, r1, SHOP_OPTIC, r0, r1), "calc", fmt=USD2, name="bp_optic_A")
    s.put(r, 14, "=SUMIF($R$%d:$R$%d,\"%s\",N%d:N%d)" % (r0, r1, SHOP_OPTIC, r0, r1), "calc", fmt=USD2, name="bp_optic_B")
    r += 1
    s.put(r, 2, "of which bought from the EU battery shop (the cell and the nickel strip: one parcel inside the EU, sheet 'Hidden costs')", "text")
    s.put(r, 12, "=SUMIF($R$%d:$R$%d,\"%s\",L%d:L%d)" % (r0, r1, SHOP_CELL, r0, r1), "calc", fmt=USD2, name="bp_cell_A")
    s.put(r, 14, "=SUMIF($R$%d:$R$%d,\"%s\",N%d:N%d)" % (r0, r1, SHOP_CELL, r0, r1), "calc", fmt=USD2, name="bp_cell_B")
    r += 1
    s.put(r, 2, "of which casting supplies for the rubber side keys (information)", "text")
    s.put(r, 12, "=SUMIF($S$%d:$S$%d,\"%s\",L%d:L%d)" % (r0, r1, GROUP_NAME["casting"], r0, r1), "calc", fmt=USD2, name="bp_cast_A")
    s.put(r, 14, "=SUMIF($S$%d:$S$%d,\"%s\",N%d:N%d)" % (r0, r1, GROUP_NAME["casting"], r0, r1), "calc", fmt=USD2, name="bp_cast_B")
    # laser explanation
    r += 2
    s.merge(r, 1, 14, "Why the laser must be Class 2 (<= 1 mW)", "sub", border=True)
    laser = [
        "Laser classes (IEC/EN 60825-1) for visible light (400-700 nm): Class 1 = harmless in normal use; Class 2 = up to 1 mW continuous - safe for accidental exposure because the blink / aversion "
        "reflex (about 0.25 s) closes the eye before damage; Class 3R = up to 5 mW - low risk but a direct look into the beam can hurt, it is not meant for a keychain; Class 3B and 4 = dangerous. "
        "(" + U_LASER + ")",
        "This light is a keychain that people carry and use in public, so the module must be Class 2: 520 nm green at <= 1 mW. Green looks about five times brighter than red at the same power "
        "because the eye is most sensitive near 555 nm, so 1 mW green is already a clearly visible dot.",
        "Cheap modules sold as '1 mW' often emit several mW. v0.7 carries no marking: the Class 2 label (EN 60825-1) is printed in the manual and on the packaging. A light that you sell or give "
        "to other people needs the label on the light itself - then use the optional artwork %s (fibre-laser marking on the lid). The label is only true if the module really is <= 1 mW: "
        "buy from a seller that states a measured power, or measure it (optional laser power meter, sheet 'Tools'). A stronger module is not allowed in this design." % ofp("FlashKa_laser_label_lid_class2.dxf"),
        "For consumer laser products in the EU the standard EN 50689:2021 applies in addition (" + U_EN50689 + "). If you only build for yourself this is a recommendation; if you sell or give lights away, read it first.",
        "Always wear 520 nm safety glasses (sheet 'Tools') when the laser is powered on the bench, and never point it at people, animals, aircraft or vehicles.",
    ]
    for t in laser:
        r += 1
        s.merge(r, 1, 14, t, "text", border=True)
    r += 2
    s.merge(r, 1, 14, "Buying tips", "sub", border=True)
    tips = [
        "Search with the exact term in column E, sort by orders/rating, check the listed dimensions against the spec column, and read the reviews with photos. Ask the seller for the power measurement of the laser, the flux bin of the LED and the exact size of the LED board.",
        "Each seller ships its own parcel: 8 parcels mean 8 shipping fees and 8 x EUR 3 customs duty. Buy the small hardware (screws, rings, wire, paste, tapes, foam, silicone pads, epoxy, shim, glue) together in ONE EU web shop - see 'Hidden costs' for the saving.",
        "The cell and the nickel strip come from one EU battery shop, for example nkon.nl in the Netherlands (the shop the prices were read from; the cell ships by courier as dangerous goods). Ask whether the shop can weld tabs onto the cell; then no spot welder is needed. Any flat-top 14500 up to 14.5 x 50.4 mm fits the bay; the firmware's runtime estimate assumes an F15.",
        "The casting supplies (urethane rubber, pigment, release) come from one EU shop, for example kaupo.de in Germany (the shop the rubber price was read from). One 0.86 kg unit of ECON 80 casts many sets of keys: share it with other builders.",
        "The TIR optic comes in packs of 5 from an electronics distributor (RS, stock no. 186-2699). Below the distributor's free-shipping limit the courier fee is about EUR 15-20: order the optics for several lights at once, or together with other parts.",
        "Order the laser, the cell, the LED board and the optic FIRST (delivery 1-5 weeks), measure them with a caliper, and only then order the housing, so that a different part size does not waste a CNC order.",
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
    s.merge(2, 1, 12, "What you pay on top of the prices of the other sheets. JLCPCB ships one parcel; JLCCNC and JLC3DP ship one merged parcel (JLCCNC's 'merged ordering': one "
            "package, one shipping rate); the casting supplies come from an EU shop, the TIR optics from an electronics distributor and the cell with its nickel strip from "
            "an EU battery shop (three parcels from inside the EU: VAT only, no customs); every AliExpress seller ships its own parcel. For Lithuania (EU) each parcel from "
            "outside the EU gets VAT 21 %% and, since 1 July 2026, a flat EUR 3 customs duty per customs line (up to EUR 150), or formal customs clearance with a carrier "
            "fee above EUR 150. All inputs are blue; everything marked ESTIMATE has no public price (JLC shows shipping only in the cart). The rules were read on %s (v0.5 "
            "price check) and checked again on %s." % (V05_DATE, CHECK_1000))
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
    s.merge(r, 1, 12, "2. Shipping per parcel (USD, ESTIMATES - the JLC carts show the real 'Shipping Estimate' before you pay)", "sub", border=True)
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
        s.put(r, 2, ln, "in", fmt="0", name="pl_lines_%d" % i)
        s.put(r, 3, rate, "est", fmt=PCT1, name="pl_rate_%d" % i)
        if i != P_WEB:
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
        how = {P_JLCPCB: "Route = IOSS if goods per parcel <= EUR 150, otherwise formal clearance. IOSS: VAT on goods + shipping, flat duty per line. Formal: duty = rate x (goods + shipping), VAT on goods + shipping + duty, carrier fee = max(minimum, % of VAT + duty).",
               P_CNC: "Same rules for the merged JLCCNC + JLC3DP parcel (aluminium and plastic parts, the resin mould: two customs lines).",
               P_EU: "Inside the EU: no customs, no duty, no carrier fee; 21 % VAT on goods + shipping (conservative if the shop's price already includes VAT).",
               P_OPTIC: "Inside the EU (an EU site of the distributor): no customs; 21 % VAT on goods + shipping.",
               P_CELL: "Inside the EU (nkon.nl ships from the Netherlands): no customs; 21 % VAT on goods + shipping.",
               P_WEB: "Goods = bought parts + consumables without the casting supplies, the optics, the cell and the nickel strip; shipping and flat duty are paid for every parcel."}
        for i, (nm, _, _, _) in enumerate(PARCELS):
            r += 1
            s.put(r, 1, nm, "text")
            if i == P_JLCPCB:
                goods = "=" + s.ref("jlc_goods_" + sc)
            elif i == P_CNC:
                goods = "=" + s.ref("cnc_" + sc)
            elif i == P_EU:
                goods = "=" + s.ref("bp_eu_" + sc)
            elif i == P_OPTIC:
                goods = "=" + s.ref("bp_optic_" + sc)
            elif i == P_CELL:
                goods = "=" + s.ref("bp_cell_" + sc)
            else:
                goods = "=%s+%s-%s-%s-%s" % (s.ref("parts_" + sc), s.ref("cons_" + sc), s.ref("bp_eu_" + sc), s.ref("bp_optic_" + sc), s.ref("bp_cell_" + sc))
            s.put(r, 2, goods, "x", fmt=USD2, name="hc_goods_%s_%d" % (sc, i))
            s.put(r, 3, "=" + s.ref("pl_n_%d" % i), "calc", fmt="0")
            s.put(r, 4, "=B%d/C%d/%s" % (r, r, fx), "calc", fmt=EUR2, name="hc_per_eur_%s_%d" % (sc, i))
            if i in EU_PARCELS:
                s.put(r, 5, "EU", "calc", name="hc_route_%s_%d" % (sc, i))
            else:
                s.put(r, 5, "=IF(D%d>%s,\"formal\",\"IOSS\")" % (r, s.ref("ioss_eur")), "calc", name="hc_route_%s_%d" % (sc, i))
            ship = ("=" + s.ref("ship_%s_%d" % (sc, i))) if i != P_WEB else "=%s*C%d" % (s.ref("ali_ship"), r)
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
        s.put(r, 1, "Card / currency fee on the two JLC payments (JLCPCB, JLCCNC + JLC3DP)", "text")
        s.put(r, 10, "=%s*(J%d+J%d)" % (s.ref("card_pct"), first + P_JLCPCB, first + P_CNC), "calc", fmt=USD2, name="card_" + sc)
        r += 1
        s.put(r, 1, "Shipping + VAT + duty + carrier fees + card fee (to the Summary)", "tot")
        for c in range(2, 10):
            s.put(r, c, None, "tot")
        s.put(r, 10, "=F%d+G%d+H%d+I%d+J%d" % (rt, rt, rt, rt, r - 1), "tot", fmt=USD2, name="tax_other_" + sc)
        return first

    landed("A", "4. Landed cost per parcel - scenario A (one light)")
    landed("B", "5. Landed cost per parcel - scenario B (the lights of cell 'Scenario B' on sheet 'Summary', five by default)")
    # ---- 6. savings and reserves
    r += 2
    s.merge(r, 1, 12, "6. Savings and risk reserves (not in the totals)", "sub", border=True)
    r += 1
    s.put(r, 1, "Saving if the small hardware comes from ONE EU web shop (USD)", "text")
    s.put(r, 2, "=(%s-%s)*(%s+%s*%s*%s)" % (s.ref("ali_parcels"), s.ref("ali_parcels_consol"), s.ref("ali_ship"), s.ref("pl_lines_%d" % P_WEB), s.ref("flat_duty"), fx),
          "calc", fmt=USD2, name="consol_saving_A")
    s.merge(r, 3, 12, "Every avoided seller parcel saves its shipping and its flat EUR 3 customs duty. Look for an EU shop that sells M1.6 screws and set screws, split rings, PTFE wire, "
            "thermal paste, Kapton, foam, silicone sheet or pads, epoxy, stainless shim and cyanoacrylate (electronics and model-making shops).", "note")
    G0, S0 = s.ref("hc_goods_A_%d" % P_JLCPCB), s.ref("hc_ship_A_%d" % P_JLCPCB)
    r += 1
    s.put(r, 1, "EUR 150 cliff: JLCPCB parcel A if it is on the IOSS route (USD, landed)", "text")
    s.put(r, 2, "=%s+%s+%s*%s*%s+%s*(%s+%s)" % (G0, S0, s.ref("pl_lines_%d" % P_JLCPCB), s.ref("flat_duty"), fx, s.ref("vat"), G0, S0), "calc", fmt=USD2, name="route_ioss_A")
    s.merge(r, 3, 12, "Goods + shipping + flat EUR 3 per customs line + VAT on goods and shipping.", "note")
    r += 1
    s.put(r, 1, "EUR 150 cliff: JLCPCB parcel A if it is on the formal-clearance route (USD, landed)", "text")
    dd = "%s*(%s+%s)" % (s.ref("pl_rate_%d" % P_JLCPCB), G0, S0)
    vv = "%s*(%s+%s+%s)" % (s.ref("vat"), G0, S0, dd)
    s.put(r, 2, "=%s+%s+%s+%s+MAX(%s*%s,%s*(%s+%s))" % (G0, S0, dd, vv, s.ref("formal_fee_min"), fx, s.ref("formal_fee_pct"), dd, vv), "calc", fmt=USD2, name="route_formal_A")
    s.merge(r, 3, 12, "Goods + shipping + tariff + VAT on goods, shipping and tariff + carrier disbursement fee (minimum EUR 15).", "note")
    r += 1
    s.put(r, 1, "EUR 150 cliff: formal route minus IOSS route (USD)", "bold")
    s.put(r, 2, "=B%d-B%d" % (r - 1, r - 2), "calc", fmt=USD2, name="route_diff_A")
    s.merge(r, 3, 12, "What the JLCPCB order would save if it were below EUR 150. It is far above the line (the panel and its assembly), so it stays on the formal route; the "
            "merged JLCCNC + JLC3DP order of one light is below the line (its route is in section 4).", "note")
    r += 1
    s.put(r, 1, "Risk reserve: second PCB + assembly order after a first-article problem (USD)", "text")
    s.put(r, 2, "=%s*%s" % (s.ref("risk_pcb_f"), s.ref("hc_landed_A_%d" % P_JLCPCB)), "calc", fmt=USD2, name="risk_pcb")
    s.merge(r, 3, 12, "A new board design almost never works perfectly the first time (wrong footprint, rotation, missing pull-up) - and the key board, the pogo contact and the "
            "1000 lm power stage are new in v0.7. The second order costs the same JLCPCB order again, with shipping and tax. The 3 spare bare panels of the first order can be "
            "re-assembled by hand, which saves the panel price but not the assembly.", "note")
    r += 1
    s.put(r, 1, "Risk reserve: second housing order (USD)", "text")
    s.put(r, 2, "=%s*%s" % (s.ref("risk_house_f"), s.ref("hc_landed_A_%d" % P_CNC)), "calc", fmt=USD2, name="risk_house")
    s.merge(r, 3, 12, "If the first tray does not fit the real laser / cell / optic, or a kit is refused and has to be re-ordered elsewhere. Reduce the risk by measuring the delivered "
            "parts before the order and ordering ONE set first.", "note")
    # ---- 7. list of hidden costs
    r += 2
    s.merge(r, 1, 12, "7. The costs people forget (amounts for scenario A and B where they are in the totals)", "sub", border=True)
    r += 1
    s.put(r, 1, "Cost", "head")
    s.put(r, 2, "A (USD)", "head")
    s.put(r, 3, "B (USD)", "head")
    s.merge(r, 4, 12, "What it is and what to do", "head", border=True)
    ci = next((i for i, t in enumerate(tools) if t[0].startswith("USB-C data cable")), None)
    singles = [P_JLCPCB, P_CNC, P_EU, P_OPTIC, P_CELL]
    rows = [
        ("Shipping of the JLCPCB parcel, the merged JLCCNC + JLC3DP parcel, the EU casting-shop parcel, the optic distributor's parcel and the battery shop's parcel",
         "=" + "+".join(s.ref("hc_ship_A_%d" % i) for i in singles), "=" + "+".join(s.ref("hc_ship_B_%d" % i) for i in singles),
         "JLCPCB and JLCCNC ship separately (JLCCNC merges only with JLC3DP), two shipping fees; the EU casting shop, the distributor and the battery shop three more (the "
         "cell travels as dangerous goods by courier). JLC publishes no rate table; anchors: "
         "DHL Express about $21.50, EuroPacket about $6.50, Global Standard Direct Line about $1.50 for a small parcel (" + U_CHIP + ", June 2025), FedEx about $16 to Spain "
         "(" + U_EEV + ", 2024). Economy takes weeks and may be slow at customs: use express for the first order."),
        ("EU VAT 21 % (Lithuania)", "=" + s.ref("hc_sum_vat_A"), "=" + s.ref("hc_sum_vat_B"),
         "VAT is charged on goods + shipping. Up to EUR 150 per parcel JLC collects it at checkout (IOSS, " + U_VAT + "); above EUR 150 you pay VAT and customs fees to the carrier (or at checkout with DDP)."),
        ("Customs duty + carrier handling fees", "=%s+%s" % (s.ref("hc_sum_duty_A"), s.ref("hc_sum_fee_A")), "=%s+%s" % (s.ref("hc_sum_duty_B"), s.ref("hc_sum_fee_B")),
         "Since 1 July 2026 every low-value parcel pays a flat EUR 3 duty per customs line (" + U_EC + "; JLC FAQ " + U_CUST + "); under IOSS JLC collects the VAT but not the EUR 3, "
         "which is paid at import unless the channel is DDP. Above EUR 150 the normal tariff and formal clearance apply and the carrier adds a disbursement fee (DHL Germany 2 % min "
         "EUR 15, UPS 3 % min EUR 15.70, FedEx 2.5 % min EUR 15; UPS Lithuania 2 % min EUR 12). A unified EU handling fee (about EUR 2 per parcel) is planned from about Nov 2026 and is not included."),
        ("THE EUR 150 CLIFF: JLCPCB order", "=" + s.ref("jlc_line_gap_A"), "=" + s.ref("jlc_line_gap_B"),
         "EUR left until the JLCPCB order passes the IOSS limit (negative = already above: formal clearance, a carrier fee of about EUR 15). The panel and its assembly cost far more "
         "than EUR 150, so this parcel cannot stay below the line."),
        ("THE EUR 150 CLIFF: JLCCNC + JLC3DP order", "=" + s.ref("cnc_line_gap_A"), "=" + s.ref("cnc_line_gap_B"),
         "EUR left until the merged housing order passes the IOSS limit. For one light it stays below the line (VAT and EUR 3 per customs line only: no 6 % duty, no carrier "
         "fee); a real quote that is much higher can push it over. For two or more lights it is above the line; splitting it into two parcels below the line only pays with "
         "economy shipping (docs/bom_notes.md, section 2)."),
        ("AliExpress / web shops: shipping + flat duty", "=%s+%s" % (s.ref("hc_ship_A_%d" % P_WEB), s.ref("hc_duty_A_%d" % P_WEB)),
         "=%s+%s" % (s.ref("hc_ship_B_%d" % P_WEB), s.ref("hc_duty_B_%d" % P_WEB)),
         "Each seller parcel pays its own shipping and its own EUR 3 duty. See the saving in section 6."),
        ("Card / currency conversion fee", "=" + s.ref("card_A"), "=" + s.ref("card_B"),
         "JLC charges in USD. Your bank may add a conversion fee; use a card without one if you can."),
        ("Spares already inside the totals: pieces JLC buys for placement loss", "=" + s.ref("extra_cost_A"), "=" + s.ref("extra_cost_B"),
         "JLC buys a few more resistors, capacitors, chips and pogo pins than the panels need (lost by the placement machine). You pay for them but do not receive them."),
        ("Spares already inside the totals: bought parts and left-over packs", "=" + s.ref("bp_spare_A"), "=" + s.ref("bp_spare_B"),
         "The spare cell, the rest of the nickel strip, the second LED board, the other optics of the pack of 5, extra screws (you WILL lose an M1.6 screw), left-over pad "
         "and foam sheets, most of the rubber (one unit casts "
         "many keys). (The spare main key comes in the PMMA kit and the spare lid insert in the POM-C kit, both inside the housing total; two of the four keys of each pour are spares.)"),
        ("First-article risk: second PCB + assembly order (NOT in the totals)", "=" + s.ref("risk_pcb"), None,
         "Budget for it. If a fix is needed, the same fees (set-up, stencil, feeder loading, panel fee) are paid again."),
        ("First-article risk: second housing order (NOT in the totals)", "=" + s.ref("risk_house"), None, "See section 6."),
        ("USB-C DATA cable (in Tools, NOT in the per-light cost)", ("=" + s.ref("tool_cost_%d" % ci)) if ci is not None else None, None,
         "Needed to charge the light and update its firmware. A charge-only cable does not work for data. You only pay if you do not have one."),
        ("Price changes between now and your order", None, None,
         "LCSC prices and stock change weekly; JLC re-prices in the cart. Re-open the LCSC links in sheet '%s' and watch for red lines in the JLC BOM upload." % BOM_SHEET),
        ("Your time and mistakes", None, None,
         "Not counted: casting and trimming the side keys, soldering the wires, assembling the housing, testing, waiting 1-5 weeks for parcels."),
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
    s.merge(2, 1, 10, "JLCPCB solders all SMD parts, so you do NOT need a hot-air station, solder paste or a reflow oven. You solder a few wires by hand (cell strips, LED, laser), "
            "weld two nickel strips onto the cell (or buy it with welded tabs), screw the housing together, cut two small silicone pads and the foam for the cell and - new in "
            "v0.7 - cast the two rubber side keys and cut their stainless stiffeners (vice, tin snips, needle files; "
            "the default urethane is mixed 1:1 by volume, so the scale is only needed for PMC-780 DRY). Prices are typical 2026 web-shop prices (ESTIMATES, USD, excl. VAT and "
            "shipping). 'Needed' = 1 counts the tool in the Summary, 0 = optional, not counted. If you already own a tool, set its 'Needed' to 0.")
    hr = 4
    s.head(hr, ["#", "Tool", "Why you need it", "Spec that matters", "Search term", "Price each (USD)", "Qty", "Needed (1/0)", "Cost (USD)", "Basis"])
    ws.row_dimensions[hr].height = 30
    r0 = hr + 1
    for i, (nm, why, spec, search, price, qty, need, first) in enumerate(tools):
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
        s.put(r, 10, "ESTIMATE (typical price; first priced %s%s)" % (first, ", added in v0.7" if first in (CHECK, CHECK_CELL) else (", added in v0.6" if first == V06_CHECK else "")), "text")
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
def check_refs(lines):
    """Designators to look at in the JLC placement preview: chips, transistors, the USB-C socket, switches, LEDs and pogo pins."""
    refs = sorted((r for l in lines for r in l["refs"] if re.match(r"(U|Q|SW|LED|P)\d+$", r) or r == "J1"), key=refkey)
    main = [r for r in refs if next(c for c in COMPONENTS if c["ref"] == r).get("board") == "main"]
    keys = [r for r in refs if r not in main]
    return main, keys


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
    pv_main, pv_keys = check_refs(lines)

    def folder_list(folder):
        return "%s (%s)" % (ofd(folder), ", ".join(n for f, n, _ in ORDER_FILES if f == folder))
    steps = [
        ("0", "Today", "Your computer", "Nothing yet: update the prices.",
         "Open the LCSC links in sheet '%s' (column E) and check the stock note column. Read sheet 'Summary' and change the blue cells you know better." % BOM_SHEET,
         "1 hour", "Is every line still in stock? Low retail stock at LCSC (read on the dates in sheet '%s'): " % BOM_SHEET
         + ", ".join(l["lcsc"] for l in lines if l["stock"] is not None and l["stock"] < 1000)
         + "; stock NOT read (pages not readable): " + ", ".join(l["lcsc"] for l in lines if l["stock"] is None) + " (see the stock notes).", None),
        ("1", "Day 1", "AliExpress / EU web shop", "Bought parts: LED board SST-20 Gen 2 10 mm (+1 spare, for example Kaidomain), laser module Class 2 (+ read its "
         "measured power), lid screws M1.6 x 6 and key-board screws M1.6 x 2.5, set screws, split rings, 24 AWG wire, thermal paste, Kapton tape, 0.5 mm foam sheet, "
         "silicone pad sheets (thermal gap pad 1.5 mm, rubber sheet 1.0 mm Shore A 70), silicone adhesive, epoxy, 0.3 mm stainless shim, cyanoacrylate, cups and syringes, "
         "polishes; once per builder the four M3 x 16 bolts, washers and nuts of the resin mould.",
         "Sheet 'Bought parts': search term, spec and link example for every item. Buy the small hardware from ONE web shop to save parcels.",
         "1-5 weeks (AliExpress), 3-7 days (EU shop)", "Size of the LED board (10 mm, SST-20 Gen 2) in the listing; laser power stated; screw lengths (6 mm for the lid, "
         "2.5 mm, not longer, for the key board); shipping to Lithuania included; VAT shown.", "web"),
        ("1b", "Day 1", "Electronics distributor (RS / Distrelec)", "TIR optics: LEDiL LISA3-RS-PIN (FP16558), one pack of 5 (RS stock no. 186-2699) - enough for 4 lights "
         "with a spare.", "Sheet 'Bought parts', row 'TIR optic'. Not the clip version (7.9 mm high).", "3-7 days",
         "The part number ends in -RS-PIN; the free-shipping limit of the shop (combine orders).", "optic"),
        ("1c", "Day 1", "EU casting shop (for example kaupo.de)", "Casting supplies, once per builder: urethane rubber Smooth-On ECON 80 (0.86 kg trial unit), black pigment "
         "SO-Strong, Universal Mold Release.",
         "Sheet 'Bought parts' (rows with shop '%s'). Read the technical bulletin and the safety data sheet of the rubber before you buy." % SHOP_EU,
         "3-7 days", "Shore 80A, mix ratio 1A:1B by volume; the shop may sell to registered customers only.", "eu"),
        ("1d", "Day 1", "EU battery shop (for example nkon.nl)", "One Vapcell INR14500 F15 per light + 1 spare, and 1 m of pure nickel strip 0.2 x 5 mm (or the cell with "
         "welded tabs, if the shop offers it).", "Sheet 'Bought parts', rows 'Li-ion cell' and 'Nickel strip'. Without welded tabs you need a spot welder (sheet 'Tools').",
         "3-7 days", "Flat top, no protection board, 14.0 x 49.0 mm (any flat-top 14500 up to 14.5 x 50.4 mm fits); pure nickel, not nickel-plated steel.", "cell"),
        ("2", "Day 1", "Your computer", "Check the order files of the package (nothing has to be generated).",
         "Ready to upload: %s; %s; %s. Only after a change of the design: re-run tools/kicad/build_all.py (re-routes both boards, takes long; writes production/) or the housing "
         "build, and replace the files in order_files/." % (folder_list("1_JLCPCB"), folder_list("2_JLCCNC"), folder_list("3_rubber_keys")),
         "10 minutes", "%s must have %d lines and %d parts; its LCSC numbers are exactly column E of sheet '%s'." % (ofp("BOM_JLCPCB.csv"), nlines, sum(l["qty"] for l in lines), BOM_SHEET), None),
        ("3", "Day 1-2", "jlcpcb.com", "5 bare panels + PCB assembly (Standard PCBA, both sides) of 2 panels (one light) or 5 panels. Each panel holds the key board and the main PCB.",
         "Gerber: %s. Settings: 4 layers, 0.8 mm, ENIG, BLACK solder mask, white silkscreen, Panel by Customer 1 x 1, Different design 2, qty 5, PCB Assembly ON, both sides, qty 2 or 5, "
         "confirm parts placement. Then upload %s and %s (see sheet 'JLCPCB order', section 1)." % (ofp("FlashKa_panel_gerbers.zip"), ofp("BOM_JLCPCB.csv"), ofp("CPL_JLCPCB.csv")),
         "PCB 3-5 days + assembly 3-5 days + express shipping 3-5 days = about 2 weeks (the cart shows the exact build time)",
         "All BOM lines matched; stock of the pogo pins C22100007 and of the power-stage parts C139643, C351410, C238645; part rotation and pin 1 in the placement preview "
         "(main PCB: %s; key board: %s); shipping DDP. The order is far above EUR 150: formal clearance with a carrier fee." % (", ".join(pv_main), ", ".join(pv_keys)), "jlcpcb"),
        ("4", "when the laser, the cell and the optic have arrived", "Your desk", "Measure the delivered parts with a caliper.",
         "Laser body 6.0 mm x 12 mm; cell 14.0 x 49.0 mm (the bay takes up to 14.5 x 50.4 mm); LED board 10.0 mm; optic 10.0 mm x 6.9 mm. Check the laser power if you "
         "have a meter.",
         "30 minutes", "Everything fits the spec of sheet 'Bought parts'; otherwise change the housing BEFORE ordering it.", None),
        ("5", "after step 4", "jlccnc.com (one merged order with jlc3dp.com)", "Tray + lid, aluminium 6061-T6, bead blast + black anodize, NO marking; the PMMA kit (3 clear "
         "main keys, ROUNDUP((lights + 1) / 3) kits); the POM-C kit (one per light); once per builder the two resin plates of the casting mould (JLC3DP, SLA).",
         "Files from %s: FlashKa_tray.step + FlashKa_tray.pdf, FlashKa_lid.step + FlashKa_lid.pdf, FlashKa_pmma_kit.step + FlashKa_pmma_kit.pdf, FlashKa_pom_kit.step + FlashKa_pom_kit.pdf "
         "(each drawing PDF has the SAME name as its STEP file); to JLC3DP from %s: FlashKa_key_mould_resin_cavity.stl + FlashKa_key_mould_resin_lid.stl. Put both into ONE merged "
         "order (cart: 'All'). Settings: see sheet 'Housing', section 9. Order ONE set first. (Aluminium mould instead: FlashKa_key_mould_cavity.step + FlashKa_key_mould_lid.step "
         "+ FlashKa_key_mould.pdf to JLCCNC.)" % (ofd("2_JLCCNC"), ofd("3_rubber_keys")),
         "Quote within 24 h, 3 working days + 1 day transfer + shipping 3-6 days = about 10-12 days",
         "Instant quote prices -> type them in sheet 'Housing' (sections 6, 6b and 7); M1.6 threads accepted (two of them blind); anodize tolerance note; the kits accepted with the parts on tabs; "
         "PMMA polish option (or polish at home); the texture (or 'texture_on' = 0 and a note to skip it); one light stays below EUR 150.", "jlccnc"),
        ("6", "when the mould and the casting supplies are there", "At home", "Cast the two rubber side keys (4 per pour: 2 + 2 spares) and glue in the stiffeners.",
         "Steps in %s and in the build guide: sand the cavity floors with 400-grit paper and polish the chevron grooves once, release, mix 5 ml A + 5 ml B with the pigment, "
         "pour, close with the four M3 bolts, cure overnight (24 h), demould, trim. Cut the plate 3.6 x 9.4 mm and the doubler 2.0 x 2.0 mm from the 0.3 mm shim and glue them "
         "in with cyanoacrylate." % (ofd("3_rubber_keys") + "README.txt"),
         "1 hour + 24 h cure", "Key face without bubbles, chevron complete; the first key fits its opening in the tray; the plate lies flat in its recess.", None),
        ("7", "when everything is there", "At home", "Inspect, assemble, test.",
         "Check every delivery against this list. Cut the PMMA keys and the POM-C parts off their kits (flush cutters) and file the stubs flat; cut the two silicone pads to size "
         "(%.1f x %.1f mm and %.1f x %.1f mm) and stick them on the lid bosses with a drop of silicone adhesive. LED board on thermal paste and the TIR optic (pins cut off) into the "
         "head bore, glued with epoxy. Fit the three keys into the floor, screw the key board onto its two bosses (M1.6 x 2.5), put the antenna spacer in, then fit the main PCB "
         "(it rests on the six pogo pins). Weld the nickel strips to the cell (or use a cell with welded tabs), solder one 24 AWG wire to each strip and to J2 (BAT+, BAT-), "
         "the LED wires to J3 and the laser to J5; tape the strips and joints; check for shorts with the multimeter BEFORE the cell goes in; pick the foam stacks for the "
         "cell; wear laser glasses when the laser is on." % (PAD_CAN_MM + PAD_FRONT_MM),
         "1-2 evenings", "Multimeter: no short between BAT+ and BAT- or GND; the cell between 3.0 and 4.2 V (new cells arrive at about 3.6 V); every key clicks and the ring "
         "lights; the installer offers 'FlashKa v0.7'.", None),
        ("8", "after the first light works", "-", "Order the other lights (scenario B).",
         "The one-time costs (set-ups, stencil, panel fee, anodizing lot, the mould, the casting supplies) are already paid, so every additional light costs much less (see 'Summary', "
         "extra cost per additional light).",
         "-", "Keep the first light as the reference for the next batch.", None),
    ]
    r = hr
    pidx = {"jlcpcb": P_JLCPCB, "jlccnc": P_CNC, "eu": P_EU, "optic": P_OPTIC, "cell": P_CELL, "web": P_WEB}
    for stp, when, shop, what, files, lead, chk, ck in steps:
        r += 1
        s.put(r, 1, stp, "bold")
        s.put(r, 2, when, "text")
        s.put(r, 3, shop, "text")
        s.put(r, 4, what, "text")
        s.put(r, 5, files, "text")
        s.put(r, 6, lead, "text")
        s.put(r, 7, chk, "text")
        for c, sc in ((8, "A"), (9, "B")):
            f = ("=" + s.ref("hc_landed_%s_%d" % (sc, pidx[ck]))) if ck else None
            s.put(r, c, f, "x" if f else "text", fmt=USD2)
    r += 1
    s.put(r, 3, "Total of the checkout charges (without the card fee)", "tot")
    for c in range(1, 10):
        if c != 3:
            s.put(r, c, None, "tot")
    s.put(r, 8, "=SUM(H%d:H%d)" % (hr + 1, r - 1), "tot", fmt=USD2, name="chk_total_A")
    s.put(r, 9, "=SUM(I%d:I%d)" % (hr + 1, r - 1), "tot", fmt=USD2, name="chk_total_B")
    r += 2
    s.merge(r, 1, 9, "File map", "sub", border=True)
    fm = [("JLCPCB", "%s: FlashKa_panel_gerbers.zip, BOM_JLCPCB.csv, CPL_JLCPCB.csv  (the panel files tools/kicad/build_all.py writes to production/; production/ also holds the "
                     "single-board files FlashKa_main_gerbers.zip and FlashKa_keys_gerbers.zip with their BOM and CPL files, a fall-back only)" % ofd("1_JLCPCB")),
          ("JLCCNC", "%s: FlashKa_tray, FlashKa_lid, FlashKa_pmma_kit, FlashKa_pom_kit (each as .step + .pdf; the PDFs are the drawings from cad/ renamed to the STEP names). "
                     "Single parts for shops that take small parts: FlashKa_key_main (.step + .pdf), FlashKa_rf_window.step, FlashKa_antenna_spacer.step (drawing "
                     "FlashKa_pom_parts.pdf); FlashKa_laser_sleeve.step only for a laser module thinner than 6 mm. The mould files are in %s." % (ofd("2_JLCCNC"), ofd("3_rubber_keys"))),
          ("Rubber keys", "%s: FlashKa_key_mould_resin_cavity.stl + FlashKa_key_mould_resin_lid.stl (to JLC3DP, once, in the merged JLCCNC order; FlashKa_key_mould_resin.step "
                          "is the closed resin mould for reference); the aluminium option FlashKa_key_mould_cavity.step + FlashKa_key_mould_lid.step (to JLCCNC) with "
                          "FlashKa_key_mould.step (closed, reference); FlashKa_key_mould.pdf (drawing of both moulds); FlashKa_key_side.step + FlashKa_key_side.pdf, "
                          "FlashKa_key_stiffener.step, FlashKa_key_side_with_plate.step and README.txt (casting at home)." % ofd("3_rubber_keys")),
          ("Optional", "%s: FlashKa_laser_label_lid_class2.dxf (+ .png preview) - only for a light that is sold or given to other people (laser label on the lid)." % ofd("optional_laser_label")),
          ("Nowhere", "Upload only the files of order_files/. cad/ and production/ hold their sources; kicad/* and tools/* are for checking and re-building, not for ordering. "
                      "The firmware is FlashKa firmware 0.7.0, built for the v0.7 board: choose 'FlashKa v0.7' in the web installer.")]
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
def xray_fee(parts):
    """JLCPCB X-ray fee for this many inspected parts (tier price x parts)."""
    if parts <= 0:
        return 0.0
    n = sum(1 for q, _ in XRAY_TIERS if q <= parts)
    return parts * XRAY_TIERS[max(1, n) - 1][1]


def money(x, sign=False):
    return "%s$%s" % ("-" if x < 0 else ("+" if sign and x > 0 else ""), format(abs(x), ",.2f"))


def first_layout_texts(cp, lines, la):
    """{group: text} for the 'what changed since the first v0.7 layout' table (scenario A numbers, computed from the model cp)."""
    v = {k: x["v"] for k, x in P.items()}
    bp = {b["id"]: b for b in BOUGHT}
    opt = {b["id"]: b for b in BOUGHT_OPTIONS}
    old = V07R_DETAIL[1]
    boards = max(la, v["min_asm"])

    x_old, x_new = xray_fee(3 * boards), xray_fee(v["xray_per_board"] * boards)

    def unit(lcsc):
        return next(l for l in lines if l["lcsc"] == lcsc)["tiers"][0][1]
    cast_old = old["cast"]
    return {
        "pcb": "No saving here: the 1000 lm power stage is new. The 4 A buck TPS62095 costs %s per board (the TLV62585 it replaces cost $0.26), the protection IC DW01A "
               "%s and the dual MOSFET SE8830A %s (ESTIMATE), plus five small parts; U2 is a QFN, so X-ray counts 4 parts per panel instead of 3 (%s instead of %s for %d "
               "panels). The cheaper pogo pin is an option (table below)."
               % (money(unit("C139643")), money(unit("C351410")), money(unit("C238645")), money(x_new), money(x_old), boards),
        "house": "Resin casting mould from JLC3DP (%s, ESTIMATE) instead of the aluminium mould (%s): %s less, once per builder. The POM-C kit lost the LED spacer ring "
                 "(one part type less: %s instead of %s for the kits). The body is 4.8 mm longer (for the optic and the cell) and an octagon 20 x 18 mm instead of a "
                 "20 x 16 mm rectangle (tray + lid %s instead of %s). Quality: the resin print does not hold the aluminium mould's +/-0.02 mm (try the first key in its "
                 "opening) and wears out sooner; the aluminium mould stays an option."
                 % (money(cp["mould_A"]), money(old["mould"]), money(old["mould"] - cp["mould_A"]), money(cp["kit_A"]), money(old["kit"]), money(cp["alu_A"]), money(old["alu"])),
        "parts": "LED board %s instead of $5.40 (SST-20 Gen 2, Kaidomain, read); no glass window ($2.95 per 5). New: the TIR optic (%s per pack of 5); one 14500 cell "
                 "(Vapcell F15, %s at nkon.nl, read) instead of two 400 mAh cells with protection boards ($4.50 each); the resin mould's bolts, washers and nuts (%s) "
                 "instead of the aluminium mould's dowel pins and screws (%s)."
                 % (money(bp["led"]["price"]), money(bp["optic"]["price"]), money(bp["cell"]["price"]), money(bp["m3set"]["price"]),
                    money(opt["dowel"]["price"] + opt["m3x12"]["price"])),
        "cons": "ECON 80 urethane (%s for 0.86 kg) instead of PMC-780 DRY ($60.40 for 1.36 kg): the same Shore 80A, mixed 1:1 by volume, so the 0.01 g scale is no longer "
                "needed; casting supplies %s instead of %s. Thermal paste instead of thermal tape, 24 AWG wire for the 3 A paths, nickel strip for the cell (%s per metre), "
                "0.5 mm foam sheet. Quality: none - ECON 80 meets the 75-85 Shore A of the drawing; its pot life is 13 minutes instead of 25 (pour without delay)."
                % (money(bp["rubber"]["price"]), money(cp["bp_cast_A"]), money(cast_old), money(bp["nickel"]["price"])),
        "tax": "The merged JLCCNC + JLC3DP order of one light is EUR %.2f, below the EUR 150 line (the first layout: EUR 151.20 with the aluminium mould, so 6 %% duty, VAT and "
               "a carrier fee of about EUR 15); %d web-shop parcels instead of 10 (no glass window; the cell comes from an EU shop). New: the optic distributor's parcel "
               "and the battery shop's parcel (ESTIMATE %s and %s shipping, VAT only). Duty and carrier fees %s instead of %s, VAT %s instead of %s, shipping %s instead of %s."
               % (cp["cnc_A"] / v["fx"], v["ali_parcels"], money(SHIPPING[P_OPTIC][2]), money(SHIPPING[P_CELL][2]), money(cp["sum_duty_A"]), money(old["duty"]),
                  money(cp["sum_vat_A"]), money(old["vat"]), money(cp["sum_ship_A"]), money(old["ship"])),
    }


def cell_change_texts(cp, lines, la):
    """{group: text} for the 'what the battery and body change costs' table (scenario A numbers, computed from the model cp)."""
    v = {k: x["v"] for k, x in P.items()}
    bp = {b["id"]: b for b in BOUGHT}
    old = V07P_DETAIL[1]
    tools_now = sum(t[4] * t[5] * t[6] for t in TOOLS)
    welder = sum(t[4] * t[5] * t[6] for t in TOOLS if t[0].startswith("Small spot welder"))
    cell = bp["cell"]
    cells_now = ceil_div(la * cell["per_light"] + cell["per_order"], cell["pack"]) * cell["price"]
    r3 = next(l for l in lines if l["lcsc"] == "C4109")
    return {
        "pcb": "R3 is 2.0 k (C4109, %s each from 100 pieces) instead of 3.3 k (C25890, $0.0036): the charger gives about 494 mA instead of 280 mA (a full charge in about "
               "3.5 h). The same %d lines and %d parts per panel: the fees do not change." % ("$%.4f" % r3["tiers"][0][1], len(lines), sum(l["qty"] for l in lines)),
        "house": "Tray + lid %s instead of %s: the section is 2 mm taller (20 x 18 mm octagon), the lid a 3.4 mm cap (%.2f mm tall with its bosses) instead of a 1.5 mm "
                 "plate, plus the diagonal facets and the cap pocket (sheet 'Housing', section 4). The kits (%s) and the resin mould cost the same."
                 % (money(cp["alu_A"]), money(old["alu"]), LID_HEIGHT_MM, money(cp["kit_A"])),
        "parts": "One Vapcell INR14500 F15 (%s at nkon.nl, read %s) instead of two 320 mAh pouch cells (ESTIMATE $%.2f each: no public price), each with one spare: %s "
                 "instead of %s for one light. The longer lid screws (M1.6 x 6) are priced like the old ones."
                 % (money(cell["price"]), CHECK_CELL, old["cell_each"], money(cells_now), money(old["cells"])),
        "cons": "New: 1 m of pure nickel strip for the two tabs (%s, read); the foam is now 0.5 mm sheet (same ESTIMATE). Without welded tabs on the cell you also need a "
                "small spot welder: tools %s instead of %s (+%s, not in the per-light cost; 0 with a pre-tabbed cell)."
                % (money(bp["nickel"]["price"]), money(tools_now), money(old["tools"]), money(welder)),
        "tax": "The cell and the strip come in their own parcel from an EU battery shop (ESTIMATE %s shipping + 21 %% VAT, no duty) instead of one of the web-shop parcels "
               "(%d instead of %d, each $%.2f shipping + EUR 3 duty). Shipping %s instead of %s, VAT %s instead of %s, duty and carrier fees %s instead of %s."
               % (money(SHIPPING[P_CELL][2]), v["ali_parcels"], old["parcels"], v["ali_ship"], money(cp["sum_ship_A"]), money(old["ship"]), money(cp["sum_vat_A"]),
                  money(old["vat"]), money(cp["sum_duty_A"]), money(old["duty"])),
    }


def build_summary(book, lines, cp0=None, opts=None, cp2=None):
    S = "Summary"
    s = Sh(book, S, [58, 14, 14, 14, 14, 14, 14, 14, 14, 11, 64])
    ws = s.ws
    s.put(1, 1, "FlashKa Keychain v0.7 - what it really costs", "title")
    s.merge(2, 1, 11, "Complete cost of building the light from scratch: electronics (one JLCPCB panel: main PCB + key board), housing (JLCCNC: aluminium tray + lid, a PMMA kit with the "
            "main keys, a POM-C kit; JLC3DP, in the same order: the resin casting mould for the rubber side keys, once per builder), bought parts (the 14500 cell, LED board, "
            "TIR optic, laser, screws), consumables (including the nickel strip and the casting supplies), shipping, EU VAT and customs for Lithuania. Scenario A = you build "
            "ONE light (JLCPCB still sells 5 bare panels and assembles at least 2), scenario B = you build FIVE (type 2 in B to see two lights). Prices that did not change keep "
            "the date they were read (%s for v0.5, %s for v0.6, %s for the first v0.7 layout); the parts of the 1000 lm power stage were read on %s, the cell, the nickel strip "
            "and R3 on %s. Blue on amber cells are ESTIMATES because the shop shows its price only after you upload the files (or no listing was read) - replace them with the "
            "real quote." % (V05_DATE, V06_CHECK, CHECK, CHECK_1000, CHECK_CELL))
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
    s.put(r, 1, "Price check date (v0.7)", "text")
    s.put(r, 2, CHECK_CELL, "in")
    s.merge(r, 3, 11, "One-cell layout (%s): the Vapcell F15 cell and the nickel strip (nkon.nl), R3 (C4109, LCSC) and the Vapcell K10 (illumn.com) were read on this date; "
            "nkon's shipping rate could not be read (ESTIMATE). 1000 lm power stage (%s): the buck TPS62095 and the protection IC DW01A (LCSC), the LED board, the TIR optic, "
            "the ECON 80 urethane, Sugru, JLC3DP's resin rate, JLCCNC's merged ordering and the EU customs rules; the page of the MOSFET SE8830A could not be read (ESTIMATE). "
            "First v0.7 check (%s): the pogo pin, the JLCPCB panel fee for two designs, JLCCNC's minimum size for plastic parts. Prices and fees that did not change keep the "
            "date they were read: %s (v0.5 check; LCSC and JLC pages) and %s (v0.6; the pages of C115357 and C25104 could not be read, those lines are ESTIMATES). Re-check "
            "before ordering." % (CHECK_CELL, CHECK_1000, CHECK, V05_DATE, V06_CHECK), "note")
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

    def line(key, label, fa, fb, kind="text", basis="", namea=None, nameb=None):
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
    n_est = [l["lcsc"] for l in lines if l["est"]]
    line("pcb", "1. PCB + assembly (JLCPCB, one panel: main PCB + key board)", "=" + g("jlc_goods_A"), "=" + g("jlc_goods_B"), "bold",
         "Fees: JLCPCB price page, read " + V05_DATE + ", main rates and the panel fee re-read " + CHECK + ". Parts: LCSC prices read " + V05_DATE + ", the pogo pin " + CHECK
         + ", the buck and the protection IC " + CHECK_1000 + ", R3 " + CHECK_CELL + "; " + ", ".join(n_est) + " are ESTIMATES. Bare panels and the two-design surcharge: "
         "ESTIMATES.", namea="sum_pcb_A", nameb="sum_pcb_B")
    line("pcb1", "     of which bare panels + two-design surcharge (4 layers, 0.8 mm, ENIG, black solder mask)", "=%s+%s" % (g("fab_A"), g("fabd_A")), "=%s+%s" % (g("fab_B"), g("fabd_B")), "x",
         "ESTIMATE - the price appears only after the Gerber upload.", namea="sum_fab_A", nameb="sum_fab_B")
    line("pcb2", "     of which assembly fees (set-up, stencil, joints, feeder, panel fee, X-ray, ...)", "=" + g("fees_A"), "=" + g("fees_B"), "x", "JLCPCB fee page, sheet 'JLCPCB order'.")
    line("pcb3", "     of which components (%d lines, %d parts per panel, incl. spares for placement loss)" % (len(lines), sum(l["qty"] for l in lines)), "=" + g("comps_A"), "=" + g("comps_B"), "x",
         "LCSC price tiers, sheet '%s'." % BOM_SHEET)
    line("house", "2. Housing (JLCCNC + JLC3DP: aluminium tray + lid, PMMA and POM-C kits, resin casting mould)", "=" + g("housing_A"), "=" + g("housing_B"), "bold",
         "ESTIMATE - replace by the JLCCNC and JLC3DP instant quotes.", namea="sum_housing_A", nameb="sum_housing_B")
    line("house1", "     of which aluminium tray + lid (bead blast + black anodize, no marking)", "=" + g("alu_A"), "=" + g("alu_B"), "x",
         "ESTIMATE from volume, box, fine features and finish, sheet 'Housing' sections 2-6 (the panel texture included: 'texture_on').")
    line("house2", "     of which PMMA kit (main keys) + POM-C kit (RF insert, antenna spacer)", "=" + g("kit_A"), "=" + g("kit_B"), "x",
         "ESTIMATE - JLCCNC publishes no price for plastic parts; sheet 'Housing' section 7.")
    line("house3", "     of which resin casting mould for the rubber side keys (two SLA plates, JLC3DP, once per builder)", "=" + g("mould_A"), "=" + g("mould_B"), "x",
         "ESTIMATE from JLC3DP's headline rate, sheet 'Housing' section 6b. Leave it out if you already have a mould.")
    line("parts", "3. Bought parts (the cell, LED board, TIR optic, laser, screws, set screw, split ring, mould hardware)", "=" + g("parts_A"), "=" + g("parts_B"), "bold",
         "The cell, the LED board and the optic READ; the rest typical prices (ESTIMATES), sheet 'Bought parts'.", namea="sum_parts_A", nameb="sum_parts_B")
    line("cons", "4. Consumables (nickel strip, wire, thermal paste, tapes, foam, silicone pads, adhesives, casting supplies)", "=" + g("cons_A"), "=" + g("cons_B"), "bold",
         "Typical prices (ESTIMATES); the nickel strip read at nkon.nl, the urethane rubber at kaupo.de. Sheet 'Bought parts'.", namea="sum_cons_A", nameb="sum_cons_B")
    line("cons1", "     of which casting supplies for the side keys (urethane, pigment, release, shim, glue, cups, polishes)", "=" + g("bp_cast_A"), "=" + g("bp_cast_B"), "x",
         "Once per builder; one unit of rubber casts many keys.")
    line("tax", "5. Shipping, VAT, customs duty, carrier and bank fees", "=" + g("tax_other_A"), "=" + g("tax_other_B"), "bold",
         "Computed from EU rules and shipping ESTIMATES, sheet 'Hidden costs'.", namea="sum_other_A", nameb="sum_other_B")
    line("tax1", "     of which shipping (JLCPCB, JLCCNC + JLC3DP, the EU casting shop, the optic distributor, the battery shop, web-shop parcels)", "=" + g("hc_sum_ship_A"),
         "=" + g("hc_sum_ship_B"), "x",
         "Shipping per parcel are ESTIMATES (JLC shows them in the cart).", namea="sum_ship_A", nameb="sum_ship_B")
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
    s.merge(r, 7, 11, "Above the line the parcel pays a carrier fee of about EUR 15 (sheet 'Hidden costs', sections 4-6).", "note")
    r += 1
    s.put(r, 1, "     JLCCNC + JLC3DP order vs the EUR 150 IOSS line (EUR left; negative = above, formal customs)", "text")
    s.put(r, 2, "=" + g("cnc_line_gap_A"), "x", fmt=EUR2)
    s.put(r, 6, "=" + g("cnc_line_gap_B"), "x", fmt=EUR2)
    s.merge(r, 7, 11, "One light: below the line (VAT and EUR 3 per customs line only). More lights: above it (6 % duty, VAT and a carrier fee).", "note")
    rt = r + 1
    line("total", "TOTAL for the lights (1 + 2 + 3 + 4 + 5)", "=B%d+B%d+B%d+B%d+B%d" % (rows["pcb"], rows["house"], rows["parts"], rows["cons"], rows["tax"]),
         "=F%d+F%d+F%d+F%d+F%d" % (rows["pcb"], rows["house"], rows["parts"], rows["cons"], rows["tax"]), "tot", "Per-light columns divide by the number of lights built.",
         namea="sum_total_A", nameb="sum_total_B")
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
    s.merge(r, 4, 11, "Set-up fees, stencil, panel fee, feeder loading, the anodizing lot fee, the casting mould, the casting supplies and most shipping are paid once, so the 2nd to 5th "
            "light is much cheaper than the first.", "note")
    # ---- what changed since the first v0.7 layout
    la_v, lb_v = P["lightsA"]["v"], P["lightsB"]["v"]
    ra_, rb_ = v07r(la_v), v07r(lb_v)
    chg7 = [("pcb", "pcb", "1. PCB + assembly (JLCPCB)"), ("house", "house", "2. Housing"), ("parts", "parts", "3. Bought parts"), ("cons", "cons", "4. Consumables"),
            ("tax", "tax", "5. Shipping, VAT, customs, fees"), ("total", "total", "TOTAL for the lights")]
    per2 = (" (2 lights: %s -> %s per light)" % (money(V07R_SUMMARY[2]["per"]).lstrip("$"), money(cp2["sum_per_B"]).lstrip("$"))) if cp2 else ""

    def change_table(title, intro, heads, old_a, old_b, key_prefix, texts, per_note):
        nonlocal r
        r += 2
        s.merge(r, 1, 11, title, "sub", border=True)
        r += 1
        s.merge(r, 1, 11, intro, "note")
        r += 1
        s.head(r, ["Cost group"] + heads)
        s.merge(r, 8, 11, "What changed (savings, new costs, quality)", "head", border=True)
        ws.row_dimensions[r].height = 28
        for key, rk, lab in chg7:
            r += 1
            s.put(r, 1, lab, "tot" if key == "total" else "text")
            s.put(r, 2, old_a[key], "in", fmt=USD2)
            s.put(r, 3, "=B%d" % rows[rk], "calc", fmt=USD2)
            s.put(r, 4, "=C%d-B%d" % (r, r), "calc", fmt=USD2, name="%s_%s_A" % (key_prefix, key))
            s.put(r, 5, old_b[key], "in", fmt=USD2)
            s.put(r, 6, "=F%d" % rows[rk], "calc", fmt=USD2)
            s.put(r, 7, "=F%d-E%d" % (r, r), "calc", fmt=USD2, name="%s_%s_B" % (key_prefix, key))
            s.merge(r, 8, 11, texts.get(key, "Sum of the lines above." if key == "total" else ""), "text", border=True)
        r += 1
        s.put(r, 1, "TOTAL per light (A: %d, B: %d)" % (la_v, lb_v), "bold")
        s.put(r, 2, old_a["per"], "in", fmt=USD2)
        s.put(r, 3, "=D%d" % rows["total"], "calc", fmt=USD2)
        s.put(r, 4, "=C%d-B%d" % (r, r), "calc", fmt=USD2, name="%s_per_A" % key_prefix)
        s.put(r, 5, old_b["per"], "in", fmt=USD2)
        s.put(r, 6, "=H%d" % rows["total"], "calc", fmt=USD2)
        s.put(r, 7, "=F%d-E%d" % (r, r), "calc", fmt=USD2, name="%s_per_B" % key_prefix)
        s.merge(r, 8, 11, per_note, "note")

    change_table("What changed since the first v0.7 layout (same scenarios and exchange rate; USD)",
                 "The 'first layout' values are typed in from the cost workbook of the first v0.7 layout (price check %s: SST-20 behind a glass window, 2 x 400 mAh cells "
                 "with protection boards, a 3 A buck, the aluminium casting mould, PMC-780 DRY rubber; %d light%s in A, %d in B). Since then the light got the parts for "
                 "1000 lm and 100 m (TIR optic, 4 A buck with board protection, 24 AWG wire), one 14500 cell in an octagonal body, and cost was taken out where it does not "
                 "hurt the design. A negative change is a saving. docs/bom_notes.md has the same table for 1, 2 and 5 lights." % (V07R_CHECK, la_v, "" if la_v == 1 else "s", lb_v),
                 ["First layout: A", "Now: A", "Change A", "First layout: B", "Now: B", "Change B"], ra_, rb_, "d07",
                 first_layout_texts(cp0, lines, la_v) if cp0 else {},
                 "The 'first layout' B values are typed in for %d lights (the B of this build). With another number in B8 compare only column A, or rebuild the workbook "
                 "with tools/parts_list.py --lights-b N%s. Tools: %s instead of $174.00 (no scale; a spot welder for the cell's nickel strips)."
                 % (lb_v if lb_v in V07R_SUMMARY else 5, per2, money(sum(t[4] * t[5] * t[6] for t in TOOLS))))
    # ---- what the battery and body change costs (two pouch cells in the 20 x 16 mm body -> one 14500 cell in the octagon)
    pa_, pb_ = v07p(la_v), v07p(lb_v)
    per2p = (" (2 lights: %s -> %s per light)" % (money(V07P_SUMMARY[2]["per"]).lstrip("$"), money(cp2["sum_per_B"]).lstrip("$"))) if cp2 else ""
    change_table("What the battery and body change costs (two pouch cells in the 20 x 16 mm body -> one Vapcell INR14500 F15 in the 20 x 18 mm octagon; USD)",
                 "The 'two pouch cells' values are typed in from this workbook as it was just before the change (price check %s: two 320 mAh pouch cells, ESTIMATE $5.00 "
                 "each, from a web shop; the 20 x 16 mm body with its 1.5 mm plate lid; %d light%s in A, %d in B). Everything else is the same in both columns. A negative "
                 "change is a saving. docs/bom_notes.md has the same table for 1, 2 and 5 lights." % (V07P_CHECK, la_v, "" if la_v == 1 else "s", lb_v),
                 ["Two pouch cells: A", "One 14500 cell: A", "Change A", "Two pouch cells: B", "One 14500 cell: B", "Change B"], pa_, pb_, "dcell",
                 cell_change_texts(cp0, lines, la_v) if cp0 else {},
                 "The 'two pouch cells' B values are typed in for %d lights (the B of this build)%s. The cell itself got cheaper and has 2.3 times the capacity (1500 "
                 "mAh instead of two 320 mAh cells); the bigger body, the nickel strip and the battery shop's own parcel cost more." % (lb_v if lb_v in V07P_SUMMARY else 5, per2p))
    # ---- options
    r += 2
    s.merge(r, 1, 11, "Options: what each one saves against the defaults above, and what it costs in quality (USD, VAT, duty and shipping included)", "sub", border=True)
    r += 1
    s.merge(r, 1, 11, "Computed by tools/parts_list.py with the default inputs of this workbook (each option alone; they do not follow later changes of the inputs). A positive "
            "number is a saving, a negative one an extra cost. The defaults are the cheapest choices that keep the design as drawn: the texture stays because the order files "
            "carry it and it is part of the exterior style; the Harwin pogo pin stays because the cheaper pin is not verified.", "note")
    r += 1
    s.head(r, ["Option", "Saves A", "Saves B"])
    s.merge(r, 4, 11, "What it costs in quality / what to do", "head", border=True)
    for oid, lab, q in OPTIONS:
        r += 1
        s.put(r, 1, lab, "text")
        for k, sc in enumerate("AB"):
            s.put(r, 2 + k, (opts or {}).get("opt_%s_%s" % (oid, sc), 0.0), "calc", fmt=USD2, name="opt_%s_%s" % (oid, sc))
        s.merge(r, 4, 11, q, "text", border=True)
    # ---- what changed from v0.6
    r += 2
    s.merge(r, 1, 11, "What changed from v0.6 (same scenarios and exchange rate; USD)", "sub", border=True)
    r += 1
    s.merge(r, 1, 11, "The v0.6 values are typed in from the v0.6 cost workbook (sheet 'Summary', price check %s; the v0.6 package keeps that workbook). "
            "Electronics: one panel with two boards, %d BOM lines, %d placements, %d solder joints per panel (v0.6: 34 lines, 68 placements, 232 joints on one board) - the six "
            "pogo pins and the 1000 lm power stage are new, the switches, ring LEDs and eight resistors moved to the key board. Housing: no stainless caps, no laser marking, no "
            "glass window; new are the octagonal body, the PMMA and POM-C kits, the resin casting mould and the panel texture and grooves. Battery: one 14500 cell instead of "
            "two pouch cells with protection boards."
            % (V06_CHECK, len(lines), sum(l["qty"] for l in lines), sum(l["qty"] * l["pads"] for l in lines)), "note")
    r += 1
    s.head(r, ["Cost group", "v0.6: A", "v0.7: A", "Change A", "v0.6: B", "v0.7: B", "Change B"])
    s.merge(r, 8, 11, "What changed", "head", border=True)
    ws.row_dimensions[r].height = 28
    chg = [
        ("pcb", "pcb", "1. PCB + assembly (JLCPCB)",
         "A bigger bare panel with two designs (ESTIMATE $30 for 5 instead of $25, plus a two-design surcharge, ESTIMATE $15) and the panel fee for two designs ($8.21, read). "
         "New parts: the six pogo pins (C22100007) and the 1000 lm power stage (4 A buck TPS62095, protection DW01A + SE8830A); X-ray for 4 parts per panel."),
        ("house", "house", "2. Housing",
         "The stainless caps, the laser marking and the resin print kit are gone. New: the octagonal body (20 x 18 mm, the lid a 3.4 mm cap), the PMMA kit with the clear "
         "main keys, the POM-C kit, the resin casting mould for the rubber side keys (once per builder) and the recessed panels with the V texture and the transverse grooves "
         "on the tray and the lid (sheet 'Housing', sections 4-7)."),
        ("parts", "parts", "3. Bought parts", "New: the TIR optic instead of the glass window, one Vapcell INR14500 F15 cell (1500 mAh, protected on the main board) instead of "
         "two 400 mAh pouch cells with protection boards, two M1.6 x 2.5 key-board screws per light, the mould's M3 bolts (once per builder); the SST-20 Gen 2 LED board "
         "costs less."),
        ("cons", "cons", "4. Consumables",
         "New: the casting supplies for the rubber side keys (urethane rubber, pigment, mould release, stainless shim, glue, cups, polishes), the nickel strip for the cell, "
         "24 AWG wire, thermal paste, 0.5 mm foam; the can hold-down pad is now 1.5 mm thick."),
        ("tax", "tax", "5. Shipping, VAT, customs, fees",
         "Follows from the orders: no 3D-print parcel of its own (the resin mould travels with JLCCNC), a parcel each from the EU casting shop, the optic distributor and the "
         "battery shop (VAT only, no customs), two customs lines on the JLCCNC parcel, the card fee on two JLC payments."),
        ("total", "total", "TOTAL for the lights", "Sum of the lines above."),
    ]
    for key, rk, lab, why in chg:
        r += 1
        s.put(r, 1, lab, "tot" if key == "total" else "text")
        s.put(r, 2, V06_SUMMARY["A"][key], "in", fmt=USD2)
        s.put(r, 3, "=B%d" % rows[rk], "calc", fmt=USD2)
        s.put(r, 4, "=C%d-B%d" % (r, r), "calc", fmt=USD2, name="d_%s_A" % key)
        s.put(r, 5, V06_SUMMARY["B"][key], "in", fmt=USD2)
        s.put(r, 6, "=F%d" % rows[rk], "calc", fmt=USD2)
        s.put(r, 7, "=F%d-E%d" % (r, r), "calc", fmt=USD2, name="d_%s_B" % key)
        s.merge(r, 8, 11, why, "text", border=True)
    r += 1
    s.put(r, 1, "TOTAL per light (A: 1 light, B: 5 lights)", "bold")
    s.put(r, 2, V06_SUMMARY["A"]["per"], "in", fmt=USD2)
    s.put(r, 3, "=D%d" % rows["total"], "calc", fmt=USD2)
    s.put(r, 4, "=C%d-B%d" % (r, r), "calc", fmt=USD2, name="d_per_A")
    s.put(r, 5, V06_SUMMARY["B"]["per"], "in", fmt=USD2)
    s.put(r, 6, "=H%d" % rows["total"], "calc", fmt=USD2)
    s.put(r, 7, "=F%d-E%d" % (r, r), "calc", fmt=USD2, name="d_per_B")
    s.merge(r, 8, 11, "Per-light price in USD; the EUR values are in the table above. The v0.6 values are for 1 and 5 lights: compare B only while B is 5.", "note")
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
    s.merge(r, 4, 11, "A new board often needs a second round (the key board, the pogo contact and the power stage are new). Landed cost of a second JLCPCB order like scenario A.", "note")
    r += 1
    s.put(r, 1, "Risk reserve: second housing order (not in any total)", "text")
    s.put(r, 2, "=" + g("risk_house"), "x", fmt=USD2)
    s.put(r, 3, "=B%d/%s" % (r, fx), "calc", fmt=EUR2)
    s.merge(r, 4, 11, "If the first tray does not fit the delivered laser / cell / optic.", "note")
    # ---- how sure are we
    r += 2
    s.merge(r, 1, 11, "How reliable is each part of the total?", "sub", border=True)
    r += 1
    s.put(r, 1, "Item", "head")
    s.merge(r, 2, 4, "Status", "head", border=True)
    s.merge(r, 5, 11, "Where to replace it with a real number", "head", border=True)
    n_read = sum(1 for l in lines if not l["est"])
    qual = [
        ("JLCPCB assembly fees", "READ from the JLCPCB price page (last updated Sep 09, 2026); the panel fee for two designs read " + CHECK,
         "Sheet 'JLCPCB order' section 5; the cart shows the final fee list."),
        ("Components at LCSC / JLC", "READ from the LCSC product pages for %d lines (%s; the pogo pin %s; the buck and the protection IC %s; R3 %s); ESTIMATE for the %d lines %s "
         "(pages not readable)" % (n_read, V05_DATE, CHECK, CHECK_1000, CHECK_CELL, len(n_est), ", ".join(n_est)),
         "Sheet '%s' (amber cells); the JLC cart shows the real component price after the BOM upload." % BOM_SHEET),
        ("Bare panels and the two-design surcharge", "ESTIMATE (shown only after the Gerber upload)", "Sheet 'JLCPCB order' section 4: type the prices from the cart."),
        ("Aluminium tray + lid", "ESTIMATE from volume, box, fine features and finish", "Sheet 'Housing' section 6: type the JLCCNC instant quote."),
        ("PMMA and POM-C kits", "ESTIMATE (JLCCNC publishes no price for plastic parts)", "Sheet 'Housing' section 7: type the JLCCNC instant quote."),
        ("Casting mould", "ESTIMATE from JLC3DP's headline resin rate (once per builder)", "Sheet 'Housing' section 6b: type the JLC3DP quote (or the JLCCNC quote of the aluminium mould), or 0 if you have a mould."),
        ("Bought parts and consumables", "READ: the LED board (Kaidomain), the TIR optic (RS) and the ECON 80 urethane (kaupo.de), " + CHECK_1000 + "; the cell and the nickel "
         "strip (nkon.nl), " + CHECK_CELL + "; ESTIMATES: the AliExpress search snippets of " + V05_DATE + " and typical prices", "Sheet 'Bought parts': change the blue prices."),
        ("Shipping", "ESTIMATES (JLC publishes no rate table; the courier fees of the distributor and of the battery shop not read)", "Sheet 'Hidden costs' section 2: type the "
         "'Shipping Estimate' of each cart."),
        ("VAT and customs", "COMPUTED from the EU rules; duty rates of the formal route are assumptions", "Sheet 'Hidden costs'. Watch the EUR 150 line of both JLC orders."),
        ("Tools", "ESTIMATES (typical prices)", "Sheet 'Tools'."),
    ]
    for a, b, c in qual:
        r += 1
        s.put(r, 1, a, "text")
        s.merge(r, 2, 4, b, "warn" if "ESTIMATE" in b else "text", border=True)
        s.merge(r, 5, 11, c, "text", border=True)
    r += 2
    s.merge(r, 1, 11, "Sheets: Summary | JLCPCB order | %s | Housing | Bought parts | Hidden costs | Tools | Ordering checklist. Notes on sources, estimates and what to re-check: "
            "docs/bom_notes.md; rebuild: python3 tools/parts_list.py." % BOM_SHEET, "note")
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
    H, hsrc, stl, mould = load_housing()
    hparts = housing_parts(H, stl, mould)
    book = Book(addr)
    cp0 = model(P, lines, H, hparts, FINISH_DEFAULT, BOUGHT, TOOLS)
    p2 = json.loads(json.dumps(P))
    p2["lightsB"]["v"] = 2
    cp2 = model(p2, lines, H, hparts, FINISH_DEFAULT, BOUGHT, TOOLS)
    build_summary(book, lines, cp0, option_savings(lines, H, hparts), cp2)
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
    wb[BOM_SHEET].print_area = "A1:W%d" % (BOM_R0 + len(lines) + 40)
    wb.active = 0
    wb.properties.title = "FlashKa Keychain v0.7 - parts list and cost"
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
    """Run build_all.bom() (extracted with ast, build_all.py itself is not imported or run) into a temp dir: the panel BOM of both boards."""
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
        ns["bom"](p, COMPONENTS)
        with open(p, newline="", encoding="utf-8") as f:
            return list(csv.reader(f))
    finally:
        shutil.rmtree(d, ignore_errors=True)


BOARD_FILES = (os.path.join("kicad", "FlashKa_main", "FlashKa_main.kicad_pcb"), os.path.join("kicad", "FlashKa_keys", "FlashKa_keys.kicad_pcb"))


def board_pads():
    """({reference: solder joints}, [problems]) read from the two routed boards (main PCB and key board), or (None, []) if a file is missing.

    Counting rule (what JLCPCB bills as joints): an smd pad with copper counts once per name (the exposed pad of the ESP32
    module is drawn in 10 pieces with the same name = 1 joint); an smd pad with copper but without a name counts each (the four
    mounting tabs of the slide switch); paste-only pads (the paste windows of an exposed pad) are not joints; a thru_hole pad
    counts, unless it carries the name of an smd pad of the same footprint (a thermal via in an exposed pad, as under the buck
    U2); np_thru_hole pads are holes, not joints."""
    pads, issues = {}, []
    for rel in BOARD_FILES:
        try:
            with open(os.path.join(REPO, rel), encoding="utf-8") as f:
                text = f.read().split("\n")
        except OSError:
            return None, []
        cur = None
        for ln in text:
            if ln.startswith("  (footprint "):
                cur = dict(ref=None, named=set(), unnamed=0, tht=[])
                continue
            if cur is None:
                continue
            m = re.search(r'\(fp_text reference "([^"]+)"', ln)
            if m:
                cur["ref"] = m.group(1)
            m = re.match(r'\s+\(pad "([^"]*)" (\w+) ', ln)
            if m:
                name, typ = m.groups()
                lay = re.search(r'\(layers ([^)]*)\)', ln)
                copper = lay is None or ".Cu" in lay.group(1)
                if typ == "smd" and copper:
                    if name:
                        cur["named"].add(name)
                    else:
                        cur["unnamed"] += 1
                elif typ == "thru_hole":
                    cur["tht"].append(name)
            if ln == "  )" and cur["ref"]:
                if cur["ref"] in pads:
                    issues.append("designator %s is on both boards" % cur["ref"])
                pads[cur["ref"]] = len(cur["named"]) + cur["unnamed"] + sum(1 for t in cur["tht"] if not (t and t in cur["named"]))
                cur = None
    return pads, issues


def kit_key(fname):
    """'FlashKa_rf_window.step (spare)' -> 'FlashKa_rf_window'."""
    return fname.split()[0].replace(".step", "")


def verify(path, book, lines, H, hparts):
    """Re-open the saved workbook and check it. Returns the list of problems (empty = all good)."""
    problems = []
    wbv = load_workbook(path, data_only=True)
    wbf = load_workbook(path)
    if [ws.title for ws in wbf.worksheets] != ["Summary", "JLCPCB order", BOM_SHEET, "Housing", "Bought parts", "Hidden costs", "Tools", "Ordering checklist"]:
        problems.append("sheet names / order: %s" % [ws.title for ws in wbf.worksheets])
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
    cp.update(option_savings(lines, H, hparts))
    n_cmp = 0
    skipped = []
    for k, exp in cp.items():
        if k not in book.addr:
            skipped.append(k)
            continue
        got = val(k)
        n_cmp += 1
        if not isinstance(got, (int, float)) or abs(got - exp) > 1e-6 * max(1.0, abs(exp)) + 1e-9:
            problems.append("model mismatch %s: workbook %r, python %r" % (k, got, exp))
    for k in skipped:
        if not k.startswith("hc_formal_"):
            problems.append("model value without a workbook cell: " + k)
    for k, exp in cp.items():
        if k.startswith("hc_formal_"):
            nm = "hc_route_" + k[len("hc_formal_"):]
            want = "EU" if int(nm.rsplit("_", 1)[1]) in EU_PARCELS else ("formal" if exp else "IOSS")
            n_cmp += 1
            if val(nm) != want:
                problems.append("route mismatch %s: %r, expected %r" % (nm, val(nm), want))
    print("model check: %d workbook cells compared with the independent Python calculation" % n_cmp)

    # 2. BOM sheet vs COMPONENTS, vs build_all.bom(), vs the panel BOM/CPL files, vs the routed boards
    ws = wbv[BOM_SHEET]
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
    n_main = sum(1 for rc in COMPONENTS if rc["lcsc"] and not rc.get("dnp") and rc.get("board") == "main")
    n_keys = sum(1 for rc in COMPONENTS if rc["lcsc"] and not rc.get("dnp") and rc.get("board") == "keys")
    print("BOM check: %d lines, %d LCSC numbers, %d placements (main PCB %d, key board %d) - all COMPONENTS LCSC numbers present with the right quantity: %s"
          % (len(rows), len(exp_q), sum(got_q.values()), n_main, n_keys, "yes" if got_q == exp_q else "NO"))
    ref_rows = build_all_bom_rows()
    if ref_rows is None:
        print("note: build_all.py bom() could not be extracted; line-by-line comparison skipped")
    else:
        body = ref_rows[1:]
        if len(body) != len(rows):
            problems.append("build_all.bom() has %d lines, workbook %d" % (len(body), len(rows)))
        bad = False
        for i, (a, b) in enumerate(zip(body, rows)):
            if [a[0], a[1], a[2], a[3], int(a[4])] != [b[0], b[1], b[2], b[3], b[4]]:
                bad = True
                problems.append("line %d differs from build_all.bom(): %s vs %s" % (i + 1, a, b))
        print("BOM check: workbook agrees line by line with build_all.bom() (%d lines): %s" % (len(body), "NO" if bad else "yes"))
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
    for rel in ("production/CPL_JLCPCB.csv", "order_files/1_JLCPCB/CPL_JLCPCB.csv"):
        try:
            with open(os.path.join(REPO, rel), newline="", encoding="utf-8") as f:
                cpl = sorted(r[0] for r in list(csv.reader(f))[1:])
            if cpl != refs_all:
                problems.append("designators of %s differ from the BOM sheet: %s" % (rel, sorted(set(cpl) ^ set(refs_all))))
            print("BOM check: the %d designators of the BOM sheet are exactly the %d rows of %s: %s"
                  % (len(refs_all), len(cpl), rel, "yes" if cpl == refs_all else "NO"))
        except OSError:
            problems.append("cannot read " + rel)
    pads, pad_issues = board_pads()
    problems.extend(pad_issues)
    if pads is None:
        print("note: the routed boards (%s) were not found; solder-joint check skipped" % ", ".join(BOARD_FILES))
        exp_joints = sum(l["qty"] * l["pads"] for l in lines)
    else:
        exp_joints = 0
        for l in lines:
            for ref in l["refs"]:
                if pads.get(ref) != l["pads"]:
                    problems.append("solder joints of %s: BOM line %s says %s, routed board has %s" % (ref, l["lcsc"], l["pads"], pads.get(ref)))
                exp_joints += pads.get(ref, 0)
        print("BOM check: solder joints per footprint agree with the pads of the two routed boards, %d joints per panel" % exp_joints)
    for nm, exp in (("placements", len(refs_all)), ("joints", exp_joints), ("n_lines", len(rows))):
        if val(nm) != exp:
            problems.append("%s is %r, expected %d" % (nm, val(nm), exp))

    # 3. machining kits and mould: contents as built by the housing script, sizes above JLCCNC's minimum, quantities
    kmin = sorted((H.get("params", {}).get("kit_min") or [30.0, 20.0, 8.0]), reverse=True)
    for kname, want in KIT_PARTS.items():
        size, files = kit_info(H, kname)
        got = tuple(kit_key(f) for f in files)
        if got != want:
            problems.append("%s holds %s in housing_interface.json, the workbook assumes %s" % (kname, got, want))
        if any(a + 1e-9 < b for a, b in zip(sorted(size, reverse=True), kmin)):
            problems.append("%s %s is below JLCCNC's minimum size %s" % (kname, dims(size), dims(kmin)))
    if KIT_PARTS["FlashKa_pmma_kit"].count("FlashKa_key_main") != PMMA_PER_KIT:
        problems.append("PMMA kit holds %d main keys, PMMA_PER_KIT is %d" % (KIT_PARTS["FlashKa_pmma_kit"].count("FlashKa_key_main"), PMMA_PER_KIT))
    for p in hparts:
        if p["id"] in ("mcav", "mlid") and any(a + 1e-9 < b for a, b in zip(sorted(p["box"], reverse=True), kmin)):
            problems.append("mould plate %s %s is below JLCCNC's minimum size" % (p["key"], dims(p["box"])))
    kits = {p["id"]: p for p in hparts if p["proc"] == "KIT"}
    for sc in "AB":
        lights = P["lights" + sc]["v"]
        if val("kit_qty_pmma_" + sc) != math.ceil((lights + 1) / PMMA_PER_KIT):
            problems.append("PMMA kits in scenario %s: %r, expected ROUNDUP((%d + 1) / %d)" % (sc, val("kit_qty_pmma_" + sc), lights, PMMA_PER_KIT))
        if val("kit_qty_pom_" + sc) != lights:
            problems.append("POM-C kits in scenario %s: %r, expected one per light (%d)" % (sc, val("kit_qty_pom_" + sc), lights))
    print("kit check: PMMA kit %s (%d main keys), POM-C kit %s (%s), both as housing_interface.json 'machining_kits' and above the %s minimum; kits ordered %s + %s (A) / %s + %s (B)"
          % (dims(kits["pmma"]["box"]), PMMA_PER_KIT, dims(kits["pom"]["box"]), ", ".join(KIT_PARTS["FlashKa_pom_kit"]).replace("FlashKa_", ""), dims(kmin),
             val("kit_qty_pmma_A"), val("kit_qty_pom_A"), val("kit_qty_pmma_B"), val("kit_qty_pom_B")))
    # housing data: the JSON and the STL files come from the same build; sizes written into texts are those of the geometry
    if H is not HOUSING_SNAPSHOT:
        stl_, mould_ = load_housing()[2:4]
        for k in HOUSING_KEYS:
            a_, b_ = H["volumes_mm3"][k], stl_[k][3]
            if abs(a_ - b_) > 0.01 * a_:
                problems.append("volume of %s: JSON %.1f mm3, STL %.1f mm3 (different builds?)" % (k, a_, b_))
        for part, key in RESIN_STL.items():
            rv_ = stl_bbox_volume(os.path.join(REPO, HOUSING_DIR, key + ".stl"))
            jv_ = mould_[MOULD_RESIN][part]["volume_mm3"]
            if not rv_ or abs(rv_[3] - jv_) > 0.01 * jv_:
                problems.append("resin mould %s: key_mould_checks.json %.1f mm3, %s.stl %s (different builds?)" % (part, jv_, key, ("%.1f mm3" % rv_[3]) if rv_ else "missing"))
        t_, l_ = texture_lengths(H)
        tg, lg = groove_lengths(H)
        if not (0 < l_ < t_) or not (0 < lg < tg):
            problems.append("texture / groove lengths look wrong: tray %.1f + %.1f mm, lid %.1f + %.1f mm" % (t_, tg, l_, lg))
        par_ = H["params"]
        for nm, (w_, h_) in (("boss_box", PAD_CAN_MM), ("boss2_box", PAD_FRONT_MM)):
            bx = par_.get(nm)
            if not bx or abs((bx[1] - bx[0]) - w_) > 0.05 or abs((bx[3] - bx[2]) - h_) > 0.05:
                problems.append("hold-down boss %s is %s in housing_interface.json, the texts say a pad of %.1f x %.1f mm" % (nm, bx, w_, h_))
        for nm, want in (("pad_t0", PAD_CAN_T[0]), ("pad_gap", PAD_CAN_T[1]), ("pad2_t0", PAD_FRONT_T[0]), ("pad2_gap", PAD_FRONT_T[1])):
            if not isinstance(par_.get(nm), (int, float)) or abs(par_[nm] - want) > 1e-6:
                problems.append("hold-down pad %s is %r in housing_interface.json, the texts say %s mm" % (nm, par_.get(nm), want))
        if abs(stl_["FlashKa_lid"][2] - LID_HEIGHT_MM) > 0.05:
            problems.append("the lid is %.2f mm tall in cad/FlashKa_lid.stl, the texts say %.2f mm" % (stl_["FlashKa_lid"][2], LID_HEIGHT_MM))
        ol = (H.get("key_board") or {}).get("outline") or {}
        if all(k in ol for k in ("x0", "x1", "y0", "y1", "corner_r")):
            kb_size = (ol["x1"] - ol["x0"], ol["y1"] - ol["y0"], ol["corner_r"])
            if any(abs(a - b) > 0.05 for a, b in zip(kb_size, KB_MM)):
                problems.append("key board is %s in housing_interface.json, the texts say %s" % (dims(kb_size), dims(KB_MM)))
        else:
            problems.append("housing_interface.json has no key board outline")
        print("housing check: JSON volumes agree with the STL files (1 %%); texture tray %.1f + lid %.1f mm, grooves tray %.1f + lid %.1f mm; pads %s (%.2f -> %.2f) and %s (%.2f -> %.2f), "
              "lid height %.2f mm as in the texts" % (t_, l_, tg, lg, dims(PAD_CAN_MM), PAD_CAN_T[0], PAD_CAN_T[1], dims(PAD_FRONT_MM), PAD_FRONT_T[0], PAD_FRONT_T[1], LID_HEIGHT_MM))
    else:
        print("note: housing_interface.json not usable; the housing checks ran on the embedded snapshot only")

    # 4. order files: every file of ORDER_FILES exists in order_files/ and nothing else is there (README.txt of each folder excepted)
    n_of = 0
    for fold, name, _src in ORDER_FILES:
        n_of += 1
        if not os.path.isfile(os.path.join(REPO, "order_files", fold, name)):
            problems.append("missing order file order_files/%s/%s" % (fold, name))
    folders = sorted({f for f, _, _ in ORDER_FILES})
    for fold in folders:
        d_ = os.path.join(REPO, "order_files", fold)
        extra = [n_ for n_ in sorted(os.listdir(d_)) if n_ != "README.txt" and (fold, n_) not in {(f, n) for f, n, _ in ORDER_FILES}] if os.path.isdir(d_) else []
        if extra:
            problems.append("files in order_files/%s/ that ORDER_FILES does not list: %s" % (fold, ", ".join(extra)))
    odirs = sorted(n_ for n_ in os.listdir(os.path.join(REPO, "order_files")) if os.path.isdir(os.path.join(REPO, "order_files", n_)))
    if odirs != folders:
        problems.append("order_files/ has the folders %s, ORDER_FILES names %s" % (odirs, folders))
    print("order files: %d files of ORDER_FILES found in order_files/ and no unlisted file in its %d folders: %s"
          % (n_of, len(folders), "yes" if not any(p.startswith(("missing order file", "files in order_files", "order_files/ has")) for p in problems) else "NO"))

    # 5. texts: no file or shop of an older version, and every order_files/ path names a file of the package layout (ORDER_FILES)
    stale = [r"housing05", r"repo05", r"[a]urora", r"button cap", r"FlashKa_cap_", r"FlashKa_marking_", r"FlashKa_print_kit", r"3_JLC3DP",
             r"Main PCB BOM", r"FlashKa_spacer_ring", r"LP601646", r"thermal transfer tape", r"10(\.0)? x 1(\.0)? mm", r"94\.4 mm",
             r"PMC-780 DRY, 1\.36", r"6\.0 x 16 x 47", r"Ufine", r"501550", r"LPHD", r"640 mAh", r"5\.0 x 15 x 50", r"M1\.6 x 4\b(?!\.)", r"4\.2 x 7\.6",
             r"re[w]ork", r"as revie[w]ed", r"as first revie[w]ed", r"20 x 16 mm (?!rectangle|body)"]
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
                    if not any(f == fold for f, _ in known) or (name and name != "README.txt" and (fold, name) not in known):
                        problems.append("unknown order file %s in %s!%s" % (m_.group(0), ws_.title, c.coordinate))
    print("text check: %d text cells, %d order_files/ paths; all paths in the package layout, no file or shop of an older version: %s"
          % (n_txt, n_paths, "yes" if not any(p.startswith(("stale text", "unknown order file")) for p in problems) else "NO"))

    # 6. docs/bom_notes.md says in which cells the real quotes and the main switches are typed: those must be cells of this workbook,
    #    and the quote cells must be empty (otherwise the totals are not the estimates)
    cells = [("pcb_fab5", False), ("fab_design", False), ("cnc_alu_quote_A", True), ("cnc_alu_quote_B", True), ("kit_quote_A", True), ("kit_quote_B", True),
             ("mould_quote_A", True), ("mould_quote_B", True), ("ship_mode", False), ("finish_sel", False), ("texture_on", False), ("fx", False), ("lightsA", False),
             ("lightsB", False)]
    refs = []
    for nm, must_be_empty in cells:
        sh, col, row = book.addr[nm]
        refs.append("%s!%s%d" % (sh, get_column_letter(col), row))
        if must_be_empty and val(nm) is not None:
            problems.append("quote cell %s is not empty: the totals would not be the estimates" % refs[-1])
    r0, r2 = book.addr["ship_A_0"][2], book.addr["ship_A_%d" % (len(SHIPPING) - 1)][2]
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
    nb = P["lightsB"]["v"]
    print("\nRESULT (price check %s, fx %.4f USD/EUR)" % (CHECK_CELL, f))
    for sc, lab in (("A", "%d light%s" % (P["lightsA"]["v"], "" if P["lightsA"]["v"] == 1 else "s")), ("B", "%d lights" % nb)):
        print("  %s: total $%.2f = EUR %.2f ; per light $%.2f = EUR %.2f   [PCB+asm %.2f, housing %.2f, parts %.2f, consumables %.2f, ship/VAT/fees %.2f]" % (
            lab, cp["sum_total_" + sc], cp["sum_total_eur_" + sc], cp["sum_per_" + sc], cp["sum_per_eur_" + sc], cp["sum_pcb_" + sc], cp["sum_housing_" + sc],
            cp["sum_parts_" + sc], cp["sum_cons_" + sc], cp["sum_other_" + sc]))
    print("  housing (A / B): tray + lid $%.2f / $%.2f (texture $%.2f / $%.2f), kits $%.2f / $%.2f (PMMA %d / %d, POM-C %d / %d), resin mould $%.2f (aluminium option "
          "$%.2f); JLCCNC + JLC3DP order $%.2f / $%.2f (EUR %.2f / %.2f below the IOSS line)" % (
              cp["alu_A"], cp["alu_B"], cp["tex_cost_A"], cp["tex_cost_B"], cp["kit_A"], cp["kit_B"], cp["kit_qty_pmma_A"], cp["kit_qty_pmma_B"], cp["kit_qty_pom_A"],
              cp["kit_qty_pom_B"], cp["mould_A"], cp["mould_alu_est_A"], cp["cnc_A"], cp["cnc_B"], cp["cnc_line_gap_A"], cp["cnc_line_gap_B"]))
    print("  JLCPCB goods (A / B): $%.2f / $%.2f (EUR %.2f / %.2f below the IOSS line: %.2f / %.2f); casting supplies $%.2f" % (
        cp["jlc_goods_A"], cp["jlc_goods_B"], cp["jlc_goods_eur_A"], cp["jlc_goods_eur_B"], cp["jlc_line_gap_A"], cp["jlc_line_gap_B"], cp["bp_cast_A"]))
    if nb == 5:
        print("  change from v0.6 (1 / 5 lights): total %+.2f / %+.2f USD, per light %+.2f / %+.2f USD" % (cp["d_total_A"], cp["d_total_B"], cp["d_per_A"], cp["d_per_B"]))
    if nb in V07R_SUMMARY:
        print("  change from the first v0.7 layout (1 / %d lights): total %+.2f / %+.2f USD, per light %+.2f / %+.2f USD" % (nb, cp["d07_total_A"], cp["d07_total_B"],
                                                                                                                     cp["d07_per_A"], cp["d07_per_B"]))
    if nb in V07P_SUMMARY:
        print("  change from the two-pouch-cell layout (1 / %d lights): total %+.2f / %+.2f USD, per light %+.2f / %+.2f USD" % (nb, cp["dcell_total_A"], cp["dcell_total_B"],
                                                                                                                         cp["dcell_per_A"], cp["dcell_per_B"]))
    if "opt_tex_A" in cp:
        print("  options (saving 1 / %d lights): %s" % (nb, "; ".join("%s %+.2f / %+.2f" % (o[0], cp["opt_%s_A" % o[0]], cp["opt_%s_B" % o[0]]) for o in OPTIONS)))
    print("  extra cost per additional light $%.2f (EUR %.2f); tools $%.2f (optional $%.2f); risk reserve PCB $%.2f, housing $%.2f" % (
        cp["sum_marginal"], cp["sum_marginal_eur"], cp["tools_total"], cp["tools_optional"], cp["risk_pcb"], cp["risk_house"]))


def main(argv):
    args, flags, i = [], set(), 1
    while i < len(argv):
        a = argv[i]
        if a == "--lights-b":
            if i + 1 >= len(argv) or not argv[i + 1].isdigit() or int(argv[i + 1]) < 1:
                raise SystemExit("--lights-b needs a whole number of lights, e.g. --lights-b 2")
            P["lightsB"]["v"] = int(argv[i + 1])
            flags.add(a)
            i += 2
            continue
        if a.startswith("--"):
            flags.add(a)
        else:
            args.append(a)
        i += 1
    if args:
        out = os.path.abspath(args[0])
    elif "--lights-b" in flags:
        out = os.path.join(tempfile.mkdtemp(prefix="flashka_b%d_" % P["lightsB"]["v"]), OUT_NAME)
    else:
        out = os.path.join(REPO, OUT_NAME)
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
