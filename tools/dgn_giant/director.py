"""director.py — the giant Mode 7 boss: choreography, the matrix, the players' dodges (docs/dungeons/20).

The boss is ONE still image on the Mode 7 plane (the Crownling, 113 px across, rendered looking straight down).
Everything it does is the PPU's matrix: rotation and magnification in M7A-M7D, the slide in the scroll, the pivot
in M7X/M7Y. That costs no CHR streaming at all, which is why a boss the whole width of the screen, spun as fast
as we like, is a few register writes a frame.

The scene is a SCORE, like dgn_fight's: 33 bytes a tick = the OAM entries of the two players (they ARE streamed:
the same back-buffer scheduler) + their hi byte + the 16-byte Mode 7 shadow. This module is pure Python; the
numpy reference renderer at the bottom is what the tests compare the ROM's picture with.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
from dgn_fight import director as DF  # noqa: E402

# ---------------------------------------------------------------------------------------------------------------
# The plane and the matrix
# ---------------------------------------------------------------------------------------------------------------
SCALE = 2.25                    # screen px per plane px: a 113 px crown spans the 256 px screen
X0 = Y0 = 512                   # the pivot: the middle of the 1024x1024 plane
IMG_W, IMG_H = 128, 192         # the crown image
IMG_AX, IMG_AY = 64, 64         # the crown's centre (the eye) inside it
IMG_ORIGIN = (X0 - IMG_AX, Y0 - IMG_AY)
BLADE_PX = 111                  # the painted blade: from the eye to its tip, plane px
BLADE_LEN = BLADE_PX * SCALE    # ... on screen
BLADE_HALF_W = 18               # the lethal half-width on screen (the painted blade is ~18 px wide, x2.25)
SCREEN_W, SCREEN_H = 256, 224
SLICE_ANGLES = (45, 90, 135)    # the three cuts, degrees from the screen's +x axis, clockwise (90 = straight down)


def s16(v: int) -> int:
    return v & 0xFFFF


def matrix_words(phi_deg: float, sx0: int, sy0: int):
    """(A, B, C, D, X0, Y0, HOFS, VOFS) for the image turned CLOCKWISE by phi on the screen, its centre at the
    screen point (sx0, sy0). The PPU maps a screen point to the plane as
        X = A*(sx + HOFS - X0) + B*(sy + VOFS - Y0) + X0     Y = C*(...) + D*(...) + Y0
    so with HOFS = X0 - sx0 and VOFS = Y0 - sy0 the pivot lands on (sx0, sy0), and A = D = cos/SCALE,
    B = -C = sin/SCALE (8.8 fixed point) rotates the image clockwise by phi."""
    p = math.radians(phi_deg)
    a = round(256 * math.cos(p) / SCALE)
    b = round(256 * math.sin(p) / SCALE)
    return (s16(a), s16(b), s16(-b), s16(a), X0, Y0, (X0 - sx0) & 0x1FFF, (Y0 - sy0) & 0x1FFF)


def pack_m7(words) -> bytes:
    return b"".join(w.to_bytes(2, "little") for w in words)


# ---------------------------------------------------------------------------------------------------------------
# The boss's pre-programmed sequence. Eased keyframes: position and cumulative rotation.
# ---------------------------------------------------------------------------------------------------------------
REST = (128, -78)               # the eye at rest: the crown is mostly above the screen
LUNGE = 130                     # px the eye travels along the blade on a cut
CUT = 34                        # ticks of a cut: lunge 14, hold 4, withdraw 16
LUNGE_T, HOLD_T, WITHDRAW_T = 14, 4, 16
# the eye's position when it locks for each cut (swung to one side so the blade crosses the whole screen)
E_START = {45: (30, -62), 90: (128, -70), 135: (226, -62)}
# (tick the cut begins, angle): the legs between cuts are the spin
CUT_AT = {45: 60, 90: 134, 135: 208}
LEG = 40                        # ticks of each spin leg
LOOP = 290
TURNS = {"spin_up": 3, "leg": 3, "retract": 1}    # whole turns added to each spin (the speed)


def smooth(u: float) -> float:
    return u * u * (3 - 2 * u)


def _eval(wps, t):
    """Piecewise smoothstep through (tick, value...) waypoints; velocity is zero at each, which is what a lock is."""
    for (t0, *v0), (t1, *v1) in zip(wps, wps[1:]):
        if t0 <= t <= t1:
            u = smooth((t - t0) / (t1 - t0)) if t1 > t0 else 1.0
            return [a + (b - a) * u for a, b in zip(v0, v1)]
    return list(wps[-1][1:])


def heading_phi(alpha: int) -> int:
    """The image rotation (clockwise) at which the blade points along screen angle alpha: the painted blade points
    straight down (screen angle 90), so phi = alpha - 90."""
    return alpha - 90


def boss_waypoints():
    """([(tick, phi cumulative)], [(tick, x, y)])."""
    phi, pos = [(0, 180.0), (20, 180.0)], [(0, *REST), (20, *REST)]
    cur_phi = 180.0
    prev_t = 20
    for k, alpha in enumerate(SLICE_ANGLES):
        t_cut = CUT_AT[alpha]
        # the spin leg: end on the heading, an integer number of turns on
        target = heading_phi(alpha) % 360
        turns = TURNS["spin_up"] if k == 0 else TURNS["leg"]
        end = cur_phi + 360.0 * turns
        end += (target - end) % 360.0
        ex, ey = E_START[alpha]
        phi += [(t_cut, end)]
        pos += [(t_cut, ex, ey)]
        cur_phi = end
        # the cut: phi locked; the eye lunges along the blade, holds, withdraws
        ux, uy = math.cos(math.radians(alpha)), math.sin(math.radians(alpha))
        phi += [(t_cut + CUT, end)]
        pos += [(t_cut + LUNGE_T, ex + LUNGE * ux, ey + LUNGE * uy), (t_cut + LUNGE_T + HOLD_T, ex + LUNGE * ux, ey + LUNGE * uy),
                (t_cut + CUT, ex, ey)]
        prev_t = t_cut + CUT
    # retract: spin out and slide home, ending on the rest heading (180 mod 360)
    end = cur_phi + 360.0 * TURNS["retract"]
    end += (180.0 - end) % 360.0
    phi += [(LOOP, end)]
    pos += [(LOOP, *REST)]
    return phi, pos


def boss_state(t: int):
    """(phi degrees, sx0, sy0) at tick t. Inside a cut the lunge and withdraw ease on their own sub-segments."""
    phi_w, pos_w = boss_waypoints()
    phi = _eval(phi_w, t)[0]
    # position: the cut's lunge/hold/withdraw are separate eased segments; the waypoints already encode them
    x, y = _eval(pos_w, t)
    return phi, round(x), round(y)


def boss_states():
    return [boss_state(t) for t in range(LOOP)]


def blade(t: int):
    """(eye x, eye y, unit direction (ux, uy)) of the blade at tick t, in screen px."""
    phi, x, y = boss_state(t)
    a = math.radians(90 + phi)
    return x, y, (math.cos(a), math.sin(a))


def cut_window(alpha: int):
    t0 = CUT_AT[alpha]
    return t0, t0 + CUT


def blade_reach(t: int):
    """How far along the blade (px from the eye) is lethal: the whole blade, because the eye carries it."""
    return BLADE_LEN


def dist_to_blade(px, py, t):
    ex, ey, (ux, uy) = blade(t)
    dx, dy = px - ex, py - ey
    along = dx * ux + dy * uy
    perp = abs(dx * uy - dy * ux)
    return along, perp


def in_blade(px, py, t, margin=0):
    along, perp = dist_to_blade(px, py, t)
    return -10 <= along <= BLADE_LEN and perp < BLADE_HALF_W + margin


# ---------------------------------------------------------------------------------------------------------------
# The players: stations in the corridors, dodges perpendicular to the blade, then home
# ---------------------------------------------------------------------------------------------------------------
HOME = {"p1": (52, 204), "p2": (204, 204)}
STATION = {  # the corridor of each cut, where a player is when the eye lunges (just outside the blade's reach)
    45: {"p2": (217, 125)},
    90: {"p1": (118, 196), "p2": (140, 172)},
    135: {"p1": (46, 118)},
}
DODGE_PX = 32
DODGE_T = 12                    # ticks to clear the corridor, finishing as the cut begins


def _unit(alpha):
    return math.cos(math.radians(alpha)), math.sin(math.radians(alpha))


def dodge_target(alpha, who, station):
    ux, uy = _unit(alpha)
    n = (-uy, ux)                                  # one perpendicular
    cand = [(station[0] + s * DODGE_PX * n[0], station[1] + s * DODGE_PX * n[1]) for s in (1, -1)]
    cand = [c for c in cand if 20 <= c[0] <= 236 and 40 <= c[1] <= 210]
    other = STATION[alpha].get("p1" if who == "p2" else "p2")
    if other:                                      # two players in one corridor go opposite ways
        cand.sort(key=lambda c: -math.hypot(c[0] - other[0], c[1] - other[1]))
    else:                                          # alone: dodge down and away from the boss, not up into it
        cand.sort(key=lambda c: -c[1])
    return tuple(round(v) for v in cand[0])


def waypoints_for(who):
    """[(tick, x, y)] for one player, the loop closed at HOME."""
    w = [(0, *HOME[who])]
    for alpha in SLICE_ANGLES:
        t_cut, _ = cut_window(alpha)
        st = STATION[alpha].get(who)
        if st:
            w.append((t_cut - DODGE_T - 2, *st))                       # on station, in the corridor
            w.append((t_cut - 2, *dodge_target(alpha, who, st)))       # cleared of the corridor, and free to go
    w.append((LOOP, *HOME[who]))
    return w


def _station_leg_start(who):
    """The player walks to its next station early enough to stay under the jog speed."""
    return None


def player_segments(who):
    wps = waypoints_for(who)
    # insert the walk-in to each station: leave the previous point as late as the speed limit allows
    segs, pos, t = [], wps[0][1:], 0
    for (t1, x1, y1) in wps[1:]:
        dist = math.hypot(x1 - pos[0], y1 - pos[1])
        ticks = t1 - t
        if ticks <= 0:
            continue
        dodging = ticks <= DODGE_T + 1
        speed = dist / ticks
        if dist < 0.5:
            segs.append(DF.Seg("idle", ticks, None, "down"))
        else:
            # leave as late as a walk allows (1.4 px/tick), idling first, unless the leg needs more
            walk_speed = 1.4 if not dodging else speed
            walk_ticks = min(ticks, max(1, math.ceil(dist / walk_speed)))
            if walk_ticks < ticks:
                segs.append(DF.Seg("idle", ticks - walk_ticks, None, _face(pos, (x1, y1))))
            scale = 0.55 if (dodging or dist / walk_ticks > 1.8) else 1.0
            segs.append(DF.Seg("walk", walk_ticks, (x1, y1), _face(pos, (x1, y1)), scale))
        pos, t = (x1, y1), t1
    return segs


def _face(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    if abs(dx) > abs(dy) * 0.8:
        return "right" if dx > 0 else "left"
    return "down"


def player_states(who):
    segs = player_segments(who)
    total = sum(s.ticks for s in segs)
    assert total == LOOP, (who, total)
    return DF.render_track(who, segs, HOME[who], "down")


def all_states():
    return {"p1": player_states("p1"), "p2": player_states("p2")}


# ---------------------------------------------------------------------------------------------------------------
# The streamed players: the SAME scheduler, a two-actor layout
# ---------------------------------------------------------------------------------------------------------------
SLOTS = {
    "p1": {"bufs": [(0, 0), (4, 0)], "rows": 4, "row_bytes": 128, "frame_bytes": 512},
    "p2": {"bufs": [(8, 0), (12, 0)], "rows": 4, "row_bytes": 128, "frame_bytes": 512},
}


def vmadd_of(actor, buf, row):
    col, r0 = SLOTS[actor]["bufs"][buf]
    return ((r0 + row) * 16 + col) * 16


def src_of(actor, frame, row):
    return 0, frame * 512 + row * 128          # blob id 0: the players' frame store


LAYOUT = DF.Layout(SLOTS, vmadd_of, src_of)


def name_of(actor, buf):
    col, row = SLOTS[actor]["bufs"][buf]
    return row * 16 + col


# ---------------------------------------------------------------------------------------------------------------
# The record: 4 OAM entries + 1 hi byte + the 16-byte Mode 7 shadow = 33 bytes a tick
# ---------------------------------------------------------------------------------------------------------------
RECORD_BYTES = 4 * 4 + 1 + 16
PARK_Y = 240


def build_record(states, plan, t):
    ent = [[0, PARK_Y, 0, 0] for _ in range(4)]
    for slot0, who in ((0, "p1"), (2, "p2")):
        s = states[who][t]
        name = name_of(who, plan["bufsel"][who][t])
        attr = DF.ATTR[who] | (DF.HFLIP if s.flip else 0)
        fr = s.frame % DF.HERO_FPF
        assert fr < DF.HERO_ATK0, "the players only walk and idle in this scene"
        x = s.x - ((15 - DF.HERO_AX) if s.flip else DF.HERO_AX)
        y = s.y - (DF.HERO_AY + 1)
        assert 0 <= x <= 240 and 0 <= y <= 224, (who, t, x, y)
        ent[slot0] = [x, y, name, attr]
        ent[slot0 + 1] = [x, y + 16, name + 32, attr]
    rec = bytearray()
    for e in ent:
        rec += bytes(v & 255 for v in e)
    rec += bytes((0,))                                     # hi byte: four small, X9 clear
    phi, sx0, sy0 = boss_state(t)
    rec += pack_m7(matrix_words(phi, sx0, sy0))
    assert len(rec) == RECORD_BYTES
    return bytes(rec)


def compile_all(mode="choreo"):
    states = all_states()
    plan = DF.compile_stream(states, mode=mode, layout=LAYOUT)
    return states, plan, [build_record(states, plan, t) for t in range(LOOP)]


# ---------------------------------------------------------------------------------------------------------------
# The reference Mode 7 renderer: what the PPU computes, in numpy (lazy import: the choreography needs none)
# ---------------------------------------------------------------------------------------------------------------
def plane_from_image(img):
    """The 1024x1024 index plane with the crown image at IMG_ORIGIN (index 0 = transparent)."""
    import numpy as np
    plane = np.zeros((1024, 1024), np.uint8)
    ox, oy = IMG_ORIGIN
    plane[oy:oy + IMG_H, ox:ox + IMG_W] = img
    return plane


def render_m7(plane, words, line0=1):
    """(224, 256) palette indices of what the PPU draws for matrix `words` (A,B,C,D,X0,Y0,HOFS,VOFS as stored).

    The hardware is NOT the naive formula. Per scanline it forms an origin from products of the matrix with the
    scroll-minus-pivot offsets, each CLIPPED to 10 bits and with the low 6 bits of every product DROPPED
    (`& ~63`), then steps A and C across the line; the plane wraps at 1024. The 6 dropped bits are a quarter
    pixel of positional noise that depends on the matrix, which is why a rotating plane shimmers. `line0` is the
    scanline number of the first row (1: the PPU's lines run 1..224)."""
    import numpy as np

    def sgn16(v):
        return v - 0x10000 if v & 0x8000 else v

    def sgn13(v):
        v &= 0x1FFF
        return v - 0x2000 if v & 0x1000 else v

    def clip(n):                                   # 13-bit signed -> 10-bit signed, as the PPU does
        return (n | ~1023) if n & 0x2000 else (n & 1023)

    A, B, C, Dm = (sgn16(w) for w in words[:4])
    x0, y0, hofs, vofs = (sgn13(w) for w in words[4:8])
    ho, vo = clip(hofs - x0), clip(vofs - y0)
    sx = np.arange(SCREEN_W)
    out = np.zeros((SCREEN_H, SCREEN_W), np.uint8)
    for row in range(SCREEN_H):
        y = row + line0
        ox = ((A * ho) & ~63) + ((B * vo) & ~63) + ((B * y) & ~63) + (x0 << 8)
        oy = ((C * ho) & ~63) + ((Dm * vo) & ~63) + ((Dm * y) & ~63) + (y0 << 8)
        px = ((ox + A * sx) >> 8) & 1023
        py = ((oy + C * sx) >> 8) & 1023
        out[row] = plane[py, px]
    return out


def decode_m7_words(rec: bytes):
    return [int.from_bytes(rec[17 + 2 * i:19 + 2 * i], "little") for i in range(8)]
