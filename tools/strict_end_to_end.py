"""Write a message, draw it, read the drawing back. Strict dialect, full chain.

Until now the strict dialect was only ever tested by handing the decoder a grid
directly (600/600), and the vision frontend was only ever tested on upstream-dialect
drawings from Julia (48/60). This closes the loop: our own writing, through our own
renderer, back through the vision frontend and the linear replay.

The claim under test is that strict needs no search, no character prior and no
ranking -- exactly one reading comes back, and it is the message.
"""
import random
import string
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nomai.codec import write  # noqa: E402
from nomai.decode import Observation, decode_strict  # noqa: E402
from nomai.glyphs import KNOWN_GLYPHS  # noqa: E402
from nomai.oracle import STRICT  # noqa: E402
from nomai.render import render_grid  # noqa: E402
from nomai.vision import analyze  # noqa: E402

WORDS = (
    "the nomai came to this solar system searching for eye of universe a signal "
    "older than itself and they never did find it built ash twin project send "
    "memories back through time then ghost matter killed every last one of them"
).split()

OUT = ROOT / "data" / "strict_svg"
OUT.mkdir(exist_ok=True)


def english(rng, n):
    out = []
    while sum(len(w) + 1 for w in out) < n + 8:
        out.append(rng.choice(WORDS))
    return " ".join(out)[:n].strip()


def gibberish(rng, n):
    return "".join(rng.choice(string.ascii_letters + " .,!") for _ in range(n))


TRIALS = 4
print(f"{'base':>7} {'hw':>4} {'kind':>10} {'len':>4} {'cols':>5} {'vision':>7} "
      f"{'readings':>9} {'exact':>6}")
print("-" * 62)
totals = [0, 0]
for base in (256, 200_000):
  for hw in (0.0, 0.3, 0.6):
    for kind, gen in (("english", english), ("gibberish", gibberish)):
        for n in (3, 8, 15, 25):
            rng = random.Random(11 * n + base + len(kind))
            vis = ok = 0
            readings_seen = []
            cols = 0
            for t in range(TRIALS):
                msg = gen(rng, n)
                grid = write(msg, base, STRICT)
                svg = render_grid(grid, KNOWN_GLYPHS, hw, seed=1000 + t)
                path = OUT / f"{base}_{hw}_{kind}_{n}_{t}.svg"
                path.write_text(svg, encoding="utf-8")
                cols = grid.ncols
                try:
                    obs = analyze(path)
                except Exception:  # noqa: BLE001
                    readings_seen.append(-1)
                    continue
                want = Observation.from_grid(grid)
                if (obs.glyphs == want.glyphs and obs.paths == want.paths
                        and obs.connections == want.connections):
                    vis += 1
                try:
                    res = decode_strict(obs, bases=(base,))
                except Exception:  # noqa: BLE001
                    readings_seen.append(-1)
                    continue
                readings_seen.append(len(res))
                if len(res) == 1 and res[0][2] == msg:
                    ok += 1
            totals[0] += ok
            totals[1] += TRIALS
            uniq = sorted(set(readings_seen))
            print(f"{base:>7} {hw:>4} {kind:>10} {n:>4} {cols:>5} {vis}/{TRIALS:<5} "
                  f"{str(uniq):>9} {ok}/{TRIALS}")
print(f"\nexact unique round trip: {totals[0]}/{totals[1]}")
