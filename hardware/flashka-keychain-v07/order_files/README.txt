FlashKa Keychain v0.7 - the files to upload, one folder per shop.

Step by step, option by option: FlashKa_v0.7_Build_Guide.pdf (one folder up), section 3 (JLCPCB),
section 4 (JLCCNC and JLC3DP, one merged order), section 5 (the rubber for the side keys) and
section 9 (casting the keys). Section 6 lists the parts you buy ready-made.
FlashKa has not been built yet: read the guide's status note before you spend money.
No part of the light is 3D-printed and nothing is laser-marked; the only print is the casting
mould of the side keys, a tool.

1_JLCPCB  jlcpcb.com   Both circuit boards in one panel - the main PCB with the 1000 lm power
                       stage and the key board - with all small parts mounted on both sides.
                       Guide section 3.
  FlashKa_panel_gerbers.zip  the Gerber file: one panel = 1 key board + 1 main PCB + two 6 mm
                             rails, 45.0 x 32.5 mm. FR-4, 4 layers, 0.8 mm, ENIG,
                             BLACK solder mask, white silkscreen, 5 panels (the minimum).
                             Delivery format "Panel by Customer", panel format 1 x 1,
                             "Different Design" 2 (two different boards in one file: JLCPCB
                             adds a surcharge for it, shown after the upload).
  BOM_JLCPCB.csv             PCB Assembly: Standard, both sides, 2 panels (the minimum), "confirm
                             parts placement". 35 lines, 79 parts per panel (60 on the main PCB,
                             19 on the key board). R3 is 2.0 k (LCSC C4109, a Basic part): it
                             sets the 500 mA charge of the 14500 cell, which is bought
                             separately.
  CPL_JLCPCB.csv             where each part goes on the panel and how it is turned.
  Check the placement preview before you pay: pin 1 of every chip. On the main PCB's top face the
  buck U2 (3 x 3 mm QFN, no leads) has pin 1 at the corner nearest to the inductor L1 (towards the
  USB-C opening); on its bottom face the protection IC U6 sits right above the dual MOSFET Q3, both
  turned the same way (pin 1 of each on the side nearer to the battery pads). The switches SW1-SW3
  and the ring LEDs LED3 and LED4 are on the bottom side of the key board (left board), the six
  gold pogo pins P1-P6 on its top side; the main PCB's six round gold pads J6 (bottom side) get no
  part.
  Edge rails and fiducials: "by customer" (the rails carry 3 fiducials and 4 tooling holes). If
  JLCPCB's review asks for a bigger panel for Standard assembly, accept the edge rails it offers.
  Pogo pins: Harwin P70-1010045R, LCSC C22100007, 6 per light. If the JLCPCB parts library shows
  no stock when you upload the BOM, buy them into your JLCPCB parts library first (Parts Manager,
  order parts from LCSC stock), then place the order.
  Extended parts of the 1000 lm power stage - check their stock when the BOM is uploaded: buck TI
  TPS62095RGTR (LCSC C139643), cell protection IC DW01A (LCSC C351410), dual MOSFET SINO-IC SE8830A
  (LCSC C238645). The SE8830A has no drop-in substitute: a common 8205A-type dual MOSFET has about
  twice the on-resistance, and the DW01A would then cut the light off in turbo (trip at about
  2-3 A). If a part shows no stock, buy it into your JLCPCB parts library from LCSC stock (as for
  the pogo pins) or wait for stock.
  Before you order, check the SE8830A pin assignment: its LCSC data sheet shows it only as a
  package picture. Pins 1-6 must be S1, D, S2, G2, D, G1 (as on the FS8205A); the board is laid out
  for exactly this order, and a part with another pinout would disable the protection or short
  the cell.
  Optional: "inner copper weight 1 oz" instead of 0.5 oz (a small surcharge in the quote) halves
  the resistance of the 2 mm battery strip inside the board; the board is designed for 0.5 oz.
  After delivery: break both boards out of the rails at the small perforated tabs and file the
  0.3 mm nubs flush (2 on each long side of each board).
  The key board fits the housing either way round - only one way is right. Its white silkscreen
  shows how: top face (the side with the six gold pins) "<- HEAD" (the arrow points to the LED
  head) and "PINS: S2 SIDE" (the pins go to the S2 / laser side, away from the USB-C opening);
  bottom face an arrow between the switches that points to the head as well. Guide section 12.4.
  Fall-back only: production/ (one folder up) also holds each board on its own
  (FlashKa_main_gerbers.zip, FlashKa_keys_gerbers.zip with their BOM and CPL files; the key board
  is 4-layer like the panel). Two separate orders pay the set-up, stencil and board fees twice.

2_JLCCNC  jlccnc.com   Machined parts: aluminium tray and lid, clear PMMA main keys, black POM-C
                       parts. Guide section 4. One merged order with the resin mould of
                       3_rubber_keys (JLC3DP): one parcel, one shipping rate.
  Body: octagon 20 x 18 mm (facets 13.2 bottom / top, 11.2 sides, 4.81 diagonals), 99.2 mm long;
  the lid is the cap above the upper facet edges (3.4 mm tall), pocketed from below over the
  cavity, with a flat seat (flat to 0.05 mm, drawing FK-H-02).
  FlashKa_tray.step + FlashKa_tray.pdf (2 sheets)   6061-T6, bead blast + black anodise, no
                                                    marking; 1 per light
  FlashKa_lid.step + FlashKa_lid.pdf                same as the tray; 1 per light
  FlashKa_pmma_kit.step + FlashKa_pmma_kit.pdf      clear cast PMMA, polished: 3 main keys
                                                    (1 + 2 spares) on tabs in a frame;
                                                    ROUNDUP((lights + 1) / 3) kits
  FlashKa_pom_kit.step + FlashKa_pom_kit.pdf        POM-C black: lid RF window insert (+1 spare)
                                                    and antenna spacer on tabs in a frame;
                                                    1 kit per light
  JLCCNC machines plastic parts only from 30 x 20 x 8 mm up, so the small PMMA and POM-C parts are
  ordered as these two kits (52.8 x 22 x 8.5 mm and 45.4 x 39.3 x 17 mm). On arrival: cut the
  tabs, file flush, then polish the PMMA keys if the shop did not. Shops that take small parts can
  use the single files in the same folder (FlashKa_key_main.step + FlashKa_key_main.pdf,
  FlashKa_rf_window.step, FlashKa_antenna_spacer.step + FlashKa_pom_parts.pdf).
  FlashKa_laser_sleeve.step (POM-C) is only for a laser module thinner than 6 mm and is not in the
  kit.
  Each drawing has the name of its STEP file: upload the two together. The tray has 7 threads
  (4 x M1.6 for the lid, 2 x M1.6 BLIND for the key board, 1 x M1.6 from the top of the head
  block into the laser bore for the laser set screw, under the lid). Every metal wall is at least
  0.5 mm (JLCCNC's absolute minimum); below the recommended 0.8 mm are only the two front lid taps
  behind the optic bore (0.51 mm at the thread root) and the upper LED wire groove (0.751 mm):
  name them in the quote chat (drawing FK-H-01, note 7). The panels of the tray and lid carry a 0.2 mm V
  texture cut with an engraving cutter: ask for it in the quote (the parts work without it). It is
  a priced option in the workbook: to leave it out, ask the shop to skip feature 17 of drawing
  FK-H-01, because the STEP files carry it. No glass window and no spacer ring: the LEDiL
  LISA3-RS-PIN TIR optic (bought; pins cut off, glued into the head bore with two-part epoxy, no
  cyanoacrylate) stands on the LED board. Bought parts too: the two hold-down pads, the stainless
  steel screws (lid: 4 x M1.6 x 6 countersunk), polyimide tape for the two cell rails and 0.5 mm
  closed-cell foam sheet for the cell's strip under the lid and its tail pad. The aluminium casting mould of the side keys (files in 3_rubber_keys) is a
  JLCCNC part, but only for builders who choose it over the resin mould: once per builder, not per
  light.
  Details: 2_JLCCNC/README.txt

3_rubber_keys  cast at home: urethane rubber (or Sugru) in a resin mould (JLC3DP) or an aluminium
               mould (JLCCNC). The two side keys. Guide sections 4, 5 and 9.
  FlashKa_key_side.step               cast rubber body, one piece, 0.47 mm recess for the
                                      stiffener in the inner face
  FlashKa_key_stiffener.step          stiffener: plate 3.6 x 9.4 + doubler 2.0 x 2.0, 0.3 mm
                                      stainless steel shim
  FlashKa_key_side_with_plate.step    rubber body + stiffener as glued
  FlashKa_key_side.pdf                drawing FK-H-04: Shore A 80 black, stiffener outline, gluing
  FlashKa_key_mould_resin_cavity.stl  resin mould part for JLC3DP (SLA): cavity half,
                                      48 x 28 x 6.0, ribbed back - the default mould
  FlashKa_key_mould_resin_lid.stl     resin mould part for JLC3DP (SLA): lid, 48 x 28 x 5.0,
                                      ribbed back
  FlashKa_key_mould_resin.step        the resin mould closed with its 4 M3 x 16 bolts (reference)
  FlashKa_key_mould.step              aluminium mould, closed: cavity half, lid, 2 dowel pins,
                                      4 M3 screws (reference)
  FlashKa_key_mould_cavity.step       aluminium mould part for JLCCNC, 6061-T6, cavity half bead
                                      blasted
  FlashKa_key_mould_lid.step          aluminium mould part for JLCCNC, 6061-T6, as machined
  FlashKa_key_mould.pdf               drawing FK-H-08: both moulds (tolerances, cutters, assembly)
  The mould is a tool, not a part of the light: one per builder. Default: the resin print (JLC3DP,
  the cheap choice, in the merged order with JLCCNC; printed pins, 4 M3 x 16 through bolts with
  washers and nuts; print with the parting face up). Durable option: the aluminium mould (JLCCNC).
  Both have the same four cavities: one pour casts 4 keys (2 + 2 spares); 2 per light (next and
  previous are the same part, turned 180 degrees).
  Rubber: Smooth-On ECON 80 (Shore 80A, 1A:1B by volume, no scale needed) with black pigment - the
  default of the parts list; Sugru (Shore 70A, pressed in by hand) is cheaper but softer; PMC-780
  DRY also works. A mould release goes on before every cast (urethane: a urethane mould release;
  Sugru: petroleum jelly). The stiffener is cut from 0.3 mm stainless steel shim with tin snips
  (or laser cut) and glued in with cyanoacrylate (Sugru keys: with fresh Sugru). The chevron points
  along the body: held like a presenter the key nearest the head reads "^" (next) and the key
  nearest the hand "v" (previous).
  Details and casting steps: 3_rubber_keys/README.txt

optional_laser_label   NOT part of the normal build.
  FlashKa_laser_label_lid_class2.dxf / .png   laser warning label for the lid, only for a light
  that is sold or given to others (EN 60825-1). The v0.7 light itself carries no marking; the label
  is printed in the build guide (section 1, "Laser safety") and goes on the packaging. It fits the
  lid panel over the main board (X 13.49 to 32.25, Y +/-4.9; text about 0.87 mm high). Details:
  optional_laser_label/README.txt

Not in these folders: the 14500 cell (Vapcell INR14500 F15 from an EU battery shop) with 0.2 mm
nickel strip for its tabs (welded on with a small spot welder, unless the cell comes with welded
tabs: never solder onto the cell), the LED board, the TIR optic (a pack of 5 from an electronics
distributor), the laser module, the screws, the set screw, the split ring, the silicone
pads, the 24 AWG wire, thermal paste, tapes, foam, two-part epoxy and other adhesives, the resin
mould's M3 bolts with washers and nuts, and the casting supplies (urethane rubber, pigment, mould
release, stainless shim, cyanoacrylate). Guide sections 5 and 6; workbook
FlashKa_Parts_List_v0.7.xlsx, sheet "Bought parts".
