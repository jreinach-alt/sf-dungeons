"""dgn_ppu.py — shared readers for the dungeon rails' tests: OAM, the per-line sprite ledger, VRAM slots and colours.

Pure helpers (numpy only). Every function takes the memory it reads as an argument; nothing here touches an address.
`mesen_runner` must be imported before numpy (see tests/test_dgn_hero.py), so import this module AFTER `machine`.
"""
import numpy as np


def decode_tile(b):
    t = np.zeros((8, 8), np.uint8)
    for y in range(8):
        p = (b[2 * y], b[2 * y + 1], b[16 + 2 * y], b[16 + 2 * y + 1])
        for x in range(8):
            t[y, x] = sum(((p[k] >> (7 - x)) & 1) << k for k in range(4))
    return t


def decode_rows(raw_rows, w_tiles):
    """raw_rows: list of byte strings, one per tile row (w_tiles tiles of 32 B). -> a (rows*8, w_tiles*8) array."""
    out = np.zeros((len(raw_rows) * 8, w_tiles * 8), np.uint8)
    for r, raw in enumerate(raw_rows):
        for t in range(w_tiles):
            out[r * 8:r * 8 + 8, t * 8:t * 8 + 8] = decode_tile(raw[t * 32:t * 32 + 32])
    return out


def parse_oam(raw):
    """544 B of OAM -> [(x with X9, y, name, attr, size)] x 128."""
    out = []
    for i in range(128):
        x, y, name, attr = raw[i * 4:i * 4 + 4]
        bits = (raw[512 + i // 4] >> ((i % 4) * 2)) & 3
        out.append((x - 256 if bits & 1 else x, y, name, attr, 32 if bits & 2 else 16))
    return out


def ledger(entries):
    """(most sprites, most 8-px slivers) on any one of the 224 display lines (docs/01 OAM)."""
    sprites, slivers = [0] * 257, [0] * 257
    for x, y, _n, _a, size in entries:
        if x <= -size or x >= 256:
            continue
        cols = sum(1 for t in range(size // 8) if 0 <= x + 8 * t < 256 or 0 <= x + 8 * t + 7 < 256)
        for dy in range(size):
            line = (y + 1 + dy) % 256
            if 1 <= line <= 224:
                sprites[line] += 1
                slivers[line] += cols
    return max(sprites), max(slivers)


def rgb_of(words):
    """BGR555 words -> the 8-bit colours a screenshot shows."""
    return np.array([[(w & 31) * 255 // 31, ((w >> 5) & 31) * 255 // 31, ((w >> 10) & 31) * 255 // 31]
                     for w in words], float)
