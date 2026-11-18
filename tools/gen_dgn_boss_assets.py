#!/usr/bin/env python3
"""gen_dgn_boss_assets.py — the boss-battle spike's art, converted for the ROM.

    python3 tools/gen_dgn_boss_assets.py OUT_DIR

docs/dungeons/18: a 64x64 boss, two players (idle / walk / ATTACK) and two small enemies in one
scene. Reads ONLY committed inputs (the build never runs Blender):
  art/dungeons/creatures/out/bellwretch64/*_{down,right}.png   the boss: 14 frames a facing
  art/dungeons/creatures/out/thornhopper/hop_right.png         enemy A, 32x32, 4 frames
  art/dungeons/creatures/out/thornling/hop_right.png           enemy B, 16x16, 4 frames
  art/dungeons/style/out/a_storybook/{idle,walk,attack}_{right,down}.png   the players
  art/dungeons/style/out/a_storybook/palettes.json             P1 / P2
and emits (byte-identical on re-run):
  dgnb_boss_down.bin / dgnb_boss_right.bin   14 frames x 2,048 B: the boss's 8x8-tile image,
                     row-major, so ONE tile row (8 tiles, 256 B) is ONE DMA and the 8 rows of a frame land
                     on the 16-wide OBJ name table's rows. STREAMED, one slot.
  dgnb_hero.bin      1 facing x 9 frames x 512 B: a player's 4x4-tile slot image (32x32). Frames 0-1 idle and
                     2-5 walk are 16x32 (the left two tile columns, the rest zero); 6-8 attack, 32x32.
                     STREAMED, one slot per player. 4 DMAs of 128 B.
  dgnb_res.bin       3,072 B: the two enemies, RESIDENT in OBJ name table 1 (uploaded once, at enter)
  dgnb_pal.bin       128 B: OBJ palettes 0 P1, 1 P2, 2 boss, 3 enemies (BGR555)
  dgnb_frames.inc    counts, anchors and the five TIMELINES (frame, hold) as ca65 equates and tables.
                     Never an address.

SPIKE PACING, deliberately the worst case: every hold is QUANTISED UP to a multiple of 6 game frames, so the
actors' frame changes land on the SAME frames as often as the timelines allow. A real game would not do that;
a budget measurement should.
"""
from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "art" / "dungeons" / "actors"))
from gen_dgn_hero_assets import bgr555, encode_4bpp  # noqa: E402
import sheets  # noqa: E402  (BG_FLOOR: the floor-coloured backdrop the hero spike uses)

CRE = REPO / "art" / "dungeons" / "creatures"
STY = REPO / "art" / "dungeons" / "style" / "out" / "a_storybook"
QUANT = 6                    # TICK: ok — a hold's granularity in game frames (spike pacing, see the docstring)

BOSS_FACINGS = ("down", "right")
BOSS_ACTIONS = ("idle", "scuttle", "prepare", "attack")    # TICK: ok — ANIMATION frames of the strips (4 + 4 + 3 + 3 a facing), not video frames
HERO_ACTIONS = (("idle", 2), ("walk", 4), ("attack", 3))   # TICK: ok — animation frames of a strip (9 a facing)
HERO_FACINGS = ("right",)           # P1 faces right, P2 is its HFLIP; the boss is the only thing above them


def strip(path: Path, w: int, h: int):
    a = np.asarray(Image.open(path))
    assert a.ndim == 2 and a.shape[0] == h and a.shape[1] % w == 0, f"{path}: {a.shape} is not {w}x{h} frames"
    return [a[:, i * w:(i + 1) * w] for i in range(a.shape[1] // w)]


def tiles_rowmajor(img: np.ndarray) -> bytes:
    h, w = img.shape
    return b"".join(encode_4bpp(img[y:y + 8, x:x + 8]) for y in range(0, h, 8) for x in range(0, w, 8))


def quant(h: int) -> int:
    return max(QUANT, ((h + QUANT // 2) // QUANT) * QUANT)


def spec_holds(name: str) -> dict:
    s = tomllib.loads((CRE / "specs" / f"{name}.toml").read_text())
    return {a: [quant(h) for h in v["hold"]] for a, v in s["action"].items()}


def boss():
    holds = spec_holds("bellwretch64")
    blobs, order = {}, {}                      # order[(facing, action)] = first frame id (facing-major)
    fid = 0
    for fc in BOSS_FACINGS:
        data = b""
        for act in BOSS_ACTIONS:
            fr = strip(CRE / "out" / "bellwretch64" / f"{act}_{fc}.png", 64, 64)
            assert len(fr) == len(holds[act]), (act, len(fr))
            order[(fc, act)] = fid
            fid += len(fr)
            for f in fr:
                b = tiles_rowmajor(f)
                assert len(b) == 2048
                data += b
        assert len(data) == 14 * 2048
        blobs[fc] = data
    return blobs, order, holds


def hero():
    ho = {}
    hold = {"idle": [30, 30], "walk": [8, 8, 8, 8], "attack": [4, 4, 6]}   # style/actions.toml, as the spike's
    data = b""
    first = {}
    n = 0
    for fc in HERO_FACINGS:
        for act, cnt in HERO_ACTIONS:
            w = 32 if act == "attack" else 16
            fr = strip(STY / f"{act}_{fc}.png", w, 32)
            assert len(fr) == cnt, (act, fc, len(fr))
            first[(fc, act)] = n
            for f in fr:
                canvas = np.zeros((32, 32), np.uint8)
                canvas[:, :w] = f
                data += tiles_rowmajor(canvas)
                n += 1
    assert len(data) == len(HERO_FACINGS) * 9 * 512
    return data, first, {a: [quant(h) for h in v] for a, v in hold.items()}


def resident():
    """Table 1: Thornhopper's 4 hop frames (32x32) in rows 0-3, one per 4 tile columns; Thornling's 4 (16x16)
    in rows 4-5, one per 2 tile columns. 16 tiles wide, 6 rows."""
    grid = [[bytes(32)] * 16 for _ in range(6)]
    for k, f in enumerate(strip(CRE / "out" / "thornhopper" / "hop_right.png", 32, 32)):
        for ty in range(4):
            for tx in range(4):
                grid[ty][k * 4 + tx] = encode_4bpp(f[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8])
    for k, f in enumerate(strip(CRE / "out" / "thornling" / "hop_right.png", 16, 16)):
        for ty in range(2):
            for tx in range(2):
                grid[4 + ty][k * 2 + tx] = encode_4bpp(f[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8])
    return b"".join(t for row in grid for t in row), spec_holds("thornhopper")["hop"], spec_holds("thornling")["hop"]


def pal_blob() -> bytes:
    sty = json.loads((STY / "palettes.json").read_text())
    pals = [sty["p1"], sty["p2"],
            json.loads((CRE / "out" / "bellwretch64" / "palettes.json").read_text())["base"],
            json.loads((CRE / "out" / "thornhopper" / "palettes.json").read_text())["base"]]
    assert json.loads((CRE / "out" / "thornling" / "palettes.json").read_text())["base"] == pals[3], \
        "the two enemies share OBJ palette 3: the shrunken one must carry the same colours"
    words = []
    for p in pals:
        assert len(p) == 16
        words += [0] + [bgr555(c) for c in p[1:]]
    return b"".join(w.to_bytes(2, "little") for w in words)


def timelines(order, bh, hf, hh, eah, ebh):
    """{name: [(frame id, hold)]}. Frame ids: boss 0-27 (down 0-13, right 14-27); a player 0-8 (idle 0-1,
    walk 2-5, attack 6-8); an enemy 0-3."""
    def seg(first, holds):
        return [(first + i, h) for i, h in enumerate(holds)]
    boss_t = []
    for fc in BOSS_FACINGS:
        boss_t += seg(order[(fc, "idle")], bh["idle"])
        boss_t += seg(order[(fc, "scuttle")], bh["scuttle"]) * 2
        boss_t += seg(order[(fc, "prepare")], bh["prepare"])
        boss_t += seg(order[(fc, "attack")], bh["attack"])
    idle, walk, atk = (seg(0, hh["idle"]), seg(2, hh["walk"]), seg(6, hh["attack"]))
    p1 = idle + walk * 2 + atk + idle + walk + atk
    p2 = walk + atk + walk * 2 + idle + atk
    return {"boss": boss_t, "p1": p1, "p2": p2, "ea": seg(0, eah), "eb": seg(0, ebh)}


def inc_text(tl) -> str:
    L = ["; GENERATED by tools/gen_dgn_boss_assets.py: do not edit.",
         "; Counts, anchors and the five timelines (frame id, hold in game frames). No addresses.",
         f"DGNB_BACKDROP_BGR = {bgr555(sheets.BG_FLOOR)}",
         "DGNB_BOSS_AX = 32          ; bellwretch64: camera.anchor, in a 64x64 box",
         "DGNB_BOSS_AY = 46",
         "DGNB_BOSS_FRAMES_A_FACING = 14",
         "DGNB_H_AX = 10             ; a_storybook: idle/walk anchor in the 16x32 box",
         "DGNB_H_AY = 27",
         "DGNB_H_ATK_AX = 16         ; the attack's, in its 32x32 box",
         "DGNB_H_ATK0 = 6            ; the first attack frame of a player's nine",
         "DGNB_EA_AX = 17            ; thornhopper, 32x32",
         "DGNB_EA_AY = 24",
         "DGNB_EB_AX = 8             ; thornling, 16x16",
         "DGNB_EB_AY = 12"]
    for k, t in tl.items():
        L.append(f"DGNB_{k.upper()}_N = {len(t)}")
    L.append('.pushseg\n.segment "RODATA"')
    for k, t in tl.items():
        L.append(f"dgnb_{k}_fr: .word {', '.join(str(f) for f, _ in t)}")
        L.append(f"dgnb_{k}_hd: .byte {', '.join(str(h) for _, h in t)}")
    L.append(".popseg")
    assert all(h % QUANT == 0 for t in tl.values() for _, h in t)
    return "\n".join(L) + "\n"


def main(argv) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    out = Path(argv[1])
    out.mkdir(parents=True, exist_ok=True)
    blobs, order, bh = boss()
    hero_blob, _, hh = hero()
    res, eah, ebh = resident()
    tl = timelines(order, bh, None, hh, eah, ebh)
    (out / "dgnb_boss_down.bin").write_bytes(blobs["down"])
    (out / "dgnb_boss_right.bin").write_bytes(blobs["right"])
    (out / "dgnb_hero.bin").write_bytes(hero_blob)
    (out / "dgnb_res.bin").write_bytes(res)
    (out / "dgnb_pal.bin").write_bytes(pal_blob())
    (out / "dgnb_frames.inc").write_text(inc_text(tl))
    print("gen_dgn_boss_assets: boss 2x%d B, hero %d B, resident %d B, timelines %s" % (
        len(blobs["down"]), len(hero_blob), len(res), {k: len(v) for k, v in tl.items()}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
