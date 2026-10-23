<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
[LuxLibre](../../README.md) › [Lights](../README.md) › Shared tools

# Shared hardware tools

Scripts that work across the reference designs. Each design's own CAD and render scripts are in its
`tools/housing/` folder. Run these from the repository root.

| Script | What it makes | Command |
|---|---|---|
| [edco_drawings.py](edco_drawings.py) | the dimensioned body drawings of every EDCO design (A3 at 2:1; DXF, PDF and PNG in each `cad/` folder), checked against the solids: [report](edco_drawings_check.txt) | `python3 hardware/tools/edco_drawings.py` |
| [edco_anim.py](edco_anim.py) | the animations of every EDCO design: turning, coming apart, and the EDCO Prism's colours (GIFs in each `assets/` folder) | `xvfb-run -a python3 hardware/tools/edco_anim.py` |
| [lineup.py](lineup.py) | all seven lights standing side by side at true scale (`docs/img/lineup*.png`, `lineup.json`) for the README and the web site | `xvfb-run -a python3 hardware/tools/lineup.py` |
| [make_banners.py](make_banners.py) | the README banner (light and dark) and the GitHub social preview | `xvfb-run -a python3 hardware/tools/make_banners.py` |
| [folder_readmes.py](folder_readmes.py) | the README pages of the `cad/` and `assets/` folders | `python3 hardware/tools/folder_readmes.py` |

They need Python 3 with CadQuery, VTK, NumPy, Pillow, ezdxf and PyMuPDF, plus `xvfb-run` and `ffmpeg` for the
renders. They reuse the FlashKa v0.7 renderer and drawing helpers in
[../flashka-keychain-v07/tools/housing/](../flashka-keychain-v07/tools/housing/).
