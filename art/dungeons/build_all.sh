#!/bin/bash
# build_all.sh — SuperForge Dungeons art: regenerate actor assets from Blender.
#
# The sf-gt stage shape (art/fgt/cars/build_all.sh), grown one stage at a time
# by the model spike (docs/dungeons/14). Today only the SMOKE stage exists.
#
#   art/dungeons/build_all.sh smoke      Blender plumbing check -> verify
#
# Stages (planned; the spike fills them in, in this order):
#   smoke     check_blender.py (Blender) -> actors/verify_smoke.py
#   render    actors/render_actor.py (Blender): rig + actions -> build/dgn_art_work/
#   pixelate  actors/pixelate_actor.py -> art/dungeons/actors/frames/*.png (indexed, tracked)
#   sheets    contact sheets, anchors.json, the lineup
#   convert   tools/dungeons/gen_dungeons_assets.py -> build/dungeons/ (in the build)
#
# Environment: BLENDER (default ~/toolchains/blender/blender, Blender 4.2 LTS,
# as in sf-gt), PYTHON (default python3; numpy + Pillow).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
BLENDER="${BLENDER:-$HOME/toolchains/blender/blender}"
PY="${PYTHON:-python3}"
cd "$REPO"

stage="${1:-smoke}"
case "$stage" in
  smoke)
    "$BLENDER" -b --factory-startup -P art/dungeons/check_blender.py
    "$PY" art/dungeons/actors/verify_smoke.py
    ;;
  *)
    echo "build_all.sh: stage '$stage' is not written yet (docs/dungeons/14)" >&2
    exit 2
    ;;
esac
