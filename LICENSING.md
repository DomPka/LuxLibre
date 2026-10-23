<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
# Licensing

LuxLibre is free and open for everyone: hobbyists, schools and companies may use, study,
change, build and **sell** lights based on it. In return, improvements to the shared parts flow
back to everyone. This is the same model as ArduPilot, whose code is under the GPL version 3:
companies build and sell products with it, and publish the changes they ship.

*This page explains the licences in plain words. It is not legal advice; the licence texts in
[LICENSES/](LICENSES/) are what counts. If your business depends on the details, ask a lawyer.*

## Which licence covers what

| Part | Where | Licence | SPDX identifier |
|---|---|---|---|
| LuxLibre firmware, tools and scripts | `firmware/`, `tools/`, `.github/`, the Python generators in `hardware/*/tools/` and `hardware/*/docs/` | GNU General Public License v3.0 or later, with the [additional permission](#additional-permission-for-vendor-radio-libraries) below for the firmware | `GPL-3.0-or-later` |
| Hardware design files | schematics, PCB layouts, CAD, drawings (including their PDFs) and production files in `hardware/` | CERN Open Hardware Licence v2, Weakly Reciprocal | `CERN-OHL-W-2.0` |
| Documentation | `docs/`, `templates/`, README files, the build guides and design-chapter PDFs | Creative Commons Attribution-ShareAlike 4.0 | `CC-BY-SA-4.0` |
| FlashKa v0.5 Rust firmware, web app and web tools | `hardware/flashka-keychain-v05/firmware/`, `app/`, `tools/web/` | MIT or Apache 2.0, at your choice | `MIT OR Apache-2.0` |
| FlashKa Rust firmware (0.6.0 for v0.6 and 0.7.0 for v0.7, one code base), web app and web tools | `hardware/flashka-keychain-v06/firmware/`, `app/`, `tools/web/` | MIT or Apache 2.0, at your choice | `MIT OR Apache-2.0` |
| FlashKa v0.7 design files, scripts and documents | `hardware/flashka-keychain-v07/` (it has no firmware or web pages of its own: its firmware 0.7.0 and the web pages come from the v0.6 folder, row above) | as for v0.6: design and production files CERN-OHL-W-2.0, the Python generators (`tools/`, `docs/build_pdf.py`) GPL-3.0-or-later, the documents and their PDFs CC-BY-SA-4.0 | `CERN-OHL-W-2.0`, `GPL-3.0-or-later`, `CC-BY-SA-4.0` |
| EDCO v0.1 design files, scripts and documents | `hardware/edco-v01/` (its firmware is the LuxLibre firmware, board `firmware/boards/edco-v01/`) | design files (CAD, STEP) CERN-OHL-W-2.0, the Python generators (`tools/`) GPL-3.0-or-later, the documents and pictures CC-BY-SA-4.0 | `CERN-OHL-W-2.0`, `GPL-3.0-or-later`, `CC-BY-SA-4.0` |
| Project web site (GitHub Pages) | `site/` | MIT or Apache 2.0, at your choice | `MIT OR Apache-2.0` |
| Generated AVR register header | `firmware/ports/attiny1616/tiny1x_io.h` | Apache License 2.0 (Microchip's device description) | `Apache-2.0` |

Source files name their licence in their first lines (`SPDX-License-Identifier: ...`); that line
wins over this table. Design and data files that cannot carry such a line (KiCad, STEP, STL,
DXF, Gerbers, CSV, spreadsheets, images, PDFs) take the licence of their row in this table. The
root [LICENSE](LICENSE) file holds the GPL text because the firmware is the largest part; all
licence texts are in [LICENSES/](LICENSES/).

## What you may do

With every part of LuxLibre you may, for any purpose including commercial ones:

- use it, study it and change it;
- build lights from it, for yourself or for sale;
- copy and share it, changed or unchanged.

## What you must do when you give a light or the files to others

Nothing is required for private use or for lights you keep. The duties start when you
**distribute**: sell or give away lights, firmware images or design files.

### Firmware (GPL-3.0-or-later)

- **Share the source.** Everyone who receives a light or a firmware image from you must be able
  to get the complete corresponding source code of that firmware, including your changes and
  your board header, under the same licence. Either ship the source with the product, or give a
  written offer (for example a link in the manual) that stays valid for at least three years and
  for as long as you offer spare parts or customer support for that product (GPL-3.0 section 6).
- **Keep the notices** (copyright and licence lines) and add a note that you changed the files.
- **Let users install modified firmware.** For consumer products, GPLv3 asks for the
  information needed to install a modified version ("Installation Information"). If your light
  has a locked bootloader, you must provide the way to unlock it.
- **No extra restrictions**: you cannot add terms that take away these rights.

### Hardware design files (CERN-OHL-W-2.0)

- **Products:** when you make and convey lights based on a LuxLibre design, give each recipient
  the source of the design or tell them where to find it (the "Source Location", for example a
  link in the manual or on the light) (section 4.1 of the licence).
- **Modified designs** stay under CERN-OHL-W-2.0: publish your changes to the covered design
  files and mark them as modified (section 3.3).
- **Your own additions can stay yours.** Parts that are not derived from the LuxLibre design and
  only connect to it ("External Material", for example your own separate module or housing
  accessory) do not have to be published (section 4.2). This is the "weakly" in weakly
  reciprocal.
- You may sell your products under your own terms, as long as they do not restrict anyone's
  rights to the covered design source (section 4.3).

### Documentation (CC-BY-SA-4.0)

- Give credit ("based on LuxLibre documentation", with a link), say what you changed, and share
  changed documentation under CC-BY-SA-4.0. Commercial use is allowed.
- **Templates:** documents you fill in from [templates/](templates/) are yours; you do not need
  to credit LuxLibre in them or license them under CC-BY-SA ([templates/README.md](templates/README.md)).

### FlashKa Rust firmware, web tools and web site (MIT OR Apache-2.0)

Permissive: keep the copyright and licence notice; no duty to share changes. The firmware links
Espressif's binary-only radio libraries for Bluetooth, which these licences allow. The built
installer pages (`app/aurora-flasher.html` of v0.5, `app/flashka-flasher.html` of v0.6) also
contain esptool-js (Apache-2.0, Espressif Systems) and pako (MIT and Zlib). Both pages keep the
libraries' licence comments; the v0.6 page also names both in its header comment and its footer.

### Names

The licences cover the files, not the names. How to use "LuxLibre" and "FlashKa" for your own
products is explained in [TRADEMARKS.md](TRADEMARKS.md).

## Additional permission for vendor radio libraries

Wireless microcontrollers need binary-only libraries from the chip maker for their radio and PHY
(for example Espressif's Bluetooth and Wi-Fi libraries for the ESP32 family). Without an
exception, the GPL would not allow distributing firmware that links them. Therefore:

> As an additional permission under section 7 of the GNU General Public License version 3, the
> copyright holders of the LuxLibre firmware give you permission to combine the firmware with the
> binary-only libraries that a microcontroller maker distributes in its software development kit
> for the radio, PHY and low-level hardware support of its chips, and to convey the resulting
> firmware, without providing source code for those libraries. All other parts of the firmware
> stay under the GPL. If you modify the firmware, you may extend this permission to your version,
> or remove it.

The current LuxLibre firmware does not use such libraries yet; the permission is there so that a
Bluetooth version can be distributed.

## Frequently asked questions

**Can my company sell flashlights that run LuxLibre?**
Yes. Publish the firmware source you ship (with your changes and board header), let users
install their own builds, and follow the name rules in [TRADEMARKS.md](TRADEMARKS.md).

**Do I have to publish my own PCB if I only use the LuxLibre firmware?**
No. The firmware licence covers the firmware. A board you designed yourself, without starting
from LuxLibre hardware files, is yours. Only the board header (the pins and limits in
`firmware/boards/<board>/board.h`) is part of the firmware source and is shared with it.

**I started from the FlashKa PCB and changed it. What now?**
Your changed design files are a modified version of a CERN-OHL-W-2.0 design: when you sell
lights made from them, publish the changed design files under the same licence and tell buyers
where to find them.

**Can I write a closed-source phone app that talks to a LuxLibre light?**
In general, a separate program that talks to the firmware over its console or a wireless
protocol is not a modified version of the firmware, so the GPL does not cover it. Code you copy
from LuxLibre into the app is a different case.

**Can I put LuxLibre firmware into a product that uses a closed-source library?**
Only if the complete source of that library can be provided under terms compatible with the
GPL version 3, if it is a "System Library" in the sense of GPL-3.0 section 1, or if it is a chip
maker's radio or PHY library covered by the
[additional permission](#additional-permission-for-vendor-radio-libraries) above. Otherwise
keep the closed part outside the firmware (for example on a separate chip).

**Why "or later" for the GPL?**
It lets the project move to a future GPL version if one is needed, without asking every past
contributor.

**What about safety and warranty?**
All these licences come without warranty. Whoever builds and sells a light is responsible for it
meeting the laws of the market it is sold in; [SAFETY.md](SAFETY.md) and
[docs/design-rules.md](docs/design-rules.md) help, but they do not replace testing and
certification.

## Third-party material

- `firmware/ports/attiny1616/tiny1x_io.h` is generated from Microchip's ATDF device description
  of the ATtiny1617 (Copyright (c) 2018 Microchip Technology Inc., Apache License 2.0), as
  distributed in the vendor folder of the `avr-device` crate. The generator script
  `atdf_to_header.py` is GPL-3.0-or-later.
- `firmware/ports/ch32v003/ch32v003_regs.h` takes register addresses and bit positions from the
  `ch32-metapac` crate (MIT OR Apache-2.0), generated from WCH's SVD files, and from the CH32V003
  reference manual.
- `hardware/flashka-keychain-v05/app/aurora-flasher.html` and
  `hardware/flashka-keychain-v06/app/flashka-flasher.html` bundle esptool-js 0.7.0 (Apache-2.0)
  and pako (MIT and Zlib).
- The licence texts in [LICENSES/](LICENSES/) are by their respective authors.

## Contributions

Contributions are accepted under the licence of the files they change ("inbound = outbound",
including the additional permission for the firmware), with a Developer Certificate of Origin
sign-off on every commit. Details: [CONTRIBUTING.md](CONTRIBUTING.md).
