# Aurora++ v0.5 - parts list and cost workbook: reading notes

| | |
|---|---|
| Workbook | `Aurora_Parts_List_v0.5.xlsx` (repository root) |
| Generator | `tools/parts_list.py` (run `python3 tools/parts_list.py`, see section 7) |
| Price-check date | **2026-10-14** (every price and fee below was read or estimated on this day) |
| Exchange rate | 1.1188 USD per EUR (ECB euro reference rate of 13 Oct 2026, input cell `Summary!B6`) |
| Delivery to | Lithuania (EU): VAT 21 %, EU customs rules of 2026 |

This file explains (1) how to read the workbook, (2) the result, (3) where every number comes from, with URL and date, (4) which numbers are only estimates,
(5) what is most uncertain and (6) what you must re-check before you order. It does not repeat every cell of the workbook: each price row in the workbook carries its own source URL and date.

## 1. How to read the workbook

**The idea.** The light is made from five groups of things, bought from different places. The workbook prices every group, then adds the costs people forget
(shipping of every separate parcel, 21 % VAT, the new EU customs duty, bank fees) so that the Summary shows what really leaves your bank account.

| Group | Where you buy it | Sheet |
|---|---|---|
| Circuit board, soldered and tested by the factory | jlcpcb.com (PCB + assembly) | `JLCPCB order`, `Main PCB BOM` |
| Aluminium body (tray + lid) and the small see-through resin parts (ordered as one print kit) | jlccnc.com, jlc3dp.com | `Housing` |
| Cells, LED board, laser module, glass, screws, ring, wire, tapes, epoxy | AliExpress or an EU web shop | `Bought parts` |
| Shipping, VAT, customs, bank fees, spares, risk | - | `Hidden costs` |
| Tools you need once (soldering iron, multimeter, laser glasses ...) | any shop | `Tools` |

`Summary` is the first sheet and `Ordering checklist` is the last: it lists, in order, what to order where, which file to upload and what to check before paying.
Every file to upload is named with its place in the ready-to-upload folder of the package: `order_files/1_JLCPCB/`, `order_files/2_JLCCNC/` and `order_files/3_JLC3DP/` (section 6, item 2).

**Colour code** (also written at the top of the sheets):

| Look | Meaning |
|---|---|
| blue number | typed-in number you may change (price, fee, quantity) |
| blue number on amber background | **ESTIMATE**: no public price exists or it could not be read; replace it with a real quote when you have one |
| black number | formula: do not type over it |
| green number | copied from another sheet |
| dark blue row / light blue row / light green row | table header / section title / total |
| "TOO SMALL" (sheet `Housing`, section 6) | the part alone is below the printer's minimum size; red only if such a part is ordered on its own (the four small parts are ordered as one print kit, see section 3.6) |

**Two scenarios.** Scenario A = you build **1** light, scenario B = you build **5** lights (`Summary!B7` and `Summary!B8`: type any other numbers).
The JLC minimums are built in: JLCPCB sells at least 5 bare boards per design (in steps of 5) and assembles from 2 boards, so one light still pays for 2 assembled boards.
The Summary shows totals in USD and EUR, per light, and the extra cost of each additional light (the set-up and stencil fees, the anodizing lot fee and most shipping are paid once).

**Putting in real numbers.** Every total is a formula, so you only change inputs:

| What | Cell |
|---|---|
| bare PCB price shown by JLCPCB after the Gerber upload (price for 5 boards) | `JLCPCB order!B44` |
| JLCCNC instant quote (aluminium tray + lid, with finish, no shipping), scenario A / B | `Housing!B63` / `Housing!C63` |
| JLC3DP instant quote (resin print kits, no shipping), scenario A / B | `Housing!E77` / `Housing!G77` |
| "Shipping Estimate" of each cart (economy / express, A and B) | `Hidden costs!B20:E22` |
| shipping mode 1 = economy, 2 = express | `Hidden costs!B11` |
| price of any bought part | column F of `Bought parts` |
| surface finish of the aluminium (drop-down) | `Housing!B33` |
| exchange rate | `Summary!B6` |

Leave a quote cell empty to use the workbook's own estimate; type a number to override it. The Summary column "Where to replace it with a real number" names the cell for each row.

## 2. Result (price check 2026-10-14)

| USD (EUR) | 1 light | 5 lights |
|---|---|---|
| 1. PCB + assembly (JLCPCB), before shipping | $169.31 (EUR 151.33) | $196.67 (EUR 175.79) |
| 2. Housing (aluminium + resin print kit) | $65.96 (EUR 58.96) | $225.40 (EUR 201.46) |
| 3. Bought parts (cells, LED board, laser, glass, screws, ring) | $56.75 (EUR 50.72) | $211.30 (EUR 188.86) |
| 4. Consumables (wire, tapes, epoxy) | $18.29 (EUR 16.35) | $18.29 (EUR 16.35) |
| 5. Shipping, VAT, customs duty, carrier and card fees | $219.32 (EUR 196.03) | $329.89 (EUR 294.86) |
| **Total for the lights** | **$529.63 (EUR 473.39)** | **$981.55 (EUR 877.33)** |
| **Per light** | **$529.63 (EUR 473.39)** | **$196.31 (EUR 175.47)** |
| Tools, one-time (only the tools marked needed) | $128.00 (EUR 114.41) | same |
| Risk reserve, not in any total: a second PCB + assembly order | $247.66 (EUR 221.36) | |
| Risk reserve, not in any total: a second housing order | $108.34 (EUR 96.83) | |

Item 5 in detail (1 light / 5 lights): shipping $81.00 / $84.00, VAT $82.17 / $157.60, customs duty and carrier fees $50.35 / $78.58, card fee $5.80 / $9.72.

**Biggest cost items.**

1. Shipping, VAT, duty and fees: 41 % of the 1-light total ($219.32). Every shop ships its own parcel: three JLC parcels and (by default) 8 AliExpress parcels, each with its own shipping and its own flat EUR 3 customs duty.
2. JLCPCB assembly fees: $127.15 for 1 light (set-up $51.12, feeder loading $50.49, stencil $16.42, X-ray $6.56, everything else together $2.56). They are mostly paid once, which is why 5 lights cost only $12.26 more in fees.
3. Aluminium tray + lid: $64.76 for 1 set, $221.80 for 5 sets (estimate; the set-ups and the anodizing lot fee are paid once per order).
4. Laser module ($23.50 each), then the two cells and the LED board.

The resin parts cost little: JLC3DP prints them as one print kit, $1.20 for 1 light (2 kits incl. the spare), $3.60 for 5 lights (6 kits).
Every additional light after the first costs about $112.98 more (the Summary shows it).

**The EUR 150 cliff.** Up to EUR 150 goods value per parcel the EU collects VAT at the checkout (IOSS) and a flat EUR 3 duty per customs line. Above EUR 150 the parcel needs formal customs
clearance and the carrier charges a handling fee of about EUR 15. The JLCPCB order for 1 light has goods of about **EUR 151.33** ($169.31 before shipping), i.e. EUR 1.33 above the line, so the workbook routes it through formal clearance,
which costs about $10.07 more than the IOSS route (`Hidden costs`, section 6). If the real PCB price or the component prices are a little lower, the parcel falls below the line and the bill drops by about this amount.
Keep the three JLC orders as three separate parcels.

## 3. Where every number comes from

"READ" = copied from the vendor page on 2026-10-14. "ESTIMATE" = no public price or not readable; the cell is blue on amber and explained in its note column.
"COMPUTED" = formula from READ inputs. Sections 3.1 to 3.9 follow the order of the sheets.

### 3.1 JLCPCB assembly fees (READ) - sheet `JLCPCB order`, section 5

Fee page: <https://jlcpcb.com/help/article/pcb-assembly-price>, shows "Last updated on Sep 09, 2026", read 2026-10-14. The board has parts on both sides, so it needs **Standard PCBA**, double-sided
(Economic PCBA is single-sided only and charges $3.07 per Extended part; Standard charges the feeder fee per unique part instead, Basic or Extended alike, and has no separate engineering fee).

| Fee | Rate | Used for this order |
|---|---|---|
| Set-up fee (Standard PCBA) | $25.56 per side | 2 sides = $51.12 |
| Stencil (Standard PCBA) | $8.21 per side | 2 sides = $16.42 |
| SMT assembly | $0.0016 per solder joint | 217 joints per board x boards assembled |
| Feeder loading | $1.53 per unique part (Basic and Extended) | 33 unique parts = $50.49 |
| Confirm parts placement (optional, recommended) | $0.45 per order | included |
| X-ray inspection ("required for components such as BGA, QFN, and other leadless packages") | per part, tiered by the order total: 1-10 $1.64, 11-50 $0.82, 51-200 $0.49, 201-500 $0.33, 501-1000 $0.25, 1001-3000 $0.16, 3001+ $0.082 | 2 parts per board (ESP32 module U4, RGB LED LED3) |
| Panelisation of small boards (<https://jlcpcb.com/help/article/Panelizing-your-PCB-for-Assembly>) | minimum $0.46 per board | included (assumed to apply, see section 4) |
| Packing | $0.50 + $0.00003 per cm2 | included |
| Hand-soldering $3.58, pre-reflow $0.016 per joint, single-board surcharge $0.48, fixture $8.21, storage $4.93, large board $57.46 (above 650 cm2) | listed on the page | quantity 0: not needed for this board |

Other JLCPCB pages used: assembly from 2 boards <https://jlcpcb.com/pcb-assembly>; 5 bare boards minimum and the price calculator <https://cart.jlcpcb.com/quote>;
capabilities (4 layers, 0.8 mm, ENIG) <https://jlcpcb.com/capabilities/pcb-capabilities>; extra pieces for placement loss are billed inside the component price <https://jlcpcb.com/help/article/pcb-assembly-faqs-part-2>.

### 3.2 Components at LCSC / JLC (READ) - sheet `Main PCB BOM`

Every price tier and the retail stock were read on 2026-10-14 from `https://www.lcsc.com/product-detail/<LCSC number>.html`; each row of the sheet links to that page (column E) and prints the URL and date (column AJ).
The library type (Basic / Extended) was read on `https://jlcpcb.com/partdetail/<LCSC number>`; the Basic parts list is at <https://jlcpcb.com/parts/basic_parts>.
The unit price is the tier that matches the quantity JLC has to buy (quantity per board x boards + extra pieces for placement loss).

The BOM has **33 lines, 60 placements, 217 solder joints per board**; it is derived from `COMPONENTS` in `tools/kicad/aurora_parts.py` with the same grouping and ordering as `build_all.py` (lines with an empty LCSC number or `dnp` are skipped).
J2 (cells), J3 (LED) and J5 (laser) are wire pads without an LCSC number: JLCPCB does not assemble them, you solder the wires by hand. 19 lines are Basic, 14 are Extended.
Retail stock at LCSC is not JLC's own warehouse stock; the JLC BOM upload shows the stock that matters.

| LCSC # | Designators | Manufacturer part | JLC type | Qty / board | LCSC stock 2026-10-14 |
|---|---|---|---|---|---|
| [C15850](https://www.lcsc.com/product-detail/C15850.html) | C1 | CL21A106KAYNNNE | Basic | 1 | 20 **low** |
| [C19702](https://www.lcsc.com/product-detail/C19702.html) | C2, C13, C15 | CL10A106KP8NNNC | Basic | 3 | 181,020 |
| [C59461](https://www.lcsc.com/product-detail/C59461.html) | C5, C8 | CL10A226MQ8NRNC | Basic | 2 | 4,416,440 |
| [C1555](https://www.lcsc.com/product-detail/C1555.html) | C9 | 0402CG220J500NT | Basic | 1 | 798,400 |
| [C15195](https://www.lcsc.com/product-detail/C15195.html) | C11 | CL05B103KB5NNNC | Basic | 1 | 0 **retail 0** |
| [C52923](https://www.lcsc.com/product-detail/C52923.html) | C12, C14, C17, C18 | CL05A105KA5NQNC | Basic | 4 | 598,000 |
| [C1525](https://www.lcsc.com/product-detail/C1525.html) | C7, C10, C16, C19, C20 | CL05B104KO5NNNC | Basic | 5 | 0 **retail 0** |
| [C82044](https://www.lcsc.com/product-detail/C82044.html) | D1 | ESD5Z5.0T1G | Extended | 1 | 370,780 |
| [C165948](https://www.lcsc.com/product-detail/C165948.html) | J1 | TYPE-C-31-M-12 | Extended | 1 | 375,745 |
| [C602028](https://www.lcsc.com/product-detail/C602028.html) | L1 | FHD4020S-1R0MT | Extended | 1 | 8,210 |
| [C2874113](https://www.lcsc.com/product-detail/C2874113.html) | LED3 | NH-B1010RGBT-HF | Extended | 1 | 345,020 |
| [C15127](https://www.lcsc.com/product-detail/C15127.html) | Q1 | AO3401A | Basic | 1 | 164,910 |
| [C5224240](https://www.lcsc.com/product-detail/C5224240.html) | Q2, Q4, Q5 | 2N7002W-7-F-ES | Extended | 3 | 17,000 |
| [C25905](https://www.lcsc.com/product-detail/C25905.html) | R1, R2 | 0402WGF5101TCE | Basic | 2 | 2,302,500 |
| [C25890](https://www.lcsc.com/product-detail/C25890.html) | R3 | 0402WGF3301TCE | Basic | 1 | 867,600 |
| [C25764](https://www.lcsc.com/product-detail/C25764.html) | R10 | 0402WGF2003TCE | Basic | 1 | 1,520,700 |
| [C25792](https://www.lcsc.com/product-detail/C25792.html) | R12 | 0402WGF4702TCE | Basic | 1 | 3,114,700 |
| [C25744](https://www.lcsc.com/product-detail/C25744.html) | R8, R9, R13, R18, R21, R22 | 0402WGF1002TCE | Basic | 6 | 2,846,900 |
| [C25879](https://www.lcsc.com/product-detail/C25879.html) | R14 | 0402WGF2201TCE | Basic | 1 | 586,000 |
| [C4109](https://www.lcsc.com/product-detail/C4109.html) | R16 | 0402WGF2001TCE | Basic | 1 | 5,789,500 |
| [C11702](https://www.lcsc.com/product-detail/C11702.html) | R19, R23 | 0402WGF1001TCE | Basic | 2 | 0 **retail 0** |
| [C25076](https://www.lcsc.com/product-detail/C25076.html) | R24, R25 | 0402WGF1000TCE | Basic | 2 | 4,360,400 |
| [C26083](https://www.lcsc.com/product-detail/C26083.html) | R27, R28 | 0402WGF1004TCE | Basic | 2 | 541,000 |
| [C25741](https://www.lcsc.com/product-detail/C25741.html) | R7, R11, R15, R17, R20, R26, R29 | 0402WGF1003TCE | Basic | 7 | 3,791,500 |
| [C92740](https://www.lcsc.com/product-detail/C92740.html) | RS1 | MS05W2F200MT5E | Extended | 1 | 4,880 |
| [C77130](https://www.lcsc.com/product-detail/C77130.html) | RT1 | NCP15WF104F03RC | Extended | 1 | 298,120 |
| [C110293](https://www.lcsc.com/product-detail/C110293.html) | S1 | SKRTLAE010 | Extended | 1 | 62,440 |
| [C431540](https://www.lcsc.com/product-detail/C431540.html) | S2 | MSK12C02 | Extended | 1 | 170,330 |
| [C12044](https://www.lcsc.com/product-detail/C12044.html) | U1 | TP4057-42-SOT26-R | Extended | 1 | 32,025 |
| [C485117](https://www.lcsc.com/product-detail/C485117.html) | U2 | TLV62585DRLR | Extended | 1 | 925 **low** |
| [C181502](https://www.lcsc.com/product-detail/C181502.html) | U3 | TLV333IDCKR | Extended | 1 | 18,425 |
| [C2838502](https://www.lcsc.com/product-detail/C2838502.html) | U4 | ESP32-C3-MINI-1-N4 | Extended | 1 | 8,387 |
| [C841192](https://www.lcsc.com/product-detail/C841192.html) | U5 | RT9080-33GJ5 | Extended | 1 | 27,375 |

### 3.3 Bare PCB (ESTIMATE) - sheet `JLCPCB order`, section 4

JLCPCB shows the price of the bare board only after the Gerber upload at <https://cart.jlcpcb.com/quote>, so the workbook uses **$25 for 5 boards** (4 layers, 0.8 mm, ENIG, 24.0 x 16.5 mm; the range $12 to $40 is shown for information).
Anchors: a 100 x 100 mm 4-layer board x 5 is about $32.90 (<https://pcbsync.com/pcb-prototype-services-compared/>, vendor not named); "$16 for ENIG on small runs" (a 2020 forum post, <https://forums.ghielectronics.com/t/enig-or-hasl-for-pcb-finish/23438>);
a 24 x 16.5 mm board is far smaller than 100 x 100 mm. Replace the estimate with the real price in `JLCPCB order!B44`. The board outline (24.0 x 16.5 mm, 1.3 mm chamfers, 3.94 cm2) comes from `cad/housing_interface.json` (`pcb_outline`).

### 3.4 Shipping (ESTIMATE) - sheet `Hidden costs`, section 2

JLC publishes no rate table; the cart shows a "Shipping Estimate" after you enter the address. Anchors for a small JLCPCB parcel: DHL Express $21.50, EuroPacket $6.50, Global Standard Direct Line $1.50
(Chiptron, 10 Jun 2025, <https://chiptron.eu/jlcpcb-reduces-shipping-costs-pcb-order-with-shipping-worth-bad-beer/>); FedEx about $16 to Spain (EEVblog 2024,
<https://eevblog.com/forum/manufacture/jlcpcb-pcb-assembly-optimal-shipping-for-eu>). The workbook defaults to express ($21.50 JLCPCB, $22 / $25 JLCCNC for 1 / 5 sets, $21.50 JLC3DP) because DDP (taxes paid at checkout) works most reliably;
economy ($6.50 JLCPCB, $7 / $9 JLCCNC for 1 / 5 sets, $6.50 JLC3DP) is selectable in `Hidden costs!B11` and lowers the 1-light total by about $55.27 (5 lights: $57.67). JLCCNC and JLC3DP shipping are guesses from weight (JLCCNC shows it only on the invoice).
AliExpress: $2 per seller parcel and 8 parcels are assumptions.

### 3.5 EU VAT, customs duty, bank fee, exchange rate - sheet `Hidden costs`, sections 1 and 3 to 5

| Input | Value | Status | URL (read 2026-10-14) |
|---|---|---|---|
| VAT Lithuania | 21 % | READ | <https://jlcpcb.com/help/article/EU-VAT-E-commerce-Rules-%26-Adjustments> |
| IOSS limit: goods value per parcel (VAT collected at checkout) | EUR 150 | READ | same page |
| Flat customs duty on low-value parcels, 1 Jul 2026 to 1 Jul 2028 | EUR 3 per customs line (item category) per parcel | READ | <https://jlcpcb.com/help/article/eu-customs-reform-faq>, <https://trade.ec.europa.eu/access-to-markets/en/news/eu-applies-eu3-customs-duty-item-low-value-e-commerce-consignments>, JLC3DP note <https://jlc3dp.com/news/eu-customs-reform2026> |
| Carrier fee in formal clearance (above EUR 150) | max(EUR 15, 2 % of VAT + duty); examples on the page: DHL Germany 2 % min EUR 15, UPS 3 % min EUR 15.70, FedEx 2.5 % min EUR 15 | READ (examples) | <https://jlcpcb.com/help/article/eu-customs-reform-faq> |
| Tariff rates in formal clearance | JLCPCB 0 % (HS 8534 / 8543), JLCCNC 6 % (aluminium articles, HS 7616 99 90), JLC3DP 6.5 % (plastic articles, HS 3926 90), AliExpress 0 % | **ESTIMATE** (assumed HS codes; the invoice decides) | - |
| Customs lines per parcel | JLCPCB 2, the others 1 | ESTIMATE | - |
| Exchange rate | 1.1188 USD per EUR | READ (ECB, 13 Oct 2026) | <https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/eurofxref-graph-usd.en.html> |
| Card / currency conversion fee on the JLC payments | 1.5 % | **ESTIMATE** (0-3 % depending on your bank) | - |

Not included: a unified EU customs handling fee of about EUR 2 per parcel that the EU plans for around Nov 2026 (not final when this was written), your own time, a second PCB or housing round (shown as risk reserve), laser engraving of the marking.

### 3.6 Housing (ESTIMATE) - sheet `Housing`

The real price of CNC and resin parts appears only after the STEP / STL upload, so the workbook estimates it with a stated method. Type the instant quotes into `Housing!B63:C63` and `Housing!E77`, `G77` when you have them.

* **JLCCNC aluminium tray + lid.** Method (sheet section 2): cost of one part = aluminium block (bounding box + 2 mm on every side, 6061 at $8 per kg, you pay for the whole block) + machining (material to remove / 6 cm3 per min + fine-feature minutes, x $0.60 per min x complexity factor)
  + $0.25 per thread + finish; set-ups ($3.50 each: tray 3, lid 2) and the anodizing lot fee are paid once per order. All of these parameters are ESTIMATES (the machine rate is calibrated so that one tray + lid costs about what the v0.4 estimate gave);
  JLCCNC publishes no price list (<https://jlccnc.com/blog/cnc-machining-cost-factors> only explains the cost factors). Facts READ from JLCCNC: 6061-T6, bead blast + black anodize as one combined option, anodize 8-25 um, ISO 2768-m, threads supported but M1.6 not listed, minimum metal wall 0.8 mm,
  STEP mandatory + drawing PDF with identical file names, standard lead time from 3 working days, quote within 24 h
  (<https://jlccnc.com/capabilities/cnc-machining-service>, <https://jlccnc.com/help/article/cnc-machining-ordering-guidelines>, <https://jlccnc.com/finishes>, <https://jlccnc.com/cnc-machining-quote>). The finish prices and lot fees per finish are ESTIMATES.
  Upload: `order_files/2_JLCCNC/Aurora_tray.step` + `Aurora_tray.pdf` and `Aurora_lid.step` + `Aurora_lid.pdf` (the v0.5 drawings `cad/Aurora_tray_drawing.pdf`, 2 pages, and `cad/Aurora_lid_drawing.pdf`, renamed to the STEP names);
  optional laser marking `Aurora_marking_class2.dxf` (`Aurora_marking_class3R.dxf` only for a module that measures above 1 mW) from the same folder.
* **JLC3DP print kit (SLA 8001 translucent).** JLC3DP gets ONE part, `order_files/3_JLC3DP/Aurora_print_kit.stl`: the RF window, button cap, spacer ring and antenna spacer joined by 1 mm sprues
  (29.5 x 16.8 x 12.6 mm, 1163.7 mm3 = the four parts' 1155.8 mm3 + 7.9 mm3 of sprues), because the RF window (8.4 x 15.5 x 1.7 mm) and the button cap (5.2 x 3.1 x 2.2 mm) alone are below the minimum build size.
  One kit per light + one spare kit: 2 kits for 1 light, 6 for 5 lights; you cut the parts apart at home. The kit is priced from its own STL volume with the same model as single parts:
  $0.30 per cm3 (headline "SLA from $0.30" on <https://jlc3dp.com/>) with an assumed minimum of $0.60 per part (<https://jlc3dp.com/3d-printing-quote>): ESTIMATE; even the kit (1.16 cm3, $0.35 by volume) is so small that the minimum decides,
  so the JLC3DP order is $1.20 for 1 light and $3.60 for 5 lights. The four parts stay in the sheet as information rows with quantity 0 ("included in the print kit"); the laser sleeve
  (`order_files/3_JLC3DP/Aurora_laser_sleeve.stl`, 10 x 6 x 6 mm, big enough on its own) is a separate optional print with quantity 0 unless your laser module is 4.5 mm.
  READ facts: tolerance +/-0.2 mm or 0.3 %, wall > 0.8 mm, minimum build size 5 x 5 x 5 mm or 10 x 2 x 2 mm, build time 2 days
  (<https://jlc3dp.com/help/article/photosensitive-8001-resin>, <https://jlc3dp.com/help/article/1219-What-is-the-build-time-of-the-3D-printing-parts>).
* **Geometry.** Volumes, bounding boxes and the PCB outline come from `cad/housing_interface.json` (final v0.5 housing: tray 8671 mm3, lid 2238 mm3) and the STL files in `cad/`
  (bounding boxes, and the volume of the print kit and the laser sleeve, which the JSON does not list); the sheet states the files it used (see section 8).

### 3.7 Bought parts and consumables (ESTIMATE, six with a search-result anchor) - sheet `Bought parts`

AliExpress item pages cannot be read automatically, so the prices come from search-result snippets of 2026-10-14 or are typical prices. The listed item is only a price anchor: check size and specification in the listing yourself.

| Item | Workbook price | Anchor (search snippet, 2026-10-14) |
|---|---|---|
| LiPo cell LP601646 with protection board (2 per light + 1 spare) | $4.50 each | $4.76 for a 400 mAh 071740 cell with PCM, <https://www.aliexpress.com/item/32662761434.html> (different size, 7 x 17 x 40 mm: price class only) |
| Luminus SST-20 on a 10 mm DTP board | $5.40 each | $5.42 for an SST-20 6500K on a 16/20 mm DTP board, <https://www.aliexpress.com/item/32884236179.html> (a 10 mm board may cost more) |
| Green laser module 520 nm, 6 x 12 mm, 1 mW APC | $23.50 each | $23.5 for a 6 mm 520 nm 1 mW APC module, <https://www.aliexpress.com/item/32869119160.html> |
| Round glass window 10 x 1 mm | $2.95 per 5 | $2.95 for 5 pcs flat glass lens, <https://www.aliexpress.com/item/4001014613249.html> (exact size not verified) |
| Screw M1.6 x 4 countersunk | $2.00 per 100 | $1.5 for 100 pcs M1.6 x 3 countersunk, <https://www.aliexpress.com/item/32917852857.html> |
| Thermal transfer tape 0.15 mm | $3.79 per roll | $3.79 for thermal tape, <https://www.aliexpress.com/item/33014898122.html> |
| M2 x 2 set screw (50), split ring 25 mm (20), PTFE wire 28 AWG 2 x 5 m, Kapton tape, foam tape, 5-minute epoxy | $2.00 / $2.00 / $6.00 / $2.50 / $2.50 / $3.50 | typical prices, no anchor found: the searches returned only retailer pages without AliExpress prices |

The search terms and the exact specifications that matter (the 6.0 x 16 x 47 mm cell bay, the 10 mm LED board, the 6 mm laser) are in the sheet. Prices exclude VAT and shipping; the Hidden costs sheet adds both.
The sheet also explains why the laser must be **Class 2** (visible, 1 mW or less continuous, the blink reflex protects the eye; cheap "1 mW" modules often emit more, so ask for a measured value or measure it) and cites EN 50689:2021 for consumer laser products
(<https://ul.com/insights/understand-new-laser-product-safety-standards-europe>, general background <https://en.wikipedia.org/wiki/Laser_safety>).

### 3.8 Tools (ESTIMATE) - sheet `Tools`

17 tools with typical 2026 web-shop prices (soldering iron $35, multimeter $15, laser safety glasses 520 nm $14, caliper $12 ...), no source page; $128.00 for the tools marked "needed" (set "needed" to 0 for what you own),
$100.00 more for the optional ones (microscope, bench supply, laser power meter, taps). A laser power meter is the only way to verify a "1 mW" claim, so consider it if you plan to give lights away.

### 3.9 Spares and placement loss

JLC buys a few more pieces than the board needs (lost by the placement machine) and bills them inside the component price. The extra counts (10 for 0402 resistors and capacitors, 5 for 0603 / 0805, 2 for small semiconductors, 1 for big parts)
are ESTIMATES (JLC publishes no table; the cart shows the real quantity): $7.09 of the $17.16 component cost for 1 light. The bought parts include spares (a third cell, a second LED board, extra screws, spare glass windows) and left-over pack contents:
of the $75.04 for bought parts and consumables (1 light) about $35.97 is pieces you will not use (information row in `Bought parts`). The spare resin parts are one spare print kit in the housing order ($0.60).

## 4. What is an estimate

READ (copied from a page on 2026-10-14): the JLCPCB Standard PCBA fee rows and X-ray tiers; LCSC price tiers and stock for all 33 lines; Basic / Extended type; VAT 21 %, the EUR 150 IOSS limit, the EUR 3 flat duty, the carrier-fee examples; the ECB rate; JLCCNC and JLC3DP technical limits.

ESTIMATE (blue on amber in the workbook):

* the bare PCB price ($25 for 5, range $12 to $40);
* all shipping prices, the number of AliExpress parcels (8, or 3 if you buy the small hardware in one EU shop) and $2 shipping per AliExpress parcel;
* the card / currency fee (1.5 %);
* the tariff rates and customs lines in formal clearance (0 / 6 / 6.5 %, 2 or 1 lines); they only matter for parcels above EUR 150;
* the placement-loss extra pieces;
* whether the $0.46 per board panelisation fee and the X-ray inspection of 2 parts per board apply (both are included to be on the safe side: together about $7.48 for 1 light);
* the complete JLCCNC model (aluminium price, machine rate, minutes, set-ups, tapping, finish prices, anodizing lot fee) and the JLC3DP resin price and minimum (applied to the print kit);
* every price of the bought parts and consumables (six have a search-result anchor, see 3.7) and of all tools;
* the risk reserves (a second order of the same size, factor 1.0 in `Hidden costs!B15:B16`; not part of any total).

Nothing is left unpriced.

## 5. Biggest uncertainties in the total

* **Housing** (1 light $65.96, 5 lights $225.40): a pure estimate until the JLCCNC quote; CNC prices of one-off parts can differ a lot from a model. Get the instant quote first.
* **Shipping and the EUR 150 line:** express versus economy shipping moves the 1-light total by about $55.27; see "The EUR 150 cliff" above.
* **Bare PCB:** at $12 the 1-light total would be $503.45 ($26 less, the parcel also drops below EUR 150), at $40 it would be $548.05 ($18 more); the estimate gives $529.63.
* **AliExpress parcels:** buying the small hardware in one EU shop instead of several AliExpress sellers saves about $26.78 (`Hidden costs`, section 6).
* **X-ray fee:** if the cart does not ask for it, the 1-light total is about $18.28 lower (the fee itself is only $6.56, but without it the JLCPCB goods fall below EUR 150 and the cheaper IOSS route applies).

## 6. What to re-check before you order

1. **Stock and prices.** LCSC prices change weekly. Open the LCSC links in `Main PCB BOM` and look for red lines in the JLC BOM upload. Lines flagged on 2026-10-14:
   C15850 (10 uF 25 V 0805, only 20 pcs at LCSC retail; 7 are needed for 1 light), C485117 (TLV62585 buck converter, 925 pcs), C15195 (10 nF), C1525 (100 nF) and C11702 (1 k) show 0 at LCSC retail but are JLC Basic parts with their own stock
   (C1525: 23,496,493 pcs on the JLC Basic parts list). U4, the ESP32-C3-MINI-1-N4 (C2838502), is marked NRND (not recommended for new designs) by Espressif; the drop-in alternative is the ESP32-C3-MINI-1-H4X (C41349510).
   If a line is rejected, substitute it and update `aurora_parts.py`.
2. **The order files.** Upload only the files of the ready-to-upload folder `order_files/` of the package:
   `1_JLCPCB/` (`Aurora_main_gerbers.zip`, `BOM_JLCPCB.csv`, `CPL_JLCPCB.csv`: the files `tools/kicad/build_all.py` writes to `production/`),
   `2_JLCCNC/` (`Aurora_tray.step` + `Aurora_tray.pdf`, `Aurora_lid.step` + `Aurora_lid.pdf`, `Aurora_marking_class2.dxf`, `Aurora_marking_class3R.dxf`) and
   `3_JLC3DP/` (`Aurora_print_kit.stl`, optional `Aurora_laser_sleeve.stl`). The BOM sheet agrees line by line with what `build_all.py` writes: 33 lines, 60 parts
   (the workbook script only extracts its `bom()` function; `build_all.py` itself re-routes the board and takes long).
3. **JLCPCB cart.** Upload the Gerber, then replace the bare PCB price (`JLCPCB order!B44`), compare the fee lines with section 5 of that sheet (does the cart really list panelisation and X-ray?), copy the "Shipping Estimate" into `Hidden costs`,
   check the part rotations in the placement preview (U4, U1, U2, U3, U5, Q1, Q2, Q4, Q5, J1, LED3) and choose DDP (taxes paid at checkout).
4. **The EUR 150 line** for the JLCPCB parcel (section 2): check the goods value shown in the cart.
5. **Housing quotes and fit.**
   * JLCCNC: type the instant quote into the workbook; ask in the quote chat whether M1.6 threads are possible (not listed on the capability page; fallback: plain 1.25 / 1.6 mm holes and hand taps, see `Tools`);
     the thinnest metal wall is 0.8 mm (LED wire groove to the lid seat; next 0.825 mm at the seam V-ring and 0.875 mm at the front screw tap, `min_walls` / `texture_walls` of `cad/housing_interface.json`), exactly the 0.8 mm minimum;
     anodizing (type II 8-12 um on the drawings; JLCCNC states 8-25 um) grows in the bores and threads (laser bore 6.1 mm, window bore 10.2 mm): the drawings say tolerances apply after finishing and threads are tapped before anodizing and gauged after it (note 3) - ask JLCCNC to confirm.
   * **JLC3DP print kit.** Upload `order_files/3_JLC3DP/Aurora_print_kit.stl` and order one kit per light + one spare kit. The RF window (8.4 x 15.5 x 1.7 mm) and the button cap (5.2 x 3.1 x 2.2 mm) alone are below the
     5 x 5 x 5 / 10 x 2 x 2 mm minimum build size of SLA 8001 resin (the workbook still shows TOO SMALL for them, without red, as the reason for the kit); the kit (29.5 x 16.8 x 12.6 mm) is not.
     The button cap's flange (0.6 mm) stays below the 0.8 mm minimum wall (the RF window's flange is 0.8 mm), so the quote may still warn about thin walls: accept it or ask JLC3DP. Cut the parts off the sprues with flush cutters and file the stubs flat.
6. **Laser.** Buy a module with a stated, measured power (Class 2 = 1 mW or less) and check its size with a caliper (6.0 x 12 mm) before the housing is ordered. The marking text in the design is only true for a module that really is 1 mW or less.
7. **Cells and LED board.** The cells must fit the bay (6.0 x 16 x 47 mm including the protection board); the LED board must be 10 mm. Measure the delivered parts before the housing order.
8. **File names at JLCCNC.** The drawings in `order_files/2_JLCCNC/` are the v0.5 drawings `cad/Aurora_tray_drawing.pdf` (2 pages) and `cad/Aurora_lid_drawing.pdf`, renamed to `Aurora_tray.pdf` and `Aurora_lid.pdf`:
   JLCCNC pairs each drawing with its STEP file by the file name, so upload them under these names together with `Aurora_tray.step` and `Aurora_lid.step`.
9. **Dates.** The fee page revision was "Sep 09, 2026"; if JLC updates it, change the blue fee cells (each has its URL and date). Check the ECB rate and your bank's fee on the day you pay.

## 7. Regenerating and checking the workbook

```
python3 tools/parts_list.py                 # writes Aurora_Parts_List_v0.5.xlsx, recalculates it, runs the checks
python3 tools/parts_list.py --check-only    # re-checks the existing workbook without rewriting it
python3 tools/parts_list.py other.xlsx      # writes somewhere else
python3 tools/parts_list.py --no-recalc     # skips recalculation and checks (no cached values: only for inspection)
```

It needs `openpyxl` and LibreOffice (`soffice`) for the recalculation; set `AURORA_RECALC` to the path of a `recalc.py` if it is not found automatically.
The script prints "all checks passed" when: the workbook has no `#REF!`, `#VALUE!`, `#NAME?`, `#DIV/0!` or `#N/A` cell and no formula without a calculated value;
every total, price and fee cell (more than 450 cells) equals an independent calculation in Python; every LCSC number of `COMPONENTS` is in the BOM sheet with the right quantity and designators; the BOM sheet equals the output of the `bom()` function of `build_all.py`
(only `refkey()` and `bom()` are extracted from that file and run into a temporary folder; `build_all.py` itself is never run); the print kit's STL volume matches its four parts (plus sprues), the kit is above the minimum build size, one kit per light + one spare is ordered
and none of its parts is ordered a second time on its own; and every `order_files/` path in the workbook names a file of the package layout, with no text pointing to an outdated file location.
To change prices, edit the blue cells in the workbook, or the tables near the top of `tools/parts_list.py`, and regenerate.

## 8. Geometry source

The housing data is read from `cad/housing_interface.json`, written by the final v0.5 housing build (volumes and masses of the tray, lid, RF window, button cap, spacer ring and antenna spacer, the tray bounding box,
the PCB outline, the parameters and the wall checks), and from the STL files in `cad/`: the bounding boxes of all parts and the volumes of `Aurora_print_kit.stl` and `Aurora_laser_sleeve.stl`, which the JSON does not list.
The sheet `Housing` prints the source (`cad/housing_interface.json (version 0.5) + cad/*.stl`). If the JSON is not found the script falls back to an embedded snapshot of the same numbers and says so; a missing STL file is replaced
by its snapshot entry and named in the same source line.
