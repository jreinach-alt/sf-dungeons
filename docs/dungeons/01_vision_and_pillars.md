# 01 — Vision and pillars

> Status: DRAFT SPEC, pre-implementation (2026-11-13). Read 00_README.md for
> how this set is used. Everything here is ORIGINAL: no names, characters,
> art, item names or levels from any commercial game. The genre reference is
> referred to as "the genre reference". Its design lessons are recorded in
> `research/genre_reference.md`; its name stays out of the tree, because
> `make cleanroom` would refuse it and should.

## 1. One sentence

Two friends on one couch, one SNES, one screen: they dive a freshly generated
dungeon floor, and the gear it drops decides who becomes the brawler, the
archer or the healer this run. Nobody picks a class.

The world is **Lumenvale**, a storybook realm being erased from the edges
inward by a silence called the Unwriting. The look is luminous 80s fantasy:
painted, dusty, vast. The score is 80s orchestral, with war brass and synth
mystery. See 10 and 12.

## 2. Pillars (in priority order: when two collide, the higher one wins)

1. **Couch co-op first.** Every system is designed for two players on one
   console. Single player is supported, but it is the case that has to fit the
   two-player design, not the reverse. Concretely:
   - **split screen that merges when the heroes are together** (06 §2)
   - mechanics that make staying together pay, without forbidding exploration
     (06 §3)
   - instanced drops, so nothing is ever shared or fought over, ammo included
   - a downed/revive loop
   - partner-facing gear (BOND, RALLY)
2. **Gear is the build.** No class, no skill tree.
   - A player's playstyle is entirely their four equipped items: **primary,
     ranged, armor, accessory** (owner, 2026-11-16).
   - Swapping is free, live and per player, at any time, through Select. There
     is no menu screen (06 §4).
3. **Every floor is new, every floor is fair.** Floors are stitched from
   hand-authored rooms along a generated critical path. Pure noise is not used.
   - Every floor is provably completable: the generator's oracle checks
     reachability, and the ROM test asserts it.
   - Pacing comes from authored rooms, so it is a design decision, not luck.
4. **Hard 60 fps, no slowdown, ever.** This is the house rule of this engine.
   Enemy counts, projectile counts and effects are capped by design, and the
   caps are measured (see 02 §3).
5. **Readable on a CRT.** A 16×16 hero must read at a glance:
   - silhouette first,
   - player-tinted palettes (P1 blue, P2 amber),
   - telegraphed enemy attacks (a flash or wind-up of at least 12 frames).

## 3. The core loop

```
 CAMP (hub) ⇄ MAP (level select) ──► LEVEL (generated floor) ──► boss ──► RESULTS ──► CAMP
   salvage, stash,    pick a location:          rooms: packs, chests,
   the lamplighter    biome + threat band       treasure branches
```

- **One level** is one generated floor of a map location, a playable target
  of 5 to 10 minutes: 5 to 9 path rooms, 0 to 2 treasure branches and 1 boss
  room (03 §3). After each level the party returns to camp (owner,
  2026-11-16).
- **The map** unlocks locations as levels are cleared. A cleared location
  stays replayable with a fresh seed, for loot. A location's threat band sets
  the level's threat (04 §3).
- **Difficulty (later, not the first build):** Normal / Hard / Epic raise the
  strength and number of spawns (04 §3.1, owner 2026-11-16).
- **Persistence:** each player's equipped kit and backpack plus the camp
  stash and map progress, saved to battery-backed SRAM (02 §2.1).

## 4. The controls (both pads identical)

| button | action | notes |
|---|---|---|
| D-pad | move (8-way) | facing = last nonzero direction |
| B | primary attack | hold = repeat at the weapon's rate |
| Y | ranged | bows spend **your own** arrows; wands spend a charge that refills over time. Nothing is shared (04 §2.1) |
| A | dodge roll | 12 frames of invulnerability, then a cooldown (05 §1.3) |
| X | potion | heals 60% of max HP, 45 s cooldown, per player |
| R | accessory | its own cooldown |
| L | **Lantern Surge** | with both players pressing within 30 frames, while merged and with the Bond meter full (06 §3) |
| Select | **gear** | tap: next slot. Hold + Up/Down: cycle items. Hold + Right/Left: add or remove a spark (06 §4) |
| Start | pause | pauses both players (options, leave the level) |

All eight buttons are spoken for. That is deliberate: it is why the kit is
four slots with one accessory, and why gear lives on Select instead of on a
menu screen.

## 5. Scope ladder (cut from the bottom)

| tier | contents | must ship? |
|---|---|---|
| **M (minimum)** | split screen with merge, live gear swapping, 1 biome (the Hollow Wood, 10 §3), 13 room templates (already authored), 4 enemy types, 1 boss, 22 item bases, 21 enchants, camp, map with 3 locations, save, Kindred + Bond/Lantern Surge + shared finds + the boss gate (06 §3 rules 1–4, 7–8) | yes |
| **S (should)** | 2nd biome (palette swap plus 8 templates), elites, twin seals and the Fray (06 §3 rules 5–6), music per biome, the Voronoi seam if M shipped the vertical fallback | next |
| **C (could)** | 3rd biome, a 2nd boss, Normal/Hard/Epic difficulty, darkness levels lit by SUN LANTERN, daily seed | later |
| **W (won't)** | online, more than 2 players, more equipment slots, shared ammo, procedural music | — |
