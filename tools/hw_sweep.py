"""Where does handwriting start to break the strict round trip?

Three levels was too coarse to base a recommendation on. This walks the range in
finer steps and separates the two ways a run can end: read exactly and uniquely, or
fail to read at all. Strict never returns a wrong answer quietly, so those are the
only two outcomes that matter.
"""
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nomai.codec import write
from nomai.decode import decode_strict
from nomai.glyphs import KNOWN_GLYPHS
from nomai.oracle import STRICT
from nomai.render import render_grid
from nomai.vision import analyze

WORDS = (
    "the nomai came to this solar system searching for eye of universe a signal "
    "older than itself and they never did find it built ash twin project send"
).split()
TMP = ROOT / "data" / "strict_svg"
TMP.mkdir(exist_ok=True)


def phrase(rng, n):
    out = []
    while sum(len(w) + 1 for w in out) < n + 8:
        out.append(rng.choice(WORDS))
    return " ".join(out)[:n].strip()


LEVELS = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8)
TRIALS = 5
print(f"{'hw':>5} " + "".join(f"{f'b{b}/{n}':>10}" for b in (256, 200000) for n in (8, 20))
      + f"{'overall':>10}")
print("-" * 60)
t0 = time.perf_counter()
for hw in LEVELS:
    cells, tot_ok, tot_n = [], 0, 0
    for base in (256, 200_000):
        for n in (8, 20):
            rng = random.Random(4242 + n)
            ok = 0
            for t in range(TRIALS):
                msg = phrase(rng, n)
                grid = write(msg, base, STRICT)
                path = TMP / "sweep.svg"
                path.write_text(
                    render_grid(grid, KNOWN_GLYPHS, hw, seed=7000 + t), encoding="utf-8"
                )
                try:
                    res = decode_strict(analyze(path), bases=(base,))
                    if len(res) == 1 and res[0][2] == msg:
                        ok += 1
                except Exception:  # noqa: BLE001
                    pass
            cells.append(f"{ok}/{TRIALS}")
            tot_ok += ok
            tot_n += TRIALS
    print(f"{hw:>5} " + "".join(f"{c:>10}" for c in cells)
          + f"{f'{tot_ok}/{tot_n}':>10}")
print(f"\n{time.perf_counter() - t0:.0f}s")
