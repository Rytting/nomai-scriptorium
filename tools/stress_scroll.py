"""Does the root's own arrangement ever ruin it for the replies?

The root is chosen first, on whether *it* reads, and then never revisited. A reply
that cannot find a readable placement falls back to its best-looking one and ships
unverified. This crowds the sheet -- long conversations, deep chains, wide fans -- and
counts how often that happens, so that re-laying the root is a fix for something
rather than a fix for nothing.
"""
import itertools
import pathlib
import random
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nomai.codec import read_strict, write  # noqa: E402
from nomai.decode import x_to_record  # noqa: E402
from nomai.glyphs import KNOWN_GLYPHS  # noqa: E402
from nomai.oracle import STRICT  # noqa: E402
from nomai.scroll import (  # noqa: E402
    Spiral,
    _lay,
    analyze_scroll,
    balance_tilt,
    check_tree,
    render_scroll,
)

BASE = 256
WORDS = ["yes", "no", "wait", "why", "come here", "I will wait", "look at this",
         "the eye is out there", "not yet", "how long", "who wrote this",
         "we should not have come", "it was already here", "Come to the Ash Twin"]
NAMES = ["", "Poke", "Solanum", "Clary", "Ramie"]

SHAPES = {
    "eight in a fan": [None] + [0] * 7,
    "eight in a chain": [None] + list(range(7)),
    "a wide tree": [None, 0, 0, 0, 1, 1, 2, 4, 4],
    "a deep tree": [None, 0, 1, 1, 2, 4, 5, 5, 7, 8],
}

rng = random.Random(5)
runs = full = 0
unverified_replies = 0
rows = []
for (shape, parents), flip, tight in itertools.product(
        SHAPES.items(), (1,), (0.29,)):
    spec = [(rng.choice(WORDS), rng.choice(NAMES), p) for p in parents]
    grids = [write(t, BASE, STRICT, s or None, p) for t, s, p in spec]
    sp = [Spiral(g, p) for g, (_, _, p) in zip(grids, spec)]
    hw = 0.15
    runs += 1
    t0 = time.time()

    # lay it the way render_scroll does, then ask of each placement: did it verify?
    laid = _lay(sp, balance_tilt(sp, flip, tight), flip, tight, KNOWN_GLYPHS, hw, 47,
                verify=True)
    unverified = [i for i, it in enumerate(laid) if not it.verified]

    svg = render_scroll(sp, KNOWN_GLYPHS, hw, 47, flip, tight)
    try:
        obs, edges, _ = analyze_scroll(svg)
        got = []
        for cands in obs:
            r = read_strict(cands, bases=(BASE,))
            got.append(x_to_record(r[0][1], BASE, False, STRICT) if len(r) == 1 else None)
        tree_ok, _ = check_tree(edges, [g[2] if g else None for g in got], len(got))
        bad = [i for i, (g, (t, s, p)) in enumerate(zip(got, spec))
               if not (g and g[1] == t and (g[0] or "") == (s or "") and g[2] == p)]
        ok = not bad and tree_ok
    except Exception as exc:  # noqa: BLE001
        ok, bad = False, f"{type(exc).__name__}"
    full += ok
    unverified_replies += len(unverified)
    rows.append((shape, flip, tight, len(spec), unverified, ok, bad,
                 int((time.time() - t0) * 1000)))

print(f"{full}/{runs} scrolls round tripped completely\n")
print(f"{'shape':<17} flip  tight  n   unverified placements   reads back   ms")
print("-" * 74)
for shape, flip, tight, n, unver, ok, bad, ms in rows:
    print(f"{shape:<17} {flip:>4}  {tight:<5}  {n:>2}  {str(unver):<22} "
          f"{'yes' if ok else 'NO ' + str(bad):<12} {ms:>6}")
print(f"\nplacements that shipped unverified: {unverified_replies}")
