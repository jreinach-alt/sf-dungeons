"""check_blender.py — the model spike's step 1: does the ported plumbing run?

    blender -b --factory-startup -P art/dungeons/check_blender.py
    python3 art/dungeons/actors/verify_smoke.py      # then check what it wrote

Renders ONE data frame of a two-part dummy (a cloak box + a skin head on a
drop shadow) through blender_common's scene, compositor and actor camera, to
build/dgn_art_work/smoke_raw.png. verify_smoke.py then proves the G channel
carries exact role ids and runs the frame through pixelate_actor.

It has NOT been run in this repo yet (no Blender where it was written). If it
fails, fix blender_common.py — that is the point of running it first.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy  # noqa: E402
import blender_common as BC  # noqa: E402

act = BC.load_toml("actions.toml")
cam_cfg, light = act["camera"], act["light"]
print("blender", bpy.app.version_string)

scene, co, so = BC.setup_scene(samples=light["samples"], sun_dir=light["sun_dir"])
kit = BC.Kit("hero")
kit.set_mode("data")
BC.add_ground()
BC.add_shadow_disc(kit, 0.30, 0.22)
BC.box(kit, "cloak", (0.0, 0.0, 0.25), (0.40, 0.30, 0.50), "cloak", bevel=0.03)
BC.ellipsoid(kit, "head", (0.0, 0.0, 0.66), (0.16, 0.16, 0.16), "skin")
BC.setup_compositor(scene)
BC.set_actor_camera(scene, co, cam_cfg, act["rig"]["anchor_px"])
BC.WORK.mkdir(parents=True, exist_ok=True)
out = BC.WORK / "smoke_raw.png"
BC.render_to(scene, out)
print("wrote", out)
