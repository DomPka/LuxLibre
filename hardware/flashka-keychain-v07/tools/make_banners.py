#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
The LuxLibre banner pictures and the GitHub social preview, made from the FlashKa v0.7 hero renders.

usage (from hardware/flashka-keychain-v07):
    python3 tools/make_banners.py [--out-dir ../../docs/img]

Inputs (written by tools/housing/render.py, same camera, same size):
    assets/v07/housing_closed_bottom.png   the closed light on white
    assets/v07/hero_dark.png               the same view on the dark background (13, 17, 23)
Outputs (in <LuxLibre>/docs/img/):
    luxlibre_banner_light.png   README banner for GitHub's light theme (1600 x 520, rounded card)
    luxlibre_banner_dark.png    README banner for GitHub's dark theme (1600 x 520, rounded card)
    social_preview.png          GitHub social preview (1280 x 640)

The layout, colours and fonts are those of the v0.6 banners (tools/housing/render_anim.py of v0.6): title
"LuxLibre", an accent bar, the two-line subtitle, a faint grid on the right, the render with a soft
shadow and the caption "FlashKa Keychain v0.7 - render". The light is cut out of the two renders by
difference matting (the object pixels of both renders are the same, only the background differs), so
its edges and the glowing ring keep their exact colours on the new background.
Needs: Pillow, numpy.
"""
import argparse
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)                                   # hardware/flashka-keychain-v07
REPO = os.path.dirname(os.path.dirname(PROJ))                  # the LuxLibre folder
IN_WHITE = os.path.join(PROJ, "assets", "v07", "housing_closed_bottom.png")
IN_DARK = os.path.join(PROJ, "assets", "v07", "hero_dark.png")
DARK_BG = (13, 17, 23)                                         # background of hero_dark.png
NOTE = "FlashKa Keychain v0.7 - render"

FONTS = {   # TeX Gyre Heros (a Helvetica-style face, GUST licence) as in v0.6; DejaVu Sans as the fallback
    "bold": ["/usr/share/texmf/fonts/opentype/public/tex-gyre/texgyreheros-bold.otf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "regular": ["/usr/share/texmf/fonts/opentype/public/tex-gyre/texgyreheros-regular.otf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
}
THEMES = {
    # card colours of GitHub's light / dark theme (primer "subtle canvas", border, text, muted text);
    # the dark card sits on GitHub's #0d1117 page, the light card on #ffffff (as in v0.6)
    "light": {"bg": (246, 248, 250), "border": (208, 215, 222), "grid": (226, 231, 236),
              "text": (31, 35, 40), "muted": (89, 99, 110), "accent": (9, 150, 168), "shadow": 0.16},
    "dark": {"bg": (22, 27, 34), "border": (48, 54, 61), "grid": (35, 42, 51),
             "text": (230, 237, 243), "muted": (145, 152, 161), "accent": (77, 222, 240), "shadow": 0.45},
}


def font(kind, size):
    for path in FONTS[kind]:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


class Cutout:
    """the light as premultiplied RGB + alpha, cut out of the white and the dark render of the same view"""

    def __init__(self, white_path, dark_path, dark_bg, margin=0.02):
        w = np.asarray(Image.open(white_path).convert("RGB"), np.float32) / 255.0
        d = np.asarray(Image.open(dark_path).convert("RGB"), np.float32) / 255.0
        if w.shape != d.shape:
            raise SystemExit("the two renders differ in size: %s %s" % (w.shape, d.shape))
        bg = np.array(dark_bg, np.float32) / 255.0
        a = 1.0 - ((w - d) / (1.0 - bg)).mean(axis=2)          # white minus dark = (1 - alpha) x (1 - bg)
        a = np.clip(a, 0.0, 1.0)
        pre = np.clip(d - (1.0 - a[..., None]) * bg, 0.0, 1.0)  # colour x alpha
        ys, xs = np.nonzero(a > 0.02)
        x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
        m = int(round(margin * (x1 - x0)))
        H, W = a.shape
        x0, y0, x1, y1 = max(x0 - m, 0), max(y0 - m, 0), min(x1 + m, W - 1), min(y1 + m, H - 1)
        self.pre = pre[y0:y1 + 1, x0:x1 + 1]
        self.alpha = a[y0:y1 + 1, x0:x1 + 1]

    def scaled(self, w):
        """(premultiplied RGB, alpha) resized to w px wide, float arrays 0..1"""
        h = int(round(self.alpha.shape[0] * w / self.alpha.shape[1]))

        def rs(arr, mode):
            im = Image.fromarray((np.clip(arr, 0, 1) * 255 + 0.5).astype(np.uint8), mode)
            return np.asarray(im.resize((w, h), Image.LANCZOS), np.float32) / 255.0
        return rs(self.pre, "RGB"), rs(self.alpha, "L")


def _blend_region(canvas, ox, oy, col, alpha):
    """canvas = canvas * (1 - alpha) + col * alpha in the window at ox, oy (clipped to the canvas)"""
    H, W = canvas.shape[:2]
    h, w = alpha.shape[:2]
    x0, y0, x1, y1 = max(ox, 0), max(oy, 0), min(ox + w, W), min(oy + h, H)
    if x1 <= x0 or y1 <= y0:
        return
    a = alpha[y0 - oy:y1 - oy, x0 - ox:x1 - ox][..., None]
    canvas[y0:y1, x0:x1] = canvas[y0:y1, x0:x1] * (1 - a) + col * a


def paste_cutout(canvas, cut, x, y, w, shadow=0.0, glow_strength=0.6, glow_radius=3.0):
    """composite the cutout (w px wide, top-left at x, y) onto the float RGB canvas, with a soft drop
    shadow below it and a light bloom round the glowing ring (the strongly cyan pixels)"""
    pre, a = cut.scaled(w)
    h = a.shape[0]
    if shadow > 0:
        sh = Image.fromarray((a * 255).astype(np.uint8), "L")
        pad = 60
        big = Image.new("L", (w + 2 * pad, h + 2 * pad), 0)
        big.paste(sh, (pad, pad))
        big = big.filter(ImageFilter.GaussianBlur(16))
        s = np.asarray(big, np.float32) / 255.0 * shadow
        _blend_region(canvas, x - pad + 6, y - pad + 16, 0.0, s)
    region = canvas[y:y + h, x:x + w]
    region[:] = pre + (1 - a[..., None]) * region
    if glow_strength > 0:
        r, g, b = pre[..., 0], pre[..., 1], pre[..., 2]
        cyan = np.clip((np.minimum(g, b) - r - 0.25) * 2.5, 0, 1)          # the lit ring only
        gm = (np.stack([r, g, b], axis=2) * cyan[..., None] * 255).astype(np.uint8)
        gi = Image.fromarray(gm, "RGB")
        g1 = np.asarray(gi.filter(ImageFilter.GaussianBlur(glow_radius)), np.float32) / 255
        g2 = np.asarray(gi.filter(ImageFilter.GaussianBlur(glow_radius * 3)), np.float32) / 255
        gg = np.clip((0.75 * g1 + 0.55 * g2) * glow_strength, 0, 1)
        region[:] = 1 - (1 - region) * (1 - gg)
    return x, y, w, h


def grid_layer(W, H, step, x_from):
    """alpha of a faint square grid: fades in from x_from towards the right and out at the edges"""
    g = np.zeros((H, W), np.float32)
    g[:, ::step] = 1.0
    g[::step, :] = 1.0
    xs = np.arange(W, dtype=np.float32)
    ys = np.arange(H, dtype=np.float32)
    fade = np.clip((xs - x_from) / (0.35 * W), 0, 1) ** 1.5
    edge_x = np.clip(np.minimum(xs, W - 1 - xs) / 48.0, 0, 1)
    edge_y = np.clip(np.minimum(ys, H - 1 - ys) / 48.0, 0, 1)
    return g * (fade * edge_x)[None, :] * edge_y[:, None]


def compose(kind, theme_name, cut, size, out):
    """kind: 'banner' (1600 x 520) or 'social' (1280 x 640)"""
    th = THEMES[theme_name]
    W, H = size
    canvas = np.empty((H, W, 3), np.float32)
    canvas[:] = np.array(th["bg"], np.float32) / 255.0
    ga = grid_layer(W, H, 32, int(W * 0.40))                   # faint 32 px grid behind the render
    gcol = np.array(th["grid"], np.float32) / 255.0
    canvas[:] = canvas * (1 - ga[..., None]) + gcol * ga[..., None]
    # render box (x0, y0, x1, y1): the hero is fitted into it, keeping its aspect
    bx0, by0, bx1, by1 = (690, 24, W - 40, H - 50) if kind == "banner" else (566, 150, W - 46, H - 52)
    asp = cut.alpha.shape[0] / cut.alpha.shape[1]
    rw = int(min(bx1 - bx0, (by1 - by0) / asp))
    rh = int(round(rw * asp))
    rx, ry = bx0 + (bx1 - bx0 - rw) // 2, by0 + (by1 - by0 - rh) // 2
    paste_cutout(canvas, cut, rx, ry, rw, shadow=th["shadow"])
    img = Image.fromarray((np.clip(canvas, 0, 1) * 255 + 0.5).astype(np.uint8), "RGB")
    dr = ImageDraw.Draw(img)
    if kind == "banner":
        tx, ty = 84, 150
        f_big, f_sub, f_note = font("bold", 112), font("regular", 31), font("regular", 21)
    else:
        tx, ty = 84, 118
        f_big, f_sub, f_note = font("bold", 112), font("regular", 32), font("regular", 21)
    sub = ["Open-source firmware, design rules", "and reference designs for flashlights"]
    dr.text((tx - 4, ty), "LuxLibre", font=f_big, fill=th["text"])
    bb = dr.textbbox((tx - 4, ty), "LuxLibre", font=f_big)
    yy = bb[3] + 30
    dr.rectangle([tx, yy, tx + 64, yy + 5], fill=th["accent"])
    yy += 30
    for ln in sub:
        dr.text((tx, yy), ln, font=f_sub, fill=th["muted"])
        yy += int(f_sub.size * 1.42)
    nb = dr.textbbox((0, 0), NOTE, font=f_note)
    nx, ny = rx + rw - (nb[2] - nb[0]) - 24, min(ry + rh + 2, H - 30 - (nb[3] - nb[1]))
    dr.rounded_rectangle([nx + nb[0] - 8, ny + nb[1] - 5, nx + nb[2] + 8, ny + nb[3] + 6], radius=5, fill=th["bg"])
    dr.text((nx, ny), NOTE, font=f_note, fill=th["muted"])
    if kind == "banner":                                       # rounded corners + 1 px border
        rad = 18
        mask = Image.new("L", (W * 4, H * 4), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, W * 4 - 1, H * 4 - 1], radius=rad * 4, fill=255)
        mask = mask.resize((W, H), Image.LANCZOS)
        border = Image.new("L", (W * 4, H * 4), 0)
        ImageDraw.Draw(border).rounded_rectangle([0, 0, W * 4 - 1, H * 4 - 1], radius=rad * 4, outline=255, width=4)
        border = border.resize((W, H), Image.LANCZOS)
        img = Image.composite(Image.new("RGB", (W, H), th["border"]), img, border)
        img = img.convert("RGBA")
        img.putalpha(mask)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    img.save(out, optimize=True)
    print("wrote %s  %s  %.0f kB" % (os.path.relpath(out, REPO), img.size, os.path.getsize(out) / 1e3))
    return out


def main():
    ap = argparse.ArgumentParser(description="LuxLibre banners and social preview from the v0.7 renders")
    ap.add_argument("--out-dir", default=os.path.join(REPO, "docs", "img"))
    a = ap.parse_args()
    cut = Cutout(IN_WHITE, IN_DARK, DARK_BG)
    compose("banner", "light", cut, (1600, 520), os.path.join(a.out_dir, "luxlibre_banner_light.png"))
    compose("banner", "dark", cut, (1600, 520), os.path.join(a.out_dir, "luxlibre_banner_dark.png"))
    compose("social", "light", cut, (1280, 640), os.path.join(a.out_dir, "social_preview.png"))


if __name__ == "__main__":
    main()
