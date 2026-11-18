# SuperForge Dungeons — handoff (2026-11-16)

For whoever picks this up next: where things are and what is next. This
follows the shape of sf-gt's `docs/fgt/HANDOFF.md`.

## 1. Where everything is

| | |
|---|---|
| This repo | `jreinach-alt/sf-dungeons`: the SuperForge kit (full history, as of `aee087f`) plus SuperForge Dungeons. The kit's own front page is `KIT.md`; the game's is `README.md` |
| The specs | `docs/dungeons/00_README.md` → 01–14, `research/`, this file |
| The reference models | `tools/dungeons/` (PRNG, level generator, loot) and their data. `tests/test_dungeons_model.py` |
| The art pipeline | `art/dungeons/` (see its README). Ported from sf-gt's `art/fgt/cars/` |
| The sibling | `jreinach-alt/sf-gt` (SUPERFORGE GT): the source of the art pipeline, the frame streaming precedent, and the audio synthesiser. Read it; do not merge it |

## 2. State

- **Specs:** a draft is complete. The open questions are in 09 (Q3–Q7, Q9,
  Q10).
- **Models:** the level generator, PRNG and loot roller are done and pinned
  (111 checks, incl. the template linter).
- **Art:** the model spike ran (2026-11-15) and its verdict is **GO, with
  adjustments** (14 §6). The wanderer's `idle` + `walk` × 3 directions are
  rendered, rigged and keyed by `art/dungeons/actors/render_actor.py`, and
  committed as indexed strips in `art/dungeons/actors/frames/`. All of 13 §4's
  metrics pass, with drift 0, and they are recalibrated on the measured
  values. `build_all.sh` has the render, pixelate and sheets stages.
  `roll` / `hurt` / `downed` / `swing` are not yet tuned.
- **ROM:** `game/dgn_hero` (2026-11-16; re-done at 16x32 on 2026-11-17, see
  14 §6.2) is the spike's on-console proof: the
  committed wanderer frames as resident 16x32 figures (two stacked 16x16 OBJs), animated on
  `actions.toml`'s holds, with the P1/P2 palettes (14 §6.1,
  `tests/test_dgn_hero.py`). It is not the game: `game/dungeons` does not
  exist yet, and 08 M0 creates it. `tools/gen_dgn_hero_assets.py` is the
  first slice of 11 §5 stage 6 that M3's converter grows from.

## 2.1 The art-direction spike (2026-11-17), awaiting the owner

14's sprites met the technical bar and not the vision. `docs/dungeons/15` has
three treatments (A storybook, B practical-effects, C painted 16-bit) built over
a new painterly stage, judged in a mock Hollow Wood room. **Do not start the
character system, or change 11 / 13, until the owner chooses (15 §9).**
Run it: `art/dungeons/style/build_style.sh`.

## 2.2 The creature pipeline (2026-11-17)

`docs/dungeons/16`: a creature is now a data file (`art/dungeons/creatures/specs/`). Proven on a 32×32
spider (8-leg IK skitter, bite) and a 112×112 BG tortoise boss that plods, rises onto its hind feet
and stomps, with tile budgets measured. Agent manual: `.claude/skills/creature-art.md`. **Owner
decisions are in 16 §7 (the quality ceiling, what to build next, size classes).**

## 2.3 The four briefed enemies (2026-11-17)

`docs/dungeons/17`: Bellwretch, Thornhopper, Candlemaw and Crownling, built from the owner's brief
(`docs/dungeons/refs/`, reference only) with the creature pipeline. ~36.5 KB of OBJ CHR for all four, both
facings. None has had a hand-cleanup pass; Crownling needs it most. Decisions are in 17 §6.

## 2.4 The boss-battle scene (2026-11-18)

`docs/dungeons/18` and `game/dgn_boss`: a 64×64 boss (four 32×32 OBJs, streamed), two players with attack
frames (streamed) and two small enemies (resident) on the console, with the V counter and STAT77 read back
every frame. The first obj_stream-shaped code in the tree, hand-rolled; **no scheduler and no deadline guard
yet (18 §3.2)**. Decisions are in 18 §6.

## 2.5 The choreographed boss fight (2026-11-18)

`docs/dungeons/19` and `game/dgn_fight`: the boss moves about the arena through a slam, a slam and a whirl; player 1
chases and attacks from three sides, backing away from each; player 2 duels two small enemies. The scene is a
**score** compiled by `tools/dgn_fight/director.py`, which prefetches every streamed frame into a back buffer
and proves the per-tick DMA load; the ROM only plays it back. Worst VBlank ends on 235 (hybrid 241) against 260
unchoreographed. **Read 19 §4.1: the commit before this one broke `make microzero` (a cross-rail lint hazard);
fixed in `4abbecd`. `make bare-check` has NOT been run on the tip.** Decisions are in 19 §7.

## 3. Next, in order

1. ~~The model spike~~: done; see 14 §6, §6.1 (console) and §6.2 (16x32,
   which supersedes the 16x16 numbers; those are archived). **Open decision:
   the hero size (16x32 recommended) and the metatile/actor scale, 02 and 11.**
2. Fold the spike's verdict into 11. 13 already carries it: the §3 as-built
   notes and the §4 calibrated metrics. Then tune `roll` / `hurt` / `downed`
   (per-direction tables; `downed` facing down is refused today) and write
   `gen_palettes.py` (P2's face contrast, 14 §6).
3. 08 M0 → M1 → M2 (scaffold, `rng`, generator + `tiles16`), alongside art
   track A1 continuing from the spike.

## 4. What was deliberately left in sf-gt

None of the following applies to Dungeons, so none of it was copied:

- the racing game (`game/forge_gt`) and its 36 `engine/features` entries
- the cars, tracks, skies, UI art and their converters (`tools/fgt/*`)
- its audio project, and its tests

Read it there when its pattern is wanted:

- the frame streaming, for `obj_stream`
- `tools/fgt/gen_audio_samples.py`, for 12 §3
- `art/fgt/ui/quantize.py`, for menu backdrops
