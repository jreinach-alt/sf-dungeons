# 08 — Milestones (the build order for the implementing agent)

> Each milestone is **independently shippable and independently testable**.
> Every one closes on the same bar:
>
> 1. The ROM builds, and `make <rail>` + `make rail-registered` +
>    `make register` + `make width-check` are green.
> 2. The milestone's tests **read rendered output**: VRAM, OAM, CGRAM, or a
>    screenshot at an absolute frame. They never read a proxy variable
>    (CLAUDE.md rule 2).
> 3. A **fresh render from the built binary** is attached to the report
>    (rule 3).
> 4. Every **(est.)** number the milestone relies on has been **measured**,
>    and the measurement is written back into the spec.
> 5. `make bare-check` is green on the pushed tip, and `build/bare_check.json`
>    is cited.
>
> Work in ≤50-line ASM / ≤30-line Python steps, building and testing as you
> go. Never write more than 100 lines without a build.

## M0 — Scaffold (`game/dungeons`)

- Fork `game/microzero`'s shapes, per `docs/lessons/04`.
- Scenes: `title`, `camp`, `map`, `level`, `results`. Each starts as a
  `bg_text` + `backdrop` card naming its gap ("GAP: GENERATOR").
- Compose `region` + `tick_scale` + `input` + `input2` from day one.
- **Test:** boot, press Start, walk the card chain title → camp → map →
  level → results → camp, reading each card's BG3 cells.

## M1 — `rng` feature + seed capture

- Write `engine/features/rng`: xorshift16 per 03 §2.2, two DP states, with no
  `[init] zero` (the seed is explicit).
- Record a **measured** cycle count in its `feature.toml`.
- `run_seed` = `sm_frame` sampled at the title press, forced nonzero.
- The map's embark card prints `SEED XXXX`.
- **Tests:**
  1. Under lockstep `Machine`, press Start on frame F. The card's glyph
     cells spell the seed the oracle derives from F.
  2. A probe prints 4 draws from state 1. The glyphs must read
     `8181 6021 E999 2E0B`.

## M2 — Generator + `dgn_bg` (the first `tiles16` rail)

- Extend the oracle first: `levelgen.tilemap(lv)` (03 §4.2 autotiling), and
  a template-blob packer in `tools/gen_dungeons_assets.py` that runs
  `lint_templates`.
- ASM `dgn_gen` (role `game_logic`) runs in `level::enter` under forced blank
  with NMI masked, then DMAs the 8 KB tilemap.
- **Tests:**
  - For seeds {1, `$BEEF`, `$1234`} × threat steps {0, 4, 8}:
    - The VRAM BG1 tilemap equals `tilemap(lv)` word for word.
    - The WRAM map equals `lv.tiles`.
    - The spawn table equals `lv.spawns`.
    - The GEN draw count equals `lv.draws`.
  - The CHR quad layout, read from VRAM.
  - **Measure** the generation time in frames. The target is under 30.
  - A screenshot.

## M3 — Two heroes, two cameras, merge/split (the proven seam first)

- Heroes are **resident** in OBJ name table 0 (02 §1.2), with movement and
  foot-box collision per 05 §1.
- **Split screen, step 1: the proven vertical seam** (06 §2.3's fallback),
  with **2-axis** cameras.
  - Port the `split_v_bg` mechanism to `dgn_bg`: BG2 points at BG1's map and
    CHR; window 1 is the seam; window 2 is the divider band, masking BG1, BG2
    and OBJ over the backdrop ink.
  - The merge/split ramp and hysteresis are per 06 §2.4.
  - Actors are drawn once, in their half (06 §2.6).
- **Tests:**
  - **Merged:** BG1 and BG2 scroll registers are equal, and a screenshot has
    no visible seam. Diff the two halves' boundary columns against a merged
    reference.
  - **Split:** drive the pads apart for 300 frames. Each hero's OAM position
    lies inside its own half on every frame. The scroll registers equal the
    oracle's camera A/B for those positions. The divider band's columns are
    the backdrop colour in the screenshot.
  - **Re-merge:** walk back together. The registers converge, and the
    hysteresis holds (no flip-flop over 120 frames at the threshold).
  - **Collision invariant:** 600 frames of scripted input into walls. On
    every frame no hero's foot box overlaps a non-walkable metatile of the
    oracle map.

## M3b — The seam spike: Voronoi

- Replace the vertical seam with the perpendicular-bisector seam (06 §2.3):
  2 HDMA channels (WH0, WH2/WH3), with tables rebuilt only when the seam
  moves.
- **Measure:**
  - the table rebuild in cycles
  - the HDMA cost per active line
  - the maximum OBJ overhang past the band, in pixels
- **Verdict:**
  - **Go:** ship it as tier M.
  - **No-go:** ship the vertical seam, and revisit at tier S. Record the
    numbers either way in 06 §2.7.
- **Tests:** players separated vertically put the seam within 10° of
  horizontal, read from the HDMA table in WRAM *and* the screenshot's divider
  pixels. Each hero is in its own region.

## M4 — Combat core

- Primary (the class arcs), bows and wands (04 §2.1), roll and potion.
- The actor pool (16 × 16 B `.struct`) and the shot pool (`pool`).
- Grunt and archer AI with a 4-frame think stagger.
- Packs spawn on room entry. Gates seal and open through the 4-cell queue.
- Hit-flash (OBJ palette 7), hit-stop, the `hit` SFX.
- **Tests:**
  - Entering a pack room puts gate metatiles in the VRAM tilemap within
    2 frames.
  - A hit puts OBJ palette 7 in the enemy's OAM attribute for 4 frames.
  - A bow at 0 arrows fires nothing: no new shot appears in OAM.
  - A wand's charge pips in the HUD row refill after `recharge` frames.

## M5 — The line ledger and the frame budget, split and merged

- Land `obj_rotate`.
- Build the worst-case room (02 §3), **once merged and once split**.
- **Tests:**
  - STAT77 range/time-over bits stay clear for 600 frames with rotation off.
  - The planted overload flickers rather than dropping a sprite.
  - **Measure every line of 02 §4**, including the seam table and the camera
    pair.
  - Zero dropped ticks over 600 frames, in both modes.

## M6 — Loot and live gear swapping

- Drops (all instanced and tinted, 04 §5), chests rolled from GEN, pickup,
  the backpack.
- **`dgn_hud`:** the 2 HUD rows DMA'd from a WRAM shadow every VBlank
  (06 §5), with the halves swapping by BG3HOFS when the seam flips sides.
- **The Select controls** (06 §4): tap = next slot; hold + Up/Down = cycle
  items; hold + Right/Left = add or remove a spark. The other player keeps
  playing.
- **Tests:**
  - A chest's record equals `Roller.roll` for the GEN state.
  - Holding Select + Down equips the next backpack item: the HUD cells spell
    `describe()` of it, and the swing arc class in OAM changes if the base
    changed.
  - A spark added shows in the HUD and is refunded by Select + Left.
  - P2 moves on every frame P1 holds Select.

## M7 — Camp, map, results, lives, save

- The 06 §6 rules (down, revive by presence, 3 lives per level).
- The camp scene (salvage, stash, the lamplighter).
- The **map** scene: the level select, with 3 locations at tier M, unlock on
  clear, and replay with a new seed.
- `results` → camp.
- Save: battery SRAM through `save`, with the payload raised to 184 B
  (02 §2.1).
- **Tests:**
  - Revive by standing beside a downed partner for 90 frames: the HUD bar
    cells change.
  - Clearing location 1 unlocks location 2 on the map: its BG3/OBJ marker
    appears.
  - A save round-trips through a power cycle (the `test_c2_slice_c`
    pattern).

## M8 — Content and the stay-together rules

- All 21 enchants (through the 5 hooks) and all 6 accessories.
- The brute and the skitter. `enemies.toml`.
- 06 §3 rules 1–4, 7 and 8: Kindred, the Bond meter and Lantern Surge,
  shared finds, hunters of the lone, and the boss gate.
- **Tests:**
  - **Kindred:** merged regen shows in the HUD cells and stops when split.
  - **Surge:** a Lantern Surge pressed while split does nothing. Pressed while
    merged with a full meter, it freezes every enemy's OAM position for 90 f.
  - **Shared finds:** a chest opened with both heroes present spawns 2
    tinted item drops plus 2 spark drops in OAM. Opened alone, it spawns 1.

## M9 — The boss on BG2 (the merge lock)

- 05 §2.2: the boss gate needs both heroes, then locks the camera merged and
  re-points BG2 to the boss.
- **Tests:**
  - BG2SC changes to the boss map's base on the lock frame.
  - The window seam registers are disarmed.
  - The boss's scroll tracks `cam − boss`.
  - The exit appears only at 0 HP.

## M10 — Audio, region, determinism, ship

- Songs and SFX (12), region parity (`docs/98` band).
- `make determinism MODULE=tests/test_dungeons.py`.
- `make falsify` with dungeons plants: break the seam or a door gap, and a
  named test must go RED.
- A flashcart run on NTSC, and PAL if available.

## Parallel tracks (start any time; they meet the main line where named)

| track | work | meets |
|---|---|---|
| **A1** | **the model spike, `14_model_spike.md`** (local, with Blender): the wanderer's body frames, resident and not streamed, then the 3 swing-arc classes | M3: replace the CC0 placeholder hero |
| **A2** | the converter (11 §5 stage 6) and the contact sheets | M2: CHR round-trip test |
| **A3** | the Hollow Wood metatile atlas (10 §3), enemies, the boss poses, the map | M2 / M4 / M7 / M9 |
| **S1** | port sf-gt's sample synthesiser; add the choir, percussion and chord samples under the 12 §3 policy; audition as WAVs | — |
| **S2** | the camp, map and level songs with the adaptive layer plan (12 §2) | M10, or earlier as a scaffold |

## Dependency graph

```
M0 ─► M1 ─► M2 ─► M3 ─► M3b ─► M4 ─► M5 ─► M6 ─► M7 ─► M8 ─► M9 ─► M10
                    └──── the asset generator grows alongside every milestone ────┘
```

- **Split screen comes first** (M3, M3b), before combat. It is the owner's
  priority, and it is the thing everything else must fit beside.
- M5 still comes **before** loot and content. It is the milestone that can
  force a design cut, and taking that cut later would invalidate more work.
- **Art and music run in parallel** (the A- and S-tracks above).
