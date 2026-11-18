"""spec.py — load and VALIDATE a creature spec. No Blender: tested on its own.

A creature is a data file (docs/dungeons/16). The point of validating up front is
that a new creature fails here, in milliseconds and with a sentence, and not 40
seconds into a render with a Blender traceback.

Schema (TOML), by section:
    name, family, size_class      identity; the roles.toml family; budget.SIZE_CLASSES
    [camera] [light]              as the hero styles (box, anchor, yaw_deg, ppu, ...)
    [[bone]]                      name, parent ("" for the root), head, tail
    [[part]]                      kind = ellipsoid | limb | box | cone | tube | dome ,
                                  role, bone, and the kind's own numbers
    [[legset]]                    an IK limb set: tags, hip{}, foot{}, parent, radii ...
    [action.<n>]                  type = keys | gait | poses, frames, hold, ...
    [[locator]]                   name, part: a named point projected each frame (stamps)
    [paint] [ramp.*] [palette]    the painter's rules and colours (paint.py)
"""
from __future__ import annotations

import sys
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import budget  # noqa: E402
import gaits  # noqa: E402

PART_KINDS = {"ellipsoid": {"c", "r"}, "limb": {"a", "b", "radius"}, "box": {"c", "s"},
              "cone": {"a", "b", "radius"}, "tube": {"pts"}, "dome": {"c", "r"},
              "lathe": {"c", "pts", "roles"}, "ring": {"c", "radius", "thick"},
              "spikes": {"c", "n", "R", "len", "radius"}, "petals": {"c", "n", "r", "radius"}}
ACTION_TYPES = {"keys", "gait", "poses"}
CHANNEL_KINDS = ("pitch", "roll", "yaw", "x", "y", "z", "scale", "stretch")


def load(path) -> dict:
    return tomllib.loads(Path(path).read_text())


def family_roles(family: str) -> set:
    roles = tomllib.loads((HERE.parent / "actors" / "roles.toml").read_text()).get("family", {})
    if family not in roles:
        return set()
    return {r["name"] for r in roles[family]["role"]} | {"shadow"}


def legset_bones(ls: dict) -> list:
    """The bone names a legset generates: <name>.<tag>.1 and .2, in tag order."""
    return [f"{ls['name']}.{t}.{k}" for t in ls["tags"] for k in (1, 2)]


def validate(s: dict) -> list:
    errs = []

    def need(cond, msg):
        if not cond:
            errs.append(msg)

    for k in ("name", "family", "size_class", "camera"):
        need(k in s, f"missing top-level `{k}`")
    if errs:
        return errs
    need(s["size_class"] in budget.SIZE_CLASSES, f"size_class {s['size_class']!r} is not one of {sorted(budget.SIZE_CLASSES)}")
    roles = family_roles(s["family"])
    need(bool(roles), f"family {s['family']!r} has no table in actors/roles.toml")
    cam = s["camera"]
    for k in ("box", "anchor", "px_per_unit", "supersample", "margin_px", "depression_deg", "yaw_deg"):
        need(k in cam, f"camera is missing `{k}`")
    if s["size_class"] in budget.SIZE_CLASSES and "box" in cam:
        w, h, kind, *_ = budget.SIZE_CLASSES[s["size_class"]]
        if kind == "obj":
            need(tuple(cam["box"]) == (w, h), f"camera.box {cam['box']} must be {w}x{h} for {s['size_class']}")
        need(cam["box"][0] % 8 == 0 and cam["box"][1] % 8 == 0, f"camera.box {cam['box']} must be whole 8x8 tiles")
    bones = {}
    for b in s.get("bone", []):
        need(b.get("name") not in bones, f"duplicate bone {b.get('name')!r}")
        bones[b.get("name")] = b.get("parent", "")
    legsets = {ls.get("name"): ls for ls in s.get("legset", [])}
    for ls in legsets.values():
        for k in ("name", "tags", "hip", "foot", "parent", "radius", "role"):
            need(k in ls, f"legset {ls.get('name')!r} is missing `{k}`")
        for t in ls.get("tags", []):
            need(t in ls.get("hip", {}) and t in ls.get("foot", {}), f"legset {ls.get('name')}: leg {t} has no hip/foot")
        for b in legset_bones(ls) if "tags" in ls and "name" in ls else []:
            bones[b] = ls.get("parent", "")
        need(ls.get("role") in roles, f"legset {ls.get('name')}: role {ls.get('role')!r} not in family {s['family']}")
    need("root" in bones, "a bone named `root` is required (the ground point)")
    for name, parent in bones.items():
        need(parent == "" or parent in bones or name == "root", f"bone {name!r}: parent {parent!r} does not exist")
    part_names = set()
    for p in s.get("part", []):
        kind = p.get("kind")
        need(kind in PART_KINDS, f"part {p.get('name')!r}: unknown kind {kind!r}")
        if kind in PART_KINDS:
            miss = PART_KINDS[kind] - set(p)
            need(not miss, f"part {p.get('name')!r} ({kind}) is missing {sorted(miss)}")
        need(p.get("role") in roles, f"part {p.get('name')!r}: role {p.get('role')!r} not in family {s['family']}")
        need(p.get("bone") in bones, f"part {p.get('name')!r}: bone {p.get('bone')!r} does not exist")
        part_names.add(p.get("name"))
    for loc in s.get("locator", []):
        need(loc.get("part") in part_names, f"locator {loc.get('name')!r}: part {loc.get('part')!r} does not exist")
    for an, a in s.get("action", {}).items():
        t = a.get("type")
        need(t in ACTION_TYPES, f"action {an}: type {t!r} must be one of {sorted(ACTION_TYPES)}")
        n = a.get("frames", 0)
        need(n >= 1, f"action {an}: frames must be >= 1")
        if "hold" in a:
            need(len(a["hold"]) == n, f"action {an}: {len(a['hold'])} holds for {n} frames")
        for ch, seq in a.get("keys", {}).items():
            bone, _, kind = ch.rpartition(".")
            need(bone in bones, f"action {an}: channel {ch!r}: no bone {bone!r}")
            need(kind in CHANNEL_KINDS, f"action {an}: channel {ch!r}: kind {kind!r} not in {CHANNEL_KINDS}")
            need(len(seq) == n, f"action {an}: channel {ch!r} has {len(seq)} values for {n} frames")
        for w in a.get("wave", []):
            for b in w.get("bones", []):
                need(b in bones, f"action {an}: wave bone {b!r} does not exist")
            need("amp" in w, f"action {an}: a wave needs `amp`")
        if t == "gait":
            ls = legsets.get(a.get("legset"))
            need(ls is not None, f"action {an}: legset {a.get('legset')!r} does not exist")
            if ls is not None:
                try:
                    gaits.leg_phases(a.get("gait", ""), len(ls["tags"]))
                except ValueError as e:
                    errs.append(f"action {an}: {e}")
        if t == "poses":
            for leg, seq in a.get("feet", {}).items():
                need(any(f"{leg}" == f"{ls['name']}.{tg}" for ls in legsets.values() for tg in ls["tags"]),
                     f"action {an}: foot {leg!r} is not a leg of any legset")
                need(len(seq) == n, f"action {an}: foot {leg!r} has {len(seq)} instructions for {n} frames")
    need(bool(s.get("action")), "at least one [action.*]")
    return errs
