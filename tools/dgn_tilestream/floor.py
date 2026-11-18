"""floor.py — the room's floor on BG3 (2bpp, four colours): a moss pattern, deterministic, 8 tiles and a 32x32 map.

A placeholder for the Hollow Wood room (the point of the scene is that a BG layer exists for it, not the art). The
colour indices are 0 (the backdrop: the darkest moss) and 1-3 (three moss tones)."""
from __future__ import annotations

import numpy as np

N_TILES = 8
FLOOR_RGB = [(34, 48, 30), (46, 66, 38), (58, 82, 46), (74, 98, 56)]       # index 0 is also CGRAM word 0, the backdrop


def _h(*v) -> int:
    x = 2166136261
    for a in v:
        x = ((x ^ (a & 0xFFFFFFFF)) * 16777619) & 0xFFFFFFFF
    return x


def tiles() -> np.ndarray:
    """(8, 8, 8) indices 0..3: mostly index 1, flecks of 2, a little 3 and 0."""
    out = np.zeros((N_TILES, 8, 8), np.uint8)
    for t in range(N_TILES):
        for y in range(8):
            for x in range(8):
                h = _h(t, y, x) % 100
                out[t, y, x] = 0 if h < 8 else 2 if h < 30 else 3 if h < 36 else 1
    return out


def tilemap() -> np.ndarray:
    return np.array([[_h(r, c, 7) % N_TILES for c in range(32)] for r in range(32)], np.uint8)


def image() -> np.ndarray:
    """The floor as the screen shows it (256 x 256 indices) at scroll (0, 0)."""
    t, m = tiles(), tilemap()
    img = np.zeros((256, 256), np.uint8)
    for r in range(32):
        for c in range(32):
            img[r * 8:r * 8 + 8, c * 8:c * 8 + 8] = t[m[r, c]]
    return img


def encode_2bpp(tile: np.ndarray) -> bytes:
    out = bytearray()
    for row in tile:
        p0 = sum(((int(v) >> 0) & 1) << (7 - x) for x, v in enumerate(row))
        p1 = sum(((int(v) >> 1) & 1) << (7 - x) for x, v in enumerate(row))
        out += bytes((p0, p1))
    return bytes(out)


def blob() -> bytes:
    """128 B of 2bpp tiles, then the 32x32 map (2,048 B): palette 0, priority 0, tile numbers 0..7."""
    return b"".join(encode_2bpp(t) for t in tiles()) + b"".join(int(v).to_bytes(2, "little") for v in tilemap().flatten())
