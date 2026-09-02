"""How much can a glyph's *shape alone* tell us, with no absolute orientation?

The core digits are built from one square and one hexagon, sliced at different
starting vertices -- so several of them are the same drawn shape rotated. The layout
then applies its own rotation per column, so unless we recover the spiral's absolute
orientation, those glyphs are indistinguishable.

This measures the collapse: how many of the 33 glyphs survive as distinct shapes when
rotation and scale are quotiented out.
"""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nomai.glyphs import KNOWN_GLYPHS  # noqa: E402

TOL = 1e-6


def procrustes_resid(src, dst):
    n = len(src)
    a = [complex(*p) for p in src]
    b = [complex(*p) for p in dst]
    ma, mb = sum(a) / n, sum(b) / n
    a = [z - ma for z in a]
    b = [z - mb for z in b]
    denom = sum(abs(z) ** 2 for z in a)
    if denom == 0:
        return float("inf"), 0.0
    w = sum(bz * az.conjugate() for az, bz in zip(a, b)) / denom
    scale = max(abs(z) for z in a) or 1.0
    resid = math.sqrt(sum(abs(bz - w * az) ** 2 for az, bz in zip(a, b)) / n)
    return resid / scale, math.atan2(w.imag, w.real)


def parts(g):
    out = [(g.core.points, g.core.close)]
    if g.annotation is not None:
        out.append((g.annotation.points, g.annotation.close))
    return out


def same_shape(g1, g2):
    """Are two glyphs related by a similarity transform (rotation + scale)?

    Both parts must fit under the *same* transform, and a closed polygon may be
    written starting at any vertex of its cycle.
    """
    p1, p2 = parts(g1), parts(g2)
    if len(p1) != len(p2):
        return False, None
    if [(len(a), c) for a, c in p1] != [(len(a), c) for a, c in p2]:
        return False, None
    (c1, cl1), (c2, _) = p1[0], p2[0]
    rots = range(len(c1)) if cl1 else [0]
    for r in rots:
        rolled = c1[r:] + c1[:r]
        res, theta = procrustes_resid(rolled, c2)
        if res > 1e-3:
            continue
        if len(p1) == 1:
            return True, theta
        # the annotation must follow the same rotation
        a1, acl1 = p1[1]
        a2, _ = p2[1]
        arots = range(len(a1)) if acl1 else [0]
        for ar in arots:
            arolled = a1[ar:] + a1[:ar]
            ares, atheta = procrustes_resid(arolled, a2)
            if ares <= 1e-3 and abs(
                math.atan2(math.sin(atheta - theta), math.cos(atheta - theta))
            ) < 1e-3:
                return True, theta
    return False, None


n = len(KNOWN_GLYPHS)
parent = list(range(n))


def find(i):
    while parent[i] != i:
        parent[i] = parent[parent[i]]
        i = parent[i]
    return i


pairs = []
for i in range(n):
    for j in range(i + 1, n):
        ok, theta = same_shape(KNOWN_GLYPHS[i], KNOWN_GLYPHS[j])
        if ok:
            pairs.append((i + 1, j + 1, math.degrees(theta)))
            parent[find(i)] = find(j)

groups: dict[int, list[int]] = {}
for i in range(n):
    groups.setdefault(find(i), []).append(i + 1)

print(f"{n} glyphs collapse to {len(groups)} distinct shapes once rotation is removed\n")
for members in sorted(groups.values()):
    if len(members) > 1:
        g = KNOWN_GLYPHS[members[0] - 1]
        kind = "core only" if g.annotation is None else "core+annotation"
        print(f"  indistinguishable without orientation: {members}   ({kind}, "
              f"{len(g.core.points)} pts, closed={g.core.close})")

print("\n  rotation between confusable pairs (degrees):")
for a, b, deg in pairs:
    print(f"    glyph {a:>2} -> glyph {b:>2}: {deg:>8.1f}")

singles = sum(1 for m in groups.values() if len(m) == 1)
print(f"\n  uniquely identifiable by shape alone: {singles}/{n}")
print(f"  need the column's absolute rotation: {n - singles}/{n}")
