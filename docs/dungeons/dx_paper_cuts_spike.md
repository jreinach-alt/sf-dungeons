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

## The 16x32 retry (2026-11-17)

- **surprise / MEDIUM — the foot-row metric assumed a symmetric stance.** In a
  side view the near foot is lower by the stance's depth separation (~1.7 px
  here), so "the lowest row is the same in every frame" failed on a correct
  walk the moment a near foot lifted. Fixed by defining drift over the
  grounded frames only and publishing the root row, not a foot row (14 §6.2).
  The 16x16 set had passed by luck of a smaller stance.
- **surprise / LOW — a pixel-boundary anchor makes a metric flicker.** The
  boot edge sat at ~29.2, so a sub-pixel stride toggled the foot row. A
  fractional `anchor_px` (27.6) moved it mid-pixel. `set_actor_camera` already
  accepts floats; the TOML just had never needed one.
- **clunky / LOW — `np.roll` wraps, and sprites touch row 0.** My planted
  defect rolled the hood tip onto the bottom row and reported a 3-row drift
  instead of 1. Plants on pixel data must shift, not roll.
- **easy / LOW — the pipeline really was box-generic.** Only the smoke
  verifier's test hard-coded a square canvas; everything else followed
  `camera.box`.
- **easy / LOW — a tall box is two OBJs, and that is cheap.** See 14 §6.2:
  OAM slots, not scanline budget.

## The art-direction spike (2026-11-17)

- **surprise / HIGH — an acceptance criterion hid in context.** "Distinct from
  scenery and enemies" cannot be judged on a sheet. On a grey sheet all three
  treatments looked fine; in the room, B's teal vanished into moss and P2's amber
  was the same hue as the floor's bark and the Rootling. Three palette fixes
  followed. *Fix:* judge every treatment in its own biome before anything else.
- **surprise / MEDIUM — a stamp hid inside what it was placed on.** The face
  glints were drawn with the hood rim's own palette index on the rim's own row, so
  they were invisible and I judged "no eyes" for two rounds. An index dump
  (`print the rows as hex`) found it in one look. *Fix:* the stamps now sit a
  row down in the void, and when a detail "is missing" dump the indices before
  re-tuning anything.
- **surprise / MEDIUM — my first planted defect was not caught.** Disabling the
  cluster passes left every test green, because the shading blur (and the
  bridge-line rule) folded the orphan pixel anyway. The test now runs with
  smoothing off so the cluster stage is the only defence, and the plant is the
  stage's call site. A test that survives its own plant is not a test.
- **clunky / MEDIUM — 16 px is tight, and refuse-never-crop kept refusing.**
  About a dozen times a pleat, a satchel, a stride or a sword's wind-up put one pixel
  outside the box. Each refusal named the pixel, and the fixes were data
  (anchor x, a radius, a key). *Fix for the pipeline:* `render_style.py` could
  print the figure's bounding box per frame so the anchor is chosen once.
- **clunky / MEDIUM — joint signs are found by probing, not reasoning.** The
  front-view slash needed `roll`, not `pitch` (a pitch swing foreshortens toward
  the camera), and the signs came from rendering six candidate poses in one
  go (a 6-frame probe style, `styles/_probe.toml`). *Fix:* keep the probe as a
  tool; it cost one render where guessing cost four.
- **easy / LOW — `set_actor_camera` overwrites the resolution**, so an inspect
  render set earlier came out at the sprite size. Set it after the camera.
- **easy / LOW — the safety check blocked `rm -f $W/*.png`** (an unset `$W` would
  expand to `/`). The deletion was unnecessary: renders overwrite their
  outputs. If one is ever needed, `"${W:?}"/*.png` is the form it accepts.
- **easy / LOW — the pipeline is fast enough to iterate:** three treatments, 18
  frames each, rendered, painted, composed into rooms and animated in 20 s; one
  Blender frame is about 0.15 s.
- **easy / LOW — the same data-pass contract carried a very different style.**
  Nothing in `blender_common`, the compositor or `pixelate_actor.fit` changed for
  the painter: the look lives entirely in the stage after the render.

## The creature pipeline (2026-11-17)

- **surprise / HIGH — the "hard" parts were the cheap ones.** IK legs on a tetrapod gait, and a body
  that rises over planted feet, were each a few lines of spec once the generators existed; the pole
  angle that keeps a knee bending the right way is *fitted* against the rest pose (four candidates,
  nearest wins) and never needed hand-tuning. The expensive part is the same as always: judging it
  by eye and fixing the palette, the anchor and the face.
- **surprise / MEDIUM — my own gait table was wrong and a test caught it.** I listed the 4-leg walk as
  FL, FR, HL, HR with phases that put a hind foot after the *same-side* front foot. The lateral
  sequence is FL, HR, FR, HL. A test that asserts the order the feet LEAVE the ground found it.
- **surprise / MEDIUM — stale bytecode survived a restored plant.** Swapping two numbers does not change
  a file's length, and a restore inside the same second keeps the old mtime pair, so Python kept the
  planted `.pyc`. CLAUDE.md records the same class for `make` (`copy2` keeps mtime). *Fix:* clear
  `__pycache__` after a plant; a harness that does not is reporting its own residue.
- **clunky / MEDIUM — Blender inspect renders cost 40x what they should.** 10 pixels per sprite pixel at
  24 samples on a 128 px canvas ran past 400 s; 4 and 4 gave 11 s. Inspect resolution and samples are
  now arguments (`--iscale`, `--isamples`).
- **clunky / LOW — the painter had hero names baked in** (outline tables, tiny-feature protection, the
  contact order). Making it family-agnostic had to keep the hero's output byte-identical; the check
  was `git status` on the committed hero strips, and it caught that my first repaint loop hid an
  error behind `>/dev/null`. Never silence the thing you are checking.
- **easy / LOW — a new size class is a table row.** `budget.SIZE_CLASSES` plus a role family is all a
  new kind of creature adds to the code; everything else is data.

## The four briefed enemies (2026-11-17)

- **surprise / MEDIUM — two keys on one bone overwrote each other.** `flame.scale` and `flame.stretch`
  on the same bone: the second assignment won, so a flame meant to vanish stretched sideways into a
  blue disc. Found by LOOKING at the sheet, not by any test; the fix (multiply) is now generic and the
  skill file says so. A channel-combination rule belongs in a test next time.
- **clunky / MEDIUM — one anchor per action serves both facings.** Every one of the four creatures
  needed a hand-tuned attack anchor, because a lunge toward the camera needs room below and a lunge to
  the side needs it in front. *Fix:* per-facing anchors in the spec, or have `creature.py` print the
  per-frame bounding box so the anchor is chosen once.
- **surprise / MEDIUM — negative space needs geometry.** Crownling's closed dome erased the gaps between
  its points; an open band with a shallow hollow restored the crown. At 32×32 the *gaps* are the detail.
- **clunky / LOW — the bestiary's tile budget was first reported for one facing only.** `report.py`
  defaults to `down`; the both-facings cost is roughly double (36.5 KB for four, not 18). A budget
  tool should say which facings it counted.
- **easy / LOW — a 600-line spec is fine when it is generated.** Crownling's 12 tendril bones and 24
  parts were emitted by a short script; the committed TOML stays plain data. If a creature wants many
  repeated limbs, a `chain` generator in the spec (like `legset`) is the next shorthand to add.
- **easy / LOW — silhouette-first design worked.** One mass plus one accent colour per creature made them
  separable before shading (17 §5.4).
