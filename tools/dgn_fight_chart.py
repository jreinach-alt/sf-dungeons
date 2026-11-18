#!/usr/bin/env python3
"""dgn_fight_chart.py — the measured VBlank profile of the three streams of the same score (docs/dungeons/19).

    python3 tools/dgn_fight_chart.py OUT.png

Runs build/dgn_fight{,_hybrid,_naive}.sfc in lockstep for one loop and plots, per tick, the scanline the NMI hook
finished on (VBlank is 225..261). The V counter is read from the ROM's own latch, not computed."""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "vendor"))
sys.path.insert(0, str(REPO / "tools"))
from machine import Machine, MemoryType  # noqa: E402

from PIL import Image, ImageDraw  # noqa: E402

from dgn_fight import director as D  # noqa: E402

W_ = MemoryType.SnesWorkRam
J = json.loads((REPO / "build" / "dgnf" / "symbol_map.json").read_text())
DP = {p["sym"]: p["start"] for p in J["scenes"]["fight"]["placements"] if p["class"] == "dp"}
T = D.total_ticks()


def profile(rom):
    out = [None] * T
    with Machine(str(rom)) as m:
        m.advance(30)
        for _ in range(T + 40):
            m.advance(1)
            ct = m.read_u16(W_, DP["US_CT"])
            out[(ct - 1) % T] = m.read_u16(W_, DP["US_VEND"])
    Machine.close_current()
    return out


def main(argv):
    out = Path(argv[1])
    series = [("unchoreographed", (214, 70, 60), REPO / "build" / "dgn_fight_naive.sfc"),
              ("boss planned, players reactive", (230, 170, 50), REPO / "build" / "dgn_fight_hybrid.sfc"),
              ("fully choreographed", (70, 170, 90), REPO / "build" / "dgn_fight.sfc")]
    data = [(n, c, profile(r)) for n, c, r in series]
    W, H, L, B = T + 120, 330, 70, 40
    im = Image.new("RGB", (W, H), (24, 22, 30))
    d = ImageDraw.Draw(im)
    y_of = lambda v: H - B - (v - 225) * (H - B - 30) / (262 - 225)
    for v in range(225, 263, 6):
        d.line([(L, y_of(v)), (L + T, y_of(v))], fill=(50, 48, 60))
        d.text((8, y_of(v) - 5), str(v), fill=(170, 170, 180))
    d.line([(L, y_of(261)), (L + T, y_of(261))], fill=(255, 255, 255), width=2)
    d.text((L + 4, y_of(261) - 14), "261: the picture starts again, VRAM writes after this are lost", fill=(255, 255, 255))
    d.text((L, 8), "scanline the NMI hook finished on, per tick of the 580-tick loop (measured)", fill=(230, 230, 235))
    for i, (name, col, prof) in enumerate(data):
        pts = [(L + t, y_of(prof[t])) for t in range(T)]
        d.line(pts, fill=col, width=1)
        d.text((L + 10, H - 34 + i * 11), f"{name}: worst {max(prof)}", fill=col)
    im.save(out)
    print(out, {n: max(p) for n, _, p in data})


if __name__ == "__main__":
    main(sys.argv)
