# SuperForge Dungeons

A two-player, same-screen, co-op action dungeon crawler for the SNES, in
development. Two wanderers descend into **the Underleaf**, the forgotten
layers beneath a storybook realm that a silence called **the Unwriting** is
erasing from the edges inward. Every floor is generated fresh, and the gear it
drops decides who becomes the brawler, the archer or the healer. Nobody picks
a class.

Built on [SuperForge](KIT.md), a SNES engine whose declarative resource
allocator proves at build time that a game's features fit the machine. It
targets real hardware at a hard 60 fps, LoROM, with battery save.

![generated floors: four seeds, floors 0, 4 and 8](docs/dungeons/img/levelgen_preview.png)

*Floors from the reference level generator: hand-authored rooms stitched along
a generated critical path, completable by construction. The cyan line is the
path to the boss.*

## Status

**Pre-production.** The design is specified, and the systems that can be
settled without a ROM already run as tested reference models.

| | |
|---|---|
| Design | [`docs/dungeons/`](docs/dungeons/00_README.md): vision, budgets, generation, gear, combat, co-op, world, art pipeline, music, milestones |
| Reference models | level generator, PRNG and loot roller (`tools/dungeons/`), pinned by `tests/test_dungeons_model.py` |
| Art pipeline | Blender → SNES sprites (`art/dungeons/`), ported from SUPERFORGE GT. The render-to-sprite half is tested; the Blender half is next |
| **Next** | [the model spike](docs/dungeons/14_model_spike.md): an animated figure out of Blender at 16×16 |
| Handoff | [`docs/dungeons/HANDOFF.md`](docs/dungeons/HANDOFF.md) |

## Try the models

```bash
python3 tools/dungeons/levelgen.py 0x1234 4             # a floor as ASCII, with validation
python3 tools/dungeons/render_preview.py out.png        # floors as a picture
python3 tools/dungeons/loot.py                          # sample drops by depth
python3 -m pytest tests/test_dungeons_model.py tests/test_dungeons_pixelate.py -q
```

## The kit

Everything under `allocator/`, `engine/`, `game/`, `vendor/` and the rest of
`docs/` and `tools/` is the SuperForge kit, with its own 42 example games.
[`KIT.md`](KIT.md) is its front page; `CLAUDE.md` and `AGENTS.md` are its
rules and operating manual, and they apply here unchanged.

## Credits and licence

SuperForge Dungeons is an original game: no names, characters, art or music
are taken from an existing game or film. First-party code and content are
zlib-licensed, per [`LICENSE`](LICENSE). Everything vendored is listed with
its provenance in [`NOTICE`](NOTICE).
