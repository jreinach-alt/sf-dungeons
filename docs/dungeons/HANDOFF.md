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
- **ROM:** `game/dgn_hero` (2026-11-16) is the spike's on-console proof: the
  committed wanderer frames as resident 16×16 OBJs, animated on
  `actions.toml`'s holds, with the P1/P2 palettes (14 §6.1,
  `tests/test_dgn_hero.py`). It is not the game: `game/dungeons` does not
  exist yet, and 08 M0 creates it. `tools/gen_dgn_hero_assets.py` is the
  first slice of 11 §5 stage 6 that M3's converter grows from.

## 3. Next, in order

1. ~~The model spike~~: done; see 14 §6 and `dx_paper_cuts_spike.md`.
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
