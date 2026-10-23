<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
[LuxLibre](README.md) › Safety

# Safety

Flashlights look simple, but a modern one combines a lithium cell that can burn, a light source
that can hurt eyes, surfaces that can burn skin and sometimes a laser. Read this before you
build, test or hand a LuxLibre light to someone else. The design rules in
[docs/design-rules.md](docs/design-rules.md) turn these risks into checkable requirements.

## Lithium cells

- A shorted, punctured, crushed, overheated or over-charged Li-ion or LiPo cell can vent hot
  gas and catch fire. Never short a cell (keys and coins in a pocket can do it), never pierce or
  bend one, and stop using cells with damaged wrappers or dents.
- Charge on a non-flammable surface, away from paper and fabric, and stay nearby during the
  first charges of a new design. Never charge a light that has been under water and not dried
  and checked, or that has been dropped hard and smells or feels warm when off.
- Use cells from known makers with a datasheet ([BAT-1](docs/design-rules.md#bat-1)); fake
  cells are common.
- Store lights and cells at room temperature, ideally partly charged for long storage.
- Shipping cells or lights with cells is regulated as dangerous goods; ask the carrier.

## Light

- High-output LEDs can damage eyes, and a focused beam stays hazardous over a long distance
  ([LED-5](docs/design-rules.md#led-5)). Do not stare into the beam, do not shine it into
  people's eyes, and never at drivers, pilots or aircraft.
- UV and IR emitters are invisible and the eye's protective blink reflex does not work for
  them; treat them with extra care and keep them away from children.
- Strobe: flashing between 3 and 30 times per second is the range most likely to trigger
  seizures in people with photosensitive epilepsy
  ([Epilepsy Society](https://epilepsysociety.org.uk/node/3618)). LuxLibre keeps strobe out of
  the defaults.

## Heat

- A head in turbo can get hot enough to burn within seconds, and a light lying face-down on
  fabric can scorch it. LuxLibre regulates the temperature ([THM-5](docs/design-rules.md#thm-5)),
  but only as well as the board header's limits are set and measured
  ([THM-1](docs/design-rules.md#thm-1)).
- Use the lockout when carrying a light in a pocket or bag ([BAT-7](docs/design-rules.md#bat-7)).

## Lasers

- Use only Class 1 or Class 2 laser modules ([LAS-1](docs/design-rules.md#las-1)), measure
  their real power ([LAS-3](docs/design-rules.md#las-3)), and keep the hardware interlock
  ([LAS-2](docs/design-rules.md#las-2)).
- Never point a laser at people, animals, vehicles or aircraft; in many countries that is a
  criminal offence.
- Lasers in products that appeal to children must be Class 1.

## Building and testing

- Power a new board from a current-limited bench supply before it ever sees a cell
  ([docs/testing.md](docs/testing.md#bring-up-of-a-new-board)).
- Solder in a ventilated room; lead-free solder needs higher temperatures, and flux fumes
  irritate the airways.
- Wear eye protection when testing lasers and when working near charged cells with tools.
- Never disable the protections in the firmware to "see what it can do". Parameter ranges exist
  for a reason ([FW-5](docs/design-rules.md#fw-5)).

## Responsibility

LuxLibre comes without warranty ([LICENSING.md](LICENSING.md)). Whoever builds a light for
others, or sells it, is responsible for its safety and for meeting the rules of the market where
it is sold (for example product safety, EMC, battery and laser regulations). The project's
rules and tests help with that; they do not replace certification where it is required.

## Reporting a safety problem

If you find a safety problem in the firmware, the design rules or a reference design, open an
issue with the label `safety` and describe what happens and how to reproduce it. Safety issues
are handled before everything else.
