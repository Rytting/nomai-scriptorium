"""Does the strict dialect actually deliver a unique reading, and what does it cost?

Checks, over random messages at both bases:
  unique   decode_strict returns exactly one reading
  correct  that reading is the original message
  cost     how much longer the spiral gets vs the upstream dialect
"""
import random
import string
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nomai.codec import write  # noqa: E402
from nomai.decode import (  # noqa: E402
    Observation,
    column_options,
    decode_backward,
    decode_strict,
)
from nomai.gridgen import grid_from_message  # noqa: E402
from nomai.oracle import STRICT, UPSTREAM  # noqa: E402

WORDS = (
    "the nomai came to this solar system searching for eye of universe a signal "
    "older than itself and they never did find it built ash twin project send "
    "memories back through time then ghost matter killed every last one of them"
).split()


def english(rng, n):
    out = []
    while sum(len(w) + 1 for w in out) < n + 8:
        out.append(rng.choice(WORDS))
    return " ".join(out)[:n].strip()


def gibberish(rng, n):
    return "".join(rng.choice(string.ascii_letters + " .,!") for _ in range(n))


print("=== the hi / &i collision ===")
for dialect in (UPSTREAM, STRICT):
    obs = Observation.from_grid(write("hi", 256, dialect))
    if dialect == STRICT:
        readings = [t for _, _, t in decode_strict(obs, bases=(256,))]
    else:
        readings = [t for _, _, t in decode_backward(obs, bases=(256,))]
    print(f"  {dialect:>8}: {readings}")

print("\n=== round trip ===")
print(f"{'base':>7} {'kind':>10} {'len':>4} {'trials':>7} {'unique':>7} "
      f"{'correct':>8} {'branchy cols':>13} {'cols up/strict':>15}")
print("-" * 82)

TRIALS = 30
for base in (256, 200_000):
    for kind, gen in (("english", english), ("gibberish", gibberish)):
        for n in (2, 5, 12, 30, 60):
            rng = random.Random(7 * n + base)
            uniq = correct = 0
            branchy = 0
            up_cols = st_cols = 0
            for _ in range(TRIALS):
                msg = gen(rng, n)
                obs = Observation.from_grid(write(msg, base, STRICT))
                st_cols += obs.ncols
                up_cols += Observation.from_grid(
                    grid_from_message(msg, base, UPSTREAM)
                ).ncols
                branchy += sum(
                    1
                    for c in range(1, obs.ncols + 1)
                    if len(column_options(obs, c, STRICT)) > 1
                )
                res = decode_strict(obs, bases=(base,))
                if len(res) == 1:
                    uniq += 1
                if len(res) == 1 and res[0][2] == msg:
                    correct += 1
            print(
                f"{base:>7} {kind:>10} {n:>4} {TRIALS:>7} {uniq / TRIALS:>6.0%} "
                f"{correct / TRIALS:>7.0%} {branchy:>13} "
                f"{up_cols / TRIALS:>7.1f}/{st_cols / TRIALS:<7.1f}"
            )
