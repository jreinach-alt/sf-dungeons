# 09 — Open questions (the owner's decisions)

> Each open question has a recommendation, so work can start under it. An
> answer changes the named sections.

## Open

| # | question | options | recommendation | affects |
|---|---|---|---|---|
| **Q5** | Hero sprite size | 16×16 (planned) vs 32×32 | **16×16, resident.** The owner ties this to whether streamed heroes fit beside everything else. Streaming is now dropped in favour of split screen (02 §1.2), and the table-0 ledger (~232 of 256 tiles) fits 16×16 resident. 32×32 heroes would need streaming back. Confirm after the model spike shows the 16 px read | 02 §1.2, 13, 14 |
| **Q7** | Seed entry (daily runs) | tier C | defer | 03 §2.3 |
| **Q10** | The Unwriting as advancing pressure, now with the Fray (06 §3 rule 6) | tier S, or drop it | keep it at tier S | 10 §4, 06 §3, 12 §2 |
| **Q11** | **Voronoi seam vs vertical seam** for the first build | the Voronoi seam (any direction, 2 HDMA channels, new) vs the vertical seam (proven, 0 HDMA) | build the proven vertical seam first (M3), then spike the Voronoi seam (M3b) and adopt it on measured cost | 06 §2.3, 08 M3/M3b |
| **Q12** | Do 06 §3's stay-together rules have the right weight? | play-test | ship rules 1–4, 7 and 8 at tier M; tune after the first two-player play-test | 06 §3 |

## Decided

| # | decision | date |
|---|---|---|
| Q1 | **Battery save.** Not a jam game. The `save` payload is raised to 184 B (02 §2.1) | 2026-11-16 |
| Q2 | **Art is modelled in Blender and prerendered** (11). CC0 placeholders serve until the renders land | 2026-11-16 |
| Q3 | **Normal / Hard / Epic** raise spawn strength and count. It is not in the initial build, but the hooks ship with only the Normal row (04 §3.1) | 2026-11-16 |
| Q4 | **No inventory screen.** Gear is swapped live, per player, through Select (06 §4). The level's state is scene-scoped again (02 §2) | 2026-11-16 |
| Q6 | **Names approved:** SuperForge Dungeons, Lumenvale, the Unwriting, the Underleaf, and the biome and enemy names | 2026-11-16 |
| Q8 | **The pipeline is SUPERFORGE GT's** (`jreinach-alt/sf-gt`), ported, and extended for animated figures (11, 13, 14) | 2026-11-16 |
| Q9 | **No external samples, and no raw samples from shipped games.** Patterns learned from shipped games may be adapted: reshape a procedural, first-party sample to match an observed BRR block pattern (12 §3) | 2026-11-16 |
| — | **The camera is two-player split screen** that merges when together. Mechanics reward staying together (06 §2–3) | 2026-11-16 |
| — | **Four slots** (primary, ranged, armor, accessory). **Gear on Select**, live (06 §4) | 2026-11-16 |
| — | **No shared ammo.** Bows have per-hero arrows; wands recharge (04 §2.1) | 2026-11-16 |
| — | **Heroes are resident, not streamed.** The budget goes to split screen (02 §1.2) | 2026-11-16 |
| — | **Level-select map; return to camp after each level** (06 §8) | 2026-11-16 |
| — | **Visual theme:** borrows mood from a 1984 storybook-void fantasy film, as evocation, not reproduction (10) | 2026-11-16 |
| — | **Music:** 80s orchestral, influenced by two early-80s fantasy scores, as technique, not quotation (12) | 2026-11-16 |
