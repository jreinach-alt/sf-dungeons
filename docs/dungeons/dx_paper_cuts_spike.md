# SuperForge Dungeons — DX paper cuts: the model spike (2026-11-15)

Scope: `docs/dungeons/14_model_spike.md`. The wanderer's `idle` and `walk`, all
three directions, from a script-built rigged figure in Blender 4.2.3 LTS to
committed indexed strips. Tags follow the sf-gt rubric: feeling (**clunky** /
**easy** / **surprise**) and cost (**HIGH** / **MEDIUM** / **LOW**).

## The port

- **easy / LOW — the ported plumbing needed no fixes.** `check_blender.py`
  ran first time through `blender_common.py` exactly as ported: scene, the
  compositor, `set_actor_camera`, `Kit`, the primitives. The G channel held
  only ids {0, 1, 2, 4}, so the material-index pass is exact, as sf-gt said.
  Smoke stage: 1.3 s wall, `PASS: foot row 14, declared anchor row 13`.
- **surprise / LOW — the smoke dummy's foot row is not the camera's anchor
  row, and should not be.** The dummy's cloak box is 0.30 u deep, and its
  near bottom edge lies `0.15 × sin 35° × 16 = 1.4` px below the root. A
  figure's feet sit under the root, and the wanderer measured 13 = the anchor
  row in all 18 frames. *Fix:* 14 §1 step 2 says to set `anchor_px` from the
  smoke frame's foot row. Read it as "from the figure's", or the anchor moves
  a row for a property of the dummy.
- **clunky / MEDIUM — sf-gt is not checked out beside this repo.** 14 §0 points
  at `sf-gt art/fgt/cars/` and the paper-cuts file. `gh` failed (a local forge
  shim at `127.0.0.1:3330` timed out), and a plain
  `git clone --depth 1 https://github.com/jreinach-alt/sf-gt` into the
  scratchpad worked. *Fix:* name the clone command in 14 §0.
- **clunky / LOW — `python3 -m pytest` fails as written in 14 §1.** The system
  Python has numpy and Pillow but not pytest. The venv is
  `~/SuperForge/.venv`, the same place sf-gt's paper cuts found it. With it,
  120 passed. *Fix:* 14 §1 could say `PY=~/SuperForge/.venv/bin/python`, or
  `tools/setup.sh` could be run once on this box.

## Blender API

- **easy / LOW — armatures build headless.** `bpy.ops.object.mode_set(mode="EDIT")`
  works under `-b --factory-startup` once the armature object is linked,
  active and selected. Edit bones take `head`/`tail`/`parent`, and that is all
  the rig needed.
- **surprise / LOW — a bone parent sits at the bone's TAIL.** A mesh parented
  with `parent_type = "BONE"` is placed relative to the tail, not the head.
  `kit.bind_rigid` sets `matrix_parent_inverse` from the tail's rest matrix
  and then restores `matrix_world`, so a part built at its world rest position
  stays put. It worked first time once that was known.
- **easy / LOW — pose channels as "rotation about a MODEL axis".** A pose
  rotation is in the bone's own rest frame, and bones here point up or down
  with arbitrary rolls. `kit.pose` conjugates: axis_local =
  `bone.matrix_local⁻¹ @ model_axis`. One convention (`pitch` about the model's
  side axis) then gives forward lean on the spine and a backward knee bend on
  the shin with the same sign, and the TOML's original key signs were already
  right under it.
- **clunky / LOW — automatic (bone-heat) weights were NOT used.** 13 §3 step 2
  asked for them. The body is separate part objects, which bone-heat would
  have to weight one by one (it is context-heavy and known to fail on
  disconnected or intersecting meshes). Rigid parts plus scripted weights are
  deterministic and reviewable. This was a choice, not a failure: heat
  weighting was not tried. Rigid limbs bind with `bind_rigid`, and the cloak
  binds with `bind_skin(weightfn)`, which weights by height: spine above the
  waist, a hips/spine blend, then `cloak.1` → `cloak.2` to the hem.
- **easy / LOW — the render is deterministic below the PNG wrapper.** The raw
  data frames from a 2-thread and a 6-thread run were pixel-identical (18 of
  18), and the indexed strips were byte-identical (md5).
- **easy / LOW — render time.** 192 × 192 raw frames (24 × 24 sprite px at ×8),
  Cycles at 2 samples, zero bounces, on an 8-core box at load average ~3:
  - 0.079–0.100 s a frame (mean 0.086 s) at 2 threads, and about 0.05 s at 6
    threads
  - the whole Blender process for 18 frames took 1.4 s wall, including
    startup and building the model
  - the full stage runner (render + pixelate + sheets) took 3.4 s

  Rendering is not the cost; Blender startup is.

## The figure at 16 px

- **surprise / MEDIUM — depth strides move the foot row.** In the up and down
  views the stride runs along the camera's depth axis, and depth projects onto
  screen y at `sin 35° × 16 = 9.2` px/unit. With the side view's ±30° stride,
  the leading toe sat a row below the passing frame's: the foot rows measured
  `[14, 13, 14, 13]`, a drift of 1, in both directions. *Resolved as data:*
  `[action.walk.dir.up|down]` tables replace the channels for that direction.
  The stride is ±8°, the knee lift is 60°, and a 10° `spine.roll` sway is
  added. Drift is now 0. This is what a sprite artist does anyway: a down-walk
  is drawn, not rotated.
- **surprise / MEDIUM — at 35° a bell cloak hides the stride in the side
  view.** The near half of the hem projects `r × 9.2` px below the hem's own
  height, about 2 px for a 0.23 u hem, which covers the legs. *Resolved:*
  - the hem rose from 0.13 to 0.19 u
  - the cloak opens 130° at the front (a 230° arc)
  - `cloak.1.pitch` trails hard (22/12°, lagged one sample)
  - the trousers moved to the cloak role, so the legs show dark against the
    brown tunic
- **surprise / LOW — the original walk keys lifted the support foot.**
  `hips.z = [0, 0.04, 0, 0.04]` raised the body at the passing frame, while the
  support leg was already straight. The keys are now `[-0.04, 0, -0.04, 0]`:
  rest = a straight 0.30 u leg on the ground, and contact drops by
  `0.30 (1 − cos 30°)`. The same drop on an 8° stride sank the feet 0.037 u
  into the ground. That was measured by probing the posed bones in Blender,
  because the sprite could not show it: the ground plane clips the feet.
- **surprise / MEDIUM — a metric that counts change rewarded a defect.** While
  the up-walk's feet were sinking into the ground on contact frames, its
  leg-row change read 15 px, comfortably "legible". Removing the sink dropped
  it to 5–6, because the leg rows had been counting legs being clipped. From
  behind, the cloak hides the legs, and the up-walk reads by the body sway.
  So the calibrated rule is a whole-frame change for every direction, plus a
  leg-row floor for right and down only (13 §4).
- **clunky / LOW — idle shimmer is mostly edge pixels at half cover.**
  A pixel 50% covered by the model flips in or out with any sub-pixel motion.
  The first idle had a 0.02 u hip dip and shimmered 40 px (over the 30 ceiling).
  A nod (`spine.pitch` + `head.pitch` 4°) measures 11–25, and the idle-down
  frame 1 is still 2 columns narrower than frame 0. That is legible as a
  breath, but it is the first place to look if idles boil on the floor.
- **easy / LOW — the cloak skins cleanly.** In ×8 data frames and in 320 px
  colour renders (`render_actor.py --inspect`), the skinned cloak deforms
  smoothly through 22° of trail with no tearing or flipped faces. The one
  interpenetration (the upper arms through the cloak's top ring) was a RIGID
  part. It showed only in the colour renders, never in a sprite, and was
  fixed by widening the shoulder ring. No rigid-segment fallback is needed at
  16 px.
- **easy / LOW — refuse-never-crop caught an untuned action.** A probe render
  of `downed` facing down (not committed) fell toward the camera, and
  `pixelate` refused it: `4 model px outside the 16x16 box (x 6..9, y 16..16)`.
- **clunky / LOW — the lantern and satchel are asymmetric, so the HFLIP for
  left moves them.** The lantern hangs on the right hip, so it faces the
  camera in the right view, and a flipped left-walk shows it on the near side
  too. That means a lantern that changes hips. actions.toml already accepts
  the flipped sun (`symmetric_for_flip = false`). At 16 px the lantern is one
  or two glow pixels, but the owner should know that it swaps.

## Harness

- **clunky / LOW — the Bash tool's working directory drifted.** A `cd` into
  `build/dgn_art_work` inside one compound command stuck for the next call.
  Every later command now starts with `cd <repo>`.

## On the console (2026-11-16)

- **surprise / HIGH — "the box has no tooling" was my PATH, not the box.**
  cc65 V2.19 is built from source at `~/toolchains/src/cc65/bin` and the
  pytest venv is `~/SuperForge/.venv`. Neither is on a non-interactive
  shell's PATH: `~/.bashrc` returns early for those, and nothing else sets
  it. So `tools/setup.sh` fell through to `sudo apt-get install cc65`, failed
  without a terminal, and the first `make bare-check` went RED with no ROM
  built. I reported that as missing tooling, and the owner rightly pushed
  back, because the SuperForge GT work builds on this box. *Fix:* a
  SessionStart hook in the git-ignored `.claude/settings.local.json` now
  prepends cc65 and a Python venv via `$CLAUDE_ENV_FILE`. Search the disk
  (`find / -xdev -name ca65`) before claiming a tool is absent.
- **surprise / MEDIUM — the borrowed venv lacks PyYAML, and the suite needs
  it.** With `~/SuperForge/.venv` first on PATH, the landing gate built
  every ROM and passed all 63 gates, but the suite ended with 4 failed and
  2,746 passed, all in `test_batch_union.py` (`No module named 'yaml'`).
  The system python3 has PyYAML but no pytest, and that venv has pytest but
  no PyYAML. `tools/setup.sh` checks only Pillow, pytest and xdist, so it
  never notices. *Fix:* a project venv at `~/toolchains/sf-dungeons-venv`,
  pinned to the same versions plus PyYAML 6.0.1, so the shared SuperForge
  venv is untouched. 38 of 38 `test_batch_union.py` tests pass under it.
  *Fix for the kit:* `setup.sh` should check for PyYAML too.
- **surprise / MEDIUM — import order segfaults the test collection.**
  `vendor/mesen_runner.py` dlopens MesenCore.so at import, and its own comment
  says it must do so before numpy's bundled libraries load. A test module
  that imports numpy or Pillow before `machine` dies with a SIGSEGV inside
  `ctypes`, during collection, with no test named. A scratch script that
  happened to import `machine` first worked, which made it look like a box
  problem. *Fix:* `test_dgn_hero.py` imports `machine` first, with the
  reason. A lint for this ordering would have saved the detour.
- **easy / LOW — the rail gates teach as AGENTS.md promises.**
  `make rail-registered` named nine missing sites, then the tenth (the
  freshness-guard dict) once the others were in. `make register` named the
  two §3.1 lines. Each refusal said exactly where and why.
- **surprise / LOW — `tick-check` reads "frame" and "clock" as video
  frames.** It flagged the animation-frame indices (`idle_i`, `walk_i`) and
  the converter's CHR band size. Each got a reasoned `TICK: ok` override;
  the genuinely frame-coupled words (the hold countdowns) already had one.
- **easy / LOW — the screenshot geometry is already written down.**
  `tests/frame_geometry.py`: Mesen's PNG is 256×239 with picture row 0 at PNG
  row 7, so an OBJ at OAM Y draws from PNG row 7 + Y. The pixel-exact crop
  test holds with exactly that mapping.
- **easy / LOW — Pillow merges identical consecutive GIF frames**, summing
  their delays, so the lineup close-up's 96 captures save as 42 frames at
  the same real-time length.
