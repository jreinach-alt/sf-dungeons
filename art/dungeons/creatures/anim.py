"""anim.py — play a creature's actions at game timing as an animated GIF (one panel per action).

    python3 art/dungeons/creatures/anim.py tortoise [--scale 3] [--facing down]
"""
import argparse, sys
from pathlib import Path
from PIL import Image, ImageDraw
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sheet as SH


def at(t, hold):
    t %= sum(hold)
    for i, h in enumerate(hold):
        if t < h:
            return i
        t -= h
    return 0


def render(name, scale, facing):
    spec, d, pal = SH.load(name)
    pk = sorted(pal)[0]
    acts = []
    for an, a in spec["action"].items():
        fr = SH.frames_of(spec, d, an, facing)
        if fr:
            acts.append((an, fr, list(a.get("hold", [8] * len(fr)))))
    total = max(sum(h) for _, _, h in acts)
    total = max(total, 90) + 30
    cw = max(f[0].shape[1] for _, f, _ in acts) * scale + 8
    ch = max(f[0].shape[0] for _, f, _ in acts) * scale + 22
    cols = min(len(acts), 2)
    rows = -(-len(acts) // cols)
    frames = []
    for t in range(0, total, 2):
        im = Image.new("RGB", (cols * cw, rows * ch), SH.BG)
        dr = ImageDraw.Draw(im)
        for k, (an, fr, hold) in enumerate(acts):
            i = min(at(t, hold), len(fr) - 1)
            x, y = (k % cols) * cw, (k // cols) * ch
            dr.text((x + 4, y + 2), f"{an} {facing}", fill=(230, 230, 230))
            im.paste(SH.tile(fr[i], pal[pk], scale), (x + 4, y + 16))
        frames.append(im)
    return frames


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("name"); ap.add_argument("--scale", type=int, default=3)
    ap.add_argument("--facing", default="down"); a = ap.parse_args()
    fr = render(a.name, a.scale, a.facing)
    out = HERE / "out" / a.name / f"anim_{a.facing}.gif"
    fr[0].save(out, save_all=True, append_images=fr[1:], duration=[(30, 30, 40)[k % 3] for k in range(len(fr))], loop=0, disposal=1)
    print(out, len(fr), "frames")
