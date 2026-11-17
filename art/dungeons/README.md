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
| `build_all.sh` | shell | the stage runner: `smoke`, `render`, `pixelate`, `sheets` (no argument runs the last three) |
| `actors/actions.toml` | data | the camera, light, bones, actions, key poses and timings, read by both the Blender script and the game |
| `actors/roles.toml` | data | palette roles: material id → palette index |
| `actors/pixelate_actor.py` | Python | data frame → indexed sprite (`tests/test_dungeons_pixelate.py`) |
| `actors/verify_smoke.py` | Python | checks the smoke frame |
| `actors/render_actor.py` | Blender | the wanderer: parts, armature, skinned cloak, keyed actions, 3 directions → raw data frames (`--inspect`: colour pictures for looking) |
| `actors/kit.py` | Blender | figure parts (shell, limb, open cloak), the armature, rigid/skinned binding, posing and keying |
| `actors/pose_data.py` | Python | the `actions.toml` channel semantics (lag, per-direction tables) and their checker, with no Blender |
| `actors/pixelate_frames.py` | Python | the pixelate stage: raw frames → `frames/<model>_<action>_<dir>.png` |
| `actors/sheets.py` | Python | the sheets stage: `sheet_<model>.png`, `anchors.json`, `metrics.json` (13 §4) |
| `actors/frames/` | tracked | the indexed 16x32 strips (index 0 transparent): the converter's input |
| `actors/archive_16x16/` | tracked | the first spike's 16x16 set, sheet, metrics and TOML, kept for comparison (`compare_16x16_vs_16x32.png`) |
