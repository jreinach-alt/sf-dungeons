"""dgn_tilestream — the scheduler and the emitted score, PURE (no ROM): docs/dungeons/21.

runtime: ~10 s.

Three jobs. (1) The CLOSED-FORM EQUATION (model.equation) predicts the spin speed at each depth from the pictures'
measured byte counts and the VBlank budget; the scheduler, a greedy earliest-completion solver, must land inside the
bracket the equation gives. (2) An INDEPENDENT INTERPRETER replays the EMITTED BINARIES (the command stream, the pool
blobs, the pointer table) into a simulated VRAM and draws what each tick shows; that must equal the source pictures
over two loops, the second starting from the state the first left (the entry/loop closure). (3) The invariants the
rail relies on: the budget, no DMA crossing a bank, the visibility rule, the dodge clearance.
"""
import math
import sys
from pathlib import Path

SUPERFORGE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SUPERFORGE / "tools"))
sys.path.insert(0, str(SUPERFORGE / "vendor"))
# FIRST, before numpy: see tests/test_dgn_hero.py (the core is dlopen'd at import)
from machine import Machine  # noqa: E402,F401  (import order only)

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from dgn_tilestream import director as D  # noqa: E402
from dgn_tilestream import model as M  # noqa: E402
import gen_dgn_fight_assets as GF  # noqa: E402
import gen_dgn_tile_assets as GT  # noqa: E402


@pytest.fixture(scope="module")
def scene():
    return D.compile_scene()


@pytest.fixture(scope="module")
def pics():
    return M.load_pictures()


# --- 1. the equation ------------------------------------------------------------------------------------------------------
def _spin_rate(scene, prefix):
    """Mean degrees a tick across the consecutive spin swaps of one set, excluding the long holds."""
    sw = [p for p in scene["events"] if p.ev.kind == "swap"]
    deg = ticks = 0
    for a, b in zip(sw, sw[1:]):
        if a.ev.vid[0] == prefix and b.ev.vid[0] == prefix and b.tick - a.tick < 8:
            deg += ((b.ev.pic - a.ev.pic) % 24) * M.STEP
            ticks += b.tick - a.tick
    return deg / ticks


def test_the_shallow_spin_is_bound_by_the_display_not_the_dma(scene):
    row = M.depth_table(r0s=(24,))[0]
    eq = M.equation(row, scene["cap"] - scene["reserve_mc"])
    assert eq["pictures_per_tick"] == 1.0 and eq["bound"].startswith("display")
    assert _spin_rate(scene, "s") == pytest.approx(30.0)


def test_the_mid_spin_lands_inside_the_closed_forms_bracket(scene):
    """The equation with the players' reserve held back is the floor, with none the ceiling (the scheduler has the
    players' real, smaller cost to spend). Mid depth is bound by DMA: ~0.6 of a picture a tick."""
    row = M.depth_table(r0s=(20,))[0]
    lo = M.equation(row, scene["cap"] - scene["reserve_mc"])
    hi = M.equation(row, scene["cap"])
    assert lo["bound"].startswith("DMA")
    got = _spin_rate(scene, "m")
    assert lo["deg_per_tick"] - 0.5 <= got <= hi["deg_per_tick"] + 0.5, (lo["deg_per_tick"], got, hi["deg_per_tick"])
    assert got < 30.0, "the mid spin is DMA-bound: it cannot reach one picture a tick"


def test_deeper_is_slower_and_fewer_pictures_fit_in_the_rom(scene):
    rows = [M.equation(r, scene["cap"] - scene["reserve_mc"], rom_budget=D.POOL_CLAIMS * D.POOL_BYTES)
            for r in M.depth_table()]
    rates = [r["deg_per_tick"] for r in rows]
    fit = [r["pictures_in_rom"] for r in rows]
    assert rates == sorted(rates, reverse=True) and fit == sorted(fit, reverse=True)
    assert rates[0] == 30.0 and rates[-1] < 10


def test_the_pause_before_a_cut_is_the_cut_bases_load(scene):
    """The cut base (the largest picture) cannot be loaded in one tick of capacity: the director stalls for it, and the
    stall is what the equation says it is (a picture of that size needs this many ticks of the whole budget)."""
    for k, cuts in scene["cuts"].items():
        v = scene["lib"][f"c{k}"]
        need = math.ceil(M.cost_mc(v.load_bytes(), 3) / scene["cap"])
        swap = cuts["swap"]
        prev = max(p.tick for p in scene["events"] if p.ev.kind == "swap" and p.tick < swap)
        assert swap - prev >= need - 1, (k, swap - prev, need)


# --- 2. the independent interpreter ---------------------------------------------------------------------------------------
def _decode(raw: bytes) -> np.ndarray:
    """32 B of SNES 4bpp -> 8x8 indices (written here, not imported: the encoder's inverse is the check)."""
    b = np.frombuffer(raw, np.uint8).reshape(2, 8, 2)                    # [plane pair][row][plane lsb/msb]
    planes = [np.unpackbits(b[0, :, 0]).reshape(8, 8), np.unpackbits(b[0, :, 1]).reshape(8, 8),
              np.unpackbits(b[1, :, 0]).reshape(8, 8), np.unpackbits(b[1, :, 1]).reshape(8, 8)]
    return sum(p.astype(np.uint8) << i for i, p in enumerate(planes))


class Vram:
    """The four boss regions and the players' OBJ region, as a command writes them."""

    def __init__(self):
        self.chr = [bytearray(304 * 32), bytearray(304 * 32)]
        self.map = [bytearray(4096), bytearray(4096)]
        self.obj = bytearray(4096)

    def region(self, kind):
        return {D.K_CHR_A: self.chr[0], D.K_CHR_B: self.chr[1], D.K_MAP_A: self.map[0], D.K_MAP_B: self.map[1],
                D.K_OBJ: self.obj}[kind]

    def apply(self, cmd, blobs):
        kind, dst, blob, src, n = cmd
        r = self.region(kind)
        r[dst * 2:dst * 2 + n] = blobs[blob][src:src + n]

    def draw(self, layer, vofs):
        """The layer as the PPU draws it: 32 x 64 cells, slot 0 blank, line y shows row (y + VOFS + 1) mod 512."""
        words = np.frombuffer(bytes(self.map[layer]), "<u2").reshape(64, 32)
        tiles = np.stack([_decode(bytes(self.chr[layer][s * 32:s * 32 + 32])) for s in range(304)])
        canvas = np.zeros((512, 256), np.uint8)
        for r in range(64):
            for c in range(32):
                canvas[r * 8:r * 8 + 8, c * 8:c * 8 + 8] = tiles[words[r, c] & 0x3FF]
        rows = (np.arange(224) + vofs + 1) % 512
        return canvas[rows]


def _blobs(scene):
    return scene["pool"].finish() + [b"".join(GF.tiles_rowmajor(f) for f in GF.hero_frames())]


def _stream(scene):
    cmds, ptr = GT.command_bytes(scene)
    off = [int.from_bytes(ptr[i:i + 2], "little") for i in range(0, len(ptr), 2)]
    def parse(a, b):
        out = []
        for i in range(a, b, 8):
            c = cmds[i:i + 8]
            out.append((c[5], int.from_bytes(c[0:2], "little"), c[4], int.from_bytes(c[2:4], "little"),
                        int.from_bytes(c[6:8], "little")))
        return out
    T = scene["T"]
    return [parse(off[t], off[t + 1]) for t in range(T)], parse(off[T], off[T + 1])


def test_replaying_the_emitted_binaries_draws_the_source_pictures_over_two_loops(scene, pics):
    blobs = _blobs(scene)
    per_tick, init = _stream(scene)
    T = scene["T"]
    vr = Vram()
    for c in init:
        vr.apply(c, blobs)
    bad = []
    for loop in range(2):                              # the second loop starts from what the first left behind
        for t in range(T):
            for c in per_tick[t]:
                vr.apply(c, blobs)
            tk = scene["ticks"][t]
            got = vr.draw(tk["layer"], tk["vofs"])
            want = np.zeros((224, 256), np.uint8)
            for y in range(224):
                r = (y + tk["vofs"] + 1) % 512
                if r < M.CH:
                    want[y] = pics[tk["pic"]][r]
            if (got != want).any():
                bad.append((loop, t, int((got != want).sum())))
    assert bad == [], f"{len(bad)} tick(s) draw the wrong picture, first: {bad[:4]}"


def test_a_command_stream_played_one_tick_late_is_caught_by_the_interpreter(scene, pics):
    blobs = _blobs(scene)
    per_tick, init = _stream(scene)
    T = scene["T"]
    vr = Vram()
    for c in init:
        vr.apply(c, blobs)
    bad = 0
    for t in range(T):
        for c in per_tick[(t - 1) % T]:
            vr.apply(c, blobs)
        tk = scene["ticks"][t]
        got = vr.draw(tk["layer"], tk["vofs"])
        want = np.zeros((224, 256), np.uint8)
        for y in range(224):
            r = (y + tk["vofs"] + 1) % 512
            if r < M.CH:
                want[y] = pics[tk["pic"]][r]
        bad += bool((got != want).any())
    assert bad >= 5, bad


# --- 3. the invariants ------------------------------------------------------------------------------------------------------
def test_no_tick_spends_more_than_the_budget(scene):
    per_tick, _ = _stream(scene)
    cost = [sum(M.cost_mc(c[4]) for c in cs) for cs in per_tick]
    assert max(cost) <= scene["cap"], (max(cost), scene["cap"])
    assert max(cost) > 0.9 * scene["cap"], "the director is not filling the budget: it is not the limiter"


def test_no_dma_run_crosses_a_bank_and_every_run_is_inside_its_blob(scene):
    per_tick, init = _stream(scene)
    sizes = [len(b) for b in _blobs(scene)]
    for c in [c for cs in per_tick for c in cs] + init:
        kind, dst, blob, src, n = c
        assert 0 < n and src + n <= sizes[blob], c
        assert dst * 2 + n <= {D.K_CHR_A: 304 * 32, D.K_CHR_B: 304 * 32, D.K_MAP_A: 4096, D.K_MAP_B: 4096,
                               D.K_OBJ: 4096}[kind], c


def test_only_rows_that_are_loaded_are_ever_on_screen(scene):
    """The visibility rule: with the eye at screen height y, canvas rows >= 136 - y show, and the picture's set was
    loaded from row r0 down, so 136 - y >= 8 * r0 on every tick."""
    for t, tk in enumerate(scene["ticks"]):
        assert 136 - tk["y"] >= 8 * scene["lib"][tk["vid"]].r0 - 1e-6, (t, tk)


def test_the_spin_never_steps_past_the_readable_limit(scene):
    """The crown's five points repeat every 72 degrees, so a step over half of that is aliasing, not animation."""
    sw = [p for p in scene["events"] if p.ev.kind == "swap"]
    steps = [((b.ev.pic - a.ev.pic) % 24) * M.STEP for a, b in zip(sw, sw[1:]) if a.ev.vid[0] in "sm" and b.ev.vid[0] in "sm"]
    assert max(steps) <= 36 and max(steps) == 30


def test_the_blade_never_comes_near_a_player(scene):
    near = 999.0
    for t in range(scene["T"]):
        r = D.blade_reach(scene["cuts"], t)
        if not r:
            continue
        k, reach = r
        a = math.radians(D.HEADING[k])
        ex, ey = 128, scene["ticks"][t]["y"]
        for who in ("p1", "p2"):
            s = scene["players"][who][t]
            dx, dy = s.x - ex, s.y - ey
            if -10 <= dx * math.cos(a) + dy * math.sin(a) <= reach + 10:
                near = min(near, abs(dx * math.sin(a) - dy * math.cos(a)))
    assert near >= 26, near


def test_the_players_never_exceed_a_walk_and_a_dodge(scene):
    for who in ("p1", "p2"):
        st = scene["players"][who]
        assert max(math.hypot(st[t].x - st[t - 1].x, st[t].y - st[t - 1].y) for t in range(1, len(st))) <= 3.7


def test_the_rom_budget_is_the_claims(scene):
    assert len(scene["pool"].blobs) <= D.POOL_CLAIMS
    with pytest.raises(SystemExit):
        p = D.Pool()
        for i in range(D.POOL_CLAIMS + 1):
            p.add(f"b{i}", bytes(D.POOL_BYTES))
        p.finish()
