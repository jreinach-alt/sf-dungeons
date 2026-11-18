#!/usr/bin/env python3
"""gen_dgn_fight_assets.py — the choreographed boss fight, converted for the ROM (docs/dungeons/19).

    python3 tools/gen_dgn_fight_assets.py OUT_DIR [--mode choreo|naive] [--preview OUT.gif]

Reads ONLY committed inputs (the build never runs Blender): the creature strips under
art/dungeons/creatures/out/{bellwretch64,thornhopper,thornling}, the hero strips under
art/dungeons/style/out/a_storybook. The director (tools/dgn_fight/director.py) turns them into a SCORE, and this
script emits (byte-identical on re-run):

  dgnf_boss0/1/2.bin  3 x 28,672 B   the boss's 38 frames (19 a facing, down then right), 2,048 B each: an 8x8-tile
                                     image, row-major, so one tile row is one 256 B DMA. 14 frames to a blob
                                     (a frame must not cross a bank)
  dgnf_hero.bin       9,216 B        the players' 18 frames (9 a facing), a 4x4-tile slot image each (512 B)
  dgnf_res.bin        8,192 B        both enemies' 10 frames, RESIDENT in OBJ name table 1 (16 rows of 16 tiles)
  dgnf_pal.bin        128 B          OBJ palettes 0 P1, 1 P2, 2 boss, 3 enemies
  dgnf_score.bin      32,768 B       580 ticks x 51 B: the OAM shadow (12 entries + 3 hi bytes) the ROM copies in
  dgnf_cmds.bin       16,384 B       the DMA rows to play, 6 B each, grouped by tick
  dgnf_ptr.bin        2,048 B        T + 2 u16 byte offsets into the command stream: tick t plays [ptr[t], ptr[t+1]),
                                     and the entry-state rows (loaded in forced blank) are [ptr[T], ptr[T+1])
  dgnf_frames.inc     equates and the entry-state command list. Never an address.
  dgnf_report.json    the bytes-per-tick profile of BOTH compilations, so the control and the choreography are
                      compared on the same score

`--mode naive` emits the same score with the unchoreographed stream (one buffer, every row on the tick the frame
changes): the control ROM (`make dgn_fight_naive`). `--mode hybrid` plans the boss only (the players follow human
input and cannot be prefetched): what a real game can do (`make dgn_fight_hybrid`).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "art" / "dungeons" / "actors"))
from dgn_fight import director as D  # noqa: E402
from gen_dgn_hero_assets import bgr555, encode_4bpp  # noqa: E402
import sheets  # noqa: E402

CRE = REPO / "art" / "dungeons" / "creatures" / "out"
STY = REPO / "art" / "dungeons" / "style" / "out" / "a_storybook"
SCORE_CLAIM, CMDS_CLAIM, PTR_CLAIM = 32768, 16384, 2048


def strip(path: Path, w: int, h: int):
    a = np.asarray(Image.open(path))
    assert a.ndim == 2 and a.shape[0] == h and a.shape[1] % w == 0, f"{path}: {a.shape} is not {w}x{h} frames"
    return [a[:, i * w:(i + 1) * w] for i in range(a.shape[1] // w)]


def tiles_rowmajor(img: np.ndarray) -> bytes:
    h, w = img.shape
    return b"".join(encode_4bpp(img[y:y + 8, x:x + 8]) for y in range(0, h, 8) for x in range(0, w, 8))


def boss_frames():
    out = []
    for fc in D.FACINGS:
        for act, n in D.BOSS_ACTIONS:
            fr = strip(CRE / "bellwretch64" / f"{act}_{fc}.png", 64, 64)
            assert len(fr) == n, (act, fc, len(fr))
            out += fr
    assert len(out) == 2 * D.BOSS_FPF
    return out


def hero_frames():
    out = []
    for fc in D.FACINGS:
        for act, n in D.HERO_ACTIONS:
            w = 32 if act == "attack" else 16
            fr = strip(STY / f"{act}_{fc}.png", w, 32)
            assert len(fr) == n, (act, fc, len(fr))
            for f in fr:
                c = np.zeros((32, 32), np.uint8)
                c[:, :w] = f
                out.append(c)
    assert len(out) == 2 * D.HERO_FPF
    return out


def enemy_frames(name: str, w: int):
    out = []
    for act, n in D.ENEMY_ACTIONS:
        fr = strip(CRE / name / f"{act}_right.png", w, w)
        assert len(fr) == n, (name, act, len(fr))
        out += fr
    return out


def boss_blobs(frames):
    blobs = []
    for b in range(3):
        data = b""
        for f in range(b * D.BOSS_FRAMES_PER_BLOB, (b + 1) * D.BOSS_FRAMES_PER_BLOB):
            data += tiles_rowmajor(frames[f]) if f < len(frames) else bytes(2048)
        assert len(data) == 14 * 2048
        blobs.append(data)
    return blobs


def resident(ea, eb):
    grid = [[bytes(32)] * 16 for _ in range(16)]
    for f, img in enumerate(ea):
        n = D.EA_NAME(f)
        for ty in range(4):
            for tx in range(4):
                grid[n // 16 + ty][n % 16 + tx] = encode_4bpp(img[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8])
    for f, img in enumerate(eb):
        n = D.EB_NAME(f)
        for ty in range(2):
            for tx in range(2):
                grid[n // 16 + ty][n % 16 + tx] = encode_4bpp(img[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8])
    return b"".join(t for row in grid for t in row)


def palettes():
    sty = json.loads((STY / "palettes.json").read_text())
    pals = [sty["p1"], sty["p2"], json.loads((CRE / "bellwretch64" / "palettes.json").read_text())["base"],
            json.loads((CRE / "thornhopper" / "palettes.json").read_text())["base"]]
    assert json.loads((CRE / "thornling" / "palettes.json").read_text())["base"] == pals[3]
    return pals


def pal_blob(pals) -> bytes:
    words = []
    for p in pals:
        words += [0] + [bgr555(c) for c in p[1:]]
    return b"".join(w.to_bytes(2, "little") for w in words)


def pad(data: bytes, size: int, what: str) -> bytes:
    if len(data) > size:
        raise SystemExit(f"gen_dgn_fight_assets: {what} is {len(data)} B, over its {size} B claim")
    return data + bytes(size - len(data))


def inc_text(T) -> str:
    L = ["; GENERATED by tools/gen_dgn_fight_assets.py: do not edit.",
         "; The score's length and record size. No addresses.",
         f"DGNF_T = {T}",
         f"DGNF_REC = {D.RECORD_BYTES}",
         f"DGNF_REC_END = {T * D.RECORD_BYTES}",
         f"DGNF_BACKDROP_BGR = {bgr555(sheets.BG_FLOOR)}"]
    return "\n".join(L) + "\n"


# ---- the preview: the SCORE drawn from the strips, in the OAM's front-to-back order ----------------------------
def render_preview(states, pals, boss, hero, ea, eb, ticks, scale=3):
    bg = np.array([(w & 31) * 255 // 31 for w in [bgr555(sheets.BG_FLOOR)]] * 3, np.uint8)
    w = bgr555(sheets.BG_FLOOR)
    bg = np.array([(w & 31) * 255 // 31, ((w >> 5) & 31) * 255 // 31, ((w >> 10) & 31) * 255 // 31], np.uint8)
    rgb = [np.array(p, np.uint8) for p in pals]
    frames = []

    def blit(canvas, img, pal, x, y, flip):
        im = img[:, ::-1] if flip else img
        h, wd = im.shape
        ys, xs = np.nonzero(im)
        for yy, xx in zip(ys, xs):
            X, Y = x + xx, y + yy
            if 0 <= X < D.SCREEN_W and 0 <= Y < D.SCREEN_H:
                canvas[Y, X] = rgb[pal][im[yy, xx]]

    for t in ticks:
        c = np.zeros((D.SCREEN_H, D.SCREEN_W, 3), np.uint8)
        c[:] = bg
        s = states["boss"][t]
        blit(c, boss[s.frame], 2, s.x - ((63 - D.BOSS_AX) if s.flip else D.BOSS_AX), s.y - D.BOSS_AY, s.flip)
        for key, arr, ax, ay, w_ in (("eb", eb, D.EB_AX, D.EB_AY, 15), ("ea", ea, D.EA_AX, D.EA_AY, 31)):
            s = states[key][t]
            blit(c, arr[s.frame % D.ENEMY_FPF], 3, s.x - ((w_ - ax) if s.flip else ax), s.y - ay, s.flip)
        for key, pal in (("p2", 1), ("p1", 0)):
            s = states[key][t]
            f = s.frame % D.HERO_FPF
            attack = f >= D.HERO_ATK0
            ax = D.HERO_ATK_AX if attack else D.HERO_AX
            wbox = 31 if attack else 15
            img = hero[s.frame]
            img = img if attack else img[:, :16]
            blit(c, img, pal, s.x - ((wbox - ax) if s.flip else ax), s.y - D.HERO_AY, s.flip)
        frames.append(Image.fromarray(c).resize((D.SCREEN_W * scale, D.SCREEN_H * scale), Image.NEAREST))
    return frames


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--mode", choices=tuple(D.MODES), default="choreo")
    ap.add_argument("--preview", type=Path)
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    states = D.all_states()
    T = len(states["boss"])
    if T * D.RECORD_BYTES > SCORE_CLAIM:
        raise SystemExit(f"gen_dgn_fight_assets: {T} ticks x {D.RECORD_BYTES} B does not fit one 32 KB bank")
    boss, hero = boss_frames(), hero_frames()
    ea, eb = enemy_frames("thornhopper", 32), enemy_frames("thornling", 16)
    pals = palettes()
    plans = {m: D.compile_stream(states, mode=m) for m in D.MODES}
    plan = plans[a.mode]
    records = [D.build_record(states, plan, t) for t in range(T)]
    cmds, ptr = D.command_bytes(plan)
    init = D.init_bytes(plan)
    ptr += (len(cmds) + len(init)).to_bytes(2, "little")      # ptr[T + 1]: the end of the entry-state rows
    cmds = cmds + init                                         # ... which are the stream's last (they start at ptr[T])
    for i, b in enumerate(boss_blobs(boss)):
        (a.out / f"dgnf_boss{i}.bin").write_bytes(b)
    (a.out / "dgnf_hero.bin").write_bytes(b"".join(tiles_rowmajor(f) for f in hero))
    (a.out / "dgnf_res.bin").write_bytes(resident(ea, eb))
    (a.out / "dgnf_pal.bin").write_bytes(pal_blob(pals))
    (a.out / "dgnf_score.bin").write_bytes(pad(b"".join(records), SCORE_CLAIM, "the score"))
    (a.out / "dgnf_cmds.bin").write_bytes(pad(cmds, CMDS_CLAIM, "the command stream"))
    (a.out / "dgnf_ptr.bin").write_bytes(pad(ptr, PTR_CLAIM, "the pointer table"))
    (a.out / "dgnf_frames.inc").write_text(inc_text(T))
    report = {"ticks": T, "mode": a.mode, **{m: D.stats(plans[m]) for m in D.MODES},
              **{f"bytes_{m}": plans[m]["bytes"] for m in D.MODES}}
    (a.out / "dgnf_report.json").write_text(json.dumps(report))
    if a.preview:
        ticks = list(range(0, T, 2))
        fr = render_preview(states, pals, boss, hero, ea, eb, ticks)
        fr[0].save(a.preview, save_all=True, append_images=fr[1:], duration=33, loop=0, optimize=False)
    print(f"gen_dgn_fight_assets[{a.mode}]: {T} ticks, score {T * D.RECORD_BYTES} B, {len(cmds)} B of commands "
          f"({len(cmds) // 6} rows), peak {plan_peak(plan)} B/tick; "
          f"choreo peak {report['choreo']['peak_bytes']} vs naive peak {report['naive']['peak_bytes']}")
    return 0


def plan_peak(plan):
    return max(plan["bytes"])


if __name__ == "__main__":
    sys.exit(main())
