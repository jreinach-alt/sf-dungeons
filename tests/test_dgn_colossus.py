"""dgn_colossus — the tile-streamed giant boss, on the console (docs/dungeons/21).

runtime: ~2-3 min — lockstep Machine passes (a frame-by-frame pass and a screenshot pass over two full loops, each
for the real ROM and the planted faults).

The boss is a SET OF PICTURES streamed into two page-flipped Mode 1 BG layers; the room's floor is BG3; the players are
OBJs. What this module proves, from the machine's own output:

  * the ROM plays the score: OAM and the BG shadow (TM, VOFS) equal the director's record on every frame;
  * THE PICTURE: at every sampled tick of two full loops the screen equals the SOURCE picture the director says is on
    display (the rendered PNG, read from the art tree, not from the blobs), the floor and the palettes, with the
    players' boxes masked. Nothing here reads a VRAM byte: a torn or late or half-loaded picture is a wrong pixel;
  * the players' streamed frames are intact, the sprite limits never trip, and the V counter says how much of VBlank the
    worst tick took;
  * two planted faults (the commands played one tick late; the layer switch one tick early) are CAUGHT by the picture check.

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
from dgn_ppu import decode_rows, ledger, parse_oam  # noqa: E402
from dgn_tilestream import director as D  # noqa: E402
from dgn_tilestream import floor as FL  # noqa: E402
from dgn_tilestream import model as M  # noqa: E402
from dgn_giant import director as GD  # noqa: E402
import gen_dgn_fight_assets as GF  # noqa: E402
import gen_dgn_tile_assets as GT  # noqa: E402

BUILD = SUPERFORGE / "build"
ROMS = {"real": BUILD / "dgn_colossus.sfc", "late": BUILD / "dgn_colossus_late.sfc", "early": BUILD / "dgn_colossus_early.sfc"}
_JMAP = json.loads((BUILD / "dgnc" / "symbol_map.json").read_text())
W, V, C, O = (MemoryType.SnesWorkRam, MemoryType.SnesVideoRam, MemoryType.SnesCgRam, MemoryType.SnesSpriteRam)
BOOT = 30


def _sym(name):
    return next(p for p in _JMAP["scenes"]["colossus"]["placements"] if p["sym"] == name)


def _dp(name):
    return _sym(name)["start"]


V_OBJ = _sym("ES_V_OBJ_CHR")["start"]
BGSH = _dp("ES_BGSH")
SCENE = D.compile_scene()
T = SCENE["T"]
RECORDS = GT.records(SCENE)
HERO = GF.hero_frames()
PICS = M.load_pictures()
BOSS_PAL = np.array(json.loads((M.OUT / "palettes.json").read_text())["base"], np.uint8)
FLOOR_RGB = np.array(FL.FLOOR_RGB, np.uint8)
FLOOR = FL.image()


def _slot(m, actor, buf):
    col, row0 = GD.SLOTS[actor]["bufs"][buf]
    return [m.read_bytes(V, (V_OBJ + ((row0 + r) * 16 + col) * 16) * 2, 4 * 32) for r in range(4)]


def reference(t):
    """The screen the director says is on display at tick t, drawn from the source picture: the floor, then the boss's
    canvas row (y + VOFS + 1; the PPU numbers its lines from 1), wrapping at the 512-px map. Players not drawn."""
    tk = SCENE["ticks"][t]
    img = PICS[tk["pic"]]
    out = np.zeros((224, 256, 3), np.uint8)
    for y in range(224):
        out[y] = FLOOR_RGB[FLOOR[(y + 1) % 256]]
        r = (y + tk["vofs"] + 1) % 512
        if r < M.CH:
            row = img[r]
            nz = row > 0
            out[y][nz] = BOSS_PAL[row[nz]]
    return out


class Pass:
    """One ROM over `frames` frames: the score, the shadows, the players' tiles, the V counter."""

    def __init__(self, which, frames=T + 60):
        self.d, self.vend, self.oam_bad, self.shadow_bad, self.tears = [], [], [], [], []
        self.worst_sprites = self.worst_slivers = 0
        cache = {}
        with Machine(str(ROMS[which])) as m:
            m.advance(BOOT)
            for k in range(frames):
                m.advance(1)
                ct = m.read_u16(W, _dp("US_CT"))
                d = (ct - 1) % T                      # the tick the last NMI committed
                self.d.append(d)
                self.vend.append(m.read_u16(W, _dp("US_VEND")))
                rec = RECORDS[d]
                oam = m.read_bytes(O, 0, 544)
                if oam[:16] != rec[:16] or oam[512] != rec[16]:
                    self.oam_bad.append(k)
                nxt = RECORDS[ct % T]                  # the shadow holds the tick just copied, not yet committed
                sh = m.read_bytes(W, BGSH, 4)          # +0 TM, +1 unused, +2 VOFS
                if (sh[0], sh[2], sh[3]) != (nxt[17], nxt[18], nxt[19]):
                    self.shadow_bad.append(k)
                s, sl = ledger(parse_oam(oam))
                self.worst_sprites, self.worst_slivers = max(self.worst_sprites, s), max(self.worst_slivers, sl)
                for actor in ("p1", "p2"):
                    buf = SCENE["player_plan"]["bufsel"][actor][d]
                    raw = _slot(m, actor, buf)
                    want = SCENE["players"][actor][d].frame
                    key = (actor, buf, b"".join(raw), want)
                    if key not in cache:
                        cache[key] = bool((decode_rows(raw, 4) == HERO[want]).all())
                    if not cache[key]:
                        self.tears.append((k, actor))
            self.vmax = m.read_u16(W, _dp("US_VMAX"))
            self.s77 = m.read_u16(W, _dp("US_S77"))


def picture_pass(which, tmp_path, samples=T + 4):
    """(tick, mismatching px outside the players' boxes, px compared) at ~2 samples per 2 ticks over two loops."""
    rows = []
    with Machine(str(ROMS[which])) as m:
        m.advance(BOOT)
        for half in range(2):
            m.advance(1)                                # shift the sampling parity: odd ticks in the second loop
            for i in range(samples):
                m.advance(1)
                ct = m.read_u16(W, _dp("US_CT"))
                d = (ct - 1) % T
                ent = parse_oam(m.read_bytes(O, 0, 544))
                shot = tmp_path / f"{which}.png"
                m.screenshot(str(shot))                 # state read BEFORE this call: it spends a frame (docs/dungeons/18)
                img = np.asarray(Image.open(shot).convert("RGB")).astype(int)
                crop = img[PICTURE_TOP:PICTURE_TOP + 224, :256]
                mask = np.ones((224, 256), bool)
                for x, y, _n, _a, size in ent[:4]:
                    mask[max(0, y + 1):y + 1 + size, max(0, x):x + 16] = False
                bad = (np.abs(crop - reference(d).astype(int)).max(-1) > 10) & mask
                rows.append((d, int(bad.sum()), int(mask.sum())))
    return rows


@pytest.fixture(scope="module", autouse=True)
def roms_built():
    for target in ("dgn_colossus", "dgn_colossus_late", "dgn_colossus_early"):
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


# --- 1. the palettes and the floor ------------------------------------------------------------------------------------
def test_the_palettes_are_the_bosss_the_floors_and_the_players():
    blob = (BUILD / "assets_colossus" / "dgnt_pal.bin").read_bytes()
    with Machine(str(ROMS["real"])) as m:
        m.advance(BOOT)
        cg = m.read_bytes(C, 0, 512)
    assert cg[64:96] == blob[:32], "boss palette (BG palette 2, CGRAM 32..47)"
    assert cg[0:8] == blob[32:40], "floor palette (BG3 palette 0, CGRAM 0..3)"
    assert cg[256:320] == blob[40:104], "the players' OBJ palettes"


# --- 2. the ROM plays the score --------------------------------------------------------------------------------------
def test_oam_and_the_bg_shadow_are_the_directors_record_on_every_frame(real):
    assert len(set(real.d)) == T, "the run did not cover every tick of the loop"
    assert real.oam_bad == [], f"OAM differs from the score on frames {real.oam_bad[:5]}"
    assert real.shadow_bad == [], f"the BG shadow differs from the score on frames {real.shadow_bad[:5]}"


def test_every_displayed_player_frame_is_intact_in_vram(real):
    assert real.tears == [], f"VRAM differs from the committed strip the OAM points at: {real.tears[:6]}"


# --- 3. VBlank and the sprite limits -----------------------------------------------------------------------------------
def test_the_worst_tick_ends_before_the_end_of_vblank(real):
    """VBlank is V = 225..261: 261 is the cliff (an overrun drops VRAM writes silently). The director budgets to 258."""
    assert all(224 < v <= 261 for v in real.vend)
    assert real.vmax < 261, f"the worst tick ended on scanline {real.vmax}"


def test_the_measured_end_agrees_with_the_model_within_a_line_and_a_half(real):
    """V_end(t) = 229 + cost(t) / 1364 for the director's own commands (model.py's constants, FITTED to this counter: the
    test is that the fit holds on every tick, to within a line and a half)."""
    errs = []
    for k, d in enumerate(real.d):
        cost = sum(M.cost_mc(c[4]) for c in SCENE["cmds"].get(d, []))
        errs.append(real.vend[k] - (M.V_BASE + cost / M.LINE_MC))
    assert max(errs) < 1.5 and min(errs) > -1.5, (min(errs), max(errs))


def test_no_scanline_exceeds_the_sprite_limits(real):
    assert real.s77 & 0xC0 == 0
    assert real.worst_sprites <= 32 and real.worst_slivers <= 34


# --- 4. the picture ----------------------------------------------------------------------------------------------------
def test_the_screen_is_the_source_picture_at_every_sampled_tick_of_two_loops(tmp_path):
    rows = picture_pass("real", tmp_path)
    assert len({d for d, _, _ in rows}) >= T - 2, "the screenshots did not cover the loop"
    worst = max(rows, key=lambda r: r[1])
    assert worst[1] == 0, f"tick {worst[0]}: {worst[1]} of {worst[2]} px differ from the source picture"
    assert min(r[2] for r in rows) > 30000


def test_the_picture_changes_a_great_deal_from_pose_to_pose():
    """Not vacuous: the sampled poses are different pictures, so an exact match is a real one."""
    for a, b in ((5, 40), (40, 66), (66, 110)):
        assert (np.abs(reference(a).astype(int) - reference(b).astype(int)).max(-1) > 20).sum() > 1500


# --- 5. the planted faults ----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("which", ["late", "early"])
def test_a_planted_fault_is_caught_by_the_picture_check(which, tmp_path):
    rows = picture_pass(which, tmp_path, samples=130)
    assert sum(1 for _, bad, _ in rows if bad > 200) >= 3, sorted(rows, key=lambda r: -r[1])[:6]


def test_the_planted_faults_leave_the_real_rom_untouched():
    real_rom = ROMS["real"].read_bytes()
    assert real_rom != ROMS["late"].read_bytes() and real_rom != ROMS["early"].read_bytes()


# --- 5b. power-on fidelity ---------------------------------------------------------------------------------------------
def test_nothing_the_picture_displays_is_read_before_it_is_written(tmp_path):
    """Rule 5. Run a whole loop and a bit under the uninitialised-read detector: no VRAM, CGRAM or OAM byte the PPU
    drew from may be one the ROM never wrote. (CHR slot 0, the blank every empty map cell names, is written by the score's
    entry-state commands, not by the arm code: the director's first command per layer.)"""
    with Machine(str(ROMS["real"]), uninit_detection=True) as m:
        m.advance(BOOT + T + 40)
        found = m.get_uninitialized_reads((V, C, O))
    assert found == {}, {k: (len(v), [hex(a) for a in v[:6]]) for k, v in found.items()}


def test_the_picture_does_not_depend_on_the_power_on_contents_of_vram(tmp_path):
    """A different power-on seed (random VRAM and WRAM) gives the same picture, pixel for pixel, at a swap, a cut and
    the retract."""
    for tick in (7, 70, 150, 225):
        with Machine(str(ROMS["real"]), seed=0x1234567) as m:
            m.advance(BOOT)
            while (m.read_u16(W, _dp("US_CT")) - 1) % T != tick:
                m.advance(1)
            ent = parse_oam(m.read_bytes(O, 0, 544))
            shot = tmp_path / f"seed{tick}.png"
            m.screenshot(str(shot))
        crop = np.asarray(Image.open(shot).convert("RGB")).astype(int)[PICTURE_TOP:PICTURE_TOP + 224, :256]
        mask = np.ones((224, 256), bool)
        for x, y, _n, _a, size in ent[:4]:
            mask[max(0, y + 1):y + 1 + size, max(0, x):x + 16] = False
        bad = int(((np.abs(crop - reference(tick).astype(int)).max(-1) > 10) & mask).sum())
        assert bad == 0, f"tick {tick}: {bad} px differ under another power-on seed"


# --- 6. what the allocator charged ---------------------------------------------------------------------------------------
def test_the_allocator_charges_the_scenes_worst_tick():
    line = next(ln for ln in (BUILD / "dgnc" / "allocation_report.txt").read_text().splitlines() if "VBLANK-DMA" in ln)
    assert "4144" in line, line
