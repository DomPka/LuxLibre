#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
FlashKa Keychain v0.7 - parametric aluminium housing, keys and inserts

One source of truth for the mechanics: every dimension lives in the parameter class P below.
The script builds

  tray            main body, 6061-T6: head block (TIR optic + LED board, laser), PCB zone, antenna zone,
                  cell bay (two floor rails) and the tail with the lanyard slot; on the floor the key bezel with the
                  three key openings, two blind tapped M1.6 bosses and four support ribs for the key board (KB), the
                  floor RF window
  lid             the top of the octagon (top facet + the two upper diagonal facets), 6061-T6, 4x M1.6 countersunk
                  screws, RF window opening + pocket, the hold-down bosses on the module can and at the front
  key_main        main key: clear cast PMMA, polished, frosted ring icon; light guide of the RGB ring
  key_side        next / previous key: black urethane rubber, Shore A 80 (75-85), cast at home in an aluminium
                  mould (key_mould.py; SLA resin version for JLC3DP as the cheap default), raised chevron
                  along the body (apex towards the head (-X) on the next key, towards the tail on the previous
                  key - the same part turned 180 deg); stainless steel stiffener plate + doubler glued into the
                  recess of the inner face (key_stiffener)
  rf_window       lid RF window insert, POM-C black, flush, textured like a panel
  antenna_spacer  POM-C black: keeps the cell off the antenna, plugs the floor RF window (textured
                  like a panel), rebate for the cell wires
  laser_sleeve    POM-C black, optional (4.5 mm laser module)
  pmma_kit,       machining kits for JLCCNC (plastic parts below 30 x 20 x 8 mm are refused): the PMMA keys /
  pom_kit         the POM parts hang on small tabs in a frame (build_pmma_kit, build_pom_kit)

v0.7 against v0.6: the three keys sit on the centre line of the bottom face (next X 18.65, main X 25.65,
previous X 32.65) and press the switches of a separate key board that is screwed to two bosses
on the floor; six pogo pins on the key board reach the unchanged main board.  For 1000 lm the head carries an
LEDiL LISA3-RS-PIN TIR optic that stands on the LED board (v0.6: glass window and POM spacer ring); the bay takes
one 14500 cell (Vapcell INR14500 F15, or any flat-top 14500 up to 14.5 x 50.4); the body is 99.2 mm long.  The main
key is clear PMMA and the light guide of the RGB ring; the side keys are cast rubber with a raised chevron.  The
section is a faceted octagon, 20 x 18 mm: flat bottom (key face) and top (lid), flat sides, four 45 deg facets;
recessed panels with a diagonal V-groove texture on the flat facets, transverse V-grooves near the head and the
tail.  No markings.  No printed parts: the light-pipe tube, the three
stainless caps, the print kit and the laser marking are gone; the small parts are POM-C, PMMA and
elastomer.

Coordinate system (all mm):
  X = 0 at the front face (light exits towards -X), +X towards the tail
  Y = 0 on the centre line, -Y = control side (USB-C), +Y = laser side (laser interlock S2)
  Z = 0 on the bottom face, +Z towards the lid
  The KiCad boards keep the frame of the first v0.7 layout, a 94.4 mm body ("PCB frame"): housing X = PCB X + PCB_DX (2.75), see
  P.pcb_dx.  housing_interface.json gives pcb_outline and components in the PCB frame (the KiCad tools read them).

Run (from this folder):
  python3 flashka_housing.py ../../cad                    full build + all checks
  python3 flashka_housing.py ../../cad --no-checks        solids + interface file only
  python3 flashka_housing.py ../../cad --interface-only   housing_interface.json only (no solids)
  A build into the package's cad folder also refreshes the STEP copies in ../../order_files (order_files.py).
  option --kb-interface FILE (or the environment variable FK_KB_INTERFACE): read the key-board numbers
  (outline, holes, Z, pogo pins) from a JSON file in the format of the v0.7 interface instead of the
  defaults in P.
"""
import json
import math
import os
import sys
from dataclasses import dataclass, asdict, field

import cadquery as cq

VERSION = "0.7"
# the TIR optic makes the head 2.95 longer than in the first v0.7 layout (94.4 mm body); the main board, the key board,
# the keys, the lid bosses and every opening that belongs to them sit PCB_DX further back than in that layout (the
# board's front gap is 0.1 instead of 0.3), whose coordinates the KiCad boards keep (the "PCB frame")
X_PCB0_V07 = 8.8              # front edge of the main board in the v0.7 body (= the KiCad / PCB frame)
PCB_DX = 2.75                 # = P.L_head + P.pcb_gap_front - X_PCB0_V07, checked in P.__post_init__


def _dx(x):
    """an X position of the PCB frame moved to the housing frame"""
    return round(x + PCB_DX, 4)


# --------------------------------------------------------------------------
# parameters
# --------------------------------------------------------------------------
@dataclass
class P:
    # envelope
    W: float = 20.0          # width (Y)
    H: float = 18.0          # height (Z)
    C_edge: float = 3.4      # legs of the four 45 deg facets: an octagon of 8 flat facets (bottom = key face, top = lid)
    C_front: float = 0.4     # chamfer on the front face outline (optic bore 1.125 from the -Y face)
    C_end: float = 0.6       # chamfer on the tail face outline
    wall: float = 1.5        # side wall thickness
    floor: float = 1.5       # floor thickness
    lid_t: float = 1.5       # lid: top plate and diagonal facets over the cavity (the lid is the part above Z_lid)
    inner_r: float = 2.0     # vertical internal corner radius (JLCCNC: R >= H/10+0.5)
    front_relief: tuple = (2.0, 0.9, 0.6)   # cavity front corners above the ledges: d, centre X behind L_head, centre Y
    #                                         inside inner_half; clears the board's chamfered corner (pushed to a side
    #                                         wall) and the USB-C receptacle while the board is tilted in

    # head block (solid, carries the TIR optic with the LED board and the laser; the lid covers its rear part)
    L_head: float = 11.45    # v0.7: 8.5; the front lid taps sit in the solid behind the optic bore floor, with at
    #                          least 0.5 mm of metal round the thread (JLCCNC's absolute minimum wall)
    Z_axis: float = 8.0      # LED / optic axis height (= mid height)
    lid_x0: float = 4.2      # front edge of the lid (it lies in the rear flank of the third head groove)

    # main LED: Luminus SST-20 Gen 2 on a ready-made 10 mm copper DTP board under an LEDiL LISA3-RS-PIN (FP16558)
    # TIR optic: d10.0, PMMA lens in a black PC holder that stands on the LED board (LED level = holder seat);
    # the two locating pins are cut off, the bore locates the optic.  No front window.
    Y_w: float = -3.825      # optic / LED axis Y
    opt_od: float = 10.0     # LEDiL datasheet FP16558: "Dimensions d 10.0"
    opt_h: float = 6.93      # LEDiL drawing FP165xx_LISA3-x-PIN rev 1.2: 6.93 +/-0.2 above the PCB (datasheet: 6.9)
    opt_h_tol: float = 0.2
    opt_exit_d: float = 8.6  # drawing callout "8.6" in the top view (not labelled in the text): lens exit diameter
    opt_recess: float = 0.2  # optic front face behind the front face of the body (0.0 to 0.4 over opt_h_tol: never
    #                          proud of the face)
    opt_bore: float = 10.1   # one bore (+0.05/0) for the optic and the LED board: it centres both
    sst_size: float = 3.45   # SST-20 package (square), pictures and clearance
    sst_h: float = 0.7       # SST-20 package height above the board (approx., pictures and clearance)
    mcpcb_d: float = 10.0
    mcpcb_t: float = 1.6
    tim_t: float = 0.10      # thermal paste under the LED board
    head_solid_min: float = 2.0   # solid head block behind the LED board (heat path), required minimum
    wire_groove: tuple = (1.4, 1.3)   # LED wire grooves in the bore wall: width, depth into the wall (24 AWG PTFE,
    #                                   OD <= 1.05: 1.35 radial room beside the 10.0 LED board)
    led_wire_r: float = 5.7  # wire holes on the groove line, straight behind the grooves (radius from the optic axis)
    led_wire_ang: float = 30.0   # grooves + holes tilted from +Z: the upper pair towards +Y, the lower towards -Y
    ledwire_d: float = 1.5   # LED wire holes from the bore floor into the cavity (24 AWG PTFE)

    # laser module (6 x 12 mm, integrated driver)
    Y_l: float = 5.85
    Z_las: float = 5.9
    las_d: float = 6.0
    las_len: float = 12.0
    las_clear: float = 0.10
    las_recess: float = 0.3
    las_set: tuple = (5.5, 4.8)   # laser set screw M1.6 (X, Y), screwed in from the head-block top under the lid: nothing
    #                               shows on the closed light; 1.05 to the -Y side of the laser axis (v0.7 position, kept),
    #                               its hole lies 0.5 behind the lid edge
    las_set_len: float = 5.0      # M1.6 x 5 set screw: its top stays below the head-block top (Z_lid)
    las_set_point: float = 0.8    # point diameter of the set screw (flat or cup point; ISO 4026 / 4029: 0.8 max for M1.6)
    las_bore_extra: float = 0.3
    sleeve_id: float = 4.6
    sleeve_od: float = 6.0
    sleeve_len: float = 10.0
    sleeve_slit: float = 0.8

    # main PCB (4 layers, 0.8 mm), unchanged from v0.6
    pcb_len: float = 24.0
    pcb_t: float = 0.8
    Z_pcb_bot: float = 9.2
    pcb_gap_front: float = 0.1    # head block -> board front edge (v0.7: 0.3)
    pcb_side_gap: float = 0.25
    pcb_chamfer: float = 1.3
    ledge_w: float = 0.8
    las_keepout_x: float = _dx(12.9)     # PCB frame 12.9 (laser module tail, no +Y ledge in front of it)

    # ESP32-C3-MINI-1
    mod_w: float = 13.2
    mod_len: float = 16.6
    mod_onboard: float = 11.2
    mod_h: float = 2.4
    mod_y: float = -1.4
    ant_gap: float = 0.8

    # cell: ONE Vapcell INR14500 F15 (maker: 14.0 +/-0.2 x 49.0 +/-0.3 mm, about 22 g, flat top, unprotected: the main
    # board protects it).  The bay takes any flat-top 14500 up to 14.5 x 50.4 (e.g. Vapcell K10, 14.1 +/-0.2 x
    # 50.1 +/-0.3).  The cell lies on two floor rails (a cradle; polyimide tape on the rails), a soft foam strip under
    # the lid holds it down, a foam pad at the tail end takes up the length; nickel strips spot-welded to both ends,
    # the two 24 AWG joints and the wire from the far end lie in the lower -Y corner channel of the octagon
    L_batt: float = 51.6                    # = longest cell 50.4 + 2 x cell_end + cell_end_pad
    cell_d: float = 14.0
    cell_d_tol: float = 0.2
    cell_len: float = 49.0
    cell_len_tol: float = 0.3
    cell_mass_g: float = 22.0               # maker: "about 22 g"
    cell_max: tuple = (14.5, 50.4)          # the largest flat-top 14500 the bay takes
    cell_alt: tuple = (14.1, 50.1, 0.2, 0.3)    # Vapcell K10: d, length, tolerances
    cell_end: float = 0.4                   # per cell end: nickel strip 0.2 + its fold / the weld bumps
    cell_end_pad: float = 0.4               # tail-end foam pad compressed to at least this (longest cell)
    cell_tape: float = 0.05                 # polyimide tape on the two rails
    rail_y: float = 3.5                     # |Y| of the rails' inner top edges: the cell rests on these two edges
    rail_w: float = 1.2
    rail_h: float = 1.1                     # above the floor: the smallest F15 keeps 0.15 over the floor between them
    top_pad: tuple = (1.5, 6.0)             # soft closed-cell foam strip under the lid: free thickness (F15), width
    foam_step: float = 0.5                  # foam sheet thickness: pads are stacks of it
    foam_target: float = 0.375              # compression aimed at (20 to 55 % is fine for closed-cell foam)
    strip_w: float = 5.0                    # nickel strip width (0.2 thick)

    # tail
    tail_front_wall: float = 0.8      # v0.7: 1.0
    lan_slot_w: float = 3.6           # v0.7: 4.4
    lan_slot_len: float = 4.6         # between the rear lid screws (Y +/-screw_dy): 0.3 of top face left between
    tail_end_wall: float = 1.45       # v0.7: 2.0 (lanyard bridge)          the countersinks and the slot chamfer
    lan_chamfer: float = 0.25
    twin_x: float = 4.6
    twin_y: float = 10.8              # inside the bottom facet
    twin_r: float = 0.8
    twin_corner: float = 1.8
    twin_depth: float = 1.0
    twin_chamfer: float = 0.3
    twin_front_gap: float = 0.8
    tail_facet: float = 2.0

    # RF window in the lid (POM-C insert, flush with the panel level, textured)
    rfw_x0_over_pcb: float = 1.0
    rfw_x_beyond_ant: float = 0.5
    rfw_y: float = 10.8           # the lid's top facet (13.2) minus the flange pocket and its wall to the facets
    rfw_r: float = 1.5
    rfw_flange: float = 0.8
    rfw_flange_t: float = 0.6
    rfw_flange_drop: float = 0.2
    rfw_clear: float = 0.03       # insert in the opening, per side (POM, light slide fit): the plug locates the insert
    rfw_flange_clear: float = 0.10  # insert flange in the lid pocket, per side (not a locating face: it carries the kit tabs)

    # screws / threads
    m16_tap: float = 1.25
    m16_drill: float = 3.6
    m16_clear: float = 1.8
    m16_csk: float = 3.3
    screw_dy: float = 4.5         # the countersinks stay 0.45 inside the top facet (13.2 wide)
    lid_screw_len: float = 6.0    # M1.6 x 6 countersunk: the lid is 3.4 thick over the head and the tail
    screw_x_front: float = 10.14  # centred in the solid behind the optic bore floor (v0.7: 7.0, where the optic bore
    #                              now is): 0.51 of metal to the bore floor and to the head rear face at the thread crest
    m16_pitch: float = 0.35

    # control side (-Y): USB-C
    X_usb: float = _dx(14.6)
    usb_open: tuple = (12.6, 6.8, 2.0)
    usb_open_chamfer: float = 0.3
    # laser side (+Y): S2 interlock slide
    X_s2: float = _dx(14.05)
    s2_slot: tuple = (3.2, 2.0, 0.8)
    s2_knob_z: float = 0.7
    s2_knob_len: float = 1.55
    s2_knob_out: float = 0.75

    # floor RF window (plugged by the POM antenna spacer)
    frw_box: tuple = (_dx(33.6), _dx(38.7), 5.4, 1.5)    # inside the bottom facet, as wide as its panels

    # ---------------------------------------------------------------- v0.7 exterior
    pan_depth: float = 0.30       # recessed panels
    pan_r: float = 0.8            # panel corner radius (end mill)
    band: float = 1.2             # frame band between panels / openings
    rail: float = 1.2             # band along the chamfer edges
    tex_pitch: float = 0.9        # diagonal V-groove texture in the panels (90 deg V)
    tex_depth: float = 0.20       # -> groove 0.40 wide, land 0.50
    grv_depth: float = 0.30       # transverse V-grooves (90 deg): 0.60 wide
    grv_head: tuple = (1.5, 2.7, 3.9)        # apex X; the third one holds the lid joint (lid_x0)
    grv_tail_off: tuple = (5.4, 4.2, 3.0)    # tail grooves: apex X in front of the bay end (X_batt1), all round
    bay_split: int = 2            # number of panels along the bay on each face
    band_rf: float = 1.8          # band behind the RF windows (keeps the texture 1 mm from the lid pocket)
    tex_min_metal_cells: float = 0.9
    tex_min_metal: float = 1.0

    # ---------------------------------------------------------------- v0.7 keys (centre line Y 0)
    X_next: float = _dx(15.9)
    X_main: float = _dx(22.9)
    X_prev: float = _dx(29.9)
    key_y: float = 0.0
    main_key: tuple = (6.8, 6.8, 1.0)      # size X, size Y, corner r
    side_key: tuple = (4.2, 10.0, 1.5)
    main_face_z: float = 0.15     # main key outer face, below the bottom-face plane
    side_face_z: float = 0.30     # side key flat face; the chevron (raised) ends at side_face_z - chevron_h
    chevron_h: float = 0.20
    chevron: tuple = (0.60, 0.60, 1.20)    # stroke width, half length along X (apex direction), half span along Y:
    #                                        90 deg apex along the body, towards the head (-X) on the next key, towards
    #                                        the tail (+X) on the previous key
    bez_depth: float = 0.50       # key bezel (recess round the keys), 45 deg walls
    bez_margin: float = 0.30      # bezel floor beyond the keys
    bez_style: str = "stadium"    # 'stadium' (one rounded rectangle) or 'bone' (follows the keys)
    key_clear: float = 0.10       # key in its floor opening, per side
    key_clear_end: float = 0.15   # side key ends (rocking)
    flange_t: float = 0.45
    flange_main: float = 0.40     # flange beyond the key outline
    flange_side: float = 0.50
    nub_d: float = 1.6
    nub_h: float = 0.50           # nub above the pocket floor (>= stroke + 0.1, also against a 2.0 mm box model)
    pre_main: float = 0.15        # free play nub -> actuator, main key (limited by the LED gap)
    pre_side: float = 0.25        # free play, side keys
    led_gap_rest: float = 0.60    # main key top face -> ring LED faces, at rest (0.85 mm LED)
    pocket_clear: float = 0.25    # key pocket round the switch body, per side
    ring_icon: tuple = (4.4, 0.5, 0.03)    # frosted ring: mean dia, width, depth
    stiffener: tuple = (3.6, 9.4, 0.3, 0.8)  # side key plate: X, Y, t, 45 deg corner clip (stainless steel shim,
    #                                          cut by hand, glued into the recess of the key's inner face after casting)
    doubler: tuple = (2.0, 2.0, 0.3)  # square of the same shim glued on the plate centre: it presses the switch
    plate_recess: tuple = (3.8, 9.6, 1.0)   # recess for the plate in the side key's inner face: X, Y, corner r
    plate_glue: float = 0.02      # glue film under the plate (the recess is that much deeper)
    E_rubber_mpa: float = 9.4     # Shore A 80 (Gent); A75 7.0, A85 13.2
    E_steel_mpa: float = 193000.0

    # ---------------------------------------------------------------- side-key casting mould (6061, JLCCNC; home casting)
    mould_n: int = 4              # cavities: 2 keys per light + 2 spares per pour
    mould_pitch: float = 9.2      # cavity pitch along X (the keys' long side runs along Y)
    mould_size: tuple = (48.0, 28.0)      # both halves, X x Y
    mould_t: tuple = (8.0, 8.0)   # cavity half, lid thickness (JLCCNC minimum size 30 x 20 x 8 for each part)
    mould_draft: float = 1.0      # deg, on the cap and flange walls of the cavities
    mould_cap_offset: float = -0.04       # cap outline at the flange step, per side: with the draft the cast cap lies
    #                                       inside the key's outline tolerance -0.05/-0.15 at every height
    mould_runner: tuple = (1.2, 0.45, 3.0)  # gate width, depth (= flange thickness), sprue well centre to cavity end
    mould_sprue_d: float = 2.5    # pour hole through the lid, one per cavity
    mould_vent: tuple = (1.0, 0.1)          # vent groove in the parting face at the far cavity end: width, depth
    mould_vent_hole: tuple = (1.0, 2.5, 1.5, 0.8)   # plateau vent: d at the face, counterbore d, small-hole length
    #                                                 above the parting plane, distance from the plateau end
    mould_dowel: tuple = (2.0, 8.0, 5.0)    # dowel pin d x length, press depth in the cavity half
    mould_dowels: tuple = ((-20.5, 0.0), (20.5, 3.0))       # positions (asymmetric: the lid fits one way only)
    mould_screws: tuple = ((-20.5, -10.5), (-20.5, 10.5), (20.5, -10.5), (20.5, 10.5))   # M3 x 12 socket head
    mould_m3: tuple = (2.5, 7.0, 6.0, 3.4)  # tap drill d, drill depth (blind), thread depth, clearance hole d in the lid
    mould_pry: tuple = (8.0, 1.5, 2.0)      # pry slot at both short ends: width, depth below the parting plane, reach
    rubber_shrink: float = 0.001  # PMC-780 DRY linear shrinkage bound ("< .001 in./in.", data sheet): below the
    #                               cavity tolerance, so no allowance is applied
    # resin version of the mould (SLA, JLC3DP; the cheap default): the same cavities, plateaus, runners, vents and
    # pry slots; thicker plates with a ribbed back, printed alignment pins, M3 through bolts with nuts (no resin threads)
    resin_t: tuple = (6.0, 5.0)       # cavity half, lid (without its plateaus)
    resin_floor: float = 2.0          # resin under the deepest cavity point (cavity half) / face plate of the lid
    resin_rim: float = 3.0            # solid rim round the back pockets
    resin_rib: float = 2.0            # back ribs: one under each cavity column, one along the middle
    resin_boss: float = 8.0           # solid round each bolt hole on the back (washer and nut seat), d
    resin_hole_boss: float = 5.0      # solid round the pour and vent holes of the lid, d
    resin_pin: tuple = (4.0, 2.5, 0.5, 4.2)   # printed pin d, height, top chamfer; socket d in the lid (slip)
    resin_bolt: tuple = (3.4, 16.0)   # through hole d; M3 x 16 socket head screw, washers and nut

    # ---------------------------------------------------------------- machining kits (JLCCNC)
    kit_min: tuple = (30.0, 20.0, 8.0)   # JLCCNC minimum processing size for plastic parts ("special shapes")
    kit_h_pmma: float = 8.5       # PMMA kit height (frame); the key is centred in it
    kit_h_pom: float = 17.0       # POM kit height: the antenna spacer (15.85 tall) stands upright in it
    kit_gap: float = 3.0          # part outline to the frame (end mill path)
    kit_gap_tall: float = 5.0     # round the antenna spacer (cut 12.5 deep from below: 2.5 x the gap)
    kit_wall: float = 3.0         # frame: outer walls and webs between the cells
    kit_tab: tuple = (0.6, 0.6)   # tab width, height (on the main key flange: the flange thickness)

    # ---------------------------------------------------------------- key board (KB), v0.7 interface
    kb_x0: float = _dx(13.4)
    kb_x1: float = _dx(32.4)
    kb_y: float = 7.4
    kb_r: float = 1.0
    kb_t: float = 0.8
    kb_z0: float = 4.4            # KB bottom face
    kb_holes: tuple = ((_dx(22.9), 5.8), (_dx(22.9), -5.8))
    kb_hole_d: float = 1.8
    kb_keepout_d: float = 3.8
    boss_d: float = 3.4
    kb_screw_len: float = 2.5     # M1.6 x 2.5 pan head (a 4 mm screw would need a tap through the floor)
    kb_screw_head: tuple = (3.0, 1.1)
    kb_ribs: tuple = ((_dx(15.9), 1), (_dx(15.9), -1), (_dx(29.9), 1), (_dx(29.9), -1))   # (X, side)
    rib_w: float = 1.4
    rib_y0: float = 5.9           # inner end of the ribs (|Y|)
    sw_body: tuple = (3.9, 2.9)   # Alps SKRKAEE020: along its pads, across
    sw_h: float = 2.0
    sw_body_h: float = 1.6
    sw_act_d: float = 1.9
    sw_travel: float = 0.25
    sw_click: float = 0.20        # travel to the click (estimate)
    sw_force_n: float = 1.6
    led_size: float = 1.0
    ring_led_h: float = 0.85      # NH-B1010RGBT-HF, worst case
    led_y: float = 2.4
    smt_standoff: float = 0.05    # SMD parts sit this far off the board face (solder), as in the KiCad STEP exports
    pogo_free: float = 5.0
    pogo_work: float = 4.0
    pogo_min: float = 3.7
    pogo_max_work: float = 4.2
    pogo_base: tuple = (2.0, 0.4)         # Harwin P70-10X: base d x h on the KB top face
    pogo_barrel: tuple = (1.54, 3.3)      # barrel d, top above the KB top face
    pogo_plunger_d: float = 0.9
    pogo_force_n: float = 1.17    # at the working height
    pogo_force_tol_n: float = 0.29
    pogo_pins: tuple = tuple((_dx(x), 2.5) for x in (15.0, 17.8, 20.6, 25.0, 27.8, 30.6))
    pogo_part: str = "Harwin P70-1010045R (LCSC C22100007)"

    # ---------------------------------------------------------------- hold-down (lid boss + gap pad on the can)
    boss_box: tuple = (_dx(22.1), _dx(30.9), -7.6, 4.8)
    boss_r: float = 1.0
    pad_t0: float = 1.5           # thermal gap pad, free thickness
    pad_gap: float = 1.15         # compressed (23 %)
    pad_E_mpa: float = 1.0
    front_boss: bool = True       # lid boss + rubber pad (as v0.6): the pins lift the board front without it
    boss2_box: tuple = (_dx(15.65), _dx(19.35), 0.25, 3.25)   # -Y edge 0.42 from U2 (TPS62095) on the board: more than
    #                                                          the board's side play (0.236), so the boss never meets U2
    boss2_r: float = 0.5
    pad2_t0: float = 1.0
    pad2_gap: float = 0.75        # front pad compressed to this (25 %: with 20 % the pins at their maximum force lift the board 0.02 mm)
    pad2_E_mpa: float = 5.3
    pcb_E_mpa: float = 20000.0
    pcb_nu: float = 0.14
    s2_stop_gap: float = 0.225

    def __post_init__(self):
        kbi = os.environ.get("FK_KB_INTERFACE")
        if kbi:                                 # key-board numbers from an interface file (see the module docstring)
            load_kb_interface(self, kbi)
        if abs(self.pcb_dx - PCB_DX) > 1e-9:
            raise ValueError("L_head + pcb_gap_front must put the board %.3f behind its v0.7 place (got %.3f)"
                             % (PCB_DX, self.pcb_dx))

    # ---------------------------------------------------------------- derived
    @property
    def inner_half(self):
        return self.W / 2 - self.wall

    @property
    def Z_lid(self):            # lid seat = the parting plane at the edge between the side facets and the upper facets;
        return self.H - self.C_edge     # the head and tail blocks of the tray end here, the lid lies on them

    @property
    def Z_ceil(self):           # inner face of the lid's top plate over the cavity
        return self.H - self.lid_t

    @property
    def Z_pcb_top(self):
        return self.Z_pcb_bot + self.pcb_t

    @property
    def D_w(self):              # bore floor = LED board contact face: optic recess + optic + LED board + paste
        return self.x_led_board + self.mcpcb_t + self.tim_t

    @property
    def pcb_dx(self):           # the board stack lies this far behind its v0.7 place (KiCad frame = v0.7 body)
        return self.X_pcb0 - X_PCB0_V07

    @property
    def grv_tail(self):         # tail V-grooves (apex X), all round, over the end of the cell bay
        return tuple(round(self.X_batt1 - d, 4) for d in self.grv_tail_off)

    @property
    def opt_front_x(self):      # front face of the optic (lens exit plane), behind the front face of the body
        return self.opt_recess

    @property
    def las_set_dy(self):       # laser set-screw axis to the laser axis (towards -Y)
        return self.Y_l - self.las_set[1]

    @property
    def las_set_tip_z(self):    # set-screw point on the laser module (module centred): the edge of the point nearest
        #                         to the laser axis touches first
        return self.Z_las + math.sqrt((self.las_d / 2) ** 2 - (self.las_set_dy - self.las_set_point / 2) ** 2)

    @property
    def las_set_bore_z(self):   # where the set-screw axis meets the laser bore wall
        return self.Z_las + math.sqrt(((self.las_d + self.las_clear) / 2) ** 2 - self.las_set_dy ** 2)

    @property
    def x_led_board(self):      # LED board front face = seat of the optic holder (LEDiL: "PCB level. LED location")
        return self.opt_recess + self.opt_h

    @property
    def X_pcb0(self):
        return self.L_head + self.pcb_gap_front

    @property
    def X_pcb1(self):
        return self.X_pcb0 + self.pcb_len

    @property
    def Y_pcb(self):
        return self.inner_half - self.pcb_side_gap

    @property
    def X_ant1(self):
        return self.X_pcb1 + self.mod_len - self.mod_onboard

    @property
    def X_batt0(self):
        return self.X_ant1 + self.ant_gap

    @property
    def X_batt1(self):
        return self.X_batt0 + self.L_batt

    @property
    def L_tail(self):
        return self.tail_front_wall + self.lan_slot_w + self.tail_end_wall

    @property
    def L(self):
        return self.X_batt1 + self.L_tail

    @property
    def X_lan(self):
        return self.X_batt1 + self.tail_front_wall + self.lan_slot_w / 2

    @property
    def X_screw_back(self):
        return self.X_lan

    @property
    def Z_usb(self):
        return self.Z_pcb_bot - 3.21 / 2

    @property
    def minusY_open(self):
        return ((self.X_usb - 4.9, self.X_usb + 5.0),)

    @property
    def can_top_z(self):
        return self.Z_pcb_top + self.mod_h

    @property
    def boss_h(self):           # lid boss height below the lid underside
        return self.Z_ceil - self.can_top_z - self.pad_gap

    @property
    def pad_strain(self):
        return 1.0 - self.pad_gap / self.pad_t0

    @property
    def rfw_box(self):
        return (self.X_pcb1 - self.rfw_x0_over_pcb, self.X_ant1 + self.rfw_x_beyond_ant, self.rfw_y / 2)

    # key stack
    @property
    def kb_z1(self):
        return self.kb_z0 + self.kb_t

    @property
    def Z_sw_tip(self):         # switch actuator tip, KB bottom face side (solder standoff included)
        return self.kb_z0 - self.smt_standoff - self.sw_h

    @property
    def Z_led_face(self):
        return self.kb_z0 - self.smt_standoff - self.ring_led_h

    @property
    def Z_seat(self):           # key flange seat = floor inner face
        return self.floor

    @property
    def main_top_z(self):       # main key top face (light input), at rest
        return self.Z_led_face - self.led_gap_rest

    @property
    def main_nub_z(self):
        return self.Z_sw_tip - self.pre_main

    @property
    def side_nub_z(self):       # side key: top of the doubler, the face that presses the switch
        return self.Z_sw_tip - self.pre_side

    @property
    def stiff_z0(self):         # side key: underside of the stiffener plate (the doubler sits on the plate)
        return self.side_nub_z - self.doubler[2] - self.stiffener[2]

    @property
    def pogo_h(self):           # pogo working height, nominal (pin base on its solder, to the J6 pad)
        return self.Z_pcb_bot - self.kb_z1 - self.smt_standoff

    @property
    def kb_screw_tip_z(self):
        return self.kb_z0 - (self.kb_screw_len - self.kb_t)

    @property
    def kb_thread_z(self):      # lowest Z of the full thread (0.15 below the screw tip)
        return self.kb_screw_tip_z - 0.15

    @property
    def kb_drill_z(self):       # end of the cylindrical tap drill (bottoming tap: 1.5 pitches of run-out)
        return self.kb_thread_z - 1.5 * self.m16_pitch

    @property
    def kb_drill_apex_z(self):  # 118 deg drill point
        return self.kb_drill_z - (self.m16_tap / 2) / math.tan(math.radians(59))

    @property
    def L_total(self):
        return self.L


def load_kb_interface(p, path):
    """Override the key-board numbers of P from a JSON file in the v0.7 interface format."""
    d = json.load(open(path))
    kb = d.get("key_board", {})
    o = kb.get("outline", {})
    p.kb_x0, p.kb_x1 = o.get("x0", p.kb_x0), o.get("x1", p.kb_x1)
    p.kb_y, p.kb_r = o.get("y1", p.kb_y), o.get("corner_r", p.kb_r)
    p.kb_t = kb.get("thickness", p.kb_t)
    p.kb_z0 = kb.get("z_bottom", p.kb_z0)
    if kb.get("mount_holes"):
        p.kb_holes = tuple((h["x"], h["y"]) for h in kb["mount_holes"])
        p.kb_hole_d = kb["mount_holes"][0].get("d", p.kb_hole_d)
    p.kb_keepout_d = kb.get("mount_keepout_d", p.kb_keepout_d)
    p.ring_led_h = kb.get("ring_led_height_worst_case", p.ring_led_h)
    sw = kb.get("switch", {})
    p.sw_h = sw.get("height_incl_actuator", p.sw_h)
    p.sw_travel = sw.get("travel", p.sw_travel)
    po = kb.get("pogo", {})
    p.pogo_free = po.get("free_height", p.pogo_free)
    p.pogo_work = po.get("working_height", p.pogo_work)
    p.pogo_min = po.get("min_height", p.pogo_min)
    if "max_working_height" in po:
        p.pogo_max_work = po["max_working_height"]
    if "base_d" in po:
        p.pogo_base = (po["base_d"], p.pogo_base[1])
    if "barrel_h" in po:
        p.pogo_barrel = (po.get("barrel_d", p.pogo_barrel[0]), po["barrel_h"])
    p.pogo_force_tol_n = po.get("force_tolerance_n", p.pogo_force_tol_n)
    p.pogo_plunger_d = po.get("plunger_d", p.pogo_plunger_d)
    p.pogo_force_n = po.get("force_at_working_n", p.pogo_force_n)
    if po.get("pins"):
        p.pogo_pins = tuple((q["x"], q["y"]) for q in po["pins"])
    if po.get("part"):
        p.pogo_part = po["part"]
    k = d.get("keys", {})
    for nm, attr in (("next", "X_next"), ("main", "X_main"), ("prev", "X_prev")):
        if nm in k:
            setattr(p, attr, k[nm]["x"])
    return p


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def rbox(x0, x1, y0, y1, z0, z1, r=0.0, axis="Z"):
    """Axis-aligned box with the edges parallel to `axis` rounded by r."""
    b = (cq.Workplane("XY")
         .box(x1 - x0, y1 - y0, z1 - z0, centered=False)
         .translate((x0, y0, z0)))
    if r > 0:
        b = b.edges("|" + axis).fillet(r)
    return b


def cyl_x(y, z, d, x0, x1):
    return (cq.Workplane("YZ").workplane(offset=x0)
            .center(y, z).circle(d / 2).extrude(x1 - x0))


def cyl_z(x, y, d, z0, z1):
    return (cq.Workplane("XY").workplane(offset=z0)
            .center(x, y).circle(d / 2).extrude(z1 - z0))


def slot_y(xc, zc, w, h, r, y0, y1):
    """Rounded-rectangle prism through a side wall (extent y0..y1)."""
    return rbox(xc - w / 2, xc + w / 2, y0, y1, zc - h / 2, zc + h / 2,
                r=min(r, h / 2 - 1e-3, w / 2 - 1e-3), axis="Y")


def rrect_z(x0, x1, y0, y1, z0, z1, r):
    return rbox(x0, x1, y0, y1, z0, z1, r=min(r, (x1 - x0) / 2 - 1e-3, (y1 - y0) / 2 - 1e-3))


def rrect_sketch(x0, x1, y0, y1, r):
    sk = cq.Sketch().push([((x0 + x1) / 2, (y0 + y1) / 2)]).rect(x1 - x0, y1 - y0)
    r = min(r, (x1 - x0) / 2 - 1e-3, (y1 - y0) / 2 - 1e-3)
    return sk.reset().vertices().fillet(r) if r > 0 else sk


def solids_of(wp):
    """list of cq.Solid of a Workplane / Shape"""
    s = wp.val() if isinstance(wp, cq.Workplane) else wp
    return list(s.Solids()) if hasattr(s, "Solids") else [s]


def cut_all(body, tools):
    """one boolean cut of many tool shapes (lists of Workplanes / Shapes)"""
    shapes = []
    for t in tools:
        if t is None:
            continue
        shapes += solids_of(t)
    if not shapes:
        return body
    b = body.val() if isinstance(body, cq.Workplane) else body
    return cq.Workplane().add(b.cut(*shapes).clean())


def transformed(shape, origin, u, v, n):
    """map a shape built in the canonical frame (X = u, Y = v, Z = n, origin 0) to a face frame"""
    from OCP.gp import gp_Ax3, gp_Pnt, gp_Dir, gp_Trsf
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    ax_from = gp_Ax3(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1), gp_Dir(1, 0, 0))
    ax_to = gp_Ax3(gp_Pnt(*origin), gp_Dir(*n), gp_Dir(*u))
    tr = gp_Trsf()
    tr.SetTransformation(ax_to, ax_from)
    s = shape.val() if isinstance(shape, cq.Workplane) else shape
    return cq.Workplane().add(cq.Shape.cast(BRepBuilderAPI_Transform(s.wrapped, tr, True).Shape()))


# --------------------------------------------------------------------------
# exterior: octagonal section (chamfered long edges)
# --------------------------------------------------------------------------
def section_pts(p, d=0.0):
    """body section (Y, Z) with 45 deg chamfers C_edge, offset inwards by d"""
    hw, H, c = p.W / 2, p.H, p.C_edge
    e = d * (math.sqrt(2) - 1)
    a, b = hw - c - e, hw - d
    zl, zh = c + e, H - c - e
    return [(-a, d), (a, d), (b, zl), (b, zh), (a, H - d), (-a, H - d), (-b, zh), (-b, zl)]


def envelope(p):
    env = cq.Workplane("YZ").polyline(section_pts(p)).close().extrude(p.L)
    env = env.faces("<X").chamfer(p.C_front).faces(">X").chamfer(p.C_end)
    return env


# face frames: right-handed (u, v, n) with n pointing into the material; natural face coordinates:
# bottom / top (X, Y), minus_y / plus_y (X, Z).  local b = natural v * VSIGN[face]
FACES = ("bottom", "top", "minus_y", "plus_y")
VSIGN = {"bottom": 1.0, "top": -1.0, "minus_y": -1.0, "plus_y": 1.0}


def face_frame(p, face):
    if face == "bottom":
        return (0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)
    if face == "top":
        return (0, 0, p.H), (1, 0, 0), (0, -1, 0), (0, 0, -1)
    if face == "minus_y":
        return (0, -p.W / 2, 0), (1, 0, 0), (0, 0, -1), (0, 1, 0)
    if face == "plus_y":
        return (0, p.W / 2, 0), (1, 0, 0), (0, 0, 1), (0, -1, 0)
    raise ValueError(face)


def to_face(p, face, shape):
    o, u, v, n = face_frame(p, face)
    return transformed(shape, o, u, v, n)


def _local_rect(face, u0, u1, v0, v1):
    """natural (u, v) rectangle -> local (a0, a1, b0, b1)"""
    s = VSIGN[face]
    b0, b1 = sorted((s * v0, s * v1))
    return u0, u1, b0, b1


def comb_tool(a0, a1, b0, b1, r, c_top, c_floor, pitch, depth, outline=None):
    """Local-frame cutter for a textured recess: everything from c_top (outside) down to the floor
    c_floor, plus 90 deg V-grooves (depth below the floor) along (1, 1)/sqrt2 with their roots on the
    global grid (a - b)/sqrt2 = k * pitch, clipped to the rounded rectangle (or the given outline solid)."""
    rt2 = math.sqrt(2)
    s_lo, s_hi = (a0 - b1) / rt2 - 1.0, (a1 - b0) / rt2 + 1.0
    t_lo, t_hi = (a0 + b0) / rt2 - 1.0, (a1 + b1) / rt2 + 1.0
    w = depth                       # half width of a 90 deg V
    pts = [(s_lo, c_top), (s_hi, c_top), (s_hi, c_floor)]
    if pitch and depth > 0:
        k1 = math.floor((s_hi - w) / pitch)
        k0 = math.ceil((s_lo + w) / pitch)
        for k in range(k1, k0 - 1, -1):
            sk = k * pitch
            pts += [(sk + w, c_floor), (sk, c_floor + depth), (sk - w, c_floor)]
    pts += [(s_lo, c_floor)]
    # profile in the XZ plane (x = s, z = c), extruded along +Y (= t) from t_lo to t_hi
    prof = cq.Workplane("XZ", origin=(0, t_lo, 0)).polyline(pts).close()
    comb = prof.extrude(-(t_hi - t_lo))          # XZ normal is -Y: negative extrude goes +Y
    comb = comb.rotate((0, 0, 0), (0, 0, 1), -45)
    if outline is None:
        c_bot = c_floor + depth + 0.1
        outline = (cq.Workplane("XY", origin=(0, 0, c_top - 0.1))
                   .placeSketch(rrect_sketch(a0, a1, b0, b1, r)).extrude(c_bot - c_top + 0.2))
    return comb.intersect(outline)


# --------------------------------------------------------------------------
# panel layout (follows the inside: key bezel, RF windows, USB-C and S2 openings, screws, joint)
# --------------------------------------------------------------------------
def bay_panels_x(p):
    x0 = p.frw_box[1] + p.band_rf
    x1 = p.grv_tail[0] - p.grv_depth - p.band - 0.3
    n = max(1, p.bay_split)
    ln = (x1 - x0 - (n - 1) * p.band) / n
    return [(x0 + k * (ln + p.band), x0 + k * (ln + p.band) + ln) for k in range(n)]


def panel_layout(p):
    """textured aluminium panels: list of dict(name, face, u0, u1, v0, v1, r) in natural face coordinates"""
    out = []
    vy = p.W / 2 - p.C_edge - p.rail                 # top / bottom: |Y| limit
    z0s, z1s = p.C_edge + p.rail, p.Z_lid - p.rail      # sides: between the facet edges (the upper one = lid joint)
    bays = bay_panels_x(p)
    # top (lid): PCB-zone panel between the front screws and the RF pocket (>= 1 mm from the pocket)
    xt0 = p.screw_x_front + p.m16_csk / 2 + p.band
    xt1 = p.rfw_box[0] - p.rfw_flange - p.tex_min_metal
    out.append(dict(name="top PCB zone", face="top", u0=xt0, u1=xt1, v0=-vy, v1=vy))
    for k, (a, b) in enumerate(bays):
        for f in FACES:
            if f == "bottom" and k == 0:
                # the floor RF window (textured POM plug) is the front part of the first bottom panel,
                # so it reads as one panel and not as a fourth key
                out.append(dict(name="bottom bay 1 (with the RF window)", face=f, u0=p.frw_box[0], u1=b,
                                v0=-vy, v1=vy))
            elif f in ("top", "bottom"):
                out.append(dict(name="%s bay %d" % (f, k + 1), face=f, u0=a, u1=b, v0=-vy, v1=vy))
            else:
                out.append(dict(name="%s bay %d" % (f, k + 1), face=f, u0=a, u1=b, v0=z0s, v1=z1s))
    # sides: from the USB-C opening / S2 slot to the first bay band
    xs1 = bays[0][0] - p.band
    xm0 = p.X_usb + p.usb_open[0] / 2 + p.usb_open_chamfer + p.band
    xp0 = p.X_s2 + p.s2_slot[0] / 2 + p.band
    out.append(dict(name="minus_y PCB zone", face="minus_y", u0=xm0, u1=xs1, v0=z0s, v1=z1s))
    out.append(dict(name="plus_y PCB zone", face="plus_y", u0=xp0, u1=xs1, v0=z0s, v1=z1s))
    for q in out:
        q["r"] = p.pan_r
    return out


def panel_tools(p, texture=True):
    """cutters of all textured panels (world frame)"""
    tools = []
    for q in panel_layout(p):
        a0, a1, b0, b1 = _local_rect(q["face"], q["u0"], q["u1"], q["v0"], q["v1"])
        t = comb_tool(a0, a1, b0, b1, q["r"], -1.0, p.pan_depth, p.tex_pitch if texture else 0.0,
                      p.tex_depth if texture else 0.0)
        tools.append((q["name"], to_face(p, q["face"], t)))
    return tools


def insert_texture_tool(p, face, outline_wp_local, c_floor):
    """V-grooves (global grid) below a POM insert face at local depth c_floor, clipped to an outline solid
    given in the local frame of `face`; returns a world-frame cutter (grooves only)."""
    bb = outline_wp_local.val().BoundingBox()
    comb = comb_tool(bb.xmin, bb.xmax, bb.ymin, bb.ymax, 0.0, c_floor - 0.2, c_floor, p.tex_pitch, p.tex_depth,
                     outline=outline_wp_local)
    return to_face(p, face, comb)


# --------------------------------------------------------------------------
# transverse V-grooves (RovyVon-like) - rings round the octagonal section
# --------------------------------------------------------------------------
def ring_groove(p, xa, d=None, ext=0.3):
    """90 deg V groove round the body, apex xa, depth d"""
    d = p.grv_depth if d is None else d
    D = d + ext
    apex = section_pts(p, d)
    left = cq.Workplane("YZ", origin=(xa, 0, 0)).polyline(apex).close().extrude(-D, taper=-45)
    right = cq.Workplane("YZ", origin=(xa, 0, 0)).polyline(apex).close().extrude(D, taper=-45)
    core = left.union(right)
    return rbox(xa - D + 0.01, xa + D - 0.01, -p.W, p.W, -p.H, 2 * p.H).cut(core)


def groove_tools(p):
    """(name, cutter): head set on the top, bottom and the four chamfers (the window and laser bores leave
    too little metal under the side faces), tail set all round"""
    out = []
    keep = (rbox(-5, 20, -(p.W / 2 - p.C_edge) - 0.02, p.W / 2 - p.C_edge + 0.02, -5, p.H + 5)
            .union(rbox(-5, 20, -p.W, p.W, -5, p.C_edge + 0.02))
            .union(rbox(-5, 20, -p.W, p.W, p.H - p.C_edge - 0.02, p.H + 5)))
    for x in p.grv_head:
        out.append(("head groove X%g" % x, ring_groove(p, x).intersect(keep)))
    for x in p.grv_tail:
        out.append(("tail groove X%g" % x, ring_groove(p, x)))
    return out


# --------------------------------------------------------------------------
# key bezel and floor openings
# --------------------------------------------------------------------------
def key_rects(p, grow=0.0, grow_end=None):
    """(x0, x1, y0, y1, r) of the three keys, grown by `grow` (side key ends by grow_end)"""
    ge = grow if grow_end is None else grow_end
    sx, sy, sr = p.side_key
    mx, my, mr = p.main_key
    y = p.key_y
    return {"next": (p.X_next - sx / 2 - grow, p.X_next + sx / 2 + grow, y - sy / 2 - ge, y + sy / 2 + ge, sr + grow),
            "main": (p.X_main - mx / 2 - grow, p.X_main + mx / 2 + grow, y - my / 2 - grow, y + my / 2 + grow, mr + grow),
            "prev": (p.X_prev - sx / 2 - grow, p.X_prev + sx / 2 + grow, y - sy / 2 - ge, y + sy / 2 + ge, sr + grow)}


def bezel_sketch(p, m):
    """outline of the bezel at margin m round the keys"""
    kr = key_rects(p, m)
    if p.bez_style == "stadium":
        x0, y0, r0 = kr["next"][0], kr["next"][2], kr["next"][4]
        x1, y1 = kr["prev"][1], kr["prev"][3]
        return rrect_sketch(x0, x1, y0, y1, r0)
    # 'bone': the three key outlines joined by a band as wide as the main key
    sk = cq.Sketch()
    for k in ("next", "main", "prev"):
        x0, x1, y0, y1, r = kr[k]
        sk = sk.push([((x0 + x1) / 2, (y0 + y1) / 2)]).rect(x1 - x0, y1 - y0).reset()
    x0, x1 = kr["next"][0] + 1.0, kr["prev"][1] - 1.0
    sk = sk.push([((x0 + x1) / 2, p.key_y)]).rect(x1 - x0, kr["main"][3] - kr["main"][2]).reset()
    return sk.clean().reset().vertices().fillet(0.6)


def bezel_tool(p):
    """45 deg recess round the keys, floor at Z bez_depth"""
    sk = bezel_sketch(p, p.bez_margin)
    return (cq.Workplane("XY", origin=(0, 0, p.bez_depth)).placeSketch(sk)
            .extrude(-(p.bez_depth + 0.3), taper=-45))


def key_openings(p):
    """through openings for the three keys"""
    kr = key_rects(p, p.key_clear, p.key_clear_end)
    out = []
    for k in ("next", "main", "prev"):
        x0, x1, y0, y1, r = kr[k]
        if k == "main":
            y0, y1 = p.key_y - p.main_key[1] / 2 - p.key_clear, p.key_y + p.main_key[1] / 2 + p.key_clear
        out.append(rrect_z(x0, x1, y0, y1, -1.0, p.floor + 0.2, r))
    return out


def kb_supports(p):
    """bosses (tapped, merged with the trough wall) and support ribs for the KB, Z floor .. kb_z0"""
    yt = p.inner_half - p.ledge_w          # trough wall
    z0, z1 = p.floor - 0.01, p.kb_z0
    out = []
    for (x, y) in p.kb_holes:
        s = 1 if y > 0 else -1
        b = cyl_z(x, y, p.boss_d, z0, z1)
        ya, yb = sorted((y, s * (yt + 0.3)))
        b = b.union(rbox(x - p.boss_d / 2, x + p.boss_d / 2, ya, yb, z0, z1))
        out.append(("boss X%g Y%+g" % (x, y), b))
    usb0, usb1 = p.minusY_open[0]
    for (x, s) in p.kb_ribs:
        free = s < 0 and usb0 - 0.5 < x < usb1 + 0.5      # USB-C gap: the wall is far away -> free post
        y_in = s * p.rib_y0
        if free:
            ya, yb = sorted((y_in, s * (p.kb_y - 0.3)))
            b = rbox(x - p.rib_w / 2, x + p.rib_w / 2, ya, yb, z0, z1, r=0.3)
        else:
            ya, yb = sorted((y_in, s * (yt + 0.3)))
            b = rbox(x - p.rib_w / 2, x + p.rib_w / 2, ya, yb, z0, z1)
        out.append(("rib X%g %s" % (x, "+Y" if s > 0 else "-Y"), b))
    return out


def kb_tap_holes(p):
    """blind M1.6 tap drills in the bosses (cylinder + 118 deg point)"""
    out = []
    r = p.m16_tap / 2
    for (x, y) in p.kb_holes:
        c = cyl_z(x, y, p.m16_tap, p.kb_drill_z, p.kb_z0 + 0.1)
        h = p.kb_drill_z - p.kb_drill_apex_z
        cone = cq.Workplane().add(cq.Solid.makeCone(r, 0.0, h, pnt=cq.Vector(x, y, p.kb_drill_z),
                                                    dir=cq.Vector(0, 0, -1)))
        out.append(c.union(cone))
    return out


# --------------------------------------------------------------------------
# interior (as v0.6) and tail
# --------------------------------------------------------------------------
def led_wire_dirs(p):
    """unit vectors (dy, dz) of the upper and the lower LED wire path, seen along X"""
    a = math.radians(p.led_wire_ang)
    return [(math.sin(a), math.cos(a)), (-math.sin(a), -math.cos(a))]


def led_wire_hole_yz(p):
    """[(y, z) upper, (y, z) lower]: axes of the two LED wire holes"""
    return [(p.Y_w + p.led_wire_r * dy, p.Z_axis + p.led_wire_r * dz) for dy, dz in led_wire_dirs(p)]


def led_wire_hole_x_end(p):
    """[upper, lower]: X where each LED wire hole ends - just behind the head rear face, or, where the hole meets the
    R inner_r corner of the cavity (the lower one, below the board ledges), far enough to break fully into it"""
    out = []
    for yh, zh in led_wire_hole_yz(p):
        halfw = p.inner_half - (p.ledge_w if zh < p.Z_pcb_bot else 0.0)
        R, rh = p.inner_r, p.ledwire_d / 2
        over = abs(yh) + rh - (halfw - R)
        if over <= 0:
            out.append(round(p.L_head + 0.01, 4))
        else:
            out.append(round(p.L_head + R - math.sqrt(max(R * R - over * over, 0.0)) + 0.2, 3))
    return out


def led_wire_paths(p):
    """(groove, hole) x 2: the LED wires leave the pads on the front face of the LED board, bend over its edge into a
    groove in the bore wall (tilted led_wire_ang from 12 and 6 o'clock, beside the optic holder) and run straight on
    through a hole in the solid behind the bore floor into the cavity - the hole lies on the groove line, so no wire
    passes under the LED board"""
    gw, gd = p.wire_groove
    rb = p.opt_bore / 2
    out = []
    for (dy, dz), (yh, zh), xe in zip(led_wire_dirs(p), led_wire_hole_yz(p), led_wire_hole_x_end(p)):
        s = 1 if dz > 0 else -1
        z0, z1 = sorted((s * (rb - 0.05), s * (rb + gd)))
        loc = rbox(p.x_led_board - 1.0, p.D_w + 0.01, -gw / 2, gw / 2, z0, z1)
        groove = loc.rotate((0, 0, 0), (1, 0, 0), -p.led_wire_ang).translate((0, p.Y_w, p.Z_axis))
        hole = cyl_x(yh, zh, p.ledwire_d, p.D_w - 0.01, xe)
        out.append((groove, hole))
    return out


def laser_set_hole(p, z1=None):
    """M1.6 tap drill of the laser set screw: from the head-block top (under the lid) down into the laser bore"""
    return cyl_z(p.las_set[0], p.las_set[1], p.m16_tap, p.Z_las, p.Z_lid + 0.1 if z1 is None else z1)


def front_relief_tool(p, sy, z1=None):
    """relief at a front corner of the cavity, from just below the ledge top to the lid seat"""
    d, dx, dy = p.front_relief
    return cyl_z(p.L_head + dx, sy * (p.inner_half - dy), d, p.Z_pcb_bot - 0.01, p.Z_lid + 0.01 if z1 is None else z1)


def optic_bore(p, x1=None):
    """the bore of the TIR optic and the LED board (one diameter, it centres both), from the front face to the bore
    floor (the LED board contact face)"""
    return cyl_x(p.Y_w, p.Z_axis, p.opt_bore, -1, p.D_w if x1 is None else x1)


def inner_pts(p, clr=0.0, part="all"):
    """inside of the closed body (Y, Z), offset inwards by clr: the walls (side, floor, diagonal facets, lid plate) are
    all p.wall thick (the floor p.floor, the lid plate p.lid_t).  part 'tray': the tray's cavity section (bottom
    facets, vertical walls up to the lid seat Z_lid), 'lid': the lid's pocket above Z_lid (diagonal facets, plate),
    'all': both, with the step where the lid's inner edge overhangs the tray walls"""
    hw, H, c, rt2 = p.W / 2, p.H, p.C_edge, math.sqrt(2)
    td = p.wall + clr                                   # wall normal to the diagonal facets
    zf = p.floor + clr
    ys = hw - p.wall - clr                              # inner side wall
    k_b = hw - c - td * rt2                             # bottom diagonal: y - z = k_b
    k_t = hw + H - c - td * rt2                         # top diagonal: y + z = k_t
    zt = H - p.lid_t - clr                              # lid plate
    zl = p.Z_lid - clr                                  # lid seat (the lid's flat underside at its edges)
    yb, zcs = k_b + zf, ys - k_b
    yl, yt = k_t - zl, k_t - zt
    tray = [(yb, zf), (ys, zcs), (ys, p.Z_lid + 0.01)]
    z_o = p.Z_lid - 0.01                                # the lid pocket starts just below the seat (clean cut)
    lid = [(min(k_t - z_o, ys), z_o), (yt, zt)]
    if part == "tray":
        half = tray
    elif part == "lid":
        half = lid
    else:
        half = [(yb, zf), (ys, zcs), (ys, zl), (min(yl, ys), zl), (yt, zt)]
    return half + [(-y, z) for (y, z) in reversed(half)]


def inner_prism(p, x0, x1, clr=0.0, part="all"):
    return cq.Workplane("YZ", origin=(x0, 0, 0)).polyline(inner_pts(p, clr, part)).close().extrude(x1 - x0)


def lid_region(p):
    """the lid is everything above the lid seat Z_lid from X lid_x0 on (the parting plane meets the outside at the
    edge between the side facets and the upper diagonal facets)"""
    return rbox(p.lid_x0, p.L + 1, -p.W, p.W, p.Z_lid, p.H + 1)


def lid_part_region(p):
    return lid_region(p)


def lid_pocket(p):
    """the lid's inside over the cavity (milled from below): the inner section above the lid seat, plan corners
    R inner_r like the cavity"""
    ih, r = p.inner_half, p.inner_r
    plan = rbox(p.L_head, p.X_batt1, -ih, ih, p.Z_lid - 0.01, p.H, r)
    return inner_prism(p, p.L_head - 1, p.X_batt1 + 1, 0.0, "lid").intersect(plan)


def bay_rails(p):
    """two floor rails in the cell bay: the cell rests on their inner top edges (|Y| rail_y)"""
    out = []
    for s in (-1, 1):
        ya, yb = sorted((s * p.rail_y, s * (p.rail_y + p.rail_w)))
        out.append(rbox(p.X_batt0 + 3.0, p.X_batt1 - 3.0, ya, yb, p.floor - 0.01, p.floor + p.rail_h))
    return out


def cavity_solid(p, supports=True):
    """milled interior of the tray: board zone above the ledges, trough below them, antenna zone and cell bay,
    bounded by the inner section of the octagon (45 deg corners at the floor); minus the KB bosses and ribs on the
    floor and the two rails of the cell bay"""
    ih, r = p.inner_half, p.inner_r
    c = rbox(p.L_head, p.X_batt1, -ih, ih, p.Z_pcb_bot, p.Z_lid + 0.01, r)
    c = c.union(rbox(p.L_head, p.X_pcb1 + 0.5, -(ih - p.ledge_w), ih - p.ledge_w,
                     p.floor, p.Z_pcb_bot + 0.01, r))
    c = c.union(rbox(p.X_pcb1, p.X_batt1, -ih, ih, p.floor, p.Z_pcb_bot + 0.01, r))
    for (xa, xb) in p.minusY_open:
        c = c.union(rbox(xa, xb, -ih, -(ih - p.ledge_w) + 1.0, p.floor, p.Z_pcb_bot + 0.01, 0.6))
    c = c.union(rbox(p.L_head, p.las_keepout_x, ih - p.ledge_w - 1.0, ih,
                     p.floor, p.Z_pcb_bot + 0.01, 0.6))
    c = c.intersect(inner_prism(p, p.L_head - 1, p.X_batt1 + 1, 0.0, "tray"))
    if supports:
        for _, s in kb_supports(p):
            c = c.cut(s)
    for rl in bay_rails(p):
        c = c.cut(rl)
    return c


def _chamfered_through(face_wp_fn, z0, z1, c, ext=0.1, top=True, bottom=True):
    core = face_wp_fn(z0 - 1).extrude(z1 - z0 + 2)
    if top:
        core = core.union(face_wp_fn(z1 - c).extrude(c + ext, taper=-45))
    if bottom:
        core = core.union(face_wp_fn(z0 + c).extrude(-(c + ext), taper=-45))
    return core


def tail_tools(p):
    """lanyard slot through tray and lid, recessed window on the bottom face round it, 45 deg tail facets.
    Returns (tray_tools, lid_tools)."""
    xc, d, H = p.X_lan, p.twin_depth, p.H
    x0, x1 = max(xc - p.twin_x / 2, p.X_batt1 + p.twin_front_gap), xc + p.twin_x / 2
    hy, k = p.twin_y / 2, p.twin_corner
    sk = (cq.Sketch().polygon([(x0, -hy), (x1 - k, -hy), (x1, -hy + k), (x1, hy - k),
                               (x1 - k, hy), (x0, hy), (x0, -hy)])
          .vertices().fillet(p.twin_r))
    bot = cq.Workplane("XY", origin=(0, 0, -1)).placeSketch(sk).extrude(d + 1)
    rim = (cq.Workplane("XY", origin=(0, 0, p.twin_chamfer)).placeSketch(sk)
           .extrude(-(p.twin_chamfer + 0.3), taper=-45))
    bot = bot.union(rim)

    def slot(z):
        return (cq.Workplane("XY", origin=(0, 0, z)).center(xc, 0)
                .slot2D(p.lan_slot_len, p.lan_slot_w, 90))
    tray_slot = _chamfered_through(slot, d, p.Z_lid, p.lan_chamfer, top=False)
    lid_slot = _chamfered_through(slot, p.Z_lid, H, p.lan_chamfer, bottom=False)
    facets = []
    for s in (-1, 1):
        f, L, w = p.tail_facet, p.L, p.W / 2
        facets.append(cq.Workplane("XY", origin=(0, 0, -1))
                      .polyline([(L - f, s * w), (L + 3, s * w), (L + 3, s * (w - f - 3))]).close()
                      .extrude(H + 2))
    return [bot, tray_slot] + facets, [lid_slot] + facets


def rf_window_outline(p, grow=0.0, z0=0.0, z1=1.0):
    x0, x1, hy = p.rfw_box
    return rrect_z(x0 - grow, x1 + grow, -hy - grow, hy + grow, z0, z1, p.rfw_r + grow)


def floor_rf_opening(p, grow=0.0, z0=-1.0, z1=None):
    x0, x1, hy, r = p.frw_box
    z1 = p.floor + 0.1 if z1 is None else z1
    return rrect_z(x0 - grow, x1 + grow, -hy - grow, hy + grow, z0, z1, r + grow)


# --------------------------------------------------------------------------
# parts
# --------------------------------------------------------------------------
TEXTURE_LEVELS = ("none", "panels", "full")


def _tex(texture):
    if texture is True or texture is None:
        return "full"
    if texture is False:
        return "none"
    if texture not in TEXTURE_LEVELS:
        raise ValueError(texture)
    return texture


def build_tray(p, texture="full"):
    """texture: 'full' (panels with the V texture), 'panels' (recessed panels, no texture: drawings),
    'none' (plain body, fast: fit checks)"""
    texture = _tex(texture)
    t = envelope(p).cut(lid_region(p))
    t = t.cut(cavity_solid(p))
    ih = p.inner_half
    cuts = []
    for sy in (-1, 1):
        cuts.append(front_relief_tool(p, sy))
    # head: optic + LED-board bore, LED wire grooves + holes, laser bore, laser set screw (from the top, under the lid)
    cuts.append(optic_bore(p))
    for groove, hole in led_wire_paths(p):
        cuts += [groove, hole]
    cuts.append(cyl_x(p.Y_l, p.Z_las, p.las_d + p.las_clear, -1, p.las_recess + p.las_len + p.las_bore_extra))
    cuts.append(laser_set_hole(p))
    # lid screw taps
    for s in (-1, 1):
        for x in (p.screw_x_front, p.X_screw_back):
            cuts.append(cyl_z(x, s * p.screw_dy, p.m16_tap, p.Z_lid - p.m16_drill, p.Z_lid + 0.1))
    # floor: key openings, bezel, floor RF window, KB tap holes
    cuts += key_openings(p)
    cuts.append(floor_rf_opening(p))
    cuts += kb_tap_holes(p)
    t = cut_all(t, cuts)
    t = t.cut(bezel_tool(p))
    # control side (-Y): USB-C opening + 45 deg chamfer band
    yo = -p.W / 2
    w, h, r = p.usb_open
    c = p.usb_open_chamfer
    band = (cq.Workplane("XZ", origin=(0, yo + c, 0)).center(p.X_usb, p.Z_usb).sketch()
            .rect(w, h).vertices().fillet(r).finalize().extrude(c + 0.3, taper=-45))
    w2, h2, r2 = p.s2_slot
    t = cut_all(t, [slot_y(p.X_usb, p.Z_usb, w, h, r, yo - 1, -ih + 0.01), band,
                    slot_y(p.X_s2, p.Z_pcb_top + p.s2_knob_z, w2, h2, r2, ih - 0.01, p.W / 2 + 1)])
    # exterior: tail, grooves, panels
    tray_tail, _ = tail_tools(p)
    ext = list(tray_tail) + [g for _, g in groove_tools(p)]
    if texture != "none":
        ext += [s for _, s in panel_tools(p, texture == "full")]
    t = cut_all(t, ext)
    return t


def boss_solid(p):
    x0, x1, y0, y1 = p.boss_box
    return rrect_z(x0, x1, y0, y1, p.Z_ceil - p.boss_h, p.Z_ceil + 0.01, p.boss_r)


def boss2_solid(p):
    x0, x1, y0, y1 = p.boss2_box
    zb = p.Z_pcb_top + p.pad2_gap
    return rrect_z(x0, x1, y0, y1, zb, p.Z_ceil + 0.01, p.boss2_r)


def build_lid(p, texture="full"):
    """the lid: the body above the lid seat Z_lid (top facet and the two upper diagonal facets), hollow over the cavity
    (lid_pocket), solid over the head and the tail blocks, where its screws go through it"""
    texture = _tex(texture)
    lid = envelope(p).intersect(lid_part_region(p))
    pts = [(p.screw_x_front, -p.screw_dy), (p.screw_x_front, p.screw_dy),
           (p.X_screw_back, -p.screw_dy), (p.X_screw_back, p.screw_dy)]
    lid = (lid.faces(">Z").workplane(origin=(0, 0, p.H)).pushPoints(pts)
           .cskHole(p.m16_clear, p.m16_csk, 90))
    _, lid_tail = tail_tools(p)
    cuts = [lid_pocket(p), rf_window_outline(p, 0.0, p.Z_ceil - 1, p.H + 1),
            rf_window_outline(p, p.rfw_flange, p.Z_ceil - 1, p.Z_ceil + p.rfw_flange_t)] + list(lid_tail)
    lid = cut_all(lid, cuts)
    lid = lid.union(boss_solid(p))
    if p.front_boss:
        lid = lid.union(boss2_solid(p))
    ext = [g for _, g in groove_tools(p)]
    if texture != "none":
        ext += [s for _, s in panel_tools(p, texture == "full")]
    lid = cut_all(lid, ext)
    return lid


def build_rf_window(p, texture=True):
    """POM-C insert: plug in the lid opening (face at the panel level, textured; the plug locates the insert),
    flange in the pocket with rfw_flange_clear per side (its edge is free: the kit tabs sit there)"""
    c = p.rfw_clear
    z_face = p.H - p.pan_depth
    plug = rf_window_outline(p, -c, p.Z_ceil + p.rfw_flange_t - 0.01, z_face)
    flange = rf_window_outline(p, p.rfw_flange - p.rfw_flange_clear, p.Z_ceil - p.rfw_flange_drop,
                               p.Z_ceil + p.rfw_flange_t)
    w = plug.union(flange)
    if texture:
        x0, x1, hy = p.rfw_box
        # outline in the local frame of the top face (a = X, b = -Y, c = H - Z)
        ol = (cq.Workplane("XY", origin=(0, 0, p.pan_depth - 0.3))
              .placeSketch(rrect_sketch(x0 - c - 0.5, x1 + c + 0.5, -hy - c - 0.5, hy + c + 0.5, p.rfw_r))
              .extrude(p.tex_depth + 0.6))
        w = w.cut(insert_texture_tool(p, "top", ol, p.pan_depth))
    return w


def build_antenna_spacer(p, texture=True):
    """POM-C block between the PCB rear edge and the cell: the antenna overhang sits in the U, the cell's front end
    (strip) rests against the rear face.  A plug on its bottom fills the floor RF window (face at the panel level,
    textured); a rebate on the -Y side (open to the wall and to the top, so that a 3-axis mill reaches it from
    above) carries the two cell wires above the key board to J2; the module overhang lies above it.  The outline
    follows the inside of the octagon (0.1 clearance), up to the lid's diagonal facets and under the RF insert."""
    ih = p.inner_half - 0.1
    x0, x1 = p.X_pcb1 + 0.15, p.X_batt0 - 0.05
    z_top_low = p.Z_pcb_top - 0.4
    body = rbox(x0, x1, -ih, ih, p.floor + 0.05, z_top_low, 0.4)
    side = p.mod_y + p.mod_w / 2 + 0.45
    for (ya, yb) in ((-ih, p.mod_y - p.mod_w / 2 - 0.3), (side, ih)):
        if yb - ya > 0.6:
            # up to 0.15 under the RF insert flange (it keeps the insert from dropping in), above the lid seat
            # inside the lid's diagonal facets (the intersection below)
            body = body.union(rbox(x0, x1, ya, yb, p.floor + 0.05, p.Z_ceil - p.rfw_flange_drop - 0.15, 0.2))
    # clear of the PCB ledge blocks beside the antenna zone
    for sg in (1, -1):
        ya, yb = (7.2, ih + 1) if sg > 0 else (-ih - 1, -7.2)
        body = body.cut(rbox(x0 - 1, p.X_pcb1 + 1.5, ya, yb, p.floor - 0.1, p.Z_pcb_bot + 0.2))
    # cell-wire rebate (-Y side, open to the wall and to the top), floor above the KB level
    cy0, cy1, cz0, cz1 = cell_wire_channel(p)
    body = body.cut(rbox(x0 - 1, x1 + 1, cy0, cy1, cz0, cz1))
    body = body.intersect(inner_prism(p, x0 - 1, x1 + 1, 0.1, "all"))
    # plug for the floor RF window
    wx0, wx1, hy, r = p.frw_box
    c = p.rfw_clear
    plug = rrect_z(wx0 + c, wx1 - c, -hy + c, hy - c, p.pan_depth, p.floor + 0.1, r - c)
    body = body.union(plug)
    if texture:
        ol = (cq.Workplane("XY", origin=(0, 0, p.pan_depth - 0.3))
              .placeSketch(rrect_sketch(wx0 - 0.5, wx1 + 0.5, -hy - 0.5, hy + 0.5, r))
              .extrude(p.tex_depth + 0.6))
        body = body.cut(insert_texture_tool(p, "bottom", ol, p.pan_depth))
    return body


def cell_wire_channel(p):
    """(y0, y1, z0, z1) of the cell-wire rebate in the antenna spacer: open to the -Y wall and to the top
    (z1 above the part); the floor z0 is 0.4 above the key board"""
    return (-p.inner_half - 1.0, -4.6, p.kb_z1 + 0.4, p.H + 1.0)


def build_optic(p):
    """LEDiL LISA3-RS-PIN as installed, simplified (pictures, assembly, clearances): (holder, lens).  Known from LEDiL:
    d10.0 x 6.93 +/-0.2 above the LED board, black PC holder standing on the board, clear PMMA lens; the pins are cut
    off.  The inner shape (lens exit d8.6 = the unlabelled drawing callout, TIR flank, LED cavity d5.1 x 1.2 for a
    3.5 x 3.5 package) is drawn, not measured."""
    x0, x1 = p.opt_front_x, p.x_led_board
    h = x1 - x0
    re_ = p.opt_exit_d / 2

    def revolve(pts):
        # profile (t = distance from the optic front, r = radius) revolved about the optic axis
        w = cq.Workplane("XZ").polyline([(r, t) for t, r in pts]).close().revolve(360, (0, 0, 0), (0, 1, 0))
        return w
    lens_pts = [(0.15, 0.0), (0.15, re_ - 0.05), (0.75, re_ - 0.05), (2.0, re_ - 0.45), (3.5, 3.55), (5.0, 3.05),
                (h - 0.9, 2.75), (h - 0.9, 2.55), (h - 2.1, 2.55), (h - 2.4, 1.6), (h - 2.55, 0.0)]
    lens = revolve(lens_pts)
    hold_pts = [(0.0, re_), (0.0, p.opt_od / 2), (h, p.opt_od / 2), (h, 2.6), (h - 0.9, 2.6), (h - 0.9, 2.8),
                (5.0, 3.1), (3.5, 3.6), (2.0, re_ - 0.4), (0.75, re_)]
    holder = revolve(hold_pts)

    def place(w):
        # revolved about global Z (t along +Z) -> optic axis along +X from the optic front, centred on (Y_w, Z_axis)
        return w.rotate((0, 0, 0), (0, 1, 0), 90).translate((x0, p.Y_w, p.Z_axis))
    return place(holder), place(lens)


def build_laser_sleeve(p):
    x0 = p.las_recess
    sl = (cq.Workplane("YZ").workplane(offset=x0).center(p.Y_l, p.Z_las)
          .circle(p.sleeve_od / 2).circle(p.sleeve_id / 2).extrude(p.sleeve_len))
    slit = rbox(x0 - 1, x0 + p.sleeve_len + 1, p.Y_l - p.sleeve_slit / 2, p.Y_l + p.sleeve_slit / 2,
                p.Z_las - p.sleeve_od, p.Z_las)
    return sl.cut(slit)


# ---- keys
def build_key_main(p, rest=0.0, icon=True):
    """clear PMMA key in place (flange on the floor seat).  rest: lift (+Z) for stroke checks"""
    mx, my, mr = p.main_key
    x, y = p.X_main, p.key_y
    zs = p.Z_seat
    fw = p.flange_main
    cap = rrect_z(x - mx / 2, x + mx / 2, y - my / 2, y + my / 2, p.main_face_z, p.main_top_z, mr)
    fl = rrect_z(x - mx / 2 - fw, x + mx / 2 + fw, y - my / 2 - fw, y + my / 2 + fw, zs, zs + p.flange_t, mr + fw)
    k = cap.union(fl)
    # pocket round the switch body (SW1 pads along X: body 3.9 along X)
    bx, by = p.sw_body
    pc = p.pocket_clear
    z_floor = p.main_nub_z - p.nub_h
    k = k.cut(rrect_z(x - bx / 2 - pc, x + bx / 2 + pc, y - by / 2 - pc, y + by / 2 + pc, z_floor,
                      p.main_top_z + 1, 0.5))
    k = k.union(cyl_z(x, y, p.nub_d, z_floor - 0.01, p.main_nub_z))
    # polished edge break on the outer face
    k = k.faces("<Z").edges().chamfer(0.15)
    if icon:
        dm, w, d = p.ring_icon
        ring = (cq.Workplane("XY", origin=(x, y, p.main_face_z - 0.1)).circle(dm / 2 + w / 2).circle(dm / 2 - w / 2)
                .extrude(0.1 + d))
        k = k.cut(ring)
    return k.translate((0, 0, rest)) if rest else k


def ring_icon_solid(p, thick=0.02):
    """the frosted ring as a thin solid on the key face (for the renders)"""
    dm, w, d = p.ring_icon
    return (cq.Workplane("XY", origin=(p.X_main, p.key_y, p.main_face_z + d - thick))
            .circle(dm / 2 + w / 2).circle(dm / 2 - w / 2).extrude(thick))


def chevron_pts(p, x, pointing):
    """centre line of the chevron on the side key at X = x: arm end, apex, arm end.  The apex points along the
    body: towards the head, -X (pointing = -1, next key) or towards the tail, +X (+1, previous key).  Held like a
    presenter (head to the screen, keys up) the key nearest the head reads '^' (next), the other 'v' (previous)."""
    sw, a, b = p.chevron
    y, s = p.key_y, pointing
    return [(x - s * a, y - b), (x + s * a, y), (x - s * a, y + b)]


def chevron_solid(p, x, pointing):
    """raised chevron on the side key face (see chevron_pts), stroke chevron[0], round ends"""
    sw = p.chevron[0]
    z1 = p.side_face_z + 0.01
    z0 = p.side_face_z - p.chevron_h
    wire = cq.Workplane("XY", origin=(0, 0, z0)).polyline(chevron_pts(p, x, pointing)).offset2D(sw / 2, "arc")
    return wire.extrude(z1 - z0)


def build_key_side(p, x=None, pointing=-1, rest=0.0, recess=True):
    """cast elastomer side key in place, one piece without inserts; x = key centre X; pointing -1 = chevron apex
    towards the head, -X (next key), +1 = towards the tail, +X (previous key: the same part turned 180 deg).  The inner face carries the
    recess for the stiffener plate, which is glued in after casting together with the doubler on its centre
    (build_key_stiffener): the doubler presses the switch, so the switch force reaches the plate directly."""
    x = p.X_next if x is None else x
    sx, sy, sr = p.side_key
    y = p.key_y
    zs = p.Z_seat
    fw = p.flange_side
    cap = rrect_z(x - sx / 2, x + sx / 2, y - sy / 2, y + sy / 2, p.side_face_z, zs + 0.01, sr)
    fl = rrect_z(x - sx / 2 - fw, x + sx / 2 + fw, y - sy / 2 - fw, y + sy / 2 + fw, zs, zs + p.flange_t, sr + fw)
    k = cap.union(fl)
    k = k.faces("<Z").edges().fillet(0.2)
    k = k.union(chevron_solid(p, x, pointing))
    if recess:
        k = k.cut(plate_recess_solid(p, x))
    return k.translate((0, 0, rest)) if rest else k


def plate_recess_solid(p, x=None):
    """the recess of the side key's inner face: plate outline + clearance, floor plate_glue below the plate"""
    x = p.X_next if x is None else x
    rx, ry, rr = p.plate_recess
    return rrect_z(x - rx / 2, x + rx / 2, p.key_y - ry / 2, p.key_y + ry / 2, p.stiff_z0 - p.plate_glue,
                   p.Z_seat + p.flange_t + 1.0, rr)


def stiffener_outline(p, x=0.0, y=0.0):
    """corner points of the stiffener plate: rectangle with the four corners clipped at 45 deg"""
    w, ln, t, c = p.stiffener
    hw, hl = w / 2, ln / 2
    return [(x - hw + c, y - hl), (x + hw - c, y - hl), (x + hw, y - hl + c), (x + hw, y + hl - c),
            (x + hw - c, y + hl), (x - hw + c, y + hl), (x - hw, y + hl - c), (x - hw, y - hl + c)]


def build_key_stiffener(p, x=None, rest=0.0, pieces=False):
    """stiffener of a side key: flat plate cut from 0.3 mm stainless steel shim (corners clipped 45 deg) and the
    doubler square of the same shim glued on its centre; both glued into the recess of the key's inner face after
    casting.  pieces=True -> (plate, doubler) as two solids, otherwise their union (the glued stiffener)"""
    x = p.X_next if x is None else x
    w, ln, t, c = p.stiffener
    z0 = p.stiff_z0
    plate = cq.Workplane("XY", origin=(0, 0, z0)).polyline(stiffener_outline(p, x, p.key_y)).close().extrude(t)
    dx, dy, dt = p.doubler
    doub = rbox(x - dx / 2, x + dx / 2, p.key_y - dy / 2, p.key_y + dy / 2, z0 + t, z0 + t + dt)
    if pieces:
        return [s.translate((0, 0, rest)) if rest else s for s in (plate, doub)]
    s = plate.union(doub)
    return s.translate((0, 0, rest)) if rest else s


# ---- key board stand-in (until the real STEP exists) and bought parts
def build_kb_standin(p, pogo_state="work"):
    """KB stand-in (spec section 4): board, switches (body + actuator), ring LEDs, pogo pins, screws.
    pogo_state: 'work' (plunger to the main board), 'free' (free height, during assembly)"""
    d = {}
    z0, z1 = p.kb_z0, p.kb_z1
    b = (cq.Workplane("XY", origin=(0, 0, z0))
         .placeSketch(rrect_sketch(p.kb_x0, p.kb_x1, -p.kb_y, p.kb_y, p.kb_r)).extrude(p.kb_t))
    for (x, y) in p.kb_holes:
        b = b.cut(cyl_z(x, y, p.kb_hole_d, z0 - 1, z1 + 1))
    d["kb"] = b
    bx, by = p.sw_body
    zs0, zs1 = z0 - p.smt_standoff, z1 + p.smt_standoff       # seating planes of the bottom / top SMD parts
    for nm, x, along in (("kb_sw1", p.X_main, "X"), ("kb_sw2", p.X_next, "Y"), ("kb_sw3", p.X_prev, "Y")):
        hx, hy = (bx / 2, by / 2) if along == "X" else (by / 2, bx / 2)
        d[nm] = rbox(x - hx, x + hx, p.key_y - hy, p.key_y + hy, zs0 - p.sw_body_h, zs0)
        d[nm + "_act"] = cyl_z(x, p.key_y, p.sw_act_d, p.Z_sw_tip, zs0 - p.sw_body_h + 0.01)
    s = p.led_size / 2
    for nm, yy in (("kb_led3", p.led_y), ("kb_led4", -p.led_y)):
        d[nm] = rbox(p.X_main - s, p.X_main + s, yy - s, yy + s, p.Z_led_face, zs0)
    (bd0, bh0), (bd, bh) = p.pogo_base, p.pogo_barrel
    ztip = p.Z_pcb_bot if pogo_state == "work" else zs1 + p.pogo_free
    for i, (x, y) in enumerate(p.pogo_pins):
        d["kb_pogo%d" % (i + 1)] = cyl_z(x, y, bd0, zs1, zs1 + bh0).union(cyl_z(x, y, bd, zs1 + bh0 - 0.01, zs1 + bh))
        d["kb_pogo%d_pl" % (i + 1)] = cyl_z(x, y, p.pogo_plunger_d, zs1 + bh - 0.01, ztip)
    hd, hk = p.kb_screw_head
    for i, (x, y) in enumerate(p.kb_holes):
        d["kb_screw%d" % (i + 1)] = cyl_z(x, y, hd, z1, z1 + hk).union(cyl_z(x, y, 1.2, p.kb_screw_tip_z, z1 + 0.01))
    return d


KB_PARTS_SWITCHES = ("kb_sw1", "kb_sw2", "kb_sw3", "kb_sw1_act", "kb_sw2_act", "kb_sw3_act")


CELL_CASES = ("f15_min", "nominal", "f15_max", "alt_min", "alt_max", "max")
CELL_CASE_NAMES = {"f15_min": "F15 at its lower limits", "nominal": "F15 nominal", "f15_max": "F15 at its upper limits",
                   "alt_min": "K10 at its lower limits", "alt_max": "K10 at its upper limits",
                   "max": "largest flat-top 14500 the bay takes"}
CHANNEL_YZ = (-6.6, 3.6)        # lower -Y corner channel of the bay: the rear (BAT-) joint and its wire
FRONT_JOINT_YZ = (-5.8, 6.6)    # front (BAT+) strip tab and joint, in the antenna-spacer rebate


def cell_case(p, case="nominal"):
    """(d, length) of a cell checked in the bay"""
    if case == "nominal":
        return p.cell_d, p.cell_len
    if case == "f15_max":
        return p.cell_d + p.cell_d_tol, p.cell_len + p.cell_len_tol
    if case == "f15_min":
        return p.cell_d - p.cell_d_tol, p.cell_len - p.cell_len_tol
    d, ln, td, tl = p.cell_alt
    if case == "alt_max":
        return d + td, ln + tl
    if case == "alt_min":
        return d - td, ln - tl
    if case == "max":
        return p.cell_max
    raise ValueError(case)


def cell_centre_z(p, d):
    """axis height of a cell of diameter d resting on the two rails (polyimide tape on them)"""
    r = d / 2
    return p.floor + p.rail_h + p.cell_tape + math.sqrt(r * r - p.rail_y ** 2)


def cell_x0(p):
    """front end of the cell can: behind the front nickel strip (cell_end)"""
    return p.X_batt0 + p.cell_end


def cell_solid(p, case="nominal"):
    d, ln = cell_case(p, case)
    zc = cell_centre_z(p, d)
    c = cyl_x(0.0, zc, d, cell_x0(p), cell_x0(p) + ln)
    return c.faces("<X or >X").edges().chamfer(0.4)


def cell_parts(p, case="nominal"):
    """the cell as installed (pictures, fit check): the can; the front nickel strip (0.2, across the front face and
    bent forward into the antenna-spacer rebate, the BAT+ joint on it there); the rear strip (across the rear face,
    bent into the lower -Y corner channel of the bay, the BAT- joint on it there)"""
    d, ln = cell_case(p, case)
    zc = cell_centre_z(p, d)
    x0, x1 = cell_x0(p), cell_x0(p) + ln
    w = 3.0
    out = {"cell": cell_solid(p, case)}

    def band(xs, yt, zt):
        ang = math.degrees(math.atan2(zt - zc, yt))
        run = math.hypot(yt, zt - zc)
        return (cq.Workplane("YZ", origin=(xs, 0, zc)).center(run / 2, 0).rect(run, w).extrude(0.2)
                .rotate((xs, 0, zc), (xs + 1, 0, zc), ang)), ang
    # front: tab forward into the rebate (horizontal, 2.0 wide), joint on it
    yf, zf = FRONT_JOINT_YZ
    b, _ = band(x0 - 0.2, yf, zf)
    tab = rbox(x0 - 2.6, x0, yf - 1.0, yf + 1.0, zf - 0.2, zf)
    out["cell_strip_front"] = b.union(tab)
    out["cell_joint_front"] = cq.Workplane().add(cq.Solid.makeSphere(0.9, cq.Vector(x0 - 1.6, yf, zf + 0.6),
                                                                      angleDegrees1=-90, angleDegrees2=90))
    # rear: tab across the lower -Y corner channel (tangential, 2.4 wide), joint on it
    yj, zj = CHANNEL_YZ
    b, ang = band(x1, yj, zj)
    tab = rbox(x1 - 2.2, x1 + 0.2, yj - 0.1, yj + 0.1, zj - 1.2, zj + 1.2)
    tab = tab.rotate((0, yj, zj), (1, yj, zj), ang - 180.0)
    out["cell_strip_rear"] = b.union(tab)
    out["cell_joint_rear"] = cq.Workplane().add(cq.Solid.makeSphere(1.0, cq.Vector(x1 - 1.4, yj, zj),
                                                                     angleDegrees1=-90, angleDegrees2=90))
    return out


CELL_PARTS = ("cell", "cell_strip_front", "cell_strip_rear", "cell_joint_front", "cell_joint_rear")


def cell_pads(p, case="nominal"):
    """foam strip under the lid (compressed to the gap over the cell) and the foam pad at the tail end (compressed
    to the length left), for the pictures"""
    d, ln = cell_case(p, case)
    zc = cell_centre_z(p, d)
    t0, w = p.top_pad
    x0, x1 = cell_x0(p), cell_x0(p) + ln
    top = rbox(x0 + 1.5, x1 - 1.5, -w / 2, w / 2, zc + d / 2 + 0.02, p.Z_ceil - 0.02)
    end = rbox(x1 + 0.22, p.X_batt1 - 0.02, -4.0, 4.0, zc - 4.0, zc + 4.0)
    return {"cell_pad_top": top, "cell_pad_end": end}


def pcb_outline(p):
    x0, x1, y, c = p.X_pcb0, p.X_pcb1, p.Y_pcb, p.pcb_chamfer
    return [(x0 + c, -y), (x1, -y), (x1, y), (x0 + c, y), (x0, y - c), (x0, -y + c)]


def build_dummies(p):
    """stand-ins for the main board and the bought parts (fit check + pictures)"""
    d = {}
    zt, zb = p.Z_pcb_top, p.Z_pcb_bot
    d["pcb"] = cq.Workplane("XY").workplane(offset=zb).polyline(pcb_outline(p)).close().extrude(p.pcb_t)
    x0m = p.X_pcb1 - p.mod_onboard
    d["module"] = rbox(x0m, p.X_ant1, p.mod_y - p.mod_w / 2, p.mod_y + p.mod_w / 2, zt, zt + 0.8)
    d["module_can"] = rbox(x0m + 0.4, p.X_pcb1 - 0.2, p.mod_y - p.mod_w / 2 + 0.3,
                           p.mod_y + p.mod_w / 2 - 0.3, zt + 0.8, zt + p.mod_h)
    d.update(cell_parts(p))
    d.update(cell_pads(p))
    d["optic_holder"], d["optic_lens"] = build_optic(p)
    xb = p.x_led_board
    d["mcpcb"] = cyl_x(p.Y_w, p.Z_axis, p.mcpcb_d, xb, xb + p.mcpcb_t)
    a = p.sst_size / 2
    d["led"] = rbox(xb - p.sst_h, xb, p.Y_w - a, p.Y_w + a, p.Z_axis - a, p.Z_axis + a)
    d["laser"] = cyl_x(p.Y_l, p.Z_las, p.las_d, p.las_recess, p.las_recess + p.las_len)
    yf = -p.Y_pcb
    d["usb"] = rbox(p.X_usb - 4.47, p.X_usb + 4.47, yf, yf + 7.35, zb - 3.21, zb, 1.2, axis="Y")
    ytip2 = p.Y_pcb + p.s2_knob_out
    yb2 = ytip2 - p.s2_knob_len
    d["s2"] = rbox(p.X_s2 - 3.35, p.X_s2 + 3.35, yb2 - 2.6, yb2, zt, zt + 1.4)
    d["s2_knob"] = rbox(p.X_s2 - 1.4, p.X_s2 + 1.4, yb2, ytip2, zt + p.s2_knob_z - 0.5, zt + p.s2_knob_z + 0.5)
    d["L1"] = rbox(_dx(11.0), _dx(15.0), -1.5, 2.5, zt, zt + 2.0)
    return d


PCB_MOUNTED = ("pcb", "module", "module_can", "usb", "s2", "s2_knob", "L1")


def pad_solid(p):
    x0, x1, y0, y1 = p.boss_box
    return rrect_z(x0, x1, y0, y1, p.can_top_z, p.Z_ceil - p.boss_h, p.boss_r)


def pad2_solid(p):
    """front rubber pad (silicone sheet pad2_t0, compressed to pad2_gap) between the front lid boss and the board"""
    x0, x1, y0, y1 = p.boss2_box
    return rrect_z(x0, x1, y0, y1, p.Z_pcb_top, p.Z_pcb_top + p.pad2_gap, p.boss2_r)


def lid_screws(p):
    """four countersunk M1.6 screws in the lid"""
    out = []
    for k, (x, y) in enumerate(((p.screw_x_front, -p.screw_dy), (p.screw_x_front, p.screw_dy),
                                (p.X_screw_back, -p.screw_dy), (p.X_screw_back, p.screw_dy))):
        cone = cq.Solid.makeCone(0.8, 1.5, 0.7, pnt=cq.Vector(x, y, p.H - 0.7))
        shank = cq.Solid.makeCylinder(0.8, p.lid_screw_len - 0.7, pnt=cq.Vector(x, y, p.H - p.lid_screw_len))
        slot = cq.Solid.makeBox(2.4, 0.45, 0.5, pnt=cq.Vector(x - 1.2, y - 0.225, p.H - 0.45))
        slot2 = cq.Solid.makeBox(0.45, 2.4, 0.5, pnt=cq.Vector(x - 0.225, y - 1.2, p.H - 0.45))
        out.append(("ref_lid_screw_%d" % (k + 1), cone.fuse(shank).cut(slot).cut(slot2)))
    return out


def laser_set_screw(p):
    """the M1.6 x 5 set screw of the laser module, installed: tip on the module, hex socket (0.7) at the top, 0.79 below
    the head-block top (under the lid)"""
    x, y = p.las_set
    z0, rp = p.las_set_tip_z, p.las_set_point / 2
    point = cq.Solid.makeCone(rp, 0.8, 0.8 - rp, pnt=cq.Vector(x, y, z0))           # 45 deg chamfer to the point
    body = cq.Solid.makeCylinder(0.8, p.las_set_len - (0.8 - rp), pnt=cq.Vector(x, y, z0 + 0.8 - rp))
    sock = (cq.Workplane("XY", origin=(0, 0, z0 + p.las_set_len - 0.8)).center(x, y)
            .polygon(6, 0.7 / math.cos(math.pi / 6)).extrude(0.81).val())
    return point.fuse(body).cut(sock)


def kb_screws_detail(p):
    """two M1.6 pan head screws (with a cross recess) for the pictures"""
    out = []
    hd, hk = p.kb_screw_head
    for k, (x, y) in enumerate(p.kb_holes):
        head = cq.Solid.makeCylinder(hd / 2, hk, pnt=cq.Vector(x, y, p.kb_z1))
        head = head.fillet(0.3, [e for e in head.Edges() if e.Center().z > p.kb_z1 + hk - 0.01])
        shank = cq.Solid.makeCylinder(0.8, p.kb_screw_len - p.kb_t, pnt=cq.Vector(x, y, p.kb_screw_tip_z))
        s1 = cq.Solid.makeBox(1.8, 0.4, 0.5, pnt=cq.Vector(x - 0.9, y - 0.2, p.kb_z1 + hk - 0.45))
        s2 = cq.Solid.makeBox(0.4, 1.8, 0.5, pnt=cq.Vector(x - 0.2, y - 0.9, p.kb_z1 + hk - 0.45))
        out.append(("ref_kb_screw_%d" % (k + 1), head.fuse(shank).cut(s1).cut(s2)))
    return out


# --------------------------------------------------------------------------
# PCB interface (read by the KiCad tools); the main board keeps its v0.6 positions (PCB frame: see to_pcb_frame)
# --------------------------------------------------------------------------
MAIN_BOARD_KEYS = ("J1_usb", "S2_interlock", "U4_module", "pcb", "keepout_bottom", "trough_y", "trough_exceptions")


def component_positions(p):
    zt, zb = p.Z_pcb_top, p.Z_pcb_bot
    hd, hk = p.kb_screw_head
    out = {
        "J1_usb": {"x": p.X_usb, "face_y": -p.Y_pcb, "side": "B", "z_centre": p.Z_usb,
                   "note": "TYPE-C-31-M-12 on the bottom side, mating face flush with the PCB edge"},
        "buttons": {
            "board": "KB",
            "part": "Alps SKRKAEE020 (LCSC C115357), KiCad Button_Switch_SMD:SW_Push_SPST_NO_Alps_SKRK",
            "side": "KB bottom face", "z_kb_bottom": p.kb_z0, "z_actuator_tip": round(p.Z_sw_tip, 4),
            "note": "v0.7: the three switches sit on the bottom face of the key board (KB), actuator pointing down "
                    "at the keys; rot 0 = the two pads along housing X, rot 90 = pads along housing Y. "
                    "The main board does not carry them any more.",
            "SW1_main": {"x": p.X_main, "y": p.key_y, "rot": 0},
            "SW2_next": {"x": p.X_next, "y": p.key_y, "rot": 90},
            "SW3_prev": {"x": p.X_prev, "y": p.key_y, "rot": 90},
        },
        "ring_leds": {
            "board": "KB",
            "part": "NH-B1010RGBT-HF (LCSC C2874113)",
            "side": "KB bottom face", "rot": 0,
            "LED3": {"x": p.X_main, "y": p.key_y + p.led_y},
            "LED4": {"x": p.X_main, "y": p.key_y - p.led_y},
            "note": "emit downwards into the top face of the clear main key (key top Z %.2f at rest, LED face Z %.2f "
                    "for the %.2f mm worst-case LED height)" % (p.main_top_z, p.Z_led_face, p.ring_led_h),
        },
        "S2_interlock": {"x": p.X_s2, "knob_tip_y": p.Y_pcb + p.s2_knob_out, "side": "F",
                         "note": "PCM12-class slide, knob towards +Y into the wall slot"},
        "U4_module": {"x_onboard_end": p.X_pcb1, "y": p.mod_y, "side": "F",
                      "note": "ESP32-C3-MINI-1, antenna overhangs the rear edge by %.1f mm" % (p.mod_len - p.mod_onboard)},
        "pcb": {"x0": p.X_pcb0, "x1": p.X_pcb1, "y_minus": -p.Y_pcb, "y_plus": p.Y_pcb, "z_bottom": zb, "t": p.pcb_t},
        "keepout_bottom": [
            {"what": "laser module tail", "x0": p.X_pcb0 - 1, "x1": p.las_keepout_x,
             "y0": p.Y_l - p.las_d / 2 - 0.3, "y1": p.Y_pcb + 1},
        ],
        "keepout_top": ([{"what": "front hold-down pad", "x0": p.boss2_box[0] - 0.05, "x1": p.boss2_box[1] + 0.05,
                          "y0": p.boss2_box[2] - 0.05, "y1": p.boss2_box[3] + 0.05,
                          "note": "no top-side components inside; copper, vias and solder mask allowed"}]
                        if p.front_boss else []),
        "keepout_bottom_circles": [],
        "trough_y": [-(p.inner_half - p.ledge_w) + 0.15, p.inner_half - p.ledge_w - 0.15],
        "trough_exceptions": [
            {"what": "USB-C (no ledge)", "x0": p.minusY_open[0][0], "x1": p.minusY_open[0][1], "side": "-Y"},
            {"what": "laser (no ledge)", "x0": p.X_pcb0 - 1, "x1": p.las_keepout_x, "side": "+Y"},
        ],
        "rf_window": {"x0": p.rfw_box[0], "x1": p.rfw_box[1], "half_y": p.rfw_box[2]},
        "max_height_top": round(p.Z_ceil - zt - 0.2, 4),
        "max_height_top_note": "under the lid plate; within %.2f of the board edges (|Y| > %.2f) the lid's inner edge "
                               "limits the parts to Z %.2f (%.2f above the board)" % (
                                   p.Y_pcb - inner_pts(p, 0.2, "lid")[0][0], inner_pts(p, 0.2, "lid")[0][0],
                                   p.Z_lid - 0.2, p.Z_lid - 0.2 - zt),
        "max_height_bottom": round(zb - p.floor - 0.3, 4),
        "kb_zone": {"x0": p.kb_x0, "x1": p.kb_x1, "y0": -p.kb_y, "y1": p.kb_y, "z_kb_top": p.kb_z1,
                    "z_pogo_barrel_top": round(p.kb_z1 + p.smt_standoff + p.pogo_barrel[1], 4), "z_screw_head_top": round(p.kb_z1 + hk, 4),
                    "pogo_pins": [list(q) for q in p.pogo_pins],
                    "note": "bottom-side parts of the main board above the key board must clear the KB top-face parts "
                            "(pogo barrels, screw heads, resistors); J6 target pads right above the pogo pins"},
        "led_wire_top": {"y": round(led_wire_hole_yz(p)[0][0], 4), "z": round(led_wire_hole_yz(p)[0][1], 4),
                         "x_exit": led_wire_hole_x_end(p)[0], "d": p.ledwire_d},
        "led_wire_bottom": {"y": round(led_wire_hole_yz(p)[1][0], 4), "z": round(led_wire_hole_yz(p)[1][1], 4),
                            "x_exit": led_wire_hole_x_end(p)[1], "d": p.ledwire_d},
        "front_screw_tips_z": p.Z_lid - p.m16_drill,
    }
    return out


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------
def _shape(x):
    return x.val() if isinstance(x, cq.Workplane) else x


def _vol(a, b):
    try:
        r = _shape(a).intersect(_shape(b))
        return r.Volume() if r is not None else 0.0
    except Exception:
        return 0.0


def _dist(a, b):
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    sa, sb = _shape(a), _shape(b)
    d = BRepExtrema_DistShapeShape(sa.wrapped, sb.wrapped)
    d.Perform()
    return d.Value() if d.IsDone() else float("nan")


def _compound(items):
    shapes = []
    for it in items:
        shapes += solids_of(it)
    return cq.Compound.makeCompound(shapes)


# --------------------------------------------------------------------------
# machining kits.  JLCCNC refuses plastic parts below 30 x 20 x 8 mm ("special shapes"), so the PMMA keys and the
# POM parts are ordered as one piece each: a frame with one through-pocket per part, every part hanging on small
# tabs on a hidden face that locates nothing.  A 3-axis mill reaches every face in two setups, from the top
# (kit +Z) and from the bottom; the tabs of a kit lie in one plane.  Cut the tabs, file flush.
# --------------------------------------------------------------------------
def _r4(v):
    return [round(q, 4) + 0.0 for q in v]


def _kit_place(wp, steps):
    """apply ("t", (dx, dy, dz)) / ("rx" | "ry" | "rz", degrees) steps in order (rotations about the origin)"""
    for k, v in steps:
        if k == "t":
            wp = wp.translate(v)
        else:
            wp = wp.rotate((0, 0, 0), {"rx": (1, 0, 0), "ry": (0, 1, 0), "rz": (0, 0, 1)}[k], v)
    return wp


def _kit_tab(px, py, nx, ny, z0, z1, w, length, ov=0.05):
    """horizontal tab from the face point (px, py) along the outward normal (nx, ny): `length` long plus ov into
    the part and into the frame, w wide, from z0 to z1"""
    b = cq.Workplane("XY").box(length + 2 * ov, w, z1 - z0, centered=(False, True, False)).translate((-ov, 0, z0))
    ang = math.degrees(math.atan2(ny, nx))
    if abs(ang) > 1e-9:
        b = b.rotate((0, 0, 0), (0, 0, 1), ang)
    return b.translate((px, py, 0))


def _kit_cell(cx, cy, hx, hy, r, h):
    """through-pocket of one kit cell: rounded rectangle (half sizes hx, hy, corner r) or a circle (hx = hy = r)"""
    if abs(hx - r) < 1e-9 and abs(hy - r) < 1e-9:
        return cyl_z(cx, cy, 2 * r, -1.0, h + 1.0)
    return rrect_z(cx - hx, cx + hx, cy - hy, cy + hy, -1.0, h + 1.0, r)


def _kit_assemble(size, cells, parts, tabs):
    X, Y, h = size
    frame = cq.Workplane("XY").box(X, Y, h, centered=False)
    for c in cells:
        frame = frame.cut(c)
    kit = frame
    for s in list(parts) + list(tabs):
        kit = kit.union(s)
    return kit, frame


def build_pmma_kit(p, n=3):
    """n clear PMMA main keys (1 + 2 spares) in a frame -> (kit, info).  Each key lies with its outer face up
    (kit +Z), centred in the kit height, and hangs on three tabs on the edge of its flange (inside the housing;
    not a locating face: the cap locates the key in its opening, the flange underside on the floor seat).  The tab
    is the full flange thickness high, so the tab plane is the flange."""
    hk, g, wall = p.kit_h_pmma, p.kit_gap, p.kit_wall
    tw = p.kit_tab[0]
    mx, my, mr = p.main_key
    hf, rf = mx / 2 + p.flange_main, mr + p.flange_main      # flange half size and corner radius
    kh = p.main_top_z - p.main_face_z
    dz = (hk - kh) / 2 + p.main_top_z                         # outer face up: kit z = dz - housing z
    cell = 2 * (hf + g)
    X = (n + 1) * wall + n * cell
    Y = max(cell + 2 * wall, p.kit_min[1] + 2.0)
    zt0, zt1 = p.Z_seat, p.Z_seat + p.flange_t
    key = build_key_main(p)
    parts, tabs, cells, places = [], [], [], []
    for i in range(n):
        cx, cy = wall + cell / 2 + i * (cell + wall), Y / 2
        st = [("t", (-p.X_main, -p.key_y, 0)), ("rx", 180), ("t", (cx, cy, dz))]
        parts.append(_kit_place(key, st))
        for (px, py, nx, ny) in ((p.X_main, p.key_y + hf, 0, 1), (p.X_main, p.key_y - hf, 0, -1),
                                 (p.X_main + hf, p.key_y, 1, 0)):
            tabs.append(_kit_place(_kit_tab(px, py, nx, ny, zt0, zt1, tw, g), st))
        cells.append(_kit_cell(cx, cy, hf + g, hf + g, rf + g, hk))
        places.append({"part": "main key %d" % (i + 1), "file": "FlashKa_key_main.step", "centre_xy": _r4([cx, cy]),
                       "z": _r4([dz - p.main_top_z, dz - p.main_face_z]), "orientation": "outer face up (kit +Z)",
                       "tabs": "3: middle of the +Y, -Y and +X flange edges (housing frame), %g x %g, %g long" % (
                           tw, p.flange_t, g)})
    kit, frame = _kit_assemble((X, Y, hk), cells, parts, tabs)
    info = {"file": "FlashKa_pmma_kit.step", "material": "clear cast PMMA (acrylic, not extruded)",
            "size": _r4([X, Y, hk]), "gap": g, "wall": wall, "tab": [tw, p.flange_t], "tab_length": g,
            "tab_plane_z": _r4([dz - zt1, dz - zt0]), "n_parts": n, "n_tabs": len(tabs), "parts": places,
            "setups": "top (kit +Z): outer face, frosted ring, edge break, cap below the flange; bottom: light-input "
                      "face, switch pocket and nub, cap above the flange; the gaps from each side to the tab plane"}
    return kit, info, {"parts": parts, "tabs": tabs, "frame": frame, "cells": cells}


def build_pom_kit(p, texture=True):
    """one set of POM-C parts plus a spare lid RF insert in a frame -> (kit, info).  Row A: two lid RF inserts,
    textured face up, tabs on the flange edge (free in the pocket: rfw_flange_clear) flush with the flange underside.
    Row B: the antenna spacer upright with its floor plug up, tabs on its two side faces (clear of the cavity walls;
    the plug locates the spacer).  One tab plane.  (The v0.6 spacer ring went with the glass window.)"""
    hk, g, gt, wall = p.kit_h_pom, p.kit_gap, p.kit_gap_tall, p.kit_wall
    tw, th = p.kit_tab
    # antenna spacer: upright, turned over (floor plug up); its -Y side face lies between the 0.7 bottom chamfer
    # (build_antenna_spacer) and the floor of the cell-wire rebate: the tab sits in the middle of it
    asp = build_antenna_spacer(p, texture=texture)
    bb = asp.val().BoundingBox()
    xs0, xs1, ys = bb.xmin, bb.xmax, bb.ymax
    dzs = (hk - (bb.zmax - bb.zmin)) / 2 + bb.zmax          # kit z = dzs - housing z
    za = ((p.floor + 0.05 + 0.7) + cell_wire_channel(p)[2]) / 2 - th / 2
    kt0, kt1 = dzs - za - th, dzs - za                      # tab plane of the kit
    # lid RF inserts: textured face up, flange underside on the tab plane
    x0, x1, hy = p.rfw_box
    fo = p.rfw_flange - p.rfw_flange_clear
    zb = p.Z_ceil - p.rfw_flange_drop
    dzr = kt0 - zb
    xc = (x0 + x1) / 2
    ins_cell = (hy + fo + g, (x1 - x0) / 2 + fo + g)       # kit half sizes (the insert is turned 90 deg)
    asp_cell = (ys + gt, (xs1 - xs0) / 2 + gt)
    rowA, rowB = 2 * ins_cell[1], 2 * asp_cell[1]
    X = max(3 * wall + 4 * ins_cell[0], 2 * wall + 2 * asp_cell[0])
    Y = 3 * wall + rowA + rowB
    cyA, cyB = wall + rowA / 2, 2 * wall + rowA + rowB / 2
    parts, tabs, cells, places = [], [], [], []
    ins = build_rf_window(p, texture=texture)
    for i, cx in enumerate((wall + ins_cell[0], 2 * wall + 3 * ins_cell[0])):
        st = [("t", (-xc, 0, 0)), ("rz", 90), ("t", (cx, cyA, dzr))]
        parts.append(_kit_place(ins, st))
        for (px, py, nx, ny) in ((x0 - fo, 0, -1, 0), (x1 + fo, 0, 1, 0), (xc, hy + fo, 0, 1)):
            tabs.append(_kit_place(_kit_tab(px, py, nx, ny, zb, zb + th, tw, g), st))
        cells.append(_kit_cell(cx, cyA, ins_cell[0], ins_cell[1], p.rfw_r + fo + g, hk))
        places.append({"part": "lid RF window insert" + (" (spare)" if i else ""), "file": "FlashKa_rf_window.step",
                       "centre_xy": _r4([cx, cyA]), "z": _r4([dzr + zb, dzr + p.H - p.pan_depth]),
                       "orientation": "textured face up (kit +Z), long side along kit X",
                       "tabs": "3: middle of both long flange edges and of one short flange edge, %g x %g, flush with "
                               "the flange underside, %g long" % (tw, th, g)})
    cx = X / 2
    st = [("t", (-(xs0 + xs1) / 2, 0, 0)), ("rx", 180), ("rz", 90), ("t", (cx, cyB, dzs))]
    parts.append(_kit_place(asp, st))
    for (px, py, nx, ny) in ((xs1 - 1.0, ys, 0, 1), (xs1 - 3.75, ys, 0, 1), (xs1 - 2.35, -ys, 0, -1)):
        tabs.append(_kit_place(_kit_tab(px, py, nx, ny, za, za + th, tw, gt), st))
    cells.append(_kit_cell(cx, cyB, asp_cell[0], asp_cell[1], 0.4 + gt, hk))
    places.append({"part": "antenna spacer", "file": "FlashKa_antenna_spacer.step", "centre_xy": _r4([cx, cyB]),
                   "z": _r4([dzs - bb.zmax, dzs - bb.zmin]), "orientation": "floor plug up (kit +Z), long side along kit X",
                   "tabs": "3: two on the +Y side face, one on the -Y side face (housing frame), %g x %g, %g long" % (
                       tw, th, gt)})
    kit, frame = _kit_assemble((X, Y, hk), cells, parts, tabs)
    info = {"file": "FlashKa_pom_kit.step", "material": "POM-C (acetal copolymer), black",
            "size": _r4([X, Y, hk]), "gap": g, "gap_spacer": gt, "wall": wall, "tab": [tw, th],
            "tab_plane_z": _r4([kt0, kt1]), "n_parts": len(parts), "n_tabs": len(tabs), "parts": places,
            "not_in_the_kit": "laser sleeve (option, only for a laser module thinner than 6 mm): its slit along the "
                              "axis needs a side setup; single file FlashKa_laser_sleeve.step",
            "setups": "top (kit +Z): insert faces with the texture, spacer floor plug with the texture and its bottom "
                      "chamfers; bottom: insert flange undersides, spacer top side (U, rebate, tall wall); the gaps "
                      "from each side to the tab plane"}
    return kit, info, {"parts": parts, "tabs": tabs, "frame": frame, "cells": cells}


def kit_two_setup_check(kit, eps=0.01, per_face=4):
    """every face of the kit must be reachable by a 3-axis mill from the top (+Z) or the bottom (-Z): from points
    on each face (the centres of its largest mesh triangles projected onto the exact surface), moved eps along the
    outward surface normal, a ray along +Z (face looking up), -Z (looking down) or either (vertical face) must
    leave the kit without hitting it."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
    from OCP.GeomLProp import GeomLProp_SLProps
    from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
    from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS
    from OCP.gp import gp_Dir, gp_Lin, gp_Pnt
    shape = _shape(kit).wrapped
    BRepMesh_IncrementalMesh(shape, 0.05, False, 0.35, True)
    inter = IntCurvesFace_ShapeIntersector()
    inter.Load(shape, 1e-7)

    def clear(o, dz):
        inter.Perform(gp_Lin(gp_Pnt(*o), gp_Dir(0, 0, dz)), 0.0, 1e4)
        return inter.NbPnt() == 0

    ex = TopExp_Explorer(shape, TopAbs_FACE)
    n_faces = n_pts = 0
    blocked = []
    while ex.More():
        f = TopoDS.Face_s(ex.Current())
        ex.Next()
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(f, loc)
        if tri is None:
            continue
        n_faces += 1
        tr = loc.Transformation()
        rev = f.Orientation() == TopAbs_REVERSED
        cand = []
        for i in range(1, tri.NbTriangles() + 1):
            a, b, c = tri.Triangle(i).Get()
            pa, pb, pc = (tri.Node(k).Transformed(tr) for k in (a, b, c))
            u = (pb.X() - pa.X(), pb.Y() - pa.Y(), pb.Z() - pa.Z())
            v = (pc.X() - pa.X(), pc.Y() - pa.Y(), pc.Z() - pa.Z())
            nrm = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
            ar = math.sqrt(sum(q * q for q in nrm))
            if ar < 1e-10:
                continue
            nrm = tuple(q / ar * (-1 if rev else 1) for q in nrm)
            cen = ((pa.X() + pb.X() + pc.X()) / 3, (pa.Y() + pb.Y() + pc.Y()) / 3, (pa.Z() + pb.Z() + pc.Z()) / 3)
            cand.append((ar, cen, nrm))
        cand.sort(key=lambda t: -t[0])
        surf = BRep_Tool.Surface_s(f)
        for ar, cen, nrm in cand[:per_face]:
            pr = GeomAPI_ProjectPointOnSurf(gp_Pnt(*cen), surf)
            if pr.NbPoints() > 0:                       # exact point and normal (the mesh lies inside curved faces)
                u, v = pr.LowerDistanceParameters()
                lp = GeomLProp_SLProps(surf, u, v, 1, 1e-7)
                if lp.IsNormalDefined():
                    q, d = pr.NearestPoint(), lp.Normal()
                    sg = -1 if rev else 1
                    nn = (sg * d.X(), sg * d.Y(), sg * d.Z())
                    if sum(nn[k] * nrm[k] for k in range(3)) > 0.5:
                        cen, nrm = (q.X(), q.Y(), q.Z()), nn
            n_pts += 1
            o = tuple(cen[k] + eps * nrm[k] for k in range(3))
            if nrm[2] > 0.1:
                ok = clear(o, 1)
            elif nrm[2] < -0.1:
                ok = clear(o, -1)
            else:
                ok = clear(o, 1) or clear(o, -1)
            if not ok:
                blocked.append({"point": [round(q, 3) for q in cen], "normal": [round(q, 3) for q in nrm]})
    return {"faces": n_faces, "points": n_pts, "blocked": len(blocked), "blocked_points": blocked[:20]}


def kit_checks(p, kit, info, pieces, singles):
    """bounding box against the JLCCNC minimum, one valid solid, gap part -> frame, volume balance, two setups.
    singles: {part file: single-part solid} for the volume comparison"""
    s = _shape(kit)
    bb = s.BoundingBox()
    size = sorted([bb.xlen, bb.ylen, bb.zlen], reverse=True)
    out = {"bbox_mm": [round(bb.xlen, 3), round(bb.ylen, 3), round(bb.zlen, 3)],
           "jlccnc_minimum_mm": list(p.kit_min),
           "bbox_ok": all(a >= b for a, b in zip(size, sorted(p.kit_min, reverse=True))),
           "solids": len(s.Solids()), "valid": s.isValid()}
    gaps = [_dist(prt, pieces["frame"]) for prt in pieces["parts"]]
    out["gap_part_to_frame_min_mm"] = round(min(gaps), 4)
    out["gap_part_to_frame_max_mm"] = round(max(gaps), 4)
    # every tab joins one part and the frame: the tabs (outside the part and the frame) plus the parts plus the frame
    vt = sum(_shape(t).Volume() - _vol(t, pieces["frame"]) - sum(_vol(t, q) for q in pieces["parts"])
             for t in pieces["tabs"])
    vparts = sum(_shape(q).Volume() for q in pieces["parts"])
    vexp = _shape(pieces["frame"]).Volume() + vparts + vt
    out["volume_mm3"] = round(s.Volume(), 2)
    out["volume_expected_mm3"] = round(vexp, 2)
    out["volume_ok"] = abs(s.Volume() - vexp) < 0.01
    out["parts_vs_single_files_mm3"] = [
        {"part": q["part"], "kit": round(_shape(prt).Volume(), 3),
         "single": round(_shape(singles[q["file"].split()[0]]).Volume(), 3)} for q, prt in zip(info["parts"], pieces["parts"])]
    out["two_setups"] = kit_two_setup_check(kit)
    out["ok"] = bool(out["bbox_ok"] and out["solids"] == 1 and out["valid"] and out["volume_ok"]
                     and out["two_setups"]["blocked"] == 0)
    return out


def housing_parts(p):
    """all housing parts in place (keys at rest on their seats)"""
    return {
        "FlashKa_tray": build_tray(p),
        "FlashKa_lid": build_lid(p),
        "FlashKa_rf_window": build_rf_window(p),
        "FlashKa_antenna_spacer": build_antenna_spacer(p),
        "FlashKa_key_main": build_key_main(p),
        "FlashKa_key_side": build_key_side(p, p.X_next, -1),
        "FlashKa_key_side_prev": build_key_side(p, p.X_prev, +1),
        "FlashKa_key_stiffener": build_key_stiffener(p, p.X_next),
        "FlashKa_key_stiffener_prev": build_key_stiffener(p, p.X_prev),
    }


def interference(parts, others, dy=0.0, movable=PCB_MOUNTED, skip=()):
    out = []
    for hn, h in parts.items():
        hb = _shape(h).BoundingBox()
        for dn, dm in others.items():
            if (hn, dn) in skip:
                continue
            moved = dm.translate((0, dy, 0)) if (dy and dn in movable) else dm
            mb = _shape(moved).BoundingBox()
            if hb.xmax < mb.xmin or mb.xmax < hb.xmin or hb.ymax < mb.ymin or mb.ymax < hb.ymin \
                    or hb.zmax < mb.zmin or mb.zmax < hb.zmin:
                continue
            v = _vol(h, moved)
            if v > 0.02:
                out.append((hn, dn, round(v, 3)))
    return out


def parts_interference(parts):
    out, names = [], list(parts)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            v = _vol(parts[a], parts[b])
            if v > 0.02:
                out.append((a, b, round(v, 3)))
    return out


def insertion_check(p, parts, dummies, kb_free, steps=12):
    """the main board goes in tilted about the X axis (+Y edge low) so that the S2 knob enters its slot first.
    Checked against the tray, the resting keys, the laser and the key board with the pogo pins at their free
    height: the board itself meets the six plunger tips in the last part of the stroke (it compresses them,
    by design); any other contact is a collision."""
    from OCP.gp import gp_Ax1, gp_Pnt, gp_Dir, gp_Trsf
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    pivot = (0.0, p.Y_pcb + p.s2_knob_out - 0.2, p.Z_pcb_top + p.s2_knob_z)
    against = {"tray": parts["FlashKa_tray"], "key_main": parts["FlashKa_key_main"],
               "key_next": parts["FlashKa_key_side"], "key_prev": parts["FlashKa_key_side_prev"],
               "laser": dummies["laser"]}
    against.update({k: v for k, v in kb_free.items()})
    top_side = ("module", "module_can", "L1", "s2", "s2_knob")     # above the board: the board shields them
    worst, plunger, first = [], [], None
    for k in range(steps + 1):
        ang = 9.0 * (1 - k / steps)
        tr = gp_Trsf()
        tr.SetRotation(gp_Ax1(gp_Pnt(*pivot), gp_Dir(1, 0, 0)), math.radians(-ang))
        for dn in PCB_MOUNTED:
            s = dummies[dn].val().wrapped
            m = cq.Workplane().add(cq.Shape.cast(BRepBuilderAPI_Transform(s, tr, True).Shape()))
            for hn, h in against.items():
                if hn.endswith("_pl") and dn in top_side:
                    continue
                v = _vol(h, m)
                if v > 2e-3:
                    if dn == "pcb" and hn.endswith("_pl"):
                        plunger.append((round(ang, 2), hn, round(v, 3)))
                        first = ang if first is None else max(first, ang)
                    else:
                        worst.append((round(ang, 2), dn, hn, round(v, 3)))
    return {"collisions": worst,
            "board reaches the plunger tips from (deg)": first,
            "board_on_plunger_tips (expected, compresses the pins)": sorted(set(x[1] for x in plunger))}


def key_stroke_check(p, parts, kb):
    """Press each key up (+Z): the nub must reach its own actuator after the free play, and nothing else may be
    touched before the switch reaches its full travel.  Rest distances larger than the whole stroke are safe;
    closer items are stepped through."""
    keys = (("main (SW1)", "FlashKa_key_main", None, "kb_sw1_act", p.pre_main),
            ("next (SW2)", "FlashKa_key_side", "FlashKa_key_stiffener", "kb_sw2_act", p.pre_side),
            ("previous (SW3)", "FlashKa_key_side_prev", "FlashKa_key_stiffener_prev", "kb_sw3_act", p.pre_side))
    res = {}
    for label, kn, sn, act, pre in keys:
        key = parts[kn].union(parts[sn]) if sn else parts[kn]
        stroke = pre + p.sw_travel
        d_act = _dist(key, kb[act])
        others = {k: v for k, v in kb.items() if k != act}
        for on in ("FlashKa_lid", "FlashKa_antenna_spacer"):
            others[on] = parts[on]
        for on in ("FlashKa_key_main", "FlashKa_key_side", "FlashKa_key_side_prev"):
            if on != kn:
                others[on] = parts[on]
        near, contacts = {}, []
        for on, o in others.items():
            d = _dist(key, o)
            near[on] = d
            if d <= stroke + 0.05:
                for k in range(1, 13):
                    st = stroke * k / 12 + 0.05 * k / 12
                    if _vol(key.translate((0, 0, st)), o) > 1e-4:
                        contacts.append((on, round(st, 3)))
                        break
        tray_hits = []
        for st in (0.05, stroke / 2, stroke):
            if _vol(key.translate((0, 0, st)), parts["FlashKa_tray"]) > 1e-4:
                tray_hits.append(round(st, 3))
        nearest = sorted(near.items(), key=lambda kv: kv[1])[:3]
        # full travel: the actuator pushed by the switch travel; the key top / pocket floor margins
        res[label] = {"free_play_mm (nub / doubler to actuator at rest)": round(d_act, 3),
                      "stroke_to_full_travel_mm": round(stroke, 3),
                      "contacts_before_full_travel": contacts,
                      "tray_contacts_while_pressed": tray_hits,
                      "nearest_other_items_at_rest_mm": [(n, round(d, 3)) for n, d in nearest]}
    # main key: pocket floor against a switch modelled as a full 2.0 mm box (if the real 3D model is a plain box)
    res["main: pocket floor below a full-height switch box at full travel (mm)"] = round(
        p.Z_sw_tip - (p.main_nub_z - p.nub_h + p.pre_main + p.sw_travel), 3)
    # side keys: no pocket; the doubler (under the switch body) against the body of the stand-in switch (1.6 tall over a
    # 0.4 actuator; the KiCad model of the SKRK: 1.5 over 0.5, checked in fit_pcb.py)
    z_body = p.kb_z0 - p.smt_standoff - p.sw_body_h
    res["side: doubler top below the switch body at full travel (mm)"] = round(
        z_body - (p.side_nub_z + p.pre_side + p.sw_travel), 3)
    res["side: plate top below the switch body at full travel (mm)"] = round(
        z_body - (p.stiff_z0 + p.stiffener[2] + p.pre_side + p.sw_travel), 3)
    return res


def key_tolerance_stack(p):
    """free play of the keys over the tolerance stack (nominal, worst case, RSS)"""
    out = {}
    common = {"switch height (actuator tip)": 0.10, "switch solder joint": 0.03, "KB boss top vs floor seat (one setup)": 0.03,
              "floor seat face": 0.03}
    for label, pre, key_items in (
            ("main key (CNC PMMA)", p.pre_main, {"key length (flange underside to nub top)": 0.03}),
            ("side keys (cast rubber + glued plate and doubler)", p.pre_side,
             {"recess floor above the flange underside (cast in the aluminium mould)": 0.05,
              "plate + doubler, 2 x 0.30 shim (+/-0.02 each)": 0.04, "glue films": 0.02})):
        tol = dict(common, **key_items)
        wc = sum(tol.values())
        rss = math.sqrt(sum(v * v for v in tol.values()))
        out[label] = {"nominal_free_play_mm": pre, "items_mm": tol, "worst_case_mm": [round(pre - wc, 3), round(pre + wc, 3)],
                      "rss_mm": [round(pre - rss, 3), round(pre + rss, 3)]}
    out["note"] = ("a negative value is a preload on the switch: for the elastomer keys it is taken by the rubber "
                   "(a few tenths of a newton per 0.1 mm), for the rigid PMMA key only the worst case (all tolerances "
                   "at their limit at once) goes below zero, and still stays below the click (about %.2f mm)" % p.sw_click)
    return out


def led_gap_check(p, parts, kb):
    key = parts["FlashKa_key_main"]
    stroke = p.pre_main + p.sw_travel
    rest = min(_dist(key, kb["kb_led3"]), _dist(key, kb["kb_led4"]))
    moved = key.translate((0, 0, stroke))
    full = min(_dist(moved, kb["kb_led3"]), _dist(moved, kb["kb_led4"]))
    tol = {"switch height": 0.10, "switch travel": 0.10, "LED solder": 0.03, "switch solder": 0.03, "key top to nub (CNC)": 0.02}
    rss = math.sqrt(sum(v * v for v in tol.values()))
    return {"gap_at_rest_mm": round(rest, 3), "gap_at_full_travel_mm": round(full, 3),
            "full_travel_gap_rss_min_mm": round(full - rss, 3), "full_travel_gap_worst_case_mm": round(full - sum(tol.values()), 3),
            "led_height_used_mm": p.ring_led_h,
            "note": "gap at full travel = switch height - travel - LED height - (key top to nub depth): independent of "
                    "the floor and the KB height; a lower real LED only makes both gaps larger"}


def side_key_end_press(p, parts=None, kb=None):
    """Side key pressed 2 mm from one end: rigid rocker about the far flange end on the floor seat + rubber
    compression + bending of the stiffener plate glued on the inner face; the doubler on the plate presses the switch
    (steel on the actuator: no rubber in that load path); and the same key without the plate (rubber only)."""
    sx, sy, sr = p.side_key
    a = sy / 2 + p.flange_side                  # pivot (far flange end) to the nub
    b = sy / 2 - 2.0                            # nub to the press point
    F = p.sw_force_n
    Fp = F * a / (a + b)                        # press force at the click
    R = F - Fp                                  # pivot reaction
    E = p.E_rubber_mpa
    w, ln, t, _ = p.stiffener
    # compressions (linear, small strain): the switch force goes from the doubler straight into the plate (no rubber);
    # the pivot reaction reaches the plate end through the flange, the finger force through the rubber under the plate
    d_nub = 0.0
    t_piv = p.flange_t
    A_piv = p.flange_side * (sx + 2 * p.flange_side)
    d_piv = R * t_piv / (E * A_piv)
    t_fin = (p.stiff_z0 - p.plate_glue) - p.side_face_z
    A_fin = 4.0 * 3.0
    d_fin = Fp * t_fin / (E * A_fin)
    # stiffener plate: overhang beam (span a, overhang b)
    I_pl = w * t ** 3 / 12
    EI = p.E_steel_mpa * I_pl
    d_bend = Fp * b ** 2 * (a + b) / (3 * EI)
    lev = (a + b) / a
    out = {"model": "rigid rocker about the far flange end (pivot) on the floor seat; the doubler on the switch "
                    "actuator; press %.1f mm from the near key end; rubber E %.1f MPa (Shore A 80, Gent), linear" % (2.0, E),
           "pivot_to_nub_mm": round(a, 3), "nub_to_press_point_mm": round(b, 3),
           "press_force_at_click_N": round(Fp, 3), "pivot_reaction_N": round(R, 3),
           "compression_mm": {"doubler on the actuator (steel)": round(d_nub, 4), "pivot flange": round(d_piv, 4),
                              "under the finger": round(d_fin, 4)},
           "stiffener_bending_at_press_point_mm": round(d_bend, 4)}
    for case, nub_travel in (("click", p.pre_side + p.sw_click), ("full travel", p.pre_side + p.sw_travel),
                             ("click, free play at the RSS maximum", p.pre_side + 0.17 + p.sw_click)):
        dp = nub_travel * lev + d_nub * lev + d_piv * (b / a) + d_fin + d_bend
        theta = (nub_travel + d_nub) / a
        end_rise = theta * (a + sy / 2 + p.flange_side)
        clear = p.kb_z0 - (p.Z_seat + p.flange_t)
        # horizontal shift of the near cap end at the opening's lower edge (bezel floor) when rocked
        dy_cap = theta * (p.Z_seat - p.bez_depth)
        out[case] = {"nub_travel_mm": round(nub_travel, 3), "press_travel_mm": round(dp, 3),
                     "near_end_rise_mm": round(end_rise, 3), "near_end_clearance_to_KB_mm": round(clear, 3),
                     "near_end_margin_mm": round(clear - end_rise, 3), "tilt_deg": round(math.degrees(theta), 2),
                     "cap_end_shift_in_opening_mm": round(dy_cap, 3), "end_gap_in_opening_mm": p.key_clear_end}
    # rubber only (no plate, empty recess): Timoshenko overhang beam of the key section, same loads
    A1, z1 = sx * (p.Z_seat - p.side_face_z), (p.Z_seat + p.side_face_z) / 2
    w2 = sx + 2 * p.flange_side - p.plate_recess[0]           # the two flange rims beside the recess
    A2, z2 = w2 * p.flange_t, p.Z_seat + p.flange_t / 2
    zc = (A1 * z1 + A2 * z2) / (A1 + A2)
    I_r = (sx * (p.Z_seat - p.side_face_z) ** 3 / 12 + A1 * (z1 - zc) ** 2 +
           w2 * p.flange_t ** 3 / 12 + A2 * (z2 - zc) ** 2)
    G = E / 3
    d_r = Fp * b ** 2 * (a + b) / (3 * E * I_r) + Fp * b / (5 / 6 * G * (A1 + A2)) + R * a / (5 / 6 * G * (A1 + A2))
    nt = p.pre_side + p.sw_click
    rigid_end = nt / a * (a + sy / 2 + p.flange_side)
    out["without the stiffener plate (rubber only)"] = {
        "section_I_mm4": round(I_r, 3), "extra_press_travel_from_bending_and_shear_mm": round(d_r, 3),
        "press_travel_at_click_mm": round(nt * lev + d_r, 3),
        "near_end_rise_estimate_mm": round(rigid_end + d_r * (a + sy / 2 + p.flange_side) / (a + b), 3),
        "note": "the rubber key bends more than its whole switch travel: it would feel soft at the ends; "
                "the 0.3 mm stainless steel plate makes it a stiff rocker"}
    if parts is not None and kb is not None:
        # geometry: rock the next key (rubber + glued stiffener) about its pivot line by the full-travel angle and look
        # for contacts
        theta = (p.pre_side + p.sw_travel + d_nub) / a
        hits = []
        key0 = parts["FlashKa_key_side"].union(parts["FlashKa_key_stiffener"])
        # the switch housing without the column above the actuator (the actuator moves up into it when pressed)
        act_col = cyl_z(p.X_next, p.key_y, p.sw_act_d + 0.02, p.Z_sw_tip - 0.1, p.kb_z0 + 0.1)
        for sgn in (1, -1):
            piv = cq.Vector(p.X_next, p.key_y - sgn * a, p.Z_seat)
            key = key0.rotate(piv, piv + cq.Vector(1, 0, 0), math.degrees(theta) * sgn)
            for on, o in list(kb.items()) + [("tray", parts["FlashKa_tray"]), ("key_main", parts["FlashKa_key_main"])]:
                if on in ("kb_sw2_act",):
                    continue
                if on == "kb_sw2":
                    o = o.cut(act_col)
                v = _vol(key, o)
                if v > 1e-4:
                    hits.append(("press at %s end" % ("+Y" if sgn > 0 else "-Y"), on, round(v, 4)))
        out["rocked_key_contacts_at_full_travel (own actuator and its column excluded)"] = hits
    return out


def pogo_stack(p):
    tol = {"main-board ledge Z": 0.05, "KB boss top Z": 0.03, "KB thickness (0.8 mm board)": 0.08, "pogo solder joint": 0.03}
    h = p.pogo_h
    wc = sum(tol.values())
    rss = math.sqrt(sum(v * v for v in tol.values()))
    s = p.pogo_free - p.pogo_work

    def force(hh, f0):
        return f0 * (p.pogo_free - hh) / s
    n = len(p.pogo_pins)
    fl, fh = p.pogo_force_n - p.pogo_force_tol_n, p.pogo_force_n + p.pogo_force_tol_n
    return {"pin": p.pogo_part, "free_mm": p.pogo_free, "working_mm": p.pogo_work, "min_mm": p.pogo_min,
            "working_height_nominal_mm": round(h, 3), "items_mm": tol,
            "working_height_worst_case_mm": [round(h - wc, 3), round(h + wc, 3)],
            "working_height_rss_mm": [round(h - rss, 3), round(h + rss, 3)],
            "allowed_range_mm": [p.pogo_min, p.pogo_max_work],
            "inside_range_worst_case": bool(h - wc >= p.pogo_min and h + wc <= p.pogo_max_work),
            "margin_to_range_worst_case_mm": [round(h - wc - p.pogo_min, 3), round(p.pogo_max_work - (h + wc), 3)],
            "compression_mm": [round(p.pogo_free - h - wc, 3), round(p.pogo_free - h, 3), round(p.pogo_free - h + wc, 3)],
            "force_per_pin_N (min, nominal, max incl. the +/-%.2f N spring tolerance)" % p.pogo_force_tol_n:
                [round(force(h + wc, fl), 3), round(force(h, p.pogo_force_n), 3), round(force(h - wc, fh), 3)],
            "force_total_N": [round(n * force(h + wc, fl), 2), round(n * force(h, p.pogo_force_n), 2),
                              round(n * force(h - wc, fh), 2)],
            "max_force_factor": round(force(h - wc, fh) / p.pogo_force_n, 3),
            "note": "spring force linear through the free height (%.2f N at %.2f mm)" % (p.pogo_force_n, p.pogo_work)}


def holddown_report(p, e_scale=1.0, gap_extra=0.0, pogo_scale=1.0, front_boss=None, nx=88, ny=60):
    """Plate model of the main board: FR-4 0.8 mm (Mindlin, free edges) on unilateral ledge supports, pressed down
    by the gap pad under the lid boss on the module can (linear spring, pre-compressed) and pushed up by the six
    pogo pins.  Returns the state and the factor on the pogo forces at which the board starts to leave the ledges."""
    import numpy as np
    import scipy.sparse as sp
    import scipy.sparse.linalg as spl
    fb = p.front_boss if front_boss is None else front_boss
    t, E, nu = p.pcb_t, p.pcb_E_mpa, p.pcb_nu
    Dm = E * t ** 3 / (12 * (1 - nu ** 2))
    Gs = 5.0 / 6.0 * E / (2 * (1 + nu)) * t
    Db = Dm * np.array([[1, nu, 0], [nu, 1, 0], [0, 0, (1 - nu) / 2]])
    x0p, x1p, hy = p.X_pcb0, p.X_pcb1, p.Y_pcb
    xs, ys = np.linspace(x0p, x1p, nx + 1), np.linspace(-hy, hy, ny + 1)
    hx, hyy = xs[1] - xs[0], ys[1] - ys[0]
    nid = lambda i, j: j * (nx + 1) + i
    N = (nx + 1) * (ny + 1)
    gp_ = [-1 / math.sqrt(3), 1 / math.sqrt(3)]
    Ke = np.zeros((12, 12))
    for xi in gp_:
        for eta in gp_:
            Nn = 0.25 * np.array([(1 - xi) * (1 - eta), (1 + xi) * (1 - eta), (1 + xi) * (1 + eta), (1 - xi) * (1 + eta)])
            dNx = 0.25 * np.array([-(1 - eta), (1 - eta), (1 + eta), -(1 + eta)]) * 2 / hx
            dNy = 0.25 * np.array([-(1 - xi), -(1 + xi), (1 + xi), (1 - xi)]) * 2 / hyy
            Bb = np.zeros((3, 12))
            Bs = np.zeros((2, 12))
            for k in range(4):
                Bb[0, 3 * k + 1] = dNx[k]
                Bb[1, 3 * k + 2] = dNy[k]
                Bb[2, 3 * k + 1] = dNy[k]
                Bb[2, 3 * k + 2] = dNx[k]
                Bs[0, 3 * k] = dNx[k]
                Bs[0, 3 * k + 1] = -Nn[k]
                Bs[1, 3 * k] = dNy[k]
                Bs[1, 3 * k + 2] = -Nn[k]
            Ke += hx * hyy / 4 * (Bb.T @ Db @ Bb + Gs * Bs.T @ Bs)
    rows, cols, vals = [], [], []
    for j in range(ny):
        for i in range(nx):
            nn = [nid(i, j), nid(i + 1, j), nid(i + 1, j + 1), nid(i, j + 1)]
            dofs = np.array([3 * n + d for n in nn for d in range(3)])
            rows.append(np.repeat(dofs, 12))
            cols.append(np.tile(dofs, 12))
            vals.append(Ke.ravel())
    K0 = sp.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(3 * N, 3 * N))
    X, Y = np.meshgrid(xs, ys)
    X, Y = X.ravel(), Y.ravel()
    yl = p.inner_half - p.ledge_w
    ysup = yl + 0.5 * (hy - yl)
    jp, jm = int(round((ysup + hy) / hyy)), int(round((-ysup + hy) / hyy))
    sup = np.array([nid(i, jp) for i in range(nx + 1) if xs[i] >= p.las_keepout_x] +
                   [nid(i, jm) for i in range(nx + 1) if xs[i] >= p.minusY_open[0][1]])

    def pad(box, t0, E_, gap, r_):
        bx0, bx1, by0, by1 = box
        A_ = (bx1 - bx0) * (by1 - by0) - (4 - math.pi) * r_ ** 2
        nodes = np.where((X >= bx0 - 1e-9) & (X <= bx1 + 1e-9) & (Y >= by0 - 1e-9) & (Y <= by1 + 1e-9))[0]
        d0 = t0 - (gap + gap_extra)
        k_tot = E_ * e_scale * A_ / t0
        return dict(nodes=nodes, k=k_tot / len(nodes), d0=d0, A=A_, k_tot=k_tot, box=box, t0=t0, E=E_ * e_scale)
    pads = [pad(p.boss_box, p.pad_t0, p.pad_E_mpa, p.pad_gap, p.boss_r)]
    if fb:
        pads.append(pad(p.boss2_box, p.pad2_t0, p.pad2_E_mpa, p.pad2_gap, p.boss2_r))
    s2n = nid(int(round((p.X_s2 - x0p) / hx)), jp)
    k_pin = p.pogo_force_n * (p.pogo_free - p.pogo_h) / (p.pogo_free - p.pogo_work)    # at the nominal working height
    pin_nodes = [np.where((abs(X - x) <= 0.45) & (abs(Y - y) <= 0.45))[0] for (x, y) in p.pogo_pins]

    def solve(scale):
        f = np.zeros(3 * N)
        for m in pin_nodes:
            f[3 * m] += scale * k_pin / len(m)
        act_l = np.ones(len(sup), bool)
        act_s = False
        w = np.zeros(N)
        for it in range(80):
            diag = np.zeros(3 * N)
            rhs = f.copy()
            diag[3 * sup[act_l]] += 1e5
            for pd in pads:
                diag[3 * pd["nodes"]] += pd["k"]
                rhs[3 * pd["nodes"]] += -pd["k"] * pd["d0"]
            if act_s:
                diag[3 * s2n] += 1e5
                rhs[3 * s2n] += 1e5 * p.s2_stop_gap
            u = spl.spsolve((K0 + sp.diags(diag)).tocsc(), rhs)
            w = u[0::3]
            new_l = w[sup] < 0.0
            new_s = w[s2n] > p.s2_stop_gap
            if np.array_equal(new_l, act_l) and new_s == act_s:
                break
            act_l, act_s = new_l, new_s
        return w, int((~act_l).sum())

    w0, n0 = solve(0.0)
    w1, n1 = solve(pogo_scale)
    lift = w1[sup]
    k_max = int(np.argmax(lift))
    max_lift = float(max(lift.max(), 0.0))
    pin_w = [round(float(np.mean(w1[m])), 4) for m in pin_nodes]
    pin_dw = [round(float(np.mean(w1[m]) - np.mean(w0[m])), 4) for m in pin_nodes]
    lift_at = None
    for s in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10, 12, 15, 20):
        _, nl = solve(s * pogo_scale)
        if nl - n0 >= 3:
            lift_at = s
            break
    out = {"model": ("Mindlin plate FR-4 0.8 mm, E %.0f MPa, nu %.2f, grid %.3f x %.3f mm, free edges; unilateral ledge "
                     "supports (+Y ledge X >= %g, -Y ledge X >= %g); pads = linear springs; six pogo pins = upward "
                     "point loads; S2 knob stop %.3f mm above rest" % (E, nu, hx, hyy, round(p.las_keepout_x, 3),
                                                                       round(p.minusY_open[0][1], 3), p.s2_stop_gap)),
           "pad_E_scale": e_scale, "pad_gap_extra_mm": gap_extra, "front_boss": bool(fb),
           "pogo_force_total_N": round(pogo_scale * k_pin * len(p.pogo_pins), 2)}
    for k, pd in zip(("can pad", "front pad"), pads):
        out[k] = {"box_mm": list(pd["box"]), "area_mm2": round(pd["A"], 1), "free_thickness_mm": pd["t0"],
                  "compressed_to_mm": round(pd["t0"] - pd["d0"], 3), "compression_pct": round(100 * pd["d0"] / pd["t0"], 1),
                  "E_MPa": round(pd["E"], 2), "stiffness_N_per_mm": round(pd["k_tot"], 2),
                  "preload_N": round(pd["k_tot"] * pd["d0"], 2)}
    pre = sum(pd["k_tot"] * pd["d0"] for pd in pads)
    out["preload_total_N"] = round(pre, 2)
    out["preload_over_pogo_force"] = round(pre / max(pogo_scale * k_pin * len(p.pogo_pins), 1e-9), 2)
    out["board_bow_at_rest_mm (no pins)"] = round(float(w0.min()), 4)
    out["ledge_nodes_lifted_with_pins"] = n1 - n0
    out["max_ledge_lift_mm"] = round(max_lift, 4)
    out["max_ledge_lift_at_XY"] = [round(float(X[sup[k_max]]), 2), round(float(Y[sup[k_max]]), 2)]
    out["board_z_at_the_pins_mm (relative to the ledges)"] = pin_w
    out["pin_point_lift_by_the_pins_mm"] = pin_dw
    out["pogo_factor_at_which_the_board_leaves_the_ledges"] = lift_at if lift_at else "> 20"
    out["lift_limit_mm"] = 0.02
    out["ok"] = bool(max_lift <= 0.02 and (pogo_scale > 1.0 or lift_at is None or lift_at >= 1.5))
    out["note"] = ("pad modulus is an assumption from the Shore hardness (gap pad Shore 00 70-80: %.1f MPa); the parts on "
                   "the board stiffen it (ignored)" % p.pad_E_mpa)
    return out


def pad_stack(p):
    tol = {"module can height": 0.10, "main board thickness": 0.08, "main-board ledge Z": 0.05, "lid boss height": 0.03,
           "lid seat Z": 0.03}
    wc = sum(tol.values())
    rss = math.sqrt(sum(v * v for v in tol.values()))
    out = {"pad_free_mm": p.pad_t0, "gap_nominal_mm": p.pad_gap, "items_mm": tol,
           "gap_worst_case_mm": [round(p.pad_gap - wc, 3), round(p.pad_gap + wc, 3)],
           "gap_rss_mm": [round(p.pad_gap - rss, 3), round(p.pad_gap + rss, 3)],
           "compression_pct_nominal": round(100 * (1 - p.pad_gap / p.pad_t0), 1),
           "compression_pct_worst_case": [round(100 * (1 - (p.pad_gap + wc) / p.pad_t0), 1),
                                          round(100 * (1 - (p.pad_gap - wc) / p.pad_t0), 1)]}
    if p.front_boss:
        t2 = {k: v for k, v in tol.items() if k != "module can height"}
        wc2 = sum(t2.values())
        rss2 = math.sqrt(sum(v * v for v in t2.values()))
        g2 = p.pad2_gap
        out["front pad"] = {"pad_free_mm": p.pad2_t0, "gap_nominal_mm": g2, "items_mm": t2,
                            "gap_worst_case_mm": [round(g2 - wc2, 3), round(g2 + wc2, 3)],
                            "gap_rss_mm": [round(g2 - rss2, 3), round(g2 + rss2, 3)],
                            "compression_pct_nominal": round(100 * (1 - g2 / p.pad2_t0), 1),
                            "compression_pct_worst_case": [round(100 * (1 - (g2 + wc2) / p.pad2_t0), 1),
                                                           round(100 * (1 - (g2 - wc2) / p.pad2_t0), 1)]}
    return out


def tray_voids(p):
    """interior voids and openings of the tray: (interior, openings)"""
    inner = {"cavity": cavity_solid(p).val()}
    inner["optic bore"] = optic_bore(p).val()
    inner["laser bore"] = cyl_x(p.Y_l, p.Z_las, p.las_d + p.las_clear, -1, p.las_recess + p.las_len + p.las_bore_extra).val()
    inner["laser set-screw hole"] = laser_set_hole(p, p.Z_lid).val()
    for i, (g, h) in enumerate(led_wire_paths(p)):
        inner["LED wire hole %d" % i] = h.val()
        inner["LED wire groove %d" % i] = g.val()
    for s in (-1, 1):
        for x in (p.screw_x_front, p.X_screw_back):
            inner["lid tap %g/%+d" % (x, s)] = cyl_z(x, s * p.screw_dy, p.m16_tap, p.Z_lid - p.m16_drill, p.Z_lid).val()
    for i, h in enumerate(kb_tap_holes(p)):
        inner["KB tap %d" % (i + 1)] = h.val()
    ih = p.inner_half
    for sy in (-1, 1):
        inner["front corner relief %+d" % sy] = front_relief_tool(p, sy, p.Z_lid).val()
    opn = {}
    for i, k in enumerate(("next", "main", "prev")):
        opn["key opening " + k] = key_openings(p)[i].val()
    opn["floor RF window"] = floor_rf_opening(p).val()
    w, h, r = p.usb_open
    opn["USB-C opening"] = slot_y(p.X_usb, p.Z_usb, w + 2 * p.usb_open_chamfer, h + 2 * p.usb_open_chamfer,
                                  r + p.usb_open_chamfer, -p.W / 2 - 1, -ih + 0.01).val()
    w, h, r = p.s2_slot
    opn["S2 slot"] = slot_y(p.X_s2, p.Z_pcb_top + p.s2_knob_z, w, h, r, ih - 0.01, p.W / 2 + 1).val()
    tt, _ = tail_tools(p)
    opn["tail window"] = tt[0].val()
    opn["lanyard slot"] = tt[1].val()
    return inner, opn


def lid_voids(p):
    below = lid_pocket(p).cut(boss_solid(p))
    if p.front_boss:
        below = below.cut(boss2_solid(p))
    inner = {"space under the lid": below.val(),
             "RF pocket": rf_window_outline(p, p.rfw_flange, p.Z_ceil - 1, p.Z_ceil + p.rfw_flange_t).val()}
    opn = {"RF opening": rf_window_outline(p, 0.0, p.Z_ceil - 1, p.H + 1).val()}
    for s in (-1, 1):
        for x in (p.screw_x_front, p.X_screw_back):
            cone = cq.Solid.makeCone(p.m16_csk / 2, p.m16_clear / 2, (p.m16_csk - p.m16_clear) / 2,
                                     pnt=cq.Vector(x, s * p.screw_dy, p.H), dir=cq.Vector(0, 0, -1))
            opn["screw %g/%+d" % (x, s)] = cone.fuse(cyl_z(x, s * p.screw_dy, p.m16_clear, p.Z_lid - 0.5, p.H).val())
    _, lt = tail_tools(p)
    opn["lanyard slot"] = lt[0].val()
    return inner, opn


def texture_report(p):
    """metal left under every panel / groove / the bezel (to the interior voids) and the clearance to openings"""
    env = envelope(p).val()
    tin, topn = tray_voids(p)
    lin, lopn = lid_voids(p)
    lid_dom = lid_part_region(p).val()
    rows = []

    def row(name, tool, inner, opn, limit, exclude=()):
        cut = _shape(tool).intersect(env)
        if cut is None or cut.Volume() < 1e-6:
            return
        under = min(_dist(cut, v) for v in inner.values())
        clr = [(_dist(cut, v), k) for k, v in opn.items() if k not in exclude]
        cl = min(clr) if clr else (float("nan"), "-")
        rows.append({"feature": name, "metal_under_mm": round(under, 3), "limit_mm": limit,
                     "ok": bool(under >= limit - 1e-3), "clearance_to_openings_mm": round(cl[0], 3), "nearest_opening": cl[1]})
    for name, tool in panel_tools(p, True):
        face = [q for q in panel_layout(p) if q["name"] == name][0]["face"]
        over_cells = [q for q in panel_layout(p) if q["name"] == name][0]["u0"] >= p.X_batt0 - 1e-6
        lim = p.tex_min_metal_cells if over_cells else p.tex_min_metal
        if face == "top":
            row(name, tool, lin, lopn, lim)
        else:
            ex = ("floor RF window",) if name.startswith("bottom bay 1") else ()
            row(name, tool, tin, topn, lim, exclude=ex)
    for name, g in groove_tools(p):
        over_cells = float(name.split("X")[-1]) >= p.X_batt0
        lim = p.tex_min_metal_cells if over_cells else p.tex_min_metal
        tray_part = _shape(g).cut(lid_dom)
        lid_part = _shape(g).intersect(lid_dom)
        row(name + " (tray)", tray_part, tin, topn, lim)
        if lid_part is not None and lid_part.Volume() > 1e-6:
            row(name + " (lid)", lid_part, lin, lopn, lim)
    keys_open = ("key opening next", "key opening main", "key opening prev")
    inner_nokeys = {k: v for k, v in tin.items()}
    row("key bezel", bezel_tool(p), inner_nokeys, topn, p.tex_min_metal, exclude=keys_open)
    return rows


def min_wall_report(p):
    rb = p.opt_bore / 2
    rl = (p.las_d + p.las_clear) / 2
    gw, gd = p.wire_groove
    a = math.radians(p.led_wire_ang)
    (_, zht), (yhb, zhb) = led_wire_hole_yz(p)
    kr = key_rects(p, p.key_clear, p.key_clear_end)
    rep = {
        "optic bore to control-side face": p.W / 2 - abs(p.Y_w) - rb,
        "optic bore to the lower -Y diagonal facet": (p.W / 2 - p.C_edge - (abs(p.Y_w) - p.Z_axis)) / math.sqrt(2) - rb,
        "optic bore to top face (lid seat, X > lid_x0)": p.Z_lid - (p.Z_axis + rb),
        "optic bore to bottom face": p.Z_axis - rb,
        "solid head block behind the LED board (bore floor to head rear face)": p.L_head - p.D_w,
        "LED wire groove (upper) to lid seat": p.Z_lid - (p.Z_axis + (rb + gd) * math.cos(a) + gw / 2 * math.sin(a)),
        "LED wire hole (upper) to lid seat": p.Z_lid - (zht + p.ledwire_d / 2),
        "LED wire groove (lower) to control-side face": p.W / 2 - abs(p.Y_w - (rb + gd) * math.sin(a)
                                                                      - gw / 2 * math.cos(a)),
        "LED wire hole (lower) to control-side face": p.W / 2 - abs(yhb) - p.ledwire_d / 2,
        "LED wire groove (lower) to the lower -Y diagonal facet": min(
            (y + z + (p.W / 2 - p.C_edge)) / math.sqrt(2)
            for y, z in [(p.Y_w - (rb + gd) * math.sin(a) + sg * gw / 2 * math.cos(a),
                          p.Z_axis - (rb + gd) * math.cos(a) - sg * gw / 2 * math.sin(a)) for sg in (-1, 1)]),
        "LED wire hole (lower) to the lower -Y diagonal facet": (yhb + zhb + (p.W / 2 - p.C_edge)) / math.sqrt(2)
                                                               - p.ledwire_d / 2,
        "laser bore to laser-side face": p.W / 2 - p.Y_l - rl,
        "laser bore to the lower +Y diagonal facet": (p.W / 2 - p.C_edge - (p.Y_l - p.Z_las)) / math.sqrt(2) - rl,
        "laser bore to bottom face": p.Z_las - rl,
        "laser set screw: thread crest to the front lid tap +Y thread": math.hypot(
            p.las_set[0] - p.screw_x_front, p.las_set[1] - p.screw_dy) - 1.6,
        "laser set screw: hole behind the lid front edge (thread crest)": p.las_set[0] - 0.8 - p.lid_x0,
        "laser set screw: thread crest to the head rear face": p.L_head - p.las_set[0] - 0.8,
        "optic bore to laser bore": (p.Y_l - p.Y_w) - rb - rl,
        "laser module top below the PCB": p.Z_pcb_bot - (p.Z_las + p.las_d / 2),
        "side walls": p.wall,
        "floor": p.floor,
        "lid plate over the cavity": p.lid_t,
        "diagonal facets: wall to the cavity (tray) and to the lid pocket": p.wall,
        "lid over the head and the tail blocks (solid)": p.H - p.Z_lid,
        "lid around the RF window flange pocket": p.lid_t - p.rfw_flange_t,
        "lid: RF window pocket edge to the upper diagonal facets": (
            (p.W / 2 + p.H - p.C_edge) - (p.rfw_box[2] + p.rfw_flange) - (p.Z_ceil + p.rfw_flange_t)) / math.sqrt(2),
        "lanyard bridge (slot to tail face)": p.L - (p.X_lan + p.lan_slot_w / 2),
        "tail front wall (bay to slot)": p.tail_front_wall,
        "slot end to rear screw tap": p.screw_dy - p.m16_tap / 2 - p.lan_slot_len / 2,
        "slot end to rear screw tap (thread crest)": p.screw_dy - 0.8 - p.lan_slot_len / 2,
        "lid top face: rear countersink edge to the slot chamfer": (p.screw_dy - p.m16_csk / 2
                                                                    - (p.lan_slot_len / 2 + p.lan_chamfer)),
        "front screw tap to head rear face": p.L_head - p.screw_x_front - p.m16_tap / 2,
        "front screw tap to head rear face (thread crest)": p.L_head - p.screw_x_front - 0.8,
        "front screw tap to the optic bore floor": p.screw_x_front - p.m16_tap / 2 - p.D_w,
        "front screw tap to the optic bore floor (thread crest)": p.screw_x_front - 0.8 - p.D_w,
        "front corner relief to the outer side face": p.W / 2 - (p.inner_half - p.front_relief[2] + p.front_relief[0] / 2),
        "floor under the key bezel": p.floor - p.bez_depth,
        "floor web: next opening to main opening": kr["main"][0] - kr["next"][1],
        "floor web: main opening to previous opening": kr["prev"][0] - kr["main"][1],
        "floor: previous opening to floor RF window": p.frw_box[0] - kr["prev"][1],
        "bezel edge to floor RF window (band)": p.frw_box[0] - (p.X_prev + p.side_key[0] / 2 + p.bez_margin + p.bez_depth),
        "floor RF window to side wall": p.inner_half - p.frw_box[2],
        "KB boss: wall round the M1.6 thread (key side)": p.boss_d / 2 - 0.8,
        "KB tap: metal under the drill point to the bottom face": p.kb_drill_apex_z,
        "KB tap: thread engagement of the M1.6 x %g screw" % p.kb_screw_len: p.kb_z0 - p.kb_screw_tip_z,
        "texture: groove width": 2 * p.tex_depth,
        "texture: land between grooves": p.tex_pitch - 2 * p.tex_depth,
        "transverse groove width": 2 * p.grv_depth,
        "transverse groove land": min(b - a for a, b in zip(p.grv_tail, p.grv_tail[1:])) - 2 * p.grv_depth,
    }
    rep.update(feature_walls(p))
    return {k: round(v, 3) for k, v in rep.items()}


def lid_tap_thread_tool(p, x, y):
    """a lid tap as cut: the thread to its root (major d 1.6) over the thread depth (drill depth - 1.0, as on the
    drawing), two pitches of run-out down to the tap drill, the tap drill to its depth and the 118 deg drill point"""
    zt = p.Z_lid - (p.m16_drill - 1.0)
    run = 2 * p.m16_pitch
    rd, zd = p.m16_tap / 2, p.Z_lid - p.m16_drill
    s = cq.Solid.makeCylinder(0.8, p.Z_lid + 0.1 - zt, cq.Vector(x, y, zt), cq.Vector(0, 0, 1))
    s = s.fuse(cq.Solid.makeCone(rd, 0.8, run, cq.Vector(x, y, zt - run), cq.Vector(0, 0, 1)))
    s = s.fuse(cq.Solid.makeCylinder(rd, zt - run - zd + 0.01, cq.Vector(x, y, zd), cq.Vector(0, 0, 1)))
    s = s.fuse(cq.Solid.makeCone(rd, 0.0, rd / math.tan(math.radians(59)), cq.Vector(x, y, zd), cq.Vector(0, 0, -1)))
    return cq.Workplane().add(s)


def feature_walls(p):
    f = {"optic bore": optic_bore(p),
         "laser bore": cyl_x(p.Y_l, p.Z_las, p.las_d + p.las_clear, -1, p.las_recess + p.las_len + p.las_bore_extra),
         "laser set-screw hole": laser_set_hole(p, p.Z_lid)}
    for i, (g, h) in enumerate(led_wire_paths(p)):
        f["LED wire hole %s" % ("top" if i == 0 else "bottom")] = h
        f["LED wire groove %s" % ("top" if i == 0 else "bottom")] = g
    for s, nm in ((1, "+Y"), (-1, "-Y")):
        f["front lid tap %s" % nm] = cyl_z(p.screw_x_front, s * p.screw_dy, p.m16_tap, p.Z_lid - p.m16_drill, p.Z_lid)
        f["rear lid tap %s" % nm] = cyl_z(p.X_screw_back, s * p.screw_dy, p.m16_tap, p.Z_lid - p.m16_drill, p.Z_lid)
    f["lanyard slot"] = (cq.Workplane("XY").center(p.X_lan, 0).slot2D(p.lan_slot_len, p.lan_slot_w, 90).extrude(p.H))
    f["front corner relief +Y"], f["front corner relief -Y"] = front_relief_tool(p, 1), front_relief_tool(p, -1)
    taps = kb_tap_holes(p)
    f["KB tap +Y"], f["KB tap -Y"] = (taps[0], taps[1]) if p.kb_holes[0][1] > 0 else (taps[1], taps[0])
    f["key bezel"] = bezel_tool(p)
    ko = key_openings(p)
    f["main key opening"] = ko[1]
    # the front lid taps with the thread to its root: 3D walls to the bore floor and to the head rear face (cavity)
    for s, nm in ((1, "+Y"), (-1, "-Y")):
        f["front lid tap %s thread" % nm] = lid_tap_thread_tool(p, p.screw_x_front, s * p.screw_dy)
    f["cavity"] = cavity_solid(p)
    pairs = [("front lid tap -Y", "LED wire hole top"), ("front lid tap -Y", "optic bore"),
             ("front lid tap +Y", "laser bore"), ("optic bore", "laser bore"),
             ("front lid tap +Y", "LED wire hole top"), ("front lid tap -Y", "LED wire groove top"),
             ("LED wire groove top", "laser bore"), ("LED wire hole top", "laser bore"),
             ("laser set-screw hole", "front lid tap +Y"), ("laser set-screw hole", "optic bore"),
             ("laser set-screw hole", "LED wire hole top"), ("laser set-screw hole", "LED wire groove top"),
             ("rear lid tap +Y", "lanyard slot"), ("rear lid tap -Y", "lanyard slot"),
             ("front lid tap +Y", "front corner relief +Y"), ("front lid tap -Y", "front corner relief -Y"),
             ("KB tap +Y", "key bezel"), ("KB tap -Y", "key bezel"), ("KB tap +Y", "main key opening"),
             ("KB tap -Y", "main key opening"),
             ("front lid tap -Y thread", "optic bore"), ("front lid tap -Y thread", "cavity"),
             ("front lid tap +Y thread", "cavity")]
    return {"wall %s - %s" % (a, b): _dist(f[a], f[b]) for a, b in pairs}


def exterior_hole_scan(p, step=0.4, limit=0.6):
    """the closed light seen from below and from above: rays on a grid onto the plain tray, lid, RF window insert,
    antenna spacer and keys; a ray that runs more than `limit` deeper than the outer surface (chamfers included)
    marks a hole.  Excluded: the key openings, the floor RF window plug and the lid RF insert (their joints), the tail
    window with the lanyard slot and the four lid screws (by design)."""
    import numpy as np
    from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
    from OCP.gp import gp_Dir, gp_Lin, gp_Pnt
    shapes = [build_tray(p, texture="none"), build_lid(p, texture="none"), build_rf_window(p, texture=False),
              build_antenna_spacer(p, texture=False), build_key_main(p), build_key_side(p, p.X_next, -1),
              build_key_side(p, p.X_prev, +1)]
    comp = cq.Compound.makeCompound([_shape(s) for s in shapes])
    it = IntCurvesFace_ShapeIntersector()
    it.Load(comp.wrapped, 1e-6)
    kr = key_rects(p, p.key_clear + 0.3, p.key_clear_end + 0.3)
    fx0, fx1, fhy, _ = p.frw_box
    rx0, rx1, rhy = p.rfw_box
    xt0 = max(p.X_lan - p.twin_x / 2, p.X_batt1 + p.twin_front_gap) - 0.3
    xt1, yt = p.X_lan + p.twin_x / 2 + 0.3, p.twin_y / 2 + 0.3
    band = 0.15

    def near_outline(x, y, x0, x1, hy, r):
        """within `band` of a rounded rectangle (centre line y = 0): the joint round a plug"""
        qx, qy = abs(x - (x0 + x1) / 2) - ((x1 - x0) / 2 - r), abs(y) - (hy - r)
        d = math.hypot(max(qx, 0.0), max(qy, 0.0)) + min(max(qx, qy), 0.0) - r
        return abs(d) < band

    def excluded(x, y, side):
        if side == "bottom":
            if any(r[0] <= x <= r[1] and r[2] <= y <= r[3] for r in kr.values()):
                return True
            if near_outline(x, y, fx0, fx1, fhy, p.frw_box[3]):
                return True
        else:
            if near_outline(x, y, rx0, rx1, rhy, p.rfw_r):
                return True
            if any(math.hypot(x - sx, y - sg * p.screw_dy) < p.m16_csk / 2 + 0.2
                   for sx in (p.screw_x_front, p.X_screw_back) for sg in (-1, 1)):
                return True
        return xt0 <= x <= xt1 and abs(y) <= yt
    out = {}
    for side, z0, dz in (("bottom", -1.0, 1.0), ("top", p.H + 1.0, -1.0)):
        deep, n = [], 0
        for x in np.arange(step / 2, p.L - step / 2, step):
            for y in np.arange(-p.W / 2 + step / 2, p.W / 2, step):
                if excluded(x, y, side):
                    continue
                it.Perform(gp_Lin(gp_Pnt(float(x), float(y), z0), gp_Dir(0, 0, dz)), 0.0, p.H + 2.0)
                if it.NbPnt() == 0:
                    continue
                n += 1
                t = min(it.WParameter(i) for i in range(1, it.NbPnt() + 1))
                c = max(0.0, abs(y) - (p.W / 2 - p.C_edge))            # long-edge chamfer
                c = max(c, p.C_front - x, x - (p.L - p.C_end))         # end chamfers
                depth = t - 1.0 - c
                if depth > limit:
                    deep.append([round(float(x), 2), round(float(y), 2), round(depth, 2)])
        out[side] = {"rays": n, "points deeper than %.1f mm" % limit: deep[:20], "count": len(deep)}
    return out


def laser_retention_report(p, scan=True):
    """laser module held by an M1.6 set screw from the head-block top under the lid: covered when the lid is on"""
    sx, sy = p.las_set
    rep = {
        "screw": "M1.6 x %g set screw, ISO 4026 flat point or ISO 4029 cup point, hex socket, stainless steel" % p.las_set_len,
        "position_x_y": [sx, sy],
        "offset_from_the_laser_axis_mm (towards -Y)": round(p.las_set_dy, 3),
        "entry": "from the head-block top (Z %g), under the front end of the lid; fitted with the lid off" % p.Z_lid,
        "thread": "M1.6x0.35-6H, tap drill d%g from the head-block top into the laser bore" % p.m16_tap,
        "thread_length_at_the_screw_axis_mm": round(p.Z_lid - p.las_set_bore_z, 3),
        "screw_point_on_the_module_z (module centred; point d%g)" % p.las_set_point: round(p.las_set_tip_z, 3),
        "screw_top_z": round(p.las_set_tip_z + p.las_set_len, 3),
        "screw_top_below_the_head_block_top_mm": round(p.Z_lid - p.las_set_tip_z - p.las_set_len, 3),
        "contact_angle_on_the_module_deg (0 = straight down onto the axis)": round(math.degrees(math.asin(
            (p.las_set_dy - p.las_set_point / 2) / (p.las_d / 2))), 1),
        "hole_x_range (tap drill)": [round(sx - p.m16_tap / 2, 3), round(sx + p.m16_tap / 2, 3)],
        "lid_front_edge_x": p.lid_x0,
        "covered_by_the_lid": bool(sx - 0.8 >= p.lid_x0 + 0.5 - 1e-9),
    }
    if scan:
        rep["outside_of_the_closed_light (ray scan)"] = exterior_hole_scan(p)
    return rep


def rf_window_sizes(p):
    x0, x1, hy = p.rfw_box
    fx0, fx1, fhy, fr = p.frw_box
    return {"lid opening (X x Y, r)": [round(x1 - x0, 3), round(2 * hy, 3), p.rfw_r], "lid opening X": [round(x0, 3), round(x1, 3)],
            "lid insert clearance per side": p.rfw_clear,
            "lid insert flange clearance per side (in the pocket)": p.rfw_flange_clear,
            "floor opening (X x Y, r)": [round(fx1 - fx0, 3), round(2 * fhy, 3), fr], "floor opening X": [fx0, fx1],
            "module antenna X": [round(p.X_pcb1, 3), round(p.X_ant1, 3)],
            "antenna covered by the lid window (X)": [round(max(x0, p.X_pcb1), 3), round(min(x1, p.X_ant1), 3)],
            "antenna covered by the floor window (X)": [round(max(fx0, p.X_pcb1), 3), round(min(fx1, p.X_ant1), 3)],
            "module width (Y)": [round(p.mod_y - p.mod_w / 2, 3), round(p.mod_y + p.mod_w / 2, 3)],
            "module width under both windows (Y)": [round(max(-hy, -fhy, p.mod_y - p.mod_w / 2), 3),
                                                    round(min(hy, fhy, p.mod_y + p.mod_w / 2), 3)],
            "window material": "POM-C black (both); between X %g and %g no metal above or below the module from Y %g "
                               "to %g; its -Y edge strip (Y %g to %g) has aluminium round it (floor corner, side wall, lid "
                               "seat and diagonal wall)" % (
                round(max(x0, fx0), 3), round(min(x1, fx1), 3), round(max(-hy, -fhy), 3),
                round(min(hy, fhy, p.mod_y + p.mod_w / 2), 3), round(p.mod_y - p.mod_w / 2, 3),
                round(max(-hy, -fhy), 3))}


# --------------------------------------------------------------------------
# reports: optic seat, bay, wire paths, thermal-model inputs
# --------------------------------------------------------------------------
def optic_report(p):
    """seat of the LEDiL LISA3-RS-PIN on the LED board in the optic bore"""
    rb, re_ = p.opt_bore / 2, p.opt_exit_d / 2
    x_front = [round(p.opt_recess - p.opt_h_tol, 3), round(p.opt_recess, 3), round(p.opt_recess + p.opt_h_tol, 3)]
    return {
        "optic": "LEDiL LISA3-RS-PIN (FP16558): d%.1f, %.2f +/-%.1f above the LED board (LEDiL drawing FP165xx "
                 "LISA3-x-PIN rev 1.2; data sheet 6.9), PMMA lens in a black PC holder; the two pins are cut off"
                 % (p.opt_od, p.opt_h, p.opt_h_tol),
        "seat": "the holder base stands on the front face of the LED board (the LED level, as LEDiL designs it: "
                "'PCB or heatsink level. LED location'); the LED board lies on the bore floor with thermal paste; "
                "no spacer, no window",
        "bore_d (+0.05/0)": p.opt_bore, "radial_play_nominal": round(rb - p.opt_od / 2, 3),
        "optic_front_face_x (min, nominal, max over the height tolerance)": x_front,
        "optic_front_recess_behind_the_front_face": x_front,
        "led_board_front_face_x (= holder seat = LED level)": round(p.x_led_board, 3),
        "led_board_back_face_x": round(p.x_led_board + p.mcpcb_t, 3),
        "thermal_paste_mm": p.tim_t,
        "bore_floor_x": round(p.D_w, 3),
        "head_rear_face_x": p.L_head,
        "solid_behind_the_bore_floor_mm": round(p.L_head - p.D_w, 3),
        "solid_behind_the_bore_floor_required_mm": p.head_solid_min,
        "led_axis_y_z": [p.Y_w, p.Z_axis],
        "lens_exit_d (drawing callout, unlabelled)": p.opt_exit_d,
        "vignetting": "the bore keeps its full diameter to the front face (no lip, no window): from the edge of the "
                      "exit (r %.2f) a ray clears the bore mouth (r %.3f) up to %.1f deg from the axis at the deepest "
                      "seat (recess %.1f), %.1f deg at the nominal one" % (
                          re_, rb, math.degrees(math.atan2(rb - re_, x_front[2])), x_front[2],
                          math.degrees(math.atan2(rb - re_, x_front[1])), ),
        "retention": "two-part epoxy (or neutral-cure silicone) on the holder rim against the bore wall, the optic "
                     "pressed onto the LED board while it cures; no cyanoacrylate (its vapour fogs PMMA).  Not a press "
                     "fit: the thin PC holder would have to carry the fit, the bore is +0.05/0, and the LED board must "
                     "stay pressed onto the floor.  The glued optic traps the LED board on the bore floor.",
        "led_wires": "the pads face the two wire grooves (upper groove %.0f deg from 12 o'clock towards the laser, "
                     "lower one opposite); if the holder base sits on the solder joints, file two notches into the "
                     "holder rim" % p.led_wire_ang,
    }


def foam_stack(p, gap):
    """free thickness of a foam pad (a stack of foam_step sheets) for a gap: the stack closest to foam_target
    compression"""
    ts = [p.foam_step * k for k in range(1, 13)]
    return min(ts, key=lambda t: (abs((1 - gap / t) - p.foam_target), t))


def bay_report(p, parts=None):
    """the 14500 cell in the bay: every cell case with its height, the gap under the lid (top foam strip), the
    length left for the tail-end foam pad; with parts: interference of the cell (with its strips and joints) with
    the housing"""
    ih = p.inner_half
    cases = {}
    for k in CELL_CASES:
        d, ln = cell_case(p, k)
        zc = cell_centre_z(p, d)
        gap_top = p.Z_ceil - (zc + d / 2)
        left = p.L_batt - 2 * p.cell_end - ln
        pad_end = foam_stack(p, left)
        pad_top = foam_stack(p, gap_top)
        cases[CELL_CASE_NAMES[k]] = {
            "d_x_length": [round(d, 3), round(ln, 3)], "axis_z": round(zc, 3),
            "clearance_over_the_floor_between_the_rails": round(zc - d / 2 - p.floor, 3),
            "gap_under_the_lid (top foam strip)": round(gap_top, 3),
            "top_strip_free_mm": pad_top, "top_strip_compression_pct": round(100 * (1 - gap_top / pad_top), 1),
            "side_gap_to_the_walls": round(ih - d / 2, 3),
            "length_left_for_the_tail_pad": round(left, 3), "tail_pad_free_mm": pad_end,
            "tail_pad_compression_pct": round(100 * (1 - left / pad_end), 1)}
    rep = {
        "bay_x": [round(p.X_batt0, 3), round(p.X_batt1, 3)], "bay_length": p.L_batt,
        "bay_section": "inside of the octagon: %g wide between the side walls, floor Z %g, lid plate Z %g; "
                       "45 deg corners (lower -Y corner = channel for the joints and the far-end wire)" % (
                           2 * ih, p.floor, p.Z_ceil),
        "rails": {"inner_top_edge_y": [-p.rail_y, p.rail_y], "width": p.rail_w, "top_z": round(p.floor + p.rail_h, 3),
                  "x": [round(p.X_batt0 + 3.0, 3), round(p.X_batt1 - 3.0, 3)],
                  "insulation": "polyimide tape %g on each rail; the cell keeps its own sleeve" % p.cell_tape},
        "cell_front_x (behind the strip)": round(cell_x0(p), 3),
        "length_budget": "%g = longest cell %g + 2 x %g (nickel strip 0.2 + fold / weld bumps) + %g (tail pad at its "
                         "thinnest)" % (p.L_batt, p.cell_max[1], p.cell_end, p.cell_end_pad),
        "cases": cases,
        "holding": "the cell rests on the two rails (it cannot roll); a soft closed-cell foam strip %g wide under the "
                   "lid presses it down and a foam pad at the tail end takes up the length; both are stacks of %g mm "
                   "foam sheet, each about 1.6 x the gap it fills (compressed 20 to 55 %%, see the cases); F15 nominal: "
                   "%g mm strip, %g mm tail pad" % (
                       p.top_pad[1], p.foam_step, cases[CELL_CASE_NAMES["nominal"]]["top_strip_free_mm"],
                       cases[CELL_CASE_NAMES["nominal"]]["tail_pad_free_mm"]),
        "connection": "nickel strips (0.2 x %g) spot-welded to both ends (pre-tabbed cell or a spot welder; never solder "
                      "on the can); front end = BAT+ (cell + towards the head): its strip is bent forward into the "
                      "antenna-spacer rebate and the 24 AWG wire soldered to it there; far end = BAT-: its strip is "
                      "bent into the lower -Y corner channel, the wire soldered there runs forward in the channel" % p.strip_w,
        "heat_path": "the cell touches the body only along the two rails (through the tape) and through the foam: "
                     "weakly coupled; no thermal pad (a gap pad pressed over the cell length would load the lid with "
                     "tens of newtons)",
    }
    if parts is not None:
        hp = {k: parts[k] for k in ("FlashKa_tray", "FlashKa_lid", "FlashKa_rf_window", "FlashKa_antenna_spacer")}
        for k in CELL_CASES:
            cp = cell_parts(p, k)
            solids = list(cp.values())
            rep["interference %s (mm3)" % CELL_CASE_NAMES[k]] = {
                n: round(sum(_vol(v, c) for c in solids), 4) for n, v in hp.items()}
    return rep


def wire_report(p, parts=None, dummies=None):
    """LED wires (24 AWG), cell wires (4 x 24 AWG), laser (28 AWG): sizes of the paths"""
    od = 1.05                               # 24 AWG PTFE (M22759/11 class), outside diameter used for the checks
    rb, gw, gd = p.opt_bore / 2, p.wire_groove[0], p.wire_groove[1]
    cy0, cy1, cz0, _ = cell_wire_channel(p)
    yw = max(cy0, -p.inner_half)
    z_mod = p.Z_pcb_top                    # module PCB underside above the rebate
    # at the spacer front face the tray's ledge-block corner (R inner_r of the full-width cavity behind X_pcb1)
    # narrows the rebate below the ledge top
    R_, xf = p.inner_r, p.X_pcb1 + 0.15
    y_corner = -(p.inner_half - R_) - math.sqrt(max(R_ * R_ - (p.X_pcb1 + R_ - xf) ** 2, 0.0))
    w_front = cy1 - y_corner
    (yt, zt), (yb, zb) = led_wire_hole_yz(p)
    rep = {
        "wire_od_used_mm (24 AWG PTFE)": od,
        "led_groove_width": gw, "led_groove_side_play": round((gw - od) / 2, 3),
        "led_radial_room_beside_the_board": round(rb + gd - p.mcpcb_d / 2, 3),
        "led_radial_play": round(rb + gd - p.mcpcb_d / 2 - od, 3),
        "led_hole_d": p.ledwire_d, "led_hole_play": round((p.ledwire_d - od) / 2, 3),
        "led_holes_on_the_groove_line": "hole axis r %.2f from the optic axis = groove channel centre "
                                        "(r %.3f .. %.3f): the wire runs straight, none passes under the LED board"
                                        % (p.led_wire_r, p.mcpcb_d / 2, rb + gd),
        "led_hole_exit_upper_y_z": [round(yt, 3), round(zt, 3)], "led_hole_exit_lower_y_z": [round(yb, 3), round(zb, 3)],
        "led_hole_end_x (upper, lower: through the cavity corner R%g)" % p.inner_r: led_wire_hole_x_end(p),
        "cell_wire_rebate_y": [round(yw, 3), cy1], "cell_wire_rebate_z": [round(cz0, 3), z_mod],
        "cell_wire_rebate_section": [round(cy1 - yw, 3), round(z_mod - cz0, 3)],
        "cell_wire_rebate_section_under_the_main_board": [round(cy1 - yw, 3), round(p.Z_pcb_bot - cz0, 3)],
        "cell_wire_rebate_width_at_the_spacer_front (inside the tray's ledge-block corner)": round(w_front, 3),
        "cell_wires (2 x 24 AWG side by side)": [round(2 * od, 3), round(od, 3)],
        "cell_wires_margin_in_the_rebate (narrowest width, height under the board)": [round(w_front - 2 * od, 3),
                                                                                      round(p.Z_pcb_bot - cz0 - od, 3)],
        "cell_channel": cell_channel_report(p),
        "kb_to_main_board_gap_z": [p.kb_z1, p.Z_pcb_bot],
        "laser_wires": "28 AWG, unchanged (beside the laser module under the main board)",
    }
    if parts is not None:
        tray = parts["FlashKa_tray"]
        out = {}
        for i, ((y, z), xe) in enumerate(zip(led_wire_hole_yz(p), led_wire_hole_x_end(p))):
            w = cyl_x(y, z, od, p.x_led_board, xe)
            nm = "upper" if i == 0 else "lower"
            out["wire d%.2f %s vs tray (mm3)" % (od, nm)] = round(_vol(tray, w), 4)
            out["wire %s: clearance to the tray" % nm] = round(_dist(tray, w), 3)
            if dummies is not None:
                out["wire %s: clearance to the LED board" % nm] = round(_dist(dummies["mcpcb"], w), 3)
                out["wire %s: clearance to the optic holder" % nm] = round(_dist(dummies["optic_holder"], w), 3)
        rep["led_wire_passage"] = out
    return rep


WIRE_OD = 1.05                              # 24 AWG PTFE (M22759/11 class): outside diameter used for the paths
LED_PADS = {"LED+": (_dx(9.85), -3.675, "top"), "LED-": (_dx(10.25), 1.7, "bottom")}   # main board J3 (PCB frame + dx)
CELL_PADS = {"BAT+": (_dx(31.3), -3.15), "BAT-": (_dx(31.3), -6.15)}                    # main board J2, bottom face


def _rod(pts, d):
    """chain of cylinders of diameter d through the points, with balls at the inner corners"""
    out = None
    for a, b in zip(pts, pts[1:]):
        va, vb = cq.Vector(*a), cq.Vector(*b)
        v = vb - va
        seg = cq.Solid.makeCylinder(d / 2, v.Length, va, v.normalized())
        out = seg if out is None else out.fuse(seg)
    for c in pts[1:-1]:
        out = out.fuse(cq.Solid.makeSphere(d / 2, cq.Vector(*c), angleDegrees1=-90, angleDegrees2=90))
    return out


def cell_wire_points(p):
    """centre lines of the two cell wires: {name: [(x, y, z), ...]} from the joints to 0.6 below the J2 pads.  The
    far-end wire (BAT-) runs forward in the lower -Y corner channel of the bay, rises beside the cell's front end into
    the antenna-spacer rebate (on its -Y side) and goes to J2 BAT-; the front wire (BAT+) starts at its joint in the
    rebate and keeps to the +Y side of it, so the two never cross"""
    yj, zj = CHANNEL_YZ
    yf, zf = FRONT_JOINT_YZ
    d, ln = cell_case(p, "nominal")
    x0, x1 = cell_x0(p), cell_x0(p) + ln
    zr = p.kb_z1 + 0.4 + WIRE_OD / 2 + 0.275           # in the rebate, over its floor
    xs = p.X_pcb1 + 0.15                                 # spacer front face
    xb, yp = CELL_PADS["BAT+"]
    _, ym = CELL_PADS["BAT-"]
    zp = p.Z_pcb_bot - 0.6
    return {
        "cell wire, far end (BAT-)": [(x1 - 2.6, yj, zj), (x0 + 3.0, yj, zj), (p.X_batt0 + 0.25, -7.7, zr),
                                      (x0 - 2.85, -7.6, zr), (xs + 0.6, -6.2, zr), (xs - 0.25, -6.25, zr + 0.2),
                                      (xb + 0.3, ym, zp)],
        "cell wire, front end (BAT+)": [(x0 - 2.8, yf + 0.1, zf + 0.8), (xs + 0.6, yf + 0.3, zf + 1.6),
                                        (xs - 0.25, yf + 0.5, zf + 1.8), (xb + 0.3, yp, zp)],
    }


def cell_channel_report(p):
    """the lower -Y corner channel at its working point: room round a 24 AWG wire for the extreme cells"""
    yj, zj = CHANNEL_YZ
    rt2 = math.sqrt(2)
    k_b = p.W / 2 - p.C_edge - p.wall * rt2           # inner bottom diagonal: |y| - z = k_b
    to_chamfer = (k_b - (abs(yj) - zj)) / rt2
    rep = {"point_y_z": [yj, zj], "to_the_floor_diagonal": round(to_chamfer, 3), "to_the_side_wall": round(p.inner_half - abs(yj), 3),
           "to_the_floor": round(zj - p.floor, 3), "to_the_rail": round(abs(yj) - (p.rail_y + p.rail_w), 3)}
    for k in ("f15_min", "max"):
        d, _ = cell_case(p, k)
        rep["to the cell (%s)" % CELL_CASE_NAMES[k]] = round(math.hypot(yj, zj - cell_centre_z(p, d)) - d / 2, 3)
    rep["free_radius (round a d%g wire: %g)" % (WIRE_OD, WIRE_OD / 2)] = round(min(v for k, v in rep.items()
                                                                                if k != "point_y_z"), 3)
    return rep


def wire_corridors(p):
    """free paths of the wires (fit check against the real boards): the two LED wires from the hole exits in the head
    rear face to 0.6 short of their J3 pads, and the two cell wires (cell_wire_points) from their joints to below the
    J2 pads.  {name: solid}"""
    od = WIRE_OD
    (yt, zt), (yb, zb) = led_wire_hole_yz(p)
    xet, xeb = led_wire_hole_x_end(p)
    xp, yp, _ = LED_PADS["LED+"]
    xm, ym, _ = LED_PADS["LED-"]
    out = {
        "LED+ wire": _rod([(xet, yt, zt), (xet + 0.4, yt, zt), (xp, yp, p.Z_pcb_top + 0.6)], od),
        "LED- wire": _rod([(xeb, yb, zb), (xeb + 0.3, yb, zb), (xm, ym - 0.6, zb + 0.5),
                           (xm, ym, p.Z_pcb_bot - 0.6)], od),
    }
    for nm, pts in cell_wire_points(p).items():
        out[nm] = _rod(pts, od)
    return out


def _section_area(tool, axis, value, t=0.01):
    big = 500.0
    lo, hi = value - t / 2, value + t / 2
    box = {"x": (lo, hi, -big, big, -big, big), "y": (-big, big, lo, hi, -big, big),
           "z": (-big, big, -big, big, lo, hi)}[axis]
    return _vol(tool, rbox(*box)) / t


def section_report(p):
    """the octagonal section: overall size, facet widths, area and perimeter of the outline"""
    hw, H, c = p.W / 2, p.H, p.C_edge
    rt2 = math.sqrt(2)
    pts = section_pts(p)
    area = 0.5 * abs(sum(pts[i][0] * pts[(i + 1) % 8][1] - pts[(i + 1) % 8][0] * pts[i][1] for i in range(8)))
    return {"width_x_height": [p.W, p.H], "facet_leg_45deg": c,
            "facets_mm (bottom, top, side, diagonal)": [round(p.W - 2 * c, 3), round(p.W - 2 * c, 3),
                                                        round(H - 2 * c, 3), round(c * rt2, 3)],
            "outline_perimeter_mm": round(2 * (p.W - 2 * c) + 2 * (H - 2 * c) + 4 * c * rt2, 3),
            "outline_area_mm2": round(area, 3),
            "lid_seat_z (parting line on the side facets)": p.Z_lid,
            "inside (Y x Z between the walls)": [round(2 * p.inner_half, 3), round(p.Z_ceil - p.floor, 3)]}


def thermal_inputs(p, parts, plain=None, dummies=None):
    """numbers for the LuxLibre thermal simulator (housing side), from the solids"""
    tray, lid = _shape(parts["FlashKa_tray"]), _shape(parts["FlashKa_lid"])
    rho = DENS["Al"]
    env = _shape(envelope(p))
    a_env = env.Area()
    # openings in the outer surface that are not aluminium (filled by the optic, laser, keys, POM windows ...)
    ops = {"optic bore (front)": _section_area(optic_bore(p), "x", 0.0),
           "laser bore (front)": _section_area(cyl_x(p.Y_l, p.Z_las, p.las_d + p.las_clear, -1, 1), "x", 0.0)}
    for k, o in zip(("next", "main", "prev"), key_openings(p)):
        ops["key opening %s" % k] = _section_area(o, "z", 0.0)
    ops["floor RF window"] = _section_area(floor_rf_opening(p), "z", 0.0)
    ops["lid RF window"] = _section_area(rf_window_outline(p, 0.0, p.H - 1, p.H + 1), "z", p.H)
    w, h, r = p.usb_open
    c = p.usb_open_chamfer
    ops["USB-C opening"] = _section_area(slot_y(p.X_usb, p.Z_usb, w + 2 * c, h + 2 * c, r + c, -p.W / 2 - 1,
                                                -p.W / 2 + 0.5), "y", -p.W / 2)
    w2, h2, r2 = p.s2_slot
    ops["S2 slot"] = _section_area(slot_y(p.X_s2, p.Z_pcb_top + p.s2_knob_z, w2, h2, r2, p.W / 2 - 0.5, p.W / 2 + 1),
                                   "y", p.W / 2)
    ops["lanyard slot (top + bottom)"] = 2 * (math.pi * (p.lan_slot_w / 2) ** 2 + (p.lan_slot_len - p.lan_slot_w) * p.lan_slot_w)
    a_ops = sum(ops.values())

    def cut_x(sh, x0, x1):
        return _vol(sh, rbox(x0, x1, -50, 50, -50, 50))
    v_tray, v_lid = tray.Volume(), lid.Volume()
    v_head = cut_x(tray, -1.0, p.L_head)
    v_head_lid = cut_x(lid, -1.0, p.L_head)
    v_slab = cut_x(tray, p.D_w, p.L_head)
    disk = cyl_x(p.Y_w, p.Z_axis, p.mcpcb_d, p.D_w, p.D_w + 0.01)
    contact = _vol(tray, disk) / 0.01
    rep = {
        "material": "6061-T6 aluminium, density %.2f g/cm3 (masses below)" % (rho * 1000),
        "mass_tray_g": round(v_tray * rho, 2), "mass_lid_g": round(v_lid * rho, 2),
        "mass_tray_plus_lid_g": round((v_tray + v_lid) * rho, 2),
        "outer_surface_mm2 (closed light, envelope incl. chamfers)": round(a_env, 1),
        "outer_surface_aluminium_mm2 (envelope minus the openings listed)": round(a_env - a_ops, 1),
        "openings_mm2": {k: round(v, 2) for k, v in ops.items()},
        "head_block_mass_g (tray X 0 .. %g)" % p.L_head: round(v_head * rho, 2),
        "lid_over_the_head_mass_g (X %g .. %g)" % (p.lid_x0, p.L_head): round(v_head_lid * rho, 2),
        "solid_behind_the_led_board_mass_g (X %g .. %g)" % (round(p.D_w, 3), p.L_head): round(v_slab * rho, 2),
        "led_board_to_head_contact_mm2 (d%.1f board on the bore floor, minus the wire-hole slivers)" % p.mcpcb_d:
            round(contact, 2),
        "led_board": "copper DTP d%.1f x %.1f, %.2f g (copper density 8.96 g/cm3), thermal paste %.2f mm" % (
            p.mcpcb_d, p.mcpcb_t, math.pi / 4 * p.mcpcb_d ** 2 * p.mcpcb_t * 8.96e-3, p.tim_t),
        "led_board_position_x_y_z": [round(p.x_led_board, 3), round(p.x_led_board + p.mcpcb_t, 3), p.Y_w, p.Z_axis],
        "distance_led_board_to_outer_faces_mm": {
            "-Y side face": round(p.W / 2 - abs(p.Y_w) - p.mcpcb_d / 2, 3),
            "lower -Y diagonal facet": round((p.W / 2 - p.C_edge - (abs(p.Y_w) - p.Z_axis)) / math.sqrt(2)
                                             - p.mcpcb_d / 2, 3),
            "bottom face": round(p.Z_axis - p.mcpcb_d / 2, 3),
            "head block top (lid seat; the lid lies on it)": round(p.Z_lid - p.Z_axis - p.mcpcb_d / 2, 3),
            "top face (head block + lid)": round(p.H - p.Z_axis - p.mcpcb_d / 2, 3),
            "front face (along the axis)": round(p.x_led_board, 3)},
        "section": section_report(p),
        "cell": {"part": "Vapcell INR14500 F15 (maker: about %g g, 14.0 +/-0.2 x 49.0 +/-0.3)" % p.cell_mass_g,
                 "mass_g (maker, about)": p.cell_mass_g,
                 "axis_y_z (nominal cell)": [0.0, round(cell_centre_z(p, p.cell_d), 3)],
                 "x": [round(cell_x0(p), 3), round(cell_x0(p) + p.cell_len, 3)],
                 "contact_to_the_body": "two line contacts along the rails (|Y| %g, X %g..%g) through polyimide tape "
                                        "%g; foam strip to the lid; nickel strips and wires to the board: weakly "
                                        "coupled" % (p.rail_y, round(p.X_batt0 + 3.0, 3), round(p.X_batt1 - 3.0, 3),
                                                     p.cell_tape)},
    }
    if plain is not None:
        a_tex = tray.Area() + lid.Area() - _shape(plain[0]).Area() - _shape(plain[1]).Area()
        rep["texture_adds_mm2 (panel V texture, all faces)"] = round(a_tex, 1)
    if dummies is not None:
        rep["optic_mass_g (PMMA lens 1.19 + PC holder 1.20 g/cm3, drawn shape)"] = round(
            _shape(dummies["optic_lens"]).Volume() * 1.19e-3 + _shape(dummies["optic_holder"]).Volume() * 1.20e-3, 3)
    return rep


# PCB-frame copy of the interface blocks that the KiCad tools read
_X_KEYS = ("x", "x0", "x1", "x_onboard_end", "x_exit")


def to_pcb_frame(obj, dx=PCB_DX):
    """housing frame -> PCB frame (X - dx): every 'x', 'x0', 'x1', 'x_onboard_end', 'x_exit' value, the first number
    of the rows of 'pogo_pins' / 'holes', the X pair of a 'bbox' and the 'X..' in a support name"""
    import re
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in _X_KEYS and isinstance(v, (int, float)) and not isinstance(v, bool):
                out[k] = round(v - dx, 4)
            elif k in ("pogo_pins", "holes") and isinstance(v, (list, tuple)):
                out[k] = [[round(q[0] - dx, 4)] + list(q[1:]) for q in v]
            elif k == "bbox" and isinstance(v, (list, tuple)) and len(v) == 4:
                out[k] = [round(v[0] - dx, 4), round(v[1] - dx, 4), v[2], v[3]]
            elif k == "what" and isinstance(v, str) and re.search(r"X\d", v):
                out[k] = re.sub(r"X(\d+(\.\d+)?)", lambda m: "X%g" % round(float(m.group(1)) - dx, 4), v)
            else:
                out[k] = to_pcb_frame(v, dx)
        return out
    if isinstance(obj, (list, tuple)):
        return [to_pcb_frame(v, dx) for v in obj]
    return obj


def pcb_frame_note(p):
    return {"dx": PCB_DX, "note": "pcb_outline, components and key_board are in the KiCad board frame (the frame of the "
                                  "first v0.7 layout, a 94.4 mm body): housing X = board X + %g. Everything else in this "
                                  "file is in the "
                                  "housing frame (X = 0 at the front face of the %.1f mm body)." % (PCB_DX, p.L)}


def _norm(o):
    """JSON-normalised value with the floats rounded to 4 decimals (comparisons of interface blocks)"""
    o = json.loads(json.dumps(o, default=str))

    def r(v):
        if isinstance(v, float):
            return round(v, 4)
        if isinstance(v, list):
            return [r(q) for q in v]
        if isinstance(v, dict):
            return {k: r(q) for k, q in v.items()}
        return v
    return r(o)


# --------------------------------------------------------------------------
DENS = {"Al": 2.70e-3, "POM": 1.41e-3, "PMMA": 1.19e-3, "rubber": 1.15e-3, "steel": 7.93e-3}
PART_MAT = {"FlashKa_tray": "Al", "FlashKa_lid": "Al", "FlashKa_rf_window": "POM", "FlashKa_antenna_spacer": "POM",
            "FlashKa_laser_sleeve": "POM", "FlashKa_key_main": "PMMA",
            "FlashKa_key_side": "rubber", "FlashKa_key_side_prev": "rubber", "FlashKa_key_stiffener": "steel",
            "FlashKa_key_stiffener_prev": "steel"}


def export_shape(s, path_noext, step=True, stl=True, tol=0.015):
    if step:
        cq.exporters.export(s, path_noext + ".step")
    if stl:
        cq.exporters.export(s, path_noext + ".stl", tolerance=tol, angularTolerance=0.1)
        _clean_stl(path_noext + ".stl")


def export_key_with_plate(p, parts, path):
    """the next key as built: cast rubber body, stiffener plate and doubler glued in (three solids) in one STEP"""
    plate, doub = build_key_stiffener(p, p.X_next, pieces=True)
    asm = cq.Assembly(name="FlashKa_key_side_with_plate")
    asm.add(parts["FlashKa_key_side"], name="rubber_body", color=cq.Color(0.04, 0.04, 0.04))
    asm.add(plate, name="stiffener_plate_stainless_steel", color=cq.Color(0.62, 0.64, 0.68))
    asm.add(doub, name="doubler_stainless_steel", color=cq.Color(0.62, 0.64, 0.68))
    asm.export(path, "STEP")


def export_stiffener_pieces(p, path):
    """FlashKa_key_stiffener.step: the plate and the doubler as two solids in their glued position (next key)"""
    plate, doub = build_key_stiffener(p, p.X_next, pieces=True)
    cq.exporters.export(cq.Workplane().add(cq.Compound.makeCompound([plate.val(), doub.val()])), path)


def _clean_stl(path):
    """drop the zero-area triangles that the mesher leaves at the corners of the ring grooves and drill points"""
    try:
        import trimesh
    except ImportError:
        return
    m = trimesh.load(path, process=True)
    m.update_faces(m.nondegenerate_faces(height=1e-7))
    m.remove_unreferenced_vertices()
    m.export(path)


def housing_summary(p, info):
    """summary: section, lengths, optic seat, LED board, bay and cell, wire paths, thermal-model inputs (for the
    firmware simulator and the docs)"""
    o, b, t = info["optic_seat"], info["bay"], info["thermal_model_inputs"]
    wp = info["wire_paths"]
    nom = b["cases"][CELL_CASE_NAMES["nominal"]]
    return {
        "total_length_mm": round(p.L, 3), "head_length_mm": p.L_head, "cross_section_mm": [p.W, p.H],
        "section": t["section"],
        "optic": {"part": "LEDiL LISA3-RS-PIN (FP16558), pins cut off, glued on the holder rim",
                  "bore_d": p.opt_bore, "front_face_x (min, nom, max)": o["optic_front_face_x (min, nominal, max over the height tolerance)"],
                  "seat_x (holder on the LED board front face = LED level)": round(p.x_led_board, 3),
                  "height_above_led_board": p.opt_h, "exit_d (unverified callout)": p.opt_exit_d},
        "led_board": {"d": p.mcpcb_d, "t": p.mcpcb_t, "x_front": round(p.x_led_board, 3),
                      "x_back": round(p.x_led_board + p.mcpcb_t, 3), "paste_mm": p.tim_t,
                      "bore_floor_x": round(p.D_w, 3), "axis_y": p.Y_w, "axis_z": p.Z_axis,
                      "solid_behind_mm": round(p.L_head - p.D_w, 3)},
        "bay": {"x": b["bay_x"], "length": b["bay_length"], "section": b["bay_section"], "rails": b["rails"],
                "cell": "1 x Vapcell INR14500 F15 (14.0 x 49.0; any flat-top 14500 up to %g x %g)" % p.cell_max,
                "cell_axis_y_z (nominal)": [0.0, nom["axis_z"]], "cell_x (nominal)": t["cell"]["x"],
                "holding": b["holding"], "connection": b["connection"]},
        "wire_paths": {"cell": {k: [[round(c, 3) for c in q] for q in v] for k, v in cell_wire_points(p).items()},
                       "cell_channel": wp["cell_channel"]},
        "thermal_model_inputs": {
            "aluminium_mass_tray_plus_lid_g": t["mass_tray_plus_lid_g"],
            "mass_tray_g": t["mass_tray_g"], "mass_lid_g": t["mass_lid_g"],
            "cell_mass_g (maker, about)": p.cell_mass_g,
            "outer_surface_mm2": t["outer_surface_mm2 (closed light, envelope incl. chamfers)"],
            "outer_surface_aluminium_mm2": t["outer_surface_aluminium_mm2 (envelope minus the openings listed)"],
            "head_block_mass_g (tray X 0..%g)" % p.L_head: t["head_block_mass_g (tray X 0 .. %g)" % p.L_head],
            "lid_over_head_mass_g": t["lid_over_the_head_mass_g (X %g .. %g)" % (p.lid_x0, p.L_head)],
            "solid_behind_led_board_mass_g": t["solid_behind_the_led_board_mass_g (X %g .. %g)" % (round(p.D_w, 3),
                                                                                                  p.L_head)],
            "led_board_to_head_contact_mm2": [v for k, v in t.items() if k.startswith("led_board_to_head_contact")][0],
            "led_board_copper_mass_g": round(math.pi / 4 * p.mcpcb_d ** 2 * p.mcpcb_t * 8.96e-3, 3),
            "thermal_paste_mm": p.tim_t,
            "cell_coupling": t["cell"]["contact_to_the_body"]},
        "pcb_frame_dx": PCB_DX,
    }


def main(outdir, full_checks=True):
    import time
    t0 = time.time()
    os.makedirs(outdir, exist_ok=True)
    p = P()
    parts = housing_parts(p)
    extra = {"FlashKa_laser_sleeve": build_laser_sleeve(p)}
    dummies = build_dummies(p)
    kb = build_kb_standin(p)
    kb_free = build_kb_standin(p, pogo_state="free")
    print("parts built %.1f s" % (time.time() - t0), flush=True)
    # files: every part in place (housing frame); the prev key and its plate are reference copies for pictures
    for n, s in parts.items():
        if n.endswith("_prev"):
            export_shape(s, os.path.join(outdir, "_ref_" + n.replace("FlashKa_", "")), step=False)
        else:
            export_shape(s, os.path.join(outdir, n), tol=0.01 if "key" in n else 0.015)
    for n, s in extra.items():
        export_shape(s, os.path.join(outdir, n))
    for n, s in dummies.items():
        export_shape(s, os.path.join(outdir, "_ref_" + n), step=False, tol=0.02)
    for n, s in kb.items():
        export_shape(s, os.path.join(outdir, "_ref_" + n), step=False, tol=0.01)
    export_shape(ring_icon_solid(p), os.path.join(outdir, "_ref_ring_icon"), step=False, tol=0.005)
    export_shape(pad_solid(p), os.path.join(outdir, "_ref_pad"), step=False)
    if p.front_boss:
        export_shape(pad2_solid(p), os.path.join(outdir, "_ref_pad2"), step=False)
    export_shape(cq.Workplane().add(cq.Compound.makeCompound([s for _, s in lid_screws(p)])),
                 os.path.join(outdir, "_ref_lidscrews"), step=False, tol=0.01)
    export_shape(cq.Workplane().add(cq.Compound.makeCompound([s for _, s in kb_screws_detail(p)])),
                 os.path.join(outdir, "_ref_kbscrews"), step=False, tol=0.01)
    ring = cq.Solid.makeTorus(12.0, 0.7, pnt=cq.Vector(p.X_lan + 11.75, 0, p.H / 2), dir=cq.Vector(0, 1, 0))
    export_shape(cq.Workplane().add(ring), os.path.join(outdir, "_ref_splitring"), step=False, tol=0.02)
    export_key_with_plate(p, parts, os.path.join(outdir, "FlashKa_key_side_with_plate.step"))
    export_stiffener_pieces(p, os.path.join(outdir, "FlashKa_key_stiffener.step"))
    # machining kits for JLCCNC (own frame: kit X, Y, Z; not in the housing frame)
    kits = {"FlashKa_pmma_kit": build_pmma_kit(p), "FlashKa_pom_kit": build_pom_kit(p)}
    for n, (k, _, _) in kits.items():
        export_shape(k, os.path.join(outdir, n), stl=False)
    print("files written %.1f s" % (time.time() - t0), flush=True)

    vols = {n: round(_shape(s).Volume(), 1) for n, s in list(parts.items()) + list(extra.items())}
    valid = {n: _shape(s).isValid() for n, s in list(parts.items()) + list(extra.items())}
    bb = _shape(parts["FlashKa_tray"]).BoundingBox()
    info = {
        "version": VERSION,
        "params": {k: v for k, v in asdict(p).items()},
        "derived": {"L": p.L, "Z_lid": p.Z_lid, "Z_pcb_top": p.Z_pcb_top, "D_w": p.D_w, "X_pcb0": p.X_pcb0,
                    "X_pcb1": p.X_pcb1, "X_ant1": p.X_ant1, "Y_pcb": p.Y_pcb, "X_batt0": p.X_batt0, "X_batt1": p.X_batt1,
                    "X_lan": p.X_lan, "X_screw_front": p.screw_x_front, "X_screw_back": p.X_screw_back, "Z_usb": p.Z_usb,
                    "rf_window": p.rfw_box, "Z_sw_tip": round(p.Z_sw_tip, 4), "Z_led_face": round(p.Z_led_face, 4),
                    "main_key_top_z": round(p.main_top_z, 4), "main_nub_z": round(p.main_nub_z, 4),
                    "side_nub_z": round(p.side_nub_z, 4), "kb_z_top": p.kb_z1, "pogo_working_height": round(p.pogo_h, 4),
                    "kb_screw_tip_z": round(p.kb_screw_tip_z, 4), "kb_tap_drill_z": round(p.kb_drill_z, 4),
                    "kb_tap_drill_apex_z": round(p.kb_drill_apex_z, 4), "lid_boss_h": round(p.boss_h, 4),
                    "pad_strain": round(p.pad_strain, 4)},
        "pcb_frame": pcb_frame_note(p),
        "pcb_outline": [[round(x - PCB_DX, 4), round(y, 4)] for x, y in pcb_outline(p)],
        "components": to_pcb_frame(component_positions(p)),
        "key_board": to_pcb_frame({"outline": {"x0": p.kb_x0, "x1": p.kb_x1, "y0": -p.kb_y, "y1": p.kb_y, "corner_r": p.kb_r},
                      "z_bottom": p.kb_z0, "z_top": p.kb_z1, "holes": [list(h) for h in p.kb_holes], "hole_d": p.kb_hole_d,
                      "screw": "M1.6 x %g pan head, stainless steel" % p.kb_screw_len,
                      "support_areas_on_the_KB_bottom_face": [
                          {"what": nm, "bbox": [round(v, 3) for v in (_shape(s).BoundingBox().xmin, _shape(s).BoundingBox().xmax,
                                                                     max(_shape(s).BoundingBox().ymin, -p.kb_y),
                                                                     min(_shape(s).BoundingBox().ymax, p.kb_y))]}
                          for nm, s in kb_supports(p)],
                      "pogo_pins": [list(q) for q in p.pogo_pins], "pogo_part": p.pogo_part}),
        "panel_layout": [{k: (round(v, 3) if isinstance(v, float) else v) for k, v in q.items()} for q in panel_layout(p)],
        "volumes_mm3": vols,
        "mass_g": {n: round(v * DENS[PART_MAT[n]], 3) for n, v in vols.items()},
        "tray_bbox": [round(v, 3) for v in (bb.xmin, bb.xmax, bb.ymin, bb.ymax, bb.zmin, bb.zmax)],
        "solids_valid": valid,
        "min_walls": min_wall_report(p),
        "rf_windows": rf_window_sizes(p),
        "pogo_stack": pogo_stack(p),
        "pad_stack": pad_stack(p),
        "key_tolerance_stack": key_tolerance_stack(p),
        "side_key_chevron": {
            "stroke": p.chevron[0], "height": p.chevron_h, "apex_angle_deg": round(2 * math.degrees(math.atan2(
                p.chevron[2], 2 * p.chevron[1])), 2),
            "overall_x": round(2 * p.chevron[1] + p.chevron[0], 3), "overall_y": round(2 * p.chevron[2] + p.chevron[0], 3),
            "next_key": "X %g: apex towards the head (-X)" % p.X_next,
            "previous_key": "X %g: apex towards the tail (+X), the same part turned 180 deg" % p.X_prev,
            "reading": "held like a presenter (head towards the screen, keys up): the key nearest the head reads '^' "
                       "(next), the key nearest the hand 'v' (previous)"},
        "machining_kits": {n: v[1] for n, v in kits.items()},
        "laser_retention": laser_retention_report(p, scan=full_checks),
        "optic_seat": optic_report(p),
        "bay": bay_report(p, parts if full_checks else None),
        "wire_paths": wire_report(p, parts, dummies),
    }
    plain = (build_tray(p, texture="none"), build_lid(p, texture="none")) if full_checks else None
    info["thermal_model_inputs"] = thermal_inputs(p, parts, plain, dummies)
    info["summary"] = housing_summary(p, info)
    print("optic / bay / wire / thermal reports done %.1f s" % (time.time() - t0), flush=True)
    hparts = {k: v for k, v in parts.items()}
    skip = {("FlashKa_tray", "kb_screw1"), ("FlashKa_tray", "kb_screw2")}
    for k in ("FlashKa_key_stiffener", "FlashKa_key_stiffener_prev"):
        hparts.pop(k)
    info["interference_main_board_centred"] = interference(hparts, dummies)
    info["interference_main_board_at_-Y"] = interference(hparts, dummies, -p.pcb_side_gap + 0.01)
    info["interference_main_board_at_+Y"] = interference(hparts, dummies, p.pcb_side_gap - 0.01)
    info["interference_key_board"] = interference(hparts, kb, skip=skip)
    kbd = {k: v for k, v in kb.items() if not k.endswith("_pl")}
    info["interference_key_board_vs_main_board"] = interference(kbd, dummies)
    print("interference done %.1f s" % (time.time() - t0), flush=True)
    if full_checks:
        info["interference_part_to_part"] = parts_interference(parts)
        info["texture_and_grooves"] = texture_report(p)
        info["texture_min_metal_mm"] = min(r["metal_under_mm"] for r in info["texture_and_grooves"])
        info["texture_all_ok"] = all(r["ok"] for r in info["texture_and_grooves"])
        print("texture done %.1f s" % (time.time() - t0), flush=True)
        info["key_stroke"] = key_stroke_check(p, parts, kb)
        info["led_to_key_gap"] = led_gap_check(p, parts, kb)
        info["side_key_end_press"] = side_key_end_press(p, parts, kb)
        print("keys done %.1f s" % (time.time() - t0), flush=True)
        info["insertion_path"] = insertion_check(p, parts, dummies, kb_free)
        print("insertion done %.1f s" % (time.time() - t0), flush=True)
        fpin = pogo_stack(p)["force_per_pin_N (min, nominal, max incl. the +/-%.2f N spring tolerance)" % p.pogo_force_tol_n]
        fmax = fpin[2] / fpin[1]                     # maximum pin force relative to the nominal one
        info["holddown"] = holddown_report(p)
        info["holddown_soft_case (pads 0.7 E, gaps +0.1, pins at their maximum force)"] = holddown_report(
            p, e_scale=0.7, gap_extra=0.1, pogo_scale=fmax)
        info["holddown_hard_case (pads 1.3 E, gaps -0.1)"] = holddown_report(p, e_scale=1.3, gap_extra=-0.1)
        info["holddown_without_the_front_boss"] = holddown_report(p, front_boss=False)
        print("holddown done %.1f s" % (time.time() - t0), flush=True)
        singles = {"FlashKa_key_main.step": parts["FlashKa_key_main"], "FlashKa_rf_window.step": parts["FlashKa_rf_window"],
                   "FlashKa_antenna_spacer.step": parts["FlashKa_antenna_spacer"]}
        info["machining_kit_checks"] = {n: kit_checks(p, k, ki, pc, singles) for n, (k, ki, pc) in kits.items()}
        print("kits done %.1f s" % (time.time() - t0), flush=True)
    path = os.path.join(outdir, "housing_interface.json")
    if os.path.exists(path):      # the main-board positions are read by the PCB tools: never change them silently
        try:
            old = json.load(open(path))
        except Exception:
            old = {}
        if "pcb_outline" in old and _norm(old["pcb_outline"]) != _norm(info["pcb_outline"]):
            print("WARNING: pcb_outline differs from the file; the file's value is kept")
            info["pcb_outline"] = old["pcb_outline"]
        for k in MAIN_BOARD_KEYS:
            oc = old.get("components", {}).get(k)
            if oc is not None and _norm(oc) != _norm(info["components"][k]):
                print("WARNING: components.%s differs from the file; the file's value is kept" % k)
                info["components"][k] = oc
    with open(path, "w") as f:
        json.dump(info, f, indent=1, default=str)
    import order_files                       # the order folders carry copies of the STEP files: refresh them
    if order_files.is_package_cad(outdir):
        order_files.copy(("step",))
    print("total %.1f s" % (time.time() - t0), flush=True)
    return p, parts, dummies, kb, info


def interface_only(outdir):
    os.makedirs(outdir, exist_ok=True)
    p = P()
    path = os.path.join(outdir, "housing_interface.json")
    info = json.load(open(path)) if os.path.exists(path) else {}
    info.update({"version": VERSION, "params": {k: v for k, v in asdict(p).items()}, "pcb_frame": pcb_frame_note(p),
                 "pcb_outline": [[round(x - PCB_DX, 4), round(y, 4)] for x, y in pcb_outline(p)],
                 "components": to_pcb_frame(component_positions(p))})
    with open(path, "w") as f:
        json.dump(info, f, indent=1, default=str)
    return p


if __name__ == "__main__":
    if "--kb-interface" in sys.argv:            # read by P.__post_init__ (also in the scripts started from here)
        os.environ["FK_KB_INTERFACE"] = os.path.abspath(sys.argv[sys.argv.index("--kb-interface") + 1])
    args = [a for i, a in enumerate(sys.argv[1:]) if not a.startswith("--") and sys.argv[i] != "--kb-interface"]
    out = args[0] if args else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "cad")
    if "--interface-only" in sys.argv:
        p = interface_only(out)
        print("interface written, L =", round(p.L, 2))
        sys.exit(0)
    p, parts, dummies, kb, info = main(out, full_checks="--no-checks" not in sys.argv)
    print("L =", round(p.L, 2), " PCB X", round(p.X_pcb0, 2), "-", round(p.X_pcb1, 2), " bay", round(p.X_batt0, 2), "-",
          round(p.X_batt1, 2))
    for k in ("solids_valid", "mass_g", "min_walls", "rf_windows", "pogo_stack", "pad_stack", "key_tolerance_stack",
              "interference_main_board_centred", "interference_main_board_at_-Y", "interference_main_board_at_+Y",
              "interference_key_board", "interference_key_board_vs_main_board", "interference_part_to_part",
              "texture_min_metal_mm", "texture_all_ok", "texture_and_grooves", "key_stroke", "led_to_key_gap",
              "side_key_end_press", "insertion_path", "side_key_chevron", "laser_retention", "machining_kits",
              "machining_kit_checks", "optic_seat", "bay", "wire_paths", "thermal_model_inputs", "summary"):
        if k in info:
            print(k, json.dumps(info[k], indent=1, default=str))
    for k in info:
        if k.startswith("holddown"):
            print(k, json.dumps(info[k], indent=1, default=str))
