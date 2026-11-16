# 04 — Gear and loot

> DRAFT SPEC. **Oracle:** `tools/dungeons/loot.py`. **Tuning data:**
> `tools/dungeons/data/gear.toml`. That file contains 22 bases and 21
> enchants, all with original names. Tuning is a data edit, never an ASM
> edit: the asset generator packs `gear.toml` into ROM tables.

## 1. The model: gear is the build

Each hero equips **4 items**: **primary (B), ranged (Y), armor, accessory
(R)**. That is the owner's simplified set, of 2026-11-16.

Nothing else defines the character:

- no class
- no skill tree
- no stat allocation

Two levers make this work in the genre reference, and both are kept here:

1. **Every item changes how you play, not just your numbers.**
   - A MAUL is a slow 140° crowd-clearer. TWIN KNIVES are a 10-frame
     single-target blender.
   - A bow spends its owner's arrows and hits hard. An ARBALEST pierces. A
     wand never runs dry but must recharge between bursts (§2.1).
   - BULWARK PLATE trades speed for damage reduction.
   - An accessory is a whole verb: throw a bomb, plant a heal zone,
     phase-dash, summon a hound, stun ring, light burst.
2. **Respec is free.**
   - Swapping is live, at any time, per player, through Select (06 §4). Sparks
     move in and out of items the same way.
   - Salvaging (at camp) refunds every spark invested.
   - A player is never locked in, so experimenting costs nothing.

**Co-op roles emerge from gear.** BOND (heal your partner) and RALLY (revive
your partner faster) are armor enchants that only matter with two players. A
pair naturally splits into "front" and "support" without either player
picking a role.

## 2. The item record: 4 bytes, the roll not the stats

```
byte 0  base id                      (gear.toml [[base]].id; the slot is implied by the base)
byte 1  power                        1..255
byte 2  enchant 1  = id << 3 | tier  (id 0 = empty; tier 1..3, 0 = locked)
byte 3  enchant 2  = id << 3 | tier
```

- **Rarity is derived, not stored.**
  - **unique**: the base is a unique.
  - **rare**: enchant 2 is present on a non-unique.
  - **common**: anything else.
- **Accessories carry no enchants.** Their power alone scales their effect,
  and their rarity reads as common.
- **Stats are computed at use time** from the base table plus power, and are
  never stored. This is the principle in research §F.
- Two heroes' equipped kits are 32 B, and their backpacks 48 B. A 24-item
  stash is 96 B.

### 2.1 Ranged: bows have ammo, wands recharge (owner, 2026-11-16)

**Nothing is shared between players, ammo included.**

| kind | bases | the limit | refill |
|---|---|---|---|
| **bow** | SHORTBOW, ARBALEST (and the unique WIDOWMAKER) | `quiver` arrows, per hero (30 / 16) | arrow drops, **instanced to a hero holding a bow** (§5); the PLENTY enchant enlarges the quiver |
| **wand** | FROST WAND, EMBER WAND | `charges` per hero (4 / 3) | one charge per `recharge` frames (45 / 60), always, with no drops needed; PLENTY speeds the recharge |

- The **trade:** bows hit harder per shot and their arrows come from the
  dungeon; wands are self-sufficient but cap the burst.
- The HUD shows arrows as a count and charges as pips (06 §5).
- Swapping bow ↔ wand keeps the bow's arrow count: arrows belong to the hero,
  not to the item.
- `tests/test_dungeons_model.py` pins the rule that every ranged base is
  exactly one kind.

## 3. Power and threat

- `floor_threat = 1 + floor × 2`, capped at 250.
- Item power = `floor_threat + offset`.
  - `offset` is drawn from `[-2, -1, 0, +1, +2]` with weights 16/48/96/64/32.
  - Rare items get +1. Uniques get +2.

**Effectiveness is relative, which is how the numbers stay 8-bit:**

```
delta = clamp(weapon_power − enemy_threat + 8, 0, 15)
dmg   = base_dmg × MULT[delta] >> 4        ; MULT[] = 16-entry ROM table, 8 = ×1.0
```

The same rule runs in the other direction, armor power against enemy threat,
for incoming damage. Being 2 threat steps under-geared is felt. Being 4 under is
punishing.

Here `floor` is the map location's threat step: each location covers a band
of threat steps, and replaying it draws a step from the band.

**Gear score** is the average power of the 4 equipped items. Camp shows it
for both heroes. The map recommends locations whose threat is within 2 of the
**pair's average** gear score. That is the genre reference's party-average
auto-balance (research §A).

### 3.1 Difficulty: Normal / Hard / Epic (later, owner 2026-11-16)

This does not ship in the first build. It is specified so that nothing built
first blocks it.

- It is a run-level setting, chosen on the map.
- It scales **spawn strength** (threat + 0 / +4 / +8) and **spawn count**
  (packs + 0 / +1 enemy / +2 enemies, capped by 02 §3's 10 active).
- Both go through one ROM table indexed by difficulty. The first build ships
  the table with only the Normal row, so the hooks exist from day one.

## 4. Enchantments

- **21 enchants**, each with 3 tiers. Magnitudes per tier are in `gear.toml`.
- Each enchant lists the slots it can roll on. Some roll on 2 slots (EMBER,
  FROST, TITANBANE).
- **Rolled items start every enchant at tier I.**
- **Sparks:**
  - Each hero earns 1 spark per level cleared, plus 1 for every shared find
    (06 §3 rule 4).
  - **At any time**, hold Select + Right to spend a spark raising the selected
    item's lowest enchant by one tier, up to III. Hold Select + Left to take
    it back (06 §4).
  - Salvaging an item at camp refunds every spark spent on it.

  This is the genre reference's enchant-point loop, minus character levels.
  Levels cleared are the level-up.
- **Uniques** carry a fixed signature enchant at tier II in slot 1, plus one
  rolled enchant in slot 2.
- **Implementation order:** each enchant is one small hook in one of five
  places:
  - on-hit
  - on-kill
  - on-damaged
  - on-dodge
  - per-second

  M6 lands the hooks with 4 enchants. M8 fills in the rest from the table.

## 5. Drops

- **Kills** roll from the FX stream. The chance out of 256 is per enemy class
  (`[drops]`).
  - Gear drops are **instanced**: each roll produces one item *per player*,
    tinted in that player's OBJ palette. Only the owner can pick it up.
  - **Consumables are instanced too** (owner, 2026-11-16: no shared ammo).
    Arrows (only for a hero holding a bow), potion refills and sparks are each
    rolled per player, tinted, and owner-only. The genre reference shared its
    consumables; this game deliberately does not.
- **Chests** are rolled from GEN at generation time, so they are part of the
  seed. A chest holds 1 item per player, which is delivered only if both
  heroes are in the room when it opens (06 §3 rule 4).
- **The boss** drops 1 guaranteed item per player, rare or better.
- **Pity:** one byte per player. After 6 commons in a row, the next roll is
  rare.
- **Pickup:** walk over your own drop.
  - If the slot is empty, it auto-equips.
  - Otherwise it goes to the backpack: 6 per hero, carried in-run.
  - A full backpack shows "FULL" on the HUD and leaves the drop where it is.
  - The backpack persists between levels (it is saved). At camp, items can
    move between the backpack and the shared stash.

## 6. Measured oracle behaviour (20,000 rolls at floor 5)

| | count | share |
|---|---|---|
| common | 14,574 | 72.9% |
| rare | 4,402 | 22.0% (the weight is 25%; the 8 points of headroom are accessories, which fold to common) |
| unique | 1,024 | 5.1% |

## 7. Tests the ROM must pass (M6)

- For a fixed stream state, the record the ROM writes into the stash slot is
  byte-identical to `Roller.roll`'s output, and its draw count is equal.
- **Asserted on rendered output:** hold Select + Down on a known backpack.
  The HUD row's BG3 cells must spell `describe()` of the newly equipped
  record, read from VRAM, and the hero's swing arc in OAM must change class
  if the base's `swing` did. Do not read a "current item" variable.
