"""room.py — a MOCK Hollow Wood room, to judge the wanderer against scenery and an enemy.

    python3 art/dungeons/style/room.py          # writes out/room_base.png (256x224)

A mock, not shipped art (the tile pipeline is 11 §5 stage 4): enough painted
Hollow Wood — colossal root walls with a lit top bevel, a hollow-log doorway,
a moss-and-bark floor with leaf litter, two fungus braziers throwing amber
light, a Rootling — to ask the questions the art direction asks: does the
hero read against it, stay distinct from the enemy and the scenery, and feel
like it lives here. 10 §3's anchors: moss green, bark umber, amber glow; 10 §2:
desaturated mid-tones carry the screen, saturated colour is spent on what
matters (the lights, the hero).

BG palette: <= 15 colours + the void, as one BG palette would hold (asserted).
Deterministic: a fixed-seed generator, no clock.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
W, H = 256, 224

# BG palette (BGR555-exact via snes()): index -> hex
PAL = {
    0: "#0b0a10",                                              # the void
    1: "#1d2a1c", 2: "#2c3f24", 3: "#42592f", 4: "#62773c",   # moss, dark -> light
    5: "#241913", 6: "#3a281c", 7: "#58402a", 8: "#7c5b3a", 9: "#a98558",   # bark umber
    10: "#d98a2e", 11: "#f6c765",                              # amber glow, pale amber
    12: "#7a8f8a",                                             # stone / lichen
    13: "#2f5c58",                                             # fungus teal
    14: "#171d2a",                                             # cold shadow
}


def snes(h):
    h = h.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) >> 3 for i in (0, 2, 4))
    return (r << 3 | r >> 2, g << 3 | g >> 2, b << 3 | b >> 2)


def noise(rng, h, w, cell):
    """Coarse value noise, upscaled and smoothed: blobs, not salt and pepper."""
    gh, gw = h // cell + 3, w // cell + 3
    g = rng.random((gh, gw))
    out = np.zeros((h, w))
    ys, xs = np.mgrid[0:h, 0:w]
    fy, fx = ys / cell, xs / cell
    iy, ix = fy.astype(int), fx.astype(int)
    ty, tx = fy - iy, fx - ix
    ty, tx = ty * ty * (3 - 2 * ty), tx * tx * (3 - 2 * tx)
    a, b = g[iy, ix], g[iy, ix + 1]
    c, d = g[iy + 1, ix], g[iy + 1, ix + 1]
    return (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty


def nb4(a, fill=-1):
    p = np.pad(a, 1, mode="constant", constant_values=fill)
    return np.stack([p[:-2, 1:-1], p[2:, 1:-1], p[1:-1, :-2], p[1:-1, 2:]], 0)


def tidy(idx, rounds=2):
    """Fold orphans (agree with none of 4 neighbours) into the surrounding index."""
    for _ in range(rounds):
        n = nb4(idx)
        agree = (n == idx).sum(0)
        vals = np.sort(n, axis=0)
        mode = vals[1]                     # a stable pick among the four
        idx = np.where(agree == 0, mode, idx)
    return idx


def paint_room(seed=7):
    rng = np.random.default_rng(seed)
    idx = np.zeros((H, W), np.uint8)                     # 0 = void
    ys, xs = np.mgrid[0:H, 0:W]
    FX0, FX1, FY0, FY1 = 24, 232, 84, 196               # floor rectangle
    WY0 = 36                                             # top of the back wall
    # ---- floor: moss over bark dust, in clusters ---------------------------------
    n1, n2 = noise(rng, H, W, 14), noise(rng, H, W, 6)
    f = 0.7 * n1 + 0.3 * n2
    floor = np.digitize(f, [0.40, 0.50, 0.60, 0.70])     # a quiet floor: 2 / 3 / 4, bark dust rare
    base = np.array([2, 2, 3, 3, 4])[floor]
    dust = (noise(rng, H, W, 5) > 0.86) & (n1 < 0.42)
    base = np.where(dust, 6, base)
    fm = (xs >= FX0) & (xs < FX1) & (ys >= FY0) & (ys < FY1)
    idx[fm] = base[fm]
    # leaf litter: little amber clusters
    for _ in range(30):
        x, y = int(rng.integers(FX0 + 2, FX1 - 4)), int(rng.integers(FY0 + 2, FY1 - 3))
        idx[y, x:x + 2] = 8
        if rng.random() < 0.5:
            idx[y + 1, x] = 7
    # stones
    for _ in range(9):
        x, y = int(rng.integers(FX0 + 4, FX1 - 8)), int(rng.integers(FY0 + 4, FY1 - 6))
        idx[y:y + 3, x:x + 4] = 12
        idx[y, x:x + 4] = 9
        idx[y + 2, x:x + 4] = 14
    idx = np.where(fm, tidy(idx), idx)
    # ---- back wall: colossal roots -------------------------------------------------
    wall = (xs >= FX0 - 16) & (xs < FX1 + 16) & (ys >= WY0) & (ys < FY0)
    idx[wall] = 14                                       # the dark gap between roots
    # amber glow beyond the roots, low in the gaps
    glow = wall & (ys > WY0 + 18) & (noise(rng, H, W, 9) > 0.5)
    idx[glow] = 5
    cols = [(34, 20), (62, 26), (96, 18), (128, 30), (166, 22), (198, 26), (226, 18)]
    for k, (cx, w0) in enumerate(cols):
        sway = noise(rng, 1, H, 18)[0] * 8 - 4
        for y in range(WY0, FY0 + 6):
            t = (y - WY0) / (FY0 + 6 - WY0)
            half = (w0 / 2) * (0.8 + 0.5 * t ** 2)       # roots flare toward the floor
            c = cx + sway[y] * (1 - t * 0.4)
            x0, x1 = int(round(c - half)), int(round(c + half))
            for x in range(max(x0, 0), min(x1, W)):
                u = (x - x0) / max(x1 - x0, 1)          # 0 = lit left edge, 1 = shadow right
                tex = noise(rng, 1, 1, 1)[0, 0]         # placeholder keeps rng stream stable
                v = 8 if u < 0.16 else 7 if u < 0.46 else 6 if u < 0.78 else 5
                if u < 0.06:
                    v = 9
                idx[y, x] = v
        # bark streaks: darker vertical grooves, in clusters
        for _ in range(6):
            gx = int(cx + (rng.random() - 0.5) * w0 * 0.7)
            gy = int(rng.integers(WY0 + 2, FY0 - 8))
            ln = int(rng.integers(5, 14))
            for y in range(gy, min(gy + ln, FY0)):
                if idx[y, gx] in (6, 7, 8):
                    idx[y, gx] = idx[y, gx] - 1
    # the hollow-log doorway in the middle: an arch with amber light inside
    dx0, dx1, dy0 = 112, 144, 48
    for y in range(dy0, FY0 + 4):
        for x in range(dx0, dx1):
            r = ((x - 128) / 16.0) ** 2 + (max(0, dy0 + 14 - y) / 14.0) ** 2
            if r <= 1.0:
                glow_t = (y - dy0) / (FY0 - dy0)
                dither = (x + y) % 2 == 0
                idx[y, x] = (10 if glow_t > 0.86 else (10 if dither else 8) if glow_t > 0.62
                             else (8 if dither else 6) if glow_t > 0.36 else (6 if dither else 5))
    for x in range(dx0 - 3, dx1 + 3):                    # the log's lit rim
        for y in range(dy0 - 2, FY0 + 4):
            r = ((x - 128) / 19.0) ** 2 + (max(0, dy0 + 12 - y) / 16.0) ** 2
            if 1.0 < r <= 1.35 and idx[y, x] != 0:
                idx[y, x] = 9 if x < 128 else 6
    # the lit top bevel where wall meets floor
    idx[FY0 - 1, FX0 - 16:FX1 + 16] = 9
    idx[FY0, FX0:FX1] = 8
    # ---- side root pillars -----------------------------------------------------------
    for (a, b) in ((0, 22), (234, 256)):
        for y in range(WY0 - 8, FY1 + 6):
            for x in range(a, b):
                u = (x - a) / (b - a)
                v = 9 if u < 0.1 else 8 if u < 0.3 else 7 if u < 0.62 else 6 if u < 0.85 else 5
                if a == 234:
                    v = 8 if u < 0.15 else 7 if u < 0.5 else 6 if u < 0.8 else 5
                idx[y, x] = v
    # ---- cold foot of the room: fall to the void -----------------------------------------
    idx[FY1:FY1 + 2, FX0:FX1] = 14
    return idx


def brazier(idx, cx, cy):
    """A fungus brazier: a stalk, a cap, an amber glow, and a dithered light pool."""
    h, w = idx.shape
    pool = [(dx, dy) for dy in range(-13, 14) for dx in range(-26, 27)
            if (dx / 26.0) ** 2 + (dy / 12.0) ** 2 <= 1.0]
    for dx, dy in pool:
        x, y = cx + dx, cy + 8 + dy
        d = (dx / 26.0) ** 2 + (dy / 12.0) ** 2
        if 0 <= x < w and 0 <= y < h and idx[y, x] in (2, 3, 4, 5, 6, 7):
            if d < 0.35 or (d < 0.8 and (x + y) % 2 == 0):
                idx[y, x] = {2: 4, 3: 4, 4: 9, 5: 7, 6: 8, 7: 9}[int(idx[y, x])]
    stalk = [(0, 6), (0, 7), (0, 8), (-1, 8), (1, 8), (0, 5)]
    for dx, dy in stalk:
        idx[cy + dy, cx + dx] = 7
    cap = ["..ooooo..", ".ommmmmo.", "ommeeemmo", "ommefemmo", ".ommmmmo.", "..ooooo.."]
    for r, row in enumerate(cap):
        for c, ch in enumerate(row):
            x, y = cx - 4 + c, cy - 2 + r
            idx[y, x] = {".": idx[y, x], "o": 5, "m": 13, "e": 10, "f": 11}[ch]
    idx[cy + 4, cx - 3:cx + 4] = 5


def rootling(idx, ox, oy):
    """A Rootling mock (10 §5): a knot of animated root, one ember eye, a branch-arm.
    Procedural silhouette (lumpy body, tendril legs, a raised branch), shaded from
    the upper left like the hero, one-pixel bark-dark outline, ember eye."""
    w, h = 20, 24
    m = np.zeros((h, w), bool)
    body_c, body_r = (10, 11), (7.2, 8.4)
    for y in range(h):
        for x in range(w):
            d = ((x - body_c[0]) / body_r[0]) ** 2 + ((y - body_c[1]) / body_r[1]) ** 2
            lump = 0.18 * np.sin(x * 1.7 + y * 0.9) + 0.12 * np.sin(y * 2.3 - x * 0.6)
            m[y, x] = d + lump < 1.0
    for lx, ph in ((5, 0.0), (10, 0.7), (15, 1.4)):                    # tendril legs
        for y in range(17, 24):
            c = lx + 1.6 * np.sin(y * 0.9 + ph) * (y - 16) / 7
            for x in range(int(c) - 1, int(c) + 1):
                if 0 <= x < w:
                    m[y, x] = True
    for t in np.linspace(0, 1, 40):                                    # the branch-arm
        x, y = 15 + 4 * t, 10 - 11 * t + 2 * np.sin(t * 6)
        for dx in (0, 1):
            xx, yy = int(x) + dx, int(y)
            if 0 <= xx < w and 0 <= yy < h:
                m[yy, xx] = True
    for fx, fy in ((17, -1), (19, 1)):                                  # twig fingers
        pass
    shade = np.zeros((h, w), int)
    yy, xx = np.mgrid[0:h, 0:w]
    lit = 1.0 - (xx - 3) * 0.045 - (yy - 2) * 0.03
    lit += 0.18 * np.sin(xx * 1.1 + yy * 0.5)
    shade = np.digitize(lit, [0.22, 0.42, 0.60])            # 0..3 -> bark 7..9 + the lit edge
    out = np.where(m, np.array([5, 6, 7, 12])[shade], 0)
    out = np.where(m & (lit > 0.82), 12, out)               # a cold lichen-lit edge: the warm is spent on the eye
    ring = ~m & (nb4(m, False).any(0))
    out = np.where(ring, 5, out)
    out[7:9, 4:6] = 5                                        # the socket
    out[8:10, 5:8] = 10                                      # the ember eye: a 3x2 ember
    out[8, 6] = 11
    for y in range(h):
        for x in range(w):
            if out[y, x] and 0 <= oy + y < idx.shape[0] and 0 <= ox + x < idx.shape[1]:
                idx[oy + y, ox + x] = out[y, x]


def build():
    idx = paint_room()
    brazier(idx, 44, 118)
    brazier(idx, 212, 118)
    rootling(idx, 176, 140)
    assert len(set(np.unique(idx).tolist())) <= 15, "the BG palette holds 15 colours"
    return idx


def to_rgb(idx):
    lut = np.array([snes(PAL[i]) for i in range(len(PAL))], np.uint8)
    return lut[idx]


if __name__ == "__main__":
    out = HERE / "out"
    out.mkdir(exist_ok=True)
    idx = build()
    np.save(out / "room_base.npy", idx)
    Image.fromarray(to_rgb(idx)).save(out / "room_base.png")
    print("room:", out / "room_base.png", "colours:", len(set(np.unique(idx).tolist())))
