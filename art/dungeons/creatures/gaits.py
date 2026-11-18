"""gaits.py — locomotion as DATA: foot paths and leg phases for any number of legs.

No Blender here (so it is unit-tested). A creature's `gait` action names a leg set
and gives a handful of numbers; this module turns them into one foot target per leg
per frame, which creature.py keys onto the IK targets. A spider's 8-leg skitter, a
tortoise's 4-leg plod and a hero's 2-leg walk are the SAME function with different
phases, strides and lifts. That is what lets a new creature cost a data file and
not a week of keying.

Convention (the model's, kit.py's): the creature FACES -Y and walks toward -Y; z is
up. A foot on the ground is fixed in the WORLD, so relative to the body it slides
toward +Y during stance; it swings back toward -Y through the air.
"""
from __future__ import annotations

import math

# ---- leg phases (fractions of a cycle) ---------------------------------------------
# A leg set is ordered as the spec lists it; `side` pairs are (left, right) per rank,
# front to back. These patterns are the ones real animals use.
PHASES = {
    # 8 legs: alternating tetrapod: legs 1,4 of one side and 2,3 of the other swing together
    "tetrapod": lambda n: _tetrapod(n),
    # 4 legs, listed FL, FR, HL, HR. The walk is a lateral sequence: FL, HR, FR, HL, a quarter
    # cycle apart, so a hind foot follows the FRONT foot of the other side (never the same side)
    "walk4": lambda n: [0.0, 0.5, 0.75, 0.25] if n == 4 else _bad(n, 4),
    # 4 legs: the trot: diagonal pairs together (FL + HR, FR + HL)
    "trot4": lambda n: [0.0, 0.5, 0.5, 0.0] if n == 4 else _bad(n, 4),
    # 2 legs: a biped walk
    "biped": lambda n: [0.0, 0.5][:n] if n == 2 else _bad(n, 2),
}


def _bad(n, want):
    raise ValueError(f"this gait needs {want} legs, the leg set has {n}")


def _tetrapod(n):
    # legs listed L1,R1,L2,R2,...: rank r, side s: phase 0 when (r + s) is even, else 0.5
    return [0.0 if (i // 2 + i % 2) % 2 == 0 else 0.5 for i in range(n)]


def leg_phases(kind: str, n_legs: int) -> list[float]:
    if kind not in PHASES:
        raise ValueError(f"unknown gait {kind!r}; known: {sorted(PHASES)}")
    return PHASES[kind](n_legs)


# ---- one foot ------------------------------------------------------------------------
def foot_offset(t: float, stride: float, lift: float, duty: float) -> tuple[float, float]:
    """(dy, dz) of a foot relative to its HOME, at gait time t (any real; wraps).

    Stance (t < duty): on the ground, sliding from the front of the stride to the
    back at constant speed. Swing: through the air, back to the front, on a sine
    arc whose peak is `lift`. Continuous at both seams, so a loop closes exactly.
    """
    t %= 1.0
    if t < duty:
        s = t / duty
        return (-stride / 2 + stride * s, 0.0)
    s = (t - duty) / (1.0 - duty)
    return (stride / 2 - stride * s, lift * math.sin(math.pi * s))


def gait_frames(n_frames: int, phases: list[float], stride: float, lift: float,
                duty: float = 0.6, bob: float = 0.0, steps: int = 1) -> dict:
    """Foot offsets for every leg at every frame of one loop.

    `steps` cycles per loop (a 4-frame loop with steps=1 is one full stride pair).
    Returns {"feet": [[(dx, dy, dz) per frame] per leg], "body_z": [dz per frame]}.
    The body bobs twice per cycle (two groups alternate), lowest at mid-stance.
    """
    feet = []
    for ph in phases:
        row = []
        for i in range(n_frames):
            t = steps * i / n_frames + ph
            dy, dz = foot_offset(t, stride, lift, duty)
            row.append((0.0, dy, dz))
        feet.append(row)
    body = [bob * math.cos(4 * math.pi * steps * i / n_frames) for i in range(n_frames)]
    return {"feet": feet, "body_z": body}


# ---- poses: planted feet --------------------------------------------------------------
def resolve_feet(frames: list[dict], homes: dict) -> list[dict]:
    """Turn a pose list's foot instructions into absolute foot targets.

    Each frame maps a leg name to one of:
        "plant"        stay where the leg was last frame (it is on the ground, FIXED
                       in the world: this is what stops a foot sliding while the body
                       pitches over it)
        "home"         the leg's rest position
        [x, y, z]      an absolute model-space position
        {"home": [dx, dy, dz]}   the rest position plus an offset (a lifted foot)
    The first frame must not say "plant" for a leg that has no earlier position.
    """
    out, last = [], {k: tuple(v) for k, v in homes.items()}
    for n, fr in enumerate(frames):
        cur = {}
        for leg, home in homes.items():
            ins = fr.get(leg, "plant" if n else "home")
            if ins == "plant":
                cur[leg] = last[leg]
            elif ins == "home":
                cur[leg] = tuple(home)
            elif isinstance(ins, dict) and "home" in ins:
                cur[leg] = tuple(h + d for h, d in zip(home, ins["home"]))
            elif isinstance(ins, (list, tuple)) and len(ins) == 3:
                cur[leg] = tuple(float(v) for v in ins)
            else:
                raise ValueError(f"frame {n} leg {leg}: unknown foot instruction {ins!r}")
        last = cur
        out.append(cur)
    return out


def contact_ok(feet_z: list[list[float]], min_grounded: int) -> list[int]:
    """Frames where fewer than `min_grounded` feet are on the ground (z <= 1e-9): a
    walk that leaves these has a moment of falling, which reads as a hop."""
    bad = []
    for i in range(len(feet_z[0])):
        g = sum(1 for leg in feet_z if leg[i] <= 1e-9)
        if g < min_grounded:
            bad.append(i)
    return bad
