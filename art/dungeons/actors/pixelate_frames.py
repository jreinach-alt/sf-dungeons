"""pixelate_frames.py — the PIXELATE stage: raw data frames -> indexed strips.

    python3 art/dungeons/actors/pixelate_frames.py [--work build/dgn_art_work]
        [--model wanderer] [--actions idle,walk] [--single PATH]

For every action x direction in actions.toml, reads
    <work>/<model>_<action>_<dir>_<i>_body.png      (render_actor.py)
runs each through pixelate_actor.pixelate (refuse-never-crop), and writes
    art/dungeons/actors/frames/<model>_<action>_<dir>.png
an INDEXED strip, frames side by side, index 0 transparent. Its embedded
palette is the grey preview ramp: the indices are the contract (roles.toml),
the colours are not (palettes.json, 11 §5 stage 1, owns them).

--single pixelates one raw frame to <work>/single_x8.png for looking.
"""
from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pixelate_actor as P  # noqa: E402

REPO = HERE.parents[2]
FRAMES = HERE / "frames"
GREY = [v for i in range(16) for v in (i * 16, i * 16, i * 16)]


def load_raw(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"))


def sprite(raw, act, fam, label):
    cam = act["camera"]
    return P.pixelate(raw, cam["supersample"], fam, cam["margin_px"], tuple(cam["box"]), label)


def save_indexed(a: np.ndarray, path: Path):
    im = Image.fromarray(a.astype(np.uint8), "P")
    im.putpalette(GREY)
    im.info["transparency"] = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, transparency=0, optimize=False)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", type=Path, default=REPO / "build" / "dgn_art_work")
    ap.add_argument("--model", default="wanderer")
    ap.add_argument("--actions", default="idle,walk")
    ap.add_argument("--single", type=Path)
    a = ap.parse_args(argv)
    act = tomllib.loads((HERE / "actions.toml").read_text())
    fam = P.load_family("hero")
    if a.single:
        s = sprite(load_raw(a.single), act, fam, a.single.name)
        im = Image.fromarray(s, "P")
        im.putpalette(GREY)
        im.resize((s.shape[1] * 8, s.shape[0] * 8), Image.NEAREST).save(a.work / "single_x8.png")
        print(f"foot row {P.foot_row(s, fam.outline)}")
        return 0
    n = 0
    for name in a.actions.split(","):
        spec = act["action"][name]
        for d in act["camera"]["directions"]:
            fr = []
            for i in range(spec["frames"]):
                p = a.work / f"{a.model}_{name}_{d}_{i}_body.png"
                if not p.is_file():
                    print(f"pixelate: missing {p} (run the render stage)", file=sys.stderr)
                    return 1
                fr.append(sprite(load_raw(p), act, fam, p.name))
            save_indexed(np.concatenate(fr, axis=1), FRAMES / f"{a.model}_{name}_{d}.png")
            n += len(fr)
    print(f"pixelate: {n} frames -> {FRAMES.relative_to(REPO)}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
