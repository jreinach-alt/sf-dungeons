# 06 — Co-op, split screen, gear swapping, HUD and flow

> DRAFT SPEC, revised 2026-11-16 to the owner's intent: **two-player split
> screen** that merges when the heroes are together. The proof of concept is
> the kit's `split_v_fight` (`engine/features/split_v_bg`), which splits a
> *flat* fighting stage along a vertical seam. This file generalises it for
> top-down exploration, where the players separate in any direction.

## 1. Players

- P1 is pad 1 (`input`), P2 is pad 2 (`input2`). Both are proven in `room`
  and `split_v_fight`.
- **Drop-in.** P2 presses Start to join, and appears beside P1 with their
  saved kit. P2 leaves from the pause menu.
- **One player** uses the same code with hero 2 parked. The camera is then
  always merged.

## 2. The split screen

### 2.1 What the proof of concept already proves (`split_v_bg`, read 2026-11-16)

- **Two cameras onto ONE copy of the stage.** BG1 is scrolled to camera A and
  BG2 to camera B. `BG2SC` points at BG1's tilemap and `BG12NBA` at BG1's
  CHR, so the second view costs **no VRAM at all**.
- **PPU window 1 clips the layers to opposite sides of the seam.** BG1 is
  shown on one side, BG2 on the other.
- **At zero divergence the halves are pixel-identical**, so the seam is
  invisible and the split opens continuously out of one view.
- **The divider band is window 2**, a band of half-width `hw` about the seam
  that ramps from zero.
- **Cost: no HDMA.** A straight seam is three CPU writes a frame (WH0, WH2,
  WH3) into shadows the NMI commits.
- **Limits:**
  - Its cameras are horizontal-only.
  - Its seam is vertical-only.
  - It uses BG3 as a bevelled divider, so its HUD is sprites.

### 2.2 Why it fits Dungeons unusually well

The whole floor is resident in VRAM as one 64×64 `tiles16` tilemap (02 §1).
Both cameras therefore look at the **same resident floor**: no streaming, no
second copy, and both views can be anywhere on the floor. Each layer has its
own HOFS/VOFS, so making both cameras **2-axis** is free. That was the one
change the fighter demo never needed.

### 2.3 The seam: a Voronoi split

Players in an exploration game separate in any direction, so the seam follows
them. It is the **perpendicular bisector of the line between the heroes**,
placed on screen so that each half shows the world nearer its own hero. This
is the modern dynamic split. On this machine it is a **per-scanline window
edge**: for each line, window 1's left edge is where the seam crosses that
line.

| | straight vertical seam (proven) | Voronoi seam (target) |
|---|---|---|
| when players separate vertically | wrong: stacks two views side by side | correct: the seam tilts to horizontal |
| window edges | 3 CPU writes a frame | **2 HDMA channels**: WH0 per line (1 B); WH2/WH3 per line for the band (2 B) |
| table rebuild | — | ~224 lines × ~20 cycles ≈ 4.5k cycles (est.), **only on frames where the seam moves** |
| risk | none | new. The seam spike (08 M3b) measures it |

**Fallback.** If the Voronoi seam misses its budget, ship the proven vertical
seam with 2-axis cameras. The half each hero is drawn in is then decided by
x order, exactly as `split_v_fight` does it.

### 2.4 Merge and split

- **Merged** whenever both heroes fit inside one 256×(224−HUD) view with a
  32 px margin. Both cameras sit on the midpoint, so the seam is invisible.
- **Split** past that. The divergence ramps over 16 frames (no snap):
  - each camera slides from the midpoint toward its own hero along the
    separation axis;
  - the divider band widens from 0 to 4 px.

  This is the fighter demo's "split opens out of a single view", along any
  axis.
- **Hysteresis.** Merge at 32 px inside the threshold and split at 32 px
  outside it, so the camera never flickers at the boundary.

### 2.5 The divider, without BG3

The fighter demo paints its divider on BG3. Dungeons needs BG3 for text, so
**the divider is the window-2 band masking BG1 and BG2**. What shows there is
the backdrop colour, a dark ink from CGRAM word 0. One less layer is spent,
and the band is still a clean line.

### 2.6 Sprites: each actor is drawn once

A Voronoi split partitions the **world** the same way it partitions the
**screen**. Every actor is nearer one hero than the other, so it lies in
exactly one half:

- Compute the sign of `(actor − midpoint) · (P2 − P1)`, which is one multiply
  pair.
- Draw the actor once, against that half's camera.

So there is **no OAM doubling** and no double CPU. The per-scanline ledger
(02 §3) is unchanged, because a line still holds at most every actor once.

- **Overhang.** A 16×16 sprite centred near the seam can overhang it by up to
  8 px. Window 2's band also masks **OBJ**, which hides up to 2 px of
  overhang on each side.
- **The rest (≤ 6 px)** is accepted, and measured in M3b. The precedent is
  `split_v_fight`, whose fighters cross halves at the seam.

### 2.7 What split screen costs, and what it buys back

| item | cost |
|---|---|
| VRAM | **0** (one floor copy, 02 §1.1) |
| HDMA | 2 channels (Voronoi) or 0 (vertical fallback) |
| CPU | 2 camera solves + the seam table when it moves (~5k cycles est.) + one sign test per actor |
| BG2 | spent on camera B while split. **Freed whenever merged**, which is what lets the boss be BG2 (§3.3) |

## 3. Staying together pays

Split screen makes separating *possible*. These rules make staying together
*worth it*, without forbidding exploration.

1. **Kindred.** While merged, both heroes regenerate 1 HP every 3 s out of
   combat, and accessory cooldowns run 25% faster. The HUD shows a small
   joined-lantern icon. It is the default reward for the default state.
2. **The Bond meter and the Lantern Surge (L).** Kills made while merged fill
   a shared Bond meter. When it is full, both players press **L within 30
   frames of each other** to release the Lantern Surge: a screen-wide stun
   (90 f), a heal of 25% of max HP to both, and a burst of the colour-math
   fixed colour. **It only works merged.**
3. **Revive needs presence.** A downed hero is revived only by a partner
   standing beside them (§6), so a pair that splits far apart risks a lost
   life. (This is the genre reference's own pressure.)
4. **Shared finds.** A chest opened with **both heroes in the room** yields
   one item per player **plus 1 spark each**. Opened alone, it yields the
   opener's item only, and the partner's share is not rolled. That is a
   reason to call your partner over.
5. **Twin seals (tier S).** A treasure vault whose door needs **two plates
   held at once**, in different cells. It rewards a *deliberate* split, and
   the loot inside then rewards regrouping (rule 4).
6. **The Fray (tier S, with the Unwriting, 10 §4).** While the view is split,
   the Unwriting advances **twice as fast**: memory frays when the wanderers
   part. This is pressure on long splits, not a ban.
7. **Hunters of the lone.** Mothwicks and Thornspitters choose the hero with
   no partner within 64 px as their target. Splitting up draws the swarm.
8. **The boss gate needs two.** A boss room's gate opens only when **both**
   heroes stand in its doorway cell. The camera then locks merged for the
   fight, and that frees BG2 to *be* the boss (05 §2.2). Solo play opens it
   alone.

## 4. Gear swapping, live, per player (no inventory screen)

**Owner direction:** swapping is available at any time, through Select.
Each player swaps independently and the game does not pause, so the couch
never waits on one player's menu.

| input | effect |
|---|---|
| **tap Select** (press and release with no D-pad in between) | move the *selected slot* to the next of **primary → ranged → armor → accessory** |
| **hold Select + Up / Down** | cycle the selected slot through the items of that slot in your backpack. The new item equips **immediately** |
| **hold Select + Right** | spend 1 spark: raise the lowest-tier enchant of the selected item by one tier (enchant 1 before enchant 2, up to III) |
| **hold Select + Left** | refund 1 spark: lower the most recently raised enchant on that item |

- **While Select is held, that hero stands still.** The D-pad is the menu, and
  the other player plays on. Releasing Select resumes movement.
- **Respec is free and continuous.** Sparks move in and out of items at any
  time. That is pillar 2 ("gear is the build") with no screen in the way.
- **Backpack:** 6 items per hero across all slots, plus the 4 equipped. A
  full backpack shows FULL, and the drop stays on the floor.
- **Salvage** (turning an item into sparks) is done at camp, not in the
  field. It is the one destructive action, so it sits behind a confirm.

09 Q4 (the inventory screen) is retired: there is no inventory scene, so the
floor never has to survive a scene change. The floor's state goes back to
being scene-scoped (02 §2).

## 5. HUD (BG3)

```
P1 ▮▮▮▮▮▮▮▯▯▯ ↟12 ⟡ [B MAUL P14 ✦2]     P2 ▮▮▮▮▯▯▯▯▯▯ ✧3 ⟡ [Y EMBER WAND]
```

- **Two HUD rows across the top,** one half per player:
  - HP bar
  - ammo (bow: arrows) or charges (wand: pips)
  - sparks
  - the **selected slot's item name**, shown while Select is held, then
    fading back to the icons after 60 f
- **Instant text through a shadow-row DMA (new, small: `dgn_hud`).** The two
  HUD rows (2 × 64 B) live in a WRAM shadow and are DMA'd every VBlank:
  **128 B of the 5,952 B pin**. The kit's `bg_text` queue (4 cells a frame)
  would take up to 8 frames to print two item names. The precedent is the
  kit's rule that "one declared whole-map DMA in one VBlank is legal"
  (`docs/hardware_for_your_idea.md`).
- **The halves follow their heroes.** P1's HUD sits over P1's half. When the
  Voronoi seam puts P1 on the right, the HUD swaps sides by writing BG3HOFS
  = 128, since the 32-tile row wraps. That costs zero bytes.
- **The HUD is not windowed:** the divider band never cuts the HUD rows. The
  window HDMA tables start below the HUD.
- **OBJ pips** (the `room` `hud_pips` shape, 8 entries) carry the cooldown
  and Bond indicators. They need no text traffic.

## 6. Down, revive, lives

- **Down.** At 0 HP a hero is **downed**. It lies in place and starts a
  30-second timer (1,800 f, tick-scaled), shown as OBJ pips. Enemies ignore
  downed heroes.
- **Revive.** The partner stands within 16 px **without attacking** for 90
  frames (RALLY shortens this). There is no button: every button is spoken
  for, and a couch player should never have to ask "which one revives?". The downed hero returns at 50% HP with 60 i-frames.
  If they are split, the camera shows the downed hero's half with a red
  divider tint, as a call for help.
- **Timer expiry.** The party loses one **life**, and the hero respawns at
  the partner's side.
- **Lives.** 3 per level, shared.
- **Both heroes down, or 0 lives:** the level fails and the party returns to
  camp. Equipped gear, the backpack and sparks are kept. Only the level's
  unclaimed chests are lost.
- **Solo play.** Going down spends a life and respawns the hero at the room's
  door.

## 7. OAM rotation (`obj_rotate`, small)

The dynamic OAM block starts at an index that advances by 7 each frame, so
an over-line case flickers rather than dropping a stable hole. Heroes and
pips stay pinned. **Test:** with a planted 12-in-a-row overload, every enemy
is drawn in at least 1 of every 3 frames.

## 8. Scene flow

```
title ──► camp ⇄ map (level select) ──► level ──► results ──► camp
                     ▲                        (boss down, or failed)
                     └── a level is one generated floor of a map location
```

| scene | composes (sketch) | notes |
|---|---|---|
| `title` | `bg_text`, a backdrop, music | captures `run_seed` on Start |
| `camp` | `dgn_bg` (the camp map), `dgn_obj`, `bg_text`, `dialog`, `save` | salvage, the stash, the lamplighter. Save happens here |
| `map` | a Lumenvale map BG, cursor OBJ, `bg_text` | **the level select** (10 §3). Each location is a biome and threat band; cleared locations stay replayable with a new seed |
| `level` | `dgn_bg` (BG1 + BG2: split, or the boss), `dgn_obj`, `dgn_hud`, `obj_rotate`, `dgn_logic`, `rng`, `input2` | generation runs in `enter`, under forced blank, behind the map's fade |
| `results` | `bg_text` | the level summary, then camp |

Every level is entered from `map`, so `sm_request`'s no-self-transition rule
never binds. The `descend` card scene is retired: the map's embark fade hides
generation instead.
