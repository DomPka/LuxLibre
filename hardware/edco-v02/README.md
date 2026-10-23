<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
# EDCO v0.2

EDCO v0.2 makes the EDCO light brighter and gives it a more rugged look, in **two sizes**:

| | EDCO-18 | EDCO-14 |
|---|---|---|
| Cell | one 18500 | one 14500 |
| Body / head | Ø24 / Ø26 mm | Ø20 / Ø22 mm |
| Length | 98.3 mm | 95.3 mm |

Both use a Luminus **SST-40** LED behind a TIR optic. Charging, firmware updates and settings all go through a
**USB-C port on the side of the head**, under a fluted **twist collar**. There is still no laser and no radio.

![EDCO-18, black anodised: crenellated and finned bezel, the fluted twist collar, the stainless button, six flats (render)](assets/edco18_hero.png)

*Render made from the design files.*

> **Status: concept (v0.2).** The housing of both sizes is modelled in CadQuery and checked for fits, walls
> and interference. The firmware board headers exist, and the light output is simulated with the LuxLibre
> simulator. The circuit boards are **not drawn yet**, and nothing has been built or measured. Every light
> figure on this page is simulated.

## What changed from v0.1

The owner asked for these changes:

* **About 2000 lm.** An SST-40 replaces the SST-20. Driving it near 6 A needs a cell that can deliver the
  current, so EDCO now comes in two sizes: an 18500 version for full output and a 14500 version that keeps the
  slim body.
* **USB-C on the side.** The socket now sits on the main board and looks down through a window in the side of
  the head. A collar turns over it: with the collar's window over the port, the port is open; turned away,
  the port is covered and sealed.
* **A more tactile look.**
  * A crenellated bezel with five cooling fins.
  * A fluted collar.
  * Six milled flats along the body.
  * Three grooves at the tail.
* **A bigger button.** The stainless cap grows from Ø4.2 to Ø7.5 mm (EDCO-18) or Ø6.5 mm (EDCO-14). Its
  translucent membrane glows when lit, so the separate indicator dot is gone.

| ![Front: crenellated bezel, fins, TIR optic with the SST-40 behind it (render)](assets/edco18_front.png) | ![The collar turned to open: the USB-C socket under the window (render)](assets/edco18_port_open.png) |
|---|---|
| **Front.** Crenellated bezel, fins, the TIR optic. | **Port open.** The collar's window over the USB-C socket. |
| ![Tail: grooves, flats and the lanyard holes (render)](assets/edco18_tail.png) | ![EDCO-18 and EDCO-14 side by side (render)](assets/edco_v02_sizes.png) |
| **Tail.** Grooves, flats and the two lanyard holes. | **Two sizes.** EDCO-18 (black) and EDCO-14 (clear anodised). |

## How it is built

![Half section of EDCO-18 (render)](assets/edco18_section.png)

From the front to the tail:

1. **Bezel.** It is crenellated and finned. It screws onto the band's external thread (M22 × 0.75 on
   EDCO-18, M18 × 0.75 on EDCO-14) and is locked with thread-locker. Its lip presses the optic onto a
   silicone gasket. Its inner shoulder clamps the head insert, metal on metal, against the band's front face.
2. **Head insert.** This is the LED holder. It has a cup for the optic and holds the SST-40 on its copper
   board, on a 2 mm floor that carries the heat into the body. A face O-ring on its rear face seals against
   the band. A key in a notch stops it turning while the bezel is tightened, so the LED wires never twist.
3. **Twist collar.** It turns freely between the bezel and the body shoulder. A moulded silicone gasket sits
   in a groove round the port window in the band. The collar's bore presses and wipes this gasket, so the
   port is sealed whenever the collar's window is turned away. The space between the collar and the band may
   get wet; the port window is the only opening into the light.
4. **Main board in a POM sled.** The board lies across the bore. The vertical USB-C socket on its underside
   looks down through the port window. The tactile switch on its top side sits under the button's light-pipe
   pin. The sled carries the axial load from the cell to the head.
5. **Cell.** Its + strip goes to the rear of the main board. The − strip runs forward along the bottom of the
   cell.
6. **Tail.** A closed end with three grooves and a lanyard hole through each corner. There is no tail board
   any more.

![Exploded view of EDCO-18 (render)](assets/edco18_exploded.png)
