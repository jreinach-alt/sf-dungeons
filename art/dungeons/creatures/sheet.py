"""sheet.py — review image for ANY painted creature: every action x facing, at a scale,
on a floor-toned ground, with the sprite's root marked. For the agent's review loop.

    python3 art/dungeons/creatures/sheet.py spider [--scale 8] [--facings right,down]
"""
import argparse, json, sys, tomllib
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
BG = (46, 62, 38)


def load(name):
    spec = tomllib.loads((HERE / "specs" / f"{name}.toml").read_text())
    d = HERE / "out" / name
    pal = json.loads((d / "palettes.json").read_text())
    return spec, d, pal


def tile(f, pal, scale, bg=BG):
    lut = np.array(pal, np.uint8)
    rgb = np.where((f == 0)[..., None], np.array(bg, np.uint8), lut[f])
    return Image.fromarray(rgb.astype(np.uint8)).resize((f.shape[1] * scale, f.shape[0] * scale), Image.NEAREST)


def frames_of(spec, d, an, facing):
    p = d / f"{an}_{facing}.png"
    if not p.exists():
        return []
    a = np.asarray(Image.open(p))
    box = spec["action"][an].get("box", spec["camera"]["box"])
    return [a[:, i * box[0]:(i + 1) * box[0]] for i in range(a.shape[1] // box[0])]


def sheet(name, scale=8, facings=("right", "down"), pk=None):
    spec, d, pal = load(name)
    pk = pk or sorted(pal)[0]
    rows = []
    for an in spec["action"]:
        for f in facings:
            fr = frames_of(spec, d, an, f)
            if fr:
                rows.append((f"{an} {f}", fr))
    gap = 6
    W = max(sum(x.shape[1] * scale + gap for x in fr) for _, fr in rows) + gap
    H = sum(fr[0].shape[0] * scale + gap + 12 for _, fr in rows) + gap
    im = Image.new("RGB", (W, H), BG)
    dr = ImageDraw.Draw(im)
    y = gap
    for label, fr in rows:
        dr.text((gap, y), label, fill=(230, 230, 230))
        y += 12
        x = gap
        for f in fr:
            im.paste(tile(f, pal[pk], scale), (x, y))
            x += f.shape[1] * scale + gap
        y += fr[0].shape[0] * scale + gap
    return im


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("name"); ap.add_argument("--scale", type=int, default=8)
    ap.add_argument("--facings", default="right,down"); a = ap.parse_args()
    out = HERE / "out" / a.name / "sheet.png"
    im = sheet(a.name, a.scale, tuple(a.facings.split(",")))
    im.save(out); print(out, im.size)
