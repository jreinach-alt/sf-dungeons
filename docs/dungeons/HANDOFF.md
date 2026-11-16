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
- **Art:** the downstream half is done and tested (pixelate, roles, actions
  data). The upstream half (Blender) is ported but **never run**.
- **ROM:** nothing yet. `game/dungeons` does not exist, and 08 M0 creates it.

## 3. Next, in order

1. **The model spike: `docs/dungeons/14_model_spike.md`.** Run locally, with
   Blender.
2. Fold the spike's verdict into 11 and 13.
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
