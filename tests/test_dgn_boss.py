"""dgn_boss — the boss-battle spike, on the console (docs/dungeons/18).

runtime: ~90 s — lockstep Machine boots; one 700-frame pass of the real ROM and one of the planted fault.

A 64x64 boss (four 32x32 OBJs), two players that idle / walk / ATTACK and two small enemies, with the boss
and the players STREAMED from ROM into fixed VRAM slots in VBlank. The question this module answers is
"what breaks": every assertion reads the rendered OUTPUT (VRAM, OAM, CGRAM, a screenshot), and the
VBlank/sprite-limit numbers are read from the PPU itself (the V counter latched at the end of the NMI hook,
STAT77), never from a proxy.

The planted fault (`make dgn_boss_overload`: the boss streamed twice a frame) is the control. Every detector
here must fire on it, so a green run on the real ROM means something.

Lockstep `Machine` only; every address is read out of the rail's emitted symbol_map.json.
"""
import json
import sys
from pathlib import Path

SUPERFORGE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SUPERFORGE / "vendor"))
# FIRST, before numpy/Pillow: mesen_runner dlopens MesenCore.so at import (see test_dgn_hero.py).
from machine import Machine, MemoryType  # noqa: E402

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PIL import Image  # noqa: E402

from conftest import run_make  # noqa: E402
from frame_geometry import PICTURE_TOP  # noqa: E402

BUILD = SUPERFORGE / "build"
ROM = BUILD / "dgn_boss.sfc"
ROM_OVERLOAD = BUILD / "dgn_boss_overload.sfc"
CRE = SUPERFORGE / "art" / "dungeons" / "creatures" / "out"
STY = SUPERFORGE / "art" / "dungeons" / "style" / "out" / "a_storybook"
_JMAP = json.loads((BUILD / "dgnb" / "symbol_map.json").read_text())

W, V, C, O = (MemoryType.SnesWorkRam, MemoryType.SnesVideoRam, MemoryType.SnesCgRam,
              MemoryType.SnesSpriteRam)
FRAMES_RUN = 700             # > the longest timeline (boss 264, P1 228, P2 168): every frame is seen
BOOT = 30


def _dp(name):
    return next(p["start"] for p in _JMAP["scenes"]["arena"]["placements"] if p["sym"] == name)


def _sym(name):
    return next(p for p in _JMAP["scenes"]["arena"]["placements"] if p["sym"] == name)


V_OBJ = _sym("ES_V_OBJ_CHR")["start"]               # VRAM word address of the OBJ claim
C_OBJ = 128                                         # hardware: OBJ palettes start at CGRAM 128
OAM_SHADOW = next(p["start"] for p in _JMAP["globals"] if p["sym"] == "ES_OAM_SHADOW")


# ---- the expected pictures, from the COMMITTED strips (independent of the converter) ----------------
def _strip(path, w, h):
    a = np.asarray(Image.open(path))
    assert a.shape[0] == h and a.shape[1] % w == 0, f"{path}: {a.shape}"
    return [a[:, i * w:(i + 1) * w] for i in range(a.shape[1] // w)]


BOSS = [f for fc in ("down", "right") for act in ("idle", "scuttle", "prepare", "attack")
        for f in _strip(CRE / "bellwretch64" / f"{act}_{fc}.png", 64, 64)]
HERO = []                                           # a player's nine frames, each padded to a 32x32 slot
for _act, _w in (("idle", 16), ("walk", 16), ("attack", 32)):
    for _f in _strip(STY / f"{_act}_right.png", _w, 32):
        _slot = np.zeros((32, 32), np.uint8)
        _slot[:, :_w] = _f
        HERO.append(_slot)
EA = _strip(CRE / "thornhopper" / "hop_right.png", 32, 32)
EB = _strip(CRE / "thornling" / "hop_right.png", 16, 16)
assert len(BOSS) == 28 and len(HERO) == 9
ATK0 = 6                                            # a player's first attack frame
BOSS_ATTACK = {11, 12, 13, 25, 26, 27}


def _decode_tile(b):
    t = np.zeros((8, 8), np.uint8)
    for y in range(8):
        p = (b[2 * y], b[2 * y + 1], b[16 + 2 * y], b[16 + 2 * y + 1])
        for x in range(8):
            t[y, x] = sum(((p[k] >> (7 - x)) & 1) << k for k in range(4))
    return t


def _vram_slot(m, col, w_tiles, rows):
    """A slot of the OBJ name table (16 tiles a row) decoded to pixels."""
    out = np.zeros((rows * 8, w_tiles * 8), np.uint8)
    for r in range(rows):
        raw = m.read_bytes(V, (V_OBJ + (r * 16 + col) * 16) * 2, w_tiles * 32)
        for t in range(w_tiles):
            out[r * 8:r * 8 + 8, t * 8:t * 8 + 8] = _decode_tile(raw[t * 32:t * 32 + 32])
    return out


def _slot_ok(m, which, have):
    if which == "boss":
        return (_vram_slot(m, 0, 8, 8) == BOSS[have]).all()
    col = {"p1": 8, "p2": 12}[which]
    return (_vram_slot(m, col, 4, 4) == HERO[have]).all()


# ---- OAM and the per-line sprite ledger -------------------------------------------------------------
def _oam(m):
    raw = m.read_bytes(O, 0, 544)
    out = []
    for i in range(128):
        x, y, name, attr = raw[i * 4:i * 4 + 4]
        bits = (raw[512 + i // 4] >> ((i % 4) * 2)) & 3
        out.append((x - 256 if bits & 1 else x, y, name, attr, 32 if bits & 2 else 16))
    return out


def _ledger(entries):
    """(most sprites, most 8-px slivers) on any one of the 224 display lines (docs/01 §OAM)."""
    sprites = [0] * 257
    slivers = [0] * 257
    for x, y, _n, _a, size in entries:
        if x <= -size or x >= 256:
            continue                                 # entirely off the sides
        cols = sum(1 for t in range(size // 8) if 0 <= x + 8 * t < 256 or 0 <= x + 8 * t + 7 < 256)
        for dy in range(size):
            line = (y + 1 + dy) % 256
            if 1 <= line <= 224:
                sprites[line] += 1
                slivers[line] += cols
    return max(sprites), max(slivers)


# ---- one pass over the run, shared by the tests ---------------------------------------------------------
class Pass:
    """Per-frame records of a ROM running FRAMES_RUN frames from the boot."""

    def __init__(self, rom, vram_every=25):
        self.have, self.want, self.vend, self.s77, self.stream_bytes = [], [], [], [], []
        self.tears = []                              # (frame, slot) where VRAM != the strip of what HAVE says
        self.worst_sprites = self.worst_slivers = 0
        self.large_wrap = []                         # (frame, slot): a 32x32 parked or placed to wrap into the top
        self.shots = []                              # frames worth a screenshot
        self.seen = {"boss": set(), "p1": set(), "p2": set()}
        prev = (None, None, None)
        with Machine(str(rom)) as m:
            m.advance(BOOT)
            for k in range(FRAMES_RUN):
                m.advance(1)
                h = tuple(m.read_u16(W, _dp(f"US_HAVE_{s}")) for s in "BAC")
                self.have.append(h)
                self.want.append(tuple(m.read_u16(W, _dp(f"US_WANT_{s}")) for s in "BAC"))
                self.vend.append(m.read_u16(W, _dp("US_VEND")))
                self.s77.append(m.read_u16(W, _dp("US_S77")))
                self.stream_bytes.append(sum(b for c, p, b in zip(h, prev, (2048, 512, 512)) if prev[0] is not None and c != p))
                for slot, key, which in ((0, "boss", "boss"), (1, "p1", "p1"), (2, "p2", "p2")):
                    cur = h[slot]
                    if cur == 0xFFFF:
                        continue
                    self.seen[key].add(cur)
                    if (prev[slot] != cur or k % vram_every == 0) and not _slot_ok(m, which, cur):
                        self.tears.append((k, which))
                ent = _oam(m)
                s, sl = _ledger(ent)
                self.worst_sprites, self.worst_slivers = max(self.worst_sprites, s), max(self.worst_slivers, sl)
                for i, (x, y, _n, _a, size) in enumerate(ent):
                    if size == 32 and y > 224:
                        self.large_wrap.append((k, i))
                if len(self.shots) < 8 and k > 40 and (h[1] >= ATK0 or h[2] >= ATK0 or h[0] in BOSS_ATTACK) \
                        and (not self.shots or k - self.shots[-1] > 20):
                    self.shots.append(k)
                prev = h
            self.vmax = m.read_u16(W, _dp("US_VMAX"))
            self.s77_final = m.read_u16(W, _dp("US_S77"))


@pytest.fixture(scope="module", autouse=True)
def roms_built():
    for target in ("dgn_boss", "dgn_boss_overload"):
        r = run_make(target)
        assert r.returncode == 0, f"make {target} failed rc={r.returncode}:\n{r.stdout}\n{r.stderr}"
    yield


@pytest.fixture(autouse=True)
def hand_back_the_core():
    yield
    Machine.close_current()


@pytest.fixture(scope="module")
def real(roms_built):
    p = Pass(ROM)
    Machine.close_current()
    return p


@pytest.fixture(scope="module")
def planted(roms_built):
    p = Pass(ROM_OVERLOAD)
    Machine.close_current()
    return p


# --- 1. the streams deliver every frame ------------------------------------------------------------------
def test_every_boss_and_player_frame_reaches_vram_intact(real):
    assert real.seen["boss"] == set(range(28)), "the run did not stream all 28 boss frames"
    assert real.seen["p1"] == set(range(9)) and real.seen["p2"] == set(range(9))
    assert real.tears == [], f"VRAM differs from the committed strip the stream says it holds: {real.tears[:5]}"


def test_the_stream_holds_what_the_actors_want(real):
    """One frame's lag at most: a frame is wanted in the tick and streamed in the same frame's VBlank, so
    sampled at a frame boundary HAVE is either WANT or the frame just before it."""
    behind = [k for k in range(1, FRAMES_RUN) if real.have[k] not in (real.want[k], real.want[k - 1])]
    assert behind == [], f"a slot is more than one frame behind what it was asked for: {behind[:5]}"


# --- 2. VBlank ---------------------------------------------------------------------------------------------------
def test_the_worst_frame_finishes_inside_vblank(real):
    """VBlank is V = 225..261. The latched counter at the END of the NMI hook is how far into it we got.
    Measured: 255 on the frame where the boss and both players change together (3,072 B + the OAM DMA)."""
    worst_frames = [k for k, b in enumerate(real.stream_bytes) if b == 3072]
    assert worst_frames, "the timelines never changed the boss and both players on one frame: nothing was measured"
    assert all(224 < v <= 261 for v in real.vend), "the NMI hook ended outside VBlank"
    assert real.vmax <= 256, (f"the worst frame ended on scanline {real.vmax}: measured 255 of 261, "
                              "so something added VBlank work. docs/dungeons/18 §3")
    worst = max(real.vend[k] for k in worst_frames)
    assert worst >= 250, f"the coincident frame ended on {worst}: it is meant to be the near-full one"


def test_the_ledger_is_monotonic_in_what_is_streamed(real):
    """More bytes, later finish: the V counter really is measuring the DMA, not noise."""
    by_cost = {}
    for b, v in zip(real.stream_bytes, real.vend):
        by_cost.setdefault(b, set()).add(v)
    costs = sorted(c for c in by_cost if c in (0, 512, 1024, 2048, 2560))
    ends = [max(by_cost[c]) for c in costs]
    assert ends == sorted(ends) and len(set(ends)) == len(ends), dict(zip(costs, ends))


# --- 3. the sprite limits ------------------------------------------------------------------------------------------
def test_no_scanline_exceeds_the_sprite_limits(real):
    assert real.s77_final & 0xC0 == 0, "the PPU raised STAT77 time-over/range-over"
    assert real.worst_sprites <= 32 and real.worst_slivers <= 34
    assert real.worst_slivers <= 24, f"{real.worst_slivers} slivers on one line: the hand ledger said 22 at most"


def test_no_large_sprite_wraps_into_the_top_of_the_screen(real):
    """A 32x32 OBJ at Y > 224 wraps (Y is mod 256) and draws at the TOP: a parked large sprite would."""
    assert real.large_wrap == [], real.large_wrap[:5]


def test_the_stat77_detector_fires_on_a_planted_overload():
    """Control: nine 32x32 OBJs on one row is 36 slivers. If STAT77 stayed clear the test above would be vacuous."""
    with Machine(str(ROM)) as m:
        m.advance(BOOT)
        assert m.read_u16(W, _dp("US_S77")) & 0xC0 == 0
        for i in range(9):                           # free slots 12..20, one row, spread across the screen
            m.write_bytes(W, OAM_SHADOW + (12 + i) * 4, bytes((i * 28, 60, 0, 0x30)))
        for byte, v in ((3, 0xAA), (4, 0xAA), (5, 0x02)):
            m.write_byte(W, OAM_SHADOW + 512 + byte, v)
        m.advance(3)
        assert m.read_u16(W, _dp("US_S77")) & 0xC0 != 0, "36 slivers on a line did not raise STAT77"


# --- 4. the picture ------------------------------------------------------------------------------------------------------
def _rgb(words):
    """BGR555 words -> the 8-bit colours the picture shows (a screenshot is 8-bit, a palette 5-bit)."""
    return np.array([[(w & 31) * 255 // 31, ((w >> 5) & 31) * 255 // 31, ((w >> 10) & 31) * 255 // 31]
                     for w in words], float)


def test_the_screen_is_the_committed_frames_at_the_oam_positions(real, tmp_path):
    """The state is read BEFORE the screenshot call. `screenshot()` spends one emulated frame and
    photographs THAT frame, which is drawn from the OAM and VRAM the last NMI committed: exactly what was
    just read. (Found the hard way: read AFTER the call, an enemy that moves 1 px a frame sits 1 px off its
    OAM x, and every actor that changed frame in that NMI is the wrong frame.)"""
    assert len(real.shots) >= 4, f"too few attack frames to photograph: {real.shots}"
    checked = done = 0
    with Machine(str(ROM)) as m:
        m.advance(BOOT)
        now = BOOT                                   # ABSOLUTE frame count: a screenshot spends one frame itself
        for s in real.shots:                         # (Pass sample s is the state after BOOT + s + 1 frames)
            m.advance(BOOT + s + 1 - now)
            cg = m.read_bytes(C, 0, 512)
            snap = (_oam(m), [int.from_bytes(cg[i:i + 2], "little") for i in range(0, 512, 2)],
                    tuple(m.read_u16(W, _dp(f"US_HAVE_{s2}")) for s2 in "BAC"))
            shot = tmp_path / f"f{s}.png"
            m.screenshot(str(shot))
            now = BOOT + s + 2
            k = s
            img = np.asarray(Image.open(shot).convert("RGB"))
            ent, words, (hb, ha, hc) = snap
            ea_f = EA[ent[4][2] // 4]                # A: name = 4 x frame (name table 1)
            eb_f = EB[(ent[5][2] - 64) // 2]         # B: name = 64 + 2 x frame
            hero = lambda have: HERO[have] if have >= ATK0 else HERO[have][:, :16]
            # (name, (x, y), expected pixels, OBJ palette, hflip)
            actors = [
                ("boss", (ent[6][0], ent[6][1]), BOSS[hb], 2, False),
                ("p1", (ent[0][0], ent[0][1]), hero(ha), 0, bool(ent[0][3] & 0x40)),
                ("p2", (ent[2][0], ent[2][1]), hero(hc), 1, bool(ent[2][3] & 0x40)),
                ("ea", (ent[4][0], ent[4][1]), ea_f, 3, bool(ent[4][3] & 0x40)),
                ("eb", (ent[5][0], ent[5][1]), eb_f, 3, bool(ent[5][3] & 0x40)),
            ]
            boxes = [(x, y, a.shape[1], a.shape[0]) for _, (x, y), a, _, _ in actors]
            for i, (name, (x, y), want, pal, flip) in enumerate(actors):
                want = want[:, ::-1] if flip else want
                h, w = want.shape
                crop = img[PICTURE_TOP + y:PICTURE_TOP + y + h, x:x + w]
                # compare COLOURS, not indices: two palette entries may share a colour, and index 0 is the backdrop
                pal_rgb = _rgb([words[0]] + words[C_OBJ + 16 * pal + 1:C_OBJ + 16 * pal + 16])
                differs = np.abs(crop.astype(float) - pal_rgb[want]).max(-1) > 10
                free = np.ones((h, w), bool)         # compare only where no OTHER actor's box lies
                for j, (bx, by, bw, bh) in enumerate(boxes):
                    if j != i:
                        free[max(0, by - y):max(0, by + bh - y), max(0, bx - x):max(0, bx + bw - x)] = False
                bad = differs & free
                assert not bad.any(), f"frame {k}: {name} renders differently from its committed frame ({int(bad.sum())} px)"
                checked += int(free.sum())
            done += 1
    assert done >= 4 and checked > 20000


# --- 5. the planted fault: every detector must fire --------------------------------------------------------------------
def test_the_overload_overruns_vblank_and_tears_vram(planted):
    """The boss streamed twice a frame cannot finish inside VBlank on the frames where more than it changes.
    What the failure LOOKS like, because it is not what one expects: the V counter at the end of the hook is
    small (the DMA ran into the NEXT frame), the writes that landed in the picture are dropped, and the
    change detector believes the slot is loaded. The corruption is permanent until the slot changes again."""
    wrapped = [v for v in planted.vend if v < 225]
    assert wrapped, "the planted overload never ran past the end of VBlank"
    assert planted.tears, "the tear detector did not fire on a ROM whose DMA overran VBlank"
    assert planted.vmax >= 261


def test_the_planted_fault_leaves_the_real_rom_untouched():
    assert ROM.read_bytes() != ROM_OVERLOAD.read_bytes(), "the control ROM is the real one: nothing was planted"


# --- 6. what the allocator charged ---------------------------------------------------------------------------------------------
def test_the_allocator_charges_the_worst_frame_and_it_fits_the_pin():
    line = next(ln for ln in (BUILD / "dgnb" / "allocation_report.txt").read_text().splitlines()
                if "VBLANK-DMA" in ln)
    # 544 B OAM + 3,072 B (boss 2,048 + two players 512 each) = 3,616 B; 17 transfers; arm cost 16 x 128 = 2,048
    assert "3616" in line and "2048 arm" in line and "5952" in line and "17 transfers" in line, line
    assert 3616 + 2048 <= 5952
