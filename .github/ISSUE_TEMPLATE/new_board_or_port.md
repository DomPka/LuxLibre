---
name: New board or port
about: Plan a new board header, MCU port or reference design
labels: board
---

**What**
<!-- Board name, MCU, driver topology, LED, cells, special hardware (laser, charger, RGB). -->

**Links**
<!-- Schematic, datasheets, an existing product or open design. -->

**Plan**
- [ ] board header (`firmware/boards/<name>/board.h`), see docs/firmware/porting.md
- [ ] simulator check (`make sim BOARD=<name>`)
- [ ] hardware bring-up and test report (docs/testing.md, templates/test-report.md)
- [ ] design files and README (hardware/README.md) for a reference design
