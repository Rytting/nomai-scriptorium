"""Is the SVG separable without any machine learning?

Two questions:
  1. Can connections be told from spike annotations? Both are 2-point strokes.
  2. Can a stroke be matched to a canonical PolySpec by ordered Procrustes fit?
     The SVG preserves vertex order, so the correspondence is already known --
     only similarity (scale, rotation, translation) has to be solved for.
"""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nomai.glyphs import KNOWN_GLYPHS  # noqa: E402
from nomai.svgparse import parse_svg  # noqa: E402

SAMPLES = sorted((ROOT / "assets" / "samples").glob("*.svg"))


def procrustes(src, dst):
    """Best similarity transform src -> dst, with the correspondence given.

    Returns (scale, rotation, rms residual). Closed-form via complex numbers:
    a similarity in the plane is just multiplication by a complex number.
    """
    n = len(src)
    a = [complex(*p) for p in src]
    b = [complex(*p) for p in dst]
    ma = sum(a) / n
    mb = sum(b) / n
    a = [z - ma for z in a]
    b = [z - mb for z in b]
    denom = sum(abs(z) ** 2 for z in a)
    if denom == 0:
        return 0.0, 0.0, float("inf")
    w = sum(bz * az.conjugate() for az, bz in zip(a, b)) / denom
    resid = math.sqrt(sum(abs(bz - w * az) ** 2 for az, bz in zip(a, b)) / n)
    return abs(w), math.atan2(w.imag, w.real), resid


CANON = []
for gid, g in enumerate(KNOWN_GLYPHS, start=1):
    CANON.append((gid, "core", g.core.points, g.core.close))
    if g.annotation is not None:
        CANON.append((gid, "annot", g.annotation.points, g.annotation.close))


def best_match(stroke):
    """Try every canonical PolySpec with the same shape signature."""
    out = []
    for gid, kind, pts, close in CANON:
        if len(pts) != len(stroke.points) or close != stroke.closed:
            continue
        # a closed polygon may be recorded starting at any rotation of its cycle
        rots = range(len(pts)) if close else [0]
        for r in rots:
            rolled = pts[r:] + pts[:r]
            s, th, res = procrustes(rolled, stroke.points)
            out.append((res, gid, kind, s, th))
    out.sort()
    return out


for sample in SAMPLES:
    strokes, circles = parse_svg(sample)
    print(f"\n=== {sample.name}: {len(strokes)} strokes, {len(circles)} circles")

    two = [s for s in strokes in ()] if False else [s for s in strokes if len(s.points) == 2]
    lens = sorted(s.length for s in two)
    print(f"  two-point stroke lengths: {[round(v, 1) for v in lens]}")

    print("  matching each stroke to a canonical PolySpec:")
    unmatched = 0
    for st in strokes:
        cands = best_match(st)
        if not cands:
            unmatched += 1
            continue
        res, gid, kind, s, th = cands[0]
        margin = cands[1][0] - res if len(cands) > 1 else float("inf")
        print(f"    n={len(st.points)} closed={st.closed!s:<5} len={st.length:>7.1f}"
              f" -> glyph {gid:>2} {kind}  resid={res:>6.3f}"
              f"  scale={s:>5.2f}  margin={margin:>6.3f}")
    print(f"  strokes with no candidate of matching shape: {unmatched}")
