"""model.py — the picture library and the budget equation for the tile-streamed giant boss (docs/dungeons/21).

The boss is a SET OF PICTURES of the Crownling (rendered looking straight down, art/dungeons/creatures/specs/
crownling_giant.toml) drawn on a BG layer, with the room's floor on another and the players as OBJs. The PPU cannot
rotate a Mode 1 layer, so a spin is a SEQUENCE OF PICTURES streamed into VRAM, and the limiter the owner asked for
is real: how many tiles of how many pictures can be loaded per frame, held in VRAM and kept in ROM.

THE EQUATION. Let a picture shown with the eye on screen at height y expose canvas rows >= 136 - y, i.e. cell rows
>= r0 = ceil((136 - y) / 8). The cells of those rows that are not blank are the tiles it must have loaded:
    T(r0)    tiles in rows >= r0                 (measured from the rendered pictures, not assumed)
    B(r0)    = 32 * T + 64 * (45 - r0)           bytes: the tiles + the tilemap rows (the cost of ONE picture)
    c(B)     = 8.4 * B + 1250 * x                master cycles of VBlank for x transfers (fitted to the console's V counter)
    C        = (V_LIMIT - V_BASE) * 1364 - R     the master cycles a tick has for the boss (R reserved for the players)
Two layers alternate (the next picture loads into the off-screen one, the swap is a TM write):
    rate(r0) = min(1, C / c(B(r0)))              pictures a tick: the two layers PIPELINE (a load overlaps the previous
                                                 picture's display, and the swap tick's own VBlank is usable), so
                                                 this is a throughput bound, not a per-picture hold
    omega    = step * rate(r0) deg/tick          the fastest sustained rotation at that depth
The ROM bound is separate and sets the STEP: a set of N pictures at depth r0 needs N * B(r0) bytes, so
    step(r0) >= 360 / floor(ROM_budget / B(r0))
Deeper pictures are bigger, so they are slower to swap AND fewer fit: the more of the crown is visible, the coarser
and slower it can spin. docs/dungeons/21 tabulates it; tests/test_dgn_tilestream_score.py checks the scheduler
agrees with it.
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
from gen_dgn_hero_assets import encode_4bpp  # noqa: E402

OUT = REPO / "art" / "dungeons" / "creatures" / "out" / "crownling_giant"
SPIN_PNG, EXT_PNG = OUT / "spin_down.png", OUT / "ext_down.png"
CW, CH = 256, 360                      # a picture: 32 x 45 cells
COLS, ROWS = 32, 45
EYE = (128, 136)                       # the crown's centre in the picture
SPIN_N, STEP = 24, 15                  # the spin pictures: k * 15 degrees clockwise
CUT = {45: 21, 90: 0, 135: 3}          # blade heading (screen degrees) -> the spin index that points there
EXT = {21: (24, 25, 26), 0: (27, 28, 29), 3: (30, 31, 32)}     # blade at 0.45 / 0.7 / 1.0 of full length
BLADE_PX = {0: 29, 1: 74, 2: 115, 3: 165}                      # the blade's reach from the eye at e0..e3 (screen px)
PAL = 2                                # BG tile palette: CGRAM 32..47 (BG3's 2bpp palettes own 0..31)

# the VBlank cost model, measured on the console (docs/dungeons/18, 19)
V_BASE = 229                           # where the NMI hook ends with nothing streamed (OAM DMA + the core)
LINE_MC = 1364                         # master cycles in a scanline
MC_PER_BYTE = 8.4                      # 8 for the DMA itself + the bus/refresh stalls it takes over a few hundred bytes
MC_PER_XFER = 1250                     # per command: the 65816 interpreter that sets one up (VMADD, A1T, DAS, A1B, the
                                       # table lookups) plus the DMA's own start-up. Least-squares over 296 frames of
                                       # the console's V counter (tests/test_dgn_colossus.py): 8.38 mc/B + 1249 mc/xfer
                                       # + 361 mc, resid <= 726 mc. docs 18-19's 680 was the simpler row player


def y_limit(r0: int) -> int:
    """The lowest the eye may be on screen while rows >= r0 are all that is loaded."""
    return EYE[1] - 8 * r0


def r0_needed(y: float) -> int:
    """The deepest-loaded row a picture MUST include when the eye is at screen height y: rows >= this are visible."""
    return int((EYE[1] - y) // 8)


def cost_mc(nbytes: int, xfers: int = 1) -> int:
    return math.ceil(MC_PER_BYTE * nbytes + MC_PER_XFER * xfers)


def cap_mc(v_limit: int = 255, reserve_mc: int = 0) -> int:
    """Master cycles a tick has: from the V_BASE the hook starts the stream at, to v_limit (261 is the cliff)."""
    return (v_limit - V_BASE) * LINE_MC - reserve_mc


def load_pictures():
    a, b = np.asarray(Image.open(SPIN_PNG)), np.asarray(Image.open(EXT_PNG))
    assert a.shape == (CH, 24 * CW) and b.shape == (CH, 9 * CW), (a.shape, b.shape)
    return [a[:, i * CW:(i + 1) * CW] for i in range(24)] + [b[:, i * CW:(i + 1) * CW] for i in range(9)]


def cells_of(img: np.ndarray) -> np.ndarray:
    return img.reshape(ROWS, 8, COLS, 8).swapaxes(1, 2)             # (45, 32, 8, 8)


def tile_bytes(cell: np.ndarray) -> bytes:
    return encode_4bpp(cell)


@dataclass
class Variant:
    """One loadable arrangement: a set of pictures sharing a slot numbering, loaded from row r0 down."""
    vid: str
    pics: list                          # picture ids sharing the slots (a cut group: the spin picture + its 3 extensions)
    r0: int
    slots: list = field(default_factory=list)       # slot i+1 -> (row, col)
    static: int = 0                     # slots 1..static never change across the group's pictures
    first_row: int = 0                  # the first row holding any cell
    last_row: int = 0                   # the last
    tiles: dict = field(default_factory=dict)       # picture id -> [32 B per slot]
    slot_of: dict = field(default_factory=dict)

    @property
    def n(self) -> int:
        return len(self.slots)

    def base_bytes(self) -> bytes:
        return b"".join(self.tiles[self.pics[0]])

    def tilemap_rows(self):
        """[(row, 32 words)] from first_row to the bottom: slot | PAL << 10, blank = 0."""
        out = []
        for r in range(self.first_row, self.last_row + 1):
            out.append((r, [(self.slot_of.get((r, c), 0)) | ((PAL << 10) if (r, c) in self.slot_of else 0) for c in range(COLS)]))
        return out

    def tilemap_bytes(self) -> bytes:
        return b"".join(w.to_bytes(2, "little") for _, row in self.tilemap_rows() for w in row)

    def load_bytes(self) -> int:
        """B(r0) for this variant: the tiles and the tilemap rows."""
        return 32 * self.n + 64 * (self.last_row - self.first_row + 1)


def build_variant(pics, vid, ids, r0, order="raster"):
    """Slots: the cells (rows >= r0) non-blank in ANY of `ids`. Static slots first (raster order), then, for a cut
    group, the cells that vary between its pictures sorted by distance from the eye, so every blade extension is
    ONE contiguous run of slots."""
    cs = [cells_of(pics[i]) for i in ids]
    cells = []
    for r in range(r0, ROWS):
        for c in range(COLS):
            if any(x[r, c].any() for x in cs):
                cells.append((r, c))
    varying = [rc for rc in cells if len({x[rc].tobytes() for x in cs}) > 1]
    static = [rc for rc in cells if rc not in set(varying)]
    if order == "cut":
        ex, ey = EYE[0] / 8, EYE[1] / 8
        varying.sort(key=lambda rc: (math.hypot(rc[1] + .5 - ex, rc[0] + .5 - ey), rc))
        cells = static + varying
    v = Variant(vid, list(ids), r0)
    v.slots = cells
    v.static = len(static) if order == "cut" else len(cells)
    v.slot_of = {rc: i + 1 for i, rc in enumerate(cells)}
    v.first_row = min((r for r, _ in cells), default=ROWS)
    v.last_row = max((r for r, _ in cells), default=ROWS - 1)
    for pid, x in zip(ids, cs):
        v.tiles[pid] = [tile_bytes(x[r, c]) for r, c in cells]
    return v


def vary_block(v: Variant, pic: int) -> bytes:
    """The tiles of `pic` in the varying slots (static+1 .. n): one contiguous block, the source of every blade patch."""
    return b"".join(v.tiles[pic][v.static:])


def ext_runs(v: Variant, a: int, b: int):
    """The slots to rewrite to go from picture a to picture b of a cut group: one contiguous run [lo, hi] (1-based
    slots) and its bytes (b's tiles). Contiguous BY CONSTRUCTION (the varying slots are ordered by distance)."""
    ta, tb = v.tiles[a], v.tiles[b]
    ch = [i for i in range(v.n) if ta[i] != tb[i]]
    if not ch:
        return None
    lo, hi = ch[0], ch[-1]
    assert lo >= v.static, "a blade patch reached into the static slots"
    return lo + 1, hi + 1, b"".join(tb[lo:hi + 1])


def library(pics=None):
    pics = pics or load_pictures()
    lib = {}
    for k in range(0, SPIN_N, 2):                                           # 30 degree steps: the readable limit (below)
        lib[f"s{k}"] = build_variant(pics, f"s{k}", [k], 24)                 # shallow: the rim (eye <= -56)
        lib[f"m{k}"] = build_variant(pics, f"m{k}", [k], 20)                 # mid: eye <= -24
    for hd, k in CUT.items():
        lib[f"c{k}"] = build_variant(pics, f"c{k}", [k, *EXT[k]], 16, order="cut")   # cut: eye <= +8, with the blade
    return lib


def depth_table(pics=None, r0s=(28, 24, 20, 16, 12)):
    """The measured cost of one spin picture at each depth r0: tiles (min/mean/max) and bytes, the tilemap counted only
    over the rows that hold anything (what the director actually sends)."""
    pics = pics or load_pictures()
    rows = []
    for r0 in r0s:
        cnt, span = [], []
        for k in range(0, SPIN_N, 2):
            c = cells_of(pics[k])[r0:].reshape(ROWS - r0, COLS, 64).any(-1)
            cnt.append(int(c.sum()))
            rr = np.nonzero(c.any(1))[0]
            span.append(int(rr.max() - rr.min() + 1) if len(rr) else 0)
        rows.append({"r0": r0, "eye_limit": y_limit(r0), "tiles_min": min(cnt), "tiles_mean": sum(cnt) / len(cnt),
                     "tiles_max": max(cnt), "map_rows": sum(span) / len(span),
                     "bytes_mean": 32 * sum(cnt) / len(cnt) + 64 * sum(span) / len(span)})
    return rows


def equation(r0_row, cap, xfers_per_picture=3, step=30, rom_budget=None):
    """The closed form for one depth. `cap` is the master cycles a tick has for the boss; `step` is the angle between
    consecutive pictures of the set (30 degrees: the readable limit).

        c         = 8.4 * bytes + 1250 * transfers       one picture's VBlank cost
        rate      = min(1, cap / c)  pictures per tick   THROUGHPUT: the two layers pipeline, so a picture's load
                                                         overlaps the previous one's display; one TM write a tick
                                                         caps it at 1 (the display bound)
        omega     = step * rate      degrees per tick    the fastest sustained rotation at this depth
        stall     = ceil(c / cap)    ticks of capacity one picture needs, the pause when nothing else is loading
                                     (the gap before a cut, whose base picture is the largest)
    """
    c = cost_mc(int(r0_row["bytes_mean"]), xfers_per_picture)
    rate = min(1.0, cap / c)
    out = {"r0": r0_row["r0"], "bytes": int(r0_row["bytes_mean"]), "cost_mc": c, "pictures_per_tick": rate,
           "deg_per_tick": step * rate, "stall_ticks": math.ceil(c / cap),
           "bound": "display (one swap a tick)" if cap >= c else "DMA (VBlank)"}
    if rom_budget:
        n = int(rom_budget // r0_row["bytes_mean"])
        out["pictures_in_rom"] = n
        out["finest_step_deg"] = 360 / n if n else None
    return out
