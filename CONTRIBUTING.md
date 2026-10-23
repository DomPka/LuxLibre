<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
[LuxLibre](README.md) › Contributing

# Contributing

**On this page:** [Ways to help](#ways-to-help) · [Workflow](#workflow) · [Firmware code rules](#firmware-code-rules) · [Hardware contributions](#hardware-contributions) · [Documentation rules](#documentation-rules) · [Licence and sign-off](#licence-and-sign-off)

Thank you for helping. LuxLibre grows through new boards, ports, measurements, fixes and better
explanations; all of them are welcome. Please read [SAFETY.md](SAFETY.md) and the
[code of conduct](CODE_OF_CONDUCT.md) first.

## Ways to help

- **Report** a bug, a wrong number in the docs or a safety concern (an issue; label `safety` for
  safety problems).
- **Measure** a light and add the test report: measured data is the most valuable contribution.
- **Add a board** for an MCU LuxLibre already supports ([docs/firmware/porting.md](docs/firmware/porting.md)).
- **Port** the firmware to a new MCU.
- **Improve the docs**: clearer explanations, translations, better sources.
- **Share a reference design** under `hardware/` (see [hardware/README.md](hardware/README.md)).

## Workflow

1. For anything larger than a small fix, open an issue first and describe the plan.
2. Fork, create a branch, make the change.
3. Run the checks:
   ```sh
   cd firmware
   make test                    # must pass
   make docs                    # if you changed parameters or the button map; commit the result
   make tiny1616 && make ch32v003   # if you changed core or port code and have the compilers
   cd .. && python3 -m unittest tools/test_lux_calc.py    # if you changed tools/
   ```
4. Commit with a sign-off (see below) and open a pull request. The template lists what reviewers
   check.

CI runs the host tests, the documentation check and the MCU builds on every pull request.

## Firmware code rules

- C++17, the embedded subset described in [docs/firmware/README.md](docs/firmware/README.md#why-c17):
  no heap, no exceptions, no RTTI, no virtual functions, no standard containers in the core, no
  floating point at run time in code that runs on the small MCUs.
- Modules are namespaces with file-scope state: `g_` prefix for file-scope variables, `k_` for
  constant tables, `P_` for parameter IDs, `LX_` for macros, `lower_case` for functions.
- 4 spaces, lines up to 120 characters, comments that explain *why*.
- The core never touches hardware; new hardware needs go through the HAL.
- Every behaviour change comes with a test in `firmware/tests/`; every bug fix with a test that
  failed before the fix.
- New user settings are added to `core/lx_params_list.h` (name at most 10 characters, a safe
  range, a unit and a description) and documented by `make docs`.
- Safety-relevant changes (thermal, low voltage, charging, laser, lockout) name the design rule
  they implement and get a second reviewer.

## Hardware contributions

- Editable sources (KiCad and CAD source or generator scripts), production files, a BOM with
  manufacturer part numbers, a README with status and known limitations, and the licence notes
  ([LICENSING.md](LICENSING.md)).
- A filled design-review checklist ([templates/design-review-checklist.md](templates/design-review-checklist.md)).
- A test report ([templates/test-report.md](templates/test-report.md)) before a design is called
  "tested".

## Documentation rules

Plain English, short sentences, SI units, sources for every number from a standard or a
datasheet, and project choices marked as such. Refer to design rules by ID. Keep personal data
out of test reports and photos.

## Licence and sign-off

Contributions are accepted under the licence of the files they change ("inbound = outbound",
[LICENSING.md](LICENSING.md)). New files start with an SPDX line, for example
`// SPDX-License-Identifier: GPL-3.0-or-later`.

Every commit carries a Developer Certificate of Origin sign-off: by adding

```text
Signed-off-by: Your Name <you@example.com>
```

(`git commit -s` does it) you certify that you wrote the change or have the right to submit it
under the project's licences, as described at [developercertificate.org](https://developercertificate.org/).
