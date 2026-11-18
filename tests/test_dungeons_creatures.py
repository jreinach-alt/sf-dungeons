"""SuperForge Dungeons — the creature pipeline (docs/dungeons/16), without Blender.

runtime: ~2 s — pure Python + numpy + Pillow on the committed specs and strips.

The creature kit (art/dungeons/creatures/) makes a new creature a DATA FILE: parts, an IK
limb set, gait / pose actions, a palette. The Blender builder is exercised by
`build_creature.sh`; what a bare clone can prove is everything around it:

  * gaits.py: loop closure, stance feet fixed on the ground, the lateral-sequence walk
    and the tetrapod skitter never leave too few feet down, planted feet stay planted;
  * budget.py: tile counting (with and without flips), the size-class refusal, the
    delta-streaming cost against the measured VBlank budget;
  * spec.py: the committed specs are valid, and each class of mistake is refused with a
    sentence rather than a Blender traceback;
  * the committed strips fit their size class and the family palettes are console-exact;
  * the painter is family-agnostic: a non-hero ramp is outlined by its own darkest step.
"""
import json
import os
import sys
import tomllib

# FIRST, before numpy/Pillow: see test_dungeons_style.py (MesenCore must load before numpy)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "vendor"))
import machine  # noqa: F401,E402

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PIL import Image  # noqa: E402

CRE = os.path.join(os.path.dirname(__file__), "..", "art", "dungeons", "creatures")
sys.path.insert(0, CRE)
sys.path.insert(0, os.path.join(CRE, "..", "style"))
sys.path.insert(0, os.path.join(CRE, "..", "actors"))
import budget as B  # noqa: E402
import gaits as G  # noqa: E402
import paint as PT  # noqa: E402
import spec as SP  # noqa: E402

CREATURES = ["spider", "tortoise"]


def spec(name):
    return SP.load(os.path.join(CRE, "specs", f"{name}.toml"))


# --- gaits ---------------------------------------------------------------------------------
@pytest.mark.parametrize("kind,n", [("tetrapod", 8), ("walk4", 4), ("trot4", 4), ("biped", 2)])
def test_a_gait_loops_exactly(kind, n):
    ph = G.leg_phases(kind, n)
    g = G.gait_frames(8, ph, 0.2, 0.1, 0.6)
    assert len(g["feet"]) == n and all(len(leg) == 8 for leg in g["feet"])
    # one whole cycle later every leg is exactly where it started: the loop closes with no jump
    for p in ph:
        for t in (0.0, 0.13, 0.5, 0.77):
            assert G.foot_offset(p + t, 0.2, 0.1, 0.6) == pytest.approx(G.foot_offset(p + t + 1.0, 0.2, 0.1, 0.6))
    # and the body bob closes too
    assert G.gait_frames(8, ph, 0.2, 0.1, 0.6, bob=0.02)["body_z"][0] == pytest.approx(0.02)


def test_stance_feet_are_on_the_ground_and_slide_at_constant_speed():
    ys = [G.foot_offset(t / 20 * 0.6, 0.3, 0.1, 0.6) for t in range(21)]
    assert all(dz == 0.0 for _, dz in ys), "a stance foot leaves the ground"
    steps = [b[0] - a[0] for a, b in zip(ys, ys[1:])]
    assert max(steps) - min(steps) < 1e-9, "a stance foot's speed is not constant (it would skate)"
    assert ys[0][0] == pytest.approx(-0.15) and ys[-1][0] == pytest.approx(0.15)


def test_a_swing_foot_peaks_at_the_lift_and_returns_to_the_front():
    mid = G.foot_offset(0.6 + 0.4 / 2, 0.3, 0.1, 0.6)
    assert mid[1] == pytest.approx(0.1)
    assert G.foot_offset(0.6 + 1e-9, 0.3, 0.1, 0.6)[0] == pytest.approx(0.15)


@pytest.mark.parametrize("kind,n,duty,min_down", [("walk4", 4, 0.75, 3), ("tetrapod", 8, 0.6, 4), ("trot4", 4, 0.6, 2)])
def test_the_gaits_never_leave_too_few_feet_down(kind, n, duty, min_down):
    ph = G.leg_phases(kind, n)
    for frames in (4, 6, 8, 16):
        g = G.gait_frames(frames, ph, 0.2, 0.1, duty)
        z = [[f[2] for f in leg] for leg in g["feet"]]
        assert G.contact_ok(z, min_down) == [], f"{kind} at {frames} frames has a frame with < {min_down} feet down"


def test_the_walk_is_a_lateral_sequence_not_a_same_side_pair():
    # listed FL, FR, HL, HR: the order the feet LEAVE the ground is FL, HR, FR, HL
    ph = dict(zip(["FL", "FR", "HL", "HR"], G.leg_phases("walk4", 4)))
    order = sorted(ph, key=lambda k: ph[k])
    assert order == ["FL", "HR", "FR", "HL"], order


def test_the_tetrapod_swings_alternate_legs_on_alternate_sides():
    ph = G.leg_phases("tetrapod", 8)                     # L1 R1 L2 R2 L3 R3 L4 R4
    assert ph == [0.0, 0.5, 0.5, 0.0, 0.0, 0.5, 0.5, 0.0]
    for a, b in zip(ph[0::2], ph[1::2]):
        assert a != b, "a left leg and its right partner must not swing together"


def test_a_wrong_leg_count_is_refused_in_a_sentence():
    with pytest.raises(ValueError, match="needs 4 legs"):
        G.leg_phases("walk4", 6)
    with pytest.raises(ValueError, match="unknown gait"):
        G.leg_phases("gallop", 4)


def test_planted_feet_stay_exactly_where_they_were():
    homes = {"a": (1, 2, 0), "b": (-1, 2, 0)}
    fr = [{"a": "home", "b": "home"}, {"a": "plant", "b": {"home": [0, 0, 0.5]}}, {"a": "plant", "b": [9, 9, 9]},
          {"a": "plant", "b": "plant"}]
    out = G.resolve_feet(fr, homes)
    assert [o["a"] for o in out] == [(1, 2, 0)] * 4
    assert out[1]["b"] == (-1, 2, 0.5) and out[2]["b"] == (9, 9, 9) and out[3]["b"] == (9, 9, 9)
    with pytest.raises(ValueError, match="unknown foot instruction"):
        G.resolve_feet([{"a": "float"}], homes)


# --- budget --------------------------------------------------------------------------------
def test_tiles_are_counted_without_the_empty_ones_and_flips_are_one_tile_on_a_bg():
    f = np.zeros((16, 16), np.uint8)
    f[0:8, 0:8] = np.arange(64).reshape(8, 8) % 15 + 1
    f[8:16, 8:16] = f[0:8, 0:8][:, ::-1]                 # the mirror of tile 0
    assert len(B.unique_tiles(f, flips=False)) == 2
    assert len(B.unique_tiles(f, flips=True)) == 1


def test_an_obj_frame_of_the_wrong_size_is_refused():
    with pytest.raises(ValueError, match="not the 32x32"):
        B.report({"x": np.zeros((16, 16), np.uint8)}, "obj32")
    with pytest.raises(ValueError, match="whole number of 8x8"):
        B.split_tiles(np.zeros((10, 16), np.uint8))


def test_a_pose_change_streams_only_the_new_tiles_and_is_costed_in_vblanks():
    rng = np.random.default_rng(1)
    a = rng.integers(1, 15, (64, 64)).astype(np.uint8)
    b = a.copy()
    b[:16, :16] = rng.integers(1, 15, (16, 16))          # four tiles change
    r = B.report({"a": a, "b": b}, "bg")
    assert r["new_tiles_per_transition"]["a->b"] == 4
    assert r["worst_transition_bytes"] == 4 * 32 and r["vblank_frames_for_worst"] == 1
    big = {"a": a, "b": rng.integers(1, 15, (64, 64)).astype(np.uint8)}
    r1 = B.report(big, "bg")
    assert r1["worst_transition_tiles"] == 64 and r1["vblank_frames_for_worst"] == 1     # 2,048 B < 5,952
    full = np.random.default_rng(2).integers(1, 15, (192, 192)).astype(np.uint8)         # 576 random tiles
    r2 = B.report({"a": a, "b": full}, "bg")
    assert r2["worst_transition_tiles"] == 576 and r2["vblank_frames_for_worst"] == 4    # 18,432 B / 5,952 B
    assert r2["pose_fits_buffer"] is False                                               # 576 > the 320-tile buffer


# --- specs ---------------------------------------------------------------------------------
@pytest.mark.parametrize("name", CREATURES)
def test_the_committed_specs_are_valid(name):
    assert SP.validate(spec(name)) == []


def _mut(name, fn):
    s = spec(name)
    fn(s)
    return SP.validate(s)


def test_each_class_of_mistake_is_refused_with_a_sentence():
    cases = [
        (lambda s: s["part"][0].__setitem__("bone", "nope"), "bone 'nope' does not exist"),
        (lambda s: s["part"][0].__setitem__("role", "chrome"), "role 'chrome' not in family"),
        (lambda s: s["action"]["skitter"].__setitem__("gait", "walk4"), "needs 4 legs"),
        (lambda s: s["action"]["idle"]["keys"].__setitem__("body.pitch", [1.0]), "1 values for 2 frames"),
        (lambda s: s["action"]["idle"]["keys"].__setitem__("wing.pitch", [0, 0]), "no bone 'wing'"),
        (lambda s: s["action"]["bite"]["feet"].__setitem__("leg.ZZ", ["home"] * 3), "not a leg of any legset"),
        (lambda s: s["camera"].__setitem__("box", [30, 32]), "must be 32x32"),
        (lambda s: s.__setitem__("size_class", "obj99"), "size_class 'obj99'"),
        (lambda s: s["locator"][0].__setitem__("part", "ghost"), "part 'ghost' does not exist"),
        (lambda s: s["legset"][0]["hip"].pop("L1"), "leg L1 has no hip/foot"),
    ]
    for fn, want in cases:
        errs = _mut("spider", fn)
        assert any(want in e for e in errs), (want, errs)


# --- the committed output ---------------------------------------------------------------------
@pytest.mark.parametrize("name", CREATURES)
def test_every_strip_fits_its_size_class_and_is_a_legal_sprite(name):
    s = spec(name)
    for an, a in s["action"].items():
        p = os.path.join(CRE, "out", name, f"{an}_down.png")
        im = Image.open(p)
        bw, bh = a.get("box", s["camera"]["box"])
        assert im.mode == "P" and im.info.get("transparency") == 0
        assert im.size == (a["frames"] * bw, bh), (p, im.size)
        assert int(np.asarray(im).max()) <= 15


@pytest.mark.parametrize("name", CREATURES)
def test_the_palette_is_console_exact(name):
    with open(os.path.join(CRE, "out", name, "palettes.json")) as f:
        pal = json.load(f)
    for k, cols in pal.items():
        assert len(cols) == 16 and cols[0] == [0, 0, 0]
        for c3 in cols:
            for c in c3:
                assert c == ((c >> 3) << 3 | (c >> 3) >> 2), f"{name} {k}: {c} is not BGR555"


def test_the_committed_budgets_say_the_creatures_fit():
    sp = json.load(open(os.path.join(CRE, "out", "spider", "budget.json")))
    assert sp["class"] == "obj32" and sp["oam_entries_per_actor"] == 1 and sp["max_tiles_one_frame"] <= 16
    to = json.load(open(os.path.join(CRE, "out", "tortoise", "budget.json")))
    assert to["pose_fits_buffer"] and to["max_unique_tiles_one_pose"] <= B.BG_CHR_TILES
    assert to["vblank_frames_for_worst"] == 1, "a pose change should stream inside ONE VBlank (5,952 B)"


def test_the_budget_report_matches_the_strips_it_describes():
    """The committed budget.json is a measurement of the committed pixels: recompute it."""
    import report
    for n in CREATURES:
        _, r = report.run(n)
        old = json.load(open(os.path.join(CRE, "out", n, "budget.json")))
        assert old["unique_tiles_all"] == r["unique_tiles_all"] and old["per_frame"] == r["per_frame"]


# --- the painter is family-agnostic ----------------------------------------------------------------
def test_a_non_hero_ramp_is_outlined_by_its_own_darkest_step():
    st = spec("spider")
    p = PT.Painter(st)
    carapace = p.by_name["carapace"]
    assert p.omap[carapace["material"]] == carapace["lo"]            # selout: its own darkest step
    assert p.omap_lit[carapace["material"]] == carapace["lo"] + 1
    eye = p.by_name["eye"]
    assert p.omap[eye["material"]] == p.fam.outline                  # a fixed role: the family outline


def test_the_hero_painter_keeps_its_historical_outline_table():
    hero = tomllib.loads(open(os.path.join(CRE, "..", "style", "styles", "a_storybook.toml")).read())
    p = PT.Painter(hero)
    assert p.omap[p.by_name["cloak"]["material"]] == 1 and p.omap[p.by_name["skin"]["material"]] == 10


def test_a_style_can_leave_thin_parts_without_an_outline_ring():
    st = dict(spec("spider"))
    p = PT.Painter(st)
    assert p.no_outline == {p.by_name["leg"]["material"]}
