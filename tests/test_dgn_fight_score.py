"""dgn_fight — the SCORE, checked without an emulator (docs/dungeons/19).

runtime: ~2 s. Pure Python.

Two kinds of claim, kept apart:

  * the CHOREOGRAPHY is what was asked for: the boss moves about the arena through a sequence of attacks; player 1
    follows it and attacks from three sides and backs away from every attack; player 2 and both small enemies
    fight. These read the director's per-tick states.

  * the SCHEDULE is safe: a second, independent interpreter plays the EMITTED binaries (score, command stream,
    pointer table) against an abstract VRAM and requires that on every tick every streamed actor's displayed
    buffer holds exactly the frame the score says it shows. It shares no code with the director's planner, so
    a bug there cannot hide in both.
"""
import math
import sys
from pathlib import Path

SUPERFORGE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SUPERFORGE / "tools"))
sys.path.insert(0, str(SUPERFORGE / "vendor"))
# FIRST, before numpy: see tests/test_dgn_hero.py (the core is dlopen'd at import)
from machine import Machine  # noqa: E402,F401  (import order only)

import pytest  # noqa: E402

from dgn_fight import director as D  # noqa: E402
import gen_dgn_fight_assets as G  # noqa: E402


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = {}
    for mode in ("choreo", "naive", "hybrid"):
        d = tmp_path_factory.mktemp(f"fight_{mode}")
        assert G.main([str(d), "--mode", mode]) == 0
        out[mode] = {n: (d / n).read_bytes() for n in
                     ("dgnf_score.bin", "dgnf_cmds.bin", "dgnf_ptr.bin", "dgnf_report.json")}
    return out


@pytest.fixture(scope="module")
def states():
    return D.all_states()


# =============================== the choreography ===================================================================
def dist(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)


def test_the_boss_moves_about_the_arena_through_a_series_of_attacks(states):
    boss = states["boss"]
    xs = [s.x for s in boss]
    assert max(xs) - min(xs) >= 60, "the boss must travel across the arena"
    ys = [s.y for s in boss]
    assert max(ys) - min(ys) >= 12
    acts = []
    for s in boss:
        if not acts or acts[-1] != s.action:
            acts.append(s.action)
    assert "attack" in acts and "whirl" in acts and "prepare" in acts and "scuttle" in acts and "idle" in acts
    assert acts.count("attack") >= 2, "a series of attacks, not one"
    faces = {s.face for s in boss}
    assert faces == {"down", "right", "left"}, "the boss turns to every side (left is the right art, flipped)"
    assert (boss[0].x, boss[0].y) == (boss[-1].x, boss[-1].y), "the loop must close in position"


def test_every_boss_attack_is_telegraphed_by_a_prepare(states):
    boss = states["boss"]
    for t in range(1, len(boss)):
        if boss[t].action in ("attack", "whirl") and boss[t - 1].action not in ("attack", "whirl"):
            assert boss[t - 1].action == "prepare", f"tick {t}: an attack with no telegraph"


def test_player_one_attacks_from_three_sides(states):
    p1, boss = states["p1"], states["boss"]
    sides = set()
    for t in range(len(p1)):
        if p1[t].action == "attack":
            dx, dy = p1[t].x - boss[t].x, p1[t].y - boss[t].y
            sides.add("left" if dx < -25 else "right" if dx > 25 else "above" if dy < -25 else "?")
    assert sides == {"left", "right", "above"}, sides


def test_player_one_keeps_clear_of_every_boss_attack(states):
    """Backing away: while the boss's slam or whirl is in its attack frames, the player is out of reach."""
    p1, boss = states["p1"], states["boss"]
    n = 0
    for t in range(len(boss)):
        if boss[t].action in ("attack", "whirl"):
            assert dist(p1[t], boss[t]) >= D.DANGER_R, f"tick {t}: {dist(p1[t], boss[t]):.0f} px from a {boss[t].action}"
            n += 1
    assert n >= 80


def test_player_one_actually_backs_away_during_the_telegraph(states):
    """Facing the boss and walking AWAY from it: the distance grows during a prepare, and the walk is shown."""
    p1, boss = states["p1"], states["boss"]
    backed = 0
    for t in range(1, len(boss)):
        if boss[t].action == "prepare" and boss[t - 1].action == "prepare":
            if dist(p1[t], boss[t]) > dist(p1[t - 1], boss[t - 1]) + 0.3 and p1[t].action == "walk":
                backed += 1
    assert backed >= 60, f"only {backed} ticks of backing away"


def test_player_one_never_overlaps_the_boss_and_always_faces_it(states):
    p1, boss = states["p1"], states["boss"]
    for t in range(len(p1)):
        assert dist(p1[t], boss[t]) >= 34, f"tick {t}: inside the boss"
        dx = boss[t].x - p1[t].x
        if abs(dx) > 1.6 * abs(boss[t].y - p1[t].y) and abs(dx) > 40:    # clearly to one side: faces it (left = the right art, flipped)
            assert p1[t].flip == (dx < 0) and p1[t].face != "down", f"tick {t}: facing away from the boss"


def test_player_one_never_outruns_a_walking_figure(states):
    p1 = states["p1"]
    for t in range(8, len(p1)):
        sp = math.hypot(p1[t].x - p1[t - 8].x, p1[t].y - p1[t - 8].y) / 8
        assert sp <= 2.6, f"tick {t}: {sp:.2f} px/tick"


def test_player_two_fights_both_small_enemies(states):
    p2, ea, eb = states["p2"], states["ea"], states["eb"]
    for name, e in (("ea", ea), ("eb", eb)):
        assert any(s.action == "attack" for s in e), f"{name} never attacks"
    assert any(s.action == "attack" for s in p2), "player 2 never strikes"
    assert any(s.action == "walk" for s in p2), "player 2 never dodges"
    # contact: each enemy is within striking range of player 2 on the tick it lands its leap
    for name, e in (("ea", ea), ("eb", eb)):
        close = min(dist(p2[t], e[t]) for t in range(len(e)) if e[t].action == "attack")
        assert close < 50, f"{name} never closes on player 2 ({close:.0f} px)"
    # and player 2 counters while an enemy is still near
    near = [t for t in range(len(p2)) if p2[t].action == "attack"
            and min(dist(p2[t], ea[t]), dist(p2[t], eb[t])) < 60]
    assert len(near) >= 40, "player 2 swings at nothing"


def test_everyone_stays_on_the_screen_and_the_loop_closes(states):
    for who, seq in states.items():
        for t, s in enumerate(seq):
            assert 8 <= s.x <= 248 and 40 <= s.y <= 215, f"{who} tick {t}: ({s.x}, {s.y}) off the arena"
    for who in ("p1", "p2", "ea", "eb"):
        a, b = states[who][0], states[who][-1]
        assert math.hypot(a.x - b.x, a.y - b.y) <= 8, f"{who}: the loop does not close ({a.x},{a.y}) -> ({b.x},{b.y})"


# =============================== the schedule ==========================================================================
def vram_after(plan_bin, ticks):
    """Play the emitted stream on an abstract VRAM. Returns, per tick, {(actor, buffer): frame held} as seen
    AFTER that tick's rows. A row is identified by (vmadd, blob id, source offset); a frame is 'held' by a
    buffer once all of its rows are there."""
    cmds, ptr = plan_bin["dgnf_cmds.bin"], plan_bin["dgnf_ptr.bin"]
    off = lambda i: int.from_bytes(ptr[2 * i:2 * i + 2], "little")
    rows = lambda a, b: [(int.from_bytes(cmds[i:i + 2], "little"), int.from_bytes(cmds[i + 2:i + 4], "little"),
                          cmds[i + 4]) for i in range(a, b, 6)]
    # the VRAM word offset of each slot row -> (actor, buffer, row)
    where = {}
    for actor, sl in D.SLOTS.items():
        for buf in (0, 1):
            for row in range(sl["rows"]):
                where[D.vmadd_of(actor, buf, row)] = (actor, buf, row)

    def src_frame(actor, bid, offset):
        if actor == "boss":
            return bid * D.BOSS_FRAMES_PER_BLOB + offset // 2048, (offset % 2048) // 256
        return offset // 512, (offset % 512) // 128

    cell = {}                                        # (actor, buf, row) -> frame whose row is there
    for dst, o, bid in rows(off(ticks), off(ticks + 1)):    # the entry state, loaded in forced blank
        a, b, r = where[dst]
        f, rr = src_frame(a, bid, o)
        assert rr == r, "an entry-state row from the wrong source row"
        cell[(a, b, r)] = f
    held = []
    loads = []
    for t in range(ticks):
        n = 0
        for dst, o, bid in rows(off(t), off(t + 1)):
            a, b, r = where[dst]
            f, rr = src_frame(a, bid, o)
            assert rr == r, f"tick {t}: a row loaded from the wrong source row"
            cell[(a, b, r)] = f
            n += 1
        loads.append(n)
        snap = {}
        for actor, sl in D.SLOTS.items():
            for buf in (0, 1):
                fr = {cell.get((actor, buf, r)) for r in range(sl["rows"])}
                snap[(actor, buf)] = fr.pop() if len(fr) == 1 else None      # None: a half-written buffer
        held.append(snap)
    return held, loads


def decode_record(rec):
    """Names of the streamed actors from a 51 B record: {actor: buffer displayed} read off the OAM names."""
    ent = [rec[i * 4:i * 4 + 4] for i in range(12)]
    out = {}
    for who, slot in (("p1", 0), ("p2", 2)):
        out[who] = {D.name_of(who, 0): 0, D.name_of(who, 1): 1}[ent[slot][2]]
    out["boss"] = None
    names = {D.name_of("boss", 0): 0, D.name_of("boss", 1): 1}
    # any of the four quadrants names its buffer: TL/TR/BL/BR are base + 0/4/64/68 (flipped: TR first)
    base = min(ent[s][2] for s in range(6, 10))
    out["boss"] = names[base]
    return out


@pytest.mark.parametrize("mode", ["choreo", "naive", "hybrid"])
def test_every_displayed_frame_is_in_its_buffer_on_every_tick(built, states, mode):
    """The independent interpreter: on EVERY tick, the buffer the OAM names point at holds the frame the score
    says is shown, whole. (Naive too: it is the same score, streamed the other way.)"""
    b = built[mode]
    T = len(states["boss"])
    score = b["dgnf_score.bin"]
    held, _ = vram_after(b, T)
    for t in range(T):
        buf = decode_record(score[t * D.RECORD_BYTES:(t + 1) * D.RECORD_BYTES])
        for actor in ("boss", "p1", "p2"):
            want = states[actor][t].frame
            got = held[t][(actor, buf[actor])]
            assert got == want, f"[{mode}] tick {t}: {actor} shows buffer {buf[actor]} holding {got}, the score wants {want}"


def test_a_frame_is_never_overwritten_while_it_is_on_screen(built, states):
    """The other half of safety: a row may land only in the buffer that is NOT displayed on that tick."""
    b = built["choreo"]
    T = len(states["boss"])
    score = b["dgnf_score.bin"]
    cmds, ptr = b["dgnf_cmds.bin"], b["dgnf_ptr.bin"]
    off = lambda i: int.from_bytes(ptr[2 * i:2 * i + 2], "little")
    where = {}
    for actor, sl in D.SLOTS.items():
        for buf in (0, 1):
            for row in range(sl["rows"]):
                where[D.vmadd_of(actor, buf, row)] = (actor, buf)
    rec = lambda t: decode_record(score[(t % T) * D.RECORD_BYTES:((t % T) + 1) * D.RECORD_BYTES])
    for t in range(T):
        now, before = rec(t), rec(t - 1)
        for i in range(off(t), off(t + 1), 6):
            actor, buf = where[int.from_bytes(cmds[i:i + 2], "little")]
            # a row may land in a buffer that is being SWAPPED IN this tick (same VBlank as the OAM change) or that
            # was just swapped out; never in one that is shown on both sides of the tick
            assert not (buf == now[actor] and buf == before[actor]), \
                f"tick {t}: a row written into {actor}'s buffer {buf}, which stays on screen through the tick"


def test_the_choreographed_stream_flattens_the_peak(built):
    """The result the owner asked about. The same score, streamed two ways."""
    import json
    rep = json.loads(built["choreo"]["dgnf_report.json"])
    ch, nv = rep["choreo"], rep["naive"]
    assert nv["peak_bytes"] >= 3000, "the control should be the dgn_boss worst case (boss + both players on one tick)"
    assert ch["peak_bytes"] <= 640, ch
    assert nv["peak_bytes"] >= 5 * ch["peak_bytes"], (nv["peak_bytes"], ch["peak_bytes"])
    assert ch["peak_transfers"] <= 4 < nv["peak_transfers"]
    # the work is the same; it is the SHAPE that changed
    assert abs(ch["total_bytes"] - nv["total_bytes"]) < 0.1 * nv["total_bytes"]


def test_the_realistic_hybrid_plans_the_boss_and_lets_the_players_react(built):
    """A real game cannot prefetch a player's frame (it follows human input), only the boss's and the scripted
    enemies'. The hybrid plans the boss and streams the players on demand: between the two extremes."""
    import json
    rep = json.loads(built["choreo"]["dgnf_report.json"])
    ch, hy, nv = rep["choreo"], rep["hybrid"], rep["naive"]
    assert ch["peak_bytes"] < hy["peak_bytes"] < nv["peak_bytes"], (ch["peak_bytes"], hy["peak_bytes"], nv["peak_bytes"])
    assert hy["peak_bytes"] <= 1280, hy["peak_bytes"]              # measured 1,024 B: both players on one tick, the boss routed round them


def test_a_buffer_swap_costs_no_dma_when_the_frame_is_already_there(states):
    """An idle that toggles between two frames needs both resident once and then nothing: the cache is real."""
    plan = D.compile_stream(states)
    naive = D.compile_stream(states, naive=True)
    assert sum(plan["bytes"]) < sum(naive["bytes"]), "the buffers saved no work at all"


def test_the_score_fits_its_claims(built):
    assert len(built["choreo"]["dgnf_score.bin"]) == G.SCORE_CLAIM
    assert len(built["choreo"]["dgnf_cmds.bin"]) == G.CMDS_CLAIM
    assert len(built["choreo"]["dgnf_ptr.bin"]) == G.PTR_CLAIM
    T = len(D.boss_states())
    assert T * D.RECORD_BYTES <= G.SCORE_CLAIM


def test_an_odd_number_of_changes_gets_a_parity_swap():
    """Every change flips the displayed buffer: an odd count would make the pattern repeat every TWO loops."""
    seq = [0] * 10 + [1] * 10 + [2] * 10
    changes = lambda q: sum(1 for t in range(len(q)) if q[t] != q[t - 1])
    out = D._add_parity_swap(seq)
    assert changes(seq) % 2 == 1 and changes(out) % 2 == 0
    assert [v % D.VIRT for v in out] == seq, "the swap re-shows the same frame from the other buffer"
    bufsel, jobs, init = D.plan_buffers(seq)             # reaches a steady state (it would raise otherwise)
    assert len(bufsel) == 30


def test_every_prefetch_window_is_narrower_than_the_loop(states):
    plan = D.compile_stream(states)
    T = plan["T"]
    for actor, jobs in plan["jobs"].items():
        for frame, buf, rel, d in jobs:
            assert 0 <= d - rel < T, (actor, frame, rel, d)
