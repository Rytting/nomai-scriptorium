"""How often does the drawing's built-in ambiguity actually produce a wrong reading?

`hi` and `&i` draw identically, so the decoder must guess, and it guesses with a
language prior. This measures how often that guess is wrong -- and, separately, how
often the true message is not even the only plausible reading, which is the number
that matters if you care about being *told* the reading is uncertain.
"""
import random
import string
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nomai.decode import Observation, decode_backward, text_score  # noqa: E402
from nomai.gridgen import grid_from_message  # noqa: E402

WORDS = (
    "the nomai came to this solar system searching for eye of universe a signal "
    "older than itself and they never did find it built ash twin project send "
    "memories back through time then ghost matter killed every last one of them "
    "before ever ran quantum moon brittle hollow dark bramble sun station"
).split()

TRIALS = 40
LENGTHS = [2, 3, 4, 6, 8, 12, 20, 40]


def english(rng, n):
    out = []
    while sum(len(w) + 1 for w in out) < n + 8:
        out.append(rng.choice(WORDS))
    return " ".join(out)[:n].strip()


def gibberish(rng, n):
    return "".join(rng.choice(string.ascii_lowercase) for _ in range(n))


def run(base, gen, lengths):
    print(f"\nbase {base}, messages: {gen.__name__}")
    print(f"{'len':>4} {'top1 ok':>8} {'true found':>11} {'ties':>6} "
          f"{'mean readings':>14}  example failure")
    print("-" * 78)
    for n in lengths:
        rng = random.Random(1234 + n)
        top1 = found = ties = 0
        readings = 0
        failure = ""
        for _ in range(TRIALS):
            msg = gen(rng, n)
            obs = Observation.from_grid(grid_from_message(msg, base))
            res = decode_backward(obs, bases=(base,))
            texts = [t for _, _, t in res]
            readings += len(texts)
            if msg in texts:
                found += 1
            if texts and texts[0] == msg:
                top1 += 1
            elif texts and not failure:
                failure = f"{msg!r} -> {texts[0]!r}"
            # a tie is a rival reading scoring at least as well as the truth
            if msg in texts:
                best_other = max(
                    (text_score(t) for t in texts if t != msg), default=-1.0
                )
                if best_other >= text_score(msg):
                    ties += 1
        print(f"{n:>4} {top1 / TRIALS:>7.0%} {found / TRIALS:>10.0%} "
              f"{ties / TRIALS:>5.0%} {readings / TRIALS:>13.1f}  {failure}")


run(256, english, LENGTHS)
run(256, gibberish, LENGTHS)
run(200_000, english, [2, 3, 4, 6, 8, 12])
run(200_000, gibberish, [2, 3, 4, 6, 8, 12])
