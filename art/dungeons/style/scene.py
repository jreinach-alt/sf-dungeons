"""scene.py — put the painted wanderer in the Hollow Wood room, natively and on a CRT.

    python3 art/dungeons/style/scene.py              # all three treatments
    python3 art/dungeons/style/scene.py a_storybook

For each style writes (art/dungeons/style/out/<style>/):
    room.png        256x224, the NATIVE frame: BG layer + OBJ layer composed as the
                    PPU would (index 0 of a sprite is transparent)
    room_x3.png     the same, 3x nearest, to look at
    room_crt.png    a CRT preview: 8:7 pixel aspect, scanlines, horizontal bleed,
                    bloom and a little vignette. A look-alike, not a measurement.
The hero is P1 walking, a P1 idle in front view, and P2 attacking the Rootling,
so facing, attack direction and weapon readability are judged where they live.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import room as R  # noqa: E402
import view as V  # noqa: E402

STYLES = ["a_storybook", "b_practical", "c_painted16"]


def hero_frame(style, action, direction, i):
    strips, pal = V.load(style)
    a = strips[(action, direction)]
    bw = 32 if action == "attack" else 16
    return a[:, i * bw:(i + 1) * bw], pal


def anchor(style, action):
    import tomllib
    s = tomllib.loads((HERE / "styles" / f"{style}.toml").read_text())["camera"]
    if action == "attack":
        ax, ay = s.get("attack_anchor", [16, s["anchor"][1]])
    else:
        ax, ay = s["anchor"]
    return int(ax), int(ay + 0.5)


def place(rgb, frame, pal_rgb, root_xy, anc):
    """Composite an indexed sprite whose ROOT pixel lands on root_xy (index 0 = transparent)."""
    h, w = frame.shape
    ox, oy = root_xy[0] - anc[0], root_xy[1] - anc[1]
    lut = np.array(pal_rgb, np.uint8)
    for y in range(h):
        for x in range(w):
            v = frame[y, x]
            if v and 0 <= oy + y < rgb.shape[0] and 0 <= ox + x < rgb.shape[1]:
                rgb[oy + y, ox + x] = lut[v]


def compose(style):
    rgb = R.to_rgb(R.build()).copy()
    # draw order = the sprite priority a lower root y is "behind": back to front
    items = [("walk", "right", 1, "p1", (112, 158)),
             ("idle", "down", 0, "p1", (72, 176)),
             ("attack", "right", 2, "p2", (146, 170))]
    for an, dr, i, pk, root in sorted(items, key=lambda t: t[4][1]):
        f, pal = hero_frame(style, an, dr, i)
        place(rgb, f, pal[pk], root, anchor(style, an))
    return rgb


def crt(rgb, scale=4):
    """A CRT look-alike. 256x224 pixels shown 8:7 wide, scanlined, bloomed."""
    h, w, _ = rgb.shape
    im = Image.fromarray(rgb).resize((w * scale, h * scale), Image.NEAREST)
    im = im.resize((int(w * scale * 8 / 7), h * scale), Image.BILINEAR)
    a = np.asarray(im).astype(float) / 255.0
    # horizontal phosphor bleed
    bl = np.asarray(Image.fromarray((a * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(scale * 0.55))).astype(float) / 255.0
    a = 0.62 * a + 0.38 * bl
    # scanlines: each source line is `scale` rows, the lower third darker
    rows = np.arange(a.shape[0]) % scale
    mask = np.where(rows >= scale - max(1, scale // 3), 0.58, 1.0)[:, None, None]
    a = a * mask
    # bloom: blurred bright pass added back
    bright = np.clip(a - 0.55, 0, 1)
    bb = np.asarray(Image.fromarray((bright * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(scale * 2.0))).astype(float) / 255.0
    a = np.clip(a + 0.9 * bb, 0, 1)
    # vignette
    yy, xx = np.mgrid[0:a.shape[0], 0:a.shape[1]]
    d = ((xx / a.shape[1] - 0.5) ** 2 + (yy / a.shape[0] - 0.5) ** 2) * 1.6
    a = a * (1.0 - d)[..., None]
    return Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8))


def run(style):
    out = HERE / "out" / style
    rgb = compose(style)
    Image.fromarray(rgb).save(out / "room.png")
    Image.fromarray(rgb).resize((rgb.shape[1] * 3, rgb.shape[0] * 3), Image.NEAREST).save(out / "room_x3.png")
    crt(rgb).save(out / "room_crt.png")
    print("scene:", style)


if __name__ == "__main__":
    for s in (sys.argv[1:] or STYLES):
        run(s)
