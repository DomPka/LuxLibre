#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Charts for docs/comparison.md from docs/data/flashlights.json (light and dark versions).

    python3 tools/comparison_charts.py

writes docs/img/compare_light_{light,dark}.png    light at 30 s and after 10 minutes, by cell size
       docs/img/compare_runtime_{light,dark}.png  time from the brightest mode to the ANSI end point

LuxLibre designs are drawn in blue (simulated), the other lights in orange (measured by an independent
reviewer). Needs matplotlib.
"""
import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "docs", "data", "flashlights.json")
OUT = os.path.join(ROOT, "docs", "img")

THEMES = {   # categorical slots 1 and 2 of the reference palette, validated on these surfaces
    "light": dict(surface="#ffffff", ink="#0b0b0b", ink2="#52514e", grid="#e6e5e1", ours="#2a78d6", theirs="#eb6834"),
    "dark": dict(surface="#0d1117", ink="#f0efec", ink2="#c3c2b7", grid="#2b2f36", ours="#3987e5", theirs="#d95926"),
}
CLASSES = [("small", "16340 and smaller cells"), ("mid", "14500, 18350 and 18500 cells"),
           ("large", "18650 and 21700 cells, large built-in packs")]


def font():
    for name in ("Inter", "DejaVu Sans"):
        if any(f.name == name for f in font_manager.fontManager.ttflist):
            return name
    return "sans-serif"


def rows_of(lights, cls, key):
    r = [x for x in lights if x["class"] == cls and x.get(key) is not None]
    return sorted(r, key=lambda x: x[key])


def legend_handles(t, kind):
    h = [Line2D([], [], marker="D", ls="", ms=8, mfc=t["ours"], mec=t["surface"], mew=1.5,
                label="LuxLibre design (simulated)"),
         Line2D([], [], marker="o", ls="", ms=8.5, mfc=t["theirs"], mec=t["surface"], mew=1.5,
                label="Popular light (measured by a reviewer)")]
    if kind == "light":
        h += [Line2D([], [], marker="o", ls="", ms=8.5, mfc=t["ink2"], mec=t["surface"], mew=1.5, label="at 30 s"),
              Line2D([], [], marker="o", ls="", ms=8, mfc=t["surface"], mec=t["ink2"], mew=2.0,
                     label="after 10 minutes")]
    return h


def style_axis(ax, t):
    ax.set_facecolor(t["surface"])
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(t["grid"])
    ax.tick_params(axis="x", colors=t["ink2"], labelsize=10, length=0, pad=6)
    ax.tick_params(axis="y", colors=t["ink"], labelsize=10.5, length=0, pad=8)
    ax.grid(axis="x", color=t["grid"], lw=1.0)
    ax.set_axisbelow(True)


def chart_light(lights, theme):
    t = THEMES[theme]
    groups = [(c, title, rows_of(lights, c, "lm_30s")) for c, title in CLASSES]
    n = [len(g[2]) for g in groups]
    fig, axes = plt.subplots(3, 1, figsize=(10, 0.36 * sum(n) + 3.0), sharex=True,
                             gridspec_kw={"height_ratios": n, "hspace": 0.42})
    fig.patch.set_facecolor(t["surface"])
    for ax, (c, title, rows) in zip(axes, groups):
        style_axis(ax, t)
        for i, x in enumerate(rows):
            col = t["ours"] if x["ours"] else t["theirs"]
            mk = "D" if x["ours"] else "o"
            if x.get("lm_10min") is not None:
                ax.plot([x["lm_10min"], x["lm_30s"]], [i, i], color=col, lw=2.0, alpha=0.45, solid_capstyle="round",
                         zorder=2)
                ax.plot(x["lm_10min"], i, marker=mk, ms=8 if x["ours"] else 8.5, mfc=t["surface"], mec=col, mew=2.0,
                        ls="", zorder=3)
            ax.plot(x["lm_30s"], i, marker=mk, ms=8.5 if x["ours"] else 9, mfc=col, mec=t["surface"], mew=1.5, ls="",
                    zorder=4)
        ax.set_yticks(range(len(rows)))
        ax.set_yticklabels([x["name"] for x in rows])
        for lab, x in zip(ax.get_yticklabels(), rows):
            if x["ours"]:
                lab.set_fontweight("semibold")
        ax.set_ylim(-0.7, len(rows) - 0.3)
        ax.set_title(title, loc="left", color=t["ink2"], fontsize=10.5, pad=6)
    axes[-1].set_xlim(0, 2600)
    axes[-1].set_xticks(range(0, 2600, 500))
    axes[-1].set_xticklabels(["0", "500", "1,000", "1,500", "2,000", "2,500"])
    axes[-1].set_xlabel("lumens out of the front", color=t["ink2"], fontsize=10, labelpad=8)
    fig.suptitle("Light at 30 s and after 10 minutes on the brightest mode", x=0.012, ha="left", y=0.995,
                 color=t["ink"], fontsize=14, fontweight="semibold")
    fig.text(0.012, 0.955 - 0.0006 * sum(n), "Filled mark: 30 s after switching on. Open mark: after 10 minutes, once "
             "the light has stepped down to what its body can hold.\nLuxLibre figures are simulated (LED at 85 °C, "
             "25 °C still air); the others are measured by the reviewers listed in docs/comparison.md.",
             ha="left", va="top", color=t["ink2"], fontsize=9.5, linespacing=1.4)
    fig.legend(handles=legend_handles(t, "light"), loc="lower left", bbox_to_anchor=(0.005, 0.0), ncol=4,
               frameon=False, fontsize=9.5, labelcolor=t["ink2"], handletextpad=0.4, columnspacing=1.4)
    fig.subplots_adjust(left=0.22, right=0.98, top=0.86, bottom=0.11)
    return fig


def chart_runtime(lights, theme):
    t = THEMES[theme]
    groups = [(c, title, rows_of(lights, c, "runtime_turbo_min")) for c, title in CLASSES]
    n = [len(g[2]) for g in groups]
    fig, axes = plt.subplots(3, 1, figsize=(10, 0.36 * sum(n) + 2.7), sharex=True,
                             gridspec_kw={"height_ratios": n, "hspace": 0.42})
    fig.patch.set_facecolor(t["surface"])
    for ax, (c, title, rows) in zip(axes, groups):
        style_axis(ax, t)
        for i, x in enumerate(rows):
            col = t["ours"] if x["ours"] else t["theirs"]
            ax.barh(i, x["runtime_turbo_min"], height=0.56, color=col, zorder=2)
            m = x["runtime_turbo_min"]
            ax.text(m + 3, i, "%d h %02d min" % (m // 60, m % 60) if m >= 60 else "%d min" % m, va="center",
                    ha="left", color=t["ink2"], fontsize=9, zorder=3,
                    bbox=dict(boxstyle="square,pad=0.15", facecolor=t["surface"], edgecolor="none"))
        ax.set_yticks(range(len(rows)))
        ax.set_yticklabels([x["name"] for x in rows])
        for lab, x in zip(ax.get_yticklabels(), rows):
            if x["ours"]:
                lab.set_fontweight("semibold")
        ax.set_ylim(-0.7, len(rows) - 0.3)
        ax.set_title(title, loc="left", color=t["ink2"], fontsize=10.5, pad=6)
    axes[-1].set_xlim(0, 270)
    axes[-1].set_xticks(range(0, 271, 60))
    axes[-1].set_xticklabels(["0", "1 h", "2 h", "3 h", "4 h"])
    axes[-1].set_xlabel("from the brightest mode until the light falls below 10 % of its 30 s output",
                        color=t["ink2"], fontsize=10, labelpad=8)
    fig.suptitle("Runtime from the brightest mode", x=0.012, ha="left", y=0.995, color=t["ink"], fontsize=14,
                 fontweight="semibold")
    fig.text(0.012, 0.952 - 0.0006 * sum(n), "LuxLibre figures are simulated; the others are measured by reviewers. "
             "Lights whose turbo is a short burst have no figure.", ha="left", va="top", color=t["ink2"], fontsize=9.5)
    fig.legend(handles=legend_handles(t, "runtime"), loc="lower left", bbox_to_anchor=(0.005, 0.0), ncol=2,
               frameon=False, fontsize=9.5, labelcolor=t["ink2"], handletextpad=0.4, columnspacing=1.4)
    fig.subplots_adjust(left=0.22, right=0.98, top=0.88, bottom=0.12)
    return fig


def main():
    plt.rcParams["font.family"] = font()
    lights = json.load(open(DATA))["lights"]
    os.makedirs(OUT, exist_ok=True)
    for theme in THEMES:
        for name, fn in (("compare_light", chart_light), ("compare_runtime", chart_runtime)):
            fig = fn(lights, theme)
            path = os.path.join(OUT, "%s_%s.png" % (name, theme))
            fig.savefig(path, dpi=150, facecolor=fig.get_facecolor())
            plt.close(fig)
            print("wrote", os.path.relpath(path, ROOT))


if __name__ == "__main__":
    main()
