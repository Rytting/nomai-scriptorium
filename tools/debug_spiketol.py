"""Where should the spike test's tolerance sit?

For every two-point stroke that touches a spike-capable cluster, compute the
residual of "this is that glyph's spike". A real spike should score at jitter level;
a connection leaving the same vertex heads for another column and should score far
higher. Print both distributions per handwriting level and look for the gap.
"""
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nomai.svgparse import parse_svg  # noqa: E402
from nomai.vision import (  # noqa: E402
    _DSU,
    _resid_fixed,
    _spike_table_cached,
    procrustes,
)

SVG = ROOT / "data" / "svg"
manifest = json.loads((SVG / "manifest.json").read_text(encoding="utf-8"))


def spike_residual(body_strokes, stroke):
    sig = tuple(sorted((len(s.points), s.closed) for s in body_strokes))
    best = math.inf
    for _gid, (core_pts, core_closed), spike_pts in _spike_table_cached().get(sig, []):
        for bs in body_strokes:
            if len(bs.points) != len(core_pts) or bs.closed != core_closed:
                continue
            for r in (range(len(core_pts)) if core_closed else [0]):
                fit = procrustes(core_pts[r:] + core_pts[:r], bs.points)
                if fit is None:
                    continue
                scale, theta, _res, _sh = fit
                w = complex(math.cos(theta), math.sin(theta)) * scale
                for pts in (stroke.points, stroke.points[::-1]):
                    best = min(best, _resid_fixed(w, spike_pts, pts))
    return best


buckets = defaultdict(list)
for entry in manifest:
    strokes, _ = parse_svg(SVG / entry["file"])
    two = [i for i, s in enumerate(strokes) if len(s.points) == 2]
    body = [i for i, s in enumerate(strokes) if len(s.points) > 2]
    owner = defaultdict(list)
    for i in body:
        for p in strokes[i].points:
            owner[p].append(i)
    dsu = _DSU(len(strokes))
    for idxs in owner.values():
        for a in idxs[1:]:
            dsu.union(idxs[0], a)
    groups = defaultdict(list)
    for i in body:
        groups[dsu.find(i)].append(strokes[i])
    home = {p: dsu.find(i) for i in body for p in strokes[i].points}

    for i in two:
        a, b = strokes[i].points
        for h in {x for x in (home.get(a), home.get(b)) if x is not None}:
            r = spike_residual(groups[h], strokes[i])
            if r < math.inf:
                # a real spike is short; a connection has to span columns
                kind = "short" if math.dist(a, b) < 35 else "long"
                buckets[(entry["handwriting"], kind)].append(r)

for hw in (0.0, 0.3, 0.6):
    for kind in ("short", "long"):
        vals = sorted(buckets.get((hw, kind), []))
        if not vals:
            continue
        n = len(vals)
        print(f"hw={hw}  {kind:>5}  n={n:>4}  "
              f"min={vals[0]:>7.2f}  p50={vals[n // 2]:>8.2f}  "
              f"p90={vals[min(n - 1, int(n * 0.9))]:>9.2f}  max={vals[-1]:>10.2f}")
