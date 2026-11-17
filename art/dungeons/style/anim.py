"""anim.py — play a painted style at game timing, as an animated GIF.

    python3 art/dungeons/style/anim.py a_storybook [--scale 5] [--palette p1|p2]

One panel per action x facing, each stepping on actions.toml's holds (game
frames at 60 Hz): idle 30/30, walk 8 x4, attack 4/4/6 then a rest so the swing
reads as a swing. Two game frames per GIF frame, the delays cycling 30/30/40 ms
(mean 33.3), so playback is real speed. Lockstep-style: no wall clock.
"""
import argparse, sys, tomllib
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import view as V

PANELS = [("idle", "right"), ("idle", "down"), ("walk", "right"), ("walk", "down"),
          ("attack", "right"), ("attack", "down")]


def hold_table(action_name):
    base = tomllib.loads((HERE / "actions.toml").read_text())["action"][action_name]
    hold = list(base["hold"])
    if action_name == "attack":
        hold = hold + [22]          # a rest on the last pose so the swing reads as a swing
    return hold


def frame_at(t, hold):
    t %= sum(hold)
    for i, h in enumerate(hold):
        if t < h:
            return i
        t -= h
    return 0


def render(style, scale=5, pk="p1", total=128):
    strips, pal = V.load(style)
    panels = []
    for an, dr in PANELS:
        a = strips[(an, dr)]
        bw = 32 if an == "attack" else 16
        panels.append((an, dr, a, bw))
    cw = 32 * scale + 8
    gap = 6
    W = cw * 2 + gap * 3
    H = (32 * scale + 22) * 3 + gap * 4
    frames = []
    for t in range(0, total, 2):
        im = Image.new("RGB", (W, H), V.BG)
        d = ImageDraw.Draw(im)
        for k, (an, dr, a, bw) in enumerate(panels):
            col, row = k % 2, k // 2
            hold = hold_table(an)
            i = min(frame_at(t, hold), a.shape[1] // bw - 1)
            tile = V.tile(a[:, i * bw:(i + 1) * bw], pal[pk], scale)
            x = gap + col * (cw + gap) + (cw - tile.width) // 2
            y = gap + row * (32 * scale + 22 + gap)
            im.paste(tile, (x, y + 16))
            d.text((gap + col * (cw + gap) + 2, y + 1), f"{an} {dr}", fill=(200, 200, 200))
        frames.append(im)
    return frames


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("style"); ap.add_argument("--scale", type=int, default=5)
    ap.add_argument("--palette", default="p1"); a = ap.parse_args()
    fr = render(a.style, a.scale, a.palette)
    delays = [(30, 30, 40)[k % 3] for k in range(len(fr))]
    out = HERE / "out" / a.style / f"anim_{a.palette}.gif"
    fr[0].save(out, save_all=True, append_images=fr[1:], duration=delays, loop=0, optimize=False, disposal=1)
    print(out, len(fr), "frames")
