#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
FlashKa Keychain v0.7 - keeps the housing files in order_files/ current.

The shops get copies of files that the housing tools write into cad/ (STEP, STL, the drawing PDFs under the names the
order READMEs use).  flashka_housing.py, key_mould.py and drawings.py call copy() after they have written into the
package's cad folder, so a rebuild refreshes the order folders and the check files in docs/checks at once and no copy
can go stale.  Output written into any other folder (a test build) is not copied.

usage:  python3 order_files.py            copy everything from ../../cad (relative to this script)
"""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.normpath(os.path.join(HERE, "..", ".."))
CAD = os.path.join(PKG, "cad")
JLCCNC = os.path.join("order_files", "2_JLCCNC")
KEYS = os.path.join("order_files", "3_rubber_keys")
CHECKS = os.path.join("docs", "checks")

# kind -> [(file in cad/, target relative to the package folder)]
FILES = {
    "step": [("FlashKa_%s.step" % n, os.path.join(JLCCNC, "FlashKa_%s.step" % n))
             for n in ("tray", "lid", "key_main", "rf_window", "antenna_spacer", "laser_sleeve", "pmma_kit", "pom_kit")]
    + [("FlashKa_%s.step" % n, os.path.join(KEYS, "FlashKa_%s.step" % n))
       for n in ("key_side", "key_stiffener", "key_side_with_plate")],
    "mould": [("FlashKa_%s.step" % n, os.path.join(KEYS, "FlashKa_%s.step" % n))
              for n in ("key_mould", "key_mould_cavity", "key_mould_lid", "key_mould_resin")]
    + [("FlashKa_%s.stl" % n, os.path.join(KEYS, "FlashKa_%s.stl" % n))
       for n in ("key_mould_resin_cavity", "key_mould_resin_lid")]
    + [("key_mould_checks.json", os.path.join(CHECKS, "key_mould_v07_checks.json"))],
    "pdf": [("FlashKa_%s_drawing.pdf" % n, os.path.join(JLCCNC, "FlashKa_%s.pdf" % n))
            for n in ("tray", "lid", "key_main", "pom_parts", "pmma_kit", "pom_kit")]
    + [("FlashKa_key_side_drawing.pdf", os.path.join(KEYS, "FlashKa_key_side.pdf")),
       ("FlashKa_key_mould_drawing.pdf", os.path.join(KEYS, "FlashKa_key_mould.pdf")),
       ("drawings_dimension_table.txt", os.path.join(CHECKS, "housing_v07_drawings_dimension_table.txt"))],
}


def is_package_cad(path):
    """True if path is this package's cad folder (only then are the order folders refreshed)"""
    try:
        return os.path.samefile(path, CAD)
    except OSError:
        return False


def copy(kinds=("step", "mould", "pdf"), cad=CAD, quiet=False):
    """copy the files of the given kinds from cad into the order folders / docs/checks; returns the targets written"""
    done = []
    for kind in kinds:
        for src, dst in FILES[kind]:
            s, d = os.path.join(cad, src), os.path.join(PKG, dst)
            if not os.path.exists(s):
                print("order_files: missing %s" % src)
                continue
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copy2(s, d)
            done.append(dst)
    if not quiet:
        print("order_files: %d files refreshed (%s)" % (len(done), ", ".join(kinds)))
    return done


if __name__ == "__main__":
    copy(cad=sys.argv[1] if len(sys.argv) > 1 else CAD)
