"""view.py — look at a painted style: every frame x8 on a floor-toned ground, P1 then P2.

    python3 art/dungeons/style/view.py a_storybook [--scale 8] [--out PNG]
"""
import argparse, json, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
BG = (46, 44, 40)


def load(style):
    d = HERE / "out" / style
    pal = json.loads((d / "palettes.json").read_text())
    strips = {}
    for p in sorted(d.glob("*_*.png")):
        parts = p.stem.split("_")
        if len(parts) != 2 or parts[0] not in ("idle", "walk", "attack"):
            continue                                  # sheets, boards and debug images share the dir
        an, dr = parts
        a = np.asarray(Image.open(p))
        strips[(an, dr)] = a
    return strips, pal


def tile(f, pal, scale, bg=BG):
    lut = np.array(pal, np.uint8)
    rgb = np.where((f == 0)[..., None], np.array(bg, np.uint8), lut[f])
    return Image.fromarray(rgb.astype(np.uint8)).resize((f.shape[1] * scale, f.shape[0] * scale), Image.NEAREST)


def sheet(style, scale=8, which=("p1",)):
    strips, pal = load(style)
    order = [("idle", "right"), ("idle", "down"), ("walk", "right"), ("walk", "down"), ("attack", "right"), ("attack", "down")]
    rows = [k for k in order if k in strips]
    gap = 10
    wmax = max(strips[k].shape[1] for k in rows)
    cols = len(which)
    H = sum(strips[k].shape[0] for k in rows) * scale + gap * (len(rows) + 1)
    W = (wmax * scale + gap) * cols + gap
    im = Image.new("RGB", (W, H), BG)
    for ci, pk in enumerate(which):
        y = gap
        for k in rows:
            a = strips[k]
            bh = a.shape[0]
            bw = 32 if k[0] == "attack" else 16
            for i in range(a.shape[1] // bw):
                t = tile(a[:, i * bw:(i + 1) * bw], pal[pk], scale)
                im.paste(t, (ci * (wmax * scale + gap) + gap + i * (bw * scale + 4), y))
            y += bh * scale + gap
    return im


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("style"); ap.add_argument("--scale", type=int, default=8)
    ap.add_argument("--out", type=Path); ap.add_argument("--both", action="store_true")
    a = ap.parse_args()
    im = sheet(a.style, a.scale, ("p1", "p2") if a.both else ("p1",))
    out = a.out or (HERE / "out" / a.style / "sheet.png")
    im.save(out); print(out, im.size)
