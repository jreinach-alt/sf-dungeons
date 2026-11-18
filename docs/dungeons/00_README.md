# SuperForge Dungeons — the spec set

> **What this is.** The up-front specification for an original SNES game: a
> two-player same-screen co-op action dungeon crawler. Floors are generated
> procedurally, and the build is whatever gear drops; there is no class. The
> set was written before any game ASM so that an implementing agent can take
> it and run, one milestone at a time, with every decision either made here or
> listed as the owner's question.
>
> **Status:** DRAFT, 2026-11-16. This is the `jreinach-alt/sf-dungeons` repo.
> In `game/`: only `game/dgn_hero`, the model spike's on-console proof (14 §6.1).
> The game's own rail, `game/dungeons`, starts at 08 M0.

## Read in this order

| file | job |
|---|---|
| [01 — Vision and pillars](01_vision_and_pillars.md) | what the game is, the 5 pillars, the controls, the scope ladder |
| [02 — Architecture and budget](02_architecture_and_budget.md) | the picture (BG1 resident `tiles16` floor, BG2 boss, BG3 HUD), the VRAM/WRAM/OAM/CPU/ROM ledgers, the scenes |
| [03 — Level generation](03_level_generation.md) | the generator, defined by an **executable oracle** |
| [04 — Gear and loot](04_gear_and_loot.md) | the 4-byte item record, power vs threat, enchants, drops |
| [05 — Combat and entities](05_combat_and_entities.md) | the hero kit, enemies, the actor record, AI cadence |
| [06 — Co-op, camera, HUD and flow](06_coop_camera_hud.md) | the spread leash, revive/lives, loot fairness, OAM rotation, the scene list |
| [07 — Assets and audio](07_assets_and_audio.md) | art direction, the asset list, the generator, sound |
| [08 — Milestones](08_milestones.md) | **the build order**: M0–M10, each with rendered-output acceptance tests |
| [09 — Open questions](09_open_questions.md) | the owner's decisions, each with a working recommendation |
| [10 — World and visual themes](10_world_and_themes.md) | the premise (the Unwriting), the "80s matte painting" look, biomes, the bestiary, and the evocation-not-reproduction line |
| [11 — Art pipeline](11_art_pipeline_3d.md) | Blender prerenders → SNES, ported from SUPERFORGE GT: data-pass renders, material-vote pixelation, palette role tables, plus what is new (skinned characters, tiles) |
| [12 — Music and sound](12_music_and_sound.md) | 80s orchestral in three colours, adaptive layers on TAD's channel mask, the synthesised orchestra, the cue sheet |
| [13 — Character pipeline](13_character_pipeline.md) | animated figures: the rig and actions as data, the ported pixelate stage (tested without Blender), the `bpy` script to write, acceptance metrics, and where Elyum helps (references only) |
| [14 — The model spike](14_model_spike.md) | the local, Blender-driven proof that an animated figure comes out as a 16×16 sprite that reads. **Ran 2026-11-15: GO, with adjustments (§6)**; friction in [dx_paper_cuts_spike](dx_paper_cuts_spike.md) |
| [15 — The art-direction spike](15_art_direction_spike.md) | **for sign-off:** three visual treatments of the wanderer (storybook, practical-effects, painted 16-bit) through a painterly stage, judged in a mock Hollow Wood room and on a CRT preview, with a recommendation |
| [16 — The creature pipeline](16_creature_pipeline.md) | **built and proven:** a creature is a data file (parts, IK leg sets, gait / pose actions, a palette). A 32×32 spider and a tortoise boss that rises onto two feet and stomps, with console budgets measured from the pixels; what raises the quality ceiling; what the hardware allows |
| [17 — The four briefed enemies](17_enemy_bestiary_spike.md) | **built:** Bellwretch, Thornhopper, Candlemaw and Crownling from the owner's brief and reference sheet, each with idle / move / telegraphed prepare / attack at 32×32, two facings, measured budgets, an honest assessment of each |
| [18 — The boss-battle scene on the console](18_boss_scene_spike.md) | **built and measured:** a 64×64 streamed boss, two players with attack frames, two small enemies, on the console; VBlank is what runs out first (worst frame ends on scanline 255 of 261), and an overrun is silent and permanent; what it did not test |
| [19 — The choreographed boss fight](19_choreographed_boss_fight.md) | **built and measured:** the boss, a chasing player and a duel played back from a compiled score; prefetching each frame into a back buffer cuts the worst VBlank from scanline 260 to 235 (241 for the realistic hybrid); what broke on the way, including a regression in my own previous commit |
| [HANDOFF](HANDOFF.md) | where everything is, what is verified, and what is next |
| [research/genre_reference.md](research/genre_reference.md) | what the genre reference and its precedents do (the evidence behind 01–06) |
| [research/kit_capabilities.md](research/kit_capabilities.md) | what this kit already proves, game by game (Proven / Near / New) |

## What already runs (no ROM needed)

The decisions that can be settled before any ASM are settled as **code**,
because a model that runs beats prose that describes:

```bash
python3 tools/dungeons/levelgen.py 0x1234 4          # ASCII floor + path, draws, validation
python3 tools/dungeons/render_preview.py out.png     # floors as a picture (img/levelgen_preview.png)
python3 tools/dungeons/loot.py                       # sample drops by floor
python3 -m pytest tests/test_dungeons_model.py tests/test_dungeons_pixelate.py tests/test_dungeons_frames.py -q   # 130 checks, ~4 s
```

| file | what it pins |
|---|---|
| `tools/dungeons/prng.py` | xorshift16 (7, 9, 8). Full period verified, golden values pinned |
| `tools/dungeons/levelgen.py` | the generator, its per-floor validation, and the template linter |
| `tools/dungeons/loot.py` | the item roller and the 4-byte record |
| `tools/dungeons/data/templates.txt` | 13 hand-authored rooms (tier M) |
| `tools/dungeons/data/gear.toml` | 22 bases, 21 enchants, rarity, power, drop tuning |
| `art/dungeons/actors/actions.toml`, `roles.toml` | the hero rig, actions and palette roles, as data for Blender and the game alike |
| `art/dungeons/actors/pixelate_actor.py` | render → sprite, ported from sf-gt (`tests/test_dungeons_pixelate.py`) |

**These are oracles.** The ROM tests in 08 compare WRAM and VRAM against them
byte for byte. That is how a generated level gets a test that reads rendered
output rather than a proxy: the expected tilemap is computable.

**What the models found before any ROM existed:**

- The template linter's first run caught `start_cross` walling off its own
  north door. 20,000 generated floors had never exercised that door.
- The CHR arithmetic showed resident hero frames overflow an OBJ name table
  (312 tiles against 256). That turned "heroes are sprites" into "heroes are
  streamed" (02 §1.2) and "the boss is sprites" into "the boss is BG2" (02 §1).

## The five decisions that shape everything

1. **The whole floor is resident in VRAM.** A 64×64 metatile floor is exactly
   one 64×64 `tiles16` tilemap (8 KB). There is no streaming, and camera
   motion costs two scroll registers.
2. **Generation is template stitching on a 4×4 grid** with a guaranteed
   critical path, deterministic per seed, and verified by its oracle.
3. **A shared screen with a spread leash.** The kit's split screen costs
   every BG layer, and the SNES cannot zoom Mode 1.
4. **The item record stores the roll, not the stats.** It is 4 bytes, and
   rarity is derived.
5. **Measured caps keep 60 fps:**
   - 10 active enemies
   - 16 shots
   - AI thinking on a 4-frame stagger
   - a hand-kept per-scanline ledger, checked against STAT77 in M5

## The creative direction (owner, 2026-11-16)

- **Visuals** borrow the mood of a 1984 fantasy film: a storybook world
  erased by an advancing void, painted 80s luminosity, vast scale. The take
  is mood, palette and motifs; no characters, designs or names. 10 draws the
  line and lists what is explicitly out.
- **Music** is 80s orchestral, borrowing technique from a barbarian-epic
  score (brass, war drums, chant) and a goblin-maze score (synth-orchestra
  whimsy). There are no quoted melodies (12).
- **Art** is modelled in Blender and prerendered with the pipeline Fable built
  for SUPERFORGE GT (`jreinach-alt/sf-gt`), ported and extended (11). The build consumes
  committed renders and never runs Blender.
- **Save** is battery SRAM. This is not a jam game.

## House rules this set follows (and that the implementer must)

- **The cleanroom rule.** The genre reference, the source film and the score
  influences are never named in the tree, nor are their characters and
  composers. The denylist entries that enforce this were added with this set
  (`tools/cleanroom_check.sh`). All item, enemy and place names are original.
- **The repo's seven rules** (`CLAUDE.md`):
  - emulator truth over reading ASM
  - rendered-output tests
  - a fresh render per claim
  - no hardware shortcuts
  - random power-on RAM
  - width annotations
  - the emulator is not the bug
- **Declare, don't allocate.** Every address in 02 is a declaration the
  allocator will place. No section of this set names an address.
