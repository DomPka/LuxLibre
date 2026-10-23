FlashKa Keychain v0.7 - OPTIONAL laser warning label for the lid. Not part of the normal build.

The v0.7 light carries no marking: the laser label (EN 60825-1, Class 2) is printed in the manual and on the
packaging. That is fine for lights you build for yourself. A light that is sold or given to other people needs
the label on the light itself: only then use these files.

Files
  FlashKa_laser_label_lid_class2.dxf   artwork, scale 1:1, lid seen from above with the head (front, X = 0) on
                                       the left, housing coordinates in mm. Layer MARK = laser marking (filled
                                       letters and warning sign); layer REF = lid outline, panels, RF window,
                                       screw holes and lanyard slot, for positioning only (do not mark).
  FlashKa_laser_label_lid_class2.png   preview of the same

Position: in the lid panel over the main board, X 13.49 to 32.25, Y -4.9 to +4.9 (housing coordinates; the
label fills X 13.49 to 29.32).

How: fibre-laser marking on the finished black anodised lid (light grey mark). The panel carries the 0.2 mm V
texture and the marks run over it: try one lid first and check that the text reads. Text height about 0.87 mm,
warning sign 5.1 mm (the top facet of the octagon body is 13.2 mm wide: the script scales the label to 0.84 so
that it fits the panel).

Laser data on the label: the light's 520 nm module, Class 2, P <= 1 mW (printed with the "≤" sign). LuxLibre
design rule LAS-1 allows Class 1 and Class 2 lasers only, so there is no label for a stronger class.

Make it again: python3 tools/housing/laser_label.py (run it in hardware/flashka-keychain-v07/; it writes into this folder).
