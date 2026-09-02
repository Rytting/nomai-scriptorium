"""What actually breaks in the strict round trip at higher jitter?"""
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nomai.codec import write
from nomai.decode import Observation, decode_strict
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


reasons = Counter()
for hw in (0.2, 0.3):
    for base, n in ((256, 20), (200_000, 20), (200_000, 8)):
        rng = random.Random(4242 + n)
        for t in range(5):
            msg = phrase(rng, n)
            grid = write(msg, base, STRICT)
            path = TMP / "fail.svg"
            path.write_text(
                render_grid(grid, KNOWN_GLYPHS, hw, seed=7000 + t), encoding="utf-8"
            )
            want = Observation.from_grid(grid)
            try:
                obs = analyze(path)
            except Exception as exc:  # noqa: BLE001
                reasons[(hw, "analyze " + type(exc).__name__, str(exc)[:38])] += 1
                continue
            if obs.glyphs != want.glyphs:
                same_cells = set(obs.glyphs) == set(want.glyphs)
                bad = sum(1 for c in set(obs.glyphs) & set(want.glyphs)
                          if obs.glyphs[c] != want.glyphs[c])
                kind = ("identity only" if same_cells else "structure")
                extra = (f"{bad}/{len(want.glyphs)} ids wrong" if same_cells
                         else f"cols {max(c for c, _ in obs.glyphs)} vs "
                              f"{max(c for c, _ in want.glyphs)}, "
                              f"rows {sorted({j for _, j in obs.glyphs})} vs "
                              f"{sorted({j for _, j in want.glyphs})}")
                reasons[(hw, "glyphs differ: " + kind, extra)] += 1
                continue
            if obs.paths != want.paths:
                reasons[(hw, "paths differ", "")] += 1
                continue
            if obs.connections != want.connections:
                reasons[(hw, "endpoints differ", "")] += 1
                continue
            try:
                res = decode_strict(obs, bases=(base,))
            except Exception as exc:  # noqa: BLE001
                reasons[(hw, "decode " + type(exc).__name__, str(exc)[:38])] += 1
                continue
            if not (len(res) == 1 and res[0][2] == msg):
                reasons[(hw, "reading", f"{len(res)} readings")] += 1

for (hw, kind, detail), c in reasons.most_common():
    print(f"hw={hw}  {c:>2}x  {kind:<28} {detail}")
if not reasons:
    print("no failures")
