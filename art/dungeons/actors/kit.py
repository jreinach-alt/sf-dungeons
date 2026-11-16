"""kit.py — SuperForge Dungeons: parametric parts and the rig, for figures.

Runs INSIDE Blender (imported by render_actor.py). The sf-gt `carlib` pattern
grown for animated figures (docs/dungeons/11 §3, 13 §3): parts are built at
their REST position in world space (the model faces -Y, toward the camera's
"down" view; z up; the ground is z = 0) and then bound to a bone, either
rigidly (`bind_rigid`) or by weights (`bind_skin`, for the cloak).

The pose convention every `actions.toml` channel uses:
    <bone>.pitch   degrees about the MODEL's +X axis, applied at the bone's
                   head in its parent's posed frame. +pitch tips an
                   up-pointing bone FORWARD (toward -Y) and swings a
                   down-pointing bone BACK: so +spine leans in, +shin bends
                   the knee, +cloak trails behind.
    <bone>.roll    degrees about the model's -Y axis (the facing axis).
    <bone>.z       units, a translation along world z (hips bob).
"""
from __future__ import annotations

import math

import bpy
from mathutils import Matrix, Quaternion, Vector

import blender_common as BC
from pose_data import action_values, channel_split  # noqa: F401  (pure; tested)

AXIS = {"pitch": Vector((1, 0, 0)), "roll": Vector((0, -1, 0))}


# ---------------------------------------------------------------------------
# parts: meshes with a palette ROLE per face
# ---------------------------------------------------------------------------
def sphere_parts(c, r, nu=16, nv=10):
    """UV-sphere rings (pole to pole) around centre c with radii r."""
    rings = []
    for i in range(1, nv):
        th = math.pi * i / nv                     # 0 = top pole
        z = math.cos(th)
        s = math.sin(th)
        rings.append([(c[0] + r[0] * s * math.cos(2 * math.pi * j / nu),
                       c[1] + r[1] * s * math.sin(2 * math.pi * j / nu),
                       c[2] + r[2] * z) for j in range(nu)])
    return rings


def shell(kit, name, c, r, rolefn, keep=None, nu=16, nv=10, parent=None):
    """A sphere-like shell with a role per face; `keep(centre) -> bool` drops
    faces (a hood's face opening). Poles are fans."""
    rings = sphere_parts(c, r, nu, nv)
    top = (c[0], c[1], c[2] + r[2])
    bot = (c[0], c[1], c[2] - r[2])
    verts = [p for ring in rings for p in ring] + [top, bot]
    it, ib = len(verts) - 2, len(verts) - 1
    faces = []
    for j in range(nu):
        faces.append((it, (j + 1) % nu, j))
    for i in range(nv - 2):
        for j in range(nu):
            a, b = i * nu + j, i * nu + (j + 1) % nu
            faces.append((a, b, b + nu, a + nu))
    base = (nv - 2) * nu
    for j in range(nu):
        faces.append((ib, base + j, base + (j + 1) % nu))
    out_f, out_r = [], []
    for f in faces:
        ctr = Vector([sum(verts[k][a] for k in f) / len(f) for a in range(3)])
        if keep is not None and not keep(ctr):
            continue
        out_f.append(f)
        out_r.append(rolefn(ctr))
    return BC.make_obj(kit, name, verts, out_f, out_r, smooth=60.0, parent=parent)


def limb(kit, name, a, b, radius, role, seg=10, cap=True):
    """A capped cylinder from point a to point b (a bone's rest span)."""
    a, b = Vector(a), Vector(b)
    axis = (b - a).normalized()
    q = Vector((0, 0, 1)).rotation_difference(axis)
    r0, r1 = [], []
    for k in range(seg):
        t = 2 * math.pi * k / seg
        o = q @ Vector((radius * math.cos(t), radius * math.sin(t), 0))
        r0.append(tuple(a + o))
        r1.append(tuple(b + o))
    v, f, r = BC.loft([r0, r1], lambda i, j: role,
                      cap0=role if cap else None, cap1=role if cap else None)
    return BC.make_obj(kit, name, v, f, r, smooth=50.0)


def bell(kit, name, rings_spec, arc_deg, rolefn, centre_y=0.0, seg=20):
    """An open cloak: rings (z, radius_x, radius_y) from the shoulders down,
    each an arc of `arc_deg` centred on +Y (the back), so the front is open.
    Single surface; Cycles shades both sides."""
    half = math.radians(arc_deg) / 2
    rings = []
    for z, rx, ry in rings_spec:
        ring = []
        for k in range(seg + 1):
            t = math.pi / 2 - half + 2 * half * k / seg       # +Y is the back
            ring.append((rx * math.cos(t), centre_y + ry * math.sin(t), z))
        rings.append(ring)
    n = seg + 1
    verts = [p for ring in rings for p in ring]
    faces, roles = [], []
    for i in range(len(rings) - 1):
        for k in range(seg):
            a = i * n + k
            faces.append((a, a + 1, a + 1 + n, a + n))
            roles.append(rolefn(i, k))
    return BC.make_obj(kit, name, verts, faces, roles, smooth=70.0)


# ---------------------------------------------------------------------------
# the armature
# ---------------------------------------------------------------------------
def build_armature(kit, spans: dict, parents: dict):
    """spans[bone] = (head, tail) at rest, world space; parents[bone] = name.
    Bones are named exactly as actions.toml's rig.bones (13 §3 step 2)."""
    arm = bpy.data.armatures.new("rig")
    ob = bpy.data.objects.new("rig", arm)
    bpy.context.scene.collection.objects.link(ob)
    ob.parent = kit.root
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    for name, (h, t) in spans.items():
        eb = arm.edit_bones.new(name)
        eb.head, eb.tail = Vector(h), Vector(t)
        eb.roll = 0.0
    for name, p in parents.items():
        if p is not None:
            arm.edit_bones[name].parent = arm.edit_bones[p]
            arm.edit_bones[name].use_connect = False
    bpy.ops.object.mode_set(mode="OBJECT")
    for pb in ob.pose.bones:
        pb.rotation_mode = "QUATERNION"
    return ob


def bind_rigid(rig, part, bone):
    """Parent a mesh to a bone without moving it (bone parents sit at the TAIL)."""
    bpy.context.view_layer.update()
    b = rig.data.bones[bone]
    tail = rig.matrix_world @ b.matrix_local @ Matrix.Translation((0, b.length, 0))
    mw = part.matrix_world.copy()
    part.parent = rig
    part.parent_type = "BONE"
    part.parent_bone = bone
    part.matrix_parent_inverse = tail.inverted()
    part.matrix_world = mw


def bind_skin(rig, part, weightfn):
    """Skin a mesh: weightfn(world_co) -> {bone: weight}. Deterministic,
    scripted weights (not bone-heat: see the spike's paper cuts)."""
    groups = {}
    for v in part.data.vertices:
        co = part.matrix_world @ v.co
        for bone, w in weightfn(co).items():
            if w <= 0:
                continue
            if bone not in groups:
                groups[bone] = part.vertex_groups.new(name=bone)
            groups[bone].add([v.index], w, "REPLACE")
    mw = part.matrix_world.copy()
    part.parent = rig
    part.parent_type = "OBJECT"
    part.matrix_parent_inverse = rig.matrix_world.inverted()
    part.matrix_world = mw
    mod = part.modifiers.new("rig", "ARMATURE")
    mod.object = rig
    mod.use_vertex_groups = True


# ---------------------------------------------------------------------------
# posing and keying
# ---------------------------------------------------------------------------
def pose(rig, values: dict):
    """values[channel] -> number, with the convention in the module doc.
    Bones with no channel return to rest."""
    for pb in rig.pose.bones:
        pb.rotation_quaternion = Quaternion()
        pb.location = Vector()
    rots = {}
    for ch, v in values.items():
        bone, kind = channel_split(ch)
        pb = rig.pose.bones[bone]
        if kind == "z":
            # world z -> the bone's local rest frame
            rest = pb.bone.matrix_local.to_3x3()
            pb.location = rest.inverted() @ Vector((0, 0, v))
        else:
            rest = pb.bone.matrix_local.to_3x3()
            ax = (rest.inverted() @ AXIS[kind]).normalized()
            rots.setdefault(bone, Quaternion())
            rots[bone] = rots[bone] @ Quaternion(ax, math.radians(v))
    for bone, q in rots.items():
        rig.pose.bones[bone].rotation_quaternion = q


def key_action(rig, name: str, act: dict, d: str | None = None):
    """One Blender Action per actions.toml action: frame i of the action is
    keyed at timeline frame i, CONSTANT interpolation (renders sample keys)."""
    rig.animation_data_create()
    a = bpy.data.actions.new(name)
    rig.animation_data.action = a
    for i in range(act["frames"]):
        pose(rig, action_values(act, i, d))
        for pb in rig.pose.bones:
            pb.keyframe_insert("rotation_quaternion", frame=i)
            pb.keyframe_insert("location", frame=i)
    for fc in a.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = "CONSTANT"
    return a


def set_direction(kit, cam_cfg: dict, d: str):
    """Yaw the ROOT (not the camera), so the light stays fixed on screen."""
    kit.root.rotation_euler = (0.0, 0.0, math.radians(cam_cfg["yaw_deg"][d]))
