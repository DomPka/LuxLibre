<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
# FlashKa Keychain v0.7 - parts list and cost workbook: reading notes

| | |
|---|---|
| Workbook | `FlashKa_Parts_List_v0.7.xlsx` (folder of the v0.7 package) |
| Generator | `tools/parts_list.py` (run `python3 tools/parts_list.py`, see section 7) |
| Price-check date | **2026-10-23** (the one-cell layout: the Vapcell INR14500 F15 cell and the nickel strip at nkon.nl, R3 (C4109) at LCSC, the Vapcell K10 at illumn.com). Earlier readings keep their dates: **2026-10-22** (the 1000 lm power stage: the buck TPS62095 and the protection IC DW01A at LCSC, the LED board, the TIR optic, the ECON 80 urethane, Sugru, JLC3DP's resin rate, JLCCNC's merged ordering, the EU customs rules), **2026-10-21** (first v0.7 check: the pogo pin C22100007, the JLCPCB panel fee for two designs, JLCCNC's minimum size for plastic parts), **2026-10-14** (v0.5 check) and **2026-10-18** (v0.6 check); the JLCCNC pages of the v0.6 research were read on 2026-10-16. |
| Pages not read | The JLCPCB and LCSC pages of C115357 (SW1-SW3) and C25104 (R23, R32) could not be read on 2026-10-18 and the LCSC page of C238645 (the MOSFET Q3) on 2026-10-22: those three lines are **ESTIMATES**. JLCPCB's own stock and library type of the pogo pin C22100007 were not read. The JLCCNC finishes and capabilities pages could not be read on 2026-10-21 (the v0.6 readings are kept). On 2026-10-23 nkon.nl's shipping page could not be opened (the battery shop's courier fee is an ESTIMATE) and the LCSC product page of C4109 neither (its tiers and stock were read on LCSC's product-image page). Section 3.10 lists them. |
| Exchange rate | 1.1188 USD per EUR (ECB euro reference rate of 13 Oct 2026, not refreshed; input cell `Summary!B6`); the RS optic price in GBP is converted with the ECB rate of the same day (0.8446 GBP per EUR) |
| Delivery to | Lithuania (EU): VAT 21 %, EU customs rules of 2026 |

This file explains (1) how to read the workbook, (2) the result, what changed since the first v0.7 layout, what the battery and body change costs, the options and what changed from v0.6, (3) where every number comes from,
with URL and date, (4) which numbers are only estimates and how to replace each with a real quote, (5) what is most uncertain and (6) what you must re-check before you order.
It does not repeat every cell of the workbook: each price row in the workbook carries its own source URL and date.

## 1. How to read the workbook

**The idea.** The light is made from a handful of groups of things, bought from different places. The workbook prices every group, then adds the costs people forget
(shipping of every separate parcel, 21 % VAT, the new EU customs duty, bank fees) so that the Summary shows what really leaves your bank account.

| Group | Where you buy it | Sheet |
|---|---|---|
| Both circuit boards (main PCB + key board) in one panel, soldered by the factory | jlcpcb.com (PCB + assembly) | `JLCPCB order`, `Panel BOM` |
| Aluminium tray + lid, the PMMA kit (clear main keys), the POM-C kit (RF insert, antenna spacer) and, once per builder, the two resin plates of the casting mould | jlccnc.com with jlc3dp.com in one merged order (one parcel) | `Housing` |
| The 14500 cell (Vapcell INR14500 F15) and the nickel strip for its tabs | an EU battery shop (for example nkon.nl) | `Bought parts` |
| LED board, laser module, screws, set screw, ring, wire, thermal paste, tapes, foam, silicone pads, adhesives, stainless shim, the mould's M3 bolts | AliExpress, Kaidomain or an EU web shop | `Bought parts` |
| The TIR optic (pack of 5) | an electronics distributor (RS, stock no. 186-2699) | `Bought parts` |
| Urethane rubber, black pigment and mould release for the two side keys (cast at home) | an EU shop (for example kaupo.de) | `Bought parts` |
| Shipping, VAT, customs, bank fees, spares, risk | - | `Hidden costs` |
| Tools you need once (soldering iron, multimeter, laser glasses ...) | any shop | `Tools` |

`Summary` is the first sheet and `Ordering checklist` is the last: it lists, in order, what to order where, which file to upload and what to check before paying.
Every file to upload is named with its place in the ready-to-upload folder of the package: `order_files/1_JLCPCB/`, `order_files/2_JLCCNC/` and `order_files/3_rubber_keys/` (section 6, item 2).
Nothing is laser-marked; the only printed part is the casting mould, a tool and not a part of the light.

**Colour code** (also written at the top of the sheets):

| Look | Meaning |
|---|---|
| blue number | typed-in number you may change (price, fee, quantity) |
| blue number on amber background | **ESTIMATE**: no public price exists or it could not be read; replace it with a real quote when you have one |
| black number | formula (or, in the options table, a number the script computed): do not type over it |
| green number | copied from another sheet |
| dark blue row / light blue row / light green row | table header / section title / total |

**Two scenarios.** Scenario A = you build **1** light, scenario B = you build **5** lights (`Summary!B7` and `Summary!B8`: type any other numbers, for example 2).
The JLC minimums are built in: JLCPCB sells at least 5 bare panels per design (in steps of 5) and assembles from 2, so one light still pays for 2 assembled panels.
The Summary shows totals in USD and EUR, per light, and the extra cost of each additional light (the set-up and stencil fees, the panel fee, the anodizing lot fee, the casting mould and the casting supplies are paid once).
It also has a group "What changed since the first v0.7 layout", a group "What the battery and body change costs" (against the two-pouch-cell layout that came just before), an options table and a group "What changed from v0.6" (section 2).

**Putting in real numbers.** Every total is a formula, so you only change inputs:

| What | Cell |
|---|---|
| bare panel price shown by JLCPCB after the Gerber upload (price for 5 panels) | `JLCPCB order!B44` |
| JLCPCB surcharge for two designs in one file ("different design") | `JLCPCB order!B47` |
| JLCCNC instant quote for tray + lid (with finish, no shipping), scenario A / B | `Housing!B95` / `Housing!C95` |
| JLCCNC instant quote for the PMMA and POM-C kits (no shipping), scenario A / B | `Housing!E121` / `Housing!G121` |
| quote for the casting mould you order (JLC3DP resin plates, or the JLCCNC aluminium option), scenario A / B (0 if you already have a mould) | `Housing!B109` / `Housing!C109` |
| surface finish of the aluminium (drop-down) | `Housing!B42` |
| panel texture: 1 = cut it, 0 = leave it out | `Housing!B33` |
| "Shipping Estimate" of each cart (economy / express, A and B) | `Hidden costs!B20:E24` |
| shipping mode 1 = economy, 2 = express | `Hidden costs!B11` |
| price of any bought part | column F of `Bought parts` |
| exchange rate | `Summary!B6` |
| lights built, scenario A / B | `Summary!B7` / `Summary!B8` |

Leave a quote cell empty to use the workbook's own estimate; type a number to override it. The Summary column "Where to replace it with a real number" names the cell for each row.

## 2. Result (price check 2026-10-23)

| USD (EUR) | 1 light | 2 lights (B = 2) | 5 lights |
|---|---|---|---|
| 1. PCB + assembly (JLCPCB, one panel), before shipping | $236.90 (EUR 211.74) | $236.90 (EUR 211.74) | $282.07 (EUR 252.11) |
| 2. Housing (JLCCNC + JLC3DP: tray + lid, PMMA and POM-C kits, resin mould) | $132.91 (EUR 118.79) | $204.99 (EUR 183.23) | $432.50 (EUR 386.58) |
| 3. Bought parts (the cell, LED board, TIR optic, laser, screws, ring, mould hardware) | $65.79 (EUR 58.80) | $95.75 (EUR 85.58) | $203.00 (EUR 181.44) |
| 4. Consumables (nickel strip, wire, paste, tapes, foam, silicone pads, adhesives, casting supplies) | $115.53 (EUR 103.26) | $115.53 (EUR 103.26) | $115.53 (EUR 103.26) |
| 5. Shipping, VAT, customs duty, carrier and card fees | $308.16 (EUR 275.44) | $361.75 (EUR 323.34) | $463.25 (EUR 414.06) |
| **Total for the lights** | **$859.28 (EUR 768.04)** | **$1,014.92 (EUR 907.15)** | **$1,496.35 (EUR 1,337.46)** |
| **Per light** | **$859.28 (EUR 768.04)** | **$507.46 (EUR 453.58)** | **$299.27 (EUR 267.49)** |
| Tools, one-time (only the tools marked needed) | $204.00 (EUR 182.34) | same | same |
| Risk reserve, not in any total: a second PCB + assembly order | $329.44 (EUR 294.46) | | |
| Risk reserve, not in any total: a second housing order | $194.15 (EUR 173.53) | | |

The Summary sheet shows the 1-light and the 5-light columns. The 2-light column is the same workbook with `Summary!B8` set to 2 (`python3 tools/parts_list.py --lights-b 2` builds and checks it in a temporary folder).

The housing in detail (1 light / 2 lights / 5 lights): tray + lid $98.34 / $160.67 / $347.69, of which the panel texture $10.25 / $20.50 / $51.26; PMMA + POM-C kits $31.25 / $41.00 / $81.50 (PMMA kits 1 / 1 / 2, POM-C kits 1 / 2 / 5); resin casting mould $3.32 in every column (once per builder). Of the consumables, the casting supplies for the side keys are $85.95 in every column (one unit of rubber casts many keys).

Item 5 in detail (1 light / 2 lights / 5 lights): shipping $110.93 / $113.93 / $113.93, VAT $139.03 / $163.99 / $246.64, customs duty and carrier fees $50.35 / $74.21 / $87.87, card fee $7.85 / $9.62 / $14.82.

### 2.1 What changed since the first v0.7 layout

Since its first layout v0.7 got the parts that 1000 lm and about 100 m of throw need (a TIR optic, a 4 A buck with board protection, 24 AWG wire), one 14500 cell in an octagonal body instead of the two small cells with protection boards, and cost was taken out wherever it does not hurt the design. The table compares today's workbook with the cost workbook of the first v0.7 layout (price check 2026-10-21; same scenarios, same exchange rate). A minus sign is a saving.

| USD | 1 light: first layout -> now | 2 lights | 5 lights |
|---|---|---|---|
| 1. PCB + assembly | $228.66 -> $236.90 (+$8.24) | $228.66 -> $236.90 (+$8.24) | $269.12 -> $282.07 (+$12.95) |
| 2. Housing | $169.16 -> $132.91 (-$36.25) | $242.46 -> $204.99 (-$37.47) | $473.59 -> $432.50 (-$41.09) |
| 3. Bought parts | $63.75 -> $65.79 (+$2.04) | $101.65 -> $95.75 (-$5.90) | $218.30 -> $203.00 (-$15.30) |
| 4. Consumables | $142.19 -> $115.53 (-$26.66) | $142.19 -> $115.53 (-$26.66) | $142.19 -> $115.53 (-$26.66) |
| 5. Shipping, VAT, customs, fees | $315.13 -> $308.16 (-$6.97) | $349.12 -> $361.75 (+$12.63) | $452.61 -> $463.25 (+$10.64) |
| **Total for the lights** | **$918.89 -> $859.28 (-$59.61)** | **$1,064.08 -> $1,014.92 (-$49.16)** | **$1,555.81 -> $1,496.35 (-$59.46)** |
| **Per light** | **$918.89 -> $859.28 (-$59.61)** | **$532.04 -> $507.46 (-$24.58)** | **$311.16 -> $299.27 (-$11.89)** |

In EUR the 1-light total goes from EUR 821.32 to EUR 768.04, the 2-light total from EUR 951.09 to EUR 907.15 and the 5-light total from EUR 1,390.61 to EUR 1,337.46. The tools that are needed once cost $204.00 instead of $174.00 (the 0.01 g scale is only needed for PMC-780 DRY now; the small spot welder for the cell's nickel strips is new).

**The savings, one by one (1 light), and what each costs in quality:**

* **Resin casting mould instead of the aluminium mould: $3.32 instead of $35.12** (once per builder). JLC3DP prints the two plates in SLA resin and ships them in the same parcel as the JLCCNC parts (JLCCNC's merged ordering: one package, one shipping rate), so no extra parcel. Quality: a print does not hold the aluminium mould's +/-0.02 mm and wears out sooner; try the first cast key in its opening and sand the cavity floors with 400-grit paper for the matte face. The aluminium mould stays an option ($40.27 more, landed).
* **ECON 80 urethane instead of PMC-780 DRY: $31.95 instead of $60.40** for the rubber, $85.95 instead of $114.40 for all casting supplies. The same Shore 80A (the drawing asks for 75-85), mixed 1:1 by volume with two syringes, so the 0.01 g scale is no longer needed. Quality: none; its pot life is 13 minutes instead of 25 (pour without delay), and it cures overnight instead of in 48 hours.
* **The housing parcel of one light now stays below EUR 150.** The merged JLCCNC + JLC3DP order is EUR 118.79 (the first layout: EUR 151.20, with the aluminium mould). Below the line it pays VAT and EUR 3 per customs line; above it, it would pay 6 % duty, VAT on the duty and a carrier fee of about EUR 15: $194.15 instead of $215.46 landed ($21.31 less).
* **No glass window and no POM-C spacer ring:** the optic's front face is the window. The window cost $2.95 per 5; the POM-C kit has one part type less: kits $31.25 instead of $37.75 for one light ($81.50 instead of $101.00 for five).
* **Cheaper LED board:** SST-20 Gen 2 on a 10 mm copper board from Kaidomain, $2.99 instead of $5.40 (read 2026-10-22; the flux bin is not stated: ask for G1). Quality: better - the Gen 2 LED gives more light per amp.
* **Smaller items:** thermal paste ($2.50) instead of thermal tape ($3.79); 8 AliExpress parcels instead of 10 (no window; the cell comes from an EU battery shop), each saving its shipping and its EUR 3 duty; the resin mould's M3 bolts, washers and nuts ($4.00) instead of the aluminium mould's dowel pins and M3 x 12 screws ($5.00).

**What the 1000 lm parts and the one-cell layout add:**

* **The TIR optic:** LEDiL LISA3-RS-PIN, a pack of 5 for $17.37 (RS, GBP 13.11 excl. VAT, read 2026-10-22), plus the distributor's parcel: ESTIMATE $20.00 courier fee and VAT on both. Order the optics for several lights at once, or with other parts, to pass the distributor's free-shipping limit.
* **The power stage on the main PCB:** the 4 A buck TPS62095 ($1.35 per board; the TLV62585 it replaces cost $0.26), the protection IC DW01A ($0.025) and the dual MOSFET SE8830A ($0.10, ESTIMATE), five small parts and 29 more solder joints per panel. U2 is a QFN, so the X-ray count rises from 3 to 4 parts per panel ($13.12 instead of $9.84 for one light). Components $46.75 instead of $41.89, fees $145.15 instead of $141.77 (1 light).
* **One 14500 cell:** a Vapcell INR14500 F15 (1500 mAh typical, 1150 mAh minimum, 3 A, flat top, no protection board) at $3.47 (nkon.nl, EUR 3.10 excl. VAT, read 2026-10-23) instead of two 400 mAh cells with protection boards at $4.50 each: nearly twice the capacity (1500 instead of 800 mAh), protected by the DW01A on the main board. It needs a nickel strip for its tabs ($2.08 per metre, read) and comes in the battery shop's own parcel (ESTIMATE $13.43 courier fee, VAT only).
* **24 AWG wire** for the 3 A paths ($7.00 per 5 m pair, instead of the 28 AWG wire at $6.00) and 0.5 mm foam sheet to hold the cell.
* **A 4.8 mm longer body, now an octagon 20 x 18 mm** (99.2 mm long, for the optic and the 14500 cell): tray + lid $98.34 instead of $96.29 for one light.

### 2.2 What the battery and body change costs

Just before the one-cell layout the workbook priced two 320 mAh pouch cells (ESTIMATE $5.00 each, from a web shop) in the 20 x 16 mm body with a 1.5 mm plate lid (price check 2026-10-22). The table compares that workbook with today's: one Vapcell INR14500 F15 in the 20 x 18 mm octagon; everything else is the same. A minus sign is a saving.

| USD | 1 light: two pouch cells -> one 14500 cell | 2 lights | 5 lights |
|---|---|---|---|
| 1. PCB + assembly | $236.91 -> $236.90 (-$0.01) | $236.91 -> $236.90 (-$0.01) | $282.08 -> $282.07 (-$0.01) |
| 2. Housing | $131.89 -> $132.91 (+$1.02) | $202.96 -> $204.99 (+$2.03) | $427.41 -> $432.50 (+$5.09) |
| 3. Bought parts | $73.85 -> $65.79 (-$8.06) | $110.34 -> $95.75 (-$14.59) | $237.18 -> $203.00 (-$34.18) |
| 4. Consumables | $113.45 -> $115.53 (+$2.08) | $113.45 -> $115.53 (+$2.08) | $113.45 -> $115.53 (+$2.08) |
| 5. Shipping, VAT, customs, fees | $298.71 -> $308.16 (+$9.45) | $353.29 -> $361.75 (+$8.46) | $457.99 -> $463.25 (+$5.26) |
| **Total for the lights** | **$854.81 -> $859.28 (+$4.47)** | **$1,016.95 -> $1,014.92 (-$2.03)** | **$1,518.11 -> $1,496.35 (-$21.76)** |
| **Per light** | **$854.81 -> $859.28 (+$4.47)** | **$508.47 -> $507.46 (-$1.01)** | **$303.62 -> $299.27 (-$4.35)** |

With the one 14500 cell, one light costs $4.47 more, two lights $2.03 less and five lights $21.76 less ($4.35 less per light) than with the two pouch cells. Where it comes from (1 light):

* **The cell is cheaper and holds more:** $6.94 for the F15 and its spare instead of $15.00 for two pouch cells and a spare; 1500 mAh instead of 2 x 320 mAh. Its price is READ (nkon.nl), the pouch cells' was an ESTIMATE (the maker quoted only on request).
* **The body is bigger:** tray + lid $98.34 instead of $97.32 (the section is 2 mm taller, the lid a 3.4 mm cap, 7.25 mm tall with its bosses, instead of a 1.5 mm plate; the diagonal facets and the cap pocket add a few minutes; the smaller panels need less texture). The kits and the resin mould cost the same.
* **New: the nickel strip** for the two tabs ($2.08 for 1 m, READ) and the battery shop's own parcel (ESTIMATE $13.43 courier fee, VAT only: lithium cells ship as dangerous goods); one web-shop parcel less (8 instead of 9). Shipping $110.93 instead of $99.50, VAT $139.03 instead of $137.68, customs duty and carrier fees $50.35 instead of $53.70.
* **The electronics:** R3 is 2.0 k instead of 3.3 k (C4109, the same price class): the charger gives about 494 mA instead of 280 mA; the BOM keeps 35 lines and 79 parts, so the JLCPCB fees do not change.
* **Not in the totals:** a small spot welder for the strips ($40.00, ESTIMATE, sheet `Tools`), unless the cell is bought with welded tabs or a shop welds them; with it the tools that are needed once cost $204.00 instead of $164.00.

### 2.3 Options: what else would save money, and what it costs

The workbook keeps the cheapest choices that leave the design as drawn. Each option below changes one thing; the saving includes VAT, duty and shipping (the same table is in the Summary sheet).

| Option | Saves (1 light) | Saves (2 lights) | Saves (5 lights) | What it costs in quality / what to do |
|---|---|---|---|---|
| Leave out the panel texture (type 0 in 'texture_on', sheet 'Housing') | $12.59 | $26.69 | $66.73 | Plain recessed panels instead of the V texture: the light looks different from the pictures, nothing else changes. The STEP files carry the texture: ask the shop to skip feature 17 of drawing FK-H-01 (or have texture-free STEP files made) - otherwise the quote still includes it. |
| Economy shipping instead of express (type 1 in 'ship_mode', sheet 'Hidden costs') | $47.73 | $50.14 | $50.14 | Two to five weeks instead of about one; tracking and the customs handling are less predictable, and the EUR 3 per line may be asked at your door. |
| Cheaper pogo pins: Xinyangze YZ00615050R-08 (LCSC C7429459) instead of the Harwin P70-1010045R | $25.08 | $25.08 | $42.68 | LCSC does not state the plating or whether it has a locating peg (the key board has no hole for one); rated 1 A (plenty for these signals); 720 in stock. Not verified, so not the default: to use it, change the LCSC number in tools/kicad/flashka_parts.py and the panel BOM, and check the footprint first. |
| Sugru instead of ECON 80 for the side keys (no pigment, no urethane release: petroleum jelly) | $61.72 | $61.72 | $61.72 | Shore 70A, softer than the 75-85 of the drawing: the keys feel softer. 48 h cure in the closed mould; the stiffener is bedded in fresh Sugru because cyanoacrylate does not hold on cured Sugru. |
| Aluminium casting mould (JLCCNC) instead of the resin mould (a negative saving: it costs more) | -$40.27 | -$42.61 | -$42.61 | Better, not worse: +/-0.02 mm instead of the print's tolerance, lasts for many pours, bead-blasted matte key faces without sanding. Needs 2 dowel pins and 4 M3 x 12 screws instead of the M3 x 16 bolts, washers and nuts. |
| Vapcell INR14500 K10 instead of the F15 | - | - | - | not priced in the totals: $4.30 at illumn.com (USA, read 2026-10-23), and no EU shop had it in stock (nkon.nl's similar H10, EUR 3.26 excl. VAT, was out of stock). It sags less (8 A) and keeps full turbo to a lower charge (not simulated), but 1000 mAh instead of 1500: about a third less runtime. It fits the bay (14.1 x 50.1 mm, flat top). |

Taken together, the four options that trade quality for cost (no texture, economy shipping, the cheaper pogo pin, Sugru) would bring one light to about $712.15 (EUR 636.53), five lights to $1,275.07 ($255.01 per light). The texture stays in the default because the order files carry it and it is part of the exterior style; the Harwin pogo pin stays because the cheaper pin's plating and peg are not confirmed; ECON 80 stays because Sugru is softer than the drawing allows; express shipping stays because it is fast and the taxes are paid at the checkout.

### 2.4 The EUR 150 lines

Up to EUR 150 goods value per parcel the EU collects VAT at the checkout (IOSS) and a flat EUR 3 duty per customs line; JLC collects the VAT but not the EUR 3, which is paid at import unless the shipping channel is DDP. Above EUR 150 the parcel needs formal customs clearance: the tariff duty, VAT on it and a carrier fee of about EUR 15 (UPS Lithuania: 2 %, minimum EUR 12).

* **JLCPCB:** the panel and its assembly come to **EUR 211.74** for one light ($236.90), EUR 61.74 above the line: it cannot be kept below it. On the IOSS route it would land $10.07 lower (`Hidden costs`, section 6).
* **JLCCNC + JLC3DP, 1 light:** EUR 118.79, EUR 31.21 below the line - the default route is IOSS (see 2.1). A real quote more than $34.91 above the estimate would push it over.
* **JLCCNC + JLC3DP, 2 lights:** EUR 183.23, above the line. Split into two orders below the line (the aluminium parts, EUR 143.61; the plastic kits and the resin mould, EUR 39.61), it lands at $312.61 instead of $316.45 with express shipping (only $3.84 less: the second shipping fee eats the saving), but at $275.77 instead of $295.62 with economy shipping ($19.85 less). So: with express shipping keep one merged order; with economy shipping split it.
* **JLCCNC + JLC3DP, 5 lights:** EUR 386.58; the aluminium parts alone are EUR 310.77, so staying below the line would take four or more parcels: not worth it.
* **Not used:** JLCPCB and JLCCNC share one cart and one payment, but one parcel for both is not stated anywhere; if the cart offers it, one shipping fee less.

### 2.5 Change from v0.6

Same scenarios, same exchange rate; v0.6 values from its workbook of 2026-10-18:

| USD | v0.6, 1 light | v0.7, 1 light | change | v0.6, 5 lights | v0.7, 5 lights | change |
|---|---|---|---|---|---|---|
| 1. PCB + assembly | $174.33 | $236.90 | +$62.57 | $194.69 | $282.07 | +$87.38 |
| 2. Housing | $122.56 | $132.91 | +$10.35 | $382.39 | $432.50 | +$50.12 |
| 3. Bought parts | $56.75 | $65.79 | +$9.04 | $211.30 | $203.00 | -$8.30 |
| 4. Consumables | $27.79 | $115.53 | +$87.74 | $27.79 | $115.53 | +$87.74 |
| 5. Shipping, VAT, customs, fees | $238.78 | $308.16 | +$69.38 | $378.82 | $463.25 | +$84.43 |
| **Total for the lights** | **$620.21** | **$859.28** | **+$239.07** | **$1,194.99** | **$1,496.35** | **+$301.36** |
| Per light | $620.21 | $859.28 | +$239.07 | $239.00 | $299.27 | +$60.27 |

In EUR the 1-light total goes from EUR 554.35 to EUR 768.04, the 5-light total from EUR 1,068.10 to EUR 1,337.46.

* **Board (PCB + assembly), +$62.57 for one light.** One panel with the main PCB and the new key board: 35 BOM lines, 79 placements (60 on the main PCB, 19 on the key board), 267 solder joints per panel (v0.6: 34, 68, 232 on one board). New parts: the six pogo pins P1-P6 (C22100007: $24.57 for one light, 13 pins at $1.89; $44.64 for five, 31 pins at $1.44) and the 1000 lm power stage (section 2.1). SW1-SW3, LED3, LED4 and eight resistors moved to the key board: the same parts at the same price. The fees grow by +$13.13: the panel fee for two designs ($8.21, read 2026-10-21), one more unique part ($1.53), the fourth X-ray part and the extra solder joints. The bare panel is bigger than the v0.6 board (ESTIMATE $30.00 for 5 instead of $25.00) and JLCPCB adds a surcharge for two designs in one file (ESTIMATE $15.00).
* **Housing, +$10.35 for one light.** The v0.6 stainless caps ($28.00), resin print kit ($1.20) and laser marking are gone. Tray + lid $93.36 -> $98.34: no laser marking (-$13.00), more machining for the recessed panels, the V texture, the transverse grooves, the facets and the longer, taller octagonal body (+$17.48; section 3.6) and two more threads (+$0.50). New: the PMMA kit and the POM-C kit ($31.25 together, ESTIMATE) and the resin casting mould ($3.32, ESTIMATE, once per builder).
* **Bought parts, +$9.04.** The TIR optic instead of the glass window, one 14500 cell (protected on the main board) instead of two pouch cells with protection boards, two M1.6 x 2.5 pan-head screws for the key board ($2.00 per 100) and the resin mould's M3 hardware; the LED board costs less.
* **Consumables, +$87.74.** The casting supplies of the rubber side keys ($85.95: urethane $31.95 read, pigment $12.00, mould release $18.00, shim $4.00, cyanoacrylate $5.00, cups and syringes $5.00, polishes $10.00; all but the urethane are ESTIMATES), the nickel strip for the cell, 24 AWG wire and thermal paste. The can hold-down pad is 1.5 mm thick (same price as the v0.6 1.0 mm sheet).
* **Shipping, VAT, customs, fees, +$69.38 for one light.** VAT on the dearer orders ($97.11 -> $139.03) and shipping ($81.00 -> $110.93); the customs duty and carrier fees go from $53.70 to $50.35: the 3D-print parcel of v0.6 is gone (the resin mould travels with JLCCNC), the parcels of the EU casting shop, the optic distributor and the battery shop are new, and the default assumes 8 AliExpress parcels as v0.6 did.

**Biggest cost items (1 light).**

1. Shipping, VAT, duty and fees: 36 % of the total ($308.16). JLCPCB ships a parcel, JLCCNC and JLC3DP one merged parcel, the EU casting shop, the optic distributor and the battery shop one each, and (by default) 8 AliExpress parcels each pay their own shipping and their own flat EUR 3 customs duty.
2. The JLCPCB order: $236.90 before shipping, of which assembly fees $145.15 (set-up $51.12, feeder loading $53.55, stencil $16.42, X-ray $13.12, panel fee $8.21, everything else together $2.73). The fees are mostly paid once, which is why 5 lights cost only $5.94 more in fees.
3. The JLCCNC + JLC3DP order: $132.91 for 1 light, $432.50 for 5 lights (estimate; the set-ups, the anodizing lot fee and the mould are paid once per order).
4. The casting supplies ($85.95, once per builder; the urethane alone $31.95), then the laser module ($23.50 each), the optic pack ($17.37) and the cell ($3.47 each).

Every additional light after the first costs about $159.27 more (the Summary shows it). A builder who already has the mould, its hardware and the casting supplies (a second batch, or a mould and a unit of rubber shared with another builder) pays $746.37 for one light instead of $859.28.

## 3. Where every number comes from

"READ" = copied from the vendor page on the date given. "ESTIMATE" = no public price or not readable; the cell is blue on amber and explained in its note column.
"COMPUTED" = formula from READ inputs. Sections 3.1 to 3.10 follow the order of the sheets.

### 3.1 JLCPCB assembly fees (READ 2026-10-14, main rates and the panel fee checked 2026-10-21) - sheet `JLCPCB order`, section 5

Fee page: <https://jlcpcb.com/help/article/pcb-assembly-price>, shows "Last updated on Sep 09, 2026", read 2026-10-14; the set-up, stencil and feeder rates were checked again and the panel fee for more than one design was read on 2026-10-21. Both boards have parts on both sides, so the panel needs **Standard PCBA**, double-sided (Economic PCBA is single-sided only and charges $3.07 per Extended part; Standard charges the feeder fee per unique part instead, Basic or Extended alike, and has no separate engineering fee). The "board" JLCPCB counts is the panel: key board + main PCB.

| Fee | Rate | Used for this order |
|---|---|---|
| Set-up fee (Standard PCBA) | $25.56 per side | 2 sides = $51.12 |
| Stencil (Standard PCBA) | $8.21 per side | 2 sides = $16.42 |
| SMT assembly | $0.0016 per solder joint | 267 joints per panel x panels assembled |
| Feeder loading | $1.53 per unique part (Basic and Extended) | 35 unique parts = $53.55 |
| **Panel fee (more than one design in the file)** | $8.21 per order | the panel holds two designs: $8.21 |
| Confirm parts placement (optional, recommended) | $0.45 per order | included |
| X-ray inspection ("required for components such as BGA, QFN, and other leadless packages") | per part, tiered by the order total: 1-10 $1.64, 11-50 $0.82, 51-200 $0.49, 201-500 $0.33, 501-1000 $0.25, 1001-3000 $0.16, 3001+ $0.082 | 4 parts per panel (ESP32 module U4 and the buck U2, a QFN, on the main PCB; ring LEDs LED3 and LED4 on the key board): ESTIMATE of the count |
| Panelisation of small boards (<https://jlcpcb.com/help/article/Panelizing-your-PCB-for-Assembly>) | minimum $0.46 per board | included per panel (assumed to apply, see section 4) |
| Packing | $0.50 + $0.00003 per cm2 | included |
| Hand-soldering $3.58, pre-reflow $0.016 per joint, single-board surcharge $0.48, fixture $8.21, storage $4.93, large board $57.46 (above 650 cm2) | listed on the page | quantity 0: not needed for this panel |

Other JLCPCB pages used: assembly from 2 boards <https://jlcpcb.com/pcb-assembly>; 5 bare boards minimum and the price calculator <https://cart.jlcpcb.com/quote>; capabilities (4 layers, 0.8 mm, ENIG, black solder mask) <https://jlcpcb.com/capabilities/pcb-capabilities>; more than one design in a file costs extra ("different design", amount shown only in the calculator) <https://jlcpcb.com/help/article/96-PCB-Panelization> and <https://jlcpcb.com/help/article/In-what-cases-will-there-be-charged-extra>; extra pieces for placement loss are billed inside the component price <https://jlcpcb.com/help/article/pcb-assembly-faqs-part-2>.

**Why one panel.** Both boards carry parts on both faces, so each needs Standard assembly with a set-up fee and a stencil per side. In one panel they share one order, one set-up per side, one stencil per side and the feeders of the three part numbers they have in common (C25879, C25076, C11702), and the key board gets the main PCB's 4-layer 0.8 mm ENIG stack-up. Ordered separately (fall-back files in `production/`) the two boards would pay four set-ups, four stencils and two bare-board orders: about $208 in assembly fees (estimate) instead of the $145.15 of section 5.

### 3.2 Components at LCSC / JLC (READ for 32 lines, ESTIMATE for 3) - sheet `Panel BOM`

The price tiers and the retail stock of the READ lines were read from `https://www.lcsc.com/product-detail/<LCSC number>.html` on 2026-10-14 (the v0.5 readings, kept for every part that did not change), for the pogo pin C22100007 on 2026-10-21, for the buck C139643 and the protection IC C351410 on 2026-10-22 and for R3 (C4109) on 2026-10-23 (on LCSC's product-image page of the part, because the product page could not be opened); each row of the sheet links to the product page (column E) and prints the URL and date (column AJ). The library type (Basic / Extended) was read on `https://jlcpcb.com/partdetail/<LCSC number>`; the Basic parts list is at <https://jlcpcb.com/parts/basic_parts>. The unit price is the tier that matches the quantity JLC has to buy (quantity per panel x panels + extra pieces for placement loss).

The BOM has **35 lines, 79 placements, 267 solder joints per panel** (60 parts on the main PCB, 19 on the key board); it is derived from `COMPONENTS` in `tools/kicad/flashka_parts.py` with the same grouping and ordering as `build_all.py` (lines with an empty LCSC number or `dnp` are skipped) and equals `production/BOM_JLCPCB.csv` (= `order_files/1_JLCPCB/BOM_JLCPCB.csv`) line by line. The joint count of each line is the pad count of its footprint in the two routed boards `kicad/FlashKa_main/FlashKa_main.kicad_pcb` and `kicad/FlashKa_keys/FlashKa_keys.kicad_pcb` (the buck U2 counts 17: 16 pins and the exposed pad; its two thermal vias and the paste windows are not joints). J2 (cell), J3 (LED) and J5 (laser) are wire pads, J6 the six round gold target pads of the pogo pins on the main PCB and H1, H2 the key board's screw holes: none has an LCSC number, JLCPCB does not assemble them. 18 lines are Basic, 17 are Extended (counting the four assumed types; in Standard PCBA both pay the same feeder fee, so the split does not change the price; the input for an extra Extended-part fee, `JLCPCB order!B58`, is 0). Retail stock at LCSC is not JLC's own warehouse stock; the JLC BOM upload shows the stock that matters.

**New with the 1000 lm power stage.** The 4 A buck TI TPS62095RGTR (C139643, U2; it replaces the TLV62585): LCSC stock 2,092, $1.35 for 1 piece (only that tier was read, 2026-10-22). The cell protection: PUOLOP DW01A (C351410, U6), $0.025 from 20 pieces, stock 109,860 (read 2026-10-22), and the dual MOSFET SINO-IC SE8830A (C238645, Q3): its LCSC page could not be read, so price and stock are **ESTIMATES** ($0.10 from 10 pieces, about twice the common FS8205A, C2830320, $0.050 from 10, read 2026-10-22). The SE8830A has no drop-in substitute: an 8205A-type MOSFET has about twice the on-resistance and would make the DW01A trip in turbo, at about 2-3 A. Before ordering, check the SE8830A's pin order in its data sheet (pins 1-6 S1, D, S2, G2, D, G1, as on the FS8205A; the LCSC data sheet shows it only as a picture): the board is laid out for exactly this order. Five small parts were added (C22 22 uF, C23 10 nF, C24 100 nF, R35 100 ohm, R36 1 k), R16 went from 2 k to 2.2 k and C9 and C7 were removed: the line count stays 35.

**For the 14500 cell** R3 went from 3.3 k (C25890) to 2.0 k (UNI-ROYAL 0402WGF2001TCE, C4109, Basic): the TP4057 charger gives about 494 mA, the standard charge of the F15, instead of 280 mA (a full charge in about 3.5 hours). LCSC: $0.003 from 100 pieces, stock 5,175,800 (read 2026-10-23 on LCSC's product-image page; v0.6 used the same part as R16). The BOM keeps 35 lines and 79 parts per panel.

**The pogo pins** P1-P6, Harwin P70-1010045R (C22100007): SMT, gold, no peg, free height 5.0 mm, working height 4.0 mm, 1.17 N per pin (maker's data); LCSC tiers read 2026-10-21: $1.89 from 1 piece, $1.44 from 30, $1.26 from 100, retail stock **100 pieces** (enough for 2 or 5 panels: 13 or 31 pins with one spare). JLCPCB's own stock and library type were not read (Extended is assumed): if the BOM upload shows no stock, buy the pins into your JLCPCB parts library first (Parts Manager, order from LCSC stock), then order. Other source: Digikey $0.696 at 100 pieces, 21 weeks lead time (<https://azcus.digikey.com/en/products/detail/harwin-inc/P70-1010045R/6211190>). A cheaper pin, Xinyangze YZ00615050R-08 (C7429459: $0.319 from 5, $0.25 from 50, 720 in stock, read 2026-10-22, <https://www.lcsc.com/product-detail/pogo-pin-spring-probe-connector_xinyangze-yz00615050r-08_C7429459.html>), is an option only: LCSC states neither its plating nor whether it has a peg.

The two lines **C25104 (R23, R32) and C115357 (SW1, SW2, SW3)** are the v0.6 numbers whose pages could not be read on 2026-10-18: their tiers, stock and library type are ESTIMATES (section 3.10). The tiers of C115357 are those of its sibling, the Alps SKRPABE010 (C115360, read on LCSC on 2026-10-16: $0.0759 at 10 pieces, $0.0616 at 100); the tiers of C25104 are those of the 5.1 k resistor C25905 of the same UNI-ROYAL 0402 series. The three ESTIMATE lines together cost $0.96 for 1 light and $1.96 for 5 lights.

| LCSC # | Designators | Manufacturer part | JLC type | Qty / panel | Board | LCSC stock (date read) |
|---|---|---|---|---|---|---|
| [C15850](https://www.lcsc.com/product-detail/C15850.html) | C1 | CL21A106KAYNNNE | Basic | 1 | main PCB | 20 **low** (2026-10-14) |
| [C19702](https://www.lcsc.com/product-detail/C19702.html) | C2, C13, C15 | CL10A106KP8NNNC | Basic | 3 | main PCB | 181,020 (2026-10-14) |
| [C59461](https://www.lcsc.com/product-detail/C59461.html) | C5, C8, C22 | CL10A226MQ8NRNC | Basic | 3 | main PCB | 4,416,440 (2026-10-14) |
| [C52923](https://www.lcsc.com/product-detail/C52923.html) | C12, C14, C17, C18 | CL05A105KA5NQNC | Basic | 4 | main PCB | 598,000 (2026-10-14) |
| [C15195](https://www.lcsc.com/product-detail/C15195.html) | C11, C23 | CL05B103KB5NNNC | Basic | 2 | main PCB | 0 **retail 0** (2026-10-14) |
| [C1525](https://www.lcsc.com/product-detail/C1525.html) | C10, C16, C19, C20, C24 | CL05B104KO5NNNC | Basic | 5 | main PCB | 0 **retail 0** (2026-10-14) |
| [C82044](https://www.lcsc.com/product-detail/C82044.html) | D1 | ESD5Z5.0T1G | Extended | 1 | main PCB | 370,780 (2026-10-14) |
| [C165948](https://www.lcsc.com/product-detail/C165948.html) | J1 | TYPE-C-31-M-12 | Extended | 1 | main PCB | 375,745 (2026-10-14) |
| [C602028](https://www.lcsc.com/product-detail/C602028.html) | L1 | FHD4020S-1R0MT | Extended | 1 | main PCB | 8,210 (2026-10-14) |
| [C2874113](https://www.lcsc.com/product-detail/C2874113.html) | LED3, LED4 | NH-B1010RGBT-HF | Extended | 2 | key board | 345,020 (2026-10-14) |
| [C22100007](https://www.lcsc.com/product-detail/C22100007.html) | P1, P2, P3, P4, P5, P6 | P70-1010045R | Extended (assumed) | 6 | key board | 100 **low** (2026-10-21) |
| [C15127](https://www.lcsc.com/product-detail/C15127.html) | Q1 | AO3401A | Basic | 1 | main PCB | 164,910 (2026-10-14) |
| [C238645](https://www.lcsc.com/product-detail/C238645.html) | Q3 | SE8830A | Extended (assumed) | 1 | main PCB | not read |
| [C5224240](https://www.lcsc.com/product-detail/C5224240.html) | Q2, Q4, Q5 | 2N7002W-7-F-ES | Extended | 3 | main PCB | 17,000 (2026-10-14) |
| [C25905](https://www.lcsc.com/product-detail/C25905.html) | R1, R2 | 0402WGF5101TCE | Basic | 2 | main PCB | 2,302,500 (2026-10-14) |
| [C4109](https://www.lcsc.com/product-detail/C4109.html) | R3 | 0402WGF2001TCE | Basic | 1 | main PCB | 5,175,800 (2026-10-23) |
| [C25764](https://www.lcsc.com/product-detail/C25764.html) | R10 | 0402WGF2003TCE | Basic | 1 | main PCB | 1,520,700 (2026-10-14) |
| [C25792](https://www.lcsc.com/product-detail/C25792.html) | R12 | 0402WGF4702TCE | Basic | 1 | main PCB | 3,114,700 (2026-10-14) |
| [C25744](https://www.lcsc.com/product-detail/C25744.html) | R8, R9, R13, R18, R21, R22 | 0402WGF1002TCE | Basic | 6 | main PCB | 2,846,900 (2026-10-14) |
| [C25879](https://www.lcsc.com/product-detail/C25879.html) | R14, R16, R31 | 0402WGF2201TCE | Basic | 3 | key board + main PCB | 586,000 (2026-10-14) |
| [C25104](https://www.lcsc.com/product-detail/C25104.html) | R23, R32 | 0402WGF3300TCE | Basic (assumed) | 2 | key board | not read |
| [C26083](https://www.lcsc.com/product-detail/C26083.html) | R27, R28 | 0402WGF1004TCE | Basic | 2 | main PCB | 541,000 (2026-10-14) |
| [C25741](https://www.lcsc.com/product-detail/C25741.html) | R7, R11, R15, R17, R20, R26, R29 | 0402WGF1003TCE | Basic | 7 | main PCB | 3,791,500 (2026-10-14) |
| [C25076](https://www.lcsc.com/product-detail/C25076.html) | R24, R25, R33, R34, R35 | 0402WGF1000TCE | Basic | 5 | key board + main PCB | 4,360,400 (2026-10-14) |
| [C11702](https://www.lcsc.com/product-detail/C11702.html) | R19, R30, R36 | 0402WGF1001TCE | Basic | 3 | key board + main PCB | 0 **retail 0** (2026-10-14) |
| [C92740](https://www.lcsc.com/product-detail/C92740.html) | RS1 | MS05W2F200MT5E | Extended | 1 | main PCB | 4,880 (2026-10-14) |
| [C77130](https://www.lcsc.com/product-detail/C77130.html) | RT1 | NCP15WF104F03RC | Extended | 1 | main PCB | 298,120 (2026-10-14) |
| [C431540](https://www.lcsc.com/product-detail/C431540.html) | S2 | MSK12C02 | Extended | 1 | main PCB | 170,330 (2026-10-14) |
| [C115357](https://www.lcsc.com/product-detail/C115357.html) | SW1, SW2, SW3 | SKRKAEE020 | Extended (assumed) | 3 | key board | not read |
| [C12044](https://www.lcsc.com/product-detail/C12044.html) | U1 | TP4057-42-SOT26-R | Extended | 1 | main PCB | 32,025 (2026-10-14) |
| [C139643](https://www.lcsc.com/product-detail/C139643.html) | U2 | TPS62095RGTR | Extended | 1 | main PCB | 2,092 (2026-10-22) |
| [C181502](https://www.lcsc.com/product-detail/C181502.html) | U3 | TLV333IDCKR | Extended | 1 | main PCB | 18,425 (2026-10-14) |
| [C2838502](https://www.lcsc.com/product-detail/C2838502.html) | U4 | ESP32-C3-MINI-1-N4 | Extended | 1 | main PCB | 8,387 (2026-10-14) |
| [C841192](https://www.lcsc.com/product-detail/C841192.html) | U5 | RT9080-33GJ5 | Extended | 1 | main PCB | 27,375 (2026-10-14) |
| [C351410](https://www.lcsc.com/product-detail/C351410.html) | U6 | DW01A | Extended | 1 | main PCB | 109,860 (2026-10-22) |

### 3.3 Bare panels and the two-design surcharge (ESTIMATE) - sheet `JLCPCB order`, section 4

JLCPCB shows the price of the bare panel only after the Gerber upload at <https://cart.jlcpcb.com/quote>, so the workbook uses **$30.00 for 5 panels** (4 layers, 0.8 mm, ENIG, black solder mask, 45.0 x 32.5 mm; the range $25.00 to $35.00 is shown for information) and **$15.00** for the surcharge for two designs in one file (range $10 to $20). Anchors: a 100 x 100 mm 4-layer board x 5 is about $32.90 (<https://pcbsync.com/pcb-prototype-services-compared/>, vendor not named); a forum guide puts ENIG at +$5-10 on small orders (<https://zbotic.in/how-to-order-pcb-from-jlcpcb-and-pcbway-india-cost-guide/>); v0.6 estimated $25 for five 24.0 x 16.5 mm main PCBs. The panel (key board left, main PCB right, 2.0 mm routed gaps, two 6 mm rails with 3 fiducials and 4 tooling holes; `tools/kicad/panel_jlc.py`) stays inside JLCPCB's cheapest 4-layer size class (up to 50 x 50 mm). Replace the estimates with the real prices in `JLCPCB order!B44` and `JLCPCB order!B47`. An inner copper of 1 oz instead of 0.5 oz (a small surcharge in the quote) halves the resistance of the battery strip inside the board; the board is designed for 0.5 oz, so the workbook does not include it. The main PCB outline (24.0 x 16.5 mm, 1.3 mm chamfers, 3.94 cm2) comes from `cad/housing_interface.json` (`pcb_outline`), the key board (19.0 x 14.8 mm, R1.0) from its `key_board` entry.

### 3.4 Shipping (ESTIMATE) - sheet `Hidden costs`, section 2

JLC publishes no rate table; the cart shows a "Shipping Estimate" after you enter the address. Anchors for a small JLCPCB parcel: DHL Express $21.50, EuroPacket $6.50, Global Standard Direct Line $1.50 (Chiptron, 10 Jun 2025, <https://chiptron.eu/jlcpcb-reduces-shipping-costs-pcb-order-with-shipping-worth-bad-beer/>); FedEx about $16 to Spain (EEVblog 2024, <https://eevblog.com/forum/manufacture/jlcpcb-pcb-assembly-optimal-shipping-for-eu>). The workbook defaults to express ($21.50 JLCPCB, $22.00 / $25.00 JLCCNC + JLC3DP for 1 / 5 lights) because DDP (taxes paid at checkout) works most reliably; economy ($6.50 JLCPCB, $7.00 / $9.00 JLCCNC + JLC3DP) is selectable in `Hidden costs!B11` and lowers the 1-light total by about $47.73 (5 lights: $50.14). JLCCNC merges its orders with JLC3DP (<https://jlccnc.com/news/merged-ordering>, read 2026-10-22: one package, one shipping rate, select "All" in the cart), so the resin mould adds no parcel; the JLCCNC shipping is a guess from weight (tray, lid and kits about 40 g per light, the two resin plates about 13 g; JLCCNC shows it only on the invoice). The EU casting-shop parcel (urethane, pigment, release, about 1-1.5 kg) is estimated at $18.00 express / $9.00 economy, the distributor's courier fee for the optics at $20.00 and the battery shop's courier fee for the cell and the nickel strip at $13.43 (about EUR 12: nkon.nl sends lithium cells inside the EU by courier as dangerous goods; its shipping page could not be opened), each in both modes and not read. AliExpress: $2.00 per seller parcel and 8 parcels are assumptions.

### 3.5 EU VAT, customs duty, bank fee, exchange rate - sheet `Hidden costs`, sections 1 and 3 to 5

| Input | Value | Status | URL |
|---|---|---|---|
| VAT Lithuania | 21 % | READ 2026-10-14 | <https://jlcpcb.com/help/article/EU-VAT-E-commerce-Rules-%26-Adjustments>; JLC collects it for individuals up to EUR 150: <https://jlcpcb.com/help/article/customs,-duties-and-taxes> (read 2026-10-22) |
| IOSS limit: goods value per parcel (VAT collected at checkout) | EUR 150 | READ 2026-10-14 | same page |
| Flat customs duty on low-value parcels, 1 Jul 2026 to 1 Jul 2028 | EUR 3 per customs line (goods with the same tariff code, whatever the quantity) per parcel; paid at import unless the channel is DDP | READ 2026-10-14, checked 2026-10-22 | <https://jlcpcb.com/help/article/eu-customs-reform-faq>, <https://trade.ec.europa.eu/access-to-markets/en/news/eu-applies-eu3-customs-duty-item-low-value-e-commerce-consignments>, EU guidance <https://taxation-customs.ec.europa.eu/document/download/053e5b4e-f0be-4f20-9a23-3e3b659a6676_en?filename=Customs+Guidance+on+EUR+3+customs+duty.pdf> |
| Carrier fee in formal clearance (above EUR 150) | max(EUR 15, 2 % of VAT + duty); examples: DHL Germany 2 % min EUR 15, UPS 3 % min EUR 15.70, FedEx 2.5 % min EUR 15 (JLC FAQ); UPS Lithuania 2 % min EUR 12 | READ (examples) | <https://jlcpcb.com/help/article/eu-customs-reform-faq>; <https://ups.com/assets/resources/webcontent/en_GB/additional-service-charge-lt.pdf> (read 2026-10-22) |
| Tariff rates in formal clearance | JLCPCB 0 %, JLCCNC + JLC3DP 6 % (aluminium articles HS 7616 99 90; the plastic kits and the resin mould HS 3926 90 are 6.5 %, the whole parcel is counted at 6 %), AliExpress 0 % | **ESTIMATE** (assumed HS codes; the invoice decides) | - |
| Customs lines per parcel | JLCPCB 2, JLCCNC + JLC3DP 2 (aluminium parts + plastic parts), each AliExpress parcel 1; the EU casting-shop, optic and battery-shop parcels 0 (inside the EU: no customs) | ESTIMATE | - |
| VAT on the EU parcels | 21 % on goods + shipping (conservative if a shop's price already includes VAT; kaupo.de does not say; nkon.nl's prices are taken without VAT, and the VAT of the Netherlands and of Lithuania is 21 % alike) | ASSUMPTION | - |
| Exchange rates | 1.1188 USD per EUR; 0.8446 GBP per EUR | READ (ECB, 13 Oct 2026) | <https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/eurofxref-graph-usd.en.html>; <https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/eurofxref-graph-gbp.en.html> |
| Card / currency conversion fee on the two JLC payments | 1.5 % | **ESTIMATE** (0-3 % depending on your bank) | - |

Not included: a unified EU customs handling fee of about EUR 2 per parcel that the EU plans for around Nov 2026 (not final when this was written), your own time, a second PCB or housing round (shown as risk reserve).

### 3.6 Housing (ESTIMATE) - sheet `Housing`

The real price of CNC parts and prints appears only after the upload, and JLCCNC and JLC3DP publish no per-part price list, so the workbook estimates every housing price with a stated method. Type the instant quotes into `Housing!B95` / `Housing!C95` (tray + lid, scenario A / B), `Housing!E121` / `Housing!G121` (the two kits) and `Housing!B109` / `Housing!C109` (the mould) when you have them. The housing costs $132.91 for 1 light and $432.50 for 5 lights: tray + lid $98.34 / $347.69, kits $31.25 / $81.50, resin mould $3.32 / $3.32.

* **JLCCNC aluminium tray + lid.** Method (sheet sections 2 to 6): cost of one part = aluminium block (bounding box + 2 mm on every side, 6061 at $8.00 per kg, you pay for the whole block) + machining (material to remove / 6 cm3 per min + fine-feature minutes, x $0.60 per min x complexity factor) + $0.25 per thread + finish; the set-ups ($3.50 each: tray 5, lid 3) and the anodizing lot fee ($8.00) are paid once per order. All of these parameters are ESTIMATES (the machine rate was calibrated in v0.5 so that one tray + lid costs about what the v0.4 estimate gave). v0.7 keeps every v0.6 parameter and changes only what the new design changes (table below). JLCCNC publishes no price list (<https://jlccnc.com/blog/cnc-machining-cost-factors> only explains the cost factors). Facts READ from JLCCNC (2026-10-14, the capabilities and finishes pages again on 2026-10-16; those two pages could not be read on 2026-10-21): 6061-T6, bead blast + black anodize as one combined option, anodize 8-25 um, ISO 2768-m, threads supported but M1.6 not listed, minimum metal wall 0.8 mm (absolute minimum 0.5 mm), STEP mandatory + drawing PDF with identical file names, standard lead time from 3 working days, quote within 24 h, more than 20 pieces go to a manual quote (<https://jlccnc.com/capabilities/cnc-machining-service>, <https://jlccnc.com/help/article/cnc-machining-ordering-guidelines>, <https://jlccnc.com/finishes>, <https://jlccnc.com/cnc-machining-quote>). The finish prices and lot fees per finish are ESTIMATES. Upload: `order_files/2_JLCCNC/FlashKa_tray.step` + `FlashKa_tray.pdf` and `FlashKa_lid.step` + `FlashKa_lid.pdf` (the drawings `cad/FlashKa_tray_drawing.pdf`, FK-H-01, 2 sheets, and `cad/FlashKa_lid_drawing.pdf`, FK-H-02, renamed to the STEP names).
* **The panel texture is a priced option.** It is $10.25 of the 1-light tray + lid estimate ($51.26 for five sets): texture minutes x machine rate x complexity factor. `Housing!B33` = 0 prices the tray and lid without it, and the options table (section 2.3) shows the landed saving. It stays in the default because the STEP files carry it: a shop that is to skip it must be told so (feature 17 of drawing FK-H-01).
* **What v0.7 changes in the aluminium estimate.**

| | v0.6 | v0.7 | Why |
|---|---|---|---|
| Tray / lid volume | 8401.2 / 2643.3 mm3 | 8328.5 / 3120.7 mm3 | `volumes_mm3` of `cad/housing_interface.json`: the 99.2 mm octagonal body (20 x 18 mm) with the optic bore, the key bezel and openings, the cell bay with its rails, recessed panels, texture and grooves; the v0.6 floor holes and skin seams are gone |
| Lid size | 90.2 x 20 x 5.2 mm | 95 x 20 x 7.25 mm | a 3.4 mm cap (top facet and two diagonal facets) with its two hold-down bosses |
| Stock block tray / lid | 47.2 / 20.8 cm3 | 54.5 / 26.7 cm3 | bounding box + 2 mm on every side |
| Fine-feature time tray / lid | 38.1 / 7.5 min | 54.2 / 14.0 min | table below |
| Machining time tray / lid | 44.6 / 10.5 min | 61.9 / 18.0 min | material to remove / 6 cm3 per min + fine-feature time |
| Complexity factor tray / lid | 1.10 / 1.30 | 1.10 / 1.30 | ESTIMATE, unchanged: the texture and grooves need indexed set-ups on the facets and ends; the lid is a cap with a 1.5 mm plate over the cavity and two bosses |
| Set-ups tray / lid | 5 / 3 | 5 / 3 | ESTIMATE, unchanged |
| Threads in the tray | 5 | 7 | two blind M1.6 threads for the key-board screws; the laser set-screw thread is M1.6 from the head-block top, under the lid (v0.6: M2 from the bottom face) |
| Laser marking | 4 faces, $2.00 per face + $5.00 per order | none | v0.7 carries no marking (an optional label DXF exists for lights given to others) |
| One set (scenario A) | $93.36 | $98.34 | +$4.98 |
| Five sets (scenario B) | $302.79 | $347.69 | +$44.90 |

  The change for one set, +$4.98, is no laser marking -$13.00, more machining and material +$17.48 (the fine-feature minutes of the texture, the grooves and the facets, the longer and taller body) and two more threads +$0.50. For five sets it is +$44.90: marking -$45.00, machining and material +$87.40, threads +$2.50.

  The fine-feature time is the part of the estimate that needs an explanation. v0.6 priced all fine work as tray 38.09 min and lid 7.52 min. v0.7 keeps that, takes out the features that no longer exist and adds the new ones. V-groove work is counted in millimetres at ONE rate (6 min per metre, i.e. $3.60 per metre before the complexity factor) for the seams that go and for the texture and grooves that come, so the groove part of the change follows the real geometry: the v0.7 lengths are computed from `panel_layout` and the groove parameters of `cad/housing_interface.json` (11 recessed panels: 8 on the tray, 3 on the lid; texture length = panel area / 0.9 mm pitch, without the floor RF window opening, which is a textured POM-C plug). The other lines are typed-in minutes (ESTIMATES).

| Feature | Tray | Lid | Unit | Tray (min) | Lid (min) |
|---|---|---|---|---|---|
| v0.6 fine-feature time (the result of the v0.6 workbook) | 38.09 | 7.52 | min | 38.1 | 7.5 |
| minus the v0.6 skin seams (frames and stringers, 0.25 deep) | -646.5 | -220.2 | mm of V-groove | -3.9 | -1.3 |
| minus the v0.6 floor holes for the caps and the light tube | -3 | 0 | min | -3.0 | +0.0 |
| plus the key bezel (stadium recess 0.5 deep, 45 deg walls) and the three key openings with their flange seats | 4 | 0 | min | +4.0 | +0.0 |
| plus the octagon: the four diagonal facets, the lid's cap pocket (45 deg walls, flat seat) and the two floor rails of the cell bay | 1.5 | 1.5 | min | +1.5 | +1.5 |
| plus the two key-board bosses (blind M1.6) and the four support ribs on the floor | 1.5 | 0 | min | +1.5 | +0.0 |
| plus the recessed panels, 0.3 deep, corners R0.8 (8 on the tray, 3 on the lid) | 4 | 1.5 | min | +4.0 | +1.5 |
| plus the V texture in the panels (90 deg V, 0.2 deep, pitch 0.9, at 45 deg) - a priced option: x 'texture_on' (section 2) | 1719.5 | 735.7 | mm of V-groove | +10.3 | +4.4 |
| plus the transverse V grooves, 0.3 deep: 3 at the head (top, bottom and diagonal facets), 3 at the tail (all round) | 272.5 | 68.4 | mm of V-groove | +1.6 | +0.4 |
| **Fine-feature time, v0.7** | | | | **54.2** | **14.0** |

* **PMMA and POM-C kits (ESTIMATE).** JLCCNC machines plastic parts only from 30 x 20 x 8 mm up (<https://jlccnc.com/help/article/what-are-the-maximum-and-minimum-processing-sizes-for-cnc>, read 2026-10-21); the main key (7.6 x 7.6 x 2.75 mm) and every POM-C part are smaller, so the housing build puts them into two kits, each one solid piece with the parts on 0.6 mm tabs in a frame: `FlashKa_pmma_kit` (52.8 x 22 x 8.5 mm, three clear main keys: one per light + two spares) and `FlashKa_pom_kit` (45.4 x 39.3 x 17 mm: two lid RF inserts and one antenna spacer with the floor plug = the POM-C parts of one light plus a spare insert; the LED spacer ring of the first v0.7 layout is gone with the glass window). PMMA (acrylic) and POM are listed JLCCNC plastics (<https://jlccnc.com/help/article/how-to-place-cnc-orders>); whether one order may mix materials is not stated (probable). JLCCNC publishes no price for plastic parts: the estimate is **$7.50 for the first PMMA key** and **$6.50 for the first piece of each POM-C part type** (research range: PMMA key with polish $6-9, POM-C $5-8 per part type), each further piece of the same type **50 %** of its first piece (the rule the v0.6 workbook used for its small CNC parts). Kits ordered: PMMA ROUNDUP((lights + 1) / 3), POM-C one per light: 1 + 1 kits for 1 light ($31.25), 1 + 2 for 2 lights ($41.00), 2 + 5 for 5 lights ($81.50). Upload `order_files/2_JLCCNC/FlashKa_pmma_kit.step` + `.pdf` (FK-H-06) and `FlashKa_pom_kit.step` + `.pdf` (FK-H-07). The single parts are in the same folder for shops that take small parts.
* **PMMA polish.** Drawing FK-H-03 asks for a vapour or flame polish on every face (the key is the light guide of the ring; JLCCNC's PMMA blog calls flame or vapour polishing a must for light-guiding parts, <https://jlccnc.com/blog/acrylic-and-pmma-cnc-machining>), but JLCCNC's polishing guide lists only machine and CNC polishing (<https://jlccnc.com/blog/acrylic-polishing-guide>): ask in the quote, or polish at home (polishes in `Bought parts`).
* **Casting mould (ESTIMATE, once per builder).** Default: two SLA resin plates from JLC3DP, 48 x 28 x 8.51 mm (cavity half, 6.24 cm3, with its printed pins) and 48 x 28 x 5.47 mm (lid with the four plateaus, 4.82 cm3), drawing FK-H-08, `order_files/3_rubber_keys/FlashKa_key_mould_resin_cavity.stl` and `..._resin_lid.stl`. JLC3DP publishes only its headline "SLA from $0.30" (<https://jlc3dp.com/>, re-read 2026-10-22): the estimate is MAX($0.60 per part, $0.30 per cm3 of model volume) per plate = $1.87 + $1.45 = **$3.32**, plus four M3 x 16 bolts with washers and nuts ($4.00, `Bought parts`). Option: the two aluminium 6061-T6 plates (48 x 28 x 8 mm and 48 x 28 x 8.47 mm, JLCCNC), priced with the aluminium model (fine-feature time 14 + 6 min, complexity factor 1.30, 2 set-ups each, 4 x M3, $1.00 for the bead blast): **$35.12**, plus 2 dowel pins and 4 M3 x 12 screws ($5.00). A builder who already has a mould types 0 in `Housing!B109`.
* **Laser sleeve.** The optional POM-C sleeve for a laser module thinner than 6 mm (10.0 x 6.0 x 5.97 mm) is too small for the instant quote and not in a kit: quantity 0, not in the totals.
* **Geometry.** Volumes and masses of the tray, lid, POM-C parts, keys and stiffener, the tray bounding box, the PCB outline, the key board, the panel layout, the wall checks, the kit contents and the hold-down results come from `cad/housing_interface.json` (version 0.7: tray 8328.5 mm3, lid 3120.7 mm3); the mould plates from `cad/key_mould_checks.json`; the STL files in `cad/` give the bounding boxes (section 8).

### 3.7 Bought parts and consumables - sheet `Bought parts`

AliExpress item pages cannot be read automatically, so the prices of the v0.5 items come from search-result snippets of 2026-10-14 or are typical prices. The listed item is only a price anchor: check size and specification in the listing yourself. The LED board, the TIR optic and the urethane rubber were read on 2026-10-22, the cell and the nickel strip on 2026-10-23; the other items are typical prices, NOT looked up.

| Item | Workbook price | Anchor |
|---|---|---|
| Vapcell INR14500 F15, 1500 mAh, 3 A, flat top, no protection board (1 per light + 1 spare) | $3.47 per cell | **READ** at nkon.nl on 2026-10-23: EUR 3.10 excl. VAT (EUR 3.75 incl.; EUR 2.85 excl. from 10 cells), in stock, <https://www.nkon.nl/en/vapcell-f15-inr14500-1500mah-3a.html>; maker's data <https://www.vapcelltech.com/h-pd-251.html>. Alternative Vapcell INR14500 K10 (1000 mAh, 8 A, flat top): $4.30 at illumn.com (USA), <https://illumn.com/14500-vapcell-inr14500-k10-1000mah-8a-high-discharge-flat-top-li-ion-battery.html>; nkon's similar H10 (EUR 3.26 excl. VAT) out of stock, <https://www.nkon.nl/en/vapcell-inr14500-1000mah-10a.html> |
| Nickel strip 0.2 x 5 mm, pure nickel, 1 m (the cell's two tabs) | $2.08 per 1 m | **READ** at nkon.nl on 2026-10-23: EUR 1.86 excl. VAT (EUR 2.25 incl.), nickel >= 99.7 %, in stock, <https://nkon.nl/en/1-meter-nikkel-batterijsoldeerstrip-5mm-0-2mm.html> |
| SST-20 Gen 2 6500 K on a 10 mm copper DTP board (+1 spare) | $2.99 per board | **READ** at Kaidomain on 2026-10-22: USD 1.99 + USD 1.00 for the 10 mm board, <https://kaidomain.com/SST-20-Gen-2-10W-3A-1100-Lumens-SMD-3535-LED>; bin not stated |
| TIR optic LEDiL LISA3-RS-PIN (FP16558), pack of 5 | $17.37 per pack of 5 | **READ** at RS UK on 2026-10-22: GBP 13.11 per 5 excl. VAT, 190 in stock, <https://uk.rs-online.com/web/p/led-lenses-reflectors/1862699>; converted at 0.8446 GBP and 1.1188 USD per EUR. Also: RS by 100 at GBP 1.35 each (<https://uk.rs-online.com/web/p/led-lenses-reflectors/1862399>); Mouser EU only the clip version at EUR 2.82 (<https://eu.mouser.com/ProductDetail/Ledil/FP18198_LISA3-RS-CLIP16?qs=Rp5uXu7WBW9W1JI96qOsiA%3D%3D>); LEDiL data sheet <https://www.ledil.com/data/prod/Lisa/16558/16558-ds.pdf> |
| Green laser module 520 nm, 6 x 12 mm, 1 mW APC | $23.50 per module | $23.5 for a 6 mm 520 nm 1 mW APC module, <https://www.aliexpress.com/item/32869119160.html>, 2026-10-14 |
| Screw M1.6 x 6 countersunk (lid) | $2.00 per 100 pcs | $1.5 for 100 pcs M1.6 x 3 countersunk, <https://www.aliexpress.com/item/32917852857.html>, 2026-10-14; the 6 mm length priced slightly higher |
| Screw M1.6 x 2.5 pan head (key board, 2 per light) | $2.00 per 100 pcs | priced like the lid screws; no listing verified (2026-10-21); industrial sources about EUR 0.5 per screw |
| M3 x 16 bolts, washers and nuts for the resin mould (once) | $4.00 per set (small packs) | typical price; no listing read |
| PTFE wire 24 AWG, red + black, 5 m each | $7.00 per 5 m | typical price; no listing read |
| Thermal paste, small syringe | $2.50 per syringe | typical price; no listing read |
| Silicone thermal gap pad 1.5 mm, Shore 00 70-80 (cut to 8.8 x 12.4 mm) | $3.50 per sheet | typical price; no listing read |
| Silicone rubber sheet 1.0 mm, Shore A 70 (cut to 3.7 x 3.0 mm) | $3.50 per sheet | typical price; no listing read |
| Urethane rubber Smooth-On ECON 80, 0.86 kg (A + B) | $31.95 per kit (0.86 kg) | **READ** at kaupo.de on 2026-10-22: EUR 28.56 (VAT status not stated) = $31.95 at 1.1188 (<https://www.kaupo.de/shop/en/URETHANE-RUBBER/ECON-SERIES/Econ-80/Econ-80-1-Polyurethan.html>); Smooth-On's US shop: 1.9 lb trial unit USD 24.93 (<https://shop.smooth-on.com/econ-80>); PMC-780 DRY 1.36 kg EUR 53.99 at kaupo.de (<https://kaupo.de/shop/en/URETHANE-RUBBER/PMC-SERIE/PMC-780/PMC-780-1-dry-Urethane-Rubber.html>) |
| Black pigment for urethane rubber (SO-Strong black) | $12.00 per bottle | typical price; no listing read |
| Mould release (Universal Mold Release) | $18.00 per can | typical price; no listing read |
| Stainless steel shim 0.3 mm, small sheet | $4.00 per sheet | typical price; no listing read |
| Cyanoacrylate, rubber-toughened | $5.00 per bottle | typical price; no listing read |
| Mixing cups, two 5 ml syringes, sticks, nitrile gloves | $5.00 per set | typical price; no listing read |
| Plastic polish, metal polish, wet-and-dry paper 400-3000 | $10.00 per set | typical price; no listing read |
| M1.6 x 5 set screw (50), split ring 25 mm (20), Kapton tape, 0.5 mm foam sheet, two-part epoxy, silicone adhesive | $2.00 / $2.00 / $2.50 / $2.50 / $3.50 / $2.50 | typical prices |
| Options, not in the totals: Sugru black 3 x 3.5 g; petroleum jelly; dowel pins 2 x 8 mm (10); M3 x 12 screws (50) | $8.94 / $2.00 / $2.50 / $2.50 | Sugru **READ** at toom.de on 2026-10-22: EUR 7.99 incl. German VAT (<https://toom.de/p/allzweckkleber-sugru-formbar-schwarz-3-x-35-g/8400437>); the rest typical prices |

What the hold-down pads do: the six pogo pins of the key board push the main PCB up with 7.37 N in total, so the lid holds the board down with two pads: a piece of the 1.5 mm gap pad (8.8 x 12.4 mm) on the can boss over the ESP32 module, compressed to 1.15 mm, and a piece of the 1.0 mm rubber sheet (3.7 x 3.0 mm) on the front boss, compressed to 0.75 mm. Together they press with 39.68 N; the plate model of the board gives a lift of 0.0004 mm (limit 0.02 mm). Softness matters, the thermal rating does not. Use neutral-cure silicone (no acetic-acid smell) and a drop per boss only. Two-part epoxy glues the TIR optic into the head bore; **never cyanoacrylate near the optic or the clear PMMA key** (its vapour leaves a white bloom); the cyanoacrylate is only for the stiffeners of the rubber keys.

The side keys are cast at home in the resin mould, four per pour (two plus two spares): about 0.22 cm3 of rubber for four keys, mixed as 5 ml A + 5 ml B with two syringes (ECON 80 is mixed 1:1 by volume). One 0.86 kg unit therefore lasts for many pours; the rubber in one light is worth a few cents, the unit is a one-off cost. The steps are in `order_files/3_rubber_keys/README.txt` and in the build guide. The search terms and the exact specifications that matter (a flat-top 14500 cell up to 14.5 x 50.4 mm, the 10 mm LED board, the LISA3-RS-PIN optic, the 6 mm laser, the 2.5 mm key-board screw length) are in the sheet. Prices exclude VAT and shipping; the Hidden costs sheet adds both. The sheet also explains why the laser must be **Class 2** (visible, 1 mW or less continuous) and cites EN 50689:2021 for consumer laser products (<https://ul.com/insights/understand-new-laser-product-safety-standards-europe>, background <https://en.wikipedia.org/wiki/Laser_safety>).

### 3.8 Tools (ESTIMATE) - sheet `Tools`

24 tools with typical 2026 web-shop prices (soldering iron $35, multimeter $15, laser safety glasses 520 nm $14, caliper $12 ...), no source page; $204.00 for the tools marked "needed" (set "needed" to 0 for what you own), $170.00 more for the optional ones (microscope, bench supply, laser power meter, hand taps, vacuum chamber, and the 0.01 g scale, which only PMC-780 DRY needs). For casting the keys and cutting the stiffeners: small vice $15, tin snips $8, needle files $6; for the cell's tabs a small spot welder for 0.1-0.2 mm nickel strip, $40 (set "needed" to 0 if you buy the cell with welded tabs or have a shop weld them; never solder onto the cell). v0.6 total $135.00; first v0.7 layout $174.00. The flush cutters also cut the kits' tabs, the optic's pins and the casting stubs. A laser power meter is the only way to verify a "1 mW" claim, so consider it if you plan to give lights away.

### 3.9 Spares and placement loss

JLC buys a few more pieces than the panels need (lost by the placement machine) and bills them inside the component price. The extra counts (10 for 0402 resistors and capacitors, 5 for 0603 / 0805, 2 for small semiconductors, 1 for big parts and the pogo pins) are ESTIMATES (JLC publishes no table; the cart shows the real quantity): $11.30 of the $46.75 component cost for 1 light. The bought parts include spares (a spare cell, a second LED board, the other optics of the pack, extra screws) and left-over pack contents; the casting supplies are one-off packs: of the $181.32 for bought parts and consumables (1 light) about $146.86 is material you will not use for this light (information row in `Bought parts`). The spare main keys come in the PMMA kit (three keys, one used), the spare lid insert in the POM-C kit, and every pour gives two spare side keys.

### 3.10 Pages that could not be read, and what is an ESTIMATE because of it

| Page | Date | What it would have given | Consequence in the workbook |
|---|---|---|---|
| <https://jlcpcb.com/partdetail/C115357> | 2026-10-18 | library type of the Alps SKRKAEE020 (SW1-SW3) | type "Extended" is assumed (every Alps tact switch checked on JLCPCB is Extended) |
| <https://www.lcsc.com/product-detail/C115357.html> | 2026-10-18 | price tiers and stock of SKRKAEE020 | tiers of the sibling Alps SKRPABE010 (C115360, read 2026-10-16): $0.0759 at 10, $0.0616 at 100; stock unknown |
| <https://jlcpcb.com/partdetail/C25104> | 2026-10-18 | library type of the 330 ohm resistor (R23, R32) | type "Basic" is assumed (same UNI-ROYAL 0402 series as the other Basic resistors) |
| <https://www.lcsc.com/product-detail/C25104.html> | 2026-10-18 | price tiers and stock of the 330 ohm resistor | tiers of the 5.1 k resistor C25905 (read 2026-10-14); stock unknown |
| <https://www.lcsc.com/product-detail/C238645.html> | 2026-10-22 | price tiers and stock of the MOSFET SE8830A (Q3) | ESTIMATE $0.10 from 10, $0.08 from 100 (about twice the FS8205A); type "Extended" assumed; stock unknown |
| <https://www.lcsc.com/product-detail/C4109.html> | 2026-10-23 | the product page of R3 (2.0 k) | none: the tiers and the stock were read on LCSC's product-image page <https://www.lcsc.com/product-image/C4109.html> the same day; the library type Basic was read on 2026-10-14 (R16 of v0.6) |
| nkon.nl shipping information (<https://www.nkon.nl/en/>) | 2026-10-23 | the courier fee for a parcel with a lithium cell to Lithuania | ESTIMATE about EUR 12 ($13.43) for the battery shop's parcel |
| <https://jlcpcb.com/partdetail/C22100007> | 2026-10-21 | JLCPCB's library type and own stock of the pogo pin | type "Extended" is assumed; the LCSC page (tiers, 100 pieces) was read the same day |
| <https://jlccnc.com/finishes> and <https://jlccnc.com/capabilities/cnc-machining-service> | 2026-10-21 | finish options and capability limits | the v0.6 readings (2026-10-14 and 2026-10-16) are kept; the finish prices were ESTIMATES anyway |
| an EU site of RS (stock no. 186-2699) | 2026-10-22 | the optic's price in EUR and the courier fee to Lithuania | the RS UK price, converted; the courier fee is an ESTIMATE |
| AliExpress item pages | - | prices of the bought parts | not read automatically: the v0.5 search-result anchors are kept, the new small items are typical prices |

The three unread BOM lines are blue on amber in `Panel BOM` (rows 21, 29, 37) and named in the Summary. The part-number text "0402WGF3300TCE" of C25104 is inferred from the UNI-ROYAL naming of the other resistors, not read.

## 4. What is an estimate

READ (copied from a page on the date given): the JLCPCB Standard PCBA fee rows and X-ray tiers (2026-10-14; set-up, stencil, feeder and the panel fee checked 2026-10-21); LCSC price tiers, stock and Basic / Extended type for 32 of the 35 BOM lines (2026-10-14; the pogo pin's tiers and stock 2026-10-21; the buck and the protection IC 2026-10-22; R3 2026-10-23); VAT 21 %, the EUR 150 IOSS limit, the EUR 3 flat duty, the carrier-fee examples (2026-10-14, checked 2026-10-22); the ECB rates (13 Oct 2026); JLCCNC's technical limits (2026-10-14 and 2026-10-16; the plastic minimum size 2026-10-21; merged ordering with JLC3DP 2026-10-22); the LED board, the TIR optic, the ECON 80 urethane and Sugru (2026-10-22); the cell, the nickel strip and the price of the K10 alternative (2026-10-23); the price tiers of the Alps SKRPABE010 (C115360, 2026-10-16), used as the stand-in for the switch.

ESTIMATE (blue on amber in the workbook):

* the three BOM lines **C115357** (SW1-SW3), **C25104** (R23, R32) and **C238645** (Q3): tiers, stock and library type (section 3.10); the library type of the pogo pin **C22100007**;
* the X-ray count of 4 parts per panel and whether the $0.46 per panel panelisation fee applies (both are included to be on the safe side: together $14.04 for 1 light);
* the bare panel price ($30.00 for 5, range $25.00 to $35.00) and the surcharge for two designs in one file ($15.00, range $10 to $20);
* all shipping prices (including the courier fees of the optic distributor and of the battery shop), the number of AliExpress parcels (8, or 3 if you buy the small hardware in one EU shop) and $2.00 shipping per AliExpress parcel;
* the card / currency fee (1.5 %);
* the tariff rates and customs lines in formal clearance (0 % JLCPCB, 6 % JLCCNC + JLC3DP with 2 lines); they matter for every parcel above EUR 150 - in scenario A the JLCPCB parcel;
* the placement-loss extra pieces;
* the complete JLCCNC aluminium model (aluminium price, machine rate, minutes, set-ups, tapping, finish prices, anodizing lot fee, the V-groove rate of 6 min per metre, the fine-feature minutes, the complexity factors) for the tray, the lid and the aluminium mould option, and the mould's bead blast ($1.00);
* the **resin mould** (JLC3DP: $0.30 per cm3, at least $0.60 per part) and the **plastic kits** ($7.50 for the first PMMA key, $6.50 for the first piece of each POM-C part type, 50 % for each further piece): no public price;
* every bought part and consumable except the cell, the nickel strip, the LED board, the optic and the urethane (the laser and the lid screws have v0.5 search-result anchors, see 3.7), and all tools;
* the risk reserves (a second order of the same size, factor 1.0 in `Hidden costs`; not part of any total).

Nothing is left unpriced.

**How to replace an estimate with a real number.**

| Estimate | Where the real number comes from | Where to type it |
|---|---|---|
| bare panels | price for 5 panels in the JLCPCB cart after the Gerber upload | `JLCPCB order!B44` |
| two-design surcharge | the "different design" line of the same cart | `JLCPCB order!B47` |
| C115357, C25104, C238645 | the three LCSC pages, and the JLC BOM upload (library type, stock) | tiers, type and stock in the rows 21, 29, 37 of `Panel BOM`; to keep it, change their entries of `LCSC_DATA` in `tools/parts_list.py` (remove `est=True` and `type_est=True`) and rebuild |
| tray + lid (finish included) | JLCCNC instant quote for `FlashKa_tray` and `FlashKa_lid` | `Housing!B95` (1 light) / `Housing!C95` (5 lights) |
| PMMA and POM-C kits | JLCCNC instant quote for `FlashKa_pmma_kit` and `FlashKa_pom_kit` (or a quote for the single parts from another shop) | `Housing!E121` / `Housing!G121` |
| casting mould | JLC3DP quote for the two resin STL files (or the JLCCNC quote of the aluminium mould); 0 if you have a mould | `Housing!B109` / `Housing!C109` |
| shipping | "Shipping Estimate" of each cart (economy / express) | `Hidden costs!B20:E24`, mode in `Hidden costs!B11` |
| surface finish | your choice at JLCCNC | `Housing!B42` |
| bought parts and tools | the listing you actually buy from | column F of `Bought parts` and `Tools` |
| exchange rate | your bank | `Summary!B6` |

## 5. Biggest uncertainties in the total

* **Housing** (1 light $132.91, 5 lights $432.50): a pure estimate until the JLCCNC and JLC3DP quotes; CNC prices of one-off parts can differ a lot from a model. Get the instant quotes first. Twice the kit estimate would raise the 1-light total by $38.38 (5 lights: $106.10), half of it would lower it by $19.19 (5 lights: $53.05), VAT and customs included. A JLCCNC quote far above the estimate can push the 1-light housing parcel above EUR 150 (section 2.4).
* **One-off costs of the side keys:** the resin mould ($3.32), its bolts ($4.00) and the casting supplies ($85.95). Without them - a second batch, or a mould and a unit of rubber shared with another builder - one light costs $746.37 instead of $859.28; without the mould only (the casting supplies still bought): $855.21.
* **The cell's parcel:** the F15 is READ ($3.47 each at nkon.nl), but the courier fee of the battery shop's parcel is an ESTIMATE ($13.43; lithium cells ship as dangerous goods). A pre-tabbed cell, if a shop offers it, saves the spot welder ($40.00, a tool, not in the totals).
* **The optic's route:** the RS UK price is used for an EU delivery; the courier fee (ESTIMATE $20.00) is the biggest part of the optic's cost for one light.
* **Shipping and the EUR 150 lines:** express versus economy shipping moves the 1-light total by about $47.73 (section 2.4).
* **Bare panels and the two-design surcharge:** at $25.00 for 5 panels the 1-light total would be $853.14 (-$6.14), at $35.00 it would be $865.42 (+$6.14); the surcharge at $10 / $20 gives $853.14 / $865.42. The JLCPCB parcel stays above the EUR 150 line in every case.
* **AliExpress parcels:** buying the small hardware in one EU shop instead of several AliExpress sellers (3 parcels instead of 8) saves $26.78 in shipping and flat duty (`Hidden costs`, section 6), $28.88 with the VAT on the saved shipping.
* **X-ray fee:** if the cart does not ask for it, the 1-light total is $16.11 lower.
* **Stock:** LCSC had only 100 pogo pins on 2026-10-21 and JLCPCB's own stock was not read; the stock of the SE8830A (C238645) could not be read. If a part is not available, the build waits (buy it into the JLCPCB parts library first, or the pins from Digikey with 21 weeks lead time). If C115357 is not in stock at JLC, the build waits or needs another switch with the same footprint (`SW_Push_SPST_NO_Alps_SKRK`, 3.9 x 2.9 x 2.0 mm); if C25104 is not available, any 330 ohm 1 % 0402 resistor will do (update `flashka_parts.py`).
* **Hold-down of the main PCB (a risk to the build, not to the price).** The two silicone pads hold the board down against the pogo pins: preload 39.68 N against 7.37 N of pin force, a lift of 0.0004 mm against a limit of 0.02 mm in the plate model (pad moduli assumed from the Shore hardness: 1.0 MPa thermal pad, 5.3 MPa rubber sheet; `cad/housing_interface.json`, `holddown`). Real boards are stiffer than the plate model. Cut the pads to the sizes in the sheet and do not use a thinner or softer pad.
* **Casting at home** has not been tried yet: the open pour, the resin mould's tolerance, the polishing of the chevron grooves and the batch size come from the rubber maker's data and the model, not from a test. A failed pour costs a few cents of rubber; the mould and the rubber stay usable.

## 6. What to re-check before you order

1. **Stock and prices.** LCSC prices change weekly. Open the LCSC links in `Panel BOM` and look for red lines in the JLC BOM upload. Lines flagged: C15850 (20 pcs), C15195 (0 pcs), C1525 (0 pcs), C22100007 (100 pcs), C11702 (0 pcs) are low or 0 at LCSC retail (C15195, C1525 and C11702 are JLC Basic parts with their own stock; C1525: 23,496,493 pcs on the JLC Basic parts list on 2026-10-14; C22100007: 100 pieces on 2026-10-21). **Stock NOT read:** C238645, C25104, C115357. U4, the ESP32-C3-MINI-1-N4 (C2838502), is marked NRND (not recommended for new designs) by Espressif; the drop-in alternative is the ESP32-C3-MINI-1-H4X (C41349510). If a line is rejected, substitute it and update `flashka_parts.py`.
2. **The order files.** Upload only the files of the ready-to-upload folder `order_files/` of the package: `1_JLCPCB/` (`FlashKa_panel_gerbers.zip`, `BOM_JLCPCB.csv`, `CPL_JLCPCB.csv`: the panel files `tools/kicad/build_all.py` writes to `production/`), `2_JLCCNC/` (`FlashKa_tray.step` + `.pdf`, `FlashKa_lid.step` + `.pdf`, `FlashKa_pmma_kit.step` + `.pdf`, `FlashKa_pom_kit.step` + `.pdf`; the single parts `FlashKa_key_main.step` + `.pdf`, `FlashKa_rf_window.step`, `FlashKa_antenna_spacer.step` with `FlashKa_pom_parts.pdf` for other shops; `FlashKa_laser_sleeve.step` only for a thinner laser) and `3_rubber_keys/` (`FlashKa_key_mould_resin_cavity.stl` + `FlashKa_key_mould_resin_lid.stl` to JLC3DP, in the merged JLCCNC order; the aluminium option `FlashKa_key_mould_cavity.step` + `FlashKa_key_mould_lid.step` + `FlashKa_key_mould.pdf` to JLCCNC; the key, stiffener and closed-mould files for reference). The BOM sheet agrees line by line with what `build_all.py` writes: 35 lines, 79 parts (the workbook script only extracts its `bom()` function; `build_all.py` itself re-routes the boards and takes long).
3. **JLCPCB cart.** Upload the Gerber, choose black solder mask, "Panel by Customer" and "Different Design" 2, then replace the bare panel price and the two-design surcharge (`JLCPCB order!B44`, `JLCPCB order!B47`), compare the fee lines with section 5 of that sheet (does the cart list the panel fee, panelisation and X-ray, and for how many parts?), copy the "Shipping Estimate" into `Hidden costs`, check the part rotations in the placement preview (U1-U6, Q1-Q5, J1 on the main PCB; SW1-SW3, LED3, LED4, P1-P6 on the key board) and choose DDP (taxes paid at checkout). **The rotation and pin 1 of the SKRKAEE020 (SW1-SW3), the NH-B1010RGBT-HF (LED3, LED4) and the pogo pins in the JLC library are not verified**: look at the placement preview and the photo of the placement confirmation.
4. **The EUR 150 lines** of the JLCPCB and the JLCCNC + JLC3DP parcel (section 2.4): check the goods value shown in each cart; with economy shipping and two lights, split the housing order.
5. **Housing quotes and fit.**
   * JLCCNC tray + lid: type the instant quote into the workbook; ask in the quote chat whether M1.6 threads are possible (not listed on the capability page; two of them are blind and must not break through the floor; fallback: plain 1.25 mm holes and hand taps, the blind ones finished with a bottoming tap, see `Tools`); the metal walls below JLCCNC's recommended 0.8 mm are 0.51 mm (the two front lid taps at the thread root, to the head's rear face and to the optic bore floor); 0.751 mm (the upper LED wire groove to the head-block top under the lid) (`min_walls` of `cad/housing_interface.json`); none is below its absolute minimum of 0.5 mm (drawing FK-H-01 note 7): name them in the quote chat; anodizing (type II 8-12 um on the drawings; JLCCNC states 8-25 um) grows in the bores, threads, key openings and the 0.2 mm texture: the drawings say tolerances apply after finishing and threads are tapped before anodizing and gauged after it - ask JLCCNC to confirm, and test-fit the first set before you order five. Ask for the 90 degree V engraving cutter of the texture (or say that it is to be left out).
   * **The two kits.** Ask whether JLCCNC accepts parts on tabs in a frame; if not, any CNC shop that takes small parts can make the single files. Polish: ask for vapour or flame polish of the PMMA keys (drawing FK-H-03), or polish at home; keep the frosted ring matte.
   * **The mould.** Resin plates from JLC3DP in the same merged order (select "All" in the cart). On arrival sand the cavity floors with 400-grit paper, polish the chevron groove floors once, and try the first cast key in its opening. The aluminium option: 6061-T6, cavity half fine glass-bead blasted, lid as machined, cavities +/-0.02 mm, a 0.6 mm end mill for the chevron groove (drawing FK-H-08).
6. **Pads.** Buy the 1.5 mm silicone thermal gap pad (Shore 00 70-80) and the 1.0 mm silicone rubber sheet (Shore A 70), cut 8.8 x 12.4 mm and 3.7 x 3.0 mm and stick them on the lid bosses with a drop of neutral-cure silicone. After assembly press every key with the lid closed: each must click firmly, and the ring must light.
7. **Laser.** Buy a module with a stated, measured power (Class 2 = 1 mW or less) and check its size with a caliper (6.0 x 12 mm) before the housing is ordered. The optional laser label is only true for a module that really is 1 mW or less.
8. **Cell, LED board and optic.** The cell must be a flat-top 14500 up to 14.5 x 50.4 mm without a protection board (the F15 is 14.0 x 49.0 mm; button-top and protected cells are usually longer); the nickel strip pure nickel, not nickel-plated steel; the LED board 10 mm with an SST-20 Gen 2; the optic the LISA3-RS-PIN (6.9 mm high), not the clip version. Measure the delivered parts before the housing order.
9. **File names at JLCCNC.** The drawings in `order_files/2_JLCCNC/` are `cad/FlashKa_tray_drawing.pdf` (2 sheets), `cad/FlashKa_lid_drawing.pdf`, `cad/FlashKa_pmma_kit_drawing.pdf` and `cad/FlashKa_pom_kit_drawing.pdf`, renamed to `FlashKa_tray.pdf`, `FlashKa_lid.pdf`, `FlashKa_pmma_kit.pdf` and `FlashKa_pom_kit.pdf`; the mould drawing is `FlashKa_key_mould.pdf` in `order_files/3_rubber_keys/`. JLCCNC pairs each drawing with its STEP file by the file name, so upload each under its own name together with its `.step` file.
10. **Dates.** The fee page revision was "Sep 09, 2026"; if JLC updates it, change the blue fee cells (each has its URL and date). Check the ECB rate and your bank's fee on the day you pay.

## 7. Regenerating and checking the workbook

```
python3 tools/parts_list.py                 # writes FlashKa_Parts_List_v0.7.xlsx, recalculates it, runs the checks
python3 tools/parts_list.py --check-only    # re-checks the existing workbook without rewriting it
python3 tools/parts_list.py --lights-b 2    # builds and checks a copy with scenario B = 2 lights (in a temporary folder)
python3 tools/parts_list.py other.xlsx      # writes somewhere else
python3 tools/parts_list.py --no-recalc     # skips recalculation and checks (no cached values: only for inspection)
```

It needs `openpyxl` and LibreOffice (`soffice`) for the recalculation; set `FLASHKA_RECALC` to the path of a `recalc.py` if it is not found automatically.
The script prints "all checks passed" when:

* the workbook has its eight sheets, no `#REF!`, `#VALUE!`, `#NAME?`, `#DIV/0!` or `#N/A` cell and no formula without a calculated value;
* every total, price and fee cell (663 cells in this version, the option savings included) equals an independent calculation in Python;
* every LCSC number of `COMPONENTS` is in the BOM sheet with the right quantity and designators (35 lines, 79 placements), and the BOM sheet equals the output of the `bom()` function of `tools/kicad/build_all.py` (only `refkey()` and `bom()` are extracted from that file and run into a temporary folder; `build_all.py` itself is never run), `production/BOM_JLCPCB.csv` and `order_files/1_JLCPCB/BOM_JLCPCB.csv`, line by line; the 79 designators are exactly the rows of `production/CPL_JLCPCB.csv` and `order_files/1_JLCPCB/CPL_JLCPCB.csv`; the solder joints per footprint equal the pads of the two routed boards (267 per panel);
* the two kits hold the parts of `machining_kits` in `cad/housing_interface.json` (three main keys; two RF inserts and the antenna spacer), the kits and both aluminium mould plates are above JLCCNC's 30 x 20 x 8 mm minimum, and the kit quantities are ROUNDUP((lights + 1) / 3) and one per light;
* the JSON volumes agree with the STL volumes (1 %; the resin mould plates of `cad/key_mould_checks.json` with their STL files too); the pad sizes (8.8 x 12.4 mm and 3.7 x 3.0 mm), the pad thicknesses (1.5 -> 1.15 mm and 1.0 -> 0.75 mm), the lid height (7.25 mm) and the key board (19.0 x 14.8 mm, R1.0) written in the texts are those of the geometry;
* every file of `ORDER_FILES` (30 files) is in `order_files/`, nothing else is in its 4 folders, every `order_files/` path written in the workbook names one of them, and no text names a file, a part or a shop of an older version;
* this file names the 15 input cells (`JLCPCB order!B44`, `JLCPCB order!B47`, `Housing!B95` ...) at their right addresses, and the quote cells are empty.

To change prices, edit the blue cells in the workbook, or the tables near the top of `tools/parts_list.py`, and regenerate.

## 8. Geometry source

The housing data is read from `cad/housing_interface.json` (version 0.7), written by the final v0.7 housing build (volumes and masses of the tray, lid, POM-C parts, keys and stiffener, the tray bounding box, the PCB outline, the key board, the parameters, the panel layout, the wall checks, the machining kits and the hold-down results), from `cad/key_mould_checks.json` (the resin and the aluminium mould plates) and from the STL files in `cad/` (bounding boxes). The sheet `Housing` prints the source (`cad/housing_interface.json (version 0.7) + cad/key_mould_checks.json + cad/*.stl`). If a JSON file is not found, is incomplete or is not version 0.7, the script falls back to an embedded snapshot of the same numbers and says so; a missing STL file is replaced by its snapshot entry and named in the same source line. After every housing rebuild run `python3 tools/parts_list.py` again: the volumes, the texture and groove lengths and the hold-down numbers in the workbook follow the files.
