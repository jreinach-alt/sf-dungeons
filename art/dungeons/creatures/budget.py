"""budget.py — what a set of painted frames COSTS on the console, per size class.

No Blender. An artist's frame is "done" only if its tiles fit: this counts them.

OBJ classes: tiles, OAM entries, and the sprite SLIVERS a scanline pays (34 per line
total, 02 §3). BG class (a boss on BG2, 02 §1): UNIQUE tiles per pose against the
10 KB CHR buffer, and what a pose CHANGE costs to stream: only tiles the previous
pose did not already hold need DMA, against the measured 5,952 usable bytes in one
VBlank (allocator/substrate.toml: vblank_usable_bytes).
"""
from __future__ import annotations

import numpy as np

TILE_BYTES = 32                     # 4bpp 8x8
VBLANK_BYTES = 5952                 # MEASURED, allocator/substrate.toml [dma]
BG_CHR_TILES = 320                  # 02 §1: the boss's CHR buffer, 10 KB

SIZE_CLASSES = {
    # name: (w, h, kind, OAM entries, slivers a scanline pays while it covers the line)
    "obj16":    (16, 16, "obj", 1, 2),
    "obj16x32": (16, 32, "obj", 2, 2),        # two stacked 16x16
    "obj32":    (32, 32, "obj", 1, 4),        # one large OBJ (OBSEL pair 16/32)
    "obj64":    (64, 64, "obj", 4, 8),        # FOUR 32x32 OBJs (2x2) under the 16/32 pair docs/dungeons/02 chose; 1 entry needs the 32/64 pair
                                              # (docs/dungeons/18 §2: measured on the console, same 8 slivers a line)
    "bg":       (0, 0, "bg", 0, 0),           # a boss: any size up to the 32x32 map
}


def split_tiles(frame: np.ndarray) -> list[np.ndarray]:
    h, w = frame.shape
    if h % 8 or w % 8:
        raise ValueError(f"a {w}x{h} frame is not a whole number of 8x8 tiles")
    return [frame[y:y + 8, x:x + 8] for y in range(0, h, 8) for x in range(0, w, 8)]


def tile_key(t: np.ndarray, flips: bool) -> bytes:
    """A tile's identity; with `flips` a tile and its mirrors are one tile (BG tiles
    carry H/V flip bits; OBJ tiles do not, flips there are per sprite)."""
    if not flips:
        return t.tobytes()
    return min(t.tobytes(), t[:, ::-1].tobytes(), t[::-1].tobytes(), t[::-1, ::-1].tobytes())


def unique_tiles(frame: np.ndarray, flips: bool) -> set:
    return {tile_key(t, flips) for t in split_tiles(frame) if t.any()}


def report(frames: dict, cls: str) -> dict:
    """frames: {name: 2-D index array}. Returns the budget picture for the class."""
    w, h, kind, entries, slivers = SIZE_CLASSES[cls]
    out = {"class": cls, "frames": len(frames), "per_frame": {}}
    flips = kind == "bg"
    seen: set = set()
    for name, f in frames.items():
        if kind == "obj" and f.shape != (h, w):
            raise ValueError(f"{name}: {f.shape[1]}x{f.shape[0]} is not the {w}x{h} of {cls}")
        u = unique_tiles(f, flips)
        out["per_frame"][name] = len(u)
        seen |= u
    out["unique_tiles_all"] = len(seen)
    out["rom_bytes_all"] = len(seen) * TILE_BYTES
    if kind == "obj":
        out["oam_entries_per_actor"] = entries
        out["slivers_per_line"] = slivers
        out["max_tiles_one_frame"] = max(out["per_frame"].values())
    else:
        worst = max(out["per_frame"].values())
        out["max_unique_tiles_one_pose"] = worst
        out["chr_budget_tiles"] = BG_CHR_TILES
        out["pose_fits_buffer"] = worst <= BG_CHR_TILES
        names = list(frames)
        deltas = {}
        for a, b in zip(names, names[1:] + names[:1]):          # a loop: the last returns to the first
            new = unique_tiles(frames[b], True) - unique_tiles(frames[a], True)
            deltas[f"{a}->{b}"] = len(new)
        out["new_tiles_per_transition"] = deltas
        worst_d = max(deltas.values()) if deltas else 0
        out["worst_transition_tiles"] = worst_d
        out["worst_transition_bytes"] = worst_d * TILE_BYTES
        out["vblank_frames_for_worst"] = -(-worst_d * TILE_BYTES // VBLANK_BYTES)
    return out
