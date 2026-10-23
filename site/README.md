<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
[LuxLibre](../README.md) › Web site

# Web site

The LuxLibre web site, published with GitHub Pages at <https://dompka.github.io/LuxLibre/> by
[.github/workflows/pages.yml](../.github/workflows/pages.yml).

| Page | File | What it does |
|---|---|---|
| [Start page](https://dompka.github.io/LuxLibre/) | [index.html](index.html) | pick a light on the true-scale lineup, take it apart, compare it with popular lights, see the drawings |
| [LuxLibre settings](https://dompka.github.io/LuxLibre/luxlibre/) | [luxlibre/index.html](luxlibre/index.html) | changes the settings of a light with the LuxLibre firmware over USB-C (Web Serial); demo mode without a light |
| [FlashKa control app and installer](https://dompka.github.io/LuxLibre/flashka/) | [hardware/flashka-keychain-v06/app/](../hardware/flashka-keychain-v06/app/) | the FlashKa pages (copied in by the workflow) |

The start page uses pictures and data from [docs/img/](../docs/img/) and [docs/data/](../docs/data/), which the workflow
copies next to it. Every page is a single HTML file with no build step; open it in a browser to try it (the start
page's chart needs the data file next to it, so serve the assembled folder with `python3 -m http.server`).
