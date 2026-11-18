"""dgn_fight — the choreographed boss fight, on the console (docs/dungeons/19).

runtime: ~120 s — four lockstep Machine passes of 640 frames (real, unchoreographed control, planted fault, picture).

The scene is a score the ROM plays. What this module proves, from the machine's own output:

  * the ROM DISPLAYS the score: OAM equals the director's record on every frame, over the loop and its wrap;
  * every streamed frame on screen is INTACT in VRAM on every frame (decoded and compared with the committed
    strips), for the choreographed stream AND for the unchoreographed control, so the control is a fair one;
  * the VBlank profile: the V counter latched at the end of the NMI hook, for both streams of the SAME score;
  * the sprite limits never trip (STAT77), and the picture is the committed frames at the OAM positions;
  * a planted fault (every tick's rows played one tick late) is CAUGHT by the intact-frame check.

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
from dgn_fight import director as D  # noqa: E402
import gen_dgn_fight_assets as G  # noqa: E402

BUILD = SUPERFORGE / "build"
ROMS = {"real": BUILD / "dgn_fight.sfc", "naive": BUILD / "dgn_fight_naive.sfc",
        "hybrid": BUILD / "dgn_fight_hybrid.sfc", "late": BUILD / "dgn_fight_late.sfc"}
_JMAP = json.loads((BUILD / "dgnf" / "symbol_map.json").read_text())
W, V, C, O = (MemoryType.SnesWorkRam, MemoryType.SnesVideoRam, MemoryType.SnesCgRam, MemoryType.SnesSpriteRam)
BOOT = 30
FRAMES = 640                                  # the 580-tick loop and its wrap


def _dp(name):
    return next(p["start"] for p in _JMAP["scenes"]["fight"]["placements"] if p["sym"] == name)


V_OBJ = next(p["start"] for p in _JMAP["scenes"]["fight"]["placements"] if p["sym"] == "ES_V_OBJ_CHR")
C_OBJ = 128

STATES = D.all_states()
T = len(STATES["boss"])
BOSS, HERO = G.boss_frames(), G.hero_frames()
EA, EB = G.enemy_frames("thornhopper", 32), G.enemy_frames("thornling", 16)
PLANS = {m: D.compile_stream(STATES, mode=m) for m in D.MODES}
RECORDS = {m: [D.build_record(STATES, PLANS[m], t) for t in range(T)] for m in D.MODES}


def _slot(m, actor, buf):
    col, row0 = D.SLOTS[actor]["bufs"][buf]
    rows = D.SLOTS[actor]["rows"]
    w = 8 if actor == "boss" else 4
    raw = [m.read_bytes(V, (V_OBJ + ((row0 + r) * 16 + col) * 16) * 2, w * 32) for r in range(rows)]
    return b"".join(raw), decode_rows, raw, w


class Pass:
    """One ROM over FRAMES frames. Sample k is the state after BOOT + k + 1 frames."""

    def __init__(self, which, plan_mode):
        self.d, self.vend, self.s77, self.bytes = [], [], [], []
        self.oam_mismatch, self.tears = [], []
        self.worst_sprites = self.worst_slivers = 0
        plan, recs = PLANS[plan_mode], RECORDS[plan_mode]
        cache = {}
        with Machine(str(ROMS[which])) as m:
            m.advance(BOOT)
            for k in range(FRAMES):
                m.advance(1)
                ct = m.read_u16(W, _dp("US_CT"))
                d = (ct - 1) % T                  # the tick whose record the last NMI committed
                self.d.append(d)
                self.vend.append(m.read_u16(W, _dp("US_VEND")))
                self.bytes.append(plan["bytes"][d])
                self.s77.append(m.read_u16(W, _dp("US_S77")))
                oam = m.read_bytes(O, 0, 544)
                if oam[:48] != recs[d][:48] or oam[512:515] != recs[d][48:51]:
                    self.oam_mismatch.append(k)
                ent = parse_oam(oam)
                s, sl = ledger(ent)
                self.worst_sprites, self.worst_slivers = max(self.worst_sprites, s), max(self.worst_slivers, sl)
                for actor in ("boss", "p1", "p2"):
                    buf = plan["bufsel"][actor][d]
                    want = STATES[actor][d].frame
                    raw, _, rows, w = _slot(m, actor, buf)
                    key = (actor, buf, raw)
                    if key not in cache:
                        img = decode_rows(rows, w)
                        ref = BOSS[want] if actor == "boss" else HERO[want]
                        cache[key] = {}
                        cache[key][want] = bool((img == ref).all())
                    if want not in cache[key]:
                        img = decode_rows(rows, w)
                        cache[key][want] = bool((img == (BOSS[want] if actor == "boss" else HERO[want])).all())
                    if not cache[key][want]:
                        self.tears.append((k, actor))
            self.vmax = m.read_u16(W, _dp("US_VMAX"))
            self.s77_final = m.read_u16(W, _dp("US_S77"))


@pytest.fixture(scope="module", autouse=True)
def roms_built():
    for target in ("dgn_fight", "dgn_fight_naive", "dgn_fight_hybrid", "dgn_fight_late"):
        r = run_make(target)
        assert r.returncode == 0, f"make {target} failed rc={r.returncode}:\n{r.stdout}\n{r.stderr}"
    yield


@pytest.fixture(autouse=True)
def hand_back_the_core():
    yield
    Machine.close_current()


@pytest.fixture(scope="module")
def real(roms_built):
    p = Pass("real", "choreo")
    Machine.close_current()
    return p


@pytest.fixture(scope="module")
def naive(roms_built):
    p = Pass("naive", "naive")
    Machine.close_current()
    return p


@pytest.fixture(scope="module")
def hybrid(roms_built):
    p = Pass("hybrid", "hybrid")
    Machine.close_current()
    return p


@pytest.fixture(scope="module")
def late(roms_built):
    p = Pass("late", "choreo")
    Machine.close_current()
    return p


# --- 1. the ROM plays the score ----------------------------------------------------------------------------------
def test_oam_is_the_directors_record_on_every_frame(real):
    assert len(set(real.d)) == T, "the run did not cover every tick of the loop"
    assert real.oam_mismatch == [], f"OAM differs from the score on frames {real.oam_mismatch[:5]}"


def test_the_loop_wraps_without_a_seam(real):
    """The tick counter wraps T-1 -> 0, and the frame after the wrap is as intact as any other."""
    wraps = [k for k in range(1, FRAMES) if real.d[k] == 0 and real.d[k - 1] == T - 1]
    assert wraps, "the loop never wrapped in the run"
    for k in wraps:
        assert not [t for t in real.tears if abs(t[0] - k) <= 3], "a tear at the wrap"


# --- 2. every displayed frame is intact -----------------------------------------------------------------------------
def test_every_displayed_frame_is_intact_in_vram(real):
    assert real.tears == [], f"VRAM differs from the committed strip the OAM points at: {real.tears[:6]}"


def test_the_unchoreographed_control_is_a_fair_one(naive):
    """Same score, same pictures: the control differs only in HOW it streamed, so the comparison is honest."""
    assert naive.oam_mismatch == [] and naive.tears == []


# --- 3. VBlank ------------------------------------------------------------------------------------------------------------
def test_the_choreographed_stream_uses_a_sliver_of_vblank(real):
    """VBlank is V = 225..261. Measured: the choreographed score's worst tick ends on 235, six lines in."""
    assert all(224 < v <= 261 for v in real.vend)
    assert real.vmax <= 237, f"the worst tick ended on scanline {real.vmax}: something added VBlank work"
    assert max(real.bytes) <= 512


def test_the_unchoreographed_stream_nearly_fills_it(naive):
    """The SAME score, streamed when each frame changes: its worst tick ends on 260 of 261."""
    assert naive.vmax >= 255, naive.vmax
    assert max(naive.bytes) >= 3000
    assert all(224 < v <= 261 for v in naive.vend), "even the control must not overrun (it is the dgn_boss worst case)"


def test_choreography_buys_at_least_twenty_scanlines(real, naive):
    """The answer to 'can a pre-programmed sequence reduce the VBlank load': yes, by this much, on this score."""
    assert naive.vmax - real.vmax >= 20, (naive.vmax, real.vmax)
    busy_real = sum(1 for v in real.vend if v > 235)
    assert busy_real == 0


def test_the_realistic_hybrid_sits_between_the_two(real, hybrid, naive):
    """What a real game can do: plan the boss, stream the players on demand (they follow human input). Its
    worst tick is the boss's drip plus both players changing together, and its frames are as intact as the others."""
    assert hybrid.oam_mismatch == [] and hybrid.tears == []
    assert hybrid.s77_final & 0xC0 == 0
    assert real.vmax < hybrid.vmax < naive.vmax, (real.vmax, hybrid.vmax, naive.vmax)
    assert hybrid.vmax <= 250, f"the hybrid's worst tick ended on {hybrid.vmax}"
    assert naive.vmax - hybrid.vmax >= 8


def test_the_v_counter_measures_the_dma_in_both(real, naive):
    """More bytes, later finish, for each ROM: the counter is measuring the stream, not noise."""
    for p in (real, naive):
        by = {}
        for b, v in zip(p.bytes, p.vend):
            by.setdefault(b, set()).add(v)
        costs = sorted(by)
        tops = [max(by[c]) for c in costs]
        assert tops == sorted(tops), dict(zip(costs, tops))


# --- 4. the sprite limits ----------------------------------------------------------------------------------------------
def test_no_scanline_exceeds_the_sprite_limits(real, naive):
    for p in (real, naive):
        assert p.s77_final & 0xC0 == 0, "the PPU raised STAT77 time-over/range-over"
        assert p.worst_sprites <= 32 and p.worst_slivers <= 34
    assert real.worst_slivers <= 24, real.worst_slivers


# --- 5. the picture -----------------------------------------------------------------------------------------------------------
def _shots():
    """Ticks worth a photograph: both players attacking, the slam, the whirl, an enemy's leap."""
    want = {"p1 attack": lambda t: STATES["p1"][t].action == "attack",
            "p2 attack": lambda t: STATES["p2"][t].action == "attack",
            "boss slam": lambda t: STATES["boss"][t].action == "attack",
            "boss whirl": lambda t: STATES["boss"][t].action == "whirl",
            "enemy leap": lambda t: STATES["ea"][t].action == "attack" or STATES["eb"][t].action == "attack",
            "boss flipped": lambda t: STATES["boss"][t].flip and STATES["boss"][t].action == "scuttle"}
    out = []
    for name, f in want.items():
        ts = [t for t in range(T) if f(t)]
        out.append((name, ts[len(ts) // 2]))
    return sorted(out, key=lambda o: o[1])         # the emulator only goes forward


def test_the_screen_is_the_committed_frames_at_the_oam_positions(real, tmp_path):
    """State is read BEFORE the screenshot call: `screenshot()` spends one emulated frame and photographs THAT
    frame, drawn from what the last NMI committed (docs/dungeons/18 §3.8)."""
    checked = 0
    with Machine(str(ROMS["real"])) as m:
        m.advance(BOOT)
        now = BOOT
        for name, tick in _shots():
            k = next(i for i, d in enumerate(real.d) if d == tick and BOOT + i + 1 > now)
            m.advance(BOOT + k + 1 - now)
            cg = m.read_bytes(C, 0, 512)
            words = [int.from_bytes(cg[i:i + 2], "little") for i in range(0, 512, 2)]
            ent = parse_oam(m.read_bytes(O, 0, 544))
            shot = tmp_path / f"{name.replace(' ', '_')}.png"
            m.screenshot(str(shot))
            now = BOOT + k + 2
            img = np.asarray(Image.open(shot).convert("RGB"))
            d = real.d[k]
            s = STATES
            boss_x = min(ent[i][0] for i in range(6, 10))
            actors = [("boss", (boss_x, ent[6][1]), BOSS[s["boss"][d].frame], 2, bool(ent[6][3] & 0x40)),
                      ("ea", (ent[4][0], ent[4][1]), EA[s["ea"][d].frame % D.ENEMY_FPF], 3, bool(ent[4][3] & 0x40)),
                      ("eb", (ent[5][0], ent[5][1]), EB[s["eb"][d].frame % D.ENEMY_FPF], 3, bool(ent[5][3] & 0x40))]
            for who, slot, pal in (("p1", 0, 0), ("p2", 2, 1)):
                fr = HERO[s[who][d].frame]
                fr = fr if ent[slot][4] == 32 else fr[:, :16]
                actors.append((who, (ent[slot][0], ent[slot][1]), fr, pal, bool(ent[slot][3] & 0x40)))
            boxes = [(x, y, a.shape[1], a.shape[0]) for _, (x, y), a, _, _ in actors]
            for i, (who, (x, y), want, pal, flip) in enumerate(actors):
                want = want[:, ::-1] if flip else want
                h, w = want.shape
                crop = img[PICTURE_TOP + y:PICTURE_TOP + y + h, x:x + w]
                pal_rgb = rgb_of([words[0]] + words[C_OBJ + 16 * pal + 1:C_OBJ + 16 * pal + 16])
                differs = np.abs(crop.astype(float) - pal_rgb[want]).max(-1) > 10
                free = np.ones((h, w), bool)
                for j, (bx, by, bw, bh) in enumerate(boxes):
                    if j != i:
                        free[max(0, by - y):max(0, by + bh - y), max(0, bx - x):max(0, bx + bw - x)] = False
                bad = differs & free
                assert not bad.any(), f"{name} (tick {d}): {who} differs from its committed frame ({int(bad.sum())} px)"
                checked += int(free.sum())
    assert checked > 30000


# --- 6. the planted fault: the intact-frame check must catch it ------------------------------------------------------------------
def test_a_stream_one_tick_late_is_caught(late):
    """Every tick's rows played one tick late: the director's deadlines are met by exactly zero ticks of slack
    on some rows, so frames reach the screen half-loaded. The detector must see it."""
    assert late.tears, "the intact-frame check did not fire on a stream that is one tick late"
    assert {a for _, a in late.tears} & {"boss", "p1", "p2"}


def test_the_planted_fault_leaves_the_real_rom_untouched():
    assert ROMS["real"].read_bytes() != ROMS["late"].read_bytes()
    assert ROMS["real"].read_bytes() != ROMS["naive"].read_bytes()


# --- 7. what the allocator charged -----------------------------------------------------------------------------------------------------
def test_the_allocator_charges_the_choreographed_worst_tick():
    line = next(ln for ln in (BUILD / "dgnf" / "allocation_report.txt").read_text().splitlines() if "VBLANK-DMA" in ln)
    assert "1056" in line and "384 arm" in line and "4 transfers" in line, line   # 544 OAM + 512; 3 x 128
