"""report.py — what a painted creature COSTS on the console (docs/dungeons/16 §5).

    python3 art/dungeons/creatures/report.py spider tortoise

Reads the committed strips, groups the frames in the spec's action order, and runs
budget.report for the spec's size class. Writes out/<name>/budget.json. A frame that
does not fit its class is an error (budget.report refuses), not a footnote.
"""
import json, sys, tomllib
from pathlib import Path
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import budget


def frames(name, facing="down"):
    spec = tomllib.loads((HERE / "specs" / f"{name}.toml").read_text())
    d = HERE / "out" / name
    out = {}
    for an, a in spec["action"].items():
        p = d / f"{an}_{facing}.png"
        arr = np.asarray(Image.open(p))
        bw = a.get("box", spec["camera"]["box"])[0]
        for i in range(arr.shape[1] // bw):
            out[f"{an}_{i}"] = arr[:, i * bw:(i + 1) * bw]
    return spec, out


def run(name):
    spec, fr = frames(name)
    r = budget.report(fr, spec["size_class"])
    r["name"] = name
    (HERE / "out" / name / "budget.json").write_text(json.dumps(r, indent=1) + "\n")
    return spec, r


if __name__ == "__main__":
    for n in sys.argv[1:]:
        spec, r = run(n)
        print(f"\n== {n}  ({spec['size_class']}, box {spec['camera']['box']}, {r['frames']} frames)")
        for k, v in r.items():
            if k in ("per_frame", "new_tiles_per_transition", "name"):
                continue
            print(f"   {k}: {v}")
        print("   tiles per frame:", r["per_frame"])
        if "new_tiles_per_transition" in r:
            print("   new tiles per transition:", r["new_tiles_per_transition"])
