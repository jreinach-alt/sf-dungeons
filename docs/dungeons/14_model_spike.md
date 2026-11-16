# 14 — The model spike (run locally, with Blender)

> **For:** the local Fable session that can drive Blender directly.
> **Question it answers:** can a script-built, rigged, keyed figure come out
> of Blender as a 16×16 SNES sprite that reads, holds its feet still, and
> fits the palette-role contract? This is the gap 13 names: sf-gt's pipeline
> only ever rendered rigid cars.
> **Scope:** the wanderer, `walk` only, all 3 directions, plus `idle`. No
> ROM work, no converter. Those come after the spike's verdict.

## 0. What is already in this repo for you

| path | what | state |
|---|---|---|
| `art/dungeons/blender_common.py` | scene, light, data-pass compositor, ortho actor camera, role materials, mesh primitives | **ported from sf-gt, never run here.** Changes from the original are marked `# DGN:` |
| `art/dungeons/check_blender.py` | renders one data frame of a box-and-head dummy | never run |
| `art/dungeons/actors/verify_smoke.py` | checks that frame: exact ids, size, pixelates it, reports the foot row | tested on synthetic frames |
| `art/dungeons/actors/pixelate_actor.py` | data frame → indexed sprite (ported from sf-gt) | 8 tests |
| `art/dungeons/actors/actions.toml` | camera, light, bones, the `walk`/`idle` key poses and timings | data; `anchor_px` is **provisional** |
| `art/dungeons/actors/roles.toml` | hero palette roles: material id → index | data |
| `art/dungeons/build_all.sh` | the stage runner (`smoke` exists) | |
| `docs/dungeons/13_character_pipeline.md` | the design: §3 is the `bpy` script, §4 the metrics | |
| sf-gt `art/fgt/cars/` | the working originals: `render_car.py`, `carlib.py`, `pixelate.py`, `sheets.py`, `build_all.sh` | read them; they rendered 1,848 frames |
| sf-gt `docs/fgt/dx_paper_cuts_cars.md` "Tooling" | the Blender lessons already paid for | read first |

## 1. Steps (stop and report at any red)

1. **Toolchain.** Blender 4.2 LTS at `~/toolchains/blender/blender`, or set
   `BLENDER`. Check with `$BLENDER -b --factory-startup --version`. Also run
   `python3 -m pytest tests/test_dungeons_pixelate.py tests/test_dungeons_model.py -q`,
   which should print 120 passed.
2. **Smoke.** Run `art/dungeons/build_all.sh smoke`. Expect `PASS` and
   `build/dgn_art_work/smoke_sprite_x8.png`, then look at it.
   - If it fails, fix `blender_common.py` against sf-gt's originals and
     record each fix as a paper cut (§4).
   - Then **set `actions.toml` `rig.anchor_px` from the measured foot row.**
3. **The wanderer.** Write `art/dungeons/actors/render_actor.py` per 13 §3,
   steps 1, 2 and 5:
   - build the body from parts on a `Kit("hero")`
   - build the armature with `rig.bones`
   - render `idle` frame 0, `right`
   - pixelate it and look at it at ×8
   - iterate on proportions until the silhouette reads as a cloaked traveller
     at 16 px
4. **Motion.** Add `key_action` and `set_direction` (13 §3 steps 3–4). Render
   `walk` (4 frames) × right/up/down, and `idle` (2 frames) × 3. That is
   18 frames.
5. **Metrics.** Write `sheets.py` (port sf-gt's) to emit:
   - a contact sheet: every frame ×8, with a grey preview palette and P1/P2
     ramps if `palettes.json` exists
   - `anchors.json`
   - 13 §4's metric table

   **Calibrate** the metric thresholds against what you actually see, and
   write the measured values into 13 §4.
6. **Commit the deliverables** (§3) on a branch and report (§5).

## 2. Rules carried from the repo

- **The build never runs Blender.** Commit the *indexed* PNGs, not Blender's
  raw frames. Raw frames stay in `build/dgn_art_work/` (ignored).
- **Never hash Blender's PNGs** for determinism, because they carry metadata.
  Hash the indexed outputs.
- **Shipped art comes from committed scripts.** Elyum images or videos may be
  used as **reference** (13 §6). They are never committed under `art/` and
  never traced.
- **Originality.** Nothing modelled on the source film's creatures (10 §5's
  "explicitly not used" list).
- **Tune data, not code.** Once the script works, a better stride is an
  `actions.toml` edit.

## 3. Deliverables

- `art/dungeons/actors/render_actor.py`, plus any `kit` helpers it grows.
- `art/dungeons/actors/frames/wanderer_{idle,walk}_{right,up,down}.png`:
  indexed strips, frames side by side, with index 0 transparent.
- `art/dungeons/actors/anchors.json` and the contact sheet PNG.
- `actions.toml` with a measured `anchor_px` and tuned key poses.
- `build_all.sh` with `render`, `pixelate` and `sheets` stages.
- 13 §4 thresholds replaced by measured values.

## 4. Paper cuts

Append friction to `docs/dungeons/dx_paper_cuts_spike.md`, in the sf-gt
format: **clunky / easy / surprise** × **HIGH / MEDIUM / LOW**. Things worth
recording:

- every fix the port needed
- Blender API surprises
- the render time per frame
- anything about skinning a cloak at 16 px

## 5. The report, and the verdict it must reach

Answer each question with evidence: frame images, the metric table, timings.

1. Does the walk **read** at 16 px in all three directions? Attach the
   contact sheet.
2. Do the feet hold still, with an anchor drift of 0?
3. Does the cloak skin cleanly, or does it need a rigid-segment fallback?
4. What is the render cost per frame, so the full roster can be
   extrapolated? 13 §3 implies about 33 hero frames plus swings × 5 bases.
5. **Go / adjust / no-go** for script-built animated figures, and if
   "adjust", what changes in 11 / 13.
