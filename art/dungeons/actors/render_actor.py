"""render_actor.py — SuperForge Dungeons: build the wanderer, rig it, key it, render it.

    blender -b --factory-startup -P art/dungeons/actors/render_actor.py -- \
        [--actions idle,walk] [--dirs right,up,down] [--frames 0,1] \
        [--out build/dgn_art_work] [--inspect]

docs/dungeons/13 §3. The structure is sf-gt's render_car.py (setup_scene /
setup_compositor / camera / render_to, all in blender_common.py), plus the
figure: build_wanderer (parts on a Kit("hero")), build_armature (bones named
as actions.toml rig.bones), key_action, set_direction (kit.py), render_frame,
project_anchor.

Writes, per frame, the DATA frame (R sun, G material id, B AO)
    <out>/wanderer_<action>_<dir>_<i>_body.png
and once per run
    <out>/render_log.json   the projected root pixel per frame + render seconds
--inspect writes colour pictures of the model instead (looking only).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import blender_common as BC  # noqa: E402
import kit as K  # noqa: E402
import pose_data  # noqa: E402

MODEL = "wanderer"


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--actions", default="idle,walk")
    ap.add_argument("--dirs", default="right,up,down")
    ap.add_argument("--frames", default="")
    ap.add_argument("--out", type=Path, default=BC.WORK)
    ap.add_argument("--inspect", action="store_true")
    ap.add_argument("--threads", type=int, default=2)
    return ap.parse_args(argv)


# ---------------------------------------------------------------------------
# the wanderer (10 §6): a cloaked traveller, satchel, lantern hook, boots.
# Rest pose faces -Y. All numbers are units (1 u = 16 sprite px).
# ---------------------------------------------------------------------------
def rig_spans():
    S, H = {}, {}

    def bone(n, h, t, p):
        S[n], H[n] = (h, t), p
    bone("root", (0, 0, 0), (0, 0, 0.1), None)
    bone("hips", (0, 0, 0.30), (0, 0, 0.40), "root")
    bone("spine", (0, 0, 0.40), (0, 0, 0.58), "hips")
    bone("head", (0, 0, 0.60), (0, 0, 0.80), "spine")
    for side, x in (("L", 1), ("R", -1)):
        bone(f"upperarm.{side}", (0.15 * x, -0.02, 0.55), (0.16 * x, -0.03, 0.42), "spine")
        bone(f"forearm.{side}", (0.16 * x, -0.03, 0.42), (0.16 * x, -0.05, 0.31), f"upperarm.{side}")
        bone(f"thigh.{side}", (0.065 * x, 0, 0.30), (0.065 * x, 0, 0.15), "hips")
        bone(f"shin.{side}", (0.065 * x, 0, 0.15), (0.065 * x, 0, 0.0), f"thigh.{side}")
    bone("cloak.1", (0, 0.02, 0.44), (0, 0.02, 0.28), "hips")
    bone("cloak.2", (0, 0.02, 0.28), (0, 0.02, 0.12), "cloak.1")
    bone("weapon", (-0.16, -0.05, 0.31), (-0.16, -0.15, 0.31), "forearm.R")
    return S, H


def cloak_weights(co):
    """Shoulders follow the spine; below the hips the cloak chain takes over
    (13 §3 step 2: the chain is weighted to the cloak's lower rings)."""
    z = co.z

    def ramp(z, z0, z1):                     # 0 at z0, 1 at z1
        return min(1.0, max(0.0, (z - z0) / (z1 - z0)))
    if z >= 0.44:
        return {"spine": 1.0}
    if z >= 0.30:
        t = ramp(z, 0.30, 0.44)
        return {"spine": t, "hips": 1 - t} if t > 0.5 else {"spine": t, "cloak.1": 1 - t}
    t = ramp(z, 0.12, 0.30)
    return {"cloak.1": t, "cloak.2": 1 - t}


def build_wanderer(kit):
    parts = []                                # (object, bone) for rigid parts

    def rigid(ob, b):
        parts.append((ob, b))
        return ob
    for side, x in (("L", 1), ("R", -1)):
        rigid(BC.box(kit, f"boot.{side}", (0.065 * x, -0.005, 0.0375), (0.09, 0.12, 0.075),
                     "leather", bevel=0.015), f"shin.{side}")
        rigid(K.limb(kit, f"shinmesh.{side}", (0.065 * x, 0, 0.16), (0.065 * x, 0, 0.05),
                     0.038, "cloak"), f"shin.{side}")
        rigid(K.limb(kit, f"thighmesh.{side}", (0.065 * x, 0, 0.31), (0.065 * x, 0, 0.15),
                     0.048, "cloak"), f"thigh.{side}")
        rigid(K.limb(kit, f"upperarmmesh.{side}", (0.15 * x, -0.02, 0.56), (0.16 * x, -0.03, 0.42),
                     0.042, "cloak"), f"upperarm.{side}")
        rigid(K.limb(kit, f"forearmmesh.{side}", (0.16 * x, -0.03, 0.42), (0.16 * x, -0.05, 0.32),
                     0.038, "cloak"), f"forearm.{side}")
        rigid(BC.ellipsoid(kit, f"hand.{side}", (0.16 * x, -0.055, 0.30), (0.035, 0.035, 0.035),
                           "skin"), f"forearm.{side}")
    rigid(K.limb(kit, "torso", (0, 0, 0.27), (0, 0, 0.58), 0.11, "leather"), "spine")
    rigid(K.limb(kit, "belt", (0, 0, 0.30), (0, 0, 0.34), 0.118, "leather", seg=14), "hips")
    rigid(BC.box(kit, "buckle", (0, -0.118, 0.32), (0.04, 0.02, 0.035), "metal"), "hips")
    # head, eyes and hood
    rigid(BC.ellipsoid(kit, "headmesh", (0, -0.01, 0.71), (0.112, 0.105, 0.11), "skin"), "head")
    for side, x in (("L", 1), ("R", -1)):
        rigid(BC.ellipsoid(kit, f"eye.{side}", (0.056 * x, -0.1, 0.715), (0.026, 0.02, 0.034),
                           "detail"), "head")

    def opening(c):                           # the face hole, seen from the front
        return c.y < -0.03 and 0.62 < c.z < 0.80 and abs(c.x) < 0.10
    rigid(K.shell(kit, "hood", (0, 0.012, 0.725), (0.14, 0.145, 0.145),
                  lambda c: "trim" if (c.y < -0.0 and 0.58 < c.z < 0.84 and abs(c.x) < 0.13)
                  else "cloak", keep=lambda c: not opening(c)), "head")
    tip = BC.make_obj(kit, "hoodtip",
                      [(0.05 * math.cos(2 * math.pi * k / 8), 0.09 + 0.05 * math.sin(2 * math.pi * k / 8),
                        0.80) for k in range(8)] + [(0, 0.20, 0.86)],
                      [(k, (k + 1) % 8, 8) for k in range(8)] + [tuple(range(7, -1, -1))], "cloak")
    rigid(tip, "head")
    # satchel (left hip, over the cloak) and the lantern (right hip, front)
    rigid(BC.box(kit, "satchel", (0.13, 0.18, 0.30), (0.10, 0.06, 0.10), "leather",
                 bevel=0.012), "hips")
    rigid(BC.box(kit, "lantern_cap", (-0.10, -0.19, 0.265), (0.055, 0.055, 0.025), "metal"), "hips")
    rigid(BC.ellipsoid(kit, "lantern", (-0.10, -0.19, 0.22), (0.035, 0.035, 0.045), "glow"), "hips")
    rigid(K.limb(kit, "lantern_hook", (-0.07, -0.11, 0.315), (-0.10, -0.19, 0.28), 0.008,
                 "metal", seg=6), "hips")
    # the cloak: open at the front, trimmed at the hem; SKINNED
    rings = [(0.59, 0.17, 0.13), (0.53, 0.2, 0.155), (0.44, 0.205, 0.17),
             (0.36, 0.21, 0.185), (0.28, 0.22, 0.195), (0.235, 0.225, 0.2),
             (0.19, 0.23, 0.205)]
    cloak = K.bell(kit, "cloak", rings, 230.0,
                   lambda i, k: "trim" if i == len(rings) - 2 else "cloak", centre_y=0.01)
    return parts, cloak


def build(kit):
    parts, cloak = build_wanderer(kit)
    spans, parents = rig_spans()
    rig = K.build_armature(kit, spans, parents)
    for ob, b in parts:
        K.bind_rigid(rig, ob, b)
    K.bind_skin(rig, cloak, cloak_weights)
    BC.add_shadow_disc(kit, 0.17, 0.17)
    return rig


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------
def project_anchor(scene, co, rig, cam_cfg):
    """The root bone's head -> sprite pixel (x, y) in the box (13 §3 step 6)."""
    bpy.context.view_layer.update()
    p = rig.matrix_world @ rig.pose.bones["root"].head
    v = world_to_camera_view(scene, co, p)
    bw, bh = cam_cfg["box"]
    m = cam_cfg["margin_px"]
    W, H = bw + 2 * m, bh + 2 * m
    return [round(v.x * W - m, 3), round((1.0 - v.y) * H - m, 3)]


def render_frame(scene, out, action, d, i, layer="body"):
    path = out / f"{MODEL}_{action}_{d}_{i}_{layer}.png"
    t0 = time.perf_counter()
    BC.render_to(scene, path)
    return path, time.perf_counter() - t0


INSPECT_COLOURS = {   # looking only (P1 preview tones); never feeds a sprite
    "cloak": (0.10, 0.14, 0.35), "trim": (0.7, 0.72, 0.78), "skin": (0.75, 0.5, 0.38),
    "leather": (0.28, 0.16, 0.08), "glow": (1.0, 0.8, 0.3), "metal": (0.5, 0.5, 0.52),
    "detail": (0.02, 0.02, 0.03), "shadow": (0, 0, 0),
}


def inspect(scene, co, kit, rig, out, act):
    kit.set_mode("beauty", INSPECT_COLOURS)
    scene.view_settings.view_transform = "Standard"
    scene.cycles.samples = 16
    scene.render.resolution_x = scene.render.resolution_y = 320
    co.data.ortho_scale = 1.3
    spec = act["action"]["walk"]
    for d in ("right", "up", "down"):
        K.key_action(rig, f"walk_{d}", spec, d)
        K.set_direction(kit, act["camera"], d)
        for i in range(spec["frames"]):
            scene.frame_set(i)
            BC.render_to(scene, out / f"{MODEL}_inspect_walk_{d}_{i}.png")


def main():
    a = parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    act = BC.load_toml("actions.toml")
    errs = pose_data.check(act)
    if errs:
        sys.exit("render_actor: actions.toml: " + "; ".join(errs))
    cam_cfg, light = act["camera"], act["light"]
    scene, co, so = BC.setup_scene(samples=light["samples"], threads=a.threads,
                                   sun_dir=light["sun_dir"])
    kit = BC.Kit("hero")
    BC.add_ground()
    rig = build(kit)
    BC.set_actor_camera(scene, co, cam_cfg, act["rig"]["anchor_px"])
    if a.inspect:
        co.location = co.location + Vector((0, 0, 0.0))
        inspect(scene, co, kit, rig, a.out, act)
        return
    kit.set_mode("data")
    BC.setup_compositor(scene)
    log = {"blender": bpy.app.version_string, "anchor_px": act["rig"]["anchor_px"], "frames": []}
    for name in a.actions.split(","):
        spec = act["action"][name]
        frames = [int(f) for f in a.frames.split(",")] if a.frames else range(spec["frames"])
        for d in a.dirs.split(","):
            K.key_action(rig, f"{name}_{d}", spec, d)
            K.set_direction(kit, cam_cfg, d)
            for i in frames:
                scene.frame_set(i)
                path, secs = render_frame(scene, a.out, name, d, i)
                log["frames"].append({"action": name, "dir": d, "i": i, "file": path.name,
                                      "root_px": project_anchor(scene, co, rig, cam_cfg),
                                      "seconds": round(secs, 3)})
    (a.out / "render_log.json").write_text(json.dumps(log, indent=1) + "\n")
    print(f"render_actor: {len(log['frames'])} frames, "
          f"{sum(f['seconds'] for f in log['frames']):.2f} s rendering")


if __name__ == "__main__":
    main()
