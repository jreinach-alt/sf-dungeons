"""render_style.py — the art-direction spike's authoring model, in Blender.

    blender -b --factory-startup -P art/dungeons/style/render_style.py -- \
        --style art/dungeons/style/styles/a_storybook.toml \
        [--actions idle,walk,attack] [--dirs right,down] [--inspect] [--out DIR]

3D is an AUTHORING and ANIMATION AID here, not the look (the art direction
brief): this builds a hand-made-feeling wanderer from the parameters in the
style file's [model] table, keys idle / walk / attack from actions.toml, and
renders the same DATA frames as the spike pipeline (R sun, G material id,
B ambient occlusion). paint.py turns those into painted pixel clusters.

What it adds over actors/render_actor.py:
  * a pleated, ragged-hemmed cloak (folds are real geometry, so the shading
    bands read as fabric), a back-slung sword (hilt over the right shoulder),
    a satchel and strap, a belt and buckle, and a lantern on a hook;
  * a dark, recessed hooded face (no eyes modelled at all: paint.py stamps
    what the style wants);
  * a drawn sword in the hand for the attack;
  * LOCATORS: projected pixel positions of named points per frame
    (head, lantern, sword tip / mid), written to locs.json, so hand-authored
    pixel stamps follow the animation.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
import tomllib
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

HERE = Path(__file__).resolve().parent
ACTORS = HERE.parent / "actors"
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(ACTORS))
import blender_common as BC  # noqa: E402
import kit as K  # noqa: E402
import pose_data  # noqa: E402

K.AXIS["yaw"] = Vector((0, 0, 1))          # a twist about z, for the sword swing
pose_data.KINDS = pose_data.KINDS + ("yaw",)

# ---------------------------------------------------------------------------
# parameters: every key has a default; a style's [model] table overrides
# ---------------------------------------------------------------------------
DEFAULT_MODEL = dict(
    hood_r=1.0,            # hood shell scale
    hood_peak=0.10,        # length of the drooping tail of the hood
    hood_droop=0.05,
    hood_open_w=0.07,      # half width of the face opening
    hood_open_z=(0.80, 0.93),
    face_back=0.03,        # how far the face is recessed into the hood
    shoulder_w=0.14,
    cloak_top=(0.15, 0.125),    # rx, ry at the shoulders
    cloak_hem=(0.225, 0.20),    # rx, ry at the hem
    cloak_hem_z=0.11,
    cloak_arc=250.0,
    pleats=7, pleat_amp=0.10,
    jag=0.035, jag_n=9, asym=0.025,
    mantle=0.0,            # 0 = none; else the capelet's radius over the shoulders
    torso_r=(0.115, 0.085),
    boot_scale=1.0, boot_cuff=0.02,
    satchel=1.0, lantern=1.0,
    arm_r=0.040,
    sword_len=0.36, sword_w=0.036,
    skew=0.012,            # handmade asymmetry: shoulder/hip offsets
    edge_trim=2,           # columns of trim down each open cloak edge (the P1/P2 identity)
    hood_tail_x=0.0,       # lateral offset of the hood tail: a crooked hood
    head_fwd=0.0,          # the head carried forward: a hunch
)


def load_style(path: Path) -> dict:
    s = tomllib.loads(Path(path).read_text())
    m = dict(DEFAULT_MODEL)
    m.update(s.get("model", {}))
    s["model"] = m
    return s


def hash01(i: int, salt: int = 0) -> float:
    """A deterministic pseudo-random 0..1 (handmade irregularity, no RNG state)."""
    x = math.sin(i * 12.9898 + salt * 78.233) * 43758.5453
    return x - math.floor(x)


# ---------------------------------------------------------------------------
# small mesh helpers (built on blender_common.make_obj)
# ---------------------------------------------------------------------------
def bar(kit, name, p0, p1, w, t, role, taper=1.0):
    """A flat bar from p0 to p1: width w across, thickness t, optional taper to the tip."""
    a, b = Vector(p0), Vector(p1)
    d = (b - a)
    L = d.length
    d = d / L
    up = Vector((0, 1, 0)) if abs(d.y) < 0.9 else Vector((1, 0, 0))
    side = d.cross(up).normalized()
    nrm = d.cross(side).normalized()
    verts = []
    for p, k in ((a, 1.0), (b, taper)):
        for sx, sn in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            verts.append(tuple(p + side * (sx * w * k / 2) + nrm * (sn * t * k / 2)))
    faces = [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    return BC.make_obj(kit, name, verts, faces, role, smooth=20.0)


def taper(kit, name, z0, z1, r0, r1, role, seg=14, c=(0.0, 0.0), cap=True, ring_fn=None):
    """A lofted tube between two z levels with elliptical radii (rx, ry) at each end."""
    rings = []
    n = 4
    for i in range(n + 1):
        t = i / n
        z = z0 + (z1 - z0) * t
        rx = r0[0] + (r1[0] - r0[0]) * t
        ry = r0[1] + (r1[1] - r0[1]) * t
        if ring_fn:
            rx, ry = ring_fn(t, rx, ry)
        rings.append([(c[0] + rx * math.cos(2 * math.pi * k / seg),
                       c[1] + ry * math.sin(2 * math.pi * k / seg), z) for k in range(seg)])
    v, f, r = BC.loft(rings, lambda i, j: role, cap0=role if cap else None, cap1=role if cap else None)
    return BC.make_obj(kit, name, v, f, r, smooth=55.0)


def cloak_mesh(kit, M):
    """The skinned cloak: open at the front, pleated, ragged at the hem."""
    top_rx, top_ry = M["cloak_top"]
    hem_rx, hem_ry = M["cloak_hem"]
    zt, zh = 0.765, M["cloak_hem_z"]
    nr, seg = 10, 40
    half = math.radians(M["cloak_arc"]) / 2
    rings = []
    for i in range(nr + 1):
        t = i / nr
        z = zt + (zh - zt) * t
        flare = t ** 1.5
        rx = top_rx + (hem_rx - top_rx) * flare
        ry = top_ry + (hem_ry - top_ry) * flare
        ring = []
        for k in range(seg + 1):
            th = math.pi / 2 - half + 2 * half * k / seg        # +Y is the back
            pl = 1.0 + M["pleat_amp"] * (0.25 + 0.75 * t) * math.sin(M["pleats"] * th + 0.6 + t * 0.8)
            pl += 0.04 * (hash01(k, 3) - 0.5) * t               # handmade irregularity
            zz = z
            if i == nr:                                          # the ragged hem
                zz -= M["jag"] * (0.5 + 0.5 * math.sin(M["jag_n"] * th + 0.4)) * (0.55 + 0.45 * hash01(k, 7))
                zz -= M["asym"] * math.sin(th - math.pi / 2 + 0.7)
            ring.append((rx * pl * math.cos(th), 0.015 + ry * pl * math.sin(th), zz))
        rings.append(ring)
    n = seg + 1
    verts = [p for r in rings for p in r]
    faces, roles = [], []
    for i in range(nr):
        for k in range(seg):
            a = i * n + k
            faces.append((a, a + 1, a + 1 + n, a + n))
            roles.append("trim" if (i == nr - 1 or k < M["edge_trim"] or k >= seg - M["edge_trim"]) else "cloak")
    return BC.make_obj(kit, "cloak", verts, faces, roles, smooth=62.0)


def cloak_weights(co):
    z = co.z

    def ramp(z, z0, z1):
        return min(1.0, max(0.0, (z - z0) / (z1 - z0)))
    if z >= 0.62:
        return {"spine": 1.0}
    if z >= 0.42:
        t = ramp(z, 0.42, 0.62)
        return {"spine": t, "cloak.1": 1 - t}
    t = ramp(z, 0.12, 0.42)
    return {"cloak.1": t, "cloak.2": 1 - t}


def rig_spans(M):
    sk = M["skew"]
    S, H = {}, {}

    def bone(n, h, t, p):
        S[n], H[n] = (h, t), p
    bone("root", (0, 0, 0), (0, 0, 0.1), None)
    bone("hips", (0, 0, 0.46), (0, 0, 0.52), "root")
    bone("spine", (0, 0, 0.52), (0, 0, 0.72), "hips")
    bone("head", (0, 0, 0.74), (0, 0, 0.99), "spine")
    for side, x in (("L", 1), ("R", -1)):
        sw = M["shoulder_w"] + (sk if side == "L" else 0)
        bone(f"upperarm.{side}", (sw * x, -0.01, 0.725), ((sw + 0.012) * x, -0.02, 0.585), "spine")
        bone(f"forearm.{side}", ((sw + 0.012) * x, -0.02, 0.585), ((sw + 0.02) * x, -0.045, 0.45), f"upperarm.{side}")
        bone(f"thigh.{side}", (0.065 * x, 0, 0.46), (0.065 * x, 0, 0.25), "hips")
        bone(f"shin.{side}", (0.065 * x, 0, 0.25), (0.065 * x, 0, 0.0), f"thigh.{side}")
    bone("cloak.1", (0, 0.03, 0.60), (0, 0.03, 0.38), "hips")
    bone("cloak.2", (0, 0.03, 0.38), (0, 0.03, 0.12), "cloak.1")
    bone("weapon", (-(M["shoulder_w"] + 0.03), -0.045, 0.45), (-(M["shoulder_w"] + 0.03), -0.045, 0.10), "forearm.R")
    return S, H


# ---------------------------------------------------------------------------
# the wanderer
# ---------------------------------------------------------------------------
def build(kit, M):
    parts = []          # (object, bone) bound rigidly
    named = {}

    def rigid(ob, b, key=None):
        parts.append((ob, b))
        if key:
            named[key] = ob
        return ob

    sk = M["skew"]
    bs = M["boot_scale"]
    for side, x in (("L", 1), ("R", -1)):
        big = 1.0 + (0.06 if side == "L" else 0.0)                  # one boot a little bigger
        fx = 0.065 * x
        rigid(BC.box(kit, f"boot.{side}", (fx, -0.01, 0.034 * bs), (0.095 * bs * big, 0.108 * bs * big, 0.068 * bs), "leather", bevel=0.012), f"shin.{side}")
        rigid(taper(kit, f"bootshaft.{side}", 0.066, 0.17, (0.052 * bs, 0.052 * bs), (0.056 * bs, 0.056 * bs), "leather", c=(fx, 0.0)), f"shin.{side}")
        rigid(taper(kit, f"cuff.{side}", 0.165, 0.185, (0.060 * bs, 0.060 * bs), (0.066 * bs, 0.066 * bs), "leather", c=(fx, 0.0)), f"shin.{side}")
        rigid(K.limb(kit, f"trouser.{side}", (fx, 0, 0.47), (fx, 0, 0.17), 0.050, "cloak"), f"thigh.{side}")
        sw = M["shoulder_w"] + (sk if side == "L" else 0)
        ar = M["arm_r"]
        rigid(K.limb(kit, f"sleeveU.{side}", (sw * x, -0.01, 0.745), ((sw + 0.012) * x, -0.02, 0.585), ar, "cloak"), f"upperarm.{side}")
        rigid(K.limb(kit, f"sleeveL.{side}", ((sw + 0.012) * x, -0.02, 0.585), ((sw + 0.02) * x, -0.045, 0.47), ar * 0.92, "cloak"), f"forearm.{side}")
        rigid(K.limb(kit, f"wrist.{side}", ((sw + 0.02) * x, -0.045, 0.475), ((sw + 0.021) * x, -0.047, 0.448), ar * 0.95, "leather"), f"forearm.{side}")
        rigid(BC.ellipsoid(kit, f"hand.{side}", ((sw + 0.021) * x, -0.05, 0.435), (0.034, 0.034, 0.036), "skin"), f"forearm.{side}")
    tr = M["torso_r"]
    rigid(taper(kit, "torso", 0.47, 0.745, (tr[0] * 0.95, tr[1] * 0.95), (tr[0], tr[1]), "leather"), "spine", "torso")
    rigid(taper(kit, "belt", 0.485, 0.535, (tr[0] + 0.012, tr[1] + 0.012), (tr[0] + 0.012, tr[1] + 0.012), "detail"), "hips")
    rigid(BC.box(kit, "buckle", (0.015, -tr[1] - 0.016, 0.51), (0.045, 0.018, 0.04), "metal", bevel=0.005), "hips")
    rigid(K.limb(kit, "neck", (0, 0, 0.74), (0, 0, 0.80), 0.045, "skin"), "head")
    # ---- the hooded head: the face is deep in the hood, a dark void --------
    hr = M["hood_r"]
    hf = M["head_fwd"]
    rigid(BC.ellipsoid(kit, "face", (0, -0.01 + M["face_back"] - hf, 0.865), (0.080, 0.080, 0.095), "skin"), "head", "face")
    ow, (oz0, oz1) = M["hood_open_w"], M["hood_open_z"]

    def opening(c):
        return c.y < -0.04 and oz0 < c.z < oz1 and abs(c.x) < ow

    def hood_role(c):
        rim = c.y < -0.02 and (oz0 - 0.02 < c.z < oz1 + 0.025) and abs(c.x) < ow + 0.035
        return "trim" if rim and not (oz0 < c.z < oz1 and abs(c.x) < ow) else "cloak"
    rigid(K.shell(kit, "hood", (0, 0.015 - hf, 0.88), (0.135 * hr, 0.145 * hr, 0.14 * hr), hood_role,
                  keep=lambda c: not opening(c), nu=20, nv=12), "head")
    pk = M["hood_peak"]
    if pk > 0:
        base = [(0.05 * math.cos(2 * math.pi * k / 8), 0.105 - hf + 0.05 * math.sin(2 * math.pi * k / 8), 0.945) for k in range(8)]
        tip = (0.012 + M["hood_tail_x"], 0.105 - hf + pk + 0.08, 0.955 - M["hood_droop"] - pk * 0.35)
        rigid(BC.make_obj(kit, "hoodtail", base + [tip],
                          [(k, (k + 1) % 8, 8) for k in range(8)] + [tuple(range(7, -1, -1))], "cloak"), "head")
    if M["mantle"] > 0:
        mr = M["mantle"]
        rigid(taper(kit, "mantle", 0.60, 0.775, (mr, mr * 0.85), (mr * 0.62, mr * 0.55), "cloak", seg=18, c=(0, 0.01), cap=False), "spine")
    # ---- satchel, strap, lantern on its hook --------------------------------
    s = M["satchel"]
    rigid(BC.box(kit, "satchel", (0.130, -0.005, 0.42), (0.105 * s, 0.07 * s, 0.11 * s), "leather", bevel=0.014), "hips")
    rigid(BC.box(kit, "satchelflap", (0.130, -0.005, 0.465), (0.112 * s, 0.076 * s, 0.045 * s), "detail", bevel=0.008), "hips")
    rigid(BC.box(kit, "satchelclasp", (0.130, -0.044, 0.45), (0.022, 0.012, 0.03), "metal"), "hips")
    rigid(bar(kit, "strap", (-0.10, -0.075, 0.73), (0.118, -0.045, 0.49), 0.028, 0.014, "detail"), "spine")
    L = M["lantern"]
    rigid(bar(kit, "hook", (-0.115, -0.07, 0.505), (-0.14, -0.09, 0.455), 0.012, 0.012, "metal"), "hips")
    rigid(BC.box(kit, "lantern_cap", (-0.152, -0.095, 0.44), (0.05 * L, 0.05 * L, 0.014 * L), "metal"), "hips", "lantern_cap")
    rigid(BC.ellipsoid(kit, "lantern_glow", (-0.152, -0.095, 0.405), (0.03 * L, 0.03 * L, 0.04 * L), "glow"), "hips", "lantern")
    rigid(BC.box(kit, "lantern_base", (-0.152, -0.095, 0.365), (0.05 * L, 0.05 * L, 0.012 * L), "metal"), "hips")
    for cx, cy in ((-0.027, -0.027), (0.027, -0.027), (-0.027, 0.027), (0.027, 0.027)):
        rigid(bar(kit, "cage", (-0.152 + cx * L, -0.095 + cy * L, 0.435), (-0.152 + cx * L, -0.095 + cy * L, 0.37),
                  0.007, 0.007, "metal"), "hips")
    # ---- the sword: back-slung (hilt over the right shoulder) --------------
    def back_y(z):
        return 0.015 + (0.125 + (0.20 - 0.125) * max(0.0, (0.765 - z) / (0.765 - 0.11)) ** 1.5) + 0.03
    p_lo = (0.075, back_y(0.30), 0.30)
    p_hi = (-0.085, back_y(0.78), 0.78)
    rigid(bar(kit, "scabbard", p_lo, p_hi, 0.046, 0.030, "leather", taper=0.85), "spine", "scabbard")
    d = (Vector(p_hi) - Vector(p_lo)).normalized()
    g0 = Vector(p_hi) + d * 0.005
    g1 = Vector(p_hi) + d * 0.095
    rigid(bar(kit, "backguard", tuple(g0 - Vector((0.05, 0, 0.01))), tuple(g0 + Vector((0.05, 0, 0.01))), 0.02, 0.022, "metal"), "spine", "backhilt")
    rigid(bar(kit, "backgrip", tuple(g0), tuple(g1), 0.026, 0.026, "leather"), "spine", "backhilt")
    rigid(BC.ellipsoid(kit, "backpommel", tuple(g1 + d * 0.012), (0.022, 0.022, 0.022), "metal"), "spine", "backhilt")
    sword = []
    sl, sw_ = M["sword_len"], M["sword_w"]
    hx = -(M["shoulder_w"] + 0.03)
    # the drawn sword is modelled hanging DOWN from the hand along the weapon bone
    sword.append(bar(kit, "grip", (hx, -0.045, 0.468), (hx, -0.045, 0.404), 0.03, 0.03, "leather"))
    sword.append(BC.ellipsoid(kit, "pommel", (hx, -0.045, 0.478), (0.026, 0.026, 0.026), "metal"))
    sword.append(bar(kit, "guard", (hx - 0.05, -0.045, 0.40), (hx + 0.05, -0.045, 0.40), 0.026, 0.026, "metal"))
    sword.append(bar(kit, "blade", (hx, -0.045, 0.395), (hx, -0.045, 0.395 - sl), sw_, 0.012, "metal", taper=0.45))
    named["sword"] = sword
    named["blade"] = sword[-1]
    # ---- the cloak ------------------------------------------------------------
    cloak = cloak_mesh(kit, M)
    spans, parents = rig_spans(M)
    rig = K.build_armature(kit, spans, parents)
    for ob, b in parts:
        K.bind_rigid(rig, ob, b)
    for o in sword:
        K.bind_rigid(rig, o, "weapon")
    K.bind_skin(rig, cloak, cloak_weights)
    BC.add_shadow_disc(kit, 0.17, 0.12)
    return rig, named


def centroid(ob):
    me = ob.data
    if not me.vertices:
        return ob.matrix_world.translation
    c = sum((v.co for v in me.vertices), Vector()) / len(me.vertices)
    return ob.matrix_world @ c


def tip_of(ob):
    """The world position of a mesh's lowest local-z vertex (a blade's tip)."""
    v = min(ob.data.vertices, key=lambda v: v.co.z)
    return ob.matrix_world @ v.co


def project(scene, co, p, cam):
    bw, bh = cam["box"]
    m = cam["margin_px"]
    W, H = bw + 2 * m, bh + 2 * m
    v = world_to_camera_view(scene, co, p)
    return [round(v.x * W - m, 2), round((1.0 - v.y) * H - m, 2)]


INSPECT_COLOURS = {
    "cloak": (0.10, 0.14, 0.35), "trim": (0.62, 0.66, 0.74), "skin": (0.70, 0.45, 0.34),
    "leather": (0.30, 0.17, 0.09), "glow": (1.0, 0.75, 0.25), "metal": (0.55, 0.58, 0.60),
    "detail": (0.05, 0.04, 0.05), "shadow": (0, 0, 0),
}


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--style", type=Path, required=True)
    ap.add_argument("--actions", default="idle,walk,attack")
    ap.add_argument("--dirs", default="right,down")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--inspect", action="store_true")
    a = ap.parse_args(argv)
    style = load_style(a.style)
    name = style["name"]
    out = a.out or (BC.WORK / f"style_{name}")
    out.mkdir(parents=True, exist_ok=True)
    M = style["model"]
    cam = dict(style["camera"])
    base = tomllib.loads((HERE / "actions.toml").read_text())["action"]
    acts = {k: dict(v) for k, v in base.items()}
    for k, v in style.get("action", {}).items():           # per-style key overrides
        if "frames" in v:
            acts[k]["frames"] = v["frames"]
            acts[k]["hold"] = v.get("hold", acts[k]["hold"])
        acts[k].setdefault("keys", {}).update(v.get("keys", {}))
        for d, t in v.get("dir", {}).items():
            acts[k].setdefault("dir", {}).setdefault(d, {}).update(t)
    light = style.get("light", dict(samples=2, sun_dir=[-0.45, 0.55, -0.70]))
    scene, co, so = BC.setup_scene(samples=light.get("samples", 2), threads=2, sun_dir=light["sun_dir"])
    kit = BC.Kit("hero")
    BC.add_ground()
    rig, named = build(kit, M)
    log = {"style": name, "frames": []}
    if a.inspect:
        kit.set_mode("beauty", INSPECT_COLOURS)
        scene.view_settings.view_transform = "Standard"
        scene.cycles.samples = 24
        bw, bh = cam["box"]
        cw, ch = bw + 2 * cam["margin_px"], bh + 2 * cam["margin_px"]
        scene.render.resolution_x, scene.render.resolution_y = cw * 14, ch * 14
    else:
        kit.set_mode("data")
        BC.setup_compositor(scene)
    sword_back = [o for o in bpy.data.objects if o.name in ("backguard", "backgrip", "backpommel")]
    sword_hand = named["sword"]
    t0 = time.perf_counter()
    for an in a.actions.split(","):
        spec = acts[an]
        cfg = dict(cam)
        if an == "attack":
            cfg["box"] = cam.get("attack_box", [32, 32])
            cfg["anchor"] = cam.get("attack_anchor", [cfg["box"][0] // 2, cam["anchor"][1]])
        for o in sword_back:
            o.hide_render = spec.get("sword") == "drawn"
        for o in sword_hand:
            o.hide_render = spec.get("sword") != "drawn"
        BC.set_actor_camera(scene, co, cfg, cfg["anchor"])
        scale = 14 if a.inspect else cfg["supersample"]
        scene.render.resolution_x = (cfg["box"][0] + 2 * cfg["margin_px"]) * scale
        scene.render.resolution_y = (cfg["box"][1] + 2 * cfg["margin_px"]) * scale
        for d in a.dirs.split(","):
            K.key_action(rig, f"{an}_{d}", spec, d)
            K.set_direction(kit, cfg, d)
            for i in range(spec["frames"]):
                scene.frame_set(i)
                bpy.context.view_layer.update()
                f = out / f"{an}_{d}_{i}{'_inspect' if a.inspect else ''}.png"
                BC.render_to(scene, f)
                loc = {"head": project(scene, co, centroid(named["face"]), cfg),
                       "lantern": project(scene, co, centroid(named["lantern"]), cfg),
                       "root": project(scene, co, rig.matrix_world @ rig.pose.bones["root"].head, cfg)}
                if spec.get("sword") == "drawn":
                    loc["sword_tip"] = project(scene, co, tip_of(named["blade"]), cfg)
                    loc["sword_mid"] = project(scene, co, centroid(named["blade"]), cfg)
                log["frames"].append({"action": an, "dir": d, "i": i, "file": f.name, "loc": loc,
                                      "box": cfg["box"], "anchor": cfg["anchor"]})
    log["seconds"] = round(time.perf_counter() - t0, 2)
    if not a.inspect:
        (out / "locs.json").write_text(json.dumps(log, indent=1) + "\n")
    print(f"render_style[{name}]: {len(log['frames'])} frames in {log['seconds']} s")


if __name__ == "__main__":
    main()
