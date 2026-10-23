FlashKa Keychain v0.7 - rubber side keys (next and previous key are the same part, turned 180 degrees).
They are cast at home in a small mould (4 keys per pour) and get a stainless steel stiffener glued in. The mould
is a tool, not a part of the light: one per builder. The cheap default is a resin print (JLC3DP); the aluminium
mould (JLCCNC) is the durable option. Both have the same cavities, so the keys come out the same.

Files
  FlashKa_key_side.step               cast rubber body, one piece, 0.47 mm recess in the inner face (housing frame)
  FlashKa_key_stiffener.step          stiffener: plate 3.6 x 9.4 x 0.3 + doubler 2.0 x 2.0 x 0.3, stainless steel
                                      shim, in the glued position
  FlashKa_key_side_with_plate.step    the three solids together as glued (rubber body, plate, doubler)
  FlashKa_key_side.pdf                drawing FK-H-04 (rubber, stiffener outline and tolerances, gluing)
  FlashKa_key_mould_resin_cavity.stl  resin mould part 1 for JLC3DP (cavity half) - the default mould
  FlashKa_key_mould_resin_lid.stl     resin mould part 2 for JLC3DP (lid)
  FlashKa_key_mould_resin.step        the resin mould closed with its four M3 bolts (reference)
  FlashKa_key_mould.step              the aluminium mould closed: cavity half, lid, 2 dowel pins, 4 M3 screws
  FlashKa_key_mould_cavity.step       aluminium mould part 1 for JLCCNC (cavity half)
  FlashKa_key_mould_lid.step          aluminium mould part 2 for JLCCNC (lid)
  FlashKa_key_mould.pdf               drawing FK-H-08 (both moulds: material, finish, tolerances, assembly)

Quantity: 2 keys per light. One pour gives 4 (2 + 2 spares): the keys are small and easy to lose.

Chevron: raised 0.2 mm, stroke 0.6 mm, a 90 degree chevron 1.8 mm along the light and 3.0 mm across it, whose
apex points along the body. Fitted as the next key (X 18.65, the key nearest the head) the apex points to the
head; turned 180 degrees the same part is the previous key (X 32.65, nearest the hand) with the apex to the tail.
Held like a presenter (head towards the screen, keys up under the thumb) the keys read "^" (next) and "v"
(previous). With the polished chevron grooves of 1. the chevron top comes out glossy on the matte key face, so
it reads by its gloss and by touch. No paint, no marking. The STEP file holds the key in the next-key position.


1. The mould (order once)

Resin mould (default): JLC3DP, SLA resin, upload FlashKa_key_mould_resin_cavity.stl and
FlashKa_key_mould_resin_lid.stl as two parts. Plates 48 x 28 mm, the cavity half 6.0 mm and the lid 5.0 mm
thick, each with a ribbed back (model volumes 6.24 and 4.82 cm3). Two printed pins (d4.0) on the cavity half go
into two sockets (d4.2) in the lid; they are offset, so the lid fits one way only. Four M3 x 16 socket head
screws with washers and nuts go through both plates: the resin carries no threads. Print with the parting face
up, so that the supports touch only the ribbed back. A resin print does not hold the +/-0.02 mm of the aluminium
mould: try the first cast key in its opening in the tray (drawing FK-H-04: outline -0.05/-0.15).
Bought parts: 4 socket head screws ISO 4762 M3 x 16, 8 washers M3, 4 nuts M3, stainless steel.

Aluminium mould (durable): JLCCNC, CNC milling, aluminium 6061-T6: upload FlashKa_key_mould_cavity.step and
FlashKa_key_mould_lid.step as two parts (48 x 28 x 8 mm plates, the lid 8.47 mm high with its plateaus - above
the 30 x 20 x 8 mm minimum of the instant quote) and attach FlashKa_key_mould.pdf. Finish: cavity half fine
glass-bead blast (gives the matte key face), lid as machined, no anodising. Threads: 4 x M3 in the cavity half
(drawing). Tolerances: cavity outlines and depths +/-0.02, both parting faces flat within 0.02 (drawing); the
chevron groove needs a 0.6 mm end mill (R0.3, the smallest radius in the mould).
Bought parts: 2 dowel pins ISO 8734 2 mm m6 x 8 mm, 4 socket head screws ISO 4762 M3 x 12, stainless steel.
Press the dowel pins into the two reamed holes of the cavity half (vice with soft jaws) so that they stand
3.0 mm above the parting face. They are offset: the lid fits one way only.

Once, on arrival (either mould): polish the floor of each chevron groove. Sharpen a toothpick to a chisel tip
narrower than the 0.6 mm groove, dip it in metal polish and rub it along the groove until the floor shines;
wipe the cavity clean with isopropyl alcohol. The chevron tops then come out glossy; without this step the
chevron is matte and still reads by touch. The resin mould's key faces take the surface of the print: for the
matte face of the pictures, rub each cavity floor (around the groove) with 400-grit paper on a flat stick.

How it works: the cavity half holds the four keys face down (the chevron is a groove in the cavity floor), the
parting plane is the key's inner face. The lid closes the cavities; its four plateaus form the plate recesses.
Each cavity has a runner and a gate on its near flange end with a pour hole through the lid, a vent groove at
the far flange end and a vent hole through the plateau. Every stub lands on the flange end or on the hidden
inner face, never on the key face. A pry slot at each short end opens the mould.


2. Rubber, mould release and tools

Either material works in both moulds (the parts list names the default). Numbers are the makers' data; read the
technical bulletin and the safety data sheet before the first use.
- Pourable urethane rubber, 1:1 by volume: Smooth-On ECON 80 - Shore 80A, mix 1A:1B by volume, pot life about
  13 minutes, handling after 6 hours, cured overnight (24 hours); translucent, coloured with Smooth-On SO-Strong
  black. Smooth-On PMC-780 DRY works as well (Shore 80A, 2A:1B by weight, pot life 25 min, 48 h at 23 C,
  shrinkage < 0.001 in./in. - the mould has no shrink allowance).
- Sugru (FORMEROL F.10), pressed in by hand: Shore 70A (softer than the 75-85 of the drawing), working time up
  to 30 minutes, cures with the moisture of the air - about 24 hours for the first 3 mm in open air; a closed
  mould slows it down.
- Mould release before every cast, on every face that touches the rubber: urethane - a mould release made for
  urethane rubber, sprayed and let dry per its label; Sugru - a thin film of petroleum jelly (Vaseline), as the
  maker recommends. Without it the rubber sticks to the resin and to aluminium.
- Small mixing cups, two 5 ml syringes (urethane, one per part), wooden sticks, a toothpick, nitrile gloves, eye
  protection, a ventilated room. Optional for urethane: a vacuum chamber and pump for degassing.


3. Casting steps (4 keys per pour)

Urethane (ECON 80; the same steps with PMC-780 DRY at its own ratio and times):
1. Clean both mould halves (no old rubber in the pour and vent holes). Put the mould release on every face that
   touches rubber - the cavities, the runners, the parting faces, the lid's plateaus and holes - and let it dry.
2. The four keys need about 0.22 cm3 of rubber (4 x 54.3 mm3, model), far too little to measure: draw 5 ml of
   each part into its own syringe, empty both into a cup and add the black pigment at the maker's dose.
3. Mix for the time the bulletin gives, scraping the sides and the bottom of the cup several times. Pour within
   the pot life (ECON 80: about 13 minutes).
4. Optional: degas the mixed rubber in its cup in the vacuum chamber, per the bulletin (the cup must hold several
   times the rubber's volume: it rises before it settles).
5. Stand the cavity half level, parting face up. With the toothpick work a little rubber into the chevron
   groove of each cavity so that no air stays in it. Then pour slowly, in a thin stream, into one corner of each
   cavity and let the rubber run across the floor; stop when it is level with the parting face.
6. Lower the lid over the pins (resin mould) or the dowel pins (aluminium mould) slowly. The plateaus push the
   surplus out through the pour holes and the vent holes. Fit the four M3 screws (resin mould: with washers and
   nuts) and tighten them evenly - in the resin mould only firmly, not hard. Rubber should now show in every
   pour hole and vent hole; top up a pour hole that stays empty with the toothpick.
7. Leave the mould level and undisturbed until the rubber has cured (ECON 80: overnight, 24 h; PMC-780 DRY: 48 h
   at 23 C). A colder room takes longer.
8. Demould: take the screws out, put a flat screwdriver in a pry slot and twist gently until the lid lifts.
   Pull each key out by its flange. A post-cure in an oven, if the bulletin gives one, is for the keys alone -
   not in the resin mould.
9. Trim with a sharp scalpel or flush cutters: the gate stub at the flange end and the vent stub at the far end
   flush with the flange, the vent stub on the recess floor flush with the floor. Check each key face: no bubble,
   chevron complete. A key that fails goes back to the spares bin; pour again.
10. Clean the mould straight away: push the cured stubs out of the pour and vent holes with a pin.

Sugru (pressed):
1. Clean both halves and wipe a thin film of petroleum jelly on every face that touches the rubber.
2. Knead one black sachet. With the toothpick press a little into the chevron groove of each cavity, then fill
   each cavity a little proud of the parting face.
3. Lower the lid over the pins and fit the four screws, tightened evenly: the surplus leaves through the pour
   and vent holes.
4. Leave it closed for at least 48 hours, then open it as in step 8 above, trim (step 9) and clean the mould.


4. Stiffener (plate + doubler) and gluing

Cut from 0.3 mm stainless steel shim (1.4301 / 304):
- plate: 3.6 x 9.4 mm, the four corners clipped 0.8 x 45 degrees; outline +0 / -0.2 mm (it must fit the
  3.8 x 9.6 mm recess; the clipped corners clear the recess's R1.0 corners);
- doubler: 2.0 x 2.0 mm, +/-0.2 mm.
By hand: mark the outline with a fine marker and a steel rule, cut just outside the line with tin snips, file
or sand to the line, deburr both faces and press the pieces flat (the snips curl thin shim) - in a vice between
two smooth blocks. Shop option: laser cutting by any sheet-metal service from FlashKa_key_stiffener.step and
the drawing.

Gluing (cyanoacrylate; a rubber-toughened grade is best):
1. Wipe the recess and both shim pieces with isopropyl alcohol (it removes the mould release), roughen the glue
   faces lightly with fine abrasive paper, wipe again.
2. Glue the doubler on the centre of the plate and press it flat.
3. Glue the plate into the recess with a thin film, doubler up (towards the switch), and hold it flat until the
   glue has set. Wipe any glue off the flange: it must sit flat on the floor of the tray.
Check: the plate lies 0.15 mm below the flange top and the doubler stands 0.15 mm above it (model); the
doubler is what presses the switch.
Sugru keys: cyanoacrylate does not hold on cured Sugru (a silicone rubber). Bed the plate (with the doubler
already glued on) in a thin film of fresh Sugru in the recess instead; Sugru bonds to steel as it cures. Wipe the
surplus off the flange and let it cure for a day before the key goes in.

Why the plate: pressed 2 mm from its end, a rubber-only key bends by more than the whole switch travel (3.9 mm
of key travel to the click, simulated) and feels soft; with the plate the key rocks as one stiff part: 0.73 mm
of travel and 1.035 N at the click (model numbers, docs/housing_v07_notes.md).


Other ways to make the keys: a vacuum-casting service (PU rubber in a silicone mould) works from
FlashKa_key_side.step and the drawing, but for two small keys the mould cost alone outweighs the parts. For a
series a rubber moulder can compression-mould the same key in black PU or silicone rubber, Shore A 75-85
(silicone needs a primer before the plate is glued: cyanoacrylate does not hold on untreated silicone). General
tolerances ISO 3302-1 class M2; home-cast keys +/-0.10 mm where the drawing gives no tolerance.

Prices are not listed here: quote at the time of the order.
