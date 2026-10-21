#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Plot luxsim logs: light output (top) and sensor temperature (bottom) over time.

    python3 tools/plot_sim.py out.png keychain.csv:"Keychain" edc.csv:"18650 EDC" [--limit 50] [--dark]
                              [--title "..."] [--xlabel "..."]

Input: CSV files with at least the columns t_s, lumens and T_sensor_C (the luxsim log format;
measurements written in the same format can be plotted next to a simulation).

Two stacked panels with a shared time axis (never two y-scales on one panel).
Colours: the first two categorical slots of the LuxLibre chart palette, checked for
colour-vision deficiency separation in light and dark mode.
"""
import csv
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

LIGHT = {"surface": "#fcfcfb", "text": "#0b0b0b", "text2": "#52514e", "grid": "#e4e3df",
         "series": ["#2a78d6", "#eb6834"]}
DARK = {"surface": "#1a1a19", "text": "#f0efec", "text2": "#c3c2b7", "grid": "#33332f",
        "series": ["#3987e5", "#d95926"]}


def load(path):
    t, lm, temp = [], [], []
    with open(path) as f:
        for r in csv.DictReader(f):
            t.append(float(r["t_s"]) / 60.0)
            lm.append(float(r["lumens"]))
            temp.append(float(r["T_sensor_C"]))
    return t, lm, temp


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    out = argv[1]
    limit = None
    theme = LIGHT
    title = "Turbo with thermal regulation (LuxLibre simulator)"
    xlabel = "Time after switching to turbo (min)"
    runs = []
    args = argv[2:]
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--limit":
            limit = float(args[i + 1])
            i += 2
            continue
        if a == "--dark":
            theme = DARK
            i += 1
            continue
        if a in ("--title", "--xlabel"):
            if a == "--title":
                title = args[i + 1]
            else:
                xlabel = args[i + 1]
            i += 2
            continue
        path, _, label = a.partition(":")
        runs.append((label or path, load(path)))
        i += 1

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8.0, 5.6), sharex=True, dpi=150)
    fig.patch.set_facecolor(theme["surface"])
    for ax in (ax1, ax2):
        ax.set_facecolor(theme["surface"])
        ax.grid(True, color=theme["grid"], linewidth=0.8)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(theme["grid"])
        ax.tick_params(colors=theme["text2"])
    for k, (label, (t, lm, temp)) in enumerate(runs):
        c = theme["series"][k % len(theme["series"])]
        ax1.plot(t, lm, color=c, linewidth=2, label=label)
        ax2.plot(t, temp, color=c, linewidth=2, label=label)
        # final value at the right end of each line (the legend names the series)
        ax1.annotate(f"{lm[-1]:.0f} lm", (t[-1], lm[-1]), xytext=(6, 0), textcoords="offset points",
                     va="center", color=theme["text"], fontsize=9)
    if limit is not None:
        ax2.axhline(limit, color=theme["text2"], linewidth=1, linestyle=(0, (4, 3)))
        t_end = max(r[1][0][-1] for r in runs)
        ax2.annotate(f"THM_LIMIT {limit:.0f} °C", (t_end, limit), xytext=(-2, -4), textcoords="offset points",
                     ha="right", va="top", color=theme["text2"], fontsize=9)
    ax1.set_ylabel("Light output (lm)", color=theme["text"])
    ax2.set_ylabel("Sensor temperature (°C)", color=theme["text"])
    ax2.set_xlabel(xlabel, color=theme["text"])
    ax1.set_ylim(bottom=0)
    leg = ax1.legend(loc="upper right", frameon=False)
    for txt in leg.get_texts():
        txt.set_color(theme["text"])
    ax1.set_title(title, color=theme["text"], loc="left", fontsize=11)
    fig.subplots_adjust(left=0.1, right=0.88, top=0.92, bottom=0.1, hspace=0.12)
    fig.savefig(out, facecolor=theme["surface"])
    print("wrote", out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
