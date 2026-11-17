"""dgn_hero — the model spike's wanderer, on the console.

runtime: ~15 s — lockstep Machine boots, dominated by the per-frame OAM walks.

The spike (docs/dungeons/14) proved the art in Blender and in Python. This
module proves it on the machine. Each figure is 16x32, drawn as TWO stacked
16x16 OBJs (16x32 is not a standard OBJ size): the committed indexed strips
reach OBJ VRAM intact, the P1/P2 palettes reach CGRAM as the role contract says, the walk
and idle advance on actions.toml's holds, and the PICTURE is the strips'
pixels at the measured anchor, the left facing being the right one mirrored.

Lockstep `Machine` only: every read is a parked, exact frame, and the
screenshot is landed on an absolute one. Every address is read out of the
rail's emitted symbol_map.json.
"""
import json
import sys
import tomllib
from pathlib import Path

SUPERFORGE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SUPERFORGE / "vendor"))
# FIRST, before numpy/Pillow: mesen_runner dlopens MesenCore.so at import and
# must do so before numpy's bundled libraries load (its own comment). Imported
# the other way round, collection segfaults inside ctypes (measured here).
from machine import Machine, MemoryType  # noqa: E402

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PIL import Image  # noqa: E402

from conftest import run_make  # noqa: E402
from frame_geometry import PICTURE_TOP  # noqa: E402

BUILD = SUPERFORGE / "build"
ROM = BUILD / "dgn_hero.sfc"
ASSETS = BUILD / "assets"
ACTORS = SUPERFORGE / "art" / "dungeons" / "actors"
_JMAP = json.loads((SUPERFORGE / "build" / "dgnh" / "symbol_map.json").read_text())

V, C, O = MemoryType.SnesVideoRam, MemoryType.SnesCgRam, MemoryType.SnesSpriteRam


def _sym(name, scene=None):
    pool = (_JMAP["scenes"][scene]["placements"] if scene else _JMAP["globals"])
    for p in pool:
        if p["sym"] == name:
            return p
    raise KeyError(f"{name} is not in the emitted map")


V_OBJ = _sym("ES_V_OBJ_CHR", "show")["start"]          # VRAM word address
V_OBJ_W = _sym("ES_V_OBJ_CHR", "show")["size"]
C_OBJ = _sym("ES_C_OBJ_PAL", "show")["start"]          # CGRAM word index
OAM_ACTORS = _sym("ES_O_ACTORS", "show")["start"]      # first sprite slot
OAM_HI_BASE = 512
BOOT = 120
BOX_W, BOX_H = ACT_BOX = (16, 32)

ACT = tomllib.loads((ACTORS / "actions.toml").read_text())
ANCHOR = json.loads((ACTORS / "anchors.json").read_text())["models"]["wanderer"]
AX, AY = ANCHOR["anchor_x"], ANCHOR["anchor_y"]
assert tuple(ACT["camera"]["box"]) == (BOX_W, BOX_H)
# Blob order (tools/gen_dgn_hero_assets.py STRIPS) and the lineup
# (dgnh_obj.asm's actor table): (slot, action, dir, hflip, palette)
ORDER = [("idle", "right"), ("idle", "up"), ("idle", "down"),
         ("walk", "right"), ("walk", "up"), ("walk", "down")]
LINEUP = [(0, "walk", "right", False, 0), (1, "walk", "right", True, 0),
          (2, "walk", "up", False, 0), (3, "walk", "down", False, 0),
          (4, "idle", "right", False, 1), (5, "idle", "right", True, 1),
          (6, "idle", "up", False, 1), (7, "idle", "down", False, 1)]
WALKER = 8
COLS = [56 + 48 * c for c in range(4)]                 # dgnh.inc foot x
ROWS = {"walk": 84, "idle": 132}                       # dgnh.inc foot y


def _strip(action, d):
    a = np.asarray(Image.open(ACTORS / "frames" / f"wanderer_{action}_{d}.png"))
    return [a[:, i * BOX_W:(i + 1) * BOX_W] for i in range(ACT["action"][action]["frames"])]


FRAMES = [f for a, d in ORDER for f in _strip(a, d)]   # blob frame index -> 16x32
FIRST = {}
for _a, _d in ORDER:
    FIRST[(_a, _d)] = sum(ACT["action"][a]["frames"] for a, d in ORDER[:ORDER.index((_a, _d))])


def _name_of(f):
    """The TOP half's name: 8 frames per band of 4 tile rows of the 16-wide table."""
    return (f % 8) * 2 + (f // 8) * 64


def _frame_of(name):
    return (name // 64) * 8 + (name % 64) // 2


def _entry(m, e):
    """OAM entry e (absolute slot): (x with X9, y, name, attr, large)."""
    x, y, name, attr = m.read_bytes(O, e * 4, 4)
    hi = m.read_byte(O, OAM_HI_BASE + e // 4)
    bits = (hi >> ((e % 4) * 2)) & 3
    return x | ((bits & 1) << 8), y, name, attr, bits >> 1


def _oam(m, actor):
    """An actor's TOP half. Each actor is two slots: top at 2*actor, bottom next."""
    return _entry(m, OAM_ACTORS + 2 * actor)


def _oam_bottom(m, actor):
    return _entry(m, OAM_ACTORS + 2 * actor + 1)


def _decode_tile(b):
    t = np.zeros((8, 8), np.uint8)
    for y in range(8):
        p = (b[2 * y], b[2 * y + 1], b[16 + 2 * y], b[16 + 2 * y + 1])
        for x in range(8):
            t[y, x] = sum(((p[k] >> (7 - x)) & 1) << k for k in range(4))
    return t


@pytest.fixture(scope="module", autouse=True)
def rom_built():
    r = run_make("dgn_hero")
    assert r.returncode == 0, f"make dgn_hero failed rc={r.returncode}:\n{r.stdout}\n{r.stderr}"
    yield


@pytest.fixture(autouse=True)
def hand_back_the_core():
    yield
    Machine.close_current()


@pytest.fixture
def fresh():
    return Machine(str(ROM)).advance(BOOT)


# --- 1. the uploads ------------------------------------------------------------
def test_obj_chr_is_the_converted_blob(fresh):
    want = (ASSETS / "dgnh_obj_chr.bin").read_bytes()
    assert len(want) == V_OBJ_W * 2, "the blob does not fill the vram claim"
    assert fresh.read_bytes(V, V_OBJ * 2, len(want)) == want


def test_vram_decodes_back_to_the_committed_strips(fresh):
    """Independent of the converter: VRAM's 16x32 frames ARE the PNG pixels."""
    raw = fresh.read_bytes(V, V_OBJ * 2, V_OBJ_W * 2)
    for f, want in enumerate(FRAMES):
        n = _name_of(f)
        got = np.zeros((BOX_H, BOX_W), np.uint8)
        for ty in range(BOX_H // 8):
            for tx in range(2):
                t = n + ty * 16 + tx
                got[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8] = _decode_tile(raw[t * 32:t * 32 + 32])
        assert (got == want).all(), f"frame {f}: VRAM differs from the committed strip"


def test_palettes_are_p1_and_p2_and_differ_only_in_the_hero_ramps(fresh):
    want = (ASSETS / "dgnh_obj_pal.bin").read_bytes()
    got = fresh.read_bytes(C, C_OBJ * 2, 64)
    assert got == want
    w = [int.from_bytes(got[i:i + 2], "little") for i in range(0, 64, 2)]
    p1, p2 = w[:16], w[16:]
    diff = [i for i in range(16) if p1[i] != p2[i]]
    assert diff == list(range(1, 8)), f"P1/P2 must differ in exactly 1-7 (11 §6), got {diff}"


# --- 2. the animation, read off OAM ------------------------------------------------
def _runs(seq):
    out, k = [], 0
    for i in range(1, len(seq) + 1):
        if i == len(seq) or seq[i] != seq[k]:
            out.append((seq[k], i - k))
            k = i
    return out


@pytest.mark.parametrize("slot,action,d", [(0, "walk", "right"), (6, "idle", "up")])
def test_frames_advance_on_the_actions_toml_holds(slot, action, d):
    hold, n = ACT["action"][action]["hold"], ACT["action"][action]["frames"]
    m = Machine(str(ROM)).advance(BOOT)
    names = []
    for _ in range(sum(hold) * 2 + 2):
        names.append(_oam(m, slot)[2])
        m.advance(1)
    runs = _runs([_frame_of(x) - FIRST[(action, d)] for x in names])[1:-1]   # drop partials
    assert runs, "no complete hold observed"
    for (i, length), (j, _) in zip(runs, runs[1:]):
        assert j == (i + 1) % n, f"frame order {runs}"
    for i, length in runs:
        assert length == hold[i], f"frame {i} held {length}, actions.toml says {hold[i]}: {runs}"


# --- 3. the picture ------------------------------------------------------------------
def _to_index(rgb, pal_words):
    """Screenshot RGB -> palette index by nearest BGR555 colour."""
    cols = np.array([[(w & 31) * 255 // 31, ((w >> 5) & 31) * 255 // 31,
                      ((w >> 10) & 31) * 255 // 31] for w in pal_words], float)
    d = ((rgb[:, :, None, :].astype(float) - cols[None, None]) ** 2).sum(-1)
    idx = d.argmin(-1)
    assert d.min(-1).max() < 3 * 12 ** 2, "a pixel matches no palette colour"
    return idx


def test_the_screen_is_the_strip_frames_at_the_anchor(fresh, tmp_path):
    shot = tmp_path / "f.png"
    fresh.screenshot(str(shot))
    img = np.asarray(Image.open(shot).convert("RGB"))
    cg = fresh.read_bytes(C, 0, 512)
    words = [int.from_bytes(cg[i:i + 2], "little") for i in range(0, 512, 2)]
    for slot, action, d, flip, pal in LINEUP:
        x, y, name, attr, large = _oam(fresh, slot)
        bx, by, bname, battr, blarge = _oam_bottom(fresh, slot)
        # the bottom half: same x, attr and size, one 16x16 lower, two tile rows on
        assert (bx, bname, battr, blarge) == (x, name + 32, attr, large) and by == (y + 16) & 255
        assert large == 1 and bool(attr & 0x40) == flip and (attr >> 1) & 7 == pal
        f = _frame_of(name)
        assert FIRST[(action, d)] <= f < FIRST[(action, d)] + ACT["action"][action]["frames"]
        foot_x = COLS[slot % 4]
        assert x == foot_x - ((BOX_W - 1 - AX) if flip else AX), f"slot {slot}: x off the anchor"
        assert y == ROWS[action] - AY - 1, f"slot {slot}: y off the anchor"
        want = FRAMES[f][:, ::-1] if flip else FRAMES[f]
        crop = img[PICTURE_TOP + y:PICTURE_TOP + y + BOX_H, x:x + BOX_W]
        got = _to_index(crop, [words[0]] + words[128 + 16 * pal + 1:128 + 16 * pal + 16])
        assert (got == want).all(), f"slot {slot} ({action} {d}{' flipped' if flip else ''}) " \
                                    f"renders differently from frame {f}"


def test_the_walker_moves_at_ground_speed_and_wraps():
    m = Machine(str(ROM)).advance(BOOT)
    x0 = _oam(m, WALKER)[0]
    m.advance(64)
    x1 = _oam(m, WALKER)[0]
    # OAM x runs -16..255 and wraps with period 256 + 16 = 272 (dgnh.inc).
    # A 64-frame window can span the wrap (measured: 212 -> 36), so the
    # distance is taken modulo the period: the 9-bit OAM x reads -16..-1 as
    # 496..511, hence the signed fold first.
    def signed(x):
        return x - 512 if x >= 256 + 16 else x
    assert (signed(x1) - signed(x0)) % 272 == 96, \
        f"64 frames at 1.5 px/frame: {x0} -> {x1}"
    xs = []
    for _ in range(200):
        m.advance(1)
        xs.append(_oam(m, WALKER)[0])
    assert any(x >= 496 for x in xs), "the walker never re-entered from the left (X9 never set)"
    for _ in range(80):                       # both halves wrap together, X9 included
        m.advance(1)
        assert _oam(m, WALKER)[0] == _oam_bottom(m, WALKER)[0], "the walker's halves disagree on x"
    assert all(x < 256 or x >= 496 for x in xs), f"the walker left the -16..255 band: {xs}"
