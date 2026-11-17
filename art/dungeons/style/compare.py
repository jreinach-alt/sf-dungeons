"""compare.py — the three treatments side by side: idle, walk and attack, two facings.

    python3 art/dungeons/style/compare.py [--scale 6] [--palette p1|p2]
"""
import argparse, sys
from pathlib import Path
from PIL import Image, ImageDraw
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import view as V

NAMES = [("a_storybook", "A  Storybook Wanderer"), ("b_practical", "B  Practical-Effects Adventurer"),
         ("c_painted16", "C  Painted 16-Bit Adventurer")]
ROWS = [("idle", "right", 2, 16), ("idle", "down", 2, 16), ("walk", "right", 4, 16),
        ("walk", "down", 4, 16), ("attack", "right", 3, 32), ("attack", "down", 3, 32)]


def board(scale=6, pk="p1"):
    cols = []
    for n, _ in NAMES:
        strips, pal = V.load(n)
        ims = []
        for an, dr, cnt, bw in ROWS:
            a = strips[(an, dr)]
            w = 4 * (16 * scale + 4) if bw == 16 else 3 * (32 * scale + 4)
            row = Image.new("RGB", (w, a.shape[0] * scale), V.BG)
            for i in range(cnt):
                row.paste(V.tile(a[:, i * bw:(i + 1) * bw], pal[pk], scale), (i * (bw * scale + 4), 0))
            ims.append(row)
        cols.append(ims)
    colw = [max(i.width for i in c) for c in cols]
    H = sum(i.height + 8 for i in cols[0]) + 36
    o = Image.new("RGB", (sum(colw) + 16 * (len(cols) + 1), H), V.BG)
    d = ImageDraw.Draw(o)
    x = 16
    for (n, label), c, w in zip(NAMES, cols, colw):
        d.text((x, 10), label, fill=(236, 236, 236))
        y = 30
        for im in c:
            o.paste(im, (x, y)); y += im.height + 8
        x += w + 16
    return o


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--scale", type=int, default=6)
    ap.add_argument("--palette", default="p1"); a = ap.parse_args()
    o = board(a.scale, a.palette); out = HERE / "out" / "compare_abc.png"; o.save(out); print(out, o.size)
