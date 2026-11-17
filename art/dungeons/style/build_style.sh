#!/bin/bash
# build_style.sh — the art-direction spike's pipeline, end to end.
#   render   (Blender)  art/dungeons/style/render_style.py: the authoring model -> data frames
#   paint    paint.py:  data frames -> painted indexed strips + palettes (committed)
#   room     room.py + scene.py: the mock Hollow Wood room, natively and on a CRT
#   boards   boards.py + anim.py: sheets, native strips, the A/B/C comparison, GIFs
# Usage: art/dungeons/style/build_style.sh [style ...]   (default: all three)
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
BLENDER="${BLENDER:-$HOME/toolchains/blender/blender}"
PY="${PYTHON:-python3}"
cd "$REPO"
styles=("$@"); [ ${#styles[@]} -eq 0 ] && styles=(a_storybook b_practical c_painted16)
mkdir -p build/dgn_art_work
for s in "${styles[@]}"; do
  echo "== $s: render + paint"
  "$BLENDER" -b --factory-startup -P art/dungeons/style/render_style.py -- \
      --style "art/dungeons/style/styles/$s.toml" --actions idle,walk,attack \
      > "build/dgn_art_work/render_$s.log" 2>&1 \
    || { echo "render failed: build/dgn_art_work/render_$s.log" >&2; exit 1; }
  grep -q Traceback "build/dgn_art_work/render_$s.log" && { echo "render failed: build/dgn_art_work/render_$s.log" >&2; exit 1; }
  "$PY" art/dungeons/style/paint.py "art/dungeons/style/styles/$s.toml"
done
echo "== room + scenes"
"$PY" art/dungeons/style/room.py
"$PY" art/dungeons/style/scene.py "${styles[@]}"
echo "== boards + animation"
"$PY" art/dungeons/style/boards.py
for s in "${styles[@]}"; do "$PY" art/dungeons/style/anim.py "$s" >/dev/null; done
"$PY" art/dungeons/style/anim.py a_storybook --palette p2 >/dev/null
echo "build_style: done -> art/dungeons/style/out/"
