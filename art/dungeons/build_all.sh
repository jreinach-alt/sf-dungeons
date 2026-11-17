#!/bin/bash
# build_all.sh — SuperForge Dungeons art: regenerate actor assets from Blender.
#
# The sf-gt stage shape (art/fgt/cars/build_all.sh), grown one stage at a time
# by the model spike (docs/dungeons/14).
#
#   art/dungeons/build_all.sh            render + pixelate + sheets (the actors)
#   art/dungeons/build_all.sh smoke      Blender plumbing check -> verify
#   art/dungeons/build_all.sh render     (Blender) wanderer idle+walk x 3 dirs -> build/dgn_art_work/
#   art/dungeons/build_all.sh pixelate   -> art/dungeons/actors/frames/*.png (indexed, tracked)
#   art/dungeons/build_all.sh sheets     -> anchors.json, sheet_wanderer.png, metrics.json
#
# Stages:
#   smoke     check_blender.py (Blender) -> actors/verify_smoke.py
#   render    actors/render_actor.py (Blender): rig + actions -> build/dgn_art_work/
#   pixelate  actors/pixelate_frames.py -> art/dungeons/actors/frames/*.png (indexed, tracked)
#   sheets    actors/sheets.py: contact sheet, anchors.json, the 13 §4 metrics
#   convert   tools/dungeons/gen_dungeons_assets.py -> build/dungeons/ (in the build; not yet)
#
# Environment: BLENDER (default ~/toolchains/blender/blender, Blender 4.2 LTS,
# as in sf-gt), PYTHON (default python3; numpy + Pillow).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
BLENDER="${BLENDER:-$HOME/toolchains/blender/blender}"
PY="${PYTHON:-python3}"
cd "$REPO"

WORK="$REPO/build/dgn_art_work"
mkdir -p "$WORK"

render() {
  echo "== render (Blender): wanderer idle,walk x right,up,down"
  if ! "$BLENDER" -b --factory-startup -P art/dungeons/actors/render_actor.py -- \
      --actions idle,walk --out "$WORK" > "$WORK/render_wanderer.log" 2>&1 \
      || grep -q -E "Traceback|Error:" "$WORK/render_wanderer.log"; then
    echo "build_all.sh: render failed — see $WORK/render_wanderer.log" >&2
    exit 1
  fi
  grep "^render_actor:" "$WORK/render_wanderer.log"
}
pixelate() { echo "== pixelate"; "$PY" art/dungeons/actors/pixelate_frames.py --work "$WORK"; }
sheets() { echo "== sheets"; "$PY" art/dungeons/actors/sheets.py "$@"; }

stage="${1:-all}"
case "$stage" in
  smoke)
    "$BLENDER" -b --factory-startup -P art/dungeons/check_blender.py
    "$PY" art/dungeons/actors/verify_smoke.py
    ;;
  render) render ;;
  pixelate) pixelate ;;
  sheets) sheets ;;
  style) bash art/dungeons/style/build_style.sh "${@:2}" ;;     # the art-direction spike (docs/dungeons/15)
  all) render; pixelate; sheets ;;
  *)
    echo "build_all.sh: stage '$stage' is not written yet (docs/dungeons/14)" >&2
    exit 2
    ;;
esac
