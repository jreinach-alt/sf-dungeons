"""creature.py — build, rig, animate and render ANY creature from its spec (Blender).

    blender -b --factory-startup -P art/dungeons/creatures/creature.py -- \
        --spec art/dungeons/creatures/specs/spider.toml \
        [--actions idle,skitter] [--dirs right,down] [--inspect] [--out DIR]

docs/dungeons/16. The hero pipeline (style/render_style.py) hard-codes one
character; this reads a SPEC (spec.py validates it first) so a new creature is a
data file:

  * parts: ellipsoid / limb / box / cone / tube / dome (a shell with hex scutes
    whose plates and seams are two ROLES, so the pattern is painted detail from
    the role map, not from shading), each bound rigidly to a bone; `mirror = true`
    makes the x-mirrored twin;
  * legsets: an IK limb set. Per leg: two bones, a knee fitted between hip and
    foot, a target the FOOT is pinned to, a pole that keeps the knee bending the
    right way (the pole's roll angle is FITTED against the rest pose, not guessed),
    the meshes, a joint ball and an optional foot pad;
  * actions: `keys` (bone channels), `gait` (gaits.py: N legs from phases, a
    stride and a lift) and `poses` (explicit bone channels plus planted / lifted
    feet: how a tortoise rises onto its hind feet without them sliding);
  * locators: named points projected to the sprite each frame, for stamps.

Output is the SAME data frame as the hero pipeline (R sun, G material id, B AO),
so paint.py paints it. locs.json carries frames, boxes, anchors and locators.
"""
from __future__ import annotations

import argparse
import colorsys
import json
import math
import sys
import time
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Quaternion, Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "actors"))
sys.path.insert(0, str(HERE.parent / "style"))
import blender_common as BC  # noqa: E402
import kit as K  # noqa: E402
import gaits  # noqa: E402
import spec as SP  # noqa: E402
from render_style import bar, hash01  # noqa: E402  (shared mesh helpers)

AXIS = {"pitch": Vector((1, 0, 0)), "roll": Vector((0, -1, 0)), "yaw": Vector((0, 0, 1))}


# ---------------------------------------------------------------------------
# extra part builders
# ---------------------------------------------------------------------------
def tube(kit, name, pts, role, seg=10):
    """A tube along a polyline of (x, y, z, radius): a tail, a neck, a horn."""
    angs = [2 * math.pi * k / seg for k in range(seg)]
    rings = []
    n = len(pts)
    for i, (x, y, z, r) in enumerate(pts):
        t = (Vector(pts[min(i + 1, n - 1)][:3]) - Vector(pts[max(i - 1, 0)][:3])).normalized()
        ref = Vector((0, 0, 1)) if abs(t.z) < 0.9 else Vector((1, 0, 0))
        u = t.cross(ref).normalized()
        v = t.cross(u).normalized()
        c = Vector((x, y, z))
        rings.append([tuple(c + (u * math.cos(a) + v * math.sin(a)) * r) for a in angs])
    vs, fs, rs = BC.loft(rings, lambda i, j: role, cap0=role, cap1=role)
    return BC.make_obj(kit, name, vs, fs, rs, smooth=60.0)


def cone(kit, name, a, b, radius, role, seg=8):
    a, b = Vector(a), Vector(b)
    t = (b - a).normalized()
    ref = Vector((0, 0, 1)) if abs(t.z) < 0.9 else Vector((1, 0, 0))
    u = t.cross(ref).normalized()
    v = t.cross(u).normalized()
    ring = [tuple(a + (u * math.cos(2 * math.pi * k / seg) + v * math.sin(2 * math.pi * k / seg)) * radius) for k in range(seg)]
    verts = ring + [tuple(b)]
    faces = [(k, (k + 1) % seg, seg) for k in range(seg)] + [tuple(range(seg - 1, -1, -1))]
    return BC.make_obj(kit, name, verts, faces, role, smooth=40.0)


def hex_cell(x, y, size):
    """The centre of the hexagon of circumradius `size` containing (x, y), and the
    distance to it: the lattice a tortoise's scutes sit on."""
    q = (math.sqrt(3) / 3 * x - 1 / 3 * y) / size
    r = (2 / 3 * y) / size
    xx, zz, yy = q, r, -q - r
    rx, ry, rz = round(xx), round(yy), round(zz)
    dx, dy, dz = abs(rx - xx), abs(ry - yy), abs(rz - zz)
    if dx > dy and dx > dz:
        rx = -ry - rz
    elif dy > dz:
        ry = -rx - rz
    else:
        rz = -rx - ry
    cx = size * math.sqrt(3) * (rx + rz / 2)
    cy = size * 1.5 * rz
    return cx, cy, math.hypot(x - cx, y - cy) / size


def dome(kit, name, c, r, role, p):
    """A shell: an ellipsoidal cap whose faces alternate between `role` (a scute
    plate, raised) and `seam_role` (the groove between plates) on a hex lattice."""
    polar = math.radians(p.get("polar_deg", 100))
    cells = p.get("cells", 0.3)
    plate = p.get("plate", 0.06)
    seam_role = p.get("seam_role", role)
    seam_w = p.get("seam_w", 0.22)
    nu, nv = p.get("nu", 80), p.get("nv", 32)
    cx0, cy0, cz0 = c
    rx, ry, rz = r
    grid = []
    for iv in range(nv + 1):
        phi = polar * iv / nv
        row = []
        for iu in range(nu):
            th = 2 * math.pi * iu / nu
            d = Vector((math.sin(phi) * math.cos(th), math.sin(phi) * math.sin(th), math.cos(phi)))
            _, _, hd = hex_cell(d.x * rx, d.y * ry, cells)
            raise_ = 1.0 + plate * (1.0 - min(1.0, max(0.0, (hd - 0.55) / 0.4)))   # plates are raised, seams sunk
            row.append((cx0 + rx * d.x * raise_, cy0 + ry * d.y * raise_, cz0 + rz * d.z * raise_, hd))
        grid.append(row)
    verts, faces, roles = [], [], []
    for row in grid:
        verts += [(x, y, z) for x, y, z, _ in row]
    for iv in range(nv):
        for iu in range(nu):
            a = iv * nu + iu
            b = iv * nu + (iu + 1) % nu
            c2 = (iv + 1) * nu + (iu + 1) % nu
            d2 = (iv + 1) * nu + iu
            faces.append((a, b, c2, d2))
            hd = sum(grid[iv + dv][(iu + du) % nu][3] for dv in (0, 1) for du in (0, 1)) / 4
            edge_band = iv >= nv - 2                          # the rim of the shell
            roles.append(seam_role if (hd > 1.0 - seam_w or edge_band) else role)
    return BC.make_obj(kit, name, verts, faces, roles, smooth=44.0)


# ---------------------------------------------------------------------------
# spec -> parts
# ---------------------------------------------------------------------------
def mirrored(p):
    q = dict(p)
    q["name"] = p["name"] + ".m"
    for k in ("c", "a", "b"):
        if k in q:
            q[k] = [-q[k][0], q[k][1], q[k][2]]
    if "pts" in q:
        q["pts"] = [[-x, y, z, r] for x, y, z, r in q["pts"]]
    return q


def make_part(kit, p):
    k = p["kind"]
    if k == "ellipsoid":
        return BC.ellipsoid(kit, p["name"], tuple(p["c"]), tuple(p["r"]), p["role"])
    if k == "limb":
        return K.limb(kit, p["name"], tuple(p["a"]), tuple(p["b"]), p["radius"], p["role"], seg=p.get("seg", 10))
    if k == "box":
        return BC.box(kit, p["name"], tuple(p["c"]), tuple(p["s"]), p["role"], bevel=p.get("bevel", 0.0))
    if k == "cone":
        return cone(kit, p["name"], p["a"], p["b"], p["radius"], p["role"], seg=p.get("seg", 8))
    if k == "tube":
        return tube(kit, p["name"], [tuple(v) for v in p["pts"]], p["role"], seg=p.get("seg", 10))
    if k == "dome":
        return dome(kit, p["name"], p["c"], p["r"], p["role"], p)
    raise ValueError(k)


def expand_legset(ls):
    """-> (bones, parts, iks) for one leg set. See the module doc."""
    bones, parts, iks = [], [], []
    cx, cy = ls.get("center", [0.0, 0.0])[:2]
    kl, ko = ls.get("knee_lift", 0.1), ls.get("knee_out", 0.0)
    r1, r2 = ls["radius"] if isinstance(ls["radius"], list) else (ls["radius"], ls["radius"] * 0.8)
    for tag in ls["tags"]:
        H, F = Vector(ls["hip"][tag]), Vector(ls["foot"][tag])
        out = Vector((H.x - cx, H.y - cy, 0.0))
        out = out.normalized() if out.length > 1e-6 else Vector((1, 0, 0))
        K_ = (H + F) / 2 + Vector((0, 0, kl)) + out * ko
        nm = f"{ls['name']}.{tag}"
        bones.append(dict(name=nm + ".1", parent=ls["parent"], head=list(H), tail=list(K_)))
        bones.append(dict(name=nm + ".2", parent=nm + ".1", head=list(K_), tail=list(F)))
        parts.append(dict(kind="limb", name=nm + ".u", a=list(H), b=list(K_), radius=r1, role=ls["role"], bone=nm + ".1"))
        parts.append(dict(kind="limb", name=nm + ".l", a=list(K_), b=list(F), radius=r2, role=ls.get("role_lower", ls["role"]), bone=nm + ".2"))
        parts.append(dict(kind="ellipsoid", name=nm + ".k", c=list(K_), r=[r1 * 1.2] * 3, role=ls["role"], bone=nm + ".1"))
        if "foot" in ls.get("pad", {}):
            pr = ls["pad"]["r"]
            parts.append(dict(kind="ellipsoid", name=nm + ".f", c=list(F + Vector((0, 0, pr[2] * 0.6))), r=pr,
                              role=ls["pad"].get("role", ls["role"]), bone=nm + ".2"))
        cl = ls.get("claws")
        if cl:                                              # toes: small cones from the front of the foot
            front = ls["pad"]["r"][1] * 0.85 if "pad" in ls else 0.05
            for j in range(cl["n"]):
                dx = (j - (cl["n"] - 1) / 2) * cl["spread"]
                base = F + Vector((dx, -front, 0.03))
                parts.append(dict(kind="cone", name=f"{nm}.c{j}", a=list(base), b=list(base + Vector((0, -cl["len"], -0.012))),
                                  radius=cl.get("radius", 0.022), role=cl.get("role", ls["role"]), bone=nm + ".2"))
        iks.append(dict(bone=nm + ".2", target=nm + ".target", pole=nm + ".pole", home=list(F),
                        pole_home=list(K_ + Vector((0, 0, ls.get("pole_up", 0.25))) + out * ls.get("pole_out", 0.0)),
                        parent=ls["parent"], leg=nm))
    return bones, parts, iks


def build_armature(kit, bones):
    arm = bpy.data.armatures.new("rig")
    ob = bpy.data.objects.new("rig", arm)
    bpy.context.scene.collection.objects.link(ob)
    ob.parent = kit.root
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    by = {b["name"]: b for b in bones}
    for b in bones:
        eb = arm.edit_bones.new(b["name"])
        eb.head, eb.tail = Vector(b["head"]), Vector(b["tail"])
    for b in bones:
        if b.get("parent"):
            eb = arm.edit_bones[b["name"]]
            eb.parent = arm.edit_bones[b["parent"]]
            eb.use_connect = (Vector(b["head"]) - Vector(by[b["parent"]]["tail"])).length < 1e-6
    bpy.ops.object.mode_set(mode="OBJECT")
    for pb in ob.pose.bones:
        pb.rotation_mode = "QUATERNION"
    return ob


def empty(kit, name, loc, parent=None):
    e = bpy.data.objects.new(name, None)
    e.empty_display_size = 0.02
    bpy.context.scene.collection.objects.link(e)
    e.parent = parent or kit.root
    e.location = Vector(loc)
    return e


def setup_ik(kit, rig, iks):
    """A target (model space, keyed) and a pole (riding the parent bone) per leg."""
    bpy.context.view_layer.update()
    targets = {}
    for ik in iks:
        tgt = empty(kit, ik["target"], ik["home"])
        pole = empty(kit, ik["pole"], ik["pole_home"])
        K.bind_rigid(rig, pole, ik["parent"])             # the pole rides the body
        pb = rig.pose.bones[ik["bone"]]
        c = pb.constraints.new("IK")
        c.target, c.pole_target, c.chain_count, c.use_tail = tgt, pole, 2, True
        c.pole_subtarget = ""
        targets[ik["leg"]] = (tgt, ik)
    bpy.context.view_layer.update()
    # FIT the pole angle: pick the roll that puts the solved knee back where the rest pose had it
    for leg, (tgt, ik) in targets.items():
        pb = rig.pose.bones[ik["bone"]]
        c = [x for x in pb.constraints if x.type == "IK"][0]
        want = rig.matrix_world @ Vector(rig.data.bones[ik["bone"]].head_local)
        best = (1e9, 0.0)
        for deg in (0, 90, -90, 180):
            c.pole_angle = math.radians(deg)
            bpy.context.view_layer.update()
            got = rig.matrix_world @ rig.pose.bones[ik["bone"]].head
            d = (got - want).length
            if d < best[0]:
                best = (d, deg)
        c.pole_angle = math.radians(best[1])
    bpy.context.view_layer.update()
    return {leg: t for leg, (t, _) in targets.items()}


# ---------------------------------------------------------------------------
# posing and keying
# ---------------------------------------------------------------------------
def pose_values(rig, values):
    for pb in rig.pose.bones:
        pb.rotation_quaternion = Quaternion()
        pb.location = Vector()
    rots, trans = {}, {}
    for ch, v in values.items():
        bone, _, kind = ch.rpartition(".")
        pb = rig.pose.bones[bone]
        rest = pb.bone.matrix_local.to_3x3()
        if kind in ("x", "y", "z"):
            vec = Vector((v if kind == "x" else 0.0, v if kind == "y" else 0.0, v if kind == "z" else 0.0))
            trans[bone] = trans.get(bone, Vector()) + rest.inverted() @ vec
        else:
            ax = (rest.inverted() @ AXIS[kind]).normalized()
            rots[bone] = rots.get(bone, Quaternion()) @ Quaternion(ax, math.radians(v))
    for b, q in rots.items():
        rig.pose.bones[b].rotation_quaternion = q
    for b, t in trans.items():
        rig.pose.bones[b].location = t


def frame_plan(spec, an, a, targets, homes):
    """-> per frame: (bone channel values, {leg: foot position}) for an action."""
    n = a["frames"]
    keys = a.get("keys", {})
    plan = []
    if a["type"] == "gait":
        ls = next(x for x in spec["legset"] if x["name"] == a["legset"])
        ph = gaits.leg_phases(a["gait"], len(ls["tags"]))
        g = gaits.gait_frames(n, ph, a["stride"], a["lift"], a.get("duty", 0.6), a.get("bob", 0.0), a.get("steps", 1))
        for i in range(n):
            vals = {ch: float(seq[i]) for ch, seq in keys.items()}
            vals[ls["parent"] + ".z"] = vals.get(ls["parent"] + ".z", 0.0) + g["body_z"][i]
            feet = {}
            for li, tag in enumerate(ls["tags"]):
                leg = f"{ls['name']}.{tag}"
                dx, dy, dz = g["feet"][li][i]
                h = homes[leg]
                feet[leg] = (h[0] + dx, h[1] + dy, h[2] + dz)
            plan.append((vals, feet))
    else:
        feet_spec = a.get("feet", {})
        frames = [{leg: seq[i] for leg, seq in feet_spec.items()} for i in range(n)]
        if a["type"] == "keys":                       # a keyed action: every foot stays at home
            feet = [dict(homes) for _ in range(n)]
        else:
            feet = gaits.resolve_feet(frames, homes) if homes else [{} for _ in range(n)]
        for i in range(n):
            plan.append(({ch: float(seq[i]) for ch, seq in keys.items()}, feet[i]))
    return plan


def key_plan(rig, targets, plan, per_dir=None):
    for ob in [rig] + [t for t in targets.values()]:
        ob.animation_data_clear()
    rig.animation_data_create()
    for i, (vals, feet) in enumerate(plan):
        pose_values(rig, vals)
        for pb in rig.pose.bones:
            pb.keyframe_insert("rotation_quaternion", frame=i)
            pb.keyframe_insert("location", frame=i)
        for leg, pos in feet.items():
            t = targets[leg]
            t.location = Vector(pos)
            t.keyframe_insert("location", frame=i)
    for act in bpy.data.actions:
        for fc in act.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = "CONSTANT"


# ---------------------------------------------------------------------------
# rendering helpers
# ---------------------------------------------------------------------------
def centroid(ob):
    me = ob.data
    c = sum((v.co for v in me.vertices), Vector()) / max(len(me.vertices), 1)
    return ob.matrix_world @ c


def project(scene, co, p, cam):
    bw, bh = cam["box"]
    m = cam["margin_px"]
    W, H = bw + 2 * m, bh + 2 * m
    v = world_to_camera_view(scene, co, p)
    return [round(v.x * W - m, 2), round((1.0 - v.y) * H - m, 2)]


def inspect_colours(roles):
    out = {}
    for i, r in enumerate(sorted(roles)):
        h = (i * 0.61803) % 1.0
        out[r] = colorsys.hsv_to_rgb(h, 0.55, 0.75)
    out["shadow"] = (0, 0, 0)
    return out


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", type=Path, required=True)
    ap.add_argument("--actions", default="")
    ap.add_argument("--dirs", default="right,down")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--inspect", action="store_true")
    ap.add_argument("--iscale", type=int, default=5, help="inspect render pixels per sprite pixel")
    ap.add_argument("--isamples", type=int, default=6)
    a = ap.parse_args(argv)
    spec = SP.load(a.spec)
    errs = SP.validate(spec)
    if errs:
        sys.exit("creature.py: " + a.spec.name + " is invalid:\n  " + "\n  ".join(errs))
    name = spec["name"]
    out = a.out or (BC.WORK / f"creature_{name}")
    out.mkdir(parents=True, exist_ok=True)
    cam = dict(spec["camera"])
    light = spec.get("light", dict(samples=2, sun_dir=[-0.45, 0.55, -0.70]))
    scene, co, so = BC.setup_scene(samples=light.get("samples", 2), threads=2, sun_dir=light["sun_dir"])
    kit = BC.Kit(spec["family"])
    BC.add_ground()
    # ---- parts + bones + ik ---------------------------------------------------------
    bones = [dict(b) for b in spec.get("bone", [])]
    parts = [dict(p) for p in spec.get("part", [])]
    iks = []
    for ls in spec.get("legset", []):
        b, p, i = expand_legset(ls)
        bones += b
        parts += p
        iks += i
    objs = {}
    for p in parts:
        ob = make_part(kit, p)
        objs[p["name"]] = (ob, p["bone"])
        if p.get("mirror"):
            q = mirrored(p)
            objs[q["name"]] = (make_part(kit, q), p["bone"])
    rig = build_armature(kit, bones)
    for ob, bone in objs.values():
        K.bind_rigid(rig, ob, bone)
    targets = setup_ik(kit, rig, iks)
    homes = {ik["leg"]: tuple(ik["home"]) for ik in iks}
    sh = spec.get("shadow", [0.2, 0.15])
    BC.add_shadow_disc(kit, sh[0], sh[1])
    # ---- render ----------------------------------------------------------------------
    if a.inspect:
        kit.set_mode("beauty", inspect_colours(set(kit.mats) - {"shadow"}))
        scene.view_settings.view_transform = "Standard"
        scene.cycles.samples = a.isamples
    else:
        kit.set_mode("data")
        BC.setup_compositor(scene)
    log = {"creature": name, "frames": []}
    t0 = time.perf_counter()
    names = [n for n in (a.actions.split(",") if a.actions else spec["action"].keys()) if n]
    for an in names:
        act = spec["action"][an]
        cfg = dict(cam)
        if "box" in act:
            cfg["box"] = act["box"]
        if "anchor" in act:
            cfg["anchor"] = act["anchor"]
        BC.set_actor_camera(scene, co, cfg, cfg["anchor"])
        scale = a.iscale if a.inspect else cfg["supersample"]
        scene.render.resolution_x = (cfg["box"][0] + 2 * cfg["margin_px"]) * scale
        scene.render.resolution_y = (cfg["box"][1] + 2 * cfg["margin_px"]) * scale
        plan = frame_plan(spec, an, act, targets, homes)
        for d in a.dirs.split(","):
            key_plan(rig, targets, plan)
            K.set_direction(kit, cfg, d)
            for i in range(act["frames"]):
                scene.frame_set(i)
                bpy.context.view_layer.update()
                f = out / f"{an}_{d}_{i}{'_inspect' if a.inspect else ''}.png"
                BC.render_to(scene, f)
                loc = {}
                for L in spec.get("locator", []):
                    loc[L["name"]] = project(scene, co, centroid(objs[L["part"]][0]), cfg)
                loc["root"] = project(scene, co, rig.matrix_world @ rig.pose.bones["root"].head, cfg)
                log["frames"].append({"action": an, "dir": d, "i": i, "file": f.name, "loc": loc,
                                      "box": cfg["box"], "anchor": cfg["anchor"]})
    log["seconds"] = round(time.perf_counter() - t0, 2)
    if not a.inspect:
        (out / "locs.json").write_text(json.dumps(log, indent=1) + "\n")
    print(f"creature[{name}]: {len(log['frames'])} frames in {log['seconds']} s")


if __name__ == "__main__":
    main()
