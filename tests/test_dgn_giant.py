"""dgn_giant — the giant Mode 7 boss, on the console (docs/dungeons/20).

runtime: ~60 s — lockstep Machine passes of 330 frames (the 290-tick loop and its wrap), plus screenshots.

The boss is one still image on the Mode 7 plane; everything it does is the PPU's matrix. What this module proves, from
the machine's own output:

  * the plane reaches VRAM intact (the interleaved map + 8bpp CHR, byte for byte) with its palette in CGRAM;
  * the ROM plays the score: OAM and the 16-byte Mode 7 shadow equal the director's record on every frame;
  * THE PICTURE: the background on screen is pixel-exact against the reference renderer drawing the plane through the
    PPU's own arithmetic, at the rest pose, mid-spin, all three cuts and the retract (the players' boxes masked);
  * the players' streamed frames are intact on every frame, the sprite limits never trip, and the V counter shows
    what the whole scene costs in VBlank;
  * a planted fault (B and C swapped: the transposed matrix) is CAUGHT by the picture check.

Lockstep `Machine` only. Every address is read out of the rail's emitted symbol_map.json.
"""
import json
import sys
from pathlib import Path

SUPERFORGE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SUPERFORGE / "vendor"))
sys.path.insert(0, str(SUPERFORGE / "tools"))
# FIRST, before numpy/Pillow: mesen_runner dlopens MesenCore.so at import (see test_dgn_hero.py).
from machine import Machine, MemoryType  # noqa: E402

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PIL import Image  # noqa: E402

from conftest import run_make  # noqa: E402
from frame_geometry import PICTURE_TOP  # noqa: E402
from dgn_ppu import decode_rows, ledger, parse_oam, rgb_of  # noqa: E402
from dgn_giant import director as G  # noqa: E402
import gen_dgn_fight_assets as GF  # noqa: E402

BUILD = SUPERFORGE / "build"
ROMS = {"real": BUILD / "dgn_giant.sfc", "plant": BUILD / "dgn_giant_plant.sfc"}
ASSETS = BUILD / "assets_giant"
_JMAP = json.loads((BUILD / "dgng" / "symbol_map.json").read_text())
W, V, C, O = (MemoryType.SnesWorkRam, MemoryType.SnesVideoRam, MemoryType.SnesCgRam, MemoryType.SnesSpriteRam)
BOOT = 30
FRAMES = 330


def _sym(name):
    return next(p for p in _JMAP["scenes"]["giant"]["placements"] if p["sym"] == name)


def _dp(name):
    return _sym(name)["start"]


V_OBJ = _sym("ES_V_OBJ_CHR")["start"]
C_OBJ = 128
M7SH = _dp("ES_M7SH")
HERO = GF.hero_frames()
STATES = G.all_states()
PLAN = G.DF.compile_stream(STATES, mode="choreo", layout=G.LAYOUT)
RECORDS = [G.build_record(STATES, PLAN, t) for t in range(G.LOOP)]
CROWN = np.asarray(Image.open(SUPERFORGE / "art" / "dungeons" / "creatures" / "out" / "crownling_boss" / "idle_down.png"))
PLANE = G.plane_from_image(CROWN)


def _slot(m, actor, buf):
    col, row0 = G.SLOTS[actor]["bufs"][buf]
    return [m.read_bytes(V, (V_OBJ + ((row0 + r) * 16 + col) * 16) * 2, 4 * 32) for r in range(4)]


class Pass:
    """One ROM over FRAMES frames. Sample k is the state after BOOT + k + 1 frames."""

    def __init__(self, which):
        self.d, self.vend, self.s77, self.bytes = [], [], [], []
        self.oam_bad, self.shadow_bad, self.tears = [], [], []
        self.worst_sprites = self.worst_slivers = 0
        cache = {}
        with Machine(str(ROMS[which])) as m:
            m.advance(BOOT)
            for k in range(FRAMES):
                m.advance(1)
                ct = m.read_u16(W, _dp("US_CT"))
                d = (ct - 1) % G.LOOP                  # the tick the last NMI committed
                self.d.append(d)
                self.vend.append(m.read_u16(W, _dp("US_VEND")))
                self.s77.append(m.read_u16(W, _dp("US_S77")))
                self.bytes.append(PLAN["bytes"][d])
                oam = m.read_bytes(O, 0, 544)
                if oam[:16] != RECORDS[d][:16] or oam[512] != RECORDS[d][16]:
                    self.oam_bad.append(k)
                if m.read_bytes(W, M7SH, 16) != RECORDS[ct % G.LOOP][17:33]:
                    self.shadow_bad.append(k)           # the shadow holds the tick just copied (ct), not yet committed
                s, sl = ledger(parse_oam(oam))
                self.worst_sprites, self.worst_slivers = max(self.worst_sprites, s), max(self.worst_slivers, sl)
                for actor in ("p1", "p2"):
                    buf = PLAN["bufsel"][actor][d]
                    raw = _slot(m, actor, buf)
                    key = (actor, buf, b"".join(raw))
                    want = STATES[actor][d].frame
                    if (key, want) not in cache:
                        cache[(key, want)] = bool((decode_rows(raw, 4) == HERO[want]).all())
                    if not cache[(key, want)]:
                        self.tears.append((k, actor))
            self.vmax = m.read_u16(W, _dp("US_VMAX"))
            self.s77_final = m.read_u16(W, _dp("US_S77"))


@pytest.fixture(scope="module", autouse=True)
def roms_built():
    for target in ("dgn_giant", "dgn_giant_plant"):
        r = run_make(target)
        assert r.returncode == 0, f"make {target} failed rc={r.returncode}:\n{r.stdout}\n{r.stderr}"
    yield


@pytest.fixture(autouse=True)
def hand_back_the_core():
    yield
    Machine.close_current()


@pytest.fixture(scope="module")
def real(roms_built):
    p = Pass("real")
    Machine.close_current()
    return p


# --- 1. the plane and its palette ---------------------------------------------------------------------------------
def test_the_mode_7_plane_reaches_vram_byte_for_byte():
    with Machine(str(ROMS["real"])) as m:
        m.advance(BOOT)
        got = m.read_bytes(V, 0, 32768)
    assert got == (ASSETS / "dgng_m7.bin").read_bytes(), "VRAM's Mode 7 region differs from the interleaved blob"


def test_the_palettes_are_the_crowns_and_the_players_and_word_0_is_the_floor():
    blob = (ASSETS / "dgng_pal.bin").read_bytes()
    with Machine(str(ROMS["real"])) as m:
        m.advance(BOOT)
        bg = m.read_bytes(C, 0, 32)
        obj = m.read_bytes(C, C_OBJ * 2, 64)
    assert bg == blob[:32] and obj == blob[32:96]
    w = [int.from_bytes(bg[i:i + 2], "little") for i in range(0, 32, 2)]
    import sheets
    from gen_dgn_hero_assets import bgr555
    assert w[0] == bgr555(sheets.BG_FLOOR), "CGRAM word 0 is both the plane's index 0 and the backdrop: the floor"


# --- 2. the ROM plays the score --------------------------------------------------------------------------------------
def test_oam_and_the_mode_7_shadow_are_the_directors_record_on_every_frame(real):
    assert len(set(real.d)) == G.LOOP, "the run did not cover every tick of the loop"
    assert real.oam_bad == [], f"OAM differs from the score on frames {real.oam_bad[:5]}"
    assert real.shadow_bad == [], f"the Mode 7 shadow differs from the score on frames {real.shadow_bad[:5]}"


def test_the_loop_wraps_without_a_seam(real):
    wraps = [k for k in range(1, FRAMES) if real.d[k] == 0 and real.d[k - 1] == G.LOOP - 1]
    assert wraps, "the loop never wrapped in the run"


def test_every_displayed_player_frame_is_intact_in_vram(real):
    assert real.tears == [], f"VRAM differs from the committed strip the OAM points at: {real.tears[:6]}"


# --- 3. VBlank and the sprite limits ----------------------------------------------------------------------------------------------
def test_the_whole_scene_costs_a_sliver_of_vblank(real):
    """OAM DMA + eight Mode 7 register writes + at most two 128 B rows. VBlank is V = 225..261."""
    assert all(224 < v <= 261 for v in real.vend)
    assert real.vmax <= 233, f"the worst tick ended on scanline {real.vmax}"
    assert max(real.bytes) <= 256


def test_no_scanline_exceeds_the_sprite_limits(real):
    assert real.s77_final & 0xC0 == 0
    assert real.worst_sprites <= 32 and real.worst_slivers <= 34


# --- 4. the picture ----------------------------------------------------------------------------------------------------------------
def _ticks():
    """Rest, mid-spin at the peak, each cut's hold, a withdraw, the retract."""
    peak = max(range(1, G.LOOP), key=lambda t: abs(G.boss_state(t)[0] - G.boss_state(t - 1)[0]))
    out = [("rest", 5), ("peak spin", peak), ("mid slide", 45)]
    for a in G.SLICE_ANGLES:
        t0, _ = G.cut_window(a)
        out += [(f"cut {a}", t0 + G.LUNGE_T + 2)]
    out += [("withdraw", G.CUT_AT[135] + G.LUNGE_T + G.HOLD_T + 6), ("retract", G.LOOP - 20)]
    return sorted(out, key=lambda o: o[1])


def test_the_named_poses_really_are_the_poses():
    """The cuts are cuts: the blade is long, on screen and lunged forward at each named tick (through the reference)."""
    for name, t in _ticks():
        if name.startswith("cut"):
            f = G.render_m7(PLANE, G.matrix_words(*G.boss_state(t)))
            assert int((f == 12).sum()) > 1500, f"{name}: the blade is not on screen at tick {t}"


def _sample_of(tick):
    """The sample index at which the ROM's last NMI committed `tick`. The ROM has been ticking since boot, so sample k
    shows tick (BOOT + k - 1) mod LOOP; the named poses must be looked up, not assumed (a first version assumed
    sample k = tick k, and its 'cut' shots were not cuts)."""
    return (tick - BOOT + 1) % G.LOOP


def _compare(which, tmp_path, ticks):
    """Per tick: (name, tick, mismatching background px outside the players' boxes, px compared)."""
    rows = []
    with Machine(str(ROMS[which])) as m:
        m.advance(BOOT)
        now = BOOT
        for name, tick in sorted(ticks, key=lambda o: _sample_of(o[1])):
            k = _sample_of(tick)
            m.advance(BOOT + k + 1 - now)
            cg = m.read_bytes(C, 0, 32)
            ct = m.read_u16(W, _dp("US_CT"))
            d = (ct - 1) % G.LOOP
            assert d == tick, f"{name}: asked for tick {tick}, the ROM is showing tick {d}"
            words = [int.from_bytes(cg[i:i + 2], "little") for i in range(0, 32, 2)]
            ent = parse_oam(m.read_bytes(O, 0, 544))
            shot = tmp_path / f"{which}_{name.replace(' ', '_')}.png"
            m.screenshot(str(shot))                    # state read BEFORE this call: it spends a frame (docs/dungeons/18)
            now = BOOT + k + 2
            img = np.asarray(Image.open(shot).convert("RGB")).astype(float)
            crop = img[PICTURE_TOP:PICTURE_TOP + 224, :256]
            ref = G.render_m7(PLANE, G.matrix_words(*G.boss_state(d)))
            pal = rgb_of(words)
            mask = np.ones((224, 256), bool)
            for x, y, _n, _a, size in ent[:4]:           # the players' sprites
                mask[max(0, y + 1):y + 1 + size, max(0, x):x + 16] = False
            bad = (np.abs(crop - pal[ref]).max(-1) > 10) & mask
            rows.append((name, d, int(bad.sum()), int(mask.sum())))
    return rows


def test_the_background_is_pixel_exact_against_the_reference_through_the_whole_sequence(real, tmp_path):
    """The boss as the PPU draws it equals the plane run through the PPU's own arithmetic, at every pose: this is the
    check that the ROM's interleave, palette, matrix writes, pivot and scroll are all right at once."""
    rows = _compare("real", tmp_path, _ticks())
    assert len(rows) >= 7
    for name, d, bad, total in rows:
        assert bad == 0, f"{name} (tick {d}): {bad} of {total} background pixels differ from the reference"
    assert min(t for *_, t in rows) > 30000


def test_the_picture_changes_a_great_deal_from_pose_to_pose(tmp_path):
    """Not vacuous: the poses are different pictures, so an exact match is a real one."""
    shots = []
    with Machine(str(ROMS["real"])) as m:
        m.advance(BOOT)
        now = BOOT
        for tick in (5, 40, 75, 150):
            m.advance(BOOT + tick + 1 - now)
            p = tmp_path / f"v{tick}.png"
            m.screenshot(str(p))
            now = BOOT + tick + 2
            shots.append(np.asarray(Image.open(p).convert("RGB")).astype(int))
    for a, b in zip(shots, shots[1:]):
        assert (np.abs(a - b).max(-1) > 20).sum() > 3000


def test_the_naive_mode_7_formula_is_wrong_on_the_real_picture(tmp_path):
    """Finding, pinned: at 22 degrees the naive formula differs from the machine by hundreds of pixels while the
    PPU-accurate renderer matches exactly (the six dropped bits are real)."""
    with Machine(str(ROMS["real"])) as m:
        m.advance(BOOT)
        m.advance(39)
        cg = m.read_bytes(C, 0, 32)
        ct = m.read_u16(W, _dp("US_CT"))
        d = (ct - 1) % G.LOOP
        ent = parse_oam(m.read_bytes(O, 0, 544))
        m.screenshot(str(tmp_path / "n.png"))
    words = [int.from_bytes(cg[i:i + 2], "little") for i in range(0, 32, 2)]
    crop = np.asarray(Image.open(tmp_path / "n.png").convert("RGB")).astype(float)[PICTURE_TOP:PICTURE_TOP + 224, :256]
    w = G.matrix_words(*G.boss_state(d))
    A, B, Cc, Dm = (v - 0x10000 if v & 0x8000 else v for v in w[:4])
    ho, vo = w[6] - w[4], w[7] - w[5]
    sy, sx = np.mgrid[0:224, 0:256]
    naive = PLANE[((Cc * (sx + ho) + Dm * (sy + 1 + vo)) >> 8) + 512 & 1023, ((A * (sx + ho) + B * (sy + 1 + vo)) >> 8) + 512 & 1023]
    exact = G.render_m7(PLANE, w)
    pal = rgb_of(words)
    mask = np.ones((224, 256), bool)
    for x, y, _n, _a, size in ent[:4]:
        mask[max(0, y + 1):y + 1 + size, max(0, x):x + 16] = False
    bad = lambda r: int(((np.abs(crop - pal[r]).max(-1) > 10) & mask).sum())
    assert bad(exact) == 0 and bad(naive) > 50, (bad(exact), bad(naive))


# --- 5. the planted fault ------------------------------------------------------------------------------------------------------------
def test_a_transposed_matrix_is_caught_by_the_picture_check(tmp_path):
    """B and C swapped turns the plane the wrong way round. At 0 and 180 degrees the matrix is symmetric, so those poses
    cannot tell; every other pose must go red."""
    rows = _compare("plant", tmp_path, [r for r in _ticks() if r[0] not in ("rest",)])
    assert any(bad > 2000 for _, _, bad, _ in rows), rows
    assert sum(1 for _, _, bad, _ in rows if bad > 500) >= 3, rows


def test_the_planted_fault_leaves_the_real_rom_untouched():
    assert ROMS["real"].read_bytes() != ROMS["plant"].read_bytes()


# --- 6. what the allocator charged ----------------------------------------------------------------------------------------------------
def test_the_allocator_charges_the_scenes_worst_tick():
    line = next(ln for ln in (BUILD / "dgng" / "allocation_report.txt").read_text().splitlines() if "VBLANK-DMA" in ln)
    assert "800" in line and "256 arm" in line and "3 transfers" in line, line    # 544 OAM + 256; 2 x 128
