<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
# FlashKa Keychain v0.6 - parts list and cost workbook: reading notes

| | |
|---|---|
| Workbook | `FlashKa_Parts_List_v0.6.xlsx` (repository root) |
| Generator | `tools/parts_list.py` (run `python3 tools/parts_list.py`, see section 7) |
| Price-check date | **2026-10-18** (v0.6 check). Readings that did not change since v0.5 keep the date they were read: **2026-10-14**. The JLCCNC, JLC3DP and Alps switch pages were read on 2026-10-16 (v0.6 parts research). |
| Pages not read | The JLCPCB and LCSC pages of the two new parts, C115357 and C25104, could not be read on 2026-10-18. Those two lines are **ESTIMATES** (sections 3.2, 3.10 and 4). |
| Exchange rate | 1.1188 USD per EUR (ECB euro reference rate of 13 Oct 2026, not refreshed in v0.6; input cell `Summary!B6`) |
| Delivery to | Lithuania (EU): VAT 21 %, EU customs rules of 2026 |

This file explains (1) how to read the workbook, (2) the result and what changed from v0.5, (3) where every number comes from, with URL and date,
(4) which numbers are only estimates and how to replace each with a real quote, (5) what is most uncertain and (6) what you must re-check before you order.
It does not repeat every cell of the workbook: each price row in the workbook carries its own source URL and date.

## 1. How to read the workbook

**The idea.** The light is made from six groups of things, bought from different places. The workbook prices every group, then adds the costs people forget
(shipping of every separate parcel, 21 % VAT, the new EU customs duty, bank fees) so that the Summary shows what really leaves your bank account.

| Group | Where you buy it | Sheet |
|---|---|---|
| Circuit board, soldered and tested by the factory | jlcpcb.com (PCB + assembly) | `JLCPCB order`, `Main PCB BOM` |
| Aluminium body (tray + lid, laser-marked) and the three stainless caps | jlccnc.com | `Housing` |
| The seven small see-through resin parts (ordered as one print kit) | jlc3dp.com | `Housing` |
| Cells, LED board, laser module, glass, screws, ring, wire, tapes, silicone pads, adhesives | AliExpress or an EU web shop | `Bought parts` |
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
| "TOO SMALL" (sheet `Housing`, section 8) | the part alone is below the printer's minimum size; red only if such a part is ordered on its own (the RF window insert is ordered inside the print kit, see section 3.6) |

**Two scenarios.** Scenario A = you build **1** light, scenario B = you build **5** lights (`Summary!B7` and `Summary!B8`: type any other numbers, for example 2).
The JLC minimums are built in: JLCPCB sells at least 5 bare boards per design (in steps of 5) and assembles from 2 boards, so one light still pays for 2 assembled boards.
The Summary shows totals in USD and EUR, per light, and the extra cost of each additional light (the set-up and stencil fees, the anodizing lot fee, the marking set-up and most shipping are paid once).
The Summary also has a group "What changed from v0.5" with the cost delta (section 2).

**Putting in real numbers.** Every total is a formula, so you only change inputs:

| What | Cell |
|---|---|
| bare PCB price shown by JLCPCB after the Gerber upload (price for 5 boards) | `JLCPCB order!B44` |
| JLCCNC instant quote for tray + lid (with finish and marking, no shipping), scenario A / B | `Housing!B87` / `Housing!C87` |
| JLCCNC instant quote for the three stainless caps (no shipping), scenario A / B | `Housing!C99` / `Housing!E99` |
| JLC3DP instant quote for the print kits (no shipping), scenario A / B | `Housing!E116` / `Housing!G116` |
| stainless caps ordered (1) or the resin caps of the print kit used instead (0) | `Housing!B92` |
| laser marking ordered at JLCCNC (1) or an adhesive label instead (0) | `Housing!B30` |
| surface finish of the aluminium (drop-down) | `Housing!B41` |
| "Shipping Estimate" of each cart (economy / express, A and B) | `Hidden costs!B20:E22` |
| shipping mode 1 = economy, 2 = express | `Hidden costs!B11` |
| price of any bought part | column F of `Bought parts` |
| exchange rate | `Summary!B6` |
| lights built, scenario A / B | `Summary!B7` / `Summary!B8` |

Leave a quote cell empty to use the workbook's own estimate; type a number to override it. The Summary column "Where to replace it with a real number" names the cell for each row.

## 2. Result (price check 2026-10-18)

| USD (EUR) | 1 light | 2 lights (B = 2) | 5 lights |
|---|---|---|---|
| 1. PCB + assembly (JLCPCB), before shipping | $174.33 (EUR 155.82) | $174.33 (EUR 155.82) | $194.69 (EUR 174.01) |
| 2. Housing (aluminium + stainless caps + resin print kit) | $122.56 (EUR 109.54) | $187.52 (EUR 167.60) | $382.39 (EUR 341.78) |
| 3. Bought parts (cells, LED board, laser, glass, screws, ring) | $56.75 (EUR 50.72) | $94.65 (EUR 84.60) | $211.30 (EUR 188.86) |
| 4. Consumables (wire, tapes, silicone pads, adhesives) | $27.79 (EUR 24.84) | $27.79 (EUR 24.84) | $27.79 (EUR 24.84) |
| 5. Shipping, VAT, customs duty, carrier and card fees | $238.78 (EUR 213.43) | $290.99 (EUR 260.09) | $378.82 (EUR 338.60) |
| **Total for the lights** | **$620.21 (EUR 554.35)** | **$775.28 (EUR 692.95)** | **$1,194.99 (EUR 1,068.10)** |
| **Per light** | **$620.21 (EUR 554.35)** | **$387.64 (EUR 346.48)** | **$239.00 (EUR 213.62)** |
| Tools, one-time (only the tools marked needed) | $135.00 (EUR 120.66) | same | same |
| Risk reserve, not in any total: a second PCB + assembly order | $253.73 (EUR 226.79) | | |
| Risk reserve, not in any total: a second housing order | $180.18 (EUR 161.04) | | |

The Summary sheet shows the 1-light and the 5-light columns. The 2-light column is the same workbook with `Summary!B8` set to 2 (checked: the recalculated workbook equals the Python model in all 515 compared cells).

Item 5 in detail (1 light / 2 lights / 5 lights): shipping $81.00 / $84.00 / $84.00, VAT $97.11 / $121.99 / $194.12, customs duty and carrier fees $53.70 / $76.41 / $88.00, card fee $6.97 / $8.58 / $12.70.

**Change from v0.5** (same scenarios, same exchange rate; v0.5 values from its workbook of 2026-10-14):

| USD | v0.5, 1 light | v0.6, 1 light | change | v0.5, 5 lights | v0.6, 5 lights | change |
|---|---|---|---|---|---|---|
| 1. PCB + assembly | $169.31 | $174.33 | +$5.02 | $196.67 | $194.69 | -$1.98 |
| 2. Housing | $65.96 | $122.56 | +$56.60 | $225.40 | $382.39 | +$156.99 |
| 3. Bought parts | $56.75 | $56.75 | +$0.00 | $211.30 | $211.30 | +$0.00 |
| 4. Consumables | $18.29 | $27.79 | +$9.50 | $18.29 | $27.79 | +$9.50 |
| 5. Shipping, VAT, customs, fees | $219.32 | $238.78 | +$19.46 | $329.89 | $378.82 | +$48.93 |
| **Total for the lights** | **$529.63** | **$620.21** | **+$90.58** | **$981.55** | **$1,194.99** | **+$213.43** |
| **Per light** | $529.63 | $620.21 | +$90.58 | $196.31 | $239.00 | +$42.69 |

In EUR the 1-light total goes from EUR 473.39 to EUR 554.35, the 5-light total from EUR 877.33 to EUR 1,068.10.

* **Board (PCB + assembly).** 34 BOM lines, 68 placements, 232 solder joints per board (v0.5: 33, 60, 217): three push buttons (SW1-SW3, Alps SKRKAEE020) instead of the one side button S1, a second ring LED (LED4), five more resistors (R30-R34).
  One more unique part means one more feeder-loading fee ($1.53), and the board has three X-ray parts instead of two. With five lights the X-ray price per part drops to the next tier (15 inspected parts instead of 10), so the 5-light PCB total is slightly lower than in v0.5.
* **Housing, +$56.60 for one light.** Aluminium tray + lid $64.76 -> $93.36: laser marking of 4 faces +$13.00 (4 x $2.00 per face and $5.00 marking set-up), more set-ups +$10.50 (tray 3 -> 5, lid 2 -> 3, $3.50 each),
  machining and material +$5.10 (the lid is now a 5.2 mm part with bosses, complexity factors 1.00 -> 1.10 and 1.25 -> 1.30, fine-feature minutes, see section 3.6). The three stainless caps are new: $28.00 (ESTIMATE). The print kit now holds seven parts but is still priced at the minimum: $1.20, as in v0.5.
* **Bought parts.** Unchanged (cells, LED board, laser, glass, screws, ring).
* **Consumables, +$9.50.** Two silicone hold-down pad sheets ($3.50 each) and a tube of silicone adhesive ($2.50), all ESTIMATES.
* **Shipping, VAT, customs, fees, +$19.46 for one light.** Mostly VAT on the dearer housing and JLCPCB order (+$14.94), a second customs line for the stainless caps and a bigger card fee. Shipping is unchanged (same three JLC parcels and 8 AliExpress parcels).

**Biggest cost items (1 light).**

1. Shipping, VAT, duty and fees: 39 % of the total ($238.78). Every shop ships its own parcel: three JLC parcels and (by default) 8 AliExpress parcels, each with its own shipping and its own flat EUR 3 customs duty.
2. JLCPCB assembly fees: $132.01 for 1 light (set-up $51.12, feeder loading $52.02, stencil $16.42, X-ray $9.84, everything else together $2.61). They are mostly paid once, which is why 5 lights cost only $4.95 more in fees.
3. Aluminium tray + lid: $93.36 for 1 set, $302.79 for 5 sets (estimate; the set-ups, the anodizing lot fee and the marking set-up are paid once per order). The three stainless caps add $28.00 / $76.00 (estimate).
4. Laser module ($23.50 each), then the two cells and the LED board.

The resin parts cost little: JLC3DP prints them as one print kit, $1.20 for 1 light (2 kits incl. the spare), $3.60 for 5 lights (6 kits).
Every additional light after the first costs about $143.69 more (the Summary shows it).

**The EUR 150 cliff.** Up to EUR 150 goods value per parcel the EU collects VAT at the checkout (IOSS) and a flat EUR 3 duty per customs line. Above EUR 150 the parcel needs formal customs
clearance and the carrier charges a handling fee of about EUR 15. The JLCPCB order for 1 light has goods of about **EUR 155.82** ($174.33 before shipping), i.e. EUR 5.82 above the line, so the workbook routes it through formal clearance,
which costs about $10.07 more than the IOSS route (`Hidden costs`, section 6). If the real PCB and component prices are $6.51 or more lower in total, the parcel falls below the line and the bill drops by about $10.07 (plus the lower goods).
With 5 lights both the JLCPCB order (EUR 174.01) and the JLCCNC order (EUR 338.57) are above the line. Keep the three JLC orders as three separate parcels.

## 3. Where every number comes from

"READ" = copied from the vendor page on the date given. "ESTIMATE" = no public price or not readable; the cell is blue on amber and explained in its note column.
"COMPUTED" = formula from READ inputs. Sections 3.1 to 3.10 follow the order of the sheets.

### 3.1 JLCPCB assembly fees (READ 2026-10-14, not refreshed in v0.6) - sheet `JLCPCB order`, section 5

Fee page: <https://jlcpcb.com/help/article/pcb-assembly-price>, shows "Last updated on Sep 09, 2026", read 2026-10-14. The board has parts on both sides, so it needs **Standard PCBA**, double-sided
(Economic PCBA is single-sided only and charges $3.07 per Extended part; Standard charges the feeder fee per unique part instead, Basic or Extended alike, and has no separate engineering fee).
The page was not read again in v0.6: every rate is unchanged, only the quantities follow the new board (232 joints per board, 34 unique parts, 3 X-ray parts per board).

| Fee | Rate | Used for this order |
|---|---|---|
| Set-up fee (Standard PCBA) | $25.56 per side | 2 sides = $51.12 |
| Stencil (Standard PCBA) | $8.21 per side | 2 sides = $16.42 |
| SMT assembly | $0.0016 per solder joint | 232 joints per board x boards assembled |
| Feeder loading | $1.53 per unique part (Basic and Extended) | 34 unique parts = $52.02 |
| Confirm parts placement (optional, recommended) | $0.45 per order | included |
| X-ray inspection ("required for components such as BGA, QFN, and other leadless packages") | per part, tiered by the order total: 1-10 $1.64, 11-50 $0.82, 51-200 $0.49, 201-500 $0.33, 501-1000 $0.25, 1001-3000 $0.16, 3001+ $0.082 | 3 parts per board (ESP32 module U4, ring LEDs LED3 and LED4): ESTIMATE of the count (v0.5: 2) |
| Panelisation of small boards (<https://jlcpcb.com/help/article/Panelizing-your-PCB-for-Assembly>) | minimum $0.46 per board | included (assumed to apply, see section 4) |
| Packing | $0.50 + $0.00003 per cm2 | included |
| Hand-soldering $3.58, pre-reflow $0.016 per joint, single-board surcharge $0.48, fixture $8.21, storage $4.93, large board $57.46 (above 650 cm2) | listed on the page | quantity 0: not needed for this board |

Other JLCPCB pages used: assembly from 2 boards <https://jlcpcb.com/pcb-assembly>; 5 bare boards minimum and the price calculator <https://cart.jlcpcb.com/quote>;
capabilities (4 layers, 0.8 mm, ENIG) <https://jlcpcb.com/capabilities/pcb-capabilities>; extra pieces for placement loss are billed inside the component price <https://jlcpcb.com/help/article/pcb-assembly-faqs-part-2>.

### 3.2 Components at LCSC / JLC (READ for 32 lines, ESTIMATE for 2) - sheet `Main PCB BOM`

Every price tier and the retail stock of the 32 READ lines were read on 2026-10-14 from `https://www.lcsc.com/product-detail/<LCSC number>.html`; each row of the sheet links to that page (column E) and prints the URL and date (column AJ).
The library type (Basic / Extended) was read on `https://jlcpcb.com/partdetail/<LCSC number>`; the Basic parts list is at <https://jlcpcb.com/parts/basic_parts>.
The unit price is the tier that matches the quantity JLC has to buy (quantity per board x boards + extra pieces for placement loss).

The BOM has **34 lines, 68 placements, 232 solder joints per board**; it is derived from `COMPONENTS` in `tools/kicad/flashka_parts.py` with the same grouping and ordering as `build_all.py`
(lines with an empty LCSC number or `dnp` are skipped) and equals `production/BOM_JLCPCB.csv` (= `order_files/1_JLCPCB/BOM_JLCPCB.csv`) line by line.
The joint count of each line is the pad count of its footprint in the routed board `kicad/FlashKa_main/FlashKa_main.kicad_pcb`.
J2 (cells), J3 (LED) and J5 (laser) are wire pads without an LCSC number: JLCPCB does not assemble them, you solder the wires by hand. 20 lines are Basic, 14 are Extended (counting the two assumed types)
(in Standard PCBA both pay the same feeder fee, so the split does not change the price; the input for an extra Extended-part fee, `JLCPCB order!B56`, is 0).
Retail stock at LCSC is not JLC's own warehouse stock; the JLC BOM upload shows the stock that matters.

**New in v0.6.** SW1-SW3 Alps SKRKAEE020 (C115357) x3 replace S1 (SKRTLAE010, C110293, removed); LED4 is a second NH-B1010RGBT-HF (C2874113, now x2 with LED3);
R30 1 k (C11702), R31 2.2 k (C25879), R32 330 ohm (C25104; R23 changes from 1 k to 330 ohm as well), R33 and R34 100 ohm (C25076). Four of these numbers (C2874113, C11702, C25879, C25076) were already in v0.5 and keep their v0.5 readings (2026-10-14).
The two lines **C25104 (R23, R32) and C115357 (SW1, SW2, SW3)** are new numbers whose pages could not be read on 2026-10-18: their tiers, stock and library type are ESTIMATES (section 3.10).
The tiers of C115357 are those of its sibling, the Alps SKRPABE010 (C115360), read on LCSC on 2026-10-16 ($0.0759 at 10 pieces, $0.0616 at 100, stock 49,490, Extended on JLCPCB);
the tiers of C25104 are those of the 5.1 k resistor C25905 of the same UNI-ROYAL 0402 series. Together they cost $0.56 for 1 light and $1.26 for 5 lights (of $17.32 and $32.72 for all components), so doubling both prices would add only $0.56 (1 light) or $1.26 (5 lights) before VAT.

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
| [C2874113](https://www.lcsc.com/product-detail/C2874113.html) | LED3, LED4 | NH-B1010RGBT-HF | Extended | 2 | 345,020 |
| [C15127](https://www.lcsc.com/product-detail/C15127.html) | Q1 | AO3401A | Basic | 1 | 164,910 |
| [C5224240](https://www.lcsc.com/product-detail/C5224240.html) | Q2, Q4, Q5 | 2N7002W-7-F-ES | Extended | 3 | 17,000 |
| [C25905](https://www.lcsc.com/product-detail/C25905.html) | R1, R2 | 0402WGF5101TCE | Basic | 2 | 2,302,500 |
| [C25890](https://www.lcsc.com/product-detail/C25890.html) | R3 | 0402WGF3301TCE | Basic | 1 | 867,600 |
| [C25764](https://www.lcsc.com/product-detail/C25764.html) | R10 | 0402WGF2003TCE | Basic | 1 | 1,520,700 |
| [C25792](https://www.lcsc.com/product-detail/C25792.html) | R12 | 0402WGF4702TCE | Basic | 1 | 3,114,700 |
| [C25744](https://www.lcsc.com/product-detail/C25744.html) | R8, R9, R13, R18, R21, R22 | 0402WGF1002TCE | Basic | 6 | 2,846,900 |
| [C25879](https://www.lcsc.com/product-detail/C25879.html) | R14, R31 | 0402WGF2201TCE | Basic | 2 | 586,000 |
| [C4109](https://www.lcsc.com/product-detail/C4109.html) | R16 | 0402WGF2001TCE | Basic | 1 | 5,789,500 |
| [C11702](https://www.lcsc.com/product-detail/C11702.html) | R19, R30 | 0402WGF1001TCE | Basic | 2 | 0 **retail 0** |
| [C25104](https://www.lcsc.com/product-detail/C25104.html) | R23, R32 | 0402WGF3300TCE | Basic (assumed) | 2 | not read |
| [C25076](https://www.lcsc.com/product-detail/C25076.html) | R24, R25, R33, R34 | 0402WGF1000TCE | Basic | 4 | 4,360,400 |
| [C26083](https://www.lcsc.com/product-detail/C26083.html) | R27, R28 | 0402WGF1004TCE | Basic | 2 | 541,000 |
| [C25741](https://www.lcsc.com/product-detail/C25741.html) | R7, R11, R15, R17, R20, R26, R29 | 0402WGF1003TCE | Basic | 7 | 3,791,500 |
| [C92740](https://www.lcsc.com/product-detail/C92740.html) | RS1 | MS05W2F200MT5E | Extended | 1 | 4,880 |
| [C77130](https://www.lcsc.com/product-detail/C77130.html) | RT1 | NCP15WF104F03RC | Extended | 1 | 298,120 |
| [C431540](https://www.lcsc.com/product-detail/C431540.html) | S2 | MSK12C02 | Extended | 1 | 170,330 |
| [C115357](https://www.lcsc.com/product-detail/C115357.html) | SW1, SW2, SW3 | SKRKAEE020 | Extended (assumed) | 3 | not read |
| [C12044](https://www.lcsc.com/product-detail/C12044.html) | U1 | TP4057-42-SOT26-R | Extended | 1 | 32,025 |
| [C485117](https://www.lcsc.com/product-detail/C485117.html) | U2 | TLV62585DRLR | Extended | 1 | 925 **low** |
| [C181502](https://www.lcsc.com/product-detail/C181502.html) | U3 | TLV333IDCKR | Extended | 1 | 18,425 |
| [C2838502](https://www.lcsc.com/product-detail/C2838502.html) | U4 | ESP32-C3-MINI-1-N4 | Extended | 1 | 8,387 |
| [C841192](https://www.lcsc.com/product-detail/C841192.html) | U5 | RT9080-33GJ5 | Extended | 1 | 27,375 |

### 3.3 Bare PCB (ESTIMATE) - sheet `JLCPCB order`, section 4

JLCPCB shows the price of the bare board only after the Gerber upload at <https://cart.jlcpcb.com/quote>, so the workbook uses **$25 for 5 boards** (4 layers, 0.8 mm, ENIG, 24.0 x 16.5 mm; the range $12 to $40 is shown for information).
Anchors: a 100 x 100 mm 4-layer board x 5 is about $32.90 (<https://pcbsync.com/pcb-prototype-services-compared/>, vendor not named); "$16 for ENIG on small runs" (a 2020 forum post, <https://forums.ghielectronics.com/t/enig-or-hasl-for-pcb-finish/23438>);
a 24 x 16.5 mm board is far smaller than 100 x 100 mm. Replace the estimate with the real price in `JLCPCB order!B44`. The board outline (24.0 x 16.5 mm, 1.3 mm chamfers, 3.94 cm2) comes from `cad/housing_interface.json` (`pcb_outline`).
Both prices were set on 2026-10-14 and are unchanged.

### 3.4 Shipping (ESTIMATE) - sheet `Hidden costs`, section 2

JLC publishes no rate table; the cart shows a "Shipping Estimate" after you enter the address. Anchors for a small JLCPCB parcel: DHL Express $21.50, EuroPacket $6.50, Global Standard Direct Line $1.50
(Chiptron, 10 Jun 2025, <https://chiptron.eu/jlcpcb-reduces-shipping-costs-pcb-order-with-shipping-worth-bad-beer/>); FedEx about $16 to Spain (EEVblog 2024,
<https://eevblog.com/forum/manufacture/jlcpcb-pcb-assembly-optimal-shipping-for-eu>). The workbook defaults to express ($21.50 JLCPCB, $22 / $25 JLCCNC for 1 / 5 sets, $21.50 JLC3DP) because DDP (taxes paid at checkout) works most reliably;
economy ($6.50 JLCPCB, $7 / $9 JLCCNC for 1 / 5 sets, $6.50 JLC3DP) is selectable in `Hidden costs!B11` and lowers the 1-light total by about $55.27 (5 lights: $57.67). JLCCNC and JLC3DP shipping are guesses from weight
(JLCCNC shows it only on the invoice; the stainless caps add a few grams). AliExpress: $2 per seller parcel and 8 parcels are assumptions. None of this changed in v0.6.

### 3.5 EU VAT, customs duty, bank fee, exchange rate - sheet `Hidden costs`, sections 1 and 3 to 5

| Input | Value | Status | URL (read 2026-10-14) |
|---|---|---|---|
| VAT Lithuania | 21 % | READ | <https://jlcpcb.com/help/article/EU-VAT-E-commerce-Rules-%26-Adjustments> |
| IOSS limit: goods value per parcel (VAT collected at checkout) | EUR 150 | READ | same page |
| Flat customs duty on low-value parcels, 1 Jul 2026 to 1 Jul 2028 | EUR 3 per customs line (item category) per parcel | READ | <https://jlcpcb.com/help/article/eu-customs-reform-faq>, <https://trade.ec.europa.eu/access-to-markets/en/news/eu-applies-eu3-customs-duty-item-low-value-e-commerce-consignments>, JLC3DP note <https://jlc3dp.com/news/eu-customs-reform2026> |
| Carrier fee in formal clearance (above EUR 150) | max(EUR 15, 2 % of VAT + duty); examples on the page: DHL Germany 2 % min EUR 15, UPS 3 % min EUR 15.70, FedEx 2.5 % min EUR 15 | READ (examples) | <https://jlcpcb.com/help/article/eu-customs-reform-faq> |
| Tariff rates in formal clearance | JLCPCB 0 %, JLCCNC 6 % (aluminium articles, HS 7616 99 90; the whole parcel including the steel caps), JLC3DP 6.5 % (plastic articles, HS 3926 90), AliExpress 0 % | **ESTIMATE** (assumed HS codes; the invoice decides) | - |
| Customs lines per parcel | JLCPCB 2, JLCCNC 2 (aluminium parts + stainless caps; 1 if the caps are not ordered, `Housing!B92` = 0), JLC3DP 1, each AliExpress parcel 1 | ESTIMATE | - |
| Exchange rate | 1.1188 USD per EUR | READ (ECB, 13 Oct 2026) | <https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/eurofxref-graph-usd.en.html> |
| Card / currency conversion fee on the JLC payments | 1.5 % | **ESTIMATE** (0-3 % depending on your bank) | - |

Not included: a unified EU customs handling fee of about EUR 2 per parcel that the EU plans for around Nov 2026 (not final when this was written), your own time, a second PCB or housing round (shown as risk reserve).

### 3.6 Housing (ESTIMATE) - sheet `Housing`

The real price of CNC and resin parts appears only after the STEP / STL upload, and JLCCNC publishes no per-part price at all, so the workbook estimates every housing price with a stated method.
Type the instant quotes into `Housing!B87` / `Housing!C87` (tray + lid, scenario A / B), `Housing!C99` / `Housing!E99` (the three stainless caps) and `Housing!E116` / `Housing!G116` (print kits) when you have them.
The housing costs $122.56 for 1 light and $382.39 for 5 lights: aluminium $93.36 / $302.79, stainless caps $28.00 / $76.00, resin print kits $1.20 / $3.60.

* **JLCCNC aluminium tray + lid.** Method (sheet sections 2 to 6): cost of one part = aluminium block (bounding box + 2 mm on every side, 6061 at $8 per kg, you pay for the whole block)
  + machining (material to remove / 6 cm3 per min + fine-feature minutes, x $0.60 per min x complexity factor) + $0.25 per thread + finish + laser marking;
  the set-ups ($3.50 each: tray 5, lid 3), the anodizing lot fee ($8.00) and the marking set-up ($5.00) are paid once per order. All of these parameters are ESTIMATES
  (the machine rate was calibrated in v0.5 so that one tray + lid costs about what the v0.4 estimate gave). v0.6 keeps every v0.5 parameter (aluminium price, density, allowance, removal rate, machine rate, tapping, finish prices, lot fee)
  and changes only what the new design changes (table below). JLCCNC publishes no price list (<https://jlccnc.com/blog/cnc-machining-cost-factors> only explains the cost factors).
  Facts READ from JLCCNC (2026-10-14, the capabilities and finishes pages again on 2026-10-16): 6061-T6, bead blast + black anodize as one combined option, anodize 8-25 um, ISO 2768-m, threads supported but M1.6 not listed,
  minimum metal wall 0.8 mm (absolute minimum 0.5 mm), STEP mandatory + drawing PDF with identical file names, standard lead time from 3 working days, quote within 24 h
  (<https://jlccnc.com/capabilities/cnc-machining-service>, <https://jlccnc.com/help/article/cnc-machining-ordering-guidelines>, <https://jlccnc.com/finishes>, <https://jlccnc.com/cnc-machining-quote>).
  The finish prices and lot fees per finish are ESTIMATES.
  Upload: `order_files/2_JLCCNC/FlashKa_tray.step` + `FlashKa_tray.pdf` and `FlashKa_lid.step` + `FlashKa_lid.pdf` (the drawings `cad/FlashKa_tray_drawing.pdf`, 2 pages, and `cad/FlashKa_lid_drawing.pdf`, renamed to the STEP names).
* **What v0.6 changes in the aluminium estimate.**

| | v0.5 | v0.6 | Why |
|---|---|---|---|
| Tray / lid volume | 8670.7 / 2238.3 mm3 | 8401.2 / 2643.3 mm3 | `volumes_mm3` of `cad/housing_interface.json`: knurl and side grooves gone, floor holes and RF window added |
| Lid size | 90.2 x 19.9 x 1.5 mm | 90.2 x 20.0 x 5.2 mm | the lid carries two hold-down bosses (up to 5.2 mm tall) |
| Stock block tray / lid | 47.2 / 12.4 cm3 | 47.2 / 20.8 cm3 | bounding box + 2 mm on every side |
| Fine-feature time tray / lid | 36.0 / 8.0 min | 38.1 / 7.5 min | table below |
| Machining time tray / lid | 42.4 / 9.7 min | 44.6 / 10.5 min | material to remove / 6 cm3 per min + fine-feature time |
| Complexity factor tray / lid | 1.00 / 1.25 | 1.10 / 1.30 | ESTIMATE: the frames of the skin wrap round the rounded corners and the two sides (indexed or 4th-axis work), where v0.5 had four straight grooves; the 1.5 mm lid plate now also carries bosses and a 0.6 mm lip |
| Set-ups tray / lid | 3 / 2 | 5 / 3 | ESTIMATE: the skin needs the side faces (top, bottom, -Y, +Y, ends) |
| Laser marking | none | 4 faces, $2.00 per face + $5.00 per order | new, see the next bullet |
| One set (scenario A) | $64.76 | $93.36 | +$28.60 |
| Five sets (scenario B) | $221.80 | $302.79 | +$80.99 |

  The change for one set, +$28.60, is laser marking +$13.00 (4 x $2.00 per face + $5.00 set-up), more set-ups +$10.50 (tray 3 -> 5, lid 2 -> 3), and machining and material +$5.10
  (the taller lid block, the fine-feature minutes and the two complexity factors). For five sets it is +$80.99: marking +$45.00, set-ups +$10.50, machining and material +$25.49.

  The fine-feature time is the part of the estimate that needs an explanation. v0.5 priced all fine work (grooves, holes, pockets) as one lump per part: tray 36 min, lid 8 min.
  v0.6 keeps the lump, takes out the features that no longer exist and adds the new ones. V-groove work is counted in millimetres at ONE rate (6 min per metre, i.e. $3.60 per metre before the complexity factor)
  for the grooves that go and for the grooves that come, so the groove part of the change follows the real geometry: the v0.6 lengths are read from `skin_layout` of `cad/housing_interface.json`
  (19 entries = 6 frames in 11 pieces and 8 stringers: tray 646.5 mm, lid 220.2 mm, together 867 mm against 1598 mm of grooves in v0.5). The other lines are typed-in minutes (ESTIMATES).

| Feature | Tray | Lid | Unit | Tray (min) | Lid (min) |
|---|---|---|---|---|---|
| v0.5 fine-feature time (one lump per part) | 36 | 8 | min | 36.0 | 8.0 |
| minus the v0.5 diamond knurl | -717 | -717 | mm of V-groove | -4.3 | -4.3 |
| minus the four v0.5 side grooves | -164 | 0 | mm of V-groove | -1.0 | 0.0 |
| plus the v0.6 skin seams (frames and stringers, V 90 deg, 0.25 mm deep) | 646.5 | 220.2 | mm of V-groove | +3.9 | +1.3 |
| plus the floor holes: main bore with counterbore, two slide holes with chamfer | 3 | 0 | min | +3.0 | 0.0 |
| plus the floor RF window 5.1 x 14.0 mm | 1 | 0 | min | +1.0 | 0.0 |
| plus the 0.6 mm lid rabbet and the 0.3 mm gussets in the cavity corners | 1.5 | 1 | min | +1.5 | +1.0 |
| plus the two hold-down bosses under the lid | 0 | 1.5 | min | 0.0 | +1.5 |
| minus the S1 hole, thumb dish and ledge gap | -2 | 0 | min | -2.0 | 0.0 |
| **Fine-feature time, v0.6** | | | | **38.1** | **7.5** |

* **Laser marking (new in v0.6, ESTIMATE).** The warning text and the artwork are laser-marked after anodising on four faces: the lid (`FlashKa_marking_lid_class2.dxf`, or `FlashKa_marking_lid_class3R.dxf` only for a module that measures above 1 mW)
  and the tray's bottom, -Y and +Y faces (`FlashKa_marking_bottom.dxf`, `FlashKa_marking_minus_y.dxf`, `FlashKa_marking_plus_y.dxf`), all in `order_files/2_JLCCNC/`. JLCCNC lists laser marking as a finish (<https://jlccnc.com/finishes>, read 2026-10-16)
  but publishes no price, so the workbook uses $2.00 per marked face and $5.00 per order for loading the artworks (`Housing!B31`, `Housing!B32`): $13.00 for 1 light and $45.00 for 5 lights.
  Set `Housing!B30` to 0 if JLCCNC does not offer marking for your order and stick a printed label with the same text on the lid instead (a few cents, not in the workbook).
  The Class 2 text is only true for a module that really is 1 mW or less.
* **Stainless caps (new in v0.6, ESTIMATE).** `FlashKa_cap_main` (1 per light) and `FlashKa_cap_slide` (2 per light) are turned from SUS304 stainless steel and bead blasted, with 1 spare of each per order:
  2 main + 3 slide caps for 1 light, 6 + 11 for 5 lights. READ facts (<https://jlccnc.com/cnc-machining>, <https://jlccnc.com/finishes>, <https://jlccnc.com/capabilities/cnc-machining-service>,
  <https://jlccnc.com/cnc-machining-service/cnc-turning>, read 2026-10-16): SUS304 is the only stainless grade; bead blasting, brushing and laser marking are offered for it, passivation and polishing are not; the minimum order is one piece;
  the minimum part size is 5 x 5 x 1 mm and the minimum turned diameter 3 mm; instant quotes work up to 20 pieces (more goes to a manual quote); SUS304 can be built in as little as 5 days.
  **JLCCNC publishes no per-part price**, only the headline "CNC milling/turning from $5.00" (<https://jlccnc.com/>).
  *Reasoning for the estimate.* The caps are tiny (flange dia 6.6 and 5.0 mm, 7.0 mm long, heads dia 5.8 and 3.4 mm; 0.86 g and 0.32 g of steel), so the material costs a few cents and the price is set by the set-up,
  the programming and the bead blasting of each part number. The workbook therefore uses **$8.00 for the first piece of each cap type** (above the $5.00 headline: stainless, a domed head, a blast pass)
  and **$4.00 for each further piece of the same cap in the same order** (set-up already paid, about half of the first piece; `Housing!B93`, `Housing!B94`).
  Main cap: 2 pieces = $12.00 (1 light), 6 pieces = $28.00 (5 lights). Slide cap: 3 pieces = $16.00, 11 pieces = $48.00. Together $28.00 / $76.00.
  Twice these prices would raise the totals by $34.39 / $98.94 (VAT included), half these prices would lower them by $17.19 / $49.47.
  *Confirm with the instant quote; if refused, any CNC service (PCBWay, Xometry, a local shop) can make them from the same STEP + PDF, or use the resin caps from the print kit.*
  The size is the open point: the caps are 7.0 mm long, and the JLCCNC FAQ says rotary-axis metal parts must be longer than 20 mm and thicker than 4 mm, while its capabilities page allows 5 x 5 x 1 mm and its turning page 3 mm diameter.
  The resin copies of the same three caps are in the print kit in every case, so the fallback costs nothing extra: set `Housing!B92` to 0 and the totals drop by $37.79 (1 light) / $98.94 (5 lights), including VAT and one customs line less.
  If another CNC service quotes the caps, type its price into `Housing!C99` / `Housing!E99` and leave `Housing!B92` at 1.
* **JLC3DP print kit (SLA 8001 translucent).** JLC3DP gets ONE part, `order_files/3_JLC3DP/FlashKa_print_kit.stl`: the RF window insert, LED spacer ring, antenna spacer with floor plug, light-pipe tube, resin main cap and two resin slide caps
  (seven parts) joined by 1 mm sprues (57.2 x 16.8 x 14.2 mm, 1576.2 mm3 = the seven parts' 1561.8 mm3 + 14.4 mm3 of sprues),
  because the RF window insert (8.4 x 15.5 x 1.7 mm) alone is below the minimum build size. One kit per light + one spare kit: 2 kits for 1 light, 6 for 5 lights; you cut the parts apart at home.
  The kit is priced from its own STL volume with the same model as single parts: $0.30 per cm3 (headline "SLA from $0.30" on <https://jlc3dp.com/>) with an assumed minimum of $0.60 per part (<https://jlc3dp.com/3d-printing-quote>): ESTIMATE.
  Even the kit (1.58 cm3, $0.47 by volume) is so small that the minimum decides, so the JLC3DP order is $1.20 for 1 light and $3.60 for 5 lights, the same as in v0.5 although the kit now holds seven parts instead of four.
  The seven parts stay in the sheet as information rows with quantity 0 ("included in the print kit"). The three resin caps are the fallback of the stainless caps; the laser sleeve
  (`order_files/3_JLC3DP/FlashKa_laser_sleeve.stl`, 10 x 6 x 6 mm, big enough on its own) is a separate optional print with quantity 0 unless your laser module is 4.5 mm.
  READ facts: tolerance +/-0.2 mm or 0.3 %, hole tolerance +/-0.3 mm, wall > 0.8 mm, minimum build size 5 x 5 x 5 mm or 10 x 2 x 2 mm, build time 2 days
  (<https://jlc3dp.com/help/article/photosensitive-8001-resin>, <https://jlc3dp.com/help/article/3d-printing-design-guideline>, <https://jlc3dp.com/help/article/1219-What-is-the-build-time-of-the-3D-printing-parts>; read 2026-10-14 and 2026-10-16).
  "Transparent" 8001 is sanded and oil-sprayed by default (clearer, extra cost); a kit is ONE part with ONE material, so the workbook prices "Translucent", as printed. The flanges of the resin caps (0.6 mm) are below the 0.8 mm wall of the resin page,
  so the quote may show a thin-wall warning: accept it or ask JLC3DP.
* **Geometry.** Volumes and masses of the tray, lid, RF window insert, tube, caps, spacer ring and antenna spacer, the tray bounding box, the PCB outline, the skin grooves and the hold-down results come from `cad/housing_interface.json`
  (final v0.6 housing: tray 8401 mm3, lid 2643 mm3); the STL files in `cad/` give the bounding boxes and the volumes of the print kit and the laser sleeve, which the JSON does not list.
  The sheet states the files it used (see section 8).

### 3.7 Bought parts and consumables (ESTIMATE, six with a search-result anchor) - sheet `Bought parts`

AliExpress item pages cannot be read automatically, so the prices come from search-result snippets of 2026-10-14 or are typical prices. The listed item is only a price anchor: check size and specification in the listing yourself.
The rows that exist in v0.5 did not change and keep their date. The two silicone pad sheets and the silicone adhesive are new in v0.6 and were NOT looked up: they are typical prices. The epoxy is the v0.5 item; v0.6 also uses it for the tube.

| Item | Workbook price | Anchor (search snippet, 2026-10-14) |
|---|---|---|
| LiPo cell LP601646 with protection board (2 per light + 1 spare) | $4.50 each | $4.76 for a 400 mAh 071740 cell with PCM, <https://www.aliexpress.com/item/32662761434.html> (different size, 7 x 17 x 40 mm: price class only) |
| Luminus SST-20 on a 10 mm DTP board | $5.40 each | $5.42 for an SST-20 6500K on a 16/20 mm DTP board, <https://www.aliexpress.com/item/32884236179.html> (a 10 mm board may cost more) |
| Green laser module 520 nm, 6 x 12 mm, 1 mW APC | $23.50 each | $23.5 for a 6 mm 520 nm 1 mW APC module, <https://www.aliexpress.com/item/32869119160.html> |
| Round glass window 10 x 1 mm | $2.95 per 5 | $2.95 for 5 pcs flat glass lens, <https://www.aliexpress.com/item/4001014613249.html> (exact size not verified) |
| Screw M1.6 x 4 countersunk | $2.00 per 100 | $1.5 for 100 pcs M1.6 x 3 countersunk, <https://www.aliexpress.com/item/32917852857.html> |
| Thermal transfer tape 0.15 mm | $3.79 per roll | $3.79 for thermal tape, <https://www.aliexpress.com/item/33014898122.html> |
| M2 x 2 set screw (50), split ring 25 mm (20), PTFE wire 28 AWG 2 x 5 m, Kapton tape, foam tape | $2.00 / $2.00 / $6.00 / $2.50 / $2.50 | typical prices, no anchor found: the searches returned only retailer pages without AliExpress prices |
| Clear two-part epoxy, 5 minute, small syringe (v0.5 item; v0.6 also glues the light-pipe tube) | $3.50 per syringe | typical price, unchanged |
| **New:** silicone thermal gap pad 1.0 mm, Shore 00 70-80, sheet (cut to 8.8 x 12.4 mm) | $3.50 per sheet | typical price of a 100 x 100 x 1 mm listing; **no listing read** |
| **New:** silicone rubber sheet 1.0 mm, Shore A 70, sheet (cut to 3.7 x 3.2 mm) | $3.50 per sheet | typical price; **no listing read** |
| **New:** silicone adhesive, neutral-cure, small tube (sticks the pads on the lid bosses) | $2.50 per tube | typical price; **no listing read** |

What the new parts do: the buttons are on the bottom face and push the PCB up, so the lid holds the board down with two bosses. A piece of the 1.0 mm gap pad (8.8 x 12.4 mm) sits on the can boss over the ESP32 module
and a piece of the 1.0 mm rubber sheet (3.7 x 3.2 mm) on the front boss next to the next button; both are compressed to 0.8 mm when the lid is closed. Softness matters, the thermal rating does not.
Use neutral-cure silicone (no acetic-acid smell: acetic cure can attack the copper) and a drop per boss only. Epoxy or UV-curing clear adhesive glues the glass window, the RF window insert and the tube; **never cyanoacrylate on the clear resin parts** (its vapour leaves a white bloom).
Nothing had to be removed from the bought parts: the v0.5 side-button cap was a resin part of the print kit, not a bought part. Consumables are $27.79 (v0.5: $18.29, +$9.50).

The search terms and the exact specifications that matter (the 6.0 x 16 x 47 mm cell bay, the 10 mm LED board, the 6 mm laser) are in the sheet. Prices exclude VAT and shipping; the Hidden costs sheet adds both.
The sheet also explains why the laser must be **Class 2** (visible, 1 mW or less continuous, the blink reflex protects the eye; cheap "1 mW" modules often emit more, so ask for a measured value or measure it) and cites EN 50689:2021 for consumer laser products
(<https://ul.com/insights/understand-new-laser-product-safety-standards-europe>, general background <https://en.wikipedia.org/wiki/Laser_safety>).

### 3.8 Tools (ESTIMATE) - sheet `Tools`

18 tools with typical 2026 web-shop prices (soldering iron $35, multimeter $15, laser safety glasses 520 nm $14, caliper $12 ...), no source page; $135.00 for the tools marked "needed" (set "needed" to 0 for what you own),
$100.00 more for the optional ones (microscope, bench supply, laser power meter, taps). New in v0.6: hobby knife and cutting mat ($7.00, to cut the two silicone pads; v0.5 total $128.00). The flush cutters also cut the print kit off its sprues.
A laser power meter is the only way to verify a "1 mW" claim, so consider it if you plan to give lights away.

### 3.9 Spares and placement loss

JLC buys a few more pieces than the board needs (lost by the placement machine) and bills them inside the component price. The extra counts (10 for 0402 resistors and capacitors, 5 for 0603 / 0805, 2 for small semiconductors, 1 for big parts)
are ESTIMATES (JLC publishes no table; the cart shows the real quantity): $7.05 of the $17.32 component cost for 1 light. The bought parts include spares (a third cell, a second LED board, extra screws, spare glass windows) and left-over pack contents:
of the $84.54 for bought parts and consumables (1 light) about $45.47 is pieces you will not use (information row in `Bought parts`).
The spare resin parts are one spare print kit in the housing order ($0.60) and the spare stainless caps are one extra piece of each cap type in the cap order.

### 3.10 Pages that could not be read, and what is an ESTIMATE because of it

Four pages could not be read on 2026-10-18:

| Page | Date | What it would have given | Consequence in the workbook |
|---|---|---|---|
| <https://jlcpcb.com/partdetail/C115357> | 2026-10-18 | library type of the Alps SKRKAEE020 (SW1-SW3) | type "Extended" is assumed (every Alps tact switch checked on JLCPCB is Extended) |
| <https://www.lcsc.com/product-detail/C115357.html> | 2026-10-18 | price tiers and stock of SKRKAEE020 | tiers of the sibling Alps SKRPABE010 (C115360, read 2026-10-16): $0.0759 at 10, $0.0616 at 100; stock unknown |
| <https://jlcpcb.com/partdetail/C25104> | 2026-10-18 | library type of the 330 ohm resistor (R23, R32) | type "Basic" is assumed (same UNI-ROYAL 0402 series as the other Basic resistors) |
| <https://www.lcsc.com/product-detail/C25104.html> | 2026-10-18 | price tiers and stock of the 330 ohm resistor | tiers of the 5.1 k resistor C25905 (read 2026-10-14): $0.0024 at 100 ... $0.0012 at 50,000; stock unknown |

Both lines are blue on amber in `Main PCB BOM` (row 37 and row 30) and named in the Summary. The part-number text "0402WGF3300TCE" of C25104 is inferred from the UNI-ROYAL naming of the other resistors, not read.
The research for this version (2026-10-16) could not read ten pages (the LCSC pages of C2874113, C110293, C2838502, C25744, C11702, C25879, C25076, C720477, and two datasheet files): for the parts that stay on the board
the v0.5 readings of 2026-10-14 are kept with their date, so nothing in the workbook depends on those pages. The JLCCNC, JLC3DP and Alps SKRPABE010 pages that WERE readable on 2026-10-16 are cited in sections 3.2 and 3.6.

## 4. What is an estimate

READ (copied from a page on the date given): the JLCPCB Standard PCBA fee rows and X-ray tiers (2026-10-14); LCSC price tiers, stock and Basic / Extended type for 32 of the 34 BOM lines (2026-10-14);
VAT 21 %, the EUR 150 IOSS limit, the EUR 3 flat duty, the carrier-fee examples (2026-10-14); the ECB rate (13 Oct 2026); the JLCCNC and JLC3DP technical limits (2026-10-14 and 2026-10-16);
the price tiers of the Alps SKRPABE010 (C115360, 2026-10-16), which are used as the stand-in for the new switch.

ESTIMATE (blue on amber in the workbook):

* the two new BOM lines **C115357** (SW1-SW3) and **C25104** (R23, R32): tiers, stock and library type, because their pages could not be read on 2026-10-18 (section 3.10); together $0.56 for 1 light and $1.26 for 5 lights;
* the X-ray count of 3 parts per board (v0.5: 2) and whether the $0.46 per board panelisation fee applies (both are included to be on the safe side: together about $10.76 for 1 light);
* the bare PCB price ($25 for 5, range $12 to $40);
* all shipping prices, the number of AliExpress parcels (8, or 3 if you buy the small hardware in one EU shop) and $2 shipping per AliExpress parcel;
* the card / currency fee (1.5 %);
* the tariff rates and customs lines in formal clearance (0 / 6 / 6.5 %; JLCCNC has 2 lines with the stainless caps, 1 without); they only matter for parcels above EUR 150;
* the placement-loss extra pieces;
* the complete JLCCNC aluminium model (aluminium price, machine rate, minutes, set-ups, tapping, finish prices, anodizing lot fee) and what v0.6 adds to it: the V-groove rate (6 min per metre), the fine-feature minutes,
  the complexity factors 1.10 and 1.30, the set-ups 5 and 3, and laser marking ($2.00 per face + $5.00 per order);
* the **stainless caps** ($8.00 for the first piece of each cap type, $4.00 for each further piece): JLCCNC publishes no per-part price at all;
* the JLC3DP resin price and minimum (applied to the print kit);
* every price of the bought parts and consumables (six have a search-result anchor, see 3.7; the two silicone pad sheets and the silicone adhesive have none) and of all tools;
* the risk reserves (a second order of the same size, factor 1.0 in `Hidden costs!B15:B16`; not part of any total).

Nothing is left unpriced.

**How to replace an estimate with a real number.**

| Estimate | Where the real number comes from | Where to type it |
|---|---|---|
| bare PCB | price for 5 boards in the JLCPCB cart after the Gerber upload | `JLCPCB order!B44` |
| C115357 and C25104 | the two LCSC pages, and the JLC BOM upload (library type, stock) | tiers, type and stock in the rows 37 and 30 of `Main PCB BOM`; to keep it, change the entries `"C115357"` and `"C25104"` of `LCSC_DATA` in `tools/parts_list.py` (remove `est=True` and `type_est=True`) and rebuild |
| tray + lid (finish and laser marking included) | JLCCNC instant quote for `FlashKa_tray` and `FlashKa_lid` | `Housing!B87` (1 light) / `Housing!C87` (5 lights) |
| stainless caps | JLCCNC instant quote for `FlashKa_cap_main` and `FlashKa_cap_slide` (SUS304, bead blasting), or another CNC service | `Housing!C99` / `Housing!E99`; the resin caps instead: `Housing!B92` = 0 |
| laser marking | included in the JLCCNC quote, or not offered | `Housing!B30` = 0 takes the marking out of the estimate (a typed tray + lid quote replaces the estimate anyway) |
| print kit | JLC3DP instant quote for `FlashKa_print_kit.stl` | `Housing!E116` / `Housing!G116` |
| shipping | "Shipping Estimate" of each cart (economy / express) | `Hidden costs!B20:E22`, mode in `Hidden costs!B11` |
| surface finish | your choice at JLCCNC | `Housing!B41` |
| bought parts and tools | the listing you actually buy from | column F of `Bought parts` and `Tools` |
| exchange rate | your bank | `Summary!B6` |

## 5. Biggest uncertainties in the total

* **Housing** (1 light $122.56, 5 lights $382.39): a pure estimate until the JLCCNC quote; CNC prices of one-off parts can differ a lot from a model. Get the instant quotes first.
  Two parts of it have no public price at all: the stainless caps ($28.00 / $76.00) and the laser marking ($13.00 / $45.00). Without the stainless caps (resin caps from the print kit) the 1-light total is $37.79 lower
  (5 lights: $98.94); without laser marking it is $15.97 lower (5 lights: $58.58).
* **Shipping and the EUR 150 line:** express versus economy shipping moves the 1-light total by about $55.27; see "The EUR 150 cliff" above. The JLCPCB parcel for 1 light is only EUR 5.82 above the line.
* **Bare PCB:** at $12 the 1-light total would be $594.02 (-$26.19) (the JLCPCB parcel then also falls below the EUR 150 line), at $40 it would be $638.63 (+$18.42); the estimate gives $620.21.
* **AliExpress parcels:** buying the small hardware in one EU shop instead of several AliExpress sellers saves about $26.78 (`Hidden costs`, section 6).
* **X-ray fee:** if the cart does not ask for it, the 1-light total is about $22.31 lower (the fee itself is only $9.84, but without it the JLCPCB goods fall from EUR 155.82 to EUR 147.02, below the EUR 150 line, and the cheaper IOSS route applies).
* **The two unread LCSC lines:** their price is small (section 3.2), but stock and library type are unknown. If C115357 is not in stock at JLC, the build waits or needs another switch with the same footprint (`SW_Push_SPST_NO_Alps_SKRK`, 3.9 x 2.9 x 2.0 mm);
  if C25104 is not available, any 330 ohm 1 % 0402 resistor will do (update `flashka_parts.py`).
* **Hold-down of the PCB (a risk to the build, not to the price).** The two silicone pads (sheet 'Bought parts') are not in the kit. The housing calculation (cad/housing_interface.json, 'holddown') gives a board lift at 10 N of 0.030 mm (SW1), 0.051 mm (SW2), 0.121 mm (SW3) against a limit of 0.05 mm, with assumed pad moduli of 1.0 MPa (thermal pad) and 5.3 MPa (rubber sheet). SW2, SW3 are above the limit in that calculation: a firmer pad under the button that lifts too far helps. Real boards are stiffer than the plate model.

## 6. What to re-check before you order

1. **Stock and prices.** LCSC prices change weekly. Open the LCSC links in `Main PCB BOM` and look for red lines in the JLC BOM upload. Lines flagged on 2026-10-14:
   C15850 (20 pcs), C485117 (925 pcs) are low at LCSC retail; C15195, C1525, C11702 show 0 at LCSC retail but are JLC Basic parts with their own stock
   (C1525: 23,496,493 pcs on the JLC Basic parts list). **Stock NOT read:** C25104, C115357 (pages not readable on 2026-10-18). U4, the ESP32-C3-MINI-1-N4 (C2838502), is marked NRND (not recommended for new designs) by Espressif;
   the drop-in alternative is the ESP32-C3-MINI-1-H4X (C41349510). If a line is rejected, substitute it and update `flashka_parts.py`.
2. **The order files.** Upload only the files of the ready-to-upload folder `order_files/` of the package:
   `1_JLCPCB/` (`FlashKa_main_gerbers.zip`, `BOM_JLCPCB.csv`, `CPL_JLCPCB.csv`: the files `tools/kicad/build_all.py` writes to `production/`),
   `2_JLCCNC/` (`FlashKa_tray.step` + `FlashKa_tray.pdf`, `FlashKa_lid.step` + `FlashKa_lid.pdf`, `FlashKa_cap_main.step` + `FlashKa_cap_main.pdf`, `FlashKa_cap_slide.step` + `FlashKa_cap_slide.pdf`,
   `FlashKa_marking_lid_class2.dxf`, `FlashKa_marking_lid_class3R.dxf`, `FlashKa_marking_bottom.dxf`, `FlashKa_marking_minus_y.dxf`, `FlashKa_marking_plus_y.dxf`) and
   `3_JLC3DP/` (`FlashKa_print_kit.stl`, optional `FlashKa_laser_sleeve.stl`). The BOM sheet agrees line by line with what `build_all.py` writes: 34 lines, 68 parts
   (the workbook script only extracts its `bom()` function; `build_all.py` itself re-routes the board and takes long).
3. **JLCPCB cart.** Upload the Gerber, then replace the bare PCB price (`JLCPCB order!B44`), compare the fee lines with section 5 of that sheet (does the cart really list panelisation and X-ray, and for how many parts?),
   copy the "Shipping Estimate" into `Hidden costs`, check the part rotations in the placement preview (U4, U1, U2, U3, U5, Q1, Q2, Q4, Q5, J1, SW1-SW3, LED3, LED4) and choose DDP (taxes paid at checkout).
   **The rotation and pin 1 of the new SKRKAEE020 (SW1-SW3) and of the NH-B1010RGBT-HF (LED3, LED4) in the JLC library are not verified** (chapter 13, section 13.9; the NH-B1010 pad map is not verified either): look at the placement preview and the photo of the placement confirmation.
4. **The EUR 150 line** for the JLCPCB parcel (section 2): check the goods value shown in the cart.
5. **Housing quotes and fit.**
   * JLCCNC tray + lid: type the instant quote into the workbook; ask in the quote chat whether M1.6 threads are possible (not listed on the capability page; fallback: plain 1.25 / 1.6 mm holes and hand taps, see `Tools`);
     the thinnest metal wall is 0.8 mm (LED wire groove to the lid seat; next 0.875 mm at the front screw tap and 0.9 mm around the RF window pocket in the lid, `min_walls` of `cad/housing_interface.json`), exactly the 0.8 mm minimum;
     anodizing (type II 8-12 um on the drawings; JLCCNC states 8-25 um) grows in the bores, threads and the 0.25 mm V grooves of the skin (laser bore 6.1 mm, window bore 10.2 mm): the drawings say tolerances apply after finishing and threads are tapped before anodizing and gauged after it - ask JLCCNC to confirm,
     and test-fit the first set before you order five. The skin may need indexed (4th-axis) work: say so in the quote chat.
   * JLCCNC laser marking: confirm that it is offered for your order, with the five DXF files (layer MARK = laser, layer REF = outline, do not mark). If not, set `Housing!B30` to 0 and use a printed label with the same text.
   * JLCCNC stainless caps: upload `FlashKa_cap_main` and `FlashKa_cap_slide` (STEP + PDF) with material SUS304 and bead blasting. *Confirm with the instant quote; if refused, any CNC service (PCBWay, Xometry, a local shop) can make them from the same STEP + PDF, or use the resin caps from the print kit.*
   * **JLC3DP print kit.** Upload `order_files/3_JLC3DP/FlashKa_print_kit.stl` and order one kit per light + one spare kit. The RF window insert (8.4 x 15.5 x 1.7 mm) alone is below the 5 x 5 x 5 / 10 x 2 x 2 mm minimum build size of SLA 8001 resin
     (the workbook shows TOO SMALL for it, without red, as the reason for the kit); the kit (57.2 x 16.8 x 14.2 mm) is not. The flanges of the resin caps (0.6 mm) stay below the 0.8 mm minimum wall, so the quote may still warn about thin walls:
     accept it or ask JLC3DP. Cut the parts off the sprues with flush cutters and file the stubs flat. Glue the tube into the floor with clear two-part epoxy or UV-curing clear adhesive, never with cyanoacrylate (white bloom).
6. **Pads.** Buy the 1.0 mm silicone thermal gap pad (Shore 00 70-80) and the 1.0 mm silicone rubber sheet (Shore A 70), cut 8.8 x 12.4 mm and 3.7 x 3.2 mm and stick them on the lid bosses with a drop of neutral-cure silicone. After assembly press every button with the lid closed:
   each must click firmly. A spongy button means the board lifts: put a firmer pad under that button (section 5).
7. **Laser.** Buy a module with a stated, measured power (Class 2 = 1 mW or less) and check its size with a caliper (6.0 x 12 mm) before the housing is ordered. The marking text in the design is only true for a module that really is 1 mW or less.
8. **Cells and LED board.** The cells must fit the bay (6.0 x 16 x 47 mm including the protection board); the LED board must be 10 mm. Measure the delivered parts before the housing order.
9. **File names at JLCCNC.** The drawings in `order_files/2_JLCCNC/` are `cad/FlashKa_tray_drawing.pdf` (2 pages), `cad/FlashKa_lid_drawing.pdf`, `cad/FlashKa_cap_main_drawing.pdf` and `cad/FlashKa_cap_slide_drawing.pdf`, renamed to
   `FlashKa_tray.pdf`, `FlashKa_lid.pdf`, `FlashKa_cap_main.pdf` and `FlashKa_cap_slide.pdf`: JLCCNC pairs each drawing with its STEP file by the file name, so upload each under its own name together with its `.step` file.
10. **Dates.** The fee page revision was "Sep 09, 2026"; if JLC updates it, change the blue fee cells (each has its URL and date). Check the ECB rate and your bank's fee on the day you pay.

## 7. Regenerating and checking the workbook

```
python3 tools/parts_list.py                 # writes FlashKa_Parts_List_v0.6.xlsx, recalculates it, runs the checks
python3 tools/parts_list.py --check-only    # re-checks the existing workbook without rewriting it
python3 tools/parts_list.py other.xlsx      # writes somewhere else
python3 tools/parts_list.py --no-recalc     # skips recalculation and checks (no cached values: only for inspection)
```

It needs `openpyxl` and LibreOffice (`soffice`) for the recalculation; set `FLASHKA_RECALC` to the path of a `recalc.py` if it is not found automatically.
The script prints "all checks passed" when:

* the workbook has no `#REF!`, `#VALUE!`, `#NAME?`, `#DIV/0!` or `#N/A` cell and no formula without a calculated value;
* every total, price and fee cell (523 cells in this version) equals an independent calculation in Python;
* every LCSC number of `COMPONENTS` is in the BOM sheet with the right quantity and designators (34 lines, 68 placements), and the BOM sheet equals the output of the `bom()` function of `tools/kicad/build_all.py`
  (only `refkey()` and `bom()` are extracted from that file and run into a temporary folder; `build_all.py` itself is never run), `production/BOM_JLCPCB.csv` and `order_files/1_JLCPCB/BOM_JLCPCB.csv`, line by line;
  the 68 designators are exactly the rows of `production/CPL_JLCPCB.csv`; the solder joints per footprint equal the pads of the routed board (232 per board);
* the print kit's STL volume matches its seven parts (plus sprues), the kit is above the minimum build size, its parts and their order are those of the `build_print_kit` call in `tools/housing/flashka_housing.py`,
  one kit per light + one spare is ordered and none of its parts is ordered a second time on its own;
* the stainless cap quantities are lights x per light + 1 spare, and the JSON volumes agree with the STL volumes (1 %); the pad sizes (8.8 x 12.4 mm and 3.7 x 3.2 mm) and the lid height (5.2 mm) written in the texts are those of the geometry;
* every file of `ORDER_FILES` (18 files) is in `order_files/`, nothing else is in its three folders, every `order_files/` path written in the workbook names one of them, and no text points to a file location of an older version;
* this file names the 15 input cells (`JLCPCB order!B44`, `Housing!B87`, `Housing!C87`, `Housing!C99`, `Housing!E99`, `Housing!E116`, `Housing!G116`, `Housing!B92`, `Housing!B30`, `Housing!B41`, `Hidden costs!B20:E22` ...) at their right addresses, and the quote cells are empty.

To change prices, edit the blue cells in the workbook, or the tables near the top of `tools/parts_list.py`, and regenerate.

## 8. Geometry source

The housing data is read from `cad/housing_interface.json` (version 0.6), written by the final v0.6 housing build (volumes and masses of the tray, lid, RF window insert, light-pipe tube, caps, spacer ring and antenna spacer, the tray bounding box,
the PCB outline, the parameters, the skin layout of the V grooves, the hold-down results and the wall checks), and from the STL files in `cad/`: the bounding boxes of all parts and the volumes of `FlashKa_print_kit.stl` and `FlashKa_laser_sleeve.stl`, which the JSON does not list.
The sheet `Housing` prints the source (`cad/housing_interface.json (version 0.6) + cad/*.stl`). If the JSON is not found, is incomplete or is not version 0.6, the script falls back to an embedded snapshot of the same numbers and says so;
a missing STL file is replaced by its snapshot entry and named in the same source line. After every housing rebuild run `python3 tools/parts_list.py` again: the volumes, the skin lengths and the hold-down numbers in the workbook follow the files.
