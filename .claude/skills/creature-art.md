---
name: creature-art
description: Make a new SuperForge Dungeons creature (enemy, boss, hero variant) as sprite art: write its SPEC, build it in Blender, paint it, review it, check its console budget. Trigger when asked to add or change any animated figure's art.
---

**The idea (docs/dungeons/16).** A creature is a *data file*. You do not model in a GUI or
key frames by hand. You write `art/dungeons/creatures/specs/<name>.toml`; a generic builder
makes the parts, an IK rig, and the animation from gait / pose instructions; a painter turns
the render into pixel-art; budget tools say whether it fits the console. **You are the
art director and the pixel artist: the loop is build, LOOK, change the data, repeat.**

## The commands
```bash
art/dungeons/creatures/build_creature.sh <name> [--dirs right,down] [--actions a,b]
python3 art/dungeons/creatures/scene.py          # hero + spider + boss in the Hollow Wood, with a CRT view
python3 -m pytest tests/test_dungeons_creatures.py -q
```
It validates the spec first (a sentence, not a traceback), renders in Blender (seconds), paints,
and writes `art/dungeons/creatures/out/<name>/`: `sheet.png` (every frame, scaled), `anim_<dir>.gif`
(game timing), `budget.json`, the indexed strips and `palettes.json`. Set `PATH` to include
`~/toolchains/src/cc65/bin` and `~/toolchains/sf-dungeons-venv/bin` (the SessionStart hook does).

## The spec, by example (read `specs/spider.toml`, then `specs/tortoise.toml`)
- `family`: a table in `actors/roles.toml` (material id -> palette index, ramp thresholds). A new
  creature kind needs its role table first; ramps are 2-5 steps, fixed roles are single colours.
- `size_class`: `obj16 | obj16x32 | obj32 | obj64 | bg` (`budget.py`). `camera.box` must match an
  OBJ class; a BG boss may be any whole-tile size up to the 32x32 map.
- `[[bone]]`, then `[[part]]`: `ellipsoid | limb | box | cone | tube | dome`, each with a `role` and
  a `bone` (rigid binding). `mirror = true` makes the x-mirrored twin. `dome` takes `seam_role`: the
  hex-scute pattern is TWO ROLES, so the pattern is painted detail and not shading.
- `[[legset]]`: an IK limb set. Give tags, a hip and a home foot per leg; it generates the two bones,
  the knee, the IK target, the pole (its roll is FITTED against the rest pose), the meshes, a joint
  ball, optional `pad` and `claws`. List the legs in the order the gait expects (see `gaits.py`).
- `[action.<n>]`: `type = "keys"` (bone channels: `<bone>.pitch|roll|yaw|x|y|z`), `"gait"` (a leg set
  + `gait = tetrapod|walk4|trot4|biped`, stride, lift, duty, bob) or `"poses"` (channels plus a foot
  instruction per leg per frame: `"home"`, `"plant"`, `[x,y,z]`, `{home=[dx,dy,dz]}`). **Use `plant`
  for any foot that is on the ground: it stays fixed in the world while the body moves. That is how a
  tortoise rises without its hind feet sliding.** Positive `pitch` is nose DOWN.
- `[paint]`, `[ramp.*]`, `[palette] base = [15 colours]`, `[[stamps]]` (hand-drawn pixels at a
  `[[locator]]`), `[override.<action>_<dir>_<n>] px = [[x,y,idx],...]` (the hand-cleanup layer).

## The review loop (do this EVERY time; it is the quality)
1. `build_creature.sh`, then READ `out/<name>/sheet.png`. Do not trust the numbers alone.
2. Judge it in context: `scene.py`. **A palette that looks right alone can vanish in its biome** (a
   green boss on a moss floor, teal on moss, amber on bark). Distinct HUE from the floor first.
3. Read `budget.json`: OBJ classes show tiles, OAM entries and slivers per line (34 per line total,
   02 §3); a BG boss shows unique tiles per pose against 320 and the tiles each pose change must
   stream against 5,952 B in one VBlank.
4. Dump indices (`print rows as hex`) when a detail "is missing": a stamp can hide inside the
   material it was placed on (it did).
5. When the painter fails locally, fix pixels in `[override.*]`, not in code. When it fails
   everywhere, change the rule or the data, then re-run.

## Mistakes already paid for
- **Refuse-never-crop** will name the pixel that leaves the box. The fix is data: anchor, a radius,
  a stride, a key. A lunge needs headroom in front: give that action its own `anchor`.
- **Thin parts** (spider legs) are drawn as clean lines: `no_outline = ["leg"]`. An outline ring
  around a 2-px limb turns it to mush.
- **Foot rows differ by facing** because feet are separated along the camera's depth axis; publish
  the ROOT row as the anchor, not a foot row (docs 14 §6.2).
- **A forward swing foreshortens**: key sideways motion with `roll`, not `pitch`, for the front view.
- **Do not `rm -f $VAR/*`** (the safety check refuses an unset-variable expansion); renders overwrite.
- **Planting a defect to prove a test**: clear `__pycache__` if the edit keeps the file's length.
- Tests that import numpy must import `machine` first (MesenCore load order).

## What this pipeline does NOT do (say so in the report)
Generated 3D (TRELLIS and kin) is not used: 24 GB is needed and the output has no role map or rig.
Weapons as their own layer, an `up` facing for creatures, sub-tile BG tile reuse and a per-frame
hand-cleanup pass are not built. Nothing is measured on a ROM until a rail exists for it.
