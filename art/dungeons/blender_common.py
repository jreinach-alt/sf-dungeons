"""blender_common.py — SuperForge Dungeons: the shared Blender plumbing.

Runs INSIDE Blender 4.2 LTS (`blender -b --factory-startup -P <script> -- …`).
Never imported by the build or the test suite: the build never runs Blender
(docs/dungeons/11 §1).

PORTED from SUPERFORGE GT (jreinach-alt/sf-gt @ 82add51; first-party, zlib):
  setup_scene / setup_compositor / aim / render_to   <- art/fgt/cars/render_car.py
  Kit / make_obj / finish_mesh / loft / box /
  ellipsoid / cyl / add_ground                      <- art/fgt/cars/carlib.py
The sf-gt originals rendered 1,848 car frames. THIS COPY HAS NOT YET BEEN RUN
in this repo — the model spike (docs/dungeons/14) runs it first, with
`check_blender.py`, and records the result. Changes from the originals are
marked `# DGN:` so a reviewer can diff the port.

What gets rendered is DATA, not a picture (sf-gt's contract): every material
is neutral clay and the compositor packs three planes into an 8-bit RGB PNG
with the view transform Raw:
    R = sunlight (direct light only, cast shadows included)
    G = material pass index (the palette ROLE, roles.toml)
    B = ambient occlusion (the open-sky share)
art/dungeons/actors/pixelate_actor.py turns those into indexed sprites.
"""
from __future__ import annotations

import math
import tomllib
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
ACTORS = HERE / "actors"
WORK = REPO / "build" / "dgn_art_work"     # scratch: never committed (sf-gt lesson)
MAT_NONE, MAT_SHADOW = 0, 1                 # reserved ids, as in pixelate_actor.py


def load_toml(name: str) -> dict:
    return tomllib.loads((ACTORS / name).read_text())


# ---------------------------------------------------------------------------
# scene, light, camera, compositor
# ---------------------------------------------------------------------------
def setup_scene(samples=2, threads=2, sun_dir=(0.0, 0.55, -0.83), seed=13):
    """sf-gt's repeatable rig: Cycles on the CPU, direct light only, a point
    sun, no denoiser, no dither, Raw view transform. `sun_dir` is the
    direction the light TRAVELS (DGN: a parameter; sf-gt fixed it on the car's
    centre line at 56 deg)."""
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    scene = bpy.context.scene
    r = scene.render
    r.engine = "CYCLES"
    c = scene.cycles
    c.device = "CPU"
    c.samples = samples
    c.use_adaptive_sampling = False
    c.use_denoising = False
    c.max_bounces = 0
    c.diffuse_bounces = 0
    c.glossy_bounces = 0
    c.transmission_bounces = 0
    c.caustics_reflective = False
    c.caustics_refractive = False
    c.seed = seed
    r.threads_mode = "FIXED"
    r.threads = threads
    r.use_persistent_data = True
    r.dither_intensity = 0.0          # the default 1.0 adds noise to the ids
    r.resolution_percentage = 100
    r.film_transparent = False
    r.image_settings.file_format = "PNG"
    r.image_settings.color_mode = "RGB"
    r.image_settings.color_depth = "8"
    r.image_settings.compression = 15
    scene.view_settings.view_transform = "Raw"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0
    bpy.context.view_layer.use_pass_material_index = True
    bpy.context.view_layer.use_pass_ambient_occlusion = True

    w = bpy.data.worlds.new("sky")
    scene.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (1, 1, 1, 1)
    bg.inputs[1].default_value = 0.0      # the sky's share comes from the AO plane
    sun = bpy.data.lights.new("sun", "SUN")
    sun.energy = 2.6
    sun.angle = 0.0                       # a point sun: crisp, repeatable shading
    so = bpy.data.objects.new("sun", sun)
    scene.collection.objects.link(so)
    so.rotation_euler = Vector(sun_dir).normalized().to_track_quat("-Z", "Y").to_euler()

    cam = bpy.data.cameras.new("cam")
    co = bpy.data.objects.new("cam", cam)
    scene.collection.objects.link(co)
    scene.camera = co
    cam.clip_start = 0.5
    cam.clip_end = 200.0
    return scene, co, so


def setup_compositor(scene):
    """R = BW(image), G = IndexMA / 255, B = BW(AO). Verbatim from sf-gt."""
    scene.use_nodes = True
    nt = scene.node_tree
    nt.nodes.clear()
    rl = nt.nodes.new("CompositorNodeRLayers")
    bw = nt.nodes.new("CompositorNodeRGBToBW")
    bw2 = nt.nodes.new("CompositorNodeRGBToBW")
    div = nt.nodes.new("CompositorNodeMath")
    div.operation = "DIVIDE"
    div.inputs[1].default_value = 255.0
    comb = nt.nodes.new("CompositorNodeCombineColor")
    comb.mode = "RGB"
    comp = nt.nodes.new("CompositorNodeComposite")
    nt.links.new(rl.outputs["Image"], bw.inputs[0])
    nt.links.new(bw.outputs[0], comb.inputs[0])
    nt.links.new(rl.outputs["IndexMA"], div.inputs[0])
    nt.links.new(div.outputs[0], comb.inputs[1])
    nt.links.new(rl.outputs["AO"], bw2.inputs[0])
    nt.links.new(bw2.outputs[0], comb.inputs[2])
    nt.links.new(comb.outputs[0], comp.inputs[0])


def aim(co, forward):
    co.rotation_euler = forward.to_track_quat("-Z", "Y").to_euler()


def set_actor_camera(scene, co, cam_cfg: dict, anchor_px):
    """DGN: sf-gt's set_tier_camera, for one fixed box. Orthographic at
    `depression_deg`, looking along +Y and down; the world ORIGIN (where the
    rig's root stands) lands on sprite pixel `anchor_px` = (x, y) of the box.
    Canvas = box + 2 * margin; resolution = canvas * supersample."""
    bw, bh = cam_cfg["box"]
    m, ss, s = cam_cfg["margin_px"], cam_cfg["supersample"], cam_cfg["px_per_unit"]
    W, H = bw + 2 * m, bh + 2 * m
    d = math.radians(cam_cfg["depression_deg"])
    scene.render.resolution_x = W * ss
    scene.render.resolution_y = H * ss
    cam = co.data
    cam.type = "ORTHO"
    cam.shift_x = cam.shift_y = 0.0
    cam.ortho_scale = max(W, H) / s
    f = Vector((0.0, math.cos(d), -math.sin(d)))      # forward
    u = Vector((0.0, math.sin(d), math.cos(d)))       # screen up
    cx, cy = m + anchor_px[0], m + anchor_px[1] + 0.5
    centre = Vector((1, 0, 0)) * ((W / 2 - cx) / s) + u * ((cy - H / 2) / s)
    co.location = centre - f * 40.0
    aim(co, f)


def render_to(scene, path):
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


# ---------------------------------------------------------------------------
# materials: one per palette role, tagged with a pass index
# ---------------------------------------------------------------------------
class Kit:
    """Role materials for one family of roles.toml (DGN: sf-gt hard-coded the
    car's roles). kit.mats[name] is the material whose pass_index is that
    role's material id; 'shadow' is always id 1."""

    def __init__(self, family: str):
        roles = tomllib.loads((ACTORS / "roles.toml").read_text())["family"][family]["role"]
        self.mats = {}
        for name, pid in [(r["name"], r["material"]) for r in roles] + [("shadow", MAT_SHADOW)]:
            m = bpy.data.materials.new("role_" + name)
            m.use_nodes = True
            m.pass_index = pid
            self.mats[name] = m
        self.root = bpy.data.objects.new("actor_root", None)
        bpy.context.scene.collection.objects.link(self.root)

    def set_mode(self, mode, colours=None):
        """'data': neutral clay whose brightness is the shading signal.
        'beauty': real colours, only for looking at the model."""
        for role, m in self.mats.items():
            b = m.node_tree.nodes["Principled BSDF"]
            if mode == "data":
                b.inputs["Base Color"].default_value = (0.8, 0.8, 0.8, 1)
                b.inputs["Metallic"].default_value = 0.0
                b.inputs["Roughness"].default_value = 0.7
                b.inputs["Specular IOR Level"].default_value = 0.2
                b.inputs["Coat Weight"].default_value = 0.0
            else:
                b.inputs["Base Color"].default_value = (*colours[role], 1)


# ---------------------------------------------------------------------------
# mesh plumbing (verbatim from sf-gt carlib.py except where marked)
# ---------------------------------------------------------------------------
def finish_mesh(me, smooth=38.0):
    for p in me.polygons:
        p.use_smooth = True
    me.set_sharp_from_angle(angle=math.radians(smooth))   # 4.2: use_auto_smooth is gone
    me.update()


def make_obj(kit, name, verts, faces, roles, smooth=38.0, parent=None):
    """roles: one role name, or a list with one role per face."""
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    if isinstance(roles, str):
        roles = [roles] * len(faces)
    used = []
    for r in roles:
        if r not in used:
            used.append(r)
    for r in used:
        me.materials.append(kit.mats[r])
    for p, r in zip(me.polygons, roles):
        p.material_index = used.index(r)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.to_mesh(me)
    bm.free()
    finish_mesh(me, smooth)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.parent = parent if parent is not None else kit.root
    return ob


def loft(rings, matfn, cap0=None, cap1=None):
    """Quads between consecutive closed rings. matfn(i, j) -> role."""
    n = len(rings[0])
    verts = [p for r in rings for p in r]
    faces, roles = [], []
    for i in range(len(rings) - 1):
        for j in range(n):
            a = i * n + j
            b = i * n + (j + 1) % n
            c = (i + 1) * n + (j + 1) % n
            d = (i + 1) * n + j
            faces.append((a, b, c, d))
            roles.append(matfn(i, j))
    if cap0:
        faces.append(tuple(range(n - 1, -1, -1)))
        roles.append(cap0)
    if cap1:
        base = (len(rings) - 1) * n
        faces.append(tuple(base + j for j in range(n)))
        roles.append(cap1)
    return verts, faces, roles


def box(kit, name, c, s, role, bevel=0.0, parent=None):
    """DGN: sf-gt's box() reduced to centre/size/role/bevel (no taper, shear,
    per-face roles or mirror — add them back from sf-gt if a part needs them)."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(s), verts=bm.verts[:])
    if bevel > 0:
        bmesh.ops.bevel(bm, geom=bm.edges[:], offset=bevel, segments=2,
                        affect="EDGES", profile=0.5)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(kit.mats[role])
    finish_mesh(me, 40.0)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.parent = parent if parent is not None else kit.root
    ob.location = c
    return ob


def ellipsoid(kit, name, c, r, role, zcut=None, parent=None):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=20, v_segments=12, radius=1.0)
    bmesh.ops.scale(bm, vec=Vector(r), verts=bm.verts[:])
    if zcut is not None:
        for v in bm.verts:
            if v.co.z < zcut:
                v.co.z = zcut
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(kit.mats[role])
    finish_mesh(me, 60.0)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.parent = parent if parent is not None else kit.root
    ob.location = c
    return ob


def cyl(kit, name, c, radius, depth, role, axis="Z", seg=14, parent=None):
    """A capped cylinder centred on c along `axis` (DGN: default Z, for limbs)."""
    ring0, ring1 = [], []
    for k in range(seg):
        a = 2 * math.pi * k / seg
        u, v = radius * math.cos(a), radius * math.sin(a)
        if axis == "Y":
            ring0.append((u, -depth / 2, v)); ring1.append((u, depth / 2, v))
        elif axis == "X":
            ring0.append((-depth / 2, u, v)); ring1.append((depth / 2, u, v))
        else:
            ring0.append((u, v, -depth / 2)); ring1.append((u, v, depth / 2))
    verts, faces, roles = loft([ring0, ring1], lambda i, j: role, cap0=role, cap1=role)
    ob = make_obj(kit, name, verts, faces, roles, smooth=50.0, parent=parent)
    ob.location = c
    return ob


def add_ground():
    """A dull ground plane with pass index 0: stops light from below, and the
    pixel pipeline treats it as empty. Verbatim from sf-gt."""
    me = bpy.data.meshes.new("ground")
    s = 40.0
    me.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
    m = bpy.data.materials.new("ground")
    m.use_nodes = True
    m.pass_index = 0
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.22, 0.22, 0.22, 1)
    b.inputs["Roughness"].default_value = 0.9
    me.materials.append(m)
    ob = bpy.data.objects.new("ground", me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def add_shadow_disc(kit, rx, ry, n=24):
    """DGN: a flat elliptical drop shadow (material 1) just above the ground,
    standing in for sf-gt's plan-outline shadow (a figure has no plan)."""
    verts = [(rx * math.cos(2 * math.pi * k / n), ry * math.sin(2 * math.pi * k / n), 0.004)
             for k in range(n)]
    return make_obj(kit, "shadow", verts, [tuple(range(n))], "shadow")
