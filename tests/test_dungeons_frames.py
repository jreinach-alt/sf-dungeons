"""SuperForge Dungeons — the COMMITTED actor frames and the pose data, without Blender.

runtime: ~1 s — numpy + Pillow on the tracked PNGs, no Blender, no ROM.

The model spike (docs/dungeons/14) rendered the wanderer in Blender and
committed the INDEXED strips (art/dungeons/actors/frames/). The build never
runs Blender, so the strips are the source of truth downstream; these tests
pin what they must satisfy: shape, the palette-role contract, the measured
anchor, and 13 §4's metrics recomputed from the pixels. A retune of
actions.toml that re-renders the strips must keep this file green.

The pose-channel semantics the Blender script keys (lag-by-one cloak, the
per-direction override tables) live in pose_data.py, which has no Blender
dependency, so they are pinned here too.
"""
import json
import os
import sys
import tomllib

import numpy as np
import pytest
from PIL import Image

ACTORS = os.path.join(os.path.dirname(__file__), "..", "art", "dungeons", "actors")
sys.path.insert(0, ACTORS)
import pixelate_actor as P  # noqa: E402
import pose_data as D  # noqa: E402
import sheets as S  # noqa: E402

DIRS = ("right", "up", "down")


@pytest.fixture(scope="module")
def act():
    with open(os.path.join(ACTORS, "actions.toml"), "rb") as f:
        return tomllib.load(f)


@pytest.fixture(scope="module")
def fam():
    return P.load_family("hero")


@pytest.fixture(scope="module")
def strips(act):
    return S.load_strips("wanderer", act)


# --- pose data ---------------------------------------------------------------
def test_actions_toml_names_only_real_bones_and_kinds(act):
    assert D.check(act) == []


def test_check_names_a_bad_channel(act):
    bad = json.loads(json.dumps(act))
    bad["action"]["walk"]["keys"]["tail.pitch"] = [0, 0, 0, 0]
    bad["action"]["walk"]["dir"]["left"] = {}
    bad["action"]["idle"]["keys"]["head.yaw"] = [0, 0]
    errs = D.check(bad)
    assert any("no bone 'tail'" in e for e in errs)
    assert any("left: not a camera direction" in e for e in errs)
    assert any("kind 'yaw'" in e for e in errs)


def test_cloak_channels_lag_the_body_by_one_sample(act):
    walk = act["action"]["walk"]
    seq = walk["keys"]["cloak.1.pitch"]
    for i in range(walk["frames"]):
        v = D.action_values(walk, i, "right")
        assert v["cloak.1.pitch"] == seq[(i - 1) % walk["frames"]]     # wraps at 0
        assert v["thigh.L.pitch"] == walk["keys"]["thigh.L.pitch"][i]  # no lag


def test_direction_tables_replace_only_their_own_channels(act):
    walk = act["action"]["walk"]
    for d in ("up", "down"):
        over = walk["dir"][d]
        v = D.action_values(walk, 0, d)
        for ch, seq in over.items():
            assert v[ch] == seq[0]
        assert v["upperarm.L.pitch"] == walk["keys"]["upperarm.L.pitch"][0]
    assert D.action_values(walk, 0, "right")["thigh.L.pitch"] == walk["keys"]["thigh.L.pitch"][0]


# --- the committed strips ------------------------------------------------------
def test_every_spike_strip_exists_indexed_with_index0_transparent(act):
    bw, bh = act["camera"]["box"]
    for name in ("idle", "walk"):
        for d in DIRS:
            p = os.path.join(ACTORS, "frames", f"wanderer_{name}_{d}.png")
            im = Image.open(p)
            assert im.mode == "P", p
            assert im.size == (bw * act["action"][name]["frames"], bh), p
            assert im.info.get("transparency") == 0, p


def test_strips_use_only_role_table_indices(strips, fam):
    legal = {0, fam.outline, fam.shadow}
    for r in fam.roles:
        legal |= set(range(r["lo"], r["hi"] + 1)) if r["kind"] == "ramp" else {r["index"]}
    for k, fr in strips.items():
        for f in fr:
            assert set(np.unique(f).tolist()) <= legal, k


def test_metrics_recomputed_from_the_pixels_pass(strips, fam, act):
    met = S.metrics(strips, {}, fam, act)
    bad = [r for r in met["per_action"] if not all(v for k, v in r.items() if k.endswith("_ok"))]
    assert bad == [] and met["role_coverage_ok"], (bad, met["role_coverage"])


def test_published_anchor_is_the_measured_foot_row(strips, fam, act):
    with open(os.path.join(ACTORS, "anchors.json")) as f:
        doc = json.load(f)["models"]["wanderer"]
    feet = {P.foot_row(f, fam.outline) for fr in strips.values() for f in fr}
    assert feet == {doc["anchor_y"]} == {act["rig"]["anchor_px"][1]}


def test_the_drift_metric_fires_on_a_one_row_slide(strips, fam, act):
    # falsification: lift one walk frame by a row (the defect the spike
    # measured when the down-walk used the full side-view stride)
    planted = dict(strips)
    fr = [f.copy() for f in strips[("walk", "down")]]
    fr[1] = np.roll(fr[1], -1, axis=0)
    planted[("walk", "down")] = fr
    rows = {(r["action"], r["dir"]): r for r in S.metrics(planted, {}, fam, act)["per_action"]}
    assert rows[("walk", "down")]["drift"] == 1 and not rows[("walk", "down")]["drift_ok"]


def test_the_walk_metric_fires_on_a_frozen_walk(strips, fam, act):
    planted = dict(strips)
    planted[("walk", "right")] = [strips[("walk", "right")][0]] * 4
    rows = {(r["action"], r["dir"]): r for r in S.metrics(planted, {}, fam, act)["per_action"]}
    assert not rows[("walk", "right")]["walk_ok"]
