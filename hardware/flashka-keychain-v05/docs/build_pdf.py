#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Print the v0.5 documents to PDF.

usage (from the project folder):
    python3 docs/build_pdf.py            # both PDFs
    python3 docs/build_pdf.py guide      # Aurora_v0.5_Build_Guide.pdf
    python3 docs/build_pdf.py ch12       # Aurora_v0.5_Hardware_Package.pdf
    python3 docs/build_pdf.py all --out some/folder

Sources (plain Markdown, readable on their own):
    docs/build_guide_v0.5.md            the zero-knowledge build guide; appendix A is section 2
                                        (user manual) of docs/firmware.md
    docs/ch12_v0.5_bluetooth_redesign.md chapter 12 of the design log (same text that
                                        tools/apply_v05_to_design_log.py merges into design_log.md)
Conventions (as in the design log and docs/build_ch11_pdf.py):
    <!-- landscape -->   before an image: that figure gets its own landscape page
    <!-- pagebreak -->   start a new page here
    an italic line right after an image becomes its caption
Image paths are relative to the Markdown file. Needs: python-markdown, playwright (Chromium).
"""
import html
import pathlib
import re
import sys

import markdown
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATE = "2026-10-14"

CSS = """
@page { size: A4; margin: 17mm 16mm 18mm 16mm; }
@page landscape { size: A4 landscape; margin: 10mm 10mm 12mm 10mm; }
html { font-family: 'Carlito', 'Liberation Sans', sans-serif; font-size: 10.3pt; color: #1d232b; }
body { margin: 0; line-height: 1.38; }
h1 { font-family: 'Liberation Sans', sans-serif; font-size: 20pt; color: #1f3a5a; margin: 0 0 10px 0; }
h2 { font-family: 'Liberation Sans', sans-serif; font-size: 16pt; color: #1f3a5a;
     border-bottom: 2px solid #1f3a5a; padding-bottom: 4px; margin: 16px 0 10px 0; break-after: avoid; }
h3 { font-family: 'Liberation Sans', sans-serif; font-size: 12.5pt; color: #1f3a5a;
     margin: 16px 0 6px 0; break-after: avoid; }
h4 { font-family: 'Liberation Sans', sans-serif; font-size: 11pt; color: #2b4f75;
     margin: 12px 0 4px 0; break-after: avoid; }
p { margin: 5px 0 7px 0; text-align: justify; hyphens: auto; }
ul, ol { margin: 4px 0 8px 0; padding-left: 22px; }
li { margin: 2px 0; }
li > table { margin-top: 4px; }
code { font-family: 'DejaVu Sans Mono', monospace; font-size: 8.4pt; background: #eef2f6;
       padding: 0 2px; border-radius: 2px; }
pre { background: #f3f6f9; border: 1px solid #d5dde6; border-radius: 3px; padding: 7px 9px;
      font-size: 8.2pt; line-height: 1.3; break-inside: avoid; white-space: pre-wrap; }
pre code { background: none; padding: 0; font-size: 8.2pt; }
blockquote { margin: 8px 0 10px 0; padding: 5px 11px; background: #fbf5e6;
             border-left: 4px solid #d4a017; break-inside: avoid; }
blockquote p { margin: 3px 0; }
table { border-collapse: collapse; width: 100%; margin: 6px 0 10px 0; font-size: 8.8pt;
        break-inside: auto; }
thead { display: table-header-group; }
tr { break-inside: avoid; }
th { background: #1f3a5a; color: #fff; text-align: left; padding: 3px 5px; font-weight: bold; }
td { border-bottom: 1px solid #d5dde6; padding: 3px 5px; vertical-align: top; }
tr:nth-child(even) td { background: #f6f8fa; }
hr { border: none; border-top: 1px solid #c9d2dc; margin: 12px 0; }
figure { margin: 10px 0 12px 0; text-align: center; break-inside: avoid; }
figure img { max-width: 100%; max-height: 112mm; }
figcaption { font-size: 8.8pt; color: #44505c; margin-top: 4px; text-align: left; font-style: italic; }
.landscape { page: landscape; break-before: page; break-after: page; margin: 0; }
.landscape img { max-width: 100%; max-height: 172mm; }
.pb { break-before: page; height: 0; }
.title { height: 252mm; display: flex; flex-direction: column; justify-content: center;
         break-after: page; }
.title .k { font-family: 'Liberation Sans', sans-serif; color: #5a6b7d; letter-spacing: 1.5px;
            font-size: 10pt; text-transform: uppercase; }
.title h1 { font-family: 'Liberation Sans', sans-serif; font-size: 30pt; color: #1f3a5a;
            margin: 6px 0 4px 0; }
.title .sub { font-size: 14pt; color: #2b4f75; margin-bottom: 16px; }
.title img { width: 100%; margin: 14px 0; }
.title .meta { font-size: 10pt; color: #44505c; line-height: 1.6; }
.toc { break-after: page; }
.toc h3 { margin-top: 0; }
.toc ol { list-style: none; padding-left: 0; }
.toc li { margin: 3px 0; }
.toc li.l4 { padding-left: 18px; font-size: 9.5pt; color: #44505c; }
"""

SIZES = {   # per-figure size limits for the print (the Markdown stays plain)
    "housing_closed_control_side.png": "max-height:70mm",
    "housing_exploded.png": "max-height:95mm",
    "size_comparison_A9.png": "max-height:120mm",
    "pcb_layers.png": "max-height:150mm",
    "flasher-connected-1280.png": "max-height:85mm",
    "app-demo-on-390.png": "max-height:120mm",
    "wiring_pads.png": "max-height:150mm",
}


def md_to_html(text, base, skip_img=None):
    lines = text.splitlines()
    out, i = [], 0
    while i < len(lines):
        ln = lines[i]
        if ln.strip() == "<!-- pagebreak -->":
            out.append('<div class="pb"></div>')
            i += 1
            continue
        land = False
        if ln.strip() == "<!-- landscape -->":
            land = True
            i += 1
            ln = lines[i]
        m = re.match(r"!\[([^\]]*)\]\(([^)]+)\)\s*$", ln.strip())
        if m:
            cap = ""
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            nxt = lines[j].strip() if j < len(lines) else ""
            if nxt.startswith("*") and not nxt.startswith("**") and nxt.endswith("*"):
                cap = nxt.strip("*")
                i = j
            capd = markdown.markdown(cap).replace("<p>", "").replace("</p>", "")
            cls = ' class="landscape"' if land else ""
            src = (base / m.group(2)).resolve()
            if not src.exists():
                raise SystemExit(f"missing image: {src}")
            if skip_img is not None and src == skip_img:      # already on the title page
                if capd:
                    out.append(f'<p class="lead"><i>{capd}</i></p>')
                i += 1
                continue
            sty = SIZES.get(src.name, "")
            sty = f' style="{sty}"' if sty else ""
            out.append(f'<figure{cls}><img src="{src.as_uri()}" alt="{m.group(1)}"{sty}>'
                       f"<figcaption>{capd}</figcaption></figure>")
        else:
            out.append(ln)
        i += 1
    return markdown.markdown("\n".join(out), extensions=["tables", "fenced_code", "sane_lists"])


def inline(t):
    """heading text -> HTML without block elements ("0. What..." must not become a list)"""
    t = html.escape(t, quote=False)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", t)
    return re.sub(r"\*([^*]+)\*", r"<i>\1</i>", t)


def toc(text, levels):
    items = []
    in_code = False
    for ln in text.splitlines():
        if ln.startswith("```"):
            in_code = not in_code
        if in_code:
            continue
        m = re.match(r"^(#{2,4})\s+(.*)$", ln)
        if m and len(m.group(1)) in levels:
            cls = "l3" if len(m.group(1)) == levels[0] else "l4"
            items.append(f'<li class="{cls}">{inline(m.group(2))}</li>')
    return '<div class="toc"><h3>Contents</h3><ol>' + "".join(items) + "</ol></div>"


def firmware_manual():
    """Section 2 of docs/firmware.md (2.1-2.9, the user manual) as appendix A of the guide."""
    fw = (ROOT / "docs" / "firmware.md").read_text(encoding="utf-8").splitlines()
    a = next(i for i, ln in enumerate(fw) if re.match(r"^## 2\.", ln))
    b = next(i for i, ln in enumerate(fw) if re.match(r"^### 2\.10\b|^## 3\.", ln))
    body = []
    for ln in fw[a + 1:b]:
        ln = re.sub(r"^### 2\.(\d+)", r"### A.\1", ln)
        ln = re.sub(r"\(see 2\.(\d+)\)", r"(see A.\1)", ln)
        body.append(ln)
    while body and body[-1].strip() in ("", "---"):
        body.pop()
    return ("\n<!-- pagebreak -->\n\n## Appendix A. How the light works (user manual)\n\n"
            "*From `docs/firmware.md`, section 2. Every gesture, colour and protection rule of the "
            "firmware v0.5.0.*\n\n" + "\n".join(body) + "\n")


DOCS = {
    "guide": dict(
        src="docs/build_guide_v0.5.md", out="Aurora_v0.5_Build_Guide.pdf",
        kicker="Aurora++ keychain flashlight · build guide",
        title="Build Guide v0.5", sub="Order the parts, install the firmware, assemble — no experience needed",
        cover="renders/housing_closed_control_side.png", levels=(2,), appendix=firmware_manual,
        meta="For builders without electronics or programming background.<br>"
             f"FlashKa Keychain v0.5 · {DATE}<br>Source: docs/build_guide_v0.5.md (+ docs/firmware.md, section 2)",
        footer="Aurora++ v0.5 — Build Guide"),
    "ch12": dict(
        src="docs/ch12_v0.5_bluetooth_redesign.md", out="Aurora_v0.5_Hardware_Package.pdf",
        kicker="Aurora++ keychain flashlight · PCB design log &amp; build reference",
        title="Hardware Package v0.5", sub="Bluetooth · 94.4 × 20 × 16 mm body · 4-layer board · build anyone can follow",
        cover="renders/housing_open_iso.png", levels=(3, 4), appendix=None,
        meta="Chapter 12 of the design log, printed on its own.<br>"
             f"FlashKa Keychain v0.5 · {DATE}<br>Source: docs/ch12_v0.5_bluetooth_redesign.md (merged into design_log.md)",
        footer="Aurora++ v0.5 — Hardware Package"),
}


def build(key, outdir):
    d = DOCS[key]
    src = ROOT / d["src"]
    text = src.read_text(encoding="utf-8")
    text = re.sub(r"\A# [^\n]*\n", "", text)          # the title page carries the H1
    if d["appendix"]:
        text = text.rstrip() + "\n" + d["appendix"]()
    cover = (ROOT / d["cover"]).as_uri()
    title = f"""<div class="title">
  <div class="k">{d['kicker']}</div>
  <h1>{d['title']}</h1>
  <div class="sub">{d['sub']}</div>
  <img src="{cover}">
  <div class="meta">{d['meta']}</div>
</div>"""
    body = md_to_html(text, src.parent, skip_img=(ROOT / d["cover"]).resolve())
    html = (f'<!doctype html><html><head><meta charset="utf-8"><title>{d["footer"]}</title>'
            f"<style>{CSS}</style></head><body>{title}{toc(text, d['levels'])}{body}</body></html>")
    tmp = ROOT / "docs" / f"_{key}_print.html"
    tmp.write_text(html, encoding="utf-8")
    out = pathlib.Path(outdir) / d["out"]
    footer = ('<div style="font-size:7.5pt;color:#6b7785;width:100%;padding:0 12mm;'
              'display:flex;justify-content:space-between;font-family:Liberation Sans,sans-serif">'
              f'<span>{d["footer"]}</span>'
              '<span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>')
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.goto(tmp.as_uri())
        pg.wait_for_load_state("networkidle")
        pg.pdf(path=str(out), prefer_css_page_size=True, print_background=True,
               display_header_footer=True, header_template="<div></div>", footer_template=footer)
        b.close()
    tmp.unlink()
    print("wrote", out)
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    outdir = ROOT
    if "--out" in sys.argv:
        outdir = pathlib.Path(sys.argv[sys.argv.index("--out") + 1])
        args = [a for a in args if a != str(outdir)]
    keys = list(DOCS) if not args or args == ["all"] else args
    for k in keys:
        build(k, outdir)


if __name__ == "__main__":
    main()
