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

## 6. Result (2026-11-15): **GO, with adjustments**

Run on Blender 4.2.3 LTS, headless, on an 8-core box. Branch
`dungeons/model-spike`. Everything below is reproduced by
`art/dungeons/build_all.sh` (render → pixelate → sheets, 3.4 s) and pinned
without Blender by `tests/test_dungeons_frames.py`. The friction is in
[`dx_paper_cuts_spike.md`](dx_paper_cuts_spike.md).

**Evidence:** [`art/dungeons/actors/sheet_wanderer.png`](../../art/dungeons/actors/sheet_wanderer.png)
shows all 18 frames at ×8, in grey roles and in P1/P2 preview tones. The
numbers are in `metrics.json` and `anchors.json` beside it, and the
thresholds are in 13 §4.

| action | dir | foot rows | drift | root agree | shimmer | walk frame px | walk leg px |
|---|---|---|---|---|---|---|---|
| idle | right | [13, 13] | 0 | 0 | 23 | - | - |
| idle | up | [13, 13] | 0 | 0 | 11 | - | - |
| idle | down | [13, 13] | 0 | 0 | 24 | - | - |
| walk | right | [13, 13, 13, 13] | 0 | 0 | - | [49, 47, 47, 50] | [17, 19, 19, 18] |
| walk | up | [13, 13, 13, 13] | 0 | 0 | - | [28, 29, 30, 29] | [5, 6, 6, 5] |
| walk | down | [13, 13, 13, 13] | 0 | 0 | - | [54, 54, 47, 52] | [13, 14, 9, 15] |

All 7 roles are covered, and every ramp step is used.

1. **Does the walk read at 16 px?** It reads in the right and down views:
   - **Right:** the leading leg shows through the open cloak front, and the
     hem trails a frame behind the body.
   - **Down:** blue legs against the brown tunic, a boot lifted on each
     passing frame, and a 1 px sway.
   - **Up:** it reads weakest. From behind the cloak hides the legs, and the
     walk reads only by the sway and the hem; 28–30 px change per frame,
     and only 5–6 of it in the leg rows.

   The side view needed the cloak opened and trailing hard: a closed bell
   at 35° hides the stride.
2. **Do the feet hold still?** Yes. The drift is 0 in all six strips, the
   foot row is 13 everywhere, and it equals the projected root row.
   `anchor_px = [8, 13]` is now measured, not provisional. It took
   per-direction key tables, because a full stride along the depth axis
   moved the foot row by 1.
3. **Does the cloak skin cleanly?** Yes, with scripted height weights on a
   `spine → hips → cloak.1 → cloak.2` chain. It deforms through 22° of trail
   with no tearing, in the sprites and in 320 px colour renders
   (`render_actor.py --inspect`). **No rigid-segment fallback is needed.**
   The limbs are rigid parts by design, which at 16 px is invisible.
4. **Render cost:**
   - 0.079–0.100 s a frame (mean 0.086 s) at 2 threads, about 0.05 s at 6
   - 1.4 s wall for an 18-frame Blender process, including startup and
     building the model

   The roster 13 §3 implies is 33 hero frames (11 per direction) plus
   45 swing frames (3 × 3 directions × 5 bases), 78 in all. That is about
   7 s of rendering, about 15 s of wall per process including startup.
   Enemies at the same size cost the same per frame. Rendering is not a
   constraint, and the spike's cost was iteration by eye. Output is
   deterministic: 2 vs 6 threads gave pixel-identical raw frames and
   byte-identical strips.
5. **Verdict: GO** for script-built, rigged, keyed figures. **Adjust** 11
   and 13 as follows (13 §3/§4 already carry the as-built notes and the
   calibrated metrics; 11 is the next step):
   - **Directions are drawn, not only rotated.** `[action.<a>.dir.<d>]`
     tables override channels per direction. Any stride, lunge or roll along
     the depth axis moves the foot row at 9.2 px/u. 11 §2 should say so
     beside "yaw at 0/90/180".
   - **Skinning is scripted and only for cloth.** Rigid parts are bound to
     bones, and only the cloak is skinned, with code-defined weights.
     Bone-heat "automatic weights" (13 §3 step 2) are dropped.
   - **Cloth must clear the legs at 35°.** The hem should sit at ≥ 0.19 u,
     with an open front and a hard trail. 11 §3's "hooded cloak" entry
     should carry this.
   - **The walk-legibility metric is per direction**, and the back view has
     no leg-row floor (13 §4 explains why a change count can reward a
     defect).
   - **The rest of the action set is untuned.** A probe render (not
     committed) showed:
     - `roll` keyed on `spine.pitch` pivots at the waist and is a blob in
       up/down. It wants `hips.pitch` (the whole body) and per-direction
       tables.
     - `downed` facing down falls toward the camera, and `pixelate` refuses
       it at 4 px out of the box.
     - `hurt` fits.

     These are data edits for the next art session.
   - **P2 needs contrast at the face.** In the preview, P2's amber cloak
     ramp swallows the skin ramp under the hood. `gen_palettes.py`
     (11 §5 stage 1) must keep the hood's lit step and the skin's lit step
     apart.
   - **The lantern swaps hips on the HFLIP.** The hero is asymmetric (a
     lantern on the right hip, a satchel on the left). This is accepted like
     the flipped sun, and noted for the owner.
