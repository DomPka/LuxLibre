FlashKa Keychain v0.6 - the files to upload, one folder per shop.

Step by step, option by option: FlashKa_v0.6_Build_Guide.pdf (one folder up), section 3 (JLCPCB),
section 4 (JLCCNC), section 5 (JLC3DP). Section 6 lists the parts you buy ready-made.
FlashKa has not been built yet: read the guide's status note before you spend money.

1_JLCPCB  jlcpcb.com   Circuit board with all small parts mounted, on both sides. Guide section 3.
  FlashKa_main_gerbers.zip   the Gerber file. FR-4, 4 layers, 0.8 mm, ENIG, 5 boards (the minimum).
  BOM_JLCPCB.csv             PCB Assembly: Standard, both sides, 2 boards (the minimum), "confirm
                             parts placement". 34 lines, 68 parts per board.
  CPL_JLCPCB.csv             where each part goes and how it is turned.
  Check the placement preview before you pay (pin 1 of every chip; the switches SW1-SW3 and the
  ring LEDs LED3 and LED4 are on the bottom side).

2_JLCCNC  jlccnc.com   Aluminium tray and lid, three stainless caps. Guide section 4.
  FlashKa_tray.step + FlashKa_tray.pdf (2 sheets)   6061-T6, bead blast + black anodise, 1 per light
  FlashKa_lid.step + FlashKa_lid.pdf                same as the tray, 1 per light
  FlashKa_cap_main.step + .pdf                      SUS304, turned, bead blast; 1 per light + 1 spare
  FlashKa_cap_slide.step + .pdf                     SUS304, turned, bead blast; 2 per light + 1 spare
  Each drawing has the name of its STEP file: upload the two together.
  Laser marking after anodising, one DXF file per face (it carries the laser label and the SAFE / ARM
  marks; if JLCCNC does not offer it, use an adhesive label, guide section 4):
  FlashKa_marking_lid_class2.dxf   lid
  FlashKa_marking_bottom.dxf       bottom face of the tray
  FlashKa_marking_minus_y.dxf      USB-C side
  FlashKa_marking_plus_y.dxf       laser side (SAFE and ARM)
  FlashKa_marking_lid_class3R.dxf  do not order. It is only a correct label for a laser module that
                                   measures more than 1 mW, and LuxLibre design rule LAS-1 allows
                                   Class 1 and Class 2 lasers only: use a Class 2 module (1 mW or less).
  The caps are very small (head 3.4 and 5.8 mm). If the instant quote refuses them by size, send the
  same STEP + PDF files to another CNC shop, or use the resin caps from the print kit.
  The two silicone hold-down pads are not part of the order (guide section 6).
  Details: 2_JLCCNC/README.txt

3_JLC3DP  jlc3dp.com   The resin parts. Guide section 5.
  FlashKa_print_kit.stl      SLA resin 8001 (translucent), one kit per light + 1 spare. One file, one
                             part: seven resin parts on thin rods (light tube, three caps, radio window
                             insert, spacer ring, antenna spacer). Cut them off at home.
  FlashKa_laser_sleeve.stl   only if the laser module is 4.5 mm instead of 6 mm.
  Details: 3_JLC3DP/README.txt

Not in these folders: the cells, LED board, laser module, glass, screws, silicone pads, wire, tapes and
adhesives. Guide section 6; workbook FlashKa_Parts_List_v0.6.xlsx, sheet "Bought parts".
