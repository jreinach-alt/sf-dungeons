#!/usr/bin/env python3
"""sheets.py — the SHEETS stage: contact sheet, anchors.json, the 13 §4 metrics.

    python3 art/dungeons/actors/sheets.py [--model wanderer] [--strict]

Ported in shape from sf-gt art/fgt/cars/sheets.py. Reads ONLY the committed
indexed strips (art/dungeons/actors/frames/) plus, when present, the render
stage's projected-root log (build/dgn_art_work/render_log.json), and writes:

    art/dungeons/actors/anchors.json        the measured foot point per model
    art/dungeons/actors/sheet_<model>.png   every frame x8: grey roles, P1, P2
    art/dungeons/actors/metrics.json        13 §4's table, measured

--strict exits 1 if any metric fails its threshold (the thresholds below were
calibrated on the spike's renders; 13 §4 records the measured values).

The P1/P2 colours here are PREVIEW tones taken from 10 §6's words (dusk blue +
silver, amber + copper). palettes.json (11 §5 stage 1) will own the real ones;
if it exists, its `hero.p1` / `hero.p2` lists of 16 RGB triples win.
"""
from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pixelate_actor as P  # noqa: E402

REPO = HERE.parents[2]
FRAMES = HERE / "frames"
WORK = REPO / "build" / "dgn_art_work"
X = 8                                       # sheet scale

# --- thresholds (13 §4), calibrated on the spike's renders (2026-11-15) ----
# Measured on the 16x32 wanderer (~200-250 model px per frame); 13 §4 records the values
# and what each threshold caught while the model was being tuned.
DRIFT_MAX = 0          # foot row identical across an action's GROUNDED frames, per direction
LIFT_MAX = 1           # a lifted foot (a non-grounded frame) may rise this far, never sink
AGREE_TOL = 1          # foot row within 1 of the projected root row (stance depth separation)
SHIMMER = (0.10, 0.60) # idle 0<->1 px changed, as a FRACTION of the model's pixels
LEG_ROWS = 9           # the bottom rows (ending at the foot row) that hold the legs
WALK_FRAME_FRAC = 0.30 # contact vs passing, whole frame, as a fraction of model pixels
WALK_LEG_MIN = {"right": 60, "down": 20, "up": None}
                       # ...and in the leg rows (measured right 17..19, down 9..15).
                       # None: from BEHIND the cloak hides the legs (measured 5..6);
                       # the up-walk reads by the body sway, so only the frame rule holds

# --- preview palettes (index -> RGB) ----------------------------------------
_COMMON = [(150, 96, 76), (226, 170, 132), (66, 42, 30), (126, 84, 52),
           (255, 216, 112), (186, 190, 200), (22, 16, 30), (14, 12, 22)]   # 8..15
P1 = [(0, 0, 0), (26, 28, 62), (42, 50, 104), (60, 76, 146), (90, 112, 184),
      (138, 160, 216), (128, 136, 156), (206, 212, 226)] + _COMMON
P2 = [(0, 0, 0), (66, 34, 16), (114, 62, 22), (172, 104, 32), (216, 150, 54),
      (246, 202, 118), (146, 80, 48), (214, 142, 92)] + _COMMON
GREYS = [0, 44, 72, 100, 128, 158, 150, 204, 150, 204, 64, 104, 244, 190, 24, 0]
GREY = [(g, g, g) for g in GREYS]
BG_GREY, BG_FLOOR, INK = (118, 118, 118), (74, 70, 66), (236, 236, 236)


def palettes():
    pj = HERE / "palettes.json"
    if pj.is_file():
        d = json.loads(pj.read_text())["hero"]
        return [("grey roles", GREY, BG_GREY), ("P1", [tuple(c) for c in d["p1"]], BG_FLOOR),
                ("P2", [tuple(c) for c in d["p2"]], BG_FLOOR)]
    return [("grey roles", GREY, BG_GREY), ("P1 preview", P1, BG_FLOOR),
            ("P2 preview", P2, BG_FLOOR)]


def load_strips(model, act):
    """{(action, dir): [16x16 index arrays]} from the committed strips."""
    bw, bh = act["camera"]["box"]
    out = {}
    for name, spec in act["action"].items():
        for d in act["camera"]["directions"]:
            p = FRAMES / f"{model}_{name}_{d}.png"
            if not p.is_file():
                continue
            a = np.asarray(Image.open(p))
            if a.shape != (bh, bw * spec["frames"]):
                raise ValueError(f"{p.name}: {a.shape[1]}x{a.shape[0]}, want "
                                 f"{bw * spec['frames']}x{bh}")
            out[(name, d)] = [a[:, i * bw:(i + 1) * bw] for i in range(spec["frames"])]
    return out


def projected_roots(model):
    p = WORK / "render_log.json"
    if not p.is_file():
        return {}
    return {(f["action"], f["dir"], f["i"]): f["root_px"]
            for f in json.loads(p.read_text())["frames"]}


def metrics(strips, roots, fam, act):
    rows, ok = [], True
    for (name, d), fr in strips.items():
        feet = [P.foot_row(f, fam.outline) for f in fr]
        grounded = act["action"][name].get("grounded", list(range(len(fr))))
        g = [feet[i] for i in grounded]
        base = max(g)
        r = {"action": name, "dir": d, "foot_rows": feet, "grounded": grounded,
             "drift": max(g) - min(g)}
        # a frame outside `grounded` lifts a foot: it may rise by <= LIFT_MAX, never sink
        r["lift"] = max([base - feet[i] for i in range(len(fr)) if i not in grounded] or [0])
        r["sink"] = max([feet[i] - base for i in range(len(fr)) if i not in grounded] or [0])
        r["drift_ok"] = r["drift"] <= DRIFT_MAX and r["lift"] <= LIFT_MAX and r["sink"] == 0
        pr = [roots.get((name, d, i)) for i in range(len(fr))]
        if all(pr):
            r["root_rows"] = [int(p[1]) for p in pr]
            r["agree"] = max(abs(f - int(p[1])) for f, p in zip(feet, pr))
            r["agree_ok"] = r["agree"] <= AGREE_TOL
        npx = sum(int(((f != 0) & (f != fam.outline)).sum()) for f in fr) / len(fr)
        r["model_px"] = round(npx, 1)
        if name == "idle":
            r["shimmer"] = P.shimmer(fr[0], fr[1])
            r["shimmer_frac"] = round(r["shimmer"] / npx, 3)
            r["shimmer_ok"] = SHIMMER[0] <= r["shimmer_frac"] <= SHIMMER[1]
        if name == "walk":
            fb = min(feet)
            leg = slice(max(0, fb - LEG_ROWS + 1), fb + 1)
            pairs = [(0, 1), (1, 2), (2, 3), (3, 0)]
            r["walk_leg_px"] = [P.shimmer(fr[a][leg], fr[b][leg]) for a, b in pairs]
            r["walk_frame_px"] = [P.shimmer(fr[a], fr[b]) for a, b in pairs]
            r["walk_frame_frac"] = round(min(r["walk_frame_px"]) / npx, 3)
            lmin = WALK_LEG_MIN.get(d)
            r["walk_ok"] = (r["walk_frame_frac"] >= WALK_FRAME_FRAC
                            and (lmin is None or min(r["walk_leg_px"]) >= lmin))
        ok = ok and all(v for k, v in r.items() if k.endswith("_ok"))
        rows.append(r)
    used = set(np.unique(np.concatenate([f.ravel() for fr in strips.values() for f in fr])).tolist())
    cover = {}
    for role in fam.roles:
        idx = range(role["lo"], role["hi"] + 1) if role["kind"] == "ramp" else [role["index"]]
        cover[role["name"]] = sorted(set(idx) & used)
    cover_ok = all(cover.values())
    return {"thresholds": {"drift_max": DRIFT_MAX, "lift_max": LIFT_MAX, "agree_tol": AGREE_TOL,
                           "shimmer_frac": list(SHIMMER), "leg_rows": LEG_ROWS,
                           "walk_frame_frac": WALK_FRAME_FRAC, "walk_leg_min": WALK_LEG_MIN},
            "per_action": rows, "role_coverage": cover, "role_coverage_ok": cover_ok,
            "fit_ok": True, "all_ok": ok and cover_ok}


def write_anchors(model, strips, fam, act):
    bw, bh = act["camera"]["box"]
    feet = {f"{n}_{d}": [P.foot_row(f, fam.outline) for f in fr] for (n, d), fr in strips.items()}
    ax, ay = act["rig"]["anchor_px"]
    root_row = int(ay + 0.5)          # the camera puts the root's CENTRE at row ay + 0.5
    doc = {"about": "SuperForge Dungeons actor sprites. anchor_x / anchor_y are the pixel the "
                    "figure's ROOT (the ground point between the feet) lands on in the box, "
                    "identical in every direction; draw a frame at (ground_x - anchor_x, "
                    "ground_y - anchor_y). foot_rows are the MEASURED lowest model row per "
                    "frame: they differ from anchor_y by the stance's depth separation (the "
                    "near foot is lower in a side view), which is geometry, not drift. "
                    "Written by sheets.py (13 §4).",
           "models": {model: {"box_w": bw, "box_h": bh,
                              "anchor_x": int(ax), "anchor_y": root_row,
                              "camera_anchor_px": [ax, ay],
                              "foot_rows": feet}}}
    (HERE / "anchors.json").write_text(json.dumps(doc, indent=1) + "\n")
    return doc


def sheet(model, strips, act, met):
    bw, bh = act["camera"]["box"]
    keys = [(n, d) for n in act["action"] for d in act["camera"]["directions"] if (n, d) in strips]
    ncol = max(len(strips[k]) for k in keys)
    pals = palettes()
    cell = bw * X + 8
    lab = 120
    panel_w = lab + ncol * cell + 16
    W, H = panel_w * len(pals), 34 + len(keys) * (bh * X + 8) + 30
    im = Image.new("RGB", (W, H), (40, 40, 46))
    dr = ImageDraw.Draw(im)
    ay = act["rig"]["anchor_px"][1]
    feet = {(r["action"], r["dir"]): r["foot_rows"] for r in met["per_action"]}
    for pi, (pname, pal, bg) in enumerate(pals):
        x0 = pi * panel_w
        dr.rectangle([x0 + 4, 26, x0 + panel_w - 4, H - 30], fill=bg)
        dr.text((x0 + 8, 8), pname, fill=INK)
        lut = np.array(pal, np.uint8)
        for ri, k in enumerate(keys):
            y = 34 + ri * (bh * X + 8)
            dr.text((x0 + 8, y + bh * X // 2 - 12), f"{k[0]}\n{k[1]}", fill=INK)
            for i, f in enumerate(strips[k]):
                rgb = lut[f]
                tile = np.where((f == 0)[..., None], np.array(bg, np.uint8), rgb)
                t = Image.fromarray(tile.astype(np.uint8), "RGB").resize((bw * X, bh * X), Image.NEAREST)
                cx = x0 + lab + i * cell
                im.paste(t, (cx, y))
                fy = y + feet[k][i] * X + X - 1
                dr.line([cx - 5, fy, cx - 1, fy], fill=(255, 70, 70))
            dr.line([x0 + lab - 14, y + ay * X + X // 2, x0 + lab - 9, y + ay * X + X // 2],
                    fill=(90, 220, 255))
    dr.text((8, H - 22), f"{model}  x{X}   rows = action/direction, columns = frame   "
            f"red tick = measured foot row (bottom edge)   cyan = camera anchor row {ay}   "
            f"metrics: {'PASS' if met['all_ok'] else 'FAIL'}", fill=INK)
    im.save(HERE / f"sheet_{model}.png", optimize=True)


def table(met) -> str:
    lines = ["| action | dir | foot rows | drift | root row agree | shimmer | walk frame px | walk leg px |",
             "|---|---|---|---|---|---|---|---|"]
    for r in met["per_action"]:
        lines.append(f"| {r['action']} | {r['dir']} | {r['foot_rows']} | {r['drift']} | "
                     f"{r.get('agree', '-')} | {r.get('shimmer', '-')} | {r.get('walk_frame_px', '-')} | "
                     f"{r.get('walk_leg_px', '-')} |")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="wanderer")
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args(argv)
    act = tomllib.loads((HERE / "actions.toml").read_text())
    fam = P.load_family("hero")
    strips = load_strips(a.model, act)
    if not strips:
        print("sheets: no strips (run the pixelate stage)", file=sys.stderr)
        return 1
    met = metrics(strips, projected_roots(a.model), fam, act)
    write_anchors(a.model, strips, fam, act)
    sheet(a.model, strips, act, met)
    (HERE / "metrics.json").write_text(json.dumps(met, indent=1) + "\n")
    print(table(met))
    print("role coverage:", {k: v for k, v in met["role_coverage"].items()})
    print(f"sheets: {'PASS' if met['all_ok'] else 'FAIL'}; wrote anchors.json, "
          f"sheet_{a.model}.png, metrics.json")
    return 1 if (a.strict and not met["all_ok"]) else 0


if __name__ == "__main__":
    sys.exit(main())
