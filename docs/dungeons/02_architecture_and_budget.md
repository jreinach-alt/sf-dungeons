# 02 — Architecture and budget

> DRAFT SPEC. Capability evidence: `research/kit_capabilities.md`. Every
> number tagged **(est.)** is an estimate and MUST be replaced by a
> measurement before the milestone that relies on it closes (CLAUDE.md
> rule 1). Every number tagged **(pin)** is a measured value from
> `allocator/substrate.toml`.

## 1. The picture (Mode 1)

| layer | job | notes |
|---|---|---|
| **BG1** | the whole floor: camera A | `tiles16`, 64×64 tilemap = 1024×1024 px, 4bpp. **Resident**: uploaded once in `level::enter` under forced blank, never streamed. Wall-top metatiles set the tilemap priority bit, so a hero at OBJ priority 2 walks *behind* them. |
| **BG2** | **camera B** while split · **the boss** while merged in a boss room | Split: `BG2SC`/`BG12NBA` point at BG1's *own* tilemap and CHR (the `split_v_bg` trick), so the second view costs 0 VRAM (06 §2). Boss room: the camera locks merged, BG2 is re-pointed in VBlank to the boss's 32×32 map and CHR, and the boss is a background that moves by scroll: 0 OAM entries and 0 per-line slivers (05 §2.2). `dgn_bg` owns BG2SC/BG12NBA in both roles. |
| **BG3** | HUD text | 2bpp, high priority (BGMODE b3). Two rows, each player's half over their own view, DMA'd from a WRAM shadow every VBlank (`dgn_hud`, 06 §5). Never windowed. |
| **OBJ** | heroes, enemies, shots, drops, FX | the **8×8 / 16×16** OBSEL pair. Heroes and enemies are 16×16; a brute is 2×2 of them (§3). |
| **windows** | the split seam and divider band | window 1 = the seam (BG1 one side, BG2 the other); window 2 = the divider band (masks BG1, BG2, OBJ). Voronoi: 2 HDMA channels; vertical fallback: 0 (06 §2.3) |

**Why one resident BG1 floor.** The generated floor is exactly 64×64 metatiles
(03 §2). In 16×16-tile mode that is one 64×64 tilemap, 8 KB of VRAM.

- **What it buys:**
  - No streaming at all. The kit's 2-axis streamer reads ROM blobs, and
    rebuilding it for WRAM would cost 64 KB.
  - No per-frame VRAM traffic for the map, apart from the door/chest cell
    queue.
  - Camera motion is free: two scroll registers.
- **What it costs:**
  - The first `tiles16` rail in the tree. `docs/100` states that nothing checks
    the CHR page's `N/N+1/N+16/N+17` quad layout. **The asset generator owns
    that invariant, and a test asserts it from VRAM** (08 M2).

### 1.1 VRAM plan (declared, never hand-placed: the allocator emits the bases)

| claim | size | note |
|---|---|---|
| BG1 tilemap 64×64 | 8 KB | `shape = "64x64"` (proven by `pfs_bg`) |
| BG1 CHR, 4bpp | ≤ 16 KB | ≤ 128 metatiles × 4 tiles × 32 B, laid out in 16-wide rows for the quad |
| BG3 tilemap + 2bpp font | ~4 KB | `bg_text` / `text_chr` |
| OBJ CHR, two name tables | 16 KB | table 0: **both heroes, resident** (one CHR set, two palettes), the weapon-class swing arcs, shots, drops and pips (§1.2). Table 1: the level's enemy set and FX, resident, uploaded at enter |
| BG2 camera-B view | **0** | points at BG1's tilemap and CHR |
| BG2 boss CHR + 32×32 map | ≤ 10 KB | the boss's poses as BG tiles |
| **total** | **≤ 54 KB of 64 KB** | leaves ~10 KB headroom (est.). The allocator proves the fit at M2 |

### 1.2 Heroes are resident, not streamed (owner decision, 2026-11-16)

The first draft streamed hero and swing frames from ROM every VBlank, because
per-weapon swing art did not fit. The owner's call is to **spend the budget on
split screen rather than on animation volume**, and the art is reshaped to
fit instead.

- **Hero body:** 3 directions (left is a flip) × 11 frames, which are idle 2,
  walk 4, roll 2, strike 1, hurt 1 and downed 1. That is 33 frames × 4 tiles
  = **132 tiles**.
- **Swings are weapon-*class* arcs, not per-weapon renders.**
  - There are 3 classes (slash, thrust, smash), each with 3 frames in
    2 orientations; the other two orientations are H/V flips.
  - That is 18 frames × 4 = **72 tiles**, drawn beside the hero's `strike`
    pose and tinted through the hero palette.
  - Each primary base names its class in `gear.toml` (`swing = …`). A MAUL
    and a SWORD then differ in arc *shape* and timing, which is what reads at
    16 px.
- **Shots and drops (8×8) and the HUD pips:** about 28 tiles.
- **Table 0 total: ~232 of 256 tiles.** `tests/test_dungeons_model.py`
  enforces this ledger from `actions.toml`, so adding a frame that breaks it
  fails a test.
- **Enemies and FX in table 1:** about 140 + 50 tiles, side-facing, with left
  by HFLIP.

**What streaming would actually have cost**, for the record:

- 1,024 B-equivalent of VBlank DMA per frame, and a few hundred CPU cycles.
- Split screen spends mostly CPU (camera solves, the seam table) and HDMA
  channels. So the two do not truly compete for cycles.
- The reason to drop streaming is **simplicity**: one fewer new feature, and
  a plan that does not depend on it.

**If art later wants more frames,** sf-gt's streamer is the documented way
back.

### 1.3 CGRAM plan

| palettes | use |
|---|---|
| BG 0–1 | HUD. Mode 1's BG3 is 2bpp, and its 8 sub-palettes are CGRAM words 0–31, the same words as BG palettes 0–1. So 0–1 belong to the HUD, and BG1 does not use them |
| BG 2–6 | biome: floor, walls, chasm, braziers, doors/chests |
| BG 7 | the boss (BG2). Its hit-flash rewrites this palette for 4 f |
| OBJ 0 / 1 | P1 hero / P2 hero (the same CHR, palette swap: the `split_v_obj` precedent) |
| OBJ 2 / 3 | P1 drop tint / P2 drop tint (instanced loot, 06 §4) |
| OBJ 4–6 | enemies (biome set) |
| OBJ 7 | the **flash** palette: all-white, used for hit-flash by swapping the attribute (zero DMA) |

## 2. WRAM and DP plan (all through `state.toml`; symbols are `US_*`)

| state | scope | size | note |
|---|---|---|---|
| floor map | scene `level` | 4,096 B | one byte per metatile; doubles as the collision grid (03 §4.1) |
| cell grid + door masks | scene `level` | 16 B | the 4×4 macro grid |
| spawn table | scene `level` | 32 × 3 B | type, mx, my |
| actor table | scene `level` | 16 × 16 B (`.struct`) | enemies (§4) |
| shot table | scene `level` | 24 × 8 B | player and enemy shots (`pool`) |
| drop table | scene `level` | 16 × 8 B | every drop is instanced to a player (04 §5) |
| hero state ×2 | global | ~48 B each | pos, HP, cooldowns, i-frames, facing, downed timer, **arrows**, **wand charges** + recharge timer, selected slot |
| equipped ×2 | global | 4 × 4 B each | the item records (04 §2): primary, ranged, armor, accessory |
| backpack ×2 | global | 6 × 4 B each | carried items, cycled with Select (06 §4) |
| stash | global | 24 × 4 B | camp storage, shared |
| run state | global | ~16 B | run seed, location, lives, pity ×2, sparks ×2, Bond meter |
| GEN / FX PRNG | global, `@dp` | 2 × 2 B | 03 §2.3 |
| cameras A, B + seam | scene `level`, `@dp` | 10 B | 06 §2 |

**The level's state is scene-scoped again.** It was `[global]` only to
survive an inventory scene, and live gear swapping (06 §4) retired that
scene.

### 2.1 The save (battery SRAM: decided)

The kit's `save` feature is proven: CRC-16, magic and version, reject codes,
and a power-cycle test. Its **24 B payload cap is a constant, "a choice, not a
law"** (`engine/features/save/feature.toml`). Dungeons raises it. The save
record:

| field | bytes |
|---|---|
| equipped kits, 2 × 4 × 4 B | 32 |
| backpacks, 2 × 6 × 4 B | 48 |
| stash, 24 × 4 B | 96 |
| sparks ×2, map progress, options | 8 |
| **payload** | **184 B** |

- No separate spark ledger is needed. Sparks spent on an item are its enchant
  tiers above I, which are already in the record (04 §2). Salvage refunds
  read them from the record.
- 2 slots × (8 B header + 184 B) = 384 B. The `sram` claim grows from the
  feature's 64 B. The allocator already derives the cart header from the
  claim: `$FFD8 = $01` (2 KiB declared, the minimum) and `$FFD6 = $02`
  (battery), both read from `engine/features/save/feature.toml`. So 384 B
  changes no header byte.
- The CRC routine's cost grows with the payload. **Measure it** in M7. It runs
  at camp only, never in a floor frame.
- **Change the feature, not a copy of it.** Raise the cap in `save` itself:
  turn the constant into a declared parameter, and keep `platformer`, `room`
  and `rpg` byte-identical. Their tests are the regression guard.

### 2.2 DP

DP is the scarcest class. Only these go `@dp`:

- the PRNG states
- the two cameras and the seam
- the hero X/Y pairs (split_v_fight's `u16[2]@dp` shape)
- the per-frame scratch the hot loops need

## 3. OAM budget (128 entries; the per-line limit is a HAND LEDGER)

The allocator proves the 128 total. **It does not model 32 sprites or 34
slivers per scanline.** That ledger is written by hand here, the way
`railshooter` keeps its 22-of-34, and is re-measured in M5.

| block | entries | size | slivers on one line, worst |
|---|---|---|---|
| heroes | 2 | 16×16 | 4 |
| swing arcs | 2 | 16×16 | 4 |
| enemies | 10 active (a brute is 2×2 16×16, so ≤ 13 entries) | 16×16 | 2 each, or 4 for a brute |
| shots | 16 | 8×8 small | 1 each |
| drops | 12 | 8×8 small, instanced and tinted | 1 each |
| FX (hits, puffs) | 8 | 16×16 | 2 each |
| HUD pips (cooldowns, Bond) / downed marker | 8 + 2 | 8×8 | 1 each |
| boss | 0 | it is BG2 (§1) | 0 |
| **total pinned** | **≤ 63** | | |

**Split screen does not change this ledger.** Each actor is drawn exactly
once, in the half whose world region holds it (06 §2.6). A scanline therefore
still carries at most every on-screen actor once, whichever half it is in.

**Design rules that keep the line ledger under 34:**

1. **Enemy cap.** At most 10 active enemies, and at most 1 brute per pack.
   Room templates already spread `e` markers vertically (03 §5); packs spawn
   in a vertical column formation.
2. **OAM rotation.** The emit start index rotates each frame (new: 06 §6). An
   overflow then shows as flicker, never as a stable hole.
3. **The M5 test boots the worst authored room** (the arena template, full
   pack, both heroes on one row, max shots) and reads **STAT77's
   range/time-over bits** every frame for 600 frames. They must stay clear
   with rotation off. That is the real ledger proof.

## 4. CPU budget (NTSC, per frame)

A reference worst 60 fps frame is 305,348 mc (pin). Targets below are in
master clocks, and every one is to be **measured** with the repo's
active-line/cycle tooling in the milestone that lands it.

| work | target (est.) | note |
|---|---|---|
| NMI + OAM DMA + HUD queue | 20,000 | the pinned NMI is 16,800 |
| input ×2, two cameras, merge/split ramp | 4,000 | |
| seam table (Voronoi), only on frames where the seam moves | 6,000 | 2 HDMA tables of ≤ 200 lines (06 §2.3); 0 with the vertical fallback |
| hero logic ×2 (move, collide, attack) | 12,000 | collision is a WRAM-grid lookup, `(y>>4)<<6 | x>>4`. NOT `col_map` (951.9 mc a query, pin) |
| enemy AI × 10 | 60,000 | 6k mc each, all-in |
| shots × 16 vs targets | 30,000 | cell-bucketed: a shot tests only actors in its 2×2 metatile neighbourhood |
| drops, FX, cooldowns | 8,000 | |
| OAM build (rotation, ≤ 63 entries, one half-test per actor) | 27,000 | |
| audio tick | 438 | pin |
| **sum** | **~167,000 (est.)** | roughly half the frame. The other half is the margin this budget is entitled to |

**Rule:** if a measured line exceeds its target by 25%, stop. Either cut the
cap (enemies, shots), or move the work to a 2-frame cadence (AI think on even
or odd frames per actor index). Never let a frame run long: 60 fps is
pillar 4.

## 5. ROM budget (512 KB, 16 windows; window 0 is code)

| blob | size (est.) |
|---|---|
| code (all scenes) | ~40 KB, spills to window 1 if needed |
| room templates (13 now, 40 at tier S) | 40 × 196 B ≈ 8 KB |
| metatile → tilemap-entry table, autotile LUT | ~1 KB |
| BG CHR per biome × 3 | 3 × 16 KB |
| OBJ CHR: heroes, swing arcs, shots, drops (resident table 0) | 8 KB |
| OBJ CHR: FX (resident, table 1) | 2 KB |
| OBJ CHR: enemy sets × 3 | 3 × 8 KB |
| boss BG CHR × 2 | 2 × 10 KB |
| item / enchant / enemy tables | ~2 KB |
| text (names, UI) | ~4 KB |
| TAD audio (driver + songs + SFX) | ~64 KB |
| **total** | **≈ 215 KB of 480 KB usable** |

## 6. Scenes

The flow is title → camp ⇄ map (level select) → level → results → camp. It
is specified in 06 §8.

- **Every level is entered from the map.** `sm_request`'s no-self-transition
  rule (`scene_mgr.asm:176`) never binds.
- **Generation happens in `level::enter`**, under forced blank with NMI
  masked, as the house pattern requires, behind the map's embark fade.
  Target: under 30 frames (est.) of black, measured in M2.
- **No inventory scene.** Gear is swapped live (06 §4), so the level's state
  never has to survive a scene change.

## 7. Region

Compose `region` + `tick_scale`, as every playable rail does.

- **Movement and projectile speeds** are rate quantities and are scaled.
- **Cooldowns and i-frames** are integer frame countdowns: class B, not
  scaled. Their PAL duration is disclosed in `game.toml`, as `shmup` does.
- **Exception:** the potion, accessory and wand-recharge cooldowns are long enough that the
  ~17% PAL stretch is a balance change. Store them as tick-scaled countdowns
  (decrement by the scaled step), and say so in `game.toml`.
