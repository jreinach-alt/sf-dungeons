"""SuperForge Dungeons — the art-direction spike: committed styles and the painter, without Blender.

runtime: ~3 s — numpy + Pillow on the tracked strips and synthetic data frames.

The art-direction spike (docs/dungeons/15) re-did the wanderer as three
treatments through a PAINTERLY stage (art/dungeons/style/paint.py) instead of
the spike's area-average. The build never runs Blender, so what is committed
is the source of truth, and this file pins what it must satisfy:

  * every committed strip is a legal sprite (indexed, 4bpp, index 0 transparent,
    the box size, two facings of idle / walk / attack);
  * every palette is exactly representable on the console (BGR555) and P1 / P2
    differ in entries 1-7 only, so the same indices repaint the hero (11 §4);
  * the painter's RULES hold on synthetic data frames: selective outlines are the
    enclosed material's dark step (never the flat outline index), orphan pixels
    fold into their band, stamps land only on the figure, overrides are applied
    last and refuse an out-of-box pixel;
  * the Hollow Wood mock stays inside one BG palette and is deterministic.
"""
import json
import os
import sys
import tomllib

# FIRST, before numpy/Pillow: vendor/mesen_runner dlopens MesenCore.so on import and must do so
# before numpy's bundled libraries load, or collection segfaults inside ctypes whenever this
# module is collected ahead of an emulator test (measured). This module needs no emulator; the
# import is only what makes it safe to run in any order.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "vendor"))
import machine  # noqa: F401,E402

import numpy as np
import pytest
from PIL import Image

STYLE = os.path.join(os.path.dirname(__file__), "..", "art", "dungeons", "style")
sys.path.insert(0, STYLE)
sys.path.insert(0, os.path.join(STYLE, "..", "actors"))
import paint as PT  # noqa: E402
import room as RM  # noqa: E402

STYLES = ["a_storybook", "b_practical", "c_painted16"]
ACTIONS = {"idle": (2, 16), "walk": (4, 16), "attack": (3, 32)}      # frames, frame width
FACINGS = ("right", "down")
BOX_H = 32


def style(name):
    with open(os.path.join(STYLE, "styles", f"{name}.toml"), "rb") as f:
        return tomllib.load(f)


# --- the committed strips ----------------------------------------------------------
@pytest.mark.parametrize("name", STYLES)
def test_every_strip_is_a_legal_sprite(name):
    for an, (n, bw) in ACTIONS.items():
        for d in FACINGS:
            p = os.path.join(STYLE, "out", name, f"{an}_{d}.png")
            im = Image.open(p)
            assert im.mode == "P", p
            assert im.size == (n * bw, BOX_H), (p, im.size)
            assert im.info.get("transparency") == 0, p
            assert int(np.asarray(im).max()) <= 15, f"{p}: an index beyond 4bpp"


@pytest.mark.parametrize("name", STYLES)
def test_palettes_are_console_exact_and_swap_only_the_cloak_and_trim(name):
    with open(os.path.join(STYLE, "out", name, "palettes.json")) as f:
        pal = json.load(f)
    for k in ("p1", "p2"):
        assert len(pal[k]) == 16 and pal[k][0] == [0, 0, 0]
        for r, g, b in pal[k]:
            for c in (r, g, b):                     # 5-bit channel expanded: c5<<3 | c5>>2
                c5 = c >> 3
                assert c == (c5 << 3 | c5 >> 2), f"{name} {k}: {c} is not a BGR555 value"
    diff = [i for i in range(16) if pal["p1"][i] != pal["p2"][i]]
    assert diff == list(range(1, 8)), f"P1/P2 must differ in 1-7 only (11 §4), got {diff}"


@pytest.mark.parametrize("name", STYLES)
def test_the_two_palettes_keep_their_identity(name):
    """P1 reads blue (dusk blue, silver trim), P2 reads warm (amber, copper trim)."""
    with open(os.path.join(STYLE, "out", name, "palettes.json")) as f:
        pal = json.load(f)
    mid1, mid2 = pal["p1"][3], pal["p2"][3]
    assert mid1[2] > mid1[0] + 20, f"{name}: P1 cloak is not blue"
    assert mid2[0] > mid2[2] + 60, f"{name}: P2 cloak is not warm"


def test_the_treatments_are_not_the_same_sprite():
    """Three treatments, not three palettes of one: their silhouettes must differ."""
    masks = []
    for name in STYLES:
        a = np.asarray(Image.open(os.path.join(STYLE, "out", name, "idle_down.png")))[:, :16] != 0
        masks.append(a)
    for i in range(3):
        for j in range(i + 1, 3):
            assert (masks[i] != masks[j]).sum() >= 18, f"{STYLES[i]} and {STYLES[j]} share a silhouette"


# --- the painter, on synthetic data frames ----------------------------------------------
SS, M, BOX = 4, 4, (16, 32)
CAN_W, CAN_H = (BOX[0] + 2 * M), (BOX[1] + 2 * M)


def blank():
    return np.zeros((CAN_H * SS, CAN_W * SS, 3), np.uint8)


def block(raw, x, y, w, h, mat, sun=200, sky=128):
    raw[y * SS:(y + h) * SS, x * SS:(x + w) * SS] = (sun, mat, sky)


@pytest.fixture(scope="module")
def painter():
    return PT.Painter(style("a_storybook"))


def test_the_outline_is_the_enclosed_materials_dark_step_not_flat_black(painter):
    raw = blank()
    block(raw, 8, 8, 6, 10, 2, sun=120)                  # a cloak: canvas x 8..13, y 8..17
    out = painter.paint(raw, SS, M, BOX, {}, "down", "synthetic")
    ring = out[3, 4:10]                                  # box coords = canvas - margin: the row above
    assert (ring != 0).all()
    assert set(ring.tolist()) <= {1, 2}, f"a cloak's outline is its darkest steps (1, or 2 where lit), got {ring}"
    assert 15 not in ring.tolist()


def test_a_lone_pixel_of_another_step_folds_into_its_band():
    # smoothing OFF: the cluster stage is then the only thing between a stray
    # pixel and the sprite (with smoothing on, the shading blur hides a planted defect)
    st = dict(style("a_storybook"))
    st["paint"] = dict(st["paint"], smooth=0.0)
    raw = blank()
    block(raw, 6, 6, 10, 14, 2, sun=130)                 # a flat cloak band
    block(raw, 10, 12, 1, 1, 2, sun=255, sky=255)        # one bright orphan pixel
    out = PT.Painter(st).paint(raw, SS, M, BOX, {}, "down", "synthetic")
    inner = out[5:12, 4:10]                              # box coords, clear of the lit edge ring
    assert len(set(inner.flatten().tolist())) == 1, f"the orphan survived: {inner}"


def test_contact_shadow_where_the_cloak_passes_over_the_tunic(painter):
    raw = blank()
    block(raw, 6, 6, 8, 14, 5, sun=200)                  # leather tunic: canvas x 6..13
    block(raw, 6, 6, 3, 14, 2, sun=200)                  # a cloak edge over its left: canvas x 6..8
    out = painter.paint(raw, SS, M, BOX, {}, "down", "synthetic")
    seam = out[8, 5]                                     # box (5, 8): the leather pixel beside the cloak
    assert seam == 10, f"the tunic's seam pixel should be its darkest step (10), got {seam}"


def test_stamps_land_on_the_figure_only(painter):
    raw = blank()
    block(raw, 8, 8, 6, 10, 2, sun=160)
    st = dict(painter.style)
    st["stamp"] = {"face_down": [[0, 0, 7], [20, 0, 7]]}
    p2 = PT.Painter(st)
    out = p2.paint(raw, SS, M, BOX, {"head": [7.0 + M, 8.0 + M]}, "down", "synthetic")   # box (7, 8)
    assert out[8, 7] == 7, "the stamp on the figure is drawn"
    assert (out == 7).sum() == 1, "a stamp placed off the figure must be dropped, not drawn on the void"


def test_overrides_apply_last_and_refuse_an_out_of_box_pixel():
    sprite = np.zeros((32, 16), np.uint8)
    st = {"override": {"idle_down_0": {"px": [[3, 4, 9]]}}}
    out = PT.apply_overrides(sprite, st, "idle_down_0")
    assert out[4, 3] == 9 and out.sum() == 9
    assert PT.apply_overrides(sprite, st, "walk_right_1") is sprite           # no entry: untouched
    with pytest.raises(ValueError, match="outside"):
        PT.apply_overrides(sprite, {"override": {"x": {"px": [[16, 0, 1]]}}}, "x")
    with pytest.raises(ValueError, match="4bpp"):
        PT.apply_overrides(sprite, {"override": {"x": {"px": [[0, 0, 16]]}}}, "x")


def test_the_painter_refuses_a_figure_outside_the_box(painter):
    raw = blank()
    block(raw, 0, 8, 6, 10, 2, sun=160)                  # runs off the left edge of the box
    with pytest.raises(ValueError, match="outside the 16x32 box"):
        painter.paint(raw, SS, M, BOX, {}, "down", "synthetic")


def test_the_painter_is_deterministic(painter):
    raw = blank()
    block(raw, 6, 6, 8, 16, 2, sun=150)
    block(raw, 7, 8, 3, 3, 4, sun=90)
    a = painter.paint(raw, SS, M, BOX, {}, "down", "synthetic")
    b = PT.Painter(style("a_storybook")).paint(raw, SS, M, BOX, {}, "down", "synthetic")
    assert (a == b).all()


# --- the Hollow Wood mock ------------------------------------------------------------------
def test_the_room_fits_one_bg_palette_and_is_deterministic():
    a, b = RM.build(), RM.build()
    assert a.shape == (224, 256) and (a == b).all()
    assert len({int(v) for v in np.unique(a)}) <= 15, "one BG palette holds 15 colours"
    rgb = RM.to_rgb(a)
    for c in np.unique(rgb.reshape(-1, 3), axis=0):
        for ch in c:
            assert int(ch) == ((int(ch) >> 3) << 3 | (int(ch) >> 3) >> 2), "a BG colour is not BGR555"
