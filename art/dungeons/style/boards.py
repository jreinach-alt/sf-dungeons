"""boards.py — the review boards: per-style sheets, native-resolution strips, A/B/C comparison.

    python3 art/dungeons/style/boards.py
"""
import sys
from pathlib import Path
import numpy as np
from PIL import Image
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import view as V, compare as C

STYLES = ["a_storybook", "b_practical", "c_painted16"]
PREFERRED = "a_storybook"


def native(style):
    """The sprites at actual native pixel resolution (1x), P1, on the room's floor tone."""
    strips, pal = V.load(style)
    rows = [("idle", "right"), ("idle", "down"), ("walk", "right"), ("walk", "down"), ("attack", "right"), ("attack", "down")]
    gap = 3
    rendered = []
    for k in rows:
        a = strips[k]; bw = 32 if k[0] == "attack" else 16
        n = a.shape[1] // bw
        row = Image.new("RGB", (n * (bw + gap) + gap, a.shape[0] + 2 * gap), (46, 62, 38))
        for i in range(n):
            row.paste(V.tile(a[:, i * bw:(i + 1) * bw], pal["p1"], 1, bg=(46, 62, 38)), (gap + i * (bw + gap), gap))
        rendered.append(row)
    W = max(r.width for r in rendered)
    o = Image.new("RGB", (W, sum(r.height for r in rendered)), (46, 62, 38))
    y = 0
    for r in rendered:
        o.paste(r, (0, y)); y += r.height
    return o


if __name__ == "__main__":
    for s in STYLES:
        out = HERE / "out" / s
        V.sheet(s, 7, ("p1", "p2") if s == PREFERRED else ("p1",)).save(out / "sheet.png")
        n = native(s); n.save(out / "native_1x.png")
        n.resize((n.width * 4, n.height * 4), Image.NEAREST).save(out / "native_4x.png")
    C.board(6).save(HERE / "out" / "compare_abc.png")
    # the three rooms stacked, cropped to the play area, for a same-scale comparison
    crops = [Image.open(HERE / "out" / s / "room_x3.png").crop((60, 230, 700, 600)) for s in STYLES]
    o = Image.new("RGB", (crops[0].width, (crops[0].height + 4) * 3))
    for i, c in enumerate(crops):
        o.paste(c, (0, i * (c.height + 4)))
    o.save(HERE / "out" / "rooms_abc.png")
    print("boards done")
