"""Where does a conversation stop reading back?

Someone tried the page and had "mixed luck" with branching, which is the shape of a
failure that happens sometimes rather than always. This throws a wide net -- shapes,
depths, message lengths, windings, coils, handwriting -- and records what failed and
whether the guilty spiral fails on its own too. A spiral that fails alone is the
reader's old per-drawing limit; one that reads alone but not in place is the scroll's
own fault, and those are the interesting ones.
"""
import itertools
import pathlib
import random
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nomai.codec import read_strict, write  # noqa: E402
from nomai.decode import x_to_record  # noqa: E402
from nomai.glyphs import KNOWN_GLYPHS  # noqa: E402
from nomai.oracle import STRICT  # noqa: E402
from nomai.render import render_grid  # noqa: E402
from nomai.scroll import Spiral, analyze_scroll, check_tree, render_scroll  # noqa: E402
from nomai.svgparse import parse_svg  # noqa: E402
from nomai.vision import observe_all  # noqa: E402

BASE = 256
WORDS = ["yes", "no", "wait", "why", "come here", "I will wait", "look at this",
         "the eye is out there", "not yet", "how long", "who wrote this",
         "Come to the Ash Twin Project"]
NAMES = ["", "Poke", "Solanum", "Clary", "Ramie"]

SHAPES = {
    "one reply": [None, 0],
    "two replies": [None, 0, 0],
    "reply to a reply": [None, 0, 1],
    "fan of three": [None, 0, 0, 0],
    "chain of four": [None, 0, 1, 2],
    "mixed tree": [None, 0, 0, 1, 3],
}


def alone(text, sig, parent, flip, tight, hw):
    """Does this spiral read when it is the only thing on the sheet?"""
    try:
        g = write(text, BASE, STRICT, sig or None, parent)
        svg = render_grid(g, KNOWN_GLYPHS, hw, 47, 0.0, flip, tight)
        got = read_strict(observe_all(parse_svg(svg)[0]), bases=(BASE,))
        if len(got) != 1:
            return False
        rec = x_to_record(got[0][1], BASE, False, STRICT)
        return bool(rec) and rec[1] == text and (rec[0] or "") == (sig or "")
    except Exception:  # noqa: BLE001
        return False


rng = random.Random(11)
runs, ok = 0, 0
scroll_fault, reader_fault = [], []

combos = list(itertools.product(SHAPES.items(), (1, -1), (0.2, 0.29, 0.45), (0.0, 0.15)))
for (shape, parents), flip, tight, hw in combos:
    spec = [(rng.choice(WORDS), rng.choice(NAMES), p) for p in parents]
    runs += 1
    try:
        grids = [write(t, BASE, STRICT, s or None, p) for t, s, p in spec]
        svg = render_scroll([Spiral(g, p) for g, (_, _, p) in zip(grids, spec)],
                            KNOWN_GLYPHS, hw, 47, flip, tight)
        obs, edges, _ = analyze_scroll(svg)
        got = []
        for cands in obs:
            r = read_strict(cands, bases=(BASE,))
            got.append(x_to_record(r[0][1], BASE, False, STRICT) if len(r) == 1 else None)
        parents_got = [g[2] if g else None for g in got]
        tree_ok, why = check_tree(edges, parents_got, len(got)) if len(got) > 1 else (True, "")
        bad = [i for i, (g, (t, s, p)) in enumerate(zip(got, spec))
               if not (g and g[1] == t and (g[0] or "") == (s or "") and g[2] == p)]
        if not bad and tree_ok:
            ok += 1
            continue
        note = why if not tree_ok else ""
    except Exception as exc:  # noqa: BLE001
        bad, note = list(range(len(spec))), f"{type(exc).__name__}: {exc}"[:60]

    for i in set(bad):
        t, s, p = spec[i]
        solo = alone(t, s, p, flip, tight, hw)
        row = (shape, flip, tight, hw, i, p, t[:22], note)
        (scroll_fault if solo else reader_fault).append(row)

print(f"{ok}/{runs} scrolls round tripped completely\n")
for name, rows in (("the scroll's own fault (the spiral reads fine alone)", scroll_fault),
                   ("the reader's per-drawing limit (fails alone too)", reader_fault)):
    print(f"── {name}: {len(rows)}")
    for shape, flip, tight, hw, i, p, t, note in rows[:14]:
        print(f"   {shape:<18} flip={flip:>2} b={tight:<5} hw={hw:<5} "
              f"spiral {i} (on {p}) {t!r:<24} {note}")
    print()
