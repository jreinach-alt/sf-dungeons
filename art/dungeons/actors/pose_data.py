"""pose_data.py — actions.toml channel semantics, with no Blender dependency.

kit.py (inside Blender) poses the rig from these values; the tests
(tests/test_dungeons_frames.py) pin them without Blender. The convention for
what a channel MEANS geometrically is in kit.py's module doc.

    <bone>.<kind>   kind in KINDS; bone in actions.toml rig.bones
"""
from __future__ import annotations

KINDS = ("pitch", "roll", "z")
LAG_PREFIX = "cloak."     # secondary motion: these bones lag by one sample


def channel_split(ch: str):
    bone, _, kind = ch.rpartition(".")
    return bone, kind


def action_values(act: dict, i: int, d: str | None = None) -> dict:
    """Frame i's channel values. `[action.<a>.dir.<d>]` channels replace the
    shared `keys` for direction d (a down-walk is drawn, not rotated: depth
    projects onto screen y). Secondary motion: channels on `cloak.*` bones
    take frame i-1's value, wrapping (13 §3 step 3)."""
    n = act["frames"]
    keys = dict(act.get("keys", {}))
    keys.update(act.get("dir", {}).get(d, {}))
    out = {}
    for ch, seq in keys.items():
        if len(seq) != n:
            raise ValueError(f"{ch}: {len(seq)} values for {n} frames")
        j = (i - 1) % n if ch.startswith(LAG_PREFIX) else i
        out[ch] = float(seq[j])
    return out


def check(doc: dict) -> list[str]:
    """Every channel of every action names a real bone and a known kind, has
    one value per frame, and every `dir` table names a camera direction."""
    bones = set(doc["rig"]["bones"])
    dirs = set(doc["camera"]["directions"])
    errs = []
    for name, act in doc["action"].items():
        tables = [("keys", act.get("keys", {}))]
        for d, t in act.get("dir", {}).items():
            if d not in dirs:
                errs.append(f"{name}.dir.{d}: not a camera direction")
            tables.append((f"dir.{d}", t))
        for where, t in tables:
            for ch, seq in t.items():
                bone, kind = channel_split(ch)
                if bone not in bones:
                    errs.append(f"{name}.{where}: {ch}: no bone {bone!r}")
                if kind not in KINDS:
                    errs.append(f"{name}.{where}: {ch}: kind {kind!r} not in {KINDS}")
                if len(seq) != act["frames"]:
                    errs.append(f"{name}.{where}: {ch}: {len(seq)} values, {act['frames']} frames")
    return errs
