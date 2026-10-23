FlashKa Keychain v0.7 - JLCCNC order (machined parts). Each drawing names its STEP file: upload them together.

Part              Files                                    Material / finish                                  Qty
FlashKa_tray      FlashKa_tray.step + FlashKa_tray.pdf     aluminium 6061-T6, fine glass-bead blast, black    1 per light
                  (2 sheets)                               anodise type II matte (8-12 um), NO marking
FlashKa_lid       FlashKa_lid.step + FlashKa_lid.pdf       same as the tray                                   1 per light
PMMA kit          FlashKa_pmma_kit.step                    clear cast PMMA (acrylic, not extruded):           ROUNDUP((lights + 1) / 3)
                  + FlashKa_pmma_kit.pdf                   3 main keys (1 + 2 spares) on tabs in a frame      kits (1 kit for 1-2 lights)
POM-C kit         FlashKa_pom_kit.step                     POM-C (acetal copolymer), black: lid RF window     1 kit per light
                  + FlashKa_pom_kit.pdf                    insert (+1 spare) and antenna spacer, on tabs in
                                                           a frame

Kit for JLCCNC, single files for other shops
- JLCCNC machines plastic parts only from 30 x 20 x 8 mm up (rotary parts: longer than 20 mm and more than 6 mm in
  diameter), see https://jlccnc.com/help/article/what-are-the-maximum-and-minimum-processing-sizes-for-cnc .
  The PMMA main key and every POM-C part are smaller, so the instant quote refuses them one by one. Upload the
  two kits instead: each is one solid piece, the PMMA kit 52.8 x 22 x 8.5 mm, the POM-C kit 45.4 x 39.3 x 17 mm.
  The parts hang in a frame on small tabs (0.6 mm wide) that sit on faces which are hidden in the light and
  locate nothing; a 3-axis mill reaches every face in two setups, from the top and from the bottom.
- When the kits arrive: cut the tabs (flush cutter or a fine saw), file flush, throw the frame away. Then polish
  the PMMA keys as drawing FK-H-03 says (the frosted ring stays matte).
- No POM-C spacer ring and no glass window (v0.6 had both): the LEDiL TIR optic stands on the LED board in the
  head bore (see "Bought" below).
- Shops that take small parts can make them from the single files instead (same geometry):
    FlashKa_key_main.step + FlashKa_key_main.pdf          PMMA main key               1 per light (+1 spare)
    FlashKa_rf_window.step, FlashKa_antenna_spacer.step
    + FlashKa_pom_parts.pdf                               POM-C parts                 1 each per light
- FlashKa_laser_sleeve.step (POM-C, drawing in FlashKa_pom_parts.pdf) is not in the kit: it is only needed for a
  laser module thinner than 6 mm, and the slit along its axis needs a side setup. Order it as a single part
  where it is needed.

Before you order
- Body: an octagon 20 x 18 mm (bottom and top facets 13.2, side facets 11.2, four 45 deg facets 4.81 wide),
  99.2 mm long. The lid is the cap above the upper facet edges (3.4 mm tall: top facet and the two upper diagonal
  facets), pocketed from below over the cavity; its flat seat (2.12 mm wide on each side) closes on the tray
  walls and must stay flat (drawing FK-H-02, item 6).
- Tray and lid: the recessed panels carry a 90 deg V texture (0.2 mm deep, pitch 0.9 mm) and the transverse V
  grooves (0.3 mm deep), cut with one 90 deg V engraving cutter before blasting and anodising (drawing FK-H-01
  sheet 2, note 1). Ask for this in the quote; if the shop will not cut it, the parts still fit and work, only
  the surface stays plain. The POM-C kit carries the same texture on the lid insert and on the floor plug of
  the antenna spacer.
- Threads, all tapped before anodising: 4x M1.6 in the tray for the lid screws (the front pair at X 10.14, in the
  middle of the 2.62 mm of solid behind the optic bore floor: 0.51 mm of metal to the bore floor and to the head
  back face at the thread root), 2x M1.6 BLIND in the key-board bosses (they must not break through the floor),
  1x M1.6 from the top of the head block into the laser bore for the laser set screw (it sits under the lid;
  there is no hole in the bottom face).
- Walls: every metal wall of the tray and the lid is at least 0.5 mm (JLCCNC's absolute minimum). Below the
  recommended 0.8 mm: the two front lid taps (0.51 at the thread root, 0.685 at the tap drill) and the upper LED
  wire groove under the lid seat (0.751) - drawing FK-H-01 note 7. Name them in the quote chat. On the lid's top
  face a land of 0.3 mm stays between each rear countersink and the chamfer of the lanyard slot (FK-H-02 note 5).
- The optic bore (d10.1 +0.05/0, flat floor at X 8.83) centres both the TIR optic and the LED board; its floor is
  the LED board's heat path: flat 0.03, no burr, no anodise step (FK-H-01 notes 4 and 6).
- No marking of any kind. The optional laser label (only for a light that is sold or given to others) is in
  ../optional_laser_label/.
- The rubber side keys are cast at home in a mould (one per builder, not per light). The default is a resin
  print from JLC3DP (../3_rubber_keys: FlashKa_key_mould_resin_cavity.stl, FlashKa_key_mould_resin_lid.stl); the
  aluminium mould is the durable option and a JLCCNC part (FlashKa_key_mould_cavity.step,
  FlashKa_key_mould_lid.step, FlashKa_key_mould.pdf): add it to this order only if you choose it.
- Prices are not listed here: quote at the time of the order.

Bought, not part of this order (build guide, parts list)
- Hold-down pads, cut to the lid bosses and stuck on with a drop of silicone adhesive:
    can boss   (8.8 x 12.4): 1.5 mm silicone gap pad (thermal pad), Shore 00 70-80; compressed to 1.15 mm
    front boss (3.7 x 3.0):  1.0 mm silicone rubber sheet, Shore A 70; compressed to 0.75 mm
- TIR optic LEDiL LISA3-RS-PIN (FP16558) on the 10 mm copper LED board: cut the two pins off flush, put the
  board (thermal paste under it) and then the optic into the head bore, put two-part epoxy (or neutral-cure
  silicone) on the holder rim and hold the optic pressed onto the board while it cures. No cyanoacrylate: its
  vapour fogs the PMMA lens. If the LED board does not drop into the bore, sand its edge.
- Screws, stainless steel: 4x M1.6 x 6 countersunk (ISO 7046 / DIN 965) for the lid,
  2x M1.6 x 2.5 pan head (ISO 7045 / DIN 7985) for the key board, 1x M1.6 x 5 set screw (ISO 4026 flat point
  or ISO 4029 cup point, hex socket 0.7 mm) for the laser - screwed in from the top of the head block with the
  lid off.
- Cell bay (one 14500 cell, Vapcell F15): polyimide tape 0.05 mm on the two floor rails; closed-cell foam sheet
  0.5 mm, stacked to a strip 6 mm wide under the lid and a pad at the tail end (each about 1.6 x the gap it
  fills; for the F15: 1.5 mm strip, 3.0 mm pad). Nickel strips spot-welded to both cell ends, never solder on
  the can.
