<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
# Templates

Fill-in documents for designing a flashlight. Copy the ones you need into your own project
folder, fill them in, and keep them under version control next to your design files. Each
Markdown template starts with a short "How to use" paragraph and works on paper too.
Placeholders are written as `<...>` or left as empty table cells.

## Which template, when

The templates follow the design steps in this order. Steps 2 to 4 repeat for every important
choice (cell, LED, driver, MCU, housing).

| Step | Template | What it is for | Related rules |
|---|---|---|---|
| 1. Requirements | [requirements.md](requirements.md) | Measurable targets (output, runtime, size, temperature, colour, safety, budget) before any part is chosen | [REQ-1](../docs/design-rules.md#req-1), [REQ-2](../docs/design-rules.md#req-2) |
| 2. Candidates | [design-log.md](design-log.md) (options list) | Collect at least three options per choice, with datasheets and sources; see [docs/choosing-parts.md](../docs/choosing-parts.md) | [REQ-3](../docs/design-rules.md#req-3) |
| 3. Decision matrix | [decision-matrix.md](decision-matrix.md), [decision-matrix.csv](decision-matrix.csv) | Screen out options that fail hard limits, then score the rest with weighted criteria | [REQ-3](../docs/design-rules.md#req-3) |
| 4. Design log | [design-log.md](design-log.md) | One record per decision: question, options, data, decision, reasons, risks, verification | [REQ-3](../docs/design-rules.md#req-3) |
| 5. BOM | [bom.csv](bom.csv) | Bill of materials (BOM, the list of all parts) with supplier numbers, prices and second sources | [DFM-2](../docs/design-rules.md#dfm-2), [DFM-6](../docs/design-rules.md#dfm-6) |
| 6. Review | [design-review-checklist.md](design-review-checklist.md) | Check the design against every LuxLibre design rule before ordering boards or releasing | all rules in [docs/design-rules.md](../docs/design-rules.md) |
| 7. Test report | [test-report.md](test-report.md) | Results of the prototype or release tests, linked back to the requirement IDs; procedures in [docs/testing.md](../docs/testing.md) | [FW-8](../docs/design-rules.md#fw-8), [THM-6](../docs/design-rules.md#thm-6) |

Tips:

- Give every requirement an ID (R1, R2, ...) and every decision an ID (D-01, D-02, ...).
  The design log, the review and the test report refer to these IDs.
- The CSV files open in any spreadsheet program. Formulas are left to you.
- A release is ready when every requirement has a test result and the review has no
  open items.

## Licence of the templates

- The templates in this folder are licensed under
  [CC-BY-SA-4.0](https://creativecommons.org/licenses/by-sa/4.0/), like the rest of the
  LuxLibre documentation (see [LICENSING.md](../LICENSING.md)).
- **Documents you make from them are yours.** The template authors waive attribution for
  filled-in copies: you may use a filled-in requirement sheet, design log, matrix, BOM,
  checklist or test report in your own project files without naming LuxLibre and without
  putting it under CC-BY-SA-4.0. Choose any licence you like for them, or none.
- Attribution and share-alike still apply if you publish changed versions of the blank
  templates themselves.
