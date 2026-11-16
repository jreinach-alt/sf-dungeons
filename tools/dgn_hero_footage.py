#!/usr/bin/env python3
"""dgn_hero_footage.py — record the dgn_hero ROM as an animated GIF.

    python3 tools/dgn_hero_footage.py OUT.gif [--frames 256] [--start 60]
        [--scale 2] [--crop X,Y,W,H] [--rom build/dgn_hero.sfc]

Lockstep capture (vendor/machine.py): the core is parked and stepped one
EMULATED frame at a time, and every second frame is photographed, so the
footage is a pure function of the ROM. No wall clock anywhere (docs/45).

GIF timing: two 60.0988 Hz frames last 3.33 cs, and a GIF delay is whole
centiseconds, so the delays cycle 3, 3, 4 (mean 3.33 cs = real speed).
The picture is the rendered screen exactly as Mesen2 presents it, upscaled by
nearest neighbour.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "vendor"))
from machine import Machine  # noqa: E402

STEP = 2                     # emulated frames per GIF frame
DELAYS_MS = (30, 30, 40)     # mean 33.3 ms = STEP frames at 60.1 Hz


def record(rom: Path, start: int, frames: int, scale: int, crop=None) -> list[Image.Image]:
    shots = []
    with Machine(str(rom)) as m, tempfile.TemporaryDirectory() as td:
        m.advance(start)
        for k in range(frames // STEP):
            m.advance(STEP)
            p = Path(td) / f"f{k:04d}.png"
            m.screenshot(str(p))
            im = Image.open(p).convert("RGB")
            if crop:
                x, y, w, h = crop
                im = im.crop((x, y, x + w, y + h))
            shots.append(im.resize((im.width * scale, im.height * scale), Image.NEAREST))
    return shots


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--rom", type=Path, default=REPO / "build" / "dgn_hero.sfc")
    ap.add_argument("--start", type=int, default=60)
    ap.add_argument("--frames", type=int, default=256)
    ap.add_argument("--scale", type=int, default=2)
    ap.add_argument("--crop", help="X,Y,W,H in Mesen's 256x239 PNG pixels")
    a = ap.parse_args(argv)
    crop = tuple(int(v) for v in a.crop.split(",")) if a.crop else None
    shots = record(a.rom, a.start, a.frames, a.scale, crop)
    durations = [DELAYS_MS[k % len(DELAYS_MS)] for k in range(len(shots))]
    shots[0].save(a.out, save_all=True, append_images=shots[1:], duration=durations,
                  loop=0, optimize=False, disposal=1)
    print(f"dgn_hero_footage: {len(shots)} GIF frames ({a.frames} emulated, "
          f"frames {a.start + STEP}..{a.start + a.frames}) -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
