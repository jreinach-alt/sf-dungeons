# art/dungeons — source art for SuperForge Dungeons

The art is built in Blender, by committed scripts, and **the build never runs
Blender**. The indexed PNGs written here are the converter's input and are
tracked (`.gitignore` un-ignores `art/dungeons/**/*.png`). Raw Blender data
frames are scratch in `build/dgn_art_work/`. Contract:
`docs/dungeons/11_art_pipeline_3d.md` and `13_character_pipeline.md`.
Ported from sf-gt's `art/fgt/cars/`.

| path | runs in | job |
|---|---|---|
| `blender_common.py` | Blender | scene, the sf-gt light rig, the data-pass compositor, the ortho actor camera, role materials, mesh primitives |
| `check_blender.py` | Blender | the smoke frame (`docs/dungeons/14` step 2) |
| `build_all.sh` | shell | the stage runner: `smoke` exists today, and render / pixelate / sheets come with the spike |
| `actors/actions.toml` | data | the camera, light, bones, actions, key poses and timings, read by both the Blender script and the game |
| `actors/roles.toml` | data | palette roles: material id → palette index |
| `actors/pixelate_actor.py` | Python | data frame → indexed sprite (`tests/test_dungeons_pixelate.py`) |
| `actors/verify_smoke.py` | Python | checks the smoke frame |
