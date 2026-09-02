"""Do the failures cluster on short messages, and if so where do they happen?"""
import collections
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nomai.codec import write  # noqa: E402
from nomai.decode import decode_strict  # noqa: E402
from nomai.glyphs import KNOWN_GLYPHS  # noqa: E402
from nomai.oracle import STRICT  # noqa: E402
from nomai.render import render_grid  # noqa: E402
from nomai.vision import analyze  # noqa: E402

BASE = 256
MESSAGES = [
    "a", "b", "c", "d", "e", "hi", "no", "why", "wait", "come",
    "I will wait", "why not", "The Eye is out there",
    "Come to the Ash Twin Project",
]

by_cols = collections.defaultdict(lambda: [0, 0])
errors = collections.Counter()
fails = []
for msg in MESSAGES:
    grid = write(msg, BASE, STRICT)
    for flip in (1, -1):
        for tight in (0.2, 0.29, 0.5):
            svg = render_grid(grid, KNOWN_GLYPHS, 0.15, 47, 0.0, flip, tight)
            try:
                got = decode_strict(analyze(svg), bases=(BASE,))
                ok = len(got) == 1 and got[0][2] == msg
                why = "" if ok else f"{len(got)} readings"
            except Exception as exc:  # noqa: BLE001
                ok, why = False, str(exc)[:52]
            slot = by_cols[grid.ncols]
            slot[0 if ok else 1] += 1
            if not ok:
                errors[why.split(":")[0]] += 1
                fails.append((msg, grid.ncols, flip, tight, why))

print(f"{'turns':>6}  {'ok':>4} {'fail':>5}   messages of that size")
print("-" * 62)
sizes = collections.defaultdict(set)
for msg in MESSAGES:
    sizes[write(msg, BASE, STRICT).ncols].add(msg)
for n in sorted(by_cols):
    ok, bad = by_cols[n]
    names = ", ".join(sorted(sizes[n]))[:34]
    print(f"{n:>6}  {ok:>4} {bad:>5}   {names}")

print("\nwhere it goes wrong:")
for why, k in errors.most_common():
    print(f"  {k:>3}  {why}")

print("\nevery failure:")
for msg, n, flip, tight, why in fails:
    print(f"  {msg[:22]!r:24} cols={n:<3} flip={flip:>2} b={tight}  {why}")
