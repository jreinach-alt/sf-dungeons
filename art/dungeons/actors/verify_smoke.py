"""verify_smoke.py — check check_blender.py's data frame, outside Blender.

    python3 art/dungeons/actors/verify_smoke.py [RAW_PNG]

1. The G channel holds ONLY reserved ids (0 ground, 1 shadow) and the hero
   role ids the dummy used (cloak, skin): proof the material-index pass
   survived the compositor bit-exactly (Raw view, dither 0 — sf-gt lesson).
2. The frame is the size actions.toml's camera asks for.
3. It pixelates: writes build/dgn_art_work/smoke_sprite.png (indexed) and a
   x8 preview, and prints the foot row against the declared anchor.
Exit 0 = pass. Each failure names what to fix.
"""
from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pixelate_actor as P  # noqa: E402

REPO = HERE.parents[2]
WORK = REPO / "build" / "dgn_art_work"


def verify(raw: np.ndarray, act: dict, fam: P.Family) -> tuple[list[str], np.ndarray | None]:
    errs = []
    cam = act["camera"]
    bw, bh = cam["box"]
    m, ss = cam["margin_px"], cam["supersample"]
    want = ((bh + 2 * m) * ss, (bw + 2 * m) * ss)
    if raw.shape[:2] != want:
        errs.append(f"frame is {raw.shape[1]}x{raw.shape[0]}, camera wants {want[1]}x{want[0]}")
        return errs, None
    ids = set(np.unique(raw[..., 1]).tolist())
    roles = {r["name"]: r["material"] for r in fam.roles}
    allowed = {P.MAT_NONE, P.MAT_SHADOW, roles["cloak"], roles["skin"]}
    if ids - allowed:
        errs.append(f"G holds ids {sorted(ids - allowed)} that no material has: the "
                    "index pass is not exact (check Raw view + dither_intensity 0)")
    for name in ("cloak", "skin"):
        if roles[name] not in ids:
            errs.append(f"no {name} pixels (id {roles[name]}): camera or anchor misplaced")
    if errs:
        return errs, None
    try:
        sprite = P.pixelate(raw, ss, fam, m, (bw, bh), "smoke")
    except ValueError as e:
        return [str(e)], None
    return [], sprite


def main(argv):
    path = Path(argv[1]) if len(argv) > 1 else WORK / "smoke_raw.png"
    act = tomllib.loads((HERE / "actions.toml").read_text())
    fam = P.load_family("hero")
    raw = np.asarray(Image.open(path).convert("RGB"))
    errs, sprite = verify(raw, act, fam)
    for e in errs:
        print("FAIL:", e)
    if errs:
        return 1
    im = Image.fromarray(sprite, "P")
    grey = [v for i in range(16) for v in (i * 16, i * 16, i * 16)]
    im.putpalette(grey)
    WORK.mkdir(parents=True, exist_ok=True)
    im.save(WORK / "smoke_sprite.png")
    im.resize((sprite.shape[1] * 8, sprite.shape[0] * 8), Image.NEAREST).save(WORK / "smoke_sprite_x8.png")
    print(f"PASS: foot row {P.foot_row(sprite, fam.outline)}, "
          f"declared anchor row {act['rig']['anchor_px'][1]}; wrote {WORK / 'smoke_sprite.png'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
