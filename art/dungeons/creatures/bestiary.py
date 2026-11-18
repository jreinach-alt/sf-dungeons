"""bestiary.py — a lineup board of several creatures: idle, move, prepare, attack, two facings.

    python3 art/dungeons/creatures/bestiary.py bellwretch thornhopper candlemaw crownling
Writes out/bestiary.png (and a native 1x strip). Silhouette-first review: every creature on the
same ground, at the same scale, in the same frame positions, so the family reads as a bestiary.
"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sheet as SH

MOVE = {"bellwretch": "scuttle", "thornhopper": "hop", "candlemaw": "waddle", "crownling": "drift"}
STATES = [("idle", 0), ("MOVE", 1), ("prepare", -1), ("attack", -1)]


def board(names, scale=5, facings=("down", "right")):
    cw = 32 * scale + 6
    rows = []
    for n in names:
        spec, d, pal = SH.load(n)
        pk = sorted(pal)[0]
        for fc in facings:
            cells = []
            for st, idx in STATES:
                an = MOVE.get(n, "move") if st == "MOVE" else st
                fr = SH.frames_of(spec, d, an, fc)
                if fr:
                    cells.append((st, fr[idx if idx >= 0 else len(fr) + idx]))
            rows.append((f"{n} {fc}", pal[pk], cells))
    W = cw * 4 + 130
    H = len(rows) * (32 * scale + 6) + 8
    im = Image.new("RGB", (W, H), SH.BG)
    dr = ImageDraw.Draw(im)
    for r, (label, pal, cells) in enumerate(rows):
        y = 4 + r * (32 * scale + 6)
        dr.text((4, y + 32 * scale // 2 - 5), label, fill=(230, 230, 230))
        for c, (st, f) in enumerate(cells):
            im.paste(SH.tile(f, pal, scale), (128 + c * cw, y))
            if r == 0:
                dr.text((128 + c * cw + 2, 0), st.lower(), fill=(200, 200, 120))
    return im


if __name__ == "__main__":
    names = sys.argv[1:] or ["bellwretch", "thornhopper", "candlemaw", "crownling"]
    im = board(names)
    out = HERE / "out" / "bestiary.png"
    im.save(out)
    print(out, im.size)
