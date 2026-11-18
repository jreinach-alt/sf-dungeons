#!/bin/bash
# build_creature.sh — a creature, spec to review images, in one command (docs/dungeons/16).
#   validate  spec.py:      the spec is checked BEFORE Blender starts (a sentence, not a traceback)
#   render    creature.py:  (Blender) parts, IK rig, gait / pose actions -> data frames
#   paint     style/paint.py: data frames -> painted indexed strips + palettes (committed)
#   review    sheet.py, anim.py, report.py: the sheet, a GIF at game timing, the console budget
# Usage: art/dungeons/creatures/build_creature.sh <name> [--dirs right,down] [--actions a,b]
#   e.g. art/dungeons/creatures/build_creature.sh tortoise --dirs down
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
BLENDER="${BLENDER:-$HOME/toolchains/blender/blender}"
PY="${PYTHON:-python3}"
name="${1:?usage: build_creature.sh <name> [--dirs right,down] [--actions a,b]}"; shift
dirs="right,down"; actions=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dirs) dirs="$2"; shift 2 ;;
    --actions) actions="$2"; shift 2 ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
done
cd "$REPO"
spec="art/dungeons/creatures/specs/$name.toml"
work="build/dgn_art_work/creature_$name"
mkdir -p build/dgn_art_work
echo "== $name: validate"
"$PY" - "$spec" <<'PYEOF'
import sys
sys.path.insert(0, "art/dungeons/creatures")
import spec
errs = spec.validate(spec.load(sys.argv[1]))
if errs:
    print("INVALID:\n  " + "\n  ".join(errs)); sys.exit(1)
print("spec ok")
PYEOF
echo "== $name: render (Blender)"
"$BLENDER" -b --factory-startup -P art/dungeons/creatures/creature.py -- --spec "$spec" --dirs "$dirs" \
    ${actions:+--actions "$actions"} > "build/dgn_art_work/render_$name.log" 2>&1 || true
if grep -q Traceback "build/dgn_art_work/render_$name.log"; then
  echo "render failed: see build/dgn_art_work/render_$name.log" >&2; grep -A12 Traceback "build/dgn_art_work/render_$name.log" | head -20 >&2; exit 1
fi
grep "^creature\[" "build/dgn_art_work/render_$name.log"
echo "== $name: paint"
"$PY" art/dungeons/style/paint.py "$spec" --work "$work" --out art/dungeons/creatures/out
echo "== $name: review"
"$PY" art/dungeons/creatures/sheet.py "$name" --scale 6 --facings "$dirs"
for d in ${dirs//,/ }; do "$PY" art/dungeons/creatures/anim.py "$name" --facing "$d" --scale 3 | tail -1; done
"$PY" art/dungeons/creatures/report.py "$name" | head -14
