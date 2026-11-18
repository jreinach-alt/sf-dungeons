"""scene.py — a creature lineup in the mock Hollow Wood room: the hero, a spider and the
tortoise boss at their real pixel sizes, so SCALE and distinctness are judged in context.

    python3 art/dungeons/creatures/scene.py        # writes out/lineup.png and out/lineup_crt.png
"""
import json, sys
from pathlib import Path
import numpy as np
from PIL import Image
HERE = Path(__file__).resolve().parent
STYLE = HERE.parent / "style"
sys.path.insert(0, str(STYLE))
import room as R, scene as S, view as V, sheet as SH


def creature_frame(name, action, i, facing="down"):
    spec, d, pal = SH.load(name)
    fr = SH.frames_of(spec, d, action, facing)[i]
    anc = spec["action"][action].get("anchor", spec["camera"]["anchor"])
    return fr, pal[sorted(pal)[0]], (int(anc[0]), int(anc[1] + 0.5))


def compose():
    rgb = R.to_rgb(R.build()).copy()
    items = []
    f, pal = S.hero_frame("a_storybook", "idle", "down", 0)[0], S.hero_frame("a_storybook", "idle", "down", 0)[1]["p1"]
    items.append((f, pal, (84, 176), S.anchor("a_storybook", "idle")))
    f, pal, anc = creature_frame("spider", "skitter", 1)
    items.append((f, pal, (48, 150), anc))
    f, pal, anc = creature_frame("tortoise", "rise", 4)
    items.append((f, pal, (168, 190), anc))
    for f, pal, root, anc in sorted(items, key=lambda t: t[2][1]):
        S.place(rgb, f, pal, root, anc)
    return rgb


def compose_bestiary():
    """The hero and the four briefed enemies on the Hollow Wood floor: scale and distinctness in context."""
    rgb = R.to_rgb(R.build()).copy()
    f, pal = S.hero_frame("a_storybook", "idle", "down", 0)[0], S.hero_frame("a_storybook", "idle", "down", 0)[1]["p1"]
    items = [(f, pal, (128, 188), S.anchor("a_storybook", "idle"))]
    spots = {"bellwretch": ("idle", 0, (60, 142)), "thornhopper": ("idle", 0, (104, 160)),
             "candlemaw": ("idle", 0, (152, 150)), "crownling": ("idle", 1, (200, 168))}
    for name, (an, i, root) in spots.items():
        fr, p, anc = creature_frame(name, an, i)
        items.append((fr, p, root, anc))
    for fr, p, root, anc in sorted(items, key=lambda t: t[2][1]):
        S.place(rgb, fr, p, root, anc)
    return rgb


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "bestiary":
    rgb = compose_bestiary()
    out = HERE / "out"
    Image.fromarray(rgb).resize((rgb.shape[1] * 3, rgb.shape[0] * 3), Image.NEAREST).save(out / "bestiary_room_x3.png")
    S.crt(rgb).save(out / "bestiary_room_crt.png")
    print("bestiary room ->", out / "bestiary_room_x3.png")
    sys.exit(0)

if __name__ == "__main__":
    rgb = compose()
    out = HERE / "out"
    Image.fromarray(rgb).save(out / "lineup.png")
    Image.fromarray(rgb).resize((rgb.shape[1] * 3, rgb.shape[0] * 3), Image.NEAREST).save(out / "lineup_x3.png")
    S.crt(rgb).save(out / "lineup_crt.png")
    print("lineup ->", out / "lineup_x3.png")
