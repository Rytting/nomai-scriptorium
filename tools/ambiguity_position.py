"""Where in the message does the ambiguity live?

Both paths start at (1, MIDLINE), so column 2 is *always* a branchy column, and it
perturbs the low-order end of X -- which is the start of the message. This measures
how far that contamination reaches, i.e. which part of a reading can be trusted.
"""
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nomai.decode import Observation, decode_backward  # noqa: E402
from nomai.gridgen import grid_from_message  # noqa: E402

WORDS = (
    "the nomai came to this solar system searching for eye of universe a signal "
    "older than itself and they never did find it built ash twin project send "
    "memories back through time then ghost matter killed every last one of them"
).split()

TRIALS = 60


def english(rng, n):
    out = []
    while sum(len(w) + 1 for w in out) < n + 8:
        out.append(rng.choice(WORDS))
    return " ".join(out)[:n].strip()


for base, n in ((256, 24), (256, 48), (200_000, 12)):
    rng = random.Random(99)
    diff_pos = Counter()
    last_diff = Counter()
    rivals = 0
    for _ in range(TRIALS):
        msg = english(rng, n)
        obs = Observation.from_grid(grid_from_message(msg, base))
        for _, _, text in decode_backward(obs, bases=(base,)):
            if text == msg or len(text) != len(msg):
                continue
            rivals += 1
            positions = [i for i, (a, b) in enumerate(zip(msg, text)) if a != b]
            if positions:
                last_diff[positions[-1]] += 1
                for p in positions:
                    diff_pos[p] += 1

    print(f"\nbase {base}, length {n}, {TRIALS} messages, {rivals} rival readings")
    print("  position of differing characters (share of rivals touching each index):")
    for p in range(n):
        c = diff_pos.get(p, 0)
        if c:
            bar = "#" * max(1, round(40 * c / rivals))
            print(f"    [{p:>2}] {c / rivals:>5.0%} {bar}")
    deepest = max(last_diff) if last_diff else -1
    print(f"  deepest index any rival ever differed at: {deepest} (of 0..{n - 1})")
