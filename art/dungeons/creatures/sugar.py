"""sugar.py — spec shorthands and generators with no Blender in them (tested on their own).

`spikes` (crown points, wax drips, thorns) and `petals` (a flower) expand to many primitive parts;
`wave_keys` turns a wave instruction into per-frame channel values for a chain of bones
(tendrils, tails, hair). Everything here is deterministic: no random numbers, a hash instead.
"""
from __future__ import annotations

import math


def hash01(i: int, salt: int = 0) -> float:
    """A deterministic pseudo-random 0..1 (handmade irregularity, no RNG state)."""
    x = math.sin(i * 12.9898 + salt * 78.233) * 43758.5453
    return x - math.floor(x)


def expand_sugar(p):
    """`spikes` and `petals` are shorthands for many primitive parts. -> a list of parts."""
    if p["kind"] == "spikes":
        out = []
        cx, cy, cz = p["c"]
        n, R = p["n"], p["R"]
        lo, hi = (p["len"] if isinstance(p["len"], list) else [p["len"], p["len"]])
        arc = math.radians(p.get("arc_deg", 360))
        a0 = math.radians(p.get("start_deg", 0))
        up = -1.0 if p.get("dir", "up") == "down" else 1.0
        for k in range(n):
            full = arc >= 2 * math.pi - 1e-6
            th = a0 + (arc * k / n if full else arc * k / max(n - 1, 1))
            h = lo + (hi - lo) * hash01(k, p.get("seed", 1))
            base = [cx + R * math.cos(th), cy + R * math.sin(th), cz]
            tip = [base[0] + p.get("lean", 0.0) * math.cos(th), base[1] + p.get("lean", 0.0) * math.sin(th), cz + up * h]
            out.append(dict(kind="cone", name=f"{p['name']}.{k}", a=base, b=tip, radius=p["radius"] * (0.8 + 0.4 * hash01(k, 5)),
                            role=p["role"], bone=p["bone"], seg=p.get("seg", 6)))
        return out
    if p["kind"] == "petals":
        out = []
        cx, cy, cz = p["c"]
        for k in range(p["n"]):
            th = 2 * math.pi * k / p["n"] + math.radians(p.get("start_deg", 0))
            rx = p["r"][0]
            out.append(dict(kind="ellipsoid", name=f"{p['name']}.{k}",
                            c=[cx + p["radius"] * math.cos(th), cy + p["radius"] * math.sin(th), cz + math.sin(math.radians(p.get("tilt", 25))) * rx * 0.8],
                            r=p["r"], rot=[0.0, -p.get("tilt", 25), math.degrees(th)], role=p["role"], bone=p["bone"]))
        return out
    return [p]




def wave_keys(w: dict, n: int) -> dict:
    """{"<bone>.<kind>": [value per frame]} for a travelling wave down a chain of bones.

    Each bone is `lag` radians behind the one before it, so the chain ripples from root to tip.
    A wave loops exactly: frame n would equal frame 0 (an integer number of `cycles`).
    """
    out = {}
    for j, b in enumerate(w["bones"]):
        out[f"{b}.{w.get('kind', 'pitch')}"] = [
            w["amp"] * math.sin(2 * math.pi * (w.get("cycles", 1) * i / n) + w.get("phase", 0.0) + j * w.get("lag", 0.8))
            + w.get("bias", 0.0) for i in range(n)]
    return out
