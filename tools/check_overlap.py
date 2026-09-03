"""How close do two spirals in a scroll actually come to each other?

Clearance during layout is measured between glyph origins, which is cheap and right in
kind but says nothing on its own about whether the ink collides. A glyph is about 40
across and the band it sits in is six rows deep, so two spirals touch long before their
origins do. This measures both: the closest pair of origins across spirals, and the
closest pair of drawn points, which is the one that decides whether it looks wrong.
"""
import itertools
import math
import pathlib
import random
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nomai.codec import write  # noqa: E402
from nomai.glyphs import KNOWN_GLYPHS  # noqa: E402
from nomai.oracle import STRICT  # noqa: E402
from nomai.render import GLYPH_K as K  # noqa: E402
from nomai.render import MAX_SCALE  # noqa: E402
from nomai.scroll import (  # noqa: E402
    Spiral,
    _lay,
    balance_tilt,
    centres,
    spiral_elements,
)

WORDS = ["yes", "no", "wait", "why", "come here", "I will wait", "look at this",
         "the eye is out there", "not yet", "how long", "who wrote this"]
NAMES = ["", "Poke", "Solanum", "Clary"]
SHAPES = {
    "one reply": [None, 0],
    "two replies": [None, 0, 0],
    "reply to a reply": [None, 0, 1],
    "fan of three": [None, 0, 0, 0],
    "a small tree": [None, 0, 0, 1, 3],
}

rng = random.Random(4)
rows = []
for (shape, parents), flip, tight in itertools.product(
        SHAPES.items(), (1, -1), (0.2, 0.29, 0.45)):
    spec = [(rng.choice(WORDS), rng.choice(NAMES), p) for p in parents]
    grids = [write(t, 256, STRICT, s or None, p) for t, s, p in spec]
    sp = [Spiral(g, p) for g, (_, _, p) in zip(grids, spec)]
    hw = 0.12
    laid = _lay(sp, balance_tilt(sp, flip, tight), flip, tight,
                KNOWN_GLYPHS, hw, 47, verify=True)

    origins, drawn = [], []
    for it in laid:
        origins.append(centres(it.spiral.grid, it.layout, it.shift))
        els, at = spiral_elements(it.spiral.grid, KNOWN_GLYPHS, hw, it.seed,
                                  it.layout, it.shift)
        drawn.append([p for v in at.values() for p in v])

    def closest(sets):
        best = math.inf
        for i in range(len(sets)):
            for j in range(i + 1, len(sets)):
                for p in sets[i]:
                    for q in sets[j]:
                        d = (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2
                        if d < best:
                            best = d
        return math.sqrt(best)

    rows.append((shape, flip, tight, closest(origins), closest(drawn)))

unit = K * MAX_SCALE
print(f"one K*MAX_SCALE is {unit:.0f} units; a glyph is about 40 across\n")
print(f"{'shape':<18} flip tight   closest origins   closest ink   ink verdict")
print("-" * 74)
touching = 0
for shape, flip, tight, o, d in rows:
    verdict = "TOUCHING" if d < 40 else ("close" if d < 90 else "clear")
    touching += d < 40
    print(f"{shape:<18} {flip:>4} {tight:<5}   {o:>9.0f} ({o/unit:4.1f})   "
          f"{d:>7.0f} ({d/unit:4.1f})   {verdict}")
print(f"\n{touching} of {len(rows)} scrolls have ink closer than one glyph width")
